"""Independent full-A6 and identity checker for the Task41 P0 A1 result."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Mapping

import numpy as np

from src.geometry.task41_phi90_profile import (
    TASK41_B0_COMPARISON_GROUP,
    TASK41_B0_GEOMETRY_IDENTITY,
    TASK41_B0_PRECONDITIONER,
    TASK41_B0_RUN_ID,
    TASK41_G13_A2_PRECONDITIONER,
    TASK41_G13_A2_RUN_ID,
    task41_direct_summary_errors,
)
from src.io import load_and_resolve
from src.runners.task41_p0_contract import (
    TASK41_A1_COMPARISON_BINDING_RELATIVE,
    require_task41_a1_comparison_binding,
    contract_relative_path,
    require_task41_p0_contract,
    sha256_file,
    task41_case_id_for_run_id,
    validate_task41_specification,
)
from src.runners.task41_p0_comparison import (
    TASK41_COMPARISON_SCHEMA,
    TASK41_MODE_RELATIVE_LIMIT,
    compare_task41_modal_artifacts,
    compare_task41_power_totals,
    evaluate_task41_metric_packet,
)

CHECKER_SCHEMA = "task41.p0.direct_checker.v1"
A2_CHECKER_SCHEMA = "task41.p0.a2_iterative_checker.v1"
B0_CHECKER_SCHEMA = "task41.p0.b0_iterative_checker.v1"
TASK41_P0_V5_FROZEN_DENOMINATORS = (2225.481253487629, 2225.4807123031883)
TASK41_P0_V5_RELATIVE_TOLERANCE = 1.0e-11
TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256 = (
    "a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031"
)


def evaluate_task41_numerical_summary(
    summary: Mapping[str, Any], numerical_output_directory: str | Path
) -> list[str]:
    """Recompute Task41 native full-space A6, recovery, MUMPS, and energy gates."""
    return task41_direct_summary_errors(summary, numerical_output_directory)


def _task41_a2_diagnostic_inventory_from_data(
    metrics: Mapping[str, Any],
    orders: Any,
    *,
    expected_m_max: int,
    expected_n_max: int,
) -> dict[str, Any]:
    """Recompute the diagnostic grid from raw rows, independently of worker status."""
    rows = orders if isinstance(orders, list) else []
    valid_bounds = (
        type(expected_m_max) is int
        and expected_m_max >= 0
        and type(expected_n_max) is int
        and expected_n_max >= 0
    )
    expected = (
        {
            (m, n, pol)
            for m in range(-expected_m_max, expected_m_max + 1)
            for n in range(-expected_n_max, expected_n_max + 1)
            for pol in ("s", "p")
        }
        if valid_bounds
        else set()
    )
    actual: list[tuple[int, int, str]] = []
    malformed = 0
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or type(row.get("m")) is not int
            or type(row.get("n")) is not int
            or row.get("polarization") not in {"s", "p"}
        ):
            malformed += 1
            continue
        actual.append((row["m"], row["n"], row["polarization"]))
    spatial_count = len(expected) // 2
    channel_count = len(expected)
    checks = {
        "resolved_reporting_bounds_match_frozen_config": bool(
            valid_bounds
            and metrics.get("diffraction_order_max_m_requested") == expected_m_max
            and metrics.get("diffraction_order_max_n_requested") == expected_n_max
            and metrics.get("diffraction_order_max_m_resolved") == expected_m_max
            and metrics.get("diffraction_order_max_n_resolved") == expected_n_max
        ),
        "spatial_counts_match_frozen_grid": bool(
            metrics.get("diffraction_order_count") == spatial_count
            and metrics.get("diffraction_fit_order_count") == spatial_count
        ),
        "polarized_row_count_matches_grid": len(rows) == channel_count,
        "channel_count_matches_grid": metrics.get("diffraction_channel_count") == channel_count,
        "raw_polarization_keys_are_unique_and_complete": bool(
            malformed == 0 and len(actual) == len(set(actual)) and set(actual) == expected
        ),
    }
    return {
        "schema": "task41.p0.independent_diagnostic_inventory.v1",
        "frozen_reporting_order_bounds": {
            "m_max": expected_m_max,
            "n_max": expected_n_max,
        },
        "expected_spatial_order_count": spatial_count,
        "expected_channel_count": channel_count,
        "actual_order_rows": len(rows),
        "malformed_order_rows": malformed,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _task41_artifact_path(root: Path, binding: Mapping[str, Any], name: str) -> Path:
    artifacts = binding["a1"]["comparison_artifacts"]
    record = artifacts[name]
    raw = Path(str(record["path"]))
    path = (raw if raw.is_absolute() else root / raw).resolve(strict=True)
    if path.stat().st_size != record["bytes"] or sha256_file(path) != record["sha256"]:
        raise ValueError(f"bound A1 comparison artifact changed: {name}")
    return path


def _task41_npz_array(path: Path, key: str) -> np.ndarray:
    import numpy as np

    with np.load(path, allow_pickle=False) as arrays:
        if key not in arrays.files:
            raise ValueError(f"Task41 bound NPZ artifact omits {key!r}")
        return np.array(arrays[key], copy=True)


def _task40_packet_array(packet: Mapping[str, Any], key: str) -> np.ndarray:
    arrays_record = packet.get("arrays")
    if not isinstance(arrays_record, Mapping):
        raise ValueError("Task41 output packet omits its array manifest")
    npz_path = Path(str(arrays_record.get("path", ""))).resolve(strict=True)
    if sha256_file(npz_path) != arrays_record.get("sha256"):
        raise ValueError("Task41 output packet NPZ hash changed")
    with np.load(npz_path, allow_pickle=False) as arrays:
        reference = packet.get(key)
        if not isinstance(reference, Mapping) or reference.get("array_key") not in arrays.files:
            raise ValueError(f"Task41 output packet omits raw array {key!r}")
        value = np.asarray(arrays[reference["array_key"]])
        if list(value.shape) != reference.get("shape") or str(value.dtype) != reference.get("dtype"):
            raise ValueError(f"Task41 output packet array identity changed for {key}")
        return np.array(value, copy=True)


def _load_task41_a2_full_solution(output_packet: Mapping[str, Any]) -> np.ndarray:
    scientific = output_packet.get("scientific_identity")
    if not isinstance(scientific, Mapping):
        raise ValueError("Task41 A2 official output omits scientific identity")
    residual_path = Path(str(scientific.get("full_solution_packet_json", ""))).resolve(strict=True)
    residual = _json_object(residual_path, "A2 full-solution residual packet")
    return _task40_packet_array(residual, "full_solution_storage").astype(np.complex128, copy=False)


def _task41_run_artifact(root: Path, record: Mapping[str, Any], label: str) -> Path:
    raw = Path(str(record.get("path", "")))
    path = (raw if raw.is_absolute() else root / raw).resolve(strict=True)
    if (
        not path.is_relative_to(root.resolve())
        or (
            record.get("bytes") is not None
            and (
                type(record.get("bytes")) is not int
                or path.stat().st_size != record["bytes"]
            )
        )
        or not isinstance(record.get("sha256"), str)
        or sha256_file(path) != record.get("sha256")
    ):
        raise ValueError(f"Task41 A2 {label} artifact is outside its run or changed")
    return path


def _task41_npy_artifact(
    root: Path, record: Mapping[str, Any], label: str
) -> np.ndarray:
    path = _task41_run_artifact(root, record, label)
    value = np.load(path, mmap_mode="r", allow_pickle=False)
    if (
        not isinstance(value, np.ndarray)
        or (record.get("shape") is not None and list(value.shape) != record.get("shape"))
        or (
            record.get("dtype") is not None
            and np.dtype(value.dtype) != np.dtype(str(record.get("dtype")))
        )
    ):
        raise ValueError(f"Task41 A2 {label} array identity changed")
    return value


def _task41_b0_owned_writable_lu_pivots(
    raw_pivots: np.ndarray, *, order: int
) -> np.ndarray:
    """Copy validated SciPy 0-based pivots into writable owned int32 storage."""
    pivots = np.asarray(raw_pivots)
    if (
        type(order) is not int
        or order < 1
        or order > np.iinfo(np.int32).max
        or pivots.shape != (order,)
        or pivots.dtype.kind not in "iu"
        or not np.isfinite(pivots).all()
    ):
        raise ValueError("Task41 B0 LU pivots have an invalid zero-based layout")
    zero_based_steps = np.arange(order, dtype=np.int64)
    if np.any(pivots < zero_based_steps) or np.any(pivots >= order):
        raise ValueError("Task41 B0 LU pivots are outside SciPy's zero-based pivot range")
    writable = np.array(pivots, dtype=np.int32, order="C", copy=True)
    if not writable.flags.owndata or not writable.flags.writeable:
        raise ValueError("Task41 B0 LU pivots were not copied to writable owned storage")
    return writable


def _task41_sparse_identity(matrix: Any) -> str:
    digest = hashlib.sha256()
    digest.update(str(matrix.format).encode("ascii"))
    digest.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
    digest.update(np.dtype(matrix.dtype).str.encode("ascii"))
    for name in ("indptr", "indices", "data"):
        values = np.ascontiguousarray(getattr(matrix, name))
        digest.update(name.encode("ascii"))
        digest.update(values.dtype.str.encode("ascii"))
        digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
        digest.update(memoryview(values).cast("B"))
    return digest.hexdigest()


def _task41_relative_vector_error(actual: np.ndarray, expected: np.ndarray) -> float:
    left = np.asarray(actual, dtype=np.complex128).reshape(-1)
    right = np.asarray(expected, dtype=np.complex128).reshape(-1)
    if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError("Task41 A2 independent vector action has invalid shape or values")
    return float(
        np.linalg.norm(left - right)
        / max(float(np.linalg.norm(right)), np.finfo(float).tiny)
    )


def _task41_a2_verify_saved_q_consumer_receipt(
    *,
    repo_root: Path,
    artifact_root: Path,
    reuse_binding: Mapping[str, Any],
    consumer_execution: Mapping[str, Any],
    q: int,
    entry: Mapping[str, Any],
    receipt: Mapping[str, Any],
    manifest_path: Path,
    qualification_path: Path,
    manifest: Mapping[str, Any],
    qualification: Mapping[str, Any],
) -> None:
    """Recheck the immutable prior native PASS and the new consumer receipt."""
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_qualified_q_csr import make_v31_q_csr_import_authorization

    expected_twist = q % TASK41_G13_A2_P6_PROFILE.replication_count
    authorization_map = reuse_binding.get("consumer_import_authorizations")
    expected_authorization = (
        authorization_map.get(str(q)) if isinstance(authorization_map, Mapping) else None
    )
    consumer_ref = receipt.get("consumer_receipt")
    if not isinstance(expected_authorization, Mapping) or not isinstance(consumer_ref, Mapping):
        raise ValueError(f"Task41 A2 imported q={q} omits its contract authorization or consumer receipt")
    consumer_path = _task41_run_artifact(
        artifact_root, consumer_ref, f"q{q} V31 consumer receipt"
    )
    consumer = _json_object(consumer_path, f"q={q} V31 consumer receipt")
    manifest_ref = entry.get("csr_manifest")
    qualification_ref = entry.get("native_qualification")
    matrix_source = manifest.get("matrix_source_identity")
    producer_execution = manifest.get("execution_identity")
    native_execution = qualification.get("execution_identity")
    artifacts = manifest.get("csr_artifacts")
    if (
        not isinstance(manifest_ref, Mapping)
        or not isinstance(qualification_ref, Mapping)
        or not isinstance(matrix_source, Mapping)
        or not isinstance(producer_execution, Mapping)
        or not isinstance(native_execution, Mapping)
        or not isinstance(artifacts, Mapping)
    ):
        raise ValueError(f"Task41 A2 imported q={q} saved producer records are incomplete")
    normalized_artifacts = {}
    for name in ("data", "indices", "indptr"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            raise ValueError(f"Task41 A2 imported q={q} CSR manifest omits {name}")
        raw_path = Path(str(record.get("path", "")))
        artifact_path = (raw_path if raw_path.is_absolute() else manifest_path.parent / raw_path).resolve()
        if not artifact_path.is_relative_to(repo_root):
            raise ValueError(f"Task41 A2 imported q={q} CSR {name} escaped the repository")
        normalized_artifacts[name] = {
            "path": str(artifact_path),
            "bytes": record.get("bytes"),
            "sha256": record.get("sha256"),
        }
    expected = make_v31_q_csr_import_authorization(
        q_index=q,
        twist_index=expected_twist,
        profile=str(manifest.get("profile", "")),
        operator_identity=manifest.get("operator_identity", {}),
        matrix_source_identity=matrix_source,
        producer_identity=manifest.get("producer_identity", {}),
        producer_execution_identity=producer_execution,
        native_execution_identity=native_execution,
        csr_manifest_sha256=str(manifest_ref.get("sha256", "")),
        native_qualification_sha256=str(qualification_ref.get("sha256", "")),
        csr_artifacts=normalized_artifacts,
        consumer_execution_identity=consumer_execution,
    )
    expected_consumer_sha = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if (
        expected != expected_authorization
        or receipt.get("qualification_kind") != "V30_NATIVE_PASS"
        or receipt.get("qualification_status") != "PASS"
        or receipt.get("csr_manifest_path") != str(manifest_path)
        or receipt.get("csr_manifest_sha256") != manifest_ref.get("sha256")
        or receipt.get("native_qualification_path") != str(qualification_path)
        or receipt.get("native_qualification_sha256") != qualification_ref.get("sha256")
        or receipt.get("selector_sha256") != reuse_binding.get("selector_sha256")
        or consumer.get("schema") != "task40extra.review_v31_q_csr_consumer_receipt.v1"
        or consumer.get("status") != "CONSUMED_COMPLETE_CSR_NATIVE_PASS"
        or consumer.get("q_index") != q
        or consumer.get("twist_index") != expected_twist
        or manifest.get("twist_index") != expected_twist
        or qualification.get("twist_index") != expected_twist
        or entry.get("twist_index") != expected_twist
        or consumer.get("profile") != manifest.get("profile")
        or consumer.get("operator_identity") != manifest.get("operator_identity")
        or consumer.get("matrix_source_identity") != matrix_source
        or consumer.get("producer_identity") != manifest.get("producer_identity")
        or consumer.get("producer_execution_identity") != producer_execution
        or consumer.get("native_execution_identity") != native_execution
        or consumer.get("consumer_execution_identity") != consumer_execution
        or consumer.get("csr_manifest")
        != {"path": str(manifest_path), "sha256": manifest_ref.get("sha256")}
        or consumer.get("native_qualification")
        != {
            "path": str(qualification_path),
            "sha256": qualification_ref.get("sha256"),
            "status": "PASS",
        }
        or consumer.get("authorization") != expected
        or consumer.get("authorization_sha256") != expected_consumer_sha
        or consumer.get("csr_artifacts") != normalized_artifacts
        or consumer.get("original_manifest_and_native_pass_rewritten") is not False
    ):
        raise ValueError(f"Task41 A2 imported q={q} consumer receipt does not preserve its producer PASS")


def _task41_iterative_reference_audit_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    *,
    repo_root: Path | None = None,
    case_id: str = "A2",
    b0_profile_capability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reapply saved q CSR actions and both factor probe residuals from raw vectors."""
    from scipy import sparse

    from src.solvers.task40_v10_p6_periodic_profile import (
        TASK41_G13_A2_P6_PROFILE,
        task41_b0_periodic_profile,
    )

    if case_id not in {"A2", "B0"}:
        raise ValueError("Task41 iterative audit supports only A2 or B0")
    if case_id == "B0":
        if (
            not isinstance(b0_profile_capability, Mapping)
            or b0_profile_capability.get("verified") is not True
            or b0_profile_capability.get("identity") != TASK41_B0_PRECONDITIONER
        ):
            raise ValueError("Task41 B0 iterative audit requires its reopened profile capability")
        profile = task41_b0_periodic_profile(
            tuple(map(int, b0_profile_capability.get("q_port_counts", ()))),
            tuple(map(int, b0_profile_capability.get("sector_port_counts", ()))),
        )
    else:
        profile = TASK41_G13_A2_P6_PROFILE

    artifact_root = numerical_output.parent.resolve()
    repo_root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    authority = summary.get("campaign_authority", {})
    reuse_binding = (
        authority.get("q_csr_reuse") if isinstance(authority, Mapping) else None
    )
    consumer_execution = {
        "source_sha": authority.get("source_sha") if isinstance(authority, Mapping) else None,
        "window_sha256": (
            authority.get("campaign_window_sha256")
            if isinstance(authority, Mapping)
            else None
        ),
    }
    imported_saved_q_indices: set[int] = set()
    snapshot = summary.get("reference_audit_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("Task41 A2 worker summary omits its pre-destroy reference audit")
    sectors = snapshot.get("sector_audits_before_destroy")
    factor = snapshot.get("factor_audit_before_destroy")
    q_matrix_audits = snapshot.get("q_matrix_audits_before_destroy")
    if (
        not isinstance(sectors, list)
        or len(sectors) != profile.replication_count
        or not isinstance(factor, Mapping)
        or not isinstance(q_matrix_audits, Mapping)
    ):
        raise ValueError("Task41 A2 reference audit omits five sectors or its All-Q factor audit")

    q_count = profile.q_count
    q_indices = list(range(q_count))
    if (
        factor.get("all_q_required") != q_indices
        or factor.get("numeric_ready_q") != q_indices
        or factor.get("all_q_numeric_ready") is not True
        or factor.get("all_q_factors_retained_simultaneously") is not True
        or factor.get("all_q_factor_objects_live_simultaneously") is not True
        or factor.get("all_q_numeric_factors_strict_true_residual_passed") is not True
        or factor.get("all_q_second_rhs_strict_true_residual_passed") is not True
        or factor.get("all_q_fresh_probe_and_second_rhs_passed") is not True
        or factor.get("factors_live_count_current") != q_count
        or factor.get("strict_factor_qualification_required") is not True
    ):
        raise ValueError("Task41 A2 All-Q factor audit does not record ten live strict q factors")
    second_contract = factor.get("second_rhs_qualification")
    if (
        not isinstance(second_contract, Mapping)
        or second_contract.get("schema") != f"task41.p0.{case_id.lower()}_all_q_second_rhs.v1"
        or second_contract.get("formula")
        != "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13"
        or second_contract.get("strict_limit") != 1.0e-10
        or second_contract.get("all_entries_nonzero") is not True
        or second_contract.get("distinct_from_direct_cos_sin_probe") is not True
    ):
        raise ValueError("Task41 A2 All-Q factor audit has the wrong strict second-RHS contract")

    def by_q(rows: Any, label: str) -> dict[int, Mapping[str, Any]]:
        if not isinstance(rows, list):
            raise ValueError(f"Task41 A2 All-Q {label} inventory is missing")
        result: dict[int, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping) or type(row.get("q")) is not int:
                raise ValueError(f"Task41 A2 All-Q {label} row is malformed")
            q = int(row["q"])
            if q in result:
                raise ValueError(f"Task41 A2 All-Q {label} repeats q={q}")
            result[q] = row
        if set(result) != set(q_indices):
            raise ValueError(f"Task41 A2 All-Q {label} does not cover q=0..9")
        return result

    factor_tests = by_q(factor.get("factor_tests"), "fresh factor probes")
    second_tests = by_q(factor.get("second_rhs_tests"), "second-RHS probes")
    factor_inputs = by_q(factor.get("factor_inputs"), "factor input identities")

    sector_by_q: dict[int, tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = {}
    expected_sector_pairs = {
        (twist, twist + profile.replication_count)
        for twist in range(profile.replication_count)
    }
    actual_sector_pairs: set[tuple[int, int]] = set()
    for sector_index, sector in enumerate(sectors):
        if not isinstance(sector, Mapping):
            raise ValueError(f"Task41 A2 sector audit {sector_index} is malformed")
        raw_pair = sector.get("q_indices")
        if not isinstance(raw_pair, list) or len(raw_pair) != 2:
            raise ValueError(f"Task41 A2 sector audit {sector_index} lacks its q pair")
        pair = tuple(sorted(int(q) for q in raw_pair))
        if pair not in expected_sector_pairs or pair in actual_sector_pairs:
            raise ValueError("Task41 A2 sector audit has an unexpected or duplicate q pair")
        actual_sector_pairs.add(pair)
        preparation = sector.get(f"task41_{case_id.lower()}_independent_q_csr_preparation")
        if not isinstance(preparation, Mapping):
            raise ValueError(f"Task41 A2 sector {pair} omits its independent CSR preparation")
        saved_import = (
            preparation.get("schema")
            == "task41.p0.a2_saved_q_csr_import_audit.v1"
        )
        identity = preparation.get("qualification_identity")
        if saved_import:
            if case_id != "A2":
                raise ValueError("Task41 B0 cannot use saved A1/A2 q-CSR evidence")
            from src.runners.task41_p0_contract import (
                TASK41_A2_Q_CSR_REUSE_SCHEMA,
                TASK41_A2_Q_CSR_REUSE_SCHEMA_V1,
            )

            pair_twist = pair[0]
            binding_schema = (
                reuse_binding.get("schema") if isinstance(reuse_binding, Mapping) else None
            )
            authorization_rows = (
                reuse_binding.get("consumer_import_authorizations")
                if isinstance(reuse_binding, Mapping)
                else None
            )
            if binding_schema == TASK41_A2_Q_CSR_REUSE_SCHEMA_V1:
                authorized_binding = (
                    isinstance(authorization_rows, Mapping)
                    and pair == (0, 5)
                    and reuse_binding.get("q_indices") == [0, 5]
                    and reuse_binding.get("twist_index") == 0
                    and set(authorization_rows) == {"0", "5"}
                )
            elif binding_schema == TASK41_A2_Q_CSR_REUSE_SCHEMA:
                expected_q_indices = list(range(profile.q_count))
                expected_twists = {
                    str(q): q % profile.replication_count
                    for q in expected_q_indices
                }
                authorized_binding = (
                    isinstance(authorization_rows, Mapping)
                    and reuse_binding.get("q_indices") == expected_q_indices
                    and reuse_binding.get("twist_indices_by_q") == expected_twists
                    and set(authorization_rows) == {str(q) for q in expected_q_indices}
                )
            else:
                authorized_binding = False
            if (
                not authorized_binding
                or preparation.get("qualification_origin")
                != "saved_v30_native_pass_cross_window_import"
                or preparation.get("selected_q_indices") != list(pair)
                or preparation.get("imported_saved_q_indices") != list(pair)
                or preparation.get("twist_index") != pair_twist
                or preparation.get("all_complete_native_pass") is not True
                or preparation.get("four_complete_csr_actions_passed") is not True
                or preparation.get("paired_sector_leakage_passed") is not True
                or not isinstance(identity, Mapping)
                or identity.get("q_indices") != list(pair)
                or identity.get("twist_index") != pair_twist
                or identity.get("profile_identity") != profile.identity()
                or not isinstance(consumer_execution.get("source_sha"), str)
                or not isinstance(consumer_execution.get("window_sha256"), str)
            ):
                raise ValueError("Task41 A2 saved q import is not authorized for its exact paired sector")
        elif (
            preparation.get("selected_q_indices") != list(pair)
            or preparation.get("all_complete_native_pass") is not True
            or preparation.get("four_complete_csr_actions_passed") is not True
            or preparation.get("paired_sector_leakage_passed") is not True
            or not isinstance(identity, Mapping)
            or identity.get("q_indices") != list(pair)
            or identity.get("twist_index") != pair[0]
            or identity.get("profile_identity") != profile.identity()
        ):
            raise ValueError(f"Task41 A2 sector {pair} failed its saved CSR qualification gates")
        entries = preparation.get("selector_entries")
        receipts = preparation.get("qualification_receipts")
        native_facts = preparation.get("native_facts_by_q")
        if (
            not isinstance(entries, list)
            or not isinstance(receipts, list)
            or len(entries) != 2
            or len(receipts) != 2
            or (
                not saved_import
                and (
                    not isinstance(native_facts, Mapping)
                    or set(native_facts) != {str(q) for q in pair}
                )
            )
        ):
            raise ValueError(f"Task41 A2 sector {pair} does not preserve both q receipts")
        entries_by_q = {int(row["q_index"]): row for row in entries if isinstance(row, Mapping)}
        receipts_by_q = {int(row["q_index"]): row for row in receipts if isinstance(row, Mapping)}
        if set(entries_by_q) != set(pair) or set(receipts_by_q) != set(pair):
            raise ValueError(f"Task41 A2 sector {pair} has a malformed q receipt inventory")
        for q in pair:
            entry = entries_by_q[q]
            receipt = receipts_by_q[q]
            facts = native_facts[str(q)] if isinstance(native_facts, Mapping) else None
            if saved_import:
                if (
                    entry.get("twist_index") != pair[0]
                    or receipt.get("q_index") != q
                    or receipt.get("twist_index") != pair[0]
                    or receipt.get("qualification_kind") != "V30_NATIVE_PASS"
                    or receipt.get("qualification_status") != "PASS"
                    or not isinstance(receipt.get("maximum_relative_error"), (int, float))
                    or receipt.get("maximum_relative_error") > 1.0e-11
                ):
                    raise ValueError(f"Task41 A2 q={q} saved native PASS receipt is incomplete")
            elif (
                entry.get("twist_index") != pair[0]
                or receipt.get("twist_index") != pair[0]
                or entry.get("manifest_status") != "COMPLETE_CSR"
                or entry.get("qualification_status") != "PASS"
                or receipt.get("manifest_status") != "COMPLETE_CSR"
                or receipt.get("qualification_status") != "PASS"
                or not isinstance(facts, Mapping)
                or facts.get("status") != "PASS"
                or facts.get("four_complete_csr_actions_passed") is not True
                or facts.get("paired_sector_leakage_passed") is not True
            ):
                raise ValueError(f"Task41 A2 q={q} selector receipt is not a complete native PASS")
            manifest_ref = entry.get("csr_manifest")
            qualification_ref = entry.get("native_qualification")
            if not isinstance(manifest_ref, Mapping) or not isinstance(qualification_ref, Mapping):
                raise ValueError(f"Task41 A2 q={q} selector entry omits hash-bound receipts")
            if saved_import:
                if (
                    Path(str(receipt.get("csr_manifest_path", ""))).resolve()
                    != Path(str(manifest_ref.get("path", ""))).resolve()
                    or receipt.get("csr_manifest_sha256") != manifest_ref.get("sha256")
                    or Path(str(receipt.get("native_qualification_path", ""))).resolve()
                    != Path(str(qualification_ref.get("path", ""))).resolve()
                    or receipt.get("native_qualification_sha256") != qualification_ref.get("sha256")
                ):
                    raise ValueError(f"Task41 A2 q={q} imported selector and provider receipt hashes disagree")
            elif (
                receipt.get("csr_manifest_path") != manifest_ref.get("path")
                or receipt.get("csr_manifest_sha256") != manifest_ref.get("sha256")
                or receipt.get("native_qualification_path") != qualification_ref.get("path")
                or receipt.get("native_qualification_sha256") != qualification_ref.get("sha256")
                or facts.get("csr_manifest_sha256") != manifest_ref.get("sha256")
                or facts.get("native_qualification_sha256") != qualification_ref.get("sha256")
            ):
                raise ValueError(f"Task41 A2 q={q} sector receipt hashes disagree")
            evidence_root = repo_root if saved_import else artifact_root
            manifest_path = _task41_run_artifact(
                evidence_root, manifest_ref, f"q{q} CSR manifest"
            )
            qualification_path = _task41_run_artifact(
                evidence_root, qualification_ref, f"q{q} native qualification"
            )
            manifest = _json_object(manifest_path, f"q={q} CSR manifest")
            qualification = _json_object(qualification_path, f"q={q} native qualification")
            if (
                manifest.get("schema") != "task40extra.review_v30_q_csr.v1"
                or manifest.get("status") != "COMPLETE_CSR"
                or manifest.get("q_index") != q
                or manifest.get("twist_index") != pair[0]
                or manifest.get("profile") != profile.name
                or manifest.get("shape") != entry.get("shape")
                or qualification.get("schema")
                != "task40extra.review_v30_q_csr_native_qualification.v1"
                or qualification.get("status") != "PASS"
                or qualification.get("q_index") != q
                or qualification.get("twist_index") != pair[0]
                or qualification.get("csr_manifest_sha256") != manifest_ref.get("sha256")
                or qualification.get("four_complete_csr_actions_passed") is not True
                or qualification.get("csr_action_count") != 4
                or qualification.get("paired_sector_leakage_passed") is not True
                or qualification.get("relative_error_limit") != 1.0e-11
                or qualification.get("maximum_relative_error")
                != receipt.get("maximum_relative_error")
            ):
                raise ValueError(f"Task41 A2 q={q} CSR manifest or qualification is invalid")
            arrays = qualification.get("native_array_artifacts")
            csr_artifacts = manifest.get("csr_artifacts")
            required_arrays = {
                *(f"input_{name}" for name in ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")),
                *(f"csr_{name}" for name in ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")),
                *(f"native_{name}" for name in ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")),
                *(f"component_case1_{name}" for name in ("volume", "minus_D", "C", "Hhat")),
                "paired_peer_input",
                "paired_peer_native_diagonal",
                "paired_peer_native_cross",
                "paired_selected_native_cross",
            }
            if not isinstance(arrays, Mapping) or not required_arrays.issubset(arrays):
                raise ValueError(f"Task41 A2 q={q} CSR qualification omits required raw vectors")
            if not isinstance(csr_artifacts, Mapping) or set(csr_artifacts) != {"data", "indices", "indptr"}:
                raise ValueError(f"Task41 A2 q={q} CSR manifest omits its three arrays")
            if saved_import:
                _task41_a2_verify_saved_q_consumer_receipt(
                    repo_root=repo_root,
                    artifact_root=artifact_root,
                    reuse_binding=reuse_binding,
                    consumer_execution=consumer_execution,
                    q=q,
                    entry=entry,
                    receipt=receipt,
                    manifest_path=manifest_path,
                    qualification_path=qualification_path,
                    manifest=manifest,
                    qualification=qualification,
                )
                imported_saved_q_indices.add(q)
            sector_by_q[q] = (manifest, qualification, arrays)
        if actual_sector_pairs != expected_sector_pairs:
            continue
    if actual_sector_pairs != expected_sector_pairs or set(sector_by_q) != set(q_indices):
        raise ValueError("Task41 A2 sector audits do not cover all ten q branches")

    def load_csr(q: int):
        manifest, _qualification, _arrays = sector_by_q[q]
        records = manifest["csr_artifacts"]
        evidence_root = repo_root if q in imported_saved_q_indices else artifact_root
        data = _task41_npy_artifact(evidence_root, records["data"], f"q{q} CSR data")
        indices = _task41_npy_artifact(evidence_root, records["indices"], f"q{q} CSR indices")
        indptr = _task41_npy_artifact(evidence_root, records["indptr"], f"q{q} CSR indptr")
        if (
            data.dtype != np.dtype(np.complex128)
            or indices.dtype != np.dtype(np.int32)
            or indptr.dtype != np.dtype(np.int32)
            or len(manifest["shape"]) != 2
        ):
            raise ValueError(f"Task41 A2 q={q} CSR dtype or shape is invalid")
        matrix = sparse.csr_matrix(
            (data, indices, indptr), shape=tuple(manifest["shape"]), copy=False
        )
        if (
            matrix.shape[0] != matrix.shape[1]
            or matrix.nnz != manifest.get("stored_structural_slots")
            or not matrix.has_canonical_format
            or not matrix.has_sorted_indices
            or not np.isfinite(matrix.data).all()
        ):
            raise ValueError(f"Task41 A2 q={q} saved CSR is not finite canonical CSR")
        return matrix

    def load_factor_packet(
        packet_ref: Any, *, q: int, label: str, expected_rhs: np.ndarray,
        matrix: Any, recorded_relative: Any,
    ) -> float:
        if not isinstance(packet_ref, Mapping):
            raise ValueError(f"Task41 A2 q={q} {label} factor packet reference is missing")
        packet_path = _task41_run_artifact(artifact_root, packet_ref, f"q{q} {label} factor packet")
        if (
            packet_ref.get("array_names") != ["residual", "rhs", "solution"]
            or packet_ref.get("dtype") != np.dtype(np.complex128).str
            or packet_ref.get("rows") != matrix.shape[0]
            or packet_ref.get("readback_verified") is not True
        ):
            raise ValueError(f"Task41 A2 q={q} {label} factor packet metadata is invalid")
        with np.load(packet_path, allow_pickle=False) as packet:
            if set(packet.files) != {"rhs", "solution", "residual"}:
                raise ValueError(f"Task41 A2 q={q} {label} factor packet array inventory changed")
            values = {name: np.array(packet[name], copy=True) for name in packet.files}
        expected_hashes = packet_ref.get("array_sha256")
        if not isinstance(expected_hashes, Mapping) or set(expected_hashes) != set(values):
            raise ValueError(f"Task41 A2 q={q} {label} factor packet hashes are incomplete")
        for name, value in values.items():
            if (
                value.dtype != np.dtype(np.complex128)
                or value.shape != expected_rhs.shape
                or not np.isfinite(value).all()
                or hashlib.sha256(
                    value.dtype.str.encode("ascii")
                    + np.asarray(value.shape, dtype=np.int64).tobytes()
                    + np.ascontiguousarray(value).view(np.uint8).tobytes()
                ).hexdigest() != expected_hashes.get(name)
            ):
                raise ValueError(f"Task41 A2 q={q} {label} factor packet {name} changed")
        if not np.array_equal(values["rhs"], expected_rhs):
            raise ValueError(f"Task41 A2 q={q} {label} RHS differs from the frozen formula")
        recomputed = np.asarray(matrix @ values["solution"], dtype=np.complex128)
        recomputed -= values["rhs"]
        if _task41_relative_vector_error(recomputed, values["residual"]) > 1.0e-13:
            raise ValueError(f"Task41 A2 q={q} {label} saved factor residual vector changed")
        relative = float(np.linalg.norm(recomputed) / np.linalg.norm(values["rhs"]))
        if not np.isclose(relative, float(recorded_relative), rtol=1.0e-10, atol=1.0e-15):
            raise ValueError(f"Task41 A2 q={q} {label} factor residual scalar does not recompute")
        if not np.isfinite(relative) or relative > 1.0e-10:
            raise ValueError(f"Task41 A2 q={q} {label} factor residual exceeds 1e-10")
        return relative

    factor_results = []
    csr_results = []
    required_actions = ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")
    for twist in range(profile.replication_count):
        pair = (twist, twist + profile.replication_count)
        matrices = {q: load_csr(q) for q in pair}
        for q in pair:
            matrix = matrices[q]
            manifest, qualification, array_records = sector_by_q[q]
            expected_columns = (
                profile.trace_rows_per_q
                + profile.q_port_counts[q]
            )
            if matrix.shape != (expected_columns, expected_columns):
                raise ValueError(f"Task41 A2 q={q} CSR dimensions differ from the frozen profile")
            matrix_identity = _task41_sparse_identity(matrix)
            factor_input = factor_inputs[q]
            q_audit = q_matrix_audits.get(str(q), q_matrix_audits.get(q))
            if (
                not isinstance(q_audit, Mapping)
                or q_audit.get("shape") != list(matrix.shape)
                or q_audit.get("nnz") != matrix.nnz
                or factor_input.get("shape") != list(matrix.shape)
                or factor_input.get("nnz") != matrix.nnz
                or factor_input.get("caller_input_sha256_before") != matrix_identity
                or factor_input.get("caller_input_sha256_after") != matrix_identity
                or factor_input.get("factor_csr_sha256_before") != matrix_identity
                or factor_input.get("factor_csr_sha256_after") != matrix_identity
                or factor_input.get("input_identity_unchanged") is not True
            ):
                raise ValueError(f"Task41 A2 q={q} factor input does not match the saved CSR")

            n = matrix.shape[0]
            index = np.arange(n, dtype=np.int64)
            fresh_rhs = np.cos(0.23 * index) + 1j * np.sin(0.37 * index)
            first = factor_tests[q]
            fresh = first.get("fresh_rhs")
            second = second_tests[q]
            nested_second = first.get("second_rhs")
            second_rhs = np.empty(n, dtype=np.complex128)
            second_rhs.real[:] = 2.0 + (index % 17) / 17.0
            second_rhs.imag[:] = 1.5 + (index % 13) / 13.0
            if (
                first.get("rows") != n
                or first.get("strict_passed") is not True
                or first.get("strict_limit") != 1.0e-10
                or not isinstance(fresh, Mapping)
                or fresh.get("formula") != "cos(0.23*i) + 1j*sin(0.37*i)"
                or fresh.get("constructed_directly_not_from_csr_times_x") is not True
                or second.get("schema") != f"task41.p0.{case_id.lower()}_all_q_second_rhs_result.v1"
                or second.get("formula") != second_contract.get("formula")
                or second.get("strict_passed") is not True
                or second.get("strict_limit") != 1.0e-10
                or not isinstance(nested_second, Mapping)
                or nested_second.get("packet") != second.get("packet")
            ):
                raise ValueError(f"Task41 A2 q={q} strict factor qualification row is invalid")
            fresh_relative = load_factor_packet(
                fresh.get("packet"), q=q, label="fresh probe", expected_rhs=fresh_rhs,
                matrix=matrix, recorded_relative=first.get("relative_true_residual"),
            )
            second_relative = load_factor_packet(
                second.get("packet"), q=q, label="second RHS", expected_rhs=second_rhs,
                matrix=matrix,
                recorded_relative=second.get("relative_full_csr_true_residual"),
            )
            if (
                not np.isclose(fresh_relative, float(first.get("relative_true_residual")), rtol=1.0e-10, atol=1.0e-15)
                or not np.isclose(second_relative, float(second.get("relative_full_csr_true_residual")), rtol=1.0e-10, atol=1.0e-15)
            ):
                raise ValueError(f"Task41 A2 q={q} factor residuals differ from the audit")
            factor_results.append(
                {"q": q, "fresh_probe_relative_residual": fresh_relative,
                 "second_rhs_relative_residual": second_relative,
                 "factor_csr_identity": matrix_identity}
            )

            evidence_root = repo_root if q in imported_saved_q_indices else artifact_root
            native_records = {
                name: _task41_npy_artifact(
                    evidence_root, array_records[name], f"q{q} {name}"
                )
                for name in array_records
            }
            inputs = {name: native_records[f"input_{name}"] for name in required_actions}
            outputs = {name: native_records[f"csr_{name}"] for name in required_actions}
            native_outputs = {name: native_records[f"native_{name}"] for name in required_actions}
            trace_rows = profile.trace_rows_per_q
            first_input = inputs["case1_full"]
            if (
                any(value.dtype != np.dtype(np.complex128) or not np.isfinite(value).all() for value in inputs.values())
                or np.any(first_input == 0.0)
                or np.any(inputs["case2_full"] == 0.0)
                or np.array_equal(first_input, inputs["case2_full"])
                or not np.array_equal(inputs["case1_trace_only"][:trace_rows], first_input[:trace_rows])
                or np.any(inputs["case1_trace_only"][trace_rows:] != 0.0)
                or np.any(inputs["case1_port_only"][:trace_rows] != 0.0)
                or not np.array_equal(inputs["case1_port_only"][trace_rows:], first_input[trace_rows:])
            ):
                raise ValueError(f"Task41 A2 q={q} saved four-action input split is invalid")
            action_errors: dict[str, float] = {}
            for name in required_actions:
                computed = np.asarray(matrix @ inputs[name], dtype=np.complex128)
                saved_csr_error = _task41_relative_vector_error(computed, outputs[name])
                native_error = _task41_relative_vector_error(computed, native_outputs[name])
                if max(saved_csr_error, native_error) > 1.0e-11:
                    raise ValueError(f"Task41 A2 q={q} {name} CSR/native action exceeds 1e-11")
                action_errors[name] = native_error
            components = sum(
                (np.asarray(native_records[f"component_case1_{name}"]) for name in ("volume", "minus_D", "C", "Hhat")),
                np.zeros(matrix.shape[0], dtype=np.complex128),
            )
            component_error = _task41_relative_vector_error(components, native_outputs["case1_full"])
            split_error = _task41_relative_vector_error(
                native_outputs["case1_trace_only"] + native_outputs["case1_port_only"],
                native_outputs["case1_full"],
            )
            peer = pair[1] if q == pair[0] else pair[0]
            peer_input = native_records["paired_peer_input"]
            peer_diagonal = native_records["paired_peer_native_diagonal"]
            peer_matrix_action = np.asarray(matrices[peer] @ peer_input, dtype=np.complex128)
            peer_csr_error = _task41_relative_vector_error(peer_matrix_action, peer_diagonal)
            leakage = qualification.get("paired_sector_leakage", {})
            q_to_peer = native_records["paired_selected_native_cross"]
            peer_to_q = native_records["paired_peer_native_cross"]
            q_to_peer_relative = float(
                np.linalg.norm(q_to_peer)
                / max(float(np.linalg.norm(native_outputs["case1_full"])), np.finfo(float).tiny)
            )
            peer_to_q_relative = float(
                np.linalg.norm(peer_to_q)
                / max(float(np.linalg.norm(peer_diagonal)), np.finfo(float).tiny)
            )
            reported_errors = qualification.get("relative_errors", {})
            if (
                component_error > 1.0e-11
                or split_error > 1.0e-11
                or peer_csr_error > 1.0e-11
                or not isinstance(leakage, Mapping)
                or not np.isclose(float(leakage.get("q_to_peer", {}).get("relative", np.nan)), q_to_peer_relative, rtol=1.0e-10, atol=1.0e-15)
                or not np.isclose(float(leakage.get("peer_to_q", {}).get("relative", np.nan)), peer_to_q_relative, rtol=1.0e-10, atol=1.0e-15)
                or max(q_to_peer_relative, peer_to_q_relative) > 1.0e-11
                or float(leakage.get("peer_to_q", {}).get("peer_csr_native_relative", np.inf)) > 1.0e-11
                or not isinstance(reported_errors, Mapping)
                or set(reported_errors) != set(required_actions)
                or any(not np.isclose(float(reported_errors[name]), action_errors[name], rtol=1.0e-10, atol=1.0e-15) for name in required_actions)
                or not np.isclose(float(qualification.get("maximum_relative_error", np.nan)), max(action_errors.values()), rtol=1.0e-10, atol=1.0e-15)
            ):
                raise ValueError(f"Task41 A2 q={q} sector action, component, or leakage audit failed")
            csr_results.append(
                {"q": q, "peer_q": peer, "four_action_relative_errors": action_errors,
                 "component_reassembly_relative": component_error,
                 "trace_port_reassembly_relative": split_error,
                 "paired_peer_csr_relative_error": peer_csr_error,
                 "q_to_peer_relative": q_to_peer_relative,
                 "peer_to_q_relative": peer_to_q_relative}
            )
    return {
        "all_q_factor_probes_reapplied": True,
        "factor_operator_reapplied_from_hash_bound_q_csr": True,
        "factor_probe_count": len(factor_results),
        "factor_results": factor_results,
        "all_q_four_action_csr_reapplied": True,
        "saved_native_qualification_q_indices": sorted(imported_saved_q_indices),
        "fresh_native_qualification_q_indices": sorted(set(q_indices) - imported_saved_q_indices),
        "sector_count": len(actual_sector_pairs),
        "q_csr_action_count": sum(len(row["four_action_relative_errors"]) for row in csr_results),
        "paired_peer_csr_action_count": len(csr_results),
        "csr_results": csr_results,
        "relative_error_limit": 1.0e-11,
    }



def _task41_a2_reference_audit_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Backward-compatible A2 entry point for the shared iterative audit."""
    return _task41_iterative_reference_audit_checks(
        summary, numerical_output, repo_root=repo_root, case_id="A2"
    )


def _task41_a2_numerical_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    contract: Mapping[str, Any],
    *,
    repo_root: Path,
    reference_audit_source: tuple[Mapping[str, Any], Path] | None = None,
) -> dict[str, Any]:
    """Independently reopen A2 output, A1 evidence, mode and metric packets."""
    errors: list[str] = []
    case = contract["case"]
    authority = summary.get("campaign_authority")
    comparison = summary.get("task41_a1_a2_comparison")
    if not isinstance(authority, Mapping) or not isinstance(comparison, Mapping):
        raise ValueError("Task41 A2 worker summary omits contract authority or A1/A2 comparison")
    if (
        case.get("run_id") != TASK41_G13_A2_RUN_ID
        or case.get("method") != "full3d_iterative"
        or summary.get("run_id") != TASK41_G13_A2_RUN_ID
        or summary.get("profile") != TASK41_G13_A2_PRECONDITIONER
        or summary.get("stage") != "TASK41_A2"
        or summary.get("status") != "PASS"
        or summary.get("official_result") is not True
        or summary.get("numeric_gates_passed") is not True
        or summary.get("output_gates_passed") is not True
        or authority.get("task41_contract_sha256")
        != hashlib.sha256(
            Path(str(authority.get("task41_contract_path", ""))).read_bytes()
        ).hexdigest()
    ):
        errors.append("A2 worker result or frozen Task41 contract identity did not pass")
    if comparison.get("schema") != TASK41_COMPARISON_SCHEMA or comparison.get("pass") is not True:
        errors.append("A1/A2 comparison gate did not pass")
    if (
        authority.get("source_sha") != contract.get("source", {}).get("sha")
        or authority.get("campaign_window_sha256") != contract.get("window", {}).get("sha256")
        or authority.get("q_csr_reuse") != contract.get("q_csr_reuse")
    ):
        errors.append("A2 worker authority differs from its source/window-bound q reuse contract")
    audit_summary, audit_output = (
        reference_audit_source
        if reference_audit_source is not None
        else (summary, numerical_output)
    )
    reference_audit_recheck = _task41_a2_reference_audit_checks(
        audit_summary, audit_output, repo_root=repo_root
    )
    expected_binding_path = (repo_root / TASK41_A1_COMPARISON_BINDING_RELATIVE).resolve()
    binding_path = Path(str(comparison.get("a1_binding_path", ""))).resolve()
    binding_sha = str(contract.get("comparison", {}).get("a1_binding_sha256", ""))
    if (
        binding_path != expected_binding_path
        or comparison.get("a1_binding_sha256") != binding_sha
        or authority.get("a1_comparison_binding_sha256") != binding_sha
    ):
        raise ValueError("Task41 A2 comparison uses a different A1 evidence binding")
    binding, actual_binding_sha = require_task41_a1_comparison_binding(
        binding_path,
        expected_sha256=binding_sha,
        current_root=repo_root,
    )
    if comparison.get("a1_run_id") != binding["a1"]["run_id"]:
        raise ValueError("Task41 A2 comparison run identity differs from its bound A1 record")

    output_packet_meta = summary.get("output_packet")
    if not isinstance(output_packet_meta, Mapping) or not isinstance(output_packet_meta.get("arrays"), Mapping):
        raise ValueError("Task41 A2 summary omits its official output packet")
    output_packet_npz = Path(str(output_packet_meta["arrays"].get("path", ""))).resolve(strict=True)
    output_packet_path = output_packet_npz.with_suffix(".json")
    if output_packet_path.parent != numerical_output.parent.resolve():
        raise ValueError("Task41 A2 official output packet escaped its run directory")
    output_packet = _json_object(output_packet_path, "A2 official output packet")
    from src.runners.task40_v10_output_checker import (
        _verify_v31_reference_tiers,
        verify_v10_output_bundle,
    )

    output_recheck = verify_v10_output_bundle(
        output_packet_path, expected_channel_count=168
    )
    if output_recheck.get("status") != "PASS":
        errors.append("A2 full-field/output packet checker did not pass")
    diagnostic_recheck: dict[str, Any]
    try:
        from src.io.input_validation import simulation_config_3d_from_normalized

        resolved_config_path = audit_output.parent / "resolved_config.json"
        if (
            not resolved_config_path.is_file()
            or hashlib.sha256(resolved_config_path.read_bytes()).hexdigest()
            != contract["case"]["resolved_config_sha256"]
        ):
            raise ValueError("producer resolved configuration hash differs from the contract")
        resolved_config = _json_object(resolved_config_path, "Task41 frozen resolved configuration")
        reporting_cfg = simulation_config_3d_from_normalized(resolved_config)
        diagnostic_doc = _json_object(
            numerical_output / "diffraction_orders_3d.json",
            "A2 diagnostic diffraction output",
        )
        diagnostic_metrics = diagnostic_doc.get("metrics")
        diagnostic_recheck = (
            _task41_a2_diagnostic_inventory_from_data(
                diagnostic_metrics,
                diagnostic_doc.get("orders"),
                expected_m_max=reporting_cfg.reporting_diffraction_order_max_m,
                expected_n_max=reporting_cfg.reporting_diffraction_order_max_n,
            )
            if isinstance(diagnostic_metrics, Mapping)
            else {"passed": False, "error": "diagnostic metrics object is missing"}
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        diagnostic_recheck = {"passed": False, "error": str(exc)}
    if diagnostic_recheck.get("passed") is not True:
        errors.append("A2 diagnostic diffraction rows do not match the frozen reporting grid")
    reference_tiers = _verify_v31_reference_tiers(
        summary.get("regular_inverse_checks", {}),
        expected_profile=TASK41_G13_A2_PRECONDITIONER,
    )
    if reference_tiers.get("case_count") != 6 or reference_tiers.get("passed") is not True:
        errors.append("A2 six startup reference cases did not independently pass")

    a1_modal = _task41_artifact_path(repo_root, binding, "modal_amplitudes")
    a1_orders = _task41_artifact_path(repo_root, binding, "diffraction_orders")
    a2_modal = (numerical_output / "dtn_port_modal_amplitudes_3d.npz").resolve(strict=True)
    a2_orders = (numerical_output / "dtn_port_diffraction_orders_3d.json").resolve(strict=True)
    modal_comparison = compare_task41_modal_artifacts(a1_modal, a2_modal, a1_orders, a2_orders)
    if modal_comparison.get("mode_count") != 168 or modal_comparison.get("pass") is not True:
        errors.append("A1/A2 physical-boundary modal amplitude or per-mode power comparison failed")
    a1_port = json.loads(_task41_artifact_path(repo_root, binding, "port_power_metrics").read_text(encoding="utf-8"))
    a1_volume = json.loads(_task41_artifact_path(repo_root, binding, "volume_absorption").read_text(encoding="utf-8"))
    power_comparison = compare_task41_power_totals(a1_port, a1_volume, output_packet.get("output", {}))
    if power_comparison.get("pass") is not True:
        errors.append("A1/A2 R/T/A/A_volume total comparison failed")

    a1_airbox = _task41_artifact_path(repo_root, binding, "airbox_fields")
    a2_airbox = numerical_output / "airbox_fields_3d_scientific.npz"
    mesh_checks = []
    mesh_keys = ("coordinates_nm", "vtk_cells", "vtk_cell_types", "cell_domain_tags")
    with np.load(a1_airbox, allow_pickle=False) as reference_mesh, np.load(
        a2_airbox, allow_pickle=False
    ) as candidate_mesh:
        for key in mesh_keys:
            equal = key in reference_mesh.files and key in candidate_mesh.files and np.array_equal(
                reference_mesh[key], candidate_mesh[key]
            )
            mesh_checks.append({"array": key, "equal": bool(equal)})
            if not equal:
                errors.append(f"A1/A2 mesh or material array differs: {key}")

    sample_archive = _task41_artifact_path(repo_root, binding, "full3d_samples_archive")
    sample_metadata_path = _task41_artifact_path(repo_root, binding, "full3d_samples_metadata")
    sample_metadata = _json_object(sample_metadata_path, "A1 saved-field sample metadata")
    if sample_metadata.get("archive_sha256") != sha256_file(sample_archive):
        errors.append("A1 saved-field sample metadata does not bind its NPZ")
    sample_witness = comparison.get("sample_representation_witness", {})
    if (
        sample_witness.get("pass") is not True
        or float(sample_witness.get("electric_relative_l2", float("inf"))) > TASK41_MODE_RELATIVE_LIMIT
        or float(sample_witness.get("magnetic_relative_l2_from_direct_fe_curl", float("inf")))
        > TASK41_MODE_RELATIVE_LIMIT
    ):
        errors.append("A1 recovered-field representation witness failed")

    full_solution = _load_task41_a2_full_solution(output_packet)
    a1_full_solution = _task41_npz_array(
        _task41_artifact_path(repo_root, binding, "full_solution"), "recovered_field"
    ).astype(np.complex128, copy=False)
    metric_meta = comparison.get("metric_packet")
    if not isinstance(metric_meta, Mapping) or not isinstance(metric_meta.get("arrays"), Mapping):
        raise ValueError("Task41 A2 comparison omits its full-volume metric packet")
    metric_json = Path(str(metric_meta["arrays"].get("path", ""))).resolve(strict=True).with_suffix(".json")
    if metric_json.parent != numerical_output.parent.resolve():
        raise ValueError("Task41 A1/A2 metric packet escaped its run directory")
    field_comparison = evaluate_task41_metric_packet(
        metric_json,
        reference_full_field=a1_full_solution,
        candidate_full_field=full_solution,
        expected_binding_sha256=actual_binding_sha,
    )
    stored_metric = comparison.get("full_volume_metric", {})
    for key in ("electric_relative_l2", "scaled_curl_relative_l2"):
        if not np.isclose(
            float(stored_metric.get(key, np.nan)),
            float(field_comparison[key]),
            rtol=1.0e-11,
            atol=1.0e-13,
        ):
            errors.append(f"A1/A2 stored full-volume {key} differs from the checker recomputation")
    if field_comparison.get("pass") is not True:
        errors.append("A1/A2 full-volume E/scaled-curl metric exceeds its limit")

    return {
        "errors": errors,
        "output_packet_recheck": output_recheck,
        "diagnostic_diffraction_inventory_recheck": diagnostic_recheck,
        "reference_tiers": reference_tiers,
        "modal_comparison": modal_comparison,
        "power_comparison": power_comparison,
        "mesh_array_checks": mesh_checks,
        "sample_representation_witness": sample_witness,
        "full_volume_metric_recheck": field_comparison,
        "reference_audit_recheck": reference_audit_recheck,
        "a1_binding_sha256": actual_binding_sha,
    }


def _task41_b0_chunked_norm(values: np.ndarray, *, chunk_rows: int = 262_144) -> float:
    total = 0.0
    for start in range(0, int(values.shape[0]), chunk_rows):
        block = np.asarray(values[start : start + chunk_rows], dtype=np.complex128)
        if not np.isfinite(block).all():
            raise ValueError("Task41 B0 norm input contains non-finite values")
        total += float(np.vdot(block, block).real)
    return float(np.sqrt(max(0.0, total)))


def _task41_b0_chunked_difference_summary(
    left: np.ndarray,
    right: np.ndarray,
    *,
    start: int = 0,
    stop: int | None = None,
    chunk_rows: int = 262_144,
) -> dict[str, float]:
    """Summarize a saved vector difference without materializing the whole delta."""
    end = int(left.shape[0]) if stop is None else stop
    if (
        left.ndim != 1
        or right.ndim != 1
        or left.shape != right.shape
        or type(start) is not int
        or type(end) is not int
        or start < 0
        or end < start
        or end > int(left.shape[0])
        or type(chunk_rows) is not int
        or chunk_rows < 1
    ):
        raise ValueError("Task41 B0 partitioned difference has an invalid vector range")
    squared_norm = 0.0
    maximum_row = 0.0
    maximum_row_index: int | None = None
    for offset in range(start, end, chunk_rows):
        block_end = min(end, offset + chunk_rows)
        lhs = np.asarray(left[offset:block_end], dtype=np.complex128)
        rhs = np.asarray(right[offset:block_end], dtype=np.complex128)
        if not np.isfinite(lhs).all() or not np.isfinite(rhs).all():
            raise ValueError("Task41 B0 partitioned difference contains non-finite values")
        difference = lhs - rhs
        squared_norm += float(np.vdot(difference, difference).real)
        if difference.size:
            magnitudes = np.abs(difference)
            local_index = int(np.argmax(magnitudes))
            local_maximum = float(magnitudes[local_index])
            if maximum_row_index is None or local_maximum > maximum_row:
                maximum_row = local_maximum
                maximum_row_index = offset + local_index
    return {
        "absolute_l2": float(np.sqrt(max(0.0, squared_norm))),
        "sum_squares": max(0.0, squared_norm),
        "max_abs_row": maximum_row,
        "max_abs_row_index": maximum_row_index,
    }


def _task41_b0_v7_map_original_rows_to_active(
    original_rows: np.ndarray, active_original_rows: np.ndarray
) -> np.ndarray:
    """Map sparse original B-alpha rows to active ids without another MPC map."""
    rows = np.asarray(original_rows, dtype=np.int64)
    active = np.asarray(active_original_rows, dtype=np.int64)
    if rows.ndim != 1 or active.ndim != 1 or np.unique(active).size != active.size:
        raise ValueError("Task41 V7 original/active row maps are malformed")
    if rows.size and not active.size:
        raise ValueError("Task41 V7 B-alpha cannot map to an empty active trace")
    order = np.argsort(active, kind="stable")
    sorted_active = active[order]
    positions = np.searchsorted(sorted_active, rows)
    if positions.size and (
        np.any(positions >= sorted_active.size)
        or np.any(sorted_active[np.minimum(positions, sorted_active.size - 1)] != rows)
    ):
        raise ValueError("Task41 V7 B-alpha row is not an independent active row")
    return order[positions]


def _task41_b0_v7_metric_state() -> dict[str, Any]:
    return {"sum_squares": 0.0, "max_abs": 0.0, "max_row": None}


def _task41_b0_v7_add_metric(
    state: dict[str, Any],
    values: np.ndarray,
    *,
    row_offset: int,
    row_indices: np.ndarray | None = None,
) -> None:
    vector = np.asarray(values, dtype=np.complex128).reshape(-1)
    if not np.isfinite(vector).all():
        raise ValueError("Task41 V7 diagnostic vector contains non-finite values")
    state["sum_squares"] += float(np.vdot(vector, vector).real)
    if vector.size:
        magnitudes = np.abs(vector)
        local_index = int(np.argmax(magnitudes))
        local_max = float(magnitudes[local_index])
        if state["max_row"] is None or local_max > float(state["max_abs"]):
            state["max_abs"] = local_max
            state["max_row"] = (
                int(np.asarray(row_indices, dtype=np.int64)[local_index])
                if row_indices is not None
                else row_offset + local_index
            )


def _task41_b0_v7_finish_metric(state: Mapping[str, Any]) -> dict[str, Any]:
    sum_squares = max(0.0, float(state["sum_squares"]))
    return {
        "absolute_l2": float(np.sqrt(sum_squares)),
        "sum_squares": sum_squares,
        "max_abs": float(state["max_abs"]),
        "max_row": state["max_row"],
    }


def _task41_b0_v7_rhs_split_metrics(
    native_rhs: np.ndarray,
    native_volume_rhs: np.ndarray,
    b_alpha_rows: np.ndarray,
    b_alpha_values: np.ndarray,
    *,
    chunk_rows: int = 262_144,
) -> dict[str, Any]:
    if (
        native_rhs.ndim != 1
        or native_volume_rhs.shape != native_rhs.shape
        or b_alpha_rows.ndim != 1
        or b_alpha_values.shape != b_alpha_rows.shape
        or b_alpha_rows.dtype.kind not in "iu"
        or b_alpha_values.dtype != np.dtype(np.complex128)
        or (b_alpha_rows.size and np.any(b_alpha_rows >= native_rhs.size))
        or (b_alpha_rows.size and np.any(b_alpha_rows < 0))
    ):
        raise ValueError("Task41 V7 full/volume RHS and B-alpha layouts differ")
    order = np.argsort(b_alpha_rows, kind="stable")
    rows = np.asarray(b_alpha_rows[order], dtype=np.int64)
    values = np.asarray(b_alpha_values[order], dtype=np.complex128)
    metrics = _task41_b0_v7_metric_state()
    for start in range(0, int(native_rhs.size), chunk_rows):
        stop = min(int(native_rhs.size), start + chunk_rows)
        difference = np.asarray(native_rhs[start:stop], dtype=np.complex128) - np.asarray(
            native_volume_rhs[start:stop], dtype=np.complex128
        )
        lo = int(np.searchsorted(rows, start, side="left"))
        hi = int(np.searchsorted(rows, stop, side="left"))
        if hi > lo:
            np.add.at(difference, rows[lo:hi] - start, -values[lo:hi])
        _task41_b0_v7_add_metric(metrics, difference, row_offset=start)
    return _task41_b0_v7_finish_metric(metrics)


def _task41_b0_v7_nonactive_rhs_difference(
    native_rhs: np.ndarray,
    native_volume_rhs: np.ndarray,
    active_original_rows: np.ndarray,
    *,
    chunk_rows: int = 262_144,
) -> dict[str, Any]:
    if native_rhs.ndim != 1 or native_volume_rhs.shape != native_rhs.shape:
        raise ValueError("Task41 V7 nonactive RHS vectors differ in layout")
    active = np.asarray(active_original_rows, dtype=np.int64)
    if active.ndim != 1 or (active.size and (np.any(active < 0) or np.any(active >= native_rhs.size))):
        raise ValueError("Task41 V7 active original-row map is invalid")
    active_mask = np.zeros(native_rhs.size, dtype=np.bool_)
    active_mask[active] = True
    metrics = _task41_b0_v7_metric_state()
    for start in range(0, int(native_rhs.size), chunk_rows):
        stop = min(int(native_rhs.size), start + chunk_rows)
        selected = ~active_mask[start:stop]
        difference = (
            np.asarray(native_rhs[start:stop], dtype=np.complex128)
            - np.asarray(native_volume_rhs[start:stop], dtype=np.complex128)
        )
        row_indices = np.flatnonzero(selected) + start
        _task41_b0_v7_add_metric(
            metrics,
            difference[selected],
            row_offset=start,
            row_indices=row_indices,
        )
    return _task41_b0_v7_finish_metric(metrics)


def _task41_b0_v7_attribution_state_recheck(
    *,
    candidate_d_full: np.ndarray,
    candidate_d_volume: np.ndarray,
    active_original_rows: np.ndarray,
    native_rhs: np.ndarray,
    native_volume_rhs: np.ndarray,
    b_alpha_rows: np.ndarray,
    b_alpha_values: np.ndarray,
    native_volume_action: np.ndarray,
    T_r_i: np.ndarray,
    delta_t: np.ndarray,
    attributed_terms: np.ndarray,
    reduce_r_volume: np.ndarray,
    reduce_r_full: np.ndarray,
    frozen_denominator: float,
    evidence_directory: Path | None = None,
    evidence_prefix: str | None = None,
) -> dict[str, Any]:
    """Independently recompute V7 full/volume formulas from saved arrays."""
    active = np.asarray(active_original_rows, dtype=np.int64)
    active_rows = int(active.size)
    if (
        active.ndim != 1
        or np.unique(active).size != active_rows
        or any(
            np.asarray(value).shape != (active_rows,)
            for value in (
                candidate_d_full,
                candidate_d_volume,
                T_r_i,
                delta_t,
                attributed_terms,
                reduce_r_volume,
                reduce_r_full,
            )
        )
        or native_rhs.ndim != 1
        or native_volume_rhs.shape != native_rhs.shape
        or native_volume_action.shape != native_rhs.shape
        or (active.size and (np.any(active < 0) or np.any(active >= native_rhs.size)))
        or b_alpha_rows.shape != b_alpha_values.shape
        or b_alpha_values.dtype != np.dtype(np.complex128)
    ):
        raise ValueError("Task41 V7 attribution state arrays have incompatible identities/layouts")
    beta_active_ids = _task41_b0_v7_map_original_rows_to_active(
        b_alpha_rows, active
    )
    beta_active = np.zeros(active_rows, dtype=np.complex128)
    np.add.at(beta_active, beta_active_ids, b_alpha_values)
    support_mask = np.zeros(active_rows, dtype=np.bool_)
    support_mask[beta_active_ids] = True
    metrics = {
        key: _task41_b0_v7_metric_state()
        for key in (
            "legacy_closure_minus_beta_active",
            "legacy_closure_vector",
            "legacy_minus_beta_vs_corrected_full",
            "legacy_closure_on_beta_support",
            "legacy_closure_off_beta_support",
            "corrected_full_closure",
            "corrected_volume_closure",
            "reduce_r_volume_vs_raw_trace_plus_T_r_i",
            "d_volume_plus_reduce_r_volume_vs_delta_plus_Q",
            "reduce_r_full_vs_raw_trace_plus_T_r_i",
            "d_full_plus_reduce_r_full_vs_delta_plus_Q",
            "d_hat_full_minus_candidate_d_full",
            "d_hat_volume_minus_saved_d_volume",
            "full_minus_volume_d_plus_rhs_split",
        )
    }
    beta_norm_sq = 0.0
    beta_inner = 0.0 + 0.0j
    term_norm_squares = {
        name: 0.0
        for name in (
            "delta_t",
            "attributed_terms_Q",
            "r_volume_trace",
            "r_full_trace",
            "T_r_i",
            "candidate_d_full",
            "saved_d_volume",
        )
    }
    d_hat_volume = np.empty(active_rows, dtype=np.complex128)
    d_hat_full = np.empty(active_rows, dtype=np.complex128)
    array_outputs: dict[str, Any] = {}
    output_maps: dict[str, np.memmap] = {}
    temporary_paths: dict[str, Path] = {}
    final_paths: dict[str, Path] = {}
    if evidence_directory is not None:
        if not evidence_prefix:
            raise ValueError("Task41 V7 closure arrays require a bound artifact prefix")
        evidence_directory = Path(evidence_directory).resolve()
        if not evidence_directory.is_dir():
            raise FileNotFoundError("Task41 V7 evidence directory was not prepared")
        for field in ("corrected_full_closure", "corrected_volume_closure"):
            name = f"{evidence_prefix}_{field}"
            final_path = evidence_directory / f"{name}.npy"
            temporary_path = evidence_directory / f".{name}.npy.tmp"
            if final_path.exists() or temporary_path.exists():
                raise FileExistsError(f"Task41 V7 closure artifact already exists: {name}")
            output_maps[field] = np.lib.format.open_memmap(
                temporary_path,
                mode="w+",
                dtype=np.complex128,
                shape=(active_rows,),
            )
            temporary_paths[field] = temporary_path
            final_paths[field] = final_path
    for start in range(0, active_rows, 262_144):
        stop = min(active_rows, start + 262_144)
        original = active[start:stop]
        d_full = np.asarray(candidate_d_full[start:stop], dtype=np.complex128)
        d_volume = np.asarray(candidate_d_volume[start:stop], dtype=np.complex128)
        f_t = np.asarray(native_rhs[original], dtype=np.complex128)
        b_t = np.asarray(native_volume_rhs[original], dtype=np.complex128)
        n_t = np.asarray(native_volume_action[original], dtype=np.complex128)
        beta = beta_active[start:stop]
        u = np.asarray(T_r_i[start:stop], dtype=np.complex128)
        delta = np.asarray(delta_t[start:stop], dtype=np.complex128)
        q = np.asarray(attributed_terms[start:stop], dtype=np.complex128)
        volume_reduce = np.asarray(reduce_r_volume[start:stop], dtype=np.complex128)
        full_reduce = np.asarray(reduce_r_full[start:stop], dtype=np.complex128)
        right = delta + q
        r_volume = b_t - n_t
        r_full = f_t - n_t - beta
        legacy = d_full + (f_t - n_t) + u - right
        legacy_minus_beta = legacy - beta
        corrected_full = d_full + r_full + u - right
        corrected_volume = d_volume + r_volume + u - right
        expected_volume_reduce = r_volume + u
        expected_full_reduce = r_full + u
        d_volume_plus_reduce = d_volume + volume_reduce - right
        d_full_plus_reduce = d_full + full_reduce - right
        hat_volume = right - r_volume - u
        hat_full = right - r_full - u
        rhs_split_active = f_t - b_t - beta
        split = (d_full - d_volume) + rhs_split_active
        d_hat_volume[start:stop] = hat_volume
        d_hat_full[start:stop] = hat_full
        if output_maps:
            output_maps["corrected_full_closure"][start:stop] = corrected_full
            output_maps["corrected_volume_closure"][start:stop] = corrected_volume
        chunk_vectors = {
            "legacy_closure_minus_beta_active": legacy_minus_beta,
            "legacy_closure_vector": legacy,
            "legacy_minus_beta_vs_corrected_full": corrected_full - legacy_minus_beta,
            "legacy_closure_on_beta_support": legacy[support_mask[start:stop]],
            "legacy_closure_off_beta_support": legacy[~support_mask[start:stop]],
            "corrected_full_closure": corrected_full,
            "corrected_volume_closure": corrected_volume,
            "reduce_r_volume_vs_raw_trace_plus_T_r_i": volume_reduce - expected_volume_reduce,
            "d_volume_plus_reduce_r_volume_vs_delta_plus_Q": d_volume_plus_reduce,
            "reduce_r_full_vs_raw_trace_plus_T_r_i": full_reduce - expected_full_reduce,
            "d_full_plus_reduce_r_full_vs_delta_plus_Q": d_full_plus_reduce,
            "d_hat_full_minus_candidate_d_full": hat_full - d_full,
            "d_hat_volume_minus_saved_d_volume": hat_volume - d_volume,
            "full_minus_volume_d_plus_rhs_split": split,
        }
        for key, values in chunk_vectors.items():
            if key == "legacy_closure_on_beta_support":
                selected = np.flatnonzero(support_mask[start:stop]) + start
                _task41_b0_v7_add_metric(
                    metrics[key], values, row_offset=start, row_indices=selected
                )
            elif key == "legacy_closure_off_beta_support":
                selected = np.flatnonzero(~support_mask[start:stop]) + start
                _task41_b0_v7_add_metric(
                    metrics[key], values, row_offset=start, row_indices=selected
                )
            else:
                _task41_b0_v7_add_metric(metrics[key], values, row_offset=start)
        beta_norm_sq += float(np.vdot(beta, beta).real)
        beta_inner += complex(np.vdot(beta, legacy))
        for name, term in (
            ("delta_t", delta),
            ("attributed_terms_Q", q),
            ("r_volume_trace", r_volume),
            ("r_full_trace", r_full),
            ("T_r_i", u),
            ("candidate_d_full", d_full),
            ("saved_d_volume", d_volume),
        ):
            term_norm_squares[name] += float(np.vdot(term, term).real)
    if output_maps:
        for value in output_maps.values():
            value.flush()
        output_maps.clear()
        import os

        for field, temporary_path in temporary_paths.items():
            final_path = final_paths[field]
            os.replace(temporary_path, final_path)
            array_outputs[field] = {
                "name": final_path.stem,
                "path": str(final_path),
                "sha256": sha256_file(final_path),
                "bytes": final_path.stat().st_size,
                "shape": [active_rows],
                "dtype": "complex128",
            }
    diagnostics = {key: _task41_b0_v7_finish_metric(value) for key, value in metrics.items()}
    term_scales = {
        name: {
            "absolute_l2": float(np.sqrt(max(0.0, square_sum))),
            "frozen_denominator": float(frozen_denominator),
            "frozen_denominator_relative": float(np.sqrt(max(0.0, square_sum)))
            / frozen_denominator,
        }
        for name, square_sum in term_norm_squares.items()
    }
    d_volume_norm = term_scales["saved_d_volume"]["absolute_l2"]
    d_full_norm = term_scales["candidate_d_full"]["absolute_l2"]
    diagnostics.update(
        {
            "corrected_full_closure_frozen_denominator_relative": diagnostics[
                "corrected_full_closure"
            ]["absolute_l2"]
            / frozen_denominator,
            "corrected_volume_closure_frozen_denominator_relative": diagnostics[
                "corrected_volume_closure"
            ]["absolute_l2"]
            / frozen_denominator,
            "corrected_full_closure_relative_to_d_full": diagnostics[
                "corrected_full_closure"
            ]["absolute_l2"]
            / max(d_full_norm, np.finfo(float).tiny),
            "corrected_volume_closure_relative_to_d_volume": diagnostics[
                "corrected_volume_closure"
            ]["absolute_l2"]
            / max(d_volume_norm, np.finfo(float).tiny),
            "term_scales": term_scales,
        }
    )
    return {
        "diagnostics": diagnostics,
        "legacy_closure_beta_active_l2": float(np.sqrt(max(0.0, beta_norm_sq))),
        "legacy_beta_conjugate_inner_product": {
            "real": float(beta_inner.real),
            "imag": float(beta_inner.imag),
        },
        "epsilon_rhs_native_minus_volume_minus_Balpha": _task41_b0_v7_rhs_split_metrics(
            native_rhs,
            native_volume_rhs,
            np.asarray(b_alpha_rows, dtype=np.int64),
            b_alpha_values,
        ),
        "_d_hat_volume": d_hat_volume,
        "_d_hat_full": d_hat_full,
        "persisted_closure_arrays": array_outputs,
    }


def _task41_b0_chunked_relative_error(
    actual: np.ndarray, expected: np.ndarray, *, chunk_rows: int = 262_144
) -> float:
    if actual.shape != expected.shape:
        raise ValueError("Task41 B0 recovery arrays differ in shape")
    error_squared = 0.0
    expected_squared = 0.0
    for start in range(0, int(actual.shape[0]), chunk_rows):
        stop = min(int(actual.shape[0]), start + chunk_rows)
        left = np.asarray(actual[start:stop], dtype=np.complex128)
        right = np.asarray(expected[start:stop], dtype=np.complex128)
        if not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError("Task41 B0 recovery array contains non-finite values")
        difference = left - right
        error_squared += float(np.vdot(difference, difference).real)
        expected_squared += float(np.vdot(right, right).real)
    return float(
        np.sqrt(max(0.0, error_squared))
        / max(float(np.sqrt(max(0.0, expected_squared))), np.finfo(float).tiny)
    )


def _task41_b0_chunked_difference_norm(
    left: np.ndarray, right: np.ndarray, *, chunk_rows: int = 262_144
) -> float:
    if left.shape != right.shape:
        raise ValueError("Task41 B0 residual arrays differ in shape")
    total = 0.0
    for start in range(0, int(left.shape[0]), chunk_rows):
        stop = min(int(left.shape[0]), start + chunk_rows)
        lhs = np.asarray(left[start:stop], dtype=np.complex128)
        rhs = np.asarray(right[start:stop], dtype=np.complex128)
        if not np.isfinite(lhs).all() or not np.isfinite(rhs).all():
            raise ValueError("Task41 B0 residual array contains non-finite values")
        difference = lhs - rhs
        total += float(np.vdot(difference, difference).real)
    return float(np.sqrt(max(0.0, total)))


def _task41_b0_chunked_residual_discrepancy(
    residual: np.ndarray,
    rhs: np.ndarray,
    action: np.ndarray,
    *,
    chunk_rows: int = 262_144,
) -> float:
    if residual.shape != rhs.shape or rhs.shape != action.shape:
        raise ValueError("Task41 B0 native residual vectors differ in shape")
    total = 0.0
    for start in range(0, int(rhs.shape[0]), chunk_rows):
        stop = min(int(rhs.shape[0]), start + chunk_rows)
        r = np.asarray(residual[start:stop], dtype=np.complex128)
        b = np.asarray(rhs[start:stop], dtype=np.complex128)
        a = np.asarray(action[start:stop], dtype=np.complex128)
        if not np.isfinite(r).all() or not np.isfinite(b).all() or not np.isfinite(a).all():
            raise ValueError("Task41 B0 native residual witness contains non-finite values")
        delta = r - (b - a)
        total += float(np.vdot(delta, delta).real)
    return float(np.sqrt(max(0.0, total)))


def _task41_b0_chunked_symmetric_relative_error(
    actual: np.ndarray, expected: np.ndarray, *, chunk_rows: int = 262_144
) -> float:
    if actual.shape != expected.shape:
        raise ValueError("Task41 B0 compared arrays differ in shape")
    error_squared = actual_squared = expected_squared = 0.0
    for start in range(0, int(actual.shape[0]), chunk_rows):
        stop = min(int(actual.shape[0]), start + chunk_rows)
        left = np.asarray(actual[start:stop], dtype=np.complex128)
        right = np.asarray(expected[start:stop], dtype=np.complex128)
        if not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError("Task41 B0 compared arrays contain non-finite values")
        error = left - right
        error_squared += float(np.vdot(error, error).real)
        actual_squared += float(np.vdot(left, left).real)
        expected_squared += float(np.vdot(right, right).real)
    return float(
        np.sqrt(max(0.0, error_squared))
        / max(
            float(np.sqrt(max(0.0, actual_squared))),
            float(np.sqrt(max(0.0, expected_squared))),
            np.finfo(float).tiny,
        )
    )


def _task41_b0_indexed_arrays_equal(
    left: np.ndarray,
    right: np.ndarray,
    rows: np.ndarray,
    *,
    zero: bool = False,
    chunk_rows: int = 262_144,
) -> bool:
    for start in range(0, int(rows.shape[0]), chunk_rows):
        selected = np.asarray(rows[start : start + chunk_rows], dtype=np.int64)
        left_values = np.asarray(left[selected])
        if zero:
            if np.any(left_values != 0.0):
                return False
        elif not np.array_equal(left_values, np.asarray(right[selected])):
            return False
    return True


def _task41_b0_recovery_evidence_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    contract: Mapping[str, Any],
    *,
    contract_sha256: str,
    expected_mode_indices: tuple[int, int] = (16030, 48090),
    checkpoint_path: Path | None = None,
    checkpoint_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute B0 recovery and joint-action gates from hash-bound raw arrays."""
    errors: list[str] = []
    integrity_errors: list[str] = []
    recovery_errors: list[str] = []
    joint_action_errors: list[str] = []
    manifest_loaded = False
    manifest_identity_binding_valid = False
    joint_action_completed = False
    joint_action_passed: bool | None = None
    joint_action_metrics: list[dict[str, Any]] = []
    raw_audit_completed_columns = 0
    checkpoint_events: list[dict[str, Any]] = []

    def save_checkpoint(stage: str, **details: Any) -> None:
        event = {"stage": stage, **details}
        checkpoint_events.append(event)
        if checkpoint_path is None:
            return
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = checkpoint_path.with_name(checkpoint_path.name + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema": "task41.p0.b0.saved_evidence_audit_checkpoint.v1",
                    "status": "IN_PROGRESS",
                    "identity": dict(checkpoint_identity or {}),
                    "events": checkpoint_events,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, checkpoint_path)

    def integrity_error(message: str) -> None:
        errors.append(message)
        integrity_errors.append(message)

    def recovery_error(message: str) -> None:
        errors.append(message)
        recovery_errors.append(message)

    def joint_action_error(message: str) -> None:
        errors.append(message)
        joint_action_errors.append(message)

    binding = summary.get("b0_recovery_evidence")
    if not isinstance(binding, Mapping):
        message = "Task41 B0 summary omits its recovery evidence binding"
        return {
            "schema": "task41.p0.b0.recovery_evidence_checker.v1",
            "audit_completed": False,
            "data_integrity": False,
            "recovery_passed": False,
            "joint_action_passed": None,
            "official_result": False,
            "integrity_errors": [message],
            "recovery_errors": [],
            "joint_action_errors": [],
            "errors": [message],
            "passed": False,
        }
    manifest_ref = binding.get("manifest")
    manifest: Mapping[str, Any] = {}
    if not isinstance(manifest_ref, Mapping):
        integrity_error("Task41 B0 recovery evidence omits its manifest artifact record")
    else:
        try:
            manifest_path = _task41_run_artifact(
                numerical_output.parent, manifest_ref, "B0 recovery manifest"
            )
            manifest = _json_object(manifest_path, "B0 recovery manifest")
            manifest_loaded = True
            manifest_stage = manifest.get("stage")
            manifest_status = manifest.get("status")
            expected_status = (
                "PASS"
                if manifest_stage == "FULL_ACTION_QUALIFIED"
                else "FAIL"
                if manifest_stage
                in {"FULL_ACTION_GATE_FAILED", "RECOVERY_GATE_FAILED"}
                else None
            )
            if (
                manifest_ref.get("stage") != manifest_stage
                or binding.get("stage") != manifest_stage
                or manifest.get("schema") != "task41.p0.b0.recovery_evidence.v1"
                or expected_status is None
                or manifest_status != expected_status
                or binding.get("status") != expected_status
            ):
                integrity_error(
                    "Task41 B0 recovery manifest stage/status binding is invalid"
                )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            integrity_error(
                f"Task41 B0 recovery manifest failed its path/hash check: {exc}"
            )

    case = contract.get("case", {})
    window = contract.get("window", {})
    run_identity = manifest.get("run_identity", {})
    mode_inventory = summary.get("b0_mode_inventory", {})
    expected_identity = {
        "case_id": "B0",
        "run_id": summary.get("run_id"),
        "source_sha": contract.get("source", {}).get("sha")
        if isinstance(contract.get("source"), Mapping)
        else None,
        "input_sha256": case.get("input_sha256") if isinstance(case, Mapping) else None,
        "physical_model_sha256": case.get("physical_model_sha256")
        if isinstance(case, Mapping)
        else None,
        "campaign_window_sha256": window.get("sha256")
        if isinstance(window, Mapping)
        else None,
        "execution_contract_sha256": contract_sha256,
        "mode_manifest_sha256": mode_inventory.get("mode_manifest_sha256")
        if isinstance(mode_inventory, Mapping)
        else None,
    }
    if not isinstance(run_identity, Mapping):
        integrity_error("Task41 B0 recovery manifest has no run identity")
        run_identity = {}
    for key, expected in expected_identity.items():
        if not expected or run_identity.get(key) != expected:
            integrity_error(f"Task41 B0 recovery run identity differs at {key}")
    for key in ("staged_input_sha256", "carrier_committed_prefix_sha256"):
        value = run_identity.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            integrity_error(f"Task41 B0 recovery run identity has invalid {key}")
    manifest_identity_binding_valid = manifest_loaded and not integrity_errors

    support = manifest.get("saved_surface_support_certificate")
    summary_support = summary.get("b0_saved_surface_support_certificate")
    support_nonzero = (
        support.get("cell_interior_nonzero_values")
        if isinstance(support, Mapping)
        else None
    )
    support_digest = hashlib.sha256(
        json.dumps(
            support if isinstance(support, Mapping) else {},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if (
        not isinstance(support, Mapping)
        or support.get("schema") != "task41.p0.b0.saved_surface_support_inventory.v1"
        or support != summary_support
        or support_nonzero != 0
        or manifest.get("local_interior_Bi_Di_exact_zero") is not True
        or manifest.get("local_interior_Bi_Di_nonzero_entry_count") != 0
        or manifest.get("saved_surface_support_certificate_passed") is not True
        or manifest.get("saved_surface_support_certificate_sha256") != support_digest
    ):
        integrity_error("Task41 B0 exact-zero local Bi/Di support certificate is absent or mismatched")
    loop = binding.get("same_lu_refinement_loop")
    loop_identity_matches = (
        isinstance(loop, Mapping)
        and loop.get("production_and_witness_share_loop") is True
        and loop.get("maximum_steps_per_column") == 3
        and loop.get("full_carrier_sweeps_per_correction") == 0
        and loop.get("correction_driver")
        == "independent_native_cell_interior_volume_residual"
    )
    legacy_failed_missing_step_limit = (
        "b0_recovery_refinement_max_steps" not in summary
        and manifest_identity_binding_valid
        and manifest.get("stage") == "FULL_ACTION_GATE_FAILED"
        and manifest.get("status") == "FAIL"
        and binding.get("stage") == "FULL_ACTION_GATE_FAILED"
        and binding.get("status") == "FAIL"
        and loop_identity_matches
        and loop.get("production_route_reached") is False
    )
    if (
        summary.get("b0_recovery_refinement_max_steps") != 3
        and not legacy_failed_missing_step_limit
    ):
        integrity_error(
            "Task41 B0 production path is not bound to the shared three-step recovery loop"
        )
    if not loop_identity_matches:
        integrity_error("Task41 B0 recovery evidence does not bind the shared same-LU correction loop")

    checked_columns = []
    shared_raw_classes: dict[str, tuple[str, str, str, str]] = {}
    columns = manifest.get("columns")
    full_rows = manifest.get("full_storage_rows")
    if type(full_rows) is not int or full_rows < 1:
        integrity_error("Task41 B0 recovery manifest has an invalid full storage size")
    if not isinstance(columns, list) or len(columns) != 2:
        integrity_error("Task41 B0 recovery manifest does not contain both input columns")
        columns = []

    def load_array(record: Any, label: str) -> np.ndarray:
        if not isinstance(record, Mapping):
            raise ValueError(f"{label} artifact record is missing")
        return _task41_npy_artifact(numerical_output.parent, record, label)

    def require_vector(record: Any, label: str, *, size: int | None = None) -> np.ndarray:
        value = load_array(record, label)
        if (
            value.ndim != 1
            or value.dtype != np.dtype(np.complex128)
            or (size is not None and value.shape != (size,))
        ):
            raise ValueError(f"{label} has an invalid complex-vector layout")
        return value

    def require_close_recorded(actual: float, recorded: Any, label: str) -> None:
        try:
            declared = float(recorded)
        except (TypeError, ValueError):
            integrity_error(f"Task41 B0 {label} metric is missing")
            return
        if not np.isfinite(declared) or abs(actual - declared) > 5.0e-13 * max(1.0, abs(actual)):
            integrity_error(f"Task41 B0 {label} metric differs from its raw arrays")

    full_action = manifest.get("full_action")
    if not isinstance(full_action, Mapping):
        integrity_error("Task41 B0 joint-action record is missing")
    else:
        joint = full_action.get("artifacts")
        if not isinstance(joint, Mapping):
            integrity_error("Task41 B0 joint-action artifact inventory is missing")
        else:
            try:
                p6 = load_array(joint.get("p6_result"), "joint P6 result")
                port_rhs = load_array(joint.get("port_rhs"), "joint port RHS")
                reduced_rhs = load_array(joint.get("reduced_rhs"), "joint reduced RHS")
                if (
                    p6.ndim != 2
                    or reduced_rhs.shape != p6.shape
                    or p6.shape[1] != 2
                    or port_rhs.ndim != 2
                    or port_rhs.shape[1] != 2
                    or port_rhs.shape[0] < 1
                    or port_rhs.shape[0] >= p6.shape[0]
                    or p6.dtype != np.dtype(np.complex128)
                    or port_rhs.dtype != np.dtype(np.complex128)
                    or reduced_rhs.dtype != np.dtype(np.complex128)
                    or not np.isfinite(p6).all()
                    or not np.isfinite(port_rhs).all()
                    or not np.isfinite(reduced_rhs).all()
                ):
                    raise ValueError(
                        "joint-action arrays have invalid shapes, dtypes, or non-finite values"
                    )

                active_rows = int(p6.shape[0] - port_rhs.shape[0])
                port_rows = int(port_rhs.shape[0])
                declared_errors = full_action.get(
                    "p6_vs_native_reduced_rhs_relative_errors"
                )
                if not isinstance(declared_errors, list) or len(declared_errors) != 2:
                    integrity_error(
                        "Task41 B0 joint-action record omits both per-column error metrics"
                    )

                column_metrics: list[dict[str, Any]] = []
                errors_by_column: list[float] = []
                for column_index in range(2):
                    left = p6[:, column_index]
                    right = reduced_rhs[:, column_index]
                    denominator = max(
                        _task41_b0_chunked_norm(left),
                        _task41_b0_chunked_norm(right),
                        np.finfo(float).tiny,
                    )
                    overall = _task41_b0_chunked_difference_summary(left, right)
                    trace = _task41_b0_chunked_difference_summary(
                        left, right, start=0, stop=active_rows
                    )
                    port = _task41_b0_chunked_difference_summary(
                        left, right, start=active_rows, stop=int(p6.shape[0])
                    )
                    relative_error = overall["absolute_l2"] / denominator
                    errors_by_column.append(relative_error)
                    if isinstance(declared_errors, list) and len(declared_errors) == 2:
                        require_close_recorded(
                            relative_error,
                            declared_errors[column_index],
                            f"joint P6/native column {column_index} relative error",
                        )

                    p6_port = p6[active_rows:, column_index]
                    reduced_port = reduced_rhs[active_rows:, column_index]
                    saved_port_rhs = port_rhs[:, column_index]
                    port_comparisons = {
                        "p6_vs_reduced": _task41_b0_chunked_difference_summary(
                            p6_port, reduced_port
                        ),
                        "p6_vs_port_rhs": _task41_b0_chunked_difference_summary(
                            p6_port, saved_port_rhs
                        ),
                        "reduced_vs_port_rhs": _task41_b0_chunked_difference_summary(
                            reduced_port, saved_port_rhs
                        ),
                        "p6_port_norm": _task41_b0_chunked_norm(p6_port),
                        "reduced_port_norm": _task41_b0_chunked_norm(reduced_port),
                        "port_rhs_norm": _task41_b0_chunked_norm(saved_port_rhs),
                    }
                    for comparison in (
                        "p6_vs_reduced",
                        "p6_vs_port_rhs",
                        "reduced_vs_port_rhs",
                    ):
                        port_comparisons[comparison][
                            "same_overall_denominator_contribution"
                        ] = (
                            port_comparisons[comparison]["absolute_l2"] / denominator
                        )
                    column_metrics.append(
                        {
                            "column": column_index,
                            "original_denominator": denominator,
                            "absolute_l2": overall["absolute_l2"],
                            "sum_squares": overall["sum_squares"],
                            "max_abs_row": overall["max_abs_row"],
                            "max_abs_row_index": overall["max_abs_row_index"],
                            "relative_error": relative_error,
                            "trace_rows": active_rows,
                            "trace": {
                                **trace,
                                "same_overall_denominator_contribution": (
                                    trace["absolute_l2"] / denominator
                                ),
                            },
                            "port_rows": port_rows,
                            "port": {
                                **port,
                                "same_overall_denominator_contribution": (
                                    port["absolute_l2"] / denominator
                                ),
                            },
                            "port_comparisons": port_comparisons,
                        }
                    )

                declared_d_error = full_action.get(
                    "original_and_active_D_relative_error"
                )
                try:
                    d_error = float(declared_d_error)
                except (TypeError, ValueError):
                    d_error = float("nan")
                d_passed = bool(np.isfinite(d_error) and d_error <= 1.0e-11)
                joint_action_passed = bool(
                    all(value <= 1.0e-11 for value in errors_by_column) and d_passed
                )
                if not d_passed:
                    joint_action_error(
                        "Task41 B0 recorded original/active D error fails the original gate"
                    )
                if not all(value <= 1.0e-11 for value in errors_by_column):
                    joint_action_error(
                        "Task41 B0 saved P6/native reduced RHS difference reproduces the original gate failure"
                    )
                expected_joint_status = "PASS" if joint_action_passed else "FAIL"
                if full_action.get("status") != expected_joint_status:
                    integrity_error(
                        "Task41 B0 joint-action status differs from its recomputed arrays"
                    )
                if full_action.get("valid_shapes_and_finite_values") is not True:
                    integrity_error(
                        "Task41 B0 joint-action finite/layout claim differs from valid saved arrays"
                    )
                joint_action_completed = True
                joint_action_metrics = column_metrics
            except (OSError, ValueError, TypeError, KeyError) as exc:
                integrity_error(f"Task41 B0 joint-action replay is incomplete: {exc}")

    save_checkpoint(
        "JOINT_ACTION_CHUNKS_COMPLETE",
        replayed=joint_action_completed,
        passed=joint_action_passed,
        metrics=joint_action_metrics,
        integrity_error_count=len(integrity_errors),
    )

    for expected_column, column in enumerate(columns):
        try:
            if not isinstance(column, Mapping):
                raise ValueError("column record is malformed")
            artifacts = column.get("artifacts")
            if not isinstance(artifacts, Mapping):
                raise ValueError("column artifact inventory is missing")
            if column.get("column") != expected_column or column.get("status") != "CAPTURED":
                raise ValueError("recovery column identity or captured status differs")
            mode_index = column.get("mode_index")
            input_rows = manifest.get("input_identities", [])
            identity_row = input_rows[expected_column]
            if (
                mode_index != expected_mode_indices[expected_column]
                or identity_row.get("mode_index") != mode_index
            ):
                raise ValueError("the two frozen selected B modes or column order differ")
            known = require_vector(artifacts.get("known_field"), "known field", size=full_rows)
            volume_rhs = require_vector(
                artifacts.get("native_volume_rhs"), "native volume RHS", size=full_rows
            )
            native_rhs = require_vector(
                artifacts.get("native_rhs"), "aggregate native RHS", size=full_rows
            )
            b_rows = load_array(artifacts.get("selected_B_frame_rows"), "selected B rows")
            b_values = load_array(artifacts.get("selected_B_frame_values"), "selected B values")
            b_alpha_rows = load_array(artifacts.get("b_alpha_rows"), "B-alpha rows")
            b_alpha_values = load_array(artifacts.get("b_alpha_values"), "B-alpha values")
            if (
                b_rows.ndim != 1
                or b_rows.dtype.kind not in "iu"
                or b_values.shape != b_rows.shape
                or b_values.dtype != np.dtype(np.complex128)
                or b_alpha_rows.ndim != 1
                or b_alpha_rows.dtype.kind not in "iu"
                or b_alpha_values.shape != b_alpha_rows.shape
                or b_alpha_values.dtype != np.dtype(np.complex128)
                or (b_rows.size and (int(b_rows[0]) < 0 or int(b_rows[-1]) >= full_rows))
                or (b_rows.size > 1 and np.any(b_rows[1:] <= b_rows[:-1]))
                or (b_alpha_rows.size > 1 and np.any(b_alpha_rows[1:] <= b_alpha_rows[:-1]))
                or (b_alpha_rows.size and (int(b_alpha_rows[0]) < 0 or int(b_alpha_rows[-1]) >= full_rows))
                or not np.isfinite(b_values).all()
                or not np.isfinite(b_alpha_values).all()
            ):
                raise ValueError("selected B-frame artifacts have invalid row/value layouts")
            alpha_pair = identity_row.get("port_alpha")
            if not isinstance(alpha_pair, list) or len(alpha_pair) != 2:
                raise ValueError("selected B input has no saved complex port amplitude")
            alpha = complex(float(alpha_pair[0]), float(alpha_pair[1]))
            if not np.isfinite([alpha.real, alpha.imag]).all():
                raise ValueError("selected B input amplitude is non-finite")
            expected_b_values = b_values * alpha
            nonzero = expected_b_values != 0.0
            if not np.array_equal(b_alpha_rows, b_rows[nonzero]) or not np.array_equal(
                b_alpha_values, expected_b_values[nonzero]
            ):
                raise ValueError("saved B-alpha vector does not replay from the selected B frame")
            for start in range(0, full_rows, 262_144):
                stop = min(full_rows, start + 262_144)
                expected_rhs = np.asarray(volume_rhs[start:stop], dtype=np.complex128).copy()
                selected = (b_alpha_rows >= start) & (b_alpha_rows < stop)
                if np.any(selected):
                    expected_rhs[b_alpha_rows[selected] - start] += b_alpha_values[selected]
                if not np.array_equal(expected_rhs, np.asarray(native_rhs[start:stop])):
                    raise ValueError("aggregate native RHS does not equal saved volume RHS plus B-alpha")

            active_original_rows = load_array(
                artifacts.get("active_original_rows"), "active original rows"
            )
            slave_rows = load_array(artifacts.get("slave_rows"), "MPC slave rows")
            if (
                active_original_rows.ndim != 1
                or active_original_rows.dtype.kind not in "iu"
                or slave_rows.ndim != 1
                or slave_rows.dtype.kind not in "iu"
                or np.any(active_original_rows < 0)
                or np.any(active_original_rows >= full_rows)
                or np.any(slave_rows < 0)
                or np.any(slave_rows >= full_rows)
                or np.unique(active_original_rows).size != active_original_rows.size
                or np.unique(slave_rows).size != slave_rows.size
                or np.intersect1d(active_original_rows, slave_rows).size
            ):
                raise ValueError("active or slave original-row identity is malformed")

            initial_storage = require_vector(
                artifacts.get("recovered_storage"), "initial recovered storage", size=full_rows
            )
            initial_action = require_vector(
                artifacts.get("native_volume_action_recovered"),
                "initial native volume action",
                size=full_rows,
            )
            initial_residual = require_vector(
                artifacts.get("native_volume_residual"), "initial native volume residual", size=full_rows
            )
            if _task41_b0_chunked_residual_discrepancy(
                initial_residual, volume_rhs, initial_action
            ) > 5.0e-13 * max(1.0, _task41_b0_chunked_norm(volume_rhs)):
                raise ValueError("initial native volume residual does not replay from raw vectors")
            if (
                not _task41_b0_indexed_arrays_equal(
                    initial_storage, known, active_original_rows
                )
                or not _task41_b0_indexed_arrays_equal(
                    known, known, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    volume_rhs, volume_rhs, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    native_rhs, native_rhs, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    initial_storage, initial_storage, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    initial_action, initial_action, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    initial_residual, initial_residual, slave_rows, zero=True
                )
            ):
                raise ValueError("initial recovery did not preserve trace/slave storage identities")
            initial_forward = _task41_b0_chunked_relative_error(initial_storage, known)
            initial_residual_relative = (
                _task41_b0_chunked_norm(initial_residual)
                / max(_task41_b0_chunked_norm(volume_rhs), np.finfo(float).tiny)
            )
            require_close_recorded(
                initial_forward, column.get("forward_relative_error"), "initial forward error"
            )
            require_close_recorded(
                initial_residual_relative,
                column.get("native_volume_residual_relative"),
                "initial volume residual",
            )

            refinement = column.get("same_lu_refinement", [])
            if not isinstance(refinement, list) or len(refinement) > 3:
                raise ValueError("same-LU correction inventory exceeds three steps")
            final_storage = initial_storage
            final_residual_relative = initial_residual_relative
            final_forward = initial_forward
            for step, record in enumerate(refinement, start=1):
                if not isinstance(record, Mapping) or record.get("step") != step:
                    raise ValueError("same-LU correction steps are missing or out of order")
                step_artifacts = record.get("artifacts")
                if not isinstance(step_artifacts, Mapping):
                    raise ValueError("same-LU correction step omits raw artifacts")
                final_storage = require_vector(
                    step_artifacts.get("storage"), "same-LU storage", size=full_rows
                )
                step_action = require_vector(
                    step_artifacts.get("native_volume_action"),
                    "same-LU volume action",
                    size=full_rows,
                )
                step_residual = require_vector(
                    step_artifacts.get("native_volume_residual"),
                    "same-LU volume residual",
                    size=full_rows,
                )
                discrepancy = _task41_b0_chunked_residual_discrepancy(
                    step_residual, volume_rhs, step_action
                )
                if discrepancy > 5.0e-13 * max(
                    1.0, _task41_b0_chunked_norm(volume_rhs)
                ):
                    raise ValueError("same-LU native volume residual does not replay")
                final_forward = _task41_b0_chunked_relative_error(final_storage, known)
                final_residual_relative = _task41_b0_chunked_norm(step_residual) / max(
                    _task41_b0_chunked_norm(volume_rhs), np.finfo(float).tiny
                )
                if (
                    not _task41_b0_indexed_arrays_equal(
                        final_storage, known, active_original_rows
                    )
                    or not _task41_b0_indexed_arrays_equal(
                        final_storage, final_storage, slave_rows, zero=True
                    )
                    or not _task41_b0_indexed_arrays_equal(
                        step_action, step_action, slave_rows, zero=True
                    )
                    or not _task41_b0_indexed_arrays_equal(
                        step_residual, step_residual, slave_rows, zero=True
                    )
                ):
                    raise ValueError("same-LU correction changed trace or nonzero MPC slave storage")
                require_close_recorded(
                    final_forward, record.get("forward_relative_error"), "same-LU forward error"
                )
                require_close_recorded(
                    final_residual_relative,
                    record.get("native_volume_residual_relative"),
                    "same-LU volume residual",
                )

            if refinement:
                require_close_recorded(
                    final_forward, column.get("final_forward_relative_error"), "final forward error"
                )
                require_close_recorded(
                    final_residual_relative,
                    column.get("final_native_volume_residual_relative"),
                    "final volume residual",
                )

            initial_gate_passed = bool(
                np.isfinite(initial_forward)
                and initial_forward <= 1.0e-11
                and np.isfinite(initial_residual_relative)
                and initial_residual_relative <= 1.0e-10
            )
            final_gate_passed = bool(
                np.isfinite(final_forward)
                and final_forward <= 1.0e-11
                and np.isfinite(final_residual_relative)
                and final_residual_relative <= 1.0e-10
            )
            column_passed = bool(
                final_gate_passed
                and column.get("recovery_passed") is True
                and (
                    bool(refinement)
                    or column.get("final_forward_relative_error") is None
                )
            )
            column_result = {
                "column": expected_column,
                "mode_index": mode_index,
                "initial_forward_relative": initial_forward,
                "initial_native_volume_residual_relative": initial_residual_relative,
                "initial_gate_passed": initial_gate_passed,
                "same_lu_steps_replayed": len(refinement),
                "final_forward_relative": final_forward,
                "final_native_volume_residual_relative": final_residual_relative,
                "final_gate_passed": final_gate_passed,
                "manifest_claim_matches_recomputed_gate": (
                    column.get("recovery_passed") is final_gate_passed
                ),
                "passed": column_passed,
            }
            checked_columns.append(column_result)
            if not column_passed:
                recovery_error(
                    f"Task41 B0 recovery column {expected_column} finite gate failed: "
                    f"forward={final_forward}, volume_residual={final_residual_relative}"
                )

            raw_integrity_errors_before = len(integrity_errors)
            raw_diagnostic = column.get("raw_cell_diagnostic")
            if refinement or not initial_gate_passed:
                if (
                    not isinstance(raw_diagnostic, Mapping)
                    or raw_diagnostic.get("structure_identity_passed") is not True
                    or raw_diagnostic.get("raw_matrices_are_independently_retabulated") is not True
                    or not isinstance(raw_diagnostic.get("cells"), list)
                    or not 1 <= len(raw_diagnostic["cells"]) <= 3
                ):
                    integrity_error(
                        f"Task41 B0 recovery column {expected_column} lacks bounded raw-cell evidence"
                    )
                else:
                    for cell in raw_diagnostic["cells"]:
                        cell_artifacts = cell.get("artifacts", {})
                        class_artifacts = cell.get("class_artifacts", {})
                        class_identity = str(class_artifacts.get("class_identity", ""))
                        class_refs = tuple(
                            str(class_artifacts.get(name, {}).get("path", ""))
                            for name in ("Vii", "Vit", "lu_factor", "lu_pivots")
                        )
                        if not class_identity or any(not path for path in class_refs):
                            integrity_error("Task41 B0 raw class lacks matrix/LU artifact identity")
                            continue
                        if class_identity in shared_raw_classes and shared_raw_classes[class_identity] != class_refs:
                            integrity_error("Task41 B0 repeated raw class matrices were not shared")
                            continue
                        shared_raw_classes[class_identity] = class_refs
                        vii = np.asarray(load_array(class_artifacts.get("Vii"), "raw Vii"))
                        vit = np.asarray(load_array(class_artifacts.get("Vit"), "raw Vit"))
                        lu_factor = np.asarray(load_array(class_artifacts.get("lu_factor"), "raw local LU"))
                        lu_pivots = np.asarray(load_array(class_artifacts.get("lu_pivots"), "raw local pivots"))
                        known_i = np.asarray(load_array(cell_artifacts.get("known_interior"), "raw known interior"))
                        known_t = np.asarray(load_array(cell_artifacts.get("known_trace"), "raw known trace"))
                        rhs_i = np.asarray(load_array(cell_artifacts.get("native_volume_rhs_interior"), "raw volume RHS interior"))
                        rec_i = np.asarray(load_array(cell_artifacts.get("recovered_interior"), "raw recovered interior"))
                        rec_t = np.asarray(load_array(cell_artifacts.get("recovered_trace"), "raw recovered trace"))
                        action_i = np.asarray(load_array(cell_artifacts.get("native_volume_action_interior"), "raw volume action interior"))
                        residual_i = np.asarray(load_array(cell_artifacts.get("native_volume_residual_interior"), "raw volume residual interior"))
                        interior_rows = np.asarray(load_array(cell_artifacts.get("interior_original_rows"), "raw interior row map"))
                        trace_rows = np.asarray(load_array(cell_artifacts.get("trace_original_rows"), "raw trace row map"))
                        active_ids = np.asarray(load_array(cell_artifacts.get("active_ids"), "raw active ids"))
                        expansion_data = np.asarray(load_array(cell_artifacts.get("trace_expansion_data"), "raw trace expansion data"))
                        expansion_indices = np.asarray(load_array(cell_artifacts.get("trace_expansion_indices"), "raw trace expansion indices"))
                        expansion_indptr = np.asarray(load_array(cell_artifacts.get("trace_expansion_indptr"), "raw trace expansion indptr"))
                        permutation = np.asarray(load_array(cell_artifacts.get("cell_permutation_info"), "raw cell permutation"))
                        if (
                            vii.ndim != 2 or vit.ndim != 2 or vii.shape[0] != vii.shape[1]
                            or vit.shape[0] != vii.shape[0]
                            or lu_factor.shape != vii.shape or lu_pivots.shape != (vii.shape[0],)
                            or lu_pivots.dtype.kind not in "iu"
                            or vii.dtype != np.dtype(np.complex128)
                            or vit.dtype != np.dtype(np.complex128)
                            or lu_factor.dtype != np.dtype(np.complex128)
                            or known_i.shape != (vii.shape[0],) or rhs_i.shape != known_i.shape
                            or rec_i.shape != known_i.shape or known_t.shape != (vit.shape[1],)
                            or rec_t.shape != known_t.shape
                            or action_i.shape != known_i.shape or residual_i.shape != known_i.shape
                            or any(
                                value.dtype != np.dtype(np.complex128)
                                for value in (known_i, rhs_i, rec_i, known_t, rec_t, action_i, residual_i)
                            )
                            or interior_rows.shape != known_i.shape or interior_rows.dtype.kind not in "iu"
                            or trace_rows.shape != known_t.shape or trace_rows.dtype.kind not in "iu"
                            or np.any(interior_rows < 0) or np.any(interior_rows >= full_rows)
                            or np.any(trace_rows < 0) or np.any(trace_rows >= full_rows)
                            or np.unique(interior_rows).size != interior_rows.size
                            or np.unique(trace_rows).size != trace_rows.size
                            or active_ids.ndim != 1 or active_ids.dtype.kind not in "iu"
                            or np.any(active_ids < 0) or np.any(active_ids >= active_original_rows.size)
                            or np.unique(active_ids).size != active_ids.size
                            or expansion_data.ndim != 1
                            or expansion_data.dtype != np.dtype(np.complex128)
                            or expansion_indices.ndim != 1
                            or expansion_indices.dtype.kind not in "iu"
                            or expansion_indptr.ndim != 1
                            or expansion_indptr.dtype.kind not in "iu"
                            or expansion_indptr.shape != (len(trace_rows) + 1,)
                            or expansion_indices.shape != expansion_data.shape
                            or expansion_indptr[0] != 0
                            or np.any(expansion_indptr < 0)
                            or np.any(expansion_indptr[1:] < expansion_indptr[:-1])
                            or expansion_indptr[-1] != len(expansion_data)
                            or np.any(expansion_indices < 0)
                            or np.any(expansion_indices >= len(active_ids))
                            or not np.isfinite(vii).all()
                            or not np.isfinite(vit).all()
                            or not np.isfinite(lu_factor).all()
                            or not np.isfinite(expansion_data).all()
                            or permutation.shape != (1,)
                            or permutation.dtype.kind not in "iu"
                        ):
                            integrity_error("Task41 B0 raw-cell Vii/Vit evidence has inconsistent local layouts")
                            continue
                        try:
                            from scipy.sparse import csr_matrix
                            from scipy.linalg import lu_solve

                            expansion = csr_matrix(
                                (expansion_data, expansion_indices, expansion_indptr),
                                shape=(len(trace_rows), len(active_ids)),
                            )
                            if not expansion.has_canonical_format:
                                raise ValueError("raw trace-expansion CSR is not canonical")
                            active_values = np.asarray(known[active_original_rows], dtype=np.complex128)
                            recovered_active_values = np.asarray(initial_storage[active_original_rows], dtype=np.complex128)
                            expected_known_trace = np.asarray(
                                expansion @ active_values[active_ids], dtype=np.complex128
                            ).reshape(-1)
                            expected_recovered_trace = np.asarray(
                                expansion @ recovered_active_values[active_ids], dtype=np.complex128
                            ).reshape(-1)
                            writable_pivots = _task41_b0_owned_writable_lu_pivots(
                                lu_pivots, order=vii.shape[0]
                            )
                            save_checkpoint(
                                "BEFORE_SMALL_CLASS_GETRS",
                                column=expected_column,
                                class_identity=class_identity,
                                factor_shape=list(lu_factor.shape),
                                factor_dtype=str(lu_factor.dtype),
                                pivot_dtype=str(lu_pivots.dtype),
                                pivot_copy_dtype=str(writable_pivots.dtype),
                                pivot_copy_owns_data=bool(writable_pivots.flags.owndata),
                                pivot_copy_writeable=bool(writable_pivots.flags.writeable),
                            )
                            lu_identity = lu_solve((lu_factor, writable_pivots), vii)
                            lu_identity_max_abs_error = float(
                                np.max(np.abs(lu_identity - np.eye(vii.shape[0])))
                            )
                            save_checkpoint(
                                "AFTER_SMALL_CLASS_GETRS",
                                column=expected_column,
                                class_identity=class_identity,
                                lu_identity_max_abs_error=lu_identity_max_abs_error,
                            )
                        except (ValueError, TypeError, IndexError) as exc:
                            integrity_error(f"Task41 B0 raw cell mapping/LU replay failed: {exc}")
                            continue
                        if (
                            not np.array_equal(known_i, known[interior_rows])
                            or not np.array_equal(volume_rhs[interior_rows], rhs_i)
                            or not np.array_equal(initial_storage[interior_rows], rec_i)
                            or not np.array_equal(initial_action[interior_rows], action_i)
                            or not np.array_equal(initial_residual[interior_rows], residual_i)
                            or not np.array_equal(known_t, expected_known_trace)
                            or not np.array_equal(rec_t, expected_recovered_trace)
                            or not np.allclose(lu_identity, np.eye(vii.shape[0]), rtol=1e-10, atol=1e-10)
                        ):
                            integrity_error("Task41 B0 raw local rows, MPC trace expansion, or LU identity failed")
                            continue
                        known_action = vii @ known_i + vit @ known_t
                        recovered_action = vii @ rec_i + vit @ rec_t
                        local_scale = max(float(np.linalg.norm(rhs_i)), float(np.linalg.norm(action_i)), np.finfo(float).tiny)
                        if (
                            np.linalg.norm(known_action - rhs_i) / local_scale > 1.0e-10
                            or np.linalg.norm(recovered_action - action_i) / local_scale > 1.0e-10
                            or not np.allclose(rhs_i - action_i, residual_i, rtol=5e-13, atol=5e-13)
                        ):
                            integrity_error("Task41 B0 independent raw-cell Vii/Vit replay failed")
            raw_audit_passed = len(integrity_errors) == raw_integrity_errors_before
            if raw_audit_passed:
                raw_audit_completed_columns += 1
            save_checkpoint(
                "COLUMN_AUDIT_RETURNED",
                column=expected_column,
                mode_index=column_result["mode_index"],
                recovery_passed=column_result["passed"],
                raw_audit_passed=raw_audit_passed,
                integrity_error_count=len(integrity_errors),
            )
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            integrity_error(f"Task41 B0 recovery column {expected_column} replay failed: {exc}")
            save_checkpoint(
                "COLUMN_AUDIT_RETURNED",
                column=expected_column,
                status="ERROR",
                error=str(exc),
                integrity_error_count=len(integrity_errors),
            )

    actual_steps = max(
        (
            len(row.get("same_lu_refinement", []))
            for row in columns
            if isinstance(row, Mapping)
        ),
        default=0,
    )
    recorded_steps = manifest.get("same_lu_refinement_max_steps_used", 0)
    if type(recorded_steps) is not int or recorded_steps != actual_steps or not 0 <= recorded_steps <= 3:
        integrity_error("Task41 B0 manifest same-LU step count differs from its raw states")
    if len(shared_raw_classes) > 3:
        integrity_error("Task41 B0 recovery evidence stores more than three raw local classes")
    recovery_passed = bool(
        len(checked_columns) == 2
        and all(row.get("passed") is True for row in checked_columns)
    )
    audit_completed = bool(
        manifest_loaded
        and len(checked_columns) == 2
        and raw_audit_completed_columns == 2
        and joint_action_completed
    )
    data_integrity = not integrity_errors
    qualification_passed = bool(
        audit_completed
        and data_integrity
        and recovery_passed
        and joint_action_passed is True
        and manifest.get("status") == "PASS"
        and binding.get("status") == "PASS"
    )
    # This helper audits recovery/action evidence only; it does not certify an
    # official target solve, full-field residual, or physical-output result.
    official_result = False
    return {
        "schema": "task41.p0.b0.recovery_evidence_checker.v1",
        "manifest_path": manifest_ref.get("path") if isinstance(manifest_ref, Mapping) else None,
        "manifest_stage": manifest.get("stage"),
        "audit_completed": audit_completed,
        "legacy_failed_missing_step_limit_accepted": legacy_failed_missing_step_limit,
        "production_route_reached": (
            loop.get("production_route_reached")
            if isinstance(loop, Mapping) and type(loop.get("production_route_reached")) is bool
            else None
        ),
        "data_integrity": data_integrity,
        "integrity_errors": integrity_errors,
        "recovery_passed": recovery_passed,
        "recovery_errors": recovery_errors,
        "joint_action_status": (
            "PASS"
            if joint_action_passed is True
            else "FAIL"
            if joint_action_passed is False
            else "NOT_RUN"
        ),
        "joint_action_passed": joint_action_passed,
        "joint_action_replayed": joint_action_completed,
        "joint_action_errors": joint_action_errors,
        "joint_action_metrics": joint_action_metrics,
        "checkpoints": checkpoint_events,
        "qualification_passed": qualification_passed,
        "official_result": official_result,
        "run_identity_rechecked": not any("identity" in error for error in integrity_errors),
        "support_certificate_rechecked": not any(
            "support certificate" in error for error in integrity_errors
        ),
        "columns": checked_columns,
        "errors": errors,
        "passed": qualification_passed,
    }


def load_task41_v4_volume_only_donor(
    *, summary_path: Path, numerical_output: Path
) -> dict[str, Any]:
    """Load only the hash-bound B0 arrays needed by the V4 volume audit.

    This intentionally reuses the saved-audit artifact checker and returns the
    narrow normalized mapping consumed by the V4 solver helper. The existing
    full saved-evidence checker still runs in the service's closeout phase.
    """

    from src.solvers.task41_v4_volume_only_audit import (
        TASK41_V4_DONOR_MANIFEST_SHA256,
        TASK41_V4_DONOR_NPY_BYTES,
    )

    summary_path = Path(summary_path).resolve(strict=True)
    run_root = summary_path.parent.resolve(strict=True)
    numerical_output = Path(numerical_output).resolve()
    if (
        summary_path.name != "task40_v10_p6_candidate_summary.json"
        or numerical_output != run_root / "numerical_output"
    ):
        raise ValueError("Task41 V4 donor path differs from the registered saved-output run")
    summary = _json_object(summary_path, "Task41 V4 donor summary")
    binding = summary.get("b0_recovery_evidence")
    manifest_ref = binding.get("manifest") if isinstance(binding, Mapping) else None
    if not isinstance(manifest_ref, Mapping):
        raise ValueError("Task41 V4 donor summary omits the recovery-manifest reference")
    manifest_path = _task41_run_artifact(run_root, manifest_ref, "V4 recovery manifest")
    manifest_sha256 = sha256_file(manifest_path)
    if manifest_sha256 != TASK41_V4_DONOR_MANIFEST_SHA256:
        raise ValueError("Task41 V4 donor recovery-manifest hash differs from the frozen identity")
    manifest = _json_object(manifest_path, "Task41 V4 recovery manifest")

    evidence_records: dict[str, int] = {}

    def collect_array_records(value: Any) -> None:
        if isinstance(value, Mapping):
            if (
                isinstance(value.get("path"), str)
                and isinstance(value.get("shape"), list)
                and isinstance(value.get("dtype"), str)
            ):
                raw_path = Path(str(value["path"]))
                path = (raw_path if raw_path.is_absolute() else run_root / raw_path).resolve()
                if not path.is_relative_to(run_root) or type(value.get("bytes")) is not int:
                    raise ValueError("Task41 V4 evidence inventory has an invalid array artifact")
                size = int(value["bytes"])
                previous = evidence_records.setdefault(str(path), size)
                if previous != size:
                    raise ValueError("Task41 V4 repeated artifact path has conflicting byte counts")
            for nested in value.values():
                collect_array_records(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_array_records(nested)

    collect_array_records(manifest)
    if len(evidence_records) != 141 or sum(evidence_records.values()) != TASK41_V4_DONOR_NPY_BYTES:
        raise ValueError("Task41 V4 donor does not bind the frozen 141-array evidence set")

    def load(record: Any, label: str) -> np.ndarray:
        if not isinstance(record, Mapping):
            raise ValueError(f"Task41 V4 {label} artifact record is missing")
        return _task41_npy_artifact(run_root, record, label)

    columns_meta = manifest.get("columns")
    raw_groups = manifest.get("raw_cell_diagnostics")
    if not isinstance(columns_meta, list) or len(columns_meta) != 2 or not isinstance(raw_groups, list) or len(raw_groups) != 2:
        raise ValueError("Task41 V4 donor manifest omits one of its two volume columns")
    columns: list[dict[str, Any]] = []
    raw_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    cell_maps: list[dict[str, Any]] = []
    for column_index, column_meta in enumerate(columns_meta):
        artifacts = column_meta.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"Task41 V4 column {column_index} artifact inventory is missing")
        column = {
            name: load(artifacts.get(name), f"column {column_index} {name}")
            for name in ("active_original_rows", "slave_rows", "known_field", "native_rhs")
        }
        for name in ("native_volume_rhs", "b_alpha_rows", "b_alpha_values", "selected_B_frame_rows", "selected_B_frame_values"):
            column[name] = load(artifacts.get(name), f"column {column_index} {name}")
        input_identity = manifest["input_identities"][column_index]
        alpha_pair = input_identity.get("port_alpha")
        if not isinstance(alpha_pair, list) or len(alpha_pair) != 2:
            raise ValueError(f"Task41 V4 column {column_index} port alpha is missing")
        alpha = complex(float(alpha_pair[0]), float(alpha_pair[1]))
        if not np.isfinite([alpha.real, alpha.imag]).all():
            raise ValueError(f"Task41 V4 column {column_index} port alpha is non-finite")
        expected_b_alpha = column["selected_B_frame_values"] * alpha
        nonzero = expected_b_alpha != 0.0
        full_rows = int(manifest.get("full_storage_rows", -1))
        frame_rows = column["selected_B_frame_rows"]
        frame_values = column["selected_B_frame_values"]
        b_alpha_rows = column["b_alpha_rows"]
        b_alpha_values = column["b_alpha_values"]
        if (
            frame_rows.ndim != 1
            or frame_rows.dtype.kind not in "iu"
            or frame_values.shape != frame_rows.shape
            or frame_values.dtype != np.dtype(np.complex128)
            or not np.isfinite(frame_values).all()
            or (frame_rows.size and (np.any(frame_rows < 0) or np.any(frame_rows >= full_rows)))
            or (frame_rows.size > 1 and np.any(frame_rows[1:] <= frame_rows[:-1]))
            or b_alpha_rows.ndim != 1
            or b_alpha_rows.dtype.kind not in "iu"
            or b_alpha_values.shape != b_alpha_rows.shape
            or b_alpha_values.dtype != np.dtype(np.complex128)
            or not np.isfinite(b_alpha_values).all()
            or (b_alpha_rows.size and (np.any(b_alpha_rows < 0) or np.any(b_alpha_rows >= full_rows)))
            or (b_alpha_rows.size > 1 and np.any(b_alpha_rows[1:] <= b_alpha_rows[:-1]))
            or not np.array_equal(b_alpha_rows, frame_rows[nonzero])
            or not np.array_equal(b_alpha_values, expected_b_alpha[nonzero])
        ):
            raise ValueError(f"Task41 V4 column {column_index} saved B-alpha does not replay")
        column["port_alpha"] = alpha

        state_artifacts = [
            (
                "j0",
                artifacts.get("recovered_storage"),
                artifacts.get("native_volume_action_recovered"),
                artifacts.get("native_volume_residual"),
            )
        ]
        refinement = column_meta.get("same_lu_refinement")
        if not isinstance(refinement, list) or len(refinement) != 3:
            raise ValueError(f"Task41 V4 column {column_index} lacks its saved j3 refinement state")
        last_step = refinement[-1]
        last_artifacts = last_step.get("artifacts") if isinstance(last_step, Mapping) else None
        if not isinstance(last_artifacts, Mapping) or last_step.get("step") != 3:
            raise ValueError(f"Task41 V4 column {column_index} last state is not step 3")
        state_artifacts.append(
            (
                "j3",
                last_artifacts.get("storage"),
                last_artifacts.get("native_volume_action"),
                last_artifacts.get("native_volume_residual"),
            )
        )
        column["states"] = [
            {
                "label": label,
                "storage": load(storage_ref, f"column {column_index} {label} storage"),
                "native_volume_action": load(action_ref, f"column {column_index} {label} action"),
                "native_volume_residual": load(residual_ref, f"column {column_index} {label} residual"),
            }
            for label, storage_ref, action_ref, residual_ref in state_artifacts
        ]
        columns.append(column)

        group = raw_groups[column_index]
        if (
            group.get("structure_identity_passed") is not True
            or group.get("raw_matrices_are_independently_retabulated") is not True
            or len(group.get("cells", ())) != 3
        ):
            raise ValueError(f"Task41 V4 column {column_index} raw-cell inventory is incomplete")
        for cell in group["cells"]:
            class_key = tuple(cell["class_key"])
            class_artifacts = cell["class_artifacts"]
            if class_key not in raw_by_key:
                raw_by_key[class_key] = {
                    "class_key": class_key,
                    "Vii": load(class_artifacts.get("Vii"), f"raw Vii class {class_key}"),
                    "Vit": load(class_artifacts.get("Vit"), f"raw Vit class {class_key}"),
                }
            cell_artifacts = cell["artifacts"]
            cell_maps.append(
                {
                    "column": column_index,
                    "cell_index": int(cell["cell_index"]),
                    "class_key": class_key,
                    **{
                        name: load(cell_artifacts.get(name), f"cell {cell['cell_index']} {name}")
                        for name in (
                            "interior_original_rows",
                            "trace_original_rows",
                            "active_ids",
                            "cell_permutation_info",
                            "trace_expansion_data",
                            "trace_expansion_indices",
                            "trace_expansion_indptr",
                        )
                    },
                }
            )

    full_action = manifest.get("full_action")
    joint_artifacts = full_action.get("artifacts") if isinstance(full_action, Mapping) else None
    if not isinstance(joint_artifacts, Mapping):
        raise ValueError("Task41 V4 donor full-action arrays are missing")
    support = manifest.get("saved_surface_support_certificate")
    support_digest = hashlib.sha256(
        json.dumps(
            support if isinstance(support, Mapping) else {},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if (
        not isinstance(support, Mapping)
        or support.get("cell_interior_nonzero_values") != 0
        or summary.get("b0_saved_surface_support_certificate") != support
        or manifest.get("local_interior_Bi_Di_exact_zero") is not True
        or manifest.get("local_interior_Bi_Di_nonzero_entry_count") != 0
        or manifest.get("saved_surface_support_certificate_passed") is not True
        or manifest.get("saved_surface_support_certificate_sha256") != support_digest
    ):
        raise ValueError("Task41 V4 donor lacks the exact-zero Bi/Di support certificate")
    return {
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "existing_evidence_bytes": sum(evidence_records.values()),
        "columns": columns,
        "raw_classes": list(raw_by_key.values()),
        "cell_maps": cell_maps,
        "attribution": {
            "joint": {
                name: load(joint_artifacts.get(name), f"joint {name}")
                for name in ("p6_result", "reduced_rhs", "port_rhs")
            },
            "local_class_identities": [],
        },
    }


def _task41_mesh_actual_exact_candidate_profile(
    report_path: Path, report: Mapping[str, Any]
) -> dict[str, str]:
    """Select a frozen V5, V6, or V8 exact-geometry evidence contract."""
    if report_path.name == "task41_p0_v5_mesh_actual_exact_attribution.json":
        if report.get("schema") != "task41.p0.v5.mesh_actual_exact_attribution_receipt.v1":
            raise ValueError("V5 candidate report schema differs")
        return {
            "version": "v5",
            "candidate_prefix": "task41_p0_v5_candidate",
            "attribution_prefix": "task41_p0_v5_attribution",
            "action_schema": "task41.p0.v5.global_geometry_native_elimination_attribution.v1",
            "denominators_source": "review_report_v5.md",
            "check_schema": "task41.p0.v5.mesh_actual_exact_candidate_check.v1",
        }
    if report_path.name == "task41_p0_v6_actual_qmetric_candidate.json":
        expected_identity = "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
        identity_audit = report.get("identity_audit")
        if (
            report.get("schema") != "task41.p0.v6.actual_qmetric_candidate_receipt.v1"
            or report.get("raw_tensor_evaluator") != "actual_qmetric_blocked_gram"
            or not isinstance(identity_audit, Mapping)
            or identity_audit.get("candidate_evaluator_identity") != expected_identity
        ):
            raise ValueError("V6 actual-qmetric candidate identity differs")
        return {
            "version": "v6",
            "candidate_prefix": "task41_p0_v6_qmetric_candidate",
            "attribution_prefix": "task41_p0_v6_qmetric_candidate_attribution",
            "action_schema": "task41.p0.v6.global_geometry_native_elimination_attribution.v1",
            "denominators_source": "review_report_v6.md",
            "check_schema": "task41.p0.v6.actual_qmetric_candidate_check.v1",
        }
    if report_path.name == "task41_p0_v8_selected_trace_star_audit.json":
        if (
            report.get("schema") != "task41.p0.v8.selected_trace_star_audit_receipt.v1"
            or report.get("status") != "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
            or report.get("raw_tensor_evaluator") != "actual_qmetric_blocked_gram"
        ):
            raise ValueError("V8 selected trace-star report schema or status differs")
        return {
            "version": "v8",
            "candidate_prefix": "task41_p0_v8_selected_cell",
            "attribution_prefix": "task41_p0_v8_selected_cell",
            "action_schema": "task41.p0.v8.selected_trace_star_p3_replay.v1",
            "denominators_source": "review_report_v8.md",
            "check_schema": "task41.p0.v8.selected_trace_star_independent_check.v1",
        }
    raise ValueError("exact-geometry candidate report filename is not registered")


def _task41_v6_candidate_producer_contract(
    report_path: Path,
    *,
    expected_report_sha256: str,
    consumer_contract: Mapping[str, Any],
    repo_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Reopen a saved V6/V8 report's producer contract beside the current checker contract."""
    report_path = Path(report_path).resolve(strict=True)
    results_root = (Path(repo_root) / "results").resolve()
    if not report_path.is_relative_to(results_root):
        raise ValueError("exact-geometry candidate report is outside the registered results tree")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", str(expected_report_sha256))
        or sha256_file(report_path) != expected_report_sha256
    ):
        raise ValueError("exact-geometry candidate report SHA-256 differs from the explicit binding")
    report = _json_object(report_path, "Task41 exact-geometry candidate report")
    profile = _task41_mesh_actual_exact_candidate_profile(report_path, report)
    if profile["version"] not in {"v6", "v8"}:
        return None, None

    source_sha = report.get("consumer_source_sha")
    contract_sha256 = report.get("consumer_contract_sha256")
    raw_contract_path = report.get("consumer_contract_path")
    if (
        not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
        or not isinstance(contract_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", contract_sha256) is None
        or not isinstance(raw_contract_path, str)
    ):
        raise ValueError("V6 candidate report omits its original producer contract binding")
    producer_contract_path = Path(raw_contract_path)
    producer_contract_path = (
        producer_contract_path
        if producer_contract_path.is_absolute()
        else Path(repo_root) / producer_contract_path
    ).resolve(strict=True)
    expected_contract_path = (
        Path(repo_root) / contract_relative_path(source_sha, "B0")
    ).resolve()
    if producer_contract_path != expected_contract_path:
        raise ValueError("V6 candidate producer contract path differs from its frozen source SHA")
    producer_contract, producer_digest = require_task41_p0_contract(
        producer_contract_path,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    producer_case = producer_contract.get("case")
    consumer_case = consumer_contract.get("case")
    producer_window = producer_contract.get("window")
    consumer_window = consumer_contract.get("window")
    if (
        producer_contract.get("source", {}).get("sha") != source_sha
        or not isinstance(producer_case, Mapping)
        or not isinstance(consumer_case, Mapping)
        or task41_case_id_for_run_id(str(producer_case.get("run_id", ""))) != "B0"
        or task41_case_id_for_run_id(str(consumer_case.get("run_id", ""))) != "B0"
        or not isinstance(producer_window, Mapping)
        or not isinstance(consumer_window, Mapping)
        or producer_window.get("sha256") != consumer_window.get("sha256")
    ):
        raise ValueError("V6 candidate producer contract differs from the current B0 checker window")
    for key in (
        "model_id",
        "method",
        "mpi_size",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
        "run_id",
    ):
        if producer_case.get(key) != consumer_case.get(key):
            raise ValueError(f"V6 candidate producer/checker contracts differ at {key}")
    return producer_contract, producer_digest


def _task41_validate_v6_prefix_qualification(
    qualification: Any,
    *,
    require_qualified: bool,
) -> str:
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        V6_PREFIX_QUALIFICATION_SCHEMA,
        V6_PREFIX_SAMPLE_CELL_INDICES,
    )
    from src.solvers.task41_v4_volume_only_audit import (
        TASK41_V5_FROZEN_DENOMINATORS,
    )

    if not isinstance(qualification, Mapping):
        raise ValueError("V6 candidate evaluator omits its prefix qualification state")
    records = qualification.get("records")
    if (
        qualification.get("schema") != V6_PREFIX_QUALIFICATION_SCHEMA
        or qualification.get("required_sample_cell_indices")
        != list(V6_PREFIX_SAMPLE_CELL_INDICES)
        or not isinstance(records, list)
        or qualification.get("sample_count") != len(records)
        or qualification.get("required_sample_count")
        != len(V6_PREFIX_SAMPLE_CELL_INDICES)
    ):
        raise ValueError("V6 prefix qualification inventory is malformed")
    status = qualification.get("status")
    if status == "P0_NOT_RUN_NO_WINDOW_APPROVAL":
        if (
            records
            or qualification.get("sample_count") != 0
            or qualification.get("geometry_witness_count") != 0
            or qualification.get("full_admission_eligible") is not False
            or require_qualified
        ):
            raise ValueError(
                "a P0 no-window record is legal only as non-qualified inventory, never full admission"
            )
        return "P0_NOT_RUN_NO_WINDOW_APPROVAL"
    if status != "PREFIX_QUALIFIED":
        if require_qualified:
            raise ValueError("V6 full candidate admission requires a qualified eight-key prefix")
        return str(status)
    if (
        len(records) != len(V6_PREFIX_SAMPLE_CELL_INDICES)
        or [record.get("cell_index") for record in records]
        != list(V6_PREFIX_SAMPLE_CELL_INDICES)
        or qualification.get("geometry_witness_count", 0) < 1
        or qualification.get("full_admission_eligible") is not True
    ):
        raise ValueError("V6 qualified prefix is incomplete or attached to a non-qualified report")
    saved_count = 0
    oracle_count = 0
    for record in records:
        source = record.get("source")
        if source == "V4_SAVED_ACTUAL_BLOCKS":
            saved_count += 1
            witness = record.get("geometry_witness")
            if (
                record.get("coordinates_bitwise_identity_passed") is not True
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("reference_report_sha256", "")))
                or not isinstance(witness, Mapping)
                or witness.get("status") != "NOT_REQUIRED_V4_SAVED_ACTUAL_BLOCKS"
                or len(record.get("local_action_comparisons", ())) != 6
            ):
                raise ValueError("V6 V4-saved prefix record omits actual identity or local-action evidence")
            observed_actions = record.get("local_action_comparisons", ())
            expected_action_keys = {
                (column, state)
                for column in (0, 1)
                for state in ("known", "j0", "j3")
            }
            if {
                (item.get("column"), item.get("state")) for item in observed_actions
            } != expected_action_keys or any(
                item.get("selected_active_row") != 5_458_716
                or item.get("frozen_denominator")
                != TASK41_V5_FROZEN_DENOMINATORS[item.get("column")]
                or item.get("selected_row_scale_check") != "diagnostic_only"
                or not np.isfinite(item.get("selected_row_difference_over_frozen_denominator", np.nan))
                or not isinstance(item.get("full_local_action"), Mapping)
                or not isinstance(
                    item.get("full_local_action", {}).get("absolute_frobenius"),
                    (int, float),
                )
                or not np.isfinite(
                    item.get("full_local_action", {}).get("absolute_frobenius", np.nan)
                )
                or item.get("full_local_action_scale_check") != "diagnostic_only"
                or not isinstance(
                    item.get("full_local_action_difference_over_frozen_denominator"),
                    (int, float),
                )
                or not np.isfinite(
                    item.get("full_local_action_difference_over_frozen_denominator", np.nan)
                )
                or not np.isclose(
                    item.get("full_local_action_difference_over_frozen_denominator", np.nan),
                    item["full_local_action"]["absolute_frobenius"]
                    / item["frozen_denominator"],
                    rtol=1.0e-12,
                    atol=0.0,
                )
                for item in observed_actions
            ):
                raise ValueError("V6 saved-cell action evidence omits frozen denominator checks")
        elif source == "ORIGINAL_FFCX_KERNEL_ORACLE":
            oracle_count += 1
            witness = record.get("geometry_witness")
            if (
                record.get("coordinates_bitwise_identity_passed") is not True
                or not isinstance(witness, Mapping)
                or witness.get("status") != "BITWISE_EQUAL"
                or witness.get("q_begin") != 0
                or witness.get("q_end") != 512
            ):
                raise ValueError("V6 missing-key sample lacks a full original-kernel geometry witness")
        else:
            raise ValueError("V6 prefix sample source is not registered")
        comparisons = record.get("comparisons")
        if (
            record.get("status") != "PASS"
            or record.get("admission_eligible") is not True
            or not isinstance(comparisons, Mapping)
            or any(
                not isinstance(comparisons.get(name), Mapping)
                or comparisons[name].get("status") != "PASS"
                or comparisons[name].get("relative_limit") != 1.0e-11
                for name in ("raw_tensor", "oriented_tensor")
            )
            or not isinstance(comparisons.get("K_G_J_L"), Mapping)
            or set(comparisons["K_G_J_L"]) != {"K", "G", "J", "L"}
            or any(
                comparisons["K_G_J_L"][name].get("status") != "PASS"
                or comparisons["K_G_J_L"][name].get("relative_limit") != 1.0e-11
                for name in ("K", "G", "J", "L")
            )
            or not isinstance(comparisons.get("R_T_S"), Mapping)
            or set(comparisons["R_T_S"]) != {"R", "T", "S"}
            or any(
                comparisons["R_T_S"][name].get("status") != "PASS"
                or comparisons["R_T_S"][name].get("relative_limit") != 1.0e-11
                for name in ("R", "T", "S")
            )
            or not isinstance(comparisons.get("strict_lu"), Mapping)
            or comparisons["strict_lu"].get("passed") is not True
            or comparisons["strict_lu"].get("relative_limit") != 1.0e-11
            or comparisons.get("condensation_defects_classification") != "diagnostic_only"
        ):
            raise ValueError(
                "V6 prefix sample has a failed/malformed tensor/Schur screen "
                "or mislabeled diagnostic_only defects"
            )
        for defect_name in ("reference_condensation_defects_relative", "candidate_condensation_defects_relative"):
            defects = comparisons.get(defect_name)
            if (
                not isinstance(defects, Mapping)
                or set(defects) != {"KR_plus_G", "TK_plus_J"}
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not np.isfinite(value)
                    or value < 0.0
                    for value in defects.values()
                )
            ):
                raise ValueError("V6 prefix sample has invalid diagnostic condensation defects")
    if saved_count != 2 or oracle_count != 6:
        raise ValueError("V6 prefix qualification must use two saved V4 keys and six missing-key oracles")
    return "PREFIX_QUALIFIED" if require_qualified else "PREFIX_QUALIFIED_INVENTORY"


def _task41_validate_v6_actual_qmetric_audit(
    identity_audit: Mapping[str, Any],
    *,
    require_prefix_qualified: bool = False,
) -> None:
    """Check the source, table, geometry, and compiler profile recorded by V6."""
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        CACHE_IDENTITY_SCHEMA,
        DIMENSION,
        EXPECTED_C_CACHE_SHA256,
        EXPECTED_C_SOURCE_BYTES,
        EXPECTED_C_SOURCE_SHA256,
        EXPECTED_STATIC_TABLE_EXTENTS,
        EXPECTED_GEOMETRY_TABLE_NAMES,
        EXPECTED_UFCX_MODULE_SHA256,
        EXPECTED_UFCX_SIGNATURE,
        FEATURE_NAMES,
        GEOMETRY_ORACLE_TRACE_SCHEMA,
        HELPER_COMPILER_FLAGS,
        IDENTITY,
        INTEGRAL_BODY_BY_TAG,
        POINT_BLOCK_SIZE,
        POINT_COUNT,
        PROFILE_TAGS,
        MAX_GEOMETRY_ORACLE_COMPARISONS,
        QUALIFICATION_STATUS,
        REQUIRED_GEOMETRY_TRACE_FIELDS,
        _cache_identity_digest,
    )

    candidate = identity_audit.get("candidate_evaluator_audit")
    if not isinstance(candidate, Mapping):
        raise ValueError("V6 candidate report omits its evaluator audit")
    prefix_qualification = candidate.get("prefix_qualification")
    prefix_state = _task41_validate_v6_prefix_qualification(
        prefix_qualification,
        require_qualified=require_prefix_qualified,
    )
    helper = candidate.get("geometry_helper")
    if not isinstance(helper, Mapping):
        raise ValueError("V6 candidate report omits its frozen geometry-helper audit")
    source_path = Path(str(helper.get("source_path", "")))
    cache_path = Path(str(helper.get("compile_metadata_path", "")))
    source_hash = str(helper.get("source_sha256", ""))
    cache_hash = str(helper.get("compile_metadata_sha256", ""))
    helper_source_hash = str(helper.get("helper_source_sha256", ""))
    helper_library_hash = str(helper.get("helper_library_sha256", ""))
    reference_hashes = helper.get("reference_table_hashes")
    reference_zero_counts = helper.get("reference_table_zero_counts")
    reference_zero_hashes = helper.get("reference_table_zero_pattern_hashes")
    static_extents = helper.get("static_table_declared_extents")
    geometry_trace_fields = helper.get("geometry_trace_fields")
    feature_pairs = helper.get("feature_pair_map")
    cache_payload = candidate.get("cache_identity_payload")
    cache_identity = str(candidate.get("cache_identity", ""))
    cache_identity_sha256 = str(candidate.get("cache_identity_sha256", ""))
    evaluator_source_path = Path(str(candidate.get("evaluator_source_path", "")))
    evaluator_source_hash = (
        sha256_file(evaluator_source_path)
        if evaluator_source_path.is_file()
        else ""
    )
    expected_pairs = {(left, right) for left in range(12) for right in range(12)}
    observed_pairs = (
        {tuple(pair) for pair in feature_pairs}
        if isinstance(feature_pairs, list)
        and all(
            isinstance(pair, list)
            and len(pair) == 2
            and all(type(index) is int for index in pair)
            for pair in feature_pairs
        )
        else set()
    )
    expected_body_map = {str(tag): digest for tag, digest in INTEGRAL_BODY_BY_TAG.items()}
    expected_extents = {
        name: list(shape) for name, shape in EXPECTED_STATIC_TABLE_EXTENTS.items()
    }
    reference_table_bytes = (
        len(FEATURE_NAMES) * POINT_COUNT * DIMENSION * np.dtype(np.float64).itemsize
        + POINT_COUNT * np.dtype(np.float64).itemsize
    )
    geometry_table_bytes = sum(
        int(np.prod(EXPECTED_STATIC_TABLE_EXTENTS[name], dtype=np.int64))
        * np.dtype(np.float64).itemsize
        for name in EXPECTED_GEOMETRY_TABLE_NAMES
    ) * len(set(INTEGRAL_BODY_BY_TAG.values()))
    expected_cache_payload = {
        "schema": CACHE_IDENTITY_SCHEMA,
        "implementation": IDENTITY,
        "evaluator_source_sha256": candidate.get("evaluator_source_sha256"),
        "ffcx_c_source_sha256": EXPECTED_C_SOURCE_SHA256,
        "ffcx_compile_metadata_sha256": EXPECTED_C_CACHE_SHA256,
        "ffcx_module_sha256": EXPECTED_UFCX_MODULE_SHA256,
        "ufcx_signature": EXPECTED_UFCX_SIGNATURE,
        "reference_table_source_sha256": EXPECTED_C_SOURCE_SHA256,
        "integral_body_by_tag": expected_body_map,
        "table_extent_contract": {
            "FE0": [1, 1, POINT_COUNT, DIMENSION],
            "FE2": [1, 1, POINT_COUNT, 8],
            "weights": [POINT_COUNT],
        },
        "compiler_flags": list(HELPER_COMPILER_FLAGS),
        "geometry_oracle_trace_schema": GEOMETRY_ORACLE_TRACE_SCHEMA,
    }
    oracle_count = helper.get("original_kernel_oracle_execution_count")
    oracle_status = helper.get("original_kernel_oracle_execution_status")
    oracle_artifact_bytes = helper.get("original_kernel_oracle_artifact_bytes")
    oracle_compile_audits = helper.get("original_kernel_oracle_compile_audits")
    oracle_records = candidate.get("original_kernel_oracle_records")
    geometry_records = candidate.get("geometry_oracle_comparison_records")
    valid_oracle_inventory = (
        type(oracle_count) is int
        and 0 <= oracle_count <= MAX_GEOMETRY_ORACLE_COMPARISONS
        and isinstance(oracle_artifact_bytes, int)
        and 0 <= oracle_artifact_bytes <= 512 * 1024**2
        and isinstance(oracle_compile_audits, Mapping)
        and isinstance(oracle_records, list)
        and len(oracle_records) == oracle_count
        and isinstance(geometry_records, list)
        and len(geometry_records) == oracle_count
    )
    if valid_oracle_inventory:
        allowed_digests = set(INTEGRAL_BODY_BY_TAG.values())
        valid_oracle_inventory = set(oracle_compile_audits).issubset(allowed_digests)
        audited_artifact_bytes = 0
        for digest, compile_audit in oracle_compile_audits.items():
            if not isinstance(compile_audit, Mapping):
                valid_oracle_inventory = False
                break
            source_bytes = compile_audit.get("source_bytes")
            library_bytes = compile_audit.get("library_bytes")
            if (
                type(source_bytes) is not int
                or not 0 < source_bytes <= 2 * EXPECTED_C_SOURCE_BYTES
                or type(library_bytes) is not int
                or library_bytes <= 0
                or compile_audit.get("compile_metadata_sha256") != EXPECTED_C_CACHE_SHA256
                or not re.fullmatch(r"[0-9a-f]{64}", str(compile_audit.get("source_sha256", "")))
                or not re.fullmatch(r"[0-9a-f]{64}", str(compile_audit.get("library_sha256", "")))
                or not isinstance(compile_audit.get("compiler_flags"), list)
                or not isinstance(compile_audit.get("command"), list)
                or any(
                    not isinstance(compile_audit.get(key), (int, float))
                    or not np.isfinite(compile_audit.get(key))
                    or compile_audit.get(key) < 0
                    for key in ("source_generation_seconds", "compiler_seconds")
                )
            ):
                valid_oracle_inventory = False
                break
            audited_artifact_bytes += source_bytes + library_bytes
        if audited_artifact_bytes != oracle_artifact_bytes:
            valid_oracle_inventory = False
        for index, record in enumerate(oracle_records):
            geometry_record = geometry_records[index]
            if not isinstance(record, Mapping) or not isinstance(geometry_record, Mapping):
                valid_oracle_inventory = False
                break
            tag = record.get("tag")
            body_digest = INTEGRAL_BODY_BY_TAG.get(tag) if type(tag) is int else None
            tensor_comparison = record.get("tensor_comparison")
            geometry_comparison = record.get("geometry_comparison")
            times = (
                "kernel_call_seconds",
                "output_allocation_seconds",
                "source_generation_seconds",
                "compiler_seconds",
                "candidate_build_seconds",
            )
            if (
                tag not in PROFILE_TAGS
                or body_digest not in oracle_compile_audits
                or record.get("execution_status") != "EXECUTED_BOUNDED_ORIGINAL_KERNEL_ORACLE"
                or type(record.get("q_begin")) is not int
                or type(record.get("q_end")) is not int
                or not 0 <= record["q_begin"] < record["q_end"] <= POINT_COUNT
                or any(
                    not isinstance(record.get(key), (int, float))
                    or not np.isfinite(record.get(key))
                    or record.get(key) < 0
                    for key in times
                )
                or not isinstance(tensor_comparison, Mapping)
                or tensor_comparison.get("relative_limit") != 1.0e-11
                or tensor_comparison.get("status")
                != ("PASS_SCREEN" if tensor_comparison.get("relative_frobenius", np.inf) <= 1.0e-11 else "FAIL_SCREEN")
                or any(
                    not isinstance(tensor_comparison.get(key), (int, float))
                    or not np.isfinite(tensor_comparison.get(key))
                    or tensor_comparison.get(key) < 0
                    for key in ("relative_frobenius", "absolute_frobenius", "max_abs")
                )
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("original_tensor_sha256", "")))
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("candidate_tensor_sha256", "")))
                or not isinstance(geometry_comparison, Mapping)
                or geometry_comparison.get("status") not in {"BITWISE_EQUAL", "MISMATCH"}
                or geometry_record.get("tag") != tag
                or geometry_record.get("q_begin") != record.get("q_begin")
                or geometry_record.get("q_end") != record.get("q_end")
                or geometry_record.get("status") != geometry_comparison.get("status")
                or record.get("compile_audit") != oracle_compile_audits.get(body_digest)
            ):
                valid_oracle_inventory = False
                break
    if valid_oracle_inventory and oracle_count == 0:
        valid_oracle_inventory = (
            oracle_status == "NOT_RUN_NO_WINDOW_APPROVAL"
            and oracle_artifact_bytes == 0
            and not oracle_compile_audits
            and prefix_state == "P0_NOT_RUN_NO_WINDOW_APPROVAL"
            and not require_prefix_qualified
        )
    elif valid_oracle_inventory:
        valid_oracle_inventory = (
            oracle_status == "EXECUTED_BOUNDED_ORIGINAL_KERNEL_ORACLE"
            and bool(oracle_compile_audits)
            and (
                prefix_state
                not in {"PREFIX_QUALIFIED", "PREFIX_QUALIFIED_INVENTORY"}
                or oracle_count == 6
            )
            and (
                not require_prefix_qualified
                or (oracle_count == 6 and prefix_state == "PREFIX_QUALIFIED")
            )
        )
    if not valid_oracle_inventory:
        raise ValueError("V6 bounded original-kernel oracle inventory is malformed")
    cache_identity_digest = _cache_identity_digest(expected_cache_payload)
    if (
        candidate.get("implementation") != IDENTITY
        or candidate.get("qualification_status") != QUALIFICATION_STATUS
        or candidate.get("expected_ufcx_signature") != EXPECTED_UFCX_SIGNATURE
        or candidate.get("full_form_signature") != EXPECTED_UFCX_SIGNATURE
        or candidate.get("ffcx_module_sha256") != EXPECTED_UFCX_MODULE_SHA256
        or candidate.get("ffcx_default_kernel_absent") is not True
        or candidate.get("point_block_size") != POINT_BLOCK_SIZE
        or candidate.get("workspace_bytes_upper") != 1024**3
        or candidate.get("prepare_workspace_bytes_upper") != 1024**3
        or candidate.get("key_workspace_bytes_upper") != 128 * 1024**2
        or candidate.get("class_timing_metadata_bytes_upper") != 16 * 1024**2
        or candidate.get("helper_scratch_bytes_upper") != 128 * 1024**2
        or candidate.get("original_kernel_oracle_scratch_bytes_upper") != 512 * 1024**2
        or type(candidate.get("class_timing_metadata_bytes")) is not int
        or not 0 <= candidate.get("class_timing_metadata_bytes", -1)
        <= candidate.get("class_timing_metadata_bytes_upper", 0)
        or not isinstance(candidate.get("phase_seconds_by_stage"), Mapping)
        or set(candidate.get("phase_seconds_by_stage", {}))
        != {"geometry", "pack", "gram", "scatter", "release"}
        or any(
            not isinstance(value, (int, float))
            or not np.isfinite(value)
            or value < 0
            for value in candidate.get("phase_seconds_by_stage", {}).values()
        )
        or not isinstance(candidate.get("class_seconds_summary"), Mapping)
        or candidate.get("class_seconds_summary", {}).get("count")
        != candidate.get("class_count")
        or not isinstance(candidate.get("class_seconds_summary", {}).get("total"), (int, float))
        or not isinstance(candidate.get("class_seconds_summary", {}).get("max"), (int, float))
        or candidate.get("class_seconds_summary", {}).get("total", -1) < 0
        or candidate.get("class_seconds_summary", {}).get("max", -1) < 0
        or candidate.get("class_seconds_summary", {}).get("max", 0)
        > candidate.get("class_seconds_summary", {}).get("total", 0)
        or not isinstance(helper.get("helper_source_bytes"), int)
        or helper.get("helper_source_bytes", -1) < 0
        or not isinstance(helper.get("helper_library_bytes"), int)
        or helper.get("helper_library_bytes", -1) < 0
        or helper.get("helper_scratch_retained_bytes")
        != helper.get("helper_source_bytes", 0) + helper.get("helper_library_bytes", 0)
        or helper.get("helper_scratch_retained_bytes", 0) > 128 * 1024**2
        or candidate.get("cache_identity_payload") != expected_cache_payload
        or cache_identity_sha256 != cache_identity_digest
        or cache_identity != f"{IDENTITY}:{cache_identity_digest}"
        or identity_audit.get("candidate_evaluator_cache_identity") != cache_identity
        or candidate.get("evaluator_source_path") is None
        or not Path(str(candidate.get("evaluator_source_path"))).is_absolute()
        or not re.fullmatch(r"[0-9a-f]{64}", str(candidate.get("evaluator_source_sha256", "")))
        or evaluator_source_hash != candidate.get("evaluator_source_sha256")
        or candidate.get("mass_coefficient_conjugated") is not False
        or candidate.get("hermitian_assumption") is not False
        or candidate.get("raw_tensor_built_before_original_schur") is not True
        or not source_path.is_absolute()
        or source_path.suffix != ".c"
        or cache_path != Path(str(source_path) + ".cached")
        or helper.get("source_bytes") != EXPECTED_C_SOURCE_BYTES
        or source_hash != EXPECTED_C_SOURCE_SHA256
        or cache_hash != EXPECTED_C_CACHE_SHA256
        or helper.get("reference_table_names") != list(FEATURE_NAMES)
        or helper.get("reference_table_bytes") != reference_table_bytes
        or helper.get("shared_table_bytes_upper")
        != reference_table_bytes + geometry_table_bytes
        or static_extents != expected_extents
        or not isinstance(reference_zero_counts, list)
        or len(reference_zero_counts) != len(FEATURE_NAMES)
        or any(type(value) is not int or not 0 <= value <= POINT_COUNT * DIMENSION for value in reference_zero_counts)
        or not isinstance(reference_zero_hashes, list)
        or len(reference_zero_hashes) != len(FEATURE_NAMES)
        or any(not re.fullmatch(r"[0-9a-f]{64}", str(item)) for item in reference_zero_hashes)
        or not isinstance(geometry_trace_fields, list)
        or not REQUIRED_GEOMETRY_TRACE_FIELDS.issubset(geometry_trace_fields)
        or helper.get("geometry_trace_source")
        != "same_frozen_FFCx_scalar_graph_as_actual_qmetric_block"
        or helper.get("original_kernel_oracle_generator")
        != "_FrozenFFCxGeometryHelper.original_kernel_oracle_source"
        or candidate.get("original_kernel_oracle_workspace_bytes_upper") != 1024**3
        or candidate.get("original_kernel_oracle_source_bytes_upper")
        != 2 * EXPECTED_C_SOURCE_BYTES
        or not isinstance(candidate.get("geometry_oracle_comparison_records"), list)
        or helper.get("quadrature_point_count") != POINT_COUNT
        or helper.get("geometry_helper_block_size") != POINT_BLOCK_SIZE
        or helper.get("geometry_expression_source")
        != "frozen_FFCx_Q907_Jacobian_and_fw_graph"
        or helper.get("geometry_shortcut_used") is not False
        or helper.get("compiler_flags") != list(HELPER_COMPILER_FLAGS)
        or candidate.get("integral_body_by_tag") != expected_body_map
        or not isinstance(feature_pairs, list)
        or len(feature_pairs) != 144
        or observed_pairs != expected_pairs
        or not isinstance(reference_hashes, list)
        or len(reference_hashes) != len(FEATURE_NAMES)
        or any(not re.fullmatch(r"[0-9a-f]{64}", str(item)) for item in reference_hashes)
        or not re.fullmatch(r"[0-9a-f]{64}", str(helper.get("reference_weight_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", helper_source_hash)
        or not re.fullmatch(r"[0-9a-f]{64}", helper_library_hash)
    ):
        raise ValueError("V6 candidate evaluator audit differs from the frozen source profile")


def _task41_v6_report_requires_prefix_qualification(report: Mapping[str, Any]) -> bool:
    """Require a passing eight-key prefix for every completed full candidate outcome."""
    return (
        report.get("candidate_numeric_status")
        in {"PASS", "ACTUAL_COORDINATES_INSUFFICIENT"}
        or report.get("status")
        in {"CANDIDATE_NUMERICAL_PASS_CHECKER_PENDING", "ACTUAL_COORDINATES_INSUFFICIENT"}
    )


def _task41_v6_global_attribution_identity_binding(
    attribution: Mapping[str, Any], identity_audit: Mapping[str, Any]
) -> None:
    """Bind optional attribution identity copies to the independently checked parent audit."""
    identity_fields = (
        "candidate_evaluator_identity",
        "candidate_evaluator_cache_identity",
    )
    parent_values = {field: identity_audit.get(field) for field in identity_fields}
    if any(not isinstance(value, str) or not value for value in parent_values.values()):
        raise ValueError("V6 global attribution parent identity_audit is incomplete")
    if any(
        field in attribution and attribution[field] != parent_values[field]
        for field in identity_fields
    ):
        raise ValueError(
            "V6 global attribution evaluator/cache identity differs from parent identity_audit"
        )


def _task41_v8_complex_pair(value: Any, label: str) -> complex:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(type(part) not in (int, float) for part in value)
        or not np.isfinite(np.asarray(value, dtype=np.float64)).all()
    ):
        raise ValueError(f"V8 {label} is not a finite real/imaginary pair")
    return complex(float(value[0]), float(value[1]))


def _task41_v8_complex_pairs(value: Any, label: str) -> np.ndarray:
    """Decode the producer's JSON list of [real, imag] coefficients."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"V8 {label} is not a sequence of real/imaginary pairs")
    return np.asarray(
        [
            _task41_v8_complex_pair(pair, f"{label}[{index}]")
            for index, pair in enumerate(value)
        ],
        dtype=np.complex128,
    )


def _task41_v8_check_selected_row_contributions(
    contributions: Mapping[str, Any], scalars: Mapping[str, complex], label: str
) -> None:
    """Check producer-owned selected-row scalars without treating arrays as scalars."""
    if not isinstance(contributions, Mapping):
        raise ValueError(f"V8 {label} omits selected scalar contributions")
    field_keys = {
        "s": "S_action",
        "rhs_i": "local_reduced_rhs_T_b_i",
        "T_r_i": "T_r_i",
        "delta_t": "delta_t_cell",
        "Q": "Q_cell",
        "Q_regrouped": "Q_regrouped_cell",
    }
    for field, report_key in field_keys.items():
        value = _task41_v8_complex_pair(contributions.get(report_key), report_key)
        _task41_v8_assert_close(value, scalars[field], f"{label} scalar {report_key}")
    # projected_T_r_i is intentionally absent here: the producer saves it as
    # an array in signed_action_artifacts, and the caller checks that array.
    for report_key, scalar_name in (
        ("projected_actual_trace", "delta_t"),
        ("projected_Q", "Q"),
        ("projected_Q_regrouped", "Q_regrouped"),
    ):
        _task41_v8_assert_close(
            _task41_v8_complex_pair(contributions.get(report_key), report_key),
            scalars[scalar_name],
            f"{label} scalar {report_key}",
        )


def _task41_v8_assert_close(actual: Any, expected: Any, label: str) -> None:
    left = np.asarray(actual)
    right = np.asarray(expected)
    if (
        left.shape != right.shape
        or not np.isfinite(left).all()
        or not np.isfinite(right).all()
        or not np.allclose(left, right, rtol=2.0e-12, atol=2.0e-13)
    ):
        raise ValueError(f"V8 independent replay differs from saved {label}")


def _task41_v8_lu_rhs_counterfactual(
    *,
    K: np.ndarray,
    J: np.ndarray,
    T: np.ndarray,
    b_i: np.ndarray,
    factor: tuple[np.ndarray, np.ndarray],
    selected_local_rows: np.ndarray,
    selected_coefficients: np.ndarray,
) -> dict[str, Any]:
    """Compare saved T @ b_i with -J @ solve(K, b_i) for one saved cell RHS."""
    from scipy.linalg import lu_solve

    counterfactual_started = time.perf_counter()
    K = np.asarray(K, dtype=np.complex128)
    J = np.asarray(J, dtype=np.complex128)
    T = np.asarray(T, dtype=np.complex128)
    rhs = np.asarray(b_i, dtype=np.complex128)
    rows = np.asarray(selected_local_rows, dtype=np.int64)
    coefficients = np.asarray(selected_coefficients, dtype=np.complex128)
    if (
        K.ndim != 2
        or K.shape[0] != K.shape[1]
        or J.ndim != 2
        or J.shape[1] != K.shape[0]
        or T.shape != J.shape
        or rhs.shape != (K.shape[0],)
        or rows.ndim != 1
        or coefficients.shape != rows.shape
        or rows.size == 0
        or np.any(rows < 0)
        or np.any(rows >= J.shape[0])
        or not all(np.isfinite(value).all() for value in (K, J, T, rhs, coefficients))
    ):
        raise ValueError("V8 saved RHS LU counterfactual inputs are malformed")
    solve_started = time.perf_counter()
    solution = lu_solve(factor, rhs, check_finite=True)
    solve_seconds = time.perf_counter() - solve_started
    residual = K @ solution - rhs
    residual_norm = float(np.linalg.norm(residual))
    rhs_norm = float(np.linalg.norm(rhs))
    solution_norm = float(np.linalg.norm(solution))
    backward_residual_scale = float(
        np.linalg.norm(K) * solution_norm + rhs_norm
    )
    old_vector = T @ rhs
    new_vector = -(J @ solution)
    old_projected = complex(np.vdot(coefficients, old_vector[rows]))
    new_projected = complex(np.vdot(coefficients, new_vector[rows]))
    if not np.isfinite(
        [
            residual_norm,
            rhs_norm,
            solution_norm,
            backward_residual_scale,
            old_projected.real,
            old_projected.imag,
            new_projected.real,
            new_projected.imag,
        ]
    ).all():
        raise ValueError("V8 saved RHS LU counterfactual produced non-finite values")
    delta = new_projected - old_projected
    return {
        "old_T_b_i_projected": [old_projected.real, old_projected.imag],
        "new_minus_J_solve_K_b_i_projected": [new_projected.real, new_projected.imag],
        "complex_signed_new_minus_old": [delta.real, delta.imag],
        "solve_residual_norm": residual_norm,
        "solve_residual_rhs_norm": rhs_norm,
        "solve_solution_norm": solution_norm,
        "solve_backward_residual_scale": backward_residual_scale,
        "solve_residual_relative_to_rhs": residual_norm
        / max(rhs_norm, np.finfo(np.float64).tiny),
        "solve_residual_backward_scaled": residual_norm
        / max(backward_residual_scale, 1.0),
        "solve_seconds": solve_seconds,
        "counterfactual_seconds": time.perf_counter() - counterfactual_started,
        "_solution_array": solution,
        "_residual_array": residual,
    }


def _task41_v8_lu_rhs_totals(
    *,
    native_volume_rhs: np.ndarray,
    selected_active_row: int,
    selected_original_row: int,
    selected_S_sum: complex,
    old_local_rhs_sum: complex,
    new_local_rhs_sum: complex,
) -> dict[str, Any]:
    """Combine two-cell RHS terms with the global volume RHS at its original row."""
    native = np.asarray(native_volume_rhs, dtype=np.complex128)
    if (
        native.ndim != 1
        or type(selected_active_row) is not int
        or type(selected_original_row) is not int
        or selected_active_row < 0
        or selected_original_row < 0
        or selected_original_row >= native.size
    ):
        raise ValueError("V8 local RHS totals have an invalid active/original row map")
    b_t = complex(native[selected_original_row])
    s_sum = complex(selected_S_sum)
    old_sum = complex(old_local_rhs_sum)
    new_sum = complex(new_local_rhs_sum)
    if not np.isfinite(
        [b_t.real, b_t.imag, s_sum.real, s_sum.imag, old_sum.real, old_sum.imag, new_sum.real, new_sum.imag]
    ).all():
        raise ValueError("V8 local RHS totals contain non-finite values")
    g_old = b_t + old_sum
    g_new = b_t + new_sum
    d_old = s_sum - g_old
    d_new = s_sum - g_new
    return {
        "selected_active_row": selected_active_row,
        "selected_original_row": selected_original_row,
        "original_b_t_added_once": [b_t.real, b_t.imag],
        "selected_S_sum": [s_sum.real, s_sum.imag],
        "g_old_b_t_plus_T_b_i": [g_old.real, g_old.imag],
        "g_new_b_t_plus_direct_minus_J_solve_K_b_i": [g_new.real, g_new.imag],
        "d_old_S_minus_g_old": [d_old.real, d_old.imag],
        "d_new_S_minus_g_new": [d_new.real, d_new.imag],
        "complex_signed_delta_g_new_minus_old": [
            (g_new - g_old).real,
            (g_new - g_old).imag,
        ],
        "complex_signed_delta_d_new_minus_old": [
            (d_new - d_old).real,
            (d_new - d_old).imag,
        ],
    }


def _task41_v8_local_matrix_defect_diagnostic(
    *,
    tensor: np.ndarray,
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
    R: np.ndarray,
    T: np.ndarray,
    S: np.ndarray,
) -> dict[str, Any]:
    """Measure the four saved elimination defects without imposing a new gate."""
    block = np.asarray(tensor, dtype=np.complex128)
    interior = np.asarray(interior_positions, dtype=np.int64)
    trace = np.asarray(trace_positions, dtype=np.int64)
    R = np.asarray(R, dtype=np.complex128)
    T = np.asarray(T, dtype=np.complex128)
    S = np.asarray(S, dtype=np.complex128)
    dimension = block.shape[0] if block.ndim == 2 else -1
    if (
        block.ndim != 2
        or block.shape != (dimension, dimension)
        or not np.array_equal(
            np.sort(np.concatenate((interior, trace))), np.arange(dimension)
        )
    ):
        raise ValueError("V8 local tensor partition is malformed")
    K = block[np.ix_(interior, interior)]
    G = block[np.ix_(interior, trace)]
    J = block[np.ix_(trace, interior)]
    L = block[np.ix_(trace, trace)]
    if (
        R.shape != G.shape
        or T.shape != J.shape
        or S.shape != L.shape
        or any(not np.isfinite(value).all() for value in (K, G, J, L, R, T, S))
    ):
        raise ValueError("V8 saved local matrix layouts or values are malformed")
    E_R = K @ R + G
    E_T = J + T @ K
    C_S = S - L - J @ R
    E_S = S - L - T @ G
    identity_rhs = C_S + E_T @ R - T @ E_R
    identity_residual = E_S - identity_rhs

    def metrics(values: np.ndarray) -> dict[str, float]:
        matrix = np.asarray(values, dtype=np.complex128)
        return {
            "frobenius": float(np.linalg.norm(matrix.ravel())),
            "max_abs": float(np.max(np.abs(matrix), initial=0.0)),
        }

    return {
        "E_R": metrics(E_R),
        "E_T": metrics(E_T),
        "C_S": metrics(C_S),
        "E_S": metrics(E_S),
        "E_S_identity_residual": metrics(identity_residual),
        "diagnostic_only": True,
        "new_rejection_tolerance": None,
    }


def _task41_v8_local_p3_replay(
    *,
    tensor: np.ndarray,
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
    R: np.ndarray,
    T: np.ndarray,
    S: np.ndarray,
    u_i: np.ndarray,
    t_c: np.ndarray,
    b_i: np.ndarray,
    n_i: np.ndarray,
    selected_local_rows: np.ndarray,
    selected_coefficients: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[str, complex]]:
    """Recreate the saved local P3 vectors and sparse E^H selected-row products."""
    block = np.asarray(tensor, dtype=np.complex128)
    interior = np.asarray(interior_positions, dtype=np.int64)
    trace = np.asarray(trace_positions, dtype=np.int64)
    R = np.asarray(R, dtype=np.complex128)
    T = np.asarray(T, dtype=np.complex128)
    S = np.asarray(S, dtype=np.complex128)
    u_i, t_c, b_i, n_i = (
        np.asarray(value, dtype=np.complex128) for value in (u_i, t_c, b_i, n_i)
    )
    selected_rows = np.asarray(selected_local_rows, dtype=np.int64)
    coefficients = np.asarray(selected_coefficients, dtype=np.complex128)
    dimension = block.shape[0] if block.ndim == 2 else -1
    if (
        block.ndim != 2
        or block.shape != (dimension, dimension)
        or interior.ndim != 1
        or trace.ndim != 1
        or np.intersect1d(interior, trace).size
        or not np.array_equal(
            np.sort(np.concatenate((interior, trace))), np.arange(dimension)
        )
        or u_i.shape != (len(interior),)
        or b_i.shape != u_i.shape
        or n_i.shape != u_i.shape
        or t_c.shape != (len(trace),)
        or selected_rows.ndim != 1
        or coefficients.shape != selected_rows.shape
        or selected_rows.size == 0
        or np.any(selected_rows < 0)
        or np.any(selected_rows >= len(trace))
        or np.unique(selected_rows).size != selected_rows.size
        or not np.isfinite(block).all()
        or not all(np.isfinite(value).all() for value in (R, T, S, u_i, t_c, b_i, n_i, coefficients))
    ):
        raise ValueError("V8 saved local P3 inputs or tensor partition are malformed")

    K = block[np.ix_(interior, interior)]
    G = block[np.ix_(interior, trace)]
    J = block[np.ix_(trace, interior)]
    L = block[np.ix_(trace, trace)]
    if (
        R.shape != G.shape
        or T.shape != J.shape
        or S.shape != L.shape
    ):
        raise ValueError("V8 saved local R/T/S matrix layouts differ from the oriented tensor")

    K_u = K @ u_i
    G_t = G @ t_c
    actual_i = K_u + G_t
    delta_i = actual_i - n_i
    J_u = J @ u_i
    L_t = L @ t_c
    actual_t = J_u + L_t
    S_action = S @ t_c
    local_reduced_rhs = T @ b_i
    T_r_i = T @ (b_i - n_i)
    T_delta_i = T @ delta_i
    E_S_t = S_action - L_t - T @ G_t
    E_T_u = J_u + T @ K_u
    minus_E_T_u = -E_T_u
    Q_local = T_delta_i + E_S_t - E_T_u
    Q_regrouped_local = (S - L) @ t_c - J_u - T @ n_i
    arrays = {
        "K_u": K_u,
        "G_t": G_t,
        "actual_i": actual_i,
        "delta_i": delta_i,
        "J_u": J_u,
        "L_t": L_t,
        "actual_t": actual_t,
        "S_action": S_action,
        "local_reduced_rhs": local_reduced_rhs,
        "T_r_i": T_r_i,
        "T_delta_i": T_delta_i,
        "E_S_t": E_S_t,
        "minus_E_T_u": minus_E_T_u,
        "Q_local": Q_local,
        "Q_regrouped_local": Q_regrouped_local,
    }
    weights = np.zeros(len(trace), dtype=np.complex128)
    weights[selected_rows] = coefficients
    scalar_names = {
        "s": S_action,
        "rhs_i": local_reduced_rhs,
        "T_r_i": T_r_i,
        "delta_t": actual_t,
        "Q": Q_local,
        "Q_regrouped": Q_regrouped_local,
    }
    scalars = {
        name: complex(np.vdot(weights, vector))
        for name, vector in scalar_names.items()
    }
    return arrays, scalars


TASK41_P0_V8_LEGACY_REPORT_SHA256 = "1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f"
TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA = "35fd1bbf2bca13bd17e89cc79cf7cd825b94411c"
TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256 = "a6a69b75e48572d59ae73f12a9424b06a3accdca957c6a32b5c72bcf2fb867da"
TASK41_P0_V8_SELECTED_TRACE_STAR_REPORT_SCHEMA = (
    "task41.p0.v8.selected_trace_star_audit_receipt.v1"
)


def _task41_v8_report_independent_checker_status(
    report: Mapping[str, Any], *, expected_report_sha256: str
) -> str | None:
    """Treat only the pinned pre-field V8 receipt as an explicitly not-run checker."""
    if report.get("independent_checker_status") == "NOT_RUN":
        return "NOT_RUN"
    if (
        "independent_checker_status" not in report
        and expected_report_sha256 == TASK41_P0_V8_LEGACY_REPORT_SHA256
        and report.get("schema") == TASK41_P0_V8_SELECTED_TRACE_STAR_REPORT_SCHEMA
        and report.get("status") == "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
        and report.get("geometry_policy") == "mesh_actual_exact"
        and report.get("raw_tensor_evaluator") == "actual_qmetric_blocked_gram"
        and report.get("consumer_source_sha")
        == TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA
        and report.get("consumer_contract_sha256")
        == TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256
    ):
        return "NOT_RUN"
    return None


def _task41_v8_selected_trace_star_recheck(
    report_path: Path,
    *,
    expected_report_sha256: str,
    donor: Mapping[str, Any],
    donor_contract_sha256: str,
    consumer: Mapping[str, Any],
    consumer_contract_sha256: str,
    candidate_producer_contract: Mapping[str, Any] | None,
    candidate_producer_contract_sha256: str | None,
    donor_contract: Mapping[str, Any],
    repo_root: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Recheck only hash-authorized V8 local operands and selected-row attribution."""
    from src.runners.task41_p0_v4_volume_only_audit import (
        TASK41_P0_V8_SELECTED_ACTIVE_ROW,
        TASK41_P0_V8_V6_INDEX_SHA256,
        TASK41_P0_V8_V6_REPORT_SHA256,
        TASK41_P0_V8_V7_ARRAY_SHA256,
        TASK41_P0_V8_V7_INDEX_SHA256,
    )

    report_path = Path(report_path).resolve(strict=True)
    repo_root = Path(repo_root).resolve(strict=True)
    results_root = (repo_root / "results").resolve()
    if (
        not report_path.is_relative_to(results_root)
        or not re.fullmatch(r"[0-9a-f]{64}", str(expected_report_sha256))
        or sha256_file(report_path) != expected_report_sha256
    ):
        raise ValueError("V8 report path or explicit SHA-256 differs")
    report = _json_object(report_path, "V8 selected trace-star report")
    profile = _task41_mesh_actual_exact_candidate_profile(report_path, report)
    if profile["version"] != "v8":
        raise ValueError("V8 independent checker received a different candidate profile")
    consumer_case = consumer.get("case")
    report_producer = candidate_producer_contract or consumer
    report_producer_sha256 = candidate_producer_contract_sha256 or consumer_contract_sha256
    if (
        report.get("geometry_policy") != "mesh_actual_exact"
        or report.get("raw_tensor_evaluator") != "actual_qmetric_blocked_gram"
        or report.get("donor_contract_sha256") != donor_contract_sha256
        or report.get("consumer_contract_sha256") != report_producer_sha256
        or report.get("donor_source_sha") != donor_contract.get("source", {}).get("sha")
        or report.get("consumer_source_sha") != report_producer.get("source", {}).get("sha")
        or report.get("donor_manifest_sha256") != donor.get("manifest_sha256")
        or _task41_v8_report_independent_checker_status(
            report, expected_report_sha256=expected_report_sha256
        )
        != "NOT_RUN"
        or not isinstance(consumer_case, Mapping)
    ):
        raise ValueError("V8 report donor/consumer/geometry identity differs")
    selected = report.get("selected_trace_star_audit")
    if not isinstance(selected, Mapping):
        raise ValueError("V8 report omits its selected trace-star result")
    metadata = selected.get("metadata")
    p3 = selected.get("p3_production_row_replay")
    source_replay = selected.get("saved_operand_recomposition")
    source_artifacts = (
        source_replay.get("source_artifacts")
        if isinstance(source_replay, Mapping)
        else None
    )
    if (
        selected.get("status") != "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
        or selected.get("selected_active_row") != TASK41_P0_V8_SELECTED_ACTIVE_ROW
        or not isinstance(metadata, Mapping)
        or not isinstance(p3, Mapping)
        or not isinstance(source_artifacts, Mapping)
        or p3.get("schema") != "task41.p0.v8.selected_trace_star_p3_replay.v1"
        or p3.get("complete_incident_cell_coverage") is not True
    ):
        raise ValueError("V8 selected trace-star report lacks its complete P3 receipt")

    expected_indices = {
        "v6_index": (
            repo_root
            / "docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v6_actual_qmetric_hash_index_20261021.json",
            TASK41_P0_V8_V6_INDEX_SHA256,
        ),
        "v7_index": (
            repo_root
            / "docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v7_saved_attribution_20261021.json",
            TASK41_P0_V8_V7_INDEX_SHA256,
        ),
    }
    source_documents: dict[str, tuple[Path, dict[str, Any]]] = {}
    for key, (expected_path, expected_sha) in expected_indices.items():
        path = Path(str(source_artifacts.get(key, ""))).resolve(strict=True)
        digest = source_artifacts.get(f"{key}_sha256")
        if path != expected_path.resolve() or digest != expected_sha or sha256_file(path) != expected_sha:
            raise ValueError(f"V8 frozen {key} path or SHA-256 differs")
        source_documents[key] = (path, _json_object(path, f"V8 {key}"))

    v6_index = source_documents["v6_index"][1]
    v7_index = source_documents["v7_index"][1]
    v6_payload = v6_index.get("candidate_persisted_arrays")
    v7_payload = v7_index.get("arrays")
    v7_audit = v7_index.get("audit")
    if not isinstance(v6_payload, Mapping) or not isinstance(v7_payload, Mapping) or not isinstance(v7_audit, Mapping):
        raise ValueError("V8 V6/V7 source indexes are malformed")
    v6_report_path = Path(str(source_artifacts.get("v6_report", ""))).resolve(strict=True)
    v7_report_path = Path(str(source_artifacts.get("v7_report", ""))).resolve(strict=True)
    if (
        v6_report_path != Path(str(v6_index.get("candidate_report_path", ""))).resolve()
        or not v6_report_path.is_relative_to(results_root)
        or source_artifacts.get("v6_report_sha256") != TASK41_P0_V8_V6_REPORT_SHA256
        or sha256_file(v6_report_path) != TASK41_P0_V8_V6_REPORT_SHA256
        or v7_report_path != Path(str(v7_audit.get("report_path", ""))).resolve()
        or not v7_report_path.is_relative_to(results_root)
        or source_artifacts.get("v7_report_sha256") != v7_audit.get("report_sha256")
        or sha256_file(v7_report_path) != v7_audit.get("report_sha256")
    ):
        raise ValueError("V8 V6/V7 source report path or SHA-256 differs from its index")
    v6_report = _json_object(v6_report_path, "V8 V6 source report")
    v7_report = _json_object(v7_report_path, "V8 V7 source report")
    v6_index_records = v6_payload.get("items")
    v6_report_records = v6_report.get("persisted_evidence_arrays")
    v7_index_records = v7_payload.get("records")
    if not all(isinstance(value, list) for value in (v6_index_records, v6_report_records, v7_index_records)):
        raise ValueError("V8 V6/V7 source indexes omit their array lists")
    v6_index_by_name = {item.get("name"): item for item in v6_index_records if isinstance(item, Mapping)}
    v6_report_by_name = {item.get("name"): item for item in v6_report_records if isinstance(item, Mapping)}
    v7_index_by_name = {item.get("name"): item for item in v7_index_records if isinstance(item, Mapping)}
    v6_source_arrays = source_artifacts.get("v6_arrays")
    v7_source_arrays = source_artifacts.get("v7_arrays")
    if (
        not isinstance(v6_source_arrays, Mapping)
        or not isinstance(v7_source_arrays, Mapping)
        or not v6_source_arrays
        or set(v6_source_arrays) - set(v6_index_by_name)
        or set(v6_source_arrays) - set(v6_report_by_name)
        or set(v7_source_arrays) != set(v7_index_by_name)
        or set(v7_source_arrays) != set(TASK41_P0_V8_V7_ARRAY_SHA256)
    ):
        raise ValueError("V8 explicit V6/V7 authorized-array lists differ from frozen indexes")

    def same_array_identity(left: Mapping[str, Any], right: Mapping[str, Any], basis: Path) -> bool:
        left_path = Path(str(left.get("path", "")))
        right_path = Path(str(right.get("path", "")))
        left_resolved = (left_path if left_path.is_absolute() else basis / left_path).resolve()
        right_resolved = (right_path if right_path.is_absolute() else repo_root / right_path).resolve()
        return bool(
            left.get("name") == right.get("name")
            and left_resolved == right_resolved
            and all(left.get(field) == right.get(field) for field in ("sha256", "bytes", "shape", "dtype"))
        )

    v6_basis = Path(str(v6_payload.get("path_basis", ""))).resolve(strict=True)
    if v6_basis != repo_root:
        raise ValueError("V8 V6 array index has a different path basis")
    for name, ref in v6_source_arrays.items():
        if (
            not isinstance(ref, Mapping)
            or not same_array_identity(ref, v6_index_by_name[name], v6_basis)
            or not same_array_identity(ref, v6_report_by_name[name], repo_root)
        ):
            raise ValueError(f"V8 V6 explicit array authorization differs for {name}")
    for name, ref in v7_source_arrays.items():
        expected_sha = TASK41_P0_V8_V7_ARRAY_SHA256[name]
        if (
            not isinstance(ref, Mapping)
            or not same_array_identity(ref, v7_index_by_name[name], repo_root)
            or ref.get("sha256") != expected_sha
        ):
            raise ValueError(f"V8 V7 explicit array authorization differs for {name}")

    v8_records_raw = report.get("persisted_evidence_arrays")
    if not isinstance(v8_records_raw, list):
        raise ValueError("V8 report omits its explicit saved-array inventory")
    v8_records: dict[str, Mapping[str, Any]] = {}
    for item in v8_records_raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ValueError("V8 persisted-array inventory has a malformed item")
        name = str(item["name"])
        if name in v8_records:
            raise ValueError(f"V8 persisted-array name is duplicated: {name}")
        path = Path(str(item.get("path", ""))).resolve(strict=True)
        if (
            not path.is_relative_to(report_path.parent)
            or path.stat().st_size != item.get("bytes")
            or not isinstance(item.get("sha256"), str)
            or sha256_file(path) != item.get("sha256")
        ):
            raise ValueError(f"V8 persisted-array path/hash differs for {name}")
        v8_records[name] = item

    cache: dict[tuple[str, str], np.ndarray] = {}

    def load_array_ref(ref: Any, label: str) -> np.ndarray:
        if not isinstance(ref, Mapping) or not isinstance(ref.get("name"), str):
            raise ValueError(f"V8 {label} omits its named array authorization")
        name = str(ref["name"])
        if name in v8_records:
            inventory, basis = v8_records[name], report_path.parent
            cache_key = ("v8", name)
        elif name in v6_source_arrays:
            inventory, basis = v6_source_arrays[name], v6_basis
            cache_key = ("v6", name)
        elif name in v7_source_arrays:
            inventory, basis = v7_source_arrays[name], repo_root
            cache_key = ("v7", name)
        else:
            raise ValueError(f"V8 {label} references an unauthorized array: {name}")
        if not same_array_identity(ref, inventory, basis):
            raise ValueError(f"V8 {label} identity differs from its authorized inventory")
        if cache_key not in cache:
            path = Path(str(inventory["path"]))
            path = (path if path.is_absolute() else basis / path).resolve(strict=True)
            if (
                not path.is_relative_to(results_root)
                or path.stat().st_size != inventory.get("bytes")
                or sha256_file(path) != inventory.get("sha256")
            ):
                raise ValueError(f"V8 {label} array path/hash changed: {name}")
            array = np.load(path, mmap_mode="r", allow_pickle=False)
            if (
                list(array.shape) != inventory.get("shape")
                or str(array.dtype) != inventory.get("dtype")
                or array.dtype.kind not in "fciu"
                or not np.isfinite(array).all()
            ):
                raise ValueError(f"V8 {label} array layout or values changed: {name}")
            cache[cache_key] = array
        return cache[cache_key]

    incident_order = metadata.get("incident_cell_order")
    selected_active_row = selected.get("selected_active_row")
    selected_original_row = selected.get("selected_original_row")
    if (
        not isinstance(incident_order, list)
        or not incident_order
        or any(type(cell) is not int for cell in incident_order)
        or incident_order != sorted(set(incident_order))
        or type(selected_original_row) is not int
        or metadata.get("incident_cell_count") != len(incident_order)
        or selected_active_row != TASK41_P0_V8_SELECTED_ACTIVE_ROW
    ):
        raise ValueError("V8 selected row or incident-cell map is malformed")
    columns = donor.get("columns")
    if not isinstance(columns, (list, tuple)) or len(columns) != 2:
        raise ValueError("V8 checker requires the normalized two-column saved donor")
    for column in columns:
        active = np.asarray(column["active_original_rows"])
        if (
            active.ndim != 1
            or active.dtype.kind not in "iu"
            or selected_active_row >= active.size
            or int(active[selected_active_row]) != selected_original_row
        ):
            raise ValueError("V8 selected original row does not resolve through donor map")

    numeric_records = selected.get("local_numeric_cell_identity_and_artifacts")
    selected_cells = metadata.get("selected_cells")
    per_cell_rows = p3.get("per_cell_signed_contributions")
    if not all(isinstance(value, list) for value in (numeric_records, selected_cells, per_cell_rows)):
        raise ValueError("V8 selected-star report omits local cells or P3 inputs")
    selected_by_id = {item.get("cell_index"): item for item in selected_cells if isinstance(item, Mapping)}
    numeric_by_id = {item.get("cell_index"): item for item in numeric_records if isinstance(item, Mapping)}
    p3_by_id = {item.get("cell_index"): item for item in per_cell_rows if isinstance(item, Mapping)}
    if (
        len(selected_by_id) != len(selected_cells)
        or len(numeric_by_id) != len(numeric_records)
        or len(p3_by_id) != len(per_cell_rows)
        or list(selected_by_id) != incident_order
        or set(incident_order) - set(numeric_by_id)
        or set(p3_by_id) != set(incident_order)
    ):
        raise ValueError("V8 selected-cell identity does not cover the complete incident star")

    from src.solvers.hcurl_assembly_time_condensation import _strict_local_lu

    cell_terms: dict[tuple[int, int, str, str], dict[str, complex]] = {}
    local_vector_checks = 0
    local_matrix_defects: list[dict[str, Any]] = []
    local_rhs_lu_factors: dict[tuple[int, str], dict[str, Any]] = {}
    local_rhs_lu_inputs: dict[tuple[int, str, int], np.ndarray] = {}
    local_rhs_lu_terms: dict[tuple[int, str, int], dict[str, Any]] = {}
    local_rhs_lu_solution_arrays: dict[tuple[int, str, int], dict[str, np.ndarray]] = {}
    local_rhs_lu_factorizations: list[dict[str, Any]] = []
    local_rhs_lu_state_pair_reuses = 0
    for cell_index in incident_order:
        numeric = numeric_by_id[cell_index]
        selected_map = selected_by_id[cell_index]
        if numeric.get("is_target_row_incident") is not True:
            raise ValueError("V8 numeric-cell inventory marks an incident cell as nonincident")
        local_meta = {
            key: numeric.get(key)
            for key in ("selected_local_trace_rows", "selected_trace_coefficients")
        }
        if (
            local_meta["selected_local_trace_rows"] != selected_map.get("selected_local_trace_rows")
            or local_meta["selected_trace_coefficients"] != selected_map.get("selected_trace_coefficients")
        ):
            raise ValueError(f"V8 selected-row support differs between cell {cell_index} records")
        interior_positions = np.asarray(numeric.get("true_interior_positions"), dtype=np.int64)
        trace_positions = np.asarray(numeric.get("trace_complement_positions"), dtype=np.int64)
        interior_rows = np.asarray(numeric.get("interior_original_rows"), dtype=np.int64)
        trace_rows = np.asarray(numeric.get("trace_original_rows"), dtype=np.int64)
        active_ids = np.asarray(numeric.get("active_ids"), dtype=np.int64)
        selected_local_rows = np.asarray(local_meta["selected_local_trace_rows"], dtype=np.int64)
        selected_coefficients = _task41_v8_complex_pairs(
            local_meta["selected_trace_coefficients"],
            f"cell {cell_index} selected trace coefficients",
        )
        if (
            interior_positions.ndim != 1
            or trace_positions.ndim != 1
            or interior_rows.shape != interior_positions.shape
            or trace_rows.shape != trace_positions.shape
            or active_ids.ndim != 1
            or np.intersect1d(interior_positions, trace_positions).size
            or not np.array_equal(
                np.sort(np.concatenate((interior_positions, trace_positions))),
                np.arange(len(interior_positions) + len(trace_positions)),
            )
            or selected_local_rows.size == 0
            or np.any(selected_local_rows >= len(trace_positions))
            or np.unique(selected_local_rows).size != selected_local_rows.size
            or not np.isfinite(selected_coefficients).all()
            or not np.any(selected_coefficients != 0.0)
        ):
            raise ValueError(f"V8 cell {cell_index} selected-row local partition is malformed")
        locations = np.flatnonzero(active_ids == selected_active_row)
        if locations.size != 1 or not np.array_equal(selected_local_rows, np.asarray(selected_map["selected_local_trace_rows"], dtype=np.int64)):
            raise ValueError(f"V8 cell {cell_index} active trace row is missing or duplicated")

        role_records = numeric.get("roles")
        state_records = p3_by_id[cell_index].get("roles_and_states")
        if not isinstance(role_records, list) or not isinstance(state_records, list):
            raise ValueError(f"V8 cell {cell_index} omits role/state records")
        roles_by_name = {row.get("role"): row for row in role_records if isinstance(row, Mapping)}
        if set(roles_by_name) != {"candidate", "reference"}:
            raise ValueError(f"V8 cell {cell_index} does not bind both numeric roles")
        state_lookup = {
            (row.get("column"), row.get("state")): row
            for row in state_records
            if isinstance(row, Mapping)
        }
        if set(state_lookup) != {
            (column, state) for column in range(2) for state in ("j0", "j3")
        }:
            raise ValueError(f"V8 cell {cell_index} does not bind both columns and paired states")

        for role in ("candidate", "reference"):
            role_row = roles_by_name[role]
            if (
                role_row.get("producer_identity")
                != (selected.get("candidate_identity") if role == "candidate" else "original_ffcx_reference_kernel")
                or not isinstance(role_row.get("raw_oriented_RTS_artifacts"), Mapping)
            ):
                raise ValueError(f"V8 cell {cell_index} {role} producer identity is missing")
            artifact_refs = role_row["raw_oriented_RTS_artifacts"]
            tensors = load_array_ref(artifact_refs.get("oriented_tensor"), f"cell {cell_index} {role} tensor")
            if tensors.shape != (len(interior_positions) + len(trace_positions),) * 2:
                raise ValueError(f"V8 cell {cell_index} {role} oriented tensor shape differs")
            RTS = {
                name: load_array_ref(artifact_refs.get(name), f"cell {cell_index} {role} {name}")
                for name in ("R", "T", "S")
            }
            if any(array.dtype != np.dtype(np.complex128) for array in [tensors, *RTS.values()]):
                raise ValueError(f"V8 cell {cell_index} {role} local matrices are not complex128")
            local_matrix_defects.append(
                {
                    "cell_index": cell_index,
                    "role": role,
                    **_task41_v8_local_matrix_defect_diagnostic(
                        tensor=tensors,
                        interior_positions=interior_positions,
                        trace_positions=trace_positions,
                        R=RTS["R"],
                        T=RTS["T"],
                        S=RTS["S"],
                    ),
                }
            )
            K = np.asarray(
                tensors[np.ix_(interior_positions, interior_positions)],
                dtype=np.complex128,
            )
            J = np.asarray(
                tensors[np.ix_(trace_positions, interior_positions)],
                dtype=np.complex128,
            )
            factor_key = (cell_index, role)
            if factor_key in local_rhs_lu_factors:
                raise ValueError(f"V8 local RHS diagnostic repeats LU factor {factor_key}")
            K_sha256 = hashlib.sha256(np.ascontiguousarray(K).view(np.uint8)).hexdigest()
            factor_started = time.perf_counter()
            local_factor, strict_identity_defect = _strict_local_lu(K)
            factor_seconds = time.perf_counter() - factor_started
            local_rhs_lu_factors[factor_key] = {
                "factor": local_factor,
                "K": K,
                "J": J,
                "T": RTS["T"],
                "selected_local_rows": selected_local_rows,
                "selected_coefficients": selected_coefficients,
                "K_sha256": K_sha256,
            }
            local_rhs_lu_factorizations.append(
                {
                    "cell_index": cell_index,
                    "role": role,
                    "factorization_identity": "fresh _strict_local_lu(K) from saved oriented_tensor; reused for both columns and states",
                    "K_sha256": K_sha256,
                    "oriented_tensor_sha256": artifact_refs["oriented_tensor"].get("sha256"),
                    "saved_T_sha256": artifact_refs["T"].get("sha256"),
                    "strict_identity_relative_defect": strict_identity_defect,
                    "factorization_seconds": factor_seconds,
                }
            )
            for column_index in range(2):
                donor_column = columns[column_index]
                native_volume_rhs = np.asarray(donor_column["native_volume_rhs"], dtype=np.complex128)
                native_rhs = np.asarray(donor_column["native_rhs"], dtype=np.complex128)
                for state_label in ("j0", "j3"):
                    state_row = state_lookup[(column_index, state_label)]
                    if state_row.get("native_full_rhs_at_selected_original_row") is None:
                        raise ValueError("V8 P3 state omits its native full RHS value")
                    state_role = next(
                        (
                            entry for entry in state_row.get("roles", [])
                            if isinstance(entry, Mapping) and entry.get("role") == role
                        ),
                        None,
                    )
                    if not isinstance(state_role, Mapping):
                        raise ValueError(f"V8 cell {cell_index} {role} P3 state input is absent")
                    local_values = state_role.get("local_values")
                    signed_refs = state_role.get("signed_action_artifacts")
                    if not isinstance(local_values, Mapping) or not isinstance(signed_refs, Mapping):
                        raise ValueError("V8 P3 state does not bind its local inputs/actions")
                    state = next(item for item in donor_column["states"] if item.get("label") == state_label)
                    storage = np.asarray(state["storage"], dtype=np.complex128)
                    native_action = np.asarray(state["native_volume_action"], dtype=np.complex128)
                    inputs = {
                        "u_i": load_array_ref(local_values.get("u_i"), "u_i"),
                        "t_c": load_array_ref(local_values.get("t_c"), "t_c"),
                        "b_i": load_array_ref(local_values.get("b_i"), "b_i"),
                        "n_i": load_array_ref(local_values.get("n_i"), "n_i"),
                    }
                    _task41_v8_assert_close(inputs["u_i"], storage[interior_rows], f"cell {cell_index} u_i donor slice")
                    _task41_v8_assert_close(inputs["t_c"], storage[trace_rows], f"cell {cell_index} t_c donor slice")
                    _task41_v8_assert_close(inputs["b_i"], native_volume_rhs[interior_rows], f"cell {cell_index} b_i donor slice")
                    _task41_v8_assert_close(inputs["n_i"], native_action[interior_rows], f"cell {cell_index} n_i donor slice")
                    vectors, scalars = _task41_v8_local_p3_replay(
                        tensor=tensors,
                        interior_positions=interior_positions,
                        trace_positions=trace_positions,
                        R=RTS["R"],
                        T=RTS["T"],
                        S=RTS["S"],
                        u_i=inputs["u_i"],
                        t_c=inputs["t_c"],
                        b_i=inputs["b_i"],
                        n_i=inputs["n_i"],
                        selected_local_rows=selected_local_rows,
                        selected_coefficients=selected_coefficients,
                    )
                    for name, expected in vectors.items():
                        actual = load_array_ref(signed_refs.get(name), f"cell {cell_index} {name}")
                        _task41_v8_assert_close(actual, expected, f"cell {cell_index} {name}")
                        local_vector_checks += 1
                    projected_location = int(locations[0])
                    for name, scalar_name in (
                        ("projected_actual_trace", "delta_t"),
                        ("projected_T_r_i", "T_r_i"),
                        ("projected_Q", "Q"),
                        ("projected_Q_regrouped", "Q_regrouped"),
                    ):
                        projected = load_array_ref(
                            signed_refs.get(name), f"cell {cell_index} {name}"
                        )
                        if projected.shape != (active_ids.size,):
                            raise ValueError(
                                f"V8 cell {cell_index} {name} projection layout differs"
                            )
                        _task41_v8_assert_close(
                            projected[projected_location],
                            scalars[scalar_name],
                            f"cell {cell_index} selected {name}",
                        )
                        local_vector_checks += 1
                    contributions = state_role.get("selected_row_contributions")
                    _task41_v8_check_selected_row_contributions(
                        contributions, scalars, f"cell {cell_index}"
                    )
                    rhs_key = (cell_index, role, column_index)
                    if state_label == "j0":
                        if rhs_key in local_rhs_lu_terms:
                            raise ValueError(f"V8 local RHS diagnostic duplicates {rhs_key}")
                        lu_data = local_rhs_lu_factors[(cell_index, role)]
                        rhs_diagnostic = _task41_v8_lu_rhs_counterfactual(
                            K=lu_data["K"],
                            J=lu_data["J"],
                            T=lu_data["T"],
                            b_i=inputs["b_i"],
                            factor=lu_data["factor"],
                            selected_local_rows=lu_data["selected_local_rows"],
                            selected_coefficients=lu_data["selected_coefficients"],
                        )
                        local_rhs_lu_solution_arrays[rhs_key] = {
                            "solution": rhs_diagnostic.pop("_solution_array"),
                            "residual": rhs_diagnostic.pop("_residual_array"),
                        }
                        local_rhs_lu_terms[rhs_key] = rhs_diagnostic
                        local_rhs_lu_inputs[rhs_key] = inputs["b_i"]
                        local_rhs_lu_terms[rhs_key].update(
                            {
                                "cell_index": cell_index,
                                "role": role,
                                "column": column_index,
                                "b_i_sha256": local_values["b_i"].get("sha256"),
                                "factorization_K_sha256": lu_data["K_sha256"],
                            }
                        )
                    else:
                        previous_rhs = local_rhs_lu_inputs.get(rhs_key)
                        if previous_rhs is None or not np.array_equal(
                            inputs["b_i"], previous_rhs
                        ):
                            raise ValueError(
                                f"V8 paired-state b_i differs for local RHS LU reuse {rhs_key}"
                            )
                        local_rhs_lu_state_pair_reuses += 1
                    cell_terms[(cell_index, column_index, state_label, role)] = scalars

    local_rhs_lu_cases: list[dict[str, Any]] = []
    for role in ("candidate", "reference"):
        for column_index in range(2):
            native_volume_rhs = np.asarray(
                columns[column_index]["native_volume_rhs"], dtype=np.complex128
            )
            for state_label in ("j0", "j3"):
                s_sum = sum(
                    cell_terms[(cell_index, column_index, state_label, role)]["s"]
                    for cell_index in incident_order
                )
                old_rhs_sum = sum(
                    complex(*local_rhs_lu_terms[(cell_index, role, column_index)]["old_T_b_i_projected"])
                    for cell_index in incident_order
                )
                new_rhs_sum = sum(
                    complex(*local_rhs_lu_terms[(cell_index, role, column_index)]["new_minus_J_solve_K_b_i_projected"])
                    for cell_index in incident_order
                )
                local_rhs_lu_cases.append(
                    {
                        "role": role,
                        "column": column_index,
                        "state": state_label,
                        **_task41_v8_lu_rhs_totals(
                            native_volume_rhs=native_volume_rhs,
                            selected_active_row=selected_active_row,
                            selected_original_row=selected_original_row,
                            selected_S_sum=s_sum,
                            old_local_rhs_sum=old_rhs_sum,
                            new_local_rhs_sum=new_rhs_sum,
                        ),
                        "cell_terms": [
                            local_rhs_lu_terms[(cell_index, role, column_index)]
                            for cell_index in incident_order
                        ],
                    }
                )
    local_rhs_lu_case_by_key = {
        (item["role"], item["column"], item["state"]): item
        for item in local_rhs_lu_cases
    }
    local_rhs_lu_candidate_reference_gaps = []
    for column_index in range(2):
        candidate = local_rhs_lu_case_by_key[("candidate", column_index, "j0")]
        reference = local_rhs_lu_case_by_key[("reference", column_index, "j0")]
        old_gap = np.asarray(candidate["g_old_b_t_plus_T_b_i"]) - np.asarray(
            reference["g_old_b_t_plus_T_b_i"]
        )
        new_gap = np.asarray(
            candidate["g_new_b_t_plus_direct_minus_J_solve_K_b_i"]
        ) - np.asarray(reference["g_new_b_t_plus_direct_minus_J_solve_K_b_i"])
        local_rhs_lu_candidate_reference_gaps.append(
            {
                "column": column_index,
                "state_used": "j0 (paired j3 b_i reuse is checked above)",
                "old_candidate_minus_reference_g": old_gap.tolist(),
                "new_candidate_minus_reference_g": new_gap.tolist(),
                "old_absolute_gap": float(np.linalg.norm(old_gap)),
                "new_absolute_gap": float(np.linalg.norm(new_gap)),
            }
        )
    expected_factorizations = len(incident_order) * 2
    expected_rhs_pairs = len(incident_order) * 2 * 2
    if (
        len(local_rhs_lu_factorizations) != expected_factorizations
        or len(local_rhs_lu_terms) != expected_rhs_pairs
        or local_rhs_lu_state_pair_reuses != expected_rhs_pairs
    ):
        raise ValueError("V8 saved local RHS LU counterfactual is incomplete")
    local_rhs_lu_counterfactual = {
        "schema": "task41.p0.v8.local_rhs_lu_counterfactual.v1",
        "status": "DIAGNOSTIC_ONLY",
        "source_report_sha256_rechecked": expected_report_sha256,
        "formal_candidate_or_residual_gate_changed": False,
        "production_solver_changed": False,
        "incident_cells": incident_order,
        "new_strict_lu_factorization_count": len(local_rhs_lu_factorizations),
        "direct_rhs_solve_count": len(local_rhs_lu_terms),
        "paired_state_rhs_reuse_count": local_rhs_lu_state_pair_reuses,
        "strict_factorization_seconds_sum": sum(
            row["factorization_seconds"] for row in local_rhs_lu_factorizations
        ),
        "rhs_counterfactual_seconds_sum": sum(
            row["counterfactual_seconds"] for row in local_rhs_lu_terms.values()
        ),
        "factorizations": local_rhs_lu_factorizations,
        "cases": local_rhs_lu_cases,
        "candidate_reference_gaps": local_rhs_lu_candidate_reference_gaps,
        "method": "Rebuild one strict LU per saved cell/role, reuse it for both columns; verify j0/j3 b_i equality and solve only once per pair; compare saved T @ b_i with -J @ solve(K, b_i), project by selected local-row coefficients, then add the original global b_t once.",
        "scope": "Saved incident cells only; no tensor regeneration, FE/PDE run, refinement, production change, or threshold change.",
    }

    v6_index_by_name = {str(name): value for name, value in v6_index_by_name.items()}
    v7_values = {str(name): value for name, value in v7_index_by_name.items()}

    def source_value(name: str, label: str) -> np.ndarray:
        ref = v6_source_arrays.get(name) or v7_source_arrays.get(name)
        if not isinstance(ref, Mapping):
            raise ValueError(f"V8 required saved {label} is not in its authorized source list")
        return load_array_ref(ref, label)

    active_rows = int(donor["manifest"].get("active_trace_rows", -1))
    p6_saved = source_value("task41_p0_v6_qmetric_candidate_full_p6", "V6 full_p6")
    reduced_saved = source_value("task41_p0_v6_qmetric_candidate_full_reduced_rhs", "V6 full reduced RHS")
    if p6_saved.shape[0] <= selected_active_row or reduced_saved.shape != p6_saved.shape:
        raise ValueError("V8 V6 full-row arrays have an invalid layout")
    v6_attribution: dict[tuple[int, str, str], complex] = {}
    v7_closures: dict[tuple[int, str, str], complex] = {}
    for column_index in range(2):
        for state_label in ("j0", "j3"):
            prefix = f"task41_p0_v6_qmetric_candidate_attribution_col{column_index}_{state_label}_"
            for field in ("T_r_i", "delta_t", "attributed_terms"):
                v6_attribution[(column_index, state_label, field)] = complex(
                    source_value(prefix + field, f"V6 {field}")[selected_active_row]
                )
            for kind in ("full", "volume"):
                name = f"task41_p0_v7_attribution_col{column_index}_{state_label}_corrected_{kind}_closure"
                v7_closures[(column_index, state_label, kind)] = complex(
                    source_value(name, f"V7 {kind} closure")[selected_active_row]
                )

    expected_orders = p3.get("cell_sum_orders")
    if not isinstance(expected_orders, Mapping):
        raise ValueError("V8 P3 report omits its two ordered summation maps")
    production_order = expected_orders.get("production_original_cell_order")
    observer_order = expected_orders.get("v6_eight_key_prefix_observer_order")
    prefix_order = expected_orders.get("v6_eight_key_prefix_order")
    if production_order != incident_order or not isinstance(observer_order, list) or not isinstance(prefix_order, list) or len(prefix_order) != 8:
        raise ValueError("V8 production or V6-prefix summation order differs")
    ordered_summaries = p3.get("ordered_summaries")
    if not isinstance(ordered_summaries, Mapping):
        raise ValueError("V8 P3 report omits ordered selected-row summaries")
    scalar_rows_checked = 0
    native_rhs_split_epsilon: dict[int, complex] = {}
    summary_field_map = {
        "s": "s_r_volume_sum_wH_S_t",
        "s_full": "s_r_full_volume_plus_B_alpha_once",
        "g_volume": "g_volume_r_b_t_plus_sum_wH_T_b_i",
        "d_volume_star": "d_volume_star_s_minus_g_volume",
        "g_full": "g_full_r_f_t_plus_sum_wH_T_b_i",
        "d_full_star": "d_full_star_s_plus_B_alpha_minus_g_full",
        "T_r_i": "sum_wH_T_r_i",
        "delta_t": "delta_t_original_order_starts_at_minus_native_action",
        "Q": "Q_sum_wH_attributed_terms",
        "Q_regrouped": "Q_regrouped_sum",
        "closure_volume": "v7_grouped_left_volume",
        "closure_full": "v7_grouped_left_full",
    }
    for order_name, order in (("production_original_cell_order", production_order), ("v6_eight_key_prefix_observer_order", observer_order)):
        if ordered_summaries.get(order_name) is None:
            raise ValueError(f"V8 P3 summary omits order {order_name}")
        report_rows = ordered_summaries[order_name]
        if not isinstance(report_rows, list):
            raise ValueError(f"V8 P3 summary rows are malformed for {order_name}")
        for column_index in range(2):
            donor_column = columns[column_index]
            native_v = complex(donor_column["native_volume_rhs"][selected_original_row])
            native_f = complex(donor_column["native_rhs"][selected_original_row])
            state_by_label = {item["label"]: item for item in donor_column["states"]}
            beta_rows = np.asarray(donor_column["b_alpha_rows"], dtype=np.int64)
            beta_values = np.asarray(donor_column["b_alpha_values"], dtype=np.complex128)
            beta = beta_values[beta_rows == selected_original_row]
            if beta.size > 1:
                raise ValueError("V8 donor B-alpha has duplicate selected-row entries")
            beta_value = complex(beta[0]) if beta.size else 0.0 + 0.0j
            native_rhs_split_epsilon[column_index] = native_f - native_v - beta_value
            for state_label in ("j0", "j3"):
                native_action = complex(state_by_label[state_label]["native_volume_action"][selected_original_row])
                for role in ("candidate", "reference"):
                    totals = {name: 0.0 + 0.0j for name in ("s", "rhs_i", "T_r_i", "Q", "Q_regrouped")}
                    totals["delta_t"] = -native_action
                    for cell_index in order:
                        terms = cell_terms.get((cell_index, column_index, state_label, role))
                        if terms is not None:
                            for name, value in terms.items():
                                totals[name] += value
                    s_full = totals["s"] + beta_value
                    g_volume = native_v + totals["rhs_i"]
                    g_full = native_f + totals["rhs_i"]
                    d_volume = totals["s"] - g_volume
                    d_full = s_full - g_full
                    r_volume = native_v - native_action
                    r_full = native_f - native_action - beta_value
                    d_volume_saved = complex(source_value(f"task41_v4_d_volume_trace_col{column_index}", "V6 d_volume")[selected_active_row])
                    d_full_saved = complex(p6_saved[selected_active_row, column_index] - reduced_saved[selected_active_row, column_index])
                    closure_volume = (d_volume_saved + r_volume) + totals["T_r_i"] - (totals["delta_t"] + totals["Q"])
                    closure_full = (d_full_saved + r_full) + totals["T_r_i"] - (totals["delta_t"] + totals["Q"])
                    expected_values = {
                        "s": totals["s"],
                        "s_full": s_full,
                        "g_volume": g_volume,
                        "d_volume_star": d_volume,
                        "g_full": g_full,
                        "d_full_star": d_full,
                        "T_r_i": totals["T_r_i"],
                        "delta_t": totals["delta_t"],
                        "Q": totals["Q"],
                        "Q_regrouped": totals["Q_regrouped"],
                        "closure_volume": closure_volume,
                        "closure_full": closure_full,
                    }
                    row = next(
                        (item for item in report_rows if isinstance(item, Mapping) and item.get("column") == column_index and item.get("state") == state_label and item.get("role") == role),
                        None,
                    )
                    if not isinstance(row, Mapping):
                        raise ValueError(f"V8 P3 ordered summary row is missing: {order_name}/{column_index}/{state_label}/{role}")
                    native_record = row.get("selected_row_rhs_and_action")
                    if not isinstance(native_record, Mapping):
                        raise ValueError("V8 P3 ordered summary omits its native row split")
                    for report_key, expected in (
                        ("native_volume_rhs_b_t", native_v),
                        ("native_full_rhs_f_t", native_f),
                        ("native_volume_action_n_t", native_action),
                        ("B_alpha_selected_row_applied_once", beta_value),
                    ):
                        _task41_v8_assert_close(
                            _task41_v8_complex_pair(native_record.get(report_key), report_key),
                            expected,
                            f"{order_name} {report_key}",
                        )
                    replay = row.get("production_row_replay")
                    if not isinstance(replay, Mapping):
                        raise ValueError("V8 P3 ordered summary omits production terms")
                    for name, report_key in summary_field_map.items():
                        actual = _task41_v8_complex_pair(replay.get(report_key), report_key)
                        _task41_v8_assert_close(actual, expected_values[name], f"{order_name} {report_key}")
                    if role == "candidate":
                        comparisons = row.get("saved_v6_v7_row_comparisons")
                        if not isinstance(comparisons, Mapping):
                            raise ValueError("V8 candidate P3 summary omits its V6/V7 comparisons")
                        expected_differences = {
                            "star_s_full_minus_V6_full_p6": s_full - complex(p6_saved[selected_active_row, column_index]),
                            "star_g_full_minus_V6_full_reduced_rhs": g_full - complex(reduced_saved[selected_active_row, column_index]),
                            "star_d_volume_minus_V6_d_volume": d_volume - d_volume_saved,
                            "star_d_full_minus_V6_d_full": d_full - d_full_saved,
                            "star_delta_t_minus_V6": totals["delta_t"] - v6_attribution[(column_index, state_label, "delta_t")],
                            "star_T_r_i_minus_V6": totals["T_r_i"] - v6_attribution[(column_index, state_label, "T_r_i")],
                            "star_Q_minus_V6": totals["Q"] - v6_attribution[(column_index, state_label, "attributed_terms")],
                            "recomposed_full_closure_minus_V7": closure_full - v7_closures[(column_index, state_label, "full")],
                            "recomposed_volume_closure_minus_V7": closure_volume - v7_closures[(column_index, state_label, "volume")],
                        }
                        for name, expected in expected_differences.items():
                            _task41_v8_assert_close(
                                _task41_v8_complex_pair(comparisons.get(name), name),
                                expected,
                                f"{order_name} {name}",
                            )
                    scalar_rows_checked += 1

    production_rows = ordered_summaries["production_original_cell_order"]
    old_baseline_crosschecks = []
    for case in local_rhs_lu_cases:
        summary_row = next(
            (
                item
                for item in production_rows
                if isinstance(item, Mapping)
                and item.get("column") == case["column"]
                and item.get("state") == case["state"]
                and item.get("role") == case["role"]
            ),
            None,
        )
        replay = summary_row.get("production_row_replay") if isinstance(summary_row, Mapping) else None
        if not isinstance(replay, Mapping):
            raise ValueError("V8 local RHS counterfactual cannot bind production-order baseline")
        expected_g = _task41_v8_complex_pair(
            replay.get(summary_field_map["g_volume"]), "production-order g_volume"
        )
        expected_d = _task41_v8_complex_pair(
            replay.get(summary_field_map["d_volume_star"]),
            "production-order d_volume_star",
        )
        actual_g = complex(*case["g_old_b_t_plus_T_b_i"])
        actual_d = complex(*case["d_old_S_minus_g_old"])
        _task41_v8_assert_close(
            actual_g, expected_g, "production-order local RHS counterfactual g_old"
        )
        _task41_v8_assert_close(
            actual_d, expected_d, "production-order local RHS counterfactual d_old"
        )
        old_baseline_crosschecks.append(
            {
                "order": "production_original_cell_order",
                "role": case["role"],
                "column": case["column"],
                "state": case["state"],
                "g_old_matches_existing_ordered_summary": True,
                "d_old_matches_existing_ordered_summary": True,
            }
        )
    local_rhs_lu_counterfactual["production_order_old_baseline_crosschecks"] = (
        old_baseline_crosschecks
    )

    import shutil

    from src.runners.task41_p0_v4_volume_only_audit import _persist_array

    diagnostic_output = Path(output_directory).resolve(strict=True)
    if not diagnostic_output.is_relative_to(results_root) or not diagnostic_output.is_dir():
        raise ValueError("V8 local RHS diagnostic output must be inside the registered results tree")
    planned_arrays: list[tuple[str, np.ndarray, str, dict[str, Any], str]] = []
    factor_record_by_key = {
        (row["cell_index"], row["role"]): row
        for row in local_rhs_lu_factorizations
    }
    for key, lu_data in local_rhs_lu_factors.items():
        cell_index, role = key
        factor_lu, factor_pivots = lu_data["factor"]
        planned_arrays.extend(
            (
                (
                    f"v8_lu_cell{cell_index}_{role}",
                    factor_lu,
                    "LOCAL_LU_RECONSTRUCTED_FROM_SAVED_TENSOR",
                    factor_record_by_key[key],
                    "lu_factor_artifact",
                ),
                (
                    f"v8_lu_cell{cell_index}_{role}_pivots",
                    factor_pivots,
                    "LOCAL_LU_PIVOTS",
                    factor_record_by_key[key],
                    "owned_pivots_artifact",
                ),
            )
        )
    for key, arrays in local_rhs_lu_solution_arrays.items():
        cell_index, role, column_index = key
        term_record = local_rhs_lu_terms[key]
        planned_arrays.extend(
            (
                (
                    f"v8_lu_solve_cell{cell_index}_{role}_col{column_index}_solution",
                    arrays["solution"],
                    "LOCAL_LU_SOLUTION",
                    term_record,
                    "solution_artifact",
                ),
                (
                    f"v8_lu_solve_cell{cell_index}_{role}_col{column_index}_residual",
                    arrays["residual"],
                    "LOCAL_LU_SOLVE_RESIDUAL",
                    term_record,
                    "residual_artifact",
                ),
            )
        )
    planned_array_payload_bytes = sum(int(array.nbytes) for _, array, _, _, _ in planned_arrays)
    planned_npy_header_allowance = 1024 * len(planned_arrays)
    prior_array_payload_bytes = int(selected.get("prior_array_payload_bytes", -1))
    persisted_report_bytes = int(report.get("persisted_evidence_bytes", -1))
    evidence_cap_bytes = int(report.get("evidence_cap_bytes", -1))
    free_space_floor_bytes = int(report.get("free_space_floor_bytes", -1))
    if min(
        prior_array_payload_bytes,
        persisted_report_bytes,
        evidence_cap_bytes,
        free_space_floor_bytes,
    ) < 0:
        raise ValueError("V8 report omits evidence-cap or free-space accounting")
    preflight_increment_bytes = planned_array_payload_bytes + planned_npy_header_allowance
    projected_cumulative_bytes = (
        prior_array_payload_bytes + persisted_report_bytes + preflight_increment_bytes
    )
    free_space_before_bytes = shutil.disk_usage(diagnostic_output).free
    if projected_cumulative_bytes > evidence_cap_bytes:
        raise ValueError("V8 local RHS LU artifacts exceed the report evidence cap")
    if free_space_before_bytes < preflight_increment_bytes + free_space_floor_bytes:
        raise ValueError("V8 local RHS LU artifacts would violate the report free-space floor")
    diagnostic_arrays_directory = diagnostic_output / "local_rhs_lu_counterfactual"
    diagnostic_arrays_directory.mkdir(parents=False, exist_ok=False)
    array_artifacts = []

    def persist_diagnostic_array(name: str, array: np.ndarray, *, kind: str) -> dict[str, Any]:
        record = _persist_array(
            diagnostic_arrays_directory,
            name,
            array,
            sha256_file=sha256_file,
        )
        item = {"name": name, "kind": kind, **record}
        array_artifacts.append(item)
        return item

    for name, array, kind, owner, field in planned_arrays:
        owner[field] = persist_diagnostic_array(name, array, kind=kind)
    persisted_diagnostic_bytes = sum(int(item["bytes"]) for item in array_artifacts)
    cumulative_bytes_after = (
        prior_array_payload_bytes + persisted_report_bytes + persisted_diagnostic_bytes
    )
    free_space_after_bytes = shutil.disk_usage(diagnostic_output).free
    if cumulative_bytes_after > evidence_cap_bytes:
        raise RuntimeError("V8 local RHS LU artifacts exceeded the report evidence cap after writing")
    if free_space_after_bytes < free_space_floor_bytes:
        raise RuntimeError("V8 local RHS LU artifacts violated the report free-space floor after writing")
    local_rhs_lu_counterfactual["array_directory"] = str(
        diagnostic_arrays_directory.resolve()
    )
    local_rhs_lu_counterfactual["array_artifact_count"] = len(array_artifacts)
    local_rhs_lu_counterfactual["array_artifacts"] = array_artifacts
    local_rhs_lu_counterfactual["evidence_cap_accounting"] = {
        "prior_array_payload_bytes": prior_array_payload_bytes,
        "report_persisted_evidence_bytes": persisted_report_bytes,
        "diagnostic_array_payload_bytes": planned_array_payload_bytes,
        "diagnostic_npy_header_allowance_bytes": planned_npy_header_allowance,
        "diagnostic_persisted_file_bytes": persisted_diagnostic_bytes,
        "evidence_cap_bytes": evidence_cap_bytes,
        "projected_cumulative_bytes_with_header_allowance": projected_cumulative_bytes,
        "cumulative_persisted_bytes_after_write": cumulative_bytes_after,
        "free_space_before_bytes": free_space_before_bytes,
        "free_space_after_bytes": free_space_after_bytes,
        "free_space_floor_bytes": free_space_floor_bytes,
    }

    return {
        "schema": "task41.p0.v8.selected_trace_star_independent_check.v1",
        "check_completed": True,
        "candidate_passed": None,
        "formal_candidate_or_residual_gate_changed": False,
        "report_sha256_rechecked": expected_report_sha256,
        "report_producer_source_sha": report_producer.get("source", {}).get("sha"),
        "report_producer_contract_sha256": report_producer_sha256,
        "checker_consumer_source_sha": consumer.get("source", {}).get("sha"),
        "authorized_v8_array_count": len(v8_records),
        "authorized_v6_array_count": len(v6_source_arrays),
        "authorized_v7_array_count": len(v7_source_arrays),
        "incident_cell_count": len(incident_order),
        "local_saved_vector_recomputations": local_vector_checks,
        "local_matrix_defect_diagnostics": local_matrix_defects,
        "local_rhs_lu_counterfactual": local_rhs_lu_counterfactual,
        "ordered_p3_summary_rows_recomputed": scalar_rows_checked,
        "native_rhs_split_epsilon_by_column": {
            str(column): [value.real, value.imag]
            for column, value in native_rhs_split_epsilon.items()
        },
        "recomputed_production_splits": {
            "s_full": "sum(w^H S t) + sparse B_alpha exactly once",
            "g_full": "saved native full RHS once + sum(w^H T b_i)",
            "r_full": "native full RHS - native action - sparse B_alpha exactly once",
            "closure_grouping": "(d + r) + T_r_i - (delta_t + Q)",
        },
    }


def _task41_mesh_actual_exact_candidate_recheck(
    report_path: Path,
    *,
    expected_report_sha256: str | None = None,
    donor: Mapping[str, Any],
    donor_contract_sha256: str,
    consumer: Mapping[str, Any],
    consumer_contract_sha256: str,
    donor_contract: Mapping[str, Any],
    repo_root: Path,
    candidate_producer_contract: Mapping[str, Any] | None = None,
    candidate_producer_contract_sha256: str | None = None,
    v7_evidence_directory: Path | None = None,
    diagnostic_output_directory: Path | None = None,
) -> dict[str, Any]:
    """Independently recheck persisted exact-geometry candidate vectors, without FE work."""
    report_path = Path(report_path).resolve(strict=True)
    results_root = (Path(repo_root) / "results").resolve()
    if not report_path.is_relative_to(results_root):
        raise ValueError("exact-geometry candidate report is outside the registered results tree")
    report = _json_object(report_path, "Task41 exact-geometry candidate report")
    profile = _task41_mesh_actual_exact_candidate_profile(report_path, report)
    if profile["version"] == "v8":
        if expected_report_sha256 is None or diagnostic_output_directory is None:
            raise ValueError(
                "V8 selected trace-star checker requires its report SHA-256 and consumer output directory"
            )
        return _task41_v8_selected_trace_star_recheck(
            report_path,
            expected_report_sha256=expected_report_sha256,
            donor=donor,
            donor_contract_sha256=donor_contract_sha256,
            consumer=consumer,
            consumer_contract_sha256=consumer_contract_sha256,
            candidate_producer_contract=candidate_producer_contract,
            candidate_producer_contract_sha256=candidate_producer_contract_sha256,
            donor_contract=donor_contract,
            repo_root=repo_root,
            output_directory=diagnostic_output_directory,
        )
    candidate_prefix = profile["candidate_prefix"]
    attribution_prefix = profile["attribution_prefix"]
    if profile["version"] == "v6":
        require_prefix_qualified = _task41_v6_report_requires_prefix_qualification(
            report
        )
        _task41_validate_v6_actual_qmetric_audit(
            report.get("identity_audit", {}),
            require_prefix_qualified=require_prefix_qualified,
        )
        if require_prefix_qualified:
            _task41_validate_v6_prefix_qualification(
                report.get("candidate_prefix_qualification"),
                require_qualified=True,
            )
            incident = report["candidate_prefix_qualification"].get(
                "original_failed_row_incident_contributions"
            )
            if (
                not isinstance(incident, list)
                or len(incident) != 6
                or any(
                    item.get("cell_count") != 2
                    or item.get("frozen_denominator")
                    != TASK41_P0_V5_FROZEN_DENOMINATORS[item.get("column")]
                    or not np.isfinite(
                        item.get("difference_over_frozen_denominator", np.nan)
                    )
                    for item in incident
                )
            ):
                raise ValueError(
                    "V6 candidate report omits the two saved-cell contributions on the frozen failed row"
                )
    candidate_contract = consumer
    candidate_contract_digest = consumer_contract_sha256
    if profile["version"] == "v6":
        if (
            not isinstance(candidate_producer_contract, Mapping)
            or candidate_producer_contract_sha256 is None
        ):
            raise ValueError("V6 candidate report requires its separately bound producer contract")
        candidate_contract = candidate_producer_contract
        candidate_contract_digest = candidate_producer_contract_sha256
    if (
        report.get("geometry_policy") != "mesh_actual_exact"
        or report.get("donor_contract_sha256") != donor_contract_sha256
        or report.get("consumer_contract_sha256") != candidate_contract_digest
        or report.get("donor_source_sha") != donor_contract.get("source", {}).get("sha")
        or report.get("consumer_source_sha") != candidate_contract.get("source", {}).get("sha")
        or report.get("donor_manifest_sha256") != donor.get("manifest_sha256")
        or report.get("independent_checker_status") != "NOT_RUN"
    ):
        raise ValueError("V5 candidate report donor/consumer/geometry identity differs")
    candidate_output = report.get("output_directory")
    evidence_directory = report.get("volume_evidence_directory")
    if (
        not isinstance(candidate_output, str)
        or Path(candidate_output).resolve() != report_path.parent
        or not isinstance(evidence_directory, str)
    ):
        raise ValueError("V5 candidate output directory differs from its report path")
    evidence_root = Path(evidence_directory).resolve(strict=True)
    if not evidence_root.is_relative_to(report_path.parent.resolve()):
        raise ValueError("V5 candidate evidence arrays escape the consumer output directory")
    v7_array_directory: Path | None = None
    v7_expected_bytes = 0
    v7_evidence_accounting: dict[str, Any] | None = None
    reference_path = Path(str(report.get("geometry_reference_report_path", ""))).resolve(strict=True)
    if (
        not reference_path.is_relative_to(results_root)
        or report.get("geometry_reference_report_sha256")
        != TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256
        or sha256_file(reference_path) != TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256
    ):
        raise ValueError("V5 frozen two-cell geometry reference path/hash differs")

    manifest = donor.get("manifest")
    columns = donor.get("columns")
    if not isinstance(manifest, Mapping) or not isinstance(columns, (list, tuple)) or len(columns) != 2:
        raise ValueError("V5 candidate checker requires the normalized two-column B0 donor")
    active_rows = int(manifest.get("active_trace_rows", -1))
    port_rows = int(manifest.get("port_rows", -1))
    full_rows = int(manifest.get("full_storage_rows", -1))
    if active_rows < 1 or port_rows < 0 or full_rows < 1:
        raise ValueError("V5 donor row counts are invalid")
    candidate_rows = active_rows + port_rows

    records_raw = report.get("persisted_evidence_arrays")
    if not isinstance(records_raw, list):
        raise ValueError("V5 candidate report omits persisted evidence-array records")
    records: dict[str, Mapping[str, Any]] = {}
    for item in records_raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ValueError("V5 candidate evidence-array record is malformed")
        name = str(item["name"])
        if name in records:
            raise ValueError(f"V5 candidate evidence-array name is duplicated: {name}")
        records[name] = item

    loaded: dict[str, np.ndarray] = {}

    def load_array(name: str, expected_shape: tuple[int, ...]) -> np.ndarray:
        record = records.get(name)
        if record is None:
            raise ValueError(f"V5 candidate evidence is missing array {name}")
        path = Path(str(record.get("path", ""))).resolve(strict=True)
        if (
            not path.is_relative_to(evidence_root)
            or path.stat().st_size != int(record.get("bytes", -1))
            or sha256_file(path) != record.get("sha256")
        ):
            raise ValueError(f"V5 candidate evidence path/hash differs for {name}")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if (
            array.shape != expected_shape
            or array.dtype != np.dtype(np.complex128)
            or record.get("shape") != list(expected_shape)
            or record.get("dtype") != "complex128"
        ):
            raise ValueError(f"V5 candidate evidence shape/dtype differs for {name}")
        for start in range(0, int(array.shape[0]), 262_144):
            if not np.isfinite(np.asarray(array[start : start + 262_144])).all():
                raise ValueError(f"V5 candidate evidence contains non-finite values: {name}")
        loaded[name] = array
        return array

    if profile["version"] == "v6":
        if v7_evidence_directory is None:
            raise ValueError("V7 saved checker requires a dedicated closure-array directory")
        v7_array_directory = Path(v7_evidence_directory).resolve()
        if (
            not v7_array_directory.is_relative_to(results_root)
            or v7_array_directory.is_relative_to(evidence_root)
            or v7_array_directory.is_relative_to(report_path.parent.resolve())
            or v7_array_directory.exists()
        ):
            raise ValueError("V7 closure-array output must be new and separate under results")
        unique_candidate_paths: dict[str, int] = {}
        for record in records.values():
            raw_path = Path(str(record.get("path", ""))).resolve()
            byte_count = int(record.get("bytes", -1))
            if byte_count < 0:
                raise ValueError("V6 candidate inventory has an invalid byte count")
            previous = unique_candidate_paths.setdefault(str(raw_path), byte_count)
            if previous != byte_count:
                raise ValueError("V6 candidate paths have conflicting byte counts")
        donor_bytes = int(donor.get("existing_evidence_bytes", -1))
        candidate_bytes = sum(unique_candidate_paths.values())
        if donor_bytes < 0 or (
            report.get("persisted_evidence_bytes") is not None
            and int(report["persisted_evidence_bytes"]) != candidate_bytes
        ):
            raise ValueError("V7 evidence accounting differs from donor/candidate inventories")
        v7_payload_bytes = active_rows * np.dtype(np.complex128).itemsize * 2 * 4
        v7_expected_bytes = v7_payload_bytes + 4096 * 8
        evidence_cap_bytes = 16 * 1024**3
        if donor_bytes + candidate_bytes + v7_expected_bytes > evidence_cap_bytes:
            raise MemoryError("V7 closure arrays would exceed the fixed 16 GiB evidence cap")
        import shutil

        anchor = v7_array_directory.parent
        while not anchor.exists() and anchor != anchor.parent:
            anchor = anchor.parent
        free_bytes = int(shutil.disk_usage(anchor).free)
        free_floor_bytes = 2 * 1024**3
        if free_bytes < v7_expected_bytes + free_floor_bytes:
            raise OSError("V7 closure arrays would violate the fixed 2 GiB free-space floor")
        v7_evidence_accounting = {
            "donor_bytes": donor_bytes,
            "candidate_unique_path_bytes": candidate_bytes,
            "new_closure_array_payload_bytes": v7_payload_bytes,
            "new_closure_array_bytes_expected": v7_expected_bytes,
            "cumulative_bytes_expected": donor_bytes + candidate_bytes + v7_expected_bytes,
            "evidence_cap_bytes": evidence_cap_bytes,
            "free_bytes_before_write": free_bytes,
            "free_space_floor_bytes": free_floor_bytes,
        }

    candidate_p6 = load_array(f"{candidate_prefix}_full_p6", (candidate_rows, 2))
    candidate_reduced = load_array(
        f"{candidate_prefix}_full_reduced_rhs", (candidate_rows, 2)
    )
    saved_port_rhs = np.asarray(donor["attribution"]["joint"]["port_rhs"])
    if saved_port_rhs.shape != (port_rows, 2) or saved_port_rhs.dtype != np.dtype(np.complex128):
        raise ValueError("V5 inherited donor port output has an invalid shape or dtype")
    if not (
        np.array_equal(candidate_p6[active_rows:, :], saved_port_rhs)
        and np.array_equal(candidate_reduced[active_rows:, :], saved_port_rhs)
    ):
        raise ValueError("V5 candidate changed the inherited port outputs")

    action_columns = []
    for column_index, frozen_denominator in enumerate(
        TASK41_P0_V5_FROZEN_DENOMINATORS
    ):
        difference = _task41_b0_chunked_difference_summary(
            candidate_p6[:, column_index], candidate_reduced[:, column_index]
        )
        dynamic_denominator = max(
            _task41_b0_chunked_norm(candidate_p6[:, column_index]),
            _task41_b0_chunked_norm(candidate_reduced[:, column_index]),
            np.finfo(float).tiny,
        )
        dynamic_relative = difference["absolute_l2"] / dynamic_denominator
        frozen_relative = difference["absolute_l2"] / frozen_denominator
        action_columns.append(
            {
                "column": column_index,
                "difference": difference,
                "dynamic_denominator": dynamic_denominator,
                "dynamic_denominator_relative": dynamic_relative,
                "frozen_denominator": frozen_denominator,
                "frozen_denominator_relative": frozen_relative,
                "dynamic_gate_passed": dynamic_relative
                <= TASK41_P0_V5_RELATIVE_TOLERANCE,
                "frozen_gate_passed": frozen_relative
                <= TASK41_P0_V5_RELATIVE_TOLERANCE,
            }
        )
    action_status = (
        "PASS"
        if all(
            item["dynamic_gate_passed"] and item["frozen_gate_passed"]
            for item in action_columns
        )
        else "ACTUAL_COORDINATES_INSUFFICIENT"
    )
    reported_action = report.get("identity_audit", {}).get("candidate_full_action_gate")
    if (
        not isinstance(reported_action, Mapping)
        or reported_action.get("relative_tolerance") != TASK41_P0_V5_RELATIVE_TOLERANCE
        or reported_action.get("status") != action_status
        or reported_action.get("frozen_denominators_source") != profile["denominators_source"]
        or reported_action.get("full_action_artifact") != f"{candidate_prefix}_full_p6"
        or reported_action.get("full_reduced_rhs_artifact")
        != f"{candidate_prefix}_full_reduced_rhs"
        or reported_action.get("port_rows_inherited_after_validation") is not True
        or len(reported_action.get("columns", ())) != 2
    ):
        raise ValueError("V5 candidate report action-gate classification differs from recomputation")
    for actual, recorded in zip(action_columns, reported_action["columns"], strict=True):
        if not isinstance(recorded, Mapping):
            raise ValueError("V5 candidate report action column is malformed")
        for key in ("dynamic_gate_passed", "frozen_gate_passed", "frozen_denominator"):
            if recorded.get(key) != actual[key]:
                raise ValueError(f"V5 candidate report action {key} differs from recomputation")
        for key in ("dynamic_denominator", "dynamic_denominator_relative", "frozen_denominator_relative"):
            if not np.isclose(float(recorded.get(key, np.nan)), actual[key], rtol=2e-12, atol=1e-300):
                raise ValueError(f"V5 candidate report action {key} differs from recomputation")
        recorded_difference = recorded.get("difference")
        if not isinstance(recorded_difference, Mapping) or not np.isclose(
            float(recorded_difference.get("absolute_l2", np.nan)),
            actual["difference"]["absolute_l2"],
            rtol=2e-12,
            atol=1e-300,
        ):
            raise ValueError("V5 candidate report action difference differs from recomputation")
    identity_audit = report.get("identity_audit", {})
    attribution = (
        identity_audit.get("global_geometry_native_elimination_attribution")
        if isinstance(identity_audit, Mapping)
        else None
    )
    if (
        not isinstance(attribution, Mapping)
        or attribution.get("schema") != profile["action_schema"]
        or len(attribution.get("columns", ())) != 2
        or attribution.get("global_closure_status") != "DIAGNOSTIC_ONLY"
        or attribution.get("diagnostic_scales") != [
            "left_and_right_identity_norms",
            "frozen_candidate_denominator",
            "sum_of_accumulated_term_norms",
        ]
    ):
        raise ValueError("V5 global attribution receipt is missing or malformed")
    if profile["version"] == "v6":
        _task41_v6_global_attribution_identity_binding(attribution, identity_audit)
    closure_results = []
    v7_formula_columns = []
    expected_artifact_names: set[str] = {
        f"{candidate_prefix}_full_p6",
        f"{candidate_prefix}_full_reduced_rhs",
    }
    recovery_gate = report.get("identity_audit", {}).get("candidate_recovery_gate")
    if (
        not isinstance(recovery_gate, Mapping)
        or recovery_gate.get("relative_forward_tolerance") != 1.0e-11
        or recovery_gate.get("native_volume_residual_relative_tolerance") != 1.0e-10
        or recovery_gate.get("native_volume_action_count") != 2
        or recovery_gate.get("recovery_source")
        != "saved native_volume_rhs with the current exact-geometry owner"
        or not isinstance(recovery_gate.get("columns"), list)
        or len(recovery_gate["columns"]) != 2
    ):
        raise ValueError("V5 candidate report omits the two-column affected recovery gate")
    recovery_results = []
    for column_index, (recorded, donor_column) in enumerate(
        zip(recovery_gate["columns"], columns, strict=True)
    ):
        if not isinstance(recorded, Mapping) or recorded.get("column") != column_index:
            raise ValueError("V5 candidate recovery column record is malformed")
        expected_names = {
            "recovered_storage_artifact": (
                f"{candidate_prefix}_recovered_storage_col{column_index}",
                "recovered_storage",
            ),
            "native_volume_residual_artifact": (
                f"{candidate_prefix}_native_volume_residual_col{column_index}",
                "native_volume_residual",
            ),
        }
        arrays = {}
        for field, (name, label) in expected_names.items():
            artifact = recorded.get(field)
            record = records.get(name)
            if (
                not isinstance(artifact, Mapping)
                or artifact.get("name") != name
                or not isinstance(record, Mapping)
                or any(
                    artifact.get(key) != record.get(key)
                    for key in ("path", "sha256", "bytes", "shape", "dtype")
                )
            ):
                raise ValueError(f"V5 candidate {label} artifact metadata differs")
            expected_artifact_names.add(name)
            arrays[label] = load_array(name, (full_rows,))
        known = np.asarray(donor_column["known_field"], dtype=np.complex128)
        rhs = np.asarray(donor_column["native_volume_rhs"], dtype=np.complex128)
        active_original = np.asarray(donor_column["active_original_rows"], dtype=np.int64)
        slave_rows = np.asarray(donor_column["slave_rows"], dtype=np.int64)
        recovered = arrays["recovered_storage"]
        residual = arrays["native_volume_residual"]
        if (
            known.shape != (full_rows,)
            or rhs.shape != (full_rows,)
            or active_original.shape != (active_rows,)
            or slave_rows.ndim != 1
        ):
            raise ValueError(f"V5 candidate recovery vectors have invalid donor layout in column {column_index}")
        forward = _task41_b0_chunked_difference_summary(recovered, known)
        forward_relative = forward["absolute_l2"] / max(
            _task41_b0_chunked_norm(known), np.finfo(float).tiny
        )
        residual_norm = _task41_b0_chunked_norm(residual)
        residual_relative = residual_norm / max(
            _task41_b0_chunked_norm(rhs), np.finfo(float).tiny
        )
        active_trace_exact = _task41_b0_indexed_arrays_equal(
            recovered, known, active_original
        )
        slave_rows_zero = _task41_b0_indexed_arrays_equal(
            recovered, recovered, slave_rows, zero=True
        )
        residual_slave_rows_zero = _task41_b0_indexed_arrays_equal(
            residual, residual, slave_rows, zero=True
        )
        forward_passed = bool(
            np.isfinite(forward_relative) and forward_relative <= 1.0e-11
        )
        residual_passed = bool(
            np.isfinite(residual_relative) and residual_relative <= 1.0e-10
        )
        passed = bool(
            forward_passed
            and residual_passed
            and active_trace_exact
            and slave_rows_zero
            and residual_slave_rows_zero
        )
        for key, actual in (
            ("forward_error_absolute_l2", forward["absolute_l2"]),
            ("forward_error_relative", forward_relative),
            ("native_volume_residual_absolute_l2", residual_norm),
            ("native_volume_residual_relative", residual_relative),
        ):
            if not np.isclose(float(recorded.get(key, np.nan)), actual, rtol=2e-12, atol=1e-300):
                raise ValueError(f"V5 candidate recovery {key} differs from independent recheck")
        for key, actual in (
            ("forward_gate_passed", forward_passed),
            ("native_volume_residual_gate_passed", residual_passed),
            ("active_trace_exact", active_trace_exact),
            ("slave_rows_zero", slave_rows_zero),
            ("residual_slave_rows_zero", residual_slave_rows_zero),
            ("passed", passed),
        ):
            if recorded.get(key) is not actual:
                raise ValueError(f"V5 candidate recovery {key} differs from independent recheck")
        recovery_results.append(
            {
                "column": column_index,
                "forward_error_relative": forward_relative,
                "native_volume_residual_relative": residual_relative,
                "active_trace_exact": active_trace_exact,
                "slave_rows_zero": slave_rows_zero,
                "residual_slave_rows_zero": residual_slave_rows_zero,
                "passed": passed,
            }
        )
    recovery_status = (
        "PASS" if all(item["passed"] for item in recovery_results) else "ACTUAL_COORDINATES_INSUFFICIENT"
    )
    if recovery_gate.get("status") != recovery_status:
        raise ValueError("V5 candidate recovery-gate classification differs from independent recheck")
    if v7_array_directory is not None:
        if v7_array_directory.exists():
            raise FileExistsError("V7 closure-array output directory appeared after preflight")
        import shutil

        anchor = v7_array_directory.parent
        while not anchor.exists() and anchor != anchor.parent:
            anchor = anchor.parent
        free_before_write = int(shutil.disk_usage(anchor).free)
        if free_before_write < v7_expected_bytes + 2 * 1024**3:
            raise OSError("V7 closure-array output lost its fixed 2 GiB free-space reserve")
        v7_array_directory.mkdir(parents=True, exist_ok=False)
        if v7_evidence_accounting is not None:
            v7_evidence_accounting["free_bytes_before_write"] = free_before_write
    for column_index, (column_report, donor_column) in enumerate(
        zip(attribution["columns"], columns, strict=True)
    ):
        active_original = np.asarray(donor_column["active_original_rows"], dtype=np.int64)
        native_rhs = np.asarray(donor_column["native_rhs"], dtype=np.complex128)
        native_volume_rhs = np.asarray(
            donor_column["native_volume_rhs"], dtype=np.complex128
        )
        b_alpha_rows = np.asarray(donor_column["b_alpha_rows"], dtype=np.int64)
        b_alpha_values = np.asarray(donor_column["b_alpha_values"], dtype=np.complex128)
        if (
            active_original.shape != (active_rows,)
            or native_rhs.ndim != 1
            or native_volume_rhs.shape != native_rhs.shape
            or b_alpha_rows.shape != b_alpha_values.shape
            or b_alpha_rows.ndim != 1
            or b_alpha_values.dtype != np.dtype(np.complex128)
            or not np.isfinite(b_alpha_values).all()
            or (b_alpha_rows.size and (np.any(b_alpha_rows < 0) or np.any(b_alpha_rows >= full_rows)))
        ):
            raise ValueError(f"V5 donor column {column_index} has invalid trace rows")
        donor_states = {str(item["label"]): item for item in donor_column["states"]}
        state_reports = column_report.get("states")
        if not isinstance(state_reports, list) or set(
            str(item.get("state")) for item in state_reports if isinstance(item, Mapping)
        ) != set(donor_states):
            raise ValueError(f"V5 attribution states differ in column {column_index}")
        if profile["version"] == "v6" and set(donor_states) != {"j0", "j3"}:
            raise ValueError("V7 donor attribution requires the bound j0 and j3 states")
        slave_rows = np.asarray(donor_column["slave_rows"], dtype=np.int64)
        if b_alpha_rows.size and slave_rows.size and np.isin(b_alpha_rows, slave_rows).any():
            raise ValueError("V7 saved B-alpha has support on an MPC slave row")
        _task41_b0_v7_map_original_rows_to_active(b_alpha_rows, active_original)
        nonactive_rhs_difference = _task41_b0_v7_nonactive_rhs_difference(
            native_rhs, native_volume_rhs, active_original
        )
        if profile["version"] == "v6":
            volume_d_name = f"task41_v4_d_volume_trace_col{column_index}"
            expected_artifact_names.add(volume_d_name)
            d_volume = load_array(volume_d_name, (active_rows,))
            d_full = np.asarray(candidate_p6[:active_rows, column_index]) - np.asarray(
                candidate_reduced[:active_rows, column_index]
            )
        else:
            d_volume = d_full = None
        v7_states = []
        for state_report in state_reports:
            state_label = str(state_report["state"])
            donor_state = donor_states[state_label]
            native_action = np.asarray(
                donor_state["native_volume_action"], dtype=np.complex128
            )
            if native_action.shape != native_rhs.shape:
                raise ValueError("V5 native RHS/action vectors differ in shape")
            state_storage = np.asarray(donor_state["storage"], dtype=np.complex128)
            known_field = np.asarray(donor_column["known_field"], dtype=np.complex128)
            if (
                state_storage.shape != native_rhs.shape
                or known_field.shape != native_rhs.shape
                or not _task41_b0_indexed_arrays_equal(
                    state_storage, known_field, active_original
                )
            ):
                raise ValueError("V7 donor j0/j3 state trace differs from its bound known field")
            artifact_report = state_report.get("accumulator_artifacts")
            if not isinstance(artifact_report, Mapping):
                raise ValueError("V5 attribution report omits full accumulator vectors")
            arrays = {}
            for field in ("T_r_i", "delta_t", "attributed_terms"):
                artifact = artifact_report.get(field)
                if not isinstance(artifact, Mapping) or not isinstance(artifact.get("name"), str):
                    raise ValueError(f"V5 attribution artifact {field} is malformed")
                name = str(artifact["name"])
                expected_name = f"{attribution_prefix}_col{column_index}_{state_label}_{field}"
                if name != expected_name:
                    raise ValueError("V5 attribution artifact name is not bound to its column/state")
                expected_artifact_names.add(name)
                record = records.get(name)
                if not isinstance(record, Mapping) or any(
                    artifact.get(key) != record.get(key)
                    for key in ("path", "sha256", "bytes", "shape", "dtype")
                ):
                    raise ValueError(f"V5 attribution artifact record differs for {name}")
                arrays[field] = load_array(name, (active_rows,))
            lhs_sq = rhs_sq = error_sq = 0.0
            accumulated_term_norm_squares = [0.0] * 5
            max_abs = 0.0
            for start in range(0, active_rows, 262_144):
                stop = min(active_rows, start + 262_144)
                d = np.asarray(candidate_p6[start:stop, column_index]) - np.asarray(
                    candidate_reduced[start:stop, column_index]
                )
                r_t = (
                    native_rhs[active_original[start:stop]]
                    - native_action[active_original[start:stop]]
                )
                t_r_i = np.asarray(arrays["T_r_i"][start:stop])
                delta_t = np.asarray(arrays["delta_t"][start:stop])
                attributed_terms = np.asarray(arrays["attributed_terms"][start:stop])
                lhs = d + r_t + t_r_i
                rhs = delta_t + attributed_terms
                difference = lhs - rhs
                if not all(np.isfinite(value).all() for value in (lhs, rhs, difference)):
                    raise ValueError("V5 attribution closure contains non-finite values")
                lhs_sq += float(np.vdot(lhs, lhs).real)
                rhs_sq += float(np.vdot(rhs, rhs).real)
                error_sq += float(np.vdot(difference, difference).real)
                for term_index, term in enumerate((d, r_t, t_r_i, delta_t, attributed_terms)):
                    accumulated_term_norm_squares[term_index] += float(np.vdot(term, term).real)
                if difference.size:
                    max_abs = max(max_abs, float(np.max(np.abs(difference))))
            closure_l2 = float(np.sqrt(max(0.0, error_sq)))
            lhs_l2 = float(np.sqrt(max(0.0, lhs_sq)))
            rhs_l2 = float(np.sqrt(max(0.0, rhs_sq)))
            frozen_relative = closure_l2 / TASK41_P0_V5_FROZEN_DENOMINATORS[column_index]
            accumulation_scale = float(
                sum(np.sqrt(max(0.0, value)) for value in accumulated_term_norm_squares)
            )
            accumulation_relative = closure_l2 / max(accumulation_scale, np.finfo(float).tiny)
            recorded_closure = state_report.get("closure_difference")
            if (
                not isinstance(recorded_closure, Mapping)
                or not np.isclose(
                    float(recorded_closure.get("absolute_l2", np.nan)),
                    closure_l2,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(recorded_closure.get("max_abs", np.nan)),
                    max_abs,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("left_d_plus_r_t_plus_T_r_i_l2", np.nan)),
                    lhs_l2,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("right_delta_t_plus_local_defects_l2", np.nan)),
                    rhs_l2,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("closure_frozen_denominator", np.nan)),
                    TASK41_P0_V5_FROZEN_DENOMINATORS[column_index],
                    rtol=0.0,
                    atol=0.0,
                )
                or not np.isclose(
                    float(state_report.get("closure_frozen_denominator_relative", np.nan)),
                    frozen_relative,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("accumulation_scale_l2_sum", np.nan)),
                    accumulation_scale,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("closure_relative_to_accumulation_scale", np.nan)),
                    accumulation_relative,
                    rtol=2e-12,
                    atol=1e-300,
                )
            ):
                raise ValueError("V5 global closure diagnostics differ from independent vector recheck")
            closure_results.append(
                {
                    "column": column_index,
                    "state": state_label,
                    "absolute_l2": closure_l2,
                    "max_abs": max_abs,
                    "left_l2": lhs_l2,
                    "right_l2": rhs_l2,
                    "frozen_denominator": TASK41_P0_V5_FROZEN_DENOMINATORS[column_index],
                    "frozen_denominator_relative": frozen_relative,
                    "accumulation_scale": accumulation_scale,
                    "relative_to_accumulation_scale": accumulation_relative,
                }
            )
            if profile["version"] != "v6":
                continue
            reduce_volume_name = (
                f"task41_v4_reduce_r_volume_{state_label}_col{column_index}"
            )
            reduce_full_name = f"task41_v4_reduce_r_full_{state_label}_col{column_index}"
            expected_artifact_names.update((reduce_volume_name, reduce_full_name))
            formula = _task41_b0_v7_attribution_state_recheck(
                candidate_d_full=d_full,
                candidate_d_volume=d_volume,
                active_original_rows=active_original,
                native_rhs=native_rhs,
                native_volume_rhs=native_volume_rhs,
                b_alpha_rows=b_alpha_rows,
                b_alpha_values=b_alpha_values,
                native_volume_action=native_action,
                T_r_i=arrays["T_r_i"],
                delta_t=arrays["delta_t"],
                attributed_terms=arrays["attributed_terms"],
                reduce_r_volume=load_array(reduce_volume_name, (active_rows,)),
                reduce_r_full=load_array(reduce_full_name, (active_rows,)),
                frozen_denominator=TASK41_P0_V5_FROZEN_DENOMINATORS[column_index],
                evidence_directory=v7_array_directory,
                evidence_prefix=(
                    f"task41_p0_v7_attribution_col{column_index}_{state_label}"
                    if profile["version"] == "v6"
                    else None
                ),
            )
            v7_states.append(
                {
                    "state": state_label,
                    "diagnostics": formula["diagnostics"],
                    "epsilon_rhs_native_minus_volume_minus_Balpha": formula[
                        "epsilon_rhs_native_minus_volume_minus_Balpha"
                    ],
                    "legacy_closure_beta_active_l2": formula[
                        "legacy_closure_beta_active_l2"
                    ],
                    "legacy_beta_conjugate_inner_product": formula[
                        "legacy_beta_conjugate_inner_product"
                    ],
                    "persisted_closure_arrays": formula["persisted_closure_arrays"],
                    "_d_hat_volume": formula["_d_hat_volume"],
                    "_d_hat_full": formula["_d_hat_full"],
                }
            )
        state_consistency = {}
        if len(v7_states) == 2:
            left_state, right_state = v7_states
            state_consistency = {
                "d_hat_volume_between_donor_states": _task41_b0_chunked_difference_summary(
                    left_state["_d_hat_volume"], right_state["_d_hat_volume"]
                ),
                "d_hat_full_between_donor_states": _task41_b0_chunked_difference_summary(
                    left_state["_d_hat_full"], right_state["_d_hat_full"]
                ),
            }
        rhs_split_receipt = (
            v7_states[0]["epsilon_rhs_native_minus_volume_minus_Balpha"]
            if v7_states
            else None
        )
        surface_support = donor.get("manifest", {}).get(
            "saved_surface_support_certificate", {}
        )
        interior_rhs_identity_verified = bool(
            profile["version"] == "v6"
            and nonactive_rhs_difference["absolute_l2"] == 0.0
            and isinstance(surface_support, Mapping)
            and surface_support.get("cell_interior_nonzero_values") == 0
            and donor.get("manifest", {}).get("local_interior_Bi_Di_exact_zero") is True
        )
        for state in v7_states:
            state.pop("_d_hat_volume")
            state.pop("_d_hat_full")
        v7_formula_columns.append(
            {
                "column": column_index,
                "states": v7_states,
                "same_trace_donor_state_consistency": state_consistency,
                "B_alpha_rows_map_once_to_active_trace": profile["version"] == "v6",
                "interior_f_equals_b_verified": interior_rhs_identity_verified,
                "interior_rhs_identity_basis": {
                    "native_rhs_minus_native_volume_rhs_on_nonactive_rows": nonactive_rhs_difference,
                    "full_rhs_split_epsilon_absolute_l2": rhs_split_receipt.get("absolute_l2")
                    if isinstance(rhs_split_receipt, Mapping)
                    else None,
                    "saved_cell_interior_nonzero_values": surface_support.get(
                        "cell_interior_nonzero_values"
                    )
                    if isinstance(surface_support, Mapping)
                    else None,
                    "local_interior_Bi_Di_exact_zero": donor.get("manifest", {}).get(
                        "local_interior_Bi_Di_exact_zero"
                    ),
                },
                "candidate_initial_recovery_is_separate": True,
            }
        )
    if set(records) & expected_artifact_names != expected_artifact_names:
        raise ValueError("V5 candidate report is missing independently consumed evidence arrays")
    closure_status = "DIAGNOSTIC_ONLY"
    candidate_status = (
        "PASS" if action_status == "PASS" and recovery_status == "PASS"
        else "ACTUAL_COORDINATES_INSUFFICIENT"
    )
    if report.get("candidate_numeric_status") != candidate_status:
        raise ValueError("V5 candidate numeric status differs from independent action/recovery recheck")
    run_status = (
        "CANDIDATE_NUMERICAL_PASS_CHECKER_PENDING"
        if candidate_status == "PASS"
        else "ACTUAL_COORDINATES_INSUFFICIENT"
    )
    if report.get("status") != run_status or attribution.get("global_closure_status") != closure_status:
        raise ValueError("V5 candidate/action or attribution-diagnostic classification differs from independent recheck")
    if v7_array_directory is not None and v7_evidence_accounting is not None:
        closure_records = [
            record
            for column in v7_formula_columns
            for state in column["states"]
            for record in state["persisted_closure_arrays"].values()
        ]
        actual_new_bytes = sum(int(record["bytes"]) for record in closure_records)
        if actual_new_bytes > v7_expected_bytes or len(closure_records) != 8:
            raise ValueError("V7 corrected closure array inventory differs from its preflight")
        v7_evidence_accounting.update(
            {
                "new_closure_array_bytes_actual": actual_new_bytes,
                "cumulative_bytes_actual": int(v7_evidence_accounting["donor_bytes"])
                + int(v7_evidence_accounting["candidate_unique_path_bytes"])
                + actual_new_bytes,
                "closure_array_bytes_expected_upper": v7_expected_bytes,
                "closure_array_records": closure_records,
                "evidence_directory": str(v7_array_directory),
            }
        )
    return {
        "schema": profile["check_schema"],
        "check_completed": True,
        "report_classification_matches": True,
        "action_status": action_status,
        "action_passed": action_status == "PASS",
        "recovery_status": recovery_status,
        "recovery_passed": recovery_status == "PASS",
        "recovery_columns": recovery_results,
        "attribution_closure_status": closure_status,
        "attribution_closure_passed": None,
        "candidate_passed": candidate_status == "PASS",
        "candidate_status": candidate_status,
        "action_columns": action_columns,
        "global_closure_states": closure_results,
        "attribution_v7_formula_recheck": {
            "schema": "task41.p0.v7.saved_full_volume_attribution_recheck.v1",
            "independently_recomputed_from_hash_bound_arrays": True,
            "legacy_global_closure_preserves_v6_formula": True,
            "corrected_full_residual": "native_rhs_trace - native_volume_action_trace - B_alpha_trace",
            "corrected_volume_residual": "native_volume_rhs_trace - native_volume_action_trace",
            "corrected_full_identity": "d_full + r_full_trace + T_r_i = delta_t + attributed_terms",
            "corrected_volume_identity": "d_volume + r_volume_trace + T_r_i = delta_t + attributed_terms",
            "formula_status": "DIAGNOSTIC_ONLY"
            if profile["version"] == "v6"
            else "NOT_APPLICABLE_V5",
            "columns": v7_formula_columns,
            "evidence_accounting": v7_evidence_accounting,
        },
        "candidate_report_path": str(report_path),
        "candidate_report_sha256": sha256_file(report_path),
        "candidate_producer_source_sha": candidate_contract.get("source", {}).get("sha"),
        "candidate_producer_contract_sha256": candidate_contract_digest,
        "checker_consumer_source_sha": consumer.get("source", {}).get("sha"),
        "checker_consumer_contract_sha256": consumer_contract_sha256,
        "geometry_reference_report_sha256": TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
        "candidate_arrays_rehashed_and_reopened": True,
        "port_outputs_inherited_unchanged": True,
    }


