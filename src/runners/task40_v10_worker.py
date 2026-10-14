"""Task40 Review V10 B0 workers.

The control remains on the qualified p4 BAL_H route.  The candidate uses one
regular, full-p6 two-cell reference inverse for both its regular-equation
checks and the real two-cell-gap outer solve.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import shutil
import sys
import time
import copy
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from src.solvers.task40_v10_p6_periodic_profile import TASK40_V10_P6_PROFILE


_REFERENCE_RESIDUAL_LIMIT = 1.0e-10
_REGULAR_ACTION_LIMIT = 1.0e-11
_REGULAR_RECOVERY_LIMIT = 1.0e-11
_MAPPING_IDENTITY_LIMIT = 1.0e-12
_A6_RESIDUAL_LIMIT = 1.0e-6
_PORT_CLOSURE_LIMIT = 1.0e-8
_IDENTITY_LIMIT = 1.0e-10


def _task40_v30_q_csr_provider(
    binding: Mapping[str, Any] | None,
    *,
    repo_root: str | Path,
    allocation_gate: Any,
    consumer_receipt_directory: str | Path | None = None,
    consumer_import_authorizations: Mapping[str, Mapping[str, Any]] | None = None,
    numeric_pending_import_authorizations: Mapping[str, Mapping[str, Any]] | None = None,
):
    if binding is None:
        return None
    is_v31 = isinstance(binding, Mapping) and binding.get("schema") == (
        "task40extra.review_v31_q_csr_worker_binding.v1"
    )
    expected_schema = (
        "task40extra.review_v31_q_csr_worker_binding.v1"
        if is_v31
        else "task40extra.review_v30_q_csr_worker_binding.v1"
    )
    if (
        not isinstance(binding, Mapping)
        or binding.get("schema") != expected_schema
        or set(binding) != {"schema", "selector_path", "selector_sha256"}
    ):
        raise ValueError("Task40 worker needs the exact frozen q-CSR selector binding")
    root = Path(repo_root).resolve()
    selector = Path(str(binding["selector_path"]))
    if not selector.is_absolute():
        selector = root / selector
    selector = selector.resolve()
    artifact_roots = (
        (
            root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native"
        ).resolve(),
        (root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_wsl").resolve(),
        (root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_preparation").resolve(),
    )
    if not any(selector.is_relative_to(path) for path in artifact_roots):
        raise ValueError("V30 q-CSR selector is outside the registered campaign artifact roots")
    from src.solvers.task40_v30_qualified_q_csr import QualifiedQCSRProvider

    path_resolver = _task40_v30_artifact_path_resolver(root)

    return QualifiedQCSRProvider(
        selector,
        selector_sha256=str(binding["selector_sha256"]),
        repo_root=root,
        path_resolver=path_resolver,
        allocation_gate=allocation_gate,
        consumer_receipt_directory=consumer_receipt_directory,
        consumer_import_authorizations=consumer_import_authorizations,
        numeric_pending_import_authorizations=numeric_pending_import_authorizations,
    )


def _task40_v30_artifact_path_resolver(repo_root: str | Path):
    """Map only canonical Task40 source paths into the current approved root."""
    from src.runners.task40_v29_contract import SOURCE_ROOT, resolve_approved_path

    root = Path(repo_root).resolve()

    def resolve(raw_path: str | Path) -> Path:
        supplied = Path(raw_path)
        candidate = (root / supplied).resolve(strict=False) if not supplied.is_absolute() else supplied.resolve(strict=False)
        if candidate.is_relative_to(root):
            return candidate
        return resolve_approved_path(
            candidate,
            source_root=SOURCE_ROOT,
            execution_root=root,
        )

    return resolve


def _task40_v30_open_saved_q4_source(
    *,
    contract: Mapping[str, Any],
    repo_root: str | Path,
    profile: Any,
    current_q0_map: Any | None = None,
    current_q4_map: Any | None = None,
    current_local_h: np.ndarray | None = None,
    allocation_gate: Any,
    return_saved_inputs: bool = False,
) -> Any:
    """Open the accepted twist-0 donor, optionally binding its later live owner."""
    from scipy import sparse
    from src.runners.task40_v29_contract import sha256_file
    from src.runners.task40_v10_campaign import TASK40_V25_CAMPAIGN_SHA256
    from src.solvers.task40_v27_saved_q0 import SavedQ0ContributionAdapter
    from src.solvers.task40_v30_qualified_q_csr import _csr_sha256

    root = Path(repo_root).resolve()
    preparation = contract.get("preparation")
    donor = preparation.get("accepted_q0_donor") if isinstance(preparation, Mapping) else None
    if not isinstance(donor, Mapping):
        raise ValueError("V30 contract omits the accepted twist-0 producer donor")
    manifest_path = (root / str(donor.get("manifest_relative_path", ""))).resolve()
    if (
        not manifest_path.is_relative_to(root)
        or not manifest_path.is_file()
        or sha256_file(manifest_path) != donor.get("manifest_sha256")
    ):
        raise ValueError("V30 accepted q0 continuation manifest is missing or changed")
    continuation = json.loads(manifest_path.read_text(encoding="utf-8"))
    numeric_fill = continuation.get("numeric_fill_identity")
    donor_identity = (
        numeric_fill.get("donor_identity")
        if isinstance(numeric_fill, Mapping)
        else None
    )
    producer = (
        donor_identity.get("producer_identity")
        if isinstance(donor_identity, Mapping)
        else None
    )
    producer_identity_sha256 = (
        donor_identity.get("producer_identity_sha256")
        if isinstance(donor_identity, Mapping)
        else None
    )
    if (
        continuation.get("schema") != "task40extra.review_v28_saved_q0_csr.v1"
        or continuation.get("status") != "COMPLETE_CSR"
        or not isinstance(producer, Mapping)
        or not isinstance(producer_identity_sha256, str)
        or producer.get("producer_source_sha")
        != "9d0f4dbfc730dd620b709d048e33e9da6c77520c"
    ):
        raise ValueError("V30 twist-0 saved producer identity differs from the accepted V25 source")
    raw_run_root = Path(str(producer.get("producer_run_directory", "")))
    producer_root = (
        raw_run_root.resolve()
        if raw_run_root.is_absolute()
        else (root / raw_run_root).resolve()
    )
    if not producer_root.is_relative_to(root):
        producer_root = _task40_v30_artifact_path_resolver(root)(producer_root)
    try:
        producer_root.relative_to(root)
    except ValueError as exc:
        raise ValueError("V30 saved twist-0 producer escaped the execution root") from exc
    payload_rows = producer.get("payloads")
    if not isinstance(payload_rows, list):
        raise ValueError("V30 accepted producer omits its payload hash inventory")
    payloads = {}
    for row in payload_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            raise ValueError("V30 accepted producer payload identity is malformed")
        name = Path(row["path"]).name
        if name in payloads:
            raise ValueError("V30 accepted producer contains duplicate payload basenames")
        payloads[name] = dict(row)
    required_names = {
        "v25_selected_q0_surface_functionals.bin",
        "v25_selected_q0_volume_classes.bin",
        "v25_selected_q0_local_H_p.npy",
        "v25_selected_q0_original_to_active_int32.npy",
        "v25_selected_q0_map.npz",
        "v25_selected_q4_map.npz",
    }
    if not required_names <= set(payloads):
        raise ValueError("V30 accepted producer is missing q4 source, map, H, or lookup evidence")
    allocation_gate(
        "task40_v30_q4_saved_twist0_producer_hash_readback",
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": 4 * 1024**2,
            "producer_payload_bytes": sum(int(payloads[name].get("bytes", -1)) for name in required_names),
            "streaming_sha256": True,
            "producer_identity_sha256": producer_identity_sha256,
        },
    )
    paths = {}
    for name in sorted(required_names):
        row = payloads[name]
        relative = Path(str(row["path"]))
        path = (producer_root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"V30 accepted q4 producer payload is unavailable: {name}")
        if int(row.get("bytes", -1)) != path.stat().st_size or sha256_file(path) != row.get("sha256"):
            raise ValueError(f"V30 accepted q4 producer payload changed: {name}")
        paths[name] = path

    q0_map = sparse.load_npz(paths["v25_selected_q0_map.npz"]).tocsr()
    q4_map = sparse.load_npz(paths["v25_selected_q4_map.npz"]).tocsr()
    saved_h = np.load(paths["v25_selected_q0_local_H_p.npy"], mmap_mode="r", allow_pickle=False)
    active_lookup = np.load(
        paths["v25_selected_q0_original_to_active_int32.npy"],
        mmap_mode="r",
        allow_pickle=False,
    )
    live_values = (current_q0_map, current_q4_map, current_local_h)
    if any(value is not None for value in live_values) and not all(
        value is not None for value in live_values
    ):
        raise ValueError("saved q4 live binding must compare q0 map, q4 map, and original H together")
    if current_q0_map is not None and _csr_sha256(q0_map) != _csr_sha256(current_q0_map):
        raise ValueError("saved q0 map differs from this live twist-0 branch map")
    if current_q4_map is not None and _csr_sha256(q4_map) != _csr_sha256(current_q4_map):
        raise ValueError("saved q4 map differs from this live twist-0 branch map")
    if saved_h.dtype != np.dtype(np.complex128) or saved_h.ndim != 1 or not np.isfinite(saved_h).all():
        raise ValueError("saved twist-0 original H is not finite complex128")
    if (
        q0_map.shape[0] != q4_map.shape[0]
        or q0_map.shape[1] != int(profile.trace_rows_per_q) + int(profile.q_port_counts[0])
        or q4_map.shape[1] != int(profile.trace_rows_per_q) + int(profile.q_port_counts[4])
        or active_lookup.dtype != np.dtype(np.int32)
        or active_lookup.ndim != 1
    ):
        raise ValueError("saved twist-0 q maps or active lookup differ from the frozen profile")
    if current_local_h is not None and not np.array_equal(
        saved_h, np.asarray(current_local_h, dtype=np.complex128)
    ):
        raise ValueError("saved twist-0 H differs from the live sector's original H")
    source = SavedQ0ContributionAdapter(
        volume_stream_path=paths["v25_selected_q0_volume_classes.bin"],
        surface_stream_path=paths["v25_selected_q0_surface_functionals.bin"],
        active_lookup=active_lookup,
        local_h=saved_h,
        q0_map=q0_map,
        active_rows=int(profile.local_trace_rows),
        q0_trace_rows=int(profile.trace_rows_per_q),
        q0_port_rows=int(profile.q_port_counts[0]),
        allocation_gate=allocation_gate,
    )
    producer_facts = {
        "kind": "accepted_v25_twist0_saved_producer",
        "producer_run_id": producer.get("producer_run_id"),
        "producer_source_sha": producer["producer_source_sha"],
        "producer_input_sha256": producer.get("verified_input_sha256"),
        "producer_physical_model_sha256": producer.get("physical_model_sha256"),
        "producer_identity_sha256": producer_identity_sha256,
        "producer_window_sha256": TASK40_V25_CAMPAIGN_SHA256,
        "payload_sha256": {name: payloads[name]["sha256"] for name in sorted(required_names)},
        "q4_map_sha256": _csr_sha256(q4_map),
    }
    result = {
        "source": source,
        "q0_map": q0_map,
        "q4_map": q4_map,
        "original_h": saved_h,
        "active_lookup": active_lookup,
        "active_lookup_path": paths["v25_selected_q0_original_to_active_int32.npy"],
        "surface_stream_path": paths["v25_selected_q0_surface_functionals.bin"],
        "producer_facts": producer_facts,
    }
    if return_saved_inputs:
        return result
    return source, q4_map, producer_facts


def _task40_v31_build_reference_after_q4_pending(
    *,
    prepare_saved_q4: Callable[[], Mapping[str, Any]] | None,
    build_reference: Callable[..., Any],
    prepare_twist0_owner: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> tuple[Any, Mapping[str, Any] | None]:
    """Persist q4, then build and hand off its local owner before global FE."""
    pending = prepare_saved_q4() if prepare_saved_q4 is not None else None
    if pending is not None and pending.get("status") != "NUMERIC_COMPLETE_NATIVE_PENDING":
        raise ValueError("V31 saved-first q4 boundary requires a numeric-pending result")
    local_owner = (
        prepare_twist0_owner(pending)
        if pending is not None and prepare_twist0_owner is not None
        else None
    )
    if local_owner is not None:
        return build_reference(pending, local_owner), pending
    return build_reference(pending), pending


def _task40_v31_merge_twist0_q_csr_audit(
    provider_matrices: Mapping[int, Any],
    provider_audit: Mapping[str, Any],
    prepared_matrices: Mapping[int, Any],
    preparation_audit: Mapping[str, Any],
    *,
    donor_binding: Mapping[str, Any],
) -> tuple[dict[int, Any], dict[str, Any]]:
    """Require one verified q0 and q4 receipt before the twist-0 owner handoff."""
    if set(provider_matrices).intersection(prepared_matrices):
        raise ValueError("V31 twist-0 q CSR was both imported and freshly prepared")
    all_matrices = {**dict(provider_matrices), **dict(prepared_matrices)}
    receipts = [
        *provider_audit.get("qualification_receipts", ()),
        *preparation_audit.get("qualification_receipts", ()),
    ]
    selector_entries = [
        *provider_audit.get("selector_entries", ()),
        *preparation_audit.get("selector_entries", ()),
    ]
    receipt_by_q = {
        int(row.get("q_index", -1)): row for row in receipts if isinstance(row, Mapping)
    }
    receipt_q_indices = sorted(receipt_by_q)
    selector_q_indices = sorted(
        int(row.get("q_index", -1))
        for row in selector_entries
        if isinstance(row, Mapping)
    )
    q0 = receipt_by_q.get(0, {})
    q4 = receipt_by_q.get(4, {})
    q0_legacy_pass = (
        q0.get("qualification_kind")
        == "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED"
        and q0.get("qualification_status") == "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"
        and isinstance(q0.get("legacy_q0_import"), Mapping)
    )
    q4_native_pass = (
        q4.get("qualification_kind") == "V30_NATIVE_PASS"
        and q4.get("qualification_status") == "PASS"
    )
    complete = (
        set(all_matrices) == {0, 4}
        and len(receipts) == 2
        and receipt_q_indices == [0, 4]
        and selector_q_indices == [0, 4]
        and all(row.get("qualification_status") == "PASS" for row in selector_entries)
        and q0_legacy_pass
        and q4_native_pass
    )
    merged = {
        **dict(provider_audit),
        **dict(preparation_audit),
        "qualification_receipts": [dict(row) for row in receipts],
        "selector_entries": [dict(row) for row in selector_entries],
        "q_indices": sorted(all_matrices),
        "all_complete_native_pass": complete,
        "q4_saved_live_binding": dict(donor_binding),
        "native_owner_created_before_global_reference": True,
    }
    if not complete:
        raise ValueError("V31 twist-0 handoff lacks COMPLETE CSR and native PASS for q0/q4")
    return all_matrices, merged


def _task40_v31_apply_local_owner_cleanup_failure(
    summary: dict[str, Any],
    worker_result: dict[str, Any] | None,
    cleanup_facts: Mapping[str, Any],
) -> None:
    """Make an unverified twist-0 release a failed worker/checker result."""
    error = cleanup_facts.get("error", {})
    message = str(error.get("message", "V31 twist-0 local owner cleanup failed"))
    summary["v31_twist0_local_owner_cleanup"] = dict(cleanup_facts)
    summary["status"] = "FAILED"
    summary["official_result"] = False
    summary["result_classification"] = "WORKER_CLEANUP_FAILED"
    summary.setdefault("cleanup_errors", []).append(dict(error))
    if worker_result is not None:
        worker_result["passed"] = False
        worker_result["status"] = "failed"
        errors = list(worker_result.get("errors", ()))
        if message not in errors:
            errors.append(message)
        worker_result["errors"] = errors
        worker_result["summary"] = summary


def _task40_v31_bind_saved_q4_to_live(
    saved_donor: Mapping[str, Any],
    *,
    current_q0_map: Any,
    current_q4_map: Any,
    current_local_h: np.ndarray,
    current_trace_constraints: Any,
    current_full_rows: int,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
) -> dict[str, Any]:
    """Bind saved maps/H/lookup to the later sector owner with a bounded lookup scan."""
    from src.solvers.task40_v30_qualified_q_csr import _csr_sha256

    q0_map = saved_donor.get("q0_map")
    q4_map = saved_donor.get("q4_map")
    saved_h = saved_donor.get("original_h")
    active_lookup = saved_donor.get("active_lookup")
    trace_constraints = current_trace_constraints
    if (
        q0_map is None or q4_map is None or saved_h is None
        or _csr_sha256(q0_map) != _csr_sha256(current_q0_map)
        or _csr_sha256(q4_map) != _csr_sha256(current_q4_map)
        or not np.array_equal(np.asarray(saved_h), np.asarray(current_local_h, dtype=np.complex128))
    ):
        raise ValueError("saved q4 donor differs from the later live q0/q4 map or original H")
    original_to_active = getattr(trace_constraints, "original_to_active", None)
    if (
        not isinstance(active_lookup, np.ndarray)
        or active_lookup.dtype != np.dtype(np.int32)
        or active_lookup.ndim != 1
        or type(current_full_rows) is not int
        or len(active_lookup) != current_full_rows
        or not isinstance(original_to_active, Mapping)
    ):
        raise ValueError("saved q4 active lookup cannot be bound to the live trace constraints")
    allocation_gate(
        "task40_v31_q4_saved_live_lookup_binding",
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": 1 * 1024**2,
            "lookup_length": int(len(active_lookup)),
            "mapping_entries": int(len(original_to_active)),
            "bounded_chunk_rows": 1 << 20,
        },
    )
    nonnegative_count = 0
    for start in range(0, len(active_lookup), 1 << 20):
        values = active_lookup[start : start + (1 << 20)]
        if np.any(values < -1):
            raise ValueError("saved q4 active lookup contains a value below the inactive sentinel")
        nonnegative_count += int(np.count_nonzero(values >= 0))
    if nonnegative_count != len(original_to_active):
        raise ValueError("saved q4 active lookup cardinality differs from live trace constraints")
    for original, active in original_to_active.items():
        original = int(original)
        if (
            original < 0 or original >= len(active_lookup)
            or int(active_lookup[original]) != int(active)
        ):
            raise ValueError("saved q4 active lookup differs from live original-to-active numbering")
    return {
        "saved_q0_map_sha256": _csr_sha256(q0_map),
        "saved_q4_map_sha256": _csr_sha256(q4_map),
        "saved_original_h_sha256": hashlib.sha256(
            np.ascontiguousarray(np.asarray(saved_h, dtype=np.complex128)).view(np.uint8)
        ).hexdigest(),
        "saved_active_lookup_sha256": saved_donor.get("producer_facts", {})
        .get("payload_sha256", {})
        .get("v25_selected_q0_original_to_active_int32.npy"),
        "active_lookup_entries": nonnegative_count,
        "live_full_rows": current_full_rows,
        "live_lookup_binding_passed": True,
        "live_map_and_h_binding_passed": True,
    }


_TASK40_V31_TARGET_OWNER_COMPONENTS = ("mesh_mpc", "local_lu", "cache", "carrier")


def _task40_v31_target_owner_inventory_total(
    inventory: Mapping[str, Any], *, measured_only: bool, allow_unknown: bool = False
) -> tuple[dict[str, dict[str, Any]], int]:
    """Require an explicit, evidence-bound byte count for every target owner."""
    if not isinstance(inventory, Mapping) or set(inventory) != set(
        _TASK40_V31_TARGET_OWNER_COMPONENTS
    ):
        raise ValueError("V31 target owner inventory must close mesh_mpc/local_lu/cache/carrier")
    normalized: dict[str, dict[str, Any]] = {}
    total = 0
    for component in _TASK40_V31_TARGET_OWNER_COMPONENTS:
        row = inventory[component]
        if not isinstance(row, Mapping):
            raise ValueError(f"V31 target owner inventory component {component} is UNKNOWN")
        byte_count = row.get("bytes")
        status = row.get("status")
        owner_id = row.get("owner_id")
        evidence = row.get("evidence")
        if status == "unknown" and allow_unknown:
            if (
                byte_count is not None
                or not isinstance(owner_id, str)
                or not owner_id.strip()
                or not isinstance(evidence, str)
                or not evidence.strip()
            ):
                raise ValueError(
                    f"V31 unknown target owner {component} must retain null bytes and evidence"
                )
            normalized[component] = {
                "bytes": None,
                "status": "unknown",
                "owner_id": owner_id,
                "evidence": evidence,
            }
            continue
        if (
            type(byte_count) is not int
            or byte_count < 0
            or status not in ({"measured"} if measured_only else {"measured", "derived"})
            or not isinstance(owner_id, str)
            or not owner_id.strip()
            or not isinstance(evidence, str)
            or not evidence.strip()
        ):
            raise ValueError(
                f"V31 target owner inventory component {component} lacks a closed byte/status/owner/evidence record"
            )
        alias_of = row.get("alias_of")
        if byte_count == 0 and (not isinstance(alias_of, str) or not alias_of.strip()):
            raise ValueError(
                f"V31 zero-byte target owner {component} requires explicit alias_of evidence"
            )
        normalized[component] = {
            "bytes": byte_count,
            "status": status,
            "owner_id": owner_id,
            "evidence": evidence,
            **({"alias_of": alias_of} if alias_of is not None else {}),
        }
        total += byte_count
    return normalized, total


def _task40_v31_reference_only_allq_callback(
    facts: Mapping[str, Any], *, expected_q_count: int
) -> dict[str, Any]:
    """Validate the closed eight-q reference budget while target owners stay unknown."""
    if expected_q_count != 8:
        raise ValueError("V31 REFERENCE_ONLY admission is restricted to the frozen eight-q profile")
    estimates = facts.get("q_symbolic_estimates_bytes")
    if not isinstance(estimates, Mapping):
        raise ValueError("V31 REFERENCE_ONLY lacks per-q symbolic estimates")
    normalized_estimates: dict[int, int] = {}
    for raw_q, raw_bytes in estimates.items():
        try:
            q = int(raw_q)
        except (TypeError, ValueError) as exc:
            raise ValueError("V31 symbolic q estimate key is not an integer") from exc
        if q in normalized_estimates or type(raw_bytes) is not int or raw_bytes < 0:
            raise ValueError("V31 symbolic q estimate inventory is duplicated or invalid")
        normalized_estimates[q] = raw_bytes
    stated_symbolic_sum = facts.get("all_q_symbolic_estimate_sum_bytes")
    if (
        set(normalized_estimates) != set(range(expected_q_count))
        or facts.get("all_q_symbolic_q_completed") is not True
        or type(stated_symbolic_sum) is not int
        or stated_symbolic_sum != sum(normalized_estimates.values())
    ):
        raise ValueError("V31 REFERENCE_ONLY requires all eight matching symbolic estimates")
    reference_rows = facts.get("reference_full_storage_rows")
    recovery_rows = facts.get("full_storage_rows_for_future_recovery")
    planned_rows = facts.get("planned_target_full_storage_rows")
    if (
        type(reference_rows) is not int
        or reference_rows <= 0
        or type(recovery_rows) is not int
        or recovery_rows != reference_rows
        or type(planned_rows) is not int
        or planned_rows <= 0
        or facts.get("actual_target_full_storage_rows") is not None
        or facts.get("actual_target_rows_match_reference") is not False
        or facts.get("target_budget_status") != "PLANNED_ROWS_RESERVED_ACTUAL_NOT_BUILT"
    ):
        raise ValueError("V31 REFERENCE_ONLY must budget reference rows and keep target rows plan-only")
    unknown_owners = facts.get("target_owner_increment_inventory")
    if not isinstance(unknown_owners, Mapping) or set(unknown_owners) != set(
        _TASK40_V31_TARGET_OWNER_COMPONENTS
    ) or any(unknown_owners[name] is not None for name in _TASK40_V31_TARGET_OWNER_COMPONENTS):
        raise ValueError("V31 REFERENCE_ONLY target owner increments must remain explicitly UNKNOWN")
    output_inventory = facts.get("pre_release_recovery_output_inventory")
    if (
        not isinstance(output_inventory, Mapping)
        or output_inventory.get("reference_full_storage_rows") != reference_rows
        or output_inventory.get("planned_target_full_storage_rows") != planned_rows
        or output_inventory.get("actual_target_full_storage_rows") is not None
        or output_inventory.get("actual_target_and_reference_full_rows_match") is not False
        or output_inventory.get("actual_target_and_reference_full_rows_match_required") is not False
    ):
        raise ValueError("V31 REFERENCE_ONLY recovery inventory must retain an unknown target")
    ksp_bytes = facts.get("future_retained_krylov_and_vector_bytes")
    inverse_payload_bytes = facts.get("future_inverse_payload_bytes")
    inverse_workspace_bytes = facts.get("future_inverse_single_operation_workspace_bytes")
    recovery_output_bytes = facts.get("future_full_p6_pre_release_recovery_output_bytes")
    selected_phase_bytes = facts.get("selected_future_nonfactor_co_resident_peak_bytes")
    if any(
        type(value) is not int or value < 0
        for value in (
            ksp_bytes,
            inverse_payload_bytes,
            inverse_workspace_bytes,
            recovery_output_bytes,
            selected_phase_bytes,
        )
    ):
        raise ValueError("V31 REFERENCE_ONLY future reference workspace inventory is incomplete")
    if output_inventory.get("pre_release_peak_bytes") != recovery_output_bytes:
        raise ValueError("V31 REFERENCE_ONLY recovery output bytes differ from its inventory")
    expected_phase = max(
        ksp_bytes + inverse_workspace_bytes,
        recovery_output_bytes + inverse_workspace_bytes,
    )
    if (
        selected_phase_bytes != expected_phase
        or facts.get("future_ksp_plus_inverse_workspace_bytes")
        != ksp_bytes + inverse_workspace_bytes
        or facts.get("future_full_output_plus_inverse_workspace_bytes")
        != recovery_output_bytes + inverse_workspace_bytes
        or facts.get("future_inverse_payload_plus_selected_phase_bytes")
        != inverse_payload_bytes + selected_phase_bytes
    ):
        raise ValueError("V31 REFERENCE_ONLY co-resident reference budget does not close")
    future_components = {
        "mumps_symbolic_estimate_sum_bytes": sum(normalized_estimates.values()),
        "persistent_pending_transform_inverse_payload_bytes": inverse_payload_bytes,
        "selected_maximum_co_resident_phase_bytes": selected_phase_bytes,
    }
    return {
        "schema": "task40extra.review_v31_target_admission.v1",
        "phase": "REFERENCE_ONLY",
        "status": "REFERENCE_INVENTORY_READY",
        "q_symbolic_estimates_bytes": {
            str(q): normalized_estimates[q] for q in range(expected_q_count)
        },
        "future_reserve_components": future_components,
        "future_reserve_bytes": sum(future_components.values()),
        "reference_full_storage_rows": reference_rows,
        "planned_target_full_storage_rows": planned_rows,
        "actual_target_full_storage_rows": None,
        "target_owner_increment_inventory": {
            name: None for name in _TASK40_V31_TARGET_OWNER_COMPONENTS
        },
        "target_build_admitted": False,
        "target_ready": False,
    }


def _task40_v31_target_build_admission(
    reference_admission: Mapping[str, Any] | None,
    target_owner_inventory: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Reserve a fully described target increment before the target mesh is built."""
    if (
        not isinstance(reference_admission, Mapping)
        or reference_admission.get("phase") != "REFERENCE_ONLY"
        or reference_admission.get("status") != "ADMITTED_REFERENCE_ONLY"
        or reference_admission.get("target_build_admitted") is not False
    ):
        raise ValueError("V31 TARGET_BUILD requires a prior REFERENCE_ONLY admission")
    if target_owner_inventory is None:
        raise ValueError("V31 TARGET_BUILD is blocked while target owner increments are UNKNOWN")
    normalized, total = _task40_v31_target_owner_inventory_total(
        target_owner_inventory, measured_only=False
    )
    return {
        "schema": "task40extra.review_v31_target_admission.v1",
        "phase": "TARGET_BUILD",
        "status": "TARGET_BUILD_INVENTORY_READY",
        "reference_full_storage_rows": reference_admission["reference_full_storage_rows"],
        "planned_target_full_storage_rows": reference_admission[
            "planned_target_full_storage_rows"
        ],
        "actual_target_full_storage_rows": None,
        "target_owner_increment_inventory": normalized,
        "reserved_target_owner_increment_bytes": total,
        "target_build_admitted": False,
        "target_ready": False,
    }


def _task40_v31_reference_future_reserve(
    reference_owner: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Recompute only still-future reference/PC work from the live owner inventories."""
    if not isinstance(reference_owner, Mapping):
        raise ValueError("V31 target readiness requires the live reference owner")
    factors = reference_owner.get("factors")
    layout = reference_owner.get("full_layout")
    if factors is None or layout is None:
        raise ValueError("V31 live reference owner lacks factors or full layout")
    factor_audit = factors.audit
    if (
        not isinstance(factor_audit, Mapping)
        or factor_audit.get("all_q_factors_retained_simultaneously") is not True
        or factor_audit.get("all_q_numeric_factors_true_residual_passed") is not True
    ):
        raise ValueError("V31 future reserve requires all qualified numeric factors live")
    row_counts = tuple(getattr(factors, "row_counts", ()))
    if len(row_counts) != 8 or any(type(rows) is not int or rows <= 0 for rows in row_counts):
        raise ValueError("V31 future reserve requires the live eight-q factor row inventory")
    reference_rows = int(layout.full_rows)
    if reference_rows <= 0:
        raise ValueError("V31 future reserve requires positive reference storage rows")
    transform_bank = getattr(factors, "transform_bank", None)
    bank = (
        transform_bank.future_inverse_reserve()
        if transform_bank is not None
        else {
            "future_unique_inverse_payload_bytes": 0,
            "future_single_inverse_workspace_bytes": 0,
            "future_unique_inverse_template_count": 0,
        }
    )
    legacy_borrowers = getattr(factors, "inverse_borrowers", {})
    if not isinstance(bank, Mapping) or not isinstance(legacy_borrowers, Mapping):
        raise ValueError("V31 future transform reserve inventory is unavailable")
    legacy = {
        str(label): borrower.future_legacy_inverse_reserve()
        for label, borrower in legacy_borrowers.items()
    }
    inverse_payload = int(bank.get("future_unique_inverse_payload_bytes", -1)) + sum(
        int(row.get("future_legacy_inverse_payload_bytes", -1))
        for row in legacy.values()
    )
    inverse_workspace = max(
        [int(bank.get("future_single_inverse_workspace_bytes", -1))]
        + [
            int(row.get("future_legacy_single_inverse_workspace_bytes", -1))
            for row in legacy.values()
        ]
    )
    bank_count = bank.get("future_unique_inverse_template_count")
    if (
        inverse_payload < 0
        or inverse_workspace < 0
        or type(bank_count) is not int
        or bank_count < 0
        or any(
            int(value) < 0
            for row in legacy.values()
            for value in (
                row.get("future_legacy_inverse_payload_bytes", -1),
                row.get("future_legacy_single_inverse_workspace_bytes", -1),
            )
        )
    ):
        raise ValueError("V31 future transform reserve has unknown or negative components")
    krylov_vector_count = 2 * (32 + 1) + 6
    krylov_bytes = int(
        sum(row_counts) * krylov_vector_count * np.dtype(np.complex128).itemsize
    )
    from src.solvers.task40_v10_p6_mumps import full_p6_pre_release_output_inventory

    output_inventory = full_p6_pre_release_output_inventory(reference_rows)
    full_output_bytes = int(output_inventory["pre_release_peak_bytes"])
    selected_phase = max(
        krylov_bytes + inverse_workspace,
        full_output_bytes + inverse_workspace,
    )
    return {
        "schema": "task40extra.review_v31_remaining_reference_reserve.v1",
        "reference_full_storage_rows": reference_rows,
        "remaining_transform_inverse_payload_bytes": inverse_payload,
        "remaining_inverse_template_count": bank_count,
        "future_inverse_single_operation_workspace_bytes": inverse_workspace,
        "future_krylov_and_vector_bytes": krylov_bytes,
        "future_full_p6_recovery_output_bytes": full_output_bytes,
        "selected_nonfactor_co_resident_phase_bytes": selected_phase,
        "future_co_resident_reserve_bytes": inverse_payload + selected_phase,
        "future_full_p6_output_inventory": output_inventory,
        "future_legacy_inverse_reserves_by_collection": legacy,
        "symbolic_estimate_reserve_released_into_current_rss": True,
        "accounting_basis": (
            "current RSS contains resident numeric factors and already materialized inverses; "
            "only live bank/legacy pending inverse payload plus the larger future KSP or "
            "full-recovery-output phase remains reserved"
        ),
    }


def _task40_v31_target_ready_admission(
    reference_admission: Mapping[str, Any] | None,
    target_build_admission: Mapping[str, Any] | None,
    actual_target_owner_inventory: Mapping[str, Any] | None,
    facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Require measured owners, true row/layout identity, and both resource inequalities."""
    if (
        not isinstance(reference_admission, Mapping)
        or reference_admission.get("status") != "ADMITTED_REFERENCE_ONLY"
        or not isinstance(target_build_admission, Mapping)
        or target_build_admission.get("phase") != "TARGET_BUILD"
        or target_build_admission.get("status") != "ADMITTED_TARGET_BUILD"
    ):
        raise ValueError("V31 TARGET_READY requires admitted reference and target-build stages")
    normalized, actual_owner_bytes = _task40_v31_target_owner_inventory_total(
        actual_target_owner_inventory, measured_only=True, allow_unknown=True
    )
    reference_rows = reference_admission.get("reference_full_storage_rows")
    actual_rows = facts.get("actual_target_full_storage_rows")
    planned_rows = facts.get("planned_target_full_storage_rows")
    if (
        type(actual_rows) is not int
        or actual_rows <= 0
        or actual_rows != reference_rows
        or actual_rows != planned_rows
    ):
        raise ValueError("V31 TARGET_READY target/reference/planned storage rows do not match")
    for field in (
        "mode_identity_passed",
        "map_identity_passed",
        "layout_identity_passed",
    ):
        if facts.get(field) is not True:
            raise ValueError(f"V31 TARGET_READY lacks passing {field}")
    future_reserve = facts.get("future_reserve")
    if not isinstance(future_reserve, Mapping):
        raise ValueError("V31 TARGET_READY future co-resident reserve is UNKNOWN")
    reserve_fields = (
        "remaining_transform_inverse_payload_bytes",
        "remaining_inverse_template_count",
        "future_inverse_single_operation_workspace_bytes",
        "future_krylov_and_vector_bytes",
        "future_full_p6_recovery_output_bytes",
        "selected_nonfactor_co_resident_phase_bytes",
        "future_co_resident_reserve_bytes",
    )
    if any(
        type(future_reserve.get(field)) is not int or future_reserve[field] < 0
        for field in reserve_fields
    ):
        raise ValueError("V31 TARGET_READY future co-resident components are not fully known")
    expected_phase = max(
        future_reserve["future_krylov_and_vector_bytes"]
        + future_reserve["future_inverse_single_operation_workspace_bytes"],
        future_reserve["future_full_p6_recovery_output_bytes"]
        + future_reserve["future_inverse_single_operation_workspace_bytes"],
    )
    if (
        expected_phase <= 0
        or future_reserve["selected_nonfactor_co_resident_phase_bytes"] != expected_phase
        or future_reserve["future_co_resident_reserve_bytes"]
        != future_reserve["remaining_transform_inverse_payload_bytes"] + expected_phase
    ):
        raise ValueError("V31 TARGET_READY future co-resident reserve does not close")
    return {
        "schema": "task40extra.review_v31_target_admission.v1",
        "phase": "TARGET_READY",
        "status": "TARGET_READY_INVENTORY_READY",
        "reference_full_storage_rows": reference_rows,
        "planned_target_full_storage_rows": planned_rows,
        "actual_target_full_storage_rows": actual_rows,
        "actual_target_owner_inventory": normalized,
        "unmeasured_target_owner_components": [
            name
            for name, row in normalized.items()
            if row["status"] == "unknown"
        ],
        "known_unique_payload_bytes_lower_bound": actual_owner_bytes,
        "complete_target_owner_bytes": (
            actual_owner_bytes
            if all(row["status"] == "measured" for row in normalized.values())
            else None
        ),
        "future_reserve": dict(future_reserve),
        "future_co_resident_reserve_bytes": future_reserve[
            "future_co_resident_reserve_bytes"
        ],
        "target_build_admitted": True,
        "target_ready": False,
    }


def _task40_v31_finalize_admission_after_resource_gate(
    candidate: Mapping[str, Any],
    resource_admission: Mapping[str, Any] | None,
    resource_sample: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Promote inventory readiness only after both live memory inequalities pass."""
    phases = {
        ("REFERENCE_ONLY", "REFERENCE_INVENTORY_READY"): "ADMITTED_REFERENCE_ONLY",
        ("TARGET_BUILD", "TARGET_BUILD_INVENTORY_READY"): "ADMITTED_TARGET_BUILD",
        ("TARGET_READY", "TARGET_READY_INVENTORY_READY"): "ADMITTED_TARGET_READY",
    }
    if not isinstance(candidate, Mapping):
        raise ValueError("V31 admission finalization requires a validated inventory candidate")
    phase_key = (candidate.get("phase"), candidate.get("status"))
    final_status = phases.get(phase_key)
    if final_status is None:
        raise ValueError("V31 admission candidate has an invalid phase/status")
    if (
        not isinstance(resource_admission, Mapping)
        or resource_admission.get("total_rss_inequality_passed") is not True
        or resource_admission.get("incremental_headroom_inequality_passed") is not True
        or not isinstance(resource_sample, Mapping)
        or type(resource_sample.get("rss_bytes")) is not int
        or resource_sample.get("rss_bytes") < 0
        or not isinstance(resource_sample.get("memory_envelope"), Mapping)
    ):
        raise ValueError(
            f"V31 {candidate.get('phase')} cannot be admitted before both resource inequalities and a sample pass"
        )
    return {
        **dict(candidate),
        "status": final_status,
        "resource_admission": dict(resource_admission),
        "resource_sample": dict(resource_sample),
        "target_build_admitted": (
            candidate.get("phase") in {"TARGET_BUILD", "TARGET_READY"}
        ),
        "target_ready": candidate.get("phase") == "TARGET_READY",
    }


def _task40_v30_resolve_sector_q_maps(
    coordinates: Any,
    sector_q_indices: tuple[int, int],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    prebuilt_q_maps_by_q: Mapping[int, Any] | None = None,
) -> dict[int, Any]:
    """Reuse owner-built sector maps, constructing maps only for legacy callers."""

    q_indices = tuple(int(q) for q in sector_q_indices)
    if len(q_indices) != 2 or len(set(q_indices)) != 2:
        raise ValueError("V30 sector maps require two distinct registered q indices")
    if prebuilt_q_maps_by_q is None:
        return {
            q: coordinates.q_map(branch, allocation_gate=allocation_gate)
            for branch, q in enumerate(q_indices)
        }
    if not isinstance(prebuilt_q_maps_by_q, Mapping):
        raise TypeError("prebuilt sector q maps must be a q-index mapping")
    q_maps = dict(prebuilt_q_maps_by_q)
    if set(q_maps) != set(q_indices):
        raise ValueError("prebuilt q maps do not match the live sector context")
    return q_maps


def _task40_v32_owner_bound_q_maps(
    route_facts: Any, local_owner: Mapping[str, Any]
) -> Mapping[int, Any] | None:
    """Return only the V32 maps whose saved-pattern audits passed in the owner."""

    if not isinstance(route_facts, Mapping) or route_facts.get("review_version") != "V32":
        return None
    q_maps = local_owner.get("q_maps_by_q")
    binding = local_owner.get("owner_receipt", {}).get("saved_q0_q4_map_binding")
    if (
        not isinstance(q_maps, Mapping)
        or set(q_maps) != {0, 4}
        or not isinstance(binding, Mapping)
        or any(
            not isinstance(binding.get(name), Mapping)
            or binding[name].get("passed") is not True
            for name in ("q0", "q4")
        )
    ):
        raise ValueError("V32 owner maps lack a passing saved q0/q4 binding audit")
    return q_maps


def _task40_v30_trace_rows_by_q(
    coordinates: Any,
    profile: Any,
    q_maps_by_q: Mapping[int, Any],
    sector_q_indices: tuple[int, int],
) -> dict[int, int]:
    """Bind each sector map's trace split to coordinate width and registered port rows."""

    q_indices = tuple(int(q) for q in sector_q_indices)
    port_counts = tuple(getattr(profile, "q_port_counts", ()))
    trace_rows = int(getattr(coordinates, "width", 0))
    if len(q_indices) != 2 or len(set(q_indices)) != 2 or trace_rows <= 0:
        raise ValueError("V30 sector trace split needs two q branches and positive coordinate width")
    result = {q: trace_rows for q in q_indices}
    for q in q_indices:
        if q < 0 or q >= len(port_counts) or q not in q_maps_by_q:
            raise ValueError("V30 sector trace split is outside the registered q profile")
        q_map = q_maps_by_q[q]
        if int(q_map.shape[1]) - trace_rows != int(port_counts[q]):
            raise ValueError(
                f"V30 q={q} map columns do not match coordinate trace width plus registered ports"
            )
    return result


def _task40_v30_q4_direct_hhat_evidence(
    *, repo_root: str | Path, producer_facts: Mapping[str, Any]
) -> dict[str, Any]:
    """Reuse the accepted twist-0 V26 internal B/D support audit for q4 direct-H."""

    from src.runners.task40_v29_contract import sha256_file

    root = Path(repo_root).resolve()
    compact_path = root / "docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v26.json"
    compact = json.loads(compact_path.read_text(encoding="utf-8"))
    reference = compact.get("raw_evidence", {}).get("selected_q_stage", {})
    if not isinstance(reference, Mapping):
        raise ValueError("V30 q4 direct-H has no pinned V26 support-stage reference")
    stage_path = Path(str(reference.get("path", "")))
    stage_path = (stage_path if stage_path.is_absolute() else root / stage_path).resolve()
    resolve_path = _task40_v30_artifact_path_resolver(root)
    stage_path = resolve_path(stage_path)
    if not stage_path.is_file() or sha256_file(stage_path) != reference.get("sha256"):
        raise ValueError("V26 twist-0 support-stage receipt is missing or changed")
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    surface = stage.get("complete_stream", {}).get("surface_functionals", {})
    raw_surface_path = surface.get("path")
    if not isinstance(raw_surface_path, str) or not raw_surface_path:
        raise ValueError("V26 twist-0 surface stream path is missing")
    mapped_surface_path = resolve_path(raw_surface_path)
    if not mapped_surface_path.is_relative_to(root):
        raise ValueError("V26 twist-0 surface stream escapes the approved execution root")
    counts = surface.get("internal_nonzero_entry_count", {})
    expected_surface_sha = producer_facts.get("payload_sha256", {}).get(
        "v25_selected_q0_surface_functionals.bin"
    )
    stage_identity = stage.get("v26_current_identity", {})
    if (
        stage.get("schema") != "task40extra.review_v25_selected_reference_q0_consumer.v1"
        or stage.get("status") != "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT"
        or surface.get("numeric_internal_support_empty") is not True
        or counts != {"B": 0, "D": 0}
        or surface.get("producer_identity_sha256")
        != producer_facts.get("producer_identity_sha256")
        or surface.get("sha256") != expected_surface_sha
        or stage_identity.get("producer_identity_sha256")
        != producer_facts.get("producer_identity_sha256")
    ):
        raise ValueError("accepted V26 twist-0 receipt does not prove empty internal B/D support")
    return {
        "numeric_internal_support_empty": True,
        "internal_B_nnz": 0,
        "internal_D_nnz": 0,
        "support_receipt_path": str(stage_path),
        "support_receipt_sha256": reference["sha256"],
        "support_receipt_source_sha": stage_identity.get("source_sha"),
        "surface_stream_path": str(mapped_surface_path),
        "surface_stream_path_raw": raw_surface_path,
        "surface_stream_sha256": surface.get("sha256"),
        "producer_identity_sha256": producer_facts.get("producer_identity_sha256"),
    }


def _task40_v30_open_saved_q4_native_witness(
    *,
    contract: Mapping[str, Any],
    repo_root: str | Path,
    operator_identity: Mapping[str, Any],
    current_execution_identity: Mapping[str, Any],
    input_sha256: str,
    physical_model_sha256: str,
    mode_manifest_sha256: str,
    ordered_mode_key_sha256: str,
    allocation_gate: Any,
) -> dict[str, Any]:
    """Read back the accepted V26 q4/q0 witness without rebuilding its old native actions."""

    from src.runners.task40_v29_contract import sha256_file
    from src.runners.task40_v10_campaign import TASK40_V28_CAMPAIGN_SHA256
    from src.solvers.task40_v30_qualified_q_csr import V28_Q0_DONOR_INPUT_SHA256
    import re
    from src.solvers.task40_v25_selected_q0 import (
        _load_v26_native_action,
        _load_v26_saved_replay_manifest,
    )

    root = Path(repo_root).resolve()
    preparation = contract.get("preparation")
    donor = preparation.get("accepted_q0_donor") if isinstance(preparation, Mapping) else None
    if not isinstance(donor, Mapping):
        raise ValueError("V30 q4 native reuse lacks the registered V28 donor")
    continuation_path = (root / str(donor.get("manifest_relative_path", ""))).resolve()
    if (
        not continuation_path.is_relative_to(root)
        or not continuation_path.is_file()
        or sha256_file(continuation_path) != donor.get("manifest_sha256")
    ):
        raise ValueError("V30 q4 native reuse V28 manifest is missing or changed")
    continuation = json.loads(continuation_path.read_text(encoding="utf-8"))
    fill = continuation.get("numeric_fill_identity")
    donor_identity = fill.get("donor_identity") if isinstance(fill, Mapping) else None
    fill_execution = fill.get("execution_identity") if isinstance(fill, Mapping) else None
    if not isinstance(donor_identity, Mapping) or not isinstance(fill_execution, Mapping):
        raise ValueError("V28 q4 donor omits its accepted V26 native/replay identity")
    if (
        operator_identity.get("scientific_input_sha256") != input_sha256
        or fill_execution.get("input_sha256") != V28_Q0_DONOR_INPUT_SHA256
        or fill_execution.get("campaign_window_sha256") != TASK40_V28_CAMPAIGN_SHA256
        or not re.fullmatch(r"[0-9a-f]{40}", str(fill_execution.get("source_sha", "")))
    ):
        raise ValueError("V26 native witness old V28 input/source/window identity differs from its pinned donor chain")
    for field, expected in (
        ("physical_model_sha256", physical_model_sha256),
        ("mode_manifest_sha256", mode_manifest_sha256),
        ("ordered_mode_key_sha256", ordered_mode_key_sha256),
    ):
        if fill_execution.get(field) != expected:
            raise ValueError(f"V26 native witness {field} differs from the live V30 operator")
    producer_identity = donor_identity.get("producer_identity")
    producer_identity_sha256 = donor_identity.get("producer_identity_sha256")
    native_ref = donor_identity.get("native_recovery_manifest")
    checker_ref = donor_identity.get("native_recovery_checker")
    replay_ref = donor_identity.get("saved_replay_manifest")
    native_cases_ref = donor_identity.get("native_cases")
    if (
        not isinstance(producer_identity, Mapping)
        or not isinstance(producer_identity_sha256, str)
        or not all(isinstance(item, Mapping) for item in (native_ref, checker_ref, replay_ref, native_cases_ref))
    ):
        raise ValueError("V28 donor has no complete native recovery provenance")
    resolve_path = _task40_v30_artifact_path_resolver(root)
    native_path = resolve_path(str(native_ref.get("path", "")))
    checker_path = resolve_path(str(checker_ref.get("path", "")))
    replay_path = resolve_path(str(replay_ref.get("path", "")))
    for label, path, record in (
        ("native recovery", native_path, native_ref),
        ("native checker", checker_path, checker_ref),
        ("saved replay", replay_path, replay_ref),
    ):
        if (
            not path.is_file()
            or sha256_file(path) != record.get("sha256")
            or record.get("status") not in (
                "PASS_RECOVERED_THREE_NATIVE_CASES",
                "PASS_READONLY_THREE_CASE_RECOVERY",
                "PASS_SAVED_STREAM_REPLAY_NO_NATIVE",
            )
        ):
            raise ValueError(f"V26 {label} evidence is missing or differs from V28")
    recovery_manifest = json.loads(native_path.read_text(encoding="utf-8"))
    checker_recorded_path = resolve_path(
        str(recovery_manifest.get("recovery_checker_receipt_path", ""))
    )
    if (
        recovery_manifest.get("schema")
        != "task40extra.review_v26_native_action_recovery.v1"
        or recovery_manifest.get("status") != "PASS_RECOVERED_THREE_NATIVE_CASES"
        or checker_recorded_path != checker_path
        or recovery_manifest.get("recovery_checker_receipt_sha256")
        != checker_ref.get("sha256")
    ):
        raise ValueError("V26 recovery manifest does not bind the accepted independent checker")
    checker = json.loads(checker_path.read_text(encoding="utf-8"))
    recovery_identity = recovery_manifest.get("recovery_current_identity")
    if (
        checker.get("schema") != "task40extra.review_v26_native_case_recovery_check.v1"
        or checker.get("status") != "PASS_READONLY_THREE_CASE_RECOVERY"
        or checker.get("checker_passed") is not True
        or checker.get("producer_identity_sha256") != producer_identity_sha256
        or checker.get("saved_replay_manifest_sha256") != replay_ref.get("sha256")
        or checker.get("recovery_current_identity") != recovery_identity
    ):
        raise ValueError("V26 independent read-only native recovery checker did not pass")
    replay_payload = replay_ref.get("artifacts", {})
    if not isinstance(replay_payload, Mapping):
        raise ValueError("V28 saved replay reference omits its artifact inventory")
    estimated_read_bytes = sum(
        int(item.get("bytes", 0))
        for item in list(native_cases_ref.values()) + list(replay_payload.values())
        if isinstance(item, Mapping)
    )
    allocation_gate(
        "task40_v30_q4_v26_saved_native_witness_readback",
        {
            "additional_payload_bytes": estimated_read_bytes,
            "workspace_bytes": 64 * 1024**2,
            "native_manifest_sha256": native_ref.get("sha256"),
            "replay_manifest_sha256": replay_ref.get("sha256"),
            "checker_sha256": checker_ref.get("sha256"),
            "read_only": True,
        },
    )
    native_manifest, native_loaded = _load_v26_native_action(
        native_path.parent,
        producer_identity_sha256=producer_identity_sha256,
        replay_manifest_sha256=str(replay_ref.get("sha256", "")),
        manifest_path=native_path,
        recovery_identity=recovery_identity,
    )
    replay_manifest, replay_paths = _load_v26_saved_replay_manifest(
        replay_path.parent, producer_identity
    )
    if (
        native_manifest.get("manifest_sha256") != native_ref.get("sha256")
        or replay_manifest.get("manifest_sha256") != replay_ref.get("sha256")
        or native_manifest.get("recovery_checker_receipt_sha256") != checker_ref.get("sha256")
    ):
        raise ValueError("V26 loader readback differs from the V28 pinned native/replay evidence")
    for case_name, compact in native_cases_ref.items():
        actual = native_manifest.get("cases", {}).get(case_name)
        if not isinstance(actual, Mapping) or any(
            actual.get(key) != compact.get(key)
            for key in ("bytes", "sha256", "array_sha256", "array_shapes")
        ) or Path(str(actual.get("path", ""))).name != Path(str(compact.get("path", ""))).name:
            raise ValueError(f"V26 native case differs from the V28 compact: {case_name}")
    input_path = replay_paths["inputs"]
    with np.load(input_path, allow_pickle=False) as archive:
        q4_input = np.asarray(archive["q4_pair"]).copy()
        q0_input = np.asarray(archive["q0_case_1"]).copy()
    q4_case = native_loaded["q4_pair"]
    q0_case = native_loaded["q0_case_1"]
    arrays = {
        "case1_full_input": q4_input,
        "case1_full_output": q4_case["native_q4_total"],
        "selected_to_peer_cross": q4_case["native_q0_from_q4"],
        "peer_case1_input": q0_input,
        "peer_case1_output": q0_case["native_q0_total"],
        "peer_to_selected_cross": q0_case["native_q4_from_q0"],
    }
    replay_inputs_sidecar = json.loads(input_path.with_suffix(".json").read_text(encoding="utf-8"))
    input_current_identity = replay_inputs_sidecar.get("current_identity", {})
    native_current_identity = native_manifest.get("native_current_identity", {})
    replay_input_record = replay_manifest["artifacts"]["inputs"]
    array_references = {}
    for name, (path, artifact, array_name, source_sha) in {
        "case1_full_input": (
            input_path, replay_input_record, "q4_pair", input_current_identity.get("source_sha")
        ),
        "peer_case1_input": (
            input_path, replay_input_record, "q0_case_1", input_current_identity.get("source_sha")
        ),
        "case1_full_output": (
            native_path.parent / native_manifest["cases"]["q4_pair"]["path"],
            native_manifest["cases"]["q4_pair"], "native_q4_total", native_current_identity.get("source_sha")
        ),
        "selected_to_peer_cross": (
            native_path.parent / native_manifest["cases"]["q4_pair"]["path"],
            native_manifest["cases"]["q4_pair"], "native_q0_from_q4", native_current_identity.get("source_sha")
        ),
        "peer_case1_output": (
            native_path.parent / native_manifest["cases"]["q0_case_1"]["path"],
            native_manifest["cases"]["q0_case_1"], "native_q0_total", native_current_identity.get("source_sha")
        ),
        "peer_to_selected_cross": (
            native_path.parent / native_manifest["cases"]["q0_case_1"]["path"],
            native_manifest["cases"]["q0_case_1"], "native_q4_from_q0", native_current_identity.get("source_sha")
        ),
    }.items():
        value = np.asarray(arrays[name])
        array_sha256 = hashlib.sha256(
            np.ascontiguousarray(value).view(np.uint8)
        ).hexdigest()
        array_references[name] = {
            "path": str(path),
            "artifact_sha256": artifact.get("sha256"),
            "array_name": array_name,
            "array_sha256": array_sha256,
            "artifact_source_sha": source_sha,
            "recovery_source_sha": recovery_identity.get("source_sha"),
            "producer_identity_sha256": producer_identity_sha256,
        }
    native_manifest["original_manifest_path"] = str(native_path)
    native_manifest["original_recovery_checker_receipt_path"] = str(
        native_manifest.get("recovery_checker_receipt_path", "")
    )
    native_manifest["recovery_checker_receipt_path"] = str(checker_path)
    replay_manifest["original_manifest_path"] = str(replay_path)
    return {
        "schema": "task40extra.review_v30_selected_q_saved_native_reuse.v1",
        "operator_identity": dict(operator_identity),
        "v28_fill_execution_identity": dict(fill_execution),
        "v30_execution_identity": dict(current_execution_identity),
        "current_identity": dict(recovery_identity),
        "expected_current_identity": dict(current_execution_identity),
        "native_manifest": native_manifest,
        "native_manifest_sha256": native_ref["sha256"],
        "saved_replay_manifest": replay_manifest,
        "saved_replay_manifest_sha256": replay_ref["sha256"],
        "producer_identity_sha256": producer_identity_sha256,
        "donor_verifier_receipt": checker,
        "donor_verifier_receipt_path": str(checker_path),
        "donor_verifier_receipt_sha256": checker_ref["sha256"],
        "array_references": array_references,
        "arrays": {
            name: {
                "value": np.asarray(value),
                "sha256": array_references[name]["array_sha256"],
            }
            for name, value in arrays.items()
        },
    }


def _task40_v30_sector_builder_inputs(
    *,
    global_bundle: Mapping[str, Any],
    mode_inventory: tuple[Any, Any, str],
    coordinates: Any,
    profile: Any,
    q_maps_by_q: Mapping[int, Any],
    sector_q_indices: tuple[int, int],
) -> dict[str, Any]:
    """Bind the reference mode identity and per-q trace split passed to CSR builders."""

    if (
        not isinstance(global_bundle, Mapping)
        or not isinstance(mode_inventory, tuple)
        or len(mode_inventory) != 3
        or str(global_bundle.get("mode_sha256", "")) != str(mode_inventory[2])
    ):
        raise ValueError("V30 reference sector mode identity differs from its frozen inventory")
    return {
        "mode_manifest_sha256": str(mode_inventory[2]),
        "trace_rows_by_q": _task40_v30_trace_rows_by_q(
            coordinates, profile, q_maps_by_q, sector_q_indices
        ),
    }


def _task40_v30_build_target_after_reference(
    *,
    reference_owner: Mapping[str, Any],
    regular_checks: Mapping[str, Any],
    mode_inventory: tuple[Any, Any, str],
    target_builder: Any,
) -> Any:
    """Build the target only after the reference passed and supplied frozen modes."""

    if not callable(target_builder) or regular_checks.get("passed") is not True:
        raise ValueError("V30 target construction requires a qualified regular reference")
    bundle = reference_owner.get("global_bundle")
    if (
        not isinstance(bundle, Mapping)
        or not isinstance(mode_inventory, tuple)
        or len(mode_inventory) != 3
        or str(bundle.get("mode_sha256", "")) != str(mode_inventory[2])
    ):
        raise ValueError("V30 qualified reference does not carry the frozen physical mode identity")
    return target_builder(
        reference_owner=reference_owner, mode_inventory=mode_inventory
    )


def _task40_sector_port_vectors(
    mode_indices: Any,
    *,
    replication_count: int,
    global_h: Any | None = None,
    global_port_rhs: Any | None = None,
    global_alpha: Any | None = None,
) -> dict[str, np.ndarray]:
    """Convert global port vectors to one of the K normalized two-cell sectors."""

    if type(replication_count) is not int or replication_count < 1:
        raise ValueError("p6 sector replication count K must be a positive integer")
    ids = np.asarray(mode_indices, dtype=np.int64)
    if ids.ndim != 1 or (len(ids) and np.any(ids < 0)):
        raise ValueError(
            "p6 sector mode indices must be a one-dimensional nonnegative vector"
        )
    root_k = np.sqrt(float(replication_count))
    result: dict[str, np.ndarray] = {}
    for name, raw in (
        ("local_h", global_h),
        ("local_port_rhs", global_port_rhs),
        ("local_alpha", global_alpha),
    ):
        if raw is None:
            continue
        dtype = np.float64 if name == "local_h" else np.complex128
        vector = np.asarray(raw, dtype=dtype)
        if (
            vector.ndim != 1
            or (len(ids) and int(ids.max()) >= len(vector))
            or not np.isfinite(vector).all()
            or (name == "local_h" and np.any(vector <= 0.0))
        ):
            raise ValueError(
                f"global vector for {name} does not cover the selected p6 modes"
            )
        selected = vector[ids]
        if name == "local_h":
            result[name] = selected / float(replication_count)
        elif name == "local_port_rhs":
            result[name] = selected / root_k
        else:
            result[name] = selected * root_k
    return result


def _task40_reference_replication_count(reference: Mapping[str, Any]) -> int:
    """Require the registered profile K to match every actual two-cell transport."""

    profile = reference["profile"]
    replication_count = int(profile.replication_count)
    sectors = tuple(reference["sectors"])
    if (
        replication_count < 1
        or not sectors
        or any(int(sector["transport"].K) != replication_count for sector in sectors)
    ):
        raise ValueError(
            "registered p6 profile K differs from its actual two-cell transports"
        )
    return replication_count


def _single_side_diffraction_order_count_passed(
    output: Mapping[str, Any], total_port_mode_count: int
) -> bool:
    """Compare the one-face diffraction count with the two-face port inventory.

    Field postprocessing counts each spatial/polarization order once, while the
    DtN profile counts those orders on both the top and bottom ports.
    """
    total_count = int(total_port_mode_count)
    return bool(
        total_count > 0
        and total_count % 2 == 0
        and output.get("diffraction_channel_count") == total_count // 2
    )


def _reference_pc_final_identity_pass(
    reference_pc_final_gate: Mapping[str, Any], identity_metrics: Mapping[str, Any]
) -> bool:
    """Retain the parent alpha and q checks using the strategy's explicit limits."""

    def finite_within(metric: Any, limit: Any) -> bool:
        try:
            value = float(metric)
            bound = float(limit)
        except (TypeError, ValueError, OverflowError):
            return False
        return bool(np.isfinite(value) and np.isfinite(bound) and value <= bound)

    return bool(
        reference_pc_final_gate.get("passed") is True
        and finite_within(
            identity_metrics.get("reference_pc_port_identity_relative"),
            reference_pc_final_gate.get("port_identity_limit", -1.0),
        )
        and finite_within(
            identity_metrics.get("maximum_q_true_residual_relative"),
            reference_pc_final_gate.get("q_true_residual_limit", -1.0),
        )
    )


def _v12_memory_admission_bounds(
    *,
    live_rss_bytes: int,
    total_rss_cap_bytes: int,
    incremental_headroom_bytes: int,
    delta_bytes: int,
    reserve_bytes: int,
) -> dict[str, int | bool | str]:
    """Keep absolute tree RSS and incremental system headroom as separate gates."""
    live = int(live_rss_bytes)
    total_cap = int(total_rss_cap_bytes)
    headroom = int(incremental_headroom_bytes)
    delta = int(delta_bytes)
    reserve = int(reserve_bytes)
    if min(live, total_cap, delta, reserve) < 0:
        raise ValueError("memory admission quantities except available headroom must be nonnegative")
    required_increment = delta + reserve
    projected_rss = live + required_increment
    return {
        "total_rss_inequality": "R_live + Delta + reserve <= C_total",
        "total_rss_inequality_passed": projected_rss <= total_cap,
        "incremental_headroom_inequality": "Delta + reserve <= H_physical_or_cgroup",
        "incremental_headroom_inequality_passed": required_increment <= headroom,
        "projected_process_tree_rss_bytes": projected_rss,
        "projected_incremental_capacity_bytes": required_increment,
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _v16_unique_array_owner_inventory(named_arrays: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize named NumPy borrowers by their unique backing ndarray owner."""
    owners: dict[int, dict[str, Any]] = {}
    array_reference_count = 0
    for name, value in named_arrays.items():
        if not isinstance(value, np.ndarray):
            continue
        array_reference_count += 1
        root = value
        while isinstance(getattr(root, "base", None), np.ndarray):
            root = root.base
        key = id(root)
        row = owners.setdefault(
            key,
            {
                "owner_token": f"ndarray-owner-{key:x}",
                "backing_bytes": int(root.nbytes),
                "dtype": str(root.dtype),
                "shape": list(root.shape),
                "names": [],
            },
        )
        row["names"].append(str(name))
    ordered = sorted(owners.values(), key=lambda row: (-row["backing_bytes"], row["owner_token"]))
    aliases = [row for row in ordered if len(row["names"]) > 1]
    return {
        "named_array_reference_count": array_reference_count,
        "unique_backing_buffer_count": len(owners),
        "unique_backing_bytes": int(sum(row["backing_bytes"] for row in owners.values())),
        "alias_group_count": len(aliases),
        "alias_reference_count": int(sum(len(row["names"]) - 1 for row in aliases)),
        "largest_backing_buffers": [
            {**row, "names": row["names"][:4]} for row in ordered[:12]
        ],
    }


def _v16_csr_owner_inventory(
    matrices: Mapping[Any, Any],
    *,
    numeric_nonzero_by_key: Mapping[str, int] | None = None,
    version: str = "v16",
) -> dict[str, Any]:
    """Report stored slots, numerical nonzeros, visible payload, and unique backing owners."""
    named_arrays: dict[str, np.ndarray] = {}
    by_block: dict[str, Any] = {}
    for key, matrix in matrices.items():
        label = "".join(map(str, key)) if isinstance(key, tuple) else str(key)
        arrays = {
            "data": matrix.data,
            "indices": matrix.indices,
            "indptr": matrix.indptr,
        }
        for field, array in arrays.items():
            named_arrays[f"block{label}.{field}"] = array
        stored = int(matrix.nnz)
        numeric = (
            int(numeric_nonzero_by_key[label])
            if numeric_nonzero_by_key is not None and label in numeric_nonzero_by_key
            else int(np.count_nonzero(matrix.data))
        )
        by_block[label] = {
            "shape": list(matrix.shape),
            "stored_slots": stored,
            "numeric_nonzero_entries": numeric,
            "exact_zero_slots_retained": stored - numeric,
            "visible_csr_payload_bytes": int(
                matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
            ),
            "canonical": bool(matrix.has_canonical_format and matrix.has_sorted_indices),
        }
    return {
        "schema": f"task40extra.review_{version}_csr_owner_inventory.v1",
        "by_block": by_block,
        "unique_array_backings": _v16_unique_array_owner_inventory(named_arrays),
        "zero_cleanup": "not_applied; no array owner copy or RSS reduction claimed",
    }


def _allocation_gate_summary_key(label: str) -> str:
    text = str(label)
    if "all_q_symbolic_before_any_numeric" in text:
        return "all_q_symbolic_before_any_numeric"
    if "before_full_p6" in text or "full_p6_post_release" in text:
        return "full_p6_output"
    if text.startswith("task40_v16_q_"):
        return text.split("/", 1)[0]
    if text.startswith("p6_reduced_contribution/"):
        parts = text.split("/")
        return "/".join(parts[:2])
    if "symbolic" in text:
        return "symbolic_other"
    if "numeric" in text or "factor" in text:
        return "numeric_factor_other"
    if "sector" in text:
        return "sector_other"
    if "target" in text:
        return "target_other"
    return text.split("/", 1)[0][:64]


def _v18_full_native_matrix_admission_facts(
    label: str, facts: Mapping[str, Any], *, header_path: Path
) -> dict[str, Any] | None:
    """Keep the narrow V18 native-matrix admission facts in raw evidence."""
    text = str(label)
    if not text.startswith("task40_v18_full_native_volume_matrix_"):
        return None
    path = Path(header_path)
    header_exists = path.is_file()
    return {
        "schema": "task40extra.review_v18_mpc_sparsity_basis.v1",
        "backend_pattern_rule": (
            "retain raw cell row/column dofs and append MPC masters to the cell pattern"
        ),
        "header_path": str(path),
        "header_sha256": (
            hashlib.sha256(path.read_bytes()).hexdigest() if header_exists else None
        ),
        "header_exists": header_exists,
        "header_source_range": "dolfinx_mpc/utils.h:create_sparsity_pattern",
        "admission_facts": dict(facts),
    }


def _v18_preproject_native_matrix_gate(
    runtime: Any,
    label: str,
    facts: Mapping[str, Any],
    *,
    amount_bytes: int,
    workspace_bytes: int,
    header_path: Path,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    """Write V18 matrix facts before projected admission can raise."""
    snapshot = _v18_full_native_matrix_admission_facts(
        label, facts, header_path=header_path
    )
    if snapshot is None:
        raise ValueError("V18 preprojection recorder received a non-matrix gate")
    runtime.marker(
        "v18_full_native_matrix_admission_input",
        {"label": str(label), **snapshot},
    )
    if not snapshot["header_exists"]:
        raise FileNotFoundError(
            f"V18 MPC sparsity contract header is missing: {snapshot['header_path']}"
        )
    checked = runtime.check_projected(
        f"v10_{label}", int(amount_bytes), workspace_bytes=int(workspace_bytes)
    )
    return snapshot, checked


def _event_file_identity(path: Path) -> dict[str, int | str]:
    digest = hashlib.sha256()
    total_records = admission_records = completion_records = 0
    with path.open("rb") as stream:
        for line in stream:
            digest.update(line)
            total_records += 1
            if b'"event":"v10_strict_allocation_admission"' in line:
                admission_records += 1
            elif b'"event":"v10_strict_allocation_admission_complete"' in line:
                completion_records += 1
    return {
        "size_bytes": int(path.stat().st_size),
        "sha256": digest.hexdigest(),
        "record_count": total_records,
        "allocation_admission_event_count": admission_records,
        "allocation_admission_complete_event_count": completion_records,
    }


def _regular_inverse_sample_label(case: str, candidate_label: str) -> str:
    if candidate_label == "initial":
        return f"v10_regular_inverse_{case}"
    return f"v13_regular_inverse_{case}_{candidate_label}"


def _v19_factor_capabilities(inverse: Any) -> Mapping[str, Any] | None:
    factors = getattr(inverse, "factors", None)
    if getattr(factors, "factor_lifecycle_strategy", None) != "ONE_Q_REFACTOR_V19":
        return None
    capabilities = getattr(factors, "capabilities", None)
    if not callable(capabilities):
        raise TypeError("V19 factor backend must expose its explicit lifecycle capability")
    return capabilities()


def _v19_sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _v19_prepare_saved_v18_startup_reference(
    reference: Mapping[str, Any], profile: Any
) -> dict[str, Any] | None:
    """Bind V18 startup witnesses except for the registered V19 E1 q4 route."""

    # E1 has four Floquet q blocks and no same-discrete V18 Ny8 witness.
    # Keep this exception limited to its exact registered profile and q count.
    if (
        getattr(profile, "name", None)
        == "task40extra_v17_p6_y_orbit_e1_reference_v1"
        and int(profile.q_count) == 4
    ):
        return None

    reuse = reference.get("complete_operator_qualification_reuse")
    if not isinstance(reuse, Mapping) or reuse.get("status") != (
        "REUSED_AFTER_FRESH_Q_HASH_AND_INDEPENDENT_CHECKER_PASS"
    ):
        raise ValueError("V19 startup comparison requires the qualified V18 Ny8 reuse receipt")
    if (
        reuse.get("qualified_source_sha") != "3b9457e57ceb15f21306a35baac07f42036840b1"
        or reuse.get("qualified_status") != "PASS"
        or reuse.get("input_differences_are_run_id_and_factor_lifecycle_only") is not True
        or reuse.get("all_eight_fresh_q_hashes_match") is not True
    ):
        raise ValueError("V19 startup comparison is not bound to the passed V18 Ny8 attempt")
    q_hashes = reuse.get("fresh_q_matrix_sha256")
    expected_qs = {str(q) for q in range(int(profile.q_count))}
    if not isinstance(q_hashes, Mapping) or set(q_hashes) != expected_qs:
        raise ValueError("V19 startup comparison lacks the exact all-q CSR identity map")

    repo_root = Path(__file__).resolve().parents[2]
    run_root = Path(str(reuse.get("qualified_run_root", ""))).resolve(strict=True)
    if not run_root.is_relative_to(repo_root):
        raise ValueError("qualified V18 startup evidence must remain inside the repository")
    summary_path = Path(str(reuse.get("qualified_candidate_summary_path", ""))).resolve(strict=True)
    manifest_path = Path(str(reuse.get("qualified_run_manifest_path", ""))).resolve(strict=True)
    if (
        summary_path.parent != run_root
        or summary_path.name != "task40_v10_p6_candidate_summary.json"
        or manifest_path != run_root / "run_manifest.json"
    ):
        raise ValueError("V18 candidate summary and run manifest are not from the qualified run root")
    summary_sha256 = _v19_sha256_path(summary_path)
    manifest_sha256 = _v19_sha256_path(manifest_path)
    if (
        summary_sha256 != reuse.get("qualified_candidate_summary_sha256")
        or manifest_sha256 != reuse.get("qualified_run_manifest_sha256")
    ):
        raise ValueError("V18 startup comparison run identities differ from the qualified hashes")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_input_path = run_root / "input_original.dat"
    old_input_sha256 = _v19_sha256_path(old_input_path)
    if (
        manifest.get("run_id") != "task40extra_0p7nm_b0_p6_reference_v18_ny8"
        or manifest.get("source_sha") != reuse.get("qualified_source_sha")
        or manifest.get("physical_model_sha256") != reuse.get("physical_model_sha256")
        or manifest.get("input_sha256") != old_input_sha256
    ):
        raise ValueError("V18 saved startup witness does not bind its original run/input identity")
    if (
        int(profile.q_count) != 8
        or reuse.get("profile_identity") != profile.name
        or not isinstance(reuse.get("input_sha256"), str)
        or len(reuse["input_sha256"]) != 64
    ):
        raise ValueError("V19 startup comparison is outside the registered Ny8 input identity")
    return {
        "run_root": run_root,
        "old_source_sha": str(manifest["source_sha"]),
        "old_input_sha256": old_input_sha256,
        "current_input_sha256": str(reuse["input_sha256"]),
        "physical_model_sha256": str(manifest["physical_model_sha256"]),
        "candidate_summary_sha256": summary_sha256,
        "run_manifest_sha256": manifest_sha256,
        "fresh_q_matrix_sha256": dict(q_hashes),
        "current_source_sha": reuse.get("current_source_sha"),
        "target_mode_sha256": reuse.get("target_mode_sha256"),
        "profile_identity": profile.name,
    }


def _v19_compare_saved_v18_startup_case(
    prepared: Mapping[str, Any],
    *,
    case: str,
    profile: Any,
    independent_rows: Any,
    current_rhs_storage: Any,
    current_port_rhs: Any,
    current_solution_storage: Any,
    current_alpha: Any,
    current_q_rows: Any,
    current_regular_residual: float,
    current_regular_gate_passed: bool,
    allocation_gate: Any,
) -> dict[str, Any]:
    """Read back an existing V18 witness and record the V19 same-input deltas."""

    if case not in {"generic_full_independent", "nonzero_all_mode_port_rhs"}:
        raise ValueError(f"unsupported V19 saved V18 comparison case: {case!r}")
    run_root = Path(prepared["run_root"])
    stem = f"v10_regular_inverse_{case}"
    witness_json_path = (run_root / f"{stem}.json").resolve(strict=True)
    witness_npz_path = (run_root / f"{stem}.npz").resolve(strict=True)
    if not witness_json_path.is_relative_to(run_root) or not witness_npz_path.is_relative_to(run_root):
        raise ValueError("V18 startup witness paths escaped their qualified run root")
    witness_json_bytes = witness_json_path.read_bytes()
    witness_json_sha256 = hashlib.sha256(witness_json_bytes).hexdigest()
    witness = json.loads(witness_json_bytes)
    witness_npz_sha256 = _v19_sha256_path(witness_npz_path)
    archive_facts = witness.get("arrays")
    if (
        witness.get("schema") != "task40extra.review_v15_regular_inverse_full_witness.v1"
        or witness.get("case") != case
        or witness.get("profile_identity") != profile.name
        or witness.get("passed") is not True
        or witness.get("reference_pc_strategy") != "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
        or witness.get("full_storage_rows") != len(current_rhs_storage)
        or not isinstance(archive_facts, Mapping)
        or Path(str(archive_facts.get("path", ""))).resolve() != witness_npz_path
        or archive_facts.get("sha256") != witness_npz_sha256
    ):
        raise ValueError("V18 saved startup witness failed its schema, identity, or NPZ hash check")

    old_full_rows = np.asarray(independent_rows, dtype=np.int64)
    current_rhs = np.asarray(current_rhs_storage, dtype=np.complex128)
    current_ports = np.asarray(current_port_rhs, dtype=np.complex128)
    current_solution = np.asarray(current_solution_storage, dtype=np.complex128)
    current_amplitudes = np.asarray(current_alpha, dtype=np.complex128)
    allocation_gate(
        "task40_v19_saved_v18_startup_witness_readback",
        {
            "additional_payload_bytes": int(
                3 * current_rhs.size * np.dtype(np.complex128).itemsize
                + old_full_rows.size * np.dtype(np.int64).itemsize
                + 3 * current_ports.size * np.dtype(np.complex128).itemsize
                + (1 << 20)
            ),
            "workspace_bytes": 0,
            "qualified_v18_witness_npz_bytes": int(witness_npz_path.stat().st_size),
            "loads_only_full_solution_rhs_alpha_and_row_index_arrays": True,
        },
    )

    def read_array(archive: Any, field: str, dtype: Any, shape: tuple[int, ...]) -> np.ndarray:
        facts = witness.get(field)
        if not isinstance(facts, Mapping):
            raise ValueError(f"V18 witness is missing array reference {field!r}")
        key = facts.get("array_key")
        if not isinstance(key, str) or key not in archive.files:
            raise ValueError(f"V18 witness array reference {field!r} is not in its NPZ")
        value = np.asarray(archive[key])
        if value.dtype != np.dtype(dtype) or value.shape != shape:
            raise ValueError(f"V18 witness array {field!r} has a mismatched dtype or shape")
        if facts.get("dtype") != value.dtype.name or facts.get("shape") != list(value.shape):
            raise ValueError(f"V18 witness array metadata differs for {field!r}")
        if not np.isfinite(value).all():
            raise ValueError(f"V18 witness array {field!r} contains a non-finite value")
        return value

    with np.load(witness_npz_path, allow_pickle=False) as archive:
        old_independent = read_array(
            archive, "independent_storage_rows", np.int64, old_full_rows.shape
        )
        old_rhs_storage = read_array(
            archive, "physical_rhs_storage", np.complex128, current_rhs.shape
        )
        old_port_rhs = read_array(
            archive, "port_rhs", np.complex128, current_ports.shape
        )
        old_solution = read_array(
            archive, "full_solution_storage", np.complex128, current_solution.shape
        )
        old_alpha = read_array(
            archive, "returned_alpha", np.complex128, current_amplitudes.shape
        )
        if (
            not np.array_equal(old_independent, old_full_rows)
            or not np.array_equal(old_rhs_storage, current_rhs)
            or not np.array_equal(old_port_rhs, current_ports)
        ):
            raise ValueError("V19 startup comparison does not reproduce the exact V18 FE/port RHS")
        field_difference = current_solution - old_solution
        alpha_difference = current_amplitudes - old_alpha
        field_delta_norm = float(np.linalg.norm(field_difference))
        alpha_delta_norm = float(np.linalg.norm(alpha_difference))
        old_field_norm = float(np.linalg.norm(old_solution))
        old_alpha_norm = float(np.linalg.norm(old_alpha))

        def reference_relative(delta: float, reference_norm: float) -> float:
            if reference_norm > 0.0:
                return delta / reference_norm
            return 0.0 if delta == 0.0 else float("inf")

        old_q_rows = witness.get("q_true_residuals")
        if not isinstance(old_q_rows, list) or len(old_q_rows) != int(profile.q_count):
            raise ValueError("V18 saved startup witness omits its complete q residual list")
        current_q_rows = list(current_q_rows)

        def by_q(rows: list[Mapping[str, Any]], label: str) -> dict[int, Mapping[str, Any]]:
            result: dict[int, Mapping[str, Any]] = {}
            for row in rows:
                if not isinstance(row, Mapping) or type(row.get("q")) is not int:
                    raise ValueError(f"{label} q residual rows are malformed")
                q = int(row["q"])
                if q in result:
                    raise ValueError(f"{label} q residual rows contain duplicate q={q}")
                result[q] = row
            if set(result) != set(range(int(profile.q_count))):
                raise ValueError(f"{label} q residual rows do not cover every Ny8 phase")
            return result

        old_by_q = by_q(old_q_rows, "V18")
        current_by_q = by_q(current_q_rows, "V19")
        per_q = {
            str(q): {
                "old_rhs_norm": float(old_by_q[q]["rhs_norm"]),
                "current_rhs_norm": float(current_by_q[q]["rhs_norm"]),
                "old_true_residual_relative": float(
                    old_by_q[q]["true_residual_relative"]
                ),
                "current_true_residual_relative": float(
                    current_by_q[q]["true_residual_relative"]
                ),
                "old_strict_passed": old_by_q[q].get("strict_passed"),
                "current_strict_passed": current_by_q[q].get("strict_passed"),
            }
            for q in range(int(profile.q_count))
        }
        rhs_digest = lambda value: hashlib.sha256(
            np.ascontiguousarray(value).view(np.uint8)
        ).hexdigest()
        return {
            "schema": "task40extra.review_v19_saved_v18_startup_comparison.v1",
            "case": case,
            "status": "SAME_INPUT_COMPARISON_RECORDED",
            "old_run_id": "task40extra_0p7nm_b0_p6_reference_v18_ny8",
            "old_source_sha": prepared["old_source_sha"],
            "old_input_sha256": prepared["old_input_sha256"],
            "current_source_sha": prepared["current_source_sha"],
            "current_input_sha256": prepared["current_input_sha256"],
            "physical_model_sha256": prepared["physical_model_sha256"],
            "target_mode_sha256": prepared["target_mode_sha256"],
            "profile_identity": prepared["profile_identity"],
            "old_candidate_summary_sha256": prepared["candidate_summary_sha256"],
            "old_run_manifest_sha256": prepared["run_manifest_sha256"],
            "old_witness_json_path": str(witness_json_path),
            "old_witness_json_sha256": witness_json_sha256,
            "old_witness_npz_path": str(witness_npz_path),
            "old_witness_npz_sha256": witness_npz_sha256,
            "fresh_q_matrix_sha256": dict(prepared["fresh_q_matrix_sha256"]),
            "same_independent_row_order": True,
            "same_fe_rhs_storage": True,
            "same_port_rhs": True,
            "input_differences_are_run_id_and_factor_lifecycle_only": True,
            "old_fe_rhs_storage_sha256": rhs_digest(old_rhs_storage),
            "current_fe_rhs_storage_sha256": rhs_digest(current_rhs),
            "old_port_rhs_sha256": rhs_digest(old_port_rhs),
            "current_port_rhs_sha256": rhs_digest(current_ports),
            "full_solution_absolute_l2_delta": field_delta_norm,
            "full_solution_relative_to_v18_l2_delta": reference_relative(
                field_delta_norm, old_field_norm
            ),
            "returned_alpha_absolute_l2_delta": alpha_delta_norm,
            "returned_alpha_relative_to_v18_l2_delta": reference_relative(
                alpha_delta_norm, old_alpha_norm
            ),
            "old_original_fe_equation_relative_residual": float(
                witness["original_regular_equation_relative_residual"]
            ),
            "current_original_fe_equation_relative_residual": float(
                current_regular_residual
            ),
            "current_existing_regular_gate_passed": bool(current_regular_gate_passed),
            "per_q_true_residuals": per_q,
            "all_old_q_strict_passed": all(
                row.get("strict_passed") is True for row in old_by_q.values()
            ),
            "all_current_q_strict_passed": all(
                row.get("strict_passed") is True for row in current_by_q.values()
            ),
            "field_and_alpha_deltas_are_diagnostic_only": True,
            "no_new_floating_delta_threshold_applied": True,
        }


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    from .physical_p4_schur_v14 import _append_jsonl as append

    append(path, row)


def _packet_array_bytes(value: Any) -> int:
    if isinstance(value, np.ndarray):
        return int(value.nbytes)
    if isinstance(value, Mapping):
        return sum(_packet_array_bytes(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return sum(_packet_array_bytes(item) for item in value)
    return 0


def _raw_artifact_bytes(directory: Path) -> int:
    ignored = {"_events.jsonl", "_worker_resources.jsonl"}
    total = 0
    for path in directory.rglob("*"):
        if path.is_file() and not any(path.name.endswith(suffix) for suffix in ignored):
            total += path.stat().st_size
    return total


def _disk_admit(runtime: Any, *, additional_bytes: int, label: str) -> dict[str, int]:
    """Keep every run below the raw-output and free-space limits before writes."""
    additional = int(additional_bytes)
    if additional < 0:
        raise ValueError("Task40 V10 raw artifact projection cannot be negative")
    current = _raw_artifact_bytes(runtime.directory)
    usage = shutil.disk_usage(runtime.directory)
    projected = current + additional
    free_after = int(usage.free) - additional
    facts = {
        "label": str(label),
        "current_raw_artifact_bytes": current,
        "projected_additional_bytes": additional,
        "projected_cumulative_raw_artifact_bytes": projected,
        "raw_artifact_limit_bytes": 8 << 30,
        "filesystem_free_bytes": int(usage.free),
        "projected_free_bytes": free_after,
        "free_space_floor_bytes": 2 << 30,
    }
    if projected > (8 << 30) or free_after < (2 << 30):
        from .physical_p4_schur_v14 import V14ResourceStop

        raise V14ResourceStop(f"Task40 V10 raw-disk admission failed: {facts}")
    runtime.marker("v10_raw_disk_admission", facts)
    return facts


def _save_packet(runtime: Any, name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    from .physical_p4_schur_v14 import _save_packet as save

    packet_target = runtime.directory / name
    packet_paths = (
        Path(f"{packet_target}.npz"),
        Path(f"{packet_target}.json"),
    )
    collisions = [
        path.name for path in packet_paths if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise FileExistsError(
            f"Task40 witness packet {name!r} already exists ({', '.join(collisions)}); refusing overwrite"
        )

    # np.savez is uncompressed.  Reserve every array byte plus a conservative
    # per-member/header margin, then reconcile the actual files immediately.
    projected = int(_packet_array_bytes(payload) * 1.05) + (2 << 20)
    _disk_admit(runtime, additional_bytes=projected, label=f"packet:{name}")
    packet_target.parent.mkdir(parents=True, exist_ok=True)
    packet = save(runtime.directory, name, payload, runtime=runtime)
    _disk_admit(runtime, additional_bytes=0, label=f"packet_written:{name}")
    return packet


def _assign_vector_storage(vector: Any, values: Any, *, rows: Any | None = None) -> None:
    """Write through PETSc's explicit writable array API, never ``array_r``."""
    writable = vector.getArray(readonly=False)
    try:
        payload = np.asarray(values, dtype=np.complex128)
        if rows is None:
            if payload.shape != writable.shape:
                raise ValueError("PETSc vector assignment has the wrong storage shape")
            writable[...] = payload
        else:
            selected = np.asarray(rows, dtype=np.int64)
            if payload.shape != selected.shape or (
                selected.size and writable.size <= int(selected.max())
            ):
                raise ValueError("PETSc vector indexed assignment has the wrong layout")
            writable[selected] = payload
    finally:
        # petsc4py 3.25 releases the public getArray view when its ndarray
        # reference is dropped; Vec.restoreArray is not exposed in this ABI.
        del writable


def _apply_full_action_array(action: Any, values: Any, petsc: Any) -> np.ndarray:
    source = petsc.Vec().createSeq(len(values), comm=petsc.COMM_SELF)
    target = source.duplicate()
    try:
        _assign_vector_storage(source, values)
        action.apply(source, target)
        return np.asarray(target.array_r, dtype=np.complex128).copy()
    finally:
        target.destroy()
        source.destroy()


def _independent_storage_vector(template: Any, independent: np.ndarray, values: Any):
    vector = template.duplicate()
    try:
        vector.set(0.0)
        array = np.asarray(values, dtype=np.complex128)
        if array.shape != independent.shape:
            raise ValueError("independent-to-storage p6 vector layout mismatch")
        _assign_vector_storage(vector, array, rows=independent)
        return vector
    except BaseException:
        vector.destroy()
        raise


def _mapping_identity(reference: Mapping[str, Any]) -> dict[str, Any]:
    """Check native entity primal/dual work and the two-cell fold/lift duality."""

    layout = reference["full_layout"]
    profile = reference["profile"]
    entities = layout.entities
    n = int(layout.independent_rows)
    rng = np.random.default_rng(40102026)
    primal = (
        rng.standard_normal(n) + 1j * rng.standard_normal(n)
    ).astype(np.complex128)
    dual = (
        rng.standard_normal(n) + 1j * rng.standard_normal(n)
    ).astype(np.complex128)
    canonical_primal = entities.transform(
        primal, direction="primal_to_canonical"
    )
    canonical_dual = entities.transform(dual, direction="dual_to_canonical")
    primal_recovered = entities.transform(
        canonical_primal, direction="primal_from_canonical"
    )
    primal_roundtrip = float(
        np.linalg.norm(primal_recovered - primal)
        / max(float(np.linalg.norm(primal)), np.finfo(float).tiny)
    )
    work_scale = max(
        float(np.linalg.norm(primal) * np.linalg.norm(dual)),
        np.finfo(float).tiny,
    )
    work_identity = float(
        abs(np.vdot(dual, primal) - np.vdot(canonical_dual, canonical_primal))
        / work_scale
    )
    if max(primal_roundtrip, work_identity) > _MAPPING_IDENTITY_LIMIT:
        raise ValueError(
            "native p6 entity primal/dual identity failed: "
            f"roundtrip={primal_roundtrip}, work={work_identity}"
        )

    transport_rows = []
    for twist, sector in enumerate(reference["sectors"]):
        transport = sector["transport"]
        local_n = len(transport.local.independent)
        local_primal = (
            rng.standard_normal(local_n) + 1j * rng.standard_normal(local_n)
        ).astype(np.complex128)
        full_dual = (
            rng.standard_normal(n) + 1j * rng.standard_normal(n)
        ).astype(np.complex128)
        folded_dual = transport.fold_dual(full_dual)
        lifted_primal = transport.lift_primal(local_primal)
        scale = max(
            float(np.linalg.norm(full_dual) * np.linalg.norm(lifted_primal)),
            np.finfo(float).tiny,
        )
        relative = float(
            abs(np.vdot(full_dual, lifted_primal) - np.vdot(folded_dual, local_primal))
            / scale
        )
        if not np.isfinite(relative) or relative > _MAPPING_IDENTITY_LIMIT:
            raise ValueError(
                f"two-cell twist {twist} primal/dual transport identity failed: {relative}"
            )
        transport_rows.append(
            {
                "twist_index": twist,
                "global_q_indices": list(transport.audit["global_q_branches"]),
                "work_identity_relative": relative,
                "limit": _MAPPING_IDENTITY_LIMIT,
                "all_internal_channels_retained": True,
            }
        )
    dft_defect = float(
        np.linalg.norm(
            layout.cell_dft.conj().T @ layout.cell_dft
            - np.eye(profile.q_count)
        )
    )
    if not np.isfinite(dft_defect) or dft_defect > _MAPPING_IDENTITY_LIMIT:
        raise ValueError(f"cell DFT unitarity identity failed: {dft_defect}")
    return {
        "schema": "task40extra.review_v10_p6_mapping_identity.v1",
        "entity_primal_roundtrip_relative": primal_roundtrip,
        "entity_primal_dual_work_relative": work_identity,
        "two_cell_transport": transport_rows,
        "cell_dft_unitarity_frobenius_defect": dft_defect,
        "maximum_identity_relative": max(
            [primal_roundtrip, work_identity, dft_defect]
            + [row["work_identity_relative"] for row in transport_rows]
        ),
        "limit": _MAPPING_IDENTITY_LIMIT,
        "native_map_covers_all_independent_rows": True,
    }


def _hash_arrays(arrays: Mapping[str, Any]) -> str:
    digest = hashlib.sha256()
    for name, value in arrays.items():
        contiguous = np.ascontiguousarray(value)
        digest.update(str(name).encode("utf-8"))
        digest.update(contiguous.dtype.str.encode("ascii"))
        digest.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
        digest.update(memoryview(contiguous).cast("B"))
    return digest.hexdigest()


def _file_manifest(directory: Path) -> list[dict[str, Any]]:
    result = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        result.append({
            "path": str(path.resolve()),
            "relative_path": str(path.relative_to(directory)),
            "size_bytes": int(path.stat().st_size),
            "sha256": digest.hexdigest(),
        })
    return result


def _mpc_payload_identity(floquet: Any) -> dict[str, Any]:
    mpc = floquet.mpc
    coefficients, offsets = mpc.coefficients()
    masters = getattr(mpc.masters, "array", mpc.masters)
    arrays = {
        "slaves": np.asarray(mpc.slaves),
        "masters": np.asarray(masters),
        "coefficients": np.asarray(coefficients),
        "offsets": np.asarray(offsets),
    }
    return {
        "sha256": _hash_arrays(arrays),
        "slave_count": int(arrays["slaves"].size),
        "master_link_count": int(arrays["masters"].size),
        "coefficient_count": int(arrays["coefficients"].size),
        "offset_count": int(arrays["offsets"].size),
    }


def _carrier_payload_identity(carrier: Any) -> str:
    digest = hashlib.sha256()
    for entry in carrier.entries:
        digest.update(
            json.dumps(entry.mode_key, separators=(",", ":"), ensure_ascii=True).encode()
        )
        digest.update(np.asarray([entry.normalization_h], dtype=np.float64).tobytes())
        for name in (
            "coupling_rows",
            "coupling_values",
            "projection_rows",
            "projection_values",
        ):
            array = np.ascontiguousarray(getattr(entry, name))
            digest.update(name.encode("ascii"))
            digest.update(array.dtype.str.encode("ascii"))
            digest.update(np.asarray(array.shape, dtype=np.int64).tobytes())
            digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def _validate_reference_physical_identity(
    target_bundle: Mapping[str, Any],
    target_levels: Mapping[str, Any],
    reference_bundle: Mapping[str, Any],
    reference_levels: Mapping[str, Any],
) -> dict[str, Any]:
    target_carrier = target_bundle["dtn_action"].carrier
    reference_carrier = reference_bundle["dtn_action"].carrier
    target_modes = tuple(entry.mode_key for entry in target_carrier.entries)
    reference_modes = tuple(entry.mode_key for entry in reference_carrier.entries)
    target_physical = str(target_bundle["mode_sha256"])
    reference_physical = str(reference_bundle["mode_sha256"])
    target_carrier_physical = str(
        getattr(target_carrier, "physical_generator_manifest_sha256", "")
    )
    reference_carrier_physical = str(
        getattr(reference_carrier, "physical_generator_manifest_sha256", "")
    )
    target_mpc = _mpc_payload_identity(target_levels["floquets"][6])
    reference_mpc = _mpc_payload_identity(reference_levels["floquets"][6])
    target_carrier_payload = _carrier_payload_identity(target_carrier)
    reference_carrier_payload = _carrier_payload_identity(reference_carrier)
    checks = {
        "ordered_physical_mode_sha_equal": target_physical == reference_physical,
        "ordered_physical_mode_keys_equal": target_modes == reference_modes,
        "target_bundle_digest_binds_target_carrier_generator": (
            target_bundle.get("physical_generator_manifest_sha256") == target_physical
            and target_carrier_physical == target_physical
        ),
        "reference_bundle_digest_binds_reference_carrier_generator": (
            reference_bundle.get("physical_generator_manifest_sha256") == reference_physical
            and reference_carrier_physical == reference_physical
        ),
        "actual_finalized_mpc_payload_equal": target_mpc["sha256"] == reference_mpc["sha256"],
        "actual_carrier_rows_and_values_equal": target_carrier_payload == reference_carrier_payload,
    }
    if not all(checks.values()):
        raise ValueError(f"Task40 V10 target/reference physical identity failed: {checks}")
    return {
        "schema": "task40extra.review_v10_physical_mode_and_carrier_identity.v1",
        "checks": checks,
        "physical_mode_sha256": target_physical,
        "ordered_physical_mode_count": len(target_modes),
        "target_carrier_assembly_manifest_sha256": str(target_carrier.mode_manifest_sha256),
        "reference_carrier_assembly_manifest_sha256": str(reference_carrier.mode_manifest_sha256),
        "carrier_assembly_digest_schema": "boundary-plane assembly identity with context and phase fields",
        "target_carrier_payload_sha256": target_carrier_payload,
        "reference_carrier_payload_sha256": reference_carrier_payload,
        "target_mpc": target_mpc,
        "reference_mpc": reference_mpc,
        "whole_carrier_assembly_manifest_digests_are_compared_as_physical_mode_digests": False,
    }


def _runtime_interior_rows(reference: Mapping[str, Any]) -> np.ndarray:
    entities = reference["full_layout"].entities
    rows = [
        np.asarray(indices, dtype=np.int64)
        for (_orbit, base), (indices, _matrix) in entities.records.items()
        if int(base[0]) == 3
    ]
    interior = np.unique(np.concatenate(rows)) if rows else np.empty(0, dtype=np.int64)
    expected = int(reference["full_layout"].audit["dimension_counts"][3])
    profile_expected = int(reference["profile"].global_interior_rows)
    if interior.size != expected or expected != profile_expected:
        raise ValueError(
            "full p6 cell-interior RHS rows do not match the selected case profile: "
            f"{interior.size} != {expected} != {profile_expected}"
        )
    return interior


def _validate_target_p6_inventory(condensed: Any, profile: Any) -> dict[str, int]:
    """Check the target's full/trace/interior/port axes against its case profile."""

    actual = {
        "full_rows": int(condensed.full_rows),
        "trace_rows": int(condensed.active_rows),
        "interior_rows": int(condensed.active_interior_rows),
        "port_rows": int(condensed.appended_rows),
    }
    expected = {
        "full_rows": int(profile.global_storage_rows),
        "trace_rows": int(profile.global_trace_rows),
        "interior_rows": int(profile.global_interior_rows),
        "port_rows": int(profile.mode_count),
    }
    if actual != expected:
        raise ValueError(
            "actual target p6 trace+port retained inventory differs from selected profile: "
            f"{actual} != {expected}"
        )
    return actual


def _sector_native_forward_action(
    reference: Mapping[str, Any],
    full_solution_independent: Any,
    petsc: Any,
    *,
    allocation_gate: Any,
) -> tuple[np.ndarray, dict[int, dict[str, np.ndarray]], dict[str, Any]]:
    """Synthesize the two local native actions into the global dual space."""

    layout = reference["full_layout"]
    profile = reference["profile"]
    solution = np.asarray(full_solution_independent, dtype=np.complex128)
    if solution.shape != (layout.independent_rows,) or not np.isfinite(solution).all():
        raise ValueError("regular action witness needs the complete finite saved p6 solution")
    sectors = tuple(reference["sectors"])
    expected_twist_count = len(profile.sector_port_counts)
    twist_indices = [int(row["context"].twist_index) for row in sectors]
    if len(sectors) != expected_twist_count or twist_indices != list(
        range(expected_twist_count)
    ):
        raise ValueError("regular action witness requires every ordered two-cell twist")
    max_local_rows = max(int(row["entities"].full_rows) for row in sectors)
    max_local_independent = max(len(row["entities"].independent) for row in sectors)
    allocation_gate(
        "task40_v10_regular_sector_forward_action",
        {
            "additional_payload_bytes": 16
            * (
                2 * layout.independent_rows
                + sum(
                    2 * int(row["entities"].full_rows)
                    + len(row["entities"].independent)
                    for row in sectors
                )
            ),
            "workspace_bytes": 16
            * (layout.independent_rows + 2 * max_local_rows),
            "twist_count": expected_twist_count,
            "global_factor_count": 0,
            "global_matrix_count": 0,
        },
    )
    synthesized = np.zeros(layout.independent_rows, dtype=np.complex128)
    mode_ids: list[np.ndarray] = []
    local_action_vectors: dict[int, dict[str, np.ndarray]] = {}
    sector_facts = []
    for sector in sectors:
        twist = int(sector["context"].twist_index)
        transport = sector["transport"]
        entities = sector["entities"]
        local_values = np.asarray(transport.extract_primal(solution), dtype=np.complex128)
        if local_values.shape != (len(entities.independent),):
            raise ValueError("two-cell primal extraction returned the wrong local p6 layout")
        local_storage = np.zeros(int(entities.full_rows), dtype=np.complex128)
        local_storage[np.asarray(entities.independent, dtype=np.int64)] = local_values
        local_action_storage = _apply_full_action_array(
            sector["bundle"]["physical_action"], local_storage, petsc
        )
        local_action = np.asarray(
            local_action_storage[np.asarray(entities.independent, dtype=np.int64)],
            dtype=np.complex128,
        ).copy()
        lifted_dual = np.asarray(transport.lift_dual(local_action), dtype=np.complex128)
        if lifted_dual.shape != synthesized.shape or not np.isfinite(lifted_dual).all():
            raise ValueError("two-cell dual lift returned an invalid global p6 action")
        synthesized += lifted_dual
        local_action_vectors[twist] = {
            "independent": local_action,
            "full_storage": np.asarray(local_action_storage, dtype=np.complex128).copy(),
        }
        mode_ids.append(np.asarray(sector["context"].original_mode_indices, dtype=np.int64))
        sector_facts.append(
            {
                "twist_index": twist,
                "local_full_rows": int(entities.full_rows),
                "local_independent_rows": int(len(entities.independent)),
                "mode_count": int(len(sector["context"].original_mode_indices)),
                "local_action_norm": float(np.linalg.norm(local_action)),
                "lifted_dual_norm": float(np.linalg.norm(lifted_dual)),
            }
        )
    ordered_modes = np.sort(np.concatenate(mode_ids))
    if not np.array_equal(ordered_modes, np.arange(profile.mode_count, dtype=np.int64)):
        raise ValueError(
            "regular local forward actions do not cover all "
            f"{profile.mode_count} port modes exactly once"
        )
    return synthesized, local_action_vectors, {
        "twist_count": len(sector_facts),
        "expected_mode_count": profile.mode_count,
        "all_modes_covered_once": True,
        "sectors": sector_facts,
        "local_to_global_dual_map": "TwoCellNativeTransport.lift_dual",
    }


def _v15_native_budget_allocation_facts(
    *,
    full_rows: int,
    independent_rows: int,
    mode_count: int,
    max_local_rows: int,
    max_local_independent: int,
    retained_candidate_state_count: int,
    retain_lifted_errors: bool = False,
) -> dict[str, int | bool]:
    """Separate resident prior candidates from genuinely new budget storage."""

    n_full = int(full_rows)
    n_independent = int(independent_rows)
    n_modes = int(mode_count)
    local_full = int(max_local_rows)
    local_independent = int(max_local_independent)
    retained = max(0, int(retained_candidate_state_count))
    additional_array_copy_bytes = 16 * (3 * n_independent + 2 * n_modes)
    additional_compressed_temporary_bytes = 16 * (
        2 * local_full + 4 * local_independent
    )
    additional_other_budget_bytes = 16 * (
        3 * n_full
        + 13 * n_independent
        + 6 * n_modes
        + 4 * local_full
    )
    retained_residual_evidence_bytes = (
        16 * (6 * n_independent + 2 * local_independent)
        if retain_lifted_errors
        else 0
    )
    workspace_bytes = 16 * (2 * n_full + 2 * local_full)
    return {
        "additional_payload_bytes": (
            additional_array_copy_bytes
            + additional_compressed_temporary_bytes
            + additional_other_budget_bytes
            + retained_residual_evidence_bytes
        ),
        "additional_array_copy_bytes": additional_array_copy_bytes,
        "additional_compressed_temporary_bytes": additional_compressed_temporary_bytes,
        "additional_other_native_budget_array_bytes": additional_other_budget_bytes,
        "additional_retained_residual_evidence_bytes": retained_residual_evidence_bytes,
        "workspace_bytes": workspace_bytes,
        "additional_simultaneous_workspace_bytes": workspace_bytes,
        "retained_candidate_state_count": retained,
        "resident_candidate_state_bytes": retained * 16 * (
            8 * n_independent + 3 * n_modes
        ),
        "resident_candidate_state_is_already_in_current_rss": True,
        "resident_candidate_state_not_added_to_projected_allocation": True,
    }


def _v15_native_budget_facts(
    reference: Mapping[str, Any],
    template: Any,
    fe_rhs: Any,
    port_rhs: Any,
    alpha: Any,
    solution_values: Any,
    global_native_action_storage: Any,
    complete_augmented_fe_residual: Any,
    petsc: Any,
    *,
    allocation_gate: Any,
    full_solution_vector: Any | None = None,
    sector_action_data: tuple[Any, Any, Any] | None = None,
    retain_lifted_errors: bool = False,
    retained_candidate_state_count: int = 0,
) -> dict[str, Any]:
    """Compute V15 native elimination and non-cancelling residual facts."""

    from src.solvers.augmented_reference_correction import (
        evaluate_v15_non_cancelling_budget,
    )

    layout = reference["full_layout"]
    profile = reference["profile"]
    bundle = reference["global_bundle"]
    independent = np.asarray(layout.independent, dtype=np.int64)
    finite_rhs = np.asarray(fe_rhs, dtype=np.complex128)
    port_load_values = np.asarray(port_rhs, dtype=np.complex128)
    alpha_values = np.asarray(alpha, dtype=np.complex128)
    native_storage = np.asarray(global_native_action_storage, dtype=np.complex128)
    complete_fe = np.asarray(complete_augmented_fe_residual, dtype=np.complex128)
    if (
        finite_rhs.shape != (len(independent),)
        or port_load_values.shape != (profile.mode_count,)
        or alpha_values.shape != (profile.mode_count,)
        or native_storage.shape != (layout.full_rows,)
        or complete_fe.shape != (len(independent),)
    ):
        raise ValueError("V15 native residual inputs do not match the frozen p6 layout")
    h = np.asarray(
        [entry.normalization_h for entry in bundle["dtn_action"].carrier.entries],
        dtype=np.float64,
    )
    if h.shape != (profile.mode_count,) or not np.isfinite(h).all() or np.any(h <= 0.0):
        raise ValueError("V15 global original-H vector is incomplete or invalid")
    if sector_action_data is None:
        sector_action_data = _sector_native_forward_action(
            reference,
            solution_values,
            petsc,
            allocation_gate=allocation_gate,
        )
    _sector_action, local_action_vectors, sector_action_facts = sector_action_data
    if sector_action_facts.get("all_modes_covered_once") is not True:
        raise ValueError("V15 local action mapping does not cover every retained mode")
    replication_count = _task40_reference_replication_count(reference)

    max_local_rows = max(int(row["entities"].full_rows) for row in reference["sectors"])
    max_local_independent = max(
        len(row["entities"].independent) for row in reference["sectors"]
    )
    n_independent = int(len(independent))
    n_modes = int(profile.mode_count)
    allocation_facts = _v15_native_budget_allocation_facts(
        full_rows=int(layout.full_rows),
        independent_rows=n_independent,
        mode_count=n_modes,
        max_local_rows=max_local_rows,
        max_local_independent=max_local_independent,
        retained_candidate_state_count=retained_candidate_state_count,
        retain_lifted_errors=retain_lifted_errors,
    )
    allocation_gate(
        "task40_v15_native_augmented_residual_budget",
        {
            **allocation_facts,
            "budget_independent_vector_equivalents": 16,
            "local_action_vector_equivalents": 6,
            "per_sector_folded_rhs_and_action_vector_equivalents": 4,
            "uses_original_global_H": True,
            "replication_count_K": replication_count,
            "uses_sector_H_equal_global_H_over_K": True,
            "uses_sector_H_equal_global_H_over_two": replication_count == 2,
            "sector_port_normalization": (
                "g_s=g/sqrt(K); H_s=H/K; alpha_s=sqrt(K)*alpha"
            ),
            "uses_actual_primal_extract_and_dual_lift": True,
            "sector_action_source": "_sector_native_forward_action_on_E_s_u",
            "no_q_csr_action_used": True,
            "bounded_sector_lift_accumulation": True,
            "retain_startup_sector_lifted_errors": bool(retain_lifted_errors),
        },
    )

    owns_solution = full_solution_vector is None
    full_solution = (
        _independent_storage_vector(template, independent, solution_values)
        if owns_solution
        else full_solution_vector
    )
    global_port_load = template.duplicate()
    global_delta_load = template.duplicate()
    local_port_loads = []
    try:
        recovered_global = np.asarray(
            bundle["dtn_action"].recover_auxiliary(full_solution),
            dtype=np.complex128,
        )
        global_port_load.set(0.0)
        bundle["dtn_action"].apply_modal_rhs(port_load_values / h, global_port_load)
        port_elimination_action = np.asarray(
            global_port_load.array_r, dtype=np.complex128
        ).copy()[independent]
        effective_rhs = finite_rhs - port_elimination_action

        delta_alpha = alpha_values - recovered_global - port_load_values / h
        global_delta_load.set(0.0)
        bundle["dtn_action"].apply_modal_rhs(delta_alpha, global_delta_load)
        modal_alpha_defect_action = np.asarray(
            global_delta_load.array_r, dtype=np.complex128
        ).copy()[independent]

        sector_terms = []
        per_sector = []
        for sector in reference["sectors"]:
            twist = int(sector["context"].twist_index)
            transport = sector["transport"]
            entities = sector["entities"]
            mode_ids = np.asarray(
                sector["context"].original_mode_indices, dtype=np.int64
            )
            local_independent = np.asarray(transport.local.independent, dtype=np.int64)
            folded_rhs = np.asarray(transport.fold_dual(finite_rhs), dtype=np.complex128)
            if folded_rhs.shape != (len(local_independent),):
                raise ValueError(f"V15 twist {twist} folded RHS has the wrong layout")
            local_port_vectors = _task40_sector_port_vectors(
                mode_ids,
                replication_count=replication_count,
                global_h=h,
                global_port_rhs=port_load_values,
            )
            h_s = local_port_vectors["local_h"]
            g_s = local_port_vectors["local_port_rhs"]
            if not np.isfinite(h_s).all() or np.any(h_s <= 0.0):
                raise ValueError(f"V15 twist {twist} original-H block is invalid")
            local_port_load = petsc.Vec().createSeq(
                int(entities.full_rows), comm=petsc.COMM_SELF
            )
            local_port_loads.append(local_port_load)
            sector["bundle"]["dtn_action"].apply_modal_rhs(
                g_s / h_s, local_port_load
            )
            local_effective_rhs = folded_rhs - np.asarray(
                local_port_load.array_r, dtype=np.complex128
            )[local_independent]
            local_action = np.asarray(
                local_action_vectors[twist]["independent"], dtype=np.complex128
            )
            sector_terms.append({
                "rhs": local_effective_rhs,
                "action": local_action,
                "lift_dual": transport.lift_dual,
            })
            per_sector.append({
                "twist_index": twist,
                "mode_indices": mode_ids.tolist(),
                "replication_count_K": replication_count,
                "H_s_is_global_H_over_K": True,
                "g_s_is_global_g_over_sqrt_K": True,
                "alpha_scaling": "sqrt(K)*global_alpha[mode_ids]",
                "effective_rhs_norm": float(np.linalg.norm(local_effective_rhs)),
                "native_action_norm": float(np.linalg.norm(local_action)),
            })

        budget = evaluate_v15_non_cancelling_budget(
            effective_rhs=np.asarray(effective_rhs, dtype=np.complex128),
            global_eliminated_action=np.asarray(native_storage[independent], dtype=np.complex128),
            original_fe_rhs=finite_rhs,
            port_elimination_action=port_elimination_action,
            complete_augmented_fe_residual=complete_fe,
            modal_alpha_defect_action=modal_alpha_defect_action,
            sectors=sector_terms,
            retain_lifted_errors=retain_lifted_errors,
        )
        budget["sector_facts"] = per_sector
        budget["effective_rhs"] = effective_rhs.copy()
        budget["port_elimination_action"] = port_elimination_action.copy()
        budget["global_native_action_independent"] = native_storage[independent].copy()
        budget["all_modes_covered_once"] = True
        budget["effective_rhs_definition"] = "f - B H_p^-1 g"
        budget["eliminated_action_definition"] = "V_r u + B H_p^-1 D u"
        budget["alpha_defect_definition"] = "alpha - recover_auxiliary(u) - g/H_p"
        return budget
    finally:
        for vector in local_port_loads:
            vector.destroy()
        global_delta_load.destroy()
        global_port_load.destroy()
        if owns_solution:
            full_solution.destroy()


def _regular_local_recovery_facts(
    reference: Mapping[str, Any],
    solution_independent: Any,
    alpha_global: Any,
    fe_rhs_global: Any,
    port_rhs_global: Any,
    local_action_vectors: Mapping[int, Mapping[str, np.ndarray]],
    petsc: Any,
    *,
    allocation_gate: Any,
    operation_relative: Any,
) -> dict[str, Any]:
    """Check every local internal row and port identity with existing formulas."""

    solution = np.asarray(solution_independent, dtype=np.complex128)
    alpha = np.asarray(alpha_global, dtype=np.complex128)
    fe_rhs = np.asarray(fe_rhs_global, dtype=np.complex128)
    ports = np.asarray(port_rhs_global, dtype=np.complex128)
    sectors = tuple(reference["sectors"])
    profile = reference["profile"]
    replication_count = _task40_reference_replication_count(reference)
    internal_residuals = []
    internal_scales = []
    internal_effective_rhs = []
    internal_action_outputs = []
    internal_original_rows = []
    internal_twist_indices = []
    native_residuals = []
    native_scales = []
    port_residuals = []
    port_scales = []
    native_identity_differences = []
    native_identity_scales = []
    schur_port_differences = []
    schur_port_scales = []
    field_differences = []
    field_scales = []
    sector_facts = []
    covered_modes: list[np.ndarray] = []
    covered_internal_rows = 0
    for sector in sectors:
        twist = int(sector["context"].twist_index)
        action = sector["action"]
        condensed = action.condensed
        transport = sector["transport"]
        mode_ids = np.asarray(sector["context"].original_mode_indices, dtype=np.int64)
        local_independent = np.asarray(transport.local.independent, dtype=np.int64)
        local_full_rows = int(condensed.full_rows)
        allocation_gate(
            "task40_v10_regular_sector_internal_port_recovery",
            {
                "additional_payload_bytes": 16
                * (10 * local_full_rows + 5 * int(action.reduced_size) + 8 * len(mode_ids)),
                "workspace_bytes": 32 * 2**20,
                "twist_index": twist,
                "internal_rows": int(condensed.active_interior_rows),
                "port_modes": int(len(mode_ids)),
                "global_factor_count": 0,
                "global_matrix_count": 0,
            },
        )
        local_values = np.asarray(transport.extract_primal(solution), dtype=np.complex128)
        local_storage = np.zeros(local_full_rows, dtype=np.complex128)
        local_storage[local_independent] = local_values
        local_rhs = np.zeros(local_full_rows, dtype=np.complex128)
        local_rhs[local_independent] = transport.fold_dual(fe_rhs)
        local_port_vectors = _task40_sector_port_vectors(
            mode_ids,
            replication_count=replication_count,
            global_port_rhs=ports,
            global_alpha=alpha,
        )
        local_ports = local_port_vectors["local_port_rhs"]
        local_alpha = local_port_vectors["local_alpha"]
        constraints = condensed.trace_constraints
        active_original = np.asarray(
            constraints.owned_active_original_dofs, dtype=np.int64
        )
        active_ids = np.asarray(
            [constraints.original_to_active[int(row)] for row in active_original],
            dtype=np.int64,
        )
        if (
            len(active_original) != int(condensed.active_rows)
            or not np.array_equal(np.sort(active_ids), np.arange(condensed.active_rows))
            or len(mode_ids) != int(condensed.appended_rows)
        ):
            raise ValueError("local recovery trace/port coordinates do not match the frozen p6 layout")
        reduced_solution = np.empty(int(action.reduced_size), dtype=np.complex128)
        reduced_solution[active_ids] = local_storage[active_original]
        reduced_solution[int(condensed.active_rows) :] = local_alpha

        saved_local_action = np.asarray(
            local_action_vectors[twist]["full_storage"], dtype=np.complex128
        )

        native_apply_calls = 0
        native_apply_seconds = 0.0

        def native_apply(local_field: Any) -> np.ndarray:
            nonlocal native_apply_calls, native_apply_seconds
            started = time.perf_counter()
            try:
                native_apply_calls += 1
                return _apply_full_action_array(
                    sector["bundle"]["physical_action"], local_field, petsc
                )
            finally:
                native_apply_seconds += time.perf_counter() - started

        evaluated = action.evaluate_native_residual(
            reduced_solution,
            local_rhs,
            native_apply,
            port_rhs=local_ports,
            rhs_is_mpc_dual=True,
        )
        if native_apply_calls != 1 or not np.isfinite(native_apply_seconds):
            raise ValueError(
                f"twist {twist} recovered-field witness must perform and time one real FFCx action"
            )
        recovered_storage = np.asarray(evaluated["storage_solution"], dtype=np.complex128)
        field_difference = recovered_storage - local_storage
        field_scale = float(np.linalg.norm(recovered_storage)) + float(
            np.linalg.norm(local_storage)
        )
        effective_rhs = np.asarray(evaluated["native_effective_rhs"], dtype=np.complex128)
        interior_rows = np.unique(
            np.concatenate(
                [
                    np.asarray(cell.interior_original_dofs, dtype=np.int64)
                    for cell in condensed.cell_recovery_maps
                ]
            )
        )
        internal = effective_rhs[interior_rows] - saved_local_action[interior_rows]
        lu_internal = np.asarray(evaluated["internal_residual"], dtype=np.complex128)
        native_residual = np.asarray(evaluated["native_residual"], dtype=np.complex128)
        port_residual = np.asarray(evaluated["augmented_port_residual"], dtype=np.complex128)
        native_identity = np.asarray(
            evaluated["native_identity_difference"], dtype=np.complex128
        )
        schur_port_identity = np.asarray(
            evaluated["schur_port_identity_difference"], dtype=np.complex128
        )
        expected_internal = int(condensed.active_interior_rows)
        if (
            internal.shape != (expected_internal,)
            or interior_rows.shape != (expected_internal,)
            or lu_internal.shape != (expected_internal,)
        ):
            raise ValueError(
                f"twist {twist} independent internal action did not cover every local row: "
                f"action={internal.shape}, rows={interior_rows.shape}, LU={lu_internal.shape}, "
                f"expected={(expected_internal,)}"
            )
        covered_internal_rows += int(internal.size)
        covered_modes.append(mode_ids)
        internal_residuals.append(internal.copy())
        internal_effective_rhs.append(effective_rhs[interior_rows].copy())
        internal_action_outputs.append(saved_local_action[interior_rows].copy())
        internal_original_rows.append(interior_rows.copy())
        internal_twist_indices.append(
            np.full(internal.size, twist, dtype=np.int8)
        )
        internal_scales.append(float(evaluated["internal_operation_scale"]))
        native_residuals.append(native_residual.copy())
        native_scales.append(float(evaluated["native_rhs_operation_scale"]))
        port_residuals.append(port_residual.copy())
        port_scales.append(float(evaluated["port_operation_scale"]))
        native_identity_differences.append(native_identity.copy())
        native_identity_scales.append(float(evaluated["native_identity_operation_scale"]))
        schur_port_differences.append(schur_port_identity.copy())
        schur_port_scales.append(float(evaluated["schur_port_identity_operation_scale"]))
        field_differences.append(field_difference.copy())
        field_scales.append(field_scale)
        sector_facts.append(
            {
                "twist_index": twist,
                "global_q_indices": list(sector["context"].global_q_indices),
                "replication_count_K": replication_count,
                "local_port_normalization": (
                    "g_s=g/sqrt(K); H_s=H/K; alpha_s=sqrt(K)*alpha"
                ),
                "internal_row_count": int(internal.size),
                "internal_operation_scale": float(evaluated["internal_operation_scale"]),
                "internal_residual_relative": float(
                    operation_relative(
                        np.linalg.norm(internal), evaluated["internal_operation_scale"]
                    )
                ),
                "internal_action_source": "saved_field_local_native_ffcx_forward",
                "internal_effective_rhs_source": "P6CellCondensedAction.native_effective_rhs",
                "lu_internal_residual_relative_auxiliary": float(
                    evaluated["internal_residual_relative"]
                ),
                "original_H_used_for_port_elimination": True,
                "native_residual_relative": float(evaluated["native_residual_relative"]),
                "native_rhs_operation_scale": float(evaluated["native_rhs_operation_scale"]),
                "port_mode_count": int(len(mode_ids)),
                "port_residual_relative": float(evaluated["port_residual_relative"]),
                "port_operation_scale": float(evaluated["port_operation_scale"]),
                "native_identity_relative": float(evaluated["native_identity_relative"]),
                "native_identity_operation_scale": float(
                    evaluated["native_identity_operation_scale"]
                ),
                "schur_port_identity_relative": float(
                    evaluated["schur_port_identity_relative"]
                ),
                "schur_port_identity_operation_scale": float(
                    evaluated["schur_port_identity_operation_scale"]
                ),
                "projected_saved_field_recovery_relative": float(
                    operation_relative(np.linalg.norm(field_difference), field_scale)
                ),
                "projected_saved_field_rows": int(local_full_rows),
                "recovered_field_ffcx_apply_count": native_apply_calls,
                "recovered_field_ffcx_apply_seconds": native_apply_seconds,
            }
        )
    ordered_modes = np.sort(np.concatenate(covered_modes))
    if not np.array_equal(ordered_modes, np.arange(profile.mode_count, dtype=np.int64)):
        raise ValueError(
            "local recovery checks do not cover all "
            f"{profile.mode_count} original-H port modes exactly once"
        )
    if covered_internal_rows != profile.global_interior_rows:
        raise ValueError(
            "local recovery checks cover "
            f"{covered_internal_rows} internal rows, expected {profile.global_interior_rows}"
        )

    def join(values: list[np.ndarray]) -> np.ndarray:
        return np.concatenate(values) if values else np.empty(0, dtype=np.complex128)

    def aggregate(values: list[np.ndarray], scales: list[float]) -> float:
        return float(operation_relative(np.linalg.norm(join(values)), sum(scales)))

    joined_internal_rows = (
        np.concatenate(internal_original_rows)
        if internal_original_rows
        else np.empty(0, dtype=np.int64)
    )
    joined_internal_twists = (
        np.concatenate(internal_twist_indices)
        if internal_twist_indices
        else np.empty(0, dtype=np.int8)
    )
    if (
        joined_internal_rows.shape != (profile.global_interior_rows,)
        or joined_internal_twists.shape != (profile.global_interior_rows,)
        or not np.array_equal(
            np.lexsort((joined_internal_rows, joined_internal_twists)),
            np.arange(profile.global_interior_rows, dtype=np.int64),
        )
    ):
        raise ValueError("internal witness arrays lost their twist/row ordering")

    return {
        "internal_row_count": covered_internal_rows,
        "internal_residual_relative": aggregate(internal_residuals, internal_scales),
        "internal_operation_scale": float(sum(internal_scales)),
        "internal_action_source": "saved_field_local_native_ffcx_forward",
        "internal_effective_rhs_source": "P6CellCondensedAction.native_effective_rhs",
        "recovered_field_ffcx_apply_count": sum(
            int(row["recovered_field_ffcx_apply_count"]) for row in sector_facts
        ),
        "recovered_field_ffcx_apply_seconds": sum(
            float(row["recovered_field_ffcx_apply_seconds"]) for row in sector_facts
        ),
        "lu_internal_residual_relative_auxiliary": max(
            (float(row["lu_internal_residual_relative_auxiliary"]) for row in sector_facts),
            default=float("inf"),
        ),
        "local_native_residual_relative": aggregate(native_residuals, native_scales),
        "local_native_rhs_operation_scale": float(sum(native_scales)),
        "port_mode_count": int(len(ordered_modes)),
        "port_residual_relative": aggregate(port_residuals, port_scales),
        "port_operation_scale": float(sum(port_scales)),
        "native_identity_relative": aggregate(
            native_identity_differences, native_identity_scales
        ),
        "native_identity_operation_scale": float(sum(native_identity_scales)),
        "schur_port_identity_relative": aggregate(
            schur_port_differences, schur_port_scales
        ),
        "schur_port_identity_operation_scale": float(sum(schur_port_scales)),
        "projected_saved_field_recovery_relative": aggregate(
            field_differences, field_scales
        ),
        "sector_facts": sector_facts,
        "arrays": {
            "internal_residuals": join(internal_residuals),
            "internal_effective_rhs": join(internal_effective_rhs),
            "internal_saved_field_action": join(internal_action_outputs),
            "internal_original_rows": joined_internal_rows,
            "internal_twist_indices": joined_internal_twists,
            "native_residuals": join(native_residuals),
            "port_residuals": join(port_residuals),
            "native_identity_differences": join(native_identity_differences),
            "schur_port_identity_differences": join(schur_port_differences),
            "projected_saved_field_differences": join(field_differences),
        },
    }


def _regular_inverse_gate_facts(
    *,
    equation_relative: float,
    action_relative: float,
    recovery: Mapping[str, Any],
    profile: Any,
    local_equation_relative: float,
    port_closure_relative: float,
    q_residual_relative: float,
    q_coverage_passed: bool,
) -> dict[str, Any]:
    gates = {
        "original_regular_equation": bool(
            np.isfinite(equation_relative)
            and equation_relative <= _REFERENCE_RESIDUAL_LIMIT
        ),
        "independent_sector_action_consistency": bool(
            np.isfinite(action_relative) and action_relative <= _REGULAR_ACTION_LIMIT
        ),
        "full_internal_recovery": bool(
            int(recovery["internal_row_count"]) == profile.global_interior_rows
            and np.isfinite(float(recovery["internal_residual_relative"]))
            and float(recovery["internal_residual_relative"]) <= _REGULAR_RECOVERY_LIMIT
        ),
        "two_local_original_equations": bool(
            np.isfinite(local_equation_relative)
            and local_equation_relative <= _REFERENCE_RESIDUAL_LIMIT
        ),
        "all_port_equations": bool(
            int(recovery["port_mode_count"]) == profile.mode_count
            and np.isfinite(float(recovery["port_residual_relative"]))
            and float(recovery["port_residual_relative"]) <= _PORT_CLOSURE_LIMIT
        ),
        "native_action_recovery_identity": bool(
            np.isfinite(float(recovery["native_identity_relative"]))
            and float(recovery["native_identity_relative"]) <= _IDENTITY_LIMIT
        ),
        "schur_port_recovery_identity": bool(
            np.isfinite(float(recovery["schur_port_identity_relative"]))
            and float(recovery["schur_port_identity_relative"]) <= _IDENTITY_LIMIT
        ),
        "saved_field_local_recovery_identity": bool(
            np.isfinite(float(recovery["projected_saved_field_recovery_relative"]))
            and float(recovery["projected_saved_field_recovery_relative"])
            <= _REGULAR_RECOVERY_LIMIT
        ),
        "global_alpha_port_closure": bool(
            np.isfinite(port_closure_relative)
            and port_closure_relative <= _REGULAR_RECOVERY_LIMIT
        ),
        "all_q_true_residuals": bool(
            q_coverage_passed
            and np.isfinite(q_residual_relative)
            and q_residual_relative <= _REFERENCE_RESIDUAL_LIMIT
        ),
    }
    return {
        "gates": gates,
        "passed": all(gates.values()),
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "limits": {
            "original_regular_equation": _REFERENCE_RESIDUAL_LIMIT,
            "independent_sector_action_consistency": _REGULAR_ACTION_LIMIT,
            "full_internal_recovery": _REGULAR_RECOVERY_LIMIT,
            "two_local_original_equations": _REFERENCE_RESIDUAL_LIMIT,
            "all_port_equations": _PORT_CLOSURE_LIMIT,
            "native_action_recovery_identity": _IDENTITY_LIMIT,
            "schur_port_recovery_identity": _IDENTITY_LIMIT,
            "saved_field_local_recovery_identity": _REGULAR_RECOVERY_LIMIT,
            "global_alpha_port_closure": _REGULAR_RECOVERY_LIMIT,
            "all_q_true_residuals": _REFERENCE_RESIDUAL_LIMIT,
        },
    }


def _task40_v30_mixed_reference_rhs_cases(
    *,
    independent_row_count: int,
    interior_rows: np.ndarray,
    original_h: np.ndarray,
) -> tuple[tuple[str, np.ndarray, np.ndarray], ...]:
    """Build two deterministic RHS pairs with FE and every port channel active."""
    count = int(independent_row_count)
    rows = np.asarray(interior_rows, dtype=np.int64)
    h = np.asarray(original_h, dtype=np.float64)
    if (
        count <= 0
        or rows.ndim != 1
        or len(rows) == 0
        or np.any(rows < 0)
        or np.any(rows >= count)
        or len(np.unique(rows)) != len(rows)
        or h.ndim != 1
        or len(h) == 0
        or not np.isfinite(h).all()
        or np.any(h <= 0.0)
    ):
        raise ValueError("V30 mixed FE/port RHS requires valid interior rows and original H")

    rng_full = np.random.default_rng(40103027)
    full_fe = (
        rng_full.standard_normal(count) + 1j * rng_full.standard_normal(count)
    ).astype(np.complex128)
    rng_interior = np.random.default_rng(40103028)
    interior_fe = np.zeros(count, dtype=np.complex128)
    interior_fe[rows] = (
        rng_interior.standard_normal(len(rows))
        + 1j * rng_interior.standard_normal(len(rows))
    )

    mode_index = np.arange(len(h), dtype=np.float64) + 1.0
    full_amplitudes = (
        1.0 + 0.2 * np.sin(0.17 * mode_index)
        + 1j * (0.8 + 0.15 * np.cos(0.11 * mode_index))
    )
    interior_amplitudes = (
        0.9 + 0.17 * np.cos(0.13 * mode_index)
        + 1j * (1.1 + 0.12 * np.sin(0.07 * mode_index))
    )
    full_ports = np.asarray(h * full_amplitudes, dtype=np.complex128)
    interior_ports = np.asarray(h * interior_amplitudes, dtype=np.complex128)
    cases = (
        ("mixed_generic_fe_and_all_mode_port_rhs", full_fe, full_ports),
        ("mixed_interior_fe_and_all_mode_port_rhs", interior_fe, interior_ports),
    )
    if any(
        not np.isfinite(fe).all()
        or not np.isfinite(ports).all()
        or not np.any(fe)
        or not np.all(ports != 0.0)
        for _, fe, ports in cases
    ):
        raise RuntimeError("V30 mixed FE/port RHS construction produced a zero or invalid input")
    if np.array_equal(full_fe, interior_fe) or np.array_equal(full_ports, interior_ports):
        raise RuntimeError("V30 mixed FE/port RHS pairs must be distinct")
    return cases


def _regular_inverse_checks_schema(
    profile: Any,
    reference_pc_strategy: str = "STRICT_ONLY",
    *,
    include_mixed_fe_port_cases: bool = False,
) -> str:
    """Select the established regular-inverse metadata schema by profile."""
    if include_mixed_fe_port_cases:
        return "task40extra.review_v30_reference_inverse_checks.v1"
    if reference_pc_strategy == "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15":
        return "task40extra.review_v15_p6_regular_inverse_checks.v1"
    if reference_pc_strategy == "STRICT_THEN_BOUNDED_INEXACT_V13":
        return "task40extra.review_v13_p6_regular_inverse_checks.v1"
    if profile.name == TASK40_V10_P6_PROFILE.name:
        return "task40extra.review_v10_p6_regular_inverse_checks.v1"
    return "task40extra.review_v11_p6_regular_inverse_checks.v1"


def _task40_v31_reference_tier_receipt(
    row: Mapping[str, Any], *, reference_pc_strategy: str
) -> dict[str, Any]:
    """Report strict and V15 admission independently for one selected FE/alpha state."""
    from src.solvers.augmented_reference_correction import (
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        V15_REFERENCE_PC_PASS,
        V15_REFERENCE_PC_REJECTED,
        select_reference_pc_candidate,
    )

    candidate = row.get("reference_pc_candidate")
    if not isinstance(candidate, Mapping):
        raise ValueError("V31 reference tier receipt requires the selected complete-state candidate")
    metrics = row.get("reference_pc_metrics")
    frozen = row.get("frozen_scale_metrics")
    structural = row.get("reference_pc_structural_gates")
    if not all(isinstance(value, Mapping) for value in (metrics, frozen, structural)):
        raise ValueError("V31 strict tier receipt lacks selected-state metrics or structural gates")
    selected_sha = row.get("selected_state_sha256", candidate.get("state_sha256"))
    candidate_sha = candidate.get("state_sha256")
    if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
        if (
            not isinstance(selected_sha, str)
            or len(selected_sha) != 64
            or selected_sha != candidate_sha
            or row.get("selected_v15_raw_facts", {}).get("state_sha256") != selected_sha
        ):
            raise ValueError("V31 strict and V15 tiers must identify the same selected FE/alpha state")
    strict_candidate = {
        "metrics": dict(metrics),
        "frozen_scale_metrics": dict(frozen),
        "structural_gates": dict(structural),
        "state_sha256": selected_sha,
        "state_label": row.get("reference_pc_candidate_label", candidate.get("state_label")),
    }
    strict = select_reference_pc_candidate([strict_candidate])
    if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
        v15_status = row.get("reference_pc_admission")
        if v15_status not in {V15_REFERENCE_PC_PASS, V15_REFERENCE_PC_REJECTED}:
            raise ValueError("V31 V15 tier receipt lacks an explicit V15 admission status")
        v15_passed: bool | None = v15_status == V15_REFERENCE_PC_PASS
    else:
        v15_status = "NOT_APPLICABLE"
        v15_passed = None
    return {
        "strict_reference_admission": strict["admission"],
        "strict_reference_passed": bool(strict["strict_passed"]),
        "strict_reference_selection": strict,
        "strict_reference_selected_state_sha256": selected_sha,
        "v15_reference_admission": v15_status,
        "v15_reference_passed": v15_passed,
        "v15_reference_selected_state_sha256": (
            selected_sha if v15_passed is not None else None
        ),
    }


def _verify_regular_inverse(
    runtime: Any,
    reference: dict[str, Any],
    physical_rhs: Any,
    physical_rhs_facts: Mapping[str, Any],
    *,
    allocation_gate: Any,
    reference_pc_strategy: str = "STRICT_ONLY",
    _case_filter: str | None = None,
    _candidate_state: tuple[np.ndarray, np.ndarray] | None = None,
    _frozen_scales: Mapping[str, Any] | None = None,
    _candidate_label: str = "initial",
    _allow_correction: bool = True,
    include_mixed_fe_port_cases: bool = False,
) -> dict[str, Any]:
    """Check complete regular FE/port recovery with the profile's live all-q factors."""

    from src.solvers.augmented_reference_correction import (
        BOUNDED_INEXACT_REFERENCE_PC,
        FACTOR_CALL_COUNTER_SOURCE,
        REFERENCE_PC_REJECTED,
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        STRICT_ONLY,
        STRICT_REFERENCE_PASS,
        STRICT_THEN_BOUNDED_INEXACT_V13,
        apply_one_augmented_residual_correction,
        augmented_port_state_offset,
        evaluate_complete_augmented_residual,
        select_reference_pc_candidate,
        select_v15_reference_pc_candidate,
    )
    from src.solvers.p6_cell_condensed_action import _operation_relative
    from petsc4py import PETSc

    if reference_pc_strategy not in {
        STRICT_ONLY,
        STRICT_THEN_BOUNDED_INEXACT_V13,
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
    }:
        raise ValueError(f"unknown Task40 reference-PC strategy: {reference_pc_strategy!r}")
    if _candidate_state is not None and _case_filter is None:
        raise ValueError("an overridden reference state requires one explicit witness case")

    inverse = reference["inverse"]
    layout = reference["full_layout"]
    profile = reference["profile"]
    bundle = reference["global_bundle"]
    template = physical_rhs
    independent = np.asarray(layout.independent, dtype=np.int64)
    n = len(independent)
    modes = tuple(bundle["modes"])
    if len(modes) != profile.mode_count:
        raise ValueError(
            f"regular reference must retain {profile.mode_count} modes, got {len(modes)}"
        )
    carrier = bundle["dtn_action"].carrier
    h = np.asarray([entry.normalization_h for entry in carrier.entries], dtype=np.float64)
    if h.shape != (profile.mode_count,) or not np.isfinite(h).all() or np.any(h <= 0.0):
        raise ValueError("regular reference original-H vector is incomplete or invalid")

    physical_storage = np.asarray(physical_rhs.array_r, dtype=np.complex128).copy()
    if physical_storage.shape != (layout.full_rows,):
        raise ValueError("regular physical RHS does not match the full p6 storage layout")
    base_case_names = (
        "generic_full_independent",
        f"interior_only_all_{profile.global_interior_rows}",
        "nonzero_all_mode_port_rhs",
        "physical_regular_incident_rhs",
    )
    mixed_cases: tuple[tuple[str, np.ndarray, np.ndarray], ...] = ()
    if include_mixed_fe_port_cases:
        allocation_gate(
            "task40_v30_mixed_reference_rhs_preflight",
            {
                "additional_payload_bytes": int(
                    16 * (2 * n + 2 * profile.mode_count)
                ),
                "workspace_bytes": int(64 * (n + profile.mode_count)),
                "mixed_case_count": 2,
                "both_fe_and_all_port_channels_nonzero": True,
                "all_q_profile_count": int(profile.q_count),
            },
        )
        mixed_cases = _task40_v30_mixed_reference_rhs_cases(
            independent_row_count=n,
            interior_rows=_runtime_interior_rows(reference),
            original_h=h,
        )
    case_names = base_case_names + tuple(name for name, _, _ in mixed_cases)
    mixed_cases_by_name = {name: (fe, ports) for name, fe, ports in mixed_cases}
    if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
        selected_names = case_names if _case_filter is None else (_case_filter,)
        if any(name not in case_names for name in selected_names):
            raise ValueError(f"regular inverse witness case not uniquely found: {_case_filter!r}")
        v15_indices = {name: index for index, name in enumerate(case_names)}
        cases_list = []
        for name in selected_names:
            case_index = v15_indices[name]
            zero_ports = np.zeros(profile.mode_count, dtype=np.complex128)
            zero_full = np.zeros(layout.full_rows, dtype=np.complex128)
            if case_index == 0:
                rng = np.random.default_rng(40102027 + case_index)
                fe_case = (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(
                    np.complex128
                )
                cases_list.append((name, fe_case, zero_ports, zero_full))
            elif case_index == 1:
                rng = np.random.default_rng(40102027 + case_index)
                interior_rows = _runtime_interior_rows(reference)
                fe_case = np.zeros(n, dtype=np.complex128)
                fe_case[interior_rows] = (
                    rng.standard_normal(len(interior_rows))
                    + 1j * rng.standard_normal(len(interior_rows))
                )
                cases_list.append((name, fe_case, zero_ports, zero_full))
            elif case_index == 2:
                amplitudes = (
                    np.sin(0.031 * (np.arange(profile.mode_count, dtype=np.float64) + 1.0))
                    + 1j * np.cos(0.047 * (np.arange(profile.mode_count, dtype=np.float64) + 1.0))
                ).astype(np.complex128)
                cases_list.append((name, np.zeros(n, dtype=np.complex128), (h * amplitudes).astype(np.complex128), zero_full))
            elif case_index == 3:
                cases_list.append((name, physical_storage[independent].copy(), zero_ports, physical_storage))
            else:
                fe_case, ports_case = mixed_cases_by_name[name]
                cases_list.append((name, fe_case, ports_case, zero_full))
        cases = tuple(cases_list)
    else:
        rng = np.random.default_rng(40102027)
        generic = (
            rng.standard_normal(n) + 1j * rng.standard_normal(n)
        ).astype(np.complex128)
        interior_rows = _runtime_interior_rows(reference)
        interior = np.zeros(n, dtype=np.complex128)
        interior[interior_rows] = (
            rng.standard_normal(len(interior_rows))
            + 1j * rng.standard_normal(len(interior_rows))
        )
        amplitudes = (
            np.sin(0.031 * (np.arange(profile.mode_count, dtype=np.float64) + 1.0))
            + 1j * np.cos(0.047 * (np.arange(profile.mode_count, dtype=np.float64) + 1.0))
        ).astype(np.complex128)
        port_rhs = (h * amplitudes).astype(np.complex128)
        cases = (
            ("generic_full_independent", generic, np.zeros(profile.mode_count, dtype=np.complex128), np.zeros(layout.full_rows, dtype=np.complex128)),
            (f"interior_only_all_{profile.global_interior_rows}", interior, np.zeros(profile.mode_count, dtype=np.complex128), np.zeros(layout.full_rows, dtype=np.complex128)),
            ("nonzero_all_mode_port_rhs", np.zeros(n, dtype=np.complex128), port_rhs, np.zeros(layout.full_rows, dtype=np.complex128)),
            ("physical_regular_incident_rhs", physical_storage[independent].copy(), np.zeros(profile.mode_count, dtype=np.complex128), physical_storage),
        )
        if mixed_cases:
            mixed_zero_full = np.zeros(layout.full_rows, dtype=np.complex128)
            cases += tuple(
                (name, fe_case, ports_case, mixed_zero_full)
                for name, fe_case, ports_case in mixed_cases
            )
        if _case_filter is not None:
            cases = tuple(row for row in cases if row[0] == _case_filter)
            if len(cases) != 1:
                raise ValueError(f"regular inverse witness case not uniquely found: {_case_filter!r}")
    v19_saved_v18_reference = None
    if (
        _candidate_state is None
        and getattr(inverse.factors, "factor_lifecycle_strategy", None)
        == "ONE_Q_REFACTOR_V19"
    ):
        v19_saved_v18_reference = _v19_prepare_saved_v18_startup_reference(
            reference, profile
        )
    records = []
    for name, fe_rhs, g_rhs, full_rhs_values in cases:
        sample_label = _regular_inverse_sample_label(name, _candidate_label)
        runtime.sample(f"{sample_label}_before")
        if _candidate_state is None:
            solution_values, alpha = inverse.apply_augmented(
                fe_rhs,
                port_rhs=g_rhs,
                rhs_category="startup_rhs_mat_solve_count",
            )
        else:
            solution_values = np.asarray(_candidate_state[0], dtype=np.complex128)
            alpha = np.asarray(_candidate_state[1], dtype=np.complex128)
            if solution_values.shape != (n,) or alpha.shape != (profile.mode_count,):
                raise ValueError("corrected complete augmented candidate has a mismatched layout")
        solution = _independent_storage_vector(template, independent, solution_values)
        applied = template.duplicate()
        port_load = template.duplicate()
        error = None
        try:
            bundle["physical_action"].apply(solution, applied)
            native_action_storage = np.asarray(applied.array_r, dtype=np.complex128).copy()
            port_load.set(0.0)
            if np.any(g_rhs):
                bundle["dtn_action"].apply_modal_rhs(g_rhs / h, port_load)
                applied.axpy(1.0, port_load)
            error = applied.copy()
            expected = _independent_storage_vector(
                template, independent, fe_rhs
            ) if name != "physical_regular_incident_rhs" else template.duplicate()
            try:
                if name == "physical_regular_incident_rhs":
                    _assign_vector_storage(expected, full_rhs_values)
                expected_storage = np.asarray(expected.array_r).copy()
                error.axpy(-1.0, expected)
                equation_scale = max(
                    float(expected.norm()) + float(port_load.norm()),
                    np.finfo(float).tiny,
                )
                equation_residual_norm = float(error.norm())
                equation_relative = equation_residual_norm / equation_scale
            finally:
                expected.destroy()

            sector_action, sector_action_vectors, sector_action_facts = (
                _sector_native_forward_action(
                    reference,
                    solution_values,
                    PETSc,
                    allocation_gate=allocation_gate,
                )
            )
            native_action_independent = native_action_storage[independent]
            action_difference = sector_action - native_action_independent
            action_operation_scale = float(np.linalg.norm(sector_action)) + float(
                np.linalg.norm(native_action_independent)
            )
            action_relative = float(
                _operation_relative(np.linalg.norm(action_difference), action_operation_scale)
            )

            recovered_alpha = bundle["dtn_action"].recover_auxiliary(solution)
            alpha_expected = recovered_alpha + g_rhs / h
            port_scale = max(
                float(np.linalg.norm(alpha))
                + float(np.linalg.norm(recovered_alpha))
                + float(np.linalg.norm(g_rhs / h)),
                np.finfo(float).tiny,
            )
            alpha_closure_residual_norm = float(np.linalg.norm(alpha - alpha_expected))
            port_relative = alpha_closure_residual_norm / port_scale
            v15_alpha_facts = None
            if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
                from src.solvers.augmented_reference_correction import stable_euclidean_norm

                alpha_defect = np.asarray(alpha - alpha_expected, dtype=np.complex128)
                alpha_norm_v15 = stable_euclidean_norm(alpha_defect)
                alpha_scale_v15 = float(
                    stable_euclidean_norm(np.asarray(alpha, dtype=np.complex128))
                    + stable_euclidean_norm(np.asarray(recovered_alpha, dtype=np.complex128))
                    + stable_euclidean_norm(np.asarray(g_rhs / h, dtype=np.complex128))
                )
                frozen_alpha_scale_v15 = float(
                    (_frozen_scales or {}).get(
                        "v15_alpha_closure_scale", alpha_scale_v15
                    )
                )

                def v15_alpha_relative(denominator: float) -> float:
                    if denominator == 0.0:
                        return 0.0 if alpha_norm_v15 == 0.0 else float("inf")
                    return alpha_norm_v15 / denominator

                v15_alpha_facts = {
                    "residual_norm": alpha_norm_v15,
                    "original_scale": alpha_scale_v15,
                    "original_relative": v15_alpha_relative(alpha_scale_v15),
                    "frozen_scale": frozen_alpha_scale_v15,
                    "frozen_relative": v15_alpha_relative(frozen_alpha_scale_v15),
                }
            augmented_fe_residual = None
            augmented_port_residual = None
            augmented_equation_residual_norm = None
            augmented_rhs_norm = None
            augmented_stacked_relative_diagnostic = None
            complete_augmented_fe_equation_relative = None
            if reference_pc_strategy in {
                STRICT_THEN_BOUNDED_INEXACT_V13,
                NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
            }:
                allocation_gate(
                    "task40_v15_complete_augmented_reference_equation_evaluation"
                    if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
                    else "task40_v13_complete_augmented_reference_equation_evaluation",
                    {
                        "additional_payload_bytes": 16 * (
                            int(layout.full_rows) + 4 * int(n)
                            + 7 * int(profile.mode_count)
                        ) + max(int(layout.full_rows), int(n), int(profile.mode_count)),
                        "workspace_bytes": 0,
                        "native_volume_action_is_independent": True,
                        "native_dual_coupling_uses_actual_returned_alpha": True,
                        "port_row_uses_original_h": True,
                        "shared_solver_residual_core": True,
                    },
                )
                augmented_port_coupling = template.duplicate()
                try:
                    alpha_minus_recovered = augmented_port_state_offset(
                        alpha, recovered_alpha
                    )
                    bundle["dtn_action"].apply_modal_rhs(
                        alpha_minus_recovered, augmented_port_coupling
                    )
                    complete_augmented = evaluate_complete_augmented_residual(
                        physical_action_storage=native_action_storage,
                        dual_coupling_storage=np.asarray(
                            augmented_port_coupling.array_r, dtype=np.complex128
                        ),
                        finite_element_rhs=expected_storage[independent],
                        port_amplitudes=alpha,
                        recovered_port_amplitudes=recovered_alpha,
                        port_state_offset=alpha_minus_recovered,
                        port_rhs=g_rhs,
                        h=h,
                        original_fe_equation_scale=equation_scale,
                        independent_rows=independent,
                    )
                finally:
                    augmented_port_coupling.destroy()
                augmented_fe_residual = complete_augmented["finite_element_residual"]
                augmented_port_residual = complete_augmented["port_residual"]
                augmented_equation_residual_norm = complete_augmented[
                    "augmented_residual_norm"
                ]
                augmented_rhs_norm = complete_augmented["augmented_rhs_norm"]
                augmented_stacked_relative_diagnostic = complete_augmented[
                    "complete_augmented_stacked_relative_diagnostic"
                ]
                complete_augmented_fe_equation_relative = complete_augmented[
                    "complete_augmented_fe_equation_relative"
                ]
            v15_budget = None
            if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
                v15_budget = _v15_native_budget_facts(
                    reference,
                    template,
                    fe_rhs,
                    g_rhs,
                    alpha,
                    solution_values,
                    native_action_storage,
                    augmented_fe_residual,
                    PETSc,
                    allocation_gate=allocation_gate,
                    full_solution_vector=solution,
                    sector_action_data=(
                        sector_action,
                        sector_action_vectors,
                        sector_action_facts,
                    ),
                    retain_lifted_errors=True,
                )
            recovery = _regular_local_recovery_facts(
                reference,
                solution_values,
                alpha,
                fe_rhs,
                g_rhs,
                sector_action_vectors,
                PETSc,
                allocation_gate=allocation_gate,
                operation_relative=_operation_relative,
            )
            solve_audit = inverse.last_solve_audit
            q_rows = [row for sector in solve_audit for row in sector["q_true_residuals"]]
            q_residual_max = max(
                (float(row["true_residual_relative"]) for row in q_rows),
                default=float("inf"),
            )
            expected_qs = set(range(profile.q_count))
            q_coverage_passed = (
                len(q_rows) == profile.q_count
                and {int(row["q"]) for row in q_rows} == expected_qs
            )
            gate_facts = _regular_inverse_gate_facts(
                equation_relative=equation_relative,
                action_relative=action_relative,
                recovery=recovery,
                profile=profile,
                local_equation_relative=float(recovery["local_native_residual_relative"]),
                port_closure_relative=port_relative,
                q_residual_relative=q_residual_max,
                q_coverage_passed=q_coverage_passed,
            )
            passed = bool(gate_facts["passed"])
            reference_pc_metrics = {
                "full_equation": equation_relative,
                "complete_augmented_fe_equation": complete_augmented_fe_equation_relative,
                "local_sector_0": float(recovery["sector_facts"][0]["native_residual_relative"]),
                "local_sector_1": float(recovery["sector_facts"][1]["native_residual_relative"]),
                "local_combined": float(recovery["local_native_residual_relative"]),
                "alpha_closure": port_relative,
                "q_solve": q_residual_max,
            }
            if v15_budget is not None:
                reference_pc_metrics.update({
                    "eliminated_fe": float(v15_budget["eliminated_fe_relative"]),
                    "complete_augmented_fe": float(v15_budget["complete_augmented_fe_relative"]),
                    "noncancelling_budget": float(v15_budget["noncancelling_budget_relative"]),
                    "alpha_closure": float(complete_augmented["alpha_closure_relative"]),
                })
            current_scales = {
                "full_equation": max(float(equation_scale), np.finfo(float).tiny),
                "complete_augmented_fe_equation": max(
                    float(equation_scale), np.finfo(float).tiny
                ),
                "local_sector_by_twist": {
                    int(sector["twist_index"]): max(
                        float(sector["native_rhs_operation_scale"]), np.finfo(float).tiny
                    )
                    for sector in recovery["sector_facts"]
                },
                "local_combined": max(
                    float(recovery["local_native_rhs_operation_scale"]),
                    np.finfo(float).tiny,
                ),
                "alpha_closure": max(float(port_scale), np.finfo(float).tiny),
                "q_rhs_by_phase": {
                    int(row["q"]): max(float(row["rhs_norm"]), np.finfo(float).tiny)
                    for row in q_rows
                },
            }
            if v15_alpha_facts is not None:
                current_scales["v15_alpha_closure_scale"] = float(
                    v15_alpha_facts["original_scale"]
                )
            frozen_scales = dict(_frozen_scales or current_scales)
            frozen_sector_scales = frozen_scales.get("local_sector_by_twist", {})
            frozen_q_scales = frozen_scales.get("q_rhs_by_phase", {})
            sector_by_twist = {
                int(sector["twist_index"]): sector for sector in recovery["sector_facts"]
            }

            def frozen_relative(numerator: float, denominator: Any) -> float:
                scale = float(denominator)
                value = float(numerator)
                if not np.isfinite(value) or not np.isfinite(scale) or scale <= 0.0:
                    return float("inf")
                return value / scale

            frozen_q_relative = []
            for q_row in q_rows:
                q = int(q_row["q"])
                q_denominator = frozen_q_scales.get(q)
                current_denominator = max(float(q_row["rhs_norm"]), np.finfo(float).tiny)
                q_residual_norm = float(q_row["true_residual_relative"]) * current_denominator
                frozen_q_relative.append(frozen_relative(q_residual_norm, q_denominator))
            frozen_scale_metrics = {
                "full_equation": frozen_relative(
                    equation_residual_norm, frozen_scales.get("full_equation")
                ),
                "complete_augmented_fe_equation": (
                    frozen_relative(
                        float(complete_augmented["finite_element_residual_norm"]),
                        frozen_scales.get("complete_augmented_fe_equation"),
                    )
                    if complete_augmented_fe_equation_relative is not None
                    else float("inf")
                ),
                "local_sector_0": frozen_relative(
                    float(sector_by_twist[0]["native_residual_relative"])
                    * float(sector_by_twist[0]["native_rhs_operation_scale"]),
                    frozen_sector_scales.get(0),
                ),
                "local_sector_1": frozen_relative(
                    float(sector_by_twist[1]["native_residual_relative"])
                    * float(sector_by_twist[1]["native_rhs_operation_scale"]),
                    frozen_sector_scales.get(1),
                ),
                "local_combined": frozen_relative(
                    float(np.linalg.norm(recovery["arrays"]["native_residuals"])),
                    frozen_scales.get("local_combined"),
                ),
                "alpha_closure": frozen_relative(
                    alpha_closure_residual_norm,
                    frozen_scales.get("alpha_closure"),
                ),
                "q_solve": max(frozen_q_relative, default=float("inf")),
            }
            if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
                if v15_budget is None:
                    raise RuntimeError("V15 native residual budget was not evaluated")
                replaced_numeric_gates = {
                    "original_regular_equation",
                    "independent_sector_action_consistency",
                    "two_local_original_equations",
                    "global_alpha_port_closure",
                    "all_q_true_residuals",
                    "complete_augmented_fe_equation",
                }
                candidate_structural_gates = {
                    name: value
                    for name, value in gate_facts["gates"].items()
                    if name not in replaced_numeric_gates
                }
                candidate_structural_gates.update({
                    "all_q_phases_covered": q_coverage_passed,
                    "all_retained_modes_mapped_once": bool(
                        sector_action_facts["all_modes_covered_once"]
                    ),
                    "native_decomposition_closure": bool(
                        np.isfinite(v15_budget["decomposition_closure_relative"])
                        and v15_budget["decomposition_closure_relative"]
                        <= 1.0e-10
                    ),
                    "native_augmented_actions_finite": bool(
                        np.isfinite(v15_budget["effective_rhs_scale"])
                        and np.isfinite(v15_budget["budget_numerator"])
                    ),
                })
                frozen_alpha_scale = float(
                    frozen_scales.get(
                        "v15_alpha_closure_scale",
                        v15_alpha_facts["original_scale"],
                    )
                )
                v15_metrics = {
                    "eliminated_fe": float(v15_budget["eliminated_fe_relative"]),
                    "complete_augmented_fe": float(
                        v15_budget["complete_augmented_fe_relative"]
                    ),
                    "noncancelling_budget": float(
                        v15_budget["noncancelling_budget_relative"]
                    ),
                    "alpha_closure": float(
                        v15_alpha_facts["original_relative"]
                    ),
                    "q_solve": q_residual_max,
                }
                v15_frozen_metrics = {
                    "eliminated_fe": v15_metrics["eliminated_fe"],
                    "complete_augmented_fe": v15_metrics["complete_augmented_fe"],
                    "noncancelling_budget": v15_metrics["noncancelling_budget"],
                    "alpha_closure": float(
                        v15_alpha_facts["frozen_relative"]
                    ),
                }
                from src.solvers.augmented_reference_correction import augmented_state_sha256

                v15_raw_facts = {
                    "profile_identity": profile.name,
                    "effective_rhs_scale": float(v15_budget["effective_rhs_scale"]),
                    "eliminated_fe_residual_norm": float(
                        v15_budget["eliminated_fe_residual_norm"]
                    ),
                    "complete_augmented_fe_residual_norm": float(
                        v15_budget["complete_augmented_fe_residual_norm"]
                    ),
                    "budget_term_norms": dict(v15_budget["budget_terms"]),
                    "alpha_closure_residual_norm": float(
                        v15_alpha_facts["residual_norm"]
                    ),
                    "alpha_closure_original_scale": float(
                        v15_alpha_facts["original_scale"]
                    ),
                    "alpha_closure_frozen_scale": frozen_alpha_scale,
                    "q_true_residuals": copy.deepcopy(q_rows),
                    "retained_mode_count": int(profile.mode_count),
                    "native_sector_facts": copy.deepcopy(
                        v15_budget["sector_facts"]
                    ),
                    "decomposition_closure_norm": float(
                        v15_budget["decomposition_closure_norm"]
                    ),
                    "decomposition_closure_scale": float(
                        v15_budget["decomposition_closure_scale"]
                    ),
                    "state_sha256": augmented_state_sha256(solution_values, alpha),
                }
                reference_pc_candidate = {
                    "metrics": v15_metrics,
                    "frozen_scale_metrics": v15_frozen_metrics,
                    "structural_gates": candidate_structural_gates,
                    "state_label": _candidate_label,
                    "state_sha256": v15_raw_facts["state_sha256"],
                    "raw_facts": v15_raw_facts,
                    "frozen_denominators": {
                        "effective_rhs_scale": v15_budget["effective_rhs_scale"],
                        "alpha_closure": frozen_alpha_scale,
                    },
                }
                v15_selection = select_v15_reference_pc_candidate(
                    [reference_pc_candidate], profile_identity=profile.name
                )
            else:
                bounded_numeric_gates = {
                    "original_regular_equation",
                    "complete_augmented_fe_equation",
                    "two_local_original_equations",
                    "global_alpha_port_closure",
                    "all_q_true_residuals",
                }
                candidate_structural_gates = {
                    name: value
                    for name, value in gate_facts["gates"].items()
                    if name not in bounded_numeric_gates
                }
                candidate_structural_gates["all_q_phases_covered"] = q_coverage_passed
                reference_pc_candidate = {
                    "metrics": reference_pc_metrics,
                    "frozen_scale_metrics": frozen_scale_metrics,
                    "structural_gates": candidate_structural_gates,
                    "state_label": _candidate_label,
                    "frozen_denominators": frozen_scales,
                }
                v15_selection = None
            v19_saved_v18_comparison = None
            if (
                v19_saved_v18_reference is not None
                and name in {"generic_full_independent", "nonzero_all_mode_port_rhs"}
            ):
                v19_saved_v18_comparison = _v19_compare_saved_v18_startup_case(
                    v19_saved_v18_reference,
                    case=name,
                    profile=profile,
                    independent_rows=independent,
                    current_rhs_storage=expected_storage,
                    current_port_rhs=g_rhs,
                    current_solution_storage=np.asarray(solution.array_r),
                    current_alpha=alpha,
                    current_q_rows=q_rows,
                    current_regular_residual=equation_relative,
                    current_regular_gate_passed=passed,
                    allocation_gate=allocation_gate,
                )
            builder_action_storage = np.zeros(layout.full_rows, dtype=np.complex128)
            builder_action_storage[independent] = sector_action
            packet = _save_packet(
                runtime,
                sample_label,
                {
                    "schema": (
                        "task40extra.review_v15_regular_inverse_full_witness.v1"
                        if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
                        else "task40extra.review_v10_regular_inverse_full_witness.v1"
                    ),
                    "profile_identity": profile.name,
                    "reference_pc_strategy": reference_pc_strategy,
                    "case": name,
                    "passed": passed,
                    "v19_saved_v18_startup_comparison": v19_saved_v18_comparison,
                    "legacy_gate_passed": passed,
                    "full_storage_rows": int(layout.full_rows),
                    "independent_storage_rows": independent.copy(),
                    "full_solution_storage": np.asarray(solution.array_r).copy(),
                    "physical_rhs_storage": expected_storage,
                    "global_ffcx_action_storage": native_action_storage,
                    "native_action_plus_port_rhs_storage": np.asarray(applied.array_r).copy(),
                    "full_residual_storage": np.asarray(error.array_r).copy(),
                    "sector_synthesized_action_storage": builder_action_storage,
                    "sector_synthesized_action_independent": sector_action,
                    "global_ffcx_action_independent": native_action_independent,
                    "sector_action_difference_independent": action_difference,
                    **{
                        f"local_ffcx_action_twist{twist}": vector
                        for twist, vector in sector_action_vectors.items()
                    },
                    "full_internal_recovery_residuals": recovery["arrays"][
                        "internal_residuals"
                    ],
                    "full_internal_effective_rhs": recovery["arrays"][
                        "internal_effective_rhs"
                    ],
                    "full_internal_saved_field_action": recovery["arrays"][
                        "internal_saved_field_action"
                    ],
                    "full_internal_original_rows": recovery["arrays"][
                        "internal_original_rows"
                    ],
                    "full_internal_twist_indices": recovery["arrays"][
                        "internal_twist_indices"
                    ],
                    "full_internal_recovery_formula": (
                        "effective_rhs - saved_field_local_ffcx_action"
                    ),
                    "full_internal_row_order": (
                        "twist_index ascending; original storage row ascending within twist"
                    ),
                    "local_native_residuals": recovery["arrays"]["native_residuals"],
                    "all_port_residuals": recovery["arrays"]["port_residuals"],
                    "native_action_identity_differences": recovery["arrays"][
                        "native_identity_differences"
                    ],
                    "schur_port_identity_differences": recovery["arrays"][
                        "schur_port_identity_differences"
                    ],
                    "saved_field_local_recovery_differences": recovery["arrays"][
                        "projected_saved_field_differences"
                    ],
                    "port_rhs": g_rhs.copy(),
                    "returned_alpha": np.asarray(alpha, dtype=np.complex128).copy(),
                    "recovered_alpha_plus_rhs_over_h": np.asarray(
                        alpha_expected, dtype=np.complex128
                    ).copy(),
                    "original_regular_equation_relative_residual": equation_relative,
                    "original_regular_equation_residual_norm": equation_residual_norm,
                    "original_regular_equation_limit": _REFERENCE_RESIDUAL_LIMIT,
                    "complete_augmented_fe_equation_relative_residual": complete_augmented_fe_equation_relative,
                    "complete_augmented_stacked_relative_diagnostic": augmented_stacked_relative_diagnostic,
                    "complete_augmented_equation_residual_norm": augmented_equation_residual_norm,
                    "complete_augmented_equation_rhs_norm_diagnostic": augmented_rhs_norm,
                    "complete_augmented_fe_residual": augmented_fe_residual,
                    "complete_augmented_port_residual": augmented_port_residual,
                    "complete_augmented_fe_row_formula": (
                        "physical_action(u) + B * (alpha - recover_auxiliary(u))"
                    ),
                    "complete_augmented_port_row_formula": (
                        "g - h * (alpha - recover_auxiliary(u)); H_p uses original h"
                    ),
                    "reference_pc_metrics": reference_pc_metrics,
                    "frozen_scale_metrics": frozen_scale_metrics,
                    "reference_pc_frozen_denominators": frozen_scales,
                    "reference_pc_structural_gates": candidate_structural_gates,
                    "sector_native_action_consistency_relative": action_relative,
                    "sector_native_action_consistency_operation_scale": action_operation_scale,
                    "full_internal_recovery_relative": recovery[
                        "internal_residual_relative"
                    ],
                    "full_internal_recovery_operation_scale": recovery[
                        "internal_operation_scale"
                    ],
                    "full_internal_recovery_rows": recovery["internal_row_count"],
                    "local_original_equation_relative": recovery[
                        "local_native_residual_relative"
                    ],
                    "all_port_equation_relative": recovery["port_residual_relative"],
                    "all_port_equation_operation_scale": recovery["port_operation_scale"],
                    "native_action_recovery_identity_relative": recovery[
                        "native_identity_relative"
                    ],
                    "native_action_recovery_identity_operation_scale": recovery[
                        "native_identity_operation_scale"
                    ],
                    "schur_port_recovery_identity_relative": recovery[
                        "schur_port_identity_relative"
                    ],
                    "schur_port_recovery_identity_operation_scale": recovery[
                        "schur_port_identity_operation_scale"
                    ],
                    "saved_field_local_recovery_relative": recovery[
                        "projected_saved_field_recovery_relative"
                    ],
                    "recovered_field_ffcx_apply_count": recovery[
                        "recovered_field_ffcx_apply_count"
                    ],
                    "recovered_field_ffcx_apply_seconds": recovery[
                        "recovered_field_ffcx_apply_seconds"
                    ],
                    "regular_recovery_relative_identity": port_relative,
                    "gate_facts": gate_facts,
                    "sector_action_facts": sector_action_facts,
                    "local_recovery_facts": recovery["sector_facts"],
                    "maximum_q_true_residual_relative": q_residual_max,
                    "q_true_residuals": q_rows,
                    "limits": gate_facts["limits"],
                    "physical_rhs_facts": dict(physical_rhs_facts),
                    **(
                        {
                            "v15_effective_rhs_scale": v15_budget["effective_rhs_scale"],
                            "v15_budget_numerator": v15_budget["budget_numerator"],
                            "v15_budget_term_norms": v15_budget["budget_terms"],
                            "v15_non_cancelling_budget_relative": v15_budget[
                                "noncancelling_budget_relative"
                            ],
                            "v15_eliminated_fe_residual_norm": v15_budget[
                                "eliminated_fe_residual_norm"
                            ],
                            "v15_eliminated_fe_relative": v15_budget[
                                "eliminated_fe_relative"
                            ],
                            "v15_complete_augmented_fe_residual_norm": v15_budget[
                                "complete_augmented_fe_residual_norm"
                            ],
                            "v15_complete_augmented_fe_relative": v15_budget[
                                "complete_augmented_fe_relative"
                            ],
                            "v15_decomposition_closure_norm": v15_budget[
                                "decomposition_closure_norm"
                            ],
                            "v15_decomposition_closure_scale": v15_budget[
                                "decomposition_closure_scale"
                            ],
                            "v15_d_b": v15_budget["d_b"],
                            "v15_d_A": v15_budget["d_A"],
                            "v15_lifted_sector_errors": tuple(
                                v15_budget["lifted_sector_errors"] or ()
                            ),
                            "v15_local_sector_errors": tuple(
                                v15_budget["local_sector_errors"] or ()
                            ),
                            "v15_eliminated_fe_residual_direct": v15_budget[
                                "eliminated_fe_residual_direct"
                            ],
                            "v15_eliminated_fe_residual_decomposed": v15_budget[
                                "eliminated_fe_residual_decomposed"
                            ],
                            "v15_complete_fe_residual_decomposed": v15_budget[
                                "complete_fe_residual_decomposed"
                            ],
                        }
                        if v15_budget is not None
                        else {}
                    ),
                },
            )
            row = {
                "name": name,
                "fe_rhs_nonzero_count": int(np.count_nonzero(fe_rhs)),
                "fe_rhs_norm": float(np.linalg.norm(fe_rhs)),
                "port_rhs_nonzero_count": int(np.count_nonzero(g_rhs)),
                "port_rhs_norm": float(np.linalg.norm(g_rhs)),
                "v19_saved_v18_startup_comparison": v19_saved_v18_comparison,
                "original_regular_equation_relative_residual": equation_relative,
                "original_regular_equation_limit": _REFERENCE_RESIDUAL_LIMIT,
                "sector_native_action_consistency_relative": action_relative,
                "sector_native_action_consistency_operation_scale": action_operation_scale,
                "sector_native_action_consistency_limit": _REGULAR_ACTION_LIMIT,
                "sector_native_action_facts": sector_action_facts,
                "full_internal_recovery_relative": recovery[
                    "internal_residual_relative"
                ],
                "full_internal_recovery_operation_scale": recovery[
                    "internal_operation_scale"
                ],
                "full_internal_recovery_rows": recovery["internal_row_count"],
                "full_internal_recovery_limit": _REGULAR_RECOVERY_LIMIT,
                "local_original_equation_relative": recovery[
                    "local_native_residual_relative"
                ],
                "all_port_equation_relative": recovery["port_residual_relative"],
                "all_port_equation_limit": _PORT_CLOSURE_LIMIT,
                "native_action_recovery_identity_relative": recovery[
                    "native_identity_relative"
                ],
                "native_action_recovery_identity_limit": _IDENTITY_LIMIT,
                "schur_port_recovery_identity_relative": recovery[
                    "schur_port_identity_relative"
                ],
                "schur_port_recovery_identity_limit": _IDENTITY_LIMIT,
                "saved_field_local_recovery_relative": recovery[
                    "projected_saved_field_recovery_relative"
                ],
                "saved_field_local_recovery_identity_limit": _REGULAR_RECOVERY_LIMIT,
                "recovered_field_ffcx_apply_count": recovery[
                    "recovered_field_ffcx_apply_count"
                ],
                "recovered_field_ffcx_apply_seconds": recovery[
                    "recovered_field_ffcx_apply_seconds"
                ],
                "regular_port_closure_relative": port_relative,
                "regular_port_closure_residual_norm": alpha_closure_residual_norm,
                "complete_augmented_fe_equation_relative_residual": complete_augmented_fe_equation_relative,
                "complete_augmented_stacked_relative_diagnostic": augmented_stacked_relative_diagnostic,
                "complete_augmented_equation_residual_norm": augmented_equation_residual_norm,
                "complete_augmented_equation_rhs_norm_diagnostic": augmented_rhs_norm,
                "reference_pc_metrics": reference_pc_metrics,
                "frozen_scale_metrics": frozen_scale_metrics,
                "reference_pc_frozen_denominators": frozen_scales,
                "reference_pc_structural_gates": candidate_structural_gates,
                "reference_pc_candidate": reference_pc_candidate,
                "v15_native_budget": (
                    {
                        key: v15_budget[key]
                        for key in (
                            "effective_rhs_scale",
                            "budget_numerator",
                            "budget_terms",
                            "noncancelling_budget_relative",
                            "eliminated_fe_residual_norm",
                            "eliminated_fe_relative",
                            "complete_augmented_fe_residual_norm",
                            "complete_augmented_fe_relative",
                            "decomposition_closure_norm",
                            "decomposition_closure_scale",
                            "decomposition_closure_relative",
                            "effective_rhs_identity_error_norm",
                            "sector_facts",
                        )
                    }
                    if v15_budget is not None
                    else None
                ),
                "regular_recovery_limit": _REGULAR_RECOVERY_LIMIT,
                "maximum_q_true_residual_relative": q_residual_max,
                "q_true_residuals": q_rows,
                "all_q_branches_exercised": q_coverage_passed,
                "all_four_q_branches_exercised": (
                    profile.q_count == 4 and q_coverage_passed
                ),
                "expected_port_mode_count": profile.mode_count,
                "all_port_modes_exercised": recovery["port_mode_count"] == profile.mode_count,
                "regular_equation_limit": _REFERENCE_RESIDUAL_LIMIT,
                "identity_limit": _REGULAR_RECOVERY_LIMIT,
                "full_witness_packet": packet,
                "gates": gate_facts["gates"],
                "failed_gates": gate_facts["failed_gates"],
                "passed": passed,
            }
            if (
                reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
                and _candidate_label == "initial"
            ):
                initial_selection = v15_selection
                candidate_rows = [row]
                candidate_states = [reference_pc_candidate]
                if initial_selection["admitted"]:
                    row["reference_pc_admission"] = "V15_REFERENCE_PC_PASS"
                    row["reference_pc_selection"] = initial_selection
                    row["reference_pc_initial_v15_passed"] = True
                    row["selected_v15_metrics"] = dict(reference_pc_candidate["metrics"])
                    row["selected_v15_raw_facts"] = dict(
                        reference_pc_candidate["raw_facts"]
                    )
                    row["selected_state_sha256"] = reference_pc_candidate["state_sha256"]
                    row["passed"] = True
                elif all(candidate_structural_gates.values()) and _allow_correction:
                    if augmented_fe_residual is None or augmented_port_residual is None:
                        raise RuntimeError(
                            "V15 complete augmented residual was not independently evaluated"
                        )

                    def raw_v15_nonrecursive_inverse(fe_error, port_error):
                        calls_before = int(inverse.factors.calls)
                        delta_fe, delta_port = inverse.apply_augmented(
                            fe_error,
                            port_rhs=port_error,
                            rhs_category="reference_correction_rhs_mat_solve_count",
                        )
                        calls_after = int(inverse.factors.calls)
                        correction_rows = [
                            q_row
                            for sector_audit in inverse.last_solve_audit
                            for q_row in sector_audit["q_true_residuals"]
                        ]
                        return delta_fe, delta_port, {
                            "counter_source": FACTOR_CALL_COUNTER_SOURCE,
                            "factor_calls_before": calls_before,
                            "factor_calls_after": calls_after,
                            "q_true_residuals": correction_rows,
                        }

                    correction = apply_one_augmented_residual_correction(
                        solution_values,
                        alpha,
                        augmented_fe_residual,
                        augmented_port_residual,
                        raw_inverse=raw_v15_nonrecursive_inverse,
                        allocation_gate=allocation_gate,
                        require_verified_solve_counter=True,
                        expected_q_count=profile.q_count,
                        factor_capabilities=_v19_factor_capabilities(inverse),
                    )
                    correction_packet = _save_packet(
                        runtime,
                        f"v15_regular_inverse_{name}_augmented_correction",
                        {
                            "schema": "task40extra.review_v15_augmented_reference_correction.v1",
                            "case": name,
                            "reference_pc_strategy": reference_pc_strategy,
                            "initial_v15_metrics": dict(reference_pc_candidate["metrics"]),
                            "initial_v15_raw_facts": dict(reference_pc_candidate["raw_facts"]),
                            "finite_element_residual": augmented_fe_residual,
                            "port_residual": augmented_port_residual,
                            "finite_element_state_before": solution_values.copy(),
                            "port_state_before": alpha.copy(),
                            "finite_element_delta": correction.finite_element - solution_values,
                            "port_delta": correction.port_amplitudes - alpha,
                            "finite_element_state_after": correction.finite_element,
                            "port_state_after": correction.port_amplitudes,
                            "correction_audit": dict(correction.audit),
                        },
                    )
                    correction_audit = {
                        **dict(correction.audit),
                        "witness_packet": correction_packet,
                        "full_augmented_equation": True,
                        "fe_residual_sign": "expected_rhs - independent native augmented action",
                        "port_residual_sign": "g - H*(alpha - recover_auxiliary(u))",
                    }
                    corrected_checks = _verify_regular_inverse(
                        runtime,
                        reference,
                        physical_rhs,
                        physical_rhs_facts,
                        allocation_gate=allocation_gate,
                        reference_pc_strategy=reference_pc_strategy,
                        _case_filter=name,
                        _candidate_state=(
                            correction.finite_element, correction.port_amplitudes
                        ),
                        _frozen_scales=current_scales,
                        _candidate_label="corrected_v15",
                        _allow_correction=False,
                        include_mixed_fe_port_cases=include_mixed_fe_port_cases,
                    )
                    corrected_row = corrected_checks["cases"][0]
                    candidate_rows.append(corrected_row)
                    candidate_states.append(corrected_row["reference_pc_candidate"])
                    final_selection = select_v15_reference_pc_candidate(
                        candidate_states, profile_identity=profile.name
                    )
                    selected_index = int(final_selection["selected_candidate_index"])
                    row = candidate_rows[selected_index]
                    selected_candidate = candidate_states[selected_index]
                    row["reference_pc_initial_v15_passed"] = False
                    row["reference_pc_admission"] = final_selection["admission"]
                    row["reference_pc_selection"] = final_selection
                    row["reference_pc_candidates"] = [
                        {
                            "state_label": candidate.get("state_label"),
                            "metrics": candidate["metrics"],
                            "frozen_scale_metrics": candidate["frozen_scale_metrics"],
                            "structural_gates": candidate["structural_gates"],
                            "raw_facts": candidate["raw_facts"],
                            "state_sha256": candidate["state_sha256"],
                        }
                        for candidate in candidate_states
                    ]
                    row["reference_pc_correction_audit"] = correction_audit
                    row["selected_v15_metrics"] = dict(selected_candidate["metrics"])
                    row["selected_v15_raw_facts"] = dict(selected_candidate["raw_facts"])
                    row["selected_state_sha256"] = selected_candidate["state_sha256"]
                    row["passed"] = bool(final_selection["admitted"])
                    if not row["passed"]:
                        row["failed_gates"] = list(dict.fromkeys([
                            *row.get("failed_gates", ()),
                            "v15_native_augmented_residual_admission",
                        ]))
                else:
                    row["reference_pc_admission"] = "V15_REFERENCE_PC_REJECTED"
                    row["reference_pc_selection"] = initial_selection
                    row["reference_pc_initial_v15_passed"] = False
                    row["passed"] = False
                    row["failed_gates"] = list(dict.fromkeys([
                        *row.get("failed_gates", ()),
                        "v15_structural_or_numeric_admission",
                    ]))
            elif reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
                row["reference_pc_admission"] = (
                    "V15_REFERENCE_PC_PASS" if v15_selection["admitted"]
                    else "V15_REFERENCE_PC_REJECTED"
                )
                row["reference_pc_selection"] = v15_selection
                row["reference_pc_candidate_label"] = _candidate_label
                row["selected_v15_metrics"] = dict(reference_pc_candidate["metrics"])
                row["selected_v15_raw_facts"] = dict(reference_pc_candidate["raw_facts"])
                row["selected_state_sha256"] = reference_pc_candidate["state_sha256"]
                row["selected_decomposition_closure_relative"] = float(
                    v15_budget["decomposition_closure_relative"]
                )
                row["port_identity_relative"] = float(
                    reference_pc_candidate["metrics"]["alpha_closure"]
                )
                row["passed"] = bool(v15_selection["admitted"])
            elif reference_pc_strategy == STRICT_THEN_BOUNDED_INEXACT_V13 and _candidate_label == "initial":
                initial_selection = select_reference_pc_candidate([reference_pc_candidate])
                correction_audit = None
                candidate_rows = [row]
                candidate_states = [reference_pc_candidate]
                if initial_selection["admission"] == STRICT_REFERENCE_PASS:
                    row["reference_pc_admission"] = STRICT_REFERENCE_PASS
                    row["reference_pc_selection"] = initial_selection
                    row["passed"] = True
                elif all(candidate_structural_gates.values()) and _allow_correction:
                    if augmented_fe_residual is None or augmented_port_residual is None:
                        raise RuntimeError("V13 complete augmented residual was not independently evaluated")

                    def raw_nonrecursive_inverse(fe_error, port_error):
                        calls_before = int(inverse.factors.calls)
                        delta_fe, delta_port = inverse.apply_augmented(
                            fe_error,
                            port_rhs=port_error,
                            rhs_category="reference_correction_rhs_mat_solve_count",
                        )
                        calls_after = int(inverse.factors.calls)
                        solve_audit = inverse.last_solve_audit
                        correction_q_rows = [
                            q_row
                            for sector_audit in solve_audit
                            for q_row in sector_audit["q_true_residuals"]
                        ]
                        return delta_fe, delta_port, {
                            "counter_source": FACTOR_CALL_COUNTER_SOURCE,
                            "factor_calls_before": calls_before,
                            "factor_calls_after": calls_after,
                            "q_true_residuals": correction_q_rows,
                        }

                    correction = apply_one_augmented_residual_correction(
                        solution_values,
                        alpha,
                        augmented_fe_residual,
                        augmented_port_residual,
                        raw_inverse=raw_nonrecursive_inverse,
                        allocation_gate=allocation_gate,
                        require_verified_solve_counter=True,
                        factor_capabilities=_v19_factor_capabilities(inverse),
                    )
                    correction_packet = _save_packet(
                        runtime,
                        f"v13_regular_inverse_{name}_augmented_correction",
                        {
                            "schema": "task40extra.review_v13_augmented_reference_correction.v1",
                            "case": name,
                            "reference_pc_strategy": reference_pc_strategy,
                            "finite_element_residual": augmented_fe_residual,
                            "port_residual": augmented_port_residual,
                            "complete_augmented_fe_equation_relative_residual": complete_augmented_fe_equation_relative,
                            "complete_augmented_stacked_relative_diagnostic": augmented_stacked_relative_diagnostic,
                            "complete_augmented_fe_row_formula": (
                                "physical_action(u) + B * (alpha - recover_auxiliary(u))"
                            ),
                            "complete_augmented_port_row_formula": (
                                "g - h * (alpha - recover_auxiliary(u))"
                            ),
                            "finite_element_state_before": solution_values.copy(),
                            "port_state_before": alpha.copy(),
                            "finite_element_delta": correction.finite_element - solution_values,
                            "port_delta": correction.port_amplitudes - alpha,
                            "finite_element_state_after": correction.finite_element,
                            "port_state_after": correction.port_amplitudes,
                            "correction_audit": dict(correction.audit),
                        },
                    )
                    correction_audit = {
                        **dict(correction.audit),
                        "witness_packet": correction_packet,
                        "full_augmented_equation": True,
                        "fe_residual_sign": "expected_rhs - independent_reference_action(u, alpha)",
                        "port_residual_sign": "h * (alpha_expected - alpha)",
                    }
                    corrected_checks = _verify_regular_inverse(
                        runtime,
                        reference,
                        physical_rhs,
                        physical_rhs_facts,
                        allocation_gate=allocation_gate,
                        reference_pc_strategy=reference_pc_strategy,
                        _case_filter=name,
                        _candidate_state=(
                            correction.finite_element, correction.port_amplitudes
                        ),
                        _frozen_scales=current_scales,
                        _candidate_label="corrected_v13",
                        _allow_correction=False,
                        include_mixed_fe_port_cases=include_mixed_fe_port_cases,
                    )
                    corrected_row = corrected_checks["cases"][0]
                    candidate_rows.append(corrected_row)
                    candidate_states.append(corrected_row["reference_pc_candidate"])
                    final_selection = select_reference_pc_candidate(candidate_states)
                    selected_index = int(final_selection["selected_candidate_index"])
                    row = candidate_rows[selected_index]
                    row["reference_pc_initial_strict_gate_passed"] = bool(
                        initial_selection["admission"] == STRICT_REFERENCE_PASS
                    )
                    row["reference_pc_admission"] = final_selection["admission"]
                    row["reference_pc_selection"] = final_selection
                    row["reference_pc_candidates"] = [
                        {
                            "label": "initial" if index == 0 else "corrected_v13",
                            "metrics": candidate["metrics"],
                            "frozen_scale_metrics": candidate["frozen_scale_metrics"],
                            "structural_gates": candidate["structural_gates"],
                            "q_true_residuals": candidate_rows[index].get("q_true_residuals"),
                            "maximum_q_true_residual_relative": candidate_rows[index].get(
                                "maximum_q_true_residual_relative"
                            ),
                            "full_witness_packet": candidate_rows[index].get("full_witness_packet"),
                        }
                        for index, candidate in enumerate(candidate_states)
                    ]
                    row["reference_pc_correction_audit"] = correction_audit
                    row["passed"] = bool(final_selection["admitted"])
                    if not row["passed"]:
                        row["failed_gates"] = list(dict.fromkeys([
                            *row.get("failed_gates", ()),
                            "reference_pc_original_and_frozen_scale_admission",
                        ]))
                else:
                    row["reference_pc_admission"] = REFERENCE_PC_REJECTED
                    row["reference_pc_selection"] = initial_selection
                    row["reference_pc_initial_strict_gate_passed"] = bool(
                        initial_selection["admission"] == STRICT_REFERENCE_PASS
                    )
                    row["passed"] = False
                    row["failed_gates"] = list(dict.fromkeys([
                        *row.get("failed_gates", ()),
                        "reference_pc_structural_or_numeric_admission",
                    ]))
            elif reference_pc_strategy == STRICT_THEN_BOUNDED_INEXACT_V13:
                row["reference_pc_admission"] = (
                    STRICT_REFERENCE_PASS if passed else REFERENCE_PC_REJECTED
                )
                row["reference_pc_candidate_label"] = _candidate_label
                row["passed"] = bool(passed)
            elif not passed:
                raise ValueError(
                    f"regular p6 inverse gates failed for {name}: "
                    f"{gate_facts['failed_gates']}; full witness saved: {row}"
                )
            if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
                selected_candidate = row.get(
                    "reference_pc_candidate", reference_pc_candidate
                )
                selected_metrics = row.get(
                    "selected_v15_metrics", selected_candidate.get("metrics", {})
                )
                selected_raw = row.get(
                    "selected_v15_raw_facts", selected_candidate.get("raw_facts", {})
                )
                selected_q_rows = selected_raw.get("q_true_residuals", ())
                selected_closure_norm = float(
                    selected_raw.get("decomposition_closure_norm", np.nan)
                )
                selected_closure_scale = float(
                    selected_raw.get("decomposition_closure_scale", np.nan)
                )
                row["reference_pc_strategy"] = reference_pc_strategy
                row["candidate_metrics"] = row.get(
                    "reference_pc_candidates", [selected_candidate]
                )
                row["candidate_selection"] = row.get(
                    "reference_pc_selection", v15_selection
                )
                row["selected_v15_metrics"] = dict(selected_metrics)
                row["selected_v15_raw_facts"] = dict(selected_raw)
                row["selected_state_sha256"] = selected_candidate.get(
                    "state_sha256", selected_raw.get("state_sha256")
                )
                row["port_identity_relative"] = float(
                    selected_metrics.get("alpha_closure", np.inf)
                )
                row["maximum_q_true_residual_relative"] = max(
                    (
                        float(q_row.get("true_residual_relative", np.inf))
                        for q_row in selected_q_rows
                        if isinstance(q_row, Mapping)
                    ),
                    default=float("inf"),
                )
                row["q_true_residuals_selected"] = list(selected_q_rows)
                row["all_q_used"] = bool(
                    len(selected_q_rows) == profile.q_count
                    and {int(q_row.get("q", -1)) for q_row in selected_q_rows}
                    == set(range(profile.q_count))
                )
                row["all_four_q_used"] = profile.q_count == 4 and row["all_q_used"]
                row["selected_decomposition_closure_relative"] = (
                    selected_closure_norm / selected_closure_scale
                    if selected_closure_scale > 0.0
                    else (
                        0.0
                        if selected_closure_norm == 0.0
                        else float("inf")
                    )
                )
            row.update(
                _task40_v31_reference_tier_receipt(
                    row, reference_pc_strategy=reference_pc_strategy
                )
            )
            runtime_prefix = (
                "v15" if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
                else "v13" if reference_pc_strategy == STRICT_THEN_BOUNDED_INEXACT_V13
                else "v10"
            )
            runtime.marker(f"{runtime_prefix}_regular_inverse_{name}_evaluated", row)
            if not row["passed"] and reference_pc_strategy == STRICT_ONLY:
                raise ValueError(
                    f"regular p6 inverse gates failed for {name}: "
                    f"{gate_facts['failed_gates']}; full witness saved: {row}"
                )
            records.append(row)
            runtime.marker(f"{runtime_prefix}_regular_inverse_{name}_complete", row)
        finally:
            if error is not None:
                error.destroy()
            port_load.destroy()
            applied.destroy()
            solution.destroy()
        runtime.sample(f"v10_regular_inverse_{name}_after")

    v19_comparison_cases = {
        str(row["name"]): row["v19_saved_v18_startup_comparison"]
        for row in records
        if row.get("v19_saved_v18_startup_comparison") is not None
    }
    return {
        "schema": _regular_inverse_checks_schema(
            profile,
            reference_pc_strategy,
            include_mixed_fe_port_cases=include_mixed_fe_port_cases,
        ),
        "profile": profile.identity(),
        "cases": records,
        "case_count": len(records),
        "required_case_names": list(case_names),
        "observed_case_names": [str(row["name"]) for row in records],
        "case_coverage_passed": (
            len(records) == len(case_names)
            and {str(row["name"]) for row in records} == set(case_names)
        ),
        "strict_reference_passed": (
            len(records) == len(case_names)
            and {str(row["name"]) for row in records} == set(case_names)
            and all(row.get("strict_reference_passed") is True for row in records)
        ),
        "strict_reference_status_by_case": {
            str(row["name"]): {
                "admission": row.get("strict_reference_admission"),
                "passed": row.get("strict_reference_passed"),
                "selected_state_sha256": row.get(
                    "strict_reference_selected_state_sha256"
                ),
            }
            for row in records
        },
        "v15_reference_passed": (
            None
            if reference_pc_strategy != NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
            else len(records) == len(case_names)
            and {str(row["name"]) for row in records} == set(case_names)
            and all(row.get("v15_reference_passed") is True for row in records)
        ),
        "v15_reference_status_by_case": {
            str(row["name"]): {
                "admission": row.get("v15_reference_admission"),
                "passed": row.get("v15_reference_passed"),
                "selected_state_sha256": row.get(
                    "v15_reference_selected_state_sha256"
                ),
            }
            for row in records
        },
        "all_q_exercised_per_case": True,
        "all_four_q_exercised_per_case": profile.q_count == 4,
        "interior_rows_exercised_per_case": profile.global_interior_rows,
        "all_port_modes_exercised_per_case": profile.mode_count,
        "regular_equation_limit": _REFERENCE_RESIDUAL_LIMIT,
        "sector_native_action_consistency_limit": _REGULAR_ACTION_LIMIT,
        "regular_recovery_limit": _REGULAR_RECOVERY_LIMIT,
        "all_port_equation_limit": _PORT_CLOSURE_LIMIT,
        "native_action_recovery_identity_limit": _IDENTITY_LIMIT,
        "schur_port_recovery_identity_limit": _IDENTITY_LIMIT,
        "q_true_residual_limit": (
            float(inverse.q_solve_limit)
            if reference_pc_strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
            else _REFERENCE_RESIDUAL_LIMIT
        ),
        "factor_probe_true_residual_limit": float(inverse.factors.factor_probe_limit),
        "physical_rhs_facts": dict(physical_rhs_facts),
        "v19_saved_v18_startup_comparison": (
            {
                "required_cases": [
                    "generic_full_independent",
                    "nonzero_all_mode_port_rhs",
                ],
                "cases": v19_comparison_cases,
                "all_required_cases_compared": set(v19_comparison_cases)
                == {"generic_full_independent", "nonzero_all_mode_port_rhs"},
                "delta_gate": "none; current existing equation and q strict residual gates remain decisive",
            }
            if v19_saved_v18_reference is not None
            else None
        ),
        "passed": (
            len(records) == len(case_names)
            and {str(row["name"]) for row in records} == set(case_names)
            and all(row["passed"] for row in records)
        ),
    }


class _P6ReferencePreconditioner:
    """Apply the regular two-cell inverse on the target trace+port space."""

    def __init__(
        self, runtime: Any, owner: dict[str, Any], target_action: Any,
        target_carrier: Any, *, allocation_gate: Any,
    ):
        from petsc4py import PETSc

        self.runtime = runtime
        self.PETSc = PETSc
        self.allocation_gate = allocation_gate
        if not callable(self.allocation_gate):
            raise TypeError("V13 PC requires the live allocation gate")
        self.owner = owner
        self.reference = owner["global_bundle"]
        self.profile = owner["profile"]
        self.layout = owner["full_layout"]
        self.inverse = owner["inverse"]
        self.target_action = target_action
        self.target_condensed = target_action.condensed
        self.independent = np.asarray(self.layout.independent, dtype=np.int64)
        self.reference_row = {int(row): i for i, row in enumerate(self.independent)}
        if self.target_condensed.full_rows != self.layout.full_rows:
            raise ValueError("target and regular p6 storage row counts differ")
        if self.target_condensed.appended_rows != len(self.reference["modes"]):
            raise ValueError("target retained port count differs from regular reference")
        if self.target_action.reduced_size != (
            self.target_condensed.active_rows + self.target_condensed.appended_rows
        ):
            raise ValueError("target KSP vector is not the actual trace+port retained space")
        target_constraints = self.target_condensed.trace_constraints
        if any(
            int(original) not in self.reference_row
            for original in target_constraints.owned_active_original_dofs
        ):
            raise ValueError("target active trace map is not contained in regular independent rows")
        reference_carrier = self.reference["dtn_action"].carrier
        if tuple(entry.mode_key for entry in target_carrier.entries) != tuple(
            entry.mode_key for entry in reference_carrier.entries
        ):
            raise ValueError("target and regular retained port order differs")
        self.h = np.asarray(
            [entry.normalization_h for entry in self.reference["dtn_action"].carrier.entries],
            dtype=np.float64,
        )
        self.calls = 0
        self._v15_native_evaluation_count = 0
        self._v15_first_packet: dict[str, Any] | None = None
        self._v15_last_state_arrays: dict[str, Any] | None = None
        self.last_facts = {
            "maximum_q_true_residual_relative": 0.0,
            "port_identity_relative": 0.0,
            "q_true_residuals": [],
        }

    def _evaluate_complete_augmented_state(
        self, finite_element: np.ndarray, port_amplitudes: np.ndarray,
        fe_rhs: np.ndarray, port_rhs: np.ndarray, *, label: str,
        capture_physical_action: bool = False,
    ) -> dict[str, Any]:
        from src.solvers.augmented_reference_correction import (
            augmented_port_state_offset,
            evaluate_complete_augmented_residual,
            stable_euclidean_norm,
        )

        if finite_element.shape != (len(self.independent),):
            raise ValueError("V13 reference FE candidate has the wrong independent layout")
        if port_amplitudes.shape != (self.profile.mode_count,):
            raise ValueError("V13 reference alpha candidate has the wrong port layout")
        if fe_rhs.shape != (len(self.independent),) or port_rhs.shape != (self.profile.mode_count,):
            raise ValueError("V13 augmented reference RHS has the wrong layout")
        is_v15 = self.inverse.reference_pc_strategy == (
            "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
        )
        prefix = "v15" if is_v15 else "v13"
        self.allocation_gate(
            f"task40_{prefix}_pc_complete_augmented_residual_evaluation",
            {
                "additional_payload_bytes": 16 * (
                    3 * int(self.layout.full_rows)
                    + 4 * int(len(self.independent))
                    + 7 * int(self.profile.mode_count)
                    + (int(self.layout.full_rows) if capture_physical_action else 0)
                ) + max(
                    int(self.layout.full_rows),
                    int(len(self.independent)),
                    int(self.profile.mode_count),
                ),
                "workspace_bytes": 0,
                "native_volume_action_is_independent": True,
                "native_dual_coupling_uses_actual_returned_alpha": True,
                "port_row_uses_original_h": True,
                "shared_solver_residual_core": True,
                "capture_physical_action_for_v15_native_budget": bool(
                    capture_physical_action
                ),
                "evaluation_label": str(label),
            },
        )
        solution = self.PETSc.Vec().createSeq(
            self.layout.full_rows, comm=self.PETSc.COMM_SELF
        )
        physical_action = solution.duplicate()
        port_coupling = solution.duplicate()
        try:
            solution.set(0.0)
            _assign_vector_storage(solution, finite_element, rows=self.independent)
            self.reference["physical_action"].apply(solution, physical_action)
            recovered = np.asarray(
                self.reference["dtn_action"].recover_auxiliary(solution),
                dtype=np.complex128,
            )
            port_coupling.set(0.0)
            self.reference["dtn_action"].apply_modal_rhs(
                port_rhs / self.h, port_coupling
            )
            original_fe_equation_scale = (
                stable_euclidean_norm(fe_rhs) + float(port_coupling.norm())
            )
            port_state_offset = augmented_port_state_offset(
                port_amplitudes, recovered
            )
            port_coupling.set(0.0)
            self.reference["dtn_action"].apply_modal_rhs(
                port_state_offset, port_coupling
            )
            complete = evaluate_complete_augmented_residual(
                physical_action_storage=np.asarray(
                    physical_action.array_r, dtype=np.complex128
                ),
                dual_coupling_storage=np.asarray(
                    port_coupling.array_r, dtype=np.complex128
                ),
                finite_element_rhs=fe_rhs,
                port_amplitudes=port_amplitudes,
                recovered_port_amplitudes=recovered,
                port_state_offset=port_state_offset,
                port_rhs=port_rhs,
                h=self.h,
                original_fe_equation_scale=original_fe_equation_scale,
                independent_rows=self.independent,
            )
            if capture_physical_action:
                complete["physical_action_storage"] = np.asarray(
                    physical_action.array_r, dtype=np.complex128
                ).copy()
        finally:
            port_coupling.destroy()
            physical_action.destroy()
            solution.destroy()
        return complete

    def _evaluate_v15_state(
        self,
        finite_element: np.ndarray,
        port_amplitudes: np.ndarray,
        fe_rhs: np.ndarray,
        port_rhs: np.ndarray,
        q_rows: list[dict[str, Any]],
        *,
        label: str,
        frozen_alpha_scale: float | None = None,
        retained_candidate_state_count: int = 0,
    ) -> dict[str, Any]:
        from src.solvers.augmented_reference_correction import (
            NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
            augmented_state_sha256,
            stable_euclidean_norm,
            select_v15_reference_pc_candidate,
        )

        evaluation_started = time.perf_counter()
        complete = self._evaluate_complete_augmented_state(
            finite_element,
            port_amplitudes,
            fe_rhs,
            port_rhs,
            label=label,
            capture_physical_action=True,
        )
        template = self.PETSc.Vec().createSeq(
            self.layout.full_rows, comm=self.PETSc.COMM_SELF
        )
        try:
            budget = _v15_native_budget_facts(
                self.owner,
                template,
                fe_rhs,
                port_rhs,
                port_amplitudes,
                finite_element,
                complete["physical_action_storage"],
                complete["finite_element_residual"],
                self.PETSc,
                allocation_gate=self.allocation_gate,
                retain_lifted_errors=True,
                retained_candidate_state_count=retained_candidate_state_count,
            )
        finally:
            template.destroy()
        complete.pop("physical_action_storage", None)

        expected_qs = set(range(self.profile.q_count))
        q_coverage = (
            len(q_rows) == self.profile.q_count
            and {int(row.get("q", -1)) for row in q_rows} == expected_qs
        )
        q_max = max(
            (float(row.get("true_residual_relative", np.inf)) for row in q_rows),
            default=float("inf"),
        )
        alpha_norm = float(complete["alpha_closure_residual_norm"])
        alpha_scale = float(complete["alpha_closure_raw_scale"])
        frozen_scale = (
            alpha_scale if frozen_alpha_scale is None else float(frozen_alpha_scale)
        )

        def relative(numerator: float, denominator: float) -> float:
            numerator = float(numerator)
            denominator = float(denominator)
            if not np.isfinite(numerator) or not np.isfinite(denominator):
                return float("inf")
            if denominator < 0.0:
                return float("inf")
            if denominator == 0.0:
                return 0.0 if numerator == 0.0 else float("inf")
            return numerator / denominator

        startup = self.owner.get("regular_inverse_checks", {})
        startup_passed = (
            isinstance(startup, Mapping) and startup.get("passed") is True
        )
        closure_relative = float(budget["decomposition_closure_relative"])
        metrics = {
            "eliminated_fe": float(budget["eliminated_fe_relative"]),
            "complete_augmented_fe": float(
                budget["complete_augmented_fe_relative"]
            ),
            "noncancelling_budget": float(
                budget["noncancelling_budget_relative"]
            ),
            "alpha_closure": relative(alpha_norm, alpha_scale),
            "q_solve": q_max,
        }
        frozen_metrics = {
            "eliminated_fe": metrics["eliminated_fe"],
            "complete_augmented_fe": metrics["complete_augmented_fe"],
            "noncancelling_budget": metrics["noncancelling_budget"],
            "alpha_closure": relative(alpha_norm, frozen_scale),
        }
        state_hash = augmented_state_sha256(finite_element, port_amplitudes)
        raw_facts = {
            "profile_identity": self.profile.name,
            "effective_rhs_scale": float(budget["effective_rhs_scale"]),
            "eliminated_fe_residual_norm": float(
                budget["eliminated_fe_residual_norm"]
            ),
            "complete_augmented_fe_residual_norm": float(
                budget["complete_augmented_fe_residual_norm"]
            ),
            "budget_term_norms": dict(budget["budget_terms"]),
            "alpha_closure_residual_norm": alpha_norm,
            "alpha_closure_original_scale": alpha_scale,
            "alpha_closure_frozen_scale": frozen_scale,
            "q_true_residuals": copy.deepcopy(q_rows),
            "retained_mode_count": int(self.profile.mode_count),
            "decomposition_closure_norm": float(
                budget["decomposition_closure_norm"]
            ),
            "decomposition_closure_scale": float(
                budget["decomposition_closure_scale"]
            ),
            "effective_rhs_identity_error_norm": float(
                budget["effective_rhs_identity_error_norm"]
            ),
            "native_sector_facts": copy.deepcopy(budget["sector_facts"]),
            "state_sha256": state_hash,
        }
        structural = {
            "startup_regular_inverse_gates_passed": startup_passed,
            "all_q_phases_covered": q_coverage,
            "all_retained_modes_mapped_once": bool(
                budget["all_modes_covered_once"]
            ),
            "native_decomposition_closure": bool(
                np.isfinite(closure_relative) and closure_relative <= 1.0e-10
            ),
            "native_augmented_actions_finite": bool(
                np.isfinite(budget["effective_rhs_scale"])
                and np.isfinite(budget["budget_numerator"])
                and np.isfinite(alpha_norm)
                and np.isfinite(alpha_scale)
            ),
        }
        candidate = {
            "metrics": metrics,
            "frozen_scale_metrics": frozen_metrics,
            "structural_gates": structural,
            "state_label": label,
            "state_sha256": state_hash,
            "raw_facts": raw_facts,
            "frozen_denominators": {
                "effective_rhs_scale": float(budget["effective_rhs_scale"]),
                "alpha_closure": frozen_scale,
            },
            "native_evaluation_seconds": float(
                time.perf_counter() - evaluation_started
            ),
        }
        self._v15_native_evaluation_count = (
            int(getattr(self, "_v15_native_evaluation_count", 0)) + 1
        )
        candidate["native_evaluation_ordinal"] = self._v15_native_evaluation_count
        return {
            "candidate": candidate,
            "complete": complete,
            "budget": budget,
            "q_rows": copy.deepcopy(q_rows),
            "selection": select_v15_reference_pc_candidate(
                [candidate], profile_identity=self.profile.name
            ),
        }

    def _save_v15_pc_packet(
        self,
        label: str,
        fe_rhs: np.ndarray,
        port_rhs: np.ndarray,
        states: list[tuple[np.ndarray, np.ndarray, Mapping[str, Any] | None]],
        *,
        status: str,
        failure: str | None = None,
        selection: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        state_count = sum(evaluated is not None for _, _, evaluated in states)
        n_independent = int(len(fe_rhs))
        n_modes = int(len(port_rhs))
        copied_vector_bytes = 16 * (
            n_independent + n_modes
            + len(states) * (n_independent + n_modes)
            + state_count * (18 * n_independent + 2 * n_modes)
        )
        self.allocation_gate(
            "task40_v15_pc_state_evidence_packet_staging",
            {
                "additional_payload_bytes": copied_vector_bytes,
                "workspace_bytes": copied_vector_bytes,
                "simultaneous_packet_and_writer_peak_bytes": 2 * copied_vector_bytes,
                "candidate_state_count": len(states),
                "evaluated_candidate_count": state_count,
                "per_candidate_vector_equivalents": {
                    "finite_element_and_alpha": 1,
                    "complete_fe_residual": 1,
                    "port_and_alpha_closure_residuals": 2,
                    "budget_decomposition_and_native_residuals": 17,
                },
                "rhs_vector_equivalents": 1,
                "hash_bound_packet_only_for_first_last_or_failure": True,
            },
        )
        payload: dict[str, Any] = {
            "schema": "task40extra.review_v15_p6_pc_state_evidence.v1",
            "reference_pc_strategy": "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15",
            "profile": self.profile.name,
            "profile_identity": self.profile.name,
            "call": int(self.calls),
            "status": status,
            "failure": failure,
            "candidate_selection": dict(selection or {}),
            "candidate_facts": [],
            "fe_rhs": np.asarray(fe_rhs, dtype=np.complex128).copy(),
            "port_rhs": np.asarray(port_rhs, dtype=np.complex128).copy(),
        }
        for index, (finite_element, alpha, evaluated) in enumerate(states):
            payload[f"candidate_{index}_finite_element_state"] = np.asarray(
                finite_element, dtype=np.complex128
            ).copy()
            payload[f"candidate_{index}_port_amplitudes"] = np.asarray(
                alpha, dtype=np.complex128
            ).copy()
            if evaluated is None:
                payload["candidate_facts"].append({"evaluation_available": False})
                continue
            candidate = evaluated["candidate"]
            complete = evaluated["complete"]
            budget = evaluated["budget"]
            facts = {
                "evaluation_available": True,
                "metrics": dict(candidate["metrics"]),
                "frozen_scale_metrics": dict(candidate["frozen_scale_metrics"]),
                "raw_facts": dict(candidate["raw_facts"]),
                "structural_gates": dict(candidate["structural_gates"]),
                "state_sha256": candidate["state_sha256"],
                "native_evaluation_seconds": candidate["native_evaluation_seconds"],
                "native_evaluation_ordinal": candidate["native_evaluation_ordinal"],
            }
            payload["candidate_facts"].append(facts)
            for field, key in (
                ("finite_element_residual", "complete_augmented_fe_residual"),
                ("port_residual", "complete_augmented_port_residual"),
                ("alpha_closure_residual", "alpha_closure_residual"),
            ):
                value = complete.get(field)
                if value is not None:
                    payload[f"candidate_{index}_{key}"] = np.asarray(
                        value, dtype=np.complex128
                    ).copy()
            for key in (
                "d_b",
                "d_A",
                "effective_rhs",
                "port_elimination_action",
                "sum_lifted_effective_rhs",
                "sum_lifted_native_actions",
                "global_native_action_independent",
                "modal_alpha_defect_action",
                "eliminated_fe_residual_direct",
                "eliminated_fe_residual_decomposed",
                "complete_fe_residual_decomposed",
            ):
                value = budget.get(key)
                if value is not None:
                    payload[f"candidate_{index}_{key}"] = np.asarray(
                        value, dtype=np.complex128
                    ).copy()
            for sector_index, value in enumerate(
                budget.get("lifted_sector_errors") or ()
            ):
                payload[f"candidate_{index}_lifted_sector_error_{sector_index}"] = (
                    np.asarray(value, dtype=np.complex128).copy()
                )
            for field, collection_key in (
                ("lifted_sector_effective_rhs", "lifted_sector_effective_rhs"),
                ("lifted_sector_native_action", "lifted_sector_native_actions"),
            ):
                for sector_index, value in enumerate(budget.get(collection_key) or ()):
                    payload[f"candidate_{index}_{field}_{sector_index}"] = np.asarray(
                        value, dtype=np.complex128
                    ).copy()
        return _save_packet(self.runtime, label, payload)

    def _record_v15_pc_failure(
        self,
        reason: str,
        fe_rhs: np.ndarray,
        port_rhs: np.ndarray,
        states: list[tuple[np.ndarray, np.ndarray, Mapping[str, Any] | None]],
        *,
        selection: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        packet = self._save_v15_pc_packet(
            f"v15_pc_failure_call{self.calls}",
            fe_rhs,
            port_rhs,
            states,
            status="REJECTED",
            failure=reason,
            selection=selection,
        )
        candidates = [
            evaluated["candidate"]
            for _, _, evaluated in states
            if evaluated is not None
        ]
        self.last_facts = {
            "call": int(self.calls),
            "reference_pc_strategy": "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15",
            "reference_pc_admission": "V15_REFERENCE_PC_REJECTED",
            "failure": reason,
            "candidate_metrics": candidates,
            "candidate_selection": dict(selection or {}),
            "failure_evidence_packet": packet,
            "native_evaluation_count_cumulative": int(
                self._v15_native_evaluation_count
            ),
            "per_pc_arrays_saved": False,
            "passed": False,
        }
        self.runtime.marker("v15_p6_reference_pc_apply_rejected", self.last_facts)
        return packet

    def _apply_v15(self, source: Any, source_values: np.ndarray):
        from src.solvers.augmented_reference_correction import (
            FACTOR_CALL_COUNTER_SOURCE,
            NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
            apply_one_augmented_residual_correction,
            select_v15_reference_pc_candidate,
        )

        self.calls += 1
        pc_call = self.calls
        self._v15_last_state_arrays = None
        self.allocation_gate(
            "task40_v15_pc_reference_rhs_injection",
            {
                "additional_payload_bytes": 16 * (
                    int(self.layout.full_rows)
                    + len(self.independent)
                    + 2 * int(self.profile.mode_count)
                ),
                "workspace_bytes": 0,
                "target_injection_is_full_storage": True,
                "same_actual_rhs_used_for_initial_and_one_correction": True,
            },
        )
        injected = self.target_action.inject_trace_port(source_values)
        fe_rhs = np.asarray(injected[self.independent], dtype=np.complex128)
        port_rhs = np.asarray(
            source_values[self.target_condensed.active_rows :], dtype=np.complex128
        ).copy()
        factor_calls_before = int(self.inverse.factors.calls)
        try:
            initial_fe, initial_alpha = self.inverse.apply_augmented(
                fe_rhs,
                port_rhs=port_rhs,
                rhs_category="pc_initial_rhs_mat_solve_count",
            )
        except Exception as exc:
            self._record_v15_pc_failure(
                f"initial_raw_inverse_failed:{type(exc).__name__}:{exc}",
                fe_rhs,
                port_rhs,
                [],
            )
            raise
        factor_calls_after = int(self.inverse.factors.calls)
        if factor_calls_after - factor_calls_before != self.profile.q_count:
            raise RuntimeError(
                "initial V15 PC raw inverse did not perform one MatSolve per q phase"
            )
        initial_q_rows = copy.deepcopy(
            [
                row
                for sector in self.inverse.last_solve_audit
                for row in sector["q_true_residuals"]
            ]
        )
        expected_qs = set(range(self.profile.q_count))
        try:
            initial_eval = self._evaluate_v15_state(
                initial_fe,
                initial_alpha,
                fe_rhs,
                port_rhs,
                initial_q_rows,
                label=f"initial_pc_{pc_call}",
            )
        except Exception as exc:
            self._record_v15_pc_failure(
                f"initial_native_evaluation_failed:{type(exc).__name__}:{exc}",
                fe_rhs,
                port_rhs,
                [(initial_fe, initial_alpha, None)],
            )
            raise
        candidate_states = [initial_eval["candidate"]]
        candidate_values = [(initial_fe, initial_alpha, initial_eval)]
        initial_selection = initial_eval["selection"]
        final_selection = initial_selection
        correction_audit = None
        correction_factor_calls = None
        correction_q_rows: list[dict[str, Any]] = []
        if not initial_selection["admitted"]:
            if not all(initial_eval["candidate"]["structural_gates"].values()):
                self._record_v15_pc_failure(
                    "initial_structural_gates_failed",
                    fe_rhs,
                    port_rhs,
                    [(initial_fe, initial_alpha, initial_eval)],
                    selection=initial_selection,
                )
                raise FloatingPointError(
                    "V15 PC structural gates failed; bounded correction is forbidden"
                )

            def raw_nonrecursive_inverse(fe_error, port_error):
                calls_before = int(self.inverse.factors.calls)
                delta_fe, delta_port = self.inverse.apply_augmented(
                    fe_error,
                    port_rhs=port_error,
                    rhs_category="pc_augmentation_rhs_mat_solve_count",
                )
                calls_after = int(self.inverse.factors.calls)
                rows = [
                    row
                    for sector in self.inverse.last_solve_audit
                    for row in sector["q_true_residuals"]
                ]
                return delta_fe, delta_port, {
                    "counter_source": FACTOR_CALL_COUNTER_SOURCE,
                    "factor_calls_before": calls_before,
                    "factor_calls_after": calls_after,
                    "q_true_residuals": copy.deepcopy(rows),
                }

            try:
                correction = apply_one_augmented_residual_correction(
                    initial_fe,
                    initial_alpha,
                    initial_eval["complete"]["finite_element_residual"],
                    initial_eval["complete"]["port_residual"],
                    raw_inverse=raw_nonrecursive_inverse,
                    allocation_gate=self.allocation_gate,
                    require_verified_solve_counter=True,
                    expected_q_count=self.profile.q_count,
                    factor_capabilities=_v19_factor_capabilities(self.inverse),
                )
            except Exception as exc:
                self._record_v15_pc_failure(
                    f"bounded_correction_failed:{type(exc).__name__}:{exc}",
                    fe_rhs,
                    port_rhs,
                    [(initial_fe, initial_alpha, initial_eval)],
                    selection=initial_selection,
                )
                raise
            correction_audit = dict(correction.audit)
            correction_q_rows = list(correction_audit.get("q_true_residuals", ()))
            correction_factor_calls = {
                "before": correction_audit.get("factor_calls_before"),
                "after": correction_audit.get("factor_calls_after"),
                "delta": correction_audit.get("extra_mat_solve_count"),
            }
            if correction_audit.get("attempted"):
                if correction_audit.get("extra_mat_solve_count") != self.profile.q_count:
                    raise RuntimeError(
                        "V15 PC correction MatSolve count differs from its registered q inventory"
                    )
                try:
                    correction_eval = self._evaluate_v15_state(
                        correction.finite_element,
                        correction.port_amplitudes,
                        fe_rhs,
                        port_rhs,
                        correction_q_rows,
                        label=f"corrected_pc_{pc_call}",
                        frozen_alpha_scale=float(
                            initial_eval["candidate"]["raw_facts"][
                                "alpha_closure_original_scale"
                            ]
                        ),
                        retained_candidate_state_count=1,
                    )
                except Exception as exc:
                    self._record_v15_pc_failure(
                        f"corrected_native_evaluation_failed:{type(exc).__name__}:{exc}",
                        fe_rhs,
                        port_rhs,
                        [
                            (initial_fe, initial_alpha, initial_eval),
                            (correction.finite_element, correction.port_amplitudes, None),
                        ],
                        selection=initial_selection,
                    )
                    raise
            else:
                correction_eval = self._evaluate_v15_state(
                    correction.finite_element,
                    correction.port_amplitudes,
                    fe_rhs,
                    port_rhs,
                    initial_q_rows,
                    label=f"zero_correction_pc_{pc_call}",
                    frozen_alpha_scale=float(
                        initial_eval["candidate"]["raw_facts"][
                            "alpha_closure_original_scale"
                        ]
                    ),
                    retained_candidate_state_count=1,
                )
            candidate_states.append(correction_eval["candidate"])
            candidate_values.append(
                (
                    correction.finite_element,
                    correction.port_amplitudes,
                    correction_eval,
                )
            )
            final_selection = select_v15_reference_pc_candidate(
                candidate_states, profile_identity=self.profile.name
            )
            if not final_selection["admitted"]:
                self._record_v15_pc_failure(
                    "initial_and_corrected_candidates_rejected",
                    fe_rhs,
                    port_rhs,
                    candidate_values,
                    selection=final_selection,
                )
                raise FloatingPointError(
                    "V15 PC initial and one corrected complete FE/alpha state failed: "
                    f"{final_selection}"
                )

        selected_index = int(final_selection["selected_candidate_index"])
        solution_values, alpha, selected_eval = candidate_values[selected_index]
        selected_candidate = candidate_states[selected_index]
        selected_metrics = dict(selected_candidate["metrics"])
        selected_raw = dict(selected_candidate["raw_facts"])
        selected_q_rows = list(selected_raw["q_true_residuals"])
        self.allocation_gate(
                "task40_v15_pc_selected_output",
            {
                "additional_payload_bytes": 16 * (
                    int(self.target_condensed.active_rows)
                    + 2 * int(self.profile.mode_count)
                ),
                "workspace_bytes": 0,
                "selected_complete_fe_alpha_state": True,
                    "last_call_state_evidence_retained": True,
                    "retained_candidate_state_count": len(candidate_values),
                    "retained_candidate_bytes": 16
                    * len(candidate_values)
                    * (
                        8 * int(len(self.independent))
                        + 2 * int(self.profile.mode_count)
                    ),
                    "evidence_state_index_matches_candidate_selection": list(
                        range(len(candidate_values))
                    ),
            },
        )
        output = source.duplicate()
        try:
            active = np.zeros(self.target_condensed.active_rows, dtype=np.complex128)
            constraints = self.target_condensed.trace_constraints
            for original in constraints.owned_active_original_dofs:
                row = int(original)
                active[constraints.original_to_active[row]] = solution_values[
                    self.reference_row[row]
                ]
            _assign_vector_storage(
                output, np.concatenate((active, np.asarray(alpha, dtype=np.complex128)))
            )
            q_relative = float(selected_metrics["q_solve"])
            q_coverage = (
                len(selected_q_rows) == self.profile.q_count
                and {int(row["q"]) for row in selected_q_rows} == expected_qs
            )
            packet = None
            if pc_call == 1:
                packet = self._save_v15_pc_packet(
                    "v15_pc_first_apply",
                    fe_rhs,
                    port_rhs,
                    candidate_values,
                    status="PASS",
                    selection=final_selection,
                )
                self._v15_first_packet = packet
            self._v15_last_state_arrays = {
                "candidate_values": candidate_values,
                "fe_rhs": fe_rhs,
                "port_rhs": port_rhs,
                "candidate_selection": final_selection,
            }
            self.last_facts = {
                "call": pc_call,
                "input_space": f"target_p6_active_trace_plus_{self.profile.mode_count}_ports",
                "reference_rhs_injected_by_target_JH": True,
                "target_active_rows": int(self.target_condensed.active_rows),
                "target_port_rows": int(self.target_condensed.appended_rows),
                "reference_pc_strategy": NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
                "profile_identity": self.profile.name,
                "reference_pc_admission": final_selection["admission"],
                "initial_candidate_passed": bool(initial_selection["admitted"]),
                "selected_candidate_index": selected_index,
                "selected_v15_metrics": selected_metrics,
                "selected_v15_raw_facts": selected_raw,
                "selected_state_sha256": selected_candidate["state_sha256"],
                "selected_decomposition_closure_relative": float(
                    selected_eval["budget"]["decomposition_closure_relative"]
                ),
                "port_identity_relative": float(selected_metrics["alpha_closure"]),
                "maximum_q_true_residual_relative": q_relative,
                "q_true_residual_limit": self.inverse.q_solve_limit,
                "q_true_residuals_initial": initial_q_rows,
                "q_true_residuals_correction": correction_q_rows,
                "q_true_residuals_selected": selected_q_rows,
                "all_q_used": q_coverage,
                "all_four_q_used": self.profile.q_count == 4 and q_coverage,
                "initial_factor_calls": {
                    "before": factor_calls_before,
                    "after": factor_calls_after,
                    "delta": factor_calls_after - factor_calls_before,
                },
                "correction_factor_calls": correction_factor_calls,
                "candidate_metrics": candidate_states,
                "candidate_selection": final_selection,
                "correction_audit": correction_audit,
                "native_evaluation_count_this_call": len(candidate_states),
                "native_evaluation_count_cumulative": int(
                    self._v15_native_evaluation_count
                ),
                "native_evaluation_seconds": [
                    float(candidate["native_evaluation_seconds"])
                    for candidate in candidate_states
                ],
                "first_call_evidence_packet": packet,
                "per_pc_arrays_saved": False,
            }
            self.runtime.marker("v15_p6_reference_pc_apply_complete", self.last_facts)
            self.runtime.sample(f"v15_p6_reference_pc_{self.calls}_after")
            return output
        except BaseException:
            output.destroy()
            raise

    def _apply_v13(self, source: Any, source_values: np.ndarray):
        from src.solvers.augmented_reference_correction import (
            BOUNDED_INEXACT_LIMITS,
            BOUNDED_INEXACT_REFERENCE_PC,
            FACTOR_CALL_COUNTER_SOURCE,
            STRICT_REFERENCE_LIMITS,
            STRICT_REFERENCE_PASS,
            apply_one_augmented_residual_correction,
            select_reference_pc_candidate,
        )

        self.allocation_gate(
            "task40_v13_pc_reference_rhs_injection",
            {
                "additional_payload_bytes": 16 * (
                    int(self.layout.full_rows) + len(self.independent)
                    + 2 * int(self.profile.mode_count)
                ),
                "workspace_bytes": 0,
                "target_injection_is_full_storage": True,
            },
        )
        injected = self.target_action.inject_trace_port(source_values)
        fe_rhs = np.asarray(injected[self.independent], dtype=np.complex128)
        port_rhs = np.asarray(
            source_values[self.target_condensed.active_rows :], dtype=np.complex128
        ).copy()
        factor_calls_before = int(self.inverse.factors.calls)
        initial_fe, initial_alpha = self.inverse.apply_augmented(
            fe_rhs,
            port_rhs=port_rhs,
            rhs_category="pc_initial_rhs_mat_solve_count",
        )
        factor_calls_after = int(self.inverse.factors.calls)
        if factor_calls_after - factor_calls_before != self.profile.q_count:
            raise RuntimeError(
                "initial V13 PC raw inverse did not perform exactly one MatSolve per q phase"
            )
        initial_q_rows = copy.deepcopy(
            [
                row
                for sector in self.inverse.last_solve_audit
                for row in sector["q_true_residuals"]
            ]
        )
        expected_qs = set(range(self.profile.q_count))
        initial_q_coverage = (
            len(initial_q_rows) == self.profile.q_count
            and {int(row["q"]) for row in initial_q_rows} == expected_qs
        )
        initial_q_relative = max(
            (float(row["true_residual_relative"]) for row in initial_q_rows),
            default=float("inf"),
        )
        initial_eval = self._evaluate_complete_augmented_state(
            initial_fe, initial_alpha, fe_rhs, port_rhs,
            label=f"initial_pc_{self.calls + 1}",
        )
        strict_limits = {
            name: float(STRICT_REFERENCE_LIMITS[name])
            for name in ("complete_augmented_fe_equation", "alpha_closure", "q_solve")
        }
        bounded_limits = {
            name: float(BOUNDED_INEXACT_LIMITS[name])
            for name in ("complete_augmented_fe_equation", "alpha_closure", "q_solve")
        }
        initial_metrics = {
            "complete_augmented_fe_equation": float(
                initial_eval["complete_augmented_fe_equation_relative"]
            ),
            "alpha_closure": float(initial_eval["alpha_closure_relative"]),
            "q_solve": initial_q_relative,
        }
        initial_candidate = {
            "metrics": initial_metrics,
            "frozen_scale_metrics": dict(initial_metrics),
            "structural_gates": {
                "all_q_phases_covered": initial_q_coverage,
                "native_augmented_action_finite": True,
            },
            "state_label": "initial",
        }
        initial_selection = select_reference_pc_candidate(
            [initial_candidate],
            strict_limits=strict_limits,
            bounded_inexact_limits=bounded_limits,
        )
        candidate_states = [initial_candidate]
        candidate_values = [(initial_fe, initial_alpha, initial_eval, initial_q_rows)]
        correction_audit = None
        correction_q_rows: list[dict[str, Any]] = []
        correction_factor_calls = None
        selected_index = 0
        final_selection = initial_selection
        if initial_selection["admission"] != STRICT_REFERENCE_PASS:
            if not all(initial_candidate["structural_gates"].values()):
                raise FloatingPointError(
                    "V13 PC reference structural q coverage failed; bounded admission is forbidden"
                )
            initial_q_scales = {
                int(row["q"]): max(float(row["rhs_norm"]), np.finfo(float).tiny)
                for row in initial_q_rows
            }
            frozen_scales = {
                "complete_augmented_fe_equation": max(
                    float(initial_eval["original_fe_equation_scale"]),
                    np.finfo(float).tiny,
                ),
                "alpha_closure": float(initial_eval["alpha_closure_scale"]),
                "q_rhs_by_phase": initial_q_scales,
            }

            def raw_nonrecursive_inverse(fe_error, port_error):
                calls_before = int(self.inverse.factors.calls)
                delta_fe, delta_port = self.inverse.apply_augmented(
                    fe_error,
                    port_rhs=port_error,
                    rhs_category="pc_augmentation_rhs_mat_solve_count",
                )
                calls_after = int(self.inverse.factors.calls)
                q_rows = [
                    row
                    for sector in self.inverse.last_solve_audit
                    for row in sector["q_true_residuals"]
                ]
                return delta_fe, delta_port, {
                    "counter_source": FACTOR_CALL_COUNTER_SOURCE,
                    "factor_calls_before": calls_before,
                    "factor_calls_after": calls_after,
                    "q_true_residuals": copy.deepcopy(q_rows),
                }

            correction = apply_one_augmented_residual_correction(
                initial_fe,
                initial_alpha,
                initial_eval["finite_element_residual"],
                initial_eval["port_residual"],
                raw_inverse=raw_nonrecursive_inverse,
                allocation_gate=self.allocation_gate,
                require_verified_solve_counter=True,
                factor_capabilities=_v19_factor_capabilities(self.inverse),
            )
            correction_audit = dict(correction.audit)
            correction_q_rows = list(correction_audit["q_true_residuals"])
            correction_factor_calls = {
                "before": correction_audit["factor_calls_before"],
                "after": correction_audit["factor_calls_after"],
            }
            correction_eval = self._evaluate_complete_augmented_state(
                correction.finite_element,
                correction.port_amplitudes,
                fe_rhs,
                port_rhs,
                label=f"corrected_pc_{self.calls + 1}",
            )
            correction_q_coverage = (
                len(correction_q_rows) == self.profile.q_count
                and {int(row["q"]) for row in correction_q_rows} == expected_qs
            )
            correction_q_relative = max(
                (float(row["true_residual_relative"]) for row in correction_q_rows),
                default=float("inf"),
            )
            correction_q_frozen = []
            for row in correction_q_rows:
                q = int(row["q"])
                current_rhs_scale = max(float(row["rhs_norm"]), np.finfo(float).tiny)
                frozen_rhs_scale = initial_q_scales.get(q)
                correction_q_frozen.append(
                    float(row["true_residual_relative"])
                    * current_rhs_scale
                    / frozen_rhs_scale
                    if frozen_rhs_scale is not None and frozen_rhs_scale > 0.0
                    else float("inf")
                )
            corrected_candidate = {
                "metrics": {
                    "complete_augmented_fe_equation": float(
                        correction_eval["complete_augmented_fe_equation_relative"]
                    ),
                    "alpha_closure": float(correction_eval["alpha_closure_relative"]),
                    "q_solve": correction_q_relative,
                },
                "frozen_scale_metrics": {
                    "complete_augmented_fe_equation": float(
                        correction_eval["finite_element_residual_norm"]
                        / frozen_scales["complete_augmented_fe_equation"]
                    ),
                    "alpha_closure": float(
                        correction_eval["alpha_closure_residual_norm"]
                        / frozen_scales["alpha_closure"]
                    ),
                    "q_solve": max(correction_q_frozen, default=float("inf")),
                },
                "structural_gates": {
                    "all_q_phases_covered": correction_q_coverage,
                    "native_augmented_action_finite": True,
                },
                "state_label": "corrected_v13",
            }
            candidate_states.append(corrected_candidate)
            candidate_values.append(
                (
                    correction.finite_element,
                    correction.port_amplitudes,
                    correction_eval,
                    correction_q_rows,
                )
            )
            final_selection = select_reference_pc_candidate(
                candidate_states,
                strict_limits=strict_limits,
                bounded_inexact_limits=bounded_limits,
            )
            selected_index = int(final_selection["selected_candidate_index"])
            if not final_selection["admitted"]:
                raise FloatingPointError(
                    "V13 PC full augmented reference residual/alpha/q gates failed: "
                    f"{final_selection}"
                )

        solution_values, alpha, selected_eval, selected_q_rows = candidate_values[selected_index]
        q_relative = max(
            (float(row["true_residual_relative"]) for row in selected_q_rows),
            default=float("inf"),
        )
        q_coverage = (
            len(selected_q_rows) == self.profile.q_count
            and {int(row["q"]) for row in selected_q_rows} == expected_qs
        )
        self.allocation_gate(
            "task40_v13_pc_selected_output",
            {
                "additional_payload_bytes": 16 * (
                    int(self.target_condensed.active_rows)
                    + 2 * int(self.profile.mode_count)
                ),
                "workspace_bytes": 0,
                "selected_complete_fe_alpha_state": True,
            },
        )
        output = source.duplicate()
        try:
            active = np.zeros(self.target_condensed.active_rows, dtype=np.complex128)
            constraints = self.target_condensed.trace_constraints
            for original in constraints.owned_active_original_dofs:
                row = int(original)
                active[constraints.original_to_active[row]] = solution_values[
                    self.reference_row[row]
                ]
            retained_output = np.concatenate((active, alpha))
            _assign_vector_storage(output, retained_output)
            self.calls += 1
            self.last_facts = {
                "call": self.calls,
                "input_space": f"target_p6_active_trace_plus_{self.profile.mode_count}_ports",
                "reference_rhs_injected_by_target_JH": True,
                "target_active_rows": int(self.target_condensed.active_rows),
                "target_port_rows": int(self.target_condensed.appended_rows),
                "reference_pc_strategy": "STRICT_THEN_BOUNDED_INEXACT_V13",
                "reference_pc_admission": final_selection["admission"],
                "strict_initial_candidate_passed": bool(
                    initial_selection["admission"] == STRICT_REFERENCE_PASS
                ),
                "selected_candidate_index": selected_index,
                "selected_complete_augmented_fe_equation_relative": float(
                    selected_eval["complete_augmented_fe_equation_relative"]
                ),
                "selected_complete_augmented_stacked_relative_diagnostic": float(
                    selected_eval["complete_augmented_stacked_relative_diagnostic"]
                ),
                "selected_original_fe_equation_scale": float(
                    selected_eval["original_fe_equation_scale"]
                ),
                "selected_complete_augmented_residual_norm": float(
                    selected_eval["augmented_residual_norm"]
                ),
                "selected_complete_augmented_rhs_norm": float(
                    selected_eval["augmented_rhs_norm"]
                ),
                "selected_alpha_closure_relative": float(
                    selected_eval["alpha_closure_relative"]
                ),
                "port_identity_relative": float(selected_eval["alpha_closure_relative"]),
                "maximum_q_true_residual_relative": q_relative,
                "q_true_residual_limit": self.inverse.q_solve_limit,
                "q_strict_passed": bool(q_relative <= _REFERENCE_RESIDUAL_LIMIT),
                "q_true_residuals_initial": initial_q_rows,
                "q_true_residuals_correction": correction_q_rows,
                "q_true_residuals_selected": selected_q_rows,
                "all_q_used": q_coverage,
                "all_four_q_used": self.profile.q_count == 4 and q_coverage,
                "initial_factor_calls": {
                    "before": factor_calls_before,
                    "after": factor_calls_after,
                    "delta": factor_calls_after - factor_calls_before,
                },
                "correction_factor_calls": correction_factor_calls,
                "initial_metrics": initial_metrics,
                "candidate_metrics": [
                    {
                        "state_label": candidate.get("state_label"),
                        "metrics": candidate["metrics"],
                        "frozen_scale_metrics": candidate["frozen_scale_metrics"],
                        "structural_gates": candidate["structural_gates"],
                    }
                    for candidate in candidate_states
                ],
                "candidate_selection": final_selection,
                "correction_audit": correction_audit,
            }
            self.runtime.marker("v13_p6_reference_pc_apply_complete", self.last_facts)
            self.runtime.sample(f"v13_p6_reference_pc_{self.calls}_after")
            return output
        except BaseException:
            output.destroy()
            raise

    def apply(self, source: Any):
        import time

        whole_pc_started_ns = time.perf_counter_ns()
        self.runtime.sample(f"v10_p6_reference_pc_{self.calls + 1}_before")
        source_values = np.asarray(source.array_r, dtype=np.complex128)
        if source_values.shape != (self.target_action.reduced_size,):
            raise ValueError("Task40 V10 p6 preconditioner input has the wrong retained layout")
        if self.inverse.reference_pc_strategy == "STRICT_THEN_BOUNDED_INEXACT_V13":
            return self._apply_v13(source, source_values)
        if self.inverse.reference_pc_strategy == "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15":
            try:
                output = self._apply_v15(source, source_values)
            except BaseException as exc:
                finished_ns = time.perf_counter_ns()
                self.runtime.marker(
                    "v15_p6_reference_pc_apply_parent_failed",
                    {
                        "call": int(self.calls),
                        "monotonic_start_ns": int(whole_pc_started_ns),
                        "monotonic_end_ns": int(finished_ns),
                        "whole_pc_apply_seconds": float(
                            (finished_ns - whole_pc_started_ns) / 1.0e9
                        ),
                        "failure": {"type": type(exc).__name__, "message": str(exc)},
                    },
                )
                raise
            finished_ns = time.perf_counter_ns()
            elapsed = float((finished_ns - whole_pc_started_ns) / 1.0e9)
            native_children = list(self.last_facts.get("native_evaluation_seconds", ()))
            self.last_facts["whole_pc_apply_seconds"] = elapsed
            self.last_facts["whole_pc_apply_monotonic_interval_ns"] = [
                int(whole_pc_started_ns), int(finished_ns)
            ]
            self.last_facts["whole_pc_timing_scope"] = (
                "parent includes raw q solves, native complete-state evaluation, optional one "
                "augmentation, output conversion, evidence write, and resource sample"
            )
            self.last_facts["native_evaluation_seconds_are_children_not_additive"] = True
            self.runtime.marker(
                "v15_p6_reference_pc_apply_parent_complete",
                {
                    "call": int(self.calls),
                    "monotonic_start_ns": int(whole_pc_started_ns),
                    "monotonic_end_ns": int(finished_ns),
                    "whole_pc_apply_seconds": elapsed,
                    "native_evaluation_seconds": native_children,
                    "native_evaluation_seconds_are_children_not_additive": True,
                    "timing_scope": self.last_facts["whole_pc_timing_scope"],
                },
            )
            return output
        injected = self.target_action.inject_trace_port(source_values)
        port_rhs = source_values[self.target_condensed.active_rows :].copy()
        solution_values, alpha = self.inverse.apply_augmented(
            injected[self.independent],
            port_rhs=port_rhs,
            rhs_category="pc_initial_rhs_mat_solve_count",
        )
        reference_solution = self.PETSc.Vec().createSeq(
            self.layout.full_rows, comm=self.PETSc.COMM_SELF
        )
        output = source.duplicate()
        try:
            reference_solution.set(0.0)
            _assign_vector_storage(reference_solution, solution_values, rows=self.independent)
            recovered = self.reference["dtn_action"].recover_auxiliary(reference_solution)
            scale = max(
                float(np.linalg.norm(alpha))
                + float(np.linalg.norm(recovered))
                + float(np.linalg.norm(port_rhs / self.h)),
                np.finfo(float).tiny,
            )
            port_relative = float(
                np.linalg.norm(alpha - recovered - port_rhs / self.h)
            ) / scale
            active = np.zeros(self.target_condensed.active_rows, dtype=np.complex128)
            constraints = self.target_condensed.trace_constraints
            for original in constraints.owned_active_original_dofs:
                row = int(original)
                active[constraints.original_to_active[row]] = solution_values[
                    self.reference_row[row]
                ]
            retained_output = np.concatenate((active, alpha))
            _assign_vector_storage(output, retained_output)
            solve_audit = self.inverse.last_solve_audit
            q_rows = [row for sector in solve_audit for row in sector["q_true_residuals"]]
            q_relative = max(
                (float(row["true_residual_relative"]) for row in q_rows),
                default=float("inf"),
            )
            if (
                len(q_rows) != self.profile.q_count
                or {int(row["q"]) for row in q_rows} != set(range(self.profile.q_count))
                or not np.isfinite(q_relative)
                or q_relative > self.inverse.q_solve_limit
                or not np.isfinite(port_relative)
                or port_relative > _IDENTITY_LIMIT
            ):
                raise FloatingPointError(
                    "Task40 V10 p6 inverse apply failed q or port identity gate: "
                    f"q={q_relative} (limit={self.inverse.q_solve_limit}), "
                    f"port={port_relative}"
                )
            self.calls += 1
            self.last_facts = {
                "call": self.calls,
                "input_space": f"target_p6_active_trace_plus_{self.profile.mode_count}_ports",
                "reference_rhs_injected_by_target_JH": True,
                "target_active_rows": int(self.target_condensed.active_rows),
                "target_port_rows": int(self.target_condensed.appended_rows),
                "maximum_q_true_residual_relative": q_relative,
                "q_true_residual_limit": self.inverse.q_solve_limit,
                "q_strict_passed": bool(q_relative <= _REFERENCE_RESIDUAL_LIMIT),
                "port_identity_relative": port_relative,
                "q_true_residuals": q_rows,
                "all_q_used": True,
                "all_four_q_used": self.profile.q_count == 4,
            }
            self.runtime.marker("v10_p6_reference_pc_apply_complete", self.last_facts)
            self.runtime.sample(f"v10_p6_reference_pc_{self.calls}_after")
            return output
        except BaseException:
            output.destroy()
            raise
        finally:
            reference_solution.destroy()

    def detach(self) -> dict[str, Any]:
        last_packet = None
        if self.inverse is not None and self.inverse.reference_pc_strategy == (
            "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
        ):
            if self.last_facts.get("reference_pc_admission") == "V15_REFERENCE_PC_REJECTED":
                last_packet = self.last_facts.get("failure_evidence_packet")
            elif self._v15_last_state_arrays is not None:
                if self.calls == 1 and self._v15_first_packet is not None:
                    last_packet = {
                        **self._v15_first_packet,
                        "reused_first_call_evidence": True,
                    }
                else:
                    last = self._v15_last_state_arrays
                    last_packet = self._save_v15_pc_packet(
                        "v15_pc_last_apply",
                        last["fe_rhs"],
                        last["port_rhs"],
                        last["candidate_values"],
                        status="PASS",
                        selection=last["candidate_selection"],
                    )
                self.last_facts["last_call_evidence_packet"] = last_packet
        facts = {
            "calls": int(self.calls),
            "v15_native_evaluation_count": int(self._v15_native_evaluation_count),
            "first_call_evidence_packet": self._v15_first_packet,
            "last_call_evidence_packet": last_packet,
            "last_facts": dict(self.last_facts),
        }
        self.target_action = None
        self.target_condensed = None
        self.reference = None
        self.layout = None
        self.inverse = None
        self.owner = None
        self._v15_last_state_arrays = None
        return facts


def _candidate_contract(
    resolved: Mapping[str, Any],
    contract: Mapping[str, Any],
    runtime: Any,
    *,
    profile_identity: str,
    v30_contract: Mapping[str, Any] | None = None,
    v31_contract: Mapping[str, Any] | None = None,
    v30_effective_factor_lifecycle_strategy: str | None = None,
    v31_effective_factor_lifecycle_strategy: str | None = None,
) -> dict[str, Any]:
    from src.geometry.task40_nonseparable_plan import (
        TASK40_B0_P6_CANDIDATE_RUN_ID,
        TASK40_B0_P6_V13_RUN_ID,
        TASK40_B0_P6_V15_RUN_ID,
        TASK40_COMPARISON_GROUP,
        TASK40_E1_V15_RUN_ID,
        TASK40_GX560_V11_P6_RUN_ID,
        TASK40_GX560_V15_RUN_ID,
        TASK40_E1_V16_RUN_ID,
        TASK40_GX560_V16_RUN_ID,
        TASK40_B0_P6_V17_RUN_ID,
        TASK40_GX560_V17_RUN_ID,
        TASK40_E1_V17_RUN_ID,
        TASK40_B0_P6_V18_Y8_RUN_ID,
        TASK40_E1_V19_RUN_ID,
        TASK40_B0_P6_V19_Y8_RUN_ID,
        TASK40_Q_ASSEMBLY_BOUNDED_V16,
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
        TASK40_GX784_V11_P6_RUN_ID,
        TASK40_GX560_V13_RUN_ID,
        TASK40_GX784_V13_RUN_ID,
        TASK40_V13_REFERENCE_PC_STRATEGY,
        TASK40_V15_REFERENCE_PC_STRATEGY,
        TASK40_STRICT_REFERENCE_PC_STRATEGY,
        TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
        task40_q_assembly_strategy_is_allowed,
    )
    from src.io.physical_intermediate_profile import (
        TASK40_V10_P6_REFERENCE_PROFILE,
        TASK40_V11_P6_GX560_PROFILE,
        TASK40_V11_P6_GX784_PROFILE,
        TASK40_V15_P6_B0_PROFILE,
        TASK40_V15_P6_GX560_PROFILE,
        TASK40_V15_P6_E1_PROFILE,
        TASK40_V16_P6_GX560_PROFILE,
        TASK40_V16_P6_E1_PROFILE,
        TASK40_V17_P6_B0_PROFILE,
        TASK40_V18_P6_B0_Y8_PROFILE,
        TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
        TASK40_V20_V22_P6_PROFILES,
        TASK40_V17_P6_GX560_PROFILE,
        TASK40_V17_P6_E1_PROFILE,
    )
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE
    from src.runners.task40_v10_campaign import CAMPAIGN_SECONDS, CLOSEOUT_RESERVE_SECONDS

    solver = resolved.get("solver", {})
    execution = resolved.get("execution", {})
    method = resolved.get("method", {})
    campaign = getattr(runtime, "campaign_context", None)
    shared = getattr(runtime, "shared_budget", {})
    reserved = float(getattr(runtime, "workflow_reserved_seconds", -1.0))
    campaign_seconds = float(
        campaign.get(
            "campaign_seconds",
            shared.get("total_budget_seconds", CAMPAIGN_SECONDS),
        )
        if isinstance(campaign, Mapping)
        else CAMPAIGN_SECONDS
    )
    closeout_reserve_seconds = float(
        campaign.get("closeout_reserve_seconds", CLOSEOUT_RESERVE_SECONDS)
        if isinstance(campaign, Mapping)
        else CLOSEOUT_RESERVE_SECONDS
    )
    reference_pc_strategy = str(
        solver.get("task40_reference_pc_strategy", TASK40_STRICT_REFERENCE_PC_STRATEGY)
    )
    q_assembly_strategy = str(
        solver.get("task40_q_assembly_strategy", "LEGACY_GLOBAL_CSR_SUM")
    )
    factor_lifecycle_strategy = str(
        solver.get(
            "task40_factor_lifecycle_strategy", TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
        )
    )
    is_v13 = reference_pc_strategy == TASK40_V13_REFERENCE_PC_STRATEGY
    is_v15 = reference_pc_strategy == TASK40_V15_REFERENCE_PC_STRATEGY
    is_v19 = factor_lifecycle_strategy == TASK40_V19_FACTOR_LIFECYCLE_STRATEGY
    is_v18 = profile_identity == TASK40_V18_P6_B0_Y8_PROFILE
    is_v20 = profile_identity in TASK40_V20_V22_P6_PROFILES
    is_v16 = q_assembly_strategy == TASK40_Q_ASSEMBLY_BOUNDED_V16
    is_v17 = q_assembly_strategy == TASK40_Q_ASSEMBLY_ROW_TILE_V17
    case_identity = {
        TASK40_V10_P6_REFERENCE_PROFILE: (
            (TASK40_B0_P6_CANDIDATE_RUN_ID, "B0_CANDIDATE", 16.0),
            (TASK40_B0_P6_V13_RUN_ID, "B0_CANDIDATE", 16.0),
            None,
            None,
        ),
        TASK40_V11_P6_GX560_PROFILE: (
            (TASK40_GX560_V11_P6_RUN_ID, "Q4_ORIGINAL", 16.0),
            (TASK40_GX560_V13_RUN_ID, "Q4_ORIGINAL", 16.0),
            None,
            None,
        ),
        TASK40_V11_P6_GX784_PROFILE: (
            (TASK40_GX784_V11_P6_RUN_ID, "Q4_ORIGINAL", 16.0),
            (TASK40_GX784_V13_RUN_ID, "Q4_ORIGINAL", 16.0),
            None,
            None,
        ),
        TASK40_V15_P6_B0_PROFILE: (
            None, None, (TASK40_B0_P6_V15_RUN_ID, "B0_CANDIDATE", 16.0), None,
        ),
        TASK40_V15_P6_GX560_PROFILE: (
            None, None, (TASK40_GX560_V15_RUN_ID, "Q4_ORIGINAL", 16.0), None,
        ),
        TASK40_V15_P6_E1_PROFILE: (
            None, None, (TASK40_E1_V15_RUN_ID, "Q4_ORIGINAL", 16.0), None,
        ),
        TASK40_V16_P6_GX560_PROFILE: (
            None, None, None, (TASK40_GX560_V16_RUN_ID, "Q4_ORIGINAL", 16.0),
        ),
        TASK40_V16_P6_E1_PROFILE: (
            None, None, None, (TASK40_E1_V16_RUN_ID, "Q4_ORIGINAL", 16.0),
        ),
        TASK40_V17_P6_B0_PROFILE: (None, None, None, None),
        TASK40_V17_P6_GX560_PROFILE: (None, None, None, None),
        TASK40_V17_P6_E1_PROFILE: (None, None, None, None),
        TASK40_V18_P6_B0_Y8_PROFILE: (None, None, None, None),
        **{profile: (None, None, None, None) for profile in TASK40_V20_V22_P6_PROFILES},
    }
    try:
        strict_identity, v13_identity, v15_identity, v16_identity = case_identity[profile_identity]
    except KeyError as exc:
        raise ValueError(f"unsupported Task40 p6 reference profile: {profile_identity}") from exc
    v17_identity = {
        TASK40_V17_P6_B0_PROFILE: (
            TASK40_B0_P6_V17_RUN_ID, "B0_CANDIDATE", 16.0
        ),
        TASK40_V17_P6_GX560_PROFILE: (
            TASK40_GX560_V17_RUN_ID, "Q4_ORIGINAL", 16.0
        ),
        TASK40_V17_P6_E1_PROFILE: (
            TASK40_E1_V17_RUN_ID, "Q4_ORIGINAL", 16.0
        ),
    }.get(profile_identity)
    v18_identity = (
        (TASK40_B0_P6_V18_Y8_RUN_ID, "B0_CANDIDATE", 16.0)
        if profile_identity == TASK40_V18_P6_B0_Y8_PROFILE
        else None
    )
    v20_case = None
    if is_v20:
        from src.solvers.task40_v20_registry import task40_v20_case

        v20_case = task40_v20_case(profile=profile_identity)
    v30_route_requested = (
        v30_contract is not None
        or v30_effective_factor_lifecycle_strategy is not None
    )
    v31_route_requested = (
        v31_contract is not None
        or v31_effective_factor_lifecycle_strategy is not None
    )
    if v30_route_requested and v31_route_requested:
        raise ValueError("candidate worker cannot mix V30 and V31 execution contracts")
    v30_route_passed = not v30_route_requested
    v30_identity = None
    if v30_route_requested:
        if v30_contract is None or v30_effective_factor_lifecycle_strategy is None:
            raise ValueError("V30 candidate contract requires both validated bindings")
        from src.runners.task40_v30_contract import require_authorized_contract

        authorized_contract, _ = require_authorized_contract(
            os.environ.get("TASK40_V30_CONTRACT_PATH", ""),
            expected_sha256=os.environ.get("TASK40_V30_CONTRACT_SHA256"),
            current_root=Path(__file__).resolve().parents[2],
        )
        if authorized_contract != v30_contract:
            raise ValueError("V30 candidate contract differs from the validated worker binding")
        v30_execution = authorized_contract["execution"]
        v30_window = v30_execution["window"]
        v30_window_path = Path(v30_execution["campaign_window_path"])
        if not v30_window_path.is_absolute():
            v30_window_path = Path(v30_execution["execution_root"]) / v30_window_path
        v30_route_passed = bool(
            profile_identity == TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
            and is_v20
            and v20_case is not None
            and v20_case.mesh_id == "TARGET_ORIGINAL_NY8"
            and is_v15
            and is_v17
            and factor_lifecycle_strategy == TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
            and v30_effective_factor_lifecycle_strategy
            == TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
            and isinstance(campaign, Mapping)
            and isinstance(shared, Mapping)
            and Path(str(campaign.get("window_path", ""))).resolve()
            == v30_window_path.resolve()
            and v30_execution["campaign_window_sha256"]
            == campaign.get("window_sha256")
            == shared.get("campaign_window_sha256")
            and v30_window["total_seconds"] == campaign_seconds
            and v30_window["closeout_reserve_seconds"]
            == closeout_reserve_seconds
        )
        if not v30_route_passed:
            raise ValueError(
                "V30 candidate contract requires the authorized target Ny8 V15/V17 AllQ route"
            )
        assert v20_case is not None
        v30_identity = (v20_case.run_id, v20_case.solver_stage, 16.0)
    v31_route_passed = not v31_route_requested
    v31_identity = None
    if v31_route_requested:
        if v31_effective_factor_lifecycle_strategy is None:
            raise ValueError("V31 candidate contract requires its dispatcher AllQ binding")
        from src.runners.task40_v31_contract import require_v31_execution_contract

        authorized_contract, _ = require_v31_execution_contract(
            os.environ.get("TASK40_V31_CONTRACT_PATH", ""),
            expected_sha256=os.environ.get("TASK40_V31_CONTRACT_SHA256"),
            current_root=Path(__file__).resolve().parents[2],
        )
        if authorized_contract != v31_contract:
            raise ValueError("V31 candidate contract differs from the validated worker binding")
        v31_execution = authorized_contract["execution"]
        v31_window = v31_execution["window"]
        v31_route_passed = bool(
            profile_identity == TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
            and is_v20
            and v20_case is not None
            and v20_case.mesh_id == "TARGET_ORIGINAL_NY8"
            and is_v15
            and is_v17
            and factor_lifecycle_strategy == TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
            and v31_effective_factor_lifecycle_strategy
            == TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
            and isinstance(campaign, Mapping)
            and isinstance(shared, Mapping)
            and Path(str(campaign.get("window_path", ""))).resolve()
            == Path(str(v31_window.get("window_path", ""))).resolve()
            and v31_window.get("window_sha256")
            == campaign.get("window_sha256")
            == shared.get("campaign_window_sha256")
            and v31_window.get("total_seconds") == campaign_seconds
            and v31_window.get("closeout_reserve_seconds")
            == closeout_reserve_seconds
        )
        if not v31_route_passed:
            raise ValueError(
                "V31 candidate contract requires the authorized target Ny8 V15/V17 AllQ route"
            )
        assert v20_case is not None
        v31_identity = (v20_case.run_id, v20_case.solver_stage, 16.0)
    v19_identity = (
        (v20_case.run_id, v20_case.solver_stage, 16.0)
        if v20_case is not None
        else (TASK40_E1_V19_RUN_ID, "Q4_ORIGINAL", 16.0)
        if profile_identity == TASK40_V17_P6_E1_PROFILE
        else (TASK40_B0_P6_V19_Y8_RUN_ID, "B0_CANDIDATE", 16.0)
        if profile_identity == TASK40_V18_P6_B0_Y8_PROFILE
        else None
    )
    expected_identity = (
        v31_identity
        if v31_route_requested
        else v30_identity
        if v30_route_requested
        else v19_identity
        if is_v19
        else v18_identity
        if v18_identity is not None
        else v17_identity
        if is_v17
        else v16_identity
        if is_v16
        else v15_identity
        if is_v15
        else v13_identity
        if is_v13
        else strict_identity
    )
    if expected_identity is None:
        raise ValueError(
            f"Task40 profile {profile_identity} does not support {reference_pc_strategy}/{q_assembly_strategy}"
        )
    expected_run_id, expected_stage, expected_memory_limit = expected_identity
    input_timeout = execution.get("timeout_seconds")
    timeout_passed = input_timeout == CAMPAIGN_SECONDS
    is_v10 = profile_identity == TASK40_V10_P6_REFERENCE_PROFILE
    checks = {
        "run_id": resolved.get("run_id") == expected_run_id,
        "reference_pc_strategy": reference_pc_strategy
        == (
            TASK40_V15_REFERENCE_PC_STRATEGY
            if is_v15 or is_v18 or is_v19
            else
            TASK40_V13_REFERENCE_PC_STRATEGY
            if is_v13
            else TASK40_STRICT_REFERENCE_PC_STRATEGY
        ),
        "q_assembly_strategy": task40_q_assembly_strategy_is_allowed(
            reference_pc_strategy, q_assembly_strategy
        ),
        "factor_lifecycle_strategy": (
            factor_lifecycle_strategy == TASK40_V19_FACTOR_LIFECYCLE_STRATEGY
            if is_v19
            else factor_lifecycle_strategy == TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
        ),
        "v19_exact_scope": (
            not is_v19
            or (
                (
                    profile_identity in {
                        TASK40_V17_P6_E1_PROFILE,
                        TASK40_V18_P6_B0_Y8_PROFILE,
                    }
                    or is_v20
                )
                and q_assembly_strategy == TASK40_Q_ASSEMBLY_ROW_TILE_V17
                and reference_pc_strategy == TASK40_V15_REFERENCE_PC_STRATEGY
            )
        ),
        "comparison_group": resolved.get("comparison_group") == TASK40_COMPARISON_GROUP,
        "profile": solver.get("preconditioner") == profile_identity,
        "stage": solver.get("stage") == expected_stage and runtime.stage == expected_stage,
        "method": method.get("kind") == "full3d_iterative",
        "mpi_size": execution.get("mpi_size") == 1,
        "input_timeout_is_case_bound_but_not_window_authority": timeout_passed,
        "zero_swap": execution.get("require_zero_swap") is True and runtime.require_zero_swap,
        "memory_limit": execution.get("memory_limit_gb") == expected_memory_limit,
        "restart": solver.get("restart") == 32,
        "max_iterations": solver.get("max_iterations") == 2048,
        "ksp": solver.get("ksp_type") == "fgmres",
        "campaign_projection": isinstance(campaign, Mapping) and campaign.get("read_only") is True,
        "campaign_hash": (
            isinstance(campaign, Mapping)
            and isinstance(shared, Mapping)
            and campaign.get("window_sha256") == shared.get("campaign_window_sha256")
            and len(str(campaign.get("window_sha256", ""))) == 64
        ),
        "no_v14_ledger": getattr(runtime, "_ledger_path", None) is None,
        "time_policy": getattr(runtime, "time_policy", None) == V14_TIME_POLICY_ENFORCE,
        "campaign_window_budget": (
            np.isfinite(campaign_seconds)
            and np.isfinite(closeout_reserve_seconds)
            and campaign_seconds > closeout_reserve_seconds > 0.0
            and (
                not isinstance(shared, Mapping)
                or float(shared.get("total_budget_seconds", campaign_seconds))
                == campaign_seconds
            )
        ),
        "reserved_time": np.isfinite(reserved)
        and 0.0 < reserved <= campaign_seconds - closeout_reserve_seconds,
        "profile_contract": (
            contract.get("identity") == profile_identity
            and isinstance(contract.get("scope"), str)
            and contract.get("scope")
            == resolved.get("derived", {}).get("physical_intermediate_profile", {}).get("scope")
            and resolved.get("derived", {}).get("physical_intermediate_profile") == contract
        ),
        "v30_target_ny8_v15_v17_all_q_binding": v30_route_passed,
        "v31_target_ny8_v15_v17_all_q_binding": v31_route_passed,
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"Task40 p6 reference worker contract failed: {failed}")
    return {
        "schema": (
            "task40extra.review_v20_one_q_p6_reference_worker_contract.v1"
            if is_v20
            else "task40extra.review_v19_one_q_p6_reference_worker_contract.v1"
            if is_v19
            else "task40extra.review_v18_ny8_p6_reference_worker_contract.v1"
            if v18_identity is not None
            else
            "task40extra.review_v17_row_tile_p6_reference_worker_contract.v1"
            if is_v17
            else "task40extra.review_v16_p6_reference_worker_contract.v1"
            if is_v16
            else "task40extra.review_v15_p6_reference_worker_contract.v1"
            if is_v15
            else "task40extra.review_v13_p6_reference_worker_contract.v1"
            if is_v13
            else "task40extra.review_v10_b0_candidate_worker_contract.v1"
            if is_v10
            else "task40extra.review_v11_p6_grid_worker_contract.v1"
        ),
        "checks": checks,
        "campaign_window_path": campaign["window_path"],
        "campaign_window_sha256": campaign["window_sha256"],
        "campaign_accounting_path": campaign["accounting_path"],
        "worker_reserved_seconds": reserved,
        "campaign_seconds": campaign_seconds,
        "closeout_reserve_seconds": closeout_reserve_seconds,
        "effective_wall_clock_authority": "existing_V11_fixed_deadline_and_cumulative_remaining",
        "campaign_writer": "subreaper_watchdog_only",
        "worker_accounting_access": "read_only_projection",
        "factor_lifecycle_strategy": factor_lifecycle_strategy,
        "execution_contract_version": 31 if v31_route_requested else 30 if v30_route_requested else None,
    }


def _resolve_v30_worker_factor_lifecycle_strategy(
    resolved_payload: Mapping[str, Any],
    *,
    v30_enabled: bool,
    requested_strategy: str | None,
    effective_strategy: str | None,
) -> str:
    """Require the authorized V30 copy to carry AllQ while preserving its raw request."""

    raw_strategy = str(
        resolved_payload.get("solver", {}).get(
            "task40_factor_lifecycle_strategy", "ALL_Q_RESIDENT"
        )
    )
    if v30_enabled:
        if (
            requested_strategy != "ONE_Q_REFACTOR_V19"
            or effective_strategy != "ALL_Q_RESIDENT"
            or raw_strategy != effective_strategy
        ):
            raise ValueError(
                "V30 worker requires the dispatcher's V19-request/AllQ-effective binding"
            )
        return effective_strategy
    if requested_strategy is not None or effective_strategy is not None:
        raise ValueError("V30 factor-lifecycle binding is forbidden outside a V30 worker route")
    return raw_strategy


def run_task40_v10_p6_reference_worker(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
    profile_identity: str | None = None,
    share_transform_bank: bool = False,
    stop_after_stage: str | None = None,
    v30_q_csr_binding: Mapping[str, Any] | None = None,
    v30_factor_config: Mapping[str, Any] | None = None,
    v30_requested_factor_lifecycle_strategy: str | None = None,
    v30_effective_factor_lifecycle_strategy: str | None = None,
    v31_q_csr_binding: Mapping[str, Any] | None = None,
    v31_factor_config: Mapping[str, Any] | None = None,
    v31_q_csr_import_authorizations: Mapping[str, Any] | None = None,
    v31_target_admission_policy: Mapping[str, Any] | None = None,
    v31_execution_binding: Mapping[str, Any] | None = None,
    _v31_entry_validation_only: bool = False,
) -> dict[str, Any]:
    """Run a frozen Task40 p6 case with one live four-q periodic reference."""

    v30_contract = None
    v30_contract_sha = None
    v30_input_identity = None
    v31_input_identity = None
    v31_contract = None
    v31_contract_sha = None
    v31_route_facts = None
    if type(_v31_entry_validation_only) is not bool:
        raise TypeError("V31 route-fixture stop must be an explicit boolean")
    v31_strict = os.environ.get("TASK40_V31_STRICT_EXECUTION") == "1"
    if v31_strict or v31_execution_binding is not None or _v31_entry_validation_only:
        if not v31_strict or os.environ.get("TASK40_V30_STRICT_EXECUTION") == "1":
            raise RuntimeError("V31 worker route requires only the separate V31 strict contract")
        if not isinstance(v31_execution_binding, Mapping):
            raise RuntimeError("V31 worker route lacks its dispatcher-built execution binding")
        from src.runners.task40_v31_contract import (
            require_v31_execution_contract,
            validate_v31_worker_execution_binding,
        )

        repo_root = Path(__file__).resolve().parents[2]
        v31_contract, v31_contract_sha = require_v31_execution_contract(
            os.environ.get("TASK40_V31_CONTRACT_PATH", ""),
            expected_sha256=os.environ.get("TASK40_V31_CONTRACT_SHA256"),
            current_root=repo_root,
        )
        if (
            v31_contract_sha != os.environ.get("TASK40_V31_CONTRACT_SHA256")
            or not isinstance(v31_q_csr_import_authorizations, Mapping)
        ):
            raise RuntimeError("V31 worker authorization or import table differs from its service envelope")
        v31_route_facts = validate_v31_worker_execution_binding(
            dict(v31_execution_binding),
            contract=v31_contract,
            contract_sha256=v31_contract_sha,
            resolved_payload=dict(resolved_payload),
            source_sha=source_sha,
            environment=dict(os.environ),
            repo_root=repo_root,
        )
        if (
            dict(v31_q_csr_binding or {})
            != dict(v31_execution_binding["q_csr_selector_binding"])
            or dict(v31_factor_config or {})
            != dict(v31_execution_binding["factor_bank_config"])
        ):
            raise RuntimeError("V31 dispatcher selector/factor arguments differ from the approved worker binding")
        if v31_target_admission_policy is None:
            v31_target_admission_policy = dict(
                v31_execution_binding["target_admission_policy"]
            )
        if _v31_entry_validation_only:
            return {
                "status": "V31_ROUTE_VALIDATED_NO_FE_HOOKS",
                "official_result": False,
                "passed": False,
                "v31_worker_route": dict(v31_route_facts),
                "fe_hooks_invoked": False,
                "jit_hooks_invoked": False,
                "numerical_hooks_invoked": False,
            }
    elif _v31_entry_validation_only:
        raise RuntimeError("V31 route fixture stop cannot be used outside strict V31 mode")

    route_contract = v31_contract
    route_contract_sha = v31_contract_sha
    factor_config = (
        dict(v31_factor_config or v31_execution_binding["factor_bank_config"])
        if v31_contract is not None and isinstance(v31_execution_binding, Mapping)
        else None
    )
    provenance = resolved_payload.get("provenance", {})
    scientific_input_sha256 = str(
        provenance.get("input_sha256", "") if isinstance(provenance, Mapping) else ""
    )

    from mpi4py import MPI
    from petsc4py import PETSc
    from dolfinx import fem
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.io.physical_intermediate_profile import (
        TASK40_V10_P6_REFERENCE_PROFILE,
        TASK40_V11_P6_GX560_PROFILE,
        TASK40_V11_P6_GX784_PROFILE,
        TASK40_V15_P6_B0_PROFILE,
        TASK40_V15_P6_GX560_PROFILE,
        TASK40_V15_P6_E1_PROFILE,
        TASK40_V16_P6_GX560_PROFILE,
        TASK40_V16_P6_E1_PROFILE,
        TASK40_V17_P6_E1_PROFILE,
        TASK40_V18_P6_B0_Y8_PROFILE,
        TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
        TASK40_V20_V22_P6_PROFILES,
        profile_facts,
    )
    from src.runners.physical_p4_schur_v14 import (
        V14ResourceStop,
        _V14Runtime,
        _abi_facts,
        _repo_root,
        _write_json,
    )
    from src.solvers.dtn_boundary_phase_gauge import (
        BOUNDARY_PLANE,
        assembly_projection_denominator,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
        recover_p0_outputs,
    )
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.fresh_c1_p6_component import _boundary_support
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.hcurl_assembly_time_condensation import (
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.original_port_blocks import DiagonalOriginalPortBlock
    from src.solvers.p6_cell_condensed_action import (
        build_p6_cell_condensed_action_from_carrier,
    )
    from src.solvers.physical_equivalent_fast import build_packed_physical_action
    from src.solvers.retained_port_block_layout import RESEARCH_PORT_LAYOUT
    from src.solvers.augmented_reference_correction import (
        REFERENCE_PC_STRATEGIES,
        STRICT_ONLY,
        recheck_reference_pc_final_admission,
    )
    from src.solvers.task40_v10_p6_yorbit import (
        Q_ASSEMBLY_LEGACY,
        Q_ASSEMBLY_BOUNDED_V16,
        Q_ASSEMBLY_STRATEGIES,
        V16StagingLimitError,
        build_task40_v10_sector_contexts,
        build_task40_v10_p6_local_sector_owner,
        build_task40_v10_p6_reference_inverse,
        destroy_task40_v10_p6_local_sector_owner,
        destroy_task40_v10_p6_reference_inverse,
        _destroy_task40_v10_levels,
        _task40_v30_load_sector_q_csr_pair,
    )
    from src.geometry.task40_nonseparable_plan import (
        TASK40_V13_REFERENCE_PC_STRATEGY,
        TASK40_V15_REFERENCE_PC_STRATEGY,
        TASK40_B0_P6_V19_Y8_RUN_ID,
        TASK40_E1_V19_RUN_ID,
        TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
        task40_q_assembly_strategy_is_allowed,
    )
    from src.solvers.task40_v10_p6_periodic_profile import (
        TASK40_P6_PERIODIC_PROFILES,
    )
    from src.geometry.task40_nonseparable_plan import (
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
    )
    from src.solvers.physical_retained_fgmres import run_retained_fgmres
    from src.solvers.task40_v10_p6_mumps import (
        ALL_Q_RESIDENT,
        ONE_Q_REFACTOR_V19,
        _sparse_content_sha256,
        full_p6_pre_release_output_inventory,
    )
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    directory = Path(run_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stage = str(resolved_payload.get("solver", {}).get("stage", ""))
    reference_pc_strategy = str(
        resolved_payload.get("solver", {}).get("task40_reference_pc_strategy", STRICT_ONLY)
    )
    if reference_pc_strategy not in REFERENCE_PC_STRATEGIES:
        raise ValueError(f"unsupported Task40 reference-PC strategy: {reference_pc_strategy!r}")
    is_v13 = reference_pc_strategy == TASK40_V13_REFERENCE_PC_STRATEGY
    is_v15 = reference_pc_strategy == TASK40_V15_REFERENCE_PC_STRATEGY
    factor_lifecycle_strategy = str(
        resolved_payload.get("solver", {}).get(
            "task40_factor_lifecycle_strategy", ALL_Q_RESIDENT
        )
    )
    q_assembly_strategy = str(
        resolved_payload.get("solver", {}).get(
            "task40_q_assembly_strategy", Q_ASSEMBLY_LEGACY
        )
    )
    is_v17 = q_assembly_strategy == TASK40_Q_ASSEMBLY_ROW_TILE_V17
    if q_assembly_strategy not in Q_ASSEMBLY_STRATEGIES:
        raise ValueError(f"unsupported Task40 q assembly strategy: {q_assembly_strategy!r}")
    if not task40_q_assembly_strategy_is_allowed(
        reference_pc_strategy, q_assembly_strategy
    ):
        raise ValueError(
            "Task40 q assembly strategy is not authorized for the selected reference-PC strategy"
        )
    profile_identity = profile_identity or str(
        resolved_payload.get("solver", {}).get("preconditioner", "")
    )
    if profile_identity not in (
        TASK40_V10_P6_REFERENCE_PROFILE,
        TASK40_V11_P6_GX560_PROFILE,
        TASK40_V11_P6_GX784_PROFILE,
        TASK40_V15_P6_B0_PROFILE,
        TASK40_V15_P6_GX560_PROFILE,
        TASK40_V15_P6_E1_PROFILE,
        TASK40_V16_P6_GX560_PROFILE,
        TASK40_V16_P6_E1_PROFILE,
        "task40extra_v17_p6_y_orbit_b0_reference_v1",
        "task40extra_v17_p6_y_orbit_gx560_reference_v1",
        "task40extra_v17_p6_y_orbit_e1_reference_v1",
        TASK40_V18_P6_B0_Y8_PROFILE,
        *TASK40_V20_V22_P6_PROFILES,
    ):
        raise ValueError(f"unsupported Task40 p6 reference profile: {profile_identity}")
    is_v18 = profile_identity == TASK40_V18_P6_B0_Y8_PROFILE
    is_v20 = profile_identity in TASK40_V20_V22_P6_PROFILES
    v20_case = None
    if is_v20:
        from src.solvers.task40_v20_registry import task40_v20_case

        v20_case = task40_v20_case(profile=profile_identity)

    v31_route_requested = v31_contract is not None
    v30_route_requested = v30_q_csr_binding is not None or v30_factor_config is not None
    if v30_route_requested and v31_route_requested:
        raise RuntimeError("Task40 worker cannot mix V30 and V31 selector routes")
    selector_binding = (
        v31_q_csr_binding if v31_route_requested else v30_q_csr_binding
    )
    if v31_route_requested:
        if v30_q_csr_binding is not None or v30_factor_config is not None:
            raise RuntimeError("V31 worker cannot inherit V30 selector or factor bindings")
        repo_root = Path(__file__).resolve().parents[2]
        selector = v31_execution_binding["q_csr_selector_binding"]
        if (
            not isinstance(v31_q_csr_binding, Mapping)
            or dict(v31_q_csr_binding) != dict(selector)
            or factor_config is None
        ):
            raise RuntimeError("V31 worker selector or factor-bank binding differs from its contract")
        from src.runners.task40_v31_contract import (
            V31_CONTRACT_SCHEMA,
            V32_CONTRACT_SCHEMA,
            require_v31_input_identity,
            v31_source_artifact_relative,
        )
        from src.runners.task40_v30_contract import V30_CANONICAL_INPUT_RELATIVE

        if not isinstance(provenance, Mapping):
            raise ValueError("V31 worker input provenance is missing")
        staged_input_path = provenance.get("source_path")
        if not isinstance(staged_input_path, str) or not staged_input_path:
            raise ValueError("V31 worker provenance omits the staged DAT path")
        preparation = v31_contract.get("preparation", {})
        if v31_contract.get("schema") == V32_CONTRACT_SCHEMA:
            q4_numeric_pending_import = (
                preparation.get("q4_numeric_pending_import")
                if isinstance(preparation, Mapping)
                else None
            )
            if not isinstance(q4_numeric_pending_import, Mapping):
                raise RuntimeError("V32 worker contract omits its fixed q4 import template")
            q4_numeric_pending_import = dict(q4_numeric_pending_import)
            q4_complete_import = (
                preparation.get("q4_complete_import")
                if isinstance(preparation, Mapping)
                else None
            )
            q4_complete_import = (
                dict(q4_complete_import)
                if isinstance(q4_complete_import, Mapping)
                else None
            )
        elif v31_contract.get("schema") == V31_CONTRACT_SCHEMA:
            q4_numeric_pending_import = None
            q4_complete_import = None
        else:
            raise RuntimeError("V31 worker has an unknown approved contract schema")
        v31_input_identity = require_v31_input_identity(
            repo_root / V30_CANONICAL_INPUT_RELATIVE,
            staged_input_path,
            repo_root=repo_root,
            source_sha=str(v31_contract["source_freeze"]["source_sha"]),
            selector_sha256=str(selector["selector_sha256"]),
            q4_numeric_pending_import=q4_numeric_pending_import,
            q4_complete_import=q4_complete_import,
        )
        if v31_input_identity["staged_input_sha256"] != provenance.get("input_sha256"):
            raise ValueError("V31 worker raw stage SHA differs from run provenance")
        scientific_input_sha256 = v31_input_identity["scientific_input_sha256"]
    elif v30_route_requested:
        repo_root = Path(__file__).resolve().parents[2]
        if os.environ.get("TASK40_V30_STRICT_EXECUTION") != "1":
            raise RuntimeError("V30 worker requires the approved target-native execution contract")
        from src.runners.task40_v30_contract import require_authorized_contract

        v30_contract, v30_contract_sha = require_authorized_contract(
            os.environ.get("TASK40_V30_CONTRACT_PATH", ""),
            expected_sha256=os.environ.get("TASK40_V30_CONTRACT_SHA256"),
            current_root=repo_root,
        )
        execution = v30_contract["execution"]
        resources = execution["resources"]
        expected_window_path = Path(execution["campaign_window_path"]).resolve()
        if (
            os.environ.get("TASK40_V30_EXECUTION_WINDOW_PATH")
            != str(expected_window_path)
            or os.environ.get("TASK40_V30_EXECUTION_WINDOW_SHA256")
            != execution["campaign_window_sha256"]
            or os.environ.get("TASK40_V30_TASK_MEMORY_MAX_BYTES")
            != str(resources["task_memory_max_bytes"])
            or os.environ.get("TASK40_V30_HOST_RESERVE_BYTES")
            != str(resources["host_reserve_bytes"])
            or os.environ.get("TASK40_V30_MEMORY_SWAP_MAX_BYTES")
            != str(resources["memory_swap_max_bytes"])
            or not v30_contract_sha
        ):
            raise RuntimeError("V30 worker environment differs from its frozen execution contract")
        route_contract = v30_contract
        route_contract_sha = v30_contract_sha
        factor_config = dict(v30_factor_config or {})
        from src.runners.task40_v30_contract import (
            V30_CANONICAL_INPUT_RELATIVE,
            require_v30_input_identity,
        )

        if not isinstance(provenance, Mapping):
            raise ValueError("V30 worker input provenance is missing")
        staged_input_path = provenance.get("source_path")
        if not isinstance(staged_input_path, str) or not staged_input_path:
            raise ValueError("V30 worker provenance omits the staged DAT path")
        v30_input_identity = require_v30_input_identity(
            repo_root / V30_CANONICAL_INPUT_RELATIVE,
            staged_input_path,
            repo_root=repo_root,
        )
        if v30_input_identity["staged_input_sha256"] != provenance.get("input_sha256"):
            raise ValueError("Task40 worker raw stage SHA differs from run provenance")
        scientific_input_sha256 = v30_input_identity["scientific_input_sha256"]

    v30_enabled = v30_route_requested or v31_route_requested
    allq_route_enabled = v30_enabled
    if v31_target_admission_policy is not None:
        if (
            not isinstance(v31_target_admission_policy, Mapping)
            or v31_target_admission_policy.get("schema")
            != "task40extra.review_v31_target_admission.v1"
            or v31_target_admission_policy.get("phase") != "REFERENCE_ONLY"
            or set(v31_target_admission_policy)
            - {"schema", "phase", "target_owner_increment_inventory"}
        ):
            raise ValueError("V31 target-admission policy is not a closed REFERENCE_ONLY contract")
        v31_target_admission_policy = dict(v31_target_admission_policy)
    effective_factor_lifecycle_strategy = _resolve_v30_worker_factor_lifecycle_strategy(
        resolved_payload,
        v30_enabled=v30_enabled,
        requested_strategy=v30_requested_factor_lifecycle_strategy,
        effective_strategy=v30_effective_factor_lifecycle_strategy,
    )
    factor_lifecycle_strategy = effective_factor_lifecycle_strategy
    if factor_lifecycle_strategy not in {ALL_Q_RESIDENT, ONE_Q_REFACTOR_V19}:
        raise ValueError(f"unsupported Task40 factor lifecycle strategy: {factor_lifecycle_strategy!r}")
    is_v19 = factor_lifecycle_strategy == ONE_Q_REFACTOR_V19
    if allq_route_enabled and (
        selector_binding is None
        or factor_config is None
        or not is_v20
        or v20_case is None
        or v20_case.mesh_id != "TARGET_ORIGINAL_NY8"
        or factor_lifecycle_strategy != TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
        or not is_v17
        or not is_v15
        or stop_after_stage is not None
    ):
        raise ValueError(
            "Task40 AllQ worker requires target Ny8, V15 row-tile, selector and factor config"
        )
    expected_factor_schema = (
        "task40extra.review_v31_all_q_factor_bank.v1"
        if v31_contract is not None
        else "task40extra.review_v30_all_q_factor_bank.v1"
    )
    if allq_route_enabled and (
        factor_config.get("schema") != expected_factor_schema
        or not isinstance(factor_config.get("output_directory"), str)
    ):
        raise ValueError("Task40 worker factor configuration is not a frozen AllQ packet contract")

    if stop_after_stage is not None:
        from src.solvers.task40_v20_registry import V20_STOP_STAGES

        if (
            not is_v20
            or stop_after_stage not in V20_STOP_STAGES
            or stop_after_stage not in {"build_and_symbolic", "one_q_numeric"}
        ):
            raise ValueError("V20 worker stage stops require an exact registered staged V20 case")
    if is_v19:
        expected_v19 = {
            TASK40_V17_P6_E1_PROFILE: (TASK40_E1_V19_RUN_ID, "Q4_ORIGINAL"),
            TASK40_V18_P6_B0_Y8_PROFILE: (TASK40_B0_P6_V19_Y8_RUN_ID, "B0_CANDIDATE"),
        }.get(profile_identity)
        if is_v20:
            expected_v19 = (v20_case.run_id, v20_case.solver_stage)
        if (
            expected_v19 is None
            or resolved_payload.get("run_id") != expected_v19[0]
            or stage != expected_v19[1]
            or not is_v15
            or not is_v17
        ):
            raise ValueError("ONE_Q_REFACTOR_V19 worker requires an exact V19 E1 or B0-Y8 input")
    if is_v17 and not (
        profile_identity.startswith("task40extra_v17_p6_y_orbit_") or is_v18 or is_v20
    ):
        raise ValueError("V17 row-tile CSR requires a registered V17 p6 profile")
    if type(share_transform_bank) is not bool:
        raise TypeError("V12 transform-bank selection must be an explicit boolean")
    periodic_profile = TASK40_P6_PERIODIC_PROFILES[profile_identity]
    if v31_target_admission_policy is not None and not (
        allq_route_enabled
        and share_transform_bank
        and is_v20
        and profile_identity == TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
        and periodic_profile.q_count == 8
        and factor_config is not None
    ):
        raise ValueError("V31 target admission is restricted to the shared-bank Ny8 AllQ route")
    is_v10 = profile_identity == TASK40_V10_P6_REFERENCE_PROFILE
    is_v16 = profile_identity in (TASK40_V16_P6_GX560_PROFILE, TASK40_V16_P6_E1_PROFILE)
    case_labels = {
        TASK40_V10_P6_REFERENCE_PROFILE: "b0",
        TASK40_V11_P6_GX560_PROFILE: "gx560",
        TASK40_V11_P6_GX784_PROFILE: "gx784",
        TASK40_V15_P6_B0_PROFILE: "b0",
        TASK40_V15_P6_GX560_PROFILE: "gx560",
        TASK40_V15_P6_E1_PROFILE: "e1",
        TASK40_V16_P6_GX560_PROFILE: "gx560",
        TASK40_V16_P6_E1_PROFILE: "e1",
        "task40extra_v17_p6_y_orbit_b0_reference_v1": "b0",
        "task40extra_v17_p6_y_orbit_gx560_reference_v1": "gx560",
        "task40extra_v17_p6_y_orbit_e1_reference_v1": "e1",
        TASK40_V18_P6_B0_Y8_PROFILE: "b0_y8",
    }
    if is_v20:
        case_labels[profile_identity] = v20_case.mesh_id.lower()
    case_label = case_labels[profile_identity]
    evidence_prefix = (
        "v20_one_q_row_tile_p6_reference"
        if is_v20
        else "v19_one_q_row_tile_p6_reference"
        if is_v19
        else
        "v18_ny8_row_tile_p6_reference"
        if is_v18
        else "v17_row_tile_p6_reference"
        if is_v17
        else
        "v16_p6_reference"
        if is_v16
        else "v15_p6_reference"
        if is_v15
        else "v13_p6_reference"
        if is_v13
        else "v10_candidate"
        if is_v10
        else "v11_p6_grid"
    )
    contract = profile_facts(profile_identity)
    runtime_contract = contract
    route_contract = v31_contract if v31_route_requested else v30_contract
    if route_contract is not None:
        runtime_contract = copy.deepcopy(contract)
        route_execution = route_contract["execution"]
        runtime_resources = runtime_contract["resources"]
        runtime_resources.update(
            {
                "process_tree_rss_cap_bytes": int(
                    route_execution["resources"]["task_memory_max_bytes"]
                ),
                "host_reserve_bytes": int(route_execution["resources"]["host_reserve_bytes"]),
                "memory_swap_max_bytes": 0,
                "workflow_seconds": float(route_execution["window"]["total_seconds"]),
                "campaign_closeout_reserve_seconds": float(
                    route_execution["window"]["closeout_reserve_seconds"]
                ),
            }
        )
    summary: dict[str, Any] = {
        "schema": (
            "task40extra.review_v20_one_q_row_tile_p6_reference_worker_summary.v1"
            if is_v20
            else "task40extra.review_v19_one_q_row_tile_p6_reference_worker_summary.v1"
            if is_v19
            else "task40extra.review_v18_ny8_row_tile_p6_reference_worker_summary.v1"
            if is_v18
            else "task40extra.review_v17_row_tile_p6_reference_worker_summary.v1"
            if is_v17
            else
            "task40extra.review_v16_p6_reference_worker_summary.v1"
            if is_v16
            else "task40extra.review_v15_p6_reference_worker_summary.v1"
            if is_v15
            else "task40extra.review_v13_p6_reference_worker_summary.v1"
            if is_v13
            else
            "task40extra.review_v10_b0_candidate_worker_summary.v1"
            if is_v10
            else "task40extra.review_v11_p6_grid_candidate_worker_summary.v1"
        ),
        "profile": profile_identity,
        "reference_pc_strategy": reference_pc_strategy,
        "q_assembly_strategy": q_assembly_strategy,
        "factor_lifecycle_strategy": factor_lifecycle_strategy,
        "periodic_inventory_expectations": periodic_profile.identity(),
        "stage": stage,
        "source_sha": source_sha,
        "v12_shared_transform_bank": {
            "enabled": share_transform_bank,
            "scope": "p6 cell-interior 450x450 blocks only; edges/faces use the legacy path",
            "one_owner_shared_by_global_and_both_sectors": share_transform_bank,
        },
        "status": "STARTED",
        "official_result": False,
        "result_classification": "INCOMPLETE",
    }
    if v31_route_requested:
        summary["run_id"] = resolved_payload.get("run_id")
        summary["v31_input_identity"] = dict(v31_input_identity or {})
    if v31_target_admission_policy is not None:
        summary["v31_target_admission_policy"] = {
            "schema": v31_target_admission_policy["schema"],
            "initial_phase": "REFERENCE_ONLY",
            "target_owner_increment_inventory": v31_target_admission_policy.get(
                "target_owner_increment_inventory"
            ),
        }
    if MPI.COMM_WORLD.Get_size() != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("Task40 p6 reference worker requires qualified MPI1 complex128")
    if not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("Task40 V10 p6 worker requires the complete source SHA")

    runtime = None
    target_levels = None
    target_bundle = None
    target_fast_bundle = None
    target_action = None
    target_condensed = None
    mode_identity: dict[str, Any] = {}
    mode_inventory_preflight: dict[str, Any] = {}
    target_backend_facts: dict[str, Any] = {}
    target_identity_cache_audit: dict[str, Any] = {}
    reference = None
    prebuilt_twist0_owner: dict[str, Any] | None = None
    rhs = None
    physical_rhs = None
    final_full_solution = None
    final_solution = None
    pc = None
    reference_audit_snapshot = None
    allocation_gate_records: list[dict[str, Any]] = []
    allocation_gate_summary: dict[str, dict[str, Any]] = {}
    allocation_gate_invocation_count = 0
    handlers: dict[int, Any] = {}
    outer_started = False
    result: dict[str, Any] | None = None
    worker_result: dict[str, Any] | None = None
    v20_stage_facts: dict[str, Any] | None = None
    v20_stage_factors: Any | None = None
    qualified_q_csr_provider = None
    qualified_q_csr_identity: dict[str, Any] | None = None
    try:
        runtime_resource_overrides = {}
        if route_contract is not None:
            route_resources = route_contract["execution"]["resources"]
            runtime_resource_overrides = {
                "fixed_process_tree_cap_bytes": int(route_resources["task_memory_max_bytes"]),
                "host_reserve_bytes": int(route_resources["host_reserve_bytes"]),
                "task_cgroup_reserve_bytes": 0,
                "require_cgroup_memory_details": True,
            }
        runtime = _V14Runtime(
            directory,
            stage,
            runtime_contract,
            root=_repo_root(),
            source_sha=source_sha,
            batch_identity=(
                f"task40_review_v20_one_q_{case_label}_p6_reference"
                if is_v20
                else f"task40_review_v19_one_q_{case_label}_p6_reference"
                if is_v19
                else f"task40_review_v18_ny8_{case_label}_p6_reference"
                if is_v18
                else f"task40_review_v17_{case_label}_p6_reference"
                if is_v17
                else f"task40_review_v16_{case_label}_p6_reference"
                if is_v16
                else f"task40_review_v15_{case_label}_p6_reference"
                if is_v15
                else f"task40_review_v13_{case_label}_p6_reference"
                if is_v13
                else "task40_review_v10_integrated_p6_engineering"
                if is_v10
                else f"task40_review_v11_{case_label}_p6_y_orbit"
            ),
            evidence_prefix=evidence_prefix,
            require_zero_swap=True,
            **runtime_resource_overrides,
        )
        summary["abi"] = _abi_facts(
            profile_identity=profile_identity,
            v30_contract_path=(
                os.environ.get("TASK40_V30_CONTRACT_PATH")
                if v30_contract is not None
                else None
            ),
            v30_contract_sha256=(
                v30_contract_sha if v30_contract is not None else None
            ),
            v31_contract_path=(
                os.environ.get("TASK40_V31_CONTRACT_PATH")
                if v31_contract is not None
                else None
            ),
            v31_contract_sha256=(
                v31_contract_sha if v31_contract is not None else None
            ),
        )
        if v31_contract is not None:
            summary["v31_execution_contract_binding"] = dict(v31_route_facts or {})
        summary["campaign_authority"] = _candidate_contract(
            resolved_payload,
            contract,
            runtime,
            profile_identity=profile_identity,
            v30_contract=v30_contract,
            v31_contract=v31_contract,
            v30_effective_factor_lifecycle_strategy=(
                effective_factor_lifecycle_strategy
                if v30_contract is not None
                else None
            ),
            v31_effective_factor_lifecycle_strategy=(
                effective_factor_lifecycle_strategy
                if v31_contract is not None
                else None
            ),
        )
        summary["time_policy"] = runtime.time_policy
        summary["time_policy_facts"] = dict(runtime.time_policy_facts)
        summary["shared_budget"] = runtime.shared_budget
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(
                signum,
                lambda *_args: setattr(runtime, "stop_requested", True),
            )
        runtime.sample("v10_candidate_preflight")

        cfg = simulation_config_3d_from_normalized(resolved_payload)
        v20_mode_inventory = None
        v20_mode_metadata = None
        if is_v20 and v20_case.mesh_id == "TARGET_ORIGINAL_NY8":
            from src.solvers.task40_v20_mode_inventory import load_v20_target_mode_inventory

            frozen_modes, frozen_rows, frozen_sha, v20_mode_metadata = (
                load_v20_target_mode_inventory(resolved_payload)
            )
            v20_mode_inventory = (frozen_modes, frozen_rows, frozen_sha)
        axis_plan = _stage4_axis_plan(cfg, MPI.COMM_SELF.Get_size())
        axes = {
            "x": tuple(map(float, axis_plan.x_values)),
            "y": tuple(map(float, axis_plan.y_values)),
            "z": tuple(map(float, axis_plan.z_values)),
        }
        def allocation_gate(label: str, facts: Mapping[str, Any]) -> dict[str, Any]:
            nonlocal allocation_gate_invocation_count
            allocation_gate_invocation_count += 1
            v31_admission_candidate: Mapping[str, Any] | None = None
            if facts.get("resource_sample_only") is True and label.startswith(
                "one_q_resource_sample_v19_"
            ):
                sample = runtime.sample(f"v10_{label}", enforce=False)
                record = {
                    "schema": "task40extra.review_v19_one_q_resource_sample.v1",
                    "label": str(label),
                    **dict(facts),
                    "current_process_tree_rss_bytes": int(sample["rss_bytes"]),
                    "resource_sample": sample,
                    "resource_sample_only": True,
                }
                allocation_gate_records.append(record)
                runtime.marker("v10_strict_allocation_admission", record)
                runtime.marker("v10_strict_allocation_admission_complete", record)
                return record
            amount = int(facts.get(
                "additional_payload_bytes",
                facts.get("matrix_payload_bytes", facts.get("workspace_bytes", 0)),
            ))
            workspace = int(facts.get("workspace_bytes", 0))
            v18_matrix_facts = None
            if is_v18 and label.startswith(
                "task40_v18_full_native_volume_matrix_"
            ):
                v18_matrix_facts, checked = _v18_preproject_native_matrix_gate(
                    runtime,
                    label,
                    facts,
                    amount_bytes=amount,
                    workspace_bytes=workspace,
                    header_path=(
                        Path(sys.prefix) / "include/dolfinx_mpc/utils.h"
                    ),
                )
            else:
                checked = runtime.check_projected(
                    f"v10_{label}", amount, workspace_bytes=workspace
                )
            future = 0
            future_components: dict[str, int] = {}
            if facts.get("factor_lifecycle_strategy") == "ONE_Q_REFACTOR_V19":
                components = facts.get("future_reserve_components")
                required_components = {
                    "persistent_pending_transform_inverse_payload_bytes",
                    "selected_maximum_co_resident_phase_bytes",
                    "one_q_symbolic_guard_bytes",
                    "one_q_numeric_factor_reserve_bytes",
                }
                if not isinstance(components, Mapping) or set(components) != required_components:
                    raise ValueError("V19 one-q admission lacks its exact future-reserve components")
                future_components = {str(key): int(value) for key, value in components.items()}
                if any(value < 0 for value in future_components.values()):
                    raise ValueError("V19 one-q future-reserve components cannot be negative")
                future = sum(future_components.values())
                if int(facts.get("future_co_resident_reserve_bytes", -1)) != future:
                    raise ValueError("V19 one-q future-reserve total differs from its components")
                if (
                    facts.get("all_q_source_csr_retained") is not True
                    or facts.get("numeric_factors_to_be_retained_simultaneously") != 1
                    or facts.get("current_work_arrays_already_live") is not True
                    or future_components["persistent_pending_transform_inverse_payload_bytes"]
                    != int(facts.get("future_inverse_payload_bytes", -1))
                    or future_components["selected_maximum_co_resident_phase_bytes"]
                    != int(facts.get("selected_future_nonfactor_co_resident_phase_bytes", -1))
                ):
                    raise ValueError("V19 one-q admission facts do not match the active lifecycle contract")
            elif label == "all_q_symbolic_before_any_numeric":
                estimates = facts.get("q_symbolic_estimates_bytes", {})
                if not isinstance(estimates, Mapping) or set(map(int, estimates)) != set(
                    range(periodic_profile.q_count)
                ):
                    raise ValueError(
                        "all-q numeric gate requires every actual INFOG(16/17) estimate"
                    )
                mumps_estimate = int(sum(int(value) for value in estimates.values()))
                stated_ksp_vectors = int(facts.get("future_retained_krylov_and_vector_bytes", 0))
                inverse_payload = int(facts.get("future_inverse_payload_bytes", 0))
                inverse_workspace = int(
                    facts.get("future_inverse_single_operation_workspace_bytes", 0)
                )
                full_output = int(
                    facts.get("future_full_p6_pre_release_recovery_output_bytes", 0)
                )
                selected_phase = int(
                    facts.get("selected_future_nonfactor_co_resident_peak_bytes", -1)
                )
                expected_phase = max(
                    stated_ksp_vectors + inverse_workspace,
                    full_output + inverse_workspace,
                )
                if selected_phase != expected_phase:
                    raise ValueError("all-q co-resident phase peak disagrees with its KSP/full-output inventory")
                if int(facts.get("future_inverse_payload_plus_selected_phase_bytes", -1)) != (
                    inverse_payload + selected_phase
                ):
                    raise ValueError("all-q persistent inverse payload and selected phase reserve disagree")
                phase_inventory = facts.get("pre_release_recovery_output_inventory", {})
                if share_transform_bank and v31_target_admission_policy is not None:
                    v31_admission_candidate = _task40_v31_reference_only_allq_callback(
                        facts, expected_q_count=periodic_profile.q_count
                    )
                    future_components = dict(
                        v31_admission_candidate["future_reserve_components"]
                    )
                    future = int(v31_admission_candidate["future_reserve_bytes"])
                else:
                    if (
                        share_transform_bank
                        and (
                            int(facts.get("full_storage_rows_for_future_recovery", 0)) <= 0
                            or not isinstance(phase_inventory, Mapping)
                            or phase_inventory.get(
                                "actual_target_and_reference_full_rows_match_required"
                            ) is not True
                        )
                    ):
                        raise ValueError(
                            "V12 all-q gate lacks actual target/reference full-row recovery dimensions"
                        )
                    future_components = {
                        "mumps_symbolic_estimate_sum_bytes": mumps_estimate,
                        "persistent_pending_transform_inverse_payload_bytes": inverse_payload,
                        "selected_maximum_co_resident_phase_bytes": selected_phase,
                    }
                    future = sum(future_components.values())
            elif "declared_future_co_resident_bytes" in facts:
                phase_bytes = int(facts["declared_future_co_resident_bytes"])
                if phase_bytes < 0:
                    raise ValueError("phase-specific co-resident reserve cannot be negative")
                future_components = {"declared_future_co_resident_phase_bytes": phase_bytes}
                future = phase_bytes
            headroom = 128 << 20
            live = runtime.sample(f"v10_{label}_strict_admission")
            profile_cap = int(
                route_contract["execution"]["resources"]["task_memory_max_bytes"]
                if route_contract is not None
                else contract["resources"]["process_tree_rss_cap_bytes"]
            )
            cap = min(profile_cap, int(live["launch_cap_bytes"]))
            untouched_workspace = int(checked.get("workspace_untouched_reserve_bytes", 0))
            envelope = live.get("memory_envelope")
            if not isinstance(envelope, Mapping):
                raise RuntimeError("strict allocation admission has no current memory envelope")
            incremental_headroom = int(envelope["launch_cap_bytes"])
            bounds = _v12_memory_admission_bounds(
                live_rss_bytes=int(live["rss_bytes"]),
                total_rss_cap_bytes=cap,
                incremental_headroom_bytes=incremental_headroom,
                delta_bytes=amount + workspace + untouched_workspace + future,
                reserve_bytes=headroom,
            )
            admission = {
                "schema": "task40extra.review_v12_allocation_admission.v1",
                "label": str(label),
                "requested_additional_bytes": amount,
                "requested_workspace_bytes": workspace,
                "workspace_untouched_reserve_bytes": untouched_workspace,
                "future_all_q_and_transform_reserve_bytes": future,
                "future_reserve_components": future_components,
                "fixed_future_workspace_headroom_bytes": headroom,
                "current_process_tree_rss_bytes": int(live["rss_bytes"]),
                "profile_tree_cap_bytes": profile_cap,
                "dynamic_launch_cap_bytes": int(live["launch_cap_bytes"]),
                "effective_absolute_total_rss_cap_bytes": cap,
                "incremental_headroom_bytes": incremental_headroom,
                **bounds,
                "physical_memory_envelope": live.get("memory_envelope"),
                "generic_projection": checked,
                "native_symbolic_facts": facts.get("current_symbolic_native_metrics"),
                "q_symbolic_native_metrics_by_q": facts.get("q_symbolic_native_metrics_by_q"),
                "native_allocated_used_facts": facts.get("resident_numeric_mumps_facts"),
                "current_q_native_allocated_bytes_upper": facts.get(
                    "current_q_native_allocated_bytes_upper"
                ),
                "current_q_native_used_bytes_upper": facts.get(
                    "current_q_native_used_bytes_upper"
                ),
                "future_bank_inverse_reserve": facts.get("future_bank_inverse_reserve"),
                "future_legacy_inverse_reserves_by_collection": facts.get(
                    "future_legacy_inverse_reserves_by_collection"
                ),
                "future_krylov_and_ksp_workspace_bytes": facts.get(
                    "future_retained_krylov_and_vector_bytes"
                ),
                "future_full_p6_pre_release_recovery_output_bytes": facts.get(
                    "future_full_p6_pre_release_recovery_output_bytes"
                ),
                "full_storage_rows_for_future_recovery": facts.get(
                    "full_storage_rows_for_future_recovery"
                ),
                "pre_release_recovery_output_inventory": facts.get(
                    "pre_release_recovery_output_inventory"
                ),
                "selected_future_nonfactor_co_resident_phase": facts.get(
                    "selected_future_nonfactor_co_resident_phase"
                ),
            }
            if v18_matrix_facts is not None:
                admission["v18_full_native_matrix_facts"] = v18_matrix_facts
            if is_v16 or is_v17:
                if label.startswith(("task40_v16_q_", "task40_v17_q_")) or label.startswith(
                    "p6_reduced_contribution/"
                ):
                    admission[
                        "v17_row_tile_staging_facts" if is_v17 else "v16_staging_facts"
                    ] = dict(facts)
                key = _allocation_gate_summary_key(label)
                if key not in allocation_gate_summary and len(allocation_gate_summary) >= 32:
                    key = "other_bounded_groups"
                row = allocation_gate_summary.setdefault(
                    key,
                    {
                        "count": 0,
                        "peak_staging_live_bytes_upper": 0,
                        "peak_requested_additional_bytes": 0,
                        "peak_requested_workspace_bytes": 0,
                        "peak_projected_process_tree_rss_bytes": 0,
                        "peak_projected_incremental_capacity_bytes": 0,
                        "peak_label": "",
                    },
                )
                row["count"] += 1
                staging_peak = int(
                    facts.get("staging_live_bytes_upper", amount + workspace)
                )
                row["peak_requested_additional_bytes"] = max(
                    int(row["peak_requested_additional_bytes"]), amount
                )
                row["peak_requested_workspace_bytes"] = max(
                    int(row["peak_requested_workspace_bytes"]), workspace
                )
                row["peak_projected_process_tree_rss_bytes"] = max(
                    int(row["peak_projected_process_tree_rss_bytes"]),
                    int(bounds["projected_process_tree_rss_bytes"]),
                )
                row["peak_projected_incremental_capacity_bytes"] = max(
                    int(row["peak_projected_incremental_capacity_bytes"]),
                    int(bounds["projected_incremental_capacity_bytes"]),
                )
                if staging_peak >= int(row["peak_staging_live_bytes_upper"]):
                    row["peak_staging_live_bytes_upper"] = staging_peak
                    row["peak_label"] = str(label)
            else:
                allocation_gate_records.append(admission)
            runtime.marker("v10_strict_allocation_admission", admission)
            if not (
                bounds["total_rss_inequality_passed"]
                and bounds["incremental_headroom_inequality_passed"]
            ):
                from .physical_p4_schur_v14 import V14ResourceStop

                raise V14ResourceStop(f"Task40 V12 two-boundary memory admission failed: {admission}")
            completion_sample = runtime.sample(f"v10_{label}_allocation_gate")
            admission["allocation_gate_completion_sample"] = completion_sample
            if v31_admission_candidate is not None:
                reference_admission = _task40_v31_finalize_admission_after_resource_gate(
                    v31_admission_candidate,
                    admission,
                    completion_sample,
                )
                summary["v31_reference_only_admission"] = reference_admission
                runtime.marker(
                    "task40_v31_reference_only_admitted_before_numeric",
                    reference_admission,
                )
            runtime.marker("v10_strict_allocation_admission_complete", admission)
            return admission

        def identity_gate(reference_bundle: Mapping[str, Any], reference_levels: Mapping[str, Any]):
            if target_bundle is None or target_levels is None:
                raise RuntimeError("target physical identity cannot be checked before target construction")
            mode_identity.update(
                _validate_reference_physical_identity(
                    target_bundle, target_levels, reference_bundle, reference_levels
                )
            )

        def build_target_context(
            reference_owner: Mapping[str, Any] | None = None,
            mode_inventory: tuple[Any, Any, str] | None = None,
        ) -> None:
            nonlocal target_levels, target_bundle, target_condensed, target_action, target_fast_bundle
            nonlocal target_identity_cache_audit, mode_inventory_preflight, target_backend_facts
            if mode_inventory is not None and mode_inventory != v20_mode_inventory:
                raise ValueError("V30 target builder received a different frozen mode inventory")
            if v31_target_admission_policy is not None:
                target_build_admission = _task40_v31_target_build_admission(
                    summary.get("v31_reference_only_admission"),
                    v31_target_admission_policy.get("target_owner_increment_inventory"),
                )
                target_build_resource_admission = allocation_gate(
                    "task40_v31_target_build_admission",
                    {
                        "additional_payload_bytes": 0,
                        "workspace_bytes": 0,
                        "declared_future_co_resident_bytes": target_build_admission[
                            "reserved_target_owner_increment_bytes"
                        ],
                        "target_admission_phase": "TARGET_BUILD",
                        "target_owner_increment_inventory": target_build_admission[
                            "target_owner_increment_inventory"
                        ],
                    },
                )
                target_build_admission = _task40_v31_finalize_admission_after_resource_gate(
                    target_build_admission,
                    target_build_resource_admission,
                    target_build_resource_admission.get(
                        "allocation_gate_completion_sample"
                    ),
                )
                summary["v31_target_build_admission"] = target_build_admission
                runtime.marker("task40_v31_target_build_admitted", target_build_admission)
            runtime.set_phase("assembly")
            runtime.marker(
                "v10_candidate_target_mesh_started",
                {
                    "cell_axes": list(cfg.mesh_axis_cell_counts_requested or ()),
                    "axes": {key: list(value) for key, value in axes.items()},
                    "target_keeps_air_void": True,
                    "degrees": [6],
                    "positive_hierarchy": False,
                },
            )
            target_levels = _build_same_mesh_levels(
                cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
            )
            target_bundle = build_same_mesh_physical_action(
                target_levels,
                cfg,
                6,
                mode_inventory=v20_mode_inventory,
                jit_options=SAME_MESH_JIT_OPTIONS,
                dtn_phase_gauge=BOUNDARY_PLANE,
                verify_dtn_quadrature=True,
            )
            if len(target_bundle["modes"]) != periodic_profile.mode_count:
                raise ValueError(
                    f"{case_label} target must retain all "
                    f"{periodic_profile.mode_count} physical modes"
                )
            if tuple(map(int, cfg.mesh_axis_cell_counts_requested or ())) != periodic_profile.global_cell_axes:
                raise ValueError(f"{case_label} resolved mesh axes differ from its p6 profile")

            regular_cfg = __import__("dataclasses").replace(
                cfg,
                air_void_box_nm=None,
                cell_notch=None,
                geometry_identity=f"{cfg.geometry_identity}.regular_reference_identity_probe",
            )
            if v20_mode_inventory is None:
                target_inventory = build_dynamic_mode_inventory(cfg)
                reference_inventory = build_dynamic_mode_inventory(regular_cfg)
            else:
                target_inventory = v20_mode_inventory
                reference_inventory = v20_mode_inventory
            target_inventory_keys = tuple(
                (index, str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
                for index, mode in enumerate(target_inventory[0])
            )
            reference_inventory_keys = tuple(
                (index, str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
                for index, mode in enumerate(reference_inventory[0])
            )
            mode_inventory_preflight = {
                "target_physical_mode_sha256": str(target_inventory[2]),
                "reference_physical_mode_sha256": str(reference_inventory[2]),
                "target_mode_count": len(target_inventory[0]),
                "reference_mode_count": len(reference_inventory[0]),
                "ordered_mode_keys_equal": target_inventory_keys == reference_inventory_keys,
                "ordered_physical_mode_sha_equal": target_inventory[2] == reference_inventory[2],
                "target_carrier_physical_generator_sha256": str(
                    getattr(target_bundle["dtn_action"].carrier,
                            "physical_generator_manifest_sha256", "")
                ),
                "target_carrier_assembly_manifest_sha256": str(
                    target_bundle["dtn_action"].carrier.mode_manifest_sha256
                ),
                **(
                    {"frozen_mode_source_lineage": v20_mode_metadata}
                    if v20_mode_metadata is not None
                    else {}
                ),
            }
            if not (
                mode_inventory_preflight["ordered_mode_keys_equal"]
                and mode_inventory_preflight["ordered_physical_mode_sha_equal"]
                and mode_inventory_preflight["target_mode_count"] == periodic_profile.mode_count
                and mode_inventory_preflight["reference_mode_count"] == periodic_profile.mode_count
                and mode_inventory_preflight["target_carrier_physical_generator_sha256"]
                == target_inventory[2]
                and target_bundle.get("physical_generator_manifest_sha256") == target_inventory[2]
            ):
                raise ValueError(
                    "target and regular ordered physical mode identity preflight failed: "
                    f"{mode_inventory_preflight}"
                )
            if reference_owner is not None:
                identity_gate(reference_owner["global_bundle"], reference_owner["global_levels"])
            runtime.sample("v10_candidate_target_mesh_and_operator_complete")

            support_groups, support_rows, _support_facts = _boundary_support(target_bundle)
            compiled_target = fem.form(
                target_bundle["volume_action"].bilinear_form,
                jit_options=dict(SAME_MESH_JIT_OPTIONS),
            )
            target_condensed = build_unconstrained_assembly_time_condensation(
                compiled_target,
                target_levels["spaces"][6],
                target_levels["mesh_data"].cell_tags,
                mpc=target_levels["floquets"][6].mpc,
                appended_global_rows=len(target_bundle["dtn_action"].carrier.entries),
                appended_support_owned_cell_groups=support_groups,
                appended_support_group_by_row=support_rows,
                sum_duplicate_cell_integrals=True,
                strict_local_checks=True,
                materialize_global_matrix=False,
                retain_local_schur_for_matrix_free=True,
                share_identity_cache=is_v16 or is_v17,
                preserve_exact_geometry=True,
                allocation_gate=allocation_gate,
            )
            target_identity_cache_audit = {
                key: target_condensed.build_audit.get(key)
                for key in (
                    "identity_cache_mode",
                    "identity_cache_readonly",
                    "identity_cache_class_count_local",
                    "identity_cache_bytes_local",
                    "retained_local_schur_bytes_local",
                    "retained_local_schur_class_count_local",
                )
            }
            target_action = build_p6_cell_condensed_action_from_carrier(
                target_condensed,
                target_bundle["dtn_action"].carrier,
                owns_condensed=True,
                port_coupling_mode="cached",
                port_block_layout=RESEARCH_PORT_LAYOUT,
                original_port_block=DiagonalOriginalPortBlock.from_carrier(
                    target_bundle["dtn_action"].carrier.entries
                ),
            )
            if is_v16 or is_v17:
                owner_version = "v17_row_tile" if is_v17 else "v16"
                owner_key = "v17_target_owner_inventory" if is_v17 else "v16_target_owner_inventory"
                owner_marker = (
                    "v17_row_tile_target_condensed_action_owner_inventory"
                    if is_v17
                    else "v16_target_condensed_action_owner_inventory"
                )
                owner_sample = (
                    "v17_row_tile_target_condensed_action_complete"
                    if is_v17
                    else "v16_target_condensed_action_complete"
                )
                target_owner_inventory = {
                    "schema": f"task40extra.review_{owner_version}_target_owner_inventory.v1",
                    "target_condensation_identity_cache": target_identity_cache_audit,
                    "target_action_buffer_inventory": dict(target_action.buffer_inventory),
                    "identity_cache_scope": (
                        "one read-only real identity per target interior shape; local LU, recovery, "
                        "and Schur buffers remain their separately counted owners"
                    ),
                    "source_owner": "target_condensed transferred to target_action.condensed",
                }
                summary[owner_key] = target_owner_inventory
                runtime.marker(owner_marker, target_owner_inventory)
                runtime.sample(owner_sample)
            target_condensed = None
            _validate_target_p6_inventory(target_action.condensed, periodic_profile)
            if reference_owner is not None:
                actual_rows = int(target_action.condensed.full_rows)
                reference_rows = int(reference_owner["full_layout"].full_rows)
                planned_rows = int(periodic_profile.global_storage_rows)
                if actual_rows != reference_rows or actual_rows != planned_rows:
                    raise ValueError(
                        "V30 actual target storage rows differ from the reserved reference plan: "
                        f"actual={actual_rows}, reference={reference_rows}, planned={planned_rows}"
                    )
                row_identity = {
                    "schema": "task40extra.review_v30_target_reference_row_identity.v1",
                    "actual_target_full_storage_rows": actual_rows,
                    "planned_target_full_storage_rows": planned_rows,
                    "reference_full_storage_rows": reference_rows,
                    "planned_target_rows_match_reference": planned_rows == reference_rows,
                    "actual_target_rows_match_reference": actual_rows == reference_rows,
                    "actual_matches_planned": actual_rows == planned_rows,
                    "qualified_after_target_build": True,
                }
                reference_owner["full_storage_dimensions"].update(
                    target_full_storage_rows=actual_rows,
                    actual_target_full_storage_rows=actual_rows,
                    planned_target_full_storage_rows=planned_rows,
                    planned_target_rows_match_reference=planned_rows == reference_rows,
                    actual_target_rows_match_reference=actual_rows == reference_rows,
                    target_reference_rows_match=actual_rows == reference_rows,
                    target_budget_status="ACTUAL_TARGET_ROWS_RECORDED",
                )
                factor_audit = reference_owner["factors"].audit
                factor_audit["actual_target_row_identity_check"] = row_identity
                summary["v30_target_reference_row_identity"] = row_identity
                runtime.marker("task40_v30_target_reference_rows_qualified", row_identity)
            if v31_target_admission_policy is not None:
                condensed_build_audit = target_action.condensed.build_audit
                action_buffers = dict(target_action.buffer_inventory)

                def measured_target_owner(
                    byte_count: Any, *, owner_id: str, evidence: str
                ) -> dict[str, Any] | None:
                    if type(byte_count) is not int or byte_count <= 0:
                        return None
                    return {
                        "bytes": byte_count,
                        "status": "measured",
                        "owner_id": owner_id,
                        "evidence": evidence,
                    }

                def unknown_target_owner(*, owner_id: str, evidence: str) -> dict[str, Any]:
                    return {
                        "bytes": None,
                        "status": "unknown",
                        "owner_id": owner_id,
                        "evidence": (
                            evidence
                            + "; opaque/native bytes are covered by the post-build process-tree/cgroup RSS gate"
                        ),
                    }

                local_lu_inventory = measured_target_owner(
                    condensed_build_audit.get("local_lu_factor_cache_bytes_local"),
                    owner_id="target_action.condensed.local_lu",
                    evidence="target_action.condensed.build_audit.local_lu_factor_cache_bytes_local",
                )
                cache_inventory = measured_target_owner(
                    target_identity_cache_audit.get("identity_cache_bytes_local"),
                    owner_id="target_action.condensed.identity_cache",
                    evidence="target_action.condensed.build_audit.identity_cache_bytes_local",
                )
                carrier_inventory = measured_target_owner(
                    action_buffers.get("unique_port_payload_owner_bytes"),
                    owner_id="target_action.carrier_cell_payload",
                    evidence="target_action.buffer_inventory.unique_port_payload_owner_bytes",
                )
                actual_target_owner_inventory = {
                    "mesh_mpc": unknown_target_owner(
                        owner_id="target_levels.mesh_data+floquet.mpc",
                        evidence="current DOLFINx mesh/MPC native backing has no complete per-owner byte inventory",
                    ),
                    "local_lu": local_lu_inventory or unknown_target_owner(
                        owner_id="target_action.condensed.local_lu",
                        evidence="local LU/recovery backing is not completely exposed by the current build audit",
                    ),
                    "cache": cache_inventory or unknown_target_owner(
                        owner_id="target_action.condensed.identity_cache",
                        evidence="identity cache did not expose a positive measured unique-owner byte count",
                    ),
                    "carrier": carrier_inventory or unknown_target_owner(
                        owner_id="target_action.carrier_cell_payload",
                        evidence="carrier buffer inventory did not expose a positive measured unique-owner byte count",
                    ),
                }
                summary["v31_target_owner_actual_inventory"] = (
                    actual_target_owner_inventory
                )
                runtime.marker(
                    "task40_v31_target_owner_actual_inventory",
                    actual_target_owner_inventory,
                )
                reference_rows = (
                    int(reference_owner["full_layout"].full_rows)
                    if reference_owner is not None
                    else None
                )
                actual_rows = int(target_action.condensed.full_rows)
                planned_rows = int(periodic_profile.global_storage_rows)
                checks = mode_identity.get("checks", {})
                future_reserve = _task40_v31_reference_future_reserve(reference_owner)
                target_ready_admission = _task40_v31_target_ready_admission(
                    summary.get("v31_reference_only_admission"),
                    summary.get("v31_target_build_admission"),
                    actual_target_owner_inventory,
                    {
                        "actual_target_full_storage_rows": actual_rows,
                        "planned_target_full_storage_rows": planned_rows,
                        "mode_identity_passed": bool(checks) and all(checks.values()),
                        "map_identity_passed": (
                            checks.get("actual_finalized_mpc_payload_equal") is True
                            and checks.get("actual_carrier_rows_and_values_equal") is True
                        ),
                        "layout_identity_passed": (
                            reference_rows is not None
                            and actual_rows == reference_rows == planned_rows
                        ),
                        "future_reserve": future_reserve,
                    },
                )
                target_ready_resource_admission = allocation_gate(
                    "task40_v31_target_ready_admission",
                    {
                        "additional_payload_bytes": 0,
                        "workspace_bytes": 0,
                        "declared_future_co_resident_bytes": target_ready_admission[
                            "future_co_resident_reserve_bytes"
                        ],
                        "target_admission_phase": "TARGET_READY",
                        "known_unique_payload_bytes_lower_bound": target_ready_admission[
                            "known_unique_payload_bytes_lower_bound"
                        ],
                        "future_reserve": future_reserve,
                    },
                )
                target_ready_admission = _task40_v31_finalize_admission_after_resource_gate(
                    target_ready_admission,
                    target_ready_resource_admission,
                    target_ready_resource_admission.get(
                        "allocation_gate_completion_sample"
                    ),
                )
                summary["v31_target_ready_admission"] = target_ready_admission
                runtime.marker("task40_v31_target_ready_admitted", target_ready_admission)
            target_fast_bundle = build_packed_physical_action(
                {"levels": target_levels, "fine": target_bundle},
                cfg,
                contiguous_work=True,
                preallocated_work=False,
                sum_factorized_work=True,
                reuse_projection_work=False,
                shared_contractions=False,
                fuse_components=True,
                degree=6,
            )
            fast_facts = dict(target_fast_bundle["facts"])
            if (
                fast_facts.get("sum_factorized_work") is not True
                or fast_facts.get("fuse_components") is not True
                or fast_facts.get("backend") != "fused_sum_factorized_split_volume"
            ):
                raise ValueError("candidate target backend did not build the qualified fused sum-factorized action")
            target_backend_facts = {
                "identity": "isotropic_sum_factorized_n1e_v26",
                "component_execution": "fused_sum_factorized_split_volume",
                "selected_for_target_backend_evaluation": True,
                "same_target_forms_and_dtn_carrier": True,
                "physical_action_facts": fast_facts,
                "initial_physical_action_audit": dict(target_fast_bundle["physical_action"].audit),
            }


        if route_contract is None:
            build_target_context()

        qualified_q_csr_provider = _task40_v30_q_csr_provider(
            selector_binding,
            repo_root=_repo_root(),
            allocation_gate=allocation_gate,
            consumer_receipt_directory=directory / "q_csr_consumer_receipts",
            consumer_import_authorizations=(
                v31_q_csr_import_authorizations.get("complete", {})
                if isinstance(v31_q_csr_import_authorizations, Mapping)
                else None
            ),
            numeric_pending_import_authorizations=(
                v31_q_csr_import_authorizations.get("numeric_pending", {})
                if v31_route_facts is not None
                and v31_route_facts.get("review_version") == "V32"
                and isinstance(v31_q_csr_import_authorizations, Mapping)
                else None
            ),
        )
        if qualified_q_csr_provider is not None:
            summary[
                "v31_q_csr_selector" if v31_route_requested else "v30_q_csr_selector"
            ] = {
                "selector_path": str(qualified_q_csr_provider.selector_path),
                "selector_sha256": qualified_q_csr_provider.selector_sha256,
                "profile": qualified_q_csr_provider.profile,
                "selected_q_indices": sorted(qualified_q_csr_provider.entries),
            }

        def load_numeric_checkpoint(path: Path, q: int) -> dict[str, Any]:
            if not path.is_file():
                raise RuntimeError(
                    f"V12 q={q} numeric checkpoint is missing before its follow-up event: {path}"
                )
            saved = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(saved, dict)
                or saved.get("schema") != "task40extra.review_v12_per_q_mumps_stage.v1"
                or not isinstance(saved.get("facts"), dict)
                or int(saved["facts"].get("q", -1)) != q
            ):
                raise RuntimeError(
                    f"V12 q={q} numeric checkpoint has invalid identity or facts: {path}"
                )
            return saved

        def reference_event(name: str, facts: Mapping[str, Any]) -> None:
            if is_v17 and name == "task40_v17_reference_global_ready":
                saved = dict(facts)
                named_arrays = saved.pop("_named_arrays", {})
                saved["global_entity_backing_inventory"] = (
                    _v16_unique_array_owner_inventory(named_arrays)
                )
                saved["stage_resource_sample"] = runtime.sample(
                    "v17_row_tile_reference_global_ready", enforce=False
                )
                runtime.marker(name, saved)
                return
            if is_v17 and name == "task40_v17_q_csr_all_ready":
                saved = dict(facts)
                q_matrices = saved.pop("_q_matrices", {})
                saved["q_matrix_owner_inventory"] = _v16_csr_owner_inventory(
                    q_matrices, version="v17_row_tile"
                )
                saved["stage_resource_sample"] = runtime.sample(
                    "v17_row_tile_q_csr_all_ready_before_symbolic", enforce=False
                )
                runtime.marker(name, saved)
                return
            if is_v17 and name == "task40_v17_p6_sector_ready":
                saved = dict(facts)
                q_matrices = saved.pop("_q_matrices", {})
                saved["q_matrix_owner_inventory"] = _v16_csr_owner_inventory(
                    q_matrices, version="v17_row_tile"
                )
                twist_index = str(saved.get("twist_index", "unknown"))
                saved["stage_resource_sample"] = runtime.sample(
                    f"v17_row_tile_reference_sector{twist_index}_q_csr_ready",
                    enforce=False,
                )
                runtime.marker(name, saved)
                return
            if is_v17 and name in {
                "task40_v12_transform_bank_ready",
                "task40_v10_p6_reference_inverse_ready",
                "task40_v17_q_assembly_comparison_complete",
            }:
                saved = dict(facts)
                label = {
                    "task40_v12_transform_bank_ready": "v17_row_tile_all_spaces_transform_bank_ready",
                    "task40_v10_p6_reference_inverse_ready": "v17_row_tile_reference_inverse_ready",
                    "task40_v17_q_assembly_comparison_complete": "v17_row_tile_q_assembly_comparison_complete",
                }[name]
                saved["stage_resource_sample"] = runtime.sample(label, enforce=False)
                runtime.marker(name, saved)
                return
            if is_v16 and name == "task40_v16_reference_global_ready":
                saved = dict(facts)
                named_arrays = saved.pop("_named_arrays", {})
                saved["global_entity_backing_inventory"] = (
                    _v16_unique_array_owner_inventory(named_arrays)
                )
                saved["stage_resource_sample"] = runtime.sample(
                    "v16_reference_global_ready", enforce=False
                )
                runtime.marker(name, saved)
                return
            if is_v16 and name == "task40_v10_p6_sector_ready":
                saved = dict(facts)
                q_matrices = saved.pop("_q_matrices", {})
                saved["q_matrix_owner_inventory"] = _v16_csr_owner_inventory(
                    q_matrices
                )
                sample_label = (
                    "v16_reference_sector"
                    + str(saved.get("twist_index", "unknown"))
                    + "_q_csr_ready"
                )
                saved["stage_resource_sample"] = runtime.sample(
                    sample_label, enforce=False
                )
                runtime.marker(name, saved)
                return
            if is_v16 and name == "task40_v16_q_csr_all_ready":
                saved = dict(facts)
                q_matrices = saved.pop("_q_matrices", {})
                saved["q_matrix_owner_inventory"] = _v16_csr_owner_inventory(
                    q_matrices
                )
                saved["stage_resource_sample"] = runtime.sample(
                    "v16_q_csr_all_ready_before_symbolic", enforce=False
                )
                runtime.marker(name, saved)
                return
            if is_v16 and name in {
                "task40_v12_transform_bank_ready",
                "task40_v10_p6_reference_inverse_ready",
                "task40_v16_q_assembly_comparison_complete",
            }:
                saved = dict(facts)
                label = {
                    "task40_v12_transform_bank_ready": "v16_all_spaces_transform_bank_ready",
                    "task40_v10_p6_reference_inverse_ready": "v16_reference_inverse_ready",
                    "task40_v16_q_assembly_comparison_complete": "v16_q_assembly_comparison_complete",
                }[name]
                saved["stage_resource_sample"] = runtime.sample(label, enforce=False)
                runtime.marker(name, saved)
                return
            if name == "task40_v12_mumps_symbolic_q_complete":
                q = int(facts["q"])
                facts = dict(facts)
                if is_v16:
                    facts["stage_resource_sample"] = runtime.sample(
                        f"v16_mumps_q{q}_symbolic_complete", enforce=False
                    )
                _write_json(
                    directory / f"task40_v12_p6_q{q}_symbolic.json",
                    {
                        "schema": "task40extra.review_v12_per_q_mumps_stage.v1",
                        "event": name,
                        "case": case_label,
                        "source_sha": source_sha,
                        "facts": facts,
                    },
                )
                runtime.marker(name, facts)
                return
            if name == "task40_v12_mumps_numeric_q_complete":
                q = int(facts["q"])
                facts = dict(facts)
                if is_v16:
                    facts["stage_resource_sample"] = runtime.sample(
                        f"v16_mumps_q{q}_numeric_complete", enforce=False
                    )
                _write_json(
                    directory / f"task40_v12_p6_q{q}_numeric.json",
                    {
                        "schema": "task40extra.review_v12_per_q_mumps_stage.v1",
                        "event": name,
                        "case": case_label,
                        "source_sha": source_sha,
                        "facts": facts,
                    },
                )
                runtime.marker(name, facts)
                return
            if name == "task40_v12_mumps_numeric_q_probe_complete":
                q = int(facts["q"])
                path = directory / f"task40_v12_p6_q{q}_numeric.json"
                probe_facts = dict(facts)
                try:
                    sample = runtime.sample(f"v12_mumps_q{q}_after_probe", enforce=False)
                    probe_facts["process_tree_rss_bytes"] = int(sample["rss_bytes"])
                    probe_facts["process_tree_rss_sample"] = sample
                except Exception as error:
                    probe_facts["process_tree_rss_bytes"] = None
                    probe_facts["process_tree_rss_sample_error"] = {
                        "type": type(error).__name__, "message": str(error)
                    }
                saved = load_numeric_checkpoint(path, q)
                saved["probe"] = probe_facts
                saved["last_event"] = name
                _write_json(path, saved)
                runtime.marker(name, probe_facts)
                return
            if name == "task40_v12_mumps_numeric_q_admitted":
                q = int(facts["q"])
                path = directory / f"task40_v12_p6_q{q}_numeric.json"
                saved = load_numeric_checkpoint(path, q)
                saved["resource_gate"] = facts
                saved["last_event"] = name
                saved["facts"]["process_tree_rss_bytes"] = facts.get(
                    "process_tree_rss_bytes"
                )
                saved["facts"]["numeric_true_residual"] = facts.get(
                    "numeric_true_residual"
                )
                saved["facts"]["native_metrics"] = facts.get("native_metrics")
                if saved.get("probe") is not None:
                    saved["probe"]["process_tree_rss_bytes"] = facts.get(
                        "process_tree_rss_bytes"
                    )
                    saved["probe"]["native_metrics"] = facts.get("native_metrics")
                _write_json(path, saved)
                runtime.marker(name, facts)
                return
            if name == "task40_v12_mumps_all_q_live_before_destroy":
                snapshot = dict(facts)
                try:
                    sample = runtime.sample("v12_all_q_live_before_destroy", enforce=False)
                    snapshot["process_tree_rss_bytes"] = int(sample["rss_bytes"])
                    snapshot["process_tree_rss_sample"] = sample
                except Exception as error:
                    snapshot["process_tree_rss_bytes"] = None
                    snapshot["process_tree_rss_sample_error"] = {
                        "type": type(error).__name__, "message": str(error)
                    }
                _write_json(
                    directory / "task40_v12_p6_all_q_live_before_destroy.json",
                    {
                        "schema": "task40extra.review_v12_all_q_live_before_destroy.v1",
                        "case": case_label,
                        "source_sha": source_sha,
                        "facts": snapshot,
                    },
                )
                runtime.marker(name, snapshot)
                return
            runtime.marker(name, facts)

        runtime.sample("v10_candidate_target_retained_and_fast_backend_complete")

        operator_qualification_reuse = None
        if is_v18:
            if is_v19:
                from src.solvers.task40_v18_ny8_operator_reuse import (
                    reuse_ny8_operator_qualification_certificate,
                )

                reuse_function = reuse_ny8_operator_qualification_certificate
                operator_reuse_receipt_path = (
                    Path(_repo_root())
                    / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/"
                    "v19_ny8_operator_reuse_receipt.json"
                )
            else:
                from src.solvers.task40_v18_ny8_operator_reuse import (
                    reuse_v18_ny8_operator_qualification,
                )

                reuse_function = reuse_v18_ny8_operator_qualification
                operator_reuse_receipt_path = (
                    Path(_repo_root())
                    / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/"
                    "v18_ny8_operator_reuse_receipt.json"
                )
            operator_reuse_receipt_sha256_path = operator_reuse_receipt_path.with_suffix(
                ".sha256"
            )

            def operator_qualification_reuse(*, candidate_q_matrices, profile):
                expected_receipt_sha256 = (
                    operator_reuse_receipt_sha256_path.read_text(encoding="ascii").strip()
                )
                return reuse_function(
                    repo_root=_repo_root(),
                    receipt_path=operator_reuse_receipt_path,
                    candidate_q_matrices=candidate_q_matrices,
                    profile=profile,
                    source_sha=source_sha,
                    input_sha256=scientific_input_sha256,
                    physical_model_sha256=str(
                        resolved_payload.get("provenance", {}).get(
                            "physical_model_sha256", ""
                        )
                    ),
                    target_mode_sha256=str(v20_mode_inventory[2]),
                    abi_identity=summary["abi"],
                    expected_receipt_sha256=expected_receipt_sha256,
                )

        if qualified_q_csr_provider is not None:
            provenance = resolved_payload.get("provenance", {})
            campaign_identity = summary.get("campaign_authority", {})
            if (
                not isinstance(provenance, Mapping)
                or not isinstance(campaign_identity, Mapping)
                or not isinstance(v20_mode_metadata, Mapping)
                or v20_mode_inventory is None
                or len(v20_mode_inventory) != 3
            ):
                raise ValueError("V30 q-CSR injection lacks input, campaign, or frozen mode identity")
            input_sha256 = scientific_input_sha256
            physical_sha256 = str(provenance.get("physical_model_sha256", ""))
            if v20_mode_inventory is None or len(v20_mode_inventory) != 3:
                raise ValueError("V30 reference-first q-CSR binding lacks the frozen mode inventory")
            mode_manifest_sha256 = str(v20_mode_inventory[2])
            ordered_mode_key_sha256 = str(
                v20_mode_metadata.get("ordered_mode_key_sha256", "")
            )
            window_sha256 = str(campaign_identity.get("campaign_window_sha256", ""))
            if any(
                len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in (
                    input_sha256,
                    physical_sha256,
                    mode_manifest_sha256,
                    ordered_mode_key_sha256,
                    window_sha256,
                )
            ):
                raise ValueError("V30 q-CSR runtime identity has an invalid SHA-256 field")
            from src.solvers.task40_v30_qualified_q_csr import (
                V28_Q0_CSR_MANIFEST_SHA256,
                V28_Q0_DONOR_INPUT_SHA256,
                V28_Q0_NATIVE_QUALIFICATION_SHA256,
            )

            qualified_q_csr_identity = {
                "scientific_input_sha256": input_sha256,
                "ordered_mode_key_sha256": ordered_mode_key_sha256,
                "execution_identity": {
                    "source_sha": source_sha,
                    "window_sha256": window_sha256,
                },
                "legacy_q0_identity": {
                    "input_sha256": V28_Q0_DONOR_INPUT_SHA256,
                    "physical_model_sha256": physical_sha256,
                    "mode_manifest_sha256": mode_manifest_sha256,
                    "manifest_sha256": V28_Q0_CSR_MANIFEST_SHA256,
                    "native_qualification_sha256": V28_Q0_NATIVE_QUALIFICATION_SHA256,
                },
            }

        qualified_q_csr_coverage_phase = "all_q"
        qualified_q_csr_preparer = None
        q4_saved_numeric_prebuild: Mapping[str, Any] | None = None
        prebuilt_twist0_q_csr: tuple[Mapping[int, Any], Mapping[str, Any]] | None = None
        if qualified_q_csr_provider is not None:
            preparation = route_contract.get("preparation", {})
            worklist = preparation.get("q_csr_worklist") if isinstance(preparation, Mapping) else None
            if not isinstance(worklist, list) or not worklist:
                raise ValueError("V30/V31 contract has no approved q CSR preparation worklist")
            approved_preparation_q = {0}
            for row in worklist:
                if not isinstance(row, Mapping) or type(row.get("q")) is not int:
                    raise ValueError("V30/V31 q CSR preparation worklist is malformed")
                approved_preparation_q.add(int(row["q"]))
            if not set(qualified_q_csr_provider.entries) <= approved_preparation_q:
                raise ValueError("V30/V31 selector includes a q outside the accepted donor and worklist")
            qualified_q_csr_coverage_phase = "sector_preparation_subset"
            q4_source_cache: dict[str, Any] = {}
            q4_saved_numeric_prebuild: Mapping[str, Any] | None = None
            prebuilt_twist0_q_csr = None

            def prepare_v30_sector_q_csr(
                *,
                provider,
                action,
                volume_action,
                coordinates,
                context,
                local_h,
                profile,
                global_bundle,
                local_bundle,
                mode_inventory,
                q_indices,
                available_sector_matrices,
                runtime_identity,
                allocation_gate,
                prebuilt_q_maps_by_q=None,
            ):
                from src.solvers.task40_v30_selected_q_csr import (
                    LiveP6SelectedQContributionSource,
                    prepare_selected_q_csr_sector,
                    selected_q_operator_identity,
                )

                sector_qs = tuple(map(int, context.global_q_indices))
                q_maps_by_q = _task40_v30_resolve_sector_q_maps(
                    coordinates,
                    sector_qs,
                    allocation_gate=allocation_gate,
                    prebuilt_q_maps_by_q=prebuilt_q_maps_by_q,
                )
                if v20_mode_inventory is None:
                    raise ValueError("V30 sector callback lacks the frozen mode inventory")
                sector_builder_inputs = _task40_v30_sector_builder_inputs(
                    global_bundle=global_bundle,
                    mode_inventory=v20_mode_inventory,
                    coordinates=coordinates,
                    profile=profile,
                    q_maps_by_q=q_maps_by_q,
                    sector_q_indices=sector_qs,
                )
                sources_by_q = {}
                matrix_source_identity_by_q = {}
                producer_identity_by_q = {}
                current_h = np.asarray(local_h, dtype=np.complex128)
                donor_facts = None
                precomputed_numeric_by_q = {}
                if 4 in q_indices:
                    if context.twist_index != 0 or sector_qs != (0, 4):
                        raise ValueError("V30 q4 saved donor may only serve the real twist-0 pair")
                    if not q4_source_cache:
                        raise ValueError(
                            "V31 q4 reached its live sector without the saved-first numeric pending"
                        )
                    donor_binding = _task40_v31_bind_saved_q4_to_live(
                        q4_source_cache,
                        current_q0_map=q_maps_by_q[0],
                        current_q4_map=q_maps_by_q[4],
                        current_local_h=current_h,
                        current_trace_constraints=action.condensed.trace_constraints,
                        current_full_rows=int(action.condensed.full_rows),
                        allocation_gate=allocation_gate,
                    )
                    q_maps_by_q[4] = q4_source_cache["q4_map"]
                    sources_by_q[4] = q4_source_cache["source"]
                    donor_facts = q4_source_cache["producer_facts"]
                    matrix_source_identity_by_q[4] = {
                        "source_sha": donor_facts["producer_source_sha"],
                        "window_sha256": donor_facts["producer_window_sha256"],
                    }
                    producer_identity_by_q[4] = dict(donor_facts)
                    if q4_saved_numeric_prebuild is None:
                        raise ValueError("V31 q4 numeric pending is missing at native qualification")
                    precomputed_numeric_by_q[4] = q4_saved_numeric_prebuild
                live_source = LiveP6SelectedQContributionSource(action, current_h)
                for q in q_indices:
                    if int(q) == 4:
                        continue
                    sources_by_q[int(q)] = live_source
                    matrix_source_identity_by_q[int(q)] = dict(
                        runtime_identity["execution_identity"]
                    )
                    producer_identity_by_q[int(q)] = {
                        "kind": "live_same_mesh_twist_sector_action",
                        "twist_index": int(context.twist_index),
                        "sector_q_indices": list(sector_qs),
                        "source_sha": runtime_identity["execution_identity"]["source_sha"],
                        "window_sha256": runtime_identity["execution_identity"][
                            "window_sha256"
                        ],
                        "ordered_mode_manifest_sha256": sector_builder_inputs[
                            "mode_manifest_sha256"
                        ],
                        "original_h_sha256": _sha256_bytes(
                            np.ascontiguousarray(current_h).view(np.uint8).tobytes()
                        ),
                    }
                operator_identity_by_q = {
                    int(q): selected_q_operator_identity(
                        scientific_input_sha256=str(
                            runtime_identity["scientific_input_sha256"]
                        ),
                        profile_identity=profile.identity(),
                        ordered_modes=tuple(global_bundle["modes"]),
                        q_map=q_maps_by_q[int(q)],
                        original_h=current_h,
                    )
                    for q in q_indices
                }
                saved_native_witness_by_q = {}
                direct_hhat_evidence_by_q = {}
                if 4 in map(int, q_indices):
                    direct_hhat_evidence_by_q[4] = q4_source_cache[
                        "direct_hhat_evidence"
                    ]
                    saved_native_witness_by_q[4] = _task40_v30_open_saved_q4_native_witness(
                        contract=route_contract,
                        repo_root=_repo_root(),
                        operator_identity=operator_identity_by_q[4],
                        current_execution_identity=runtime_identity["execution_identity"],
                        input_sha256=str(runtime_identity["scientific_input_sha256"]),
                        physical_model_sha256=physical_sha256,
                        mode_manifest_sha256=str(v20_mode_inventory[2]),
                        ordered_mode_key_sha256=ordered_mode_key_sha256,
                        allocation_gate=allocation_gate,
                    )
                matrices, audit = prepare_selected_q_csr_sector(
                    sources_by_q=sources_by_q,
                    q_maps_by_q=q_maps_by_q,
                    sector_q_indices=sector_qs,
                    twist_index=int(context.twist_index),
                    trace_rows_by_q=sector_builder_inputs["trace_rows_by_q"],
                    selected_q_indices=tuple(map(int, q_indices)),
                    action=action,
                    volume_action=volume_action,
                    comm=action.condensed.comm,
                    available_sector_matrices=available_sector_matrices,
                    allocation_gate=allocation_gate,
                    profile=str(profile.name),
                    profile_identity=profile.identity(),
                    ordered_modes=tuple(global_bundle["modes"]),
                    original_h=current_h,
                    scientific_input_sha256=str(
                        runtime_identity["scientific_input_sha256"]
                    ),
                    operator_identity_by_q=operator_identity_by_q,
                    matrix_source_identity_by_q=matrix_source_identity_by_q,
                    execution_identity=dict(runtime_identity["execution_identity"]),
                    producer_identity_by_q=producer_identity_by_q,
                    saved_native_witness_by_q=saved_native_witness_by_q,
                    direct_hhat_evidence_by_q=direct_hhat_evidence_by_q,
                    precomputed_numeric_by_q=precomputed_numeric_by_q,
                    output_directory=(
                        Path(str(factor_config["output_directory"])) / "selected_q"
                    ),
                )
                if donor_facts is not None:
                    audit["q4_saved_producer_identity"] = donor_facts
                    audit["q4_direct_hhat_support_evidence"] = direct_hhat_evidence_by_q[4]
                    audit["q4_saved_live_binding"] = donor_binding
                return matrices, audit

            qualified_q_csr_preparer = prepare_v30_sector_q_csr

        def v31_phase_start(phase: str, **facts: Any) -> int | None:
            if not v31_route_requested:
                return None
            started_ns = time.time_ns()
            runtime.marker(
                f"{phase}_phase_started",
                {
                    "schema": "task40extra.review_v31_worker_phase_event.v1",
                    "phase": phase,
                    "status": "STARTED",
                    "started_utc_ns": started_ns,
                    **facts,
                },
            )
            return started_ns

        def v31_phase_end(
            phase: str,
            started_ns: int | None,
            *,
            status: str,
            **facts: Any,
        ) -> None:
            if started_ns is None:
                return
            finished_ns = time.time_ns()
            runtime.marker(
                f"{phase}_phase_completed",
                {
                    "schema": "task40extra.review_v31_worker_phase_event.v1",
                    "phase": phase,
                    "status": status,
                    "started_utc_ns": started_ns,
                    "finished_utc_ns": finished_ns,
                    "elapsed_seconds": max(0.0, (finished_ns - started_ns) / 1.0e9),
                    **facts,
                },
            )

        def v32_owner_stage_event(event: Mapping[str, Any]) -> None:
            if not isinstance(v31_route_facts, Mapping) or v31_route_facts.get("review_version") != "V32":
                return
            phase = str(event.get("phase", "unknown"))
            status = str(event.get("status", "unknown")).lower()
            runtime.marker(
                f"task40_v32_owner_{phase}_{status}",
                {
                    "schema": "task40extra.review_v32_owner_phase_event.v1",
                    "attempt_id": directory.name,
                    "run_id": getattr(runtime, "run_id", None),
                    "execution_identity": dict(
                        qualified_q_csr_identity.get("execution_identity", {})
                        if isinstance(qualified_q_csr_identity, Mapping)
                        else {}
                    ),
                    **dict(event),
                },
            )

        def v31_write_product(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
            if not v31_route_requested:
                raise RuntimeError("V31 product receipt cannot be written outside the V31 route")
            path = directory / name
            _write_json(path, payload)
            raw = path.read_bytes()
            return {
                "schema": "task40extra.review_v31_worker_product_receipt.v1",
                "path": path.relative_to(directory).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }

        def prepare_saved_q4_numeric_before_reference() -> Mapping[str, Any]:
            if (
                route_contract is None
                or factor_config is None
                or not isinstance(qualified_q_csr_identity, Mapping)
                or v20_mode_inventory is None
                or len(v20_mode_inventory) != 3
            ):
                raise ValueError("V31 saved-first q4 lacks its frozen contract or mode inventory")
            from src.solvers.task40_v30_selected_q_csr import (
                prepare_saved_selected_q_numeric_pending,
                preflight_v32_q4_numeric_pending_import,
                selected_q_operator_identity,
            )

            v32_q4_import = None
            import_output_root = (
                Path(str(factor_config["output_directory"]))
                / "selected_q" / "q4_twist0"
            ).resolve()
            if isinstance(v31_route_facts, Mapping) and v31_route_facts.get("review_version") == "V32":
                v32_q4_import = v31_route_facts.get(
                    "q4_numeric_pending_import_authorization"
                )
                if not isinstance(v32_q4_import, Mapping):
                    raise ValueError(
                        "V32 q4 require-existing authorization is missing before opening the saved donor"
                    )
                preflight_v32_q4_numeric_pending_import(
                    v32_q4_import,
                    profile=str(periodic_profile.name),
                    execution_identity=dict(
                        qualified_q_csr_identity["execution_identity"]
                    ),
                    output_directory=import_output_root,
                )

            donor = _task40_v30_open_saved_q4_source(
                contract=route_contract,
                repo_root=_repo_root(),
                profile=periodic_profile,
                allocation_gate=allocation_gate,
                return_saved_inputs=True,
            )
            q4_map = donor["q4_map"]
            q4_trace_rows = int(q4_map.shape[1]) - int(periodic_profile.q_port_counts[4])
            if q4_trace_rows != int(periodic_profile.trace_rows_per_q):
                raise ValueError("saved q4 map columns do not match its actual trace/port split")
            operator_identity = selected_q_operator_identity(
                scientific_input_sha256=str(
                    qualified_q_csr_identity["scientific_input_sha256"]
                ),
                profile_identity=periodic_profile.identity(),
                ordered_modes=tuple(v20_mode_inventory[0]),
                q_map=q4_map,
                original_h=donor["original_h"],
            )
            producer_facts = dict(donor["producer_facts"])
            direct_hhat_evidence = _task40_v30_q4_direct_hhat_evidence(
                repo_root=_repo_root(), producer_facts=producer_facts
            )
            donor["direct_hhat_evidence"] = direct_hhat_evidence
            matrix_source_identity = {
                "source_sha": producer_facts["producer_source_sha"],
                "window_sha256": producer_facts["producer_window_sha256"],
            }
            numeric_stage = prepare_saved_selected_q_numeric_pending(
                source=donor["source"],
                q_map=q4_map,
                q_index=4,
                twist_index=0,
                trace_rows=q4_trace_rows,
                allocation_gate=allocation_gate,
                profile=str(periodic_profile.name),
                operator_identity=operator_identity,
                matrix_source_identity=matrix_source_identity,
                execution_identity=dict(qualified_q_csr_identity["execution_identity"]),
                producer_identity=producer_facts,
                output_directory=import_output_root,
                direct_hhat_evidence=direct_hhat_evidence,
                consumer_import_authorization=(
                    v31_q_csr_import_authorizations.get("numeric_pending", {}).get("4")
                    if v32_q4_import is None
                    and isinstance(v31_q_csr_import_authorizations, Mapping)
                    and isinstance(v31_q_csr_import_authorizations.get("numeric_pending", {}), Mapping)
                    else None
                ),
                numeric_pending_import_authorization=v32_q4_import,
            )
            if numeric_stage.get("status") != "NUMERIC_COMPLETE_NATIVE_PENDING":
                raise RuntimeError("saved-first q4 did not reach durable numeric-pending")
            q4_source_cache.update(donor)
            pending_record = numeric_stage["numeric_pending"]
            runtime.marker(
                "task40_v31_q4_numeric_pending_complete",
                {
                    "q_index": 4,
                    "twist_index": 0,
                    "pending_record": pending_record.get("record_path"),
                    "pending_sha256": pending_record.get("record_sha256"),
                    "shape": list(numeric_stage["matrix"].shape),
                    "stored_structural_slots": int(numeric_stage["matrix"].nnz),
                    "reopened_existing_pending": bool(numeric_stage.get("reopened", False)),
                    "global_reference_builder_started": False,
                    "native_or_factor_started": False,
                    "numeric_pending_import_execution": numeric_stage.get(
                        "numeric_pending_import_execution"
                    ),
                },
            )
            return {**numeric_stage, "saved_donor": donor}

        def prepare_saved_q4_with_phase() -> Mapping[str, Any]:
            phase = "task40_v31_q4_saved_numeric_pending"
            started_ns = v31_phase_start(
                phase,
                q_index=4,
                twist_index=0,
                native_or_factor_started=False,
                global_reference_builder_started=False,
            )
            try:
                result = prepare_saved_q4_numeric_before_reference()
            except BaseException as error:
                v31_phase_end(
                    phase,
                    started_ns,
                    status="FAILED",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                raise
            record = result.get("numeric_pending", {})
            v31_phase_end(
                phase,
                started_ns,
                status="COMPLETE",
                q_index=4,
                twist_index=0,
                product_path=record.get("record_path"),
                product_sha256=record.get("record_sha256"),
                reopened_existing_pending=bool(result.get("reopened", False)),
            )
            return result

        def prepare_twist0_owner_with_phase(
            pending: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            numeric_pending = pending.get("numeric_pending", {})
            phase = "task40_v31_twist0_owner_prebuild"
            started_ns = v31_phase_start(
                phase,
                q4_pending_path=numeric_pending.get("record_path"),
                q4_pending_sha256=numeric_pending.get("record_sha256"),
                global_reference_builder_started=False,
            )
            try:
                owner = prepare_twist0_owner_before_global(pending)
            except BaseException as error:
                v31_phase_end(
                    phase,
                    started_ns,
                    status="FAILED",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                raise
            receipt = dict(owner.get("owner_receipt", {}))
            if v31_route_requested:
                product = v31_write_product(
                    "v31_twist0_owner_receipt.json",
                    {
                        "schema": "task40extra.review_v31_twist0_owner_product.v1",
                        "source_sha": source_sha,
                        "run_id": resolved_payload.get("run_id"),
                        "input_sha256": scientific_input_sha256,
                        "owner_receipt": receipt,
                    },
                )
                receipt["owner_receipt_product"] = product
                owner.setdefault("owner_receipt", {}).update(
                    owner_receipt_product=product
                )
            v31_phase_end(
                phase,
                started_ns,
                status="COMPLETE",
                owner_receipt=receipt,
                q4_pending_path=numeric_pending.get("record_path"),
                q4_pending_sha256=numeric_pending.get("record_sha256"),
            )
            return owner

        def prepare_twist0_owner_before_global(
            pending: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            nonlocal q4_saved_numeric_prebuild, prebuilt_twist0_owner, prebuilt_twist0_q_csr
            if (
                pending.get("status") != "NUMERIC_COMPLETE_NATIVE_PENDING"
                or not isinstance(pending.get("saved_donor"), Mapping)
                or not isinstance(v20_mode_inventory, tuple)
                or len(v20_mode_inventory) != 3
                or qualified_q_csr_provider is None
                or 0 not in qualified_q_csr_provider.entries
            ):
                raise ValueError(
                    "V31 twist-0 handoff requires durable q4 pending, frozen modes, and accepted q0"
                )
            q4_saved_numeric_prebuild = pending
            donor = pending["saved_donor"]
            frozen_modes, frozen_rows, frozen_mode_sha = v20_mode_inventory
            regular_cfg = __import__("dataclasses").replace(
                cfg,
                air_void_box_nm=None,
                cell_notch=None,
                geometry_identity="task40_v10_p6_reference.regular_reference",
            )
            contexts = build_task40_v10_sector_contexts(
                tuple(frozen_modes),
                regular_cfg,
                axes,
                expected_q_counts=periodic_profile.q_port_counts,
                expected_sector_counts=periodic_profile.sector_port_counts,
            )
            context = next(
                (row for row in contexts if int(row.twist_index) == 0), None
            )
            if context is None or tuple(context.global_q_indices) != (0, 4):
                raise ValueError("V31 frozen inventory does not identify the real twist-0 (q0,q4) pair")
            saved_local_h = np.asarray(donor.get("original_h"), dtype=np.complex128)
            selected_modes = np.asarray(context.original_mode_indices, dtype=np.int64)
            if (
                len(frozen_modes) != int(periodic_profile.mode_count)
                or len(frozen_rows) != len(frozen_modes)
                or selected_modes.ndim != 1
                or len(np.unique(selected_modes)) != len(selected_modes)
                or np.any(selected_modes < 0)
                or np.any(selected_modes >= len(frozen_modes))
                or saved_local_h.shape != selected_modes.shape
                or not np.isfinite(saved_local_h).all()
                or not np.all(saved_local_h.imag == 0.0)
                or np.any(saved_local_h.real <= 0.0)
            ):
                raise ValueError(
                    "V31 saved q4 donor does not carry finite positive twist-0 local H "
                    "for the frozen selected mode indices"
                )
            global_h = np.fromiter(
                (
                    assembly_projection_denominator(mode, regular_cfg, BOUNDARY_PLANE)
                    for mode in frozen_modes
                ),
                dtype=np.float64,
                count=len(frozen_modes),
            )
            if (
                global_h.shape != (int(periodic_profile.mode_count),)
                or not np.isfinite(global_h).all()
                or np.any(global_h <= 0.0)
            ):
                raise ValueError("V31 frozen mode table did not produce finite positive global H")
            global_h_sha256 = hashlib.sha256(
                np.ascontiguousarray(global_h).view(np.uint8)
            ).hexdigest()
            saved_port_owner = None
            saved_stage_callback = None
            if isinstance(v31_route_facts, Mapping) and v31_route_facts.get("review_version") == "V32":
                producer_facts = donor.get("producer_facts", {})
                support_evidence = donor.get("direct_hhat_evidence", {})
                if not isinstance(producer_facts, Mapping) or not isinstance(
                    support_evidence, Mapping
                ):
                    raise ValueError(
                        "V32 saved-port owner source differs from the accepted V26 stream identity"
                    )
                execution_root = Path(_repo_root()).resolve()
                resolve_path = _task40_v30_artifact_path_resolver(execution_root)
                surface_path = resolve_path(str(donor.get("surface_stream_path", "")))
                support_surface_path = resolve_path(
                    str(support_evidence.get("surface_stream_path", ""))
                )
                raw_support_surface_path = support_evidence.get("surface_stream_path_raw")
                surface_hash = str(support_evidence.get("surface_stream_sha256", ""))
                if (
                    not surface_path.is_relative_to(execution_root)
                    or not support_surface_path.is_relative_to(execution_root)
                    or not isinstance(raw_support_surface_path, str)
                    or not raw_support_surface_path
                    or resolve_path(raw_support_surface_path) != support_surface_path
                    or surface_path != support_surface_path
                    or surface_hash
                    != producer_facts.get("payload_sha256", {}).get(
                        "v25_selected_q0_surface_functionals.bin"
                    )
                    or not isinstance(producer_facts.get("producer_identity_sha256"), str)
                ):
                    raise ValueError("V32 saved-port owner source differs from the accepted V26 stream identity")
                saved_port_owner = {
                    "surface_stream_path": str(surface_path),
                    "surface_stream_sha256": surface_hash,
                    "active_lookup_path": str(donor["active_lookup_path"]),
                    "q0_map": donor["q0_map"],
                    "q4_map": donor["q4_map"],
                    "original_h": donor["original_h"],
                    "direct_hhat_evidence": dict(support_evidence),
                    "producer_identity_sha256": str(
                        producer_facts["producer_identity_sha256"]
                    ),
                }
                saved_stage_callback = v32_owner_stage_event
            local_owner = build_task40_v10_p6_local_sector_owner(
                cfg,
                axes,
                context=context,
                global_modes=tuple(frozen_modes),
                global_mode_rows=tuple(frozen_rows),
                global_mode_sha256=str(frozen_mode_sha),
                global_h=global_h,
                profile=periodic_profile,
                allocation_gate=allocation_gate,
                jit_options=SAME_MESH_JIT_OPTIONS,
                share_transform_bank=share_transform_bank,
                saved_port_owner=saved_port_owner,
                stage_callback=saved_stage_callback,
            )
            prebuilt_twist0_owner = local_owner
            local_owner.setdefault("owner_receipt", {}).update(
                handover_status="TWIST0_LOCAL_OWNER_AWAITING_Q4_NATIVE",
                global_reference_builder_started=False,
            )
            owner_local_h = np.asarray(local_owner.get("local_h"), dtype=np.float64)
            if (
                owner_local_h.shape != saved_local_h.shape
                or not np.array_equal(
                    saved_local_h,
                    np.asarray(owner_local_h, dtype=np.complex128),
                )
                or local_owner.get("global_h_sha256") != global_h_sha256
            ):
                raise ValueError(
                    "V31 saved local H, prepared owner local H, and frozen global H carrier identity differ"
                )
            local_y_span_nm = float(
                context.local_axes["y"][-1] - context.local_axes["y"][0]
            )
            global_y_span_nm = float(cfg.period_y)
            local_owner.setdefault("owner_receipt", {}).update(
                global_h_source="frozen_mode_table_boundary_plane_projection_denominator",
                global_h_mode_count=int(global_h.size),
                global_h_sha256=global_h_sha256,
                saved_local_h_count=int(saved_local_h.size),
                saved_local_h_sha256=hashlib.sha256(
                    np.ascontiguousarray(saved_local_h).view(np.uint8)
                ).hexdigest(),
                prepared_local_h_sha256=hashlib.sha256(
                    np.ascontiguousarray(owner_local_h).view(np.uint8)
                ).hexdigest(),
                local_h_matches_saved_owner_exactly=True,
                global_h_bound_to_current_carrier_identity=True,
                local_to_global_y_span_ratio_diagnostic=(
                    local_y_span_nm / global_y_span_nm
                    if global_y_span_nm > 0.0
                    else None
                ),
                local_y_span_nm=local_y_span_nm,
                global_y_span_nm=global_y_span_nm,
                y_span_ratio_is_diagnostic_only=True,
            )
            runtime.marker(
                "task40_v31_twist0_local_owner_prebuilt",
                {
                    **dict(local_owner.get("owner_receipt", {})),
                    "pending_record": pending.get("numeric_pending", {}).get("record_path"),
                    "pending_sha256": pending.get("numeric_pending", {}).get("record_sha256"),
                    "global_reference_builder_started": False,
                    "q4_native_started": False,
                },
            )

            prebuilt_q_maps_by_q = _task40_v32_owner_bound_q_maps(
                v31_route_facts, local_owner
            )
            if prebuilt_q_maps_by_q is not None:
                q_maps_by_q = prebuilt_q_maps_by_q
            else:
                q_maps_by_q = {
                    q: local_owner["coordinates"].q_map(
                        branch, allocation_gate=allocation_gate
                    )
                    for branch, q in enumerate(context.global_q_indices)
                }
            donor_binding = _task40_v31_bind_saved_q4_to_live(
                donor,
                current_q0_map=q_maps_by_q[0],
                current_q4_map=q_maps_by_q[4],
                current_local_h=np.asarray(local_owner["local_h"], dtype=np.complex128),
                current_trace_constraints=local_owner["action"].condensed.trace_constraints,
                current_full_rows=int(local_owner["action"].condensed.full_rows),
                allocation_gate=allocation_gate,
            )
            frozen_bundle_identity = {
                "modes": tuple(frozen_modes),
                "mode_rows": tuple(frozen_rows),
                "mode_sha256": str(frozen_mode_sha),
            }
            provider_q_indices = {0}
            if (
                isinstance(v31_route_facts, Mapping)
                and v31_route_facts.get("review_version") == "V32"
                and 4 in qualified_q_csr_provider.entries
            ):
                provider_q_indices.add(4)
            provider_matrices, provider_audit = _task40_v30_load_sector_q_csr_pair(
                qualified_q_csr_provider,
                action=local_owner["action"],
                coordinates=local_owner["coordinates"],
                context=context,
                local_h=np.asarray(local_owner["local_h"], dtype=np.float64),
                profile=periodic_profile,
                global_bundle=frozen_bundle_identity,
                mode_inventory=local_owner["mode_inventory"],
                runtime_identity=qualified_q_csr_identity,
                allocation_gate=allocation_gate,
                selected_q_indices=provider_q_indices,
                prebuilt_q_maps_by_q=prebuilt_q_maps_by_q,
            )
            if set(provider_matrices) != provider_q_indices:
                raise ValueError("V31 twist-0 handoff did not reopen exactly its authorized provider q set")
            missing_q = set(map(int, context.global_q_indices)) - set(provider_matrices)
            if not missing_q <= {4}:
                raise ValueError("V31 twist-0 preparation would repeat an already accepted q native route")
            preparation_audit: Mapping[str, Any] = {}
            prepared_matrices: Mapping[int, Any] = {}
            if missing_q:
                if missing_q != {4} or not callable(qualified_q_csr_preparer):
                    raise ValueError("V31 twist-0 q4 native preparer is unavailable")
                native_phase = "task40_v31_twist0_q4_native"
                native_started_ns = v31_phase_start(
                    native_phase,
                    q_indices=[4],
                    twist_index=0,
                    global_reference_builder_started=False,
                    numeric_factor_started=False,
                )
                try:
                    prepared_matrices, preparation_audit = qualified_q_csr_preparer(
                        provider=qualified_q_csr_provider,
                        action=local_owner["action"],
                        volume_action=local_owner["bundle"]["volume_action"],
                        coordinates=local_owner["coordinates"],
                        context=context,
                        local_h=np.asarray(local_owner["local_h"], dtype=np.float64),
                        profile=periodic_profile,
                        global_bundle=frozen_bundle_identity,
                        local_bundle=local_owner["bundle"],
                        mode_inventory=local_owner["mode_inventory"],
                        q_indices=(4,),
                        available_sector_matrices=provider_matrices,
                        runtime_identity=qualified_q_csr_identity,
                        allocation_gate=allocation_gate,
                        prebuilt_q_maps_by_q=q_maps_by_q,
                    )
                except BaseException as error:
                    v31_phase_end(
                        native_phase,
                        native_started_ns,
                        status="FAILED",
                        error_type=type(error).__name__,
                        error_message=str(error),
                    )
                    raise
                v31_phase_end(
                    native_phase,
                    native_started_ns,
                    status="COMPLETE",
                    q_indices=sorted(map(int, prepared_matrices)),
                    qualification_receipt_count=len(
                        preparation_audit.get("qualification_receipts", ())
                    ),
                    selector_entry_count=len(preparation_audit.get("selector_entries", ())),
                )
            all_matrices, merged_audit = _task40_v31_merge_twist0_q_csr_audit(
                provider_matrices,
                provider_audit,
                prepared_matrices,
                preparation_audit,
                donor_binding=donor_binding,
            )
            prebuilt_twist0_q_csr = (all_matrices, merged_audit)
            local_owner["owner_receipt"].update(
                handover_status="PREPARED_FOR_GLOBAL_REFERENCE",
                q4_saved_live_binding=donor_binding,
                q4_native_status="PASS",
                q4_selector_entry=next(
                    row for row in merged_audit["selector_entries"] if int(row.get("q_index", -1)) == 4
                ),
                global_reference_builder_started=False,
            )
            runtime.marker(
                "task40_v31_twist0_q4_native_complete",
                dict(local_owner["owner_receipt"]),
            )
            return local_owner

        def build_reference_from_saved_q4(
            pending: Mapping[str, Any] | None,
            prepared_owner: Mapping[str, Any] | None = None,
        ) -> Any:
            nonlocal q4_saved_numeric_prebuild
            q4_saved_numeric_prebuild = pending
            if isinstance(prepared_owner, dict):
                prepared_owner.setdefault("owner_receipt", {}).update(
                    handover_status="REFERENCE_BUILDER_RECEIVED_OWNER",
                    global_reference_builder_started=True,
                )
                runtime.marker(
                    "task40_v31_twist0_owner_handed_to_reference",
                    dict(prepared_owner["owner_receipt"]),
                )
            reference_phase = "task40_v31_global_reference_builder"
            reference_started_ns = v31_phase_start(
                reference_phase,
                q4_pending_path=(
                    pending.get("numeric_pending", {}).get("record_path")
                    if isinstance(pending, Mapping)
                    else None
                ),
                q4_pending_sha256=(
                    pending.get("numeric_pending", {}).get("record_sha256")
                    if isinstance(pending, Mapping)
                    else None
                ),
                twist0_owner_prebuilt=prepared_owner is not None,
            )
            try:
                built_reference = build_task40_v10_p6_reference_inverse(
                    cfg,
                    axes,
                    allocation_gate=allocation_gate,
                    profile=periodic_profile,
                    event=reference_event,
                    identity_gate=identity_gate if route_contract is None else None,
                    jit_options=SAME_MESH_JIT_OPTIONS,
                    share_transform_bank=share_transform_bank,
                    target_full_storage_rows=(
                        int(target_action.condensed.full_rows)
                        if target_action is not None else None
                    ),
                    planned_target_full_storage_rows=(
                        int(periodic_profile.global_storage_rows)
                        if route_contract is not None
                        or v31_target_admission_policy is not None
                        else None
                    ),
                    target_admission_phase=(
                        "REFERENCE_ONLY"
                        if v31_target_admission_policy is not None
                        else None
                    ),
                    reference_pc_strategy=reference_pc_strategy,
                    q_assembly_strategy=q_assembly_strategy,
                    factor_lifecycle_strategy=factor_lifecycle_strategy,
                    operator_qualification_reuse=operator_qualification_reuse,
                    mode_inventory=v20_mode_inventory,
                    qualified_q_csr_provider=qualified_q_csr_provider,
                    qualified_q_csr_identity=qualified_q_csr_identity,
                    qualified_q_csr_coverage_phase=qualified_q_csr_coverage_phase,
                    qualified_q_csr_preparer=qualified_q_csr_preparer,
                    prebuilt_sector_owners=(
                        {0: prepared_owner} if prepared_owner is not None else None
                    ),
                    prebuilt_sector_q_csr=(
                        {0: prebuilt_twist0_q_csr}
                        if prebuilt_twist0_q_csr is not None
                        else None
                    ),
                    v30_factor_config=factor_config,
                    factor_output_directory=(
                        str(factor_config["output_directory"])
                        if factor_config is not None
                        else None
                    ),
                )
            except BaseException as error:
                if isinstance(prepared_owner, dict):
                    prepared_owner.setdefault("owner_receipt", {}).update(
                        handover_status="REFERENCE_BUILDER_FAILED",
                        global_reference_builder_failed=True,
                    )
                v31_phase_end(
                    reference_phase,
                    reference_started_ns,
                    status="FAILED",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                raise
            if isinstance(prepared_owner, dict):
                prepared_owner.setdefault("owner_receipt", {}).update(
                    handover_status="REFERENCE_OWNS_LOCAL_SECTOR",
                    global_reference_builder_returned=True,
                )
            v31_phase_end(
                reference_phase,
                reference_started_ns,
                status="COMPLETE",
                reference_q_count=len(
                    getattr(built_reference.get("factors"), "csr_matrices", {})
                ),
                reference_q_indices=sorted(
                    map(
                        int,
                        getattr(built_reference.get("factors"), "csr_matrices", {}).keys(),
                    )
                ),
            )
            return built_reference

        needs_saved_q4 = (
            qualified_q_csr_provider is not None
            and 0 in qualified_q_csr_provider.entries
        )
        reference, q4_saved_numeric_prebuild = _task40_v31_build_reference_after_q4_pending(
            prepare_saved_q4=(
                prepare_saved_q4_with_phase if needs_saved_q4 else None
            ),
            build_reference=build_reference_from_saved_q4,
            prepare_twist0_owner=(
                prepare_twist0_owner_with_phase if needs_saved_q4 else None
            ),
        )
        if qualified_q_csr_provider is not None:
            summary[
                "v31_all_q_selector" if v31_route_requested else "v30_all_q_selector"
            ] = reference.get(
                "qualified_q_csr_final_selector"
            )
        if stop_after_stage is not None:
            factors = reference["factors"]
            v20_stage_factors = factors
            factor_audit = copy.deepcopy(factors.audit)
            q_matrices = factors.csr_matrices
            q_inventory = {
                str(q): {
                    "shape": list(matrix.shape),
                    "nnz": int(matrix.nnz),
                    "csr_sha256": _sparse_content_sha256(matrix),
                }
                for q, matrix in sorted(q_matrices.items())
            }
            if stop_after_stage == "build_and_symbolic":
                if (
                    factor_audit.get("all_q_symbolic_covered") is not True
                    or set(q_matrices) != set(range(int(periodic_profile.q_count)))
                    or int(factor_audit.get("numeric_factor_build_attempt_count", 0)) != 0
                ):
                    raise RuntimeError("V20 build_and_symbolic stop failed its all-q symbolic contract")
                stage_facts = {
                    "schema": "task40extra.review_v20_worker_stage_result.v1",
                    "requested_stage": stop_after_stage,
                    "completed_stage": stop_after_stage,
                    "run_id": resolved_payload.get("run_id"),
                    "profile": profile_identity,
                    "source_sha": source_sha,
                    "input_sha256": resolved_payload.get("provenance", {}).get("input_sha256"),
                    "all_q_symbolic_covered": True,
                    "numeric_factor_build_attempt_count": 0,
                    "q_csr_inventory": q_inventory,
                    "factor_audit": factor_audit,
                    "official_result": False,
                    "full_field_release_allowed": False,
                }
            else:
                from src.solvers.task40_v20_local_components import _save_component_packet
                from src.solvers.task40_v20_numeric_stage import (
                    run_v20_one_q_physical_rhs,
                )

                v20_physical_rhs, physical_rhs_facts = build_physical_rhs(
                    reference["global_bundle"]
                )
                full_storage_rhs = None
                physical_rhs_values = None
                one_q_arrays = None
                try:
                    full_storage_rhs = np.asarray(
                        v20_physical_rhs.array_r, dtype=np.complex128
                    ).copy()
                    layout = reference["full_layout"]
                    independent = np.asarray(layout.independent, dtype=np.int64)
                    if full_storage_rhs.shape != (int(layout.full_rows),):
                        raise ValueError(
                            "V20 regular physical RHS differs from the full reference storage layout"
                        )
                    if independent.shape != (int(layout.independent_rows),):
                        raise ValueError(
                            "V20 regular physical RHS independent-row map is incomplete"
                        )
                    physical_rhs_values = full_storage_rhs[independent].copy()
                    physical_rhs_facts = {
                        **dict(physical_rhs_facts),
                        "case": "regular_reference_physical_startup_rhs",
                        "input_rhs_is_production_maxwell_source": True,
                        "port_rhs_is_zero_as_in_the_existing_physical_incident_witness": True,
                        "full_storage_rows": int(layout.full_rows),
                        "independent_rows": int(layout.independent_rows),
                        "mode_manifest_sha256": str(
                            reference["global_bundle"]["mode_sha256"]
                        ),
                    }
                    one_q_facts, one_q_arrays = run_v20_one_q_physical_rhs(
                        reference["inverse"],
                        factors,
                        physical_rhs_values,
                        physical_rhs_facts=physical_rhs_facts,
                        q_count=int(periodic_profile.q_count),
                    )
                    one_q_facts["q_csr_inventory"] = q_inventory
                    one_q_facts["selected_q_csr_sha256"] = q_inventory["0"][
                        "csr_sha256"
                    ]
                    one_q_facts["raw_packet"] = _save_component_packet(
                        directory,
                        "v20_one_q_numeric",
                        one_q_facts,
                        one_q_arrays,
                    )
                finally:
                    try:
                        v20_physical_rhs.destroy()
                    finally:
                        if full_storage_rhs is not None:
                            del full_storage_rhs
                        if physical_rhs_values is not None:
                            del physical_rhs_values
                        if one_q_arrays is not None:
                            del one_q_arrays

                factor_audit = copy.deepcopy(factors.audit)
                stage_facts = {
                    "schema": "task40extra.review_v20_worker_stage_result.v1",
                    "requested_stage": stop_after_stage,
                    "completed_stage": stop_after_stage,
                    "run_id": resolved_payload.get("run_id"),
                    "profile": profile_identity,
                    "source_sha": source_sha,
                    "input_sha256": resolved_payload.get("provenance", {}).get("input_sha256"),
                    "all_q_symbolic_covered": one_q_facts["all_q_symbolic_covered"],
                    "selected_q": one_q_facts["selected_q"],
                    "selected_q_numeric_coverage": one_q_facts[
                        "selected_q_numeric_coverage"
                    ],
                    "numeric_factor_build_attempt_count": one_q_facts[
                        "numeric_factor_build_attempt_count"
                    ],
                    "factor_probe_mat_solve_count": one_q_facts[
                        "factor_probe_mat_solve_count"
                    ],
                    "startup_rhs_mat_solve_count": one_q_facts[
                        "startup_rhs_mat_solve_count"
                    ],
                    "physical_rhs_stage": one_q_facts,
                    "factor_audit": factor_audit,
                    "official_result": False,
                    "full_field_release_allowed": False,
                }
            v20_stage_facts = stage_facts
            summary.update(
                status="CONTROLLED_STOP",
                official_result=False,
                result_classification="CONTROLLED_STOP_AT_REQUESTED_V20_STAGE",
                v20_stage_result=stage_facts,
            )
            runtime.marker("task40_v20_worker_stage_complete", stage_facts)
            worker_result = {
                "passed": True,
                "errors": [],
                "status": "controlled_stop",
                "official_result": False,
                "summary": summary,
                "numerical_output_directory": str(output_directory),
            }
            return worker_result
        if route_contract is None and not mode_identity:
            raise RuntimeError("regular p6 physical identity callback did not run before q factors")
        mapping_identity = _mapping_identity(reference)
        ref_rhs, ref_rhs_facts = build_physical_rhs(reference["global_bundle"])
        regular_checks = _verify_regular_inverse(
            runtime,
            reference,
            ref_rhs,
            ref_rhs_facts,
            allocation_gate=allocation_gate,
            reference_pc_strategy=reference_pc_strategy,
            include_mixed_fe_port_cases=route_contract is not None,
        )
        ref_rhs.destroy()
        ref_rhs = None
        if not regular_checks["passed"]:
            raise ValueError("complete regular p6 inverse checks did not pass")
        reference["regular_inverse_checks"] = regular_checks
        runtime.marker("v10_regular_reference_inverse_qualified", regular_checks)
        if v31_route_requested:
            early_reference_snapshot = {
                "schema": "task40extra.review_v10_reference_audit_snapshot.v1",
                "factor_audit_before_destroy": copy.deepcopy(reference["factors"].audit),
                "q_matrix_audits_before_destroy": copy.deepcopy(
                    reference.get("q_matrix_audits", {})
                ),
                "sector_audits_before_destroy": copy.deepcopy(
                    reference.get("sector_audits", [])
                ),
                "inverse_call_count": int(reference["inverse"].calls),
                "reference_layout": copy.deepcopy(reference["full_layout"].audit),
                "snapshot_after_six_reference_checks": True,
            }
            summary["regular_inverse_checks"] = regular_checks
            summary["reference_audit_snapshot"] = early_reference_snapshot
            early_product = v31_write_product(
                "v31_reference_inverse_product.json",
                {
                    "schema": "task40extra.review_v31_reference_inverse_product.v1",
                    "source_sha": source_sha,
                    "run_id": resolved_payload.get("run_id"),
                    "scientific_input_sha256": scientific_input_sha256,
                    "reference_audit_snapshot": early_reference_snapshot,
                    "regular_inverse_checks": regular_checks,
                    "all_q_selector": summary.get("v31_all_q_selector"),
                },
            )
            summary["v31_reference_inverse_product"] = early_product
            runtime.marker(
                "task40_v31_reference_inverse_product_persisted",
                {
                    **early_product,
                    "source_sha": source_sha,
                    "run_id": resolved_payload.get("run_id"),
                    "scientific_input_sha256": scientific_input_sha256,
                    "strict_reference_status_by_case": regular_checks.get(
                        "strict_reference_status_by_case"
                    ),
                    "v15_reference_status_by_case": regular_checks.get(
                        "v15_reference_status_by_case"
                    ),
                    "snapshot_stage": "after_complete_reference_checks_before_target_build",
                },
            )

        if route_contract is not None:
            _task40_v30_build_target_after_reference(
                reference_owner=reference,
                regular_checks=regular_checks,
                mode_inventory=v20_mode_inventory,
                target_builder=build_target_context,
            )
        if not mode_identity:
            raise RuntimeError("regular p6 physical identity did not pass before the target pilot")

        physical_rhs, rhs_facts = build_physical_rhs(target_bundle)
        rhs_norm = float(physical_rhs.norm())
        if not np.isfinite(rhs_norm) or rhs_norm <= 0.0:
            raise ValueError(f"{case_label} target physical RHS must be finite and nonzero")
        reduced_rhs_values = target_action.reduce_rhs(
            physical_rhs, rhs_is_mpc_dual=True
        )
        rhs = target_action.create_reduced_rhs_vector()
        _assign_vector_storage(rhs, reduced_rhs_values)
        reduced_rhs_norm = float(rhs.norm())
        if not np.isfinite(reduced_rhs_norm) or reduced_rhs_norm <= 0.0:
            raise ValueError(f"{case_label} retained trace+port RHS must be finite and nonzero")
        identity = {
            "schema": "task40extra.review_v10_b0_candidate_identity.v1",
            "profile_identity": profile_identity,
            "q_assembly_strategy": q_assembly_strategy,
            "source_sha": source_sha,
            "input_sha256": resolved_payload.get("provenance", {}).get("input_sha256"),
            "physical_model_sha256": resolved_payload.get("provenance", {}).get("physical_model_sha256"),
            "run_id": resolved_payload.get("run_id"),
            "stage": stage,
            "target_geometry_identity": cfg.geometry_identity,
            "mesh_axis_cell_counts": list(cfg.mesh_axis_cell_counts_requested or ()),
            "mesh_axes": {key: list(value) for key, value in axes.items()},
            "target_rectangular_air_void_audit": target_levels["mesh_data"].rectangular_air_void_audit,
            "target_p6_rows": int(physical_rhs.getSize()),
            "target_retained_rows": int(target_action.reduced_size),
            "target_active_trace_rows": int(target_action.condensed.active_rows),
            "target_port_rows": int(target_action.condensed.appended_rows),
            "target_mode_count": int(len(target_bundle["modes"])),
            "target_ordered_mode_sha256": str(target_bundle["mode_sha256"]),
            "reference_regular_mode_sha256": str(reference["global_bundle"]["mode_sha256"]),
            "mode_and_carrier_identity": mode_identity,
            "mode_inventory_preflight": mode_inventory_preflight,
            "target_backend": target_backend_facts,
            "reference_layout": dict(reference["full_layout"].audit),
            "mapping_identity": mapping_identity,
            "regular_inverse_checks": regular_checks,
            "physical_rhs_facts": rhs_facts,
            "physical_rhs_norm": rhs_norm,
            "retained_rhs_norm": reduced_rhs_norm,
            "reference_in_operator": False,
            "reference_in_initial_guess": False,
            **(
                {
                    "complete_operator_qualification_reuse": copy.deepcopy(
                        reference.get("complete_operator_qualification_reuse")
                    )
                }
                if is_v18 and reference.get("complete_operator_qualification_reuse") is not None
                else {}
            ),
            **(
                {
                    "complete_operator_qualification_sha256": hashlib.sha256(
                        json.dumps(
                            reference["complete_operator_qualification"],
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ).encode("utf-8")
                    ).hexdigest()
                }
                if is_v18
                else {}
            ),
        }
        if is_v18:
            summary["complete_operator_qualification_sha256"] = identity[
                "complete_operator_qualification_sha256"
            ]
        identity_packet = _save_packet(runtime, "v10_candidate_operator_identity", identity)
        summary.update(
            identity_packet=identity_packet,
            target_mesh={
                "cell_count": int(target_levels["mesh_data"].mesh.topology.index_map(3).size_global),
                "axis_cell_counts": list(cfg.mesh_axis_cell_counts_requested or ()),
                "air_void_audit": target_levels["mesh_data"].rectangular_air_void_audit,
            },
            ordered_mode_sha256=identity["target_ordered_mode_sha256"],
            mode_count=identity["target_mode_count"],
            regular_inverse_checks=regular_checks,
            mapping_identity=mapping_identity,
            mode_and_carrier_identity=mode_identity,
            mode_inventory_preflight=mode_inventory_preflight,
            target_backend=target_backend_facts,
            target_condensed_action_audit=dict(target_action.audit),
            allocation_admission_gates=allocation_gate_records,
            allocation_admission_gate_summary=(
                allocation_gate_summary if is_v16 or is_v17 else None
            ),
        )

        pc = _P6ReferencePreconditioner(
            runtime, reference, target_action, target_bundle["dtn_action"].carrier,
            allocation_gate=allocation_gate,
        )
        if is_v16:
            live_q_indices = sorted(
                int(q) for q in reference["factors"].factors
            )
            expected_q_indices = list(range(int(periodic_profile.q_count)))
            all_q_factor_objects_live = live_q_indices == expected_q_indices
            startup_facts = {
                "schema": "task40extra.review_v16_solver_startup_inventory.v1",
                "q_matrix_audits": dict(reference.get("q_matrix_audits", {})),
                "expected_q_count": int(periodic_profile.q_count),
                "factor_live_count": len(live_q_indices),
                "factor_q_indices": live_q_indices,
                "all_q_factor_objects_live": all_q_factor_objects_live,
                "all_four_factor_objects_live": (
                    periodic_profile.q_count == 4 and all_q_factor_objects_live
                ),
                "target_reduced_rows": int(target_action.reduced_size),
                "target_action_buffer_inventory": dict(target_action.buffer_inventory),
            }
            runtime.marker("v16_solver_startup_complete_before_ksp", startup_facts)
            runtime.sample("v16_solver_startup_complete_before_ksp", enforce=False)
        checkpoints = {"count": 0}
        outer_started_ns = time.perf_counter_ns()
        runtime.begin_outer_solve()
        outer_started = True

        def action(source: Any):
            return target_action.apply(source)

        def evaluate(source: Any, residual: Any):
            source_values = np.asarray(source.array_r, dtype=np.complex128)
            schur_residual = np.asarray(residual.array_r, dtype=np.complex128).copy()
            candidate = target_action.evaluate_native_residual(
                source_values,
                physical_rhs,
                lambda values: _apply_full_action_array(
                    target_fast_bundle["physical_action"], values, PETSc
                ),
                rhs_is_mpc_dual=True,
                reduced_residual=schur_residual,
            )
            native_witness = target_action.evaluate_native_residual(
                source_values,
                physical_rhs,
                lambda values: _apply_full_action_array(
                    target_bundle["physical_action"], values, PETSc
                ),
                rhs_is_mpc_dual=True,
                reduced_residual=schur_residual,
            )
            applied_residual = float(candidate["native_residual_relative"])
            port_relative = float(candidate["port_residual_relative"])
            if not np.isfinite(applied_residual) or not np.isfinite(port_relative):
                raise FloatingPointError("candidate target A6 or actual port residual is nonfinite")
            pc_facts = dict(pc.last_facts)
            return {
                "original_A6_relative": applied_residual,
                "port_closure_relative": port_relative,
                "internal_residual_relative": float(candidate["internal_residual_relative"]),
                "native_identity_relative": float(candidate["native_identity_relative"]),
                "schur_port_identity_relative": float(candidate["schur_port_identity_relative"]),
                "target_backend": "isotropic_sum_factorized_n1e_v26",
                "target_native_witness": {
                    "native_residual_relative": float(native_witness["native_residual_relative"]),
                    "port_residual_relative": float(native_witness["port_residual_relative"]),
                    "internal_residual_relative": float(native_witness["internal_residual_relative"]),
                    "native_identity_relative": float(native_witness["native_identity_relative"]),
                    "schur_port_identity_relative": float(native_witness["schur_port_identity_relative"]),
                },
                "retained_alpha_norm": float(np.linalg.norm(candidate["retained_alpha"])),
                "reference_pc_apply": pc_facts,
            }

        def append(name: str, row: Mapping[str, Any]):
            _append_jsonl(directory / name, row)
            if name in {"primary_stop.jsonl", "ksp_solve_phase.jsonl"}:
                runtime.marker(f"v10_{name.removesuffix('.jsonl')}_recorded", row)

        def save_retained(iteration: int, vector: Any):
            checkpoints["count"] += 1
            _save_packet(
                runtime,
                f"checkpoints/v10_candidate_p6_x_{int(iteration):04d}_{checkpoints['count']:04d}",
                {
                    "schema": "task40extra.review_v10_b0_candidate_full_p6_checkpoint.v1",
                    "iteration": int(iteration),
                    "solution_storage": np.asarray(vector.array_r).copy(),
                    "saved_before_physical_evaluation": True,
                    "identity": identity,
                },
            )

        def checkpoint(iteration: int, vector: Any, row: Mapping[str, Any]):
            _save_packet(
                runtime,
                f"checkpoints/v10_candidate_p6_residual_{int(iteration):04d}",
                {
                    "schema": "task40extra.review_v10_b0_candidate_residual_checkpoint.v1",
                    "iteration": int(iteration),
                    "residual_facts": dict(row),
                    "solution_storage": np.asarray(vector.array_r).copy(),
                    "identity": identity,
                },
            )

        def stop_requested() -> bool:
            if runtime.stop_requested:
                return True
            elapsed = float(runtime.workflow_clock_interval()["budget_seconds"])
            return elapsed >= float(runtime.workflow_reserved_seconds)

        if is_v16:
            runtime.marker(
                "v16_ksp_start",
                {
                    "outer_solver": "FGMRES",
                    "restart": 32,
                    "max_it": 2048,
                    "initial_guess": "zero",
                    "mpi_size": 1,
                    "mathematical_threads": 1,
                },
            )
            runtime.sample("v16_ksp_start", enforce=False)
        result = run_retained_fgmres(
            rhs,
            action,
            pc.apply,
            evaluate=evaluate,
            checkpoint=checkpoint,
            append=append,
            seconds=lambda: (time.perf_counter_ns() - outer_started_ns) / 1.0e9,
            resource_sample=lambda: runtime.sample("v10_candidate_outer_iteration"),
            stop_requested=stop_requested,
            save_retained=save_retained,
            persist_native_stop_records=True,
        )
        final_solution = result.pop("final_solution")
        runtime.finish_outer_solve()
        outer_started = False
        summary["solver"] = {
            key: value for key, value in result.items() if key != "snapshots"
        }
        summary["solver"]["snapshots"] = list(result.get("snapshots", []))
        summary["reference_pc_apply_count"] = int(pc.calls)
        summary["reference_pc_last_facts"] = dict(pc.last_facts)

        def evaluate_final_full_state() -> tuple[dict[str, Any], dict[str, Any]]:
            reduced_values = np.asarray(final_solution.array_r, dtype=np.complex128).copy()
            fast = target_action.evaluate_native_residual(
                reduced_values,
                physical_rhs,
                lambda values: _apply_full_action_array(
                    target_fast_bundle["physical_action"], values, PETSc
                ),
                rhs_is_mpc_dual=True,
            )
            native = target_action.evaluate_native_residual(
                reduced_values,
                physical_rhs,
                lambda values: _apply_full_action_array(
                    target_bundle["physical_action"], values, PETSc
                ),
                rhs_is_mpc_dual=True,
            )
            return fast, native

        pre_release_full_rows = int(target_action.condensed.full_rows)
        reference_full_rows = int(reference["full_layout"].full_rows)
        if pre_release_full_rows != reference_full_rows:
            raise ValueError(
                "full p6 recovery budget needs matching target/reference rows: "
                f"{pre_release_full_rows} != {reference_full_rows}"
            )
        pre_release_output_inventory = full_p6_pre_release_output_inventory(
            pre_release_full_rows
        )
        allocation_gate(
            "before_full_p6_pre_release_recovery_output_and_save",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": 0,
                "declared_future_co_resident_bytes": int(
                    pre_release_output_inventory["pre_release_peak_bytes"]
                ),
                "full_storage_rows": pre_release_full_rows,
                "full_output_inventory": pre_release_output_inventory,
                "phase_scope": "paired full A6 residual recovery and six-array pre-release audit packet while all q factors remain live",
            },
        )
        runtime.marker(
            "v12_full_p6_pre_release_output_budget",
            {
                "target_full_storage_rows": pre_release_full_rows,
                "reference_full_storage_rows": reference_full_rows,
                "inventory": pre_release_output_inventory,
            },
        )
        pre_backend, pre_native = evaluate_final_full_state()
        pre_release_relative = float(pre_backend["native_residual_relative"])
        pre_native_relative = float(pre_native["native_residual_relative"])
        pre_full_solution = np.asarray(
            pre_backend["storage_solution"], dtype=np.complex128
        ).copy()
        pre_full_rhs = np.asarray(physical_rhs.array_r, dtype=np.complex128).copy()
        pre_backend_residual = np.asarray(pre_backend["native_residual"], dtype=np.complex128).copy()
        pre_backend_applied = pre_full_rhs - pre_backend_residual
        pre_native_residual = np.asarray(pre_native["native_residual"], dtype=np.complex128).copy()
        pre_native_applied = pre_full_rhs - pre_native_residual
        final_full_solution = PETSc.Vec().createSeq(
            target_action.condensed.full_rows, comm=PETSc.COMM_SELF
        )
        _assign_vector_storage(final_full_solution, pre_full_solution)
        final_record = {
            "schema": "task40extra.review_v10_b0_candidate_independent_A6_residual.v1",
            "identity": identity,
            "rhs_norm": rhs_norm,
            "relative_residual": pre_release_relative,
            "limit": _A6_RESIDUAL_LIMIT,
            "native_witness_relative_residual": pre_native_relative,
            "independent_action_count": 2,
            "target_backend": "isotropic_sum_factorized_n1e_v26",
            "independent_witness_backend": "native_ffcx_full_A6_same_target_forms_and_carrier",
            "all_target_cell_interior_rows_evaluated": periodic_profile.global_interior_rows,
            "actual_retained_alpha": np.asarray(pre_backend["retained_alpha"]).copy(),
            "actual_port_residual_relative": float(pre_backend["port_residual_relative"]),
            "actual_internal_residual_relative": float(pre_backend["internal_residual_relative"]),
            "actual_native_identity_relative": float(pre_backend["native_identity_relative"]),
            "actual_schur_port_identity_relative": float(pre_backend["schur_port_identity_relative"]),
            "solver_reported_true_residual": result.get("final_true_residual"),
            "full_physical_rhs_storage": pre_full_rhs,
            "full_solution_storage": pre_full_solution,
            "target_backend_applied_storage": pre_backend_applied,
            "target_backend_residual_storage": pre_backend_residual,
            "native_witness_applied_storage": pre_native_applied,
            "native_witness_residual_storage": pre_native_residual,
            "mode_identity": mode_identity,
        }
        final_residual_packet = _save_packet(
            runtime, "v10_candidate_final_A6_pre_release", final_record
        )
        inverse_input_identity = reference["factors"].verify_all_input_identities(
            stage="before_reference_factor_release"
        )
        transform_bank_final_receipt = None
        transform_bank = reference.get("transform_bank")
        if transform_bank is not None:
            named_arrays = reference["global_entities"].named_backing_arrays("global")
            for sector_index, sector in enumerate(reference["sectors"]):
                named_arrays.update(
                    sector["entities"].named_backing_arrays(f"sector{sector_index}")
                )
            transform_bank_final_receipt = transform_bank.receipt(
                named_arrays, stage="all_reference_checks_before_owner_release"
            )
            reference["transform_bank_receipt"] = transform_bank_final_receipt
        reference_audit_snapshot = {
            "schema": "task40extra.review_v10_reference_audit_snapshot.v1",
            "factor_audit_before_destroy": copy.deepcopy(reference["factors"].audit),
            "q_matrix_audits_before_destroy": copy.deepcopy(reference.get("q_matrix_audits", {})),
            "sector_audits_before_destroy": copy.deepcopy(reference.get("sector_audits", [])),
            "inverse_call_count": int(reference["inverse"].calls),
            "inverse_last_solve_q_residuals": copy.deepcopy(
                reference["inverse"].last_solve_audit
            ),
            "reference_layout": copy.deepcopy(reference["full_layout"].audit),
            "inverse_input_identity": inverse_input_identity,
            "full_storage_dimensions": copy.deepcopy(
                reference.get("full_storage_dimensions", {})
            ),
            "transform_bank_final_receipt": copy.deepcopy(transform_bank_final_receipt),
            **(
                {
                    "complete_operator_qualification": copy.deepcopy(
                        reference.get("complete_operator_qualification")
                    ),
                    **(
                        {
                            "complete_operator_qualification_reuse": copy.deepcopy(
                                reference["complete_operator_qualification_reuse"]
                            )
                        }
                        if reference.get("complete_operator_qualification_reuse") is not None
                        else {}
                    ),
                }
                if is_v18
                else {}
            ),
        }
        pc_snapshot = pc.detach()
        summary["reference_audit_snapshot"] = reference_audit_snapshot
        if v31_route_requested:
            reference_product = v31_write_product(
                "v31_reference_inverse_product.json",
                {
                    "schema": "task40extra.review_v31_reference_inverse_product.v1",
                    "source_sha": source_sha,
                    "run_id": resolved_payload.get("run_id"),
                    "scientific_input_sha256": scientific_input_sha256,
                    "reference_audit_snapshot": reference_audit_snapshot,
                    "regular_inverse_checks": summary.get("regular_inverse_checks"),
                    "all_q_selector": summary.get("v31_all_q_selector"),
                },
            )
            summary["v31_reference_inverse_product"] = reference_product
            runtime.marker(
                "task40_v31_reference_inverse_product_persisted",
                {
                    **reference_product,
                    "source_sha": source_sha,
                    "run_id": resolved_payload.get("run_id"),
                    "scientific_input_sha256": scientific_input_sha256,
                    "strict_reference_status_by_case": (
                        summary.get("regular_inverse_checks", {}).get(
                            "strict_reference_status_by_case"
                        )
                    ),
                    "v15_reference_status_by_case": (
                        summary.get("regular_inverse_checks", {}).get(
                            "v15_reference_status_by_case"
                        )
                    ),
                },
            )
        summary["reference_pc_audit_before_detach"] = pc_snapshot
        summary["target_backend_final_audit"] = dict(
            target_fast_bundle["physical_action"].audit
        )
        summary["target_native_witness_final_audit"] = dict(
            target_bundle["physical_action"].audit
        )
        summary["target_condensed_action_final_audit"] = dict(target_action.audit)
        summary["allocation_admission_gates"] = allocation_gate_records
        if is_v16:
            summary["allocation_admission_gate_summary"] = allocation_gate_summary
        destroy_task40_v10_p6_reference_inverse(reference)
        reference = None
        runtime.sample("v10_candidate_reference_factor_release_complete")

        allocation_gate(
            "before_full_p6_post_release_residual_output_and_save",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": 0,
                "declared_future_co_resident_bytes": int(
                    pre_release_output_inventory["pre_release_peak_bytes"]
                ),
                "full_storage_rows": pre_release_full_rows,
                "full_output_inventory": pre_release_output_inventory,
                "phase_scope": (
                    "paired post-release full A6 residual and packet; prior pre-release result arrays are already in live RSS"
                ),
                "pre_release_known_retained_array_equivalents_already_live": (
                    2 * len(pre_release_output_inventory["native_residual_result_full_rows_array_names"])
                    + int(pre_release_output_inventory["pre_release_independent_audit_copy_count"])
                    + int(pre_release_output_inventory["final_full_solution_petsc_vector_count"])
                ),
            },
        )
        runtime.marker(
            "v12_full_p6_post_release_output_budget",
            {
                "full_storage_rows": pre_release_full_rows,
                "inventory": pre_release_output_inventory,
            },
        )
        post_backend, post_native = evaluate_final_full_state()
        post_release_relative = float(post_backend["native_residual_relative"])
        post_native_relative = float(post_native["native_residual_relative"])
        post_full_solution = np.asarray(
            post_backend["storage_solution"], dtype=np.complex128
        ).copy()
        post_full_rhs = np.asarray(physical_rhs.array_r, dtype=np.complex128).copy()
        post_backend_residual = np.asarray(
            post_backend["native_residual"], dtype=np.complex128
        ).copy()
        post_native_residual = np.asarray(
            post_native["native_residual"], dtype=np.complex128
        ).copy()
        post_release_packet = _save_packet(
            runtime,
            "v10_candidate_final_A6_post_release",
            {
                "schema": "task40extra.review_v10_b0_candidate_post_release_A6_residual.v1",
                "identity": identity,
                "rhs_norm": rhs_norm,
                "relative_residual": post_release_relative,
                "native_witness_relative_residual": post_native_relative,
                "limit": _A6_RESIDUAL_LIMIT,
                "independent_action_count": 2,
                "reference_factors_released": True,
                "full_physical_rhs_storage": post_full_rhs,
                "full_solution_storage": post_full_solution,
                "target_backend_applied_storage": post_full_rhs - post_backend_residual,
                "target_backend_residual_storage": post_backend_residual,
                "native_witness_applied_storage": post_full_rhs - post_native_residual,
                "native_witness_residual_storage": post_native_residual,
                "all_target_cell_interior_rows_evaluated": periodic_profile.global_interior_rows,
                "mode_identity": mode_identity,
            },
        )
        runtime.sample("v12_full_p6_post_release_residual_packet_complete")
        solver_residual = float(result.get("final_true_residual", np.inf))
        final_eval = dict(result.get("final_evaluation", {}))
        final_port_closure = float(final_eval.get("port_closure_relative", np.inf))
        identity_metrics = {
            "native_mapping_identity_relative": float(
                mapping_identity["maximum_identity_relative"]
            ),
            "reference_pc_port_identity_relative": float(
                pc_snapshot["last_facts"]["port_identity_relative"]
            ),
            "maximum_q_true_residual_relative": float(
                pc_snapshot["last_facts"]["maximum_q_true_residual_relative"]
            ),
            "target_native_witness_relative_residual": pre_native_relative,
            "target_condensed_native_identity_relative": float(
                pre_backend["native_identity_relative"]
            ),
            "target_schur_port_identity_relative": float(
                pre_backend["schur_port_identity_relative"]
            ),
        }
        reference_pc_final_gate = recheck_reference_pc_final_admission(
            pc_snapshot["last_facts"], reference_pc_strategy
        )
        reference_pc_port_identity_limit = float(
            reference_pc_final_gate.get("port_identity_limit", -1.0)
        )
        reference_pc_q_limit = float(
            reference_pc_final_gate.get("q_true_residual_limit", -1.0)
        )
        identity_metrics["reference_pc_port_identity_limit"] = (
            reference_pc_port_identity_limit
        )
        identity_metrics["reference_pc_q_true_residual_limit"] = reference_pc_q_limit
        identity_metrics["reference_pc_admission"] = reference_pc_final_gate.get(
            "admission"
        )
        final_physical_metrics = {
            "pre_release_target_backend": pre_backend,
            "pre_release_native_witness": pre_native,
            "post_release_target_backend": post_backend,
            "post_release_native_witness": post_native,
        }

        def finite_within(metric: Any, limit: float) -> bool:
            value = float(metric)
            return bool(np.isfinite(value) and value <= limit)

        physical_identity_pass = all(
            finite_within(row[key], limit)
            for row in final_physical_metrics.values()
            for key, limit in (
                ("port_residual_relative", _PORT_CLOSURE_LIMIT),
                ("internal_residual_relative", _IDENTITY_LIMIT),
                ("native_identity_relative", _IDENTITY_LIMIT),
                ("schur_port_identity_relative", _IDENTITY_LIMIT),
            )
        )
        numeric_pass = bool(
            result.get("status") == "TRUE_RESIDUAL_PASS"
            and np.isfinite(pre_release_relative)
            and pre_release_relative <= _A6_RESIDUAL_LIMIT
            and np.isfinite(post_release_relative)
            and post_release_relative <= _A6_RESIDUAL_LIMIT
            and np.isfinite(pre_native_relative)
            and pre_native_relative <= _A6_RESIDUAL_LIMIT
            and np.isfinite(post_native_relative)
            and post_native_relative <= _A6_RESIDUAL_LIMIT
            and physical_identity_pass
            and np.isfinite(solver_residual)
            and solver_residual <= _A6_RESIDUAL_LIMIT
            and np.isfinite(final_port_closure)
            and final_port_closure <= _PORT_CLOSURE_LIMIT
            and identity_metrics["native_mapping_identity_relative"] <= _IDENTITY_LIMIT
            and _reference_pc_final_identity_pass(
                reference_pc_final_gate, identity_metrics
            )
            and all(inverse_input_identity.values())
        )
        summary.update(
            pre_release_final_residual_packet=final_residual_packet,
            post_release_final_residual_packet=post_release_packet,
            independent_final_A6_relative_residual=pre_release_relative,
            post_release_final_A6_relative_residual=post_release_relative,
            independent_final_native_witness_relative_residual=pre_native_relative,
            post_release_native_witness_relative_residual=post_native_relative,
            inverse_input_identity=inverse_input_identity,
            identity_metrics=identity_metrics,
            reference_pc_final_gate_recheck=reference_pc_final_gate,
            final_evaluation=final_eval,
            final_physical_metrics={
                name: {
                    key: float(row[key])
                    for key in (
                        "native_residual_relative",
                        "port_residual_relative",
                        "internal_residual_relative",
                        "native_identity_relative",
                        "schur_port_identity_relative",
                    )
                }
                for name, row in final_physical_metrics.items()
            },
            final_physical_identity_pass=physical_identity_pass,
            solver_status=result.get("status"),
            solver_reported_residual=solver_residual,
            port_closure_relative=final_port_closure,
            iterations=result.get("iterations"),
            ksp_reason=result.get("reason"),
            numeric_gates_passed=numeric_pass,
        )
        if not numeric_pass:
            summary.update(
                status="NUMERICAL_FAIL",
                result_classification=(
                    "B0_CANDIDATE_FULL_A6_OR_IDENTITY_GATE_FAIL"
                    if is_v10
                    else f"{case_label.upper()}_P6_FULL_A6_OR_IDENTITY_GATE_FAIL"
                ),
                official_result=False,
            )
            worker_result = {"passed": False, "errors": [summary["result_classification"]], "summary": summary}
            return worker_result

        runtime.set_phase("evaluation")
        output_directory = directory / "numerical_output"
        _disk_admit(
            runtime,
            additional_bytes=1 << 30,
            label="before_p6_field_mode_and_diffraction_export",
        )
        official_full_field_bytes = (
            pre_release_full_rows * 2 * np.dtype(np.complex128).itemsize
            + int(periodic_profile.mode_count) * np.dtype(np.complex128).itemsize
        )
        allocation_gate(
            "before_full_p6_official_field_and_mode_output",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": 0,
                "declared_future_co_resident_bytes": int(official_full_field_bytes),
                "full_storage_rows": pre_release_full_rows,
                "full_field_vector_equivalents": 2,
                "retained_port_auxiliary_complex128_bytes": int(
                    periodic_profile.mode_count * np.dtype(np.complex128).itemsize
                ),
                "phase_scope": (
                    "known full-space DOLFINx field plus one full_rows postprocessing workspace and retained mode auxiliary; "
                    "DG/JIT internals remain under live watchdog samples"
                ),
            },
        )
        runtime.sample("v10_candidate_before_official_output")
        output = recover_p0_outputs(
            target_bundle,
            final_full_solution,
            output_directory,
            export_all_port_modes=True,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        port = output.get("port_metrics", {})
        volume = output.get("volume_metrics", {})
        power = {
            "R": float(port.get("R_total", np.nan)),
            "T": float(port.get("T_total", np.nan)),
            "A": float(port.get("A_balance", np.nan)),
            "A_volume": float(volume.get("A_volume_total", np.nan)),
        }
        energy_error = abs(power["R"] + power["T"] + power["A_volume"] - 1.0)
        absorption_error = abs(power["A"] - power["A_volume"])
        output_pass = bool(
            output.get("electric_finite") is True
            and output.get("auxiliary_finite") is True
            and _single_side_diffraction_order_count_passed(
                output, periodic_profile.mode_count
            )
            and np.isfinite(list(power.values())).all()
            and energy_error <= 1.0e-5
            and absorption_error <= 1.0e-5
        )
        output_files = _file_manifest(output_directory)
        _disk_admit(runtime, additional_bytes=0, label="after_p6_field_mode_and_diffraction_export")
        scientific_identity = {
            "schema": "task40extra.review_v10_scientific_output_identity.v1",
            "source_sha": source_sha,
            "input_sha256": identity["input_sha256"],
            "physical_model_sha256": identity["physical_model_sha256"],
            "ordered_physical_mode_sha256": str(target_bundle["mode_sha256"]),
            "carrier_assembly_manifest_sha256": str(
                target_bundle["dtn_action"].carrier.mode_manifest_sha256
            ),
            "carrier_payload_rows_values_sha256": _carrier_payload_identity(
                target_bundle["dtn_action"].carrier
            ),
            "full_solution_storage_sha256": _hash_arrays(
                {"full_solution_storage": pre_full_solution}
            ),
            "modal_amplitudes_sha256": _hash_arrays(
                {"modal_amplitudes": np.asarray(output["auxiliary"], dtype=np.complex128)}
            ),
            "full_solution_packet": final_residual_packet.get("arrays"),
            "full_solution_packet_json": str(
                directory / "v10_candidate_final_A6_pre_release.json"
            ),
            "field_mode_and_diffraction_files": output_files,
            "field_file_count": len(output_files),
            "independent_reevaluation": {
                "entrypoint": "src.runners.task40_v10_output_checker.verify_v10_output_bundle",
                "command": (
                    "python -m src.runners.task40_v10_output_checker "
                    "<v10_candidate_official_output.json> "
                    f"--expected-channel-count {periodic_profile.mode_count}"
                ),
                "scope": "reopen hashes and independently recompute saved full residual algebra",
            },
        }
        target_backend_facts.update(
            final_physical_action_audit=dict(target_fast_bundle["physical_action"].audit),
            kernel_call_audits=[dict(kernel.audit) for kernel in target_fast_bundle["kernels"]],
            native_witness_action_audit=dict(target_bundle["physical_action"].audit),
        )
        output_packet = _save_packet(
            runtime,
            "v10_candidate_official_output",
            {
                "schema": "task40extra.review_v10_b0_candidate_output.v1",
                "identity": identity,
                "scientific_identity": scientific_identity,
                "output": output,
                "power": power,
                "R_plus_T_plus_A_volume_minus_one": energy_error,
                "A_minus_A_volume": absorption_error,
                "passed": output_pass,
            },
        )
        runtime.sample("v10_candidate_official_output_complete")
        summary.update(
            output_packet=output_packet,
            scientific_identity=scientific_identity,
            independent_reevaluation=scientific_identity["independent_reevaluation"],
            target_backend=target_backend_facts,
            output_facts={key: value for key, value in output.items() if key != "auxiliary"},
            power=power,
            energy_closure_absolute=energy_error,
            absorption_consistency_absolute=absorption_error,
            output_gates_passed=output_pass,
            status="PASS" if output_pass else "PHYSICAL_OUTPUT_GATE_FAIL",
            result_classification=(
                "B0_CANDIDATE_FULL_P6_REFERENCE_INVERSE_PASS"
                if is_v10 and output_pass
                else "B0_CANDIDATE_PHYSICAL_OUTPUT_GATE_FAIL"
                if is_v10
                else f"{case_label.upper()}_P6_REFERENCE_INVERSE_PASS"
                if output_pass
                else f"{case_label.upper()}_P6_PHYSICAL_OUTPUT_GATE_FAIL"
            ),
            official_result=output_pass,
        )
        runtime.marker("v10_candidate_worker_result", summary)
        worker_result = {
            "passed": bool(output_pass),
            "errors": [] if output_pass else ["physical R/T/A output gates failed"],
            "summary": summary,
            "numerical_output_directory": str(output_directory),
        }
        return worker_result
    except V16StagingLimitError as exc:
        gate_key = "v17_row_tile_staging_gate" if is_v17 else "v16_staging_gate"
        summary.update(
            status="CONTROLLED_STOP",
            official_result=False,
            result_classification="RESOURCE_CONTROLLED_STOP",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        summary[gate_key] = exc.evidence()
        worker_result = {"passed": False, "errors": [str(exc)], "summary": summary}
        return worker_result
    except V14ResourceStop as exc:
        summary.update(
            status="CONTROLLED_STOP",
            official_result=False,
            result_classification=getattr(exc, "classification", "RESOURCE_CONTROLLED_STOP"),
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        worker_result = {"passed": False, "errors": [str(exc)], "summary": summary}
        return worker_result
    except BaseException as exc:
        summary.update(
            status="FAILED",
            official_result=False,
            result_classification="WORKER_FAILED",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        raise
    finally:
        if outer_started and runtime is not None:
            try:
                runtime.finish_outer_solve()
            except Exception:
                pass
        if final_solution is not None:
            final_solution.destroy()
        if rhs is not None:
            rhs.destroy()
        if physical_rhs is not None:
            physical_rhs.destroy()
        if final_full_solution is not None:
            final_full_solution.destroy()
        if target_condensed is not None:
            try:
                target_condensed.destroy()
            except Exception:
                pass
        if pc is not None and pc.owner is not None:
            try:
                summary["reference_pc_audit_before_failure_cleanup"] = pc.detach()
            except Exception as exc:
                summary.setdefault("cleanup_errors", []).append(
                    {"type": type(exc).__name__, "message": str(exc)}
                )
        if reference is not None:
            try:
                if reference_audit_snapshot is None:
                    reference_audit_snapshot = {
                        "schema": "task40extra.review_v10_reference_audit_snapshot.v1",
                        "factor_audit_before_destroy": copy.deepcopy(
                            reference.get("factors").audit
                            if reference.get("factors") is not None
                            else {}
                        ),
                        "q_matrix_audits_before_destroy": copy.deepcopy(
                            reference.get("q_matrix_audits", {})
                        ),
                        "sector_audits_before_destroy": copy.deepcopy(
                            reference.get("sector_audits", [])
                        ),
                        "inverse_call_count": int(
                            reference.get("inverse").calls
                            if reference.get("inverse") is not None
                            else 0
                        ),
                        "inverse_last_solve_q_residuals": copy.deepcopy(
                            reference.get("inverse").last_solve_audit
                            if reference.get("inverse") is not None
                            else None
                        ),
                        "reference_layout": copy.deepcopy(
                            reference.get("full_layout").audit
                            if reference.get("full_layout") is not None
                            else {}
                        ),
                        **(
                            {
                                "complete_operator_qualification": copy.deepcopy(
                                    reference.get("complete_operator_qualification")
                                ),
                                **(
                                    {
                                        "complete_operator_qualification_reuse": copy.deepcopy(
                                            reference["complete_operator_qualification_reuse"]
                                        )
                                    }
                                    if reference.get("complete_operator_qualification_reuse") is not None
                                    else {}
                                ),
                            }
                            if is_v18
                            else {}
                        ),
                        "snapshot_before_failure_cleanup": True,
                    }
                    summary["reference_audit_snapshot"] = reference_audit_snapshot
                destroy_task40_v10_p6_reference_inverse(reference)
                if v20_stage_factors is not None and v20_stage_facts is not None:
                    from src.solvers.task40_v20_numeric_stage import (
                        v20_factor_cleanup_facts,
                    )

                    cleanup = v20_factor_cleanup_facts(v20_stage_factors)
                    v20_stage_facts["cleanup"] = cleanup
                    v20_stage_facts["cleanup_gate_passed"] = cleanup["passed"]
                    summary["v20_stage_result"] = v20_stage_facts
                    if not cleanup["passed"]:
                        cleanup_error = {
                            "type": "RuntimeError",
                            "message": "V20 stage did not release the one-q factor slot",
                        }
                        summary.setdefault("cleanup_errors", []).append(cleanup_error)
                        if worker_result is not None:
                            worker_result["passed"] = False
                            worker_result["status"] = "failed"
                            worker_result["errors"] = [cleanup_error["message"]]
            except Exception as exc:
                summary.setdefault(
                    "cleanup_errors", []
                ).append({"type": type(exc).__name__, "message": str(exc)})
                if v20_stage_facts is not None:
                    v20_stage_facts["cleanup"] = {
                        "passed": False,
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    }
                    v20_stage_facts["cleanup_gate_passed"] = False
                    summary["v20_stage_result"] = v20_stage_facts
                    if worker_result is not None:
                        worker_result["passed"] = False
                        worker_result["status"] = "failed"
                        worker_result["errors"] = [str(exc)]
        if prebuilt_twist0_owner is not None:
            prior_owner_receipt = dict(
                prebuilt_twist0_owner.get("owner_receipt", {})
            )
            owner_was_already_released = (
                prebuilt_twist0_owner.get("local_owner_cleanup_complete") is True
            )
            try:
                cleanup = destroy_task40_v10_p6_local_sector_owner(
                    prebuilt_twist0_owner,
                    close_transform_bank=True,
                )
                if cleanup.get("status") != "RELEASED":
                    raise RuntimeError(
                        "V31 twist-0 owner cleanup did not confirm release: "
                        f"{cleanup}"
                    )
                handover_status = prior_owner_receipt.get(
                    "handover_status", "OWNER_NOT_HANDED_TO_REFERENCE"
                )
                cleanup_facts = {
                    "schema": "task40extra.review_v31_twist0_owner_handoff_cleanup.v1",
                    "status": "RELEASED",
                    "handover_status": handover_status,
                    "reference_builder_returned": bool(
                        prior_owner_receipt.get("global_reference_builder_returned")
                    ),
                    "reference_object_present_during_finally": reference is not None,
                    "owner_already_released_before_worker_finally": owner_was_already_released,
                    "cleanup_responsibility": (
                        "reference_owner_then_worker_finally_idempotent_verification"
                        if handover_status == "REFERENCE_OWNS_LOCAL_SECTOR"
                        else "worker_finally_release_or_idempotent_builder_failure_fallback"
                    ),
                    "worker_finally_called_cleanup": True,
                    "cleanup_receipt": dict(cleanup),
                }
                summary["v31_twist0_local_owner_cleanup"] = cleanup_facts
                if runtime is not None:
                    runtime.marker(
                        "task40_v31_twist0_local_owner_cleanup",
                        cleanup_facts,
                    )
            except BaseException as exc:
                cleanup_facts = {
                    "schema": "task40extra.review_v31_twist0_owner_handoff_cleanup.v1",
                    "status": "CLEANUP_FAILED",
                    "handover_status": prior_owner_receipt.get(
                        "handover_status", "OWNER_NOT_HANDED_TO_REFERENCE"
                    ),
                    "reference_builder_returned": bool(
                        prior_owner_receipt.get("global_reference_builder_returned")
                    ),
                    "owner_already_released_before_worker_finally": owner_was_already_released,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
                _task40_v31_apply_local_owner_cleanup_failure(
                    summary,
                    worker_result,
                    cleanup_facts,
                )
        if target_fast_bundle is not None:
            try:
                target_fast_bundle["physical_action"].destroy()
            except Exception as exc:
                summary.setdefault(
                    "cleanup_errors", []
                ).append({"type": type(exc).__name__, "message": str(exc)})
        if target_action is not None:
            try:
                target_action.destroy()
            except Exception as exc:
                summary.setdefault(
                    "cleanup_errors", []
                ).append({"type": type(exc).__name__, "message": str(exc)})
        if target_bundle is not None:
            try:
                destroy_same_mesh_physical_action(target_bundle)
            except Exception as exc:
                summary.setdefault(
                    "cleanup_errors", []
                ).append({"type": type(exc).__name__, "message": str(exc)})
        if target_levels is not None:
            try:
                _destroy_task40_v10_levels(target_levels)
            except Exception as exc:
                summary.setdefault(
                    "cleanup_errors", []
                ).append({"type": type(exc).__name__, "message": str(exc)})
        if runtime is not None:
            try:
                runtime.set_phase("cleanup")
                runtime.sample("v10_candidate_post_cleanup")
            except Exception as exc:
                summary.setdefault(
                    "cleanup_errors", []
                ).append({"type": type(exc).__name__, "message": str(exc)})
            try:
                summary["allocation_admission_gates"] = allocation_gate_records
                if is_v16 or is_v17:
                    summary["allocation_admission_gate_summary"] = allocation_gate_summary
                    summary["allocation_admission_gate_storage"] = (
                        "full per-gate records are durably appended to the raw events file; "
                        "memory retains bounded grouped maxima only"
                    )
                    summary["allocation_gate_invocation_count"] = int(
                        allocation_gate_invocation_count
                    )
                _write_json(directory / "task40_v10_p6_candidate_summary.json", summary)
                runtime.marker("v10_candidate_worker_complete", summary)
                if is_v16 or is_v17:
                    events_path = Path(runtime.events_path)
                    raw_identity = _event_file_identity(events_path)
                    summary["allocation_admission_raw"] = {
                        "path": str(events_path.relative_to(directory)),
                        **raw_identity,
                        "allocation_gate_invocation_count": int(
                            allocation_gate_invocation_count
                        ),
                    }
                    admission_count = int(
                        raw_identity["allocation_admission_event_count"]
                    )
                    completion_count = int(
                        raw_identity["allocation_admission_complete_event_count"]
                    )
                    completion_gap = admission_count - completion_count
                    status = str(summary.get("status", ""))
                    ledger_passed = bool(
                        admission_count == allocation_gate_invocation_count
                        and 0 <= completion_gap <= 1
                        and (status != "PASS" or completion_gap == 0)
                    )
                    summary["allocation_admission_raw_validation"] = {
                        "admission_events_match_invocation_count": (
                            admission_count == allocation_gate_invocation_count
                        ),
                        "admission_event_count": admission_count,
                        "completion_event_count": completion_count,
                        "incomplete_admission_count": completion_gap,
                        "status_at_closeout": status,
                        "passed": ledger_passed,
                    }
                    if not ledger_passed:
                        error = {
                            "type": "V17AllocationLedgerMismatch" if is_v17 else "V16AllocationLedgerMismatch",
                            "message": (
                                "raw allocation admission/complete event counts do not "
                                "match recorded gate invocations and result status"
                            ),
                        }
                        summary.update(
                            status="FAILED",
                            official_result=False,
                            result_classification="V16_ADMISSION_LEDGER_INCONSISTENT",
                            **{
                                "v17_admission_ledger_error" if is_v17 else "v16_admission_ledger_error": error
                            },
                        )
                        if worker_result is not None:
                            worker_result["passed"] = False
                            worker_result.setdefault("errors", []).append(error["message"])
                    _write_json(directory / "task40_v10_p6_candidate_summary.json", summary)
            except Exception as exc:
                if is_v16 or is_v17:
                    prior_status = str(summary.get("status", ""))
                    error = {
                        "type": "V17AllocationLedgerEvidenceWriteFailure" if is_v17 else "V16AllocationLedgerEvidenceWriteFailure",
                        "cause_type": type(exc).__name__,
                        "message": str(exc),
                    }
                    summary.update(
                        status="FAILED",
                        official_result=False,
                        result_classification="V16_ADMISSION_LEDGER_EVIDENCE_FAILURE",
                        allocation_admission_raw_validation={
                            "passed": False,
                            "status_at_closeout": prior_status,
                            "error": error,
                        },
                        **{
                            "v17_admission_ledger_error" if is_v17 else "v16_admission_ledger_error": error
                        },
                    )
                    if worker_result is not None:
                        worker_result["passed"] = False
                        worker_result.setdefault("errors", []).append(error["message"])
                    try:
                        _write_json(directory / "task40_v10_p6_candidate_summary.json", summary)
                    except Exception as write_exc:
                        summary.setdefault("cleanup_errors", []).append(
                            {
                                "type": type(write_exc).__name__,
                                "message": str(write_exc),
                                "while_persisting_v17_ledger_failure" if is_v17 else "while_persisting_v16_ledger_failure": True,
                            }
                        )
        if v31_route_requested and runtime is not None:
            try:
                summary_path = directory / "task40_v10_p6_candidate_summary.json"
                _write_json(summary_path, summary)
                summary_bytes = summary_path.read_bytes()
                runtime.marker(
                    "task40_v31_worker_summary_product_persisted",
                    {
                        "schema": "task40extra.review_v31_worker_summary_product.v1",
                        "path": summary_path.relative_to(directory).as_posix(),
                        "sha256": hashlib.sha256(summary_bytes).hexdigest(),
                        "bytes": len(summary_bytes),
                        "source_sha": source_sha,
                        "run_id": resolved_payload.get("run_id"),
                        "scientific_input_sha256": scientific_input_sha256,
                        "status": summary.get("status"),
                        "official_result": summary.get("official_result"),
                        "cleanup_errors": list(summary.get("cleanup_errors", ())),
                    },
                )
            except Exception as exc:
                summary.setdefault("cleanup_errors", []).append(
                    {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "while_persisting_v31_worker_summary_product": True,
                    }
                )
                if worker_result is not None:
                    worker_result["passed"] = False
                    worker_result.setdefault("errors", []).append(
                        "V31 final worker-summary product receipt could not be persisted"
                    )
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


__all__ = ("run_task40_v10_p6_reference_worker",)
