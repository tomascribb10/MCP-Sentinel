from oslo_config import cfg

target_group = cfg.OptGroup(name="target", title="sentinel-target options")

target_opts = [
    cfg.StrOpt(
        "target_id",
        default=None,
        help=(
            "Unique identifier for this target instance. "
            "Defaults to the system hostname if not set."
        ),
    ),
    cfg.StrOpt(
        "mode",
        default="direct",
        help=(
            "Operating mode: 'direct' (execute commands locally) or "
            "'gateway' (proxy execution to managed remote targets)."
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
        help="List of stevedore driver names this target is allowed to load.",
    ),
    cfg.IntOpt(
        "execution_timeout_seconds",
        default=300,
        help="Hard timeout for any single command execution.",
    ),
]

gateway_group = cfg.OptGroup(name="gateway", title="sentinel-target gateway mode options")

gateway_opts = [
    cfg.StrOpt(
        "managed_targets_config",
        default="/etc/sentinel/managed_targets.json",
        help=(
            "Path to JSON file listing the remote targets this gateway manages. "
            "Only used when [target] mode = gateway."
        ),
    ),
]
