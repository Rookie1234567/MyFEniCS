from pathlib import Path
from time import perf_counter

import numpy as np
import pytest
from petsc4py import PETSc

from src.io import load_and_resolve
from src.io.native_capacity_profile import native_profile_facts
from src.runners.reviewed_scope_evidence import validate_scoped_terminal
from src.solvers.physical_retained_fgmres import run_retained_fgmres

ROOT = Path(__file__).resolve().parents[2]


def test_explicit_profiles_preserve_physical_identity_and_limited_scope():
    for name, base, mode in (
        ('5nm_full', '5nm_p6h4_q4', 'full_solve'),
        ('2nm_h6_only', '2nm_p6h1p5_q4', 'h6_only'),
        ('2nm_pilot16', '2nm_p6h1p5_q4', 'pilot_16'),
    ):
        old = load_and_resolve(ROOT/f'input/task39extra_para_workstation_capacity/v5_node1_{base}.dat')
        new = load_and_resolve(ROOT/f'input/task39extra_para_workstation_capacity/v6_{name}.dat')
        assert new.physical_model_sha256 == old.physical_model_sha256
        assert new.input_sha256 != old.input_sha256
        facts = native_profile_facts(new.solver['preconditioner'])
        assert facts['execution_mode'] == mode
        assert facts['resources']['rss_hard_limit_bytes'] == 1_300_000_000_000
        assert facts['resources']['pss_sampling_policy'] == 'disabled_by_profile'
        assert facts['resources']['swap_policy'] == 'observe_only'
        assert facts['outer']['restart'] == 32
        assert facts['outer']['max_iterations'] == 2048


def test_real_ksp_pilot_stops_at_16_and_saves_without_qualification():
    rhs = PETSc.Vec().createSeq(64)
    rhs.set(1.0)
    diagonal = np.geomspace(1.0, 1e7, 64)
    records, saved = [], []
    started = perf_counter()
    result = None

    def action(vector):
        output = vector.duplicate()
        output.array[:] = diagonal*vector.array
        return output

    def evaluate(_vector, residual):
        return {'original_A6_relative': float(residual.norm()/rhs.norm()),
            'port_closure_relative': 0.0, 'internal_residual_relative': 0.0,
            'native_identity_relative': 0.0, 'schur_port_identity_relative': 0.0}

    try:
        result = run_retained_fgmres(rhs, action, lambda vector: vector.copy(),
            evaluate=evaluate, checkpoint=lambda *args: None,
            append=lambda name, row: records.append((name, row)),
            seconds=lambda: perf_counter()-started,
            save_retained=lambda iteration, _vec: saved.append(iteration),
            planned_stop_iteration=16)
        assert result['iterations'] == 16
        assert result['status'] == 'PILOT_COMPLETED_NOT_SOLVER_QUALIFICATION'
        assert result['final_true_residual'] > 1e-6
        assert 16 in saved
        assert result['restart'] == 32 and result['max_it'] == 2048
        assert {r['iteration'] for n, r in records if n == 'monitor_residuals.jsonl'} == {0, 8, 16}
    finally:
        if result:
            result['final_solution'].destroy()
        rhs.destroy()


@pytest.mark.parametrize('mutation', ['factor', 'rta', 'qualification', 'power'])
def test_h6_only_scope_rejects_false_terminal_claims(mutation):
    summary = {'status': 'H6_ONLY_COMPLETED', 'execution_mode': 'h6_only',
        'result_classification': 'h6_only', 'complete_solve': False, 'official_result': None,
        'rta_status': 'NOT_RUN', 'physical_checker_status': 'NOT_RUN',
        'p4_factor_counts': {'symbolic_calls': 0, 'numeric_calls': 0, 'solve_calls': 0},
        'h6_setup': {'power_matrix_mult_count': 20}}
    assert not validate_scoped_terminal('h6_only', summary)
    if mutation == 'factor':
        summary['p4_factor_counts']['numeric_calls'] = 1
    elif mutation == 'rta':
        summary['rta_status'] = 'PASS'
    elif mutation == 'qualification':
        summary['complete_solve'] = True
    else:
        summary['h6_setup']['power_matrix_mult_count'] = 10
    assert validate_scoped_terminal('h6_only', summary)
