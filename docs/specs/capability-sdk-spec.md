# MCP-Sentinel — Capability SDK Specification

**Status:** Draft  
**Version:** 1.0.0-draft  
**Target:** MCP-Sentinel v2 capability architecture  
**Audience:** SDK developers, plugin developers, code-generation agents, security reviewers

Normative terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** define implementation requirements.

---

## 1. Purpose

This specification defines MCP-Sentinel's Capability architecture and SDK.

> **Agents request capabilities. The Control Plane authorizes capabilities. The Executor executes capabilities via the SDK. Agents never submit arbitrary shell commands for v2 capability execution.**

The architecture MUST provide a stable Capability SDK, a secure Executor execution model, human-readable definitions, a useful built-in catalog, Capability Packs, an extension model, a signed Control Plane → Executor protocol, and machine-readable metadata usable by MCP, policy, CLI, documentation and audit.

The SDK MUST be independently importable and MUST NOT depend on Conductor DB models, RabbitMQ transport, MCP server implementation, or web framework state.

---

## 2. Scope

### 2.1 In scope

- Capability identity/naming/versioning
- Metadata and typed input/output schemas
- Risk metadata and constraints
- `Capability`, `CapabilityProvider`, `ExecutionContext`, result/error contracts
- Providers, registry, manifests, packs
- Linux Observer built-ins
- Control Plane → Executor protocol (see `protocol-v2-spec.md`)
- Execution lifecycle and audit
- Extensions and plugin development
- Security invariants
- Implementation work packages

### 2.2 Explicitly out of scope for v1

- External sandbox products
- Container orchestration
- A new broker (RabbitMQ is used)
- A generic remote shell
- Windows implementations
- Automatic remediation
- A complete WRITE/DESTRUCTIVE built-in catalog

---

## 3. Architectural Principles

### 3.1 Responsibilities

**Agent:** determines the semantic operation it wants. It MUST NOT select executable paths, shell syntax, drivers, providers, privilege mechanisms or target transport.

```json
{"capability":"service.status","arguments":{"service":"postgresql"}}
```

**Control Plane:** decides whether the principal may execute that capability with those arguments on that target. It owns identity, RBAC/policy, target/capability authorization, HITL, request signing and audit correlation. It MUST NOT construct shell commands for Protocol v2.

**Executor:** verifies an authorized request, validates it again, resolves a local provider, applies local constraints/limits and executes it. It MUST NOT grant a capability absent Control Plane authorization.

### 3.2 Capability vs Provider

A **Capability** describes WHAT operation exists. A **Provider** describes HOW it is implemented.

```text
service.status
    ├── linux.systemd
    ├── linux.openrc       (future)
    └── windows.scm        (future)
```

The Agent sees `service.status`, never `linux.systemd`.

### 3.3 No arbitrary shell in Protocol v2

Agent-controlled v2 fields MUST NOT include `binary`, `command`, `shell`, `driver`, `raw_args` or `script`.

Invalid:

```json
{"command":"systemctl status postgresql"}
```

Valid:

```json
{"capability":"service.status","arguments":{"service":"postgresql"}}
```

### 3.4 Layered Design

```text
┌─────────────────────────────────────────────────────────┐
│                    PLUGIN CODE                           │
│  (Custom capabilities, providers, manifests)             │
├─────────────────────────────────────────────────────────┤
│                    CAPABILITY SDK                        │
│  Capability, Provider, ExecutionContext, Registry        │
│  Manifest, Constraints, Risk, Errors                    │
├─────────────────────────────────────────────────────────┤
│                    EXECUTOR                              │
│  (Loads SDK, discovers providers, executes requests)     │
├─────────────────────────────────────────────────────────┤
│                    TARGET OS                             │
│  (Linux kernel, systemd, iproute2, etc.)                 │
└─────────────────────────────────────────────────────────┘
```

### 3.5 Dependencies

The SDK MUST NOT depend on:
- `sentinel_conductor` (Control Plane)
- `sentinel_scheduler` (Control Plane)
- `sentinel_mcp_api` (Control Plane)
- `sentinel_admin_api` (Control Plane)
- `oslo.messaging` (transport)
- `sqlalchemy` (persistence)
- `fastapi` (web framework)

