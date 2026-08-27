from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import merged_config, project_config, project_root, write_json
from .installer import codex_status
from .models import ModelResolver
from .router import Router
from .state import create_task, fame_dir, next_task_id as next_local_task_id, transition
from .telemetry import aggregate
from .verifier import verify
from .scopes import diagnose as diagnose_scopes, resolve as resolve_scopes
from .worktree import (create as create_worktree, destination_for, next_task_id,
                       preflight, prepare_environment, record, registry)

TOOLS = {
    "fame_route": {"task": "string", "budget": "string?", "max_tier": "string?", "human_approved": "boolean?"},
    "fame_doctor": {}, "fame_preflight": {"task": "string", "budget": "string?", "max_tier": "string?", "human_approved": "boolean?"},
    "fame_status": {}, "fame_verify": {"task": "string?", "paths": "array?"}, "fame_usage": {"task_id": "string?"},
    "fame_prepare_task": {"task": "string", "paths": "array?", "budget": "string?", "max_tier": "string?", "human_approved": "boolean?"},
    "fame_finish_task": {"task_id": "string", "workspace": "string?", "project_path": "string?", "success": "boolean?"},
    "fame_recover": {},
}

def route_result(root: Path, args: dict) -> dict:
    config = merged_config(root); budget = args.get("budget") or config.get("budget", config.get("default_budget", "balanced"))
    route = Router().route(args.get("task", ""), budget, args.get("max_tier"), bool(args.get("human_approved")))
    role = route.role.value if route.role else None
    resolver = ModelResolver(config)
    spec = resolver.resolve(route.role) if route.role else None
    return {"classification": route.classification, "role": role, "reasoning_effort": route.effort,
            "risk": route.risk, "model_role": role, "model": spec.model if spec else None,
            "selected_agent": {"F1": "fame-operator", "F2": "fame-builder-low", "F3": "fame-builder-medium",
                               "F4": "fame-architect", "F5": "fame-architect"}.get(route.classification),
            "phases": route.phases, "blocked": route.blocked, "reasons": list(route.reasons), "budget": budget}

def doctor(root: Path) -> dict:
    config = project_config(root); commands = config.get("verification", {}).get("commands", [])
    scope_report = diagnose_scopes(config, root)
    has_verification = bool(commands) or any(resolve_scopes(config, scope.get("name", ""))["commands"] for scope in config.get("scopes", []) if isinstance(scope, dict))
    integration = codex_status(root)
    git = (root/".git").exists()
    production = bool(config.get("production", False))
    return {"fame_version": __import__("fame_agent_os").__version__, "project_initialized": fame_dir(root).is_dir(),
            "schema_version": (fame_dir(root)/"schema-version").read_text().strip() if (fame_dir(root)/"schema-version").exists() else None,
            "git": git, "production": {"enabled": production, "deterministic_verification_configured": has_verification,
            "live_checkout_clean": _git_clean(root), "safe": not production or has_verification},
            "codex_cli_backend": bool(__import__("shutil").which(config.get("codex_binary", "codex"))),
            "extension_integration": integration, "graphify": {"available": bool(__import__("shutil").which(config.get("graphify_binary", "graphify"))),
            "graph_exists": (root/"graphify-out").exists()},
            "scopes": scope_report,
            "safety_problems": (["production verification commands are not configured"] if production and not has_verification else []) + (["production live checkout is not clean"] if production and has_verification and not _git_clean(root) else []) + scope_report["problems"]}

def _git_clean(root: Path) -> bool:
    import subprocess
    p = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=False)
    return p.returncode == 0 and not p.stdout.strip()

def preflight_result(root: Path, args: dict) -> dict:
    route = route_result(root, args); config = project_config(root); production = bool(config.get("production", False))
    problems = []
    if not fame_dir(root).is_dir(): problems.append("project is not initialized; run fame init")
    if route["blocked"]: problems.append("route blocked by max-tier")
    if route["classification"] == "F5" and not args.get("human_approved"): problems.append("F5 requires explicit human approval")
    if production and not resolve_scopes(config, args.get("task", ""), args.get("paths", []))["commands"]: problems.append("production verification commands are not configured for selected scope")
    if production and not _git_clean(root): problems.append("production live checkout is not clean")
    return {"allowed": not problems, "requires_worktree": production, "problems": problems, "route": route}

