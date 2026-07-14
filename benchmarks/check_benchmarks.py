from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "benchmarks"


@dataclass
class Gate:
    name: str
    passed: bool
    observed: Any
    expected: Any
    evidence: str


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _relative_difference(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-300)


def _iterative_peak_rss(record: dict[str, Any]) -> float | None:
    if record.get("simultaneous_worker_peak_gib") is not None:
        return float(record["simultaneous_worker_peak_gib"])
    if record.get("peak_rss_gb_including_rta") is not None:
        return float(record["peak_rss_gb_including_rta"])
    if record.get("peak_total_rss_including_rta_gb") is not None:
        return float(record["peak_total_rss_including_rta_gb"])
    values = [record.get("final_peak_total_gb")]
    values.append((record.get("official_rta") or {}).get("rta_peak_total_gb"))
    available = [float(value) for value in values if value is not None]
    return max(available) if available else None


def _metadata_complete(record: dict[str, Any]) -> tuple[bool, list[str]]:
    metadata = record.get("metadata", {})
    required = (
        "commit_sha",
        "branch",
        "git_dirty",
        "command",
        "timestamp_utc",
        "container_image",
        "container_digest",
        "host_environment_id",
        "provenance",
    )
    missing = [key for key in required if metadata.get(key) in (None, "")]
    return not missing, missing


def _commit_relation(commit: str | None, provenance: str | None) -> str:
    if provenance == "reviewed_reference_not_rerun":
        return "reviewed_reference_exempt"
    if commit is None or re.fullmatch(r"[0-9a-f]{7,40}", commit) is None:
        return "invalid_commit"
    checkout = _git("rev-parse", "HEAD")
    if checkout is None:
        return "checkout_unavailable_sha_valid"
    try:
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", commit, checkout],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return "not_checkout_ancestor"
    return "exact_checkout" if commit == checkout else "checkout_ancestor"


def _record_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else BENCHMARKS / path


