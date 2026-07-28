from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
import ufl
from dolfinx import fem, geometry, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import SimulationConfig3D
from ..modes.cross_section_spaces import CrossSectionMesh, CrossSectionSpaces
from ..modes.mode_classification import BiorthogonalModeBasis


InterfaceSide = Literal["bottom", "top"]


@dataclass(frozen=True)
class InterfaceConvention:
    """One explicit orientation convention for a hybrid internal interface.

    The canonical electric trace is always stored as ``(E_x, E_y)``.  The
    local 3D FEM block and the middle modal block have opposite outward
    normals on the same geometric plane; both signs are retained so later
    electric/magnetic continuity blocks cannot silently reuse the wrong one.
    """

    side: InterfaceSide
    z_nm: float
    local_fem_outward_normal_sign: int
    modal_outward_normal_sign: int
    middle_adjacent_cell_sign: int

    @property
    def local_fem_outward_normal(self) -> tuple[float, float, float]:
        return (0.0, 0.0, float(self.local_fem_outward_normal_sign))

    @property
    def modal_outward_normal(self) -> tuple[float, float, float]:
        return (0.0, 0.0, float(self.modal_outward_normal_sign))

    def n_cross_tangential(
        self,
        values: np.ndarray,
        *,
        domain: Literal["local_fem", "modal"] = "local_fem",
    ) -> np.ndarray:
        """Return the x-y components of ``n x E_t`` without changing storage."""

        array = np.asarray(values)
        if array.shape[-1] != 2:
            raise ValueError("Tangential values must have final dimension two.")
        sign = (
            self.local_fem_outward_normal_sign
            if domain == "local_fem"
            else self.modal_outward_normal_sign
        )
        result = np.empty_like(array)
        result[..., 0] = -sign * array[..., 1]
        result[..., 1] = sign * array[..., 0]
        return result


@dataclass(frozen=True)
class MatchedInterfaceTrace:
    """Distributed matched trace metadata; the trace field lives on the 2D mesh."""

    convention: InterfaceConvention
    cross_section: CrossSectionMesh
    spaces: CrossSectionSpaces
    source_mesh: mesh.Mesh
    source_interface_facets: np.ndarray
    source_middle_adjacent_cells: np.ndarray
    global_interface_facet_count: int
    global_middle_adjacent_cell_count: int
    global_trace_dofs: int
    coordinate_axis_metadata_gathered: bool = True
    field_or_mode_vector_gathered: bool = False


@dataclass(frozen=True)
class TraceExtractionReport:
    side: InterfaceSide
    z_nm: float
    local_query_points: int
    local_source_evaluations: int
    global_query_points: int
    global_source_evaluations: int
    unresolved_points: int
    used_middle_side_only: bool
    field_vector_gathered: bool = False
    tangential_value_bytes_sent: int = 0
    tangential_value_bytes_received: int = 0


@dataclass(frozen=True)
class ModeTraceRoundTripReport:
    expected_coefficients: np.ndarray
    projected_coefficients: np.ndarray
    coefficient_relative_error: float
    trace_relative_residual: float
    gram_condition: float


@dataclass(frozen=True)
class TraceSubspaceReport:
    dimension: int
    singular_values: tuple[float, ...]
    max_principal_angle_rad: float
    projector_error: float


def interface_convention(
    side: InterfaceSide,
    *,
    bottom_z_nm: float = 10.0,
    top_z_nm: float = 110.0,
) -> InterfaceConvention:
    """Return the frozen Task32 top/bottom sign convention."""

    if side == "bottom":
        # Bottom local FEM block occupies z <= z_b.  Its interface outward
        # normal is +z; the middle modal block sees the opposite -z normal.
        return InterfaceConvention(
            side="bottom",
            z_nm=float(bottom_z_nm),
            local_fem_outward_normal_sign=+1,
            modal_outward_normal_sign=-1,
            middle_adjacent_cell_sign=+1,
        )
    if side == "top":
        # Top local FEM block occupies z >= z_t.  Its interface outward normal
        # is -z; the middle modal block sees the opposite +z normal.
        return InterfaceConvention(
            side="top",
            z_nm=float(top_z_nm),
            local_fem_outward_normal_sign=-1,
            modal_outward_normal_sign=+1,
            middle_adjacent_cell_sign=-1,
        )
    raise ValueError(f"Unsupported interface side: {side}")


