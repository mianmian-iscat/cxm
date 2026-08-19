# Test Plan: [Project/Feature Name]

## 1. Overview

| Field | Value |
|-------|-------|
| Project | [Project Name] |
| Feature | [Feature Name] |
| Author | [Name] |
| Date | [YYYY-MM-DD] |
| Version | [1.0] |
| Status | Draft / In Review / Approved |

### Objective
[1-2 sentences describing what this test plan covers and the quality goals]

### Scope
**In Scope:**
- [Feature/module 1]
- [Feature/module 2]

**Out of Scope:**
- [Excluded items]

---

## 2. Test Strategy

### Test Types and Coverage

| Test Type | Scope | Tools | Coverage Target |
|-----------|-------|-------|-----------------|
| Unit | [Business logic, validation] | [pytest/Jest] | [80%+] |
| Integration | [API endpoints, DB ops] | [pytest+httpx] | [70%+] |
| E2E | [Critical user journeys] | [Playwright] | [5-10 paths] |
| Performance | [Load-sensitive endpoints] | [k6] | [p95 < 500ms] |
| Security | [Auth, input fields] | [OWASP ZAP/Bandit] | [All auth flows] |

### Test Pyramid Distribution
- Unit: [X]%
- Integration: [X]%
- E2E: [X]%

---

## 3. Feature Risk Assessment

| Feature | Business Impact | Failure Likelihood | Risk Level | Test Depth |
|---------|----------------|-------------------|------------|------------|
| [Feature 1] | Critical/High/Med/Low | High/Med/Low | [P0-P3] | [Test types] |
| [Feature 2] | ... | ... | ... | ... |

---

## 4. Test Cases Summary

### [Module 1 Name]

| TC ID | Title | Type | Priority | Status |
|-------|-------|------|----------|--------|
| TC-001 | [Description] | Unit | P0 | Planned |
| TC-002 | [Description] | Integration | P0 | Planned |

### [Module 2 Name]

| TC ID | Title | Type | Priority | Status |
|-------|-------|------|----------|--------|
| TC-010 | [Description] | Unit | P1 | Planned |

---

## 5. Test Environment

| Environment | Purpose | Configuration |
|-------------|---------|---------------|
| Local | Development testing | [Docker Compose / local services] |
| CI | Automated pipeline | [GitHub Actions / Jenkins] |
| Staging | Pre-production validation | [Staging cluster config] |

### Test Data Strategy
- [How test data is generated / managed]
- [Data cleanup approach]

---

## 6. Quality Gates

| Gate | Trigger | Criteria | Blocks |
|------|---------|----------|--------|
| PR Gate | Pull request | All unit+integration pass, coverage >= 80% | Merge |
| Deploy Gate | Merge to main | All tests pass including E2E | Deployment |
| Release Gate | Pre-release | Performance baselines met, security scan clean | Release |

---

## 7. Schedule

| Phase | Start | End | Deliverables |
|-------|-------|-----|-------------|
| Test planning | [Date] | [Date] | This document |
| Test case design | [Date] | [Date] | Test cases |
| Test automation | [Date] | [Date] | Automated scripts |
| Test execution | [Date] | [Date] | Test results |
| Regression | [Date] | [Date] | Regression report |

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| [Risk 1] | [Impact] | [Mitigation plan] |

---

## 9. Exit Criteria

- [ ] All P0 test cases pass
- [ ] All P1 test cases pass (or documented exceptions)
- [ ] Code coverage meets target (>= 80%)
- [ ] No open P0/P1 bugs
- [ ] Performance baselines met
- [ ] Security scan clean
- [ ] Test report generated and reviewed
