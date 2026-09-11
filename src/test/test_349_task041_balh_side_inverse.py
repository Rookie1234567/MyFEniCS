"""Focused small-PETSc checks for the H1e side BAL_H adapter."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

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

    def apply_adjoint(self, source: PETSc.Vec) -> PETSc.Vec:
        self.apply_count += 1
        return self._copy(source)

    def apply_primal(self, source: PETSc.Vec) -> PETSc.Vec:
        self.apply_count += 1
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
    ) -> dict[str, object]:
        del residual_tolerance
        rhs.copy(solution)
        self.solve_count += 1
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
    p4_factor = _IdentityP4(size)
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


def test_side_inverse_right_pc_reuse_zero_and_cleanup() -> None:
    checkpoint_calls: list[None] = []
    audit_records: list[dict[str, object]] = []
    inverse, owned = _build_fixture(
        checkpoint_callback=lambda: checkpoint_calls.append(None),
        audit_callback=audit_records.append,
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
    inverse, owned = _build_fixture(audit_callback=audit_records.append)
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
