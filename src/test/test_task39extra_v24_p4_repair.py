"""Focused V24 tests for bounded p4 repair and count semantics."""

from __future__ import annotations

import json

import numpy as np
import pytest

from petsc4py import PETSc

from src.solvers.physical_interface_balanced import (
    InterfaceBalancedCoupling,
    P4ResidualRepairPolicy,
    P4ResidualRepairRejected,
)


def _vec(values):
    result = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
    result.array[:] = np.asarray(values, dtype=np.complex128)
    result.assemble()
    return result


def _copy(value):
    result = value.duplicate()
    result.array[:] = value.array
    result.assemble()
    return result


class _IdentityTransfer:
    def apply_adjoint(self, value):
        return _copy(value)

    def apply_primal(self, value):
        return _copy(value)


class _SequenceFint:
    """First solve is deliberately inexact; the next one solves its RHS."""

    def __init__(self, *, fail=False, with_port=False):
        self.fail = fail
        self.with_port = with_port
        self.apply_count = 0
        self.logical_apply_count = 0
        self.logical_apply_attempt_count = 0
        self.local_count = 0
        self._last_port_solution = np.zeros(1 if with_port else 0, dtype=np.complex128)

    @property
    def last_port_solution(self):
        return self._last_port_solution

    @last_port_solution.setter
    def last_port_solution(self, value):
        self._last_port_solution = np.asarray(value, dtype=np.complex128).copy()

    def begin_logical_apply(self):
        self.logical_apply_attempt_count += 1
        self.local_count = 0

    def complete_logical_apply(self):
        self.logical_apply_count += 1

    def apply_with_facts(self, rhs):
        self.apply_count += 1
        self.local_count += 1
        result = _copy(rhs)
        if self.local_count == 1:
            result.set(PETSc.ScalarType(0.0))
            port = 0.25 if self.with_port else 0.0
        else:
            if self.fail:
                result.set(PETSc.ScalarType(0.0))
            port = 0.75 if self.with_port else 0.0
        result.assemble()
        self.last_port_solution = np.asarray([port], dtype=np.complex128) if self.with_port else np.empty(0, dtype=np.complex128)
        return result, {
            "factor_solve_call_delta": 1,
            "fixture_local_apply": self.local_count,
        }


class _NonHermitianCoupledFint:
    """Small complex Bi/Di/H fixture with a nonzero internal RHS.

    The first F4 result has a deliberately chosen defect whose port equation
    is already closed.  Applying F4 to the native top residual therefore
    returns exactly that defect, making the cumulative FE/port repair
    verifiable against the full augmented matrix.
    """

    def __init__(self, V, B, D, H):
        self.V, self.B, self.D, self.H = V, B, D, H
        self.matrix = np.block([[V, B], [-D, H]])
        self.defect_c = np.asarray([0.03 + 0.02j, -0.04 + 0.01j])
        self.defect_alpha = np.linalg.solve(H, D @ self.defect_c)
        self._last_port_solution = np.zeros(H.shape[0], dtype=np.complex128)
        self.local_count = 0
        self.apply_count = 0
        self.solve_calls = 0
        self.logical_apply_count = 0
        self.logical_apply_attempt_count = 0

    @property
    def last_port_solution(self):
        return self._last_port_solution

    @last_port_solution.setter
    def last_port_solution(self, value):
        self._last_port_solution = np.asarray(value, dtype=np.complex128).copy()

    def begin_logical_apply(self):
        self.logical_apply_attempt_count += 1
        self.local_count = 0

    def complete_logical_apply(self):
        self.logical_apply_count += 1

    def apply_with_facts(self, rhs):
        self.apply_count += 1
        self.local_count += 1
        values = np.asarray(rhs.array, dtype=np.complex128).copy()
        result = _vec(np.zeros_like(values))
        if not np.any(values):
            self.last_port_solution = np.zeros_like(self.last_port_solution)
            return result, {"factor_solve_call_delta": 0, "zero_rhs": True}
        self.solve_calls += 1
        exact = np.linalg.solve(
            self.matrix,
            np.concatenate((values, np.zeros(self.H.shape[0], dtype=np.complex128))),
        )
        if self.local_count == 1:
            result.array[:] = exact[: values.size] - self.defect_c
            self.last_port_solution = exact[values.size :] - self.defect_alpha
        else:
            result.array[:] = self.defect_c
            self.last_port_solution = self.defect_alpha
        result.assemble()
        return result, {
            "factor_solve_call_delta": 1,
            "zero_rhs": False,
            "nonhermitian_coupling": True,
        }


