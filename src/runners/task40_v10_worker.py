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
    if interior.size != expected or expected != 36_000:
        raise ValueError(
            "full p6 cell-interior RHS rows do not match the 36,000-row contract: "
            f"{interior.size} != {expected}"
        )
    return interior


def _verify_regular_inverse(
    runtime: Any,
    reference: dict[str, Any],
    physical_rhs: Any,
    physical_rhs_facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Check complete regular FE/port recovery with the live four-q factors."""

    from src.solvers.task40_v10_p6_periodic_profile import TASK40_V10_P6_PROFILE

    inverse = reference["inverse"]
    layout = reference["full_layout"]
    bundle = reference["global_bundle"]
    template = physical_rhs
    independent = np.asarray(layout.independent, dtype=np.int64)
    n = len(independent)
    modes = tuple(bundle["modes"])
    if len(modes) != 532:
        raise ValueError(f"regular reference must retain 532 modes, got {len(modes)}")
    carrier = bundle["dtn_action"].carrier
    h = np.asarray([entry.normalization_h for entry in carrier.entries], dtype=np.float64)
    if h.shape != (532,) or not np.isfinite(h).all() or np.any(h <= 0.0):
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
        np.sin(0.031 * (np.arange(532, dtype=np.float64) + 1.0))
        + 1j * np.cos(0.047 * (np.arange(532, dtype=np.float64) + 1.0))
    ).astype(np.complex128)
    port_rhs = (h * amplitudes).astype(np.complex128)
    physical_storage = np.asarray(physical_rhs.array_r, dtype=np.complex128).copy()
    if physical_storage.shape != (layout.full_rows,):
        raise ValueError("regular physical RHS does not match the full p6 storage layout")

    cases = (
        ("generic_full_independent", generic, np.zeros(532, dtype=np.complex128), np.zeros(layout.full_rows, dtype=np.complex128)),
        ("interior_only_all_36000", interior, np.zeros(532, dtype=np.complex128), np.zeros(layout.full_rows, dtype=np.complex128)),
        ("nonzero_all_mode_port_rhs", np.zeros(n, dtype=np.complex128), port_rhs, np.zeros(layout.full_rows, dtype=np.complex128)),
        ("physical_regular_incident_rhs", physical_storage[independent].copy(), np.zeros(532, dtype=np.complex128), physical_storage),
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
            recovered_alpha = bundle["dtn_action"].recover_auxiliary(solution)
            alpha_expected = recovered_alpha + g_rhs / h
            port_scale = max(
                float(np.linalg.norm(alpha))
                + float(np.linalg.norm(recovered_alpha))
                + float(np.linalg.norm(g_rhs / h)),
                np.finfo(float).tiny,
            )
            port_relative = float(np.linalg.norm(alpha - alpha_expected)) / port_scale
            solve_audit = inverse.last_solve_audit
            q_rows = [row for sector in solve_audit for row in sector["q_true_residuals"]]
            q_residual_max = max(
                (float(row["true_residual_relative"]) for row in q_rows),
                default=float("inf"),
            )
            q_coverage_passed = (
                len(q_rows) == 4 and {int(row["q"]) for row in q_rows} == {0, 1, 2, 3}
            )
            passed = bool(
                q_coverage_passed
                and
                np.isfinite(equation_relative)
                and equation_relative <= _REGULAR_ACTION_LIMIT
                and np.isfinite(port_relative)
                and port_relative <= _REGULAR_RECOVERY_LIMIT
                and np.isfinite(q_residual_max)
                and q_residual_max <= _REFERENCE_RESIDUAL_LIMIT
            )
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
                    "native_action_plus_port_rhs_storage": np.asarray(applied.array_r).copy(),
                    "full_residual_storage": np.asarray(error.array_r).copy(),
                    "port_rhs": g_rhs.copy(),
                    "returned_alpha": np.asarray(alpha, dtype=np.complex128).copy(),
                    "recovered_alpha_plus_rhs_over_h": np.asarray(
                        alpha_expected, dtype=np.complex128
                    ).copy(),
                    "native_action_relative_residual": equation_relative,
                    "regular_recovery_relative_identity": port_relative,
                    "maximum_q_true_residual_relative": q_residual_max,
                    "q_true_residuals": q_rows,
                    "limits": {
                        "native_action": _REGULAR_ACTION_LIMIT,
                        "regular_recovery": _REGULAR_RECOVERY_LIMIT,
                        "q_true_residual": _REFERENCE_RESIDUAL_LIMIT,
                    },
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
                "native_action_limit": _REGULAR_ACTION_LIMIT,
                "regular_port_closure_relative": port_relative,
                "regular_recovery_limit": _REGULAR_RECOVERY_LIMIT,
                "maximum_q_true_residual_relative": q_residual_max,
                "q_true_residuals": q_rows,
                "all_four_q_branches_exercised": q_coverage_passed,
                "regular_equation_limit": _REGULAR_ACTION_LIMIT,
                "identity_limit": _REGULAR_RECOVERY_LIMIT,
                "full_witness_packet": packet,
                "passed": passed,
            }
            if not passed:
                raise ValueError(
                    f"regular p6 inverse gate failed for {name}; full witness saved: {row}"
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
        "schema": "task40extra.review_v10_p6_regular_inverse_checks.v1",
        "profile": TASK40_V10_P6_PROFILE.identity(),
        "cases": records,
        "case_count": len(records),
        "all_four_q_exercised_per_case": True,
        "all_36000_interior_rows_exercised": True,
        "regular_equation_limit": _REGULAR_ACTION_LIMIT,
        "regular_recovery_limit": _REGULAR_RECOVERY_LIMIT,
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
                len(q_rows) != 4
                or {int(row["q"]) for row in q_rows} != {0, 1, 2, 3}
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
                "input_space": "target_p6_active_trace_plus_532_ports",
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


def _candidate_contract(resolved: Mapping[str, Any], contract: Mapping[str, Any], runtime: Any) -> dict[str, Any]:
    from src.geometry.task40_nonseparable_plan import (
        TASK40_B0_P6_CANDIDATE_RUN_ID,
        TASK40_COMPARISON_GROUP,
    )
    from src.io.physical_intermediate_profile import TASK40_V10_P6_REFERENCE_PROFILE
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE
    from src.runners.task40_v10_campaign import CAMPAIGN_SECONDS, CLOSEOUT_RESERVE_SECONDS

    solver = resolved.get("solver", {})
    execution = resolved.get("execution", {})
    method = resolved.get("method", {})
    campaign = getattr(runtime, "campaign_context", None)
    shared = getattr(runtime, "shared_budget", {})
    reserved = float(getattr(runtime, "workflow_reserved_seconds", -1.0))
    checks = {
        "run_id": resolved.get("run_id") == TASK40_B0_P6_CANDIDATE_RUN_ID,
        "comparison_group": resolved.get("comparison_group") == TASK40_COMPARISON_GROUP,
        "profile": solver.get("preconditioner") == TASK40_V10_P6_REFERENCE_PROFILE,
        "stage": solver.get("stage") == "B0_CANDIDATE" and runtime.stage == "B0_CANDIDATE",
        "method": method.get("kind") == "full3d_iterative",
        "mpi_size": execution.get("mpi_size") == 1,
        "timeout": execution.get("timeout_seconds") == CAMPAIGN_SECONDS,
        "zero_swap": execution.get("require_zero_swap") is True and runtime.require_zero_swap,
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
            contract.get("identity") == TASK40_V10_P6_REFERENCE_PROFILE
            and contract.get("scope") == "review_v10_b0_full_p6_y_orbit_reference_inverse"
            and resolved.get("derived", {}).get("physical_intermediate_profile") == contract
        ),
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"Task40 V10 p6 candidate contract failed: {failed}")
    return {
        "schema": "task40extra.review_v10_b0_candidate_worker_contract.v1",
        "checks": checks,
        "campaign_window_path": campaign["window_path"],
        "campaign_window_sha256": campaign["window_sha256"],
        "campaign_accounting_path": campaign["accounting_path"],
        "worker_reserved_seconds": reserved,
        "campaign_seconds": CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": CLOSEOUT_RESERVE_SECONDS,
        "campaign_writer": "subreaper_watchdog_only",
        "worker_accounting_access": "read_only_projection",
    }


def run_task40_v10_p6_reference_worker(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
) -> dict[str, Any]:
    """Run B0 candidate through a full p6 regular inverse and the target gap solve."""

    from mpi4py import MPI
    from petsc4py import PETSc
    from dolfinx import fem
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.io.physical_intermediate_profile import (
        TASK40_V10_P6_REFERENCE_PROFILE,
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
    from src.solvers.physical_retained_fgmres import run_retained_fgmres
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    directory = Path(run_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stage = str(resolved_payload.get("solver", {}).get("stage", ""))
    contract = profile_facts(TASK40_V10_P6_REFERENCE_PROFILE)
    summary: dict[str, Any] = {
        "schema": "task40extra.review_v10_b0_candidate_worker_summary.v1",
        "profile": TASK40_V10_P6_REFERENCE_PROFILE,
        "stage": stage,
        "source_sha": source_sha,
        "status": "STARTED",
        "official_result": False,
        "result_classification": "INCOMPLETE",
    }
    if MPI.COMM_WORLD.Get_size() != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("Task40 V10 p6 worker requires qualified MPI1 complex128")
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
            batch_identity="task40_review_v10_integrated_p6_engineering",
            evidence_prefix="v10_candidate",
            require_zero_swap=True,
        )
        summary["abi"] = _abi_facts()
        summary["campaign_authority"] = _candidate_contract(
            resolved_payload, contract, runtime
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
        if len(target_bundle["modes"]) != 532:
            raise ValueError("B0 target must retain the complete 532-mode physical inventory")

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
            and mode_inventory_preflight["target_mode_count"] == 532
            and mode_inventory_preflight["reference_mode_count"] == 532
            and mode_inventory_preflight["target_carrier_physical_generator_sha256"]
            == target_inventory[2]
            and target_bundle.get("physical_generator_manifest_sha256") == target_inventory[2]
        ):
            raise ValueError(
                "target and regular ordered physical mode identity preflight failed: "
                f"{mode_inventory_preflight}"
            )
        runtime.sample("v10_candidate_target_mesh_and_operator_complete")

        def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
            amount = int(facts.get(
                "additional_payload_bytes",
                facts.get("matrix_payload_bytes", facts.get("workspace_bytes", 0)),
            ))
            workspace = int(facts.get("workspace_bytes", 0))
            checked = runtime.check_projected(
                f"v10_{label}", amount, workspace_bytes=workspace
            )
            future = 0
            if label == "all_q_symbolic_before_any_numeric":
                estimates = facts.get("q_symbolic_estimates_bytes", {})
                if not isinstance(estimates, Mapping) or set(map(int, estimates)) != {0, 1, 2, 3}:
                    raise ValueError("all-q numeric gate requires all four actual INFOG(16/17) estimates")
                future = int(sum(int(value) for value in estimates.values()))
                future += int(facts.get("future_retained_krylov_and_vector_bytes", 0))
            headroom = 128 << 20
            live = runtime.sample(f"v10_{label}_strict_admission")
            profile_cap = int(contract["resources"]["process_tree_rss_cap_bytes"])
            cap = min(profile_cap, int(live["launch_cap_bytes"]))
            projected = (
                int(live["rss_bytes"]) + amount + workspace + future + headroom
            )
            admission = {
                "schema": "task40extra.review_v10_allocation_admission.v1",
                "label": str(label),
                "requested_additional_bytes": amount,
                "requested_workspace_bytes": workspace,
                "all_q_native_symbolic_estimate_bytes": future,
                "fixed_future_workspace_headroom_bytes": headroom,
                "current_process_tree_rss_bytes": int(live["rss_bytes"]),
                "profile_tree_cap_bytes": profile_cap,
                "dynamic_launch_cap_bytes": int(live["launch_cap_bytes"]),
                "effective_finite_cap_bytes": cap,
                "projected_process_tree_rss_bytes": projected,
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
            }
            allocation_gate_records.append(admission)
            runtime.marker("v10_strict_allocation_admission", admission)
            if projected >= cap:
                from .physical_p4_schur_v14 import V14ResourceStop

                raise V14ResourceStop(
                    f"Task40 V10 finite all-object memory admission failed: {admission}"
                )
            runtime.sample(f"v10_{label}_allocation_gate")

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
        if (
            target_action.condensed.full_rows != 55_950
            or target_action.condensed.active_rows != 16_992
            or target_action.condensed.active_interior_rows != 36_000
            or target_action.condensed.appended_rows != 532
        ):
            raise ValueError("actual target p6 trace+port retained inventory differs from B0 contract")
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

        runtime.sample("v10_candidate_target_retained_and_fast_backend_complete")

        reference = build_task40_v10_p6_reference_inverse(
            cfg,
            axes,
            allocation_gate=allocation_gate,
            event=runtime.marker,
            identity_gate=identity_gate,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        if not mode_identity:
            raise RuntimeError("regular p6 physical identity callback did not run before q factors")
        mapping_identity = _mapping_identity(reference)
        ref_rhs, ref_rhs_facts = build_physical_rhs(reference["global_bundle"])
        regular_checks = _verify_regular_inverse(
            runtime, reference, ref_rhs, ref_rhs_facts
        )
        ref_rhs.destroy()
        ref_rhs = None
        if not regular_checks["passed"]:
            raise ValueError("complete regular p6 inverse checks did not pass")
        runtime.marker("v10_regular_reference_inverse_qualified", regular_checks)

        physical_rhs, rhs_facts = build_physical_rhs(target_bundle)
        rhs_norm = float(physical_rhs.norm())
        if not np.isfinite(rhs_norm) or rhs_norm <= 0.0:
            raise ValueError("B0 target physical RHS must be finite and nonzero")
        reduced_rhs_values = target_action.reduce_rhs(
            physical_rhs, rhs_is_mpc_dual=True
        )
        rhs = target_action.create_reduced_rhs_vector()
        _assign_vector_storage(rhs, reduced_rhs_values)
        reduced_rhs_norm = float(rhs.norm())
        if not np.isfinite(reduced_rhs_norm) or reduced_rhs_norm <= 0.0:
            raise ValueError("B0 retained trace+port RHS must be finite and nonzero")
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
            "all_36000_cell_interior_rows_evaluated": True,
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
                "all_36000_cell_interior_rows_evaluated": True,
                "mode_identity": mode_identity,
            },
        )
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
                result_classification="B0_CANDIDATE_FULL_A6_OR_IDENTITY_GATE_FAIL",
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
            and output.get("diffraction_channel_count") == 532
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
                    "<v10_candidate_official_output.json>"
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
                if output_pass
                else "B0_CANDIDATE_PHYSICAL_OUTPUT_GATE_FAIL"
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
