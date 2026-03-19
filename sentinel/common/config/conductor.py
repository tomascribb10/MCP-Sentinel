from oslo_config import cfg

conductor_group = cfg.OptGroup(name="conductor", title="sentinel-conductor options")

conductor_opts = [
    cfg.StrOpt(
        "private_key_path",
        default="/etc/sentinel/conductor_private.pem",
        help="Path to the RSA private key used to sign execution payloads.",
    ),
    cfg.StrOpt(
        "public_key_path",
        default="/etc/sentinel/conductor_public.pem",
        help=(
            "Path to the RSA public key distributed to sentinel-targets "
            "for payload signature verification."
        ),
    ),
    cfg.IntOpt(
        "rsa_key_bits",
        default=4096,
        help="RSA key size in bits used during key generation.",
    ),
    cfg.IntOpt(
        "twofa_challenge_timeout_seconds",
        default=300,
        help="Seconds before a pending 2FA challenge expires.",
    ),
    cfg.StrOpt(
        "workers",
        default="1",
        help="Number of RPC worker threads for the conductor service.",
    ),
]
