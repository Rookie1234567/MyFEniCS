"""Focused T2 contracts for the generic full-space form action."""

from __future__ import annotations

import ast
import inspect

import dolfinx_mpc
import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.fullspace_mpc_action as action_module
from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action


def _fixture(degree: int, with_mpc: bool):
    domain = mesh.create_unit_cube(
        MPI.COMM_SELF,
        2,
        2,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = domain.topology.dim
    owned_cells = int(domain.topology.index_map(tdim).size_local)
    cell_tags = mesh.meshtags(
        domain,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    space = fem.functionspace(
        domain,
        element(
            "N1curl",
            domain.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(space)
    v = ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=cell_tags)
    ufl_form = (
        ufl.inner(ufl.curl(u), ufl.curl(v))
        + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
    ) * dx(1)
    form = fem.form(ufl_form)
    mpc = None
    if with_mpc:
        mpc = dolfinx_mpc.MultiPointConstraint(space)
        owned_rows = int(space.dofmap.index_map.size_local)
        mpc.add_constraint(
            space,
            np.asarray([owned_rows - 1], dtype=np.int32),
            np.asarray([0], dtype=np.int64),
            np.asarray([0.5 + 0.25j], dtype=PETSc.ScalarType),
            np.asarray([0], dtype=np.int32),
            np.asarray([0, 1], dtype=np.int32),
        )
        mpc.finalize()
    return domain, cell_tags, space, ufl_form, form, mpc


def _source(matrix: PETSc.Mat) -> PETSc.Vec:
    source = matrix.createVecRight()
    start, stop = source.getOwnershipRange()
    ids = np.arange(start, stop, dtype=PETSc.IntType)
    values = (1.0 + 0.013 * ids) + 1j * (0.35 - 0.007 * ids)
    source.setValues(ids, np.asarray(values, dtype=PETSc.ScalarType))
    source.assemble()
    return source


@pytest.mark.parametrize("degree", [2, 3])
def test_mpc_action_matches_assembled_oracle_and_repeats(degree: int) -> None:
    domain, _tags, space, ufl_form, form, mpc = _fixture(
        degree, with_mpc=True
    )
    assembled = dolfinx_mpc.assemble_matrix(form, mpc, bcs=[])
    assembled.assemble()
    action = build_fullspace_mpc_form_action(ufl_form, space, mpc=mpc)
    source = _source(assembled)
    expected = assembled.createVecLeft()
    observed = assembled.createVecLeft()
    repeated = assembled.createVecLeft()
    difference = observed.copy()
    try:
        assembled.mult(source, expected)
        action.matrix.mult(source, observed)
        observed.copy(result=repeated)
        action.matrix.mult(source, repeated)
        observed.copy(result=difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        relative = difference.norm() / max(expected.norm(), 1.0e-30)
        assert relative <= 1.0e-12
        assert np.array_equal(
            observed.getArray(readonly=True),
            repeated.getArray(readonly=True),
        )
        for _index in range(10):
            action.matrix.mult(source, repeated)
            assert np.array_equal(
                observed.getArray(readonly=True),
                repeated.getArray(readonly=True),
            )
        audit = action.audit
        assert audit["apply_count"] == 12
        assert audit["mpc_enabled"] is True
        assert audit["slave_row_identity"] is True
        assert audit["phase_application"] == "finalized_floquet_mpc_once"
        assert audit["constraint_nnz_closes"] is True
        assert audit["global_matrix_materialized"] is False
        assert audit["global_constraint_matrix_materialized"] is False
        assert audit["global_condensed_schur_materialized"] is False
        assert audit["cell_schur_matrix_materialized"] is False
        assert audit["slab_matrix_materialized"] is False
        assert audit["factor_count"] == 0
        assert audit["ksp_created"] is False
        assert audit["numeric_allgather"] is False
        components = audit["retained_numeric_payload_components"]
        assert components["output_vector_local_storage_bytes"] == (
            audit["local_storage_entries"] * np.dtype(PETSc.ScalarType).itemsize
        )
        assert components["owned_slave_indices_bytes"] == mpc.num_local_slaves * np.dtype(
            np.int32
        ).itemsize
        assert sum(components.values()) == audit[
            "retained_numeric_payload_local_bytes"
        ]
        assert audit["retained_numeric_payload_global_sum_bytes"] > 0
        assert audit["retained_numeric_payload_global_max_bytes"] > 0
        assert action.matrix.getType().lower() == "python"
        retained_arrays = [
            value
            for value in action.__dict__.values()
            if isinstance(value, np.ndarray)
        ]
        assert not any(array.ndim >= 2 for array in retained_arrays)
    finally:
        difference.destroy()
        repeated.destroy()
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()
        assembled.destroy()
        assert domain.comm.Get_size() == 1


def test_direct_form_has_the_same_matrix_free_contract() -> None:
    domain, _tags, space, ufl_form, form, _mpc = _fixture(2, with_mpc=False)
    assembled = fem_petsc.assemble_matrix(form, bcs=[])
    assembled.assemble()
    action = build_fullspace_mpc_form_action(ufl_form, space)
    source = _source(assembled)
    expected = assembled.createVecLeft()
    observed = assembled.createVecLeft()
    try:
        assembled.mult(source, expected)
        action.matrix.mult(source, observed)
        difference = observed.copy()
        observed.copy(result=difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        assert difference.norm() / max(expected.norm(), 1.0e-30) <= 1.0e-12
        difference.destroy()
        assert action.audit["mpc_enabled"] is False
        assert action.audit["constraint_count"] == 0
    finally:
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()
        assembled.destroy()
        assert domain.comm.Get_size() == 1


def test_complex_mpc_action_matches_ufl_adjoint_identity() -> None:
    domain, _tags, space, ufl_form, _form, mpc = _fixture(
        2, with_mpc=True
    )
    adjoint_ufl_form = ufl.adjoint(ufl_form)
    forward = build_fullspace_mpc_form_action(ufl_form, space, mpc=mpc)
    adjoint = build_fullspace_mpc_form_action(
        adjoint_ufl_form, space, mpc=mpc
    )
    x = _source(forward.matrix)
    y = _source(forward.matrix)
    forward_result = forward.matrix.createVecLeft()
    adjoint_result = adjoint.matrix.createVecLeft()
    assembled = dolfinx_mpc.assemble_matrix(
        fem.form(ufl_form), mpc, bcs=[]
    )
    assembled_adjoint = dolfinx_mpc.assemble_matrix(
        fem.form(adjoint_ufl_form), mpc, bcs=[]
    )
    assembled.assemble()
    assembled_adjoint.assemble()
    expected_forward = assembled.createVecLeft()
    expected_adjoint = assembled_adjoint.createVecLeft()
    try:
        forward.matrix.mult(x, forward_result)
        adjoint.matrix.mult(y, adjoint_result)
        assembled.mult(x, expected_forward)
        assembled_adjoint.mult(y, expected_adjoint)
        assert np.allclose(
            forward_result.getArray(readonly=True),
            expected_forward.getArray(readonly=True),
            rtol=1.0e-12,
            atol=1.0e-12,
        )
        assert np.allclose(
            adjoint_result.getArray(readonly=True),
            expected_adjoint.getArray(readonly=True),
            rtol=1.0e-12,
            atol=1.0e-12,
        )
        lhs = np.vdot(
            forward_result.getArray(readonly=True),
            y.getArray(readonly=True),
        )
        rhs = np.vdot(
            x.getArray(readonly=True),
            adjoint_result.getArray(readonly=True),
        )
        assert abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1.0e-30) <= 1.0e-12
    finally:
        expected_adjoint.destroy()
        expected_forward.destroy()
        assembled_adjoint.destroy()
        assembled.destroy()
        adjoint_result.destroy()
        forward_result.destroy()
        y.destroy()
        x.destroy()
        adjoint.destroy()
        forward.destroy()
        assert domain.comm.Get_size() == 1


def test_production_module_has_no_matrix_or_dense_cell_builder() -> None:
    source = inspect.getsource(action_module)
    tree = ast.parse(source)
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    }
    assert "createAIJ" not in called_attributes
    assert "assemble_matrix" not in called_attributes
    assert "createPython" in called_attributes


def test_mpc_metadata_row_closure_and_fail_closed_cases() -> None:
    class _Masters:
        def __init__(self, rows):
            self._rows = rows

        def links(self, row):
            return np.asarray(self._rows[int(row)], dtype=np.int32)

    class _Metadata:
        def __init__(self, slaves, offsets, coefficients, is_slave, rows):
            self.slaves = np.asarray(slaves, dtype=np.int32)
            self._offsets = np.asarray(offsets, dtype=np.int64)
            self._coefficients = np.asarray(coefficients, dtype=np.complex128)
            self.is_slave = np.asarray(is_slave, dtype=bool)
            self.masters = _Masters(rows)

        def coefficients(self):
            return self._coefficients, self._offsets

    def prepare(metadata, local_storage):
        action = action_module.FullspaceMpcFormAction.__new__(
            action_module.FullspaceMpcFormAction
        )
        action._owned_rows = 2
        action._prepare_mpc_metadata(metadata, local_storage)
        return action

    imported_master = _Metadata(
        slaves=[0],
        offsets=[0, 1, 1],
        coefficients=[0.5 + 0.25j],
        is_slave=[True, False],
        rows={0: [2]},
    )
    action = prepare(imported_master, local_storage=3)
    assert np.array_equal(action._master_indices, np.asarray([2], dtype=np.int32))

    with pytest.raises(RuntimeError, match="coefficient row metadata"):
        prepare(
            _Metadata(
                slaves=[0], offsets=[0], coefficients=[], is_slave=[], rows={0: []}
            ),
            local_storage=2,
        )
    with pytest.raises(RuntimeError, match="local storage"):
        prepare(
            _Metadata(
                slaves=[2], offsets=[0, 0, 0, 0], coefficients=[],
                is_slave=[False, False, False], rows={2: []}
            ),
            local_storage=2,
        )
    with pytest.raises(NotImplementedError, match="chained MPC"):
        prepare(
            _Metadata(
                slaves=[0], offsets=[0, 1, 1], coefficients=[1.0],
                is_slave=[False, True], rows={0: [1]}
            ),
            local_storage=2,
        )
