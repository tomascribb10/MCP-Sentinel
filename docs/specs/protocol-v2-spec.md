# MCP-Sentinel — Protocol v2 Specification

**Status:** Draft  
**Version:** 2.0.0-draft  
**Target:** Control Plane ↔ Executor communication  
**Audience:** SDK developers, Executor developers, code-generation agents, security reviewers

Normative terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** define implementation requirements.

---

## 1. Purpose

This specification defines the wire protocol for communication between the **Control Plane** and the **Executor** in MCP-Sentinel v2.

> **The protocol transmits authorization to execute a semantic capability, not a command.**

Protocol v2 MUST NOT contain Agent-selected `binary`, `command`, `shell`, `driver`, or `script`.

---

## 2. Scope

### 2.1 In scope

- Request/result envelope structure
- Canonical JSON serialization for signing
- Signature algorithm and key management
- Verification order in the Executor
- Error handling
- Protocol versioning
- Transport (RabbitMQ)
- Replay protection
- Expiry and clock skew

### 2.2 Out of scope

- Capability SDK internals (see `capability-sdk-spec.md`)
- Control Plane authorization logic
- MCP tool generation
- Audit logging
- Database persistence

---

## 3. Architecture

### 3.1 Message Flow

```text
Control Plane
  |
  | 1. Authorize request (RBAC + policy)
  | 2. Build CapabilityRequest
  | 3. Sign request (RSA-SHA256)
  | 4. Send to Executor queue (RabbitMQ)
  v
Executor
  |
  | 1. Receive request
  | 2. Verify signature
  | 3. Verify expiry
  | 4. Verify nonce/replay
  | 5. Validate arguments
  | 6. Resolve provider
  | 7. Execute capability
  | 8. Build CapabilityResult
  | 9. Send result to Control Plane queue (RabbitMQ)
  v
Control Plane
  |
  | 1. Receive result
  | 2. Verify signature
  | 3. Update audit log
  | 4. Return result to Agent
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
                          │
                          │ Signed CapabilityResult
                          │ (RabbitMQ — untrusted transport)
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    CONTROL PLANE                         │
│  (Trusted — verifies result, updates audit)              │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Envelope Structure

### 4.1 CapabilityRequest

```json
{
  "protocol_version": "2.0",
  "request_id": "018f...",
  "principal": {
    "id": "llm-agent-claude"
  },
  "target": {
    "id": "4cb6e61e-..."
  },
  "capability": {
    "name": "service.status",
    "major_version": 1
  },
  "arguments": {
    "service": "postgresql"
  },
  "authorization": {
    "policy_id": "uuid",
    "decision_id": "uuid",
    "approved": true
  },
  "limits": {
    "timeout_seconds": 10,
    "max_output_bytes": 1048576
  },
  "security": {
    "issued_at": "2026-09-28T16:00:00Z",
    "expires_at": "2026-09-28T16:00:30Z",
    "nonce": "uuid",
    "signature": "base64..."
  }
}
```

### 4.2 CapabilityResult

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
  },
  "security": {
    "issued_at": "2026-09-28T16:00:00Z",
    "expires_at": "2026-09-28T16:00:30Z",
    "nonce": "uuid",
    "signature": "base64..."
  }
}
```

### 4.3 Field Descriptions

| Field | Type | Description |
|---|---|---|
| `protocol_version` | string | Protocol version (e.g., "2.0") |
| `request_id` | UUID | Unique request identifier |
| `principal.id` | string | Principal identifier (agent identity) |
| `target.id` | string | Executor identifier |
| `capability.name` | string | Capability name (e.g., "service.status") |
| `capability.major_version` | integer | Major version (e.g., 1) |
| `arguments` | object | Capability arguments (validated by input schema) |
| `authorization.policy_id` | UUID | Policy identifier |
| `authorization.decision_id` | UUID | Authorization decision identifier |
| `authorization.approved` | boolean | Whether request is approved |
| `limits.timeout_seconds` | integer | Timeout in seconds |
| `limits.max_output_bytes` | integer | Maximum output in bytes |
| `security.issued_at` | ISO8601 | Request issuance timestamp |
| `security.expires_at` | ISO8601 | Request expiration timestamp |
| `security.nonce` | UUID | Unique nonce for replay protection |
| `security.signature` | base64 | RSA-SHA256 signature |

