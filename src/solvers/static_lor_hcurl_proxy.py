"""Direct lowest-order shifted Maxwell proxy on an affine LOR edge space.

This research-only proxy assembles the physical lowest-order child-cell
operator directly.  It is not the p-high parent Galerkin matrix, a smoother,
or a coercivity claim.  Only the final shifted active-edge CSR is retained.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from time import perf_counter
from types import MappingProxyType
from typing import Iterable

import basix
import numpy as np
import scipy.sparse as sp

from .hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from .static_lor_hcurl_transfer import (
    AffineLORParentTopology,
    LORSlabEdgeSpace,
)


_SHIFT_FRACTION = 0.1
_SHIFT_FLOOR_RELATIVE = 1.0e-12
_AXIS_ALIGNED_TOLERANCE = 1.0e-12
_HEX_LOCAL_EDGE_COUNT = 12


def _readonly_csr(values: sp.spmatrix) -> sp.csr_matrix:
    matrix = sp.csr_matrix(values, dtype=np.complex128, copy=True)
    matrix.sum_duplicates()
    matrix.sort_indices()
    matrix.eliminate_zeros()
    for array in (matrix.data, matrix.indices, matrix.indptr):
        array.setflags(write=False)
    return matrix


def _csr_payload_bytes(matrix: sp.csr_matrix) -> int:
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def _csr_fingerprint(matrix: sp.csr_matrix) -> str:
    digest = hashlib.sha256()
    digest.update(b"task037-extra.shifted-lor-csr.v1")
    digest.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
    for array in (matrix.indptr, matrix.indices, matrix.data):
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _array_hash(domain: str, values: np.ndarray) -> str:
    digest = hashlib.sha256(domain.encode("ascii"))
    array = np.ascontiguousarray(np.asarray(values, dtype=np.complex128))
    digest.update(np.asarray(array.shape, dtype=np.int64).tobytes())
    digest.update(array.tobytes())
    return digest.hexdigest()


def _child_widths(
    topology: AffineLORParentTopology,
    cell_index: int,
) -> tuple[float, float, float]:
    points = topology.vertices[topology.cells[cell_index]]
    lower = np.min(points, axis=0)
    upper = np.max(points, axis=0)
    widths = upper - lower
    if np.any(~np.isfinite(widths)) or np.any(widths <= 0.0):
        raise ValueError("LOR child must have positive finite widths")
    distance_to_axis_box = np.minimum(
        np.abs(points - lower),
        np.abs(points - upper),
    )
    if np.any(distance_to_axis_box > _AXIS_ALIGNED_TOLERANCE):
        raise NotImplementedError(
            "shifted LOR proxy supports axis-aligned affine children only"
        )
    return tuple(float(value) for value in widths)


def _child_active_stencil(
    topology: AffineLORParentTopology,
    edge_expansion: sp.csr_matrix,
    cell_index: int,
) -> tuple[np.ndarray, np.ndarray]:
    columns = np.empty(_HEX_LOCAL_EDGE_COUNT, dtype=np.int64)
    coefficients = np.empty(_HEX_LOCAL_EDGE_COUNT, dtype=np.complex128)
    for local_edge, (edge_id_value, orientation_value) in enumerate(
        zip(
            topology.cell_edge_ids[cell_index],
            topology.cell_edge_orientations[cell_index],
            strict=True,
        )
    ):
        edge_id = int(edge_id_value)
        start = int(edge_expansion.indptr[edge_id])
        end = int(edge_expansion.indptr[edge_id + 1])
        if end - start != 1:
            raise RuntimeError("each LOR parent edge expansion row must have one entry")
        columns[local_edge] = int(edge_expansion.indices[start])
        coefficients[local_edge] = (
            complex(edge_expansion.data[start]) * int(orientation_value)
        )
    return columns, coefficients


@dataclass(frozen=True)
class LORShiftedProxy:
    """Read-only shifted active-edge matrix and one-action interface."""

    _matrix: sp.csr_matrix
    audit: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_matrix", _readonly_csr(self._matrix))
        object.__setattr__(
            self,
            "audit",
            MappingProxyType(dict(self.audit)),
        )

    @property
    def matrix(self) -> sp.csr_matrix:
        return self._matrix

    def apply(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self._matrix.shape[1],):
            raise ValueError("active LOR values have the wrong edge count")
        return np.asarray(self._matrix @ vector, dtype=np.complex128)


def build_shifted_lor_proxy(
    parent_topologies: Iterable[AffineLORParentTopology],
    edge_space: LORSlabEdgeSpace,
    spec: AffineIsotropicMaxwellTensorSpec,
) -> LORShiftedProxy:
    """Build the direct child-cell shifted active-edge Maxwell proxy."""

    started = perf_counter()
    topologies = tuple(
        sorted(parent_topologies, key=lambda topology: topology.canonical_cell_id)
    )
    if not topologies:
        raise ValueError("at least one LOR parent topology is required")
    parent_ids = tuple(int(topology.canonical_cell_id) for topology in topologies)
    if parent_ids != tuple(edge_space.parent_ids):
        raise ValueError("parent topology order does not match the LOR edge space")
    degrees = {int(topology.degree) for topology in topologies}
    if len(degrees) != 1:
        raise ValueError("all LOR parents must use one refinement degree")

    element = basix.ufl.element(
        "N1curl",
        "hexahedron",
        1,
    ).basix_element
    if int(element.dim) != _HEX_LOCAL_EDGE_COUNT:
        raise RuntimeError("lowest-order hexahedron must have 12 edge DoFs")
    factory = AffineIsotropicMaxwellTensorFactory(element, spec)
    child_count = sum(len(topology.cells) for topology in topologies)
    triplet_count = child_count * _HEX_LOCAL_EDGE_COUNT**2
    row_indices = np.empty(triplet_count, dtype=np.int64)
    column_indices = np.empty(triplet_count, dtype=np.int64)
    values = np.empty(triplet_count, dtype=np.complex128)
    tensor_cache: dict[tuple[int, tuple[float, float, float]], np.ndarray] = {}
    cursor = 0
    for parent_index, topology in enumerate(topologies):
        edge_expansion = edge_space._parent_expansions[parent_index]
        tag = int(topology.material_tag)
        for cell_index in range(len(topology.cells)):
            widths = _child_widths(topology, cell_index)
            cache_key = (tag, widths)
            tensor = tensor_cache.get(cache_key)
            if tensor is None:
                tensor = factory.tensor(tag=tag, widths=widths)
                tensor_cache[cache_key] = tensor
            columns, coefficients = _child_active_stencil(
                topology,
                edge_expansion,
                cell_index,
            )
            for local_row in range(_HEX_LOCAL_EDGE_COUNT):
                for local_column in range(_HEX_LOCAL_EDGE_COUNT):
                    row_indices[cursor] = columns[local_row]
                    column_indices[cursor] = columns[local_column]
                    values[cursor] = (
                        np.conjugate(coefficients[local_row])
                        * tensor[local_row, local_column]
                        * coefficients[local_column]
                    )
                    cursor += 1
    base_matrix = sp.csr_matrix(
        (
            values,
            (row_indices, column_indices),
        ),
        shape=(len(edge_space.active_edge_keys),) * 2,
    )
    del row_indices, column_indices, values
    base_matrix.sum_duplicates()
    base_matrix.sort_indices()
    base_matrix.eliminate_zeros()
    if not np.all(np.isfinite(base_matrix.data)):
        raise RuntimeError("LOR proxy base matrix is not finite")
    base_nnz = int(base_matrix.nnz)
    base_diagonal = np.asarray(base_matrix.diagonal(), dtype=np.complex128)
    scale = float(np.max(np.abs(base_diagonal)))
    floor = _SHIFT_FLOOR_RELATIVE * scale
    shift = -1j * _SHIFT_FRACTION * np.maximum(np.abs(base_diagonal), floor)
    base_fingerprint = _csr_fingerprint(base_matrix)
    base_diagonal_hash = _array_hash(
        "task037-extra.shifted-lor-base-diagonal.v1",
        base_diagonal,
    )
    shift_hash = _array_hash(
        "task037-extra.shifted-lor-diagonal-shift.v1",
        shift,
    )
    base_matrix.setdiag(base_diagonal + shift)
    base_matrix.sum_duplicates()
    base_matrix.sort_indices()
    base_matrix.eliminate_zeros()
    audit = {
        "definition": "direct lowest-order child-cell Hcurl Maxwell proxy",
        "parent_ids": list(parent_ids),
        "parent_count": len(topologies),
        "degree": int(next(iter(degrees))),
        "local_element_degree": 1,
        "child_count": child_count,
        "unique_tensor_count": len(tensor_cache),
        "triplet_entry_count": triplet_count,
        "rows": int(base_matrix.shape[0]),
        "nnz": int(base_matrix.nnz),
        "csr_payload_bytes": _csr_payload_bytes(base_matrix),
        "base_nnz": base_nnz,
        "base_matrix_fingerprint": base_fingerprint,
        "matrix_fingerprint": _csr_fingerprint(base_matrix),
        "base_diagonal_finite": bool(np.all(np.isfinite(base_diagonal))),
        "base_diagonal_norm2": float(np.linalg.norm(base_diagonal)),
        "base_diagonal_abs_min": float(np.min(np.abs(base_diagonal))),
        "base_diagonal_abs_max": float(np.max(np.abs(base_diagonal))),
        "base_diagonal_sha256": base_diagonal_hash,
        "shift_finite": bool(np.all(np.isfinite(shift))),
        "shift_norm2": float(np.linalg.norm(shift)),
        "shift_abs_min": float(np.min(np.abs(shift))),
        "shift_abs_max": float(np.max(np.abs(shift))),
        "shift_sha256": shift_hash,
        "shift_fraction": _SHIFT_FRACTION,
        "shift_floor_relative": _SHIFT_FLOOR_RELATIVE,
        "shift_floor_abs": floor,
        "shift_rule": "diag += -1j*0.1*max(abs(diag),1e-12*max_abs_diag)",
        "direct_child_cell": True,
        "literal_p6_galerkin": False,
        "factor_count": 0,
        "global_dense": False,
        "global_A": False,
        "global_F": False,
        "build_seconds": float(perf_counter() - started),
    }
    return LORShiftedProxy(base_matrix, audit)


__all__ = (
    "LORShiftedProxy",
    "build_shifted_lor_proxy",
)
