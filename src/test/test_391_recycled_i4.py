"""Focused pure-array tests for the opt-in V8 GCROT adapter."""

import copy
import json
from pathlib import Path
import numpy as np
import pytest

from src.solvers.physical_recycled_i4 import (
    BoundedGCROTI4,
    CLOSURE_LIMIT,
    FIXED_NEW16_PAYLOAD_BYTES,
    FIXED_NEW16_RECYCLE8,
    GCROT_ATOL,
    GCROT_K,
    GCROT_M,
    GCROT_MAXITER,
    GCROT_TOL,
    MAX_NEW_B4,
    MAX_NEW_DIRECTIONS,
    MAX_POOL_PAIRS,
    POOL_NUMERIC_BYTES_P4_DERIVED,
    RANK_THRESHOLD,
    RECYCLING_EXTRA_BYTES_LIMIT,
    V8_FIXED_M8_RECYCLE8,
    RecycledI4Error,
    VerifiedRecyclingPool,
    gcrotmk_backend_facts,
)


def _problem(size=16, *, shift=None):
    rng = np.random.default_rng(391039)
    matrix = rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))
    shift = 4 * size if shift is None else shift
    matrix = np.asarray(matrix + shift * np.eye(size), dtype=np.complex128)
    return matrix, rng


V8_K1_ROOT = (Path(__file__).resolve().parents[2] / 'benchmarks' / 'artifacts' /
              'task39extra' / 'v8_k1_controls' /
              '09c1b3a6f3c21d4d0e99feb36a97972819971fb3' / 'controls')


def test_v8_backend_is_the_qualified_local_gcrotmk():
    facts = gcrotmk_backend_facts()
    assert facts["backend"] == "scipy.sparse.linalg.gcrotmk"
    assert all(name in facts["signature"] for name in (
        "tol", "maxiter", "m", "k", "CU", "discard_C", "truncate", "atol"))
    assert facts["source_sha256"]
    assert facts["required_parameters"] == [
        "CU", "atol", "discard_C", "k", "m", "maxiter", "tol", "truncate"]


def test_v9_fixed_new16_uses_one_new_work_budget_on_a_nonhermitian_complex_fixture():
    """The opt-in policy keeps SciPy ml at 16 while V8 remains unchanged."""

    matrix, rng = _problem(48, shift=2)
    adapter = BoundedGCROTI4(
        lambda value: matrix @ value,
        lambda value: value.copy(),
        validation_action=lambda value: matrix @ value,
        model_identity={"case": "tiny-v9", "operator": "nonhermitian"},
        policy=FIXED_NEW16_RECYCLE8,
    )
    try:
        observed_ranks = set()
        for _ in range(10):
            rhs = np.asarray(rng.normal(size=48) + 1j * rng.normal(size=48),
                             dtype=np.complex128)
            original = rhs.copy()
            facts = adapter.solve(rhs)["facts"]
            rank = facts["effective_pool_rank"]
            observed_ranks.add(rank)
            assert facts["policy"] == FIXED_NEW16_RECYCLE8
            assert facts["m_call"] == 16 - max(8 - rank, 0)
            assert facts["gcrot_inner_dimension"] == 16
            assert facts["requested_new_B4"] == 16
            assert facts["requested_new_arnoldi_directions"] == 16
            assert facts["status"] == "INNER_APPROXIMATE_RETURN"
            assert facts["stop_reason"] == "MAXITER_ONE"
            assert facts["B4_calls"] == 16
            assert facts["completed_new_arnoldi_directions"] == 16
            assert facts["rejected_new_B4_callbacks"] == 0
            assert not facts["work_policy_violation"]
            assert facts["recycling_memory"]["cap_bytes"] == FIXED_NEW16_PAYLOAD_BYTES
            assert facts["recycling_memory"]["cap_passed"]
            assert facts["recycling_memory"]["payload_ledger"]["cap_bytes"] == FIXED_NEW16_PAYLOAD_BYTES
            assert facts["recycling_memory"]["payload_ledger"]["search_vectors_bytes"] > 0
            assert facts["recycling_memory"]["payload_ledger"]["index_payload_bytes"] > 0
            assert facts["recycling_memory"]["scipy_small_matrix_bound"] == (
                4 * (16 + 2) * (GCROT_K + 2) * 16)
            assert np.array_equal(rhs, original)
        assert observed_ranks == set(range(9))
        assert adapter.snapshot()["fixed"]["policy"] == FIXED_NEW16_RECYCLE8
        assert adapter.snapshot()["fixed"]["extra_bytes_limit"] == FIXED_NEW16_PAYLOAD_BYTES
    finally:
        adapter.destroy()


def test_v9_rank_legalization_discards_correlated_old_columns_before_m_call():
    matrix, rng = _problem(48, shift=2)
    pool = VerifiedRecyclingPool("tiny-v9-rank")
    seed = np.zeros(48, dtype=np.complex128)
    seed[0] = 1.0
    image = matrix @ seed
    scale = np.linalg.norm(image)
    seed /= scale
    image /= scale
    pool.replace([(seed.copy(), image.copy()) for _ in range(MAX_POOL_PAIRS)],
                 closure_errors=[0.0] * MAX_POOL_PAIRS)
    adapter = BoundedGCROTI4(
        lambda value: matrix @ value,
        lambda value: value.copy(),
        validation_action=lambda value: matrix @ value,
        model_identity="tiny-v9-rank",
        pool=pool,
        policy=FIXED_NEW16_RECYCLE8,
    )
    try:
        rhs = np.asarray(rng.normal(size=48) + 1j * rng.normal(size=48),
                         dtype=np.complex128)
        facts = adapter.solve(rhs)["facts"]
        assert facts["pool_before"] == MAX_POOL_PAIRS
        assert facts["effective_pool_rank"] == 1
        assert facts["discarded_pool_directions"] == MAX_POOL_PAIRS - 1
        assert facts["m_call"] == 9
        assert facts["gcrot_inner_dimension"] == 16
        assert facts["requested_new_B4"] == 16
        assert facts["B4_calls"] == 16
        assert facts["requested_new_B4_callbacks"] == 16
        assert facts["rejected_new_B4_callbacks"] == 0
        assert not facts["work_policy_violation"]
    finally:
        adapter.destroy()