def _global_coordinate_axis(msh: mesh.Mesh, component: int) -> np.ndarray:
    local = np.unique(np.asarray(msh.geometry.x[:, component], dtype=np.float64))
    gathered = msh.comm.allgather(local)
    if not gathered:
        return np.empty(0, dtype=np.float64)
    return np.unique(np.concatenate(gathered))


def _middle_adjacent_owned_cells(
    msh: mesh.Mesh,
    convention: InterfaceConvention,
    tolerance: float,
) -> np.ndarray:
    tdim = msh.topology.dim
    num_owned = msh.topology.index_map(tdim).size_local
    dofmap = np.asarray(msh.geometry.dofmap)
    coordinates = np.asarray(msh.geometry.x)
    selected: list[int] = []
    for cell in range(num_owned):
        cell_z = coordinates[dofmap[cell], 2]
        touches_from_middle = (
            abs(float(np.min(cell_z)) - convention.z_nm) <= tolerance
            if convention.middle_adjacent_cell_sign > 0
            else abs(float(np.max(cell_z)) - convention.z_nm) <= tolerance
        )
        if touches_from_middle:
            selected.append(cell)
    return np.asarray(selected, dtype=np.int32)


def build_matched_interface_trace(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    source_mesh: mesh.Mesh,
    side: InterfaceSide,
    *,
    bottom_z_nm: float = 10.0,
    top_z_nm: float = 110.0,
) -> MatchedInterfaceTrace:
    """Validate and bind one matched 3D/2D Nedelec interface."""

    if source_mesh.topology.dim != 3 or source_mesh.geometry.dim != 3:
        raise ValueError("The source field must live on a three-dimensional mesh.")
    if cross_section.mesh.topology.dim != 2:
        raise ValueError("The canonical trace must live on a two-dimensional mesh.")
    if source_mesh.comm.size != cross_section.mesh.comm.size:
        raise ValueError("Source and trace communicators have different sizes.")

    convention = interface_convention(
        side, bottom_z_nm=bottom_z_nm, top_z_nm=top_z_nm
    )
    tolerance = 1.0e-10 * max(cfg.period_x, cfg.period_y, 1.0)
    source_x = _global_coordinate_axis(source_mesh, 0)
    source_y = _global_coordinate_axis(source_mesh, 1)
    source_z = _global_coordinate_axis(source_mesh, 2)
    if not np.allclose(source_x, cross_section.x_values, rtol=0.0, atol=tolerance):
        raise ValueError("The 3D and 2D x axes are not matched.")
    if not np.allclose(source_y, cross_section.y_values, rtol=0.0, atol=tolerance):
        raise ValueError("The 3D and 2D y axes are not matched.")
    if not np.any(np.isclose(source_z, convention.z_nm, rtol=0.0, atol=tolerance)):
        raise ValueError(f"Interface z={convention.z_nm:g} nm is not a 3D mesh plane.")

    fdim = source_mesh.topology.dim - 1
    source_mesh.topology.create_entities(fdim)
    facets = mesh.locate_entities(
        source_mesh,
        fdim,
        lambda x: np.isclose(x[2], convention.z_nm, rtol=0.0, atol=tolerance),
    )
    num_owned_facets = source_mesh.topology.index_map(fdim).size_local
    facets = np.asarray(facets[facets < num_owned_facets], dtype=np.int32)
    adjacent_cells = _middle_adjacent_owned_cells(
        source_mesh, convention, tolerance
    )
    global_facets = int(source_mesh.comm.allreduce(len(facets), op=MPI.SUM))
    global_cells = int(
        source_mesh.comm.allreduce(len(adjacent_cells), op=MPI.SUM)
    )
    expected_cells = int(cross_section.mesh_cells[0] * cross_section.mesh_cells[1])
    if global_facets != expected_cells:
        raise RuntimeError(
            f"Interface facet count {global_facets} does not match {expected_cells}."
        )
    if global_cells != expected_cells:
        raise RuntimeError(
            "Middle-side adjacent cell count "
            f"{global_cells} does not match {expected_cells}."
        )

    trace_map = spaces.transverse.dofmap.index_map
    global_trace_dofs = int(
        trace_map.size_global * spaces.transverse.dofmap.index_map_bs
    )
    return MatchedInterfaceTrace(
        convention=convention,
        cross_section=cross_section,
        spaces=spaces,
        source_mesh=source_mesh,
        source_interface_facets=facets,
        source_middle_adjacent_cells=adjacent_cells,
        global_interface_facet_count=global_facets,
        global_middle_adjacent_cell_count=global_cells,
        global_trace_dofs=global_trace_dofs,
    )


