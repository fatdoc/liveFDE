"""Restricted WeChat HTTPS candidates; never decode or regenerate signed queries."""

from urllib.parse import urljoin, urlsplit

from live_review.integrations.capture.contracts import CaptureError


def validate_text(url):
    # urlsplit/urljoin silently discard some controls; reject them before parsing.
    if any(ord(c) < 33 or ord(c) == 127 for c in url) or "#" in url or "\\" in url:
        raise CaptureError("unsafe_stream_url")


def https_candidate(url, domains):
    validate_text(url)
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.username is not None or parts.password is not None:
            raise CaptureError("unsafe_stream_url")
        if parts.scheme != "http":
            return url
        if (
            parts.port not in {None, 80}
            or not (host == "wxlivecdn.com" or host.endswith(".wxlivecdn.com"))
            or not any(host == d or host.endswith("." + d) for d in domains)
        ):
            raise CaptureError("unsafe_stream_url")
        # Slice the original suffix, retaining even an empty '?' and exact escapes.
        authority_start = url.index(":") + 3
        suffix_start = authority_start + len(parts.netloc)
        authority = parts.netloc.split(":", 1)[0]
        return "https://" + authority + url[suffix_start:]
    except ValueError:
        raise CaptureError("unsafe_stream_url") from None


def resolve_reference(base, reference):
    validate_text(reference)
    # urljoin can remove an empty query or inherit the base query for '?'.
    # Absolute signed URLs must not be normalized at all.
    if urlsplit(reference).scheme:
        return reference
    joined = urljoin(base, reference)
    if "?" in reference:
        return joined.split("?", 1)[0] + "?" + reference.split("?", 1)[1]
    return joined


def request_target(url):
    parts = urlsplit(url)
    return (parts.path or "/") + ("?" + parts.query if "?" in url else "")
