#!/usr/bin/env python3
"""CI smoke test -- imports every module under app/ plus the agent entrypoint.

Catches startup-time crashes (missing dependencies, syntax errors, broken
module-level code) before they reach production. Every module in app/ must
be importable with no network access and no secrets configured -- optional
integrations (CareLink, FHIR, MCP, Apple Health, weather) are expected to
guard their heavy imports lazily inside functions.

Usage: python scripts/ci_smoke.py
"""

import importlib
import os
import pkgutil
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as _app_pkg


def _iter_module_names(package):
    prefix = package.__name__ + "."
    for _, name, _ in pkgutil.walk_packages(package.__path__, prefix):
        yield name


def main() -> bool:
    modules = ["app", "agent"] + sorted(_iter_module_names(_app_pkg))
    failures = []

    for name in modules:
        try:
            importlib.import_module(name)
            print(f"  OK   {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL {name}: {type(e).__name__}: {e}")

    print(f"\n=== Smoke test: {len(modules) - len(failures)}/{len(modules)} modules imported ===")

    if failures:
        print("\nFailed imports:")
        for name, e in failures:
            print(f"  - {name}: {type(e).__name__}: {e}")
        return False
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
