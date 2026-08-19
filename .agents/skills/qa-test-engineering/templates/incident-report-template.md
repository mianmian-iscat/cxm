# Incident Report: [INC-YYYY-XXX]

## Executive Summary

| Field | Value |
|-------|-------|
| Incident ID | INC-YYYY-XXX |
| Severity | P0 / P1 / P2 / P3 |
| Status | Investigating / Mitigated / Resolved / Closed |
| Start Time | YYYY-MM-DD HH:MM UTC |
| Detection Time | YYYY-MM-DD HH:MM UTC |
| Resolution Time | YYYY-MM-DD HH:MM UTC |
| Duration | X hours Y minutes |
| Reporter | [Name/System] |
| Incident Commander | [Name] |

**Summary:** [1-2 sentences: what happened, who was affected, how it was resolved]

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| HH:MM | [First symptom or trigger] |
| HH:MM | [Detection / alert fired] |
| HH:MM | [Investigation began] |
| HH:MM | [Root cause identified] |
| HH:MM | [Fix applied] |
| HH:MM | [Verification: system back to normal] |
| HH:MM | [Incident closed] |

---

## Impact

| Metric | Value |
|--------|-------|
| Users Affected | [Count or percentage] |
| Requests Failed | [Count or error rate] |
| Revenue Impact | [Estimated or N/A] |
| Data Impact | [None / Partial / Description] |
| SLA Impact | [Breached / Within SLA] |

---

## Root Cause Analysis

### Root Cause
[Clear, technical explanation of what caused the incident]

### 5 Whys

1. **Why** did [symptom]?
   → Because [direct cause]
2. **Why** did [direct cause]?
   → Because [deeper cause]
3. **Why** did [deeper cause]?
   → Because [deeper cause]
4. **Why** did [deeper cause]?
   → Because [deeper cause]
5. **Why** did [deeper cause]?
   → Because [root cause] ← **This is the root cause**

### Contributing Factors
- [Factor 1: e.g., missing monitoring for this scenario]
- [Factor 2: e.g., no staging test for this migration]

---

## Resolution

### Immediate Fix
[What was done to stop the bleeding]

### Permanent Fix
[What was done to prevent recurrence]

### Verification
[How was the fix verified? In staging? In production?]

---

## Action Items

| # | Action | Owner | Due Date | Priority | Status |
|---|--------|-------|----------|----------|--------|
| 1 | [Regression test for this issue] | [Owner] | [Date] | P0 | Open |
| 2 | [Add monitoring/alert] | [Owner] | [Date] | P1 | Open |
| 3 | [Process improvement] | [Owner] | [Date] | P2 | Open |

---

## Lessons Learned

### What Went Well
- [Fast detection, good communication, etc.]

### What Went Poorly
- [Slow investigation, missing docs, etc.]

### Process Improvements
- [Concrete changes to prevent recurrence]

---

## Regression Tests Added

| Test ID | Description | Type | File |
|---------|-------------|------|------|
| [TC-XXX] | [Test that would catch this issue] | [Unit/Integration] | [tests/regression/test_xxx.py] |
