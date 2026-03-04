"""
common.models
=============
SQLAlchemy ORM models for MCP-Sentinel.

All models share a single ``Base`` declared here.
Only ``sentinel-conductor`` should instantiate DB sessions.
"""

from common.models.base import Base
from common.models.agent import Agent, AgentStatus
from common.models.group import HostGroup, AgentGroupMembership
from common.models.policy import CommandSet, Command, RoleBinding
from common.models.audit import AuditLog, AuditOutcome
from common.models.auth import User, TwoFAChallenge, ChallengeStatus

__all__ = [
    "Base",
    "Agent", "AgentStatus",
    "HostGroup", "AgentGroupMembership",
    "CommandSet", "Command", "RoleBinding",
    "AuditLog", "AuditOutcome",
    "User", "TwoFAChallenge", "ChallengeStatus",
]
