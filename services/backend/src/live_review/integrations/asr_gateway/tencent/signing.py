"""Pure Tencent TC3 and realtime-V2 signatures; never log the returned credentials."""

import base64
import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import urlencode


def tc3_headers(secret_id, secret_key, action, body: bytes, timestamp: int):
    host = "asr.tencentcloudapi.com"
    content_type = "application/json; charset=utf-8"
    headers = f"content-type:{content_type}\nhost:{host}\nx-tc-action:{action.lower()}\n"
    signed = "content-type;host;x-tc-action"
    canonical = f"POST\n/\n\n{headers}\n{signed}\n{hashlib.sha256(body).hexdigest()}"
    date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
    scope = f"{date}/asr/tc3_request"
    message = (
        f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    )
    key = ("TC3" + secret_key).encode()
    for part in (date, "asr", "tc3_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, message.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": content_type,
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": "2019-06-14",
        "X-TC-Timestamp": str(timestamp),
        "Authorization": f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, "
        f"SignedHeaders={signed}, Signature={signature}",
    }


def realtime_url(app_id: str, secret_key: str, params: dict) -> str:
    host_path = f"asr.cloud.tencent.com/asr/v2/{app_id}"
    ordered = sorted(params.items())
    message = host_path + "?" + "&".join(f"{key}={value}" for key, value in ordered)
    signature = base64.b64encode(
        hmac.new(secret_key.encode(), message.encode(), hashlib.sha1).digest()
    ).decode()
    return "wss://" + host_path + "?" + urlencode(ordered + [("signature", signature)])
