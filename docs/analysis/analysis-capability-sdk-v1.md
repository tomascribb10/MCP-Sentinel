# Análisis: Capability SDK v1 vs. Estado Actual del Proyecto

**Fecha:** 2026-09-28  
**Especificación:** `docs/capability-sdk-spec.md`  
**Código analizado:** `sentinel/`, `config/`, `docker-compose.yml`, `scripts/`, `docker/`

---

## 1. Inconsistencia y Errores Encontrados

### 1.1 Conflictos de Nomenclatura

| Especificación | Código Actual | Conflicto |
|---|---|---|
| `Agent Command Proxy` | `sentinel_target` (daemon) | La especificación introduce un nombre nuevo para un concepto que ya existe con otro nombre |
| `Capability` | `Command` (en `CommandSet`) | La especificación reemplaza "Command" por "Capability", pero el código actual tiene `Command` como entidad |
| `Pack` | `CommandSet` | La especificación dice "Command Sets se reemplazan por Packs", pero son conceptos diferentes: CommandSet = colección de comandos ejecutables; Pack = agrupación administrativa de capacidades |
| `Provider` | `Driver` | La especificación usa "Provider" para la implementación; el código actual usa "Driver" |
| `Capability Registry` | No existe | Nuevo concepto, no hay equivalente en el código actual |
| `ExecutionContext` | No existe | Nuevo concepto, no hay equivalente en el código actual |

### 1.2 Conflictos de Arquitectura

| Especificación | Código Actual | Conflicto |
|---|---|---|
| Protocolo v2 firmado con capability + arguments | `ExecutionPayload` con command + args | El protocolo actual es command-centric, no capability-centric |
| Proxy ejecuta localmente en el target | `sentinel_target` consume de RabbitMQ | La especificación asume ejecución local, no RPC |
| Control Plane autoriza capacidades | `RBACEngine` autoriza comandos | El motor RBAC actual es command-centric |
| Sin shell en Protocol v2 | `BashDriver` usa subprocess sin shell | El driver actual ya no usa shell=True, pero la especificación lo prohíbe explícitamente |
| MCP tools generadas desde manifests | MCP tools hardcodeadas en `sentinel_mcp_api/main.py` | Las tools actuales son estáticas, no generadas |

### 1.3 Inconsistencia Internas de la Especificación

1. **Section 3.1 vs Section 14:** La Section 3.1 dice "Agent Command Proxy ejecuta una operación ya autorizada localmente", pero la Section 14 describe un protocolo de 12 pasos que incluye verificación de firma, expiry, replay, etc. No está claro si el Proxy es un componente separado o parte del target.

2. **Section 5 vs Section 12:** La Section 5 define nombres de capacidades como `system.info.get`, pero la Section 12 usa los mismos nombres. Sin embargo, la Section 11 (Packs) usa nombres diferentes como `linux-observer` que no aparecen en la Section 5.

3. **Section 6 vs Section 7:** La Section 6 define el manifiesto con `provider.preferred`, pero la Section 7 define la clase `Capability` sin un campo `provider`. No está claro cómo se resuelve el provider.

4. **Section 8 vs Section 9:** La Section 8 define `ExecutionContext.exec()` con `executable: str` y `argv: list[str]`, pero la Section 9 dice "Agent input MUST NOT become shell code". Si el Proxy recibe un executable y argv del Control Plane, ¿cómo se garantiza que no sea shell code? La especificación no aclara si el Proxy construye el executable/argv o si el Control Plane lo envía.

5. **Section 10 vs Section 14:** La Section 10 dice "Agents MUST NOT select providers", pero la Section 14 incluye `provider` en el request. ¿Quién selecciona el provider? ¿El Control Plane? ¿El Proxy?

6. **Section 19 vs Section 20:** La Section 19 dice "Command Sets MUST NOT be removed in the first Capability release", pero la Section 20 prohíbe "silently falling back from Capability Protocol v2 to unrestricted legacy execution". No está claro cómo coexisten ambos modelos sin fallback.