def test_v9_rejects_a_seventeenth_callback_and_the_petsc_bridge_blocks_it(monkeypatch):
    from scipy.sparse import linalg as sparse_linalg
    from src.solvers.physical_bounded_policy import RecycledI4Admission

    class FakeComm:
        @staticmethod
        def getSize():
            return 1

    class FakeVec:
        def __init__(self, size):
            self.array = np.zeros(size, dtype=np.complex128)
            self._comm = FakeComm()
            self.destroyed = False

        def getComm(self):
            return self._comm

        def getLocalSize(self):
            return self.array.size

        def getSize(self):
            return self.array.size

        def duplicate(self):
            return FakeVec(self.array.size)

        def set(self, value):
            self.array.fill(value)

        def destroy(self):
            self.destroyed = True

    saved = []

    def identity(vector):
        output = vector.duplicate()
        output.array[:] = vector.array
        return output

    def overrun(_operator, rhs, *, M, **_kwargs):
        for _ in range(17):
            M.matvec(np.ones_like(rhs))
        raise AssertionError("the seventeenth callback was not rejected")

    admission = RecycledI4Admission(
        identity, identity, residual_action=identity,
        model_identity="tiny-v9-overrun", independent_indices=np.arange(4),
        sample=lambda: None,
        save=lambda name, facts: saved.append((name, facts)),
        stop_requested=lambda: False,
        policy=FIXED_NEW16_RECYCLE8,
    )
    # Backend provenance is captured at construction; replace only the call
    # used by this focused overrun probe.
    monkeypatch.setattr(sparse_linalg, "gcrotmk", overrun)
    rhs = FakeVec(4)
    rhs.array[:] = [1 + .2j, -2 + .1j, .3 - .4j, 2 - .7j]
    try:
        with pytest.raises(RuntimeError, match="implementation blocked"):
            admission(rhs)
        assert saved and saved[-1][0] == "recycled_i4_work_policy_violation"
        facts = saved[-1][1]["facts"]
        assert facts["requested_new_B4_callbacks"] == 17
        assert facts["rejected_new_B4_callbacks"] == 1
        assert facts["completed_new_B4"] == 16
        assert facts["work_policy_violation"] is True
        assert facts["pool_after"] == 0
    finally:
        rhs.destroy()
        admission.destroy()


def _v9_l1_sequence_facts(residual, seconds, *, completed=16,
                           stop_reason='MAXITER_ONE'):
    target = residual <= 1e-4
    return dict(
        status='INNER_TARGET_REACHED' if target else 'INNER_APPROXIMATE_RETURN',
        policy=FIXED_NEW16_RECYCLE8, requested_new_B4=16,
        requested_new_arnoldi_directions=16,
        requested_new_B4_callbacks=completed, attempted_B4=completed,
        completed_B4=completed, completed_new_B4=completed,
        attempted_new_arnoldi_directions=completed,
        completed_new_arnoldi_directions=completed,
        actual_arnoldi_length=completed,
        discarded_new_B4=16 - completed,
        discarded_new_arnoldi_directions=16 - completed,
        rejected_new_B4_callbacks=0, implementation_blocked=False,
        work_policy_violation=False, input_unchanged=True,
        recycling_memory={'cap_passed': True}, final_true_residual=residual,
        actual_elapsed_seconds=seconds, seconds=seconds,
        timeout_exceeded=False, requested_safe_return=False,
        stop_reason=stop_reason, pool_update='committed',
    )


def _v9_l1_sequences(reset_values, carry_values, *, completed=16,
                     reset_times=None, carry_times=None):
    reset_times = reset_times or [10.0] * len(reset_values)
    carry_times = carry_times or [5.0] * len(carry_values)

    def records(values, times):
        return [dict(sequence_index=index, stem=f'stem-{index}',
                     g_array_sha256=f'g-{index}', status='complete',
                     facts=_v9_l1_sequence_facts(value, times[index - 1],
                                                  completed=completed))
                for index, value in enumerate(values, 1)]

    return dict(reset={'records': records(reset_values, reset_times)},
                carry={'records': records(carry_values, carry_times)})