def _pc(
    fint,
    *,
    policy=None,
    capture_vectors=False,
    sink=None,
    fine_action=None,
    p4_action=None,
    h6=None,
    transfer=None,
    logical_apply_hook=None,
):
    if transfer is None:
        transfer = _IdentityTransfer()
    if fine_action is None:
        fine_action = lambda value: _copy(value)
    if p4_action is None:
        p4_action = lambda value: _copy(value)
    if h6 is None:
        h6 = lambda value: _vec(np.zeros(value.getSize(), dtype=np.complex128))
    return InterfaceBalancedCoupling(
        fine_action,
        p4_action,
        transfer,
        fint,
        h6,
        save=lambda *_args: None,
        capture_vectors=capture_vectors,
        repair_policy=policy,
        repair_vector_sink=sink,
        logical_apply_hook=logical_apply_hook,
    )


def test_default_path_is_one_logical_call_without_capture_attribute_error():
    fint = _SequenceFint()
    pc = _pc(fint)
    source = _vec([1.0 + 0.5j, -2.0j])
    try:
        result = pc.apply(source)
        try:
            assert result.norm() == 0.0
        finally:
            result.destroy()
        assert len(pc.coarse_calls) == 2
        assert all(call["p4_logical_apply_count"] == 1 for call in pc.coarse_calls)
        assert all(call["repair"]["extra_solve_count"] == 0 for call in pc.coarse_calls)
        assert all(call["p4_mat_solve_count"] == 1 for call in pc.coarse_calls)
        assert pc.native_A4_count == 2
        assert pc.native_A4_seconds > 0.0
        assert fint.apply_count == 2
        assert fint.logical_apply_count == 2
    finally:
        pc.destroy()
        source.destroy()


def test_bounded_repair_counts_solves_not_new_logical_p4_and_accumulates_port():
    fint = _SequenceFint(with_port=True)
    pc = _pc(
        fint,
        policy=P4ResidualRepairPolicy(
            enabled=True, residual_limit=1.0e-10, max_extra_solves=2
        ),
        capture_vectors=True,
    )
    source = _vec([1.0 + 0.5j, -2.0j])
    try:
        result = pc.apply(source)
        try:
            np.testing.assert_allclose(result.array, source.array)
        finally:
            result.destroy()
        assert len(pc.coarse_calls) == 2
        assert pc.coarse_calls[0]["p4_logical_apply_count"] == 1
        assert pc.coarse_calls[0]["p4_mat_solve_count"] == 2
        assert pc.coarse_calls[0]["native_A4_actions"] == 2
        assert pc.coarse_calls[0]["repair"]["extra_solve_count"] == 1
        assert pc.coarse_calls[0]["repair"]["logical_p4_apply_count"] == 1
        assert pc.coarse_calls[0]["repair"]["actual_mat_solve_count"] == 2
        assert pc.coarse_calls[0]["repair"]["status"] == "PASS"
        assert pc.coarse_calls[1]["p4_logical_apply_count"] == 1
        assert pc.coarse_calls[1]["p4_mat_solve_count"] == 1
        assert pc.coarse_calls[1]["native_A4_actions"] == 1
        assert pc.coarse_calls[1]["repair"]["extra_solve_count"] == 0
        assert pc.coarse_calls[1]["repair"]["status"] == "NOT_NEEDED"
        assert fint.apply_count == 3
        assert fint.logical_apply_count == 2
        assert pc.native_A4_count == 3
        assert len(pc.last_apply_vectors["p4_repair_calls"]) == 3
        first_repair = next(
            item
            for item in pc.last_apply_vectors["p4_repair_calls"]
            if item["logical_call"] == 1 and item["phase"] == "correction_1"
        )
        np.testing.assert_allclose(first_repair["alpha"], [1.0])
    finally:
        pc.destroy()
        source.destroy()


