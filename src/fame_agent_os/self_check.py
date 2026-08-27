from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .state import SCHEMA_VERSION, fame_dir


TASK_ID = re.compile(r"FAME-\d{4,}$")


@dataclass
class SelfCheck:
    success: bool
    errors: list[dict[str, str]]


def _error(errors: list[dict[str, str]], code: str, path: Path, message: str) -> None:
    errors.append({"code": code, "path": str(path), "message": message})


def _load_object(path: Path, errors: list[dict[str, str]]) -> dict | None:
    try:
        value = json.loads(path.read_text())
    except OSError as exc:
        _error(errors, "unreadable_json", path, str(exc))
        return None
    except json.JSONDecodeError as exc:
        _error(errors, "invalid_json", path, f"{exc.msg} (line {exc.lineno}, column {exc.colno})")
        return None
    if not isinstance(value, dict):
        _error(errors, "invalid_json_shape", path, "expected a JSON object")
        return None
    return value


def check(root: Path) -> SelfCheck:
    """Validate on-disk Fame state only; this function never invokes Codex."""
    errors: list[dict[str, str]] = []
    directory = fame_dir(root)
    if not directory.is_dir():
        _error(errors, "not_initialized", directory, "run `fame init` first")
        return SelfCheck(False, errors)

    schema = directory / "schema-version"
    try:
        found_schema = schema.read_text().strip()
    except OSError:
        _error(errors, "missing_schema_version", schema, "expected schema-version file")
    else:
        if found_schema != SCHEMA_VERSION:
            _error(errors, "schema_version_mismatch", schema, f"expected {SCHEMA_VERSION!r}, found {found_schema!r}")

    for name in ("PROJECT.md", "DECISIONS.md"):
        path = directory / "state" / name
        if not path.is_file():
            _error(errors, "missing_state_file", path, "expected state file")

    config = directory / "config.json"
    if not config.is_file():
        _error(errors, "missing_config", config, "expected project configuration")
    else:
        _load_object(config, errors)

    current_path = directory / "state" / "CURRENT.json"
    current = _load_object(current_path, errors) if current_path.is_file() else None
    if current is None and not current_path.is_file():
        _error(errors, "missing_current_state", current_path, "expected current task state")

    tasks_path = directory / "tasks"
    tasks: dict[str, dict] = {}
    if not tasks_path.is_dir():
        _error(errors, "missing_tasks_directory", tasks_path, "expected task artifact directory")
    else:
        for path in sorted(tasks_path.iterdir()):
            if not path.is_dir() or not TASK_ID.fullmatch(path.name):
                _error(errors, "invalid_task_directory", path, "expected a directory named FAME-<number>")
                continue
            artifact = path / "TASK.json"
            if not artifact.is_file():
                _error(errors, "missing_task_artifact", artifact, "expected task artifact")
                continue
            task = _load_object(artifact, errors)
            if task is None:
                continue
            if task.get("id") != path.name:
                _error(errors, "task_id_mismatch", artifact, f"task id must equal directory name {path.name!r}")
            if not isinstance(task.get("status"), str) or not task["status"]:
                _error(errors, "missing_task_status", artifact, "task status must be a non-empty string")
            tasks[path.name] = task

    if current is not None:
        task_id = current.get("task_id")
        status = current.get("status")
        if status == "IDLE":
            if task_id is not None or current.get("phase") is not None:
                _error(errors, "idle_state_inconsistent", current_path, "IDLE state requires null task_id and phase")
        else:
            if not isinstance(task_id, str) or not task_id:
                _error(errors, "missing_current_task", current_path, "non-IDLE state requires a task_id")
            elif task_id not in tasks:
                _error(errors, "current_task_missing", current_path, f"no valid task artifact for {task_id!r}")
            elif status != tasks[task_id].get("status"):
                _error(errors, "current_status_mismatch", current_path, "current status must match the referenced task status")

    return SelfCheck(not errors, errors)
