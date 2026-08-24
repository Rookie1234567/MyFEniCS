"""Global owner-packet LOR edge transfer for the S4-A2a audit.

This module contains only the distributed implicit prolongation and its
Hermitian adjoint.  It deliberately does not build a global prolongation
matrix, a node matrix, HX, PCGAMG, or a Krylov runner.  The fine canonical
topology is the parent-cell p-refined topology already retained by the
``build_hx=False`` L2 fixture; a separate raw p1 topology is used only to
bridge those owner packets to ``fixture.lor_edge_space``.

Coarse-axis endpoints are checked against the resolved configuration, and the
raw-map active-owner closure is distributed with metadata-only uint32 routing;
no local raw-owner/canonical-owner layout identity is assumed.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .fullspace_lor_edge_geometric_mg import build_local_lor_edge_geometric_transfer
from .fullspace_lor_edge_geometric_mg import (
    CHEBYSHEV_DEGREE,
    LAMBDA_HI_FACTOR,
    LAMBDA_LO_FACTOR,
    POWER_STEPS,
)
from .fullspace_lor_hx_root_cause import (
    DiagnosticDirectSolver,
    lift_low_primal,
    low_input_from_high_dual,
)
from .fullspace_lor_memory_first_foundation import (
    _canonical_raw_map,
    _fill_raw_vector,
    _route_low_to_owner,
)
from .fullspace_lor_native_hx_fixture import (
    _P1IdentityTransfer,
    _assemble_sparse,
    _edge_records,
    _p1_transfer_local_indices,
    RealL2PositiveHXFixture,
)
from .fullspace_lor_topology import (
    _alltoallv,
    _group_by_owner,
    build_canonical_lor_subedge_topology,
)


A2_SCHEMA = "task038.lor-edge-geometric-mg.global-implicit.v1"
A2_CELL_BATCH = 32


class FixedChebyshevJacobiPETSc:
    """Fixed Jacobi-scaled degree-three Chebyshev action on a PETSc matrix."""

    def __init__(self, matrix: PETSc.Mat) -> None:
        rows, columns = matrix.getSize()
        if rows != columns or rows <= 0:
            raise ValueError("Chebyshev matrix must be nonempty and square")
        self.matrix = matrix
        self._destroyed = False
        diagonal = matrix.createVecRight()
        matrix.getDiagonal(diagonal)
        values = np.asarray(diagonal.array, dtype=np.complex128)
        if (
            not np.all(np.isfinite(values))
            or np.any(np.abs(values.imag) > 1.0e-12)
            or np.any(values.real <= 0.0)
        ):
            diagonal.destroy()
            raise ValueError("Chebyshev Jacobi diagonal must be positive")
        self._inv_sqrt = matrix.createVecRight()
        self._inv_sqrt.array[:] = 1.0 / np.sqrt(values.real)
        diagonal.destroy()

        self._scaled_input = matrix.createVecRight()
        self._scaled_action = matrix.createVecLeft()
        power_vector = matrix.createVecRight()
        power_action = matrix.createVecLeft()
        self.matrix_mult_count = 0
        self.power_matrix_mult_count = 0
        try:
            start, stop = power_vector.getOwnershipRange()
            global_rows = int(rows)
            indices = np.arange(start + 1, stop + 1, dtype=np.float64)
            reverse = np.arange(
                global_rows - start, global_rows - stop, -1.0, dtype=np.float64
            )
            power_vector.array[:] = indices + 1j * reverse
            norm = float(power_vector.norm())
            if not np.isfinite(norm) or norm == 0.0:
                raise FloatingPointError("Chebyshev power vector is invalid")
            power_vector.scale(1.0 / norm)
            history: list[float] = []
            for _ in range(POWER_STEPS):
                self._apply_scaled_into(power_vector, power_action)
                norm = float(power_action.norm())
                if not np.isfinite(norm) or norm == 0.0:
                    raise FloatingPointError("Chebyshev power estimate is invalid")
                power_action.copy(power_vector)
                power_vector.scale(1.0 / norm)
                self._apply_scaled_into(power_vector, power_action)
                rayleigh = power_vector.dot(power_action)
                value = float(np.real(rayleigh))
                if (
                    not np.isfinite(value)
                    or value <= 0.0
                    or abs(float(np.imag(rayleigh))) > 1.0e-10 * max(value, 1.0)
                ):
                    raise FloatingPointError("Chebyshev power estimate is invalid")
                history.append(value)
            self.power_history = tuple(history)
        finally:
            power_vector.destroy()
            power_action.destroy()

        self.power_matrix_mult_count = int(self.matrix_mult_count)
        self.lambda_power10 = float(self.power_history[-1])
        self.lambda_hi = LAMBDA_HI_FACTOR * self.lambda_power10
        self.lambda_lo = LAMBDA_LO_FACTOR * self.lambda_hi
        if not np.isfinite(self.lambda_hi) or not 0.0 < self.lambda_lo < self.lambda_hi:
            self.destroy()
            raise FloatingPointError("Chebyshev spectral window is invalid")
        self._rhs_scaled = matrix.createVecRight()
        self._residual = matrix.createVecLeft()
        self._direction = matrix.createVecRight()
        self._solution = matrix.createVecRight()
        self._action = matrix.createVecLeft()
        self.apply_count = 0
        self.last_apply_facts: dict[str, object] = {}
        self._destroyed = False

    def _apply_scaled_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._scaled_input.pointwiseMult(self._inv_sqrt, source)
        self.matrix.mult(self._scaled_input, self._scaled_action)
        target.pointwiseMult(self._inv_sqrt, self._scaled_action)
        self.matrix_mult_count += 1

    def apply_into(self, rhs: PETSc.Vec, target: PETSc.Vec) -> dict[str, object]:
        if self._destroyed:
            raise RuntimeError("PETSc Chebyshev smoother has been destroyed")
        if rhs.getSize() != self.matrix.getSize()[0] or target.getSize() != self.matrix.getSize()[0]:
            raise ValueError("Chebyshev Vec size does not match matrix")
        before = self.matrix_mult_count
        self._rhs_scaled.pointwiseMult(self._inv_sqrt, rhs)
        center = 0.5 * (self.lambda_hi + self.lambda_lo)
        half_width = 0.5 * (self.lambda_hi - self.lambda_lo)
        sigma = center / half_width
        rho = 1.0 / sigma
        self._rhs_scaled.copy(self._direction)
        self._direction.scale(1.0 / center)
        self._direction.copy(self._solution)
        for _ in range(1, CHEBYSHEV_DEGREE):
            self._apply_scaled_into(self._solution, self._action)
            self._rhs_scaled.copy(self._residual)
            self._residual.axpy(-1.0, self._action)
            rho_new = 1.0 / (2.0 * sigma - rho)
            self._direction.scale(rho_new * rho)
            self._direction.axpy(2.0 * rho_new / half_width, self._residual)
            self._solution.axpy(1.0, self._direction)
            rho = rho_new
        target.pointwiseMult(self._inv_sqrt, self._solution)
        self.apply_count += 1
        facts = {
            "matrix_mult_count": int(self.matrix_mult_count - before),
            "apply_count": int(self.apply_count),
        }
        self.last_apply_facts = facts
        return facts

    def apply(self, rhs: PETSc.Vec) -> PETSc.Vec:
        target = self.matrix.createVecRight()
        try:
            self.apply_into(rhs, target)
        except Exception:
            target.destroy()
            raise
        return target

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        for name in (
            "_inv_sqrt",
            "_scaled_input",
            "_scaled_action",
            "_rhs_scaled",
            "_residual",
            "_direction",
            "_solution",
            "_action",
        ):
            vector = getattr(self, name, None)
            if vector is not None:
                vector.destroy()
                setattr(self, name, None)


class FixedOneVCycle:
    """One frozen fine Chebyshev/coarse-direct/fine Chebyshev cycle."""

    def __init__(self, case: "ImplicitLORTransferCase") -> None:
        if int(case.degree) not in (2, 3):
            raise ValueError("fixed one-V-cycle coarse direct solve supports p2/p3 only")
        self.case = case
        self.fine_matrix = case.fixture.edge_matrix
        self.coarse_matrix = case.coarse_matrix
        self.smoother = FixedChebyshevJacobiPETSc(self.fine_matrix)
        self.coarse_solver = DiagnosticDirectSolver(
            self.coarse_matrix, label=f"p{case.degree}-coarse-vcycle"
        )
        self._z_pre = self.fine_matrix.createVecRight()
        self._fine_action = self.fine_matrix.createVecLeft()
        self._fine_residual = self.fine_matrix.createVecLeft()
        self._z = self.fine_matrix.createVecRight()
        self._post_action = self.fine_matrix.createVecLeft()
        self._post_residual = self.fine_matrix.createVecLeft()
        self._post_correction = self.fine_matrix.createVecRight()
        self.apply_count = 0
        self.last_apply_facts: dict[str, object] = {}
        self._destroyed = False

    def apply_into(self, rhs: PETSc.Vec, target: PETSc.Vec) -> dict[str, object]:
        if self._destroyed:
            raise RuntimeError("one-V-cycle has been destroyed")
        before_matrix = self.smoother.matrix_mult_count
        self.smoother.apply_into(rhs, self._z_pre)
        self.fine_matrix.mult(self._z_pre, self._fine_action)
        rhs.copy(self._fine_residual)
        self._fine_residual.axpy(-1.0, self._fine_action)
        coarse_rhs = self.case.apply_adjoint(self._fine_residual)
        coarse_solution = None
        fine_correction = None
        try:
            coarse_solution, coarse_facts = self.coarse_solver.solve_lean(coarse_rhs)
            fine_correction = self.case.apply_primal(coarse_solution)
            self._z_pre.copy(self._z)
            self._z.axpy(1.0, fine_correction)
        finally:
            if fine_correction is not None:
                fine_correction.destroy()
            if coarse_solution is not None:
                coarse_solution.destroy()
            coarse_rhs.destroy()
        self.fine_matrix.mult(self._z, self._post_action)
        rhs.copy(self._post_residual)
        self._post_residual.axpy(-1.0, self._post_action)
        self.smoother.apply_into(self._post_residual, self._post_correction)
        self._z.copy(target)
        target.axpy(1.0, self._post_correction)
        self.apply_count += 1
        facts = {
            "fine_smoother_matrix_mult_count": int(self.smoother.matrix_mult_count - before_matrix),
            "fine_matrix_mult_count": 2,
            "transfer_primal_count": 1,
            "transfer_adjoint_count": 1,
            "coarse_factor_solve_count": int(self.coarse_solver.solve_count),
            "coarse_solver_backend": coarse_facts["backend"],
            "coarse_finite": coarse_facts["finite"],
        }
        self.last_apply_facts = facts
        return facts

    def apply(self, rhs: PETSc.Vec) -> PETSc.Vec:
        target = self.fine_matrix.createVecRight()
        try:
            self.apply_into(rhs, target)
        except Exception:
            target.destroy()
            raise
        return target

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        # The MUMPS factor is released before the case-owned matrices.
        self.coarse_solver.destroy()
        for vector in (
            self._z_pre,
            self._fine_action,
            self._fine_residual,
            self._z,
            self._post_action,
            self._post_residual,
            self._post_correction,
        ):
            vector.destroy()
        self.smoother.destroy()


class HighLORGeometricVcyclePC:
    """Adapt one frozen LOR V-cycle to the high-space dual/primal interface.

    The transfer case owns the single ``build_hx=False`` fixture.  This adapter
    owns the V-cycle and releases it before releasing that transfer case.  The
    returned high-space vector is newly allocated; no borrowed action output is
    retained or destroyed here.
    """

    def __init__(self, transfer_case: "ImplicitLORTransferCase") -> None:
        if transfer_case._destroyed:
            raise RuntimeError("cannot attach a PC to a destroyed transfer case")
        self.transfer_case = transfer_case
        self.vcycle = FixedOneVCycle(transfer_case)
        self.apply_count = 0
        self._destroyed = False

    def apply(self, high_residual: PETSc.Vec) -> PETSc.Vec:
        if self._destroyed:
            raise RuntimeError("high LOR V-cycle PC has been destroyed")
        low_rhs, _owner_packet = low_input_from_high_dual(
            self.transfer_case.fixture, high_residual
        )
        low_solution = None
        try:
            low_solution = self.vcycle.apply(low_rhs)
            high_solution = lift_low_primal(
                self.transfer_case.fixture, low_solution
            )
        finally:
            if low_solution is not None:
                low_solution.destroy()
            low_rhs.destroy()
        self.apply_count += 1
        return high_solution

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self.vcycle.destroy()
        self.transfer_case.destroy()
        self.vcycle = None
        self.transfer_case = None


def _owner_incidence_counts(topology: Any) -> tuple[np.ndarray, np.ndarray]:
    """Count parent-cell incidence using packed IDs, not phase-weighted values."""

    def chunks():
        for start in range(0, topology.cell_edge_ids.shape[0], A2_CELL_BATCH):
            stop = min(start + A2_CELL_BATCH, topology.cell_edge_ids.shape[0])
            orientation = np.asarray(
                topology.cell_orientation[start:stop], dtype=np.complex128
            )
            phase = topology.phase_values[topology.cell_phase_codes[start:stop]]
            # route_owner_cell_chunks_additive applies orientation / phase.
            # Multiplying by orientation * phase makes every canonical
            # contribution exactly one, including periodic edges.
            yield start, orientation * phase

    owner_ids, owner_counts = topology.route_owner_cell_chunks_additive(chunks())
    owner_counts = np.asarray(owner_counts, dtype=np.complex128)
    if np.any(np.abs(owner_counts.imag) > 1.0e-12):
        raise RuntimeError("packed owner incidence counts are not real")
    counts = np.rint(owner_counts.real).astype(np.int64)
    if np.any(counts <= 0) or np.any(np.abs(owner_counts.real - counts) > 1.0e-12):
        raise RuntimeError("packed owner incidence counts are not positive integers")
    return np.asarray(owner_ids, dtype=np.uint32), counts


def _raw_dual_owner_packet(
    space: Any,
    floquet: Any,
    topology: Any,
    source: PETSc.Vec,
    local_permutations: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert a raw p1 dual Vec to canonical owners with additive routing."""

    from dolfinx import fem

    work_space = floquet.mpc.function_space
    field = fem.Function(work_space)
    multiplicity = fem.Function(work_space)
    source.copy(field.x.petsc_vec)
    field.x.scatter_forward()
    floquet.mpc.homogenize(field)
    field.x.scatter_forward()
    multiplicity.x.array[:] = 0.0
    cell_count = int(space.mesh.topology.index_map(3).size_local)
    cell_info = np.asarray(
        space.mesh.topology.get_cell_permutation_info(), dtype=np.uint32
    )
    for cell in range(cell_count):
        local_dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
        multiplicity.x.array[local_dofs] += 1.0
    multiplicity.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
    )
    multiplicity.x.scatter_forward()

    def chunks():
        for start in range(0, cell_count, A2_CELL_BATCH):
            stop = min(start + A2_CELL_BATCH, cell_count)
            batch: list[np.ndarray] = []
            for cell in range(start, stop):
                local_dofs = np.asarray(
                    work_space.dofmap.cell_dofs(cell), dtype=np.int32
                )
                values = np.asarray(
                    field.x.array[local_dofs], dtype=np.complex128
                ).copy()
                local_multiplicity = np.asarray(
                    multiplicity.x.array[local_dofs].real, dtype=np.float64
                )
                if np.any(local_multiplicity <= 0.0):
                    raise RuntimeError("raw dual incidence multiplicity is incomplete")
                values /= local_multiplicity
                work_space.element.Tt_apply(
                    values, np.asarray([cell_info[cell]], dtype=np.uint32), 1
                )
                batch.append(values[np.asarray(local_permutations[cell])])
            yield start, np.asarray(batch, dtype=np.complex128)

    try:
        return topology.route_owner_cell_chunks_additive(chunks())
    finally:
        del multiplicity, field


