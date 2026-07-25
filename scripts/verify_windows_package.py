#!/usr/bin/env python3
"""Verify SubSentry Windows full and update package contents."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


APP_FILES = {
    "app.py",
    "cable_config.py",
    "circuit_analyzer.py",
    "comparison.py",
    "data_source.py",
    "deploy_check.py",
    "excel_builder.py",
    "report_builder.py",
    "requirements.txt",
    "templates/index.html",
    "static/vendor/alpine.min.js",
    "static/vendor/tailwindcss.js",
    "tests/test_cable_config.py",
    "tests/test_comparison.py",
    "tests/test_excel_builder.py",
    "tests/test_windows_manage.py",
}

ROOT_FILES = {
    "PACKAGE_VERSION.txt",
    "WINDOWS_OFFLINE_DEPLOY.md",
    "backup.bat",
    "check_env.bat",
    "install_offline_deps.bat",
    "install_python_312.bat",
    "resolve_python.bat",
    "rollback.bat",
    "set_env.bat",
    "start.bat",
    "stop_subsentry.bat",
    "windows_manage.py",
}


def _members(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt member in {path.name}: {bad}")
        return {name.rstrip("/") for name in archive.namelist()}


def _require(members: set[str], required: set[str], label: str) -> None:
    missing = sorted(required - members)
    if missing:
        raise ValueError(f"{label} is missing: {', '.join(missing)}")


def verify_full(path: Path, version: str) -> None:
    members = _members(path)
    root = "SubSentry"
    app_root = f"{root}/versions/{version}"
    required = {f"{root}/{name}" for name in ROOT_FILES}
    required.update(f"{app_root}/{name}" for name in APP_FILES)
    required.update(
        {
            f"{root}/python-installer/python-3.12.10-amd64.exe",
            f"{root}/bootstrap/上海ITMC电路槽路表0407改进版.xlsx",
            f"{root}/bootstrap/reference/路由中断分析结果APCN2 S3.xlsx",
            f"{root}/bootstrap/reference/路由中断分析结果APCN2 S4A.xlsx",
            f"{root}/bootstrap/reference/路由中断分析结果APG S3.xlsx",
            f"{root}/bootstrap/reference/路由中断分析结果APG S4.xlsx",
            f"{root}/bootstrap/reference/路由中断分析结果NCP S1.1.xlsx",
            f"{root}/bootstrap/reference/路由中断分析结果NCP S3.xlsx",
            f"{root}/bootstrap/reference/路由中断分析结果TPE S1S.xlsx",
            f"{root}/bootstrap/reference/路由中断分析结果TPE S4.xlsx",
            f"{root}/SHA256SUMS.txt",
        }
    )
    _require(members, required, "Full package")
    if not any(name.startswith(f"{root}/wheels/") and name.endswith(".whl") for name in members):
        raise ValueError("Full package has no wheels")
    forbidden = (
        "/data/fault_state.json",
        "/data/uploads/current_circuit_table.xlsx",
        "/.git/",
        "/__pycache__/",
        ".pyc",
    )
    if any(marker in f"/{name}" for name in members for marker in forbidden):
        raise ValueError("Full package contains runtime state or Git metadata")


def verify_update(path: Path, version: str) -> None:
    members = _members(path)
    root = f"SubSentry_Update_{version}"
    required = {
        f"{root}/install_update.bat",
        f"{root}/windows_manage.py",
        f"{root}/PACKAGE_VERSION.txt",
        f"{root}/SHA256SUMS.txt",
    }
    required.update(f"{root}/app/{name}" for name in APP_FILES)
    required.update(f"{root}/root_files/{name}" for name in ROOT_FILES - {"PACKAGE_VERSION.txt"})
    _require(members, required, "Update package")
    if not any(name.startswith(f"{root}/wheels/") and name.endswith(".whl") for name in members):
        raise ValueError("Update package has no wheels")

    forbidden_fragments = (
        "/bootstrap/",
        "/reference/",
        "/data/",
        ".xlsx",
        "python-3.12.10-amd64.exe",
        "/.git/",
        "/__pycache__/",
        ".pyc",
    )
    forbidden = [
        name for name in members if any(fragment in name for fragment in forbidden_fragments)
    ]
    if forbidden:
        raise ValueError(f"Update package contains protected data: {forbidden[0]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", required=True, type=Path)
    parser.add_argument("--update", required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    verify_full(args.full, args.version)
    verify_update(args.update, args.version)
    print(f"Verified full package: {args.full}")
    print(f"Verified update package: {args.update}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
