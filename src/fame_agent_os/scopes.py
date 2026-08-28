from __future__ import annotations

import fnmatch
import re
import subprocess


DOC_PATTERNS = [
    "docs/*.md",
    "docs/*.txt",
    "docs/**/*.md",
    "docs/**/*.txt",
    "README.md",
    "README*.md",
    "CHANGELOG*",
    "CONTRIBUTING*",
    "LICENSE*",
]
CONTROL_PATTERNS = [
    ".fame/*",
    ".fame/**/*",
    ".codex/*",
    ".codex/**/*",
    ".agents/*",
    ".agents/**/*",
    "AGENTS.md",
]

def _normalize(path: str) -> str:
    return str(path)[2:] if str(path).startswith("./") else str(path)


def _ordered(scopes: list[dict]) -> list[dict]:
    return [scope for _, scope in sorted(enumerate(scopes), key=lambda item: (-int(item[1].get("priority", 0)), item[0]))]


def _paths(scope: dict) -> list[str]:
    return [_normalize(str(path)) for path in scope.get("paths", scope.get("patterns", [])) if str(path)]


def _token_matches(text: str, token: str) -> bool:
    return bool(token) and re.search(rf"(?<![\w./-]){re.escape(token)}(?![\w-])", text) is not None


def _task_refs(task: str) -> list[str]:
    return re.findall(r"[\w./-]+", task.lower())


def _path_evidence(scope: dict, paths: list[str]) -> bool:
    patterns = _paths(scope)
    return any(any(fnmatch.fnmatch(_normalize(path), pattern) for pattern in patterns) for path in paths)


def _task_evidence(scope: dict, task: str) -> bool:
    text = task.lower()
    name = str(scope.get("name", "")).lower()
    if name and _token_matches(text, name):
        return True
    refs = _task_refs(task)
    patterns = _paths(scope)
    for ref in refs:
        if any(fnmatch.fnmatch(ref.lstrip("./"), pattern) for pattern in patterns):
            return True
    for pattern in patterns:
        top = pattern.split("/", 1)[0].rstrip("*").lower()
        if top and _token_matches(text, top):
            return True
    return False


def _optional(scope: dict, task: str, paths: list[str]) -> tuple[list[str], list[str]]:
    verification = scope.get("verification", {})
    checks = verification.get("optional", scope.get("optional_verification", []))
    patterns = verification.get("optional_when_paths", scope.get("optional_when_paths", []))
    required = bool(verification.get("optional_required", scope.get("optional_required", False)))
    explicit = any(term in task.lower() for term in ("production build", "optional check", "acceptance check"))
    relevant = required or explicit or any(any(fnmatch.fnmatch(_normalize(path), pattern) for pattern in patterns) for path in paths)
    commands, available = [], []
    for check in checks:
        if isinstance(check, dict):
            command = check.get("command", "")
            when = check.get("when_paths", [])
            use = relevant or any(any(fnmatch.fnmatch(_normalize(path), pattern) for pattern in when) for path in paths)
        else:
            command, use = str(check), relevant
        if command:
            (commands if use else available).append(command)
    return commands, available


def _python_parse_command(module: str, paths: list[str]) -> str:
    return (
        "python3 -c "
        f"\"import pathlib, sys, {module}; "
        f"[{module}.loads(pathlib.Path(p).read_text()) for p in sys.argv[1:]]\" "
        + " ".join(repr(path) for path in paths)
    )


def _self_check_command() -> str:
    return (
        "python3 -c "
        "\"import json, sys; sys.path.insert(0, 'src'); "
        "from pathlib import Path; from fame_agent_os.self_check import check; "
        "result = check(Path('.')); "
        "print(json.dumps({'success': result.success, 'errors': result.errors})); "
        "raise SystemExit(0 if result.success else 1)\""
    )


