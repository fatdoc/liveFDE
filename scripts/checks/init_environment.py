"""Create a private LIVE-002 environment once; refuses to overwrite credentials."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[2]
workspace = root.parent.parent if root.parent.name == ".worktrees" else root.parent
runtime = workspace / "runtime/live-002"
runtime.mkdir(parents=True, exist_ok=True)
pg, mq = secrets.token_hex(24), secrets.token_hex(24)
path = runtime / "private.env"
with path.open("x") as file:
    path.chmod(0o600)
    file.write(
        f"LIVE_RUNTIME={runtime}\nPG_PASSWORD={pg}\nMQ_PASSWORD={mq}\n"
        f"LIVE_DATABASE_URL=postgresql+psycopg://live002:{pg}@127.0.0.1:15432/live002\n"
        f"LIVE_BROKER_URL=amqp://live002:{mq}@127.0.0.1:5673//\n"
    )
print(path)
