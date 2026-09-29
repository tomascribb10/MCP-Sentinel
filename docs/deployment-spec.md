# MCP-Sentinel — Deployment Specification

**Status:** Draft  
**Version:** 1.0.0-draft  
**Target:** Docker Compose, Ansible, systemd, configuration management  
**Audience:** DevOps, SRE, code-generation agents, security reviewers

Normative terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** define implementation requirements.

---

## 1. Purpose

This specification defines how to deploy MCP-Sentinel in development and production environments.

> **MCP-Sentinel follows OpenStack's deployment patterns: microservices, message bus, and database-backed state.**

---

## 2. Architecture

### 2.1 Deployment Topology

```text
┌─────────────────────────────────────────────────────────────────┐
│                        CONTROL PLANE                             │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │sentinel-mcp  │  │sentinel-     │  │sentinel-     │          │
│  │-api :8000    │  │admin-api     │  │conductor     │          │
│  │              │  │:8001         │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │sentinel-     │  │RabbitMQ      │  │PostgreSQL    │          │
│  │scheduler     │  │:5672         │  │:5432         │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ RabbitMQ (Protocol v2)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       EXECUTION PLANE                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ sentinel_executor  (one per target host)                 │  │
│  │                                                          │  │
│  │  - Capability SDK                                        │  │
│  │  - Local Capability Registry                             │  │
│  │  - Built-in providers (linux.system, linux.logs, etc.)    │  │
│  │  - Optional plugins (linux.zfs, etc.)                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Network Requirements

| Source | Destination | Port | Protocol | Purpose |
|---|---|---|---|---|
| AI Agents | sentinel-mcp-api | 8000 | HTTP | MCP tools |
| Admins | sentinel-admin-api | 8001 | HTTP | Admin REST API |
| CLI | sentinel-admin-api | 8001 | HTTP | CLI operations |
| sentinel-conductor | RabbitMQ | 5672 | AMQP | RPC messaging |
| sentinel-scheduler | RabbitMQ | 5672 | AMQP | RPC messaging |
| sentinel-mcp-api | RabbitMQ | 5672 | AMQP | RPC messaging |
| sentinel-admin-api | RabbitMQ | 5672 | AMQP | RPC messaging |
| sentinel-conductor | PostgreSQL | 5432 | TCP | Database |
| sentinel_executor | RabbitMQ | 5672 | AMQP | Protocol v2 |

---

## 3. Docker Compose (Development)

### 3.1 Services

| Service | Image | Ports | Description |
|---|---|---|---|
| `rabbitmq` | `rabbitmq:3.13-management-alpine` | 5672, 15672 | Message bus |
| `postgres` | `postgres:16-alpine` | 5432 | Database |
| `keygen` | Build from `./sentinel` | — | One-shot RSA key generation |
| `migrate` | Build from `./sentinel` | — | One-shot DB migration |
| `conductor` | Build from `./sentinel` | — | Core orchestration |
| `scheduler` | Build from `./sentinel` | — | Heartbeat registry |
| `mcp-api` | Build from `./sentinel` | 8000 | MCP gateway |
| `admin-api` | Build from `./sentinel` | 8001 | Admin API |

### 3.2 Volumes

| Volume | Purpose |
|---|---|
| `postgres-data` | PostgreSQL persistent data |
| `rabbitmq-data` | RabbitMQ persistent data |
| `sentinel-keys` | RSA keys shared between conductor and executor |

### 3.3 Service Dependencies

```text
postgres ──> keygen ──> migrate ──> conductor ──> scheduler
                                           ├──> mcp-api
                                           └──> admin-api
rabbitmq ─────────────────────────────────> conductor
```

### 3.4 Health Checks

| Service | Health Check | Interval | Timeout | Retries |
|---|---|---|---|---|
| `rabbitmq` | `rabbitmq-diagnostics -q ping` | 10s | 5s | 5 |
| `postgres` | `pg_isready -U sentinel -d sentinel` | 10s | 5s | 5 |
| `conductor` | `pgrep -f sentinel-conductor` | 15s | 5s | 3 |
| `mcp-api` | HTTP GET /health | 15s | 5s | 3 |
| `admin-api` | HTTP GET /health | 15s | 5s | 3 |

### 3.5 Environment Variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `SENTINEL_CONF` | All control plane | `/etc/sentinel/sentinel.conf` | Config file path |
| `SENTINEL_INITIAL_ADMIN_USER` | conductor | `admin` | Initial admin username |
| `SENTINEL_INITIAL_ADMIN_PASSWORD` | conductor | `sentinel-admin-dev` | Initial admin password |
| `SENTINEL_INITIAL_ADMIN_EMAIL` | conductor | `admin@localhost` | Initial admin email |
| `SENTINEL_SEED_DEFAULTS` | conductor | `true` | Seed default capabilities/packs |

### 3.6 Quick Start

```bash
# Clone and configure
git clone https://github.com/your-org/mcp-sentinel.git
cd mcp-sentinel
cp config/sentinel.dev.conf.example config/sentinel.dev.conf

# Start control plane
docker compose up --build -d

# Verify services
docker compose ps

# Login with CLI
export SENTINEL_API_URL=http://localhost:8001
sentinel login -u admin
# Password: sentinel-admin-dev
```

---

## 4. Docker Compose (Production)

### 4.1 Differences from Development

| Aspect | Development | Production |
|---|---|---|
| Debug | `true` | `false` |
| Log level | `DEBUG` | `INFO` |
| Admin password | Hardcoded | Strong secret |
| RabbitMQ credentials | `sentinel/sentinel` | Strong credentials |
| PostgreSQL credentials | `sentinel/sentinel` | Strong credentials |
| API keys | Default | Strong secrets |
| TLS | None | Required |
| Replicas | 1 | Multiple (HA) |
| Resource limits | None | Configured |

### 4.2 Production Checklist

- [ ] Change all default credentials
- [ ] Enable TLS for MCP API and Admin API
- [ ] Configure strong API keys
- [ ] Set up PostgreSQL backups
- [ ] Set up RabbitMQ clustering
- [ ] Configure resource limits
- [ ] Set up monitoring and alerting
- [ ] Configure log aggregation
- [ ] Enable audit log retention
- [ ] Test disaster recovery

---

## 5. Executor Deployment

### 5.1 Packaged Deployment

```bash
apt install sentinel-executor
```

### 5.2 Python Deployment

```bash
python3 -m venv /opt/mcp-sentinel
/opt/mcp-sentinel/bin/pip install sentinel-executor
```

### 5.3 Configuration

```yaml
executor:
  id: 4cb6e61e-....  # Auto-generated on first run, persisted locally

control_plane:
  url: https://sentinel.infraestructura.com.ar
  enrollment_token: "..."

capabilities:
  builtin: true

plugins:
  auto_discover: true
```

### 5.4 Systemd Service

```ini
[Unit]
Description=MCP-Sentinel Executor
After=network.target

[Service]
Type=simple
User=sentinel-executor
Group=sentinel-executor
ExecStart=/opt/mcp-sentinel/bin/sentinel-executor
Restart=on-failure
RestartSec=10
RestartSteps=6
RestartMaxDelaySec=300

# Security hardening
NoNewPrivileges=false
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=false
RestrictSUIDSGID=false

# Capabilities
AmbientCapabilities=CAP_NET_RAW CAP_SETUID CAP_SETGID CAP_KILL CAP_AUDIT_WRITE
CapabilityBoundingSet=CAP_NET_RAW CAP_SETUID CAP_SETGID CAP_KILL CAP_AUDIT_WRITE

[Install]
WantedBy=multi-user.target
```

### 5.5 Installation Script

```bash
# Install executor on a host
curl -fsSL https://sentinel.infraestructura.com.ar/install.sh | sudo bash

# Or manual installation
sudo ./scripts/install-executor.sh \
  --config-dir /etc/sentinel \
  --install-dir /opt/mcp-sentinel \
  --user sentinel-executor
```

### 5.6 Uninstallation

```bash
sudo ./scripts/install-executor.sh --uninstall
```

---

## 6. Ansible Deployment

### 6.1 Inventory

```ini
[sentinel_executors]
executor-01 ansible_host=192.0.2.10 ansible_user=admin
executor-02 ansible_host=192.0.2.11 ansible_user=admin

