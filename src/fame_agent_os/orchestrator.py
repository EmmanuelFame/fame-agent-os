from __future__ import annotations
from pathlib import Path
from .models import ModelResolver, Role
from .context import phase_prompt
from .state import create_task, transition
from .telemetry import append
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
   result=self.runner.run(phase_prompt(phase,task,self.root),spec,write=phase=="builder",cwd=str(self.root))
   append(self.root/".fame"/"logs"/"runs.jsonl",{"task_id":task["id"],"phase":phase,"role":role.value,"model":spec.model,"effort":spec.effort,"duration":result.duration,"status":"success" if result.returncode==0 else "failed",**{k:v for k,v in result.usage.items() if k!="raw"}})
   if result.returncode: transition(self.root,task["id"],"FAILED",phase); return task
   artifact={"architect":"PLAN.md","builder":"HANDOFF.md","verifier":"VERIFY.md"}[phase]
   (self.root/".fame"/"tasks"/task["id"]/artifact).write_text(
       f"# {phase.title()} result\n\nCodex phase completed successfully.\n")
  commands=self.config.get("verification",{}).get("commands",[])
  deterministic=verify(self.root,commands)
  if not deterministic.success:
   transition(self.root,task["id"],"FAILED","deterministic-verification"); return task
  transition(self.root,task["id"],"DONE","complete"); return task
