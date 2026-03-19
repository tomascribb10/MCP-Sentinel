from oslo_config import cfg

messaging_group = cfg.OptGroup(name="messaging", title="oslo.messaging / RabbitMQ options")

messaging_opts = [
    cfg.StrOpt(
        "transport_url",
        default="rabbit://sentinel:sentinel@localhost:5672/sentinel",
        help="oslo.messaging transport URL (RabbitMQ AMQP URI).",
        secret=True,
    ),
    cfg.StrOpt(
        "rpc_topic_conductor",
        default="sentinel.conductor",
        help="RPC topic for sentinel-conductor.",
    ),
    cfg.StrOpt(
        "rpc_topic_scheduler",
        default="sentinel.scheduler",
        help="RPC topic for sentinel-scheduler.",
    ),
    cfg.StrOpt(
        "target_queue_prefix",
        default="sentinel.target",
        help=(
            "Prefix for per-target queues. "
            "Final queue name: <prefix>.<target_id>"
        ),
    ),
    cfg.IntOpt(
        "rpc_timeout",
        default=60,
        help="Default timeout in seconds for synchronous RPC calls.",
    ),
]
