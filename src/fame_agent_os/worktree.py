from __future__ import annotations
from pathlib import Path
import subprocess, tempfile
def create(root:Path, task_id:str) -> tuple[Path,str]:
    status=subprocess.run(["git","status","--porcelain"],cwd=root,text=True,capture_output=True,check=False)
    if status.returncode or status.stdout.strip(): raise RuntimeError("worktree requires a clean Git checkout")
    branch=f"fame/{task_id.lower()}"; destination=Path(tempfile.gettempdir())/f"fame-{task_id.lower()}"
    p=subprocess.run(["git","worktree","add","-b",branch,str(destination)],cwd=root,text=True,capture_output=True,check=False)
    if p.returncode: raise RuntimeError(p.stderr.strip() or "could not create worktree")
    return destination,branch
