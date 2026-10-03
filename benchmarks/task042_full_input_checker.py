"""Independent saved-vector checks; no physical action, solve, factor or fit."""
import json
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.full_input_block_correction import EXPECTED, CAPS, VECTOR_KEYS
from benchmarks.collect_task042_return_direction import load_members
from benchmarks.task042_return_certificates import (require, scalar, finite,
    error_ratio, state_certificate, factor_sources, factor_reload_certificate)

NAMES=('V24-LZ-CYCLE4','V24-LCZ-CYCLE4')
OUTER=(0,1,2,3,4,6)
IDENTITIES=('action_sha256','physical_sha256','mode_sha256','canonical_master_sha256','b_sha256')


def classify(rows):
    if len(rows)!=2 or {x['name'] for x in rows}!=set(NAMES):return 'PARTIAL'
    if not all(x['trustworthy'] is True for x in rows):return 'NUMERICALLY_UNRESOLVED'
    if all(x['rho_full']<=.75 and x['rho0']>0 and x['rho_full']<=.8*x['rho0'] for x in rows):
        return 'FULL_INPUT_SINGLE_STEP_SIGNAL'
    if all(x['rho_full']>=.95 for x in rows) or all(x['rho_full']>=x['rho0']-1e-10 for x in rows):
        return 'FULL_INPUT_FIXED_STEP_INSUFFICIENT'
    return 'STATE_DEPENDENT_INCONCLUSIVE'


