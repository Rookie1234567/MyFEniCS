from dataclasses import replace

import pytest

from src.solvers import dtn_port_3d
from src.solvers.dtn_port_3d import (
    Stage4ExternalLinearSolverSnapshot,
    _dispatch_external_linear_solver,
    _external_snapshot_allows_official_rta,
)


class _FakeMat:
    def getSize(self) -> tuple[int, int]:
        return (3, 3)

    def getOwnershipRange(self) -> tuple[int, int]:
        return (0, 3)


class _FakeVec:
    def __init__(self, size: int = 3, ownership: tuple[int, int] = (0, 3)):
        self.size = size
        self.ownership = ownership

    def getSize(self) -> int:
        return self.size

    def getOwnershipRange(self) -> tuple[int, int]:
        return self.ownership


def _snapshot(
    solution: _FakeVec,
    residuals=(1.0e-12, 2.0e-12, 3.0e-12),
    *,
    reason=1,
    no_global_factor=True,
) -> Stage4ExternalLinearSolverSnapshot:
    return Stage4ExternalLinearSolverSnapshot(
        solution,
        reason,
        4,
        residuals[0],
        residuals[1],
        residuals[2],
        "synthetic",
        "none",
        1.0e-9,
        no_global_factor,
    )


def test_dispatch_borrows_system_and_does_not_call_direct(monkeypatch) -> None:
    matrix, solution, rhs = _FakeMat(), _FakeVec(), object()
    sentinels = tuple(object() for _ in range(4))
    seen = {}
    monkeypatch.setattr(
        dtn_port_3d,
        "_solve_augmented_system",
        lambda *_args, **_kwargs: pytest.fail("direct solve was called"),
    )

    def port(request):
        seen.update(A=request.A, b=request.b, n_fe=request.n_fe, n_aux=request.n_aux)
        assert request.static_condensed_system is sentinels[0]
        assert request.function_space is sentinels[1]
        assert request.config is sentinels[2]
        assert request.floquet_data is sentinels[3]
        return _snapshot(solution)

    accepted = _dispatch_external_linear_solver(
        matrix,
        rhs,
        n_fe=2,
        n_aux=1,
        static_condensed_system=sentinels[0],
        function_space=sentinels[1],
        config=sentinels[2],
        floquet_data=sentinels[3],
        port=port,
    )
    assert accepted.x is solution
    assert seen == {"A": matrix, "b": rhs, "n_fe": 2, "n_aux": 1}


@pytest.mark.parametrize(
    ("no_global_factor", "x"),
    ((False, _FakeVec()), (True, _FakeVec(size=2, ownership=(0, 2)))),
)
def test_dispatch_rejects_snapshot_contract_violations(no_global_factor, x) -> None:
    snapshot = replace(_snapshot(_FakeVec()), no_global_factor=no_global_factor, x=x)
    with pytest.raises(ValueError):
        _dispatch_external_linear_solver(
            _FakeMat(),
            object(),
            n_fe=2,
            n_aux=1,
            static_condensed_system=object(),
            function_space=object(),
            config=object(),
            floquet_data=object(),
            port=lambda _request: snapshot,
        )


@pytest.mark.parametrize(
    ("reason", "residuals", "full_fe", "expected"),
    [
        (1, (1.0e-12, 2.0e-12, 3.0e-12), 4.0e-12, True),
        (0, (1.0e-12, 2.0e-12, 3.0e-12), 4.0e-12, False),
        (1, (None, 2.0e-12, 3.0e-12), 4.0e-12, False),
        (1, (float("nan"), 2.0e-12, 3.0e-12), 4.0e-12, False),
        (1, (1.0e-12, 2.0e-12, 3.0e-12), 2.0e-9, False),
    ],
)
def test_external_rta_gate_is_fail_closed(reason, residuals, full_fe, expected) -> None:
    snapshot = _snapshot(_FakeVec(), residuals, reason=reason)
    assert _external_snapshot_allows_official_rta(snapshot, full_fe) is expected