@pytest.mark.parametrize('mode', ('cold_start_is_excluded', 'all_target_early_stop'))
def test_v9_l1_admission_classifies_cold_start_and_early_target_separately(mode):
    from src.runners.physical_bounded_j1 import evaluate_v9_l1_admission

    if mode == 'cold_start_is_excluded':
        sequences = _v9_l1_sequences(
            [0.9, .5, .4, .3], [.9, .25, .2, .1],
            reset_times=[100., 10., 10., 10.],
            carry_times=[200., 1., 1., 1.])
        admission = evaluate_v9_l1_admission(sequences)
        assert admission['effective_pairs'] == 3
        assert [row['sequence_index'] for row in admission['observations']] == [2, 3, 4]
        assert admission['carry_reset_time_ratio'] > 1.5
        assert admission['status'] == 'EQUAL_NEW_WORK_NO_CLEAR_GAIN'
    else:
        sequences = _v9_l1_sequences(
            [8e-5, 7e-5, 6e-5, 5e-5], [7e-5, 6e-5, 5e-5, 4e-5],
            completed=4)
        admission = evaluate_v9_l1_admission(sequences)
        assert admission['all_target'] is True
        assert admission['full16_pairs'] == 0
        assert admission['observations'] == []
        assert len(admission['target_observations']) == 3
        assert admission['carry_reset_time_ratio'] == .5
        assert admission['status'] == 'L1_ADMISSION_OPEN'


def test_v9_checker_consumes_real_adapter_facts_and_recomputes_payload_bound():
    from benchmarks.physical_intermediate_checker import recompute_bounded_i4

    matrix, rng = _problem(48, shift=2)
    adapter = BoundedGCROTI4(
        lambda value: matrix @ value,
        lambda value: value.copy(),
        validation_action=lambda value: matrix @ value,
        model_identity={'case': 'checker-v9'}, policy=FIXED_NEW16_RECYCLE8)
    try:
        rows = []
        nested = []
        for call in range(4):
            rhs = np.asarray(rng.normal(size=48) + 1j * rng.normal(size=48),
                             dtype=np.complex128)
            facts = adapter.solve(rhs)['facts']
            rows.append(dict(call=facts['call'], facts=facts))
            nested.append(facts)

        def pc_row(index, left, right):
            audit = dict(actual_audit='PASS' if index == 1 else 'not_sampled')
            if index == 1:
                audit['audit'] = dict(closure_norm=0.0,
                                      operation_scale=1.0, closure_relative=0.0)
            return dict(
                apply_count=index, route='BAL_H', status='BALANCED_ACTION_COMPLETED',
                counts=dict(C=2, smoother=1, A_structure=2, A_inner_true=0,
                            PH_audit=0),
                inexact_balance=dict(actual_audit=audit['actual_audit'],
                                     audit=audit.get('audit'),
                                     calls=[dict(inner=left), dict(inner=right)]))

        checked = recompute_bounded_i4(
            rows, [pc_row(1, nested[0], nested[1]),
                   pc_row(2, nested[2], nested[3])],
            profile='balanced_h6_entity_gcrot8_new16_v9')
        assert checked['passed'], checked['errors']
    finally:
        adapter.destroy()


def test_v9_l1_missing_tail_is_limited_evidence_not_a_quality_error():
    from src.runners.physical_bounded_j1 import evaluate_v9_l1_admission

    sequences = _v9_l1_sequences(
        [.9, .5, .4, .3, .2], [.9, .25, .2, .1, .05])
    sequences['carry']['records'].pop()
    admission = evaluate_v9_l1_admission(sequences)
    assert admission['effective_pairs'] == 3
    assert admission['missing']
    assert admission['errors'] == []
    assert admission['status'] == 'L1_ADMISSION_OPEN'


def test_v8_default_policy_keeps_its_64_mib_accounting():
    adapter = BoundedGCROTI4(
        lambda value: value.copy(), lambda value: value.copy(),
        model_identity="tiny-v8-default")
    try:
        fixed = adapter.snapshot()["fixed"]
        assert fixed["policy"] == V8_FIXED_M8_RECYCLE8
        assert fixed["extra_bytes_limit"] == RECYCLING_EXTRA_BYTES_LIMIT
    finally:
        adapter.destroy()


