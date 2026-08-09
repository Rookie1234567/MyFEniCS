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


def _run_case(degree: int, *, full_checks: bool) -> dict[str, float | int]:
    comm = MPI.COMM_SELF
    cfg, mesh_data, function_space, cell_tags, tags, floquet, _ = _build_case(
        degree, comm
    )
    del cfg, mesh_data
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
    try:
        assert {int(tag) for tag in tags} == {1, 2}
        assert abs(complex(floquet.phase_x) - 1.0) > 1.0e-12
        assert abs(complex(floquet.phase_y) - 1.0) > 1.0e-12
        assert int(floquet.num_edge_constraints) > 0
        assert int(floquet.num_face_constraints) > 0
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
                assert _relative(reference_output, expected) <= _TOLERANCE
                assert _relative(observed, expected) <= _TOLERANCE
                assert np.array_equal(
                    observed.getArray(readonly=True),
                    repeated.getArray(readonly=True),
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
        assert audit["global_rows"] == audit["local_owned_rows"]
        assert audit["retained_numeric_payload_local_bytes"] == sum(
            components.values()
        )
        assert audit["retained_numeric_payload_global_sum_bytes"] == audit[
            "retained_numeric_payload_local_bytes"
        ]
        assert audit["retained_numeric_payload_global_max_bytes"] == audit[
            "retained_numeric_payload_local_bytes"
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
        if full_checks:
            assert np.all(np.isfinite(candidate.output_vector.getArray()))
        return {
            "degree": degree,
            "global_rows": int(audit["global_rows"]),
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


@pytest.mark.parametrize("degree", (2, 3))
def test_h1r2_mpc_rank_one_p2_p3_full_fixture(degree: int):
    result = _run_case(degree, full_checks=True)
    assert result["constraints"] > 0