def status(root: Path) -> dict:
    current = __import__("json").loads((fame_dir(root)/"state"/"CURRENT.json").read_text()) if (fame_dir(root)/"state"/"CURRENT.json").exists() else {"status": "NOT_INITIALIZED"}
    return {"local_task": current, "production_tasks": list(registry(root).get("tasks", {}).values()), "recovery": recover(root)}

def recover(root: Path) -> dict:
    tasks = []
    for task_id, item in registry(root).get("tasks", {}).items():
        if item.get("status") not in ("DONE", "FAILED"):
            tasks.append({"task_id": task_id, "status": item.get("status"), "worktree": item.get("worktree_path"),
                          "action": "review or resume persistent worktree; Fame will not delete it"})
    return {"interrupted_or_active": tasks, "actions": ["inspect the reported worktree", "resume with fame_prepare_task or review manually", "merge only after human review"]}

def prepare(root: Path, args: dict) -> dict:
    check = preflight_result(root, args)
    if not check["allowed"]: return check
    config = merged_config(root)
    budget = args.get("budget") or config.get("budget", config.get("default_budget", "balanced"))
    route = Router().route(args["task"], budget, args.get("max_tier"), bool(args.get("human_approved")))
    scope = resolve_scopes(config, args["task"], args.get("paths", []))
    task_id = next_task_id(root) if check["requires_worktree"] else next_local_task_id(root)
    workspace = root
    branch = None
    if check["requires_worktree"]:
        preflight(root)
        record(root, task_id, status="PROVISIONING", branch=f"fame/{task_id.lower()}", worktree_path=str(destination_for(root, task_id)), verification_state="NOT_RUN", recovery={"available": True})
        workspace, branch, recovered = create_worktree(root, task_id)
        if recovered: return {"allowed": True, "recovered": True, "task_id": task_id, "workspace": str(workspace), "branch": branch, "route": route_result(root, args)}
        preparation = prepare_environment(workspace, scope["preparation"])
        record(root, task_id, status="PREPARED" if preparation.success else "PREPARATION_FAILED", branch=branch,
               worktree_path=str(workspace), preparation={"success": preparation.success, "results": preparation.results},
               recovery={"available": True, "action": "review or resume persistent worktree"})
        if not preparation.success:
            return {"allowed": False, "task_id": task_id, "workspace": str(workspace), "branch": branch,
                    "recoverable": True, "preparation": {"success": False, "results": preparation.results}, "scopes": scope["scopes"]}
    task = create_task(workspace, args["task"], route, budget, args.get("max_tier"), task_id)
    task["scope"] = scope; write_json(fame_dir(workspace)/"tasks"/task_id/"TASK.json", task)
    if branch: record(root, task_id, status="PROVISIONED", branch=branch, worktree_path=str(workspace), verification_state="NOT_RUN", recovery={"available": True})
    return {"allowed": True, "task_id": task_id, "workspace": str(workspace), "project_path": str(root), "branch": branch,
            "selected_agent": route_result(root, args)["selected_agent"], "phases": route.phases,
            "verification_policy": "deterministic-first" if route.classification in ("F1", "F2") else "strong-review-required",
            "acceptance": task["acceptance_criteria"], "route": route_result(root, args),
            "scopes": scope["scopes"], "scope_ambiguity": scope["ambiguous"], "candidate_scopes": scope["candidates"],
            "verification_commands": scope["commands"], "optional_checks": scope["optional_checks"],
            "preparation": {"configured": bool(scope["preparation"]), "commands": scope["preparation"]}}

