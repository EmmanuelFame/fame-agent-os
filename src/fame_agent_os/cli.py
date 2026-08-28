from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path
from . import __version__
from .codex import CodexRunner
from .config import project_root, merged_config, project_config
from .graph import GraphAdapter
from .installer import initialize, codex_install, codex_status
from .mcp import serve as serve_mcp, doctor as mcp_doctor
from .models import ModelResolver, Role
from .orchestrator import Orchestrator
from .router import Router
from .self_check import check as self_check
from .state import fame_dir
from .telemetry import aggregate, benchmark
from .verifier import verify
from .scopes import resolve as resolve_scopes
from .worktree import (create as create_worktree, existing_task_status,
                       next_task_id as next_worktree_task_id,
                       preflight as production_preflight, prepare_environment,
                       record as record_production, record_preparation,
                       recovery_action, registry as production_registry)

def emit(value, as_json=False):
    if as_json: print(json.dumps(value,indent=2)); return
    if isinstance(value,str): print(value)
    else: print(json.dumps(value,indent=2))
def common(p): p.add_argument("--budget",choices=["economy","balanced","quality"]); p.add_argument("--max-tier",choices=["operator","builder","architect","luna","terra","sol"]); p.add_argument("--dry-run",action="store_true")
def route_data(route, resolver): return {"class":route.classification,"role":route.role.value if route.role else None,"reasoning":route.effort,"risk":route.risk,"reason":list(route.reasons),"blocked":route.blocked,"model":resolver.resolve(route.role).model if route.role else None,"phases":route.phases}
def parser():
 p=argparse.ArgumentParser(prog="fame",description="Fame Agent OS");p.add_argument("--version",action="version",version=__version__); sub=p.add_subparsers(dest="command",required=True)
 i=sub.add_parser("init");i.add_argument("--production",action="store_true")
 sub.add_parser("doctor"); sub.add_parser("models")
 r=sub.add_parser("route");r.add_argument("task"); common(r);r.add_argument("--json",action="store_true")
 for name in ("task","plan","debug"):
  q=sub.add_parser(name);q.add_argument("task");common(q);q.add_argument("--worktree",action="store_true")
 v=sub.add_parser("verify");v.add_argument("--json",action="store_true");v.add_argument("--task",default="");v.add_argument("--path",dest="paths",action="append",default=[])
 s=sub.add_parser("self-check", help="validate Fame project state without invoking Codex");s.add_argument("--json",action="store_true")
 sub.add_parser("status")
 u=sub.add_parser("usage");u.add_argument("--task");u.add_argument("--json",action="store_true")
 b=sub.add_parser("benchmark",help="compare context-token telemetry between two tasks");b.add_argument("--before",required=True);b.add_argument("--after",required=True);b.add_argument("--json",action="store_true")
 g=sub.add_parser("graph");gsub=g.add_subparsers(dest="graph_command",required=True);gsub.add_parser("status");gsub.add_parser("update")
 m=sub.add_parser("mcp", help="start the Fame stdio MCP server")
 c=sub.add_parser("codex", help="manage Codex extension integration");csub=c.add_subparsers(dest="codex_command",required=True)
 ci=csub.add_parser("install", help="install project-scoped Fame Codex integration");ci.add_argument("--project",action="store_true")
 csub.add_parser("status", help="diagnose project-scoped Fame Codex integration")
 return p
