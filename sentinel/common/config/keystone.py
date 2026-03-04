from oslo_config import cfg

keystone_group = cfg.OptGroup(
    name="keystone",
    title="Optional OpenStack Keystone integration",
)

keystone_opts = [
    cfg.StrOpt(
        "auth_url",
        default=None,
        help=(
            "Keystone auth URL (e.g. http://keystone:5000/v3). "
            "Leave empty to disable Keystone integration and use "
            "the built-in local auth for the Admin API."
        ),
    ),
    cfg.StrOpt(
        "project_name",
        default="sentinel",
        help="OpenStack project name for service account authentication.",
    ),
    cfg.StrOpt(
        "username",
        default="sentinel",
        help="OpenStack username for sentinel service account.",
    ),
    cfg.StrOpt(
        "password",
        default=None,
        help="OpenStack password for sentinel service account.",
        secret=True,
    ),
    cfg.StrOpt(
        "user_domain_name",
        default="Default",
        help="Keystone user domain name.",
    ),
    cfg.StrOpt(
        "project_domain_name",
        default="Default",
        help="Keystone project domain name.",
    ),
]
