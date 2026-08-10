from __future__ import annotations

import numpy as np
import pytest
import ufl
import dolfinx_mpc
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.mpc_form_action import MpcFormActionContext
from src.solvers.hcurl_rank_one_mpc_action import (
    build_task037_extra_h1r2_mpc_action,
)
from src.test.test_272_task037_extra_fullspace_mf_mpi import _build_case


_TOLERANCE = 1.0e-11


def _bilinear_form(function_space, cell_tags):
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure(
        "dx", domain=function_space.mesh, subdomain_data=cell_tags
    )
    coefficients = {
        1: (PETSc.ScalarType(1.0 + 0.17j), PETSc.ScalarType(2.1 - 0.3j)),
        2: (PETSc.ScalarType(1.6 - 0.21j), PETSc.ScalarType(0.7 + 0.41j)),
    }
    return sum(
        (
            curl * ufl.inner(ufl.curl(u), ufl.curl(v))
            + mass * ufl.inner(u, v)
        )
        * dx(tag)
        for tag, (curl, mass) in coefficients.items()
    )


def _source(function_space, mpc, variant: int):
    field = fem.Function(function_space)
    if variant == 0:
        field.interpolate(
            lambda x: np.vstack(
                (
                    1.0 + 0.2 * x[0] - 0.11 * x[2],
                    -0.4 + 0.13 * x[1] + 0.07 * x[2],
                    0.25 + 0.09 * x[0] - 0.17 * x[1],
                )
            ).astype(np.complex128)
        )
    else:
        field.interpolate(
            lambda x: np.vstack(
                (
                    -0.7 + 0.17 * x[0] + 0.08 * x[1],
                    0.6 - 0.19 * x[1] + 0.05 * x[2],
                    -0.2 + 0.11 * x[0] + 0.14 * x[2],
                )
            ).astype(np.complex128)
        )
    field.x.scatter_forward()
    index_map = mpc.function_space.dofmap.index_map
    source = create_vector(
        [(index_map, mpc.function_space.dofmap.index_map_bs)]
    )
    owned = int(index_map.size_local)
    with source.localForm() as local:
        local.set(0.0)
        local.array_w[:owned] = field.x.array[:owned]
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    mpc.backsubstitution(source)
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return source


def _relative(first: PETSc.Vec, second: PETSc.Vec) -> float:
    difference = second.duplicate()
    try:
        first.copy(result=difference)
        difference.axpy(PETSc.ScalarType(-1.0), second)
        return float(
            difference.norm()
            / max(float(second.norm()), np.finfo(float).tiny)
        )
    finally:
        difference.destroy()


