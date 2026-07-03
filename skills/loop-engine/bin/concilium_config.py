#!/usr/bin/env python3
"""Load Concilium layered configuration."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REDACTED = "[REDACTED]"
RISK_POSTURES = {"speed-first", "balanced", "review-first"}
SENSITIVE_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|cookie|credential)", re.I)
SECRET_VALUE_RE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]+|[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b")
USER_ONLY_MEMORY_KEYS = {
    "private_context_dirs",
    "private_context_max_file_bytes",
    "private_context_max_total_bytes",
    "private_archive_dir",
}


def default_config_path() -> Path:
    return ROOT / "config" / "concilium.defaults.json"


def user_config_path() -> Path:
    return Path.home() / ".config" / "concilium" / "config.json"


def project_config_path(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / ".concilium.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config must be a JSON object: {path}")
    return data


def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def strip_project_only_memory(project_config: dict) -> dict:
    sanitized = copy.deepcopy(project_config)
    memory = sanitized.get("memory")
    if isinstance(memory, dict):
        for key in USER_ONLY_MEMORY_KEYS:
            memory.pop(key, None)
    return sanitized


def validate_config(config: dict) -> None:
    lanes = config.get("lanes", {})
    review = lanes.get("review", {})
    executor = review.get("default_review_executor")
    reviewer = review.get("default_review_reviewer")
    if executor and reviewer and executor == reviewer:
        raise ValueError("review executor and reviewer must differ")

    risk_posture = config.get("routing", {}).get("risk_posture")
    if risk_posture not in RISK_POSTURES:
        raise ValueError(f"routing.risk_posture must be one of {sorted(RISK_POSTURES)}")

    capacity = config.get("capacity", {})
    warn = capacity.get("warn_below_percent")
    block = capacity.get("block_below_percent")
    if not isinstance(warn, (int, float)) or not isinstance(block, (int, float)):
        raise ValueError("capacity thresholds must be numbers")
    if block > warn:
        raise ValueError("capacity.block_below_percent must be less than or equal to warn_below_percent")

    timeouts = config.get("timeouts", {})
    seat_modes = timeouts.get("seat_mode_seconds", {}) if isinstance(timeouts, dict) else {}
    if not isinstance(seat_modes, dict):
        raise ValueError("timeouts.seat_mode_seconds must be an object")
    for seat, modes in seat_modes.items():
        if not isinstance(modes, dict):
            raise ValueError(f"timeouts.seat_mode_seconds.{seat} must be an object")
        for mode, seconds in modes.items():
            if not isinstance(seconds, (int, float)) or seconds <= 0:
                raise ValueError(f"timeout override for {seat}.{mode} must be positive")

    memory = config.get("memory", {})
    if not isinstance(memory, dict):
        raise ValueError("memory must be an object")
    dirs = memory.get("private_context_dirs", [])
    if not isinstance(dirs, list) or not all(isinstance(item, str) for item in dirs):
        raise ValueError("memory.private_context_dirs must be a list of strings")
    max_file = memory.get("private_context_max_file_bytes", 20000)
    max_total = memory.get("private_context_max_total_bytes", 200000)
    private_archive_dir = memory.get("private_archive_dir", "")
    if not isinstance(max_file, int) or max_file <= 0:
        raise ValueError("memory.private_context_max_file_bytes must be a positive integer")
    if not isinstance(max_total, int) or max_total <= 0:
        raise ValueError("memory.private_context_max_total_bytes must be a positive integer")
    if not isinstance(private_archive_dir, str):
        raise ValueError("memory.private_archive_dir must be a string")


def _redact_value(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if SENSITIVE_KEY_RE.search(str(key)) and isinstance(item, str):
                redacted[key] = REDACTED
            else:
                redacted[key] = _redact_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub(REDACTED, value)
    return value


def redact_for_render(config: dict) -> dict:
    return _redact_value(config)


def load_config(
    repo: str | Path,
    user_config: str | Path | None = None,
    default_config: str | Path | None = None,
) -> dict:
    defaults_path = Path(default_config).expanduser().resolve() if default_config else default_config_path()
    user_path = Path(user_config).expanduser().resolve() if user_config else user_config_path()
    project_path = project_config_path(repo)

    config = load_json(defaults_path)
    user_config_data = load_json(user_path)
    project_config_data = strip_project_only_memory(load_json(project_path))
    config = deep_merge(config, user_config_data)
    config = deep_merge(config, project_config_data)
    validate_config(config)
    return config


def render_effective_config(
    repo: str | Path,
    user_config: str | Path | None = None,
    default_config: str | Path | None = None,
) -> str:
    config = load_config(repo, user_config=user_config, default_config=default_config)
    redacted = redact_for_render(config)
    return json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def init_project_config(repo: str | Path, force: bool = False) -> Path:
    repo_path = Path(repo).expanduser().resolve()
    if not repo_path.is_dir():
        raise NotADirectoryError(f"repo directory does not exist: {repo_path}")
    path = repo_path / ".concilium.json"
    if path.exists() and not force:
        raise FileExistsError(f"project config already exists: {path}")
    data = {
        "version": 1,
        "lanes": {
            "fast": {
                "default_single_agent": "kimi",
            },
            "review": {
                "default_review_executor": "kimi",
                "default_review_reviewer": "hermes",
            },
        },
        "routing": {
            "risk_posture": "balanced",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Concilium layered configuration.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--user-config", default="")
    parser.add_argument("--default-config", default="")
    parser.add_argument("--print-effective", action="store_true")
    parser.add_argument("--init-project", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    actions = int(args.print_effective) + int(args.init_project)
    if actions != 1:
        parser.error("choose exactly one of --print-effective or --init-project")

    user_config_arg = args.user_config or None
    default_config_arg = args.default_config or None
    try:
        if args.init_project:
            print(init_project_config(args.repo, force=args.force))
            return 0
        print(render_effective_config(args.repo, user_config=user_config_arg, default_config=default_config_arg), end="")
        return 0
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
