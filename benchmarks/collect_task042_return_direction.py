"""Independent cached-array V28 checker: no action, factor solve, QR or SVD."""
import json
from pathlib import Path
import numpy as np
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.return_block_window import CAPS
from benchmarks.task042_return_certificates import complete_consumption,flow_certificates,state_certificate,factor_sources

NAMES=('V24-LZ-CYCLE4','V24-LCZ-CYCLE4')
GATES={'baseline_identity','QR','stationarity','original_recombination','inequality'}
IDENTITIES=('action_sha256','physical_sha256','mode_sha256','canonical_master_sha256','b_sha256')
RECORDS=ROOT/'docs/task042_neural_coarse_inverse/outcomes/records'


def require(ok,message):
    if not ok:raise ValueError(message)


def ratio(a,b):return float(a/b) if b else (0. if not a else None)


def near(a,b,scale,limit=1e-11):
    value=ratio(float(np.linalg.norm(a-b)),float(scale))
    require(value is not None and value<=limit,'cached vector identity exceeds '+str(limit))
    return value


def numeric(row,a,r,W9,cached_c9,cached_e9,ids,*,qj,state=None):
    """Recompute certificates solely from fixed saved arrays and upstream caches."""
    n=len(r);bn=row['full_b_norm'];eps=np.finfo(float).eps
    require(set(row['gates'])==GATES and all(v is True for v in row['gates'].values()),'missing/failed numeric gates')
    for k in ('full_b_norm','residual_norm','eta9','eta10','h_norm','ad_norm','h_operation_scale','h_roundoff_floor','QR_relative','orthogonality_relative','stationarity_operation_relative'):
        require(isinstance(row[k],(int,float)) and np.isfinite(row[k]) and row[k]>=0,'nonfinite/negative scalar '+k)
    require(bn>0 and np.linalg.norm(r)>0,'positive physical normalization')
    shapes={k:(n,) for k in ('direction','image','innovation','old_e9','diagnostic_residual','original_combination_image','original_baseline_image','input_residual','w','aw','feedback','feedback_image','return_direction','return_image')}
    shapes.update(coefficients=(10,),baseline_coefficients=(9,),projection_coefficients=(9,))
    for k,shape in shapes.items():require(a[k].shape==shape and np.isfinite(a[k]).all(),'member shape/finite '+k)
    require(np.isfinite(W9).all() and W9.shape==(n,9),'qualified nine response shape')
    flow_certificates(row,a,r,qj,ids,W9)
    if state is not None:state_certificate(row,a,state,n)
    norms=np.linalg.norm(W9,axis=0);require(np.all(norms>0),'qualified nine nonzero columns')
    ad=a['image'];h=a['innovation'];c9=a['baseline_coefficients'];coef=a['coefficients'];rn=float(np.linalg.norm(r))
    an=float(np.linalg.norm(ad));hn=float(np.linalg.norm(h));floor=64*eps*row['h_operation_scale']
    W=np.column_stack((W9/norms,ad/an)) if an else W9/norms
    Z,R=a['thin_Q'],a['thin_R'];k=W.shape[1]
    require(Z.shape==(n,k) and R.shape==(k,k) and np.isfinite(Z).all() and np.isfinite(R).all(),'saved thin certificate inventory')
    qrerr=near(Z@R,W,np.linalg.norm(W),1e-10)
    orth=near(Z.conj().T@Z,np.eye(k),np.sqrt(k),1e-10)
    # Existing nine-dimensional certificate, no new rank factorization.
    require(row['driver']=='gelsd' and row['rank_threshold']==1e-12 and isinstance(row['rank'],int) and 9<=row['rank']<=k,'fixed driver/rank policy')
    sv=np.asarray(row['singular_values']);require(sv.shape==(k,) and np.isfinite(sv).all() and np.all(sv>=0) and np.all(np.diff(sv)<=0),'saved rank values')
    require(row['rank']==int(np.count_nonzero(sv>1e-12*sv[0])),'rank threshold count')
    near(ad-h,W9@a['projection_coefficients'],row['h_operation_scale'],1e-10)
    near(W9.conj().T@h,np.zeros(9),np.linalg.norm(W9)*row['h_operation_scale'],1e-10)
    resolved=bool(an>0 and hn>floor and hn/an>1e-12 and row['rank']==10)
    require(row['new_direction_resolved'] is resolved,'innovation resolution differs')
    e9=r-W9@c9;thin=r-W9@coef[:9]-coef[9]*ad;e10=r-a['original_combination_image']
    near(a['input_residual'],r,bn);near(e9,a['old_e9'],bn);near(e9,cached_e9,bn)
    near(W9@(c9-cached_c9),np.zeros(n),bn);near(a['original_baseline_image'],W9@c9,bn)
    near(e10,a['diagnostic_residual'],bn);err=float(np.linalg.norm(e10-thin));near(e10,thin,bn)
    oldscale=np.asarray(row['old_operation_scales']);require(oldscale.shape==(9,) and np.isfinite(oldscale).all() and np.all(oldscale>=0),'original action operand scale inventory')
    op=float(abs(coef[:9])@oldscale+abs(coef[9])*row['h_operation_scale'])
    require(ratio(err,op) is not None and ratio(err,op)<=1e-10,'original recombination operation scale')
    qualified=W if resolved else W[:,:9]
    station=ratio(float(np.linalg.norm(qualified.conj().T@thin)),float(np.linalg.norm(qualified)*(rn+np.linalg.norm(r-thin))))
    base_station=ratio(float(np.linalg.norm((W9/norms).conj().T@e9)),float(np.linalg.norm(W9/norms)*(rn+np.linalg.norm(r-e9))))
    require(station<=1e-8 and base_station<=1e-8,'actual baseline/new stationarity')
    eta9=float(np.linalg.norm(e9)/rn);eta10=float(np.linalg.norm(e10)/rn);g=None if eta9==0 else eta10/eta9
    for name,value in [('eta9',eta9),('eta10',eta10),('h_norm',hn),('ad_norm',an),('h_roundoff_floor',floor),('QR_relative',qrerr),('orthogonality_relative',orth),('stationarity_operation_relative',station)]:
        require(abs(row[name]-value)<=1e-11*max(1.,abs(value)),'recomputed metric '+name)
    require(row['g10'] is None if g is None else row['g10'] is not None and np.isfinite(row['g10']) and abs(row['g10']-g)<=1e-11,'g/null identity')
    require(eta10<=eta9+1e-10,'true inequality')
    if not resolved:require(coef[9]==0,'unresolved innovation must not use huge beta')
    # A resolved column with beta==0 is an entirely legal negative result.
    near(a['direction'],-a['w']+a['feedback'],np.linalg.norm(a['w'])+np.linalg.norm(a['feedback']),1e-10)
    near(a['image'],a['feedback_image']-a['aw'],row['h_operation_scale'],1e-10)
    near(a['return_image'],W9[:,-1]+ad,np.linalg.norm(W9[:,-1])+row['h_operation_scale'],1e-10)
    near(ad[ids],np.zeros(len(ids)),row['h_operation_scale'],1e-10)
    near(a['return_image'][ids],r[ids],np.linalg.norm(r)+row['h_operation_scale'],1e-10)
    masks=[np.isin(np.arange(n),ids),~np.isin(np.arange(n),ids)]
    for label,mask in zip(('inside_J','outside_J'),masks):
        for name,v in [('qj_response_norm',W9[:,-1]),('d_response_norm',ad),('return_response_norm',a['return_image']),('old_e9_norm',e9),('new_e10_norm',e10)]:
            value=float(np.linalg.norm(v[mask]));require(abs(row['regions'][label][name]-value)<=1e-11*max(1.,value),'region norm identity')
    require(row['trustworthy'] is True,'untrusted result')
    return dict(name=row['name'],trustworthy=True,new_direction_resolved=resolved,eta9=eta9,eta10=eta10,g10=g,
        beta=dict(real=float(coef[9].real),imag=float(coef[9].imag)),baseline_stationarity=base_station,
        stationarity=station,QR_relative=qrerr,orthogonality_relative=orth,
        beta_zero_legal=bool(coef[9]==0),classification='SOLVED_BASELINE' if eta9==0 else 'RESOLVED' if resolved else 'REDUNDANT_OR_UNRESOLVED')


