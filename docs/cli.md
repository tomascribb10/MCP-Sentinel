# MCP-Sentinel — CLI Reference

The `sentinel` CLI lets administrators manage every aspect of MCP-Sentinel from the command line.

---

## Setup

```bash
export SENTINEL_API_URL=http://<host>:8001   # Admin API base URL
```

The CLI stores the JWT token in `~/.sentinel/token`. All commands require a valid token except `login`.

Global flags available on every command:

| Flag             | Description                         |
|------------------|-------------------------------------|
| `--os-auth-url`  | Override `SENTINEL_API_URL`         |
| `--format`       | Output format: `table`, `json`, `csv`, `value` |
| `--column`       | Select specific columns to display  |

---

## Authentication

### sentinel login

Authenticate and save the token.

```bash
sentinel login -u admin
sentinel login -u admin -p mypassword
```

Options:

| Flag             | Env var            | Default  |
|------------------|--------------------|----------|
| `-u, --username` | `SENTINEL_USER`    | `admin`  |
| `-p, --password` | `SENTINEL_PASSWORD`| prompted |

Token is saved to `~/.sentinel/token` and reused automatically by all subsequent commands.

---

### sentinel logout

Remove the cached token.

```bash
sentinel logout
```

---

## Hosts (Agents)

Agents are auto-registered on first heartbeat. Use these commands to inspect and manage them.

### sentinel host list

```bash
sentinel host list
sentinel host list --status active
```

Options:

| Flag       | Description                             |
|------------|-----------------------------------------|
| `--status` | Filter: `active`, `inactive`, `unknown` |

Output columns: `agent_id`, `hostname`, `status`, `last_heartbeat`

---

### sentinel host show

```bash
sentinel host show <agent_id>
```

Argument: agent_id or UUID of the agent.

---

### sentinel host set

Update an agent's description or labels.

```bash
sentinel host set <agent_id> --description "Primary compute node"
sentinel host set <agent_id> --label env=prod --label region=us-east
```

Options:

| Flag            | Description                                    |
|-----------------|------------------------------------------------|
| `--description` | Free-text description                          |
| `--label`       | `KEY=VALUE` label (repeatable)                 |

---

### sentinel host delete

```bash
sentinel host delete <agent_id>
sentinel host delete <agent_id> --yes   # skip confirmation
```

---

## Host Groups

An agent must belong to at least one group to receive commands. Groups are the target scope for policies.

### sentinel group list

```bash
sentinel group list
```

Output columns: `id`, `name`, `description`

---

### sentinel group show

```bash
sentinel group show <group_id>
```

---

### sentinel group create

```bash
sentinel group create prod-servers
sentinel group create prod-servers --description "Production nodes"
```

---

### sentinel group delete

```bash
sentinel group delete <group_id>
sentinel group delete <group_id> --yes
```

---

### sentinel group member list

```bash
sentinel group member list <group_id>
```

Output columns: `agent_id`, `hostname`, `status`

---

### sentinel group member add

```bash
sentinel group member add <group_id> <agent_id>
```

---

### sentinel group member remove

```bash
sentinel group member remove <group_id> <agent_id>
```

---

## Command Sets

A Command Set defines which commands are allowed for a given driver, along with argument constraints and 2FA requirements.

### sentinel commandset list

```bash
sentinel commandset list
```

Output columns: `id`, `name`, `driver`, `description`

---

### sentinel commandset show

```bash
sentinel commandset show <command_set_id>
```

Displays the command set details and a summary of all its commands.

---

### sentinel commandset create

```bash
sentinel commandset create linux_diagnostics
sentinel commandset create linux_diagnostics --driver posix_bash --description "Read-only tools"
```

Options:

| Flag            | Default      | Description                                  |
|-----------------|--------------|----------------------------------------------|
| `--driver`      | `posix_bash` | Execution driver: `posix_bash`, `ansible`, `openstack_sdk` |
| `--description` |              | Optional description                         |

---

### sentinel commandset delete

```bash
sentinel commandset delete <command_set_id>
sentinel commandset delete <command_set_id> --yes
```

---

### sentinel command list

List commands within a command set.

```bash
sentinel command list <command_set_id>
```

Output columns: `id`, `name`, `binary`, `args_regex`, `require_2fa`

---

### sentinel command add

Add an allowed command to a command set.

```bash
sentinel command add <command_set_id> uname /usr/bin/uname
sentinel command add <command_set_id> uname /usr/bin/uname --args-regex "^(-a|-r|-n)$"
sentinel command add <command_set_id> restart_nginx /usr/bin/systemctl \
    --args-regex "^restart (nginx|apache2)$" \
    --require-2fa
```

Arguments:

