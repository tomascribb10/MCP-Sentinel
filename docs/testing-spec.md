# MCP-Sentinel — Testing Specification

**Status:** Draft  
**Version:** 1.0.0-draft  
**Target:** All components  
**Audience:** QA, developers, code-generation agents, security reviewers

Normative terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** define implementation requirements.

---

## 1. Purpose

This specification defines the testing strategy for MCP-Sentinel.

> **Security regressions block release. Every security-relevant validation rule MUST have tests.**

---

## 2. Testing Principles

1. **Test security boundaries first** — Input validation, authorization, constraints
2. **Test happy path second** — Normal operation
3. **Test edge cases third** — Boundary values, empty inputs, oversized inputs
4. **Test failure modes fourth** — Timeouts, network failures, invalid data
5. **Automate everything** — No manual-only tests for security

---

## 3. Test Categories

### 3.1 Unit Tests

**Scope:** Individual functions, classes, methods

**Requirements:**
- Fast execution (< 100ms per test)
- No external dependencies (mock everything)
- High coverage (> 80%)
- Deterministic (no randomness without seed)

**Tools:** `pytest`, `pytest-asyncio`, `pytest-cov`

### 3.2 Integration Tests

**Scope:** Component interactions, API endpoints, RPC calls

**Requirements:**
- Use real dependencies (PostgreSQL, RabbitMQ) or realistic mocks
- Test complete flows (request → authorization → execution → result)
- Verify data persistence
- Verify message delivery

**Tools:** `pytest`, `testcontainers`, `httpx`

### 3.3 Security Tests

**Scope:** Adversarial inputs, injection attempts, boundary violations

**Requirements:**
- Test all security invariants
- Test all input validation rules
- Test all authorization paths
- Test all constraint enforcement

**Tools:** `pytest`, custom adversarial test suites

### 3.4 Contract Tests

**Scope:** Plugin interfaces, API schemas, protocol compatibility

**Requirements:**
- Verify plugin implements SDK contract
- Verify API schemas match specification
- Verify protocol versioning works
- Verify backward compatibility

**Tools:** `pytest`, `jsonschema`, `pydantic`

### 3.5 End-to-End Tests

**Scope:** Complete system flows from Agent to Executor

**Requirements:**
- Deploy full stack (Docker Compose)
- Execute real capabilities
- Verify audit trail
- Verify 2FA flow

**Tools:** `pytest`, `docker-compose`, `httpx`

---

## 4. Test Structure

### 4.1 Directory Layout

```text
tests/
├── unit/
│   ├── test_capability_models.py
│   ├── test_capability_registry.py
│   ├── test_constraints.py
│   ├── test_manifest.py
│   ├── test_rbac_engine.py
│   ├── test_crypto.py
│   └── test_execution_context.py
├── integration/
│   ├── test_control_plane.py
│   ├── test_executor.py
│   ├── test_mcp_api.py
│   ├── test_admin_api.py
│   └── test_cli.py
├── security/
│   ├── test_input_validation.py
│   ├── test_authorization.py
│   ├── test_constraints.py
│   ├── test_path_traversal.py
│   ├── test_signature_verification.py
│   └── test_replay_protection.py
├── contract/
│   ├── test_plugin_contract.py
│   ├── test_api_schemas.py
│   └── test_protocol_versioning.py
└── e2e/
    ├── test_full_flow.py
    ├── test_2fa_flow.py
    └── test_plugin_lifecycle.py
```

### 4.2 Naming Conventions

- Test files: `test_<module>.py`
- Test functions: `test_<description>`
- Test classes: `Test<Feature>`
- Fixtures: `<scope>_<name>` (e.g., `unit_mock_capability`)

---

## 5. Security Test Cases

### 5.1 Input Validation

```python
def test_capability_name_rejects_invalid_characters():
    """Capability name MUST only contain lowercase, dots, and alphanumeric."""
    with pytest.raises(ValidationError):
        Capability(name="Invalid_Name!", ...)

def test_capability_name_rejects_uppercase():
    """Capability name MUST be lowercase."""
    with pytest.raises(ValidationError):
        Capability(name="Service.Status", ...)

def test_input_rejects_extra_fields():
    """Input models MUST reject unknown fields."""
    with pytest.raises(ValidationError):
        ServiceStatusInput(service="postgresql", extra_field="value")

def test_input_rejects_wrong_type():
    """Input models MUST reject wrong types."""
    with pytest.raises(ValidationError):
        ServiceStatusInput(service=123)  # Should be string

def test_input_rejects_empty_string():
    """Input models MUST reject empty strings where inappropriate."""
    with pytest.raises(ValidationError):
        ServiceStatusInput(service="")

def test_input_rejects_oversized_input():
    """Input models MUST reject oversized inputs."""
    with pytest.raises(ValidationError):
        ServiceStatusInput(service="a" * 10000)
```

### 5.2 Authorization

```python
def test_rbac_deny_by_default():
    """RBAC MUST deny when no binding exists."""
    result = rbac_engine.authorize(request)
    assert result.denied
    assert result.reason == "no_matching_binding"

def test_rbac_allow_with_valid_binding():
    """RBAC MUST allow when valid binding exists."""
    result = rbac_engine.authorize(request)
    assert result.allowed

def test_rbac_deny_disabled_binding():
    """RBAC MUST deny when binding is disabled."""
    binding.enabled = False
    result = rbac_engine.authorize(request)
    assert result.denied

def test_rbac_deny_wrong_principal():
    """RBAC MUST deny when principal doesn't match."""
    request.principal_id = "wrong-agent"
    result = rbac_engine.authorize(request)
    assert result.denied

def test_rbac_deny_wrong_target():
    """RBAC MUST deny when target doesn't match."""
    request.target_id = "wrong-target"
    result = rbac_engine.authorize(request)
    assert result.denied

def test_rbac_expand_pack_to_capabilities():
    """RBAC MUST expand Pack to concrete capabilities."""
    binding.resource_type = "PACK"
    result = rbac_engine.authorize(request)
    assert result.allowed
    assert result.capability.name == "service.status"
```

### 5.3 Constraints

```python
def test_constraint_allowed_values():
    """Constraints MUST allow values in allowed list."""
    constraints = PoolStatusConstraints(allowed_pools=["Storage01"])
    result = constraints.validate(pool="Storage01")
    assert result.valid

def test_constraint_reject_disallowed_values():
    """Constraints MUST reject values not in allowed list."""
    constraints = PoolStatusConstraints(allowed_pools=["Storage01"])
    with pytest.raises(ConstraintViolationError):
        constraints.validate(pool="Storage03")

def test_constraint_intersection():
    """Effective constraints MUST be intersection of all layers."""
    profile_constraints = {"allowed_pools": ["Storage01", "Storage02"]}
    policy_constraints = {"allowed_pools": ["Storage01"]}
    executor_constraints = {"allowed_pools": ["Storage01", "Storage03"]}
    
    effective = merge_constraints(profile_constraints, policy_constraints, executor_constraints)
    assert effective["allowed_pools"] == ["Storage01"]

def test_constraint_no_broadening():
    """Constraints MUST NOT be broadened by lower layers."""
    base_constraints = {"allowed_pools": ["Storage01"]}
    override_constraints = {"allowed_pools": ["Storage01", "Storage02"]}
    
    effective = merge_constraints(base_constraints, override_constraints)
    assert effective["allowed_pools"] == ["Storage01"]
```

### 5.4 Path Traversal

