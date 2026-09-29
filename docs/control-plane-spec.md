# MCP-Sentinel — Control Plane Specification

**Status:** Draft  
**Version:** 1.0.0-draft  
**Target:** sentinel-conductor, sentinel-scheduler, sentinel-mcp-api, sentinel-admin-api  
**Audience:** Control Plane developers, code-generation agents, security reviewers

Normative terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** define implementation requirements.

---

## 1. Purpose

This specification defines the Control Plane components of MCP-Sentinel v2.

> **The Control Plane authorizes capabilities. It does not execute them.**

The Control Plane is the **only trusted component** in the system. It owns:
- Identity and authentication
- RBAC/policy evaluation
- Capability catalog and lifecycle
- HITL (2FA) approval
- Request signing (RSA-SHA256)
- Audit logging

---

## 2. Components

| Component | Role | Port | Spec Reference |
|---|---|---|---|
| `sentinel-conductor` | RBAC, 2FA, RSA signing, audit (sole DB writer) | N/A (RPC) | This document |
| `sentinel-scheduler` | Executor registry, heartbeat, message routing | N/A (RPC) | This document |
| `sentinel-mcp-api` | MCP gateway (Streamable HTTP) | 8000 | This document |
| `sentinel-admin-api` | Admin REST API | 8001 | This document |

---

## 3. Architecture

### 3.1 Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                        CONTROL PLANE                             │
│                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │sentinel-mcp  │    │sentinel-conductor│    │sentinel-     │  │
│  │-api          │───▶│                  │◀───│scheduler     │  │
│  │(MCP Gateway) │    │ RBAC + 2FA +     │    │              │  │
│  └──────────────┘    │ RSA signing +    │    │ Heartbeat    │  │
│                      │ Audit logs       │    │ registry +   │  │
│  ┌──────────────┐    │                  │    │ router       │  │
│  │sentinel-     │───▶│ (only component  │    └──────────────┘  │
│  │admin-api     │    │  with DB access) │                      │
│  │(REST API)    │    └──────────────────┘                      │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ RabbitMQ (Protocol v2)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       EXECUTION PLANE                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ sentinel_executor  (one per target host)                 │  │
│  │                                                          │  │
│  │  1. Verify RSA signature                                 │  │
│  │  2. Validate arguments                                   │  │
│  │  3. Resolve provider from local registry                  │  │
│  │  4. Apply local constraints/limits                       │  │
│  │  5. Execute via SDK (no shell)                           │  │
│  │  6. Return signed result                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Trust Boundary

```text
┌─────────────────────────────────────────────────────────┐
│                    CONTROL PLANE                         │
│  (Trusted — owns authorization, signing, audit)          │
└─────────────────────────────────────────────────────────┘
                          │
                          │ Signed CapabilityRequest
                          │ (RabbitMQ — untrusted transport)
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    EXECUTOR                              │
│  (Semi-trusted — verifies request, executes locally)     │
└─────────────────────────────────────────────────────────┘
```

---

## 4. sentinel-conductor

### 4.1 Responsibilities

The Conductor is the **sole DB writer** and **policy decision point**. All other components access data through it via oslo.messaging RPC.

**Responsibilities:**
- RBAC evaluation (capability-centric)
- 2FA orchestration
- RSA-SHA256 request signing
- Audit logging (immutable)
- CRUD for all entities
- Capability catalog management

### 4.2 RBAC Engine (Capability-Centric)

#### 4.2.1 Authorization Flow

```text
Agent requests: service.status@1 on target spzfs27
  │
  ▼
1. Resolve target → get target's group memberships
  │
  ▼
2. Find active bindings where:
   - principal_id == agent_id
   - enabled == true
   - target_group_id IN target's groups
  │
  ▼
3. Expand Packs/Profiles to concrete capabilities
  │
  ▼
4. Find capability match:
   - capability.name == request.capability.name
   - capability.major_version == request.capability.major_version
  │
  ▼
5. Validate arguments against input schema
  │
  ▼
6. Apply effective constraints (intersection of all layers)
  │
  ▼
7. Check risk level → require HITL if needed
  │
  ▼
8. Return AuthorizationResult
```

#### 4.2.2 Authorization Result

```python
@dataclass
class AuthorizationResult:
    capability: Capability       # Resolved capability
    provider: str                # Selected provider
    decision_id: UUID            # Unique decision ID
    requires_2fa: bool          # Whether HITL is required
    effective_constraints: dict  # Merged constraints
    effective_limits: dict       # Merged limits
    bindings: list[Binding]      # All applicable bindings
```

#### 4.2.3 Denial Hierarchy

| Error | When |
|---|---|
| `TargetNotFound` | Target does not exist |
| `TargetNotInGroup` | Target has no group memberships |
| `PolicyDenied` | No active binding grants access |
| `CapabilityNotAllowed` | Capability not in any binding |
| `InvalidArguments` | Arguments fail input schema validation |
| `ConstraintViolation` | Arguments violate effective constraints |

### 4.3 2FA Flow

```text
Conductor receives CapabilityRequest
  │
  ├─ RBAC check passes, capability.risk.requires_2fa == True
  │
  ├─ _handle_2fa_required()
  │   ├─ Build ChallengeContext (principal, target, capability, arguments, request_id)
  │   ├─ Call auth_provider.issue_challenge(context) → returns challenge_id
  │   ├─ Create TwoFAChallenge record (status=PENDING, expires_at=now+timeout)
  │   ├─ Update AuditLog with twofa_provider, twofa_challenge_id
  │   ├─ Start _TwoFAPoller daemon thread
  │   └─ Return {"status": "pending_2fa", "challenge_id": ...}
  │
  ├─ _TwoFAPoller polls every N seconds:
  │   ├─ Check expiry → EXPIRED → AuditLog(FAILURE)
  │   ├─ Call auth_provider.verify_challenge(challenge_id, external_ref)
  │   │   ├─ APPROVED → sign_and_dispatch(), AuditLog(SUCCESS)
  │   │   ├─ REJECTED → AuditLog(DENIED)
  │   │   └─ PENDING → continue polling
  │   └─ On error → log and retry next tick
```

### 4.4 RSA Signing

#### 4.4.1 Algorithm

- **Algorithm:** RSA-SHA256
- **Key size:** 4096 bits
- **Padding:** PKCS#1 v1.5
- **Hash:** SHA-256

#### 4.4.2 Signature Payload

The signature is computed over the canonical JSON of the `CapabilityRequest` envelope **excluding** the `security.signature` field.

See `docs/protocol-v2-spec.md` sección 5 for canonical JSON rules.

#### 4.4.3 Key Configuration

| Option | Default | Description |
|---|---|---|
| `private_key_path` | `/etc/sentinel/conductor_private.pem` | RSA private key path |
| `public_key_path` | `/etc/sentinel/conductor_public.pem` | RSA public key path |
| `rsa_key_bits` | 4096 | RSA key size |

### 4.5 Audit Logging

#### 4.5.1 Audit Log Model

CADF-inspired format. **Immutable** — no update path.

| Field | Type | Description |
|---|---|---|
| `id` | UUID PK | Primary key |
| `request_id` | UUID | Request correlation ID |
| `decision_id` | UUID | Authorization decision ID |
| `policy_id` | UUID | Policy/binding ID |
| `principal_id` | str | Who made the request |
| `target_id` | str | Target identifier |
| `executor_id` | str | Executor that executed |
| `executor_instance_id` | str | Executor instance ID |
| `capability_id` | UUID | Capability ID |
| `capability_name` | str | Capability name |
| `capability_version` | str | Capability version |
| `provider_name` | str | Provider used |
| `provider_version` | str | Provider version |
| `risk_level` | str | Risk level |
| `approval_id` | str | 2FA approval ID |
| `approved_by` | str | Who approved |
| `arguments` | JSONB | Arguments (classified) |
| `arguments_hash` | str | SHA-256 hash of arguments |
| `effective_timeout_seconds` | int | Effective timeout |
| `effective_max_output_bytes` | int | Effective max output |
| `started_at` | timestamp | Execution start |
| `finished_at` | timestamp | Execution end |
| `duration_ms` | int | Duration |
| `success` | bool | Success or failure |
| `error_code` | str | Error code if failed |
| `result_size_bytes` | int | Result size |
| `output_truncated` | bool | Whether output was truncated |
| `executor_version` | str | Executor version |
| `created_at` | timestamp | Record creation |

#### 4.5.2 Audit Flow

