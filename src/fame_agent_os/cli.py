from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path
from . import __version__
from .codex import CodexRunner
from .config import project_root, merged_config, project_config
from .graph import GraphAdapter
from .installer import initialize
from .models import ModelResolver, Role
from .orchestrator import Orchestrator
from .router import Router
from .self_check import check as self_check
from .state import fame_dir
from .telemetry import aggregate
from .verifier import verify
from .worktree import create as create_worktree

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
 v=sub.add_parser("verify");v.add_argument("--json",action="store_true")
 s=sub.add_parser("self-check", help="validate Fame project state without invoking Codex");s.add_argument("--json",action="store_true")
 sub.add_parser("status")
 u=sub.add_parser("usage");u.add_argument("--task");u.add_argument("--json",action="store_true")
 g=sub.add_parser("graph");gsub=g.add_subparsers(dest="graph_command",required=True);gsub.add_parser("status");gsub.add_parser("update")
 return p
def main(argv=None):
 args=parser().parse_args(argv); root=project_root(); config=merged_config(root); runner=CodexRunner(config.get("codex_binary","codex")); graph=GraphAdapter(config.get("graphify_binary","graphify"))
 if args.command=="init": emit({"actions":initialize(root,args.production),"root":str(root)});return 0
 if args.command=="models":
  resolver=ModelResolver(config); catalog,note=runner.models(); emit({"note":note,"models":[{"role":r.value,"model":resolver.resolve(r).model,"reasoning":resolver.resolve(r).effort,"catalog_known":resolver.resolve(r).model in catalog if catalog else None} for r in Role]});return 0
 if args.command=="doctor":
  git=shutil.which("git"); codex=runner.available(); catalog,note=runner.models() if codex else ([],"Codex absent")
  emit({"fame_version":__version__,"python":sys.version.split()[0],"git":bool(git),"git_repository":(root/".git").exists(),"codex":codex,"model_catalog":note,"graph":graph.status(root),"project_initialized":fame_dir(root).exists(),"schema_version":(fame_dir(root)/"schema-version").read_text().strip() if (fame_dir(root)/"schema-version").exists() else None});return 0
 if args.command=="graph":
  if args.graph_command=="status":emit(graph.status(root));return 0
  ok,msg=graph.update(root);emit({"success":ok,"message":msg});return 0 if ok else 1
 if args.command in ("route","task","plan","debug"):
  budget=getattr(args,"budget",None) or config.get("budget",config.get("default_budget","balanced")); route=Router().route(args.task,budget,getattr(args,"max_tier",None),"approved pattern" in args.task.lower())
  if args.command=="route":emit(route_data(route,ModelResolver(config)),args.json);return 2 if route.blocked else 0
  if args.command in ("plan","debug") or args.dry_run:
   data=route_data(route,ModelResolver(config)); data["dry_run"]=True; data["codex_calls"]=0; emit(data); return 2 if route.blocked else 0
  if project_config(root).get("production") and not args.worktree:
   print("Production project guard: use --worktree for modifying task.",file=sys.stderr);return 2
  if args.worktree:
   try: path,branch=create_worktree(root,"FAME-PENDING"); emit({"worktree":str(path),"branch":branch,"note":"No automatic merge or deploy."});return 0
   except RuntimeError as e: print(str(e),file=sys.stderr);return 2
  try: result=Orchestrator(root,config,runner).task(args.task,route,budget,args.max_tier);emit({"task_id":result.get("id"),"status":result.get("status","started")});return 0
  except Exception as e: print(str(e),file=sys.stderr);return 2
 if args.command=="verify":
  result=verify(root,project_config(root).get("verification",{}).get("commands",[])); emit({"success":result.success,"results":result.results},args.json);return 0 if result.success else 1
 if args.command=="self-check":
  result=self_check(root); emit({"success":result.success,"errors":result.errors},args.json);return 0 if result.success else 1
 if args.command=="status": emit(json.loads((fame_dir(root)/"state"/"CURRENT.json").read_text()) if (fame_dir(root)/"state"/"CURRENT.json").exists() else {"status":"NOT_INITIALIZED"});return 0
 if args.command=="usage": emit(aggregate(fame_dir(root)/"logs"/"runs.jsonl",args.task),args.json);return 0
 return 1
