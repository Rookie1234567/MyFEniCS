"""Research-only sparse endpoint trace mass and Riesz actions.

The inverse metric is exposed only as a reusable sparse solve; no explicit
inverse or dense endpoint metric is formed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import ufl
from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from petsc4py import PETSc

from ..constraints.cross_section_floquet import reduce_matrix_hermitian
from .hcurl_assembly_time_condensation import TraceConstraintMap


RESEARCH_STATUS = "research_only_endpoint_metric"


@dataclass(frozen=True)
class EndpointTraceMassSelection:
    """Research-only endpoint row selection and exterior facet tag."""

    tag: int
    original_rows: np.ndarray
    active_rows: np.ndarray


@dataclass
class EndpointTraceMassAction:
    """Research-only sparse endpoint mass with an implicit Riesz inverse."""

    matrix: PETSc.Mat
    solver: PETSc.KSP
    active_rows: np.ndarray
    hermitian_relative_defect: float
    constraint_action_relative_error: float
    solve_relative_residual: float
    _destroyed: bool = False

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.matrix.getSize())

    def solve_columns(self, values: np.ndarray) -> np.ndarray:
        """Apply the sparse Riesz inverse to a small column block."""

        columns = np.asarray(values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != self.shape[0]:
            raise ValueError(
                f"Endpoint Riesz columns must have shape ({self.shape[0]}, n)."
            )
        if self._destroyed:
            raise RuntimeError("The endpoint trace mass action has been destroyed.")
        rhs = self.matrix.createVecLeft()
        solution = self.matrix.createVecRight()
        result = np.empty_like(columns)
        try:
            first, last = map(int, rhs.getOwnershipRange())
            all_rows = np.arange(self.shape[0], dtype=PETSc.IntType)
            for column in range(columns.shape[1]):
                rhs.getArray()[:] = np.asarray(
                    columns[first:last, column], dtype=PETSc.ScalarType
                )
                rhs.assemble()
                self.solver.solve(rhs, solution)
                if int(self.solver.getConvergedReason()) < 0:
                    raise RuntimeError("Endpoint Riesz solve did not converge.")
                result[:, column] = np.asarray(
                    solution.getValues(all_rows), dtype=np.complex128
                )
        finally:
            solution.destroy()
            rhs.destroy()
        return result

    def multiply_columns(self, values: np.ndarray) -> np.ndarray:
        """Apply the sparse endpoint mass to a small column block."""

        columns = np.asarray(values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != self.shape[1]:
            raise ValueError(
                f"Endpoint mass columns must have shape ({self.shape[1]}, n)."
            )
        if self._destroyed:
            raise RuntimeError("The endpoint trace mass action has been destroyed.")
        source = self.matrix.createVecRight()
        target = self.matrix.createVecLeft()
        result = np.empty_like(columns)
        try:
            first, last = map(int, source.getOwnershipRange())
            all_rows = np.arange(self.shape[0], dtype=PETSc.IntType)
            for column in range(columns.shape[1]):
                source.getArray()[:] = np.asarray(
                    columns[first:last, column], dtype=PETSc.ScalarType
                )
                source.assemble()
                self.matrix.mult(source, target)
                result[:, column] = np.asarray(
                    target.getValues(all_rows), dtype=np.complex128
                )
        finally:
            target.destroy()
            source.destroy()
        return result

    def dual_gram(self, columns: np.ndarray) -> np.ndarray:
        """Return the small Gram matrix under the implicit dual metric."""

        columns = np.asarray(columns, dtype=np.complex128)
        return columns.conj().T @ self.solve_columns(columns)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.solver.destroy()
        self.matrix.destroy()
        self._destroyed = True


def _endpoint_constraint_matrix(
    selection: EndpointTraceMassSelection,
    constraints: TraceConstraintMap,
    comm: Any,
) -> PETSc.Mat:
    active_local = {
        int(active): index for index, active in enumerate(selection.active_rows)
    }
    expansions = [
        constraints.expansion_by_original[int(original)]
        for original in selection.original_rows
    ]
    transform = PETSc.Mat().createAIJ(
        size=(len(selection.original_rows), len(selection.active_rows)),
        nnz=max(len(active) for active, _coefficients in expansions),
        comm=comm,
    )
    for row, (active, coefficients) in enumerate(expansions):
        transform.setValues(
            np.asarray([row], dtype=PETSc.IntType),
            np.asarray(
                [active_local[int(value)] for value in active],
                dtype=PETSc.IntType,
            ),
            np.asarray(coefficients, dtype=PETSc.ScalarType)[None, :],
        )
    transform.assemble()
    return transform


def _build_one_action(
    full: PETSc.Mat,
    selection: EndpointTraceMassSelection,
    constraints: TraceConstraintMap,
    probe_offset: int,
    factor_solver_type: str | None,
) -> EndpointTraceMassAction:
    endpoint_is = PETSc.IS().createGeneral(
        np.asarray(selection.original_rows, dtype=PETSc.IntType),
        comm=full.getComm(),
    )
    face_mass = full.createSubMatrix(endpoint_is, endpoint_is)
    transform = _endpoint_constraint_matrix(selection, constraints, full.getComm())
    reduced = reduce_matrix_hermitian(face_mass, transform)
    hermitian = PETSc.Mat()
    reduced.hermitianTranspose(hermitian)
    difference = reduced.copy()
    difference.axpy(
        PETSc.ScalarType(-1.0),
        hermitian,
        structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
    )
    probe = reduced.createVecRight()
    indices = np.arange(len(selection.active_rows), dtype=np.float64)
    probe.getArray()[:] = (indices + 1.0) + 1.0j * (indices + probe_offset)
    probe.assemble()
    direct = reduced.createVecLeft()
    expanded = transform.createVecLeft()
    face_action = face_mass.createVecLeft()
    chained = transform.createVecRight()
    action_error = reduced.createVecLeft()
    reduced.mult(probe, direct)
    transform.mult(probe, expanded)
    face_mass.mult(expanded, face_action)
    transform.multHermitian(face_action, chained)
    direct.copy(action_error)
    action_error.axpy(PETSc.ScalarType(-1.0), chained)
    solver = PETSc.KSP().create(reduced.getComm())
    solution = reduced.createVecRight()
    residual = reduced.createVecLeft()
    try:
        if any(
            "aij" not in matrix.getType().lower()
            for matrix in (face_mass, transform, reduced)
        ):
            raise AssertionError(
                "Endpoint mass qualification requires sparse AIJ matrices."
            )
        expected_original = len(selection.original_rows)
        expected_active = len(selection.active_rows)
        if face_mass.getSize() != (
            expected_original,
            expected_original,
        ):
            raise AssertionError("Endpoint full mass shape is inconsistent.")
        if transform.getSize() != (expected_original, expected_active):
            raise AssertionError("Endpoint constraint shape is inconsistent.")
        if reduced.getSize() != (expected_active, expected_active):
            raise AssertionError("Endpoint reduced mass shape is inconsistent.")
        hermitian_defect = float(difference.norm() / max(reduced.norm(), 1.0e-30))
        constraint_error = float(action_error.norm() / max(direct.norm(), 1.0e-30))
        if hermitian_defect > 1.0e-12 or constraint_error > 1.0e-12:
            raise AssertionError("Endpoint mass qualification action failed.")
        reduced.setOption(PETSc.Mat.Option.HERMITIAN, True)
        solver.setType(PETSc.KSP.Type.PREONLY)
        pc = solver.getPC()
        pc.setType(PETSc.PC.Type.CHOLESKY)
        if factor_solver_type is not None:
            pc.setFactorSolverType(factor_solver_type)
        solver.setOperators(reduced)
        solver.setErrorIfNotConverged(True)
        solver.setUp()
        solver.solve(direct, solution)
        if int(solver.getConvergedReason()) < 0:
            raise RuntimeError("Endpoint mass qualification solve did not converge.")
        reduced.mult(solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), direct)
        solve_residual = float(residual.norm() / max(direct.norm(), 1.0e-30))
        if solve_residual > 1.0e-11:
            raise AssertionError("Endpoint mass solve residual exceeds 1e-11.")
        return EndpointTraceMassAction(
            matrix=reduced,
            solver=solver,
            active_rows=np.asarray(selection.active_rows, dtype=np.int64).copy(),
            hermitian_relative_defect=hermitian_defect,
            constraint_action_relative_error=constraint_error,
            solve_relative_residual=solve_residual,
        )
    except Exception:
        solver.destroy()
        reduced.destroy()
        raise
    finally:
        residual.destroy()
        solution.destroy()
        action_error.destroy()
        chained.destroy()
        face_action.destroy()
        expanded.destroy()
        direct.destroy()
        probe.destroy()
        difference.destroy()
        hermitian.destroy()
        transform.destroy()
        face_mass.destroy()
        endpoint_is.destroy()


def build_endpoint_trace_mass_actions(
    V: Any,
    mesh_data: Any,
    constraints: TraceConstraintMap,
    selections: tuple[
        EndpointTraceMassSelection,
        EndpointTraceMassSelection,
    ],
    *,
    quadrature_degree: int = 14,
    factor_solver_type: str | None = None,
) -> tuple[EndpointTraceMassAction, EndpointTraceMassAction]:
    """Assemble two sparse research-only endpoint metric actions."""

    if V.mesh.comm.size != 1:
        raise RuntimeError("Endpoint trace mass qualification is serial-only.")
    trial = ufl.TrialFunction(V)
    test = ufl.TestFunction(V)
    normal = ufl.FacetNormal(mesh_data.mesh)
    ds = ufl.Measure(
        "ds",
        domain=mesh_data.mesh,
        subdomain_data=mesh_data.facet_tags,
        metadata={"quadrature_degree": int(quadrature_degree)},
    )
    integrand = ufl.inner(ufl.cross(normal, trial), ufl.cross(normal, test))
    full = fem_petsc.assemble_matrix(
        fem.form(integrand * (ds(selections[0].tag) + ds(selections[1].tag))),
        bcs=[],
    )
    full.assemble()
    actions: list[EndpointTraceMassAction] = []
    try:
        for offset, selection in enumerate(selections, start=1):
            actions.append(
                _build_one_action(
                    full,
                    selection,
                    constraints,
                    offset,
                    factor_solver_type,
                )
            )
        return actions[0], actions[1]
    except Exception:
        for action in actions:
            action.destroy()
        raise
    finally:
        full.destroy()
