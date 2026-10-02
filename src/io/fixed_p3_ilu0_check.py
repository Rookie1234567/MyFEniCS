"""Read-only fixed ILU evidence checks; no operator, factor or new solve."""
import math
from pathlib import Path

import numpy as np

from src.io.augmented_trace_evidence_check import equation
from src.io.post_lsqr_polish_check import state_check
from src.io.resumable_trace_evidence_check import field_gate
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def bounded(value, limit):
    return isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= limit


def capacity_gate(row):
    return all(bounded(row.get(key), limit) for key, limit in (
        ('contribution_nnz_upper', 20000000), ('csr_bytes_upper', 512*2**20),
        ('factor_explicit_payload_upper_bytes', 2**30),
        ('simultaneous_planning_upper_bytes', 8*2**30)))


def pc_gate(row):
    effective = row['effective']; spec = effective['specification']
    expected = dict(type='ilu', levels=0, ordering='natural', shift='NONE',
                    communicator='COMM_SELF', matrix='seqaij', out_of_place=True,
                    drop=None, diagonal_rescue=False)
    return bool(spec == expected and effective['effective_type'] == 'ilu'
        and effective['effective_matrix_type'] == 'seqaij'
        and effective['scalar'] == 'complex128' and effective['integer'] == 'int64'
        and effective['effective_Levels'] == 0 and effective['effective_ShiftType'] == 0
        and not effective['external_options_applied']
        and bounded(row['repeat']['operation_relative'], 1e-10)
        and bounded(row['complex_linearity']['operation_relative'], 1e-10)
        and all(bounded(x['operation_relative'], 1e-10) for x in row.get('cross_process_pairs', [])))


def port_gate(row):
    return bool(bounded(row['cond2'], 1e10) and bounded(row['solve_operation_relative'], 1e-12)
                and row['W_payload_bytes'] == 18144*40*16 and row['H_is_Hhat']
                and not row['F_is_C_adjoint_assumed'])


def right_state(row, arrays, previous_trace):
    """Check the saved physical update, rather than treating right y as trace."""
    ident = row['identity']
    if ident['parent_trace_sha256'] != array_hash(previous_trace):
        raise ValueError('previous physical trace hash')
    if ident['pc_kind'] == 'IDENTITY':
        return
    for key in ('y', 'By'):
        if key not in arrays or arrays[key].shape != previous_trace.shape or not np.isfinite(arrays[key]).all():
            raise ValueError('complete finite right variable inventory')
        if array_hash(arrays[key]) != row['state'].get(key+'_sha256'):
            raise ValueError('right variable array hash')
    if row.get('right_variable_is_trace') is not False:
        raise ValueError('right y incorrectly labelled physical trace')
    if not np.array_equal(arrays['trace'], previous_trace+arrays['By']):
        raise ValueError('trace must equal previous trace plus By')


def campaign_gate(ledger):
    limits = dict(actions=35000, audits=120, B0=35000, F=35000,
                  K_assemblies=2, factor_setups=5, field_states=12)
    if ledger.get('active') or not ledger['closed'] or set(ledger['charged']) != set(limits):
        return False
    if any(type(ledger['charged'][k]) is not int or not bounded(ledger['charged'][k], n)
           for k, n in limits.items()):
        return False
    if not bounded(ledger['reentries'], 2) or not bounded(ledger['cooldown_seconds'], 1200) or len(ledger['repairs']) > 4:
        return False
    wall_caps = dict(SETUP=1800, N=1200, P0=1200, P40=1200, T=1200, C=1800)
    return all(bounded(row['wall_seconds'], wall_caps.get(name, 12600))
               for name, row in ledger['routes'].items())


