"""Start only the isolated LIVE-006C API or provisioned local inference process."""

import argparse
import json
import os
import stat
import sys

from live006c_runtime import ROOT, RUNTIME, environment


def private_read(name):
    path = RUNTIME / name
    if path.resolve() != path:
        raise RuntimeError("unsafe_preview_path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeError("unsafe_preview_mode")
        content = source.read(16385)
        if len(content) > 16384:
            raise RuntimeError("preview_config_too_large")
        return content


def ui_environment():
    from sqlalchemy.engine import make_url

    base = environment()
    values = dict(line.split("=", 1) for line in private_read("ui.env").splitlines())
    account = json.loads(private_read("ui-account.json"))
    expected = make_url(base["LIVE_DATABASE_URL"]).set(database=account["database"])
    if make_url(values["LIVE_DATABASE_URL"]) != expected:
        raise RuntimeError("foreign_ui_database")
    if not account["database"].startswith("live006c_ui_") or not account["synthetic"]:
        raise RuntimeError("foreign_ui_account")
    for key in ("LIVE_STORAGE_ROOT", "LIVE_BROKER_URL"):
        if values[key] != base[key]:
            raise RuntimeError("foreign_ui_resource")
    if values["LIVE_MODEL_CONFIG_DIR"] != str(RUNTIME / "config"):
        raise RuntimeError("foreign_model_config")
    base.update(values)
    return base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["api", "worker"])
    args = parser.parse_args()
    env = ui_environment()
    if args.mode == "api":
        os.execve(
            sys.executable,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "live_review.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8196",
                "--ws",
                "wsproto",
            ],
            env,
        )
    else:
        from live_review.core.config import Settings
        from live_review.integrations.asr_gateway.factory import registry_for
        from live_review.integrations.asr_gateway.local.config import LocalConfig

        settings = Settings(
            **{
                key.removeprefix("LIVE_").lower(): value
                for key, value in env.items()
                if key.startswith("LIVE_") and key != "LIVE_TRUSTED_ORIGINS"
            }
        )
        route = registry_for(settings).get("asr.local").route
        values = route.model_dump(
            exclude={
                "protocol",
                "enabled",
                "provider",
                "key_env",
                "model",
                "worker_socket",
            }
        )
        values["asr_model"] = route.model
        config = LocalConfig(**values)
        path = RUNTIME / "worker-config.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(config.model_dump_json())
        python = RUNTIME / ".venv/bin/python"
        env["PYTHONPATH"] = str(ROOT / "services/backend/src")
        os.execve(
            python,
            [
                str(python),
                "-m",
                "live_review.workers.local_asr_server",
                "--config-json",
                str(path),
                "--socket",
                route.worker_socket,
                "--storage-root",
                str(RUNTIME / "storage"),
            ],
            env,
        )


if __name__ == "__main__":
    main()
