"""Compact V21 raw-vector/Gate/contract reader, never calls an operator."""
import math
import numpy as np
from src.io.augmented_trace_evidence_check import equation
from src.io.post_lsqr_polish_check import state_check
from src.io.resumable_trace_evidence_check import field_gate
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.io.exact_action_recycling import ROUTE_WALL,ROUTE_ACTION


def bounded(x,limit):
    return isinstance(x,(int,float)) and math.isfinite(x) and 0<=x<=limit


def limits(ledger):
    caps=dict(actions=100000,audits=320,field_states=12)
    return bool(ledger.get('active') is None and ledger['closed'] and set(ledger['charged'])==set(caps)
        and all(type(ledger['charged'][key]) is int and bounded(ledger['charged'][key],v) for key,v in caps.items())
        and bounded(ledger['reentries'],2) and bounded(ledger['cooldown_seconds'],1200) and len(ledger['repairs'])<=4
        and all(name in ROUTE_WALL and bounded(v['wall_seconds'],ROUTE_WALL[name])
                and bounded(v['actions'],ROUTE_ACTION[name]) for name,v in ledger['routes'].items()))


def recycle_contract(row):
    return bool(row['m']==256 and row['k']==32 and row['maxiter']==1 and row['preconditioner'] is None
        and row['truncate']=='oldest' and row['discard_C'] is False
        and row['relative_tolerance']==0 and row['internal_Arnoldi_iterations'] is None
        and bounded(row['CU_count'],33) and all(type(i) is int and 0<=i<row['CU_count'] for i in row['CU_none_indices']))


def check_records(pre,routes,verify,ledger,plan):
    errors=[];raw={};packet=pre['operator_packet']
    if file_hash(packet['path'])!=plan['action_sha256']:errors.append('original action file hash')
    with np.load(packet['path'],allow_pickle=False) as a:
        bnorm=float(np.linalg.norm(a['b']));master=array_hash(a['masters'])
    if not limits(ledger):errors.append('campaign caps/freeze')
    parents={}
    for key,item in plan['initial_states'].items():_,parents[key]=state_check(item,bnorm)
    for name,route in routes.items():
        try:
            if route['reference_read'] or route['old_CU_or_Q_loaded'] or route['neural_training_increment'] or route['global_factor_constructed']:
                raise ValueError('data/factor/training boundary')
            base=np.zeros(18144,complex) if name=='Z' else parents['GNN' if name=='T' else 'GPOLY']['trace']
            if array_hash(base)!=route['base_trace_sha256']:raise ValueError('frozen independent start')
            for index,row in enumerate(route['cycles'],1):
                measured,arrays=state_check(row,bnorm);raw[name+'-'+str(index)]=measured
                if row['cycle']!=index or row['audit_pending'] or not row['committed']:raise ValueError('cycle/commit continuity')
                if row['identity']['action_sha256']!=plan['action_sha256'] or row['identity']['master_sha256']!=master:raise ValueError('action/master identity')
                if not np.array_equal(arrays['trace'],base+arrays['x']):raise ValueError('base plus cumulative correction')
                if equation(row['audit'])!=(row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'):raise ValueError('original equation status')
                if row['inner']['absolute_tolerance']!=1e-8*bnorm:raise ValueError('fixed physical b denominator')
                if name!='B' and not recycle_contract(row['inner']):raise ValueError('CU/GCROT specification')
                if not bounded(row['fixed_correction_identity_relative'],1e-10 if name!='B' else 1e-8):raise ValueError('correction identity')
                if row.get('old_new_residual_difference_full_b',0)>1e-11:raise ValueError('old/new residual identity')
                if 'recycle_check' in row and any(p['operation_relative']>1e-10 for p in row['recycle_check']['pairs']):raise ValueError('CU original image')
        except (ValueError,KeyError,OSError) as error:errors.append(name+': '+str(error))
    qualified={};equations={}
    reference_pass=bool(equation(verify['reference_audit']) and bounded(verify['reference_audit']['independent_DOLFINx_total_native_relative'],1e-10))
    for name,row in verify['rows'].items():
        try:raw[name],_=state_check(verify['state_sources'][name],bnorm)
        except (ValueError,KeyError,OSError) as error:errors.append(name+': '+str(error))
        qualified[name]=field_gate(row,reference_pass);equations[name]=equation(row['audit'])
        if qualified[name]!=(row['status']=='SAME_DISCRETE_QUALIFIED'):errors.append(name+' field status')
    if not reference_pass or verify['reference_feedback_to_solver'] or not verify['queue_frozen'] or not verify['no_new_LU']:errors.append('reference barrier/actual residual')
    return dict(status='EVIDENCE_CONSISTENT' if not errors else 'RAW_MISMATCH',mismatches=errors,raw_checks=raw,
        original_equation=equations,strict_same_discrete=qualified,strict_qualified_states=sum(qualified.values()),
        no_saved_status_trusted=True,operator_or_factor_or_solve_calls=0,global_factor_present=False,hidden_training_increment=False)
