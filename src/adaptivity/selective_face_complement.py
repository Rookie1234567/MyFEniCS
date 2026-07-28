"""Exact-sequence reference authority for selective p6 face recovery.

The Task035d nested-p experiment keeps every edge and physical face at p5
while retaining p6 cell-interior modes.  Recovering selected trace accuracy
must therefore add real p6 face rows, not coefficients in a hidden global-p6
matrix.  This module qualifies the smallest legal local transition:

```
edge p5, face p5, cell p6
    -> one whole face p6, all other entities unchanged
```

Only the reference-cell algebra is handled here.  Hanging participants,
periodic-orbit closure, DtN/port coupling, and a heavy PDE remain separate
fail-closed gates.
"""

from __future__ import annotations

import basix
import basix.ufl
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from scipy.linalg import qr

from src.constraints.high_order_floquet_trace import (
    face_coefficient_transform,
    quadrilateral_d4_vertex_permutations,
)

from .exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    VariablePReferenceSpace,
    apply_active_dof_transformation,
    build_variable_p_reference_space,
)
from .hcurl_hanging_trace import build_hexa_face_trace_pair


_FACE_COUNT = 6
_HCURL_COMPLEMENT_DIMENSION = 20
_H1_COMPLEMENT_DIMENSION = 9
_ROUND_OFF_LIMIT = 5.0e-11


