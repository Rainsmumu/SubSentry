# -*- coding: utf-8 -*-
"""Windows offline deployment checks for SubSentry."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import os
import sys


MIN_VERSION = (3, 9)
WINDOWS_VERSION = (3, 12)


def check_python() -> int:
    print("=== Python ===")
    print(sys.version.split()[0])
    required = (
        WINDOWS_VERSION
        if os.environ.get("SUBSENTRY_WINDOWS") == "1"
        else MIN_VERSION
    )
    if sys.version_info < required:
        print(f"[ERROR] Python {required[0]}.{required[1]} or newer is required.")
        return 1
    return 0


def check_data_file() -> int:
    print("\n=== Data file ===")
    from data_source import get_current_path

    path = get_current_path()
    if os.path.exists(path):
        print("Found:", path)
        return 0
    print("[ERROR] Missing data file:", path)
    print("Upload or install the circuit table before starting SubSentry.")
    return 1


def check_modules() -> int:
    print("\n=== Required modules ===")
    failed = False
    for name in ("flask", "openpyxl", "waitress"):
        try:
            importlib.import_module(name)
            version = importlib.metadata.version(name)
            print(f"{name} {version}")
        except Exception as exc:
            failed = True
            print(f"[ERROR] {name} is not available: {exc}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("start", "env"),
        default="env",
        help="start checks Python and data file; env also checks dependencies.",
    )
    args = parser.parse_args()

    rc = check_python()
    if args.mode == "env":
        rc = check_modules() or rc
    rc = check_data_file() or rc

    if rc == 0:
        print("\nEnvironment check passed.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
