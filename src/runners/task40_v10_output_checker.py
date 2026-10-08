"""Independent integrity and full-residual recheck for Task40 V10 packets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

_TASK40_V10_INTERNAL_RECOVERY_LIMIT = 1.0e-11


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_q_assembly_allocation_admission_ledger(
    run_directory: str | Path, summary: Mapping[str, Any], *, version: str
) -> dict[str, Any]:
    """Independently bind a bounded q-assembly worker's raw gate events."""
    root = Path(run_directory).resolve()
    raw = summary.get("allocation_admission_raw")
    if not isinstance(raw, Mapping) or not isinstance(raw.get("path"), str):
        raise ValueError(f"{version} candidate summary omits its raw allocation event identity")
    relative_path = Path(str(raw["path"]))
    if relative_path.is_absolute():
        raise ValueError(f"{version} allocation event path must be relative to its run directory")
    event_path = (root / relative_path).resolve(strict=True)
    try:
        event_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{version} allocation event path escapes its run directory") from exc

    digest = hashlib.sha256()
    record_count = admission_count = completion_count = 0
    with event_path.open("rb") as stream:
        for line in stream:
            digest.update(line)
            record_count += 1
            if b'"event":"v10_strict_allocation_admission"' in line:
                admission_count += 1
            if b'"event":"v10_strict_allocation_admission_complete"' in line:
                completion_count += 1
    actual = {
        "path": str(event_path.relative_to(root)),
        "size_bytes": int(event_path.stat().st_size),
        "sha256": digest.hexdigest(),
        "record_count": record_count,
        "allocation_admission_event_count": admission_count,
        "allocation_admission_complete_event_count": completion_count,
    }
    for field, value in actual.items():
        if field != "path" and raw.get(field) != value:
            raise ValueError(f"{version} raw allocation event {field} differs from its saved identity")

    invocation_count = int(summary.get("allocation_gate_invocation_count", -1))
    completion_gap = admission_count - completion_count
    status = str(summary.get("status", ""))
    passed = bool(
        invocation_count >= 0
        and admission_count == invocation_count
        and 0 <= completion_gap <= 1
        and (status != "PASS" or completion_gap == 0)
    )
    stored_validation = summary.get("allocation_admission_raw_validation")
    if not isinstance(stored_validation, Mapping) or stored_validation.get("passed") is not True:
        passed = False
    if not passed:
        raise ValueError(
            f"{version} raw admission/complete counts do not match the recorded invocation count "
            "and worker result"
        )
    return {
        "schema": f"task40extra.review_{version}_allocation_admission_ledger_check.v1",
        **actual,
        "allocation_gate_invocation_count": invocation_count,
        "incomplete_admission_count": completion_gap,
        "worker_status": status,
        "passed": True,
    }


def _verify_v16_allocation_admission_ledger(
    run_directory: str | Path, summary: Mapping[str, Any]
) -> dict[str, Any]:
    return _verify_q_assembly_allocation_admission_ledger(
        run_directory, summary, version="v16"
    )


def _verify_v17_row_tile_allocation_admission_ledger(
    run_directory: str | Path, summary: Mapping[str, Any]
) -> dict[str, Any]:
    return _verify_q_assembly_allocation_admission_ledger(
        run_directory, summary, version="v17_row_tile"
    )


def _raw_array_ref(record: Mapping[str, Any], key: str, arrays: Any) -> np.ndarray:
    reference = record.get(key)
    if not isinstance(reference, Mapping) or not isinstance(reference.get("array_key"), str):
        raise ValueError(f"saved residual packet is missing array reference {key!r}")
    value = np.asarray(arrays[reference["array_key"]])
    if list(value.shape) != reference.get("shape"):
        raise ValueError(f"saved residual array {key!r} changed shape")
    return value


def _array_ref(record: Mapping[str, Any], key: str, arrays: Any) -> np.ndarray:
    return np.asarray(_raw_array_ref(record, key, arrays), dtype=np.complex128)


def _registered_v15_profile_inventory(identity: Any) -> dict[str, Any]:
    """Resolve registered V15/V16/V17 identities; never trust packet row counts."""

    from src.io.physical_intermediate_profile import (
        TASK40_V15_P6_PROFILES,
        TASK40_V16_P6_PROFILES,
        TASK40_V17_P6_PROFILES,
        TASK40_V18_P6_PROFILES,
    )
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    if not isinstance(identity, str) or identity not in (
        *TASK40_V15_P6_PROFILES,
        *TASK40_V16_P6_PROFILES,
        *TASK40_V17_P6_PROFILES,
        *TASK40_V18_P6_PROFILES,
    ):
        raise ValueError(f"unknown registered Task40 V15/V16/V17 profile identity: {identity!r}")
    profile = TASK40_P6_PERIODIC_PROFILES.get(identity)
    if profile is None:
        raise ValueError(f"registered Task40 V15/V16 profile has no periodic inventory: {identity}")
    return {
        "identity": identity,
        "global_interior_rows": int(profile.global_interior_rows),
        "global_independent_rows": int(profile.global_independent_rows),
        "global_storage_rows": int(profile.global_storage_rows),
        "mode_count": int(profile.mode_count),
        "q_count": int(profile.q_count),
        "q_port_counts": tuple(int(value) for value in profile.q_port_counts),
        "twist_count": int(profile.replication_count),
        "sector_port_counts": tuple(int(value) for value in profile.sector_port_counts),
        "local_interior_rows": int(profile.local_interior_rows),
    }


