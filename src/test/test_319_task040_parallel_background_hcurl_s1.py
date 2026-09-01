"""B0-S1a single-phase canonical owner round-trip."""

from __future__ import annotations

from math import asin, degrees, pi
from types import SimpleNamespace

import dolfinx_mpc
import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI

from src.common.config_3d import SimulationConfig3D
from src.constraints.floquet_3d_high_order import build_high_order_constraint_data
from src.geometry.mesh_builder_3d import _mark_boundary_facets
from src.solvers.floquet_background_hcurl_single_harmonic import (
    apply_phase_once,
    build_single_x_phase_layout,
    canonicalize_envelope,
    remove_phase_once,
)


def _fixture(comm):
    cfg = SimulationConfig3D(
        case_name="b0_s1a_tiny",
        stage_case="floquet_airbox",
        geometry_kind="airbox",
        lambda0=2.0 * pi,
        period_x=1.0,
        period_y=1.0,
        z_min=0.0,
        z_max=1.0,
        use_floquet_xy=True,
        incident_theta_deg=degrees(asin(0.17)),
        incident_phi_deg=0.0,
        nedelec_degree=1,
        floquet_constraint_mode="auto",
    )
    box = mesh.create_unit_cube(
        comm,
        2,
        2,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    V = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 1, dtype=default_real_type),
    )
    facet_tags, _boundary_facets = _mark_boundary_facets(box, cfg)
    mesh_data = SimpleNamespace(mesh=box, facet_tags=facet_tags)
    data = build_high_order_constraint_data(V, mesh_data, cfg)
    mpc = dolfinx_mpc.MultiPointConstraint(V)
    mpc.add_constraint(
        V,
        data.slave_local_dofs,
        data.master_global_dofs,
        data.coefficients,
        data.master_owners,
        data.offsets,
    )
    mpc.finalize()
    return box, V, mpc, np.complex128(cfg.floquet_phase_x)


def test_b0_s1a_single_x_phase_canonical_roundtrip():
    comm = MPI.COMM_WORLD
    _box, V, mpc, phase = _fixture(comm)
    layout = build_single_x_phase_layout(V, mpc, phase)
    assert layout.global_slave_count > 0
    assert layout.global_phase_count > 0
    assert layout.global_cross_owner_count >= 0
    if comm.size == 2:
        assert layout.global_cross_owner_count > 0

    field = fem.Function(V)
    index_map = V.dofmap.index_map
    owned_ids = index_map.local_to_global(
        np.arange(layout.owned_size, dtype=np.int32)
    )
    field.x.array[: layout.owned_size] = owned_ids + 0.25j
    field.x.scatter_forward()
    envelope = canonicalize_envelope(field.x.array, layout)
    applied = apply_phase_once(envelope, layout)
    recovered = remove_phase_once(applied.values, layout)
    recovered_values = canonicalize_envelope(recovered.values, layout)
    local_ids = index_map.local_to_global(
        np.arange(layout.local_size, dtype=np.int32)
    )
    canonical_ids = np.asarray(local_ids, dtype=np.int64)
    canonical_ids[layout.slave_local] = canonical_ids[layout.master_local]
    order = np.argsort(canonical_ids[: layout.owned_size], kind="stable")
    observed = recovered_values[: layout.owned_size][order]
    expected = envelope[: layout.owned_size][order]
    local_numerator = float(np.vdot(observed - expected, observed - expected).real)
    local_denominator = float(np.vdot(expected, expected).real)
    numerator = comm.allreduce(local_numerator, op=MPI.SUM)
    denominator = comm.allreduce(local_denominator, op=MPI.SUM)
    relative_error = np.sqrt(numerator) / max(np.sqrt(denominator), 1.0e-30)
    assert relative_error <= 1.0e-9
    assert applied.phase_application_count == 1
    assert recovered.phase_application_count == 1
    if comm.rank == 0:
        print(
            f"B0_S1A relative_error={relative_error:.3e} "
            f"cross_owner={layout.global_cross_owner_count} "
            f"phase={layout.global_phase_count}/{layout.global_slave_count}"
        )

    if comm.size != 1:
        return
    actual_slaves = np.asarray(mpc.slaves, dtype=np.int64)
    empty = SimpleNamespace(
        function_space=V,
        slaves=np.empty(0, dtype=np.int64),
        masters=mpc.masters,
        coefficients=mpc.coefficients,
    )
    with pytest.raises(RuntimeError):
        build_single_x_phase_layout(V, empty, phase)
    duplicate = SimpleNamespace(
        function_space=V,
        slaves=np.concatenate((actual_slaves, actual_slaves[:1])),
        masters=mpc.masters,
        coefficients=mpc.coefficients,
    )
    with pytest.raises(RuntimeError):
        build_single_x_phase_layout(V, duplicate, phase)
    index_map = V.dofmap.index_map
    bad_map = SimpleNamespace(
        size_local=int(index_map.size_local) + 1,
        num_ghosts=int(index_map.num_ghosts),
        local_to_global=index_map.local_to_global,
    )
    bad_space = SimpleNamespace(
        mesh=_box,
        dofmap=SimpleNamespace(index_map=bad_map),
    )
    with pytest.raises(RuntimeError):
        build_single_x_phase_layout(bad_space, mpc, phase)
