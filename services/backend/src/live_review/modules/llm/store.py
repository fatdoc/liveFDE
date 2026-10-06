"""Revision CAS and durable request tombstones; uncertain calls are never reissued."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from live_review.core.errors import ApiError
from live_review.integrations.llm.connection import CheckFailure, validate_target
from live_review.modules.llm.private_files import PrivateFiles, unavailable
from live_review.modules.llm.schemas import Public, Record, State
from live_review.workers.media_configuration import config_environment


def now():
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, settings, workspace_id):
        self.files = PrivateFiles(settings, workspace_id)
        self.settings = settings

    def _read(self):
        raw = self.files.read("state.json", 2097152)
        try:
            state = State.model_validate_json(raw) if raw else State()
            if state.value.revision != "0":
                UUID(state.value.revision)
            if len(state.requests) > 1024:
                raise ValueError
            for key in state.requests:
                UUID(key)
            return state
        except ValueError:
            raise unavailable() from None

    def _write(self, state):
        self.files.write("state.json", state.model_dump_json().encode())

    def secret(self, value):
        if not value.configured:
            return ""
        try:
            UUID(value.revision)
            raw = self.files.read(value.revision + ".secret", 4096)
            if not raw or any(c < 33 or c > 126 for c in raw):
                raise ValueError
            return raw.decode("ascii")
        except ValueError:
            raise unavailable() from None

    @staticmethod
    def require_revision(value, revision):
        if value.revision != revision:
            raise ApiError(409, "revision_conflict", "配置已变更，请刷新后重试")

    def read(self):
        # A free check lock proves no live request owns a durable checking state.
        try:
            with self.files.lock("check.lock"):
                with self.files.lock():
                    state = self._read()
                    if state.value.status == "checking":
                        state.value.status = "unknown"
                        state.value.last_error = "llm_result_unknown"
                        self._write(state)
                    return state.value
        except ApiError as error:
            if error.code != "llm_settings_busy":
                raise
            with self.files.lock():
                return self._read().value

    def update(self, data=None, *, revision):
        if data is not None:
            try:
                validate_target(
                    self.settings,
                    config_environment(self.settings, self.settings.model_config_environment),
                    data.base_url,
                )
            except CheckFailure as error:
                raise ApiError(422, error.code, "接口地址未通过服务端安全配置") from None
        with self.files.lock():
            state = self._read()
            self.require_revision(state.value, revision)
            old = state.value
            key = (
                ""
                if data is None
                else data.api_key.get_secret_value()
                if data.api_key is not None
                else self.secret(old)
            )
            value = Public(
                revision=uuid4().hex,
                base_url=data.base_url if data else old.base_url,
                model=data.model if data else old.model,
                timeout_seconds=data.timeout_seconds if data else old.timeout_seconds,
                configured=bool(key),
                status="unverified" if key else "not_configured",
                debug_http=(data.base_url if data else old.base_url).startswith("http://"),
            )
            # Immutable secret first, atomic metadata pointer second. Failure cannot mix revisions.
            if key:
                self.files.write(value.revision + ".secret", key.encode())
            state.value = value
            self._write(state)
            # Includes orphans from a failed pre-pointer write. Requests never reference keys.
            for path in self.files.path.glob("*.secret"):
                if value.configured and path.name == value.revision + ".secret":
                    continue
                try:
                    UUID(path.stem)
                    path.unlink(missing_ok=True)
                except (ValueError, OSError):
                    raise unavailable() from None
            return value

    def begin(self, revision, request_id):
        with self.files.lock():
            state = self._read()
            self.require_revision(state.value, revision)
            key = str(request_id)
            if key in state.requests:
                record = state.requests[key]
                if record.revision != revision:
                    raise ApiError(409, "llm_request_reused", "该测试编号已使用，不能再次发送")
                if state.value.status == "checking":
                    state.value = record.result
                    self._write(state)
                return record.result, None
            if state.value.status in {"checking", "unknown"}:
                state.value.status, state.value.last_error = "unknown", "llm_result_unknown"
                self._write(state)
                raise ApiError(409, "llm_result_unknown", "先前测试结果未知，不能再次发送")
            if not state.value.configured:
                raise ApiError(422, "llm_not_configured", "请先保存接口与密钥")
            if len(state.requests) >= 1024:
                raise ApiError(409, "llm_check_limit", "测试记录已达上限，请联系管理员")
            secret = self.secret(state.value)
            state.value.status, state.value.checked_at = "checking", now()
            state.value.last_error, state.value.usage = None, None
            uncertain = state.value.model_copy(
                update={"status": "unknown", "last_error": "llm_result_unknown"}
            )
            state.requests[key] = Record(revision=revision, result=uncertain)
            self._write(state)  # Durable before DNS or any request bytes.
            return state.value, secret

    def finish(self, previous, request_id, *, status, error=None, usage=None):
        result = Public.model_validate(
            previous.model_dump()
            | {"status": status, "last_error": error, "usage": usage, "checked_at": now()}
        )
        with self.files.lock():
            state = self._read()
            state.requests[str(request_id)].result = result
            if state.value.revision == previous.revision:
                state.value = result
            self._write(state)
            self.require_revision(state.value, previous.revision)
            return result