def _verify_v17_row_tile_assembly_summary(
    run_directory: str | Path, summary: Mapping[str, Any]
) -> dict[str, Any]:
    """Recompute the structural acceptance gates from the saved worker summary."""
    strategy = "ROW_TILE_BOUNDED_CSR_V17"
    if summary.get("q_assembly_strategy") != strategy:
        raise ValueError("V17 worker summary does not select the registered row-tile strategy")
    profile_identity = summary.get("profile")
    from src.io.physical_intermediate_profile import (
        TASK40_V17_P6_PROFILES,
        TASK40_V18_P6_PROFILES,
    )

    if not isinstance(profile_identity, str) or profile_identity not in (
        *TASK40_V17_P6_PROFILES,
        *TASK40_V18_P6_PROFILES,
    ):
        raise ValueError(
            "V17 row-tile summary is not bound to an exact registered V17 profile or V18 profile"
        )
    profile_inventory = _registered_v15_profile_inventory(profile_identity)
    q_count = int(profile_inventory["q_count"])
    sector_count = len(profile_inventory["sector_port_counts"])
    is_v18 = profile_identity in TASK40_V18_P6_PROFILES
    if q_count != (8 if is_v18 else 4) or sector_count != q_count // 2:
        raise ValueError("row-tile profile does not match its registered q/twist inventory")
    if not isinstance(summary.get("source_sha"), str) or len(summary["source_sha"]) != 40:
        raise ValueError("V17 row-tile worker summary omits its frozen source SHA")
    snapshot = summary.get("reference_audit_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("V17 row-tile summary omits the pre-destroy reference audit snapshot")
    sectors = snapshot.get("sector_audits_before_destroy")
    if not isinstance(sectors, list) or len(sectors) != sector_count:
        raise ValueError("row-tile summary omits one or more physical p6 sector audits")

    block_keys = {"00", "01", "10", "11"}
    covered_q: set[int] = set()
    all_sector_facts = []
    final_payload_total = 0
    maximum_sector_payload = 0
    max_staging = 0
    for index, sector in enumerate(sectors):
        if not isinstance(sector, Mapping):
            raise ValueError(f"V17 sector audit {index} is not a mapping")
        sector_q = [int(q) for q in sector.get("global_q_indices", ())]
        if len(sector_q) != q_count // sector_count or len(set(sector_q)) != len(sector_q):
            raise ValueError(f"row-tile sector audit {index} has an invalid q-count inventory")
        if covered_q.intersection(sector_q):
            raise ValueError(f"row-tile sector audit {index} duplicates a global q branch")
        covered_q.update(sector_q)
        if sector.get("assembly_strategy") != strategy:
            raise ValueError(f"V17 sector audit {index} has a different assembly strategy")
        shapes = sector.get("block_shapes")
        patterns = sector.get("pattern_facts_by_block")
        norms = sector.get("complete_csr_frobenius_norm_by_block")
        if not isinstance(shapes, Mapping) or set(shapes) != block_keys:
            raise ValueError(f"V17 sector audit {index} omits one or more q blocks")
        if not isinstance(patterns, Mapping) or set(patterns) != block_keys:
            raise ValueError(f"V17 sector audit {index} omits one or more tile patterns")
        if not isinstance(norms, Mapping) or set(norms) != block_keys:
            raise ValueError(f"V17 sector audit {index} omits a complete-CSR norm")
        if sector.get("pattern_layout_pass_count") != 1:
            raise ValueError(f"V17 sector audit {index} regenerated contribution layout")
        if sector.get("numeric_contribution_pass_count") != 1:
            raise ValueError(f"V17 sector audit {index} regenerated numeric FE/Hhat contributions")
        if sector.get("cartesian_support_pairs_materialized") != 0:
            raise ValueError(f"V17 sector audit {index} materialized Cartesian support pairs")
        if sector.get("full_shape_bitset_bytes") != 0:
            raise ValueError(f"V17 sector audit {index} materialized a full-shape bitset")
        if sector.get("full_coo_list_count") != 0 or sector.get("global_python_row_set_count") != 0:
            raise ValueError(f"V17 sector audit {index} materialized a full COO or global row set")
        if sector.get("route_query_uses_temporary_sort") is not False:
            raise ValueError(f"V17 sector audit {index} used a SQLite temporary sort")
        if sector.get("support_route_spool_removed_after_pattern") is not True:
            raise ValueError(f"V17 sector audit {index} did not remove its temporary support spool")
        if sector.get("row_tiles_are_materialized_in_two_descriptor_passes") is not True:
            raise ValueError(f"V17 sector audit {index} does not show bounded tile replay")
        if sector.get("descriptor_replay_regenerates_no_FE_or_Hhat_values") is not True:
            raise ValueError(f"V17 sector audit {index} does not preserve one numeric generation pass")
        if sector.get("all_four_complete_csr_owners_retained_through_norm_gate") is not True:
            raise ValueError(f"V17 sector audit {index} lacks the four-block simultaneous-owner statement")
        stage = int(sector.get("staging_peak_bytes_total_all_blocks", -1))
        budget = int(sector.get("staging_budget_bytes_total_all_q_blocks", -1))
        if stage < 0 or budget != 256 * 1024**2 or stage > budget:
            raise ValueError(f"V17 sector audit {index} violates its 256 MiB staging gate")
        max_staging = max(max_staging, stage)
        final_payload = int(sector.get("final_four_block_csr_payload_bytes", -1))
        if final_payload < 0 or final_payload != int(sector.get("final_csr_payload_bytes_total", -2)):
            raise ValueError(f"V17 sector audit {index} has inconsistent four-block CSR payload accounting")
        final_payload_total += final_payload
        maximum_sector_payload = max(maximum_sector_payload, final_payload)
        reserve = int(sector.get("temporary_filesystem_free_space_reserve_bytes", -1))
        observed_free = int(sector.get("temporary_filesystem_free_bytes_minimum_observed", -1))
        if reserve <= 0 or observed_free < reserve:
            raise ValueError(f"V17 sector audit {index} fell below its temporary filesystem reserve")
        for key in block_keys:
            pattern = patterns[key]
            if not isinstance(pattern, Mapping):
                raise ValueError(f"V17 sector audit {index} pattern {key} is malformed")
            if pattern.get("shape") != shapes[key]:
                raise ValueError(f"V17 sector audit {index} pattern {key} shape disagrees")
            if pattern.get("wide_counts_and_prefix_checked_before_cast") is not True:
                raise ValueError(f"V17 sector audit {index} pattern {key} lacks checked PETSc index casts")
            if int(pattern.get("full_shape_bitset_bytes", -1)) != 0:
                raise ValueError(f"V17 pattern {key} records a full-shape bitset")
            if int(pattern.get("full_coo_list_count", -1)) != 0:
                raise ValueError(f"V17 pattern {key} records a full COO list")
            norm = float(norms[key])
            if not np.isfinite(norm) or norm < 0.0:
                raise ValueError(f"V17 sector audit {index} has an invalid CSR norm for {key}")
        diagonal_scale = max(
            float(norms["00"]), float(norms["11"]), np.finfo(float).tiny
        )
        recomputed_off_diagonal = {
            "q0_q1_relative": float(norms["01"]) / diagonal_scale,
            "q1_q0_relative": float(norms["10"]) / diagonal_scale,
        }
        recorded_off_diagonal = sector.get("off_diagonal_relative")
        if not isinstance(recorded_off_diagonal, Mapping):
            raise ValueError(f"V17 sector audit {index} omits its off-diagonal ratios")
        for key, relative in recomputed_off_diagonal.items():
            if not _close_float(float(recorded_off_diagonal.get(key, float("nan"))), relative):
                raise ValueError(
                    f"V17 sector audit {index} off-diagonal {key} differs from saved complete-CSR norms"
                )
            if not np.isfinite(relative) or relative > 1.0e-11:
                raise ValueError(f"V17 sector audit {index} fails the original 1e-11 operator gate")
        all_sector_facts.append(
            {
                "sector_index": index,
                "global_q_indices": sorted(int(q) for q in sector["global_q_indices"]),
                "staging_peak_bytes": stage,
                "final_four_block_csr_payload_bytes": final_payload,
                "off_diagonal_relative_recomputed_from_saved_norms": recomputed_off_diagonal,
                "all_four_blocks_checked": True,
            }
        )
    if covered_q != set(range(q_count)):
        raise ValueError("row-tile summary does not cover every registered global q branch")
    return {
        "schema": (
            "task40extra.review_v18_ny8_row_tile_assembly_checker.v1"
            if is_v18
            else "task40extra.review_v17_row_tile_assembly_checker.v1"
        ),
        "profile": profile_identity,
        "sector_count": len(sectors),
        "covered_q": sorted(covered_q),
        "sector_checks": all_sector_facts,
        "maximum_staging_bytes": max_staging,
        "sum_final_four_block_csr_payload_bytes_across_sequential_sectors": final_payload_total,
        "maximum_single_sector_final_four_block_csr_payload_bytes": maximum_sector_payload,
        "off_diagonal_recomputed_from_saved_complete_csr_norms": True,
        "operator_reapplied_by_checker": False,
        "checker_scope": "recomputed off-diagonal ratios from saved complete-CSR Frobenius norms; did not reapply the numerical operator",
        "passed": True,
    }


def _verify_v18_ny8_operator_qualification(
    summary: Mapping[str, Any], profile_inventory: Mapping[str, Any]
) -> dict[str, Any]:
    """Recompute saved Ny8 block-coverage and residual gates from the worker audit."""
    snapshot = summary.get("reference_audit_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("V18 worker summary omits its reference audit snapshot")
    operator = snapshot.get("complete_operator_qualification")
    if not isinstance(operator, Mapping):
        raise ValueError("V18 reference snapshot omits the independent complete-operator record")
    operator_sha256 = hashlib.sha256(
        json.dumps(
            operator, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
    if summary.get("complete_operator_qualification_sha256") != operator_sha256:
        raise ValueError("V18 complete-operator snapshot differs from its saved identity hash")
    q_count = int(profile_inventory["q_count"])
    expected_ports = tuple(int(value) for value in profile_inventory["q_port_counts"])
    if q_count != 8 or operator.get("schema") != (
        "task40extra.review_v18_complete_ny_reference_operator.v1"
    ):
        raise ValueError("V18 complete-operator record has the wrong profile/schema")
    if (
        operator.get("status") != "PASS"
        or operator.get("passed") is not True
        or int(operator.get("ny", -1)) != q_count
        or int(operator.get("translation_count_K", -1)) != 4
        or int(operator.get("local_y_cells_ell", -1)) != 2
        or tuple(int(value) for value in operator.get("q_port_counts", ()))
        != expected_ports
    ):
        raise ValueError("V18 complete-operator identity differs from the registered Ny8 inventory")

    block_keys = {f"{p}{q}" for p in range(q_count) for q in range(q_count)}
    offdiagonal_keys = {
        f"{p}{q}" for p in range(q_count) for q in range(q_count) if p != q
    }
    shapes = operator.get("complete_q_block_shapes")
    if (
        operator.get("full_q_block_coverage_count") != q_count**2
        or operator.get("expected_full_q_block_coverage_count") != q_count**2
        or operator.get("all_ordered_q_blocks_covered") is not True
        or not isinstance(shapes, Mapping)
        or set(shapes) != block_keys
        or int(operator.get("native_independent_rows", -1))
        != int(profile_inventory["global_independent_rows"])
    ):
        raise ValueError("V18 independent audit does not cover all 64 ordered q blocks")
    width = int(profile_inventory["global_independent_rows"]) // q_count
    for p in range(q_count):
        for q in range(q_count):
            expected_shape = [
                width + expected_ports[p],
                width + expected_ports[q],
            ]
            if shapes[f"{p}{q}"] != expected_shape:
                raise ValueError(f"V18 q block {p}{q} shape differs from its registered inventory")

    mapping_limit = float(operator.get("mapping_limit", np.nan))
    mapping_defect = float(operator.get("q_dft_unitarity_frobenius_defect", np.nan))
    operator_limit = float(operator.get("operator_limit", np.nan))
    offdiagonal = operator.get("offdiagonal_frobenius_by_block")
    offdiagonal_relative = operator.get("offdiagonal_relative_by_block")
    diagonal_norms = operator.get("complete_augmented_diagonal_frobenius_by_q")
    diagonal_scale = float(operator.get("offdiagonal_diagonal_frobenius_scale", np.nan))
    expected_q_keys = {str(q) for q in range(q_count)}
    if (
        not isinstance(offdiagonal, Mapping)
        or set(offdiagonal) != offdiagonal_keys
        or not isinstance(offdiagonal_relative, Mapping)
        or set(offdiagonal_relative) != offdiagonal_keys
        or not isinstance(diagonal_norms, Mapping)
        or set(diagonal_norms) != expected_q_keys
        or not np.isfinite(mapping_limit)
        or mapping_limit != 1.0e-12
        or not np.isfinite(mapping_defect)
        or mapping_defect > mapping_limit
        or not np.isfinite(operator_limit)
        or operator_limit != 1.0e-11
        or not np.isfinite(diagonal_scale)
        or diagonal_scale <= 0.0
    ):
        raise ValueError("V18 complete-operator record omits its mapping/offdiagonal gates")
    checked_diagonal_norms = {
        key: float(diagonal_norms[key]) for key in sorted(expected_q_keys, key=int)
    }
    if not all(np.isfinite(value) and value >= 0.0 for value in checked_diagonal_norms.values()):
        raise ValueError("V18 saved complete diagonal block norms are invalid")
    recomputed_diagonal_scale = max(
        max(checked_diagonal_norms.values()), np.finfo(float).tiny
    )
    if not _close_float(diagonal_scale, recomputed_diagonal_scale):
        raise ValueError("V18 offdiagonal diagonal scale differs from the eight saved q norms")
    recomputed_offdiagonal = {}
    for key in sorted(offdiagonal_keys):
        norm = float(offdiagonal[key])
        relative = norm / diagonal_scale
        recorded = float(offdiagonal_relative[key])
        if (
            not np.isfinite(norm)
            or norm < 0.0
            or not np.isfinite(relative)
            or relative > operator_limit
            or not _close_float(recorded, relative)
        ):
            raise ValueError(f"V18 offdiagonal block {key} fails the saved 1e-11 gate")
        recomputed_offdiagonal[key] = relative
    maximum_offdiagonal = max(recomputed_offdiagonal.values(), default=0.0)
    if not _close_float(
        float(operator.get("maximum_complete_offdiagonal_relative", np.nan)),
        maximum_offdiagonal,
    ):
        raise ValueError("V18 maximum offdiagonal ratio differs from its 56 saved blocks")

    schur = operator.get("independent_schur_relative_by_q")
    schur_norms = operator.get("independent_schur_norms_by_q")
    if (
        not isinstance(schur, Mapping)
        or set(schur) != expected_q_keys
        or not isinstance(schur_norms, Mapping)
        or set(schur_norms) != expected_q_keys
    ):
        raise ValueError("V18 independent global Schur audit omits one or more q branches")
    recomputed_schur = {}
    for key in sorted(expected_q_keys, key=int):
        norms = schur_norms[key]
        if not isinstance(norms, Mapping):
            raise ValueError(f"V18 q={key} Schur norms are malformed")
        independent = float(norms.get("independent_schur_frobenius", np.nan))
        candidate = float(norms.get("candidate_csr_frobenius", np.nan))
        difference = float(norms.get("complete_difference_frobenius", np.nan))
        relative = difference / max(independent, candidate, np.finfo(float).tiny)
        if (
            not all(np.isfinite(value) and value >= 0.0 for value in (independent, candidate, difference))
            or not np.isfinite(relative)
            or relative > operator_limit
            or not _close_float(float(schur[key]), relative)
        ):
            raise ValueError(f"V18 q={key} candidate differs from its independent Schur oracle")
        recomputed_schur[key] = relative
    maximum_schur = max(recomputed_schur.values(), default=float("inf"))
    if (
        not np.isfinite(maximum_schur)
        or maximum_schur > operator_limit
        or not _close_float(
            float(operator.get("maximum_independent_schur_relative", np.nan)),
            maximum_schur,
        )
    ):
        raise ValueError("V18 maximum independent Schur ratio differs from its q records")

    q4_norm = float(operator.get("q4_nonzero_fe_rhs_norm", np.nan))
    phase_distance = float(operator.get("global_y_phase_distance_from_one", np.nan))
    phase = operator.get("global_y_phase")
    nonhermitian = float(
        operator.get("complex_nonhermitian_reference_witness_relative", np.nan)
    )
    if (
        expected_ports[4] != 0
        or operator.get("empty_port_q_indices") != [4]
        or operator.get("q4_zero_port_nonzero_fe_gate_passed") is not True
        or operator.get("q4_nonzero_fe_rhs_witness_passed") is not True
        or not np.isfinite(q4_norm)
        or q4_norm <= 0.0
        or operator.get("mode_identities_covered_once") is not True
        or operator.get("complex_material_volume_witness_passed") is not True
        or int(operator.get("complex_material_volume_imaginary_nnz", 0)) <= 0
        or operator.get("complex_nonhermitian_reference_witness_passed") is not True
        or not np.isfinite(nonhermitian)
        or nonhermitian <= 1.0e-12
        or not np.isfinite(phase_distance)
        or phase_distance <= mapping_limit
        or not isinstance(phase, Sequence)
        or isinstance(phase, (str, bytes))
        or len(phase) != 2
        or not np.isfinite(np.asarray(phase, dtype=np.float64)).all()
        or not _close_float(
            phase_distance,
            abs(complex(float(phase[0]), float(phase[1])) - 1.0),
        )
        or int(operator.get("original_H_mode_count", -1)) != int(profile_inventory["mode_count"])
        or not np.isfinite(float(operator.get("original_H_minimum", np.nan)))
        or float(operator.get("original_H_minimum", np.nan)) <= 0.0
        or not np.isfinite(float(operator.get("original_H_maximum", np.nan)))
        or float(operator.get("original_H_maximum", np.nan)) < float(operator.get("original_H_minimum", np.nan))
        or sum(expected_ports) != int(profile_inventory["mode_count"])
    ):
        raise ValueError("V18 zero-port, phase, complex-material, or physical witness gate failed")

    return {
        "schema": "task40extra.review_v18_ny8_operator_checker.v1",
        "profile": profile_inventory["identity"],
        "complete_operator_qualification_sha256": operator_sha256,
        "complete_q_block_count": q_count**2,
        "offdiagonal_block_count": len(offdiagonal_keys),
        "independent_schur_q_count": q_count,
        "maximum_offdiagonal_relative_recomputed": maximum_offdiagonal,
        "maximum_independent_schur_relative_recomputed": maximum_schur,
        "q4_zero_port_nonzero_fe_witness_passed": True,
        "nonhermitian_complex_material_witness_passed": True,
        "global_phase_witness_passed": True,
        "operator_reapplied_by_checker": False,
        "passed": True,
    }


def _close_float(actual: float, expected: float, *, rtol: float = 2.0e-12) -> bool:
    actual = float(actual)
    expected = float(expected)
    return bool(
        np.isfinite(actual)
        and np.isfinite(expected)
        and (actual == expected or np.isclose(actual, expected, rtol=rtol, atol=0.0))
    )


def _vector_defect_relative(
    actual: np.ndarray, expected: np.ndarray, action_scale: float
) -> float:
    from src.solvers.augmented_reference_correction import stable_euclidean_norm

    left = np.asarray(actual)
    right = np.asarray(expected)
    if left.shape != right.shape or left.dtype != np.dtype(np.complex128):
        return float("inf")
    if right.dtype != np.dtype(np.complex128):
        return float("inf")
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        return float("inf")
    scale = float(action_scale)
    defect = stable_euclidean_norm(left - right)
    if not np.isfinite(scale) or scale < 0.0:
        return float("inf")
    if scale == 0.0:
        return 0.0 if defect == 0.0 else float("inf")
    return defect / scale


def verify_v10_dtn_port_mode_table(
    csv_path: str | Path, *, expected_channel_count: int = 532
) -> dict[str, Any]:
    """Verify complete top and bottom modal rows in the emitted DtN port table.

    ``diffraction_channel_count`` from field postprocessing counts the 266
    spatial/polarization orders once.  The official port table carries one row
    for each of those orders on each side, so its complete channel count is
    532 and both sides must contain the same 266 mode identities.
    """

    path = Path(csv_path).resolve()
    expected = int(expected_channel_count)
    expected_per_side = expected // 2
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"side", "m", "n", "polarization"}
        columns = set(reader.fieldnames or ())
        missing_columns = sorted(required - columns)
        rows = list(reader)

    side_counts = {"top": 0, "bottom": 0}
    mode_sets: dict[str, set[tuple[int, int, str]]] = {"top": set(), "bottom": set()}
    duplicate_modes = {"top": 0, "bottom": 0}
    malformed_rows = 0
    for row in rows:
        side = str(row.get("side", "")).strip().lower()
        if side not in mode_sets:
            malformed_rows += 1
            continue
        side_counts[side] += 1
        try:
            key = (
                int(row["m"]),
                int(row["n"]),
                str(row["polarization"]).strip().lower(),
            )
            if not key[2]:
                raise ValueError("empty polarization")
        except (KeyError, TypeError, ValueError):
            malformed_rows += 1
            continue
        if key in mode_sets[side]:
            duplicate_modes[side] += 1
        mode_sets[side].add(key)

    paired_modes = len(mode_sets["top"] & mode_sets["bottom"])
    table_passed = bool(
        expected > 0
        and expected % 2 == 0
        and not missing_columns
        and malformed_rows == 0
        and len(rows) == expected
        and side_counts == {"top": expected_per_side, "bottom": expected_per_side}
        and duplicate_modes == {"top": 0, "bottom": 0}
        and len(mode_sets["top"]) == expected_per_side
        and len(mode_sets["bottom"]) == expected_per_side
        and mode_sets["top"] == mode_sets["bottom"]
    )
    npz_path = path.parent / "dtn_port_modal_amplitudes_3d.npz"
    npz_report = None
    if npz_path.is_file():
        try:
            npz_report = _verify_dtn_port_modal_amplitudes_npz(npz_path, rows)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            npz_report = {"npz_path": str(npz_path), "passed": False, "error": str(exc)}
    elif "dtn_phase_gauge" in columns:
        npz_report = {
            "npz_path": str(npz_path),
            "passed": False,
            "error": "new gauge-aware modal CSV requires its NPZ payload",
        }
    passed = bool(table_passed and (npz_report is None or npz_report.get("passed") is True))
    return {
        "schema": "task40extra.review_v10_dtn_port_mode_table_check.v1",
        "csv_path": str(path),
        "expected_channel_count": expected,
        "actual_channel_count": len(rows),
        "expected_modes_per_side": expected_per_side,
        "channel_count_by_side": side_counts,
        "unique_mode_count_by_side": {
            side: len(mode_sets[side]) for side in ("top", "bottom")
        },
        "paired_top_bottom_mode_count": paired_modes,
        "duplicate_mode_count_by_side": duplicate_modes,
        "malformed_row_count": malformed_rows,
        "missing_columns": missing_columns,
        "modal_amplitudes_npz": npz_report,
        "passed": passed,
    }


def _verify_dtn_port_modal_amplitudes_npz(
    npz_path: Path, csv_rows: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Check required solver/plane arrays and explicitly masked optional conversions."""
    required_arrays = {
        "dtn_phase_gauge",
        "solver_amplitude_coordinate",
        "physical_boundary_amplitude_coordinate",
        "legacy_amplitude_field_coordinate",
        "auxiliary_index",
        "side",
        "m",
        "n",
        "polarization",
        "solver_auxiliary_amplitude_total_projection",
        "solver_incident_projection",
        "solver_outgoing_amplitude",
        "physical_boundary_total_amplitude",
        "physical_boundary_incident_amplitude",
        "physical_boundary_outgoing_amplitude",
        "physical_boundary_total_representable",
        "physical_boundary_incident_representable",
        "physical_boundary_outgoing_representable",
        "boundary_phase",
        "boundary_phase_representable",
        "legacy_global_total_projection",
        "legacy_global_incident_projection",
        "legacy_global_outgoing_amplitude",
        "legacy_global_total_representable",
        "legacy_global_incident_representable",
        "legacy_global_outgoing_representable",
        "global_output_representable",
        "global_output_failure_reason",
    }
    with np.load(npz_path, allow_pickle=False) as arrays:
        missing = sorted(required_arrays - set(arrays.files))
        if missing:
            raise ValueError(f"modal amplitude NPZ is missing fields: {missing}")
        count = len(csv_rows)
        vector_names = required_arrays - {
            "dtn_phase_gauge",
            "solver_amplitude_coordinate",
            "physical_boundary_amplitude_coordinate",
            "legacy_amplitude_field_coordinate",
        }
        wrong_shapes = {
            name: list(np.asarray(arrays[name]).shape)
            for name in vector_names
            if np.asarray(arrays[name]).shape != (count,)
        }
        if wrong_shapes:
            raise ValueError(f"modal amplitude NPZ arrays have wrong shapes: {wrong_shapes}")
        gauge = str(np.asarray(arrays["dtn_phase_gauge"]).item())
        if gauge not in {"global_z", "boundary_plane"}:
            raise ValueError("modal amplitude NPZ has an unknown solver gauge")
        if str(np.asarray(arrays["solver_amplitude_coordinate"]).item()) != gauge:
            raise ValueError("modal amplitude NPZ solver coordinate does not match its gauge")
        if str(np.asarray(arrays["physical_boundary_amplitude_coordinate"]).item()) != "boundary_plane":
            raise ValueError("modal amplitude NPZ physical boundary coordinate is not boundary_plane")
        if str(np.asarray(arrays["legacy_amplitude_field_coordinate"]).item()) != "global_z":
            raise ValueError("modal amplitude NPZ legacy coordinate is not global_z")

        for index, row in enumerate(csv_rows):
            if (
                int(arrays["auxiliary_index"][index]) != index
                or str(arrays["side"][index]) != str(row["side"])
                or int(arrays["m"][index]) != int(row["m"])
                or int(arrays["n"][index]) != int(row["n"])
                or str(arrays["polarization"][index]) != str(row["polarization"])
                or str(row.get("dtn_phase_gauge", gauge)) != gauge
            ):
                raise ValueError(f"modal amplitude NPZ identity differs from CSV row {index}")

        csv_value_map = (
            ("solver_auxiliary_amplitude_total_projection", "solver_auxiliary_amplitude_total_projection", None),
            ("solver_incident_projection", "solver_incident_projection", None),
            ("solver_outgoing_amplitude", "solver_outgoing_amplitude", None),
            ("physical_boundary_total_amplitude", "physical_boundary_total_amplitude", "physical_boundary_total_representable"),
            ("physical_boundary_incident_amplitude", "physical_boundary_incident_amplitude", "physical_boundary_incident_representable"),
            ("physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
            ("outgoing_amplitude_at_boundary", "physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
            ("auxiliary_amplitude_total_projection", "legacy_global_total_projection", "legacy_global_total_representable"),
            ("incident_projection", "legacy_global_incident_projection", "legacy_global_incident_representable"),
            ("outgoing_amplitude", "legacy_global_outgoing_amplitude", "legacy_global_outgoing_representable"),
            ("boundary_phase", "boundary_phase", "boundary_phase_representable"),
        )
        for csv_name, npz_name, mask_name in csv_value_map:
            values = np.asarray(arrays[npz_name])
            mask = None if mask_name is None else np.asarray(arrays[mask_name], dtype=bool)
            for index, row in enumerate(csv_rows):
                raw = str(row.get(csv_name, "")).strip()
                if not raw:
                    if mask is None or mask[index]:
                        raise ValueError(f"CSV field {csv_name} is missing at row {index}")
                    continue
                parsed = complex(raw)
                if mask is not None and not mask[index]:
                    raise ValueError(f"CSV field {csv_name} is present despite an unrepresentable NPZ mask")
                if parsed != complex(values[index]):
                    raise ValueError(f"CSV field {csv_name} differs from NPZ at row {index}")

        solver_names = (
            "solver_auxiliary_amplitude_total_projection",
            "solver_incident_projection",
            "solver_outgoing_amplitude",
        )
        nonfinite_solver = [name for name in solver_names if not np.isfinite(arrays[name]).all()]
        if nonfinite_solver:
            raise ValueError(f"required solver-coordinate amplitudes are nonfinite: {nonfinite_solver}")
        solver_total = np.asarray(arrays["solver_auxiliary_amplitude_total_projection"])
        solver_incident = np.asarray(arrays["solver_incident_projection"])
        solver_outgoing = np.asarray(arrays["solver_outgoing_amplitude"])
        sides = np.asarray(arrays["side"]).astype(str)
        expected_outgoing = solver_total.copy()
        top_rows = sides == "top"
        bottom_rows = sides == "bottom"
        if not np.all(top_rows | bottom_rows):
            raise ValueError("solver-coordinate amplitude NPZ contains an unknown port side")
        expected_outgoing[top_rows] -= solver_incident[top_rows]
        if not np.array_equal(solver_outgoing, expected_outgoing):
            raise ValueError("top outgoing is not total-minus-incident once or bottom outgoing is not total")

        boundary_fields = (
            ("physical_boundary_total_amplitude", "physical_boundary_total_representable"),
            ("physical_boundary_incident_amplitude", "physical_boundary_incident_representable"),
            ("physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
        )
        boundary_masks = []
        for name, mask_name in boundary_fields:
            values = np.asarray(arrays[name])
            mask = np.asarray(arrays[mask_name], dtype=bool)
            boundary_masks.append(mask)
            if not np.isfinite(values[mask]).all():
                raise ValueError(f"representable physical-plane array {name} is nonfinite")
            invalid = values[~mask]
            if invalid.size and not (np.isnan(invalid.real).all() and np.isnan(invalid.imag).all()):
                raise ValueError(f"unrepresentable physical-plane array {name} lacks an explicit NaN placeholder")
        if gauge == "boundary_plane":
            if not all(mask.all() for mask in boundary_masks):
                raise ValueError("boundary-plane solver amplitudes must retain every finite physical-plane value")
            for solver_name, boundary_name in zip(solver_names, (name for name, _ in boundary_fields), strict=True):
                if not np.array_equal(arrays[solver_name], arrays[boundary_name]):
                    raise ValueError("boundary-plane physical fields differ from their solver-coordinate values")

        optional_fields = (
            ("legacy_global_total_projection", "legacy_global_total_representable"),
            ("legacy_global_incident_projection", "legacy_global_incident_representable"),
            ("legacy_global_outgoing_amplitude", "legacy_global_outgoing_representable"),
        )
        optional_masks = []
        for name, mask_name in optional_fields:
            values = np.asarray(arrays[name])
            mask = np.asarray(arrays[mask_name], dtype=bool)
            optional_masks.append(mask)
            if not np.isfinite(values[mask]).all():
                raise ValueError(f"representable optional global array {name} is nonfinite")
            invalid = values[~mask]
            if invalid.size and not (np.isnan(invalid.real).all() and np.isnan(invalid.imag).all()):
                raise ValueError(f"unrepresentable optional global array {name} lacks an explicit NaN placeholder")

        phase = np.asarray(arrays["boundary_phase"])
        phase_mask = np.asarray(arrays["boundary_phase_representable"], dtype=bool)
        if not np.isfinite(phase[phase_mask]).all():
            raise ValueError("representable boundary phases contain nonfinite values")
        invalid_phase = phase[~phase_mask]
        if invalid_phase.size and not (np.isnan(invalid_phase.real).all() and np.isnan(invalid_phase.imag).all()):
            raise ValueError("unrepresentable boundary phase lacks an explicit NaN placeholder")

        global_mask = np.asarray(arrays["global_output_representable"], dtype=bool)
        reason = np.asarray(arrays["global_output_failure_reason"]).astype(str)
        expected_global_mask = np.logical_and.reduce(optional_masks)
        if gauge == "boundary_plane":
            expected_global_mask &= phase_mask
        if not np.array_equal(global_mask, expected_global_mask):
            raise ValueError("global-output status disagrees with its per-field representability masks")
        if np.any(~global_mask & (reason == "")):
            raise ValueError("an unrepresentable optional global output has no recorded reason")

    json_path = npz_path.parent / "dtn_auxiliary_amplitudes_3d.json"
    if not json_path.is_file():
        raise ValueError("new gauge-aware modal CSV requires dtn_auxiliary_amplitudes_3d.json")
    json_rows = json.loads(json_path.read_text(encoding="utf-8"))
    if len(json_rows) != len(csv_rows):
        raise ValueError("modal JSON and CSV row counts differ")
    json_value_map = (
        ("solver_auxiliary_amplitude_total_projection", "solver_auxiliary_amplitude_total_projection", None),
        ("solver_incident_projection", "solver_incident_projection", None),
        ("solver_outgoing_amplitude", "solver_outgoing_amplitude", None),
        ("physical_boundary_total_amplitude", "physical_boundary_total_amplitude", "physical_boundary_total_representable"),
        ("physical_boundary_incident_amplitude", "physical_boundary_incident_amplitude", "physical_boundary_incident_representable"),
        ("physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
        ("outgoing_amplitude_at_boundary", "physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
        ("auxiliary_amplitude_total_projection", "legacy_global_total_projection", "legacy_global_total_representable"),
        ("incident_projection", "legacy_global_incident_projection", "legacy_global_incident_representable"),
        ("outgoing_amplitude", "legacy_global_outgoing_amplitude", "legacy_global_outgoing_representable"),
        ("boundary_phase", "boundary_phase", "boundary_phase_representable"),
    )
    with np.load(npz_path, allow_pickle=False) as arrays:
        for index, (json_row, csv_row) in enumerate(zip(json_rows, csv_rows, strict=True)):
            if (
                int(json_row["auxiliary_index"]) != int(csv_row["auxiliary_index"])
                or str(json_row["dtn_phase_gauge"]) != str(csv_row["dtn_phase_gauge"])
                or str(json_row["side"]) != str(csv_row["side"])
                or int(json_row["m"]) != int(csv_row["m"])
                or int(json_row["n"]) != int(csv_row["n"])
                or str(json_row["polarization"]) != str(csv_row["polarization"])
            ):
                raise ValueError(f"modal JSON identity differs from CSV row {index}")
            for json_name, npz_name, mask_name in json_value_map:
                value = json_row.get(json_name)
                mask = True if mask_name is None else bool(arrays[mask_name][index])
                if value is None:
                    if mask:
                        raise ValueError(f"modal JSON field {json_name} is null despite a true NPZ mask")
                    continue
                if not mask or len(value) != 2:
                    raise ValueError(f"modal JSON field {json_name} conflicts with its NPZ mask")
                parsed = complex(float(value[0]), float(value[1]))
                if parsed != complex(arrays[npz_name][index]):
                    raise ValueError(f"modal JSON field {json_name} differs from NPZ at row {index}")

    return {
        "npz_path": str(npz_path.resolve()),
        "json_path": str(json_path.resolve()),
        "mode_count": count,
        "dtn_phase_gauge": gauge,
        "required_solver_and_plane_fields_finite": True,
        "optional_global_values_masked": True,
        "json_csv_npz_values_agree": True,
        "passed": True,
    }


def verify_v10_regular_internal_witness(packet_json: str | Path) -> dict[str, Any]:
    """Recompute frozen Task40 internal recovery from saved raw arrays."""

    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    profile_identity = record.get("profile_identity")
    v15_inventory = None
    if profile_identity is None:
        # Historical V10 packets predate profile binding and remain frozen at B0.
        registered_interior_rows = 36_000
    elif profile_identity == "task40extra_v10_p6_y_orbit_reference_v1":
        registered_interior_rows = 36_000
    else:
        v15_inventory = _registered_v15_profile_inventory(profile_identity)
        registered_interior_rows = v15_inventory["global_interior_rows"]
    array_manifest = record.get("arrays")
    if not isinstance(array_manifest, Mapping):
        raise ValueError("V10 regular witness packet has no NPZ array manifest")
    npz_path = Path(str(array_manifest["path"])).resolve()
    actual_npz_sha = _file_sha256(npz_path)
    if actual_npz_sha != array_manifest.get("sha256"):
        raise ValueError("V10 regular witness NPZ identity check failed")

    with np.load(npz_path, allow_pickle=False) as arrays:
        effective_rhs = _array_ref(record, "full_internal_effective_rhs", arrays)
        saved_action = _array_ref(record, "full_internal_saved_field_action", arrays)
        saved_residual = _array_ref(record, "full_internal_recovery_residuals", arrays)
        original_rows = _raw_array_ref(record, "full_internal_original_rows", arrays)
        twists = _raw_array_ref(record, "full_internal_twist_indices", arrays)

    expected_rows = int(record.get("full_internal_recovery_rows", 0))
    if expected_rows != registered_interior_rows:
        raise ValueError(
            "regular witness row count differs from its registered profile inventory"
        )
    row_shape = (expected_rows,)
    if any(
        vector.shape != row_shape
        for vector in (effective_rhs, saved_action, saved_residual, original_rows, twists)
    ):
        raise ValueError("regular internal raw arrays do not share their registered row layout")
    if not np.issubdtype(original_rows.dtype, np.integer) or not np.issubdtype(
        twists.dtype, np.integer
    ):
        raise ValueError("V10 regular internal row identity arrays must be integers")
    if not np.isfinite(effective_rhs).all() or not np.isfinite(saved_action).all():
        raise ValueError("V10 regular internal raw action arrays contain non-finite values")
    sector_count = (
        len(v15_inventory["sector_port_counts"]) if v15_inventory is not None else 2
    )
    if not np.array_equal(
        np.unique(twists), np.arange(sector_count, dtype=twists.dtype)
    ):
        raise ValueError("V10 regular internal raw arrays do not identify every twist")
    ordered = np.lexsort((original_rows, twists))
    row_pairs = np.rec.fromarrays((twists, original_rows))
    if not np.array_equal(ordered, np.arange(expected_rows)) or np.unique(row_pairs).size != expected_rows:
        raise ValueError("V10 regular internal twist/row order is not unique and canonical")

    if v15_inventory is not None:
        sector_count = len(v15_inventory["sector_port_counts"])
        q_per_twist = v15_inventory["q_count"] // sector_count
        if (
            sector_count <= 0
            or v15_inventory["global_interior_rows"] % sector_count
            or v15_inventory["q_count"] % sector_count
        ):
            raise ValueError("registered profile has incompatible twist/q dimensions")
        expected_per_twist = v15_inventory["global_interior_rows"] // sector_count
        twist_counts = {
            twist: int(np.count_nonzero(twists == twist))
            for twist in range(sector_count)
        }
        if twist_counts != {twist: expected_per_twist for twist in range(sector_count)}:
            raise ValueError("regular witness does not cover every complete interior sector")
        if int(record.get("expected_port_mode_count", -1)) != v15_inventory["mode_count"]:
            raise ValueError("V15 regular witness mode count differs from registered profile")
        sectors = record.get("local_recovery_facts")
        if not isinstance(sectors, Sequence) or isinstance(sectors, (str, bytes)) or len(sectors) != sector_count:
            raise ValueError("regular witness is missing one or more sector recovery facts")
        sector_by_twist = {}
        for sector in sectors:
            if not isinstance(sector, Mapping):
                raise ValueError("V15 sector recovery facts must be mappings")
            twist = int(sector.get("twist_index", -1))
            if twist in sector_by_twist or twist not in range(sector_count):
                raise ValueError("V15 regular witness sector identities are incomplete or duplicated")
            sector_by_twist[twist] = sector
        expected_q_by_twist = {
            twist: tuple(
                twist + branch * sector_count for branch in range(q_per_twist)
            )
            for twist in range(sector_count)
        }
        for twist, q_indices in expected_q_by_twist.items():
            sector = sector_by_twist.get(twist)
            expected_sector_modes = sum(
                v15_inventory["q_port_counts"][q] for q in q_indices
            )
            if (
                sector is None
                or tuple(int(value) for value in sector.get("global_q_indices", ()))
                != q_indices
                or int(sector.get("internal_row_count", -1)) != expected_per_twist
                or int(sector.get("port_mode_count", -1)) != expected_sector_modes
            ):
                raise ValueError("V15 regular witness sector rows or modes differ from profile")
        q_rows = record.get("q_true_residuals")
        if (
            not isinstance(q_rows, Sequence)
            or isinstance(q_rows, (str, bytes))
            or len(q_rows) != v15_inventory["q_count"]
            or {int(row.get("q", -1)) for row in q_rows if isinstance(row, Mapping)}
            != set(range(v15_inventory["q_count"]))
            or any(not isinstance(row, Mapping) for row in q_rows)
        ):
            raise ValueError("V15 regular witness does not cover every registered q branch")
        for row in q_rows:
            rhs_norm = float(row.get("rhs_norm", np.nan))
            residual_norm = float(row.get("true_residual_norm", np.nan))
            relative = float(row.get("true_residual_relative", np.nan))
            recomputed_relative = (
                residual_norm / rhs_norm if rhs_norm > 0.0 else (0.0 if residual_norm == 0.0 else float("inf"))
            )
            if not _close_float(relative, recomputed_relative):
                raise ValueError("V15 regular witness q residual rows are inconsistent")

    recomputed = effective_rhs - saved_action
    scale = float(record["full_internal_recovery_operation_scale"])
    limits = record.get("limits")
    if not isinstance(limits, Mapping) or "full_internal_recovery" not in limits:
        raise ValueError("V10 regular witness is missing limits.full_internal_recovery")
    recorded_limit = float(limits["full_internal_recovery"])
    if "full_internal_recovery_limit" in record:
        duplicate_limit = float(record["full_internal_recovery_limit"])
        if not np.isfinite(duplicate_limit) or duplicate_limit != recorded_limit:
            raise ValueError("V10 regular internal recovery limit fields conflict")
    stored_relative = float(record["full_internal_recovery_relative"])
    if not np.isfinite(scale) or scale < 0.0:
        raise ValueError("V10 regular internal operation scale is invalid")
    if (
        not np.isfinite(recorded_limit)
        or recorded_limit != _TASK40_V10_INTERNAL_RECOVERY_LIMIT
    ):
        raise ValueError("V10 regular internal witness limit differs from fixed 1e-11 contract")
    limit = _TASK40_V10_INTERNAL_RECOVERY_LIMIT
    denominator = max(scale, np.finfo(float).tiny)
    relative = float(np.linalg.norm(recomputed) / denominator)
    algebra_defect = float(
        np.linalg.norm(recomputed - saved_residual)
        / max(
            float(np.linalg.norm(effective_rhs)) + float(np.linalg.norm(saved_action)),
            np.finfo(float).tiny,
        )
    )
    passed = bool(
        np.isfinite(relative)
        and relative <= limit
        and abs(relative - stored_relative) <= 1.0e-12
        and algebra_defect <= 1.0e-12
    )
    if not passed:
        raise ValueError("V10 regular internal residual failed raw-array recomputation")
    return {
        "schema": (
            "task40extra.review_v15_regular_internal_witness_recheck.v1"
            if v15_inventory is not None
            else "task40extra.review_v10_regular_internal_witness_recheck.v1"
        ),
        "packet_json": str(path),
        "packet_npz": str(npz_path),
        "packet_npz_sha256": actual_npz_sha,
        "profile_identity": profile_identity,
        "internal_row_count": expected_rows,
        "expected_port_mode_count": (
            v15_inventory["mode_count"] if v15_inventory is not None else None
        ),
        "twist_row_order": "twist_index ascending; original storage row ascending within twist",
        "recomputed_relative_residual": relative,
        "stored_relative_residual": stored_relative,
        "residual_algebra_defect_relative": algebra_defect,
        "operation_scale": scale,
        "limit": limit,
        "passed": True,
        "operator_reapplied_by_checker": False,
    }


def verify_v15_pc_state_packet(packet_json: str | Path) -> dict[str, Any]:
    """Recompute V15 state identities, native budget terms, and admission."""

    from src.solvers.augmented_reference_correction import (
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        V15_DECOMPOSITION_CLOSURE_LIMIT,
        V15_REFERENCE_PC_REJECTED,
        augmented_state_sha256,
        recompute_v15_candidate_facts,
        select_v15_reference_pc_candidate,
        stable_euclidean_norm,
    )

    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") != "task40extra.review_v15_p6_pc_state_evidence.v1":
        raise ValueError("not a registered V15 PC state evidence packet")
    if record.get("reference_pc_strategy") != NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
        raise ValueError("V15 PC packet strategy identity is invalid")
    profile_identity = record.get("profile_identity", record.get("profile"))
    inventory = _registered_v15_profile_inventory(profile_identity)
    array_manifest = record.get("arrays")
    if not isinstance(array_manifest, Mapping):
        raise ValueError("V15 PC packet has no NPZ array manifest")
    npz_path = Path(str(array_manifest["path"])).resolve()
    actual_npz_sha = _file_sha256(npz_path)
    if actual_npz_sha != array_manifest.get("sha256"):
        raise ValueError("V15 PC packet NPZ identity check failed")

    def complex_array(arrays: Any, key: str, shape: tuple[int, ...]) -> np.ndarray:
        value = _raw_array_ref(record, key, arrays)
        if value.dtype != np.dtype(np.complex128) or value.shape != shape:
            raise ValueError(f"V15 PC packet array {key!r} has an invalid dtype or profile shape")
        if not np.isfinite(value).all():
            raise ValueError(f"V15 PC packet array {key!r} contains nonfinite values")
        return value

    def norm_matches(raw_facts: Mapping[str, Any], key: str, value: np.ndarray) -> bool:
        return _close_float(
            float(raw_facts.get(key, np.nan)), stable_euclidean_norm(value)
        )

    candidates_meta = record.get("candidate_facts")
    if not isinstance(candidates_meta, Sequence) or isinstance(candidates_meta, (str, bytes)):
        raise ValueError("V15 PC packet candidate_facts must be a sequence")
    candidates = []
    with np.load(npz_path, allow_pickle=False) as arrays:
        fe_rhs = complex_array(arrays, "fe_rhs", (inventory["global_independent_rows"],))
        port_rhs = complex_array(arrays, "port_rhs", (inventory["mode_count"],))
        for index, facts in enumerate(candidates_meta):
            if not isinstance(facts, Mapping):
                raise ValueError("V15 PC candidate facts must be mappings")
            fe_state = complex_array(
                arrays,
                f"candidate_{index}_finite_element_state",
                (inventory["global_independent_rows"],),
            )
            alpha = complex_array(
                arrays,
                f"candidate_{index}_port_amplitudes",
                (inventory["mode_count"],),
            )
            if facts.get("evaluation_available") is not True:
                if record.get("status") != "REJECTED":
                    raise ValueError("V15 PASS packet contains an unevaluated candidate")
                continue

            raw_facts = facts.get("raw_facts")
            if not isinstance(raw_facts, Mapping):
                raise ValueError("evaluated V15 candidate has no raw_facts mapping")
            computed_state_sha = augmented_state_sha256(fe_state, alpha)
            if (
                computed_state_sha != facts.get("state_sha256")
                or computed_state_sha != raw_facts.get("state_sha256")
            ):
                raise ValueError("V15 candidate state hash differs from its saved FE/alpha arrays")
            raw_profile_identity = raw_facts.get("profile_identity")
            if raw_profile_identity is not None and raw_profile_identity != inventory["identity"]:
                raise ValueError("V15 candidate profile identity differs from its packet")
            if inventory["q_count"] == 8 and raw_profile_identity != inventory["identity"]:
                raise ValueError("V18 Ny8 candidate raw facts must explicitly record their profile")
            if int(raw_facts.get("retained_mode_count", -1)) != inventory["mode_count"]:
                raise ValueError("V15 candidate retained mode count differs from profile")

            sector_facts = raw_facts.get("native_sector_facts")
            if (
                not isinstance(sector_facts, Sequence)
                or isinstance(sector_facts, (str, bytes))
                or len(sector_facts) != inventory["twist_count"]
            ):
                raise ValueError("V15 candidate does not cover every registered native sector")
            sector_by_twist = {}
            for sector in sector_facts:
                if not isinstance(sector, Mapping):
                    raise ValueError("V15 candidate sector identity must be a mapping")
                twist = sector.get("twist_index")
                if type(twist) is not int or twist not in range(inventory["twist_count"]) or twist in sector_by_twist:
                    raise ValueError("V15 candidate sector identities are incomplete or duplicated")
                sector_by_twist[twist] = sector
            all_mode_ids = []
            for twist, expected_count in enumerate(inventory["sector_port_counts"]):
                ids = sector_by_twist[twist].get("mode_indices")
                if (
                    not isinstance(ids, Sequence)
                    or isinstance(ids, (str, bytes))
                    or any(type(value) is not int for value in ids)
                ):
                    raise ValueError("V15 candidate sector mode identities are missing")
                ids = list(ids)
                if len(ids) != expected_count:
                    raise ValueError("V15 candidate sector mode count differs from profile")
                all_mode_ids.extend(ids)
            if sorted(all_mode_ids) != list(range(inventory["mode_count"])):
                raise ValueError("V15 candidate does not cover every registered port mode once")

            q_rows = raw_facts.get("q_true_residuals")
            if (
                not isinstance(q_rows, Sequence)
                or isinstance(q_rows, (str, bytes))
                or len(q_rows) != inventory["q_count"]
                or any(not isinstance(row, Mapping) for row in q_rows)
                or any(type(row.get("q")) is not int for row in q_rows)
                or {row["q"] for row in q_rows} != set(range(inventory["q_count"]))
            ):
                raise ValueError("V15 candidate does not cover every registered q phase")

            effective_rhs = complex_array(
                arrays, f"candidate_{index}_effective_rhs", (inventory["global_independent_rows"],)
            )
            port_elimination_action = complex_array(
                arrays,
                f"candidate_{index}_port_elimination_action",
                (inventory["global_independent_rows"],),
            )
            sum_lifted_rhs = complex_array(
                arrays,
                f"candidate_{index}_sum_lifted_effective_rhs",
                (inventory["global_independent_rows"],),
            )
            sum_lifted_actions = complex_array(
                arrays,
                f"candidate_{index}_sum_lifted_native_actions",
                (inventory["global_independent_rows"],),
            )
            global_action = complex_array(
                arrays,
                f"candidate_{index}_global_native_action_independent",
                (inventory["global_independent_rows"],),
            )
            d_b = complex_array(
                arrays, f"candidate_{index}_d_b", (inventory["global_independent_rows"],)
            )
            d_a = complex_array(
                arrays, f"candidate_{index}_d_A", (inventory["global_independent_rows"],)
            )
            b_delta = complex_array(
                arrays,
                f"candidate_{index}_modal_alpha_defect_action",
                (inventory["global_independent_rows"],),
            )
            eliminated_direct = complex_array(
                arrays,
                f"candidate_{index}_eliminated_fe_residual_direct",
                (inventory["global_independent_rows"],),
            )
            eliminated_decomposed = complex_array(
                arrays,
                f"candidate_{index}_eliminated_fe_residual_decomposed",
                (inventory["global_independent_rows"],),
            )
            complete_decomposed = complex_array(
                arrays,
                f"candidate_{index}_complete_fe_residual_decomposed",
                (inventory["global_independent_rows"],),
            )
            complete_fe = complex_array(
                arrays,
                f"candidate_{index}_complete_augmented_fe_residual",
                (inventory["global_independent_rows"],),
            )
            complete_port = complex_array(
                arrays,
                f"candidate_{index}_complete_augmented_port_residual",
                (inventory["mode_count"],),
            )
            alpha_closure = complex_array(
                arrays,
                f"candidate_{index}_alpha_closure_residual",
                (inventory["mode_count"],),
            )
            lifted_errors = [
                complex_array(
                    arrays,
                    f"candidate_{index}_lifted_sector_error_{twist}",
                    (inventory["global_independent_rows"],),
                )
                for twist in range(inventory["twist_count"])
            ]
            lifted_sector_rhs = [
                complex_array(
                    arrays,
                    f"candidate_{index}_lifted_sector_effective_rhs_{twist}",
                    (inventory["global_independent_rows"],),
                )
                for twist in range(inventory["twist_count"])
            ]
            lifted_sector_actions = [
                complex_array(
                    arrays,
                    f"candidate_{index}_lifted_sector_native_action_{twist}",
                    (inventory["global_independent_rows"],),
                )
                for twist in range(inventory["twist_count"])
            ]
            lifted_rhs_sum = np.zeros_like(effective_rhs)
            lifted_action_sum = np.zeros_like(effective_rhs)
            lifted_error_sum = np.zeros_like(effective_rhs)
            for rhs_sector, action_sector, error_sector in zip(
                lifted_sector_rhs, lifted_sector_actions, lifted_errors, strict=True
            ):
                lifted_rhs_sum += rhs_sector
                lifted_action_sum += action_sector
                lifted_error_sum += error_sector
            action_identity_defects = [
                (effective_rhs, fe_rhs - port_elimination_action),
                (sum_lifted_rhs, lifted_rhs_sum),
                (sum_lifted_actions, lifted_action_sum),
                (d_b, effective_rhs - sum_lifted_rhs),
                (d_a, sum_lifted_actions - global_action),
                *[
                    (lifted_errors[twist], lifted_sector_rhs[twist] - lifted_sector_actions[twist])
                    for twist in range(inventory["twist_count"])
                ],
                (
                    eliminated_direct,
                    effective_rhs - global_action,
                ),
                (
                    eliminated_decomposed,
                    d_b + lifted_error_sum + d_a,
                ),
                (eliminated_direct, eliminated_decomposed),
                (complete_decomposed, eliminated_decomposed - b_delta),
                (complete_fe, complete_decomposed),
            ]
            def action_norm(value: np.ndarray) -> float:
                return stable_euclidean_norm(value)

            recomputed_closure_scale = (
                action_norm(effective_rhs)
                + action_norm(global_action)
                + sum(action_norm(value) for value in lifted_sector_rhs)
                + sum(action_norm(value) for value in lifted_sector_actions)
                + action_norm(complete_fe)
                + action_norm(b_delta)
                + action_norm(fe_rhs)
                + action_norm(port_elimination_action)
            )
            producer_closure_defects = (
                (eliminated_direct, eliminated_decomposed),
                (complete_fe, complete_decomposed),
                (effective_rhs, fe_rhs - port_elimination_action),
            )
            closure_norm = max(
                (action_norm(left - right) for left, right in producer_closure_defects),
                default=0.0,
            )
            additional_identity_defect_norm = max(
                (action_norm(left - right) for left, right in action_identity_defects),
                default=0.0,
            )
            closure_relative = (
                closure_norm / recomputed_closure_scale
                if recomputed_closure_scale > 0.0
                else (0.0 if closure_norm == 0.0 else float("inf"))
            )
            recorded_closure_scale = float(
                raw_facts.get("decomposition_closure_scale", np.nan)
            )
            recorded_closure_norm = float(
                raw_facts.get("decomposition_closure_norm", np.nan)
            )
            recorded_original_scale = float(raw_facts.get("effective_rhs_scale", np.nan))
            recomputed_original_scale = action_norm(fe_rhs) + action_norm(port_elimination_action)
            if (
                not _close_float(recorded_closure_scale, recomputed_closure_scale)
                or not _close_float(recorded_closure_norm, closure_norm)
                or not _close_float(
                    recorded_original_scale, recomputed_original_scale
                )
                or not np.isfinite(closure_relative)
                or closure_relative > V15_DECOMPOSITION_CLOSURE_LIMIT
                or (
                    additional_identity_defect_norm / recomputed_closure_scale
                    if recomputed_closure_scale > 0.0
                    else (0.0 if additional_identity_defect_norm == 0.0 else float("inf"))
                ) > V15_DECOMPOSITION_CLOSURE_LIMIT
            ):
                raise ValueError("V15 native budget closure or identity fails on its registered action scale")
            budget_terms = raw_facts.get("budget_term_norms")
            if not isinstance(budget_terms, Mapping):
                raise ValueError("V15 candidate is missing native budget term norms")
            lifted_norms = [stable_euclidean_norm(value) for value in lifted_errors]
            for actual, expected in zip(
                budget_terms.get("lifted_sector_errors", ()), lifted_norms, strict=True
            ):
                if not _close_float(float(actual), expected):
                    raise ValueError("V15 lifted-sector budget norm differs from saved array")
            expected_norms = {
                "d_b": stable_euclidean_norm(d_b),
                "d_A": stable_euclidean_norm(d_a),
                "B_delta_alpha": stable_euclidean_norm(b_delta),
            }
            if any(
                not _close_float(float(budget_terms.get(key, np.nan)), value)
                for key, value in expected_norms.items()
            ):
                raise ValueError("V15 native budget term norm differs from saved array")
            if not (
                norm_matches(raw_facts, "eliminated_fe_residual_norm", eliminated_direct)
                and norm_matches(raw_facts, "complete_augmented_fe_residual_norm", complete_fe)
                and norm_matches(raw_facts, "alpha_closure_residual_norm", alpha_closure)
            ):
                raise ValueError("V15 candidate residual norm differs from saved residual array")
            budget_numerator = (
                expected_norms["d_b"]
                + sum(lifted_norms)
                + expected_norms["d_A"]
                + expected_norms["B_delta_alpha"]
            )
            scale = recorded_original_scale
            budget_relative = (
                budget_numerator / scale
                if scale > 0.0
                else (0.0 if budget_numerator == 0.0 else float("inf"))
            )
            if not _close_float(float(facts.get("metrics", {}).get("noncancelling_budget", np.nan)), budget_relative):
                raise ValueError("V15 candidate non-cancelling budget differs from saved arrays")

            candidate = {
                "state_label": facts.get("state_label", f"candidate_{index}"),
                "metrics": facts.get("metrics"),
                "frozen_scale_metrics": facts.get("frozen_scale_metrics"),
                "structural_gates": facts.get("structural_gates"),
                "state_sha256": computed_state_sha,
                "raw_facts": raw_facts,
            }
            rebuilt = recompute_v15_candidate_facts(
                candidate, profile_identity=inventory["identity"]
            )
            if not rebuilt["raw_facts_consistent"]:
                raise ValueError("V15 candidate raw metrics do not match independent recomputation")
            candidates.append(candidate)

    status = record.get("status")
    if status not in {"PASS", "REJECTED"}:
        raise ValueError("V15 PC packet status is not a recognized state")
    if not candidates:
        if status != "REJECTED" or not isinstance(record.get("failure"), str):
            raise ValueError("V15 packet has no evaluated candidate and no explicit failure")
        return {
            "schema": "task40extra.review_v15_p6_pc_state_packet_recheck.v1",
            "packet_json": str(path),
            "packet_npz": str(npz_path),
            "packet_npz_sha256": actual_npz_sha,
            "profile_identity": inventory["identity"],
            "candidate_count": 0,
            "admission": V15_REFERENCE_PC_REJECTED,
            "numerically_admitted": False,
            "packet_integrity_passed": True,
            "passed": True,
        }
    recomputed_selection = select_v15_reference_pc_candidate(
        candidates, profile_identity=inventory["identity"]
    )
    recorded_selection = record.get("candidate_selection")
    if not isinstance(recorded_selection, Mapping) or (
        recorded_selection.get("admission") != recomputed_selection["admission"]
        or recorded_selection.get("selected_candidate_index")
        != recomputed_selection["selected_candidate_index"]
    ):
        raise ValueError("V15 candidate selector result differs from independently recomputed facts")
    if status == "PASS" and not recomputed_selection["admitted"]:
        raise ValueError("V15 packet claims PASS while its saved candidates are rejected")
    if status == "REJECTED" and recomputed_selection["admitted"]:
        raise ValueError("V15 failure packet contains a candidate that independently passes")
    return {
        "schema": "task40extra.review_v15_p6_pc_state_packet_recheck.v1",
        "packet_json": str(path),
        "packet_npz": str(npz_path),
        "packet_npz_sha256": actual_npz_sha,
        "profile_identity": inventory["identity"],
        "candidate_count": len(candidates),
        "candidate_selection": recomputed_selection,
        "admission": recomputed_selection["admission"],
        "numerically_admitted": recomputed_selection["admitted"],
        "packet_integrity_passed": True,
        "passed": True,
        "operator_reapplied_by_checker": False,
    }


def verify_v10_output_bundle(
    packet_json: str | Path, *, expected_channel_count: int = 532
) -> dict[str, Any]:
    """Reopen output identities and independently recompute saved A6 residuals.

    The checker verifies the saved backend applications and their residual
    algebra.  It does not claim to rerun DOLFINx or independently apply A6.
    The worker's distinct sum-factorized and native applications remain the
    operator evidence.
    """
    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    packet_identity = record.get("identity")
    identity = record.get("scientific_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("V10 output packet has no scientific identity")
    file_checks = []
    for item in identity.get("field_mode_and_diffraction_files", ()):
        file_path = Path(str(item["path"])).resolve()
        actual = _file_sha256(file_path)
        file_checks.append({
            "path": str(file_path),
            "expected_sha256": str(item["sha256"]),
            "actual_sha256": actual,
            "size_bytes": file_path.stat().st_size,
            "passed": actual == item["sha256"],
        })
    if not all(row["passed"] for row in file_checks):
        raise ValueError("V10 scientific field/mode output file identity check failed")

    port_table_paths = [
        Path(str(item["path"])).resolve()
        for item in identity.get("field_mode_and_diffraction_files", ())
        if Path(str(item.get("path", ""))).name == "dtn_port_diffraction_orders_3d.csv"
    ]
    if len(port_table_paths) != 1:
        raise ValueError("V10 output identity must contain exactly one full DtN port table")
    port_mode_table_check = verify_v10_dtn_port_mode_table(
        port_table_paths[0], expected_channel_count=expected_channel_count
    )
    if not port_mode_table_check["passed"]:
        raise ValueError("V10 full top/bottom DtN port mode table is incomplete")

    residual_path = Path(str(identity["full_solution_packet_json"])).resolve()
    residual_record = json.loads(residual_path.read_text(encoding="utf-8"))
    array_manifest = residual_record.get("arrays")
    if not isinstance(array_manifest, Mapping):
        raise ValueError("V10 final full-state packet has no NPZ array manifest")
    npz_path = Path(str(array_manifest["path"])).resolve()
    actual_npz_sha = _file_sha256(npz_path)
    if actual_npz_sha != array_manifest.get("sha256"):
        raise ValueError("V10 final full-state NPZ identity check failed")

    residual_checks = []
    with np.load(npz_path, allow_pickle=False) as arrays:
        rhs = _array_ref(residual_record, "full_physical_rhs_storage", arrays)
        solution = _array_ref(residual_record, "full_solution_storage", arrays)
        if solution.shape != rhs.shape:
            raise ValueError("V10 full solution and physical RHS layouts differ")
        for label, applied_key, residual_key, stored_relative in (
            (
                "sum_factorized_target_backend",
                "target_backend_applied_storage",
                "target_backend_residual_storage",
                float(residual_record["relative_residual"]),
            ),
            (
                "native_full_A6_witness",
                "native_witness_applied_storage",
                "native_witness_residual_storage",
                float(residual_record["native_witness_relative_residual"]),
            ),
        ):
            applied = _array_ref(residual_record, applied_key, arrays)
            saved_residual = _array_ref(residual_record, residual_key, arrays)
            recomputed = rhs - applied
            scale = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
            relative = float(np.linalg.norm(recomputed) / scale)
            algebra_defect = float(
                np.linalg.norm(recomputed - saved_residual)
                / max(scale + float(np.linalg.norm(saved_residual)), np.finfo(float).tiny)
            )
            residual_checks.append({
                "backend": label,
                "recomputed_relative_residual": relative,
                "stored_relative_residual": stored_relative,
                "residual_algebra_defect_relative": algebra_defect,
                "limit": float(residual_record["limit"]),
                "passed": bool(
                    np.isfinite(relative)
                    and relative <= float(residual_record["limit"])
                    and abs(relative - stored_relative) <= 1.0e-12
                    and algebra_defect <= 1.0e-12
                ),
            })
    if not all(row["passed"] for row in residual_checks):
        raise ValueError("V10 independently recomputed saved residual did not pass")
    v16_allocation_ledger = None
    v17_row_tile_assembly = None
    v17_row_tile_allocation_ledger = None
    v17_dispatch_binding = None
    v18_ny8_operator_qualification = None
    v18_ny8_row_tile_allocation_ledger = None
    v18_ny8_dispatch_binding = None
    packet_identity_map = (
        packet_identity if isinstance(packet_identity, Mapping) else {}
    )
    packet_strategy = packet_identity_map.get("q_assembly_strategy")
    scientific_strategy = identity.get("q_assembly_strategy")
    from src.io.physical_intermediate_profile import (
        TASK40_V17_P6_PROFILES,
        TASK40_V18_P6_PROFILES,
    )

    packet_profile = packet_identity_map.get("profile_identity")
    has_registered_v17_profile = (
        isinstance(packet_profile, str) and packet_profile in TASK40_V17_P6_PROFILES
    )
    has_registered_v18_profile = (
        isinstance(packet_profile, str) and packet_profile in TASK40_V18_P6_PROFILES
    )
    if (
        packet_strategy is not None
        and scientific_strategy is not None
        and packet_strategy != scientific_strategy
    ):
        raise ValueError(
            "V10 packet and scientific identities disagree on q assembly strategy"
        )
    if scientific_strategy == "BOUNDED_STAGING_CSR_V16":
        summary_path = path.parent / "task40_v10_p6_candidate_summary.json"
        if not summary_path.is_file():
            raise ValueError("V16 official output is missing its candidate worker summary")
        worker_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        v16_allocation_ledger = _verify_v16_allocation_admission_ledger(
            path.parent, worker_summary
        )
    elif (
        packet_strategy == "ROW_TILE_BOUNDED_CSR_V17"
        or scientific_strategy == "ROW_TILE_BOUNDED_CSR_V17"
        or has_registered_v17_profile
        or has_registered_v18_profile
    ):
        if not isinstance(packet_identity, Mapping):
            raise ValueError("V17 row-tile output is missing its run identity")
        strategy = "ROW_TILE_BOUNDED_CSR_V17"
        source_sha = packet_identity.get("source_sha")
        profile_identity = packet_identity.get("profile_identity")
        run_id = packet_identity.get("run_id")
        stage = packet_identity.get("stage")
        if packet_strategy != strategy or scientific_strategy not in (None, strategy):
            raise ValueError("V17 packet strategy identity is incomplete or inconsistent")
        if (
            not isinstance(source_sha, str)
            or len(source_sha) != 40
            or any(c not in "0123456789abcdef" for c in source_sha.lower())
        ):
            raise ValueError("V17 output identity omits a valid frozen source SHA")
        if not isinstance(profile_identity, str):
            raise ValueError("V17 output identity omits its registered profile")
        if not isinstance(run_id, str) or not isinstance(stage, str):
            raise ValueError("V17 output identity omits run or stage")
        from src.io.physical_intermediate_profile import profile_facts

        profile_contract = profile_facts(profile_identity)
        if (
            profile_contract.get("q_assembly_strategy") != strategy
            or profile_contract.get("run_id") != run_id
            or profile_contract.get("stage") != stage
        ):
            raise ValueError(
                "V17 output identity does not match its registered profile/run/stage contract"
            )
        for field in ("source_sha", "input_sha256", "physical_model_sha256"):
            packet_value = packet_identity.get(field)
            scientific_value = identity.get(field)
            if not isinstance(packet_value, str) or packet_value != scientific_value:
                raise ValueError(f"V17 packet/scientific {field} identities disagree")
        run_manifest_path = path.parent / "run_manifest.json"
        if not run_manifest_path.is_file():
            raise ValueError("V17 official output is missing its run manifest")
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        if (
            run_manifest.get("source_sha") != source_sha
            or run_manifest.get("run_id") != run_id
        ):
            raise ValueError("V17 run manifest differs from the output source/run identity")
        summary_path = path.parent / "task40_v10_p6_candidate_summary.json"
        if not summary_path.is_file():
            raise ValueError("V17 row-tile output is missing its candidate worker summary")
        worker_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_scientific_identity = worker_summary.get("scientific_identity")
        if (
            worker_summary.get("source_sha") != source_sha
            or worker_summary.get("profile") != profile_identity
            or worker_summary.get("q_assembly_strategy") != strategy
            or worker_summary.get("stage") != stage
            or not isinstance(summary_scientific_identity, Mapping)
            or any(
                summary_scientific_identity.get(field) != identity.get(field)
                for field in ("source_sha", "input_sha256", "physical_model_sha256")
            )
        ):
            raise ValueError(
                "V17 worker summary differs from the output source/profile/run/strategy identity"
            )
        row_tile_assembly = _verify_v17_row_tile_assembly_summary(
            path.parent, worker_summary
        )
        if has_registered_v18_profile:
            inventory = _registered_v15_profile_inventory(profile_identity)
            v18_ny8_operator_qualification = _verify_v18_ny8_operator_qualification(
                worker_summary, inventory
            )
            if (
                identity.get("complete_operator_qualification_sha256")
                != v18_ny8_operator_qualification[
                    "complete_operator_qualification_sha256"
                ]
            ):
                raise ValueError(
                    "V18 official output identity is not bound to the checked complete-operator record"
                )
            v18_ny8_row_tile_allocation_ledger = _verify_q_assembly_allocation_admission_ledger(
                path.parent, worker_summary, version="v18_ny8_row_tile"
            )
            v18_ny8_dispatch_binding = {
                "source_sha": source_sha,
                "profile_identity": profile_identity,
                "run_id": run_id,
                "stage": stage,
                "q_assembly_strategy": strategy,
                "registered_profile_contract_passed": True,
                "packet_scientific_identity_match_passed": True,
                "worker_summary_binding_passed": True,
                "run_manifest_binding_passed": True,
                "complete_operator_checker_passed": True,
            }
        else:
            v17_row_tile_assembly = row_tile_assembly
            v17_row_tile_allocation_ledger = _verify_v17_row_tile_allocation_admission_ledger(
                path.parent, worker_summary
            )
            v17_dispatch_binding = {
            "identity_source": (
                "official_output.identity + adjacent run_manifest.json + "
                "task40_v10_p6_candidate_summary.json"
            ),
            "source_sha": source_sha,
            "profile_identity": profile_identity,
            "run_id": run_id,
            "stage": stage,
            "q_assembly_strategy": strategy,
            "registered_profile_contract_passed": True,
            "packet_scientific_identity_match_passed": True,
            "worker_summary_binding_passed": True,
            "run_manifest_binding_passed": True,
            }
    return {
        "schema": "task40extra.review_v10_output_packet_recheck.v1",
        "packet_json": str(path),
        "residual_packet_json": str(residual_path),
        "residual_packet_npz": str(npz_path),
        "residual_packet_npz_sha256": actual_npz_sha,
        "full_solution_storage_sha256": str(identity["full_solution_storage_sha256"]),
        "ordered_physical_mode_sha256": str(identity["ordered_physical_mode_sha256"]),
        "field_mode_and_diffraction_file_checks": file_checks,
        "full_dtn_port_mode_table_check": port_mode_table_check,
        "residual_checks": residual_checks,
        "v16_allocation_admission_ledger": v16_allocation_ledger,
        "v17_row_tile_assembly": v17_row_tile_assembly,
        "v17_row_tile_allocation_admission_ledger": v17_row_tile_allocation_ledger,
        "v17_dispatch_binding": v17_dispatch_binding,
        "v18_ny8_operator_qualification": v18_ny8_operator_qualification,
        "v18_ny8_row_tile_assembly": (
            row_tile_assembly if has_registered_v18_profile else None
        ),
        "v18_ny8_row_tile_allocation_admission_ledger": v18_ny8_row_tile_allocation_ledger,
        "v18_ny8_dispatch_binding": v18_ny8_dispatch_binding,
        "operator_reapplied_by_checker": False,
        "status": "PASS",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet_json", type=Path)
    parser.add_argument("--regular-internal-witness", action="store_true")
    parser.add_argument("--v15-pc-state-packet", action="store_true")
    parser.add_argument(
        "--receipt-output",
        type=Path,
        help="V15 PC checker receipt path (defaults beside the packet)",
    )
    parser.add_argument(
        "--expected-channel-count",
        type=int,
        choices=(340, 532, 588),
        default=532,
        help="explicit case contract: 532 for B0, 340 for Gx560, 588 for E1",
    )
    args = parser.parse_args(argv)
    selected_checks = sum(
        (bool(args.regular_internal_witness), bool(args.v15_pc_state_packet))
    )
    if selected_checks > 1:
        parser.error("select at most one packet-specific checker mode")
    if args.v15_pc_state_packet:
        packet_path = args.packet_json.resolve()
        receipt_path = args.receipt_output or packet_path.with_name(
            f"{packet_path.stem}.v15_checker_receipt.json"
        )
        receipt_path = receipt_path.resolve()
        try:
            result = verify_v15_pc_state_packet(packet_path)
        except Exception as exc:
            receipt = {
                "schema": "task40extra.review_v15_pc_state_checker_receipt.v1",
                "checker": "verify_v15_pc_state_packet",
                "status": "REJECTED",
                "packet_json": str(packet_path),
                "packet_json_sha256": (
                    _file_sha256(packet_path) if packet_path.is_file() else None
                ),
                "passed": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with receipt_path.open("x", encoding="utf-8") as stream:
                json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            print(json.dumps({"receipt_path": str(receipt_path), **receipt}, sort_keys=True, indent=2))
            return 2
        receipt = {
            "schema": "task40extra.review_v15_pc_state_checker_receipt.v1",
            "checker": "verify_v15_pc_state_packet",
            "status": "PASS",
            "packet_json": str(packet_path),
            "packet_json_sha256": _file_sha256(packet_path),
            "packet_npz": result["packet_npz"],
            "packet_npz_sha256": result["packet_npz_sha256"],
            "passed": True,
            "result": result,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"receipt_path": str(receipt_path), **receipt}, sort_keys=True, indent=2))
        return 0
    elif args.regular_internal_witness:
        result = verify_v10_regular_internal_witness(args.packet_json)
    else:
        if args.receipt_output is not None:
            parser.error("--receipt-output is supported with --v15-pc-state-packet only")
        result = verify_v10_output_bundle(
            args.packet_json, expected_channel_count=args.expected_channel_count
        )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
