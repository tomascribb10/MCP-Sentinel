# MCP-Sentinel — Especificación General

**Fecha:** 2026-09-29  
**Estado:** Draft  
**Audience:** maintainers, contributors, code-generation agents, security reviewers

---

## 1. Visión General

**MCP-Sentinel** es un framework de orquestación y seguridad **Zero Trust** diseñado para permitir que Agentes de IA (operando bajo el Model Context Protocol - MCP) ejecuten capacidades en infraestructura remota de forma auditada, restringida y con validación humana en el bucle (HITL / 2FA) mediante plugins.

### Problema que resuelve

Los agentes de IA necesitan ejecutar operaciones en servidores remotos (diagnósticos, gestión de servicios, lectura de logs), pero esto implica riesgos de seguridad. MCP-Sentinel actúa como un **controlador intermedio** que garantiza que solo se ejecuten capacidades pre-aprobadas.

### Principios

1. **Zero Trust** — Todo está denegado por defecto
2. **Capacidades semánticas** — Los agentes solicitan QUÉ, no CÓMO
3. **Separación de responsabilidades** — Agent, Control Plane y Executor tienen roles claros
4. **Defensa en profundidad** — Validación múltiple, firmas, constraints
5. **Auditoría completa** — Cada operación queda registrada

---

## 2. Arquitectura

### 2.1 Diagrama

```text
┌─────────────────────────────────────────────────────────────────┐
│                        CONTROL PLANE                             │
│                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │sentinel-mcp  │    │sentinel-conductor│    │sentinel-     │  │
│  │-api          │───▶│                  │◀───│scheduler     │  │
│  │(MCP Gateway) │    │ RBAC + 2FA +     │    │              │  │
│  └──────────────┘    │ RSA signing +    │    │ Heartbeat    │  │
│                      │ Audit logs       │    │ tracker +    │  │
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

### 2.2 Componentes

| Componente | Rol | Puerto | Spec |
|---|---|---|---|
| `sentinel-mcp-api` | Gateway MCP (Streamable HTTP) | 8000 | `docs/control-plane-spec.md` |
| `sentinel-admin-api` | API REST para administradores | 8001 | `docs/control-plane-spec.md` |
| `sentinel-conductor` | RBAC, 2FA, RSA signing, auditoría (único con acceso a DB) | N/A (RPC) | `docs/control-plane-spec.md` |
| `sentinel-scheduler` | Heartbeat registry, message routing | N/A (RPC) | `docs/control-plane-spec.md` |
| `sentinel_executor` | Ejecutor de capacidades en hosts destino (sin puertos entrantes) | N/A (RPC) | `docs/executor-spec.md` |
| `sentinel-cli` | CLI basado en `cliff` | N/A | `docs/cli-spec.md` |

### 2.3 Plano de Control vs. Plano de Ejecución

- **Plano de Control:** mcp-api, admin-api, conductor, scheduler. No se ejecuta en nodos destino.
- **Plano de Ejecución:** sentinel_executor. Corre en hosts destino como usuario no privilegiado.

### 2.4 Comunicación

- **Control Plane ↔ Executor:** RabbitMQ (oslo.messaging) — Protocol v2
- **Admin API → Conductor:** RPC vía RabbitMQ
- **MCP API → Conductor:** RPC vía RabbitMQ
- **CLI → Admin API:** HTTP (httpx)

---

## 3. Flujo de Ejecución End-to-End

### Ejemplo: Agent solicita `service.status` para `postgresql`

#### Paso 1: Agent solicita vía MCP

```json
{
  "capability": "service.status",
  "arguments": {"service": "postgresql"}
}
```

#### Paso 2: Control Plane autoriza

1. Verifica identidad del Agent
2. Evalúa policy/bindings
3. Genera `decision_id`
4. Firma request con RSA-SHA256

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

#### Paso 3: Executor recibe y verifica

1. Verifica firma RSA-SHA256
2. Verifica expiry (60 segundos)
3. Verifica nonce (anti-replay)
4. Valida arguments contra input schema
5. Resuelve provider: `linux.systemd`

#### Paso 4: Provider ejecuta

```python
await ctx.exec(
    executable="/usr/bin/systemctl",
    argv=["systemctl", "status", "--", "postgresql"],
    timeout_seconds=10,
    max_output_bytes=1048576,
)
```

#### Paso 5: Resultado retorna al Agent

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
  }
}
```

---

## 4. Modelo de Datos

### 4.1 Diagrama de Relaciones

