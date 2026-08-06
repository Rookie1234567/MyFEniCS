"""Research-only E1a owner-local basis/action and partition primitives.

No modes, canonical ordering, coarse PC, or Full3D integration are built here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

import numpy as np
from dolfinx import cpp, fem
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve, qr, svd


def _require_research_opt_in(research_opt_in: bool) -> None:
    if research_opt_in is not True:
        raise ValueError(
            "Task037 E1 modal-basis foundation is research-only; "
            "pass research_opt_in=True explicitly."
        )


def _as_complex_array(values: Any, *, ndim: int | None = None) -> np.ndarray:
    array = np.asarray(values, dtype=np.complex128)
    if ndim is not None and array.ndim != ndim:
        raise ValueError(f"expected an array with ndim={ndim}, got {array.ndim}")
    if not np.all(np.isfinite(array)):
        raise ValueError("modal basis values must be finite")
    return array


def _mpi_comm(vector: PETSc.Vec) -> MPI.Comm:
    return vector.getComm().tompi4py()


def _global_norm(vector: PETSc.Vec) -> float:
    values = _as_complex_array(vector.getArray(readonly=True), ndim=1)
    local_squared = float(np.vdot(values, values).real)
    total_squared = _mpi_comm(vector).allreduce(local_squared, op=MPI.SUM)
    return float(np.sqrt(total_squared))


@dataclass
class OwnerLocalBasis:
    """A collection of distributed PETSc columns with no global dense copy."""

    global_rows: int
    columns: tuple[PETSc.Vec, ...]
    label: str = "Z"
    research_only: bool = True
    _destroyed: bool = False

    def __post_init__(self) -> None:
        if self.research_only is not True:
            raise ValueError("OwnerLocalBasis must remain research-only")
        self.columns = tuple(self.columns)
        if not self.columns:
            raise ValueError("OwnerLocalBasis requires at least one column")
        if int(self.global_rows) <= 0:
            raise ValueError("OwnerLocalBasis global_rows must be positive")
        first_size = int(self.columns[0].getSize())
        if first_size != int(self.global_rows):
            raise ValueError("basis column size differs from global_rows")
        ownership = self.columns[0].getOwnershipRange()
        for column in self.columns:
            if int(column.getSize()) != first_size:
                raise ValueError("basis columns have inconsistent global sizes")
            if column.getOwnershipRange() != ownership:
                raise ValueError("basis columns have inconsistent ownership")
            _as_complex_array(column.getArray(readonly=True), ndim=1)

    @classmethod
    def from_vectors(
        cls,
        columns: Iterable[PETSc.Vec],
        *,
        label: str,
        research_opt_in: bool = False,
    ) -> OwnerLocalBasis:
        _require_research_opt_in(research_opt_in)
        values = tuple(columns)
        if not values:
            raise ValueError("from_vectors requires non-empty columns")
        return cls(int(values[0].getSize()), values, label=label)

    @classmethod
    def from_local_array(
        cls,
        local_values: Any,
        *,
        global_rows: int,
        comm: MPI.Comm,
        label: str,
        research_opt_in: bool = False,
    ) -> OwnerLocalBasis:
        _require_research_opt_in(research_opt_in)
        array = _as_complex_array(local_values)
        if array.ndim == 1:
            array = array[:, None]
        if array.ndim != 2 or array.shape[1] == 0:
            raise ValueError("local_values must be a non-empty 1D/2D array")
        if int(array.shape[0]) > int(global_rows):
            raise ValueError("local rows exceed global rows")

        columns: list[PETSc.Vec] = []
        try:
            for index in range(array.shape[1]):
                vector = PETSc.Vec().createMPI(
                    (int(array.shape[0]), int(global_rows)),
                    comm=comm,
                )
                if vector.getLocalSize() != int(array.shape[0]):
                    vector.destroy()
                    raise ValueError("PETSc owner-local size differs from input")
                vector.getArray()[:] = array[:, index]
                vector.assemble()
                columns.append(vector)
        except Exception:
            for vector in columns:
                vector.destroy()
            raise
        return cls.from_vectors(
            columns,
            label=label,
            research_opt_in=True,
        )

    @property
    def column_count(self) -> int:
        return len(self.columns)

    @property
    def ownership_range(self) -> tuple[int, int]:
        self._require_live()
        return tuple(map(int, self.columns[0].getOwnershipRange()))

    @property
    def comm(self) -> MPI.Comm:
        self._require_live()
        return _mpi_comm(self.columns[0])

    def local_matrix(self) -> np.ndarray:
        self._require_live()
        return np.column_stack(
            [
                _as_complex_array(column.getArray(readonly=True), ndim=1)
                for column in self.columns
            ]
        )

    def combine(
        self,
        coefficients: Any,
        *,
        research_opt_in: bool = False,
    ) -> PETSc.Vec:
        _require_research_opt_in(research_opt_in)
        self._require_live()
        values = _as_complex_array(coefficients, ndim=1)
        if values.shape != (self.column_count,):
            raise ValueError("coefficient count differs from basis column count")
        result = self.columns[0].duplicate()
        result.set(PETSc.ScalarType(0.0))
        try:
            for coefficient, column in zip(values, self.columns, strict=True):
                result.axpy(PETSc.ScalarType(coefficient), column)
            result.assemble()
            return result
        except Exception:
            result.destroy()
            raise

    def apply(
        self,
        operator: PETSc.Mat,
        *,
        label: str = "Y",
        research_opt_in: bool = False,
    ) -> OwnerLocalBasis:
        _require_research_opt_in(research_opt_in)
        self._require_live()
        rows, columns = map(int, operator.getSize())
        if columns != self.global_rows:
            raise ValueError("action column size differs from basis row count")
        targets: list[PETSc.Vec] = []
        try:
            for source in self.columns:
                target = operator.createVecLeft()
                operator.mult(source, target)
                _as_complex_array(target.getArray(readonly=True), ndim=1)
                targets.append(target)
        except Exception:
            for target in targets:
                target.destroy()
            raise
        return OwnerLocalBasis.from_vectors(
            targets,
            label=label,
            research_opt_in=True,
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        for column in self.columns:
            column.destroy()
        self.columns = ()
        self._destroyed = True

    def _require_live(self) -> None:
        if self._destroyed:
            raise RuntimeError(f"{self.label} basis has already been destroyed")


@dataclass(frozen=True)
class ColumnNormalizationAudit:
    column: int
    norm_before: float
    norm_after: float
    pivot_global_row: int


def _pivot_value(vector: PETSc.Vec, global_row: int) -> complex:
    first, last = map(int, vector.getOwnershipRange())
    local_value: complex | None = None
    if first <= global_row < last:
        values = _as_complex_array(vector.getArray(readonly=True), ndim=1)
        local_value = complex(values[global_row - first])
    values = _mpi_comm(vector).allgather(local_value)
    matches = [value for value in values if value is not None]
    if len(matches) != 1:
        raise RuntimeError("pivot row does not have exactly one PETSc owner")
    return matches[0]


def normalize_owner_local_columns(
    basis: OwnerLocalBasis,
    *,
    research_opt_in: bool = False,
) -> tuple[OwnerLocalBasis, tuple[ColumnNormalizationAudit, ...]]:
    """Normalize columns and fix phase by smallest global maximum entry."""

    _require_research_opt_in(research_opt_in)
    basis._require_live()
    normalized: list[PETSc.Vec] = []
    audits: list[ColumnNormalizationAudit] = []
    try:
        for column_index, source in enumerate(basis.columns):
            target = source.duplicate()
            source.copy(target)
            norm_before = _global_norm(target)
            if not np.isfinite(norm_before) or norm_before <= 0.0:
                target.destroy()
                raise ValueError("basis columns must have a finite nonzero norm")
            target.scale(PETSc.ScalarType(1.0 / norm_before))

            local_values = _as_complex_array(
                target.getArray(readonly=True),
                ndim=1,
            )
            first, _last = map(int, target.getOwnershipRange())
            local_max = float(np.max(np.abs(local_values), initial=0.0))
            global_max = float(basis.comm.allreduce(local_max, op=MPI.MAX))
            candidates = [
                first + index
                for index, value in enumerate(np.abs(local_values))
                if value == global_max
            ]
            local_pivot = min(candidates, default=basis.global_rows)
            pivot = int(basis.comm.allreduce(local_pivot, op=MPI.MIN))
            if pivot >= basis.global_rows or global_max <= 0.0:
                target.destroy()
                raise ValueError("basis columns must contain a nonzero pivot")
            pivot_value = _pivot_value(target, pivot)
            phase = pivot_value / abs(pivot_value)
            multiplier = np.conj(phase)
            target.getArray()[:] *= multiplier
            target.assemble()
            norm_after = _global_norm(target)
            normalized.append(target)
            audits.append(
                ColumnNormalizationAudit(
                    column=column_index,
                    norm_before=norm_before,
                    norm_after=norm_after,
                    pivot_global_row=pivot,
                )
            )
    except Exception:
        for vector in normalized:
            vector.destroy()
        raise
    return (
        OwnerLocalBasis.from_vectors(
            normalized,
            label=f"{basis.label}_normalized",
            research_opt_in=True,
        ),
        tuple(audits),
    )


@dataclass(frozen=True)
class ActionSpaceAudit:
    global_rows: int
    column_count: int
    effective_rank: int
    retained_condition_number: float
    singular_values: tuple[float, ...]
    rank_tolerance: float
    local_qr_method: str
    stacked_r_svd_method: str
    stacked_r_shape: tuple[int, int]
    normal_equations_used: bool = False


def audit_owner_local_action_space(
    basis: OwnerLocalBasis,
    *,
    rank_tolerance: float = 1.0e-12,
    research_opt_in: bool = False,
) -> ActionSpaceAudit:
    _require_research_opt_in(research_opt_in)
    basis._require_live()
    if rank_tolerance <= 0.0:
        raise ValueError("rank_tolerance must be positive")
    local = basis.local_matrix()
    if local.shape[0] == 0:
        local_r = np.zeros((0, basis.column_count), dtype=np.complex128)
    else:
        try:
            _local_q, local_r = qr(
                local,
                mode="economic",
                pivoting=False,
                check_finite=True,
            )
        except Exception as exc:
            local_r = None
            local_error = f"{type(exc).__name__}: {exc}"
        else:
            local_error = None
    if local.shape[0] == 0:
        local_error = None
    errors = basis.comm.allgather(local_error)
    first_error = next((error for error in errors if error is not None), None)
    if first_error is not None:
        raise RuntimeError(f"local action QR failed collectively: {first_error}")

    pieces = basis.comm.gather(
        np.asarray(local_r, dtype=np.complex128),
        root=0,
    )
    payload: dict[str, Any] | None = None
    error_message: str | None = None
    if basis.comm.rank == 0:
        try:
            stacked_r = (
                np.vstack(pieces)
                if pieces
                else np.zeros((0, basis.column_count), dtype=np.complex128)
            )
            if stacked_r.shape[0] == 0:
                raise ValueError("action basis has no owner-local rows")
            _stacked_q, stacked_qr_r = qr(
                stacked_r,
                mode="economic",
                pivoting=False,
                check_finite=True,
            )
            singular = svd(
                stacked_qr_r,
                full_matrices=False,
                compute_uv=False,
                check_finite=True,
            )
            if singular.size == 0 or not np.all(np.isfinite(singular)):
                raise ValueError("action singular spectrum is empty or non-finite")
            scale = max(float(singular[0]), np.finfo(float).tiny)
            effective_rank = int(np.count_nonzero(singular > rank_tolerance * scale))
            retained_condition = (
                float(singular[0] / singular[effective_rank - 1])
                if effective_rank > 0
                else float("inf")
            )
            payload = {
                "global_rows": basis.global_rows,
                "column_count": basis.column_count,
                "effective_rank": effective_rank,
                "retained_condition_number": retained_condition,
                "singular_values": tuple(float(value) for value in singular),
                "rank_tolerance": float(rank_tolerance),
                "local_qr_method": "scipy.linalg.qr",
                "stacked_r_svd_method": "scipy.linalg.qr + scipy.linalg.svd",
                "stacked_r_shape": tuple(map(int, stacked_r.shape)),
            }
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
    ok, payload, error_message = basis.comm.bcast(
        (payload is not None, payload, error_message),
        root=0,
    )
    if not ok:
        raise RuntimeError(f"root stacked-R audit failed collectively: {error_message}")
    assert payload is not None
    return ActionSpaceAudit(
        **payload,
    )


@dataclass(frozen=True)
class PrescribedInterfaceSolution:
    values: np.ndarray
    retained_rows: tuple[int, ...]
    interface_rows: tuple[int, ...]
    retained_residual_norm: float
    retained_residual_relative: float
    factor_released: bool


def solve_homogeneous_prescribed_interface(
    matrix: Any,
    interface_rows: Iterable[int],
    interface_values: Any,
    *,
    factor_factory: Callable[[np.ndarray], Any] | None = None,
    research_opt_in: bool = False,
) -> PrescribedInterfaceSolution:
    _require_research_opt_in(research_opt_in)
    array = _as_complex_array(matrix, ndim=2)
    if array.shape[0] != array.shape[1]:
        raise ValueError("partition matrix must be square")
    size = int(array.shape[0])
    gamma = np.asarray(tuple(interface_rows), dtype=np.int64)
    values = _as_complex_array(interface_values, ndim=1)
    if gamma.shape != values.shape or gamma.size == 0:
        raise ValueError("interface rows and values must be non-empty and aligned")
    if np.any(gamma < 0) or np.any(gamma >= size):
        raise ValueError("interface row lies outside the matrix")
    if len(set(map(int, gamma))) != gamma.size:
        raise ValueError("interface rows must be unique")
    retained = np.asarray(
        [row for row in range(size) if row not in set(map(int, gamma))],
        dtype=np.int64,
    )
    a_rr = array[np.ix_(retained, retained)]
    rhs = -array[np.ix_(retained, gamma)] @ values
    factor = None
    factor_released = True
    try:
        if factor_factory is None:
            lu, pivots = lu_factor(a_rr, check_finite=True)
            retained_values = lu_solve(
                (lu, pivots),
                rhs,
                check_finite=True,
            )
        else:
            factor = factor_factory(np.array(a_rr, copy=True))
            solve = getattr(factor, "solve", None)
            destroy = getattr(factor, "destroy", None)
            if not callable(solve) or not callable(destroy):
                raise TypeError("offline factor must provide solve(rhs) and destroy()")
            retained_values = solve(rhs)
            factor_released = False
        retained_values = _as_complex_array(retained_values, ndim=1)
        if retained_values.shape != retained.shape:
            raise ValueError("offline factor returned the wrong retained size")
    finally:
        if factor is not None:
            factor.destroy()
            factor_released = True
    full = np.zeros(size, dtype=np.complex128)
    full[gamma] = values
    full[retained] = retained_values
    residual = array[np.ix_(retained, np.arange(size))] @ full
    scale = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
    return PrescribedInterfaceSolution(
        values=full,
        retained_rows=tuple(map(int, retained)),
        interface_rows=tuple(map(int, gamma)),
        retained_residual_norm=float(np.linalg.norm(residual)),
        retained_residual_relative=float(np.linalg.norm(residual) / scale),
        factor_released=factor_released,
    )


def build_middle_modal_active_column(
    condensed: Any,
    function_space: Any,
    floquet_data: Any,
    evaluator: Any,
    propagation: Any,
    *,
    mode_index: int,
    direction: str,
    bottom_z_nm: float,
    top_z_nm: float,
    research_opt_in: bool = False,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Lift one frozen modal field through the middle Full3D cells only.

    ``evaluator`` is the existing distributed 2D evaluator and is called
    collectively before the local DOLFINx interpolation callback.  The field
    is multiplied with the selected ``TwoSidedPropagation`` effective beta;
    no raw modal beta or load-condensation operation enters this path.  The
    returned active vector is explicitly a middle-only component: endcap
    homogeneous extension is intentionally not performed here.
    """

    _require_research_opt_in(research_opt_in)
    direction = str(direction)
    if direction not in {"forward", "backward"}:
        raise ValueError("direction must be 'forward' or 'backward'")
    bottom_z_nm = float(bottom_z_nm)
    top_z_nm = float(top_z_nm)
    if not np.all(np.isfinite((bottom_z_nm, top_z_nm))):
        raise ValueError("middle-column z coordinates must be finite")
    if not bottom_z_nm < top_z_nm:
        raise ValueError("bottom_z_nm must be smaller than top_z_nm")
    length_nm = top_z_nm - bottom_z_nm
    propagation_length = float(propagation.length_nm)
    if not np.isclose(propagation_length, length_nm, rtol=1.0e-12, atol=1.0e-12):
        raise ValueError("TwoSidedPropagation length differs from the target slab")
    mode_index = int(mode_index)
    block = getattr(propagation, direction)
    effective_betas = np.asarray(block.effective_beta_per_nm, dtype=np.complex128)
    if mode_index < 0 or mode_index >= len(effective_betas):
        raise IndexError("mode_index lies outside the propagation block")
    effective_beta = complex(effective_betas[mode_index])

    mesh = function_space.mesh
    tdim = mesh.topology.dim
    owned_cells = int(mesh.topology.index_map(tdim).size_local)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    coordinates = np.asarray(mesh.geometry.x)
    middle_cells = []
    for cell in range(owned_cells):
        z_values = coordinates[geometry_dofmap[cell], 2]
        if (
            float(np.min(z_values)) >= bottom_z_nm - 1.0e-12
            and float(np.max(z_values)) <= top_z_nm + 1.0e-12
        ):
            middle_cells.append(cell)
    cells = np.asarray(middle_cells, dtype=np.int32)
    interpolation_points = np.asarray(
        cpp.fem.interpolation_coords(
            function_space.element._cpp_object,
            mesh.geometry._cpp_object,
            cells,
        ),
        dtype=np.float64,
    )
    values = np.asarray(evaluator.evaluate_points(interpolation_points))
    if values.ndim != 2:
        raise ValueError("distributed modal evaluator returned non-matrix values")
    if interpolation_points.shape[0] == 3:
        points = np.asarray(interpolation_points.T, dtype=np.float64)
    elif interpolation_points.shape[1] == 3:
        points = np.asarray(interpolation_points, dtype=np.float64)
    else:
        raise ValueError("middle interpolation coordinates need three columns")
    point_count = len(points)
    if values.shape[-1] != point_count:
        raise ValueError("distributed modal values do not match interpolation points")
    reference_z = bottom_z_nm if direction == "forward" else top_z_nm
    point_factors = np.exp(1j * effective_beta * (points[:, 2] - reference_z))
    if not np.all(np.isfinite(point_factors)):
        raise FloatingPointError("middle modal propagation factors are non-finite")
    scaled_values = np.asarray(
        values * point_factors[np.newaxis, :], dtype=PETSc.ScalarType
    )
    target = fem.Function(function_space)
    target.x.array[:] = PETSc.ScalarType(0.0)

    def cached_values(x: np.ndarray) -> np.ndarray:
        coordinates_arg = np.asarray(x, dtype=np.float64)
        if coordinates_arg.shape != interpolation_points.shape or not np.allclose(
            coordinates_arg,
            interpolation_points,
            rtol=0.0,
            atol=1.0e-13,
        ):
            raise RuntimeError(
                "DOLFINx middle interpolation points changed after collective evaluation"
            )
        return scaled_values

    target.interpolate(cached_values, cells)
    target.x.scatter_forward()
    if floquet_data is not None:
        mpc = getattr(floquet_data, "mpc", None)
        if mpc is None or not callable(getattr(mpc, "homogenize", None)):
            raise TypeError("floquet_data must provide an MPC homogenize method")
        mpc.homogenize(target)
        target.x.scatter_forward()

    active = condensed.create_active_vector()
    active.set(PETSc.ScalarType(0.0))
    full_vector = target.x.petsc_vec
    first, last = map(int, full_vector.getOwnershipRange())
    local_values = np.asarray(full_vector.getArray(readonly=True))
    owned_originals = np.asarray(
        condensed.trace_constraints.owned_active_original_dofs, dtype=np.int64
    )
    missing_ownership = [
        int(original)
        for original in owned_originals
        if not first <= int(original) < last
    ]
    if missing_ownership:
        active.destroy()
        raise RuntimeError(
            "owned active original rows are outside the full-vector ownership "
            f"range: {missing_ownership[:8]}"
        )
    written = 0
    for original in owned_originals:
        original = int(original)
        active_id = condensed.trace_constraints.original_to_active.get(original)
        if active_id is None:
            raise RuntimeError("owned active original row has no active mapping")
        active.setValue(
            int(active_id), PETSc.ScalarType(local_values[original - first])
        )
        written += 1
    if written != len(owned_originals):
        active.destroy()
        raise RuntimeError("middle column did not write every owned active row")
    active.assemble()
    comm = mesh.comm
    nonzero_owned = int(np.count_nonzero(np.abs(active.getArray(readonly=True)) > 0.0))
    return active, {
        "research_only": True,
        "middle_only_component": True,
        "endcap_extension_performed": False,
        "load_condensation_used": False,
        "direction": direction,
        "mode_index": mode_index,
        "bottom_z_nm": bottom_z_nm,
        "top_z_nm": top_z_nm,
        "effective_beta_per_nm": [effective_beta.real, effective_beta.imag],
        "interpolation_point_count": int(point_count),
        "interpolation_z_min_nm": float(np.min(points[:, 2], initial=bottom_z_nm)),
        "interpolation_z_max_nm": float(np.max(points[:, 2], initial=top_z_nm)),
        "propagation_factor_at_bottom": [
            complex(np.exp(1j * effective_beta * (bottom_z_nm - reference_z))).real,
            complex(np.exp(1j * effective_beta * (bottom_z_nm - reference_z))).imag,
        ],
        "propagation_factor_at_top": [
            complex(np.exp(1j * effective_beta * (top_z_nm - reference_z))).real,
            complex(np.exp(1j * effective_beta * (top_z_nm - reference_z))).imag,
        ],
        "propagation_model": str(propagation.propagation_model),
        "owned_middle_cell_count": int(len(cells)),
        "global_middle_cell_count": int(comm.allreduce(len(cells), op=MPI.SUM)),
        "owned_active_rows_written": int(written),
        "owned_active_rows_expected": int(len(owned_originals)),
        "global_nonzero_active_rows": int(comm.allreduce(nonzero_owned, op=MPI.SUM)),
    }
