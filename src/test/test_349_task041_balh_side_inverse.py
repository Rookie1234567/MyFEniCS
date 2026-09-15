"""Focused small-PETSc checks for the H1e side BAL_H adapter."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers import physical_balanced_side_inverse as side_inverse_module
from src.solvers.hybrid_local_dtn_action import HybridLocalDtnActionSystem
from src.solvers.physical_balanced_physical_operator import (
    P4ExactFactor,
    P4PhysicalResidualGateError,
)
from src.solvers.physical_balanced_side_inverse import SideBalancedInverse

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="Task041 H1e focused side-inverse tests are serial/MPI2 only",
)

# Native PETSc names the task's DIVERGED_ITS budget result DIVERGED_MAX_IT.
_DIVERGED_ITS = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)


class _ScaleContext:
    def __init__(self, scale: complex) -> None:
        self.scale = PETSc.ScalarType(scale)
        self.apply_count = 0
        self.destroyed = False

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self.destroyed:
            raise RuntimeError("scale matrix context has been destroyed")
        target.set(0.0)
        target.axpy(self.scale, source)
        self.apply_count += 1

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        self.destroyed = True


def _scale_matrix(size: int, scale: complex) -> tuple[PETSc.Mat, _ScaleContext]:
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    local_rows = size // comm.Get_size()
    context = _ScaleContext(scale)
    matrix = PETSc.Mat().createPython(
        ((local_rows, size), (local_rows, size)),
        context=context,
        comm=comm,
    )
    matrix.setUp()
    del rank
    return matrix, context


class _IdentityCondensed:
    def __init__(self, size: int) -> None:
        comm = MPI.COMM_WORLD
        self.comm = comm
        self.active_rows = size
        self.full_rows = size
        self.owned_active_rows = size // comm.Get_size()
        first = self.owned_active_rows * comm.Get_rank()
        self.trace_constraints = SimpleNamespace(
            owned_active_original_dofs=np.arange(
                first,
                first + self.owned_active_rows,
                dtype=PETSc.IntType,
            )
        )

    def create_active_vector(self) -> PETSc.Vec:
        return PETSc.Vec().createMPI(
            (self.owned_active_rows, self.active_rows),
            comm=self.comm,
        )


class _IdentityTransfer:
    def __init__(self) -> None:
        self.apply_count = 0
        self.destroy_count = 0

    @staticmethod
    def _copy(source: PETSc.Vec) -> PETSc.Vec:
        target = source.duplicate()
        source.copy(target)
        return target

    def apply_adjoint(
        self,
        source: PETSc.Vec,
        *,
        timing: dict[str, float] | None = None,
    ) -> PETSc.Vec:
        self.apply_count += 1
        if timing is not None:
            timing.update(
                {
                    "cell_adjoint_seconds": 1.0e-4,
                    "dual_reduce_seconds": 2.0e-4,
                    "mpi_exchange_seconds": 4.0e-4,
                    "ghost_mpc_prepare_seconds": 5.0e-4,
                    "ghost_mpc_check_seconds": 6.0e-4,
                }
            )
        return self._copy(source)

    def apply_primal(
        self,
        source: PETSc.Vec,
        *,
        timing: dict[str, float] | None = None,
    ) -> PETSc.Vec:
        self.apply_count += 1
        if timing is not None:
            timing.update(
                {
                    "local_candidate_generation_seconds": 1.0e-4,
                    "route_sort_index_seconds": 2.0e-4,
                    "mpi_exchange_seconds": 3.0e-4,
                    "duplicate_row_check_seconds": 4.0e-4,
                    "ghost_mpc_prepare_seconds": 5.0e-4,
                    "ghost_mpc_check_seconds": 6.0e-4,
                }
            )
        return self._copy(source)

    @property
    def audit(self) -> dict[str, object]:
        return {"pair_fine_to_coarse": [6, 4], "owner_local": True}

    def destroy(self) -> None:
        self.destroy_count += 1


class _IdentityP4:
    def __init__(self, size: int) -> None:
        self.physical_action = SimpleNamespace(V=object(), floquet_data=object())
        self.solve_count = 0
        self.destroy_count = 0
        self.size = size

    @staticmethod
    def _copy(source: PETSc.Vec) -> PETSc.Vec:
        target = source.duplicate()
        source.copy(target)
        return target

    def create_rhs(self, source: PETSc.Vec) -> PETSc.Vec:
        return self._copy(source)

    def solve_with_refinement(
        self,
        rhs: PETSc.Vec,
        solution: PETSc.Vec,
        *,
        residual_tolerance: float,
        timing=None,
    ) -> dict[str, object]:
        del residual_tolerance
        rhs.copy(solution)
        self.solve_count += 1
        if timing is not None:
            timing["factor_solve_seconds"] = 1.0e-3
            timing["A4_residual_refinement_seconds"] = 2.0e-3
            timing["physical_action_matrix_mult_seconds"] = 3.0e-4
        return {"backsolve_count": 1, "relative_residual": 0.0}

    def extract_fe_solution(self, solution: PETSc.Vec) -> PETSc.Vec:
        return self._copy(solution)

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "factor_creation_count": 1,
            "factor_destroy_count": int(self.destroy_count > 0),
            "last_solve": {"backsolve_count": 1},
            "research_factor": {
                "solve_count": self.solve_count,
                "direct_factor_count": int(self.destroy_count == 0),
                "factor_destroyed": bool(self.destroy_count),
            },
        }

    def destroy(self) -> None:
        self.destroy_count += 1


class _NonfiniteP4(_IdentityP4):
    def solve_with_refinement(
        self,
        rhs: PETSc.Vec,
        _solution: PETSc.Vec,
        *,
        residual_tolerance: float,
    ) -> dict[str, object]:
        self.solve_count += 1
        rhs_norm = float(rhs.norm())
        raise P4PhysicalResidualGateError(
            {
                "status": "failed_nonfinite_residual",
                "rhs_norm": rhs_norm,
                "residual_norm": float("nan"),
                "relative_residual": float("nan"),
                "residual_tolerance": float(residual_tolerance),
                "backsolve_count": self.solve_count,
                "refinement_count": 0,
            }
        )


class _RefinementFactor:
    def __init__(self) -> None:
        self.solve_count = 0
        self.destroy_count = 0

    def solve(self, _rhs: PETSc.Vec, solution: PETSc.Vec) -> None:
        self.solve_count += 1
        if self.solve_count <= 3:
            solution.set(0.0)
            return
        _rhs.copy(solution)
        solution.scale(PETSc.ScalarType(0.5))

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "solve_count": self.solve_count,
            "direct_factor_count": int(self.destroy_count == 0),
            "factor_destroyed": bool(self.destroy_count),
        }

    def destroy(self) -> None:
        self.destroy_count += 1


class _PhysicalP4Action:
    def __init__(self, matrix: PETSc.Mat) -> None:
        self.matrix = matrix
        self.full_rows = 2
        self.modes: tuple[object, ...] = ()

    def destroy(self) -> None:
        self.matrix.destroy()


class _IdentityH6:
    def __init__(self) -> None:
        self.apply_count = 0
        self.destroy_count = 0

    @staticmethod
    def _copy(source: PETSc.Vec) -> PETSc.Vec:
        target = source.duplicate()
        source.copy(target)
        return target

    def apply(self, source: PETSc.Vec) -> PETSc.Vec:
        self.apply_count += 1
        return self._copy(source)

    @property
    def audit(self) -> dict[str, object]:
        return {"factor_count": 0, "apply_count": self.apply_count}

    def destroy(self) -> None:
        self.destroy_count += 1


class _FailingH6(_IdentityH6):
    def apply(self, _source: PETSc.Vec) -> PETSc.Vec:
        raise RuntimeError("focused H1e H6 failure")


class _KspContractStub:
    def __init__(self, approximate: PETSc.Vec, reason: int, iterations: int) -> None:
        self.approximate = approximate
        self.reason = int(reason)
        self.iterations = int(iterations)

    def solve(self, _source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.approximate.copy(target)

    def getConvergedReason(self) -> int:
        return self.reason

    def getIterationNumber(self) -> int:
        return self.iterations


class _BufferRecordingComm:
    def __init__(self, comm) -> None:
        self.comm = comm
        self.scalar_allreduce_count = 0
        self.buffer_allreduce_count = 0

    def allreduce(self, value, *, op):
        self.scalar_allreduce_count += 1
        return self.comm.allreduce(value, op=op)

    def Allreduce(self, send, receive, *, op):
        self.buffer_allreduce_count += 1
        self.comm.Allreduce(send, receive, op=op)

    def Get_rank(self) -> int:
        return self.comm.Get_rank()


class _RepeatedPcKsp:
    def __init__(self, owner: SideBalancedInverse) -> None:
        self.owner = owner

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        work = target.duplicate()
        try:
            self.owner._apply_balanced_pc(source, work)
            self.owner._apply_balanced_pc(source, target)
        finally:
            work.destroy()

    def getConvergedReason(self) -> int:
        return 1

    def getIterationNumber(self) -> int:
        return 1


class _FullAction:
    def __init__(self, size: int) -> None:
        self.matrix, self.context = _scale_matrix(size, 1.0)
        self.full_rows = size
        self.destroy_count = 0

    def destroy(self) -> None:
        self.destroy_count += 1
        self.matrix.destroy()


def _new_vector(operator: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = operator.createVecRight()
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()
    return vector


def _relative_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.duplicate()
    try:
        left.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), right)
        denominator = float(right.norm())
        numerator = float(difference.norm())
        return numerator / denominator if denominator else numerator
    finally:
        difference.destroy()


def _build_fixture(
    size: int = 2,
    *,
    checkpoint_callback=None,
    audit_callback=None,
    p4_factor=None,
    detailed_timing: bool = False,
) -> tuple[SideBalancedInverse, dict[str, object]]:
    operator, operator_context = _scale_matrix(size, 2.0)
    condensed = _IdentityCondensed(size)
    side_system = SimpleNamespace(
        A=operator,
        cfg=SimpleNamespace(nedelec_degree=6),
        static_condensation=SimpleNamespace(condensed=condensed),
        side="bottom",
    )
    full_action = _FullAction(size)
    p4_factor = _IdentityP4(size) if p4_factor is None else p4_factor
    transfer = _IdentityTransfer()
    h6 = _IdentityH6()
    inverse = SideBalancedInverse(
        side_system,
        full_action,
        p4_factor,
        transfer,
        h6,
        checkpoint_callback=checkpoint_callback,
        audit_callback=audit_callback,
        detailed_timing=detailed_timing,
    )
    return inverse, {
        "operator": operator,
        "operator_context": operator_context,
        "full_action": full_action,
        "p4_factor": p4_factor,
        "transfer": transfer,
        "h6": h6,
        "side_system": side_system,
    }


def _builder_side_system(size: int = 2):
    operator, operator_context = _scale_matrix(size, 2.0)
    side_system = object.__new__(HybridLocalDtnActionSystem)
    side_system.A = operator
    side_system.cfg = SimpleNamespace(nedelec_degree=6)
    side_system.static_condensation = SimpleNamespace(
        condensed=_IdentityCondensed(size)
    )
    side_system.side = "bottom"
    b = operator.createVecLeft()
    b.set(PETSc.ScalarType(1.0 + 0.5j))
    b.assemble()
    side_system.b = b
    return side_system, operator, operator_context, b


def _assert_borrowed_stub_system_works(
    operator: PETSc.Mat,
    operator_context: _ScaleContext,
    b: PETSc.Vec,
    b_before: np.ndarray,
) -> None:
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    output = operator.createVecLeft()
    try:
        operator.mult(source, output)
        np.testing.assert_allclose(
            output.getArray(readonly=True),
            2.0 * source.getArray(readonly=True),
        )
        np.testing.assert_array_equal(
            b.getArray(readonly=True),
            b_before,
        )
        assert operator_context.destroyed is False
    finally:
        output.destroy()
        source.destroy()


def _install_stub_side_builders(monkeypatch, captured):
    def fake_full_action(_side_system):
        action = _FullAction(2)
        action.V = object()
        action.floquet_data = object()
        captured["full_action"] = action
        return action

    def fake_p4(_side_system, *, lifecycle_callback=None):
        captured["p4_callback"] = lifecycle_callback
        factor = _IdentityP4(2)
        captured["p4"] = factor
        return factor

    def fake_transfer(*_args, **_kwargs):
        transfer = _IdentityTransfer()
        captured["transfer"] = transfer
        return transfer

    def fake_h6(_side_system, *, lifecycle_callback=None):
        captured["h6_callback"] = lifecycle_callback
        h6 = _IdentityH6()
        captured["h6"] = h6
        return h6

    monkeypatch.setattr(
        side_inverse_module,
        "build_fullspace_physical_dtn_action",
        fake_full_action,
    )
    monkeypatch.setattr(side_inverse_module, "build_p4_exact_factor", fake_p4)
    monkeypatch.setattr(
        side_inverse_module,
        "build_same_mesh_hcurl_owner_transfer",
        fake_transfer,
    )
    monkeypatch.setattr(side_inverse_module, "build_balanced_h6", fake_h6)
    monkeypatch.setattr(
        side_inverse_module,
        "_full_action_inventory",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_owner_transfer_inventory",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_side_adapter_inventory",
        lambda *_args, **_kwargs: {},
    )


def test_side_inverse_builder_default_callback_skips_inventory(monkeypatch):
    captured = {}
    side_system, operator, _operator_context, b = _builder_side_system()
    inventory_calls = []
    _install_stub_side_builders(monkeypatch, captured)

    def forbidden_inventory(*_args, **_kwargs):
        inventory_calls.append(True)
        raise AssertionError("default lifecycle callback read inventory")

    monkeypatch.setattr(
        side_inverse_module,
        "_full_action_inventory",
        forbidden_inventory,
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_owner_transfer_inventory",
        forbidden_inventory,
    )
    monkeypatch.setattr(
        side_inverse_module,
        "_side_adapter_inventory",
        forbidden_inventory,
    )
    inverse = None
    try:
        inverse = side_inverse_module.build_side_balanced_inverse(side_system)
        assert captured["p4_callback"] is None
        assert captured["h6_callback"] is None
        assert inventory_calls == []
    finally:
        if inverse is not None:
            inverse.destroy()
        b.destroy()
        operator.destroy()


@pytest.mark.parametrize("failure_event", ["full_action_ready", "adapter_ksp_ready"])
def test_side_inverse_builder_callback_failure_cleans_owned_only(
    monkeypatch, failure_event
):
    captured = {}
    side_system, operator, operator_context, b = _builder_side_system()
    b_before = np.asarray(b.getArray(readonly=True)).copy()
    _install_stub_side_builders(monkeypatch, captured)

    def failing_callback(event, _detail):
        if event == failure_event:
            raise RuntimeError(f"injected {failure_event}")

    try:
        with pytest.raises(RuntimeError, match=failure_event):
            side_inverse_module.build_side_balanced_inverse(
                side_system,
                lifecycle_callback=failing_callback,
            )
        _assert_borrowed_stub_system_works(
            operator, operator_context, b, b_before
        )
        assert captured["full_action"].destroy_count == 1
        if failure_event == "full_action_ready":
            assert "p4" not in captured
            assert "transfer" not in captured
            assert "h6" not in captured
        else:
            assert captured["p4"].destroy_count == 1
            assert captured["transfer"].destroy_count == 1
            assert captured["h6"].destroy_count == 1
    finally:
        b.destroy()
        operator.destroy()


@pytest.mark.parametrize("detailed_timing", [False, True])
def test_side_inverse_right_pc_reuse_zero_and_cleanup(
    detailed_timing: bool,
) -> None:
    checkpoint_calls: list[None] = []
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        checkpoint_callback=lambda: checkpoint_calls.append(None),
        audit_callback=audit_records.append,
        detailed_timing=detailed_timing,
    )
    operator = owned["operator"]
    q1 = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    q2 = _new_vector(operator, np.asarray([0.3 - 0.5j, 0.8 + 0.1j]))
    q1_before = q1.copy()
    q2_before = q2.copy()
    y1 = operator.createVecLeft()
    y2 = operator.createVecLeft()
    y3 = operator.createVecLeft()
    zero = operator.createVecRight()
    zero.set(0.0)
    zero_out = operator.createVecLeft()
    bad = operator.createVecRight()
    bad.set(PETSc.ScalarType(np.nan))
    bad_out = operator.createVecLeft()
    expected: PETSc.Vec | None = None
    expected2: PETSc.Vec | None = None
    try:
        inverse.apply(q1, y1)
        inverse.apply(q2, y2)
        inverse.apply(q1, y3)
        with pytest.raises(RuntimeError, match="RHS norm is non-finite"):
            inverse.apply(bad, bad_out)
        failed = inverse.diagnostics["last_apply"]
        assert failed["status"] == "FAILED"
        assert failed["reason"] is None
        assert failed["iterations"] == 0
        assert failed["residual_norm"] == "not_measured"
        assert audit_records[-1]["status"] == "FAILED"
        inverse.apply(zero, zero_out)
        with pytest.raises(ValueError, match="source/target aliasing"):
            inverse.apply(q1, q1)
        expected = q1.copy()
        expected.scale(0.5)
        expected2 = q2.copy()
        expected2.scale(0.5)
        assert _relative_difference(y1, expected) <= 1.0e-12
        assert _relative_difference(y2, expected2) <= 1.0e-12
        assert _relative_difference(y3, y1) <= 1.0e-12
        assert _relative_difference(q1, q1_before) == 0.0
        assert _relative_difference(q2, q2_before) == 0.0
        assert zero_out.norm() == 0.0
        assert len(audit_records) == 5
        successful = audit_records[:3]
        assert len({record["iterations"] for record in successful}) == 1
        assert len(
            {
                record["counts"]["delta"]["checkpoint"]
                for record in successful
            }
        ) == 1
        assert len(checkpoint_calls) > 0
        last = inverse.diagnostics["last_apply"]
        assert last["status"] == "ZERO_RHS_EXACT"
        assert last["explicit_true_target_reached"] is True
        if detailed_timing:
            zero_timing = last["operation_seconds"]
            assert zero_timing["status"] == "measured_rank_max"
            assert all(
                value == "not_called"
                for value in zero_timing["detailed"]["measurement_status"].values()
            )
            assert all(
                value is None
                for value in zero_timing["detailed"]["max_rank_seconds"].values()
            )
        else:
            assert inverse.diagnostics["detailed_timing"] is False
            assert "detailed" not in last["operation_seconds"]
        diagnostics = inverse.diagnostics
        assert diagnostics["apply_count"] == 5
        assert diagnostics["p4_factor_count"] == 1
        assert inverse.diagnostics["p6_factor_count"] == 0
        assert inverse.diagnostics["nested_iterative_ksp_count"] == 1
        assert inverse.diagnostics["nested_ksp_created_count"] == 1
        assert diagnostics["research_only"] is True
        assert inverse.diagnostics["last_apply"]["reason"] is None
        assert diagnostics["counts"]["JH"] == diagnostics["counts"]["pc"]
        assert diagnostics["counts"]["PH_audit"] == 2 * diagnostics["counts"]["pc"]
        assert diagnostics["counts"]["p4_backsolve"] == diagnostics["counts"]["Q"]
    finally:
        if expected is not None:
            expected.destroy()
        if expected2 is not None:
            expected2.destroy()
        q1_before.destroy()
        q2_before.destroy()
        q1.destroy()
        q2.destroy()
        y1.destroy()
        y2.destroy()
        y3.destroy()
        zero.destroy()
        zero_out.destroy()
        bad.destroy()
        bad_out.destroy()
        inverse.destroy()
        after_destroy = inverse.diagnostics
        assert after_destroy["p4_factor_live"] == 0
        assert after_destroy["p4_factor_created_count"] == 1
        assert after_destroy["p4_factor_destroy_count"] == 1
        assert after_destroy["direct_factor_count"] == 0
        assert after_destroy["nested_iterative_ksp_count"] == 0
        assert after_destroy["nested_ksp_created_count"] == 1
        assert after_destroy["nested_ksp_destroy_count"] == 1
        assert after_destroy["nested_ksp_current_live"] is False
        assert after_destroy["p4_factor"]["factor_destroy_count"] == 1
        assert after_destroy["p4_factor"]["research_factor"]["direct_factor_count"] == 0
        assert after_destroy["p4_factor"]["research_factor"]["factor_destroyed"] is True
        assert owned["full_action"].destroy_count == 1
        assert owned["p4_factor"].destroy_count == 1
        assert owned["transfer"].destroy_count == 1
        assert owned["h6"].destroy_count == 1
        assert operator.getSize() == (2, 2)
        operator.destroy()


def test_side_inverse_dense_batch_bound_and_true_error_propagation() -> None:
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        audit_callback=audit_records.append,
        detailed_timing=True,
    )
    operator = owned["operator"]
    comm = MPI.COMM_WORLD
    width = 3
    source_dense = PETSc.Mat().createDense(
        size=((operator.getOwnershipRange()[1] - operator.getOwnershipRange()[0], 2), width),
        comm=comm,
    )
    target_dense = source_dense.duplicate(copy=False)
    source_values = np.asarray(
        [
            [1.0 + 0.1j, 0.2 - 0.3j, -0.5 + 0.7j],
            [0.4 + 0.6j, -0.8 + 0.2j, 0.9 - 0.1j],
        ],
        dtype=np.complex128,
    )
    first, last = (int(value) for value in source_dense.getOwnershipRange())
    source_dense.getDenseArray()[:, :] = source_values[first:last, :]
    source_dense.assemble()
    original_dense = np.array(source_dense.getDenseArray(), copy=True)
    target_dense.zeroEntries()
    target_dense.assemble()
    try:
        inverse.apply_many(source_dense, target_dense)
        assert np.max(
            np.abs(target_dense.getDenseArray() - 0.5 * original_dense)
        ) <= 1.0e-12
        assert np.array_equal(source_dense.getDenseArray(), original_dense)
        too_wide = PETSc.Mat().createDense(
            size=((last - first, 2), 33),
            comm=comm,
        )
        too_wide.setUp()
        with pytest.raises(ValueError, match="batch aliasing"):
            inverse.apply_many(too_wide, too_wide)
        too_wide_target = too_wide.duplicate(copy=False)
        too_wide_target.zeroEntries()
        too_wide_target.assemble()
        with pytest.raises(ValueError, match="one to 32"):
            inverse.apply_many(too_wide, too_wide_target)
        too_wide_target.destroy()
        too_wide.destroy()

        old_h6 = inverse._h6
        inverse._h6 = _FailingH6()
        source = _new_vector(operator, np.asarray([1.0 + 0.2j, 0.4 - 0.1j]))
        target = operator.createVecLeft()
        try:
            with pytest.raises((RuntimeError, PETSc.Error)):
                inverse.apply(source, target)
            failed = inverse.diagnostics["last_apply"]
            assert failed["status"] == "FAILED"
            assert failed["exception_type"]
            assert failed["residual_norm"] == "not_measured"
            failed_timing = failed["operation_seconds"]["detailed"]
            assert failed_timing["measurement_status"]["q_ph_seconds"] == "measured"
            assert failed_timing["per_rank_seconds"]["q_ph_seconds"] > 0.0
            assert failed_timing["max_rank_seconds"] is None
            for name in (
                "q_ph_route_sort_index_seconds",
                "q_ph_duplicate_row_check_seconds",
                "balance_ph_route_sort_index_seconds",
                "balance_ph_duplicate_row_check_seconds",
            ):
                assert failed_timing["measurement_status"][name] == "not_called"
                assert failed_timing["per_rank_seconds"][name] is None
            assert (
                failed_timing["measurement_status"]["balance_h6_seconds"]
                == "measured"
            )
            assert audit_records[-1]["status"] == "FAILED"
        finally:
            source.destroy()
            target.destroy()
            inverse._h6 = old_h6
    finally:
        source_dense.destroy()
        target_dense.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_rhs_timing_uses_one_buffer_for_multiple_pc_calls() -> None:
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        audit_callback=audit_records.append,
        detailed_timing=True,
    )
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    target = operator.createVecLeft()
    coupling = inverse._coupling
    assert coupling is not None
    real_coupling_apply = coupling.apply
    operation_facts: list[dict[str, float]] = []

    def spy_coupling_apply(value: PETSc.Vec) -> PETSc.Vec:
        result = real_coupling_apply(value)
        operation_facts.append(
            dict(coupling.last_apply_facts["operation_seconds"])
        )
        return result

    coupling.apply = spy_coupling_apply  # type: ignore[method-assign]
    real_ksp = inverse._ksp
    real_comm = inverse._comm
    recording_comm = _BufferRecordingComm(real_comm)
    inverse._ksp = _RepeatedPcKsp(inverse)  # type: ignore[assignment]
    inverse._comm = recording_comm  # type: ignore[assignment]
    try:
        unmeasured = inverse._rhs_operation_timing(0.0, reduce=False)
        assert all(
            value is None
            for value in unmeasured["detailed"]["per_rank_seconds"].values()
        )
        assert all(
            status == "not_called"
            for status in unmeasured["detailed"]["measurement_status"].values()
        )
        inverse.apply(source, target)
        first_record = inverse.diagnostics["last_apply"]
        first_timing = first_record["operation_seconds"]
        assert first_record["status"] == "KSP_CONVERGED"
        assert first_record["counts"]["delta"]["pc"] == 2
        assert first_record["counts"]["delta"]["Q"] == 4
        assert first_record["counts"]["delta"]["H6"] == 2
        assert first_record["counts"]["delta"]["A6"] == 4
        assert owned["p4_factor"].solve_count == 4
        assert owned["h6"].apply_count == 2
        assert owned["full_action"].context.apply_count == 4
        assert owned["operator_context"].apply_count == 1
        assert recording_comm.scalar_allreduce_count == 1
        assert recording_comm.buffer_allreduce_count == 1
        assert first_timing["status"] == "measured_rank_max"
        assert set(first_timing["max_rank_accumulated_seconds"]) == {
            "Q",
            "H6",
            "A6",
        }
        assert "max_rank_total_seconds" not in first_timing
        assert first_timing["max_rank_uncovered_seconds"] >= 0.0
        first_operation_facts = operation_facts[:]
        assert len(first_operation_facts) == 2
        first_detail = first_timing["detailed"]
        assert first_detail["logging_rank"] == MPI.COMM_WORLD.Get_rank()
        assert first_detail["local_scope"] == "logging_rank_only"
        measured_names = (
            "q_ph_seconds",
            "q_ph_cell_adjoint_seconds",
            "q_ph_dual_reduce_seconds",
            "q_ph_mpi_exchange_seconds",
            "q_ph_ghost_mpc_prepare_seconds",
            "q_ph_ghost_mpc_check_seconds",
            "q_p_seconds",
            "q_p_local_candidate_generation_seconds",
            "q_p_route_sort_index_seconds",
            "q_p_mpi_exchange_seconds",
            "q_p_duplicate_row_check_seconds",
            "q_p_ghost_mpc_prepare_seconds",
            "q_p_ghost_mpc_check_seconds",
            "q_augmented_rhs_extract_seconds",
            "q_factor_solve_seconds",
            "q_a4_residual_refinement_seconds",
            "q_physical_action_matrix_mult_seconds",
            "balance_ph_seconds",
            "balance_ph_cell_adjoint_seconds",
            "balance_ph_dual_reduce_seconds",
            "balance_ph_mpi_exchange_seconds",
            "balance_ph_ghost_mpc_prepare_seconds",
            "balance_ph_ghost_mpc_check_seconds",
            "balance_a6_seconds",
            "balance_h6_seconds",
            "balance_jh_inject_allocate_seconds",
        )
        assert all(
            first_detail["measurement_status"][name] == "measured"
            for name in measured_names
        )
        not_called_names = (
            "q_ph_route_sort_index_seconds",
            "q_ph_duplicate_row_check_seconds",
            "balance_ph_route_sort_index_seconds",
            "balance_ph_duplicate_row_check_seconds",
        )
        assert all(
            first_detail["measurement_status"][name] == "not_called"
            and first_detail["max_rank_seconds"][name] is None
            for name in not_called_names
        )
        assert first_detail["max_rank_seconds"]["q_factor_solve_seconds"] == pytest.approx(
            4.0e-3
        )
        assert first_detail["max_rank_seconds"][
            "q_a4_residual_refinement_seconds"
        ] == pytest.approx(8.0e-3)
        assert first_detail["max_rank_seconds"][
            "q_physical_action_matrix_mult_seconds"
        ] == pytest.approx(1.2e-3)
        assert first_detail["max_rank_seconds"][
            "q_ph_mpi_exchange_seconds"
        ] == pytest.approx(1.6e-3)
        assert first_detail["max_rank_seconds"][
            "q_p_local_candidate_generation_seconds"
        ] == pytest.approx(4.0e-4)
        assert first_detail["max_rank_seconds"][
            "balance_ph_mpi_exchange_seconds"
        ] == pytest.approx(1.6e-3)
        assert first_detail["max_rank_seconds"][
            "balance_jh_inject_allocate_seconds"
        ] >= 0.0
        for name in ("Q", "H6", "A6"):
            assert first_timing["per_rank_accumulated_seconds"][name] == pytest.approx(
                sum(facts[name] for facts in operation_facts),
                rel=1.0e-12,
                abs=1.0e-12,
            )
        inverse.apply(source, target)
        second_record = inverse.diagnostics["last_apply"]
        second_timing = second_record["operation_seconds"]
        assert second_record["counts"]["delta"]["pc"] == 2
        assert second_record["counts"]["delta"]["Q"] == 4
        assert second_timing["detailed"]["max_rank_seconds"][
            "q_factor_solve_seconds"
        ] == pytest.approx(4.0e-3)
        assert second_timing["detailed"]["max_rank_seconds"][
            "q_a4_residual_refinement_seconds"
        ] == pytest.approx(8.0e-3)
        assert recording_comm.scalar_allreduce_count == 2
        assert recording_comm.buffer_allreduce_count == 2
        assert len(operation_facts) == 4
        for timing, facts in (
            (first_timing, first_operation_facts),
            (second_timing, operation_facts[2:]),
        ):
            for name in ("Q", "H6", "A6"):
                assert timing["per_rank_accumulated_seconds"][name] == pytest.approx(
                    sum(item[name] for item in facts),
                    rel=1.0e-12,
                    abs=1.0e-12,
                )
        assert owned["p4_factor"].solve_count == 8
        assert owned["h6"].apply_count == 4
        assert owned["full_action"].context.apply_count == 8
        assert owned["operator_context"].apply_count == 2
        assert len(audit_records) == 2
    finally:
        coupling.apply = real_coupling_apply  # type: ignore[method-assign]
        inverse._ksp = real_ksp
        inverse._comm = real_comm
        source.destroy()
        target.destroy()
        inverse.destroy()
        operator.destroy()


def test_side_inverse_preserves_current_nonfinite_p4_gate_audit() -> None:
    audit_records: list[dict[str, object]] = []
    failing_p4 = _NonfiniteP4(2)
    inverse, owned = _build_fixture(
        p4_factor=failing_p4,
        audit_callback=audit_records.append,
    )
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    source_before = source.copy()
    target = operator.createVecLeft()
    try:
        with pytest.raises((RuntimeError, PETSc.Error)):
            inverse.apply(source, target)
        record = inverse.diagnostics["last_apply"]
        assert record["status"] == "FAILED"
        assert record["failure_classification"] == "P4_PHYSICAL_RESIDUAL_GATE"
        assert record["relative_residual"] == "not_measured"
        assert record["p4_solve_audit"]["status"] == "failed_nonfinite_residual"
        assert np.isnan(record["p4_solve_audit"]["relative_residual"])
        assert record["p4_solve_audit"]["backsolve_count"] == 1
        assert _relative_difference(source, source_before) == 0.0
        assert audit_records[-1]["p4_solve_audit"]["rhs_norm"] > 0.0
    finally:
        source.destroy()
        source_before.destroy()
        target.destroy()
        inverse.destroy()
        operator.destroy()


def test_p4_physical_gate_audit_uses_each_real_vec_rhs() -> None:
    physical_matrix, physical_context = _scale_matrix(2, 2.0)
    augmented_matrix, _augmented_context = _scale_matrix(2, 1.0)
    physical_action = _PhysicalP4Action(physical_matrix)
    factor = _RefinementFactor()
    p4 = P4ExactFactor(
        physical_action=physical_action,
        matrix=augmented_matrix,
        factor=factor,
        factor_events=["created"],
    )
    rhs1 = _new_vector(physical_matrix, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    augmented_rhs1 = p4.create_rhs(rhs1)
    solution1 = augmented_rhs1.duplicate()
    solution1.set(0.0)
    rhs2 = _new_vector(physical_matrix, np.asarray([2.0 - 0.1j, 0.25 + 0.5j]))
    augmented_rhs2 = p4.create_rhs(rhs2)
    solution2 = augmented_rhs2.duplicate()
    solution2.set(0.0)
    rhs3 = _new_vector(physical_matrix, np.asarray([-0.3 + 0.6j, 0.9 - 0.2j]))
    augmented_rhs3 = p4.create_rhs(rhs3)
    solution3 = augmented_rhs3.duplicate()
    solution3.set(0.0)
    try:
        with pytest.raises(P4PhysicalResidualGateError) as first_failure:
            p4.solve_with_refinement(augmented_rhs1, solution1)
        first_audit = first_failure.value.audit
        assert first_audit["status"] == "failed_gate"
        assert first_audit["residual_norm"] == pytest.approx(rhs1.norm())
        assert first_audit["relative_residual"] == pytest.approx(1.0)
        assert first_audit["backsolve_count"] == 3
        assert first_audit["refinement_count"] == 2

        second_audit = p4.solve_with_refinement(augmented_rhs2, solution2)
        assert second_audit["status"] == "passed"
        assert second_audit["rhs_norm"] == pytest.approx(rhs2.norm())
        assert second_audit["rhs_norm"] != first_audit["rhs_norm"]
        assert second_audit["backsolve_count"] == 1
        assert second_audit["refinement_count"] == 0

        physical_context.scale = PETSc.ScalarType(np.nan)
        with pytest.raises(P4PhysicalResidualGateError) as nonfinite_failure:
            p4.solve_with_refinement(augmented_rhs3, solution3)
        nonfinite_audit = nonfinite_failure.value.audit
        assert nonfinite_audit["status"] == "failed_nonfinite_residual"
        assert np.isnan(nonfinite_audit["relative_residual"])
        assert nonfinite_audit["backsolve_count"] == 1
        assert nonfinite_audit["refinement_count"] == 0
        assert factor.solve_count == 5
        last_audit = p4.diagnostics["last_solve"]
        assert last_audit["status"] == "failed_nonfinite_residual"
        assert last_audit["backsolve_count"] == 1
    finally:
        rhs1.destroy()
        augmented_rhs1.destroy()
        solution1.destroy()
        rhs2.destroy()
        augmented_rhs2.destroy()
        solution2.destroy()
        rhs3.destroy()
        augmented_rhs3.destroy()
        solution3.destroy()
        p4.destroy()


@pytest.mark.parametrize(
    ("reason", "iterations", "accepted"),
    [
        (_DIVERGED_ITS, 128, True),
        (_DIVERGED_ITS, 127, False),
        (_DIVERGED_ITS, 129, False),
        (int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN), 128, False),
    ],
)
def test_side_inverse_fixed_ksp_budget_contract(
    reason: int,
    iterations: int,
    accepted: bool,
) -> None:
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(audit_callback=audit_records.append)
    operator = owned["operator"]
    source = _new_vector(operator, np.asarray([1.0 + 0.2j, -0.4 + 0.7j]))
    source_before = source.copy()
    target = operator.createVecLeft()
    approximate = source.copy()
    approximate.scale(0.25)
    real_ksp = inverse._ksp
    stub = _KspContractStub(approximate, reason, iterations)
    inverse._ksp = stub  # type: ignore[assignment]
    try:
        if accepted:
            inverse.apply(source, target)
            record = inverse.diagnostics["last_apply"]
            assert record["status"] == "INNER_APPROXIMATE_RETURN"
            assert record["reason"] == reason
            assert record["iterations"] == iterations
            assert record["ksp_positive"] is False
            assert record["explicit_true_target_reached"] is False
            assert record["relative_residual"] == pytest.approx(0.5)
            assert np.isfinite(record["residual_norm"])
            assert len(audit_records) == 1
            assert audit_records[0]["status"] == "INNER_APPROXIMATE_RETURN"
            assert _relative_difference(source, source_before) == 0.0
        else:
            with pytest.raises(RuntimeError):
                inverse.apply(source, target)
            record = inverse.diagnostics["last_apply"]
            assert record["status"] == "FAILED"
            assert record["reason"] == reason
            assert record["iterations"] == iterations
            assert record["explicit_true_target_reached"] == "not_measured"
            assert record["residual_norm"] == "not_measured"
            assert len(audit_records) == 1
            assert audit_records[0]["status"] == "FAILED"
            assert _relative_difference(source, source_before) == 0.0
    finally:
        inverse._ksp = real_ksp
        restored_real_ksp = inverse._ksp is real_ksp
        source.destroy()
        source_before.destroy()
        approximate.destroy()
        target.destroy()
        inverse.destroy()
        operator.destroy()
    assert restored_real_ksp is True
    assert inverse._ksp is None
