"""Workspace-private vision preferences; default credentials stay in the LLM store."""

from uuid import UUID, uuid4

from live_review.core.errors import ApiError
from live_review.integrations.llm.connection import CheckFailure, validate_target
from live_review.modules.llm.private_files import PrivateFiles, unavailable
from live_review.modules.llm.store import Store as TextStore
from live_review.modules.llm.vision_schemas import Public, Stored
from live_review.workers.media_configuration import config_environment


class Store:
    def __init__(self, settings, workspace_id):
        self.settings, self.workspace_id = settings, workspace_id
        self.files = PrivateFiles(settings, workspace_id, namespace="vision")

    def _read(self):
        raw = self.files.read("state.json", 65536)
        try:
            value = Stored.model_validate_json(raw) if raw else Stored()
            if value.revision != "0":
                UUID(value.revision)
            return value
        except ValueError:
            raise unavailable() from None

    def secret(self, value):
        if not value.independent_key_configured:
            return ""
        try:
            UUID(value.revision)
            raw = self.files.read(value.revision + ".secret", 4096)
            if not raw or any(c < 33 or c > 126 for c in raw):
                raise ValueError
            return raw.decode("ascii")
        except ValueError:
            raise unavailable() from None

    def public(self, value):
        result = Public(**value.model_dump())
        if value.mode == "default":
            text = TextStore(self.settings, self.workspace_id)
            # Read metadata only, without changing abandoned-check state or reading its key.
            with text.files.lock():
                default = text._read().value
            result.effective_base_url = default.base_url
            result.timeout_seconds = default.timeout_seconds
            result.default_revision = default.revision
            result.default_status = default.status
            result.configured = bool(default.configured and value.model and default.base_url)
        else:
            result.effective_base_url = value.base_url
            result.configured = bool(value.independent_key_configured and value.model)
        result.debug_http = result.effective_base_url.startswith("http://")
        return result

    def read(self):
        with self.files.lock():
            return self.public(self._read())

    def update(self, data=None, *, revision):
        if data is not None and data.mode == "independent":
            try:
                validate_target(
                    self.settings,
                    config_environment(self.settings, self.settings.model_config_environment),
                    data.base_url,
                )
            except CheckFailure as error:
                raise ApiError(422, error.code, "接口地址未通过服务端安全配置") from None
        with self.files.lock():
            old = self._read()
            TextStore.require_revision(old, revision)
            key = (
                ""
                if data is None
                else data.api_key.get_secret_value()
                if data.api_key is not None
                else self.secret(old)
            )
            value = old.model_copy(update={"revision": uuid4().hex})
            value.enabled = data.enabled if data else False
            value.independent_key_configured = bool(key)
            if data:
                value.mode, value.model = data.mode, data.model
                if data.mode == "independent":
                    value.base_url, value.timeout_seconds = data.base_url, data.timeout_seconds
            if key:
                self.files.write(value.revision + ".secret", key.encode())
            self.files.write("state.json", value.model_dump_json().encode())
            for path in self.files.path.glob("*.secret"):
                if key and path.name == value.revision + ".secret":
                    continue
                try:
                    UUID(path.stem)
                    path.unlink(missing_ok=True)
                except (ValueError, OSError):
                    raise unavailable() from None
            return self.public(value)
