"""
sentinel_target.drivers.base
============================
Abstract base class for all execution drivers loaded via stevedore.

Stevedore namespace: ``sentinel.target.drivers``

Driver authors must subclass ``BaseDriver`` and implement:
  - ``validate_args(command, args)`` — validate args against policy regex BEFORE execution
  - ``execute(command, args, env, limits)`` — perform the actual execution

Drivers are loaded by ``stevedore.driver.DriverManager`` in the target.
They MUST be registered in setup.cfg under ``sentinel.target.drivers``.
"""

import abc
from dataclasses import dataclass, field
from datetime import datetime

from common.schemas.payload import ExecutionLimits


@dataclass
class ExecutionResult:
    """Return value from BaseDriver.execute()."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime = field(default_factory=datetime.utcnow)
    truncated: bool = False


class BaseDriver(abc.ABC):
    """
    Abstract execution driver.

    Implementations must be stateless — a new instance may be created
    per execution request.  Configuration is passed via oslo.config CONF
    (available globally) and constructor kwargs.
    """

    #: Human-readable name; override in subclasses.
    name: str = "base"

    def __init__(self, **kwargs):
        """
        Drivers may receive keyword arguments from the target configuration.
        Subclasses should call super().__init__(**kwargs).
        """

    @abc.abstractmethod
    def validate_args(
        self,
        command: str,
        args: list[str],
        args_regex: str | None,
        allowed_paths: list[str] | None = None,
    ) -> None:
        """
        Validate ``args`` against the policy-defined ``args_regex`` and
        optionally against a set of permitted filesystem path prefixes.

        Raises:
            common.exceptions.ArgsRegexMismatch: if args don't match the regex.
            common.exceptions.PathNotAllowed:    if a path argument is outside
                                                 the permitted prefix list.

        Note: The RBAC engine validates both before dispatch; the driver
        performs a second check as a defence-in-depth measure.
        """

    @abc.abstractmethod
    def execute(
        self,
        command: str,
        args: list[str],
        env: dict[str, str],
        limits: ExecutionLimits,
        allowed_paths: list[str] | None = None,
        require_sudo: bool = False,
    ) -> ExecutionResult:
        """
        Execute the command and return the result.

        Must respect ``limits.timeout_seconds`` and truncate output to
        ``limits.max_stdout_bytes`` / ``limits.max_stderr_bytes``.
        Re-enforces ``allowed_paths`` immediately before spawning the
        subprocess as a final safety check.

        Raises:
            common.exceptions.DriverExecutionFailed: on unexpected driver error.
            common.exceptions.ExecutionTimeout: if the command exceeds the timeout.
            common.exceptions.PathNotAllowed:    if a path argument is outside
                                                 the permitted prefix list.
        """