def check_task41_p0_b0_saved_evidence_audit(
    *,
    summary_path: Path,
    numerical_output: Path,
    contract_path: Path,
    contract_sha256: str,
    consumer_contract_path: Path,
    consumer_contract_sha256: str,
    output_path: Path,
    repo_root: Path,
    mesh_actual_exact_report_path: Path | None = None,
    mesh_actual_exact_report_sha256: str | None = None,
) -> dict[str, Any]:
    """Audit producer arrays read-only under a separately bound consumer window/source."""
    if (mesh_actual_exact_report_path is None) != (mesh_actual_exact_report_sha256 is None):
        raise ValueError("saved B0 candidate report requires both explicit path and SHA-256")
    donor, donor_digest = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=False,
    )
    consumer, consumer_digest = require_task41_p0_contract(
        consumer_contract_path,
        expected_sha256=consumer_contract_sha256,
        current_root=repo_root,
        check_current_source=True,
        require_clean_source=True,
        case_id="B0",
    )
    donor_case = donor.get("case")
    consumer_case = consumer.get("case")
    if (
        not isinstance(donor_case, Mapping)
        or not isinstance(consumer_case, Mapping)
        or task41_case_id_for_run_id(str(donor_case.get("run_id", ""))) != "B0"
        or task41_case_id_for_run_id(str(consumer_case.get("run_id", ""))) != "B0"
    ):
        raise ValueError("saved B0 audit requires frozen B0 donor and consumer contracts")
    for key in (
        "model_id",
        "method",
        "mpi_size",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
    ):
        if donor_case.get(key) != consumer_case.get(key):
            raise ValueError(f"saved B0 donor/consumer contracts differ at {key}")

    summary_path = summary_path.resolve(strict=True)
    donor_directory = summary_path.parent
    numerical_output = numerical_output.resolve()
    expected_numerical_output = donor_directory / "numerical_output"
    if numerical_output != expected_numerical_output or (
        numerical_output.exists() and not numerical_output.is_dir()
    ):
        raise ValueError(
            "saved B0 donor numerical-output path differs from its bound logical child"
        )
    output_path = output_path.resolve()
    output_root = (repo_root / "results").resolve()
    if (
        summary_path.name != "task40_v10_p6_candidate_summary.json"
        or not output_path.is_relative_to(output_root)
        or output_path.is_relative_to(donor_directory)
        or output_path.name != "task41_p0_b0_saved_evidence_audit.json"
        or output_path.exists()
        or output_path.with_name(output_path.name + ".tmp").exists()
    ):
        raise ValueError("saved B0 audit output must be a new file in a separate consumer result directory")

    run_manifest_path = donor_directory / "run_manifest.json"
    if not run_manifest_path.is_file():
        raise ValueError("saved B0 donor run manifest is missing")
    run_manifest = _json_object(run_manifest_path, "saved B0 donor run manifest")
    launcher_summary_path = donor_directory / "run_summary.json"
    launcher_summary = _json_object(launcher_summary_path, "saved B0 donor run summary")
    summary = _json_object(summary_path, "saved B0 donor candidate summary")
    expected_manifest = {
        "run_id": donor_case.get("run_id"),
        "model_id": donor_case.get("model_id"),
        "method": donor_case.get("method"),
        "mpi_size": donor_case.get("mpi_size"),
        "input_sha256": donor_case.get("input_sha256"),
        "physical_model_sha256": donor_case.get("physical_model_sha256"),
        "resolved_config_sha256": donor_case.get("resolved_config_sha256"),
        "source_sha": donor.get("source", {}).get("sha")
        if isinstance(donor.get("source"), Mapping)
        else None,
    }
    if any(run_manifest.get(key) != value for key, value in expected_manifest.items()):
        raise ValueError("saved B0 donor manifest differs from its frozen producer contract")
    if (
        summary.get("run_id") != donor_case.get("run_id")
        or launcher_summary.get("run_id") != donor_case.get("run_id")
        or Path(str(run_manifest.get("output_directory", ""))).resolve() != donor_directory
        or Path(str(run_manifest.get("numerical_output_directory", ""))).resolve()
        != numerical_output
        or Path(str(launcher_summary.get("output_directory", ""))).resolve()
        != donor_directory
        or Path(str(launcher_summary.get("numerical_output_directory", ""))).resolve()
        != numerical_output
    ):
        raise ValueError("saved B0 donor summaries and numerical-output path differ")
    input_path = donor_directory / "input_original.dat"
    config_path = donor_directory / "resolved_config.json"
    if (
        not input_path.is_file()
        or sha256_file(input_path) != donor_case.get("input_sha256")
        or not config_path.is_file()
        or sha256_file(config_path) != donor_case.get("resolved_config_sha256")
    ):
        raise ValueError("saved B0 donor input/config identity differs from its frozen contract")

    evidence = _task41_b0_recovery_evidence_checks(
        summary,
        numerical_output,
        donor,
        contract_sha256=donor_digest,
        checkpoint_path=output_path,
        checkpoint_identity={
            "donor_contract_sha256": donor_digest,
            "donor_source_sha": donor.get("source", {}).get("sha"),
            "donor_window_sha256": donor.get("window", {}).get("sha256"),
            "consumer_contract_sha256": consumer_digest,
            "consumer_source_sha": consumer.get("source", {}).get("sha"),
            "consumer_window_sha256": consumer.get("window", {}).get("sha256"),
        },
    )
    mesh_actual_candidate_check = None
    candidate_producer_contract = None
    candidate_producer_contract_sha256 = None
    if mesh_actual_exact_report_path is not None:
        candidate_producer_contract, candidate_producer_contract_sha256 = (
            _task41_v6_candidate_producer_contract(
                mesh_actual_exact_report_path,
                expected_report_sha256=str(mesh_actual_exact_report_sha256),
                consumer_contract=consumer,
                repo_root=repo_root,
            )
        )
        normalized_donor = load_task41_v4_volume_only_donor(
            summary_path=summary_path, numerical_output=numerical_output
        )
        mesh_actual_candidate_check = _task41_mesh_actual_exact_candidate_recheck(
            mesh_actual_exact_report_path,
            expected_report_sha256=mesh_actual_exact_report_sha256,
            donor=normalized_donor,
            donor_contract_sha256=donor_digest,
            donor_contract=donor,
            consumer=consumer,
            consumer_contract_sha256=consumer_digest,
            repo_root=repo_root,
            candidate_producer_contract=candidate_producer_contract,
            candidate_producer_contract_sha256=candidate_producer_contract_sha256,
            v7_evidence_directory=(
                output_path.with_name(output_path.stem + "_v7_attribution_arrays")
            ),
            diagnostic_output_directory=output_path.parent,
        )
    audit_completed = bool(evidence.get("audit_completed") is True) and (
        mesh_actual_candidate_check is None
        or mesh_actual_candidate_check.get("check_completed") is True
    )
    payload = {
        "schema": "task41.p0.b0.saved_evidence_audit.v1",
        "status": "COMPLETE" if audit_completed else "INCOMPLETE",
        "audit_completed": audit_completed,
        "data_integrity": evidence.get("data_integrity") is True,
        "recovery_passed": evidence.get("recovery_passed") is True,
        "joint_action_passed": evidence.get("joint_action_passed"),
        "qualification_passed": evidence.get("qualification_passed") is True,
        "official_result": False,
        "donor": {
            "run_id": donor_case.get("run_id"),
            "source_sha": donor.get("source", {}).get("sha"),
            "contract_sha256": donor_digest,
            "window_sha256": donor.get("window", {}).get("sha256"),
            "run_directory": str(donor_directory),
            "run_manifest_sha256": sha256_file(run_manifest_path),
            "launcher_summary_sha256": sha256_file(launcher_summary_path),
            "candidate_summary_sha256": sha256_file(summary_path),
            "launcher_result_classification": launcher_summary.get("result_classification"),
        },
        "consumer": {
            "run_id": consumer_case.get("run_id"),
            "source_sha": consumer.get("source", {}).get("sha"),
            "contract_sha256": consumer_digest,
            "window_sha256": consumer.get("window", {}).get("sha256"),
        },
        "recovery_evidence_recheck": evidence,
        **(
            {"mesh_actual_exact_candidate_check": mesh_actual_candidate_check}
            if mesh_actual_candidate_check is not None
            else {}
        ),
        "checkpoints": evidence.get("checkpoints", []),
        "raw_evidence_retained": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output_path)
    return payload


