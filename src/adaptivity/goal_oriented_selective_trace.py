"""Goal-oriented quotient algebra for periodic selective p6 faces.

The coarse space ``B`` has p5 edges/faces and p6 cell interiors.  The
selective carrier ``S`` has p5 edges and p6 faces.  The fine trace ``F`` is
global p6 on the same physical mesh.  This module constructs:

* the exact ``B -> S -> F`` injections between physical trace roots;
* one 20-dimensional quotient for every periodic physical face orbit while
  keeping all edge traces in their p5 subspace; and
* a Gram-corrected signed pairing partition that does not double-count
  neighbouring faces with shared-edge support.

It contains no PDE runner and does not select a production default.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import sparse
from scipy.linalg import null_space
from scipy.sparse.linalg import splu

from .exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    build_variable_p_reference_space,
)
from .hcurl_broken_trace_graph import (
    BrokenHexTraceConstraintAuthority,
    PhysicalTraceEntity,
    physical_face_closure_rows,
)


_ROUND_OFF_LIMIT = 5.0e-10
_QUOTIENT_DIMENSION = 20


def _csr_sha256(matrix: sparse.spmatrix, *, namespace: str) -> str:
    values = sparse.csr_matrix(matrix, dtype=np.complex128)
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    for label, array in (
        ("shape", np.asarray(values.shape, dtype=np.int64)),
        ("indptr", np.asarray(values.indptr, dtype=np.int64)),
        ("indices", np.asarray(values.indices, dtype=np.int64)),
        ("data", np.asarray(values.data, dtype=np.complex128)),
    ):
        contiguous = np.ascontiguousarray(array)
        digest.update(label.encode("ascii"))
        digest.update(b"\0")
        digest.update(contiguous.dtype.str.encode("ascii"))
        digest.update(b"\0")
        digest.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
        digest.update(contiguous.view(np.uint8))
    return digest.hexdigest()


def _json_sha256(value: Any, *, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )
    return digest.hexdigest()


def _maximum_sparse_absolute(matrix: sparse.spmatrix) -> float:
    values = sparse.csr_matrix(matrix)
    return (
        0.0
        if values.nnz == 0
        else float(np.max(np.abs(values.data), initial=0.0))
    )


def _canonicalize_columns(values: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(values, dtype=np.complex128)
    for column in range(result.shape[1]):
        pivot = int(np.argmax(np.abs(result[:, column])))
        magnitude = abs(result[pivot, column])
        if magnitude:
            result[:, column] *= np.conj(
                result[pivot, column] / magnitude
            )
    return result


def _entity_offsets(
    authority: BrokenHexTraceConstraintAuthority,
) -> tuple[
    dict[tuple[int, tuple[int, ...]], tuple[PhysicalTraceEntity, int, int]],
    dict[Any, int],
]:
    catalog: dict[
        tuple[int, tuple[int, ...]],
        tuple[PhysicalTraceEntity, int, int],
    ] = {}
    offset = 0
    for entity in authority.entities:
        stop = offset + len(entity.rows)
        if tuple(authority.graph.raw_rows[offset:stop]) != entity.rows:
            raise RuntimeError(
                "physical entity order differs from flattened graph rows"
            )
        identity = (entity.dimension, entity.geometry_key)
        if identity in catalog:
            raise RuntimeError("physical trace authority repeats an entity")
        catalog[identity] = (entity, offset, stop)
        offset = stop
    if offset != len(authority.graph.raw_rows):
        raise RuntimeError("physical entity slices do not close")
    return catalog, {
        row: index
        for index, row in enumerate(authority.graph.raw_rows)
    }


def _reference_space(label: str):
    if label == "B":
        degree_map = HexaEntityDegreeMap.dimension_uniform(
            edge_degree=5,
            face_degree=5,
            cell_degree=6,
        )
    elif label == "S":
        degree_map = HexaEntityDegreeMap.dimension_uniform(
            edge_degree=5,
            face_degree=6,
            cell_degree=6,
        )
    elif label == "F":
        degree_map = HexaEntityDegreeMap.uniform(6)
    else:
        raise ValueError(f"unknown trace hierarchy label {label!r}")
    return build_variable_p_reference_space(degree_map)


@lru_cache(maxsize=3)
def _reference_trace_injection(
    source_label: str,
    target_label: str,
) -> tuple[np.ndarray, np.ndarray, Mapping[str, Any]]:
    """Return one exact local trace injection in canonical entity order."""

    allowed = {("B", "S"), ("S", "F"), ("B", "F")}
    if (source_label, target_label) not in allowed:
        raise ValueError(
            f"unsupported trace hierarchy edge {source_label}->{target_label}"
        )
    source = _reference_space(source_label)
    target = _reference_space(target_label)
    source_expansion = np.asarray(
        source.hcurl_to_p6,
        dtype=np.complex128,
    )
    target_expansion = np.asarray(
        target.hcurl_to_p6,
        dtype=np.complex128,
    )
    if target_label == "F":
        identity_error = float(
            np.max(
                np.abs(
                    target_expansion
                    - np.eye(
                        target_expansion.shape[0],
                        dtype=np.complex128,
                    )
                ),
                initial=0.0,
            )
        )
        if identity_error > _ROUND_OFF_LIMIT:
            raise RuntimeError("uniform p6 ceased to be the carrier space")
        injection = np.ascontiguousarray(source_expansion)
        rank = int(target_expansion.shape[1])
        singular_values = np.ones(rank, dtype=np.float64)
    else:
        injection, _residuals, rank, singular_values = np.linalg.lstsq(
            target_expansion,
            source_expansion,
            rcond=None,
        )
    closure_error = float(
        np.max(
            np.abs(target_expansion @ injection - source_expansion),
            initial=0.0,
        )
    )
    if rank != target_expansion.shape[1] or closure_error > _ROUND_OFF_LIMIT:
        raise RuntimeError(
            f"reference trace injection {source_label}->{target_label} "
            "does not close"
        )

    source_edge = np.asarray(
        source.hcurl_element.entity_dofs[1][0],
        dtype=np.int64,
    )
    target_edge = np.asarray(
        target.hcurl_element.entity_dofs[1][0],
        dtype=np.int64,
    )
    source_closure = np.asarray(
        source.hcurl_element.entity_closure_dofs[2][0],
        dtype=np.int64,
    )
    target_closure = np.asarray(
        target.hcurl_element.entity_closure_dofs[2][0],
        dtype=np.int64,
    )
    edge = np.ascontiguousarray(
        injection[np.ix_(target_edge, source_edge)]
    )
    closure = np.ascontiguousarray(
        injection[np.ix_(target_closure, source_closure)]
    )
    outside_source = np.setdiff1d(
        np.arange(source.hcurl_dimension, dtype=np.int64),
        source_closure,
        assume_unique=True,
    )
    outside_target = np.setdiff1d(
        np.arange(target.hcurl_dimension, dtype=np.int64),
        target_closure,
        assume_unique=True,
    )
    target_closure_from_outside = float(
        np.max(
            np.abs(
                injection[np.ix_(target_closure, outside_source)]
            ),
            initial=0.0,
        )
    )
    outside_target_from_closure = float(
        np.max(
            np.abs(
                injection[np.ix_(outside_target, source_closure)]
            ),
            initial=0.0,
        )
    )
    expected_shapes = {
        ("B", "S"): ((5, 5), (80, 60)),
        ("S", "F"): ((6, 5), (84, 80)),
        ("B", "F"): ((6, 5), (84, 60)),
    }
    if (
        (edge.shape, closure.shape)
        != expected_shapes[(source_label, target_label)]
        or target_closure_from_outside > _ROUND_OFF_LIMIT
    ):
        raise RuntimeError(
            f"reference trace locality {source_label}->{target_label} failed"
        )
    audit = MappingProxyType(
        {
            "source": source_label,
            "target": target_label,
            "source_dimension": source.hcurl_dimension,
            "target_dimension": target.hcurl_dimension,
            "rank": int(rank),
            "minimum_singular_value": float(
                np.min(singular_values, initial=np.inf)
            ),
            "carrier_closure_error_max": closure_error,
            "target_closure_from_outside_source_max": (
                target_closure_from_outside
            ),
            "outside_target_from_source_closure_max": (
                outside_target_from_closure
            ),
        }
    )
    return edge, closure, audit


def _authority_role(
    authority: BrokenHexTraceConstraintAuthority,
) -> str:
    edge_degrees = {
        entity.degree
        for entity in authority.entities
        if entity.dimension == 1
    }
    face_degrees = {
        entity.degree
        for entity in authority.entities
        if entity.dimension == 2
    }
    physical_faces = {
        entity.geometry_key
        for entity in authority.entities
        if entity.dimension == 2
    }
    selected_faces = set(authority.selected_p6_face_geometry_keys)
    if (
        edge_degrees == {5}
        and face_degrees == {5}
        and not selected_faces
    ):
        return "B"
    if (
        edge_degrees == {5}
        and face_degrees == {6}
        and selected_faces == physical_faces
    ):
        return "S"
    if (
        edge_degrees == {6}
        and face_degrees == {6}
        and not selected_faces
    ):
        return "F"
    raise ValueError(
        "authority is not one of the qualified B/S/F trace spaces"
    )


@dataclass(frozen=True)
class PhysicalRootInjection:
    """Exact independent-root injection along one B/S/F hierarchy edge."""

    trace_injection: sparse.csr_matrix
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class PeriodicFaceQuotient:
    """All periodic face-orbit quotient generators in global p6 roots."""

    generators: sparse.csr_matrix
    orbit_slices: tuple[tuple[int, int], ...]
    orbit_geometry_keys: tuple[tuple[tuple[int, ...], ...], ...]
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class FaceResidualPartition:
    """One Gram-corrected face projection of a fine-space residual."""

    coefficients: np.ndarray
    face_projection: np.ndarray
    unexplained: np.ndarray
    orbit_components_l2: np.ndarray
    audit: Mapping[str, Any]


def build_nested_trace_root_injection(
    source: BrokenHexTraceConstraintAuthority,
    target: BrokenHexTraceConstraintAuthority,
) -> PhysicalRootInjection:
    """Build one exact physical independent-root hierarchy injection."""

    if source.audit["pass"] is not True or target.audit["pass"] is not True:
        raise ValueError("both physical trace authorities must pass")
    source_label = _authority_role(source)
    target_label = _authority_role(target)
    edge_injection, closure_injection, reference_audit = (
        _reference_trace_injection(source_label, target_label)
    )
    source_entities, source_row_index = _entity_offsets(source)
    target_entities, target_row_index = _entity_offsets(target)
    if set(source_entities) != set(target_entities):
        raise ValueError("source and target physical geometry catalogs differ")
    if any(
        left[0].canonical_points
        != target_entities[key][0].canonical_points
        for key, left in source_entities.items()
    ):
        raise ValueError("source and target canonical geometry differs")

    raw_injection = sparse.lil_matrix(
        (
            len(target.graph.raw_rows),
            len(source.graph.raw_rows),
        ),
        dtype=np.complex128,
    )
    source_catalog = {
        key: row[0] for key, row in source_entities.items()
    }
    target_catalog = {
        key: row[0] for key, row in target_entities.items()
    }
    for identity in sorted(target_entities):
        target_entity, target_start, target_stop = target_entities[identity]
        source_entity, source_start, source_stop = source_entities[
            identity
        ]
        if target_entity.dimension == 1:
            if edge_injection.shape != (
                target_stop - target_start,
                source_stop - source_start,
            ):
                raise RuntimeError("physical edge injection shape changed")
            raw_injection[
                target_start:target_stop,
                source_start:source_stop,
            ] = edge_injection
        elif target_entity.dimension == 2:
            target_closure = physical_face_closure_rows(
                target_entity,
                target_catalog,
            )
            source_closure = physical_face_closure_rows(
                source_entity,
                source_catalog,
            )
            if closure_injection.shape != (
                len(target_closure),
                len(source_closure),
            ):
                raise RuntimeError("physical face closure shape changed")
            target_edge_rows = (
                len(target_closure) - len(target_entity.rows)
            )
            target_rows = np.asarray(
                [
                    target_row_index[row]
                    for row in target_closure[target_edge_rows:]
                ],
                dtype=np.int64,
            )
            source_rows = np.asarray(
                [source_row_index[row] for row in source_closure],
                dtype=np.int64,
            )
            if not np.array_equal(
                target_rows,
                np.arange(
                    target_start,
                    target_stop,
                    dtype=np.int64,
                ),
            ):
                raise RuntimeError(
                    "physical target face rows differ from closure ordering"
                )
            raw_injection[
                np.ix_(target_rows, source_rows)
            ] = closure_injection[target_edge_rows:, :]
        else:
            raise RuntimeError("unexpected H(curl) physical entity")
    raw_injection = raw_injection.tocsr()

    source_expansion = sparse.csr_matrix(
        source.graph.raw_from_independent,
        dtype=np.complex128,
    )
    target_expansion = sparse.csr_matrix(
        target.graph.raw_from_independent,
        dtype=np.complex128,
    )
    target_raw = (raw_injection @ source_expansion).tocsr()
    root_indices = np.asarray(
        [target_row_index[row] for row in target.graph.root_rows],
        dtype=np.int64,
    )
    trace_injection = target_raw[root_indices].tocsr()
    trace_injection.eliminate_zeros()
    closure = (
        target_expansion @ trace_injection - target_raw
    ).tocsr()
    closure.eliminate_zeros()
    closure_error = _maximum_sparse_absolute(closure)
    if (
        trace_injection.shape[1] != len(source.graph.root_rows)
        or trace_injection.shape[0] != len(target.graph.root_rows)
        or closure_error > _ROUND_OFF_LIMIT
    ):
        raise RuntimeError(
            "physical independent-root injection does not close"
        )
    audit = {
        "status": (
            f"{source_label}_to_{target_label}_physical_root_"
            "injection_pass"
        ),
        "pass": True,
        "source_space": source_label,
        "target_space": target_label,
        "source_independent_trace_rows": int(
            trace_injection.shape[1]
        ),
        "target_independent_trace_rows": int(trace_injection.shape[0]),
        "dimension_delta": int(
            trace_injection.shape[0] - trace_injection.shape[1]
        ),
        "physical_graph_closure_error_max": closure_error,
        "reference": dict(reference_audit),
        "trace_injection_sha256": _csr_sha256(
            trace_injection,
            namespace=(
                "task035e.goal-oriented-root-injection.v2."
                f"{source_label}-{target_label}"
            ),
        ),
        "inactive_modes_globally_numbered": False,
        "ordinary_default_changed": False,
    }
    return PhysicalRootInjection(
        trace_injection=trace_injection,
        audit=MappingProxyType(audit),
    )


def build_p5_to_global_p6_root_injection(
    coarse: BrokenHexTraceConstraintAuthority,
    fine: BrokenHexTraceConstraintAuthority,
) -> PhysicalRootInjection:
    """Build the qualified direct ``B -> F`` root injection."""

    if _authority_role(coarse) != "B" or _authority_role(fine) != "F":
        raise ValueError("direct p5/global-p6 injection requires B and F")
    return build_nested_trace_root_injection(coarse, fine)


def build_periodic_face_quotient(
    coarse: BrokenHexTraceConstraintAuthority,
    selective: BrokenHexTraceConstraintAuthority,
    fine: BrokenHexTraceConstraintAuthority,
    root_injection: PhysicalRootInjection,
) -> PeriodicFaceQuotient:
    """Build one exact ``S/B`` quotient for every periodic face orbit."""

    coarse_to_fine = sparse.csr_matrix(
        root_injection.trace_injection,
        dtype=np.complex128,
    )
    coarse_to_selective_authority = build_nested_trace_root_injection(
        coarse,
        selective,
    )
    selective_to_fine_authority = build_nested_trace_root_injection(
        selective,
        fine,
    )
    coarse_to_selective = sparse.csr_matrix(
        coarse_to_selective_authority.trace_injection,
        dtype=np.complex128,
    )
    selective_to_fine = sparse.csr_matrix(
        selective_to_fine_authority.trace_injection,
        dtype=np.complex128,
    )
    composition = (
        selective_to_fine @ coarse_to_selective - coarse_to_fine
    ).tocsr()
    composition.eliminate_zeros()
    composition_error = _maximum_sparse_absolute(composition)
    if composition_error > _ROUND_OFF_LIMIT:
        raise RuntimeError("B -> S -> F root injection does not commute")

    selective_expansion = sparse.csr_matrix(
        selective.graph.raw_from_independent,
        dtype=np.complex128,
    )
    selective_entities, selective_row_index = _entity_offsets(selective)
    fine_entities, _fine_row_index = _entity_offsets(fine)
    coarse_entities, _ = _entity_offsets(coarse)
    if not (
        set(fine_entities)
        == set(selective_entities)
        == set(coarse_entities)
    ):
        raise ValueError("B/S/F physical catalogs differ")

    orbit_map: dict[
        tuple[int, ...],
        list[PhysicalTraceEntity],
    ] = {}
    for entity, start, stop in selective_entities.values():
        if entity.dimension != 2:
            continue
        support = tuple(
            sorted(
                set(
                    map(
                        int,
                        selective_expansion[start:stop].indices,
                    )
                )
            )
        )
        if len(support) != 60:
            raise RuntimeError(
                "one p6 physical face does not have 60 root supports"
            )
        orbit_map.setdefault(support, []).append(entity)

    data_blocks: list[np.ndarray] = []
    row_blocks: list[np.ndarray] = []
    column_blocks: list[np.ndarray] = []
    orbit_slices: list[tuple[int, int]] = []
    orbit_keys: list[tuple[tuple[int, ...], ...]] = []
    orbit_audits: list[dict[str, Any]] = []
    column_offset = 0
    entity_catalog = {
        key: row[0] for key, row in selective_entities.items()
    }
    for face_support, faces in sorted(
        orbit_map.items(),
        key=lambda item: tuple(
            sorted(face.geometry_key for face in item[1])
        ),
    ):
        geometry_keys = tuple(
            sorted(face.geometry_key for face in faces)
        )
        closure_rows = {
            row
            for face in faces
            for row in physical_face_closure_rows(
                face,
                entity_catalog,
            )
        }
        closure_raw = np.asarray(
            sorted(selective_row_index[row] for row in closure_rows),
            dtype=np.int64,
        )
        support = np.unique(
            selective_expansion[closure_raw].indices
        ).astype(np.int64, copy=False)
        local_injection = coarse_to_selective[support].tocsr()
        coarse_columns = np.unique(
            local_injection.indices
        ).astype(np.int64, copy=False)
        coarse_block = local_injection[:, coarse_columns].toarray()
        local_quotient = _canonicalize_columns(
            null_space(
                coarse_block.conj().T,
                rcond=1.0e-11,
            )
        )
        if local_quotient.shape != (
            len(support),
            _QUOTIENT_DIMENSION,
        ):
            raise RuntimeError(
                "one periodic face orbit does not have a 20-mode "
                "p5-edge/p6-face quotient"
        )
        coarse_cross = float(
            np.max(
                np.abs(
                    coarse_block.conj().T @ local_quotient
                ),
                initial=0.0,
            )
        )
        gram_error = float(
            np.max(
                np.abs(
                    local_quotient.conj().T @ local_quotient
                    - np.eye(
                        _QUOTIENT_DIMENSION,
                        dtype=np.complex128,
                    )
                ),
                initial=0.0,
            )
        )
        if max(coarse_cross, gram_error) > _ROUND_OFF_LIMIT:
            raise RuntimeError("one periodic face quotient failed closure")
        significant = np.abs(local_quotient) > 1.0e-14
        rows, columns = np.nonzero(significant)
        row_blocks.append(support[rows])
        column_blocks.append(columns + column_offset)
        data_blocks.append(local_quotient[rows, columns])
        orbit_slices.append(
            (
                column_offset,
                column_offset + _QUOTIENT_DIMENSION,
            )
        )
        orbit_keys.append(geometry_keys)
        orbit_audits.append(
            {
                "geometry_keys": [list(key) for key in geometry_keys],
                "periodic_copy_count": len(geometry_keys),
                "face_root_support_rows": len(face_support),
                "closure_root_support_rows": len(support),
                "coarse_support_columns": len(coarse_columns),
                "coarse_cross_error_max": coarse_cross,
                "local_gram_error_max": gram_error,
            }
        )
        column_offset += _QUOTIENT_DIMENSION

    selective_generators = sparse.coo_matrix(
        (
            np.concatenate(data_blocks),
            (
                np.concatenate(row_blocks),
                np.concatenate(column_blocks),
            ),
        ),
        shape=(selective_expansion.shape[1], column_offset),
        dtype=np.complex128,
    ).tocsr()
    selective_generators.eliminate_zeros()
    generators = (
        selective_to_fine @ selective_generators
    ).tocsr()
    generators.eliminate_zeros()
    coarse_cross = _maximum_sparse_absolute(
        coarse_to_selective.conj().T @ selective_generators
    )
    gram = (generators.conj().T @ generators).tocsc()
    gram.eliminate_zeros()
    factor = splu(gram)
    pivot_min = float(np.min(np.abs(factor.U.diagonal())))
    if (
        coarse_cross > _ROUND_OFF_LIMIT
        or not np.isfinite(pivot_min)
        or pivot_min <= np.finfo(float).tiny
    ):
        raise RuntimeError("global periodic face quotient is rank deficient")
    del factor
    orbit_catalog = [
        {
            "orbit": index,
            **row,
        }
        for index, row in enumerate(orbit_audits)
    ]
    audit = {
        "status": "periodic_physical_face_quotient_pass",
        "pass": True,
        "physical_face_count": int(
            sum(len(keys) for keys in orbit_keys)
        ),
        "periodic_physical_face_orbit_count": len(orbit_keys),
        "quotient_modes_per_orbit": _QUOTIENT_DIMENSION,
        "face_quotient_rows": int(column_offset),
        "global_coarse_cross_error_max": coarse_cross,
        "B_independent_trace_rows": int(coarse_to_selective.shape[1]),
        "S_independent_trace_rows": int(coarse_to_selective.shape[0]),
        "F_independent_trace_rows": int(selective_to_fine.shape[0]),
        "B_to_S_to_F_composition_error_max": composition_error,
        "B_to_S": dict(coarse_to_selective_authority.audit),
        "S_to_F": dict(selective_to_fine_authority.audit),
        "B_to_F": dict(root_injection.audit),
        "gram_nnz": int(gram.nnz),
        "gram_minimum_lu_pivot_abs": pivot_min,
        "generators_sha256": _csr_sha256(
            generators,
            namespace="task035e.goal-oriented-face-generators.v1",
        ),
        "orbit_catalog_sha256": _json_sha256(
            orbit_catalog,
            namespace="task035e.goal-oriented-face-orbits.v1",
        ),
        "orbit_catalog": orbit_catalog,
        "shared_edge_nonorthogonality_uses_global_gram": True,
        "ordinary_default_changed": False,
    }
    return PeriodicFaceQuotient(
        generators=generators,
        orbit_slices=tuple(orbit_slices),
        orbit_geometry_keys=tuple(orbit_keys),
        audit=MappingProxyType(audit),
    )


def decompose_face_residual(
    quotient: PeriodicFaceQuotient,
    residual_trace: Sequence[complex] | np.ndarray,
) -> FaceResidualPartition:
    """Project a p5-Galerkin residual into the full face quotient."""

    residual = np.asarray(residual_trace, dtype=np.complex128)
    generators = quotient.generators
    if residual.shape != (generators.shape[0],):
        raise ValueError("fine residual has the wrong trace dimension")
    gram = (generators.conj().T @ generators).tocsc()
    rhs = np.asarray(generators.conj().T @ residual)
    factor = splu(gram)
    coefficients = np.asarray(factor.solve(rhs))
    projection = np.asarray(generators @ coefficients)
    unexplained = np.ascontiguousarray(residual - projection)
    orbit_norms = np.empty(len(quotient.orbit_slices), dtype=np.float64)
    for index, (start, stop) in enumerate(quotient.orbit_slices):
        component = np.asarray(
            generators[:, start:stop] @ coefficients[start:stop]
        )
        orbit_norms[index] = float(np.linalg.norm(component))
    orthogonality = float(
        np.linalg.norm(
            np.asarray(generators.conj().T @ unexplained)
        )
    )
    audit = {
        "status": "face_residual_gram_partition_pass",
        "pass": bool(
            orthogonality
            <= 2.0e-9 * max(float(np.linalg.norm(residual)), 1.0)
        ),
        "residual_l2_norm": float(np.linalg.norm(residual)),
        "face_projection_l2_norm": float(np.linalg.norm(projection)),
        "unexplained_l2_norm": float(np.linalg.norm(unexplained)),
        "generator_orthogonality_error_l2": orthogonality,
        "face_orbit_count": len(quotient.orbit_slices),
        "signed_pairing_must_use_orbit_coefficients": True,
    }
    if not audit["pass"]:
        raise RuntimeError("face residual Gram projection did not close")
    return FaceResidualPartition(
        coefficients=coefficients,
        face_projection=projection,
        unexplained=unexplained,
        orbit_components_l2=orbit_norms,
        audit=MappingProxyType(audit),
    )


def signed_orbit_pairings(
    quotient: PeriodicFaceQuotient,
    partition: FaceResidualPartition,
    adjoint_trace: Sequence[complex] | np.ndarray,
) -> np.ndarray:
    """Return the complex signed DWR pairing for every face orbit."""

    adjoint = np.asarray(adjoint_trace, dtype=np.complex128)
    if adjoint.shape != (quotient.generators.shape[0],):
        raise ValueError("fine adjoint has the wrong trace dimension")
    dual_coordinates = np.asarray(
        quotient.generators.conj().T @ adjoint
    )
    result = np.empty(len(quotient.orbit_slices), dtype=np.complex128)
    for index, (start, stop) in enumerate(quotient.orbit_slices):
        result[index] = np.vdot(
            dual_coordinates[start:stop],
            partition.coefficients[start:stop],
        )
    return result


__all__ = [
    "FaceResidualPartition",
    "PeriodicFaceQuotient",
    "PhysicalRootInjection",
    "build_nested_trace_root_injection",
    "build_p5_to_global_p6_root_injection",
    "build_periodic_face_quotient",
    "decompose_face_residual",
    "signed_orbit_pairings",
]
