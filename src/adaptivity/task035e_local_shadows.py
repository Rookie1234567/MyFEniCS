"""Actual dyadic h-action and algebraic nested-system shadow identities.

The geometry function performs the requested split and all forest closure.
The algebra function consumes the resulting nested coarse/enriched systems;
it never looks at an external solution or error map.  Its enriched endpoint
is not an independently solved production candidate and therefore carries no
formal Task035e D4 effectivity credit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from .dyadic_hexa_refinement import (
    BalancedDyadicHexForest,
    DyadicHexKey,
    refine_balanced_dyadic_hexa_forest,
)


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _complex_vector(values: np.ndarray, *, label: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim != 1 or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must be one finite complex vector")
    return result


def _complex_matrix(values: np.ndarray, *, label: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim != 2 or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must be one finite complex matrix")
    return result


@dataclass(frozen=True, slots=True)
class HShadowGeometry:
    """One replayable actual h->h/2 action after physical closure."""

    forest: BalancedDyadicHexForest
    requested_split_keys: tuple[DyadicHexKey, ...]
    closure_split_keys: tuple[DyadicHexKey, ...]
    removed_leaf_keys: tuple[DyadicHexKey, ...]
    added_leaf_keys: tuple[DyadicHexKey, ...]
    net_added_leaf_count: int
    audit: Mapping[str, Any]


def build_h_shadow_geometry(
    forest: BalancedDyadicHexForest,
    requested_split_keys: Sequence[DyadicHexKey],
    *,
    maximum_level: int = 2,
) -> HShadowGeometry:
    """Execute one local split and retain requested-vs-closure identities."""

    if forest.audit.get("pass") is not True:
        raise ValueError("current forest must pass before an h-shadow")
    requested = tuple(sorted(set(requested_split_keys)))
    if not requested or len(requested) != len(tuple(requested_split_keys)):
        raise ValueError("h-shadow split keys must be nonempty and unique")
    pre = dict(forest.leaf_by_key)
    missing = tuple(key for key in requested if key not in pre)
    if missing:
        raise ValueError(f"h-shadow marks non-leaf keys: {missing[:2]}")
    if any(key.level >= int(maximum_level) for key in requested):
        raise ValueError("h-shadow cannot exceed the maximum leaf level")
    enriched = refine_balanced_dyadic_hexa_forest(
        forest,
        requested,
        maximum_level=int(maximum_level),
    )
    post = dict(enriched.leaf_by_key)
    removed = tuple(sorted(set(pre) - set(post)))
    added = tuple(sorted(set(post) - set(pre)))
    closure = tuple(sorted(set(removed) - set(requested)))
    if not set(requested).issubset(removed):
        raise RuntimeError("requested h-shadow leaves were not split")
    audit_payload = {
        "schema_version": "task035e.actual-local-h-shadow-geometry.v1",
        "status": "actual_local_h_shadow_geometry_pass",
        "pass": True,
        "maximum_level": int(maximum_level),
        "requested_split_keys": [key.to_dict() for key in requested],
        "closure_split_keys": [key.to_dict() for key in closure],
        "removed_leaf_keys": [key.to_dict() for key in removed],
        "added_leaf_keys": [key.to_dict() for key in added],
        "pre_leaf_count": len(pre),
        "post_leaf_count": len(post),
        "net_added_leaf_count": len(post) - len(pre),
        "leaf_level_counts": dict(enriched.audit["leaf_level_counts"]),
        "maximum_adjacent_level_jump": int(
            enriched.audit["maximum_adjacent_level_jump"]
        ),
        "strong_2_to_1_balance": bool(
            enriched.audit["strong_2_to_1_balance"]
        ),
        "periodic_boundary_audit": dict(
            enriched.audit["periodic_boundary_audit"]
        ),
        "material_interface_hanging_face_count": int(
            enriched.audit["material_interface_hanging_face_count"]
        ),
        "leaf_catalog_sha256": enriched.audit["leaf_catalog_sha256"],
        "hanging_face_catalog_sha256": enriched.audit[
            "hanging_face_catalog_sha256"
        ],
    }
    audit_payload["action_sha256"] = _json_sha256(audit_payload)
    return HShadowGeometry(
        forest=enriched,
        requested_split_keys=requested,
        closure_split_keys=closure,
        removed_leaf_keys=removed,
        added_leaf_keys=added,
        net_added_leaf_count=len(post) - len(pre),
        audit=MappingProxyType(audit_payload),
    )


@dataclass(frozen=True, slots=True)
class SignedShadowGoal:
    """One signed DWR prediction and its same-system enriched endpoint."""

    goal_id: str
    predicted_delta: float
    enriched_endpoint_delta: float
    algebraic_effectivity: float | None
    safe_zero: bool
    sign_consistent: bool
    within_factor_two: bool


@dataclass(frozen=True, slots=True)
class NestedShadowEvidence:
    """Galerkin, residual, adjoint and effectivity audit for one action."""

    shadow_state: np.ndarray
    embedded_current_state: np.ndarray
    residual: np.ndarray
    goals: tuple[SignedShadowGoal, ...]
    audit: Mapping[str, Any]


def evaluate_nested_shadow_system(
    *,
    action_kind: str,
    goal_ids: Sequence[str],
    current_matrix: np.ndarray,
    current_rhs: np.ndarray,
    current_state: np.ndarray,
    shadow_matrix: np.ndarray,
    shadow_rhs: np.ndarray,
    prolongation: np.ndarray,
    shadow_goal_gradients: np.ndarray,
    algebraic_tolerance: float = 5.0e-11,
    zero_tolerance: float = 1.0e-13,
) -> NestedShadowEvidence:
    """Check the signed DWR algebra against its same-system endpoint.

    This component check deliberately does not accept caller-supplied
    ``actual_goal_deltas``.  Formal D4 evidence must instead bind this
    prediction to a later independent candidate PDE/output authority.
    """

    if action_kind not in {"p-up", "h-refine"}:
        raise ValueError("nested shadow action must be p-up or h-refine")
    ids = tuple(str(goal_id) for goal_id in goal_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("shadow goal IDs must be nonempty and unique")
    coarse_matrix = _complex_matrix(current_matrix, label="current matrix")
    fine_matrix = _complex_matrix(shadow_matrix, label="shadow matrix")
    coarse_rhs = _complex_vector(current_rhs, label="current RHS")
    coarse_state = _complex_vector(current_state, label="current state")
    fine_rhs = _complex_vector(shadow_rhs, label="shadow RHS")
    transfer = _complex_matrix(prolongation, label="prolongation")
    gradients = _complex_matrix(
        shadow_goal_gradients,
        label="shadow goal gradients",
    )
    if coarse_matrix.shape[0] != coarse_matrix.shape[1]:
        raise ValueError("current matrix must be square")
    if fine_matrix.shape[0] != fine_matrix.shape[1]:
        raise ValueError("shadow matrix must be square")
    coarse_size = coarse_matrix.shape[0]
    fine_size = fine_matrix.shape[0]
    if (
        coarse_rhs.shape != (coarse_size,)
        or coarse_state.shape != (coarse_size,)
        or fine_rhs.shape != (fine_size,)
        or transfer.shape != (fine_size, coarse_size)
        or gradients.shape != (len(ids), fine_size)
    ):
        raise ValueError("nested shadow array shapes are inconsistent")
    if algebraic_tolerance <= 0.0 or zero_tolerance <= 0.0:
        raise ValueError("shadow tolerances must be positive")

    coarse_residual = coarse_rhs - coarse_matrix @ coarse_state
    embedded = transfer @ coarse_state
    residual = fine_rhs - fine_matrix @ embedded
    shadow_state = np.linalg.solve(fine_matrix, fine_rhs)
    adjoints = np.linalg.solve(fine_matrix.conj().T, gradients.T)
    predicted = np.real(np.conj(adjoints).T @ residual)
    if predicted.shape != (len(ids),):
        raise RuntimeError("shadow adjoint pairing has the wrong shape")
    enriched_endpoint = np.real(
        np.conj(gradients) @ (shadow_state - embedded)
    )
    if enriched_endpoint.shape != (len(ids),):
        raise RuntimeError("shadow endpoint pairing has the wrong shape")

    rows: list[SignedShadowGoal] = []
    for goal_id, estimate, observed in zip(
        ids,
        predicted,
        enriched_endpoint,
        strict=True,
    ):
        estimate_value = float(estimate)
        observed_value = float(observed)
        safe_zero = (
            abs(estimate_value) <= zero_tolerance
            and abs(observed_value) <= zero_tolerance
        )
        effectivity = (
            None
            if abs(observed_value) <= zero_tolerance
            else estimate_value / observed_value
        )
        sign_consistent = bool(
            safe_zero
            or estimate_value == 0.0
            or observed_value == 0.0
            or math.copysign(1.0, estimate_value)
            == math.copysign(1.0, observed_value)
        )
        within = bool(
            safe_zero
            or (
                effectivity is not None
                and 0.5 <= abs(effectivity) <= 2.0
            )
        )
        rows.append(
            SignedShadowGoal(
                goal_id=goal_id,
                predicted_delta=estimate_value,
                enriched_endpoint_delta=observed_value,
                algebraic_effectivity=effectivity,
                safe_zero=safe_zero,
                sign_consistent=sign_consistent,
                within_factor_two=within,
            )
        )

    projected_matrix = transfer.conj().T @ fine_matrix @ transfer
    projected_rhs = transfer.conj().T @ fine_rhs
    matrix_scale = max(
        float(np.linalg.norm(coarse_matrix)),
        float(np.linalg.norm(projected_matrix)),
        np.finfo(float).tiny,
    )
    rhs_scale = max(
        float(np.linalg.norm(coarse_rhs)),
        float(np.linalg.norm(projected_rhs)),
        np.finfo(float).tiny,
    )
    matrix_galerkin_error = float(
        np.linalg.norm(projected_matrix - coarse_matrix) / matrix_scale
    )
    rhs_galerkin_error = float(
        np.linalg.norm(projected_rhs - coarse_rhs) / rhs_scale
    )
    coarse_residual_relative = float(
        np.linalg.norm(coarse_residual)
        / max(float(np.linalg.norm(coarse_rhs)), np.finfo(float).tiny)
    )
    endpoint_equation_error = float(
        np.linalg.norm(fine_matrix @ shadow_state - fine_rhs)
        / max(float(np.linalg.norm(fine_rhs)), np.finfo(float).tiny)
    )
    factor_two_fraction = sum(row.within_factor_two for row in rows) / len(rows)
    audit_payload = {
        "schema_version": "task035e.algebraic-nested-local-shadow.v2",
        "status": "algebraic_nested_local_shadow_component_pass",
        "component_pass": bool(
            matrix_galerkin_error <= algebraic_tolerance
            and rhs_galerkin_error <= algebraic_tolerance
            and coarse_residual_relative <= algebraic_tolerance
            and endpoint_equation_error <= algebraic_tolerance
            and factor_two_fraction >= 0.90
            and all(row.sign_consistent for row in rows)
        ),
        "action_kind": action_kind,
        "backend": "dense_numpy_nested_component",
        "formal_d4_effectivity_credit": False,
        "independent_candidate_pde_bound": False,
        "actual_candidate_output_sha256": None,
        "current_size": coarse_size,
        "shadow_size": fine_size,
        "added_rows": fine_size - coarse_size,
        "matrix_galerkin_relative_error": matrix_galerkin_error,
        "rhs_galerkin_relative_error": rhs_galerkin_error,
        "current_equation_relative_residual": coarse_residual_relative,
        "shadow_equation_relative_residual": endpoint_equation_error,
        "enriched_residual_norm": float(np.linalg.norm(residual)),
        "goal_count": len(rows),
        "sign_consistent_goal_count": sum(
            row.sign_consistent for row in rows
        ),
        "factor_two_goal_count": sum(row.within_factor_two for row in rows),
        "factor_two_fraction": factor_two_fraction,
        "goal_rows": [
            {
                "goal_id": row.goal_id,
                "predicted_delta": row.predicted_delta,
                "enriched_endpoint_delta": row.enriched_endpoint_delta,
                "algebraic_effectivity": row.algebraic_effectivity,
                "safe_zero": row.safe_zero,
                "sign_consistent": row.sign_consistent,
                "within_factor_two": row.within_factor_two,
            }
            for row in rows
        ],
        "structural_cost": {
            "added_active_dof": "not_measured",
            "actual_rows": "not_measured",
            "matrix_nnz": "not_measured",
            "factor_nnz": "not_measured",
            "peak_memory_bytes": "not_measured",
        },
        "ordinary_default_changed": False,
    }
    audit_payload["evidence_sha256"] = _json_sha256(audit_payload)
    for array in (shadow_state, embedded, residual):
        array.setflags(write=False)
    return NestedShadowEvidence(
        shadow_state=shadow_state,
        embedded_current_state=embedded,
        residual=residual,
        goals=tuple(rows),
        audit=MappingProxyType(audit_payload),
    )


__all__ = [
    "HShadowGeometry",
    "NestedShadowEvidence",
    "SignedShadowGoal",
    "build_h_shadow_geometry",
    "evaluate_nested_shadow_system",
]
