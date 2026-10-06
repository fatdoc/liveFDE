from fastapi import APIRouter, Request

from live_review.core.auth import CurrentAdmin, MutationAdmin
from live_review.core.model_config.workspace_llm import effective_llm
from live_review.core.provider_config import ProviderConfigError
from live_review.integrations.llm.connection import CheckFailure, check_connection, validate_target
from live_review.modules.llm.schemas import Check, Public, Revision, Update
from live_review.modules.llm.store import Store
from live_review.workers.media_configuration import config_environment

router = APIRouter(prefix="/api/v1/llm/settings", tags=["llm"])


def public(value, settings):
    allowed_http = False
    if value.base_url.startswith("http://"):
        try:
            validate_target(
                settings,
                config_environment(settings, settings.model_config_environment),
                value.base_url,
            )
            allowed_http = True
        except Exception:
            pass
    return value.model_copy(update={"debug_http": allowed_http})


@router.get("", response_model=Public, response_model_exclude_none=False)
def read_settings(request: Request, admin: CurrentAdmin):
    settings = request.app.state.settings
    return public(Store(settings, admin.workspace_id).read(), settings)


@router.put("", response_model=Public)
def save_settings(data: Update, request: Request, admin: MutationAdmin):
    settings = request.app.state.settings
    return public(
        Store(settings, admin.workspace_id).update(data, revision=data.expected_revision), settings
    )


@router.delete("", response_model=Public)
def clear_settings(data: Revision, request: Request, admin: MutationAdmin):
    settings = request.app.state.settings
    return public(
        Store(settings, admin.workspace_id).update(revision=data.expected_revision), settings
    )


@router.post("/check", response_model=Public)
def check_settings(data: Check, request: Request, admin: MutationAdmin):
    settings = request.app.state.settings
    store = Store(settings, admin.workspace_id)
    with store.files.lock("check.lock"):
        value, secret = store.begin(data.expected_revision, data.request_id)
        if secret is None:
            return public(value, settings)
        try:
            loaded = effective_llm(settings, value, secret)
            usage = check_connection(settings, loaded)
        except CheckFailure as error:
            return public(
                store.finish(
                    value,
                    data.request_id,
                    status="unknown" if error.unknown else "check_failed",
                    error=error.code,
                ),
                settings,
            )
        except ProviderConfigError:
            return public(
                store.finish(
                    value, data.request_id, status="check_failed", error="llm_configuration_invalid"
                ),
                settings,
            )
        except Exception:
            return public(
                store.finish(value, data.request_id, status="unknown", error="llm_result_unknown"),
                settings,
            )
        return public(
            store.finish(value, data.request_id, status="verified", usage=usage), settings
        )
