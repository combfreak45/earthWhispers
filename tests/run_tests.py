"""
Test runner script to execute all unit tests.
"""

import sys
import os
import traceback

test_files = [
    "test_baseline.py",
    "test_freshness.py",
    "test_policy.py",
    "test_geometry.py"
]

tests_dir = os.path.dirname(__file__)
total_passed = 0
total_failed = 0

for tf in test_files:
    path = os.path.join(tests_dir, tf)
    print(f"\n=== Running {tf} ===")
    namespace = {"__file__": path}
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, path, "exec"), namespace)

    for name, func in namespace.items():
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  [PASS] {name}")
                total_passed += 1
            except Exception as e:
                print(f"  [FAIL] {name}: {e}")
                traceback.print_exc()
                total_failed += 1

print(f"\n==========================================")
print(f"Total: {total_passed + total_failed} | Passed: {total_passed} | Failed: {total_failed}")
print(f"==========================================")

if total_failed > 0:
    sys.exit(1)
