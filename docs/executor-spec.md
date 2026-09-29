# MCP-Sentinel — Executor Specification

**Status:** Draft  
**Version:** 1.0.0-draft  
**Target:** sentinel_executor (replaces sentinel_target)  
**Audience:** Executor developers, code-generation agents, security reviewers

Normative terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** define implementation requirements.

---

## 1. Purpose

This specification defines the Executor — the component that runs on target hosts and executes authorized capabilities.

> **The Executor verifies an authorized request, validates it again, resolves a local provider, applies local constraints/limits and executes it. It MUST NOT grant a capability absent Control Plane authorization.**

---

## 2. Architecture

### 2.1 Component Diagram

```text
┌─────────────────────────────────────────────────────────┐
│                    EXECUTOR                              │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ sentinel_executor                                │  │
│  │                                                  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐  │  │
│  │  │Heartbeat    │  │Capability   │  │Plugin   │  │  │
│  │  │Thread       │  │Registry     │  │Discovery│  │  │
│  │  └─────────────┘  └─────────────┘  └─────────┘  │  │
│  │                                                  │  │
│  │  ┌──────────────────────────────────────────┐   │  │
│  │  │Capability Request Handler                │   │  │
│  │  │  1. Verify signature                     │   │  │
│  │  │  2. Verify expiry                        │   │  │
│  │  │  3. Verify nonce/replay                  │   │  │
│  │  │  4. Validate arguments                   │   │  │
│  │  │  5. Resolve provider                     │   │  │
│  │  │  6. Apply constraints/limits             │   │  │
│  │  │  7. Execute via SDK                      │   │  │
│  │  │  8. Return signed result                 │   │  │
│  │  └──────────────────────────────────────────┘   │  │
│  │                                                  │  │
│  │  ┌──────────────────────────────────────────┐   │  │
│  │  │Capability SDK                            │   │  │
│  │  │  - Capability                            │   │  │
│  │  │  - CapabilityProvider                    │   │  │
│  │  │  - ExecutionContext                       │   │  │
│  │  │  - Registry                              │   │  │
│  │  └──────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Trust Boundary

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
│                                                          │
│  Golden Rule:                                            │
│  NEVER execute a request that fails verification         │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Identifiers

### 3.1 executor_id

- **Type:** UUID (opaque, stable, persistent)
- **Generation:** During enrollment
- **Persistence:** Stored locally on the host
- **Survives:** Restarts and upgrades
- **Loss:** Requires re-enrollment or explicit identity recovery

### 3.2 instance_id

- **Type:** UUID (new on every process start)
- **Persistence:** Not persisted
- **Purpose:** Restart detection and replay protection

### 3.3 hostname

- **Type:** String (display metadata only)
- **NOT** used as primary identity
- Changing hostname does NOT change executor identity

---

## 4. Installation

### 4.1 Packaged Deployment

```bash
apt install sentinel-executor
```

### 4.2 Python Deployment

```bash
python3 -m venv /opt/mcp-sentinel
/opt/mcp-sentinel/bin/pip install sentinel-executor
```

### 4.3 Configuration

```yaml
executor:
  id: 4cb6e61e-....  # Auto-generated on first run, persisted locally

control_plane:
  url: https://sentinel.infraestructura.com.ar
  enrollment_token: "..."

capabilities:
  builtin: true

plugins:
  auto_discover: true