def _task41_b0_numerical_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    contract: Mapping[str, Any],
    *,
    contract_path: Path,
    contract_sha256: str,
    repo_root: Path,
) -> dict[str, Any]:
    """Reopen B0's identity-bound all-mode and q-map records independently."""
    from src.solvers import task41_b0_mode_inventory as inventory_module
    from src.solvers.task41_b0_mode_inventory import TASK41_B0_MODE_COUNT

    errors: list[str] = []
    case = contract.get("case", {})
    window = contract.get("window", {})
    authority = summary.get("campaign_authority", {})
    if not isinstance(case, Mapping) or not isinstance(window, Mapping):
        return {"errors": ["Task41 B0 contract case/window is malformed"]}
    if not isinstance(authority, Mapping):
        authority = {}
    from src.runners.task41_p0_contract import task41_raw_artifact_limit_bytes

    expected_raw_limit = task41_raw_artifact_limit_bytes(contract)
    if contract.get("evidence", {}).get("raw_disk_policy") is not None and (
        summary.get("raw_artifact_limit_bytes") != expected_raw_limit
        or authority.get("raw_artifact_limit_bytes") != expected_raw_limit
    ):
        errors.append("Task41 B0 raw evidence limit differs from its approved contract")
    expected_identity = {
        "run_id": TASK41_B0_RUN_ID,
        "profile": TASK41_B0_PRECONDITIONER,
        "stage": "TASK41_B0",
        "source_sha": contract.get("source", {}).get("sha")
        if isinstance(contract.get("source"), Mapping)
        else None,
    }
    for key, expected in expected_identity.items():
        if summary.get(key) != expected:
            errors.append(f"Task41 B0 candidate summary {key} differs from the fixed contract")
    if (
        case.get("run_id") != TASK41_B0_RUN_ID
        or case.get("profile_identity") != TASK41_B0_PRECONDITIONER
        or case.get("solver_stage") != "TASK41_B0"
        or case.get("comparison_group") != TASK41_B0_COMPARISON_GROUP
        or case.get("geometry_identity") != TASK41_B0_GEOMETRY_IDENTITY
        or case.get("method") != "full3d_iterative"
        or contract.get("comparison") is not None
        or contract.get("q_csr_reuse") is not None
    ):
        errors.append("Task41 B0 fixed contract has a changed identity or donor binding")
    expected_window_path = (repo_root / str(window.get("path", ""))).resolve()
    if (
        authority.get("case_id") != "B0"
        or Path(str(authority.get("task41_contract_path", ""))).resolve()
        != contract_path.resolve()
        or authority.get("task41_contract_sha256") != contract_sha256
        or authority.get("source_sha") != expected_identity["source_sha"]
        or authority.get("campaign_window_sha256") != window.get("sha256")
        or Path(str(authority.get("campaign_window_path", ""))).resolve()
        != expected_window_path
    ):
        errors.append("Task41 B0 campaign authority differs from the fixed contract/window")
    abi_facts = summary.get("abi")
    runtime_contract = contract.get("runtime")
    if (
        not isinstance(abi_facts, Mapping)
        or not isinstance(runtime_contract, Mapping)
        or runtime_contract.get("profile") != "native_linux"
        or abi_facts.get("profile_identity") != TASK41_B0_PRECONDITIONER
        or abi_facts.get("runtime_profile") != runtime_contract.get("profile")
        or abi_facts.get("receipt_sha256")
        != runtime_contract.get("abi_receipt_sha256")
        or abi_facts.get("qualification")
        != "task41_p0_contract_receipt_bound"
        or abi_facts.get("scalar") != "complex128"
        or abi_facts.get("integer") != "int32"
        or abi_facts.get("mpi_size") != 1
    ):
        errors.append(
            "Task41 B0 mode-manifest ABI identity differs from the frozen native contract receipt"
        )
    if (
        summary.get("precision_status") != "NOT_QUALIFIED"
        or summary.get("mode_truncation_status") != "MODE_TRUNCATION_UNQUALIFIED"
        or summary.get("comparison_authority") is not None
        or "task41_a1_a2_comparison" in summary
        or summary.get("live_mode_inventory_status") != "LIVE_CAPTURED_AND_HASH_VERIFIED"
    ):
        errors.append("Task41 B0 qualification labels or no-comparison status changed")

    inventory = summary.get("b0_mode_inventory")
    periodic = summary.get("periodic_inventory_expectations")
    if not isinstance(inventory, Mapping) or not isinstance(periodic, Mapping):
        return {"errors": errors + ["Task41 B0 summary omits its live inventory/profile"]}
    run_directory = numerical_output.parent.resolve()
    b0_profile_capability = None
    try:
        b0_profile_capability = inventory_module.recheck_task41_b0_mode_inventory(
            run_directory,
            inventory,
            source_sha=str(expected_identity["source_sha"]),
            input_sha256=str(case.get("input_sha256", "")),
            abi_facts=abi_facts,
        )
        if (
            periodic.get("name") != TASK41_B0_PRECONDITIONER
            or periodic.get("name") != b0_profile_capability["identity"]
            or periodic.get("q_count") != b0_profile_capability["q_count"]
            or periodic.get("mode_count") != b0_profile_capability["mode_count"]
            or periodic.get("q_port_counts") != b0_profile_capability["q_port_counts"]
            or periodic.get("sector_port_counts")
            != b0_profile_capability["sector_port_counts"]
            or summary.get("b0_profile_capability") != b0_profile_capability
        ):
            errors.append("Task41 B0 periodic profile differs from the reopened mode/q capability")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"Task41 B0 verified profile capability failed: {exc}")
    q_counts = (
        b0_profile_capability.get("q_port_counts")
        if isinstance(b0_profile_capability, Mapping)
        else None
    )
    sector_counts = (
        b0_profile_capability.get("sector_port_counts")
        if isinstance(b0_profile_capability, Mapping)
        else None
    )

    iterative_reference_recheck = None
    recovery_evidence_recheck = None
    reference_tier_recheck = None
    output_packet_recheck = None
    post_release_recheck = None
    factor_release_recheck = None
    power_recheck = None
    if (
        summary.get("status") != "PASS"
        or summary.get("official_result") is not True
        or summary.get("numeric_gates_passed") is not True
        or summary.get("output_gates_passed") is not True
        or summary.get("solver_status") != "TRUE_RESIDUAL_PASS"
        or summary.get("comparison_authority") is not None
        or "task41_a1_a2_comparison" in summary
    ):
        errors.append("Task41 B0 worker result or no-comparison outcome did not pass")
    try:
        iterative_reference_recheck = _task41_iterative_reference_audit_checks(
            summary,
            numerical_output,
            repo_root=repo_root,
            case_id="B0",
            b0_profile_capability=b0_profile_capability,
        )
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        errors.append(f"Task41 B0 iterative CSR/factor audit failed: {exc}")
    recovery_evidence_recheck = _task41_b0_recovery_evidence_checks(
        summary,
        numerical_output,
        contract,
        contract_sha256=contract_sha256,
    )
    errors.extend(recovery_evidence_recheck["errors"])

    output_meta = summary.get("output_packet")
    output_packet_path = None
    if (
        isinstance(output_meta, Mapping)
        and isinstance(output_meta.get("arrays"), Mapping)
        and isinstance(output_meta["arrays"].get("path"), str)
    ):
        output_npz = Path(str(output_meta["arrays"]["path"])).resolve()
        output_packet_path = output_npz.with_suffix(".json")
        if (
            output_npz.parent != run_directory
            or output_packet_path.parent != run_directory
            or not output_packet_path.is_file()
        ):
            errors.append("Task41 B0 official output packet escaped its run directory or is missing")
    else:
        errors.append("Task41 B0 worker summary omits its official output packet")
    if output_packet_path is not None and b0_profile_capability is not None:
        try:
            from src.runners.task40_v10_output_checker import (
                _verify_v31_reference_tiers,
                verify_v10_output_bundle,
            )

            output_packet = _json_object(output_packet_path, "B0 official output packet")
            output_packet_recheck = verify_v10_output_bundle(
                output_packet_path, expected_channel_count=TASK41_B0_MODE_COUNT
            )
            if output_packet_recheck.get("status") != "PASS":
                errors.append("Task41 B0 official output packet checker did not pass")
            reference_tier_recheck = _verify_v31_reference_tiers(
                summary.get("regular_inverse_checks", {}),
                expected_profile=TASK41_B0_PRECONDITIONER,
                b0_profile_capability=b0_profile_capability,
            )
            if (
                reference_tier_recheck.get("case_count") != 6
                or reference_tier_recheck.get("passed") is not True
            ):
                errors.append("Task41 B0 six full FE/port startup reference cases did not pass")
            power = summary.get("power")
            if not isinstance(power, Mapping):
                raise ValueError("Task41 B0 worker summary omits R/T/A/A_volume")
            power_values = {
                name: float(power.get(name, np.nan))
                for name in ("R", "T", "A", "A_volume")
            }
            closure = abs(power_values["R"] + power_values["T"] + power_values["A_volume"] - 1.0)
            absorption = abs(power_values["A"] - power_values["A_volume"])
            power_recheck = {
                "R_T_A_A_volume": power_values,
                "R_plus_T_plus_A_volume_minus_one": closure,
                "A_minus_A_volume": absorption,
                "limit": 1.0e-5,
                "passed": bool(
                    np.isfinite(list(power_values.values())).all()
                    and closure <= 1.0e-5
                    and absorption <= 1.0e-5
                    and abs(closure - float(summary.get("energy_closure_absolute", np.nan)))
                    <= 1.0e-12
                    and abs(
                        absorption - float(summary.get("absorption_consistency_absolute", np.nan))
                    )
                    <= 1.0e-12
                    and output_packet.get("passed") is True
                ),
            }
            if not power_recheck["passed"]:
                errors.append("Task41 B0 R/T/A/A_volume physical energy gate did not pass")
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            errors.append(f"Task41 B0 output/reference-tier recheck failed: {exc}")

    post_meta = summary.get("post_release_final_residual_packet")
    if isinstance(post_meta, Mapping) and isinstance(post_meta.get("arrays"), Mapping):
        post_npz = Path(str(post_meta["arrays"].get("path", ""))).resolve()
        post_json = post_npz.with_suffix(".json")
        if post_npz.parent != run_directory or post_json.parent != run_directory:
            errors.append("Task41 B0 post-release A6 packet escaped its run directory")
        else:
            try:
                from src.runners.task40_v10_output_checker import (
                    verify_saved_full_a6_residual_packet,
                )

                post_release_recheck = verify_saved_full_a6_residual_packet(
                    post_json,
                    expected_identity={
                        key: (
                            summary.get("scientific_identity", {}).get(key)
                            if isinstance(summary.get("scientific_identity"), Mapping)
                            else None
                        )
                        for key in ("source_sha", "input_sha256", "physical_model_sha256")
                    },
                    expected_reference_factors_released=True,
                )
            except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                errors.append(f"Task41 B0 post-release full A6 residual recheck failed: {exc}")
    else:
        errors.append("Task41 B0 worker summary omits its post-release full A6 packet")

    release = summary.get("b0_factor_release_audit")
    if not isinstance(release, Mapping) or (
        release.get("cleanup_status") != "DESTROYED"
        or release.get("destroyed") is not True
        or release.get("cleanup_failed") is not False
        or release.get("factors_live_count_current") != 0
        or release.get("matrices_live_count_current") != 0
        or release.get("cleanup_last_attempt_failures") != []
        or release.get("unconfirmed_owner_tags") != []
        or release.get("max_simultaneous_factors") != 200
        or release.get("all_q_factor_objects_live_simultaneously") is not True
    ):
        errors.append("Task41 B0 All-Q factors were not independently recorded as released")
    else:
        factor_release_recheck = {
            "cleanup_status": release["cleanup_status"],
            "factors_live_count_current": release["factors_live_count_current"],
            "matrices_live_count_current": release["matrices_live_count_current"],
            "max_simultaneous_factors": release["max_simultaneous_factors"],
            "all_q_factor_objects_live_simultaneously": True,
            "passed": True,
        }
    return {
        "schema": "task41.p0.b0_inventory_recheck.v1",
        "errors": errors,
        "mode_manifest_sha256": (
            b0_profile_capability.get("mode_manifest_sha256")
            if isinstance(b0_profile_capability, Mapping)
            else inventory.get("mode_manifest_sha256")
            if isinstance(inventory, Mapping)
            else None
        ),
        "mode_count": (
            b0_profile_capability.get("mode_count")
            if isinstance(b0_profile_capability, Mapping)
            else inventory.get("mode_count")
            if isinstance(inventory, Mapping)
            else TASK41_B0_MODE_COUNT
        ),
        "q_count": 200,
        "sector_count": 100,
        "q_port_counts_recomputed": q_counts,
        "sector_port_counts_recomputed": sector_counts,
        "verified_profile_capability": b0_profile_capability,
        "iterative_reference_recheck": iterative_reference_recheck,
        "recovery_evidence_recheck": recovery_evidence_recheck,
        "reference_tier_recheck": reference_tier_recheck,
        "output_packet_recheck": output_packet_recheck,
        "post_release_a6_recheck": post_release_recheck,
        "factor_release_recheck": factor_release_recheck,
        "power_recheck": power_recheck,
        "passed": not errors,
    }


