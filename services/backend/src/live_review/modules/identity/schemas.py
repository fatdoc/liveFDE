"""Public identity contracts contain no credential or internal session fields."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class UserView(BaseModel):
    id: UUID
    workspace_id: UUID
    display_name: str
    role: Literal["admin"]


class LoginResponse(BaseModel):
    user: UserView
    csrf_token: str
