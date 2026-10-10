"""Bounded, real Ny=8 edge-orbit panel for the Task40 V24 volume operator.

The panel keeps the complete local 432-column trace Schur block until the
actual finalized MPC expansion is applied.  It produces the complete 48-row
Ny=8 q-row block against every touched active trace column.  The 48-by-48
edge self q-by-r block is saved as a nested diagnostic; neither output is a
full q matrix or a full-volume action.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from scipy import sparse


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(repr((array.shape, str(array.dtype))).encode("ascii"))
    digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_frobenius_error(
    actual: np.ndarray, expected: np.ndarray
) -> tuple[float, float, float]:
    actual_array = np.asarray(actual, dtype=np.complex128)
    expected_array = np.asarray(expected, dtype=np.complex128)
    if actual_array.shape != expected_array.shape:
        raise ValueError("V24 panel comparison arrays have different shapes")
    error_norm = float(np.linalg.norm(actual_array - expected_array))
    oracle_norm = float(np.linalg.norm(expected_array))
    if oracle_norm == 0.0:
        return (0.0 if error_norm == 0.0 else float("inf"), error_norm, oracle_norm)
    return error_norm / oracle_norm, error_norm, oracle_norm


def _assemble_v17_edge_row_blocks(
    native_panel: np.ndarray,
    *,
    edge_column_positions: np.ndarray,
    row_basis: np.ndarray,
    index_dtype: np.dtype,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
    resource_admission: Callable[[str, int], Mapping[str, Any]],
) -> tuple[dict[tuple[int, int], sparse.csr_matrix], dict[str, Any]]:
    """Run the existing bounded V17 CSR consumer for a selected complete row panel."""

    from src.solvers.task40_v10_p6_yorbit import (
        _assemble_bounded_v17_row_tile_q_patterns,
    )

    native = np.asarray(native_panel, dtype=np.complex128)
    edge_positions = np.asarray(edge_column_positions, dtype=np.int64)
    basis = np.asarray(row_basis, dtype=np.complex128)
    if native.ndim != 2 or basis.shape != (native.shape[0], native.shape[0]):
        raise ValueError("V24 V17 row panel dimensions do not match the selected entity rows")
    column_count = native.shape[1]
    row_count = native.shape[0]
    if (
        edge_positions.shape != (row_count,)
        or len(np.unique(edge_positions)) != row_count
        or np.any(edge_positions < 0)
        or np.any(edge_positions >= column_count)
    ):
        raise ValueError("V24 V17 edge row positions are invalid or duplicated")
    dtype = np.dtype(index_dtype)
    if dtype.kind != "i" or dtype.itemsize not in (4, 8):
        raise TypeError("V24 V17 row panel requires signed int32/int64 indices")

    # Sparse construction avoids an N-by-48 dense q-map.  Rows map native
    # active trace rows into the true oriented Bloch edge basis.
    q_map0 = sparse.csr_matrix(
        (
            basis.reshape(-1),
            (
                np.repeat(edge_positions, row_count).astype(dtype, copy=False),
                np.tile(np.arange(row_count, dtype=dtype), row_count),
            ),
        ),
        shape=(column_count, row_count),
    )
    q_map0.sum_duplicates()
    q_map0.sort_indices()
    q_map0.indices = np.asarray(q_map0.indices, dtype=dtype)
    q_map0.indptr = np.asarray(q_map0.indptr, dtype=dtype)
    q_map1 = sparse.eye(column_count, dtype=np.complex128, format="csr")
    q_map1.indices = np.asarray(q_map1.indices, dtype=dtype)
    q_map1.indptr = np.asarray(q_map1.indptr, dtype=dtype)

    row_order = np.argsort(edge_positions, kind="stable")
    action_rows = np.asarray(edge_positions[row_order], dtype=dtype)
    action_values = np.ascontiguousarray(native[row_order, :])
    action_columns = np.arange(column_count, dtype=dtype)

    class _V24PanelContribution:
        def iter_reduced_contribution_layouts(self, *, hhat_block_columns=None):
            del hhat_block_columns
            yield action_rows, action_columns, "v24/complete_edge_q_row/native_trace_columns"

        def iter_reduced_contributions(
            self, *, allocation_gate, hhat_block_columns=None
        ):
            del hhat_block_columns
            allocation_gate(
                "v24/complete_edge_q_row/native_trace_columns",
                {
                    "additional_payload_bytes": int(action_values.nbytes),
                    "workspace_bytes": int(action_rows.nbytes + action_columns.nbytes),
                    "shape": list(action_values.shape),
                    "index_dtype": dtype.str,
                },
            )
            yield (
                action_rows,
                action_columns,
                action_values,
                "v24/complete_edge_q_row/native_trace_columns",
            )

    worst_case_csr_bytes = int(
        4 * (column_count + 1) * dtype.itemsize
        + (2 * row_count * column_count + row_count * row_count)
        * (dtype.itemsize + np.dtype(np.complex128).itemsize)
    )
    admission = dict(
        resource_admission(
            "v24_v17_complete_edge_row_csr",
            worst_case_csr_bytes + 256 * 2**20,
        )
    )
    v17_started = time.perf_counter()
    blocks, audit = _assemble_bounded_v17_row_tile_q_patterns(
        _V24PanelContribution(), (q_map0, q_map1), allocation_gate=allocation_gate
    )
    consumer_seconds = time.perf_counter() - v17_started

    direct_q_row = basis.conjugate().T @ native
    direct_q_edge = direct_q_row[:, edge_positions] @ basis
    if blocks[(0, 1)].shape != (row_count, column_count):
        raise RuntimeError("V17 consumer returned a non-complete selected q-row block")
    if blocks[(0, 0)].shape != (row_count, row_count):
        raise RuntimeError("V17 consumer returned a malformed edge q-by-r subpanel")
    q_row_error, q_row_error_norm, q_row_oracle_norm = _relative_frobenius_error(
        blocks[(0, 1)].toarray(), direct_q_row
    )
    q_edge_error, q_edge_error_norm, q_edge_oracle_norm = _relative_frobenius_error(
        blocks[(0, 0)].toarray(), direct_q_edge
    )
    if q_row_error > 1e-11 or q_edge_error > 1e-11:
        raise RuntimeError(
            "V17 CSR q-row accumulation differs from its dense oracle by more than "
            f"1e-11 relative (row={q_row_error:.6e}, edge={q_edge_error:.6e})"
        )
    facts = {
        "consumer": "_assemble_bounded_v17_row_tile_q_patterns",
        "assembly_strategy": str(audit.get("assembly_strategy")),
        "row_tile_rows": 64,
        "index_dtype": dtype.str,
        "q_map0_shape": list(q_map0.shape),
        "q_map0_nnz": int(q_map0.nnz),
        "q_map1_shape": list(q_map1.shape),
        "q_map1_nnz": int(q_map1.nnz),
        "q_row_native_column_block_shape": list(blocks[(0, 1)].shape),
        "q_row_native_column_block_nnz": int(blocks[(0, 1)].nnz),
        "q_row_native_column_block_bytes": int(
            blocks[(0, 1)].indptr.nbytes
            + blocks[(0, 1)].indices.nbytes
            + blocks[(0, 1)].data.nbytes
        ),
        "q_row_relative_frobenius_error": float(q_row_error),
        "q_row_frobenius_error_norm": float(q_row_error_norm),
        "q_row_oracle_frobenius_norm": float(q_row_oracle_norm),
        "q_edge_self_block_shape": list(blocks[(0, 0)].shape),
        "q_edge_self_block_nnz": int(blocks[(0, 0)].nnz),
        "q_edge_self_relative_frobenius_error": float(q_edge_error),
        "q_edge_self_frobenius_error_norm": float(q_edge_error_norm),
        "q_edge_self_oracle_frobenius_norm": float(q_edge_oracle_norm),
        "relative_error_limit": 1e-11,
        "all_block_nnz": {
            f"{p}{q}": int(matrix.nnz) for (p, q), matrix in blocks.items()
        },
        "all_block_csr_payload_bytes": dict(
            audit.get("final_csr_payload_bytes_by_block", {})
        ),
        "staging_peak_bytes": int(
            audit.get("staging_peak_bytes_total_all_blocks", 0)
        ),
        "support_route_spool_peak_file_bytes": int(
            audit.get("support_route_spool_peak_file_bytes", 0)
        ),
        "consumer_wall_seconds": float(consumer_seconds),
        "preallocation_admission": admission,
        "full_q_column_projection": False,
        "q_column_scope": (
            "identity selector over every touched active MPC master; "
            "not a full-operator q map"
        ),
    }
    return blocks, facts


class LocalEquationWitnessFailure(np.linalg.LinAlgError):
    """A failed local residual gate carrying the exact class input for evidence."""

    def __init__(
        self,
        message: str,
        *,
        oriented_class: str,
        audit: Mapping[str, Any],
        payload: Mapping[str, np.ndarray],
    ) -> None:
        super().__init__(message)
        self.oriented_class = str(oriented_class)
        self.audit = dict(audit)
        self.payload = {
            str(name): np.asarray(value, dtype=np.complex128)
            for name, value in payload.items()
        }


def project_edge_orbit_panel(
    native_panel: np.ndarray,
    edge_transforms: np.ndarray,
    *,
    ky: float,
    period_y: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply the actual eight entity maps, then the frozen Ny=8 Bloch DFT."""

    native = np.asarray(native_panel, dtype=np.complex128)
    transforms = np.asarray(edge_transforms, dtype=np.complex128)
    if native.shape != (48, 48) or transforms.shape != (8, 6, 6):
        raise ValueError("V24 edge panel requires eight six-row physical entity blocks")
    if not np.isfinite(native).all() or not np.isfinite(transforms).all():
        raise ValueError("V24 edge panel and entity transforms must be finite")
    if not np.isfinite(ky) or not np.isfinite(period_y) or period_y <= 0:
        raise ValueError("V24 Ny=8 Bloch phase requires finite ky and positive period_y")

    entity_map = np.zeros((48, 48), dtype=np.complex128)
    for orbit, transform in enumerate(transforms):
        start = 6 * orbit
        entity_map[start : start + 6, start : start + 6] = transform
    theta = (float(ky) * float(period_y) + 2.0 * np.pi * np.arange(8)) / 8.0
    dft = np.exp(1j * np.arange(8)[:, None] * theta[None, :]) / np.sqrt(8.0)
    orbit_dft = np.kron(dft, np.eye(6, dtype=np.complex128))
    canonical = entity_map.conjugate().T @ native @ entity_map
    modal = orbit_dft.conjugate().T @ canonical @ orbit_dft
    if not np.isfinite(modal).all():
        raise FloatingPointError("V24 edge-orbit q projection produced non-finite entries")
    return canonical, modal, dft


