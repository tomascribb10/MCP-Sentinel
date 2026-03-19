"""
common.models
=============
SQLAlchemy ORM models for MCP-Sentinel.

All models share a single ``Base`` declared here.
Only ``sentinel-conductor`` should instantiate DB sessions.
"""

from common.models.base import Base
from common.models.gateway import Gateway, GatewayStatus
from common.models.target import Target, TargetStatus, TargetType
from common.models.group import HostGroup, TargetGroupMembership
from common.models.policy import CommandSet, Command, RoleBinding
from common.models.audit import AuditLog, AuditOutcome
from common.models.auth import User, TwoFAChallenge, ChallengeStatus

__all__ = [
    "Base",
    "Gateway", "GatewayStatus",
    "Target", "TargetStatus", "TargetType",
    "HostGroup", "TargetGroupMembership",
    "CommandSet", "Command", "RoleBinding",
    "AuditLog", "AuditOutcome",
    "User", "TwoFAChallenge", "ChallengeStatus",
]
