from __future__ import annotations
import io, json, subprocess, tempfile, unittest, tomllib
from pathlib import Path
from unittest.mock import patch
from fame_agent_os import __version__
from fame_agent_os.router import Router
from fame_agent_os.models import ModelResolver, Role, ModelSpec
from fame_agent_os.installer import initialize, BEGIN, END
from fame_agent_os.state import next_task_id, create_task, transition
from fame_agent_os.codex import CodexRunner
from fame_agent_os.telemetry import parse_jsonl, aggregate, append, context_metrics, context_warnings, benchmark
from fame_agent_os.context import build_phase_context
from fame_agent_os.graph import GraphAdapter
from fame_agent_os.policy import tier_allowed
from fame_agent_os.escalation import EscalationGovernor
from fame_agent_os.cli import main
from fame_agent_os.orchestrator import Orchestrator
from fame_agent_os.codex import CodexResult
from fame_agent_os.mcp import serve, call, TOOLS
from fame_agent_os.installer import codex_install, codex_status
from fame_agent_os.scopes import resolve as resolve_scopes
from fame_agent_os.worktree import prepare_environment


class VersionTests(unittest.TestCase):
 def test_package_version_matches_pyproject(self):
  root = Path(__file__).resolve().parents[1]
  data = tomllib.loads((root/"pyproject.toml").read_text())
  self.assertEqual(__version__, data["project"]["version"])