def numeric(row,a,state,cache25,cache26,cache32,groups,ids,nt):
    require(set(a)==set(VECTOR_KEYS),'exact new vector inventory')
    for k,v in a.items():
        shape=(nt+40,) if k=='audited_full_residual' else (40,) if k=='reclosed_port' else (len(ids),) if k=='joint_local_image' else (nt,)
        require(v.shape==shape and v.dtype==np.complex128 and np.isfinite(v).all(),'full vector shape/finite '+k)
    bn=finite(row['full_b_norm'],'physical b');require(bn>0,'positive physical b')
    state_certificate(row,a,state,nt)
    r=state['residual'][:nt];rn=float(np.linalg.norm(r));require(rn>0,'positive real input residual')
    scalar(rn,row['residual_norm'],'input residual norm')
    d,w=cache25['directions'],cache25['images']
    require(d.shape==w.shape==(nt,8),'eight fixed columns')
    for b in range(8):require(not np.count_nonzero(d[groups!=b,b]),'cache column/support order')
    outside=(groups!=5)&(groups!=7)
    require(not np.count_nonzero(a['qj'][outside]) and not np.count_nonzero(a['k'][outside]) and
            not np.count_nonzero(a['u'][~outside]),'J/outer support')
    # Inputs and +/-1 constructions are independent of the actor's metrics.
    expected=dict(input_residual=r,u=np.sum(d[:,OUTER],axis=1),au_cached=np.sum(w[:,OUTER],axis=1),
        qj=cache26['joint_direction'],aqj=cache26['joint_image'],
        qret=cache32['return_direction'],aqret_cached=cache32['return_image'])
    expected.update(delta=a['u']-a['k'],qfull=a['qret']+a['delta'],q0=a['qj']+a['u'])
    for k,v in expected.items():require(np.array_equal(a[k],v),'fixed cache/coefficients identity '+k)
    require(row['unit_coefficients'] is True and row['fitted_coefficients_used'] is False,'no fitted coefficients')
    scales=row['action_operation_scales'];operands=row['scale_provenance']['operands']
    require(set(scales)==set(operands)=={'u','k','delta','qret','qfull','q0'},'six action scales')
    require(row['scale_provenance']['method']=='cell_S_expand_plus_C_port_bound' and
            row['scale_provenance']['action_sha256']==row['operator_action_sha256'],'bound source')
    for key,cert in operands.items():
        require(cert['input_array_sha256']==array_hash(a[key]),'scale vector identity '+key)
        weights=np.asarray(cert['weights']);norms=np.asarray(cert['expanded_cell_norms'])
        require(weights.shape==norms.shape and weights.ndim==1 and len(weights)>0 and
                np.isfinite(weights).all() and np.isfinite(norms).all() and
                np.all(weights>=0) and np.all(norms>=0),'finite precancellation operands')
        bound=float(weights@norms+finite(cert['C_norm'],'C norm')*finite(cert['closed_port_norm'],'closed port'))
        scalar(bound,cert['value'],'computed operand bound');scalar(bound,scales[key],'saved operand bound')
    tests={
        'cached_outer_action':(a['au'],a['au_cached'],scales['u']),
        'cached_return_action':(a['aqret'],a['aqret_cached'],scales['qret']),
        'delta_linearity':(a['adelta'],a['au']-a['ak'],scales['u']+scales['k']),
        'full_linearity':(a['aqfull'],a['aqret']+a['adelta'],scales['qret']+scales['delta']),
        'control_linearity':(a['aq0'],a['aqj']+a['au'],np.linalg.norm(a['aqj'])+scales['u']),
        'J_delta_cancellation':(a['adelta'][ids],np.zeros(len(ids)),scales['u']+scales['k']),
        'J_full_rhs':(a['aqfull'][ids],r[ids],scales['qret']+scales['u']+scales['k']+rn),
        'J_feedback_solve':(a['joint_local_image'],a['au'][ids],np.linalg.norm(a['joint_local_image'])+np.linalg.norm(a['au'][ids]))}
    require(set(row['checks'])==set(tests),'all mathematical checks')
    worst_b=worst_op=0.
    for name,(left,right,op) in tests.items():
        c=row['checks'][name];error=float(np.linalg.norm(left-right));op=float(op)
        for key,value in [('error_norm',error),('operation_scale',op),('full_b_relative',error/bn),
                          ('current_r_relative',error/rn),('operation_relative',error_ratio(error,op))]:
            scalar(value,c[key],name+'.'+key)
        require(error/bn<=1e-11 and error_ratio(error,op)<=1e-10,'unsafe original identity '+name)
        worst_b=max(worst_b,error/bn);worst_op=max(worst_op,error_ratio(error,op))
    js=row['joint_feedback_solve'];err=float(np.linalg.norm(a['joint_local_image']-a['au'][ids]))
    jn=float(np.linalg.norm(a['au'][ids]));scalar(err,js['error_norm'],'feedback solve error');scalar(jn,js['rhs_norm'],'feedback RHS')
    relative=error_ratio(err,jn);oper=error_ratio(err,finite(js['operand_scale'],'J operand'))
    scalar(relative,js['relative'],'feedback relative');scalar(oper,js['operation_relative'],'feedback operation')
    require(relative<=1e-8 and oper<=1e-12,'J feedback solve unsafe')
    metrics={k:float(np.linalg.norm(r-a[member])/rn) for k,member in [('rho_full','aqfull'),('rho0','aq0'),('rho_ret','aqret')]}
    ro=r.copy();ro[ids]=0;ron=float(np.linalg.norm(ro))
    outer=float(np.linalg.norm(ro-a['adelta'])/ron) if ron else None
    for k,v in metrics.items():scalar(v,row[k],k)
    if outer is None:require(row['outer_isolated_ratio'] is None and row['outer_isolated_status']=='NOT_APPLICABLE','zero outer denominator')
    else:scalar(outer,row['outer_isolated_ratio'],'outer isolated');require(row['outer_isolated_status']=='MEASURED','outer status')
    require(row['trustworthy'] is True,'untrusted result')
    return dict(name=row['name'],trustworthy=True,**metrics,outer_isolated_ratio=outer,
        max_identity_full_b_relative=worst_b,max_identity_operation_relative=worst_op)