def _builtin_scope(name: str, paths: list[str]) -> dict:
    if name == "documentation":
        return {
            "name": "documentation",
            "paths": DOC_PATTERNS,
            "priority": -100,
            "verification": {"required": ["git diff --check"]},
            "preparation": {"commands": []},
        }
    normalized = [_normalize(path) for path in paths if any(fnmatch.fnmatch(_normalize(path), pattern) for pattern in CONTROL_PATTERNS)]
    commands = ["git diff --check"]
    json_paths = [path for path in normalized if path.endswith(".json")]
    toml_paths = [path for path in normalized if path.endswith(".toml")]
    if json_paths:
        commands.append(_python_parse_command("json", json_paths))
    if toml_paths:
        commands.append(_python_parse_command("tomllib", toml_paths))
    if normalized:
        commands.append(_self_check_command())
    return {
        "name": "fame-control-plane",
        "paths": CONTROL_PATTERNS,
        "priority": -100,
        "verification": {"required": commands},
        "preparation": {"commands": []},
    }


def _configured_scopes(config: dict) -> list[dict]:
    return [scope for scope in config.get("scopes", []) if isinstance(scope, dict) and scope.get("name")]


def _builtin_scopes(config: dict, paths: list[str]) -> list[dict]:
    configured_names = {str(scope.get("name", "")).lower() for scope in _configured_scopes(config)}
    scopes = []
    if "documentation" not in configured_names:
        scopes.append(_builtin_scope("documentation", paths))
    scopes.append(_builtin_scope("fame-control-plane", paths))
    return scopes


def resolve(config: dict, task: str = "", paths: list[str] | None = None) -> dict:
    """Deterministically select configured monorepo scopes and safe built-in fallbacks."""
    paths = [_normalize(str(path)) for path in (paths or []) if str(path)]
    configured = _ordered(_configured_scopes(config))
    if not configured and not paths and not task:
        commands = list(config.get("verification", {}).get("commands", []))
        return {"scopes": [], "candidates": [], "ambiguous": False, "scope_state": "resolved", "commands": commands,
                "skipped_commands": [], "optional_checks": [], "preparation": [], "environment_notes": [], "unmatched_paths": []}
    all_scopes = configured + _ordered(_builtin_scopes(config, paths))
    if paths:
        selected = [scope for scope in all_scopes if _path_evidence(scope, paths)]
    else:
        selected = [scope for scope in all_scopes if _task_evidence(scope, task)]
    candidates = [] if selected else [scope["name"] for scope in configured] or [scope["name"] for scope in all_scopes]
    commands, skipped, optional, preparation, notes = [], [], [], [], []
    for scope in selected:
        verification = scope.get("verification", {})
        commands.extend(verification.get("required", scope.get("required_verification", [])))
        chosen, available = _optional(scope, task, paths)
        commands.extend(chosen)
        optional.extend(available)
        preparation.extend(scope.get("preparation", {}).get("commands", scope.get("preparation_commands", [])))
        notes.extend(scope.get("environment_notes", []))
    commands = list(dict.fromkeys(str(command) for command in commands if command))
    optional = list(dict.fromkeys(str(command) for command in optional if command and command not in commands))
    if selected:
        all_required = [command for scope in all_scopes for command in scope.get("verification", {}).get("required", scope.get("required_verification", []))]
        skipped = [command for command in dict.fromkeys(all_required) if command not in commands]
    if not selected and not configured:
        commands = list(config.get("verification", {}).get("commands", []))
    unmatched = [path for path in paths if not any(_path_evidence(scope, [path]) for scope in all_scopes)]
    return {"scopes": [scope["name"] for scope in selected], "candidates": candidates, "ambiguous": not selected and bool(configured),
            "scope_state": "resolved" if selected or not configured else "pending", "commands": commands, "skipped_commands": skipped,
            "optional_checks": optional, "preparation": list(dict.fromkeys(str(command) for command in preparation if command)),
            "environment_notes": notes, "unmatched_paths": unmatched}


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
            "legacy_repository_verification": not bool(config.get("scopes")), "problems": problems, "builtins": ["documentation", "fame-control-plane"]}
