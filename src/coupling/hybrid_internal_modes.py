"""Matched internal-mode coupling for the Task032 current-scale reference.

The generic ``epsilon(x, y)`` interface algebra is retained, but replicated
dense modal arrays are not a scalable production API for the 0.7 nm target.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
import ufl
from basix.ufl import element
from dolfinx import cpp, default_real_type, fem
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import SimulationConfig3D
from ..common.high_order_quadrature import (
    HighOrderQuadraturePolicy,
    high_order_quadrature_policy,
)
from ..modes.cross_section_spaces import CrossSectionSpaces
from ..modes.mode_classification import (
    BiorthogonalModeBasis,
    ClassifiedBiorthogonalMode,
)
from ..modes.stable_propagation import (
    AxialPropagationModel,
    ModalTractionModel,
    TwoSidedPropagation,
    build_two_sided_propagation,
    scalar_cg_discrete_traction_beta,
)
from ..solvers.dtn_port_3d import (
    _assemble_mpc_form_vector,
    _assemble_unconstrained_form_vector,
    _vec_nonzero_owned_entries,
)
from ..solvers.hybrid_local_dtn import HybridLocalDtnSystem
from .modal_trace_projection import (
    ModalTraceProjection,
    _trace_from_full_mode_vector,
)


_TASK039_E7_TRACE_FAMILY_SHA256 = (
    "5fd8351050fb4849b87084de9465b218745805ecda7e4a83109bcd7a472aaedd"
)


@dataclass
class HybridInterfaceModeBlocks:
    """Sparse FE/modal blocks for one internal interface."""

    side: str
    projection: PETSc.Mat
    positive_traction: PETSc.Mat
    negative_traction: PETSc.Mat
    negative_trace_to_positive: np.ndarray
    inverse_trace_gram: np.ndarray
    trace_gram_condition: float
    positive_projection_identity_error: float
    local_fem_outward_normal_sign: int
    lifted_query_points: int
    quadrature_degree: int
    positive_interior_correction: np.ndarray
    negative_interior_correction: np.ndarray
    modal_rhs_correction: np.ndarray
    tangential_surface_trace_only_verified: bool = False
    interior_modal_pairwise_schur_evaluated: bool = False
    full_surface_mode_vectors_retained: bool = False
    full_field_or_mode_gathered: bool = False
    canonical_trace_raw_consistency_error: float = 0.0
    canonical_trace_representation_error: float = 0.0
    canonical_trace_gate: dict[str, object] | None = None
    quadrature_coefficient_degree: int = 0
    surface_reduction_audits: tuple[dict[str, object], ...] = ()

    def destroy(self) -> None:
        self.projection.destroy()
        self.positive_traction.destroy()
        self.negative_traction.destroy()


@dataclass
class HybridInternalModeCoupling:
    """Task32 reflection-free middle-region coupling before monolithic assembly."""

    projection: ModalTraceProjection
    bottom: HybridInterfaceModeBlocks
    top: HybridInterfaceModeBlocks
    propagation: TwoSidedPropagation
    modal_traction_model: ModalTractionModel
    positive_traction_beta_per_nm: tuple[complex, ...]
    negative_traction_beta_per_nm: tuple[complex, ...]
    negative_trace_to_positive: np.ndarray
    positive_projection_identity_error: float
    mode_count_per_direction: int
    interface_quadrature_degree: int
    spaces: CrossSectionSpaces
    positive_basis: BiorthogonalModeBasis
    negative_basis: BiorthogonalModeBasis
    full_field_or_mode_gathered: bool = False
    dense_interface_square_formed: bool = False
    interface_quadrature_coefficient_degree: int = 0
    exact_one_cell_audit: dict[str, object] | None = None
    traction_beta_source: str = "coupling_selected_traction_beta_per_nm"

    @property
    def internal_unknown_count(self) -> int:
        return 2 * self.mode_count_per_direction

    @property
    def internal_equation_count(self) -> int:
        return 2 * self.mode_count_per_direction

    def destroy(self) -> None:
        self.bottom.destroy()
        self.top.destroy()
        self.projection.destroy()


def _destroy_pending_exact_overrides(
    pending: dict[str, tuple[PETSc.Mat, PETSc.Mat]],
) -> None:
    """Destroy exact pairs that have not yet transferred to interface blocks."""

    for pair in pending.values():
        for matrix in pair:
            matrix.destroy()
    pending.clear()


class _DistributedTwoDimensionalEvaluator:
    """Evaluate a distributed 2D field through the matched structured grid."""

    def __init__(self, source: fem.Function, *, padding: float) -> None:
        if tuple(source.function_space.element.value_shape) != (2,):
            raise ValueError("The lifted cross-section field must have two components.")
        self.source = source
        self.padding = float(padding)
        self.local_query_points = 0
        self.local_source_evaluations = 0
        self._cached_points: np.ndarray | None = None
        self._cached_cell_keys: np.ndarray | None = None
        self._cached_received_requests = None
        msh = source.function_space.mesh
        comm = msh.comm
        local_x = np.unique(np.asarray(msh.geometry.x[:, 0], dtype=np.float64))
        local_y = np.unique(np.asarray(msh.geometry.x[:, 1], dtype=np.float64))
        self.x_values = np.unique(np.concatenate(comm.allgather(local_x)))
        self.y_values = np.unique(np.concatenate(comm.allgather(local_y)))
        if len(self.x_values) < 2 or len(self.y_values) < 2:
            raise RuntimeError("The matched cross-section has no structured cells.")
        self.tolerance = max(
            self.padding,
            1.0e-12
            * max(
                self.x_values[-1] - self.x_values[0],
                self.y_values[-1] - self.y_values[0],
                1.0,
            ),
        )
        tdim = msh.topology.dim
        num_owned = msh.topology.index_map(tdim).size_local
        geometry_dofmap = np.asarray(msh.geometry.dofmap)
        coordinates = np.asarray(msh.geometry.x)
        self.local_cell_by_key: dict[tuple[int, int], int] = {}
        for cell in range(num_owned):
            cell_coordinates = coordinates[geometry_dofmap[cell], :2]
            midpoint = np.mean(cell_coordinates, axis=0)
            key = self._cell_key(float(midpoint[0]), float(midpoint[1]))
            if key in self.local_cell_by_key:
                raise RuntimeError(f"Duplicate owned cross-section cell key {key}.")
            self.local_cell_by_key[key] = cell
        gathered_keys = comm.allgather(tuple(self.local_cell_by_key))
        self.owner_by_key: dict[tuple[int, int], int] = {}
        for owner, keys in enumerate(gathered_keys):
            for key in keys:
                if key in self.owner_by_key:
                    raise RuntimeError(f"Cross-section cell key {key} has two owners.")
                self.owner_by_key[key] = owner
        expected = (len(self.x_values) - 1) * (len(self.y_values) - 1)
        if len(self.owner_by_key) != expected:
            raise RuntimeError(
                f"Structured cross-section owner map has {len(self.owner_by_key)} "
                f"cells, expected {expected}."
            )

    def _axis_cell(self, value: float, axis: np.ndarray) -> int:
        if value < axis[0] - self.tolerance or value > axis[-1] + self.tolerance:
            raise RuntimeError(f"Interface point {value:.16e} lies outside an axis.")
        clipped = min(max(value, float(axis[0])), float(axis[-1]))
        index = int(np.searchsorted(axis, clipped, side="right") - 1)
        return min(max(index, 0), len(axis) - 2)

    def _cell_key(self, x: float, y: float) -> tuple[int, int]:
        return (
            self._axis_cell(x, self.x_values),
            self._axis_cell(y, self.y_values),
        )

    def set_source(self, source: fem.Function) -> None:
        if source.function_space.mesh is not self.source.function_space.mesh:
            raise ValueError("A cached interface evaluator cannot change source mesh.")
        if tuple(source.function_space.element.value_shape) != (2,):
            raise ValueError("The lifted cross-section field must have two components.")
        self.source = source

    def evaluate_points(
        self,
        x: np.ndarray,
        *,
        cell_keys: np.ndarray | None = None,
    ) -> np.ndarray:
        """Collectively evaluate one rank-local set of interpolation points.

        This method must be called explicitly by every rank.  In particular,
        it must not be used directly as a ``Function.interpolate`` callback:
        DOLFINx is free to skip that callback on ranks with no local cells,
        whereas the two ``alltoall`` exchanges below are collective.
        """

        coordinates = np.asarray(x, dtype=np.float64)
        if coordinates.ndim != 2:
            raise ValueError("Interpolation coordinates must be a rank-2 array.")
        if coordinates.shape[0] == 3:
            points = np.asarray(coordinates.T, dtype=np.float64)
        elif coordinates.shape[1] == 3:
            points = np.asarray(coordinates, dtype=np.float64)
        else:
            raise ValueError("Interpolation coordinates must have three columns.")
        xy = points[:, :2]
        # DOLFINx stores geometry.x with three columns even for this gdim=2
        # mesh, and its point-ownership ABI requires the padded third column.
        points = np.zeros((len(xy), 3), dtype=np.float64)
        points[:, :2] = xy
        if cell_keys is None:
            routed_keys = np.asarray(
                [self._cell_key(float(point[0]), float(point[1])) for point in points],
                dtype=np.int64,
            )
        else:
            routed_keys = np.asarray(cell_keys, dtype=np.int64)
            if routed_keys.shape != (len(points), 2):
                raise ValueError(
                    "Interpolation cell keys must have shape (point_count, 2)."
                )
        self.local_query_points += len(points)
        if self._cached_points is None:
            self._cached_points = points.copy()
            self._cached_cell_keys = routed_keys.copy()
            comm = self.source.function_space.mesh.comm
            requests: list[list[tuple[int, float, float, int, int]]] = [
                [] for _ in range(comm.size)
            ]
            for index, point in enumerate(points):
                key = tuple(map(int, routed_keys[index]))
                owner = self.owner_by_key[key]
                requests[owner].append(
                    (index, float(point[0]), float(point[1]), key[0], key[1])
                )
            self._cached_received_requests = comm.alltoall(requests)
        else:
            if self._cached_points.shape != points.shape or not np.allclose(
                self._cached_points, points, rtol=0.0, atol=1.0e-13
            ):
                raise RuntimeError(
                    "Cached 2D-to-3D interpolation points changed ordering."
                )
            if not np.array_equal(self._cached_cell_keys, routed_keys):
                raise RuntimeError("Cached 2D-to-3D source-cell routing changed.")
        comm = self.source.function_space.mesh.comm
        received_requests = self._cached_received_requests
        dest_points_list: list[tuple[float, float, float]] = []
        dest_cells_list: list[int] = []
        destinations: list[tuple[int, int]] = []
        for requester, records in enumerate(received_requests):
            for index, x_value, y_value, key_x, key_y in records:
                key = (int(key_x), int(key_y))
                if key not in self.local_cell_by_key:
                    raise RuntimeError(
                        f"Rank {comm.rank} received non-owned cell key {key}."
                    )
                dest_points_list.append((float(x_value), float(y_value), 0.0))
                dest_cells_list.append(self.local_cell_by_key[key])
                destinations.append((requester, int(index)))
        dest_points = np.asarray(dest_points_list, dtype=np.float64).reshape(-1, 3)
        dest_cells = np.asarray(dest_cells_list, dtype=np.int32)
        values = (
            np.asarray(
                self.source.eval(dest_points, dest_cells),
                dtype=PETSc.ScalarType,
            ).reshape(len(dest_points), 2)
            if len(dest_points)
            else np.empty((0, 2), dtype=PETSc.ScalarType)
        )
        self.local_source_evaluations += len(values)
        send: list[list[tuple[int, complex, complex]]] = [[] for _ in range(comm.size)]
        for (requester, index), value in zip(destinations, values):
            send[requester].append((index, complex(value[0]), complex(value[1])))
        received = comm.alltoall(send)
        result = np.zeros((len(points), 3), dtype=PETSc.ScalarType)
        resolved = np.zeros(len(points), dtype=bool)
        for packets in received:
            for index, first, second in packets:
                if resolved[int(index)]:
                    raise RuntimeError("An interface point received two values.")
                result[int(index), :2] = (first, second)
                resolved[int(index)] = True
        if not np.all(resolved):
            raise RuntimeError("At least one interface point received no 2D value.")
        return result.T


def _function_space_polynomial_degree(space) -> int:
    basix_element = getattr(space.element, "basix_element", None)
    degree = int(getattr(basix_element, "degree", 0))
    if degree < 1:
        raise RuntimeError("Could not determine a positive function-space degree.")
    return degree


def _interface_owned_cells(system: HybridLocalDtnSystem) -> np.ndarray:
    msh = system.local_mesh.mesh
    tdim = msh.topology.dim
    num_owned = msh.topology.index_map(tdim).size_local
    coordinates = np.asarray(msh.geometry.x)
    geometry_dofmap = np.asarray(msh.geometry.dofmap)
    interface_z = system.local_mesh.interface_z_nm
    tolerance = 1.0e-10 * max(
        system.local_mesh.mesh_data.mesh_axis_cell_stats["x"]["max"],
        system.local_mesh.mesh_data.mesh_axis_cell_stats["y"]["max"],
        1.0,
    )
    cells: list[int] = []
    for cell in range(num_owned):
        z_values = coordinates[geometry_dofmap[cell], 2]
        if system.side == "bottom":
            touches = abs(float(np.max(z_values)) - interface_z) <= tolerance
        else:
            touches = abs(float(np.min(z_values)) - interface_z) <= tolerance
        if touches:
            cells.append(cell)
    local = np.asarray(cells, dtype=np.int32)
    expected = system.local_mesh.global_interface_facet_count
    actual = int(msh.comm.allreduce(len(local), op=MPI.SUM))
    if actual != expected:
        raise RuntimeError(
            f"{system.side} interface-adjacent cell count {actual} != {expected}."
        )
    return local


def lift_cross_section_vector_to_local_interface(
    source: fem.Function,
    system: HybridLocalDtnSystem,
    *,
    target_space=None,
) -> tuple[fem.Function, int]:
    """Lift only one layer of a 2D vector field to a local 3D interface."""

    msh = system.local_mesh.mesh
    if target_space is None:
        target_degree = _function_space_polynomial_degree(system.V)
        target_space = fem.functionspace(
            msh,
            element(
                "DG",
                msh.basix_cell(),
                target_degree,
                shape=(3,),
                dtype=default_real_type,
            ),
        )
    lifter = _ReusableInterfaceLifter(system, target_space=target_space)
    return lifter.lift(source)


class _ReusableInterfaceLifter:
    """Reuse target space and point ownership for many fields on one interface."""

    def __init__(self, system: HybridLocalDtnSystem, *, target_space=None) -> None:
        self.system = system
        msh = system.local_mesh.mesh
        if target_space is None:
            target_degree = _function_space_polynomial_degree(system.V)
            target_space = fem.functionspace(
                msh,
                element(
                    "DG",
                    msh.basix_cell(),
                    target_degree,
                    shape=(3,),
                    dtype=default_real_type,
                ),
            )
        self.target = fem.Function(target_space)
        self.cells = _interface_owned_cells(system)
        self.interpolation_points = np.asarray(
            cpp.fem.interpolation_coords(
                target_space.element._cpp_object,
                msh.geometry._cpp_object,
                self.cells,
            ),
            dtype=np.float64,
        )
        self.padding = 1.0e-10 * max(
            system.local_mesh.mesh_data.mesh_axis_cell_stats["x"]["max"],
            system.local_mesh.mesh_data.mesh_axis_cell_stats["y"]["max"],
            1.0,
        )
        self.evaluator: _DistributedTwoDimensionalEvaluator | None = None
        self.point_cell_keys: np.ndarray | None = None

    def _build_point_cell_keys(
        self, evaluator: _DistributedTwoDimensionalEvaluator
    ) -> np.ndarray:
        coordinates = self.interpolation_points
        if coordinates.shape[0] == 3:
            points = np.asarray(coordinates.T, dtype=np.float64)
        elif coordinates.shape[1] == 3:
            points = np.asarray(coordinates, dtype=np.float64)
        else:
            raise RuntimeError("Target interpolation coordinates need three columns.")
        # Route every target interpolation point through the source modal
        # mesh.  The old midpoint shortcut was valid only when both structured
        # meshes had identical cell boundaries; an independently refined QEP
        # mesh can place several source cells under one local-FE interface
        # cell.
        return np.asarray(
            [evaluator._cell_key(float(point[0]), float(point[1])) for point in points],
            dtype=np.int64,
        ).reshape(-1, 2)

    def lift(self, source: fem.Function) -> tuple[fem.Function, int]:
        if self.evaluator is None:
            self.evaluator = _DistributedTwoDimensionalEvaluator(
                source, padding=self.padding
            )
            self.point_cell_keys = self._build_point_cell_keys(self.evaluator)
        else:
            self.evaluator.set_source(source)
        before_queries = self.evaluator.local_query_points
        before_evaluations = self.evaluator.local_source_evaluations
        values = self.evaluator.evaluate_points(
            self.interpolation_points,
            cell_keys=self.point_cell_keys,
        )

        def cached_values(x: np.ndarray) -> np.ndarray:
            coordinates = np.asarray(x, dtype=np.float64)
            if coordinates.shape != self.interpolation_points.shape or not np.allclose(
                coordinates,
                self.interpolation_points,
                rtol=0.0,
                atol=1.0e-13,
            ):
                raise RuntimeError(
                    "DOLFINx interpolation points changed after collective evaluation."
                )
            return values

        self.target.x.array[:] = 0.0
        # The callback is deliberately local-only.  All distributed source
        # evaluation has already completed above with every rank participating.
        self.target.interpolate(cached_values, self.cells)
        self.target.x.scatter_forward()
        comm = self.system.local_mesh.mesh.comm
        queries = int(
            comm.allreduce(
                self.evaluator.local_query_points - before_queries,
                op=MPI.SUM,
            )
        )
        evaluations = int(
            comm.allreduce(
                self.evaluator.local_source_evaluations - before_evaluations,
                op=MPI.SUM,
            )
        )
        if queries != evaluations:
            raise RuntimeError("2D-to-3D interface lift lost interpolation values.")
        return self.target, queries


@dataclass
class _InterfaceSurfaceLoadEntries:
    matrix_rows: np.ndarray
    matrix_values: np.ndarray
    overlap_rows: np.ndarray
    overlap_values: np.ndarray
    full_vector: PETSc.Vec | None
    queries: int
    tangential_surface_trace_only_verified: bool


class _ReusableInterfaceSurfaceLoad:
    """Compile one interface load form and update only its lifted coefficient."""

    def __init__(self, system: HybridLocalDtnSystem) -> None:
        self.system = system
        self.reduction_audits: list[dict[str, object]] = []
        self.lifter = _ReusableInterfaceLifter(system)
        lifted_coefficient_degree = _function_space_polynomial_degree(
            self.lifter.target.function_space
        )
        self.quadrature_policy: HighOrderQuadraturePolicy = (
            high_order_quadrature_policy(
                field_degree=_function_space_polynomial_degree(system.V),
                geometry_degree=int(
                    getattr(system.local_mesh.mesh.geometry.cmap, "degree", 1)
                ),
                coefficient_degree=lifted_coefficient_degree,
            )
        )
        v = ufl.TestFunction(system.V)
        ds = ufl.Measure(
            "ds",
            domain=system.local_mesh.mesh,
            subdomain_data=system.local_mesh.mesh_data.facet_tags,
        )
        self.form = fem.form(
            ufl.inner(self.lifter.target, v)
            * ds(system.local_mesh.interface_facet_tag),
            form_compiler_options={
                "quadrature_degree": self.quadrature_policy.selected_degree
            },
        )

    def assemble(
        self,
        source: fem.Function,
        *,
        role: str,
    ) -> _InterfaceSurfaceLoadEntries:
        _lifted, queries = self.lifter.lift(source)
        overlap_vector = _assemble_mpc_form_vector(
            self.form, self.system.floquet_data.mpc
        )
        overlap_rows, overlap_values = _vec_nonzero_owned_entries(overlap_vector)
        if self.system.static_condensation is None:
            self.reduction_audits.append(
                {
                    "side": self.system.side,
                    "role": role,
                    "source_name": str(source.name),
                    "quadrature_degree": (self.quadrature_policy.selected_degree),
                    "coefficient_degree": (self.quadrature_policy.coefficient_degree),
                    "status": "not_applicable_no_static_reduction",
                    "pass": True,
                }
            )
            overlap_vector.destroy()
            return _InterfaceSurfaceLoadEntries(
                matrix_rows=overlap_rows,
                matrix_values=overlap_values,
                overlap_rows=overlap_rows,
                overlap_values=overlap_values,
                full_vector=None,
                queries=queries,
                tangential_surface_trace_only_verified=False,
            )
        reduction_audit: dict[str, object] = {
            "side": self.system.side,
            "role": role,
            "source_name": str(source.name),
            "quadrature_degree": self.quadrature_policy.selected_degree,
            "coefficient_degree": self.quadrature_policy.coefficient_degree,
        }
        try:
            reduced = (
                self.system.static_condensation.reduce_tangential_surface_mpc_vector(
                    overlap_vector,
                    audit=reduction_audit,
                )
            )
            matrix_rows, matrix_values = _vec_nonzero_owned_entries(reduced)
            reduced.destroy()
        except Exception:
            self.reduction_audits.append(reduction_audit)
            overlap_vector.destroy()
            raise
        self.reduction_audits.append(reduction_audit)
        overlap_vector.destroy()
        return _InterfaceSurfaceLoadEntries(
            matrix_rows=matrix_rows,
            matrix_values=matrix_values,
            overlap_rows=overlap_rows,
            overlap_values=overlap_values,
            full_vector=None,
            queries=queries,
            tangential_surface_trace_only_verified=True,
        )

    def assemble_entries(
        self, source: fem.Function
    ) -> tuple[np.ndarray, np.ndarray, int]:
        entries = self.assemble(source, role="load_column")
        if entries.full_vector is not None:
            entries.full_vector.destroy()
        return entries.matrix_rows, entries.matrix_values, entries.queries

    def assemble_full_vector(
        self,
        source: fem.Function,
    ) -> tuple[PETSc.Vec, int]:
        """Assemble one full-space interface load for streaming recovery."""

        if self.system.static_condensation is None:
            raise ValueError(
                "Full-space Hybrid interface loads are recovery-only and "
                "require assembly-time static condensation."
            )
        _lifted, queries = self.lifter.lift(source)
        return _assemble_unconstrained_form_vector(self.form), queries


def _surface_load_entries(
    source: fem.Function,
    system: HybridLocalDtnSystem,
) -> tuple[np.ndarray, np.ndarray, int]:
    """One-shot wrapper; production mode loops use the reusable assembler."""

    return _ReusableInterfaceSurfaceLoad(system).assemble_entries(source)


def _canonicalized_negative_traces(
    projection: ModalTraceProjection,
    canonical_mapping: np.ndarray,
) -> list[fem.Function]:
    """Represent reciprocal traces in the qualified positive coordinates."""

    mode_count = len(projection.right_traces)
    if canonical_mapping.shape != (mode_count, mode_count):
        raise ValueError("Canonical negative trace map has the wrong shape.")
    traces: list[fem.Function] = []
    for column in range(mode_count):
        trace = fem.Function(
            projection.right_traces[0].function_space,
            name=f"task032_canonical_negative_trace_{column}",
        )
        trace.x.petsc_vec.set(0.0)
        for row, source in enumerate(projection.right_traces):
            coefficient = complex(canonical_mapping[row, column])
            if abs(coefficient) > 0.0:
                trace.x.petsc_vec.axpy(
                    PETSc.ScalarType(coefficient),
                    source.x.petsc_vec,
                )
        trace.x.scatter_forward()
        traces.append(trace)
    return traces


def _canonical_trace_consistency_audit(
    surface_gram: np.ndarray,
    raw_negative_overlap: np.ndarray,
    canonical_negative_overlap: np.ndarray,
    canonical_mapping: np.ndarray,
    *,
    tolerance: float = 1.0e-12,
    canonical_trace_gate_policy: str | None = None,
    canonical_trace_family_sha256: str | None = None,
) -> dict[str, object]:
    """Audit raw and canonical reciprocal traces in one coordinate system."""

    gram = np.asarray(surface_gram, dtype=np.complex128)
    raw = np.asarray(raw_negative_overlap, dtype=np.complex128)
    canonical = np.asarray(canonical_negative_overlap, dtype=np.complex128)
    mapping = np.asarray(canonical_mapping, dtype=np.complex128)
    if (
        gram.ndim != 2
        or gram.shape[0] != gram.shape[1]
        or raw.shape != gram.shape
        or canonical.shape != gram.shape
        or mapping.shape != gram.shape
    ):
        raise ValueError(
            "Canonical trace audit matrices must have equal square shapes."
        )
    expected = gram @ mapping
    if not all(
        np.all(np.isfinite(values))
        for values in (gram, raw, canonical, mapping, expected)
    ):
        raw_error = representation_error = float("inf")
    else:
        raw_scale = max(
            float(np.linalg.norm(raw, ord=np.inf)),
            float(np.linalg.norm(expected, ord=np.inf)),
            1.0e-30,
        )
        canonical_scale = max(
            float(np.linalg.norm(canonical, ord=np.inf)),
            float(np.linalg.norm(expected, ord=np.inf)),
            1.0e-30,
        )
        raw_error = float(np.linalg.norm(raw - expected, ord=np.inf) / raw_scale)
        representation_error = float(
            np.linalg.norm(canonical - expected, ord=np.inf) / canonical_scale
        )
    result = {
        "pass": bool(
            np.isfinite(tolerance)
            and tolerance >= 0.0
            and raw_error <= tolerance
            and representation_error <= tolerance
        ),
        "tolerance": float(tolerance),
        "raw_consistency_error": raw_error,
        "canonical_representation_error": representation_error,
    }
    if canonical_trace_gate_policy is None:
        return result
    if canonical_trace_gate_policy != "task039_m960_backward_stable_v1":
        raise ValueError(
            "Unsupported canonical trace Gate policy; ordinary fixed 1e-12 "
            "behavior is the only default."
        )
    if gram.shape != (960, 960):
        raise ValueError("Task039 M960 canonical trace Gate requires a 960x960 matrix.")
    if canonical_trace_family_sha256 != _TASK039_E7_TRACE_FAMILY_SHA256:
        raise ValueError(
            "Task039 M960 canonical trace Gate requires the approved family SHA256."
        )
    finite = all(
        np.isfinite(values).all()
        for values in (gram, raw, canonical, mapping, expected)
    )
    tiny = np.finfo(np.float64).tiny
    eta_denominator = (
        float(np.linalg.norm(raw, ord=np.inf))
        + float(np.linalg.norm(gram, ord=np.inf))
        * float(np.linalg.norm(mapping, ord=np.inf))
        + tiny
        if finite
        else float("inf")
    )
    eta = (
        float(np.linalg.norm(raw - expected, ord=np.inf) / eta_denominator)
        if finite
        else float("inf")
    )
    dynamic_limit = float(100.0 * np.finfo(np.float64).eps * gram.shape[0])
    result.update(
        {
            "pass": bool(
                finite
                and raw_error <= 1.0e-9
                and representation_error <= 1.0e-12
                and eta <= dynamic_limit
            ),
            "policy": canonical_trace_gate_policy,
            "backward_error_eta": eta,
            "backward_error_denominator": eta_denominator,
            "dynamic_backward_error_limit": dynamic_limit,
            "family_sha256": canonical_trace_family_sha256,
            "family_provenance": "tracked_compact_record:task039_e7_trace_family_v1.json",
            "finite_all_trace_arrays": finite,
        }
    )
    return result


class _ReusableModeTractionEvaluator:
    """Compile one traction expression and update only field/beta/normal."""

    def __init__(self, spaces: CrossSectionSpaces) -> None:
        self.spaces = spaces
        self.field = fem.Function(spaces.mixed)
        msh = spaces.transverse.mesh
        self.beta = fem.Constant(msh, PETSc.ScalarType(0.0))
        self.sign = fem.Constant(msh, PETSc.ScalarType(1.0))
        Et, Ez = ufl.split(self.field)
        traction_expr = ufl.as_vector(
            (
                self.sign * (PETSc.ScalarType(1j) * self.beta * Et[0] - Ez.dx(0)),
                self.sign * (-Ez.dx(1) + PETSc.ScalarType(1j) * self.beta * Et[1]),
            )
        )
        self.traction_space = fem.functionspace(
            msh,
            element(
                "DG",
                msh.basix_cell(),
                max(spaces.transverse_degree, spaces.longitudinal_degree),
                shape=(2,),
                dtype=default_real_type,
            ),
        )
        points = self.traction_space.element.interpolation_points
        if callable(points):
            points = points()
        self.expression = fem.Expression(traction_expr, points)
        self.traction = fem.Function(self.traction_space)

    @staticmethod
    def _set_constant(constant: fem.Constant, value: complex) -> None:
        scalar = PETSc.ScalarType(value)
        try:
            constant.value[...] = scalar
        except Exception:
            constant.value = scalar

    def evaluate(
        self,
        mode: ClassifiedBiorthogonalMode,
        *,
        local_outward_normal_sign: int,
        beta_override: complex | None = None,
    ) -> fem.Function:
        """Return ``curl(E) x n_local`` in x/y components."""

        if local_outward_normal_sign not in {-1, +1}:
            raise ValueError("The local interface normal sign must be +/-1.")
        field_vector = self.field.x.petsc_vec
        mode.right.right_full.copy(field_vector)
        self.field.x.scatter_forward()
        self._set_constant(
            self.beta,
            complex(mode.beta if beta_override is None else beta_override),
        )
        self._set_constant(self.sign, complex(local_outward_normal_sign))
        self.traction.interpolate(self.expression)
        self.traction.x.scatter_forward()
        return self.traction


def _mode_traction_field(
    mode: ClassifiedBiorthogonalMode,
    spaces: CrossSectionSpaces,
    *,
    local_outward_normal_sign: int,
) -> fem.Function:
    """Convenience wrapper; production loops reuse one evaluator explicitly."""

    return _ReusableModeTractionEvaluator(spaces).evaluate(
        mode,
        local_outward_normal_sign=local_outward_normal_sign,
    )


def _create_rectangular_aij(
    comm: MPI.Intracomm,
    *,
    global_rows: int,
    local_rows: int,
    global_cols: int,
    local_cols: int,
) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((local_rows, global_rows), (local_cols, global_cols)),
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    return matrix


def _assemble_canonical_trace_overlaps(
    system: HybridLocalDtnSystem,
    projection: ModalTraceProjection,
    raw_negative_traces: Sequence[fem.Function],
    canonical_negative_traces: Sequence[fem.Function],
    surface_load: _ReusableInterfaceSurfaceLoad,
    trace_lifter: _ReusableInterfaceLifter,
    log=None,
) -> tuple[
    list[_InterfaceSurfaceLoadEntries],
    int,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Assemble one independent surface-load/lift overlap pass."""

    comm = system.local_mesh.mesh.comm
    mode_count = len(projection.left_traces)
    raw_entries = []
    try:
        for index, left in enumerate(projection.left_traces):
            if log is not None:
                log(
                    f"Task32 {system.side}: assembling left surface load "
                    f"{index + 1}/{mode_count}"
                )
            raw_entries.append(
                surface_load.assemble(
                    left,
                    role=f"row_functional_mode_{index}",
                )
            )
        lift_queries = 0

        def raw_overlap_matrix(traces: Sequence[fem.Function]) -> np.ndarray:
            nonlocal lift_queries
            values = np.empty((len(raw_entries), len(traces)), dtype=np.complex128)
            for column, trace in enumerate(traces):
                if log is not None:
                    log(
                        f"Task32 {system.side}: lifting projection trace "
                        f"{column + 1}/{len(traces)}"
                    )
                field, queries = trace_lifter.lift(trace)
                lift_queries += queries
                system.floquet_data.mpc.homogenize(field)
                field.x.scatter_forward()
                field_vector = field.x.petsc_vec
                for row, entries in enumerate(raw_entries):
                    columns = entries.overlap_rows
                    coefficients = entries.overlap_values
                    local = (
                        complex(
                            np.vdot(
                                coefficients,
                                field_vector.getValues(columns),
                            )
                        )
                        if len(columns)
                        else 0.0 + 0.0j
                    )
                    values[row, column] = complex(comm.allreduce(local, op=MPI.SUM))
            return values

        return (
            raw_entries,
            lift_queries,
            raw_overlap_matrix(projection.right_traces),
            raw_overlap_matrix(raw_negative_traces),
            raw_overlap_matrix(canonical_negative_traces),
        )
    except Exception:
        for entries in raw_entries:
            if entries.full_vector is not None:
                entries.full_vector.destroy()
        raise