def consumption(result,plan,sources,ledger,manifest):
    require(set(EXPECTED)==set(CAPS) and result['budget_counts']==EXPECTED,'complete fixed consumption')
    require(result['action_counts']==dict(S=20,SH=2,audit=0),'S/SH inventory')
    reload=result['factor_reloads'];require(len(reload)==1 and reload[0]['block']=='J','one J reader only')
    factor_reload_certificate(reload[0],sources['J'])
    ports=result['port_rhs_inventory']
    require(len(ports)==21 and sum(x['adjoint'] is True for x in ports)==2 and
        all(type(x['adjoint']) is bool and x['shape']==[40] and x['RHS_columns']==1 for x in ports),'complete port count/columns')
    require(ledger['active'] is None,'unsettled actor')
    consuming=[r for r in ledger['runs'] if any(r['counts'].values())]
    require(len(consuming)==1,'one real consuming actor')
    for r in ledger['runs']:
        if r not in consuming:require(r['classification']=='WORKER_FAILED' and not any(r['upper'].values()),'nonzero earlier consumption')
    run=consuming[0]
    require(run['exact_counts'] is True and run['classification']=='COMPLETED' and
        run['directory']==result['run_directory'] and run['source_sha']==result['source_sha'],'settled run identity')
    require(all(c==EXPECTED for c in (run['counts'],run['completed'],run['upper'],ledger['charged'],manifest['completed_budget_counts'])),'durable count mismatch')
    require(manifest['completed_action_counts']==result['action_counts'] and
        manifest['source_sha']==result['source_sha'] and manifest['input_sha256']==result['input_sha256'] and
        manifest['plan_sha256']==result['plan_sha256'],'manifest identity')


