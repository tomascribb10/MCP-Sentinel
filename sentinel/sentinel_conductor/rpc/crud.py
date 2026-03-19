"""
sentinel_conductor.rpc.crud
============================
ConductorCRUDMixin — CRUD RPC methods for sentinel-conductor.

Mixed into ``ConductorRPCEndpoint``.  Keeps the execution-flow logic
in ``server.py`` separate from the data-management methods here.

All methods follow the same pattern:
  - Receive plain dicts over oslo.messaging.
  - Open a DB session via ``self._session_factory()``.
  - Perform the DB operation.
  - Return plain dicts (serialisable over oslo.messaging).

The Admin API calls these methods; it never touches the DB directly.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from common.models import (
    Target, TargetGroupMembership, TargetStatus, TargetType,
    Gateway, GatewayStatus,
    AuditLog,
    Command, CommandSet,
    HostGroup,
    RoleBinding,
    TwoFAChallenge,
    User,
)

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _target_to_dict(t: Target) -> dict:
    return {
        "id": t.id,
        "target_id": t.target_id,
        "hostname": t.hostname,
        "description": t.description,
        "target_type": t.target_type.value,
        "gateway_id": t.gateway_id,
        "status": t.status.value,
        "last_heartbeat": t.last_heartbeat.isoformat() if t.last_heartbeat else None,
        "labels": json.loads(t.labels_json or "{}"),
        "created_at": t.created_at.isoformat(),
    }


def _gateway_to_dict(g: Gateway) -> dict:
    return {
        "id": g.id,
        "gateway_id": g.gateway_id,
        "hostname": g.hostname,
        "description": g.description,
        "status": g.status.value,
        "last_heartbeat": g.last_heartbeat.isoformat() if g.last_heartbeat else None,
        "labels": json.loads(g.labels_json or "{}"),
        "created_at": g.created_at.isoformat(),
    }


def _group_to_dict(g: HostGroup) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "labels": json.loads(g.labels_json or "{}"),
        "created_at": g.created_at.isoformat(),
    }


def _command_set_to_dict(cs: CommandSet, include_commands: bool = True) -> dict:
    d = {
        "id": cs.id,
        "name": cs.name,
        "description": cs.description,
        "driver": cs.driver,
        "created_at": cs.created_at.isoformat(),
    }
    if include_commands:
        d["commands"] = [_command_to_dict(c) for c in cs.commands]
    return d


def _command_to_dict(c: Command) -> dict:
    return {
        "id": c.id,
        "command_set_id": c.command_set_id,
        "name": c.name,
        "binary": c.binary,
        "args_regex": c.args_regex,
        "require_2fa": c.require_2fa,
        "require_sudo": c.require_sudo,
        "description": c.description,
        "allowed_paths": c.allowed_paths,
    }


def _role_binding_to_dict(rb: RoleBinding) -> dict:
    return {
        "id": rb.id,
        "principal_id": rb.principal_id,
        "command_set_id": rb.command_set_id,
        "target_group_id": rb.target_group_id,
        "description": rb.description,
        "enabled": rb.enabled,
        "created_at": rb.created_at.isoformat(),
    }


def _audit_log_to_dict(a: AuditLog) -> dict:
    return {
        "id": a.id,
        "type_uri": a.type_uri,
        "event_time": a.event_time.isoformat(),
        "initiator_id": a.initiator_id,
        "initiator_type": a.initiator_type,
        "action": a.action,
        "target_id": a.target_id,
        "target_host": a.target_host,
        "driver": a.driver,
        "binary": a.binary,
        "args": a.args,
        "outcome": a.outcome.value,
        "reason": a.reason,
        "twofa_required": a.twofa_required,
        "twofa_provider": a.twofa_provider,
        "message_id": a.message_id,
        "request_id": a.request_id,
        "stdout": a.stdout,
        "stderr": a.stderr,
        "exit_code": a.exit_code,
        "duration_ms": a.duration_ms,
        "created_at": a.created_at.isoformat(),
    }


def _user_to_dict(u: User, include_password: bool = False) -> dict:
    d = {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "is_active": u.is_active,
        "is_superuser": u.is_superuser,
        "created_at": u.created_at.isoformat(),
    }
    if include_password:
        d["hashed_password"] = u.hashed_password
    return d


# ---------------------------------------------------------------------------
# Mixin class
# ---------------------------------------------------------------------------

class ConductorCRUDMixin:
    """
    CRUD RPC methods mixed into ConductorRPCEndpoint.

    Expects ``self._session_factory`` to be available (set by the concrete class).
    """

    # ==================================================================
    # TARGETS
    # ==================================================================

    def list_targets(self, ctxt: dict, status_filter: str | None = None) -> list[dict]:
        with self._session_factory() as session:
            q = select(Target)
            if status_filter:
                try:
                    q = q.where(Target.status == TargetStatus(status_filter))
                except ValueError:
                    pass
            targets = session.scalars(q.order_by(Target.created_at.desc())).all()
            return [_target_to_dict(t) for t in targets]

    def get_target(self, ctxt: dict, target_id: str) -> dict | None:
        with self._session_factory() as session:
            target = session.scalar(
                select(Target).where(
                    (Target.target_id == target_id) | (Target.id == target_id)
                )
            )
            return _target_to_dict(target) if target else None

    def update_target(self, ctxt: dict, target_id: str, data: dict) -> dict | None:
        with self._session_factory() as session:
            target = session.scalar(
                select(Target).where(
                    (Target.target_id == target_id) | (Target.id == target_id)
                )
            )
            if target is None:
                return None
            if "description" in data:
                target.description = data["description"]
            if "labels" in data:
                target.labels_json = json.dumps(data["labels"])
            return _target_to_dict(target)

    def delete_target(self, ctxt: dict, target_id: str) -> bool:
        with self._session_factory() as session:
            target = session.scalar(
                select(Target).where(
                    (Target.target_id == target_id) | (Target.id == target_id)
                )
            )
            if target is None:
                return False
            session.delete(target)
            return True

    def update_target_status(
        self,
        ctxt: dict,
        target_id: str,
        hostname: str,
        status: str,
        last_heartbeat: str,
        enabled_drivers: list,
        labels: dict,
        target_type: str = "direct",
        gateway_id: str | None = None,
    ) -> None:
        """Upsert target status after a heartbeat. Called by sentinel-scheduler."""
        with self._session_factory() as session:
            target = session.scalar(
                select(Target).where(Target.target_id == target_id)
            )
            if target is None:
                target = Target(
                    target_id=target_id,
                    hostname=hostname,
                    target_type=TargetType(target_type) if target_type else TargetType.DIRECT,
                    gateway_id=gateway_id,
                    labels_json=json.dumps(labels or {}),
                )
                session.add(target)
                LOG.info("Auto-registered new target: target_id=%r hostname=%r", target_id, hostname)
            target.hostname = hostname
            target.status = TargetStatus(status) if status in ("active", "inactive", "unknown") else TargetStatus.UNKNOWN
            target.last_heartbeat = datetime.fromisoformat(last_heartbeat)
            target.labels_json = json.dumps(labels or {})
            if target_type:
                try:
                    target.target_type = TargetType(target_type)
                except ValueError:
                    pass
            if gateway_id is not None:
                target.gateway_id = gateway_id

    # ==================================================================
    # GATEWAYS
    # ==================================================================

    def list_gateways(self, ctxt: dict, status_filter: str | None = None) -> list[dict]:
        with self._session_factory() as session:
            q = select(Gateway)
            if status_filter:
                try:
                    q = q.where(Gateway.status == GatewayStatus(status_filter))
                except ValueError:
                    pass
            gateways = session.scalars(q.order_by(Gateway.created_at.desc())).all()
            return [_gateway_to_dict(g) for g in gateways]

    def get_gateway(self, ctxt: dict, gateway_id: str) -> dict | None:
        with self._session_factory() as session:
            gw = session.scalar(
                select(Gateway).where(
                    (Gateway.gateway_id == gateway_id) | (Gateway.id == gateway_id)
                )
            )
            return _gateway_to_dict(gw) if gw else None

    def update_gateway_status(
        self,
        ctxt: dict,
        gateway_id: str,
        hostname: str,
        status: str,
        last_heartbeat: str,
        managed_target_ids: list,
        labels: dict,
    ) -> None:
        """Upsert gateway status after a heartbeat. Called by sentinel-scheduler."""
        with self._session_factory() as session:
            gw = session.scalar(
                select(Gateway).where(Gateway.gateway_id == gateway_id)
            )
            if gw is None:
                gw = Gateway(
                    gateway_id=gateway_id,
                    hostname=hostname,
                    labels_json=json.dumps(labels or {}),
                )
                session.add(gw)
                LOG.info("Auto-registered new gateway: gateway_id=%r hostname=%r", gateway_id, hostname)
            gw.hostname = hostname
            gw.status = GatewayStatus(status) if status in ("active", "inactive", "unknown") else GatewayStatus.UNKNOWN
            gw.last_heartbeat = datetime.fromisoformat(last_heartbeat)
            gw.labels_json = json.dumps(labels or {})

    # ==================================================================
    # HOST GROUPS
    # ==================================================================

    def list_host_groups(self, ctxt: dict) -> list[dict]:
        with self._session_factory() as session:
            groups = session.scalars(
                select(HostGroup).order_by(HostGroup.name)
            ).all()
            return [_group_to_dict(g) for g in groups]

    def get_host_group(self, ctxt: dict, group_id: str) -> dict | None:
        with self._session_factory() as session:
            group = session.get(HostGroup, group_id)
            return _group_to_dict(group) if group else None

    def create_host_group(self, ctxt: dict, data: dict) -> dict:
        with self._session_factory() as session:
            group = HostGroup(
                name=data["name"],
                description=data.get("description"),
                labels_json=json.dumps(data.get("labels", {})),
            )
            session.add(group)
            session.flush()
            return _group_to_dict(group)

    def update_host_group(self, ctxt: dict, group_id: str, data: dict) -> dict | None:
        with self._session_factory() as session:
            group = session.get(HostGroup, group_id)
            if group is None:
                return None
            if "name" in data:
                group.name = data["name"]
            if "description" in data:
                group.description = data["description"]
            if "labels" in data:
                group.labels_json = json.dumps(data["labels"])
            return _group_to_dict(group)

    def delete_host_group(self, ctxt: dict, group_id: str) -> bool:
        with self._session_factory() as session:
            group = session.get(HostGroup, group_id)
            if group is None:
                return False
            session.delete(group)
            return True

    def add_target_to_group(self, ctxt: dict, group_id: str, target_id: str) -> bool:
        with self._session_factory() as session:
            group = session.get(HostGroup, group_id)
            target = session.scalar(
                select(Target).where(
                    (Target.target_id == target_id) | (Target.id == target_id)
                )
            )
            if group is None or target is None:
                return False
            # Idempotent: check if already a member
            existing = session.scalar(
                select(TargetGroupMembership).where(
                    TargetGroupMembership.group_id == group_id,
                    TargetGroupMembership.target_id == target.id,
                )
            )
            if existing:
                return True
            session.add(TargetGroupMembership(target_id=target.id, group_id=group_id))
            return True

    def remove_target_from_group(self, ctxt: dict, group_id: str, target_id: str) -> bool:
        with self._session_factory() as session:
            target = session.scalar(
                select(Target).where(
                    (Target.target_id == target_id) | (Target.id == target_id)
                )
            )
            if target is None:
                return False
            membership = session.scalar(
                select(TargetGroupMembership).where(
                    TargetGroupMembership.group_id == group_id,
                    TargetGroupMembership.target_id == target.id,
                )
            )
            if membership is None:
                return False
            session.delete(membership)
            return True

    def list_group_members(self, ctxt: dict, group_id: str) -> list[dict]:
        with self._session_factory() as session:
            memberships = session.scalars(
                select(TargetGroupMembership).where(
                    TargetGroupMembership.group_id == group_id
                )
            ).all()
            result = []
            for m in memberships:
                target = session.get(Target, m.target_id)
                if target:
                    result.append(_target_to_dict(target))
            return result

    # ==================================================================
    # ALLOWED COMMANDS QUERY  (used by MCP list_allowed_commands tool)
    # ==================================================================

    def list_allowed_commands(
        self,
        ctxt: dict,
        initiator_id: str,
        target_id: str | None = None,
    ) -> list[dict]:
        """
        Return every command the given initiator is authorised to execute.

        For each active RoleBinding matching principal_id, resolves the
        CommandSet → Commands and HostGroup → member Targets.
        Optionally filtered to a single target (by target_id or id).
        """
        with self._session_factory() as session:
            bindings = session.scalars(
                select(RoleBinding).where(
                    RoleBinding.principal_id == initiator_id,
                    RoleBinding.enabled.is_(True),
                )
            ).all()

            rows = []
            for binding in bindings:
                cs = session.get(CommandSet, binding.command_set_id)
                if cs is None:
                    continue

                memberships = session.scalars(
                    select(TargetGroupMembership).where(
                        TargetGroupMembership.group_id == binding.target_group_id
                    )
                ).all()

                targets = []
                for m in memberships:
                    t = session.get(Target, m.target_id)
                    if t is None:
                        continue
                    if target_id and t.target_id != target_id and t.id != target_id:
                        continue
                    targets.append({
                        "target_id": t.target_id,
                        "hostname": t.hostname,
                        "status": t.status.value,
                    })

                if not targets:
                    continue

                for cmd in cs.commands:
                    rows.append({
                        "command_name": cmd.name,
                        "binary": cmd.binary,
                        "args_regex": cmd.args_regex,
                        "require_2fa": cmd.require_2fa,
                        "require_sudo": cmd.require_sudo,
                        "allowed_paths": cmd.allowed_paths,
                        "driver": cs.driver,
                        "command_set": cs.name,
                        "targets": targets,
                    })

            return rows

    # ==================================================================
    # COMMAND SETS
    # ==================================================================

    def list_command_sets(self, ctxt: dict) -> list[dict]:
        with self._session_factory() as session:
            sets = session.scalars(
                select(CommandSet).order_by(CommandSet.name)
            ).all()
            return [_command_set_to_dict(cs) for cs in sets]

    def get_command_set(self, ctxt: dict, command_set_id: str) -> dict | None:
        with self._session_factory() as session:
            cs = session.get(CommandSet, command_set_id)
            return _command_set_to_dict(cs) if cs else None

    def create_command_set(self, ctxt: dict, data: dict) -> dict:
        with self._session_factory() as session:
            cs = CommandSet(
                name=data["name"],
                driver=data["driver"],
                description=data.get("description"),
            )
            session.add(cs)
            session.flush()
            for cmd_data in data.get("commands", []):
                cmd = Command(
                    command_set_id=cs.id,
                    name=cmd_data["name"],
                    binary=cmd_data["binary"],
                    args_regex=cmd_data.get("args_regex"),
                    require_2fa=cmd_data.get("require_2fa", False),
                    require_sudo=cmd_data.get("require_sudo", False),
                    description=cmd_data.get("description"),
                    allowed_paths=cmd_data.get("allowed_paths"),
                )
                session.add(cmd)
            session.flush()
            # Reload to get commands populated
            session.refresh(cs)
            return _command_set_to_dict(cs)

    def delete_command_set(self, ctxt: dict, command_set_id: str) -> bool:
        with self._session_factory() as session:
            cs = session.get(CommandSet, command_set_id)
            if cs is None:
                return False
            session.delete(cs)
            return True

    def create_command(self, ctxt: dict, command_set_id: str, data: dict) -> dict | None:
        with self._session_factory() as session:
            cs = session.get(CommandSet, command_set_id)
            if cs is None:
                return None
            cmd = Command(
                command_set_id=command_set_id,
                name=data["name"],
                binary=data["binary"],
                args_regex=data.get("args_regex"),
                require_2fa=data.get("require_2fa", False),
                require_sudo=data.get("require_sudo", False),
                description=data.get("description"),
                allowed_paths=data.get("allowed_paths"),
            )
            session.add(cmd)
            session.flush()
            return _command_to_dict(cmd)

    def delete_command(self, ctxt: dict, command_id: str) -> bool:
        with self._session_factory() as session:
            cmd = session.get(Command, command_id)
            if cmd is None:
                return False
            session.delete(cmd)
            return True

    # ==================================================================
    # ROLE BINDINGS (POLICIES)
    # ==================================================================

    def list_role_bindings(
        self, ctxt: dict, principal_id: str | None = None
    ) -> list[dict]:
        with self._session_factory() as session:
            q = select(RoleBinding)
            if principal_id:
                q = q.where(RoleBinding.principal_id == principal_id)
            bindings = session.scalars(q.order_by(RoleBinding.created_at.desc())).all()
            return [_role_binding_to_dict(rb) for rb in bindings]

    def get_role_binding(self, ctxt: dict, binding_id: str) -> dict | None:
        with self._session_factory() as session:
            rb = session.get(RoleBinding, binding_id)
            return _role_binding_to_dict(rb) if rb else None

    def create_role_binding(self, ctxt: dict, data: dict) -> dict:
        with self._session_factory() as session:
            rb = RoleBinding(
                principal_id=data["principal_id"],
                command_set_id=data["command_set_id"],
                target_group_id=data["target_group_id"],
                description=data.get("description"),
                enabled=data.get("enabled", True),
            )
            session.add(rb)
            session.flush()
            return _role_binding_to_dict(rb)

    def update_role_binding(
        self, ctxt: dict, binding_id: str, data: dict
    ) -> dict | None:
        with self._session_factory() as session:
            rb = session.get(RoleBinding, binding_id)
            if rb is None:
                return None
            if "enabled" in data:
                rb.enabled = data["enabled"]
            if "description" in data:
                rb.description = data["description"]
            return _role_binding_to_dict(rb)

    def delete_role_binding(self, ctxt: dict, binding_id: str) -> bool:
        with self._session_factory() as session:
            rb = session.get(RoleBinding, binding_id)
            if rb is None:
                return False
            session.delete(rb)
            return True

    # ==================================================================
    # AUDIT LOGS (read-only)
    # ==================================================================

    def list_audit_logs(
        self,
        ctxt: dict,
        initiator_id: str | None = None,
        target_id: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        from common.models import AuditOutcome
        with self._session_factory() as session:
            q = select(AuditLog)
            if initiator_id:
                q = q.where(AuditLog.initiator_id == initiator_id)
            if target_id:
                q = q.where(AuditLog.target_id == target_id)
            if outcome:
                try:
                    q = q.where(AuditLog.outcome == AuditOutcome(outcome))
                except ValueError:
                    pass
            q = q.order_by(AuditLog.event_time.desc()).offset(offset).limit(limit)
            logs = session.scalars(q).all()
            return [_audit_log_to_dict(a) for a in logs]

    # ==================================================================
    # USERS (Admin API local auth)
    # ==================================================================

    def get_user_by_username(self, ctxt: dict, username: str) -> dict | None:
        """Returns user dict INCLUDING hashed_password (for login verification)."""
        with self._session_factory() as session:
            user = session.scalar(select(User).where(User.username == username))
            return _user_to_dict(user, include_password=True) if user else None

    def list_users(self, ctxt: dict) -> list[dict]:
        with self._session_factory() as session:
            users = session.scalars(select(User).order_by(User.username)).all()
            return [_user_to_dict(u) for u in users]

    def create_user(self, ctxt: dict, data: dict) -> dict:
        with self._session_factory() as session:
            user = User(
                username=data["username"],
                email=data.get("email"),
                hashed_password=data["hashed_password"],
                is_active=data.get("is_active", True),
                is_superuser=data.get("is_superuser", False),
            )
            session.add(user)
            session.flush()
            return _user_to_dict(user)

    def update_user(self, ctxt: dict, user_id: str, data: dict) -> dict | None:
        with self._session_factory() as session:
            user = session.get(User, user_id)
            if user is None:
                return None
            if "hashed_password" in data:
                user.hashed_password = data["hashed_password"]
            if "email" in data:
                user.email = data["email"]
            if "is_active" in data:
                user.is_active = data["is_active"]
            if "is_superuser" in data:
                user.is_superuser = data["is_superuser"]
            return _user_to_dict(user)

    def delete_user(self, ctxt: dict, user_id: str) -> bool:
        with self._session_factory() as session:
            user = session.get(User, user_id)
            if user is None:
                return False
            session.delete(user)
            return True
