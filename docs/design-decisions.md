# MCP-Sentinel — Diseño Consolidado

**Fecha:** 2026-09-28  
**Estado:** Draft  
**Basado en:** `docs/capability-sdk-spec.md` + decisiones de diseño

---

## 1. Terminología

```text
Agent → Control Plane → Executor → Target Host
```

| Componente | Descripción |
|---|---|
| **Agent** | Solicita operaciones semánticas. Nunca envía comandos arbitrarios. |
| **Control Plane** | Autoriza principal + capability + arguments + target. Es dueño de policy/RBAC, HITL, firma y auditoría. |
| **Executor** | Verifica un request autorizado, lo valida nuevamente, resuelve un provider local, aplica constraints/limits y ejecuta. Corre en el host destino. |
| **Target Host** | Host físico, VM o container donde corre el Executor. |

**Nombre definitivo:** `sentinel_executor` (reemplaza `sentinel_target` y `Agent Command Proxy`)

---

## 2. Arquitectura

### 2.1 Componentes

| Componente | Rol | Puerto |
|---|---|---|
| `sentinel-mcp-api` | Gateway MCP (Streamable HTTP) | 8000 |
| `sentinel-admin-api` | API REST para administradores | 8001 |
| `sentinel-conductor` | RBAC, 2FA, firma RSA, auditoría (único con acceso a DB) | N/A (RPC) |
| `sentinel-scheduler` | Heartbeat registry, message routing | N/A (RPC) |
| `sentinel_executor` | Ejecutor de capacidades en hosts destino (sin puertos entrantes) | N/A (RPC) |
| `sentinel-cli` | CLI basado en `cliff` | N/A |

### 2.2 Transporte

- **Control Plane ↔ Executor:** RabbitMQ (oslo.messaging) — patrón OpenStack
- **Admin API → Conductor:** RPC vía RabbitMQ
- **MCP API → Conductor:** RPC vía RabbitMQ
- **CLI → Admin API:** HTTP (httpx)

### 2.3 Flujo de Ejecución

```text
Agent
  |
  | semantic tool call (capability + arguments)
  v
Control Plane
  |
  | identity + policy + optional HITL
  | signed CapabilityRequest
  v
Executor
  |
  +--> verify request (signature, expiry, replay)
  +--> validate arguments again
  +--> resolve provider from local registry
  +--> apply local constraints/limits
  +--> provider.execute()
  +--> ExecutionContext (exec without shell)
  +--> normalize result
  v
Control Plane / Agent
```

---

## 3. Modelo de Datos

### 3.1 Fuentes de Verdad

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

### 3.2 Tablas Principales

#### `capabilities` — Catálogo Global de Capacidades

```text
capabilities
────────────────────────────────
id                  UUID PK
name                TEXT (ej: "service.status")
version             TEXT (ej: "1.0.0")
major_version       INTEGER
title               TEXT
description         TEXT
category            TEXT

risk_level          TEXT (READ/WRITE/DESTRUCTIVE/PRIVILEGED)
modifies_system     BOOLEAN
accesses_sensitive_data BOOLEAN
requires_privilege  BOOLEAN
network_access      BOOLEAN

input_schema        JSONB
output_schema       JSONB
constraint_schema   JSONB

default_constraints  JSONB
default_limits      JSONB

manifest            JSONB
manifest_hash       TEXT

source              TEXT
lifecycle_status    TEXT (DISCOVERED/APPROVED/ENABLED/DISABLED/REVOKED)
enabled             BOOLEAN

created_at          TIMESTAMP
updated_at          TIMESTAMP
```

**Identidad:** `service.status@1`, `logs.read@1`, `zfs.pool.status@1`

**Importante:** Esta tabla describe **qué significa la operación**, no el ejecutable local usado para implementarla. NO contiene `/usr/bin/systemctl`, `/usr/sbin/zpool`, ni fragmentos de shell.

#### `providers` — Metadata de Providers

```text
providers
────────────────────────────────
id                  UUID PK
name                TEXT (ej: "linux.systemd")
version             TEXT (ej: "1.0.0")
source              TEXT
package_name        TEXT
publisher           TEXT
trust_status        TEXT
enabled             BOOLEAN
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

**Nota:** La implementación Python real del provider permanece instalada en los Executors, no en la base de datos del Control Plane.

#### `executor_capabilities` — Inventario Runtime

```text
executor_capabilities
────────────────────────────────
executor_id         TEXT
capability_id       UUID FK
capability_version  TEXT
provider_name       TEXT
provider_version    TEXT
manifest_hash       TEXT
availability_status TEXT (AVAILABLE/UNAVAILABLE/MANIFEST_MISMATCH)
requirements_status TEXT
first_seen_at       TIMESTAMP
last_seen_at        TIMESTAMP
```

**Responde:** ¿Puede este Executor actualmente implementar esta Capability?  
**NO responde:** ¿Puede un Agent usar esta Capability?

#### `capability_packs` — Packs

```text
capability_packs
────────────────────────────────
id                  UUID PK
name                TEXT (ej: "linux-observer")
version             TEXT
description         TEXT
source              TEXT
enabled             BOOLEAN
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

#### `capability_pack_members` — Membresía de Packs

```text
capability_pack_members
────────────────────────────────
pack_id             UUID FK
capability_id       UUID FK
```

**Nota:** Se usa una relación N:M normalizada, no un array de UUIDs.

#### `capability_profiles` — Profiles

```text
capability_profiles
────────────────────────────────
id                  UUID PK
name                TEXT (ej: "postgres-production-observer")
version             TEXT
description         TEXT
pack_id             UUID FK
enabled             BOOLEAN
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

#### `capability_profile_overrides` — Overrides de Profiles

```text
capability_profile_overrides
────────────────────────────────
profile_id          UUID FK
capability_id       UUID FK
constraints         JSONB
limits              JSONB
enabled_override    BOOLEAN
```

#### `capability_configurations` — Configuración por Scope

```text
capability_configurations
────────────────────────────────
id                  UUID PK
scope_type          TEXT (GLOBAL/TARGET_GROUP/TARGET)
scope_id            TEXT
capability_id       UUID FK
enabled             BOOLEAN
constraints         JSONB
limits              JSONB
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

#### `bindings` — Asignaciones de Autorización

```text
bindings
────────────────────────────────
id                  UUID PK
principal_id        TEXT
resource_type       TEXT (CAPABILITY/PACK/PROFILE)
resource_id         UUID
target_type         TEXT (TARGET/TARGET_GROUP)
target_id           TEXT
enabled             BOOLEAN
created_at          TIMESTAMP
created_by          TEXT
updated_at          TIMESTAMP
```

**Nota:** Un binding es una asignación administrativa/policy input, NO la decisión de autorización runtime.

**Versión de Capabilities en Bindings:**

Un binding debe referenciar una **Capability + major version**.

Ejemplo:

```text
service.status@1
```

El binding se aplica a cualquier versión `1.x` compatible instalada/disponible, pero **nunca debe extenderse automáticamente a `2.x`**.

Un cambio de major version requiere una decisión/configuración explícita.

#### `audit_log` — Auditoría

```text
audit_log
────────────────────────────────
id                  UUID PK
request_id          UUID
decision_id         UUID
policy_id           UUID

principal_id        TEXT
target_id           TEXT
executor_id         TEXT
executor_instance_id TEXT

capability_id       UUID
capability_name     TEXT
capability_version  TEXT

provider_name       TEXT
provider_version    TEXT

risk_level          TEXT

approval_id         TEXT
approved_by         TEXT

arguments           JSONB
arguments_hash      TEXT

effective_timeout_seconds   INTEGER
effective_max_output_bytes   INTEGER

started_at          TIMESTAMP
finished_at         TIMESTAMP
duration_ms         INTEGER

success             BOOLEAN
error_code          TEXT

result_size_bytes   INTEGER
output_truncated    BOOLEAN

executor_version    TEXT
created_at          TIMESTAMP
```

### 3.3 Invariantes de Persistencia

1. **NO** almacenar código ejecutable de plugins en la base de datos.
2. **NO** almacenar templates de shell arbitrarios como implementaciones de Capabilities.
3. **NO** tratar la disponibilidad del Executor como autorización.
4. **NO** tratar la membresía de Pack como la identidad final de ejecución/auditoría.
5. **NO** duplicar Capabilities solo para expresar configuración específica de un target.
6. **NO** permitir que un request del Control Plane amplíe los constraints hard locales del Executor.
7. **NO** usar merge genérico de JSON para constraints sensibles a seguridad sin una regla de merge tipada.
8. **NO** autorizar automáticamente una Capability porque un plugin la publicó.
9. **SÍ** preservar el manifest/hash que identifica el contrato semántico que se está autorizando.
10. **SÍ** correlacionar la decisión de política y la ejecución usando `decision_id` y `request_id`.