def test_logical_count_accumulates_across_pc_applications_but_records_recent_calls():
    from types import SimpleNamespace

    from src.runners.physical_p4_schur_v14 import _pc_count_facts

    fint = _SequenceFint()
    pc = _pc(
        fint,
        policy=P4ResidualRepairPolicy(enabled=True, max_extra_solves=2),
    )
    source = _vec([1.0 + 0.5j, -2.0j])
    try:
        for _ in range(2):
            result = pc.apply(source)
            result.destroy()
        assert pc.successful_logical_apply_count == 4
        assert len(pc.coarse_calls) == 2
        facts = _pc_count_facts(
            pc,
            {"inverse": SimpleNamespace(solve_count=fint.apply_count)},
            {"h6": SimpleNamespace(apply_count=0)},
            P4ResidualRepairPolicy(enabled=True, max_extra_solves=2),
        )
        assert facts["p4_logical_apply_count"] == 4
        assert facts["p4_recent_logical_apply_count"] == 2
        assert [row["p4_logical_apply_sequence"] for row in facts["p4_call_records"]] == [3, 4]
    finally:
        pc.destroy()
        source.destroy()


def test_prefix_stop_hook_stops_after_total_logical_three_and_destroys_output():
    from src.runners.physical_dual_cell_condensed_lowmem_v20 import V24P4PrefixStop

    class _TrackingTransfer(_IdentityTransfer):
        def __init__(self):
            self.primal_outputs = []

        def apply_primal(self, value):
            result = _copy(value)
            self.primal_outputs.append(result)
            return result

    transfer = _TrackingTransfer()
    hook_facts = []

    def stop_after_target(facts, _repair_vectors):
        hook_facts.append(dict(facts))
        if facts["p4_logical_apply_sequence"] == 3:
            raise V24P4PrefixStop(
                {"target_logical_call_sequence": 3, "stop_point": "test"}
            )

    fint = _SequenceFint()
    pc = _pc(
        fint,
        policy=P4ResidualRepairPolicy(enabled=True, max_extra_solves=2),
        transfer=transfer,
        logical_apply_hook=stop_after_target,
    )
    source = _vec([1.0 + 0.5j, -2.0j])
    try:
        first = pc.apply(source)
        first.destroy()
        with pytest.raises(V24P4PrefixStop, match="before the next coarse"):
            pc.apply(source)
        assert [item["p4_logical_apply_sequence"] for item in hook_facts] == [1, 2, 3]
        assert hook_facts[-1]["p4_logical_apply_cumulative_count"] == 3
        assert pc.successful_logical_apply_count == 3
        assert fint.logical_apply_count == 3
        assert len(pc.coarse_calls) == 1
        assert transfer.primal_outputs[-1].handle == 0
    finally:
        pc.destroy()
        source.destroy()


def test_targeted_capture_keeps_raw_vectors_even_when_native_gate_passes():
    captured = []
    fint = _SequenceFint()
    pc = _pc(
        fint,
        policy=P4ResidualRepairPolicy(enabled=True, max_extra_solves=2),
        sink=captured.append,
    )
    pc.repair_vector_capture = lambda facts: (
        facts["logical_call_sequence"] == 1 and facts["phase"] == "raw"
    )
    source = _vec([0.0, 0.0])
    try:
        result = pc.apply(source)
        result.destroy()
        selected = next(
            item
            for item in captured
            if item["logical_call_sequence"] == 1 and item["phase"] == "raw"
        )
        assert "g" in selected and "correction" in selected
        assert any(
            item["logical_call_sequence"] == 1 and item["phase"] == "raw"
            for item in pc.last_apply_vectors["p4_repair_calls"]
        )
    finally:
        pc.destroy()
        source.destroy()


