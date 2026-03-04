"""
common.config
=============
Centralised oslo.config option declarations for all MCP-Sentinel components.

Each component imports its own group from here and calls
``register_opts(CONF)`` before parsing the config file.
"""

from common.config.conductor import conductor_opts, conductor_group
from common.config.agent import agent_opts, agent_group
from common.config.database import database_opts, database_group
from common.config.messaging import messaging_opts, messaging_group
from common.config.auth import auth_opts, auth_group, telegram_opts, telegram_group
from common.config.keystone import keystone_opts, keystone_group

__all__ = [
    "conductor_opts", "conductor_group",
    "agent_opts", "agent_group",
    "database_opts", "database_group",
    "messaging_opts", "messaging_group",
    "auth_opts", "auth_group",
    "telegram_opts", "telegram_group",
    "keystone_opts", "keystone_group",
]