class V13IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.d=tempfile.TemporaryDirectory(); self.root=Path(self.d.name); (self.root/".git").mkdir(); initialize(self.root)
 def tearDown(self): self.d.cleanup()
 def test_codex_installer_is_idempotent_and_preserves_config(self):
  config=self.root/".codex/config.toml"; config.parent.mkdir(); config.write_text('[profiles.custom]\nmodel = "user-model"\n')
  first=codex_install(self.root); contents=config.read_text(); second=codex_install(self.root)
  self.assertIn('model = "user-model"', config.read_text()); self.assertEqual(contents,config.read_text()); self.assertEqual(first,second)
  self.assertTrue(codex_status(self.root)["healthy"]); self.assertEqual(__import__("tomllib").loads(contents)["mcp_servers"]["fame"]["args"],["mcp"])
 def test_mcp_initialize_list_route_and_malformed_request(self):
  requests='not-json\n'+json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}})+'\n'+json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})+'\n'+json.dumps({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fame_route","arguments":{"task":"Change button label"}}})+'\n'
  output=io.StringIO()
  with patch("sys.stdin",io.StringIO(requests)), patch("sys.stdout",output): self.assertEqual(serve(self.root),0)
  rows=[json.loads(x) for x in output.getvalue().splitlines()]
  self.assertEqual(rows[0]["error"]["code"],-32700); self.assertEqual(rows[1]["result"]["serverInfo"]["name"],"fame")
  self.assertEqual(len(rows[2]["result"]["tools"]),len(TOOLS)); self.assertEqual(json.loads(rows[3]["result"]["content"][0]["text"])["selected_agent"],"fame-operator")
 def test_blocked_mcp_prepare_creates_no_task(self):
  result=call(self.root,"fame_prepare_task",{"task":"destructive financial migration with unresolved accounting invariants","max_tier":"builder"})
  self.assertFalse(result["allowed"]); self.assertFalse((self.root/".fame/tasks/FAME-0001").exists())
 def test_mcp_prepare_uses_local_task_sequence_outside_production(self):
  route=Router().route("Change button label"); create_task(self.root,"existing",route,"balanced",None)
  result=call(self.root,"fame_prepare_task",{"task":"Change another button label"})
  self.assertTrue(result["allowed"]); self.assertEqual(result["task_id"],"FAME-0002")
 def test_prohibition_does_not_trigger_risk_route(self):
  route=Router().route("Never deploy automatically; change the button label")
  self.assertEqual(route.classification,"F1"); self.assertEqual(route.risk,"low")
 def test_mcp_finish_runs_deterministic_verification(self):
  config=json.loads((self.root/".fame/config.json").read_text()); config["verification"]["commands"]=["true"]; (self.root/".fame/config.json").write_text(json.dumps(config))
  route=Router().route("Change button label"); task=create_task(self.root,"Change button label",route,"balanced",None)
  result=call(self.root,"fame_finish_task",{"task_id":task["id"]})
  self.assertTrue(result["success"]); self.assertEqual(result["status"],"DONE")
 def test_mcp_reports_scopes_concisely(self):
  config=json.loads((self.root/".fame/config.json").read_text()); config["scopes"]=[{"name":"frontend","paths":["web/**"],"verification":{"required":["true"]}}]; (self.root/".fame/config.json").write_text(json.dumps(config))
  result=call(self.root,"fame_prepare_task",{"task":"Update frontend component"})
  self.assertEqual(result["scopes"],["frontend"]); self.assertEqual(result["verification_commands"],["true"]); self.assertFalse(result["scope_ambiguity"])

class ScopeTests(unittest.TestCase):
 def config(self):
  return {"verification":{"commands":["legacy"]},"scopes":[
   {"name":"frontend","paths":["web/**"],"priority":10,"verification":{"required":["frontend-test","shared"],"optional":["frontend-build"],"optional_when_paths":["web/package.json"]}},
   {"name":"backend","paths":["api/**"],"verification":{"required":["backend-test","shared"]},"preparation":{"commands":["true"]},"production_sensitive":True}]}
 def test_legacy_single_project_config_still_works(self):
  result=resolve_scopes({"verification":{"commands":["legacy-test"]}})
  self.assertEqual(result["commands"],["legacy-test"]); self.assertFalse(result["ambiguous"])
 def test_frontend_and_backend_are_scoped(self):
  self.assertEqual(resolve_scopes(self.config(),"fix web button")["commands"],["frontend-test","shared"])
  self.assertEqual(resolve_scopes(self.config(),"fix api handler")["commands"],["backend-test","shared"])
 def test_multi_scope_deduplicates_and_orders_commands(self):
  result=resolve_scopes(self.config(),"change web and api",["web/a.ts","api/a.py"])
  self.assertEqual(result["scopes"],["frontend","backend"]); self.assertEqual(result["commands"],["frontend-test","shared","backend-test"])
 def test_ambiguous_task_returns_candidates(self):
  result=resolve_scopes(self.config(),"Update shared release notes")
  self.assertTrue(result["ambiguous"]); self.assertEqual(result["candidates"],["frontend","backend"]); self.assertEqual(result["commands"],[])
 def test_optional_check_requires_explicit_policy_or_relevant_path(self):
  self.assertEqual(resolve_scopes(self.config(),"fix web button")["optional_checks"],["frontend-build"])
  self.assertIn("frontend-build",resolve_scopes(self.config(),"fix web manifest",["web/package.json"])["commands"])
 def test_missing_dependencies_do_not_invent_preparation(self):
  result=resolve_scopes(self.config(),"fix web button")
  self.assertEqual(result["preparation"],[])
 def test_preparation_only_runs_in_the_given_worktree_and_failure_is_reported(self):
  with tempfile.TemporaryDirectory() as d:
   live=Path(d)/"live"; worktree=Path(d)/"worktree"; live.mkdir(); worktree.mkdir()
   prepared=prepare_environment(worktree,["python3 -c \"from pathlib import Path; Path('prepared').write_text('ok')\""])
   failed=prepare_environment(worktree,["false"])
   self.assertTrue(prepared.success); self.assertTrue((worktree/"prepared").exists()); self.assertFalse((live/"prepared").exists()); self.assertFalse(failed.success)

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
   p=Path(d)/"runs.jsonl";append(p,{"task_id":"A","role":"builder","status":"success","input_tokens":4,"cached_input_tokens":3,"output_tokens":3,"reasoning_output_tokens":1});a=aggregate(p);self.assertEqual(a["by_role"]["builder"]["output_tokens"],3);self.assertEqual(a["by_role"]["builder"]["fresh_input_tokens"],1);self.assertEqual(a["by_role"]["builder"]["cache_ratio"],.75)
 def test_context_metrics_warnings_and_benchmark(self):
  self.assertEqual(context_metrics(10,7)["fresh_input_tokens"],3)
  self.assertIn("fresh_input_above_threshold",context_warnings(context_metrics(11,0),settings={"fresh_input_warning_tokens":10}))
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"runs.jsonl";append(p,{"task_id":"before","role":"builder","input_tokens":100,"cached_input_tokens":60});append(p,{"task_id":"after","role":"builder","input_tokens":50,"cached_input_tokens":40})
   report=benchmark(p,"before","after");self.assertEqual(report["delta"]["fresh_input_tokens"],-30);self.assertEqual(report["fresh_input_reduction_ratio"],.75)
 def test_bounded_phase_context_and_verifier_handoff(self):
  task={"id":"FAME-0001","goal":"x","acceptance_criteria":["works"]}
  verifier=build_phase_context("verifier",task,Path("."),{"max_source_files":2})
  self.assertIn("HANDOFF.md",verifier.prompt);self.assertIn("git diff --stat",verifier.prompt);self.assertEqual(verifier.diagnostics["source_file_limit"],2)
  with self.assertRaises(ValueError): build_phase_context("builder",task,Path("."),{"max_prompt_chars":1})
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
   def run(self,prompt,spec,write,cwd): self.calls.append((spec.model,write,prompt));return CodexResult(0,"{}","",0.01,{"input_tokens":1,"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":1,"reasoning_output_tokens":0,"raw":[]})
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/".git").mkdir();initialize(root);runner=FakeRunner();task=Orchestrator(root,{"models":{},"verification":{"commands":["true"]}},runner).task("Redesign vendor settlement and ledger semantics",Router().route("Redesign vendor settlement and ledger semantics"),"balanced",None)
   self.assertEqual(task["id"],"FAME-0001");self.assertEqual(task["status"],"DONE");self.assertEqual(len(runner.calls),3);self.assertFalse(runner.calls[0][1]);self.assertTrue(runner.calls[1][1]);self.assertTrue((root/".fame/tasks/FAME-0001/PLAN.md").exists());self.assertTrue((root/".fame/tasks/FAME-0001/VERIFY.md").exists())
   rows=[json.loads(line) for line in (root/".fame/logs/runs.jsonl").read_text().splitlines()]
   self.assertTrue(all("context_diagnostics" in row and "fresh_input_tokens" in row for row in rows))
 def test_production_worktree_runs_task_without_changing_live_checkout(self):
  class FakeRunner:
   def run(self,prompt,spec,write,cwd):
    if write: (Path(cwd)/"builder-change.txt").write_text("isolated")
    return CodexResult(0,"{}","",0.01,{"input_tokens":1,"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":1,"reasoning_output_tokens":0,"raw":[]})
  with tempfile.TemporaryDirectory() as d, patch.dict("os.environ",{"XDG_STATE_HOME":str(Path(d).parent/(Path(d).name+"-machine-state"))}), patch("fame_agent_os.cli.project_root",return_value=Path(d)), patch("fame_agent_os.cli.CodexRunner",return_value=FakeRunner()):
   root=Path(d); subprocess.run(["git","init"],cwd=root,check=True,capture_output=True); subprocess.run(["git","config","user.email","test@example.com"],cwd=root,check=True); subprocess.run(["git","config","user.name","Test"],cwd=root,check=True)
   (root/"README").write_text("base"); subprocess.run(["git","add","README"],cwd=root,check=True); subprocess.run(["git","commit","-m","base"],cwd=root,check=True,capture_output=True)
   initialize(root,True); config=json.loads((root/".fame/config.json").read_text()); config["verification"]["commands"]=["true"]; config["scopes"]=[{"name":"api","paths":["api/**"],"verification":{"required":["true"]},"preparation":{"commands":["python3 -c \"from pathlib import Path; Path('prepared').write_text('ok')\""]}}]; (root/".fame/config.json").write_text(json.dumps(config)); subprocess.run(["git","add","."],cwd=root,check=True); subprocess.run(["git","commit","-m","initialize fame"],cwd=root,check=True,capture_output=True)
   self.assertEqual(main(["task","Change api button label","--worktree"]),0)
   worktree=root.parent/".fame-worktrees"/root.name/"FAME-0001"; self.assertTrue(worktree.exists()); self.assertTrue((worktree/"prepared").exists()); self.assertFalse((root/"prepared").exists()); self.assertTrue((worktree/"builder-change.txt").exists()); self.assertFalse((root/"builder-change.txt").exists()); self.assertEqual(subprocess.run(["git","branch","--show-current"],cwd=root,text=True,capture_output=True,check=True).stdout.strip(),"master")
   task_path=worktree/".fame/tasks/FAME-0001/TASK.json"; task=json.loads(task_path.read_text()); task["status"]="INTERRUPTED"; task_path.write_text(json.dumps(task)); self.assertEqual(main(["task","Change api button label","--worktree"]),2); self.assertFalse((worktree.parent/"FAME-0002").exists())
 def test_production_preflight_rejections_create_no_worktree(self):
  with tempfile.TemporaryDirectory() as d, patch.dict("os.environ",{"XDG_STATE_HOME":str(Path(d).parent/(Path(d).name+"-machine-state"))}), patch("fame_agent_os.cli.project_root",return_value=Path(d)):
   root=Path(d); subprocess.run(["git","init"],cwd=root,check=True,capture_output=True); initialize(root,True)
   (root/"dirty.txt").write_text("dirty")
   self.assertEqual(main(["task","Change button label","--worktree"]),2)
   self.assertFalse((root.parent/".fame-worktrees"/root.name).exists())
   self.assertEqual(main(["task","Redesign vendor settlement and ledger semantics","--worktree","--max-tier","builder"]),2)
   self.assertFalse((root.parent/".fame-worktrees"/root.name).exists())
 def test_production_status_is_visible_without_dirtying_live_checkout(self):
  class FakeRunner:
   def run(self,prompt,spec,write,cwd): return CodexResult(0,"{}","",0.01,{"input_tokens":1,"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":1,"reasoning_output_tokens":0,"raw":[]})
  with tempfile.TemporaryDirectory() as d, patch.dict("os.environ",{"XDG_STATE_HOME":str(Path(d).parent/(Path(d).name+"-machine-state"))}), patch("fame_agent_os.cli.project_root",return_value=Path(d)), patch("fame_agent_os.cli.CodexRunner",return_value=FakeRunner()), patch("sys.stdout",new_callable=io.StringIO) as output:
   root=Path(d); subprocess.run(["git","init"],cwd=root,check=True,capture_output=True); subprocess.run(["git","config","user.email","test@example.com"],cwd=root,check=True); subprocess.run(["git","config","user.name","Test"],cwd=root,check=True); (root/"README").write_text("base"); subprocess.run(["git","add","README"],cwd=root,check=True); subprocess.run(["git","commit","-m","base"],cwd=root,check=True,capture_output=True)
   initialize(root,True); config=json.loads((root/".fame/config.json").read_text()); config["verification"]["commands"]=["true"]; (root/".fame/config.json").write_text(json.dumps(config)); subprocess.run(["git","add","."],cwd=root,check=True); subprocess.run(["git","commit","-m","fame"],cwd=root,check=True,capture_output=True)
   self.assertEqual(main(["task","Change button label","--worktree"]),0); output.seek(0); output.truncate(0); self.assertEqual(main(["status"]),0); status=json.loads(output.getvalue()); self.assertEqual(status["production_tasks"][0]["task_id"],"FAME-0001"); self.assertEqual(subprocess.run(["git","status","--porcelain"],cwd=root,text=True,capture_output=True,check=True).stdout,"")
 def test_production_doctor_requires_verification_commands(self):
  with tempfile.TemporaryDirectory() as d, patch("fame_agent_os.cli.project_root",return_value=Path(d)):
   root=Path(d);(root/".git").mkdir();initialize(root,True);self.assertEqual(main(["doctor"]),2)
