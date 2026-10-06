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
import time
import copy
from pathlib import Path
from typing import Any, Mapping

import numpy as np


_REFERENCE_RESIDUAL_LIMIT = 1.0e-10
_REGULAR_ACTION_LIMIT = 1.0e-11
_REGULAR_RECOVERY_LIMIT = 1.0e-11
_MAPPING_IDENTITY_LIMIT = 1.0e-12
_A6_RESIDUAL_LIMIT = 1.0e-6
_PORT_CLOSURE_LIMIT = 1.0e-8
_IDENTITY_LIMIT = 1.0e-10


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

    # np.savez is uncompressed.  Reserve every array byte plus a conservative
    # per-member/header margin, then reconcile the actual files immediately.
    projected = int(_packet_array_bytes(payload) * 1.05) + (2 << 20)
    _disk_admit(runtime, additional_bytes=projected, label=f"packet:{name}")
    packet_target = runtime.directory / name
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
        np.linalg.norm(layout.cell_dft.conj().T @ layout.cell_dft - np.eye(4))
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
    if len(sectors) != 2 or [int(row["context"].twist_index) for row in sectors] != [0, 1]:
        raise ValueError("regular action witness requires both ordered two-cell twists")
    max_local_rows = max(int(row["entities"].full_rows) for row in sectors)
    max_local_independent = max(len(row["entities"].independent) for row in sectors)
    allocation_gate(
        "task40_v10_regular_sector_forward_action",
        {
            "additional_payload_bytes": 16
            * (2 * layout.independent_rows + 4 * max_local_rows + 2 * max_local_independent),
            "workspace_bytes": 16 * (layout.independent_rows + 2 * max_local_rows),
            "twist_count": 2,
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
        local_ports = ports[mode_ids] / np.sqrt(2.0)
        local_alpha = alpha[mode_ids] * np.sqrt(2.0)
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
        "all_four_q_true_residuals": bool(
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
            "all_four_q_true_residuals": _REFERENCE_RESIDUAL_LIMIT,
        },
    }


def _verify_regular_inverse(
    runtime: Any,
    reference: dict[str, Any],
    physical_rhs: Any,
    physical_rhs_facts: Mapping[str, Any],
    *,
    allocation_gate: Any,
) -> dict[str, Any]:
    """Check complete regular FE/port recovery with the live four-q factors."""

    from src.solvers.p6_cell_condensed_action import _operation_relative
    from petsc4py import PETSc

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
    physical_storage = np.asarray(physical_rhs.array_r, dtype=np.complex128).copy()
    if physical_storage.shape != (layout.full_rows,):
        raise ValueError("regular physical RHS does not match the full p6 storage layout")

    cases = (
        ("generic_full_independent", generic, np.zeros(profile.mode_count, dtype=np.complex128), np.zeros(layout.full_rows, dtype=np.complex128)),
        (f"interior_only_all_{profile.global_interior_rows}", interior, np.zeros(profile.mode_count, dtype=np.complex128), np.zeros(layout.full_rows, dtype=np.complex128)),
        ("nonzero_all_mode_port_rhs", np.zeros(n, dtype=np.complex128), port_rhs, np.zeros(layout.full_rows, dtype=np.complex128)),
        ("physical_regular_incident_rhs", physical_storage[independent].copy(), np.zeros(profile.mode_count, dtype=np.complex128), physical_storage),
    )
    records = []
    for name, fe_rhs, g_rhs, full_rhs_values in cases:
        runtime.sample(f"v10_regular_inverse_{name}_before")
        solution_values, alpha = inverse.apply_augmented(fe_rhs, port_rhs=g_rhs)
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
                equation_relative = float(error.norm()) / equation_scale
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
            port_relative = float(np.linalg.norm(alpha - alpha_expected)) / port_scale

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
            builder_action_storage = np.zeros(layout.full_rows, dtype=np.complex128)
            builder_action_storage[independent] = sector_action
            packet = _save_packet(
                runtime,
                f"v10_regular_inverse_{name}",
                {
                    "schema": "task40extra.review_v10_regular_inverse_full_witness.v1",
                    "case": name,
                    "passed": passed,
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
                    "original_regular_equation_limit": _REFERENCE_RESIDUAL_LIMIT,
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
                },
            )
            row = {
                "name": name,
                "fe_rhs_nonzero_count": int(np.count_nonzero(fe_rhs)),
                "fe_rhs_norm": float(np.linalg.norm(fe_rhs)),
                "port_rhs_nonzero_count": int(np.count_nonzero(g_rhs)),
                "port_rhs_norm": float(np.linalg.norm(g_rhs)),
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
                "regular_recovery_limit": _REGULAR_RECOVERY_LIMIT,
                "maximum_q_true_residual_relative": q_residual_max,
                "q_true_residuals": q_rows,
                "all_four_q_branches_exercised": q_coverage_passed,
                "expected_port_mode_count": profile.mode_count,
                "all_port_modes_exercised": recovery["port_mode_count"] == profile.mode_count,
                "regular_equation_limit": _REFERENCE_RESIDUAL_LIMIT,
                "identity_limit": _REGULAR_RECOVERY_LIMIT,
                "full_witness_packet": packet,
                "gates": gate_facts["gates"],
                "failed_gates": gate_facts["failed_gates"],
                "passed": passed,
            }
            runtime.marker(f"v10_regular_inverse_{name}_evaluated", row)
            if not passed:
                raise ValueError(
                    f"regular p6 inverse gates failed for {name}: "
                    f"{gate_facts['failed_gates']}; full witness saved: {row}"
                )
            records.append(row)
            runtime.marker(f"v10_regular_inverse_{name}_complete", row)
        finally:
            if error is not None:
                error.destroy()
            port_load.destroy()
            applied.destroy()
            solution.destroy()
        runtime.sample(f"v10_regular_inverse_{name}_after")

    return {
        "schema": (
            "task40extra.review_v10_p6_regular_inverse_checks.v1"
            if profile.name == TASK40_V10_P6_PROFILE.name
            else "task40extra.review_v11_p6_regular_inverse_checks.v1"
        ),
        "profile": profile.identity(),
        "cases": records,
        "case_count": len(records),
        "all_four_q_exercised_per_case": True,
        "interior_rows_exercised_per_case": profile.global_interior_rows,
        "all_port_modes_exercised_per_case": profile.mode_count,
        "regular_equation_limit": _REFERENCE_RESIDUAL_LIMIT,
        "sector_native_action_consistency_limit": _REGULAR_ACTION_LIMIT,
        "regular_recovery_limit": _REGULAR_RECOVERY_LIMIT,
        "all_port_equation_limit": _PORT_CLOSURE_LIMIT,
        "native_action_recovery_identity_limit": _IDENTITY_LIMIT,
        "schur_port_recovery_identity_limit": _IDENTITY_LIMIT,
        "q_true_residual_limit": _REFERENCE_RESIDUAL_LIMIT,
        "physical_rhs_facts": dict(physical_rhs_facts),
        "passed": len(records) == 4 and all(row["passed"] for row in records),
    }


class _P6ReferencePreconditioner:
    """Apply the regular two-cell inverse on the target trace+port space."""

    def __init__(
        self, runtime: Any, owner: dict[str, Any], target_action: Any, target_carrier: Any
    ):
        from petsc4py import PETSc

        self.runtime = runtime
        self.PETSc = PETSc
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
        self.last_facts = {
            "maximum_q_true_residual_relative": 0.0,
            "port_identity_relative": 0.0,
            "q_true_residuals": [],
        }

    def apply(self, source: Any):
        self.runtime.sample(f"v10_p6_reference_pc_{self.calls + 1}_before")
        source_values = np.asarray(source.array_r, dtype=np.complex128)
        if source_values.shape != (self.target_action.reduced_size,):
            raise ValueError("Task40 V10 p6 preconditioner input has the wrong retained layout")
        injected = self.target_action.inject_trace_port(source_values)
        port_rhs = source_values[self.target_condensed.active_rows :].copy()
        solution_values, alpha = self.inverse.apply_augmented(
            injected[self.independent], port_rhs=port_rhs
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
                or q_relative > _REFERENCE_RESIDUAL_LIMIT
                or not np.isfinite(port_relative)
                or port_relative > _IDENTITY_LIMIT
            ):
                raise FloatingPointError(
                    "Task40 V10 p6 inverse apply failed q or port identity gate: "
                    f"q={q_relative}, port={port_relative}"
                )
            self.calls += 1
            self.last_facts = {
                "call": self.calls,
                "input_space": f"target_p6_active_trace_plus_{self.profile.mode_count}_ports",
                "reference_rhs_injected_by_target_JH": True,
                "target_active_rows": int(self.target_condensed.active_rows),
                "target_port_rows": int(self.target_condensed.appended_rows),
                "maximum_q_true_residual_relative": q_relative,
                "port_identity_relative": port_relative,
                "q_true_residuals": q_rows,
                "all_four_q_used": True,
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
        facts = {"calls": int(self.calls), "last_facts": dict(self.last_facts)}
        self.target_action = None
        self.target_condensed = None
        self.reference = None
        self.layout = None
        self.inverse = None
        self.owner = None
        return facts


def _candidate_contract(
    resolved: Mapping[str, Any],
    contract: Mapping[str, Any],
    runtime: Any,
    *,
    profile_identity: str,
) -> dict[str, Any]:
    from src.geometry.task40_nonseparable_plan import (
        TASK40_B0_P6_CANDIDATE_RUN_ID,
        TASK40_COMPARISON_GROUP,
        TASK40_GX560_V11_P6_RUN_ID,
        TASK40_GX784_V11_P6_RUN_ID,
    )
    from src.io.physical_intermediate_profile import (
        TASK40_V10_P6_REFERENCE_PROFILE,
        TASK40_V11_P6_GX560_PROFILE,
        TASK40_V11_P6_GX784_PROFILE,
    )
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE
    from src.runners.task40_v10_campaign import CAMPAIGN_SECONDS, CLOSEOUT_RESERVE_SECONDS

    solver = resolved.get("solver", {})
    execution = resolved.get("execution", {})
    method = resolved.get("method", {})
    campaign = getattr(runtime, "campaign_context", None)
    shared = getattr(runtime, "shared_budget", {})
    reserved = float(getattr(runtime, "workflow_reserved_seconds", -1.0))
    case_identity = {
        TASK40_V10_P6_REFERENCE_PROFILE: (TASK40_B0_P6_CANDIDATE_RUN_ID, "B0_CANDIDATE", 16.0),
        TASK40_V11_P6_GX560_PROFILE: (TASK40_GX560_V11_P6_RUN_ID, "Q4_ORIGINAL", 16.0),
        TASK40_V11_P6_GX784_PROFILE: (TASK40_GX784_V11_P6_RUN_ID, "Q4_ORIGINAL", 16.0),
    }
    try:
        expected_run_id, expected_stage, expected_memory_limit = case_identity[profile_identity]
    except KeyError as exc:
        raise ValueError(f"unsupported Task40 p6 reference profile: {profile_identity}") from exc
    input_timeout = execution.get("timeout_seconds")
    timeout_passed = input_timeout == CAMPAIGN_SECONDS
    is_v10 = profile_identity == TASK40_V10_P6_REFERENCE_PROFILE
    checks = {
        "run_id": resolved.get("run_id") == expected_run_id,
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
        "reserved_time": np.isfinite(reserved) and 0.0 < reserved <= CAMPAIGN_SECONDS - CLOSEOUT_RESERVE_SECONDS,
        "profile_contract": (
            contract.get("identity") == profile_identity
            and isinstance(contract.get("scope"), str)
            and contract.get("scope")
            == resolved.get("derived", {}).get("physical_intermediate_profile", {}).get("scope")
            and resolved.get("derived", {}).get("physical_intermediate_profile") == contract
        ),
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"Task40 p6 reference worker contract failed: {failed}")
    return {
        "schema": (
            "task40extra.review_v10_b0_candidate_worker_contract.v1"
            if is_v10
            else "task40extra.review_v11_p6_grid_worker_contract.v1"
        ),
        "checks": checks,
        "campaign_window_path": campaign["window_path"],
        "campaign_window_sha256": campaign["window_sha256"],
        "campaign_accounting_path": campaign["accounting_path"],
        "worker_reserved_seconds": reserved,
        "campaign_seconds": CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": CLOSEOUT_RESERVE_SECONDS,
        "effective_wall_clock_authority": "existing_V11_fixed_deadline_and_cumulative_remaining",
        "campaign_writer": "subreaper_watchdog_only",
        "worker_accounting_access": "read_only_projection",
    }


def run_task40_v10_p6_reference_worker(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
    profile_identity: str | None = None,
    share_transform_bank: bool = False,
) -> dict[str, Any]:
    """Run a frozen Task40 p6 case with one live four-q periodic reference."""

    from mpi4py import MPI
    from petsc4py import PETSc
    from dolfinx import fem
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.io.physical_intermediate_profile import (
        TASK40_V10_P6_REFERENCE_PROFILE,
        TASK40_V11_P6_GX560_PROFILE,
        TASK40_V11_P6_GX784_PROFILE,
        profile_facts,
    )
    from src.runners.physical_p4_schur_v14 import (
        V14ResourceStop,
        _V14Runtime,
        _abi_facts,
        _repo_root,
        _write_json,
    )
    from src.solvers.dtn_boundary_phase_gauge import BOUNDARY_PLANE
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
    from src.solvers.task40_v10_p6_yorbit import (
        build_task40_v10_p6_reference_inverse,
        destroy_task40_v10_p6_reference_inverse,
        _destroy_task40_v10_levels,
    )
    from src.solvers.task40_v10_p6_periodic_profile import (
        TASK40_P6_PERIODIC_PROFILES,
    )
    from src.solvers.physical_retained_fgmres import run_retained_fgmres
    from src.solvers.task40_v10_p6_mumps import full_p6_pre_release_output_inventory
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    directory = Path(run_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stage = str(resolved_payload.get("solver", {}).get("stage", ""))
    profile_identity = profile_identity or str(
        resolved_payload.get("solver", {}).get("preconditioner", "")
    )
    if profile_identity not in (
        TASK40_V10_P6_REFERENCE_PROFILE,
        TASK40_V11_P6_GX560_PROFILE,
        TASK40_V11_P6_GX784_PROFILE,
    ):
        raise ValueError(f"unsupported Task40 p6 reference profile: {profile_identity}")
    if type(share_transform_bank) is not bool:
        raise TypeError("V12 transform-bank selection must be an explicit boolean")
    periodic_profile = TASK40_P6_PERIODIC_PROFILES[profile_identity]
    is_v10 = profile_identity == TASK40_V10_P6_REFERENCE_PROFILE
    case_label = (
        "b0"
        if is_v10
        else "gx560"
        if profile_identity == TASK40_V11_P6_GX560_PROFILE
        else "gx784"
    )
    evidence_prefix = "v10_candidate" if is_v10 else "v11_p6_grid"
    contract = profile_facts(profile_identity)
    summary: dict[str, Any] = {
        "schema": (
            "task40extra.review_v10_b0_candidate_worker_summary.v1"
            if is_v10
            else "task40extra.review_v11_p6_grid_candidate_worker_summary.v1"
        ),
        "profile": profile_identity,
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
    reference = None
    rhs = None
    physical_rhs = None
    final_full_solution = None
    final_solution = None
    pc = None
    reference_audit_snapshot = None
    allocation_gate_records: list[dict[str, Any]] = []
    handlers: dict[int, Any] = {}
    outer_started = False
    result: dict[str, Any] | None = None
    try:
        runtime = _V14Runtime(
            directory,
            stage,
            contract,
            root=_repo_root(),
            source_sha=source_sha,
            batch_identity=(
                "task40_review_v10_integrated_p6_engineering"
                if is_v10
                else f"task40_review_v11_{case_label}_p6_y_orbit"
            ),
            evidence_prefix=evidence_prefix,
            require_zero_swap=True,
        )
        summary["abi"] = _abi_facts(
            profile_identity=profile_identity,
        )
        summary["campaign_authority"] = _candidate_contract(
            resolved_payload, contract, runtime, profile_identity=profile_identity
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
        axis_plan = _stage4_axis_plan(cfg, MPI.COMM_SELF.Get_size())
        axes = {
            "x": tuple(map(float, axis_plan.x_values)),
            "y": tuple(map(float, axis_plan.y_values)),
            "z": tuple(map(float, axis_plan.z_values)),
        }
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
        target_inventory = build_dynamic_mode_inventory(cfg)
        reference_inventory = build_dynamic_mode_inventory(regular_cfg)
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
        runtime.sample("v10_candidate_target_mesh_and_operator_complete")

        def allocation_gate(label: str, facts: Mapping[str, Any]) -> dict[str, Any]:
            amount = int(facts.get(
                "additional_payload_bytes",
                facts.get("matrix_payload_bytes", facts.get("workspace_bytes", 0)),
            ))
            workspace = int(facts.get("workspace_bytes", 0))
            checked = runtime.check_projected(
                f"v10_{label}", amount, workspace_bytes=workspace
            )
            future = 0
            future_components: dict[str, int] = {}
            if label == "all_q_symbolic_before_any_numeric":
                estimates = facts.get("q_symbolic_estimates_bytes", {})
                if not isinstance(estimates, Mapping) or set(map(int, estimates)) != {0, 1, 2, 3}:
                    raise ValueError("all-q numeric gate requires all four actual INFOG(16/17) estimates")
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
                if (
                    share_transform_bank
                    and (
                        int(facts.get("full_storage_rows_for_future_recovery", 0)) <= 0
                        or not isinstance(phase_inventory, Mapping)
                        or phase_inventory.get("actual_target_and_reference_full_rows_match_required") is not True
                    )
                ):
                    raise ValueError("V12 all-q gate lacks actual target/reference full-row recovery dimensions")
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
            profile_cap = int(contract["resources"]["process_tree_rss_cap_bytes"])
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
            runtime.marker("v10_strict_allocation_admission_complete", admission)
            return admission

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
            preserve_exact_geometry=True,
            allocation_gate=allocation_gate,
        )
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
        target_condensed = None
        _validate_target_p6_inventory(target_action.condensed, periodic_profile)
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
        mode_identity: dict[str, Any] = {}

        def identity_gate(reference_bundle: Mapping[str, Any], reference_levels: Mapping[str, Any]):
            mode_identity.update(
                _validate_reference_physical_identity(
                    target_bundle, target_levels, reference_bundle, reference_levels
                )
            )

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
            if name == "task40_v12_mumps_symbolic_q_complete":
                q = int(facts["q"])
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

        reference = build_task40_v10_p6_reference_inverse(
            cfg,
            axes,
            allocation_gate=allocation_gate,
            profile=periodic_profile,
            event=reference_event,
            identity_gate=identity_gate,
            jit_options=SAME_MESH_JIT_OPTIONS,
            share_transform_bank=share_transform_bank,
            target_full_storage_rows=int(target_action.condensed.full_rows),
        )
        if not mode_identity:
            raise RuntimeError("regular p6 physical identity callback did not run before q factors")
        mapping_identity = _mapping_identity(reference)
        ref_rhs, ref_rhs_facts = build_physical_rhs(reference["global_bundle"])
        regular_checks = _verify_regular_inverse(
            runtime,
            reference,
            ref_rhs,
            ref_rhs_facts,
            allocation_gate=allocation_gate,
        )
        ref_rhs.destroy()
        ref_rhs = None
        if not regular_checks["passed"]:
            raise ValueError("complete regular p6 inverse checks did not pass")
        runtime.marker("v10_regular_reference_inverse_qualified", regular_checks)

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
        }
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
        )

        pc = _P6ReferencePreconditioner(
            runtime, reference, target_action, target_bundle["dtn_action"].carrier
        )
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
        }
        pc_snapshot = pc.detach()
        summary["reference_audit_snapshot"] = reference_audit_snapshot
        summary["reference_pc_audit_before_detach"] = pc_snapshot
        summary["target_backend_final_audit"] = dict(
            target_fast_bundle["physical_action"].audit
        )
        summary["target_native_witness_final_audit"] = dict(
            target_bundle["physical_action"].audit
        )
        summary["target_condensed_action_final_audit"] = dict(target_action.audit)
        summary["allocation_admission_gates"] = allocation_gate_records
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
            and identity_metrics["reference_pc_port_identity_relative"] <= _IDENTITY_LIMIT
            and identity_metrics["maximum_q_true_residual_relative"] <= _REFERENCE_RESIDUAL_LIMIT
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
            return {"passed": False, "errors": [summary["result_classification"]], "summary": summary}

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
            and output.get("diffraction_channel_count") == periodic_profile.mode_count
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
        return {
            "passed": bool(output_pass),
            "errors": [] if output_pass else ["physical R/T/A output gates failed"],
            "summary": summary,
            "numerical_output_directory": str(output_directory),
        }
    except V14ResourceStop as exc:
        summary.update(
            status="CONTROLLED_STOP",
            official_result=False,
            result_classification=getattr(exc, "classification", "RESOURCE_CONTROLLED_STOP"),
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        return {"passed": False, "errors": [str(exc)], "summary": summary}
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
                        "snapshot_before_failure_cleanup": True,
                    }
                    summary["reference_audit_snapshot"] = reference_audit_snapshot
                destroy_task40_v10_p6_reference_inverse(reference)
            except Exception as exc:
                summary.setdefault(
                    "cleanup_errors", []
                ).append({"type": type(exc).__name__, "message": str(exc)})
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
                _write_json(directory / "task40_v10_p6_candidate_summary.json", summary)
                runtime.marker("v10_candidate_worker_complete", summary)
            except Exception:
                pass
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


__all__ = ("run_task40_v10_p6_reference_worker",)
