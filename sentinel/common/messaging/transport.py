"""
common.messaging.transport
===========================
oslo.messaging transport singleton helpers.

Components call ``get_transport()`` once at startup and reuse the
returned object for the lifetime of the process.  The transport is
constructed from the ``[messaging] transport_url`` oslo.config option.

Usage::

    from common.messaging.transport import get_transport

    transport = get_transport(CONF)
"""

import threading
from typing import TYPE_CHECKING

import oslo_messaging

if TYPE_CHECKING:
    from oslo_config import cfg

_transport: oslo_messaging.Transport | None = None
_transport_lock = threading.Lock()


def get_transport(conf: "cfg.ConfigOpts", *, url: str | None = None) -> oslo_messaging.Transport:
    """
    Return the process-level oslo.messaging RPC transport.

    Thread-safe singleton — initialised once and cached.

    Args:
        conf:  oslo.config CONF object (must have [messaging] group registered).
        url:   Override transport URL.  Defaults to conf.messaging.transport_url.
    """
    global _transport
    if _transport is not None:
        return _transport

    with _transport_lock:
        if _transport is None:
            transport_url = url or conf.messaging.transport_url
            _transport = oslo_messaging.get_rpc_transport(
                conf,
                url=transport_url,
            )
    return _transport


def get_notification_transport(
    conf: "cfg.ConfigOpts", *, url: str | None = None
) -> oslo_messaging.Transport:
    """
    Return a transport suitable for oslo.messaging Notifier (CADF audit events).

    Kept separate from the RPC transport so notification fanout can be
    routed to a different exchange without affecting RPC traffic.
    """
    transport_url = url or conf.messaging.transport_url
    return oslo_messaging.get_notification_transport(conf, url=transport_url)


def reset_transport() -> None:
    """
    Reset the cached transport.  Intended for use in tests only.
    """
    global _transport
    with _transport_lock:
        _transport = None