def inventory(result,plan,*,sources,ledger,manifest):
    rows=result['rows'];items=plan['states']
    require(len(rows)==len(items)==2 and {x.get('name') for x in rows}==set(NAMES) and {x.get('name') for x in items}==set(NAMES),'fixed two unique named inventory')
    counts=result['budget_counts'];require(set(counts)==set(CAPS),'exact budget inventory')
    require(all(type(counts[k]) is int and 0<=counts[k]<=cap for k,cap in CAPS.items()),'finite integer/cap budget')
    ac=result['action_counts'];require(set(ac)=={'S','SH','audit'} and all(type(v) is int and v>=0 for v in ac.values()) and ac['audit']==0 and ac['S']+ac['SH']==counts['actions'],'original action accounting')
    require(counts['factor_readers']==7 and counts['outer_lu_solve']==24 and counts['joint_lu_solve']==4 and counts['explicit_triangular_pass']==56 and counts['thin_decompositions']==2 and counts['port_factors']==1,'complete fixed actor inventory')
    require(result['status']=='DIAGNOSTIC_COMPLETE' and not result['reference_arrays_read'] and not result['Q_U_R_D_L_loaded'] and result['new_solver_states']==0 and not result['global_p4_factor_constructed'],'result not complete or forbidden data')
    require(result['operator_identity']=={k:plan[k] for k in IDENTITIES} and result['operator_packet']['sha256']==plan['action_sha256'] and result['complete_ports']==40,'full original identity')
    require(len(result['source_sha'])==40 and all(x in '0123456789abcdef' for x in result['source_sha']),'real source SHA')
    complete_consumption(result,plan,sources,ledger,manifest)
    by_name={x['name']:x for x in rows}
    for item in items:
        row=by_name[item['name']]
        for src,dst in [('parent_result','parent_result'),('state','input_state'),('v25_arrays','v25_arrays'),('v26_arrays','v26_arrays')]:
            require(bool(item[src]) and row[dst]==item[src],'named parent/cache binding '+src)
        require(bool(row['parent_result']['path']) and len(row['parent_result']['sha256'])==64,'nonempty parent_result')
    return by_name


