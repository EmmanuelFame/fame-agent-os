from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .config import write_json, load_json

SCHEMA_VERSION="1"
def now() -> str: return datetime.now(timezone.utc).isoformat()
def fame_dir(root: Path) -> Path: return root/".fame"
def next_task_id(root: Path) -> str:
    tasks=fame_dir(root)/"tasks"; nums=[]
    if tasks.exists():
        for p in tasks.iterdir():
            if p.name.startswith("FAME-"):
                try: nums.append(int(p.name[5:]))
                except ValueError: pass
    return f"FAME-{max(nums, default=0)+1:04d}"
def create_task(root: Path, goal: str, route, budget: str, max_tier: str | None, task_id: str | None=None) -> dict:
    task_id=task_id or next_task_id(root); task={"id":task_id,"goal":goal,"acceptance_criteria":["Implementation matches task goal","Configured verification succeeds"],"class":route.classification,"risk_indicators":list(route.reasons),"route":{"role":route.role.value if route.role else None,"effort":route.effort,"phases":route.phases},"budget_mode":budget,"max_tier":max_tier,"status":"PLANNED","timestamps":{"created":now()},"graph_context":{}}
    d=fame_dir(root)/"tasks"/task_id; d.mkdir(parents=True); write_json(d/"TASK.json",task); write_json(fame_dir(root)/"state"/"CURRENT.json",{"task_id":task_id,"status":"PLANNED","phase":"created","updated":now()}); return task
def transition(root: Path, task_id: str, status: str, phase: str) -> None:
    p=fame_dir(root)/"tasks"/task_id/"TASK.json"; task=load_json(p); task["status"]=status; task.setdefault("timestamps",{})[status.lower()]=now(); write_json(p,task); write_json(fame_dir(root)/"state"/"CURRENT.json",{"task_id":task_id,"status":status,"phase":phase,"updated":now()})
