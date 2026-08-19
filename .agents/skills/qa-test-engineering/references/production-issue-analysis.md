# Production Issue Analysis Guide

## Table of Contents
1. [Investigation Framework](#investigation-framework)
2. [Evidence Collection](#evidence-collection)
3. [Root Cause Analysis Methods](#root-cause-analysis-methods)
4. [Log Analysis Patterns](#log-analysis-patterns)
5. [Metrics Correlation](#metrics-correlation)
6. [Incident Report Writing](#incident-report-writing)
7. [Regression Test Creation](#regression-test-creation)

---

## Investigation Framework

### The OODA Loop for Incidents

```
Observe → Orient → Decide → Act → Loop
    │         │         │        │
    │         │         │        └─ Apply fix, create regression test
    │         │         └─ Choose investigation path
    │         └─ Form hypotheses from evidence
    └─ Collect timeline, logs, metrics, user reports
```

### Step-by-Step Investigation Process

```
1. STABILIZE (if active incident)
   → Is the system still failing? Take immediate mitigation
   → Rollback, feature flag off, scale up, redirect traffic

2. ESTABLISH TIMELINE
   → When did it start? When was it detected?
   → What changed? (deployments, config, traffic)
   → Who reported it? How many users affected?

3. COLLECT EVIDENCE
   → Application logs (errors, stack traces)
   → Infrastructure metrics (CPU, memory, disk, network)
   → Application metrics (latency, error rate, throughput)
   → Database metrics (slow queries, connections, locks)
   → User reports and screenshots

4. FORM HYPOTHESES
   → List 3-5 possible causes ranked by likelihood
   → For each: what evidence would confirm/refute it?

5. TEST HYPOTHESES
   → Use data, not assumptions
   → Reproduce in staging if possible
   → Correlate timestamps across systems

6. IDENTIFY ROOT CAUSE
   → Distinguish root cause from symptoms
   → Use 5 Whys or Fishbone diagram

7. FIX AND VERIFY
   → Apply fix
   → Verify in staging, then production
   → Create regression test before closing

8. WRITE INCIDENT REPORT
   → Timeline, root cause, fix, action items
   → Share with team for learning
```

---

## Evidence Collection

### What to Collect

| Evidence Type | Where to Find It | What to Look For |
|---|---|---|
| Application Logs | ELK, CloudWatch, Datadog | Error messages, stack traces, request IDs |
| Access Logs | Nginx, ALB, API Gateway | Status codes, response times, request patterns |
| Infrastructure Metrics | Prometheus, Grafana, CloudWatch | CPU spikes, memory leaks, disk I/O |
| Application Metrics | APM (Datadog, New Relic) | Latency p99, error rate, throughput |
| Database Metrics | pg_stat, slow query log | Lock waits, connection pool, query time |
| Deployment History | CI/CD, Git log | What changed and when |
| Dependency Status | Status pages, health checks | Third-party outages |
| User Reports | Support tickets, Slack, error tracking | Patterns in affected users |

### Correlation Pattern

Line up all evidence on the same timeline:

```
Timeline:
14:00 - Deploy v2.3.1 (commit abc123)
14:15 - Error rate starts climbing (0.1% → 2%)
14:20 - First user report: "registration not working"
14:25 - DB connection pool exhaustion alert
14:30 - Investigation begins
14:35 - Root cause identified: missing DB index on email lookup
14:40 - Hotfix deployed (add index)
14:45 - Error rate returns to normal
```

---

## Root Cause Analysis Methods

### Method 1: 5 Whys

Start with the symptom and ask "why" until you reach the root cause:

```
Problem: Users cannot register

Why? → Registration API returns 500 errors
Why? → Database query times out after 30 seconds
Why? → Full table scan on users table for email uniqueness check
Why? → Missing index on users.email column
Why? → Index was dropped during migration v2.3.1

Root Cause: Migration script accidentally dropped the email index
Action: Restore index, add migration test to prevent future index drops
```

### Method 2: Fishbone (Ishikawa) Diagram

Categorize potential causes:

```
                         Registration Failure
                              │
    ┌──────────┬──────────┬───┴───┬──────────┬──────────┐
    │          │          │       │          │          │
  Code    Database   Network  Config   External  Infrastructure
    │          │          │       │          │          │
 - Bug in    - Index   - DNS   - Wrong   - Email   - CPU spike
   validation  missing   issue   env var   service  - Memory leak
 - Null ptr  - Locks   - TLS   - Feature  down     - Disk full
 - Race      - Pool      cert    flag     - Rate
   condition   exhaust   expiry  wrong     limited
```

### Method 3: Change Analysis

What changed between "working" and "not working"?

```
Checklist:
□ Recent deployments (last 24h, last 7d)
□ Configuration changes (env vars, feature flags)
□ Infrastructure changes (scaling, migrations, certificates)
□ Traffic pattern changes (spike, new region, bot traffic)
□ Dependency updates (libraries, APIs, services)
□ Database schema changes (migrations)
□ External service changes (provider outage, API version)
```

---

## Log Analysis Patterns

### Filtering by Severity and Time

```bash
# Find all errors in the last hour
# (Adapt to your log system — examples for structured JSON logs)

# Search for error-level logs
grep '"level":"error"' app.log | tail -50

# Search by time range
grep '2026-03-16T14' app.log | grep '"status":500'

# Search by request ID (for distributed tracing)
grep 'req-abc123' app.log | sort

# Count error types
grep '"level":"error"' app.log | jq '.error_type' | sort | uniq -c | sort -rn
```

### Common Error Patterns

| Pattern | Likely Cause |
|---------|-------------|
| Sudden spike in 500s after deploy | Code bug in new release |
| Gradual increase in latency | Memory leak, connection pool exhaustion |
| Intermittent 503s | Resource contention, race condition |
| All requests from one region failing | DNS, CDN, or network issue |
| 429 responses increasing | Rate limiting triggered, possible abuse |
| Connection refused errors | Service down, port misconfiguration |
| Timeout errors | Slow query, external service delay |

### Structured Log Queries (ELK/Datadog)

```
# Find registration failures
service:user-api AND status:>=400 AND path:/api/register

# Find slow requests
service:user-api AND duration:>5000 AND path:/api/register

# Find correlated errors across services
trace_id:"abc123" AND level:error

# Error rate by endpoint
service:user-api | stats count by path, status | where status >= 400
```

---

## Metrics Correlation

### Key Metric Relationships

```
High Error Rate + Normal Latency
  → Likely: validation bug, authorization issue, bad input
  
High Error Rate + High Latency
  → Likely: database issue, external service timeout, resource exhaustion

Normal Error Rate + High Latency
  → Likely: slow query, N+1, memory pressure, GC pauses

Sudden Drop in Throughput
  → Likely: circuit breaker opened, rate limiter, connection pool exhaustion
```

### Dashboard Checklist for Investigation

1. **Error rate** (by status code: 4xx vs 5xx)
2. **Latency** (p50, p95, p99 — look for p99 divergence)
3. **Throughput** (requests/sec — drop means service issue)
4. **Resource utilization** (CPU, memory, disk, network)
5. **Database** (active connections, query duration, lock waits)
6. **External dependencies** (health check status, response time)
7. **Deployment markers** (vertical lines on graphs showing deploys)

---

## Incident Report Writing

Use the template at `templates/incident-report-template.md`. The key sections:

### Executive Summary (1-2 sentences)
What happened, how long, who was affected.

### Timeline
Chronological events from first symptom to resolution.

### Root Cause
Clear explanation — technical enough for engineers, readable for managers.

### Impact
- Users affected (count or percentage)
- Duration of impact
- Revenue impact (if applicable)
- Data impact (any data loss or corruption?)

### Resolution
What was done to fix it and verify the fix.

### Action Items
| Action | Owner | Due Date | Priority |
|--------|-------|----------|----------|
| Add missing index | @backend-team | 2026-03-17 | P0 |
| Add migration test | @qa-team | 2026-03-20 | P1 |
| Add monitoring alert for query latency | @sre-team | 2026-03-20 | P1 |

### Lessons Learned
- What went well (fast detection, good communication)
- What went poorly (slow investigation, missing monitoring)
- Process improvements

---

## Regression Test Creation

Every production issue must result in at least one new test. This is non-negotiable.

### From Issue to Test

```
Production Issue: Registration fails for emails with + character
Root Cause: Email regex doesn't support + in local part

New Tests to Add:
  1. Unit test: validate_email("user+tag@domain.com") → True
  2. Integration test: POST /api/register with "user+tag@domain.com" → 201
  3. (Optional) Parameterized test with more special character emails
```

### Test Placement Rules

| Root Cause Type | Test Layer | Rationale |
|----------------|------------|-----------|
| Logic bug | Unit test | Fast, precise, catches exact issue |
| API behavior | Integration test | Tests the actual endpoint |
| UI interaction | E2E test | Only if UI was the failure point |
| Performance | Performance test | Add as threshold to k6/Locust |
| Configuration | Integration test | Verify config is loaded correctly |

### Regression Test Template

```python
class TestRegression:
    """Regression tests from production incidents.
    Each test references the incident that caused its creation.
    """

    def test_email_with_plus_character(self, client):
        """Incident INC-2026-042: Registration failed for + emails."""
        response = client.post("/api/register", json={
            "email": "user+tag@domain.com",
            "password": "SecurePass123",
            "name": "Plus Email User"
        })
        assert response.status_code == 201

    def test_concurrent_duplicate_registration(self, client):
        """Incident INC-2026-038: Race condition on duplicate check."""
        import concurrent.futures
        payload = {"email": "race@test.com", "password": "Pass1234", "name": "Race"}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(client.post, "/api/register", json=payload) for _ in range(5)]
            results = [f.result() for f in futures]
        
        created = [r for r in results if r.status_code == 201]
        conflicts = [r for r in results if r.status_code == 409]
        assert len(created) == 1, "Exactly one registration should succeed"
        assert len(conflicts) == 4, "Others should get 409 Conflict"
```