[sentinel_executors:vars]
sentinel_executor_user=sentinel-executor
sentinel_executor_install_dir=/opt/mcp-sentinel
sentinel_executor_config_dir=/etc/sentinel
```

### 6.2 Playbook

```yaml
---
- name: Deploy MCP-Sentinel Executor
  hosts: sentinel_executors
  become: true
  roles:
    - sentinel_executor
```

### 6.3 Role Variables

| Variable | Default | Description |
|---|---|---|
| `sentinel_executor_user` | `sentinel-executor` | Service user |
| `sentinel_executor_install_dir` | `/opt/mcp-sentinel` | Installation directory |
| `sentinel_executor_config_dir` | `/etc/sentinel` | Configuration directory |
| `sentinel_executor_control_plane_url` | — | Control Plane URL |
| `sentinel_executor_enrollment_token` | — | Enrollment token |
| `sentinel_executor_builtin_enabled` | `true` | Enable built-in providers |
| `sentinel_executor_plugin_auto_discover` | `true` | Auto-discover plugins |

---

## 7. Configuration

### 7.1 Control Plane Configuration

```ini
[DEFAULT]
debug = false
log_level = INFO

[database]
connection = postgresql+psycopg2://sentinel:PASSWORD@postgres:5432/sentinel
pool_size = 10
max_overflow = 20
echo = false

[messaging]
transport_url = rabbit://sentinel:PASSWORD@rabbitmq:5672/sentinel
rpc_topic_conductor = sentinel.conductor
rpc_topic_scheduler = sentinel.scheduler
executor_queue_prefix = sentinel.executor
rpc_timeout = 60

[conductor]
private_key_path = /etc/sentinel/conductor_private.pem
public_key_path = /etc/sentinel/conductor_public.pem
rsa_key_bits = 4096
twofa_challenge_timeout_seconds = 300
workers = 1

[auth]
provider = telegram
admin_api_secret_key = CHANGE_ME
admin_api_token_ttl_minutes = 60
mcp_api_secret_key = CHANGE_ME

[telegram]
bot_token = CHANGE_ME
approver_chat_id = CHANGE_ME
polling_interval_seconds = 5
```

### 7.2 Executor Configuration

```ini
[DEFAULT]
debug = false
log_level = INFO

[executor]
executor_id = 4cb6e61e-....
conductor_public_key_path = /etc/sentinel/conductor_public.pem
heartbeat_interval_seconds = 30

[messaging]
transport_url = rabbit://sentinel:PASSWORD@rabbitmq:5672/sentinel
rpc_topic_conductor = sentinel.conductor
rpc_topic_scheduler = sentinel.scheduler
executor_queue_prefix = sentinel.executor
rpc_timeout = 60

[capabilities]
builtin_enabled = true
plugin_auto_discover = true
```

### 7.3 Environment Variables

| Variable | Description |
|---|---|
| `SENTINEL_CONF` | Path to config file |
| `SENTINEL_EXECUTOR_ID` | Override executor_id (for testing) |
| `SENTINEL_INITIAL_ADMIN_USER` | Initial admin username |
| `SENTINEL_INITIAL_ADMIN_PASSWORD` | Initial admin password |
| `SENTINEL_SEED_DEFAULTS` | Seed default capabilities/packs |

---

## 8. Key Management

### 8.1 RSA Key Generation

```bash
# Generate keys (one-shot container)
docker compose run --rm keygen

# Or manually
openssl genrsa -out conductor_private.pem 4096
openssl rsa -in conductor_private.pem -pubout -out conductor_public.pem
```

### 8.2 Key Distribution

| Component | Key | Location |
|---|---|---|
| Conductor | Private key | `/etc/sentinel/conductor_private.pem` |
| Executor | Public key | `/etc/sentinel/conductor_public.pem` |

### 8.3 Key Rotation

1. Generate new key pair
2. Distribute new public key to all executors
3. Update conductor with new private key
4. Restart conductor
5. Verify all executors reconnect

---

## 9. Monitoring

### 9.1 Health Checks

| Service | Endpoint | Expected |
|---|---|---|
| `mcp-api` | `GET /health` | `{"status": "ok"}` |
| `admin-api` | `GET /health` | `{"status": "ok"}` |
| `conductor` | Process check | Running |
| `scheduler` | Process check | Running |
| `rabbitmq` | `rabbitmq-diagnostics -q ping` | `ping ok` |
| `postgres` | `pg_isready -U sentinel -d sentinel` | `accepting connections` |

### 9.2 Metrics

| Metric | Source | Description |
|---|---|---|
| `sentinel_requests_total` | Conductor | Total capability requests |
| `sentinel_requests_denied_total` | Conductor | Total denied requests |
| `sentinel_execution_duration_seconds` | Conductor | Execution duration |
| `sentinel_executors_active` | Scheduler | Active executors |
| `sentinel_capabilities_available` | Conductor | Available capabilities |

### 9.3 Log Aggregation

All services log to stdout/stderr. Use Docker logging driver or external aggregation:

```yaml
# docker-compose.yml
services:
  conductor:
    logging:
      driver: "fluentd"
      options:
        fluentd-address: "localhost:24224"
        tag: "sentinel.conductor"
