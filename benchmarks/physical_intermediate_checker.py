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

    raw = summary['residual_arrays']
    from src.io.physical_balanced_profile import BALANCED_PROFILES
    balanced = summary['profile']['identity'] in BALANCED_PROFILES
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
    with np.load(hashed_file(raw['filename'], raw['sha256']), allow_pickle=False) as arrays:
        rhs, action, solution = arrays['rhs'], arrays['action'], arrays['solution']
        require(rhs.shape == action.shape == solution.shape, 'incompatible raw vector shapes')
        require(all(np.isfinite(v).all() for v in (rhs, action, solution)), 'nonfinite raw vectors')
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
        require(matched.get('status') in ('MATCHED_REFERENCE_PASS','REFERENCE_AUTHORITY_LIMITED'), 'matched reference failed')
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
