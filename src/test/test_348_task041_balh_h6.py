"""Focused real-FE checks for the fixed V5 BAL_H H6 action."""

from __future__ import annotations

import json
from types import SimpleNamespace

import basix
import dolfinx_mpc
import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import SimulationConfig3D
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import _structured_hexa_mesh
from src.solvers.physical_balanced_h6 import (
    build_balanced_h6,
    build_fixed_random_seed,
    build_positive_material_coefficients,
)
from src.solvers.physical_balanced_mpc_action import FullspaceMpcFormAction
from src.solvers.physical_balanced_positive_kernel import (
    IsotropicPartialAssembly,
    PositiveCellBasis,
    _cell_jacobians,
    _validate_affine_cell_jacobians,
    build_quadrature_positive_diagonal,
    same_mesh_positive_form,
)

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="Task041 H1d focused H6 tests are serial/MPI2 only",
)


def _fixture_config() -> SimulationConfig3D:
    return SimulationConfig3D(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=3.7,
        period_x=1.0,
        period_y=1.0,
        z_min=0.0,
        z_max=1.0,
        interface_z=0.5,
        n_substrate=1.4 + 0.02j,
        n_grating=1.7 + 0.01j,
        grating_width_x=1.0,
        grating_width_y=1.0,
        grating_height=0.5,
        incident_theta_deg=17.0,
        incident_phi_deg=23.0,
        polarization_kind="s",
        nedelec_degree=6,
        mesh_cell_type="hexahedron",
        mesh_target_size=2.0,
        mesh_axis_cell_counts=(2, 1, 1),
        use_floquet_xy=True,
        floquet_constraint_mode="topological_trace_p6",
    )


def _boundary_tags(msh: mesh.Mesh, cfg: SimulationConfig3D) -> mesh.MeshTags:
    fdim = msh.topology.dim - 1
    records = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
        (cfg.tags.z_min, lambda x: np.isclose(x[2], cfg.domain_z_min)),
        (cfg.tags.z_max, lambda x: np.isclose(x[2], cfg.domain_z_max)),
    )
    indices = []
    values = []
    for tag, marker in records:
        found = mesh.locate_entities_boundary(msh, fdim, marker)
        indices.append(np.asarray(found, dtype=np.int32))
        values.append(np.full(len(found), tag, dtype=np.int32))
    all_indices = np.concatenate(indices)
    all_values = np.concatenate(values)
    order = np.argsort(all_indices)
    return mesh.meshtags(
        msh,
        fdim,
        all_indices[order],
        all_values[order],
    )


def _cell_tags(msh: mesh.Mesh, cfg: SimulationConfig3D) -> mesh.MeshTags:
    owned = int(msh.topology.index_map(msh.topology.dim).size_local)
    values = np.empty(owned, dtype=np.int32)
    for cell in range(owned):
        midpoint = np.mean(msh.geometry.x[msh.geometry.dofmap[cell]], axis=0)
        values[cell] = (
            int(cfg.tags.air) if midpoint[0] < 0.5 else int(cfg.tags.grating)
        )
    local_counts = np.asarray(
        [
            np.count_nonzero(values == int(cfg.tags.air)),
            np.count_nonzero(values == int(cfg.tags.grating)),
        ],
        dtype=np.int32,
    )
    global_counts = msh.comm.allreduce(local_counts, op=MPI.SUM)
    if tuple(int(value) for value in global_counts) != (1, 1):
        raise RuntimeError("H1d fixture requires one global air and one grating cell")
    return mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(owned, dtype=np.int32),
        values,
    )


def _new_algebraic_vector(space, mpc, seed: float) -> PETSc.Vec:
    index_map = space.dofmap.index_map
    vector = create_vector([(index_map, int(space.dofmap.index_map_bs))])
    first, last = (int(value) for value in vector.getOwnershipRange())
    rows = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = (
        seed
        + 0.013 * rows
        + 1.0
        + 1j * (0.31 + 0.009 * rows)
    ).astype(PETSc.ScalarType)
    local_slaves = np.asarray(mpc.slaves, dtype=np.int64)
    local_slaves = local_slaves[local_slaves < vector.getLocalSize()]
    vector.getArray()[local_slaves] = 0.0
    vector.assemble()
    return vector


