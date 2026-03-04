# MCP-Sentinel — Admin API Reference

Base URL: `http://<host>:8001`
Interactive docs: `http://<host>:8001/docs`

---

## Authentication

All endpoints (except `/auth/login` and `/health`) require a JWT Bearer token.

```
Authorization: Bearer <token>
```

Tokens expire after the configured TTL (default: 60 minutes).

---

## Auth

### POST /auth/login

Obtain a JWT token.

**Request body**

```json
{
  "username": "admin",
  "password": "secret"
}
```

**Response**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in_minutes": 60
}
```

---

### GET /auth/me

Return the currently authenticated user.

**Response**

```json
{
  "id": "uuid",
  "username": "admin",
  "email": "admin@sentinel.local",
  "is_superuser": true
}
```

---

## Agents

Agents are auto-registered on first heartbeat. They cannot be created manually.

### GET /agents

List all registered agents.

**Query parameters**

| Parameter | Type   | Description                          |
|-----------|--------|--------------------------------------|
| `status`  | string | Filter by status: `active`, `inactive` |

**Response**

```json
[
  {
    "id": "uuid",
    "agent_id": "2b942c2ccb21",
    "hostname": "compute01",
    "description": null,
    "status": "active",
    "last_heartbeat": "2026-03-01T04:00:00+00:00",
    "labels": {},
    "created_at": "2026-03-01T00:00:00+00:00"
  }
]
```

---

### GET /agents/{agent_id}

Get a single agent by its UUID.

---

### PATCH /agents/{agent_id}

Update an agent's description or labels.

**Request body**

```json
{
  "description": "Primary compute node",
  "labels": {"env": "prod", "region": "us-east"}
}
```

---

### DELETE /agents/{agent_id}

Remove an agent from the system. Returns `204 No Content`.

---

### GET /agents/{agent_id}/groups

List all host groups the agent belongs to.

---

## Host Groups

Groups are used to scope policies. An agent must belong to at least one group to receive commands.

### GET /groups

List all host groups.

### POST /groups

Create a new host group.

**Request body**

```json
{
  "name": "prod-servers",
  "description": "Production compute nodes",
  "labels": {"env": "prod"}
}
```

**Response**: `201 Created` with the created group object.

---

### GET /groups/{group_id}

Get a single group by UUID.

### PATCH /groups/{group_id}

Update a group's name, description, or labels.

**Request body** (all fields optional)

```json
{
  "name": "prod-servers-v2",
  "description": "Updated description",
  "labels": {"env": "prod", "tier": "backend"}
}
```

### DELETE /groups/{group_id}

Delete a group. Returns `204 No Content`.

---

### GET /groups/{group_id}/members

List agents that belong to a group.

### POST /groups/{group_id}/members

Add an agent to a group.

**Request body**

```json
{
  "agent_id": "2b942c2ccb21"
}
```

Returns `204 No Content`.

---

### DELETE /groups/{group_id}/members/{agent_id}

Remove an agent from a group. Returns `204 No Content`.

---

## Command Sets

A Command Set defines a named set of allowed commands for a specific driver. Each command has an optional argument whitelist regex and a 2FA flag.

### GET /command-sets

List all command sets.

**Response**

```json
[
  {
    "id": "uuid",
    "name": "linux_diagnostics",
    "description": "Read-only diagnostic commands",
    "driver": "posix_bash",
    "commands": [...],
    "created_at": "..."
  }
]
```

---

### POST /command-sets

Create a command set. You can optionally include commands inline.

**Request body**

```json
{
  "name": "linux_diagnostics",
  "driver": "posix_bash",
  "description": "Read-only diagnostic commands",
  "commands": [
    {
      "name": "uname",
      "binary": "/usr/bin/uname",
      "args_regex": "^(-a|-r|-n)$",
      "require_2fa": false
    }
  ]
}
```

**Fields**

| Field         | Type    | Required | Description                                      |
|---------------|---------|----------|--------------------------------------------------|
| `name`        | string  | Yes      | Unique name for the command set                  |
| `driver`      | string  | Yes      | `posix_bash`, `ansible`, `openstack_sdk`         |
| `description` | string  | No       |                                                  |
| `commands`    | array   | No       | Commands to add inline (can also add separately) |

**Command object fields** (inside `commands[]`):

| Field           | Type         | Required | Description                                         |
|-----------------|--------------|----------|-----------------------------------------------------|
| `name`          | string       | Yes      | Logical name (e.g. `tail_log`)                      |
| `binary`        | string       | Yes      | Absolute path to the binary                         |
| `args_regex`    | string       | No       | `re.fullmatch` pattern for `" ".join(args)`         |
| `allowed_paths` | string[]     | No       | Filesystem path prefixes. Path-like args must match |
| `require_2fa`   | bool         | No       | Default: `false`                                    |
| `description`   | string       | No       |                                                     |

Returns `201 Created`.

---

### GET /command-sets/{command_set_id}

Get a command set and all its commands.

### DELETE /command-sets/{command_set_id}

Delete a command set. Returns `204 No Content`.

---

### POST /command-sets/{command_set_id}/commands

Add a command to an existing command set.

**Request body**

```json
{
  "name": "restart_nginx",
  "binary": "/usr/bin/systemctl",
  "args_regex": "^restart (nginx|apache2)$",
  "require_2fa": true,
  "description": "Restart web server (requires approval)"
}
```

**Fields**

| Field           | Type     | Required | Description                                                      |
|-----------------|----------|----------|------------------------------------------------------------------|
| `name`          | string   | Yes      | Logical name (e.g. `restart_nginx`)                              |
| `binary`        | string   | Yes      | Absolute path to the binary (must start with `/`)                |
| `args_regex`    | string   | No       | `re.fullmatch` pattern for `" ".join(args)`. Omit to allow any  |
| `allowed_paths` | string[] | No       | Path prefixes; any arg starting with `/` or `./` must match one |
| `require_2fa`   | bool     | No       | Require human approval before execution. Default: `false`        |
| `description`   | string   | No       |                                                                  |

**`allowed_paths` semantics:**
- If `null` or omitted: no path restriction.
- If set (e.g. `["/var/log/"]`): any argument starting with `/` or `./` must start with at least one listed prefix.
- Enforced at two points: the conductor RBAC engine (before signing) and the agent driver (before `subprocess.run`). Included in the RSA-signed payload so it cannot be tampered in transit.

**Example** — command that can only tail files under `/var/log/`:

```json
{
  "name": "tail_log",
  "binary": "/usr/bin/tail",
  "args_regex": "^-n \\d{1,4} .+$",
  "allowed_paths": ["/var/log/"],
  "require_2fa": false
}
```

Returns `201 Created`.

---

### DELETE /command-sets/{command_set_id}/commands/{command_id}

Remove a command from a command set. Returns `204 No Content`.

---

## Policies (Role Bindings)

A policy grants a principal (AI agent identity) access to a command set scoped to a host group.

### GET /policies

List all policies.

**Query parameters**

| Parameter      | Type   | Description                  |
|----------------|--------|------------------------------|
| `principal_id` | string | Filter by initiator identity |

---

### POST /policies

Create a new policy.

**Request body**

```json
{
  "principal_id": "llm-agent-claude",
  "command_set_id": "uuid-of-command-set",
  "target_group_id": "uuid-of-host-group",
  "description": "Claude agent access to diagnostics",
  "enabled": true
}
```

**Fields**

| Field             | Type   | Required | Description                             |
|-------------------|--------|----------|-----------------------------------------|
| `principal_id`    | string | Yes      | Identity of the AI agent or user        |
| `command_set_id`  | string | Yes      | UUID of the command set to grant        |
| `target_group_id` | string | Yes      | UUID of the host group to scope access  |
| `description`     | string | No       |                                         |
| `enabled`         | bool   | No       | Default: `true`                         |

Returns `201 Created`.

---

### GET /policies/{policy_id}

Get a policy by UUID.

### PATCH /policies/{policy_id}

Enable or disable a policy.

**Request body**

```json
{
  "enabled": false
}
```

### DELETE /policies/{policy_id}

Delete a policy. Returns `204 No Content`.

---

## Audit Logs

Read-only. Audit logs are written automatically for every execution request.

### GET /audit-logs

**Query parameters**

| Parameter        | Type    | Default | Description                                      |
|------------------|---------|---------|--------------------------------------------------|
| `initiator_id`   | string  |         | Filter by the AI agent identity                  |
| `target_agent_id`| string  |         | Filter by target agent                           |
| `outcome`        | string  |         | `pending`, `success`, `failure`, `denied`        |
| `limit`          | integer | 50      | Max results (1–500)                              |
| `offset`         | integer | 0       | Pagination offset                                |

**Response**

```json
[
  {
    "id": "uuid",
    "event_time": "2026-03-01T04:08:50+00:00",
    "initiator_id": "llm-agent-claude",
    "action": "execute:/usr/bin/uname",
    "target_agent_id": "2b942c2ccb21",
    "driver": "posix_bash",
    "binary": "/usr/bin/uname",
    "args": "-a",
    "outcome": "success",
    "reason": null,
    "twofa_required": false,
    "twofa_provider": null,
    "message_id": "uuid",
    "request_id": "uuid"
  }
]
```

---

## Users

Superuser access required.

### GET /users

List all users.

### POST /users

Create a new user.

**Request body**

```json
{
  "username": "alice",
  "password": "changeme123",
  "email": "alice@example.com",
  "is_superuser": false
}
```

### PATCH /users/{user_id}

Update a user's password, email, active status, or superuser flag.

### DELETE /users/{user_id}

Delete a user. Returns `204 No Content`.

---

## Health

### GET /health

Returns service status. No authentication required.

```json
{"status": "ok", "service": "sentinel-admin-api"}
```
