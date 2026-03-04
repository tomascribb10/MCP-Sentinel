#!/usr/bin/env bash
# =============================================================================
# MCP-Sentinel — Agent Installer
# =============================================================================
#
# Installs or upgrades sentinel-agent as a systemd service on a Linux host.
# Uses an isolated Python venv so it never touches system packages.
#
# REQUIREMENTS
#   - Linux with systemd
#   - Python 3.10+ (python3 / python3.10 / python3.11 / python3.12)
#   - pip
#   - Root / sudo
#
# USAGE
#   # From the repo root, as root or via sudo:
#   sudo bash scripts/install-agent.sh [OPTIONS]
#
# OPTIONS
#   --source-dir DIR    Path to the repo root (default: directory of this script)
#   --install-dir DIR   Venv + binary install location (default: /opt/sentinel-agent)
#   --config-dir DIR    Config + key storage (default: /etc/sentinel)
#   --log-dir DIR       Log directory (default: /var/log/sentinel)
#   --user USER         Service OS user (default: sentinel-agent; created if absent)
#   --uninstall         Stop service, remove venv and systemd unit (keeps config)
#   --help              Show this message
#
# POST-INSTALL STEPS (fresh install)
#   1. Edit /etc/sentinel/sentinel-agent.conf
#      - Set the RabbitMQ URL (transport_url)
#      - Optionally override agent_id (defaults to hostname)
#   2. Copy the conductor public key:
#        scp <control-plane>:/etc/sentinel/conductor_public.pem \
#            /etc/sentinel/conductor_public.pem
#   3. Start the service:
#        systemctl start sentinel-agent
#        journalctl -fu sentinel-agent
#
# UPGRADE
#   Re-run the script — it detects an existing install, upgrades the venv,
#   reloads the systemd unit and restarts the service if it was running.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"   # repo root (one level up from scripts/)
INSTALL_DIR="/opt/sentinel-agent"
CONFIG_DIR="/etc/sentinel"
LOG_DIR="/var/log/sentinel"
SERVICE_USER="sentinel-agent"
SERVICE_NAME="sentinel-agent"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SUDOERS_FILE="/etc/sudoers.d/${SERVICE_NAME}"
DO_UNINSTALL=false

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[0;33m'
BLU='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()      { echo -e "${GRN}[ OK ]${NC}  $*"; }
warn()    { echo -e "${YLW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR ]${NC}  $*" >&2; }
die()     { error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        --source-dir)  SOURCE_DIR="$2";  shift 2 ;;
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        --config-dir)  CONFIG_DIR="$2";  shift 2 ;;
        --log-dir)     LOG_DIR="$2";     shift 2 ;;
        --user)        SERVICE_USER="$2"; shift 2 ;;
        --uninstall)   DO_UNINSTALL=true; shift ;;
        --help|-h)
            sed -n '/^# USAGE/,/^# ===/p' "$0" | head -n -1 | sed 's/^# \?//'
            exit 0
            ;;
        *) die "Unknown option: $1 (use --help)" ;;
    esac
done

VENV_DIR="${INSTALL_DIR}/venv"
SENTINEL_BIN="${VENV_DIR}/bin/sentinel-agent"
SOURCE_PKG="${SOURCE_DIR}/sentinel"          # directory with setup.cfg
REQ_AGENT="${SOURCE_PKG}/requirements.agent.txt"

# ---------------------------------------------------------------------------
# Root check
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    die "This script must be run as root. Try: sudo bash $0"
fi

