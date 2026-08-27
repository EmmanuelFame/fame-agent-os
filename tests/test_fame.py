from __future__ import annotations
import json, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from fame_agent_os.router import Router
from fame_agent_os.models import ModelResolver, Role, ModelSpec
from fame_agent_os.installer import initialize, BEGIN, END
from fame_agent_os.state import next_task_id, create_task, transition
from fame_agent_os.codex import CodexRunner
from fame_agent_os.telemetry import parse_jsonl, aggregate, append
from fame_agent_os.graph import GraphAdapter
from fame_agent_os.policy import tier_allowed
from fame_agent_os.escalation import EscalationGovernor
from fame_agent_os.cli import main
from fame_agent_os.orchestrator import Orchestrator
from fame_agent_os.codex import CodexResult

class RoutingTests(unittest.TestCase):
 def test_routes_examples(self):
  r=Router(); self.assertEqual(r.route("Change the dashboard button from Save to Publish").classification,"F1")
  self.assertEqual(r.route("Add a normal CRUD endpoint following the existing pattern").classification,"F2")
  self.assertEqual(r.route("Debug an intermittent transaction failure across two services").classification,"F3")
  self.assertEqual(r.route("Redesign vendor settlement and ledger semantics").classification,"F4")
  self.assertEqual(r.route("destructive financial migration with unresolved accounting invariants").classification,"F5")
 def test_context_efficiency_diagnosis_is_f3(self):
  task = "Optimize context efficiency, diagnose excessive token usage, add regression tests and benchmark the improvement"
  route = Router().route(task)
  self.assertEqual(route.classification, "F3")
  self.assertEqual(route.role, Role.BUILDER)
  self.assertEqual(route.effort, "medium")

 def test_high_engineering_score_without_architecture_stays_builder(self):
  task = "Diagnose performance regression, benchmark it, add tests, implement fixes and optimize context efficiency"
  route = Router().route(task)
  self.assertEqual(route.classification, "F3")
  self.assertEqual(route.role, Role.BUILDER)
  self.assertEqual(route.effort, "medium")

 def test_budget_and_max(self):
  self.assertEqual(Router().route("redesign normal system", "economy").classification,"F2")
  self.assertTrue(Router().route("Redesign vendor settlement and ledger semantics",max_tier="builder").blocked)
  self.assertFalse(tier_allowed(__import__('fame_agent_os.models',fromlist=['Tier']).Tier.ARCHITECT,"builder"))
 def test_established_risk_pattern_lowers(self): self.assertEqual(Router().route("Add payment endpoint following approved pattern",established_decision=True).classification,"F2")

class StateTests(unittest.TestCase):
 def setUp(self): self.d=tempfile.TemporaryDirectory();self.root=Path(self.d.name); (self.root/".git").mkdir()
 def tearDown(self):self.d.cleanup()
 def test_init_idempotent_and_preserves_agents(self):
  (self.root/"AGENTS.md").write_text("my rules\n")
  initialize(self.root); first=(self.root/"AGENTS.md").read_text();initialize(self.root); second=(self.root/"AGENTS.md").read_text()
  self.assertIn("my rules",second);self.assertEqual(second.count(BEGIN),1);self.assertEqual(first,second);self.assertTrue((self.root/".fame/state/CURRENT.json").exists())
 def test_task_transitions(self):
  initialize(self.root); route=Router().route("add crud endpoint"); task=create_task(self.root,"x",route,"balanced",None);self.assertEqual(task["id"],"FAME-0001");transition(self.root,task["id"],"INTERRUPTED","builder");self.assertEqual(json.loads((self.root/".fame/tasks/FAME-0001/TASK.json").read_text())["status"],"INTERRUPTED")
 def test_self_check_accepts_consistent_state(self):
  initialize(self.root)
  with patch("fame_agent_os.cli.project_root",return_value=self.root), patch("fame_agent_os.codex.CodexRunner.run",side_effect=AssertionError("called")):
   self.assertEqual(main(["self-check","--json"]),0)
 def test_self_check_reports_current_task_mismatch(self):
  initialize(self.root)
  (self.root/".fame/state/CURRENT.json").write_text(json.dumps({"task_id":"FAME-9999","status":"PLANNED","phase":"created"}))
  with patch("fame_agent_os.cli.project_root",return_value=self.root):
   self.assertEqual(main(["self-check"]),1)