The SDK SHOULD depend on:
- `pydantic` v2 (data validation)
- `stevedore` (plugin discovery)

---

## 4. Security Invariants

1. **Agent input MUST NOT become shell code.** Official providers MUST NOT use `shell=True`, `os.system`, `os.popen`, `eval`, `exec`, or equivalent interpretation with Agent-controlled input.
2. **Arguments MUST be validated twice:** before Control Plane authorization and again by the Executor before execution.
3. **Deny by default:** unknown capabilities/providers/arguments are rejected. Input schemas SHOULD reject extra fields.
4. **Absolute executables:** official process providers MUST use absolute paths and MUST NOT resolve through an Agent-controlled `PATH`.
5. **Bounded execution:** every execution has timeout, output limits and deterministic cleanup.
6. **Restricted environment:** child environments are explicitly constructed; unrelated secrets MUST NOT be inherited.
7. **No implicit privilege escalation:** providers MUST NOT invoke `sudo`, `su`, or equivalent unless a future privilege specification explicitly permits it.
8. **Result data is untrusted:** output MUST NOT be reinterpreted as executable instructions.

Conceptually safe:

```text
execve("/usr/bin/systemctl",
       ["systemctl","status","--","postgresql"],
       restricted_environment)
```

Forbidden design:

```text
/bin/sh -c "systemctl status " + agent_input
```

---

## 5. Naming, Versioning and Risk

### 5.1 Capability Names

Standard names SHOULD follow `<domain>.<resource>.<action>`; concise two-component names MAY be used when unambiguous.

```text
system.info.get
system.uptime.get
process.list
process.inspect
filesystem.list
filesystem.stat
filesystem.read
logs.read
logs.search
service.list
service.status
network.interfaces.list
network.routes.list
network.connections.list
network.dns.resolve
network.ping
storage.filesystems.list
storage.usage
storage.devices.list
```

Names MUST be lowercase, stable and semantic rather than command-oriented.

Standard namespaces initially reserved: `system`, `process`, `filesystem`, `logs`, `service`, `network`, `storage`, `package`, `user`, `security`.

Optional official packs MAY reserve `zfs`, `postgres`, `docker`, `openstack`, `vault`, `haproxy`.

Organizations MAY use private namespaces such as `neuralsoft.zfs.replication.status`.

### 5.2 Versioning

Each capability MUST have a semantic version. Breaking input/output/security/authorization semantics increment the major version.

The v1 registry SHOULD resolve major-version compatibility, e.g. `service.status@1` to the newest compatible installed `1.x`.

### 5.3 Risk Metadata

Every capability MUST expose:

```yaml
risk:
  level: READ
  modifies_system: false
  accesses_sensitive_data: false
  requires_privilege: false
  network_access: false
```

Risk levels are `READ`, `WRITE`, `DESTRUCTIVE`, and `PRIVILEGED`.

Linux Observer v1 SHOULD contain only READ capabilities.

---

## 6. Capability Manifest

### 6.1 Structure

Every capability MUST expose one canonical machine-readable manifest.

```yaml
name: logs.read
version: "1.0.0"
title: Read log
description: Reads a bounded number of lines from an allowed log file.
category: logs

risk:
  level: READ
  modifies_system: false
  accesses_sensitive_data: true
  requires_privilege: false
  network_access: false

input:
  type: object
  additionalProperties: false
  properties:
    path:
      type: string
    lines:
      type: integer
      default: 100
      minimum: 1
      maximum: 5000
  required: [path]

output:
  type: object
  properties:
    content:
      type: string
    lines_read:
      type: integer

constraints:
  allowed_paths:
    - /var/log/**

limits:
  timeout_seconds: 10
  max_output_bytes: 2097152

provider:
  preferred: linux.logs
```

### 6.2 Manifest Generation

Do not require developers to maintain duplicated Python schemas and hand-written manifests.

```text
Capability definition
  + Pydantic InputModel
  + Pydantic OutputModel
  + ConstraintsModel
  + RiskMetadata
  + descriptive metadata
        |
        v
  Capability SDK
        |
        v
  Canonical Manifest
        |
        v
  manifest_hash = SHA256(canonical_json(manifest))
```

