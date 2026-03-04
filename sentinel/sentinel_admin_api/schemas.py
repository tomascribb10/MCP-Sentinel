"""
sentinel_admin_api.schemas
============================
Pydantic v2 request/response schemas for the Admin API.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class CurrentUser(BaseModel):
    id: str
    username: str
    email: str | None
    is_superuser: bool


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class AgentUpdate(BaseModel):
    description: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    id: str
    agent_id: str
    hostname: str
    description: str | None
    status: str
    last_heartbeat: str | None
    labels: dict[str, Any]
    created_at: str


class GroupMemberAdd(BaseModel):
    agent_id: str


# ---------------------------------------------------------------------------
# Host Groups
# ---------------------------------------------------------------------------

class HostGroupCreate(BaseModel):
    name: str
    description: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class HostGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    labels: dict[str, str] | None = None


class HostGroupResponse(BaseModel):
    id: str
    name: str
    description: str | None
    labels: dict[str, Any]
    created_at: str


# ---------------------------------------------------------------------------
# Command Sets & Commands
# ---------------------------------------------------------------------------

class CommandCreate(BaseModel):
    name: str
    binary: str = Field(..., pattern=r"^/.*")
    args_regex: str | None = None
    require_2fa: bool = False
    require_sudo: bool = False
    description: str | None = None
    allowed_paths: list[str] | None = None


class CommandResponse(BaseModel):
    id: str
    command_set_id: str
    name: str
    binary: str
    args_regex: str | None
    require_2fa: bool
    require_sudo: bool
    description: str | None
    allowed_paths: list[str] | None


class CommandSetCreate(BaseModel):
    name: str
    driver: str
    description: str | None = None
    commands: list[CommandCreate] = Field(default_factory=list)


class CommandSetResponse(BaseModel):
    id: str
    name: str
    description: str | None
    driver: str
    commands: list[CommandResponse]
    created_at: str


# ---------------------------------------------------------------------------
# Role Bindings (Policies)
# ---------------------------------------------------------------------------

class RoleBindingCreate(BaseModel):
    principal_id: str
    command_set_id: str
    target_group_id: str
    description: str | None = None
    enabled: bool = True


class RoleBindingUpdate(BaseModel):
    enabled: bool | None = None
    description: str | None = None


class RoleBindingResponse(BaseModel):
    id: str
    principal_id: str
    command_set_id: str
    target_group_id: str
    description: str | None
    enabled: bool
    created_at: str


# ---------------------------------------------------------------------------
# Audit Logs (read-only)
# ---------------------------------------------------------------------------

class AuditLogResponse(BaseModel):
    id: str
    type_uri: str
    event_time: str
    initiator_id: str
    initiator_type: str
    action: str
    target_agent_id: str | None
    target_host: str | None
    driver: str | None
    binary: str | None
    args: str | None
    outcome: str
    reason: str | None
    twofa_required: bool
    twofa_provider: str | None
    message_id: str | None
    request_id: str | None
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    duration_ms: int | None
    created_at: str


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str
    password: str = Field(..., min_length=8)
    email: str | None = None
    is_superuser: bool = False


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8)
    email: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str | None
    is_active: bool
    is_superuser: bool
    created_at: str
