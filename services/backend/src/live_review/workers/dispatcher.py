"""Bootstrap preflight only. No outbox polling until the jobs module exists."""

import argparse
import json

from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.core.health import dependencies_ready


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, action="store_true")
    parser.parse_args()
    settings = get_settings()
    engine = build_engine(settings)
    try:
        checks = dependencies_ready(engine, settings.broker_url.get_secret_value())
        print(json.dumps({"mode": "preflight_only", "checks": checks}))
        return 0 if all(v == "up" for v in checks.values()) else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
