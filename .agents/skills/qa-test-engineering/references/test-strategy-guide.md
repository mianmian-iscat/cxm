# Test Strategy Guide

## Table of Contents
1. [Test Types Deep Dive](#test-types-deep-dive)
2. [Testing Pyramid Rationale](#testing-pyramid-rationale)
3. [Coverage Strategy](#coverage-strategy)
4. [Risk-Based Testing](#risk-based-testing)
5. [CI/CD Integration](#cicd-integration)
6. [Test Environment Strategy](#test-environment-strategy)

---

## Test Types Deep Dive

### 1. Unit Tests

**Purpose**: Verify isolated logic — pure functions, business rules, data transformations.

**Characteristics**:
- Execute in < 100ms per test
- Zero external dependencies (mock everything at the boundary)
- Deterministic — same input always produces same output
- Can run in any order without affecting results

**When to Use**:
- Business rule validation (pricing, discounts, eligibility)
- Data transformation/parsing logic
- State machine transitions
- Utility functions and helpers
- Input validation logic

**Example Scenarios for User Registration**:
```
- Validate email format (valid/invalid patterns)
- Validate password strength rules
- Hash password correctly
- Generate unique user ID
- Format user data for storage
```

**Framework Recommendations**:
| Language | Framework | Config |
|----------|-----------|--------|
| Python | pytest | `pytest.ini` or `pyproject.toml` |
| JavaScript | Vitest / Jest | `vitest.config.ts` / `jest.config.js` |
| Go | testing (stdlib) | Built-in |
| Java | JUnit 5 | `build.gradle` / `pom.xml` |

### 2. Integration Tests

**Purpose**: Validate interactions between components — API endpoints, database operations, message queues, external service calls.

**Characteristics**:
- Execute in < 5s per test
- Use real (or containerized) dependencies when feasible
- Test the contract between components
- May require setup/teardown of test data

**When to Use**:
- API endpoint behavior (request → response → side effects)
- Database CRUD operations and queries
- Message queue publish/consume flows
- Cache read/write/invalidation
- External service integration (with test doubles for third-party)

**Example Scenarios for User Registration API**:
```
- POST /api/register → 201 + user created in DB
- POST /api/register duplicate → 409
- POST /api/register invalid data → 400 with error details
- Registration triggers welcome email event
- User record has correct timestamps and defaults
```

**Test Data Strategy**:
- Use factories/fixtures for consistent test data
- Clean up after each test (transaction rollback or delete)
- Never depend on data from other tests
- Use realistic but synthetic data (no real PII)

### 3. Contract Tests

**Purpose**: Prevent breaking changes in cross-service communication.

**When to Use**:
- Microservice architectures with shared APIs
- API versioning changes
- Schema evolution (OpenAPI, Protobuf, AsyncAPI)
- Consumer-driven contracts

**Tools**: Pact, Specmatic, OpenAPI diff, JSON Schema validation

**Key Principle**: The consumer defines expectations, the provider verifies against them. Neither side can break the contract without the other knowing.

### 4. End-to-End (E2E) Tests

**Purpose**: Validate critical user journeys through the entire stack.

**Characteristics**:
- Execute in 5-30s per test
- Run against a full application stack
- Test real user workflows (not API contracts)
- Expensive to maintain — use sparingly

**When to Use**:
- Critical business flows (registration, login, checkout, payment)
- Multi-step user journeys that cross service boundaries
- Flows where failure has significant business impact

**Limit to 5-10 critical paths** — the "money paths" that generate revenue or are required for core functionality.

**Playwright Best Practices**:
- Use `data-testid` attributes for stable selectors
- Wait for `networkidle` before assertions on dynamic apps
- Use Page Object Model for maintainability
- Run in headless mode in CI
- Capture screenshots and videos on failure

### 5. Performance Tests

**Purpose**: Validate system behavior under load and identify bottlenecks.

**Types**:
| Type | Goal | Duration |
|------|------|----------|
| Load | Behavior under expected traffic | 5-30 min |
| Stress | Breaking point identification | Until failure |
| Soak | Memory leak detection | 2-8 hours |
| Spike | Sudden traffic surge handling | 1-5 min |

**Key Metrics**:
- Response time (p50, p95, p99)
- Throughput (requests/second)
- Error rate under load
- Resource utilization (CPU, memory, connections)

**Tools**: k6 (recommended), Locust, Artillery, JMeter

### 6. Security Tests

**Purpose**: Identify vulnerabilities before attackers do.

**Automated Checks**:
- SQL injection on all input fields
- XSS on all user-generated content
- Authentication bypass attempts
- Authorization boundary testing (horizontal + vertical)
- Secret scanning in codebase
- Dependency vulnerability scanning (Snyk, npm audit)

**For User Registration Specifically**:
```
- Rate limiting on registration endpoint
- Password not stored in plaintext
- Email enumeration prevention
- CAPTCHA or bot protection
- Input sanitization (SQL injection, XSS)
- Secure headers (CORS, CSP, HSTS)
```

---

## Testing Pyramid Rationale

Why push tests down the pyramid?

| Layer | Speed | Cost | Reliability | Feedback Loop |
|-------|-------|------|-------------|---------------|
| Unit | ~10ms | Lowest | Highest | Immediate |
| Integration | ~1s | Low | High | Minutes |
| E2E | ~15s | High | Medium (flaky) | Minutes-Hours |
| Manual | ~Hours | Highest | Varies | Days |

**Rule of thumb**: If you can test it with a unit test, don't use an integration test. If you can test it with an integration test, don't use E2E.

**Exception**: Some behaviors (cross-page navigation, authentication flows, payment) genuinely need E2E validation. Don't force them into lower layers.

---

## Coverage Strategy

### Targets by Risk Level

| Risk Level | Coverage Target | Examples |
|------------|----------------|----------|
| Critical | 95-100% | Auth, payment, data mutation |
| High | 80-90% | Core business logic, API endpoints |
| Medium | 60-80% | Internal tools, admin features |
| Low | 40-60% | Static content, non-critical UI |

### Coverage Types

- **Line Coverage**: Which lines were executed (baseline metric)
- **Branch Coverage**: Which decision branches were taken (more meaningful)
- **Function Coverage**: Which functions were called
- **Path Coverage**: Which execution paths were exercised (ideal but expensive)

Focus on **branch coverage** for business logic — it catches untested conditional paths that line coverage misses.

### What NOT to Chase

- 100% coverage everywhere (diminishing returns after 80%)
- Coverage on auto-generated code
- Coverage on simple getters/setters
- Coverage metrics as the sole quality indicator

---

## Risk-Based Testing

### Risk Assessment Matrix

```
                    Business Impact
                    Low    Medium   High    Critical
Likelihood  High  | Med  | High  | Crit  | Crit  |
            Med   | Low  | Med   | High  | Crit  |
            Low   | Low  | Low   | Med   | High  |
```

### Applying to User Registration

| Feature | Impact | Likelihood | Risk | Test Depth |
|---------|--------|------------|------|------------|
| Email validation | Medium | High | High | Unit + Integration |
| Password hashing | Critical | Low | High | Unit + Security |
| Duplicate detection | High | High | Critical | Integration + E2E |
| Welcome email | Low | Medium | Low | Integration |
| Rate limiting | High | Medium | High | Performance + Integration |
| SQL injection | Critical | Medium | Critical | Security + Integration |

---

## CI/CD Integration

### Pipeline Architecture

```
Pre-commit Hook
    → lint + format + typecheck + secret scan

PR Gate (< 10 min target)
    → unit tests + fast integration tests
    → coverage check (fail if below threshold)
    → contract tests (if applicable)

Merge to Main
    → full unit + integration suite
    → E2E critical paths
    → build verification

Pre-deploy (Staging)
    → full E2E suite
    → performance baseline check
    → security scan (DAST)

Post-deploy (Production)
    → smoke tests (critical paths only)
    → synthetic monitoring
    → canary analysis
```

### Quality Gate Configuration

```yaml
quality_gates:
  pr_gate:
    coverage_threshold: 80
    max_duration_minutes: 10
    required_tests: [unit, integration]
    block_on: [test_failure, coverage_drop]
  
  deploy_gate:
    required_tests: [unit, integration, e2e]
    block_on: [any_failure]
    
  nightly:
    required_tests: [full_suite, performance, security]
    alert_on: [regression, vulnerability]
```

---

## Test Environment Strategy

### Environment Tiers

| Environment | Purpose | Data | Refresh Cycle |
|-------------|---------|------|---------------|
| Local | Developer testing | Synthetic seeds | On demand |
| CI | Automated tests | Ephemeral containers | Per pipeline run |
| Staging | Pre-production validation | Anonymized production snapshot | Weekly |
| Production | Smoke tests + monitoring | Real data | Continuous |

### Test Data Principles

1. **Never use real PII** in test environments
2. **Use factories** for generating consistent, realistic test data
3. **Isolate test data** — each test creates and cleans up its own data
4. **Seed data** should be version-controlled alongside tests
5. **Anonymize** production data before using in staging
