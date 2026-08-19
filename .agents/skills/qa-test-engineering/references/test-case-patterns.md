# Test Case Patterns

## Table of Contents
1. [Test Case Format](#test-case-format)
2. [API Test Patterns](#api-test-patterns)
3. [Unit Test Patterns](#unit-test-patterns)
4. [Integration Test Patterns](#integration-test-patterns)
5. [E2E Test Patterns](#e2e-test-patterns)
6. [Common Test Data Patterns](#common-test-data-patterns)

---

## Test Case Format

### Standard Format: Given/When/Then

```
Test Case ID: TC-XXX
Title: [Descriptive name that states the scenario and expected outcome]
Priority: P0 | P1 | P2 | P3
Type: Unit | Integration | API | E2E | Performance | Security
Preconditions: [Setup required before test execution]

Given [initial context / state]
When [action or event occurs]
Then [expected outcome / assertion]
And [additional assertions if needed]

Test Data:
  - Input: { ... }
  - Expected Output: { ... }

Cleanup: [Teardown steps if needed]
```

### Naming Convention

Test names should describe the scenario, not the implementation:

```
Good:
  test_registration_succeeds_with_valid_email_and_password
  test_registration_fails_when_email_already_exists
  test_registration_rejects_password_shorter_than_8_chars

Bad:
  test_register
  test_post_endpoint
  test_validation
```

---

## API Test Patterns

### Pattern 1: CRUD Operations

```python
import pytest
import httpx

BASE_URL = "http://localhost:8000/api"

class TestUserCRUD:
    """Full CRUD lifecycle for user resource."""

    def test_create_user(self, client):
        response = client.post(f"{BASE_URL}/users", json={
            "email": "create@test.com",
            "password": "SecurePass123",
            "name": "Create Test"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "create@test.com"
        assert "password" not in data  # password never in response
        assert "id" in data
        return data["id"]

    def test_read_user(self, client, created_user_id):
        response = client.get(f"{BASE_URL}/users/{created_user_id}")
        assert response.status_code == 200
        assert response.json()["id"] == created_user_id

    def test_update_user(self, client, created_user_id):
        response = client.put(f"{BASE_URL}/users/{created_user_id}", json={
            "name": "Updated Name"
        })
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_delete_user(self, client, created_user_id):
        response = client.delete(f"{BASE_URL}/users/{created_user_id}")
        assert response.status_code == 204
        # Verify deletion
        response = client.get(f"{BASE_URL}/users/{created_user_id}")
        assert response.status_code == 404
```

### Pattern 2: Error Response Validation

```python
class TestRegistrationErrors:
    """Validate all error responses for registration endpoint."""

    @pytest.mark.parametrize("payload,expected_status,expected_error", [
        # Missing required fields
        ({}, 400, "email is required"),
        ({"email": "a@b.com"}, 400, "password is required"),
        # Invalid email formats
        ({"email": "not-email", "password": "Pass1234"}, 400, "Invalid email"),
        ({"email": "", "password": "Pass1234"}, 400, "email is required"),
        # Invalid password
        ({"email": "a@b.com", "password": "short"}, 400, "at least 8 characters"),
        ({"email": "a@b.com", "password": "nouppercase1"}, 400, "uppercase"),
        ({"email": "a@b.com", "password": "NoNumber!!"}, 400, "number"),
    ])
    def test_registration_validation(self, client, payload, expected_status, expected_error):
        response = client.post(f"{BASE_URL}/register", json=payload)
        assert response.status_code == expected_status
        assert expected_error.lower() in response.json()["error"].lower()
```

### Pattern 3: Authentication Flows

```python
class TestAuthentication:

    def test_login_returns_token(self, client, registered_user):
        response = client.post(f"{BASE_URL}/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"]
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"

    def test_protected_endpoint_without_token(self, client):
        response = client.get(f"{BASE_URL}/me")
        assert response.status_code == 401

    def test_protected_endpoint_with_valid_token(self, client, auth_token):
        response = client.get(f"{BASE_URL}/me", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_protected_endpoint_with_expired_token(self, client, expired_token):
        response = client.get(f"{BASE_URL}/me", headers={
            "Authorization": f"Bearer {expired_token}"
        })
        assert response.status_code == 401
```

### Pattern 4: Pagination & Filtering

```python
class TestUserListing:

    def test_default_pagination(self, client, seed_50_users):
        response = client.get(f"{BASE_URL}/users")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 20  # default page size
        assert data["total"] == 50
        assert data["page"] == 1

    def test_custom_page_size(self, client, seed_50_users):
        response = client.get(f"{BASE_URL}/users?page_size=10&page=3")
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 3

    def test_filter_by_status(self, client, seed_users_mixed_status):
        response = client.get(f"{BASE_URL}/users?status=active")
        data = response.json()
        assert all(u["status"] == "active" for u in data["items"])
```

---

## Unit Test Patterns

### Pattern 1: AAA (Arrange-Act-Assert)

```python
def test_calculate_discount_for_premium_user():
    # Arrange
    user = User(tier="premium", years_active=3)
    order = Order(total=200.00, items=5)

    # Act
    discount = calculate_discount(user, order)

    # Assert
    assert discount == 30.00  # 15% for premium with 3+ years
```

### Pattern 2: Parameterized Tests

```python
@pytest.mark.parametrize("password,is_valid,reason", [
    ("SecurePass1", True, "meets all requirements"),
    ("Secure1", False, "too short"),
    ("securepass1", False, "no uppercase"),
    ("SecurePass", False, "no number"),
    ("", False, "empty string"),
    ("A1" + "a" * 126, True, "at max length"),
    ("A1" + "a" * 127, False, "exceeds max length"),
])
def test_password_validation(password, is_valid, reason):
    result = validate_password(password)
    assert result.is_valid == is_valid, f"Failed for: {reason}"
```

### Pattern 3: Exception Testing

```python
def test_register_with_duplicate_email_raises_conflict():
    repo = InMemoryUserRepository()
    repo.save(User(email="exists@test.com", name="Existing"))
    service = RegistrationService(repo)

    with pytest.raises(DuplicateEmailError) as exc_info:
        service.register(email="exists@test.com", password="Pass1234", name="New")

    assert "already registered" in str(exc_info.value)
```

### Pattern 4: Mock External Dependencies

```python
from unittest.mock import Mock, patch

def test_registration_sends_welcome_email():
    mock_email = Mock()
    repo = InMemoryUserRepository()
    service = RegistrationService(repo, email_service=mock_email)

    service.register(email="new@test.com", password="Pass1234", name="New User")

    mock_email.send_welcome.assert_called_once_with("new@test.com", "New User")


@patch("services.registration.send_event")
def test_registration_publishes_event(mock_send):
    repo = InMemoryUserRepository()
    service = RegistrationService(repo)

    service.register(email="new@test.com", password="Pass1234", name="New User")

    mock_send.assert_called_once()
    event = mock_send.call_args[0][0]
    assert event["type"] == "user.registered"
    assert event["data"]["email"] == "new@test.com"
```

---

## Integration Test Patterns

### Pattern 1: Database Integration with Fixtures

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

@pytest.fixture
def db_session():
    # Always use an env variable for the DB URL — never hardcode production credentials.
    db_url = os.environ.get("TEST_DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    engine = create_engine(db_url)
    session = Session(engine)
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def registered_user(db_session):
    user = UserModel(email="fixture@test.com", name="Fixture User", password_hash="hashed")
    db_session.add(user)
    db_session.flush()
    return user

def test_find_user_by_email(db_session, registered_user):
    repo = UserRepository(db_session)
    found = repo.find_by_email("fixture@test.com")
    assert found is not None
    assert found.id == registered_user.id
```

### Pattern 2: API Integration with Test Server

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_register_and_login_flow(client):
    # Register
    reg_response = client.post("/api/register", json={
        "email": "flow@test.com", "password": "Pass1234", "name": "Flow Test"
    })
    assert reg_response.status_code == 201

    # Login with same credentials
    login_response = client.post("/api/login", json={
        "email": "flow@test.com", "password": "Pass1234"
    })
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()
```

### Pattern 3: Message Queue Integration

```python
def test_registration_publishes_to_queue(client, mock_queue):
    client.post("/api/register", json={
        "email": "queue@test.com", "password": "Pass1234", "name": "Queue Test"
    })

    messages = mock_queue.get_messages("user.events")
    assert len(messages) == 1
    assert messages[0]["type"] == "user.registered"
    assert messages[0]["payload"]["email"] == "queue@test.com"
```

---

## E2E Test Patterns

### Pattern 1: Page Object Model (Playwright)

```python
class RegistrationPage:
    def __init__(self, page):
        self.page = page
        self.email_input = page.locator('[data-testid="email"]')
        self.password_input = page.locator('[data-testid="password"]')
        self.name_input = page.locator('[data-testid="name"]')
        self.submit_button = page.locator('[data-testid="submit"]')
        self.error_message = page.locator('[data-testid="error"]')
        self.success_message = page.locator('[data-testid="success"]')

    def navigate(self):
        self.page.goto("http://localhost:3000/register")
        self.page.wait_for_load_state("networkidle")

    def register(self, email, password, name):
        self.email_input.fill(email)
        self.password_input.fill(password)
        self.name_input.fill(name)
        self.submit_button.click()

    def get_error(self):
        self.error_message.wait_for(state="visible")
        return self.error_message.text_content()

    def get_success(self):
        self.success_message.wait_for(state="visible")
        return self.success_message.text_content()


def test_user_registration_e2e():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        reg_page = RegistrationPage(page)

        reg_page.navigate()
        reg_page.register("e2e@test.com", "SecurePass123", "E2E User")

        assert "success" in reg_page.get_success().lower()
        browser.close()
```

### Pattern 2: Full User Journey

```python
def test_complete_registration_to_login_journey():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Step 1: Register
        page.goto("http://localhost:3000/register")
        page.wait_for_load_state("networkidle")
        page.fill('[data-testid="email"]', "journey@test.com")
        page.fill('[data-testid="password"]', "SecurePass123")
        page.fill('[data-testid="name"]', "Journey User")
        page.click('[data-testid="submit"]')
        page.wait_for_url("**/verify-email**")

        # Step 2: Verify email (simulate)
        page.goto("http://localhost:3000/verify?token=test-token")
        page.wait_for_selector("text=Email verified")

        # Step 3: Login
        page.goto("http://localhost:3000/login")
        page.wait_for_load_state("networkidle")
        page.fill('[data-testid="email"]', "journey@test.com")
        page.fill('[data-testid="password"]', "SecurePass123")
        page.click('[data-testid="login-submit"]')
        page.wait_for_url("**/dashboard**")

        assert page.locator('[data-testid="welcome"]').text_content() == "Welcome, Journey User"
        browser.close()
```

---

## Common Test Data Patterns

### Factory Pattern

```python
from dataclasses import dataclass, field
from uuid import uuid4

@dataclass
class UserFactory:
    email: str = field(default_factory=lambda: f"user-{uuid4().hex[:8]}@test.com")
    password: str = "SecurePass123"
    name: str = "Test User"

    def build(self, **overrides):
        data = {"email": self.email, "password": self.password, "name": self.name}
        data.update(overrides)
        return data

# Usage
user_data = UserFactory().build(name="Custom Name")
admin_data = UserFactory().build(email="admin@test.com", role="admin")
```

### Fixture Composition

```python
@pytest.fixture
def user_factory(client):
    created_ids = []

    def _create(**overrides):
        data = UserFactory().build(**overrides)
        response = client.post("/api/register", json=data)
        user = response.json()
        created_ids.append(user["id"])
        return user

    yield _create

    for uid in created_ids:
        client.delete(f"/api/users/{uid}")
```

### Boundary Value Sets

```python
BOUNDARY_EMAILS = [
    ("a@b.co", True),           # minimum valid
    ("a" * 64 + "@b.com", True),  # max local part
    ("a" * 65 + "@b.com", False), # over max local part
    ("test@" + "a" * 253 + ".com", True),  # near max domain
]

BOUNDARY_PASSWORDS = [
    ("A" * 7 + "1", True),     # exactly 8 chars (min)
    ("A" * 6 + "1", False),    # 7 chars (below min)
    ("A" * 127 + "1", True),   # 128 chars (at max)
    ("A" * 128 + "1", False),  # 129 chars (above max)
]
```
