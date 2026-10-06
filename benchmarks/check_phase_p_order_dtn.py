"""Independent V54 saved-array checks; no FE construction or solver."""
import hashlib
import json
from pathlib import Path
import numpy as np
from src.solvers.scattering_anchor_checks import checked_arrays


def check_frozen_member(value,record,name):
    from src.solvers.scattering_anchor import array_hash
    meta=record['members'][name]
    if list(value.shape)!=meta['shape'] or str(value.dtype)!=meta['dtype'] or array_hash(value)!=meta['sha256']:
        raise ValueError('unchanged physical body differs from frozen parent')
    return meta['sha256']


def operation(numerator,denominator):
    n=float(numerator);d=float(denominator)
    if not np.isfinite([n,d]).all() or min(n,d)<0:raise ValueError('nonfinite/negative operation scale')
    return n/max(d,1e-30)


def check_inventory_identity(v):
    required=('rhs_old','rhs_new','old_residual','new_residual','old_volume','new_volume',
        'old_closed_boundary','new_closed_boundary','load_delta','boundary_delta','volume_delta','action_delta','identity_defect')
    if any(k not in v for k in required):raise ValueError('full inventory residual primitive vectors required')
    shape=v['rhs_old'].shape
    if len(shape)!=1 or not all(v[k].shape==shape and np.isfinite(v[k]).all() for k in required):raise ValueError('inventory residual vector layout')
    load=v['rhs_new']-v['rhs_old'];vol=v['new_volume']-v['old_volume'];boundary=v['new_closed_boundary']-v['old_closed_boundary']
    action=vol+boundary;defect=(v['new_residual']-v['old_residual'])-(load-action)
    scale=sum(np.linalg.norm(v[k]) for k in ('rhs_old','rhs_new','old_volume','new_volume','old_closed_boundary','new_closed_boundary'))
    differences={k:operation(np.linalg.norm(x-v[k]),scale) for k,x in dict(load_delta=load,volume_delta=vol,boundary_delta=boundary,action_delta=action,identity_defect=defect).items()}
    value=operation(np.linalg.norm(defect),scale)
    primitive_consistency={label:operation(np.linalg.norm(v[label+'_residual']-(v['rhs_'+label]-v[label+'_volume']-v[label+'_closed_boundary'])),scale) for label in ('old','new')}
    passed=max(value,*differences.values(),*primitive_consistency.values())<=1e-10
    if not passed:raise ValueError('original residual inventory identity/array consistency')
    cross=np.vdot(load,action)
    return dict(operation=value,numerator=float(np.linalg.norm(defect)),denominator=float(scale),array_consistency=differences,primitive_consistency=primitive_consistency,
        cross_load_action=[float(cross.real),float(cross.imag)],load_norm=float(np.linalg.norm(load)),boundary_norm=float(np.linalg.norm(boundary)),pass_gate=passed)


def check_raw_direction(v,d):
    keys=[f'q13_d{d}_{k}' for k in ('curl','kappa_cross','mass')]
    lower=[f'q11_d{d}_{k}' for k in ('curl','kappa_cross','mass')]
    required=keys+lower+[f'q13_d{d}',f'q11_d{d}',f'raw_d{d}',f'coefficient_d{d}']
    if any(k not in v for k in required):raise ValueError('raw direction component inventory')
    if any(v[k].shape!=(1344,) or not np.isfinite(v[k]).all() for k in required):raise ValueError('p7 complete local direction layout')
    if np.linalg.norm(v[f'coefficient_d{d}'])==0:raise ValueError('nonzero direction required')
    total=sum(v[k] for k in keys);scale=sum(np.linalg.norm(v[k]) for k in keys)
    errors={name:operation(np.linalg.norm(a-b),scale) for name,a,b in (
        ('raw',v[f'raw_d{d}'],v[f'q13_d{d}']),('quadrature',v[f'q11_d{d}'],v[f'q13_d{d}']),('split',total,v[f'q13_d{d}']),('lower_split',sum(v[k] for k in lower),v[f'q11_d{d}']))}
    if max(errors.values())>1e-10:raise ValueError('p7 raw action/directional integration')
    return dict(errors=errors,denominator=float(scale),pass_gate=True)