def finish(root: Path, args: dict) -> dict:
    workspace = Path(args.get("workspace") or root).resolve(); task_id = args["task_id"]
    task_path = fame_dir(workspace)/"tasks"/task_id/"TASK.json"
    if not task_path.exists(): return {"success": False, "error": f"task not found: {task_id}"}
    config = project_config(workspace)
    import subprocess
    changed_paths = [line[3:] for line in subprocess.run(["git", "status", "--porcelain"], cwd=workspace, text=True, capture_output=True, check=False).stdout.splitlines() if not line[3:].startswith(".fame/")]
    task = json.loads(task_path.read_text()); scope = resolve_scopes(config, task.get("goal", ""), changed_paths)
    result = verify(workspace, scope["commands"])
    if args.get("success") is False: result = type(result)(False, [{"error": "extension reported failure"}] + result.results)
    task["scope"] = scope; task["verification"] = {"success": result.success, "results": result.results};
    task_path.write_text(json.dumps(task, indent=2) + "\n")
    final_status = "DONE" if result.success else "FAILED"
    transition(workspace, task_id, final_status, "complete" if result.success else "deterministic-verification")
    task["status"] = final_status
    changed = []
    p = subprocess.run(["git", "status", "--porcelain"], cwd=workspace, text=True, capture_output=True, check=False)
    changed = [line[3:] for line in p.stdout.splitlines()]
    project_root_path = Path(args.get("project_path") or root)
    if project_config(project_root_path).get("production"):
        record(project_root_path, task_id, status=task["status"], worktree_path=str(workspace), verification_state="PASSED" if result.success else "FAILED", verification=task["verification"], recovery={"available": True})
    return {"success": result.success, "task_id": task_id, "status": task["status"], "workspace": str(workspace),
            "changed_files": {"project": [p for p in changed if not p.startswith(".fame/")], "fame_metadata": [p for p in changed if p.startswith(".fame/")]},
            "verification": task["verification"], "scopes": scope["scopes"], "scope_ambiguity": scope["ambiguous"],
            "commands_selected": scope["commands"], "commands_skipped": scope["skipped_commands"],
            "optional_checks": scope["optional_checks"], "automatic_merge": False, "automatic_deploy": False}

def call(root: Path, name: str, args: dict) -> dict:
    if name == "fame_route": return route_result(root, args)
    if name == "fame_doctor": return doctor(root)
    if name == "fame_preflight": return preflight_result(root, args)
    if name == "fame_status": return status(root)
    if name == "fame_verify":
        paths = args.get("paths", [])
        if not paths:
            import subprocess
            paths = [line[3:] for line in subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=False).stdout.splitlines()]
        scope = resolve_scopes(project_config(root), args.get("task", ""), paths); result = verify(root, scope["commands"])
        return {"success": result.success, "results": result.results, "scopes": scope["scopes"], "scope_ambiguity": scope["ambiguous"], "candidate_scopes": scope["candidates"], "commands_selected": scope["commands"], "commands_skipped": scope["skipped_commands"], "optional_checks": scope["optional_checks"]}
    if name == "fame_usage": return aggregate(fame_dir(root)/"logs"/"runs.jsonl", args.get("task_id"))
    if name == "fame_prepare_task": return prepare(root, args)
    if name == "fame_finish_task": return finish(root, args)
    if name == "fame_recover": return recover(root)
    raise ValueError(f"unknown Fame MCP tool: {name}")

def serve(root: Path | None = None) -> int:
    root = project_root(root); _log("Fame MCP server ready")
    for line in sys.stdin:
        try: request = json.loads(line)
        except json.JSONDecodeError:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}); continue
        if request.get("method", "").startswith("notifications/"): continue
        method, request_id = request.get("method"), request.get("id")
        try:
            if method == "initialize": result = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "fame", "version": __import__("fame_agent_os").__version__}}
            elif method == "tools/list": result = {"tools": [{"name": name, "description": f"Deterministic Fame operation: {name}", "inputSchema": {"type": "object", "properties": {k: {"type": "boolean" if v == "boolean?" else "array" if v == "array?" else "string"} for k, v in schema.items()}}} for name, schema in TOOLS.items()]}
            elif method == "tools/call":
                params = request.get("params", {}); value = call(root, params.get("name", ""), params.get("arguments", {})); result = {"content": [{"type": "text", "text": json.dumps(value, separators=(",", ":"))}], "structuredContent": value}
            elif method == "ping": result = {}
            else: raise ValueError(f"method not found: {method}")
            _write({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as exc:
            _write({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}})
    return 0

def _write(value: dict) -> None: sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n"); sys.stdout.flush()
def _log(message: str) -> None: print(message, file=sys.stderr)