---

## 5. Canonical JSON Serialization

### 5.1 Rules

For signing and verification, the SDK MUST use canonical JSON:

1. **Keys sorted lexicographically** (by Unicode code point)
2. **No whitespace** (no spaces, tabs, newlines)
3. **UTF-8 encoding**
4. **No trailing newline**
5. **Numbers:** No leading zeros, no trailing zeros in fractions
6. **Strings:** Minimal escaping (only `"`, `\`, and control characters)

### 5.2 Signature Payload

The signature is computed over the canonical JSON of the envelope **excluding** the `security.signature` field.

```python
def sign_envelope(envelope: dict, private_key: str) -> str:
    """Sign an envelope with RSA-SHA256."""
    payload = {k: v for k, v in envelope.items() if k != "security"}
    payload["security"] = {k: v for k, v in envelope["security"].items() if k != "signature"}
    canonical = canonical_json(payload)
    signature = rsa_sign(canonical, private_key)
    return base64_encode(signature)
```

### 5.3 Verification

```python
def verify_envelope(envelope: dict, public_key: str) -> bool:
    """Verify an envelope signature."""
    signature = envelope["security"]["signature"]
    payload = {k: v for k, v in envelope.items() if k != "security"}
    payload["security"] = {k: v for k, v in envelope["security"].items() if k != "signature"}
    canonical = canonical_json(payload)
    return rsa_verify(canonical, signature, public_key)
```

---

## 6. Signature

### 6.1 Algorithm

- **Algorithm:** RSA-SHA256
- **Key size:** 4096 bits
- **Padding:** PKCS#1 v1.5
- **Hash:** SHA-256

### 6.2 Key Management

- **Control Plane:** Holds the private key
- **Executor:** Holds the public key
- **Key rotation:** Out of scope for v1 (manual process)

### 6.3 Signature Scope

The signature covers:
- `protocol_version`
- `request_id`
- `principal`
- `target`
- `capability`
- `arguments`
- `authorization`
- `limits`
- `security.issued_at`
- `security.expires_at`
- `security.nonce`

The signature does NOT cover:
- `security.signature` (the signature itself)

---

## 7. Verification Order

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

- Recompute canonical JSON
- Verify RSA-SHA256 signature
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
- Store nonce with TTL (e.g., 5 minutes)
- Reject replayed nonces

### 7.7 Confirm Authorization

- Check `authorization.approved` is true
- Check `authorization.decision_id` is present
- Reject unauthorized requests

### 7.8 Resolve Capability/Version

- Resolve `capability.name` + `capability.major_version` to a concrete capability
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

## 8. Error Handling

### 8.1 Error Codes

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

### 8.2 Error Response

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
  },
  "security": {
    "issued_at": "2026-09-28T16:00:00Z",
    "expires_at": "2026-09-28T16:00:30Z",
    "nonce": "uuid",
    "signature": "base64..."
  }
}
```

### 8.3 Error Handling Rules

- Errors MUST NOT leak sensitive information
- Errors MUST be logged locally in the Executor
- Errors MUST be returned to the Control Plane
- Errors MUST include `request_id` for correlation

---

## 9. Protocol Versioning

### 9.1 Version Format

`MAJOR.MINOR` (e.g., "2.0")

### 9.2 Compatibility

- **Major version change:** Breaking changes, requires explicit upgrade
- **Minor version change:** Backward compatible, additive changes

### 9.3 Negotiation

- Control Plane sends request with `protocol_version`
- Executor rejects unsupported versions
- Executor returns error with supported versions

---

## 10. Transport

### 10.1 RabbitMQ

- **Request queue:** `sentinel.executor.<executor_id>` (durable)
- **Result queue:** `sentinel.control_plane.results` (durable)
- **Exchange:** `sentinel` (topic)
- **Routing key:** `executor.<executor_id>` for requests, `results` for results

### 10.2 Message Properties

```python
{
  "content_type": "application/json",
  "delivery_mode": 2,  # Persistent
  "expiration": "120000",  # 120 seconds TTL
  "correlation_id": request_id,
  "reply_to": "sentinel.control_plane.results"
}
```

### 10.3 Message Format

- JSON text (UTF-8)
- No binary encoding
- No compression (for debugging simplicity)

### 10.4 Confirmation

- Publisher confirms for requests
- Consumer acknowledgements for results
- Dead letter queue for failed messages

---

## 11. Replay Protection

### 11.1 Nonce

- Each request has a unique `security.nonce` (UUID)
- Executor stores seen nonces with TTL (5 minutes)
- Replayed nonces are rejected

### 11.2 Timestamp

- `security.issued_at` MUST be within 120 seconds of current time
- `security.expires_at` MUST be in the future
- Clock skew tolerance: 30 seconds

### 11.3 Request ID

- Each request has a unique `request_id` (UUID)
- Used for correlation between request and result
- Stored in audit log

---

## 12. Security

### 12.1 Invariants

1. **Request MUST be signed** by Control Plane
2. **Executor MUST verify signature** before execution
3. **Request MUST expire** (max 60 seconds)
4. **Nonce MUST be unique** (replay protection)
5. **Target MUST match** Executor's identity
6. **Authorization MUST be confirmed** before execution
7. **Arguments MUST be validated** before execution
8. **Constraints MUST be enforced** before execution
9. **Result MUST be signed** by Executor
10. **Control Plane MUST verify result signature**

### 12.2 Forbidden

- Unsigned requests
- Expired requests
- Replayed nonces
- Requests for other targets
- Unauthorized requests
- Invalid arguments
- Constraint violations
- Unsigned results

---

## 13. Example Flow

### 13.1 Request

```json
{
  "protocol_version": "2.0",
  "request_id": "018f3a2b-...",
  "principal": {"id": "llm-agent-claude"},
  "target": {"id": "4cb6e61e-..."},
  "capability": {"name": "service.status", "major_version": 1},
  "arguments": {"service": "postgresql"},
  "authorization": {
    "policy_id": "uuid",
    "decision_id": "uuid",
    "approved": true
  },
  "limits": {"timeout_seconds": 10, "max_output_bytes": 1048576},
  "security": {
    "issued_at": "2026-09-28T16:00:00Z",
    "expires_at": "2026-09-28T16:00:30Z",
    "nonce": "uuid",
    "signature": "base64..."
  }
}
```

### 13.2 Result

```json
{
  "protocol_version": "2.0",
  "request_id": "018f3a2b-...",
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
  },
  "security": {
    "issued_at": "2026-09-28T16:00:00Z",
    "expires_at": "2026-09-28T16:00:30Z",
    "nonce": "uuid",
    "signature": "base64..."
  }
}
```

---

## 14. Definition of Done

Protocol v2 is complete when:

1. Envelope structure is defined and stable
2. Canonical JSON serialization is implemented
3. RSA-SHA256 signing/verification works
4. Verification order is implemented correctly
5. Error handling is stable and complete
6. Protocol versioning works
7. RabbitMQ transport is implemented
8. Replay protection works
9. Security tests pass
10. Example flow works end-to-end

---

## 15. Future Specifications

Intentionally deferred:

- mTLS for transport encryption
- Key rotation automation
- Multi-Executor coordination
- Streaming results
- Long-running operations
- Result compression
- Binary encoding
