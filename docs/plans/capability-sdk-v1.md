# Plan de Implementación: Capability SDK v1

**Fecha:** 2026-09-29  
**Estado:** Draft  
**Spec relacionada:** `docs/specs/capability-sdk-spec.md`

---

## Work Packages

### Phase A — Foundation

#### CAP-001 — Capability SDK Core

**Goal:** Implement base SDK models/interfaces.

**Spec:** `docs/specs/capability-sdk-spec.md` sección 7

**Deliverables:**
- `Capability`
- `RiskLevel`
- `RiskMetadata`
- base input/output models
- `CapabilityResult`
- execution metadata
- stable SDK errors

**Constraints:**
- Pydantic v2
- async-ready
- no Conductor/DB/broker dependency

**Acceptance:**
- package imports independently
- malformed metadata rejected
- extra input fields rejected by default
- unit tests cover models/errors

---

#### CAP-002 — Capability Manifest

**Goal:** Create canonical manifest representation and validation.

**Spec:** `docs/specs/capability-sdk-spec.md` sección 6

**Deliverables:**
- manifest model
- YAML/JSON load
- JSON Schema export
- validation of name/version/risk/input/limits
- canonical JSON serialization
- manifest hash generation

**Acceptance:**
- example manifests round-trip
- invalid manifests fail clearly
- one canonical schema can serve CLI/MCP/policy
- manifest hash is deterministic

---

#### CAP-003 — Capability Registry

**Goal:** Deterministically map capability/version to provider.

**Spec:** `docs/specs/capability-sdk-spec.md` sección 9

**Deliverables:**
- register/resolve/list
- major-version compatibility
- duplicate detection
- provider availability status

**Acceptance:**
- unknown/unsupported versions fail with stable errors
- duplicate conflict tests
- deterministic resolution tests

---

#### CAP-004 — Stevedore Provider Discovery

**Goal:** Load external providers without core modification.

**Spec:** `docs/specs/capability-sdk-spec.md` sección 9

**Deliverables:**
- `sentinel.capability.providers` entry point
- startup discovery
- explicit load errors
- provider metadata

**Acceptance:**
- test plugin loads
- broken plugin does not silently replace another
- load failure is visible/auditable

---

#### CAP-005 — Safe ExecutionContext

**Goal:** Implement the primary process-execution security boundary.

**Spec:** `docs/specs/capability-sdk-spec.md` sección 7.4

**Deliverables:**
- async `exec`
- absolute executable enforcement
- no-shell execution
- controlled environment
- timeout
- output bounding
- cleanup
- `ExecResult`

**Acceptance:**
- shell metacharacters remain literal argv data
- timeout kills execution
- output limits work
- relative executables rejected
- environment leakage tests pass

---

#### CAP-006 — Path Constraint Library

**Goal:** Safely support filesystem/log capabilities.

**Spec:** `docs/specs/capability-sdk-spec.md` sección 13

**Deliverables:**
- canonical path validation
- allowed-path matching
- explicit symlink policy
- traversal defenses

**Acceptance:**
- tests for `..`, symlinks, prefix confusion and normalization
- lexical prefix matching is not used as the security decision

---

### Phase B — Read-only catalog

#### CAP-007 — System Capabilities

**Spec:** `docs/specs/capability-sdk-spec.md` sección 11

Implement:
- `system.info.get`
- `system.uptime.get`
- `system.resources.get`

Acceptance: READ-only, structured output, bounded execution, provider tests.

---

#### CAP-008 — Process Capabilities

**Spec:** `docs/specs/capability-sdk-spec.md` sección 11

Implement:
- `process.list`
- `process.inspect`

Acceptance: bounded listing, typed filters, structured output, no generic `/proc` arbitrary read.

---

#### CAP-009 — Filesystem Capabilities

**Spec:** `docs/specs/capability-sdk-spec.md` sección 11

Implement:
- `filesystem.list`
- `filesystem.stat`
- `filesystem.read`

Acceptance: CAP-006 constraints enforced, bounded content/listing, structured metadata.

---

#### CAP-010 — Log Capabilities

**Spec:** `docs/specs/capability-sdk-spec.md` sección 11

Implement:
- `logs.read`
- `logs.search`

Acceptance: allowed paths, line/result limits, no arbitrary shell pipeline, truncation metadata.

---

#### CAP-011 — Service Capabilities

**Spec:** `docs/specs/capability-sdk-spec.md` sección 11

Implement:
- `service.list`
- `service.status`

Initial provider: `linux.systemd`.

Acceptance: service name validation, structured state, no Agent-provided systemctl arguments.

---

#### CAP-012 — Network Capabilities

**Spec:** `docs/specs/capability-sdk-spec.md` sección 11

