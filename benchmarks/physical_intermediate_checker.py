"""Independent raw-output checks; never construct or invoke a PDE solver."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

_POSITIVE_APPLY_KEYS = ('s6_apply_count', 's3_apply_count')

_BOUNDED_I4_STATUSES = (
    'INNER_ZERO_RHS', 'INNER_TARGET_REACHED', 'INNER_APPROXIMATE_RETURN',
)
_BOUNDED_NEGATIVE_STATUSES = (
    'NORMAL_SCREEN_STOP', 'PROGRESS_INSUFFICIENT_AT_MID_BUDGET',
    'TIME_PROGRESS_SCREEN_STOP',
    'PERFORMANCE_CONTROLLED_STOP', 'ITERATION_BUDGET_EXHAUSTED',
    'CONTROLLED_STOP',
)

_V8_K1_CONTROL_LABELS = ('A2R160', 'LIGHT448')


def _stable_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _finite_number(value, *, nonnegative=False) -> bool:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(result) and (not nonnegative or result >= 0.0))


def _bounded_i4_facts(row: dict) -> dict:
    facts = row.get('facts', row)
    return facts if isinstance(facts, dict) else {}


def recompute_bounded_i4(i4_rows, pc_rows, exit_rows=(), *, profile=None,
                         call_start=1, native_seen_before=False) -> dict:
    """Recompute bounded I4, PC, H6, and inexact-audit accounting from JSONL.

    This deliberately does not use ``positive_setup`` or the solver's status.
    In particular, H6 is counted from the actual per-PC smoother count, and
    the two I4 calls are matched to their nested inexact-balance records.
    """
    errors = []
    v8_recycled = profile == 'balanced_h6_entity_gcrot8_v8'
    v9_recycled = profile == 'balanced_h6_entity_gcrot8_new16_v9'
    recycled = v8_recycled or v9_recycled

    def require(condition, message):
        if not condition:
            errors.append(message)

    normalized = []
    timeout_streak = 0
    no_direction_streak = 0
    v8_identity = None
    v8_previous_after = None
    v8_native_seen = bool(native_seen_before)
    v9_identity = None
    v9_previous_after = None
    v9_native_seen = bool(native_seen_before)
    for index, row in enumerate(i4_rows, 1):
        facts = _bounded_i4_facts(row)
        expected_call = int(call_start) + index - 1
        require(row.get('call') == expected_call,
                f'I4 call ordering mismatch at {expected_call}')
        status = facts.get('status')
        require(status in _BOUNDED_I4_STATUSES, f'illegal I4 status at {index}: {status}')
        for key in ('target', 'rhs_norm', 'final_true_residual', 'seconds',
                    'actual_elapsed_seconds'):
            require(_finite_number(facts.get(key), nonnegative=True),
                    f'nonfinite/negative I4 {key} at {index}')
        require(facts.get('target') == 1e-4, f'I4 target is not 1e-4 at {index}')
        if v8_recycled:
            backend = facts.get('backend', {})
            require(facts.get('restart') == 8 and facts.get('m') == 8 and
                    facts.get('k') == 8 and facts.get('max_it') == 1,
                    f'I4 GCROT8 fixed-round contract mismatch at {index}')
            require(facts.get('truncate') == 'smallest' and
                    facts.get('discard_C') is False and facts.get('atol') == 0.0,
                    f'I4 GCROT truncation contract mismatch at {index}')
            require(isinstance(backend, dict) and
                    backend.get('backend') == 'scipy.sparse.linalg.gcrotmk',
                    f'I4 GCROT backend identity missing at {index}')
            for key in ('pool_before', 'pool_after', 'pool_identity_sha256',
                        'pool_facts', 'recycling_memory', 'initial_guess',
                        'pool_projection_source'):
                require(key in facts, f'V8 I4 field is missing at {index}: {key}')
            require(facts.get('initial_guess') ==
                    'library_x0_zero_plus_current_pool_projection',
                    f'V8 I4 initial-guess semantics mismatch at {index}')
            require(facts.get('pool_projection_source') == 'current_pool_only',
                    f'V8 I4 pool source mismatch at {index}')
            pool_before = facts.get('pool_before')
            pool_after = facts.get('pool_after')
            inner_dimension = facts.get('gcrot_inner_dimension')
            require(isinstance(pool_before, int) and not isinstance(pool_before, bool) and
                    0 <= pool_before <= 8,
                    f'I4 GCROT pool-before ledger invalid at {index}')
            require(isinstance(pool_after, int) and not isinstance(pool_after, bool) and
                    0 <= pool_after <= 8,
                    f'I4 GCROT pool-after ledger invalid at {index}')
            if v8_previous_after is not None:
                require(pool_before == v8_previous_after,
                        f'I4 GCROT pool continuity mismatch at {index}')
            v8_previous_after = pool_after
            identity = facts.get('pool_identity_sha256')
            require(isinstance(identity, str) and identity,
                    f'I4 GCROT pool identity is missing at {index}')
            if v8_identity is None and isinstance(identity, str):
                v8_identity = identity
            elif v8_identity is not None:
                require(identity == v8_identity,
                        f'I4 GCROT pool identity changed at {index}')
            if isinstance(pool_before, int) and isinstance(inner_dimension, int):
                require(inner_dimension == 8 + max(8 - pool_before, 0),
                        f'I4 GCROT dynamic inner dimension mismatch at {index}')
            for key in ('attempted_B4', 'completed_B4',
                        'attempted_new_arnoldi_directions',
                        'completed_new_arnoldi_directions'):
                require(key in facts and isinstance(facts[key], int) and
                        not isinstance(facts[key], bool) and facts[key] >= 0,
                        f'I4 GCROT work field is missing/invalid at {index}: {key}')
            if all(key in facts for key in (
                    'attempted_B4', 'completed_B4',
                    'attempted_new_arnoldi_directions',
                    'completed_new_arnoldi_directions')):
                require(facts['attempted_B4'] <= 16 and
                        facts['attempted_new_arnoldi_directions'] <= 16,
                        f'I4 GCROT new-work cap mismatch at {index}')
                require(facts['completed_B4'] <= facts['attempted_B4'] and
                        facts['completed_new_arnoldi_directions'] <=
                        facts['attempted_new_arnoldi_directions'],
                        f'I4 GCROT completed work exceeds attempted work at {index}')
                require(facts['completed_B4'] == facts['B4_calls'] and
                        facts['completed_new_arnoldi_directions'] ==
                        facts['iterations'],
                        f'I4 GCROT completed-work relation mismatch at {index}')
            pool_facts = facts['pool_facts']
            memory = facts['recycling_memory']
            require(isinstance(pool_facts, dict),
                    f'I4 GCROT pool facts are not a mapping at {index}')
            require(isinstance(memory, dict),
                    f'I4 GCROT memory facts are not a mapping at {index}')
            if isinstance(pool_facts, dict):
                for key in ('candidate_pairs', 'pairs', 'rank', 'rank_pruned',
                            'rank_singular_values', 'q_gram',
                            'orthogonality_error', 'closure_errors',
                            'closure_error', 'cached_closure_checks',
                            'native_spot_checked', 'native_spot_due',
                            'native_spot_call', 'native_spot_errors'):
                    require(key in pool_facts,
                            f'I4 GCROT pool fact is missing at {index}: {key}')
                if all(key in pool_facts for key in (
                        'candidate_pairs', 'pairs', 'rank', 'rank_pruned')):
                    candidate_pairs = pool_facts['candidate_pairs']
                    rank = pool_facts['rank']
                    require(isinstance(candidate_pairs, int) and 0 <= candidate_pairs <= 8,
                            f'I4 GCROT candidate-pair count invalid at {index}')
                    require(isinstance(rank, int) and 0 <= rank <= candidate_pairs,
                            f'I4 GCROT rank invalid at {index}')
                    require(pool_facts['pairs'] == rank and
                            pool_facts['rank_pruned'] == candidate_pairs - rank,
                            f'I4 GCROT rank accounting mismatch at {index}')
                for key in ('orthogonality_error', 'closure_error'):
                    require(_finite_number(pool_facts.get(key), nonnegative=True) and
                            float(pool_facts[key]) <= 1e-10,
                            f'I4 GCROT {key} exceeds 1e-10 at {index}')
                closure_errors = pool_facts.get('closure_errors')
                require(isinstance(closure_errors, list) and
                        all(_finite_number(value, nonnegative=True) and
                            float(value) <= 1e-10 for value in closure_errors),
                        f'I4 GCROT cached closure evidence invalid at {index}')
                singular = np.asarray(pool_facts.get('rank_singular_values'), dtype=float)
                require(singular.ndim == 1 and np.isfinite(singular).all(),
                        f'I4 GCROT rank spectrum invalid at {index}')
                if singular.size and isinstance(pool_facts.get('rank'), int):
                    threshold = 1e-12 * max(float(singular[0]), np.finfo(float).tiny)
                    require(int(np.count_nonzero(singular > threshold)) ==
                            int(pool_facts['rank']),
                            f'I4 GCROT rank spectrum disagrees at {index}')
                gram = np.asarray(pool_facts.get('q_gram'))
                if gram.ndim == 3 and gram.shape[-1] == 2:
                    gram = gram[..., 0] + 1j * gram[..., 1]
                require(gram.ndim == 2 and np.isfinite(gram).all(),
                        f'I4 GCROT Q Gram evidence invalid at {index}')
                if gram.ndim == 2 and gram.shape[0] == gram.shape[1]:
                    require(float(np.linalg.norm(
                        gram - np.eye(gram.shape[0], dtype=np.complex128), ord=2)) <= 1e-10,
                        f'I4 GCROT Q orthogonality evidence failed at {index}')
                native_errors = pool_facts.get('native_spot_errors')
                require(isinstance(native_errors, list) and
                        all(_finite_number(value, nonnegative=True) and
                            float(value) <= 1e-10 for value in native_errors),
                        f'I4 GCROT native closure evidence invalid at {index}')
                native_checked = pool_facts.get('native_spot_checked')
                require(isinstance(native_checked, int) and 0 <= native_checked <= 8 and
                        native_checked == len(native_errors),
                        f'I4 GCROT native spot count invalid at {index}')
                native_due = pool_facts.get('native_spot_due')
                require(isinstance(native_due, bool),
                        f'I4 GCROT native due flag is invalid at {index}')
                expected_native_due = (not v8_native_seen or expected_call % 32 == 0)
                require(native_due is expected_native_due,
                        f'I4 GCROT native cadence invalid at {index}')
                if native_due:
                    require(native_checked > 0 and
                            pool_facts.get('native_spot_call') == expected_call,
                            f'I4 GCROT native spot identity/cadence invalid at {index}')
                    if native_checked > 0:
                        v8_native_seen = True
                else:
                    require(native_checked == 0 and
                            pool_facts.get('native_spot_call') is None,
                            f'I4 GCROT unexpected native spot at {index}')
            if isinstance(memory, dict):
                required_memory = (
                    'extra_recycling_peak_bytes', 'peak_live_bytes', 'cap_bytes',
                    'phase_bounds', 'base_inner_vz_bytes',
                    'inner_transient_vector_bytes',
                    'scipy_smallest_cu_overlap_bytes',
                    'scipy_qr_input_output_bytes',
                    'scipy_gram_conjugate_temp_bytes')
                for key in required_memory:
                    require(key in memory,
                            f'I4 GCROT memory field is missing at {index}: {key}')
                if all(key in memory for key in required_memory):
                    cap = memory['cap_bytes']
                    extra = memory['extra_recycling_peak_bytes']
                    require(cap == 64 * 1024**2 and isinstance(extra, int) and
                            extra >= 0 and extra <= cap,
                            f'I4 GCROT 64MiB memory gate failed at {index}')
                    phase = memory['phase_bounds']
                    require(isinstance(phase, dict) and all(key in phase for key in (
                        'projection_phase', 'gcrot_phase',
                        'candidate_validation_phase')),
                        f'I4 GCROT phase table is incomplete at {index}')
        elif v9_recycled:
            backend = facts.get('backend', {})
            require(facts.get('k') == 8 and facts.get('max_it') == 1 and
                    facts.get('gcrot_inner_dimension') == 16,
                    f'I4 V9 fixed-new16 inner contract mismatch at {index}')
            m_call = facts.get('m_call')
            effective_rank = facts.get('effective_pool_rank')
            require(isinstance(m_call, int) and 8 <= m_call <= 16 and
                    isinstance(effective_rank, int) and 0 <= effective_rank <= 8 and
                    m_call == 16 - max(8 - effective_rank, 0) and
                    facts.get('restart') == m_call and facts.get('m') == m_call,
                    f'I4 V9 effective-rank/m_call contract mismatch at {index}')
            require(facts.get('truncate') == 'smallest' and
                    facts.get('discard_C') is False and facts.get('atol') == 0.0,
                    f'I4 V9 GCROT truncation contract mismatch at {index}')
            require(isinstance(backend, dict) and
                    backend.get('backend') == 'scipy.sparse.linalg.gcrotmk',
                    f'I4 V9 GCROT backend identity missing at {index}')
            for key in ('pool_before', 'pool_after', 'pool_identity_sha256',
                        'pool_facts', 'recycling_memory', 'initial_guess',
                        'pool_projection_source', 'requested_new_B4',
                        'requested_new_arnoldi_directions',
                        'requested_new_B4_callbacks', 'completed_new_B4',
                        'completed_new_arnoldi_directions',
                        'actual_arnoldi_length', 'discarded_new_B4',
                        'discarded_new_arnoldi_directions',
                        'rejected_new_B4_callbacks'):
                require(key in facts, f'V9 I4 field is missing at {index}: {key}')
            require(facts.get('policy') == 'FIXED_NEW16_RECYCLE8' and
                    facts.get('initial_guess') ==
                    'library_x0_zero_plus_current_pool_projection' and
                    facts.get('pool_projection_source') == 'current_pool_only',
                    f'V9 I4 policy/initial-guess semantics mismatch at {index}')
            pool_before = facts.get('pool_before')
            pool_after = facts.get('pool_after')
            require(isinstance(pool_before, int) and not isinstance(pool_before, bool) and
                    0 <= pool_before <= 8 and isinstance(pool_after, int) and
                    not isinstance(pool_after, bool) and 0 <= pool_after <= 8,
                    f'I4 V9 pool ledger invalid at {index}')
            if v9_previous_after is not None:
                require(pool_before == v9_previous_after,
                        f'I4 V9 pool continuity mismatch at {index}')
            v9_previous_after = pool_after
            identity = facts.get('pool_identity_sha256')
            require(isinstance(identity, str) and identity,
                    f'I4 V9 pool identity is missing at {index}')
            if v9_identity is None and isinstance(identity, str):
                v9_identity = identity
            elif v9_identity is not None:
                require(identity == v9_identity,
                        f'I4 V9 pool identity changed at {index}')
            pool_facts = facts.get('pool_facts')
            require(isinstance(pool_facts, dict),
                    f'I4 V9 pool facts are not a mapping at {index}')
            if isinstance(pool_facts, dict) and pool_facts.get('checked') is not True:
                require(pool_facts.get('pairs') == effective_rank and
                        pool_facts.get('rank') == effective_rank and
                        pool_facts.get('rank_pruned') ==
                        max(pool_before - effective_rank, 0),
                        f'I4 V9 uncommitted pool ledger is inconsistent at {index}')
                # Zero-RHS, no-direction, and safe/deadline returns expose no
                # candidate Gram/native evidence because no new pool was
                # validated.  Their existing pool ledger is sufficient.
                pool_facts = None
            if isinstance(pool_facts, dict):
                for key in ('candidate_pairs', 'pairs', 'rank', 'rank_pruned',
                            'rank_singular_values', 'q_gram',
                            'orthogonality_error', 'closure_errors',
                            'closure_error', 'native_spot_checked',
                            'native_spot_due', 'native_spot_call',
                            'native_spot_errors'):
                    require(key in pool_facts,
                            f'I4 V9 pool fact is missing at {index}: {key}')
                candidate_pairs = pool_facts.get('candidate_pairs')
                rank = pool_facts.get('rank')
                require(isinstance(candidate_pairs, int) and
                        0 <= candidate_pairs <= 8 and
                        isinstance(rank, int) and 0 <= rank <= candidate_pairs and
                        pool_facts.get('pairs') == rank and
                        pool_facts.get('rank_pruned') == candidate_pairs - rank,
                        f'I4 V9 rank ledger invalid at {index}')
                for key in ('orthogonality_error', 'closure_error'):
                    require(_finite_number(pool_facts.get(key), nonnegative=True) and
                            float(pool_facts[key]) <= 1e-10,
                            f'I4 V9 {key} exceeds 1e-10 at {index}')
                singular = np.asarray(pool_facts.get('rank_singular_values'), dtype=float)
                require(singular.ndim == 1 and np.isfinite(singular).all(),
                        f'I4 V9 rank spectrum invalid at {index}')
                if singular.size and isinstance(rank, int):
                    threshold = 1e-12 * max(float(singular[0]), np.finfo(float).tiny)
                    require(int(np.count_nonzero(singular > threshold)) == rank,
                            f'I4 V9 rank spectrum disagrees at {index}')
                gram = np.asarray(pool_facts.get('q_gram'))
                if gram.ndim == 3 and gram.shape[-1] == 2:
                    gram = gram[..., 0] + 1j * gram[..., 1]
                require(gram.ndim == 2 and np.isfinite(gram).all() and
                        isinstance(rank, int) and gram.shape == (rank, rank),
                        f'I4 V9 Q Gram evidence invalid at {index}')
                if gram.ndim == 2 and isinstance(rank, int) and gram.shape == (rank, rank):
                    require(float(np.linalg.norm(
                        gram - np.eye(rank, dtype=np.complex128), ord=2)) <= 1e-10,
                            f'I4 V9 Q orthogonality evidence failed at {index}')
                closures = pool_facts.get('closure_errors')
                native_errors = pool_facts.get('native_spot_errors')
                require(isinstance(closures, list) and
                        all(_finite_number(value, nonnegative=True) and
                            float(value) <= 1e-10 for value in closures) and
                        _finite_number(pool_facts.get('closure_error'), nonnegative=True) and
                        float(pool_facts.get('closure_error')) <= 1e-10,
                        f'I4 V9 cached A4U closure failed at {index}')
                require(isinstance(native_errors, list) and
                        all(_finite_number(value, nonnegative=True) and
                            float(value) <= 1e-10 for value in native_errors),
                        f'I4 V9 native A4U closure evidence invalid at {index}')
                native_checked = pool_facts.get('native_spot_checked')
                require(isinstance(native_checked, int) and 0 <= native_checked <= 8 and
                        native_checked == len(native_errors),
                        f'I4 V9 native spot count invalid at {index}')
                native_due = pool_facts.get('native_spot_due')
                require(isinstance(native_due, bool),
                        f'I4 V9 native due flag is invalid at {index}')
                expected_native_due = (not v9_native_seen or expected_call % 32 == 0)
                require(native_due is expected_native_due,
                        f'I4 V9 native cadence invalid at {index}')
                if native_due:
                    require(native_checked > 0 and
                            pool_facts.get('native_spot_call') == expected_call,
                            f'I4 V9 native spot identity/cadence invalid at {index}')
                    if native_checked > 0:
                        v9_native_seen = True
                else:
                    require(native_checked == 0 and
                            pool_facts.get('native_spot_call') is None,
                            f'I4 V9 unexpected native spot at {index}')
            for key in ('requested_new_B4', 'requested_new_arnoldi_directions',
                        'requested_new_B4_callbacks', 'attempted_B4',
                        'completed_B4', 'attempted_new_arnoldi_directions',
                        'completed_new_B4', 'completed_new_arnoldi_directions',
                        'actual_arnoldi_length',
                        'discarded_new_B4', 'discarded_new_arnoldi_directions',
                        'rejected_new_B4_callbacks'):
                value = facts.get(key)
                require(isinstance(value, int) and not isinstance(value, bool) and
                        0 <= value <= 16,
                        f'I4 V9 work field invalid at {index}: {key}')
            if all(isinstance(facts.get(key), int) and
                   not isinstance(facts.get(key), bool) for key in (
                    'requested_new_B4', 'requested_new_arnoldi_directions',
                    'requested_new_B4_callbacks', 'attempted_B4', 'completed_B4',
                    'completed_new_B4', 'attempted_new_arnoldi_directions',
                    'completed_new_arnoldi_directions', 'actual_arnoldi_length',
                    'discarded_new_B4', 'discarded_new_arnoldi_directions',
                    'rejected_new_B4_callbacks')):
                require(facts['requested_new_B4'] ==
                        facts['requested_new_arnoldi_directions'] == 16 and
                        facts['requested_new_B4_callbacks'] == facts['attempted_B4'] and
                        facts['completed_B4'] == facts['completed_new_B4'] and
                        facts['completed_B4'] == facts.get('B4_calls') and
                        facts['completed_new_arnoldi_directions'] ==
                        facts['actual_arnoldi_length'] == facts.get('iterations') and
                        facts['discarded_new_B4'] ==
                        max(16 - facts['completed_new_B4'], 0) and
                        facts['discarded_new_arnoldi_directions'] ==
                        max(16 - facts['actual_arnoldi_length'], 0) and
                        facts['rejected_new_B4_callbacks'] == 0,
                        f'I4 V9 work accounting failed at {index}')
                early_return = (facts.get('status') in ('INNER_ZERO_RHS',
                                                         'INNER_TARGET_REACHED') or
                                facts.get('requested_safe_return') is True or
                                facts.get('timeout_exceeded') is True)
                if not early_return:
                    require(facts['completed_new_B4'] == 16 and
                            facts['actual_arnoldi_length'] == 16,
                            f'I4 V9 non-early return did not complete 16 new directions at {index}')
            memory = facts.get('recycling_memory')
            require(isinstance(memory, dict),
                    f'I4 V9 memory facts are not a mapping at {index}')
            if isinstance(memory, dict):
                required_memory = ('payload_ledger', 'scipy_small_matrix_bound',
                                   'cap_bytes', 'cap_peak_bytes', 'cap_passed',
                                   'peak_live_bytes', 'phase_bounds')
                for key in required_memory:
                    require(key in memory, f'I4 V9 memory field is missing at {index}: {key}')
                ledger = memory.get('payload_ledger')
                phase = memory.get('phase_bounds')
                named = memory.get('named_array_bytes')
                base_extra = (memory.get('persistent_before_bytes', -1) +
                              memory.get('working_cu_bytes_including_terminal', -1))
                small = memory.get('scipy_small_matrix_bound')
                overlap = memory.get('scipy_smallest_cu_overlap_bytes', -1)
                qr = memory.get('scipy_qr_input_output_bytes', -1)
                gram = memory.get('scipy_gram_conjugate_temp_bytes', -1)
                projection = memory.get('projection_matrix_bytes', -1)
                ordinary = memory.get('ordinary_live_vector_bytes', -1)
                inner = (memory.get('base_inner_vz_bytes', -1) +
                         memory.get('inner_transient_vector_bytes', -1))
                candidate_q = (named.get('candidate_q_matrix_bound', -1)
                              if isinstance(named, dict) else -1)
                projection_phase = base_extra + projection + small + ordinary
                library_phase = base_extra + overlap + qr + gram + small + ordinary + inner
                candidate_phase = base_extra + candidate_q + qr + gram + small + ordinary
                expected_peak = max(projection_phase, library_phase, candidate_phase) + (
                    memory.get('index_payload_bytes', -1))
                phase_ok = (isinstance(phase, dict) and
                            phase.get('projection_phase') == projection_phase +
                            memory.get('index_payload_bytes', -1) and
                            phase.get('gcrot_phase') == library_phase +
                            memory.get('index_payload_bytes', -1) and
                            phase.get('candidate_validation_phase') == candidate_phase +
                            memory.get('index_payload_bytes', -1))
                require(memory.get('cap_bytes') == 128 * 1024**2 and
                        memory.get('scipy_small_matrix_bound') ==
                        4 * (16 + 2) * (8 + 2) * 16 and
                        isinstance(ledger, dict) and
                        ledger.get('search_vectors_bytes') == inner and
                        ledger.get('persistent_pool_bytes') ==
                        memory.get('persistent_before_bytes') and
                        ledger.get('transaction_pool_bytes') ==
                        memory.get('working_cu_bytes_including_terminal') and
                        ledger.get('qr_svd_truncation_bytes') == overlap + qr + gram + small and
                        ledger.get('adapter_vector_bytes') == ordinary and
                        ledger.get('index_payload_bytes') == memory.get('index_payload_bytes') and
                        ledger.get('peak_bytes') == expected_peak and
                        memory.get('peak_live_bytes') == expected_peak and
                        memory.get('cap_peak_bytes') == expected_peak and
                        memory.get('cap_passed') is (expected_peak <= 128 * 1024**2) and
                        ledger.get('cap_bytes') == 128 * 1024**2 and
                        ledger.get('cap_passed') is (expected_peak <= 128 * 1024**2) and
                        phase_ok,
                        f'I4 V9 128MiB payload gate failed at {index}')
        else:
            require(facts.get('restart') == 16 and facts.get('max_it') == 16,
                    f'I4 16-step contract mismatch at {index}')
        require(facts.get('zero_start') is True, f'I4 is not zero-start at {index}')
        iterations = facts.get('iterations')
        legal = facts.get('legal_direction_count')
        require(isinstance(iterations, int) and 0 <= iterations <= 16,
                f'I4 iteration cap mismatch at {index}')
        require(isinstance(legal, int) and legal >= 0,
                f'I4 legal-direction count mismatch at {index}')
        for key in ('A4_matvec', 'B4_calls', 'explicit_A4'):
            require(isinstance(facts.get(key), int) and facts[key] >= 0,
                    f'I4 {key} is not a nonnegative count at {index}')
        attempted = facts.get('attempted', {})
        for key in ('A4_matvec', 'B4_calls', 'explicit_A4'):
            if attempted:
                require(attempted.get(key) == facts.get(key),
                        f'I4 attempted/completed {key} mismatch at {index}')
        timeout = facts.get('timeout_exceeded')
        require(isinstance(timeout, bool), f'I4 timeout flag is not boolean at {index}')
        if timeout:
            require(float(facts['seconds']) >= 30.0,
                    f'I4 hard-30 timeout is early at {index}')
        else:
            require(float(facts['seconds']) <= 30.0 + 1e-7,
                    f'I4 exceeded hard-30 without timeout at {index}')
        safe_return = facts.get('requested_safe_return')
        require(isinstance(safe_return, bool),
                f'I4 safe-return flag is not boolean at {index}')
        if status != 'INNER_ZERO_RHS':
            if float(facts['seconds']) >= 25.0:
                require(safe_return, f'I4 missed soft-25 safe-return flag at {index}')
            if safe_return and float(facts['seconds']) < 25.0:
                require(facts.get('stop_reason') == 'OUTER_SAFE_DEADLINE',
                        f'I4 early safe-return has no outer deadline at {index}')
            timeout_streak = timeout_streak + 1 if timeout else 0
            no_direction_streak = (no_direction_streak + 1
                                   if legal == 0 else 0)
        # Zero-RHS is legal but does not reset either consecutive-cost streak.
        admission = row.get('admission', {})
        if admission:
            require(admission.get('calls') == expected_call,
                    f'I4 admission call count mismatch at {index}')
            require(admission.get('timeout_streak') == timeout_streak,
                    f'I4 timeout streak mismatch at {index}')
            require(admission.get('no_direction_streak') == no_direction_streak,
                    f'I4 no-direction streak mismatch at {index}')
        if status == 'INNER_ZERO_RHS':
            require(facts['rhs_norm'] == 0.0 and facts['final_true_residual'] == 0.0,
                    f'zero-RHS I4 has nonzero norm at {index}')
            require(iterations == facts['A4_matvec'] == facts['B4_calls'] == 0,
                    f'zero-RHS I4 invented work at {index}')
            require(facts['explicit_A4'] == 0,
                    f'zero-RHS I4 performed an explicit action at {index}')
        else:
            require(float(facts['rhs_norm']) > 0.0,
                    f'nonzero I4 has zero RHS at {index}')
            eps_norm = facts.get('eps_norm')
            require(_finite_number(eps_norm, nonnegative=True),
                    f'nonzero I4 has no finite eps_norm at {index}')
            relative = float(eps_norm) / float(facts['rhs_norm'])
            require(np.isclose(relative, float(facts['final_true_residual']),
                               rtol=0, atol=1e-12),
                    f'I4 eps_norm/rhs_norm relative mismatch at {index}')
            if status == 'INNER_TARGET_REACHED':
                require(relative <= 1e-4 + 1e-12,
                        f'target I4 returned above target at {index}')
            if recycled:
                require(facts['A4_matvec'] >= facts['B4_calls'],
                        f'I4 GCROT A4/B4 accounting is inconsistent at {index}')
            else:
                require(facts['A4_matvec'] <= iterations and facts['B4_calls'] <= iterations,
                        f'I4 work exceeds iteration count at {index}')
        normalized.append(facts)

    # Match the nested I4 scalar packets to the independently written I4 JSONL.
    nested = []
    for pc_index, row in enumerate(pc_rows, 1):
        calls = row.get('inexact_balance', {}).get('calls', [])
        require(len(calls) == 2, f'PC {pc_index} does not contain exactly two I4 calls')
        nested.extend(item.get('inner', {}) for item in calls)
    require(len(nested) == len(normalized), 'nested I4 count differs from raw I4 count')
    for index, (facts, inner) in enumerate(zip(normalized, nested), 1):
        for key in ('status', 'iterations', 'rhs_norm', 'eps_norm', 'final_true_residual',
                    'A4_matvec', 'B4_calls', 'explicit_A4', 'restart', 'max_it'):
            if key in inner:
                left, right = facts.get(key), inner.get(key)
                if isinstance(left, float) or isinstance(right, float):
                    require(np.isclose(float(left), float(right), rtol=0, atol=1e-12),
                            f'nested/raw I4 {key} mismatch at {index}')
                else:
                    require(left == right, f'nested/raw I4 {key} mismatch at {index}')
        if inner.get('status') != 'INNER_ZERO_RHS':
            require(_finite_number(inner.get('eps_norm'), nonnegative=True),
                    f'nested I4 eps_norm missing at {index}')
            nested_relative = float(inner['eps_norm']) / float(inner['rhs_norm'])
            require(np.isclose(nested_relative, float(inner['final_true_residual']),
                               rtol=0, atol=1e-12),
                    f'nested I4 eps_norm/rhs_norm mismatch at {index}')

    pc_facts = []
    h6_count = 0
    for index, row in enumerate(pc_rows, 1):
        require(row.get('apply_count') == index, f'PC apply ordering mismatch at {index}')
        require(row.get('route') == 'BAL_H', f'bounded PC route mismatch at {index}')
        require(row.get('status') == 'BALANCED_ACTION_COMPLETED',
                f'bounded PC status mismatch at {index}')
        counts = row.get('counts', {})
        expected_counts = dict(C=2, smoother=1, A_structure=2, A_inner_true=0,
                               PH_audit=0)
        for key, expected in expected_counts.items():
            require(counts.get(key) == expected,
                    f'bounded PC {key} count mismatch at {index}')
        h6_count += int(counts.get('smoother', 0))
        audit = row.get('inexact_balance', {})
        actual_audit = audit.get('actual_audit')
        audit_due = index == 1 or index % 32 == 0
        require(actual_audit == ('PASS' if audit_due else 'not_sampled'),
                f'inexact audit cadence mismatch at PC {index}')
        if actual_audit == 'PASS':
            closure = audit.get('audit', {})
            require(_finite_number(closure.get('closure_norm'), nonnegative=True) and
                    _finite_number(closure.get('operation_scale'), nonnegative=True) and
                    float(closure.get('operation_scale', 0.0)) > 0.0,
                    f'inexact closure scalars are invalid at PC {index}')
            if _finite_number(closure.get('closure_norm'), nonnegative=True) and \
                    _finite_number(closure.get('operation_scale'), nonnegative=True) and \
                    float(closure.get('operation_scale', 0.0)) > 0.0:
                relative = (float(closure['closure_norm']) /
                            float(closure['operation_scale']))
                require(_finite_number(closure.get('closure_relative'), nonnegative=True),
                        f'saved inexact closure ratio is invalid at PC {index}')
                if _finite_number(closure.get('closure_relative'), nonnegative=True):
                    require(np.isclose(relative, float(closure['closure_relative']),
                                       rtol=0, atol=1e-15),
                            f'saved inexact closure ratio differs at PC {index}')
                require(relative <= 1e-8, f'inexact closure failed at PC {index}')
        pc_facts.append(dict(apply_count=index, counts=dict(counts),
                             actual_audit=actual_audit))

    exit_rows = list(exit_rows or [])
    if exit_rows:
        require(len(exit_rows) == 1, 'bounded exit audit is not exactly one record')
        exit_row = exit_rows[-1]
        require(exit_row.get('last_PC') == len(pc_rows), 'exit audit last_PC mismatch')
        costs = exit_row.get('audit_costs', {})
        for key, value in costs.items():
            require(_finite_number(value, nonnegative=True),
                    f'negative/nonfinite exit audit cost {key}')
        closure = exit_row.get('audit', {})
        require(_finite_number(closure.get('closure_norm'), nonnegative=True) and
                _finite_number(closure.get('operation_scale'), nonnegative=True) and
                float(closure.get('operation_scale', 0.0)) > 0.0,
                'exit inexact closure scalars are invalid')
        if (_finite_number(closure.get('closure_norm'), nonnegative=True) and
                _finite_number(closure.get('operation_scale'), nonnegative=True) and
                float(closure.get('operation_scale', 0.0)) > 0.0):
            relative = float(closure['closure_norm']) / float(closure['operation_scale'])
            require(_finite_number(closure.get('closure_relative'), nonnegative=True),
                    'saved exit closure ratio is invalid')
            if _finite_number(closure.get('closure_relative'), nonnegative=True):
                require(np.isclose(relative, float(closure['closure_relative']),
                                   rtol=0, atol=1e-15),
                        'saved exit closure ratio differs from closure_norm/operation_scale')
            require(relative <= 1e-8, 'exit inexact closure failed')
        if recycled:
            recycled_identity = (v8_identity if v8_recycled else v9_identity)
            spot = exit_row.get('total', {}).get('I4', {}).get('exit_native_spot', {})
            require(isinstance(spot, dict), 'recycled exit native spot-check record is missing')
            if isinstance(spot, dict):
                require(spot.get('status') in ('completed', 'skipped_resource_stop'),
                        'recycled exit native spot-check status is invalid')
                require(isinstance(spot.get('checked'), int) and 0 <= spot['checked'] <= 8,
                        'recycled exit native spot-check count is invalid')
                require(_finite_number(spot.get('elapsed_seconds'), nonnegative=True),
                        'recycled exit native spot-check time is invalid')
                completed = spot.get('completed_native_A4', spot.get('checked', 0))
                require(isinstance(completed, int) and completed >= 0,
                        'recycled exit native spot A4 count is invalid')
                require(spot.get('pool_identity_sha256') == recycled_identity,
                        'recycled exit native spot identity differs from I4 pool')
                costs = exit_row.get('audit_costs', {})
                require(float(costs.get('native_exit_spot_A4', completed)) == float(completed),
                        'recycled exit native spot A4 cost differs from snapshot')
                require(np.isclose(float(costs.get('native_exit_spot_seconds',
                                                   spot.get('elapsed_seconds', 0.0))),
                                   float(spot.get('elapsed_seconds', 0.0)),
                                   rtol=0, atol=1e-12),
                        'recycled exit native spot time differs from snapshot')

    i4_totals = {
        key: sum(int(facts.get(key, 0)) for facts in normalized)
        for key in ('A4_matvec', 'B4_calls', 'explicit_A4')
    }
    return dict(passed=not errors, errors=errors, i4_calls=len(normalized),
                i4_totals=i4_totals, completed_pc_count=len(pc_rows),
                actual_h6_applies=h6_count, pc=pc_facts,
                semantics=dict(I4=('two independent calls per PC; target=1e-4; '
                                   'GCROT fixed-new16, k=8, maxiter=1, ml=16; soft=25; hard=30; zero-start'
                                   if v9_recycled else
                                   'two independent calls per PC; target=1e-4; '
                                   'GCROT m=k=8, maxiter=1, dynamic ml; soft=25; hard=30; zero-start'
                                   if v8_recycled else
                                   'two independent calls per PC; target=1e-4; '
                                   'restart=max_it=16; soft=25; hard=30; zero-start'),
                               H6='one actual smoother apply per PC; positive_setup is not used'))


def recompute_recycled_i4_sequence(records, *, sequence=None, budget=None,
                                   exit_record=None, native_seen_before=False,
                                   profile='balanced_h6_entity_gcrot8_v8') -> dict:
    """Independently check one finite recycled-I4 RESET/CARRY sequence.

    This checker consumes scalar/raw ledgers emitted by the finite runner.  It
    requires every pool, work, rank, closure, memory, identity, and cadence
    field explicitly; absent values are errors rather than zero-work claims.
    """

    errors = []
    v9 = profile == 'balanced_h6_entity_gcrot8_new16_v9'
    sequence_schema = ('task39extra.review-v9-equal-new-work-sequence.v1'
                       if v9 else 'task39extra.review-v8-recycling-sequence.v1')

    def require(condition, message):
        if not condition:
            errors.append(message)

    expected_stems = [
        'A2R160_BAL_H_p4_01', 'A2R160_BAL_H_p4_02',
        'LIGHT448_BAL_H_p4_09', 'LIGHT448_BAL_H_p4_10',
        'JOINT448_BAL_H_p4_17', 'JOINT448_BAL_H_p4_18',
    ]
    rows = list(records or [])
    require(len(rows) == len(expected_stems),
            'V8 finite sequence does not contain exactly six ordered records')
    identity = None
    previous_after = None
    previous_call = None
    native_seen = bool(native_seen_before)
    complete_calls = []
    for index, row in enumerate(rows[:len(expected_stems)], 1):
        if sequence == 'RESET':
            # The runner calls reset() before every RESET item.  The engine
            # keeps its lifetime call number but clears native_spot.seen.
            native_seen = False
        required_row = ('schema', 'sequence', 'sequence_index', 'stem', 'role',
                        'input_sha256', 'g_array_sha256', 'reference_status',
                        'reset_before', 'pool_before', 'pool_after',
                        'pool_identity_before', 'pool_identity_after',
                        'pool_snapshot_before', 'pool_snapshot_after', 'facts')
        for key in required_row:
            require(key in row, f'V8 sequence field missing at {index}: {key}')
        if any(key not in row for key in required_row):
            continue
        require(row.get('schema') == sequence_schema,
                f'V8 sequence schema mismatch at {index}')
        require(row.get('sequence_index') == index and
                row.get('stem') == expected_stems[index - 1],
                f'V8 six-RHS order mismatch at {index}')
        if sequence is not None:
            require(row.get('sequence') == sequence,
                    f'V8 sequence name mismatch at {index}')
            if sequence == 'RESET':
                require(row.get('reset_before') is True,
                        f'V8 RESET did not clear before record {index}')
            elif sequence == 'CARRY':
                require(row.get('reset_before') is (index == 1),
                        f'V8 CARRY reset cadence mismatch at {index}')
        before = row.get('pool_before')
        after = row.get('pool_after')
        require(isinstance(before, int) and not isinstance(before, bool) and
                0 <= before <= 8 and isinstance(after, int) and
                not isinstance(after, bool) and 0 <= after <= 8,
                f'V8 sequence pool size invalid at {index}')
        if previous_after is not None and sequence != 'RESET':
            require(before == previous_after,
                    f'V8 sequence pool continuity broke at {index}')
        if sequence == 'RESET':
            require(before == 0, f'V8 RESET pool was not empty at {index}')
        elif sequence == 'CARRY' and index == 1:
            require(before == 0, 'V8 CARRY did not start from an empty pool')
        previous_after = after
        before_snapshot = row.get('pool_snapshot_before')
        after_snapshot = row.get('pool_snapshot_after')
        for snapshot, name, expected_size, expected_identity in (
                (before_snapshot, 'before', before, row.get('pool_identity_before')),
                (after_snapshot, 'after', after, row.get('pool_identity_after'))):
            require(isinstance(snapshot, dict),
                    f'V8 {name} pool snapshot missing at {index}')
            if isinstance(snapshot, dict):
                for key in ('pairs', 'retained_bytes', 'model_identity_sha256'):
                    require(key in snapshot,
                            f'V8 {name} pool snapshot field missing at {index}: {key}')
                if all(key in snapshot for key in ('pairs', 'retained_bytes',
                                                   'model_identity_sha256')):
                    require(snapshot['pairs'] == expected_size and
                            snapshot['model_identity_sha256'] == expected_identity and
                            isinstance(snapshot['retained_bytes'], int) and
                            snapshot['retained_bytes'] >= 0,
                            f'V8 {name} pool snapshot disagrees at {index}')
        before_identity = row.get('pool_identity_before')
        after_identity = row.get('pool_identity_after')
        require(isinstance(before_identity, str) and before_identity and
                before_identity == after_identity,
                f'V8 pool identity changed within record {index}')
        if identity is None and isinstance(before_identity, str):
            identity = before_identity
        elif identity is not None:
            require(before_identity == identity,
                    f'V8 pool identity changed across records at {index}')
        status = row.get('status')
        if status == 'not_found':
            require(row.get('facts') is None,
                    f'V8 not-found record carries numeric facts at {index}')
            continue
        require(status == 'complete' and isinstance(row.get('facts'), dict),
                f'V8 sequence status/facts invalid at {index}')
        if status != 'complete' or not isinstance(row.get('facts'), dict):
            continue
        facts = row['facts']
        complete_calls.append(facts.get('call'))
        for key in ('call', 'pool_before', 'pool_after', 'pool_identity_sha256',
                    'initial_guess', 'pool_projection_source', 'zero_start',
                    'attempted_B4', 'completed_B4',
                    'attempted_new_arnoldi_directions',
                    'completed_new_arnoldi_directions', 'A4_matvec', 'B4_calls',
                    'pool_facts', 'recycling_memory'):
            require(key in facts, f'V8 I4 fact missing at {index}: {key}')
        if not all(key in facts for key in ('call', 'pool_before', 'pool_after',
                                            'pool_identity_sha256')):
            continue
        require(isinstance(facts['call'], int) and facts['call'] >= 1 and
                (previous_call is None or facts['call'] == previous_call + 1) and
                facts['pool_before'] == before and facts['pool_after'] == after and
                facts['pool_identity_sha256'] == identity,
                f'V8 I4/sequence pool binding mismatch at {index}')
        if isinstance(facts['call'], int):
            previous_call = facts['call']
        require(facts.get('initial_guess') ==
                'library_x0_zero_plus_current_pool_projection' and
                facts.get('pool_projection_source') == 'current_pool_only' and
                facts.get('zero_start') is True,
                f'V8 initial-guess semantics mismatch at {index}')
        if v9:
            require(facts.get('policy') == 'FIXED_NEW16_RECYCLE8' and
                    facts.get('k') == 8 and facts.get('max_it') == 1 and
                    facts.get('gcrot_inner_dimension') == 16 and
                    isinstance(facts.get('effective_pool_rank'), int) and
                    0 <= facts.get('effective_pool_rank') <= 8 and
                    facts.get('m_call') ==
                    16 - max(8 - facts.get('effective_pool_rank'), 0) and
                    facts.get('restart') == facts.get('m_call') and
                    facts.get('m') == facts.get('m_call'),
                    f'V9 fixed-new16 inner contract mismatch at {index}')
            for key in ('requested_new_B4', 'requested_new_arnoldi_directions',
                        'requested_new_B4_callbacks', 'completed_new_B4',
                        'actual_arnoldi_length', 'discarded_new_B4',
                        'discarded_new_arnoldi_directions',
                        'rejected_new_B4_callbacks'):
                require(isinstance(facts.get(key), int) and
                        not isinstance(facts.get(key), bool) and
                        0 <= facts[key] <= 16,
                        f'V9 fixed-new16 field invalid at {index}: {key}')
            require(facts.get('requested_new_B4') ==
                    facts.get('requested_new_arnoldi_directions') == 16 and
                    facts.get('rejected_new_B4_callbacks') == 0,
                    f'V9 fixed-new16 request contract failed at {index}')
            early_return = (facts.get('status') in ('INNER_ZERO_RHS',
                                                     'INNER_TARGET_REACHED') or
                            facts.get('requested_safe_return') is True or
                            facts.get('timeout_exceeded') is True)
            if not early_return:
                require(facts.get('completed_new_B4') == 16 and
                        facts.get('actual_arnoldi_length') == 16,
                        f'V9 non-early sequence call did not complete 16 work at {index}')
        work_keys = ('attempted_B4', 'completed_B4',
                     'attempted_new_arnoldi_directions',
                     'completed_new_arnoldi_directions', 'A4_matvec', 'B4_calls')
        if all(key in facts for key in work_keys):
            require(all(isinstance(facts[key], int) and not isinstance(facts[key], bool)
                        and facts[key] >= 0 for key in work_keys),
                    f'V8 work counters invalid at {index}')
            require(facts['attempted_B4'] <= 16 and
                    facts['attempted_new_arnoldi_directions'] <= 16 and
                    facts['completed_B4'] <= facts['attempted_B4'] and
                    facts['completed_new_arnoldi_directions'] <=
                    facts['attempted_new_arnoldi_directions'] and
                    facts['completed_B4'] == facts['B4_calls'] and
                    facts['A4_matvec'] >= facts['B4_calls'],
                    f'V8 work relation/cap failed at {index}')
        pool_facts = facts.get('pool_facts')
        memory = facts.get('recycling_memory')
        require(isinstance(pool_facts, dict) and isinstance(memory, dict),
                f'V8 pool/memory facts are incomplete at {index}')
        if not isinstance(pool_facts, dict) or not isinstance(memory, dict):
            continue
        if v9 and pool_facts.get('checked') is not True:
            require(pool_facts.get('pairs') == facts.get('effective_pool_rank') and
                    pool_facts.get('rank') == facts.get('effective_pool_rank') and
                    pool_facts.get('rank_pruned') == facts.get('discarded_pool_directions'),
                    f'V9 uncommitted pool ledger is inconsistent at {index}')
            pool_facts = None
        required_pool = ('candidate_pairs', 'pairs', 'rank', 'rank_pruned',
                         'rank_singular_values', 'q_gram', 'orthogonality_error',
                         'closure_errors', 'closure_error', 'native_spot_checked',
                         'native_spot_due', 'native_spot_call', 'native_spot_errors')
        for key in required_pool:
            require(pool_facts is None or key in pool_facts,
                    f'V8 pool fact missing at {index}: {key}')
        if pool_facts is not None and all(key in pool_facts for key in required_pool):
            candidate_pairs = pool_facts['candidate_pairs']
            rank = pool_facts['rank']
            require(isinstance(candidate_pairs, int) and 0 <= candidate_pairs <= 8 and
                    isinstance(rank, int) and 0 <= rank <= candidate_pairs and
                    pool_facts['pairs'] == rank and
                    pool_facts['rank_pruned'] == candidate_pairs - rank,
                    f'V8 rank ledger invalid at {index}')
            for key in ('orthogonality_error', 'closure_error'):
                require(_finite_number(pool_facts[key], nonnegative=True) and
                        float(pool_facts[key]) <= 1e-10,
                        f'V8 {key} exceeds 1e-10 at {index}')
            singular = np.asarray(pool_facts['rank_singular_values'], dtype=float)
            require(singular.ndim == 1 and np.isfinite(singular).all(),
                    f'V8 rank spectrum invalid at {index}')
            if singular.size:
                threshold = 1e-12 * max(float(singular[0]), np.finfo(float).tiny)
                require(int(np.count_nonzero(singular > threshold)) == rank,
                        f'V8 rank spectrum disagrees at {index}')
            gram = np.asarray(pool_facts['q_gram'])
            if gram.ndim == 3 and gram.shape[-1] == 2:
                gram = gram[..., 0] + 1j * gram[..., 1]
            require(gram.ndim == 2 and np.isfinite(gram).all() and
                    gram.shape == (rank, rank), f'V8 Q Gram invalid at {index}')
            if gram.ndim == 2 and gram.shape == (rank, rank):
                require(float(np.linalg.norm(
                    gram - np.eye(rank, dtype=np.complex128), ord=2)) <= 1e-10,
                        f'V8 Q orthogonality failed at {index}')
            closures = pool_facts['closure_errors']
            native_errors = pool_facts['native_spot_errors']
            require(isinstance(closures, list) and
                    all(_finite_number(value, nonnegative=True) and
                        float(value) <= 1e-10 for value in closures) and
                    _finite_number(pool_facts['closure_error'], nonnegative=True) and
                    float(pool_facts['closure_error']) <= 1e-10,
                    f'V8 cached A4U closure failed at {index}')
            require(isinstance(native_errors, list) and
                    all(_finite_number(value, nonnegative=True) and
                        float(value) <= 1e-10 for value in native_errors) and
                    isinstance(pool_facts['native_spot_checked'], int) and
                    pool_facts['native_spot_checked'] == len(native_errors) and
                    0 <= pool_facts['native_spot_checked'] <= 8,
                    f'V8 native A4U closure/cost failed at {index}')
            native_due = pool_facts['native_spot_due']
            require(isinstance(native_due, bool),
                    f'V8 native due flag is invalid at {index}')
            expected_native_due = (not native_seen or facts['call'] % 32 == 0)
            require(native_due is expected_native_due,
                    f'V8 native periodic cadence mismatch at {index}')
            if native_due:
                require(pool_facts['native_spot_checked'] > 0 and
                        pool_facts['native_spot_call'] == facts['call'],
                        f'V8 native periodic spot identity/count failed at {index}')
                if pool_facts['native_spot_checked'] > 0:
                    native_seen = True
            else:
                require(pool_facts['native_spot_checked'] == 0 and
                        pool_facts['native_spot_call'] is None,
                        f'V8 native spot occurred off cadence at {index}')
        required_memory = ('extra_recycling_peak_bytes', 'peak_live_bytes',
                           'cap_bytes', 'phase_bounds', 'base_inner_vz_bytes',
                           'inner_transient_vector_bytes',
                           'scipy_smallest_cu_overlap_bytes',
                           'scipy_qr_input_output_bytes',
                           'scipy_gram_conjugate_temp_bytes')
        for key in required_memory:
            require(key in memory, f'V8 memory fact missing at {index}: {key}')
        if all(key in memory for key in required_memory):
            if v9:
                phase = memory.get('phase_bounds')
                named = memory.get('named_array_bytes')
                base_extra = (memory.get('persistent_before_bytes', -1) +
                              memory.get('working_cu_bytes_including_terminal', -1))
                small = memory.get('scipy_small_matrix_bound')
                overlap = memory.get('scipy_smallest_cu_overlap_bytes', -1)
                qr = memory.get('scipy_qr_input_output_bytes', -1)
                gram = memory.get('scipy_gram_conjugate_temp_bytes', -1)
                projection = memory.get('projection_matrix_bytes', -1)
                ordinary = memory.get('ordinary_live_vector_bytes', -1)
                inner = (memory.get('base_inner_vz_bytes', -1) +
                         memory.get('inner_transient_vector_bytes', -1))
                candidate_q = (named.get('candidate_q_matrix_bound', -1)
                              if isinstance(named, dict) else -1)
                index_bytes = memory.get('index_payload_bytes', -1)
                expected_phases = (
                    base_extra + projection + small + ordinary + index_bytes,
                    base_extra + overlap + qr + gram + small + ordinary + inner + index_bytes,
                    base_extra + candidate_q + qr + gram + small + ordinary + index_bytes)
                ledger = memory.get('payload_ledger')
                require(memory.get('cap_bytes') == 128 * 1024**2 and
                        memory.get('scipy_small_matrix_bound') ==
                        4 * (16 + 2) * (8 + 2) * 16 and
                        isinstance(ledger, dict) and
                        ledger.get('peak_bytes') == max(expected_phases) and
                        memory.get('peak_live_bytes') == max(expected_phases) and
                        memory.get('cap_peak_bytes') == max(expected_phases) and
                        memory.get('cap_passed') is (max(expected_phases) <= 128 * 1024**2) and
                        isinstance(phase, dict) and
                        tuple(phase.get(name) for name in (
                            'projection_phase', 'gcrot_phase',
                            'candidate_validation_phase')) == expected_phases,
                        f'V9 128MiB memory bound failed at {index}')
            else:
                require(memory['cap_bytes'] == 64 * 1024**2 and
                    isinstance(memory['extra_recycling_peak_bytes'], int) and
                    memory['extra_recycling_peak_bytes'] <= memory['cap_bytes'] and
                    isinstance(memory['peak_live_bytes'], int) and
                    memory['peak_live_bytes'] >= memory['extra_recycling_peak_bytes'],
                    f'V8 64MiB memory bound failed at {index}')
                phase = memory['phase_bounds']
                require(isinstance(phase, dict) and all(key in phase for key in (
                    'projection_phase', 'gcrot_phase', 'candidate_validation_phase')),
                    f'V8 phase memory table incomplete at {index}')

    if budget is not None:
        for key in ('schema', 'total_limit_seconds', 'finite_control_limit_seconds',
                    'charged_seconds', 'finite_control_seconds', 'stage_seconds',
                    'stages_nonoverlapping'):
            require(key in budget, f'V8 preparation budget field missing: {key}')
        if all(key in budget for key in ('schema', 'total_limit_seconds',
                                         'finite_control_limit_seconds',
                                         'charged_seconds', 'finite_control_seconds',
                                         'stage_seconds',
                                         'stages_nonoverlapping')):
            require(budget['schema'] == ('task39extra.review-v9-equal-new-work-budget.v1'
                                         if v9 else
                                         'task39extra.review-v8-k0-k1-budget.v1') and
                    budget['total_limit_seconds'] == 3600 and
                    budget['finite_control_limit_seconds'] == 900 and
                    _finite_number(budget['charged_seconds'], nonnegative=True) and
                    float(budget['charged_seconds']) <= 3600 and
                    _finite_number(budget['finite_control_seconds'], nonnegative=True) and
                    float(budget['finite_control_seconds']) <= 900 and
                    budget['stages_nonoverlapping'] is True,
                    'recycled preparation budget contract failed')
            stages = budget['stage_seconds']
            require(isinstance(stages, dict) and all(name in stages for name in (
                'setup', 'reset_carry_sequences', 'two_pc_controls')),
                'V8 preparation stage ledger is incomplete')

    if exit_record is not None:
        try:
            total = exit_record['total']
            spot = total['I4']['exit_native_spot']
            costs = exit_record['audit_costs']
        except (KeyError, TypeError) as exc:
            errors.append(f'V8 exit native spot record is incomplete: {exc}')
        else:
            for key in ('status', 'checked', 'completed_native_A4',
                        'elapsed_seconds', 'pool_identity_sha256'):
                require(key in spot, f'V8 exit spot field missing: {key}')
            if all(key in spot for key in ('status', 'checked',
                                           'completed_native_A4',
                                           'elapsed_seconds',
                                           'pool_identity_sha256')):
                require(spot['status'] in ('completed', 'skipped_resource_stop') and
                        isinstance(spot['checked'], int) and 0 <= spot['checked'] <= 8 and
                        isinstance(spot['completed_native_A4'], int) and
                        spot['completed_native_A4'] >= 0 and
                        _finite_number(spot['elapsed_seconds'], nonnegative=True) and
                        spot['pool_identity_sha256'] == identity,
                        'V8 exit native spot identity/count failed')
            for key in ('native_exit_spot_A4', 'native_exit_spot_seconds'):
                require(key in costs, f'V8 exit audit cost missing: {key}')
            if all(key in costs for key in ('native_exit_spot_A4',
                                            'native_exit_spot_seconds')):
                require(float(costs['native_exit_spot_A4']) ==
                        float(spot['completed_native_A4']) and
                        np.isclose(float(costs['native_exit_spot_seconds']),
                                   float(spot['elapsed_seconds']), rtol=0, atol=1e-12),
                        'V8 exit native spot cost does not match snapshot')

    return dict(passed=not errors, errors=errors,
                complete_calls=complete_calls, identity=identity,
                sequence_calls=len(complete_calls))


def recompute_v8_k1_controls(sequence_summary, i4_rows, pc_rows,
                             exit_rows=(), *, control_metadata=None,
                             budget=None, control_audit_rows=(),
                             profile='balanced_h6_entity_gcrot8_v8') -> dict:
    """Wire completed finite sequence calls to the final four controls.

    The detailed field checks remain in the two existing checkers.  This
    small adapter only verifies the global counter split and uses the live
    control baseline for cumulative deltas; it never treats a missing field as
    zero and never applies the K1 offset to the fresh K2 checker.
    """

    errors = []
    v9 = profile == 'balanced_h6_entity_gcrot8_new16_v9'
    sequence_schema = ('task39extra.review-v9-equal-new-work-sequence.v1'
                       if v9 else 'task39extra.review-v8-recycling-sequence.v1')

    def require(condition, message):
        if not condition:
            errors.append(message)

    if not isinstance(sequence_summary, dict):
        return dict(passed=False, errors=['V8 K1 sequence summary is not a mapping'])
    if not isinstance(control_metadata, dict):
        return dict(passed=False, errors=['V8 K1 control metadata/baseline is missing'])
    reset_summary = sequence_summary.get('reset')
    carry_summary = sequence_summary.get('carry')
    require(sequence_summary.get('schema') == sequence_schema,
            'V8 K1 sequence summary schema is missing or incorrect')
    require(isinstance(reset_summary, dict) and isinstance(carry_summary, dict),
            'V8 K1 RESET/CARRY summaries are incomplete')
    if not isinstance(reset_summary, dict) or not isinstance(carry_summary, dict):
        return dict(passed=False, errors=errors)

    reset = recompute_recycled_i4_sequence(
        reset_summary.get('records'), sequence='RESET', budget=budget,
        profile=profile)
    carry = recompute_recycled_i4_sequence(
        carry_summary.get('records'), sequence='CARRY', profile=profile)
    errors.extend(f'RESET: {error}' for error in reset['errors'])
    errors.extend(f'CARRY: {error}' for error in carry['errors'])

    raw_rows = list(i4_rows or [])
    sequence_calls = reset['complete_calls'] + carry['complete_calls']
    sequence_count = len(sequence_calls)
    require(len(raw_rows) == sequence_count + 4,
            'V8 K1 finite I4 ledger must contain completed sequence and four control rows')
    sequence_raw = raw_rows[:sequence_count]
    control_raw = raw_rows[sequence_count:]
    raw_sequence_calls = [_bounded_i4_facts(row).get('call') for row in sequence_raw]
    require(sequence_calls == raw_sequence_calls,
            'V8 K1 raw sequence rows do not match RESET/CARRY records')
    require(sequence_calls == list(range(1, sequence_count + 1)),
            'V8 K1 RESET/CARRY calls are not a continuous global prefix')
    require(sequence_summary.get('total_calls') == sequence_count,
            'V8 K1 sequence total_calls differs from completed records')
    control_start = sequence_count + 1
    control_end = sequence_count + 4
    require(control_metadata.get('control_i4_call_start') == control_start,
            'V8 K1 controls do not follow the completed sequence calls')
    require(control_metadata.get('control_i4_call_end') == control_end,
            'V8 K1 control call end differs from the four control rows')

    baseline = control_metadata.get('control_baseline')
    require(isinstance(baseline, dict),
            'V8 K1 control cumulative baseline is missing')
    if isinstance(baseline, dict):
        baseline_i4 = baseline.get('I4')
        require(isinstance(baseline_i4, dict) and
                baseline_i4.get('calls') == sequence_count,
                'V8 K1 control baseline I4 calls differ from sequence count')
        snapshot = baseline_i4.get('snapshot') if isinstance(baseline_i4, dict) else None
        engine = snapshot.get('engine') if isinstance(snapshot, dict) else None
        pool = engine.get('pool') if isinstance(engine, dict) else None
        require(isinstance(engine, dict) and engine.get('calls') == sequence_count,
                'V8 K1 baseline engine call counter differs from sequence count')
        require(isinstance(pool, dict) and pool.get('pairs') == 0,
                'V8 K1 baseline pool is not empty')

    control = recompute_bounded_i4(
        control_raw, list(pc_rows or []), list(exit_rows or []),
        profile=profile, call_start=control_start,
        native_seen_before=False)
    errors.extend(f'CONTROLS: {error}' for error in control['errors'])
    costs = recompute_bounded_costs(
        control_raw, list(pc_rows or []), list(exit_rows or []),
        baseline if isinstance(baseline, dict) else {}, require_lifetime=True,
        control_audit_rows=control_audit_rows)
    errors.extend(f'COSTS: {error}' for error in costs['errors'])
    return dict(passed=not errors, errors=errors, reset=reset, carry=carry,
                bounded_i4=control, bounded_costs=costs,
                control_i4_call_start=control_start, control_i4_call_end=control_end)


def recompute_bounded_screen(solve, rows):
    """Recompute the V7 8-step screen and its 128/1800/5400 gates."""
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(solve.get('screen_enabled') is True, 'V7 bounded screen is disabled')
    require(solve.get('screen_policy') == 'v7', 'bounded solve is not using V7 screen')
    require(solve.get('restart') == 32 and solve.get('max_it') == 2048,
            'bounded outer restart/max_it mismatch')
    require(solve.get('zero_start') is True, 'bounded outer solve is not zero-start')
    require(solve.get('ksp_create_count') == solve.get('ksp_solve_count') ==
            solve.get('ksp_destroy_count') == 1, 'bounded outer does not have one KSP lifecycle')
    require(solve.get('residual_interval') == 8 and solve.get('checkpoint_interval') == 32,
            'bounded outer cadence mismatch')
    history = [(0, 1.0)]
    screen = None
    mid = None
    nodes = []
    previous = (-1, -1.0)
    for row in rows:
        try:
            iteration = int(row['iteration'])
            relative = float(row['explicit_true_residual'])
            seconds = float(row['solve_seconds'])
        except (KeyError, TypeError, ValueError):
            errors.append('malformed V7 monitor row')
            continue
        require(iteration >= previous[0], 'V7 monitor iterations are not monotone')
        require(np.isfinite([relative, seconds]).all() and relative >= 0 and seconds >= 0,
                f'invalid V7 monitor scalar at iteration {iteration}')
        previous = (iteration, seconds)
        if iteration == 0:
            if not nodes:
                nodes.append((iteration, relative))
        elif iteration % 8 == 0 and (not nodes or nodes[-1][0] != iteration):
            nodes.append((iteration, relative))
            history = (history + [(iteration, relative)])[-3:]
        # The live solver checks the true residual immediately after the
        # snapshot, before either the investment screen or the 5400-second
        # continuation gate.  A late true pass therefore leaves mid_budget
        # unset even when the screen had already continued the KSP.
        if relative <= 1e-6:
            break
        if screen is None and (iteration >= 128 or seconds >= 1800):
            trend = (len(history) == 3 and history[1][0] - history[0][0] == 8 and
                     history[2][0] - history[1][0] == 8 and
                     0 < history[2][1] < history[1][1] < history[0][1] and
                     np.sqrt(history[2][1] / history[0][1]) <= .80)
            passed = relative <= 1e-2 or (iteration >= 16 and relative <= .30 and trend)
            screen = dict(status='SCREEN_CONTINUE_SAME_LIVE_KSP' if passed else
                          'NORMAL_SCREEN_STOP', passed=bool(passed), iteration=iteration,
                          true_relative=relative, solve_seconds=seconds,
                          checkpoints=list(history), policy='v7')
            if not passed:
                break
        if mid is None and seconds >= 5400:
            passed = relative <= 1e-3
            mid = dict(status='MID_BUDGET_CONTINUE' if passed else
                       'PROGRESS_INSUFFICIENT_AT_MID_BUDGET', passed=bool(passed),
                       iteration=iteration, true_relative=relative,
                       solve_seconds=seconds)
            if not passed:
                break

    saved = solve.get('screen')
    if screen is None:
        require(saved is None, 'saved V7 screen decision differs from recomputation')
    else:
        require(saved is not None, 'missing saved V7 screen decision')
        if saved is not None:
            for key in ('status', 'passed', 'iteration', 'policy'):
                require(saved.get(key) == screen.get(key),
                        f'saved V7 screen {key} differs from raw nodes')
            for key in ('true_relative', 'solve_seconds'):
                require(np.isclose(float(saved.get(key)), float(screen.get(key)),
                                   rtol=0, atol=1e-10),
                        f'saved V7 screen {key} differs from raw nodes')
            def normalized_checkpoints(value):
                return [(int(item[0]), float(item[1])) for item in (value or [])]
            saved_nodes = normalized_checkpoints(saved.get('checkpoints'))
            raw_nodes = normalized_checkpoints(screen.get('checkpoints'))
            require(len(saved_nodes) == len(raw_nodes) and all(
                left[0] == right[0] and np.isclose(left[1], right[1], rtol=0, atol=1e-12)
                for left, right in zip(saved_nodes, raw_nodes)),
                'saved V7 checkpoint history differs from raw 8-step nodes')
    require(solve.get('mid_budget') == mid,
            'saved V7 mid-budget decision differs from raw monitor')
    return dict(passed=not errors, errors=errors, nodes=nodes,
                recomputed_screen=screen, recomputed_mid_budget=mid)


def recompute_v9_bounded_screen(solve, rows):
    """Recompute the V9 absolute 1800-second progress screen.

    Eight-step residuals, including iteration 128, are observations only.
    The first decision is the first raw node at or after 1800 seconds and
    uses the absolute ``rho <= 0.10`` gate.  The later 5400-second gate keeps
    the existing bounded-workflow continuation rule.
    """
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(solve.get('screen_enabled') is True, 'V9 bounded screen is disabled')
    require(solve.get('screen_policy') == 'v9_equal_new_work',
            'V9 bounded screen policy is missing')
    require(solve.get('restart') == 32 and solve.get('max_it') == 2048,
            'V9 bounded outer restart/max_it mismatch')
    require(solve.get('zero_start') is True, 'V9 bounded outer solve is not zero-start')
    require(solve.get('ksp_create_count') == solve.get('ksp_solve_count') ==
            solve.get('ksp_destroy_count') == 1,
            'V9 bounded outer does not have one KSP lifecycle')
    require(solve.get('residual_interval') == 8 and solve.get('checkpoint_interval') == 32,
            'V9 bounded outer cadence mismatch')
    history = []
    screen = None
    mid = None
    nodes = []
    previous_iteration = -1
    previous_seconds = -1.0
    for row in rows:
        try:
            iteration = int(row['iteration'])
            relative = float(row['explicit_true_residual'])
            seconds = float(row['solve_seconds'])
        except (KeyError, TypeError, ValueError):
            errors.append('malformed V9 monitor row')
            continue
        require(iteration >= previous_iteration and seconds >= previous_seconds,
                'V9 monitor order is not monotone')
        require(np.isfinite([relative, seconds]).all() and relative >= 0 and seconds >= 0,
                f'invalid V9 monitor scalar at iteration {iteration}')
        previous_iteration, previous_seconds = iteration, seconds
        if iteration == 0 or iteration % 8 == 0:
            if not nodes or nodes[-1][0] != iteration:
                nodes.append((iteration, relative))
                history = (history + [(iteration, relative)])[-3:]
        if relative <= 1e-6:
            break
        if screen is None and seconds >= 1800:
            passed = bool(relative <= 0.10)
            screen = dict(
                status='SCREEN_CONTINUE_SAME_LIVE_KSP' if passed
                else 'TIME_PROGRESS_SCREEN_STOP',
                passed=passed, iteration=iteration,
                true_relative=relative, solve_seconds=seconds,
                checkpoints=list(history), policy='v9_equal_new_work')
            if not passed:
                break
        if mid is None and seconds >= 5400:
            passed = bool(relative <= 1e-3)
            mid = dict(
                status='MID_BUDGET_CONTINUE' if passed
                else 'PROGRESS_INSUFFICIENT_AT_MID_BUDGET',
                passed=passed, iteration=iteration,
                true_relative=relative, solve_seconds=seconds)
            if not passed:
                break

    saved = solve.get('screen')
    if screen is None:
        require(saved is None, 'saved V9 screen decision differs from recomputation')
    else:
        require(isinstance(saved, dict), 'missing saved V9 screen decision')
        if isinstance(saved, dict):
            for key in ('status', 'passed', 'iteration', 'policy'):
                require(saved.get(key) == screen.get(key),
                        f'saved V9 screen {key} differs from raw nodes')
            for key in ('true_relative', 'solve_seconds'):
                require(np.isclose(float(saved.get(key)), float(screen.get(key)),
                                   rtol=0, atol=1e-10),
                        f'saved V9 screen {key} differs from raw nodes')
            saved_nodes = [(int(item[0]), float(item[1]))
                           for item in (saved.get('checkpoints') or [])]
            require(len(saved_nodes) == len(screen['checkpoints']) and all(
                left[0] == right[0] and np.isclose(left[1], right[1], rtol=0, atol=1e-12)
                for left, right in zip(saved_nodes, screen['checkpoints'])),
                'saved V9 checkpoint observations differ from raw 8-step nodes')
    require(solve.get('mid_budget') == mid,
            'saved V9 mid-budget decision differs from raw monitor')
    return dict(passed=not errors, errors=errors, nodes=nodes,
                recomputed_screen=screen, recomputed_mid_budget=mid)


def recompute_bounded_costs(i4_rows, pc_rows, exit_rows=(), setup_costs=None,
                            *, require_lifetime=False, control_audit_rows=()) -> dict:
    """Recompute cumulative bounded costs, subtracting setup exactly once.

    ``control_audit_rows`` is deliberately opt-in.  V8 K1 calls
    ``InexactBalanceLedger.audit_last`` once for each named control after its
    two coarse calls; those explicit audit records are separate from the
    automatic per-PC audit and the final exit audit.  Keeping the argument
    empty preserves the formal V7 accounting contract.
    """
    errors = []
    missing = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    setup = setup_costs or {}
    control_audit_rows = list(control_audit_rows or ())
    explicit_control_audits = len(control_audit_rows)
    zero_b4 = dict(applies=0, attempted=0, counts={}, operation_seconds={})
    setup_b4 = setup.get('B4', zero_b4)
    setup_i4 = setup.get('I4', {})
    setup_audit = setup.get('inexact_audit', {})
    setup_s = setup.get('S_action', {})
    setup_bottom = setup.get('bottom', {}).get('counts', setup.get('bottom', {}))

    def delta(total, baseline, key):
        if key not in total:
            return None
        value = float(total.get(key, 0)) - float(baseline.get(key, 0))
        require(value >= -1e-12, f'cumulative {key} regressed across setup boundary')
        return value

    i4_totals = {
        key: sum(int(_bounded_i4_facts(row).get(key, 0)) for row in i4_rows)
        for key in ('A4_matvec', 'B4_calls', 'explicit_A4')
    }
    expected_b4 = dict(
        applies=i4_totals['B4_calls'], attempted=i4_totals['B4_calls'],
        counts=dict(A_inner_true=0, A_structure=2*i4_totals['B4_calls'],
                    C=2*i4_totals['B4_calls'], PH_audit=2*i4_totals['B4_calls'],
                    smoother=i4_totals['B4_calls']))
    per_pc_trace = [row.get('trace_counts', {}) for row in pc_rows]
    have_b4 = all('B4' in trace for trace in per_pc_trace)
    have_s = all('S_action' in trace for trace in per_pc_trace)
    have_audit = all('inexact_audit' in trace for trace in per_pc_trace)
    if require_lifetime:
        for present, name in ((have_b4, 'B4'), (have_s, 'S_action'),
                              (have_audit, 'inexact_audit')):
            if not present:
                missing.append(name)
        require(not missing, 'bounded per-PC lifetime counters are missing: '+','.join(missing))

    if control_audit_rows:
        require(len(control_audit_rows) == len(pc_rows),
                'V8 K1 explicit control audit row count differs from PC records')
        require(len(control_audit_rows) == len(_V8_K1_CONTROL_LABELS),
                'V8 K1 explicit control audit count differs from the two-control contract')
        for index, row in enumerate(control_audit_rows, 1):
            require(isinstance(row, dict),
                    f'V8 K1 explicit control audit record is not a mapping at {index}')
            if not isinstance(row, dict):
                continue
            expected_label = _V8_K1_CONTROL_LABELS[index - 1] \
                if index <= len(_V8_K1_CONTROL_LABELS) else None
            require(row.get('status') == 'COMPLETE',
                    f'V8 K1 explicit control audit status is not COMPLETE at {index}')
            require(row.get('label') == expected_label,
                    f'V8 K1 explicit control audit label/order mismatch at {index}')
            require(row.get('complete_pc_calls') == index,
                    f'V8 K1 explicit control audit PC count mismatch at {index}')
            balance = row.get('balance')
            require(isinstance(balance, dict),
                    f'V8 K1 explicit control balance record is missing at {index}')
            if not isinstance(balance, dict):
                continue
            for key in ('actual_defect_norm', 'closure_norm', 'operation_scale',
                        'closure_relative', 'closure_limit', 'defect_scaled'):
                require(_finite_number(balance.get(key), nonnegative=True),
                        f'V8 K1 explicit control balance field is invalid at {index}: {key}')
            if _finite_number(balance.get('operation_scale'), nonnegative=True):
                require(float(balance['operation_scale']) > 0.0,
                        f'V8 K1 explicit control operation scale is not positive at {index}')
            if all(key in balance for key in ('closure_relative', 'closure_limit')):
                require(balance['closure_limit'] == 1e-8,
                        f'V8 K1 explicit control closure limit changed at {index}')
                require(float(balance['closure_relative']) <=
                        float(balance['closure_limit']),
                        f'V8 K1 explicit control closure failed at {index}')
            if (_finite_number(balance.get('closure_norm'), nonnegative=True) and
                    _finite_number(balance.get('operation_scale'), nonnegative=True) and
                    float(balance['operation_scale']) > 0.0):
                expected_relative = (float(balance['closure_norm']) /
                                     float(balance['operation_scale']))
                require(np.isclose(float(balance['closure_relative']),
                                   expected_relative, rtol=0, atol=1e-15),
                        f'V8 K1 explicit control closure relative is not independently '
                        f'recomputed at {index}')
            g2_relative = row.get('g2_relative')
            require(_finite_number(g2_relative, nonnegative=True) and
                    float(g2_relative) <= 1e-10,
                    f'V8 K1 explicit control g2 recompute failed at {index}')

    for name, present in (('B4', have_b4), ('S_action', have_s),
                          ('inexact_audit', have_audit)):
        if present:
            previous = None
            for trace in per_pc_trace:
                counter = trace[name]
                current = float(counter.get('applies', counter.get('calls',
                                  counter.get('audits', 0))))
                if previous is not None:
                    require(current >= previous, f'{name} lifetime counter regressed')
                previous = current

    exit_row = list(exit_rows or [])[-1] if exit_rows else None
    total = exit_row.get('total', {}) if exit_row else {}
    if total:
        b4 = total.get('B4', {})
        b4_applies = delta(b4, setup_b4, 'applies')
        b4_attempted = delta(b4, setup_b4, 'attempted')
        require(b4_applies == expected_b4['applies'], 'B4 apply total differs from I4 calls')
        require(b4_attempted == expected_b4['attempted'], 'B4 attempted total differs from I4 calls')
        for key, expected in expected_b4['counts'].items():
            require(delta(b4.get('counts', {}), setup_b4.get('counts', {}), key) == expected,
                    f'B4 {key} total differs from independent I4 accounting')
        if have_b4 and per_pc_trace:
            last_b4 = per_pc_trace[-1]['B4']
            for key in ('applies', 'attempted'):
                require(delta(b4, setup_b4, key) ==
                        delta(last_b4, setup_b4, key),
                        f'B4 terminal count differs from last PC lifetime snapshot: {key}')
            for key, value in b4.get('operation_seconds', {}).items():
                if key in last_b4.get('operation_seconds', {}):
                    require(np.isclose(
                        float(value) - float(setup_b4.get('operation_seconds', {}).get(key, 0.0)),
                        float(last_b4['operation_seconds'][key]) -
                        float(setup_b4.get('operation_seconds', {}).get(key, 0.0)),
                        rtol=0, atol=1e-10),
                        f'B4 terminal seconds differs from last PC snapshot: {key}')
        i4_total = total.get('I4', {})
        require(delta(i4_total, setup_i4, 'calls') == len(i4_rows),
                'I4 cumulative calls re-add setup or disagree with raw records')
        outer_total = delta(total, setup, 'outer_PC_applies')
        require(outer_total == len(pc_rows), 'outer PC cumulative count mismatch')
        bottom = total.get('bottom', {}).get('counts', {})
        if bottom:
            mat_solve = delta(bottom, setup_bottom, 'MatSolve')
            per_pc_bottom = [trace.get('bottom', {}) for trace in per_pc_trace]
            if all('MatSolve' in row for row in per_pc_bottom):
                require(float(per_pc_bottom[-1]['MatSolve']) - float(setup_bottom.get('MatSolve', 0))
                        == mat_solve, 'MatSolve setup-subtracted total disagrees with PC trace')
        s_total = total.get('S_action', {})
        if s_total:
            s_calls = delta(s_total, setup_s, 'calls')
            if have_s and per_pc_trace:
                last_s = per_pc_trace[-1]['S_action']
                require(s_calls == delta(last_s, setup_s, 'calls'),
                        'S_action terminal count differs from last PC snapshot')
                if 'seconds' in s_total and 'seconds' in last_s:
                    require(np.isclose(
                        float(s_total['seconds']) - float(setup_s.get('seconds', 0.0)),
                        float(last_s['seconds']) - float(setup_s.get('seconds', 0.0)),
                        rtol=0, atol=1e-10),
                        'S_action terminal seconds differs from last PC snapshot')
        audit_total = total.get('inexact_audit', {})
        if audit_total and (have_audit or require_lifetime):
            audits = delta(audit_total, setup_audit, 'audits')
            expected_audits = (sum(
                row.get('inexact_balance', {}).get('actual_audit') == 'PASS'
                for row in pc_rows) + explicit_control_audits + 1)
            require(audits == expected_audits,
                    ('inexact audit total does not equal independently counted PC, '
                     'explicit control, and exit audits'
                     if explicit_control_audits else
                     'inexact audit total does not equal PC audits plus one exit audit'))
            exit_costs = (exit_row or {}).get('audit_costs', {})
            for key in ('audits', 'extra_A6', 'extra_PH'):
                if key in exit_costs:
                    total_delta = delta(audit_total, setup_audit, key)
                    expected_total = (expected_audits if key != 'audits' else expected_audits)
                    require(total_delta == expected_total,
                            f'inexact {key} total differs from independently counted audits')
                    require(float(exit_costs[key]) == 1.0,
                            f'exit audit {key} cost is not exactly one audit')
    else:
        missing.append('bounded_exit_audit.total')
        require(not require_lifetime, 'bounded exit cumulative counters are missing')

    expected_inexact_audits = None
    if total and total.get('inexact_audit', {}):
        expected_inexact_audits = (sum(
            row.get('inexact_balance', {}).get('actual_audit') == 'PASS'
            for row in pc_rows) + explicit_control_audits + 1)
    return dict(passed=not errors, errors=errors, missing=missing,
                i4_totals=i4_totals, expected_b4=expected_b4,
                explicit_control_audits=explicit_control_audits,
                expected_inexact_audits=expected_inexact_audits,
                setup=setup, setup_counts_separate=True)


def recompute_projected_trace_costs(pc_rows, exit_rows=(), storage=None,
                                    setup_costs=None) -> dict:
    """Recompute full252 sequential-route work from raw lifetime counters.

    Route B keeps the generic BAL_H accounting, but every trace application
    additionally performs one complete current physical ``T`` action and one
    backsolve in each of the 252 restored patch factors.  All comparisons are
    deltas from the saved setup snapshot, so a finite prerequisite fixture is
    not mistaken for solve work and its counters are never assumed to start at
    zero.
    """
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    def count(container, key, label):
        value = container.get(key) if isinstance(container, dict) else None
        valid = (isinstance(value, (int, np.integer)) and not isinstance(value, bool)
                 and value >= 0)
        require(valid, f'{label} {key} is missing or invalid')
        return int(value) if valid else None

    def scalar(container, key, label):
        value = container.get(key) if isinstance(container, dict) else None
        valid = (isinstance(value, (int, float, np.integer, np.floating))
                 and not isinstance(value, bool) and np.isfinite(value) and value >= 0)
        require(valid, f'{label} {key} is missing or invalid')
        return float(value) if valid else None

    projected = (storage or {}).get('projected') if isinstance(storage, dict) else None
    require(isinstance(projected, dict), 'projected trace setup identity is missing')
    if isinstance(projected, dict):
        require(projected.get('source_sha') == 'dcca0f5ea6b7ba9221b23dd210a3c06839cc47be',
                'projected trace source identity differs')
        require(projected.get('factor_count') == 252,
                'projected trace factor count is not 252')
        require(projected.get('factor_dimension') == 144,
                'projected trace factor dimension is not 144')
        require(projected.get('grouping') == 'structured_cell_coordinate_parity_(i+j+k)%2',
                'projected trace grouping identity differs')
        require(projected.get('group_counts') and
                sum(projected.get('group_counts', ())) == 252,
                'projected trace group counts do not cover 252 factors')
        require(projected.get('restored_factor_count') == 252,
                'projected trace did not restore exactly 252 factors')
        require(projected.get('setup_s_column_solves') == 0,
                'projected trace performed forbidden setup S-column solves')
        require(projected.get('no_saved_entity_lu_overlap') is True,
                'projected trace retained the old entity LU path')
        require(projected.get('formula') == 'M0 + M1 - M1*T*M0',
                'projected trace formula identity differs')

    setup = setup_costs if isinstance(setup_costs, dict) else {}
    setup_trace = setup.get('trace', {})
    setup_entities = setup_trace.get('counts', {}) if isinstance(setup_trace, dict) else {}
    setup_joint = setup_trace.get('joint', {}) if isinstance(setup_trace, dict) else {}
    setup_T = setup_trace.get('projected_T', {}) if isinstance(setup_trace, dict) else {}
    setup_B4 = setup.get('B4', {})
    setup_S = setup.get('S_action', {})
    setup_cached = setup.get('cached', {})
    setup_cached = (setup_cached.get('counts', {})
                    if isinstance(setup_cached, dict) and 'counts' in setup_cached
                    else setup_cached)
    setup_bottom = setup.get('bottom', {})
    setup_bottom = (setup_bottom.get('counts', {})
                    if isinstance(setup_bottom, dict) and 'counts' in setup_bottom
                    else setup_bottom)
    for container, label in ((setup_trace, 'projected setup trace'),
                             (setup_T, 'projected setup T'),
                             (setup_joint, 'projected setup joint'),
                             (setup_B4, 'projected setup B4'),
                             (setup_S, 'projected setup S'),
                             (setup_cached, 'projected setup cached A4'),
                             (setup_bottom, 'projected setup bottom')):
        require(isinstance(container, dict), f'{label} baseline is missing')
    for key in ('calls', 'F', 'FH', 'A4', 'CU'):
        count(setup_T, key, 'projected setup T')
    scalar(setup_T, 'seconds', 'projected setup T')
    # The setup trace is the only authoritative baseline for the inner
    # counters; the generic setup costs provide the B4 and coarse-S baselines.
    base_T = {key: count(setup_T, key, 'projected setup T')
              for key in ('calls', 'F', 'FH', 'A4', 'CU')}
    base_entities = {key: count(setup_entities, key, 'projected setup entity')
                     for key in ('HT', 'F', 'FH', 'E', 'EH', 'volume', 'volume_adjoint')}
    base_joint = {key: count(setup_joint, key, 'projected setup joint')
                  for key in ('applications', 'sequential_applications', 'T_started',
                              'T_completed', 'patch_apply_rhs', 'patch_MatSolve',
                              'group0_patch_apply_rhs', 'group1_patch_apply_rhs',
                              'patch_LU', 'restored_factors')}
    base_b4 = count(setup_B4, 'applies', 'projected setup B4')
    base_s = count(setup_S, 'calls', 'projected setup S')
    base_cached = {key: count(setup_cached, key, 'projected setup cached A4')
                   for key in ('started', 'completed')}
    base_bottom = {key: count(setup_bottom, key, 'projected setup bottom')
                   for key in ('MatSolve', 'refinement')}
    if (any(value is None for value in base_T.values()) or
            any(value is None for value in base_entities.values()) or
            any(value is None for value in base_joint.values()) or
            base_b4 is None or base_s is None or
            any(value is None for value in base_cached.values()) or
            any(value is None for value in base_bottom.values())):
        return dict(passed=False, errors=errors,
                    completed_pc_count=len(pc_rows), T_calls=0,
                    patch_backsolves=0, bottom_mat_solves=0, setup=projected)

    traces = [row.get('trace_counts', {}) for row in pc_rows]
    require(bool(traces), 'projected trace has no completed PC snapshots')
    previous = {}
    last = None
    for index, trace in enumerate(traces, 1):
        entities = trace.get('entities') if isinstance(trace, dict) else None
        joint = trace.get('joint') if isinstance(trace, dict) else None
        current = trace.get('projected_T') if isinstance(trace, dict) else None
        b4 = trace.get('B4') if isinstance(trace, dict) else None
        coarse = trace.get('S_action') if isinstance(trace, dict) else None
        cached = trace.get('cached') if isinstance(trace, dict) else None
        bottom = trace.get('bottom') if isinstance(trace, dict) else None
        if not isinstance(entities, dict):
            require(False, f'projected PC {index} entity counters missing')
        if not isinstance(joint, dict):
            require(False, f'projected PC {index} joint counters missing')
        if not isinstance(current, dict):
            require(False, f'projected PC {index} T counters missing')
            continue
        if not isinstance(b4, dict):
            require(False, f'projected PC {index} B4 counters missing')
            continue
        if not isinstance(coarse, dict):
            require(False, f'projected PC {index} S counters missing')
            continue
        if not isinstance(cached, dict):
            require(False, f'projected PC {index} cached A4 counters missing')
            continue
        if not isinstance(bottom, dict):
            require(False, f'projected PC {index} bottom counters missing')
            continue

        t_keys = ('calls', 'F', 'FH', 'A4', 'CU')
        t_values = {key: count(current, key, f'projected PC {index} T') for key in t_keys}
        seconds = scalar(current, 'seconds', f'projected PC {index} T')
        if any(value is None for value in t_values.values()) or seconds is None:
            continue
        if previous:
            for key in (*t_keys, 'seconds'):
                left = seconds if key == 'seconds' else t_values[key]
                right = previous[key]
                require(left >= right,
                        f'projected T lifetime counter regressed: {key} at PC {index}')
        previous = dict(t_values, seconds=seconds)

        b4_value = count(b4, 'applies', f'projected PC {index} B4')
        s_value = count(coarse, 'calls', f'projected PC {index} S')
        cached_values = {key: count(cached, key, f'projected PC {index} cached A4')
                         for key in ('started', 'completed')}
        bottom_values = {key: count(bottom, key, f'projected PC {index} bottom')
                         for key in ('MatSolve', 'refinement')}
        entity_values = {key: count(entities, key, f'projected PC {index} entity')
                         for key in ('HT', 'F', 'FH', 'E', 'EH', 'volume', 'volume_adjoint')}
        joint_values = {key: count(joint, key, f'projected PC {index} joint')
                        for key in ('applications', 'sequential_applications', 'T_started',
                                    'T_completed', 'patch_apply_rhs', 'patch_MatSolve',
                                    'group0_patch_apply_rhs', 'group1_patch_apply_rhs',
                                    'patch_LU', 'restored_factors')}
        if b4_value is None or s_value is None or any(value is None for value in cached_values.values()) or \
                any(value is None for value in bottom_values.values()) or \
                any(value is None for value in entity_values.values()) or \
                any(value is None for value in joint_values.values()):
            continue
        if last is not None:
            for key in joint_values:
                require(joint_values[key] >= last['joint'][key],
                        f'projected joint lifetime counter regressed: {key} at PC {index}')
        delta_t = {key: t_values[key] - base_T[key] for key in t_keys}
        delta_b4 = b4_value - base_b4
        delta_s = s_value - base_s
        delta_cached = {key: cached_values[key] - base_cached[key]
                        for key in cached_values}
        delta_bottom = {key: bottom_values[key] - base_bottom[key]
                        for key in bottom_values}
        delta_entities = {key: entity_values[key] - base_entities[key]
                          for key in entity_values}
        delta_joint = {key: joint_values[key] - base_joint[key]
                       for key in joint_values}
        require(all(value >= 0 for value in (*delta_t.values(), delta_b4, delta_s,
                                               *delta_bottom.values(),
                                               *delta_entities.values(), *delta_joint.values())),
                f'projected lifetime counter regressed across setup at PC {index}')
        calls = delta_t['calls']
        require(delta_b4 == calls and delta_entities['HT'] == calls,
                f'projected PC {index} B4/HT/T call deltas differ')
        require(delta_t['F'] == calls and delta_t['FH'] == calls and
                delta_t['A4'] == 2 * calls and delta_t['CU'] == calls,
                f'projected PC {index} T physical/coarse costs differ')
        require(delta_cached['started'] == delta_cached['completed'] ==
                3 * delta_b4 + 2 * calls,
                f'projected PC {index} cached A4 cost misses base or T actions')
        require(delta_joint['applications'] == calls and
                delta_joint['sequential_applications'] == calls and
                delta_joint['T_started'] == calls and delta_joint['T_completed'] == calls,
                f'projected PC {index} does not have one complete T per apply')
        require(delta_joint['group0_patch_apply_rhs'] + delta_joint['group1_patch_apply_rhs'] == 252 * calls and
                delta_joint['patch_apply_rhs'] == 252 * calls and
                delta_joint['patch_MatSolve'] == 252 * calls,
                f'projected PC {index} patch backsolve count differs from 252*T')
        require(joint_values['patch_LU'] == base_joint['patch_LU'] and
                joint_values['restored_factors'] == base_joint['restored_factors'] == 252,
                f'projected PC {index} refactored or lost restored factors')
        require(delta_entities['F'] == 2 * calls and delta_entities['FH'] == 2 * calls and
                delta_entities['E'] == 5 * calls and delta_entities['volume'] == 5 * calls and
                delta_entities['EH'] == 2 * calls and
                delta_entities['volume_adjoint'] == 2 * calls,
                f'projected PC {index} physical F/CU callback costs differ')
        # The two ordinary BAL_H C calls cost 2 logical S applications per
        # B4. T contributes one additional coarse/S feedback. A bottom
        # refinement performs one extra physical S action and is reported
        # separately; it is not a patch MatSolve.
        logical_s = delta_s - delta_bottom['refinement']
        require(logical_s == 2 * delta_b4 + delta_t['CU'] and
                delta_bottom['MatSolve'] == delta_s,
                f'projected PC {index} coarse S logical cost differs')
        last = dict(projected=t_values, joint=joint_values, entities=entity_values,
                    b4=b4_value, S=s_value, cached=cached_values,
                    bottom=bottom_values)

    terminal = list(exit_rows or [])[-1].get('total', {}) if exit_rows else {}
    terminal_trace = terminal.get('trace', {}) if isinstance(terminal, dict) else {}
    require(isinstance(terminal_trace, dict), 'projected terminal trace snapshot is missing')
    if isinstance(terminal_trace, dict) and last is not None:
        terminal_projected = terminal_trace.get('projected_T')
        terminal_joint = terminal_trace.get('joint')
        terminal_entities = terminal_trace.get('counts')
        terminal_b4 = terminal.get('B4', {}) if isinstance(terminal, dict) else {}
        terminal_s = terminal.get('S_action', {}) if isinstance(terminal, dict) else {}
        terminal_cached = terminal.get('cached', {}).get('counts', {}) \
            if isinstance(terminal, dict) else {}
        terminal_bottom = terminal.get('bottom', {}).get('counts', {}) \
            if isinstance(terminal, dict) else {}
        for key, value in last['projected'].items():
            actual = scalar(terminal_projected, key, 'projected terminal T')
            require(actual is not None and np.isclose(actual, float(value), rtol=0, atol=1e-10),
                    f'projected terminal T counter differs: {key}')
        for key, value in last['joint'].items():
            actual = count(terminal_joint, key, 'projected terminal joint')
            require(actual == value, f'projected terminal joint counter differs: {key}')
        for key, value in last['entities'].items():
            actual = count(terminal_entities, key, 'projected terminal entity')
            require(actual == value, f'projected terminal entity counter differs: {key}')
        require(count(terminal_b4, 'applies', 'projected terminal B4') == last['b4'],
                'projected terminal B4 counter differs')
        require(count(terminal_s, 'calls', 'projected terminal S') == last['S'],
                'projected terminal S counter differs')
        for key, value in last['cached'].items():
            actual = count(terminal_cached, key, 'projected terminal cached A4')
            require(actual == value, f'projected terminal cached A4 counter differs: {key}')
        for key, value in last['bottom'].items():
            actual = count(terminal_bottom, key, 'projected terminal bottom')
            require(actual == value, f'projected terminal bottom counter differs: {key}')

    setup_calls = base_T['calls']
    return dict(passed=not errors, errors=errors,
                completed_pc_count=len(pc_rows),
                T_calls=(last['projected']['calls'] - setup_calls) if last else 0,
                patch_backsolves=(last['joint']['patch_MatSolve'] - base_joint['patch_MatSolve'])
                if last else 0,
                bottom_mat_solves=(last['bottom']['MatSolve'] - base_bottom['MatSolve'])
                if last else 0,
                setup=projected)


def bounded_output_classification(summary, errors, expected_errors=()):
    """Classify bounded results without allowing schema errors to pass."""
    if not errors:
        if summary.get('status') == 'RESIDUAL_PASS':
            # Bounded V7 is a separate accounting path, but its successful
            # result remains consumed by the existing balanced output gate.
            return 'BALANCED_OUTPUT_PASS'
        if summary.get('status') in _BOUNDED_NEGATIVE_STATUSES:
            return summary['status']
        if summary.get('status') in ('BALANCED_OUTPUT_PASS',
                                     'BALANCED_OUTPUT_AUTHORITY_LIMITED'):
            return summary['status']
        return 'CORRECTNESS_OR_EVIDENCE_BLOCKED'
    if summary.get('status') in _BOUNDED_NEGATIVE_STATUSES:
        return (summary['status'] if all(error in expected_errors for error in errors)
                else 'CORRECTNESS_OR_EVIDENCE_BLOCKED')
    return 'NUMERICAL_OR_OUTPUT_FAIL'


def recompute_positive_apply_counts(pc_records: list[dict], cycles: list[dict]) -> dict:
    """Count recorded calls, not the sum of lifetime apply ordinals.

    Only completed PC records are covered; an interrupted PC has no inferred cost.
    This read-only audit does not change the historical ledger or solver verdict.
    """
    previous = {'s6': 0, 's3': 0}
    light = bool(pc_records and pc_records[0].get('positive_identity') == 'H6')
    keys = _POSITIVE_APPLY_KEYS + (('h6_apply_count', 'b6_action_count', 'positive_p1_apply_count') if light else ())
    h6_ordinal = 0
    per_pc = []
    for index, pc in enumerate(pc_records, 1):
        if pc['apply_count'] != index:
            raise ValueError('noncontiguous completed PC records')
        counts = {'s6_apply_count': 0, 's3_apply_count': 0}
        if light:
            if pc.get('positive_identity') != 'H6':
                raise ValueError('mixed positive identities in one run')
            counts.update(h6_apply_count=0, b6_action_count=0, positive_p1_apply_count=0)
        for direction in pc['direction_facts']:
            positive = direction.get('positive_cycle_facts')
            if positive is None:
                continue
            if light:
                if positive['apply_count'] != h6_ordinal+1 or positive['matrix_mult_count'] != 2:
                    raise ValueError('H6 ordinal or actual B6 count mismatch')
                h6_ordinal += 1
                counts['h6_apply_count'] += 1
                counts['b6_action_count'] += positive['matrix_mult_count']
                if 'lower_cycle_facts' in positive:
                    raise ValueError('H6 evidence unexpectedly contains a coarse cycle')
                continue
            for prefix, facts in (('s6', positive), ('s3', positive['lower_cycle_facts'])):
                ordinal = facts['apply_count']
                if ordinal != previous[prefix] + 1:
                    raise ValueError(f'noncontiguous {prefix} lifetime ordinal')
                previous[prefix] = ordinal
                counts[prefix + '_apply_count'] += 1
        if light and (counts['h6_apply_count'] != 2 or counts['b6_action_count'] != 4):
            raise ValueError('light PC did not execute two H6/four B6 calls')
        per_pc.append(counts)
    offset, corrected = 0, []
    for cycle in cycles:
        count = cycle['pc_apply_count']
        if count < 0 or offset + count > len(per_pc):
            raise ValueError('cycle exceeds completed PC records')
        selected = per_pc[offset:offset + count]
        values = {key: sum(row[key] for row in selected) for key in keys}
        corrected.append(dict(cycle_index=cycle['cycle_index'], end_iteration=cycle['end_iteration'],
            completed_pcs=count, recomputed=values,
            raw_reported={key: cycle['pc_costs'][key] for key in values}))
        offset += count
    return dict(scope='completed PC records only; partial PC costs unavailable', cycles=corrected,
        total={key: sum(row[key] for row in per_pc) for key in keys},
        completed_pc_count=len(per_pc), completed_pcs_after_last_cycle=len(per_pc)-offset,
        tail={key: sum(row[key] for row in per_pc[offset:]) for key in keys})


def recompute_p4_decisions(decisions, pc_rows):
    groups={};errors=[];external=0
    for row in decisions:
        logical=row['logical_rhs'];iteration=row['refinement_steps']
        group=groups.setdefault(logical,[])
        relative=row['true_residual_norm']/max(row['original_rhs_norm'],np.finfo(float).tiny)
        if (iteration!=len(group) or iteration>2 or row['external_solves']-external not in (0,1) or
                not np.isfinite(relative) or abs(relative-row['final_true_residual'])>1e-12):
            errors.append('decision ordering/norm/count mismatch')
        if group and (group[-1]['final_true_residual']<=1e-10 or
                      group[0]['original_rhs_norm']!=row['original_rhs_norm']):
            errors.append('refinement after pass or changed normalization')
        external=row['external_solves']
        group.append(row)
    if list(groups)!=list(range(1,len(groups)+1)):
        errors.append('noncontiguous logical RHS')
    if any(g[-1]['true_residual_norm']/max(g[-1]['original_rhs_norm'],np.finfo(float).tiny)>1e-10 for g in groups.values()):
        errors.append('final A4 residual missed')
    if external!=sum(r['p4_counts']['MatSolve'] for r in pc_rows) or len(groups)!=sum(r['p4_counts']['C'] for r in pc_rows):
        errors.append('PC/MatSolve totals differ')
    return dict(passed=not errors,errors=errors,logical_rhs=len(groups),MatSolve=external,
                refinements=len(decisions)-len(groups))


def recompute_balanced_screen(solve, rows):
    if not solve['screen_enabled']:
        return dict(matches=solve.get('screen') is None, enabled=False)
    history=[]; decision=None
    for row in rows:
        i=row['iteration']; r=row['explicit_true_residual']
        if i and i%32==0 and (not history or history[-1][0]!=i):
            history=(history+[(i,r)])[-3:]
        if i>=128 or row['solve_seconds']>=1800:
            if r<=1e-6 and solve.get('screen') is None:
                return dict(matches=True,converged_before_screen=True)
            trend=(len(history)==3 and history[1][0]-history[0][0]==32 and
                history[2][0]-history[1][0]==32 and 0<history[2][1]<history[1][1]<history[0][1]
                and np.sqrt(history[2][1]/history[0][1])<=.65)
            decision=dict(iteration=i,passed=bool(r<=1e-2 or trend));break
    saved=solve.get('screen')
    matches=(saved is None) if decision is None else (saved is not None and
        saved['iteration']==decision['iteration'] and saved['passed']==decision['passed'])
    return dict(matches=matches,recomputed=decision)


def balanced_output_classification(summary, errors, expected_errors=()):
    if not errors:
        return ('BALANCED_OUTPUT_AUTHORITY_LIMITED' if
            summary.get('matched_reference',{}).get('status')=='REFERENCE_AUTHORITY_LIMITED'
            else 'BALANCED_OUTPUT_PASS')
    if summary['status'] in ('SCREEN_BUDGET_NO_QUALIFIED_PROGRESS',
                            'PERFORMANCE_CONTROLLED_STOP','ITERATION_BUDGET_EXHAUSTED'):
        return summary['status'] if all(e in expected_errors for e in errors) else 'CORRECTNESS_OR_EVIDENCE_BLOCKED'
    return 'NUMERICAL_OR_OUTPUT_FAIL'


def check(directory: Path) -> dict:
    started = time.monotonic()
    summary = json.loads((directory / 'physical_intermediate_summary.json').read_text())
    errors, facts, expected_errors = [], {}, []
    controlled = summary['status'] in ('SCREEN_BUDGET_NO_QUALIFIED_PROGRESS',
        'PERFORMANCE_CONTROLLED_STOP', 'ITERATION_BUDGET_EXHAUSTED',
        *_BOUNDED_NEGATIVE_STATUSES)

    def require(condition, message, *, expected=False):
        if not condition:
            errors.append(message)
            if expected:
                expected_errors.append(message)

    def hashed_file(filename, digest):
        path = directory / filename
        require(path.is_relative_to(directory) and path.is_file(), f'missing artifact: {filename}')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'artifact hash mismatch: {filename}')
        return path

    if 'recovery' in summary:
        recovery = summary['recovery']
        origin = Path(recovery['original_directory']).resolve()
        audit_path = Path(recovery['original_audit_path'])
        require(hashlib.sha256(audit_path.read_bytes()).hexdigest() == recovery['original_audit_sha256'],
                'recovery original audit hash mismatch')
        audit = json.loads(audit_path.read_text())
        require(Path(audit['run_directory']).resolve() == origin, 'recovery original path mismatch')
        old_path = origin/'physical_intermediate_summary.json'
        require(hashlib.sha256(old_path.read_bytes()).hexdigest() ==
                audit['artifact_sha256']['physical_intermediate_summary.json'], 'original summary hash mismatch')
        old = json.loads(old_path.read_text())
        require(summary['solve'] == old['solve'] and summary['source_sha'] == old['source_sha'] ==
                recovery['original_source_sha'], 'recovery changed original solve evidence')
        require(all(recovery[k] == 0 for k in ('new_factor_count','new_pc_count','new_ksp_count')),
                'recovery unexpectedly performed a new solve')
        for name in ('pc_applies.jsonl','p4_decisions.jsonl','monitor_residuals.jsonl'):
            require(hashlib.sha256((directory/name).read_bytes()).hexdigest() == audit['artifact_sha256'][name],
                    'recovery copied solve evidence differs: '+name)
        require(summary['final_solution_sha256'] == old['final_solution_sha256'], 'recovery solution identity changed')

    raw = summary['residual_arrays']
    from src.io.physical_balanced_profile import BALANCED_PROFILES, BOUNDED_PROFILES
    from src.io.physical_recursive_profile import RECURSIVE_PROFILES
    recursive = summary['profile']['identity'] in RECURSIVE_PROFILES
    bounded = summary['profile']['identity'] in BOUNDED_PROFILES
    balanced = recursive or summary['profile']['identity'] in BALANCED_PROFILES or bounded
    reference_only = summary['profile'].get('reference_only', False)
    if reference_only:
        ledger = summary['reference_pc_ledger']
        pc_rows = [json.loads(x) for x in hashed_file(ledger['filename'], ledger['sha256']).read_text().splitlines()]
        require(bool(pc_rows), 'missing reference PC solves')
        if balanced:
            decisions = [json.loads(x) for x in (directory/'p4_decisions.jsonl').read_text().splitlines()]
            facts['p4_decisions'] = recompute_p4_decisions(decisions,pc_rows)
            require(facts['p4_decisions']['passed'], 'native A4 final residual or accounting gate failed')
            facts['balanced_screen'] = recompute_balanced_screen(summary['solve'],
                [json.loads(x) for x in (directory/'monitor_residuals.jsonl').read_text().splitlines()])
            require(facts['balanced_screen']['matches'], 'screen decision differs from raw checkpoints')
            require(summary['solve']['ksp_create_count'] == summary['solve']['ksp_solve_count'] ==
                    summary['solve']['ksp_destroy_count'] == 1, 'not one live KSP')
        for row in ([] if balanced else pc_rows):
            inner = row['intermediate']
            numerator, denominator = inner['true_residual_norm'], inner['rhs_norm']
            relative = numerator / max(denominator, np.finfo(float).tiny)
            require(np.isfinite([numerator, denominator, relative]).all() and
                    min(numerator, denominator) >= 0 and relative <= 1e-10,
                    'original A4 reference residual gate failed')
            require(abs(relative-inner['final_true_residual']) <= 1e-12,
                    'reference norm/residual mismatch')
    if recursive:
        from src.io.physical_intermediate_profile import profile_facts
        require(summary['profile']==profile_facts(summary['profile']['identity']),'recursive resolved contract differs')
        from benchmarks.physical_recursive_checker import recompute_recursive
        rows={name:[json.loads(x) for x in hashed_file(name,digest).read_text().splitlines()]
              for name,digest in summary['recursive_evidence'].items()}
        facts['recursive']=recompute_recursive(rows['pc_applies.jsonl'],rows['recursive_inner.jsonl'],
            rows['recursive_exit_audit.jsonl'],summary)
        require(facts['recursive']['passed'],'recursive accounting/closure failed: '+str(facts['recursive']['errors']))
        facts['balanced_screen']=recompute_balanced_screen(summary['solve'],
            [json.loads(x) for x in (directory/'monitor_residuals.jsonl').read_text().splitlines()])
        require(facts['balanced_screen']['matches'],'screen differs from raw checkpoints')
        require(summary['solve']['ksp_create_count']==summary['solve']['ksp_solve_count']==
                summary['solve']['ksp_destroy_count']==1,'not one live KSP')
    if bounded:
        from src.io.physical_intermediate_profile import profile_facts

        require(summary['profile'] == profile_facts(summary['profile']['identity']),
                'bounded resolved contract differs')
        bounded_evidence = summary.get('bounded_evidence', {})
        evidence_files = bounded_evidence.get('files', bounded_evidence)
        required_names = tuple(bounded_evidence.get('required', (
            'bounded_i4.jsonl', 'pc_applies.jsonl', 'bounded_exit_audit.jsonl',
            'monitor_residuals.jsonl', 'iterations.jsonl')))

        def read_bounded_jsonl(name):
            entry = evidence_files.get(name, {})
            digest = entry.get('sha256') if isinstance(entry, dict) else entry
            require(bool(digest), f'bounded evidence binding missing: {name}')
            path = hashed_file(name, digest) if digest else directory / name
            if not path.is_file():
                return []
            return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

        rows = {name: read_bounded_jsonl(name) for name in required_names}
        # A normal or controlled bounded solve must have the full five-file
        # evidence set.  This is an evidence/schema gate, not a numerical gate.
        require(set(required_names) == {
            'bounded_i4.jsonl', 'pc_applies.jsonl', 'bounded_exit_audit.jsonl',
            'monitor_residuals.jsonl', 'iterations.jsonl'},
                'bounded evidence required-file set differs from V7 contract')
        v8_k1 = summary.get('v8_k1', {})
        control_call_start = int(v8_k1.get('control_i4_call_start', 1))
        facts['bounded_i4'] = recompute_bounded_i4(
            rows['bounded_i4.jsonl'], rows['pc_applies.jsonl'],
            rows['bounded_exit_audit.jsonl'],
            profile=summary['profile']['identity'], call_start=control_call_start,
            native_seen_before=False)
        require(facts['bounded_i4']['passed'],
                'bounded I4/PC/H6/closure accounting failed: '+
                str(facts['bounded_i4']['errors']))
        call_policy = summary.get('bounded_setup', {}).get('actual_calls_per_PC', {})
        require(call_policy.get('I4') == 2 and call_policy.get('H6') == 1,
                'bounded call-policy metadata does not state I4=2/H6=1 per PC')
        require(facts['bounded_i4']['actual_h6_applies'] ==
                facts['bounded_i4']['completed_pc_count'],
                'actual H6 smoother count is not one per completed PC')
        screen_checker = (recompute_v9_bounded_screen
                          if summary['profile']['identity'] ==
                          'balanced_h6_entity_gcrot8_new16_v9'
                          else recompute_bounded_screen)
        facts['bounded_screen'] = screen_checker(
            summary['solve'], rows['monitor_residuals.jsonl'])
        require(facts['bounded_screen']['passed'],
                'bounded V7 screen differs from raw nodes: '+
                str(facts['bounded_screen']['errors']))
        policy = summary.get('bounded_solve_policy', {})
        require(policy.get('solve_limit_seconds') == 10800,
                'bounded solve limit is not the required 10800 seconds')
        require(policy.get('outer_restart') == 32 and policy.get('outer_max_it') == 2048,
                'bounded solve policy does not bind restart32/max2048')
        setup_costs = (v8_k1.get('control_baseline') if v8_k1 else
                       summary.get('bounded_setup', {}).get('setup_costs',
                                                            summary.get('bounded_setup_costs')))
        require(isinstance(setup_costs, dict), 'bounded setup cost baseline is missing')
        facts['bounded_costs'] = recompute_bounded_costs(
            rows['bounded_i4.jsonl'], rows['pc_applies.jsonl'],
            rows['bounded_exit_audit.jsonl'], setup_costs,
            require_lifetime=True)
        require(facts['bounded_costs']['passed'],
                'bounded cumulative cost accounting failed: '+
                str(facts['bounded_costs']['errors']))
        storage = summary.get('bounded_setup', {}).get('trace_storage')
        from src.io.physical_balanced_profile import BOUNDED_PROJECTED_PROFILE
        projected_route = summary['profile']['identity'] == BOUNDED_PROJECTED_PROFILE
        route_fact = summary.get('bounded_setup', {}).get('route', {})
        if projected_route:
            require(isinstance(route_fact, dict) and
                    route_fact.get('route') == 'PROJECTED_SEQ2_16',
                    'projected profile does not bind PROJECTED_SEQ2_16 route')
            facts['bounded_projected_trace'] = recompute_projected_trace_costs(
                rows['pc_applies.jsonl'], rows['bounded_exit_audit.jsonl'], storage,
                setup_costs)
            require(facts['bounded_projected_trace']['passed'],
                    'projected full252/T accounting failed: ' +
                    str(facts['bounded_projected_trace']['errors']))
        elif isinstance(storage, dict) and storage.get('projected') is not None:
            require(False, 'non-projected bounded profile carries projected trace storage')
        iteration_rows = rows['iterations.jsonl']
        require(bool(iteration_rows), 'bounded iterations ledger is empty')
        if iteration_rows:
            values = [row.get('iteration') for row in iteration_rows]
            require(values == sorted(values), 'bounded iterations ledger is not monotone')
            require(values[-1] == summary['solve']['iterations'],
                    'bounded iterations ledger does not end at solve iteration')

        binding = summary.get('bounded_binding', {})
        require(isinstance(binding, dict) and isinstance(storage, dict),
                'bounded source/physical/mode/RHS/storage binding is missing')
        if isinstance(binding, dict) and isinstance(storage, dict):
            require(binding.get('source_sha') == summary.get('source_sha'),
                    'bounded source identity binding mismatch')
            require(binding.get('physical_model_sha256') == raw.get('physical_model_sha256'),
                    'bounded physical-model binding mismatch')
            require(binding.get('mode_sha256') == summary.get('mode_sha256'),
                    'bounded mode binding mismatch')
            require(binding.get('input_sha256') == raw.get('input_sha256'),
                    'bounded RHS input binding mismatch')
            require(binding.get('operator_identity_sha256') == raw.get('operator_identity_sha256'),
                    'bounded operator binding mismatch')
            require(binding.get('storage_sha256') == _stable_sha256(storage),
                    'bounded storage binding mismatch')
    with np.load(hashed_file(raw['filename'], raw['sha256']), allow_pickle=False) as arrays:
        rhs, action, solution = arrays['rhs'], arrays['action'], arrays['solution']
        require(rhs.shape == action.shape == solution.shape, 'incompatible raw vector shapes')
        if bounded:
            binding = summary.get('bounded_binding', {})
            rhs_sha = hashlib.sha256(rhs.tobytes()).hexdigest()
            require(binding.get('rhs_sha256') == rhs_sha,
                    'bounded RHS bytes identity differs')
            require(summary.get('rhs', {}).get('vector_sha256') == rhs_sha,
                    'bounded RHS summary hash differs')
        if recursive:
            require(hashlib.sha256(rhs.tobytes()).hexdigest()==summary['recursive_identity']['rhs_sha256'],
                    'recursive raw RHS identity differs')
        require(all(np.isfinite(v).all() for v in (rhs, action, solution)), 'nonfinite raw vectors')
        if 'recovery' in summary:
            require(hashlib.sha256(solution.tobytes()).hexdigest() == summary['final_solution_sha256'],
                    'recovery actual solution bytes hash mismatch')
            old_raw = old['residual_arrays']
            old_raw_path = (origin/old_raw['filename']).resolve()
            require(old_raw_path.is_relative_to(origin), 'recovery original raw path escapes origin')
            old_digest = hashlib.sha256(old_raw_path.read_bytes()).hexdigest()
            require(old_digest == old_raw['sha256'] == audit['artifact_sha256'][old_raw['filename']],
                    'recovery original residual arrays hash mismatch')
            with np.load(old_raw_path, allow_pickle=False) as old_arrays:
                differences = {}
                for name, value in (('rhs', rhs), ('action', action)):
                    prior = old_arrays[name]
                    difference = (float(np.linalg.norm(value-prior)/max(np.linalg.norm(prior),np.finfo(float).tiny))
                                  if value.shape == prior.shape else float('inf'))
                    differences[name] = difference
                    require(np.isfinite(difference) and difference <= 1e-10,
                            'recovery original '+name+' relative difference exceeds 1e-10')
                facts['recovery_original_array_differences'] = differences
        residual = np.linalg.norm(rhs-action)/max(np.linalg.norm(rhs), np.finfo(float).tiny)
        facts['full_explicit_true_relative_residual'] = float(residual)
        require(np.isfinite(residual) and residual <= 1e-6, f'fine residual {residual} exceeds 1e-6',
                expected=controlled and bool(np.isfinite(residual)))
        solve = summary['solve']
        require(abs(residual-solve['final_true_residual']) <= max(1e-12, .001*residual), 'raw/reported true residual mismatch')
        require(solve['reason'] >= 0 or solve['reason'] == -3, f'KSP breakdown reason {solve["reason"]}')
        for cycle in solve.get('cycles', []):
            reported = cycle['reported_final_residual']/max(np.linalg.norm(rhs), np.finfo(float).tiny)
            difference = abs(reported-cycle['explicit_true_residual'])
            require(np.isfinite(difference) and difference <= max(1e-10, .01*cycle['explicit_true_residual']),
                    f'reported/true norm mismatch at iteration {cycle["end_iteration"]}: {difference}')
    from src.io.physical_intermediate_profile import profile_facts
    resources = profile_facts(summary['profile']['identity'])['resources']
    light = summary['profile']['identity'] == 'p6smooth_p4ref_p6smooth_v1'
    stagnation = False
    if light:
        cycles = [json.loads(line) for line in (directory/'cycles.jsonl').read_text().splitlines()]
        require(bool(pc_rows) and all(row.get('positive_identity') == 'H6' for row in pc_rows),
                'LIGHT profile requires explicit H6 identity on every PC record')
        facts['light_pc_counts'] = recompute_positive_apply_counts(pc_rows, cycles)
        require(all(row['recomputed'] == row['raw_reported'] for row in facts['light_pc_counts']['cycles']),
                'raw cycle PC counts disagree with independently recomputed calls')
        require(all(row['direction_count'] == 3 and
                    sum(d['fine_action_count'] for d in row['direction_facts']) == 3
                    and row['intermediate']['factor_solve_calls'] == 1 for row in pc_rows),
                'light PC must have three original A6 MR actions and one A4 backsolve')
        require(summary['positive_setup']['positive_p3_p1_constructed'] is False,
                'unused positive coarse objects were constructed')
        if len(cycles) >= 5 and cycles[-1]['end_iteration'] >= 256:
            tail = list(zip(cycles[-5:-1], cycles[-4:]))
            stagnation = all(c['iterations'] == 32 and c['end_iteration']-c['start_iteration'] == 32
                and p['end_iteration'] == c['start_iteration'] and p['explicit_true_residual'] > 0
                and np.isfinite([p['explicit_true_residual'], c['explicit_true_residual']]).all()
                and c['explicit_true_residual']/p['explicit_true_residual'] >= .99 for p, c in tail)
        facts['stagnation_from_raw_cycles'] = bool(stagnation)
        if summary['status'] == 'STAGNATION_CONTROLLED_STOP':
            require(stagnation, 'claimed stagnation does not satisfy raw four-cycle rule')
        with np.load(directory/raw['filename'], allow_pickle=False) as arrays:
            require(hashlib.sha256(arrays['solution'].tobytes()).hexdigest() == summary['final_solution_sha256'],
                    'final solution hash mismatch before recovery')
    require(summary.get('solve_conservative_seconds', summary['solve_monotonic_seconds']) <= resources['solve_seconds'], 'solve budget exceeded', expected=summary['status']=='PERFORMANCE_CONTROLLED_STOP')
    require(summary.get('elapsed_conservative_seconds', summary['elapsed_monotonic_seconds']) <= resources['workflow_seconds'], 'workflow budget exceeded before checker', expected=summary['status']=='PERFORMANCE_CONTROLLED_STOP')
    require(summary['auxiliary_stack_released_before_recovery'] is True, 'auxiliary stack not released')
    output = summary.get('official_result')
    if output is None:
        require(False,'official outputs unavailable',expected=controlled)
    else:
        port, volume = output['port_metrics'], output['volume_metrics']
        r, t, a, av = port['R_total'], port['T_total'], port['A_balance'], volume['A_volume_total']
        facts['physics'] = dict(R=r, T=t, A=a, A_volume=av,
                               volume_energy_error=abs(r+t+av-1), absorption_difference=abs(a-av))
        require(np.isfinite([r, t, a, av]).all(), 'nonfinite R/T/A/A_volume')
        require(abs(r+t+av-1) <= 1e-5, f'independent volume energy error {abs(r+t+av-1)} exceeds 1e-5')
        require(abs(a-av) <= 1e-5, f'absorption difference {abs(a-av)} exceeds 1e-5')
        require(min(r, t, a, av) >= -1e-12, f'passivity sign error: {r,t,a,av}')
        modal = json.loads((directory / 'numerical_output/dtn_port_diffraction_orders_3d.json').read_text())
        rows = modal['orders']
        require(len(rows) == port['dtn_port_mode_count'], 'incomplete mode output')
        keys = [(row['side'], row['m'], row['n'], row['polarization']) for row in rows]
        require(len(keys) == len(set(keys)), 'duplicate mode keys')
        require(abs(sum(row['R'] for row in rows)-r) <= 1e-12, 'reflection channel sum mismatch')
        require(abs(sum(row['T'] for row in rows)-t) <= 1e-12, 'transmission channel sum mismatch')
        require(all(np.isfinite([row['R'], row['T'], row['power_ratio']]).all() and
                    min(row['R'], row['T']) >= -1e-12 for row in rows), 'nonfinite or negative channel power')
        amplitudes = json.loads((directory / 'numerical_output/dtn_auxiliary_amplitudes_3d.json').read_text())
        require(len(amplitudes) == len(rows), 'incomplete complex modal amplitudes')
        def finite_numbers(value):
            if isinstance(value, dict):
                return all(finite_numbers(v) for v in value.values())
            if isinstance(value, list):
                return all(finite_numbers(v) for v in value)
            return not isinstance(value, (int, float)) or bool(np.isfinite(value))
        require(finite_numbers(amplitudes), 'nonfinite complex modal amplitudes')
        exported = output['field_export']
        samples = Path(exported['full3d_reference_archive'])
        require(hashlib.sha256(samples.read_bytes()).hexdigest() == exported['full3d_reference_archive_sha256'],
                'E/H sample hash mismatch')
        with np.load(samples, allow_pickle=False) as arrays:
            e, h = arrays['E_V_per_m'], arrays['H_A_per_m']
            require(e.shape == h.shape and e.ndim == 4 and e.shape[-1] == 3, 'E/H sample shape mismatch')
            require(np.iscomplexobj(e) and np.iscomplexobj(h) and np.isfinite(e).all() and np.isfinite(h).all(),
                    'invalid complex E/H samples')
            require(all(np.isfinite(arrays[k]).all() for k in ('x_nm', 'y_nm', 'z_nm')), 'nonfinite sample coordinates')
        canonical = output['canonical_vector']
        hashed_file('numerical_output/' + canonical['filename'], canonical['file_sha256'])
        from benchmarks.canonical_vector_artifacts import read_canonical_packet_shard

        packets = read_canonical_packet_shard(directory / 'numerical_output' / canonical['filename'])
        require(len(packets) == canonical['packet_count'] > 0, 'canonical packet count mismatch')
        require(all(np.isfinite(value) for _, value in packets), 'nonfinite canonical coefficients')
    if balanced and output is not None:
        matched = summary.get('matched_reference', {})
        require(matched.get('status') in (('MATCHED_REFERENCE_PASS',) if recursive or bounded else
            ('MATCHED_REFERENCE_PASS','REFERENCE_AUTHORITY_LIMITED')), 'matched reference failed')
        require(summary['rss_after_release'] < summary['rss_before_release'], 'RSS did not decrease before recovery')
    independent_output_gates_passed = not errors
    classification = ('REFERENCE_ONLY_PASS' if reference_only else 'DISCRETE_SOLVER_OUTPUT_PASS') if not errors else 'NUMERICAL_OR_OUTPUT_FAIL'
    if light and errors and summary['status'] == 'STAGNATION_CONTROLLED_STOP' and stagnation:
        classification = 'STAGNATION_CONTROLLED_STOP'
    elif light and errors and summary['status'] == 'ITERATION_BUDGET_EXHAUSTED' and summary['solve']['iterations'] == 2048:
        classification = 'ITERATION_BUDGET_EXHAUSTED'
    if bounded:
        classification = bounded_output_classification(summary, errors, expected_errors)
    elif balanced:
        classification = balanced_output_classification(summary,errors,expected_errors)
    return dict(classification=classification,
                reference_authority=summary.get('matched_reference',{}).get('status','PENDING_A4_not_compared'),
                independent_output_gates_passed=independent_output_gates_passed,
                gate_failures=errors, raw_facts=facts, checker_seconds=time.monotonic()-started,
                resource_authority='separate enclosing parent verdict required')


def main() -> int:
    directory = Path(sys.argv[1]).resolve()
    try:
        result = check(directory)
    except Exception as exc:
        result = dict(classification='EVIDENCE_INCOMPLETE', reference_authority='PENDING_A4_not_compared',
                      gate_failures=[f'{type(exc).__name__}: {exc}'])
    (directory / 'checker.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return 0 if result['classification'] in ('DISCRETE_SOLVER_OUTPUT_PASS', 'REFERENCE_ONLY_PASS',
        'BALANCED_OUTPUT_PASS', 'BALANCED_OUTPUT_AUTHORITY_LIMITED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
