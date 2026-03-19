"""
sentinel_conductor.rbac.engine
================================
RBAC evaluation engine — the policy decision point of sentinel-conductor.

Authorization flow
------------------
Given an ExecutionRequest(initiator_id, target_id, driver, command, args):

  1. Resolve the target → get its Host Group memberships.
  2. Find active RoleBindings where:
       principal_id == initiator_id
       AND target_group is one the target belongs to.
  3. For each matching RoleBinding, inspect its CommandSet:
       a. CommandSet.driver must match request.driver.
       b. Find a Command where binary == request.command.
       c. If Command.args_regex is set, validate " ".join(args) against it.
  4. Return the first matching AuthorizationResult.
  5. If no match → raise the most specific PolicyDenied subclass.

Default Deny: any request that doesn't match a policy is rejected.
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.exceptions import (
    TargetNotFound,
    TargetNotInGroup,
    ArgsRegexMismatch,
    CommandNotAllowed,
    PathNotAllowed,
    PolicyDenied,
)
from common.models import (
    Target,
    TargetGroupMembership,
    Command,
    CommandSet,
    RoleBinding,
)
from common.schemas.requests import ExecutionRequest

LOG = logging.getLogger(__name__)


@dataclass
class AuthorizationResult:
    """Returned by RBACEngine.authorize() on success."""

    command: Command
    command_set: CommandSet
    role_binding: RoleBinding
    requires_2fa: bool
    requires_sudo: bool


class RBACEngine:
    """
    Stateless policy evaluator.  Instantiate per-request with a live DB session.

    Example::

        with get_session() as session:
            engine = RBACEngine(session)
            result = engine.authorize(request)
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def authorize(self, request: ExecutionRequest) -> AuthorizationResult:
        """
        Evaluate all applicable policies and return an AuthorizationResult.

        Raises:
            TargetNotFound:     target is not registered.
            TargetNotInGroup:   target has no group memberships.
            PolicyDenied:      no active binding grants this principal access.
            CommandNotAllowed: command not found in any applicable CommandSet.
            ArgsRegexMismatch: command found but args don't match any pattern.
            PathNotAllowed:    a path argument is outside the permitted prefix list.
        """
        args_str = " ".join(request.args)

        # ------------------------------------------------------------------
        # 1. Resolve target
        # ------------------------------------------------------------------
        target: Target | None = self._session.scalar(
            select(Target).where(Target.target_id == request.target_id)
        )
        if target is None:
            raise TargetNotFound(
                f"Target {request.target_id!r} is not registered in the system."
            )

        # ------------------------------------------------------------------
        # 2. Get the target's group memberships
        # ------------------------------------------------------------------
        memberships = self._session.scalars(
            select(TargetGroupMembership).where(
                TargetGroupMembership.target_id == target.id
            )
        ).all()
        target_group_ids = {m.group_id for m in memberships}

        if not target_group_ids:
            raise TargetNotInGroup(
                f"Target {request.target_id!r} does not belong to any Host Group."
            )

        # ------------------------------------------------------------------
        # 3. Find active RoleBindings for this principal + target's groups
        # ------------------------------------------------------------------
        bindings = self._session.scalars(
            select(RoleBinding).where(
                RoleBinding.principal_id == request.initiator_id,
                RoleBinding.enabled.is_(True),
                RoleBinding.target_group_id.in_(target_group_ids),
            )
        ).all()

        if not bindings:
            LOG.warning(
                "RBAC DENY (no binding): principal=%r target=%r",
                request.initiator_id, request.target_id,
            )
            raise PolicyDenied(
                f"No active policy grants principal {request.initiator_id!r} "
                f"access to target {request.target_id!r}."
            )

        # ------------------------------------------------------------------
        # 4. Check each binding's CommandSet for a matching command
        # ------------------------------------------------------------------
        # Track why we're denying, to surface the most helpful error.
        found_driver_match = False
        found_command_match = False

        for binding in bindings:
            command_set: CommandSet | None = self._session.get(
                CommandSet, binding.command_set_id
            )
            if command_set is None:
                continue

            # Driver must match
            if command_set.driver != request.driver:
                continue
            found_driver_match = True

            for cmd in command_set.commands:
                if cmd.binary != request.command:
                    continue
                found_command_match = True

                # Validate args against the whitelist regex
                if cmd.args_regex is not None:
                    if not re.fullmatch(cmd.args_regex, args_str):
                        LOG.debug(
                            "Args %r do not match regex %r for command %r in set %r",
                            args_str, cmd.args_regex, cmd.name, command_set.name,
                        )
                        continue  # Try next command in the set

                # Validate filesystem path prefixes (defence-in-depth)
                if cmd.allowed_paths:
                    for arg in request.args:
                        if arg.startswith("/") or arg.startswith("./"):
                            if not any(arg.startswith(p) for p in cmd.allowed_paths):
                                raise PathNotAllowed(arg, cmd.allowed_paths)

                # ----- AUTHORIZED -----
                LOG.info(
                    "RBAC ALLOW: principal=%r command=%r args=%r target=%r "
                    "(set=%r cmd=%r requires_2fa=%s requires_sudo=%s)",
                    request.initiator_id, request.command, args_str,
                    request.target_id, command_set.name, cmd.name,
                    cmd.require_2fa, cmd.require_sudo,
                )
                return AuthorizationResult(
                    command=cmd,
                    command_set=command_set,
                    role_binding=binding,
                    requires_2fa=cmd.require_2fa,
                    requires_sudo=cmd.require_sudo,
                )

        # ------------------------------------------------------------------
        # 5. Deny with the most descriptive error
        # ------------------------------------------------------------------
        LOG.warning(
            "RBAC DENY: principal=%r command=%r args=%r driver=%r target=%r",
            request.initiator_id, request.command, args_str,
            request.driver, request.target_id,
        )

        if found_command_match:
            # Command was found but args_regex never matched
            raise ArgsRegexMismatch(
                f"Command {request.command!r} is allowed, but arguments {args_str!r} "
                "do not match the permitted pattern."
            )
        if found_driver_match:
            # Driver matched but no such command in any CommandSet
            raise CommandNotAllowed(
                f"Command {request.command!r} is not listed in any CommandSet "
                f"for driver {request.driver!r}."
            )
        # No CommandSet with the requested driver exists for this principal
        raise CommandNotAllowed(
            f"No CommandSet with driver {request.driver!r} is assigned to "
            f"principal {request.initiator_id!r}."
        )
