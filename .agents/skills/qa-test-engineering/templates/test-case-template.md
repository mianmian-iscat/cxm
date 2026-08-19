# Test Case: [TC-XXX]

## Metadata

| Field | Value |
|-------|-------|
| ID | TC-XXX |
| Title | [Descriptive title stating scenario and expected outcome] |
| Module | [Module/Feature name] |
| Type | Unit / Integration / API / E2E / Performance / Security |
| Priority | P0 / P1 / P2 / P3 |
| Requirement | [REQ-XXX] |
| Author | [Name] |
| Status | Planned / Automated / Manual / Blocked |

---

## Test Steps

### Preconditions
- [Required system state before test execution]
- [Required test data]
- [Required services running]

### Steps

```
Given [initial context / system state]
  And [additional context if needed]
When [action performed by user or system]
  And [additional action if needed]
Then [expected primary outcome]
  And [expected side effect 1]
  And [expected side effect 2]
```

### Test Data

**Input:**
```json
{
  "field1": "value1",
  "field2": "value2"
}
```

**Expected Output:**
```json
{
  "status": 201,
  "body": {
    "id": "<generated>",
    "field1": "value1"
  }
}
```

---

## Assertions

| # | Assertion | Type |
|---|-----------|------|
| 1 | [Response status code is 201] | Status |
| 2 | [Response body contains id field] | Structure |
| 3 | [Database record created with correct data] | Side Effect |
| 4 | [Event published to message queue] | Side Effect |

---

## Cleanup
- [Teardown steps to restore system to original state]

---

## Notes
- [Edge cases to consider]
- [Related test cases: TC-YYY, TC-ZZZ]
- [Known limitations]