def _run_case(
    degree: int, *, full_checks: bool, comm=None
) -> dict[str, object]:
    if comm is None:
        comm = MPI.COMM_SELF
    cfg, mesh_data, function_space, cell_tags, tags, floquet, _ = _build_case(
        degree, comm
    )
    del cfg
    bilinear = _bilinear_form(function_space, cell_tags)
    compiled = fem.form(bilinear)
    assembled = dolfinx_mpc.assemble_matrix(
        compiled, floquet.mpc, diagval=PETSc.ScalarType(1.0)
    )
    assembled.assemble()
    reference = MpcFormActionContext(
        bilinear, floquet.mpc, reference=assembled
    )
    candidate = build_task037_extra_h1r2_mpc_action(
        bilinear, floquet.mpc, task037_extra_h1r2=True
    )
    sources = [_source(function_space, floquet.mpc, variant) for variant in (0, 1)]
    candidate_owned_outputs = []
    reference_errors = []
    candidate_errors = []
    finite_local = True
    deterministic_local = True
    try:
        global_tags = set().union(
            *comm.allgather({int(tag) for tag in tags})
        )
        assert global_tags == {1, 2}
        assert abs(complex(floquet.phase_x) - 1.0) > 1.0e-12
        assert abs(complex(floquet.phase_y) - 1.0) > 1.0e-12
        assert comm.allreduce(
            int(floquet.num_edge_constraints) > 0, op=MPI.LOR
        )
        assert comm.allreduce(
            int(floquet.num_face_constraints) > 0, op=MPI.LOR
        )
        for source in sources:
            source_before = np.array(
                source.getArray(readonly=True), copy=True
            )
            expected = assembled.createVecLeft()
            reference_output = assembled.createVecLeft()
            observed = assembled.createVecLeft()
            repeated = assembled.createVecLeft()
            try:
                assembled.mult(source, expected)
                reference.mult(None, source, reference_output)
                candidate.mult(source).copy(result=observed)
                candidate.mult(source).copy(result=repeated)
                reference_error = _relative(reference_output, expected)
                candidate_error = _relative(observed, expected)
                reference_errors.append(reference_error)
                candidate_errors.append(candidate_error)
                assert reference_error <= _TOLERANCE
                assert candidate_error <= _TOLERANCE
                repeated_equal = np.array_equal(
                    observed.getArray(readonly=True),
                    repeated.getArray(readonly=True),
                )
                assert repeated_equal
                deterministic_local = deterministic_local and repeated_equal
                finite_local = finite_local and bool(
                    np.all(np.isfinite(reference_output.getArray(readonly=True)))
                    and np.all(np.isfinite(observed.getArray(readonly=True)))
                )
                assert np.all(np.isfinite(observed.getArray(readonly=True)))
                candidate_owned_outputs.append(
                    np.array(observed.getArray(readonly=True), copy=True)
                )
                assert np.array_equal(
                    source.getArray(readonly=True), source_before
                )
                owned = int(floquet.mpc.function_space.dofmap.index_map.size_local)
                owned_slaves = np.asarray(floquet.mpc.slaves, dtype=np.int32)
                owned_slaves = owned_slaves[owned_slaves < owned]
                np.testing.assert_array_equal(
                    observed.getArray(readonly=True)[owned_slaves],
                    source_before[owned_slaves],
                )
            finally:
                repeated.destroy()
                observed.destroy()
                reference_output.destroy()
                expected.destroy()

        audit = candidate.audit
        components = dict(audit["retained_numeric_payload_components"])
        assert audit["backend"].startswith("dolfinx.fem.assemble_vector")
        assert audit["form_rank"] == 1
        assert audit["coefficient_count"] == 1
        assert audit["constraint_nnz_closes"] is True
        assert audit["constraint_work_retained"] is True
        assert audit["constraint_work_bytes"] == (
            audit["constraint_nnz"] * np.dtype(np.complex128).itemsize
        )
        assert audit["owned_slave_work_retained"] is True
        assert audit["owned_slave_work_bytes"] == (
            audit["owned_constraint_count"]
            * np.dtype(np.complex128).itemsize
        )
        assert audit["constraint_count"] == int(floquet.num_constraints)
        assert audit["constraint_nnz"] == sum(
            len(floquet.mpc.masters.links(int(slave)))
            for slave in np.asarray(floquet.mpc.slaves, dtype=np.int32)
        )
        assert audit["local_storage_entries"] == (
            audit["local_owned_rows"] + audit["local_ghost_rows"]
        )
        index_map = floquet.mpc.function_space.dofmap.index_map
        assert audit["global_rows"] == int(index_map.size_global)
        assert audit["local_owned_rows"] == int(index_map.size_local)
        assert audit["local_ghost_rows"] == int(index_map.num_ghosts)
        assert comm.allreduce(
            int(audit["local_owned_rows"]), op=MPI.SUM
        ) == audit["global_rows"]
        local_payload = int(audit["retained_numeric_payload_local_bytes"])
        assert local_payload == sum(
            components.values()
        )
        assert audit["retained_numeric_payload_global_sum_bytes"] == comm.allreduce(
            local_payload, op=MPI.SUM
        )
        assert audit["retained_numeric_payload_global_max_bytes"] == comm.allreduce(
            local_payload, op=MPI.MAX
        )
        assert local_payload <= audit["retained_numeric_payload_global_max_bytes"]
        assert audit["retained_numeric_payload_global_max_bytes"] <= audit[
            "retained_numeric_payload_global_sum_bytes"
        ]
        assert candidate_owned_outputs[0].shape == candidate_owned_outputs[1].shape
        assert not np.array_equal(
            candidate_owned_outputs[0], candidate_owned_outputs[1]
        )
        assert candidate._flat_slave_indices.size == audit["constraint_nnz"]
        assert candidate._master_indices.size == audit["constraint_nnz"]
        assert (
            candidate._conjugated_master_coefficients.size
            == audit["constraint_nnz"]
        )
        assert candidate._constraint_work.size == audit["constraint_nnz"]
        assert candidate._owned_slave_work.size == audit["owned_constraint_count"]
        assert audit["owned_slave_work_bytes"] == candidate._owned_slave_work.nbytes
        assert "slave_offsets_bytes" not in components
        assert "master_coefficients_bytes" not in components
        shapes = audit["last_packed_coefficient_shapes"]
        entries = int(audit["last_packed_coefficient_entry_count"])
        assert sum(int(np.prod(shape)) for shape in shapes) == entries
        assert entries * np.dtype(np.complex128).itemsize == audit[
            "last_packed_coefficient_bytes"
        ]
        assert audit["last_packed_coefficient_bytes"] == audit[
            "per_apply_bounded_temporary_bytes"
        ]
        assert audit["apply_count"] == 4
        assert audit["global_matrix_materialized"] is False
        assert audit["global_constraint_matrix_materialized"] is False
        assert audit["global_condensed_schur_materialized"] is False
        assert audit["retained_dense_cell_tensor_count"] == 0
        assert audit["dense_cell_tensor_materialized_per_apply"] is False
        assert audit["cell_metadata_retained"] is False
        assert audit["cell_schur_matrix_nnz"] == 0
        assert audit["slab_matrix_nnz"] == 0
        assert audit["cell_schur_matrix_materialized"] is False
        assert audit["slab_matrix_materialized"] is False
        assert audit["factor_count"] == 0
        assert audit["ksp_created"] is False
        assert audit["dtn_used"] is False
        assert audit["ordinary_default_changed"] is False
        assert not any(
            isinstance(value, np.ndarray) and value.ndim >= 2
            for value in vars(candidate).values()
        )
        assert not any(
            name.startswith("_cell") for name in vars(candidate)
        )
        cell_infos = np.asarray(
            mesh_data.mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        owned_cell_count = int(mesh_data.mesh.topology.index_map(3).size_local)
        global_permutation_values = sorted(
            {
                int(value)
                for rank_values in comm.allgather(
                    [int(value) for value in cell_infos[:owned_cell_count]]
                )
                for value in rank_values
            }
        )
        local_payload = int(audit["retained_numeric_payload_local_bytes"])
        global_payload_sum = int(
            audit["retained_numeric_payload_global_sum_bytes"]
        )
        global_payload_max = int(
            audit["retained_numeric_payload_global_max_bytes"]
        )
        global_rows = int(audit["global_rows"])
        reference_error_max = float(
            comm.allreduce(max(reference_errors), op=MPI.MAX)
        )
        candidate_error_max = float(
            comm.allreduce(max(candidate_errors), op=MPI.MAX)
        )
        owned_constraints_global = int(
            comm.allreduce(
                int(audit["owned_constraint_count"]), op=MPI.SUM
            )
        )
        assert (
            owned_constraints_global
            == audit["constraint_count"]
            == int(floquet.num_constraints)
        )
        finite = bool(comm.allreduce(finite_local, op=MPI.LAND))
        deterministic = bool(comm.allreduce(deterministic_local, op=MPI.LAND))
        if full_checks:
            assert np.all(np.isfinite(candidate.output_vector.getArray()))
        if comm.size == 2 and comm.rank == 0:
            print(
                {
                    "h1r2_mpi2_smoke": {
                        "degree": degree,
                        "assembled_reference_relative_error": reference_error_max,
                        "candidate_relative_error": candidate_error_max,
                        "finite": finite,
                        "deterministic": deterministic,
                        "phase_x": complex(floquet.phase_x),
                        "phase_y": complex(floquet.phase_y),
                        "global_material_tags": sorted(global_tags),
                        "global_permutation_unique_values": global_permutation_values,
                        "edge_constraints": int(floquet.num_edge_constraints),
                        "face_constraints": int(floquet.num_face_constraints),
                        "global_constraints": int(floquet.num_constraints),
                        "audit_global_rows": global_rows,
                        "audit_local_owned_rows_rank0": int(
                            audit["local_owned_rows"]
                        ),
                        "audit_local_ghost_rows_rank0": int(
                            audit["local_ghost_rows"]
                        ),
                        "audit_owned_constraints_global": int(
                            owned_constraints_global
                        ),
                        "payload_local_rank0_bytes": local_payload,
                        "payload_global_sum_bytes": global_payload_sum,
                        "payload_global_max_bytes": global_payload_max,
                        "inventory": {
                            key: audit[key]
                            for key in (
                                "global_matrix_materialized",
                                "global_constraint_matrix_materialized",
                                "global_condensed_schur_materialized",
                                "retained_dense_cell_tensor_count",
                                "cell_schur_matrix_nnz",
                                "slab_matrix_nnz",
                                "factor_count",
                                "ksp_created",
                                "dtn_used",
                            )
                        },
                    }
                }
            )
        return {
            "degree": degree,
            "global_rows": global_rows,
            "constraints": int(audit["constraint_count"]),
        }
    finally:
        for source in sources:
            source.destroy()
        candidate.destroy()
        reference.destroy(None)
        assembled.destroy()


def test_h1r2_mpc_rank_one_p2_minimal_case():
    result = _run_case(2, full_checks=False)
    assert result["degree"] == 2


def test_h1r2_mpc_rank_one_p2_mpi2_world_smoke():
    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("MPI2 smoke is qualified only for COMM_WORLD size 2")
    result = _run_case(2, full_checks=True, comm=comm)
    assert result["degree"] == 2
    assert result["global_rows"] > 0
    assert result["constraints"] > 0


@pytest.mark.parametrize("degree", (2, 3))
def test_h1r2_mpc_rank_one_p2_p3_full_fixture(degree: int):
    result = _run_case(degree, full_checks=True)
    assert result["constraints"] > 0
