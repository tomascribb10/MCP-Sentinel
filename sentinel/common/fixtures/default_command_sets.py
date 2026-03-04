"""
common.fixtures.default_command_sets
======================================
Static definition of the six built-in command sets that are seeded
into every fresh MCP-Sentinel installation.

This module contains pure data — no DB access, no imports from the
rest of the stack.  The seeder (sentinel_conductor.seeder) reads
``DEFAULT_COMMAND_SETS`` and inserts the rows if they don't exist.

Command set structure mirrors the ORM models:
  {
    "name": str,
    "driver": str,
    "description": str,
    "commands": [
      {
        "name": str,
        "binary": str,
        "args_regex": str | None,
        "require_2fa": bool,
        "description": str | None,
        "allowed_paths": list[str] | None,
      },
      ...
    ],
  }
"""

DEFAULT_COMMAND_SETS: list[dict] = [
    # ------------------------------------------------------------------
    # 1. linux_diagnostics — read-only system info, no 2FA
    # ------------------------------------------------------------------
    {
        "name": "linux_diagnostics",
        "driver": "posix_bash",
        "description": "Read-only system diagnostics (uptime, disk, memory, processes).",
        "commands": [
            {
                "name": "uptime",
                "binary": "/usr/bin/uptime",
                "args_regex": r"^$",
                "require_2fa": False,
                "description": "Show system uptime.",
                "allowed_paths": None,
            },
            {
                "name": "disk_usage",
                "binary": "/usr/bin/df",
                "args_regex": r"^-hl?$",
                "require_2fa": False,
                "description": "Show disk usage in human-readable format.",
                "allowed_paths": None,
            },
            {
                "name": "memory_usage",
                "binary": "/usr/bin/free",
                "args_regex": r"^-h$",
                "require_2fa": False,
                "description": "Show memory usage in human-readable format.",
                "allowed_paths": None,
            },
            {
                "name": "running_processes",
                "binary": "/usr/bin/ps",
                "args_regex": r"^aux$",
                "require_2fa": False,
                "description": "List all running processes.",
                "allowed_paths": None,
            },
            {
                "name": "system_info",
                "binary": "/usr/bin/uname",
                "args_regex": r"^-a$",
                "require_2fa": False,
                "description": "Print all system information.",
                "allowed_paths": None,
            },
            {
                "name": "hostname",
                "binary": "/usr/bin/hostname",
                "args_regex": r"^(-f|-i|-s)?$",
                "require_2fa": False,
                "description": "Show hostname (FQDN, IP or short).",
                "allowed_paths": None,
            },
        ],
    },

    # ------------------------------------------------------------------
    # 2. log_reader — tail/grep logs under /var/log/, no 2FA
    # ------------------------------------------------------------------
    {
        "name": "log_reader",
        "driver": "posix_bash",
        "description": "Read log files under /var/log/. No 2FA required.",
        "commands": [
            {
                "name": "tail_log",
                "binary": "/usr/bin/tail",
                "args_regex": r"^-n \d{1,4} .+$",
                "require_2fa": False,
                "description": "Tail the last N lines of a log file.",
                "allowed_paths": ["/var/log/"],
            },
            {
                "name": "list_logs",
                "binary": "/usr/bin/ls",
                "args_regex": r"^-la? /var/log.*$",
                "require_2fa": False,
                "description": "List files in /var/log/.",
                "allowed_paths": ["/var/log/"],
            },
            {
                "name": "grep_logs",
                "binary": "/usr/bin/grep",
                "args_regex": r'^-E ".{1,200}" /var/log/.+$',
                "require_2fa": False,
                "description": "Search log files with an extended regex pattern.",
                "allowed_paths": ["/var/log/"],
            },
        ],
    },

    # ------------------------------------------------------------------
    # 3. service_management — systemctl status/list (no 2FA),
    #    restart/stop/start (2FA required)
    # ------------------------------------------------------------------
    {
        "name": "service_management",
        "driver": "posix_bash",
        "description": "Manage systemd services. Mutating actions require 2FA.",
        "commands": [
            {
                "name": "service_status",
                "binary": "/usr/bin/systemctl",
                "args_regex": r"^status [\w@.-]+(\.service)?$",
                "require_2fa": False,
                "description": "Show the status of a systemd service.",
                "allowed_paths": None,
            },
            {
                "name": "list_services",
                "binary": "/usr/bin/systemctl",
                "args_regex": r"^list-units( --type=service)?$",
                "require_2fa": False,
                "description": "List active systemd units (optionally filtered to services).",
                "allowed_paths": None,
            },
            {
                "name": "service_restart",
                "binary": "/usr/bin/systemctl",
                "args_regex": r"^restart [\w@.-]+(\.service)?$",
                "require_2fa": True,
                "require_sudo": True,
                "description": "Restart a systemd service (requires 2FA approval).",
                "allowed_paths": None,
            },
            {
                "name": "service_stop",
                "binary": "/usr/bin/systemctl",
                "args_regex": r"^stop [\w@.-]+(\.service)?$",
                "require_2fa": True,
                "require_sudo": True,
                "description": "Stop a systemd service (requires 2FA approval).",
                "allowed_paths": None,
            },
            {
                "name": "service_start",
                "binary": "/usr/bin/systemctl",
                "args_regex": r"^start [\w@.-]+(\.service)?$",
                "require_2fa": True,
                "require_sudo": True,
                "description": "Start a systemd service (requires 2FA approval).",
                "allowed_paths": None,
            },
        ],
    },

    # ------------------------------------------------------------------
    # 4. process_management — inspect (no 2FA), signal/renice (2FA)
    # ------------------------------------------------------------------
    {
        "name": "process_management",
        "driver": "posix_bash",
        "description": (
            "Inspect and signal OS processes. "
            "Kill and renice operations require 2FA approval."
        ),
        "commands": [
            {
                "name": "list_processes",
                "binary": "/usr/bin/ps",
                "args_regex": r"^aux$",
                "require_2fa": False,
                "description": "List all running processes (ps aux).",
                "allowed_paths": None,
            },
            {
                "name": "top_processes",
                "binary": "/usr/bin/ps",
                "args_regex": r"^-eo pid,ppid,user,%cpu,%mem,cmd --sort=-%(cpu|mem)$",
                "require_2fa": False,
                "description": "List processes sorted by CPU or memory usage.",
                "allowed_paths": None,
            },
            {
                "name": "search_process",
                "binary": "/usr/bin/pgrep",
                "args_regex": r"^-la? [\w][\w.-]{0,62}$",
                "require_2fa": False,
                "description": "Find processes by name with PID and full command line.",
                "allowed_paths": None,
            },
            {
                "name": "process_tree",
                "binary": "/usr/bin/pstree",
                "args_regex": r"^(-[apu]{1,3})?$",
                "require_2fa": False,
                "description": "Show process tree (flags: a=args, p=PIDs, u=user).",
                "allowed_paths": None,
            },
            {
                "name": "kill_process",
                "binary": "/usr/bin/kill",
                "args_regex": r"^-(?:TERM|15) \d+$",
                "require_2fa": True,
                "require_sudo": True,
                "description": "Send SIGTERM to a PID (graceful shutdown). Requires 2FA.",
                "allowed_paths": None,
            },
            {
                "name": "kill_process_force",
                "binary": "/usr/bin/kill",
                "args_regex": r"^-(?:KILL|9) \d+$",
                "require_2fa": True,
                "require_sudo": True,
                "description": "Send SIGKILL to a PID (forceful kill). Requires 2FA.",
                "allowed_paths": None,
            },
            {
                "name": "renice_process",
                "binary": "/usr/bin/renice",
                "args_regex": r"^-n -?(?:[0-9]|1[0-9]) -p \d+$",
                "require_2fa": True,
                "require_sudo": True,
                "description": "Adjust process priority (-19 to 19) by PID. Requires 2FA.",
                "allowed_paths": None,
            },
        ],
    },

    # ------------------------------------------------------------------
    # 5. zfs_storage — pool/dataset inspection (no 2FA),
    #    snapshot/rollback/destroy (2FA required)
    # ------------------------------------------------------------------
    {
        "name": "zfs_storage",
        "driver": "posix_bash",
        "description": (
            "ZFS pool and dataset management. "
            "Snapshot, rollback, and destroy operations require 2FA."
        ),
        "commands": [
            # --- Read-only ---
            {
                "name": "zpool_status",
                "binary": "/usr/sbin/zpool",
                "args_regex": r"^status( [\w.-]+)?$",
                "require_2fa": False,
                "description": "Show ZFS pool health and configuration.",
                "allowed_paths": None,
            },
            {
                "name": "zpool_list",
                "binary": "/usr/sbin/zpool",
                "args_regex": r"^list( [\w.-]+)?$",
                "require_2fa": False,
                "description": "List ZFS pools with size, usage and health.",
                "allowed_paths": None,
            },
            {
                "name": "zpool_iostat",
                "binary": "/usr/sbin/zpool",
                "args_regex": r"^iostat( -v)?( [\w.-]+)?$",
                "require_2fa": False,
                "description": "Show ZFS pool I/O statistics.",
                "allowed_paths": None,
            },
            {
                "name": "zfs_list",
                "binary": "/usr/sbin/zfs",
                "args_regex": r"^list( -r)?( [\w.-]+(/[\w.-]+)*)?$",
                "require_2fa": False,
                "description": "List ZFS datasets (optionally recursive).",
                "allowed_paths": None,
            },
            {
                "name": "zfs_list_snapshots",
                "binary": "/usr/sbin/zfs",
                "args_regex": r"^list -t snapshot( -r)?( [\w.-]+(/[\w.-]+)*)?$",
                "require_2fa": False,
                "description": "List ZFS snapshots (optionally recursive).",
                "allowed_paths": None,
            },
            {
                "name": "zfs_get",
                "binary": "/usr/sbin/zfs",
                "args_regex": r"^get [\w:,]+ [\w.-]+(/[\w.-]+)*$",
                "require_2fa": False,
                "description": "Get one or more ZFS dataset properties.",
                "allowed_paths": None,
            },
            {
                "name": "zpool_scrub",
                "binary": "/usr/sbin/zpool",
                "args_regex": r"^scrub( -s)? [\w.-]+$",
                "require_2fa": False,
                "require_sudo": True,
                "description": "Initiate (or stop with -s) a ZFS pool scrub.",
                "allowed_paths": None,
            },
            # --- Mutating (2FA + sudo required) ---
            {
                "name": "zfs_snapshot",
                "binary": "/usr/sbin/zfs",
                "args_regex": r"^snapshot [\w.-]+(/[\w.-]+)*@[\w.:-]+$",
                "require_2fa": True,
                "require_sudo": True,
                "description": "Create a ZFS snapshot (dataset@snapname). Requires 2FA.",
                "allowed_paths": None,
            },
            {
                "name": "zfs_rollback",
                "binary": "/usr/sbin/zfs",
                "args_regex": r"^rollback (-r )?[\w.-]+(/[\w.-]+)*@[\w.:-]+$",
                "require_2fa": True,
                "require_sudo": True,
                "description": (
                    "Roll back a dataset to a snapshot "
                    "(-r also destroys more-recent snapshots). Requires 2FA."
                ),
                "allowed_paths": None,
            },
            {
                "name": "zfs_destroy_snapshot",
                "binary": "/usr/sbin/zfs",
                "args_regex": r"^destroy [\w.-]+(/[\w.-]+)*@[\w.:-]+$",
                "require_2fa": True,
                "require_sudo": True,
                "description": (
                    "Destroy a ZFS snapshot. "
                    "Dataset-level destroy is intentionally not allowed. Requires 2FA."
                ),
                "allowed_paths": None,
            },
        ],
    },

    # ------------------------------------------------------------------
    # 6. network_diagnostics — ping, ss, dig, ip — no 2FA
    # ------------------------------------------------------------------
    {
        "name": "network_diagnostics",
        "driver": "posix_bash",
        "description": "Read-only network diagnostics (ping, ports, DNS, routing).",
        "commands": [
            {
                "name": "ping",
                "binary": "/usr/bin/ping",
                "args_regex": r"^-c [1-5] [\w.-]+$",
                "require_2fa": False,
                "description": "Ping a host up to 5 times.",
                "allowed_paths": None,
            },
            {
                "name": "open_ports",
                "binary": "/usr/bin/ss",
                "args_regex": r"^-tlnp$",
                "require_2fa": False,
                "description": "List listening TCP ports.",
                "allowed_paths": None,
            },
            {
                "name": "active_connections",
                "binary": "/usr/bin/ss",
                "args_regex": r"^-tnp$",
                "require_2fa": False,
                "description": "List active TCP connections.",
                "allowed_paths": None,
            },
            {
                "name": "dns_lookup",
                "binary": "/usr/bin/dig",
                "args_regex": r"^[\w.-]+( (A|AAAA|MX|NS|TXT|CNAME))?$",
                "require_2fa": False,
                "description": "DNS lookup for a hostname (optionally specify record type).",
                "allowed_paths": None,
            },
            {
                "name": "ip_info",
                "binary": "/usr/bin/ip",
                "args_regex": r"^(addr|link|route)( show)?$",
                "require_2fa": False,
                "description": "Show IP address, link, or routing information.",
                "allowed_paths": None,
            },
        ],
    },
]
