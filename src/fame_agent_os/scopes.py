from __future__ import annotations

import fnmatch
import re
import subprocess


def _ordered(scopes: list[dict]) -> list[dict]:
    return [scope for _, scope in sorted(enumerate(scopes), key=lambda item: (-int(item[1].get("priority", 0)), item[0]))]


def _paths(scope: dict) -> list[str]:
    return [str(path).lstrip("./") for path in scope.get("paths", scope.get("patterns", [])) if str(path)]


def _matches(scope: dict, task: str, paths: list[str]) -> bool:
    text = task.lower()
    name = str(scope.get("name", "")).lower()
    if name and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
        return True
    patterns = _paths(scope)
    for path in paths:
        if any(fnmatch.fnmatch(path.lstrip("./"), pattern) for pattern in patterns):
            return True
    # A named top-level component in a task is deterministic ownership evidence.
    return any(pattern.split("/", 1)[0].lower() in text for pattern in patterns if "/" in pattern)


def _optional(scope: dict, task: str, paths: list[str]) -> tuple[list[str], list[str]]:
    verification = scope.get("verification", {})
    checks = verification.get("optional", scope.get("optional_verification", []))
    patterns = verification.get("optional_when_paths", scope.get("optional_when_paths", []))
    required = bool(verification.get("optional_required", scope.get("optional_required", False)))
    explicit = any(term in task.lower() for term in ("production build", "optional check", "acceptance check"))
    relevant = required or explicit or any(any(fnmatch.fnmatch(path.lstrip("./"), pattern) for pattern in patterns) for path in paths)
    commands, available = [], []
    for check in checks:
        if isinstance(check, dict):
            command = check.get("command", "")
            when = check.get("when_paths", [])
            use = relevant or any(any(fnmatch.fnmatch(path.lstrip("./"), pattern) for pattern in when) for path in paths)
        else:
            command, use = str(check), relevant
        if command:
            (commands if use else available).append(command)
    return commands, available


def resolve(config: dict, task: str = "", paths: list[str] | None = None) -> dict:
    """Deterministically select configured monorepo scopes and their checks."""
    paths = [str(path) for path in (paths or [])]
    scopes = _ordered([scope for scope in config.get("scopes", []) if isinstance(scope, dict) and scope.get("name")])
    if not scopes:
        commands = list(config.get("verification", {}).get("commands", []))
        return {"scopes": [], "candidates": [], "ambiguous": False, "commands": commands,
                "skipped_commands": [], "optional_checks": [], "preparation": [], "environment_notes": []}
    selected = [scope for scope in scopes if _matches(scope, task, paths)]
    candidates = [] if selected else [scope["name"] for scope in scopes]
    commands, skipped, optional, preparation, notes = [], [], [], [], []
    for scope in selected:
        verification = scope.get("verification", {})
        commands.extend(verification.get("required", scope.get("required_verification", [])))
        chosen, available = _optional(scope, task, paths)
        commands.extend(chosen); optional.extend(available)
        preparation.extend(scope.get("preparation", {}).get("commands", scope.get("preparation_commands", [])))
        notes.extend(scope.get("environment_notes", []))
    # Preserve configured scope/command order while executing a command once.
    commands = list(dict.fromkeys(str(command) for command in commands if command))
    optional = list(dict.fromkeys(str(command) for command in optional if command and command not in commands))
    if selected:
        all_required = [command for scope in scopes for command in scope.get("verification", {}).get("required", scope.get("required_verification", []))]
        skipped = [command for command in dict.fromkeys(all_required) if command not in commands]
    return {"scopes": [scope["name"] for scope in selected], "candidates": candidates,
            "ambiguous": not selected, "commands": commands, "skipped_commands": skipped,
            "optional_checks": optional, "preparation": list(dict.fromkeys(str(command) for command in preparation if command)),
            "environment_notes": notes}


def diagnose(config: dict, root=None) -> dict:
    problems = []
    tracked = []
    if root is not None:
        tracked = subprocess.run(["git", "ls-files"], cwd=root, text=True, capture_output=True, check=False).stdout.splitlines()
    for scope in config.get("scopes", []):
        if not isinstance(scope, dict) or not scope.get("name"):
            problems.append("scope missing name")
            continue
        patterns = _paths(scope)
        if not patterns:
            problems.append(f"scope {scope['name']} has no ownership patterns")
        elif tracked and not any(fnmatch.fnmatch(path, pattern) for path in tracked for pattern in patterns):
            problems.append(f"scope {scope['name']} patterns match no tracked files")
        if scope.get("production_sensitive") and not scope.get("verification", {}).get("required", scope.get("required_verification", [])):
            problems.append(f"production-sensitive scope {scope['name']} has no required verification")
    return {"configured": [scope.get("name") for scope in config.get("scopes", []) if isinstance(scope, dict)],
            "legacy_repository_verification": not bool(config.get("scopes")), "problems": problems}