def _copy_vector(source: PETSc.Vec) -> PETSc.Vec:
    result = source.duplicate()
    source.copy(result)
    return result


def _relative_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.duplicate()
    try:
        left.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), right)
        denominator = float(right.norm())
        numerator = float(difference.norm())
        return numerator / denominator if denominator > 0.0 else numerator
    finally:
        difference.destroy()


def _closed_form_chebyshev(
    matrix: PETSc.Mat,
    diagonal: PETSc.Vec,
    rhs: PETSc.Vec,
    lambda_hi: float,
    lambda_lo: float,
) -> PETSc.Vec:
    """Independent p2(B) oracle for the fixed degree-three H6 recurrence."""

    inverse_sqrt = diagonal.duplicate()
    scaled_rhs = rhs.duplicate()
    first_action = matrix.createVecLeft()
    second_action = matrix.createVecLeft()
    work = rhs.duplicate()
    polynomial = rhs.duplicate()
    result = matrix.createVecRight()
    try:
        diagonal_values = np.asarray(
            diagonal.getArray(readonly=True), dtype=np.complex128
        )
        inverse_sqrt.getArray()[:] = 1.0 / np.sqrt(diagonal_values.real)
        inverse_sqrt.assemble()
        scaled_rhs.pointwiseMult(inverse_sqrt, rhs)
        work.pointwiseMult(inverse_sqrt, scaled_rhs)
        matrix.mult(work, second_action)
        first_action.pointwiseMult(inverse_sqrt, second_action)
        work.pointwiseMult(inverse_sqrt, first_action)
        matrix.mult(work, second_action)
        work.pointwiseMult(inverse_sqrt, second_action)

        center = 0.5 * (lambda_hi + lambda_lo)
        half_width = 0.5 * (lambda_hi - lambda_lo)
        denominator = 4.0 * center**3 - 3.0 * center * half_width**2
        coefficient_0 = (12.0 * center**2 - 3.0 * half_width**2) / denominator
        coefficient_1 = -12.0 * center / denominator
        coefficient_2 = 4.0 / denominator
        polynomial.set(0.0)
        polynomial.axpy(coefficient_0, scaled_rhs)
        polynomial.axpy(coefficient_1, first_action)
        polynomial.axpy(coefficient_2, work)
        result.pointwiseMult(inverse_sqrt, polynomial)
        return result
    except BaseException:
        result.destroy()
        raise
    finally:
        inverse_sqrt.destroy()
        scaled_rhs.destroy()
        first_action.destroy()
        second_action.destroy()
        work.destroy()
        polynomial.destroy()


def test_task041_affine_geometry_validation_is_translation_stable() -> None:
    box = mesh.create_unit_cube(
        MPI.COMM_SELF,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    coordinates = np.asarray(
        box.geometry.x[box.geometry.dofmap[0]], dtype=np.float64
    )
    translated = coordinates + np.asarray([1.0e9, -2.0e9, 3.0e9])
    geometry_element = basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.hexahedron,
        1,
        basix.LagrangeVariant.equispaced,
    )
    points, _ = basix.make_quadrature(basix.CellType.hexahedron, 2)
    derivatives = geometry_element.tabulate(1, points)[1:, :, :, 0]

    jacobians = _cell_jacobians(derivatives, translated)
    jacobian, determinant = _validate_affine_cell_jacobians(jacobians)
    np.testing.assert_allclose(jacobian, np.eye(3), rtol=0.0, atol=1.0e-14)
    assert determinant > 0.0

    non_affine = translated.copy()
    non_affine[6, 2] += 0.125
    with pytest.raises(NotImplementedError, match="affine geometry"):
        _validate_affine_cell_jacobians(
            _cell_jacobians(derivatives, non_affine)
        )

    reflected = translated.copy()
    reflected[:, 0] = 1.0e9 - (reflected[:, 0] - 1.0e9)
    with pytest.raises(ValueError, match="positive finite"):
        _validate_affine_cell_jacobians(
            _cell_jacobians(derivatives, reflected)
        )


    zero_jacobians = np.zeros_like(jacobians)
    with pytest.raises(ValueError, match="positive finite"):
        _validate_affine_cell_jacobians(zero_jacobians)
    nonfinite_jacobians = jacobians.copy()
    nonfinite_jacobians[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="positive finite"):
        _validate_affine_cell_jacobians(nonfinite_jacobians)