class ImplicitLORTransferCase:
    """One p2/p3 implicit owner-packet transfer case."""

    def __init__(self, fixture: RealL2PositiveHXFixture) -> None:
        if fixture.build_hx:
            raise ValueError("A2 requires the fixture build_hx=False path")
        self.fixture = fixture
        self.degree = int(fixture.degree)
        self.local_transfer = build_local_lor_edge_geometric_transfer(self.degree)
        basix_to_lor = self.local_transfer.coarse_basix_to_lor_order
        self.q_custom = np.asarray(
            self.local_transfer.edge_transfer[:, np.argsort(basix_to_lor)],
            dtype=np.complex128,
        )

        from basix.ufl import element
        from dolfinx import default_real_type, fem
        from src.constraints.floquet_3d import build_double_floquet_mpc
        from src.geometry.mesh_builder_3d import _mark_boundary_facets
        import ufl

        coarse_cfg = replace(
            fixture.cfg,
            nedelec_degree=1,
            nedelec_trace_degree=None,
            nedelec_interior_degree=None,
            visualization_degree=1,
        )
        facets, _ = _mark_boundary_facets(fixture.high_mesh, coarse_cfg)
        coarse_data = SimpleNamespace(
            mesh=fixture.high_mesh,
            cell_tags=fixture.high_cell_tags,
            facet_tags=facets,
        )
        self.coarse_space = fem.functionspace(
            fixture.high_mesh,
            element(
                "N1curl",
                fixture.high_mesh.basix_cell(),
                1,
                dtype=default_real_type,
            ),
        )
        self.coarse_floquet = build_double_floquet_mpc(
            self.coarse_space, coarse_data, coarse_cfg
        )
        coarse_u = ufl.TrialFunction(self.coarse_space)
        coarse_v = ufl.TestFunction(self.coarse_space)
        coarse_form = (
            fixture.high_mu_coefficient
            * ufl.inner(ufl.curl(coarse_u), ufl.curl(coarse_v))
            + fixture.high_mass_coefficient * ufl.inner(coarse_u, coarse_v)
        ) * ufl.dx
        self.coarse_matrix = _assemble_sparse(
            coarse_form, mpc=self.coarse_floquet.mpc
        )

        self.coarse_topology = build_canonical_lor_subedge_topology(
            self.coarse_space,
            self.coarse_floquet,
            _P1IdentityTransfer(),
        )
        self.coarse_local_permutations = np.asarray(
            [
                _p1_transfer_local_indices(self.coarse_space, cell)
                for cell in range(
                    int(fixture.high_mesh.topology.index_map(3).size_local)
                )
            ],
            dtype=np.int32,
        )
        coarse_node_space = fem.functionspace(
            fixture.high_mesh,
            element(
                "Lagrange",
                fixture.high_mesh.basix_cell(),
                1,
                dtype=default_real_type,
            ),
        )
        coarse_records, _ = _edge_records(
            self.coarse_space, coarse_node_space
        )
        coarse_axes = tuple(
            np.asarray(axis[:: self.degree], dtype=np.float64)
            for axis in fixture.refined_axes
        )
        for axis, values in enumerate(coarse_axes):
            if values.size < 2 or not np.all(np.diff(values) > 0.0):
                raise RuntimeError("coarse axes are not strictly increasing")
        expected_endpoints = (
            (float(fixture.cfg.x_min), float(fixture.cfg.x_max)),
            (float(fixture.cfg.y_min), float(fixture.cfg.y_max)),
            (float(fixture.cfg.domain_z_min), float(fixture.cfg.domain_z_max)),
        )
        for axis, (values, endpoints) in enumerate(
            zip(coarse_axes, expected_endpoints, strict=True)
        ):
            if not np.isclose(values[0], endpoints[0]):
                raise RuntimeError("coarse axis lower endpoint does not close")
            if not np.isclose(values[-1], endpoints[1]):
                raise RuntimeError("coarse axis upper endpoint does not close")
        self.coarse_raw_map = _canonical_raw_map(
            self.coarse_space,
            coarse_node_space,
            coarse_records,
            coarse_axes,
            owner_ids=self.coarse_topology.owned_edge_ids,
            local_permutations=self.coarse_local_permutations,
            validate_local_owner_layout=False,
        )
        self.coarse_raw_map_facts = self._distributed_raw_map_facts(
            self.coarse_raw_map, self.coarse_topology
        )
        del coarse_node_space

        self.fine_parent_topology = fixture.lor_topology
        self.fine_raw_topology = fixture.lor_raw_topology
        if not np.array_equal(
            self.fine_parent_topology.owned_edge_ids,
            self.fine_raw_topology.owned_edge_ids,
        ):
            raise RuntimeError("fine parent and raw owner inventories do not close")
        self.fine_raw_map = _canonical_raw_map(
            fixture.lor_edge_space,
            fixture.lor_node_space,
            fixture.lor_edge_records,
            fixture.refined_axes,
            owner_ids=self.fine_raw_topology.owned_edge_ids,
            local_permutations=fixture._lor_p1_transfer_local_indices,
            validate_local_owner_layout=False,
        )
        self.fine_raw_map_facts = self._distributed_raw_map_facts(
            self.fine_raw_map, self.fine_raw_topology
        )
        count_ids, count_values = _owner_incidence_counts(
            self.fine_parent_topology
        )
        self.fine_parent_multiplicity = self.fine_parent_topology.pull_owner_unique_values(
            count_ids, count_values.astype(np.complex128)
        ).real.astype(np.int64)
        self.audit = self._make_audit()
        self._destroyed = False

    @staticmethod
    def _raw_map_facts(
        raw_map: dict[str, np.ndarray],
        owner_ids: np.ndarray,
        *,
        validate_owner_layout: bool = True,
    ) -> dict[str, Any]:
        phase = np.asarray(raw_map["phase_codes"])
        canonical = np.asarray(raw_map["canonical_ids"])
        active = phase == 0
        active_ids = canonical[active]
        if np.unique(active_ids).size != active_ids.size:
            raise RuntimeError("active raw rows are not unique")
        if validate_owner_layout and not np.array_equal(
            np.sort(active_ids), np.sort(owner_ids)
        ):
            raise RuntimeError("active raw rows do not cover owner IDs")
        factors = np.asarray(raw_map["orientation_factors"])
        if not np.all(np.isin(factors, (-1, 1))):
            raise RuntimeError("raw edge orientation factors are not signs")
        facts = {
            "owned_raw_rows": int(canonical.size),
            "active_raw_rows": int(np.count_nonzero(active)),
            "phase_rows": int(np.count_nonzero(~active)),
            "active_raw_local_unique": True,
            "orientation_minus_count": int(np.count_nonzero(factors < 0)),
        }
        if validate_owner_layout:
            facts["active_owner_bijection"] = True
        return facts

    @classmethod
    def _distributed_raw_map_facts(
        cls, raw_map: dict[str, np.ndarray], topology: Any
    ) -> dict[str, Any]:
        """Close active raw rows against packed owners with metadata-only routing."""

        local = cls._raw_map_facts(
            raw_map, topology.owned_edge_ids, validate_owner_layout=False
        )
        comm = topology.comm
        active_ids = np.asarray(
            raw_map["canonical_ids"][np.asarray(raw_map["phase_codes"]) == 0],
            dtype=np.uint32,
        )
        _order, send_counts, _displacements, send_ids = _group_by_owner(
            active_ids, comm.size
        )
        received_ids, _receive_counts = _alltoallv(
            comm, send_ids, send_counts, MPI.UNSIGNED
        )
        received_ids = np.asarray(received_ids, dtype=np.uint32)
        if np.unique(received_ids).size != received_ids.size:
            raise RuntimeError("canonical owner received duplicate raw ids")
        received_sorted = np.sort(received_ids)
        expected_ids = np.asarray(topology.owned_edge_ids, dtype=np.uint32)
        if not np.array_equal(received_sorted, expected_ids):
            raise RuntimeError(
                "distributed raw/canonical owner inventories do not close"
            )
        factors = np.asarray(raw_map["orientation_factors"], dtype=np.int8)
        local.update(
            {
                "canonical_owner_closure": "exact_sorted_set_once",
                "active_owner_bijection": True,
                "canonical_owner_received_rows": int(received_ids.size),
                "global_owned_raw_rows": int(
                    comm.allreduce(local["owned_raw_rows"], op=MPI.SUM)
                ),
                "global_active_raw_rows": int(
                    comm.allreduce(local["active_raw_rows"], op=MPI.SUM)
                ),
                "global_phase_rows": int(
                    comm.allreduce(local["phase_rows"], op=MPI.SUM)
                ),
                "global_orientation_minus_count": int(
                    comm.allreduce(int(np.count_nonzero(factors < 0)), op=MPI.SUM)
                ),
                "global_orientation_plus_count": int(
                    comm.allreduce(int(np.count_nonzero(factors > 0)), op=MPI.SUM)
                ),
            }
        )
        return local

    def _make_audit(self) -> dict[str, Any]:
        mpi_size = int(self.fixture.comm.size)
        coarse_phase_values = [
            [float(value.real), float(value.imag)]
            for value in self.coarse_topology.phase_values
        ]
        fine_parent_phase_values = [
            [float(value.real), float(value.imag)]
            for value in self.fine_parent_topology.phase_values
        ]
        fine_raw_phase_values = [
            [float(value.real), float(value.imag)]
            for value in self.fine_raw_topology.phase_values
        ]
        return {
            "schema": A2_SCHEMA,
            "degree": self.degree,
            "mpi_size": mpi_size,
            "build_scope": f"p{self.degree}_h50_mpi{mpi_size}_transfer_core_only",
            "qualification": "focused_core_only_not_S4",
            "global_de_rham": "local_A1_only_not_global_MPI_qualified",
            "build_hx": False,
            "global_transfer_matrix": False,
            "global_high_order_aij": False,
            "scalar_node_matrix_built": False,
            "hx_hierarchy_built": False,
            "pcgamg_hierarchy_built": False,
            "numeric_allgather": False,
            "setup_closure_route": "typed_uint32_metadata_alltoallv",
            "apply_owner_route": "typed_complex128_alltoallv",
            "coarse_basix_to_lor_order": self.local_transfer.coarse_basix_to_lor_order.tolist(),
            "q_custom_shape": list(self.q_custom.shape),
            "coarse_space_global_rows": int(
                self.coarse_space.dofmap.index_map.size_global
            ),
            "fine_raw_space_global_rows": int(
                self.fixture.lor_edge_space.dofmap.index_map.size_global
            ),
            "coarse_raw_map": dict(self.coarse_raw_map_facts),
            "fine_raw_map": dict(self.fine_raw_map_facts),
            "fine_parent_owner_count": int(
                self.fine_parent_topology.owned_edge_ids.size
            ),
            "fine_parent_multiplicity_min": int(
                np.min(self.fine_parent_multiplicity)
            ),
            "fine_parent_multiplicity_max": int(
                np.max(self.fine_parent_multiplicity)
            ),
            "local_transfer_audit": dict(self.local_transfer.audit),
            "orientation_phase_contract": (
                "canonical route divides by phase; pull multiplies phase"
            ),
            "coarse_phase_values": coarse_phase_values,
            "fine_parent_phase_values": fine_parent_phase_values,
            "fine_raw_phase_values": fine_raw_phase_values,
        }

    def apply_primal(self, source: PETSc.Vec) -> PETSc.Vec:
        """Apply implicit P from coarse raw primal to fine raw primal."""

        if self._destroyed:
            raise RuntimeError("A2 transfer case has been destroyed")
        coarse_owner_ids, coarse_owner_values = _route_low_to_owner(
            self.coarse_space,
            self.coarse_floquet,
            self.coarse_topology,
            source,
            self.coarse_local_permutations,
        )
        coarse_unique = self.coarse_topology.pull_owner_unique_values(
            coarse_owner_ids, coarse_owner_values
        )

        def chunks():
            for start in range(
                0, self.coarse_topology.cell_edge_ids.shape[0], A2_CELL_BATCH
            ):
                stop = min(
                    start + A2_CELL_BATCH,
                    self.coarse_topology.cell_edge_ids.shape[0],
                )
                coarse_values = self.coarse_topology.cell_values_from_unique(
                    coarse_unique, start, stop
                )
                yield start, np.asarray(coarse_values @ self.q_custom.T)

        fine_owner_ids, fine_owner_values = (
            self.fine_parent_topology.route_owner_cell_chunks(chunks())
        )
        target = self.fixture.edge_matrix.createVecRight()
        fine_unique = self.fine_raw_topology.pull_owner_unique_values(
            fine_owner_ids, fine_owner_values
        )
        _fill_raw_vector(
            target,
            fine_unique,
            self.fine_raw_map,
            self.fine_raw_topology.unique_edge_ids,
        )
        return target

    def apply_adjoint(self, source: PETSc.Vec) -> PETSc.Vec:
        """Apply implicit P^H from fine raw dual to coarse raw dual."""

        if self._destroyed:
            raise RuntimeError("A2 transfer case has been destroyed")
        fine_owner_ids, fine_owner_values = _raw_dual_owner_packet(
            self.fixture.lor_edge_space,
            self.fixture.lor_edge_floquet,
            self.fine_raw_topology,
            source,
            self.fixture._lor_p1_transfer_local_indices,
        )
        fine_unique = self.fine_parent_topology.pull_owner_unique_values(
            fine_owner_ids, fine_owner_values
        )
        fine_ids = self.fine_parent_topology.unique_edge_ids
        fine_positions = np.searchsorted(fine_ids, self.fine_parent_topology.cell_edge_ids)
        if np.any(fine_positions >= fine_ids.size):
            raise RuntimeError("fine parent packed IDs are incomplete")
        parent_counts = self.fine_parent_multiplicity[fine_positions]
        if np.any(parent_counts <= 0):
            raise RuntimeError("fine parent multiplicity is not positive")

        def chunks():
            for start in range(
                0, self.fine_parent_topology.cell_edge_ids.shape[0], A2_CELL_BATCH
            ):
                stop = min(
                    start + A2_CELL_BATCH,
                    self.fine_parent_topology.cell_edge_ids.shape[0],
                )
                fine_values = self.fine_parent_topology.cell_values_from_unique(
                    fine_unique, start, stop
                )
                fine_values = fine_values / parent_counts[start:stop]
                coarse_values = fine_values @ self.q_custom.conj()
                yield start, np.asarray(coarse_values, dtype=np.complex128)

        coarse_owner_ids, coarse_owner_values = (
            self.coarse_topology.route_owner_cell_chunks_additive(chunks())
        )
        target = self.coarse_matrix.createVecRight()
        coarse_unique = self.coarse_topology.pull_owner_unique_values(
            coarse_owner_ids, coarse_owner_values
        )
        _fill_raw_vector(
            target,
            coarse_unique,
            self.coarse_raw_map,
            self.coarse_topology.unique_edge_ids,
        )
        return target

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self.coarse_matrix is not None:
            self.coarse_matrix.destroy()
        self.coarse_matrix = None
        self.coarse_floquet = None
        self.coarse_space = None
        self.coarse_topology = None
        self.fine_parent_topology = None
        self.fine_raw_topology = None
        self.fine_raw_map = None
        self.coarse_raw_map = None
        self.fixture.destroy()
        self.fixture = None


def build_implicit_lor_transfer_case(
    degree: int, comm: MPI.Comm = MPI.COMM_WORLD
) -> ImplicitLORTransferCase:
    """Build the p2/p3 global implicit bridge without HX construction."""

    degree = int(degree)
    if degree not in (2, 3):
        raise ValueError("A2a supports only p2 and p3")
    fixture = RealL2PositiveHXFixture(degree, comm, build_hx=False)
    try:
        return ImplicitLORTransferCase(fixture)
    except Exception:
        fixture.destroy()
        raise


__all__ = [
    "A2_CELL_BATCH",
    "A2_SCHEMA",
    "FixedChebyshevJacobiPETSc",
    "FixedOneVCycle",
    "HighLORGeometricVcyclePC",
    "ImplicitLORTransferCase",
    "build_implicit_lor_transfer_case",
]