def main(argv=None):
 args=parser().parse_args(argv); root=project_root(); config=merged_config(root); runner=CodexRunner(config.get("codex_binary","codex")); graph=GraphAdapter(config.get("graphify_binary","graphify"))
 if args.command=="mcp": return serve_mcp(root)
 if args.command=="codex":
  if args.codex_command=="install":
   if not args.project: print("codex install requires --project",file=sys.stderr); return 2
   try: emit({"actions":codex_install(root),"status":codex_status(root)}); return 0
   except (RuntimeError, OSError) as e: print(str(e),file=sys.stderr); return 2
  emit(codex_status(root)); return 0 if codex_status(root)["healthy"] else 2
 if args.command=="init": emit({"actions":initialize(root,args.production),"root":str(root)});return 0
 if args.command=="models":
  resolver=ModelResolver(config); catalog,note=runner.models(); emit({"note":note,"models":[{"role":r.value,"model":resolver.resolve(r).model,"reasoning":resolver.resolve(r).effort,"catalog_known":resolver.resolve(r).model in catalog if catalog else None} for r in Role]});return 0
 if args.command=="doctor":
  git=shutil.which("git"); codex=runner.available(); catalog,note=runner.models() if codex else ([],"Codex absent")
  production=project_config(root).get("production",False); commands=project_config(root).get("verification",{}).get("commands",[])
  report=mcp_doctor(root); report.update({"python":sys.version.split()[0],"git":bool(git),"git_repository":(root/".git").exists(),"codex":codex,"model_catalog":note,"graph":graph.status(root)})
  emit(report);return 0 if not production or (report["production"]["deterministic_verification_configured"] and report["production"]["live_checkout_clean"]) else 2
 if args.command=="graph":
  if args.graph_command=="status":emit(graph.status(root));return 0
  ok,msg=graph.update(root);emit({"success":ok,"message":msg});return 0 if ok else 1
 if args.command in ("route","task","plan","debug"):
  budget=getattr(args,"budget",None) or config.get("budget",config.get("default_budget","balanced")); route=Router().route(args.task,budget,getattr(args,"max_tier",None),"approved pattern" in args.task.lower())
  if args.command=="route":emit(route_data(route,ModelResolver(config)),args.json);return 2 if route.blocked else 0
  if args.command in ("plan","debug") or args.dry_run:
   data=route_data(route,ModelResolver(config)); data["dry_run"]=True; data["codex_calls"]=0; emit(data); return 2 if route.blocked else 0
  if route.blocked:
   print("Required route is blocked by --max-tier",file=sys.stderr); return 2
  production=project_config(root).get("production")
  if production and not args.worktree:
   print("Production project guard: use --worktree for modifying task.",file=sys.stderr);return 2
  scope=resolve_scopes(config,args.task)
  if production and not scope["commands"]:
   print("Production project unsafe: configure deterministic verification commands for the selected scope.",file=sys.stderr);return 2
  if args.worktree:
   try:
   # All guards run before choosing an ID or creating any persistent task resource.
    production_preflight(root)
    task_id=next_worktree_task_id(root)
    # Reserve only after preflight, so an interrupted git operation can reuse this ID.
    if not (root.parent/".fame-worktrees"/root.name/task_id).exists():
     record_production(root,task_id,status="PROVISIONING",branch=f"fame/{task_id.lower()}",worktree_path=str(root.parent/".fame-worktrees"/root.name/task_id),verification_state="NOT_RUN",recovery={"available":True,"action":"retry provisioning or review persistent worktree"})
    path,branch,recovered=create_worktree(root,task_id)
    if recovered:
     task=production_registry(root)["tasks"].get(task_id,{})
     status=existing_task_status(root,task_id,path)
     record_production(root,task_id,status=status,branch=branch,worktree_path=str(path),recovery={"available":True,"action":task.get("recovery",{}).get("action") or recovery_action(task)})
     response={"task_id":task_id,"status":status,"worktree":str(path),"branch":branch,"changed_files":{"project":[],"fame_metadata":[]},"verification_result":None,"recovery":production_registry(root)["tasks"][task_id]["recovery"],"review_instructions":"Review or resume this persistent worktree manually; it was not deleted, merged, deployed, or restarted."}
     if task.get("preparation",{}).get("success") is False: response.update({"preparation":task.get("preparation"),"recoverable":True})
     emit(response); return 2
    preparation=prepare_environment(path,scope["preparation"])
    record_preparation(root,task_id,branch,path,preparation)
    if not preparation.success:
     emit({"task_id":task_id,"status":"FAILED","worktree":str(path),"branch":branch,"scopes":scope["scopes"],"preparation":{"success":False,"results":preparation.results},"recoverable":True,"recovery":production_registry(root)["tasks"][task_id]["recovery"]}); return 2
    worktree_config=merged_config(path); result=Orchestrator(path,worktree_config,runner).task(args.task,route,budget,args.max_tier,task_id=task_id)
    changed=[line[3:] for line in subprocess.run(["git","status","--porcelain"],cwd=path,text=True,capture_output=True,check=False).stdout.splitlines()]
    grouped={"project":[p for p in changed if not p.startswith(".fame/")],"fame_metadata":[p for p in changed if p.startswith(".fame/")]}
    task=production_registry(root)["tasks"].get(task_id,{})
    if task.get("preparation",{}).get("success") is False:
     emit({"task_id":task_id,"status":task.get("status","FAILED"),"worktree":str(path),"branch":branch,"preparation":task.get("preparation"),"recoverable":True,"recovery":task.get("recovery"),"review_instructions":"Fix the preparation failure in the persistent worktree, then rerun fame_prepare_task from the live checkout."}); return 2
    record_production(root,task_id,status=result.get("status"),branch=branch,worktree_path=str(path),verification_state="PASSED" if result.get("verification",{}).get("success") else "FAILED" if result.get("verification") else "NOT_RUN",verification=result.get("verification"),recovery={"available":True,"action":recovery_action()})
    emit({"task_id":result.get("id"),"status":result.get("status"),"worktree":str(path),"branch":branch,"changed_files":grouped,"verification_result":result.get("verification"),"recovery":production_registry(root)["tasks"][task_id]["recovery"],"review_instructions":"Review changes in the persistent worktree, then merge or deploy manually. Fame never merges, deploys, restarts services, modifies the live branch, or deletes this worktree."}); return 0 if result.get("status")=="DONE" else 1
   except RuntimeError as e: print(str(e),file=sys.stderr);return 2
  try: result=Orchestrator(root,config,runner).task(args.task,route,budget,args.max_tier);emit({"task_id":result.get("id"),"status":result.get("status","started"),"scopes":result.get("scope",{}).get("scopes",[])});return 0
  except Exception as e: print(str(e),file=sys.stderr);return 2
 if args.command=="verify":
  scope=resolve_scopes(project_config(root),args.task,args.paths); result=verify(root,scope["commands"]); emit({"success":result.success,"results":result.results,"scopes":scope["scopes"],"scope_ambiguity":scope["ambiguous"],"candidate_scopes":scope["candidates"],"commands_selected":scope["commands"],"commands_skipped":scope["skipped_commands"],"optional_checks":scope["optional_checks"]},args.json);return 0 if result.success else 1
 if args.command=="self-check":
  result=self_check(root); emit({"success":result.success,"errors":result.errors},args.json);return 0 if result.success else 1
 if args.command=="status":
  state=json.loads((fame_dir(root)/"state"/"CURRENT.json").read_text()) if (fame_dir(root)/"state"/"CURRENT.json").exists() else {"status":"NOT_INITIALIZED"}
  state["production_tasks"]=list(production_registry(root).get("tasks",{}).values()); emit(state);return 0
 if args.command=="usage": emit(aggregate(fame_dir(root)/"logs"/"runs.jsonl",args.task),args.json);return 0
 if args.command=="benchmark": emit(benchmark(fame_dir(root)/"logs"/"runs.jsonl",args.before,args.after),args.json);return 0
 return 1
