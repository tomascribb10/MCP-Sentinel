# Deployment Guide

This document describes the three deployment configurations for MCP-Sentinel agents. Each configuration corresponds to a different use case.

---

## Overview

```
┌──────────────────────────────────────────────┐
│  docker-compose.yml                           │
│  (Control Plane — always required)            │
│                                              │
│  RabbitMQ · PostgreSQL · Conductor           │
│  Scheduler · MCP API · Admin API             │
└──────────────────┬───────────────────────────┘
                   │  RabbitMQ :5672
           ┌───────┴──────────────────┐
           │                          │
           ▼                          ▼
┌─────────────────────┐   ┌──────────────────────────┐
│ docker-compose.      │   │ scripts/install-agent.sh  │
│ agent-test.yml       │   │                           │
│                      │   │ Installed on a real host  │
│ Containerised agent  │   │ as a systemd service.     │
│ with a fixed name    │   │ agent_id = host hostname  │
│ (for dev / testing)  │   │ (real OS access)          │
└─────────────────────┘   └──────────────────────────┘
```

---

## 1. Control Plane (always required)

**File:** `docker-compose.yml`

Starts all core services. Agents are managed separately — none are included here.

```bash
# Copy and edit the config
cp config/sentinel.dev.conf.example config/sentinel.dev.conf

# Start
docker compose up -d

# Seed built-in command sets on first run
SENTINEL_SEED_DEFAULTS=true docker compose restart conductor
```

**Services started:**

| Container | Port | Description |
|-----------|------|-------------|
| `sentinel-rabbitmq` | 5672, 15672 | Message broker |
| `sentinel-postgres` | 5432 | Database |
| `sentinel-conductor` | — | RBAC, 2FA, signing, audit |
| `sentinel-scheduler` | — | Heartbeat tracker, routing |
| `sentinel-mcp-api` | 8000 | MCP gateway for AI agents |
| `sentinel-admin-api` | 8001 | REST API for administrators |

> **Network name:** `sentinel_sentinel-net` (used by agent-test compose)
> **Volume name:** `sentinel_sentinel-keys` (RSA keys, used by agent-test compose)

---

## 2. Containerised Test Agent (fixed identity)

**File:** `docker-compose.agent-test.yml`

A Docker-based agent with a **stable `agent_id`** that survives container recreations. Use this for development and integration testing. The agent's identity never changes because Docker sets the container's hostname to the fixed value `sentinel-agent-test`.

**Prerequisites:** The control plane must be running first.

```bash
# Copy and optionally edit the config
cp config/sentinel.agent-test.conf.example config/sentinel.agent-test.conf

# Start
docker compose -f docker-compose.agent-test.yml up -d --build

# Logs
docker compose -f docker-compose.agent-test.yml logs -f

# Stop
docker compose -f docker-compose.agent-test.yml down
```

**Why the agent_id is stable:**

`sentinel-agent` resolves its identity from `[agent] agent_id` in the config file. If that is unset, it falls back to `socket.gethostname()`. Docker uses the `hostname:` field to set the container's hostname — so setting `hostname: sentinel-agent-test` in the compose file means `gethostname()` always returns `sentinel-agent-test`, regardless of the container ID.

**Identity:** `sentinel-agent-test`
**Network:** Joins the existing `sentinel_sentinel-net` bridge.
**RSA keys:** Reads from the existing `sentinel_sentinel-keys` Docker volume.

---

## 3. Agent on a Real Host (systemd service)

**Script:** `scripts/install-agent.sh`

Installs sentinel-agent directly on a Linux host as a systemd service. The agent runs with the real OS user, sees real host processes and logs, and is identified by the machine's actual hostname.

```bash
# Clone the repo on the target host
git clone https://github.com/your-org/sentinel.git
cd sentinel

# Install (creates venv, systemd unit, config template)
sudo bash scripts/install-agent.sh

# Edit config: set RabbitMQ address
sudo nano /etc/sentinel/sentinel-agent.conf

# Copy the conductor public key
scp admin@control-plane:/etc/sentinel/conductor_public.pem \
    /etc/sentinel/conductor_public.pem

# Start
sudo systemctl start sentinel-agent
sudo journalctl -fu sentinel-agent
```

See [agent-install.md](agent-install.md) for the complete installation guide.

**Identity:** Real hostname of the machine (`hostname` command output).
**Venv:** `/opt/sentinel-agent/venv` (only agent dependencies, ~80 MB).
**Config:** `/etc/sentinel/sentinel-agent.conf`.
**Service user:** `sentinel-agent` (non-root; added to `adm` and `systemd-journal` groups).

---

## Comparison

| | Test Agent Container | Real Host Service |
|---|---|---|
| **Identity stability** | Fixed via `hostname:` in compose | Fixed — it's the real hostname |
| **Host process visibility** | Container processes only | Real host processes |
| **Log access** | Container logs only | Real `/var/log/` |
| **Systemctl / D-Bus** | Not available | Available (with polkit/sudo config) |
| **Setup effort** | `docker compose up` | `sudo bash install-agent.sh` |
| **Recommended for** | Dev / integration tests | Staging / production hosts |

---

## Managing Agents After Registration

Agents auto-register on first heartbeat. From any machine with the CLI:

```bash
# List registered agents
sentinel host list

# Assign to a group
sentinel group create prod-servers
sentinel group member add <GROUP_ID> <AGENT_ID>

# Bind a command set (or use a seeded default)
sentinel commandset list
sentinel policy create llm-agent-claude <CS_ID> --target-group <GROUP_ID>
```
