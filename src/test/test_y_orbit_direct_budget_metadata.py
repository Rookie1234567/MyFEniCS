"""Stdlib-only X research budget/provenance/timing contracts; no FE imports."""
from pathlib import Path
import ast
import copy
import importlib.util
import json
import math
import os
import subprocess
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]/"repo" if ROOT.name in {"y_orbit_direct_budget_staging", "y_orbit_direct_memory_staging"} else ROOT
BASE = "1ba6e1209a0d360c1ff9c231632b36c26d5fed10"

def module(name):
    path = ROOT/"benchmarks"/(name+".py")
    spec = importlib.util.spec_from_file_location("_budget_test_"+name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

runner = module("run_y_orbit_quotient_probe")
checker = module("check_y_orbit_direct_probe")

def fixtures():
    source = ast.parse((REPO/"src/test/test_y_orbit_direct_pipeline_metadata.py").read_text())
    names = {"profile", "report", "artifacts", "provenance", "events"}
    scope = {"checker": checker, "copy": copy}
    exec(compile(ast.Module(body=[n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), "<pure metadata fixtures>", "exec"),scope)
    return scope

def memory_envelope():
    required = 2*1024**3 + runner.RESERVE_BYTES
    return {"launch_cap_bytes": required, "effective_available_bytes": required + 4*1024**3,
        "effective_total_bytes": 16*1024**3, "reserve_bytes": 4*1024**3,
        "cgroup_limits": [{"path": "/sys/fs/cgroup", "limit_bytes": 16*1024**3, "current_bytes": 1024**3}]}

def supervised_metadata(source, *, cap=2*1024**3, seconds=1795.5):
    envelope = memory_envelope()
    return {"classification": "COMPLETED", "leader_exit_code": 0, "source_state": copy.deepcopy(source),
        "sampled_process_tree_swap_peak_bytes": 0, "descendants_cleared": True,
        "process_tree_all_status_readable": True, "process_tree_all_identity_complete": True,
        "sampled_process_tree_rss_peak_bytes": 1800*1024**2, "elapsed_seconds": 1700.,
        "global_swap_activity": {"delta": {"pswpin_pages": 0, "pswpout_pages": 0}},
        "time_reference_seconds": {"workflow": seconds},
        "launch_envelope": {**envelope, "dynamic_launch_cap_bytes": envelope["launch_cap_bytes"],
            "launch_cap_bytes": cap, "tree_cap_bytes": cap,
            "cap_policy": "min(dynamic_memory_envelope, explicit_tree_cap)"}}

class DirectBudgetTests(unittest.TestCase):
    def test_only_explicit_X_1800_and_default600(self):
        for profile in (None,"X","XZ","Y","same80"):
            self.assertEqual(runner.research_wall_budget(profile),600)
        self.assertEqual(runner.research_wall_budget("X",1800),1800)
        for profile, seconds in [(p,1800) for p in (None,"XZ","Y","same80",True)]+[("X",v) for v in (600,1801,0,True,1800.,"1800")]:
            with self.assertRaises(ValueError): runner.research_wall_budget(profile,seconds)

    def test_supervisor_environment_binds_remaining_phase(self):
        env = runner.research_watchdog_environment(1800,1720.25)["worker_environment"]
        self.assertEqual(runner.research_phase_budget("X",1800,env),1720.25)
        self.assertEqual(runner.research_watchdog_environment(None,599),{})
        self.assertEqual(runner.research_phase_budget(None,None,{}),600)
        for key,bad in (("QUOTIENT_RESEARCH_WALL_SECONDS","600"),("QUOTIENT_PHASE_WALL_SECONDS","nan"),
                        ("QUOTIENT_PHASE_WALL_SECONDS","inf"),("QUOTIENT_PHASE_WALL_SECONDS","0"),
                        ("QUOTIENT_PHASE_WALL_SECONDS","1801")):
            changed=dict(env);changed[key]=bad
            with self.assertRaises(ValueError): runner.research_phase_budget("X",1800,changed)
        for key in env:
            changed=dict(env);del changed[key]
            with self.assertRaises(ValueError): runner.research_phase_budget("X",1800,changed)

    def test_default_plan_is_exact_historical_metadata(self):
        old = subprocess.run(["git","-C",str(REPO),"show",BASE+":benchmarks/run_y_orbit_quotient_probe.py"],check=True,capture_output=True,text=True).stdout
        tree=ast.parse(old);scope={"Path":Path,"__file__":str(REPO/"benchmarks/run_y_orbit_quotient_probe.py")}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.Assign) or isinstance(n,ast.FunctionDef) and n.name=="plan_metadata"],type_ignores=[]),"<baseline metadata>","exec"),scope)
        for stage in ("prefactor","solve"):
            for shared,profile in ((False,None),(True,None),(True,"X")):
                self.assertEqual(runner.plan_metadata(stage,shared_transforms=shared,direct_profile=profile),scope["plan_metadata"](stage,shared_transforms=shared,direct_profile=profile))
        result=runner.plan_metadata("solve",direct_profile="X",research_wall_seconds=1800)
        self.assertEqual(result["wall_seconds"],1800)
        self.assertEqual((result["tree_cap_bytes"],result["swap_bytes"],result["mpi"],result["math_threads"]),(3*1024**3//2,0,1,1))

    def test_plan_cli_and_invalid_nonX_request(self):
        script=ROOT/"benchmarks/run_y_orbit_quotient_probe.py"
        command=[sys.executable,str(script),"--research-wall-seconds","1800"]
        rejected=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(rejected.returncode,2)
        accepted=subprocess.run(command+["--direct-profile","X","--stage","solve"],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(accepted.stdout)["wall_seconds"],1800)
        self.assertFalse(json.loads(accepted.stdout)["PDE_solved"])

    def binding(self,research=False,stage="prefactor",memory=None):
        f=fixtures();report=f["report"](stage);report["artifacts"]=f["artifacts"](report,stage);prior=f["provenance"](report)
        if research:
            prior["command"] += ["--research-wall-seconds","1800"]
            prior["resource_contract"].update(wall_seconds=1800,research_wall_seconds=1800,worker_phase_wall_seconds=1795.5)
        kwargs={"checker_source":report["source"],"checker_environment":report["environment"],"stage":stage}
        if research:kwargs["research_wall_seconds"]=1800
        if memory is not None:
            prior["command"] += ["--research-memory-gib",str(memory)]
            prior["resource_contract"].update(tree_cap_bytes=2*1024**3,research_memory_gib=memory,
                requested_tree_cap_bytes=2*1024**3,
                research_memory_launch_admission=runner.validate_research_memory_launch(memory_envelope(),memory))
            kwargs["research_memory_gib"]=memory
        return report,prior,kwargs

    def test_exact_worker_argv_provenance_checker_request(self):
        for research in (False,True):
            report,prior,kwargs=self.binding(research)
            self.assertTrue(checker.validate_metadata_bindings(report,prior,report["artifacts"],**kwargs))
        report,prior,kwargs=self.binding(True)
        default=dict(kwargs);del default["research_wall_seconds"]
        with self.assertRaises(ValueError): checker.validate_metadata_bindings(report,prior,report["artifacts"],**default)
        for field,bad in (("wall_seconds",600),("research_wall_seconds",600),("worker_phase_wall_seconds",0),
                          ("worker_phase_wall_seconds",1801),("worker_phase_wall_seconds",float("nan")),("swap_bytes",1),
                          ("mpi",2),("math_threads",2),("evidence_reserve_bytes",1)):
            changed=copy.deepcopy(prior);changed["resource_contract"][field]=bad
            with self.assertRaises(ValueError): checker.validate_metadata_bindings(report,changed,report["artifacts"],**kwargs)
        for command in (["run.py","--direct-profile","X"],prior["command"]+["--research-wall-seconds","1800"],
                        ["run.py","--direct-profile","X","--research-wall-seconds","600"]):
            changed=copy.deepcopy(prior);changed["command"]=command
            with self.assertRaises(ValueError): checker.validate_metadata_bindings(report,changed,report["artifacts"],**kwargs)

    def test_actual_watchdog_phase_allocation_timing_join(self):
        report,prior,kwargs=self.binding(True)
        supervision={"time_reference_seconds":{"workflow":1795.5}}
        phase={"research_wall_seconds":1800,"phase_wall_seconds":1795.5,"worker_elapsed_seconds":1700.}
        events=[{"event":"allocation_admission","research_wall_seconds":1800,"phase_wall_seconds":1795.5,"worker_elapsed_seconds":100.}]
        self.assertTrue(checker.validate_research_timing(prior,supervision,events,phase,research_wall_seconds=1800))
        for target,key,bad in (("phase","phase_wall_seconds",1800),("phase","worker_elapsed_seconds",1795.5),
                              ("event","research_wall_seconds",600),("event","worker_elapsed_seconds",float("inf")),
                              ("event","phase_wall_seconds",1795.4)):
            p=copy.deepcopy(phase);e=copy.deepcopy(events)
            (p if target=="phase" else e[0])[key]=bad
            with self.assertRaises(ValueError): checker.validate_research_timing(prior,supervision,e,p,research_wall_seconds=1800)
        with self.assertRaises(ValueError): checker.validate_research_timing(prior,supervision,[],phase,research_wall_seconds=1800)
        bad=copy.deepcopy(supervision);bad["time_reference_seconds"]["workflow"]=1800
        with self.assertRaises(ValueError): checker.validate_research_timing(prior,bad,events,phase,research_wall_seconds=1800)

    def test_carrier_receipt_default_exact_and_selected1800(self):
        path=ROOT/"src/solvers/y_orbit_direct_carrier_qualification.py"
        fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="_resource_authority")
        scope={};exec(compile(ast.Module(body=[fn],type_ignores=[]),"<carrier resource metadata>","exec"),scope)
        old="external min(fresh dynamic cap,1.5GiB)/600s/zeroSwap/MPI1/thread1 supervision"
        self.assertEqual(scope["_resource_authority"]({}),old)
        self.assertEqual(scope["_resource_authority"]({"QUOTIENT_RESEARCH_WALL_SECONDS":"1800","QUOTIENT_PHASE_WALL_SECONDS":"1700"}),old.replace("/600s/","/1800s/"))
        for env in ({"QUOTIENT_RESEARCH_WALL_SECONDS":"600"},{"QUOTIENT_RESEARCH_WALL_SECONDS":"1800"},
                    {"QUOTIENT_RESEARCH_WALL_SECONDS":"1800","QUOTIENT_PHASE_WALL_SECONDS":"1801"}):
            with self.assertRaises(ValueError):scope["_resource_authority"](env)

    def test_budget_forwarding_and_allocation_clocks_in_source(self):
        for name in ("run_y_orbit_quotient_probe","check_y_orbit_quotient_probe"):
            tree=ast.parse((ROOT/"benchmarks"/(name+".py")).read_text());text=ast.unparse(tree)
            self.assertIn("--research-wall-seconds",text)
            self.assertIn("phase_seconds",text)
            self.assertIn("research_phase_budget",text)
            self.assertIn("checker_elapsed_seconds" if name.startswith("check") else "worker_elapsed_seconds",text)
        main=next(n for n in ast.parse((ROOT/"benchmarks/run_y_orbit_quotient_probe.py").read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="main")
        calls=[n for n in ast.walk(main) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="supervise"]
        self.assertEqual(len(calls),2)
        for call in calls:
            self.assertTrue(any(k.arg is None and isinstance(k.value,ast.Call) and getattr(k.value.func,"id",None)=="research_watchdog_environment" for k in call.keywords))
        self.assertEqual((runner.TREE_CAP_BYTES,runner.RESERVE_BYTES,runner.FACTOR_ALLOWANCE_BYTES),(3*1024**3//2,128*1024**2,512*1024**2))

    def test_only_literal2_X_solve_wall1800_and_default_cap(self):
        for profile in (None,"X","XZ","Y",True):
            for stage in ("prefactor","solve"):
                for wall in (None,600,1800):
                    self.assertEqual(runner.research_memory_budget(profile,stage,wall),runner.TREE_CAP_BYTES)
                    self.assertEqual(checker.direct_memory_cap(profile,stage,wall),checker.TREE_CAP_BYTES)
        self.assertEqual(runner.research_memory_budget("X","solve",1800,2),2*1024**3)
        self.assertEqual(checker.direct_memory_cap("X","solve",1800,2),2*1024**3)
        invalid = [(p,"solve",1800,2) for p in (None,"XZ","Y",True,"same80")]
        invalid += [("X","prefactor",1800,2)]
        invalid += [("X","solve",w,2) for w in (None,600,True,1800.,"1800")]
        invalid += [("X","solve",1800,v) for v in (0,1,3,True,2.,"2")]
        for args in invalid:
            for validate in (runner.research_memory_budget,checker.direct_memory_cap):
                with self.subTest(args=args,validate=validate.__name__), self.assertRaises(ValueError): validate(*args)

    def test_memory_plan_cli_has_no_run_and_rejects_other_routes(self):
        script=ROOT/"benchmarks/run_y_orbit_quotient_probe.py"
        command=[sys.executable,str(script),"--direct-profile","X","--stage","solve",
            "--research-wall-seconds","1800","--research-memory-gib","2"]
        plan=json.loads(subprocess.run(command,check=True,capture_output=True,text=True).stdout)
        self.assertEqual((plan["tree_cap_bytes"],plan["wall_seconds"],plan["PDE_solved"]),(2*1024**3,1800,False))
        for tail in (["--research-memory-gib","2"],
                     ["--direct-profile","X","--research-wall-seconds","1800","--research-memory-gib","2"],
                     ["--direct-profile","X","--stage","solve","--research-memory-gib","2"],
                     ["--direct-profile","X","--stage","solve","--research-wall-seconds","600","--research-memory-gib","2"],
                     ["--direct-profile","XZ","--stage","solve","--research-wall-seconds","1800","--research-memory-gib","2"],
                     ["--direct-profile","X","--stage","solve","--research-wall-seconds","1800","--research-memory-gib","3"]):
            self.assertEqual(subprocess.run([sys.executable,str(script),*tail],capture_output=True,text=True).returncode,2)

    def test_fresh_launch_envelope_host_dynamic_and_each_cgroup(self):
        env=memory_envelope();admission=runner.validate_research_memory_launch(env,2)
        self.assertTrue(checker.validate_direct_memory_admission(admission))
        self.assertIsNone(runner.validate_research_memory_launch({},None))
        required=2*1024**3+runner.RESERVE_BYTES
        for key in ("launch_cap_bytes","effective_available_bytes","effective_total_bytes"):
            for value in (required-1,0,True,2.,float("nan"),float("inf"),None):
                changed=copy.deepcopy(env);changed[key]=value
                with self.subTest(key=key,value=value):
                    with self.assertRaises((ValueError,MemoryError)):runner.validate_research_memory_launch(changed,2)
                    with self.assertRaises(ValueError):checker.validate_direct_memory_launch(changed)
        for groups in (None,[{"limit_bytes":required,"current_bytes":1}],
                       [{"limit_bytes":required,"current_bytes":-1}],
                       [{"limit_bytes":float("inf"),"current_bytes":0}],
                       [{"limit_bytes":required,"current_bytes":False}]):
            changed=copy.deepcopy(env);changed["cgroup_limits"]=groups
            with self.assertRaises((ValueError,MemoryError)):runner.validate_research_memory_launch(changed,2)
            with self.assertRaises(ValueError):checker.validate_direct_memory_launch(changed)
        for key,value in (("requested_memory_gib",2.),("requested_tree_cap_bytes",runner.TREE_CAP_BYTES),
                          ("required_cap_plus_evidence_reserve_bytes",2*1024**3),("launch_admission_passed",False)):
            changed=copy.deepcopy(admission);changed[key]=value
            with self.assertRaises(ValueError):checker.validate_direct_memory_admission(changed)
        changed=copy.deepcopy(admission);changed["unexpected"]=True
        with self.assertRaises(ValueError):checker.validate_direct_memory_admission(changed)

    def test_child_memory_environment_and_launch_receipt_exact(self):
        admission=runner.validate_research_memory_launch(memory_envelope(),2)
        env=runner.research_watchdog_environment(1800,1795.5,2,admission)["worker_environment"]
        self.assertEqual(runner.research_memory_child_budget("X","solve",1800,2,env,2*1024**3),(2*1024**3,admission))
        self.assertEqual(runner.research_memory_child_budget(None,"prefactor",None,None,{},runner.TREE_CAP_BYTES),(runner.TREE_CAP_BYTES,None))
        memory_keys=[key for key in env if key.startswith("QUOTIENT_RESEARCH_MEMORY") or key=="QUOTIENT_RESEARCH_TREE_CAP_BYTES"]
        self.assertEqual(len(memory_keys),5)
        for key in memory_keys:
            for mutation in ("missing","changed"):
                changed=dict(env)
                if mutation=="missing":del changed[key]
                else:changed[key]="null" if key.endswith("ADMISSION") else "invalid"
                with self.subTest(key=key,mutation=mutation), self.assertRaises(ValueError):
                    runner.research_memory_child_budget("X","solve",1800,2,changed,2*1024**3)
            with self.assertRaises(ValueError):
                runner.research_memory_child_budget("X","solve",1800,None,{key:env[key]},runner.TREE_CAP_BYTES)
        for cap in (runner.TREE_CAP_BYTES,0,True,float(2*1024**3),2*1024**3+1):
            with self.assertRaises(ValueError):runner.research_memory_child_budget("X","solve",1800,2,env,cap)
        for key,value in (("requested_memory_gib",1),("requested_tree_cap_bytes",runner.TREE_CAP_BYTES),
                          ("required_cap_plus_evidence_reserve_bytes",2*1024**3),("launch_admission_passed",False),
                          ("unexpected",True)):
            changed=copy.deepcopy(admission);changed[key]=value
            changed_env=dict(env);changed_env["QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION"]=json.dumps(changed)
            with self.assertRaises(ValueError):runner.research_memory_child_budget("X","solve",1800,2,changed_env,2*1024**3)
        with self.assertRaises(ValueError):runner.research_watchdog_environment(None,599,2,admission)

    def test_explicit2_metadata_bindings_and_default_rejection(self):
        report,prior,kwargs=self.binding(True,"solve",2)
        self.assertTrue(checker.validate_metadata_bindings(report,prior,report["artifacts"],**kwargs))
        for request in (None,True,2.,"2",1,3):
            changed=dict(kwargs);changed["research_memory_gib"]=request
            with self.assertRaises(ValueError):checker.validate_metadata_bindings(report,prior,report["artifacts"],**changed)
        for field,value in (("tree_cap_bytes",runner.TREE_CAP_BYTES),("tree_cap_bytes",2*1024**3+1),
                            ("research_memory_gib",2.),("requested_tree_cap_bytes",runner.TREE_CAP_BYTES),
                            ("research_memory_launch_admission",None),("wall_seconds",600),("mpi",2),("swap_bytes",1)):
            changed=copy.deepcopy(prior);changed["resource_contract"][field]=value
            with self.assertRaises(ValueError):checker.validate_metadata_bindings(report,changed,report["artifacts"],**kwargs)
        for command in (prior["command"][:-2],prior["command"]+["--research-memory-gib","2"],
                        prior["command"][:-1]+["1"],prior["command"][:-1]):
            changed=copy.deepcopy(prior);changed["command"]=command
            with self.assertRaises(ValueError):checker.validate_metadata_bindings(report,changed,report["artifacts"],**kwargs)
        ordinary,default,plain=self.binding(True,"solve")
        default["resource_contract"]["tree_cap_bytes"]=2*1024**3
        with self.assertRaises(ValueError):checker.validate_metadata_bindings(ordinary,default,ordinary["artifacts"],**plain)

    def test_explicit2_supervision_retains_every_source_swap_time_gate(self):
        report,_,_=self.binding(True,"solve",2);summary=supervised_metadata(report["source"])
        kwargs={"maximum_wall":1795.5,"direct_profile":"X","stage":"solve","research_wall_seconds":1800,"research_memory_gib":2}
        self.assertTrue(checker.validate_direct_supervision(summary,report["source"],**kwargs))
        for field,value in (("classification","WORKER_FAILED"),("leader_exit_code",1),("source_state",{}),
                            ("sampled_process_tree_swap_peak_bytes",1),("descendants_cleared",False),
                            ("process_tree_all_status_readable",False),("process_tree_all_identity_complete",False),
                            ("sampled_process_tree_rss_peak_bytes",2*1024**3),("sampled_process_tree_rss_peak_bytes",0),
                            ("elapsed_seconds",1795.5),("elapsed_seconds",float("inf"))):
            changed=copy.deepcopy(summary);changed[field]=value
            with self.assertRaises(ValueError):checker.validate_direct_supervision(changed,report["source"],**kwargs)
        for field,value in (("launch_cap_bytes",runner.TREE_CAP_BYTES),("tree_cap_bytes",runner.TREE_CAP_BYTES),
                            ("launch_cap_bytes",2*1024**3+1),("dynamic_launch_cap_bytes",2*1024**3),
                            ("cap_policy","dynamic_only"),("cgroup_limits",[{"limit_bytes":2*1024**3,"current_bytes":1}])):
            changed=copy.deepcopy(summary);changed["launch_envelope"][field]=value
            with self.assertRaises(ValueError):checker.validate_direct_supervision(changed,report["source"],**kwargs)
        for key in ("pswpin_pages","pswpout_pages"):
            changed=copy.deepcopy(summary);changed["global_swap_activity"]["delta"][key]=1
            with self.assertRaises(ValueError):checker.validate_direct_supervision(changed,report["source"],**kwargs)

    def test_default_supervision_calls_unchanged_authority(self):
        tree=ast.parse((REPO/"benchmarks/y_orbit_two_cell_authority.py").read_text())
        fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="validate_supervision")
        old=subprocess.run(["git","-C",str(REPO),"show","5758f5e7a04d5ef15ddbc21369e0663b01edd860:benchmarks/y_orbit_two_cell_authority.py"],
            check=True,capture_output=True,text=True).stdout
        baseline=next(node for node in ast.parse(old).body if isinstance(node,ast.FunctionDef) and node.name=="validate_supervision")
        self.assertEqual(ast.dump(fn),ast.dump(baseline))
        inherited_guard=next(node for node in baseline.body if isinstance(node,ast.If))
        direct_tree=ast.parse((ROOT/"benchmarks/check_y_orbit_direct_probe.py").read_text())
        direct_fn=next(node for node in direct_tree.body if isinstance(node,ast.FunctionDef) and node.name=="validate_direct_supervision")
        selected_guard=next(node for node in direct_fn.body if isinstance(node,ast.If) and isinstance(node.test,ast.BoolOp))
        class SelectedCap(ast.NodeTransformer):
            def visit_Name(self,node):
                if node.id=="TREE_CAP_BYTES":return ast.copy_location(ast.Name(id="selected_cap",ctx=node.ctx),node)
                return node
        self.assertEqual(ast.dump(SelectedCap().visit(copy.deepcopy(inherited_guard))),ast.dump(selected_guard))
        scope={"TREE_CAP_BYTES":runner.TREE_CAP_BYTES}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),"<unchanged stdlib authority validator>","exec"),scope)
        module=ModuleType("benchmarks.y_orbit_two_cell_authority");calls=[]
        def inherited(*args,**kwargs):
            calls.append((args,kwargs));return scope["validate_supervision"](*args,**kwargs)
        module.validate_supervision=inherited
        report,_,_=self.binding();summary=supervised_metadata(report["source"],cap=runner.TREE_CAP_BYTES,seconds=600)
        summary["sampled_process_tree_rss_peak_bytes"]=10**6;summary["elapsed_seconds"]=599.
        with patch.dict(sys.modules,{"benchmarks.y_orbit_two_cell_authority":module}):
            self.assertTrue(checker.validate_direct_supervision(summary,report["source"]))
            self.assertEqual(calls,[((summary,report["source"]),{"maximum_wall":600})])
            summary["sampled_process_tree_rss_peak_bytes"]=runner.TREE_CAP_BYTES
            with self.assertRaises(ValueError):checker.validate_direct_supervision(summary,report["source"])

    def memory_packets(self):
        report,prior,_=self.binding(True,"solve",2)
        events=fixtures()["events"](report,"solve")
        phase={"research_memory_gib":2,"requested_tree_cap_bytes":2*1024**3}
        for event in events:
            if event["event"]=="allocation_admission":
                event.update(phase,launch_cap_bytes=2*1024**3,effective_tree_cap_bytes=2*1024**3,
                    fresh_memory_envelope=memory_envelope())
        summary=supervised_metadata(report["source"])
        kwargs={"direct_profile":"X","stage":"solve","research_wall_seconds":1800,"research_memory_gib":2}
        return report,prior,summary,events,phase,kwargs

    def test_worker_phase_allocation_and_factor_gates_bind_selected_cap(self):
        report,prior,summary,events,phase,kwargs=self.memory_packets()
        self.assertTrue(checker.validate_research_memory_resources(prior,summary,events,phase,**kwargs))
        self.assertTrue(checker.validate_direct_event_contract(events,report,"solve",research_wall_seconds=1800,research_memory_gib=2))
        for key,value in (("research_memory_gib",None),("research_memory_gib",2.),("requested_tree_cap_bytes",runner.TREE_CAP_BYTES),
                          ("launch_cap_bytes",runner.TREE_CAP_BYTES),("effective_tree_cap_bytes",2*1024**3+1),
                          ("effective_tree_cap_bytes",runner.TREE_CAP_BYTES),("projected_tree_bytes",0),("admitted",False),
                          ("evidence_reserve_bytes",1),("fresh_memory_envelope",{})):
            changed=copy.deepcopy(events);changed[4][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):checker.validate_research_memory_resources(prior,summary,changed,phase,**kwargs)
        for key,value in (("research_memory_gib",1),("requested_tree_cap_bytes",runner.TREE_CAP_BYTES)):
            changed=copy.deepcopy(phase);changed[key]=value
            with self.assertRaises(ValueError):checker.validate_research_memory_resources(prior,summary,events,changed,**kwargs)
        with self.assertRaises(ValueError):checker.validate_research_memory_resources(prior,summary,[],phase,**kwargs)
        with self.assertRaises(ValueError):checker.validate_direct_event_contract(events,report,"solve")
        # A real strict projection can pass above the old cap, only with opt-in2.
        changed=copy.deepcopy(events)
        for event in changed:
            if event["event"]=="allocation_admission":
                event["current_tree_rss_bytes"]=runner.TREE_CAP_BYTES
                event["projected_tree_bytes"]=sum(event[k] for k in ("current_tree_rss_bytes","additional_payload_bytes",
                    "declared_workspace_bytes","remaining_factor_allowance_bytes","evidence_reserve_bytes"))
        # The first two factors also retain512/384MiB allowance plus128MiB reserve.
        for index,reduction in ((4,256*1024**2),(7,128*1024**2)):
            changed[index]["current_tree_rss_bytes"]-=reduction
            changed[index]["projected_tree_bytes"]-=reduction
        self.assertTrue(checker.validate_direct_event_contract(changed,report,"solve",research_wall_seconds=1800,research_memory_gib=2))
        with self.assertRaises(ValueError):checker.validate_direct_event_contract(changed,report,"solve")

    def test_fresh_carrier_2GiB_text_requires_bound_environment(self):
        tree=ast.parse((ROOT/"src/solvers/y_orbit_direct_carrier_qualification.py").read_text())
        fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="_resource_authority")
        scope={"json":json};exec(compile(ast.Module(body=[fn],type_ignores=[]),"<stdlib fresh resource receipt>","exec"),scope)
        admission=runner.validate_research_memory_launch(memory_envelope(),2)
        env=runner.research_watchdog_environment(1800,1795.5,2,admission)["worker_environment"]
        env["PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES"]=str(2*1024**3)
        expected="external min(fresh dynamic cap,2GiB)/1800s/zeroSwap/MPI1/thread1 supervision"
        self.assertEqual(scope["_resource_authority"](env),expected)
        for key,value in (("QUOTIENT_RESEARCH_MEMORY_GIB","1"),("QUOTIENT_RESEARCH_MEMORY_PROFILE","XZ"),
                          ("QUOTIENT_RESEARCH_MEMORY_STAGE","prefactor"),("QUOTIENT_RESEARCH_WALL_SECONDS","600"),
                          ("QUOTIENT_PHASE_WALL_SECONDS","nan"),("QUOTIENT_PHASE_WALL_SECONDS","1801"),
                          ("QUOTIENT_RESEARCH_TREE_CAP_BYTES",str(runner.TREE_CAP_BYTES)),
                          ("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES",str(runner.TREE_CAP_BYTES)),
                          ("QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION","null")):
            changed=dict(env);changed[key]=value
            with self.assertRaises(ValueError):scope["_resource_authority"](changed)
        for key in ("QUOTIENT_RESEARCH_MEMORY_PROFILE","QUOTIENT_RESEARCH_MEMORY_STAGE",
                    "QUOTIENT_RESEARCH_TREE_CAP_BYTES","QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION",
                    "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES"):
            changed=dict(env);del changed[key]
            with self.assertRaises(ValueError):scope["_resource_authority"](changed)
        old=subprocess.run(["git","-C",str(REPO),"show","5758f5e7a04d5ef15ddbc21369e0663b01edd860:src/solvers/y_orbit_direct_carrier_qualification.py"],
            check=True,capture_output=True,text=True).stdout
        previous=next(node for node in ast.parse(old).body if isinstance(node,ast.FunctionDef) and node.name=="_resource_authority")
        inherited=next(node for node in fn.body if isinstance(node,ast.If) and ast.unparse(node.test)=="memory is None")
        def undocument(body):return [node for node in body if not (isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str))]
        self.assertEqual(ast.dump(ast.Module(body=undocument(previous.body),type_ignores=[])),
            ast.dump(ast.Module(body=inherited.body,type_ignores=[])))

    def test_memory_forwarding_packet_and_default_source_seams(self):
        direct=ast.parse((ROOT/"benchmarks/check_y_orbit_direct_probe.py").read_text())
        helper=next(node for node in direct.body if isinstance(node,ast.FunctionDef) and node.name=="validate_direct_supervision")
        default=next(node for node in helper.body if isinstance(node,ast.If))
        self.assertEqual(ast.unparse(default.test),"research_memory_gib is None")
        self.assertEqual(ast.unparse(default.body[-1]),"return validate_supervision(summary, source, maximum_wall=maximum_wall)")
        for name in ("run_y_orbit_quotient_probe","check_y_orbit_quotient_probe"):
            source=ast.unparse(ast.parse((ROOT/"benchmarks"/(name+".py")).read_text()))
            self.assertIn("--research-memory-gib",source)
            self.assertIn("research_memory_child_budget",source)
            self.assertIn("requested_tree_cap_bytes",source)
            self.assertIn("research_memory_gib",source)
        function=next(node for node in direct.body if isinstance(node,ast.FunctionDef) and node.name=="check_direct")
        source=ast.unparse(function)
        self.assertNotIn("< TREE_CAP_BYTES",source)
        self.assertIn("< selected_cap",source)
        self.assertIn("validate_research_memory_resources",source)
        self.assertIn("validate_direct_supervision",source)
        for suffix in ("*.npy","*.npz"):
            self.assertFalse(list((ROOT/"src").rglob(suffix)))
            self.assertFalse([path for path in (ROOT/"benchmarks").rglob(suffix)
                if path.relative_to(ROOT/"benchmarks").parts[0]!="artifacts"])

if __name__ == "__main__": unittest.main(verbosity=2)
