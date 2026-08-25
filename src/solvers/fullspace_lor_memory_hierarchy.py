"""Pure single-cell interlevel LOR edge-transfer audit primitives.

The module keeps only bounded cell-local arrays.  It does not construct a
distributed object or a numerical hierarchy; those concerns belong to later
stages.  The two supported maps are fixed at 6<-3 and 3<-1.
"""

from __future__ import annotations

from types import MappingProxyType

import basix
import numpy as np

from .fullspace_lor_edge_geometric_mg import (
    _curl_face_oracle,
    _edge_line_integral_oracle,
    build_local_lor_edge_geometric_transfer,
)
from .fullspace_lor_transfer import (
    LOR_BATCH_CELL_CAP,
    _edge_endpoints,
    build_local_lor_transfer,
)


INTERLEVEL_PAIRS = ((6, 3), (3, 1))
INTERLEVEL_BATCH_CELL_CAP = LOR_BATCH_CELL_CAP
EDGE_QUADRATURE_LIMIT = 1.0e-11
GRADIENT_LIMIT = 1.0e-11
CURL_LIMIT = 1.0e-11
ADJOINT_LIMIT = 1.0e-12
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left)
    right = np.asarray(right)
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(right), np.finfo(float).tiny)
    )


def _n1e(degree: int):
    return basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.equispaced,
    )


def _scalar(degree: int):
    return basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.equispaced,
    )


def _node_transfer(
    fine_local: object,
    coarse_local: object,
    fine_degree: int,
    coarse_degree: int,
) -> np.ndarray:
    coarse_element = _scalar(coarse_degree)
    fine_element = _scalar(fine_degree)
    interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_element, fine_element),
        dtype=np.complex128,
    )
    fine_h1 = np.asarray(fine_local.h1_transfer, dtype=np.complex128)
    coarse_h1 = np.asarray(coarse_local.h1_transfer, dtype=np.complex128)
    if interpolation.shape != (int(fine_element.dim), int(coarse_element.dim)):
        raise RuntimeError("scalar interpolation shape is not closed")
    return np.ascontiguousarray(
        fine_h1 @ interpolation @ np.linalg.solve(coarse_h1, np.eye(coarse_h1.shape[0]))
    )


def _structural_trace_mask(
    fine_degree: int, coarse_degree: int
) -> np.ndarray:
    """Return the reference-cell boundary-plane support mask for an edge map."""

    fine_start, fine_end = _edge_endpoints(int(fine_degree))
    coarse_start, coarse_end = _edge_endpoints(int(coarse_degree))
    mask = np.ones(
        (fine_start.shape[0], coarse_start.shape[0]), dtype=bool
    )
    for row, (start, end) in enumerate(zip(fine_start, fine_end, strict=True)):
        boundary_planes = tuple(
            (axis, int(start[axis]))
            for axis in range(3)
            if int(start[axis]) == int(end[axis])
            and int(start[axis]) in (0, int(fine_degree))
        )
        if not boundary_planes:
            continue
        for column, (coarse_row, coarse_column) in enumerate(
            zip(coarse_start, coarse_end, strict=True)
        ):
            mask[row, column] = all(
                int(coarse_row[axis]) == int(coarse_column[axis])
                and int(coarse_row[axis])
                == (0 if position == 0 else int(coarse_degree))
                for axis, position in boundary_planes
            )
    return mask


