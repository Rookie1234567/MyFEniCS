from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_assembly_time_condensation import (
    _owned_trace_numbering,
    _trace_constraint_map,
)
from src.solvers.static_trace_auxiliary import (
    build_p2_to_p6_active_trace_transfer,
)
from src.solvers.hcurl_canonical_vector import compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_full_fe_packets,
)
from src.test.test_46_task033_high_order_floquet_topology import (
    _fixed_target_fixture,
)


def _spaces(comm, nx=2, ny=2, nz=2):
    mesh_3d = mesh.create_unit_cube(
        comm,
        nx,
        ny,
        nz,
        cell_type=mesh.CellType.hexahedron,
    )
    spaces = []
    for degree in (2, 6):
        V = fem.functionspace(
            mesh_3d,
            element(
                "N1curl",
                mesh_3d.basix_cell(),
                degree,
                dtype=default_real_type,
            ),
        )
        spaces.append(V)
    return mesh_3d, spaces, [_constraint_map(V) for V in spaces]


def _constraint_map(space, mpc=None):
    interior_positions = np.asarray(
        space.element.basix_element.entity_dofs[3][0], dtype=np.int32
    )
    owned_cells = int(space.mesh.topology.index_map(space.mesh.topology.dim).size_local)
    local_interiors = tuple(
        np.asarray(
            space.dofmap.index_map.local_to_global(
                np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
            ),
            dtype=PETSc.IntType,
        )[interior_positions]
        for cell in range(owned_cells)
    )
    owned_trace, mapping, trace_rows, _full_rows = _owned_trace_numbering(
        space, local_interiors
    )
    return _trace_constraint_map(
        space,
        owned_trace,
        mapping,
        trace_rows,
        mpc,
    )


def _probe(vector, seed, *, random=False):
    first, last = map(int, vector.getOwnershipRange())
    ids = np.arange(first, last, dtype=np.float64)
    if random:
        generator = np.random.default_rng(seed)
        values = generator.standard_normal(
            last - first
        ) + 1j * generator.standard_normal(last - first)
        values /= max(float(np.max(np.abs(values), initial=0.0)), 1.0)
    else:
        values = np.sin((seed + 1.0) * 0.17 + 0.13 * ids) + 1j * np.cos(
            (seed + 2.0) * 0.11 - 0.09 * ids
        )
    vector.getArray()[:] = values
    vector.assemble()


# Analytic gradient of the Q2 scalar polynomial x0^2 + 2*x1*x2 + x0*x1.
def _gradient(x):
    return np.vstack((2.0 * x[0] + x[1], 2.0 * x[2], 2.0 * x[1]))


def _active_vector(space, constraints):
    comm = space.mesh.comm
    return PETSc.Vec().createMPI(
        (len(constraints.owned_active_original_dofs), int(constraints.active_rows)),
        comm=comm,
    )


def _global_owned_values(vector):
    first, last = map(int, vector.getOwnershipRange())
    local = {
        first + offset: complex(value)
        for offset, value in enumerate(vector.getArray(readonly=True))
    }
    merged = {}
    for packet in vector.getComm().tompi4py().allgather(local):
        if set(merged).intersection(packet):
            raise AssertionError("owned vector packets overlap")
        merged.update(packet)
    return merged


def _field_from_active(space, constraints, active):
    values = _global_owned_values(active)
    field = fem.Function(space)
    local_count = int(space.dofmap.index_map.size_local)
    local_global = space.dofmap.index_map.local_to_global(
        np.arange(local_count, dtype=np.int32)
    )
    for local, original in enumerate(local_global):
        block = constraints.expansion_by_original.get(int(original))
        if block is not None:
            active_ids, coefficients = block
            field.x.array[local] = sum(
                coefficient * values[int(active_id)]
                for active_id, coefficient in zip(active_ids, coefficients, strict=True)
            )
    field.x.scatter_forward()
    return field


def _active_from_field(space, constraints, field):
    active = _active_vector(space, constraints)
    local_count = int(space.dofmap.index_map.size_local)
    local_global = space.dofmap.index_map.local_to_global(
        np.arange(local_count, dtype=np.int32)
    )
    for local, original in enumerate(local_global):
        active_id = constraints.original_to_active.get(int(original))
        if active_id is not None:
            active.setValue(int(active_id), field.x.array[local])
    active.assemble()
    return active


