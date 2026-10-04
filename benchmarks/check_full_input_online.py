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
    result['source_sha']=record['source_sha']
    write_json(ARTIFACT_ROOT/'independent_checker.json',result)
    print(json.dumps(result))


if __name__=='__main__':
    main()
