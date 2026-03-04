"""
common.exceptions
=================
Hierarchy of MCP-Sentinel domain exceptions.

All exceptions inherit from ``SentinelException`` so callers can catch
the entire family with a single ``except SentinelException``.
"""


class SentinelException(Exception):
    """Base class for all MCP-Sentinel exceptions."""
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, **kwargs):
        self.message = message or self.__class__.message
        super().__init__(self.message)


# -----------------------------------------------------------------------
# Policy / RBAC errors
# -----------------------------------------------------------------------

class PolicyDenied(SentinelException):
    """Raised when the RBAC engine denies an execution request."""
    message = "Execution request denied by policy."


class CommandNotAllowed(PolicyDenied):
    """The requested command is not in any applicable Command Set."""
    message = "Command is not permitted by any active Command Set."


class ArgsRegexMismatch(PolicyDenied):
    """The provided arguments do not match the allowed args_regex."""
    message = "Command arguments do not match the allowed pattern."


class PathNotAllowed(PolicyDenied):
    """A filesystem path argument is outside the permitted prefix list."""
    message = "Filesystem path argument is not within any allowed path prefix."

    def __init__(self, path: str, allowed_paths: list[str]):
        super().__init__(
            f"Path {path!r} is not within allowed prefixes: {allowed_paths}"
        )


class AgentNotInGroup(PolicyDenied):
    """The target agent does not belong to the required Host Group."""
    message = "Target agent is not a member of the required Host Group."


# -----------------------------------------------------------------------
# Cryptography / payload errors
# -----------------------------------------------------------------------

class SignatureVerificationFailed(SentinelException):
    """Raised by sentinel-agent when RSA signature validation fails."""
    message = "Payload RSA-SHA256 signature verification failed."


class PayloadTampered(SignatureVerificationFailed):
    """Payload content does not match its signature."""
    message = "Payload has been tampered with; discarding."


# -----------------------------------------------------------------------
# 2FA errors
# -----------------------------------------------------------------------

class TwoFARequired(SentinelException):
    """Execution is blocked until 2FA approval is received."""
    message = "This command requires 2FA approval."


class TwoFAChallengeExpired(SentinelException):
    """The 2FA challenge timed out before the human responded."""
    message = "2FA challenge expired."


class TwoFARejected(SentinelException):
    """The human explicitly rejected the 2FA push."""
    message = "2FA request was rejected by the approver."


# -----------------------------------------------------------------------
# Messaging / transport errors
# -----------------------------------------------------------------------

class AgentNotFound(SentinelException):
    """No registered agent matches the requested target."""
    message = "Target agent not found or not registered."


class AgentUnreachable(SentinelException):
    """The agent is registered but not responding (heartbeat timeout)."""
    message = "Target agent is not reachable (heartbeat timeout)."


class MessageDispatchFailed(SentinelException):
    """oslo.messaging failed to deliver the payload to the agent queue."""
    message = "Failed to dispatch message to agent queue."


# -----------------------------------------------------------------------
# Driver errors
# -----------------------------------------------------------------------

class DriverNotFound(SentinelException):
    """No stevedore driver registered under the requested name."""
    message = "Execution driver not found."


class DriverExecutionFailed(SentinelException):
    """The execution driver returned a non-zero exit code or raised."""
    message = "Execution driver reported a failure."


class ExecutionTimeout(DriverExecutionFailed):
    """Command exceeded the configured timeout."""
    message = "Command execution timed out."