```

### 4.4 Systemd

```bash
systemctl enable --now sentinel-executor
```

---

## 5. Startup Lifecycle

```text
Executor starts
  │
  ├─ 1. Identify host/executor
  │     └─ Load or generate executor_id (persisted locally)
  │
  ├─ 2. Authenticate/enroll
  │     └─ Register with Control Plane (enrollment_token)
  │
  ├─ 3. Load built-in providers
  │     └─ linux.system, linux.process, linux.filesystem, etc.
  │
  ├─ 4. Discover installed plugins
  │     └─ stevedore entry points: sentinel.capability.providers
  │
  ├─ 5. Validate capability definitions
  │     └─ Schema validation, risk metadata, manifests
  │
  ├─ 6. Check provider host requirements
  │     └─ Executable paths, permissions
  │
  ├─ 7. Build local Capability Registry
  │     └─ Map capability@major_version → provider
  │
  ├─ 8. Generate canonical manifests/hashes
  │     └─ manifest_hash = SHA256(canonical_json(manifest))
  │
  ├─ 9. Calculate capability_set_hash
  │     └─ SHA-256(canonical_inventory)
  │
  ├─ 10. REGISTER/synchronize with Control Plane
  │      └─ Send inventory to Control Plane
  │
  └─ 11. Start heartbeat
         └─ Send heartbeat every N seconds
