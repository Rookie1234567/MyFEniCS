"""One input, one supervised six-layer FE case; no batch or GP scheduling."""
from __future__ import annotations
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import time

from ..common.strict_json import atomic_json,snapshot
from ..io.sixlayer_input import resolve_sixlayer_input,build_sixlayer_config

ROOT=Path(__file__).resolve().parents[2]


def file_sha(path):
    h=sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(2**20),b""):h.update(block)
    return h.hexdigest()


def exact_record(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path or path.is_symlink() or not path.is_file():
        raise RuntimeError("regular canonical input/artifact required: "+str(path))
    return {"path":str(path),"bytes":path.stat().st_size,"sha256":file_sha(path)}


def execution_records():
    records={}
    for role in ("COMPILER_POLICY","COMPILER_RECIPE","OWNER_ENTRY","JIT_CONFIG"):
        item=exact_record(os.environ["TASK44_"+role+"_FILE"])
        if item["sha256"]!=os.environ["TASK44_"+role+"_SHA256"]:raise RuntimeError(role+" identity mismatch")
        records[role]=item
    recipe=json.loads(Path(records["COMPILER_RECIPE"]["path"]).read_text())
    if (recipe["source_sha256"]!=records["COMPILER_POLICY"]["sha256"]
            or recipe["runtime"]!=os.environ["TASK44_RUNTIME_PREFIX"]
            or recipe["compiler"]!=sysconfig.get_config_var("CC")
            or recipe["C_only"] is not True or recipe["runtime_byte_changes"]!=0):
        raise RuntimeError("qualified compiler recipe is not the currently active process policy")
    return records


def prepare_case_jit_config(out,execution):
    original=Path(execution["JIT_CONFIG"]["path"])
    if original != (Path(os.environ["XDG_CONFIG_HOME"])/"dolfinx/dolfinx_jit_options.json").resolve():
        raise RuntimeError("the pinned JIT config is not the current runtime config")
    options=json.loads(original.read_text())
    if set(options)!={"cache_dir","cffi_extra_compile_args","timeout"}:
        raise RuntimeError("unexpected runtime JIT policy keys")
    if options["cffi_extra_compile_args"]!=["-O1","-g0","-fno-fast-math","-ffp-contract=off"] or options["timeout"]!=600:
        raise RuntimeError("runtime JIT math/compiler policy changed")
    if (ROOT/"dolfinx_jit_options.json").exists() or (ROOT/"ffcx_options.json").exists():
        raise RuntimeError("unexpected working-directory JIT policy override")
    original_xdg=Path(os.environ["XDG_CONFIG_HOME"])
    if (original_xdg/"ffcx/ffcx_options.json").exists():raise RuntimeError("unregistered FFCx user policy")
    patched={**options,"cache_dir":str(out/"cache/fenics")}
    target=out/"config/dolfinx/dolfinx_jit_options.json"
    atomic_json(target,patched)
    os.environ["XDG_CONFIG_HOME"]=str(out/"config")
    os.environ["XDG_CACHE_HOME"]=str(out/"cache")
    atomic_json(out/"jit_config_transition.json",{"original":execution["JIT_CONFIG"],"original_values":options,
            "effective":exact_record(target),"effective_values":patched,"only_changed_key":"cache_dir"})
    return patched


def generated_native_records(out):
    # Both directories are created by this fresh single-owner case. Nothing
    # outside these two exact build locations may become a generated native
    # permission; the loaded gate still verifies each mapped file separately.
    rows=[]
    for directory in (out/"cache/fenics",out/"native/mumps_symbolic"):
        if directory.exists():
            if directory.is_symlink():raise RuntimeError("symlink generated build directory")
            for path in sorted(directory.rglob("*")):
                if path.suffix in (".so",".c"):
                    if not path.resolve(strict=True).is_relative_to(directory):raise RuntimeError("generated build path escaped")
                    rows.append(exact_record(path))
    return rows


def source_identity():
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    branch=subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip()
    if branch!="task40extra_dot_parallel_cloud":raise RuntimeError("wrong authorized execution branch")
    files=sorted({p for directory in (ROOT/"src",ROOT/"scripts",ROOT/"benchmarks/supervision_task44")
                  for p in directory.rglob("*") if p.is_file() and p.suffix in (".py",".c")})
    records=[{"path":str(p.relative_to(ROOT)),"sha256":file_sha(p),"bytes":p.stat().st_size} for p in files]
    digest=sha256(json.dumps(records,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {"git_HEAD":head,"branch":branch,"working_source_sha256":digest,"files":records}


def _stage_module():
    path=ROOT/"benchmarks/supervision_task44/stage_admission_v1.py"
    spec=importlib.util.spec_from_file_location("_sixlayer_stage_admission",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if Path(module.__file__).resolve()!=path.resolve():raise RuntimeError("stage admission module origin")
    return module


def validate_outputs(summary,absorption,original,plan):
    import math
    if original.get("passed") is not True or not 0<=float(original["relative_residual"])<=1e-6:
        raise ValueError("original full augmented residual does not pass")
    regions=absorption["regions"]
    for name,expected in plan["expected_region_volumes_nm3"].items():
        if name=="air":continue
        record=regions[name]
        if (record["cell_count"]<=0 or record["status"] not in ("ok","lossless")
                or record["A_volume"] is None or not math.isfinite(float(record["A_volume"]))
                or abs(float(record["volume_nm3"])-expected)>1e-11*max(1.0,expected)):
            raise ValueError("incomplete material volume/absorption: "+name)
    out={name:float(summary[name]) for name in ("R_total","T_total","R00_s","R00_p","R00_total","A_balance")}
    out["A_volume"]=float(absorption["A_volume_total"])
    if not all(math.isfinite(v) for v in out.values()):raise ValueError("nonfinite power output")
    if min(out[k] for k in ("R_total","T_total","R00_s","R00_p","R00_total","A_volume")) < -1e-12:
        raise ValueError("negative power")
    if abs(out["R00_total"]-out["R00_s"]-out["R00_p"])>1e-12:raise ValueError("R00 components")
    if out["R00_total"]>out["R_total"]+1e-12:raise ValueError("R00 cannot exceed all reflected power")
    if abs(out["A_balance"]-(1-out["R_total"]-out["T_total"]))>1e-12:raise ValueError("absorption balance identity")
    if abs(out["R_total"]+out["T_total"]+out["A_volume"]-1)>1e-5:raise ValueError("volume energy closure")
    return out


def validate_floquet(summary,cfg):
    """Actual MPC phase/count diagnostics, not only periodic mesh coordinates."""
    import cmath
    import math
    keys=("floquet_x_face_mismatch","floquet_y_face_mismatch","floquet_edge_corner_mismatch",
          "floquet_edge_corner_constraint_phase_mismatch","max_face_pairing_coordinate_error")
    facts={key:float(summary[key]) for key in keys}
    for value in facts.values():
        if not math.isfinite(value) or value<0 or value>1e-10:raise ValueError("Floquet pairing/phase mismatch")
    counts=("floquet_num_constraints","floquet_num_x_constraints","floquet_num_y_constraints","floquet_num_corner_constraints")
    for key in counts:
        value=summary[key]
        if isinstance(value,bool) or int(value)!=value or value<=0:raise ValueError("missing actual Floquet constraints")
        facts[key]=int(value)
    # Native summary returned in memory retains complex phases; JSON codecs
    # are only used after all three exact physical phases have been checked.
    px=cmath.exp(1j*cfg.kx*(cfg.x_max-cfg.x_min));py=cmath.exp(1j*cfg.ky*(cfg.y_max-cfg.y_min))
    for axis,expected in (("x",px),("y",py),("corner",px*py)):
        actual=complex(summary["floquet_constraint_phase_"+axis])
        if not (math.isfinite(actual.real) and math.isfinite(actual.imag)) or abs(actual-expected)>1e-12:
            raise ValueError("actual Floquet phase differs from fixed incident wavevector")
        facts["phase_"+axis]={"actual":actual,"expected":expected}
    facts["scope"]="actual MPC pairing/constraint phases; not an independent field trace error estimate"
    return facts


def run_sixlayer(path,*,dry_run=False):
    loaded,resolved=resolve_sixlayer_input(path)
    if dry_run:return resolved
    # Required before any scientific import. The sole owner establishes this
    # process-group identity and monitors tree memory/available/swap externally.
    required=("TASK44_TREE_CAP_BYTES","TASK44_SUPERVISOR_PID","TASK44_SUPERVISOR_START_TICKS",
              "TASK44_STAGE_LOG","TASK44_AVAILABLE_FLOOR_BYTES","TASK44_RUNTIME_PREFIX",
              "TASK44_RUNTIME_MEMBER_MANIFEST","TASK44_RUNTIME_MEMBER_MANIFEST_SHA256")
    if any(name not in os.environ for name in required):raise RuntimeError("formal case requires qualified single-owner supervisor")
    stage=_stage_module();stage.admit("before_native_imports",512*2**20,estimate_basis="native FE import and mesh preparation reserve")
    out=Path(resolved["output_directory"])
    if not out.is_absolute():out=ROOT/out
    out=out.resolve()
    allowed=(ROOT/"benchmarks/artifacts/task44").resolve()
    if not out.is_relative_to(allowed):raise ValueError("Task44 outputs must stay in ignored benchmarks/artifacts/task44")
    out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();report={"schema":"sixlayer-case-run.v1","sample_id":resolved["sample_id"],"status":"RUNNING"}
    primary=None
    try:
        identity=source_identity()
        execution=execution_records()
        scientific_inputs=[exact_record(loaded.source_path),exact_record(ROOT/"input/materials/task44_0p7nm.json")]
        source_records=[{**row,"path":str(ROOT/row["path"])} for row in identity["files"]]
        source_records.extend(execution[key] for key in ("COMPILER_POLICY","OWNER_ENTRY"))
        atomic_json(out/"resolved_config.json",resolved)
        (out/"input_original.dat").write_bytes(loaded.raw_input_bytes)
        for name,value in (("input_sha256",loaded.input_sha256),("physical_model_sha256",resolved["physical_model_sha256"]),("source_sha",identity["git_HEAD"])):
            (out/(name+".txt")).write_text(value+"\n")
        atomic_json(out/"run_manifest.json",{"source":identity,"execution":execution,"scientific_inputs":scientific_inputs,
                    "resolved_input_sha256":file_sha(out/"resolved_config.json"),
                    "entry":"python scripts/run_case.py input/path.dat","stage_log":os.environ["TASK44_STAGE_LOG"],
                    "supervisor_pid":int(os.environ["TASK44_SUPERVISOR_PID"]),"MPI":1})
        from ..common.runtime_resource_policy import resource_policy
        with resource_policy(stage.admit):
            from ..common.native_runtime_identity import arm_native_runtime_identity,require_native_runtime_identity
            preimport=arm_native_runtime_identity()
            jit_expected=prepare_case_jit_config(out,execution)
            import numpy as np
            import scipy, dolfinx, dolfinx_mpc, basix, ffcx, ufl
            import slepc4py.SLEPc
            from petsc4py import PETSc
            from mpi4py import MPI
            if (MPI.COMM_WORLD.size!=1 or np.dtype(PETSc.ScalarType)!=np.dtype("complex128")
                    or np.dtype(PETSc.IntType)!=np.dtype("int32")):
                raise RuntimeError("MPI1 complex128 int32 required")
            from dolfinx import jit
            effective_jit=jit.get_options()
            if any((str(effective_jit[k]) if k=="cache_dir" else effective_jit[k])!=v for k,v in jit_expected.items()):
                raise RuntimeError("actual DOLFINx JIT policy differs from explicit case policy")
            atomic_json(out/"actual_jit_options.json",{k:str(v) if isinstance(v,Path) else v for k,v in effective_jit.items()})
            def loaded_gate(label):
                generated=generated_native_records(out)
                atomic_json(out/(label+"_generated.json"),generated)
                actual=require_native_runtime_identity(os.environ["TASK44_RUNTIME_PREFIX"],
                    os.environ["TASK44_RUNTIME_MEMBER_MANIFEST"],generated,
                    member_manifest_sha256=os.environ["TASK44_RUNTIME_MEMBER_MANIFEST_SHA256"],
                    preimport_state=preimport,source_records=source_records)
                atomic_json(out/(label+"_native_identity.json"),actual)
                return {"file":label+"_native_identity.json","sha256":file_sha(out/(label+"_native_identity.json")),
                        "generated_manifest_sha256":file_sha(out/(label+"_generated.json"))}
            report["before_FE_loaded_identity"]=loaded_gate("before_FE")
            cfg=build_sixlayer_config(resolved)
            from ..geometry.mesh_builder_3d import build_airbox_mesh_3d
            from ..geometry.sixlayer_mesh_audit import audit_sixlayer_mesh
            stage.admit("mesh_build",128*2**20,estimate_basis="144 affine cells and metadata; refinements independently counted")
            mesh_data=build_airbox_mesh_3d(cfg,out/"native")
            mesh_audit=audit_sixlayer_mesh(mesh_data,resolved["mesh_plan"])
            atomic_json(out/"actual_mesh_audit.json",mesh_audit)
            from ..common.modes_3d import outgoing_port_modes_3d
            modes=outgoing_port_modes_3d(cfg)
            expected=4*(2*cfg.diffraction_order_max_m+1)*(2*cfg.diffraction_order_max_n+1)
            if len(modes)!=expected:raise RuntimeError("complete two-side two-polarization lattice not returned")
            mode_rows=[{"index":i,"side":m.side,"m":m.m,"n":m.n,"polarization":m.polarization,
                        "alpha":m.alpha,"gamma":m.gamma,"beta":m.beta,"n_medium":m.refractive_index,
                        "electric":m.e_vector.tolist(),"Et_squared":m.electric_tangential_norm_sq,
                        "outward_power":m.power_per_unit_amplitude,"propagating":bool(m.propagating),
                        "rayleigh_warning":bool(m.rayleigh_warning)} for i,m in enumerate(modes)]
            atomic_json(out/"actual_modes.json",mode_rows)
            from ..solvers.solve_maxwell_3d_stage_4b_block_grating import run_stage4b_block_grating_3d_case
            summary=run_stage4b_block_grating_3d_case(cfg,out/"native",mesh_data_override=mesh_data)
            original=json.loads((out/"native/original_full_augmented_residual.json").read_text())
            absorption=json.loads((out/"native/volume_absorption.json").read_text())
            outputs=validate_outputs(summary,absorption,original,resolved["mesh_plan"])
            floquet=validate_floquet(summary,cfg)
            report.update(status="SIXLAYER_SINGLE_SAMPLE_NUMERICAL_GATES_PASS_PENDING_EXTERNAL_RESOURCES_AND_GENERATOR_QUALIFICATION",
                          outputs=outputs,full_true_residual=original["relative_residual"],mesh=mesh_audit,floquet=floquet,
                          dtn_mode_count=len(modes),dofs=summary.get("num_nedelec_dofs"),
                          native_summary_sha256=file_sha(out/"native/run_summary.json"),
                          source_sha256=identity["working_source_sha256"],
                          physical_model_sha256=resolved["physical_model_sha256"],
                          generator_sha256=resolved["generator_identity_sha256"])
            stage.admit("case_final",0,estimate_basis="no future allocation; sampled no-swap/source publication gate")
            report["after_solve_and_postprocess_loaded_identity"]=loaded_gate("after_postprocess")
        after=source_identity()
        if after!=identity:raise RuntimeError("source changed during formal case")
        for item in scientific_inputs+list(execution.values()):
            if exact_record(item["path"])!=item:raise RuntimeError("scientific/execution input changed during case")
        report["all_source_inputs_unchanged"]=True
    except BaseException as exc:
        primary=exc;report.update(status="FAILED_NOT_A_TRAINING_LABEL",error=repr(exc));raise
    finally:
        report["child_elapsed_seconds"]=time.monotonic()-started
        report["resource_scope"]="external supervisor total tree/wall required; child time is not total cost"
        try:atomic_json(out/"run_summary.json",report)
        except BaseException as exc:
            if primary is not None:primary.add_note("run summary publication: "+repr(exc))
            else:raise
    return report
