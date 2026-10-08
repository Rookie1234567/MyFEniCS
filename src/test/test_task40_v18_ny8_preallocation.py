"""Regression coverage for the DOLFINx-MPC native matrix pattern upper bound."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.task40_v18_ny8_operator_qualification import (
    _mpc_cell_pattern_support_upper,
    _owned_array_or_copy,
)


def test_cell_support_upper_distinguishes_replacement_from_backend_union():
    cells = ((0, 1, 2), (3, 4, 5))
    space = SimpleNamespace(
        mesh=SimpleNamespace(
            topology=SimpleNamespace(
                index_map=lambda _dimension: SimpleNamespace(size_local=len(cells))
            )
        ),
        dofmap=SimpleNamespace(cell_dofs=lambda cell: cells[cell]),
    )

    class _Masters:
        @staticmethod
        def links(dof):
            return {3: np.asarray([0, 6], dtype=np.int32)}.get(
                int(dof), np.asarray([], dtype=np.int32)
            )

    mpc = SimpleNamespace(
        slaves=np.asarray([3], dtype=np.int32), masters=_Masters()
    )
    counts = _mpc_cell_pattern_support_upper(space, mpc)

    assert counts["raw_cell_support_pairs_sum"] == 18
    assert counts["constraint_replaced_cell_support_pairs_sum"] == 25
    assert counts["backend_raw_plus_masters_union_pairs_sum"] == 34
    assert counts["maximum_constraint_replaced_cell_dof_count"] == 4
    assert counts["maximum_backend_union_cell_dof_count"] == 5
    assert counts["support_count_workspace_upper_bytes"] == 56


def test_owned_matching_csr_arrays_are_reused_and_views_are_copied():
    owned = np.arange(4, dtype=np.int32)
    assert _owned_array_or_copy(owned, dtype=np.int32) is owned

    backing = np.arange(6, dtype=np.int32)
    view = backing[1:5]
    copied_view = _owned_array_or_copy(view, dtype=np.int32)
    assert copied_view.flags.owndata
    assert not np.shares_memory(copied_view, backing)
    np.testing.assert_array_equal(copied_view, view)

    mismatched = np.arange(4, dtype=np.int64)
    copied_dtype = _owned_array_or_copy(mismatched, dtype=np.int32)
    assert copied_dtype.dtype == np.dtype(np.int32)
    assert copied_dtype.flags.owndata
    assert not np.shares_memory(copied_dtype, mismatched)


def test_p6_native_mpc_allocation_exceeds_old_bound_but_fits_backend_union():
    pytest.importorskip("dolfinx")
    basix_ufl = pytest.importorskip("basix.ufl")
    dolfinx_mpc = pytest.importorskip("dolfinx_mpc")
    ufl = pytest.importorskip("ufl")
    from dolfinx import default_real_type, fem, mesh
    from mpi4py import MPI
    from petsc4py import PETSc

    assert PETSc.ScalarType is np.complex128
    assert np.dtype(PETSc.IntType) == np.dtype(np.int32)
    domain = mesh.create_box(
        MPI.COMM_SELF,
        [np.zeros(3), np.ones(3)],
        [2, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    space = fem.functionspace(
        domain,
        basix_ufl.element(
            "N1curl", domain.basix_cell(), 6, dtype=default_real_type
        ),
    )
    cell0 = tuple(map(int, space.dofmap.cell_dofs(0)))
    cell1 = tuple(map(int, space.dofmap.cell_dofs(1)))
    masters = sorted(set(cell0).difference(cell1))
    slaves = sorted(set(cell1).difference(cell0))
    pair_count = min(200, len(masters), len(slaves))
    assert pair_count == 200
    assert not set(masters[:pair_count]).intersection(cell1)

    unconstrained = dolfinx_mpc.MultiPointConstraint(space)
    unconstrained.finalize()
    constrained = dolfinx_mpc.MultiPointConstraint(space)
    constrained.add_constraint(
        space,
        np.asarray(slaves[:pair_count], dtype=np.int32),
        np.asarray(masters[:pair_count], dtype=np.int64),
        np.full(pair_count, 1.0 + 0.125j, dtype=np.complex128),
        np.zeros(pair_count, dtype=np.int32),
        np.arange(pair_count + 1, dtype=np.int32),
    )
    constrained.finalize()

    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    form = fem.form(
        (
            ufl.inner(ufl.curl(trial), ufl.curl(test))
            + ufl.inner(trial, test)
        )
        * ufl.dx
    )
    storage_rows = int(space.dofmap.index_map.size_local)

    def assembled_inventory(mpc):
        matrix = dolfinx_mpc.cpp.mpc.create_matrix(
            form._cpp_object, mpc._cpp_object, mpc._cpp_object
        )
        try:
            before = dict(matrix.getInfo())
            dolfinx_mpc.assemble_matrix(form, mpc, bcs=[], A=matrix)
            matrix.assemble()
            after = dict(matrix.getInfo())
            return {
                "shape": tuple(map(int, matrix.getSize())),
                "nz_allocated_before": int(before["nz_allocated"]),
                "nz_used_before": int(before["nz_used"]),
                "nz_allocated_after": int(after["nz_allocated"]),
                "nz_used_after": int(after["nz_used"]),
            }
        finally:
            matrix.destroy()

    raw_facts = _mpc_cell_pattern_support_upper(space, unconstrained)
    constrained_facts = _mpc_cell_pattern_support_upper(space, constrained)
    raw_inventory = assembled_inventory(unconstrained)
    constrained_inventory = assembled_inventory(constrained)

    raw_upper = storage_rows + raw_facts["backend_raw_plus_masters_union_pairs_sum"]
    old_upper = (
        storage_rows
        + constrained_facts["constraint_replaced_cell_support_pairs_sum"]
    )
    backend_union_upper = (
        storage_rows
        + constrained_facts["backend_raw_plus_masters_union_pairs_sum"]
    )
    assert raw_inventory["shape"] == (storage_rows, storage_rows)
    assert raw_inventory["nz_allocated_after"] <= raw_upper
    assert raw_inventory["nz_used_after"] <= raw_inventory["nz_allocated_after"]
    assert constrained_inventory["shape"] == (storage_rows, storage_rows)
    assert constrained_inventory["nz_allocated_after"] > old_upper
    assert constrained_inventory["nz_allocated_after"] <= backend_union_upper
    assert constrained_inventory["nz_used_after"] <= constrained_inventory[
        "nz_allocated_after"
    ]
    assert constrained_facts["backend_raw_plus_masters_union_pairs_sum"] > (
        constrained_facts["constraint_replaced_cell_support_pairs_sum"]
    )