def test_prefix_diagnostic_packet_preserves_named_vectors_and_writer_array_map(tmp_path):
    from src.runners.physical_diagnosis_worker import save_packet

    names = (
        "native_A4_residual",
        "native_volume_top_residual",
        "augmented_top_residual",
        "port_residual",
    )
    vectors = {
        name: np.asarray([index + 1j * (index + 1)], dtype=np.complex128)
        for index, name in enumerate(names)
    }
    save_packet(
        tmp_path,
        "v24_prefix_diagnostic",
        {"schema": "task039extra.v24.p4-prefix-diagnostic.v1", "diagnostic_vectors": vectors},
    )
    record = json.loads((tmp_path / "v24_prefix_diagnostic.json").read_text())
    assert set(record["diagnostic_vectors"]) == set(names)
    assert set(record["arrays"]) == {"path", "sha256"}
    with np.load(tmp_path / "v24_prefix_diagnostic.npz", allow_pickle=False) as packet:
        for name in names:
            descriptor = record["diagnostic_vectors"][name]
            assert descriptor["array_key"] in packet.files
            np.testing.assert_array_equal(packet[descriptor["array_key"]], vectors[name])


def test_bounded_repair_preserves_negative_after_two_extra_solves():
    saved = []
    fint = _SequenceFint(fail=True)
    pc = _pc(
        fint,
        policy=P4ResidualRepairPolicy(enabled=True, max_extra_solves=2),
        sink=saved.append,
    )
    source = _vec([1.0, 2.0])
    try:
        with pytest.raises(P4ResidualRepairRejected):
            pc.apply(source)
        assert len(pc.coarse_calls) == 0
        assert fint.logical_apply_count == 0
        assert fint.apply_count == 3
        assert any(item.get("schema") == "task039extra.v24.p4-repair-failure.v1" for item in saved)
    finally:
        pc.destroy()
        source.destroy()


def test_nonfinite_rhs_is_saved_before_fint_or_native_action():
    saved = []
    fint = _SequenceFint()
    pc = _pc(fint, policy=P4ResidualRepairPolicy(enabled=True, max_extra_solves=2), sink=saved.append)
    source = _vec([np.nan, 1.0])
    try:
        with pytest.raises(FloatingPointError, match="non-finite p4 repair state"):
            pc.apply(source)
        assert fint.apply_count == 0
        assert pc.native_A4_count == 0
        assert saved[0]["phase"] == "source_rhs"
    finally:
        pc.destroy()
        source.destroy()


def test_complex_nonhermitian_bidi_port_repair_accumulates_augmented_state():
    V = np.asarray(
        [[3.0 + 0.4j, 0.2 - 0.3j], [1.1 + 0.5j, 2.4 - 0.2j]],
        dtype=np.complex128,
    )
    B = np.asarray([[0.7 + 0.1j], [-0.2 + 0.4j]], dtype=np.complex128)
    D = np.asarray([[0.3 - 0.5j, 0.8 + 0.2j]], dtype=np.complex128)
    H = np.asarray([[1.7 + 0.2j]], dtype=np.complex128)
    fint = _NonHermitianCoupledFint(V, B, D, H)
    reduced_native = V + B @ np.linalg.solve(H, D)
    pc = _pc(
        fint,
        policy=P4ResidualRepairPolicy(enabled=True, max_extra_solves=2),
        capture_vectors=True,
        fine_action=lambda value: _vec(reduced_native @ value.array),
        p4_action=lambda value: _vec(reduced_native @ value.array),
    )
    source = _vec([0.8 + 0.4j, -0.6 + 0.9j])
    original = source.array.copy()
    try:
        result = pc.apply(source)
        result.destroy()
        snapshot = next(
            item
            for item in pc.last_apply_vectors["p4_repair_calls"]
            if item["logical_call"] == 1 and item["phase"] == "correction_1"
        )
        augmented = fint.matrix @ np.concatenate(
            (snapshot["correction"], snapshot["alpha"])
        )
        np.testing.assert_allclose(
            augmented,
            np.concatenate((original, np.zeros(H.shape[0], dtype=np.complex128))),
            rtol=2.0e-12,
            atol=2.0e-12,
        )
        np.testing.assert_array_equal(source.array, original)
        assert fint.solve_calls == 2
        assert fint.apply_count == 3
        assert fint.logical_apply_count == 2
        assert pc.coarse_calls[0]["repair"]["extra_solve_count"] == 1
        assert pc.coarse_calls[1]["p4_mat_solve_count"] == 0
        assert pc.coarse_calls[1]["repair"]["extra_solve_count"] == 0
    finally:
        pc.destroy()
        source.destroy()
