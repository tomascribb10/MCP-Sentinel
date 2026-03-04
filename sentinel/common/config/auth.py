from oslo_config import cfg

auth_group = cfg.OptGroup(name="auth", title="2FA authentication options")

auth_opts = [
    cfg.StrOpt(
        "provider",
        default="stub",
        choices=["telegram", "stub"],
        help="Stevedore name of the 2FA provider plugin to load.",
    ),
    cfg.StrOpt(
        "admin_api_secret_key",
        default="change-me-in-production",
        help="Secret key for signing Admin API JWT tokens.",
        secret=True,
    ),
    cfg.IntOpt(
        "admin_api_token_ttl_minutes",
        default=60,
        help="Lifetime in minutes of Admin API JWT access tokens.",
    ),
    cfg.StrOpt(
        "mcp_api_secret_key",
        default="change-me-in-production",
        help=(
            "Shared API key for MCP API clients (AI agents). "
            "Clients must send 'Authorization: Bearer <key>' on every request. "
            "Set to a strong random string in production (e.g. openssl rand -hex 32)."
        ),
        secret=True,
    ),
]

# -----------------------------------------------------------------------
# Telegram-specific options (only used when provider = telegram)
# -----------------------------------------------------------------------
telegram_group = cfg.OptGroup(name="telegram", title="Telegram Bot 2FA provider options")

telegram_opts = [
    cfg.StrOpt(
        "bot_token",
        default=None,
        help="Telegram Bot API token obtained from @BotFather.",
        secret=True,
    ),
    cfg.StrOpt(
        "approver_chat_id",
        default=None,
        help=(
            "Telegram chat_id of the human approver. "
            "Can be a personal chat, a group, or a channel."
        ),
    ),
    cfg.IntOpt(
        "polling_interval_seconds",
        default=5,
        help="Interval in seconds to poll Telegram for callback query responses.",
    ),
]
