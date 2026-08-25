"""Research-only exact one-cell traction coupling contracts.

This module contains the small, explicit data boundary between the exact
one-cell endpoint Schur oracle and a Hybrid local interface.  It does not
change ordinary scalar-CG traction behavior and never constructs a dense
endpoint square.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from petsc4py import PETSc


EXACT_ONE_CELL_TRACTION_MODEL = "full3d_one_cell_exact_schur"
EXACT_ROW_IDENTITY_TOLERANCE = 1.0e-10


class TraceIdentityGateError(RuntimeError):
    """A finite, shape-valid trace comparison failed its numerical gate."""


def _columns(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.complex128)
    if array.ndim != 2:
        raise ValueError(f"{name} must be a rank-2 complex array.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite.")
    return array


def congruent_trace_identity(
    exact_columns: Any,
    local_columns: Any,
    *,
    side: str,
    tolerance: float = EXACT_ROW_IDENTITY_TOLERANCE,
) -> dict[str, Any]:
    """Compare exact one-cell and local-interface primal columns.

    The arrays must use the same ordered active trace rows.  A shape mismatch
    is a structural error, while the returned relative discrepancy is the
    numerical identity evidence used by the explicit Task37c lane.
    """

    if side not in {"bottom", "top"}:
        raise ValueError("Trace identity side must be bottom or top.")
    exact = _columns(exact_columns, f"{side} exact columns")
    local = _columns(local_columns, f"{side} local columns")
    if exact.shape != local.shape:
        raise ValueError(
            f"{side} exact/local trace shapes differ: {exact.shape} != {local.shape}."
        )
    scale = max(float(np.linalg.norm(exact)), float(np.linalg.norm(local)), 1.0e-30)
    relative = float(np.linalg.norm(exact - local) / scale)
    return {
        "side": side,
        "rows": int(exact.shape[0]),
        "columns": int(exact.shape[1]),
        "relative_l2": relative,
        "tolerance": float(tolerance),
        "finite": True,
        "pass": bool(relative <= float(tolerance)),
    }


def require_congruent_trace_identity(
    exact_columns: Any,
    local_columns: Any,
    *,
    side: str,
    tolerance: float = EXACT_ROW_IDENTITY_TOLERANCE,
) -> dict[str, Any]:
    """Return identity evidence or fail closed before dual embedding."""

    audit = congruent_trace_identity(
        exact_columns,
        local_columns,
        side=side,
        tolerance=tolerance,
    )
    if audit["pass"] is not True:
        raise TraceIdentityGateError(
            f"{side} exact/local primal trace identity failed: "
            f"relative_l2={audit['relative_l2']:.6e}, "
            f"limit={audit['tolerance']:.6e}."
        )
    return audit


def _transfer_entity_block(
    source_columns: Any,
    source_transform: Any,
    source_phase: complex,
    target_transform: Any,
    target_phase: complex,
    *,
    dual: bool = False,
) -> np.ndarray:
    """Transfer one small canonical H(curl) entity block.

    Stored primal coefficients obey ``stored = phase * E * canonical``.
    Dual columns use the inverse-conjugate-transpose of the resulting primal
    map.  This helper is intentionally block-local; it never constructs an
    endpoint-sized dense transfer matrix.
    """

    values = _columns(source_columns, "entity columns")
    source = np.asarray(source_transform, dtype=np.complex128)
    target = np.asarray(target_transform, dtype=np.complex128)
    if source.ndim != 2 or target.ndim != 2:
        raise ValueError("Entity transforms must be rank-2 matrices.")
    if source.shape[0] != source.shape[1] or target.shape[0] != target.shape[1]:
        raise ValueError("Entity transforms must be square.")
    if source.shape != target.shape or source.shape[0] != values.shape[0]:
        raise ValueError("Entity transform and coefficient block shapes differ.")
    if not np.isfinite(source_phase) or not np.isfinite(target_phase):
        raise ValueError("Entity phases must be finite.")
    if abs(source_phase) <= 1.0e-14 or abs(target_phase) <= 1.0e-14:
        raise ValueError("Entity phases must be nonzero.")
    primal_map = (
        complex(target_phase)
        * target
        @ np.linalg.solve(source, np.eye(source.shape[0], dtype=np.complex128))
        / complex(source_phase)
    )
    if dual:
        return np.linalg.solve(primal_map.conj().T, values)
    return primal_map @ values


def _endpoint_entity_blocks(V, condensed, endpoint: str, tolerance: float):
    """Collect independent active edge/face blocks on one endpoint."""

    from mpi4py import MPI

    from ..geometry.tetra_mesh_audit import canonical_entity_key
    from ..solvers.hcurl_canonical_vector_dolfinx import (
        _entity_coordinates,
        _physical_entity_transform,
    )

    if endpoint not in {"left", "right"}:
        raise ValueError("Endpoint must be left or right.")
    mesh = V.mesh
    topology = mesh.topology
    tdim = topology.dim
    for dimension in (1, 2):
        topology.create_entities(dimension)
        topology.create_connectivity(dimension, tdim)
        topology.create_connectivity(tdim, dimension)
    local_z = np.asarray(mesh.geometry.x[:, 2], dtype=np.float64)
    z_min = mesh.comm.allreduce(float(np.min(local_z, initial=np.inf)), op=MPI.MIN)
    z_max = mesh.comm.allreduce(float(np.max(local_z, initial=-np.inf)), op=MPI.MAX)
    endpoint_z = z_min if endpoint == "left" else z_max
    constraints = condensed.trace_constraints
    active_originals = {
        int(value)
        for packet in mesh.comm.allgather(
            tuple(int(value) for value in constraints.owned_active_original_dofs)
        )
        for value in packet
    }
    degree = int(V.element.basix_element.degree)
    layout = V.dofmap.dof_layout
    entity_to_cell = {
        dimension: topology.connectivity(dimension, tdim) for dimension in (1, 2)
    }
    local_blocks = []
    for dimension in (1, 2):
        entity_map = topology.index_map(dimension)
        for entity in range(int(entity_map.size_local)):
            coords = _entity_coordinates(V, dimension, entity)
            if not np.allclose(
                coords[:, 2], endpoint_z, rtol=0.0, atol=10.0 * tolerance
            ):
                continue
            cells = entity_to_cell[dimension].links(entity)
            if len(cells) == 0:
                raise RuntimeError("Endpoint entity has no owned incident cell.")
            cell = int(cells[0])
            cell_entities = topology.connectivity(tdim, dimension).links(cell)
            local_matches = np.flatnonzero(
                np.asarray(cell_entities, dtype=np.int32) == int(entity)
            )
            if len(local_matches) != 1:
                raise RuntimeError("Endpoint entity has no unique cell-local position.")
            positions = np.asarray(
                layout.entity_dofs(dimension, int(local_matches[0])), dtype=np.int32
            )
            originals = np.asarray(
                V.dofmap.index_map.local_to_global(
                    np.asarray(V.dofmap.cell_dofs(cell), dtype=np.int32)[positions]
                ),
                dtype=np.int64,
            )
            if not all(int(original) in active_originals for original in originals):
                continue
            active_ids = []
            for original in originals:
                original = int(original)
                expansion = constraints.expansion_by_original.get(original)
                active = constraints.original_to_active.get(original)
                if (
                    expansion is None
                    or active is None
                    or len(expansion[0]) != 1
                    or int(expansion[0][0]) != int(active)
                    or len(expansion[1]) != 1
                    or abs(complex(expansion[1][0]) - 1.0) > 1.0e-14
                ):
                    raise RuntimeError(
                        "Endpoint active master entity has a non-identity expansion: "
                        f"dimension={dimension}, entity={entity}."
                    )
                active_ids.append(int(active))
            physical_key = canonical_entity_key(coords, tolerance)
            transform, _state = _physical_entity_transform(
                coords, dimension, degree, tolerance
            )
            local_blocks.append(
                {
                    "key": _normalized_entity_key_from_quantized(
                        physical_key, dimension
                    ),
                    "active_ids": tuple(active_ids),
                    "transform": np.asarray(transform, dtype=np.complex128),
                    "phase": 1.0 + 0.0j,
                    "dimension": int(dimension),
                }
            )
    packets = mesh.comm.allgather(local_blocks)
    blocks = {}
    for packet in packets:
        for block in packet:
            key = block["key"]
            if key in blocks:
                raise RuntimeError(f"Duplicate endpoint entity block: {key!r}.")
            blocks[key] = block
    return blocks


def _normalized_entity_key_from_quantized(key, dimension: int):
    return int(dimension), tuple(
        sorted((int(point[0]), int(point[1])) for point in key)
    )


def _floquet_phase_values(floquet_data) -> tuple[complex, complex, complex]:
    phase_x = complex(floquet_data.phase_x)
    phase_y = complex(floquet_data.phase_y)
    phase_corner = (
        complex(floquet_data.phase_corner)
        if hasattr(floquet_data, "phase_corner")
        else phase_x * phase_y
    )
    return phase_x, phase_y, phase_corner


def _floquet_phase_identity(source_floquet, target_floquet) -> dict[str, Any]:
    source = _floquet_phase_values(source_floquet)
    target = _floquet_phase_values(target_floquet)
    if not all(np.isfinite(value) for value in (*source, *target)):
        raise RuntimeError("Source/target Floquet phases must be finite.")
    deltas = tuple(
        abs(left - right) for left, right in zip(source, target, strict=True)
    )
    if not all(np.isfinite(delta) for delta in deltas):
        raise RuntimeError("Source/target Floquet phase deltas must be finite.")
    maximum = float(max(deltas))
    if maximum > 1.0e-13:
        raise RuntimeError(
            f"Source/target Floquet phases differ: max_abs_delta={maximum:.6e}."
        )
    return {
        "floquet_phase_identity": True,
        "floquet_phase_delta_max": maximum,
        "floquet_phase_delta": [float(value) for value in deltas],
    }


def _transfer_endpoint_columns(
    source_columns: Any,
    source_space,
    source_condensed,
    source_floquet,
    source_rows: Sequence[int],
    target_space,
    target_condensed,
    target_floquet,
    target_rows: Sequence[int],
    *,
    source_endpoint: str,
    target_endpoint: str,
    dual: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    from ..geometry.tetra_mesh_audit import mesh_coordinate_tolerance

    values = _columns(source_columns, "source endpoint columns")
    source_rows = np.asarray(source_rows, dtype=PETSc.IntType)
    target_rows = np.asarray(target_rows, dtype=PETSc.IntType)
    if len(np.unique(source_rows)) != len(source_rows) or len(
        np.unique(target_rows)
    ) != len(target_rows):
        raise ValueError("Endpoint active rows must be unique.")
    if values.shape[0] != len(source_rows) or len(source_rows) != len(target_rows):
        raise ValueError("Source/target endpoint row counts differ.")
    source_degree = int(source_space.element.basix_element.degree)
    target_degree = int(target_space.element.basix_element.degree)
    if source_degree != target_degree:
        raise ValueError("Source/target N1curl degrees differ.")
    phase_audit = _floquet_phase_identity(source_floquet, target_floquet)
    tolerance = min(
        mesh_coordinate_tolerance(source_space.mesh),
        mesh_coordinate_tolerance(target_space.mesh),
    )
    source_blocks = _endpoint_entity_blocks(
        source_space, source_condensed, source_endpoint, tolerance
    )
    target_blocks = _endpoint_entity_blocks(
        target_space, target_condensed, target_endpoint, tolerance
    )
    if set(source_blocks) != set(target_blocks):
        missing = sorted(set(source_blocks) - set(target_blocks), key=repr)
        extra = sorted(set(target_blocks) - set(source_blocks), key=repr)
        raise RuntimeError(
            "Endpoint entity-block coverage is not bijective: "
            f"missing={missing[:1]}, extra={extra[:1]}"
        )
    source_position = {int(row): index for index, row in enumerate(source_rows)}
    target_position = {int(row): index for index, row in enumerate(target_rows)}
    result = np.zeros((len(target_rows), values.shape[1]), dtype=np.complex128)
    source_covered: set[int] = set()
    target_covered: set[int] = set()
    max_block_size = 0
    dual_inverse_map_reconstruction_error = 0.0
    for key in source_blocks:
        source_block = source_blocks[key]
        target_block = target_blocks[key]
        if source_block["dimension"] != target_block["dimension"]:
            raise RuntimeError(f"Endpoint entity dimension changed for {key!r}.")
        source_ids = tuple(int(value) for value in source_block["active_ids"])
        target_ids = tuple(int(value) for value in target_block["active_ids"])
        if len(source_ids) != len(target_ids):
            raise RuntimeError(f"Endpoint entity block size changed for {key!r}.")
        if any(row not in source_position for row in source_ids) or any(
            row not in target_position for row in target_ids
        ):
            raise RuntimeError(
                f"Endpoint entity block is outside active rows: {key!r}."
            )
        if source_covered.intersection(source_ids) or target_covered.intersection(
            target_ids
        ):
            raise RuntimeError(f"Endpoint active row is covered twice: {key!r}.")
        source_covered.update(source_ids)
        target_covered.update(target_ids)
        source_block_values = values[
            np.asarray([source_position[row] for row in source_ids], dtype=np.int64)
        ]
        transferred = _transfer_entity_block(
            source_block_values,
            source_block["transform"],
            source_block["phase"],
            target_block["transform"],
            target_block["phase"],
            dual=dual,
        )
        result[
            np.asarray([target_position[row] for row in target_ids], dtype=np.int64)
        ] = transferred
        max_block_size = max(max_block_size, len(source_ids))
        if dual:
            primal_map = (
                complex(target_block["phase"])
                * target_block["transform"]
                @ np.linalg.solve(
                    source_block["transform"],
                    np.eye(len(source_ids), dtype=np.complex128),
                )
                / complex(source_block["phase"])
            )
            reconstructed = primal_map.conj().T @ transferred
            scale = max(float(np.linalg.norm(source_block_values)), 1.0e-30)
            dual_inverse_map_reconstruction_error = max(
                dual_inverse_map_reconstruction_error,
                float(np.linalg.norm(reconstructed - source_block_values) / scale),
            )
    if source_covered != set(map(int, source_rows)) or target_covered != set(
        map(int, target_rows)
    ):
        raise RuntimeError("Endpoint active master entity blocks do not cover rows.")
    return result, {
        "entity_block_count": int(len(source_blocks)),
        "max_entity_block_size": int(max_block_size),
        "bijection": True,
        "source_rows": int(len(source_rows)),
        "target_rows": int(len(target_rows)),
        "dual_inverse_map_reconstruction_error": float(
            dual_inverse_map_reconstruction_error
        ),
        **phase_audit,
        "dense_endpoint_square_formed": False,
        "active_master_phase": 1.0,
    }


def transfer_congruent_endpoint_columns(
    source_columns: Any,
    source_space,
    source_condensed,
    source_floquet,
    source_rows: Sequence[int],
    target_space,
    target_condensed,
    target_floquet,
    target_rows: Sequence[int],
    *,
    source_endpoint: str,
    target_endpoint: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Transfer primal endpoint columns through canonical entity blocks."""

    return _transfer_endpoint_columns(
        source_columns,
        source_space,
        source_condensed,
        source_floquet,
        source_rows,
        target_space,
        target_condensed,
        target_floquet,
        target_rows,
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        dual=False,
    )