def test_v8_fixed_round_fills_eight_pair_pool_and_keeps_bytes_bounded():
    from scipy.sparse.linalg import LinearOperator, gcrotmk

    matrix, rng = _problem(48, shift=2)
    calls = {"action": 0, "pc": 0, "native": 0}
    size = matrix.shape[0]

    def action(value):
        calls["action"] += 1
        value[:] = matrix @ value
        return value

    def pc(value):
        calls["pc"] += 1
        value[:] = value
        return value

    def native(value):
        calls["native"] += 1
        return matrix @ value

    adapter = BoundedGCROTI4(
        action, pc, validation_action=native, model_identity={"case": "tiny-v8"})
    try:
        for index in range(10):
            rhs = np.asarray(rng.normal(size=size) + 1j * rng.normal(size=size),
                             dtype=np.complex128)
            original = rhs.copy()
            replay_solution = replay_info = None
            if index == 0:
                direct_cu = []
                direct_solution, direct_info = gcrotmk(
                    LinearOperator((size, size), matvec=lambda value: matrix @ value,
                                   dtype=np.complex128),
                    rhs.copy(),
                    M=LinearOperator((size, size), matvec=lambda value: value,
                                     dtype=np.complex128),
                    m=8, k=8, maxiter=1, tol=1e-4, atol=0.0,
                    CU=direct_cu, discard_C=False, truncate="smallest")
            if index == 8:
                # Replay the exact persistent full-pool CU state through the
                # installed library before the adapter consumes the RHS.
                replay_cu = adapter.pool.working_cu()
                replay_solution, replay_info = gcrotmk(
                    LinearOperator((size, size), matvec=lambda value: matrix @ value,
                                   dtype=np.complex128),
                    rhs.copy(),
                    M=LinearOperator((size, size), matvec=lambda value: value,
                                     dtype=np.complex128),
                    m=8, k=8, maxiter=1, tol=1e-4, atol=0.0,
                    CU=replay_cu, discard_C=False, truncate="smallest")
            result = adapter.solve(rhs)
            facts = result["facts"]
            assert facts["input_unchanged"]
            assert np.array_equal(rhs, original)
            assert facts["B4_calls"] <= MAX_NEW_B4
            assert facts["attempted_B4"] <= MAX_NEW_B4
            assert facts["completed_new_arnoldi_directions"] <= MAX_NEW_DIRECTIONS
            assert facts["pool_after"] <= MAX_POOL_PAIRS
            assert facts["recycling_memory"]["cap_passed"]
            assert facts["pool_facts"]["candidate_pairs"] <= MAX_POOL_PAIRS
            assert facts["pool_facts"]["closure_error"] <= CLOSURE_LIMIT
            assert facts["m"] == GCROT_M and facts["k"] == GCROT_K
            assert facts["max_it"] == GCROT_MAXITER
            assert facts["tol"] == GCROT_TOL and facts["atol"] == GCROT_ATOL
            assert facts["truncate"] == "smallest" and not facts["discard_C"]
            if index == 0:
                assert facts["library_info"] == direct_info
                assert np.allclose(result["solution"], direct_solution)
                assert facts["gcrot_inner_dimension"] == 16
                assert facts["recycling_memory"]["inner_vz_vector_count"] == 33
            if index == 8:
                assert facts["pool_before"] == MAX_POOL_PAIRS
                assert facts["gcrot_inner_dimension"] == 8
                assert facts["B4_calls"] <= 8
                assert facts["recycling_memory"]["inner_vz_vector_count"] == 17
                assert facts["library_info"] == replay_info
                assert np.allclose(result["solution"], replay_solution)
        # Calls 11--32 exercise the periodic native spot check while the pool
        # is full; each remains one fixed library invocation.
        for _ in range(22):
            rhs = np.asarray(rng.normal(size=size) + 1j * rng.normal(size=size),
                             dtype=np.complex128)
            result = adapter.solve(rhs)
        facts = result["facts"]
        assert facts["call"] == 32
        assert facts["pool_facts"]["native_spot_checked"] == MAX_POOL_PAIRS
        assert facts["pool_facts"]["native_spot_due"]
        assert facts["pool_facts"]["native_spot_call"] == 32
        assert facts["pool_A4_checks"] == MAX_POOL_PAIRS
        snapshot = adapter.snapshot()
        assert snapshot["pool"]["pairs"] == MAX_POOL_PAIRS
        assert snapshot["pool"]["retained_bytes"] == 2 * size * 16 * MAX_POOL_PAIRS
        assert snapshot["pool"]["retained_bytes"] <= RECYCLING_EXTRA_BYTES_LIMIT
        assert POOL_NUMERIC_BYTES_P4_DERIVED == 12_533_760
        assert facts["recycling_memory"]["scipy_smallest_cu_overlap_vector_count"] == 14
        assert facts["recycling_memory"]["scipy_qr_input_output_bytes"] > 0
        assert facts["recycling_memory"]["scipy_gram_conjugate_temp_bytes"] > 0
        assert calls["pc"] >= 32
        assert calls["native"] >= 32
        exit_check = adapter.native_exit_spot_check()
        assert exit_check["checked"] == MAX_POOL_PAIRS
        assert max(exit_check["errors"]) <= CLOSURE_LIMIT
        assert adapter.snapshot()["exit_native_spot"]["checks"] == MAX_POOL_PAIRS
    finally:
        adapter.destroy()


def test_v8_pool_is_transactional_and_zero_rhs_does_not_mutate_it():
    matrix, _ = _problem(4)

    def action(value):
        value[:] = matrix[:4, :4] @ value
        return value

    def pc(value):
        value[:] = np.linalg.solve(matrix[:4, :4], value)
        return value

    adapter = BoundedGCROTI4(action, pc, validation_action=action,
                             model_identity="transactional")
    try:
        rhs = np.asarray([1 + 1j, 2 - 1j, .2 + .4j, -.3 + .1j], dtype=np.complex128)
        adapter.solve(rhs)
        before = adapter.snapshot()
        exposed = adapter.pool.pairs()
        exposed[0][0][:] = 0
        exposed[0][1][:] = 0
        assert adapter.snapshot()["pool"]["retained_bytes"] == before["pool"]["retained_bytes"]
        zero = adapter.solve(np.zeros(4, dtype=np.complex128))
        assert zero["facts"]["status"] == "INNER_ZERO_RHS"
        assert zero["facts"]["pool_update"] == "unchanged_zero_rhs"
        assert adapter.snapshot()["pool"] == before["pool"]
    finally:
        adapter.destroy()


def test_v8_abort_returns_last_complete_state_without_pool_commit():
    matrix, _ = _problem(4)
    checks = {"count": 0}

    def stop_requested():
        checks["count"] += 1
        return checks["count"] >= 4

    def action(value):
        return matrix[:4, :4] @ value

    def pc(value):
        return np.linalg.solve(matrix[:4, :4], value)

    adapter = BoundedGCROTI4(
        action, pc, validation_action=action, model_identity="abort",
        stop_requested=stop_requested)
    try:
        result = adapter.solve(np.asarray([1 + 0j, 2 + 1j, 3 - 1j, 1 - 2j],
                                          dtype=np.complex128))
        facts = result["facts"]
        assert facts["status"] == "INNER_APPROXIMATE_RETURN"
        assert facts["stop_reason"] == "OUTER_SAFE_DEADLINE"
        assert facts["pool_after"] == 0
        assert facts["completed_new_arnoldi_directions"] == 0
        assert facts["legal_direction_count"] == 0
        assert adapter.snapshot()["pool"]["replacements"] == 0
    finally:
        adapter.destroy()