def collect(*,root=None,plan_path=None,artifact_root=None,records=None,ledger_path=None,nt=18144,old_plan=None):
    from src.io import full_input_block_v33 as io
    root=Path(root or io.ROOT).resolve();plan_path=Path(plan_path or io.PLAN_PATH)
    artifact_root=Path(artifact_root or io.ARTIFACT_ROOT);records=Path(records or root/'docs/task042_neural_coarse_inverse/outcomes/records')
    records.mkdir(parents=True,exist_ok=True);plan=json.loads(plan_path.read_text());pointer=artifact_root/'DIAGNOSTIC.json'
    if not pointer.exists():out=dict(status='NOT_RUN',rows=[],decision='PARTIAL')
    else:
        idx=json.loads(pointer.read_text());result=io.checked_json(idx,artifact_root)
        if result['status']!='DIAGNOSTIC_COMPLETE':
            out=dict(status='PARTIAL_UNRESOLVED',raw=idx,decision=result.get('decision','PARTIAL'),
                rows=[dict(name=x['name'],rho_full=None,rho0=None) for x in plan['states']])
        else:
            require(result['plan_sha256']==file_hash(plan_path),'pre-registration')
            require(len(result['rows'])==2 and {r['name'] for r in result['rows']}==set(NAMES) and
                    tuple(r['name'] for r in plan['states'])==NAMES,'fixed two-state inventory')
            require(result['operator_identity']=={k:plan[k] for k in IDENTITIES} and
                result['operator_packet']['sha256']==plan['action_sha256'] and result['complete_ports']==40,'original operator identity')
            require(not result['reference_arrays_read'] and not result['Q_U_R_D_L_loaded'] and
                not result['global_p4_factor_constructed'] and result['new_solver_states']==0,'forbidden data/result')
            setup=io.checked_json(plan['local_setup'],root/'benchmarks/artifacts/task042/v24')
            prior=io.checked_json(plan['v26_result'],root/'benchmarks/artifacts/task042/v26')
            ret=io.checked_json(plan['v32_result'],root/'benchmarks/artifacts/task042/v32')
            old=io.checked_json(plan['v25_result'],root/'benchmarks/artifacts/task042/v25')
            from benchmarks.collect_task042_block_direction import fixed_inventory
            oldrows={x['name']:x for x in fixed_inventory(old,old_plan,root=root)}
            require(prior['source_sha']==plan['v26_source_sha'] and ret['source_sha']==plan['v32_source_sha'] and
                old['source_sha']==plan['v25_source_sha'] and ret['status']=='DIAGNOSTIC_COMPLETE','upstream source/status')
            for r in (prior,ret,old):require(r['operator_packet']['sha256']==plan['action_sha256'],'upstream operator')
            manifest=io.checked_json(result['run_manifest'],root/'results/task042')
            lp=Path(ledger_path or result['ledger_path']).resolve();require(lp.is_relative_to(root/'tmp/task042/v33'),'ledger namespace')
            consumption(result,plan,factor_sources(setup,prior,plan),json.loads(lp.read_text()),manifest)
            groups=np.empty(nt,np.int64)
            allrows=[]
            for b,part in enumerate(setup['block_inventory']):groups[part['rows']]=b;allrows.extend(part['rows'])
            require(sorted(allrows)==list(range(nt)),'all canonical rows once')
            ids=np.flatnonzero((groups==5)|(groups==7));require(array_hash(ids)==plan['joint_rows_sha256'],'joint row order')
            checked=[]
            for item in plan['states']:
                row=next(r for r in result['rows'] if r['name']==item['name'])
                for src,dst in [('parent_result','parent_result'),('state','input_state'),('v25_arrays','v25_arrays'),('v26_arrays','v26_arrays'),('v32_arrays','v32_arrays')]:
                    require(row[dst]==item[src],'named parent/cache receipt')
                p=next(r for r in prior['rows'] if r['name']==item['name']);q=next(r for r in ret['rows'] if r['name']==item['name'])
                require(p['input_state']==q['input_state']==item['state'] and p['diagnostic_arrays']==item['v26_arrays'] and
                    q['diagnostic_arrays']==item['v32_arrays'] and oldrows[item['name']]['diagnostic_arrays']==item['v25_arrays'] and
                    p['old_direction_arrays']==q['v25_arrays']==item['v25_arrays'] and q['v26_arrays']==item['v26_arrays'] and
                    p['trustworthy'] and q['trustworthy'] and all(p['gates'].values()) and all(q['gates'].values()),'qualified named caches')
                scalar(p['full_b_norm'],row['full_b_norm'],'b normalization')
                parent=io.checked_json(item['parent_result'],root/'benchmarks/artifacts/task042/v24')
                require(parent['source_sha']==plan['upstream_source_sha'] and parent['operator_packet']['sha256']==plan['action_sha256'] and
                    parent['cycles'][3]['state']==item['state'],'V24 parent')
                state=load_members(item['state'],('trace','port','z','residual'),root/'benchmarks/artifacts/task042/v24')
                d=load_members(item['v25_arrays'],('directions','images'),root/'benchmarks/artifacts/task042/v25')
                j=load_members(item['v26_arrays'],('joint_direction','joint_image'),root/'benchmarks/artifacts/task042/v26')
                retdata=load_members(item['v32_arrays'],('return_direction','return_image'),root/'benchmarks/artifacts/task042/v32')
                a=load_members(row['diagnostic_arrays'],VECTOR_KEYS,artifact_root)
                require(row['operator_action_sha256']==plan['action_sha256'],'original action scale identity')
                checked.append(numeric(row,a,state,d,j,retdata,groups,ids,nt))
            out=dict(status='CHECKED',rows=checked,decision=classify(checked),raw=idx,
                actual_numeric_source=result['source_sha'],no_factor_reads=True,no_new_actions=True,no_QR_SVD=True)
            require(out['decision']==result['decision'],'independent decision')
    out['checker_source_sha256']=file_hash(Path(__file__))
    write_json(records/'full_input_checker_v33.json',out)
    return out


if __name__=='__main__':print(json.dumps(collect(),ensure_ascii=False))
