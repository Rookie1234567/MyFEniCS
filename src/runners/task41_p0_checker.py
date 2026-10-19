"""Independent full-A6 and identity checker for the Task41 P0 A1 result."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
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
) -> dict[str, Any]:
    """Recompute B0 recovery and joint-action gates from hash-bound raw arrays."""
    errors: list[str] = []
    binding = summary.get("b0_recovery_evidence")
    if not isinstance(binding, Mapping):
        return {
            "schema": "task41.p0.b0.recovery_evidence_checker.v1",
            "errors": ["Task41 B0 summary omits its recovery evidence binding"],
            "passed": False,
        }
    manifest_ref = binding.get("manifest")
    manifest: Mapping[str, Any] = {}
    if not isinstance(manifest_ref, Mapping):
        errors.append("Task41 B0 recovery evidence omits its manifest artifact record")
    else:
        try:
            manifest_path = _task41_run_artifact(
                numerical_output.parent, manifest_ref, "B0 recovery manifest"
            )
            manifest = _json_object(manifest_path, "B0 recovery manifest")
            if (
                manifest_ref.get("stage") != manifest.get("stage")
                or binding.get("stage") != manifest.get("stage")
                or binding.get("status") != "PASS"
                or manifest.get("schema") != "task41.p0.b0.recovery_evidence.v1"
                or manifest.get("stage") != "FULL_ACTION_QUALIFIED"
                or manifest.get("status") != "PASS"
            ):
                errors.append("Task41 B0 recovery manifest did not finish the full-action gate")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append(f"Task41 B0 recovery manifest failed its path/hash check: {exc}")

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
        errors.append("Task41 B0 recovery manifest has no run identity")
        run_identity = {}
    for key, expected in expected_identity.items():
        if not expected or run_identity.get(key) != expected:
            errors.append(f"Task41 B0 recovery run identity differs at {key}")
    for key in ("staged_input_sha256", "carrier_committed_prefix_sha256"):
        value = run_identity.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            errors.append(f"Task41 B0 recovery run identity has invalid {key}")

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
        errors.append("Task41 B0 exact-zero local Bi/Di support certificate is absent or mismatched")
    if summary.get("b0_recovery_refinement_max_steps") != 3:
        errors.append("Task41 B0 production path is not bound to the shared three-step recovery loop")
    loop = binding.get("same_lu_refinement_loop")
    if (
        not isinstance(loop, Mapping)
        or loop.get("production_and_witness_share_loop") is not True
        or loop.get("maximum_steps_per_column") != 3
        or loop.get("full_carrier_sweeps_per_correction") != 0
        or loop.get("correction_driver")
        != "independent_native_cell_interior_volume_residual"
    ):
        errors.append("Task41 B0 recovery evidence does not bind the shared same-LU correction loop")

    checked_columns = []
    shared_raw_classes: dict[str, tuple[str, str, str, str]] = {}
    columns = manifest.get("columns")
    full_rows = manifest.get("full_storage_rows")
    if type(full_rows) is not int or full_rows < 1:
        errors.append("Task41 B0 recovery manifest has an invalid full storage size")
    if not isinstance(columns, list) or len(columns) != 2:
        errors.append("Task41 B0 recovery manifest does not contain both input columns")
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
            errors.append(f"Task41 B0 {label} metric is missing")
            return
        if not np.isfinite(declared) or abs(actual - declared) > 5.0e-13 * max(1.0, abs(actual)):
            errors.append(f"Task41 B0 {label} metric differs from its raw arrays")

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
                or not np.isfinite(b_values).all()
                or not np.isfinite(b_alpha_values).all()
            ):
                raise ValueError("selected B-frame artifacts have invalid row/value layouts")
            alpha_pair = identity_row.get("port_alpha")
            if not isinstance(alpha_pair, list) or len(alpha_pair) != 2:
                raise ValueError("selected B input has no saved complex port amplitude")
            alpha = complex(float(alpha_pair[0]), float(alpha_pair[1]))
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
                errors.append(
                    f"Task41 B0 recovery column {expected_column} finite gate failed: "
                    f"forward={final_forward}, volume_residual={final_residual_relative}"
                )

            raw_diagnostic = column.get("raw_cell_diagnostic")
            if refinement or not initial_gate_passed:
                if (
                    not isinstance(raw_diagnostic, Mapping)
                    or raw_diagnostic.get("structure_identity_passed") is not True
                    or raw_diagnostic.get("raw_matrices_are_independently_retabulated") is not True
                    or not isinstance(raw_diagnostic.get("cells"), list)
                    or not 1 <= len(raw_diagnostic["cells"]) <= 3
                ):
                    errors.append(
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
                            errors.append("Task41 B0 raw class lacks matrix/LU artifact identity")
                            continue
                        if class_identity in shared_raw_classes and shared_raw_classes[class_identity] != class_refs:
                            errors.append("Task41 B0 repeated raw class matrices were not shared")
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
                            or known_i.shape != (vii.shape[0],) or rhs_i.shape != known_i.shape
                            or rec_i.shape != known_i.shape or known_t.shape != (vit.shape[1],)
                            or rec_t.shape != known_t.shape
                            or interior_rows.shape != known_i.shape or interior_rows.dtype.kind not in "iu"
                            or trace_rows.shape != known_t.shape or trace_rows.dtype.kind not in "iu"
                            or active_ids.ndim != 1 or active_ids.dtype.kind not in "iu"
                            or expansion_indptr.shape != (len(trace_rows) + 1,)
                            or expansion_indices.shape != expansion_data.shape
                            or expansion_indptr[-1] != len(expansion_data)
                            or permutation.shape != (1,)
                            or permutation.dtype.kind not in "iu"
                        ):
                            errors.append("Task41 B0 raw-cell Vii/Vit evidence has inconsistent local layouts")
                            continue
                        try:
                            from scipy.sparse import csr_matrix
                            from scipy.linalg import lu_solve

                            expansion = csr_matrix(
                                (expansion_data, expansion_indices, expansion_indptr),
                                shape=(len(trace_rows), len(active_ids)),
                            )
                            active_values = np.asarray(known[active_original_rows], dtype=np.complex128)
                            recovered_active_values = np.asarray(final_storage[active_original_rows], dtype=np.complex128)
                            expected_known_trace = np.asarray(
                                expansion @ active_values[active_ids], dtype=np.complex128
                            ).reshape(-1)
                            expected_recovered_trace = np.asarray(
                                expansion @ recovered_active_values[active_ids], dtype=np.complex128
                            ).reshape(-1)
                            lu_identity = lu_solve(
                                (lu_factor, lu_pivots.astype(np.int32, copy=False)), vii
                            )
                        except (ValueError, TypeError, IndexError) as exc:
                            errors.append(f"Task41 B0 raw cell mapping/LU replay failed: {exc}")
                            continue
                        if (
                            not np.array_equal(known_i, known[interior_rows])
                            or not np.array_equal(rec_i, final_storage[interior_rows])
                            or not np.array_equal(known_t, expected_known_trace)
                            or not np.array_equal(rec_t, expected_recovered_trace)
                            or not np.allclose(lu_identity, np.eye(vii.shape[0]), rtol=1e-10, atol=1e-10)
                        ):
                            errors.append("Task41 B0 raw local rows, MPC trace expansion, or LU identity failed")
                            continue
                        known_action = vii @ known_i + vit @ known_t
                        recovered_action = vii @ rec_i + vit @ rec_t
                        local_scale = max(float(np.linalg.norm(rhs_i)), float(np.linalg.norm(action_i)), np.finfo(float).tiny)
                        if (
                            np.linalg.norm(known_action - rhs_i) / local_scale > 1.0e-10
                            or np.linalg.norm(recovered_action - action_i) / local_scale > 1.0e-10
                            or not np.allclose(rhs_i - action_i, residual_i, rtol=5e-13, atol=5e-13)
                        ):
                            errors.append("Task41 B0 independent raw-cell Vii/Vit replay failed")
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            errors.append(f"Task41 B0 recovery column {expected_column} replay failed: {exc}")

    full_action = manifest.get("full_action")
    try:
        if not isinstance(full_action, Mapping) or full_action.get("status") != "PASS":
            raise ValueError("joint P6 full action did not pass")
        joint = full_action.get("artifacts")
        if not isinstance(joint, Mapping):
            raise ValueError("joint-action artifact inventory is missing")
        p6 = load_array(joint.get("p6_result"), "joint P6 result")
        port_rhs = load_array(joint.get("port_rhs"), "joint port RHS")
        reduced_rhs = load_array(joint.get("reduced_rhs"), "joint reduced RHS")
        if (
            p6.ndim != 2
            or reduced_rhs.shape != p6.shape
            or port_rhs.ndim != 2
            or p6.shape[1] != 2
            or port_rhs.shape[1] != 2
            or not np.isfinite(p6).all()
            or not np.isfinite(port_rhs).all()
            or not np.isfinite(reduced_rhs).all()
        ):
            raise ValueError("joint-action arrays have invalid shapes or non-finite values")
        errors_by_column = []
        for column in range(2):
            left = np.asarray(p6[:, column], dtype=np.complex128)
            right = np.asarray(reduced_rhs[:, column], dtype=np.complex128)
            errors_by_column.append(
                float(np.linalg.norm(left - right))
                / max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), np.finfo(float).tiny)
            )
        if max(errors_by_column, default=float("inf")) > 1.0e-11:
            raise ValueError("joint P6 and native reduced RHS differ beyond the original gate")
        for name, actual in zip(
            ("p6_result", "port_rhs", "reduced_rhs"),
            (p6, port_rhs, reduced_rhs),
            strict=True,
        ):
            _ = actual
            if name not in joint:
                raise ValueError(f"joint-action evidence omits {name}")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"Task41 B0 joint-action replay failed: {exc}")

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
        errors.append("Task41 B0 manifest same-LU step count differs from its raw states")
    if len(shared_raw_classes) > 3:
        errors.append("Task41 B0 recovery evidence stores more than three raw local classes")
    return {
        "schema": "task41.p0.b0.recovery_evidence_checker.v1",
        "manifest_path": manifest_ref.get("path") if isinstance(manifest_ref, Mapping) else None,
        "manifest_stage": manifest.get("stage"),
        "run_identity_rechecked": not any("identity" in error for error in errors),
        "support_certificate_rechecked": not any("support certificate" in error for error in errors),
        "columns": checked_columns,
        "joint_action_status": (
            "PASS"
            if isinstance(manifest.get("full_action"), Mapping)
            and manifest["full_action"].get("status") == "PASS"
            else "NOT_RUN"
            if not isinstance(manifest.get("full_action"), Mapping)
            else "FAIL"
        ),
        "joint_action_replayed": not any("joint-action" in error for error in errors),
        "errors": errors,
        "passed": not errors,
    }


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
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--numerical-output", type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
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
