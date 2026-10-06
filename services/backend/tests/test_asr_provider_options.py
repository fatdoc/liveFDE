from types import SimpleNamespace

from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.modules.asr import providers


def test_missing_configuration_keeps_both_choices_visible(monkeypatch):
    def missing(_):
        raise ASRError("model_configuration_missing")

    monkeypatch.setattr(providers, "registry_for", missing)
    rows = providers.provider_options(None)["providers"]
    assert [row["provider"] for row in rows] == ["local", "tencent"]
    assert all(not row["configured"] and not row["network_checked"] for row in rows)
    assert all(row["max_duration_seconds"] is None for row in rows)


def test_limits_follow_media_configuration_and_credentials_without_network(monkeypatch):
    registry = SimpleNamespace(
        loaded=SimpleNamespace(
            public=SimpleNamespace(media=SimpleNamespace(max_duration_seconds=600))
        )
    )
    monkeypatch.setattr(providers, "registry_for", lambda _: registry)

    class NoCalls:
        async def health(self):
            raise AssertionError("configuration list must not call health")

    def construct(_, name):
        if name == "tencent":
            raise ASRError("tencent_credentials_missing")
        return NoCalls()

    monkeypatch.setattr(providers, "create_provider", construct)
    local, cloud = providers.provider_options(None)["providers"]
    assert local["configured"] and local["max_duration_seconds"] == 600
    assert local["network_checked"] is False
    assert not cloud["configured"] and cloud["reason"] == "tencent_credentials_missing"
    assert cloud["max_duration_seconds"] == 156 and cloud["max_audio_bytes"] == 5_000_000
