# 📄 DOCUMENTO DE ESPECIFICACIÓN: MCP-Sentinel Framework (v1.1)

## 1. Visión General del Sistema
**MCP-Sentinel** es un sistema de orquestación y seguridad de "Confianza Cero" (Zero Trust) diseñado para permitir que Agentes de IA (operando bajo el Model Context Protocol - MCP) ejecuten comandos en infraestructura remota de forma auditada, restringida y con validación humana en el bucle (HITL / 2FA) mediante plugins.

El diseño se basa estrictamente en la **arquitectura de microservicios distribuidos de OpenStack**.

**Stack Tecnológico Base Obligatorio:**
* **Lenguaje:** Python 3.10+
* **Mensajería Asíncrona:** `oslo.messaging` (sobre RabbitMQ)
* **Configuración:** `oslo.config`
* **Gestión de Plugins (Drivers y 2FA):** `stevedore`
* **CLI Framework:** `cliff` (Command Line Interface Formulation Framework)
* **Validación de Datos:** `pydantic`
* **Persistencia:** SQLAlchemy (PostgreSQL/MariaDB).

---

## 2. Topología de Componentes

El sistema se divide en el Plano de Control, el Plano de Ejecución y las Interfaces de Administración. Ningún componente del Plano de Control se ejecuta en los nodos destino.

### Plano de Control (Centralizado)
1. **`sentinel-mcp-api` (El Gateway IA):** Expone el servidor MCP nativo. Traduce las intenciones del LLM en peticiones de ejecución hacia el bus interno.
2. **`sentinel-admin-api` (El Gateway Administrativo):** API RESTful exclusiva para administradores humanos. Gestiona el CRUD de políticas, grupos, agentes y consulta de logs CADF.
3. **`sentinel-conductor` (El Cerebro y Auditor):**
   * Único componente con acceso a la base de datos central.
   * Evalúa las políticas de acceso (RBAC).
   * Gestiona el motor de **2FA mediante plugins cargados dinámicamente** (ej: DUO Push, Telegram).
   * Firma criptográficamente (RSA-SHA256) los payloads de ejecución antes de enviarlos al bus.
   * Genera logs de auditoría inmutables (formato CADF).
4. **`sentinel-scheduler` (El Enrutador):** Mantiene el estado y heartbeat de los agentes vivos y enruta el mensaje firmado a la cola específica del nodo destino.

### Plano de Ejecución (Distribuido)
5. **`sentinel-agent` (El Ejecutor):**
   * Demonio liviano que corre en los hosts (servidores físicos, VMs, contenedores) como **usuario no privilegiado**.
   * No tiene puertos de red abiertos a la escucha; consume mensajes de su cola en RabbitMQ.
   * **Regla de Oro:** Valida obligatoriamente la firma RSA del payload contra la llave pública del Conductor. Si falla, descarta silenciosamente o lanza alerta.
   * Utiliza `stevedore` para cargar el driver de ejecución correspondiente (`bash`, `openstack_sdk`, `ansible`).

### Herramientas de Operación
6. **`sentinel-cli`:** Cliente de línea de comandos oficial basado en `cliff`. Permite a los sysadmins operar el sistema (ej: `sentinel host list`, `sentinel policy create`).

---

## 3. Modelo de Acceso y Políticas (RBAC Escalable)

El modelo de datos relacional para gestionar accesos se estructura en 3 pilares:

### A. Command Sets (Conjuntos de Comandos)
Agrupa comandos permitidos por función. Todo lo no listado está denegado (*Default Deny*).
```yaml
# command_set: linux_basic_diagnostics
driver: posix_bash
commands:
  - name: read_syslogs
    binary: /usr/bin/tail
    args_regex: "^-n \\d+ /var/log/(nginx|syslog|messages).*$"
    require_2fa: false
  - name: restart_web
    binary: /usr/bin/systemctl
    args_regex: "^restart (nginx|apache2)$"
    require_2fa: true

### B. Host Groups (Grupos de Nodos)
Agrupa agentes por etiquetas o entornos.
```yaml
# host_group: prod_web_servers
labels:
  env: production
  role: web

### C. Role Bindings (Las Políticas)
Vincula quién (IA), qué (Command Set) y dónde (Host Group).
```yaml
# policy: ia_web_operator_policy
principal: "llm-agent-claude"
command_set: "linux_basic_diagnostics"
target_group: "prod_web_servers"

* Lógica del Conductor: Cuando la IA pide hacer systemctl restart nginx en web-node-05, el Conductor verifica si el nodo pertenece a prod_web_servers, si la IA tiene el rol asignado, y si el comando coincide con el regex. Si todo es OK, chequea el flag require_2fa.

## 4. Arquitectura de Plugins (Stevedore Namespaces)
La IA generadora de código debe configurar los entry_points en el archivo setup.cfg para extender las funcionalidades sin tocar el core:

# Namespace 1: Drivers de Ejecución (sentinel.agent.drivers)

  * bash = sentinel.agent.drivers.posix:BashDriver

  * ansible = sentinel.agent.drivers.ansible:AnsibleRunnerDriver

# Namespace 2: Proveedores de 2FA (sentinel.auth.providers)

  * duo = sentinel.conductor.auth.duo:DuoPushProvider

  * telegram = sentinel.conductor.auth.telegram:TelegramBotProvider

* Contrato del Plugin 2FA (BaseAuthProvider):
Debe implementar el método asíncrono issue_challenge(user_id, context) y verify_challenge(challenge_id).

## 5. Contratos de Datos (JSON Schemas)
Payload de Mensajería (oslo.messaging Contract)
```yaml
{
  "message_id": "uuid-v4",
  "context": {
    "initiator_id": "llm-agent-claude",
    "2fa_verified": true,
    "2fa_provider_used": "duo"
  },
  "execution": {
    "driver": "posix_bash",
    "command": "/usr/bin/systemctl",
    "args": ["restart", "nginx"],
    "limits": { "timeout_seconds": 30, "max_stdout_bytes": 1048576 }
  },
  "security": {
    "signature": "base64-encoded-rsa-signature",
    "timestamp": 1740493800
  }
}

## 6. Instrucciones para la IA Generadora de Código
Al momento de programar los módulos basados en esta especificación, sigue estas directivas:

  1. Modularidad: Crea la estructura sentinel/mcp_api/, sentinel/admin_api/, sentinel/conductor/, sentinel/agent/, sentinel/cli/.

  2. Sistema de Plugins: Implementa clases base abstractas estandarizadas (BaseDriver y BaseAuthProvider) para que Stevedore las cargue sin errores.

  3. Seguridad de Mensajes: El sentinel-agent JAMÁS debe confiar en un mensaje de RabbitMQ sin validar la firma RSA de sentinel-conductor.

  4. CLI (Cliff): El código de sentinel-cli debe usar las clases Lister y ShowOne del framework cliff para formatear las tablas de salida.

  5.  2FA Asíncrono: El Conductor no debe bloquearse esperando a que el humano acepte el Push de DUO. Debe cambiar el estado de la tarea a PENDING_2FA y exponer un webhook de callback o hacer polling en un thread separado.