```python
def test_path_rejects_traversal():
    """Path validation MUST reject directory traversal."""
    with pytest.raises(ConstraintViolationError):
        validate_path("/var/log/../etc/passwd", allowed_paths=["/var/log/**"])

def test_path_rejects_symlink_escape():
    """Path validation MUST reject symlink escape."""
    with pytest.raises(ConstraintViolationError):
        validate_path("/var/log/link_to_etc", allowed_paths=["/var/log/**"])

def test_path_rejects_relative_path():
    """Path validation MUST reject relative paths."""
    with pytest.raises(ConstraintViolationError):
        validate_path("../etc/passwd", allowed_paths=["/var/log/**"])

def test_path_rejects_prefix_confusion():
    """Path validation MUST reject prefix confusion."""
    with pytest.raises(ConstraintViolationError):
        validate_path("/var/log-private/secret", allowed_paths=["/var/log/**"])

def test_path_allows_valid_path():
    """Path validation MUST allow valid paths."""
    result = validate_path("/var/log/syslog", allowed_paths=["/var/log/**"])
    assert result.valid
```

### 5.5 Signature Verification

```python
def test_signature_valid():
    """Signature verification MUST accept valid signatures."""
    envelope = create_signed_envelope(private_key)
    assert verify_envelope(envelope, public_key)

def test_signature_invalid():
    """Signature verification MUST reject invalid signatures."""
    envelope = create_signed_envelope(private_key)
    envelope["security"]["signature"] = "invalid"
    with pytest.raises(SignatureVerificationFailed):
        verify_envelope(envelope, public_key)

def test_signature_tampered_payload():
    """Signature verification MUST reject tampered payloads."""
    envelope = create_signed_envelope(private_key)
    envelope["arguments"]["service"] = "malicious"
    with pytest.raises(SignatureVerificationFailed):
        verify_envelope(envelope, public_key)

def test_signature_expired():
    """Signature verification MUST reject expired requests."""
    envelope = create_signed_envelope(private_key, expires_at=past_time)
    with pytest.raises(RequestExpiredError):
        verify_envelope(envelope, public_key)

def test_signature_replay():
    """Signature verification MUST reject replayed nonces."""
    envelope = create_signed_envelope(private_key)
    nonce_store.add(envelope["security"]["nonce"])
    with pytest.raises(RequestReplayedError):
        verify_envelope(envelope, public_key)
```

### 5.6 Shell Injection

```python
def test_shell_metacharacters_remain_literal():
    """Shell metacharacters MUST remain literal argv data."""
    result = await ctx.exec(
        executable="/bin/echo",
        argv=["echo", "; rm -rf /"],
    )
    assert "; rm -rf /" in result.stdout

def test_no_shell_true():
    """Providers MUST NOT use shell=True."""
    with pytest.raises(AssertionError):
        subprocess.run("echo hello", shell=True)

def test_argument_injection_rejected():
    """Argument injection MUST be rejected."""
    with pytest.raises(ConstraintViolationError):
        ServiceStatusInput(service="postgresql; rm -rf /")

def test_path_injection_rejected():
    """Path injection MUST be rejected."""
    with pytest.raises(ConstraintViolationError):
        validate_path("/var/log/; rm -rf /", allowed_paths=["/var/log/**"])
```

---

## 6. Contract Test Cases

### 6.1 Plugin Contract

```python
def test_plugin_implements_capability():
    """Plugin MUST implement Capability interface."""
    assert hasattr(ZFSPoolStatus, "name")
    assert hasattr(ZFSPoolStatus, "version")
    assert hasattr(ZFSPoolStatus, "risk")
    assert hasattr(ZFSPoolStatus, "input_model")
    assert hasattr(ZFSPoolStatus, "output_model")

def test_plugin_implements_provider():
    """Plugin MUST implement CapabilityProvider interface."""
    assert hasattr(ZFSProvider, "name")
    assert hasattr(ZFSProvider, "version")
    assert hasattr(ZFSProvider, "capabilities")
    assert hasattr(ZFSProvider, "requirements")

def test_plugin_manifest_valid():
    """Plugin MUST generate valid manifest."""
    manifest = generate_manifest(ZFSPoolStatus)
    assert manifest["name"] == "zfs.pool.status"
    assert manifest["version"] == "1.0.0"
    assert manifest["risk"]["level"] == "READ"

def test_plugin_requirements_checked():
    """Plugin requirements MUST be checked."""
    provider = ZFSProvider()
    results = provider.check_requirements()
    assert all(isinstance(r, RequirementResult) for r in results)
```

