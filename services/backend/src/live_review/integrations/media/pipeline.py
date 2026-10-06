import json
import math
import shutil
import wave
from pathlib import Path
from uuid import uuid4

from live_review.integrations.media.files import artifact, controlled_file, fingerprint, snapshot
from live_review.integrations.media.models import AudioSegment, Extraction
from live_review.integrations.media.process import Cancel, MediaError, check_cancel, run_process

# No playlist, concat, image sequence or network demuxers. Input content, not its
# extension, selects among these self-contained media container formats.
FORMATS = "mov,matroska,webm,avi,mpeg,mpegts,flv,wav,mp3,ogg,flac,aac"
RATE = 16000


def milliseconds(samples: int) -> int:
    return (samples * 1000 + RATE - 1) // RATE


def _seconds(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def split_audio(
    audio: Path, root: Path, segment_seconds: int, offset_ms: int, cancel: Cancel
) -> tuple[AudioSegment, ...]:
    segments = []
    with wave.open(str(audio), "rb") as source:
        total = source.getnframes()
        if math.ceil(total / (segment_seconds * RATE)) > 2000:
            raise MediaError("segment_count_limit")
        for index, start in enumerate(range(0, total, segment_seconds * RATE)):
            check_cancel(cancel)
            end = min(total, start + segment_seconds * RATE)
            path = audio.parent / f"segment-{index:05d}.wav"
            with wave.open(str(path), "wb") as target:
                target.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
                remaining = end - start
                while remaining:
                    check_cancel(cancel)
                    frames = source.readframes(min(remaining, RATE))
                    if not frames:
                        raise MediaError("truncated_wav")
                    target.writeframesraw(frames)
                    remaining -= len(frames) // 2
            segments.append(
                AudioSegment(
                    index=index,
                    start_sample=start,
                    end_sample=end,
                    start_ms=offset_ms + milliseconds(start),
                    end_ms=offset_ms + milliseconds(end),
                    artifact=artifact(root, path, cancel),
                )
            )
    return tuple(segments)


def extract_audio(
    source: Path,
    *,
    input_root: Path,
    output_root: Path,
    segment_seconds: int = 300,
    ffmpeg_timeout_seconds: float = 600,
    ffprobe_timeout_seconds: float = 30,
    max_duration_seconds: int = 14400,
    cancel: Cancel = None,
) -> Extraction:
    if not 1 <= segment_seconds <= 3600 or not 1 <= max_duration_seconds <= 86400:
        raise MediaError("invalid_media_limits")
    try:
        source = controlled_file(input_root, source)
        root = Path(output_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as error:
        raise MediaError("invalid_local_path") from error
    if source.stat().st_size > 16 * 1024**3:
        raise MediaError("source_size_limit")
    run = root / uuid4().hex
    run.mkdir(mode=0o700)
    captured = run / "source.snapshot"
    try:
        digest, size = snapshot(source, captured, cancel)
        common = ["-protocol_whitelist", "file,pipe", "-format_whitelist", FORMATS]
        raw = run_process(
            [
                "ffprobe",
                "-v",
                "error",
                *common,
                "-show_entries",
                "format=duration,start_time:stream=index,codec_type,duration,start_time",
                "-of",
                "json",
                str(captured),
            ],
            timeout=ffprobe_timeout_seconds,
            cancel=cancel,
        )
        try:
            probe = json.loads(raw)
            stream = next(s for s in probe.get("streams", []) if s.get("codec_type") == "audio")
        except StopIteration as error:
            raise MediaError("no_audio_track") from error
        except (ValueError, TypeError) as error:
            raise MediaError("invalid_probe_result") from error
        duration = _seconds(probe.get("format", {}).get("duration"))
        if duration is not None and (duration <= 0 or duration > max_duration_seconds):
            raise MediaError("source_duration_limit")
        origin = _seconds(probe.get("format", {}).get("start_time")) or 0
        stream_start = _seconds(stream.get("start_time"))
        if stream_start is None:
            stream_start = origin
        offset = max(0, round((stream_start - origin) * 1000))
        output = run / "audio.wav"
        run_process(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-v",
                "error",
                "-xerror",
                "-err_detect",
                "explode",
                *common,
                "-i",
                str(captured),
                "-map",
                f"0:{int(stream['index'])}",
                "-vn",
                "-sn",
                "-dn",
                "-ac",
                "1",
                "-ar",
                str(RATE),
                "-c:a",
                "pcm_s16le",
                "-t",
                str(max_duration_seconds + 1),
                "-f",
                "wav",
                "-n",
                str(output),
            ],
            timeout=ffmpeg_timeout_seconds,
            cancel=cancel,
        )
        with wave.open(str(output), "rb") as audio:
            samples = audio.getnframes()
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, RATE):
                raise MediaError("invalid_wav_format")
            if not 0 < samples <= max_duration_seconds * RATE:
                raise MediaError("audio_duration_limit")
        if fingerprint(source, cancel) != (digest, size):
            raise MediaError("source_changed")
        segments = split_audio(output, root, segment_seconds, offset, cancel)
        versions = [
            run_process([tool, "-version"], timeout=ffprobe_timeout_seconds, cancel=cancel)
            .decode("utf-8", "replace")
            .splitlines()[0][:240]
            for tool in ("ffmpeg", "ffprobe")
        ]
        result = Extraction(
            source_sha256=digest,
            source_size_bytes=size,
            source_duration_ms=round(duration * 1000) if duration is not None else None,
            source_audio_stream_index=int(stream["index"]),
            audio_offset_ms=offset,
            audio_samples=samples,
            audio_duration_ms=milliseconds(samples),
            audio=artifact(root, output, cancel),
            segments=segments,
            ffmpeg_version=versions[0],
            ffprobe_version=versions[1],
        )
        (run / "extraction.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result
    except BaseException:
        shutil.rmtree(run)
        raise
    finally:
        captured.unlink(missing_ok=True)
