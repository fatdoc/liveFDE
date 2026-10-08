"""Fail-closed RFC 8216 attribute parsing before FFmpeg sees a playlist.

Unknown extensions are rejected, not forwarded to a potentially more permissive
FFmpeg parser. Every URI-bearing tag uses the same quoted URI rule and relay.
"""

import re
from urllib.parse import urljoin

from live_review.integrations.capture.contracts import CaptureError

# Deliberately bounded supported subset. Unsupported extensions need review/tests.
ATTRIBUTES = {
    "EXT-X-KEY": {"METHOD", "URI", "IV", "KEYFORMAT", "KEYFORMATVERSIONS"},
    "EXT-X-SESSION-KEY": {"METHOD", "URI", "IV", "KEYFORMAT", "KEYFORMATVERSIONS"},
    "EXT-X-MAP": {"URI", "BYTERANGE"},
    "EXT-X-MEDIA": {
        "TYPE",
        "URI",
        "GROUP-ID",
        "LANGUAGE",
        "ASSOC-LANGUAGE",
        "NAME",
        "DEFAULT",
        "AUTOSELECT",
        "FORCED",
        "INSTREAM-ID",
        "CHARACTERISTICS",
        "CHANNELS",
    },
    "EXT-X-STREAM-INF": {
        "BANDWIDTH",
        "AVERAGE-BANDWIDTH",
        "CODECS",
        "RESOLUTION",
        "FRAME-RATE",
        "HDCP-LEVEL",
        "AUDIO",
        "VIDEO",
        "SUBTITLES",
        "CLOSED-CAPTIONS",
        "VIDEO-RANGE",
    },
    "EXT-X-I-FRAME-STREAM-INF": {
        "URI",
        "BANDWIDTH",
        "AVERAGE-BANDWIDTH",
        "CODECS",
        "RESOLUTION",
        "HDCP-LEVEL",
        "VIDEO",
        "VIDEO-RANGE",
    },
    "EXT-X-SESSION-DATA": {"DATA-ID", "VALUE", "URI", "LANGUAGE"},
    "EXT-X-START": {"TIME-OFFSET", "PRECISE"},
    "EXT-X-SERVER-CONTROL": {
        "CAN-SKIP-UNTIL",
        "CAN-SKIP-DATERANGES",
        "HOLD-BACK",
        "PART-HOLD-BACK",
        "CAN-BLOCK-RELOAD",
    },
    "EXT-X-PART-INF": {"PART-TARGET"},
    "EXT-X-PART": {"URI", "DURATION", "INDEPENDENT", "BYTERANGE", "GAP"},
    "EXT-X-PRELOAD-HINT": {"TYPE", "URI", "BYTERANGE-START", "BYTERANGE-LENGTH"},
    "EXT-X-RENDITION-REPORT": {"URI", "LAST-MSN", "LAST-PART"},
    "EXT-X-SKIP": {"SKIPPED-SEGMENTS", "RECENTLY-REMOVED-DATERANGES"},
    "EXT-X-DATERANGE": {
        "ID",
        "CLASS",
        "START-DATE",
        "END-DATE",
        "DURATION",
        "PLANNED-DURATION",
        "SCTE35-CMD",
        "SCTE35-OUT",
        "SCTE35-IN",
        "END-ON-NEXT",
    },
}
PLAIN = {
    "EXTM3U",
    "EXTINF",
    "EXT-X-VERSION",
    "EXT-X-TARGETDURATION",
    "EXT-X-MEDIA-SEQUENCE",
    "EXT-X-DISCONTINUITY-SEQUENCE",
    "EXT-X-ENDLIST",
    "EXT-X-PLAYLIST-TYPE",
    "EXT-X-I-FRAMES-ONLY",
    "EXT-X-INDEPENDENT-SEGMENTS",
    "EXT-X-BYTERANGE",
    "EXT-X-DISCONTINUITY",
    "EXT-X-PROGRAM-DATE-TIME",
    "EXT-X-GAP",
    "EXT-X-BITRATE",
    "EXT-X-ALLOW-CACHE",
}
PLAYLIST_URIS = {"EXT-X-MEDIA", "EXT-X-I-FRAME-STREAM-INF", "EXT-X-RENDITION-REPORT"}
ATTRIBUTE = re.compile(r'([A-Z0-9-]+)=(?:"([^"\r\n\\]*)"|([^,\s"\\]+))(?=,|$)')


def attributes(text):
    values = []
    seen = set()
    offset = 0
    while offset < len(text):
        match = ATTRIBUTE.match(text, offset)
        if not match or match[1] in seen:
            raise CaptureError("invalid_hls_attributes")
        key, quoted, plain = match.groups()
        value = quoted if quoted is not None else plain
        if any(ord(c) < 32 for c in value):
            raise CaptureError("invalid_hls_attributes")
        values.append((key, value, quoted is not None))
        seen.add(key)
        offset = match.end()
        if offset < len(text):
            offset += 1
            if offset == len(text):
                raise CaptureError("invalid_hls_attributes")
    if not values:
        raise CaptureError("invalid_hls_attributes")
    return values


def rewrite(body, base, register, *, resolve=urljoin):
    if len(body) > 1048576:
        raise CaptureError("playlist_limit")
    try:
        lines = body.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        raise CaptureError("invalid_hls_playlist") from None
    if not lines or lines[0].strip() != "#EXTM3U":
        raise CaptureError("invalid_hls_playlist")
    result = []
    next_playlist = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if "{$" in line or any(ord(c) < 32 for c in line):
            raise CaptureError("unsupported_hls_syntax")
        if not line.startswith("#"):
            result.append(register(resolve(base, line), "playlist" if next_playlist else "segment"))
            next_playlist = False
            continue
        tag, separator, payload = line[1:].partition(":")
        if tag in PLAIN:
            result.append(line)
        elif tag in ATTRIBUTES:
            if not separator:
                raise CaptureError("invalid_hls_attributes")
            parsed = attributes(payload)
            rewritten = []
            for key, value, quoted in parsed:
                if key not in ATTRIBUTES[tag]:
                    raise CaptureError("unsupported_hls_attribute")
                if key == "URI":
                    if not quoted or not value:
                        raise CaptureError("invalid_hls_uri")
                    kind = (
                        "playlist"
                        if tag in PLAYLIST_URIS
                        else (
                            "key"
                            if tag in {"EXT-X-KEY", "EXT-X-SESSION-KEY"}
                            else "map"
                            if tag == "EXT-X-MAP"
                            else "segment"
                        )
                    )
                    value = register(resolve(base, value), kind)
                rewritten.append(key + "=" + ('"' + value + '"' if quoted else value))
            next_playlist = tag == "EXT-X-STREAM-INF"
            result.append("#" + tag + ":" + ",".join(rewritten))
        elif tag.startswith("EXT"):
            raise CaptureError("unsupported_hls_tag")
        # Plain comments are dropped, not forwarded as possible unknown directives.
    return ("\n".join(result) + "\n").encode()