def _local_trace_expansion(
    trace_global: np.ndarray,
    mpc_rows: Mapping[int, tuple[np.ndarray, np.ndarray]],
    *,
    index_dtype: np.dtype,
) -> tuple[np.ndarray, sparse.csr_matrix, int]:
    """Build the exact cell-local trace-to-active expansion from finalized MPC rows."""

    original = np.asarray(trace_global, dtype=np.int64)
    if original.ndim != 1 or len(original) != 432 or len(np.unique(original)) != 432:
        raise ValueError("V24 panel cell must retain all 432 distinct trace rows")
    expanded: list[tuple[np.ndarray, np.ndarray]] = []
    active: set[int] = set()
    slave_count = 0
    for row in original:
        pair = mpc_rows.get(int(row))
        if pair is None:
            ids = np.asarray([row], dtype=np.int64)
            coeffs = np.asarray([1.0], dtype=np.complex128)
        else:
            ids = np.asarray(pair[0], dtype=np.int64)
            coeffs = np.asarray(pair[1], dtype=np.complex128)
            slave_count += 1
            if ids.ndim != 1 or coeffs.ndim != 1 or len(ids) == 0 or len(ids) != len(coeffs):
                raise ValueError("V24 panel received a malformed finalized MPC row")
        if not np.isfinite(coeffs).all():
            raise ValueError("V24 panel received non-finite MPC coefficients")
        active.update(map(int, ids))
        expanded.append((ids, coeffs))

    active_ids = np.asarray(sorted(active), dtype=np.int64)
    active_column = {int(value): index for index, value in enumerate(active_ids)}
    row_indices: list[int] = []
    column_indices: list[int] = []
    values: list[complex] = []
    for row_index, (ids, coeffs) in enumerate(expanded):
        for active_id, coefficient in zip(ids, coeffs, strict=True):
            row_indices.append(row_index)
            column_indices.append(active_column[int(active_id)])
            values.append(complex(coefficient))
    expansion = sparse.csr_matrix(
        (
            np.asarray(values, dtype=np.complex128),
            (
                np.asarray(row_indices, dtype=np.int32),
                np.asarray(column_indices, dtype=np.int32),
            ),
        ),
        shape=(432, len(active_ids)),
    )
    expansion.sum_duplicates()
    expansion.sort_indices()
    if expansion.nnz != len(values) or not np.all(np.diff(expansion.indptr) >= 1):
        raise RuntimeError("V24 panel MPC expansion lost a native trace row")
    if index_dtype.kind not in "iu":
        raise TypeError("V24 panel requires an integer PETSc index type")
    return active_ids, expansion, slave_count


def _grid_index(values: np.ndarray, value: float, tolerance: float = 1e-9) -> int | None:
    matches = np.flatnonzero(np.abs(np.asarray(values, dtype=float) - float(value)) <= tolerance)
    return int(matches[0]) if len(matches) == 1 else None