def _oracle_q6(V2, V6, C2, C6, q2):
    p2 = _field_from_active(V2, C2, q2)
    p6 = fem.Function(V6)
    p6.interpolate(p2)
    p6.x.scatter_forward()
    return _active_from_field(V6, C6, p6), p2, p6


def _trace_closure_error(space, constraints, field, active):
    values = _global_owned_values(active)
    trace_positions = np.setdiff1d(
        np.arange(int(space.element.space_dimension), dtype=np.int32),
        np.asarray(space.element.basix_element.entity_dofs[3][0], dtype=np.int32),
    )
    maximum = 0.0
    maximum_reference = 0.0
    for cell in range(int(space.mesh.topology.index_map(3).size_local)):
        local_dofs = np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
        global_dofs = np.asarray(
            space.dofmap.index_map.local_to_global(local_dofs), dtype=np.int64
        )
        for local_position in trace_positions:
            original = int(global_dofs[int(local_position)])
            active_ids, coefficients = constraints.expansion_by_original[original]
            expected = sum(
                coefficient * values[int(active_id)]
                for active_id, coefficient in zip(active_ids, coefficients, strict=True)
            )
            error = abs(field.x.array[int(local_dofs[int(local_position)])] - expected)
            maximum = max(maximum, float(error))
            maximum_reference = max(maximum_reference, float(abs(expected)))
    return maximum, maximum / max(maximum_reference, 1.0e-30)


def _assert_close(left, right, atol=1.0e-11):
    difference = left.copy()
    difference.axpy(PETSc.ScalarType(-1.0), right)
    comm = difference.getComm().tompi4py()
    local_absolute = float(
        np.max(np.abs(difference.getArray(readonly=True)), initial=0.0)
    )
    local_reference = float(np.max(np.abs(right.getArray(readonly=True)), initial=0.0))
    absolute = comm.allreduce(local_absolute, op=MPI.MAX)
    reference = max(comm.allreduce(local_reference, op=MPI.MAX), 1.0e-30)
    two_norm_relative = difference.norm() / max(right.norm(), 1.0e-30)
    difference.destroy()
    assert absolute <= atol
    assert absolute / reference <= atol
    return absolute, absolute / reference, two_norm_relative