@pytest.mark.filterwarnings("ignore:invalid value encountered in scalar divide")
def test_v8_zero_b4_is_not_a_legal_return_but_nonzero_pool_projection_is():
    matrix, _ = _problem(4)

    def action(value):
        return matrix[:4, :4] @ value

    def exact_pc(value):
        return np.linalg.solve(matrix[:4, :4], value)

    adapter = BoundedGCROTI4(action, exact_pc, validation_action=action,
                             model_identity="zero-b4")
    try:
        adapter.solve(np.asarray([1 + 0j, 2 + 1j, 3 - 1j, 1 - 2j],
                                 dtype=np.complex128))
        adapter.pc = lambda value: np.zeros_like(value)
        result = adapter.solve(np.asarray([1 + 2j, 2 - 1j, -.5 + .3j, 1 + .7j],
                                          dtype=np.complex128))
        facts = result["facts"]
        assert facts["B4_calls"] >= 1
        assert facts["completed_new_arnoldi_directions"] >= 1
        assert facts["completed_legal_new_arnoldi_directions"] == 0
        assert not facts["new_update_evidence"]
        assert facts["legal_direction_count"] == 1
        assert facts["pool_update"] == "unchanged"
        assert facts["pool_after"] == 1
    finally:
        adapter.destroy()


def test_v8_bad_native_closure_propagates_and_leaves_old_pool_unchanged():
    matrix, _ = _problem(4)

    def action(value):
        return matrix[:4, :4] @ value

    def pc(value):
        return np.linalg.solve(matrix[:4, :4], value)

    def bad_native(value):
        result = matrix[:4, :4] @ value
        result[0] += 1e-3
        return result

    adapter = BoundedGCROTI4(action, pc, validation_action=bad_native,
                             model_identity="bad-native")
    try:
        with pytest.raises(RecycledI4Error):
            adapter.solve(np.asarray([1 + 0j, 2 + 1j, 3 - 1j, 1 - 2j],
                                     dtype=np.complex128))
        assert adapter.snapshot()["pool"]["pairs"] == 0
        assert adapter.snapshot()["pool"]["replacements"] == 0
    finally:
        adapter.destroy()


def test_v8_rank_revealing_selector_operates_on_q_and_only_prunes_dependence():
    q0 = np.asarray([1 + 0j, 0 + 0j], dtype=np.complex128)
    q1 = np.asarray([1 + 0j, 0 + 0j], dtype=np.complex128)
    u0 = q0.copy()
    u1 = 2 * q1
    selected, indices, rank, residuals = BoundedGCROTI4._rank_revealing_subset(
        [(q0, u0), (q1, u1)])
    assert rank == 1
    assert indices == [0]
    assert len(selected) == 1
    assert residuals[1] <= RANK_THRESHOLD * np.linalg.norm(np.column_stack([q0, q1]))


def test_v8_pool_identity_reset_and_release_are_explicit():
    pool = VerifiedRecyclingPool({"model": "identity"})
    vector = np.asarray([1 + 0j, 0 + 0j], dtype=np.complex128)
    pool.replace([(vector, vector)], closure_errors=[0.0])
    assert pool.snapshot()["pairs"] == 1
    with pytest.raises(ValueError):
        BoundedGCROTI4(lambda value: value, lambda value: value,
                       model_identity="different", pool=pool)
    pool.reset()
    assert pool.snapshot()["pairs"] == 0
    pool.destroy()
    with pytest.raises(RecycledI4Error):
        pool.pairs()


def test_v8_petsc_bridge_checks_full_zero_slave_vectors_and_carries_pool():
    """Exercise the real PETSc Vec bridge without building a mesh or PDE."""

    from petsc4py import PETSc
    from src.solvers.physical_bounded_policy import RecycledI4Admission

    independent = np.asarray([0, 2], dtype=np.int64)
    excluded = np.asarray([1, 3], dtype=np.int64)
    matrix = np.asarray([[2.0 + .1j, .2 - .3j],
                         [.4 + .2j, 1.5 - .1j]], dtype=np.complex128)

    def apply(vector):
        output = vector.duplicate()
        output.set(0)
        output.array[independent] = matrix @ vector.array[independent]
        return output

    def pc(vector):
        output = vector.duplicate()
        output.set(0)
        output.array[independent] = vector.array[independent]
        return output

    admission = RecycledI4Admission(
        apply, pc, residual_action=apply, model_identity='petsc-bridge-v8',
        independent_indices=independent, sample=lambda: None,
        save=lambda *_: None, stop_requested=lambda: False)
    rhs = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    rhs2 = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    returned = []
    try:
        rhs.array[:] = [1 + .2j, 0, 2 - .1j, 0]
        before = rhs.array.copy()
        first = admission(rhs)
        returned.extend(first[name] for name in ('solution', 'applied', 'residual'))
        assert first['facts']['input_unchanged']
        assert np.array_equal(rhs.array, before)
        assert np.all(first['solution'].array[excluded] == 0.0)
        first_pool_size = first['facts']['pool_after']

        rhs2.array[:] = [-.3 + .4j, 0, .7 + .1j, 0]
        second = admission(rhs2)
        returned.extend(second[name] for name in ('solution', 'applied', 'residual'))
        assert second['facts']['pool_before'] == first_pool_size
        assert second['facts']['input_unchanged']
        assert np.all(second['applied'].array[excluded] == 0.0)

        polluted = rhs2.duplicate()
        try:
            polluted.array[:] = rhs2.array
            polluted.array[1] = 1e-12
            with pytest.raises(RuntimeError, match='excluded slave'):
                admission(polluted)
        finally:
            polluted.destroy()

        nonfinite = rhs2.duplicate()
        try:
            nonfinite.array[:] = rhs2.array
            nonfinite.array[0] = np.nan + 0j
            with pytest.raises(RuntimeError, match='non-finite'):
                admission(nonfinite)
        finally:
            nonfinite.destroy()
    finally:
        for vector in returned:
            vector.destroy()
        rhs2.destroy()
        rhs.destroy()
        admission.destroy()