def build_real_edge_volume_panel(
    *,
    compiled_form: Any,
    function_space: Any,
    cell_tags: Any,
    mpc: Any,
    cfg: Any,
    axes_values: Mapping[str, Sequence[float]],
    resource_sample: Callable[[], Mapping[str, Any]],
    resource_admission: Callable[[str, int], Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble one complete physical edge-orbit Schur panel from real cells."""

    from dolfinx import cpp
    from petsc4py import PETSc
    from scipy.linalg import lu_solve

    from .hcurl_assembly_time_condensation import (
        _canonical_axis_aligned_coordinates,
        _cell_integral_kernels,
        _orient_cell_tensor,
        _strict_local_lu,
        _tabulate_raw_tensor_class,
        assembly_time_condensation_capacity_facts,
        _cell_tag_array,
    )
    from .hcurl_canonical_vector_dolfinx import _physical_entity_transform

    started = time.perf_counter()
    cpu_started = time.process_time()
    mesh = function_space.mesh
    topology = mesh.topology
    if int(mesh.comm.size) != 1 or int(function_space.dofmap.index_map_bs) != 1:
        raise ValueError("V24 real edge panel is qualified for serial scalar-blocked H(curl)")
    if int(function_space.element.space_dimension) != 882:
        raise ValueError("V24 real edge panel requires the frozen 882-row p6 cell element")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise TypeError("V24 real edge panel requires complex128 PETSc")
    axes = {name: np.asarray(axes_values[name], dtype=np.float64) for name in ("x", "y", "z")}
    if len(axes["y"]) != 9:
        raise ValueError("V24 real edge panel requires all eight actual y-cell intervals")
    degree = int(function_space.element.basix_element.degree)
    if degree != 6:
        raise ValueError("V24 real edge panel requires p=6 canonical edge moments")

    for dimension in (1, 3):
        topology.create_entities(dimension)
    topology.create_connectivity(1, 3)
    topology.create_connectivity(3, 1)
    edge_to_cell = topology.connectivity(1, 3)
    cell_to_edge = topology.connectivity(3, 1)
    edge_index_map = topology.index_map(1)
    cell_count = int(topology.index_map(3).size_local)
    cell_permutations = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    tags = _cell_tag_array(cell_tags, cell_count)
    coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int32)
    index_map = function_space.dofmap.index_map
    cell_dofmap = function_space.dofmap
    layout = cell_dofmap.dof_layout
    edge_positions_by_local_entity = {
        local_entity: np.asarray(layout.entity_dofs(1, local_entity), dtype=np.int32)
        for local_entity in range(12)
    }
    if any(len(value) != 6 for value in edge_positions_by_local_entity.values()):
        raise ValueError("actual p6 Basix edge inventory changed from six rows")

    # The base is a genuine y-directed edge in the interior of x and z.  Its
    # eight translates are selected by exact grid vertices, not by row-number
    # arithmetic or a presumed orientation identity.
    candidates: dict[tuple[int, int], dict[int, dict[str, Any]]] = {}
    for edge in range(int(edge_index_map.size_local)):
        geometry_ids = cpp.mesh.entities_to_geometry(
            mesh._cpp_object, 1, np.asarray([edge], dtype=np.int32), True
        )[0]
        edge_coordinates = coordinates[np.asarray(geometry_ids, dtype=np.int64)]
        if edge_coordinates.shape != (2, 3):
            continue
        if not (
            abs(float(edge_coordinates[0, 0] - edge_coordinates[1, 0])) <= 1e-9
            and abs(float(edge_coordinates[0, 2] - edge_coordinates[1, 2])) <= 1e-9
        ):
            continue
        xi = _grid_index(axes["x"], float(edge_coordinates[0, 0]))
        zi = _grid_index(axes["z"], float(edge_coordinates[0, 2]))
        y0 = min(float(edge_coordinates[0, 1]), float(edge_coordinates[1, 1]))
        y1 = max(float(edge_coordinates[0, 1]), float(edge_coordinates[1, 1]))
        yi = _grid_index(axes["y"], y0)
        yi1 = _grid_index(axes["y"], y1)
        if (
            xi is None
            or zi is None
            or yi is None
            or yi1 != yi + 1
            or not 0 < xi < len(axes["x"]) - 1
            or not 0 < zi < len(axes["z"]) - 1
        ):
            continue
        incident = np.asarray(edge_to_cell.links(edge), dtype=np.int32)
        if len(incident) == 0:
            continue
        witness_cell = int(np.min(incident))
        local_edges = np.asarray(cell_to_edge.links(witness_cell), dtype=np.int32)
        local_matches = np.flatnonzero(local_edges == edge)
        if len(local_matches) != 1:
            continue
        local_edge = int(local_matches[0])
        positions = edge_positions_by_local_entity[local_edge]
        local_rows = np.asarray(cell_dofmap.cell_dofs(witness_cell), dtype=np.int32)
        global_rows = np.asarray(index_map.local_to_global(local_rows[positions]), dtype=np.int64)
        if len(np.unique(global_rows)) != 6:
            continue
        transform, transform_state = _physical_entity_transform(
            edge_coordinates, 1, degree, 1e-9
        )
        candidates.setdefault((xi, zi), {})[yi] = {
            "edge": int(edge),
            "cell": witness_cell,
            "rows": global_rows,
            "coordinates": edge_coordinates,
            "transform": transform,
            "transform_state": transform_state,
            "incident": tuple(sorted(map(int, incident))),
        }

    slave_local = np.asarray(mpc.slaves, dtype=np.int32).reshape(-1)
    slave_global = np.asarray(index_map.local_to_global(slave_local), dtype=np.int64).reshape(-1)
    if len(np.unique(slave_global)) != len(slave_global):
        raise ValueError("finalized MPC contains duplicate global slave rows")
    all_slave_rows = set(map(int, slave_global))
    selected_orbit: dict[int, dict[str, Any]] | None = None
    selected_base: tuple[int, int] | None = None
    for base in sorted(candidates):
        orbit = candidates[base]
        if set(orbit) != set(range(8)):
            continue
        rows = np.concatenate([orbit[index]["rows"] for index in range(8)])
        if len(np.unique(rows)) != 48 or any(int(row) in all_slave_rows for row in rows):
            continue
        selected_base, selected_orbit = base, orbit
        break
    if selected_orbit is None or selected_base is None:
        raise ValueError(
            "no complete, independent interior x/z edge with eight y-orbit copies was found"
        )

    cells_by_orbit = {
        orbit: tuple(selected_orbit[orbit]["incident"]) for orbit in range(8)
    }
    panel_cells = sorted({cell for cells in cells_by_orbit.values() for cell in cells})
    cell_orbits: dict[int, int] = {}
    for orbit, cells in cells_by_orbit.items():
        for cell in cells:
            previous = cell_orbits.setdefault(int(cell), int(orbit))
            if previous != orbit:
                raise ValueError("one incident cell is assigned to two y edge-orbit rows")
    if len(panel_cells) != sum(len(cells) for cells in cells_by_orbit.values()):
        raise ValueError("selected edge orbit shares an incident cell unexpectedly")

    edge_rows_by_orbit = {
        orbit: np.asarray(selected_orbit[orbit]["rows"], dtype=np.int64)
        for orbit in range(8)
    }
    panel_rows = np.concatenate([edge_rows_by_orbit[orbit] for orbit in range(8)])
    panel_position = {int(row): position for position, row in enumerate(panel_rows)}
    if len(panel_position) != 48:
        raise RuntimeError("selected V24 edge orbit does not own 48 unique global rows")

    cell_local: dict[
        int,
        tuple[
            np.ndarray,
            np.ndarray,
            np.ndarray,
            tuple[Any, ...],
            tuple[float, float, float],
        ],
    ] = {}
    raw_class_keys: set[tuple[Any, ...]] = set()
    oriented_class_keys: set[tuple[Any, ...]] = set()
    for cell in panel_cells:
        local_rows = np.asarray(cell_dofmap.cell_dofs(cell), dtype=np.int32)
        if len(local_rows) != 882:
            raise ValueError(f"incident cell {cell} does not have 882 actual p6 rows")
        global_rows = np.asarray(index_map.local_to_global(local_rows), dtype=np.int64)
        local_edges = np.asarray(cell_to_edge.links(cell), dtype=np.int32)
        matching = np.flatnonzero(local_edges == int(selected_orbit[cell_orbits[cell]]["edge"]))
        if len(matching) != 1:
            raise ValueError("incident-cell edge incidence does not close")
        edge_positions = edge_positions_by_local_entity[int(matching[0])]
        if not np.array_equal(
            np.sort(global_rows[edge_positions]),
            np.sort(edge_rows_by_orbit[cell_orbits[cell]]),
        ):
            raise ValueError("incident-cell edge rows do not match the canonical orbit member")
        raw_coordinates, widths = _canonical_axis_aligned_coordinates(
            mesh, cell, tolerance=1e-11, preserve_exact_geometry=True
        )
        tag = int(tags[cell])
        raw_key = (tag, *widths)
        permutation = int(cell_permutations[cell])
        oriented_key = (*raw_key, permutation)
        raw_class_keys.add(raw_key)
        oriented_class_keys.add(oriented_key)
        cell_local[cell] = (
            local_rows,
            global_rows,
            edge_positions,
            raw_key,
            widths,
        )

    interior_positions = np.asarray(
        function_space.element.basix_element.entity_dofs[3][0], dtype=np.int32
    )
    trace_positions = np.setdiff1d(
        np.arange(882, dtype=np.int32), interior_positions, assume_unique=True
    )
    if len(interior_positions) != 450 or len(trace_positions) != 432:
        raise ValueError("actual p6 local 450/432 interior/trace split changed")

    touched_global_rows = np.unique(
        np.concatenate([cell_local[cell][1] for cell in panel_cells])
    )
    from src.solvers.task40_v22_operator_probe import _global_mpc_expansions

    mpc_rows = _global_mpc_expansions(mpc, index_map, touched_global_rows)
    if any(
        int(master) in all_slave_rows
        for masters, _coefficients in mpc_rows.values()
        for master in masters
    ):
        raise NotImplementedError("V24 panel does not accept chained finalized MPC rows")

    trace_expansion_by_cell: dict[
        int, tuple[np.ndarray, sparse.csr_matrix, int]
    ] = {}
    active_column_union: set[int] = set()
    for cell in panel_cells:
        trace_global = cell_local[cell][1][trace_positions]
        active_ids, expansion, slave_count = _local_trace_expansion(
            trace_global,
            mpc_rows,
            index_dtype=np.dtype(PETSc.IntType),
        )
        trace_expansion_by_cell[cell] = (active_ids, expansion, slave_count)
        active_column_union.update(map(int, active_ids))
    panel_column_rows = np.asarray(sorted(active_column_union), dtype=np.int64)
    if panel_column_rows.size == 0:
        raise ValueError("V24 edge panel has no active trace columns after MPC expansion")
    panel_column_position = {
        int(row): position for position, row in enumerate(panel_column_rows)
    }

    # Admit the complete 48-by-all-touched-master row block, not only the
    # 48-by-48 edge self-coupling diagnostic.  The class formulas cover the
    # 882-row kernel, orientation, LU, Schur, and local workspace; the added
    # term reserves panel/MPC/CSR owners and bounded Python metadata.
    class_facts = assembly_time_condensation_capacity_facts(
        dimension=882,
        interior_dimension=450,
        trace_dimension=432,
        raw_class_count=len(raw_class_keys),
        oriented_class_count=len(oriented_class_keys),
        identity_class_count=1,
        retain_local_schur=True,
        scalar_bytes=np.dtype(np.complex128).itemsize,
        index_bytes=np.dtype(PETSc.IntType).itemsize,
        real_bytes=np.dtype(np.float64).itemsize,
    )
    full_row_block_bytes = 48 * int(panel_column_rows.size) * np.dtype(np.complex128).itemsize
    additional_bytes = int(
        class_facts["workspace_bytes_upper"]
        + class_facts["retained_numeric_bytes_upper"]
        + len(oriented_class_keys)
        * (
            450 * 450
            + 2 * 450 * 432
            + 432 * 432
        )
        * np.dtype(np.complex128).itemsize
        + full_row_block_bytes
        + 512 * 2**20
        + len(panel_cells) * (882 * 8 + 432 * 64)
    )
    admission = dict(
        resource_admission("v24_real_edge_orbit_full_trace_row_block", additional_bytes)
    )
    resource_samples = [
        {"label": "after_full_row_block_admission", **dict(resource_sample())}
    ]

    kernels = _cell_integral_kernels(
        compiled_form, sum_duplicate_cell_integrals=True
    )
    raw_cache: dict[tuple[Any, ...], np.ndarray] = {}
    schur_cache: dict[tuple[Any, ...], np.ndarray] = {}
    local_lu_audits: dict[str, dict[str, float | int]] = {}
    local_witness_audits: dict[str, dict[str, Any]] = {}
    local_witness_arrays: dict[str, np.ndarray] = {}
    cell_projection_records: list[dict[str, Any]] = []
    cell_projection_arrays: dict[str, np.ndarray] = {}
    native_panel = np.zeros((48, len(panel_column_rows)), dtype=np.complex128)
    kernel_seconds = 0.0
    local_schur_seconds = 0.0
    projection_seconds = 0.0
    max_expansion_columns = 0
    mpc_slave_occurrences = 0
    projected_cell_count_by_orbit = [0] * 8

    for cell in panel_cells:
        _local, global_rows, _edge_positions, raw_key, widths = cell_local[cell]
        oriented_key = (*raw_key, int(cell_permutations[cell]))
        schur = schur_cache.get(oriented_key)
        if schur is None:
            raw_tensor = raw_cache.get(raw_key)
            if raw_tensor is None:
                raw_started = time.perf_counter()
                raw_coordinates, _ = _canonical_axis_aligned_coordinates(
                    mesh, cell, tolerance=1e-11, preserve_exact_geometry=True
                )
                raw_tensor = _tabulate_raw_tensor_class(
                    compiled_form,
                    kernels,
                    raw_coordinates,
                    tag=int(raw_key[0]),
                    dimension=882,
                )
                raw_cache[raw_key] = raw_tensor
                kernel_seconds += time.perf_counter() - raw_started
            oriented = raw_tensor.copy()
            _orient_cell_tensor(
                function_space.element,
                oriented,
                cell_permutations[cell : cell + 1],
            )
            A_ii = oriented[np.ix_(interior_positions, interior_positions)]
            A_it = oriented[np.ix_(interior_positions, trace_positions)]
            A_ti = oriented[np.ix_(trace_positions, interior_positions)]
            A_tt = oriented[np.ix_(trace_positions, trace_positions)]
            local_started = time.perf_counter()
            (lu, pivots), lu_relative = _strict_local_lu(A_ii)
            inverse_cross = -lu_solve((lu, pivots), A_it)
            schur = A_tt + A_ti @ inverse_cross
            witness_index_i = np.arange(450, dtype=np.float64)
            witness_index_t = np.arange(432, dtype=np.float64)
            x_i_true = (
                0.25
                + np.sin(0.017 * (witness_index_i + 1.0))
                + 1j * (0.125 + np.cos(0.013 * (witness_index_i + 2.0)))
            ).astype(np.complex128)
            x_t_true = (
                0.2
                + np.cos(0.019 * (witness_index_t + 1.0))
                + 1j * (0.1 + np.sin(0.011 * (witness_index_t + 3.0)))
            ).astype(np.complex128)
            b_i = A_ii @ x_i_true + A_it @ x_t_true
            b_t = A_ti @ x_i_true + A_tt @ x_t_true
            full_rhs_norm = float(
                np.hypot(np.linalg.norm(b_i), np.linalg.norm(b_t))
            )

            def witness_metrics(
                x_i_state: np.ndarray, solve_b_state: np.ndarray
            ) -> dict[str, Any]:
                interior_residual = A_ii @ x_i_state + A_it @ x_t_true - b_i
                trace_residual = A_ti @ x_i_state + A_tt @ x_t_true - b_t
                equation_relative = float(
                    np.hypot(
                        np.linalg.norm(interior_residual),
                        np.linalg.norm(trace_residual),
                    )
                    / max(full_rhs_norm, np.finfo(np.float64).tiny)
                )
                forward_relative = float(
                    np.linalg.norm(x_i_state - x_i_true)
                    / max(float(np.linalg.norm(x_i_true)), np.finfo(np.float64).tiny)
                )
                rhs_condensed_state = b_t - A_ti @ solve_b_state
                condensed_residual = schur @ x_t_true - rhs_condensed_state
                condensed_relative = float(
                    np.linalg.norm(condensed_residual)
                    / max(
                        float(np.linalg.norm(rhs_condensed_state)),
                        np.finfo(np.float64).tiny,
                    )
                )
                return {
                    "full_equation_residual_relative": equation_relative,
                    "recovered_interior_forward_relative": forward_relative,
                    "condensed_trace_residual_relative": condensed_relative,
                    "interior_residual_norm": float(np.linalg.norm(interior_residual)),
                    "trace_residual_norm": float(np.linalg.norm(trace_residual)),
                    "condensed_trace_residual_norm": float(
                        np.linalg.norm(condensed_residual)
                    ),
                }

            def witness_passes(metrics: Mapping[str, Any]) -> bool:
                values = (
                    float(metrics["full_equation_residual_relative"]),
                    float(metrics["recovered_interior_forward_relative"]),
                    float(metrics["condensed_trace_residual_relative"]),
                )
                return bool(
                    np.isfinite(values).all()
                    and values[0] <= 1e-10
                    and values[1] <= 1e-11
                    and values[2] <= 1e-10
                )

            x_i_recovered_initial = lu_solve(
                (lu, pivots), b_i - A_it @ x_t_true
            )
            solve_b_initial = lu_solve((lu, pivots), b_i)
            x_i_recovered = np.asarray(x_i_recovered_initial).copy()
            solve_b = np.asarray(solve_b_initial).copy()
            initial_metrics = witness_metrics(x_i_recovered, solve_b)
            refinement_history: list[dict[str, Any]] = [
                {"state": "initial", **initial_metrics}
            ]
            refinement_states: dict[str, np.ndarray] = {}
            refinement_corrections = 0
            for correction_index in range(1, 4):
                if witness_passes(witness_metrics(x_i_recovered, solve_b)):
                    break
                if not (
                    np.isfinite(x_i_recovered).all()
                    and np.isfinite(solve_b).all()
                ):
                    break
                residual_i = b_i - (A_ii @ x_i_recovered + A_it @ x_t_true)
                residual_b = b_i - A_ii @ solve_b
                correction_i = lu_solve((lu, pivots), residual_i)
                correction_b = lu_solve((lu, pivots), residual_b)
                if not (
                    np.isfinite(correction_i).all()
                    and np.isfinite(correction_b).all()
                ):
                    state_prefix = f"refinement_{correction_index:03d}_nonfinite"
                    refinement_states[f"{state_prefix}_correction_i"] = np.asarray(
                        correction_i
                    ).copy()
                    refinement_states[f"{state_prefix}_correction_b"] = np.asarray(
                        correction_b
                    ).copy()
                    refinement_history.append(
                        {
                            "state": state_prefix,
                            "correction_applied": False,
                            "correction_finite": False,
                            "interior_residual_before_correction_norm": float(
                                np.linalg.norm(residual_i)
                            ),
                            "original_b_residual_before_correction_norm": float(
                                np.linalg.norm(residual_b)
                            ),
                        }
                    )
                    break
                x_i_recovered += correction_i
                solve_b += correction_b
                refinement_corrections += 1
                state_prefix = f"refinement_{correction_index:03d}"
                refinement_states[f"{state_prefix}_x_i_recovered"] = x_i_recovered.copy()
                refinement_states[f"{state_prefix}_solve_b"] = solve_b.copy()
                post_metrics = witness_metrics(x_i_recovered, solve_b)
                refinement_history.append(
                    {
                        "state": state_prefix,
                        "interior_residual_before_correction_norm": float(
                            np.linalg.norm(residual_i)
                        ),
                        "original_b_residual_before_correction_norm": float(
                            np.linalg.norm(residual_b)
                        ),
                        "interior_correction_norm": float(np.linalg.norm(correction_i)),
                        "original_b_correction_norm": float(np.linalg.norm(correction_b)),
                        **post_metrics,
                    }
                )
            selected_metrics = witness_metrics(x_i_recovered, solve_b)
            rhs_condensed = b_t - A_ti @ solve_b
            oriented_key_id = repr(oriented_key)
            witness_prefix = f"local_witness_{len(local_witness_audits):03d}"
            witness_audit = {
                "payload_prefix": witness_prefix,
                "nonzero_interior_rhs_norm": float(np.linalg.norm(b_i)),
                "full_rhs_norm": full_rhs_norm,
                "full_equation_residual_relative": float(
                    selected_metrics["full_equation_residual_relative"]
                ),
                "recovered_interior_forward_relative": float(
                    selected_metrics["recovered_interior_forward_relative"]
                ),
                "condensed_trace_residual_relative": float(
                    selected_metrics["condensed_trace_residual_relative"]
                ),
                "initial_full_equation_residual_relative": float(
                    initial_metrics["full_equation_residual_relative"]
                ),
                "initial_recovered_interior_forward_relative": float(
                    initial_metrics["recovered_interior_forward_relative"]
                ),
                "initial_condensed_trace_residual_relative": float(
                    initial_metrics["condensed_trace_residual_relative"]
                ),
                "initial_state_passed": witness_passes(initial_metrics),
                "refinement_correction_count": refinement_corrections,
                "refinement_history": refinement_history,
                "full_equation_relative_limit": 1e-10,
                "recovered_interior_forward_limit": 1e-11,
                "condensed_trace_relative_limit": 1e-10,
                "native_local_rows": 882,
                "interior_rows": 450,
                "trace_rows": 432,
                "same_lu_fresh_factorizations": 1,
                "same_lu_refinement_corrections": refinement_corrections,
                "same_lu_max_refinement_corrections": 3,
            }
            witness_payload = {
                f"{witness_prefix}_{name}": np.asarray(value, dtype=np.complex128)
                for name, value in (
                    ("A_ii", A_ii),
                    ("A_it", A_it),
                    ("A_ti", A_ti),
                    ("A_tt", A_tt),
                    ("schur", schur),
                    ("x_i_true", x_i_true),
                    ("x_t_true", x_t_true),
                    ("b_i", b_i),
                    ("b_t", b_t),
                    ("x_i_recovered_initial", x_i_recovered_initial),
                    ("solve_b_initial", solve_b_initial),
                    ("x_i_recovered", x_i_recovered),
                    ("solve_b_selected", solve_b),
                    ("rhs_condensed", rhs_condensed),
                )
            }
            witness_payload.update(
                {
                    f"{witness_prefix}_{name}": np.asarray(
                        value, dtype=np.complex128
                    )
                    for name, value in refinement_states.items()
                }
            )
            if (
                float(np.linalg.norm(b_i)) <= 0.0
                or not witness_passes(selected_metrics)
            ):
                witness_audit["status"] = "FAILED_LOCAL_EQUATION_CONDENSE_RECOVER_WITNESS"
                raise LocalEquationWitnessFailure(
                    "V24 local equation/condense/recover witness exceeded its residual gate "
                    f"for class {oriented_key_id} after {refinement_corrections} "
                    f"same-LU corrections: {selected_metrics}",
                    oriented_class=oriented_key_id,
                    audit=witness_audit,
                    payload=witness_payload,
                )
            witness_audit["status"] = "PASS_LOCAL_EQUATION_CONDENSE_RECOVER_WITNESS"
            equation_relative = float(
                selected_metrics["full_equation_residual_relative"]
            )
            forward_relative = float(
                selected_metrics["recovered_interior_forward_relative"]
            )
            condensed_relative = float(
                selected_metrics["condensed_trace_residual_relative"]
            )
            local_schur_seconds += time.perf_counter() - local_started
            if not np.isfinite(schur).all():
                raise FloatingPointError(
                    "V24 local condensed edge panel contains non-finite values"
                )
            schur_cache[oriented_key] = np.ascontiguousarray(schur)
            oriented_key_id = repr(oriented_key)
            local_lu_audits[oriented_key_id] = {
                "fresh_factorizations": 1,
                "reuse_count": 0,
                "relative_identity_defect": float(lu_relative),
                "iterative_refinement_corrections": refinement_corrections,
                "maximum_iterative_refinement_corrections_allowed": 3,
            }
            local_witness_audits[oriented_key_id] = witness_audit
            local_witness_arrays.update(witness_payload)
            del oriented, A_ii, A_it, A_ti, A_tt, inverse_cross, lu, pivots
        else:
            local_lu_audits[repr(oriented_key)]["reuse_count"] = int(
                local_lu_audits[repr(oriented_key)]["reuse_count"]
            ) + 1

        orbit = cell_orbits[cell]
        trace_global = global_rows[trace_positions]
        if len(trace_global) != 432:
            raise RuntimeError("V24 panel dropped local trace columns before MPC projection")
        active_ids, expansion_sparse, slave_count = trace_expansion_by_cell[cell]
        mpc_slave_occurrences += slave_count
        max_expansion_columns = max(max_expansion_columns, len(active_ids))
        selected_edge_ids = edge_rows_by_orbit[orbit]
        active_positions = np.searchsorted(active_ids, selected_edge_ids)
        if np.any(active_positions >= len(active_ids)) or not np.array_equal(
            active_ids[active_positions], selected_edge_ids
        ):
            raise ValueError("selected edge row is not represented in its incident MPC expansion")
        expansion = expansion_sparse.toarray()
        selected_expansion = expansion[:, active_positions]
        projection_started = time.perf_counter()
        # All native trace columns remain present in the right expansion.
        # Only the six selected edge rows are restricted on the left.
        projected = selected_expansion.conjugate().T @ schur @ expansion
        projection_seconds += time.perf_counter() - projection_started
        if projected.shape != (6, len(active_ids)) or not np.isfinite(projected).all():
            raise FloatingPointError("V24 projected edge-cell Schur block is invalid")
        positions = np.asarray(
            [panel_position[int(row)] for row in selected_edge_ids], dtype=np.int64
        )
        column_positions = np.asarray(
            [panel_column_position[int(row)] for row in active_ids], dtype=np.int64
        )
        native_panel[np.ix_(positions, column_positions)] += projected
        record_prefix = f"cell_projection_{len(cell_projection_records):03d}"
        witness_prefix = str(
            local_witness_audits[repr(oriented_key)]["payload_prefix"]
        )
        record_array_keys = {
            "trace_global_rows": f"{record_prefix}_trace_global_rows",
            "active_global_rows": f"{record_prefix}_active_global_rows",
            "expansion_data": f"{record_prefix}_expansion_data",
            "expansion_indices": f"{record_prefix}_expansion_indices",
            "expansion_indptr": f"{record_prefix}_expansion_indptr",
        }
        cell_projection_arrays.update(
            {
                record_array_keys["trace_global_rows"]: np.array(
                    trace_global, dtype=np.int64, copy=True
                ),
                record_array_keys["active_global_rows"]: np.array(
                    active_ids, dtype=np.int64, copy=True
                ),
                record_array_keys["expansion_data"]: np.array(
                    expansion_sparse.data, dtype=np.complex128, copy=True
                ),
                record_array_keys["expansion_indices"]: np.array(
                    expansion_sparse.indices, copy=True
                ),
                record_array_keys["expansion_indptr"]: np.array(
                    expansion_sparse.indptr, copy=True
                ),
            }
        )
        cell_projection_records.append(
            {
                "record_prefix": record_prefix,
                "cell_id": int(cell),
                "orbit_index": int(orbit),
                "oriented_class_key": repr(oriented_key),
                "schur_payload_key": f"{witness_prefix}_schur",
                "trace_global_rows_payload_key": record_array_keys[
                    "trace_global_rows"
                ],
                "active_global_rows_payload_key": record_array_keys[
                    "active_global_rows"
                ],
                "expansion_data_payload_key": record_array_keys["expansion_data"],
                "expansion_indices_payload_key": record_array_keys[
                    "expansion_indices"
                ],
                "expansion_indptr_payload_key": record_array_keys[
                    "expansion_indptr"
                ],
                "expansion_shape": [432, int(len(active_ids))],
                "expansion_nnz": int(expansion_sparse.nnz),
                "selected_edge_global_rows": selected_edge_ids.tolist(),
                "selected_edge_expansion_columns": active_positions.tolist(),
                "panel_row_positions": positions.tolist(),
                "panel_column_positions": column_positions.tolist(),
                "finalized_mpc_slave_rows_in_trace": int(slave_count),
            }
        )
        projected_cell_count_by_orbit[orbit] += 1

    expected_cells = [len(cells_by_orbit[index]) for index in range(8)]
    if projected_cell_count_by_orbit != expected_cells:
        raise RuntimeError("V24 edge panel did not accumulate every incident cell exactly once")

    edge_transforms = np.stack(
        [selected_orbit[orbit]["transform"] for orbit in range(8)], axis=0
    )
    dft = np.exp(
        1j
        * np.arange(8)[:, None]
        * (
            float(complex(cfg.ky).real) * float(cfg.period_y)
            + 2.0 * np.pi * np.arange(8)
        )[None, :]
        / 8.0
    ) / np.sqrt(8.0)
    dft_edge = np.kron(dft, np.eye(6, dtype=np.complex128))
    entity_map = np.zeros((48, 48), dtype=np.complex128)
    for orbit, transform in enumerate(edge_transforms):
        first = 6 * orbit
        entity_map[first : first + 6, first : first + 6] = transform

    edge_column_positions = np.asarray(
        [panel_column_position[int(row)] for row in panel_rows], dtype=np.int64
    )
    edge_self_native = native_panel[:, edge_column_positions]
    edge_self_canonical, edge_self_q_panel, _dft_check = project_edge_orbit_panel(
        edge_self_native,
        edge_transforms,
        ky=float(complex(cfg.ky).real),
        period_y=float(cfg.period_y),
    )
    if not np.allclose(_dft_check, dft, rtol=0.0, atol=0.0):
        raise RuntimeError("V24 edge self-panel DFT changed within one assembly")
    canonical_row_block = entity_map.conjugate().T @ native_panel
    q_row_panel = dft_edge.conjugate().T @ canonical_row_block

    column_count = len(panel_column_rows)
    row_basis = entity_map @ dft_edge
    v17_gate_events: list[dict[str, Any]] = []

    def v17_allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
        v17_gate_events.append({"label": str(label), **dict(facts)})

    v17_blocks, v17_csr_facts = _assemble_v17_edge_row_blocks(
        native_panel,
        edge_column_positions=edge_column_positions,
        row_basis=row_basis,
        index_dtype=np.dtype(PETSc.IntType),
        allocation_gate=v17_allocation_gate,
        resource_admission=resource_admission,
    )
    v17_csr_facts["gate_event_count"] = len(v17_gate_events)
    resource_samples.append(
        {"label": "after_panel_assembly", **dict(resource_sample())}
    )

    volume_port_rows = np.asarray(
        [row for rows in edge_rows_by_orbit.values() for row in rows], dtype=np.int64
    )
    status = "PASS_V24_REAL_EDGE_ORBIT_Q_PANEL"
    return {
        "schema": "task40extra.review_v24_real_edge_orbit_volume_panel.v1",
        "status": status,
        "official_result": False,
        "full_q_matrix": False,
        "full_volume_action": False,
        "pde_solved": False,
        "factor_created": False,
        "ksp_created": False,
        "q_coverage": (
            "0/8 full q matrices; complete 48-by-all-touched-active-trace q-row "
            "block plus a measured 48x48 edge self q-by-r diagnostic; "
            "non-edge q-column projection not run"
        ),
        "selected_entity": {
            "kind": "edge",
            "edge_axis": "y",
            "base_grid_indices_x_z": list(selected_base),
            "rows_per_orbit": 6,
            "orbit_count": 8,
            "global_edge_ids_by_orbit": [
                int(selected_orbit[index]["edge"]) for index in range(8)
            ],
            "global_rows_by_orbit": [edge_rows_by_orbit[index].tolist() for index in range(8)],
            "transform_state_by_orbit": [
                list(selected_orbit[index]["transform_state"]) for index in range(8)
            ],
            "global_rows_sha256": _array_sha256(volume_port_rows),
        },
        "incident_cells": {
            "cell_count": len(panel_cells),
            "cells_by_orbit": {str(key): list(value) for key, value in cells_by_orbit.items()},
            "projected_cell_count_by_orbit": projected_cell_count_by_orbit,
            "all_incident_cells_included_exactly_once": True,
            "cell_dofs_per_cell": 882,
            "interior_rows_per_cell": 450,
            "trace_rows_per_cell": 432,
            "complete_432_trace_rows_retained_before_projection": True,
            "complete_active_trace_columns_accumulated": True,
            "active_trace_column_count": int(column_count),
            "active_trace_column_rows_sha256": _array_sha256(panel_column_rows),
        },
        "cell_mpc_projection_records": cell_projection_records,
        "geometry_and_integrals": {
            "preserve_exact_geometry": True,
            "geometry_widths_by_cell": {
                str(cell): list(cell_local[cell][4]) for cell in panel_cells
            },
            "sum_duplicate_cell_integrals": True,
            "local_cell_kernel_rule": (
                "all default and matching tagged FFCx curl+mass cell kernels summed"
            ),
            "actual_cell_orientation_applied": True,
            "raw_class_count_in_panel": len(raw_cache),
            "oriented_schur_class_count_in_panel": len(schur_cache),
        },
        "mpc_projection": {
            "finalized_mpc_rows_applied": True,
            "unique_slave_rows_in_touched_cells": len(mpc_rows),
            "slave_row_occurrences_in_local_trace": mpc_slave_occurrences,
            "maximum_local_active_columns": max_expansion_columns,
            "selected_edge_rows_are_independent": True,
            "chained_mpc_rows": False,
        },
        "local_lu": {
            "fresh_factorization_count": sum(
                int(row["fresh_factorizations"]) for row in local_lu_audits.values()
            ),
            "oriented_classes": local_lu_audits,
            "maximum_fresh_factorizations_per_class": max(
                (int(row["fresh_factorizations"]) for row in local_lu_audits.values()),
                default=0,
            ),
            "maximum_iterative_refinement_corrections_per_class": max(
                (
                    int(row["iterative_refinement_corrections"])
                    for row in local_lu_audits.values()
                ),
                default=0,
            ),
            "same_lu_max_iterative_refinement_corrections": 3,
            "maximum_identity_relative_defect": max(
                (float(row["relative_identity_defect"]) for row in local_lu_audits.values()),
                default=0.0,
            ),
        },
        "local_equation_condense_recover_witnesses": local_witness_audits,
        "q_projection": {
            "convention": (
                "F[orbit,q]=exp(i*orbit*(ky*period_y+2*pi*q)/8)/sqrt(8); "
                "selected q rows use F_edge^H T_edge^H; q columns remain active "
                "global rows except in the edge self-subpanel"
            ),
            "q_indices": list(range(8)),
            "full_q_row_block_shape": list(v17_blocks[(0, 1)].shape),
            "full_q_row_block_columns_are_native_active_rows": True,
            "full_q_column_projection": "NOT_RUN_FOR_NON_EDGE_COLUMNS",
            "edge_self_subpanel_diagonal_block_frobenius_norms": [
                float(np.linalg.norm(edge_self_q_panel[6 * q : 6 * q + 6, 6 * q : 6 * q + 6]))
                for q in range(8)
            ],
            "edge_self_subpanel_off_diagonal_block_frobenius_norms": [
                [
                    float(np.linalg.norm(edge_self_q_panel[6 * q : 6 * q + 6, 6 * r : 6 * r + 6]))
                    for r in range(8)
                ]
                for q in range(8)
            ],
            "edge_self_subpanel_maximum_off_diagonal_block_norm": max(
                (
                    float(np.linalg.norm(edge_self_q_panel[6 * q : 6 * q + 6, 6 * r : 6 * r + 6]))
                    for q in range(8)
                    for r in range(8)
                    if q != r
                ),
                default=0.0,
            ),
            "edge_self_subpanel_maximum_diagonal_block_norm": max(
                (
                    float(
                        np.linalg.norm(
                            edge_self_q_panel[
                                6 * q : 6 * q + 6, 6 * q : 6 * q + 6
                            ]
                        )
                    )
                    for q in range(8)
                ),
                default=0.0,
            ),
            "actual_q_offdiagonal_evaluated": True,
            "q_offdiagonal_assumed_zero": False,
            "edge_self_q_panel_source": (
                "V17 CSR block 00, independently matched to direct 48x48 projection"
            ),
        },
        "v17_row_tile_csr": v17_csr_facts,
        "C_minus_D_H_coverage": {
            "source": (
                "hash-bound completed V24 C receipt; independently read back "
                "by the existing partial checker"
            ),
            "volume_panel_is_S_only": True,
            "C_minus_D_H_recomputed_in_D": False,
        },
        "capacity": {
            "status": "PANEL_ADMITTED",
            "admission": admission,
            "class_capacity_facts": class_facts,
            "additional_object_upper_bound_bytes": additional_bytes,
            "full_row_block_payload_bytes": int(full_row_block_bytes),
        },
        "resource_samples": resource_samples,
        "timing_seconds": {
            "raw_kernel_generation": float(kernel_seconds),
            "local_lu_and_schur": float(local_schur_seconds),
            "mpc_projection_and_accumulation": float(projection_seconds),
            "total_wall": float(time.perf_counter() - started),
            "total_process_cpu": float(time.process_time() - cpu_started),
        },
        "payload": {
            "native_panel": native_panel,
            "canonical_row_panel": canonical_row_block,
            "q_row_panel": q_row_panel,
            "edge_self_native_panel": edge_self_native,
            "edge_self_canonical_panel": edge_self_canonical,
            "edge_self_q_panel": edge_self_q_panel,
            "edge_transforms": edge_transforms,
            "entity_map": entity_map,
            "dft": dft,
            "dft_edge": dft_edge,
            "column_global_rows": panel_column_rows,
            "q_row_csr_data": v17_blocks[(0, 1)].data,
            "q_row_csr_indices": v17_blocks[(0, 1)].indices,
            "q_row_csr_indptr": v17_blocks[(0, 1)].indptr,
            "q_edge_csr_data": v17_blocks[(0, 0)].data,
            "q_edge_csr_indices": v17_blocks[(0, 0)].indices,
            "q_edge_csr_indptr": v17_blocks[(0, 0)].indptr,
            **cell_projection_arrays,
            **local_witness_arrays,
        },
        "payload_hashes": {
            "native_panel_sha256": _array_sha256(native_panel),
            "canonical_row_panel_sha256": _array_sha256(canonical_row_block),
            "q_row_panel_sha256": _array_sha256(q_row_panel),
            "edge_self_q_panel_sha256": _array_sha256(edge_self_q_panel),
            "entity_map_sha256": _array_sha256(entity_map),
            "dft_sha256": _array_sha256(dft),
            "column_global_rows_sha256": _array_sha256(panel_column_rows),
            "local_equation_witness_payloads_sha256": {
                name: _array_sha256(array)
                for name, array in local_witness_arrays.items()
            },
            "cell_mpc_projection_payloads_sha256": {
                name: _array_sha256(array)
                for name, array in cell_projection_arrays.items()
            },
        },
    }


def write_panel_payload(output_directory: Path, panel: dict[str, Any]) -> dict[str, Any]:
    """Persist raw and derived edge panels with independent-readback hashes."""

    output_directory = Path(output_directory)
    payload_path = output_directory / "v24_real_edge_volume_panel.npz"
    if payload_path.exists():
        raise FileExistsError(payload_path)
    payload = panel.pop("payload")
    with payload_path.open("xb") as stream:
        np.savez(stream, **payload)
        stream.flush()
        os.fsync(stream.fileno())
    panel["payload_file"] = payload_path.name
    panel["payload_sha256"] = _file_sha256(payload_path)
    panel["payload_hashes"]["payload_file_sha256"] = panel["payload_sha256"]
    return panel