### 6.3 Canonical JSON

The SDK MUST define canonical JSON serialization for manifest hashing:

1. Keys sorted lexicographically (by Unicode code point)
2. No whitespace (no spaces, tabs, newlines)
3. UTF-8 encoding
4. No trailing newline
5. Numbers: No leading zeros, no trailing zeros in fractions
6. Strings: Minimal escaping (only `"`, `\`, and control characters)

### 6.4 Manifest Validation

The SDK MUST validate:
- Name follows `<domain>.<resource>.<action>` pattern
- Version is valid semver
- Risk level is valid
- Input/output schemas are valid JSON Schema
- Constraints model is valid Pydantic model
- Provider name is valid

### 6.6 Single Source of Truth

The same manifest SHOULD feed human documentation, CLI, API/UI, policy validation, MCP tool generation, Executor validation and audit.

Independent incompatible schemas MUST NOT be maintained.

---

## 7. Capability SDK Core

### 7.1 Capability

```python
from abc import ABC, abstractmethod
from typing import TypeVar

InputT = TypeVar("InputT", bound="CapabilityInput")
OutputT = TypeVar("OutputT", bound="CapabilityOutput")


class Capability(ABC):
    """Base class for all capabilities."""

    name: str
    version: str
    title: str
    description: str
    category: str

    risk: RiskMetadata
    input_model: type[CapabilityInput]
    output_model: type[CapabilityOutput]
    constraints_model: type[ConstraintsModel] | None = None

    @abstractmethod
    async def execute(
        self,
        ctx: ExecutionContext,
        input: CapabilityInput,
    ) -> CapabilityResult:
        """Execute the capability with validated input."""
        ...
```

### 7.2 CapabilityProvider

```python
class CapabilityProvider(ABC):
    """Base class for capability providers."""

    name: str
    version: str
    capabilities: list[type[Capability]]
    requirements: list[HostRequirement]

    def check_requirements(self) -> list[RequirementResult]:
        """Check if host requirements are met."""
        ...
```

**Nota:** Un `CapabilityProvider` puede tener múltiples capabilities (ej: `linux.zfs` tiene `zfs.pool.list`, `zfs.pool.status`, etc.).

### 7.3 HostRequirement

```python
@dataclass
class HostRequirement(ABC):
    """Base class for host requirements."""
    pass


@dataclass
class Executable(HostRequirement):
    """Requirement for an executable file."""
    path: str           # Absolute path
    required: bool = True

    def check(self) -> RequirementResult:
        """Check if executable exists and is executable."""
        ...


@dataclass
class RequirementResult:
    """Result of a requirement check."""
    requirement: HostRequirement
    satisfied: bool
    message: str
```

Requisitos mínimos para `Executable`:
- `path` debe ser absoluto
- Verificar que el path exista
- Verificar que sea un archivo ejecutable válido
- Verificar permisos de ejecución aplicables al Executor
- La comprobación **no debe ejecutar el binario** durante discovery

### 7.4 ExecutionContext

```python
class ExecutionContext(ABC):
    """Security boundary for process execution."""

    @abstractmethod
    async def exec(
        self,
        executable: str,
        argv: list[str],
        *,
        timeout_seconds: int | None = None,
        max_output_bytes: int | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> ExecResult:
        """Execute a process without shell.

        Requirements:
        - executable MUST be absolute
        - argv MUST be preserved as separate arguments
        - No shell interpretation
        - Timeout enforced
        - Output bounded
        - Environment controlled
        - Cleanup deterministic
        """
        ...
```

### 7.5 ExecResult

```python
@dataclass
class ExecResult:
    """Result of process execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    truncated: bool = False
```

### 7.6 Data Models

```python
class CapabilityInput(BaseModel):
    """Base class for capability input models."""
    model_config = ConfigDict(extra="forbid")


class CapabilityOutput(BaseModel):
    """Base class for capability output models."""
    model_config = ConfigDict(extra="forbid")


class ConstraintsModel(BaseModel):
    """Base class for capability constraints.

    Developers define the model; admins configure values.
    """
    model_config = ConfigDict(extra="forbid")


@dataclass
class CapabilityResult:
    """Result of capability execution."""
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
```

---

## 8. Results and Errors

### 8.1 Result Envelope

A normalized result envelope MUST be returned:

```json
{
  "success": true,
  "data": {"service":"postgresql","state":"active","substate":"running"},
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

### 8.2 Error Codes

Minimum stable errors:

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

### 8.3 Error Hierarchy

```python
class CapabilityError(Exception):
    """Base exception for capability errors."""
    code: str
    message: str
    details: dict[str, Any] | None


class CapabilityNotFoundError(CapabilityError):
    code = "CAPABILITY_NOT_FOUND"


class ProviderNotFoundError(CapabilityError):
    code = "PROVIDER_NOT_FOUND"


class InvalidArgumentError(CapabilityError):
    code = "INVALID_ARGUMENT"


class ConstraintViolationError(CapabilityError):
    code = "CONSTRAINT_VIOLATION"


class ExecutionTimeoutError(CapabilityError):
    code = "EXECUTION_TIMEOUT"


class OutputLimitExceededError(CapabilityError):
    code = "OUTPUT_LIMIT_EXCEEDED"
```

---

## 9. Provider Model and Capability Registry

### 9.1 Provider Model

Providers implement semantic capabilities on a target platform. Exact executable paths and arguments are provider-owned and MUST NOT come from Agent or Control Plane.

### 9.2 Stevedore Entry Point

```ini
[project.entry-points."sentinel.capability.providers"]
linux.systemd = sentinel_capabilities.linux.systemd:SystemdProvider
linux.zfs = sentinel_capabilities.zfs:ZFSProvider
```

### 9.3 Registry

The Executor MUST maintain a local registry:

```text
service.status@1             -> linux.systemd
logs.read@1                  -> linux.logs
network.routes.list@1        -> linux.iproute2
network.connections.list@1   -> linux.iproute2
```

Duplicate incompatible registrations MUST fail explicitly; dependency failures MUST be reported; resolution MUST be deterministic; Agents MUST NOT select providers; registry contents MUST be locally discoverable; loading failures MUST be auditable.

### 9.4 Resolution Rules

1. **Major version compatibility:** `service.status@1` resolves to the newest compatible `1.x` installed
2. **Duplicate detection:** Duplicate incompatible registrations MUST fail explicitly
3. **Deterministic resolution:** Same input always produces same output
4. **Agent MUST NOT select providers:** Resolution is deterministic based on capability name + version

### 9.5 Discovery Behavior

1. Load all entry points from `sentinel.capability.providers`
2. Validate provider identity/version
3. Validate capability metadata
4. Check host requirements
5. Build local registry
6. Generate canonical manifests/hashes
7. Calculate `capability_set_hash`

### 9.6 Load Failure

- Broken plugin MUST NOT silently replace another
- Load failure MUST be visible/auditable
- Error message MUST be clear

---

## 10. Capability Packs

### 10.1 Definition

A Pack is an administrative grouping, not an authorization primitive. Packs MUST expand to concrete capabilities before final authorization and audit.

```yaml
name: linux-observer
version: "1.0.0"
description: Safe Linux diagnostic capabilities
capabilities:
  - system.info.get
  - system.uptime.get
  - system.resources.get
  - process.list
  - process.inspect
  - filesystem.list
  - filesystem.stat
  - filesystem.read
  - logs.read
  - logs.search
  - service.list
  - service.status
  - network.interfaces.list
  - network.routes.list
  - network.connections.list
  - network.dns.resolve
  - network.ping
  - storage.filesystems.list
  - storage.usage
  - storage.devices.list
```

### 10.2 Pack Membership

Membership SHOULD use a normalized N:M relation:

```text
capability_pack_members
────────────────────────────────
pack_id             UUID FK
capability_id       UUID FK
```

Do not store the canonical membership only as an array of UUID references.

### 10.3 Pack Expansion

Before authorization, a Pack MUST expand into concrete Capabilities. Audit MUST ultimately identify the concrete Capability that executed.

### 10.4 Pack Overrides

Administrators SHOULD usually assign Packs and override selected constraints.

```yaml
packs:
  - linux-observer

overrides:
  logs.read:
    constraints:
      allowed_paths:
        - /var/log/**
    limits:
      max_output_bytes: 1048576

  network.ping:
    constraints:
      allowed_destinations:
        - 172.18.0.0/16
        - 172.19.0.0/16
```

---

## 11. Built-in Linux Observer v1

### 11.1 Capabilities

| Capability | Purpose |
|---|---|
| `system.info.get` | OS/kernel/host information |
| `system.uptime.get` | Uptime/boot information |
| `system.resources.get` | CPU/memory/load overview |
| `process.list` | Bounded process listing |
| `process.inspect` | Inspect one process |
| `filesystem.list` | List allowed directory |
| `filesystem.stat` | Metadata for allowed path |
| `filesystem.read` | Bounded read of allowed file |
| `logs.read` | Bounded log read |
| `logs.search` | Bounded search in allowed logs |
| `service.list` | List services |
| `service.status` | Structured service status |
| `network.interfaces.list` | Interface/address state |
| `network.routes.list` | Routing table |
| `network.connections.list` | Socket/connection state |
| `network.dns.resolve` | DNS lookup |
| `network.ping` | Bounded reachability test |
| `storage.filesystems.list` | Mounted filesystems |
| `storage.usage` | Filesystem usage |
| `storage.devices.list` | Block device inventory |

### 11.2 Providers

```text
linux.system
linux.process
linux.filesystem
linux.logs
linux.systemd
linux.network
linux.storage
```

### 11.3 Security Requirements

Path-aware capabilities MUST defend against traversal, symlink escape, relative paths, normalization ambiguity and prefix tricks. Lexical `startswith()` checks are NOT sufficient.

Network destinations MUST be typed and validated. `network.ping` MUST bound count and timeout. Process inspection MUST NOT become a generic arbitrary `/proc` reader.

---

## 12. Extension Model

### 12.1 Configuration-only

Administrators MAY customize an existing capability without code:

```yaml
logs.read:
  constraints:
    allowed_paths:
      - /var/log/**
      - /opt/application/logs/**
  limits:
    max_output_bytes: 2097152
```

Site configuration MAY narrow built-in constraints. Broadening security-sensitive defaults SHOULD require explicit administrative configuration and MUST be auditable.

### 12.2 Custom Capability

Organizations MAY add semantic operations:

```text
neuralsoft.zfs.replication.status
neuralsoft.postgres.clone.status
```

Custom capabilities MUST implement the same SDK contracts, manifests, schemas, risk metadata, limits and audit behavior.

### 12.3 Custom Provider

Organizations MAY implement an official semantic capability differently. Provider overrides MUST be explicit and deterministic. Silent replacement is forbidden.

---

## 13. Constraints and Limits

### 13.1 Precedence

```text
Capability defaults
        ↓
Global configuration
        ↓
Target Group configuration
        ↓
Target configuration
        ↓
Profile overrides
        ↓
Policy restrictions
        ↓
Authorized request limits
        ↓
Executor local hard limits
        ↓
EFFECTIVE CAPABILITY
```

### 13.2 Numeric Limits

```text
effective_timeout = minimum(applicable timeout limits)
effective_max_output = minimum(applicable output limits)
```

### 13.3 Allow-Lists

Effective value is the **safe intersection** of applicable restrictions, not simple replacement.

Ejemplo:

```text
Profile allowed pools:     Storage01, Storage02
Policy allowed pools:      Storage01
Executor hard allowed pools: Storage01, Storage03

Effective:                 Storage01
```

### 13.4 Composición de Constraints

Los constraints aplicables se combinan de forma **restrictiva**, no mediante reemplazo simple.

Ejemplo:

```text
GLOBAL:
    allowed_paths = /var/log/**

TARGET_GROUP:
    allowed_paths = /var/log/postgresql/**

Resultado efectivo:
    /var/log/postgresql/**
```

Cada `ConstraintsModel` debe definir formalmente su algoritmo de composición.

**NO se debe utilizar un merge JSON genérico para constraints de seguridad.**

### 13.5 Broadening

Normal layers (Profile, Policy, Binding) can only **restrict**. To broaden permissions, the administrator MUST explicitly modify the base configuration/security ceiling of the Capability in the corresponding scope.

### 13.6 Precedencia entre Binding Individual y Pack

No existe una regla de precedencia del tipo `binding individual > Pack`.

Primero, el Pack se expande a sus Capabilities concretas. Luego se evalúan **todas las asignaciones, policies y constraints aplicables a la Capability concreta**.

Un binding adicional no debe convertirse implícitamente en un mecanismo para ampliar un security ceiling establecido por otra capa.

---

## 14. Plugin Development

### 14.1 Package Structure

```text
sentinel-capability-zfs/
├── pyproject.toml
├── README.md
├── tests/
│   ├── test_pool_status.py
│   └── test_contract.py
└── sentinel_zfs/
    ├── __init__.py
    ├── provider.py
    └── capabilities/
        ├── __init__.py
        ├── pool_list.py
        ├── pool_status.py
        ├── dataset_list.py
        └── snapshot_list.py
```

### 14.2 pyproject.toml

```toml
[project]
name = "sentinel-capability-zfs"
version = "1.0.0"
dependencies = ["mcp-sentinel-capability-sdk>=1.0,<2.0"]

[project.entry-points."sentinel.capability.providers"]
zfs = "sentinel_zfs.provider:ZFSProvider"
```

### 14.3 Provider Implementation

```python
from sentinel_sdk import CapabilityProvider
from .capabilities.pool_list import ZFSPoolList
from .capabilities.pool_status import ZFSPoolStatus
from .capabilities.dataset_list import ZFSDatasetList


class ZFSProvider(CapabilityProvider):
    name = "linux.zfs"
    version = "1.0.0"
    capabilities = [ZFSPoolList, ZFSPoolStatus, ZFSDatasetList]
    requirements = [
        Executable(path="/usr/sbin/zpool"),
        Executable(path="/usr/sbin/zfs"),
    ]
```

### 14.4 Capability Implementation

```python
from pydantic import BaseModel, ConfigDict, Field
from sentinel_sdk import Capability, RiskLevel, RiskMetadata


class PoolStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pool: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )


class PoolStatusOutput(BaseModel):
    pool: str
    state: str
    read_errors: int
    write_errors: int
    checksum_errors: int


class PoolStatusConstraints(BaseModel):
    allowed_pools: list[str] = []


class ZFSPoolStatus(Capability):
    name = "zfs.pool.status"
    version = "1.0.0"
    title = "ZFS Pool Status"
    description = "Returns health information for a ZFS pool."

    risk = RiskMetadata(
        level=RiskLevel.READ,
        modifies_system=False,
        accesses_sensitive_data=False,
        requires_privilege=False,
        network_access=False,
    )

    input_model = PoolStatusInput
    output_model = PoolStatusOutput
    constraints_model = PoolStatusConstraints

    async def execute(self, ctx, input):
        result = await ctx.exec(
            executable="/usr/sbin/zpool",
            argv=["status", "-x", input.pool],
            timeout_seconds=10,
            max_output_bytes=1024 * 1024,
        )
        return parse_zpool_status(input.pool, result)
```

### 14.5 Plugin Security Contract

Conforming plugins MUST:
- Never turn Agent-controlled input into shell code
- Never use `shell=True` for Agent-controlled execution
- Avoid `os.system`, `os.popen`, `eval`, `exec`
- Use absolute executables
- Preserve argv boundaries
- Validate typed inputs
- Enforce effective constraints before execution
- Enforce timeout/output limits
- Use controlled child environments
- Prevent Agent-controlled provider selection
- Check host requirements
- Treat results as untrusted data
- Deny unknown/extra fields by default

The SDK should make the safe path easy and dangerous shortcuts difficult.

---

## 15. SDK Tooling

### 15.1 Commands

```bash
sentinel-sdk validate .
sentinel-sdk manifest .
sentinel-sdk test .
```

### 15.2 validate

Checks:
- Absolute executables
- No-shell execution
- Schemas valid
- Risk metadata present
- Limits defined
- Generated manifests valid

### 15.3 manifest

Generates canonical manifest for a capability package.

### 15.4 test

Runs standard SDK contract/security tests.

---

## 16. Capability Discovery

The Executor MUST expose local operator discovery. Minimum CLI semantics:

```text
sentinel-executor capability list
sentinel-executor capability show service.status
sentinel-executor provider list
sentinel-executor plugin list
```

`show` SHOULD render purpose, version, risk, parameters, constraints, limits and provider. Machine-readable JSON SHOULD also be available.

---

## 17. MCP Exposure

MCP tools SHOULD be generated from authorized Capability manifests rather than hand-maintained command definitions.

Where practical, an Agent SHOULD see only capabilities authorized for its effective policy/target context. Tool descriptions MUST describe semantic behavior and relevant limits, without unnecessary provider internals.

Example:

```text
Tool: service_status
Description: Return the current status of an authorized system service.
Input: { service: string }
```

### 17.1 Effective MCP Tools

```text
Global approved Capability Catalog
        ∩
Executor AVAILABLE capabilities
        ∩
Principal authorization
        ∩
Effective constraints
        =
Effective MCP tools
```

When safe and representable, MCP SHOULD expose the **effective/restricted schema** to the Agent, not simply the global schema without restrictions.

The Executor always retains final validation and its local hard constraints, regardless of what the Control Plane has calculated.

---

## 18. Non-Goals and Forbidden Shortcuts

Implementations conforming to this specification MUST NOT introduce any of these shortcuts:

- A `shell.execute` standard capability
- An unrestricted `command.run` capability
- Arbitrary executable path supplied by the Agent
- Arbitrary shell fragments hidden inside a capability argument
- `shell=True` to simplify provider implementation
- Provider selection by the Agent
- Trusting Control Plane validation without Executor re-validation
- Bypassing the registry for built-in operations
- Treating Packs as the final audit identity instead of the concrete capability
- Silently falling back from Capability Protocol v2 to unrestricted legacy execution

If a required operation cannot be safely represented by the current SDK, it SHOULD trigger a specification extension rather than an ad-hoc escape hatch.

---

## 19. Definition of Done

Capability SDK v1 is considered complete when:

1. Core SDK imports independently
2. Capability manifests are schema-validated
3. Registry/provider discovery is deterministic
4. Safe `ExecutionContext.exec()` exists and has adversarial tests
5. Linux Observer built-ins are implemented with structured outputs
6. Capability Packs can be expanded and overridden
7. Protocol v2 requests are signed, verified, expiry/replay protected and executed
8. Control Plane authorizes semantic capabilities rather than raw commands
9. MCP tools can be derived from manifests
10. Audit correlates authorization and execution
11. Security tests demonstrate that Agent-controlled input cannot escape argument boundaries in official providers

---

## 20. Future Specifications

The following are intentionally deferred and SHOULD receive separate specifications rather than expanding v1 implicitly:

- WRITE/DESTRUCTIVE capability catalog
- Privilege execution model
- Windows providers
- Specialized ZFS/PostgreSQL/Docker/OpenStack packs
- Richer approval semantics
- Capability dependencies/composition
- Streaming output
- Long-running jobs
- Transactional/rollback semantics
- Provider isolation/hardening
- Capability signing/distribution
- Third-party capability trust model

---

## 24. Core Design Summary

The v1 architecture is intentionally simple:

```text
                   AGENT
                     |
              semantic request
                     |
                     v
              CONTROL PLANE
         identity / policy / HITL
                     |
           signed authorization
                     |
                     v
                   EXECUTOR
                     |
              verify + validate
                     |
                     v
           CAPABILITY REGISTRY
                     |
                     v
                 PROVIDER
                     |
                     v
            EXECUTION CONTEXT
                     |
                     v
                 TARGET OS
```

The durable abstraction is the **Capability**.

The Control Plane decides **whether** it may run.

The Provider decides **how** it runs.

The Executor ensures the authorized semantic operation is the operation actually executed.

The Agent never needs arbitrary shell access for Capability Protocol v2.