---

## 4. Capability SDK

### 4.1 Interfaces Base

```python
class Capability(ABC):
    name: str
    version: str
    title: str
    description: str
    risk: RiskMetadata
    input_model: type[CapabilityInput]
    output_model: type[CapabilityOutput]
    constraints_model: type[ConstraintsModel] | None

    @abstractmethod
    async def execute(self, ctx: ExecutionContext, input: CapabilityInput) -> CapabilityResult:
        ...
```

### 4.2 CapabilityProvider

```python
class CapabilityProvider(ABC):
    name: str
    version: str
    capabilities: list[type[Capability]]
    requirements: list[HostRequirement]
```

**Nota:** Un `CapabilityProvider` puede tener múltiples capabilities (ej: `linux.zfs` tiene `zfs.pool.list`, `zfs.pool.status`, etc.).

### 4.2.1 HostRequirement

```python
class Executable:
    path: str           # Debe ser absoluto
    required: bool = True
```

Requisitos mínimos:
- `path` debe ser absoluto
- Verificar que el path exista
- Verificar que sea un archivo ejecutable válido
- Verificar permisos de ejecución aplicables al Executor
- La comprobación **no debe ejecutar el binario** durante discovery

La comprobación de una versión mínima/máxima del ejecutable debe modelarse como un requirement explícito adicional o una extensión bien definida, no ejecutarse implícitamente durante un simple `Executable` check.

### 4.3 ConstraintsModel

```python
class ConstraintsModel(BaseModel):
    """Define constraints configurables para una capability."""
    pass
```

**Decisión:** El developer define el modelo, el admin configura valores.

### 4.4 ExecutionContext

```python
class ExecutionContext(ABC):
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
        ...
```

### 4.5 Manifest Generation

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

### 4.6 Capability Set Hash

El `capability_set_hash` debe ser determinístico.

```text
capability_set_hash = SHA-256(canonical_inventory)
```

El inventario debe ordenarse de forma estable por:

```text
capability_name
capability_version
provider_name
provider_version
```

Cada entrada debe incluir como mínimo:

```text
capability_name
capability_version
manifest_hash
provider_name
provider_version
availability_status
```

Luego se serializa usando la representación canónica definida por la especificación/protocolo y se calcula SHA-256.

**No se debe utilizar concatenación informal de strings.**

Dos Executors con exactamente el mismo inventario relevante deben producir el mismo `capability_set_hash`.

---

## 5. Lifecycle de Capacidades

### 5.1 Estados

```text
DISCOVERED → APPROVED → ENABLED → DISABLED → REVOKED
```

### 5.2 Flujo de Descubrimiento

```text
Executor anuncia name/version/hash
  -> Control Plane conoce el hash?
       SÍ -> registra availability
       NO  -> solicita manifest canónico
              -> almacena como DISCOVERED
              -> aprobación administrativa/trust
              -> APPROVED / ENABLED
```

### 5.3 Plugin Desinstalado

**Decisión:** Cuando un plugin se desinstala, las capabilities quedan en `DISABLED` hasta decisión del admin.

---

## 6. Executor

### 6.1 Identificadores

| Identificador | Descripción | Persistencia | Formato |
|---|---|---|---|
| `executor_id` | ID lógico estable del executor | Se persiste en el host | UUID opaco generado durante enrollment |
| `instance_id` | ID de instancia por proceso | Se genera cada vez (no se persiste) | UUID nuevo en cada startup |

**Reglas:**
- El `executor_id` es un identificador **opaco, estable y persistente**, preferentemente un UUID generado durante el enrollment.
- El hostname **NO** debe utilizarse como identidad primaria del Executor.
- Cambiar el hostname no debe cambiar la identidad del Executor.
- El `executor_id` debe persistirse localmente y sobrevivir reinicios y upgrades.
- Una reinstalación limpia donde se pierda la identidad local debe requerir re-enrollment o recuperación explícita de identidad; no debe crear silenciosamente una identidad nueva como comportamiento normal.
- El `instance_id` se genera nuevamente en cada arranque del proceso Executor y no constituye identidad persistente.

