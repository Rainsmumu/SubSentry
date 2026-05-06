# -*- coding: utf-8 -*-
"""Windows offline deployment checks for SubSentry."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import os
import sys


MIN_VERSION = (3, 8)
DATA_FILE = "金桥机房电路表.xlsx"


def check_python() -> int:
    print("=== Python ===")
    print(sys.version.split()[0])
    if sys.version_info < MIN_VERSION:
        print("[ERROR] Python 3.8 or newer is required.")
        return 1
    return 0


def check_data_file() -> int:
    print("\n=== Data file ===")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DATA_FILE)
    if os.path.exists(path):
        print("Found:", DATA_FILE)
        return 0
    print("[ERROR] Missing data file:", DATA_FILE)
    print("Please put it in the same folder as app.py before starting SubSentry.")
    return 1


def check_modules() -> int:
    print("\n=== Required modules ===")
    failed = False
    for name in ("flask", "openpyxl"):
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
