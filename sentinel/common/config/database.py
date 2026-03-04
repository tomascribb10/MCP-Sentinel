from oslo_config import cfg

database_group = cfg.OptGroup(name="database", title="Database options")

database_opts = [
    cfg.StrOpt(
        "connection",
        default="postgresql+psycopg2://sentinel:sentinel@localhost:5432/sentinel",
        help="SQLAlchemy connection string for the central database.",
        secret=True,
    ),
    cfg.IntOpt(
        "pool_size",
        default=10,
        help="Number of connections to keep in the SQLAlchemy connection pool.",
    ),
    cfg.IntOpt(
        "max_overflow",
        default=20,
        help="Maximum number of connections that can be opened beyond pool_size.",
    ),
    cfg.BoolOpt(
        "echo",
        default=False,
        help="Log all SQL statements (development only).",
    ),
]
