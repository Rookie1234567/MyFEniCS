"""Read-only V19 evidence: numbers and stored vectors, no new solve/action."""
import math
from pathlib import Path
import numpy as np
from src.io.augmented_trace_evidence_check import equation
from src.io.gmres_residual_completion_check import close_qualified
from src.io.resumable_trace_evidence_check import field_gate
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def bounded(x, limit):
    return isinstance(x, (int, float)) and math.isfinite(x) and 0 <= x <= limit


def caps(ledger, budget):
    if ledger.get('active') or not ledger['closed']:
        return False
    limits = dict(actions_upper=80000, audits_upper=300, new_A_columns=0,
                  image_QR=0, field_states=12, reentries=3)
    if any(type(ledger[k]) is not int or not bounded(ledger[k], n) for k, n in limits.items()):
        return False
    if not bounded(ledger['cooldown_seconds'], 1800) or len(ledger['repairs']) > 4:
        return False
    names = {a+'_'+f for a in ('P', 'L') for f in ('GPOLY', 'GNN')}
    if set(ledger['routes']) != names | {'GPOLY', 'GNN'}:
        return False
    if not bounded(budget['uniform_route_wall_seconds'], 2700):
        return False
    for name in names:
        row = ledger['routes'][name]
        if not bounded(row['wall_seconds'], budget['uniform_route_wall_seconds']):
            return False
        for key, limit in (('actions_upper', 19500), ('new_updates', 64)):
            if type(row[key]) is not int or not bounded(row[key], limit):
                return False
    return all(type(ledger['routes'][f]['reentries']) is int and
               bounded(ledger['routes'][f]['reentries'], 2) for f in ('GPOLY', 'GNN'))


def state_check(source, bnorm):
    record = source['state']; path = Path(record['path'])
    if file_hash(path) != record['sha256']:
        raise ValueError('state file hash differs')
    # Never load old GK/c/v or Q/image arrays to audit the saved physical z.
    with np.load(path, allow_pickle=False) as stream:
        arrays = {k: np.array(stream[k]) for k in
                  ('trace', 'port', 'z', 'residual', 'x', 'outer_directions') if k in stream.files}
    for key, array in arrays.items():
        if not np.isfinite(array).all():
            raise ValueError('nonfinite state')
        if key+'_sha256' in record and array_hash(array) != record[key+'_sha256']:
            raise ValueError(key+' raw array hash')
    if any(arrays[k].shape != shape for k, shape in
           (('trace', (18144,)), ('port', (40,)), ('z', (18184,)), ('residual', (18184,)))):
        raise ValueError('full trace/port/residual inventory')
    if not np.array_equal(arrays['z'], np.r_[arrays['trace'], arrays['port']]):
        raise ValueError('full z composition')
    rho = float(np.linalg.norm(arrays['residual'])/bnorm)
    if source.get('audit') and abs(rho-source['audit']['schur_relative']) > 1e-12:
        raise ValueError('raw residual versus saved Schur')
    return dict(raw_Schur=rho, arrays_checked=list(arrays), Q_U_R_GK_loaded=False), arrays


