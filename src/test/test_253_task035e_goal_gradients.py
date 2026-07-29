from __future__ import annotations

import inspect
from types import MappingProxyType, SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest
import ufl

from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from basix.ufl import element

from src.adaptivity.task035e_goal_gradients import (
    INTERIOR_SENSITIVE_GOAL_IDS,
    Task035eFormalGoalGradients,
    _assemble_volume_p6_gradient,
    _oriented_physical_basis,
    _point_owners,
    _secant_weights,
    build_task035e_formal_secant_goal_gradients,
)
from src.adaptivity.blind_controller.contracts import FORMAL_GOAL_IDS


def _space(domain: mesh.Mesh, *, degree: int = 2):
    return fem.functionspace(
        domain,
        element(
            "N1curl",
            domain.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )


def test_oriented_point_basis_matches_complex_function_eval() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [2, 1, max(1, comm.size)],
        cell_type=mesh.CellType.hexahedron,
    )
    space = _space(domain)
    field = fem.Function(space)
    start = int(space.dofmap.index_map.local_range[0])
    rows = start + np.arange(len(field.x.array), dtype=float)
    field.x.array[:] = (
        np.cos(0.13 * (rows + 1.0))
        + 1j * np.sin(0.17 * (rows + 1.0))
    )
    field.x.scatter_forward()
    cell_count = domain.topology.index_map(domain.topology.dim).size_local
    assert cell_count > 0
    domain.topology.create_connectivity(domain.topology.dim, 0)
    cell = 0
    coordinates = domain.geometry.x[domain.geometry.dofmap[cell]]
    points = np.asarray(
        [
            0.25 * coordinates.min(axis=0)
            + 0.75 * coordinates.max(axis=0),
            0.65 * coordinates.min(axis=0)
            + 0.35 * coordinates.max(axis=0),
        ]
    )
    basis = _oriented_physical_basis(
        space,
        cell=cell,
        points=points,
    )
    coefficients = field.x.array[space.dofmap.cell_dofs(cell)]
    predicted = np.einsum("i,pic->pc", coefficients, basis)
    observed = np.asarray(
        field.eval(
            points,
            np.full(len(points), cell, dtype=np.int32),
        )
    ).reshape((-1, 3))
    np.testing.assert_allclose(predicted, observed, rtol=1e-13, atol=1e-13)


def test_point_owner_catalog_closes_in_mpi() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_unit_cube(
        comm,
        2,
        2,
        max(2, 2 * comm.size),
        cell_type=mesh.CellType.hexahedron,
    )
    space = _space(domain)
    points = np.asarray(
        [
            [0.25, 0.25, 0.0],
            [0.75, 0.75, 0.5],
            [0.25, 0.75, 1.0],
        ],
        dtype=np.float64,
    )
    owners, cells, audit = _point_owners(
        space,
        points,
        np.asarray([1, 1, -1], dtype=np.int8),
    )
    assert owners.shape == (3,)
    assert cells.shape == (3,)
    assert np.all(owners >= 0)
    assert np.all(owners < comm.size)
    assert np.all(cells >= 0)
    assert audit["full_vector_python_allgather_used"] is False


def test_volume_gradient_uses_field_scaled_quadratic_difference() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_unit_cube(
        comm,
        2,
        2,
        max(2, 2 * comm.size),
        cell_type=mesh.CellType.hexahedron,
    )
    space = _space(domain)
    field = fem.Function(space)
    start = int(space.dofmap.index_map.local_range[0])
    rows = start + np.arange(len(field.x.array), dtype=float)
    field.x.array[:] = 0.7 * np.cos(0.031 * (rows + 1.0)) + 0.4j * np.sin(
        0.047 * (rows + 1.0)
    )
    field.x.scatter_forward()
    cell_map = domain.topology.index_map(domain.topology.dim)
    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    cell_tags = mesh.meshtags(
        domain,
        domain.topology.dim,
        owned_cells,
        np.ones(len(owned_cells), dtype=np.int32),
    )
    view = SimpleNamespace(
        field=field,
        mesh_data=SimpleNamespace(
            mesh=domain,
            cell_tags=cell_tags,
        ),
        config=SimpleNamespace(
            k0=0.35,
            eps_grating=2.1 + 0.7j,
            eps_substrate=1.4 + 0.0j,
            tags=SimpleNamespace(grating=1, substrate=2),
        ),
        port_metrics={"incident_power_code_units": 1.3},
    )
    gradient, audit = _assemble_volume_p6_gradient(view)
    test = ufl.TestFunction(space)
    measure = ufl.Measure(
        "dx",
        domain=domain,
        subdomain_data=cell_tags,
    )
    coefficient = 0.5 * 0.35 * 0.7 / 1.3
    reference_gradient = fem_petsc.assemble_vector(
        fem.form(
            PETSc.ScalarType(2.0 * coefficient) * ufl.inner(field, test) * measure(1)
        )
    )
    reference_gradient.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    reference_value = float(
        np.real(
            comm.allreduce(
                fem.assemble_scalar(
                    fem.form(
                        PETSc.ScalarType(coefficient)
                        * ufl.real(ufl.inner(field, field))
                        * measure(1)
                    )
                ),
                op=MPI.SUM,
            )
        )
    )
    difference = gradient.copy()
    try:
        difference.axpy(
            PETSc.ScalarType(-1.0),
            reference_gradient,
        )
        assert difference.norm() / reference_gradient.norm() <= 2.0e-12
        assert audit["goal_value"] == pytest.approx(
            reference_value,
            rel=2.0e-12,
            abs=2.0e-13,
        )
        assert audit["finite_difference_relative_step"] == 1.0e-5
        assert audit["finite_difference_absolute_step"] > 1.0e-7
        assert audit["finite_difference_relative_error"] <= 2.0e-7
        assert audit["field_l2_norm"] > 0.0
        assert audit["direction_l2_norm"] > 0.0
        assert audit["ffcx_jit_form_loaded"] is False
        assert audit["affine_geometry_gate_pass"] is True
        assert audit["quadrature_degree"] == 12
        assert audit["quadrature_point_count"] == 343
    finally:
        difference.destroy()
        reference_gradient.destroy()
        gradient.destroy()


def test_volume_gradient_rejects_nonaffine_hexahedron_collectively() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_unit_cube(
        comm,
        2,
        1,
        max(2, 2 * comm.size),
        cell_type=mesh.CellType.hexahedron,
    )
    space = _space(domain)
    field = fem.Function(space)
    field.x.array[:] = PETSc.ScalarType(1.0 + 0.25j)
    field.x.scatter_forward()
    cell_map = domain.topology.index_map(domain.topology.dim)
    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    cell_tags = mesh.meshtags(
        domain,
        domain.topology.dim,
        owned_cells,
        np.ones(len(owned_cells), dtype=np.int32),
    )
    if comm.rank == 0:
        geometry_rows = domain.geometry.dofmap[0]
        domain.geometry.x[int(geometry_rows[-1]), 0] += 0.013
    view = SimpleNamespace(
        field=field,
        mesh_data=SimpleNamespace(
            mesh=domain,
            cell_tags=cell_tags,
        ),
        config=SimpleNamespace(
            k0=0.35,
            eps_grating=2.1 + 0.7j,
            eps_substrate=1.4 + 0.0j,
            tags=SimpleNamespace(grating=1, substrate=2),
        ),
        port_metrics={"incident_power_code_units": 1.3},
    )
    with pytest.raises(
        RuntimeError,
        match="collective A_volume affine-hexahedron gate failed",
    ):
        _assemble_volume_p6_gradient(view)