def _matrix_sha256(values: np.ndarray) -> str:
    matrix = np.ascontiguousarray(values)
    header = json.dumps(
        {
            "dtype": matrix.dtype.str,
            "shape": list(matrix.shape),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(header)
    digest.update(matrix.tobytes())
    return digest.hexdigest()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _maximum_absolute(values: np.ndarray) -> float:
    return float(np.max(np.abs(values), initial=0.0))


def _canonicalize_columns(values: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(values.copy())
    for column in range(result.shape[1]):
        pivot = int(np.argmax(np.abs(result[:, column])))
        if result[pivot, column] < 0.0:
            result[:, column] *= -1.0
    return result


def _rank_from_pivoted_qr(values: np.ndarray) -> tuple[int, float]:
    _orthogonal, upper, _pivots = qr(
        values,
        mode="economic",
        pivoting=True,
        check_finite=False,
    )
    diagonal = np.abs(np.diag(upper))
    tolerance = (
        0.0
        if len(diagonal) == 0
        else float(
            diagonal[0]
            * max(values.shape)
            * np.finfo(np.float64).eps
            * 64.0
        )
    )
    return int(np.count_nonzero(diagonal > tolerance)), tolerance


@dataclass(frozen=True)
class NestedCoefficientComplement:
    """One nested injection and its p6-coefficient-Riesz complement."""

    injection: np.ndarray
    complement: np.ndarray
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class FaceInteriorRieszComplement:
    """Physical-face p5 embedding and p6 tangential-Riesz complement."""

    p5_to_p6: np.ndarray
    complement_to_p6: np.ndarray
    p6_tangential_riesz_gram: np.ndarray
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class SelectiveP6FaceReferenceComplement:
    """Reference algebra for one whole physical face p5-to-p6 action."""

    local_face: int
    coarse_space: VariablePReferenceSpace
    enriched_space: VariablePReferenceSpace
    hcurl: NestedCoefficientComplement
    h1: NestedCoefficientComplement
    face_interior: FaceInteriorRieszComplement
    audit: Mapping[str, Any]


def _nested_coefficient_complement(
    coarse_expansion: np.ndarray,
    enriched_expansion: np.ndarray,
    *,
    family: str,
    expected_complement_dimension: int,
) -> NestedCoefficientComplement:
    coarse = np.asarray(coarse_expansion, dtype=np.float64)
    enriched = np.asarray(enriched_expansion, dtype=np.float64)
    if coarse.ndim != 2 or enriched.ndim != 2:
        raise ValueError("nested expansions must be matrices")
    if coarse.shape[0] != enriched.shape[0]:
        raise ValueError("nested expansions require one p6 container")
    dimension_difference = enriched.shape[1] - coarse.shape[1]
    if dimension_difference != int(expected_complement_dimension):
        raise RuntimeError(
            f"{family} selective-face dimension difference is "
            f"{dimension_difference}, expected "
            f"{expected_complement_dimension}"
        )

    injection = np.linalg.lstsq(
        enriched,
        coarse,
        rcond=None,
    )[0]
    coarse_orthogonal, _upper = np.linalg.qr(
        coarse,
        mode="reduced",
    )
    residual = enriched - coarse_orthogonal @ (
        coarse_orthogonal.T @ enriched
    )
    residual_orthogonal, residual_upper, _pivots = qr(
        residual,
        mode="economic",
        pivoting=True,
        check_finite=False,
    )
    residual_diagonal = np.abs(np.diag(residual_upper))
    residual_tolerance = float(
        residual_diagonal[0]
        * max(residual.shape)
        * np.finfo(np.float64).eps
        * 64.0
    )
    residual_rank = int(
        np.count_nonzero(residual_diagonal > residual_tolerance)
    )
    if residual_rank != dimension_difference:
        raise RuntimeError(
            f"{family} selective-face complement rank is {residual_rank}, "
            f"expected {dimension_difference}"
        )
    p6_complement = _canonicalize_columns(
        residual_orthogonal[:, :dimension_difference]
    )
    complement = np.linalg.lstsq(
        enriched,
        p6_complement,
        rcond=None,
    )[0]

    enriched_metric = enriched.T @ enriched
    augmented = np.concatenate((injection, complement), axis=1)
    augmented_rank, augmented_tolerance = _rank_from_pivoted_qr(
        augmented
    )
    injection_error = _maximum_absolute(
        enriched @ injection - coarse
    )
    complement_error = _maximum_absolute(
        enriched @ complement - p6_complement
    )
    cross_error = _maximum_absolute(
        injection.T @ enriched_metric @ complement
    )
    complement_gram_error = _maximum_absolute(
        complement.T @ enriched_metric @ complement
        - np.eye(dimension_difference)
    )
    checks = {
        "coarse_is_nested_in_enriched": (
            injection_error <= _ROUND_OFF_LIMIT
        ),
        "complement_is_in_enriched_space": (
            complement_error <= _ROUND_OFF_LIMIT
        ),
        "coarse_complement_riesz_orthogonal": (
            cross_error <= _ROUND_OFF_LIMIT
        ),
        "complement_riesz_orthonormal": (
            complement_gram_error <= _ROUND_OFF_LIMIT
        ),
        "injection_plus_complement_spans_enriched": (
            augmented_rank == enriched.shape[1]
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            f"{family} selective-face nestedness audit failed: "
            + ", ".join(failures)
        )
    for matrix in (injection, complement):
        matrix.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035d.selective-face-nested-coefficient-complement.v1"
            ),
            "status": "selective_face_nested_complement_pass",
            "pass": True,
            "family": family,
            "coarse_dimension": int(coarse.shape[1]),
            "enriched_dimension": int(enriched.shape[1]),
            "p6_container_dimension": int(enriched.shape[0]),
            "complement_dimension": dimension_difference,
            "riesz_metric": "euclidean_p6_coefficient_metric",
            "injection_embedding_error_max": injection_error,
            "complement_embedding_error_max": complement_error,
            "coarse_complement_riesz_error_max": cross_error,
            "complement_gram_error_max": complement_gram_error,
            "residual_rank": residual_rank,
            "residual_rank_tolerance": residual_tolerance,
            "augmented_rank": augmented_rank,
            "augmented_rank_tolerance": augmented_tolerance,
            "injection_sha256": _matrix_sha256(injection),
            "complement_sha256": _matrix_sha256(complement),
            "checks": checks,
            "prefix_assumption_used": False,
        }
    )
    return NestedCoefficientComplement(
        injection=np.ascontiguousarray(injection),
        complement=np.ascontiguousarray(complement),
        audit=audit,
    )


@lru_cache(maxsize=1)
def _p6_face_interior_tangential_riesz_gram() -> np.ndarray:
    element = basix.ufl.element(
        "N1curl",
        "quadrilateral",
        6,
    ).basix_element
    points, weights = basix.make_quadrature(
        basix.CellType.quadrilateral,
        14,
    )
    values = np.asarray(element.tabulate(0, points)[0])
    full_gram = np.einsum(
        "qia,qja,q->ij",
        values,
        values,
        weights,
        optimize=True,
    )
    interior = np.asarray(
        element.entity_dofs[2][0],
        dtype=np.int32,
    )
    gram = np.ascontiguousarray(
        full_gram[np.ix_(interior, interior)]
    )
    gram.setflags(write=False)
    return gram


def _face_interior_riesz_complement(
    coarse_space: VariablePReferenceSpace,
    enriched_space: VariablePReferenceSpace,
    *,
    local_face: int,
) -> FaceInteriorRieszComplement:
    p6_space = build_variable_p_reference_space(
        HexaEntityDegreeMap.uniform(6)
    )
    coarse_dofs = np.asarray(
        coarse_space.hcurl_element.entity_dofs[2][local_face],
        dtype=np.int32,
    )
    enriched_dofs = np.asarray(
        enriched_space.hcurl_element.entity_dofs[2][local_face],
        dtype=np.int32,
    )
    p6_dofs = np.asarray(
        p6_space.hcurl_element.entity_dofs[2][local_face],
        dtype=np.int32,
    )
    if (
        len(coarse_dofs) != 40
        or len(enriched_dofs) != 60
        or len(p6_dofs) != 60
    ):
        raise RuntimeError("p5/p6 hexa face-interior dimensions changed")
    p5_to_p6 = np.ascontiguousarray(
        coarse_space.hcurl_to_p6[np.ix_(p6_dofs, coarse_dofs)]
    )
    enriched_to_p6 = np.ascontiguousarray(
        enriched_space.hcurl_to_p6[
            np.ix_(p6_dofs, enriched_dofs)
        ]
    )
    outside_p5 = np.delete(
        coarse_space.hcurl_to_p6[:, coarse_dofs],
        p6_dofs,
        axis=0,
    )
    outside_enriched = np.delete(
        enriched_space.hcurl_to_p6[:, enriched_dofs],
        p6_dofs,
        axis=0,
    )
    gram = np.asarray(_p6_face_interior_tangential_riesz_gram())
    cholesky = np.linalg.cholesky(gram)
    whitening = cholesky.T
    whitened_p5 = whitening @ p5_to_p6
    coarse_orthogonal, _upper = np.linalg.qr(
        whitened_p5,
        mode="complete",
    )
    whitened_complement = _canonicalize_columns(
        coarse_orthogonal[:, 40:]
    )
    complement = np.linalg.solve(
        whitening,
        whitened_complement,
    )
    complement = np.ascontiguousarray(complement)
    embedding_rank, embedding_rank_tolerance = _rank_from_pivoted_qr(
        p5_to_p6
    )
    combined_rank, combined_rank_tolerance = _rank_from_pivoted_qr(
        np.concatenate((p5_to_p6, complement), axis=1)
    )
    cross_error = _maximum_absolute(
        p5_to_p6.T @ gram @ complement
    )
    complement_gram_error = _maximum_absolute(
        complement.T @ gram @ complement - np.eye(20)
    )
    whitened_projector_error = _maximum_absolute(
        coarse_orthogonal @ coarse_orthogonal.T - np.eye(60)
    )

    maximum_d4_embedding_error = 0.0
    maximum_d4_riesz_error = 0.0
    maximum_d4_complement_closure_error = 0.0
    maximum_d4_complement_unitarity_error = 0.0
    d4_rows: list[dict[str, Any]] = []
    for permutation in sorted(quadrilateral_d4_vertex_permutations()):
        transform_p5 = np.asarray(
            face_coefficient_transform(5, permutation),
            dtype=np.complex128,
        )
        transform_p6 = np.asarray(
            face_coefficient_transform(6, permutation),
            dtype=np.complex128,
        )
        embedding_error = _maximum_absolute(
            transform_p6 @ p5_to_p6
            - p5_to_p6 @ transform_p5
        )
        riesz_error = _maximum_absolute(
            transform_p6.conj().T @ gram @ transform_p6 - gram
        )
        oriented_complement = transform_p6 @ complement
        complement_representation = (
            complement.conj().T @ gram @ oriented_complement
        )
        closure_error = _maximum_absolute(
            oriented_complement
            - complement @ complement_representation
        )
        unitarity_error = _maximum_absolute(
            complement_representation.conj().T
            @ complement_representation
            - np.eye(20)
        )
        maximum_d4_embedding_error = max(
            maximum_d4_embedding_error,
            embedding_error,
        )
        maximum_d4_riesz_error = max(
            maximum_d4_riesz_error,
            riesz_error,
        )
        maximum_d4_complement_closure_error = max(
            maximum_d4_complement_closure_error,
            closure_error,
        )
        maximum_d4_complement_unitarity_error = max(
            maximum_d4_complement_unitarity_error,
            unitarity_error,
        )
        d4_rows.append(
            {
                "vertex_permutation": list(permutation),
                "embedding_commuting_error_max": embedding_error,
                "riesz_invariance_error_max": riesz_error,
                "complement_closure_error_max": closure_error,
                "complement_unitarity_error_max": unitarity_error,
            }
        )

    p5_trace_pair = build_hexa_face_trace_pair(5, local_face)
    p6_trace_pair = build_hexa_face_trace_pair(6, local_face)
    checks = {
        "p5_face_embedding_rank_40": embedding_rank == 40,
        "p6_face_complement_rank_20": combined_rank == 60,
        "p5_embedding_has_no_other_entity_support": (
            _maximum_absolute(outside_p5) <= _ROUND_OFF_LIMIT
        ),
        "p6_face_modes_have_no_other_entity_support": (
            _maximum_absolute(outside_enriched) <= _ROUND_OFF_LIMIT
        ),
        "enriched_face_is_p6_container": (
            _maximum_absolute(enriched_to_p6 - np.eye(60))
            <= _ROUND_OFF_LIMIT
        ),
        "tangential_riesz_positive_definite": (
            float(np.min(np.linalg.eigvalsh(gram))) > 0.0
        ),
        "p5_complement_riesz_orthogonal": (
            cross_error <= _ROUND_OFF_LIMIT
        ),
        "complement_riesz_orthonormal": (
            complement_gram_error <= _ROUND_OFF_LIMIT
        ),
        "p5_plus_complement_reconstructs_p6_face": (
            whitened_projector_error <= _ROUND_OFF_LIMIT
        ),
        "all_eight_d4_actions_covered": len(d4_rows) == 8,
        "d4_embedding_commutes": (
            maximum_d4_embedding_error <= _ROUND_OFF_LIMIT
        ),
        "d4_preserves_tangential_riesz": (
            maximum_d4_riesz_error <= _ROUND_OFF_LIMIT
        ),
        "d4_preserves_complement_subspace": (
            maximum_d4_complement_closure_error <= _ROUND_OFF_LIMIT
        ),
        "d4_complement_representation_unitary": (
            maximum_d4_complement_unitarity_error
            <= _ROUND_OFF_LIMIT
        ),
        "p5_hexa_piola_trace_qualified": (
            p5_trace_pair.audit["pass"] is True
        ),
        "p6_hexa_piola_trace_qualified": (
            p6_trace_pair.audit["pass"] is True
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "selective p6 face-interior Riesz audit failed: "
            + ", ".join(failures)
        )
    for matrix in (p5_to_p6, complement):
        matrix.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035d.p5-p6-face-interior-riesz-complement.v1"
            ),
            "status": "p5_p6_face_interior_riesz_complement_pass",
            "pass": True,
            "local_face": int(local_face),
            "p5_face_interior_dimension": 40,
            "p6_face_interior_dimension": 60,
            "complement_dimension": 20,
            "riesz_metric": (
                "reference_affine_face_tangential_l2_p6_gram"
            ),
            "quadrature_degree": 14,
            "p5_embedding_rank": embedding_rank,
            "p5_embedding_rank_tolerance": embedding_rank_tolerance,
            "combined_rank": combined_rank,
            "combined_rank_tolerance": combined_rank_tolerance,
            "p5_to_p6_sha256": _matrix_sha256(p5_to_p6),
            "complement_to_p6_sha256": _matrix_sha256(complement),
            "p6_tangential_riesz_gram_sha256": _matrix_sha256(gram),
            "p6_tangential_riesz_condition_number": float(
                np.linalg.cond(gram)
            ),
            "p5_other_entity_support_error_max": _maximum_absolute(
                outside_p5
            ),
            "p6_other_entity_support_error_max": _maximum_absolute(
                outside_enriched
            ),
            "enriched_face_identity_error_max": _maximum_absolute(
                enriched_to_p6 - np.eye(60)
            ),
            "p5_complement_riesz_error_max": cross_error,
            "complement_gram_error_max": complement_gram_error,
            "whitened_reconstruction_projector_error_max": (
                whitened_projector_error
            ),
            "maximum_d4_embedding_commuting_error": (
                maximum_d4_embedding_error
            ),
            "maximum_d4_riesz_invariance_error": (
                maximum_d4_riesz_error
            ),
            "maximum_d4_complement_closure_error": (
                maximum_d4_complement_closure_error
            ),
            "maximum_d4_complement_unitarity_error": (
                maximum_d4_complement_unitarity_error
            ),
            "p5_hexa_trace_audit": dict(p5_trace_pair.audit),
            "p6_hexa_trace_audit": dict(p6_trace_pair.audit),
            "d4_actions": d4_rows,
            "checks": checks,
            "prefix_assumption_used": False,
            "individual_complement_modes_are_not_production_rows": True,
        }
    )
    return FaceInteriorRieszComplement(
        p5_to_p6=p5_to_p6,
        complement_to_p6=complement,
        p6_tangential_riesz_gram=np.asarray(
            _p6_face_interior_tangential_riesz_gram()
        ),
        audit=audit,
    )


