"""Cache-only independent V35 return inventory and gate recomputation."""
import json
from pathlib import Path

import numpy as np

from src.runners.autonomous_neural_head import original_gate
from src.solvers.full_input_online import continue_after_cycle
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def check(record, b, *, root, nt=18144):
    b = np.asarray(b)
    if b.shape!=(nt+40,) or not np.isfinite(b).all() or np.linalg.norm(b)==0:
        raise ValueError('checker physical RHS inventory')
    rows = record['cycles']
    if not 1<=len(rows)<=2 or [r['cycle'] for r in rows]!=list(range(1,len(rows)+1)):
        raise ValueError('one original cold trajectory inventory')
    if len(rows)==2 and not continue_after_cycle(rows[0]['audit'],1)[0]:
        raise ValueError('unauthorized second cycle')
    outputs=[]
    for row in rows:
        state=row['state']; path=Path(state['path']).resolve()
        if not path.is_relative_to(Path(root).resolve()) or file_hash(path)!=state['sha256']:
            raise ValueError('online state container path/hash')
        with np.load(path,allow_pickle=False) as contents:
            values={k:np.array(contents[k]) for k in ('y','By','trace','port','z','residual')}
        for k,v in values.items():
            if array_hash(v)!=state[k+'_sha256'] or not np.isfinite(v).all():
                raise ValueError('online state member hash/nonfinite '+k)
        if (any(values[k].shape!=(nt,) for k in ('y','By','trace'))
                or values['port'].shape!=(40,) or values['z'].shape!=(nt+40,)
                or values['residual'].shape!=(nt+40,)
                or not np.array_equal(values['z'],np.r_[values['trace'],values['port']])):
            raise ValueError('trace/port/full-z inventory')
        base=np.zeros(nt,complex) if row['cycle']==1 else previous
        if not np.array_equal(values['trace'],base+values['By']):
            raise ValueError('right variable/physical correction identity')
        if not 0<=row['inner']['inner_iterations']<=256 or row['audit_pending']:
            raise ValueError('returned inner/audit inventory')
        rho=float(np.linalg.norm(values['residual'])/np.linalg.norm(b))
        if abs(rho-row['audit']['schur_relative'])>1e-11:
            raise ValueError('raw residual/audit Schur mismatch')
        gate=original_gate(row['audit'])
        if gate!=row['original_equation_gate']:
            raise ValueError('declared equation gate mismatch')
        outputs.append(dict(cycle=row['cycle'],measured_schur_relative=rho,
            original_equation_gate=gate,full_state_sha256=state['sha256'],
            state_members=state,inner_iterations=row['inner']['inner_iterations']))
        previous=values['trace']
    if record['status']!=continue_after_cycle(rows[-1]['audit'],len(rows))[1]:
        raise ValueError('final decision mismatch')
    return dict(status='CHECKED',rows=outputs,reference_read=False,
                new_actions=0,new_factor_reads=0,neural_gain='NOT_DEMONSTRATED')


