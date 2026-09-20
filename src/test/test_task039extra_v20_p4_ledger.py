"""Controlled ledger bookkeeping coverage, not numerical p4 qualification.

The fixture uses a real FE condensation object, but its factor and original
A4 callback are deliberately controlled doubles.  It verifies ownership,
logical/physical call accounting, refinement accumulation, and failure-safe
ledger control flow only.  Numerical qualification is covered separately by
the frozen V18/V19 real FE/MPC fixtures.
"""

from types import SimpleNamespace
import gc
import weakref

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.p4_cell_condensed_inverse import (
    P4CellCondensedInverse,
    P4RefinementLedger,
    assemble_condensed_ports,
)
from src.runners.physical_retained_condensed_v20 import (
    RetainedCondensedRuntime,
    persist_p4_failure_packet,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture


class _ControlledFactor:
    """Controlled factor double; never a numerical qualification backend."""

    symbolic_calls = 1
    numeric_calls = 1

    def __init__(self, active_index: int, port_index: int) -> None:
        self.active_index = int(active_index)
        self.port_index = int(port_index)
        self.solve_calls = 0

    def solve_repeated(self, _rhs, solution) -> None:
        solution.set(PETSc.ScalarType(0.0))
        solution.getArray()[self.active_index] = 2.0
        solution.getArray()[self.port_index] = 3.0
        self.solve_calls += 1


def test_controlled_p4_ledger_accumulates_port_and_records_factor_counts():
    mesh_3d, cell_tags, space, compiled = _build_fixture(MPI.COMM_SELF)
    cells = int(mesh_3d.topology.index_map(mesh_3d.topology.dim).size_local)
    system = build_unconstrained_assembly_time_condensation(
        compiled,
        space,
        cell_tags,
        appended_global_rows=1,
        appended_support_owned_cell_groups=(np.arange(cells, dtype=np.int32),),
        appended_support_group_by_row=(0,),
        dense_appended_block=True,
        sum_duplicate_cell_integrals=True,
        strict_local_checks=True,
        defer_final_assembly=True,
    )
    assert system.matrix is not None
    system.matrix.assemble()
    try:
        original = int(system.trace_constraints.owned_active_original_dofs[0])
        active_index = int(system.trace_constraints.original_to_active[original])
        factor = _ControlledFactor(active_index, system.active_rows)
        inverse = P4CellCondensedInverse(system, factor)
        with pytest.raises(ValueError, match="max_refinements"):
            P4RefinementLedger(
                inverse,
                lambda _solution, _port_state: rhs,
                port_closure=lambda _solution, _port_state: {"status": "PASS"},
                max_refinements=3,
            )
        rhs = PETSc.Vec().createMPI(
            (system.full_rows, system.full_rows),
            comm=PETSc.COMM_SELF,
        )
        rhs.set(PETSc.ScalarType(0.0))
        rhs.getArray()[active_index] = 1.0
        rhs.assemble()
        calls = {"count": 0}

        def original_a4(_solution, _port_state):
            output = rhs.duplicate()
            rhs.copy(output)
            calls["count"] += 1
            if calls["count"] <= 2:
                output.scale(PETSc.ScalarType(2.0))
            return output

        def port_closure(solution, port_state):
            c = complex(solution.getValues(np.asarray([original], dtype=PETSc.IntType))[0])
            a = complex(port_state[0])
            net = np.asarray([2.0 * a - 3.0 * c], dtype=np.complex128)
            norm = float(np.linalg.norm(net))
            scale = float(abs(2.0 * a) + abs(3.0 * c))
            relative = 0.0 if scale == 0.0 and norm == 0.0 else norm / scale
            return {
                "status": "PASS" if relative <= 1.0e-10 else "P4_NUMERICAL_UNQUALIFIED",
                "finite": bool(np.isfinite(net).all()),
                "norm": norm,
                "scale": scale,
                "relative_residual": relative,
                "formula": "H*a-D*c",
            }

        ledger = P4RefinementLedger(
            inverse,
            original_a4,
            port_closure=port_closure,
            max_refinements=2,
        )
        solution = ledger.solve(rhs)
        try:
            assert ledger.last_audit["status"] == "P4_RETURN_PASS"
            assert ledger.last_audit["refinement_count"] == 2
            assert ledger.logical_apply_calls == 1
            assert factor.symbolic_calls == 1
            assert factor.numeric_calls == 1
            assert factor.solve_calls == 3
            assert all(row["port_closure"]["status"] == "PASS" for row in ledger.last_audit["rows"])
            assert np.isclose(ledger.total_port_solution[0], 9.0)
        finally:
            solution.destroy()
            rhs.destroy()
            inverse.destroy()
    finally:
            system.destroy()


def test_p4_failure_sink_writes_nonfinite_arrays_to_npz(tmp_path):
    """Raw nonfinite failure vectors stay in NPZ; JSON diagnostics stay finite."""

    records = []
    packet = {
        "status": "P4_NUMERICAL_UNQUALIFIED",
        "matrix_identity": {"csr_sha256": "matrix"},
        "factor_counts": {"logical_apply_calls": 1},
        "rows": [{"relative_residual": float("nan"), "attempt": 1}],
        "g": np.asarray([np.nan + 1j, 2.0 + 0j], dtype=np.complex128),
        "c": np.asarray([np.inf + 0j], dtype=np.complex128),
        "r": None,
        "port_state": np.asarray([3.0 + 0j], dtype=np.complex128),
    }
    record = persist_p4_failure_packet(
        packet,
        tmp_path,
        source_sha="a" * 40,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        append=lambda _name, value: records.append(value),
    )
    assert len(records) == 1
    assert record["array_artifact"]["arrays"]["g"]["finite"] is False
    assert record["array_artifact"]["arrays"]["c"]["finite"] is False
    assert record["rows"][0]["relative_residual"] == {"nonfinite": "nan"}
    artifact = tmp_path / record["array_artifact"]["filename"]
    loaded = np.load(artifact, allow_pickle=False)
    try:
        assert np.isnan(loaded["g"][0].real)
        assert np.isinf(loaded["c"][0].real)
        assert "r" not in loaded.files
    finally:
        loaded.close()


class _PerturbedRealInverse(P4CellCondensedInverse):
    """Perturb a complete recovered state and its port state for testing."""

    def __init__(self, *args, scale=1.0 - 1.0e-4, **kwargs):
        super().__init__(*args, **kwargs)
        self.scale = float(scale)

    def apply(self, rhs):
        output = super().apply(rhs)
        output.scale(PETSc.ScalarType(self.scale))
        self.last_port_solution = np.asarray(
            self.last_port_solution, dtype=np.complex128
        ) * self.scale
        return output


def test_real_factor_ledger_refines_independent_a4_and_saves_failure_packet():
    """Real FE/MUMPS factor, fixed independent A4, cumulative port and failure evidence."""

    from dolfinx.fem import petsc as fem_petsc
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

    mesh_3d, cell_tags, space, compiled = _build_fixture(MPI.COMM_SELF)
    cells = int(mesh_3d.topology.index_map(mesh_3d.topology.dim).size_local)
    system = build_unconstrained_assembly_time_condensation(
        compiled,
        space,
        cell_tags,
        appended_global_rows=1,
        appended_support_owned_cell_groups=(np.arange(cells, dtype=np.int32),),
        appended_support_group_by_row=(0,),
        dense_appended_block=True,
        sum_duplicate_cell_integrals=True,
        strict_local_checks=True,
        geometry_identity_policy="raw_unrounded",
        share_identity_cache=True,
        defer_final_assembly=True,
    )
    full = fem_petsc.assemble_matrix(compiled, bcs=[])
    full.assemble()
    factor_backend = None
    inverse = None
    success = None
    failure = None
    rhs = None
    try:
        interior = int(system.cell_recovery_maps[0].interior_original_dofs[0])
        trace = int(system.cell_recovery_maps[0].trace_original_dofs[0])
        carrier = SimpleNamespace(
            entries=(SimpleNamespace(
                coupling_rows=np.asarray([interior], dtype=PETSc.IntType),
                coupling_values=np.asarray([0.23 - 0.11j], dtype=np.complex128),
                projection_rows=np.asarray([interior], dtype=PETSc.IntType),
                projection_values=np.asarray([0.37 + 0.19j], dtype=np.complex128),
                normalization_h=1.4 + 0.25j,
            ),)
        )
        terms = assemble_condensed_ports(system, carrier)
        system.matrix.assemble()
        factor_backend = _MumpsFactor(system.matrix)
        factor_backend.set_icntl(23, 0)
        factor_backend.symbolic(system.matrix)
        factor_backend.numeric(system.matrix)
        inverse = _PerturbedRealInverse(
            system,
            factor_backend,
            port_terms=terms,
            owns_factor=True,
            owns_condensed=True,
        )
        rhs = PETSc.Vec().createMPI(
            (system.full_rows, system.full_rows), comm=PETSc.COMM_SELF
        )
        rhs.set(PETSc.ScalarType(0.0))
        rhs.setValue(interior, PETSc.ScalarType(0.9 + 0.2j))
        rhs.setValue(trace, PETSc.ScalarType(-0.15 + 0.07j))
        rhs.assemble()

        def original_a4(solution, _port_state):
            output = full.createVecLeft()
            full.mult(solution, output)
            c = complex(solution.getValue(interior))
            independent_port_elimination = (
                (0.23 - 0.11j) * (0.37 + 0.19j) * c / (1.4 + 0.25j)
            )
            output.setValue(
                interior,
                PETSc.ScalarType(independent_port_elimination),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            output.assemble()
            return output

        def port_closure(solution, port_state):
            c = complex(solution.getValue(interior))
            a = complex(port_state[0])
            h_term = (1.4 + 0.25j) * a
            d_term = (0.37 + 0.19j) * c
            net = h_term - d_term
            scale = abs(h_term) + abs(d_term)
            relative = 0.0 if scale == 0.0 and net == 0.0 else abs(net) / scale
            return {
                "status": "PASS" if relative <= 1.0e-10 else "P4_NUMERICAL_UNQUALIFIED",
                "finite": bool(np.isfinite(net)),
                "norm": float(abs(net)),
                "scale": float(scale),
                "relative_residual": float(relative),
                "formula": "H*a-D*c",
            }

        success = P4RefinementLedger(
            inverse,
            original_a4,
            port_closure=port_closure,
            max_refinements=2,
        )
        solved = success.solve(rhs)
        assert success.last_audit["status"] == "P4_RETURN_PASS"
        assert success.last_audit["refinement_count"] == 2
        assert success.logical_apply_calls == 1
        assert success.last_audit["factor_counts"]["symbolic_calls"] == 1
        assert success.last_audit["factor_counts"]["numeric_calls"] == 1
        assert success.last_audit["factor_counts"]["solve_calls"] == 3
        assert len(success.total_port_solution) == 1
        assert np.linalg.norm(success.total_port_solution) > 0.0
        assert success.last_audit["rows"][-1]["relative_residual"] <= 1.0e-10
        assert all(
            row["port_closure"]["status"] == "PASS"
            for row in success.last_audit["rows"]
        )

        packets = []
        failure = P4RefinementLedger(
            inverse,
            original_a4,
            port_closure=port_closure,
            failure_sink=packets.append,
            tolerance=1.0e-10,
            max_refinements=0,
        )
        try:
            failure.solve(rhs)
        except RuntimeError as error:
            assert "qualified limit" in str(error)
        else:
            raise AssertionError("strict real-A4 failure path unexpectedly passed")
        assert failure.last_audit["status"] == "P4_NUMERICAL_UNQUALIFIED"
        assert packets and all(packets[0][key] is not None for key in ("g", "c", "r"))
        assert packets[0]["matrix_identity"]["csr_sha256"]
    finally:
        if success is not None:
            success_solution = locals().get("solved")
            if success_solution is not None:
                success_solution.destroy()
        if failure is not None:
            failure.last_audit.clear()
        if inverse is not None:
            inverse.destroy()
        elif factor_backend is not None:
            factor_backend.destroy()
        if rhs is not None:
            rhs.destroy()
        full.destroy()
        if inverse is None:
            system.destroy()


class _LifecycleOwner:
    def __init__(self, name):
        self.name = name
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


def test_retained_runtime_release_and_destroy_clear_owner_refs(monkeypatch):
    """Normal release records gates; destroy cleans without fabricating them."""

    physical_destroyed = []

    def destroy_physical(value):
        physical_destroyed.append(value)

    monkeypatch.setattr(
        "src.solvers.fullspace_same_mesh_hcurl_pmg_physical.destroy_same_mesh_physical_action",
        destroy_physical,
    )
    fine = {"owner": _LifecycleOwner("fine")}
    p4 = {"owner": _LifecycleOwner("p4")}
    p6_action = _LifecycleOwner("p6_action")
    p4_inverse = _LifecycleOwner("p4_inverse")
    h6_owner = _LifecycleOwner("h6")
    shell_owner = _LifecycleOwner("shell")
    transfer_owner = _LifecycleOwner("transfer")
    closure_owner = _LifecycleOwner("closure")
    closure_ref = weakref.ref(closure_owner)
    runtime = RetainedCondensedRuntime(
        levels={"dummy": object()},
        fine=fine,
        p4=p4,
        p6_system=object(),
        p6_action=p6_action,
        p4_system=object(),
        p4_terms={0: closure_owner},
        mode_count=1,
        mode_sha256="controlled",
        p4_inverse=p4_inverse,
        h6={"h6": h6_owner, "p6_shell": shell_owner},
        transfer=lambda value=closure_owner: value,
        bal_h=lambda value=closure_owner: value,
        bridge=lambda value=closure_owner: value,
        transfer_owner=transfer_owner,
    )

    with pytest.raises(RuntimeError, match="saved field"):
        runtime.release_solver_stack(field_saved=False, pre_release_a6_checked=True)
    assert not p4_inverse.destroyed

    markers = []
    facts = runtime.release_solver_stack(
        field_saved=True,
        pre_release_a6_checked=True,
        marker=lambda name, payload: markers.append((name, payload)),
    )
    assert facts["status"] == "RELEASED"
    assert facts["factor_released_before_matrix"]
    assert p4_inverse.destroyed and p6_action.destroyed
    assert h6_owner.destroyed and shell_owner.destroyed and transfer_owner.destroyed
    assert runtime.fine is fine
    assert runtime.p4_terms == {} and runtime.bridge is None and runtime.bal_h is None
    assert [name for name, _payload in markers] == [
        "retained_solver_stack_release_started",
        "retained_solver_stack_release_complete",
    ]

    closure_owner = None
    gc.collect()
    assert closure_ref() is None
    runtime.destroy()
    assert runtime.destroyed
    assert physical_destroyed == [fine, p4]

    unsafe = RetainedCondensedRuntime(
        levels={},
        fine={},
        p4={},
        p6_system=None,
        p6_action=_LifecycleOwner("unsafe_p6"),
        p4_system=None,
        p4_terms={},
        mode_count=1,
        mode_sha256="controlled",
    )
    unsafe.destroy()
    assert unsafe.destroyed and unsafe.solver_stack_released
