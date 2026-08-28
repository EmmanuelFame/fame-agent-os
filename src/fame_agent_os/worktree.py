from __future__ import annotations
from pathlib import Path
import hashlib, json, os, shutil, subprocess
from datetime import datetime, timezone
from .verifier import run_commands

def branch_for(task_id: str) -> str: return f"fame/{task_id.lower()}"
def destination_for(root: Path, task_id: str) -> Path: return root.parent/".fame-worktrees"/root.name/task_id
def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _registry_task(root: Path, task_id: str) -> dict: return registry(root).get("tasks", {}).get(task_id, {})
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
    numbers=[]; active=[]
    for task_id, task in registry(root).get("tasks",{}).items():
        try: numbers.append(int(task_id[5:]))
        except ValueError: continue
        task_file=destination_for(root,task_id)/".fame"/"tasks"/task_id/"TASK.json"
        try: status=json.loads(task_file.read_text()).get("status",task.get("status"))
        except (OSError,json.JSONDecodeError): status=task.get("status")
        effective=dict(task); effective["status"]=status
        if status != "DONE" and (status != "FAILED" or is_recoverable_task(effective)): active.append(task_id)
    if active: return sorted(active)[0]
    for path in destination_for(root,"x").parent.glob("FAME-*"):
        try:
            number=int(path.name[5:]); numbers.append(number)
            task=path/".fame"/"tasks"/path.name/"TASK.json"
            if task.exists() and json.loads(task.read_text()).get("status") != "DONE": return path.name
        except ValueError: pass
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
    if not preparation.success: values["failure_stage"] = "PREPARATION"
    return record(root, task_id, **values)
def prepare_environment(worktree: Path, commands: list[str]):
    """Run only explicit project-owned setup in the isolated task worktree."""
    return run_commands(worktree, commands)