1. **PENDING** — Created at start of `request_capability()`
2. **DENIED** — Set when RBAC denies the request
3. **PENDING** (2FA) — Set when 2FA challenge is issued
4. **SUCCESS** — Set when dispatch succeeds or result received with success=True
5. **FAILURE** — Set when executor unreachable, 2FA expired, or success=False

#### 4.5.3 Argument Classification

Arguments are classified per field in the capability's input schema:

| Classification | Behavior |
|---|---|
| `VALUE` | Stored in plain text |
| `HASH_ONLY` | Only hash stored |
| `REDACT` | Stored as `[REDACTED]` |

### 4.6 RPC Methods

#### 4.6.1 Execution Flow

| Method | Type | Description |
|---|---|---|
| `request_capability` | call | Authorize and dispatch capability request |
| `get_capability_result` | call | Retrieve result by request_id |
| `report_capability_result` | cast | Receive execution result from Executor |

#### 4.6.2 Capability Catalog

| Method | Type | Description |
|---|---|---|
| `list_capabilities` | call | List all capabilities in catalog |
| `get_capability` | call | Get capability by ID |
| `create_capability` | call | Create new capability |
| `update_capability` | call | Update capability |
| `delete_capability` | call | Delete capability |
| `approve_capability` | call | Approve discovered capability |

#### 4.6.3 Packs and Profiles

| Method | Type | Description |
|---|---|---|
| `list_packs` | call | List all packs |
| `get_pack` | call | Get pack by ID |
| `create_pack` | call | Create new pack |
| `update_pack` | call | Update pack |
| `delete_pack` | call | Delete pack |
| `list_profiles` | call | List all profiles |
| `get_profile` | call | Get profile by ID |
| `create_profile` | call | Create new profile |
| `update_profile` | call | Update profile |
| `delete_profile` | call | Delete profile |

#### 4.6.4 Bindings

| Method | Type | Description |
|---|---|---|
| `list_bindings` | call | List bindings (optional principal filter) |
| `get_binding` | call | Get binding by ID |
| `create_binding` | call | Create binding |
| `update_binding` | call | Update binding (enable/disable) |
| `delete_binding` | call | Delete binding |

#### 4.6.5 Executor Management

| Method | Type | Description |
|---|---|---|
| `list_executors` | call | List all executors |
| `get_executor` | call | Get executor by ID |
| `update_executor_status` | cast | Upsert executor status after heartbeat |
| `list_executor_capabilities` | call | List capabilities available on executor |

#### 4.6.6 Target Management

| Method | Type | Description |
|---|---|---|
| `list_targets` | call | List all targets |
| `get_target` | call | Get target by ID |
| `update_target` | call | Update target |
| `delete_target` | call | Delete target |

#### 4.6.7 Target Group Management

| Method | Type | Description |
|---|---|---|
| `list_target_groups` | call | List all target groups |
| `get_target_group` | call | Get target group by ID |
| `create_target_group` | call | Create target group |
| `update_target_group` | call | Update target group |
| `delete_target_group` | call | Delete target group |
| `add_target_to_group` | call | Add target to group |
| `remove_target_from_group` | call | Remove target from group |
| `list_group_members` | call | List all targets in a group |

#### 4.6.8 Configuration

| Method | Type | Description |
|---|---|---|
| `list_configurations` | call | List capability configurations |
| `get_configuration` | call | Get configuration by ID |
| `create_configuration` | call | Create configuration |
| `update_configuration` | call | Update configuration |
| `delete_configuration` | call | Delete configuration |

#### 4.6.9 Audit and Users

| Method | Type | Description |
|---|---|---|
| `list_audit_logs` | call | List audit logs with filters |
| `get_user_by_username` | call | Get user (includes password hash) |
| `list_users` | call | List all users |
| `create_user` | call | Create user |
| `update_user` | call | Update user |
| `delete_user` | call | Delete user |
| `list_effective_capabilities` | call | List capabilities a principal can execute |

---

## 5. sentinel-scheduler

### 5.1 Responsibilities

- Maintain in-memory liveness registry of executors
- Route signed CapabilityRequests to executor queues
- Track executor heartbeats
- Mark stale executors as inactive

### 5.2 Executor Registry

```python
@dataclass
class ExecutorInfo:
    executor_id: str
    hostname: str
    status: str  # ACTIVE, INACTIVE, UNKNOWN
    last_seen: datetime
    capabilities: list[str]  # capability names
    labels: dict[str, str]
```