def capture_hybrid_trace_audit(
    spaces: CrossSectionSpaces,
    positive_basis: BiorthogonalModeBasis,
    negative_basis: BiorthogonalModeBasis,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    log=None,
) -> dict[str, object]:
    """Capture independent bottom/top trace matrices without building traction.

    This is a research-only seam.  It performs two fresh surface-load/lift
    passes per endcap and returns NumPy evidence before any exact-cell
    traction, augmented operator, solve, or field reconstruction is entered.
    """

    mode_count = len(positive_basis.modes)
    if mode_count == 0 or len(negative_basis.modes) != mode_count:
        raise ValueError("Trace audit requires equal nonzero positive/negative bases.")
    if bottom_system.side != "bottom" or top_system.side != "top":
        raise ValueError("Trace audit systems must be ordered bottom, top.")
    projection = ModalTraceProjection(spaces, positive_basis)
    raw_negative_traces: list[fem.Function] = []
    canonical_negative_traces: list[fem.Function] = []
    repeat_canonical_traces: list[fem.Function] = []
    try:
        for column, mode in enumerate(negative_basis.modes):
            raw_negative_traces.append(
                _trace_from_full_mode_vector(
                    mode.right.right_full,
                    spaces,
                    name=f"task039_audit_negative_trace_{column}",
                )
            )
        canonical_mapping = np.column_stack(
            [projection.project(trace) for trace in raw_negative_traces]
        )
        sides: dict[str, object] = {}

        def assemble_pass(canonical_traces, mapping, system):
            entries = []
            try:
                surface_load = _ReusableInterfaceSurfaceLoad(system)
                trace_lifter = _ReusableInterfaceLifter(system, target_space=system.V)
                entries, queries, gram, raw, canonical = (
                    _assemble_canonical_trace_overlaps(
                        system,
                        projection,
                        raw_negative_traces,
                        canonical_traces,
                        surface_load,
                        trace_lifter,
                        log,
                    )
                )
                return {
                    "surface_gram": gram,
                    "raw_negative_overlap": raw,
                    "canonical_negative_overlap": canonical,
                    "lift_queries": int(queries),
                    "gram_condition": float(np.linalg.cond(gram)),
                    "mapping": mapping.copy(),
                }
            finally:
                for entry in entries:
                    if entry.full_vector is not None:
                        entry.full_vector.destroy()

        canonical_negative_traces = _canonicalized_negative_traces(
            projection, canonical_mapping
        )
        for system in (bottom_system, top_system):
            sides[system.side] = {
                "first": assemble_pass(
                    canonical_negative_traces, canonical_mapping, system
                )
            }
        canonical_negative_traces = []

        repeat_mapping = np.column_stack(
            [projection.project(trace) for trace in raw_negative_traces]
        )
        repeat_canonical_traces = _canonicalized_negative_traces(
            projection, repeat_mapping
        )
        for system in (bottom_system, top_system):
            sides[system.side]["repeat"] = assemble_pass(
                repeat_canonical_traces, repeat_mapping, system
            )
        repeat_canonical_traces = []
        for side, side_passes in sides.items():
            first = side_passes["first"]
            repeat = side_passes["repeat"]
            sides[side] = {
                "surface_gram": first["surface_gram"],
                "raw_negative_overlap": first["raw_negative_overlap"],
                "canonical_negative_overlap": first["canonical_negative_overlap"],
                "canonical_mapping": first["mapping"],
                "repeat_surface_gram": repeat["surface_gram"],
                "repeat_raw_overlap": repeat["raw_negative_overlap"],
                "repeat_canonical_negative_overlap": repeat[
                    "canonical_negative_overlap"
                ],
                "repeat_canonical_mapping": repeat["mapping"],
                "lift_queries": {
                    "first": first["lift_queries"],
                    "repeat": repeat["lift_queries"],
                },
                "gram_condition": first["gram_condition"],
                "repeat_gram_condition": repeat["gram_condition"],
                "audit": _canonical_trace_consistency_audit(
                    first["surface_gram"],
                    first["raw_negative_overlap"],
                    first["canonical_negative_overlap"],
                    first["mapping"],
                ),
                "repeat_audit": _canonical_trace_consistency_audit(
                    repeat["surface_gram"],
                    repeat["raw_negative_overlap"],
                    repeat["canonical_negative_overlap"],
                    repeat["mapping"],
                ),
            }
        column_keys = [
            [
                index,
                str(mode.direction),
                float(mode.beta.real),
                float(mode.beta.imag),
            ]
            for index, mode in enumerate(negative_basis.modes)
        ]
        return {
            "schema": "task039.review-v1.m960-trace-capture.v1",
            "mode_count": mode_count,
            "column_keys": column_keys,
            "mode_identifiers": [
                {
                    "index": index,
                    "key": column_keys[index],
                    "direction": mode.direction,
                    "beta": [float(mode.beta.real), float(mode.beta.imag)],
                }
                for index, mode in enumerate(negative_basis.modes)
            ],
            "degenerate_groups": [
                {
                    "indices": list(group.indices),
                    "keys": [column_keys[index] for index in group.indices],
                    "beta_center": [
                        float(group.beta_center.real),
                        float(group.beta_center.imag),
                    ],
                    "max_relative_beta_spread": float(group.max_relative_beta_spread),
                }
                for group in negative_basis.groups
            ],
            "sides": sides,
        }
    finally:
        projection.destroy()


