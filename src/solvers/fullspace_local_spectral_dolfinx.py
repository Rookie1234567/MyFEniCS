"""Real hexahedral cell adapter for the bounded N1 local spectral core.

This module is deliberately narrower than the later distributed production
path.  It builds the p2/p3 serial smoke fixture directly from affine Basix
cell tensors, DOLFINx cell orientation, and finalized Floquet MPC expansion.
It never obtains a local block from a global assembled matrix.  Dense cell
arrays exist only while one smoke patch is being constructed and are released
by :class:`~src.solvers.fullspace_local_spectral.LocalSpectralPatch`.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
from dolfinx import fem, la
from mpi4py import MPI

from ..geometry.tetra_mesh_audit import canonical_entity_key, mesh_coordinate_tolerance
from .hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from .hcurl_canonical_vector import canonical_key
from .hcurl_canonical_vector_dolfinx import (
    _entity_coordinates,
    _physical_entity_transform,
)
from .fullspace_local_spectral import (
    ExactClassOwnerPlan,
    LocalSpectralPatch,
    N1_LEVELS,
    N1_MODE_CAP,
    N1_REGIONAL_RANK,
    N1_TOP_RANK,
    build_owner_local_multilevel_basis,
    build_regional_rayleigh_ritz,
    canonical_vector_digest,
    deterministic_row_owner,
    map_mode_template_to_patch,
    top_mixing_coefficient,
)


_MATRIX_TOL = 1.0e-12
_SMOKE_MAX_ROWS = 882
_REGIONAL_CELL_BLOCK = 2


def _pair(value: complex) -> list[float]:
    scalar = complex(value)
    return [
        0.0 if scalar.real == 0.0 else float(scalar.real),
        0.0 if scalar.imag == 0.0 else float(scalar.imag),
    ]


def _canonical_expansion_coefficient(
    value: complex, floquet_phases: tuple[complex, ...] = ()
) -> complex:
    """Normalize only the mathematically signed unit orientation coefficient."""

    scalar = complex(value)
    for phase in floquet_phases:
        phase = complex(phase)
        for sign in (1.0, -1.0):
            if abs(scalar - sign * phase) <= _MATRIX_TOL:
                return sign * phase
    if (
        scalar.imag == 0.0
        and abs(abs(scalar.real) - 1.0) <= _MATRIX_TOL
    ):
        return complex(1.0 if scalar.real >= 0.0 else -1.0)
    return scalar


def _relative(values: np.ndarray, reference: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(values))
        / max(float(np.linalg.norm(np.asarray(reference))), 1.0e-300)
    )


def _hermitian_defect(matrix: np.ndarray) -> float:
    array = np.asarray(matrix, dtype=np.complex128)
    return _relative(array - array.conj().T, array)


def _orient_cell_tensor(element: Any, tensor: np.ndarray, cell_info: int) -> None:
    """Apply DOLFINx's cell coefficient transform to a local tensor."""

    info = np.asarray([int(cell_info)], dtype=np.uint32)
    dimension = int(tensor.shape[0])
    element.T_apply(tensor.ravel(), info, dimension)
    transpose = np.ascontiguousarray(tensor.T)
    element.T_apply(transpose.ravel(), info, dimension)
    tensor[:] = transpose.T


def _monomial_columns(
    transform: np.ndarray, *, label: str, positions: np.ndarray | None = None
) -> dict[int, tuple[int, complex]]:
    """Map stored rows to canonical columns for a monomial block."""

    array = np.asarray(transform, dtype=np.complex128)
    result: dict[int, tuple[int, complex]] = {}
    for row in range(array.shape[0]):
        column = int(np.argmax(np.abs(array[row])))
        value = complex(array[row, column])
        if abs(value) <= _MATRIX_TOL or not np.allclose(
            np.delete(array[row], column), 0.0, rtol=0.0, atol=_MATRIX_TOL
        ):
            raise RuntimeError(
                f"{label} is not a signed/permuted H(curl) block; "
                f"row={row} max={abs(value)}"
            )
        result[row] = (column, value)
    if positions is not None and set(result) != set(int(v) for v in positions):
        raise RuntimeError(f"{label} does not cover the expected cell rows")
    return result


def _cell_interior_transform(
    element: Any, positions: np.ndarray, cell_info: int
) -> np.ndarray:
    """Return the stored-to-canonical matrix represented by ``Tt_apply``."""

    dimension = int(element.space_dimension)
    transform = np.zeros((dimension, dimension), dtype=np.complex128)
    info = np.asarray([int(cell_info)], dtype=np.uint32)
    for column in range(dimension):
        basis = np.zeros(dimension, dtype=np.complex128)
        basis[column] = 1.0
        element.Tt_apply(basis, info, 1)
        transform[:, column] = basis
    _monomial_columns(transform[np.ix_(positions, positions)], label="cell Tt_apply")
    return transform


def _field_component(function_space: Any, component: int) -> fem.Function:
    """Interpolate one fixed Cartesian H(curl) coordinate field."""

    field = fem.Function(function_space, name=f"coordinate_gradient_{component}")

    def value(x):
        result = np.zeros((3, x.shape[1]), dtype=np.complex128)
        result[int(component), :] = 1.0
        return result

    field.interpolate(value)
    field.x.scatter_forward()
    return field


def _mpc_expansion(
    local_dofs: np.ndarray,
    mpc: Any,
    slave_rows: set[int],
    raw_to_key: dict[int, Any],
    raw_to_scale: dict[int, complex],
) -> tuple[tuple[int, ...], tuple[tuple[tuple[int, complex], ...], ...], tuple[Any, ...]]:
    """Return the cell-to-free-row MPC expansion and deterministic pattern."""

    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    entries: list[tuple[tuple[int, complex], ...]] = []
    for raw in np.asarray(local_dofs, dtype=np.int32):
        row = int(raw)
        if row not in slave_rows:
            entries.append(((row, complex(raw_to_scale[row])),))
            continue
        masters = np.asarray(mpc.masters.links(row), dtype=np.int32)
        start, stop = int(offsets[row]), int(offsets[row + 1])
        values = coefficients[start:stop]
        if masters.size != values.size or not masters.size:
            raise RuntimeError(f"MPC row {row} has an invalid master expansion")
        if any(int(master) in slave_rows for master in masters):
            raise RuntimeError(f"chained MPC row {row} is not supported")
        entries.append(
            tuple(
                (
                    int(master),
                    complex(value) * complex(raw_to_scale[int(master)]),
                )
                for master, value in zip(masters, values, strict=True)
            )
        )

    free_rows = tuple(
        sorted(
            {row for entry in entries for row, _value in entry},
            key=lambda row: repr(raw_to_key[int(row)]),
        )
    )
    columns = {row: index for index, row in enumerate(free_rows)}
    sparse_pattern: list[tuple[tuple[int, complex], ...]] = []
    pattern: list[Any] = []
    for entry in entries:
        normalized = []
        for row, value in entry:
            normalized.append((int(columns[row]), _pair(value)))
        sparse_pattern.append(
            tuple((int(columns[row]), complex(value)) for row, value in entry)
        )
        pattern.append(tuple(normalized))
    return free_rows, tuple(sparse_pattern), tuple(pattern)


def _dense_expansion(
    sparse_pattern: tuple[tuple[tuple[int, complex], ...], ...],
    column_count: int,
) -> np.ndarray:
    """Materialize one cell's constrained expansion for the current pass."""

    expansion = np.zeros((len(sparse_pattern), int(column_count)), dtype=np.complex128)
    for row, entries in enumerate(sparse_pattern):
        for column, value in entries:
            expansion[row, int(column)] = complex(value)
    return expansion


def _relative_canonical_row_descriptor(key: Any, cell_origin: tuple[int, ...]) -> Any:
    """Remove the cell's absolute origin from one physical row key."""

    role, dimension, entity, basis, orientation, floquet_master, floquet_value = key
    relative_entity = tuple(
        tuple(
            int(coordinate) - int(cell_origin[axis])
            for axis, coordinate in enumerate(point)
        )
        for point in entity
    )
    return (
        role,
        int(dimension),
        relative_entity,
        int(basis),
        orientation,
        floquet_master,
        tuple(floquet_value),
    )


def _canonical_row_expansions(
    local_row_descriptors: tuple[Any, ...],
    free_row_descriptors: tuple[Any, ...],
    local_row_scales: tuple[complex, ...],
    sparse_pattern: tuple[tuple[tuple[int, complex], ...], ...],
    floquet_phases: tuple[complex, ...] = (),
) -> tuple[Any, ...]:
    """Pair canonical rows with their scale-adjusted canonical expansion."""

    rows = []
    for row_descriptor, row_scale, entries in zip(
        local_row_descriptors, local_row_scales, sparse_pattern, strict=True
    ):
        expansion = tuple(
            sorted(
                (
                    (
                        free_row_descriptors[int(column)],
                        _pair(
                            _canonical_expansion_coefficient(
                                complex(value) / complex(row_scale),
                                floquet_phases,
                            )
                        ),
                    )
                    for column, value in entries
                ),
                key=repr,
            )
        )
        rows.append((row_descriptor, expansion))
    return tuple(sorted(rows, key=repr))