class _DistributedTangentialEvaluator:
    """Collectively evaluate 3D values and return them to 2D request owners."""

    def __init__(
        self,
        source: fem.Function,
        interface: MatchedInterfaceTrace,
        *,
        padding: float,
    ) -> None:
        self._source = source
        self._interface = interface
        self._padding = float(padding)
        self.local_query_points = 0
        self.local_source_evaluations = 0
        self.unresolved_points = 0
        self.local_tangential_value_bytes_sent = 0
        self.local_tangential_value_bytes_received = 0

    def __call__(self, x: np.ndarray) -> np.ndarray:
        xy = np.asarray(x[:2, :].T, dtype=np.float64)
        points = np.empty((len(xy), 3), dtype=np.float64)
        points[:, :2] = xy
        points[:, 2] = self._interface.convention.z_nm
        self.local_query_points += len(points)

        ownership = geometry.determine_point_ownership(
            self._interface.source_mesh,
            points,
            self._padding,
            cells=self._interface.source_middle_adjacent_cells,
        )
        src_owner = np.asarray(ownership.src_owner, dtype=np.int32)
        dest_owner = np.asarray(ownership.dest_owner, dtype=np.int32)
        dest_points = np.asarray(ownership.dest_points, dtype=np.float64).reshape(-1, 3)
        dest_cells = np.asarray(ownership.dest_cells, dtype=np.int32)
        self.unresolved_points += int(np.count_nonzero(src_owner < 0))
        if np.any(src_owner < 0):
            raise RuntimeError("At least one interface interpolation point is unresolved.")

        evaluated = (
            np.asarray(
                self._source.eval(dest_points, dest_cells), dtype=PETSc.ScalarType
            ).reshape(len(dest_points), -1)
            if len(dest_points)
            else np.empty((0, 3), dtype=PETSc.ScalarType)
        )
        if evaluated.shape[1] != 3:
            raise ValueError("The 3D source function must have three value components.")
        tangential = evaluated[:, :2]
        self.local_source_evaluations += len(tangential)

        comm = self._interface.source_mesh.comm
        send: list[list[tuple[complex, complex]]] = [
            [] for _ in range(comm.size)
        ]
        for owner, value in zip(dest_owner, tangential):
            send[int(owner)].append((complex(value[0]), complex(value[1])))
        received = comm.alltoall(send)
        value_bytes = 2 * np.dtype(PETSc.ScalarType).itemsize
        self.local_tangential_value_bytes_sent += int(
            sum(
                len(values) * value_bytes
                for rank, values in enumerate(send)
                if rank != comm.rank
            )
        )
        self.local_tangential_value_bytes_received += int(
            sum(
                len(values) * value_bytes
                for rank, values in enumerate(received)
                if rank != comm.rank
            )
        )

        result = np.empty((len(points), 2), dtype=PETSc.ScalarType)
        offsets = np.zeros(comm.size, dtype=np.int32)
        for index, owner in enumerate(src_owner):
            owner_index = int(owner)
            offset = int(offsets[owner_index])
            if offset >= len(received[owner_index]):
                raise RuntimeError("Returned interface values do not match point ownership.")
            result[index, :] = received[owner_index][offset]
            offsets[owner_index] += 1
        for rank, values in enumerate(received):
            if int(offsets[rank]) != len(values):
                raise RuntimeError("Unused returned interface values indicate an ordering error.")
        return result.T


