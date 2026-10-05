from kombu import Connection
from sqlalchemy import text


def dependencies_ready(engine, broker_url: str) -> dict[str, str]:
    checks = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "up"
    except Exception:
        checks["database"] = "down"
    try:
        with Connection(broker_url, connect_timeout=3) as connection:
            connection.connect()
        checks["broker"] = "up"
    except Exception:
        checks["broker"] = "down"
    return checks
