"""Exact cell-local vector-field export and batched distributed sampling.

For affine hexahedra, the three components of a first-family H(curl) field of
degree at most six and its curl lie in the componentwise Q6 polynomial space.
Interpolating both into vector DGQ6 therefore preserves the polynomial fields
cell by cell; it does not pass through a visualization field.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CellLocalVectorFieldExport:
    """DGQ6 copies for evaluation, while retaining the recovered source field."""

    source_electric: object
    electric_dgq6: object
    curl_electric_dgq6: object
    source_degree: int
    target_degree: int = 6
    representation: str = "affine_hex_n1e_to_cell_local_vector_dgq6_v1"


def _interpolation_points(element) -> np.ndarray:
    points = element.interpolation_points
    return np.asarray(points() if callable(points) else points, dtype=np.float64)


def _first_collective_error(comm, local_error: str | None) -> str | None:
    for rank, error in enumerate(comm.allgather(local_error)):
        if error is not None:
            return f"rank {rank}: {error}"
    return None


def _axis_aligned_affine_cell_error(mesh) -> str | None:
    """Check owned hexahedra against the Cartesian affine reference map."""

    import basix

    reference_vertices = np.asarray(
        basix.cell.geometry(basix.CellType.hexahedron), dtype=np.float64
    )
    reference_origin = np.flatnonzero(
        np.all(np.isclose(reference_vertices, 0.0), axis=1)
    )
    if reference_origin.size != 1:
        return "Basix hexahedron has no unique reference origin"
    edge_rows = []
    for axis in range(3):
        target = np.zeros(3, dtype=np.float64)
        target[axis] = 1.0
        matches = np.flatnonzero(
            np.all(np.isclose(reference_vertices, target), axis=1)
        )
        if matches.size != 1:
            return "Basix hexahedron has no unique reference edge vertex"
        edge_rows.append(int(matches[0]))

    topological_dimension = int(mesh.topology.dim)
    cell_map = mesh.topology.index_map(topological_dimension)
    owned_cell_count = int(cell_map.size_local)
    origin_index = int(reference_origin[0])
    for cell in range(owned_cell_count):
        geometry_dofs = np.asarray(mesh.geometry.dofmap[cell], dtype=np.int64)
        coordinates = np.asarray(mesh.geometry.x[geometry_dofs, :3], dtype=np.float64)
        if len(geometry_dofs) != 8 or coordinates.shape != (8, 3):
            return f"owned cell {cell} does not have eight linear hexahedron vertices"
        tolerance = 1.0e-11 * max(1.0, float(np.max(np.abs(coordinates))))
        origin = coordinates[origin_index]
        edges = np.asarray(
            [coordinates[row] - origin for row in edge_rows], dtype=np.float64
        )
        physical_axes: list[int] = []
        for edge in edges:
            nonzero_axes = np.flatnonzero(np.abs(edge) > tolerance)
            if nonzero_axes.size != 1:
                return f"owned cell {cell} has a non-axis-aligned reference edge"
            physical_axes.append(int(nonzero_axes[0]))
        if len(set(physical_axes)) != 3:
            return f"owned cell {cell} does not span three distinct physical axes"
        predicted_vertices = origin + reference_vertices @ edges
        if float(np.max(np.abs(predicted_vertices - coordinates))) > tolerance:
            return f"owned cell {cell} is not an affine Cartesian hexahedron"
    return None


def prepare_cell_local_vector_field_export(electric_field) -> CellLocalVectorFieldExport:
    """Prepare exact DGQ6 evaluations of an affine-hexahedron N1E field/curl.

    The input coefficient field is returned unchanged in ``source_electric``.
    This helper deliberately rejects other geometries or element families
    instead of silently routing through a lower-degree display space.
    """

    import basix
    import ufl
    from dolfinx import fem

    function_space = electric_field.function_space
    mesh = function_space.mesh
    if str(mesh.topology.cell_name()) != "hexahedron":
        raise ValueError("exact DGQ6 vector export currently requires hexahedra")
    if int(mesh.geometry.dim) != 3 or int(mesh.geometry.cmap.degree) != 1:
        raise ValueError("exact DGQ6 vector export requires affine 3D geometry")

    source_element = function_space.element.basix_element
    source_degree = int(source_element.degree)
    if source_element.family != basix.ElementFamily.N1E:
        raise ValueError("exact DGQ6 vector export requires the first-family N1E element")
    if not 1 <= source_degree <= 6:
        raise ValueError("source N1E degree must be in [1, 6]")
    if tuple(source_element.value_shape) != (3,):
        raise ValueError("source electric field must have three vector components")

    geometry_error = None
    try:
        geometry_error = _axis_aligned_affine_cell_error(mesh)
    except (AttributeError, IndexError, RuntimeError, TypeError, ValueError) as exc:
        # Synchronize a rank-local geometry inspection failure.
        geometry_error = f"could not inspect affine hexahedron geometry: {exc}"
    geometry_error = _first_collective_error(mesh.comm, geometry_error)
    if geometry_error is not None:
        raise ValueError(
            "DGQ6 exact export requires axis-aligned affine hexahedra; "
            f"{geometry_error}"
        )

    target_space = fem.functionspace(mesh, ("DG", 6, (3,)))
    electric_dgq6 = fem.Function(target_space, name="electric_code_cell_dgq6")
    electric_dgq6.interpolate(electric_field)
    electric_dgq6.x.scatter_forward()

    curl_dgq6 = fem.Function(target_space, name="curl_electric_code_cell_dgq6")
    curl_expression = fem.Expression(
        ufl.curl(electric_field),
        _interpolation_points(target_space.element),
    )
    curl_dgq6.interpolate(curl_expression)
    curl_dgq6.x.scatter_forward()
    return CellLocalVectorFieldExport(
        source_electric=electric_field,
        electric_dgq6=electric_dgq6,
        curl_electric_dgq6=curl_dgq6,
        source_degree=source_degree,
    )


def sample_cell_local_vector_fields(
    fields: Mapping[str, object],
    points_nm: np.ndarray,
    *,
    batch_size: int = 32768,
    root: int = 0,
) -> dict[str, np.ndarray] | None:
    """Evaluate vector fields in point batches, using owned-cell evaluation.

    All fields must use the same distributed mesh.  Geometric point searches
    are shared across fields.  The full ordered sample arrays are returned on
    ``root`` only; other ranks return ``None``.  Points with multiple owned
    incident cells are rejected as ambiguous so each value has one cell trace.
    """

    from dolfinx import geometry

    if not fields or any(not isinstance(name, str) or not name for name in fields):
        raise ValueError("at least one named vector field is required")

    names = tuple(fields)
    functions = tuple(fields[name] for name in names)
    mesh = functions[0].function_space.mesh
    comm = mesh.comm
    local_error = None
    points = np.empty((0, 3), dtype=np.float64)
    try:
        if int(batch_size) != batch_size or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if not 0 <= int(root) < int(comm.size):
            raise ValueError("root rank is outside the field mesh communicator")
        for function in functions:
            if function.function_space.mesh is not mesh:
                raise ValueError("all sampled fields must use the same mesh object")
            if tuple(function.function_space.element.value_shape) != (3,):
                raise ValueError("all sampled fields must be three-component vectors")
        points = np.asarray(points_nm, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
            raise ValueError("points_nm must be a finite array with shape (npoints, 3)")
        if points.shape[0] == 0:
            raise ValueError("at least one point is required")
    except (OverflowError, TypeError, ValueError) as exc:
        local_error = str(exc)
    validation_error = _first_collective_error(comm, local_error)
    if validation_error is not None:
        raise ValueError(f"invalid distributed vector-field sampling request; {validation_error}")

    point_bytes = np.ascontiguousarray(points, dtype="<f8").tobytes()
    local_contract = (
        names,
        int(batch_size),
        int(root),
        tuple(points.shape),
        hashlib.sha256(point_bytes).hexdigest(),
    )
    contracts = comm.allgather(local_contract)
    if any(contract != contracts[0] for contract in contracts[1:]):
        raise ValueError("all ranks must use the same field order, point array, batch size, and root")

    topological_dimension = int(mesh.topology.dim)
    local_error = None
    tree = None
    try:
        tree = geometry.bb_tree(mesh, topological_dimension)
    except (RuntimeError, TypeError, ValueError) as exc:
        local_error = f"could not build local cell tree: {exc}"
    tree_error = _first_collective_error(comm, local_error)
    if tree_error is not None:
        raise RuntimeError(f"distributed vector-field point search failed; {tree_error}")

    cell_map = mesh.topology.index_map(topological_dimension)
    owned_cell_count = int(cell_map.size_local)
    local_index_chunks: list[np.ndarray] = []
    local_value_chunks: dict[str, list[np.ndarray]] = {name: [] for name in names}

    for start in range(0, len(points), int(batch_size)):
        stop = min(start + int(batch_size), len(points))
        point_batch = points[start:stop]
        try:
            candidates = geometry.compute_collisions_points(tree, point_batch)
            collisions = geometry.compute_colliding_cells(mesh, candidates, point_batch)
            sample_indices: list[int] = []
            sample_cells: list[int] = []
            for row in range(len(point_batch)):
                owned_links = [
                    int(cell)
                    for cell in collisions.links(row)
                    if int(cell) < owned_cell_count
                ]
                if len(owned_links) > 1:
                    raise ValueError(
                        f"sample point {start + row} lies on an owned-cell interface; "
                        "common-volume Gauss points must be interior to each mesh cell"
                    )
                if owned_links:
                    sample_indices.append(start + row)
                    sample_cells.append(owned_links[0])

            if not sample_indices:
                continue
            global_indices = np.asarray(sample_indices, dtype=np.int64)
            local_points = points[global_indices]
            cells = np.asarray(sample_cells, dtype=np.int32)
            batch_values: dict[str, np.ndarray] = {}
            for name, function in zip(names, functions, strict=True):
                values = np.asarray(function.eval(local_points, cells), dtype=np.complex128)
                values = values.reshape((len(global_indices), -1))
                if values.shape[1] != 3 or not np.all(np.isfinite(values)):
                    raise ValueError(f"field {name!r} returned invalid vector samples")
                batch_values[name] = values
            local_index_chunks.append(global_indices)
            for name in names:
                local_value_chunks[name].append(batch_values[name])
        except (IndexError, RuntimeError, TypeError, ValueError) as exc:
            local_error = f"sample batch beginning at row {start}: {exc}"
            break

    sampling_error = _first_collective_error(comm, local_error)
    if sampling_error is not None:
        raise RuntimeError(f"distributed vector-field evaluation failed; {sampling_error}")

    if local_index_chunks:
        local_indices = np.concatenate(local_index_chunks)
        local_values = {
            name: np.concatenate(chunks, axis=0)
            for name, chunks in local_value_chunks.items()
        }
    else:
        local_indices = np.zeros(0, dtype=np.int64)
        local_values = {name: np.zeros((0, 3), dtype=np.complex128) for name in names}

    packets = comm.gather((local_indices, local_values), root=int(root))
    if int(comm.rank) != int(root):
        return None

    output: dict[str, np.ndarray] | None = None
    root_error = None
    if int(comm.rank) == int(root):
        try:
            output = {
                name: np.zeros((len(points), 3), dtype=np.complex128) for name in names
            }
            owners = np.zeros(len(points), dtype=np.int32)
            for rank_indices, rank_values in packets:
                owners[rank_indices] += 1
                for name in names:
                    output[name][rank_indices] = rank_values[name]
            if np.any(owners != 1):
                missing = np.flatnonzero(owners == 0)
                repeated = np.flatnonzero(owners > 1)
                root_error = (
                    "each field sample must have exactly one owned mesh cell; "
                    f"missing={missing[:5].tolist()}, repeated={repeated[:5].tolist()}"
                )
        except (IndexError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            root_error = f"could not merge distributed field samples: {exc}"
    root_error = comm.bcast(root_error, root=int(root))
    if root_error is not None:
        raise RuntimeError(root_error)
    return output