# ---------------------------------------------------------------------------
# Uninstall path
# ---------------------------------------------------------------------------
if $DO_UNINSTALL; then
    info "Uninstalling sentinel-agent..."

    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        info "Stopping service..."
        systemctl stop "$SERVICE_NAME"
    fi
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        info "Disabling service..."
        systemctl disable "$SERVICE_NAME"
    fi
    [[ -f "$UNIT_FILE" ]]    && rm -f "$UNIT_FILE"    && info "Removed $UNIT_FILE"
    [[ -f "$SUDOERS_FILE" ]] && rm -f "$SUDOERS_FILE" && info "Removed $SUDOERS_FILE"
    systemctl daemon-reload

    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        ok "Removed $INSTALL_DIR"
    fi

    warn "Config at $CONFIG_DIR and logs at $LOG_DIR were NOT removed."
    warn "Remove them manually if desired: rm -rf $CONFIG_DIR $LOG_DIR"
    ok "Uninstall complete."
    exit 0
fi

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
info "Running preflight checks..."

# systemd
command -v systemctl &>/dev/null || die "systemd not found — this installer requires systemd."

# Source package
[[ -f "${SOURCE_PKG}/setup.cfg" ]] \
    || die "Cannot find setup.cfg in ${SOURCE_PKG}. Run from repo root or use --source-dir."
[[ -f "$REQ_AGENT" ]] \
    || die "Cannot find requirements.agent.txt in ${SOURCE_PKG}."