def test_v8_petsc_bridge_rejects_polluted_callback_output():
    from petsc4py import PETSc
    from src.solvers.physical_bounded_policy import RecycledI4Admission

    independent = np.asarray([0, 2], dtype=np.int64)

    def polluted_action(vector):
        output = vector.duplicate()
        output.set(0)
        output.array[independent] = vector.array[independent]
        output.array[1] = 1e-12
        return output

    def identity(vector):
        output = vector.duplicate()
        output.set(0)
        output.array[independent] = vector.array[independent]
        return output

    admission = RecycledI4Admission(
        polluted_action, identity, residual_action=identity,
        model_identity='petsc-pollution-v8', independent_indices=independent,
        sample=lambda: None, save=lambda *_: None,
        stop_requested=lambda: False)
    rhs = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    try:
        rhs.array[:] = [1 + 0j, 0, 2 + 0j, 0]
        with pytest.raises(RuntimeError, match='excluded slave'):
            admission(rhs)
        assert admission.engine.pool.size == 0
    finally:
        rhs.destroy()
        admission.destroy()


def test_v8_k1_fake_runner_orders_reset_carry_clears_pool_and_rejects_bad_fields():
    from benchmarks.physical_intermediate_checker import recompute_recycled_i4_sequence
    from src.runners.physical_bounded_j1 import run_v8_k1_recycling_sequences

    stems = [
        'A2R160_BAL_H_p4_01', 'A2R160_BAL_H_p4_02',
        'LIGHT448_BAL_H_p4_09', 'LIGHT448_BAL_H_p4_10',
        'JOINT448_BAL_H_p4_17', 'JOINT448_BAL_H_p4_18',
    ]

    class FakeAdmission:
        def __init__(self):
            self.calls = 0
            self.pairs = 0
            self.reset_calls = 0
            self.identity = 'fake-v8-identity'

        def reset(self):
            self.pairs = 0
            self.reset_calls += 1

        def snapshot(self):
            return dict(calls=self.calls, engine=dict(calls=self.calls, pool=dict(
                pairs=self.pairs, retained_bytes=self.pairs * 32,
                model_identity_sha256=self.identity)))

        def __call__(self, rhs):
            before = self.pairs
            self.calls += 1
            self.pairs = min(8, self.pairs + 1)
            rank = self.pairs
            gram = np.eye(rank, dtype=np.complex128)
            due = before == 0 or self.calls % 32 == 0
            facts = dict(
                call=self.calls, status='INNER_APPROXIMATE_RETURN',
                pool_before=before, pool_after=self.pairs,
                pool_identity_sha256=self.identity,
                initial_guess='library_x0_zero_plus_current_pool_projection',
                pool_projection_source='current_pool_only', zero_start=True,
                attempted_B4=1, completed_B4=1,
                attempted_new_arnoldi_directions=1,
                completed_new_arnoldi_directions=1,
                A4_matvec=1, B4_calls=1, iterations=1,
                pool_facts=dict(
                    candidate_pairs=rank, pairs=rank, rank=rank,
                    rank_pruned=0, rank_singular_values=[1.0] * rank,
                    q_gram=gram, orthogonality_error=0.0,
                    closure_errors=[0.0] * rank, closure_error=0.0,
                    native_spot_checked=rank if due else 0,
                    native_spot_due=due,
                    native_spot_call=self.calls if due else None,
                    native_spot_errors=[0.0] * rank if due else [],
                ),
                recycling_memory=dict(
                    extra_recycling_peak_bytes=1024, peak_live_bytes=2048,
                    cap_bytes=64 * 1024**2,
                    phase_bounds=dict(projection_phase=10, gcrot_phase=20,
                                      candidate_validation_phase=12),
                    base_inner_vz_bytes=1, inner_transient_vector_bytes=1,
                    scipy_smallest_cu_overlap_bytes=1,
                    scipy_qr_input_output_bytes=1,
                    scipy_gram_conjugate_temp_bytes=1),
            )
            return dict(facts=facts)

    items = [dict(stem=stem, role='g1' if index % 2 == 0 else 'g2',
                  input_sha256=f'in-{index}', g_array_sha256=f'g-{index}',
                  reference_status='available_not_used', status='available',
                  g=np.asarray([index + 1j], dtype=np.complex128))
              for index, stem in enumerate(stems)]
    admission = FakeAdmission()
    saved = {}
    result = run_v8_k1_recycling_sequences(
        admission, items, make_rhs=lambda item: item['g'].copy(),
        sample=lambda: None,
        save=lambda name, facts: saved.setdefault(name, facts),
        append=lambda *_: None)
    assert [row['stem'] for row in result['reset']['records']] == stems
    assert [row['stem'] for row in result['carry']['records']] == stems
    assert [row['pool_before'] for row in result['reset']['records']] == [0] * 6
    assert [row['pool_before'] for row in result['carry']['records']] == list(range(6))
    assert result['control_pool']['pairs'] == 0
    assert result['total_calls'] == 12
    assert admission.reset_calls == 8

    budget = dict(schema='task39extra.review-v8-k0-k1-budget.v1',
                  total_limit_seconds=3600, finite_control_limit_seconds=900,
                  charged_seconds=12.0, finite_control_seconds=10.0,
                  stage_seconds=dict(setup=2.0, reset_carry_sequences=6.0,
                                     two_pc_controls=4.0),
                  stages_nonoverlapping=True)
    checked = recompute_recycled_i4_sequence(
        result['reset']['records'], sequence='RESET', budget=budget)
    assert checked['passed'], checked['errors']
    checked_carry = recompute_recycled_i4_sequence(
        result['carry']['records'], sequence='CARRY')
    assert checked_carry['passed'], checked_carry['errors']
    broken = copy.deepcopy(result['reset']['records'])
    del broken[0]['facts']['recycling_memory']
    rejected = recompute_recycled_i4_sequence(broken, sequence='RESET')
    assert not rejected['passed']
    assert any('recycling_memory' in error for error in rejected['errors'])


