# AGENTS.md — MCP-Sentinel

**Para agentes de código, contribuidores y maintainers.**

---

## ¿Qué es MCP-Sentinel?

Framework de orquestación y seguridad **Zero Trust** para agentes de IA que operan bajo el protocolo **MCP (Model Context Protocol)**.

**Principio fundamental:** Los agentes de IA nunca envían comandos arbitrarios. En su lugar, solicitan **capacidades semánticas** que son autorizadas por el Control Plane y ejecutadas por el Executor.

```
Agent → solicita capability → Control Plane autoriza → Executor ejecuta
```

---

## Cómo trabajar en este proyecto

1. **Leer `docs/spec-overview.md` primero** — Es la especificación general end-to-end
2. **Leer la especificación del componente** antes de codificar
3. **No romper los invariantes de seguridad** (ver spec-overview.md sección 5)
4. **Agregar tests** para toda regla de validación relevante para seguridad
5. **No introducir ejecución de shell arbitraria** como atajo
6. **Documentar conflictos** entre código y especificación antes de hacer cambios

---

## Invariantes de Seguridad (Resumen)

1. Input del agente NUNCA se convierte en código shell
2. Argumentos se validan dos veces (Control Plane + Executor)
3. Denegación por defecto
4. Ejecutables absolutos
5. Ejecución acotada (timeout, output limits)
6. Entorno restringido
7. Sin escalada implícita de privilegios
8. Datos de resultado no son confiables

**Ver detalle en:** `docs/spec-overview.md` sección 5

---

## Convenciones

### Código
- **Estilo:** PEP 8, con `black` y `ruff`
- **Type hints:** Obligatorio en APIs públicas
- **Async:** Usar `async/await` para I/O
- **Pydantic:** v2 para validación de datos
- **Tests:** Cobertura mínima 80%

### Commits
- Mensajes en español o inglés
- Formato: `<tipo>: <descripción>`
- Tipos: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

### Documentación
- Toda capacidad debe tener un manifiesto YAML
- Toda API debe tener documentación OpenAPI
- Toda decisión de diseño debe estar documentada en `docs/`

---

## Referencias

| Documento | Descripción |
|---|---|
| `docs/spec-overview.md` | **Espec general end-to-end** (empezar aquí) |
| `docs/specs/capability-sdk-spec.md` | Capability SDK |
| `docs/specs/protocol-v2-spec.md` | Protocolo v2 (Control Plane ↔ Executor) |
| `docs/specs/control-plane-spec.md` | Control Plane (Conductor, Scheduler, APIs) |
| `docs/specs/executor-spec.md` | Executor |
| `docs/specs/cli-spec.md` | CLI |
| `docs/specs/deployment-spec.md` | Deployment (Docker, Ansible, Config) |
| `docs/specs/testing-spec.md` | Testing strategy |
| `docs/specs/design-decisions.md` | Decisiones de diseño consolidadas |
| `docs/analysis/analysis-capability-sdk-v1.md` | Análisis de inconsistencias |
| `docs/plans/capability-sdk-v1.md` | Plan de implementación (work packages) |

---

## Reglas para Agentes de Código

1. **Leer este documento y `docs/spec-overview.md` antes de generar código.**
2. **No romper los invariantes de seguridad.**
3. **No introducir ejecución de shell arbitraria** como atajo.
4. **No rediseñar subsistemas no relacionados.**
5. **Preservar compatibilidad hacia atrás** a menos que el work package lo indique explícitamente.
6. **Preferir interfaces tipadas** sobre diccionarios genéricos en boundaries de seguridad.
7. **Agregar tests** para toda regla de validación relevante para seguridad.
8. **Si el repositorio entra en conflicto con la especificación**, documentar el conflicto antes de hacer cambios arquitectónicos.
9. **No implementar capacidades futuras** solo porque el SDK lo permite.
10. **Mantener el Capability SDK independiente** de transporte y persistencia del Control Plane.
11. **Actualizar la bitácora** en `docs/plans/capability-sdk-v1.md` al completar cada work package.