# Python 3.10+
PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c 'import sys; print(sys.version_info[:2] >= (3,10))')
        if [[ "$ver" == "True" ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done
[[ -n "$PYTHON" ]] || die "Python 3.10+ is required but not found. Install it first."
ok "Using Python: $($PYTHON --version)"

# pip / venv module
"$PYTHON" -m pip --version &>/dev/null \
    || die "pip not available for $PYTHON. Install: sudo apt-get install python3-pip"
"$PYTHON" -c "import venv" &>/dev/null \
    || die "venv module not available. Install: sudo apt-get install python3-venv"

ok "Preflight OK"

# ---------------------------------------------------------------------------
# Detect fresh install vs upgrade
# ---------------------------------------------------------------------------
IS_UPGRADE=false
if [[ -x "$SENTINEL_BIN" ]]; then
    IS_UPGRADE=true
    warn "Existing installation detected — performing upgrade."
fi

# Was the service running before upgrade? We'll restart it afterward.
WAS_RUNNING=false
if $IS_UPGRADE && systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    WAS_RUNNING=true
    info "Service is currently running — will restart after upgrade."
fi

# ---------------------------------------------------------------------------
# Create system user
# ---------------------------------------------------------------------------
if ! id "$SERVICE_USER" &>/dev/null; then
    info "Creating system user: $SERVICE_USER"
    useradd \
        --system \
        --no-create-home \
        --shell /sbin/nologin \
        --comment "MCP-Sentinel Agent" \
        "$SERVICE_USER"

    # Add to 'adm' group so the agent can read /var/log/syslog etc.
    if getent group adm &>/dev/null; then
        usermod -aG adm "$SERVICE_USER"
        info "Added $SERVICE_USER to group 'adm' (log file read access)"
    fi
    # Add to 'systemd-journal' for journalctl access (optional)
    if getent group systemd-journal &>/dev/null; then
        usermod -aG systemd-journal "$SERVICE_USER"
    fi
    ok "User $SERVICE_USER created"
else
    ok "User $SERVICE_USER already exists"
fi

# ---------------------------------------------------------------------------
# Sudoers rule — privilege escalation for whitelisted binaries
# ---------------------------------------------------------------------------
info "Installing sudoers rule: $SUDOERS_FILE"
cat > "$SUDOERS_FILE" <<EOF
# MCP-Sentinel agent — controlled privilege escalation for whitelisted binaries.
# Argument restrictions are enforced by Conductor RBAC engine + driver args_regex.
# This file is managed by scripts/install-agent.sh — do not edit manually.
Defaults!SENTINEL_CMDS !requiretty, !pam_session
Cmnd_Alias SENTINEL_CMDS = /usr/bin/systemctl, /usr/bin/kill, /usr/bin/renice, /usr/sbin/zpool, /usr/sbin/zfs
${SERVICE_USER} ALL=(root) NOPASSWD: SENTINEL_CMDS
EOF
chmod 0440 "$SUDOERS_FILE"
if visudo -c -f "$SUDOERS_FILE" &>/dev/null; then
    ok "Sudoers rule installed"
else
    rm -f "$SUDOERS_FILE"
    die "Generated sudoers file failed visudo validation — removed. Check /etc/sudoers.d/ manually."
fi

# ---------------------------------------------------------------------------
# Create directories
# ---------------------------------------------------------------------------
info "Creating directories..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR"

# Agent owns only its log dir; config dir is root-owned (keys/configs sensitive)
chown root:${SERVICE_USER} "$CONFIG_DIR"
chmod 750 "$CONFIG_DIR"
chown "${SERVICE_USER}:${SERVICE_USER}" "$LOG_DIR"
chmod 750 "$LOG_DIR"
ok "Directories ready"

# ---------------------------------------------------------------------------
# Create / update venv
# ---------------------------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating Python venv at $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
    ok "Venv created"
else
    ok "Venv already exists — upgrading packages"
fi

# On Debian/Ubuntu, python3-venv may not create a 'pip' wrapper but does
# create 'pip3' or 'pip3.x'.  Find whichever is available.
PIP=""
for _candidate in pip pip3 pip3.12 pip3.11 pip3.10; do
    if [[ -x "${VENV_DIR}/bin/${_candidate}" ]]; then
        PIP="${VENV_DIR}/bin/${_candidate}"
        break
    fi
done
[[ -n "$PIP" ]] || die "No pip binary found in venv (tried pip, pip3, pip3.12/11/10).
  Install the required package and retry:
    sudo apt-get install python3-pip"

info "Upgrading pip inside venv..."
"$PIP" install --quiet --upgrade pip

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------
info "Installing agent dependencies from ${REQ_AGENT} ..."
"$PIP" install --quiet -r "$REQ_AGENT"
ok "Dependencies installed"

info "Installing mcp-sentinel package (without pulling redundant deps)..."
# --no-deps: deps already installed above; we just need the entry points
# registered so 'sentinel-agent' console_script is available in the venv.
"$PIP" install --quiet --no-deps "$SOURCE_PKG"
ok "Package installed — $(${VENV_DIR}/bin/sentinel-agent --version 2>/dev/null || echo 'OK')"

# Ensure the binary is owned by root and not writable by the service user
chown -R root:root "$INSTALL_DIR"
chmod 755 "${VENV_DIR}/bin/sentinel-agent"

# ---------------------------------------------------------------------------
# Config template (fresh install only — never overwrite existing config)
# ---------------------------------------------------------------------------
CONF_FILE="${CONFIG_DIR}/sentinel-agent.conf"
CONF_EXAMPLE="${SOURCE_DIR}/config/sentinel.agent-host.conf.example"

if [[ ! -f "$CONF_FILE" ]]; then
    if [[ -f "$CONF_EXAMPLE" ]]; then
        cp "$CONF_EXAMPLE" "$CONF_FILE"
        chmod 640 "$CONF_FILE"
        chown "root:${SERVICE_USER}" "$CONF_FILE"
        warn "Config template written to $CONF_FILE"
        warn ">>> Edit $CONF_FILE before starting the service! <<<"
    else
        warn "Config example not found at $CONF_EXAMPLE"
        warn "Create $CONF_FILE manually (see config/sentinel.agent-host.conf.example)"
    fi
else
    ok "Config file already exists — not overwritten"
fi

# ---------------------------------------------------------------------------
# Key placeholder reminder
# ---------------------------------------------------------------------------
KEY_FILE="${CONFIG_DIR}/conductor_public.pem"
if [[ ! -f "$KEY_FILE" ]]; then
    warn "Conductor public key not found at $KEY_FILE"
    warn "Copy it from the control-plane host before starting:"
    warn "  scp <control-plane>:/etc/sentinel/conductor_public.pem $KEY_FILE"
    warn "Or extract from a local Docker volume:"
    warn "  docker run --rm -v sentinel_sentinel-keys:/k alpine \\"
    warn "    cat /k/conductor_public.pem > $KEY_FILE"
fi

# ---------------------------------------------------------------------------
# systemd unit file
# ---------------------------------------------------------------------------
info "Writing systemd unit file: $UNIT_FILE"

cat > "$UNIT_FILE" << EOF
[Unit]
Description=MCP-Sentinel Agent
Documentation=https://github.com/anthropics/mcp-sentinel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}

ExecStart=${VENV_DIR}/bin/sentinel-agent
Environment=SENTINEL_CONF=${CONF_FILE}

# Restart on any non-zero exit; back off up to 5 minutes between retries.
Restart=on-failure
RestartSec=10
RestartSteps=6
RestartMaxDelaySec=300

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=sentinel-agent

# --- Security hardening ---
# The agent must be able to spawn privileged commands (ps, systemctl, ss -p …).
# We therefore do NOT use ProtectSystem=strict or PrivateMounts, but we
# still apply a set of lightweight restrictions on the agent process itself.
NoNewPrivileges=false          # child processes (spawned commands) may need setuid
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=false   # some Python JIT paths require W+X pages
RestrictSUIDSGID=false         # spawned binaries may use setuid (e.g. ping, sudo)

# Capability whitelist:
#   CAP_NET_RAW    — lets the agent run ping(1) without root.
#   CAP_SETUID     — required for sudo to switch to UID 0.
#   CAP_SETGID     — required for sudo to switch to GID 0.
#   CAP_KILL       — lets sudo'd kill(1) send signals to other-user processes.
#   CAP_AUDIT_WRITE — suppresses sudo's "audit" warning on kernels with auditing enabled.
AmbientCapabilities=CAP_NET_RAW CAP_SETUID CAP_SETGID CAP_KILL CAP_AUDIT_WRITE
CapabilityBoundingSet=CAP_NET_RAW CAP_SETUID CAP_SETGID CAP_KILL CAP_AUDIT_WRITE

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$UNIT_FILE"
ok "Unit file written"

# ---------------------------------------------------------------------------
# Reload systemd and enable service
# ---------------------------------------------------------------------------
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
ok "Service enabled (will start on next boot)"

# ---------------------------------------------------------------------------
# Restart if upgrading and was running; print start instructions otherwise
# ---------------------------------------------------------------------------
if $IS_UPGRADE && $WAS_RUNNING; then
    info "Restarting service after upgrade..."
    systemctl restart "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        ok "Service restarted successfully"
    else
        error "Service failed to restart — check logs: journalctl -fu sentinel-agent"
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${GRN}========================================================${NC}"
if $IS_UPGRADE; then
    echo -e "${GRN}  sentinel-agent upgraded successfully!${NC}"
else
    echo -e "${GRN}  sentinel-agent installed successfully!${NC}"
fi
echo -e "${GRN}========================================================${NC}"
echo ""

if ! $IS_UPGRADE; then
    echo "Next steps:"
    echo ""
    echo "  1. Edit the config file:"
    echo "       $CONF_FILE"
    echo "     → Set transport_url to your RabbitMQ address"
    echo "     → Optionally set agent_id (default: hostname = $(hostname))"
    echo ""
    echo "  2. Place the conductor public key:"
    echo "       $KEY_FILE"
    echo ""
    echo "  3. Start the service:"
    echo "       systemctl start $SERVICE_NAME"
    echo "       journalctl -fu $SERVICE_NAME"
    echo ""
    echo "  Upgrade later by re-running:"
    echo "       sudo bash $0"
    echo ""
fi

echo "Useful commands:"
echo "  systemctl status  $SERVICE_NAME"
echo "  systemctl start   $SERVICE_NAME"
echo "  systemctl stop    $SERVICE_NAME"
echo "  systemctl restart $SERVICE_NAME"
echo "  journalctl -fu    $SERVICE_NAME"
echo ""
echo "Uninstall:"
echo "  sudo bash $0 --uninstall"
echo ""
