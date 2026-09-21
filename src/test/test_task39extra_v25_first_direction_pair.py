"""Tiny wiring tests for the bounded V25 first-direction pair.

Real FE equivalence remains covered by the completed S1 evidence and the
formal same-factor check; these tests only exercise callback wiring and gates.
"""

from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.runners.physical_retained_outer_adapter import RetainedOuterAdapter


class _Runtime:
    def __init__(self):
        self.events = []

    def reserve_workspace(self, label, amount):
        self.events.append(("reserve_workspace", label, int(amount)))

    def release_workspace(self, label):
        self.events.append(("release_workspace", label))

    def reserve_inventory(self, label, components, **_kwargs):
        self.events.append(("reserve_inventory", label, dict(components)))

    def release_inventory(self, label):
        self.events.append(("release_inventory", label))


class _NativeB6:
    def __init__(self, *_args, **_kwargs):
        self._bilinear_form = object()
        self._function_space = object()
        self.audit = {
            "backend": "native_ffcx",
            "retained_numeric_payload_local_bytes": 128,
            "per_apply_bounded_temporary_bytes": 64,
        }
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


def _adapter(monkeypatch, *, unequal=False):
    runtime = _Runtime()
    adapter = RetainedOuterAdapter.__new__(RetainedOuterAdapter)
    adapter.runtime = runtime
    adapter.common = {
        "levels": {"floquets": {6: SimpleNamespace(mpc=object())}}
    }
    adapter.evidence_prefix = "test"
    adapter.count = {"schur_action": 0, "bridge": 0, "native_action": 0}
    adapter._active_role = "check"
    adapter.role_counts = {
        role: {key: 0 for key in adapter.count}
        for role in ("setup", "iteration", "check")
    }
    adapter.role_timings = {"setup": 0.0, "iteration": 0.0, "check": 0.0}
    adapter.identity = {}
    adapter.bridge = object()
    adapter._packet = lambda name, _facts: name

    candidate_b6 = SimpleNamespace(
        _bilinear_form=object(),
        _function_space=object(),
        audit={
            "retained_numeric_payload_local_bytes": 128,
            "per_apply_bounded_temporary_bytes": 64,
        },
    )
    shell = SimpleNamespace(action=candidate_b6)

    class _H6:
        apply_count = 0
        matrix_mult_count = 0

        def apply(self, _source):
            self.apply_count += 1
            self.matrix_mult_count += 2
            return None

    h6 = _H6()
    saved_a = object()
    saved_ledger_a = object()
    saved_s = object()
    candidate_a6 = lambda _x: None
    native_a6 = lambda _x: None
    pc = SimpleNamespace(
        balanced=SimpleNamespace(
            A=saved_a,
            S=saved_s,
            total_counts={
                "C": 0,
                "smoother": 0,
                "A_structure": 0,
                "A_inner_true": 0,
                "PH_audit": 0,
            },
        ),
        ledger=SimpleNamespace(
            A=saved_ledger_a,
            A_count=0,
            PH_count=0,
            audit_count=0,
        ),
        apply_count=0,
        native_A4_count=0,
        last_apply_facts={
            "counts": {"C": 1},
            "operation_seconds": {"C": 0.0},
        },
        coarse_calls=[{"p4_mat_solve_count": 2}],
        _candidate_a6_callback=candidate_a6,
        _native_a6_callback=native_a6,
        _candidate_h6_callback=h6.apply,
    )
    native_holder = {"object": None}

    def fake_pc(source):
        adapter.count["bridge"] += 1
        pc.apply_count += 1
        pc.native_A4_count += 1
        h6.apply_count += 1
        h6.matrix_mult_count += 2
        result = source.duplicate()
        source.copy(result)
        if unequal and pc.balanced.A is native_a6 and shell.action is native_holder["object"]:
            result.array[0] += 1.0
        return result

    adapter._pc = fake_pc
    adapter.rhs = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    adapter.rhs.array[:] = [1.0, 2.0j, -0.5, 0.25j]
    adapter.first_direction_pair_context = {
        "pc": pc,
        "positive": {
            "p6_shell": shell,
            "h6": h6,
            "light_facts": {
                "seed_sha256": "a" * 64,
                "diagonal_sha256": "b" * 64,
                "inverse_sqrt_diagonal_sha256": "c" * 64,
                "power_history": [1.0],
                "lambda_power10": 1.0,
                "lambda_lo": 0.1,
                "lambda_hi": 10.0,
            },
        },
    }
    monkeypatch.setattr(
        "src.solvers.fullspace_mpc_action.FullspaceMpcFormAction", _NativeB6
    )
    native_holder["object"] = None

    original_constructor = _NativeB6

    def constructor(*args, **kwargs):
        result = original_constructor(*args, **kwargs)
        native_holder["object"] = result
        return result

    monkeypatch.setattr(
        "src.solvers.fullspace_mpc_action.FullspaceMpcFormAction", constructor
    )
    return adapter, runtime, shell, candidate_b6, pc, saved_a, saved_ledger_a, saved_s


def test_first_direction_pair_reuses_callbacks_and_releases_temporary_b6(monkeypatch):
    adapter, runtime, shell, candidate_b6, pc, saved_a, saved_ledger_a, saved_s = _adapter(
        monkeypatch
    )
    try:
        result = adapter.actual_first_arnoldi_check()
        assert result["passed"]
        assert result["input_norm"] == pytest.approx(1.0)
        assert result["pair"]["passed"]
        assert len(result["pair"]["variants"]) == 4
        assert result["pair"]["same_input"]
        assert (
            result["pair"]["variants"]["candidate_a6_candidate_h6"][
                "output_identity"
            ]
            == result["pair"]["input_identity"]
        )
        assert adapter.first_direction_pair_context is None
        assert shell.action is candidate_b6
        assert pc.balanced.A is saved_a
        assert pc.ledger.A is saved_ledger_a
        assert pc.balanced.S is saved_s
        assert any(event[0] == "release_workspace" for event in runtime.events)
        assert any(event[0] == "release_inventory" for event in runtime.events)
    finally:
        adapter.rhs.destroy()


def test_first_direction_pair_rejects_non_equivalent_combination(monkeypatch):
    adapter, _runtime, shell, candidate_b6, pc, saved_a, saved_ledger_a, saved_s = _adapter(
        monkeypatch, unequal=True
    )
    try:
        with pytest.raises(RuntimeError):
            adapter.actual_first_arnoldi_check()
        assert shell.action is candidate_b6
        assert pc.balanced.A is saved_a
        assert pc.ledger.A is saved_ledger_a
        assert pc.balanced.S is saved_s
        assert adapter.first_direction_pair_context is None
    finally:
        adapter.rhs.destroy()
