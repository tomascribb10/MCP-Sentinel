# MCP-Sentinel — CLI Specification

**Status:** Draft  
**Version:** 1.0.0-draft  
**Target:** sentinel-cli  
**Audience:** CLI developers, code-generation agents, security reviewers

Normative terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** define implementation requirements.

---

## 1. Purpose

This specification defines the `sentinel` CLI — the command-line interface for human administrators to operate MCP-Sentinel.

> **The CLI is a thin client over the Admin API. It does not implement business logic.**

---

## 2. Architecture

### 2.1 Framework

The CLI is built on **cliff** (OpenStack's CLI framework):

- **`App`** — top-level application class
- **`CommandManager`** — loads commands from entry points under the `sentinel` namespace
- **`Command`** — base class for single-action commands
- **`Lister`** — base class for tabular list commands
- **`ShowOne`** — base class for single-record display

### 2.2 Request Flow

```text
User
  |
  v
sentinel <command> [options]
  |
  v
SentinelApp (cliff App)
  |-- CommandManager("sentinel")
  |
  v
Command (SentinelCommand / SentinelLister / SentinelShowOne)
  |-- take_action(parsed_args)
        |
        v
      _get_client(parsed_args)
        |-- reads --api-url or $SENTINEL_API_URL
        |-- creates AdminAPIClient
        |     |-- loads token from ~/.sentinel/token
        |
        v
      AdminAPIClient
        |-- get/post/patch/delete(path, data)
        |     |-- adds Authorization: Bearer <token>
        |     |-- httpx request
        |     |-- _raise_for_status() -> APIError on failure
        |
        v
      Admin API (http://localhost:8001)
```

---

## 3. Authentication

### 3.1 Token Storage

- **Location:** `~/.sentinel/token`
- **Format:** Plain text JWT (single line)
- **Permissions:** Filesystem permissions

### 3.2 Token Lifecycle

1. **Login:** `POST /auth/login` with `username`/`password` → receives `access_token` → saved to `~/.sentinel/token`
2. **Auto-load:** On `AdminAPIClient.__init__`, token is loaded from file if it exists
3. **Authorization header:** `Authorization: Bearer <token>` sent with every request
4. **Logout:** Deletes the token file and clears in-memory token

### 3.3 Environment Variables

| Variable | Purpose |
|---|---|
| `SENTINEL_API_URL` | Admin API base URL (default: `http://localhost:8001`) |
| `SENTINEL_USER` | Default username for login |
| `SENTINEL_PASSWORD` | Default password for login |

---

## 4. Global Options

| Option | Env Var | Default | Description |
|---|---|---|---|
| `--api-url` | `SENTINEL_API_URL` | `http://localhost:8001` | Admin API base URL |
| `--output` | — | `table` | Output format (`table`, `json`) |

---

## 5. Commands

### 5.1 Authentication

| Command | Description |
|---|---|
| `sentinel login` | Authenticate and save token |
| `sentinel logout` | Remove cached token |

**Login options:**
- `-u, --username` (default: `$SENTINEL_USER` or `"admin"`)
- `-p, --password` (default: `$SENTINEL_PASSWORD`, prompts if omitted)

### 5.2 Capabilities

| Command | Description |
|---|---|
| `sentinel capability list` | List all capabilities in catalog |
| `sentinel capability show <capability_id>` | Show capability details |
| `sentinel capability create` | Create new capability |
| `sentinel capability delete <capability_id>` | Delete capability |
| `sentinel capability approve <capability_id>` | Approve discovered capability |

**Capability list options:** `--category`, `--risk-level`
**Capability create options:** `--name`, `--version`, `--category`, `--risk-level`, `--input-schema`, `--output-schema`
**Capability delete options:** `--yes`

### 5.3 Packs

| Command | Description |
|---|---|
| `sentinel pack list` | List all packs |
| `sentinel pack show <pack_id>` | Show pack details |
| `sentinel pack create <name>` | Create new pack |
| `sentinel pack delete <pack_id>` | Delete pack |
| `sentinel pack member list <pack_id>` | List capabilities in pack |
| `sentinel pack member add <pack_id> <capability_id>` | Add capability to pack |
| `sentinel pack member remove <pack_id> <capability_id>` | Remove capability from pack |

**Pack create options:** `--description`
**Pack delete options:** `--yes`

### 5.4 Profiles

| Command | Description |
|---|---|
| `sentinel profile list` | List all profiles |
| `sentinel profile show <profile_id>` | Show profile details |
| `sentinel profile create <name>` | Create new profile |
| `sentinel profile delete <profile_id>` | Delete profile |

**Profile create options:** `--pack`, `--description`
**Profile delete options:** `--yes`

### 5.5 Bindings

| Command | Description |
|---|---|
| `sentinel binding list` | List all bindings |
| `sentinel binding show <binding_id>` | Show binding details |
| `sentinel binding create <principal_id> <resource_type> <resource_id>` | Create binding |
| `sentinel binding delete <binding_id>` | Delete binding |

**Binding list options:** `--principal`
**Binding create options:** `--target`, `--target-group`
**Binding delete options:** `--yes`

### 5.6 Executors

| Command | Description |
|---|---|
| `sentinel executor list` | List all executors |
| `sentinel executor show <executor_id>` | Show executor details |
| `sentinel executor capabilities <executor_id>` | List capabilities available on executor |

**Executor list options:** `--status`

### 5.7 Targets

| Command | Description |
|---|---|
| `sentinel target list` | List all targets |
| `sentinel target show <target_id>` | Show target details |
| `sentinel target update <target_id>` | Update target |
| `sentinel target delete <target_id>` | Delete target |
| `sentinel target health <target_id>` | Show target health status |
| `sentinel target monitor enable <target_id>` | Enable health monitoring |
| `sentinel target monitor disable <target_id>` | Disable health monitoring |

**Target list options:** `--status`
**Target update options:** `--description`, `--label KEY=VALUE` (repeatable)
**Target delete options:** `--yes`
**Target monitor enable options:** `--type` (TCP_PING, SNMP, SSH, API), `--interval` (seconds), `--timeout` (seconds)

### 5.8 Target Groups

| Command | Description |
|---|---|
| `sentinel target-group list` | List all target groups |
| `sentinel target-group show <group_id>` | Show group details |
| `sentinel target-group create <name>` | Create new group |
| `sentinel target-group delete <group_id>` | Delete group |
| `sentinel target-group member list <group_id>` | List targets in group |
| `sentinel target-group member add <group_id> <target_id>` | Add target to group |
| `sentinel target-group member remove <group_id> <target_id>` | Remove target from group |

**Target-group create options:** `--description`
**Target-group delete options:** `--yes`

### 5.9 Configurations

| Command | Description |
|---|---|
| `sentinel config list` | List capability configurations |
| `sentinel config show <config_id>` | Show configuration details |
| `sentinel config create` | Create configuration |
| `sentinel config delete <config_id>` | Delete configuration |

**Config create options:** `--scope-type`, `--scope-id`, `--capability`, `--constraints`, `--limits`
**Config delete options:** `--yes`

### 5.10 Audit Logs

| Command | Description |
|---|---|
| `sentinel audit list` | Query immutable audit log |

**Audit list options:**
- `--initiator` (filter by initiator ID)
- `--target` (filter by target ID)
- `--capability` (filter by capability name)
- `--outcome` (choices: `success`, `failure`, `denied`, `pending_2fa`)
- `--limit` (int, default: 50)
- `--offset` (int, default: 0)

### 5.11 Users (Superuser Only)

| Command | Description |
|---|---|
| `sentinel user list` | List admin users |
| `sentinel user create <username>` | Create admin user |
| `sentinel user delete <user_id>` | Delete admin user |

**User create options:** `--superuser` (flag), `--password` (prompts if omitted)
**User delete options:** `--yes`

---

## 6. Output Formatting

### 6.1 Lister Commands (Tabular)

Return `(columns, rows)` tuple. cliff formats as a table by default.

| Command | Columns |
|---|---|
| `capability list` | `id`, `name`, `version`, `category`, `risk_level` |
| `pack list` | `id`, `name`, `description` |
| `pack member list` | `capability_id`, `name`, `version` |
| `profile list` | `id`, `name`, `pack_id` |
| `binding list` | `id`, `principal_id`, `resource_type`, `resource_id` |
| `executor list` | `executor_id`, `hostname`, `status` |
| `executor capabilities` | `name`, `version`, `provider` |
| `target list` | `target_id`, `hostname`, `status` |
| `target-group list` | `id`, `name`, `description` |
| `target-group member list` | `target_id`, `hostname`, `status` |
| `config list` | `id`, `scope_type`, `scope_id`, `capability_id` |
| `audit list` | `request_id`, `initiator_id`, `capability_name`, `outcome`, `created_at` |
| `user list` | `id`, `username`, `is_superuser` |

### 6.2 ShowOne Commands (Key-Value)

Return `(columns, data)` tuple. cliff formats as key-value pairs.

| Command | Columns |
|---|---|
| `capability show` | `id`, `name`, `version`, `category`, `risk_level`, `input_schema`, `output_schema` |
| `pack show` | `id`, `name`, `description`, `capabilities` |
| `profile show` | `id`, `name`, `pack_id`, `overrides` |
| `binding show` | `id`, `principal_id`, `resource_type`, `resource_id`, `target_type`, `target_id` |
| `executor show` | `executor_id`, `hostname`, `status`, `capabilities` |
| `target show` | `id`, `target_id`, `hostname`, `status` |
| `target-group show` | `id`, `name`, `description` |
| `config show` | `id`, `scope_type`, `scope_id`, `capability_id`, `constraints`, `limits` |

### 6.3 JSON Output

All commands support `--output json`:

```bash
sentinel capability list --output json
```

---

## 7. Error Handling

### 7.1 Centralized Error Handling

All commands wrap execution in `try/except APIError`:

```python
def _handle_api_error(exc: APIError) -> None:
    if exc.status_code == 401:
        print("Error: not authenticated. Run `sentinel login` first.", file=sys.stderr)
    elif exc.status_code == 404:
        print(f"Error: not found — {exc.detail}", file=sys.stderr)
    elif exc.status_code == 403:
        print(f"Error: forbidden — {exc.detail}", file=sys.stderr)
    else:
        print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)
```

### 7.2 Error Codes

| Status | Message |
|---|---|
| 401 | `Error: not authenticated. Run 'sentinel login' first.` |
| 404 | `Error: not found — {detail}` |
| 403 | `Error: forbidden — {detail}` |
| Other | `Error: HTTP {status_code}: {detail}` |

All errors go to **stderr** and exit with code **1**.

### 7.3 Confirmation Prompts

All delete commands prompt for confirmation unless `--yes` is passed:

```python
confirm = input(f"Delete {resource} '{id}'? [y/N] ")
if confirm.lower() != "y":
    print("Aborted.")
    return
```

---

## 8. Entry Points

### 8.1 Main Entry Point

```ini
[entry_points]
console_scripts =
    sentinel = sentinel_cli.main:main
```

### 8.2 Command Registration

```ini
[entry_points]
sentinel =
    login              = sentinel_cli.login:Login
    logout             = sentinel_cli.login:Logout
    capability list    = sentinel_cli.capability:ListCapabilities
    capability show    = sentinel_cli.capability:ShowCapability
    capability create  = sentinel_cli.capability:CreateCapability
    capability delete  = sentinel_cli.capability:DeleteCapability
    capability approve = sentinel_cli.capability:ApproveCapability
    pack list          = sentinel_cli.pack:ListPacks
    pack show          = sentinel_cli.pack:ShowPack
    pack create        = sentinel_cli.pack:CreatePack
    pack delete        = sentinel_cli.pack:DeletePack
    pack member list   = sentinel_cli.pack:ListPackMembers
    pack member add    = sentinel_cli.pack:AddPackMember
    pack member remove = sentinel_cli.pack:RemovePackMember
    profile list       = sentinel_cli.profile:ListProfiles
    profile show       = sentinel_cli.profile:ShowProfile
    profile create     = sentinel_cli.profile:CreateProfile
    profile delete     = sentinel_cli.profile:DeleteProfile
    binding list       = sentinel_cli.binding:ListBindings
    binding show       = sentinel_cli.binding:ShowBinding
    binding create     = sentinel_cli.binding:CreateBinding
    binding delete     = sentinel_cli.binding:DeleteBinding
    executor list      = sentinel_cli.executor:ListExecutors
    executor show      = sentinel_cli.executor:ShowExecutor
    executor capabilities = sentinel_cli.executor:ListExecutorCapabilities
    target list        = sentinel_cli.target:ListTargets
    target show        = sentinel_cli.target:ShowTarget
    target update      = sentinel_cli.target:UpdateTarget
    target delete      = sentinel_cli.target:DeleteTarget
    target-group list  = sentinel_cli.target_group:ListTargetGroups
    target-group show  = sentinel_cli.target_group:ShowTargetGroup
    target-group create = sentinel_cli.target_group:CreateTargetGroup
    target-group delete = sentinel_cli.target_group:DeleteTargetGroup
    target-group member list = sentinel_cli.target_group:ListGroupMembers
    target-group member add = sentinel_cli.target_group:AddGroupMember
    target-group member remove = sentinel_cli.target_group:RemoveGroupMember
    config list        = sentinel_cli.config:ListConfigurations
    config show        = sentinel_cli.config:ShowConfiguration
    config create      = sentinel_cli.config:CreateConfiguration
    config delete      = sentinel_cli.config:DeleteConfiguration
    audit list         = sentinel_cli.audit:ListAuditLogs
    user list          = sentinel_cli.user:ListUsers
    user create        = sentinel_cli.user:CreateUser
    user delete        = sentinel_cli.user:DeleteUser
```

---

## 9. Migration from Legacy CLI

### 9.1 Command Mapping

| Legacy Command | New Command |
|---|---|
| `sentinel host list` | `sentinel executor list` |
| `sentinel host show` | `sentinel executor show` |
| `sentinel host register` | `sentinel target update` |
| `sentinel host delete` | `sentinel target delete` |
| `sentinel commandset list` | `sentinel capability list` |
| `sentinel commandset show` | `sentinel capability show` |
| `sentinel commandset create` | `sentinel capability create` |
| `sentinel commandset delete` | `sentinel capability delete` |
| `sentinel command list` | `sentinel pack member list` |
| `sentinel command add` | `sentinel pack member add` |
| `sentinel command delete` | `sentinel pack member remove` |
| `sentinel policy list` | `sentinel binding list` |
| `sentinel policy show` | `sentinel binding show` |
| `sentinel policy create` | `sentinel binding create` |
| `sentinel policy delete` | `sentinel binding delete` |
| `sentinel group list` | `sentinel target-group list` |
| `sentinel group show` | `sentinel target-group show` |
| `sentinel group create` | `sentinel target-group create` |
| `sentinel group delete` | `sentinel target-group delete` |
| `sentinel group member list` | `sentinel target-group member list` |
| `sentinel group member add` | `sentinel target-group member add` |
| `sentinel group member remove` | `sentinel target-group member remove` |
| `sentinel audit log list` | `sentinel audit list` |

### 9.2 New Commands

| Command | Description |
|---|---|
| `sentinel pack *` | Pack management |
| `sentinel profile *` | Profile management |
| `sentinel config *` | Configuration management |
| `sentinel capability approve` | Approve discovered capability |

---

## 10. Definition of Done

CLI v1 is complete when:

1. All commands work against Admin API
2. Authentication and token caching work
3. Output formatting (table + JSON) works
4. Error handling is consistent
5. Confirmation prompts work for destructive operations
6. Entry points are registered correctly
7. Help text is clear and complete
8. Migration mapping is documented