class RunnerTests(unittest.TestCase):
 def test_command_security(self):
  cmd=CodexRunner("codex").command(ModelSpec("model","low"),False);self.assertIn("read-only",cmd);self.assertNotIn("--yolo",cmd);self.assertNotIn("fast", " ".join(cmd).lower())
 def test_jsonl_unknown_tolerated(self):
  u=parse_jsonl('{"type":"other"}\n{"usage":{"input_tokens":5,"output_tokens":2,"reasoning_output_tokens":1}}');self.assertEqual(u["input_tokens"],5);self.assertEqual(u["output_tokens"],2)
 def test_missing_codex(self):
  with self.assertRaises(RuntimeError): CodexRunner("definitely-not-codex").run("x",ModelSpec("m","low"))
 def test_catalog_mock(self):
  with patch("subprocess.run") as run:
   run.return_value=subprocess.CompletedProcess([],0,"gpt-x\n",""); models,note=CodexRunner().models();self.assertEqual(models,["gpt-x"]);self.assertIn("detected",note)

class OtherTests(unittest.TestCase):
 def test_resolver_override_and_high_only_architect(self):
  r=ModelResolver({"models":{"builder":{"model":"other","effort":"medium"}}});self.assertEqual(r.resolve(Role.BUILDER).model,"other");self.assertEqual(r.resolve(Role.ARCHITECT,True).effort,"high")
 def test_telemetry(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"runs.jsonl";append(p,{"task_id":"A","role":"builder","status":"success","input_tokens":4,"output_tokens":3,"reasoning_output_tokens":1});a=aggregate(p);self.assertEqual(a["by_role"]["builder"]["output_tokens"],3)
 def test_graph_absent(self):
  g=GraphAdapter("certainly-none");self.assertFalse(g.status(Path("."))["available"]);self.assertFalse(g.update(Path("."))[0])
 def test_escalation_governor(self):
  e=EscalationGovernor();self.assertIsNone(e.record(Role.OPERATOR,"a","test"));self.assertIsNone(e.record(Role.OPERATOR,"a","test"));self.assertEqual(e.record(Role.OPERATOR,"b","test"),Role.BUILDER)
  self.assertIsNone(EscalationGovernor().record(Role.BUILDER,"network","environmental"));self.assertEqual(EscalationGovernor().record(Role.BUILDER,"a","test",True),Role.ARCHITECT)
 def test_dry_run_and_route_do_not_run_codex(self):
  with patch("fame_agent_os.codex.CodexRunner.run",side_effect=AssertionError("called")):
   self.assertEqual(main(["route","Change button label"]),0);self.assertEqual(main(["task","Change button label","--dry-run"]),0)
 def test_production_guard(self):
  with tempfile.TemporaryDirectory() as d, patch("fame_agent_os.cli.project_root",return_value=Path(d)):
   root=Path(d);(root/".git").mkdir();initialize(root,True)
   self.assertEqual(main(["task","Change button label"]),2)
 def test_orchestrator_isolates_phases_and_writes_artifacts(self):
  class FakeRunner:
   def __init__(self): self.calls=[]
   def run(self,prompt,spec,write,cwd): self.calls.append((spec.model,write,prompt));return CodexResult(0,"{}","",0.01,{"input_tokens":1,"cached_input_tokens":0,"cache_write_tokens":0,"output_tokens":1,"reasoning_output_tokens":0,"raw":[]})
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/".git").mkdir();initialize(root);runner=FakeRunner();task=Orchestrator(root,{"models":{},"verification":{"commands":[]}},runner).task("Redesign vendor settlement and ledger semantics",Router().route("Redesign vendor settlement and ledger semantics"),"balanced",None)
   self.assertEqual(task["id"],"FAME-0001");self.assertEqual(len(runner.calls),3);self.assertFalse(runner.calls[0][1]);self.assertTrue(runner.calls[1][1]);self.assertTrue((root/".fame/tasks/FAME-0001/PLAN.md").exists());self.assertTrue((root/".fame/tasks/FAME-0001/VERIFY.md").exists())