```text
                        CAPABILITY CATALOG
                               │
                     ┌─────────┴─────────┐
                     │                   │
               capabilities         providers
                     │
           ┌─────────┼──────────┐
           │         │          │
         packs    profiles   configurations
           │         │
           └────┬────┘
                │
             bindings
                │
       principal ↔ target/group


                        EXECUTOR INVENTORY
                               │
                          executors
                               │
                               ▼
                    executor_capabilities
                               │
                    installed/available
                      provider/version


                          AUTHORIZATION
                               │
                      runtime evaluation
                               │
                          decision_id
                               │
                     signed capability request
                               │
                               ▼
                            Executor
                               │
                               ▼
                            audit_log
```

### 4.2 Tablas Principales

| Tabla | Descripción |
|---|---|
| `capabilities` | Catálogo global de capacidades (QUÉ) |
| `providers` | Metadata de providers (CÓMO) |
| `executor_capabilities` | Inventario runtime de capacidades por executor |
| `capability_packs` | Agrupaciones administrativas de capacidades |
| `capability_pack_members` | Membresía N:M de packs |
| `capability_profiles` | Configuraciones restringibles sobre packs |
| `capability_profile_overrides` | Overrides por capability en profiles |
| `capability_configurations` | Configuración por scope (GLOBAL/TARGET_GROUP/TARGET) |
| `bindings` | Asignaciones de autorización (principal + resource + target) |
| `audit_log` | Registro inmutable de eventos |
| `executors` | Registro de executores |
| `targets` | Registro de targets (hosts) con estado y monitoreo |
| `target_groups` | Grupos lógicos de targets |
| `users` | Usuarios administradores |
| `twofa_challenges` | Desafíos 2FA pendientes |

### 4.2.1 Relación Executor-Target

- Un **executor** puede gestionar **0 o N targets**
- Un **target** pertenece a **un solo executor**
- Relación **1:N** (executor → targets)

Ejemplo:

| Executor | Targets | Descripción |
|---|---|---|
| `executor-bastion-01` | `switch-01`, `switch-02`, `router-01` | Bastion gestiona dispositivos de red |
| `executor-web-01` | `web-server-01` | Executor local en servidor web |

### 4.2.2 Estados del Target

| Estado | Descripción | Comportamiento |
|---|---|---|
| `ACTIVE` | Health check OK | Ejecución normal |
| `UNAVAILABLE` | Health check falló 3 veces | Rechazar ejecución inmediato |
| `DEGRADED` | Health check falló 1-2 veces | Ejecutar con advertencia |
| `UNKNOWN` | Nunca monitoreado (best effort) | Intentar ejecución, retornar error si falla |

### 4.2.3 Monitoreo Opccional

El monitoreo de targets es **opcional**:

- **Con monitoreo:** Health check periódico (TCP ping, SNMP, SSH, API)
- **Sin monitoreo:** Estado `UNKNOWN` (best effort) — se intenta la ejecución y se maneja el error si falla

| Target Type | Health Check Default | Timeout |
|---|---|---|
| REMOTE (switch, router) | TCP ping (port 22) | 5s |
| DIRECT (Linux server) | TCP ping (port 22) | 5s |
| VM | Hypervisor API call | 10s |
| Container | Docker API call | 5s |
| Custom | Configurable | Configurable |

### 4.3 Fuentes de Verdad

```text
CODE / EXECUTOR
    ¿Cómo se ejecuta la operación?
    Implementación del provider.

CONTROL PLANE DATABASE
    ¿Qué capacidades existen?
    ¿Cómo se agrupan/configuran?
    ¿Qué Executors las proveen actualmente?

POLICY / AUTHORIZATION
    ¿Quién puede ejecutar qué, dónde y bajo qué restricciones?
```

---

## 5. Seguridad

### 5.1 Invariantes

1. **Input del agente NUNCA se convierte en código shell.** Los providers oficiales NO deben usar `shell=True`, `os.system`, `os.popen`, `eval`, `exec`, o equivalentes.

2. **Argumentos se validan dos veces:** antes de la autorización del Control Plane y nuevamente por el Executor antes de la ejecución.

3. **Denegación por defecto:** capacidades/providers/argumentos desconocidos son rechazados.

4. **Ejecutables absolutos:** los providers oficiales deben usar rutas absolutas y NO resolver a través de un `PATH` controlado por el agente.

5. **Ejecución acotada:** cada ejecución tiene timeout, límites de output y cleanup determinístico.

6. **Entorno restringido:** los entornos de procesos hijos son construidos explícitamente; secretos no relacionados NO deben heredarse.

7. **Sin escalada implícita de privilegios:** los providers NO deben invocar `sudo`, `su`, o equivalentes.

8. **Datos de resultado no son confiables:** el output NO debe ser reinterpretado como instrucciones ejecutables.

### 5.2 Boundary de Confianza

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

