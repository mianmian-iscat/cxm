#!/usr/bin/env python3
"""
Generate a standardized test project structure with config and fixture boilerplate.

Usage:
    # Create Python test scaffold (default)
    python scripts/scaffold_tests.py --lang python --target ./my-project

    # Create JavaScript/TypeScript test scaffold
    python scripts/scaffold_tests.py --lang javascript --target ./my-project

    # Python scaffold with specific test layers
    python scripts/scaffold_tests.py --lang python --target ./my-project --layers unit integration e2e

    # Show what would be created without writing files
    python scripts/scaffold_tests.py --lang python --target ./my-project --dry-run
"""

import argparse
import os
import sys

PYTHON_CONFTEST_ROOT = '''import pytest
import os

@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("TEST_BASE_URL", "http://localhost:8000")
'''

PYTHON_CONFTEST_UNIT = '''import pytest
'''

PYTHON_CONFTEST_INTEGRATION = '''import pytest
import httpx
import os

@pytest.fixture
def client(base_url):
    with httpx.Client(base_url=base_url, timeout=10.0) as c:
        yield c

@pytest.fixture
def auth_client(client):
    """Client with authentication token. Customize login credentials as needed."""
    response = client.post("/api/login", json={
        "email": os.environ.get("TEST_ADMIN_EMAIL", "admin@test.com"),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "AdminPass123"),
    })
    token = response.json().get("access_token", "")
    with httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    ) as ac:
        yield ac
'''

PYTHON_CONFTEST_E2E = '''import pytest

@pytest.fixture(scope="session")
def browser_context_args():
    # ignore_https_errors: ONLY for local/staging with self-signed certs.
    return {
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }
'''

PYTHON_PYPROJECT = '''[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
markers = [
    "unit: Unit tests (fast, no external deps)",
    "integration: Integration tests (require services)",
    "e2e: End-to-end tests (require full stack)",
    "smoke: Smoke tests (critical paths only)",
    "regression: Regression tests from production incidents",
]
addopts = "-v --tb=short --strict-markers"

[tool.coverage.run]
source = ["src"]
omit = ["tests/*", "*/migrations/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
'''

PYTHON_SAMPLE_UNIT = '''import pytest


class TestExample:
    """Replace with your actual unit tests."""

    def test_placeholder(self):
        assert True, "Replace this with real tests"
'''

PYTHON_SAMPLE_INTEGRATION = '''import pytest


class TestAPIExample:
    """Replace with your actual API integration tests."""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
'''

PYTHON_SAMPLE_E2E = '''from playwright.sync_api import sync_playwright


def test_homepage_loads():
    """Replace with your actual E2E tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:3000")
        page.wait_for_load_state("networkidle")
        assert page.title() != ""
        browser.close()
'''

PYTHON_SAMPLE_REGRESSION = '''import pytest


class TestRegression:
    """Regression tests from production incidents.
    Each test references the incident that caused its creation.
    """

    # def test_incident_example(self, client):
    #     """Incident INC-YYYY-XXX: Description of what failed."""
    #     pass
'''

JS_VITEST_CONFIG = '''import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.{js,ts}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      thresholds: { lines: 80 },
    },
  },
});
'''

JS_SAMPLE_UNIT = '''import { describe, it, expect } from "vitest";

describe("Example", () => {
  it("placeholder test — replace with real tests", () => {
    expect(true).toBe(true);
  });
});
'''

LAYER_CONFIGS = {
    "python": {
        "unit": {
            "conftest": PYTHON_CONFTEST_UNIT,
            "sample": ("test_example.py", PYTHON_SAMPLE_UNIT),
        },
        "integration": {
            "conftest": PYTHON_CONFTEST_INTEGRATION,
            "sample": ("test_api_example.py", PYTHON_SAMPLE_INTEGRATION),
        },
        "e2e": {
            "conftest": PYTHON_CONFTEST_E2E,
            "sample": ("test_e2e_example.py", PYTHON_SAMPLE_E2E),
        },
        "regression": {
            "conftest": None,
            "sample": ("test_regression.py", PYTHON_SAMPLE_REGRESSION),
        },
    },
    "javascript": {
        "unit": {
            "conftest": None,
            "sample": ("example.test.js", JS_SAMPLE_UNIT),
        },
        "integration": {
            "conftest": None,
            "sample": ("api.test.js", JS_SAMPLE_UNIT),
        },
        "e2e": {
            "conftest": None,
            "sample": ("e2e.test.js", JS_SAMPLE_UNIT),
        },
    },
}