def check_task41_p0(
    *,
    input_path: Path,
    summary_path: Path,
    manifest_path: Path,
    numerical_output: Path,
    contract_path: Path,
    contract_sha256: str,
    output_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    contract, contract_digest = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        check_current_source=True,
        require_clean_source=True,
    )
    case = contract["case"]
    case_id = task41_case_id_for_run_id(str(case.get("run_id", "")))
    source_sha = contract["source"]["sha"]
    specification = load_and_resolve(input_path)
    validate_task41_specification(
        specification, input_path, contract, current_root=repo_root
    )
    input_path = input_path.resolve()
    summary_path = summary_path.resolve()
    manifest_path = manifest_path.resolve()
    numerical_output = numerical_output.resolve()
    output_path = output_path.resolve()
    if input_path != (repo_root / case["input_path"]).resolve():
        raise ValueError("checker input path differs from the frozen Task41 DAT")
    if summary_path.parent != manifest_path.parent:
        raise ValueError("run summary and manifest do not share the same run directory")
    manifest = _json_object(manifest_path, "run manifest")
    launcher_summary = _json_object(summary_path, "launcher summary")
    output_summary_path = (
        summary_path.parent / "task40_v10_p6_candidate_summary.json"
        if case_id in {"A2", "B0"}
        else numerical_output / "run_summary.json"
    )
    output_summary = _json_object(output_summary_path, "full numerical summary")
    run_directory = summary_path.parent
    expected_output_dir = Path(str(manifest.get("output_directory", ""))).resolve()
    expected_numerical_output = Path(
        str(manifest.get("numerical_output_directory", ""))
    ).resolve()
    if (
        summary_path != run_directory / "run_summary.json"
        or manifest_path != run_directory / "run_manifest.json"
        or expected_output_dir != run_directory
        or expected_numerical_output != numerical_output
        or Path(str(launcher_summary.get("output_directory", ""))).resolve() != run_directory
        or Path(str(launcher_summary.get("numerical_output_directory", ""))).resolve()
        != numerical_output
        or launcher_summary.get("run_id") != case["run_id"]
    ):
        raise ValueError("persisted run summary, manifest, and numerical-output paths disagree")
    expected_manifest = {
        "model_id": case["model_id"],
        "run_id": case["run_id"],
        "method": case["method"],
        "mpi_size": case["mpi_size"],
        "input_sha256": case["input_sha256"],
        "physical_model_sha256": case["physical_model_sha256"],
        "resolved_config_sha256": case["resolved_config_sha256"],
        "source_sha": source_sha,
    }
    identity_errors = [
        f"run manifest {key} differs from the Task41 contract"
        for key, expected in expected_manifest.items()
        if manifest.get(key) != expected
    ]
    copied_input = run_directory / "input_original.dat"
    resolved_config = run_directory / "resolved_config.json"
    if not copied_input.is_file() or sha256_file(copied_input) != case["input_sha256"]:
        identity_errors.append("copied original DAT is missing or has a different hash")
    if (
        not resolved_config.is_file()
        or hashlib.sha256(resolved_config.read_bytes()).hexdigest()
        != case["resolved_config_sha256"]
    ):
        identity_errors.append("saved resolved configuration is missing or has a different hash")
    a2_rechecks = None
    b0_rechecks = None
    if case_id == "A2":
        a2_rechecks = _task41_a2_numerical_checks(
            output_summary,
            numerical_output,
            contract,
            repo_root=repo_root,
        )
        numerical_errors = list(a2_rechecks["errors"])
    elif case_id == "B0":
        b0_rechecks = _task41_b0_numerical_checks(
            output_summary,
            numerical_output,
            contract,
            contract_path=contract_path,
            contract_sha256=contract_digest,
            repo_root=repo_root,
        )
        numerical_errors = list(b0_rechecks["errors"])
    else:
        numerical_errors = evaluate_task41_numerical_summary(output_summary, numerical_output)
    errors = identity_errors + numerical_errors
    passed = not errors
    payload = {
        "schema": (
            A2_CHECKER_SCHEMA
            if case_id == "A2"
            else B0_CHECKER_SCHEMA
            if case_id == "B0"
            else CHECKER_SCHEMA
        ),
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "PASS" if passed else "FAIL",
        "checker_passed": passed,
        "full_pass": passed,
        "official_result": passed,
        "task_id": contract["task_id"],
        "run_id": case["run_id"],
        "source_sha": source_sha,
        "contract_sha256": contract_digest,
        "window_path": str((repo_root / contract["window"]["path"]).resolve()),
        "window_sha256": contract["window"]["sha256"],
        "input_sha256": case["input_sha256"],
        "physical_model_sha256": case["physical_model_sha256"],
        "resolved_config_sha256": case["resolved_config_sha256"],
        "run_manifest_sha256": sha256_file(manifest_path),
        "launcher_summary_sha256": sha256_file(summary_path),
        "numerical_summary_sha256": sha256_file(output_summary_path),
        "launcher_result_classification": launcher_summary.get("result_classification"),
        **({"a2_independent_rechecks": a2_rechecks} if a2_rechecks is not None else {}),
        **({"b0_independent_rechecks": b0_rechecks} if b0_rechecks is not None else {}),
        "errors": errors,
        "raw_evidence_retained": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input", type=Path)
    mode.add_argument("--saved-output-continuation-input", type=Path)
    mode.add_argument("--saved-b0-evidence-audit", action="store_true")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--numerical-output", type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--consumer-contract", type=Path)
    parser.add_argument("--consumer-contract-sha256")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mesh-actual-exact-report", type=Path)
    parser.add_argument("--mesh-actual-exact-report-sha256")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.saved_b0_evidence_audit:
        if (
            args.input is not None
            or args.saved_output_continuation_input is not None
            or args.manifest is not None
            or args.summary is None
            or args.numerical_output is None
            or args.consumer_contract is None
            or args.consumer_contract_sha256 is None
            or (args.mesh_actual_exact_report is None)
            != (args.mesh_actual_exact_report_sha256 is None)
        ):
            parser.error(
                "saved B0 evidence audit requires donor --summary/--numerical-output "
                "and a strict --consumer-contract binding"
            )
        try:
            result = check_task41_p0_b0_saved_evidence_audit(
                summary_path=args.summary,
                numerical_output=args.numerical_output,
                contract_path=args.contract,
                contract_sha256=args.contract_sha256,
                consumer_contract_path=args.consumer_contract,
                consumer_contract_sha256=args.consumer_contract_sha256,
                output_path=args.output,
                repo_root=root,
                mesh_actual_exact_report_path=args.mesh_actual_exact_report,
                mesh_actual_exact_report_sha256=args.mesh_actual_exact_report_sha256,
            )
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            result = {
                "schema": "task41.p0.b0.saved_evidence_audit.v1",
                "status": "INCOMPLETE",
                "audit_completed": False,
                "data_integrity": False,
                "recovery_passed": False,
                "joint_action_passed": None,
                "qualification_passed": False,
                "official_result": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "raw_evidence_retained": True,
            }
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 2
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("audit_completed") is True else 2
    if args.saved_output_continuation_input is not None:
        checker_only = os.environ.get("TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY") == "1"
        expected_output = (
            Path(os.environ.get("TASK41_P0_CHECKER_RESULT_PATH", "")).resolve()
            if checker_only
            else (
                args.saved_output_continuation_input.resolve().parent
                / "task41_p0_saved_output_checker_result.json"
            ).resolve()
        )
        if (
            args.summary is not None
            or args.manifest is not None
            or args.numerical_output is not None
            or args.output.resolve() != expected_output
        ):
            parser.error("saved-output continuation checker uses its bound input snapshot and adjacent result path")
        try:
            from src.runners.task41_p0_saved_output_continuation import (
                check_task41_p0_saved_output_continuation,
            )

            result = check_task41_p0_saved_output_continuation(
                args.saved_output_continuation_input,
                contract_path=args.contract,
                contract_sha256=args.contract_sha256,
                repo_root=root,
                result_path=args.output.resolve(),
            )
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            result = {
                "schema": "task41.p0.saved_output_checker.v1",
                "status": "FAIL",
                "checker_passed": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "raw_evidence_retained": True,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("checker_passed") is True else 2
    if any(value is None for value in (args.summary, args.manifest, args.numerical_output)):
        parser.error("ordinary Task41 checker mode requires --summary, --manifest, and --numerical-output")
    try:
        result = check_task41_p0(
            input_path=args.input,
            summary_path=args.summary,
            manifest_path=args.manifest,
            numerical_output=args.numerical_output,
            contract_path=args.contract,
            contract_sha256=args.contract_sha256,
            output_path=args.output,
            repo_root=root,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        result = {
            "schema": CHECKER_SCHEMA,
            "status": "FAIL",
            "checker_passed": False,
            "full_pass": False,
            "official_result": False,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "raw_evidence_retained": True,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("checker_passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