def _class_digest(
    *,
    element: Any,
    cfg: Any,
    tag: int,
    widths: tuple[float, float, float],
    canonical_row_expansions: tuple[Any, ...],
) -> str:
    """Hash one cell class without absolute coordinates or raw row ids."""

    payload = {
        "schema": "task038.n1.cell-class.v2",
        "element_hash": int(element.hash()),
        "element_degree": int(element.degree),
        "cell_type": str(element.cell_type.name),
        "mu_r": _pair(1.0 / complex(cfg.mu_r)),
        "tag": int(tag),
        "widths": [float(value) for value in widths],
        "canonical_row_expansions": canonical_row_expansions,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _row_semantics(
    function_space: Any, mesh: Any
) -> tuple[dict[int, Any], dict[int, Any], dict[int, complex]]:
    """Build raw-row physical keys and local orientation signatures."""

    topology = mesh.topology
    tdim = int(topology.dim)
    index_map = topology.index_map(tdim)
    layout = function_space.dofmap.dof_layout
    element = function_space.element.basix_element
    dof_element = function_space.element
    degree = int(element.degree)
    tolerance = mesh_coordinate_tolerance(mesh)
    topology.create_entities(1)
    topology.create_entities(2)
    topology.create_connectivity(tdim, 0)
    topology.create_connectivity(tdim, 1)
    topology.create_connectivity(1, tdim)
    topology.create_connectivity(tdim, 2)
    topology.create_connectivity(2, tdim)
    topology.create_entity_permutations()
    cell_info = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    raw_to_key: dict[int, Any] = {}
    raw_to_signature: dict[int, Any] = {}
    raw_to_scale: dict[int, complex] = {}

    def record(row: int, key: Any, signature: Any, scale: complex) -> None:
        old = raw_to_key.get(int(row))
        if old is not None and old != key:
            raise RuntimeError(f"raw row {row} has inconsistent canonical keys")
        raw_to_key[int(row)] = key
        old_signature = raw_to_signature.get(int(row))
        if old_signature is not None and old_signature != signature:
            raise RuntimeError(f"raw row {row} has inconsistent orientation state")
        raw_to_signature[int(row)] = signature
        old_scale = raw_to_scale.get(int(row))
        if old_scale is not None and old_scale != complex(scale):
            raise RuntimeError(f"raw row {row} has inconsistent canonical scale")
        raw_to_scale[int(row)] = complex(scale)

    cell_count = int(index_map.size_local) + int(index_map.num_ghosts)
    for cell in range(cell_count):
        local_dofs = np.asarray(function_space.dofmap.cell_dofs(cell), dtype=np.int32)
        for dimension in (1, 2):
            connectivity = topology.connectivity(tdim, dimension)
            for local_entity, entity in enumerate(connectivity.links(cell)):
                positions = np.asarray(layout.entity_dofs(dimension, local_entity), dtype=np.int32)
                coordinates = _entity_coordinates(function_space, dimension, int(entity))
                transform, state = _physical_entity_transform(
                    coordinates, dimension, degree, tolerance
                )
                mapping = _monomial_columns(transform, label=f"entity dim {dimension}")
                physical = canonical_entity_key(coordinates, tolerance)
                for position in positions:
                    basis, coefficient = mapping[
                        int(np.flatnonzero(positions == position)[0])
                    ]
                    row = int(local_dofs[int(position)])
                    key = canonical_key(
                        role="full_fe",
                        entity_dimension=dimension,
                        physical_entity=physical,
                        entity_local_basis_index=basis,
                        orientation_state=state,
                    )
                    record(
                        row,
                        key,
                        (dimension, int(basis), tuple(state)),
                        complex(coefficient),
                    )

        interior_positions = np.asarray(element.entity_dofs[3][0], dtype=np.int32)
        cell_transform = _cell_interior_transform(
            dof_element, interior_positions, int(cell_info[cell])
        )
        reduced = cell_transform[np.ix_(interior_positions, interior_positions)]
        mapping = _monomial_columns(reduced, label="cell Tt_apply")
        physical = canonical_entity_key(_entity_coordinates(function_space, 3, cell), tolerance)
        for position in interior_positions:
            basis, coefficient = mapping[
                int(np.flatnonzero(interior_positions == position)[0])
            ]
            row = int(local_dofs[int(position)])
            key = canonical_key(
                role="full_fe",
                entity_dimension=3,
                physical_entity=physical,
                entity_local_basis_index=basis,
                orientation_state=("canonical_cell", "Tt_apply"),
            )
            record(
                row,
                key,
                (3, int(basis), ("canonical_cell", "Tt_apply")),
                complex(coefficient),
            )
    return raw_to_key, raw_to_signature, raw_to_scale


def _resolve_imported_master_metadata(
    function_space: Any,
    mpc: Any,
    slave_rows: set[int],
    raw_to_key: dict[int, Any],
    raw_to_signature: dict[int, Any],
    raw_to_scale: dict[int, complex],
) -> dict[str, int]:
    """Resolve only MPC masters absent from this rank's cell metadata."""

    comm = function_space.mesh.comm
    index_map = function_space.dofmap.index_map
    missing_rows = sorted(
        {
            int(master)
            for slave in slave_rows
            for master in np.asarray(mpc.masters.links(int(slave)), dtype=np.int32)
            if int(master) not in raw_to_key
        }
    )
    missing_global_values = np.asarray(
        index_map.local_to_global(np.asarray(missing_rows, dtype=np.int32)),
        dtype=np.int64,
    )
    missing_pairs = tuple(
        sorted(
            (int(global_row), int(raw_row))
            for raw_row, global_row in zip(
                missing_rows, missing_global_values, strict=True
            )
        )
    )
    missing_global = tuple(global_row for global_row, _raw_row in missing_pairs)
    requested_parts = comm.gather(missing_global, root=0)
    if comm.rank == 0:
        requested_global = tuple(
            sorted({int(value) for part in requested_parts for value in part})
        )
    else:
        requested_global = None
    requested_global = tuple(comm.bcast(requested_global, root=0))

    local_global_rows = np.asarray(
        index_map.local_to_global(
            np.asarray(tuple(sorted(raw_to_key)), dtype=np.int32)
        ),
        dtype=np.int64,
    )
    known_by_global = {
        int(global_row): (
            raw_to_key[int(raw_row)],
            raw_to_signature[int(raw_row)],
            raw_to_scale[int(raw_row)],
        )
        for raw_row, global_row in zip(
            tuple(sorted(raw_to_key)), local_global_rows, strict=True
        )
        if int(global_row) in requested_global
    }
    response = tuple(
        (int(global_row), key, signature, scale)
        for global_row, (key, signature, scale) in sorted(known_by_global.items())
    )
    response_parts = comm.gather(response, root=0)
    if comm.rank == 0:
        resolved: dict[int, tuple[Any, Any, complex]] = {}
        for part in response_parts:
            for global_row, key, signature, scale in part:
                old = resolved.get(int(global_row))
                value = (key, signature, complex(scale))
                if old is not None and old != value:
                    raise RuntimeError(
                        f"global MPC metadata {global_row} has conflicting canonical values"
                    )
                resolved[int(global_row)] = value
        unresolved = tuple(
            global_row
            for global_row in requested_global
            if global_row not in resolved
        )
    else:
        resolved = None
        unresolved = None
    resolved, unresolved = comm.bcast((resolved, unresolved), root=0)
    unresolved = tuple(int(value) for value in unresolved)
    if unresolved:
        raise RuntimeError(
            "unresolved imported MPC master metadata: "
            f"global_ids={unresolved!r}"
        )
    by_global = {int(global_row): value for global_row, value in resolved.items()}
    local_missing_by_global = {
        int(global_row): int(raw_row) for global_row, raw_row in missing_pairs
    }
    for global_row, raw_row in local_missing_by_global.items():
        key, signature, scale = by_global[global_row]
        raw_to_key[raw_row] = key
        raw_to_signature[raw_row] = signature
        raw_to_scale[raw_row] = complex(scale)
    return {
        "local_missing_count": len(missing_rows),
        "global_request_count": len(requested_global),
        "global_resolved_count": len(resolved),
        "global_unresolved_count": len(unresolved),
    }


def _distributed_pou_closure(
    function_space: Any,
    context: dict[str, Any],
    patches: tuple[LocalSpectralPatch, ...],
    expected: Mapping[Any, complex],
) -> float:
    """Reduce owner-local PoU contributions through the finalized vector map."""

    index_map = function_space.dofmap.index_map
    owned_count = int(index_map.size_local)
    slave_rows = context["slave_rows"]
    key_rows: dict[Any, list[int]] = {}
    for raw_row, key in context["raw_to_key"].items():
        if int(raw_row) not in slave_rows:
            key_rows.setdefault(key, []).append(int(raw_row))
    local_row_by_key = {
        key: min(
            (row for row in rows if row < owned_count),
            default=min(rows),
        )
        for key, rows in key_rows.items()
    }
    vector = fem.Function(function_space)
    vector.x.array[:] = 0.0
    for patch in patches:
        values = np.asarray(
            [expected[key] for key in patch.row_keys], dtype=np.complex128
        )
        keys, contribution = patch.pou_contribution(values)
        for key, value in zip(keys, contribution, strict=True):
            vector.x.array[local_row_by_key[key]] += value
    vector.x.scatter_reverse(la.InsertMode.add)

    numerator_sq = 0.0
    denominator_sq = 0.0
    for raw_row, key in context["raw_to_key"].items():
        raw_row = int(raw_row)
        if raw_row >= owned_count or raw_row in slave_rows or key not in expected:
            continue
        difference = vector.x.array[raw_row] - expected[key]
        numerator_sq += float(abs(difference) ** 2)
        denominator_sq += float(abs(expected[key]) ** 2)
    global_numerator_sq = function_space.mesh.comm.allreduce(
        numerator_sq, op=MPI.SUM
    )
    global_denominator_sq = function_space.mesh.comm.allreduce(
        denominator_sq, op=MPI.SUM
    )
    del vector
    return float(
        np.sqrt(global_numerator_sq)
        / max(np.sqrt(global_denominator_sq), 1.0e-300)
    )


def _gradient_metrics(gradients: np.ndarray, mass: np.ndarray) -> tuple[int, float]:
    gram = gradients.conj().T @ mass @ gradients
    values, vectors = np.linalg.eigh((gram + gram.conj().T) * 0.5)
    rank = int(np.count_nonzero(values > 1.0e-14 * max(float(values[-1]), 1.0)))
    if rank != 3:
        return rank, float("inf")
    normalized = gradients @ vectors @ np.diag(1.0 / np.sqrt(values)) @ vectors.conj().T
    defect = _relative(normalized.conj().T @ mass @ normalized - np.eye(3), np.eye(3))
    return rank, float(defect)


def _mode_digest(
    patches: tuple[LocalSpectralPatch, ...],
    canonical_cell_keys: tuple[Any, ...] | None = None,
) -> str:
    payload = []
    if canonical_cell_keys is None:
        canonical_cell_keys = tuple(patch.row_keys for patch in patches)
    for cell_key, patch in zip(canonical_cell_keys, patches, strict=True):
        columns = [
            canonical_vector_digest(patch.row_keys, patch.modes[:, column])
            for column in range(patch.modes.shape[1])
        ]
        payload.append((cell_key, tuple(columns)))
    return hashlib.sha256(repr(tuple(payload)).encode("utf-8")).hexdigest()


def _prepare_real_context(
    function_space: Any, mesh_data: Any, floquet_data: Any, cfg: Any
) -> dict[str, Any]:
    """Prepare only small cell metadata; no dense local matrix is retained."""

    comm = function_space.mesh.comm
    element = function_space.element.basix_element
    dof_element = function_space.element
    if str(element.cell_type.name).lower() != "hexahedron":
        raise NotImplementedError("the local-cell adapter requires hexahedra")
    degree = int(element.degree)
    if degree not in {2, 3, 6}:
        raise ValueError(f"real local spectral adapter supports p2/p3/p6, got p{degree}")

    mesh = function_space.mesh
    topology = mesh.topology
    tdim = int(topology.dim)
    owned_cells = int(topology.index_map(tdim).size_local)
    tags = {
        int(index): int(value)
        for index, value in zip(
            mesh_data.cell_tags.indices, mesh_data.cell_tags.values, strict=True
        )
    }
    if set(tags) != set(range(owned_cells)):
        raise RuntimeError("cell_tags do not cover every owned hexahedral cell")
    mass_coefficients = {
        int(cfg.tags.air): complex(cfg.k0**2 * abs(cfg.eps_air)),
        int(cfg.tags.substrate): complex(cfg.k0**2 * abs(cfg.eps_substrate)),
        int(cfg.tags.grating): complex(cfg.k0**2 * abs(cfg.eps_grating)),
    }
    b_factory = AffineIsotropicMaxwellTensorFactory(
        element,
        AffineIsotropicMaxwellTensorSpec(
            curl_coefficient=1.0 / complex(cfg.mu_r),
            mass_coefficient_by_tag=mass_coefficients,
        ),
    )
    raw_to_key, raw_to_signature, raw_to_scale = _row_semantics(
        function_space, mesh
    )
    mpc = floquet_data.mpc
    slave_rows = {int(value) for value in np.asarray(mpc.slaves, dtype=np.int32)}
    imported_master_metadata = _resolve_imported_master_metadata(
        function_space,
        mpc,
        slave_rows,
        raw_to_key,
        raw_to_signature,
        raw_to_scale,
    )
    cell_infos = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    cell_metadata: list[dict[str, Any]] = []
    local_class_digests: list[str] = []
    tolerance = mesh_coordinate_tolerance(mesh)
    for cell in range(owned_cells):
        local_dofs = tuple(
            int(value)
            for value in np.asarray(function_space.dofmap.cell_dofs(cell), dtype=np.int32)
        )
        free_rows, sparse_pattern, expansion_pattern = _mpc_expansion(
            np.asarray(local_dofs, dtype=np.int32),
            mpc,
            slave_rows,
            raw_to_key,
            raw_to_scale,
        )
        if any(row not in raw_to_key for row in free_rows):
            raise RuntimeError("MPC expansion references a row without a physical canonical key")
        coordinates = np.asarray(
            _entity_coordinates(function_space, 3, cell), dtype=np.float64
        )
        if coordinates.shape != (8, 3):
            raise RuntimeError("real cell is not an eight-vertex hexahedron")
        widths = tuple(float(value) for value in np.ptp(coordinates, axis=0))
        if any(value <= 0.0 for value in widths):
            raise RuntimeError("real hexahedron has a nonpositive width")
        cell_key = canonical_entity_key(coordinates, tolerance)
        cell_origin = tuple(
            min(int(point[axis]) for point in cell_key)
            for axis in range(3)
        )
        local_row_descriptors = tuple(
            _relative_canonical_row_descriptor(
                raw_to_key[int(row)], cell_origin
            )
            for row in local_dofs
        )
        free_row_descriptors = tuple(
            _relative_canonical_row_descriptor(raw_to_key[int(row)], cell_origin)
            for row in free_rows
        )
        canonical_row_expansions = _canonical_row_expansions(
            local_row_descriptors,
            free_row_descriptors,
            tuple(raw_to_scale[int(row)] for row in local_dofs),
            sparse_pattern,
            tuple(
                complex(value)
                for value in (
                    floquet_data.phase_x,
                    floquet_data.phase_y,
                    floquet_data.phase_corner,
                )
            ),
        )
        row_signatures = tuple(
            raw_to_signature.get(int(row), ("slave",)) for row in local_dofs
        )
        free_signatures = tuple(raw_to_signature[int(row)] for row in free_rows)
        digest = _class_digest(
            element=element,
            cfg=cfg,
            tag=int(tags[cell]),
            widths=widths,
            canonical_row_expansions=canonical_row_expansions,
        )
        metadata = {
            "local_dofs": local_dofs,
            "free_rows": free_rows,
            "sparse_pattern": sparse_pattern,
            "row_keys": tuple(raw_to_key[row] for row in free_rows),
            "row_signatures": row_signatures,
            "free_signatures": free_signatures,
            "expansion_pattern": expansion_pattern,
            "canonical_row_descriptors": local_row_descriptors,
            "canonical_free_row_descriptors": free_row_descriptors,
            "canonical_row_expansions": canonical_row_expansions,
            "tag": int(tags[cell]),
            "widths": widths,
            "cell_info": int(cell_infos[cell]),
            "cell_key": cell_key,
            "cell_origin": cell_origin,
            "digest": digest,
        }
        if len(set(metadata["row_keys"])) != len(metadata["row_keys"]):
            raise RuntimeError(f"cell {cell} has duplicate constrained canonical rows")
        cell_metadata.append(metadata)
        local_class_digests.append(digest)
    class_parts = comm.gather(tuple(sorted(set(local_class_digests))), root=0)
    if comm.rank == 0:
        class_digests = tuple(
            sorted({digest for part in class_parts for digest in part})
        )
    else:
        class_digests = None
    class_digests = comm.bcast(class_digests, root=0)
    local_multiplicities = Counter(
        key for metadata in cell_metadata for key in metadata["row_keys"]
    )
    multiplicity_parts = comm.gather(dict(local_multiplicities), root=0)
    if comm.rank == 0:
        multiplicities = Counter()
        for part in multiplicity_parts:
            multiplicities.update(part)
    else:
        multiplicities = None
    multiplicity_payload = (
        dict(multiplicities) if comm.rank == 0 else None
    )
    multiplicities = Counter(comm.bcast(multiplicity_payload, root=0))
    return {
        "comm": comm,
        "function_space": function_space,
        "element": element,
        "dof_element": dof_element,
        "mesh": mesh,
        "topology": topology,
        "tdim": tdim,
        "owned_cells": owned_cells,
        "degree": degree,
        "b_factory": b_factory,
        "mpc": mpc,
        "slave_rows": slave_rows,
        "cell_metadata": cell_metadata,
        "class_digests": class_digests,
        "local_class_digests": tuple(sorted(set(local_class_digests))),
        "multiplicities": multiplicities,
        "raw_to_key": raw_to_key,
        "raw_to_signature": raw_to_signature,
        "raw_to_scale": raw_to_scale,
        "imported_master_metadata": imported_master_metadata,
    }


def _cell_operators(
    metadata: dict[str, Any], context: dict[str, Any], *, with_mass: bool = True
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Build one oriented constrained cell block for the streaming pass."""

    expansion = _dense_expansion(
        metadata["sparse_pattern"], len(metadata["free_rows"])
    )
    raw_block = context["b_factory"].tensor(
        tag=metadata["tag"], widths=metadata["widths"]
    )
    _orient_cell_tensor(context["dof_element"], raw_block, metadata["cell_info"])
    block = np.ascontiguousarray(expansion.conj().T @ raw_block @ expansion)
    if not with_mass:
        del expansion, raw_block
        return block, None, None
    raw_mass = context["b_factory"].mass_tensor(
        tag=metadata["tag"], widths=metadata["widths"]
    )
    _orient_cell_tensor(context["dof_element"], raw_mass, metadata["cell_info"])
    local_mass = np.ascontiguousarray(expansion.conj().T @ raw_mass @ expansion)
    del expansion, raw_block, raw_mass
    return block, None, local_mass


def _class_relative_template_order(
    metadata: Mapping[str, Any],
) -> tuple[tuple[Any, ...], tuple[int, ...]]:
    """Return deterministic class-relative free-row keys and source order."""

    descriptors = tuple(metadata["canonical_free_row_descriptors"])
    order = tuple(sorted(range(len(descriptors)), key=lambda index: repr(descriptors[index])))
    return tuple(descriptors[index] for index in order), order


def _metadata_gradient_candidates(
    metadata: Mapping[str, Any],
    context: Mapping[str, Any],
    gradient_fields: tuple[fem.Function, ...],
) -> np.ndarray:
    """Read three finalized-MPC gradients in one cell's free raw rows."""

    return np.ascontiguousarray(
        np.column_stack(
            [
                np.asarray(
                    [
                        field.x.array[int(row)]
                        / context["raw_to_scale"][int(row)]
                        for row in metadata["free_rows"]
                    ],
                    dtype=np.complex128,
                )
                for field in gradient_fields
            ]
        )
    )


def _class_participation(
    comm: Any,
    class_digests: Sequence[str],
    local_class_digests: Sequence[str],
) -> tuple[dict[str, tuple[int, ...]], dict[str, int]]:
    """Build bounded class participant/representative metadata."""

    local = tuple(sorted(set(local_class_digests)))
    parts = comm.gather(local, root=0)
    if comm.rank == 0:
        participants = {
            digest: tuple(
                rank for rank, part in enumerate(parts) if digest in part
            )
            for digest in class_digests
        }
        representatives = {
            digest: min(ranks) for digest, ranks in participants.items()
        }
    else:
        participants = None
        representatives = None
    return (
        comm.bcast(participants, root=0),
        comm.bcast(representatives, root=0),
    )


def _build_reused_class_template_patches(
    context: dict[str, Any],
    plan: ExactClassOwnerPlan,
) -> tuple[tuple[LocalSpectralPatch, ...], dict[str, Any]]:
    """Build one dense/eigensolve representative and retain patch shards."""

    comm = context["comm"]
    participants, representatives = _class_participation(
        comm,
        context["class_digests"],
        context["local_class_digests"],
    )
    gradient_fields = tuple(
        _field_component(context["function_space"], component)
        for component in range(3)
    )
    for field in gradient_fields:
        context["mpc"].homogenize(field)
        context["mpc"].backsubstitution(field)
        field.x.scatter_forward()

    class_templates: dict[str, tuple[tuple[Any, ...], np.ndarray]] = {}
    template_audits: dict[str, dict[str, Any]] = {}
    template_bytes_local = 0
    try:
        for slot, digest in enumerate(plan.class_digests):
            representative_rank = int(representatives[digest])
            representative = next(
                (
                    metadata
                    for metadata in context["cell_metadata"]
                    if metadata["digest"] == digest
                ),
                None,
            )
            block = None
            local_mass = None
            gradients = None
            template_keys = None
            template_modes = None
            template_audit = None
            if comm.rank == representative_rank:
                if representative is None:
                    raise RuntimeError("class representative metadata is unavailable")
                block, _unused, local_mass = _cell_operators(
                    representative, context
                )
                gradients = _metadata_gradient_candidates(
                    representative, context, gradient_fields
                )
                template_keys, order = _class_relative_template_order(representative)
                indices = np.ix_(order, order)
                block = np.ascontiguousarray(block[indices])
                local_mass = np.ascontiguousarray(local_mass[indices])
                gradients = np.ascontiguousarray(gradients[np.asarray(order), :])

            plan.register_class_representative(digest, block, slot=slot)
            if comm.rank == representative_rank:
                template_patch = LocalSpectralPatch(
                    block,
                    local_mass,
                    gradients,
                    patch_id=-1,
                    exact_class_digest=digest,
                    row_keys=template_keys,
                    comm=comm,
                    class_plan=plan,
                )
                template_patch.build()
                template_modes = np.ascontiguousarray(template_patch.modes)
                template_audit = dict(template_patch.audit)
                template_bytes_local += int(template_modes.nbytes)
                template_patch.destroy()
                del template_patch, block, local_mass, gradients

            template_audit = comm.bcast(template_audit, root=representative_rank)
            routed = plan.register_class_template(
                digest,
                template_keys,
                template_modes,
                slot=slot,
                representative_rank=representative_rank,
                participant_ranks=participants[digest],
            )
            if routed is not None:
                class_templates[digest] = routed
            template_audits[digest] = template_audit
            del template_keys, template_modes, template_audit
    finally:
        for field in gradient_fields:
            del field

    local_factor_audits = {
        digest: dict(value) for digest, value in plan.local_factor_audits.items()
    }
    factor_audit_parts = comm.gather(local_factor_audits, root=0)
    if comm.rank == 0:
        global_factor_audits: dict[str, dict[str, Any]] = {}
        for part in factor_audit_parts:
            for digest, value in part.items():
                if digest in global_factor_audits:
                    raise RuntimeError(
                        f"exact class {digest} has multiple factor owners"
                    )
                global_factor_audits[digest] = dict(value)
        if set(global_factor_audits) != set(plan.class_digests):
            raise RuntimeError("factor-owner audit is incomplete")
    else:
        global_factor_audits = None
    global_factor_audits = comm.bcast(global_factor_audits, root=0)
    for digest in plan.class_digests:
        template_audits[digest].update(global_factor_audits[digest])

    patches: list[LocalSpectralPatch] = []
    for patch_id, metadata in enumerate(context["cell_metadata"]):
        template_keys, template_modes = class_templates[metadata["digest"]]
        patch_keys = tuple(metadata["canonical_free_row_descriptors"])
        mode_shard = map_mode_template_to_patch(
            template_keys,
            template_modes,
            patch_keys,
        )
        patch = LocalSpectralPatch.from_mode_template(
            mode_shard,
            patch_id=patch_id,
            exact_class_digest=metadata["digest"],
            row_keys=metadata["row_keys"],
            shared_row_multiplicity=np.asarray(
                [context["multiplicities"][key] for key in metadata["row_keys"]],
                dtype=np.int64,
            ),
            comm=comm,
            class_plan=plan,
            class_template_row_keys=template_keys,
        )
        patches.append(patch)
        del mode_shard
    del class_templates

    local_patch_counts = Counter(metadata["digest"] for metadata in context["cell_metadata"])
    patch_count_parts = comm.gather(dict(local_patch_counts), root=0)
    if comm.rank == 0:
        global_patch_counts = Counter()
        for part in patch_count_parts:
            global_patch_counts.update(part)
        global_patch_counts = dict(global_patch_counts)
    else:
        global_patch_counts = None
    global_patch_counts = comm.bcast(global_patch_counts, root=0)

    expected = {
        key: _source_value(key) for key in context["multiplicities"]
    }
    adjoint_errors = []
    for patch in patches:
        seed = hashlib.sha256(repr(patch.row_keys).encode("utf-8")).digest()
        x = np.resize(
            np.asarray(
                [complex(value / 17.0, -value / 23.0) for value in seed],
                dtype=np.complex128,
            ),
            len(patch.row_keys),
        )
        c = np.asarray(
            [complex(index + 1.0, -0.5 * index) for index in range(N1_MODE_CAP)],
            dtype=np.complex128,
        )
        adjoint_errors.append(patch.restriction_prolongation_adjoint_error(x, c))

    template_audit_values = tuple(template_audits.values())
    local_mode_shard_bytes = sum(int(patch.modes.nbytes) for patch in patches)
    audit = {
        "schema": "task038.n2.class-template-local-cell-adapter.v1",
        "fixture": "real_p2_p3_p6_cell_template_setup_only",
        "degree": context["degree"],
        "cell_count": context["owned_cells"],
        "patch_count": len(patches),
        "row_count_min": min(len(patch.row_keys) for patch in patches),
        "row_count_max": max(len(patch.row_keys) for patch in patches),
        "class_count": len(plan.class_digests),
        "class_digests": tuple(plan.class_digests),
        "class_owners": dict(plan.owners),
        "class_participants": dict(participants),
        "class_representatives": dict(representatives),
        "class_patch_counts_global": global_patch_counts,
        "class_inventory": "global_sorted_exact_class_digests",
        "class_factor_registration": (
            "fixed_global_class_slots_one_representative_to_hash_owner"
        ),
        "owner_factor_count": plan.factor_count,
        "owner_factor_bytes": plan.factor_bytes,
        "global_owner_factor_count": int(comm.allreduce(plan.factor_count, op=MPI.SUM)),
        "global_owner_factor_bytes": int(comm.allreduce(plan.factor_bytes, op=MPI.SUM)),
        "factor_audits_by_class": global_factor_audits,
        "mode_template_count": len(plan.class_digests),
        "mode_template_bytes_transient_local": int(template_bytes_local),
        "mode_template_bytes_transient_global": int(
            comm.allreduce(template_bytes_local, op=MPI.SUM)
        ),
        "mode_shard_bytes_retained_local": int(local_mode_shard_bytes),
        "mode_shard_bytes_retained_global": int(
            comm.allreduce(local_mode_shard_bytes, op=MPI.SUM)
        ),
        "dense_transient_class_count": len(plan.class_digests),
        "dense_workspace_released": all(
            patch.block is None and patch.local_mass is None
            for patch in patches
        ),
        "mode_template_route": "class_relative_keys_to_participant_patch_ranks",
        "B0_hermitian_relative_defect": max(
            float(value["B0_hermitian_relative_defect"])
            for value in template_audit_values
        ),
        "factorization_relative_error_max": max(
            float(value["factorization_relative_error"])
            for value in global_factor_audits.values()
        ),
        "M_local_hermitian_relative_defect": max(
            float(value["M_local_hermitian_relative_defect"])
            for value in template_audit_values
        ),
        "B0_min_eigenvalue": min(
            float(value["B0_min_eigenvalue"]) for value in template_audit_values
        ),
        "M_local_min_eigenvalue": min(
            float(value["M_local_min_eigenvalue"]) for value in template_audit_values
        ),
        "gradient_rank_min": min(
            int(value["gradient_rank"]) for value in template_audit_values
        ),
        "gradient_gram_defect_max": max(
            float(value["gradient_m_gram_relative_defect"])
            for value in template_audit_values
        ),
        "projected_eigen_residual_max": max(
            float(value["generalized_eigen_residual"])
            for value in template_audit_values
        ),
        "fixed_solve_residual_max": max(
            (
                float(value["fixed_rhs_solve_residual"])
                for value in global_factor_audits.values()
            ),
            default=None,
        ),
        "pou_closure_relative_error": _distributed_pou_closure(
            context["function_space"], context, patches, expected
        ),
        "pou_closure_route": "owner_local_fem_function_scatter_reverse_insert_add",
        "restriction_prolongation_adjoint_relative_error_max": max(adjoint_errors),
        "independent_global_assembled_oracle": None,
        "production_path_references_oracle": False,
        "oracle_contract": "small_assembled_oracle_only_p2_p3_test_path",
        "mode_digest": _mode_digest(
            tuple(patches),
            tuple(metadata["cell_key"] for metadata in context["cell_metadata"]),
        ),
        "forbidden_objects": {
            "global_numeric_allgather": False,
            "global_aij": False,
            "global_schur": False,
            "static_condensation": False,
            "trace_harmonic_backend": False,
            "per_patch_retained_dense_block": False,
        },
        "orientation": "DOLFINx Basix T_apply/Tt_apply cell semantics",
        "mpc_expansion": "finalized Floquet direct primal coefficients, slaves excluded from free rows",
        "patch_ownership": "owned_cells_only; ghost_cells_metadata_only",
        "class_template_eigensolve": "one canonical representative per exact class",
        "class_factor_count_per_class": 1,
        "regional_setup": "not_built_in_this_setup_block",
        "top_rank": N1_TOP_RANK,
        "coarse_levels": N1_LEVELS,
    }
    return tuple(patches), audit


def _macroregion_key(
    coordinates: np.ndarray,
    *,
    origin: np.ndarray,
    base_width: np.ndarray,
) -> tuple[int, int, int]:
    """Map one cell's lower corner to the fixed two-cell macroregion."""

    lower = np.min(np.asarray(coordinates, dtype=np.float64), axis=0)
    cell_index = np.rint((lower - origin) / base_width).astype(np.int64)
    return tuple(int(value) // _REGIONAL_CELL_BLOCK for value in cell_index)


def _regional_owner(region: Any, active_ranks: tuple[int, ...]) -> int:
    if not active_ranks:
        raise ValueError("a regional owner requires at least one active rank")
    digest = hashlib.sha256(repr(("regional", region)).encode("utf-8")).hexdigest()
    slot = int.from_bytes(bytes.fromhex(digest)[:8], "big") % len(active_ranks)
    return int(active_ranks[slot])


def _route_region_expanded_to_row_owners(
    comm: Any,
    owner: int,
    region: Any,
    region_slot: int,
    row_keys: Sequence[Any] | None,
    expanded: np.ndarray | None,
) -> tuple[tuple[Any, np.ndarray], ...]:
    """Route one regional expanded shard to canonical row owners."""

    if comm.rank == owner:
        assert row_keys is not None and expanded is not None
        destinations = tuple(
            sorted(
                {
                    deterministic_row_owner(key, comm.size)
                    for key in row_keys
                }
            )
        )
    else:
        destinations = None
    destinations = tuple(comm.bcast(destinations, root=owner))
    tag = 8000 + int(region_slot)
    if comm.rank == owner:
        by_destination: dict[int, list[tuple[Any, np.ndarray]]] = {
            rank: [] for rank in destinations
        }
        for index, key in enumerate(row_keys):
            destination = deterministic_row_owner(key, comm.size)
            by_destination[destination].append(
                (key, np.ascontiguousarray(expanded[index, :]))
            )
        local = tuple(by_destination[owner])
        for destination in destinations:
            if destination != owner:
                comm.send(tuple(by_destination[destination]), dest=destination, tag=tag)
    elif comm.rank in destinations:
        local = tuple(comm.recv(source=owner, tag=tag))
    else:
        local = ()
    return local


def _physical_owned_row_layout(
    function_space: Any, context: Mapping[str, Any]
) -> tuple[tuple[Any, ...], tuple[Any, ...], tuple[int, ...]]:
    """Return the finalized-MPC owned slice in its physical local order.

    ``raw_to_key`` is used only to label the already-owned DOLFINx rows.  The
    local row number is never part of the canonical identity.  Owned slave
    rows remain explicit zero slots because the physical action Vec owns the
    complete finalized-MPC slice; they are excluded from ``active_keys``.
    """

    owned_count = int(function_space.dofmap.index_map.size_local)
    slave_rows = {int(row) for row in context["slave_rows"]}
    raw_to_key = context["raw_to_key"]
    physical_keys: list[Any] = []
    active_keys: list[Any] = []
    active_positions: list[int] = []
    seen: set[Any] = set()
    for raw_row in range(owned_count):
        key = raw_to_key.get(raw_row)
        if raw_row in slave_rows:
            physical_keys.append(None)
            continue
        if key is None:
            raise RuntimeError(
                "owned non-slave physical row has no canonical key: "
                f"local_row={raw_row}"
            )
        if key in seen:
            raise RuntimeError(
                f"owned physical row order repeats canonical key: {key!r}"
            )
        seen.add(key)
        physical_keys.append(key)
        active_keys.append(key)
        active_positions.append(raw_row)
    return tuple(physical_keys), tuple(active_keys), tuple(active_positions)


def _physical_row_targets(
    comm: Any, active_keys: Sequence[Any], active_positions: Sequence[int]
) -> dict[Any, tuple[int, int]]:
    """Exchange only key/rank/position metadata for hash-owner routing."""

    outgoing: list[list[tuple[Any, int, int]]] = [
        [] for _ in range(comm.size)
    ]
    for key, position in zip(active_keys, active_positions, strict=True):
        outgoing[deterministic_row_owner(key, comm.size)].append(
            (key, int(comm.rank), int(position))
        )
    incoming = comm.alltoall(outgoing)
    targets: dict[Any, tuple[int, int]] = {}
    for packets in incoming:
        for key, rank, position in packets:
            target = (int(rank), int(position))
            old = targets.get(key)
            if old is not None and old != target:
                raise RuntimeError(
                    f"canonical key has multiple physical owners: {key!r}"
                )
            targets[key] = target
    return targets


def _scatter_hash_owned_rows_to_physical_order(
    comm: Any,
    regional_accumulator: Mapping[Any, np.ndarray],
    top_accumulator: Mapping[Any, np.ndarray],
    targets: Mapping[Any, tuple[int, int]],
    physical_keys: Sequence[Any],
    active_keys: Sequence[Any],
    active_positions: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    """Scatter hash-owner packets into the DOLFINx owned row order.

    This is a point-to-point owner route, not a numeric allgather: each row's
    16/32 values are sent once to its physical PETSc owner and never replicated
    on every rank.
    """

    outgoing: list[list[tuple[Any, int, np.ndarray, np.ndarray]]] = [
        [] for _ in range(comm.size)
    ]
    for key, regional in regional_accumulator.items():
        if key not in targets or key not in top_accumulator:
            raise RuntimeError(
                f"hash-owned canonical row has no physical target: {key!r}"
            )
        rank, position = targets[key]
        top = np.asarray(top_accumulator[key], dtype=np.complex128)
        regional = np.asarray(regional, dtype=np.complex128)
        if regional.shape != (N1_REGIONAL_RANK,) or top.shape != (N1_TOP_RANK,):
            raise RuntimeError("owner-local multilevel row packet has wrong shape")
        if not np.all(np.isfinite(regional)) or not np.all(np.isfinite(top)):
            raise RuntimeError("owner-local multilevel row packet is non-finite")
        outgoing[int(rank)].append(
            (key, int(position), np.ascontiguousarray(regional), np.ascontiguousarray(top))
        )
    incoming = comm.alltoall(outgoing)
    expected = {key: int(position) for key, position in zip(active_keys, active_positions, strict=True)}
    received_keys: set[Any] = set()
    regional_columns = np.zeros(
        (len(physical_keys), N1_REGIONAL_RANK), dtype=np.complex128
    )
    top_columns = np.zeros((len(physical_keys), N1_TOP_RANK), dtype=np.complex128)
    for packets in incoming:
        for key, position, regional, top in packets:
            if key not in expected or int(position) != expected[key]:
                raise RuntimeError(
                    f"physical row packet is not in the local owned order: {key!r}"
                )
            if key in received_keys:
                raise RuntimeError(f"physical row packet is duplicated: {key!r}")
            received_keys.add(key)
            regional_columns[int(position), :] = regional
            top_columns[int(position), :] = top
    missing = set(expected) - received_keys
    if missing:
        raise RuntimeError(
            "physical owner route is missing canonical rows: "
            f"count={len(missing)}"
        )
    return regional_columns, top_columns


def build_real_local_regional_rayleigh_ritz(
    patches: tuple[LocalSpectralPatch, ...],
    function_space: Any,
    mesh_data: Any,
    floquet_data: Any,
    cfg: Any,
    *,
    return_multilevel: bool = False,
) -> tuple[Mapping[Any, Mapping[str, Any]], dict[str, Any]] | tuple[
    Mapping[Any, Mapping[str, Any]], dict[str, Any], Any
]:
    """Aggregate fixed two-cell regions through participant-only messages."""

    context = _prepare_real_context(function_space, mesh_data, floquet_data, cfg)
    if len(patches) != context["owned_cells"]:
        raise ValueError("regional patches must cover owned cells exactly")
    mesh = context["mesh"]
    comm = context["comm"]
    local_coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
    local_origin = np.min(local_coordinates, axis=0)
    origin = np.asarray(
        [comm.allreduce(float(value), op=MPI.MIN) for value in local_origin],
        dtype=np.float64,
    )
    base_width = np.asarray(
        [
            comm.allreduce(
                min(metadata["widths"][axis] for metadata in context["cell_metadata"]),
                op=MPI.MIN,
            )
            for axis in range(3)
        ],
        dtype=np.float64,
    )
    if np.any(base_width <= 0.0):
        raise RuntimeError("regional cell widths must be positive")
    region_for_cell = tuple(
        _macroregion_key(
            np.asarray(
                _entity_coordinates(function_space, 3, cell),
                dtype=np.float64,
            ),
            origin=origin,
            base_width=base_width,
        )
        for cell in range(context["owned_cells"])
    )
    local_entries = tuple(
        sorted(
            (
                metadata["cell_key"],
                region,
            )
            for metadata, region in zip(
                context["cell_metadata"], region_for_cell, strict=True
            )
        )
    )
    cell_parts = comm.gather(local_entries, root=0)
    if comm.rank == 0:
        global_cells: dict[Any, Any] = {}
        region_cells: dict[Any, list[Any]] = {}
        region_participants: dict[Any, list[int]] = {}
        for rank, part in enumerate(cell_parts):
            for cell_key, region in part:
                if cell_key in global_cells:
                    raise RuntimeError("canonical cell key has multiple owners")
                global_cells[cell_key] = region
                region_cells.setdefault(region, []).append(cell_key)
                region_participants.setdefault(region, []).append(rank)
        inventory = {
            region: tuple(sorted(keys, key=repr))
            for region, keys in region_cells.items()
        }
        participants = {
            region: tuple(sorted(set(ranks)))
            for region, ranks in region_participants.items()
        }
    else:
        inventory = None
        participants = None
    inventory, participants = comm.bcast((inventory, participants), root=0)
    ordered_regions = tuple(sorted(inventory, key=repr))
    canonical_cell_inventory = tuple(
        (
            repr(region),
            tuple(repr(cell_key) for cell_key in inventory[region]),
        )
        for region in ordered_regions
    )
    canonical_cell_inventory_digest = hashlib.sha256(
        repr(canonical_cell_inventory).encode("utf-8")
    ).hexdigest()
    region_cell_counts = tuple(len(inventory[region]) for region in ordered_regions)
    global_cell_count = sum(region_cell_counts)
    if max(region_cell_counts, default=0) > 8:
        raise RuntimeError(
            "canonical 2x2x2 regional inventory exceeds the eight-cell bound: "
            f"max_region_cells={max(region_cell_counts, default=0)}"
        )
    metadata_by_cell = {
        metadata["cell_key"]: (metadata, patches[index])
        for index, metadata in enumerate(context["cell_metadata"])
    }
    records: dict[Any, Mapping[str, Any]] = {}
    patch_digests: dict[Any, str] = {}
    expanded_digests: dict[Any, str] = {}
    source_action_digests: dict[Any, str] = {}
    regional_ranks: list[int] = []
    regional_candidate_ranks: list[int] = []
    regional_mass_defects: list[float] = []
    regional_residuals: list[float] = []
    max_candidate_dimension = 0
    max_projected_dimension = 0
    regional_accumulator: dict[Any, np.ndarray] = {}
    top_accumulator: dict[Any, np.ndarray] = {}
    for region_slot, region in enumerate(ordered_regions):
        cell_order = inventory[region]
        active_ranks = participants[region]
        owner = _regional_owner(region, active_ranks)
        local_cells = tuple(
            cell_key for cell_key in cell_order if cell_key in metadata_by_cell
        )
        local_packet = []
        for cell_key in local_cells:
            metadata, patch = metadata_by_cell[cell_key]
            values = np.column_stack(
                [
                    patch.local_weighted_value(patch.modes[:, mode])
                    for mode in range(8)
                ]
            )
            local_packet.append((cell_key, metadata["row_keys"], values))
        if comm.rank == owner:
            packets_by_rank = {}
            if comm.rank in active_ranks:
                packets_by_rank[owner] = local_packet
            for rank in active_ranks:
                if rank != owner:
                    packets_by_rank[rank] = comm.recv(
                        source=rank, tag=4000 + region_slot
                    )
            packets = [
                packet
                for rank in active_ranks
                for packet in packets_by_rank[rank]
            ]
            row_keys = tuple(
                sorted(
                    {
                        key
                        for _cell_key, keys, _values in packets
                        for key in keys
                    },
                    key=repr,
                )
            )
            row_index = {key: index for index, key in enumerate(row_keys)}
            candidate_count = 8 * len(cell_order)
            if candidate_count > 64:
                raise RuntimeError(
                    f"regional candidate count {candidate_count} exceeds limit 64"
                )
            candidates = np.zeros(
                (len(row_keys), candidate_count), dtype=np.complex128
            )
            packet_by_cell = {
                cell_key: (keys, values)
                for cell_key, keys, values in packets
            }
            for cell_offset, cell_key in enumerate(cell_order):
                keys, values = packet_by_cell[cell_key]
                indices = np.asarray(
                    [row_index[key] for key in keys], dtype=np.int64
                )
                candidates[indices, 8 * cell_offset : 8 * cell_offset + 8] = values
            patch_payload = tuple(
                (
                    cell_key,
                    tuple(
                        canonical_vector_digest(
                            packet_by_cell[cell_key][0],
                            packet_by_cell[cell_key][1][:, mode],
                        )
                        for mode in range(8)
                    ),
                )
                for cell_key in cell_order
            )
            patch_digest = hashlib.sha256(
                repr(patch_payload).encode("utf-8")
            ).hexdigest()
            merged = (row_keys, candidates, cell_order, patch_digest)
            for rank in active_ranks:
                if rank != owner:
                    comm.send(merged, dest=rank, tag=5000 + region_slot)
        elif comm.rank in active_ranks:
            comm.send(local_packet, dest=owner, tag=4000 + region_slot)
            merged = comm.recv(source=owner, tag=5000 + region_slot)
        else:
            merged = None
        if comm.rank in active_ranks:
            row_keys, candidates, _ordered_cells, patch_digest = merged
            row_index = {key: index for index, key in enumerate(row_keys)}
            candidate_count = int(candidates.shape[1])
            local_contributions = []
            for cell_key in local_cells:
                metadata, _patch = metadata_by_cell[cell_key]
                block, _unused, mass_block = _cell_operators(metadata, context)
                indices = np.asarray(
                    [row_index[key] for key in metadata["row_keys"]],
                    dtype=np.int64,
                )
                cell_candidates = candidates[indices, :]
                local_contributions.append(
                    (
                        cell_key,
                        cell_candidates.conj().T @ block @ cell_candidates,
                        cell_candidates.conj().T @ mass_block @ cell_candidates,
                    )
                )
                del block, _unused, mass_block, indices, cell_candidates
            if comm.rank == owner:
                contributions_by_cell = {
                    cell_key: (cell_stiffness, cell_mass)
                    for cell_key, cell_stiffness, cell_mass in local_contributions
                }
                for rank in active_ranks:
                    if rank != owner:
                        for cell_key, cell_stiffness, cell_mass in comm.recv(
                            source=rank, tag=6000 + region_slot
                        ):
                            contributions_by_cell[cell_key] = (
                                cell_stiffness,
                                cell_mass,
                            )
                stiffness = np.zeros(
                    (candidate_count, candidate_count), dtype=np.complex128
                )
                mass = np.zeros_like(stiffness)
                for cell_key in cell_order:
                    cell_stiffness, cell_mass = contributions_by_cell[cell_key]
                    stiffness += cell_stiffness
                    mass += cell_mass
            else:
                comm.send(
                    local_contributions,
                    dest=owner,
                    tag=6000 + region_slot,
                )
        if comm.rank == owner:
            regional_result = build_regional_rayleigh_ritz(
                {region: candidates},
                {region: stiffness},
                {region: mass},
                region_candidate_keys={
                    region: tuple(
                        (cell_key, mode)
                        for cell_key in cell_order
                        for mode in range(8)
                    )
                },
            )[region]
            coefficients = regional_result["coefficients"]
            expanded = candidates @ coefficients
            expanded_payload = tuple(
                canonical_vector_digest(row_keys, expanded[:, mode])
                for mode in range(expanded.shape[1])
            )
            expanded_digest = hashlib.sha256(
                repr(expanded_payload).encode("utf-8")
            ).hexdigest()
            source = np.asarray(
                [complex(index + 1.0, -0.25 * index) for index in range(candidate_count)],
                dtype=np.complex128,
            )
            action = stiffness @ source
            source_action_digest = hashlib.sha256(
                repr(
                    (
                        tuple(row_keys),
                        tuple(_pair(value) for value in source),
                        tuple(_pair(value) for value in action),
                    )
                ).encode("utf-8")
            ).hexdigest()
            compact = dict(regional_result)
            compact.pop("coefficients")
            compact.update(
                {
                    "canonical_row_count": len(row_keys),
                    "candidate_count": candidate_count,
                    "regional_owner": owner,
                    "participants": active_ranks,
                    "canonical_patch_mode_digest": patch_digest,
                    "regional_expanded_mode_digest": expanded_digest,
                    "source_action_digest": source_action_digest,
                    "streamed_one_region_at_a_time": True,
                }
            )
        else:
            compact = None
        if return_multilevel:
            if comm.rank == owner:
                for rank in active_ranks:
                    if rank != owner:
                        comm.send(
                            coefficients,
                            dest=rank,
                            tag=7000 + region_slot,
                        )
                local_coefficients = coefficients
            elif comm.rank in active_ranks:
                local_coefficients = comm.recv(
                    source=owner,
                    tag=7000 + region_slot,
                )
            else:
                local_coefficients = None
            compact = comm.bcast(compact, root=owner)
            record_payload = dict(compact)
            if local_coefficients is not None:
                record_payload["coefficients"] = np.ascontiguousarray(
                    local_coefficients, dtype=np.complex128
                )
            records[region] = MappingProxyType(record_payload)
            routed_rows = _route_region_expanded_to_row_owners(
                comm,
                owner,
                region,
                region_slot,
                row_keys if comm.rank == owner else None,
                expanded if comm.rank == owner else None,
            )
            for key, values in routed_rows:
                if key not in regional_accumulator:
                    regional_accumulator[key] = np.zeros(
                        N1_REGIONAL_RANK, dtype=np.complex128
                    )
                    top_accumulator[key] = np.zeros(
                        32, dtype=np.complex128
                    )
                regional_accumulator[key][
                    : values.size
                ] += values
                for mode in range(values.size):
                    for top_index in range(32):
                        top_accumulator[key][top_index] += values[mode] * (
                            top_mixing_coefficient(region, mode, top_index)
                        )
        else:
            compact = comm.bcast(compact, root=owner)
            if comm.rank == owner:
                records[region] = MappingProxyType(
                    {**compact, "coefficients": coefficients}
                )
            else:
                records[region] = MappingProxyType(compact)
        patch_digests[region] = compact["canonical_patch_mode_digest"]
        expanded_digests[region] = compact["regional_expanded_mode_digest"]
        source_action_digests[region] = compact["source_action_digest"]
        regional_ranks.append(int(compact["selected_rank"]))
        regional_candidate_ranks.append(int(compact["candidate_m_rank"]))
        regional_mass_defects.append(float(compact["mass_orthogonality"]))
        regional_residuals.append(float(compact["projected_eigen_residual"]))
        max_candidate_dimension = max(
            max_candidate_dimension, int(compact["candidate_count"])
        )
        max_projected_dimension = max(
            max_projected_dimension, int(compact["projected_dimension"])
        )
        if comm.rank == owner:
            del candidates, stiffness, mass, expanded, source, action
            if comm.rank in active_ranks:
                del local_contributions
        elif comm.rank in active_ranks:
            del candidates, local_contributions
        comm.barrier()
    if return_multilevel:
        physical_row_keys, active_row_keys, active_row_positions = (
            _physical_owned_row_layout(function_space, context)
        )
        physical_targets = _physical_row_targets(
            comm, active_row_keys, active_row_positions
        )
        regional_columns, top_raw_columns = _scatter_hash_owned_rows_to_physical_order(
            comm,
            regional_accumulator,
            top_accumulator,
            physical_targets,
            physical_row_keys,
            active_row_keys,
            active_row_positions,
        )
        basis = build_owner_local_multilevel_basis(
            active_row_keys,
            regional_columns,
            top_raw_columns,
            regional_mode_count=sum(regional_ranks),
            comm=comm,
            physical_row_keys=physical_row_keys,
            active_row_positions=active_row_positions,
            row_order_audit="physical_dofmap_owned_local_order",
        )
    else:
        basis = None
    audit = {
        "schema": "task038.n1.local-regional-rayleigh-ritz.v1",
        "macroregion_rule": "canonical_lower_cell_index_integer_division_by_2",
        "region_count": len(ordered_regions),
        "streamed_region_count": len(ordered_regions),
        "global_cell_count": global_cell_count,
        "region_cell_counts": region_cell_counts,
        "max_region_cell_count": max(region_cell_counts, default=0),
        "canonical_cell_inventory_digest": canonical_cell_inventory_digest,
        "regional_rank_cap": 16,
        "regional_ranks": tuple(regional_ranks),
        "regional_candidate_m_ranks": tuple(regional_candidate_ranks),
        "regional_mass_orthogonality_max": max(regional_mass_defects, default=0.0),
        "regional_projected_eigen_residual_max": max(regional_residuals, default=0.0),
        "max_candidate_dimension": max_candidate_dimension,
        "max_projected_dimension": max_projected_dimension,
        "region_owners": {
            repr(region): _regional_owner(region, participants[region])
            for region in sorted(inventory, key=repr)
        },
        "region_participants": {
            repr(region): participants[region]
            for region in sorted(inventory, key=repr)
        },
        "canonical_cell_order": {
            repr(region): tuple(repr(key) for key in inventory[region])
            for region in sorted(inventory, key=repr)
        },
        "canonical_patch_mode_digests": tuple(
            (repr(region), patch_digests.get(region))
            for region in sorted(inventory, key=repr)
        ),
        "regional_expanded_mode_digests": tuple(
            (repr(region), expanded_digests.get(region))
            for region in sorted(inventory, key=repr)
        ),
        "source_action_digests": tuple(
            (repr(region), source_action_digests.get(region))
            for region in sorted(inventory, key=repr)
        ),
        "regional_dense_row_operator_materialized": False,
        "participant_only_numeric_route": True,
        "source_independent": True,
        "contraction_not_run": True,
        "global_numeric_allgather": False,
        "multilevel_basis_built": return_multilevel,
        "multilevel_basis_audit": (
            dict(basis.audit) if basis is not None else None
        ),
        "physical_owned_row_order": (
            "dofmap_index_map_size_local_raw_order" if basis is not None else None
        ),
        "physical_owned_rows": (
            basis.audit["physical_owned_rows"] if basis is not None else None
        ),
        "physical_active_owned_rows": (
            basis.audit["active_owned_rows"] if basis is not None else None
        ),
        "physical_owned_slave_rows": (
            basis.audit["owned_slave_rows"] if basis is not None else None
        ),
        "canonical_key_scatter_route": (
            basis.audit["canonical_key_scatter"] if basis is not None else None
        ),
        "regional_z16_bytes": (
            basis.audit["regional_z16_bytes"] if basis is not None else None
        ),
        "top_z32_bytes": (
            basis.audit["top_z32_bytes"] if basis is not None else None
        ),
        "top_mixing_schema": (
            basis.audit["top_mixing_schema"] if basis is not None else None
        ),
        "regional_columns_semantics": (
            basis.audit["regional_columns_semantics"] if basis is not None else None
        ),
        "top_columns_semantics": (
            basis.audit["top_columns_semantics"] if basis is not None else None
        ),
        "top_rank_built": bool(basis is not None),
        "global_direct_coarse_solve": False,
    }
    del context
    if basis is None:
        return MappingProxyType(records), audit
    return MappingProxyType(records), audit, basis


def _source_value(key: Any) -> complex:
    digest = hashlib.sha256(repr(key).encode("utf-8")).digest()
    return complex(
        0.25 + int.from_bytes(digest[:8], "big") / 2.0**64,
        -0.25 - int.from_bytes(digest[8:16], "big") / 2.0**64,
    )


def small_p2p3_local_action_oracle(
    function_space: Any, mesh_data: Any, floquet_data: Any, cfg: Any
) -> dict[str, Any]:
    """Stream a canonical-key cell action for the small assembled test oracle."""

    context = _prepare_real_context(function_space, mesh_data, floquet_data, cfg)
    source_by_key = {
        key: _source_value(key) for key in context["multiplicities"]
    }
    source_keys = set(source_by_key)
    free_raw_rows = tuple(
        row
        for row, key in context["raw_to_key"].items()
        if row not in context["slave_rows"] and key in source_keys
    )
    source_by_raw = {
        int(row): source_by_key[key] * context["raw_to_scale"][int(row)]
        for row, key in context["raw_to_key"].items()
        if row not in context["slave_rows"] and key in source_keys
    }
    action_by_key = {key: 0.0j for key in source_by_key}
    cell_action_by_key: dict[Any, dict[Any, complex]] = {}
    for metadata in context["cell_metadata"]:
        block, _unused, _mass = _cell_operators(metadata, context, with_mass=False)
        x = np.asarray(
            [source_by_key[key] for key in metadata["row_keys"]],
            dtype=np.complex128,
        )
        values = block @ x
        for key, value in zip(metadata["row_keys"], values, strict=True):
            action_by_key[key] += complex(value)
        cell_action_by_key[metadata["cell_key"]] = {
            key: complex(value)
            for key, value in zip(metadata["row_keys"], values, strict=True)
        }
        del block, _unused, _mass, x, values
    return {
        "canonical_source": source_by_key,
        "source_by_raw_row": source_by_raw,
        "local_action_by_key": action_by_key,
        "cell_action_by_key": cell_action_by_key,
        "free_rows_by_canonical_key": tuple(
            sorted(free_raw_rows, key=lambda row: repr(context["raw_to_key"][row]))
        ),
        "raw_to_key": context["raw_to_key"],
        "class_count": len(context["class_digests"]),
        "production_path_references_oracle": False,
        "oracle_kind": "small_assembled_oracle_only",
    }


def build_real_local_spectral_patches(
    function_space: Any,
    mesh_data: Any,
    floquet_data: Any,
    cfg: Any,
    *,
    reuse_class_templates: bool = False,
) -> tuple[tuple[LocalSpectralPatch, ...], dict[str, Any]]:
    """Build real cell patches, optionally reusing one template per class."""

    context = _prepare_real_context(function_space, mesh_data, floquet_data, cfg)
    comm = context["comm"]
    plan = ExactClassOwnerPlan(context["class_digests"], comm)
    if reuse_class_templates:
        return _build_reused_class_template_patches(context, plan)
    for slot, digest in enumerate(plan.class_digests):
        representative = next(
            (
                metadata
                for metadata in context["cell_metadata"]
                if metadata["digest"] == digest
            ),
            None,
        )
        if representative is None:
            block = None
        else:
            block, _unused, _mass = _cell_operators(
                representative, context, with_mass=False
            )
            del _unused, _mass
        plan.register_class_representative(digest, block, slot=slot)
        if block is not None:
            del block
    gradient_fields = tuple(
        _field_component(function_space, component) for component in range(3)
    )
    for field in gradient_fields:
        context["mpc"].homogenize(field)
        context["mpc"].backsubstitution(field)
        field.x.scatter_forward()
    patches: list[LocalSpectralPatch] = []
    b_defects: list[float] = []
    m_defects: list[float] = []
    b_minimums: list[float] = []
    m_minimums: list[float] = []
    gradient_ranks: list[int] = []
    gradient_gram_defects: list[float] = []
    try:
        for patch_id, metadata in enumerate(context["cell_metadata"]):
            block, _unused, local_mass = _cell_operators(metadata, context)
            gradients = np.ascontiguousarray(
                np.column_stack(
                    [
                        np.asarray(
                            [
                                field.x.array[int(row)]
                                / context["raw_to_scale"][int(row)]
                                for row in metadata["free_rows"]
                            ],
                            dtype=np.complex128,
                        )
                        for field in gradient_fields
                    ]
                )
            )
            gradient_rank, gradient_defect = _gradient_metrics(gradients, local_mass)
            gradient_ranks.append(gradient_rank)
            gradient_gram_defects.append(gradient_defect)
            b_defects.append(_hermitian_defect(block))
            m_defects.append(_hermitian_defect(local_mass))
            b_minimums.append(float(np.min(np.linalg.eigvalsh(block))))
            m_minimums.append(float(np.min(np.linalg.eigvalsh(local_mass))))
            patch = LocalSpectralPatch(
                block,
                local_mass,
                gradients,
                patch_id=patch_id,
                exact_class_digest=metadata["digest"],
                row_keys=metadata["row_keys"],
                shared_row_multiplicity=np.asarray(
                    [context["multiplicities"][key] for key in metadata["row_keys"]],
                    dtype=np.int64,
                ),
                comm=comm,
                class_plan=plan,
            )
            patch.build()
            patches.append(patch)
            del block, _unused, local_mass, gradients
    finally:
        for field in gradient_fields:
            del field

    expected = {
        key: _source_value(key) for key in context["multiplicities"]
    }
    adjoint_errors = []
    for patch in patches:
        seed = hashlib.sha256(repr(patch.row_keys).encode("utf-8")).digest()
        x = np.resize(
            np.asarray(
                [complex(value / 17.0, -value / 23.0) for value in seed],
                dtype=np.complex128,
            ),
            len(patch.row_keys),
        )
        c = np.asarray(
            [complex(index + 1.0, -0.5 * index) for index in range(8)],
            dtype=np.complex128,
        )
        adjoint_errors.append(patch.restriction_prolongation_adjoint_error(x, c))

    local_factor_audits = {
        digest: dict(value) for digest, value in plan.local_factor_audits.items()
    }
    factor_audit_parts = comm.gather(local_factor_audits, root=0)
    if comm.rank == 0:
        global_factor_audits: dict[str, dict[str, Any]] = {}
        for part in factor_audit_parts:
            for digest, value in part.items():
                if digest in global_factor_audits:
                    raise RuntimeError(
                        f"exact class {digest} has multiple factor owners"
                    )
                global_factor_audits[digest] = dict(value)
        if set(global_factor_audits) != set(plan.class_digests):
            raise RuntimeError("factor-owner audit is incomplete")
    else:
        global_factor_audits = None
    global_factor_audits = comm.bcast(global_factor_audits, root=0)

    patch_tuple = tuple(patches)
    audit = {
        "schema": "task038.n1.real-local-cell-adapter.v1",
        "fixture": "real_p2_h50_serial_cell_tensor_smoke",
        "degree": context["degree"],
        "cell_count": context["owned_cells"],
        "patch_count": len(patches),
        "row_count_min": min(len(patch.row_keys) for patch in patches),
        "row_count_max": max(len(patch.row_keys) for patch in patches),
        "class_count": len(plan.class_digests),
        "class_digests": tuple(plan.class_digests),
        "class_owners": dict(plan.owners),
        "local_class_digests": tuple(context["local_class_digests"]),
        "class_inventory": "global_sorted_exact_class_digests",
        "class_factor_registration": (
            "fixed_global_class_slots_lowest_representative_to_hash_owner"
        ),
        "owner_factor_count": plan.factor_count,
        "owner_factor_bytes": plan.factor_bytes,
        "factor_audits_by_class": global_factor_audits,
        "factorization_relative_error_max": max(
            float(value["factorization_relative_error"])
            for value in global_factor_audits.values()
        ),
        "fixed_solve_residual_max": max(
            float(value["fixed_rhs_solve_residual"])
            for value in global_factor_audits.values()
        ),
        "global_owner_factor_count": int(
            comm.allreduce(plan.factor_count, op=MPI.SUM)
        ),
        "B0_hermitian_relative_defect": max(b_defects),
        "M_local_hermitian_relative_defect": max(m_defects),
        "B0_min_eigenvalue": min(b_minimums),
        "M_local_min_eigenvalue": min(m_minimums),
        "gradient_rank_min": min(gradient_ranks),
        "gradient_m_gram_relative_defect_max": max(gradient_gram_defects),
        "projected_eigen_residual_max": max(
            patch.audit["generalized_eigen_residual"] for patch in patches
        ),
        "pou_closure_relative_error": _distributed_pou_closure(
            function_space, context, patches, expected
        ),
        "pou_closure_route": (
            "owner_local_fem_function_scatter_reverse_insert_add"
        ),
        "restriction_prolongation_adjoint_relative_error_max": max(adjoint_errors),
        "independent_global_assembled_oracle": None,
        "production_path_references_oracle": False,
        "oracle_contract": "small_assembled_oracle_only_p2_p3_test_path",
        "mode_digest": _mode_digest(
            patch_tuple,
            tuple(metadata["cell_key"] for metadata in context["cell_metadata"]),
        ),
        "dense_workspace_released": all(
            patch.audit["construction_workspace_released"]
            and patch.block is None
            and patch.local_mass is None
            for patch in patches
        ),
        "forbidden_objects": {
            "global_numeric_allgather": False,
            "global_aij": False,
            "global_schur": False,
            "static_condensation": False,
            "trace_harmonic_backend": False,
            "per_patch_retained_dense_block": False,
        },
        "orientation": "DOLFINx Basix T_apply/Tt_apply cell semantics",
        "mpc_expansion": "finalized Floquet direct primal coefficients, slaves excluded from free rows",
        "patch_ownership": "owned_cells_only; ghost_cells_metadata_only",
        "ghost_cells_patched": False,
        "imported_master_metadata": dict(
            context["imported_master_metadata"]
        ),
        "imported_master_metadata_route": (
            "bounded_global_id_request_gather_bcast_known_key_response"
        ),
        "canonical_packet_key": "canonical_cell_key+canonical_row_key+mode_index",
        "multiplicity_collective": "bounded_canonical_metadata_gather_bcast",
        "gradient_definition": "three interpolated constant H(curl) coordinate fields e_x,e_y,e_z after finalized MPC homogenize/backsubstitution",
        "pou_rule": "inverse canonical multiplicity over every cell patch row",
        "repeat_identity": "caller_builds_independent_second_adapter_pass",
    }
    return patch_tuple, audit


__all__ = (
    "build_real_local_regional_rayleigh_ritz",
    "build_real_local_spectral_patches",
    "small_p2p3_local_action_oracle",
)
