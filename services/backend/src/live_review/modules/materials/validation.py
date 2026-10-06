import hashlib
import json
import subprocess
from pathlib import Path

from live_review.core.errors import ApiError


def validate_file(
    path: Path,
    declared_size: int,
    declared_hash: str | None,
    media_type: str,
    purpose: str,
    ffprobe: str,
) -> str:
    if path.stat().st_size != declared_size or declared_size == 0:
        raise ApiError(422, "file_size_mismatch", "文件大小与声明不一致")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if declared_hash and digest != declared_hash:
        raise ApiError(422, "file_hash_mismatch", "文件校验失败，请重新上传")
    if purpose == "transcript":
        if media_type != "text/plain" or declared_size > 10 * 1024 * 1024:
            raise ApiError(415, "unsupported_format", "逐字稿须为小于10MiB的UTF-8文本")
        with path.open("rb") as probe:
            if probe.read(5) == b"%PDF-":
                raise ApiError(415, "format_mismatch", "PDF只能作为参考材料上传")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeError as exc:
            raise ApiError(422, "invalid_transcript", "逐字稿必须是UTF-8文本") from exc
        if not text.strip() or any(ord(char) < 32 and char not in "\n\r\t" for char in text):
            raise ApiError(422, "invalid_transcript", "逐字稿为空或包含二进制字符")
    elif purpose == "reference_pdf":
        if media_type != "application/pdf" or declared_size > 20 * 1024 * 1024:
            raise ApiError(415, "unsupported_format", "参考资料须为小于20MiB的PDF")
        from pypdf import PdfReader

        try:
            with path.open("rb") as source:
                if source.read(5) != b"%PDF-":
                    raise ValueError("Invalid PDF header")
                source.seek(0)
                reader = PdfReader(source, strict=True)
                if reader.is_encrypted or len(reader.pages) == 0:
                    raise ValueError("Encrypted or empty PDF")
                # Material purpose remains reference_pdf; it never becomes speech evidence.
                for page in reader.pages:
                    _ = page.mediabox
        except Exception as exc:
            raise ApiError(422, "invalid_pdf", "无法解析PDF或PDF已加密") from exc
    else:
        allowed = {
            "video/mp4": "mp4",
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/mpeg": "mp3",
            "audio/mp4": "mp4",
            "audio/aac": "aac",
        }
        if media_type not in allowed:
            raise ApiError(415, "unsupported_format", "直播材料仅支持MP4/WAV/MP3/M4A/AAC")
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-f",
                    "mov" if media_type in {"video/mp4", "audio/mp4"} else allowed[media_type],
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ApiError(503, "media_probe_unavailable", "媒体验证服务暂不可用") from exc
        try:
            info = json.loads(result.stdout)
            formats = info["format"]["format_name"].split(",")
            streams = info["streams"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ApiError(415, "invalid_media", "文件不是可解析的媒体") from exc
        types = {stream.get("codec_type") for stream in streams}
        required = "video" if media_type == "video/mp4" else "audio"
        if result.returncode or allowed[media_type] not in formats or required not in types:
            raise ApiError(415, "format_mismatch", "媒体实际格式与声明不符")
    return digest
