"""
Pydantic schemas for API-level request/response objects.

These are used by sentinel-mcp-api and sentinel-admin-api endpoints,
NOT for the internal oslo.messaging payload (see payload.py for that).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ExecutionRequest(BaseModel):
    """
    Inbound execution request from an MCP client or Admin API.

    This is the *untrusted* input that sentinel-conductor validates
    against RBAC policies before producing a signed ExecutionPayload.
    """

    initiator_id: str = Field(..., description="Identity of the requesting MCP agent.")
    target_agent_id: str = Field(..., description="agent_id of the target sentinel-agent.")
    driver: str = Field(..., description="Execution driver name.")
    command: str = Field(..., description="Absolute path to binary.")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class AgentHeartbeat(BaseModel):
    """
    Heartbeat message sent by sentinel-agent to sentinel-scheduler.

    Published periodically (every N seconds) to the scheduler's RPC topic.
    """

    agent_id: str
    hostname: str
    status: str = "active"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    enabled_drivers: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
