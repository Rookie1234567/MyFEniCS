"""Small V4 compatibility audit for frozen exact-side authority outputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from petsc4py import PETSc


V4_EXACT_AUTHORITY_LABELS = (
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
)
V4_EXACT_AUTHORITY_FAILURE = "EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F"
V4_EXACT_AUTHORITY_PASS = "EXACT_AUTHORITY_COMPATIBLE_WITH_CURRENT_BARE_F"
V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE = "CANONICAL_SOURCE_ROW_BINDING_UNAVAILABLE"
V4_CANONICAL_SOURCE_BINDING_REASON = (
    "canonical source-row binding unavailable/incompatible"
)
V4_CANONICAL_SOURCE_BRIDGE_NOT_QUALIFIED = "CANONICAL_SOURCE_BRIDGE_NOT_QUALIFIED"

__all__ = (
    "V4_CANONICAL_SOURCE_BINDING_REASON",
    "V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE",
    "V4_CANONICAL_SOURCE_BRIDGE_NOT_QUALIFIED",
    "V4_EXACT_AUTHORITY_FAILURE",
    "V4_EXACT_AUTHORITY_LABELS",
    "V4_EXACT_AUTHORITY_PASS",
    "audit_exact_authority_petsc",
    "inspect_canonical_source_authority",
    "canonical_binding_failure_audit",
)


def _authority_descriptor(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    direct = record.get("canonical_source_authority")
    if isinstance(direct, Mapping):
        return direct
    shards = record.get("shards")
    if not isinstance(shards, Sequence) or isinstance(shards, (str, bytes)):
        return None
    descriptors = [
        shard.get("canonical_source_authority")
        for shard in shards
        if isinstance(shard, Mapping)
    ]
    if not descriptors or any(not isinstance(item, Mapping) for item in descriptors):
        return None
    first = dict(descriptors[0])
    if any(dict(item) != first for item in descriptors[1:]):
        return None
    return first


def _valid_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def inspect_canonical_source_authority(
    spool: Mapping[str, Mapping[str, Any]],
    *,
    labels: Sequence[str] = V4_EXACT_AUTHORITY_LABELS,
) -> dict[str, Any]:
    """Inspect the persisted source-row descriptor, without loading map values."""

    labels = tuple(labels)
    required_fields = (
        "map_path",
        "map_sha256",
        "source_sha",
        "run_identity_sha256",
        "partition_sha256",
        "key_set_sha256",
    )
    entries: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    malformed: list[str] = []
    consistency_values: dict[str, set[Any]] = {
        "source_sha": set(),
        "run_identity_sha256": set(),
        "partition_sha256": set(),
    }
    for label in labels:
        label_record = spool.get(label)
        if not isinstance(label_record, Mapping):
            for role in ("rhs", "exact_output"):
                missing.append(f"{label}:{role}")
            continue
        entries[label] = {}
        for role in ("rhs", "exact_output"):
            role_record = label_record.get(role)
            descriptor = (
                _authority_descriptor(role_record)
                if isinstance(role_record, Mapping)
                else None
            )
            key = f"{label}:{role}"
            if descriptor is None:
                missing.append(key)
                entries[label][role] = {
                    "descriptor_available": False,
                    "reason": V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE,
                    "ownership_ranges": [
                        list(map(int, shard.get("ownership_range", ())))
                        for shard in role_record.get("shards", ())
                        if isinstance(shard, Mapping)
                        and isinstance(shard.get("ownership_range"), Sequence)
                    ]
                    if isinstance(role_record, Mapping)
                    else [],
                }
                continue
            invalid = [field for field in required_fields if field not in descriptor]
            valid = not invalid and bool(
                isinstance(descriptor.get("map_path"), str)
                and _valid_hex(descriptor.get("map_sha256"), 64)
                and _valid_hex(descriptor.get("source_sha"), 40)
                and _valid_hex(descriptor.get("run_identity_sha256"), 64)
                and _valid_hex(descriptor.get("partition_sha256"), 64)
                and _valid_hex(descriptor.get("key_set_sha256"), 64)
            )
            if not valid:
                malformed.append(key)
            for field in consistency_values:
                if field in descriptor:
                    consistency_values[field].add(descriptor[field])
            entries[label][role] = {
                "descriptor_available": bool(valid),
                "descriptor": dict(descriptor),
                "invalid_fields": invalid,
                "ownership_ranges": [
                    list(map(int, shard.get("ownership_range", ())))
                    for shard in role_record.get("shards", ())
                    if isinstance(shard, Mapping)
                    and isinstance(shard.get("ownership_range"), Sequence)
                ]
                if isinstance(role_record, Mapping)
                else [],
            }
    inconsistent = [
        field for field, values in consistency_values.items() if len(values) > 1
    ]
    descriptor_complete = bool(not missing and not malformed and not inconsistent)
    bridge_qualified = False
    if descriptor_complete:
        failure_code = V4_CANONICAL_SOURCE_BRIDGE_NOT_QUALIFIED
        failure_reason = "canonical source bridge content/hash/equality/reconstruction is not qualified"
    else:
        failure_code = V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE
        failure_reason = V4_CANONICAL_SOURCE_BINDING_REASON
    return {
        "required_roles": ["rhs", "exact_output"],
        "labels": list(labels),
        "descriptor_complete": descriptor_complete,
        "bridge_qualified": bridge_qualified,
        "descriptor_available": descriptor_complete,
        "pass": False,
        "reason": failure_reason,
        "failure_code": failure_code,
        "missing_entries": missing,
        "malformed_entries": malformed,
        "inconsistent_fields": inconsistent,
        "entries": entries,
        "raw_global_row_remap_forbidden": True,
        "array_hash_validation_only": None,
        "numeric_vectors_constructed": False,
        "values_retained": False,
        "raw_npy_mmap_hash_read": None,
        "canonical_map_opened": False,
        "canonical_map_content_hash_verified": False,
        "source_current_key_equality_verified": False,
        "canonical_reconstruction_verified": False,
    }


def canonical_binding_failure_audit(
    *,
    identity: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    labels: Sequence[str] = V4_EXACT_AUTHORITY_LABELS,
) -> dict[str, Any]:
    """Build an identity stop before PETSc Vec/numeric reconstruction/system setup."""

    labels = tuple(labels)
    factor_inventory = {
        "exact_output_vectors_loaded": 0,
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "cross_section_group_factor_count": 0,
        "reduced_dense_factor_count": 0,
        "factor_objects_created": 0,
    }
    return {
        "schema": "task040.v4.exact_authority_compatibility.v1",
        "labels": list(labels),
        "identity": dict(identity),
        "identity_pass": False,
        "operator_identity": {
            "bare_f": "not_run_by_identity_gate",
            "a_side": "not_run_by_identity_gate",
        },
        "source_binding": dict(source_binding),
        "reports": [],
        "residual_status": "not_run_by_identity_gate",
        "bare_f_residual": "not_run_by_identity_gate",
        "a_side_explanatory_residual": "not_run_by_identity_gate",
        "exact_output_vectors_loaded": 0,
        "finite_pass": None,
        "bare_f_residual_pass": None,
        "repeat_pass": None,
        "bare_f_hash_unchanged_pass": None,
        "factor_inventory": factor_inventory,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "cleanup": {
            "factor_objects_created": 0,
            "interface_masses_built": False,
            "packet_built": False,
        },
        "classification": V4_EXACT_AUTHORITY_FAILURE,
        "failure_code": str(
            source_binding.get("failure_code", V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE)
        ),
        "failure_reason": str(
            source_binding.get("reason", V4_CANONICAL_SOURCE_BINDING_REASON)
        ),
        "numerical_gate_pass": None,
        "gate_pass": False,
        "downstream": {
            "projection": "not_run_by_gate",
            "lift": "not_run_by_gate",
            "trace": "not_run_by_gate",
            "dual": "not_run_by_gate",
            "response": "not_run_by_gate",
            "fgmres": "not_run_by_gate",
            "coarse": "not_run_by_gate",
            "level_b": "not_run_by_gate",
            "full_hybrid": "not_run_by_gate",
            "h3": "not_run_by_gate",
        },
    }


def _operator_identity(
    operator: PETSc.Mat,
    name: str,
) -> dict[str, Any]:
    rows, columns = map(int, operator.getSize())
    identity = {
        "name": name,
        "semantic": "explicit bare components.F"
        if name == "bare_f"
        else "system.A = F - C H^-1 D action",
        "petsc_type": str(operator.getType()),
        "shape": [rows, columns],
        "global_size": [rows, columns],
        "local_size": list(map(int, operator.getLocalSize())),
        "ownership_range": list(map(int, operator.getOwnershipRange())),
        "block_size": int(operator.getBlockSize()),
        "matrix_free": str(operator.getType()).lower() in {"python", "shell"},
    }
    if name == "a_side":
        identity["action_identity"] = "system.A = F - C H^-1 D"
    return identity


def _apply_residual(
    operator: PETSc.Mat,
    exact: PETSc.Vec,
    rhs: PETSc.Vec,
) -> tuple[float, float, bool]:
    first = rhs.duplicate()
    repeat = rhs.duplicate()
    difference = rhs.duplicate()
    try:
        operator.mult(exact, first)
        operator.mult(exact, repeat)
        difference.waxpy(PETSc.ScalarType(-1.0), repeat, first)
        rhs_norm = float(rhs.norm())
        residual = first.duplicate()
        try:
            first.copy(residual)
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            residual_relative = float(residual.norm()) / max(rhs_norm, 1.0e-30)
        finally:
            residual.destroy()
        repeat_relative = float(difference.norm()) / max(float(first.norm()), 1.0e-30)
        finite = bool(
            np.isfinite(rhs_norm)
            and np.isfinite(residual_relative)
            and np.isfinite(repeat_relative)
        )
        return residual_relative, repeat_relative, finite
    finally:
        difference.destroy()
        repeat.destroy()
        first.destroy()


def audit_exact_authority_petsc(
    bare_f: PETSc.Mat,
    side_operator: PETSc.Mat,
    rhs_vectors: Mapping[str, PETSc.Vec],
    exact_vectors: Mapping[str, PETSc.Vec],
    *,
    source_metadata: Mapping[str, Mapping[str, Any]],
    exact_output_identity_sha256: Mapping[str, str],
    identity: Mapping[str, Any],
    bare_matrix_hash: Callable[[PETSc.Mat], str],
    labels: Sequence[str] = V4_EXACT_AUTHORITY_LABELS,
) -> dict[str, Any]:
    """Compare frozen exact outputs against bare ``F`` and explanatory ``A``.

    ``side_operator`` is recorded as the historical explanatory
    ``A_side = F - C H^-1 D`` action.  It never substitutes for the bare-F
    residual Gate.  The helper intentionally owns no factors or interface
    data; all five vectors are borrowed and remain caller-owned.
    """

    labels = tuple(labels)
    if labels != V4_EXACT_AUTHORITY_LABELS:
        raise ValueError("V4 exact authority labels are not the frozen five labels")
    if set(rhs_vectors) != set(labels) or set(exact_vectors) != set(labels):
        raise ValueError("V4 exact authority vectors do not cover the frozen labels")
    if set(source_metadata) != set(labels):
        raise ValueError("V4 RHS probe metadata does not cover the frozen labels")
    if set(exact_output_identity_sha256) != set(labels):
        raise ValueError("V4 exact-output identities do not cover the frozen labels")

    bare_hash_before = str(bare_matrix_hash(bare_f))
    reports: list[dict[str, Any]] = []
    for label in labels:
        bare_relative, bare_repeat, bare_finite = _apply_residual(
            bare_f, exact_vectors[label], rhs_vectors[label]
        )
        side_relative, side_repeat, side_finite = _apply_residual(
            side_operator, exact_vectors[label], rhs_vectors[label]
        )
        reports.append(
            {
                "label": label,
                "source_probe_metadata": dict(source_metadata[label]),
                "exact_output_identity_sha256": str(
                    exact_output_identity_sha256[label]
                ),
                "bare_f": {
                    "residual_relative": bare_relative,
                    "repeat_relative": bare_repeat,
                    "finite": bare_finite,
                },
                "a_side_explanatory": {
                    "residual_relative": side_relative,
                    "repeat_relative": side_repeat,
                    "finite": side_finite,
                },
            }
        )
    bare_hash_after = str(bare_matrix_hash(bare_f))
    bare_pass = all(
        row["bare_f"]["finite"] is True and row["bare_f"]["residual_relative"] <= 1.0e-9
        for row in reports
    )
    all_finite = all(
        row["bare_f"]["finite"] is True and row["a_side_explanatory"]["finite"] is True
        for row in reports
    )
    repeat_pass = all(
        row["bare_f"]["repeat_relative"] <= 1.0e-12
        and row["a_side_explanatory"]["repeat_relative"] <= 1.0e-12
        for row in reports
    )
    bare_unchanged = bare_hash_before == bare_hash_after
    gate_pass = bool(bare_pass and all_finite and repeat_pass and bare_unchanged)
    return {
        "schema": "task040.v4.exact_authority_compatibility.v1",
        "labels": list(labels),
        "identity": dict(identity),
        "operator_identity": {
            "bare_f": _operator_identity(bare_f, "bare_f"),
            "a_side": _operator_identity(side_operator, "a_side"),
            "bare_f_hash_before": bare_hash_before,
            "bare_f_hash_after": bare_hash_after,
            "bare_f_unchanged": bare_hash_before == bare_hash_after,
        },
        "reports": reports,
        "exact_output_vectors_loaded": len(labels),
        "finite_pass": bool(all_finite),
        "bare_f_residual_pass": bool(bare_pass and all_finite),
        "repeat_pass": bool(repeat_pass),
        "bare_f_hash_unchanged_pass": bool(bare_unchanged),
        "factor_inventory": {
            "exact_output_vectors_loaded": len(labels),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "cross_section_group_factor_count": 0,
            "reduced_dense_factor_count": 0,
            "factor_objects_created": 0,
        },
        "qep_calls": 0,
        "pde_solve": "not_run",
        "cleanup": {
            "factor_objects_created": 0,
            "interface_masses_built": False,
            "packet_built": False,
        },
        "classification": (
            V4_EXACT_AUTHORITY_PASS if gate_pass else V4_EXACT_AUTHORITY_FAILURE
        ),
        "gate_pass": gate_pass,
    }
