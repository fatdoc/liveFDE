"""Model-derived observations and file-wide anonymous speaker clustering."""

import math
import unicodedata
from dataclasses import dataclass

from ..contracts import ASRError, ASRSegment


@dataclass
class Observation:
    segment: ASRSegment
    embedding: object = None


def punctuation_input(text):
    """Remove sentence punctuation before restoration, preserving numeric/word syntax."""
    characters = []
    for index, character in enumerate(text):
        previous = text[index - 1] if index else ""
        following = text[index + 1] if index + 1 < len(text) else ""
        numeric = character in ".,:/-" and previous.isdigit() and following.isdigit()
        apostrophe = (
            character in "'’"
            and previous.isascii()
            and previous.isalpha()
            and following.isascii()
            and following.isalpha()
        )
        if not unicodedata.category(character).startswith("P") or numeric or apostrophe:
            characters.append(character)
        elif (
            previous.isascii()
            and previous.isalpha()
            and following.isascii()
            and following.isalpha()
        ):
            characters.append(" ")
    return "".join(characters)


def analyze_audio(models, audio, request, *, offset_ms=0, first_index=0, windowed=False):
    import numpy as np

    cfg = models.config
    duration_ms = len(audio) * 1000 // cfg.sample_rate
    vad = models.generate(cfg.vad_model, audio)
    if not vad or not isinstance(vad[0].get("value"), list):
        raise ASRError("local_vad_result_invalid")
    intervals = vad[0]["value"]
    observed = []
    for interval in intervals:
        start, end = (int(interval[0]), int(interval[1]))
        if start < 0 or start >= duration_ms or end <= start or end > duration_ms + 50:
            raise ASRError("local_vad_result_invalid")
        end = min(end, duration_ms)
        # Bound long utterance decoding, regardless of VAD implementation limits.
        for begin in range(start, end, cfg.vad_max_segment_ms):
            stop = min(end, begin + cfg.vad_max_segment_ms)
            samples = audio[begin * 16 : stop * 16]
            if len(samples) < 400:
                raise ASRError("local_speech_segment_too_short")
            raw = models.generate(
                cfg.asr_model,
                samples,
                language={"auto": None, "zh": "中文", "zh-CN": "中文", "en": "英文", "ja": "日文"}[
                    request.language
                ],
                max_length=512,
                batch_size=1,
            )
            text = raw[0].get("text", "").strip() if raw else ""
            if not text:
                raise ASRError("local_asr_empty_for_speech")
            if request.punctuation and cfg.punctuation_model:
                punc = models.generate(
                    cfg.punctuation_model, punctuation_input(text), data_type="text"
                )
                text = punc[0].get("text", text) if punc else text
            embedding, emotion, score = None, None, None
            if request.speaker and len(samples) >= cfg.min_speaker_duration_ms * 16:
                result = models.generate(cfg.speaker_model, samples)
                embedding = result[0]["spk_embedding"].detach().cpu().numpy().reshape(-1)
                if not np.isfinite(embedding).all() or np.linalg.norm(embedding) == 0:
                    raise ASRError("local_speaker_result_invalid")
                embedding = embedding / np.linalg.norm(embedding)
            if request.emotion and len(samples) >= 6400:
                result = models.generate(
                    cfg.emotion_model, samples, granularity="utterance", extract_embedding=False
                )
                if result and result[0].get("scores"):
                    labels, scores = result[0]["labels"], result[0]["scores"]
                    best = max(range(len(scores)), key=lambda index: scores[index])
                    emotion, score = labels[best], float(scores[best])
                    if not math.isfinite(score) or not 0 <= score <= 1:
                        raise ASRError("local_emotion_result_invalid")
            segment = ASRSegment(
                id=f"seg-{first_index + len(observed):06d}",
                text=text,
                start_ms=offset_ms + begin,
                end_ms=offset_ms + stop,
                timestamp_source=(
                    "vad_window"
                    if windowed
                    or end - start >= cfg.vad_max_segment_ms - 50
                    or begin != start
                    or stop != end
                    else "vad"
                ),
                emotion=emotion,
                emotion_confidence=score,
                emotion_source="model" if emotion is not None else "unavailable",
            )
            observed.append(Observation(segment, embedding))
    return observed


def cluster_speakers(observations, config):
    import numpy as np

    available = [i for i, item in enumerate(observations) if item.embedding is not None]
    if not available:
        return tuple(item.segment for item in observations)
    vectors = np.stack([observations[i].embedding for i in available])
    if len(available) == 1:
        labels = [0]
    else:
        from sklearn.cluster import AgglomerativeClustering

        labels = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=1 - config.speaker_similarity_threshold,
        ).fit_predict(vectors)
        if len(set(labels)) > config.max_speakers:
            labels = AgglomerativeClustering(
                n_clusters=config.max_speakers, metric="cosine", linkage="average"
            ).fit_predict(vectors)
    # Renumber by first appearance; labels have no enrolled identity meaning.
    names, assignments = {}, {}
    for index, label in zip(available, labels, strict=True):
        names.setdefault(int(label), f"speaker-{len(names) + 1:02d}")
        assignments[index] = names[int(label)]
    return tuple(
        item.segment.model_copy(
            update={"speaker_id": assignments[i], "speaker_source": "clustering"}
        )
        if i in assignments
        else item.segment
        for i, item in enumerate(observations)
    )