def transfer_congruent_endpoint_dual_columns(
    source_columns: Any,
    source_space,
    source_condensed,
    source_floquet,
    source_rows: Sequence[int],
    target_space,
    target_condensed,
    target_floquet,
    target_rows: Sequence[int],
    *,
    source_endpoint: str,
    target_endpoint: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Transfer endpoint traction columns by blockwise ``T^{-H}``.

    Here ``T^{-H}`` is the inverse-conjugate-transpose of the primal entity
    transfer, preserving the local complex dual pairing.
    """

    return _transfer_endpoint_columns(
        source_columns,
        source_space,
        source_condensed,
        source_floquet,
        source_rows,
        target_space,
        target_condensed,
        target_floquet,
        target_rows,
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        dual=True,
    )


def split_exact_local_amplitude_blocks(
    forward_flux: Any,
    backward_flux: Any,
    *,
    left_rows: int,
    right_rows: int,
    forward_factors: Any,
    backward_factors: Any,
) -> dict[str, np.ndarray]:
    """Split exact outward flux into bottom/top local-amplitude blocks."""

    forward = _columns(forward_flux, "forward flux")
    backward = _columns(backward_flux, "backward flux")
    if forward.shape != backward.shape:
        raise ValueError("Forward/backward exact flux shapes differ.")
    expected_rows = int(left_rows) + int(right_rows)
    if forward.shape[0] != expected_rows:
        raise ValueError("Exact flux rows do not match the two endpoint row counts.")
    lam = np.asarray(forward_factors, dtype=np.complex128)
    mu = np.asarray(backward_factors, dtype=np.complex128)
    expected = (forward.shape[1],)
    if lam.shape != expected or mu.shape != expected:
        raise ValueError("Exact propagation factors need one entry per column.")
    if (
        not np.all(np.isfinite(lam))
        or not np.all(np.isfinite(mu))
        or np.any(np.abs(lam) <= 1.0e-14)
        or np.any(np.abs(mu) <= 1.0e-14)
    ):
        raise ValueError("Exact propagation factors must be finite and nonzero.")
    split = int(left_rows)
    return {
        "bottom_forward": forward[:split].copy(),
        "top_forward": (forward[split:] / lam[None, :]).copy(),
        "bottom_backward": (backward[:split] / mu[None, :]).copy(),
        "top_backward": backward[split:].copy(),
    }


def embed_exact_trace_columns_dense_reference(
    local_rows: Any,
    columns: Any,
    *,
    local_fe_rows: int,
) -> np.ndarray:
    """Pure dense reference embedding; production uses owned PETSc insertion."""

    rows = np.asarray(local_rows, dtype=PETSc.IntType)
    values = _columns(columns, "exact trace columns")
    if rows.ndim != 1 or len(np.unique(rows)) != len(rows):
        raise ValueError("Local interface rows must be a unique one-dimensional list.")
    if len(rows) != values.shape[0]:
        raise ValueError("Local interface row count and exact column rows differ.")
    if np.any(rows < 0) or np.any(rows >= int(local_fe_rows)):
        raise ValueError("Exact interface rows lie outside the local FE layout.")
    result = np.zeros((int(local_fe_rows), values.shape[1]), dtype=np.complex128)
    result[rows, :] = values
    return result


@dataclass(frozen=True)
class ExactOneCellCoupling:
    """Four exact blocks plus the auditable row/lifecycle contract."""

    blocks: Mapping[str, np.ndarray]
    bottom_rows: np.ndarray
    top_rows: np.ndarray
    row_identity: Mapping[str, Mapping[str, Any]]
    action_audit: Mapping[str, int]
    dense_endpoint_square_formed: bool = False
    exact_reduced_trace_columns: bool = True
    zero_eliminated_interior_support: bool = True
    transient_released: bool = True

    def __post_init__(self) -> None:
        required = {
            "bottom_forward",
            "top_forward",
            "bottom_backward",
            "top_backward",
        }
        if set(self.blocks) != required:
            raise ValueError(
                "Exact coupling must contain exactly four directional blocks."
            )
        blocks = dict(self.blocks)
        object.__setattr__(self, "blocks", blocks)
        bottom_rows = np.asarray(self.bottom_rows, dtype=PETSc.IntType)
        top_rows = np.asarray(self.top_rows, dtype=PETSc.IntType)
        object.__setattr__(self, "bottom_rows", bottom_rows)
        object.__setattr__(self, "top_rows", top_rows)
        for name, values in blocks.items():
            array = _columns(values, name)
            expected_rows = bottom_rows if name.startswith("bottom") else top_rows
            if array.shape[0] != len(expected_rows):
                raise ValueError(f"{name} does not match its ordered interface rows.")
            blocks[name] = array
        identity = {side: dict(values) for side, values in self.row_identity.items()}
        for side in ("bottom", "top"):
            if side not in identity:
                raise ValueError(f"Exact coupling is missing {side} row identity.")
            for trace_kind in ("positive", "raw_negative"):
                if identity[side].get(trace_kind, {}).get("pass") is not True:
                    raise ValueError(
                        f"{side} {trace_kind} row identity must pass before embedding."
                    )
        object.__setattr__(self, "row_identity", identity)
        action = dict(self.action_audit)
        required_action = {"port_rows", "interior_rows", "interior_matrix_nnz"}
        if set(action) != required_action:
            raise ValueError("Exact coupling action audit has the wrong fields.")
        if any(int(value) < 0 for value in action.values()):
            raise ValueError("Exact coupling action audit cannot be negative.")
        object.__setattr__(self, "action_audit", action)
        if self.dense_endpoint_square_formed:
            raise ValueError(
                "Exact one-cell coupling may not form a dense endpoint square."
            )
        if self.transient_released is not True:
            raise ValueError("Exact one-cell transient owners must be released.")

    @property
    def mode_count(self) -> int:
        return int(self.blocks["bottom_forward"].shape[1])

    def audit(self) -> dict[str, Any]:
        return {
            "model": EXACT_ONE_CELL_TRACTION_MODEL,
            "block_shapes": {
                name: list(values.shape) for name, values in self.blocks.items()
            },
            "bottom_rows": int(len(self.bottom_rows)),
            "top_rows": int(len(self.top_rows)),
            **self.action_audit,
            "dense_endpoint_square_formed": False,
            "exact_reduced_trace_columns": bool(self.exact_reduced_trace_columns),
            "zero_eliminated_interior_support": bool(
                self.zero_eliminated_interior_support
            ),
            "row_identity": dict(self.row_identity),
            "transient_released": bool(self.transient_released),
        }


def exact_model_record(enabled: bool) -> dict[str, Any]:
    """Return explicit model identity without changing ordinary defaults."""

    return {
        "requested": bool(enabled),
        "model": EXACT_ONE_CELL_TRACTION_MODEL if enabled else "ordinary_default",
        "research_only": bool(enabled),
        "production_qualified": False if enabled else None,
    }


__all__ = [
    "EXACT_ONE_CELL_TRACTION_MODEL",
    "EXACT_ROW_IDENTITY_TOLERANCE",
    "ExactOneCellCoupling",
    "TraceIdentityGateError",
    "congruent_trace_identity",
    "embed_exact_trace_columns_dense_reference",
    "exact_model_record",
    "require_congruent_trace_identity",
    "split_exact_local_amplitude_blocks",
    "transfer_congruent_endpoint_columns",
    "transfer_congruent_endpoint_dual_columns",
]
