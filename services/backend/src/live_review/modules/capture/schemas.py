from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.providers import canonical_reference


class ProbeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["douyin", "wechat"]
    source_ref: str = Field(max_length=200)

    @model_validator(mode="after")
    def canonical(self):
        try:
            self.source_ref = canonical_reference(self.platform, self.source_ref)
        except CaptureError:
            raise ValueError(
                "Use a PC room URL or phone_cast; signed stream URLs are forbidden"
            ) from None
        return self


class StartInput(ProbeInput):
    session_id: UUID