Implement:
- `network.interfaces.list`
- `network.routes.list`
- `network.connections.list`
- `network.dns.resolve`
- `network.ping`

Acceptance: typed destinations, bounded ping, structured results, no arbitrary command flags.

---

#### CAP-013 — Storage Capabilities

**Spec:** `docs/specs/capability-sdk-spec.md` sección 11

Implement:
- `storage.filesystems.list`
- `storage.usage`
- `storage.devices.list`

Acceptance: READ-only structured inventory/usage, bounded output.

---

#### CAP-014 — Linux Observer Pack

**Spec:** `docs/specs/capability-sdk-spec.md` sección 10

**Goal:** Publish the first official Pack.

Acceptance:
- expands deterministically
- every referenced capability exists
- overrides can only affect documented configurable fields
- pack has human-readable documentation

---

#### CAP-015 — Capability Discovery CLI

**Spec:** `docs/specs/capability-sdk-spec.md` sección 16

Implement minimum operator commands:

```text
sentinel-executor capability list
sentinel-executor capability show <name>
sentinel-executor provider list
sentinel-executor plugin list
```

Acceptance: human-readable and JSON output.

---

### Phase C — Distributed execution

#### CAP-016 — Capability Protocol v2 Models

**Spec:** `docs/specs/protocol-v2-spec.md`

**Goal:** Define signed semantic request/result models.

Deliverables:
- request envelope
- authorization metadata
- security envelope
- result envelope
- serialization/canonicalization required for signing

Acceptance: deterministic serialization; invalid/unknown fields rejected; no raw-command fields.

---

#### CAP-017 — Executor v2 Execution

**Spec:** `docs/specs/executor-spec.md`

**Goal:** Execute a verified CapabilityRequest through Registry + SDK.

Acceptance:
- required verification order implemented
- validation repeated locally
- local limits cannot be broadened
- correct provider invoked
- stable result/errors returned

---

#### CAP-018 — Control Plane Capability Authorization

**Spec:** `docs/specs/control-plane-spec.md`

**Goal:** Adapt authorization from command-centric to capability-centric semantics.

Acceptance:
- principal + target + capability + arguments are policy inputs
- denied requests are never dispatched
- approved requests receive decision ID and signature
- existing HITL can be attached to risk/policy decisions

---

### Phase D — Agent integration

#### CAP-019 — MCP Capability Exposure

**Spec:** `docs/specs/control-plane-spec.md`

**Goal:** Generate MCP-facing tools from authorized manifests.

Acceptance:
- standard v2 tools contain semantic inputs only
- Agent cannot select provider/driver/binary
- effective constraints are exposed in tool schema

---

### Phase E — Release gate

#### CAP-020 — Security and Adversarial Test Suite

**Spec:** `docs/specs/testing-spec.md`

Test at minimum:

```text
shell metacharacters
argument injection
unexpected fields
path traversal
symlink escape
prefix confusion
oversized input
oversized output
timeouts
child-process cleanup
environment leakage
unknown capability
unsupported version
provider collision
expired request
invalid signature
replayed nonce
wrong target
constraint broadening attempt
malformed provider output
```

**Acceptance:** all official providers pass the suite; security regressions block release.

---

## Dependencias

```text
Phase A — Foundation
CAP-001 → CAP-002 → CAP-003 → CAP-004 → CAP-005 → CAP-006

Phase B — Read-only catalog
CAP-007 → CAP-008 → CAP-009 → CAP-010
CAP-011 → CAP-012 → CAP-013 → CAP-014 → CAP-015

Phase C — Distributed execution
CAP-016 → CAP-017 → CAP-018

Phase D — Agent integration
CAP-019

Phase E — Release gate
CAP-020
```

---

## Estado

| Work Package | Estado | Asignado | Fecha |
|---|---|---|---|
| CAP-001 | Pendiente | — | — |
| CAP-002 | Pendiente | — | — |
| CAP-003 | Pendiente | — | — |
| CAP-004 | Pendiente | — | — |
| CAP-005 | Pendiente | — | — |
| CAP-006 | Pendiente | — | — |
| CAP-007 | Pendiente | — | — |
| CAP-008 | Pendiente | — | — |
| CAP-009 | Pendiente | — | — |
| CAP-010 | Pendiente | — | — |
| CAP-011 | Pendiente | — | — |
| CAP-012 | Pendiente | — | — |
| CAP-013 | Pendiente | — | — |
| CAP-014 | Pendiente | — | — |
| CAP-015 | Pendiente | — | — |
| CAP-016 | Pendiente | — | — |
| CAP-017 | Pendiente | — | — |
| CAP-018 | Pendiente | — | — |
| CAP-019 | Pendiente | — | — |
| CAP-020 | Pendiente | — | — |
