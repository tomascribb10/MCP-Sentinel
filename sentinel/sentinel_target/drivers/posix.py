"""
sentinel_target.drivers.posix
==============================
BashDriver — executes commands via subprocess on POSIX systems.

Stevedore entry point: ``posix_bash``
"""

import re
import subprocess
from datetime import datetime, timezone

from common.exceptions import ArgsRegexMismatch, DriverExecutionFailed, ExecutionTimeout, PathNotAllowed
from common.schemas.payload import ExecutionLimits
from sentinel_target.drivers.base import BaseDriver, ExecutionResult


class BashDriver(BaseDriver):
    """
    Executes whitelisted commands as subprocess calls.

    Security notes:
    - Never uses shell=True (prevents shell injection).
    - Validates args against args_regex before spawning the process.
    - Enforces timeout and output byte limits.
    - Runs as the unprivileged user of the sentinel-target process.
    """

    name = "posix_bash"

    def validate_args(
        self,
        command: str,
        args: list[str],
        args_regex: str | None,
        allowed_paths: list[str] | None = None,
    ) -> None:
        if args_regex is not None:
            args_str = " ".join(args)
            if not re.fullmatch(args_regex, args_str):
                raise ArgsRegexMismatch(
                    f"Arguments {args_str!r} do not match allowed pattern {args_regex!r}"
                )
        self._check_paths(args, allowed_paths)

    def _check_paths(self, args: list[str], allowed_paths: list[str] | None) -> None:
        """Enforce filesystem path prefix restrictions on path-like arguments."""
        if not allowed_paths:
            return
        for arg in args:
            if arg.startswith("/") or arg.startswith("./"):
                if not any(arg.startswith(p) for p in allowed_paths):
                    raise PathNotAllowed(arg, allowed_paths)

    def execute(
        self,
        command: str,
        args: list[str],
        env: dict[str, str],
        limits: ExecutionLimits,
        allowed_paths: list[str] | None = None,
        require_sudo: bool = False,
    ) -> ExecutionResult:
        # Re-enforce path restrictions immediately before spawning (defence in depth)
        self._check_paths(args, allowed_paths)

        # Privilege escalation: prepend sudo when the policy requires it.
        # /usr/bin/sudo is hardcoded to prevent PATH-based injection.
        cmd = ["/usr/bin/sudo", command, *args] if require_sudo else [command, *args]

        started_at = datetime.now(timezone.utc)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=limits.timeout_seconds,
                env=env or None,  # None → inherit parent env
                shell=False,      # NEVER use shell=True
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutionTimeout(
                f"Command {command!r} exceeded timeout of {limits.timeout_seconds}s"
            ) from exc
        except OSError as exc:
            raise DriverExecutionFailed(
                f"Failed to launch {command!r}: {exc}"
            ) from exc

        finished_at = datetime.now(timezone.utc)

        stdout_raw = proc.stdout or b""
        stderr_raw = proc.stderr or b""
        truncated = False

        if len(stdout_raw) > limits.max_stdout_bytes:
            stdout_raw = stdout_raw[: limits.max_stdout_bytes]
            truncated = True
        if len(stderr_raw) > limits.max_stderr_bytes:
            stderr_raw = stderr_raw[: limits.max_stderr_bytes]
            truncated = True

        return ExecutionResult(
            exit_code=proc.returncode,
            stdout=stdout_raw.decode("utf-8", errors="replace"),
            stderr=stderr_raw.decode("utf-8", errors="replace"),
            started_at=started_at,
            finished_at=finished_at,
            truncated=truncated,
        )