def _transformation_matrix(
    space: VariablePReferenceSpace,
    *,
    family: str,
    cell_info: int,
) -> np.ndarray:
    dimension = (
        space.hcurl_dimension if family == "hcurl" else space.h1_dimension
    )
    return apply_active_dof_transformation(
        space,
        np.eye(dimension, dtype=np.float64),
        family=family,
        cell_info=cell_info,
    )


def _orientation_audit(
    coarse_space: VariablePReferenceSpace,
    enriched_space: VariablePReferenceSpace,
    pair: NestedCoefficientComplement,
    *,
    family: str,
    local_face: int,
) -> dict[str, Any]:
    p6_space = build_variable_p_reference_space(
        HexaEntityDegreeMap.uniform(6)
    )
    if family == "hcurl":
        coarse_expansion = np.asarray(coarse_space.hcurl_to_p6)
        enriched_expansion = np.asarray(enriched_space.hcurl_to_p6)
        p6_dimension = p6_space.hcurl_dimension
    elif family == "h1":
        coarse_expansion = np.asarray(coarse_space.h1_to_q6)
        enriched_expansion = np.asarray(enriched_space.h1_to_q6)
        p6_dimension = p6_space.h1_dimension
    else:
        raise ValueError(f"unknown exact-sequence family {family!r}")

    maximum_injection_error = 0.0
    maximum_cross_error = 0.0
    maximum_complement_gram_error = 0.0
    rows: list[dict[str, Any]] = []
    for reflected in (0, 1):
        for rotations in range(4):
            cell_info = (
                (reflected << (3 * local_face))
                | (rotations << (3 * local_face + 1))
            )
            coarse_transform = _transformation_matrix(
                coarse_space,
                family=family,
                cell_info=cell_info,
            )
            enriched_transform = _transformation_matrix(
                enriched_space,
                family=family,
                cell_info=cell_info,
            )
            p6_transform = apply_active_dof_transformation(
                p6_space,
                np.eye(p6_dimension, dtype=np.float64),
                family=family,
                cell_info=cell_info,
            )
            oriented_coarse = (
                p6_transform
                @ coarse_expansion
                @ coarse_transform.T
            )
            oriented_enriched = (
                p6_transform
                @ enriched_expansion
                @ enriched_transform.T
            )
            oriented_injection = (
                enriched_transform
                @ pair.injection
                @ coarse_transform.T
            )
            oriented_complement = (
                enriched_transform @ pair.complement
            )
            injection_error = _maximum_absolute(
                oriented_enriched @ oriented_injection
                - oriented_coarse
            )
            complement_image = (
                oriented_enriched @ oriented_complement
            )
            cross_error = _maximum_absolute(
                oriented_coarse.T @ complement_image
            )
            gram_error = _maximum_absolute(
                complement_image.T @ complement_image
                - np.eye(pair.complement.shape[1])
            )
            maximum_injection_error = max(
                maximum_injection_error,
                injection_error,
            )
            maximum_cross_error = max(
                maximum_cross_error,
                cross_error,
            )
            maximum_complement_gram_error = max(
                maximum_complement_gram_error,
                gram_error,
            )
            rows.append(
                {
                    "reflected": bool(reflected),
                    "rotations": rotations,
                    "cell_info": cell_info,
                    "injection_embedding_error_max": injection_error,
                    "coarse_complement_riesz_error_max": cross_error,
                    "complement_gram_error_max": gram_error,
                }
            )
    checks = {
        "all_eight_d4_actions_covered": len(rows) == 8,
        "oriented_injection_is_nested": (
            maximum_injection_error <= _ROUND_OFF_LIMIT
        ),
        "oriented_complement_is_riesz_orthogonal": (
            maximum_cross_error <= _ROUND_OFF_LIMIT
        ),
        "oriented_complement_is_riesz_orthonormal": (
            maximum_complement_gram_error <= _ROUND_OFF_LIMIT
        ),
    }
    return {
        "schema_version": "task035d.selective-face-d4-audit.v1",
        "status": (
            "selective_face_d4_pass"
            if all(checks.values())
            else "selective_face_d4_fail"
        ),
        "pass": all(checks.values()),
        "family": family,
        "local_face": int(local_face),
        "maximum_injection_embedding_error": (
            maximum_injection_error
        ),
        "maximum_coarse_complement_riesz_error": maximum_cross_error,
        "maximum_complement_gram_error": (
            maximum_complement_gram_error
        ),
        "checks": checks,
        "actions": rows,
    }