### 5.3 Verificación en el Executor (12 pasos)

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

**Fallo en cualquier paso = detener ejecución.**

---

## 6. Nomenclatura

### 6.1 Capacidades

Patrón `<domain>.<resource>.<action>`:

```text
system.info.get
process.list
filesystem.read
logs.read
service.status
network.interfaces.list
storage.usage
```

- Nombres en minúsculas
- Estables y semánticos (no orientados a comandos)
- Namespaces reservados: `system`, `process`, `filesystem`, `logs`, `service`, `network`, `storage`, `package`, `user`, `security`

### 6.2 Providers

Describen CÓMO se implementa una capacidad:

```text
linux.systemd
linux.logs
linux.iproute2
linux.zfs
```

El agente NUNCA ve el provider. Solo ve la capacidad.

### 6.3 Packs

Agrupaciones administrativas, NO primitivas de autorización:

```yaml
name: linux-observer
capabilities:
  - system.info.get
  - process.list
  - logs.read
```

### 6.4 Profiles

Configuraciones restringibles sobre Packs:

```yaml
name: postgres-production-observer
pack: linux-observer
overrides:
  logs.read:
    constraints:
      allowed_paths:
        - /var/log/postgresql/**
```

### 6.5 Bindings

Asignaciones administrativas (NO decisión runtime):

```text
principal: infra-agent
resource:  PACK linux-observer
target:    TARGET_GROUP linux-production
```

---

## 7. Desarrollo

### 7.1 Cómo agregar una capability

1. Crear clase que hereda de `Capability`
2. Definir `name`, `version`, `risk`, `input_model`, `output_model`
3. Implementar `execute(ctx, input)`
4. Registrar en un `CapabilityProvider`
5. Agregar entry point en `pyproject.toml`

Ver: `docs/capability-sdk-spec.md` sección 14

### 7.2 Cómo crear un plugin

1. Crear estructura de paquete (`sentinel-capability-<name>/`)
2. Implementar `CapabilityProvider` con lista de capabilities
3. Definir `requirements` (ejecutables necesarios)
4. Agregar entry point stevedore
5. Tests de contrato y seguridad

Ver: `docs/capability-sdk-spec.md` sección 14

### 7.3 Cómo agregar un Pack

1. Crear YAML con lista de capabilities
2. Importar vía CLI o Admin API
3. Asignar a un principal sobre un target group

Ver: `docs/control-plane-spec.md`

### 7.4 Cómo configurar constraints

```yaml
# Configuración por scope
logs.read:
  constraints:
    allowed_paths:
      - /var/log/**
  limits:
    max_output_bytes: 1048576
```

Ver: `docs/design-decisions.md` sección 7

---

## 8. Referencias

| Documento | Descripción |
|---|---|
| `docs/capability-sdk-spec.md` | Capability SDK (interfaces, modelos, plugins) |
| `docs/protocol-v2-spec.md` | Protocolo v2 (Control Plane ↔ Executor) |
| `docs/control-plane-spec.md` | Control Plane (Conductor, Scheduler, APIs) |
| `docs/executor-spec.md` | Executor |
| `docs/cli-spec.md` | CLI |
| `docs/deployment-spec.md` | Deployment (Docker, Ansible, Config) |
| `docs/testing-spec.md` | Testing strategy |
| `docs/design-decisions.md` | Decisiones de diseño consolidadas |
| `docs/analysis-capability-sdk-v1.md` | Análisis de inconsistencias |

---

## 9. Estado del Proyecto

| Componente | Estado | Spec |
|---|---|---|
| Capability SDK | ✅ Especificado | `docs/capability-sdk-spec.md` |
| Protocolo v2 | ✅ Especificado | `docs/protocol-v2-spec.md` |
| Control Plane | ✅ Especificado | `docs/control-plane-spec.md` |
| Executor | ✅ Especificado | `docs/executor-spec.md` |
| CLI | ✅ Especificado | `docs/cli-spec.md` |
| Deployment | ✅ Especificado | `docs/deployment-spec.md` |
| Testing | ✅ Especificado | `docs/testing-spec.md` |

**Todas las especificaciones están completas.** El siguiente paso es la implementación de los work packages (CAP-001 a CAP-020).

---

## 10. Work Packages

Ver `docs/capability-sdk-spec.md` sección 20 para la lista completa de CAP-001 a CAP-020.

**Phase A — Foundation:** CAP-001 a CAP-006  
**Phase B — Read-only catalog:** CAP-007 a CAP-015  
**Phase C — Distributed execution:** CAP-016 a CAP-018  
**Phase D — Agent integration:** CAP-019  
**Phase E — Release gate:** CAP-020
