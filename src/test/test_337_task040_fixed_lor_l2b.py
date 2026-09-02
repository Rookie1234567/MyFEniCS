"""Focused active-trace P+ service contract for L2b."""

from itertools import pairwise

import dolfinx_mpc
import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    _cell_trace_expansion,
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hcurl_fixed_lor_cell_bridge import (
    build_fixed_p6_lor_cell_bridge,
)
from src.solvers.hcurl_fixed_lor_trace_service import (
    build_fixed_lor_trace_service,
)


def _make_fixture(comm):
    box = mesh.create_unit_cube(
        comm, 1, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    tdim = box.topology.dim
    owned = int(box.topology.index_map(tdim).size_local)
    tags = mesh.meshtags(
        box,
        tdim,
        np.arange(owned, dtype=np.int32),
        np.ones(owned, dtype=np.int32),
    )
    space = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 6, dtype=default_real_type),
    )
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=box, subdomain_data=tags)
    form = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(1.0 + 0.0j) * ufl.inner(u, v)
        )
        * dx(1)
    )
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    if comm.size == 1:
        interior = space.element.basix_element.entity_dofs[3][0]
        local = np.asarray(space.dofmap.cell_dofs(0), dtype=np.int32)
        global_dofs = np.asarray(
            space.dofmap.index_map.local_to_global(local), dtype=np.int64
        )
        trace = np.setdiff1d(
            np.arange(space.element.space_dimension),
            interior,
            assume_unique=True,
        )
        mpc.add_constraint(
            space,
            np.asarray([global_dofs[trace[-1]]], dtype=np.int32),
            np.asarray([global_dofs[trace[0]]], dtype=np.int64),
            np.asarray([0.35 + 0.2j], dtype=PETSc.ScalarType),
            np.asarray([0], dtype=np.int32),
            np.asarray([0, 1], dtype=np.int32),
        )
    mpc.finalize()
    box.topology.create_entity_permutations()
    condensed = build_unconstrained_assembly_time_condensation(
        form,
        space,
        tags,
        mpc=mpc,
        retain_local_schur_for_matrix_free=True,
        materialize_global_matrix=False,
    )
    bridges = {}
    for class_key in {cell.class_key for cell in condensed.cell_recovery_maps}:
        assert len(class_key) == 5
        tag, wx, wy, wz, cell_info = class_key
        assert int(tag) == 1
        bridges[class_key] = build_fixed_p6_lor_cell_bridge(
            (float(wx), float(wy), float(wz)),
            curl_coefficient=1.0 + 0.0j,
            mass_coefficient=1.0 + 0.0j,
            cell_info=int(cell_info),
        )
    service = build_fixed_lor_trace_service(condensed, bridges)
    try:
        yield {
            "box": box,
            "condensed": condensed,
            "bridges": bridges,
            "service": service,
        }
    finally:
        service.destroy()
        for bridge in bridges.values():
            bridge.destroy()
        condensed.destroy()


@pytest.fixture(scope="module")
def l2b():
    yield from _make_fixture(MPI.COMM_WORLD)


def _new_vector(condensed, factor=1.0):
    vector = condensed.create_active_vector()
    start, stop = vector.getOwnershipRange()
    rows = np.arange(start, stop, dtype=np.float64)
    vector.getArray()[:] = factor * (rows + 1.0 + 1j * (rows + 2.0))
    return vector


def _dense_oracle(data, source):
    condensed = data["condensed"]
    values = source.getArray(readonly=True)
    cells = []
    counts = {}
    for cell in condensed.cell_recovery_maps:
        active, sparse_expansion, _ = _cell_trace_expansion(
            cell.trace_original_dofs, condensed.trace_constraints
        )
        active = np.asarray(active, dtype=np.int64)
        expansion = np.asarray(sparse_expansion.toarray(), dtype=np.complex128)
        bridge = data["bridges"][cell.class_key]
        mapped = bridge.trace_transfer.conj().T @ (
            bridge.lor_trace_operator @ bridge.trace_transfer
        )
        block = expansion.conj().T @ mapped @ expansion
        cells.append((active, block))
        for row in active:
            counts[int(row)] = counts.get(int(row), 0) + 1
    result = np.zeros_like(values)
    for active, block in cells:
        result[active] += np.linalg.solve(block, values[active]) / np.asarray(
            [counts[int(row)] for row in active]
        )
    return result


def _relative_vec(left, right):
    difference = left.copy()
    difference.axpy(PETSc.ScalarType(-1.0), right)
    relative = difference.norm() / max(right.norm(), 1.0e-30)
    difference.destroy()
    return float(relative)


