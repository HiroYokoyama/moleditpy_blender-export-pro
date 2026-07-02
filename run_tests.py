#!/usr/bin/env python3
"""Test runner for the Blender Export Pro plugin.

Thin wrapper around pytest so the suite can be run the same way locally and
in CI, from any working directory. The suite is fully headless: PyQt6 /
pyvista / numpy / rdkit are mocked or duck-typed (see tests/conftest.py),
so only pytest itself is required (pytest-cov for --coverage).

Usage:
    python run_tests.py                 # full suite, quiet
    python run_tests.py -v              # verbose (one line per test)
    python run_tests.py -k ring         # only tests matching a keyword
    python run_tests.py --coverage      # with coverage report
    python run_tests.py tests/test_dialog.py   # a single file
"""

import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Blender Export Pro test suite (headless).")
    parser.add_argument("targets", nargs="*", default=["tests/"],
                        help="test files/directories (default: tests/)")
    parser.add_argument("-k", metavar="EXPR",
                        help="only run tests matching the expression")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="one line per test instead of dots")
    parser.add_argument("--coverage", action="store_true",
                        help="measure coverage (requires pytest-cov)")
    parser.add_argument("-x", "--exitfirst", action="store_true",
                        help="stop on the first failure")
    args = parser.parse_args()

    cmd = [sys.executable, "-m", "pytest"]
    cmd += args.targets if args.targets else ["tests/"]
    cmd.append("-v" if args.verbose else "-q")
    if args.k:
        cmd += ["-k", args.k]
    if args.exitfirst:
        cmd.append("-x")
    if args.coverage:
        cmd += ["--cov=blender_export_pro", "--cov-report=term-missing"]

    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
