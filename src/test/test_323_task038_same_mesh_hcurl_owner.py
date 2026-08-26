"""C1.1 small same-mesh N1E owner/Floquet transfer qualification."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import (
    _mark_boundary_facets,
    _mark_cells,
    _stage4_axis_plan,
    _structured_hexa_mesh,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg import (
    build_same_mesh_hcurl_transfer,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
    OWNER_RUNTIME_SCHEMA,
    _resolve_owner_candidates,
    build_same_mesh_hcurl_owner_transfer,
    explicit_owner_adjoint_audit_only,
)


def _context(comm: MPI.Comm):
    cfg3 = target_stage4_config(degree=3, h_nm=50.0)
    plan = _stage4_axis_plan(cfg3, comm.size)
    mesh = _structured_hexa_mesh(
        comm,
        plan.x_values,
        plan.y_values,
        plan.z_values,
        preserve_input_partition=cfg3.stage4_preserve_structured_input_partition,
    )
    facet_tags, _ = _mark_boundary_facets(mesh, cfg3)
    cell_tags = _mark_cells(mesh, cfg3)
    mesh_data = SimpleNamespace(
        mesh=mesh,
        cell_tags=cell_tags,
        facet_tags=facet_tags,
    )

    def make_space(degree: int):
        return fem.functionspace(
            mesh,
            element(
                "N1curl",
                mesh.basix_cell(),
                degree,
                dtype=default_real_type,
            ),
        )

    v3 = make_space(3)
    v1 = make_space(1)
    floquet3 = build_double_floquet_mpc(v3, mesh_data, cfg3)
    cfg1 = target_stage4_config(degree=1, h_nm=50.0)
    floquet1 = build_double_floquet_mpc(v1, mesh_data, cfg1)
    local = build_same_mesh_hcurl_transfer(3, 1)
    owner = build_same_mesh_hcurl_owner_transfer(
        v3, floquet3, v1, floquet1, local_transfer=local
    )
    return mesh, v3, floquet3, v1, floquet1, local, owner


@pytest.fixture(scope="module")
def context():
    values = _context(MPI.COMM_WORLD)
    try:
        yield values
    finally:
        values[-1].destroy()
        del values


def _field(space, floquet, scale: complex = 1.0):
    field = fem.Function(space)
    field.interpolate(
        lambda x: scale
        * np.vstack(
            (
                x[0] + 1j * (1.0 + x[1]),
                2.0 * x[1] + 1j * (2.0 + x[2]),
                -x[2] + 1j * (3.0 + x[0]),
            )
        )
    )
    floquet.mpc.homogenize(field)
    field.x.scatter_forward()
    floquet.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _dual_field(space, floquet, scale: complex = 1.0):
    field = fem.Function(space)
    field.interpolate(
        lambda x: scale
        * np.vstack(
            (
                x[0] + 1j * (1.0 + x[1]),
                2.0 * x[1] + 1j * (2.0 + x[2]),
                -x[2] + 1j * (3.0 + x[0]),
            )
        )
    )
    floquet.mpc.homogenize(field)
    field.x.scatter_forward()
    return field


def _reduce_dual_field(field, floquet):
    """Test-only independent C^H reduction matching the MPC metadata."""

    mpc = floquet.mpc
    values = field.x.array
    raw = values.copy()
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    for slave in np.asarray(mpc.slaves, dtype=np.int64):
        start = int(offsets[slave])
        stop = int(offsets[slave + 1])
        masters = np.asarray(mpc.masters.links(int(slave)), dtype=np.int64)
        values[masters] += np.conjugate(coefficients[start:stop]) * raw[slave]
    values[np.asarray(mpc.slaves, dtype=np.int64)] = 0.0
    field.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    field.x.scatter_forward()


def _scalar_relative(left: complex, right: complex) -> float:
    return float(
        abs(left - right)
        / max(abs(left), abs(right), np.finfo(np.float64).tiny)
    )


def _slave_max(field, floquet) -> float:
    slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
    local = (
        float(np.max(np.abs(field.x.array[slaves]))) if slaves.size else 0.0
    )
    return float(field.function_space.mesh.comm.allreduce(local, op=MPI.MAX))


def _relative(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    result = float(
        difference.norm() / max(right.norm(), np.finfo(np.float64).tiny)
    )
    difference.destroy()
    return result


def _explicit_oracle(space_fine, space_coarse, local_transfer):
    """Test-only sparse row oracle; it is destroyed after the action checks."""

    comm = space_fine.mesh.comm
    fine_map = space_fine.dofmap.index_map
    coarse_map = space_coarse.dofmap.index_map
    fine_ranges = tuple(comm.allgather(tuple(int(x) for x in fine_map.local_range)))
    stops = np.asarray([item[1] for item in fine_ranges], dtype=np.int64)
    topology = space_fine.mesh.topology
    topology.create_entity_permutations()
    infos = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    cell_map = topology.index_map(topology.dim)
    cells = int(cell_map.size_local + cell_map.num_ghosts)
    authority: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for cell in range(cells):
        info = int(infos[cell])
        local = build_same_mesh_hcurl_transfer(
            3, 1, coarse_cell_info=info, fine_cell_info=info
        )
        fine_local = np.asarray(
            space_fine.dofmap.cell_dofs(cell), dtype=np.int32
        )
        coarse_global = np.asarray(
            coarse_map.local_to_global(
                np.asarray(space_coarse.dofmap.cell_dofs(cell), dtype=np.int32)
            ),
            dtype=np.int64,
        )
        fine_global = np.asarray(
            fine_map.local_to_global(fine_local), dtype=np.int64
        )
        owners = np.searchsorted(stops, fine_global, side="right")
        for position, gid in enumerate(fine_global):
            if int(owners[position]) == int(comm.rank):
                authority.setdefault(
                    int(gid), (coarse_global.copy(), local.matrix[position].copy())
                )
    matrix = PETSc.Mat().createAIJ(
        size=(
            (int(fine_map.size_local), int(fine_map.size_global)),
            (int(coarse_map.size_local), int(coarse_map.size_global)),
        ),
        nnz=12,
        comm=comm,
    )
    for row, (columns, values) in authority.items():
        matrix.setValues(
            row,
            np.asarray(columns, dtype=PETSc.IntType),
            np.asarray(values, dtype=PETSc.ScalarType),
        )
    matrix.assemble()
    return matrix


def test_owner_setup_and_explicit_oracle(context):
    mesh, v3, f3, v1, f1, _local, owner = context
    audit = owner.audit
    assert audit["schema"] == OWNER_RUNTIME_SCHEMA
    assert audit["pair_fine_to_coarse"] == [3, 1]
    assert audit["fine_lagrange_variant"] == "legendre"
    assert audit["coarse_lagrange_variant"] == "legendre"
    assert audit["fine_global_rows"] == int(v3.dofmap.index_map.size_global)
    assert audit["coarse_global_rows"] == int(v1.dofmap.index_map.size_global)
    for floquet, field_audit_key, expected in (
        (f3, "fine_mpc_slave_count_global", 480),
        (f1, "coarse_mpc_slave_count_global", 60),
    ):
        index_map = floquet.mpc.function_space.dofmap.index_map
        owned_scalar_size = int(index_map.size_local) * int(
            floquet.mpc.function_space.dofmap.index_map_bs
        )
        slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
        owned_count = int(
            np.count_nonzero(
                (slaves >= 0) & (slaves < owned_scalar_size)
            )
        )
        global_owned_count = int(
            MPI.COMM_WORLD.allreduce(owned_count, op=MPI.SUM)
        )
        assert audit[field_audit_key] == global_owned_count == expected
    assert audit["global_transfer_matrix"] is False
    assert audit["numeric_allgather"] is False
    assert audit["static_condensation"] is False
    assert audit["physical"] is False
    assert audit["pde"] is False
    assert audit["ksp_created"] is False
    assert audit["vcycle_created"] is False
    assert audit["owner_local"] is True
    assert audit["owner_ghost_identity"] is True
    assert audit["nontrivial_cell_permutation_present_global"] is True
    assert len(audit["canonical_global_digest"]) == 64

    source = _field(v1, f1)
    before = source.x.array.copy()
    output = owner.apply_primal(source.x.petsc_vec)
    repeated = owner.apply_primal(source.x.petsc_vec)
    assert np.array_equal(source.x.array, before)
    assert _relative(output, repeated) == 0.0
    assert np.all(np.isfinite(output.getArray(readonly=True)))
    assert owner.last_apply_facts["shared_row_max_defect"] <= 1.0e-11
    assert owner.last_apply_facts["fine_mpc_constraint_residual"] <= 1.0e-11

    interpolation_oracle = fem.Function(v3)
    interpolation_oracle.interpolate(source)
    f3.mpc.homogenize(interpolation_oracle)
    interpolation_oracle.x.scatter_forward()
    f3.mpc.backsubstitution(interpolation_oracle)
    interpolation_oracle.x.scatter_forward()
    assert _relative(output, interpolation_oracle.x.petsc_vec) <= 1.0e-11

    oracle = _explicit_oracle(v3, v1, _local)
    oracle_output = oracle.createVecLeft()
    oracle.mult(source.x.petsc_vec, oracle_output)
    oracle_field = fem.Function(v3)
    oracle_output.copy(oracle_field.x.petsc_vec)
    oracle_field.x.scatter_forward()
    f3.mpc.homogenize(oracle_field)
    oracle_field.x.scatter_forward()
    f3.mpc.backsubstitution(oracle_field)
    oracle_field.x.scatter_forward()
    assert _relative(output, oracle_field.x.petsc_vec) <= 1.0e-11

    fine_source = _dual_field(v3, f3, 1.0 + 0.25j)
    assert _slave_max(fine_source, f3) == 0.0
    adjoint = owner.apply_adjoint(fine_source.x.petsc_vec)
    adjoint_repeat = owner.apply_adjoint(fine_source.x.petsc_vec)
    assert _relative(adjoint, adjoint_repeat) == 0.0
    assert np.all(np.isfinite(adjoint.getArray(readonly=True)))
    assert owner.last_apply_facts["coarse_dual_reduction"] == "C^H_once"
    assert owner.last_apply_facts["coarse_slave_storage_max"] == 0.0
    assert (
        owner.last_apply_facts["phase_application"]
        == "fine_dual_homogenize_then_coarse_C^H_once"
    )
    lhs = output.dot(fine_source.x.petsc_vec)
    rhs = source.x.petsc_vec.dot(adjoint)
    global_work_relative = _scalar_relative(lhs, rhs)
    assert global_work_relative <= 1.0e-11
    oracle_adjoint = oracle.createVecRight()
    oracle.multHermitian(fine_source.x.petsc_vec, oracle_adjoint)
    oracle_adjoint_field = fem.Function(v1)
    oracle_adjoint.copy(oracle_adjoint_field.x.petsc_vec)
    _reduce_dual_field(oracle_adjoint_field, f1)
    oracle_adjoint_relative = _relative(
        adjoint, oracle_adjoint_field.x.petsc_vec
    )
    assert oracle_adjoint_relative <= 1.0e-11
    audit_adjoint = explicit_owner_adjoint_audit_only(owner, fine_source.x.petsc_vec)
    assert _relative(adjoint, audit_adjoint) <= 1.0e-11

    alpha = 0.37 - 0.19j
    beta = -0.23 + 0.41j
    second = _field(v1, f1, 0.5 - 0.75j)
    combo = source.x.petsc_vec.copy()
    combo.scale(alpha)
    combo.axpy(beta, second.x.petsc_vec)
    combo_output = owner.apply_primal(combo)
    alpha_output = owner.apply_primal(source.x.petsc_vec)
    beta_output = owner.apply_primal(second.x.petsc_vec)
    expected = alpha_output.copy()
    expected.scale(alpha)
    expected.axpy(beta, beta_output)
    assert _relative(combo_output, expected) <= 1.0e-11

    expected.destroy()
    combo_output.destroy()
    alpha_output.destroy()
    beta_output.destroy()
    combo.destroy()
    adjoint.destroy()
    adjoint_repeat.destroy()
    oracle_adjoint.destroy()
    audit_adjoint.destroy()
    repeated.destroy()
    output.destroy()
    oracle_output.destroy()
    oracle.destroy()
    del (
        oracle_adjoint_field,
        oracle_field,
        interpolation_oracle,
        fine_source,
        second,
        source,
    )


def test_owner_rejects_duplicate_disagreement_and_destroy_is_bounded(context):
    _mesh, _v3, _f3, _v1, _f1, _local, owner = context
    with pytest.raises(RuntimeError, match="candidates disagree"):
        _resolve_owner_candidates(
            np.asarray([0, 0], dtype=np.uint64),
            np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
            np.asarray([0, 0], dtype=np.int32),
            0,
            MPI.COMM_SELF,
        )
    owner.destroy()
    owner.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        owner.apply_primal(None)


def test_owner_rejects_p6_to_p3_until_bounded_runtime_exists():
    def fake_space(degree):
        return SimpleNamespace(
            element=SimpleNamespace(
                basix_element=SimpleNamespace(degree=degree)
            )
        )

    with pytest.raises(ValueError, match="unsupported"):
        build_same_mesh_hcurl_owner_transfer(
            fake_space(6), None, fake_space(3), None
        )


def test_runtime_source_is_owner_packet_only():
    from pathlib import Path

    source = Path(
        "src/solvers/fullspace_same_mesh_hcurl_pmg_runtime.py"
    ).read_text()
    assert "createAIJ" not in source
    assert "allgather" in source
    assert "Alltoallv" in source
    assert "global_transfer_matrix" in source
    assert "numeric_allgather" in source
