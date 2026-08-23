"""Recompute the Task040 Level-A Gate from one ignored raw run root."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

HARD_STOP_BYTES = 45 * 2**30
MANDATORY_RHO_LIMIT = 1.0
WORST_RHO_LIMIT = 0.95
PREFERRED_RHO_LIMIT = 0.90
ZERO_MAP_LIMIT = 1e-13
REPEAT_LIMIT = 1e-10
LINEARITY_LIMIT = 1e-10
SQUARED_RESIDUAL_ROUNDOFF = 1e-12
ORIGINAL_RHO_CONSISTENCY_LIMIT = 1e-10
GRAM_CONSISTENCY_LIMIT = 1e-10
PREFERRED_LABELS = {
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
}
EXPECTED_LABELS = [
    "physical_side_rhs",
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
]

V1_1_SCHEMA = "task040.v1_1.scalar_krylov.v1"
V1_1_LABELS = [
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
]

__all__ = ["recompute_level_a_gate", "recompute_scalar_krylov_gate"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _complex_pair(value: Any) -> complex | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not all(_finite(item) for item in value):
        return None
    return complex(float(value[0]), float(value[1]))


def _complex_matrix(value: Any, size: int) -> Any:
    if not isinstance(value, list) or len(value) != size:
        return None
    rows = []
    for row in value:
        if not isinstance(row, list) or len(row) != size:
            return None
        parsed = [_complex_pair(item) for item in row]
        if any(item is None for item in parsed):
            return None
        rows.append(parsed)
    return rows


def recompute_level_a_gate(run_root: str | Path) -> dict[str, Any]:
    root = Path(run_root)
    worker_path = root / "worker" / "run_summary.json"
    watchdog_path = root / "watchdog_summary.json"
    samples_path = root / "process_tree_samples.jsonl"
    worker = _read_json(worker_path)
    watchdog = _read_json(watchdog_path)
    reports = worker["action"]["reports"]
    labels = [record["label"] for record in reports]
    mandatory = [record for record in reports if record["label"] != "physical_side_rhs"]
    rho_by_label = {
        record["label"]: record.get("true_residual_relative") for record in reports
    }
    mandatory_rhos = [record["true_residual_relative"] for record in mandatory]
    worst_rho = max(mandatory_rhos)
    physical = next(
        record for record in reports if record["label"] == "physical_side_rhs"
    )
    action_identity = worker["action"]["action_identity"]
    factors = worker["action"]["factor_inventory"]
    masses = worker["interface_masses"]
    samples = [
        json.loads(line)
        for line in samples_path.read_text().splitlines()
        if line.strip()
    ]
    peak_rss = max(
        sample["resource_authority"]["memory_authority_bytes"] for sample in samples
    )
    peak_swap = max(
        sample["resource_authority"]["process_tree"]["swap_bytes"] for sample in samples
    )
    checks = {
        "source_labels": labels == EXPECTED_LABELS and len(labels) == len(set(labels)),
        "finite": all(
            record["finite"]
            and _finite(record["source_norm"])
            and _finite(record["output_norm"])
            and _finite(record["true_residual_norm"])
            for record in mandatory
        )
        and physical["finite"]
        and _finite(physical["output_norm"]),
        "zero_map": physical["source_norm"] <= ZERO_MAP_LIMIT
        and physical["output_norm"] <= ZERO_MAP_LIMIT,
        "repeat": all(record["repeat_error"] <= REPEAT_LIMIT for record in reports),
        "linearity": worker["action"]["gate"]["linearity_relative_error"]
        <= LINEARITY_LIMIT,
        "restriction_prolongation": action_identity["restriction_prolongation_pass"]
        and not action_identity["global_numpy_copy"]
        and not action_identity["subdomain_vectors_global_numpy_copy"],
        "bare_operator_unchanged": action_identity["bare_operator_unchanged"],
        "interface_mass_support": len(masses) == 2
        and all(
            mass["finite"]
            and mass["support_sets_exact_match"]
            and mass["bare_operator_unchanged"]
            for mass in masses
        ),
        "factor_inventory": factors["cross_section_factor_count_ready"] == 3
        and factors["full_side_exact_factor_count"] == 0
        and factors["global_direct_factor_count"] == 0
        and factors["nested_ksp_count"] == 0
        and factors["system_direct_factor_count_observed"] == 0
        and not factors["system_global_A_materialized_observed"]
        and factors["oracle_only"]
        and not factors["scalable_candidate"]
        and worker["cleanup"]["factor_owner"]["after"]["factor_count_after_cleanup"]
        == 0,
        "mandatory_rho": all(rho < MANDATORY_RHO_LIMIT for rho in mandatory_rhos),
        "worst_rho": worst_rho <= WORST_RHO_LIMIT,
        "preferred_rho": all(
            rho_by_label[label] <= PREFERRED_RHO_LIMIT for label in PREFERRED_LABELS
        ),
        "watchdog": watchdog["return_code"] == 0
        and watchdog["termination_reason"] == "natural_exit"
        and watchdog["run_summary_present"]
        and watchdog["all_status_readable"]
        and watchdog["source_sha"] == worker["source_sha"]
        and watchdog["run_summary_sha256"] == _sha256(worker_path),
        "resource": peak_rss < HARD_STOP_BYTES
        and peak_swap == 0
        and watchdog["peak_swap_bytes"] == 0
        and watchdog["peak_dedicated_cgroup_swap_bytes"] == 0,
    }
    raw_paths = {
        "watchdog_summary.json": watchdog_path,
        "worker/run_summary.json": worker_path,
        "process_tree_samples.jsonl": samples_path,
        "memory_stage_markers.raw.jsonl": root / "memory_stage_markers.raw.jsonl",
        "memory_stages.jsonl": root / "memory_stages.jsonl",
    }
    return {
        "schema": "task040.level_a.recomputed_gate.v1",
        "source_sha": worker["source_sha"],
        "raw_hashes": {name: _sha256(path) for name, path in raw_paths.items()},
        "rho_by_label": rho_by_label,
        "worst_mandatory_rho": worst_rho,
        "peak_rss_bytes": peak_rss,
        "peak_rss_gib": peak_rss / 2**30,
        "peak_swap_bytes": peak_swap,
        "wall_seconds": max(sample["elapsed_seconds"] for sample in samples),
        "factor_inventory": {
            "cross_section_ready": factors["cross_section_factor_count_ready"],
            "full_side": factors["full_side_exact_factor_count"],
            "global_direct": factors["global_direct_factor_count"],
            "nested_ksp": factors["nested_ksp_count"],
            "cleanup_after": worker["cleanup"]["factor_owner"]["after"][
                "factor_count_after_cleanup"
            ],
        },
        "checks": checks,
        "gate_pass": all(checks.values()),
    }


def recompute_scalar_krylov_gate(run_root: str | Path) -> dict[str, Any]:
    """Recompute V1-1 scalar contractions and fixed batch-FGMRES Gate."""

    root = Path(run_root)
    worker_path = root / "worker" / "run_summary.json"
    worker = _read_json(worker_path)
    if worker.get("schema") != V1_1_SCHEMA:
        raise ValueError("run root is not a V1-1 scalar-krylov record")
    base = recompute_level_a_gate(root)
    raw = worker["action"].get("scalar_contractions")
    screen = worker.get("scalar_screen")
    labels = list(raw.get("labels", [])) if isinstance(raw, dict) else []
    per_source = raw.get("per_source", {}) if isinstance(raw, dict) else {}
    bhb = _complex_matrix(raw.get("BHB") if isinstance(raw, dict) else None, 5)
    bhy = _complex_matrix(raw.get("BHY") if isinstance(raw, dict) else None, 5)
    yhy = _complex_matrix(raw.get("YHY") if isinstance(raw, dict) else None, 5)
    contraction_shape = bool(
        labels == V1_1_LABELS
        and isinstance(per_source, dict)
        and all(label in per_source for label in V1_1_LABELS)
        and all(isinstance(per_source[label], dict) for label in V1_1_LABELS)
        and bhb is not None
        and bhy is not None
        and yhy is not None
    )
    contraction_finite = False
    gram_consistency_pass = False
    norm_storage_consistency_pass = False
    original_rho_consistency_pass = False
    derived_by_label: dict[str, dict[str, Any]] = {}
    cross_correlation: list[list[list[float]]] = []
    cross_correlation_abs: list[list[float]] = []
    if contraction_shape:
        contraction_finite = all(
            _finite(per_source[label].get(field))
            for label in V1_1_LABELS
            for field in (
                "source_norm",
                "source_norm_squared",
                "x_norm_squared",
                "y_norm",
                "y_norm_squared",
                "true_residual_norm",
            )
        )
        contraction_finite = contraction_finite and all(
            _finite(value.real) and _finite(value.imag)
            for matrix in (bhb, bhy, yhy)
            for row in matrix
            for value in row
        )
        if contraction_finite:
            gram_consistency_pass = True
            for matrix in (bhb, yhy):
                for row in range(5):
                    gram_consistency_pass = gram_consistency_pass and (
                        abs(matrix[row][row].imag)
                        <= GRAM_CONSISTENCY_LIMIT * max(1.0, abs(matrix[row][row].real))
                    )
                    for column in range(row):
                        defect = abs(
                            matrix[row][column] - matrix[column][row].conjugate()
                        )
                        gram_consistency_pass = gram_consistency_pass and (
                            defect
                            <= GRAM_CONSISTENCY_LIMIT
                            * max(
                                1.0,
                                abs(matrix[row][column]),
                                abs(matrix[column][row]),
                            )
                        )
            norm_storage_consistency_pass = True
            for index, label in enumerate(V1_1_LABELS):
                stored = per_source[label]
                b2 = float(bhb[index][index].real)
                y2 = float(yhy[index][index].real)
                source_norm = float(stored["source_norm"])
                source_norm_squared = float(stored["source_norm_squared"])
                y_norm = float(stored["y_norm"])
                y_norm_squared = float(stored["y_norm_squared"])
                x2 = float(stored["x_norm_squared"])
                norm_scale = max(1.0, b2, y2)
                norm_storage_consistency_pass = (
                    norm_storage_consistency_pass
                    and x2 >= -SQUARED_RESIDUAL_ROUNDOFF * max(1.0, abs(x2))
                    and abs(source_norm_squared - b2)
                    <= GRAM_CONSISTENCY_LIMIT * norm_scale
                    and abs(y_norm_squared - y2) <= GRAM_CONSISTENCY_LIMIT * norm_scale
                    and abs(source_norm * source_norm - b2)
                    <= GRAM_CONSISTENCY_LIMIT * norm_scale
                    and abs(y_norm * y_norm - y2) <= GRAM_CONSISTENCY_LIMIT * norm_scale
                )
            original_rho_consistency_pass = (
                gram_consistency_pass and norm_storage_consistency_pass
            )
    if contraction_shape and contraction_finite:
        for index, label in enumerate(V1_1_LABELS):
            b2 = float(bhb[index][index].real)
            y2 = float(yhy[index][index].real)
            by = bhy[index][index]
            source_norm = math.sqrt(max(b2, 0.0))
            y_norm = math.sqrt(max(y2, 0.0))
            if b2 <= 0.0 or y2 <= 0.0:
                contraction_finite = False
                original_rho_consistency_pass = False
                break
            alpha = by.conjugate() / y2
            rho_star_numerator = b2 - abs(by) ** 2 / y2
            rho_star_scale = max(1.0, b2, abs(by) ** 2 / y2)
            if rho_star_numerator < -SQUARED_RESIDUAL_ROUNDOFF * rho_star_scale:
                contraction_finite = False
                original_rho_consistency_pass = False
                break
            rho_star = math.sqrt(max(rho_star_numerator, 0.0) / b2)
            correlation = abs(by) / (source_norm * y_norm)
            x2 = float(per_source[label]["x_norm_squared"])
            if x2 < -SQUARED_RESIDUAL_ROUNDOFF * max(1.0, abs(x2)):
                contraction_finite = False
                original_rho_consistency_pass = False
                break
            x_norm = math.sqrt(max(x2, 0.0))
            original_rho_numerator = b2 + y2 - 2.0 * float(by.real)
            original_rho_scale = max(1.0, b2, y2, 2.0 * abs(by))
            if original_rho_numerator < -SQUARED_RESIDUAL_ROUNDOFF * original_rho_scale:
                contraction_finite = False
                original_rho_consistency_pass = False
                break
            original_rho = math.sqrt(max(original_rho_numerator, 0.0) / b2)
            reported_rho = float(per_source[label]["true_residual_norm"]) / source_norm
            consistency_error = abs(reported_rho - original_rho)
            original_rho_consistency_pass = (
                original_rho_consistency_pass
                and consistency_error
                <= ORIGINAL_RHO_CONSISTENCY_LIMIT * max(1.0, original_rho)
            )
            derived_by_label[label] = {
                "alpha_star": [float(alpha.real), float(alpha.imag)],
                "rho_star": float(rho_star),
                "correlation": float(correlation),
                "x_over_b": float(x_norm / source_norm),
                "y_over_b": float(y_norm / source_norm),
                "original_rho": float(original_rho),
                "reported_original_rho": float(reported_rho),
                "original_rho_consistency_error": float(consistency_error),
                "alpha_magnitude": float(abs(alpha)),
                "alpha_phase_radians": float(math.atan2(alpha.imag, alpha.real)),
            }
        if contraction_finite:
            cross_correlation = [
                [
                    [
                        float(
                            (
                                bhy[row][column]
                                / math.sqrt(
                                    bhb[row][row].real * yhy[column][column].real
                                )
                            ).real
                        ),
                        float(
                            (
                                bhy[row][column]
                                / math.sqrt(
                                    bhb[row][row].real * yhy[column][column].real
                                )
                            ).imag
                        ),
                    ]
                    for column in range(5)
                ]
                for row in range(5)
            ]
            cross_correlation_abs = [
                [abs(complex(pair[0], pair[1])) for pair in row]
                for row in cross_correlation
            ]

    phase_one = screen.get("phase1", {}) if isinstance(screen, dict) else {}
    phase_two = screen.get("phase2", {}) if isinstance(screen, dict) else {}
    phase_one_gate: dict[str, bool] = {}
    trend_limit = 10.0 ** (-0.25)
    if isinstance(phase_one, dict):
        for label in V1_1_LABELS:
            record = phase_one.get(label, {})
            checkpoints = record.get("checkpoints", {})
            r8 = checkpoints.get("8", {}).get("true_residual_relative")
            r16 = checkpoints.get("16", {}).get("true_residual_relative")
            phase_one_gate[label] = bool(
                all(
                    checkpoints.get(str(iteration), {}).get("finite") is True
                    for iteration in (4, 8, 16)
                )
                and isinstance(r8, (int, float))
                and isinstance(r16, (int, float))
                and math.isfinite(float(r8))
                and math.isfinite(float(r16))
                and float(r16) <= trend_limit * float(r8)
                and record.get("ksp_breakdown") is False
            )
    resource = (
        screen.get("resource_at_phase_boundary", {}) if isinstance(screen, dict) else {}
    )
    resource_pass = bool(
        isinstance(resource, dict)
        and resource.get("all_status_readable") is True
        and isinstance(resource.get("rss_bytes"), int)
        and int(resource["rss_bytes"]) < HARD_STOP_BYTES
        and resource.get("swap_bytes") == 0
    )
    conditional_32 = bool(
        len(phase_one_gate) == len(V1_1_LABELS)
        and all(phase_one_gate.values())
        and resource_pass
    )

    def phase_integrity(
        phase_records: Any, *, max_it: int, include_32: bool
    ) -> tuple[bool, int]:
        if not isinstance(phase_records, dict) or set(phase_records) != set(
            V1_1_LABELS
        ):
            return False, 0
        expected = {"0", "4", "8", "16"}
        if include_32:
            expected.add("32")
        phase_apply_count = 0
        valid = True
        for label in V1_1_LABELS:
            record = phase_records.get(label)
            checkpoints = (
                record.get("checkpoints") if isinstance(record, dict) else None
            )
            if not isinstance(record, dict) or not isinstance(checkpoints, dict):
                valid = False
                continue
            valid = valid and set(checkpoints) == expected
            valid = valid and record.get("pc_side") == "right"
            valid = valid and record.get("restart") == 32
            valid = valid and record.get("max_it") == max_it
            valid = valid and record.get("zero_initial_guess") is True
            valid = valid and record.get("zero_initial_guess_count") == 1
            valid = valid and record.get("ksp_breakdown") is False
            valid = valid and record.get("shared_ksp") is True
            nonzero_checkpoints = [key for key in expected if key != "0"]
            valid = valid and all(
                checkpoints.get(key, {}).get("finite") is True
                and _finite(checkpoints.get(key, {}).get("true_residual_relative"))
                for key in nonzero_checkpoints
            )
            valid = (
                valid
                and checkpoints.get("0", {}).get("reported_relative_residual") == 1.0
            )
            actual_count = record.get("true_residual_matvec_count")
            valid = valid and actual_count == len(nonzero_checkpoints)
            pc_count = record.get("right_pc_apply_count")
            valid = valid and isinstance(pc_count, int) and pc_count >= 0
            if isinstance(pc_count, int):
                phase_apply_count += pc_count
        return bool(valid), phase_apply_count

    screen_contract = bool(
        isinstance(screen, dict)
        and screen.get("schema") == "task040.v1_1.right_fgmres_batch.v1"
        and screen.get("labels") == V1_1_LABELS
        and screen.get("ksp_setup_count") == 1
        and screen.get("ksp_destroy_count") == 1
        and screen.get("ksp_destroyed") is True
        and screen.get("single_right_pc_setup") is True
        and screen.get("zero_initial_guess_all_rhs") is True
    )
    phase1_integrity, phase1_apply_count = phase_integrity(
        phase_one, max_it=16, include_32=False
    )
    phase2_integrity, phase2_apply_count = (
        phase_integrity(phase_two, max_it=32, include_32=True)
        if phase_two
        else (True, 0)
    )
    pc_apply_count_consistent = bool(
        screen_contract
        and screen.get("right_pc_apply_count")
        == phase1_apply_count + phase2_apply_count
        and (not phase_two or phase2_integrity)
    )
    checkpoint_gate: dict[str, dict[str, Any]] = {}
    for phase_name, phase_records in (("phase1", phase_one), ("phase2", phase_two)):
        for iteration in (4, 8, 16, 32):
            rows = {
                label: phase_records.get(label, {})
                .get("checkpoints", {})
                .get(str(iteration))
                for label in V1_1_LABELS
            }
            present = [row for row in rows.values() if isinstance(row, dict)]
            if len(present) != len(V1_1_LABELS):
                continue
            values = [row.get("true_residual_relative") for row in present]
            if not all(_finite(value) for value in values):
                checkpoint_gate[f"{phase_name}:{iteration}"] = {
                    "finite": False,
                    "mandatory_max": None,
                    "preferred_max": None,
                    "pass": False,
                }
                continue
            values = [float(value) for value in values]
            preferred = [
                float(rows[label]["true_residual_relative"])
                for label in V1_1_LABELS[:3]
            ]
            checkpoint_gate[f"{phase_name}:{iteration}"] = {
                "finite": all(row.get("finite") is True for row in present),
                "mandatory_max": max(values),
                "preferred_max": max(preferred),
                "pass": bool(
                    all(row.get("finite") is True for row in present)
                    and max(values) <= 1.0e-2
                    and max(preferred) <= 1.0e-3
                ),
            }
    checkpoint_order = ["phase1:4", "phase1:8", "phase1:16"]
    if conditional_32:
        checkpoint_order.append("phase2:32")
    early_passing_checkpoint = next(
        (
            checkpoint_name
            for checkpoint_name in checkpoint_order[:3]
            if checkpoint_gate.get(checkpoint_name, {}).get("pass") is True
        ),
        None,
    )
    first_passing_checkpoint = next(
        (
            checkpoint_name
            for checkpoint_name in checkpoint_order
            if checkpoint_gate.get(checkpoint_name, {}).get("pass") is True
        ),
        None,
    )
    phase_one_trend_pass = len(phase_one_gate) == 5 and all(phase_one_gate.values())
    checkpoint_pass = bool(
        early_passing_checkpoint is not None
        or (
            early_passing_checkpoint is None
            and conditional_32
            and checkpoint_gate.get("phase2:32", {}).get("pass") is True
        )
    )
    identity_resource_checks = {
        key: base["checks"][key]
        for key in (
            "source_labels",
            "finite",
            "zero_map",
            "repeat",
            "linearity",
            "restriction_prolongation",
            "bare_operator_unchanged",
            "interface_mass_support",
            "factor_inventory",
            "watchdog",
            "resource",
        )
    }
    checks = {
        **identity_resource_checks,
        "contraction_shape": contraction_shape,
        "contraction_finite": contraction_finite,
        "gram_consistency": gram_consistency_pass,
        "norm_storage_consistency": norm_storage_consistency_pass,
        "original_rho_consistency": original_rho_consistency_pass,
        "screen_contract": screen_contract,
        "phase1_integrity": phase1_integrity,
        "phase2_integrity": phase2_integrity,
        "pc_apply_count_consistency": pc_apply_count_consistent,
        "ksp_lifecycle": isinstance(screen, dict)
        and screen.get("ksp_setup_count") == 1
        and screen.get("ksp_destroy_count") == 1
        and screen.get("ksp_destroyed") is True
        and screen.get("single_right_pc_setup") is True
        and screen.get("zero_initial_guess_all_rhs") is True,
        "conditional_32_contract": (
            isinstance(screen, dict) and (bool(phase_two) == conditional_32)
        ),
        "checkpoint_gate": checkpoint_pass,
    }
    core_check_names = (
        "source_labels",
        "finite",
        "zero_map",
        "repeat",
        "linearity",
        "restriction_prolongation",
        "bare_operator_unchanged",
        "interface_mass_support",
        "factor_inventory",
        "watchdog",
        "resource",
        "contraction_shape",
        "contraction_finite",
        "gram_consistency",
        "norm_storage_consistency",
        "original_rho_consistency",
        "screen_contract",
        "phase1_integrity",
        "phase2_integrity",
        "pc_apply_count_consistency",
        "ksp_lifecycle",
        "conditional_32_contract",
    )
    core_pass = all(checks[name] for name in core_check_names)
    if not core_pass:
        classification = "IMPLEMENTATION_OR_RESOURCE_FAILURE"
    elif early_passing_checkpoint is not None:
        classification = "SCALAR_TRANSMISSION_KRYLOV_PASS"
    elif conditional_32:
        classification = (
            "SCALAR_TRANSMISSION_KRYLOV_PASS"
            if checkpoint_gate.get("phase2:32", {}).get("pass") is True
            else "SCALAR_TRANSMISSION_KRYLOV_CAPACITY_FAIL"
        )
    elif not phase_one_trend_pass:
        classification = "SCALAR_TRANSMISSION_DIRECTIONAL_FAIL"
    else:
        classification = "IMPLEMENTATION_OR_RESOURCE_FAILURE"
    return {
        "schema": "task040.v1_1.scalar_krylov.recomputed.v1",
        "source_sha": worker["source_sha"],
        "raw_hashes": base["raw_hashes"],
        "derived": {
            "by_label": derived_by_label,
            "B_vs_Y_normalized_cross_correlation": cross_correlation,
            "B_vs_Y_normalized_cross_correlation_abs": cross_correlation_abs,
            "phase_one_gate": phase_one_gate,
            "phase_one_trend_pass": phase_one_trend_pass,
            "phase1_integrity": phase1_integrity,
            "phase2_integrity": phase2_integrity,
            "pc_apply_count_consistency": pc_apply_count_consistent,
            "phase1_right_pc_apply_count": phase1_apply_count,
            "phase2_right_pc_apply_count": phase2_apply_count,
            "resource_at_phase_boundary_pass": resource_pass,
            "conditional_32_authorized": conditional_32,
            "checkpoint_gate": checkpoint_gate,
            "early_passing_checkpoint": early_passing_checkpoint,
            "first_passing_checkpoint": first_passing_checkpoint,
        },
        "checks": checks,
        "classification": classification,
        "gate_pass": bool(
            classification == "SCALAR_TRANSMISSION_KRYLOV_PASS" and all(checks.values())
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    worker_path = args.run_root / "worker" / "run_summary.json"
    worker = _read_json(worker_path)
    result = (
        recompute_scalar_krylov_gate(args.run_root)
        if worker.get("schema") == V1_1_SCHEMA
        else recompute_level_a_gate(args.run_root)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
