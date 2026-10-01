"""Independent hash-bound checker for saved original actions and sparse blocks.

Does not solve or rebuild FFCx. Original action-vector artifacts are live FE
authority; this checker independently recomputes their full residuals/augmented
identities and streamed all-q congruence. p4 has no global direct control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
from scipy import sparse


def _complete_interior_rhs(generic, interior_positions, expected_rows):
    return bool(len(interior_positions) == int(expected_rows)
                and np.linalg.norm(generic[interior_positions]) > 0)


def _bind_worker_dependencies(worker_source, checker_source):
    """Only the reviewed checker/serialization-test edit may differ.

    Every other tracked source/config/input/runner dependency in source_facts
    must have exactly the worker's byte identity, including added/deleted paths.
    The numerical worker HEAD remains historical; the checker has its own HEAD.
    """
    allowed = {"benchmarks/check_y_orbit_sparse_probe.py",
               "src/test/test_y_orbit_sparse_diagnostic_inventory.py"}
    old, new = worker_source["files_sha256"], checker_source["files_sha256"]
    changed = {path for path in set(old) | set(new) if old.get(path) != new.get(path)}
    if (worker_source["branch"] != checker_source["branch"] or worker_source["dirty"]
            or checker_source["dirty"] or not changed.issubset(allowed)):
        raise RuntimeError("checker requires byte-identical numerical/config dependencies")
    return {"worker_head": worker_source["head"], "checker_head": checker_source["head"],
            "verified_unchanged_dependency_count": len((set(old) | set(new)) - allowed),
            "reviewed_changed_paths": sorted(changed),
            "exception_scope": "only checker serialization/binding code and its own regression test",
            "all_other_source_config_input_hashes_match": True}


def _raw_factor_inventory(report, directory, ny):
    """Require every reviewed input/output vector, not vacuous all(empty)."""
    expected = {f"q_{q}_{name}" for q in range(ny)
                for name in ("rhs_a", "rhs_b", "solution_a", "solution_b", "solution_a_repeat", "solution_sum")}
    inventory = report.get("factor_raw_diagnostics", {})
    if set(inventory) != expected:
        raise ValueError("complete expected raw factor vector inventory is required")
    rows = {int(block["q"]): int(block["shape"][0]) for block in report["reference_factor"]["input_blocks"]}
    finite = True
    for name, descriptor in inventory.items():
        path = (directory / descriptor["path"]).resolve()
        if not path.is_relative_to(directory) or hashlib.sha256(path.read_bytes()).hexdigest() != descriptor["file_sha256"]:
            raise ValueError("raw factor diagnostic identity mismatch")
        values = np.load(path, allow_pickle=False)
        q = int(name.split("_")[1])
        if values.shape != (rows[q],) or values.dtype != np.dtype(np.complex128) or values.size > 65536:
            raise ValueError("raw factor diagnostic shape/dtype/bound differs")
        count = int(np.count_nonzero(np.isfinite(values)))
        if descriptor["finite_entries"] != count or descriptor["nonfinite_entries"] != values.size - count:
            raise ValueError("raw finite/nonfinite diagnostic counts differ")
        finite = finite and count == values.size
    return finite


def check(directory, *, checker_source, checker_environment):
    directory = Path(directory).resolve()
    report = json.loads((directory / "probe_report.json").read_text())
    provenance = json.loads((directory / "provenance.json").read_text())
    summary = json.loads((directory / "summary.json").read_text())
    if (report.get("status") != "SPARSE_CONDENSED_FULL3D_PROBE_PASS"
            or report.get("source_clean_unchanged") is not True
            or report["source"] != provenance["source"]
            or summary.get("classification") != "COMPLETED"):
        return {"gate_pass": False, "evidence_valid": False, "reason": "incomplete source/run authority"}
    source_binding = _bind_worker_dependencies(report["source"], checker_source)
    if checker_environment != report["environment"]:
        raise RuntimeError("checker ABI/config environment differs from the numerical worker")
    source_binding["worker_and_checker_ABI_manifest_sha256"] = checker_environment["qualification_manifest_sha256"]
    centered = report.get("dtn_phase_gauge", "global_z") == "boundary_plane"
    centered_authority = None
    if centered:
        from benchmarks.run_y_orbit_sparse_probe import ROOT, SavedCenteredDenseP2Authority
        from src.solvers.y_orbit_centered_evidence import COMPONENT_IDENTITY, SOURCES
        receipt = provenance["saved_dense_p2_authority"]
        centered_authority = SavedCenteredDenseP2Authority(ROOT/receipt["report_path"],receipt["report_sha256"],
                                                          report["source"],report["environment"])
        if (report["degree"] != 2 or report["auxiliary_gauge"] != "positive-h"
                or set(report["regular_sources"]) != set(SOURCES) or set(report["notched_sources"]) != set(SOURCES)
                or report["centered_identity"] != centered_authority.report["identity"]
                or any(report["centered_identity"].get(k) != v for k,v in COMPONENT_IDENTITY.items())):
            raise ValueError("centered sparse/authority/source/load representation identity differs")
    checks = []
    descriptors = report["artifacts"]
    report_sha = hashlib.sha256((directory / "probe_report.json").read_bytes()).hexdigest()
    provenance_sha = hashlib.sha256((directory / "provenance.json").read_bytes()).hexdigest()
    artifact_sha = hashlib.sha256(json.dumps(descriptors, sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()

    def load(name):
        descriptor = descriptors[name]
        path = (directory / descriptor["path"]).resolve()
        if not path.is_relative_to(directory):
            raise ValueError("artifact escapes run directory")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != descriptor["file_sha256"]:
            raise ValueError("artifact hash mismatch: " + name)
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if list(value.shape) != descriptor["shape"] or str(value.dtype) != descriptor["dtype"]:
            raise ValueError("artifact descriptor mismatch: " + name)
        if value.dtype.hasobject or (value.dtype.kind in "fc" and not np.isfinite(value).all()):
            raise ValueError("invalid nonfinite/object artifact")
        return value

    def add(name, measured, limit):
        checks.append({"name": name, "measured": float(measured), "limit": float(limit),
                       "passed": bool(np.isfinite(measured) and measured <= limit)})

    # Verify the complete descriptor inventory, including diagnostics that are
    # not independently acted on below. The manifest binding cannot conceal a
    # substituted unused file.
    for name in descriptors:
        values = load(name)
        del values

    def relative(values, scale):
        return float(np.linalg.norm(values) / max(np.linalg.norm(scale), np.finfo(float).tiny))

    def csr(prefix, shape):
        return sparse.csr_matrix((load(prefix + "_data"), load(prefix + "_indices"),
                                  load(prefix + "_indptr")), shape=shape, copy=False)

    full_n = int(report["layout"]["independent_rows"])
    ny = int(report["layout"]["ny"])
    full_width = int(report["layout"]["rows_per_q"])
    trace_audit = report["coordinates"]["trace"]
    trace_n = int(trace_audit["complete_trace_rows"])
    trace_width = trace_n // ny
    ports = int(report["coordinates"]["ports"]["mode_count"])
    port_scale = load("port_factor_coordinate_scale")
    original_h = load("port_original_H")
    if not np.isfinite(original_h).all() or np.any(original_h <= 0):
        raise ValueError("positive original H identity lost")
    expected_scale = 1 / np.sqrt(original_h) if report["auxiliary_gauge"] == "positive-h" else np.ones(ports)
    add("exact_original_H_coordinate_scale", relative(port_scale - expected_scale, expected_scale), 1e-12)
    independent = load("independent_storage_rows")
    ri = csr("full_R_inverse", (full_n, full_n))
    f = csr("full_F", (full_n, full_n))
    q = csr("full_Q", (full_n, full_n))
    rt = csr("trace_R_t", (trace_n, trace_n))
    ft = csr("trace_F_t", (trace_n, trace_n))
    qt = (rt @ ft).tocsr()
    generic = load("generic_rhs")
    modal = np.asarray(q.conj().T @ generic).reshape(ny, full_width)
    norms = np.linalg.norm(modal, axis=1)
    all_q_excitation = bool(np.min(norms) / np.linalg.norm(norms) >= 1e-3)
    native_trace_positions = load("trace_full_independent_trace_positions")
    interior_positions = np.setdiff1d(np.arange(full_n), native_trace_positions)
    complete_interiors = _complete_interior_rhs(generic, interior_positions, trace_audit["complete_interior_rows"])
    slave_zero = True
    centered_mode_checks = {}
    optional_global_outputs = {}

    for prefix, sources in (("regular", report["regular_sources"]), ("notch", report["notched_sources"])):
        for name in sources:
            label = prefix + "_" + name
            rhs = load(label + "_rhs_storage")
            field = load(label + "_solution_storage")
            slaves = np.setdiff1d(np.arange(len(field)), independent)
            slave_zero = slave_zero and bool(np.all(field[slaves] == 0))
            action = load(label + "_original_action")
            volume = load(label + "_volume_action")
            coupling = load(label + "_coupling_action")
            alpha = load(label + "_auxiliary_ports")
            projection = load(label + "_projection")
            h = load(label + "_normalization_h")
            native_residual = rhs - action
            top_residual = rhs - volume - coupling
            port_residual = projection - h * alpha
            add(label + "_full_original_residual", relative(native_residual, rhs), 1e-10)
            add(label + "_augmented_FE_residual", relative(top_residual, rhs), 1e-10)
            add(label + "_port_closure", np.linalg.norm(port_residual) /
                max(np.linalg.norm(projection) + np.linalg.norm(h * alpha), np.finfo(float).tiny), 1e-10)
            add(label + "_native_residual_record", relative(native_residual - load(label + "_native_residual"), rhs), 1e-12)
            add(label + "_augmented_residual_record", relative(top_residual - load(label + "_augmented_FE_residual"), rhs), 1e-12)
            add(label + "_port_residual_record", relative(port_residual - load(label + "_augmented_port_residual"), projection), 1e-12)
            active = field[independent]
            modal = np.asarray(f.conj().T @ (ri @ active)).reshape(ny, full_width)
            computed_q_norms = np.linalg.norm(modal, axis=1)
            add(label + "_full_primal_q_norms_record", relative(computed_q_norms - sources[name]["solution_primal_q_norms"], computed_q_norms), 1e-12)
            if prefix == "notch" and name == "physical":
                physical_q_relative = float(np.linalg.norm(computed_q_norms[1:]) / np.linalg.norm(computed_q_norms))
            if report["degree"] == 2 and (centered or name in ("generic", "physical")):
                # Frozen old authority is separately content-bound by the runner.
                add(label + "_saved_dense_direct_difference_live", sources[name]["saved_dense_direct_difference"], 1e-9)
            if centered:
                from src.solvers.y_orbit_centered_evidence import compare_mode_evidence, bind_native_packet
                authority_name = ("A0_direct_" if prefix == "regular" else "notch_direct_")+name
                direct = centered_authority.load(authority_name)
                bind_native_packet(field,rhs,load(label+"_solution"),load(name+"_rhs"),independent)
                if not np.array_equal(load("actual_interior_positions"),interior_positions):
                    raise ValueError("centered full native packet detached from actual solver/RHS/interior inventory")
                matrix = centered_authority.load("A0_original" if prefix == "regular" else "A_notch_original")
                add(label+"_fresh_dense_original_residual",relative(rhs[independent]-matrix@active,rhs[independent]),1e-10)
                add(label+"_native_action_bound_to_fresh_dense_matrix",relative(action[independent]-matrix@active,rhs[independent]),1e-11)
                add(label+"_fresh_dense_direct_difference",relative(active-direct,direct),1e-9)
                dense_label = "direct_"+label
                add(label+"_fresh_dense_recovered_field_difference",relative(load(label+"_recovered_field")-
                     centered_authority.load(dense_label+"_recovered_field"),centered_authority.load(dense_label+"_recovered_field")),1e-9)
                centered_mode_checks[label] = compare_mode_evidence(load,
                    lambda key: centered_authority.load("direct_"+key),label)
                coefficients, offsets = load("full_mpc_coefficients"),load("full_mpc_offsets")
                masters, saved_slaves = load("full_mpc_masters"),load("full_mpc_slaves")
                if (offsets.shape != (len(field)+1,) or int(offsets[-1]) != len(coefficients)
                        or offsets.dtype.kind not in "iu" or masters.dtype.kind not in "iu" or saved_slaves.dtype.kind not in "iu"
                        or len(masters)!=len(coefficients) or not np.array_equal(slaves,np.sort(saved_slaves))
                        or np.any(offsets[1:]<offsets[:-1]) or len(np.intersect1d(saved_slaves,masters))
                        or (masters.size and (masters.min()<0 or masters.max()>=len(field)))):
                    raise ValueError("centered actual finalized MPC recovery inventory differs")
                backsub = field.copy()
                for slave in saved_slaves:
                    begin,end = int(offsets[slave]),int(offsets[slave+1])
                    if end <= begin: raise ValueError("centered MPC slave expansion empty")
                    backsub[slave] = np.dot(coefficients[begin:end],field[masters[begin:end]])
                add(label+"_independent_actual_MPC_backsubstitution",relative(load(label+"_recovered_field")-backsub,backsub),1e-12)
                amplitude_error = np.abs(load(label+"_plane_total_auxiliary")-alpha)
                amplitude_scale = load(label+"_mode_local_amplitude_scale")
                if np.any((amplitude_scale == 0)&(amplitude_error != 0)):
                    raise ValueError("nonzero original alpha recovery error has zero local scale")
                amplitude_ratios = np.divide(amplitude_error,amplitude_scale,out=np.zeros_like(amplitude_error),where=amplitude_scale != 0)
                add(label+"_mode_recovery_vs_original_alpha",np.max(amplitude_ratios),1e-10)
                optional_global_outputs[label] = sources[name]["outputs"]["status"]
                if (sources[name]["outputs"].get("finite_plane_mode_count") != ports
                        or sources[name]["outputs"].get("status") != "representable_global_output"
                        or sources[name]["outputs"].get("global_output_component_consistency_checked") is not True):
                    raise ValueError("complete required centered finite-plane mode output missing")
            add(label + "_augmented_identity_live", sources[name]["augmented_residual_identity"]["relative"], 1e-10)
            if len(alpha) != ports or len(projection) != ports or len(h) != ports:
                raise ValueError("full port inventory missing from original residual vectors")

    original = csr("reference_S", (trace_n + ports, trace_n + ports))
    port_q = load("port_q_labels")
    aliases = [np.flatnonzero(port_q == j) for j in range(ny)]
    if len(port_q) != ports or not all(len(v) for v in aliases):
        raise ValueError("all physical aliases/all q must survive")

    def q_map(j):
        port_map = sparse.csr_matrix((port_scale[aliases[j]].astype(complex),
                                     (aliases[j], np.arange(len(aliases[j])))), shape=(ports, len(aliases[j])))
        return sparse.block_diag((qt[:, j * trace_width:(j + 1) * trace_width], port_map), format="csr")

    diagonal_sq = off_sq = 0.0
    pair_norms = {}
    for j in range(ny):
        right = q_map(j)
        product = original @ right
        for i in range(ny):
            block = q_map(i).conj().T @ product
            norm_sq = float(np.vdot(block.data, block.data).real)
            pair_norms[i, j] = float(np.sqrt(norm_sq))
            if i == j:
                diagonal_sq += norm_sq
                expected = csr(f"q_{j}_S", block.shape)
                add(f"q_{j}_diagonal_block_record", sparse.linalg.norm(block - expected) /
                    max(sparse.linalg.norm(block), np.finfo(float).tiny), 1e-12)
            else:
                off_sq += norm_sq
            del block
        del product, right
    add("complete_augmented_modal_off_block", np.sqrt(off_sq / max(off_sq + diagonal_sq, np.finfo(float).tiny)), 1e-11)
    for (i, j), value in pair_norms.items():
        if i != j:
            if min(pair_norms[i, i], pair_norms[j, j]) == 0:
                raise ValueError("zero diagonal q block cannot be omitted")
            add(f"off_block_{i}_{j}_relative_to_both_diagonals",
                max(value / pair_norms[i, i], value / pair_norms[j, j]), 1e-11)
    t_trace = csr("trace_native_trace_translation", (trace_n, trace_n))
    eta = load("port_eta")
    phase = complex(*report["layout"]["phase_y"])
    add("actual_port_translation_cycle", relative(eta**ny - phase, np.ones_like(eta)), 1e-11)
    nonzero_wrap = report["azimuth_deg"] == 5.0 and abs(phase - 1) >= 1e-3
    ta = sparse.block_diag((t_trace, sparse.diags(eta)), format="csr")
    add("native_augmented_form_covariance", sparse.linalg.norm(ta.conj().T @ original @ ta - original) /
        max(sparse.linalg.norm(original), np.finfo(float).tiny), 1e-11)
    rti = csr("trace_R_t_inverse", (trace_n, trace_n))
    for j in range(ny):
        for label in ("a", "b"):
            prefix = f"q_{j}_manufactured_{label}_"
            modal_load = load(prefix + "complete_modal_load")
            native_rhs = load(prefix + "native_rhs")
            native_solution = load(prefix + "native_solution")
            action = np.asarray(original @ native_solution)
            rhs_from_inverse_dual = np.empty_like(modal_load)
            rhs_from_inverse_dual[:trace_n] = rti.conj().T @ (ft @ modal_load[:trace_n])
            rhs_from_inverse_dual[trace_n:] = modal_load[trace_n:] / port_scale
            add(f"q_{j}_{label}_P_inverse_H_complete_load_map", relative(rhs_from_inverse_dual - native_rhs, native_rhs), 1e-12)
            add(f"q_{j}_{label}_ORIGINAL_S_manufactured_residual", relative(action - native_rhs, native_rhs), 1e-10)
            add(f"q_{j}_{label}_original_S_action_record", relative(action - load(prefix + "original_S_action"), native_rhs), 1e-12)
    full_ports = report["coordinates"]["ports"]
    keys = [tuple(key) for key in report["mode_keys"]]
    alias_inventory = sorted((entry for group in full_ports["alias_groups"].values() for entry in group), key=lambda entry: entry["index"])
    alias_keys = [(str(e["side"]), int(e["m"]), int(e["n"]), str(e["polarization"])) for e in alias_inventory]
    exact_ports = (keys == alias_keys and len(set(keys)) == ports
                   and full_ports["production_generator_ordered_keys_match"] is True
                   and [len(v) for v in aliases] == report["coordinates"]["alias_counts"]
                   and {1, -3}.issubset({keys[i][2] for i in aliases[1]}))
    resource = (summary.get("sampled_process_tree_swap_peak_bytes") == 0
                and summary.get("process_tree_all_status_readable") is True
                and summary.get("process_tree_all_identity_complete") is True
                and summary.get("descendants_cleared") is True
                and 0 < summary["sampled_process_tree_rss_peak_bytes"] < provenance["resource_contract"]["tree_cap_bytes"]
                and provenance["resource_contract"]["tree_cap_bytes"] <= 3 * 1024**3 // 2)
    live_symmetry = max(report["full_form_covariance"]["full_original_covariance_action_relative_max"],
                        report["complete_RHS_covariance"]["complete_RHS_reduction_covariance_relative_max"]) <= 1e-11
    notch_coupling = report["sampled_notch_off_q_delta_relative"] >= 1e-8
    factor_audits = report["reference_factor"]["input_blocks"]
    factor_valid = (len(factor_audits) == ny
                    and all(max(item["repeated_solve_relative"], item["linearity_relative"]) <= 1e-11
                            and item["block_true_residual_relative_max"] <= 1e-10 for item in factor_audits))
    raw_finite = _raw_factor_inventory(report, directory, ny)
    centered_outputs = True
    if centered:
        centered_outputs = all(item["passed"] for group in centered_mode_checks.values() for item in group.values())
        nonzero_interior = np.flatnonzero(load("interior_only_rhs"))
        complete_interiors = complete_interiors and np.array_equal(nonzero_interior,interior_positions)
    return {"schema": "task40extra.y-orbit-sparse-checker.v1", "evidence_valid": True,
            "report_sha256": report_sha, "provenance_sha256": provenance_sha,
            "artifact_manifest_sha256": artifact_sha, "source": report["source"], "degree": report["degree"],
            "checker_source": checker_source, "worker_dependency_binding": source_binding,
            "gate_pass": bool(all(item["passed"] for item in checks) and all_q_excitation
                              and complete_interiors and exact_ports and resource and live_symmetry
                              and notch_coupling and factor_valid and raw_finite and slave_zero and nonzero_wrap
                              and physical_q_relative > 1e-12 and centered_outputs),
            "checks": checks, "generic_all_q_excitation": all_q_excitation,
            "complete_original_interior_RHS": complete_interiors, "all_physical_alias_keys": exact_ports,
            "physical_notch_nonzero_q_relative": physical_q_relative,
            "sampled_notch_cross_q_gate": notch_coupling, "live_full_symmetry_gate": live_symmetry,
            "actual_q_factor_repeated_linear_residual_gates": factor_valid,
            "factor_raw_vectors_finite": raw_finite, "auxiliary_gauge": report["auxiliary_gauge"],
            "representation": report["reference_scope"],
            "upstream_clipped_functionals_restored": centered,
            "centered_per_mode_output_checks": centered_mode_checks,
            "optional_global_output_statuses": optional_global_outputs,
            "centered_fresh_dense_authority_verified": centered_authority is not None,
            "original_full_slave_zeros": slave_zero, "nontrivial_real_ky_wrap": nonzero_wrap,
            "original_FFCx_action_is_saved_live_authority": True,
            "full_p4_direct_control": "not_run_not_admitted" if report["degree"] == 4 else "saved_p2",
            "resource_requires_separate_whole_tree_review": True,
            "qualification": "bounded full3D architecture/degree probe only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-checker-head", required=True)
    parser.add_argument("--checker-attempt", type=int, default=1)
    args = parser.parse_args()
    args.run_directory = args.run_directory.resolve()
    artifact_root = Path(__file__).resolve().parents[1] / "benchmarks/artifacts/task40extra_dot_parallel_cloud"
    if not args.run_directory.is_relative_to(artifact_root):
        parser.error("checker evidence must remain in the own ignored artifact subtree")
    if not 1 <= args.checker_attempt <= 99:
        parser.error("checker attempt must be1..99; each attempt uses a fresh directory")
    if not args.worker:
        from benchmarks.run_real_p4_probe import source_facts, environment_facts
        from benchmarks.subreaper_watchdog import supervise
        from src.solvers.real_p4_probe import file_sha256
        report = json.loads((args.run_directory / "probe_report.json").read_text())
        source = source_facts(args.expected_checker_head)
        _bind_worker_dependencies(report["source"], source)
        if environment_facts() != report["environment"]:
            raise RuntimeError("checker environment must match worker ABI exactly")
        dirname = "checker_supervision" if args.checker_attempt == 1 else f"checker_supervision_attempt{args.checker_attempt}"
        checker_directory = args.run_directory / dirname
        command = [sys.executable, "-m", "benchmarks.check_y_orbit_sparse_probe", str(args.run_directory), "--worker",
                   "--expected-checker-head", args.expected_checker_head, "--checker-attempt", str(args.checker_attempt)]
        summary = supervise(command, checker_directory, wall_seconds=600, interval=.25, grace_seconds=2,
                            source_state=source, phase_path=checker_directory / "phase.json",
                            tree_cap_bytes=3 * 1024**3 // 2, hard_stop_immediate=True,
                            timebase_guard=True, stop_on_global_swap=True,
                            pss_sampling_policy="disabled_by_profile")
        path = args.run_directory / "independent_checker.json"
        if not path.exists():
            return 2
        result = json.loads(path.read_text())
        result["checker_watchdog_receipt"] = {"path": dirname + "/summary.json",
                                              "sha256": file_sha256(checker_directory / "summary.json")}
        result["gate_pass"] = (result.get("gate_pass") is True and summary["classification"] == "COMPLETED"
                               and summary.get("sampled_process_tree_swap_peak_bytes") == 0
                               and summary.get("process_tree_all_status_readable") is True
                               and summary.get("process_tree_all_identity_complete") is True
                               and summary.get("descendants_cleared") is True
                               and source_facts(args.expected_checker_head) == source)
        path.write_text(json.dumps(result, allow_nan=False, indent=2) + "\n")
        print(json.dumps(result, allow_nan=False, indent=2))
        return 0 if result["gate_pass"] else 2
    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    cap = int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "0"))
    if parent <= 0 or parent != os.getppid() or not 0 < cap <= 3 * 1024**3 // 2:
        raise RuntimeError("checker worker needs its separately admitted watchdog")
    try:
        from benchmarks.run_real_p4_probe import source_facts, environment_facts
        checker_source = source_facts(args.expected_checker_head)
        result = check(args.run_directory, checker_source=checker_source, checker_environment=environment_facts())
        if source_facts(args.expected_checker_head) != checker_source:
            raise RuntimeError("checker source changed during artifact verification")
    except Exception as exc:
        result = {"evidence_valid": False, "gate_pass": False, "error_type": type(exc).__name__, "error": str(exc)}
    (args.run_directory / "independent_checker.json").write_text(json.dumps(result, allow_nan=False, indent=2) + "\n")
    print(json.dumps(result, allow_nan=False, indent=2))
    return 0 if result["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
