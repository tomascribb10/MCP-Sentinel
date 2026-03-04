"""
Pydantic schemas for the oslo.messaging execution payload.

This is the canonical contract between sentinel-conductor (producer)
and sentinel-agent (consumer).  The agent MUST validate the RSA
signature in ``PayloadSecurity`` before trusting any other field.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ExecutionContext(BaseModel):
    """Metadata about who triggered the execution and 2FA status."""

    initiator_id: str = Field(..., description="Identity of the LLM agent or MCP client.")
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Correlation ID linking this payload to the original MCP request.",
    )
    twofa_verified: bool = Field(
        default=False,
        description="True when the 2FA challenge has been approved for this execution.",
    )
    twofa_provider_used: str | None = Field(
        default=None,
        description="Name of the 2FA provider used (e.g. 'telegram', 'stub').",
    )


class ExecutionLimits(BaseModel):
    """Resource constraints applied by the agent during execution."""

    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    max_stdout_bytes: int = Field(default=1_048_576, ge=0)  # 1 MiB default
    max_stderr_bytes: int = Field(default=65_536, ge=0)     # 64 KiB default


class ExecutionDetail(BaseModel):
    """What to execute and how."""

    driver: str = Field(
        ...,
        description="Stevedore driver name (e.g. 'posix_bash', 'openstack_sdk').",
    )
    command: str = Field(..., description="Full path to the binary to execute.")
    args: list[str] = Field(default_factory=list, description="Argument list.")
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Additional environment variables (merged with driver defaults).",
    )
    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)
    allowed_paths: list[str] | None = Field(
        default=None,
        description="Allowed filesystem path prefixes enforced by the agent driver. "
                    "Included in the signed payload to prevent tampering.",
    )
    require_sudo: bool = Field(
        default=False,
        description="If True, the agent driver prepends /usr/bin/sudo to the command. "
                    "Included in the signed payload to prevent tampering.",
    )

    @field_validator("command")
    @classmethod
    def command_must_be_absolute(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError(f"command must be an absolute path, got: {v!r}")
        return v


class PayloadSecurity(BaseModel):
    """
    RSA-SHA256 signature fields.

    ``signature`` is the base64-encoded signature of the canonical JSON
    representation of ``ExecutionDetail`` + ``ExecutionContext``.
    ``timestamp`` provides replay-attack protection (agents MUST reject
    payloads older than a configurable window, e.g. 60 seconds).
    """

    signature: str = Field(..., description="Base64-encoded RSA-SHA256 signature.")
    timestamp: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp()),
        description="Unix timestamp (UTC) when the payload was signed.",
    )
    key_id: str | None = Field(
        default=None,
        description="Optional key identifier for future key rotation support.",
    )


class ExecutionPayload(BaseModel):
    """
    Top-level oslo.messaging message body.

    Produced by sentinel-conductor, consumed by sentinel-agent.
    The agent validates ``security.signature`` before acting on any field.
    """

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    context: ExecutionContext
    execution: ExecutionDetail
    security: PayloadSecurity

    model_config = {"frozen": True}  # Immutable after construction


class ExecutionResult(BaseModel):
    """
    Result payload returned by sentinel-agent after execution.

    Sent back to sentinel-conductor via a dedicated reply queue or
    oslo.messaging RPC return value.
    """

    message_id: str = Field(..., description="Echoes the ExecutionPayload.message_id.")
    agent_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    started_at: datetime
    finished_at: datetime
    truncated: bool = Field(
        default=False,
        description="True if stdout/stderr was truncated to the configured limits.",
    )
    error: str | None = Field(
        default=None,
        description="Internal error message if the driver itself failed (not the command).",
    )
