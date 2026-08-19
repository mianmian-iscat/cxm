---
name: qa-test-engineering
version: 0.2.0
description: 全生命周期质量保证（QA）测试工程技能。该技能包括分析需求以提取测试点、制定测试计划和编写测试用例、执行自动化回归测试（涵盖接口、界面及单元测试），以及通过根本原因分析调查生产环境问题。无论用户是否明确提及”QA”，只要其涉及测试规划、测试策略、测试用例生成、基于需求的测试、接口测试、回归测试、生产调试、事件分析或质量保证工作流程，请随时运用此技能。排除：F88/i-FASHION 提测场景请使用 hfz-test-workflow 编排器（十步流程：Step 0 提测声明→Step 1 需求分析→Step 2 用例生成→Step 3 前置造数→Step 4 执行→Step 5 自愈→Step 6 对抗验证→Step 7 报告→Step 8 结果通知→Step 9 缺陷跟进），本 skill 仅用于非 F88 项目的通用 QA 需求。
install_source: aone-kit
install_method: cli
name_zh: 自动化测试
enabled_at: 1781545563516
---

# QA Test Engineering

A comprehensive skill for full-lifecycle quality assurance — from requirement analysis through test execution to production issue investigation.

**Helper Scripts Available**:
- `scripts/scaffold_tests.py` — Generates standardized test project structure (directories, config, fixtures)

**Always run scripts with `--help` first** to see usage. These scripts are black-box tools — invoke directly rather than reading source.

## End-to-End Flow

When the user needs the full QA lifecycle (not just a single task), follow this pipeline. Each step feeds into the next:

```
1. Analyze Requirements  →  Test Point Matrix (with risk levels)
        ↓
1b. Archive to KB         →  Local knowledge card + DingTalk doc (dedup)
        ↓
2. Generate Test Plan    →  Strategy document (types, coverage, gates)
        ↓
3. Generate Test Cases   →  Given/When/Then cases grouped by layer
        ↓
4. Scaffold & Automate   →  Run scaffold_tests.py, then write test code
        ↓
5. Execute & Report      →  Run tests, feed results to report skill
        ↓
6. (If issues found)     →  Investigate, root cause, regression test
```

Each step's output becomes the input for the next. For example, the test point matrix from step 1 drives which test types appear in the test plan (step 2), which drives the specific test cases (step 3).

## Core Workflow

When the user query covers **multiple tasks** (e.g., "write a test plan, generate test cases, and set up automation"), handle them sequentially in the order below. Read the relevant reference file for each task before producing output.

```
User Query → Identify Task Type(s) — may be one or multiple
    │
    ├─ "写测试计划/测试策略"
    │   → Read references/test-strategy-guide.md
    │   → Use templates/test-plan-template.md
    │   → Output structured test plan
    │
    ├─ "分析需求文档"
    │   → Read references/requirement-analysis-guide.md
    │   → Extract functional & non-functional requirements
    │   → Map to test points with risk levels
    │
    ├─ "生成测试用例"
    │   → Read references/test-case-patterns.md
    │   → Generate Given/When/Then cases by test type
    │   → Classify: unit / integration / API / E2E
    │
    ├─ "执行自动化测试"
    │   → Read references/automation-execution.md
    │   → Select framework (pytest / Playwright / k6)
    │   → Write and run test scripts
    │
    ├─ "生成测试报告"
    │   → This skill does NOT generate reports directly
    │   → Delegate to the user's existing report generation skill
    │   → Provide test results data (pass/fail counts, coverage) as input
    │
    └─ "分析线上问题"
        → Read references/production-issue-analysis.md
        → Systematic investigation: timeline → logs → root cause
        → Output incident report with action items
```

## Code Path Ambiguity Self-Check (Mandatory)

When encountering ambiguity about which code path is used (e.g., "does this go through config center or DB?", "does it use API A or API B?"), you MUST self-investigate by searching code, decompiling, or checking references to confirm the actual path. **Never ask the user to confirm which code path is used.** Example: if a DB table doesn't exist causing BLOCKED, but a Diamond config might override the same feature → search the code for references to the relevant key and table name, confirm which path is actually used, then decide the verification strategy. Investigate first, don't ask the user.

## Root Cause: Verify Before Conclude (Mandatory)

When attributing a BLOCKED or FAIL to missing prerequisites such as "code not deployed", "feature not developed", or "branch not merged", you MUST first verify the actual deployment status (branch name, version, release timestamp) before drawing conclusions. Submitted for testing = deployed to pre-prod — this is a fundamental assumption. **Never attribute issues to "code not deployed" without first verifying the deployment status.** If you need to confirm the branch, check the code repository's deployment records or release orders yourself — do not ask the user. **When static code search is insufficient (e.g., tools only search the default branch, release branch paths don't match), you MUST escalate to hands-on verification in the pre-prod environment (run the actual flow and observe behavior). Never stop and ask the user "should I verify in pre-prod?"** — verification is an obligation, not an option. Just go verify, don't ask.

## Quick Reference: Test Types

