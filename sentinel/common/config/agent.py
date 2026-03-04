from oslo_config import cfg

agent_group = cfg.OptGroup(name="agent", title="sentinel-agent options")

agent_opts = [
    cfg.StrOpt(
        "agent_id",
        default=None,
        help=(
            "Unique identifier for this agent instance. "
            "Defaults to the system hostname if not set."
        ),
    ),
    cfg.StrOpt(
        "conductor_public_key_path",
        default="/etc/sentinel/conductor_public.pem",
        help="Path to the RSA public key of sentinel-conductor for payload verification.",
    ),
    cfg.IntOpt(
        "heartbeat_interval_seconds",
        default=30,
        help="Interval in seconds between heartbeat messages sent to sentinel-scheduler.",
    ),
    cfg.ListOpt(
        "enabled_drivers",
        default=["posix_bash"],
        help="List of stevedore driver names this agent is allowed to load.",
    ),
    cfg.IntOpt(
        "execution_timeout_seconds",
        default=300,
        help="Hard timeout for any single command execution.",
    ),
]