### 6.2 API Schema Contract

```python
def test_capability_schema_matches_spec():
    """Capability schema MUST match specification."""
    schema = Capability.schema()
    assert "name" in schema["properties"]
    assert "version" in schema["properties"]
    assert "risk" in schema["properties"]

def test_request_schema_matches_protocol():
    """Request schema MUST match Protocol v2."""
    schema = CapabilityRequest.schema()
    assert "protocol_version" in schema["properties"]
    assert "capability" in schema["properties"]
    assert "arguments" in schema["properties"]
    assert "security" in schema["properties"]
```

### 6.3 Protocol Versioning

```python
def test_protocol_version_supported():
    """Protocol MUST support version 2.0."""
    assert is_version_supported("2.0")

def test_protocol_version_unsupported():
    """Protocol MUST reject unsupported versions."""
    with pytest.raises(ProtocolVersionError):
        is_version_supported("3.0")

def test_protocol_backward_compatible():
    """Protocol MUST maintain backward compatibility."""
    # Minor version changes are additive
    assert is_version_supported("2.1")
```

---

## 7. Integration Test Cases

### 7.1 Control Plane

```python
def test_conductor_authorizes_capability():
    """Conductor MUST authorize valid capability requests."""
    request = create_capability_request()
    result = conductor.authorize(request)
    assert result.allowed

def test_conductor_signs_request():
    """Conductor MUST sign capability requests."""
    request = create_capability_request()
    signed = conductor.sign(request)
    assert "signature" in signed["security"]

def test_conductor_logs_audit():
    """Conductor MUST log audit events."""
    request = create_capability_request()
    conductor.process(request)
    audit = get_audit_log(request.request_id)
    assert audit is not None
```

### 7.2 Executor

```python
def test_executor_verifies_request():
    """Executor MUST verify signed requests."""
    request = create_signed_request()
    result = executor.verify(request)
    assert result.valid

def test_executor_rejects_invalid_signature():
    """Executor MUST reject invalid signatures."""
    request = create_signed_request()
    request["security"]["signature"] = "invalid"
    with pytest.raises(SignatureVerificationFailed):
        executor.verify(request)

def test_executor_executes_capability():
    """Executor MUST execute capabilities via SDK."""
    request = create_signed_request()
    result = executor.execute(request)
    assert result.success
```

### 7.3 MCP API

```python
def test_mcp_list_capabilities():
    """MCP API MUST list capabilities."""
    response = mcp_client.call("list_effective_capabilities", {})
    assert "capabilities" in response

def test_mcp_request_capability():
    """MCP API MUST request capabilities."""
    response = mcp_client.call("request_capability", {
        "capability": "service.status",
        "arguments": {"service": "postgresql"}
    })
    assert "request_id" in response
```

### 7.4 Admin API

```python
def test_admin_create_capability():
    """Admin API MUST create capabilities."""
    response = admin_client.post("/capabilities", {
        "name": "test.capability",
        "version": "1.0.0",
        "category": "test"
    })
    assert response.status_code == 201

def test_admin_list_bindings():
    """Admin API MUST list bindings."""
    response = admin_client.get("/bindings")
    assert response.status_code == 200
```

---

## 8. End-to-End Test Cases

### 8.1 Full Flow

```python
def test_full_capability_flow():
    """Complete flow: Agent → Control Plane → Executor → Result."""
    # 1. Agent requests capability
    response = mcp_client.call("request_capability", {
        "capability": "service.status",
        "arguments": {"service": "postgresql"},
        "target_id": "executor-001"
    })
    request_id = response["request_id"]
    
    # 2. Poll for result
    result = None
    for _ in range(30):
        result = mcp_client.call("get_capability_result", {"request_id": request_id})
        if result["success"] is not None:
            break
        time.sleep(1)
    
    # 3. Verify result
    assert result["success"] is True
    assert result["data"]["service"] == "postgresql"
    
    # 4. Verify audit
    audit = admin_client.get(f"/audit-logs?request_id={request_id}")
    assert audit.status_code == 200
```

