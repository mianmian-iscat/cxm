# Requirement Analysis Guide

## Table of Contents
1. [Analysis Methodology](#analysis-methodology)
2. [Extracting Test Points](#extracting-test-points)
3. [Requirement Traceability](#requirement-traceability)
4. [Risk Assessment](#risk-assessment)
5. [Output Format](#output-format)

---

## Analysis Methodology

### Step-by-Step Process

```
Requirement Document
    │
    ├─ Step 1: Identify Functional Requirements
    │   → What should the system do?
    │   → What are the input/output specifications?
    │   → What are the business rules?
    │
    ├─ Step 2: Identify Non-Functional Requirements
    │   → Performance (response time, throughput)
    │   → Security (authentication, authorization, data protection)
    │   → Usability (accessibility, error messaging)
    │   → Reliability (uptime, error handling, recovery)
    │   → Scalability (concurrent users, data volume)
    │
    ├─ Step 3: Identify Implicit Requirements
    │   → Error handling (what happens when things go wrong?)
    │   → Edge cases (empty inputs, max values, special characters)
    │   → Backward compatibility
    │   → Internationalization / localization
    │
    ├─ Step 4: Classify by Priority & Risk
    │   → Map each requirement to risk level
    │   → Determine test depth for each
    │
    └─ Step 5: Generate Test Point Matrix
        → Output structured test points with traceability
```

### Key Questions to Ask for Each Requirement

**Functional**:
- What is the expected input? What formats are valid?
- What is the expected output? What does success look like?
- What are the business rules and constraints?
- What happens with invalid input?
- Are there dependencies on other features?

**Non-Functional**:
- What is the acceptable response time?
- How many concurrent users must be supported?
- What are the security requirements?
- What compliance standards apply (GDPR, SOC2, PCI-DSS)?
- What is the expected uptime SLA?

**Edge Cases**:
- What if the input is empty, null, or very large?
- What if the user submits the same request twice quickly?
- What if a dependent service is unavailable?
- What happens at system boundaries (max int, max string length)?

---

## Extracting Test Points

### From a Requirement to Test Points

**Example Requirement**: "The system shall allow users to register with email, password, and name. Email must be unique. Password must be at least 8 characters with one uppercase letter and one number."

**Extracted Test Points**:

| ID | Test Point | Type | Priority | Source Req |
|----|-----------|------|----------|------------|
| TP-001 | Valid registration with all fields | Functional/Positive | P0 | REQ-001 |
| TP-002 | Registration with duplicate email rejected | Functional/Negative | P0 | REQ-001 |
| TP-003 | Email format validation (valid patterns) | Functional/Positive | P1 | REQ-001 |
| TP-004 | Email format validation (invalid patterns) | Functional/Negative | P1 | REQ-001 |
| TP-005 | Password minimum length (7 chars rejected) | Boundary | P0 | REQ-001 |
| TP-006 | Password minimum length (8 chars accepted) | Boundary | P0 | REQ-001 |
| TP-007 | Password without uppercase rejected | Functional/Negative | P1 | REQ-001 |
| TP-008 | Password without number rejected | Functional/Negative | P1 | REQ-001 |
| TP-009 | Name field empty | Edge Case | P1 | REQ-001 |
| TP-010 | Name with special characters | Edge Case | P2 | REQ-001 |
| TP-011 | Registration response time < 500ms | Performance | P1 | NFR-001 |
| TP-012 | 100 concurrent registrations | Performance | P2 | NFR-002 |
| TP-013 | SQL injection on email field | Security | P0 | SEC-001 |
| TP-014 | XSS on name field | Security | P0 | SEC-001 |
| TP-015 | Password not returned in response | Security | P0 | SEC-002 |
| TP-016 | Password stored as hash, not plaintext | Security | P0 | SEC-002 |
| TP-017 | Rate limiting (>10 requests/min blocked) | Security | P1 | SEC-003 |

### Techniques for Extracting Test Points

#### 1. Equivalence Partitioning

Divide input into valid and invalid classes, test one representative from each:

```
Email field:
  Valid: standard@domain.com, user+tag@domain.co.uk
  Invalid: no-at-sign, @no-local, user@, user@.com, ""
  
Password field:
  Valid: "Secure123" (meets all rules)
  Invalid-length: "Ab1" (too short)
  Invalid-no-upper: "secure123"
  Invalid-no-number: "SecurePass"
```

#### 2. Boundary Value Analysis

Test at exact boundaries, just below, and just above:

```
Password length (min 8):
  Below boundary: 7 characters → reject
  At boundary: 8 characters → accept
  Above boundary: 9 characters → accept
  Maximum: 128 characters → accept (if defined)
  Over maximum: 129+ characters → reject (if defined)
```

#### 3. State Transition Testing

Map system states and transitions:

```
User Registration States:
  [Anonymous] → register → [Pending Verification]
  [Pending Verification] → verify email → [Active]
  [Pending Verification] → timeout → [Expired]
  [Expired] → re-register → [Pending Verification]
  [Active] → deactivate → [Inactive]
```

#### 4. Decision Table Testing

For requirements with multiple conditions:

```
Registration Decision Table:
| Email Valid | Email Unique | Password Valid | Name Present | Result |
|-------------|-------------|----------------|--------------|--------|
| Y | Y | Y | Y | 201 Created |
| N | - | - | - | 400 Invalid email |
| Y | N | - | - | 409 Duplicate |
| Y | Y | N | - | 400 Invalid password |
| Y | Y | Y | N | 400 Name required |
```

---

## Requirement Traceability

### Traceability Matrix

Every requirement should map to at least one test case, and every test case should trace back to a requirement:

```
REQ-001 (Registration) → TC-001, TC-002, TC-003, TC-004, TC-005
REQ-002 (Email Verify) → TC-010, TC-011, TC-012
NFR-001 (Performance)  → TC-020, TC-021
SEC-001 (Input Safety)  → TC-030, TC-031, TC-032
```

### Coverage Gaps

After mapping, check for:
- Requirements with no test cases (untested features)
- Test cases with no requirements (possibly outdated tests)
- High-risk requirements with insufficient test depth

---

## Risk Assessment

### Risk Scoring Formula

```
Risk Score = Business Impact × Failure Likelihood × Detection Difficulty
```

Each factor scored 1-5:
- **Business Impact**: How badly does failure affect users/revenue?
- **Failure Likelihood**: How likely is this to fail? (complexity, new code, external deps)
- **Detection Difficulty**: How hard is it to detect before production?

### Risk-Based Test Prioritization

| Risk Score | Priority | Testing Depth |
|------------|----------|---------------|
| 60-125 | P0 - Critical | Full coverage: unit + integration + E2E + security |
| 30-59 | P1 - High | Strong coverage: unit + integration |
| 10-29 | P2 - Medium | Standard: unit + selective integration |
| 1-9 | P3 - Low | Basic: unit tests only |

---

## Output Format

When analyzing requirements, output in this structure:

```markdown
# Test Point Analysis: [Feature Name]

## Summary
- Total test points: N
- P0 (Critical): N
- P1 (High): N
- P2 (Medium): N
- P3 (Low): N

## Functional Requirements
| ID | Requirement | Test Points | Risk |
|----|------------|-------------|------|
| ... | ... | ... | ... |

## Non-Functional Requirements
| ID | Requirement | Test Points | Risk |
|----|------------|-------------|------|
| ... | ... | ... | ... |

## Edge Cases & Error Scenarios
| ID | Scenario | Expected Behavior | Priority |
|----|----------|-------------------|----------|
| ... | ... | ... | ... |

## Coverage Gaps
- [List any requirements without adequate test coverage]

## Recommended Test Distribution
- Unit: N test cases
- Integration: N test cases
- E2E: N test cases
- Performance: N test cases
- Security: N test cases
```