```

---

## 6. Capability Registry

### 6.1 Local Registry

The Executor maintains a local registry mapping capabilities to providers:

```text
service.status@1             -> linux.systemd
logs.read@1                  -> linux.logs
network.routes.list@1       -> linux.iproute2
network.connections.list@1  -> linux.iproute2
zfs.pool.status@1           -> linux.zfs (plugin)
```

### 6.2 Registry Operations

| Operation | Description |
|---|---|
| `register(capability, provider)` | Add capability to registry |
| `resolve(name, major_version)` | Resolve capability to provider |
| `list()` | List all registered capabilities |
| `remove(name)` | Remove capability from registry |

### 6.3 Resolution Rules

1. **Major version compatibility:** `service.status@1` resolves to newest compatible `1.x`
2. **Duplicate detection:** Duplicate incompatible registrations fail explicitly
3. **Deterministic resolution:** Same input always produces same output
4. **Agent MUST NOT select providers**

---

## 7. Request Verification (12 Steps)

The Executor MUST verify requests in this exact order:

```text
1. Parse envelope
2. Validate protocol version
3. Verify signature
4. Verify target identity
5. Verify expiry
6. Verify nonce/replay
7. Confirm authorization
8. Resolve capability/version
9. Validate arguments
10. Apply local constraints/limits
11. Resolve provider
12. Execute
```

**Failure at any stage MUST stop execution.**

### 7.1 Parse Envelope

- Validate JSON structure
- Validate required fields present
- Validate field types

### 7.2 Validate Protocol Version

- Check `protocol_version` is supported
- Reject unknown versions

### 7.3 Verify Signature

- Recompute canonical JSON (excluding `security.signature`)
- Verify RSA-SHA256 signature with Control Plane's public key
- Reject invalid signatures

### 7.4 Verify Target Identity

- Check `target.id` matches Executor's `executor_id`
- Reject requests for other targets

### 7.5 Verify Expiry

- Check `security.expires_at` is in the future
- Check `security.issued_at` is not too far in the past (max 120 seconds)
- Check clock skew (max 30 seconds future)

### 7.6 Verify Nonce/Replay

- Check `security.nonce` has not been seen before
- Store nonce with TTL (5 minutes)
- Reject replayed nonces

### 7.7 Confirm Authorization

- Check `authorization.approved` is true
- Check `authorization.decision_id` is present
- Reject unauthorized requests

### 7.8 Resolve Capability/Version

- Resolve `capability.name` + `capability.major_version` to concrete capability
- Reject unknown capabilities
- Reject unsupported versions

### 7.9 Validate Arguments

- Validate arguments against capability's `input_model`
- Reject invalid arguments
- Reject extra fields

### 7.10 Apply Local Constraints/Limits

- Apply Executor's local hard constraints
- Apply effective limits (minimum of applicable limits)
- Reject constraint violations

### 7.11 Resolve Provider

- Resolve provider for the capability
- Reject unknown providers
- Reject unavailable providers

### 7.12 Execute

- Execute capability via `ExecutionContext`
- Capture result
- Build `CapabilityResult`

---

## 8. Heartbeat and Synchronization

### 8.1 Heartbeat

```json
{
  "executor_id": "4cb6e61e-...",
  "instance_id": "98bd...",
  "sequence": 9381,
  "capability_set_hash": "sha256:ABCDE..."
}
```

- **Interval:** Configurable (default: 30 seconds)
- **Transport:** RabbitMQ cast to scheduler
- **Purpose:** Liveness detection

### 8.2 Capability Set Hash

```text
capability_set_hash = SHA-256(canonical_inventory)
```

The inventory is sorted by:
- `capability_name`
- `capability_version`
- `provider_name`
- `provider_version`

Each entry includes:
- `capability_name`
- `capability_version`
- `manifest_hash`
- `provider_name`
- `provider_version`
- `availability_status`

### 8.3 Synchronization

- If `capability_set_hash` unchanged: no retransmission needed
- If `capability_set_hash` changed: trigger SYNC with detailed inventory

### 8.4 Detailed Inventory

```json
{
  "executor_id": "4cb6e61e-...",
  "capabilities": [
    {
      "name": "service.status",
      "version": "1.0.0",
      "manifest_hash": "sha256:...",
      "provider": "linux.systemd",
      "provider_version": "1.2.0"
    },
    {
      "name": "zfs.pool.status",
      "version": "1.0.0",
      "manifest_hash": "sha256:...",
      "provider": "linux.zfs",
      "provider_version": "1.0.1"
    }
  ]
}
```

---

## 9. Plugin Discovery

### 9.1 Stevedore Entry Points

```ini
[project.entry-points."sentinel.capability.providers"]
linux.systemd = sentinel_capabilities.linux.systemd:SystemdProvider
linux.zfs = sentinel_capabilities.zfs:ZFSProvider
```

### 9.2 Discovery Behavior

1. Load all entry points from `sentinel.capability.providers`
2. Validate provider identity/version
3. Validate capability metadata
4. Check host requirements
5. Build local registry
6. Generate canonical manifests/hashes
7. Calculate `capability_set_hash`

### 9.3 Load Failure

- Broken plugin MUST NOT silently replace another
- Load failure MUST be visible/auditable
- Error message MUST be clear

### 9.4 Plugin Installation

```bash
/opt/mcp-sentinel/bin/pip install sentinel-capability-zfs
systemctl restart sentinel-executor
```

After installation:
- New capabilities appear in registry
- `capability_set_hash` changes
- SYNC triggered automatically

---

## 10. Execution

### 10.1 ExecutionContext

The Executor uses the Capability SDK's `ExecutionContext` for all process execution:

```python
result = await ctx.exec(
    executable="/usr/bin/systemctl",
    argv=["systemctl", "status", "--", "postgresql"],
    timeout_seconds=10,
    max_output_bytes=1048576,
)
```

### 10.2 Security Properties

- **No shell:** `subprocess.run(..., shell=False)` always
- **Absolute paths:** Executable must be absolute
- **Argv boundaries:** Arguments preserved as separate list items
- **Timeout:** Enforced by SDK
- **Output limits:** Enforced by SDK
- **Environment:** Controlled, no secret inheritance
- **Cleanup:** Deterministic process cleanup

### 10.3 Result

```json
{
  "protocol_version": "2.0",
  "request_id": "018f...",
  "success": true,
  "data": {
    "service": "postgresql",
    "state": "active",
    "substate": "running"
  },
  "error": null,
  "metadata": {
    "duration_ms": 83,
    "provider": "linux.systemd",
    "capability": "service.status",
    "capability_version": "1.0.0",
    "truncated": false
  }
}
```

---

## 11. CLI

### 11.1 Commands

```bash
sentinel-executor capability list
sentinel-executor capability show service.status
sentinel-executor provider list
sentinel-executor plugin list
```

### 11.2 Output

Human-readable and JSON formats:

```bash
sentinel-executor capability list --output json
```

---

## 12. Configuration

### 12.1 Option Groups

| Group | Key Options |
|---|---|
| `[executor]` | `executor_id`, `instance_id`, `conductor_public_key_path`, `heartbeat_interval_seconds` |
| `[messaging]` | `transport_url`, `rpc_topic_conductor`, `rpc_topic_scheduler`, `executor_queue_prefix`, `rpc_timeout` |
| `[capabilities]` | `builtin_enabled`, `plugin_auto_discover` |

### 12.2 Environment Variables

| Variable | Description |
|---|---|
| `SENTINEL_CONF` | Path to config file |
| `SENTINEL_EXECUTOR_ID` | Override executor_id (for testing) |

---

## 13. Security

### 13.1 Golden Rules

1. **NEVER execute a request that fails verification**
2. **NEVER skip signature verification**
3. **NEVER execute unsigned requests**
4. **NEVER execute expired requests**
5. **NEVER execute replayed requests**
6. **NEVER execute requests for other targets**
7. **NEVER execute unauthorized requests**
8. **NEVER execute with invalid arguments**
9. **NEVER execute with constraint violations**
10. **NEVER use shell=True**

### 13.2 No Listening Sockets

The Executor opens **NO listening network sockets**. All communication is outbound to RabbitMQ only.

### 13.3 No Inbound Credentials

The Executor has **NO credentials** for:
- PostgreSQL (database)
- RabbitMQ management
- Other executors

The Executor only has:
- Conductor's public key (for signature verification)
- Enrollment token (for initial registration)

---

## 14. Error Handling

### 14.1 Error Codes

```text
CAPABILITY_NOT_FOUND
CAPABILITY_VERSION_UNSUPPORTED
PROVIDER_NOT_FOUND
PROVIDER_UNAVAILABLE
INVALID_ARGUMENT
CONSTRAINT_VIOLATION
EXECUTION_TIMEOUT
OUTPUT_LIMIT_EXCEEDED
EXECUTION_FAILED
AUTHORIZATION_INVALID
REQUEST_EXPIRED
REQUEST_REPLAYED
SIGNATURE_INVALID
INTERNAL_ERROR
```

### 14.2 Error Response

```json
{
  "protocol_version": "2.0",
  "request_id": "018f...",
  "success": false,
  "data": null,
  "error": {
    "code": "CONSTRAINT_VIOLATION",
    "message": "Pool 'Storage03' is not in allowed_pools",
    "details": {
      "constraint": "allowed_pools",
      "value": "Storage03"
    }
  },
  "metadata": {
    "duration_ms": 0,
    "provider": "linux.zfs",
    "capability": "zfs.pool.status",
    "capability_version": "1.0.0"
  }
}
```

---

## 15. Migration from sentinel_target

### 15.1 Key Changes

| Aspecto | sentinel_target | sentinel_executor |
|---|---|---|
| Nombre | `sentinel_target` | `sentinel_executor` |
| Ejecución | Drivers (posix_bash) | Providers (capabilities) |
| Payload | ExecutionPayload (command + args) | CapabilityRequest (capability + arguments) |
| Verificación | 7 pasos | 12 pasos |
| Registry | No existe | Local Capability Registry |
| Plugins | Drivers stevedore | Providers stevedore |
| Heartbeat | TargetHeartbeat | ExecutorHeartbeat |
| CLI | N/A | `sentinel-executor capability list` |

### 15.2 Removed

- `BashDriver` (reemplazado por providers de capacidades)
- `ExecutionPayload` (reemplazado por CapabilityRequest)
- `TargetHeartbeat` (reemplazado por ExecutorHeartbeat)
- `enabled_drivers` whitelist (reemplazado por capability registry)

### 15.3 Added

- Capability SDK integration
- Local Capability Registry
- Plugin discovery via stevedore
- 12-step request verification
- Capability set hash synchronization
- Executor CLI

---

## 16. Definition of Done

Executor v1 is complete when:

1. Executor starts and enrolls with Control Plane
2. Built-in providers load correctly
3. Plugin discovery works via stevedore
4. Local Capability Registry is built
5. 12-step request verification works
6. Capabilities execute via SDK (no shell)
7. Heartbeat and synchronization work
8. CLI commands work
9. Security tests pass
10. Example flow works end-to-end