def collect_separation(scope):
    from src.runners.task042_shared import write_json
    import os
    current=scope.stage('D');binding=current['original_D_evidence'];p=Path(binding['path'])
    if hashlib.sha256(p.read_bytes()).hexdigest()!=binding['sha256']:raise ValueError('original D hash')
    old=json.loads(p.read_text());embedding=[]
    for row in current['embedding']:
        a=checked_arrays(row['arrays']);b=checked_arrays(row['component_arrays'])
        scale=sum(np.linalg.norm(b[k]) for k in ('P_curl','P_material_mass','P_DtN','dual_B_curl','dual_B_material_mass','dual_B_DtN'))
        n=np.linalg.norm(a['action6']-a['dual_action7']);actual=operation(n,scale)
        sums=[(sum(b['P_'+k] for k in ('curl','material_mass','DtN')),a['action6']),
            (sum(b['dual_B_'+k] for k in ('curl','material_mass','DtN')),a['dual_action7'])]
        reconstruction=max(operation(np.linalg.norm(x-y),scale) for x,y in sums)
        load=operation(np.linalg.norm(a['rhs6']-a['dual_rhs7']),np.linalg.norm(a['rhs6']))
        if max(actual,reconstruction,load)>1e-10:raise ValueError('full body embedded action/load components')
        if not np.isclose(actual,row['operator_operation'],rtol=1e-12,atol=1e-18):raise ValueError('D recorded operation differs from raw vectors')
        embedding.append(dict(label=row['label'],operation=actual,numerator=float(n),denominator=float(scale),reconstruction=reconstruction,
            load_operation=load,historical_result_scale=operation(n,np.linalg.norm(a['action6'])),pass_gate=True))
    contract=scope.plan_record()['raw_tensor_parents']['B'];manifest=scope.ROOT/contract['path']
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=contract['sha256']:raise ValueError('D raw inventory parent')
    expected={r['key']:r['arrays']['sha256'] for r in json.loads(manifest.read_text())['classes']}
    rows=old['raw_directions'];actual={r['key']:r['parent_sha256'] for r in rows}
    if len(rows)!=len(actual) or actual!=expected:raise ValueError('complete unique raw class inventory')
    raw=[]
    for row in rows:
        v=checked_arrays(row['arrays']);raw.append(dict(key=row['key'],directions=[check_raw_direction(v,d) for d in (0,1)]))
    eval_vectors=checked_arrays(old['saved_evaluation']['arrays']);evaluations=[]
    for row in old['saved_evaluation']['rows']:
        key=str(row['cell'])+'_'+row['component'];x=eval_vectors[key+'_old'];y=eval_vectors[key+'_new']
        value=operation(np.linalg.norm(x-y),np.linalg.norm(x))
        if value>1e-11:raise ValueError('saved p7 old/new physical evaluation')
        evaluations.append(dict(cell=row['cell'],component=row['component'],operation=value))
    inventory=[]
    for role in scope.SOLVES:
        if not (scope.ARTIFACT/(role+'.json')).exists():continue
        r=scope.stage(role)
        if not r.get('equation_pass'):continue
        w=r['projected_parent828']['finite_mode_projection'];v=checked_arrays(w['residual_identity']['arrays'])
        parent=scope.read({'R7':'B','R6':'P','C':'R7'}[role])
        unchanged=check_frozen_member(v['u_unchanged'],parent['arrays'],'u_storage')
        checked=check_inventory_identity(v)
        if not np.isclose(checked['operation'],w['residual_identity']['operation'],rtol=1e-12,atol=1e-18):raise ValueError('recorded inventory operation differs')
        inventory.append(dict(role=role,original_count=w['original_count'],added_count=w['added_count'],new_count=w['count'],unchanged_body_sha256=unchanged,**checked))
    result=dict(status='SAVED_VECTOR_CHECKS_PASSED',embedding=embedding,raw_classes=raw,saved_p7_evaluation=evaluations,inventory_changes=inventory,
        original_D=binding,scope='independent saved vector norms/sums/identities; scalar-only J physical/dual measurements remain actor evidence; no new FE or operator')
    folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY'])/'records'
    write_json(folder/'p_order_dtn_vector_checks_v54.json',result)
    return result