Ejemplo:

```text
executor_id = 4cb6e61e-....     # identidad estable (UUID)
hostname    = spzfs27           # nombre/display metadata
instance_id = 98bd....          # nuevo UUID en cada startup
```

### 6.2 Startup Lifecycle

```text
Executor starts
  + identify host/executor
  + authenticate/enroll
  + load built-in providers
  + discover installed plugins
  + validate capability definitions
  + check provider host requirements
  + build local Capability Registry
  + generate canonical manifests/hashes
  + calculate capability_set_hash
  + REGISTER/synchronize with Control Plane
  + heartbeat
```

### 6.3 REGISTER / SYNC / HEARTBEAT

- **REGISTER:** identidad de startup, `instance_id`, versión del Executor y resumen de inventario.
- **SYNC:** inventario detallado cuando el registry cambia o el Control Plane lo solicita.
- **HEARTBEAT:** mensaje pequeño de liveness.

Ejemplo heartbeat:

```json
{
  "executor_id": "spzfs27",
  "instance_id": "58d391c0-...",
  "sequence": 9381,
  "capability_set_hash": "sha256:ABCDE..."
}
```

Si el hash no cambió, no se retransmite el inventario completo. Un hash cambiado dispara sincronización.

---

## 7. Precedencia de Constraints

### 7.1 Orden

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

### 7.2 Regla de Ampliación

**Las capas normales (Profile, Policy, Binding) solo pueden restringir.**

Para ampliar permisos, el administrador debe modificar **explícitamente** la configuración base/security ceiling de la Capability en el scope correspondiente.

### 7.3 Límites Numéricos

```text
effective_timeout = minimum(applicable timeout limits)
effective_max_output = minimum(applicable output limits)
```

### 7.4 Allow-Lists

El valor efectivo es la **intersección segura** de las restricciones aplicables, no un reemplazo simple.

Ejemplo:

```text
Profile allowed pools:     Storage01, Storage02
Policy allowed pools:      Storage01
Executor hard allowed pools: Storage01, Storage03

Effective:                 Storage01
```

### 7.5 Composición de Constraints

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

Como regla general, las capas normales de configuración/policy sólo pueden mantener o restringir permisos. Para ampliar el security ceiling se requiere una modificación administrativa explícita de la configuración base correspondiente.

### 7.6 Precedencia entre Binding Individual y Pack

No existe una regla de precedencia del tipo `binding individual > Pack`.

Primero, el Pack se expande a sus Capabilities concretas. Luego se evalúan **todas las asignaciones, policies y constraints aplicables a la Capability concreta**.

Ejemplo:

```text
Pack linux-observer
    └── service.status

+

Binding individual
    └── service.status
```

Ambos terminan participando en la evaluación de `service.status@1`. Las restricciones aplicables se combinan de manera restrictiva según el `ConstraintsModel`.

Un binding adicional no debe convertirse implícitamente en un mecanismo para ampliar un security ceiling establecido por otra capa.

---

## 8. Auditoría de Argumentos

### 8.1 Clasificación por Campo

```yaml
input:
  service:
    type: string
    audit: VALUE
  token:
    type: string
    audit: HASH_ONLY
  password:
    type: string
    audit: REDACT
```

### 8.2 Output de Auditoría

```json
{
  "service": "postgresql",
  "token": "sha256:...",
  "password": "[REDACTED]"
}
```

### 8.3 Hash de Argumentos

El `arguments_hash` se calcula como:

```text
arguments_hash = SHA-256(canonical_json(arguments))
```

Se debe usar la misma serialización JSON canónica definida por el protocolo.

El hash se calcula sobre los **argumentos completos originales validados**, antes de aplicar las reglas de auditoría (`VALUE`, `REDACT`, `HASH_ONLY`).

De esta manera, el audit log puede conservar una representación segura/redactada de los argumentos y, simultáneamente, un hash determinístico del conjunto completo.

**Los secretos NO se persisten en texto plano en logs de auditoría.**

---

## 9. Exposición MCP

### 9.1 Tools Efectivas

