# MCP-Sentinel — MCP API Reference

Base URL: `http://<host>:8000`
Protocol: [Model Context Protocol](https://modelcontextprotocol.io/) — Streamable HTTP (JSON-RPC 2.0)
Protocol version: `2024-11-05`

---

## Transport

All requests go to a single endpoint:

```
POST /mcp
Content-Type: application/json
```

The body is a JSON-RPC 2.0 request object (or an array of objects for batched calls). The server responds synchronously with a JSON-RPC 2.0 result.

**Request structure**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": { ... }
}
```

**Response structure**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { ... }
}
```

On error:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Missing required parameters: {'target_agent_id'}"
  }
}
```

---

## Lifecycle Methods

### initialize

Called by the client on connection. Returns server capabilities.

**Request**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

**Response**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}, "prompts": {}},
    "serverInfo": {"name": "sentinel-mcp-api", "version": "0.1.0"}
  }
}
```

---

### ping

```json
{"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}}
```

Returns `{"jsonrpc": "2.0", "id": 2, "result": {}}`.

---

### tools/list

Discover available tools and their input schemas.

```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
```

---

## Tools

### execute_command

Execute a whitelisted command on a target agent. Returns immediately — use `get_execution_status` to poll for results.

**Parameters**

| Field             | Type     | Required | Description                                                 |
|-------------------|----------|----------|-------------------------------------------------------------|
| `initiator_id`    | string   | Yes      | Identity of the requesting AI agent (e.g. `llm-agent-claude`) |
| `target_agent_id` | string   | Yes      | `agent_id` of the target sentinel-agent                     |
| `driver`          | string   | Yes      | `posix_bash`, `ansible`, or `openstack_sdk`                 |
| `command`         | string   | Yes      | Absolute path to the binary (e.g. `/usr/bin/uname`)         |
| `args`            | string[] | No       | Command arguments. Default: `[]`                            |
| `timeout_seconds` | integer  | No       | Execution timeout. Default: `30`                            |

**Request**

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "execute_command",
    "arguments": {
      "initiator_id": "llm-agent-claude",
      "target_agent_id": "2b942c2ccb21",
      "driver": "posix_bash",
      "command": "/usr/bin/uname",
      "args": ["-a"]
    }
  }
}
```

**Response — dispatched**

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "content": [{
      "type": "text",
      "text": "Status: dispatched\nRequest ID: 95fe715f-...\nMessage ID: 90e3c157-...\n"
    }],
    "isError": false
  }
}
```

**Response — pending 2FA**

```json
{
  "result": {
    "content": [{
      "type": "text",
      "text": "Status: pending_2fa\nRequest ID: ...\nChallenge ID: ...\n"
    }],
    "isError": false
  }
}
```

**Response — denied**

```json
{
  "result": {
    "content": [{
      "type": "text",
      "text": "Status: denied\nRequest ID: ...\nReason: No active policy grants ...\n"
    }],
    "isError": true
  }
}
```

**Possible status values**

| Status             | Meaning                                                   |
|--------------------|-----------------------------------------------------------|
| `dispatched`       | Command sent to agent. Poll `get_execution_status`        |
| `pending_2fa`      | Waiting for human approval. Keep polling                  |
| `denied`           | RBAC check failed — no policy allows this command         |
| `agent_unreachable`| Scheduler could not reach the target agent                |
| `error`            | Internal error (malformed request, conductor unavailable) |

---

### get_execution_status

Poll the audit log for the result of a previously submitted request. Call this repeatedly (every 2–3 seconds) until `outcome` is `success` or `failure`.

**Parameters**

| Field        | Type   | Required | Description                                     |
|--------------|--------|----------|-------------------------------------------------|
| `request_id` | string | Yes      | The `request_id` returned by `execute_command`  |

**Request**

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "get_execution_status",
    "arguments": {
      "request_id": "95fe715f-71c1-45ba-9dd0-7b2bdb7318af"
    }
  }
}
```

**Response — completed**

```json
{
  "result": {
    "content": [{
      "type": "text",
      "text": "Request ID: 95fe715f-...\nOutcome: success\nAction: execute:/usr/bin/uname\nTarget Agent: 2b942c2ccb21\nEvent Time: 2026-03-01T04:08:50+00:00\nMessage ID: 90e3c157-...\nExit Code: 0\nDuration: 12ms\n\n--- stdout ---\nLinux 2b942c2ccb21 6.1.0 #1 SMP x86_64 GNU/Linux\n"
    }],
    "isError": false
  }
}
```

**Outcome values**

| Outcome   | Meaning                                             |
|-----------|-----------------------------------------------------|
| `pending` | Not yet executed (dispatched but agent hasn't run)  |
| `success` | Command completed (check `exit_code` for errors)    |
| `failure` | Execution failed or exit_code != 0                  |
| `denied`  | RBAC denied before dispatch                         |

**Note:** `outcome: success` means the command ran. Always check `exit_code`: `0` is success, anything else is a command-level failure.

---

### list_agents

Return all registered agents and their liveness status.

**Request**

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "tools/call",
  "params": {
    "name": "list_agents",
    "arguments": {}
  }
}
```

**Response**

```json
{
  "result": {
    "content": [{
      "type": "text",
      "text": "Registered agents:\n\n  [✓] 2b942c2ccb21 (compute01) — status=active\n  [✗] aabbcc112233 (compute02) — status=inactive\n"
    }]
  }
}
```

`[✓]` = alive (sent a heartbeat recently), `[✗]` = stale or offline.

---

### list_allowed_commands

Discover which commands a given AI agent is authorised to run, on which hosts, and whether 2FA is required. Call this before `execute_command`.

**Parameters**

| Field             | Type   | Required | Description                                      |
|-------------------|--------|----------|--------------------------------------------------|
| `initiator_id`    | string | Yes      | Identity of the AI agent                         |
| `target_agent_id` | string | No       | Filter to a specific agent                       |

**Request**

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": {
    "name": "list_allowed_commands",
    "arguments": {
      "initiator_id": "llm-agent-claude"
    }
  }
}
```

**Response**

```
Authorised commands for 'llm-agent-claude':

  [posix_bash] /usr/bin/uname  args: ^(-a|-r|-n)$  — no 2FA
    hosts: 2b942c2ccb21 (compute01, active)

  [posix_bash] /usr/bin/systemctl  args: ^restart (nginx|apache2)$  — ⚠ requires 2FA
    hosts: 2b942c2ccb21 (compute01, active)
```

---

## System Prompt

The server exposes a built-in operational prompt for AI agents via `prompts/get`:

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "method": "prompts/get",
  "params": {"name": "sentinel-operator"}
}
```

This prompt instructs the AI agent on the correct workflow: discover agents → discover allowed commands → confirm with user → execute → poll → report output.

---

## Recommended Workflow

```
1. initialize
2. tools/call → list_agents              # find live hosts
3. tools/call → list_allowed_commands    # what can I run?
4. tools/call → execute_command          # run the command
5. loop:
     tools/call → get_execution_status
     if outcome in (success, failure, denied) → break
     sleep 2s
6. Report stdout / stderr / exit_code to user
```

---

## Health

```
GET /health
```

No authentication required.

```json
{"status": "ok", "service": "sentinel-mcp-api"}
```
