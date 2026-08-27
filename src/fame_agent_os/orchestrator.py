from __future__ import annotations
from pathlib import Path
from .models import ModelResolver, Role
from .context import build_phase_context
from .state import create_task, transition
from .telemetry import append, context_metrics, context_warnings
from .errors import HumanGate
from .verifier import verify

class Orchestrator:
 def __init__(self,root:Path,config:dict,runner): self.root=root; self.config=config; self.runner=runner; self.resolver=ModelResolver(config)
 def dry_run(self,route): return {"route":route.classification,"phases":route.phases,"models":{p:(self.resolver.resolve(Role(p) if p != "verifier" else Role.OPERATOR).model) for p in route.phases if p != "deterministic"},"graph_query":False,"worktree":False}
 def task(self,goal,route,budget,max_tier,dry_run=False):
  if route.blocked: raise HumanGate("Required route is blocked by --max-tier")
  if dry_run:return self.dry_run(route)
  task=create_task(self.root,goal,route,budget,max_tier)
  if route.classification=="F0": transition(self.root,task["id"],"DONE","deterministic"); return task
  for phase in route.phases:
   role=Role.OPERATOR if phase=="verifier" else Role(phase); spec=self.resolver.resolve(role,route.classification=="F5" and role is Role.ARCHITECT)
   context=build_phase_context(phase,task,self.root,self.config.get("context",{}))
   result=self.runner.run(context.prompt,spec,write=phase=="builder",cwd=str(self.root))
   usage={k:v for k,v in result.usage.items() if k!="raw"};metrics=context_metrics(usage.get("input_tokens",0),usage.get("cached_input_tokens",0))
   append(self.root/".fame"/"logs"/"runs.jsonl",{"task_id":task["id"],"phase":phase,"role":role.value,"model":spec.model,"effort":spec.effort,"duration":result.duration,"status":"success" if result.returncode==0 else "failed",**usage,**metrics,"context_diagnostics":context.diagnostics,"context_warnings":context_warnings(metrics,context.diagnostics,self.config.get("context",{}))})
   if result.returncode: transition(self.root,task["id"],"FAILED",phase); return task
   artifact={"architect":"PLAN.md","builder":"HANDOFF.md","verifier":"VERIFY.md"}[phase]
   changed=[]
   if phase=="builder":
    import subprocess
    changed=subprocess.run(["git","diff","--name-only"],cwd=self.root,text=True,capture_output=True,check=False).stdout.splitlines()[:40]
   body=f"# {phase.title()} result\n\nCodex phase completed successfully.\n"
   if changed: body+="\nChanged files for verifier (bounded):\n"+"\n".join(f"- `{path}`" for path in changed)+"\n"
   (self.root/".fame"/"tasks"/task["id"]/artifact).write_text(body)
  commands=self.config.get("verification",{}).get("commands",[])
  deterministic=verify(self.root,commands)
  if not deterministic.success:
   transition(self.root,task["id"],"FAILED","deterministic-verification"); return task
  transition(self.root,task["id"],"DONE","complete")
  return __import__("json").loads(
   (self.root/".fame"/"tasks"/task["id"]/"TASK.json").read_text()
  )