```text
Global approved Capability Catalog
        ∩
Capabilities available on target Executor
        ∩
Principal policy
        ∩
Target/effective constraints
        =
Effective tools visible/usable by Agent
```

### 9.2 Target/Effective Constraints

`Target/effective constraints` se refiere al conjunto efectivo de restricciones resultante de combinar, según las reglas definidas:

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
Policy / Bindings restrictions
        ↓
Authorized request limits
        ↓
Executor local hard limits
        ↓
EFFECTIVE CAPABILITY
```

Además, para que una Capability pueda exponerse como herramienta MCP para un target concreto, debe estar actualmente disponible en el Executor correspondiente.

Conceptualmente:

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

Cuando sea seguro y representable, el MCP debe exponer al Agent el **schema efectivo/restringido**, no simplemente el schema global sin restricciones.

El Executor conserva siempre la validación final y sus hard constraints locales, independientemente de lo que haya calculado el Control Plane.

### 9.3 Implicación

Una capability destructiva instalada en un host no necesita ser visible para un principal que no tiene autorización.

---

## 10. Seguridad

### 10.1 Invariantes

1. **Input del agente NUNCA se convierte en código shell.**
2. **Argumentos se validan dos veces:** antes de la autorización del Control Plane y nuevamente por el Executor.
3. **Denegación por defecto:** capacidades/providers/argumentos desconocidos son rechazados.
4. **Ejecutables absolutos:** los providers oficiales deben usar rutas absolutas.
5. **Ejecución acotada:** timeout, límites de output y cleanup determinístico.
6. **Entorno restringido:** secretos no relacionados NO deben heredarse.
7. **Sin escalada implícita de privilegios.**
8. **Datos de resultado no son confiables.**

### 10.2 Contrato de Plugins

Los plugins conformantes deben:
- Nunca convertir input controlado por el Agent en código shell
- Nunca usar `shell=True` para ejecución controlada por el Agent
- Evitar `os.system`, `os.popen`, `eval`, `exec`
- Usar ejecutables absolutos
- Preservar límites de argv
- Validar inputs tipados
- Forzar constraints efectivos antes de la ejecución
- Forzar timeout/límites de output
- Usar entornos controlados de hijos
- Prevenir selección de provider controlada por el Agent
- Verificar requisitos del host
- Tratar resultados como datos no confiables
- Denegar campos extra/desconocidos por defecto

---

## 11. Decisiones de Diseño

| Decisión | Resolución |
|---|---|
| Nombre del componente | `sentinel_executor` |
| Transporte | RabbitMQ (patrón OpenStack) |
| Migración | Todo desde cero, no se migra nada |
| ConstraintsModel | Developer define el modelo, admin configura valores |
| Plugin desinstalado | Queda `DISABLED` hasta decisión del admin |
| executor_id | UUID opaco, estable y persistente en el host |
| instance_id | Se genera cada vez (no se persiste) |
| CapabilityProvider | Puede tener múltiples capabilities |
| Precedencia | Capas normales solo restringen. Ampliar requiere modificación explícita de la configuración base |
| Composición de constraints | Combinación restrictiva, no merge JSON genérico |
| Binding individual vs Pack | No hay precedencia; se expande y se evalúan todas las asignaciones |
| Versión en bindings | Major version (ej: `service.status@1`), nunca extiende automáticamente a 2.x |
| Packs | Vista materializada sobre capacidades (relación N:M normalizada) |
| Profiles | Overrides restringibles sobre Packs |
| Bindings | Asignación administrativa, no decisión runtime |
| Audit | Correlación con decision_id, request_id, argument classification |
| HostRequirement | `Executable` con path absoluto, verificación sin ejecutar el binario |
| capability_set_hash | SHA-256(canonical_inventory) con orden estable |
| arguments_hash | SHA-256(canonical_json(arguments)) sobre argumentos completos originales |
| Target/effective constraints | Conjunto efectivo resultante de combinar todas las capas |
| MCP exposure | Schema efectivo/restringido, no schema global |

---

## 12. Referencias

| Documento | Ubicación |
|---|---|
| Especificación Capability SDK | `docs/capability-sdk-spec.md` |
| Análisis de migración | `docs/analysis-capability-sdk-v1.md` |
| AGENTS.md | `AGENTS.md` |