def evaluate() -> tuple[list[Gate], list[dict[str, Any]]]:
    expected = _load_json(BENCHMARKS / "expected" / "gates.json")
    canonical_config = _load_json(BENCHMARKS / "configs" / "workstation_p2.json")
    with (BENCHMARKS / "benchmark_manifest.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        manifest = list(csv.DictReader(stream))

    gates: list[Gate] = []

    case_requirements = {
        "001_2d_tm_pml_floquet": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
        ),
        "002_2d_tm_dtn_equivalence": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "003_2d_te_tm_complex_absorption": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "010_3d_stage1_airbox": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "011_3d_stage2a_floquet": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
        ),
        "012_3d_stage2b_pml": ("README.md", "config.json", "expected.json", "run.sh"),
        "013_3d_stage2c_fresnel": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
        ),
        "020_3d_stage4a_flat_dtn": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
        ),
        "021_3d_stage4b_direct": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "022_dtn_condensation_equivalence": (
            "README.md",
            "fixture.json",
            "expected.json",
            "test_command.txt",
        ),
        "030_mumps_ooc_blr": (
            "README.md",
            "config.json",
            "expected.json",
            "test_command.txt",
        ),
        "031_workstation_iterative": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "040_mpi_p_algebra_regression": (
            "README.md",
            "fixture.json",
            "expected.json",
            "test_command.txt",
        ),
        "050_stage4_direct_memory_forensics": (
            "README.md",
            "config.json",
            "expected.json",
            "run_h5.sh",
            "run_h3.sh",
            "run_h2_guarded.sh",
            "records",
        ),
        "060_multilevel_hcurl_iterative_solver": (
            "README.md",
            "config.json",
            "expected.json",
            "expected/gates.json",
            "run.sh",
            "records/h5_baseline.json",
            "records/hierarchy_contract.json",
            "records/transfer_contract.json",
            "records/candidate_screen_summary.json",
            "records/best_h5.json",
            "records/best_h3.json",
            "records/best_h2.json",
        ),
        "070_compact_physical_slab_memory_optimization": (
            "README.md",
            "config.json",
            "expected.json",
            "expected/gates.json",
            "run.sh",
            "records/baseline_h5.json",
            "records/baseline_h3.json",
            "records/baseline_h2.json",
            "records/object_lifecycle.json",
            "records/pc_linearity.json",
            "records/candidate_screen.json",
            "records/memory_components.json",
            "records/h2_prediction.json",
            "records/best_h5.json",
            "records/best_h3.json",
            "records/best_h2.json",
        ),
        "080_hybrid_fem_modal_direct_baseline": (
            "README.md",
            "config.json",
            "expected.json",
            "expected/gates.json",
            "run.sh",
            "run_phase2.sh",
            "run_phase3.sh",
            "records/full3d_h5_reference.json",
            "records/full3d_h3_reference.json",
            "records/qep_phase2.json",
            "records/modes_phase3.json",
        ),
    }
    cases_root = BENCHMARKS / "cases"
    for case_name, required_names in case_requirements.items():
        missing = [
            name
            for name in required_names
            if not (cases_root / case_name / name).exists()
        ]
        gates.append(
            Gate(
                f"case_contract:{case_name}",
                not missing,
                missing or "complete",
                "all case-contained contract files exist",
                f"cases/{case_name}",
            )
        )

    reference_files = (
        "010_3d_stage1_airbox/records/canonical_reference.json",
        "021_3d_stage4b_direct/records/h5_reference.json",
        "021_3d_stage4b_direct/records/h3_reference.json",
        "021_3d_stage4b_direct/records/h2_reviewed_reference.json",
        "031_workstation_iterative/records/h5_reference.json",
        "031_workstation_iterative/records/h3_reference.json",
        "031_workstation_iterative/records/h2_reference.json",
    )
    for relative_reference in reference_files:
        reference_path = cases_root / relative_reference
        if not reference_path.is_file():
            gates.append(
                Gate(
                    f"case_reference:{relative_reference}",
                    False,
                    "missing reference file",
                    "sha256-pinned canonical reference",
                    f"cases/{relative_reference}",
                )
            )
            continue
        reference = _load_json(reference_path)
        canonical_path = ROOT / str(reference.get("canonical_record", ""))
        observed_hash = _sha256(canonical_path) if canonical_path.is_file() else None
        expected_hash = reference.get("sha256")
        gates.append(
            Gate(
                f"case_reference:{relative_reference}",
                observed_hash == expected_hash,
                observed_hash,
                expected_hash,
                str(reference.get("canonical_record")),
            )
        )

    case080 = cases_root / "080_hybrid_fem_modal_direct_baseline"
    case080_config = _load_json(case080 / "config.json")
    case080_expected = _load_json(case080 / "expected.json")
    case080_gate_bundle = _load_json(case080 / "expected" / "gates.json")
    case080_gates = case080_gate_bundle["phase1"]
    case080_phase2_gates = case080_gate_bundle["phase2"]
    case080_phase3_gates = case080_gate_bundle["phase3"]
    gates.append(
        Gate(
            "task032_phase1_ordinary_default_unchanged",
            case080_config.get("ordinary_default_changed") is False
            and case080_expected.get("ordinary_default_changed") is False
            and case080_gates.get("ordinary_default_changed") is False
            and case080_phase2_gates.get("ordinary_default_changed") is False
            and case080_phase3_gates.get("ordinary_default_changed") is False,
            {
                "config": case080_config.get("ordinary_default_changed"),
                "expected": case080_expected.get("ordinary_default_changed"),
                "gates": case080_gates.get("ordinary_default_changed"),
                "phase2_gates": case080_phase2_gates.get(
                    "ordinary_default_changed"
                ),
                "phase3_gates": case080_phase3_gates.get(
                    "ordinary_default_changed"
                ),
            },
            False,
            "cases/080_hybrid_fem_modal_direct_baseline",
        )
    )

    phase2_relative = "records/qep_phase2.json"
    phase2_path = case080 / phase2_relative
    phase2_record = _load_json(phase2_path)
    phase2_metadata = phase2_record.get("metadata", {})
    phase2_metadata_for_contract = dict(phase2_metadata)
    phase2_metadata_for_contract.setdefault(
        "timestamp_utc", phase2_record.get("timestamp_utc")
    )
    phase2_complete, phase2_missing = _metadata_complete(
        {"metadata": phase2_metadata_for_contract}
    )
    phase2_relation = _commit_relation(
        phase2_metadata.get("commit_sha"), phase2_metadata.get("provenance")
    )
    phase2_identity_ok = (
        phase2_complete
        and phase2_record.get("schema_version")
        == case080_phase2_gates["required_schema"]
        and phase2_record.get("status") == "pass"
        and phase2_metadata.get("commit_sha")
        == case080_phase2_gates["required_commit"]
        and phase2_metadata.get("container_digest")
        == case080_phase2_gates["required_container_digest"]
        and phase2_metadata.get("mpi_size")
        == case080_phase2_gates["required_mpi_size"]
        and phase2_metadata.get("eigen_backend")
        == case080_phase2_gates["required_backend"]
        and phase2_metadata.get("git_dirty") is False
        and phase2_metadata.get("tracked_source_dirty") is False
        and phase2_metadata.get("full_eigenvector_gather") is False
        and phase2_relation in {"exact_checkout", "checkout_ancestor"}
    )
    gates.append(
        Gate(
            "task032_phase2_identity",
            phase2_identity_ok,
            {
                "missing": phase2_missing,
                "relation": phase2_relation,
                "metadata": phase2_metadata,
            },
            "clean MPI4 SLEPc PEP record on the frozen commit and image",
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase2_relative}",
        )
    )

    phase2_cases = phase2_record.get("cases", [])
    phase2_by_id = {case.get("case_id"): case for case in phase2_cases}
    expected_phase2_ids = case080_phase2_gates["required_case_ids"]
    phase2_case_contract_ok = (
        set(phase2_by_id) == set(expected_phase2_ids)
        and all(
            case.get("scalar_dtype") == case080_phase2_gates["required_dtype"]
            and case.get("formulation")
            == "mixed_transverse_N1curl_longitudinal_Lagrange_QEP"
            and case.get("polynomial_order") == 2
            and case.get("leading_coefficient_singular_by_design") is True
            and case.get("constraint_communication_scope")
            == case080_phase2_gates["required_constraint_communication_scope"]
            and int(case.get("global_slave_count", -1))
            == int(case.get("full_shape", [0])[0])
            - int(case.get("reduced_shape", [0])[0])
            and int(case.get("global_slave_count", -1))
            == int(case.get("transverse_constraint_count_global", -2))
            + int(case.get("longitudinal_constraint_count_global", -3))
            for case in phase2_cases
        )
    )
    gates.append(
        Gate(
            "task032_phase2_case_and_qep_contract",
            phase2_case_contract_ok,
            {
                "case_ids": list(phase2_by_id),
                "formulations": [case.get("formulation") for case in phase2_cases],
                "shapes": [
                    [case.get("full_shape"), case.get("reduced_shape")]
                    for case in phase2_cases
                ],
            },
            {
                "case_ids": expected_phase2_ids,
                "dtype": case080_phase2_gates["required_dtype"],
                "polynomial": "singular-leading quadratic",
            },
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase2_relative}",
        )
    )

    phase2_targets = [
        target
        for case in phase2_cases
        for target in (case.get("positive_target"), case.get("negative_target"))
        if target is not None
    ]
    max_polynomial_residual = max(
        float(target["selected"]["polynomial_relative_residual"])
        for target in phase2_targets
    )
    max_norm_error = max(
        abs(float(target["selected"]["electric_l2_norm_after"]) - 1.0)
        for target in phase2_targets
    )
    max_probe_residual = max(
        float(case.get("max_probe_residual", float("inf"))) for case in phase2_cases
    )
    max_pair_coordinate_error = max(
        float(case.get("max_pair_coordinate_error", float("inf")))
        for case in phase2_cases
    )
    phase2_numeric_ok = (
        max_polynomial_residual
        <= float(case080_phase2_gates["max_polynomial_relative_residual"])
        and max_norm_error
        <= float(case080_phase2_gates["max_electric_l2_norm_error"])
        and max_probe_residual
        <= float(case080_phase2_gates["max_probe_residual"])
        and max_pair_coordinate_error
        <= float(case080_phase2_gates["max_pair_coordinate_error"])
    )
    gates.append(
        Gate(
            "task032_phase2_residual_normalization_and_orientation",
            phase2_numeric_ok,
            {
                "max_polynomial_residual": max_polynomial_residual,
                "max_electric_l2_norm_error": max_norm_error,
                "max_probe_residual": max_probe_residual,
                "max_pair_coordinate_error": max_pair_coordinate_error,
            },
            {
                "max_polynomial_residual": case080_phase2_gates[
                    "max_polynomial_relative_residual"
                ],
                "max_electric_l2_norm_error": case080_phase2_gates[
                    "max_electric_l2_norm_error"
                ],
                "max_probe_residual": case080_phase2_gates["max_probe_residual"],
                "max_pair_coordinate_error": case080_phase2_gates[
                    "max_pair_coordinate_error"
                ],
            },
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase2_relative}",
        )
    )

    ownership_ok = True
    ownership_observed: dict[str, Any] = {}
    for case in phase2_cases:
        for target_name in ("positive_target", "negative_target"):
            target = case.get(target_name)
            if target is None:
                continue
            ownership = target.get("ownership_by_rank") or []
            reduced_sum = sum(int(row["reduced_local_size"]) for row in ownership)
            full_sum = sum(int(row["full_local_size"]) for row in ownership)
            key = f"{case['case_id']}:{target_name}"
            ownership_observed[key] = {
                "ranks": len(ownership),
                "reduced_sum": reduced_sum,
                "full_sum": full_sum,
            }
            ownership_ok = ownership_ok and (
                len(ownership) == case080_phase2_gates["required_mpi_size"]
                and reduced_sum == int(case["reduced_shape"][0])
                and full_sum == int(case["full_shape"][0])
                and target["selected"].get("gathered_to_root") is False
            )
    gates.append(
        Gate(
            "task032_phase2_distributed_ownership",
            ownership_ok,
            ownership_observed,
            "all local sizes sum to global shapes on MPI4; no full vector gather",
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase2_relative}",
        )
    )

    air_cases = [phase2_by_id[key] for key in ("air_p2_h5", "air_p2_h3", "air_p2_h2", "air_p2_h1p5")]
    air_errors = [float(case["positive_relative_beta_error"]) for case in air_cases]
    lossy_case = phase2_by_id["lossy_homogeneous_p2_h2"]
    phase2_analytic_ok = (
        all(later < earlier for earlier, later in zip(air_errors, air_errors[1:]))
        and air_errors[2]
        <= float(case080_phase2_gates["max_air_h2_relative_beta_error"])
        and air_errors[3]
        <= float(case080_phase2_gates["max_air_h1p5_relative_beta_error"])
        and float(lossy_case["positive_relative_beta_error"])
        <= float(case080_phase2_gates["max_lossy_h2_relative_beta_error"])
        and float(lossy_case["positive_target"]["selected"]["beta_per_nm"][1]) > 0.0
    )
    gates.append(
        Gate(
            "task032_phase2_homogeneous_analytic_beta",
            phase2_analytic_ok,
            {
                "air_relative_errors_h5_h3_h2_h1p5": air_errors,
                "lossy_h2_relative_error": lossy_case["positive_relative_beta_error"],
                "lossy_h2_beta": lossy_case["positive_target"]["selected"]["beta_per_nm"],
            },
            {
                "air_strictly_decreasing": True,
                "air_h2_max": case080_phase2_gates["max_air_h2_relative_beta_error"],
                "air_h1p5_max": case080_phase2_gates[
                    "max_air_h1p5_relative_beta_error"
                ],
                "lossy_h2_max": case080_phase2_gates[
                    "max_lossy_h2_relative_beta_error"
                ],
                "lossy_forward_imag_positive": True,
            },
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase2_relative}",
        )
    )

    requested_pairs = [
        case for case in phase2_cases if case.get("negative_target") is not None
    ]
    max_pair_error = max(
        float(case.get("reciprocal_pair_relative_error", float("inf")))
        for case in requested_pairs
    )
    runner_gates = phase2_record.get("gates", {})
    phase2_pair_and_runner_ok = (
        max_pair_error <= float(case080_phase2_gates["max_pair_relative_error"])
        and runner_gates
        and all(value is True for value in runner_gates.values())
    )
    gates.append(
        Gate(
            "task032_phase2_reciprocal_pairs_and_runner_gates",
            phase2_pair_and_runner_ok,
            {"max_pair_relative_error": max_pair_error, "runner_gates": runner_gates},
            {
                "max_pair_relative_error": case080_phase2_gates[
                    "max_pair_relative_error"
                ],
                "all_runner_gates": True,
            },
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase2_relative}",
        )
    )

    phase3_relative = "records/modes_phase3.json"
    phase3_record = _load_json(case080 / phase3_relative)
    phase3_metadata = phase3_record.get("metadata", {})
    phase3_complete, phase3_missing = _metadata_complete(phase3_record)
    phase3_relation = _commit_relation(
        phase3_metadata.get("commit_sha"), phase3_metadata.get("provenance")
    )
    phase3_identity_ok = (
        phase3_complete
        and phase3_record.get("schema_version")
        == case080_phase3_gates["required_schema"]
        and phase3_record.get("status") == "pass"
        and phase3_metadata.get("commit_sha")
        == case080_phase3_gates["required_commit"]
        and phase3_metadata.get("container_digest")
        == case080_phase3_gates["required_container_digest"]
        and phase3_metadata.get("mpi_size")
        == case080_phase3_gates["required_mpi_size"]
        and phase3_metadata.get("eigen_backend")
        == case080_phase3_gates["required_backend"]
        and phase3_metadata.get("git_dirty") is False
        and phase3_metadata.get("tracked_source_dirty") is False
        and phase3_metadata.get("full_eigenvector_gather") is False
        and phase3_relation in {"exact_checkout", "checkout_ancestor"}
    )
    gates.append(
        Gate(
            "task032_phase3_identity",
            phase3_identity_ok,
            {
                "missing": phase3_missing,
                "relation": phase3_relation,
                "metadata": phase3_metadata,
            },
            "clean MPI4 adjoint-QEP record on the frozen commit and image",
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase3_relative}",
        )
    )

    phase3_cases = phase3_record.get("cases", [])
    phase3_by_id = {case.get("case_id"): case for case in phase3_cases}
    phase3_bases = [
        (case, side, case.get(side))
        for case in phase3_cases
        for side in ("positive", "negative")
        if case.get(side) is not None
    ]
    phase3_modes = [
        (case, side, basis, mode)
        for case, side, basis in phase3_bases
        for mode in basis.get("modes", [])
    ]
    phase3_ownership_ok = True
    phase3_ownership_observed: dict[str, Any] = {}
    for case, side, basis, mode in phase3_modes:
        ownership = mode.get("left_ownership_by_rank") or []
        reduced_sum = sum(int(row["reduced_local_size"]) for row in ownership)
        full_sum = sum(int(row["full_local_size"]) for row in ownership)
        key = f"{case['case_id']}:{side}:{mode['index']}"
        phase3_ownership_observed[key] = {
            "ranks": len(ownership),
            "reduced_sum": reduced_sum,
            "full_sum": full_sum,
        }
        phase3_ownership_ok = phase3_ownership_ok and (
            len(ownership) == case080_phase3_gates["required_mpi_size"]
            and reduced_sum == int(case["reduced_shape"][0])
            and full_sum == int(case["full_shape"][0])
            and mode.get("full_vector_gathered") is False
        )
    phase3_case_contract_ok = (
        set(phase3_by_id) == set(case080_phase3_gates["required_case_ids"])
        and phase3_ownership_ok
        and all(
            case.get("constraint_communication_scope")
            == case080_phase3_gates[
                "required_constraint_communication_scope"
            ]
            for case in phase3_cases
        )
        and all(
            int(basis.get("mode_count", 0)) >= 2
            and basis.get("full_vector_gathered") is False
            and all(
                float(group.get("overlap_condition", float("inf")))
                <= float(case080_phase3_gates["max_overlap_condition"])
                for group in basis.get("near_degenerate_groups", [])
            )
            for _, _, basis in phase3_bases
        )
    )
    gates.append(
        Gate(
            "task032_phase3_case_ownership_and_condition_contract",
            phase3_case_contract_ok,
            {
                "case_ids": list(phase3_by_id),
                "basis_sides": [
                    [case["case_id"], side, basis.get("mode_count")]
                    for case, side, basis in phase3_bases
                ],
                "ownership": phase3_ownership_observed,
            },
            {
                "case_ids": case080_phase3_gates["required_case_ids"],
                "mpi_size": case080_phase3_gates["required_mpi_size"],
                "no_full_vector_gather": True,
                "max_overlap_condition": case080_phase3_gates[
                    "max_overlap_condition"
                ],
            },
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase3_relative}",
        )
    )

    max_phase3_right_residual = max(
        float(mode["right_polynomial_relative_residual"])
        for _, _, _, mode in phase3_modes
    )
    max_phase3_left_residual = max(
        float(mode["left_polynomial_relative_residual"])
        for _, _, _, mode in phase3_modes
    )
    max_phase3_left_pair_error = max(
        float(mode["left_pair_relative_error"])
        for _, _, _, mode in phase3_modes
    )
    max_phase3_biorth_error = max(
        float(basis["max_biorthogonality_identity_error"])
        for _, _, basis in phase3_bases
    )
    max_phase3_unit_flux_error = max(
        abs(abs(float(mode["poynting_z_after_normalization"])) - 1.0)
        for _, _, _, mode in phase3_modes
    )
    phase3_numeric_ok = (
        max_phase3_right_residual
        <= float(
            case080_phase3_gates["max_right_polynomial_relative_residual"]
        )
        and max_phase3_left_residual
        <= float(
            case080_phase3_gates["max_left_polynomial_relative_residual"]
        )
        and max_phase3_left_pair_error
        <= float(case080_phase3_gates["max_left_pair_relative_error"])
        and max_phase3_biorth_error
        <= float(case080_phase3_gates["max_biorthogonality_identity_error"])
        and max_phase3_unit_flux_error
        <= float(case080_phase3_gates["max_unit_flux_error"])
        and all(mode.get("passive_branch_valid") is True for _, _, _, mode in phase3_modes)
    )
    gates.append(
        Gate(
            "task032_phase3_residual_biorthogonality_and_flux",
            phase3_numeric_ok,
            {
                "max_right_residual": max_phase3_right_residual,
                "max_left_residual": max_phase3_left_residual,
                "max_left_pair_error": max_phase3_left_pair_error,
                "max_biorthogonality_identity_error": max_phase3_biorth_error,
                "max_unit_flux_error": max_phase3_unit_flux_error,
                "all_passive": all(
                    mode.get("passive_branch_valid") is True
                    for _, _, _, mode in phase3_modes
                ),
            },
            {
                "max_right_residual": case080_phase3_gates[
                    "max_right_polynomial_relative_residual"
                ],
                "max_left_residual": case080_phase3_gates[
                    "max_left_polynomial_relative_residual"
                ],
                "max_left_pair_error": case080_phase3_gates[
                    "max_left_pair_relative_error"
                ],
                "max_biorthogonality_identity_error": case080_phase3_gates[
                    "max_biorthogonality_identity_error"
                ],
                "max_unit_flux_error": case080_phase3_gates[
                    "max_unit_flux_error"
                ],
            },
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase3_relative}",
        )
    )

    air_phase3 = phase3_by_id["air_p2_h10"]
    lossy_phase3 = phase3_by_id["lossy_homogeneous_p2_h10"]
    patterned_phase3 = phase3_by_id["stage4_xy_p2_h10"]
    phase3_pairs = air_phase3.get("reciprocal_pairs", [])
    max_phase3_reciprocal_error = max(
        float(pair.get("relative_beta_error", float("inf")))
        for pair in phase3_pairs
    )
    phase3_direction_ok = (
        len(phase3_pairs) >= 2
        and max_phase3_reciprocal_error
        <= float(case080_phase3_gates["max_reciprocal_pair_relative_error"])
        and all(
            pair.get("opposite_direction") is True
            and pair.get("passive_branches_valid") is True
            for pair in phase3_pairs
        )
        and all(
            mode.get("direction") == "forward"
            and float(mode["poynting_z_after_normalization"]) > 0.0
            for mode in air_phase3["positive"]["modes"]
        )
        and all(
            mode.get("direction") == "backward"
            and float(mode["poynting_z_after_normalization"]) < 0.0
            for mode in air_phase3["negative"]["modes"]
        )
        and all(
            mode.get("direction") == "forward"
            and mode.get("kind") == "lossy_propagating"
            and float(mode["beta_per_nm"][1]) > 0.0
            for case in (lossy_phase3, patterned_phase3)
            for mode in case["positive"]["modes"]
        )
    )
    gates.append(
        Gate(
            "task032_phase3_direction_and_reciprocal_identity",
            phase3_direction_ok,
            {
                "max_reciprocal_error": max_phase3_reciprocal_error,
                "pairs": phase3_pairs,
                "air_positive_directions": [
                    mode.get("direction")
                    for mode in air_phase3["positive"]["modes"]
                ],
                "air_negative_directions": [
                    mode.get("direction")
                    for mode in air_phase3["negative"]["modes"]
                ],
            },
            {
                "max_reciprocal_error": case080_phase3_gates[
                    "max_reciprocal_pair_relative_error"
                ],
                "air_directions": ["forward", "backward"],
                "lossy_and_patterned": "forward passive lossy_propagating",
            },
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase3_relative}",
        )
    )

    phase3_tracking = phase3_record.get("angle_tracking") or {}
    phase3_tracking_matches = phase3_tracking.get("matches", [])
    phase3_tracking_subspaces = phase3_tracking.get("subspaces", [])
    min_phase3_tracking_overlap = min(
        (float(match.get("overlap", float("-inf"))) for match in phase3_tracking_matches),
        default=float("-inf"),
    )
    max_phase3_tracking_angle = max(
        (
            float(report.get("max_principal_angle_rad", float("inf")))
            for report in phase3_tracking_subspaces
        ),
        default=float("inf"),
    )
    phase3_runner_gates = phase3_record.get("gates", {})
    phase3_tracking_ok = (
        len(phase3_tracking_matches) >= 2
        and not phase3_tracking.get("unmatched_previous")
        and min_phase3_tracking_overlap
        >= float(case080_phase3_gates["min_tracking_overlap"])
        and max_phase3_tracking_angle
        <= float(case080_phase3_gates["max_tracking_principal_angle_rad"])
        and phase3_runner_gates
        and all(value is True for value in phase3_runner_gates.values())
    )
    gates.append(
        Gate(
            "task032_phase3_tracking_subspace_and_runner_gates",
            phase3_tracking_ok,
            {
                "match_count": len(phase3_tracking_matches),
                "min_overlap": min_phase3_tracking_overlap,
                "max_principal_angle_rad": max_phase3_tracking_angle,
                "unmatched_previous": phase3_tracking.get("unmatched_previous"),
                "unmatched_current": phase3_tracking.get("unmatched_current"),
                "runner_gates": phase3_runner_gates,
            },
            {
                "min_match_count": 2,
                "min_overlap": case080_phase3_gates["min_tracking_overlap"],
                "max_principal_angle_rad": case080_phase3_gates[
                    "max_tracking_principal_angle_rad"
                ],
                "all_runner_gates": True,
            },
            f"cases/080_hybrid_fem_modal_direct_baseline/{phase3_relative}",
        )
    )
    task032_reference_records: dict[str, dict[str, Any]] = {}
    for level in case080_gates["required_levels"]:
        relative = f"records/full3d_{level}_reference.json"
        record_path = case080 / relative
        record = _load_json(record_path)
        task032_reference_records[level] = record
        metadata = record.get("metadata", {})
        complete, missing = _metadata_complete(record)
        relation = _commit_relation(metadata.get("commit_sha"), metadata.get("provenance"))
        identity_ok = (
            complete
            and metadata.get("commit_sha") == case080_gates["required_commit"]
            and metadata.get("container_digest")
            == case080_gates["required_container_digest"]
            and metadata.get("git_dirty") is False
            and metadata.get("tracked_source_dirty") is False
            and relation in {"exact_checkout", "checkout_ancestor"}
        )
        gates.append(
            Gate(
                f"task032_phase1_identity:{level}",
                identity_ok,
                {"missing": missing, "relation": relation, "metadata": metadata},
                "complete clean metadata on frozen commit and image",
                f"cases/080_hybrid_fem_modal_direct_baseline/{relative}",
            )
        )

        results = record.get("results", {})
        numeric_ok = (
            results.get("case_status") == "completed"
            and results.get("official_result") is True
            and float(results.get("linear_system_true_relative_residual", float("inf")))
            <= float(case080_gates["max_true_relative_residual"])
            and abs(float(results.get("energy_closure_error_port_volume", float("inf"))))
            <= float(case080_gates["max_abs_energy_closure"])
        )
        gates.append(
            Gate(
                f"task032_phase1_numeric:{level}",
                numeric_ok,
                {
                    "residual": results.get("linear_system_true_relative_residual"),
                    "closure": results.get("energy_closure_error_port_volume"),
                    "status": results.get("case_status"),
                    "official": results.get("official_result"),
                },
                {
                    "residual_max": case080_gates["max_true_relative_residual"],
                    "closure_abs_max": case080_gates["max_abs_energy_closure"],
                },
                f"cases/080_hybrid_fem_modal_direct_baseline/{relative}",
            )
        )

        reference_contract = record.get("reference_contract", {})
        archive_ok = (
            reference_contract.get("schema_version")
            == case080_gates["required_archive_schema"]
            and reference_contract.get("array_shape")
            == case080_gates["required_archive_shape"]
            and reference_contract.get("plane_z_nm")
            == case080_gates["required_plane_z_nm"]
            and reference_contract.get("dtype") == case080_gates["required_dtype"]
            and reference_contract.get("interface_trace_sides")
            == case080_gates["required_interface_trace_sides"]
            and int(reference_contract.get("replicated_payload_bytes_uncompressed", 2**63))
            <= int(case080_gates["max_replicated_payload_bytes"])
        )
        gates.append(
            Gate(
                f"task032_phase1_archive_contract:{level}",
                archive_ok,
                reference_contract,
                {
                    "schema": case080_gates["required_archive_schema"],
                    "shape": case080_gates["required_archive_shape"],
                    "planes": case080_gates["required_plane_z_nm"],
                    "dtype": case080_gates["required_dtype"],
                },
                f"cases/080_hybrid_fem_modal_direct_baseline/{relative}",
            )
        )

        artifacts = record.get("artifacts", {})
        hash_keys = (
            "run_summary_sha256",
            "reference_metadata_sha256",
            "reference_npz_sha256",
            "diffraction_orders_sha256",
            "dtn_port_diffraction_orders_sha256",
            "power_metrics_sha256",
        )
        hashes_ok = all(
            re.fullmatch(r"[0-9a-f]{64}", str(artifacts.get(key, "")))
            for key in hash_keys
        ) and int(artifacts.get("reference_npz_bytes", 0)) > 0
        gates.append(
            Gate(
                f"task032_phase1_artifact_hashes:{level}",
                hashes_ok,
                {key: artifacts.get(key) for key in hash_keys},
                "six SHA-256 identities and a positive NPZ byte count",
                f"cases/080_hybrid_fem_modal_direct_baseline/{relative}",
            )
        )

        expected_rta = case080_expected["full3d_reference"][level]
        rta_delta = {
            key: abs(float(results.get(key, float("inf"))) - float(expected_rta[key]))
            for key in ("R_total", "T_total", "A_balance")
        }
        rta_ok = max(rta_delta.values()) <= float(case080_gates["rta_absolute_tolerance"])
        gates.append(
            Gate(
                f"task032_phase1_rta:{level}",
                rta_ok,
                rta_delta,
                {"absolute_tolerance": case080_gates["rta_absolute_tolerance"]},
                f"cases/080_hybrid_fem_modal_direct_baseline/{relative}",
            )
        )

    h3_consistency = task032_reference_records["h3"].get("historical_consistency", {})
    h3_history_ok = all(
        float(h3_consistency.get(key, float("inf"))) <= 1.0e-12
        for key in (
            "R_total_absolute_difference",
            "T_total_absolute_difference",
            "A_volume_total_absolute_difference",
        )
    )
    gates.append(
        Gate(
            "task032_phase1_h3_historical_consistency",
            h3_history_ok,
            h3_consistency,
            "all h3 R/T/A absolute differences <= 1e-12",
            "cases/080_hybrid_fem_modal_direct_baseline/records/full3d_h3_reference.json",
        )
    )

    records: dict[str, dict[str, Any]] = {}
    summaries: list[dict[str, Any]] = []
    for row in manifest:
        raw_path = row.get("canonical_record", "").strip()
        if not raw_path:
            continue
        path = _record_path(raw_path)
        exists = path.is_file()
        gates.append(
            Gate(f"record_exists:{row['benchmark_id']}", exists, exists, True, raw_path)
        )
        if not exists:
            continue
        record = _load_json(path)
        records[row["benchmark_id"]] = record
        record_benchmark_id = record.get("benchmark_id")
        gates.append(
            Gate(
                f"benchmark_id_matches_manifest:{row['benchmark_id']}",
                record_benchmark_id == row["benchmark_id"],
                record_benchmark_id,
                row["benchmark_id"],
                raw_path,
            )
        )
        complete, missing = _metadata_complete(record)
        gates.append(
            Gate(
                f"metadata_complete:{row['benchmark_id']}",
                complete,
                missing or "complete",
                "no missing required metadata",
                raw_path,
            )
        )
        metadata = record.get("metadata", {})
        if (
            metadata.get("provenance")
            == "canonical_lightweight_rerun_from_frozen_case_contract"
        ):
            tracked_source_dirty = metadata.get("tracked_source_dirty")
            gates.append(
                Gate(
                    f"canonical_lightweight_tracked_source_clean:{row['benchmark_id']}",
                    tracked_source_dirty is False,
                    tracked_source_dirty,
                    False,
                    raw_path,
                )
            )
        relation = _commit_relation(
            metadata.get("commit_sha"), metadata.get("provenance")
        )
        accepted_relations = set(expected["record_commit_relations_accepted"])
        gates.append(
            Gate(
                f"record_commit_consistent:{row['benchmark_id']}",
                relation in accepted_relations,
                relation,
                sorted(accepted_relations),
                raw_path,
            )
        )
        summaries.append(
            {
                "benchmark_id": row["benchmark_id"],
                "category": row["category"],
                "h_nm": record.get("h_nm", record.get("mesh_target_size_nm")),
                "mpi": record.get("mpi_size", 1),
                "iterations": record.get("iterations"),
                "true_residual": record.get(
                    "full_augmented_true_residual",
                    record.get(
                        "linear_system_relative_residual",
                        record.get(
                            "reduced_linear_residual",
                            (record.get("solver") or {}).get("linear_true_residual"),
                        ),
                    ),
                ),
                "peak_total_rss_gb": record.get(
                    "peak_total_rss_including_rta_gb",
                    _iterative_peak_rss(record)
                    or record.get(
                        "total_peak_rss_gb", record.get("total_peak_rss_upper_gb")
                    ),
                ),
                "R": (record.get("official_rta") or {}).get(
                    "R_total", record.get("R_total")
                ),
                "T": (record.get("official_rta") or {}).get(
                    "T_total", record.get("T_total")
                ),
                "A_volume": (record.get("official_rta") or {}).get(
                    "A_volume_total",
                    (record.get("official_rta") or {}).get(
                        "A_volume", record.get("A_volume_total")
                    ),
                ),
                "status": row["status"],
                "record": raw_path,
            }
        )

    case002_comparison_path = (
        cases_root / "002_2d_tm_dtn_equivalence" / "records" / "comparison.json"
    )
    case002_comparison = (
        _load_json(case002_comparison_path)
        if case002_comparison_path.is_file()
        else None
    )
    gates.append(
        Gate(
            "case002_comparison_exists",
            case002_comparison is not None,
            case002_comparison is not None,
            True,
            "cases/002_2d_tm_dtn_equivalence/records/comparison.json",
        )
    )
    if case002_comparison is not None:
        comparison_metadata = case002_comparison.get("metadata", {})
        if (
            comparison_metadata.get("provenance")
            == "canonical_lightweight_rerun_from_frozen_case_contract"
        ):
            tracked_source_dirty = comparison_metadata.get("tracked_source_dirty")
            gates.append(
                Gate(
                    "canonical_lightweight_tracked_source_clean:"
                    "case002_explicit_vs_auxiliary",
                    tracked_source_dirty is False,
                    tracked_source_dirty,
                    False,
                    "cases/002_2d_tm_dtn_equivalence/records/comparison.json",
                )
            )
        field_difference = float(case002_comparison["field_relative_difference"])
        rta_differences = [
            float(value)
            for value in case002_comparison["absolute_differences"].values()
        ]
        max_rta_difference = max(rta_differences, default=0.0)
        gates.extend(
            (
                Gate(
                    "case002_field_equivalence",
                    field_difference
                    <= expected["case002_field_relative_difference_max"],
                    field_difference,
                    expected["case002_field_relative_difference_max"],
                    "case002 comparison",
                ),
                Gate(
                    "case002_rta_equivalence",
                    max_rta_difference
                    <= expected["case002_rta_absolute_difference_max"],
                    max_rta_difference,
                    expected["case002_rta_absolute_difference_max"],
                    "case002 comparison",
                ),
                Gate(
                    "case002_matrix_identity",
                    case002_comparison["explicit"]["auxiliary_dofs"] == 0
                    and case002_comparison["auxiliary"]["auxiliary_dofs"] > 0
                    and case002_comparison["auxiliary"]["matrix_rows"]
                    > case002_comparison["explicit"]["matrix_rows"],
                    {
                        "explicit": {
                            "rows": case002_comparison["explicit"]["matrix_rows"],
                            "aux": case002_comparison["explicit"]["auxiliary_dofs"],
                        },
                        "auxiliary": {
                            "rows": case002_comparison["auxiliary"]["matrix_rows"],
                            "aux": case002_comparison["auxiliary"]["auxiliary_dofs"],
                        },
                    },
                    "explicit has no auxiliary rows; auxiliary system is augmented",
                    "case002 comparison",
                ),
            )
        )

    for benchmark_id in ("case002_explicit", "case002_auxiliary"):
        record = records.get(benchmark_id)
        if record is None:
            continue
        residual = float(record["solver"]["linear_true_residual"])
        closure = float(record["official_rta"]["energy_closure_error"])
        gates.extend(
            (
                Gate(
                    f"two_d_residual:{benchmark_id}",
                    residual <= expected["two_d_linear_residual_max"],
                    residual,
                    expected["two_d_linear_residual_max"],
                    benchmark_id,
                ),
                Gate(
                    f"lossless_energy:{benchmark_id}",
                    abs(closure) <= expected["two_d_energy_closure_abs_max"],
                    closure,
                    expected["two_d_energy_closure_abs_max"],
                    benchmark_id,
                ),
            )
        )

    for benchmark_id in ("case003_tm_lossy", "case003_te_lossy"):
        record = records.get(benchmark_id)
        if record is None:
            continue
        residual = float(record["solver"]["linear_true_residual"])
        official = record["official_rta"]
        closure = float(official["energy_closure_error"])
        balance_difference = abs(
            float(official["A_balance"]) - float(official["A_volume"])
        )
        nonnegative = {
            key: float(official[key]) for key in ("R_total", "T_total", "A_volume")
        }
        probe = record.get("diagnostic_probe") or {}
        gates.extend(
            (
                Gate(
                    f"lossy_residual:{benchmark_id}",
                    residual <= expected["two_d_linear_residual_max"],
                    residual,
                    expected["two_d_linear_residual_max"],
                    benchmark_id,
                ),
                Gate(
                    f"lossy_nonnegative:{benchmark_id}",
                    all(value >= 0.0 for value in nonnegative.values()),
                    nonnegative,
                    ">= 0",
                    benchmark_id,
                ),
                Gate(
                    f"lossy_energy:{benchmark_id}",
                    abs(closure) <= expected["two_d_energy_closure_abs_max"],
                    closure,
                    expected["two_d_energy_closure_abs_max"],
                    benchmark_id,
                ),
                Gate(
                    f"lossy_absorption_balance:{benchmark_id}",
                    balance_difference
                    <= expected["two_d_absorption_balance_difference_max"],
                    balance_difference,
                    expected["two_d_absorption_balance_difference_max"],
                    benchmark_id,
                ),
                Gate(
                    f"probe_is_diagnostic:{benchmark_id}",
                    probe.get("identity") == "diagnostic_only"
                    and probe.get("must_not_replace_official") is True,
                    probe.get("identity"),
                    "diagnostic_only and must_not_replace_official=true",
                    benchmark_id,
                ),
            )
        )

    tm_lossy = records.get("case003_tm_lossy")
    if tm_lossy is not None:
        auxiliary_trace = tm_lossy.get("auxiliary_vs_trace") or {}
        maximum = max(
            (abs(float(value)) for value in auxiliary_trace.values()),
            default=float("inf"),
        )
        gates.append(
            Gate(
                "lossy_tm_auxiliary_trace",
                maximum <= expected["two_d_auxiliary_trace_abs_difference_max"],
                maximum,
                expected["two_d_auxiliary_trace_abs_difference_max"],
                "case003_tm_lossy",
            )
        )

    zero_contrast = records.get("l1_2d_zero_contrast")
    if zero_contrast is not None:
        lossless_sum = float(zero_contrast["R_plus_T"])
        gates.append(
            Gate(
                "lossless_zero_contrast_regression",
                abs(lossless_sum - 1.0) <= expected["two_d_energy_closure_abs_max"],
                lossless_sum,
                1.0,
                "l1_2d_zero_contrast",
            )
        )

    iterative_ids = ["l3_iterative_h5", "l3_iterative_h3", "l3_iterative_h2"]
    iterative = [records.get(name) for name in iterative_ids]
    present = all(record is not None for record in iterative)
    gates.append(
        Gate(
            "iterative_h5_h3_h2_present",
            present,
            present,
            True,
            ",".join(iterative_ids),
        )
    )
    if present:
        iterative_records = [record for record in iterative if record is not None]
        profiles = {record.get("profile") for record in iterative_records}
        gates.append(
            Gate(
                "iterative_profile_consistent",
                len(profiles) == 1,
                sorted(profiles),
                1,
                "records",
            )
        )
        for name, record in zip(iterative_ids, iterative_records, strict=True):
            config_mapping = {
                "profile": "profile",
                "mpi_size": "mpi_size",
                "coarse_slabs": "coarse_slabs",
                "coarse_dimension": "coarse_dimension",
                "num_slabs": "num_physical_slabs",
                "overlap_layers": "overlap_layers",
                "absorption_shift": "absorption_shift",
                "ilu_levels": "ilu_levels",
                "smoother_iterations": "smoother_iterations",
                "restart": "restart",
                "rtol": "rtol",
                "max_it": "max_it",
            }
            config_differences = {
                record_key: {
                    "record": record.get(record_key),
                    "config": canonical_config[config_key],
                }
                for record_key, config_key in config_mapping.items()
                if record.get(record_key) != canonical_config[config_key]
            }
            gates.append(
                Gate(
                    f"record_matches_canonical_config:{name}",
                    not config_differences,
                    config_differences or "match",
                    "all canonical profile fields match",
                    name,
                )
            )
            metadata = record.get("metadata", {})
            provenance_fields = {
                "actual_source_command": metadata.get("actual_source_command"),
                "actual_source_artifact_root": metadata.get(
                    "actual_source_artifact_root"
                ),
                "canonical_rerun_command": metadata.get("canonical_rerun_command"),
                "canonical_artifact_root": metadata.get("canonical_artifact_root"),
                "artifact_provenance": metadata.get("artifact_provenance"),
            }
            missing_provenance = [
                key for key, value in provenance_fields.items() if value in (None, "")
            ]
            gates.append(
                Gate(
                    f"artifact_provenance_complete:{name}",
                    not missing_provenance,
                    missing_provenance or "complete",
                    "actual and canonical source fields present",
                    name,
                )
            )
            artifact_consistent = (
                metadata.get("command") == metadata.get("actual_source_command")
                and record.get("artifact_root")
                == metadata.get("actual_source_artifact_root")
                and metadata.get("canonical_artifact_root")
                == canonical_config.get("artifact_root")
                and str(metadata.get("canonical_artifact_root", ""))
                in str(metadata.get("canonical_rerun_command", ""))
            )
            gates.append(
                Gate(
                    f"artifact_provenance_consistent:{name}",
                    artifact_consistent,
                    {
                        "command_is_actual": metadata.get("command")
                        == metadata.get("actual_source_command"),
                        "record_root_is_actual": record.get("artifact_root")
                        == metadata.get("actual_source_artifact_root"),
                        "canonical_root": metadata.get("canonical_artifact_root"),
                    },
                    "actual source and canonical rerun identities are not conflated",
                    name,
                )
            )
            clean_provenance = str(metadata.get("provenance", "")).startswith(
                "clean_rerun"
            )
            gates.append(
                Gate(
                    f"clean_rerun_git_clean:{name}",
                    (not clean_provenance) or metadata.get("git_dirty") is False,
                    metadata.get("git_dirty"),
                    False,
                    name,
                )
            )
            gates.extend(
                (
                    Gate(
                        f"qualified_profile:{name}",
                        record.get("qualified_profile") is True
                        and not record.get("qualification_deviations"),
                        {
                            "qualified": record.get("qualified_profile"),
                            "deviations": record.get("qualification_deviations"),
                        },
                        "qualified=true and no deviations",
                        name,
                    ),
                    Gate(
                        f"ksp_converged:{name}",
                        int(record.get("ksp_reason", 0)) > 0,
                        record.get("ksp_reason"),
                        "> 0",
                        name,
                    ),
                    Gate(
                        f"coarse_condition:{name}",
                        record.get("coarse_condition") is not None
                        and float(record["coarse_condition"])
                        <= expected["coarse_condition_max"],
                        record.get("coarse_condition"),
                        expected["coarse_condition_max"],
                        name,
                    ),
                    Gate(
                        f"physical_model:{name}",
                        record.get("physical_model")
                        == canonical_config.get("physical_model"),
                        record.get("physical_model"),
                        canonical_config.get("physical_model"),
                        name,
                    ),
                )
            )
            reported = float(record["reported_relative_residual"])
            condensed = float(record["condensed_true_residual"])
            full = float(record["full_augmented_true_residual"])
            gates.extend(
                (
                    Gate(
                        f"residual_max:{name}",
                        max(reported, condensed, full)
                        <= expected["full_augmented_true_residual_max"],
                        max(reported, condensed, full),
                        expected["full_augmented_true_residual_max"],
                        name,
                    ),
                    Gate(
                        f"reported_condensed_match:{name}",
                        _relative_difference(reported, condensed)
                        <= expected["reported_condensed_relative_difference_max"],
                        _relative_difference(reported, condensed),
                        expected["reported_condensed_relative_difference_max"],
                        name,
                    ),
                    Gate(
                        f"reported_full_match:{name}",
                        _relative_difference(reported, full)
                        <= expected["reported_full_relative_difference_max"],
                        _relative_difference(reported, full),
                        expected["reported_full_relative_difference_max"],
                        name,
                    ),
                    Gate(
                        f"coarse_rank:{name}",
                        record.get("coarse_rank") == expected["coarse_rank_required"],
                        record.get("coarse_rank"),
                        expected["coarse_rank_required"],
                        name,
                    ),
                )
            )
            official = record.get("official_rta") or {}
            gates.append(
                Gate(
                    f"official_rta:{name}",
                    all(
                        official.get(key) is not None
                        for key in ("R_total", "T_total", "A_volume_total")
                    ),
                    sorted(official),
                    "R_total,T_total,A_volume_total",
                    name,
                )
            )
            closure = official.get("energy_closure_error")
            gates.append(
                Gate(
                    f"energy_closure:{name}",
                    closure is not None
                    and abs(float(closure)) <= expected["energy_closure_abs_max"],
                    closure,
                    expected["energy_closure_abs_max"],
                    name,
                )
            )
        counts = [int(record["iterations"]) for record in iterative_records]
        ratio = max(counts) / min(counts)
        gates.append(
            Gate(
                "iteration_ratio_h5_h3_h2",
                ratio <= expected["iteration_ratio_h5_h3_h2_max"],
                ratio,
                expected["iteration_ratio_h5_h3_h2_max"],
                "iterative records",
            )
        )
        h2_rss = _iterative_peak_rss(iterative_records[2])
        gates.append(
            Gate(
                "h2_peak_total_rss_gb",
                h2_rss is not None and h2_rss <= expected["h2_peak_total_rss_gb_max"],
                h2_rss,
                expected["h2_peak_total_rss_gb_max"],
                iterative_ids[2],
            )
        )

    case060_expected = _load_json(
        cases_root / "060_multilevel_hcurl_iterative_solver" / "expected" / "gates.json"
    )
    task030_ids = {
        "h5": "task030_compact_h5",
        "h3": "task030_compact_h3",
        "h2": "task030_compact_h2",
    }
    task030 = {label: records.get(name) for label, name in task030_ids.items()}
    task030_present = all(record is not None for record in task030.values())
    gates.append(
        Gate(
            "task030_h5_h3_h2_present",
            task030_present,
            task030_present,
            True,
            ",".join(task030_ids.values()),
        )
    )
    if task030_present:
        contract = case060_expected["record_contract"]
        numeric = case060_expected["numeric_common"]
        direct_ids = {
            "h5": "l3_direct_h5",
            "h3": "l3_direct_h3",
            "h2": "l3_direct_h2",
        }
        canonical_iterative_ids = {
            "h5": "l3_iterative_h5",
            "h3": "l3_iterative_h3",
            "h2": "l3_iterative_h2",
        }
        for label, benchmark_id in task030_ids.items():
            record = task030[label]
            assert record is not None
            metadata = record.get("metadata") or {}
            artifact_hash = metadata.get("source_artifact_sha256")
            artifact_path = ROOT / str(record.get("source_artifact", ""))
            observed_artifact_hash = (
                _sha256(artifact_path) if artifact_path.is_file() else None
            )
            hash_format_ok = (
                isinstance(artifact_hash, str)
                and re.fullmatch(
                    contract["source_artifact_sha256_pattern"], artifact_hash
                )
                is not None
            )
            artifact_hash_ok = hash_format_ok and (
                observed_artifact_hash is None
                or observed_artifact_hash == artifact_hash
            )
            gates.append(
                Gate(
                    f"task030_source_artifact_sha256:{benchmark_id}",
                    artifact_hash_ok,
                    observed_artifact_hash or "heavy artifact unavailable by policy",
                    artifact_hash,
                    str(record.get("source_artifact")),
                )
            )
            if label in set(contract["clean_rerun_labels"]):
                provenance_qualified = (
                    metadata.get("commit_sha")
                    == contract["clean_final_head_commit_sha"]
                    and metadata.get("git_dirty") is False
                    and metadata.get("tracked_source_dirty") is False
                    and metadata.get("tracked_source_verification")
                    == "host_git_clean_attestation"
                    and metadata.get("verified_clean_sha")
                    == contract["clean_final_head_commit_sha"]
                    and metadata.get("provenance") == "clean_rerun"
                    and bool(metadata.get("provenance_qualification"))
                    and bool(metadata.get("actual_source_artifact_root"))
                    and metadata.get("container_image") != "unknown"
                    and metadata.get("container_digest") != "unknown"
                )
                expected_provenance = (
                    "clean final implementation commit with full-SHA host attestation"
                )
            else:
                equivalence = metadata.get("clean_final_head_equivalence") or {}
                h5_metadata = (task030["h5"] or {}).get("metadata") or {}
                h3_metadata = (task030["h3"] or {}).get("metadata") or {}
                provenance_qualified = (
                    metadata.get("git_dirty") is True
                    and metadata.get("tracked_source_dirty") is True
                    and metadata.get("provenance")
                    == "working_tree_source_artifact_recovered_without_rerun"
                    and metadata.get("evidence_identity")
                    == contract["h2_evidence_identity"]
                    and equivalence.get("implementation_commit_sha")
                    == contract["clean_final_head_commit_sha"]
                    and equivalence.get("h5_source_artifact_sha256")
                    == h5_metadata.get("source_artifact_sha256")
                    and equivalence.get("h3_source_artifact_sha256")
                    == h3_metadata.get("source_artifact_sha256")
                    and equivalence.get("candidate_identity_match") is True
                    and equivalence.get("physical_and_modal_identity_match") is True
                    and bool(metadata.get("provenance_qualification"))
                    and bool(metadata.get("actual_source_artifact_root"))
                    and metadata.get("container_image") != "unknown"
                    and metadata.get("container_digest") != "unknown"
                )
                expected_provenance = (
                    "explicit reviewed historical dirty-worktree h2 exemption linked "
                    "to clean final-HEAD h5/h3 equivalence"
                )
            gates.append(
                Gate(
                    f"task030_provenance_qualified:{benchmark_id}",
                    provenance_qualified,
                    {
                        "git_dirty": metadata.get("git_dirty"),
                        "tracked_source_dirty": metadata.get("tracked_source_dirty"),
                        "provenance": metadata.get("provenance"),
                        "evidence_identity": metadata.get("evidence_identity"),
                        "commit_sha": metadata.get("commit_sha"),
                    },
                    expected_provenance,
                    benchmark_id,
                )
            )
            relation = _commit_relation(
                metadata.get("commit_sha"), metadata.get("provenance")
            )
            gates.append(
                Gate(
                    f"task030_source_commit_relation:{benchmark_id}",
                    relation in set(expected["record_commit_relations_accepted"]),
                    relation,
                    sorted(expected["record_commit_relations_accepted"]),
                    benchmark_id,
                )
            )
            identity_ok = (
                record.get("profile_identity") == contract["profile_identity"]
                and record.get("final_solver_identity")
                == contract["final_solver_identity"]
                and record.get("hierarchy_infrastructure_status")
                == contract["hierarchy_infrastructure_status"]
                and record.get("p_h_multigrid_solver_disposition")
                == contract["p_h_multigrid_solver_disposition"]
            )
            gates.append(
                Gate(
                    f"task030_solver_identity:{benchmark_id}",
                    identity_ok,
                    {
                        "profile": record.get("profile_identity"),
                        "final_solver": record.get("final_solver_identity"),
                        "hierarchy": record.get("hierarchy_infrastructure_status"),
                        "p_h_solver": record.get("p_h_multigrid_solver_disposition"),
                    },
                    {
                        "profile": contract["profile_identity"],
                        "final_solver": contract["final_solver_identity"],
                        "hierarchy": contract["hierarchy_infrastructure_status"],
                        "p_h_solver": contract["p_h_multigrid_solver_disposition"],
                    },
                    benchmark_id,
                )
            )
            qualification_ok = record.get("qualified_profile") is False and bool(
                record.get("qualification_deviations")
            )
            gates.append(
                Gate(
                    f"task030_explicit_opt_in_identity:{benchmark_id}",
                    qualification_ok,
                    {
                        "qualified_profile": record.get("qualified_profile"),
                        "deviations": record.get("qualification_deviations"),
                    },
                    "qualified_profile=false with explicit deviations",
                    benchmark_id,
                )
            )
            modal = record.get("modal_identity") or {}
            common_contract_ok = (
                record.get("ordinary_default_changed")
                is contract["ordinary_default_changed"]
                and record.get("n_aux") == contract["n_aux"]
                and modal.get("n_aux_before_condensation") == contract["n_aux"]
                and record.get("physical_model")
                == canonical_config.get("physical_model")
            )
            gates.append(
                Gate(
                    f"task030_frozen_contract:{benchmark_id}",
                    common_contract_ok,
                    {
                        "ordinary_default_changed": record.get(
                            "ordinary_default_changed"
                        ),
                        "n_aux": record.get("n_aux"),
                        "modal_n_aux": modal.get("n_aux_before_condensation"),
                        "physical_model_match": record.get("physical_model")
                        == canonical_config.get("physical_model"),
                    },
                    "ordinary default false, same physical model and 80 modes",
                    benchmark_id,
                )
            )
            gates.append(
                Gate(
                    f"task030_ksp_converged:{benchmark_id}",
                    int(record.get("ksp_reason", 0)) > 0,
                    record.get("ksp_reason"),
                    "> 0",
                    benchmark_id,
                )
            )
            reported = float(record["reported_relative_residual"])
            condensed = float(record["condensed_true_residual"])
            full = float(record["full_augmented_true_residual"])
            maximum_residual = max(reported, condensed, full)
            maximum_mismatch = max(
                _relative_difference(reported, condensed),
                _relative_difference(reported, full),
            )
            gates.extend(
                (
                    Gate(
                        f"task030_residual_max:{benchmark_id}",
                        maximum_residual <= numeric["full_true_residual_max"],
                        maximum_residual,
                        numeric["full_true_residual_max"],
                        benchmark_id,
                    ),
                    Gate(
                        f"task030_residual_consistency:{benchmark_id}",
                        maximum_mismatch
                        <= numeric["reported_true_relative_difference_max"],
                        maximum_mismatch,
                        numeric["reported_true_relative_difference_max"],
                        benchmark_id,
                    ),
                )
            )
            rta_complete = all(
                record.get(key) is not None
                for key in ("R_total", "T_total", "A_volume_total")
            )
            gates.append(
                Gate(
                    f"task030_official_rta:{benchmark_id}",
                    rta_complete,
                    rta_complete,
                    True,
                    benchmark_id,
                )
            )
            closure = record.get("energy_closure_error")
            gates.append(
                Gate(
                    f"task030_energy_closure:{benchmark_id}",
                    closure is not None
                    and abs(float(closure)) <= numeric["energy_closure_abs_max"],
                    closure,
                    numeric["energy_closure_abs_max"],
                    benchmark_id,
                )
            )
            direct = records.get(direct_ids[label])
            direct_delta = float("inf")
            if direct is not None and rta_complete:
                direct_delta = max(
                    abs(float(record[key]) - float(direct[key]))
                    for key in ("R_total", "T_total", "A_volume_total")
                )
            gates.append(
                Gate(
                    f"task030_rta_delta_from_direct:{benchmark_id}",
                    direct_delta <= numeric["rta_delta_from_direct_max"],
                    direct_delta,
                    numeric["rta_delta_from_direct_max"],
                    f"{benchmark_id},{direct_ids[label]}",
                )
            )

        task030_h5 = task030["h5"]
        task030_h3 = task030["h3"]
        task030_h2 = task030["h2"]
        assert task030_h5 is not None
        assert task030_h3 is not None
        assert task030_h2 is not None
        canonical_h3 = records.get(canonical_iterative_ids["h3"])
        task030_h3_peak = _iterative_peak_rss(task030_h3)
        canonical_h3_peak = (
            _iterative_peak_rss(canonical_h3) if canonical_h3 is not None else None
        )
        h3_memory_reduction = (
            None
            if task030_h3_peak is None or canonical_h3_peak is None
            else (canonical_h3_peak - task030_h3_peak) / canonical_h3_peak
        )
        h3_memory_pass = task030_h3_peak is not None and (
            task030_h3_peak <= case060_expected["h3_full"]["peak_rss_gb_max"]
            or (
                h3_memory_reduction is not None
                and h3_memory_reduction
                >= case060_expected["h3_full"]["minimum_memory_reduction_fraction"]
            )
        )
        gates.append(
            Gate(
                "task030_h3_memory_gate",
                h3_memory_pass,
                {
                    "peak_rss_gb": task030_h3_peak,
                    "relative_reduction": h3_memory_reduction,
                    "absolute_gate_pass": task030_h3_peak is not None
                    and task030_h3_peak
                    <= case060_expected["h3_full"]["peak_rss_gb_max"],
                    "relative_gate_pass": h3_memory_reduction is not None
                    and h3_memory_reduction
                    >= case060_expected["h3_full"]["minimum_memory_reduction_fraction"],
                },
                "RSS <= 3.8 GB OR reduction >= 25%",
                "task030_compact_h3,l3_iterative_h3",
            )
        )
        h3_h5_ratio = float(task030_h3["iterations"]) / float(task030_h5["iterations"])
        gates.append(
            Gate(
                "task030_h3_h5_iteration_ratio",
                h3_h5_ratio
                <= case060_expected["h3_full"]["h3_to_h5_iteration_ratio_max"],
                h3_h5_ratio,
                case060_expected["h3_full"]["h3_to_h5_iteration_ratio_max"],
                "task030_compact_h5,task030_compact_h3",
            )
        )
        task030_h2_peak = _iterative_peak_rss(task030_h2)
        gates.append(
            Gate(
                "task030_h2_peak_rss",
                task030_h2_peak is not None
                and task030_h2_peak <= case060_expected["h2_full"]["peak_rss_gb_max"],
                task030_h2_peak,
                case060_expected["h2_full"]["peak_rss_gb_max"],
                "task030_compact_h2",
            )
        )
        strong_claim_absent = (
            task030_h2.get("strong_workstation_success")
            is contract["strong_workstation_success"]
            and "strong_workstation_success"
            not in str(task030_h2.get("classification", ""))
            and task030_h2.get("preferred_iteration_target_pass") is False
        )
        gates.append(
            Gate(
                "task030_h2_classification_not_strong",
                strong_claim_absent,
                {
                    "classification": task030_h2.get("classification"),
                    "strong_workstation_success": task030_h2.get(
                        "strong_workstation_success"
                    ),
                    "preferred_iteration_target_pass": task030_h2.get(
                        "preferred_iteration_target_pass"
                    ),
                },
                "strong success false and preferred iteration target missed",
                "task030_compact_h2",
            )
        )

    case070 = cases_root / "070_compact_physical_slab_memory_optimization"
    case070_expected = _load_json(case070 / "expected" / "gates.json")
    case070_config = _load_json(case070 / "config.json")
    task031_ids = {
        "h5": "task031_compact_h5",
        "h3": "task031_compact_h3",
        "h2": "task031_compact_h2",
    }
    task031 = {label: records.get(name) for label, name in task031_ids.items()}
    task031_present = all(record is not None for record in task031.values())
    gates.append(
        Gate(
            "task031_h5_h3_h2_present",
            task031_present,
            task031_present,
            True,
            ",".join(task031_ids.values()),
        )
    )
    if task031_present:
        contract = case070_expected["record_contract"]
        numeric = case070_expected["numeric_common"]
        direct_ids = {"h5": "l3_direct_h5", "h3": "l3_direct_h3", "h2": "l3_direct_h2"}
        for label, benchmark_id in task031_ids.items():
            record = task031[label]
            assert record is not None
            metadata = record.get("metadata") or {}
            source_hash = metadata.get("source_artifact_sha256")
            sampler_hash = metadata.get("memory_sampler_sha256")
            hash_pattern = contract["source_artifact_sha256_pattern"]
            source_path = ROOT / str(record.get("source_artifact", ""))
            sampler_path = ROOT / str(record.get("memory_sampler_artifact", ""))
            observed_source_hash = _sha256(source_path) if source_path.is_file() else None
            observed_sampler_hash = _sha256(sampler_path) if sampler_path.is_file() else None
            hashes_ok = (
                isinstance(source_hash, str)
                and re.fullmatch(hash_pattern, source_hash) is not None
                and isinstance(sampler_hash, str)
                and re.fullmatch(hash_pattern, sampler_hash) is not None
                and (observed_source_hash is None or observed_source_hash == source_hash)
                and (observed_sampler_hash is None or observed_sampler_hash == sampler_hash)
            )
            gates.append(
                Gate(
                    f"task031_artifact_hashes:{benchmark_id}",
                    hashes_ok,
                    {
                        "source": observed_source_hash or "heavy artifact unavailable",
                        "sampler": observed_sampler_hash or "heavy artifact unavailable",
                    },
                    {"source": source_hash, "sampler": sampler_hash},
                    benchmark_id,
                )
            )
            provenance_ok = (
                metadata.get("commit_sha") == contract["clean_source_commit_sha"]
                and metadata.get("verified_clean_sha")
                == contract["clean_source_commit_sha"]
                and metadata.get("git_dirty") is False
                and metadata.get("tracked_source_dirty") is False
                and metadata.get("tracked_source_verification")
                == "host_git_clean_attestation"
                and metadata.get("provenance") == "clean_rerun"
                and metadata.get("container_image") != "unknown"
                and str(metadata.get("container_digest", "")).startswith("sha256:")
                and bool(metadata.get("command"))
                and bool(metadata.get("timestamp_utc"))
                and bool(metadata.get("host_environment_id"))
            )
            gates.append(
                Gate(
                    f"task031_clean_provenance:{benchmark_id}",
                    provenance_ok,
                    {
                        "commit": metadata.get("commit_sha"),
                        "dirty": metadata.get("tracked_source_dirty"),
                        "image": metadata.get("container_image"),
                        "digest": metadata.get("container_digest"),
                    },
                    "clean full-SHA plus real image/digest/command/time/host",
                    benchmark_id,
                )
            )
            relation = _commit_relation(metadata.get("commit_sha"), metadata.get("provenance"))
            gates.append(
                Gate(
                    f"task031_source_commit_relation:{benchmark_id}",
                    relation in set(expected["record_commit_relations_accepted"]),
                    relation,
                    sorted(expected["record_commit_relations_accepted"]),
                    benchmark_id,
                )
            )
            identity_ok = (
                record.get("profile_identity") == contract["profile_identity"]
                and record.get("ordinary_default_changed")
                is contract["ordinary_default_changed"]
                and record.get("qualified_profile") is False
                and record.get("physical_model_match") is True
                and record.get("n_aux") == contract["n_aux"]
                and record.get("mpi_size") == 4
                and record.get("ksp_type") == "fgmres"
                and record.get("restart") == 90
                and record.get("num_slabs") == 16
                and float(record.get("overlap_layers")) == 0.125
                and record.get("matrix_free_fine") is True
                and record.get("fine_matrix_present_during_solve") is False
                and record.get("compact_lifecycle") is True
                and case070_config.get("physical_model")
                == canonical_config.get("physical_model")
            )
            gates.append(
                Gate(
                    f"task031_frozen_solver_identity:{benchmark_id}",
                    identity_ok,
                    {
                        "profile": record.get("profile_identity"),
                        "n_aux": record.get("n_aux"),
                        "ksp": record.get("ksp_type"),
                        "matrix_free": record.get("matrix_free_fine"),
                        "compact": record.get("compact_lifecycle"),
                    },
                    "same physical model/80 modes, FGMRES90, matrix-free fine, compact lifecycle",
                    benchmark_id,
                )
            )
            residuals = [
                float(record["reported_relative_residual"]),
                float(record["condensed_true_residual"]),
                float(record["full_augmented_true_residual"]),
            ]
            residual_max = max(residuals)
            residual_mismatch = max(
                _relative_difference(residuals[0], residuals[1]),
                _relative_difference(residuals[0], residuals[2]),
            )
            gates.extend(
                (
                    Gate(
                        f"task031_ksp_converged:{benchmark_id}",
                        int(record.get("ksp_reason", 0)) > 0,
                        record.get("ksp_reason"),
                        "> 0",
                        benchmark_id,
                    ),
                    Gate(
                        f"task031_residual_max:{benchmark_id}",
                        residual_max <= numeric["residual_max"],
                        residual_max,
                        numeric["residual_max"],
                        benchmark_id,
                    ),
                    Gate(
                        f"task031_residual_consistency:{benchmark_id}",
                        residual_mismatch
                        <= numeric["reported_true_relative_difference_max"],
                        residual_mismatch,
                        numeric["reported_true_relative_difference_max"],
                        benchmark_id,
                    ),
                    Gate(
                        f"task031_fine_action:{benchmark_id}",
                        float(record["fine_action_relative_error"])
                        <= numeric["fine_action_relative_error_max"],
                        record["fine_action_relative_error"],
                        numeric["fine_action_relative_error_max"],
                        benchmark_id,
                    ),
                )
            )
            rta_complete = all(
                record.get(key) is not None
                for key in ("R_total", "T_total", "A_volume_total")
            )
            direct = records.get(direct_ids[label])
            direct_delta = float("inf")
            if direct is not None and rta_complete:
                direct_delta = max(
                    abs(float(record[key]) - float(direct[key]))
                    for key in ("R_total", "T_total", "A_volume_total")
                )
            gates.extend(
                (
                    Gate(
                        f"task031_official_rta:{benchmark_id}",
                        rta_complete,
                        rta_complete,
                        True,
                        benchmark_id,
                    ),
                    Gate(
                        f"task031_energy_closure:{benchmark_id}",
                        abs(float(record["energy_closure_error"]))
                        <= numeric["energy_closure_abs_max"],
                        record["energy_closure_error"],
                        numeric["energy_closure_abs_max"],
                        benchmark_id,
                    ),
                    Gate(
                        f"task031_rta_delta_from_direct:{benchmark_id}",
                        direct_delta <= numeric["rta_delta_from_direct_max"],
                        direct_delta,
                        numeric["rta_delta_from_direct_max"],
                        f"{benchmark_id},{direct_ids[label]}",
                    ),
                    Gate(
                        f"task031_external_memory_and_swap:{benchmark_id}",
                        float(record.get("simultaneous_worker_peak_gib", 0.0)) > 0.0
                        and int(record.get("swap_in_delta_pages", -1)) == 0
                        and int(record.get("swap_out_delta_pages", -1)) == 0,
                        {
                            "worker_peak_gib": record.get("simultaneous_worker_peak_gib"),
                            "swap_in": record.get("swap_in_delta_pages"),
                            "swap_out": record.get("swap_out_delta_pages"),
                        },
                        "positive simultaneous peak and zero swap",
                        benchmark_id,
                    ),
                )
            )

        h3 = task031["h3"]
        h2 = task031["h2"]
        assert h3 is not None and h2 is not None
        task030_h3 = records.get("task030_compact_h3")
        task030_h2 = records.get("task030_compact_h2")
        h3_peak = float(h3["simultaneous_worker_peak_gib"])
        h3_baseline = _iterative_peak_rss(task030_h3) if task030_h3 else None
        h3_reduction = (
            None
            if h3_baseline is None
            else (float(h3_baseline) - h3_peak) / float(h3_baseline)
        )
        gates.append(
            Gate(
                "task031_h3_memory_gate",
                h3_peak <= case070_expected["h3"]["simultaneous_worker_peak_gib_max"]
                and h3_reduction is not None
                and h3_reduction
                >= case070_expected["h3"]["minimum_reduction_vs_task030"],
                {"peak_gib": h3_peak, "reduction": h3_reduction},
                "peak <=3.50 GiB and reduction >=8% vs Task030",
                "task031_compact_h3,task030_compact_h3",
            )
        )
        prediction = _load_json(case070 / "records" / "h2_prediction.json")
        prediction_ok = (
            prediction.get("h3_full_numeric_pass") is True
            and float(prediction["h3_memory_reduction_fraction"])
            >= case070_expected["h3"]["minimum_reduction_vs_task030"]
            and float(prediction["affine_dof_central_gib"])
            <= case070_expected["h2_launch"]["affine_dof_prediction_gib_max"]
            and float(prediction["task030_ratio_transfer_central_gib"])
            <= case070_expected["h2_launch"]["task030_ratio_prediction_gib_max"]
            and float(prediction["conservative_upper_gib"])
            <= case070_expected["h2_launch"]["conservative_upper_gib_max"]
            and prediction.get("clean_source") is True
            and prediction.get("same_n_aux") == 80
            and prediction.get("launch_allowed") is True
        )
        gates.append(
            Gate(
                "task031_h2_launch_gate",
                prediction_ok,
                prediction,
                "two central predictions <=8.8 GiB and upper <=10 GiB",
                "cases/070_compact_physical_slab_memory_optimization/records/h2_prediction.json",
            )
        )
        h2_peak = float(h2["simultaneous_worker_peak_gib"])
        h2_baseline = _iterative_peak_rss(task030_h2) if task030_h2 else None
        h2_reduction = (
            None
            if h2_baseline is None
            else (float(h2_baseline) - h2_peak) / float(h2_baseline)
        )
        gates.append(
            Gate(
                "task031_h2_strong_memory_success",
                h2_peak <= case070_expected["h2"]["strong_success_gib_max"]
                and h2.get("classification")
                == "strong_memory_success_slow_but_memory_efficient"
                and h2.get("warning_triggered") is False
                and h2.get("terminated_for_memory") is False,
                {
                    "peak_gib": h2_peak,
                    "reduction": h2_reduction,
                    "classification": h2.get("classification"),
                },
                "converged h2 <=8.0 GiB without warning/termination",
                "task031_compact_h2,task030_compact_h2",
            )
        )
        pc_contract = _load_json(case070 / "records" / "pc_linearity.json")
        pc_ok = (
            float(pc_contract["task030_flexible_pc"]["linearity_relative_error"])
            > float(pc_contract["task030_flexible_pc"]["gate"])
            and pc_contract["task030_flexible_pc"]["result"] == "fail"
            and float(pc_contract["fixed_richardson_variant"]["linearity_relative_error"])
            <= 1.0e-11
            and pc_contract["fixed_richardson_variant"]["solver_result"]
            == "numeric_negative"
        )
        gates.append(
            Gate(
                "task031_pc_legality_contract",
                pc_ok,
                pc_contract["final_disposition"],
                "nonlinear PC requires FGMRES; linear substitute is numeric-negative",
                "cases/070_compact_physical_slab_memory_optimization/records/pc_linearity.json",
            )
        )
        components = _load_json(case070 / "records" / "memory_components.json")
        factor_contract = components["factor_deduplication"]
        gates.append(
            Gate(
                "task031_exact_factor_dedup_negative",
                factor_contract.get("unique_factor_classes") == 16
                and factor_contract.get("exact_duplicate_factor_count") == 0
                and "approximate sharing prohibited" in factor_contract.get("disposition", ""),
                factor_contract,
                "16 unique exact factors and no approximate sharing",
                "cases/070_compact_physical_slab_memory_optimization/records/memory_components.json",
            )
        )

    for label in ("h5", "h3"):
        direct = records.get(f"l3_direct_{label}")
        iterative_record = records.get(f"l3_iterative_{label}")
        if direct is None or iterative_record is None:
            continue
        official = iterative_record.get("official_rta") or {}
        for quantity, direct_key in (
            ("R", "R_total"),
            ("T", "T_total"),
            ("A_volume", "A_volume_total"),
        ):
            delta = abs(float(direct[direct_key]) - float(official[direct_key]))
            tolerance = expected["direct_iterative_abs_tolerance"][label][quantity]
            gates.append(
                Gate(
                    f"direct_iterative_{quantity}:{label}",
                    delta <= tolerance,
                    delta,
                    tolerance,
                    f"l3_direct_{label},l3_iterative_{label}",
                )
            )

    h2_direct = records.get("l3_direct_h2")
    h2_status = None if h2_direct is None else h2_direct.get("status")
    gates.append(
        Gate(
            "h2_direct_reviewed_reference",
            h2_status == "reviewed_reference_not_rerun_in_task028",
            h2_status,
            "reviewed_reference_not_rerun_in_task028",
            "l3_direct_h2",
        )
    )
    environment = _load_json(BENCHMARKS / "environment.json")
    environment_status = environment.get("reproducibility_status")
    gates.append(
        Gate(
            "environment_reproducibility_declared",
            environment_status in {"reproducible", "qualified_local_image"},
            environment_status,
            "reproducible or qualified_local_image",
            "environment.json",
        )
    )
    ordinary = all(
        record.get("ordinary_default_changed") is False
        for record in iterative
        if record
    )
    gates.append(
        Gate(
            "ordinary_default_unchanged", ordinary, ordinary, True, "iterative records"
        )
    )
    return gates, summaries