def test_task041_positive_cell_basis_handles_top_translation_and_rejects_nonaffine():
    x_values = np.asarray([0.0, 1.5], dtype=default_real_type)
    y_values = np.asarray([0.0, 25.0 / 17.0], dtype=default_real_type)
    top_z_values = np.asarray([111.0, 112.5], dtype=default_real_type)
    reference_z_values = np.asarray([0.0, 1.5], dtype=default_real_type)

    def make_basis(z_values):
        local_mesh = _structured_hexa_mesh(
            MPI.COMM_SELF, x_values, y_values, z_values
        )
        space = fem.functionspace(
            local_mesh,
            element(
                "N1curl",
                local_mesh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        coefficient_space = fem.functionspace(local_mesh, ("DG", 0))
        mu = fem.Function(coefficient_space)
        mass = fem.Function(coefficient_space)
        mu.x.array[:] = 2.0
        mass.x.array[:] = 3.0
        basis = PositiveCellBasis(space, mu, mass, action_rule=False)
        local_mesh.topology.create_entity_permutations()
        permutation = int(local_mesh.topology.get_cell_permutation_info()[0])
        return local_mesh, space, mu, mass, basis, permutation

    (
        reference_mesh,
        reference_space,
        reference_mu,
        reference_mass,
        reference_basis,
        reference_permutation,
    ) = make_basis(reference_z_values)
    (
        top_mesh,
        top_space,
        top_mu,
        top_mass,
        top_basis,
        top_permutation,
    ) = make_basis(top_z_values)
    try:
        top_coordinates = np.asarray(
            top_mesh.geometry.x[top_mesh.geometry.dofmap[0]], dtype=np.float64
        )
        assert np.min(top_coordinates[:, 2]) == 111.0
        assert np.max(top_coordinates[:, 2]) == 112.5
        assert np.max(top_coordinates[:, 0]) == 1.5
        assert np.max(top_coordinates[:, 1]) == 25.0 / 17.0

        reference_values, reference_curls, reference_weights, reference_coefficients = (
            reference_basis.cell(0, reference_permutation)
        )
        top_values, top_curls, top_weights, top_coefficients = top_basis.cell(
            0, top_permutation
        )
        np.testing.assert_allclose(top_values, reference_values, rtol=1.0e-13, atol=1.0e-13)
        np.testing.assert_allclose(top_curls, reference_curls, rtol=1.0e-13, atol=1.0e-13)
        np.testing.assert_allclose(top_weights, reference_weights, rtol=1.0e-13, atol=1.0e-13)
        assert top_coefficients == reference_coefficients == (2.0, 3.0)

        reference_packed = IsotropicPartialAssembly(
            reference_space,
            reference_mu,
            reference_mass,
            contiguous_work=True,
        )
        top_packed = IsotropicPartialAssembly(
            top_space,
            top_mu,
            top_mass,
            contiguous_work=True,
        )
        np.testing.assert_allclose(
            top_packed.metrics,
            reference_packed.metrics,
            rtol=1.0e-13,
            atol=1.0e-13,
        )

        top_cell_dofs = np.asarray(top_mesh.geometry.dofmap[0], dtype=np.int64)
        top_mesh.geometry.x[top_cell_dofs[6], 2] += 0.125
        with pytest.raises(NotImplementedError, match="affine geometry"):
            top_basis.cell(0, top_permutation)
        with pytest.raises(NotImplementedError, match="affine geometry"):
            IsotropicPartialAssembly(
                top_space,
                top_mu,
                top_mass,
                contiguous_work=True,
            )
    finally:
        del top_basis, reference_basis, top_mesh, reference_mesh


@pytest.fixture(scope="module")
def h6_fixture():
    cfg = _fixture_config()
    box = mesh.create_unit_cube(
        MPI.COMM_WORLD,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    mesh_data = SimpleNamespace(
        mesh=box,
        facet_tags=_boundary_tags(box, cfg),
        cell_tags=_cell_tags(box, cfg),
    )
    space = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 6, dtype=default_real_type),
    )
    floquet_data = build_double_floquet_mpc(space, mesh_data, cfg)
    local_mesh = SimpleNamespace(mesh=box, mesh_data=mesh_data)
    side_system = SimpleNamespace(
        side="bottom",
        cfg=cfg,
        local_mesh=local_mesh,
        V=space,
        floquet_data=floquet_data,
    )
    reference = None
    reference_diagonal = None
    quadrature_diagonal = None
    original_action = None
    packed_action = None
    h6 = None
    seed = None
    mu = mass = None
    try:
        mu, mass, material_audit = build_positive_material_coefficients(side_system)
        form = same_mesh_positive_form(
            space,
            curl_coefficient=mu,
            mass_coefficient=mass,
        )
        compiled = fem.form(form, dtype=PETSc.ScalarType)
        reference = dolfinx_mpc.assemble_matrix(compiled, floquet_data.mpc, bcs=[])
        reference.assemble()
        reference_diagonal = reference.createVecRight()
        reference.getDiagonal(reference_diagonal)
        quadrature_diagonal = build_quadrature_positive_diagonal(
            space,
            mu,
            mass,
            floquet_data.mpc,
        )
        original_action = FullspaceMpcFormAction(
            form,
            space,
            mpc=floquet_data.mpc,
        )
        packed_action = FullspaceMpcFormAction(
            form,
            space,
            mpc=floquet_data.mpc,
            local_kernel=IsotropicPartialAssembly(
                floquet_data.mpc.function_space,
                mu,
                mass,
                contiguous_work=True,
            ),
        )
        seed, seed_audit = build_fixed_random_seed(space, floquet_data, cfg)
        h6 = build_balanced_h6(side_system)
        seed.destroy()
        seed = None
        yield {
            "cfg": cfg,
            "space": space,
            "mpc": floquet_data.mpc,
            "reference": reference,
            "reference_diagonal": reference_diagonal,
            "quadrature_diagonal": quadrature_diagonal,
            "original_action": original_action,
            "packed_action": packed_action,
            "h6": h6,
            "material_audit": material_audit,
            "seed_audit": seed_audit,
        }
    finally:
        if h6 is not None:
            h6.destroy()
        if packed_action is not None:
            packed_action.destroy()
        if original_action is not None:
            original_action.destroy()
        if quadrature_diagonal is not None:
            quadrature_diagonal.destroy()
        if reference_diagonal is not None:
            reference_diagonal.destroy()
        if reference is not None:
            reference.destroy()
        if seed is not None:
            seed.destroy()


def test_task041_h1d_h6_real_fe_oracle_and_fixed_window(h6_fixture) -> None:
    data = h6_fixture
    reference = data["reference"]
    reference_diagonal = data["reference_diagonal"]
    quadrature_diagonal = data["quadrature_diagonal"]
    original_action = data["original_action"]
    packed_action = data["packed_action"]
    h6 = data["h6"]
    mpc = data["mpc"]
    q1 = _new_algebraic_vector(data["space"], mpc, 2.0)
    q2 = _new_algebraic_vector(data["space"], mpc, 7.0)
    zero = q1.duplicate()
    zero.set(0.0)
    zero.assemble()
    outputs: list[PETSc.Vec] = []
    reference_outputs: list[PETSc.Vec] = []
    try:
        assert q1.norm() > 0.0
        assert q2.norm() > 0.0
        q1_before = np.asarray(q1.getArray(readonly=True)).copy()
        q2_before = np.asarray(q2.getArray(readonly=True)).copy()

        diagonal_relative = _relative_difference(
            quadrature_diagonal,
            reference_diagonal,
        )
        assert diagonal_relative <= 1.0e-10
        assert data["material_audit"]["owned_cell_count"] > 0

        for rhs in (q1, q2):
            reference_output = reference.createVecLeft()
            reference.mult(rhs, reference_output)
            reference_outputs.append(reference_output)

        for action in (original_action, packed_action):
            first = _copy_vector(action.apply(q1))
            second = _copy_vector(action.apply(q2))
            repeat = _copy_vector(action.apply(q1))
            outputs.extend((first, second, repeat))
            assert _relative_difference(first, reference_outputs[0]) <= 1.0e-10
            assert _relative_difference(second, reference_outputs[1]) <= 1.0e-10
            assert _relative_difference(first, repeat) <= 1.0e-12

        np.testing.assert_array_equal(q1.getArray(readonly=True), q1_before)
        np.testing.assert_array_equal(q2.getArray(readonly=True), q2_before)
        assert packed_action.audit["local_kernel"]["component"] == "positive_sum"

        audit_before = dict(h6.audit)
        power_history = tuple(audit_before["power_history"])
        window_values = (
            float(audit_before["lambda_power10"]),
            float(audit_before["lambda_hi"]),
            float(audit_before["lambda_lo"]),
        )
        assert audit_before["h6_degree"] == 3
        assert audit_before["power_steps"] == 10
        assert audit_before["power_matrix_mult_count"] == 20
        assert audit_before["window_original_apply_count"] == 20
        assert audit_before["runtime_apply_count_at_install"] == 0
        assert audit_before["contiguous_work"] is True
        assert audit_before["factor_count"] == 0
        assert len(power_history) == 10
        json.dumps(audit_before)
        assert data["seed_audit"]["name"] == "random"
        assert "fixed noninteger trigonometric" in data["seed_audit"]["formula"]

        before = h6.matrix_mult_count
        h6_q1 = h6.apply(q1)
        outputs.append(h6_q1)
        assert h6.matrix_mult_count - before == 2
        before = h6.matrix_mult_count
        h6_q2 = h6.apply(q2)
        outputs.append(h6_q2)
        assert h6.matrix_mult_count - before == 2
        before = h6.matrix_mult_count
        h6_q1_repeat = h6.apply(q1)
        outputs.append(h6_q1_repeat)
        assert h6.matrix_mult_count - before == 2

        closed_q1 = _closed_form_chebyshev(
            reference,
            reference_diagonal,
            q1,
            window_values[1],
            window_values[2],
        )
        closed_q2 = _closed_form_chebyshev(
            reference,
            reference_diagonal,
            q2,
            window_values[1],
            window_values[2],
        )
        outputs.extend((closed_q1, closed_q2))
        assert _relative_difference(h6_q1, closed_q1) <= 1.0e-10
        assert _relative_difference(h6_q2, closed_q2) <= 1.0e-10
        assert _relative_difference(h6_q1, h6_q1_repeat) <= 1.0e-12
        np.testing.assert_array_equal(q1.getArray(readonly=True), q1_before)
        np.testing.assert_array_equal(q2.getArray(readonly=True), q2_before)

        zero_output = h6.apply(zero)
        outputs.append(zero_output)
        assert zero_output.norm() == 0.0
        audit_after = h6.audit
        assert audit_after["power_matrix_mult_count"] == 20
        assert tuple(audit_after["power_history"]) == power_history
        assert (
            float(audit_after["lambda_power10"]),
            float(audit_after["lambda_hi"]),
            float(audit_after["lambda_lo"]),
        ) == window_values
        assert h6.action.audit["apply_count"] == 8
        assert audit_after["factor_count"] == 0
        assert h6.matrix_mult_count == 28
    finally:
        for output in outputs:
            output.destroy()
        for output in reference_outputs:
            output.destroy()
        q1.destroy()
        q2.destroy()
        zero.destroy()
