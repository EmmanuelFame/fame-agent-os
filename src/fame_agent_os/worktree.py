from __future__ import annotations
from pathlib import Path
import hashlib, json, os, shutil, subprocess
from datetime import datetime, timezone
from .verifier import run_commands

def branch_for(task_id: str) -> str: return f"fame/{task_id.lower()}"
def destination_for(root: Path, task_id: str) -> Path: return root.parent/".fame-worktrees"/root.name/task_id
def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _registry_task(root: Path, task_id: str) -> dict: return registry(root).get("tasks", {}).get(task_id, {})
def _load_json(path: Path) -> dict:
    try: return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError): return {}
def _task_number(task_id: str) -> int | None:
    try: return int(task_id[5:]) if task_id.startswith("FAME-") else None
    except ValueError: return None
def _recovery_available(task: dict) -> bool: return bool(task.get("recovery", {}).get("available"))
def _preparation_failed(task: dict) -> bool: return task.get("preparation", {}).get("success") is False
def is_recoverable_task(task: dict) -> bool: return _recovery_available(task) and task.get("status") != "DONE"
def recovery_action(task: dict | None = None) -> str:
    task = task or {}
    if _preparation_failed(task):
        return "inspect the preparation failure output in the persistent worktree, fix the environment, then rerun fame_prepare_task"
    return "review or resume the persistent worktree manually; Fame will not delete it"
def existing_task_status(root: Path, task_id: str, destination: Path | None = None) -> str:
    destination = destination or destination_for(root, task_id)
    task_file = destination/".fame"/"tasks"/task_id/"TASK.json"
    if task_file.exists():
        try: return json.loads(task_file.read_text()).get("status") or _registry_task(root, task_id).get("status", "INTERRUPTED")
        except (OSError, json.JSONDecodeError): pass
    return _registry_task(root, task_id).get("status", "INTERRUPTED")
def registry_path(root: Path) -> Path:
    """Machine runtime state; deliberately never stored in the checkout."""
    state=Path(os.environ.get("XDG_STATE_HOME", Path.home()/".local"/"state")) / "fame"
    identity=hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return state / "production-tasks" / f"{identity}.json"
def registry(root: Path) -> dict:
    try: return json.loads(registry_path(root).read_text())
    except (OSError, json.JSONDecodeError): return {"project":str(root.resolve()),"tasks":{}}
def record(root: Path, task_id: str, **values) -> dict:
    data=registry(root); task=data.setdefault("tasks",{}).setdefault(task_id,{"task_id":task_id,"created_at":_now()})
    task.update(values); task["updated_at"]=_now(); registry_path(root).parent.mkdir(parents=True,exist_ok=True); registry_path(root).write_text(json.dumps(data,indent=2)+"\n")
    return task
def next_task_id(root: Path) -> str:
    numbers=[]
    for task_id in registry(root).get("tasks",{}):
        number = _task_number(task_id)
        if number is not None: numbers.append(number)
    tasks_dir = root/".fame"/"tasks"
    if tasks_dir.exists():
        for path in tasks_dir.glob("FAME-*"):
            number = _task_number(path.name)
            if number is not None: numbers.append(number)
    for path in destination_for(root,"x").parent.glob("FAME-*"):
        number = _task_number(path.name)
        if number is not None: numbers.append(number)
    return f"FAME-{max(numbers,default=0)+1:04d}"
def _git(root: Path, *args: str): return subprocess.run(["git",*args],cwd=root,text=True,capture_output=True,check=False)
def _registered(root: Path, destination: Path) -> bool:
    result=_git(root,"worktree","list","--porcelain")
    return result.returncode==0 and f"worktree {destination.resolve()}" in result.stdout
def preflight(root: Path) -> None:
    status=_git(root,"status","--porcelain")
    if status.returncode: raise RuntimeError(status.stderr.strip() or "worktree requires a Git checkout")
    if status.stdout.strip(): raise RuntimeError("production worktree requires a clean live Git checkout")
