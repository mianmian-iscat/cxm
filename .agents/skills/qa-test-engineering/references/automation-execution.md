# Automation Execution Guide

## Table of Contents
1. [Framework Selection](#framework-selection)
2. [pytest Setup & Patterns](#pytest-setup--patterns)
3. [Playwright E2E Setup](#playwright-e2e-setup)
4. [k6 Performance Testing](#k6-performance-testing)
5. [Test Execution Strategies](#test-execution-strategies)
6. [CI/CD Pipeline Integration](#cicd-pipeline-integration)
7. [Test Data Management](#test-data-management)

---

## Framework Selection

```
What are you testing?
    │
    ├─ Python backend / API?
    │   → pytest + httpx (async) or requests (sync)
    │   → Install: pip install pytest httpx pytest-cov pytest-asyncio
    │
    ├─ JavaScript/TypeScript backend?
    │   → Vitest or Jest + Supertest
    │   → Install: npm install -D vitest @vitest/coverage-v8
    │
    ├─ Frontend UI / User flows?
    │   → Playwright (recommended) or Cypress
    │   → Install: pip install playwright && playwright install
    │   → Or: npm install -D @playwright/test && npx playwright install
    │
    ├─ Performance / Load?
    │   → k6 (recommended) or Locust (Python)
    │   → Install: brew install k6  OR  pip install locust
    │
    └─ Security scanning?
        → OWASP ZAP (DAST), Bandit (Python SAST), npm audit
```

---

## pytest Setup & Patterns

### Project Structure

```
project/
├── src/                    # Application code
│   ├── models/
│   ├── services/
│   └── api/
├── tests/
│   ├── conftest.py         # Shared fixtures
│   ├── unit/
│   │   ├── test_models.py
│   │   └── test_services.py
│   ├── integration/
│   │   ├── conftest.py     # Integration-specific fixtures (DB, client)
│   │   ├── test_api.py
│   │   └── test_repository.py
│   └── e2e/
│       ├── conftest.py
│       └── test_user_journey.py
├── pyproject.toml
└── requirements-test.txt
```

### Configuration (pyproject.toml)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
markers = [
    "unit: Unit tests (fast, no external deps)",
    "integration: Integration tests (require services)",
    "e2e: End-to-end tests (require full stack)",
    "slow: Tests that take > 5s",
]
addopts = "-v --tb=short --strict-markers"

[tool.coverage.run]
source = ["src"]
omit = ["tests/*", "*/migrations/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

### Shared Fixtures (conftest.py)

```python
import pytest
import httpx

@pytest.fixture(scope="session")
def base_url():
    return "http://localhost:8000"

@pytest.fixture
def client(base_url):
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        yield client

@pytest.fixture
def auth_client(client, base_url):
    """Client with authentication token."""
    response = client.post("/api/login", json={
        "email": "testadmin@test.com",
        "password": "AdminPass123"
    })
    token = response.json()["access_token"]
    with httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0
    ) as auth_client:
        yield auth_client
```

### Running pytest

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Run with coverage report
pytest --cov=src --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_services.py -v

# Run tests matching a pattern
pytest -k "test_registration" -v

# Run with parallel execution
pip install pytest-xdist
pytest -n auto  # auto-detect CPU cores

# Run and stop on first failure
pytest -x

# Run with verbose failure output
pytest --tb=long
```

---

## Playwright E2E Setup

### Installation

```bash
# Python
pip install playwright pytest-playwright
playwright install chromium

# JavaScript
npm install -D @playwright/test
npx playwright install
```

### Configuration (playwright.config.py or conftest.py)

```python
import pytest

@pytest.fixture(scope="session")
def browser_context_args():
    # ignore_https_errors: ONLY for local/staging with self-signed certs. Never in production.
    return {
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }

@pytest.fixture
def page(browser):
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
    )
    page = context.new_page()
    yield page
    page.close()
    context.close()
```

### Running with Server Management

If you have access to `scripts/with_server.py` from the webapp-testing skill, use it:

```bash
# Single server
python scripts/with_server.py \
  --server "uvicorn app.main:app --port 8000" \
  --port 8000 \
  -- pytest tests/e2e/ -v

# Frontend + backend
python scripts/with_server.py \
  --server "cd backend && uvicorn app.main:app --port 8000" --port 8000 \
  --server "cd frontend && npm run dev" --port 3000 \
  -- pytest tests/e2e/ -v
```

### Key Practices

1. **Always wait for networkidle** before interacting with dynamic content
2. **Use data-testid** selectors — they survive refactoring
3. **Screenshot on failure** for debugging:
   ```python
   page.screenshot(path=f"/tmp/failure-{test_name}.png", full_page=True)
   ```
4. **Capture console logs** for debugging:
   ```python
   page.on("console", lambda msg: print(f"BROWSER: {msg.text}"))
   ```

---

## k6 Performance Testing

### Basic Load Test

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 20 },   // Ramp up
    { duration: '1m', target: 20 },    // Sustained
    { duration: '10s', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% under 500ms
    http_req_failed: ['rate<0.01'],    // <1% error rate
  },
};

export default function () {
  const payload = JSON.stringify({
    email: `user-${__VU}-${__ITER}@test.com`,
    password: 'SecurePass123',
    name: 'Load Test User',
  });

  const response = http.post('http://localhost:8000/api/register', payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  check(response, {
    'status is 201': (r) => r.status === 201,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });

  sleep(1);
}
```

### Running k6

```bash
# Run load test
k6 run tests/performance/load_test.js

# Run with custom VUs and duration
k6 run --vus 50 --duration 2m tests/performance/load_test.js

# Output results to JSON
k6 run --out json=results.json tests/performance/load_test.js
```

---

## Test Execution Strategies

### Strategy 1: Layered Execution

```bash
#!/bin/bash
set -e

echo "=== Stage 1: Static Analysis ==="
ruff check src/
mypy src/

echo "=== Stage 2: Unit Tests ==="
pytest tests/unit/ -v --cov=src --cov-report=term-missing

echo "=== Stage 3: Integration Tests ==="
pytest tests/integration/ -v

echo "=== Stage 4: E2E Tests ==="
pytest tests/e2e/ -v --screenshot=on

echo "=== All tests passed ==="
```

### Strategy 2: Parallel by Layer

```bash
# Run unit and integration in parallel (no dependency)
pytest tests/unit/ -v &
UNIT_PID=$!

pytest tests/integration/ -v &
INT_PID=$!

wait $UNIT_PID $INT_PID

# E2E depends on integration passing
pytest tests/e2e/ -v
```

### Strategy 3: Smoke Test for Quick Validation

```python
# tests/smoke/test_health.py
@pytest.mark.smoke
class TestSmoke:
    def test_health_endpoint(self, client):
        assert client.get("/health").status_code == 200

    def test_can_register(self, client):
        response = client.post("/api/register", json={
            "email": f"smoke-{uuid4().hex[:6]}@test.com",
            "password": "Pass1234",
            "name": "Smoke"
        })
        assert response.status_code == 201

    def test_can_login(self, client, known_user_credentials):
        response = client.post("/api/login", json=known_user_credentials)
        assert response.status_code == 200
```

```bash
# Run only smoke tests
pytest -m smoke -v
```

---

## CI/CD Pipeline Integration

### GitHub Actions Example

```yaml
name: Test Pipeline

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install ruff mypy
      - run: ruff check src/
      - run: mypy src/

  unit-tests:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements-test.txt
      - run: pytest tests/unit/ --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v4

  integration-tests:
    runs-on: ubuntu-latest
    needs: lint
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements-test.txt
      - run: pytest tests/integration/ -v
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb

  e2e-tests:
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements-test.txt
      - run: playwright install chromium
      - run: |
          uvicorn app.main:app --port 8000 &
          sleep 5
          pytest tests/e2e/ -v
```

---

## Test Data Management

### Principles

1. **Deterministic**: Same test data produces same results
2. **Isolated**: Each test manages its own data
3. **Realistic**: Data should resemble production (without real PII)
4. **Versioned**: Test data scripts are in version control

### Fixture Lifecycle

```python
@pytest.fixture(scope="session")
def db_engine():
    """One database connection per test session.
    CRITICAL: TEST_DATABASE_URL must NEVER point to a production database.
    """
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(db_engine):
    """Fresh transaction per test — auto-rollback."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

### Synthetic Data Generation

```python
from faker import Faker

fake = Faker()

def generate_user_data(n=10):
    return [
        {
            "email": fake.unique.email(),
            "name": fake.name(),
            "password": "TestPass123",
            "phone": fake.phone_number(),
        }
        for _ in range(n)
    ]
```