```

---

## 10. Backup and Recovery

### 10.1 PostgreSQL Backup

```bash
# Backup
docker exec sentinel-postgres pg_dump -U sentinel sentinel > backup.sql

# Restore
docker exec -i sentinel-postgres psql -U sentinel sentinel < backup.sql
```

### 10.2 RabbitMQ Backup

```bash
# Backup
docker exec sentinel-rabbitmq rabbitmqctl export_definitions /tmp/rabbitmq.json
docker cp sentinel-rabbitmq:/tmp/rabbitmq.json ./rabbitmq.json

# Restore
docker cp ./rabbitmq.json sentinel-rabbitmq:/tmp/rabbitmq.json
docker exec sentinel-rabbitmq rabbitmqctl import_definitions /tmp/rabbitmq.json
```

### 10.3 Key Backup

```bash
# Backup keys
tar -czf sentinel-keys-backup.tar.gz -C /etc/sentinel conductor_private.pem conductor_public.pem

# Restore keys
tar -xzf sentinel-keys-backup.tar.gz -C /etc/sentinel
```

---

## 11. Security

### 11.1 Invariants

1. **Default credentials MUST be changed** before production
2. **TLS MUST be enabled** for MCP API and Admin API in production
3. **Private key MUST NOT be distributed** to executors
4. **Public key MUST be distributed** to all executors
5. **Secrets MUST NOT be committed** to version control
6. **Audit log MUST be backed up** regularly
7. **Executor MUST NOT have database access**
8. **Executor MUST NOT have RabbitMQ management access**

### 11.2 Network Security

- Control Plane services SHOULD be on a private network
- Executor only needs outbound access to RabbitMQ (port 5672)
- MCP API and Admin API SHOULD be behind a reverse proxy with TLS
- Database SHOULD NOT be exposed to the internet

### 11.3 Secret Management

Use a secret manager (Vault, AWS Secrets Manager, etc.):

```bash
# Example: HashiCorp Vault
vault kv put secret/sentinel \
  admin_password=STRONG_PASSWORD \
  rabbitmq_password=STRONG_PASSWORD \
  postgres_password=STRONG_PASSWORD \
  mcp_api_key=STRONG_KEY \
  admin_api_secret=STRONG_SECRET
```

---

## 12. Troubleshooting

### 12.1 Common Issues

| Issue | Cause | Solution |
|---|---|---|
| Executor not connecting | Wrong Control Plane URL | Check `control_plane.url` |
| Executor not verifying | Missing public key | Check `conductor_public_key_path` |
| Conductor not starting | Missing private key | Run `keygen` service |
| Database connection failed | Wrong credentials | Check `[database] connection` |
| RabbitMQ connection failed | Wrong credentials | Check `[messaging] transport_url` |
| 2FA not working | Wrong bot token | Check `[telegram] bot_token` |

### 12.2 Debug Mode

```ini
[DEFAULT]
debug = true
log_level = DEBUG
```

### 12.3 Log Locations

| Component | Log Location |
|---|---|
| Docker | `docker compose logs <service>` |
| systemd | `journalctl -u sentinel-executor` |
| File | `/var/log/sentinel/` |

---

## 13. Definition of Done

Deployment v1 is complete when:

1. Docker Compose works for development
2. Production checklist is documented
3. Executor installation works via script
4. Ansible playbook works
5. Configuration is documented
6. Key management is documented
7. Monitoring is documented
8. Backup and recovery is documented
9. Security checklist is documented
10. Troubleshooting guide is documented