| Test Type | Purpose | Tools | Coverage Target |
|-----------|---------|-------|-----------------|
| Unit | Isolated logic verification | pytest, Jest, Vitest | 80%+ business logic |
| Integration | Service boundary validation | pytest+httpx, Supertest | 70%+ API endpoints |
| Contract | Cross-service compatibility | Pact, OpenAPI validation | All public APIs |
| E2E | Critical user journey validation | Playwright, Cypress | 5-10 critical paths |
| Performance | Load/stress/soak testing | k6, Locust | All perf-critical endpoints |
| Security | Vulnerability scanning | OWASP ZAP, Bandit | Auth + data mutation flows |

## Test Pyramid

```
           /\
          /E2E\           5-10% - Critical user journeys
         /------\
        / Integr \        15-25% - API, DB, message queues
       /----------\
      / Component  \      20-30% - UI components, modules
     /--------------\
    /     Unit       \    40-60% - Business logic, pure functions
   /------------------\
  /  Static Analysis   \  Foundation - lint, typecheck, secrets scan
 /----------------------\
```

Principle: push tests down the pyramid. Prefer unit tests over E2E when possible — they are faster, cheaper, and more reliable.

## Decision Tree: Choosing Test Approach

```
Feature to test → What type?
    │
    ├─ Pure business logic / data transformation?
    │   → Unit tests (mock external boundaries)
    │   → Target: pytest / Jest with AAA pattern
    │
    ├─ API endpoint?
    │   ├─ Single service? → Integration tests (real DB or test containers)
    │   ├─ Cross-service? → Contract tests (schema validation)
    │   └─ Performance-critical? → Load tests (k6/Locust)
    │
    ├─ User-facing UI flow?
    │   ├─ Single component? → Component tests (Testing Library)
    │   └─ Multi-page journey? → E2E tests (Playwright)
    │
    ├─ Authentication / Authorization?
    │   → Integration + Security tests
    │   → Cover: valid creds, invalid creds, expired tokens, role boundaries
    │
    └─ Data mutation (create/update/delete)?
        → Integration tests with state verification
        → Verify DB state before and after
        → Test rollback on failure
```

## Task 1: Generating a Test Plan

When the user asks for a test plan or test strategy:

1. Read `references/test-strategy-guide.md` for the detailed framework
2. Use `templates/test-plan-template.md` as the output structure
3. Identify the system under test and its boundaries
4. Classify features by risk level (Critical / High / Medium / Low)
5. Map each feature to appropriate test types
6. Define coverage targets and quality gates
7. Specify CI/CD integration points

## Task 2: Analyzing Requirements

When the user provides a requirement document or describes a feature:

1. Read `references/requirement-analysis-guide.md` for methodology
2. Extract functional requirements (what the system should do)
3. Extract non-functional requirements (performance, security, usability)
4. Identify edge cases and error scenarios
5. Assess risk per requirement (business impact x failure likelihood)
6. Output a test point matrix with priority and suggested test type

## Task 2b: Archive Requirement to Knowledge Base (Dedup)

> After analyzing a requirement, automatically archive the PRD / technical document to both local knowledge base and DingTalk knowledge base. Always check for duplicates before archiving.

### Local Knowledge Base

Target path: `~/.qoderwork/skills/qa-test-engineering/references/knowledge-base/features/`

1. **Dedup check**:
   - Read `features/_index.md`, check if a knowledge card with the same name or module already exists
   - Search for requirement keywords in the `features/` directory, matching filenames and content
   - If a matching card exists → update it (append new version content, update `updated` date and `version`)
   - If no match → create a new card following `_TEMPLATE.md` format, numbered as current max + 1

2. **Knowledge card format** (follow `_TEMPLATE.md`):
   ```
   ---
   id: features/{NN}-{slug}
   title: {Requirement name}
   owner: {Author}
   version: 1.0.0
   created: {YYYY-MM-DD}
   updated: {YYYY-MM-DD}
   tags: [requirementId, keywords, module]
   source_sessions: [{requirementId}]
   ---
   # {Requirement name}
   ## Overview
   {PRD core summary}
   ## Details
   {PRD / technical document key information}
   ## Verification
   {How to verify the requirement is correctly implemented}
   ## Related Knowledge
   {Related knowledge card links}
   ```

3. **Update index**: After creating or updating a card, sync update `features/_index.md`

### DingTalk Knowledge Base

Target workspace: F88/i-FASHION knowledge base (workspace_id: `nb9XJ9V6ErBnlzyA`)

1. **Dedup check**:
   - Call dingtalk-doc-rw's `search_docs(keyword=requirement_name)` to search
   - If found → use `update_doc` to update content (append version marker)
   - If not found → use `create_doc` to create new document

2. **Document format**:
   - Name: `[PRD] {Requirement name}（ID: {requirementId}）`
   - Content: PRD / technical document Markdown content, with metadata header (requirementId, date, author)

