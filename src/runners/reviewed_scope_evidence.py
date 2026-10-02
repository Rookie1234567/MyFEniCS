"""Validate the limited result scope without manufacturing PDE qualification."""
from __future__ import annotations

import math


def validate_scoped_terminal(mode, summary):
    errors = []
    if not isinstance(summary, dict):
        return ['scoped worker summary must be an object']
    expected = {'h6_only': 'H6_ONLY_COMPLETED',
                'pilot_16': 'PILOT_COMPLETED_NOT_SOLVER_QUALIFICATION'}
    if mode not in expected:
        return ['unknown reviewed execution scope']
    if (summary.get('status') != expected[mode]
            or summary.get('execution_mode') != mode
            or summary.get('result_classification') != mode
            or summary.get('complete_solve') is not False
            or summary.get('official_result') is not None):
        errors.append('scoped terminal classification/qualification mismatch')
    if any(summary.get(key) != 'NOT_RUN' for key in ('rta_status', 'physical_checker_status')):
        errors.append('limited scope must not claim official RTA/checker results')
    if mode == 'h6_only':
        if summary.get('p4_factor_counts') != {'symbolic_calls': 0, 'numeric_calls': 0, 'solve_calls': 0}:
            errors.append('H6-only constructed an unexpected p4 factor')
        if summary.get('h6_setup', {}).get('power_matrix_mult_count') != 20:
            errors.append('H6-only lacks the original power10 action count')
    else:
        pilot = summary.get('pilot_facts', {})
        counts = pilot.get('p4_factor_counts', {})
        if (pilot.get('planned_stop_iteration') != 16
                or not 0 < int(pilot.get('iterations', -1)) <= 16
                or pilot.get('qa_and_outer_share_one_factor') is not True
                or pilot.get('zero_start') is not True
                or counts.get('symbolic_calls') != 1 or counts.get('numeric_calls') != 1):
            errors.append('pilot scope/factor reuse contract mismatch')
        residual = float(pilot.get('final_native_A6_relative', math.nan))
        if not math.isfinite(residual) or residual < 0:
            errors.append('pilot native A6 residual is missing or nonfinite')
        if summary.get('retained_runtime', {}).get('setup_checks', {}).get('status') != 'PASS':
            errors.append('pilot lacks same-object setup QA')
    return errors
