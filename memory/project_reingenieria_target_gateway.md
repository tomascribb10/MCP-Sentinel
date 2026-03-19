---
name: Re-ingeniería agent→target+gateway
description: Major architectural rename completed 2026-03-19 — sentinel-agent → sentinel-target, plus new Gateway concept for proxy targets
type: project
---

On 2026-03-19, a full re-engineering was completed:

**Rename:** `sentinel-agent` → `sentinel-target` everywhere (package, models, schemas, config, DB, API, CLI, Docker, scripts).

**New concept — Gateway:** A sentinel-target running in `mode=gateway` that manages remote targets (switches, appliances) that cannot run sentinel themselves. The gateway registers and proxies execution for managed targets.

**Key naming decisions (for future consistency):**
- `target_id` (not `agent_id`) everywhere
- Config group `[target]` (not `[agent]`), option `target_id`, `target_queue_prefix`
- DB tables: `targets`, `gateways`, `target_group_memberships`
- Stevedore namespace: `sentinel.target.drivers`
- RabbitMQ queue prefix: `sentinel.target`
- REST API: `/targets`, `/gateways`
- Console script: `sentinel-target`
- Exceptions: `TargetNotFound`, `TargetNotInGroup`, `TargetUnreachable`
- Scheduler RPC methods: `target_heartbeat`, `list_targets`, `dispatch`
- Conductor RPC methods: `list_targets`, `get_target`, `update_target`, `delete_target`, `update_target_status`, `add_target_to_group`, `remove_target_from_group`, `list_gateways`, `get_gateway`, `update_gateway_status`

**New fields on Target model:**
- `target_type`: `direct` | `gateway_managed`
- `gateway_id`: FK → gateways.id (null for direct targets)

**Gateway registration:** implicit via heartbeat (`target_heartbeat` for targets, `gateway_heartbeat` for gateways), same pattern as original agents.

**Why:** User requested the rename to better reflect that a "target" is the execution endpoint (local or remote), and a "gateway" is a passthrough service for devices that can't run sentinel natively.

**How to apply:** Always use the new terminology. Never introduce `agent_id`, `sentinel-agent`, `sentinel.agent.drivers`, or `[agent]` config group in new code.
