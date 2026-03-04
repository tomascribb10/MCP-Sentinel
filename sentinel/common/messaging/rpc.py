"""
common.messaging.rpc
=====================
Factory helpers for oslo.messaging RPC clients and servers.

Design decisions
----------------
* All RPC methods use oslo.messaging's **call** (synchronous, awaits reply)
  or **cast** (fire-and-forget) patterns.

* The conductor uses ``call`` to wait for the agent's ExecutionResult.
  The scheduler uses ``cast`` for heartbeat updates (no reply needed).

* ``get_rpc_server`` wraps oslo.messaging's ``get_rpc_server`` with
  sensible defaults for the executor and access policy.

Typical usage (conductor RPC server)::

    from common.messaging.rpc import get_rpc_server
    from common.messaging.transport import get_transport

    transport = get_transport(CONF)
    endpoints  = [ConductorRPCEndpoint()]
    server = get_rpc_server(
        transport,
        topic=CONF.messaging.rpc_topic_conductor,
        server="conductor-1",
        endpoints=endpoints,
    )
    server.start()

Typical usage (mcp-api RPC client calling conductor)::

    from common.messaging.rpc import get_rpc_client
    from common.messaging.transport import get_transport

    transport = get_transport(CONF)
    client = get_rpc_client(
        transport,
        topic=CONF.messaging.rpc_topic_conductor,
        version="1.0",
    )
    result = client.call(ctxt, "request_execution", request=payload_dict)
"""

from typing import Any

import oslo_messaging
from oslo_messaging import RPCClient, Target


# -----------------------------------------------------------------------
# RPC API version — bump minor on backwards-compatible additions,
# major on breaking changes.
# -----------------------------------------------------------------------
RPC_API_VERSION = "1.0"


def get_rpc_client(
    transport: oslo_messaging.Transport,
    topic: str,
    *,
    server: str | None = None,
    version: str = RPC_API_VERSION,
    timeout: int | None = None,
) -> RPCClient:
    """
    Create an oslo.messaging RPCClient for the given topic.

    Args:
        transport: Initialised transport (from ``get_transport()``).
        topic:     RPC topic (e.g. ``sentinel.conductor``).
        server:    Optional server name to target a specific instance.
        version:   Minimum RPC API version expected on the server side.
        timeout:   Call timeout in seconds.  Uses transport default if None.

    Returns:
        oslo_messaging.RPCClient ready to ``.call()`` or ``.cast()``.
    """
    target = Target(topic=topic, server=server, version=version)
    return RPCClient(transport, target, timeout=timeout)


def get_rpc_server(
    transport: oslo_messaging.Transport,
    topic: str,
    endpoints: list[Any],
    *,
    server: str = "default",
    executor: str = "threading",
) -> oslo_messaging.MessageHandlingServer:
    """
    Create an oslo.messaging RPC server.

    Args:
        transport:  Initialised transport.
        topic:      RPC topic this server will consume from.
        endpoints:  List of endpoint objects whose public methods become
                    callable RPC methods.
        server:     Server name — used to form the unique queue name.
        executor:   oslo.messaging executor type.  ``"threading"`` is the
                    safe default for synchronous (oslo.db) code paths.
                    Use ``"eventlet"`` only if the whole stack uses eventlet.

    Returns:
        MessageHandlingServer — call ``.start()`` to begin consuming.
    """
    target = Target(topic=topic, server=server)
    access_policy = oslo_messaging.DefaultRPCAccessPolicy

    return oslo_messaging.get_rpc_server(
        transport,
        target,
        endpoints,
        executor=executor,
        access_policy=access_policy,
    )


def get_fanout_client(
    transport: oslo_messaging.Transport,
    topic: str,
    *,
    version: str = RPC_API_VERSION,
) -> RPCClient:
    """
    Create a fanout RPCClient that broadcasts a ``cast`` to ALL consumers
    on the given topic (e.g. broadcasting to all agents).

    Note: fanout only supports ``cast`` (fire-and-forget) — never ``call``.
    """
    target = Target(topic=topic, fanout=True, version=version)
    return RPCClient(transport, target)