| Argument         | Description                                |
|------------------|--------------------------------------------|
| `command_set_id` | UUID of the command set                    |
| `name`           | Logical name (e.g. `restart_nginx`)        |
| `binary`         | Absolute path to the binary                |

Options:

| Flag            | Default | Description                                                    |
|-----------------|---------|----------------------------------------------------------------|
| `--args-regex`  | `.*`    | `re.fullmatch` pattern applied to `" ".join(args)`. Omit to allow any args |
| `--require-2fa` | off     | Block execution until a human approves via the 2FA plugin      |

**Args regex examples:**

| Intent                             | Regex                               |
|------------------------------------|-------------------------------------|
| No arguments allowed               | `^$`                                |
| Exactly `-a`                       | `^-a$`                              |
| One of several flags               | `^(-a\|-r\|-n)$`                    |
| `restart` + specific service names | `^restart (nginx\|apache2)$`        |
| Any `/var/log/` path               | `^/var/log/[\w./]+$`                |
| Any arguments (unrestricted)       | `.*`                                |

---

### sentinel command delete

```bash
sentinel command delete <command_set_id> <command_id>
sentinel command delete <command_set_id> <command_id> --yes
```

---

## Policies (Role Bindings)

A policy grants a principal (AI agent identity) access to a command set scoped to a host group.

### sentinel policy list

```bash
sentinel policy list
sentinel policy list --principal llm-agent-claude
```

Output columns: `id`, `principal_id`, `command_set_id`, `target_group_id`

---

### sentinel policy show

```bash
sentinel policy show <policy_id>
```

---

### sentinel policy create

```bash
sentinel policy create <principal_id> <command_set_id> --target-group <group_id>
```

Arguments:

| Argument         | Description                                          |
|------------------|------------------------------------------------------|
| `principal_id`   | Identity of the AI agent or user (free string)       |
| `command_set_id` | UUID of the command set to grant                     |

Options:

| Flag             | Description                                          |
|------------------|------------------------------------------------------|
| `--target-group` | UUID of the host group to scope access to (required) |

Example:

```bash
sentinel policy create llm-agent-claude a1b2c3-... --target-group d4e5f6-...
```

---

### sentinel policy delete

```bash
sentinel policy delete <policy_id>
sentinel policy delete <policy_id> --yes
```

---

## Audit Logs

Audit logs are immutable and written automatically for every execution request.

### sentinel audit log list

```bash
sentinel audit log list
sentinel audit log list --initiator llm-agent-claude
sentinel audit log list --agent 2b942c2ccb21
sentinel audit log list --outcome denied
sentinel audit log list --limit 100 --offset 50
```

Options:

| Flag          | Description                                            |
|---------------|--------------------------------------------------------|
| `--initiator` | Filter by initiator (AI agent) identity                |
| `--agent`     | Filter by target agent_id                              |
| `--outcome`   | `success`, `failure`, `denied`, `pending_2fa`          |
| `--limit`     | Max results (default: 50)                              |
| `--offset`    | Pagination offset (default: 0)                         |

Output columns: `request_id`, `initiator_id`, `target_agent_id`, `outcome`, `exit_code`, `created_at`

---

## Users

Superuser access required for all user management commands.

### sentinel user list

```bash
sentinel user list
```

Output columns: `id`, `username`, `is_superuser`, `created_at`

---

### sentinel user create

```bash
sentinel user create alice
sentinel user create alice --superuser
sentinel user create alice --password secret123
```

Options:

| Flag          | Description                                        |
|---------------|----------------------------------------------------|
| `--superuser` | Grant superuser privileges                         |
| `--password`  | Password (prompted interactively with confirmation if omitted) |

Minimum password length: 8 characters.

---

### sentinel user delete

```bash
sentinel user delete <user_id>
sentinel user delete <user_id> --yes
```

---

## Common Workflow

Setting up access for a new AI agent from scratch:

```bash
# 1. Authenticate
sentinel login -u admin

# 2. Find the agent (auto-registered after first heartbeat)
sentinel host list

# 3. Create a host group and add the agent
sentinel group create prod-servers
sentinel group member add <GROUP_ID> <AGENT_ID>

# 4. Create a command set with allowed commands
sentinel commandset create diagnostics --driver posix_bash
sentinel command add <CS_ID> uname   /usr/bin/uname   --args-regex "^-a$"
sentinel command add <CS_ID> df      /usr/bin/df       --args-regex "^-h$"
sentinel command add <CS_ID> id      /usr/bin/id       --args-regex "^$"

# 5. Create the policy
sentinel policy create llm-agent-claude <CS_ID> --target-group <GROUP_ID>

# 6. Verify
sentinel policy list --principal llm-agent-claude

# 7. Audit what the agent has done
sentinel audit log list --initiator llm-agent-claude --limit 20
```