def extract_tangential_trace(
    source: fem.Function,
    interface: MatchedInterfaceTrace,
    *,
    padding: float | None = None,
) -> tuple[fem.Function, TraceExtractionReport]:
    """Interpolate ``(E_x,E_y)`` into the matched 2D Nedelec trace space."""

    source_shape = tuple(source.function_space.element.value_shape)
    if source_shape != (3,):
        raise ValueError(f"Expected a three-component 3D source, got {source_shape}.")
    if source.function_space.mesh is not interface.source_mesh:
        raise ValueError("The source function does not live on the bound 3D mesh.")
    comm = interface.source_mesh.comm
    padding_value = (
        1.0e-10
        * max(
            interface.cross_section.x_values[-1]
            - interface.cross_section.x_values[0],
            interface.cross_section.y_values[-1]
            - interface.cross_section.y_values[0],
            1.0,
        )
        if padding is None
        else float(padding)
    )
    evaluator = _DistributedTangentialEvaluator(
        source, interface, padding=padding_value
    )
    trace = fem.Function(
        interface.spaces.transverse,
        name=f"task032_{interface.convention.side}_Et_trace",
    )
    trace_cells = np.arange(
        interface.cross_section.mesh.topology.index_map(2).size_local,
        dtype=np.int32,
    )
    trace.interpolate(evaluator, trace_cells)
    trace.x.scatter_forward()
    report = TraceExtractionReport(
        side=interface.convention.side,
        z_nm=interface.convention.z_nm,
        local_query_points=evaluator.local_query_points,
        local_source_evaluations=evaluator.local_source_evaluations,
        global_query_points=int(
            comm.allreduce(evaluator.local_query_points, op=MPI.SUM)
        ),
        global_source_evaluations=int(
            comm.allreduce(evaluator.local_source_evaluations, op=MPI.SUM)
        ),
        unresolved_points=int(comm.allreduce(evaluator.unresolved_points, op=MPI.SUM)),
        used_middle_side_only=True,
        tangential_value_bytes_sent=int(
            comm.allreduce(
                evaluator.local_tangential_value_bytes_sent,
                op=MPI.SUM,
            )
        ),
        tangential_value_bytes_received=int(
            comm.allreduce(
                evaluator.local_tangential_value_bytes_received,
                op=MPI.SUM,
            )
        ),
    )
    return trace, report


def _trace_from_full_mode_vector(
    full_vector: PETSc.Vec,
    spaces: CrossSectionSpaces,
    *,
    name: str,
) -> fem.Function:
    mixed = fem.Function(spaces.mixed)
    if int(full_vector.getSize()) != int(mixed.x.petsc_vec.getSize()):
        raise ValueError("Mode vector and mixed function space have different sizes.")
    full_vector.copy(mixed.x.petsc_vec)
    mixed.x.scatter_forward()
    trace = fem.Function(spaces.transverse, name=name)
    if len(spaces.transverse_to_mixed) != len(trace.x.array):
        raise RuntimeError("Collapsed transverse map has an unexpected local shape.")
    trace.x.array[:] = mixed.x.array[spaces.transverse_to_mixed]
    trace.x.scatter_forward()
    return trace


def _assemble_trace_mass(
    spaces: CrossSectionSpaces,
    *,
    quadrature_degree: int | None = None,
) -> PETSc.Mat:
    trial = ufl.TrialFunction(spaces.transverse)
    test = ufl.TestFunction(spaces.transverse)
    form = ufl.inner(trial, test) * ufl.dx
    compiler_options = (
        {}
        if quadrature_degree is None
        else {"quadrature_degree": int(quadrature_degree)}
    )
    matrix = fem_petsc.assemble_matrix(
        fem.form(form, form_compiler_options=compiler_options),
        bcs=[],
    )
    matrix.assemble()
    return matrix