def create(root:Path, task_id:str) -> tuple[Path,str,bool]:
    """Provision (or safely recover) a task worktree outside the live checkout."""
    preflight(root)
    branch=branch_for(task_id); destination=destination_for(root,task_id)
    if destination.exists():
        if _registered(root,destination):
            current=_registry_task(root,task_id)
            record(root,task_id,status=existing_task_status(root,task_id,destination),branch=branch,worktree_path=str(destination),recovery={"available":True,"action":recovery_action(current)})
            return destination,branch,True
        raise RuntimeError(f"worktree destination already exists and is not registered: {destination}")
    if _git(root,"show-ref","--verify","--quiet",f"refs/heads/{branch}").returncode==0:
        raise RuntimeError(f"worktree branch already exists and is not recoverable: {branch}")
    destination.parent.mkdir(parents=True,exist_ok=True)
    added=_git(root,"worktree","add","-b",branch,str(destination))
    if added.returncode: raise RuntimeError(added.stderr.strip() or "could not create worktree")
    source=root/".fame"
    if source.exists(): shutil.copytree(source,destination/".fame",dirs_exist_ok=True,ignore=shutil.ignore_patterns("logs","cache","tmp"))
    record(root,task_id,status="PROVISIONED",branch=branch,worktree_path=str(destination),verification_state="NOT_RUN",recovery={"available":True,"action":recovery_action()})
    return destination,branch,False
def record_preparation(root: Path, task_id: str, branch: str, worktree_path: Path, preparation) -> dict:
    task = {"status": "FAILED" if not preparation.success else "PREPARED", "preparation": {"success": preparation.success, "results": preparation.results}}
    values = {"status": task["status"], "branch": branch, "worktree_path": str(worktree_path), "preparation": task["preparation"],
              "verification_state": "NOT_RUN", "recovery": {"available": True, "action": recovery_action(task)}}
    if not preparation.success:
        environment = any(result.get("returncode") in (126, 127) or result.get("error_type") == "FileNotFoundError" for result in preparation.results)
        values["failure_stage"] = "ENVIRONMENT" if environment else "PREPARATION"
    return record(root, task_id, **values)
def update_task_artifact_status(workspace: Path, task_id: str, status: str, **extra) -> dict:
    task_path = workspace/".fame"/"tasks"/task_id/"TASK.json"
    task = _load_json(task_path)
    task["status"] = status
    task.update(extra)
    task_path.write_text(json.dumps(task, indent=2) + "\n")
    return task
def inspect_task(root: Path, task_id: str) -> dict:
    current = _registry_task(root, task_id)
    workspace = Path(current.get("worktree_path") or destination_for(root, task_id))
    artifact = _load_json(workspace/".fame"/"tasks"/task_id/"TASK.json")
    status = artifact.get("status") or current.get("status") or ("MISSING" if not workspace.exists() else "UNKNOWN")
    return {"task_id": task_id, "status": status, "workspace": str(workspace), "branch": current.get("branch") or branch_for(task_id),
            "registry": current, "task": artifact, "recoverable": _recovery_available({**current, **artifact})}
def close_task(root: Path, task_id: str, reason: str) -> dict:
    info = inspect_task(root, task_id)
    workspace = Path(info["workspace"])
    if not info["registry"] and not info["task"]:
        raise RuntimeError(f"unknown task: {task_id}")
    closure = {"reason": reason, "closed_at": _now()}
    if workspace.exists() and (workspace/".fame"/"tasks"/task_id/"TASK.json").exists():
        update_task_artifact_status(workspace, task_id, "CLOSED", recovery={"available": False}, closure=closure)
    return record(root, task_id, status="CLOSED", branch=info["branch"], worktree_path=str(workspace),
                  recovery={"available": False, "action": ""}, closure=closure,
                  verification_state=info["registry"].get("verification_state", "NOT_RUN"))
def prepare_environment(worktree: Path, commands: list[str]):
    """Run only explicit project-owned setup in the isolated task worktree."""
    return run_commands(worktree, commands)