def _build_projection_matrix(
    system: HybridLocalDtnSystem,
    projection: ModalTraceProjection,
    raw_negative_traces: Sequence[fem.Function],
    canonical_negative_traces: Sequence[fem.Function],
    canonical_negative_mapping: np.ndarray,
    surface_load: _ReusableInterfaceSurfaceLoad,
    trace_lifter: _ReusableInterfaceLifter,
    log=None,
    canonical_trace_gate_policy: str | None = None,
    canonical_trace_family_sha256: str | None = None,
) -> tuple[
    PETSc.Mat,
    int,
    np.ndarray,
    float,
    float,
    tuple[PETSc.Vec, ...],
    np.ndarray,
    np.ndarray,
    float,
    float,
    dict[str, object] | None,
]:
    comm = system.local_mesh.mesh.comm
    mode_count = len(projection.left_traces)
    local_mode_rows = mode_count if comm.rank == comm.size - 1 else 0
    matrix = _create_rectangular_aij(
        comm,
        global_rows=mode_count,
        local_rows=local_mode_rows,
        global_cols=system.global_size,
        local_cols=system.A.getLocalSize()[1],
    )
    try:
        (
            raw_entries,
            lift_queries,
            surface_gram,
            negative_raw,
            canonical_negative_raw,
        ) = _assemble_canonical_trace_overlaps(
            system,
            projection,
            raw_negative_traces,
            canonical_negative_traces,
            surface_load,
            trace_lifter,
            log,
        )
    except Exception:
        matrix.destroy()
        raise
    gram_condition = float(np.linalg.cond(surface_gram))
    if not np.isfinite(gram_condition) or gram_condition > 1.0e12:
        matrix.destroy()
        for entries in raw_entries:
            if entries.full_vector is not None:
                entries.full_vector.destroy()
        raise RuntimeError(
            f"{system.side} lifted interface Gram is ill-conditioned: "
            f"{gram_condition:.6e}."
        )
    inverse_gram = np.linalg.solve(
        surface_gram,
        np.eye(mode_count, dtype=np.complex128),
    )
    positive_identity_error = float(
        np.linalg.norm(inverse_gram @ surface_gram - np.eye(mode_count), ord=np.inf)
    )
    trace_audit = _canonical_trace_consistency_audit(
        surface_gram,
        negative_raw,
        canonical_negative_raw,
        canonical_negative_mapping,
        canonical_trace_gate_policy=canonical_trace_gate_policy,
        canonical_trace_family_sha256=canonical_trace_family_sha256,
    )
    if not trace_audit["pass"]:
        matrix.destroy()
        for entries in raw_entries:
            if entries.full_vector is not None:
                entries.full_vector.destroy()
        if canonical_trace_gate_policy is None:
            raise RuntimeError(
                "Canonicalized negative trace surface integrals disagree: "
                f"raw_relative_error="
                f"{trace_audit['raw_consistency_error']:.3e}, "
                f"representation_relative_error="
                f"{trace_audit['canonical_representation_error']:.3e}, "
                f"limit={trace_audit['tolerance']:.3e}."
            )
        raise RuntimeError(
            "Task039 canonical trace Gate failed: "
            f"policy={trace_audit['policy']!r}, "
            f"raw_forward={trace_audit['raw_consistency_error']:.3e}, "
            f"representation={trace_audit['canonical_representation_error']:.3e}, "
            f"backward_eta={trace_audit['backward_error_eta']:.3e}, "
            f"dynamic_limit={trace_audit['dynamic_backward_error_limit']:.3e}."
        )
    negative_mapping = canonical_negative_mapping.copy()
    for row in range(mode_count):
        for left_index, entries in enumerate(raw_entries):
            columns = entries.matrix_rows
            values = entries.matrix_values
            coefficient = complex(inverse_gram[row, left_index])
            if len(columns) and abs(coefficient) > 0.0:
                matrix.setValues(
                    np.asarray([row], dtype=PETSc.IntType),
                    columns,
                    (coefficient * np.conj(values)).reshape((1, len(columns))),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
    matrix.assemble()
    full_left_vectors = tuple(
        entries.full_vector
        for entries in raw_entries
        if entries.full_vector is not None
    )
    if system.static_condensation is None:
        modal_rhs_correction = np.zeros(mode_count, dtype=np.complex128)
    else:
        if not all(
            entries.tangential_surface_trace_only_verified for entries in raw_entries
        ):
            matrix.destroy()
            for vector in full_left_vectors:
                vector.destroy()
            raise RuntimeError(
                "Hybrid static projection did not verify trace-only "
                "tangential surface loads."
            )
        if full_left_vectors:
            matrix.destroy()
            for vector in full_left_vectors:
                vector.destroy()
            raise RuntimeError(
                "Hybrid trace-only projection unexpectedly retained "
                "full-space left vectors."
            )
        # The verified left vectors have cell-interior entries within the
        # scale-aware floating-point roundoff envelope, so the discarded
        # l_i^H A_ii^-1 b_i term is zero at the qualified trace-only accuracy.
        modal_rhs_correction = np.zeros(mode_count, dtype=np.complex128)
    return (
        matrix,
        int(sum(item.queries for item in raw_entries) + lift_queries),
        negative_mapping,
        gram_condition,
        positive_identity_error,
        full_left_vectors,
        inverse_gram,
        modal_rhs_correction,
        float(trace_audit["raw_consistency_error"]),
        float(trace_audit["canonical_representation_error"]),
        dict(trace_audit) if canonical_trace_gate_policy is not None else None,
    )


def _build_traction_matrix(
    system: HybridLocalDtnSystem,
    modes: Sequence[ClassifiedBiorthogonalMode],
    traction_evaluator: _ReusableModeTractionEvaluator,
    surface_load: _ReusableInterfaceSurfaceLoad,
    full_left_vectors: tuple[PETSc.Vec, ...],
    inverse_gram: np.ndarray,
    traction_beta_per_nm: Sequence[complex],
) -> tuple[PETSc.Mat, int, np.ndarray]:
    comm = system.local_mesh.mesh.comm
    mode_count = len(modes)
    if len(traction_beta_per_nm) != mode_count:
        raise ValueError("Traction beta count must equal the modal count.")
    local_mode_cols = mode_count if comm.rank == comm.size - 1 else 0
    matrix = _create_rectangular_aij(
        comm,
        global_rows=system.global_size,
        local_rows=system.A.getLocalSize()[0],
        global_cols=mode_count,
        local_cols=local_mode_cols,
    )
    query_count = 0
    raw_interior_correction = np.zeros(
        (inverse_gram.shape[1], mode_count),
        dtype=np.complex128,
    )
    sign = system.local_mesh.local_interface_outward_normal_sign
    try:
        for column, mode in enumerate(modes):
            traction = traction_evaluator.evaluate(
                mode,
                local_outward_normal_sign=sign,
                beta_override=traction_beta_per_nm[column],
            )
            entries = surface_load.assemble(
                traction,
                role=f"load_column_{mode.direction}_mode_{column}",
            )
            query_count += entries.queries
            if entries.full_vector is not None:
                if system.static_condensation is None:
                    entries.full_vector.destroy()
                    raise RuntimeError(
                        "Standard Hybrid traction unexpectedly retained a full vector."
                    )
                try:
                    for row, left_vector in enumerate(full_left_vectors):
                        raw_interior_correction[row, column] = (
                            system.static_condensation.interior_cross_bilinear(
                                left_vector,
                                entries.full_vector,
                            )
                        )
                finally:
                    entries.full_vector.destroy()
            elif (
                system.static_condensation is not None
                and not entries.tangential_surface_trace_only_verified
            ):
                matrix.destroy()
                raise RuntimeError(
                    "Hybrid static traction did not verify a trace-only "
                    "tangential surface load."
                )
            if len(entries.matrix_rows):
                # Existing Stage-4 DtN convention inserts -traction in the FE row.
                matrix.setValues(
                    entries.matrix_rows,
                    np.asarray([column], dtype=PETSc.IntType),
                    (-entries.matrix_values).reshape((len(entries.matrix_rows), 1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
    except Exception:
        matrix.destroy()
        raise
    matrix.assemble()
    return (
        matrix,
        query_count,
        inverse_gram @ raw_interior_correction,
    )


def _build_interface_blocks(
    system: HybridLocalDtnSystem,
    spaces: CrossSectionSpaces,
    projection: ModalTraceProjection,
    positive_basis: BiorthogonalModeBasis,
    negative_basis: BiorthogonalModeBasis,
    raw_negative_traces: Sequence[fem.Function],
    canonical_negative_traces: Sequence[fem.Function],
    canonical_negative_mapping: np.ndarray,
    traction_evaluator: _ReusableModeTractionEvaluator | None,
    positive_traction_beta_per_nm: Sequence[complex],
    negative_traction_beta_per_nm: Sequence[complex],
    traction_override: tuple[PETSc.Mat, PETSc.Mat] | None = None,
    log=None,
    canonical_trace_gate_policy: str | None = None,
    canonical_trace_family_sha256: str | None = None,
) -> HybridInterfaceModeBlocks:
    if log is not None:
        log(f"Task32 {system.side}: compiling reusable interface surface form")
    surface_load = _ReusableInterfaceSurfaceLoad(system)
    trace_lifter = _ReusableInterfaceLifter(system, target_space=system.V)
    if log is not None:
        log(f"Task32 {system.side}: assembling canonical trace projection")
    if log is not None and traction_override is None:
        log(f"Task32 {system.side}: assembling positive traction columns")
    projection_matrix = None
    full_left_vectors: tuple[PETSc.Vec, ...] = ()
    positive_traction = None
    negative_traction = None
    positive_queries = 0
    negative_queries = 0
    try:
        (
            projection_matrix,
            projection_queries,
            negative_mapping,
            trace_gram_condition,
            positive_identity_error,
            full_left_vectors,
            inverse_gram,
            modal_rhs_correction,
            canonical_trace_raw_consistency_error,
            canonical_trace_representation_error,
            canonical_trace_gate,
        ) = _build_projection_matrix(
            system,
            projection,
            raw_negative_traces,
            canonical_negative_traces,
            canonical_negative_mapping,
            surface_load,
            trace_lifter,
            log,
            canonical_trace_gate_policy,
            canonical_trace_family_sha256,
        )
        if traction_override is None:
            if traction_evaluator is None:
                raise ValueError("A scalar traction evaluator is required here.")
            (
                positive_traction,
                positive_queries,
                positive_interior_correction,
            ) = _build_traction_matrix(
                system,
                positive_basis.modes,
                traction_evaluator,
                surface_load,
                full_left_vectors,
                inverse_gram,
                positive_traction_beta_per_nm,
            )
            if log is not None:
                log(f"Task32 {system.side}: assembling negative traction columns")
            (
                negative_traction,
                negative_queries,
                negative_interior_correction,
            ) = _build_traction_matrix(
                system,
                negative_basis.modes,
                traction_evaluator,
                surface_load,
                full_left_vectors,
                inverse_gram,
                negative_traction_beta_per_nm,
            )
        else:
            positive_traction, negative_traction = traction_override
            expected = (system.global_size, len(positive_basis.modes))
            if (
                positive_traction.getSize() != expected
                or negative_traction.getSize() != expected
            ):
                raise ValueError(
                    f"Exact traction block shape differs from {system.side} local algebra: "
                    f"expected={expected}, positive={positive_traction.getSize()}, "
                    f"negative={negative_traction.getSize()}"
                )
            positive_interior_correction = np.zeros(
                (inverse_gram.shape[1], len(positive_basis.modes)),
                dtype=np.complex128,
            )
            negative_interior_correction = np.zeros_like(positive_interior_correction)
    except Exception:
        if traction_override is None and positive_traction is not None:
            positive_traction.destroy()
        if traction_override is None and negative_traction is not None:
            negative_traction.destroy()
        if projection_matrix is not None:
            projection_matrix.destroy()
        raise
    finally:
        for vector in full_left_vectors:
            vector.destroy()
    if log is not None:
        log(f"Task32 {system.side}: internal interface blocks complete")
    return HybridInterfaceModeBlocks(
        side=system.side,
        projection=projection_matrix,
        positive_traction=positive_traction,
        negative_traction=negative_traction,
        negative_trace_to_positive=negative_mapping.copy(),
        inverse_trace_gram=np.asarray(inverse_gram, dtype=np.complex128).copy(),
        trace_gram_condition=trace_gram_condition,
        positive_projection_identity_error=positive_identity_error,
        local_fem_outward_normal_sign=(
            system.local_mesh.local_interface_outward_normal_sign
        ),
        lifted_query_points=(projection_queries + positive_queries + negative_queries),
        quadrature_degree=surface_load.quadrature_policy.selected_degree,
        positive_interior_correction=positive_interior_correction,
        negative_interior_correction=negative_interior_correction,
        modal_rhs_correction=modal_rhs_correction,
        tangential_surface_trace_only_verified=bool(
            system.static_condensation is not None
        ),
        interior_modal_pairwise_schur_evaluated=False,
        full_surface_mode_vectors_retained=False,
        canonical_trace_raw_consistency_error=(canonical_trace_raw_consistency_error),
        canonical_trace_representation_error=(canonical_trace_representation_error),
        canonical_trace_gate=canonical_trace_gate,
        quadrature_coefficient_degree=(
            surface_load.quadrature_policy.coefficient_degree
        ),
        surface_reduction_audits=tuple(surface_load.reduction_audits),
    )


def build_hybrid_internal_mode_coupling(
    cfg: SimulationConfig3D,
    spaces: CrossSectionSpaces,
    positive_basis: BiorthogonalModeBasis,
    negative_basis: BiorthogonalModeBasis,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    *,
    length_nm: float = 100.0,
    propagation_model: AxialPropagationModel = "continuous_beta",
    modal_traction_model: ModalTractionModel = "continuous_qep_beta",
    exact_one_cell_work_dir=None,
    canonical_trace_gate_policy: str | None = None,
    canonical_trace_family_sha256: str | None = None,
    stage_callback: Callable[[str, Mapping[str, object]], None] | None = None,
    post_destroy_cleanup: Callable[[], Mapping[str, object]] | None = None,
    log=None,
) -> HybridInternalModeCoupling:
    """Build sparse internal-interface blocks without assembling the full solve."""

    if bottom_system.side != "bottom" or top_system.side != "top":
        raise ValueError("Hybrid local systems must be ordered bottom, top.")
    if bottom_system.assembly_backend_actual != top_system.assembly_backend_actual:
        raise ValueError("Hybrid bottom/top local assembly backends must match.")
    mode_count = len(positive_basis.modes)
    if mode_count == 0 or len(negative_basis.modes) != mode_count:
        raise ValueError(
            "Positive and negative internal bases need equal nonzero size."
        )
    if any(mode.direction != "forward" for mode in positive_basis.modes):
        raise ValueError("The positive internal basis must contain forward modes.")
    if any(mode.direction != "backward" for mode in negative_basis.modes):
        raise ValueError("The negative internal basis must contain backward modes.")

    if log is not None:
        log("Task32 internal coupling: building canonical modal projection")
    projection = ModalTraceProjection(spaces, positive_basis)
    exact_one_cell_audit = None
    exact_traction_overrides = None
    pending_exact_overrides: dict[str, tuple[PETSc.Mat, PETSc.Mat]] = {}
    try:
        canonical_negative_mapping = np.empty(
            (mode_count, mode_count), dtype=np.complex128
        )
        raw_negative_traces: list[fem.Function] = []
        for column, mode in enumerate(negative_basis.modes):
            trace = _trace_from_full_mode_vector(
                mode.right.right_full,
                spaces,
                name=f"task032_negative_trace_{column}",
            )
            raw_negative_traces.append(trace)
            canonical_negative_mapping[:, column] = projection.project(trace)
        positive_mapping = np.column_stack(
            [projection.project(trace) for trace in projection.right_traces]
        )
        identity_error = float(
            np.linalg.norm(positive_mapping - np.eye(mode_count), ord=np.inf)
        )
        if identity_error > 1.0e-9:
            raise RuntimeError(
                f"Positive interface projection identity error {identity_error:.3e}."
            )
        if not np.all(np.isfinite(canonical_negative_mapping)):
            raise RuntimeError("Negative-to-positive interface map is non-finite.")

        propagation = build_two_sided_propagation(
            [*positive_basis.modes, *negative_basis.modes],
            length_nm,
            propagation_model=propagation_model,
            axial_fem_degree=int(cfg.nedelec_degree),
            axial_h_nm=float(cfg.mesh_target_size),
        )
        if modal_traction_model == "continuous_qep_beta":
            positive_traction_beta = tuple(
                complex(mode.beta) for mode in positive_basis.modes
            )
            negative_traction_beta = tuple(
                complex(mode.beta) for mode in negative_basis.modes
            )
        elif modal_traction_model == "scalar_cg_discrete_derivative":
            if propagation_model != "full3d_uniform_cg":
                raise ValueError(
                    "scalar_cg_discrete_derivative traction requires "
                    "full3d_uniform_cg propagation."
                )
            positive_traction_beta = tuple(
                scalar_cg_discrete_traction_beta(
                    mode.beta,
                    degree=int(cfg.nedelec_degree),
                    h_nm=float(cfg.mesh_target_size),
                    direction="forward",
                )
                for mode in positive_basis.modes
            )
            negative_traction_beta = tuple(
                scalar_cg_discrete_traction_beta(
                    mode.beta,
                    degree=int(cfg.nedelec_degree),
                    h_nm=float(cfg.mesh_target_size),
                    direction="backward",
                )
                for mode in negative_basis.modes
            )
        elif modal_traction_model == "full3d_one_cell_exact_schur":
            if propagation_model != "full3d_uniform_cg":
                raise ValueError(
                    "full3d_one_cell_exact_schur requires full3d_uniform_cg."
                )
            if exact_one_cell_work_dir is None:
                raise ValueError(
                    "Exact one-cell traction requires an explicit ignored work directory."
                )
            if not np.isclose(float(length_nm), 100.0, rtol=0.0, atol=1.0e-12):
                raise ValueError(
                    "Exact Hybrid coupling requires a 100 nm middle interval."
                )
            cell_propagation = build_two_sided_propagation(
                [*positive_basis.modes, *negative_basis.modes],
                10.0,
                propagation_model="full3d_uniform_cg",
                axial_fem_degree=int(cfg.nedelec_degree),
                axial_h_nm=10.0,
            )
            from .hybrid_one_cell_exact_traction_builder import (
                build_exact_one_cell_traction_matrices,
            )

            exact_build = build_exact_one_cell_traction_matrices(
                cfg,
                positive_basis,
                raw_negative_traces,
                projection,
                cell_propagation,
                bottom_system,
                top_system,
                work_dir=exact_one_cell_work_dir,
                coupling_propagation_length_nm=float(length_nm),
                log=log,
                stage_callback=stage_callback,
                post_destroy_cleanup=post_destroy_cleanup,
            )
            exact_traction_overrides = exact_build.matrices
            pending_exact_overrides = dict(exact_traction_overrides)
            exact_one_cell_audit = exact_build.audit
            positive_traction_beta = tuple(
                scalar_cg_discrete_traction_beta(
                    mode.beta,
                    degree=int(cfg.nedelec_degree),
                    h_nm=float(cfg.mesh_target_size),
                    direction="forward",
                )
                for mode in positive_basis.modes
            )
            negative_traction_beta = tuple(
                scalar_cg_discrete_traction_beta(
                    mode.beta,
                    degree=int(cfg.nedelec_degree),
                    h_nm=float(cfg.mesh_target_size),
                    direction="backward",
                )
                for mode in negative_basis.modes
            )
            traction_beta_source = (
                "reconstruction_only_scalar_cg_discrete_derivative_"
                "not_used_by_exact_coupling"
            )
        else:
            raise ValueError(
                f"Unsupported modal_traction_model {modal_traction_model!r}."
            )
        canonical_negative_traces = _canonicalized_negative_traces(
            projection,
            canonical_negative_mapping,
        )
    except Exception:
        _destroy_pending_exact_overrides(pending_exact_overrides)
        projection.destroy()
        raise
    bottom = None
    top = None
    try:
        if log is not None:
            log("Task32 internal coupling: compiling reusable traction expression")
        traction_evaluator = (
            None
            if exact_traction_overrides is not None
            else _ReusableModeTractionEvaluator(spaces)
        )
        bottom_override = (
            None
            if exact_traction_overrides is None
            else pending_exact_overrides["bottom"]
        )
        bottom = _build_interface_blocks(
            bottom_system,
            spaces,
            projection,
            positive_basis,
            negative_basis,
            raw_negative_traces,
            canonical_negative_traces,
            canonical_negative_mapping,
            traction_evaluator,
            positive_traction_beta,
            negative_traction_beta,
            bottom_override,
            log,
            canonical_trace_gate_policy,
            canonical_trace_family_sha256,
        )
        if exact_traction_overrides is not None:
            pending_exact_overrides.pop("bottom")
            if post_destroy_cleanup is not None:
                bottom_cleanup = post_destroy_cleanup()
                if stage_callback is not None:
                    stage_callback(
                        "bottom_interface_blocks_heap_cleanup",
                        {
                            "source": "bottom_interface_blocks",
                            "collective_call_completed": bottom_cleanup[
                                "collective_call_completed"
                            ],
                            "max_rss_before_mb": bottom_cleanup["max_rss_before_mb"],
                            "max_rss_after_mb": bottom_cleanup["max_rss_after_mb"],
                            "max_rss_released_mb": bottom_cleanup[
                                "max_rss_released_mb"
                            ],
                            "elapsed_seconds_max_rank": bottom_cleanup[
                                "elapsed_seconds_max_rank"
                            ],
                        },
                    )
        top_override = (
            None if exact_traction_overrides is None else pending_exact_overrides["top"]
        )
        top = _build_interface_blocks(
            top_system,
            spaces,
            projection,
            positive_basis,
            negative_basis,
            raw_negative_traces,
            canonical_negative_traces,
            canonical_negative_mapping,
            traction_evaluator,
            positive_traction_beta,
            negative_traction_beta,
            top_override,
            log,
            canonical_trace_gate_policy,
            canonical_trace_family_sha256,
        )
        if exact_traction_overrides is not None:
            pending_exact_overrides.pop("top")
        mapping_scale = max(
            float(np.linalg.norm(canonical_negative_mapping, ord=np.inf)),
            1.0,
        )
        bottom_top_error = float(
            np.linalg.norm(
                bottom.negative_trace_to_positive - top.negative_trace_to_positive,
                ord=np.inf,
            )
            / mapping_scale
        )
        canonical_error = max(
            float(
                np.linalg.norm(
                    block.negative_trace_to_positive - canonical_negative_mapping,
                    ord=np.inf,
                )
                / mapping_scale
            )
            for block in (bottom, top)
        )
        if log is not None:
            column_errors = {
                block.side: [
                    float(
                        np.linalg.norm(
                            block.negative_trace_to_positive[:, column]
                            - canonical_negative_mapping[:, column]
                        )
                        / max(
                            np.linalg.norm(canonical_negative_mapping[:, column]),
                            1.0e-30,
                        )
                    )
                    for column in range(mode_count)
                ]
                for block in (bottom, top)
            }
            log(
                "Task32 internal coupling diagnostics: "
                f"bottom_gram_condition={bottom.trace_gram_condition:.6e} "
                f"top_gram_condition={top.trace_gram_condition:.6e} "
                f"canonical_mapping_condition="
                f"{np.linalg.cond(canonical_negative_mapping):.6e} "
                f"max_bottom_column_error={max(column_errors['bottom'], default=0.0):.6e} "
                f"max_top_column_error={max(column_errors['top'], default=0.0):.6e} "
                f"mode_count={mode_count}"
            )
        if bottom_top_error > 1.0e-8 or canonical_error > 1.0e-8:
            raise RuntimeError(
                "Lifted negative trace maps disagree across interfaces or with "
                f"the canonical 2D map: bottom_top={bottom_top_error:.3e}, "
                f"canonical={canonical_error:.3e}."
            )
        negative_mapping = 0.5 * (
            bottom.negative_trace_to_positive + top.negative_trace_to_positive
        )
        if bottom.quadrature_degree != top.quadrature_degree:
            raise RuntimeError("Bottom/top interface quadrature policies disagree.")
        if bottom.quadrature_coefficient_degree != top.quadrature_coefficient_degree:
            raise RuntimeError("Bottom/top interface coefficient degrees disagree.")
        return HybridInternalModeCoupling(
            projection=projection,
            bottom=bottom,
            top=top,
            propagation=propagation,
            modal_traction_model=modal_traction_model,
            positive_traction_beta_per_nm=positive_traction_beta,
            negative_traction_beta_per_nm=negative_traction_beta,
            negative_trace_to_positive=negative_mapping,
            positive_projection_identity_error=max(
                identity_error,
                bottom.positive_projection_identity_error,
                top.positive_projection_identity_error,
            ),
            mode_count_per_direction=mode_count,
            interface_quadrature_degree=bottom.quadrature_degree,
            spaces=spaces,
            positive_basis=positive_basis,
            negative_basis=negative_basis,
            interface_quadrature_coefficient_degree=(
                bottom.quadrature_coefficient_degree
            ),
            exact_one_cell_audit=exact_one_cell_audit,
            traction_beta_source=(
                traction_beta_source
                if exact_traction_overrides is not None
                else "coupling_selected_traction_beta_per_nm"
            ),
        )
    except Exception:
        _destroy_pending_exact_overrides(pending_exact_overrides)
        if bottom is not None:
            bottom.destroy()
        if top is not None:
            top.destroy()
        projection.destroy()
        raise