def test_serial_owner_local_transfer_closure_adjoint_and_oracle():
    mesh_3d, (V2, V6), (C2, C6) = _spaces(MPI.COMM_SELF)
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    assert transfer.audit["global_transfer_matrix_materialized"] is False
    assert transfer.audit["allgather_active_values"] is False
    assert transfer.audit["cell_info_nonzero_count"] > 0
    assert transfer.audit["trace_interior_dependency_max"] <= 1.0e-12
    assert transfer.audit["owner_local_stencil_nbytes"] > 0
    assert transfer.audit["source_staging_nbytes"] > 0

    max_apply_absolute = 0.0
    max_apply_relative = 0.0
    max_apply_two_norm_relative = 0.0
    max_closure_absolute = 0.0
    max_closure_relative = 0.0
    for seed, random in ((0, False), (1, False), (2, False), (234, True)):
        q2 = _active_vector(V2, C2)
        q6 = _active_vector(V6, C6)
        _probe(q2, seed, random=random)
        transfer.apply(q2, q6)
        oracle, _p2, p6 = _oracle_q6(V2, V6, C2, C6, q2)
        absolute, relative_action, two_norm_relative = _assert_close(q6, oracle)
        max_apply_absolute = max(max_apply_absolute, absolute)
        max_apply_relative = max(max_apply_relative, relative_action)
        max_apply_two_norm_relative = max(
            max_apply_two_norm_relative, two_norm_relative
        )
        maximum, relative = _trace_closure_error(V6, C6, p6, oracle)
        assert maximum <= 1.0e-11
        assert relative <= 1.0e-11
        max_closure_absolute = max(max_closure_absolute, maximum)
        max_closure_relative = max(max_closure_relative, relative)
        oracle.destroy()
        q6.destroy()
        q2.destroy()

    gradient2 = fem.Function(V2)
    gradient6 = fem.Function(V6)
    gradient2.interpolate(_gradient)
    gradient6.interpolate(_gradient)
    gradient2.x.scatter_forward()
    gradient6.x.scatter_forward()
    gradient_q2 = _active_from_field(V2, C2, gradient2)
    gradient_q6 = _active_from_field(V6, C6, gradient6)
    transferred_gradient = _active_vector(V6, C6)
    transfer.apply(gradient_q2, transferred_gradient)
    gradient_absolute, gradient_relative, gradient_two_norm_relative = _assert_close(
        transferred_gradient, gradient_q6
    )
    gradient_q2.destroy()
    gradient_q6.destroy()
    transferred_gradient.destroy()

    q2 = _active_vector(V2, C2)
    q6 = _active_vector(V6, C6)
    q6_image = _active_vector(V6, C6)
    adjoint = _active_vector(V2, C2)
    _probe(q2, 11)
    _probe(q6, 12)
    transfer.apply(q2, q6_image)
    transfer.apply_adjoint(q6, adjoint)
    lhs = q6_image.dot(q6)
    rhs = q2.dot(adjoint)
    adjoint_relative = abs(lhs - rhs) / max(abs(lhs), 1.0)
    assert adjoint_relative <= 1.0e-11
    adjoint.destroy()
    q6_image.destroy()
    q6.destroy()
    q2.destroy()

    n2 = int(C2.active_rows)
    n6 = int(C6.active_rows)
    explicit = np.empty((n6, n2), dtype=np.complex128)
    for column in range(n2):
        basis = _active_vector(V2, C2)
        basis.setValue(column, 1.0)
        basis.assemble()
        image = _active_vector(V6, C6)
        transfer.apply(basis, image)
        explicit[:, column] = image.getArray(readonly=True)
        image.destroy()
        basis.destroy()
    assert np.all(np.linalg.norm(explicit, axis=0) > 0.0)
    assert len({column.tobytes() for column in explicit.T}) == n2
    assert np.linalg.matrix_rank(explicit, tol=1.0e-11) == n2
    zero_p6_rows = int(np.count_nonzero(np.max(np.abs(explicit), axis=1) == 0.0))
    assert zero_p6_rows > 0
    print(
        "M4A_SERIAL_AUDIT",
        {
            "max_apply_absolute": max_apply_absolute,
            "max_apply_relative": max_apply_relative,
            "max_apply_two_norm_relative": max_apply_two_norm_relative,
            "max_full_trace_closure_absolute": max_closure_absolute,
            "max_full_trace_closure_relative": max_closure_relative,
            "gradient_absolute": gradient_absolute,
            "gradient_relative": gradient_relative,
            "gradient_two_norm_relative": gradient_two_norm_relative,
            "adjoint_relative": adjoint_relative,
            "p2_active_rows": n2,
            "p6_active_rows": n6,
            "zero_p6_row_count": zero_p6_rows,
            "global_stencil_nnz": transfer.audit["global_stencil_nnz"],
            "local_stencil_nnz": transfer.audit["local_stencil_nnz"],
            "owner_local_stencil_nbytes": transfer.audit["owner_local_stencil_nbytes"],
            "source_staging_nbytes": transfer.audit["source_staging_nbytes"],
            "communication_index_nbytes": transfer.audit["communication_index_nbytes"],
            "structural_zero_tolerance": transfer.audit["structural_zero_tolerance"],
            "structural_zero_discarded_candidate_count": transfer.audit[
                "structural_zero_discarded_candidate_count"
            ],
            "structural_zero_discarded_candidate_max_abs": transfer.audit[
                "structural_zero_discarded_candidate_max_abs"
            ],
        },
    )
    transfer.destroy()
    transfer.destroy()