def create_file(path, content, dry_run=False):
    if os.path.exists(path):
        print(f"  SKIP  {path} (already exists)")
        return
    if dry_run:
        print(f"  WOULD CREATE  {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"  CREATE  {path}")


def scaffold_python(target, layers, dry_run):
    print(f"\nScaffolding Python test project in: {target}/tests/")
    print(f"Layers: {', '.join(layers)}\n")

    create_file(os.path.join(target, "tests", "__init__.py"), "", dry_run)
    create_file(os.path.join(target, "tests", "conftest.py"), PYTHON_CONFTEST_ROOT, dry_run)

    for layer in layers:
        cfg = LAYER_CONFIGS["python"].get(layer)
        if not cfg:
            print(f"  WARN  Unknown layer '{layer}', skipping")
            continue
        layer_dir = os.path.join(target, "tests", layer)
        create_file(os.path.join(layer_dir, "__init__.py"), "", dry_run)
        if cfg["conftest"]:
            create_file(os.path.join(layer_dir, "conftest.py"), cfg["conftest"], dry_run)
        sample_name, sample_content = cfg["sample"]
        create_file(os.path.join(layer_dir, sample_name), sample_content, dry_run)

    create_file(os.path.join(target, "tests", "fixtures", ".gitkeep"), "", dry_run)

    pyproject_path = os.path.join(target, "pyproject.toml")
    if os.path.exists(pyproject_path):
        print(f"\n  SKIP  {pyproject_path} (already exists — add [tool.pytest] config manually)")
    else:
        create_file(pyproject_path, PYTHON_PYPROJECT, dry_run)

    print(f"\nDone. Install test dependencies:")
    print(f"  pip install pytest httpx pytest-cov")
    if "e2e" in layers:
        print(f"  pip install playwright pytest-playwright && playwright install chromium")


def scaffold_javascript(target, layers, dry_run):
    print(f"\nScaffolding JavaScript test project in: {target}/tests/")
    print(f"Layers: {', '.join(layers)}\n")

    for layer in layers:
        cfg = LAYER_CONFIGS["javascript"].get(layer)
        if not cfg:
            print(f"  WARN  Unknown layer '{layer}', skipping")
            continue
        layer_dir = os.path.join(target, "tests", layer)
        sample_name, sample_content = cfg["sample"]
        create_file(os.path.join(layer_dir, sample_name), sample_content, dry_run)

    create_file(os.path.join(target, "vitest.config.js"), JS_VITEST_CONFIG, dry_run)

    print(f"\nDone. Install test dependencies:")
    print(f"  npm install -D vitest @vitest/coverage-v8")
    if "e2e" in layers:
        print(f"  npm install -D @playwright/test && npx playwright install")


def main():
    parser = argparse.ArgumentParser(
        description="Generate standardized test project structure with config and boilerplate."
    )
    parser.add_argument(
        "--lang",
        choices=["python", "javascript"],
        default="python",
        help="Project language (default: python)",
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "--layers",
        nargs="+",
        default=["unit", "integration", "e2e", "regression"],
        help="Test layers to scaffold (default: unit integration e2e regression)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing files",
    )

    args = parser.parse_args()
    target = os.path.abspath(args.target)

    if not os.path.isdir(target):
        print(f"Error: Target directory does not exist: {target}")
        sys.exit(1)

    if args.lang == "python":
        scaffold_python(target, args.layers, args.dry_run)
    elif args.lang == "javascript":
        scaffold_javascript(target, args.layers, args.dry_run)


if __name__ == "__main__":
    main()