@lru_cache(maxsize=6)
def build_selective_p6_face_reference_complement(
    local_face: int,
) -> SelectiveP6FaceReferenceComplement:
    """Qualify one whole-face p5-to-p6 exact-sequence transition."""

    face = int(local_face)
    if not 0 <= face < _FACE_COUNT:
        raise ValueError("hexahedron local face must be in [0, 5]")
    coarse_map = HexaEntityDegreeMap.dimension_uniform(
        edge_degree=5,
        face_degree=5,
        cell_degree=6,
    )
    enriched_faces = [5] * _FACE_COUNT
    enriched_faces[face] = 6
    enriched_map = HexaEntityDegreeMap(
        edges=(5,) * 12,
        faces=tuple(enriched_faces),
        cell=6,
    )
    coarse_space = build_variable_p_reference_space(coarse_map)
    enriched_space = build_variable_p_reference_space(enriched_map)
    hcurl = _nested_coefficient_complement(
        coarse_space.hcurl_to_p6,
        enriched_space.hcurl_to_p6,
        family="hcurl",
        expected_complement_dimension=_HCURL_COMPLEMENT_DIMENSION,
    )
    h1 = _nested_coefficient_complement(
        coarse_space.h1_to_q6,
        enriched_space.h1_to_q6,
        family="h1",
        expected_complement_dimension=_H1_COMPLEMENT_DIMENSION,
    )
    face_interior = _face_interior_riesz_complement(
        coarse_space,
        enriched_space,
        local_face=face,
    )
    gradient_commuting_error = _maximum_absolute(
        hcurl.injection @ coarse_space.discrete_gradient
        - enriched_space.discrete_gradient @ h1.injection
    )
    hcurl_orientation = _orientation_audit(
        coarse_space,
        enriched_space,
        hcurl,
        family="hcurl",
        local_face=face,
    )
    h1_orientation = _orientation_audit(
        coarse_space,
        enriched_space,
        h1,
        family="h1",
        local_face=face,
    )
    checks = {
        "coarse_reference_space": coarse_space.audit["pass"] is True,
        "enriched_reference_space": enriched_space.audit["pass"] is True,
        "whole_face_hcurl_complement_has_20_modes": (
            hcurl.complement.shape[1] == _HCURL_COMPLEMENT_DIMENSION
        ),
        "whole_face_h1_complement_has_9_modes": (
            h1.complement.shape[1] == _H1_COMPLEMENT_DIMENSION
        ),
        "exact_sequence_injection_commutes": (
            gradient_commuting_error <= _ROUND_OFF_LIMIT
        ),
        "hcurl_d4_orientation": hcurl_orientation["pass"] is True,
        "h1_d4_orientation": h1_orientation["pass"] is True,
        "face_interior_tangential_riesz": (
            face_interior.audit["pass"] is True
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "selective p6 face reference audit failed: "
            + ", ".join(failures)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035d.selective-p6-face-reference-complement.v1"
            ),
            "status": "selective_p6_face_reference_complement_pass",
            "pass": True,
            "local_face": face,
            "action": "whole_physical_face_p5_to_p6",
            "coarse_degree_map": coarse_map.to_dict(),
            "enriched_degree_map": enriched_map.to_dict(),
            "hcurl": dict(hcurl.audit),
            "h1": dict(h1.audit),
            "face_interior": dict(face_interior.audit),
            "gradient_injection_commuting_error_max": (
                gradient_commuting_error
            ),
            "hcurl_d4_orientation": hcurl_orientation,
            "h1_d4_orientation": h1_orientation,
            "checks": checks,
            "non_hanging_physical_face_only": True,
            "hanging_participant_supported": False,
            "periodic_orbit_closure_required": True,
            "individual_mode_selection_supported": False,
            "dtn_port_complement_qualified": False,
            "heavy_pde_authorized": False,
            "pde_launch_qualified": False,
            "pde_accuracy_credit": False,
            "inactive_modes_globally_numbered": False,
            "full_p6_matrix_constructed": False,
            "ordinary_default_changed": False,
        }
    )
    return SelectiveP6FaceReferenceComplement(
        local_face=face,
        coarse_space=coarse_space,
        enriched_space=enriched_space,
        hcurl=hcurl,
        h1=h1,
        face_interior=face_interior,
        audit=audit,
    )


