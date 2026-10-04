"""Independent selected top/x action contractions, staged without FE execution.

This helper receives an existing p6 N1E hexahedron space, finalized MPC and
three already backsubstituted/scattered Functions. It creates no mesh, space,
form, mode, carrier, factor or PDE. Imports of Basix/DOLFINx are lazy; the
embedded --synthetic-tests exercise NumPy algebra/geometry and source contracts
only. This is a selected-action/quadrature check, not full C/D qualification.

If b_FE[j] = integral phase * conjugate(phi_j,x), MPC assembly gives b=K^H b_FE.
For native u with slave slots zero, vdot(u,b) = integral phase*conj((K u)_x).
The public Function.eval route includes actual Piola/orientation transforms.
The phase is never conjugated and the vdot arguments must not be reversed.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


OPERATION_RTOL = 1.0e-10
EXPECTED_AXES = ((0.0, 16.5, 33.5, 50.0), (0.0, 12.5, 25.0), (-10.0, 0.0, 120.0, 130.0))
MAX_CHUNK_SIZE = 512
P6_CELL_DOFS = 882
_REFERENCE_VERTICES = np.array(
    [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
     [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]], dtype=np.float64,
)


@dataclass(frozen=True)
class FacetRectangle:
    facet: int
    cell: int
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zplane: float

    @property
    def area(self) -> float:
        return (self.xmax - self.xmin) * (self.ymax - self.ymin)


def _hash_array(value: np.ndarray) -> str:
    if not value.flags.c_contiguous:
        raise ValueError("identity hashing requires a contiguous native array")
    digest = hashlib.sha256()
    digest.update(str(value.dtype).encode())
    digest.update(str(value.shape).encode())
    digest.update(memoryview(value).cast("B"))
    return digest.hexdigest()


def operation_scaled_difference(left: complex, right: complex, scale: float) -> dict[str, Any]:
    """Use the declared absolute operation scale with no denominator floor."""
    if not all(np.isfinite(v) for v in (left, right, scale)) or scale < 0:
        raise ValueError("nonfinite contraction/scale or negative operation scale")
    # Finite inputs can still overflow during subtraction or normalization.
    error = float(abs(complex(left) - complex(right)))
    limit = float(OPERATION_RTOL * scale)
    if not math.isfinite(error) or not math.isfinite(limit):
        raise ValueError("computed contraction error/limit is nonfinite")
    scaled_error = None if scale == 0 else float(error / scale)
    if scaled_error is not None and not math.isfinite(scaled_error):
        raise ValueError("computed normalized contraction error is nonfinite")
    return {
        "absolute_error": error, "operation_scale": float(scale), "limit": limit,
        "scaled_error": scaled_error,
        "exact_zero_scale": bool(scale == 0),
        "passed": bool(error == 0 if scale == 0 else error <= limit),
    }


def _admit(gate: Callable, event: Callable, label: str, items: list[dict[str, Any]], **facts: Any) -> None:
    requested = sum(int(item["bytes"]) for item in items)
    record = {
        "requested_bytes": requested, "live_named_bytes": requested,
        "workspace_estimate_bytes": sum(int(i["bytes"]) for i in items if i["classification"] == "workspace_estimate"),
        "items": items, "estimate_is_rss": False,
        "whole_process_3gib_watchdog_required": True, **facts,
    }
    event({"kind": "reference_allocation_before", "label": label, **record})
    if gate(label, record) is False:
        raise MemoryError(f"reference allocation gate rejected {label}")
    event({"kind": "reference_allocation_admitted", "label": label, **record})


def _item(name: str, count: int, width: int, classification: str = "named_array") -> dict[str, Any]:
    return {"name": name, "count": int(count), "itemsize": int(width), "bytes": int(count) * int(width), "classification": classification}


def reference_workspace_items(points: int, *, rule_points: int, ndofs: int = P6_CELL_DOFS) -> list[dict[str, Any]]:
    """Conservative admission model informed by DOLFINx 0.10 Function.h eval.

    Public eval allocates real reference basis (N,D,3), one transformed basis
    (D,3), complex cell coefficients D, and reference/J/K/det arrays. Basix
    internal polynomial scratch and transformation scratch are modeled more
    generously below. This is not a proven allocator peak; retained library
    allocations and process memory are covered by the caller watchdog.
    """
    if points < 1 or points > MAX_CHUNK_SIZE or rule_points < points or ndofs != P6_CELL_DOFS:
        raise ValueError("unsupported reference workspace dimensions")
    return [
        _item("retained_reference_points", rule_points * 2, 8),
        _item("retained_reference_weights", rule_points, 8),
        _item("physical_coordinates", points * 3, 8),
        _item("physical_weights", points, 8),
        _item("cell_ids", points, 4),
        _item("field_eval_output", points * 3, 16),
        _item("bounded_three_state_field_x_cache", points * 3, 16),
        _item("complex_phase_argument_phase_conjugate_product", points * 4, 16),
        _item("phase_field_magnitudes_scale_terms", points * 3, 8),
        _item("point_bounds_checks", points * 3, 1),
        _item("eval_reference_basis", points * ndofs * 3, 8, "workspace_estimate"),
        _item("eval_transformed_basis", ndofs * 3, 8, "workspace_estimate"),
        _item("eval_complex_cell_coefficients", ndofs, 16, "workspace_estimate"),
        _item("eval_reference_jacobian_inverse_determinant", points * 22, 8, "workspace_estimate"),
        _item("eval_geometry_tabulation_and_pullback_scratch", 4 * 8 * 4 + 8 * 3 + 32, 8, "workspace_estimate"),
        _item("basix_polynomial_tabulation_scratch_conservative", 4 * points * (6 + 1) ** 3 * 3, 8, "workspace_estimate"),
        _item("basis_transformation_scratch_conservative", 2 * ndofs * ndofs, 8, "workspace_estimate"),
        _item("additional_basis_tabulation_scratch_conservative", 2 * points * ndofs * 3, 8, "workspace_estimate"),
    ]


def rectangle_from_geometry(facet: int, cell: int, face_xyz: np.ndarray, cell_xyz: np.ndarray, zplane: float) -> FacetRectangle:
    """Require literal degree-one, axis-aligned affine vertex geometry."""
    if face_xyz.shape != (4, 3) or cell_xyz.shape != (8, 3):
        raise ValueError("expected four facet vertices and eight cell coordinate DoFs")
    if not np.isfinite(face_xyz).all() or not np.isfinite(cell_xyz).all() or not math.isfinite(zplane):
        raise ValueError("nonfinite geometry")
    if np.unique(cell_xyz, axis=0).shape[0] != 8 or np.unique(face_xyz, axis=0).shape[0] != 4:
        raise ValueError("duplicate geometry vertices")
    origin = cell_xyz[0]
    affine_columns = np.column_stack((cell_xyz[1] - origin, cell_xyz[2] - origin, cell_xyz[4] - origin))
    if not np.all(np.count_nonzero(affine_columns, axis=0) == 1) or not np.all(np.count_nonzero(affine_columns, axis=1) == 1):
        raise ValueError("cell map is not axis-aligned affine")
    expected = origin + _REFERENCE_VERTICES @ affine_columns.T
    if not np.array_equal(expected, cell_xyz):
        raise ValueError("cell coordinate ordering/map is not literal affine geometry")
    if not np.all(face_xyz[:, 2] == zplane) or not float(cell_xyz[:, 2].max()) == zplane:
        raise ValueError("tagged facet is not on the exact top plane of its cell")
    if not all(any(np.array_equal(point, vertex) for vertex in cell_xyz) for point in face_xyz):
        raise ValueError("facet vertices do not belong to associated cell")
    xmin, ymin = face_xyz[:, :2].min(axis=0)
    xmax, ymax = face_xyz[:, :2].max(axis=0)
    expected_face = {(float(x), float(y), zplane) for x in (xmin, xmax) for y in (ymin, ymax)}
    if set(map(tuple, face_xyz)) != expected_face or not (xmax > xmin and ymax > ymin):
        raise ValueError("facet is not a nondegenerate axis-aligned rectangle")
    return FacetRectangle(int(facet), int(cell), float(xmin), float(xmax), float(ymin), float(ymax), zplane)


def validate_rectangles(rectangles: list[FacetRectangle]) -> None:
    if len(rectangles) != 6 or len({r.facet for r in rectangles}) != 6 or len({r.cell for r in rectangles}) != 6:
        raise ValueError("expected exactly six unique top exterior facets/cells")
    expected = {(x0, x1, y0, y1, 130.0) for x0, x1 in zip(EXPECTED_AXES[0][:-1], EXPECTED_AXES[0][1:]) for y0, y1 in zip(EXPECTED_AXES[1][:-1], EXPECTED_AXES[1][1:])}
    actual = {(r.xmin, r.xmax, r.ymin, r.ymax, r.zplane) for r in rectangles}
    if actual != expected or sum(r.area for r in rectangles) != 1250.0:
        raise ValueError("top facets do not cover the exact target fixture once")


def map_chunk(rectangle: FacetRectangle, reference_points: np.ndarray, reference_weights: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    count = len(reference_weights)
    if reference_points.shape != (count, 2) or not count:
        raise ValueError("invalid quadrature chunk shape")
    if not np.isfinite(reference_points).all() or not np.isfinite(reference_weights).all() or np.any(reference_weights <= 0):
        raise ValueError("nonfinite rule or nonpositive quadrature weights")
    if np.any(reference_points < 0) or np.any(reference_points > 1):
        raise ValueError("reference quadrature points outside unit square")
    xyz = np.empty((count, 3), dtype=np.float64)
    xyz[:, 0] = rectangle.xmin + (rectangle.xmax - rectangle.xmin) * reference_points[:, 0]
    xyz[:, 1] = rectangle.ymin + (rectangle.ymax - rectangle.ymin) * reference_points[:, 1]
    xyz[:, 2] = rectangle.zplane
    if np.any(xyz[:, 0] < rectangle.xmin) or np.any(xyz[:, 0] > rectangle.xmax) or np.any(xyz[:, 1] < rectangle.ymin) or np.any(xyz[:, 1] > rectangle.ymax) or not np.all(xyz[:, 2] == rectangle.zplane):
        raise ValueError("mapped points escaped their associated physical facet/cell")
    return xyz, np.ascontiguousarray(reference_weights * rectangle.area), np.full(count, rectangle.cell, dtype=np.int32)


def _phase_chunk(xyz: np.ndarray, alpha: complex, gamma: complex, kz: complex, zplane: float) -> np.ndarray:
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all() or not all(np.isfinite(v) for v in (alpha, gamma, kz, zplane)):
        raise ValueError("nonfinite phase input or physical point dimension mismatch")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        phase = np.exp(1j * (alpha * xyz[:, 0] + gamma * xyz[:, 1] + kz * (xyz[:, 2] - zplane)))
    if not np.isfinite(phase).all():
        raise ValueError("nonfinite complex phase")
    return phase


def _contract_phased(weights: np.ndarray, field_component: np.ndarray, phase: np.ndarray) -> tuple[complex, float]:
    if field_component.shape != weights.shape or phase.shape != weights.shape or weights.ndim != 1:
        raise ValueError("contraction chunk dimension mismatch")
    if not all(np.isfinite(v).all() for v in (weights, field_component, phase)) or np.any(weights <= 0):
        raise ValueError("nonfinite contraction input or nonpositive physical weights")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        product = weights * phase * np.conjugate(field_component)
        value = complex(np.sum(product, dtype=np.complex128))
        scale = float(np.sum(weights * np.abs(phase) * np.abs(field_component), dtype=np.float64))
    if not np.isfinite(value) or not np.isfinite(scale):
        raise ValueError("nonfinite reference result")
    return value, scale


def contract_chunk(xyz: np.ndarray, weights: np.ndarray, field_component: np.ndarray, alpha: complex, gamma: complex, kz: complex, zplane: float) -> tuple[complex, float]:
    if xyz.shape != (len(weights), 3):
        raise ValueError("contraction physical point count mismatch")
    return _contract_phased(weights, field_component, _phase_chunk(xyz, alpha, gamma, kz, zplane))


def _assert_same_native_layout(V: Any, other: Any) -> dict[str, Any]:
    """MPC.finalize replaces its FunctionSpace wrapper; compare native maps."""
    if other.mesh is not V.mesh or other.element.signature != V.element.signature:
        raise ValueError("MPC/Function mesh or element signature differs from supplied space")
    original, candidate = V.dofmap, other.dofmap
    for dofmap in (original, candidate):
        index = dofmap.index_map
        if index.num_ghosts or index.size_local != original.index_map.size_local or index.size_global != original.index_map.size_global or tuple(index.local_range) != (0, original.index_map.size_local) or dofmap.index_map_bs != 1 or dofmap.bs != 1:
            raise ValueError("MPC/Function native ownership/blocking differs from supplied space")
    rows = int(original.index_map.size_local)
    numbering = original.index_map.local_to_global(np.arange(rows, dtype=np.int32))
    candidate_numbering = candidate.index_map.local_to_global(np.arange(rows, dtype=np.int32))
    if not np.array_equal(numbering, np.arange(rows, dtype=np.int64)) or not np.array_equal(numbering, candidate_numbering):
        raise ValueError("MPC/Function global native numbering differs")
    digest = hashlib.sha256()
    for cell in range(int(V.mesh.topology.index_map(3).size_local)):
        source, target = np.asarray(original.cell_dofs(cell)), np.asarray(candidate.cell_dofs(cell))
        if not np.array_equal(source, target):
            raise ValueError("MPC/Function cell DoF ordering differs from supplied space")
        digest.update(memoryview(source).cast("B"))
    return {"element_signature": V.element.signature, "global_numbering_sha256": _hash_array(np.asarray(numbering)), "cell_dof_order_sha256": digest.hexdigest()}


def _validate_states(V: Any, mpc: Any, native_fields: tuple, independent_states: np.ndarray) -> dict[str, Any]:
    rows = int(V.dofmap.index_map.size_local) * int(V.dofmap.index_map_bs)
    if not mpc.finalized:
        raise ValueError("MPC must already be finalized")
    layout_identity = _assert_same_native_layout(V, mpc.function_space)
    if V.mesh.comm.size != 1 or V.mesh.comm.rank != 0 or V.dofmap.index_map.num_ghosts != 0 or V.dofmap.index_map.size_global != V.dofmap.index_map.size_local or V.dofmap.index_map_bs != 1 or V.dofmap.bs != 1:
        raise ValueError("reference requires MPI1 unghosted native scalar ownership")
    if independent_states.shape != (rows, 3) or independent_states.dtype != np.complex128 or not independent_states.flags.c_contiguous or not np.isfinite(independent_states).all() or len(native_fields) != 3:
        raise ValueError("expected three finite contiguous complex128 native states")
    slaves = np.asarray(mpc.slaves)
    flags = np.asarray(mpc.is_slave)
    if slaves.ndim != 1 or len(slaves) == 0 or len(np.unique(slaves)) != len(slaves) or np.any(slaves < 0) or np.any(slaves >= rows) or flags.shape != (rows,) or not np.array_equal(np.flatnonzero(flags), np.sort(slaves)):
        raise ValueError("MPC slave indexing/ownership is inconsistent")
    if not np.all(independent_states[slaves, :] == 0):
        raise ValueError("independent contraction states must have literal zero slave slots")
    coefficients, offsets = mpc.coefficients()
    coefficients, offsets = np.asarray(coefficients), np.asarray(offsets)
    if offsets.shape != (rows + 1,) or offsets[0] != 0 or np.any(np.diff(offsets) < 0) or offsets[-1] != len(coefficients) or not np.isfinite(coefficients).all():
        raise ValueError("invalid public MPC coefficient/offset mapping")
    master_mask = flags == 0
    constraint_error_max = 0.0
    for state_index, field in enumerate(native_fields):
        _assert_same_native_layout(V, field.function_space)
        expanded = np.asarray(field.x.array)
        if expanded.shape != (rows,) or expanded.dtype != np.complex128 or not expanded.flags.c_contiguous or not np.isfinite(expanded).all():
            raise ValueError("expanded Function space/native ordering/dtype is inconsistent")
        if np.shares_memory(expanded, independent_states):
            raise ValueError("independent master state aliases expanded Function storage")
        if not np.array_equal(expanded[master_mask], independent_states[master_mask, state_index]):
            raise ValueError("backsubstitution changed an independent master coefficient")
        for slave in slaves:
            masters = np.asarray(mpc.masters.links(int(slave)))
            coeff = coefficients[offsets[slave]:offsets[slave + 1]]
            if len(masters) != len(coeff) or not len(masters) or np.any(masters < 0) or np.any(masters >= rows) or np.any(flags[masters]):
                raise ValueError("slave must reference admitted local independent master coefficients")
            wanted = complex(np.sum(coeff * independent_states[masters, state_index], dtype=np.complex128))
            scale = float(np.sum(np.abs(coeff) * np.abs(independent_states[masters, state_index]), dtype=np.float64))
            metric = operation_scaled_difference(complex(expanded[slave]), wanted, scale)
            if not metric["passed"]:
                raise ValueError("expanded Function violates public MPC constraint coefficients")
            constraint_error_max = max(constraint_error_max, metric["absolute_error"])
    return {"rows": rows, "owned_range": [0, rows], "slaves": len(slaves), **layout_identity, "master_state_sha256": _hash_array(independent_states), "expanded_state_sha256": [_hash_array(np.asarray(f.x.array)) for f in native_fields], "slaves_sha256": _hash_array(slaves), "coefficients_sha256": _hash_array(coefficients), "offsets_sha256": _hash_array(offsets), "constraint_max_absolute_error": constraint_error_max, "slave_slots_zero": True, "constraint_equations_checked": int(3 * len(slaves))}


def _actual_rectangles(mesh_data: Any, cfg: Any, gate: Callable, event: Callable) -> list[FacetRectangle]:
    from dolfinx import mesh as dx_mesh

    msh = mesh_data.mesh
    if msh.topology.dim != 3 or msh.geometry.dim != 3 or msh.topology.cell_type.name != "hexahedron" or msh.geometry.cmap.degree != 1 or msh.geometry.cmap.dim != 8 or msh.geometry.x.dtype != np.float64:
        raise ValueError("expected 3D hexahedron mesh with degree-one float64 geometry")
    if msh.topology.index_map(3).size_local != 18 or msh.topology.index_map(3).num_ghosts or (cfg.x_min, cfg.x_max, cfg.y_min, cfg.y_max, cfg.domain_z_min, cfg.domain_z_max) != (0, 50, 0, 25, -10, 130):
        raise ValueError("mesh/config does not have the admitted original target fixture bounds")
    _admit(gate, event, "reference_geometry_connectivity", [_item("geometry_and_connectivity_small_copies", 18 * 8 * 3 + 6 * 4 * 3 + 256, 8)], calls="public topology connectivity and entities_to_geometry only")
    msh.topology.create_connectivity(2, 3)
    f_to_c = msh.topology.connectivity(2, 3)
    exterior = set(map(int, dx_mesh.exterior_facet_indices(msh.topology)))
    facets = np.asarray(mesh_data.facet_tags.find(int(cfg.tags.z_max)), dtype=np.int32)
    if len(facets) != 6 or len(np.unique(facets)) != 6 or not set(map(int, facets)).issubset(exterior):
        raise ValueError("top tags must identify exactly six unique owned exterior facets")
    geometry_dofs = dx_mesh.entities_to_geometry(msh, 2, facets, permute=False)
    if geometry_dofs.shape != (6, 4):
        raise ValueError("unexpected top facet geometric DoF shape")
    rectangles = []
    all_cell_vertices = msh.geometry.x[msh.geometry.dofmap]
    for axis, expected in enumerate(EXPECTED_AXES):
        if not np.array_equal(np.unique(all_cell_vertices[:, :, axis]), np.asarray(expected)):
            raise ValueError("actual mesh axes differ from the frozen 18-cell fixture")
    # Validate all cells' affine ordering, including the two lower z layers.
    for cell, xyz in enumerate(all_cell_vertices):
        top_xyz = xyz[xyz[:, 2] == xyz[:, 2].max()]
        rectangle_from_geometry(-1, cell, top_xyz, xyz, float(xyz[:, 2].max()))
    actual_boxes = {tuple(xyz.min(axis=0)) + tuple(xyz.max(axis=0)) for xyz in all_cell_vertices}
    expected_boxes = {(x0, y0, z0, x1, y1, z1) for x0, x1 in zip(EXPECTED_AXES[0][:-1], EXPECTED_AXES[0][1:]) for y0, y1 in zip(EXPECTED_AXES[1][:-1], EXPECTED_AXES[1][1:]) for z0, z1 in zip(EXPECTED_AXES[2][:-1], EXPECTED_AXES[2][1:])}
    if actual_boxes != expected_boxes or len(actual_boxes) != 18:
        raise ValueError("actual cells do not cover every admitted affine hex exactly once")
    for facet, gdofs in zip(facets, geometry_dofs):
        cells = np.asarray(f_to_c.links(int(facet)))
        if cells.shape != (1,) or not 0 <= cells[0] < 18:
            raise ValueError("exterior top facet must associate with one owned cell")
        rectangles.append(rectangle_from_geometry(int(facet), int(cells[0]), msh.geometry.x[gdofs], all_cell_vertices[cells[0]], float(cfg.domain_z_max)))
    validate_rectangles(rectangles)
    return sorted(rectangles, key=lambda r: (r.xmin, r.ymin, r.facet))


def run_reference(*, V: Any, mesh_data: Any, mpc: Any, cfg: Any, selected_modes: tuple, selected_indices: tuple, native_fields: tuple, independent_states: np.ndarray, quadrature_degree: int, allocation_gate: Callable, event: Callable, output_dir: Any = None, chunk_size: int = 256) -> dict[str, Any]:
    """Run only after caller admits actual FE and an active 3GiB watchdog.

    output_dir is accepted for compatibility; this helper does not write files.
    The caller owns arrays, their persistence and the primary contraction check.
    """
    if not callable(allocation_gate) or not callable(event):
        raise ValueError("allocation gate and durable event callback are mandatory")
    if type(chunk_size) is not int or not 1 <= chunk_size <= MAX_CHUNK_SIZE or type(quadrature_degree) is not int or quadrature_degree < 1:
        raise ValueError("invalid primary quadrature degree or bounded chunk size")
    if not 1 <= len(selected_modes) <= 8 or len(selected_indices) != len(selected_modes) or len(set(selected_indices)) != len(selected_indices) or any(type(i) is not int or i < 0 for i in selected_indices):
        raise ValueError("expected <=8 modes with distinct frozen nonnegative inventory indices")
    if V.mesh is not mesh_data.mesh or V.value_size != 3:
        raise ValueError("space and mesh identity/value size mismatch")
    element = V.element.basix_element
    if element.family.name != "N1E" or element.cell_type.name != "hexahedron" or element.degree != 6 or element.dim != P6_CELL_DOFS or tuple(element.value_shape) != (3,):
        raise ValueError("reference requires the admitted p6 882-DoF N1E hex element")
    for mode in selected_modes:
        if mode.side != "top" or np.shape(mode.k_vector) != (3,) or not all(np.isfinite(v) for v in (mode.alpha, mode.gamma, mode.k_vector[2])):
            raise ValueError("reference only accepts finite actual top modes")
    phase_groups: dict[tuple[complex, complex, complex], list[int]] = {}
    for index, mode in enumerate(selected_modes):
        phase_groups.setdefault((complex(mode.alpha), complex(mode.gamma), complex(mode.k_vector[2])), []).append(index)
    if len(phase_groups) > 4:
        raise ValueError("selected modes exceed the admitted four distinct phase tuples")
    rows = int(V.dofmap.index_map.size_local)
    _admit(allocation_gate, event, "reference_state_validation", [_item("master_constraint_validation_views_and_index_copies", rows * 3 + rows * 2, 16)], rows=rows, fields=3)
    state_identity = _validate_states(V, mpc, native_fields, independent_states)
    rectangles = _actual_rectangles(mesh_data, cfg, allocation_gate, event)
    from basix import CellType, QuadratureType, make_quadrature

    arrays: dict[str, np.ndarray] = {}
    rule_records = []
    for increment in (8, 16):
        degree = quadrature_degree + increment
        predicted_nodes = ((degree + 2) // 2) ** 2
        _admit(allocation_gate, event, f"reference_rule_plus{increment}", [_item("reference_points_weights", predicted_nodes * 3, 8), _item("quadrature_construction_scratch_conservative", predicted_nodes * 6 + 8 * (degree + 2) ** 2, 8, "workspace_estimate"), _item("retained_scalar_output_arrays", len(selected_modes) * 3 * 2 * 2, 16)], degree=degree, predicted_nodes=predicted_nodes)
        points, weights = make_quadrature(CellType.quadrilateral, degree, rule=QuadratureType.gauss_jacobi)
        points, weights = np.asarray(points), np.asarray(weights)
        if points.dtype != np.float64 or weights.dtype != np.float64 or points.shape != (predicted_nodes, 2) or weights.shape != (predicted_nodes,) or not np.isfinite(points).all() or not np.isfinite(weights).all() or np.any(weights <= 0) or np.any(points < 0) or np.any(points > 1) or abs(float(weights.sum()) - 1.0) > 32 * np.finfo(float).eps:
            raise ValueError("actual Basix quadrilateral rule differs from admitted finite Gauss identity")
        contractions = np.zeros((len(selected_modes), 3), dtype=np.complex128)
        scales = np.zeros((len(selected_modes), 3), dtype=np.float64)
        nonzero_x_trace = [False, False, False]
        for rectangle in rectangles:
            for start in range(0, len(weights), chunk_size):
                stop = min(start + chunk_size, len(weights))
                count = stop - start
                _admit(allocation_gate, event, "reference_public_function_eval_chunk", reference_workspace_items(count, rule_points=len(weights)), degree=degree, facet=rectangle.facet, cell=rectangle.cell, start=start, stop=stop, chunk_size=count)
                xyz, physical_weights, cells = map_chunk(rectangle, points[start:stop], weights[start:stop])
                output = np.empty((count, 3), dtype=np.complex128)
                field_cache = np.empty((count, 3), dtype=np.complex128)
                for state_index, field in enumerate(native_fields):
                    field.eval(xyz, cells, u=output)
                    if output.shape != (count, 3) or output.dtype != np.complex128 or not np.isfinite(output).all():
                        raise ValueError("public Function.eval returned invalid finite vector field")
                    field_cache[:, state_index] = output[:, 0]
                    nonzero_x_trace[state_index] |= bool(np.any(output[:, 0] != 0))
                for phase_key, mode_indices in phase_groups.items():
                    phase = _phase_chunk(xyz, *phase_key, rectangle.zplane)
                    for state_index in range(3):
                        value, scale = _contract_phased(physical_weights, field_cache[:, state_index], phase)
                        for mode_index in mode_indices:
                            contractions[mode_index, state_index] += value
                            scales[mode_index, state_index] += scale
                    del phase
                del output, field_cache, xyz, physical_weights, cells
        if not np.isfinite(contractions).all() or not np.isfinite(scales).all():
            raise ValueError("nonfinite accumulated reference result")
        if not all(nonzero_x_trace):
            raise ValueError("each admitted native state must have a nonzero actual top x trace")
        arrays[f"contractions_degree_plus{increment}"] = contractions
        arrays[f"operation_scales_degree_plus{increment}"] = scales
        rule_records.append({"increment": increment, "degree": degree, "actual_nodes_per_facet": len(weights), "actual_total_geometric_points": 6 * len(weights), "field_point_evaluations": 3 * 6 * len(weights), "reference_points_sha256": _hash_array(points), "reference_weights_sha256": _hash_array(weights), "quadrature_family": "Basix.gauss_jacobi.quadrilateral", "chunk_maximum": chunk_size, "field_eval_calls": 3 * 6 * math.ceil(len(weights) / chunk_size), "distinct_phase_tuples": len(phase_groups), "phase_evaluation_calls": len(phase_groups) * 6 * math.ceil(len(weights) / chunk_size), "three_states_nonzero_actual_top_x_trace": nonzero_x_trace, "component_field_cache_maximum_complex_values": 3 * chunk_size, "cache_lifetime": "one facet quadrature chunk; discarded before next chunk"})
        del points, weights
    metrics = []
    for mode_index, inventory_index in enumerate(selected_indices):
        for state_index in range(3):
            # Compare convergence against the more accurate rule's operation scale.
            metric = operation_scaled_difference(arrays["contractions_degree_plus8"][mode_index, state_index], arrays["contractions_degree_plus16"][mode_index, state_index], arrays["operation_scales_degree_plus16"][mode_index, state_index])
            metrics.append({"selected_mode_index": mode_index, "inventory_index": inventory_index, "state_index": state_index, **metric})
    convergence_pass = all(m["passed"] for m in metrics)
    record = {"status": "REFERENCE_ACTION_CONVERGENCE_PASS" if convergence_pass else "REFERENCE_ACTION_CONVERGENCE_FAILED", "reference_convergence_pass": bool(convergence_pass), "scope": "selected_top_x_component_action_contractions_only", "full_C_D_qualification": False, "target_PDE_qualification": False, "primary_degree": quadrature_degree, "reference_increments": [8, 16], "operation_rtol": OPERATION_RTOL, "operation_scale": "sum(weights*abs(phase)*abs(field_x))", "no_numerical_denominator_floor": True, "primal_dual_convention": "vdot(master_only_native_u, raw_MPC_b) = integral phase*conj(Function.eval(Ku)_x)", "state_identity": state_identity, "facet_rectangles": [r.__dict__ for r in rectangles], "selected_indices": list(selected_indices), "selected_modes": [{"side": m.side, "m": int(m.m), "n": int(m.n), "polarization": m.polarization, "alpha": [float(complex(m.alpha).real), float(complex(m.alpha).imag)], "gamma": [float(complex(m.gamma).real), float(complex(m.gamma).imag)], "kz": [float(complex(m.k_vector[2]).real), float(complex(m.k_vector[2]).imag)]} for m in selected_modes], "rules": rule_records, "convergence_metrics": metrics, "arrays_sha256": {key: _hash_array(value) for key, value in arrays.items()}, "allocation_estimates_are_rss": False, "whole_process_3gib_watchdog_required": True, "build_mesh_space_form_mode_carrier_factor_PDE_calls": 0}
    event({"kind": "reference_finished", "record": record})
    return {"record": record, "arrays": arrays}


def _synthetic_tests() -> None:
    """Pure NumPy fixtures and source/API negatives. Never instantiate FE."""
    import ast
    import inspect
    import unittest
    from types import SimpleNamespace

    class ReferenceSyntheticTests(unittest.TestCase):
        def make_rectangle(self):
            vertices = _REFERENCE_VERTICES * np.array([16.5, 12.5, 10]) + np.array([0, 0, 120])
            return rectangle_from_geometry(5, 7, vertices[4:], vertices, 130), vertices

        def test_affine_mapping_bounds_area(self):
            rectangle, _ = self.make_rectangle()
            nodes, weights = np.polynomial.legendre.leggauss(6)
            q = np.array([(x, y) for x in (nodes + 1) / 2 for y in (nodes + 1) / 2])
            w = np.outer(weights / 2, weights / 2).ravel()
            xyz, physical, cells = map_chunk(rectangle, q, w)
            self.assertTrue(np.all(cells == 7))
            self.assertEqual(xyz.dtype, np.float64)
            self.assertEqual(cells.dtype, np.int32)
            self.assertAlmostEqual(physical.sum(), 16.5 * 12.5, places=12)
            got, scale = contract_chunk(xyz, physical, xyz[:, 0] + 1j * xyz[:, 1], 0, 0, 10000j, 130)
            self.assertAlmostEqual(got.real, rectangle.area * 16.5 / 2, places=10)
            self.assertAlmostEqual(got.imag, -rectangle.area * 12.5 / 2, places=10)
            self.assertGreater(scale, abs(got))

        def test_oscillatory_chunk_partition_and_phase_sign(self):
            rectangle, _ = self.make_rectangle()
            nodes, weights = np.polynomial.legendre.leggauss(40)
            q = np.array([(x, y) for x in (nodes + 1) / 2 for y in (nodes + 1) / 2])
            w = np.outer(weights / 2, weights / 2).ravel()
            alpha, gamma, field = 0.4 + 0.02j, -0.3, 1 + 2j
            total, scale = 0j, 0.0
            for start in range(0, len(w), 37):
                xyz, physical, _ = map_chunk(rectangle, q[start:start + 37], w[start:start + 37])
                value, local_scale = contract_chunk(xyz, physical, np.full(len(physical), field), alpha, gamma, 999j, 130)
                total += value
                scale += local_scale
            exact = np.conjugate(field) * np.expm1(1j * alpha * 16.5) / (1j * alpha) * np.expm1(1j * gamma * 12.5) / (1j * gamma)
            self.assertTrue(operation_scaled_difference(total, exact, scale)["passed"])
            self.assertFalse(operation_scaled_difference(np.conjugate(total), exact, scale)["passed"])

        def test_primal_dual_constraint_convention(self):
            K = np.array([[1, 0], [0, 1], [np.exp(0.7j), -0.4j]])
            master = np.array([1.2 + 0.3j, -0.7 + 0.6j])
            b_fe = np.array([0.5 - 0.4j, 0.2 + 0.7j, -0.6 + 0.3j])
            b_mpc = K.conj().T @ b_fe
            self.assertAlmostEqual(abs(np.vdot(master, b_mpc) - np.vdot(K @ master, b_fe)), 0, places=14)
            self.assertGreater(abs(np.vdot(b_mpc, master) - np.vdot(K @ master, b_fe)), 0.1)

        def test_exact_zero_scale_and_no_floor(self):
            self.assertTrue(operation_scaled_difference(0j, 0j, 0)["passed"])
            metric = operation_scaled_difference(1e-300j, 0j, 0)
            self.assertFalse(metric["passed"])
            self.assertIsNone(metric["scaled_error"])
            self.assertFalse(operation_scaled_difference(1e-110j, 0j, 1e-101)["passed"])
            with self.assertRaises(ValueError):
                operation_scaled_difference(np.nan, 0, 1)

        def test_metric_rejects_overflow_after_finite_inputs(self):
            with self.assertRaisesRegex(ValueError, "computed contraction error"):
                operation_scaled_difference(1e308, -1e308, 1e308)
            with self.assertRaisesRegex(ValueError, "computed normalized"):
                operation_scaled_difference(1.0, 0, 1e-320)

        def test_geometry_rejects_warp_and_cell_order(self):
            rectangle, vertices = self.make_rectangle()
            warped = vertices.copy()
            warped[7, 0] += 1e-12
            with self.assertRaises(ValueError):
                rectangle_from_geometry(1, 1, warped[4:], warped, 130)
            wrong = vertices.copy()
            wrong[[1, 3]] = wrong[[3, 1]]
            with self.assertRaises(ValueError):
                rectangle_from_geometry(1, 1, vertices[4:], wrong, 130)
            with self.assertRaises(ValueError):
                rectangle_from_geometry(1, 1, vertices[4:], vertices, 130 + 1e-12)
            with self.assertRaises(ValueError):
                map_chunk(rectangle, np.array([[1.01, 0.4]]), np.array([1.0]))

        def test_full_rectangle_cover_and_duplicate_negative(self):
            rectangles = [FacetRectangle(i, i, x0, x1, y0, y1, 130) for i, (x0, x1, y0, y1) in enumerate((x0, x1, y0, y1) for x0, x1 in zip(EXPECTED_AXES[0][:-1], EXPECTED_AXES[0][1:]) for y0, y1 in zip(EXPECTED_AXES[1][:-1], EXPECTED_AXES[1][1:]))]
            validate_rectangles(rectangles)
            with self.assertRaises(ValueError):
                validate_rectangles(rectangles[:-1] + [rectangles[0]])

        def test_allocation_gate_precedes_event_and_denies(self):
            calls = []
            def gate(label, facts):
                calls.append((label, facts))
                raise MemoryError("synthetic allocation denied")
            with self.assertRaises(MemoryError):
                _admit(gate, lambda record: calls.append(record), "synthetic", reference_workspace_items(256, rule_points=7921))
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["kind"], "reference_allocation_before")
            self.assertGreater(calls[1][1]["requested_bytes"], 256 * 882 * 3 * 8)
            with self.assertRaises(MemoryError):
                _admit(lambda *args: False, lambda record: None, "synthetic_false", reference_workspace_items(256, rule_points=7921))
            with self.assertRaises(ValueError):
                reference_workspace_items(513, rule_points=7921)

        def test_negative_api_before_any_fe_import(self):
            with self.assertRaisesRegex(ValueError, "allocation gate"):
                run_reference(V=None, mesh_data=None, mpc=None, cfg=None, selected_modes=(), selected_indices=(), native_fields=(), independent_states=np.empty((0, 3)), quadrature_degree=160, allocation_gate=None, event=None)
            with self.assertRaisesRegex(ValueError, "chunk size"):
                run_reference(V=None, mesh_data=None, mpc=None, cfg=None, selected_modes=(), selected_indices=(), native_fields=(), independent_states=np.empty((0, 3)), quadrature_degree=160, allocation_gate=lambda *a: None, event=lambda *a: None, chunk_size=513)

        def test_source_forbids_build_assemble_private_kernel(self):
            tree = ast.parse(inspect.getsource(run_reference))
            names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            for forbidden in ("Function", "functionspace", "create_mesh", "form", "assemble_vector", "assemble_scalar", "tabulate", "_cpp_object", "ctypes", "ffi", "solve", "factor", "create_element"):
                self.assertNotIn(forbidden, names)
            source = inspect.getsource(run_reference)
            self.assertIn("field.eval(xyz, cells, u=output)", source)
            self.assertLess(source.index("reference_public_function_eval_chunk"), source.index("field.eval("))

        def test_fake_native_state_order_and_constraints(self):
            # Synthetic algebra stubs, not actual FE execution.
            V = SimpleNamespace(mesh=SimpleNamespace(comm=SimpleNamespace(size=1, rank=0), topology=SimpleNamespace(index_map=lambda dim: SimpleNamespace(size_local=1))), element=SimpleNamespace(signature="synthetic_N1E_not_FE"), dofmap=SimpleNamespace(index_map=SimpleNamespace(size_local=3, size_global=3, num_ghosts=0, local_range=(0, 3), local_to_global=lambda rows: rows.astype(np.int64)), index_map_bs=1, bs=1, cell_dofs=lambda cell: np.array([0, 1, 2], dtype=np.int32)))
            state = np.array([[1 + 2j, 2 - 3j, -0.2j], [3 - 0.3j, 4 + 1j, 0.1], [0, 0, 0]], dtype=np.complex128)
            coeff = np.array([0.7j, -0.2], dtype=np.complex128)
            updated_wrapper = SimpleNamespace(mesh=V.mesh, element=V.element, dofmap=V.dofmap)
            mpc = SimpleNamespace(finalized=True, function_space=updated_wrapper, slaves=np.array([2], dtype=np.int32), is_slave=np.array([0, 0, 1], dtype=np.int8), coefficients=lambda: (coeff, np.array([0, 0, 0, 2], dtype=np.int32)), masters=SimpleNamespace(links=lambda i: np.array([0, 1], dtype=np.int32)))
            fields = tuple(SimpleNamespace(function_space=V, x=SimpleNamespace(array=np.array([state[0, k], state[1, k], coeff @ state[:2, k]], dtype=np.complex128))) for k in range(3))
            self.assertEqual(_validate_states(V, mpc, fields, state)["constraint_equations_checked"], 3)
            fields[1].x.array[2] += 1e-5
            with self.assertRaisesRegex(ValueError, "violates"):
                _validate_states(V, mpc, fields, state)
            state[2, 0] = 1
            with self.assertRaisesRegex(ValueError, "literal zero"):
                _validate_states(V, mpc, fields, state)

        def test_native_layout_rejects_changed_cell_order(self):
            index = SimpleNamespace(size_local=3, size_global=3, num_ghosts=0, local_range=(0, 3), local_to_global=lambda rows: rows.astype(np.int64))
            mesh = SimpleNamespace(topology=SimpleNamespace(index_map=lambda dim: SimpleNamespace(size_local=1)))
            V = SimpleNamespace(mesh=mesh, element=SimpleNamespace(signature="synthetic"), dofmap=SimpleNamespace(index_map=index, index_map_bs=1, bs=1, cell_dofs=lambda cell: np.array([0, 1, 2], dtype=np.int32)))
            changed = SimpleNamespace(mesh=mesh, element=V.element, dofmap=SimpleNamespace(index_map=index, index_map_bs=1, bs=1, cell_dofs=lambda cell: np.array([0, 2, 1], dtype=np.int32)))
            with self.assertRaisesRegex(ValueError, "cell DoF ordering"):
                _assert_same_native_layout(V, changed)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceSyntheticTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["--synthetic-tests"]:
        raise SystemExit("Only --synthetic-tests is exposed; actual FE execution belongs to the admitted caller")
    _synthetic_tests()
