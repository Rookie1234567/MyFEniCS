"""Focused contracts and a real p2 hexa/Floquet one-cell lift fixture."""

from types import SimpleNamespace
from pathlib import Path
import tempfile

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import oblique_incidence_airbox_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.one_cell_trace_schur import (
    EndpointActiveRows,
    EndpointModeLifter,
    _active_values_for_port,
    apply_directional_endpoint_columns,
    assemble_directional_endpoint_columns,
    identify_endpoint_active_rows,
    lifted_endpoint_columns,
)
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)


class _Comm:
    def __init__(self, packets=None):
        self.packets = packets

    def tompi4py(self):
        return self

    def allgather(self, entries):
        return [entries] if self.packets is None else self.packets


class _Vec:
    def __init__(self, values, packets=None):
        self.values = np.asarray(values, dtype=np.complex128)
        self.comm = _Comm(packets)

    def getComm(self):
        return self.comm

    def getValues(self, indices):
        return self.values[np.asarray(indices, dtype=np.int64)]


class _X:
    def __init__(self, vector):
        self.petsc_vec = vector
        self.scatter_calls = 0

    def scatter_forward(self):
        self.scatter_calls += 1


class _MPC:
    def __init__(self):
        self.calls = 0

    def homogenize(self, field):
        self.calls += 1


def _rows() -> EndpointActiveRows:
    return EndpointActiveRows(
        left_original=np.array([10, 11]),
        right_original=np.array([20, 21]),
        left_active=np.array([0, 2]),
        right_active=np.array([4, 5]),
        interior_active=np.array([1, 3]),
        left_original_sha256="left",
        right_original_sha256="right",
        left_active_sha256="left-active",
        right_active_sha256="right-active",
        interior_active_sha256="interior",
    )


def _field(values, *, owned=None, packets=None):
    if owned is None:
        owned = np.array([0, 1, 2, 3])
    constraints = SimpleNamespace(
        owned_active_original_dofs=np.asarray(owned, dtype=np.int32),
        original_to_active={0: 0, 1: 2, 2: 4, 3: 5},
    )
    condensed = SimpleNamespace(trace_constraints=constraints)
    field = SimpleNamespace(x=_X(_Vec(values, packets)))
    return field, condensed


def test_active_values_preserve_left_right_order() -> None:
    field, condensed = _field([10, 11, 12, 13])
    result = _active_values_for_port(field, condensed, [0, 2, 4, 5])
    np.testing.assert_allclose(result, [10, 11, 12, 13])


def test_active_values_fail_closed_for_missing_row() -> None:
    field, condensed = _field([10, 11], owned=[0, 1])
    with pytest.raises(RuntimeError, match="missing"):
        _active_values_for_port(field, condensed, [0, 2, 4, 5])


def test_active_values_fail_closed_for_duplicate_owner() -> None:
    entries = [(0, 10.0), (2, 12.0), (4, 14.0), (5, 15.0)]
    field, condensed = _field(
        [10, 11, 12, 13],
        packets=[entries, entries],
    )
    with pytest.raises(RuntimeError, match="multiple owners"):
        _active_values_for_port(field, condensed, [0, 2, 4, 5])


def test_lifted_columns_homogenize_each_source_and_keep_side_order() -> None:
    first, condensed = _field([10, 11, 12, 13])
    second, _ = _field([20, 21, 22, 23])
    mpc = _MPC()
    lifter = SimpleNamespace(lift=lambda source: source)
    left, right = lifted_endpoint_columns(
        [first, second],
        lifter,
        condensed,
        _rows(),
        mpc=mpc,
    )
    np.testing.assert_allclose(left, [[10, 20], [11, 21]])
    np.testing.assert_allclose(right, [[12, 22], [13, 23]])
    assert mpc.calls == 2
    assert first.x.scatter_calls == 1
    assert second.x.scatter_calls == 1


