"""Physical-root transfer for a true p5-to-p6 whole-face enrichment.

The ordinary Task035d variable-p matrix numbers only independent physical
trace roots.  A selective-face experiment therefore cannot copy PETSc row
numbers from its p5 endpoint: adding one p6 face changes both the physical
row catalog and the independent-root numbering.  This module constructs the
explicit, geometry-bound injection

```
P : (p5 trace roots + DtN auxiliaries)
      -> (selected p6-face roots + DtN auxiliaries)
```

from the two flattened physical constraint graphs.  It never constructs a
hidden global-p6 Maxwell matrix.  A selected face is a whole, non-periodic
physical block; boundary edges may participate in hanging constraints, so
the complete physical closure is expanded to its independent master-root
support before the quotient is built.  Periodic selected-face orbits remain
outside this cross-trace DWR lane.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from scipy import sparse
from scipy.linalg import null_space

from .hcurl_broken_trace_graph import (
    BrokenHexTraceConstraintAuthority,
    PhysicalTraceEntity,
    physical_face_closure_rows,
)
from .selective_face_complement import (
    build_selective_p6_face_reference_complement,
)


_ROUND_OFF_LIMIT = 2.0e-10
_CONDITION_LIMIT = 1.0e8


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _csr_sha256(values: sparse.spmatrix) -> str:
    matrix = sparse.csr_matrix(values, dtype=np.complex128)
    digest = hashlib.sha256()
    digest.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
    digest.update(np.ascontiguousarray(matrix.indptr).view(np.uint8))
    digest.update(np.ascontiguousarray(matrix.indices).view(np.uint8))
    digest.update(np.ascontiguousarray(matrix.data).view(np.uint8))
    return digest.hexdigest()


def _maximum_sparse_absolute(values: sparse.spmatrix) -> float:
    matrix = sparse.csr_matrix(values)
    if matrix.nnz == 0:
        return 0.0
    return float(np.max(np.abs(matrix.data), initial=0.0))


def _authority_identity(
    authority: BrokenHexTraceConstraintAuthority,
) -> dict[str, Any]:
    """Return a content identity independent of a complement basis."""

    entity_catalog = [
        {
            "dimension": int(entity.dimension),
            "geometry_key": list(entity.geometry_key),
            "degree": int(entity.degree),
            "canonical_points": [
                list(point) for point in entity.canonical_points
            ],
            "mode_count": len(entity.rows),
        }
        for entity in authority.entities
    ]
    graph = sparse.csr_matrix(
        authority.graph.raw_from_independent,
        dtype=np.complex128,
    )
    declared = authority.audit.get("physical_authority_sha256")
    return {
        "declared_physical_authority_sha256": (
            None if declared is None else str(declared)
        ),
        "entity_catalog_sha256": _json_sha256(entity_catalog),
        "flattened_graph_sha256": _csr_sha256(graph),
        "raw_trace_rows": int(graph.shape[0]),
        "independent_trace_rows": int(graph.shape[1]),
    }


def _entity_offsets(
    authority: BrokenHexTraceConstraintAuthority,
) -> tuple[
    dict[tuple[int, tuple[int, ...]], tuple[PhysicalTraceEntity, int, int]],
    dict[Any, int],
]:
    """Return physical-entity raw slices and the graph raw-row index."""

    result: dict[
        tuple[int, tuple[int, ...]],
        tuple[PhysicalTraceEntity, int, int],
    ] = {}
    offset = 0
    for entity in authority.entities:
        stop = offset + len(entity.rows)
        if tuple(authority.graph.raw_rows[offset:stop]) != entity.rows:
            raise RuntimeError(
                "physical entity order differs from flattened raw-row order"
            )
        identity = (entity.dimension, entity.geometry_key)
        if identity in result:
            raise RuntimeError("physical trace authority repeats an entity")
        result[identity] = (entity, offset, stop)
        offset = stop
    if offset != len(authority.graph.raw_rows):
        raise RuntimeError("physical entity slices do not close raw rows")
    return result, {
        row: index for index, row in enumerate(authority.graph.raw_rows)
    }


def _canonicalize_complex_columns(values: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(values, dtype=np.complex128)
    for column in range(result.shape[1]):
        pivot = int(np.argmax(np.abs(result[:, column])))
        magnitude = abs(result[pivot, column])
        if magnitude:
            result[:, column] *= np.conj(
                result[pivot, column] / magnitude
            )
    return result


def _rank_revealing_statistics(values: np.ndarray) -> dict[str, Any]:
    matrix = np.asarray(values, dtype=np.complex128)
    singular_values = np.linalg.svd(
        matrix,
        compute_uv=False,
    )
    largest = float(singular_values[0]) if len(singular_values) else 0.0
    smallest = float(singular_values[-1]) if len(singular_values) else 0.0
    tolerance = float(
        64.0
        * np.finfo(np.float64).eps
        * max(matrix.shape, default=0)
        * largest
    )
    rank = int(np.count_nonzero(singular_values > tolerance))
    condition = (
        float("inf")
        if smallest == 0.0
        else float(largest / smallest)
    )
    return {
        "rank": rank,
        "rank_tolerance": tolerance,
        "largest_singular_value": largest,
        "smallest_singular_value": smallest,
        "condition_number": condition,
    }


@dataclass(frozen=True)
class SelectiveFaceRootTransfer:
    """Sparse primal injection, dual restriction, and exact complement."""

    trace_injection: sparse.csr_matrix
    total_injection: sparse.csr_matrix
    trace_complement: sparse.csr_matrix
    total_complement: sparse.csr_matrix
    trace_face_generators: sparse.csr_matrix
    total_face_generators: sparse.csr_matrix
    face_generator_slices: Mapping[
        tuple[int, ...],
        tuple[int, int],
    ]
    face_generator_gram_cholesky: np.ndarray
    audit: Mapping[str, Any]

    def prolong_primal(self, values: np.ndarray) -> np.ndarray:
        """Apply ``P`` to one coarse solver vector or a column block."""

        supplied = np.asarray(values, dtype=np.complex128)
        if supplied.shape[0] != self.total_injection.shape[1]:
            raise ValueError("coarse solver vector has the wrong dimension")
        return np.asarray(self.total_injection @ supplied)

    def restrict_dual(self, values: np.ndarray) -> np.ndarray:
        """Apply the Hermitian dual restriction ``P^H``."""

        supplied = np.asarray(values, dtype=np.complex128)
        if supplied.shape[0] != self.total_injection.shape[0]:
            raise ValueError("enriched solver vector has the wrong dimension")
        return np.asarray(self.total_injection.conj().T @ supplied)

    def complement_coordinates(self, values: np.ndarray) -> np.ndarray:
        """Return orthonormal solver-coordinate complement coefficients."""

        supplied = np.asarray(values, dtype=np.complex128)
        if supplied.shape[0] != self.total_complement.shape[0]:
            raise ValueError("enriched solver vector has the wrong dimension")
        return np.asarray(self.total_complement.conj().T @ supplied)

    def partition_pairing(
        self,
        dual: np.ndarray,
        primal: np.ndarray,
    ) -> Mapping[tuple[int, ...], complex]:
        """Partition one global pairing across selected physical faces.

        Each face owns one 20-dimensional quotient generator.  Shared-edge
        support makes those generators nonorthogonal, so the supplied primal
        is first decomposed through their full Gram matrix.  The resulting
        direct-sum face components close the signed global pairing exactly.
        """

        supplied_dual = np.asarray(dual, dtype=np.complex128)
        supplied_primal = np.asarray(primal, dtype=np.complex128)
        expected = self.total_complement.shape[0]
        if supplied_dual.shape != (expected,):
            raise ValueError("dual solver vector has the wrong dimension")
        if supplied_primal.shape != (expected,):
            raise ValueError("primal solver vector has the wrong dimension")
        generator_rhs = np.asarray(
            self.total_face_generators.conj().T @ supplied_primal
        )
        lower = np.asarray(self.face_generator_gram_cholesky)
        intermediate = np.linalg.solve(lower, generator_rhs)
        coefficients = np.linalg.solve(
            lower.conj().T,
            intermediate,
        )
        projected = np.asarray(
            self.total_face_generators @ coefficients
        )
        projection_error = float(
            np.linalg.norm(supplied_primal - projected)
        )
        projection_limit = float(
            _ROUND_OFF_LIMIT
            * max(np.linalg.norm(supplied_primal), 1.0)
        )
        if projection_error > projection_limit:
            raise ValueError(
                "primal vector is not in the selective complement"
            )
        result: dict[tuple[int, ...], complex] = {}
        for key, (start, stop) in self.face_generator_slices.items():
            component = np.asarray(
                self.total_face_generators[:, start:stop]
                @ coefficients[start:stop]
            )
            result[key] = complex(np.vdot(supplied_dual, component))
        return MappingProxyType(result)


def build_selective_face_root_transfer(
    coarse: BrokenHexTraceConstraintAuthority,
    enriched: BrokenHexTraceConstraintAuthority,
    *,
    auxiliary_rows: int,
) -> SelectiveFaceRootTransfer:
    """Build the fail-closed physical-root injection for one face set."""

    auxiliary_rows = int(auxiliary_rows)
    if auxiliary_rows < 0:
        raise ValueError("auxiliary row count must be nonnegative")
    if coarse.audit["pass"] is not True or enriched.audit["pass"] is not True:
        raise ValueError("both physical trace authorities must pass")
    if coarse.degree != 5 or enriched.degree != 5:
        raise ValueError("selective-face root transfer requires a p5 base")
    if coarse.selected_p6_face_geometry_keys:
        raise ValueError("coarse authority already contains selected p6 faces")
    selected = tuple(enriched.selected_p6_face_geometry_keys)
    if not selected:
        raise ValueError("enriched authority selects no p6 physical face")

    coarse_entities, coarse_row_index = _entity_offsets(coarse)
    enriched_entities, enriched_row_index = _entity_offsets(enriched)
    if set(coarse_entities) != set(enriched_entities):
        raise ValueError(
            "coarse and enriched physical entity geometry catalogs differ"
        )
    same_entity_order = tuple(
        (entity.dimension, entity.geometry_key)
        for entity in coarse.entities
    ) == tuple(
        (entity.dimension, entity.geometry_key)
        for entity in enriched.entities
    )
    same_canonical_geometry = all(
        coarse_entities[identity][0].canonical_points
        == enriched_entities[identity][0].canonical_points
        for identity in coarse_entities
    )
    if not same_entity_order or not same_canonical_geometry:
        raise ValueError(
            "coarse and enriched physical entity geometry ordering differs"
        )

    # Physical canonical face coefficients use the local-face-0 closure
    # ordering: four p5 edge blocks followed by the face-interior block.
    # The reference authority separately qualifies all six hexa embeddings
    # and all D4 actions.  It is essential to retain the full 80x60 closure
    # injection: its lower-left block maps the four coarse edge blocks into
    # the new p6 face moments.
    reference = build_selective_p6_face_reference_complement(0)
    coarse_closure_dofs = np.asarray(
        reference.coarse_space.hcurl_element.entity_closure_dofs[2][0],
        dtype=np.int64,
    )
    enriched_closure_dofs = np.asarray(
        reference.enriched_space.hcurl_element.entity_closure_dofs[2][0],
        dtype=np.int64,
    )
    reference_injection = np.asarray(
        reference.hcurl.injection,
        dtype=np.complex128,
    )
    closure_embedding = np.ascontiguousarray(
        reference_injection[
            np.ix_(enriched_closure_dofs, coarse_closure_dofs)
        ]
    )
    if closure_embedding.shape != (80, 60):
        raise RuntimeError(
            "qualified p5-to-p6 face-closure embedding changed shape"
        )
    closure_rank_statistics = _rank_revealing_statistics(
        closure_embedding
    )
    closure_rank = int(closure_rank_statistics["rank"])
    edge_identity_error = float(
        np.max(
            np.abs(
                closure_embedding[:20, :20]
                - np.eye(20, dtype=np.complex128)
            ),
            initial=0.0,
        )
    )
    edge_target_face_source_error = float(
        np.max(np.abs(closure_embedding[:20, 20:]), initial=0.0)
    )
    face_target_edge_source_max = float(
        np.max(np.abs(closure_embedding[20:, :20]), initial=0.0)
    )
    face_interior_block_error = float(
        np.max(
            np.abs(
                closure_embedding[20:, 20:]
                - reference.face_interior.p5_to_p6
            ),
            initial=0.0,
        )
    )
    outside_coarse_closure = np.setdiff1d(
        np.arange(reference_injection.shape[1], dtype=np.int64),
        coarse_closure_dofs,
        assume_unique=True,
    )
    outside_enriched_closure = np.setdiff1d(
        np.arange(reference_injection.shape[0], dtype=np.int64),
        enriched_closure_dofs,
        assume_unique=True,
    )
    closure_target_from_outside_source_max = float(
        np.max(
            np.abs(
                reference_injection[
                    np.ix_(
                        enriched_closure_dofs,
                        outside_coarse_closure,
                    )
                ]
            ),
            initial=0.0,
        )
    )
    outside_target_from_closure_source_max = float(
        np.max(
            np.abs(
                reference_injection[
                    np.ix_(
                        outside_enriched_closure,
                        coarse_closure_dofs,
                    )
                ]
            ),
            initial=0.0,
        )
    )
    if (
        closure_rank != 60
        or closure_rank_statistics["condition_number"]
        > _CONDITION_LIMIT
        or edge_identity_error > _ROUND_OFF_LIMIT
        or edge_target_face_source_error > _ROUND_OFF_LIMIT
        or face_target_edge_source_max <= 1.0e-12
        or face_interior_block_error > _ROUND_OFF_LIMIT
        or closure_target_from_outside_source_max > _ROUND_OFF_LIMIT
        or outside_target_from_closure_source_max > _ROUND_OFF_LIMIT
    ):
        raise RuntimeError(
            "qualified p5-to-p6 full face-closure embedding failed"
        )

    raw_rows_a = len(enriched.graph.raw_rows)
    raw_rows_b = len(coarse.graph.raw_rows)
    physical_injection = sparse.lil_matrix(
        (raw_rows_a, raw_rows_b),
        dtype=np.complex128,
    )
    changed_entities: list[dict[str, Any]] = []
    for identity in sorted(enriched_entities):
        entity_a, start_a, stop_a = enriched_entities[identity]
        entity_b, start_b, stop_b = coarse_entities[identity]
        if entity_a.degree == entity_b.degree:
            block = sparse.eye(
                stop_a - start_a,
                dtype=np.complex128,
                format="csr",
            )
            if block.shape != (stop_a - start_a, stop_b - start_b):
                raise RuntimeError(
                    "physical entity identity has a wrong shape"
                )
            physical_injection[start_a:stop_a, start_b:stop_b] = block
        elif not (
            entity_a.dimension == 2
            and entity_b.degree == 5
            and entity_a.degree == 6
            and entity_a.geometry_key in selected
        ):
            raise ValueError(
                "physical entity degree change is not the qualified "
                f"p5-to-p6 face action: {identity}"
            )

    coarse_entity_catalog = {
        identity: row[0] for identity, row in coarse_entities.items()
    }
    enriched_entity_catalog = {
        identity: row[0] for identity, row in enriched_entities.items()
    }
    selected_closure_rows: dict[
        tuple[int, ...],
        tuple[Any, ...],
    ] = {}
    for geometry_key in sorted(selected):
        entity_a, start_a, stop_a = enriched_entities[(2, geometry_key)]
        entity_b, _start_b, _stop_b = coarse_entities[(2, geometry_key)]
        closure_rows_a = physical_face_closure_rows(
            entity_a,
            enriched_entity_catalog,
        )
        closure_rows_b = physical_face_closure_rows(
            entity_b,
            coarse_entity_catalog,
        )
        if len(closure_rows_a) != 80 or len(closure_rows_b) != 60:
            raise RuntimeError(
                "selected physical face closure has a wrong dimension"
            )
        target_face_rows = np.asarray(
            [enriched_row_index[row] for row in closure_rows_a[20:]],
            dtype=np.int64,
        )
        source_closure_rows = np.asarray(
            [coarse_row_index[row] for row in closure_rows_b],
            dtype=np.int64,
        )
        if not np.array_equal(
            target_face_rows,
            np.arange(start_a, stop_a, dtype=np.int64),
        ):
            raise RuntimeError(
                "selected face-interior slice differs from its closure rows"
            )
        physical_injection[
            np.ix_(target_face_rows, source_closure_rows)
        ] = closure_embedding[20:, :]
        selected_closure_rows[geometry_key] = closure_rows_a
        changed_entities.append(
            {
                "dimension": 2,
                "geometry_key": list(entity_a.geometry_key),
                "coarse_degree": 5,
                "enriched_degree": 6,
                "coarse_modes": 40,
                "enriched_modes": 60,
            }
        )
    physical_injection = physical_injection.tocsr()

    coarse_expansion = sparse.csr_matrix(
        coarse.graph.raw_from_independent,
        dtype=np.complex128,
    )
    enriched_expansion = sparse.csr_matrix(
        enriched.graph.raw_from_independent,
        dtype=np.complex128,
    )
    target_raw = (physical_injection @ coarse_expansion).tocsr()
    root_indices_a = np.asarray(
        [enriched_row_index[row] for row in enriched.graph.root_rows],
        dtype=np.int64,
    )
    trace_injection = target_raw[root_indices_a].tocsr()
    trace_injection.eliminate_zeros()
    graph_closure = (
        enriched_expansion @ trace_injection - target_raw
    ).tocsr()
    graph_closure.eliminate_zeros()
    graph_closure_error = _maximum_sparse_absolute(graph_closure)

    selected_root_positions: dict[tuple[int, ...], np.ndarray] = {}
    selected_support_catalog: dict[str, Any] = {}
    enriched_root_rows = set(enriched.graph.root_rows)
    for geometry_key in sorted(selected):
        closure_rows = selected_closure_rows[geometry_key]
        raw_positions = np.asarray(
            [enriched_row_index[row] for row in closure_rows],
            dtype=np.int64,
        )
        closure_from_roots = enriched_expansion[raw_positions].tocsr()
        positions = np.unique(closure_from_roots.indices).astype(
            np.int64,
            copy=False,
        )
        if len(positions) == 0:
            raise RuntimeError(
                "selected physical face closure has no independent roots"
            )
        selected_root_positions[geometry_key] = positions
        selected_support_catalog[str(geometry_key)] = {
            "geometry_key": list(geometry_key),
            "physical_closure_rows": len(closure_rows),
            "independent_root_support_rows": len(positions),
            "constrained_physical_closure_rows": sum(
                row not in enriched_root_rows
                for row in closure_rows
            ),
        }

    affected_positions = np.asarray(
        sorted(
            {
                int(position)
                for positions in selected_root_positions.values()
                for position in positions
            }
        ),
        dtype=np.int64,
    )
    affected_sparse = trace_injection[affected_positions].tocsr()
    affected_significant = np.abs(affected_sparse.data) > 1.0e-14
    coarse_columns = np.unique(
        affected_sparse.indices[affected_significant]
    ).astype(
        np.int64,
        copy=False,
    )
    patch_injection = affected_sparse[:, coarse_columns].toarray()
    patch_rank_statistics = _rank_revealing_statistics(patch_injection)
    patch_rank = int(patch_rank_statistics["rank"])
    reference_face_generator = _canonicalize_complex_columns(
        null_space(
            closure_embedding.conj().T,
            rcond=1.0e-12,
        )
    )
    reference_face_generator_rank = int(
        _rank_revealing_statistics(
            reference_face_generator[20:, :]
        )["rank"]
    )
    expected_delta = 20 * len(selected)
    if (
        patch_rank != patch_injection.shape[1]
        or patch_rank_statistics["condition_number"] > _CONDITION_LIMIT
        or reference_face_generator.shape != (80, 20)
        or reference_face_generator_rank != 20
    ):
        raise RuntimeError(
            "selected face-closure generator has a wrong rank"
        )
    generator_blocks: list[sparse.csr_matrix] = []
    face_generator_slices: dict[
        tuple[int, ...],
        tuple[int, int],
    ] = {}
    generator_offset = 0
    for geometry_key, positions in sorted(
        selected_root_positions.items()
    ):
        local_sparse = trace_injection[positions].tocsr()
        local_significant = np.abs(local_sparse.data) > 1.0e-14
        local_coarse_columns = np.unique(
            local_sparse.indices[local_significant]
        ).astype(
            np.int64,
            copy=False,
        )
        local_injection = local_sparse[
            :,
            local_coarse_columns,
        ].toarray()
        local_generator = _canonicalize_complex_columns(
            null_space(
                local_injection.conj().T,
                rcond=1.0e-12,
            )
        )
        local_rank_statistics = _rank_revealing_statistics(
            local_injection
        )
        local_rank = int(local_rank_statistics["rank"])
        if (
            local_rank != local_injection.shape[1]
            or local_rank_statistics["condition_number"]
            > _CONDITION_LIMIT
            or local_generator.shape != (len(positions), 20)
        ):
            raise RuntimeError(
                "one graph-expanded physical face quotient is not "
                "20-dimensional"
            )
        selected_support_catalog[str(geometry_key)].update(
            {
                "coarse_root_support_columns": len(
                    local_coarse_columns
                ),
                "local_injection_rank": local_rank,
                "local_rank_tolerance": local_rank_statistics[
                    "rank_tolerance"
                ],
                "local_smallest_singular_value": local_rank_statistics[
                    "smallest_singular_value"
                ],
                "local_condition_number": local_rank_statistics[
                    "condition_number"
                ],
                "local_complement_dimension": local_generator.shape[1],
            }
        )
        block = sparse.lil_matrix(
            (trace_injection.shape[0], 20),
            dtype=np.complex128,
        )
        block[positions, :] = local_generator
        generator_blocks.append(block.tocsr())
        face_generator_slices[geometry_key] = (
            generator_offset,
            generator_offset + 20,
        )
        generator_offset += 20
    trace_face_generators = sparse.hstack(
        generator_blocks,
        format="csr",
    )
    patch_generators = trace_face_generators[
        affected_positions
    ].toarray()
    generator_rank_statistics = _rank_revealing_statistics(
        patch_generators
    )
    generator_rank = int(generator_rank_statistics["rank"])
    if (
        generator_rank != expected_delta
        or generator_rank_statistics["condition_number"]
        > _CONDITION_LIMIT
    ):
        raise RuntimeError(
            "graph-expanded face generators are rank deficient or "
            "ill-conditioned"
        )
    generator_gram = np.ascontiguousarray(
        patch_generators.conj().T @ patch_generators
    )
    generator_gram_condition = float(np.linalg.cond(generator_gram))
    generator_gram_cholesky = np.ascontiguousarray(
        np.linalg.cholesky(generator_gram)
    )
    inverse_upper = np.linalg.solve(
        generator_gram_cholesky.conj().T,
        np.eye(expected_delta, dtype=np.complex128),
    )
    patch_complement = np.ascontiguousarray(
        patch_generators @ inverse_upper
    )
    trace_complement_lil = sparse.lil_matrix(
        (trace_injection.shape[0], expected_delta),
        dtype=np.complex128,
    )
    trace_complement_lil[affected_positions, :] = patch_complement
    trace_complement = trace_complement_lil.tocsr()
    face_generator_slice_payload = {
        str(key): [int(start), int(stop)]
        for key, (start, stop) in sorted(
            face_generator_slices.items()
        )
    }
    generator_gram_cholesky.setflags(write=False)

    total_injection = sparse.block_diag(
        (
            trace_injection,
            sparse.eye(
                auxiliary_rows,
                dtype=np.complex128,
                format="csr",
            ),
        ),
        format="csr",
    )
    total_complement = sparse.vstack(
        (
            trace_complement,
            sparse.csr_matrix(
                (auxiliary_rows, trace_complement.shape[1]),
                dtype=np.complex128,
            ),
        ),
        format="csr",
    )
    total_face_generators = sparse.vstack(
        (
            trace_face_generators,
            sparse.csr_matrix(
                (auxiliary_rows, trace_face_generators.shape[1]),
                dtype=np.complex128,
            ),
        ),
        format="csr",
    )

    complement_cross_error = _maximum_sparse_absolute(
        trace_injection.conj().T @ trace_complement
    )
    complement_gram_error = _maximum_sparse_absolute(
        trace_complement.conj().T @ trace_complement
        - sparse.eye(
            trace_complement.shape[1],
            dtype=np.complex128,
            format="csr",
        )
    )
    complement_projector = (
        trace_complement @ trace_complement.conj().T
    ).tocsr()
    generator_cross_error = _maximum_sparse_absolute(
        trace_injection.conj().T @ trace_face_generators
    )
    generator_projector = patch_generators @ np.linalg.solve(
        generator_gram,
        patch_generators.conj().T,
    )
    orthonormal_projector = (
        patch_complement @ patch_complement.conj().T
    )
    generator_projector_error = float(
        np.max(
            np.abs(generator_projector - orthonormal_projector),
            initial=0.0,
        )
    )
    checks = {
        "same_physical_entity_geometry_catalog": (
            same_entity_order and same_canonical_geometry
        ),
        "only_selected_whole_faces_change_degree": (
            len(changed_entities) == len(selected)
        ),
        "full_face_closure_embedding_is_nested": (
            closure_rank == 60
            and closure_rank_statistics["condition_number"]
            <= _CONDITION_LIMIT
            and edge_identity_error <= _ROUND_OFF_LIMIT
            and edge_target_face_source_error <= _ROUND_OFF_LIMIT
            and face_interior_block_error <= _ROUND_OFF_LIMIT
            and reference_face_generator_rank == 20
        ),
        "edge_to_face_coupling_is_present": (
            face_target_edge_source_max > 1.0e-12
        ),
        "reference_face_closure_has_no_outside_coupling": (
            closure_target_from_outside_source_max <= _ROUND_OFF_LIMIT
            and outside_target_from_closure_source_max
            <= _ROUND_OFF_LIMIT
        ),
        "physical_constraint_graph_injection_closes": (
            graph_closure_error <= _ROUND_OFF_LIMIT
        ),
        "selected_patch_injection_is_full_rank": (
            patch_rank == patch_injection.shape[1]
            and patch_rank_statistics["condition_number"]
            <= _CONDITION_LIMIT
        ),
        "each_graph_expanded_face_has_20_quotient_modes": all(
            row.get("local_complement_dimension") == 20
            and row.get("local_condition_number", float("inf"))
            <= _CONDITION_LIMIT
            for row in selected_support_catalog.values()
        ),
        "face_generators_form_direct_sum": (
            generator_rank == expected_delta
            and generator_rank_statistics["condition_number"]
            <= _CONDITION_LIMIT
        ),
        "face_generators_are_global_complement": (
            generator_cross_error <= _ROUND_OFF_LIMIT
        ),
        "generator_and_orthonormal_projectors_agree": (
            generator_projector_error <= _ROUND_OFF_LIMIT
        ),
        "face_generator_gram_is_well_conditioned": (
            np.isfinite(generator_gram_condition)
            and generator_gram_condition <= 1.0e8
        ),
        "root_dimension_delta_is_20_per_selected_face": (
            trace_injection.shape[0] - trace_injection.shape[1]
            == expected_delta
        ),
        "complement_dimension_is_20_per_selected_face": (
            trace_complement.shape[1] == expected_delta
        ),
        "complement_is_solver_coordinate_orthogonal": (
            complement_cross_error <= _ROUND_OFF_LIMIT
        ),
        "complement_is_solver_coordinate_orthonormal": (
            complement_gram_error <= _ROUND_OFF_LIMIT
        ),
        "auxiliary_coordinates_are_identity": True,
        "no_hidden_global_p6_matrix": True,
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "selective-face physical-root transfer failed: "
            + ", ".join(failures)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035d.selective-face-physical-root-transfer.v2"
            ),
            "status": "selective_face_physical_root_transfer_pass",
            "pass": True,
            "coarse_raw_trace_rows": raw_rows_b,
            "coarse_independent_trace_rows": (
                trace_injection.shape[1]
            ),
            "enriched_raw_trace_rows": raw_rows_a,
            "enriched_independent_trace_rows": (
                trace_injection.shape[0]
            ),
            "auxiliary_rows": auxiliary_rows,
            "selected_p6_face_count": len(selected),
            "selected_p6_face_geometry_keys": [
                list(key) for key in sorted(selected)
            ],
            "coarse_input_identity": _authority_identity(coarse),
            "enriched_input_identity": _authority_identity(enriched),
            "changed_entities": changed_entities,
            "trace_dimension_delta": expected_delta,
            "reference_face_closure_shape": list(
                closure_embedding.shape
            ),
            "reference_face_closure_rank": closure_rank,
            "reference_face_closure_rank_tolerance": (
                closure_rank_statistics["rank_tolerance"]
            ),
            "reference_face_closure_smallest_singular_value": (
                closure_rank_statistics["smallest_singular_value"]
            ),
            "reference_face_closure_condition_number": (
                closure_rank_statistics["condition_number"]
            ),
            "reference_face_closure_injection_sha256": _csr_sha256(
                sparse.csr_matrix(closure_embedding)
            ),
            "reference_edge_identity_error_max": edge_identity_error,
            "reference_edge_target_face_source_error_max": (
                edge_target_face_source_error
            ),
            "reference_face_target_edge_source_max": (
                face_target_edge_source_max
            ),
            "reference_face_interior_block_error_max": (
                face_interior_block_error
            ),
            "reference_face_generator_face_block_rank": (
                reference_face_generator_rank
            ),
            "reference_closure_target_from_outside_source_max": (
                closure_target_from_outside_source_max
            ),
            "reference_outside_target_from_closure_source_max": (
                outside_target_from_closure_source_max
            ),
            "affected_root_row_count": len(affected_positions),
            "affected_coarse_column_count": len(coarse_columns),
            "dense_patch_shape": list(patch_injection.shape),
            "full_width_dense_transfer_materialized": False,
            "selected_patch_injection_rank": patch_rank,
            "selected_patch_rank_tolerance": (
                patch_rank_statistics["rank_tolerance"]
            ),
            "selected_patch_smallest_singular_value": (
                patch_rank_statistics["smallest_singular_value"]
            ),
            "selected_patch_condition_number": (
                patch_rank_statistics["condition_number"]
            ),
            "selected_face_root_support_catalog": (
                [
                    selected_support_catalog[str(key)]
                    for key in sorted(selected)
                ]
            ),
            "selected_face_root_support_catalog_sha256": _json_sha256(
                [
                    selected_support_catalog[str(key)]
                    for key in sorted(selected)
                ]
            ),
            "face_generator_rank": generator_rank,
            "face_generator_rank_tolerance": (
                generator_rank_statistics["rank_tolerance"]
            ),
            "face_generator_smallest_singular_value": (
                generator_rank_statistics["smallest_singular_value"]
            ),
            "face_generator_condition_number": (
                generator_rank_statistics["condition_number"]
            ),
            "face_generator_gram_condition_number": (
                generator_gram_condition
            ),
            "face_generator_global_cross_error_max": (
                generator_cross_error
            ),
            "face_generator_projector_error_max": (
                generator_projector_error
            ),
            "face_generator_slices_sha256": _json_sha256(
                face_generator_slice_payload
            ),
            "face_generator_gram_sha256": _csr_sha256(
                sparse.csr_matrix(generator_gram)
            ),
            "graph_injection_closure_error_max": graph_closure_error,
            "complement_cross_error_max": complement_cross_error,
            "complement_gram_error_max": complement_gram_error,
            "physical_injection_sha256": _csr_sha256(
                physical_injection
            ),
            "trace_injection_sha256": _csr_sha256(trace_injection),
            "total_injection_sha256": _csr_sha256(total_injection),
            "trace_complement_projector_sha256": _csr_sha256(
                complement_projector
            ),
            "complement_basis_sha256_noncanonical": _csr_sha256(
                trace_complement
            ),
            "complement_basis_is_identity_authority": False,
            "selected_root_positions_sha256": _json_sha256(
                {
                    str(key): positions.tolist()
                    for key, positions in sorted(
                        selected_root_positions.items()
                    )
                }
            ),
            "checks": checks,
            "cross_trace_dwr_scope": (
                "whole non-periodic physical p6 faces with "
                "graph-expanded closure-root support"
            ),
            "periodic_selected_face_backend_supported_but_dwr_v2": False,
            "physical_closure_rows_assumed_independent_roots": False,
            "signed_face_attribution": (
                "direct_sum_face_generators_with_full_gram_decomposition"
            ),
            "ordinary_default_changed": False,
        }
    )
    return SelectiveFaceRootTransfer(
        trace_injection=trace_injection,
        total_injection=total_injection,
        trace_complement=trace_complement,
        total_complement=total_complement,
        trace_face_generators=trace_face_generators,
        total_face_generators=total_face_generators,
        face_generator_slices=MappingProxyType(
            dict(face_generator_slices)
        ),
        face_generator_gram_cholesky=generator_gram_cholesky,
        audit=audit,
    )


__all__ = [
    "SelectiveFaceRootTransfer",
    "build_selective_face_root_transfer",
]