### 5.3 Liveness Tracking

- **Heartbeat interval:** Configurable (default: 30 seconds)
- **Liveness threshold:** `heartbeat_interval * 3` (default: 90 seconds)
- **Stale reaper:** Background daemon thread scans for stale executors

### 5.4 RPC Methods

| Method | Type | Description |
|---|---|---|
| `executor_heartbeat` | cast | Receive heartbeat from executor |
| `dispatch` | call | Route signed CapabilityRequest to executor |
| `list_executors` | call | List all known executors with liveness |

### 5.5 Dispatch Flow

```text
Conductor calls scheduler.dispatch(request, executor_id)
  │
  ├─ Check liveness: registry.is_alive(executor_id)
  │   ├─ NO → return {"status": "executor_unreachable"}
  │   └─ YES → continue
  │
  ├─ Build message properties:
  │   ├─ content_type: application/json
  │   ├─ delivery_mode: 2 (persistent)
  │   ├─ expiration: 120000 (120 seconds TTL)
  │   ├─ correlation_id: request_id
  │   └─ reply_to: sentinel.control_plane.results
  │
  └─ Cast to queue: sentinel.executor.<executor_id>
```

---

## 6. sentinel-mcp-api

### 6.1 Responsibilities

- Expose MCP tools for AI agents
- Generate tools from authorized capability manifests
- Authenticate MCP clients (API key)
- Forward requests to Conductor via RPC

### 6.2 MCP Tools

#### 6.2.1 `request_capability`

**Description:** Request execution of a capability on a target. Returns immediately with a `request_id`; poll `get_capability_result` for results.

**Input Schema:**

| Property | Type | Required | Description |
|---|---|---|---|
| `capability` | string | Yes | Capability name (e.g., `service.status`) |
| `arguments` | object | Yes | Capability arguments |
| `target_id` | string | Yes | Target executor ID |

**Output:**

```json
{
  "status": "pending|pending_2fa|success|failure|denied|error|executor_unreachable",
  "request_id": "uuid",
  "decision_id": "uuid",
  "challenge_id": "uuid (if 2FA)",
  "reason": "string (if denied/error)"
}
```

#### 6.2.2 `get_capability_result`

**Description:** Poll for the outcome of a previously submitted capability request.

**Input Schema:**

| Property | Type | Required | Description |
|---|---|---|---|
| `request_id` | string | Yes | The request_id returned by `request_capability` |

**Output:**

```json
{
  "request_id": "uuid",
  "success": true,
  "data": {},
  "error": null,
  "metadata": {
    "duration_ms": 83,
    "provider": "linux.systemd",
    "capability": "service.status",
    "capability_version": "1.0.0"
  }
}
```

#### 6.2.3 `list_executors`

**Description:** Return the list of registered executors and their liveness status.

**Input Schema:** Empty object (no parameters)

**Output:**

```json
{
  "executors": [
    {
      "executor_id": "uuid",
      "hostname": "web-server-01",
      "status": "active",
      "capabilities": ["service.status", "logs.read"]
    }
  ]
}
```

#### 6.2.4 `list_effective_capabilities`

**Description:** List every capability this AI agent is authorized to execute, including effective constraints.

**Input Schema:**

| Property | Type | Required | Description |
|---|---|---|---|
| `target_id` | string | No | Filter results to a specific target |

**Output:**

```json
{
  "capabilities": [
    {
      "name": "service.status",
      "major_version": 1,
      "risk_level": "READ",
      "input_schema": {},
      "effective_constraints": {},
      "executors": ["executor-001", "executor-002"]
    }
  ]
}
```

### 6.3 Authentication

- **Mechanism:** `Authorization: Bearer <mcp_api_secret_key>` header
- **Validation:** Constant-time comparison via `secrets.compare_digest()`
- **Failure:** HTTP 401 with JSON-RPC error body

### 6.4 MCP Lifecycle

| Method | Response |
|---|---|
| `initialize` | `protocolVersion`, `capabilities: {tools: {}}`, `serverInfo` |
| `notifications/initialized` | Empty result |
| `ping` | Empty result |

---

## 7. sentinel-admin-api

### 7.1 Responsibilities

