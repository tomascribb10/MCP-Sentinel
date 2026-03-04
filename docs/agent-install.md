# Installing sentinel-agent on a Host

`sentinel-agent` is a lightweight daemon that runs on each host you want to manage. It has **no listening network ports** — it only consumes its dedicated RabbitMQ queue and reports results back to the conductor.

The recommended way to install it on a real host is with the provided installer script, which creates an isolated Python venv and registers the agent as a systemd service.

---

## Prerequisites

- Linux with **systemd**
- **Python 3.10+** (`python3.10`, `python3.11`, or `python3.12`)
- `python3-pip` and `python3-venv`
- Root / `sudo` access
- Network access to port **5672** on the machine running RabbitMQ

```bash
# Verify Python version
python3 --version

# Install system dependencies (Debian / Ubuntu)
sudo apt-get install -y python3-pip python3-venv gcc libssl-dev libffi-dev
```

---

## Quick Install

### 1. Clone the repository on the target host

```bash
git clone https://github.com/your-org/sentinel.git
cd sentinel
```

Alternatively, copy the repository from another machine:

```bash
# From the machine that has the repo
scp -r /path/to/sentinel user@<TARGET-IP>:/opt/sentinel-src
```

### 2. Run the installer

```bash
sudo bash scripts/install-agent.sh
```

The installer:

- Creates the `sentinel-agent` system user (added to `adm` and `systemd-journal` groups)
- Creates a Python venv at `/opt/sentinel-agent/venv` with only the agent's dependencies (no FastAPI, SQLAlchemy, Telegram, etc.)
- Copies the config template to `/etc/sentinel/sentinel-agent.conf`
- Writes `/etc/systemd/system/sentinel-agent.service` and enables it

### 3. Edit the configuration

```bash
sudo nano /etc/sentinel/sentinel-agent.conf
```

Replace `CONTROL_PLANE_HOST` with the IP or hostname of the machine running the sentinel stack:

```ini
[messaging]
transport_url = rabbit://sentinel:sentinel@192.168.1.100:5672/sentinel
```

Leave `agent_id` unset — it defaults to the machine's hostname, which gives you a stable, meaningful identifier.

### 4. Copy the conductor public key

The agent verifies the RSA-SHA256 signature of every payload before executing anything. It needs the conductor's public key.

**Option A — SCP from the control-plane host:**

```bash
scp root@<CONTROL-PLANE-HOST>:/etc/sentinel/conductor_public.pem \
    /etc/sentinel/conductor_public.pem
```

**Option B — Extract from the Docker volume (if the control plane runs on this machine):**

```bash
docker run --rm -v sentinel_sentinel-keys:/keys alpine \
    cat /keys/conductor_public.pem \
    > /etc/sentinel/conductor_public.pem
```

Set correct permissions:

```bash
sudo chmod 640 /etc/sentinel/conductor_public.pem
sudo chown root:sentinel-agent /etc/sentinel/conductor_public.pem
```

### 5. Start the service

```bash
sudo systemctl start sentinel-agent
sudo journalctl -fu sentinel-agent
```

Expect output like:

```
INFO  sentinel_agent.main  Starting sentinel-agent agent_id='my-server'
INFO  sentinel_agent.main  Conductor public key loaded successfully
INFO  sentinel_agent.main  RPC server listening on topic='sentinel.agent' server='my-server'
INFO  sentinel_agent.main  Heartbeat thread started: agent_id='my-server' interval=30s
```

---

## Installer Options

```
sudo bash scripts/install-agent.sh [OPTIONS]

Options:
  --source-dir DIR    Path to the repo root (default: directory above scripts/)
  --install-dir DIR   Venv location (default: /opt/sentinel-agent)
  --config-dir DIR    Config / key directory (default: /etc/sentinel)
  --log-dir DIR       Log directory (default: /var/log/sentinel)
  --user USER         Service OS user (default: sentinel-agent)
  --uninstall         Stop + disable service, remove venv and unit (keeps config)
  --help              Show help
```

---

## Upgrading

Re-run the installer. It detects the existing installation, upgrades the venv, and restarts the service if it was running.

```bash
cd /path/to/repo
git pull
sudo bash scripts/install-agent.sh
```

---

## Uninstalling

```bash
sudo bash scripts/install-agent.sh --uninstall
```

This stops and disables the service, removes the venv and systemd unit.
Config at `/etc/sentinel/` and logs at `/var/log/sentinel/` are **not removed** — delete them manually if desired.

---

## Verifying Registration

Once the agent is running, verify it appears in the system from the machine where the CLI is installed:

```bash
sentinel host list
```

The agent shows up with `status=active` within the first heartbeat interval (default: 30 seconds).

---

## Granting Access

After the agent registers, assign it to a group and create a policy so an AI agent can send it commands:

```bash
# Find the agent's ID
sentinel host list

# Create a group and add the agent
sentinel group create my-servers
sentinel group member add <GROUP_ID> <AGENT_ID>

# Use a built-in command set (seeded automatically on conductor startup when
# SENTINEL_SEED_DEFAULTS=true) or create your own
sentinel commandset list

# Bind the command set to the group for a given AI agent identity
sentinel policy create llm-agent-claude <COMMANDSET_ID> --target-group <GROUP_ID>

# Verify
sentinel audit log list --agent <AGENT_ID> --limit 20
```

---

## Service Management

```bash
systemctl status  sentinel-agent   # Current status
systemctl start   sentinel-agent   # Start
systemctl stop    sentinel-agent   # Stop
systemctl restart sentinel-agent   # Restart
journalctl -fu    sentinel-agent   # Live logs
```

---

## Security Notes

- The agent **never opens listening sockets** — all communication is outbound to RabbitMQ.
- **Every payload is RSA-SHA256 verified** before execution. A payload with an invalid or missing signature is silently discarded.
- The agent runs as the unprivileged `sentinel-agent` user. If a command requires elevated privileges (e.g. `systemctl restart`), configure `sudo` or polkit rules for that specific binary — do not run the agent as root.
- `AmbientCapabilities=CAP_NET_RAW` is set in the systemd unit to allow `ping` to work as a non-root user. Remove it if not needed.

---

## Manual Installation (advanced)

If you prefer full control without the installer script:

```bash
# 1. Create user
sudo useradd --system --no-create-home --shell /sbin/nologin sentinel-agent

# 2. Create venv with agent-only dependencies
python3 -m venv /opt/sentinel-agent/venv
/opt/sentinel-agent/venv/bin/pip install -r sentinel/requirements.agent.txt
/opt/sentinel-agent/venv/bin/pip install --no-deps ./sentinel/

# 3. Write config and copy public key (see above)

# 4. Write /etc/systemd/system/sentinel-agent.service
#    (see scripts/install-agent.sh for the full unit template)

# 5. Enable and start
systemctl daemon-reload
systemctl enable --now sentinel-agent
```
