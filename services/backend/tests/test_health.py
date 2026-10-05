from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from live_review.core.config import get_settings
from live_review.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LIVE_DATABASE_URL", "postgresql+psycopg://u:p@localhost/test")
    monkeypatch.setenv("LIVE_BROKER_URL", "amqp://u:p@localhost//")
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def test_liveness_does_not_probe_dependencies(client):
    with patch("live_review.main.dependencies_ready", side_effect=AssertionError):
        assert client.get("/health/live").json() == {"status": "alive"}


@pytest.mark.parametrize("failed", ["database", "broker"])
def test_readiness_failure_is_503_without_secrets(client, failed):
    checks = {"database": "up", "broker": "up", failed: "down"}
    with patch("live_review.main.dependencies_ready", return_value=checks):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": checks}
