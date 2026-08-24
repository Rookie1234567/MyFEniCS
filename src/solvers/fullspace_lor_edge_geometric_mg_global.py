"""Global owner-packet LOR edge transfer for the S4-A2a audit.

This module contains only the distributed implicit prolongation and its
Hermitian adjoint.  It deliberately does not build a global prolongation
matrix, a node matrix, HX, PCGAMG, or a Krylov runner.  The fine canonical
topology is the parent-cell p-refined topology already retained by the
``build_hx=False`` L2 fixture; a separate raw p1 topology is used only to
bridge those owner packets to ``fixture.lor_edge_space``.

The next MPI2 increment must replace the local coarse-axis endpoint check with
global reductions/configuration endpoints and must replace the reused raw-map
same-owner-layout assumption with a distributed canonical/raw closure. Those
two boundaries are intentionally not hidden by an MPI1 guard here.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .fullspace_lor_edge_geometric_mg import build_local_lor_edge_geometric_transfer
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
from .fullspace_lor_topology import build_canonical_lor_subedge_topology


A2_SCHEMA = "task038.lor-edge-geometric-mg.global-implicit.v1"
A2_CELL_BATCH = 32


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
        mesh_coordinates = np.asarray(fixture.high_mesh.geometry.x, dtype=np.float64)
        for axis, values in enumerate(coarse_axes):
            if values.size < 2 or not np.all(np.diff(values) > 0.0):
                raise RuntimeError("coarse axes are not strictly increasing")
            if not np.isclose(values[0], np.min(mesh_coordinates[:, axis])):
                raise RuntimeError("coarse axis lower endpoint does not close")
            if not np.isclose(values[-1], np.max(mesh_coordinates[:, axis])):
                raise RuntimeError("coarse axis upper endpoint does not close")
        self.coarse_raw_map = _canonical_raw_map(
            self.coarse_space,
            coarse_node_space,
            coarse_records,
            coarse_axes,
            owner_ids=self.coarse_topology.owned_edge_ids,
            local_permutations=self.coarse_local_permutations,
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
    def _raw_map_facts(raw_map: dict[str, np.ndarray], owner_ids: np.ndarray) -> dict[str, Any]:
        phase = np.asarray(raw_map["phase_codes"])
        canonical = np.asarray(raw_map["canonical_ids"])
        active = phase == 0
        active_ids = canonical[active]
        if np.unique(active_ids).size != active_ids.size:
            raise RuntimeError("active raw rows are not unique")
        if not np.array_equal(np.sort(active_ids), np.sort(owner_ids)):
            raise RuntimeError("active raw rows do not cover owner IDs")
        factors = np.asarray(raw_map["orientation_factors"])
        if not np.all(np.isin(factors, (-1, 1))):
            raise RuntimeError("raw edge orientation factors are not signs")
        return {
            "owned_raw_rows": int(canonical.size),
            "active_raw_rows": int(np.count_nonzero(active)),
            "phase_rows": int(np.count_nonzero(~active)),
            "active_owner_bijection": True,
            "orientation_minus_count": int(np.count_nonzero(factors < 0)),
        }

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
            "owner_route": "typed_complex128_alltoallv",
            "coarse_basix_to_lor_order": self.local_transfer.coarse_basix_to_lor_order.tolist(),
            "q_custom_shape": list(self.q_custom.shape),
            "coarse_space_global_rows": int(
                self.coarse_space.dofmap.index_map.size_global
            ),
            "fine_raw_space_global_rows": int(
                self.fixture.lor_edge_space.dofmap.index_map.size_global
            ),
            "coarse_raw_map": self._raw_map_facts(
                self.coarse_raw_map, self.coarse_topology.owned_edge_ids
            ),
            "fine_raw_map": self._raw_map_facts(
                self.fine_raw_map, self.fine_raw_topology.owned_edge_ids
            ),
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
    "ImplicitLORTransferCase",
    "build_implicit_lor_transfer_case",
]
