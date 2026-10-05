"""Guard synthetic execution and lease timing at the configuration boundary."""

import pytest
from pydantic import ValidationError

from live_review.core.config import Settings


@pytest.mark.parametrize("overrides", [
    {"environment": "production", "trusted_origins": ["https://example.test"],
     "job_test_handlers": True},
    {"job_lease_seconds": 0},
    {"job_dispatch_interval_seconds": 0},
    {"job_dispatch_interval_seconds": float("nan")},
    {"job_dispatch_interval_seconds": float("inf")},
])
def test_unsafe_job_configuration_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://unused", broker_url="amqp://unused", **overrides)