7. **Section 21 vs estructura actual:** La Section 21 sugiere una estructura de directorios completamente diferente (`mcp_sentinel/capability_sdk/`, `mcp_sentinel/capabilities/`, `mcp_sentinel/proxy/`). El código actual tiene `sentinel/sentinel_conductor/`, `sentinel/sentinel_target/`, etc. La especificación dice "Existing project layout SHOULD be respected", pero la estructura propuesta es muy diferente.

### 1.4 Ambigüedades

1. **¿Dónde se ejecuta el Agent Command Proxy?** ¿Es un proceso separado del target? ¿Es el mismo proceso? ¿Es un sidecar?

2. **¿Cómo se comunica el Control Plane con el Proxy?** ¿RabbitMQ? ¿HTTP? ¿gRPC? La especificación no define el transporte.

3. **¿Qué pasa con el `sentinel_target` actual?** ¿Se reemplaza completamente por el Proxy? ¿Se mantiene para legacy?

4. **¿Cómo se migran los Command Sets existentes a Capabilities?** ¿Herramienta de migración? ¿Migración manual?

5. **¿Qué es un "Pack" en términos de base de datos?** ¿Es una tabla nueva? ¿Una vista sobre capacidades?

6. **¿Cómo se versionan las capacidades en el registry?** ¿Semver estricto? ¿Compatibilidad de major version?

7. **¿El Proxy tiene acceso a la base de datos?** La especificación dice que el Control Plane es el único con acceso a DB, pero el Proxy necesita verificar firmas y nonces.

### 1.5 Errores Técnicos

1. **Section 4, Invariante 1:** "Official providers MUST NOT use `shell=True`" — pero `subprocess.run` con `shell=False` y una lista de argv es seguro. La especificación debería mencionar explícitamente que se usa `subprocess.run(..., shell=False)` o equivalente.

2. **Section 8, ExecutionContext.exec():** El parámetro `env: dict[str, str] | None` sugiere que se puede pasar un entorno personalizado, pero la Section 4 dice "unrelated secrets MUST NOT be inherited". No está claro si el entorno es completamente controlado por el SDK o si el caller puede inyectar variables.

3. **Section 14, Protocolo v2:** El campo `authorization.policy_id` sugiere que el Control Plane ya evaluó la política, pero no está claro si el Proxy vuelve a evaluarla o solo confirma.

4. **Section 16, Audit:** "Secrets MUST NOT be logged" — pero no está claro qué constituye un "secret" en el contexto de argumentos de capacidades. ¿Un path es un secret? ¿Un nombre de servicio?

5. **Section 23, CAP-005:** "Safe ExecutionContext" — pero no menciona cómo se manejan los signals, zombies, o procesos huérfanos.

---

## 2. Mapeo: Especificación vs. Código Actual

### 2.1 Componentes

| Especificación | Código Actual | Estado | Acción Requerida |
|---|---|---|---|
| Capability SDK Core | No existe |  Nuevo | Crear desde cero |
| Capability Manifest | No existe | Nuevo | Crear desde cero |
| Capability Registry | No existe | Nuevo | Crear desde cero |
| Stevedore Provider Discovery | `sentinel.target.drivers` (stevedore) | Existe | Adaptar namespace |
| Safe ExecutionContext | No existe | Nuevo | Crear desde cero |
| Path Constraint Library | `Command.allowed_paths` (en RBAC) | Existe | Extraer a librería independiente |
| Linux Observer Pack | `default_command_sets.py` (6 sets) | Existe | Reemplazar por Capabilities |
| Agent Command Proxy | `sentinel_target` | Existe | Reemplazar completamente |
| Control Plane Authorization | `RBACEngine` | Existe | Adaptar a capability-centric |
| MCP Capability Exposure | `sentinel_mcp_api/main.py` | Existe | Generar tools desde manifests |
| Legacy Adapter | No existe | Nuevo | Crear capa de compatibilidad |

### 2.2 Modelos de Datos