def load_members(receipt,keys,allowed):
    path=Path(receipt['path']).resolve();require(path.is_relative_to(allowed) and file_hash(path)==receipt['sha256'],'container path/hash')
    with np.load(path,allow_pickle=False) as f:out={k:np.array(f[k]) for k in keys}
    for k,v in out.items():require(np.isfinite(v).all() and array_hash(v)==receipt[k+'_sha256'],'saved member hash/finite '+k)
    return out


def classify(rows):
    if all(x['new_direction_resolved'] and x['g10'] is not None and x['g10']<=.75 for x in rows):return 'RETURN_EXTRA_DIRECTION_SIGNAL'
    if all(not x['new_direction_resolved'] for x in rows):return 'REDUNDANT_OR_UNRESOLVED'
    if all(x['g10'] is not None and x['g10']>=.95 for x in rows):return 'FIXED_RETURN_DIRECTION_INSUFFICIENT'
    return 'STATE_DEPENDENT_INCONCLUSIVE'


def compact_inputs(plan):
    return [dict(name=x['name'],parent_result=x['parent_result'],state=x['state'],v25_arrays=x['v25_arrays'],v26_arrays=x['v26_arrays']) for x in plan['states']]


def collect(*,root=ROOT,plan_path=None,artifact_root=None,records=None,ledger_path=None,nt=18144,old_plan=None,batch='v28'):
    """Paths/dimensions are explicit for isolated fixtures; defaults stay V28.

    Every complete result must bind independent durable files, not embedded labels.
    Neither this function nor its fixtures admit or reopen a numerical window.
    """
    if batch not in ('v28','v31','v32'):raise ValueError('unapproved return checker namespace')
    if batch=='v32':
        from src.io import return_block_v32 as io
    elif batch=='v31':
        from src.io import return_block_v31 as io
    else:
        from src.io import return_block_continuation as io
    root=Path(root).resolve();plan_path=Path(plan_path or io.PLAN_PATH).resolve()
    artifact_root=Path(artifact_root or io.ARTIFACT_ROOT).resolve();records=Path(records or RECORDS).resolve()
    plan=json.loads(plan_path.read_text());inputs=compact_inputs(plan)
    # The collector owns the destination. The fixture deliberately supplies a
    # fresh directory; the shared atomic writer retains its existing contract.
    records.mkdir(parents=True,exist_ok=True)
    write_json(records/('input_inventory_'+batch+'.json'),dict(pre_registration=dict(path=str(plan_path),sha256=file_hash(plan_path)),states=inputs,
        prior_V27_null_corrections=[dict(name=x['name'],old_parent=None,correct_parent_result=x['parent_result'],old_files=['input_inventory_v27.json','return_direction_results_v27.json']) for x in inputs]))
    pointer=artifact_root/'DIAGNOSTIC.json'
    if not pointer.exists():
        out=dict(status='NOT_RUN',actual_numeric_source=None,rows=[dict(name=x['name'],parent_result=x['parent_result'],eta10=None,g10=None,status='NOT_RUN') for x in inputs],
            checker_scope='no actual arrays; no numerical PASS claimed',checker_source_sha256=file_hash(Path(__file__)))
    else:
        idx=json.loads(pointer.read_text());result=io.checked_json(idx,artifact_root)
        if result['status']!='DIAGNOSTIC_COMPLETE':
            out=dict(status='PARTIAL_UNRESOLVED',raw=idx,actual_numeric_source=result.get('source_sha'),
                rows=[dict(name=x['name'],eta10=None,g10=None,status='NOT_QUALIFIED') for x in inputs],
                reason='actor not complete; no numerical CHECKED classification')
            write_json(records/('return_direction_checker_'+batch+'.json'),out)
            write_json(records/('return_direction_results_'+batch+'.json'),out)
            return out
        require(result['plan_sha256']==file_hash(plan_path),'actual pre-registration')
        prior=io.checked_json(plan['v26_result'],root/'benchmarks/artifacts/task042/v26')
        old=io.checked_json(plan['v25_result'],root/'benchmarks/artifacts/task042/v25')
        from benchmarks.collect_task042_block_direction import fixed_inventory
        oldrows={x['name']:x for x in fixed_inventory(old,old_plan,root=root)}
        require(prior['source_sha']==plan['v26_source_sha'] and old['source_sha']==plan['v25_source_sha'],'cache source identity')
        require(len(prior['rows'])==2 and {x['name'] for x in prior['rows']}==set(NAMES),'nine inventory')
        priorrows={x['name']:x for x in prior['rows']}
        setup=io.checked_json(plan['local_setup'],root/'benchmarks/artifacts/task042/v24')
        sources=factor_sources(setup,prior,plan)
        manifest=io.checked_json(result['run_manifest'],root/'results/task042')
        lp=Path(ledger_path or result['ledger_path']).resolve()
        require(lp.is_relative_to(root/'tmp/task042'),'durable ledger path outside task namespace')
        ledger=json.loads(lp.read_text())
        rows=inventory(result,plan,sources=sources,ledger=ledger,manifest=manifest)
        ids=np.sort(np.r_[setup['block_inventory'][5]['rows'],setup['block_inventory'][7]['rows']]).astype(np.int64)
        require(array_hash(ids)==plan['joint_rows_sha256'],'J row identity')
        checked=[]
        for item in plan['states']:
            row=rows[item['name']];p=priorrows[item['name']]
            require(oldrows[item['name']]['diagnostic_arrays']==item['v25_arrays'] and
                row['old_operation_scales'][:8]==oldrows[item['name']]['operation_scales'],
                'V25 original operand scale/cache provenance')
            require(p['input_state']==item['state'] and p['diagnostic_arrays']==item['v26_arrays'] and p['old_direction_arrays']==item['v25_arrays'] and p['trustworthy'] and p['new_direction_resolved'] and p['rank']==9 and all(p['gates'].values()),'qualified V26 original nine baseline')
            require(row['full_b_norm']==p['full_b_norm'],'original b denominator')
            parent=io.checked_json(item['parent_result'],root/'benchmarks/artifacts/task042/v24')
            require(parent['source_sha']==plan['upstream_source_sha'] and parent['operator_packet']['sha256']==plan['action_sha256'] and parent['cycles'][3]['state']==item['state'],'V24 exact parent/state')
            cached=load_members(item['v26_arrays'],('joint_direction','joint_image','coefficients','diagnostic_residual'),root/'benchmarks/artifacts/task042/v26')
            olda=load_members(item['v25_arrays'],('images',),root/'benchmarks/artifacts/task042/v25')
            state=load_members(item['state'],('trace','port','z','residual'),root/'benchmarks/artifacts/task042/v24')
            receipt=row['diagnostic_arrays'];require(bool(receipt),'missing new raw arrays')
            path=Path(receipt['path'])
            with np.load(path,allow_pickle=False) as f:keys=f.files
            a=load_members(receipt,keys,artifact_root)
            W9=np.column_stack((olda['images'],cached['joint_image']))
            require(row['operator_action_sha256']==plan['action_sha256'],'scale original action binding')
            checked.append(numeric(row,a,state['residual'][:nt],W9,cached['coefficients'],cached['diagnostic_residual'],ids,
                qj=cached['joint_direction'],state=state))
        out=dict(status='CHECKED',decision=classify(checked),rows=checked,actual_numeric_source=result['source_sha'],raw=idx,
            no_new_actions=True,no_factor_reads=True,no_QR_SVD=True,checker_source_sha256=file_hash(Path(__file__)))
        require(out['decision']==result['decision'],'independent decision differs')
    write_json(records/('return_direction_checker_'+batch+'.json'),out)
    write_json(records/('return_direction_results_'+batch+'.json'),out)
    return out


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--batch',choices=('v28','v31','v32'),default='v28')
    print(json.dumps(collect(batch=parser.parse_args().batch),ensure_ascii=False))
