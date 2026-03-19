"""
sentinel_admin_api.main
========================
FastAPI service entry point for sentinel-admin-api.

Exposes a RESTful API on port 8001 for human administrators.
All write operations are forwarded to sentinel-conductor via
oslo.messaging RPC (conductor is the sole DB writer).

Endpoints
---------
  POST   /auth/login
  GET    /auth/me
  GET    /targets
  GET    /targets/{id}
  PATCH  /targets/{id}
  DELETE /targets/{id}
  GET    /targets/{id}/groups
  GET    /gateways
  GET    /gateways/{id}
  GET    /groups
  POST   /groups
  GET    /groups/{id}
  PATCH  /groups/{id}
  DELETE /groups/{id}
  GET    /groups/{id}/members
  POST   /groups/{id}/members
  DELETE /groups/{id}/members/{target_id}
  GET    /command-sets
  POST   /command-sets
  GET    /command-sets/{id}
  DELETE /command-sets/{id}
  POST   /command-sets/{id}/commands
  DELETE /command-sets/{id}/commands/{cmd_id}
  GET    /policies
  POST   /policies
  GET    /policies/{id}
  PATCH  /policies/{id}
  DELETE /policies/{id}
  GET    /audit-logs
  GET    /users              (superuser only)
  POST   /users              (superuser only)
  PATCH  /users/{id}         (superuser only)
  DELETE /users/{id}         (superuser only)
  GET    /health
"""

import logging
import os
import sys

import uvicorn
from fastapi import FastAPI
from oslo_config import cfg
from oslo_log import log as oslo_log

from common.config.auth import auth_group, auth_opts, telegram_group, telegram_opts
from common.config.messaging import messaging_group, messaging_opts
from common.messaging.rpc import get_rpc_client
from common.messaging.transport import get_transport
from sentinel_admin_api import deps
from sentinel_admin_api.routers import (
    targets, gateways, audit, auth, commandsets, groups, policies, users,
)

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

SERVICE_NAME = "sentinel-admin-api"
DEFAULT_PORT = 8001


def _register_opts() -> None:
    CONF.register_group(messaging_group)
    CONF.register_opts(messaging_opts, group=messaging_group)
    CONF.register_group(auth_group)
    CONF.register_opts(auth_opts, group=auth_group)
    CONF.register_group(telegram_group)
    CONF.register_opts(telegram_opts, group=telegram_group)


def create_app() -> FastAPI:
    app = FastAPI(
        title="MCP-Sentinel Admin API",
        description="RESTful API for human administrators of MCP-Sentinel.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Register all routers
    app.include_router(auth.router)
    app.include_router(targets.router)
    app.include_router(gateways.router)
    app.include_router(groups.router)
    app.include_router(commandsets.router)
    app.include_router(policies.router)
    app.include_router(audit.router)
    app.include_router(users.router)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "service": SERVICE_NAME}

    return app


def main() -> None:
    _register_opts()
    oslo_log.register_options(CONF)

    conf_file = os.environ.get("SENTINEL_CONF")
    default_files = [conf_file] if conf_file and os.path.exists(conf_file) else []
    CONF(
        args=sys.argv[1:],
        project=SERVICE_NAME,
        default_config_files=default_files,
    )

    oslo_log.setup(CONF, SERVICE_NAME)
    LOG.info("Starting %s", SERVICE_NAME)

    # Initialise oslo.messaging conductor client and inject into deps
    transport = get_transport(CONF)
    conductor_client = get_rpc_client(
        transport,
        topic=CONF.messaging.rpc_topic_conductor,
        timeout=CONF.messaging.rpc_timeout,
    )
    deps.set_conductor_client(conductor_client)
    deps.set_conf(CONF)

    app = create_app()

    LOG.info("Admin API listening on port %d", DEFAULT_PORT)
    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT, log_level="info")


if __name__ == "__main__":
    main()
