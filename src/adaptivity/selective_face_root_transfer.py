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
hidden global-p6 Maxwell matrix.  The selected faces must be whole,
non-hanging, non-periodic root blocks for this first cross-trace DWR lane;
the production trace backend remains more general and can still close a
complete periodic orbit.
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
)
from .selective_face_complement import (
    build_selective_p6_face_reference_complement,
)


_ROUND_OFF_LIMIT = 2.0e-10


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


@dataclass(frozen=True)
class SelectiveFaceRootTransfer:
    """Sparse primal injection, dual restriction, and exact complement."""

    trace_injection: sparse.csr_matrix
    total_injection: sparse.csr_matrix
    trace_complement: sparse.csr_matrix
    total_complement: sparse.csr_matrix
    complement_slices: Mapping[tuple[int, ...], tuple[int, int]]
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

    coarse_entities, _coarse_row_index = _entity_offsets(coarse)
    enriched_entities, enriched_row_index = _entity_offsets(enriched)
    if set(coarse_entities) != set(enriched_entities):
        raise ValueError(
            "coarse and enriched physical entity geometry catalogs differ"
        )

    # Physical canonical face coefficients use the same quadrilateral basis
    # on every hexa face.  local_face=0 is a canonical source; the component
    # authority separately qualifies all six hexa embeddings and all D4
    # actions.
    reference = build_selective_p6_face_reference_complement(0)
    face_embedding = sparse.csr_matrix(
        reference.face_interior.p5_to_p6,
        dtype=np.complex128,
    )
    if face_embedding.shape != (60, 40):
        raise RuntimeError("qualified p5-to-p6 face embedding changed shape")

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
        elif (
            entity_a.dimension == 2
            and entity_b.degree == 5
            and entity_a.degree == 6
            and entity_a.geometry_key in selected
        ):
            block = face_embedding
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
        else:
            raise ValueError(
                "physical entity degree change is not the qualified "
                f"p5-to-p6 face action: {identity}"
            )
        if block.shape != (stop_a - start_a, stop_b - start_b):
            raise RuntimeError("physical entity injection has a wrong shape")
        physical_injection[start_a:stop_a, start_b:stop_b] = block
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
    graph_closure = (
        enriched_expansion @ trace_injection - target_raw
    ).tocsr()
    graph_closure.eliminate_zeros()
    graph_closure_error = _maximum_sparse_absolute(graph_closure)

    selected_root_positions: dict[tuple[int, ...], np.ndarray] = {}
    root_position = {
        row: index for index, row in enumerate(enriched.graph.root_rows)
    }
    complement_blocks: list[sparse.csr_matrix] = []
    complement_slices: dict[tuple[int, ...], tuple[int, int]] = {}
    complement_offset = 0
    for geometry_key in sorted(selected):
        entity, _start, _stop = enriched_entities[(2, geometry_key)]
        if any(row not in root_position for row in entity.rows):
            raise ValueError(
                "cross-trace DWR v1 requires every selected face mode to "
                "be an unconstrained physical root; periodic/hanging "
                f"participant observed for {geometry_key}"
            )
        positions = np.asarray(
            [root_position[row] for row in entity.rows],
            dtype=np.int64,
        )
        selected_root_positions[geometry_key] = positions
        coarse_columns = np.flatnonzero(
            np.max(
                np.abs(
                    trace_injection[positions].toarray()
                ),
                axis=0,
            )
            > 1.0e-14
        )
        local_injection = trace_injection[
            positions
        ][:, coarse_columns].toarray()
        if local_injection.shape != (60, 40):
            raise RuntimeError(
                "selected unconstrained face does not expose one 60x40 "
                "physical-root injection"
            )
        local_complement = _canonicalize_complex_columns(
            null_space(
                local_injection.conj().T,
                rcond=1.0e-12,
            )
        )
        if local_complement.shape != (60, 20):
            raise RuntimeError(
                "selected face root complement does not have 20 modes"
            )
        block = sparse.lil_matrix(
            (trace_injection.shape[0], 20),
            dtype=np.complex128,
        )
        block[positions, :] = local_complement
        complement_blocks.append(block.tocsr())
        complement_slices[geometry_key] = (
            complement_offset,
            complement_offset + 20,
        )
        complement_offset += 20
    trace_complement = sparse.hstack(
        complement_blocks,
        format="csr",
    )

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
    expected_delta = 20 * len(selected)
    checks = {
        "same_physical_entity_geometry_catalog": True,
        "only_selected_whole_faces_change_degree": (
            len(changed_entities) == len(selected)
        ),
        "physical_constraint_graph_injection_closes": (
            graph_closure_error <= _ROUND_OFF_LIMIT
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
                "task035d.selective-face-physical-root-transfer.v1"
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
                "whole non-hanging non-periodic physical p6 face roots"
            ),
            "periodic_selected_face_backend_supported_but_dwr_v1": False,
            "ordinary_default_changed": False,
        }
    )
    return SelectiveFaceRootTransfer(
        trace_injection=trace_injection,
        total_injection=total_injection,
        trace_complement=trace_complement,
        total_complement=total_complement,
        complement_slices=MappingProxyType(dict(complement_slices)),
        audit=audit,
    )


__all__ = [
    "SelectiveFaceRootTransfer",
    "build_selective_face_root_transfer",
]