def _overlap_matrix(
    mass: PETSc.Mat,
    left: Sequence[fem.Function],
    right: Sequence[fem.Function],
) -> np.ndarray:
    overlap = np.empty((len(left), len(right)), dtype=np.complex128)
    action = mass.createVecLeft()
    try:
        for column, right_field in enumerate(right):
            mass.mult(right_field.x.petsc_vec, action)
            for row, left_field in enumerate(left):
                # PETSc VecDot(x, y) returns y^H x.
                overlap[row, column] = complex(
                    action.dot(left_field.x.petsc_vec)
                )
    finally:
        action.destroy()
    return overlap


def _mass_norm(mass: PETSc.Mat, field: fem.Function) -> float:
    action = mass.createVecLeft()
    try:
        mass.mult(field.x.petsc_vec, action)
        value = complex(action.dot(field.x.petsc_vec))
    finally:
        action.destroy()
    scale = max(abs(value.real), 1.0)
    if abs(value.imag) > 1.0e-10 * scale or value.real < -1.0e-12 * scale:
        raise RuntimeError(f"Trace mass norm is not positive-real: {value!r}.")
    return float(np.sqrt(max(value.real, 0.0)))


class ModalTraceProjection:
    """Distributed right reconstruction and left Petrov projection.

    No dense ``N_Gamma x N_Gamma`` object is formed.  Storage consists of one
    sparse trace mass matrix, distributed left/right trace columns, and the
    replicated small ``M x M`` Gram matrix.
    """

    def __init__(
        self,
        spaces: CrossSectionSpaces,
        basis: BiorthogonalModeBasis,
        *,
        mode_indices: Sequence[int] | None = None,
        condition_limit: float = 1.0e12,
        quadrature_degree: int | None = None,
        test_basis: Literal["biorthogonal_left", "right_galerkin"] = (
            "biorthogonal_left"
        ),
    ) -> None:
        selected = (
            tuple(range(len(basis.modes)))
            if mode_indices is None
            else tuple(int(index) for index in mode_indices)
        )
        if not selected:
            raise ValueError("At least one interface mode is required.")
        if len(set(selected)) != len(selected):
            raise ValueError("Interface mode indices must be unique.")
        if min(selected) < 0 or max(selected) >= len(basis.modes):
            raise IndexError("An interface mode index is out of range.")

        self.spaces = spaces
        self.mode_indices = selected
        self.right_traces = tuple(
            _trace_from_full_mode_vector(
                basis.modes[index].right.right_full,
                spaces,
                name=f"task032_right_trace_{index}",
            )
            for index in selected
        )
        if test_basis == "biorthogonal_left":
            self.left_traces = tuple(
                _trace_from_full_mode_vector(
                    basis.modes[index].left_full,
                    spaces,
                    name=f"task032_left_trace_{index}",
                )
                for index in selected
            )
        elif test_basis == "right_galerkin":
            self.left_traces = self.right_traces
        else:
            raise ValueError(f"Unsupported modal trace test basis {test_basis!r}.")
        self.test_basis = test_basis
        if quadrature_degree is not None and int(quadrature_degree) < 1:
            raise ValueError("Trace quadrature degree must be positive.")
        self.quadrature_degree = (
            None if quadrature_degree is None else int(quadrature_degree)
        )
        self.mass = _assemble_trace_mass(
            spaces,
            quadrature_degree=self.quadrature_degree,
        )
        self.gram = _overlap_matrix(
            self.mass, self.left_traces, self.right_traces
        )
        self.gram_condition = float(np.linalg.cond(self.gram))
        if not np.isfinite(self.gram_condition) or self.gram_condition > condition_limit:
            self.mass.destroy()
            raise RuntimeError(
                "Interface left/right Gram block is singular or ill-conditioned: "
                f"cond={self.gram_condition:.6e}."
            )
        self.global_trace_dofs = int(self.mass.getSize()[0])
        self.reconstruction_shape = (self.global_trace_dofs, len(selected))
        self.projection_shape = (len(selected), self.global_trace_dofs)
        self.small_dense_shape = tuple(int(value) for value in self.gram.shape)
        self.full_vector_gathered = False
        self.dense_interface_operator_formed = False
        self._destroyed = False

    def reconstruct(self, coefficients: Sequence[complex]) -> fem.Function:
        values = np.asarray(coefficients, dtype=np.complex128)
        if values.shape != (len(self.right_traces),):
            raise ValueError("Coefficient vector has the wrong shape.")
        trace = fem.Function(self.spaces.transverse, name="task032_reconstructed_trace")
        trace.x.array[:] = 0.0
        for value, right in zip(values, self.right_traces):
            trace.x.array[:] += PETSc.ScalarType(value) * right.x.array
        trace.x.scatter_forward()
        return trace

    def project(self, trace: fem.Function) -> np.ndarray:
        if trace.function_space is not self.spaces.transverse:
            raise ValueError("Trace function is not in the canonical interface space.")
        action = self.mass.createVecLeft()
        try:
            self.mass.mult(trace.x.petsc_vec, action)
            raw = np.asarray(
                [complex(action.dot(left.x.petsc_vec)) for left in self.left_traces],
                dtype=np.complex128,
            )
        finally:
            action.destroy()
        return np.linalg.solve(self.gram, raw)

    def relative_residual(
        self, trace: fem.Function, coefficients: Sequence[complex]
    ) -> float:
        reconstructed = self.reconstruct(coefficients)
        difference = fem.Function(self.spaces.transverse)
        difference.x.array[:] = trace.x.array - reconstructed.x.array
        difference.x.scatter_forward()
        numerator = _mass_norm(self.mass, difference)
        denominator = _mass_norm(self.mass, trace)
        return float(numerator / max(denominator, 1.0e-30))

    def round_trip(
        self, coefficients: Sequence[complex]
    ) -> ModeTraceRoundTripReport:
        expected = np.asarray(coefficients, dtype=np.complex128)
        trace = self.reconstruct(expected)
        projected = self.project(trace)
        coefficient_error = float(
            np.linalg.norm(projected - expected)
            / max(np.linalg.norm(expected), 1.0e-30)
        )
        return ModeTraceRoundTripReport(
            expected_coefficients=expected.copy(),
            projected_coefficients=projected,
            coefficient_relative_error=coefficient_error,
            trace_relative_residual=self.relative_residual(trace, projected),
            gram_condition=self.gram_condition,
        )

    def destroy(self) -> None:
        if not self._destroyed:
            self.mass.destroy()
            self._destroyed = True


