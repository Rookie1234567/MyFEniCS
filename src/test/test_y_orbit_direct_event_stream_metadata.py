"""Stdlib-only bounded JSONL and pinned checker source metadata regressions."""
from pathlib import Path
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]/"repo" if ROOT.name in ("y_orbit_direct_event_stream_staging", "direct_X_source_role_staging", "direct_X_residual_binding_staging") else ROOT
BASE = "816b7247c8359a7affbd450365de5bbb86de367a"
WORKER_MANIFEST_SHA = "b17eac7ff5e937688ae8f7ed05a26327942637f326e6401027277f88f55030d2"
DIRECT = "benchmarks/check_y_orbit_direct_probe.py"
GENERIC = "benchmarks/check_y_orbit_quotient_probe.py"
TEST = "src/test/test_y_orbit_direct_event_stream_metadata.py"
PINNED_CHECKERS = {DIRECT: "ef0bd44c7fcc1ba852fc00e8a74b7851d62cba4f231bbb773681585d98b61d55",
    GENERIC: "77b4090ebf4395b1e8f37b72def54fde05f4dc09ef466395898b5c2ef0f0c42a"}


def module(name):
    path = ROOT/"benchmarks"/(name+".py")
    if not path.is_file(): path = REPO/"benchmarks"/(name+".py")
    spec = importlib.util.spec_from_file_location("_event_stream_test_"+name,path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


checker = module("check_y_orbit_direct_probe")
generic = module("check_y_orbit_quotient_probe")


def fixture_scope():
    source = ast.parse((REPO/"src/test/test_y_orbit_direct_pipeline_metadata.py").read_text())
    names = {"profile","report","artifacts","provenance","events"}
    scope = {"checker":checker,"copy":copy}
    exec(compile(ast.Module(body=[node for node in source.body if isinstance(node,ast.FunctionDef)
        and node.name in names],type_ignores=[]),"<unchanged stdlib direct fixtures>","exec"),scope)
    return scope


def baseline_inventory():
    """Hash tracked source blobs at the pinned commit in bounded byte panels."""
    listing = subprocess.run(["git","-C",str(REPO),"ls-tree","-r","-z",BASE,"--","src","benchmarks",
        "input/task40extra_0p7nm_engineering"],check=True,capture_output=True).stdout
    entries = [record.split(b"\t",1) for record in listing.split(b"\0") if record]
    files = {}
    with subprocess.Popen(["git","-C",str(REPO),"cat-file","--batch"],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
        for metadata,path_bytes in entries:
            mode,kind,object_id = metadata.split()
            path = path_bytes.decode()
            if kind != b"blob" or mode not in (b"100644",b"100755"):
                raise AssertionError("the pinned source inventory must consist of regular tracked files")
            if Path(path).suffix in {".npy",".npz"}:
                raise AssertionError("numeric saved arrays are outside these source-only tests")
            process.stdin.write(object_id+b"\n");process.stdin.flush()
            header=process.stdout.readline().split()
            if len(header)!=3 or header[:2]!=[object_id,b"blob"]:
                raise AssertionError("exact pinned source blob required")
            remaining=int(header[2]);digest=hashlib.sha256()
            while remaining:
                panel=process.stdout.read(min(remaining,1<<20))
                if not panel:raise AssertionError("source blob ended before its declared byte count")
                digest.update(panel);remaining-=len(panel)
            if process.stdout.read(1)!=b"\n":raise AssertionError("source blob boundary differs")
            files[path]=digest.hexdigest()
        process.stdin.close()
        if process.wait()!=0:raise AssertionError("pinned source blob scan failed")
    return files


def sources(inventory):
    worker={"head":BASE,"branch":"task40extra_dot_parallel_cloud","dirty":"","files_sha256":copy.deepcopy(inventory)}
    changed=copy.deepcopy(worker);changed["head"]="d"*40
    changed["files_sha256"].update({DIRECT:"a"*64,GENERIC:"b"*64,TEST:"c"*64})
    return worker,changed



class DirectContextSourceRoleTests(unittest.TestCase):
    BASE_PATHS = (
        "src/solvers/dtn_boundary_phase_gauge.py", "src/solvers/dtn_port_3d.py",
        "src/solvers/fullspace_dtn_action.py", "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
        "src/solvers/dtn_boundary_plane_qualification.py", "src/common/modes_3d.py", "src/common/config_3d.py")
    EXTRA_PATHS = (
        "src/solvers/y_orbit_quotient_context.py", "src/solvers/fullspace_same_mesh_hcurl_pmg_global.py",
        "src/solvers/y_orbit_condensed_adapter.py", "src/constraints/floquet_3d.py",
        "src/constraints/floquet_3d_high_order.py", "src/constraints/high_order_floquet_trace.py")

    def fixture(self, root, role):
        paths = self.BASE_PATHS+(self.EXTRA_PATHS if role != "full" else ())
        inventory={}
        for relative in paths:
            path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text("exact bound source "+relative)
            inventory[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
        context={"source_sha256":{Path(path).name:digest for path,digest in inventory.items()}}
        if role != "full":
            twist=int(role[-1])
            contract={"schema":"task40extra.y-orbit-two-cell-context.research.v1","twist_index":twist,
                "direct_profile":"X","physical_generator_manifest_sha256":checker.PHYSICAL_MANIFEST,
                "global_y_cells":4,"local_y_cells":2,"global_q_indices":[twist,twist+2],
                "global_mode_count":532,"sector_mode_count":checker.SECTOR_PORTS[twist],"replication_count":2}
            context["y_orbit_quotient"]={"contract":contract,"contract_sha256":checker.digest_json(contract),
                "actual_local_cells":60,"actual_local_storage_rows":13236,
                "twist_requires_global_dual_rhs_transport":True}
        return context,{"files_sha256":inventory}

    def test_complete7_and13_actual_sources_match_immutable_worker(self):
        for role,count in (("full",7),("twist_0",13),("twist_1",13)):
            with self.subTest(role=role),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);context,worker=self.fixture(root,role)
                checked=checker.validate_context_source_role(role,context,worker,source_root=root)
                self.assertEqual(len(checked),count)
                self.assertEqual({name:v["sha256"] for name,v in checked.items()},context["source_sha256"])
                self.assertTrue(all(Path(item["path"]).is_file() for item in checked.values()))

    def test_unknown_missing_extra_swapped_roles_and_contracts_stop(self):
        for role in ("full","twist_0","twist_1"):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);context,worker=self.fixture(root,role)
                for mutation in ("unknown","missing","extra","swapped","quotient_presence","contract_hash","twist"):
                    bad=copy.deepcopy(context);actual_role=role
                    if mutation=="unknown":actual_role="twist_2"
                    elif mutation=="missing":bad["source_sha256"].pop("dtn_port_3d.py")
                    elif mutation=="extra":bad["source_sha256"]["unreviewed.py"]="a"*64
                    elif mutation=="swapped":actual_role="twist_0" if role=="full" else "full"
                    elif mutation=="quotient_presence":
                        if role=="full":bad["y_orbit_quotient"]={}
                        else:del bad["y_orbit_quotient"]
                    elif mutation=="contract_hash":
                        if role=="full":continue
                        bad["y_orbit_quotient"]["contract_sha256"]="a"*64
                    else:
                        if role=="full":continue
                        bad["y_orbit_quotient"]["contract"]["twist_index"]=1-int(role[-1])
                        bad["y_orbit_quotient"]["contract_sha256"]=checker.digest_json(bad["y_orbit_quotient"]["contract"])
                    with self.subTest(role=role,mutation=mutation),self.assertRaises(ValueError):
                        checker.validate_context_source_role(actual_role,bad,worker,source_root=root)

    def test_local_contract_profiles_counts_hashes_and_dual_transport_are_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);context,worker=self.fixture(root,"twist_0")
            for name,value in (("schema","other"),("twist_index",False),("direct_profile","Y"),
                ("physical_generator_manifest_sha256","a"*64),("global_y_cells",6),("local_y_cells",1),
                ("global_q_indices",[0,3]),("global_mode_count",531),("sector_mode_count",227),("replication_count",3)):
                bad=copy.deepcopy(context);bad["y_orbit_quotient"]["contract"][name]=value
                bad["y_orbit_quotient"]["contract_sha256"]=checker.digest_json(bad["y_orbit_quotient"]["contract"])
                with self.subTest(field=name),self.assertRaises(ValueError):
                    checker.validate_context_source_role("twist_0",bad,worker,source_root=root)
            for name,value in (("actual_local_cells",40),("actual_local_storage_rows",8940),
                               ("twist_requires_global_dual_rhs_transport",False)):
                bad=copy.deepcopy(context);bad["y_orbit_quotient"][name]=value
                with self.subTest(field=name),self.assertRaises(ValueError):
                    checker.validate_context_source_role("twist_0",bad,worker,source_root=root)

    def test_every_actual_context_and_worker_hash_and_file_is_required(self):
        for role in ("full","twist_0","twist_1"):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);context,worker=self.fixture(root,role)
                for path in worker["files_sha256"]:
                    name=Path(path).name
                    for mutation in ("context","worker","actual","missing","invalid"):
                        bad=copy.deepcopy(context);old=copy.deepcopy(worker);original=(root/path).read_bytes()
                        if mutation=="context":bad["source_sha256"][name]="a"*64
                        elif mutation=="worker":old["files_sha256"][path]="a"*64
                        elif mutation=="actual":(root/path).write_bytes(b"changed bound code")
                        elif mutation=="missing":(root/path).unlink()
                        else:bad["source_sha256"][name]="not-SHA256"
                        try:
                            with self.subTest(role=role,path=path,mutation=mutation),self.assertRaises(ValueError):
                                checker.validate_context_source_role(role,bad,old,source_root=root)
                        finally:(root/path).write_bytes(original)

    def test_direct_dispatch_uses_role_validator_and_preserves_numeric_helper(self):
        tree=ast.parse((ROOT/DIRECT).read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="check_direct")
        calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
            and n.func.id=="validate_context_source_role"]
        self.assertEqual(len(calls),1)
        self.assertEqual([ast.unparse(arg) for arg in calls[0].args],["role","context","worker_source"])
        self.assertNotIn("_source_binding",ast.unparse(fn))
        original=subprocess.run(["git","-C",str(REPO),"show",BASE+":src/solvers/y_orbit_quotient_raw_qualification.py"],
            check=True,capture_output=True).stdout
        actual=(REPO/"src/solvers/y_orbit_quotient_raw_qualification.py").read_bytes()
        approved_metadata_guard=b'            require(direct.name in ("X", "XZ", "Y"), "direct raw numerical qualification admits only X/XZ/Y")\n'
        self.assertEqual(actual.count(approved_metadata_guard),1)
        self.assertEqual(original,actual.replace(approved_metadata_guard,b""))



