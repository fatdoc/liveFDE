"""Shared configuration files must isolate both tenant and service namespaces."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from live_review.core.errors import ApiError
from live_review.modules.llm.private_files import PrivateFiles


def test_service_and_workspace_isolation(tmp_path):
    settings = SimpleNamespace(storage_root=tmp_path / "storage")
    tenant = uuid4()
    files = [PrivateFiles(settings, tenant, namespace=n) for n in ("llm", "vision", "asr")]
    for i, store in enumerate(files):
        with store.lock():
            store.write("state.json", str(i).encode())
    assert [f.read("state.json", 32) for f in files] == [b"0", b"1", b"2"]
    assert PrivateFiles(settings, uuid4()).read("state.json", 32) is None
    assert PrivateFiles(settings, tenant).path == files[0].path
    for namespace in ("../llm", "capture", "", None):
        with pytest.raises(ApiError):
            PrivateFiles(settings, tenant, namespace=namespace)
