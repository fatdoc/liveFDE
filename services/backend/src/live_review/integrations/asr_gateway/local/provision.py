"""Operator-only public weight provisioning, never imported by inference."""

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

MODELS = {
    "Fun-ASR-Nano-2512": (
        "FunAudioLLM/Fun-ASR-Nano-2512",
        "272c57b82523ada6fd87095e955f8e29100979ab",
        [
            "model.pt",
            "config.yaml",
            "configuration.json",
            "multilingual.tiktoken",
            "Qwen3-0.6B/config.json",
            "Qwen3-0.6B/generation_config.json",
            "Qwen3-0.6B/merges.txt",
            "Qwen3-0.6B/tokenizer.json",
            "Qwen3-0.6B/tokenizer_config.json",
            "Qwen3-0.6B/vocab.json",
            "example/zh.mp3",
        ],
    ),
    "fsmn-vad": (
        "funasr/fsmn-vad",
        "df20e6b30c653645fa4ff125cacfcabd1020a669",
        ["model.pt", "config.yaml", "configuration.json", "am.mvn"],
    ),
    "campplus": (
        "funasr/campplus",
        "e4b6ede7ce16997aff4ae69fbca1f0175e2afede",
        ["campplus_cn_common.bin", "config.yaml", "configuration.json"],
    ),
    "emotion2vec_plus_base": (
        "emotion2vec/emotion2vec_plus_base",
        "b318240bfe67db81a8c572ecb37ce9c3759b81c9",
        ["model.pt", "config.yaml", "configuration.json", "tokens.txt"],
    ),
    "ct-punc": (
        "funasr/ct-punc",
        "d0e55e2b8722a78b63705ff443d09c4f86e5d750",
        ["model.pt", "config.yaml", "configuration.json", "tokens.json"],
    ),
}


def provision(root: Path, *, resume=False):
    runtime = root.parent
    root.mkdir(parents=True, exist_ok=True)
    for name, (repo, revision, files) in MODELS.items():
        with urllib.request.urlopen(
            f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true", timeout=60
        ) as response:
            metadata = {x["rfilename"]: x for x in json.load(response)["siblings"]}
        manifest = []
        for filename in files:
            info = metadata[filename]
            size = info["size"]
            expected = info.get("lfs", {}).get("sha256")
            target = root / name / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                part = target.with_name(target.name + ".part")
                offset = part.stat().st_size if part.exists() else 0
                if part.exists() and not resume:
                    raise RuntimeError(f"partial_download_requires_operator_review:{part}")
                if offset > size:
                    raise RuntimeError("partial_download_exceeds_declared_size")
                used = sum(p.stat().st_size for p in runtime.rglob("*") if p.is_file())
                remaining = size - offset
                if (
                    used + remaining > 7_000_000_000
                    or shutil.disk_usage(runtime).free - remaining < 8 * 1024**3
                ):
                    raise RuntimeError("runtime_storage_budget_exceeded")
                print(f"download {name}/{filename} {remaining} remaining", flush=True)
                if remaining:
                    request = urllib.request.Request(
                        f"https://huggingface.co/{repo}/resolve/{revision}/{filename}",
                        headers={"Range": f"bytes={offset}-"} if offset else {},
                    )
                    with urllib.request.urlopen(request, timeout=120) as response:
                        if offset and (
                            response.status != 206
                            or not response.headers.get("Content-Range", "").startswith(
                                f"bytes {offset}-"
                            )
                        ):
                            raise RuntimeError("resume_range_not_honored")
                        with part.open("ab" if offset else "wb") as output:
                            written = offset
                            while block := response.read(1024 * 1024):
                                written += len(block)
                                if written > size:
                                    raise RuntimeError("download_exceeds_declared_size")
                                output.write(block)
                if part.stat().st_size != size:
                    raise RuntimeError("download_size_mismatch")
                part.rename(target)
            hasher = hashlib.sha256()
            with target.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    hasher.update(block)
            digest = hasher.hexdigest()
            if target.stat().st_size != size or (expected and expected != digest):
                raise RuntimeError(f"weight_integrity_failed:{target}")
            manifest.append({"file": filename, "bytes": size, "sha256": digest})
        (root / name / "provision-manifest.json").write_text(
            json.dumps({"repo": repo, "revision": revision, "files": manifest}, indent=2)
        )
        print(f"provisioned {name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model_root", type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume reviewed partial files with verified HTTP Range",
    )
    args = parser.parse_args()
    provision(args.model_root.resolve(), resume=args.resume)