def test_volume_gradient_p6_affine_workspace_is_bounded() -> None:
    comm = MPI.COMM_WORLD
    domain = mesh.create_unit_cube(
        comm,
        1,
        1,
        max(1, comm.size),
        cell_type=mesh.CellType.hexahedron,
    )
    space = _space(domain, degree=6)
    field = fem.Function(space)
    rows = int(space.dofmap.index_map.local_range[0]) + np.arange(
        len(field.x.array), dtype=float
    )
    field.x.array[:] = 0.3 * np.cos(0.019 * (rows + 1.0)) + 0.2j * np.sin(
        0.029 * (rows + 1.0)
    )
    field.x.scatter_forward()
    cell_map = domain.topology.index_map(domain.topology.dim)
    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    cell_tags = mesh.meshtags(
        domain,
        domain.topology.dim,
        owned_cells,
        np.ones(len(owned_cells), dtype=np.int32),
    )
    view = SimpleNamespace(
        field=field,
        mesh_data=SimpleNamespace(mesh=domain, cell_tags=cell_tags),
        config=SimpleNamespace(
            k0=0.35,
            eps_grating=2.1 + 0.7j,
            eps_substrate=1.4 + 0.0j,
            tags=SimpleNamespace(grating=1, substrate=2),
        ),
        port_metrics={"incident_power_code_units": 1.3},
    )
    gradient, audit = _assemble_volume_p6_gradient(view)
    try:
        assert gradient.getSize() == space.dofmap.index_map.size_global
        assert gradient.norm() > 0.0
        assert audit["finite_difference_relative_error"] <= 2.0e-7
        assert audit["quadrature_point_count"] == 343
        assert audit["maximum_live_basis_workspace_bytes_per_rank"] < 32 * 1024**2
    finally:
        gradient.destroy()


def test_formal_builder_has_no_reference_or_endpoint_input() -> None:
    from src.adaptivity.task035e_goal_gradients import (
        build_task035e_formal_goal_gradients,
    )

    parameters = inspect.signature(
        build_task035e_formal_goal_gradients
    ).parameters
    assert tuple(parameters) == ("view",)


def test_secant_builder_spools_current_and_reuses_shadow_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.adaptivity import task035e_goal_gradients as module

    comm = MPI.COMM_WORLD
    bundles: list[Task035eFormalGoalGradients] = []

    def endpoint_bundle(scale: float) -> Task035eFormalGoalGradients:
        gradients = {}
        active = {}
        for index, goal_id in enumerate(FORMAL_GOAL_IDS):
            vector = PETSc.Vec().createMPI(23, comm=comm)
            vector.set(PETSc.ScalarType(scale * (index + 1)))
            gradients[goal_id] = vector
        for index, goal_id in enumerate(INTERIOR_SENSITIVE_GOAL_IDS):
            vector = PETSc.Vec().createMPI(29, comm=comm)
            vector.set(PETSc.ScalarType(scale * (index + 2)))
            active[goal_id] = vector
        bundle = Task035eFormalGoalGradients(
            gradients=MappingProxyType(gradients),
            active_full_gradients=MappingProxyType(active),
            audit=MappingProxyType(
                {
                    "gradient_inventory_sha256": (
                        f"{int(scale)}" * 64
                    ),
                    "field_goal_metadata": {
                        "interface_probe_l2": 3.0 * scale,
                        "volume_probe_l2": 5.0 * scale,
                    },
                }
            ),
        )
        bundles.append(bundle)
        return bundle

    scales = iter((1.0, 2.0))
    monkeypatch.setattr(
        module,
        "build_task035e_formal_goal_gradients",
        lambda _view: endpoint_bundle(next(scales)),
    )
    release_called = False

    def release_endpoint(_comm: MPI.Intracomm) -> dict[str, object]:
        nonlocal release_called
        assert bundles[0]._destroyed is True
        release_called = True
        return {
            "schema_version": (
                "task035e.endpoint-gradient-spool-release.v1"
            ),
            "pass": True,
            "sum_rank_rss_released_mb": 12.5,
        }

    monkeypatch.setattr(
        module,
        "_release_spooled_endpoint",
        release_endpoint,
    )
    view = SimpleNamespace(
        mesh_data=SimpleNamespace(mesh=SimpleNamespace(comm=comm))
    )
    result = build_task035e_formal_secant_goal_gradients(view, view)
    try:
        assert release_called is True
        assert result is bundles[1]
        assert bundles[0]._destroyed is True
        assert not bundles[0].gradients
        assert not bundles[0].active_full_gradients
        assert result.audit["third_full_gradient_inventory_allocated"] is False
        assert result.audit["secant_vector_allocation_strategy"] == (
            "rank_local_current_endpoint_spool_then_"
            "destructive_shadow_reuse"
        )
        assert result.audit["endpoint_spool"][
            "maximum_simultaneous_endpoint_vector_inventories"
        ] == 1
        assert result.audit["endpoint_spool"]["total_spool_bytes"] > 0
        assert (
            result.audit["endpoint_spool"]["hidden_reference_content"]
            is False
        )
        gradient_hashes = comm.allgather(
            result.audit["gradient_inventory_sha256"]
        )
        assert len(set(gradient_hashes)) == 1
        assert len(
            result.audit["endpoint_spool"]["rank_local_spool_bytes"]
        ) == comm.size
        assert len(
            result.audit["endpoint_spool"][
                "maximum_live_spool_read_bytes_by_rank"
            ]
        ) == comm.size
        for index, goal_id in enumerate(FORMAL_GOAL_IDS):
            current_weight = (
                1.0 / 3.0
                if goal_id
                in {
                    "scalar/interface_probe_l2",
                    "scalar/volume_probe_l2",
                }
                else 0.5
            )
            shadow_weight = 1.0 - current_weight
            expected = (index + 1) * (
                current_weight + 2.0 * shadow_weight
            )
            np.testing.assert_allclose(
                result.gradients[goal_id].getArray(readonly=True),
                expected,
                rtol=2.0e-15,
                atol=2.0e-15,
            )
    finally:
        result.destroy()


