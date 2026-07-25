"""Qualify the physical p5-to-p6 H(curl) trace complement.

This module constructs a reference-entity data product for the Task035b
selective-trace lane.  It does not inspect a DOLFINx mesh, allocate global
rows, assemble a matrix, or compute DWR weights.  Its narrower purpose is to
answer whether the missing p6 edge and face shells are mathematically safe
inputs to the separate periodic-orbit layer.

The retained p5 entity coefficients are embedded in the p6 entity coefficient
space with Basix's interpolation operator.  The missing shell is the
tangential-L2 Riesz-orthogonal complement of that embedding.  Qualification
then checks:

* the expected one-edge and twenty-face missing dimensions;
* rank and conditioning of the trace Gram, retained Riesz map, and direct sum;
* covariant-Piola push-forward/pull-back and tangential covector identity;
* p5/p6 entity-transformation intertwining and invariance of the complement;
* identical entity-local construction on every reference-hexahedron entity.

All matrices and per-mode hashes are metadata only.  In particular, every
mode has ``global_row=None`` so that this qualification layer cannot silently
retain inactive p6 rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence

import basix
import numpy as np
from scipy.linalg import qr


TraceEntityKind = Literal["edge", "face"]

_CELL = basix.CellType.hexahedron
_EXPECTED_ENTITY_DIMENSIONS = {
    "edge": (1, 5, 6, 1, "interval"),
    "face": (2, 40, 60, 20, "quadrilateral"),
}
_GENERATOR_NAMES = {
    "interval": ("reversal",),
    "quadrilateral": ("rotation", "reflection"),
}


def _readonly_matrix(values: np.ndarray, *, label: str) -> np.ndarray:
    matrix = np.array(values, dtype=np.float64, order="C", copy=True)
    if matrix.ndim != 2:
        raise ValueError(f"{label} must be a matrix")
    if not np.all(np.isfinite(matrix)):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    matrix.setflags(write=False)
    return matrix


def _relative_error(left: np.ndarray, right: np.ndarray) -> float:
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    difference = float(np.linalg.norm((left_array - right_array).ravel()))
    scale = max(
        1.0,
        float(np.linalg.norm(left_array.ravel())),
        float(np.linalg.norm(right_array.ravel())),
    )
    return difference / scale


def _condition_number(matrix: np.ndarray, *, label: str) -> float:
    values = np.linalg.svd(np.asarray(matrix), compute_uv=False)
    if (
        len(values) == 0
        or not np.all(np.isfinite(values))
        or float(values[-1]) <= 0.0
    ):
        raise RuntimeError(f"{label} is singular")
    return float(values[0] / values[-1])


def _numerical_rank(matrix: np.ndarray) -> tuple[int, float]:
    array = np.asarray(matrix, dtype=np.float64)
    singular_values = np.linalg.svd(array, compute_uv=False)
    if len(singular_values) == 0:
        return 0, 0.0
    tolerance = float(
        32.0
        * max(array.shape)
        * np.finfo(np.float64).eps
        * singular_values[0]
    )
    return int(np.count_nonzero(singular_values > tolerance)), tolerance


def _sha256_payload(
    metadata: Mapping[str, Any],
    arrays: Sequence[tuple[str, np.ndarray]],
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            metadata,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    for label, values in arrays:
        array = np.ascontiguousarray(values)
        digest.update(label.encode("utf-8"))
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(
            np.asarray(array.shape, dtype="<i8").tobytes(order="C")
        )
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _element_identity_hash(
    element: basix.finite_element.FiniteElement,
) -> str:
    metadata = {
        "schema": "task035b.basix-nedelec-element-identity.v1",
        "basix_version": basix.__version__,
        "family": str(element.family),
        "cell_type": str(element.cell_type),
        "degree": int(element.degree),
        "lagrange_variant": str(element.lagrange_variant),
        "dpc_variant": str(element.dpc_variant),
        "map_type": str(element.map_type),
        "sobolev_space": str(element.sobolev_space),
        "dimension": int(element.dim),
        "value_shape": list(map(int, element.value_shape)),
        "entity_dofs": [
            [list(map(int, entity)) for entity in dimension]
            for dimension in element.entity_dofs
        ],
    }
    arrays: list[tuple[str, np.ndarray]] = [
        ("wcoeffs", np.asarray(element.wcoeffs)),
        ("coefficient_matrix", np.asarray(element.coefficient_matrix)),
    ]
    for dimension, entities in enumerate(element.x):
        arrays.extend(
            (
                f"x[{dimension}][{entity}]",
                np.asarray(values),
            )
            for entity, values in enumerate(entities)
        )
    for dimension, entities in enumerate(element.M):
        arrays.extend(
            (
                f"M[{dimension}][{entity}]",
                np.asarray(values),
            )
            for entity, values in enumerate(entities)
        )
    for entity_name, transforms in sorted(
        element.entity_transformations().items()
    ):
        arrays.append(
            (f"entity_transformations[{entity_name}]", transforms)
        )
    return _sha256_payload(metadata, arrays)


@dataclass(frozen=True)
class P6TraceModeMetadata:
    """One local Riesz-complement basis mode, with no global row."""

    local_mode_index: int
    anchor_enriched_entity_dof: int
    canonical_p6_entity_dof: int
    coefficient_sha256: str
    global_row: None = None

    def __post_init__(self) -> None:
        if int(self.local_mode_index) < 0:
            raise ValueError("local mode index must be nonnegative")
        if int(self.anchor_enriched_entity_dof) < 0:
            raise ValueError("anchor entity DoF must be nonnegative")
        if int(self.canonical_p6_entity_dof) < 0:
            raise ValueError("canonical p6 entity DoF must be nonnegative")
        if len(self.coefficient_sha256) != 64:
            raise ValueError("mode coefficient hash must be SHA-256")
        if self.global_row is not None:
            raise RuntimeError(
                "qualification metadata must not allocate global rows"
            )


@dataclass(frozen=True)
class P6TraceTransformationQualification:
    """One Basix entity generator restricted to retained/missing shells."""

    generator_name: str
    enriched_transform: np.ndarray
    retained_transform: np.ndarray
    induced_missing_transform: np.ndarray
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        enriched = _readonly_matrix(
            self.enriched_transform,
            label="enriched entity transform",
        )
        retained = _readonly_matrix(
            self.retained_transform,
            label="retained entity transform",
        )
        missing = _readonly_matrix(
            self.induced_missing_transform,
            label="induced missing transform",
        )
        if self.audit.get("pass") is not True:
            raise RuntimeError("entity transformation qualification failed")
        object.__setattr__(self, "enriched_transform", enriched)
        object.__setattr__(self, "retained_transform", retained)
        object.__setattr__(self, "induced_missing_transform", missing)


@dataclass(frozen=True)
class P6TraceComplementShell:
    """Qualified canonical edge or face p5-to-p6 trace complement."""

    entity_kind: TraceEntityKind
    entity_dimension: int
    retained_dimension: int
    enriched_dimension: int
    missing_dimension: int
    retained_embedding: np.ndarray
    trace_l2_gram: np.ndarray
    retained_riesz_projector: np.ndarray
    missing_basis: np.ndarray
    mode_metadata: tuple[P6TraceModeMetadata, ...]
    transformation_generators: tuple[
        P6TraceTransformationQualification, ...
    ]
    shell_sha256: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        retained = _readonly_matrix(
            self.retained_embedding,
            label="retained embedding",
        )
        gram = _readonly_matrix(
            self.trace_l2_gram,
            label="trace L2 Gram",
        )
        projector = _readonly_matrix(
            self.retained_riesz_projector,
            label="retained Riesz projector",
        )
        missing = _readonly_matrix(
            self.missing_basis,
            label="missing basis",
        )
        enriched_dimension = int(self.enriched_dimension)
        retained_dimension = int(self.retained_dimension)
        missing_dimension = int(self.missing_dimension)
        if retained.shape != (enriched_dimension, retained_dimension):
            raise ValueError("retained embedding shape is inconsistent")
        if gram.shape != (enriched_dimension, enriched_dimension):
            raise ValueError("trace L2 Gram shape is inconsistent")
        if projector.shape != (enriched_dimension, enriched_dimension):
            raise ValueError("Riesz projector shape is inconsistent")
        if missing.shape != (enriched_dimension, missing_dimension):
            raise ValueError("missing basis shape is inconsistent")
        if len(self.mode_metadata) != missing_dimension:
            raise ValueError("mode metadata does not close missing dimension")
        if any(mode.global_row is not None for mode in self.mode_metadata):
            raise RuntimeError("qualification allocated a global p6 row")
        if len(self.shell_sha256) != 64:
            raise ValueError("shell hash must be SHA-256")
        if self.audit.get("pass") is not True:
            raise RuntimeError("trace complement shell is unqualified")
        object.__setattr__(self, "retained_embedding", retained)
        object.__setattr__(self, "trace_l2_gram", gram)
        object.__setattr__(self, "retained_riesz_projector", projector)
        object.__setattr__(self, "missing_basis", missing)


@dataclass(frozen=True)
class P5P6TraceComplementQualification:
    """Complete edge/face qualification product for orbit selection."""

    basix_version: str
    p5_element_sha256: str
    p6_element_sha256: str
    edge: P6TraceComplementShell
    face: P6TraceComplementShell
    qualification_sha256: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        for value in (
            self.p5_element_sha256,
            self.p6_element_sha256,
            self.qualification_sha256,
        ):
            if len(value) != 64:
                raise ValueError("qualification identities must be SHA-256")
        if self.audit.get("pass") is not True:
            raise RuntimeError("p5/p6 trace complement is unqualified")


def _standard_hcurl(
    degree: int,
) -> basix.finite_element.FiniteElement:
    return basix.create_element(
        basix.ElementFamily.N1E,
        _CELL,
        int(degree),
        basix.LagrangeVariant.legendre,
    )


def _entity_trace_samples(
    element: basix.finite_element.FiniteElement,
    *,
    entity_dimension: int,
    entity_index: int,
    points_per_axis: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    geometry = np.asarray(basix.cell.geometry(_CELL), dtype=np.float64)
    topology = basix.cell.topology(_CELL)
    vertices = geometry[topology[entity_dimension][entity_index]]
    origin = vertices[0]
    first_tangent = vertices[1] - origin
    axis, weights_1d = np.polynomial.legendre.leggauss(points_per_axis)
    axis = (axis + 1.0) / 2.0
    weights_1d = weights_1d / 2.0
    if entity_dimension == 1:
        length = float(np.linalg.norm(first_tangent))
        unit_tangents = np.asarray([first_tangent / length])
        points = origin[None, :] + axis[:, None] * first_tangent
        weights = weights_1d * length
    elif entity_dimension == 2:
        second_tangent = vertices[2] - origin
        area = float(np.linalg.norm(np.cross(first_tangent, second_tangent)))
        if area <= 0.0:
            raise RuntimeError("reference face parameterization is singular")
        first_unit = first_tangent / np.linalg.norm(first_tangent)
        second_unit = second_tangent / np.linalg.norm(second_tangent)
        if abs(float(np.dot(first_unit, second_unit))) > 1.0e-14:
            raise RuntimeError("reference face tangents are not orthogonal")
        unit_tangents = np.asarray([first_unit, second_unit])
        points = np.asarray(
            [
                origin + first * first_tangent + second * second_tangent
                for first in axis
                for second in axis
            ]
        )
        weights = np.asarray(
            [
                first_weight * second_weight * area
                for first_weight in weights_1d
                for second_weight in weights_1d
            ]
        )
    else:
        raise ValueError("only edge and face traces are supported")
    values = element.tabulate(
        0,
        np.ascontiguousarray(points, dtype=np.float64),
    )[0][:, element.entity_dofs[entity_dimension][entity_index], :]
    traces = np.einsum("qiv,tv->qit", values, unit_tangents)
    gram = np.einsum("q,qit,qjt->ij", weights, traces, traces)
    return (
        np.asarray((gram + gram.T) / 2.0),
        np.asarray(values),
        np.asarray(points),
        np.asarray(unit_tangents),
    )


def _piola_audit(
    element: basix.finite_element.FiniteElement,
    *,
    entity_values: np.ndarray,
    unit_tangents: np.ndarray,
    missing_basis: np.ndarray,
) -> dict[str, float]:
    reference_values = np.einsum(
        "qiv,im->qmv",
        entity_values,
        missing_basis,
    )
    flat_reference = np.ascontiguousarray(
        reference_values.reshape(1, -1, 3)
    )
    jacobian = np.asarray(
        [[[1.7, 0.2, 0.1], [0.0, 0.9, 0.15], [0.0, 0.0, 1.3]]],
        dtype=np.float64,
    )
    inverse = np.ascontiguousarray(np.linalg.inv(jacobian))
    determinant = np.ascontiguousarray(np.linalg.det(jacobian))
    physical = np.asarray(
        element.push_forward(
            flat_reference,
            jacobian,
            determinant,
            inverse,
        )
    )
    pulled_back = np.asarray(
        element.pull_back(
            np.ascontiguousarray(physical),
            jacobian,
            determinant,
            inverse,
        )
    )
    explicit_covariant = np.einsum(
        "qpi,qij->qpj",
        flat_reference,
        inverse,
    )
    physical_tangents = np.einsum(
        "ij,tj->ti",
        jacobian[0],
        unit_tangents,
    )
    reference_covectors = np.einsum(
        "qpi,ti->qpt",
        flat_reference,
        unit_tangents,
    )
    physical_covectors = np.einsum(
        "qpi,ti->qpt",
        physical,
        physical_tangents,
    )
    return {
        "push_forward_matches_explicit_covariant_piola": _relative_error(
            physical,
            explicit_covariant,
        ),
        "push_pull_roundtrip_relative_error": _relative_error(
            pulled_back,
            flat_reference,
        ),
        "tangential_covector_pullback_relative_error": _relative_error(
            physical_covectors,
            reference_covectors,
        ),
    }


def _build_shell(
    *,
    entity_kind: TraceEntityKind,
    retained_element: basix.finite_element.FiniteElement,
    enriched_element: basix.finite_element.FiniteElement,
    interpolation: np.ndarray,
    tolerance: float,
    condition_limit: float,
    points_per_axis: int,
) -> P6TraceComplementShell:
    (
        entity_dimension,
        expected_retained,
        expected_enriched,
        expected_missing,
        transform_key,
    ) = _EXPECTED_ENTITY_DIMENSIONS[entity_kind]
    retained_counts = tuple(
        len(entity)
        for entity in retained_element.entity_dofs[entity_dimension]
    )
    enriched_counts = tuple(
        len(entity)
        for entity in enriched_element.entity_dofs[entity_dimension]
    )
    if (
        set(retained_counts) != {expected_retained}
        or set(enriched_counts) != {expected_enriched}
    ):
        raise RuntimeError(
            f"unexpected p5/p6 {entity_kind} entity dimensions"
        )
    retained_dofs = np.asarray(
        retained_element.entity_dofs[entity_dimension][0],
        dtype=np.int32,
    )
    enriched_dofs = np.asarray(
        enriched_element.entity_dofs[entity_dimension][0],
        dtype=np.int32,
    )
    retained_embedding = np.asarray(
        interpolation[np.ix_(enriched_dofs, retained_dofs)],
        dtype=np.float64,
    )
    retained_rank, retained_rank_tolerance = _numerical_rank(
        retained_embedding
    )

    trace_gram, entity_values, _points, unit_tangents = (
        _entity_trace_samples(
            enriched_element,
            entity_dimension=entity_dimension,
            entity_index=0,
            points_per_axis=points_per_axis,
        )
    )
    refined_gram, _values, _refined_points, _tangents = (
        _entity_trace_samples(
            enriched_element,
            entity_dimension=entity_dimension,
            entity_index=0,
            points_per_axis=points_per_axis + 1,
        )
    )
    entity_gram_errors: list[float] = []
    entity_embedding_errors: list[float] = []
    for entity_index in range(len(enriched_counts)):
        entity_gram, _values, _entity_points, _entity_tangents = (
            _entity_trace_samples(
                enriched_element,
                entity_dimension=entity_dimension,
                entity_index=entity_index,
                points_per_axis=points_per_axis,
            )
        )
        entity_gram_errors.append(
            _relative_error(entity_gram, trace_gram)
        )
        entity_retained = np.asarray(
            retained_element.entity_dofs[entity_dimension][entity_index],
            dtype=np.int32,
        )
        entity_enriched = np.asarray(
            enriched_element.entity_dofs[entity_dimension][entity_index],
            dtype=np.int32,
        )
        entity_embedding = interpolation[
            np.ix_(entity_enriched, entity_retained)
        ]
        entity_embedding_errors.append(
            _relative_error(entity_embedding, retained_embedding)
        )

    gram_rank, gram_rank_tolerance = _numerical_rank(trace_gram)
    gram_condition = _condition_number(
        trace_gram,
        label=f"{entity_kind} trace L2 Gram",
    )
    retained_condition = _condition_number(
        retained_embedding,
        label=f"{entity_kind} retained embedding",
    )
    retained_gram = retained_embedding.T @ trace_gram @ retained_embedding
    retained_gram_condition = _condition_number(
        retained_gram,
        label=f"{entity_kind} retained Riesz Gram",
    )
    retained_riesz_projector = retained_embedding @ np.linalg.solve(
        retained_gram,
        retained_embedding.T @ trace_gram,
    )
    missing_projector = (
        np.eye(expected_enriched) - retained_riesz_projector
    )
    cholesky = np.linalg.cholesky(trace_gram)
    _orthogonal, upper, pivots = qr(
        cholesky.T @ missing_projector,
        mode="economic",
        pivoting=True,
        check_finite=False,
    )
    diagonal = np.abs(np.diag(upper))
    missing_rank = int(
        np.count_nonzero(
            diagonal
            > (
                32.0
                * expected_enriched
                * np.finfo(np.float64).eps
                * diagonal[0]
            )
        )
    )
    anchors = np.asarray(pivots[:expected_missing], dtype=np.int32)
    anchored_missing = missing_projector[:, anchors]
    anchored_gram = anchored_missing.T @ trace_gram @ anchored_missing
    anchored_cholesky = np.linalg.cholesky(
        (anchored_gram + anchored_gram.T) / 2.0
    )
    missing_basis = np.linalg.solve(
        anchored_cholesky,
        anchored_missing.T,
    ).T
    direct_sum = np.concatenate(
        (retained_embedding, missing_basis),
        axis=1,
    )
    direct_sum_rank, direct_sum_rank_tolerance = _numerical_rank(direct_sum)
    direct_sum_condition = _condition_number(
        direct_sum,
        label=f"{entity_kind} retained/missing direct sum",
    )

    riesz_identity_error = _relative_error(
        missing_basis.T @ trace_gram @ missing_basis,
        np.eye(expected_missing),
    )
    retained_missing_leakage = _relative_error(
        retained_embedding.T @ trace_gram @ missing_basis,
        np.zeros((expected_retained, expected_missing)),
    )
    projector_idempotence_error = _relative_error(
        retained_riesz_projector @ retained_riesz_projector,
        retained_riesz_projector,
    )
    projector_riesz_symmetry_error = _relative_error(
        retained_riesz_projector.T @ trace_gram,
        trace_gram @ retained_riesz_projector,
    )
    piola = _piola_audit(
        enriched_element,
        entity_values=entity_values,
        unit_tangents=unit_tangents,
        missing_basis=missing_basis,
    )

    retained_transforms = retained_element.entity_transformations()[
        transform_key
    ]
    enriched_transforms = enriched_element.entity_transformations()[
        transform_key
    ]
    generator_names = _GENERATOR_NAMES[transform_key]
    if (
        len(retained_transforms) != len(generator_names)
        or len(enriched_transforms) != len(generator_names)
    ):
        raise RuntimeError(
            f"unexpected Basix {transform_key} generator inventory"
        )
    transformation_qualifications = []
    transform_max_error = 0.0
    for generator_name, retained_transform, enriched_transform in zip(
        generator_names,
        retained_transforms,
        enriched_transforms,
        strict=True,
    ):
        induced_missing = (
            missing_basis.T
            @ trace_gram
            @ enriched_transform
            @ missing_basis
        )
        errors = {
            "retained_intertwining_relative_error": _relative_error(
                enriched_transform @ retained_embedding,
                retained_embedding @ retained_transform,
            ),
            "trace_gram_invariance_relative_error": _relative_error(
                enriched_transform.T
                @ trace_gram
                @ enriched_transform,
                trace_gram,
            ),
            "retained_into_missing_leakage_relative_error": (
                _relative_error(
                    missing_projector
                    @ enriched_transform
                    @ retained_embedding,
                    np.zeros_like(retained_embedding),
                )
            ),
            "missing_into_retained_leakage_relative_error": (
                _relative_error(
                    retained_riesz_projector
                    @ enriched_transform
                    @ missing_basis,
                    np.zeros_like(missing_basis),
                )
            ),
            "missing_intertwining_relative_error": _relative_error(
                enriched_transform @ missing_basis,
                missing_basis @ induced_missing,
            ),
            "induced_missing_orthogonality_relative_error": (
                _relative_error(
                    induced_missing.T @ induced_missing,
                    np.eye(expected_missing),
                )
            ),
        }
        transform_max_error = max(transform_max_error, *errors.values())
        missing_condition = _condition_number(
            induced_missing,
            label=f"{entity_kind} {generator_name} missing transform",
        )
        checks = MappingProxyType(
            {
                "retained_embedding_intertwines": (
                    errors["retained_intertwining_relative_error"]
                    <= tolerance
                ),
                "trace_l2_gram_is_invariant": (
                    errors["trace_gram_invariance_relative_error"]
                    <= tolerance
                ),
                "retained_shell_is_invariant": (
                    errors[
                        "retained_into_missing_leakage_relative_error"
                    ]
                    <= tolerance
                ),
                "missing_shell_is_invariant": (
                    errors[
                        "missing_into_retained_leakage_relative_error"
                    ]
                    <= tolerance
                ),
                "induced_missing_transform_intertwines": (
                    errors["missing_intertwining_relative_error"]
                    <= tolerance
                ),
                "induced_missing_transform_is_orthogonal": (
                    errors[
                        "induced_missing_orthogonality_relative_error"
                    ]
                    <= tolerance
                ),
                "induced_missing_transform_is_well_conditioned": (
                    missing_condition <= condition_limit
                ),
            }
        )
        if not all(checks.values()):
            failed = [name for name, passed in checks.items() if not passed]
            raise RuntimeError(
                f"{entity_kind} {generator_name} transformation "
                f"qualification failed: {', '.join(failed)}"
            )
        transform_audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.p6-trace-transformation-qualification.v1"
                ),
                "status": "entity_transformation_qualified",
                "pass": True,
                **errors,
                "induced_missing_condition_number": missing_condition,
                "checks": checks,
            }
        )
        transformation_qualifications.append(
            P6TraceTransformationQualification(
                generator_name=generator_name,
                enriched_transform=enriched_transform,
                retained_transform=retained_transform,
                induced_missing_transform=induced_missing,
                audit=transform_audit,
            )
        )

    mode_metadata = tuple(
        P6TraceModeMetadata(
            local_mode_index=mode_index,
            anchor_enriched_entity_dof=int(anchors[mode_index]),
            canonical_p6_entity_dof=int(
                enriched_dofs[anchors[mode_index]]
            ),
            coefficient_sha256=_sha256_payload(
                {
                    "schema": "task035b.p6-trace-complement-mode.v1",
                    "entity_kind": entity_kind,
                    "local_mode_index": mode_index,
                    "anchor_enriched_entity_dof": int(
                        anchors[mode_index]
                    ),
                },
                [("coefficients", missing_basis[:, mode_index])],
            ),
        )
        for mode_index in range(expected_missing)
    )
    quadrature_error = _relative_error(refined_gram, trace_gram)
    checks = MappingProxyType(
        {
            "entity_dimensions_match_p5_p6_shell": (
                expected_enriched - expected_retained == expected_missing
            ),
            "retained_embedding_has_full_rank": (
                retained_rank == expected_retained
            ),
            "trace_l2_gram_has_full_rank": (
                gram_rank == expected_enriched
            ),
            "missing_projector_has_expected_rank": (
                missing_rank == expected_missing
            ),
            "retained_missing_direct_sum_has_full_rank": (
                direct_sum_rank == expected_enriched
            ),
            "trace_l2_gram_is_well_conditioned": (
                gram_condition <= condition_limit
            ),
            "retained_embedding_is_well_conditioned": (
                retained_condition <= condition_limit
            ),
            "retained_riesz_gram_is_well_conditioned": (
                retained_gram_condition <= condition_limit
            ),
            "direct_sum_is_well_conditioned": (
                direct_sum_condition <= condition_limit
            ),
            "missing_basis_is_riesz_orthonormal": (
                riesz_identity_error <= tolerance
            ),
            "retained_missing_riesz_leakage_absent": (
                retained_missing_leakage <= tolerance
            ),
            "retained_riesz_projector_is_idempotent": (
                projector_idempotence_error <= tolerance
            ),
            "retained_projector_is_riesz_self_adjoint": (
                projector_riesz_symmetry_error <= tolerance
            ),
            "quadrature_is_converged": quadrature_error <= tolerance,
            "all_reference_entities_share_trace_gram": (
                max(entity_gram_errors) <= tolerance
            ),
            "all_reference_entities_share_retained_embedding": (
                max(entity_embedding_errors) <= tolerance
            ),
            "covariant_piola_push_forward_matches": (
                piola[
                    "push_forward_matches_explicit_covariant_piola"
                ]
                <= tolerance
            ),
            "covariant_piola_roundtrip_passes": (
                piola["push_pull_roundtrip_relative_error"] <= tolerance
            ),
            "tangential_covectors_pull_back_exactly": (
                piola[
                    "tangential_covector_pullback_relative_error"
                ]
                <= tolerance
            ),
            "entity_transformations_are_qualified": (
                len(transformation_qualifications)
                == len(generator_names)
            ),
            "qualification_allocates_no_global_rows": all(
                mode.global_row is None for mode in mode_metadata
            ),
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            f"{entity_kind} p6 trace complement qualification failed: "
            + ", ".join(failed)
        )
    shell_sha256 = _sha256_payload(
        {
            "schema": "task035b.p6-trace-complement-shell.v1",
            "basix_version": basix.__version__,
            "entity_kind": entity_kind,
            "entity_dimension": entity_dimension,
            "retained_dimension": expected_retained,
            "enriched_dimension": expected_enriched,
            "missing_dimension": expected_missing,
            "quadrature_points_per_axis": points_per_axis,
            "mode_hashes": [
                mode.coefficient_sha256 for mode in mode_metadata
            ],
            "generator_names": list(generator_names),
        },
        [
            ("retained_embedding", retained_embedding),
            ("trace_l2_gram", trace_gram),
            ("missing_basis", missing_basis),
            *[
                (
                    f"missing_transform[{item.generator_name}]",
                    item.induced_missing_transform,
                )
                for item in transformation_qualifications
            ],
        ],
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.p5-p6-trace-complement-shell.v1"
            ),
            "status": "p5_p6_trace_complement_shell_qualified",
            "pass": True,
            "entity_kind": entity_kind,
            "entity_dimension": entity_dimension,
            "retained_dimension": expected_retained,
            "enriched_dimension": expected_enriched,
            "missing_dimension": expected_missing,
            "retained_embedding_rank": retained_rank,
            "retained_embedding_rank_tolerance": (
                retained_rank_tolerance
            ),
            "trace_l2_gram_rank": gram_rank,
            "trace_l2_gram_rank_tolerance": gram_rank_tolerance,
            "missing_projector_rank": missing_rank,
            "direct_sum_rank": direct_sum_rank,
            "direct_sum_rank_tolerance": direct_sum_rank_tolerance,
            "trace_l2_gram_condition_number": gram_condition,
            "retained_embedding_condition_number": retained_condition,
            "retained_riesz_gram_condition_number": (
                retained_gram_condition
            ),
            "direct_sum_condition_number": direct_sum_condition,
            "missing_riesz_identity_relative_error": (
                riesz_identity_error
            ),
            "retained_missing_riesz_leakage_relative_error": (
                retained_missing_leakage
            ),
            "projector_idempotence_relative_error": (
                projector_idempotence_error
            ),
            "projector_riesz_symmetry_relative_error": (
                projector_riesz_symmetry_error
            ),
            "quadrature_points_per_axis": points_per_axis,
            "quadrature_polynomial_exactness_per_axis": (
                2 * points_per_axis - 1
            ),
            "quadrature_refinement_relative_error": quadrature_error,
            "all_entity_gram_max_relative_error": max(
                entity_gram_errors
            ),
            "all_entity_embedding_max_relative_error": max(
                entity_embedding_errors
            ),
            "transformation_max_relative_error": transform_max_error,
            "piola": MappingProxyType(piola),
            "mode_anchor_entity_dofs": tuple(map(int, anchors)),
            "mode_coefficient_sha256": tuple(
                mode.coefficient_sha256 for mode in mode_metadata
            ),
            "global_rows_allocated": 0,
            "inactive_modes_allocated_global_rows": False,
            "matrix_assembly_performed": False,
            "dolfinx_mesh_integration_performed": False,
            "periodic_orbit_selection_performed": False,
            "actual_channel_dwr_computed": False,
            "scope": (
                "Basix reference-entity qualification input for the "
                "separate periodic-orbit and later assembly layers"
            ),
            "checks": checks,
            "ordinary_default_changed": False,
        }
    )
    return P6TraceComplementShell(
        entity_kind=entity_kind,
        entity_dimension=entity_dimension,
        retained_dimension=expected_retained,
        enriched_dimension=expected_enriched,
        missing_dimension=expected_missing,
        retained_embedding=retained_embedding,
        trace_l2_gram=trace_gram,
        retained_riesz_projector=retained_riesz_projector,
        missing_basis=missing_basis,
        mode_metadata=mode_metadata,
        transformation_generators=tuple(
            transformation_qualifications
        ),
        shell_sha256=shell_sha256,
        audit=audit,
    )


@lru_cache(maxsize=4)
def qualify_p5_p6_nedelec_hexahedron_trace_complement(
    *,
    tolerance: float = 2.0e-10,
    condition_limit: float = 1.0e8,
    quadrature_points_per_axis: int = 9,
) -> P5P6TraceComplementQualification:
    """Build and fail-closed qualify the physical missing-p6 trace basis."""

    tolerance = float(tolerance)
    condition_limit = float(condition_limit)
    quadrature_points_per_axis = int(quadrature_points_per_axis)
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("qualification tolerance must be positive")
    if not np.isfinite(condition_limit) or condition_limit <= 1.0:
        raise ValueError("condition limit must be finite and greater than one")
    if quadrature_points_per_axis < 7:
        raise ValueError(
            "p6 trace qualification needs at least seven Gauss points "
            "per entity axis"
        )
    retained_element = _standard_hcurl(5)
    enriched_element = _standard_hcurl(6)
    element_checks = {
        "retained_family_is_nedelec_first_kind": (
            retained_element.family == basix.ElementFamily.N1E
        ),
        "enriched_family_is_nedelec_first_kind": (
            enriched_element.family == basix.ElementFamily.N1E
        ),
        "both_cells_are_hexahedra": (
            retained_element.cell_type == _CELL
            and enriched_element.cell_type == _CELL
        ),
        "degrees_are_p5_p6": (
            retained_element.degree == 5 and enriched_element.degree == 6
        ),
        "both_use_covariant_piola": (
            retained_element.map_type == basix.MapType.covariantPiola
            and enriched_element.map_type == basix.MapType.covariantPiola
        ),
        "both_are_hcurl_conforming": (
            retained_element.sobolev_space == basix.SobolevSpace.HCurl
            and enriched_element.sobolev_space
            == basix.SobolevSpace.HCurl
        ),
        "both_use_legendre_variant": (
            retained_element.lagrange_variant
            == basix.LagrangeVariant.legendre
            and enriched_element.lagrange_variant
            == basix.LagrangeVariant.legendre
        ),
    }
    if not all(element_checks.values()):
        failed = [
            name for name, passed in element_checks.items() if not passed
        ]
        raise RuntimeError(
            "Basix p5/p6 element identity failed: " + ", ".join(failed)
        )
    interpolation = np.asarray(
        basix.compute_interpolation_operator(
            retained_element,
            enriched_element,
        ),
        dtype=np.float64,
    )
    interpolation_rank, interpolation_rank_tolerance = _numerical_rank(
        interpolation
    )
    if interpolation_rank != retained_element.dim:
        raise RuntimeError("global p5-to-p6 interpolation is rank deficient")

    edge = _build_shell(
        entity_kind="edge",
        retained_element=retained_element,
        enriched_element=enriched_element,
        interpolation=interpolation,
        tolerance=tolerance,
        condition_limit=condition_limit,
        points_per_axis=quadrature_points_per_axis,
    )
    face = _build_shell(
        entity_kind="face",
        retained_element=retained_element,
        enriched_element=enriched_element,
        interpolation=interpolation,
        tolerance=tolerance,
        condition_limit=condition_limit,
        points_per_axis=quadrature_points_per_axis,
    )
    p5_hash = _element_identity_hash(retained_element)
    p6_hash = _element_identity_hash(enriched_element)
    qualification_hash = _sha256_payload(
        {
            "schema": (
                "task035b.p5-p6-nedelec-hexa-trace-qualification.v1"
            ),
            "basix_version": basix.__version__,
            "p5_element_sha256": p5_hash,
            "p6_element_sha256": p6_hash,
            "edge_shell_sha256": edge.shell_sha256,
            "face_shell_sha256": face.shell_sha256,
            "tolerance": tolerance,
            "condition_limit": condition_limit,
            "quadrature_points_per_axis": quadrature_points_per_axis,
        },
        [("p5_to_p6_interpolation", interpolation)],
    )
    checks = MappingProxyType(
        {
            **element_checks,
            "global_p5_to_p6_interpolation_has_full_column_rank": (
                interpolation_rank == retained_element.dim
            ),
            "edge_missing_shell_has_one_mode": (
                edge.missing_dimension == 1
            ),
            "face_missing_shell_has_twenty_modes": (
                face.missing_dimension == 20
            ),
            "both_shells_pass": (
                edge.audit["pass"] is True
                and face.audit["pass"] is True
            ),
            "qualification_allocates_no_global_rows": (
                edge.audit["global_rows_allocated"] == 0
                and face.audit["global_rows_allocated"] == 0
            ),
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "p5/p6 trace qualification failed: " + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.p5-p6-nedelec-hexa-trace-qualification.v1"
            ),
            "status": "p5_p6_trace_complement_qualified",
            "pass": True,
            "basix_version": basix.__version__,
            "cell_type": "hexahedron",
            "family": "Nedelec first kind H(curl)",
            "retained_degree": 5,
            "enriched_degree": 6,
            "map_type": "covariantPiola",
            "p5_dimension": int(retained_element.dim),
            "p6_dimension": int(enriched_element.dim),
            "interpolation_rank": interpolation_rank,
            "interpolation_rank_tolerance": (
                interpolation_rank_tolerance
            ),
            "edge_missing_dimension": edge.missing_dimension,
            "face_missing_dimension": face.missing_dimension,
            "p5_element_sha256": p5_hash,
            "p6_element_sha256": p6_hash,
            "edge_shell_sha256": edge.shell_sha256,
            "face_shell_sha256": face.shell_sha256,
            "qualification_sha256": qualification_hash,
            "basis_hash_semantics": (
                "bytewise Basix element data, p5-to-p6 interpolation, "
                "trace L2 Gram, Riesz complement, and induced entity "
                "transformations in the qualified Linux ABI"
            ),
            "global_rows_allocated": 0,
            "inactive_modes_allocated_global_rows": False,
            "matrix_assembly_performed": False,
            "dolfinx_mesh_integration_performed": False,
            "periodic_orbit_selection_performed": False,
            "actual_channel_dwr_computed": False,
            "caller_must_bind_source_and_mesh_provenance": True,
            "checks": checks,
            "ordinary_default_changed": False,
        }
    )
    return P5P6TraceComplementQualification(
        basix_version=basix.__version__,
        p5_element_sha256=p5_hash,
        p6_element_sha256=p6_hash,
        edge=edge,
        face=face,
        qualification_sha256=qualification_hash,
        audit=audit,
    )


__all__ = [
    "P5P6TraceComplementQualification",
    "P6TraceComplementShell",
    "P6TraceModeMetadata",
    "P6TraceTransformationQualification",
    "qualify_p5_p6_nedelec_hexahedron_trace_complement",
]
