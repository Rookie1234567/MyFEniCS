"""Opt-in scale-homogeneous cutoff replay of the frozen V4 saved-field worker.

The wrapper reuses V4's saved-field reconstruction and q28 integration path,
but scopes the candidate cutoff helpers to the capture call only.  It never
builds a carrier/action, global matrix, factor, or solve.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = Path(__file__).resolve().parent
BASE_WORKER = SCRIPTS / "d13_saved_field_cutoff_stage_worker.py"
BASE_SUPERVISOR = SCRIPTS / "d13_saved_field_cutoff_stage_supervisor.py"
ACCOUNTING = SCRIPTS / "d13_scale_homogeneous_cutoff_accounting.py"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(SCRIPTS))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load bound Python module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decode_complex(value: Any) -> complex:
    if isinstance(value, dict) and {"real", "imag"}.issubset(value):
        return complex(float(value["real"]), float(value["imag"]))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    if isinstance(value, (int, float)):
        return complex(value)
    raise ValueError(f"unsupported serialized complex scalar: {type(value).__name__}")


def _complex_json(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _verify_candidate_contract(
    contract_path: Path,
    contract: dict[str, Any],
    *,
    require_execution_authorized: bool = True,
) -> dict[str, Any]:
    if contract.get("schema") != "task40.d13.cutoff-stage-signed-key-contract.v2":
        raise ValueError("candidate must retain the frozen V4 saved-field input contract")
    candidate = contract.get("scale_homogeneous_candidate")
    if not isinstance(candidate, dict):
        raise TypeError("contract lacks the explicit scale-homogeneous candidate opt-in")
    if candidate.get("enabled") is not True or candidate.get("relative_tolerance") != 1.0e-13:
        raise ValueError("candidate opt-in must preserve the frozen relative tolerance")
    if candidate.get("absolute_floor") is not None:
        raise ValueError("candidate must remove the absolute-floor influence")
    if candidate.get("qualification") != "NO_CARRIER_COMPARISON_NOT_SOLVER_QUALIFICATION":
        raise ValueError("candidate must remain explicitly unqualified")
    if require_execution_authorized and contract.get("execution_authorized") is not True:
        raise PermissionError("candidate package is review-only and is not authorized to execute")
    if contract.get("analysis_source_head") != subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout.strip():
        raise ValueError("Task40 base HEAD differs from the frozen candidate contract")
    worker_hash = _sha256(Path(__file__).resolve())
    if worker_hash != contract.get("candidate_worker_script_sha256"):
        raise ValueError("scale-homogeneous candidate worker SHA differs from contract")
    supervisor_hash = _sha256(SCRIPTS / "d13_saved_field_scale_homogeneous_supervisor.py")
    if supervisor_hash != contract.get("candidate_supervisor_script_sha256"):
        raise ValueError("scale-homogeneous candidate supervisor SHA differs from contract")
    accounting_hash = _sha256(ACCOUNTING)
    if accounting_hash != contract.get("candidate_accounting_script_sha256"):
        raise ValueError("scale-homogeneous accounting SHA differs from contract")
    if _sha256(BASE_WORKER) != contract.get("worker_script_sha256"):
        raise ValueError("frozen V4 base worker SHA differs from contract")
    if _sha256(BASE_SUPERVISOR) != contract.get("supervisor_script_sha256"):
        raise ValueError("frozen V4 base supervisor SHA differs from contract")
    for name in ("frozen_v4_report", "v4_postprocess_correction"):
        binding = candidate.get(name)
        if not isinstance(binding, dict):
            raise TypeError(f"candidate contract lacks {name} identity")
        path = Path(binding["path"]).resolve()
        if not path.is_file() or _sha256(path) != binding.get("sha256"):
            raise ValueError(f"candidate input evidence changed: {name}")
    source_files = contract.get("analysis_source_file_sha256")
    if not isinstance(source_files, dict) or not source_files:
        raise ValueError("candidate contract lacks source file identities")
    observed = {}
    for relative, expected in source_files.items():
        path = (REPO / relative).resolve()
        if REPO not in path.parents or not path.is_file():
            raise ValueError(f"candidate source path is absent or outside worktree: {relative}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"candidate source hash changed: {relative}")
        observed[relative] = actual
    return {
        "analysis_source_head": contract["analysis_source_head"],
        "candidate_worker_script_sha256": worker_hash,
        "candidate_supervisor_script_sha256": supervisor_hash,
        "candidate_accounting_script_sha256": accounting_hash,
        "base_v4_worker_script_sha256": contract["worker_script_sha256"],
        "base_v4_supervisor_script_sha256": contract["supervisor_script_sha256"],
        "analysis_source_file_sha256": observed,
        "frozen_v4_report_sha256": candidate["frozen_v4_report"]["sha256"],
        "v4_postprocess_correction_sha256": candidate["v4_postprocess_correction"]["sha256"],
    }


def _candidate_capture(base_worker, **kwargs):
    """Invoke the original V4 capture with both actual helpers opt-in enabled."""
    import d13_cutoff_stage_accounting as legacy_accounting

    import src.solvers.dtn_port_3d as dtn_port

    candidate_accounting = _load_module("task40_scale_homogeneous_accounting", ACCOUNTING)
    saved_cutoff_names = {
        "ABSOLUTE_FLOOR": legacy_accounting.ABSOLUTE_FLOOR,
        "cutoff_facts": legacy_accounting.cutoff_facts,
        "expected_component_filter": legacy_accounting.expected_component_filter,
        "expected_merged_filter": legacy_accounting.expected_merged_filter,
        "route_cutoff_accounting": legacy_accounting.route_cutoff_accounting,
    }
    saved_vec = dtn_port._vec_nonzero_owned_entries
    saved_combine = dtn_port._combine_owned_entries

    def candidate_vec(vec, **options):
        if options.get("scale_homogeneous", False):
            raise RuntimeError("candidate wrapper owns the only scale-homogeneous opt-in")
        options["scale_homogeneous"] = True
        return saved_vec(vec, **options)

    def candidate_combine(component_entries, coefficients, **options):
        if options.get("scale_homogeneous", False):
            raise RuntimeError("candidate wrapper owns the only scale-homogeneous opt-in")
        options["scale_homogeneous"] = True
        return saved_combine(component_entries, coefficients, **options)

    try:
        legacy_accounting.ABSOLUTE_FLOOR = None
        legacy_accounting.cutoff_facts = candidate_accounting.relative_cutoff_facts
        legacy_accounting.expected_component_filter = candidate_accounting.expected_component_filter
        legacy_accounting.expected_merged_filter = candidate_accounting.expected_merged_filter
        legacy_accounting.route_cutoff_accounting = candidate_accounting.route_cutoff_accounting
        dtn_port._vec_nonzero_owned_entries = candidate_vec
        dtn_port._combine_owned_entries = candidate_combine
        result = base_worker._cutoff_stage_capture(**kwargs)
    finally:
        dtn_port._vec_nonzero_owned_entries = saved_vec
        dtn_port._combine_owned_entries = saved_combine
        for name, value in saved_cutoff_names.items():
            setattr(legacy_accounting, name, value)

    result["candidate_policy"] = {
        "name": "scale_homogeneous_relative_only_v1",
        "relative_tolerance": 1.0e-13,
        "absolute_floor": None,
        "absolute_floor_influences_rowset": False,
        "zero_vector_policy": "empty_rowset",
        "nonfinite_or_magnitude_overflow": "reject_collectively",
        "merge_product_underflow_to_zero": "reject_collectively",
        "normalized_ratio_underflow": "discarded only below positive relative tolerance",
        "subnormal_nonzero_products": "retained as stored IEEE-754 values; reported scale/terms expose precision limits",
        "global_maximum": "same owned/global MPI.MAX semantics as the production helper",
        "row_order_mpc_conjugation": "unchanged production ordering, support, and route conjugation",
        "qualification": "NO_CARRIER_COMPARISON_NOT_SOLVER_QUALIFICATION",
    }
    result["candidate_cutoff_policy"] = {
        "relative_tolerance": 1.0e-13,
        "absolute_floor": None,
        "strict_keep_rule": "abs(value)/global_maximum > 1e-13; zero global maximum produces an empty rowset",
        "status": "EXPLICIT_DIAGNOSTIC_CANDIDATE_ONLY; legacy default remains unchanged",
    }
    result.pop("unchanged_production_cutoff", None)
    for key_result in result.get("six_exact_signed_key_results", []):
        component_records = key_result.pop("component_stage_records")
        for record in component_records:
            for old_name, new_name in (
                ("production_rows_values_sha256", "candidate_rows_values_sha256"),
                (
                    "production_matches_independent_stage1_mask_elementwise",
                    "candidate_matches_independent_stage1_mask_elementwise",
                ),
                ("production_entry_count", "candidate_entry_count"),
                ("production_nonzero_count", "candidate_nonzero_count"),
                (
                    "production_largest_entries_bounded_sample",
                    "candidate_largest_entries_bounded_sample",
                ),
            ):
                if old_name in record:
                    record[new_name] = record.pop(old_name)
        key_result["candidate_component_stage_records"] = component_records
        key_result["candidate_scale_homogeneous_stage_two_routes"] = key_result.pop(
            "production_stage_two_routes"
        )
        for route in key_result["candidate_scale_homogeneous_stage_two_routes"].values():
            for old_name, new_name in (
                ("after_production_merged_cutoff_dot_complex", "after_candidate_merged_cutoff_dot_complex"),
                ("stage2_rows_values_match_production_elementwise", "candidate_matches_independent_stage2_mask_elementwise"),
                ("stage2_actual_row_count", "candidate_stage2_row_count"),
                ("stage2_actual_rows_values_sha256", "candidate_stage2_rows_values_sha256"),
            ):
                if old_name in route:
                    route[new_name] = route.pop(old_name)
            route.pop("closure_passed", None)
            route["closure_is_qualification_gate"] = False
    return result


def _attach_frozen_v4_comparison(report: dict[str, Any], v4_report: dict[str, Any]) -> None:
    old_cases = {str(case["run_directory_id"]): case for case in v4_report.get("cases", [])}
    for case in report.get("cases", []):
        old_case = old_cases.get(str(case.get("run_directory_id")))
        if old_case is None:
            raise ValueError("candidate case has no exact frozen V4 baseline case")
        old_capture = old_case.get("diagnostic_only_cutoff_stage_capture", {})
        new_capture = case.get("diagnostic_only_cutoff_stage_capture", {})
        old_modes = {
            tuple(mode.get("exact_signed_mode_key", ())): mode
            for mode in old_capture.get("six_exact_signed_key_results", [])
        }
        new_modes = new_capture.get("six_exact_signed_key_results", [])
        if len(old_modes) != 6 or len(new_modes) != 6:
            raise ValueError("candidate and V4 baseline must each contain exactly six signed keys")
        for new_mode in new_modes:
            key = tuple(new_mode.get("exact_signed_mode_key", ()))
            old_mode = old_modes.get(key)
            if old_mode is None:
                raise ValueError(f"candidate signed key has no exact V4 match: {key}")
            old_projection = old_mode["projection"]
            new_projection = new_mode["projection"]
            old_boundary = _decode_complex(old_projection["merged_cut_boundary_total_amplitude_complex"])
            saved_total = _decode_complex(new_projection["saved_total_auxiliary_projection_complex"])
            candidate_route = new_mode["candidate_scale_homogeneous_stage_two_routes"]
            projection_route = candidate_route["projection"]
            coupling_route = candidate_route["coupling"]
            candidate_n = _decode_complex(projection_route["after_candidate_merged_cutoff_dot_complex"])
            untruncated_n = _decode_complex(projection_route["raw_untruncated_dot_complex"])
            H = float(new_projection["H"])
            P = _decode_complex(new_projection["boundary_phase_P"])
            candidate_total_boundary = candidate_n / H * P
            untruncated_boundary = untruncated_n / H * P
            new_mode["frozen_v4_default_cutoff_baseline"] = {
                "component_stage_records": old_mode["component_stage_records"],
                "stage_two_routes": old_mode["production_stage_two_routes"],
                "projection": old_projection,
                "qualification": "NO_CARRIER_COMPARISON; original gate result is preserved separately",
            }
            new_mode["candidate_vs_legacy_and_untruncated"] = {
                "legacy_v4_boundary_minus_saved_total_abs": float(abs(old_boundary - saved_total)),
                "candidate_boundary_minus_saved_total_abs": float(abs(candidate_total_boundary - saved_total)),
                "candidate_boundary_minus_legacy_v4_abs": float(abs(candidate_total_boundary - old_boundary)),
                "untruncated_boundary_minus_saved_total_abs": float(abs(untruncated_boundary - saved_total)),
                "candidate_projection_N_minus_legacy_v4_N": _complex_json(
                    candidate_n
                    - _decode_complex(old_projection["after_merged_cutoff_N_complex"])
                ),
                "candidate_projection_N_minus_untruncated_N": _complex_json(
                    candidate_n - untruncated_n
                ),
                "candidate_coupling_Du_nonconjugated": coupling_route[
                    "after_production_merged_cutoff_dot_complex"
                ],
                "untruncated_coupling_Du_nonconjugated": coupling_route[
                    "raw_untruncated_dot_complex"
                ],
                "coupling_dot_is_not_physical_power": True,
                "saved_total_is_used_for_top00; incident_and_outgoing_remain_separate": True,
            }
        case["original_v4_carrier_gate"] = old_case.get("carrier_comparison_gate")
        case["original_v4_qualification"] = old_case.get("qualification")
        case["status"] = "NO_CARRIER_COMPARISON"
        case["qualification"] = "DIAGNOSTIC_ONLY; ORIGINAL V4 CARRIER GATE REMAINS FAIL/OPEN"
        new_capture["status"] = "SCALE_HOMOGENEOUS_CANDIDATE_CAPTURE_COMPLETE_NOT_QUALIFICATION"
        new_capture["qualification"] = "NO_CARRIER_COMPARISON; original V4/V5 failure is unchanged"
        new_capture["historical_v4_absolute_floor_cutoff_not_modified"] = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract_path = args.contract.resolve()
    output_path = args.output.resolve()
    contract = json.loads(contract_path.read_text())
    identity = _verify_candidate_contract(contract_path, contract)
    candidate = contract["scale_homogeneous_candidate"]
    v4_report_path = Path(candidate["frozen_v4_report"]["path"]).resolve()
    v4_report = json.loads(v4_report_path.read_text())
    if v4_report.get("status") != "COMPLETE_CUTOFF_STAGE_DIAGNOSTIC_NO_QUALIFICATION":
        raise ValueError("frozen V4 saved-field baseline is not a completed diagnostic")

    base = _load_module("task40_frozen_v4_cutoff_worker", BASE_WORKER)
    base._cutoff_stage_capture = lambda **kwargs: _candidate_capture(base, **kwargs)
    sys.argv = [str(BASE_WORKER), "--contract", str(contract_path), "--output", str(output_path)]
    status = int(base.main())
    if not output_path.is_file():
        raise RuntimeError("base saved-field worker did not write its candidate report")
    report = json.loads(output_path.read_text())
    _attach_frozen_v4_comparison(report, v4_report)
    report["schema"] = "task40.d13.scale-homogeneous-cutoff-candidate-report.v1"
    report["scope"] = "same_saved_Y2_Y3_six_signed_keys_legacy_candidate_untruncated_q28_integrals"
    report["candidate_policy"] = contract["scale_homogeneous_candidate"]
    report["candidate_source_and_package_identity"] = identity
    report["frozen_v4_comparison_report"] = {
        "path": str(v4_report_path),
        "sha256": candidate["frozen_v4_report"]["sha256"],
        "correction_path": candidate["v4_postprocess_correction"]["path"],
        "correction_sha256": candidate["v4_postprocess_correction"]["sha256"],
    }
    report["qualification"] = (
        "DIAGNOSTIC_ONLY_NO_CARRIER_COMPARISON; original qualification gate remains FAIL/OPEN; "
        "this saved-field candidate cannot establish a repaired FE solution"
    )
    if report.get("status") == "COMPLETE_CUTOFF_STAGE_DIAGNOSTIC_NO_QUALIFICATION":
        report["status"] = "SCALE_HOMOGENEOUS_CANDIDATE_CAPTURE_COMPLETE_NOT_QUALIFICATION"
    temporary = output_path.with_suffix(output_path.suffix + ".candidate.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, output_path)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