def check_fixed_ilu(setup, routes, verify, ledger, plan, repeats):
    errors = []; raw_states = {}; cycles = {}; source = setup['source_sha']
    packet = setup['operator_packet']
    if file_hash(packet['path']) != packet['sha256'] or packet['sha256'] != plan['action_sha256']:
        errors.append('original action identity')
    with np.load(packet['path'], allow_pickle=False) as stream:
        bnorm = float(np.linalg.norm(stream['b'])); master = array_hash(stream['masters'])
        rhs_hash = array_hash(stream['b'])
    if not campaign_gate(ledger): errors.append('campaign limits/freeze')
    if not capacity_gate(setup['capacity']) or not setup['capacity']['qualified']:
        errors.append('preallocation capacity')
    pairs = setup['K_action_pairs']
    operator_ok = all(all(bounded(row[k]['operation_relative'], 1e-10) for k in ('K', 'KH', 'F'))
                      and bounded(row['closed_difference_full_b'], 1e-8) for row in pairs)
    operator_ok = operator_ok and all(bounded(setup[k]['operation_relative'], 1e-10) for k in ('C_pair', 'H_pair'))
    if not operator_ok or not setup['operator_qualified']: errors.append('K/original pair')
    if not pc_gate(setup['PC']) or not setup['PC_qualified']: errors.append('fixed PC interface')
    kitem = setup['K']; receipt = kitem['assembly']
    if file_hash(kitem['path']) != kitem['sha256']: errors.append('K file identity')
    with np.load(kitem['path'], allow_pickle=False) as stream:
        for key in ('data', 'indices', 'indptr'):
            if array_hash(stream[key]) != receipt[key+'_sha256']: errors.append('K '+key+' identity')
        if len(stream['data']) != receipt['nnz'] or sum(stream[k].nbytes for k in ('data', 'indices', 'indptr')) != receipt['csr_payload_bytes']:
            errors.append('K payload/pattern')
    for name, route in routes.items():
        if route['source_sha'] != source or route['reference_read'] or route['Q_U_R_loaded'] or route['hidden_training']:
            errors.append(name+' source/data boundary')
        if route['global_p4_factor_constructed'] or route['hidden_fallback']:
            errors.append(name+' forbidden factor/fallback')
        parent = plan['initial_states']['GPOLY']
        try:
            _, previous = state_check(parent, bnorm)
            if route['parent']['state']['sha256'] != parent['state']['sha256']:
                raise ValueError('independent fixed warm parent')
            if name != 'N' and not pc_gate(repeats[name]): raise ValueError('cross-process fixed factor pair')
            if name == 'P40' and not port_gate(route['port_correction']): raise ValueError('unsafe port correction')
            for index, row in enumerate(route['cycles']):
                raw, arrays = state_check(row, bnorm)
                # The older general reader intentionally excludes right variables.
                if name != 'N':
                    with np.load(row['state']['path'], allow_pickle=False) as stream:
                        arrays.update({k:np.array(stream[k]) for k in ('y', 'By')})
                right_state(row, arrays, previous['trace'])
                ident = row['identity']; inner = row['inner']
                if row['cycle'] != index+1 or not row['committed'] or row['audit_pending']:
                    raise ValueError('cycle continuity/commit')
                if row['source_sha'] != source or row['reference_arrays_read']:
                    raise ValueError('cycle source/reference boundary')
                if ident['master_sha256'] != master or ident['rhs_sha256'] != rhs_hash or ident['action_sha256'] != packet['sha256']:
                    raise ValueError('canonical/RHS/action identity')
                if ident['physical_sha256'] != plan['physical_sha256']:
                    raise ValueError('physical identity')
                if not bounded(row['original_residual_identity_relative'], 1e-8): raise ValueError('original closed identity')
                if equation(row['audit']) != (row['original_equation_gate']['status'] == 'ORIGINAL_EQUATION_PASS'):
                    raise ValueError('saved original equation status')
                if (inner['restart'] != 256 or inner['maxiter'] != 1 or inner['callback_type'] != 'pr_norm'
                        or inner['preconditioner'] is not None or inner['relative_tolerance'] != 0
                        or inner['absolute_tolerance'] != 1e-8*bnorm
                        or not bounded(inner['inner_iterations'], 256)):
                    raise ValueError('fixed GMRES contract/count')
                raw_states[name+'-'+str(index+1)] = raw; previous = arrays
            cycles[name] = dict(cycles=len(route['cycles']), Arnoldi=sum(x['inner']['inner_iterations'] for x in route['cycles']))
            if len(route['cycles']) > (4 if name == 'N' else 16): raise ValueError('route cycle cap')
            ratio = route['final']['audit']['schur_relative']/route['start']['audit']['schur_relative']
            if name != 'N' and ratio > .9 and len(route['cycles']) != 4:
                raise ValueError('fixed four-cycle progress rule')
        except (ValueError, KeyError, OSError) as error: errors.append(name+': '+str(error))
    reference_ok = (bounded(verify['reference_audit']['independent_DOLFINx_total_native_relative'], 1e-10)
                    and equation(verify['reference_audit']))
    if not reference_ok or not verify['reference_native_pass']: errors.append('reference native')
    if verify['reference_feedback_to_solver'] or not verify['no_new_solve'] or not verify['no_new_LU'] or not verify['queue_frozen']:
        errors.append('reference barrier')
    if file_hash(verify['reference_identity']['path']) != verify['reference_identity']['sha256']:
        errors.append('reference identity')
    if verify['states_read'] != len(verify['rows']) or not 1 <= verify['states_read'] <= 12:
        errors.append('field inventory')
    qualified = {}; equations = {}
    for name, row in verify['rows'].items():
        try: raw_states[name], _ = state_check(verify['state_sources'][name], bnorm)
        except (ValueError, KeyError, OSError) as error: errors.append(name+': '+str(error))
        qualified[name] = field_gate(row, reference_ok); equations[name] = equation(row['audit'])
        if qualified[name] != (row['status'] == 'SAME_DISCRETE_QUALIFIED'): errors.append(name+' field status')
        if equations[name] != (row['original_equation_gate']['status'] == 'ORIGINAL_EQUATION_PASS'): errors.append(name+' equation status')
    return dict(status='EVIDENCE_CONSISTENT' if not errors else 'RAW_MISMATCH', mismatches=errors,
                operator_qualified=operator_ok, PC_qualified=pc_gate(setup['PC']),
                raw_state_checks=raw_states, cycle_checks=cycles, original_equation=equations,
                strict_same_discrete=qualified, strict_qualified_states=sum(qualified.values()),
                original_actions_factors_or_solves_in_checker=0, no_saved_status_trusted=True,
                GLOBAL_P3_INCOMPLETE_FACTOR_PRESENT=True, global_p4_factor_present=False,
                hidden_training_increment=False)
