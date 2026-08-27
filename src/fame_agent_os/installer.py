from __future__ import annotations
from pathlib import Path
import shutil
import tomllib
from .config import write_json
from .state import SCHEMA_VERSION

BEGIN="<!-- FAME_AGENT_OS:BEGIN -->"; END="<!-- FAME_AGENT_OS:END -->"
SECTION=BEGIN+"\n# Fame Agent OS\n\n- Consult Fame state before rediscovering completed work.\n- Use structural navigation before broad scanning when available; source is authoritative.\n- Do not re-plan approved decisions without evidence or silently redesign architecture.\n- Use targeted verification, update task state after meaningful work, and verify acceptance criteria before DONE.\n- Escalate unresolved ambiguity rather than repeatedly guessing; minimize unnecessary context.\n"+END+"\n"
IGNORE=(".fame/logs/", ".fame/cache/", ".fame/tmp/", "graphify-out/")
CODEX_BEGIN="# BEGIN FAME AGENT OS CODEX INTEGRATION"
CODEX_END="# END FAME AGENT OS CODEX INTEGRATION"
CODEX_CONFIG=(CODEX_BEGIN+"\n[mcp_servers.fame]\ncommand = \"fame\"\nargs = [\"mcp\"]\n"+CODEX_END+"\n")
SKILL='''---
name: fame
description: Route repository engineering work through Fame before broad exploration.
---

# Fame Agent OS

Use this skill for repository engineering requests, including explicit `$fame ...` requests.

1. Call `fame_route` before broad repository exploration.
2. Respect its classification, selected agent, phases, blocked state, max-tier, and production requirements.
3. Call `fame_preflight`, then `fame_prepare_task` before modifying files. Determine configured scope before broad scanning; if a worktree path is returned, work there only.
4. Delegate to the exact selected Fame custom agent. Do not independently choose Sol/Terra/Luna or duplicate its work.
5. Call `fame_finish_task` after implementation so scoped deterministic verification and state recording run before reporting completion; do not run unrelated monorepo suites.
6. Never merge, deploy, restart services, delete persistent worktrees, or bypass an F5 human gate.

Keep responses concise. Return paths and state references rather than large file bodies. For non-engineering conversation, do not activate this workflow.
'''
AGENTS = {
    "fame-operator.toml": ("gpt-5.6-luna", "low", "Mechanical, bounded changes following established patterns."),
    "fame-builder-low.toml": ("gpt-5.6-terra", "low", "Normal F2 implementation with targeted source inspection."),
    "fame-builder-medium.toml": ("gpt-5.6-terra", "medium", "Difficult F3 engineering and debugging without architectural authority."),
    "fame-architect.toml": ("gpt-5.6-sol", "medium", "F4/F5 planning, diagnosis, constraints, and acceptance criteria."),
    "fame-verifier.toml": ("gpt-5.6-luna", "low", "Verify changed files and deterministic evidence; avoid broad rediscovery."),
}

def _agent_toml(filename: str, model: str, effort: str, responsibility: str) -> str:
    name = filename.removesuffix(".toml")
    return (f'# Fame-managed profile. Edit .fame/config.json for model policy.\n'
            f'name = "{name}"\ndescription = "{responsibility}"\nmodel = "{model}"\n'
            f'model_reasoning_effort = "{effort}"\n'
            f'developer_instructions = "You are the Fame {name} agent. {responsibility} Respect Fame state, bounded context, production worktrees, and human gates."\n')

def _merge_codex_config(path: Path) -> str:
    old = path.read_text() if path.exists() else ""
    if CODEX_BEGIN in old and CODEX_END in old:
        start, end = old.index(CODEX_BEGIN), old.index(CODEX_END) + len(CODEX_END)
        new = old[:start] + CODEX_CONFIG.rstrip("\n") + old[end:]
    else:
        try:
            parsed = tomllib.loads(old) if old.strip() else {}
        except tomllib.TOMLDecodeError as exc:
            raise RuntimeError(f"existing Codex config is invalid TOML: {exc}") from exc
        if isinstance(parsed.get("mcp_servers"), dict) and "fame" in parsed["mcp_servers"]:
            return "preserved existing mcp_servers.fame configuration"
        new = old.rstrip() + ("\n\n" if old.strip() else "") + CODEX_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(new)
    return "installed project-scoped Fame MCP configuration"

def codex_install(root: Path) -> list[str]:
    actions = [_merge_codex_config(root/".codex"/"config.toml")]
    skill = root/".agents"/"skills"/"fame"/"SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True); skill.write_text(SKILL)
    actions.append("installed Fame skill")
    for filename, (model, effort, responsibility) in AGENTS.items():
        path = root/".codex"/"agents"/filename
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(_agent_toml(filename, model, effort, responsibility))
    actions.append(f"installed {len(AGENTS)} Fame custom agents")
    merge_agents(root/"AGENTS.md"); actions.append("updated Fame-controlled AGENTS.md section")
    return actions

def codex_status(root: Path) -> dict:
    config = root/".codex"/"config.toml"; skill = root/".agents"/"skills"/"fame"/"SKILL.md"; agent_dir = root/".codex"/"agents"
    config_valid, config_error = False, None
    if config.is_file():
        try: tomllib.loads(config.read_text()); config_valid = True
        except tomllib.TOMLDecodeError as exc: config_error = str(exc)
    agents = {name: (agent_dir/name).is_file() for name in AGENTS}
    mcp = False
    if config_valid: mcp = "fame" in tomllib.loads(config.read_text()).get("mcp_servers", {})
    launchable = shutil.which("fame") is not None
    return {"project_config": str(config), "config_valid": config_valid, "config_error": config_error,
            "mcp_configured": mcp, "mcp_launchable": launchable, "skill_installed": skill.is_file(),
            "agents": agents, "agents_complete": all(agents.values()),
            "healthy": config_valid and mcp and skill.is_file() and all(agents.values())}
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
