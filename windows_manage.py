"""Windows offline installation, backup, activation, and rollback helpers."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
KEEP_BACKUPS = 30


def _root(path: str) -> Path:
    root = Path(path).expanduser().resolve()
    if root.name.lower() != "subsentry":
        raise ValueError("Install root folder must be named SubSentry.")
    return root


def _version(value: str) -> str:
    version = value.strip()
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"Invalid version: {value!r}")
    return version


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, value) -> None:
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _current_version(root: Path) -> str:
    try:
        return root.joinpath("current_version.txt").read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        return ""


def _ensure_layout(root: Path) -> None:
    for name in ("versions", "data/uploads", "reference", "backups", "logs"):
        root.joinpath(name).mkdir(parents=True, exist_ok=True)


def initialize(
    root_path: str,
    version_value: str,
    bootstrap_source: str,
    bootstrap_reference: str,
) -> None:
    root = _root(root_path)
    version = _version(version_value)
    version_dir = root / "versions" / version
    if not version_dir.is_dir():
        raise FileNotFoundError(f"Version directory not found: {version_dir}")

    _ensure_layout(root)

    source = Path(bootstrap_source).resolve()
    target_source = root / "data" / "uploads" / "current_circuit_table.xlsx"
    target_meta = root / "data" / "uploads" / "current_meta.json"
    if not target_source.exists():
        if not source.is_file():
            raise FileNotFoundError(f"Bootstrap circuit table not found: {source}")
        shutil.copy2(source, target_source)
        _write_json(
            target_meta,
            {
                "original_name": source.name,
                "uploaded_at": datetime.now().isoformat(timespec="seconds"),
                "size_bytes": target_source.stat().st_size,
                "source": "windows-offline-bootstrap",
            },
        )

    reference_source = Path(bootstrap_reference).resolve()
    reference_target = root / "reference"
    if not any(reference_target.iterdir()):
        if not reference_source.is_dir():
            raise FileNotFoundError(
                f"Bootstrap reference folder not found: {reference_source}"
            )
        shutil.copytree(reference_source, reference_target, dirs_exist_ok=True)

    print(f"initialized={version}")


def backup(root_path: str, reason: str) -> Path:
    root = _root(root_path)
    _ensure_layout(root)
    safe_reason = re.sub(r"[^A-Za-z0-9_-]+", "-", reason.strip()) or "manual"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = root / "backups" / f"system-{timestamp}-{safe_reason}"
    target.mkdir(parents=True)

    for name in ("data", "reference"):
        source = root / name
        if source.exists():
            shutil.copytree(source, target / name)

    for name in ("current_version.txt", "version_state.json"):
        source = root / name
        if source.exists():
            shutil.copy2(source, target / name)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "current_version": _current_version(root),
    }
    _write_json(target / "backup_manifest.json", manifest)

    backups = sorted(
        (
            path
            for path in (root / "backups").iterdir()
            if path.is_dir() and path.name.startswith("system-")
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[KEEP_BACKUPS:]:
        shutil.rmtree(old_backup, ignore_errors=True)

    print(target)
    return target


def activate(root_path: str, version_value: str) -> None:
    root = _root(root_path)
    version = _version(version_value)
    version_dir = root / "versions" / version
    if not version_dir.is_dir():
        raise FileNotFoundError(f"Version directory not found: {version_dir}")

    state_path = root / "version_state.json"
    state = _read_json(state_path, {"current": "", "rollback_stack": [], "events": []})
    current = _current_version(root) or state.get("current", "")
    stack = [item for item in state.get("rollback_stack", []) if item != version]
    if current and current != version:
        stack.append(current)

    state["current"] = version
    state["rollback_stack"] = stack[-20:]
    state.setdefault("events", []).append(
        {
            "action": "activate",
            "version": version,
            "previous": current or None,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
    )
    state["events"] = state["events"][-100:]
    _atomic_write_text(root / "current_version.txt", version + "\n")
    _write_json(state_path, state)
    print(version)


def rollback(root_path: str) -> str:
    root = _root(root_path)
    state_path = root / "version_state.json"
    state = _read_json(state_path, {"current": "", "rollback_stack": [], "events": []})
    stack = list(state.get("rollback_stack", []))
    if not stack:
        raise RuntimeError("No previous version is available for rollback.")

    previous = _version(stack.pop())
    previous_dir = root / "versions" / previous
    if not previous_dir.is_dir():
        raise FileNotFoundError(f"Previous version directory not found: {previous_dir}")

    current = _current_version(root) or state.get("current", "")
    state["current"] = previous
    state["rollback_stack"] = stack
    state.setdefault("events", []).append(
        {
            "action": "rollback",
            "version": previous,
            "previous": current or None,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
    )
    state["events"] = state["events"][-100:]
    _atomic_write_text(root / "current_version.txt", previous + "\n")
    _write_json(state_path, state)
    print(previous)
    return previous


def status(root_path: str) -> None:
    root = _root(root_path)
    current = _current_version(root)
    data_source = root / "data" / "uploads" / "current_circuit_table.xlsx"
    reference_files = list((root / "reference").glob("*.xlsx"))
    print(f"root={root}")
    print(f"current_version={current or 'not-installed'}")
    print(f"data_source={'present' if data_source.is_file() else 'missing'}")
    print(f"reference_files={len(reference_files)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("initialize")
    init_parser.add_argument("--root", required=True)
    init_parser.add_argument("--version", required=True)
    init_parser.add_argument("--bootstrap-source", required=True)
    init_parser.add_argument("--bootstrap-reference", required=True)

    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--root", required=True)
    backup_parser.add_argument("--reason", default="manual")

    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("--root", required=True)
    activate_parser.add_argument("--version", required=True)

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--root", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--root", required=True)

    args = parser.parse_args()
    if args.command == "initialize":
        initialize(
            args.root, args.version, args.bootstrap_source, args.bootstrap_reference
        )
    elif args.command == "backup":
        backup(args.root, args.reason)
    elif args.command == "activate":
        activate(args.root, args.version)
    elif args.command == "rollback":
        rollback(args.root)
    elif args.command == "status":
        status(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
