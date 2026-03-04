"""
sentinel_mcp_api.main
======================
FastAPI MCP gateway for sentinel — implements the Model Context Protocol
(MCP) Streamable HTTP transport over a single POST endpoint.

Protocol reference: https://modelcontextprotocol.io/specification

MCP tools exposed
-----------------
execute_command
    Ask an agent to run a command.  The conductor performs RBAC + optional
    2FA before dispatch.  Returns immediately; use ``get_execution_status``
    to poll for the result.

get_execution_status
    Poll the audit log for the outcome of a previously submitted command.

list_agents
    Return the list of known agents from sentinel-scheduler.

MCP transport
-------------
Clients send JSON-RPC 2.0 messages to ``POST /mcp``.
The server responds with a JSON-RPC 2.0 result or error.

For streaming (long-running tools), clients can include
``Accept: text/event-stream`` to receive SSE responses.
This implementation uses a simple request/response pattern for now.
"""

import logging
import os
import secrets
import sys
import uuid
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from oslo_config import cfg
from oslo_log import log as oslo_log
from pydantic import BaseModel, Field

from common.config.auth import auth_group, auth_opts
from common.config.messaging import messaging_group, messaging_opts
from common.messaging.rpc import get_rpc_client
from common.messaging.transport import get_transport

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

SERVICE_NAME = "sentinel-mcp-api"
DEFAULT_PORT = 8000
MCP_PROTOCOL_VERSION = "2024-11-05"

# ---------------------------------------------------------------------------
# Operational system prompt (Fase C)
# ---------------------------------------------------------------------------

_SENTINEL_PROMPT_NAME = "sentinel-operator"
_SENTINEL_PROMPT_DESCRIPTION = (
    "Operational system prompt for AI agents using MCP-Sentinel to manage infrastructure."
)
_SENTINEL_PROMPT_TEXT = """\
You are a system administration assistant operating through MCP-Sentinel, \
a Zero Trust command execution framework.

## Your capabilities

Use the available tools to manage infrastructure:
- `list_agents`: See all registered agents and their liveness status.
- `list_allowed_commands`: Discover which commands you are authorised to run \
and on which hosts. Call this BEFORE attempting any execution.
- `execute_command`: Execute an authorised command on a target agent.
- `get_execution_status`: Poll for the result of a previously submitted command.

## Mandatory workflow

1. Call `list_agents` to identify live hosts.
2. Call `list_allowed_commands` with your `initiator_id` to discover what \
you may run. Never assume — always verify.
3. Before executing, explain to the user exactly what command you will run, \
on which host, and why.
4. Call `execute_command` and immediately poll `get_execution_status` until \
outcome is `success` or `failure` (retry every 2–3 seconds, up to 60 s).
5. Report the full output (`stdout`/`stderr`/`exit_code`) back to the user.

## 2FA-protected commands

Commands with `require_2fa: true` will return `status: pending_2fa`.
- Inform the user that human approval is required.
- Keep polling `get_execution_status` until it resolves.
- Do NOT take dependent actions until the command is approved and completes.

## Operating principles

- Prefer read-only diagnostics (`uname -a`, `df -h`, `systemctl status …`) \
before making changes.
- If `exit_code != 0`, analyse `stderr` before deciding to retry or escalate.
- Never attempt to execute a command not listed by `list_allowed_commands`.
- Be transparent: always show the user the exact binary and arguments \
before executing.
- When in doubt, ask the user for confirmation before proceeding.
"""

# Lazily-initialised RPC clients
_conductor_client = None
_scheduler_client = None


def _get_conductor():
    global _conductor_client
    if _conductor_client is None:
        _conductor_client = get_rpc_client(
            get_transport(CONF),
            topic=CONF.messaging.rpc_topic_conductor,
            timeout=CONF.messaging.rpc_timeout,
        )
    return _conductor_client


def _get_scheduler():
    global _scheduler_client
    if _scheduler_client is None:
        _scheduler_client = get_rpc_client(
            get_transport(CONF),
            topic=CONF.messaging.rpc_topic_scheduler,
        )
    return _scheduler_client