def check_v19(pre, ledger, budget, verify, plan, cycles):
    errors=[]; states={}; cycle_checks={}
    packet=pre['operator_packet']
    if file_hash(ROOT/'benchmarks/artifacts/task042/v18/FROZEN.json')!=plan['old_v18_frozen_sha256']:
        errors.append('old_V18_freeze_changed')
    if file_hash(packet['path']) != packet['sha256']:
        errors.append('original_action_packet_hash')
    with np.load(packet['path'], allow_pickle=False) as stream:
        bnorm=float(np.linalg.norm(stream['b'])); master=array_hash(stream['masters'])
    interfaces={f:close_qualified(row) for f,row in pre['libraries'].items()}
    if set(interfaces)!={'GPOLY','GNN'} or not all(interfaces.values()):errors.append('C0_identity')
    if any(p!=pre['libraries'][f]['qualified'] for f,p in interfaces.items()):errors.append('C0_status')
    if pre['action_counts']['S']+pre['action_counts']['SH']>256:errors.append('C0_budget')
    if not caps(ledger,budget):errors.append('campaign_budget')
    parents={}
    for family,item in plan['initial_states'].items():
        _,parents[family]=state_check(item,bnorm)
    for route, rows in cycles.items():
        method,family=route.split('_',1); actions=0; previous_x=np.zeros(18144,complex)
        previous_directions=np.empty((0,18144),complex); fixed_rb_sha=None
        for j,row in enumerate(rows):
            try:
                if row['cycle']!=j+1 or not row['committed'] or row['audit_pending']:
                    raise ValueError('noncontiguous/uncommitted cycle')
                _,arrays=state_check(row,bnorm); inner=row['inner']; ident=row['identity']
                if ident['library']!=family or ident['algorithm_route']!=method or ident['master_sha256']!=master:
                    raise ValueError('route/master identity')
                if ident['action_sha256']!=packet['sha256'] or row['parent_R_state']['sha256']!=plan['initial_states'][family]['state']['sha256']:
                    raise ValueError('operator/fixed R parent')
                if not bounded(row['original_residual_identity_relative'],1e-8):raise ValueError('original identity')
                if equation(row['audit'])!=(row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'):
                    raise ValueError('equation status')
                if method=='P':
                    if type(inner['inner_iterations']) is not int or not bounded(inner['inner_iterations'],256):
                        raise ValueError('measured Arnoldi count')
                else:
                    if fixed_rb_sha is None:fixed_rb_sha=ident['fixed_rb_sha256']
                    if ident['fixed_rb_sha256']!=fixed_rb_sha:raise ValueError('fixed rb changed across boundaries')
                    if ident['parent_trace_sha256']!=array_hash(parents[family]['trace']):raise ValueError('fixed base trace hash')
                    dirs=arrays['outer_directions']; count=len(dirs)
                    if dirs.shape!=(count,18144) or count>3 or row['direction_inventory']['Av'] is not None:
                        raise ValueError('ordered direction inventory')
                    if row['direction_inventory']['array_sha256']!=array_hash(dirs) or row['direction_inventory']['count']!=count:
                        raise ValueError('direction hash/count')
                    if not np.array_equal(arrays['trace'],parents[family]['trace']+arrays['x']):
                        raise ValueError('fixed base plus cumulative x')
                    if ident['prior_x_sha256']!=array_hash(previous_x) or ident['prior_directions_sha256']!=array_hash(previous_directions):
                        raise ValueError('prior boundary continuity')
                    if inner['internal_Arnoldi_iterations'] is not None or inner['maxiter']!=1 or inner['outer_k']!=3 or inner['inner_m']!=256:
                        raise ValueError('boundary semantics/unknown Arnoldi')
                    if not bounded(row['fixed_correction_identity_relative'],1e-8):raise ValueError('fixed rb identity')
                    previous_x=arrays['x'];previous_directions=dirs
                actions+=sum(row['cycle_action_counts'][k] for k in ('S','SH'))
            except (ValueError,KeyError,OSError) as error:errors.append(route+'.'+str(j+1)+':'+str(error))
        if len(rows)>64 or actions>ledger['routes'][route]['actions_upper']:errors.append(route+'.work_cap')
        cycle_checks[route]=dict(cycles=len(rows),actual_cycle_S_SH=actions,
            internal_Arnoldi='unknown' if method=='L' else sum(r['inner']['inner_iterations'] for r in rows))
    if not verify['reference_native_pass'] or verify['reference_audit']['independent_DOLFINx_total_native_relative']>1e-10:
        errors.append('reference_native')
    if verify['reference_feedback_to_solver'] or not verify['no_new_solve'] or not verify['no_new_LU']:
        errors.append('reference_boundary')
    if file_hash(verify['reference_identity']['path'])!=verify['reference_identity']['sha256']:
        errors.append('reference_hash')
    if verify['states_read']!=len(verify['rows']) or not 1<=verify['states_read']<=12:errors.append('field_inventory')
    qualified={}
    for name,row in verify['rows'].items():
        try:states[name],_=state_check(verify['state_sources'][name],bnorm)
        except (ValueError,KeyError,OSError) as error:errors.append(name+':'+str(error))
        qualified[name]=field_gate(row,verify['reference_native_pass'])
        if qualified[name]!=(row['status']=='SAME_DISCRETE_QUALIFIED'):errors.append(name+'.field_status')
        if equation(row['audit'])!=(row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'):errors.append(name+'.equation_status')
    return dict(status='EVIDENCE_CONSISTENT' if not errors else 'RAW_MISMATCH',mismatches=errors,
        interfaces=interfaces,cycle_checks=cycle_checks,raw_state_checks=states,
        strict_same_discrete=qualified,strict_qualified_states=sum(qualified.values()),
        original_action_or_solve_in_checker=0,Q_U_R_GK_loaded=False,
        no_saved_status_trusted=True,no_neural_training_increment=True)