def consumption(record, book):
    """Recompute deployment inventory; do not accept a qualified/status flag."""
    from src.solvers.full_input_online_window import CAPS
    counts=record['budget_counts']
    if set(counts)!=set(CAPS) or any(type(v) is not int or not 0<=v<=CAPS[k] for k,v in counts.items()):
        raise ValueError('full consumption inventory/caps')
    if len(book['runs'])!=1 or book['active'] is not None or book['charged']!=counts:
        raise ValueError('settled single actor consumption differs')
    run=book['runs'][0]
    if (not run['descendants_cleared'] or not run['exact_counts']
            or run['source_sha']!=record['source_sha'] or run['counts']!=counts):
        raise ValueError('source/settlement/cleanup identity')
    n=record['pc_apply_calls']-record['pc_zero_calls']
    if (counts['pc_apply']!=record['pc_apply_calls'] or n<0 or counts['factor_readers']!=7
            or counts['joint_lu_solve']!=2+2*n or counts['outer_lu_solve']!=12+6*n
            or counts['explicit_triangular_pass']!=2*(counts['joint_lu_solve']+counts['outer_lu_solve'])):
        raise ValueError('fixed eight-solves PC consumption mismatch')
    factors=record['factor_reloads']
    if [x['block'] for x in factors]!=['J',0,1,2,3,4,6] or [x['row_count'] for x in factors]!=[3888,2913,2676,2289,2076,2439,1863]:
        raise ValueError('seven factor/support inventory')
    for i,factor in enumerate(factors):
        witnesses=factor['witnesses']
        if (len(witnesses)!=2 or [x['seed'] for x in witnesses]!=[422601+2*i,422602+2*i]
                or factor['refactored'] or len(factor['files'])!=3
                or [f['key'] for f in factor['files']]!=['matrix','LU','pivots']
                or not all(f['readonly'] and len(f['array_sha256'])==64 for f in factor['files'])):
            raise ValueError('factor qualification raw inventory')
        for w in witnesses:
            values=[(w['solve_relative'],1e-8),(w['solve_operation_relative'],1e-12),
                (w['original_principal_action']['operation_relative'],1e-10),
                (w['original_adjoint_action']['operation_relative'],1e-10)]
            if not all(np.isfinite(v) and 0<=v<=gate for v,gate in values):
                raise ValueError('factor numeric qualification failed')
        expected=2+(2*n if i==0 else n)
        if factor['solve_calls']!=expected or factor['RHS_columns']!=expected or factor['triangular_passes']!=2*expected:
            raise ValueError('bundle solve/RHS/triangular inventory')
    actions=sum(record['action_counts'][k]+record['fast_action_counts'][k] for k in ('S','SH'))
    if actions!=counts['actions'] or record['actual_equivalent_actions']!=actions:
        raise ValueError('original plus fast equivalent action inventory')
    if (counts['arnoldi']!=sum(x['inner']['inner_iterations'] for x in record['cycles'])
            or counts['cycles']!=len(record['cycles']) or counts['original_audits']!=len(record['cycles'])):
        raise ValueError('actual Arnoldi/cycle/audit inventory')
    checks=record['PC_qualification']
    errors=[checks['repeat']['operation_relative'],checks['complex_linearity']['operation_relative'],
            *(x['operation_relative'] for x in checks['J_balance'])]
    if (checks['seeds']!=[423511,423513] or not checks['zero_exact']
            or checks['support_rows']!=[2913,2676,2289,2076,2439,2220,1863,1668]
            or not all(np.isfinite(v) and 0<=v<=1e-10 for v in errors)):
        raise ValueError('arbitrary-RHS PC qualification mismatch')
    return dict(status='CONSUMPTION_CHECKED',counts=counts,nonzero_PC_calls=n,
        equivalent_actions=actions,field_recovery_calls_derived=counts['original_audits'],
        legacy_all_batch_equivalent_actions_scope='old oracle only; not total deployment',
        legacy_field_recovery_calls_scope='inherited adapter zero; reconstructed from original audits',
        full_hash_copy_scope='reader whole-file container hash allocates; only canonical array hash streams64 rows',
        neural_gain='NOT_DEMONSTRATED')


def main():
    from src.io.full_input_online import read_result, ARTIFACT_ROOT
    from src.runners.task042_shared import write_json
    record,_=read_result('ONLINE')
    # b is a compact original vector saved by the actor, not an accurate field.
    receipt=record['physical_rhs'];path=Path(receipt['path'])
    if file_hash(path)!=receipt['sha256']:
        raise ValueError('saved physical RHS hash')
    with np.load(path,allow_pickle=False) as data:
        b=np.array(data['b'])
    if array_hash(b)!=receipt['b_sha256']:
        raise ValueError('saved b member hash')
    result=check(record,b,root=ARTIFACT_ROOT)
    from src.solvers.full_input_online_window import ledger
    result['consumption']=consumption(record,ledger())
    result['source_sha']=record['source_sha']
    write_json(ARTIFACT_ROOT/'independent_checker.json',result)
    print(json.dumps(result))


if __name__=='__main__':
    main()