def test_v8_k1_real_engine_json_ledger_and_reset_native_state():
    from benchmarks.physical_intermediate_checker import recompute_recycled_i4_sequence
    from src.runners.physical_bounded_j1 import run_v8_k1_recycling_sequences
    from src.runners.physical_intermediate import _jsonable

    matrix, rng = _problem(48, shift=2)
    calls = {'action': 0, 'pc': 0, 'native': 0}

    def action(value):
        calls['action'] += 1
        return matrix @ value

    def pc(value):
        calls['pc'] += 1
        return value.copy()

    def native(value):
        calls['native'] += 1
        return matrix @ value

    def json_roundtrip(value):
        return json.loads(json.dumps(_jsonable(value), allow_nan=False, sort_keys=True))

    stems = [
        'A2R160_BAL_H_p4_01', 'A2R160_BAL_H_p4_02',
        'LIGHT448_BAL_H_p4_09', 'LIGHT448_BAL_H_p4_10',
        'JOINT448_BAL_H_p4_17', 'JOINT448_BAL_H_p4_18',
    ]
    items = [dict(stem=stem, role='g1' if index % 2 == 0 else 'g2',
                  input_sha256=f'in-{index}', g_array_sha256=f'g-{index}',
                  reference_status='available_not_used', status='available',
                  g=np.asarray(rng.normal(size=48) + 1j * rng.normal(size=48),
                               dtype=np.complex128))
             for index, stem in enumerate(stems)]
    engine = BoundedGCROTI4(
        action, pc, validation_action=native, model_identity='k1-real-json')

    class EngineAdmission:
        def __init__(self, engine):
            self.engine = engine

        @property
        def calls(self):
            return self.engine.calls

        def reset(self):
            self.engine.reset()

        def snapshot(self):
            return dict(calls=self.engine.calls, engine=self.engine.snapshot())

        def __call__(self, rhs):
            return self.engine.solve(rhs)

        def destroy(self):
            self.engine.destroy()

    admission = EngineAdmission(engine)
    saved = {}
    appended = []
    try:
        result = run_v8_k1_recycling_sequences(
            admission, items, make_rhs=lambda item: item['g'].copy(),
            sample=lambda: None,
            save=lambda name, facts: saved.__setitem__(name, json_roundtrip(facts)),
            append=lambda name, facts: appended.append((name, json_roundtrip(facts))))
        serialized = json_roundtrip(result)
        reset_checked = recompute_recycled_i4_sequence(
            serialized['reset']['records'], sequence='RESET')
        carry_checked = recompute_recycled_i4_sequence(
            serialized['carry']['records'], sequence='CARRY')
        assert reset_checked['passed'], reset_checked['errors']
        assert carry_checked['passed'], carry_checked['errors']
        assert saved['v8_k1_sequences']['schema'] == result['schema']
        assert len(appended) == 12

        before_controls = admission.snapshot()
        assert before_controls['calls'] == 12
        assert before_controls['engine']['pool']['pairs'] == 0
        assert before_controls['engine']['native_spot']['seen'] is False

        control_facts = []
        for item in items[:4]:
            outcome = admission(item['g'].copy())
            control_facts.append(json_roundtrip(outcome['facts']))
        assert [facts['call'] for facts in control_facts] == [13, 14, 15, 16]
        assert control_facts[0]['pool_facts']['native_spot_due'] is True
        assert control_facts[0]['pool_facts']['native_spot_call'] == 13
        assert all(facts['pool_facts']['native_spot_due'] is False
                   for facts in control_facts[1:])
        assert admission.snapshot()['calls'] == 16
        assert calls['pc'] > 0 and calls['native'] > 0
    finally:
        admission.destroy()


