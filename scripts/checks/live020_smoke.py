"""Attach a local synthetic test clip through the real API; never a platform-capture claim."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

import httpx
from live020_environment import RUNTIME, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=UUID, required=True)
    parser.add_argument("--media", type=Path, required=True)
    args = parser.parse_args()
    environment()  # Refuse foreign private runtime configuration before writes.
    path = args.media.resolve(strict=True)
    if not path.is_relative_to(RUNTIME / "fixtures") or path.suffix != ".mp4":
        raise RuntimeError("synthetic_fixture_required")
    if not 0 < path.stat().st_size <= 10_000_000:
        raise RuntimeError("fixture_size_limit")
    account_path = RUNTIME / "browser-account.json"
    if account_path.is_symlink() or account_path.stat().st_mode & 0o077:
        raise RuntimeError("unsafe_browser_account")
    account = json.loads(account_path.read_text())
    headers = {"Origin": "http://127.0.0.1:5199", "Sec-Fetch-Site": "same-origin"}
    with httpx.Client(base_url="http://127.0.0.1:8199/api/v1", timeout=60) as client:
        login = client.post("/auth/login", headers=headers, json=account)
        login.raise_for_status()
        headers["X-CSRF-Token"] = login.json()["csrf_token"]
        session = client.get(f"/sessions/{args.session}")
        session.raise_for_status()
        if not session.json()["title"].startswith("LIVE-020 合成"):
            raise RuntimeError("synthetic_session_required")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        initialized = client.post(
            "/materials/uploads",
            headers=headers | {"Idempotency-Key": "live020-synthetic-" + digest},
            json={
                "filename": "合成画面与公开语音验收.mp4",
                "byte_size": len(data),
                "media_type": "video/mp4",
                "purpose": "session_media",
                "sha256": digest,
            },
        )
        initialized.raise_for_status()
        upload_id = initialized.json()["upload_id"]
        if initialized.json()["status"] == "pending":
            sent = client.put(
                f"/materials/uploads/{upload_id}/content", headers=headers, content=data
            )
            sent.raise_for_status()
        finalized = client.post(f"/materials/uploads/{upload_id}/finalize", headers=headers)
        finalized.raise_for_status()
        material_id = finalized.json()["material_id"]
        linked = client.post(
            f"/sessions/{args.session}/materials",
            headers=headers,
            json={"material_id": material_id, "role": "primary"},
        )
        linked.raise_for_status()
        content = client.get(f"/materials/{material_id}/content")
        content.raise_for_status()
        if hashlib.sha256(content.content).hexdigest() != digest:
            raise RuntimeError("download_digest_mismatch")
        result = {
            "session_id": str(args.session),
            "material_id": material_id,
            "sha256": digest,
            "verified": "real API upload, association and download hash",
            "platform_capture": False,
            "asr_submitted": False,
        }
        (RUNTIME / "evidence/browser-material.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))


if __name__ == "__main__":
    main()
