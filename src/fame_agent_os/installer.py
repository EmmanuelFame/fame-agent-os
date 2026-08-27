from __future__ import annotations
from pathlib import Path
from .config import write_json
from .state import SCHEMA_VERSION

BEGIN="<!-- FAME_AGENT_OS:BEGIN -->"; END="<!-- FAME_AGENT_OS:END -->"
SECTION=BEGIN+"\n# Fame Agent OS\n\n- Consult Fame state before rediscovering completed work.\n- Use structural navigation before broad scanning when available; source is authoritative.\n- Do not re-plan approved decisions without evidence or silently redesign architecture.\n- Use targeted verification, update task state after meaningful work, and verify acceptance criteria before DONE.\n- Escalate unresolved ambiguity rather than repeatedly guessing; minimize unnecessary context.\n"+END+"\n"
IGNORE=(".fame/logs/", ".fame/cache/", ".fame/tmp/", "graphify-out/")
def merge_agents(path: Path) -> None:
    old=path.read_text() if path.exists() else ""
    if BEGIN in old and END in old:
        start=old.index(BEGIN); finish=old.index(END,start)+len(END); new=old[:start]+SECTION.rstrip("\n")+old[finish:]
    else: new=(old.rstrip()+"\n\n" if old.strip() else "")+SECTION
    path.write_text(new)
def merge_ignore(path: Path) -> None:
    old=path.read_text() if path.exists() else ""; lines=old.splitlines(); existing=set(lines)
    lines.extend(x for x in IGNORE if x not in existing); path.write_text("\n".join(lines)+"\n")
def initialize(root: Path, production: bool=False) -> list[str]:
    f=root/".fame"; (f/"state").mkdir(parents=True,exist_ok=True); (f/"tasks").mkdir(exist_ok=True); (f/"logs").mkdir(exist_ok=True); (f/"cache").mkdir(exist_ok=True); (f/"tmp").mkdir(exist_ok=True)
    if not (f/"schema-version").exists(): (f/"schema-version").write_text(SCHEMA_VERSION+"\n")
    if not (f/"config.json").exists(): write_json(f/"config.json", {"budget":"balanced","verification":{"commands":[]},"graph":{"budget":400},"production":production})
    if not (f/"state"/"PROJECT.md").exists(): (f/"state"/"PROJECT.md").write_text("# Project\n\nStable architecture notes belong here.\n")
    if not (f/"state"/"DECISIONS.md").exists(): (f/"state"/"DECISIONS.md").write_text("# Decisions\n\nDurable architectural decisions and rationale.\n")
    if not (f/"state"/"CURRENT.json").exists(): write_json(f/"state"/"CURRENT.json", {"task_id":None,"status":"IDLE","phase":None})
    merge_agents(root/"AGENTS.md"); merge_ignore(root/".gitignore")
    return ["initialized .fame state", "merged AGENTS.md", "updated .gitignore"]