| Especificación | Código Actual | Estado | Acción Requerida |
|---|---|---|---|
| Capability | `Command` | Existe | Reemplazar por Capability |
| Pack | `CommandSet` | Existe | Reemplazar por Pack |
| Provider | `Driver` (stevedore) | Existe | Renombrar a Provider |
| Risk Metadata | No existe | Nuevo | Crear |
| Capability Manifest | No existe | Nuevo | Crear |
| ExecutionContext | No existe | Nuevo | Crear |
| CapabilityResult | `ExecutionResult` | Existe | Adaptar |
| Protocol v2 Request | `ExecutionPayload` | Existe | Reemplazar |
| Protocol v2 Result | `ExecutionResult` | Existe | Adaptar |

### 2.3 Flujo de Ejecución

| Paso | Especificación | Código Actual | Diferencia |
|---|---|---|---|
| 1 | Agent solicita capability | MCP tool call | El código actual usa command, no capability |
| 2 | Control Plane autoriza | `RBACEngine.authorize()` | El código actual autoriza comandos, no capacidades |
| 3 | Control Plane firma request | `conductor/crypto.py` firma payload | El código actual firma command+args, no capability+arguments |
| 4 | Proxy verifica firma | `sentinel_target/crypto.py` verifica | Similar, pero el Proxy es un componente nuevo |
| 5 | Proxy resuelve provider | No existe | Nuevo |
| 6 | Proxy valida arguments | `driver.validate_args()` | El código actual valida en el driver, no en el Proxy |
| 7 | Proxy ejecuta | `driver.execute()` | El código actual ejecuta en el driver |
| 8 | Proxy retorna resultado | `report_execution_result` cast | El código actual usa RPC, no retorno directo |

---

## 3. Recomendaciones

### 3.1 Antes de Empezar la Implementación

1. **Definir el transporte Control Plane → Proxy:** ¿RabbitMQ? ¿HTTP? ¿gRPC? Esto es crítico para la arquitectura.

2. **Definir la relación Proxy ↔ Target:** ¿Es el Proxy el mismo proceso que el target? ¿Es un sidecar? ¿Es un componente separado?

3. **Definir la migración de Command Sets a Capabilities:** ¿Herramienta automática? ¿Migración manual? ¿Coexistencia?

4. **Definir el modelo de datos para Packs:** ¿Tabla nueva? ¿Vista? ¿Herencia?

5. **Definir cómo se versionan las capacidades en el registry:** ¿Semver estricto? ¿Compatibilidad de major version?

6. **Definir qué información se incluye en el audit:** ¿Argumentos completos? ¿Hash de argumentos? ¿Solo capability name?

### 3.2 Cambios Necesarios en el Código Actual

1. **Renombrar `sentinel_target` → `sentinel_executor`:** Para alinear con la nomenclatura de la especificación.

2. **Crear `capability_sdk/` como paquete independiente:** Que no dependa de conductor, DB, ni RabbitMQ.

3. **Extraer `RBACEngine` a una librería independiente:** Para que pueda ser usada tanto por el Control Plane como por el Executor.

4. **Crear `capabilities/linux/` con las capacidades read-only:** Empezando con `system.info.get`, `system.uptime.get`, etc.

5. **Adaptar `sentinel_mcp_api` para generar tools desde manifests:** En lugar de tener tools hardcodeadas.

6. **Crear capa de legacy adapter:** Para que los Command Sets existentes sigan funcionando durante la migración.

### 3.3 Riesgos

1. **Complejidad del Protocolo v2:** El protocolo de 12 pasos es complejo. Debe ser implementado cuidadosamente.

2. **Migración de Command Sets:** Los deployments existentes deben seguir funcionando durante la migración.

3. **Doble validación:** La validación en Control Plane y Proxy añade latencia. Debe ser optimizada.

4. **Versionamiento de Capabilities:** Si no se maneja bien, puede causar problemas de compatibilidad.

5. **Falta de especificación del transporte:** Sin definir el transporte, la arquitectura está incompleta.

---

## 4. Conclusión

La especificación Capability SDK v1 es un buen punto de partida, pero tiene varias inconsistencias y ambigüedades que deben ser resueltas antes de empezar la implementación. El código actual es maduro y bien estructurado, pero necesita cambios significativos para alinearse con la nueva arquitectura.

**Recomendación:** Resolver las ambigüedades de la especificación antes de empezar a implementar. Crear un documento de diseño que defina el transporte, la relación Proxy-Target, y la estrategia de migración.