def trace_subspace_report(
    mass: PETSc.Mat,
    first: Sequence[fem.Function],
    second: Sequence[fem.Function],
    *,
    rank_tolerance: float = 1.0e-12,
) -> TraceSubspaceReport:
    """Compare near-degenerate trace spans without matching individual vectors."""

    if len(first) != len(second) or not first:
        raise ValueError("Subspace bases must have the same positive dimension.")
    gram_first = _overlap_matrix(mass, first, first)
    gram_second = _overlap_matrix(mass, second, second)
    cross = _overlap_matrix(mass, first, second)

    def whitening(gram: np.ndarray) -> np.ndarray:
        hermitian = 0.5 * (gram + gram.conj().T)
        values, vectors = np.linalg.eigh(hermitian)
        scale = max(float(np.max(np.abs(values))), 1.0)
        if np.min(values) <= rank_tolerance * scale:
            raise RuntimeError("A trace subspace basis is rank deficient.")
        return vectors @ np.diag(1.0 / np.sqrt(values))

    first_white = whitening(gram_first)
    second_white = whitening(gram_second)
    normalized_cross = first_white.conj().T @ cross @ second_white
    singular_values = np.clip(
        np.linalg.svd(normalized_cross, compute_uv=False).real, 0.0, 1.0
    )
    angles = np.arccos(singular_values)
    projector_error = float(
        np.sqrt(max(len(first) - np.sum(singular_values**2), 0.0))
    )
    return TraceSubspaceReport(
        dimension=len(first),
        singular_values=tuple(float(value) for value in singular_values),
        max_principal_angle_rad=float(np.max(angles)),
        projector_error=projector_error,
    )
