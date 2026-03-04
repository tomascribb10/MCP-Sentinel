# Adding Default Command Sets

This guide explains how to add a new built-in command set to MCP-Sentinel so that it is
automatically seeded into every new installation and can be inserted into existing
deployments without manual SQL.

---

## Where the data lives

```
sentinel/common/fixtures/default_command_sets.py
```

This is a **pure-data module** — no DB imports, no I/O.  The list
`DEFAULT_COMMAND_SETS` is the single source of truth for all built-in command sets.
The seeder (`sentinel_conductor/seeder.py`) reads it at conductor startup.

---

## Step 1 — Add the entry to the fixtures file

Append a new dict to `DEFAULT_COMMAND_SETS` following the schema below.
Keep the section header comment consistent with the numbering.

```python
# ------------------------------------------------------------------
# N. your_command_set — short description
# ------------------------------------------------------------------
{
    "name": "your_command_set",          # unique slug, snake_case
    "driver": "posix_bash",              # must match a stevedore driver entry_point
    "description": "Human-readable description shown in the Admin UI and CLI.",
    "commands": [
        {
            "name": "command_name",      # unique within the command set
            "binary": "/usr/bin/tool",   # absolute path to the executable
            "args_regex": r"^-flag [\w.-]+$",  # matched against the joined args string
            "require_2fa": False,        # True for mutating/destructive operations
            "require_sudo": False,       # True when the command needs root privileges
            "description": "One-liner shown to admins and the LLM.",
            "allowed_paths": None,       # list[str] of path prefixes, or None = unrestricted
        },
        # ...
    ],
}
```

### args_regex conventions

| Pattern element | Meaning |
|---|---|
| `^...$` | Always anchor — partial matches are never acceptable |
| `[\w.-]+` | Alphanumeric + underscore/dot/hyphen (safe for names, hostnames) |
| `\d+` | Digits only (PID, port, count) |
| `(a\|b\|c)` | Whitelist of literal values |
| `(flag )?` | Optional flag |

### require_2fa guidelines

| Action type | require_2fa |
|---|---|
| Read-only inspection | `False` |
| Creates new state (snapshot, file) | `True` |
| Modifies existing state (restart, renice) | `True` |
| Destroys or rolls back state | `True` |

### require_sudo guidelines

Set `require_sudo: True` when the binary requires root UID to operate correctly:

| Scenario | require_sudo |
|---|---|
| Killing processes owned by other users (`kill`) | `True` |
| Mutating systemd services (`systemctl restart/stop/start`) | `True` |
| Changing process priority to negative values (`renice`) | `True` |
| ZFS pool/dataset mutations (`zpool scrub`, `zfs snapshot`, etc.) | `True` |
| Read-only inspection (ps, df, ss, ping, zfs list…) | `False` |

`scripts/install-agent.sh` creates `/etc/sudoers.d/sentinel-agent` with `NOPASSWD`
rules for the exact binaries that need sudo. Argument validation is still performed by
`args_regex` (Conductor RBAC) and the agent driver — sudoers only grants binary-level
access, not unrestricted root.

---

### allowed_paths guidelines

Use `allowed_paths` when a command operates on files and you want to restrict **which
part of the filesystem** it can touch, independently of `args_regex`.

```python
# Only allow reading files under /var/log/
"allowed_paths": ["/var/log/"],

# No path restriction (binary does not take file arguments)
"allowed_paths": None,
```

The list contains **prefixes** — any path argument must start with at least one of them.
The check is enforced both at the conductor (RBAC) and at the agent driver (defense-in-depth).

---

## Step 2 — Deploy to a running installation

### Option A — Automatic seeder (recommended)

Restart the conductor with the seed flag.  The seeder is **idempotent**: it skips
command sets that already exist by name and only inserts new ones.

```bash
# Docker Compose
SENTINEL_SEED_DEFAULTS=true docker compose up -d conductor

# Bare-metal / systemd
SENTINEL_SEED_DEFAULTS=true sentinel-conductor
# (or set the variable in the systemd unit's EnvironmentFile)
```

Check the conductor logs to confirm:

```
INFO  sentinel_conductor.seeder  Seeded 1 new command set(s): zfs_storage
```

### Option B — Manual via CLI

If you cannot restart the conductor right now, use the CLI to insert the command set
directly.  Replace the values with those from your fixture entry.

```bash
export SENTINEL_API_URL=http://localhost:8001
sentinel login -u admin

sentinel commandset create <name> --driver <driver> --description "<desc>"
CS_ID=$(sentinel commandset list | grep <name> | awk '{print $2}')

sentinel command add $CS_ID <cmd_name> <binary> \
    --args-regex "<regex>" \
    [--require-2fa] \
    [--allowed-paths "/prefix1/" "/prefix2/"]
```

---

## Step 3 — Assign the command set to agents

A command set is useless until it is attached to a **role binding** that links it to an
agent or host group.

```bash
# Assign to a specific agent
sentinel policy create <policy-name> <cs_id> --target-agent <agent_id>

# Assign to a whole group
sentinel policy create <policy-name> <cs_id> --target-group <group_id>
```

---

## Built-in command sets reference

| Name | Driver | Commands | Notes |
|---|---|---|---|
| `linux_diagnostics` | posix_bash | 6 | Read-only system info, no 2FA |
| `log_reader` | posix_bash | 3 | Restricted to `/var/log/`, no 2FA |
| `service_management` | posix_bash | 5 | status/list no 2FA; restart/stop/start 2FA |
| `process_management` | posix_bash | 7 | inspect no 2FA; kill/renice 2FA |
| `zfs_storage` | posix_bash | 10 | pool/dataset inspection no 2FA; snapshot/rollback/destroy 2FA |
| `network_diagnostics` | posix_bash | 5 | ping, ss, dig, ip — no 2FA |