- REST API for human administrators
- CRUD for capabilities, packs, profiles, bindings, configurations
- CRUD for executors, targets, target groups
- Audit log queries
- User management (superuser only)

### 7.2 Endpoints

#### 7.2.1 Auth (`/auth`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/login` | None | Login, returns JWT |
| `GET` | `/auth/me` | JWT | Get current user |

#### 7.2.2 Capabilities (`/capabilities`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/capabilities` | JWT | List all capabilities |
| `POST` | `/capabilities` | JWT | Create capability |
| `GET` | `/capabilities/{id}` | JWT | Get capability |
| `PATCH` | `/capabilities/{id}` | JWT | Update capability |
| `DELETE` | `/capabilities/{id}` | JWT | Delete capability |
| `POST` | `/capabilities/{id}/approve` | JWT | Approve discovered capability |

#### 7.2.3 Packs (`/packs`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/packs` | JWT | List all packs |
| `POST` | `/packs` | JWT | Create pack |
| `GET` | `/packs/{id}` | JWT | Get pack |
| `PATCH` | `/packs/{id}` | JWT | Update pack |
| `DELETE` | `/packs/{id}` | JWT | Delete pack |

#### 7.2.4 Profiles (`/profiles`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/profiles` | JWT | List all profiles |
| `POST` | `/profiles` | JWT | Create profile |
| `GET` | `/profiles/{id}` | JWT | Get profile |
| `PATCH` | `/profiles/{id}` | JWT | Update profile |
| `DELETE` | `/profiles/{id}` | JWT | Delete profile |

#### 7.2.5 Bindings (`/bindings`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/bindings` | JWT | List bindings |
| `POST` | `/bindings` | JWT | Create binding |
| `GET` | `/bindings/{id}` | JWT | Get binding |
| `PATCH` | `/bindings/{id}` | JWT | Update binding |
| `DELETE` | `/bindings/{id}` | JWT | Delete binding |

#### 7.2.6 Executors (`/executors`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/executors` | JWT | List all executors |
| `GET` | `/executors/{id}` | JWT | Get executor |
| `GET` | `/executors/{id}/capabilities` | JWT | List executor capabilities |

#### 7.2.7 Targets (`/targets`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/targets` | JWT | List all targets |
| `GET` | `/targets/{id}` | JWT | Get target |
| `PATCH` | `/targets/{id}` | JWT | Update target |
| `DELETE` | `/targets/{id}` | JWT | Delete target |
| `GET` | `/targets/{id}/groups` | JWT | List target groups |

#### 7.2.8 Target Groups (`/target-groups`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/target-groups` | JWT | List all target groups |
| `POST` | `/target-groups` | JWT | Create target group |
| `GET` | `/target-groups/{id}` | JWT | Get target group |
| `PATCH` | `/target-groups/{id}` | JWT | Update target group |
| `DELETE` | `/target-groups/{id}` | JWT | Delete target group |
| `GET` | `/target-groups/{id}/members` | JWT | List members |
| `POST` | `/target-groups/{id}/members` | JWT | Add member |
| `DELETE` | `/target-groups/{id}/members/{target_id}` | JWT | Remove member |

#### 7.2.9 Configurations (`/configurations`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/configurations` | JWT | List configurations |
| `POST` | `/configurations` | JWT | Create configuration |
| `GET` | `/configurations/{id}` | JWT | Get configuration |
| `PATCH` | `/configurations/{id}` | JWT | Update configuration |
| `DELETE` | `/configurations/{id}` | JWT | Delete configuration |

#### 7.2.10 Audit Logs (`/audit-logs`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/audit-logs` | JWT | List audit logs with filters |