# ---------------------------------------------------------------------------
# MCP JSON-RPC types
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Any = None


def _ok(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str, data: Any = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message, "data": data},
    }


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "execute_command",
        "description": (
            "Execute a whitelisted command on a target agent. "
            "Returns immediately with a request_id. "
            "Use get_execution_status to poll for results."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["initiator_id", "target_agent_id", "driver", "command"],
            "properties": {
                "initiator_id": {
                    "type": "string",
                    "description": "Identity of the requesting AI agent (e.g. 'llm-agent-claude').",
                },
                "target_agent_id": {
                    "type": "string",
                    "description": "agent_id of the target sentinel-agent.",
                },
                "driver": {
                    "type": "string",
                    "description": "Execution driver (e.g. 'posix_bash').",
                    "enum": ["posix_bash", "ansible", "openstack_sdk"],
                },
                "command": {
                    "type": "string",
                    "description": "Absolute path to the binary (e.g. '/usr/bin/systemctl').",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command arguments.",
                    "default": [],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Execution timeout in seconds.",
                    "default": 30,
                },
            },
        },
    },
    {
        "name": "get_execution_status",
        "description": "Poll the audit log for the outcome of a previously submitted execution request.",
        "inputSchema": {
            "type": "object",
            "required": ["request_id"],
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": "The request_id returned by execute_command.",
                },
            },
        },
    },
    {
        "name": "list_agents",
        "description": "Return the list of registered sentinel-agents and their liveness status.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_allowed_commands",
        "description": (
            "List every command this AI agent is authorised to execute, "
            "including the target hosts, driver, args_regex, and whether 2FA is required. "
            "Call this before execute_command to discover what is permitted."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["initiator_id"],
            "properties": {
                "initiator_id": {
                    "type": "string",
                    "description": "Identity of the requesting AI agent (must match the principal_id in the RBAC policy).",
                },
                "target_agent_id": {
                    "type": "string",
                    "description": "Optional — filter results to a specific agent.",
                },
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _handle_execute_command(params: dict, request_id: Any) -> dict:
    required = {"initiator_id", "target_agent_id", "driver", "command"}
    missing = required - params.keys()
    if missing:
        return _err(request_id, -32602, f"Missing required parameters: {missing}")

    rpc_request = {
        "initiator_id": params["initiator_id"],
        "target_agent_id": params["target_agent_id"],
        "driver": params["driver"],
        "command": params["command"],
        "args": params.get("args", []),
        "env": params.get("env", {}),
        "timeout_seconds": params.get("timeout_seconds", 30),
        "request_id": str(uuid.uuid4()),
    }

    try:
        result = _get_conductor().call({}, "request_execution", request=rpc_request)
    except Exception as exc:
        LOG.error("conductor.request_execution failed: %s", exc)
        return _err(request_id, -32603, f"Internal error: {exc}")

    status_val = result.get("status")
    content = [
        {
            "type": "text",
            "text": (
                f"Status: {status_val}\n"
                f"Request ID: {result.get('request_id', rpc_request['request_id'])}\n"
                + (f"Message ID: {result.get('message_id')}\n" if "message_id" in result else "")
                + (f"Challenge ID: {result.get('challenge_id')}\n" if "challenge_id" in result else "")
                + (f"Reason: {result.get('reason')}\n" if "reason" in result else "")
            ),
        }
    ]

    if status_val in ("denied", "error", "agent_unreachable"):
        return _ok(request_id, {"content": content, "isError": True})

    return _ok(request_id, {"content": content})


def _handle_get_execution_status(params: dict, request_id: Any) -> dict:
    req_id = params.get("request_id")
    if not req_id:
        return _err(request_id, -32602, "Missing required parameter: request_id")

    try:
        audit = _get_conductor().call({}, "get_audit_log", request_id=req_id)
    except Exception as exc:
        return _err(request_id, -32603, f"Internal error: {exc}")

    if audit is None:
        return _ok(request_id, {
            "content": [{"type": "text", "text": f"No record found for request_id: {req_id}"}],
            "isError": True,
        })

    outcome = audit["outcome"]
    text = (
        f"Request ID: {audit['request_id']}\n"
        f"Outcome: {outcome}\n"
        f"Action: {audit['action']}\n"
        f"Target Agent: {audit['target_agent_id']}\n"
        f"Event Time: {audit['event_time']}\n"
    )
    if audit.get("reason"):
        text += f"Reason: {audit['reason']}\n"
    if audit.get("message_id"):
        text += f"Message ID: {audit['message_id']}\n"
    if audit.get("exit_code") is not None:
        text += f"Exit Code: {audit['exit_code']}\n"
    if audit.get("duration_ms") is not None:
        text += f"Duration: {audit['duration_ms']}ms\n"
    if audit.get("stdout"):
        text += f"\n--- stdout ---\n{audit['stdout']}"
    if audit.get("stderr"):
        text += f"\n--- stderr ---\n{audit['stderr']}"

    is_error = outcome in ("failure", "denied")
    return _ok(request_id, {"content": [{"type": "text", "text": text}], "isError": is_error})


def _handle_list_allowed_commands(params: dict, request_id: Any) -> dict:
    initiator_id = params.get("initiator_id")
    if not initiator_id:
        return _err(request_id, -32602, "Missing required parameter: initiator_id")

    target_agent_id = params.get("target_agent_id")

    try:
        rows = _get_conductor().call(
            {},
            "list_allowed_commands",
            initiator_id=initiator_id,
            target_agent_id=target_agent_id,
        )
    except Exception as exc:
        return _err(request_id, -32603, f"Internal error: {exc}")

    if not rows:
        text = f"No commands authorised for initiator '{initiator_id}'."
        if target_agent_id:
            text += f" (filtered to agent '{target_agent_id}')"
        return _ok(request_id, {"content": [{"type": "text", "text": text}]})

    lines = [f"Authorised commands for '{initiator_id}':\n"]
    for r in rows:
        agents_str = ", ".join(
            f"{a['agent_id']} ({a['hostname']}, {a['status']})" for a in r["agents"]
        )
        twofa = "⚠ requires 2FA" if r["require_2fa"] else "no 2FA"
        lines.append(
            f"  [{r['driver']}] {r['binary']}"
            + (f"  args: {r['args_regex']}" if r["args_regex"] else "  args: (none)")
            + f"  — {twofa}"
            + f"\n    hosts: {agents_str}"
        )

    return _ok(request_id, {"content": [{"type": "text", "text": "\n".join(lines)}]})


def _handle_list_agents(params: dict, request_id: Any) -> dict:
    try:
        agents = _get_scheduler().call({}, "list_agents")
    except Exception as exc:
        LOG.error("scheduler.list_agents failed: %s", exc)
        # Fall back to conductor DB query
        try:
            agents = _get_conductor().call({}, "list_agents")
        except Exception as exc2:
            return _err(request_id, -32603, f"Internal error: {exc2}")

    lines = ["Registered agents:\n"]
    for a in agents:
        alive = "✓" if a.get("alive", a.get("status") == "active") else "✗"
        lines.append(
            f"  [{alive}] {a['agent_id']} ({a.get('hostname', '?')}) "
            f"— status={a.get('status', '?')}"
        )

    return _ok(request_id, {
        "content": [{"type": "text", "text": "\n".join(lines)}],
    })


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

_AUTH_SCHEME = "Bearer "
_UNAUTHORIZED_RESPONSE = {
    "jsonrpc": "2.0",
    "id": None,
    "error": {"code": -32001, "message": "Unauthorized: valid API key required"},
}


def _check_api_key(authorization: str | None) -> None:
    """
    Validate the Bearer API key sent by the MCP client.

    Raises HTTP 401 if the key is missing or does not match the configured
    ``mcp_api_secret_key``.  Uses a constant-time comparison to prevent
    timing attacks.
    """
    configured_key = CONF.auth.mcp_api_secret_key
    if not authorization or not authorization.startswith(_AUTH_SCHEME):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHORIZED_RESPONSE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    provided_key = authorization[len(_AUTH_SCHEME):]
    if not secrets.compare_digest(provided_key, configured_key):
        LOG.warning("MCP API: rejected request with invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHORIZED_RESPONSE,
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="MCP-Sentinel MCP API",
        description="Model Context Protocol gateway for sentinel.",
        version="0.1.0",
        docs_url="/docs",
    )

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "service": SERVICE_NAME}

    @app.post("/mcp")
    async def mcp_endpoint(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        """
        MCP Streamable HTTP transport endpoint.

        Accepts JSON-RPC 2.0 messages and returns JSON-RPC 2.0 responses.
        Supports both single requests and batched requests (list).

        Authentication: clients must send ``Authorization: Bearer <mcp_api_secret_key>``.
        """
        _check_api_key(authorization)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                _err(None, -32700, "Parse error"),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Batch support
        if isinstance(body, list):
            results = [_dispatch(item) for item in body]
            return JSONResponse(results)

        return JSONResponse(_dispatch(body))

    return app


def _dispatch(body: dict) -> dict:
    """Dispatch a single JSON-RPC request to the appropriate handler."""
    request_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    LOG.info("MCP method=%r id=%s", method, request_id)

    # ------------------------------------------------------------------
    # MCP lifecycle methods
    # ------------------------------------------------------------------
    if method == "initialize":
        return _ok(request_id, {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "prompts": {}},
            "serverInfo": {"name": SERVICE_NAME, "version": "0.1.0"},
        })

    if method == "notifications/initialized":
        # Client notification — no response needed (but return empty for HTTP)
        return _ok(request_id, {})

    if method == "ping":
        return _ok(request_id, {})

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    if method == "tools/list":
        return _ok(request_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if tool_name == "execute_command":
            return _handle_execute_command(tool_args, request_id)
        if tool_name == "get_execution_status":
            return _handle_get_execution_status(tool_args, request_id)
        if tool_name == "list_agents":
            return _handle_list_agents(tool_args, request_id)
        if tool_name == "list_allowed_commands":
            return _handle_list_allowed_commands(tool_args, request_id)

        return _err(request_id, -32601, f"Unknown tool: {tool_name!r}")

    # ------------------------------------------------------------------
    # Prompts (Fase C — operational system prompt for AI agents)
    # ------------------------------------------------------------------
    if method == "prompts/list":
        return _ok(request_id, {"prompts": [
            {
                "name": _SENTINEL_PROMPT_NAME,
                "description": _SENTINEL_PROMPT_DESCRIPTION,
                "arguments": [],
            }
        ]})

    if method == "prompts/get":
        name = params.get("name")
        if name != _SENTINEL_PROMPT_NAME:
            return _err(request_id, -32601, f"Unknown prompt: {name!r}")
        return _ok(request_id, {
            "description": _SENTINEL_PROMPT_DESCRIPTION,
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": _SENTINEL_PROMPT_TEXT,
                    },
                }
            ],
        })

    # Unknown method
    return _err(request_id, -32601, f"Method not found: {method!r}")


# ---------------------------------------------------------------------------
# Service entry point
# ---------------------------------------------------------------------------

def _register_opts() -> None:
    CONF.register_group(messaging_group)
    CONF.register_opts(messaging_opts, group=messaging_group)
    CONF.register_group(auth_group)
    CONF.register_opts(auth_opts, group=auth_group)


def main() -> None:
    _register_opts()
    oslo_log.register_options(CONF)

    conf_file = os.environ.get("SENTINEL_CONF")
    default_files = [conf_file] if conf_file and os.path.exists(conf_file) else []
    CONF(
        args=sys.argv[1:],
        project=SERVICE_NAME,
        default_config_files=default_files,
    )

    oslo_log.setup(CONF, SERVICE_NAME)
    LOG.info("Starting %s on port %d", SERVICE_NAME, DEFAULT_PORT)

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT, log_level="info")


if __name__ == "__main__":
    main()
