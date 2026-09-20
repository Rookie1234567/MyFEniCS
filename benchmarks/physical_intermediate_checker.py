"""Independent raw-output checks; never construct or invoke a PDE solver."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

_POSITIVE_APPLY_KEYS = ('s6_apply_count', 's3_apply_count')


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
    screen_seconds = solve.get('screen_seconds', 1800)
    for row in rows:
        i=row['iteration']; r=row['explicit_true_residual']
        if i and i%32==0 and (not history or history[-1][0]!=i):
            history=(history+[(i,r)])[-3:]
        if i>=128 or (screen_seconds is not None and row['solve_seconds']>=screen_seconds):
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


def _check_optional_time_limits(summary, resources, require):
    """Apply finite solve/workflow gates while allowing explicit no-deadline runs."""
    expected = summary['status'] == 'PERFORMANCE_CONTROLLED_STOP'
    solve_limit = resources['solve_seconds']
    if solve_limit is not None:
        require(summary.get('solve_conservative_seconds', summary['solve_monotonic_seconds']) <= solve_limit,
                'solve budget exceeded', expected=expected)
    workflow_limit = resources['workflow_seconds']
    if workflow_limit is not None:
        require(summary.get('elapsed_conservative_seconds', summary['elapsed_monotonic_seconds']) <= workflow_limit,
                'workflow budget exceeded before checker', expected=expected)


def balanced_output_classification(summary, errors, expected_errors=()):
    if not errors:
        return ('BALANCED_OUTPUT_AUTHORITY_LIMITED' if
            summary.get('matched_reference',{}).get('status')=='REFERENCE_AUTHORITY_LIMITED'
            else 'BALANCED_OUTPUT_PASS')
    if summary['status'] in ('SCREEN_BUDGET_NO_QUALIFIED_PROGRESS',
                            'PERFORMANCE_CONTROLLED_STOP','ITERATION_BUDGET_EXHAUSTED'):
        return summary['status'] if all(e in expected_errors for e in errors) else 'CORRECTNESS_OR_EVIDENCE_BLOCKED'
    return 'NUMERICAL_OR_OUTPUT_FAIL'


def check_retained_v20(directory: Path, summary: dict) -> dict:
    """Check the opt-in retained V20 contract without legacy profile rules."""

    started = time.monotonic()
    errors: list[str] = []
    facts: dict = {}

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    from src.io.physical_intermediate_profile import profile_facts

    identity = summary.get('profile', {}).get('identity')
    try:
        require(summary['profile'] == profile_facts(identity),
                'retained resolved profile facts differ from native contract')
    except (KeyError, ValueError):
        errors.append('retained profile identity is not resolvable')
    solve = summary.get('solve', {})
    require(solve.get('restart') == 32 and solve.get('max_it') == 2048,
            'retained outer restart/max_it contract mismatch')
    require(solve.get('zero_start') is True and solve.get('screen_enabled') is False,
            'retained outer zero-start/progress-only contract mismatch')
    require(solve.get('time_policy') == 'observe_only' and
            solve.get('time_gate_evaluated') is False,
            'retained outer time contract is not observe-only')
    require(solve.get('ksp_create_count') == solve.get('ksp_solve_count') ==
            solve.get('ksp_destroy_count') == 1, 'retained route did not use one KSP')
    final = float(solve.get('final_true_residual', np.inf))
    require(np.isfinite(final) and final <= 1e-6,
            'retained final A6 residual exceeds 1e-6')

    retained_runtime = summary.get('retained_runtime', {})
    jit = retained_runtime.get('postprocess_jit_prefactor', {})
    require(jit.get('status') == 'POSTPROCESS_JIT_PREFACTOR_PASS' and
            jit.get('compiled_before_p4_factor') is True and
            jit.get('expression_count') == 2 and
            jit.get('form_count') == 7,
            'official postprocess Form/Expression JIT was not completed before p4')
    jit_release = retained_runtime.get('postprocess_jit_release_before_factor', {})
    require(jit_release.get('status') == 'POSTPROCESS_JIT_RELEASED' and
            jit_release.get('release_context') == 'cleanup' and
            'released_after_recovery' not in jit_release,
            'postprocess JIT holders were not released at the pre-factor boundary')
    setup_checks = retained_runtime.get('setup_checks', {})
    fixed_vector_facts = setup_checks.get('mixed_original_A6_J', {}).get('fixed_vector_facts', {})
    require(set(fixed_vector_facts) == {'trace', 'port', 'mixed'},
            'retained setup trace/port/mixed algebra coverage is incomplete')
    for name, values in fixed_vector_facts.items():
        for key in ('internal_residual_relative', 'native_identity_relative',
                    'schur_port_identity_relative'):
            require(np.isfinite(values.get(key, np.inf)) and
                    float(values.get(key, np.inf)) <= 1e-10,
                    f'retained setup {name} {key} identity failed')
    require(setup_checks.get('status') == 'PASS' and
            setup_checks.get('same_runtime_object') is True and
            setup_checks.get('bal_h', {}).get('actual_logical_call') is True and
            setup_checks.get('cache_content_and_unique_bytes_unchanged') is True,
            'same-object D3 setup/A6/J/BAL_H/cache checks are incomplete')
    require(retained_runtime.get('p6_cache_unchanged_before_release') is True,
            'retained p6 cache changed before solver-stack release')

    raw = summary.get('residual_arrays', {})
    raw_path = directory / raw.get('filename', '')
    try:
        require(raw_path.is_file(), 'missing retained residual artifact')
        require(hashlib.sha256(raw_path.read_bytes()).hexdigest() == raw.get('sha256'),
                'retained residual artifact hash mismatch')
        with np.load(raw_path, allow_pickle=False) as arrays:
            rhs, action, solution = arrays['rhs'], arrays['action'], arrays['solution']
            require(rhs.shape == action.shape == solution.shape,
                    'retained residual vectors have incompatible shapes')
            require(all(np.isfinite(value).all() for value in (rhs, action, solution)),
                    'retained residual artifact contains non-finite values')
            residual = float(np.linalg.norm(rhs-action) /
                             max(np.linalg.norm(rhs), np.finfo(float).tiny))
            facts['full_explicit_true_relative_residual'] = residual
            require(np.isfinite(residual) and residual <= 1e-6,
                    'retained raw A6 residual exceeds 1e-6')
            require(abs(residual-final) <= max(1e-12, .001*max(residual, 1e-30)),
                    'retained raw/reported residual mismatch')
    except Exception as exc:
        errors.append(f'retained residual artifact read failed: {type(exc).__name__}: {exc}')

    packet = summary.get('pre_release_residual_packet', {})
    packet_path = directory / packet.get('filename', '')
    try:
        require(packet_path.is_file(), 'missing pre-release residual packet')
        require(hashlib.sha256(packet_path.read_bytes()).hexdigest() == packet.get('sha256'),
                'pre-release residual packet hash mismatch')
        with np.load(packet_path, allow_pickle=False) as arrays:
            required = ('storage_solution', 'full_rhs', 'original_a6', 'residual')
            require(all(name in arrays for name in required),
                    'pre-release residual packet is missing a required vector')
            if all(name in arrays for name in required):
                require(all(np.isfinite(arrays[name]).all() for name in required),
                        'pre-release residual packet contains non-finite values')
                require(arrays['full_rhs'].shape == arrays['original_a6'].shape ==
                        arrays['storage_solution'].shape == arrays['residual'].shape,
                        'pre-release residual packet vector shapes differ')
                require(np.allclose(arrays['residual'],
                                    arrays['full_rhs']-arrays['original_a6'],
                                    rtol=0.0, atol=0.0),
                        'pre-release residual packet is not full_rhs-original_a6')
    except Exception as exc:
        errors.append(f'pre-release residual packet read failed: {type(exc).__name__}: {exc}')

    retained_root = directory / 'retained_checkpoint_manifests'
    full_root = directory / 'full_solution_checkpoint_manifests'
    recovery_root = directory / 'retained_recovery_packets'
    retained_checkpoints = sorted(
        path.name for path in retained_root.glob('iteration_*') if path.is_dir()
    ) if retained_root.is_dir() else []
    full_checkpoints = sorted(
        path.name for path in full_root.glob('iteration_*') if path.is_dir()
    ) if full_root.is_dir() else []
    recovery_checkpoint_names = sorted(
        path.stem for path in recovery_root.glob('iteration_*.json')
    ) if recovery_root.is_dir() else []
    require(bool(retained_checkpoints), 'retained solution checkpoints are missing')
    require(retained_checkpoints == full_checkpoints == recovery_checkpoint_names,
            'retained/full/recovery checkpoint identities are not paired')
    facts['checkpoints'] = {
        'retained': retained_checkpoints,
        'full': full_checkpoints,
        'recovery_packets': recovery_checkpoint_names,
        'full_field_reused_evaluation': True,
    }

    decisions_path = directory / 'p4_decisions.jsonl'
    decisions = []
    if decisions_path.is_file():
        decisions = [json.loads(line) for line in decisions_path.read_text().splitlines() if line]
    require(bool(decisions), 'retained p4 audit ledger is missing')
    pc_path = directory / 'pc_applies.jsonl'
    pc_rows = []
    if pc_path.is_file():
        pc_rows = [json.loads(line) for line in pc_path.read_text().splitlines() if line]
    setup_pc_rows = [row for row in pc_rows if row.get('scope') == 'setup']
    outer_pc_rows = [row for row in pc_rows if row.get('scope') == 'outer_pc']
    require(len(setup_pc_rows) == 1,
            'retained setup BAL_H/PC evidence is not exactly one record')
    if setup_pc_rows:
        setup_pc = setup_pc_rows[0]
        require(setup_pc.get('p4_logical_apply_delta') == 2,
                'retained setup BAL_H did not make two logical p4 calls')
        setup_delta = setup_pc.get('p4_physical_factor_delta', {})
        require(setup_delta.get('symbolic_calls') == 0 and
                setup_delta.get('numeric_calls') == 0 and
                'solve_calls' in setup_delta,
                'retained setup BAL_H factor accounting is invalid')
    for index, pc_row in enumerate(outer_pc_rows, start=1):
        require(pc_row.get('p4_logical_apply_delta') == 2,
                f'retained outer PC {index} did not make two logical p4 calls')
        delta = pc_row.get('p4_physical_factor_delta', {})
        require(delta.get('symbolic_calls') == 0 and
                delta.get('numeric_calls') == 0 and
                'solve_calls' in delta,
                f'retained outer PC {index} factor/refinement accounting is invalid')
    require(len(decisions) == (2 + 2 * len(outer_pc_rows)),
            'retained p4 decisions do not match setup plus per-PC logical calls')
    def decisions_for_interval(before, after):
        return [
            decision for decision in decisions
            if int(before) < int(decision.get('logical_apply', 0)) <= int(after)
        ]

    for label, pc_row in [
        ('setup', setup_pc_rows[0] if setup_pc_rows else None),
        *[(f'outer PC {index}', row) for index, row in enumerate(outer_pc_rows, start=1)],
    ]:
        if pc_row is None:
            continue
        before = int(pc_row.get('p4_logical_apply_before', -1))
        after = int(pc_row.get('p4_logical_apply_after', -1))
        interval = decisions_for_interval(before, after)
        expected_solves = sum(len(decision.get('rows', [])) for decision in interval)
        delta = pc_row.get('p4_physical_factor_delta', {})
        require(int(delta.get('solve_calls', -1)) == expected_solves,
                f'retained {label} physical MatSolve delta disagrees with p4 rows')
        require(int(delta.get('symbolic_calls', -1)) == 0 and
                int(delta.get('numeric_calls', -1)) == 0,
                f'retained {label} refactored an already symbolic/numeric factor')
    logical_numbers = []
    physical_solves = 0
    max_refinements = 0
    for decision in decisions:
        rows = decision.get('rows', [])
        logical_numbers.append(int(decision.get('logical_apply', 0)))
        max_refinements = max(max_refinements, max(0, len(rows)-1))
        counts = decision.get('factor_counts', {})
        physical_solves = max(physical_solves, int(counts.get('solve_calls', 0)))
        require(decision.get('logical_apply_delta') == 1,
                'retained p4 audit is not one logical call per BAL_H coarse solve')
        require(len(rows) <= 3, 'retained p4 exceeded two refinements')
        if not rows:
            require(decision.get('status') == 'P4_ZERO_RHS_DIRECT_ZERO' and
                    float(decision.get('rhs_norm', np.nan)) == 0.0,
                    'empty p4 audit rows are not a proven zero-RHS return')
        else:
            for row in rows:
                require(row.get('port_closure', {}).get('status') == 'PASS',
                        'retained p4 port closure failed')
                relative = row.get('relative_residual', np.inf)
                require(np.isfinite(relative),
                        'retained p4 intermediate residual is non-finite')
            final_row = rows[-1]
            require(float(final_row.get('relative_residual', np.inf)) <= 1e-10,
                    'retained p4 final A4 residual exceeds 1e-10')
    if logical_numbers:
        require(logical_numbers == list(range(1, len(logical_numbers)+1)),
                'retained p4 logical audit numbers are not contiguous')
    facts['p4'] = {
        'logical_apply_count': len(decisions),
        'physical_solve_count_at_least': physical_solves,
        'max_refinements': max_refinements,
    }
    outer_counts = summary.get('outer_pc_counts', {})
    require(int(outer_counts.get('p4_logical_apply_calls', -1)) == len(decisions),
            'retained p4 logical count disagrees with outer PC audit')
    require(int(outer_counts.get('retained_bal_h_bridge_apply_count', 0)) >= 0,
            'retained BAL_H bridge count is missing')
    factor = summary.get('retained_runtime', {}).get('p4_factor', {})
    require(factor.get('symbolic', {}).get('symbolic_calls') == 1,
            'retained p4 symbolic count is not one')
    require(factor.get('numeric', {}).get('numeric_calls') == 1,
            'retained p4 numeric count is not one')
    require(summary.get('retained_runtime', {}).get(
        'p4_inverse_retain_through_postprocess_v18') is False,
        'retained p4 inverse was not configured for pre-postprocess release')

    require(summary.get('auxiliary_stack_released_before_recovery') is True,
            'retained auxiliary stack was not released before recovery')
    for name in ('pre_release_a6', 'post_release_a6'):
        value = summary.get(name, {})
        require(value.get('finite') is True and value.get('relative', np.inf) <= 1e-6,
                f'{name} gate is missing or failed')

    output = summary.get('official_result')
    if output is None:
        errors.append('retained official outputs are unavailable')
    else:
        port = output.get('port_metrics', {})
        volume = output.get('volume_metrics', {})
        values = [port.get('R_total'), port.get('T_total'),
                  port.get('A_balance'), volume.get('A_volume_total')]
        require(all(value is not None and np.isfinite(value) for value in values),
                'retained official R/T/A output is non-finite')
        if all(value is not None and np.isfinite(value) for value in values):
            r, t, a, av = values
            require(abs(r+t+av-1.0) <= 1e-5, 'retained energy balance exceeds 1e-5')
            require(abs(a-av) <= 1e-5, 'retained volume absorption mismatch exceeds 1e-5')
            require(port.get('dtn_port_mode_count') == 600,
                    'retained 5 nm output does not contain 600 DtN modes')
        numerical = directory / 'numerical_output'
        modal_path = numerical / 'dtn_port_diffraction_orders_3d.json'
        amplitude_path = numerical / 'dtn_auxiliary_amplitudes_3d.json'
        try:
            modal = json.loads(modal_path.read_text())
            rows = modal['orders']
            keys = [(row['side'], row['m'], row['n'], row['polarization']) for row in rows]
            require(len(rows) == 600 and len(keys) == len(set(keys)),
                    'retained modal output is not 600 unique channels')
            require(abs(sum(row['R'] for row in rows)-port['R_total']) <= 1e-12 and
                    abs(sum(row['T'] for row in rows)-port['T_total']) <= 1e-12,
                    'retained modal R/T sums disagree with official totals')
            require(all(np.isfinite([row['R'], row['T'], row['power_ratio']]).all() and
                        min(row['R'], row['T']) >= -1e-12 for row in rows),
                    'retained modal powers are non-finite or negative')
            amplitudes = json.loads(amplitude_path.read_text())
            require(len(amplitudes) == len(rows),
                    'retained auxiliary amplitude count differs from modal count')
            def finite_numbers(value):
                if isinstance(value, dict):
                    return all(finite_numbers(item) for item in value.values())
                if isinstance(value, list):
                    return all(finite_numbers(item) for item in value)
                return not isinstance(value, (int, float)) or bool(np.isfinite(value))
            require(finite_numbers(amplitudes), 'retained modal amplitudes are non-finite')
        except Exception as exc:
            errors.append(f'retained modal output check failed: {type(exc).__name__}: {exc}')
        try:
            exported = output['field_export']
            samples = Path(exported['full3d_reference_archive'])
            require(hashlib.sha256(samples.read_bytes()).hexdigest() ==
                    exported['full3d_reference_archive_sha256'],
                    'retained E/H archive hash mismatch')
            with np.load(samples, allow_pickle=False) as arrays:
                e, h = arrays['E_V_per_m'], arrays['H_A_per_m']
                require(e.shape == h.shape and e.ndim == 4 and e.shape[-1] == 3 and
                        np.iscomplexobj(e) and np.iscomplexobj(h) and
                        np.isfinite(e).all() and np.isfinite(h).all(),
                        'retained E/H archive is incomplete or non-finite')
            canonical = output['canonical_vector']
            canonical_path = numerical / canonical['filename']
            require(hashlib.sha256(canonical_path.read_bytes()).hexdigest() ==
                    canonical['file_sha256'], 'retained canonical artifact hash mismatch')
            from benchmarks.canonical_vector_artifacts import read_canonical_packet_shard
            packets = read_canonical_packet_shard(canonical_path)
            require(len(packets) == canonical['packet_count'] > 0 and
                    all(np.isfinite(value) for _, value in packets),
                    'retained canonical artifact is incomplete or non-finite')
        except Exception as exc:
            errors.append(f'retained E/H/canonical check failed: {type(exc).__name__}: {exc}')

    matched_facts = summary.get('matched_reference', {})
    matched = matched_facts.get('status')
    require(matched == 'MATCHED_REFERENCE_PASS',
            'retained 5 nm full reference comparison did not pass')
    require(matched_facts.get('full_field', {}).get('status') == 'FULL_FIELD_PASS',
            'retained full-field comparison is missing or failed')
    classification = ('BALANCED_OUTPUT_PASS' if not errors and
                      matched == 'MATCHED_REFERENCE_PASS' else
                      'NUMERICAL_OR_OUTPUT_FAIL')
    return {
        'classification': classification,
        'reference_authority': matched or 'PENDING_A4_not_compared',
        'independent_output_gates_passed': not errors,
        'gate_failures': errors,
        'raw_facts': facts,
        'checker_seconds': time.monotonic()-started,
        'resource_authority': 'separate enclosing parent verdict required',
    }


def check(directory: Path) -> dict:
    started = time.monotonic()
    summary = json.loads((directory / 'physical_intermediate_summary.json').read_text())
    if summary.get('profile', {}).get('identity') == 'dual_condensed_balh_native_5nm_v3':
        return check_retained_v20(directory, summary)
    errors, facts, expected_errors = [], {}, []
    controlled = summary['status'] in ('SCREEN_BUDGET_NO_QUALIFIED_PROGRESS',
        'PERFORMANCE_CONTROLLED_STOP','ITERATION_BUDGET_EXHAUSTED')

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
    from src.io.physical_balanced_profile import BALANCED_ROUTES
    from src.io.physical_recursive_profile import RECURSIVE_PROFILES
    recursive = summary['profile']['identity'] in RECURSIVE_PROFILES
    balanced = recursive or summary['profile']['identity'] in BALANCED_ROUTES
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
    with np.load(hashed_file(raw['filename'], raw['sha256']), allow_pickle=False) as arrays:
        rhs, action, solution = arrays['rhs'], arrays['action'], arrays['solution']
        require(rhs.shape == action.shape == solution.shape, 'incompatible raw vector shapes')
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
    _check_optional_time_limits(summary, resources, require)
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
        require(matched.get('status') in (('MATCHED_REFERENCE_PASS',) if recursive else
            ('MATCHED_REFERENCE_PASS','REFERENCE_AUTHORITY_LIMITED')), 'matched reference failed')
        if not summary['profile'].get('native_capacity'):
            require(summary['rss_after_release'] < summary['rss_before_release'], 'RSS did not decrease before recovery')
    independent_output_gates_passed = not errors
    classification = ('REFERENCE_ONLY_PASS' if reference_only else 'DISCRETE_SOLVER_OUTPUT_PASS') if not errors else 'NUMERICAL_OR_OUTPUT_FAIL'
    if light and errors and summary['status'] == 'STAGNATION_CONTROLLED_STOP' and stagnation:
        classification = 'STAGNATION_CONTROLLED_STOP'
    elif light and errors and summary['status'] == 'ITERATION_BUDGET_EXHAUSTED' and summary['solve']['iterations'] == 2048:
        classification = 'ITERATION_BUDGET_EXHAUSTED'
    if balanced:
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
    return 0 if result['classification'] in ('DISCRETE_SOLVER_OUTPUT_PASS', 'REFERENCE_ONLY_PASS', 'BALANCED_OUTPUT_PASS', 'BALANCED_OUTPUT_AUTHORITY_LIMITED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