def _write_outputs(gates: list[Gate], summaries: list[dict[str, Any]]) -> None:
    summary_path = BENCHMARKS / "benchmark_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as stream:
        fieldnames = list(summaries[0])
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)
    payload = {
        "checkout_commit": _git("rev-parse", "HEAD"),
        "checkout_dirty": bool(_git("status", "--short")),
        "checkout_dirty_note": (
            "This reports the checkout at checker execution time. It is independent "
            "of metadata.git_dirty, which records the original benchmark run. Writing "
            "this report can itself make the checkout dirty."
        ),
        "passed": all(gate.passed for gate in gates),
        "passed_count": sum(gate.passed for gate in gates),
        "total_count": len(gates),
        "gates": [gate.__dict__ for gate in gates],
    }
    path = BENCHMARKS / "records" / "benchmark_gate_report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate canonical Task28 benchmark records"
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Check without refreshing summary/report files",
    )
    args = parser.parse_args()
    gates, summaries = evaluate()
    if not args.no_write:
        _write_outputs(gates, summaries)
    failed = [gate for gate in gates if not gate.passed]
    for gate in gates:
        print(f"{'PASS' if gate.passed else 'FAIL'} {gate.name}: {gate.observed!r}")
    print(f"benchmark gates: {len(gates) - len(failed)}/{len(gates)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