@lru_cache(maxsize=1)
def build_selective_p6_face_reference_catalog() -> dict[str, Any]:
    """Return the six-face deterministic component authority."""

    entries = [
        dict(build_selective_p6_face_reference_complement(face).audit)
        for face in range(_FACE_COUNT)
    ]
    checks = {
        "all_six_local_faces_qualified": (
            len(entries) == _FACE_COUNT
            and all(entry["pass"] is True for entry in entries)
        ),
        "all_actions_are_whole_face": all(
            entry["action"] == "whole_physical_face_p5_to_p6"
            for entry in entries
        ),
        "all_actions_are_preflight_only": all(
            entry["heavy_pde_authorized"] is False
            for entry in entries
        ),
        "ordinary_default_unchanged": all(
            entry["ordinary_default_changed"] is False
            for entry in entries
        ),
    }
    core = {
        "schema_version": (
            "task035d.selective-p6-face-reference-catalog.v1"
        ),
        "status": "selective_p6_face_reference_catalog_pass",
        "pass": all(checks.values()),
        "action": "whole_physical_face_p5_to_p6",
        "qualified_local_faces": _FACE_COUNT,
        "entries": entries,
        "checks": checks,
        "production_qualified": False,
        "heavy_pde_authorized": False,
        "ordinary_default_changed": False,
    }
    return core | {"catalog_sha256": _payload_sha256(core)}


__all__ = [
    "NestedCoefficientComplement",
    "FaceInteriorRieszComplement",
    "SelectiveP6FaceReferenceComplement",
    "build_selective_p6_face_reference_catalog",
    "build_selective_p6_face_reference_complement",
]
