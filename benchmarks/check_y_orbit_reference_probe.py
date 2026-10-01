"""Hash-bound independent matrix/residual checker; never re-runs the solver."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
from scipy import sparse


def check_centered(directory, *, source, environment):
    from src.solvers.y_orbit_centered_evidence import (
        COMPONENT_IDENTITY, SOURCES, compare_mode_evidence, digest_json, require_centered_dense_inventory,
        bind_native_packet,
    )
    directory = Path(directory).resolve()
    report = json.loads((directory/"pilot_report.json").read_text())
    require_centered_dense_inventory(report)
    provenance = json.loads((directory/"provenance.json").read_text())
    summary = json.loads((directory/"summary.json").read_text())
    if (report.get("status") != "CENTERED_DENSE_AUTHORITY_PASS"
            or report.get("source_clean_unchanged") is not True
            or source != report.get("source") or source != provenance["source"]
            or environment != report.get("environment") or environment != provenance["environment"]
            or summary.get("classification") != "COMPLETED"
            or (not report.get("live_component_oracle",False) and any(report["identity"].get(k) != v for k,v in COMPONENT_IDENTITY.items()))
            or report.get("source_names") != list(SOURCES)
            or set(report["regular_sources"]) != set(SOURCES) or set(report["notched_sources"]) != set(SOURCES)):
        raise ValueError("fresh centered dense authority/source/config/inventory incomplete")
    if report.get("live_component_oracle",False):
        from src.solvers.y_orbit_live_boundary_contract import load_bound_live_receipt
        load_bound_live_receipt(directory,report["identity"],worker_source=source)
    descriptors = report["artifacts"]
    def load(name):
        d = descriptors[name]
        path = (directory/d["path"]).resolve()
        if not path.is_relative_to(directory) or hashlib.sha256(path.read_bytes()).hexdigest() != d["file_sha256"]:
            raise ValueError("centered dense artifact hash/path differs: "+name)
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if (list(value.shape) != d["shape"] or str(value.dtype) != d["dtype"] or value.dtype.hasobject
                or (value.dtype.kind in "fc" and not np.isfinite(value).all())):
            raise ValueError("centered dense artifact descriptor/finite inventory differs: "+name)
        return value
    for name in descriptors:
        load(name)
    checks = []
    def add(name, value, limit):
        checks.append({"name": name, "measured": float(value), "limit": limit,
                       "passed": bool(np.isfinite(value) and value <= limit)})
    rel = lambda a,b: float(np.linalg.norm(a)/max(np.linalg.norm(b), np.finfo(float).tiny))
    independent = load("independent_storage_rows")
    slaves, masters = load("full_mpc_slaves"), load("full_mpc_masters")
    coefficients, offsets = load("full_mpc_coefficients"), load("full_mpc_offsets")
    if (len(independent) != 2048 or offsets.shape != (2395,) or int(offsets[-1]) != len(coefficients)
            or len(masters) != len(coefficients) or len(np.intersect1d(slaves, masters))
            or np.any(offsets[1:] < offsets[:-1]) or int(offsets[0]) != 0
            or not np.array_equal(np.setdiff1d(np.arange(2394), slaves), independent)):
        raise ValueError("complete actual MPC storage map missing")
    if masters.size and (masters.min() < 0 or masters.max() >= 2394):
        raise ValueError("MPC master index exceeds full storage")
    mode_checks = {}
    optional_global = {}
    for prefix, matrix_name in (("regular", "A0_original"), ("notch", "A_notch_original")):
        matrix = load(matrix_name)
        if matrix.shape != (2048,2048):
            raise ValueError("full original centered dense matrix inventory differs")
        for name in SOURCES:
            b = load(name+"_rhs")
            direct = load(("A0_direct_" if prefix=="regular" else "notch_direct_")+name)
            candidate = load(("A0_modal_" if prefix=="regular" else "notch_iterative_")+name)
            add(prefix+"_"+name+"_direct_matrix_residual", rel(b-matrix@direct,b), 1e-10)
            add(prefix+"_"+name+"_candidate_matrix_residual", rel(b-matrix@candidate,b), 1e-10)
            add(prefix+"_"+name+"_direct_field_difference", rel(candidate-direct,direct), 1e-9)
            for kind in ("direct_", ""):
                label = kind+prefix+"_"+name
                rhs, field = load(label+"_rhs_storage"), load(label+"_solution_storage")
                action, volume, coupling = (load(label+"_"+key) for key in ("original_action", "volume_action", "coupling_action"))
                alpha, projection, h = (load(label+"_"+key) for key in ("auxiliary_ports", "projection", "normalization_h"))
                expected_field = direct if kind else candidate
                if (field.shape != (2394,) or rhs.shape != (2394,) or any(v.shape != (532,) for v in (alpha,projection,h))
                        or np.any(field[slaves] != 0) or np.any(h <= 0)):
                    raise ValueError("full native zero-slave/port inventory differs")
                bind_native_packet(field,rhs,expected_field,b,independent)
                add(label+"_native_action_bound_to_full_matrix",rel(action[independent]-matrix@expected_field,b),1e-11)
                add(label+"_original_action_residual", rel(rhs-action,rhs), 1e-10)
                add(label+"_augmented_FE_residual", rel(rhs-volume-coupling,rhs), 1e-10)
                add(label+"_port_closure", np.linalg.norm(projection-h*alpha)/
                    max(np.linalg.norm(projection)+np.linalg.norm(h*alpha),np.finfo(float).tiny), 1e-10)
                reconstructed = field.copy()
                for slave in slaves:
                    start, stop = int(offsets[slave]), int(offsets[slave+1])
                    if stop <= start:
                        raise ValueError("finalized MPC slave has empty expansion")
                    reconstructed[slave] = np.dot(coefficients[start:stop], field[masters[start:stop]])
                recovered = load(label+"_recovered_field")
                add(label+"_independent_actual_MPC_recovery", rel(recovered-reconstructed,reconstructed), 1e-12)
                packet = report[("regular_sources" if prefix=="regular" else "notched_sources")][name]["direct" if kind else "candidate"]
                optional_global[label] = packet["outputs"].get("status")
                if (packet["outputs"].get("finite_plane_mode_count") != 532
                        or packet["outputs"].get("status") != "representable_global_output"
                        or packet["outputs"].get("global_output_component_consistency_checked") is not True):
                    raise ValueError("complete required finite-plane output packet missing")
                amplitude_error=np.abs(load(label+"_plane_total_auxiliary")-alpha)
                amplitude_scale=load(label+"_mode_local_amplitude_scale")
                if np.any((amplitude_scale == 0)&(amplitude_error != 0)):
                    raise ValueError("nonzero dense alpha recovery error has zero local scale")
                ratio=np.divide(amplitude_error,amplitude_scale,out=np.zeros_like(amplitude_error),where=amplitude_scale != 0)
                add(label+"_mode_output_bound_to_original_alpha",np.max(ratio),1e-10)
            mode_checks[prefix+"_"+name] = compare_mode_evidence(load,
                lambda key: load("direct_"+key), prefix+"_"+name)
            add(prefix+"_"+name+"_recovered_full_field_difference", rel(load(prefix+"_"+name+"_recovered_field")-
                load("direct_"+prefix+"_"+name+"_recovered_field"),load("direct_"+prefix+"_"+name+"_recovered_field")),1e-9)
    q = sparse.csr_matrix((load("Q_data"),load("Q_indices"),load("Q_indptr")),shape=(2048,2048))
    norms = np.linalg.norm(np.asarray(q.conj().T@load("generic_rhs")).reshape(4,512),axis=1)
    all_q = bool(np.min(norms)/np.linalg.norm(norms) >= 1e-3)
    interior = load("interior_only_rhs")
    interior_positions=load("actual_interior_positions")
    if (interior_positions.shape != (480,) or interior_positions.dtype.kind not in "iu"
            or len(np.unique(interior_positions))!=480 or interior_positions.min()<0 or interior_positions.max()>=2048):
        raise ValueError("actual Basix interior row inventory incomplete")
    all_interior = bool(np.array_equal(np.flatnonzero(interior),interior_positions))
    t = sparse.csr_matrix((load("T_data"),load("T_indices"),load("T_indptr")),shape=(2048,2048))
    matrix = load("A0_original")
    from src.solvers.task40extra_y_orbit_reference import _congruence
    add("native_form_covariance", rel(_congruence(matrix,t)-matrix,matrix),1e-11)
    ri = sparse.csr_matrix((load("R_inverse_data"),load("R_inverse_indices"),load("R_inverse_indptr")),shape=(2048,2048))
    f = sparse.csr_matrix((load("F_data"),load("F_indices"),load("F_indptr")),shape=(2048,2048))
    modal = np.asarray(f.conj().T@(ri@load("notch_iterative_physical"))).reshape(4,512)
    nonzero_q = float(np.linalg.norm(modal[1:])/np.linalg.norm(modal))
    resources = (summary.get("sampled_process_tree_swap_peak_bytes")==0 and summary.get("descendants_cleared") is True
       and summary.get("process_tree_all_status_readable") is True and summary.get("process_tree_all_identity_complete") is True
       and 0 < summary["sampled_process_tree_rss_peak_bytes"] < 3*1024**3//2)
    outputs = all(c["passed"] for group in mode_checks.values() for c in group.values())
    return {"schema":"task40extra.centered-dense-checker.v1","evidence_valid":True,
       "gate_pass": bool(all(c["passed"] for c in checks) and outputs and all_q and all_interior and resources
                         and nonzero_q > 1e-12 and report["notch_delta_off_q_relative"] >= 1e-8),
       "report_sha256":hashlib.sha256((directory/"pilot_report.json").read_bytes()).hexdigest(),
       "provenance_sha256":hashlib.sha256((directory/"provenance.json").read_bytes()).hexdigest(),
       "artifact_manifest_sha256":digest_json(descriptors),"source":source,"environment":environment,
       "degree":2,"identity":report["identity"],"live_component_oracle":report.get("live_component_oracle",False),"checks":checks,"per_mode_output_checks":mode_checks,
       "generic_all_q_excitation":all_q,"all_480_nonzero_interior_load_entries":all_interior,
       "physical_notch_nonzero_q_relative":nonzero_q,"optional_global_output_statuses":optional_global,
       "global_conversion_representability_is_not_assumed":True,
       "required_global_output_contract_verified":True,"official_RTA":False}


def check(directory: Path):
    report = json.loads((directory / "pilot_report.json").read_text())
    if report.get("status") != "ARCHITECTURE_IDENTITY_AND_NOTCH_PASS":
        return {"evidence_valid": False, "gate_pass": False, "reason": "no completed architecture report"}
    artifacts = report["artifacts"]
    def load(label):
        descriptor = artifacts[label]
        path = (directory / descriptor["path"]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("artifact escapes its run directory")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != descriptor["file_sha256"]:
            raise ValueError("artifact hash mismatch: " + label)
        array = np.load(path, allow_pickle=False, mmap_mode="r")
        if list(array.shape) != descriptor["shape"] or str(array.dtype) != descriptor["dtype"]:
            raise ValueError("artifact descriptor mismatch: " + label)
        return array
    n = int(report["layout"]["independent_rows"])
    q = sparse.csr_matrix((load("Q_data"), load("Q_indices"), load("Q_indptr")), shape=(n, n))
    r_inverse = sparse.csr_matrix((load("R_inverse_data"), load("R_inverse_indices"), load("R_inverse_indptr")), shape=(n, n))
    fourier = sparse.csr_matrix((load("F_data"), load("F_indices"), load("F_indptr")), shape=(n, n))
    rhs = {label: load(label + "_rhs") for label in ("generic", "physical")}
    regular_matrix = load("A0_original")
    notch_matrix = load("A_notch_original")
    checks = []
    def add(name, value, limit):
        checks.append({"name": name, "measured": float(value), "limit": float(limit),
                       "pass": bool(np.isfinite(value) and value <= limit)})
    for prefix, matrix in (("A0", regular_matrix), ("notch", notch_matrix)):
        for label, b in rhs.items():
            direct = load(prefix + "_direct_" + label)
            candidate = load(prefix + ("_modal_" if prefix == "A0" else "_iterative_") + label)
            scale = max(float(np.linalg.norm(b)), np.finfo(float).tiny)
            add(prefix + "_direct_" + label + "_matrix_true_residual", np.linalg.norm(b - matrix @ direct) / scale, 1e-10)
            add(prefix + "_candidate_" + label + "_matrix_true_residual", np.linalg.norm(b - matrix @ candidate) / scale, 1e-10)
            add(prefix + "_" + label + "_direct_difference", np.linalg.norm(candidate - direct) / max(np.linalg.norm(direct), np.finfo(float).tiny), 1e-9)
    modal_rhs = np.asarray(q.conj().T @ rhs["generic"]).reshape(report["layout"]["ny"], report["layout"]["rows_per_q"])
    norms = np.linalg.norm(modal_rhs, axis=1)
    all_q = bool(np.min(norms) / np.linalg.norm(norms) >= 1e-3)
    aliases = report["ports"]["alias_groups"]
    alias_complete = len([entry for entries in aliases.values() for entry in entries]) == report["ports"]["mode_count"]
    alias_complete = alias_complete and all(aliases[str(i)] for i in range(report["layout"]["ny"]))
    ns = {entry["n"] for entry in aliases["1"]}
    alias_complete = alias_complete and {1, -3}.issubset(ns)
    # Native form-action residuals are live authority, not independently reproducible from NPY.
    live_native = all(packet["full_original_true_residual"] <= 1e-10
                      for group in (report["regular_sources"], report["notched_sources"]) for packet in group.values())
    port_symmetry = max(report["ports"][key] for key in (
        "coupling_off_q_relative_max", "projection_off_q_relative_max",
        "augmented_C_covariance_relative_max", "augmented_D_covariance_relative_max")) <= 1e-11
    physical_modal = np.asarray(fourier.conj().T @ (r_inverse @ load("notch_iterative_physical"))).reshape(report["layout"]["ny"], report["layout"]["rows_per_q"])
    physical_q_relative = float(np.linalg.norm(physical_modal[1:]) / np.linalg.norm(physical_modal))
    physical_q = physical_q_relative > 1e-12
    live_augmented = all(max(packet["augmented_FE_true_residual"], packet["augmented_port_closure_relative"],
                             packet["augmented_vs_original_residual_relative"]) <= 1e-10
                         for group in (report["regular_sources"], report["notched_sources"]) for packet in group.values())
    return {"schema": "task40extra.y-orbit-checker.v1", "evidence_valid": True,
            "gate_pass": bool(all(item["pass"] for item in checks) and all_q and alias_complete and live_native and port_symmetry and physical_q and live_augmented),
            "checks": checks, "generic_all_q_excitation": all_q, "all_port_aliases_retained": alias_complete,
            "live_native_residual_authority_present": live_native, "live_port_symmetry": port_symmetry,
            "notch_physical_nonzero_q_content": physical_q,
            "notch_physical_nonzero_q_relative_recomputed": physical_q_relative,
            "live_augmented_residual_authority": live_augmented,
            "resource_authority": "separate existing whole-tree watchdog, must be reviewed independently",
            "qualification": "small full3D algebra architecture only, not target field/accuracy/memory"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--expected-checker-head")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.run_directory = args.run_directory.resolve()
    report = json.loads((args.run_directory/"pilot_report.json").read_text())
    if report.get("dtn_phase_gauge") == "boundary_plane":
        from benchmarks.run_real_p4_probe import source_facts, environment_facts
        from src.solvers.real_p4_probe import file_sha256
        if not args.expected_checker_head:
            parser.error("centered authority checker requires the exact clean frozen HEAD")
        root = Path(__file__).resolve().parents[1]/"benchmarks/artifacts/task40extra_dot_parallel_cloud"
        if not args.run_directory.is_relative_to(root):
            parser.error("centered checker requires own ignored artifact directory")
        source, environment = source_facts(args.expected_checker_head), environment_facts()
        if not args.worker:
            from benchmarks.subreaper_watchdog import supervise
            d = args.run_directory/"checker_supervision"
            summary = supervise([sys.executable,"-m","benchmarks.check_y_orbit_reference_probe",str(args.run_directory),
               "--expected-checker-head",args.expected_checker_head,"--worker"],d,wall_seconds=600,interval=.25,
               grace_seconds=2,source_state=source,phase_path=d/"phase.json",tree_cap_bytes=3*1024**3//2,
               hard_stop_immediate=True,timebase_guard=True,stop_on_global_swap=True,pss_sampling_policy="disabled_by_profile")
            path = args.run_directory/"independent_checker.json"
            if not path.is_file(): return 2
            result = json.loads(path.read_text())
            result["checker_watchdog_receipt"]={"path":"checker_supervision/summary.json","sha256":file_sha256(d/"summary.json")}
            result["gate_pass"] = bool(result.get("gate_pass") is True and summary["classification"]=="COMPLETED"
               and summary.get("sampled_process_tree_swap_peak_bytes")==0 and summary.get("descendants_cleared") is True
               and summary.get("process_tree_all_identity_complete") is True and summary.get("process_tree_all_status_readable") is True
               and source_facts(args.expected_checker_head)==source)
            path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
            return 0 if result["gate_pass"] else 2
        parent=int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID","0"))
        if parent <= 0 or parent != os.getppid() or not 0 < int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES","0")) <=3*1024**3//2:
            raise RuntimeError("centered checker needs its own admitted watchdog")
        try:
            result=check_centered(args.run_directory,source=source,environment=environment)
            if source_facts(args.expected_checker_head)!=source: raise RuntimeError("checker source changed")
        except Exception as exc:
            result={"evidence_valid":False,"gate_pass":False,"error_type":type(exc).__name__,"error":str(exc)}
        (args.run_directory/"independent_checker.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
        return 0 if result["gate_pass"] else 2
    try:
        result = check(args.run_directory.resolve())
    except Exception as exc:
        result = {"evidence_valid": False, "gate_pass": False, "error_type": type(exc).__name__, "error": str(exc)}
    (args.run_directory / "independent_checker.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