def test_l2b_serial_dense_oracle_contract(l2b):
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("dense additive oracle is the serial contract")
    condensed, service = l2b["condensed"], l2b["service"]
    audit = service.audit
    assert audit["pass"] is True
    assert audit["scope"] == "component_service_only_not_h10_h5_or_5nm_signal"
    assert audit["max_local_factor_rows"] <= 432
    assert audit["prod_vs_bridge_max_relative"] <= 1.0e-10
    assert audit["hermitian_max_relative"] <= 1.0e-10
    assert audit["factor_solve_relative_max"] <= 1.0e-10
    assert audit["coverage_global_min"] > 0.0
    assert audit["factor_count_local"] <= audit["cell_count_local"]
    assert audit["retained_numpy_factor_map_bytes_not_peak"] > 0
    assert audit["retained_work_vector_payload_bytes_not_peak"] == (
        2
        * audit["local_union_rows"]
        * np.dtype(PETSc.ScalarType).itemsize
    )
    assert audit["global_F"] is False
    assert audit["global_AIJ"] is False
    assert audit["global_factor"] is False
    source = _new_vector(condensed)
    target = condensed.create_active_vector()
    service.solve(source, target)
    expected = condensed.create_active_vector()
    expected.getArray()[:] = _dense_oracle(l2b, source)
    oracle_error = _relative_vec(target, expected)
    assert oracle_error <= 1.0e-10
    repeated = condensed.create_active_vector()
    service.solve(source, repeated)
    repeat_error = _relative_vec(target, repeated)
    other = _new_vector(condensed, 0.7)
    other_target = condensed.create_active_vector()
    service.solve(other, other_target)
    combo = source.copy()
    combo.scale(PETSc.ScalarType(0.4 - 0.3j))
    combo.axpy(PETSc.ScalarType(-0.2 + 0.5j), other)
    combo_target = condensed.create_active_vector()
    service.solve(combo, combo_target)
    linear_expected = target.copy()
    linear_expected.scale(PETSc.ScalarType(0.4 - 0.3j))
    linear_expected.axpy(PETSc.ScalarType(-0.2 + 0.5j), other_target)
    linearity_error = _relative_vec(combo_target, linear_expected)
    assert repeat_error <= 1.0e-10
    assert linearity_error <= 1.0e-10
    assert audit["apply_count"] == 4
    assert audit["solve_count"] == 4
    prod = audit["prod_vs_bridge_max_relative"]
    hermitian = audit["hermitian_max_relative"]
    factor_solve = audit["factor_solve_relative_max"]
    coverage = audit["coverage_global_min"]
    pou = audit["pou_weight_sum_max_error"]
    factor_reuse = audit["factor_cache_reuse_local"]
    factor_bytes = audit["retained_numpy_factor_map_bytes_not_peak"]
    work_bytes = audit["retained_work_vector_payload_bytes_not_peak"]
    print(
        "TASK040_L2B "
        f"cells={audit['cell_count_global']} factors={audit['factor_count_local']} "
        f"oracle={oracle_error:.3e} repeat={repeat_error:.3e} "
        f"linearity={linearity_error:.3e} rows={audit['max_local_factor_rows']} "
        f"prod_vs_bridge_max_relative={prod:.3e} "
        f"hermitian_max_relative={hermitian:.3e} "
        f"factor_solve_relative_max={factor_solve:.3e} "
        f"coverage_global_min={coverage:.3e} "
        f"pou_weight_sum_max_error={pou:.3e} "
        f"factor_cache_reuse_local={factor_reuse} "
        f"retained_numpy_factor_map_bytes_not_peak={factor_bytes} "
        f"retained_work_vector_payload_bytes_not_peak={work_bytes} "
        f"apply_count={audit['apply_count']} solve_count={audit['solve_count']}"
    )
    for vector in (
        linear_expected,
        combo_target,
        combo,
        other_target,
        other,
        repeated,
        expected,
        target,
        source,
    ):
        vector.destroy()


def test_l2b_distributed_ownership_and_lifecycle(l2b):
    comm = MPI.COMM_WORLD
    condensed, service = l2b["condensed"], l2b["service"]
    audit = service.audit
    assert audit["pou_weight_sum_max_error"] <= 1.0e-10
    assert audit["numeric_allgather"] is False
    assert audit["full_basis_replication"] is False
    assert audit["bridge_retained"] is False
    source = _new_vector(condensed)
    target = condensed.create_active_vector()
    before_apply = audit["apply_count"]
    before_solve = audit["solve_count"]
    service.apply(None, source, target)
    assert np.all(np.isfinite(target.getArray(readonly=True)))
    repeated = condensed.create_active_vector()
    service.apply(None, source, repeated)
    assert audit["apply_count"] == before_apply + 2
    assert audit["solve_count"] == before_solve
    assert _relative_vec(target, repeated) <= 1.0e-10
    ranges = comm.allgather(tuple(map(int, target.getOwnershipRange())))
    assert ranges[0][0] == 0
    assert ranges[-1][1] == condensed.active_rows
    assert all(
        left[1] == right[0]
        for left, right in pairwise(ranges)
    )
    service.destroy()
    assert service.destroyed is True
    with pytest.raises(RuntimeError):
        service.apply(None, source, target)
    repeated.destroy()
    target.destroy()
    source.destroy()
