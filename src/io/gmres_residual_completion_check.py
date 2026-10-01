"""Raw V18 evidence checks; no equation solve, no training, no operator action."""
import math
from pathlib import Path

import numpy as np

from src.io.augmented_trace_evidence_check import equation
from src.io.resumable_trace_evidence_check import field_gate, frozen_state
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def close_qualified(row):
    if 'audit' not in row:
        return False
    audit = row['audit']
    checks = (
        (row['original_closed_identity_relative'], 1e-8),
        (row['saved_vs_original_residual_full_b_relative'], 1e-8),
        (row['port_difference_operation_relative'], 1e-12),
        (audit['port_operation_relative'], 1e-12),
        (audit['recovery_relative'], 1e-10),
        (audit['schur_original_identity_operation_relative'], 1e-10),
        (audit['slave_storage_max'], 0),
    )
    return bool(row['shape'] == dict(trace=18144, port=40, z=18184)
                and all(math.isfinite(x) and 0 <= x <= limit for x, limit in checks))


def caps(ledger, budget):
    if ledger.get('active') or not ledger['closed']:
        return False
    if not (ledger['actions_upper'] <= 66000 and ledger['audits_upper'] <= 512
            and ledger['new_A_columns'] <= 6196 and ledger['image_QR'] <= 2
            and ledger['field_states'] <= 12 and ledger['reentries'] <= 3
            and ledger['cooldown_seconds'] <= 1800 and len(ledger['repairs']) <= 6):
        return False
    counted = ('actions_upper', 'audits_upper', 'new_A_columns', 'image_QR', 'field_states', 'reentries')
    if any(not isinstance(ledger[k], int) or ledger[k] < 0 for k in counted):
        return False
    if not math.isfinite(ledger['cooldown_seconds']) or ledger['cooldown_seconds'] < 0:
        return False
    if set(ledger['routes']) != {'GPOLY', 'GNN'}:
        return False
    for r in ledger['routes'].values():
        numeric = ((r['wall_seconds'], budget['uniform_route_wall_seconds'], 10000),
                   (r['G_wall_seconds'], budget['GMRES_total_ceiling_seconds'], 1800))
        if any(not all(math.isfinite(x) for x in item) or not 0 <= item[0] <= item[1] <= item[2]
               for item in numeric):
            return False
        integers = ((r['actions_upper'], 28000), (r['new_updates'], 10300),
                    (r['arnoldi_upper']['G64'], 1024), (r['arnoldi_upper']['G256'], 2048),
                    (r['reentries'], 2), (r['correction_restarts'], 1))
        if any(type(x) is not int or not 0 <= x <= limit for x, limit in integers):
            return False
    return True