def test_v9_real_adapter_sequence_ledger_reaches_sequence_checker():
    """Exercise the V9 runner/checker boundary with actual adapter facts."""
    from benchmarks.physical_intermediate_checker import (
        recompute_recycled_i4_sequence,
    )
    from src.runners.physical_bounded_j1 import run_v9_equal_new_work_sequences
    from src.runners.physical_intermediate import _jsonable

    matrix, rng = _problem(48, shift=2)

    def action(value):
        return matrix @ value

    def json_roundtrip(value):
        return json.loads(json.dumps(_jsonable(value), allow_nan=False, sort_keys=True))

    stems = [
        'A2R160_BAL_H_p4_01', 'A2R160_BAL_H_p4_02',
        'LIGHT448_BAL_H_p4_09', 'LIGHT448_BAL_H_p4_10',
        'JOINT448_BAL_H_p4_17', 'JOINT448_BAL_H_p4_18',
    ]
    items = [dict(stem=stem, role='g1' if index % 2 == 0 else 'g2',
                  input_sha256=f'in-v9-{index}', g_array_sha256=f'g-v9-{index}',
                  reference_status='available_not_used', status='available',
                  g=np.asarray(rng.normal(size=48) + 1j * rng.normal(size=48),
                               dtype=np.complex128))
             for index, stem in enumerate(stems)]
    engine = BoundedGCROTI4(
        action, lambda value: value.copy(), validation_action=action,
        model_identity='v9-real-sequence', policy=FIXED_NEW16_RECYCLE8)

    class EngineAdmission:
        def __init__(self, engine):
            self.engine = engine

        @property
        def calls(self):
            return self.engine.calls

        def reset(self):
            self.engine.reset()

        def snapshot(self):
            return dict(calls=self.engine.calls, engine=self.engine.snapshot())

        def __call__(self, rhs):
            return self.engine.solve(rhs)

        def destroy(self):
            self.engine.destroy()

    admission = EngineAdmission(engine)
    try:
        result = run_v9_equal_new_work_sequences(
            admission, items, make_rhs=lambda item: item['g'].copy(),
            sample=lambda: None,
            save=lambda *_: None,
            append=lambda *_: None)
        serialized = json_roundtrip(result)
        reset_checked = recompute_recycled_i4_sequence(
            serialized['reset']['records'], sequence='RESET',
            profile='balanced_h6_entity_gcrot8_new16_v9')
        carry_checked = recompute_recycled_i4_sequence(
            serialized['carry']['records'], sequence='CARRY',
            profile='balanced_h6_entity_gcrot8_new16_v9')
        assert reset_checked['passed'], reset_checked['errors']
        assert carry_checked['passed'], carry_checked['errors']
        assert serialized['schema'] == 'task39extra.review-v9-equal-new-work-sequence.v1'
        assert serialized['control_pool']['pairs'] == 0
        assert serialized['total_calls'] == 12
    finally:
        admission.destroy()


def test_v8_provenance_helpers_use_flat_simulation_config_and_realized_arrays():
    from src.common.config_3d import SimulationConfig3D
    from src.solvers.physical_bounded_runtime import (
        _realized_floquet_identity, _realized_material_identity,
    )

    cfg = SimulationConfig3D(geometry_kind='rectangular_block_grating',
                             use_floquet_xy=True)

    class FakeMPC:
        slaves = np.asarray([1], dtype=np.int32)
        masters = np.asarray([0], dtype=np.int32)

        @staticmethod
        def coefficients():
            return (np.asarray([1 + 0j], dtype=np.complex128),
                    np.asarray([0, 0, 1], dtype=np.int32))

    class FakeFloquet:
        mpc = FakeMPC()

    floquet = _realized_floquet_identity(cfg, FakeFloquet())
    assert floquet['details']['p4_mpc']['slaves']['shape'] == [1]
    assert 'derived' not in floquet['details']

    class X:
        array = np.asarray([1.0, 2.0], dtype=np.float64)

    class Function:
        x = X()

    material = _realized_material_identity(
        cfg, dict(mu=Function(), mass=Function(), coefficient_audit={'positive': True}))
    assert material['details']['coefficient_source'] == (
        'realized_positive_coefficients_not_raw_material_values')
    assert set(material['details']['coefficient_arrays']) == {'mu', 'mass'}


@pytest.mark.skipif(not (V8_K1_ROOT / 'j1_controls.jsonl').is_file(),
                    reason='ignored immutable V8 K1 fixture is not present')
def test_v8_k1_checker_counts_explicit_control_audits_from_fixture():
    from benchmarks.physical_intermediate_checker import recompute_v8_k1_controls

    def rows(name):
        return [json.loads(line) for line in (V8_K1_ROOT / name).read_text().splitlines()
                if line.strip()]

    summary = json.loads((V8_K1_ROOT / 'j1_controls_summary.json').read_text())
    control_audits = rows('j1_controls.jsonl')
    checked = recompute_v8_k1_controls(
        summary['v8_k1_sequences'],
        rows('v8_k1_sequence.jsonl') + rows('bounded_i4.jsonl'),
        rows('pc_applies.jsonl'), rows('bounded_exit_audit.jsonl'),
        control_metadata=summary['v8_k1'],
        budget=summary['v8_preparation_budget'],
        control_audit_rows=control_audits)

    assert checked['passed'], checked['errors']
    assert [row['label'] for row in control_audits] == ['A2R160', 'LIGHT448']
    assert [row['complete_pc_calls'] for row in control_audits] == [1, 2]
    assert all(row['balance']['closure_relative'] <= 1e-8
               for row in control_audits)
    costs = checked['bounded_costs']
    assert costs['explicit_control_audits'] == 2
    assert costs['expected_inexact_audits'] == 4
