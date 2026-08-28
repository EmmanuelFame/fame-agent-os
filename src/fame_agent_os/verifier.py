from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path
@dataclass
class Verification: success:bool; results:list[dict]
def run_commands(root:Path, commands:list[str]) -> Verification:
    results=[]
    for command in commands:
        # Commands are project-owned configuration; no shell is used: split only simple argv strings.
        import shlex
        args=shlex.split(command)
        try: p=subprocess.run(args,cwd=root,text=True,capture_output=True,check=False)
        except FileNotFoundError as exc:
            results.append({"command":args,"argv":args,"returncode":127,"stdout":"","stderr":str(exc),"error_type":"FileNotFoundError"})
            continue
        results.append({"command":args,"argv":args,"returncode":p.returncode,"stdout":p.stdout[-4000:],"stderr":p.stderr[-4000:]})
    return Verification(all(x["returncode"]==0 for x in results),results)
def verify(root:Path, commands:list[str]) -> Verification:
    if not commands: return Verification(False,[{"command":[],"returncode":None,"stdout":"","stderr":"no deterministic verification commands configured"}])
    return run_commands(root,commands)