#### 7.2.11 Users (`/users`) — Superuser only

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/users` | Superuser | List all users |
| `POST` | `/users` | Superuser | Create user |
| `PATCH` | `/users/{id}` | Superuser | Update user |
| `DELETE` | `/users/{id}` | Superuser | Delete user |

### 7.3 Authentication

- **Mechanism:** JWT (HS256) via `Authorization: Bearer <token>`
- **Token lifetime:** Configurable (default: 60 minutes)
- **Superuser guard:** Required for user management endpoints

### 7.4 Request Forwarding

All endpoints forward to Conductor via oslo.messaging RPC:

```python
conductor.call({}, "method_name", **kwargs)
```

---

## 8. Configuration

### 8.1 Option Groups

| Group | File | Key Options |
|---|---|---|
| `[database]` | `config/database.py` | `connection`, `pool_size`, `max_overflow`, `echo` |
| `[messaging]` | `config/messaging.py` | `transport_url`, `rpc_topic_conductor`, `rpc_topic_scheduler`, `executor_queue_prefix`, `rpc_timeout` |
| `[conductor]` | `config/conductor.py` | `private_key_path`, `public_key_path`, `rsa_key_bits`, `twofa_challenge_timeout_seconds`, `workers` |
| `[auth]` | `config/auth.py` | `provider`, `admin_api_secret_key`, `admin_api_token_ttl_minutes`, `mcp_api_secret_key` |
| `[telegram]` | `config/auth.py` | `bot_token`, `approver_chat_id`, `polling_interval_seconds` |

### 8.2 Environment Variables

| Variable | Description |
|---|---|
| `SENTINEL_CONF` | Path to config file |
| `SENTINEL_INITIAL_ADMIN_USER` | Initial admin username |
| `SENTINEL_INITIAL_ADMIN_PASSWORD` | Initial admin password |
| `SENTINEL_INITIAL_ADMIN_EMAIL` | Initial admin email |
| `SENTINEL_SEED_DEFAULTS` | Seed default capabilities/packs |

---

## 9. Database Schema

### 9.1 Entity Relationship

```text
capabilities ──┬── capability_pack_members ── capability_packs
               ├── capability_profile_overrides ── capability_profiles
               ├── capability_configurations
               └── executor_capabilities ── executors

bindings ──┬── principals (users/agents)
           ├── capabilities / packs / profiles
           └── targets / target_groups

audit_log ── request_id, decision_id, executor_id
```

### 9.2 Tables

See `docs/design-decisions.md` sección 3 for complete table definitions.

---

## 10. Migration from Legacy

### 10.1 Command Sets → Packs

| Legacy | New |
|---|---|
| `CommandSet` | `Pack` |
| `Command` | `Capability` |
| `RoleBinding` | `Binding` (with `resource_type`) |
| `driver` | `provider` |
| `binary` + `args_regex` | `input_schema` + `constraints` |

### 10.2 Migration Strategy

1. Create new tables alongside legacy tables
2. Migrate data from `CommandSet` → `Pack`, `Command` → `Capability`
3. Create `Binding` records from `RoleBinding` records
4. Keep legacy tables read-only during transition
5. Remove legacy tables after all clients migrated

---

## 11. Security

### 11.1 Invariants

1. **Conductor is the sole DB writer** — no other component touches the database
2. **All requests signed** — Conductor signs every CapabilityRequest
3. **All results signed** — Executor signs every CapabilityResult
4. **Audit log is immutable** — no update path, no delete path
5. **Secrets never logged** — passwords, tokens, keys are never stored in plain text
6. **Default deny** — anything not explicitly allowed is rejected

### 11.2 RPC Security

- All RPC calls are internal (RabbitMQ)
- No authentication on RPC (trusted network)
- Signature verification at the Executor boundary

---

## 12. Error Handling

### 12.1 MCP API — JSON-RPC 2.0 Error Codes

| Code | Meaning | When |
|---|---|---|
| `-32700` | Parse error | Invalid JSON |
| `-32601` | Method not found | Unknown method/tool |
| `-32602` | Invalid params | Missing required parameters |
| `-32603` | Internal error | Conductor RPC exception |
| `-32001` | Unauthorized | Missing/invalid API key |

### 12.2 Admin API — HTTP Status Codes

| Status | When |
|---|---|
| 401 | Invalid/missing JWT |
| 403 | Inactive user, non-superuser |
| 404 | Resource not found |
| 422 | Validation failure |
| 500 | Unhandled Conductor RPC exception |

---

## 13. Definition of Done

Control Plane v2 is complete when:

1. Conductor authorizes capabilities (not commands)
2. Scheduler routes to executors (not targets)
3. MCP API generates tools from manifests
4. Admin API manages capabilities, packs, profiles, bindings
5. Audit log correlates authorization and execution
6. 2FA flow works with capability risk levels
7. RSA signing/verification works end-to-end
8. Legacy migration path is documented
9. Security tests pass
10. Example flow works end-to-end