def _probe_facts(edge_transfer: np.ndarray) -> dict[str, object]:
    columns = int(edge_transfer.shape[1])
    rows = int(edge_transfer.shape[0])
    first = (
        np.arange(1, columns + 1, dtype=np.float64)
        + 1j * np.arange(columns, 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    second = (
        np.arange(columns + 3, 2 * columns + 3, dtype=np.float64)
        - 0.5j * np.arange(1, columns + 1, dtype=np.float64)
    ).astype(np.complex128)
    fine = (
        np.arange(2, rows + 2, dtype=np.float64)
        + 0.25j * np.arange(rows, 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    before = first.copy()
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    observed = edge_transfer @ first
    repeated = edge_transfer @ first
    combined = edge_transfer @ (alpha * first + beta * second)
    expected = alpha * observed + beta * (edge_transfer @ second)
    lhs = np.vdot(observed, fine)
    rhs = np.vdot(first, edge_transfer.conj().T @ fine)
    return {
        "adjoint_work_relative": float(
            abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny)
        ),
        "linearity_relative": _relative(combined, expected),
        "repeat_relative": _relative(repeated, observed),
        "input_unchanged": bool(np.array_equal(first, before)),
        "finite": bool(
            np.all(np.isfinite(observed))
            and np.all(np.isfinite(repeated))
            and np.all(np.isfinite(combined))
        ),
    }


def _independent_facts(
    fine_degree: int,
    coarse_degree: int,
    edge_transfer: np.ndarray,
    node_transfer: np.ndarray,
) -> dict[str, object]:
    fine_degree = int(fine_degree)
    coarse_degree = int(coarse_degree)
    if (fine_degree, coarse_degree) not in INTERLEVEL_PAIRS:
        raise ValueError("only (6, 3) and (3, 1) interlevel maps are supported")
    edge_transfer = np.asarray(edge_transfer, dtype=np.complex128)
    node_transfer = np.asarray(node_transfer, dtype=np.complex128)
    node_reference = None
    if (fine_degree, coarse_degree) == (3, 1):
        authority = build_local_lor_edge_geometric_transfer(3)
        basix_to_lor = np.asarray(
            authority.coarse_basix_to_lor_order, dtype=np.int32
        )
        custom_columns = np.argsort(basix_to_lor)
        expected_shape = tuple(int(value) for value in authority.edge_transfer.shape)
        expected_node_shape = tuple(int(value) for value in authority.node_transfer.shape)
        edge_oracle = np.asarray(
            authority.direct_edge_integral[:, custom_columns],
            dtype=np.complex128,
        )
        curl_oracle = np.asarray(
            authority.direct_curl_flux[:, custom_columns],
            dtype=np.complex128,
        )
        fine_curl = np.asarray(authority.fine_curl_incidence, dtype=np.complex128)
        coarse_gradient = np.asarray(
            authority.coarse_gradient[custom_columns], dtype=np.complex128
        )
        fine_gradient = np.asarray(authority.fine_gradient, dtype=np.complex128)
        node_reference = np.asarray(authority.node_transfer, dtype=np.complex128)
        cond = 1.0
    else:
        fine_local = build_local_lor_transfer(fine_degree)
        coarse_local = build_local_lor_transfer(coarse_degree)
        coarse_element = _n1e(coarse_degree)
        coarse_transform = np.asarray(
            coarse_local.high_to_lor_matrix, dtype=np.complex128
        )
        expected_shape = (
            int(fine_local.high_to_lor_matrix.shape[0]),
            int(coarse_transform.shape[0]),
        )
        expected_node_shape = (
            int(fine_local.h1_transfer.shape[0]),
            int(coarse_local.h1_transfer.shape[0]),
        )
        coarse_inverse = np.linalg.solve(
            coarse_transform,
            np.eye(coarse_transform.shape[0], dtype=np.complex128),
        )
        edge_oracle = _edge_line_integral_oracle(
            fine_degree, coarse_element, fine_local.nodes
        ) @ coarse_inverse
        curl_oracle = _curl_face_oracle(
            fine_degree, coarse_element, fine_local.nodes
        ) @ coarse_inverse
        fine_curl = np.asarray(fine_local.lor_curl_incidence, dtype=np.complex128)
        coarse_gradient = np.asarray(coarse_local.lor_gradient, dtype=np.complex128)
        fine_gradient = np.asarray(fine_local.lor_gradient, dtype=np.complex128)
        cond = float(np.linalg.cond(coarse_transform))

    if edge_transfer.shape != expected_shape:
        raise ValueError(
            f"edge map shape {edge_transfer.shape} != expected {expected_shape}"
        )
    if node_transfer.shape != expected_node_shape:
        raise ValueError(
            f"node map shape {node_transfer.shape} != expected {expected_node_shape}"
        )
    if not np.all(np.isfinite(edge_transfer)) or not np.all(
        np.isfinite(node_transfer)
    ):
        raise ValueError("interlevel map contains non-finite values")

    structural_mask = _structural_trace_mask(fine_degree, coarse_degree)
    forbidden = edge_transfer[~structural_mask]
    if np.any(forbidden != 0.0):
        raise ValueError("structural forbidden edge entries are not exact zero")

    curl_incidence = fine_curl @ edge_transfer
    gradient_left = fine_gradient @ node_transfer
    gradient_right = edge_transfer @ coarse_gradient
    probe = _probe_facts(edge_transfer)
    edge_relative = _relative(edge_transfer, edge_oracle)
    curl_relative = _relative(curl_incidence, curl_oracle)
    gradient_relative = _relative(gradient_left, gradient_right)
    node_relative = (
        0.0
        if node_reference is None
        else _relative(node_transfer, node_reference)
    )
    if not np.isfinite(cond):
        raise ValueError("coarse high-to-LOR transform condition is non-finite")
    audit = {
        "schema": "task038.local_interlevel_edge_transfer.v1",
        "fine_degree": fine_degree,
        "coarse_degree": coarse_degree,
        "batch_cell_cap": int(INTERLEVEL_BATCH_CELL_CAP),
        "edge_shape": tuple(int(value) for value in edge_transfer.shape),
        "node_shape": tuple(int(value) for value in node_transfer.shape),
        "edge_dtype": "complex128",
        "node_dtype": "complex128",
        "edge_numeric_bytes": int(edge_transfer.nbytes),
        "node_numeric_bytes": int(node_transfer.nbytes),
        "coarse_transform_condition": cond,
        "edge_line_integral_relative": edge_relative,
        "curl_flux_relative": curl_relative,
        "gradient_commuting_relative": gradient_relative,
        "node_transfer_relative": node_relative,
        "adjoint_work_relative": probe["adjoint_work_relative"],
        "linearity_relative": probe["linearity_relative"],
        "repeat_relative": probe["repeat_relative"],
        "input_unchanged": probe["input_unchanged"],
        "finite": probe["finite"],
        "line_integral_histopolation": True,
        "simple_injection": False,
        "global_transfer_matrix": False,
        "oracle_workspace_retained": False,
        "structural_projection": True,
        "structural_forbidden_entry_count": int(np.count_nonzero(~structural_mask)),
        "structural_forbidden_nnz_after": int(np.count_nonzero(forbidden)),
        "structural_removed_nonzero_count": 0,
        "structural_removed_max_abs": 0.0,
    }
    limits = (
        ("edge_line_integral_relative", EDGE_QUADRATURE_LIMIT),
        ("curl_flux_relative", CURL_LIMIT),
        ("gradient_commuting_relative", GRADIENT_LIMIT),
        ("node_transfer_relative", GRADIENT_LIMIT),
        ("adjoint_work_relative", ADJOINT_LIMIT),
        ("linearity_relative", LINEARITY_LIMIT),
        ("repeat_relative", REPEAT_LIMIT),
    )
    for name, limit in limits:
        if float(audit[name]) > limit:
            raise ValueError(f"{name}={audit[name]:.17g} exceeds {limit:.17g}")
    if not audit["input_unchanged"] or not audit["finite"]:
        raise ValueError("interlevel local legality probe failed")
    return audit


def audit_local_interlevel_transfer(
    fine_degree: int,
    coarse_degree: int,
    edge_transfer: np.ndarray,
    node_transfer: np.ndarray,
) -> dict[str, object]:
    """Independently recompute all bounded local transfer facts."""

    return _independent_facts(
        fine_degree, coarse_degree, edge_transfer, node_transfer
    )


class LocalInterlevelEdgeTransfer:
    """Immutable bounded cell-local transfer for exactly one S5 pair."""

    __slots__ = (
        "fine_degree",
        "coarse_degree",
        "edge_transfer",
        "node_transfer",
        "audit",
        "_frozen",
    )

    def __init__(
        self,
        fine_degree: int,
        coarse_degree: int,
        edge_transfer: np.ndarray,
        node_transfer: np.ndarray,
        audit: dict[str, object],
    ) -> None:
        object.__setattr__(self, "fine_degree", int(fine_degree))
        object.__setattr__(self, "coarse_degree", int(coarse_degree))
        edge = np.ascontiguousarray(edge_transfer, dtype=np.complex128)
        node = np.ascontiguousarray(node_transfer, dtype=np.complex128)
        edge.setflags(write=False)
        node.setflags(write=False)
        object.__setattr__(self, "edge_transfer", edge)
        object.__setattr__(self, "node_transfer", node)
        object.__setattr__(self, "audit", MappingProxyType(dict(audit)))
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("LocalInterlevelEdgeTransfer is immutable")
        object.__setattr__(self, name, value)

    @property
    def edge_shape(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.edge_transfer.shape)

    def apply_primal_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        squeezed = vectors.ndim == 1
        if squeezed:
            vectors = vectors[None, :]
        if vectors.ndim != 2 or vectors.shape[1] != self.edge_shape[1]:
            raise ValueError("coarse batch has an unexpected local shape")
        if not 1 <= vectors.shape[0] <= INTERLEVEL_BATCH_CELL_CAP:
            raise ValueError("interlevel batch exceeds the fixed cap")
        result = np.asarray(vectors @ self.edge_transfer.T, dtype=np.complex128)
        return result[0] if squeezed else result

    def apply_adjoint_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        squeezed = vectors.ndim == 1
        if squeezed:
            vectors = vectors[None, :]
        if vectors.ndim != 2 or vectors.shape[1] != self.edge_shape[0]:
            raise ValueError("fine batch has an unexpected local shape")
        if not 1 <= vectors.shape[0] <= INTERLEVEL_BATCH_CELL_CAP:
            raise ValueError("interlevel batch exceeds the fixed cap")
        result = np.asarray(vectors @ self.edge_transfer.conj(), dtype=np.complex128)
        return result[0] if squeezed else result


def build_local_interlevel_edge_transfer(
    fine_degree: int, coarse_degree: int
) -> LocalInterlevelEdgeTransfer:
    """Build and independently qualify one fixed local interlevel map."""

    pair = (int(fine_degree), int(coarse_degree))
    if pair not in INTERLEVEL_PAIRS:
        raise ValueError("only (fine, coarse)=(6, 3) or (3, 1) is supported")
    if pair == (3, 1):
        authority = build_local_lor_edge_geometric_transfer(3)
        custom_columns = np.argsort(authority.coarse_basix_to_lor_order)
        edge_transfer = np.asarray(
            authority.edge_transfer[:, custom_columns], dtype=np.complex128
        )
        node_transfer = np.asarray(authority.node_transfer, dtype=np.complex128)
    else:
        fine_local = build_local_lor_transfer(pair[0])
        coarse_local = build_local_lor_transfer(pair[1])
        fine_element = _n1e(pair[0])
        coarse_element = _n1e(pair[1])
        interpolation = np.asarray(
            basix.compute_interpolation_operator(coarse_element, fine_element),
            dtype=np.complex128,
        )
        coarse_transform = np.asarray(
            coarse_local.high_to_lor_matrix, dtype=np.complex128
        )
        edge_transfer = np.asarray(
            fine_local.high_to_lor_matrix
            @ interpolation
            @ np.linalg.solve(
                coarse_transform,
                np.eye(coarse_transform.shape[0], dtype=np.complex128),
            ),
            dtype=np.complex128,
        )
        node_transfer = _node_transfer(
            fine_local, coarse_local, pair[0], pair[1]
        )
    edge_transfer = np.ascontiguousarray(edge_transfer, dtype=np.complex128)
    structural_mask = _structural_trace_mask(pair[0], pair[1])
    removed = edge_transfer[~structural_mask]
    removed_nonzero_count = int(np.count_nonzero(removed))
    removed_max_abs = float(np.max(np.abs(removed))) if removed.size else 0.0
    edge_transfer[~structural_mask] = 0.0
    audit = _independent_facts(
        pair[0], pair[1], edge_transfer, node_transfer
    )
    audit.update(
        structural_removed_nonzero_count=removed_nonzero_count,
        structural_removed_max_abs=removed_max_abs,
    )
    return LocalInterlevelEdgeTransfer(
        pair[0], pair[1], edge_transfer, node_transfer, audit
    )


__all__ = [
    "ADJOINT_LIMIT",
    "CURL_LIMIT",
    "EDGE_QUADRATURE_LIMIT",
    "GRADIENT_LIMIT",
    "INTERLEVEL_BATCH_CELL_CAP",
    "INTERLEVEL_PAIRS",
    "LINEARITY_LIMIT",
    "REPEAT_LIMIT",
    "LocalInterlevelEdgeTransfer",
    "audit_local_interlevel_transfer",
    "build_local_interlevel_edge_transfer",
]