3. **Invocation** (via dingtalk-doc-rw skill):
   ```python
   # Dedup search
   search_docs(keyword="requirement name")
   # Create
   create_doc(doc_name="[PRD] Requirement name（ID: xxx）", content="...", workspace_id="nb9XJ9V6ErBnlzyA")
   # Update
   update_doc(url="https://alidocs.dingtalk.com/i/nodes/<nodeId>", content="...")
   ```

### Archiving Result Report

After archiving, report to user via IM:
- Local KB: which knowledge card was created/updated
- DingTalk KB: which document was created/updated (with link)
- If duplicate detected: explain existing document info and that it was updated

**Auto-advance**: After archiving, proceed to Task 3 (Generate Test Cases).

## Task 3: Generating Test Cases

When the user needs test cases for a specific feature:

1. Read `references/test-case-patterns.md` for templates and examples
2. Use Given/When/Then format for each test case
3. Cover positive paths, negative paths, edge cases, and boundary values
4. Group by test type: unit, integration, API, E2E
5. Include test data requirements and preconditions
6. For API test cases, provide complete request/response examples

**Example: User Registration API Test Cases**

```
Feature: User Registration

  Positive:
    Given valid email and password (8+ chars, 1 uppercase, 1 number)
    When POST /api/register with { email, password, name }
    Then response 201 with { id, email, created_at }
    And user record exists in database
    And welcome email is queued

  Negative - Invalid Email:
    Given email = "not-an-email"
    When POST /api/register
    Then response 400 with { error: "Invalid email format" }
    And no user record created

  Negative - Duplicate Email:
    Given email already exists in database
    When POST /api/register with same email
    Then response 409 with { error: "Email already registered" }

  Boundary - Password Length:
    Given password = "Aa1" (3 chars, below minimum)
    When POST /api/register
    Then response 400 with { error: "Password must be at least 8 characters" }

  Security - SQL Injection:
    Given email = "test@test.com'; DROP TABLE users;--"
    When POST /api/register
    Then response 400 (input sanitized, no SQL execution)
```

## Task 4: Executing Automated Tests

When the user wants to run or write automated tests:

1. **Scaffold first**: Run `python scripts/scaffold_tests.py --help` to generate a standardized test project structure. This creates directories, config files, and fixture boilerplate so you can start writing tests immediately.
2. Read `references/automation-execution.md` for framework-specific code patterns (pytest, Playwright, k6), CI/CD pipeline configs, and test data management strategies.
3. Determine the test layer (unit / integration / E2E) using the Decision Tree above.
4. Write tests following the patterns from `references/test-case-patterns.md`.
5. Run tests in layered order: static analysis → unit → integration → E2E.

## Task 5: Investigating Production Issues

When the user reports a production issue or incident:

1. Read `references/production-issue-analysis.md` for the investigation framework
2. Follow the systematic approach:

```
Incident → Establish Timeline
    → Collect Evidence (logs, metrics, traces, user reports)
    → Form Hypotheses
    → Test Hypotheses (with data, not assumptions)
    → Identify Root Cause
    → Define Fix + Regression Test
    → Write Incident Report
```

3. Use `templates/incident-report-template.md` for the output structure
4. Every production issue should result in at least one new regression test

## Quality Gates

Define these gates in CI/CD pipelines:

| Gate | Trigger | Tests | Block If |
|------|---------|-------|----------|
| Pre-commit | git commit | lint + typecheck + unit | Any failure |
| PR Gate | Pull request | unit + integration | Coverage < 80% or any failure |
| Pre-deploy | Merge to main | unit + integration + E2E | Any failure |
| Post-deploy | After deployment | Smoke tests (critical paths) | Any critical path failure |
| Scheduled | Nightly/weekly | Full suite + performance + security | Regression detected |

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Do This Instead |
|---|---|---|
| Testing implementation details | Breaks on refactor | Test observable behavior |
| Shared mutable test state | Flaky, order-dependent | Isolate each test |
| `sleep()` in tests | Slow, unreliable | Use explicit waits or events |
| Everything as E2E | Slow, expensive, flaky | Push down the pyramid |
| Coverage as the only KPI | Inflated numbers, low quality | Focus on critical path coverage |
| No test for production bugs | Same bug recurs | Every fix needs a regression test |

## Reference Files

Read these when you need deeper guidance on a specific area. Each file has a table of contents for navigation.

| File | When to Read | Lines |
|------|-------------|-------|
| `references/test-strategy-guide.md` | Generating test plans, choosing test approach | ~300 |
| `references/requirement-analysis-guide.md` | Analyzing requirements, extracting test points | ~240 |
| `references/test-case-patterns.md` | Writing test cases (API, unit, integration, E2E code patterns) | ~480 |
| `references/automation-execution.md` | Setting up frameworks, CI/CD pipelines, running tests | ~480 |
| `references/production-issue-analysis.md` | Investigating incidents, root cause analysis, log analysis | ~330 |

## Templates

| Template | Purpose |
|----------|---------|
| `templates/test-plan-template.md` | Structured test plan document |
| `templates/test-case-template.md` | Individual test case documentation |
| `templates/incident-report-template.md` | Production incident report |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold_tests.py` | Generate test directory structure, config files, and fixture boilerplate |