class DirectResidualRepresentationTests(unittest.TestCase):
    def test_cancellation_operand_drift_is_bound_without_tiny_residual_claim(self):
        import numpy as np
        f=np.array([1.+0j]);v=np.array([1000.+0j]);c=f-v
        old=[f,v,c];saved=f-v-c
        new=[f,v+np.array([2e-10+0j]),c];actual=f-new[1]-c
        self.assertGreater(float(np.linalg.norm(actual-saved)/np.linalg.norm(f)),1e-12)
        # These independent action and equation gates remain compulsory.
        checker.finite_gate(float(np.linalg.norm(new[1]-v)/np.linalg.norm(v)),1e-11,'volume')
        with self.assertRaises(ValueError):checker.finite_gate(float(np.linalg.norm(actual)/np.linalg.norm(f)),1e-10,'true equation')
        receipt=checker.residual_representation_binding(new,old,(1,-1,-1),actual,saved)
        self.assertTrue(receipt['saved_exact_definition']);self.assertFalse(receipt['tiny_residual_relative_precision_claimed'])
        self.assertLessEqual(receipt['residual_difference_norm'],receipt['derived_operand_plus_roundoff_bound'])

    def test_native_FE_and_port_expressions_match_exact_saved_operands(self):
        import numpy as np
        rng=np.random.default_rng(403)
        for signs in ((1,-1),(1,-1,-1),(1,-1,1)):
            terms=[rng.standard_normal(12)+1j*rng.standard_normal(12) for _ in signs]
            residual=terms[0].copy()
            for sign,a in zip(signs[1:],terms[1:]):residual=residual+a if sign==1 else residual-a
            value=checker.residual_representation_binding(terms,terms,signs,residual,residual)
            self.assertEqual(value['residual_difference_norm'],0.)
            self.assertEqual(value['difference_consistency_defect_norm'],0.)

    def test_zero_operations_require_exact_zero_not_a_floor(self):
        import numpy as np
        z=np.zeros(7,complex)
        value=checker.residual_representation_binding([z,z,z],[z,z,z],(1,-1,-1),z,z)
        self.assertEqual(value['derived_operand_plus_roundoff_bound'],0.)
        self.assertEqual(value['derived_roundoff_bound'],0.)

    def test_nonzero_norm_underflow_stops_without_floor_or_zero_certificate(self):
        import numpy as np
        tiny=np.array([1e-200+0j]);zero=np.zeros(1,complex)
        with self.assertRaisesRegex(ValueError,'underflowed to zero'):
            checker.residual_representation_binding([tiny,zero],[tiny,zero],(1,-1),tiny,tiny)

    def test_saved_or_independent_residual_tampering_is_rejected_exactly(self):
        import numpy as np
        a=np.array([1.+2j,3.-4j]);b=np.array([.1+.2j,.3-.4j]);r=a-b
        for side in ('new','saved'):
            wrong=r.copy();wrong[0]+=1e-15
            with self.subTest(side=side),self.assertRaises(ValueError):
                checker.residual_representation_binding([a,b],[a,b],(1,-1),wrong if side=='new' else r,wrong if side=='saved' else r)

    def test_nonfinite_wrong_shape_dtype_or_expression_cannot_pass(self):
        import numpy as np
        a=np.array([1.+0j,2.+0j]);b=np.array([.1+0j,.2+0j]);r=a-b
        for mutation in ('nan','inf','shape','real','wrong_sign','wrong_count'):
            terms=[a.copy(),b.copy()];signs=(1,-1)
            if mutation=='nan':terms[0][0]=complex(float('nan'),0.)
            elif mutation=='inf':terms[1][0]=complex(float('inf'),0.)
            elif mutation=='shape':terms[1]=terms[1][None,:]
            elif mutation=='real':terms[0]=terms[0].real
            elif mutation=='wrong_sign':signs=(-1,-1)
            else:signs=(1,-1,-1)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                checker.residual_representation_binding(terms,[a,b],signs,r,r)

    def test_derived_bound_follows_each_rounded_addition_and_subtraction(self):
        import numpy as np
        old=[np.array([1.+2j]),np.array([1e3+2e3j]),np.array([-999.-1998j])]
        new=[old[0].copy(),old[1]+np.array([1e-11-2e-11j]),old[2].copy()]
        r=new[0]-new[1]-new[2];rs=old[0]-old[1]-old[2]
        value=checker.residual_representation_binding(new,old,(1,-1,-1),r,rs)
        norm=lambda x:float(np.linalg.norm(x));u=np.finfo(float).eps/2;gamma=2*u/(1-2*u)
        delta=[a-b for a,b in zip(new,old)];summed=delta[0]-delta[1]-delta[2];rd=r-rs
        op=sum(norm(x) for x in new+old);d=sum(norm(x) for x in delta)
        bound=gamma*op+u*op+u*(norm(r)+norm(rs))+gamma*d+u*(norm(rd)+norm(summed))
        self.assertEqual(value['derived_roundoff_bound'],bound)
        self.assertEqual(value['derived_operand_plus_roundoff_bound'],d+bound)
        self.assertEqual(value['unit_roundoff'],u)

    def test_injected_inverse_error_still_fails_both_original_equation_gates(self):
        import numpy as np
        f=np.array([1.+0j]);v=np.array([1.000001+0j]);r=f-v
        receipt=checker.residual_representation_binding([f,v],[f,v],(1,-1),r,r)
        self.assertTrue(receipt['saved_exact_definition'])
        for value in (r,r.copy()):
            with self.assertRaises(ValueError):checker.finite_gate(float(np.linalg.norm(value)/np.linalg.norm(f)),1e-10,'true equation')

    def test_action_gate_remains_independent_of_residual_formula_binding(self):
        import numpy as np
        f=np.array([1.+0j]);old=np.array([.5+0j]);new=np.array([.5001+0j]);a=f-new;b=f-old
        checker.residual_representation_binding([f,new],[f,old],(1,-1),a,b)
        with self.assertRaises(ValueError):checker.finite_gate(float(np.linalg.norm(new-old)/np.linalg.norm(new)),1e-11,'original volume action')

    def test_caller_preserves_all_original_action_and_equation_limits(self):
        tree=ast.parse((ROOT/DIRECT).read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='check_solve')
        text=ast.unparse(fn)
        for name in ('complete_original_volume_action','complete_original_action','final_D_field_projection','final_C_alpha_coupling'):
            self.assertIn(name,text)
        for name in ('saved_original_native_true_residual','saved_augmented_FE_true_residual','saved_all532_augmented_port_closure',
                     'original_native_true_residual','augmented_FE_true_residual','all532_augmented_port_closure'):
            self.assertIn(name,text)
        calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='add']
        for suffix in ('complete_original_volume_action','complete_original_action','final_D_field_projection','final_C_alpha_coupling'):
            call=next(c for c in calls if suffix in ast.unparse(c.args[0]))
            self.assertEqual(ast.literal_eval(call.args[2]),1e-11)
        for suffix in ('saved_original_native_true_residual','saved_augmented_FE_true_residual','saved_all532_augmented_port_closure',
                       'original_native_true_residual','augmented_FE_true_residual','all532_augmented_port_closure'):
            call=next(c for c in calls if ast.unparse(c.args[0]).endswith(repr('_'+suffix)))
            self.assertEqual(ast.literal_eval(call.args[2]),1e-10)
        self.assertNotIn('relative(top - saved.load',text)
        self.assertNotIn('relative(native - saved.load',text)


class DirectEventStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory=baseline_inventory()

    def test_source_fixture_pins_full_worker_inventory_and_both_checkers(self):
        self.assertGreater(len(self.inventory),1000)
        self.assertEqual(checker.digest_json(self.inventory),WORKER_MANIFEST_SHA)
        self.assertNotIn(TEST,self.inventory)
        self.assertEqual({path:self.inventory[path] for path in PINNED_CHECKERS},PINNED_CHECKERS)

    def test_stream_preserves_all_events_nested_values_and_key_identity(self):
        records=[{"event":"unrecognized_control","shared_long_metadata_key_916b":"a long repeated value 816b",
            "nested":{"shared_deep_dictionary_key_916b":[1,{"preserved":"深层"},None,True]},"ordinal":0},
            {"event":"allocation_admission","shared_long_metadata_key_916b":"a long repeated value 816b",
            "nested":{"shared_deep_dictionary_key_916b":[2,{"preserved":"second"}]},"ordinal":1},
            {"event":"unrecognized_control","duplicate_event_kept":True,"ordinal":2}]
        raw=b"\n"+b"\n".join(json.dumps(record,ensure_ascii=False).encode() for record in records)+b"\n\n"
        calls=[]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"events.jsonl";path.write_bytes(raw)
            with patch.object(Path,"read_text",side_effect=AssertionError("event loader cannot collect file text")),\
                 patch.object(Path,"read_bytes",side_effect=AssertionError("event loader cannot collect file bytes")):
                events,receipt=checker.load_direct_events(path,lambda name,facts:calls.append((name,copy.deepcopy(facts))))
        self.assertEqual(events,records)
        self.assertIs(next(key for key in events[0] if key.startswith("shared_long")),
            next(key for key in events[1] if key.startswith("shared_long")))
        self.assertIs(next(iter(events[0]["nested"])),next(iter(events[1]["nested"])))
        self.assertTrue(calls)
        self.assertEqual(receipt,{"path":"events.jsonl","file_sha256":hashlib.sha256(raw).hexdigest(),
            "file_bytes":len(raw),"line_count":5,"blank_line_count":2,"event_count":3,
            "maximum_line_bytes":max(map(len,raw.splitlines(keepends=True))),"read_chunk_bytes":1<<20,
            "maximum_admitted_line_bytes":64<<20,"all_events_retained":True,"exact_event_order_preserved":True,
            "complete_EOF_verified":True,"same_file_hash_both_passes":True,"keys_interned_without_value_changes":True})
        parses=[facts for name,facts in calls if name=="direct_checker_event_json_line"]
        self.assertEqual([facts["event_line_number"] for facts in parses],list(range(1,6)))
        self.assertEqual([facts["retained_event_count"] for facts in parses],[0,0,1,2,3])
        self.assertTrue(all(facts["workspace_bytes"]==8*facts["event_line_bytes"]
            +16*(facts["retained_event_count"]+1)+(4<<20) for facts in parses))

    def test_admission_precedes_every_chunk_line_decode_and_list_growth(self):
        raw=b'{"event":"first","nested":{"key_816b":"ordinary value"}}\n{"event":"second"}\n'
        observations=[];open_file=Path.open;decode=json.loads;intern=sys.intern;interned=[];decoding=False
        class Reader:
            def __init__(self,stream):self.stream=stream
            def __enter__(self):self.stream.__enter__();return self
            def __exit__(self,*args):return self.stream.__exit__(*args)
            def read(self,count):
                data=self.stream.read(count);observations.append(("read",count,data));return data
            def readline(self,count):observations.append(("readline",count));return self.stream.readline(count)
        def open_tracked(path,*args,**kwargs):return Reader(open_file(path,*args,**kwargs))
        def gate(name,facts):observations.append(("gate",name,copy.deepcopy(facts)))
        def decode_tracked(*args,**kwargs):
            nonlocal decoding
            observations.append(("decode",));decoding=True
            try:return decode(*args,**kwargs)
            finally:decoding=False
        def intern_tracked(key):
            if decoding:interned.append(key)
            return intern(key)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"events.jsonl";path.write_bytes(raw)
            with patch.object(checker,"DIRECT_EVENT_CHUNK_BYTES",7),patch.object(Path,"open",open_tracked),\
                 patch.object(checker.json,"loads",decode_tracked),patch.object(sys,"intern",intern_tracked):
                events,receipt=checker.load_direct_events(path,gate)
        self.assertEqual(events,[{"event":"first","nested":{"key_816b":"ordinary value"}},{"event":"second"}])
        self.assertEqual(receipt["file_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt["line_count"],2)
        self.assertEqual(sorted(interned),sorted(["event","nested","key_816b","event"]))
        for index,entry in enumerate(observations):
            if entry[0] in {"read","readline"}:
                prior=observations[index-1]
                self.assertEqual(prior[0],"gate")
                self.assertEqual(prior[1],"direct_checker_event_json_line" if entry[0]=="readline" else
                    "direct_checker_event_full_EOF" if entry[1]==1 else "direct_checker_event_scan_chunk")
            elif entry[0]=="decode":
                self.assertEqual(observations[index-1][0],"readline")
                self.assertEqual(observations[index-2][1],"direct_checker_event_json_line")
        completed=0
        for index,entry in enumerate(observations):
            if entry[:2]==("gate","direct_checker_event_scan_chunk"):
                self.assertEqual(entry[2]["workspace_bytes"],2*7+(4<<20))
            elif entry[:2]==("gate","direct_checker_event_line_inventory"):
                count=observations[index-1][2].count(b"\n")
                self.assertEqual(entry[2]["workspace_bytes"],16*(completed+count+1)+64*(count+1)+2*7+(4<<20))
                completed+=count
        fn=next(node for node in ast.parse((ROOT/DIRECT).read_text()).body if isinstance(node,ast.FunctionDef) and node.name=="load_direct_events")
        loops=[node for node in ast.walk(fn) if isinstance(node,(ast.For,ast.While))]
        append=next(node for node in loops if any(isinstance(child,ast.Call) and isinstance(child.func,ast.Attribute)
            and isinstance(child.func.value,ast.Name) and child.func.value.id=="lengths" and child.func.attr=="append" for child in ast.walk(node)))
        self.assertIn("direct_checker_event_line_inventory",ast.unparse(append))
        self.assertNotIn("read_text",ast.unparse(fn));self.assertNotIn("read_bytes",ast.unparse(fn))

    def test_complete_blank_and_empty_stream_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            for raw in (b"",b"\n \t\n\r\n"):
                path=Path(directory)/"blank.jsonl";path.write_bytes(raw)
                events,receipt=checker.load_direct_events(path,lambda *args:None)
                self.assertEqual(events,[])
                self.assertEqual(receipt["file_sha256"],hashlib.sha256(raw).hexdigest())
                self.assertEqual(receipt["line_count"],raw.count(b"\n"))
                self.assertEqual(receipt["blank_line_count"],raw.count(b"\n"))
                self.assertTrue(receipt["complete_EOF_verified"])

    def test_rejects_malformed_nonobjects_missing_events_and_partial_EOF(self):
        invalid=(b'{"event":\n',b'[]\n',b'null\n',b'1\n',b'"event"\n',b'{}\n',
            b'{"event":null}\n',b'{"event":1}\n',b'{"event":""}\n',b'{"event":"ok"}',
            b'{"event":"ok"}\n ',b'{"event":"\xff"}\n')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"invalid.jsonl"
            for raw in invalid:
                path.write_bytes(raw)
                with self.subTest(raw=raw),self.assertRaises(ValueError):checker.load_direct_events(path,lambda *args:None)

    def test_line_maximum_is_enforced_before_JSON_parse(self):
        raw=b'{"event":"bounded"}\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"events.jsonl";path.write_bytes(raw)
            with patch.object(checker,"DIRECT_EVENT_MAX_LINE_BYTES",len(raw)):
                self.assertEqual(checker.load_direct_events(path,lambda *args:None)[0],[{"event":"bounded"}])
            with patch.object(checker,"DIRECT_EVENT_MAX_LINE_BYTES",len(raw)-1),\
                 patch.object(checker,"DIRECT_EVENT_CHUNK_BYTES",7),\
                 patch.object(checker.json,"loads",side_effect=AssertionError("oversized line must stop before parse")):
                with self.assertRaisesRegex(ValueError,"bounded maximum"):checker.load_direct_events(path,lambda *args:None)

    def test_gate_denial_propagates_before_the_denied_operation(self):
        raw=b'{"event":"denied"}\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"events.jsonl";path.write_bytes(raw)
            for boundary in ("direct_checker_event_scan_chunk","direct_checker_event_line_inventory",
                             "direct_checker_event_json_line","direct_checker_event_full_EOF"):
                def gate(name,facts):
                    if name==boundary:raise MemoryError("synthetic denied admission")
                with patch.object(checker.json,"loads",wraps=json.loads) as decode:
                    with self.assertRaisesRegex(MemoryError,"synthetic denied"):checker.load_direct_events(path,gate)
                    self.assertEqual(decode.call_count,1 if boundary.endswith("full_EOF") else 0)

    def test_mutation_between_passes_and_unscanned_trailing_bytes_are_rejected(self):
        raw=b'{"event":"first"}\n';changed=b'{"event":"other"}\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"events.jsonl"
            for action,boundary in (("same_length","direct_checker_event_json_line"),
                                    ("append","direct_checker_event_full_EOF"),
                                    ("stat_only","direct_checker_event_json_line")):
                path.write_bytes(raw);mutated=False
                def gate(name,facts):
                    nonlocal mutated
                    if name==boundary and not mutated:
                        mutated=True
                        if action=="same_length":path.write_bytes(changed)
                        elif action=="append":
                            with path.open("ab") as stream:stream.write(b'{"event":"tail"}\n')
                        else:
                            stamp=path.stat();os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1_000_000))
                with self.subTest(action=action),self.assertRaises(ValueError):checker.load_direct_events(path,gate)
                self.assertTrue(mutated)

    def test_same_head_exact_identity_and_full_cross_head_bridge_receipt(self):
        worker,current=sources(self.inventory)
        same=checker.bind_direct_checker_source(worker,copy.deepcopy(worker))
        self.assertTrue(same["same_head_exact_source_identity"])
        self.assertEqual(same["changed_paths"],[])
        bridge=checker.bind_direct_checker_source(worker,current)
        self.assertEqual(bridge,{"schema":"task40extra.direct-X-checker-event-stream-source-bridge.v1",
            "worker_head":BASE,"checker_head":"d"*40,"same_head_exact_source_identity":False,
            "allowed_checker_test_paths":sorted([DIRECT,GENERIC,TEST]),"changed_paths":sorted([DIRECT,GENERIC,TEST]),
            "all_other_numerical_config_input_dependencies_equal":True,
            "worker_dependency_manifest_sha256":WORKER_MANIFEST_SHA,
            "checker_dependency_manifest_sha256":checker.digest_json(current["files_sha256"]),
            "changed_dependencies":[{"path":path,"worker_sha256":worker["files_sha256"].get(path),
                "checker_sha256":current["files_sha256"][path]} for path in sorted([DIRECT,GENERIC,TEST])]})

    def test_bridge_rejects_dirty_drift_missing_hashes_or_unpinned_worker(self):
        worker,current=sources(self.inventory)
        for which,key,value in (("worker","dirty",False),("checker","dirty",False),
                               ("worker","dirty"," M source.py"),("checker","dirty","?? evidence"),
                               ("checker","branch","other_branch"),("worker","head","e"*40),
                               ("checker","head","invalid"),("worker","files_sha256",{}),
                               ("checker","files_sha256",{})):
            old=copy.deepcopy(worker);new=copy.deepcopy(current);(old if which=="worker" else new)[key]=value
            with self.subTest(which=which,key=key,value=value),self.assertRaises(ValueError):checker.bind_direct_checker_source(old,new)
        for which in ("worker","checker"):
            for value in (None,"","G"*64,3):
                old=copy.deepcopy(worker);new=copy.deepcopy(current);(old if which=="worker" else new)["files_sha256"][DIRECT]=value
                with self.assertRaises(ValueError):checker.bind_direct_checker_source(old,new)
        changed=copy.deepcopy(current);changed["head"]=BASE
        with self.assertRaises(ValueError):checker.bind_direct_checker_source(worker,changed)
        changed=copy.deepcopy(worker);changed["source_metadata_drift"]=True
        with self.assertRaises(ValueError):checker.bind_direct_checker_source(worker,changed)

    def test_cross_head_requires_both_checker_changes_one_test_addition_and_all_other_dependencies(self):
        worker,current=sources(self.inventory)
        untouched=next(path for path in self.inventory if path.startswith("src/solvers/"))
        for mutation in ("omit_direct_change","omit_generic_change","omit_test","remove_file","change_numerics",
                         "add_other","worker_checker_hash","worker_inventory_subset","test_preexisting"):
            old=copy.deepcopy(worker);new=copy.deepcopy(current)
            if mutation=="omit_direct_change":new["files_sha256"][DIRECT]=old["files_sha256"][DIRECT]
            elif mutation=="omit_generic_change":new["files_sha256"][GENERIC]=old["files_sha256"][GENERIC]
            elif mutation=="omit_test":del new["files_sha256"][TEST]
            elif mutation=="remove_file":del new["files_sha256"][untouched]
            elif mutation=="change_numerics":new["files_sha256"][untouched]="e"*64
            elif mutation=="add_other":new["files_sha256"]["src/test/unapproved_extra.py"]="e"*64
            elif mutation=="worker_checker_hash":old["files_sha256"][DIRECT]="e"*64
            elif mutation=="worker_inventory_subset":old["files_sha256"]={path:old["files_sha256"][path] for path in (DIRECT,GENERIC)}
            else:old["files_sha256"][TEST]="e"*64
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):checker.bind_direct_checker_source(old,new)

    def test_worker_report_provenance_and_ABI_stay_exact_across_source_bridge(self):
        fixture=fixture_scope();value=fixture["report"]();value["artifacts"]=fixture["artifacts"](value,"prefactor")
        prior=fixture["provenance"](value);worker,current=sources(self.inventory)
        value["source"]=worker;prior["source"]=copy.deepcopy(worker)
        kwargs={"checker_source":current,"checker_environment":value["environment"],"stage":"prefactor"}
        self.assertTrue(checker.validate_metadata_bindings(value,prior,value["artifacts"],**kwargs))
        for mutation in ("report_to_checker","provenance_to_checker","different_ABI","wrong_manifest","dirty_worker"):
            report=copy.deepcopy(value);provenance=copy.deepcopy(prior);arguments=copy.deepcopy(kwargs)
            if mutation=="report_to_checker":report["source"]=current
            elif mutation=="provenance_to_checker":provenance["source"]=current
            elif mutation=="different_ABI":arguments["checker_environment"]["qualification_manifest_sha256"]="f"*64
            elif mutation=="wrong_manifest":report["artifacts"]={}
            else:report["source"]["dirty"]=" M src/solvers/source.py";provenance["source"]=report["source"]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                checker.validate_metadata_bindings(report,provenance,value["artifacts"],**arguments)

    def test_generic_X_output_admission_retains_original_fresh_output_guard(self):
        worker,current=sources(self.inventory)
        kwargs={"worker_directory":Path("/tmp/immutable_worker"),"output_directory":Path("/tmp/fresh_checker"),
            "explicit_checker_directory":True,"prior_checker_output":False,"direct_profile":"X"}
        with patch.dict(sys.modules,{"benchmarks.check_y_orbit_direct_probe":checker}):
            self.assertEqual(generic.admit_checker_output(worker,current,**kwargs),checker.bind_direct_checker_source(worker,current))
            for field,value in (("output_directory",kwargs["worker_directory"]),("explicit_checker_directory",False),
                                ("explicit_checker_directory",1),("prior_checker_output",True),("prior_checker_output",0),
                                ("direct_profile","XZ"),("direct_profile","Y"),("direct_profile",True)):
                changed=dict(kwargs);changed[field]=value
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):generic.admit_checker_output(worker,current,**changed)
        plain=dict(kwargs);plain.pop("direct_profile")
        with self.assertRaises(ValueError):generic.admit_checker_output(worker,current,**plain)
        original=subprocess.run(["git","-C",str(REPO),"show",BASE+":"+GENERIC],check=True,capture_output=True,text=True).stdout
        old=next(node for node in ast.parse(original).body if isinstance(node,ast.FunctionDef) and node.name=="admit_checker_output")
        new=next(node for node in ast.parse((ROOT/GENERIC).read_text()).body if isinstance(node,ast.FunctionDef) and node.name=="admit_checker_output")
        guard=next(node for node in old.body if isinstance(node,ast.If))
        same=next(node for node in new.body if isinstance(node,ast.If) and isinstance(node.test,ast.BoolOp))
        self.assertEqual(ast.dump(guard),ast.dump(same))

    def test_streamed_complete_factor_proof_events_feed_unchanged_validator(self):
        fixture=fixture_scope();value=fixture["report"]("solve");value["artifacts"]=fixture["artifacts"](value,"solve")
        events=fixture["events"](value,"solve")
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"proof.jsonl"
            def load(records):
                path.write_bytes(b"".join(json.dumps(record).encode()+b"\n" for record in records))
                return checker.load_direct_events(path,lambda *args:None)[0]
            self.assertEqual(load(events),events)
            self.assertTrue(checker.validate_direct_event_contract(load(events),value,"solve"))
            for removed in ("direct_fresh_carrier_qualification_complete","direct_complete_original_operator_qualification",
                            "shared_complete_equivalence_before_any_factor","direct_complete_original_qualification_before_any_factor",
                            "allocation_admission","all_branch_factor_created","all_branch_factor_retained"):
                records=copy.deepcopy(events);index=next(index for index,event in enumerate(records) if event["event"]==removed);records.pop(index)
                with self.subTest(removed=removed),self.assertRaises(ValueError):checker.validate_direct_event_contract(load(records),value,"solve")
        original=subprocess.run(["git","-C",str(REPO),"show",BASE+":"+DIRECT],check=True,capture_output=True,text=True).stdout
        old=next(node for node in ast.parse(original).body if isinstance(node,ast.FunctionDef) and node.name=="validate_direct_event_contract")
        new=next(node for node in ast.parse((ROOT/DIRECT).read_text()).body if isinstance(node,ast.FunctionDef) and node.name=="validate_direct_event_contract")
        class RestoreOldFourQ(ast.NodeTransformer):
            metadata_assignment_count=0
            Y_retention_count=0
            allowance_assignment_count=0
            def visit_Assign(self,node):
                if any(isinstance(t,ast.Name) and t.id=='metadata' for t in node.targets):
                    self.metadata_assignment_count+=1;return None
                if any(isinstance(t,ast.Name) and t.id=='allowance' for t in node.targets):
                    self_outer.assertEqual(ast.unparse(node.value),'(metadata.ny - q) * metadata.factor_allowance_per_q_bytes')
                    self.allowance_assignment_count+=1
                    original_allowance=next(n for n in ast.walk(old) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='allowance' for t in n.targets))
                    return copy.deepcopy(original_allowance)
                return self.generic_visit(node)
            def visit_If(self,node):
                if ast.unparse(node.test)=="metadata.name == 'Y'":
                    self.Y_retention_count+=1
                    self_outer.assertEqual(len(node.body),1)
                    self_outer.assertIn("'remaining_declared_allowance_bytes'",ast.unparse(node.body[0]))
                    self_outer.assertIn("'factor_memory_bytes'",ast.unparse(node.body[0]))
                    self_outer.assertIn('is None',ast.unparse(node.body[0]))
                    return None
                return self.generic_visit(node)
            def visit_Attribute(self,node):
                if isinstance(node.value,ast.Name) and node.value.id=='metadata':
                    if node.attr=='ny':return ast.Constant(4)
                    if node.attr=='factor_allowance_per_q_bytes':return ast.parse('128*1024**2',mode='eval').body
                return self.generic_visit(node)
        self_outer=self
        restored=RestoreOldFourQ();normalized=restored.visit(copy.deepcopy(new))
        self.assertEqual((restored.metadata_assignment_count,restored.Y_retention_count,restored.allowance_assignment_count),(1,1,1))
        self.assertEqual(ast.dump(old),ast.dump(normalized))

    def test_live_checker_source_seams_use_loader_bridge_and_head_alias(self):
        direct_tree=ast.parse((ROOT/DIRECT).read_text())
        direct_fn=next(node for node in direct_tree.body if isinstance(node,ast.FunctionDef) and node.name=="check_direct")
        loader_calls=[node for node in ast.walk(direct_fn) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Name) and node.func.id=="load_direct_events"]
        self.assertEqual(len(loader_calls),1)
        self.assertEqual([ast.unparse(arg) for arg in loader_calls[0].args],["events_path","allocation_gate"])
        self.assertFalse(any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
            and isinstance(node.func.value,ast.Name) and node.func.value.id=="events_path"
            and node.func.attr in {"read_text","read_bytes"} for node in ast.walk(direct_fn)))
        metadata=next(node for node in direct_tree.body if isinstance(node,ast.FunctionDef) and node.name=="validate_metadata_bindings")
        self.assertTrue(any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
            and node.func.id=="bind_direct_checker_source" for node in ast.walk(metadata)))
        generic_tree=ast.parse((ROOT/GENERIC).read_text())
        aliases=[node for node in ast.walk(generic_tree) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Attribute) and node.func.attr=="add_argument"
            and any(isinstance(arg,ast.Constant) and arg.value=="--expected-checker-head" for arg in node.args)]
        self.assertEqual(len(aliases),1)
        self.assertIn("--expected-head",[arg.value for arg in aliases[0].args if isinstance(arg,ast.Constant)])
        admissions=[node for node in ast.walk(generic_tree) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Name) and node.func.id=="admit_checker_output"]
        self.assertEqual(len(admissions),1)
        self.assertTrue(any(keyword.arg=="direct_profile" and ast.unparse(keyword.value)=="direct_profile" for keyword in admissions[0].keywords))
        # Scan only source trees; ignored historical evidence stays outside this contract.
        for suffix in ("*.npy","*.npz"):
            self.assertFalse(list((ROOT/"src").rglob(suffix)))
            self.assertFalse([path for path in (ROOT/"benchmarks").rglob(suffix)
                if path.relative_to(ROOT/"benchmarks").parts[0]!="artifacts"])

    def test_synthetic_X_main_rejections_preserve_existing_worker_checker_files(self):
        runner_tree=ast.parse((REPO/"benchmarks/run_y_orbit_quotient_probe.py").read_text())
        keep={"research_wall_budget","research_phase_budget","research_memory_budget",
            "validate_research_memory_launch","research_memory_child_budget"}
        helpers={"math":math,"json":json,"Path":Path,"__file__":str(REPO/"benchmarks/run_y_orbit_quotient_probe.py")}
        exec(compile(ast.Module(body=[node for node in runner_tree.body if isinstance(node,ast.Assign)
            or isinstance(node,ast.FunctionDef) and node.name in keep],type_ignores=[]),"<stdlib supervisor metadata helpers>","exec"),helpers)
        main=next(node for node in ast.parse((ROOT/GENERIC).read_text()).body if isinstance(node,ast.FunctionDef) and node.name=="main")
        main.body=[node for node in main.body if not isinstance(node,(ast.Import,ast.ImportFrom))]
        worker,current=sources(self.inventory)
        for failure in ("missing_fresh_output","stale_expected_head"):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);directory=root/"benchmarks/artifacts/task40extra_dot_parallel_cloud/worker"
                directory.mkdir(parents=True)
                (directory/"probe_report.json").write_text(json.dumps({"source":worker}))
                (directory/"provenance.json").write_text(json.dumps({"direct_profile":"X"}))
                for name in ("independent_checker.json","checker_traceback.txt","checker_events.jsonl","checker_phase.json"):
                    (directory/name).write_text("immutable saved checker metadata")
                before={path.name:path.read_bytes() for path in directory.iterdir()}
                output=directory.parent/"fresh_checker";output.mkdir()
                called=[]
                def source_reader(expected):
                    called.append(expected)
                    if failure=="stale_expected_head":raise RuntimeError("actual clean HEAD differs from stale expected HEAD")
                    return current
                def forbidden(*args,**kwargs):raise AssertionError("rejected source/output admission must not run or write checker evidence")
                scope=dict(vars(generic),**helpers)
                scope.update(__file__=str(root/GENERIC),argparse=argparse,os=os,sys=sys,time=time,
                    source_facts=source_reader,environment_facts=forbidden,write_json=forbidden,check=forbidden)
                exec(compile(ast.Module(body=[main],type_ignores=[]),"<synthetic X CLI main rejection>","exec"),scope)
                arguments=["--worker","--expected-checker-head",current["head"],"--stage","solve","--run-directory",str(directory)]
                if failure=="stale_expected_head":arguments += ["--checker-directory",str(output)]
                with patch.dict(sys.modules,{"benchmarks.check_y_orbit_direct_probe":checker}),\
                     patch.dict(os.environ,{"PHYSICAL_WATCHDOG_PARENT_PID":str(os.getppid()),
                        "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES":str(checker.TREE_CAP_BYTES),"PHYSICAL_TIMEBASE_GUARD":"1"},clear=True),\
                     self.assertRaises((RuntimeError,ValueError)):
                    scope["main"](arguments)
                self.assertEqual(called,[current["head"]])
                self.assertEqual(before,{path.name:path.read_bytes() for path in directory.iterdir()})
                self.assertEqual(list(output.iterdir()),[])


if __name__ == "__main__":unittest.main(verbosity=2)