def test_directional_action_is_thin_and_checks_port_rows() -> None:
    seen = []

    def apply(columns):
        seen.append(columns.copy())
        return 2.0 * columns

    action = SimpleNamespace(port_rows=4, apply_columns=apply)
    result = apply_directional_endpoint_columns(
        action,
        np.ones((2, 1), dtype=np.complex128),
        np.ones((2, 1), dtype=np.complex128),
        multipliers=[-1.0],
    )
    np.testing.assert_allclose(result[:, 0], [2.0, 2.0, -2.0, -2.0])
    assert len(seen) == 1

    with pytest.raises(ValueError):
        apply_directional_endpoint_columns(
            SimpleNamespace(port_rows=3, apply_columns=apply),
            np.ones((2, 1)),
            np.ones((2, 1)),
            multipliers=[1.0],
        )


def test_directional_assembly_rejects_inconsistent_column_count() -> None:
    with pytest.raises(ValueError, match="column counts"):
        assemble_directional_endpoint_columns(
            np.ones((2, 1)),
            np.ones((3, 2)),
            multipliers=[1.0],
        )


def test_real_hcurl_p2_double_floquet_endpoint_lift() -> None:
    """Actual p2 hexa/Floquet lift with active rows from condensation."""

    comm = MPI.COMM_SELF
    cfg = oblique_incidence_airbox_config(
        case_name="task037c_x1_endpoint_fixture",
        stage_case="floquet_airbox",
        geometry_kind="airbox",
        lambda0=13.5,
        period_x=10.0,
        period_y=10.0,
        z_min=0.0,
        z_max=10.0,
        use_floquet_xy=True,
        use_pml=False,
        incident_theta_deg=37.0,
        incident_phi_deg=23.0,
        polarization_kind="s",
        custom_polarization=None,
        nedelec_degree=2,
        visualization_degree=1,
        mesh_target_size=5.0,
        mesh_cell_type="hexahedron",
        floquet_constraint_mode="auto",
    )
    mesh_data = build_airbox_mesh_3d(
        cfg,
        Path(tempfile.mkdtemp(prefix="task037c_x1_floquet_")),
    )
    V = fem.functionspace(
        mesh_data.mesh,
        element("N1curl", mesh_data.mesh.basix_cell(), 2, dtype=default_real_type),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.dx(domain=mesh_data.mesh)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
        )
        * dx
    )
    floquet = build_double_floquet_mpc(V, mesh_data, cfg)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        mesh_data.cell_tags,
        mpc=floquet.mpc,
        retain_local_schur_for_matrix_free=True,
        materialize_global_matrix=False,
    )
    assert condensed.matrix is None
    bottom_facets = mesh.locate_entities_boundary(
        mesh_data.mesh,
        mesh_data.mesh.topology.dim - 1,
        lambda x: np.isclose(x[2], 0.0),
    )
    top_facets = mesh.locate_entities_boundary(
        mesh_data.mesh,
        mesh_data.mesh.topology.dim - 1,
        lambda x: np.isclose(x[2], 10.0),
    )
    rows = identify_endpoint_active_rows(
        V,
        condensed,
        left_facets=bottom_facets,
        right_facets=top_facets,
    )
    source_mesh = mesh.create_rectangle(
        comm,
        [np.array([0.0, 0.0]), np.array([10.0, 10.0])],
        [1, 1],
        cell_type=mesh.CellType.quadrilateral,
    )
    source_space = fem.functionspace(
        source_mesh,
        element("N1curl", source_mesh.basix_cell(), 2, dtype=default_real_type),
    )
    source = fem.Function(source_space)
    source.interpolate(lambda x: np.vstack((1.0 + x[0], 2.0 + x[1])))
    source.x.scatter_forward()
    lifter = EndpointModeLifter(V, 10.0)
    try:
        left, right = lifted_endpoint_columns(
            [source],
            lifter,
            condensed,
            rows,
            mpc=floquet.mpc,
        )
        assert rows.left_active.size > 0
        assert rows.right_active.size > 0
        assert rows.to_record()["left_right_disjoint"] is True
        assert left.shape == (rows.left_active.size, 1)
        assert right.shape == (rows.right_active.size, 1)
        assert np.all(np.isfinite(left))
        assert np.all(np.isfinite(right))
        assert np.linalg.norm(left) > 0.0
        assert np.linalg.norm(right) > 0.0
        assert np.all(np.isfinite(lifter.target.x.array))
    finally:
        condensed.destroy()
