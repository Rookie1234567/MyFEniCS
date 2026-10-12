"""Small-record checks only; no PDE, mesh, factor, or field arrays."""

import json

import pytest

from benchmarks.physical_intermediate_checker import check_retained_v20


def _evidence(directory):
    scope = 'n0_filtered_dtn_not_full_dtn'
    final = {
        'iteration': 16, 'physical_residual_key': 'A6_n0_relative',
        'operator_scope': scope, 'A6_n0_relative': 0.4,
        'physical_residual_pass': False,
    }
    factor = {'symbolic_calls': 1, 'numeric_calls': 1, 'solve_calls': 34}
    summary = {
        'profile': {'identity': 'dual_condensed_balh_native_0p7nm_n0_p3_pilot16_v6'},
        'experiment': 'N0_PORT_FILTER_TARGET_PILOT', 'operator_scope': scope,
        'status': 'PILOT_COMPLETED_NOT_SOLVER_QUALIFICATION',
        'execution_mode': 'pilot_16', 'complete_solve': False,
        'official_result': None, 'rta_status': 'NOT_RUN',
        'operator_selection': {
            'schema': 'task39extra.dtn-mode-selection.v1',
            'policy': 'n_equals_zero_both_ports_both_polarizations',
            'parent_mode_count': 32060,
            'parent_mode_sha256':
                '7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb',
            'active_mode_count': 572,
            'active_mode_sha256':
                '946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b',
            'selected_parent_indices_sha256':
                'f423721c90fe6259f9d9ea9f514aa9c5f1abdd7723ffd49fac64c79af03c56b2',
            'side_polarization_counts':
                {'bottom_p': 143, 'bottom_s': 143, 'top_p': 143, 'top_s': 143},
            'm_range_in_each_side_polarization': [-142, 0],
            'quadrature_inventory': 'full_parent_modes', 'operator_scope': scope,
        },
        'solve': {
            'physical_residual_key': 'A6_n0_relative', 'operator_scope': scope,
            'restart': 32, 'max_it': 2048, 'planned_stop_iteration': 16,
            'zero_start': True, 'screen_enabled': False, 'time_policy': 'observe_only',
            'time_gate_evaluated': False, 'ksp_create_count': 1,
            'ksp_solve_count': 1, 'ksp_destroy_count': 1,
            'iterations': 16, 'final_evaluation': final, 'final_true_residual': 0.4,
            'p4_factor_counts': factor,
        },
        'pilot_facts': {'qa_and_outer_share_one_factor': True, 'A6_n0_relative': 0.4},
        'full_dtn_endpoint_check': {'status': 'FULL_DTN_NOT_VERIFIED'},
    }
    decisions = [{
        'logical_apply': 1, 'coarse_degree': 3, 'coarse_operator': 'A3',
        'factor_counts': factor,
        'rows': [{'relative_residual': 1e-12, 'port_closure': {'status': 'PASS'}}],
    }]
    (directory / 'monitor_residuals.jsonl').write_text(json.dumps(final) + '\n')
    (directory / 'p4_decisions.jsonl').write_text(json.dumps(decisions[0]) + '\n')
    return summary, decisions


def test_n0_pilot_nonconvergence_is_evidence_not_solver_qualification(tmp_path):
    summary, _ = _evidence(tmp_path)
    result = check_retained_v20(tmp_path, summary)
    assert result['gate_failures'] == []
    assert result['pilot_evidence_complete'] is True
    assert result['independent_output_gates_passed'] is False
    assert result['full_dtn_qualified'] is False
    assert result['raw_facts']['A6_n0_relative'] == 0.4


@pytest.mark.parametrize('field,value', [
    ('active_mode_count', 286), ('active_mode_sha256', 'a' * 64),
    ('selected_parent_indices_sha256', 'b' * 64),
    ('quadrature_inventory', 'active_modes'),
])
def test_n0_checker_rejects_wrong_selection_and_quadrature(tmp_path, field, value):
    summary, _ = _evidence(tmp_path)
    summary['operator_selection'][field] = value
    result = check_retained_v20(tmp_path, summary)
    assert f'N0 selection mismatch: {field}' in result['gate_failures']


def test_n0_checker_rejects_full_alias_and_fabricated_missing_channel_result(tmp_path):
    summary, _ = _evidence(tmp_path)
    summary['solve']['final_evaluation']['original_A6_relative'] = 0.4
    summary['full_dtn_endpoint_check']['A6_full_relative'] = 0.0
    result = check_retained_v20(tmp_path, summary)
    assert 'N0 final uses the full-DtN alias' in result['gate_failures']
    assert 'Unverified full-DtN residual must not be fabricated' in result['gate_failures']


def test_n0_checker_rejects_extra_factor_and_failed_a3_return(tmp_path):
    summary, decisions = _evidence(tmp_path)
    decisions[0]['rows'][-1]['relative_residual'] = 1.01e-10
    decisions[0]['factor_counts']['numeric_calls'] = 2
    (tmp_path / 'p4_decisions.jsonl').write_text(json.dumps(decisions[0]) + '\n')
    result = check_retained_v20(tmp_path, summary)
    assert 'N0 A3 final return residual exceeds 1e-10' in result['gate_failures']
    assert 'N0 A3 decision refactored or lacks factor identity' in result['gate_failures']


def test_n0_checker_rejects_unauthorized_iteration_extension(tmp_path):
    summary, _ = _evidence(tmp_path)
    summary['solve']['iterations'] = 17
    result = check_retained_v20(tmp_path, summary)
    assert 'N0 pilot exceeded its iteration budget or has no iteration count' in result['gate_failures']


def test_n0_checker_never_qualifies_full_problem_even_with_small_n0_residual(tmp_path):
    summary, _ = _evidence(tmp_path)
    summary['solve']['iterations'] = 8
    summary['solve']['status'] = 'TRUE_RESIDUAL_PASS'
    summary['solve']['final_true_residual'] = 1e-8
    final = summary['solve']['final_evaluation']
    final.update(iteration=8, A6_n0_relative=1e-8, physical_residual_pass=True)
    (tmp_path / 'monitor_residuals.jsonl').write_text(json.dumps(final) + '\n')
    result = check_retained_v20(tmp_path, summary)
    assert result['gate_failures'] == []
    assert not result['full_dtn_qualified']
    assert not result['official_rta_qualified']