def check_v18(pre, ledger, budget, verify, plan, cycle_rows):
    errors = []
    packet = pre['operator_packet']
    if file_hash(packet['path']) != packet['sha256']:
        errors.append('original_action_packet_hash')
    with np.load(packet['path'], allow_pickle=False) as stream:
        bnorm = float(np.linalg.norm(stream['b']))
        masters = array_hash(stream['masters'])
    interfaces = {name: close_qualified(item) for name, item in pre['libraries'].items()}
    if set(interfaces) != {'GPOLY', 'GNN'} or not all(interfaces.values()):
        errors.append('real_close_interface')
    for name, qualified in interfaces.items():
        if qualified != pre['libraries'][name]['qualified']:
            errors.append(name+'.F0_saved_status')
    if pre['action_counts']['S']+pre['action_counts']['SH'] > 256:
        errors.append('F0_action_cap')
    if not caps(ledger, budget):
        errors.append('campaign_budget_or_freeze')
    if not verify['reference_native_pass'] or verify['reference_audit']['independent_DOLFINx_total_native_relative'] > 1e-10:
        errors.append('independent_REF7_native')
    if verify['reference_feedback_to_solver'] or not verify['no_new_solve'] or not verify['no_new_LU']:
        errors.append('reference_data_boundary')
    reference = verify['reference_identity']
    if file_hash(reference['path']) != reference['sha256']:
        errors.append('REF7_file_hash')
    if verify['states_read'] != len(verify['rows']) or not 1 <= len(verify['rows']) <= 12:
        errors.append('field_state_inventory')
    states = {}
    image_checks = {}
    for family, im in plan['images'].items():
        bi = im['basis_identity']
        if bi['canonical_master_sha256'] != masters or bi['columns'] != 3098 or bi['complement']['take_columns'] != 1538:
            errors.append(family+'.canonical_order_or_capacity')
        for item in (bi['G0'], bi['complement'], im['U'], im['R']):
            if file_hash(item['path']) != item['sha256']:
                errors.append(family+'.basis_image_hash')
        image_checks[family] = dict(canonical_master_sha256=masters, columns=3098,
                                   matched_complement_columns=1538, new_image_rebuilt=False)
        basis = [np.load(bi['G0']['path'], mmap_mode='r'),
                 np.load(bi['complement']['path'], mmap_mode='r')[:, :1538]]
        for name, source in verify['state_sources'].items():
            if family not in name:
                continue
            try:
                state_path = Path(source['state']['path'])
                use_basis = None
                # R/V17 states contain physical v/c; G states contain only trace/port.
                with np.load(state_path, allow_pickle=False) as f:
                    if 'v' in f.files and 'c' in f.files:
                        use_basis = basis
                states[name] = frozen_state(source, bnorm, use_basis)
                if source.get('logical_iteration', 0) > 16384:
                    errors.append(name+'.absolute_logical_cap')
            except (ValueError, KeyError, OSError) as error:
                errors.append(name+'.'+str(error))
        del basis
    cycles_checked = {}
    for route, cycles in cycle_rows.items():
        algorithm, family = route.split('_', 1)
        maximum = 16 if algorithm == 'G64' else 8
        restart = 64 if algorithm == 'G64' else 256
        counted = 0
        for j, row in enumerate(cycles):
            if row['cycle'] != j+1 or not row['committed'] or row['audit_pending']:
                errors.append(route+'.noncontiguous_or_pending_cycle')
            inner = row['inner']
            if not 0 <= inner['inner_iterations'] <= restart or inner['info'] not in (0, 1):
                errors.append(route+'.Arnoldi_count_or_info')
            counted += inner['inner_iterations']
            if equation(row['audit']) != (row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'):
                errors.append(route+'.original_equation_status')
            try:
                frozen_state(row, bnorm)
            except (ValueError, KeyError, OSError) as error:
                errors.append(route+'.cycle'+str(row['cycle'])+'.'+str(error))
        if len(cycles)>maximum or counted > ledger['routes'][family]['arnoldi_upper'][algorithm]:
            errors.append(route+'.cycle_or_work_cap')
        cycles_checked[route] = dict(committed_cycles=len(cycles), actual_Arnoldi=counted,
                                    saved_original_residual_checked=True)
    qualified = {}
    for name, row in verify['rows'].items():
        if name not in states:
            errors.append(name+'.missing_raw_state')
        qualified[name] = field_gate(row, verify['reference_native_pass'])
        if qualified[name] != (row['status']=='SAME_DISCRETE_QUALIFIED'):
            errors.append(name+'.field_status')
        if equation(row['audit']) != (row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'):
            errors.append(name+'.original_equation_status')
    return dict(status='EVIDENCE_CONSISTENT' if not errors else 'RAW_MISMATCH', mismatches=errors,
        qualified_interfaces=interfaces, basis_image_checks=image_checks, raw_state_checks=states,
        cycle_checks=cycles_checked, strict_same_discrete=qualified,
        strict_qualified_states=sum(qualified.values()), no_saved_status_trusted=True,
        new_equation_actions_or_solves_in_checker=0, no_hidden_training_claimed=True)