### 8.2 2FA Flow

```python
def test_2fa_approval_flow():
    """2FA flow: Request → Challenge → Approval → Execution."""
    # 1. Request capability that requires 2FA
    response = mcp_client.call("request_capability", {
        "capability": "service.restart",
        "arguments": {"service": "nginx"},
        "target_id": "executor-001"
    })
    assert response["status"] == "pending_2fa"
    challenge_id = response["challenge_id"]
    
    # 2. Approve via Telegram callback
    approve_2fa(challenge_id)
    
    # 3. Poll for result
    result = poll_for_result(response["request_id"])
    assert result["success"] is True
```

### 8.3 Plugin Lifecycle

```python
def test_plugin_install_discover_execute():
    """Plugin lifecycle: Install → Discover → Execute."""
    # 1. Install plugin
    install_plugin("sentinel-capability-zfs")
    
    # 2. Restart executor
    restart_executor()
    
    # 3. Verify discovery
    capabilities = executor.list_capabilities()
    assert "zfs.pool.status" in [c.name for c in capabilities]
    
    # 4. Execute capability
    result = execute_capability("zfs.pool.status", {"pool": "Storage01"})
    assert result.success
```

---

## 9. Test Execution

### 9.1 Running Tests

```bash
# All tests
pytest tests/

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Security tests only
pytest tests/security/

# With coverage
pytest --cov=sentinel --cov-report=html

# With verbose output
pytest -v

# Specific test
pytest tests/security/test_input_validation.py::test_capability_name_rejects_invalid_characters
```

### 9.2 Coverage Requirements

| Component | Minimum Coverage |
|---|---|
| Capability SDK | 90% |
| Control Plane | 85% |
| Executor | 85% |
| MCP API | 80% |
| Admin API | 80% |
| CLI | 75% |
| **Overall** | **80%** |

### 9.3 CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
      rabbitmq:
        image: rabbitmq:3.13
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest --cov=sentinel --cov-report=xml
      - uses: codecov/codecov-action@v3
```

---

## 10. Security Regression Tests

### 10.1 Definition

Security regression tests verify that previously discovered vulnerabilities do not reoccur.

### 10.2 Requirements

- Every security fix MUST have a regression test
- Regression tests MUST be in `tests/security/`
- Regression tests MUST fail if the vulnerability is reintroduced
- Regression tests MUST be run in CI/CD

### 10.3 Example

```python
def test_regression_cve_2026_0001():
    """Regression test for path traversal vulnerability."""
    # This test MUST fail if the vulnerability is reintroduced
    with pytest.raises(ConstraintViolationError):
        validate_path("/var/log/../../etc/passwd", allowed_paths=["/var/log/**"])
```

---

## 11. Performance Tests

### 11.1 Load Tests

```python
def test_concurrent_capability_requests():
    """System MUST handle concurrent capability requests."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(request_capability, f"service-{i}")
            for i in range(100)
        ]
        results = [f.result() for f in futures]
    assert all(r.success for r in results)
```

### 11.2 Stress Tests

```python
def test_executor_under_load():
    """Executor MUST handle sustained load."""
    start_time = time.time()
    for i in range(1000):
        result = execute_capability("system.info.get")
        assert result.success
    duration = time.time() - start_time
    assert duration < 60  # 1000 requests in < 60 seconds
```

---

## 12. Definition of Done

Testing v1 is complete when:

1. All unit tests pass
2. All integration tests pass
3. All security tests pass
4. All contract tests pass
5. All end-to-end tests pass
6. Coverage meets minimum requirements
7. CI/CD integration works
8. Security regression tests exist for all known vulnerabilities
9. Performance tests pass
10. Test documentation is complete
