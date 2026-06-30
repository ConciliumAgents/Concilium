#!/usr/bin/env python3
"""Concilium run artifact gates and redacted run bundles."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import capacity_status

def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return capacity_status.redact(value)
    return value


def _as_relative(path: str) -> str:
    return str(Path(path)).replace("\\", "/").lstrip("/")


def _normalize_artifact_path(path: str) -> tuple[str, str | None]:
    raw = str(path).replace("\\", "/")
    pure = PurePosixPath(raw)
    parts = pure.parts
    if pure.is_absolute() or not parts or any(part in {"", ".", ".."} for part in parts):
        return raw, raw
    return pure.as_posix(), None


def _normalize_artifact_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    normalized: list[str] = []
    invalid: list[str] = []
    for path in paths:
        value, invalid_value = _normalize_artifact_path(path)
        if invalid_value is not None:
            invalid.append(invalid_value)
        else:
            normalized.append(value)
    return normalized, sorted(set(invalid))


def _match_parts(path_parts: tuple[str, ...], pattern_parts: tuple[str, ...]) -> bool:
    if not pattern_parts:
        return not path_parts
    head, tail = pattern_parts[0], pattern_parts[1:]
    if head == "**":
        return any(_match_parts(path_parts[index:], tail) for index in range(len(path_parts) + 1))
    if not path_parts:
        return False
    return fnmatchcase(path_parts[0], head) and _match_parts(path_parts[1:], tail)


def _matches_any(path: str, patterns: list[str], *, allow_when_empty: bool = True) -> bool:
    if not patterns:
        return allow_when_empty
    path_parts = PurePosixPath(path).parts
    return any(
        _match_parts(path_parts, PurePosixPath(pattern).parts)
        for pattern in patterns
    )


def _hash_delta_path(repo_path: Path, rel_path: str) -> str:
    target = (repo_path / rel_path).resolve()
    try:
        target.relative_to(repo_path)
    except ValueError:
        return "<outside>"
    if not target.exists():
        return "<missing>"
    if target.is_dir():
        return "<dir>"
    return hashlib.sha256(target.read_bytes()).hexdigest()


def hash_delta_snapshot(repo: str | Path, include_paths: list[str] | None = None) -> dict[str, str]:
    repo_path = Path(repo).expanduser().resolve()
    delta_paths = set(collect_delta(repo_path).get("delta_paths", []))
    extra_paths, invalid_extra = _normalize_artifact_paths([str(path) for path in (include_paths or [])])
    delta_paths.update(extra_paths)
    delta_paths.update(invalid_extra)
    return {path: _hash_delta_path(repo_path, path) for path in sorted(delta_paths)}


def changed_snapshot_paths(before: dict[str, str], after: dict[str, str], *, allowed_paths: list[str]) -> list[str]:
    allowed = set(allowed_paths)
    paths = set(before) | set(after)
    return sorted(path for path in paths if path not in allowed and before.get(path) != after.get(path))


def _git_delta_paths(repo: Path) -> tuple[str, list[str]]:
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all", "-z"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return "unavailable", []

    fields = result.stdout.decode("utf-8", "surrogateescape").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        record = fields[index]
        if not record:
            index += 1
            continue
        status = record[:2]
        path = record[3:]
        if path:
            paths.append(_as_relative(path))
        if any(code in status for code in ("R", "C")) and index + 1 < len(fields):
            old_path = fields[index + 1]
            if old_path:
                paths.append(_as_relative(old_path))
            index += 2
        else:
            index += 1
    return "available", sorted(set(paths))


def collect_delta(repo: str | Path) -> dict:
    repo_path = Path(repo).expanduser().resolve()
    delta_status, delta_paths = _git_delta_paths(repo_path)
    return {"delta_status": delta_status, "delta_paths": delta_paths}


def evaluate_artifact_gate(
    repo: str | Path,
    *,
    required_artifact_paths: list[str] | None = None,
    allowed_write_paths: list[str] | None = None,
    baseline_delta_paths: list[str] | None = None,
    allow_unlisted_required: bool = True,
    allow_unlisted_delta: bool = True,
) -> dict:
    repo_path = Path(repo).expanduser().resolve()
    required, invalid_required = _normalize_artifact_paths([str(path) for path in (required_artifact_paths or [])])
    allowed, invalid_allowed = _normalize_artifact_paths([str(path) for path in (allowed_write_paths or [])])
    baseline, invalid_baseline = _normalize_artifact_paths([str(path) for path in (baseline_delta_paths or [])])
    invalid = sorted(set(invalid_required + invalid_allowed + invalid_baseline))
    baseline_set = set(baseline)

    missing = [path for path in required if not (repo_path / path).exists()]
    empty = [
        path
        for path in required
        if (repo_path / path).is_file() and (repo_path / path).stat().st_size == 0
    ]
    disallowed = [
        path
        for path in required
        if not _matches_any(path, allowed, allow_when_empty=allow_unlisted_required)
    ]
    delta_status, delta_paths = _git_delta_paths(repo_path)
    new_delta_paths = [path for path in delta_paths if path not in baseline_set]
    unchanged_required = [
        path
        for path in required
        if delta_status == "available" and path not in missing and path not in new_delta_paths
    ]
    disallowed_delta = [
        path
        for path in new_delta_paths
        if not _matches_any(path, allowed, allow_when_empty=allow_unlisted_delta)
    ]
    status = (
        "passed"
        if not invalid and not missing and not empty and not unchanged_required and not disallowed and not disallowed_delta
        else "failed"
    )
    return {
        "status": status,
        "required": required,
        "allowed": allowed,
        "invalid": invalid,
        "missing": missing,
        "empty": empty,
        "unchanged_required": unchanged_required,
        "disallowed": disallowed,
        "delta_status": delta_status,
        "delta_paths": delta_paths,
        "baseline_delta_paths": sorted(baseline_set),
        "new_delta_paths": new_delta_paths,
        "disallowed_delta": disallowed_delta,
    }


def write_run_bundle(root: str | Path, run_id: str, payload: dict) -> Path:
    bundle = Path(root).expanduser().resolve() / str(run_id)
    bundle.mkdir(parents=True, exist_ok=True)
    manifest = bundle / "manifest.json"
    manifest.write_text(
        json.dumps(redact(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle
