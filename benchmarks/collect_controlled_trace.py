"""Frozen V76 consumers; expensive bad-field integrals are never requested."""
import gc
import json
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers import controlled_trace_scope as scope
from src.solvers.scattering_anchor import relative, save_arrays
from src.solvers.scattering_anchor_checks import checked_arrays


def verify(folder, journal, *, scope=scope):
    from src.solvers.bounded_trace_study import action_charge
    from src.solvers.tetra_coefficient_action import CoefficientFullAction
    from src.solvers.independent_tetra_study import load_boundary
    from benchmarks.collect_independent_tetra import restored
    path = scope.verification_inventory_for('VERIFY_COST')
    if path is None or journal.source_state['verification_inventory']['sha256'] != __import__('hashlib').sha256(path.read_bytes()).hexdigest():
        raise ValueError('V76 frozen route inventory')
    frozen = json.loads(path.read_text()); rows = {}
    for role, identity in frozen['states'].items():
        record = scope.stage(role)
        if (identity['array_sha256'] != record['arrays']['sha256']
                or identity['retained']['sha256'] != record['retained_returned']['sha256']):
            raise ValueError('frozen final coefficient/retained identity')
        own = folder/role; own.mkdir(exist_ok=True)
        strategy_check = None
        if record['strategy'] == 'PHYSICAL_IMPEDANCE':
            from benchmarks.collect_bounded_trace import numeric_saved_check
            producer=Path(json.loads((scope.ARTIFACT/(role+'.json')).read_text())['path']).parent
            from benchmarks.check_impedance_patch import saved_preparation_check
            prepared_check=saved_preparation_check(scope)
            factor_check=numeric_saved_check(producer,minimum_bytes=12*2**30,check_linear_PC=False)
            pc_values=checked_arrays(__import__('json').loads((producer/'live_PC_qualification.json').read_text())['arrays'])
            pc_error=relative(pc_values['second']-pc_values['alpha']*pc_values['first'],pc_values['alpha']*pc_values['first'])
            if pc_error>1e-10: raise ValueError('independent impedance PC complex linearity')
            strategy_check=dict(preparation=prepared_check,factors=factor_check,complex_linearity=pc_error,pass_gate=True)
        if record['strategy'] == 'SMR':
            from benchmarks.collect_bounded_trace import numeric_saved_check
            root = Path(scope.ARTIFACT/(role+'.json'))
            root = Path(json.loads(root.read_text())['path']).parent
            factors = numeric_saved_check(root, minimum_bytes=12*2**30, check_linear_PC=False)
            facts = []
            logs = [json.loads(line) for line in (root/'SMR_calls.jsonl').read_text().splitlines()]
            for i in (1, 2):
                p = root/f'SMR_directions_{i}.npz'
                expected_hash = frozen['SMR_witnesses'][str(i)]['sha256']
                if __import__('hashlib').sha256(p.read_bytes()).hexdigest() != expected_hash:
                    raise ValueError('SMR frozen qualification direction bytes')
                with np.load(p, allow_pickle=False) as a:
                    v, D, W, z = (a[k] for k in ('input', 'directions', 'images', 'correction'))
                norms = np.linalg.norm(W, axis=0)
                scales = np.where(norms==0, 1., norms)
                coefficients, _, rank, _ = np.linalg.lstsq(W/scales, v, rcond=1e-12)
                optimum = float(np.linalg.norm(v-W@(coefficients/scales)))
                row = logs[i-1]
                saved_weights = np.asarray(row['weights_real'])+1j*np.asarray(row['weights_imag'])
                image = W@saved_weights
                residual = float(np.linalg.norm(v-image))
                bound = min(float(np.linalg.norm(v)), float(np.linalg.norm(v-W[:,1])),
                    float(np.linalg.norm(v-W[:,1]-W[:,2])), optimum)
                operation = relative(D@saved_weights-z, np.abs(D)@np.abs(saved_weights))
                protected = (residual <= bound+1e-10*max(np.linalg.norm(v)+np.linalg.norm(image),1e-300)
                    and operation <= 1e-10 and row['operation_scaled_defect'] <= 1e-10)
                if not protected: raise ValueError('independent saved SMR feasible-direction protection')
                facts.append(dict(input_index=i, rank=int(rank), actual_saved_relative=row['actual_relative'],
                    recomputed_prediction_relative=residual/np.linalg.norm(v),
                    direction_combination_operation=operation, pass_gate=bool(protected)))
            strategy_check = dict(factors=factors, SMR=facts,
                additive_linearity_gate_applied=False, pass_gate=True)
        s, values, field = restored(record, journal)
        boundary = load_boundary(s, record['boundary_arrays'], record['mode_sha256'], 'q63')
        action = CoefficientFullAction(s, boundary, 15)
        audit, residual, rhs = action_charge('V_'+role+'_public_original',
            lambda action=action, values=values: action.audit(values['x'], values['rhs'], journal), scope=scope)
        old = checked_arrays(record['audit']['arrays'])
        operation = relative(residual-old['residual'], rhs)
        arrays = save_arrays(own/'independent_original.npz', x=values['x'],
            residual=residual, rhs=rhs, action=rhs-residual)
        qualified = scope.joint_equation_pass(record)
        row = dict(original=audit, producer_consumer_operation=operation,
            arrays=arrays, complete_coefficients_verified=True,
            equation_qualified=qualified,
            expensive_physics='NOT_RUN_BY_FAIL_FAST_POLICY', strict_pass=False)
        if strategy_check is not None: row['strategy_check'] = strategy_check
        if operation > 1e-10:
            raise ValueError('saved full original-operation mismatch')
        if record.get('physical_output_status') != 'NOT_RUN_BY_FAIL_FAST_POLICY':
            # At most one preselected best state has an expensive output.
            if frozen.get('full_output_role') != role:
                raise ValueError('unapproved repeated expensive field output')
            from benchmarks.collect_frozen_local_h import saved_original, first_normalization
            from benchmarks.collect_exact_tetra import strict_reproduction
            from benchmarks.check_independent_tetra import saved_pair
            from src.solvers.tetra_polynomial_difference import comparison
            from src.solvers.independent_tetra_fields import selected_points
            from src.solvers import assembly_tetra_scope as reference
            # Original was just independently consumed; do not replay it.
            from benchmarks.collect_independent_tetra import saved_output_check
            output_check = saved_output_check(record)
            parent = reference.stage('SOLVE')
            pair = comparison(parent, record, own/'V70_pair', journal, coefficient_first=True)
            check = saved_pair(pair, parent, record, expected_points=selected_points(record['physical']))
            second = strict_reproduction(pair)
            first = first_normalization(pair, parent, label='V70')
            cached = checked_arrays(pair['arrays'])
            selected = {name: relative(cached['selected_'+name+'_second']-cached['selected_'+name+'_first'],
                cached['selected_'+name+'_first']) for name in pair['selected']}
            reference_pass = (max(v['relative'] for v in first['fields'].values()) <= 1e-6
                and max(selected.values()) <= 1e-6
                and pair['modes']['outgoing_amplitude_at_boundary_relative'] <= 1e-6
                and pair['modes']['mode_power_max_absolute'] <= 1e-9
                and max(pair['power_differences'].values()) <= 1e-8
                and max(pair['energies']) <= 1e-5)
            if not check['published_gate_matches_recalculation']:
                raise ValueError('saved strict score mismatch')
            row.update(expensive_physics='COMPLETED', comparison=pair,
                candidate_denominator=second, reference_denominator=first,
                strict_pass=bool(qualified and audit['pass_gate'] and output_check['pass_gate']
                    and second['pass_gate'] and reference_pass))
        rows[role] = row
        write_json(own/'completed_independent_route.json', row)
        del s, values, field, boundary, action, old; gc.collect()
    result = dict(status='COMPLETED', consumer_pass=True,
        pass_gate=any(row['strict_pass'] for row in rows.values()), routes=rows,
        new_numeric_factors=0, new_complete_solves=0,
        source=journal.source_state, timings=journal.timings,
        continuum_accuracy=False, target_qualified=False, NN20=False)
    write_json(folder/'verification_scientific_result.json', result)
    return result