def test_analytic_secant_weights_close_quadratic_and_l2_goals() -> None:
    current = np.asarray([0.7 + 0.2j, -0.3 + 0.4j])
    shadow = np.asarray([0.2 - 0.1j, 0.5 + 0.3j])
    delta = shadow - current

    quadratic_matrix = np.asarray(
        [[1.4, 0.2 - 0.1j], [0.2 + 0.1j, 0.9]],
        dtype=np.complex128,
    )
    current_gradient = 2.0 * quadratic_matrix @ current
    shadow_gradient = 2.0 * quadratic_matrix @ shadow
    secant_gradient = 0.5 * (
        current_gradient + shadow_gradient
    )
    quadratic_delta = float(
        np.vdot(shadow, quadratic_matrix @ shadow).real
        - np.vdot(current, quadratic_matrix @ current).real
    )
    assert float(np.vdot(secant_gradient, delta).real) == pytest.approx(
        quadratic_delta,
        rel=2.0e-15,
        abs=2.0e-15,
    )

    current_norm = float(np.linalg.norm(current))
    shadow_norm = float(np.linalg.norm(shadow))
    audit_current = {
        "field_goal_metadata": {
            "interface_probe_l2": current_norm,
            "volume_probe_l2": current_norm,
        }
    }
    audit_shadow = {
        "field_goal_metadata": {
            "interface_probe_l2": shadow_norm,
            "volume_probe_l2": shadow_norm,
        }
    }
    current_weight, shadow_weight, rule = _secant_weights(
        "scalar/volume_probe_l2",
        current_audit=audit_current,
        shadow_audit=audit_shadow,
    )
    assert rule == "exact_l2_secant_endpoint_norm_weighting"
    l2_gradient = (
        current_weight * current / current_norm
        + shadow_weight * shadow / shadow_norm
    )
    assert float(np.vdot(l2_gradient, delta).real) == pytest.approx(
        shadow_norm - current_norm,
        rel=2.0e-15,
        abs=2.0e-15,
    )
    assert _secant_weights(
        "scalar/A_volume",
        current_audit=audit_current,
        shadow_audit=audit_shadow,
    ) == (
        0.5,
        0.5,
        "arithmetic_endpoint_gradient_average",
    )