def test_serial_floquet_phases_and_nontrivial_orientation():
    cfg, mesh_data, V2 = _fixed_target_fixture(2, h_nm=50.0)
    cfg = replace(cfg, incident_phi_deg=37.0)
    V6 = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    cfg6 = replace(cfg, nedelec_degree=6)
    mpc2_data = build_double_floquet_mpc(V2, mesh_data, cfg)
    mpc6_data = build_double_floquet_mpc(V6, mesh_data, cfg6)
    assert mpc2_data.num_x_constraints > 0
    assert mpc2_data.num_y_constraints > 0
    assert mpc2_data.num_corner_constraints > 0
    assert mpc6_data.num_x_constraints > 0
    assert mpc6_data.num_y_constraints > 0
    assert mpc6_data.num_corner_constraints > 0
    C2 = _constraint_map(V2, mpc2_data.mpc)
    C6 = _constraint_map(V6, mpc6_data.mpc)
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    assert transfer.audit["cell_info_nonzero_count"] > 0
    assert abs(complex(cfg.floquet_phase_x) - 1.0) > 1.0e-8
    assert abs(complex(cfg.floquet_phase_y) - 1.0) > 1.0e-8
    assert abs(complex(cfg.floquet_phase_x * cfg.floquet_phase_y) - 1.0) > 1.0e-8
    q2 = _active_vector(V2, C2)
    q6 = _active_vector(V6, C6)
    _probe(q2, 234)
    transfer.apply(q2, q6)
    oracle, _p2, p6 = _oracle_q6(V2, V6, C2, C6, q2)
    apply_absolute, apply_relative, apply_two_norm_relative = _assert_close(q6, oracle)
    maximum, relative = _trace_closure_error(V6, C6, p6, oracle)
    assert maximum <= 1.0e-11
    assert relative <= 1.0e-11
    oracle.destroy()
    q6.destroy()
    q2.destroy()
    transfer.destroy()
    print(
        "M4A_FLOQUET_AUDIT",
        {
            "apply_absolute": apply_absolute,
            "apply_relative": apply_relative,
            "apply_two_norm_relative": apply_two_norm_relative,
            "full_trace_closure_absolute": maximum,
            "full_trace_closure_relative": relative,
            "p2_x_constraints": mpc2_data.num_x_constraints,
            "p2_y_constraints": mpc2_data.num_y_constraints,
            "p2_corner_constraints": mpc2_data.num_corner_constraints,
            "p6_x_constraints": mpc6_data.num_x_constraints,
            "p6_y_constraints": mpc6_data.num_y_constraints,
            "p6_corner_constraints": mpc6_data.num_corner_constraints,
        },
    )


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (2, 4), reason="MPI2/MPI4")
def test_mpi_owner_local_transfer_remote_values_and_adjoint():
    _mesh, (V2, V6), (C2, C6) = _spaces(MPI.COMM_WORLD, 2, 2, 2)
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    comm = MPI.COMM_WORLD
    assert comm.allreduce(transfer.audit["remote_coarse_columns_local"], op=MPI.SUM) > 0
    for active_rows in (int(C2.active_rows), int(C6.active_rows)):
        minimum = comm.allreduce(active_rows, op=MPI.MIN)
        maximum = comm.allreduce(active_rows, op=MPI.MAX)
        assert minimum == maximum
    rank_audits = comm.gather(
        {
            key: transfer.audit[key]
            for key in (
                "local_stencil_nnz",
                "owner_local_stencil_nbytes",
                "source_staging_nbytes",
                "communication_index_nbytes",
                "structural_zero_tolerance",
                "structural_zero_discarded_candidate_count",
                "structural_zero_discarded_candidate_max_abs",
            )
        },
        root=0,
    )
    gradient2 = fem.Function(V2)
    gradient6 = fem.Function(V6)
    gradient2.interpolate(_gradient)
    gradient6.interpolate(_gradient)
    gradient2.x.scatter_forward()
    gradient6.x.scatter_forward()
    q2 = _active_from_field(V2, C2, gradient2)
    q6 = _active_vector(V6, C6)
    transfer.apply(q2, q6)
    expected_q6 = _active_from_field(V6, C6, gradient6)
    apply_absolute, apply_relative, apply_two_norm_relative = _assert_close(
        q6, expected_q6
    )
    p6_field = _field_from_active(V6, C6, q6)
    local_closure_absolute, local_closure_relative = _trace_closure_error(
        V6, C6, p6_field, q6
    )
    closure_absolute = comm.allreduce(local_closure_absolute, op=MPI.MAX)
    closure_relative = comm.allreduce(local_closure_relative, op=MPI.MAX)
    assert closure_absolute <= 1.0e-11
    assert closure_relative <= 1.0e-11
    gradient_absolute = apply_absolute
    gradient_relative = apply_relative
    gradient_two_norm_relative = apply_two_norm_relative
    y = _active_vector(V6, C6)
    adjoint = _active_vector(V2, C2)
    _probe(y, 235)
    transfer.apply_adjoint(y, adjoint)
    lhs = q6.dot(y)
    rhs = q2.dot(adjoint)
    adjoint_relative = abs(lhs - rhs) / max(abs(lhs), 1.0)
    assert adjoint_relative <= 1.0e-11

    actual_packets = extract_canonical_full_fe_packets(V6, p6_field.x.petsc_vec, None)[
        0
    ]
    gathered_packets = comm.gather(actual_packets, root=0)
    reference_result = None
    if comm.rank == 0:
        _reference_mesh, (RV2, RV6), (RC2, RC6) = _spaces(MPI.COMM_SELF, 2, 2, 2)
        reference_gradient2 = fem.Function(RV2)
        reference_gradient2.interpolate(_gradient)
        reference_gradient2.x.scatter_forward()
        reference_q2 = _active_from_field(RV2, RC2, reference_gradient2)
        reference_transfer = build_p2_to_p6_active_trace_transfer(RV2, RV6, RC2, RC6)
        reference_q6 = _active_vector(RV6, RC6)
        reference_transfer.apply(reference_q2, reference_q6)
        reference_field = _field_from_active(RV6, RC6, reference_q6)
        reference_packets = extract_canonical_full_fe_packets(
            RV6, reference_field.x.petsc_vec, None
        )[0]
        merged_packets = tuple(packet for part in gathered_packets for packet in part)
        canonical = compare_canonical_packets(
            merged_packets,
            reference_packets,
            relative_tolerance=1.0e-11,
        )
        reference_result = {
            "pass": bool(canonical["pass"]),
            "relative": float(canonical["relative_coefficient_l2"]),
            "max_abs": float(canonical["max_abs_coefficient_error"]),
            "reference_p2_active_rows": int(RC2.active_rows),
            "reference_p6_active_rows": int(RC6.active_rows),
            "reference_global_stencil_nnz": int(
                reference_transfer.audit["global_stencil_nnz"]
            ),
            "reference_cell_info_nonzero_count": int(
                reference_transfer.audit["cell_info_nonzero_count"]
            ),
        }
        reference_transfer.destroy()
        reference_q6.destroy()
        reference_q2.destroy()
    reference_result = comm.bcast(reference_result, root=0)
    if comm.rank == 0:
        print(
            "M4A_MPI_CANONICAL_AUDIT",
            {
                "size": comm.size,
                "candidate_global_stencil_nnz": transfer.audit["global_stencil_nnz"],
                "candidate_rank_ledgers": rank_audits,
                "reference": reference_result,
            },
        )
    assert reference_result["pass"], reference_result
    assert reference_result["max_abs"] <= 1.0e-11
    assert reference_result["relative"] <= 1.0e-11
    assert reference_result["reference_p2_active_rows"] == int(C2.active_rows)
    assert reference_result["reference_p6_active_rows"] == int(C6.active_rows)
    if comm.rank == 0:
        print(
            "M4A_MPI_NUMERICAL_AUDIT",
            {
                "apply_absolute": apply_absolute,
                "apply_relative": apply_relative,
                "apply_two_norm_relative": apply_two_norm_relative,
                "closure_absolute": closure_absolute,
                "closure_relative": closure_relative,
                "gradient_absolute": gradient_absolute,
                "gradient_relative": gradient_relative,
                "gradient_two_norm_relative": gradient_two_norm_relative,
                "adjoint_relative": adjoint_relative,
                **reference_result,
            },
        )
    adjoint.destroy()
    y.destroy()
    expected_q6.destroy()
    q6.destroy()
    q2.destroy()
    transfer.destroy()


def test_rejects_non_p2_coarse_space():
    mesh_3d, (V2, V6), (C2, C6) = _spaces(MPI.COMM_SELF)
    V4 = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            4,
            dtype=default_real_type,
        ),
    )
    with pytest.raises(ValueError, match="requires p2"):
        build_p2_to_p6_active_trace_transfer(V4, V6, C2, C6)
