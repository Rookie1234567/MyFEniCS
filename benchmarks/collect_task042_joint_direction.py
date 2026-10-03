"""Read fixed saved evidence only; no operator, factor reader or decomposition."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np

from src.io import joint_block_diagnostic as io
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.joint_block_window import CAPS
from src.solvers.joint_block_study import cached_directions
from benchmarks.collect_task042_block_direction import fixed_inventory,check_arrays,csv_write,pointer

RECORDS=io.ROOT/'docs/task042_neural_coarse_inverse/outcomes/records'


def require(condition,message):
    if not condition:raise ValueError(message)


def read_result():
    item=json.loads((io.ARTIFACT_ROOT/'DIAGNOSTIC.json').read_text())
    return io.checked_json(item,io.ARTIFACT_ROOT),item


def verify_cached(result,plan=None):
    plan=json.loads(io.PLAN_PATH.read_text()) if plan is None else plan
    rows=result['rows'];names=io.NAMES
    require(len(rows)==2 and {x.get('name') for x in rows}==set(names),'fixed two unique cold samples required')
    require(result['operator_packet']['sha256']==plan['action_sha256'] and result['complete_ports']==40,'original operator inventory')
    require(result['joint_rows']==3888 and result['joint_blocks']==[5,7],'joint scope')
    require(not result['reference_arrays_read'] and not result['Q_U_R_D_L_loaded'] and not result['old_eight_LU_loaded'] and result['new_solver_states']==0,'forbidden data or new solver state')
    counts=result['budget_counts']
    require(set(counts)==set(CAPS) and all(0<=counts[k]<=cap for k,cap in CAPS.items()),'cumulative numerical caps')
    require(counts['actions']==result['action_counts']['S']+result['action_counts']['SH'],'original action count')
    require(counts['joint_LU_attempts']==counts['joint_assemblies']==1 and counts['thin_decompositions']==2,'unique matrix/factor and two workflows')
    old=io.checked_json(plan['v25_result'],io.ROOT/'benchmarks/artifacts/task042/v25')
    old_rows={x['name']:x for x in fixed_inventory(old)}
    setup=io.checked_json(plan['local_setup'],io.ROOT/'benchmarks/artifacts/task042/v24')
    ids=np.sort(np.r_[setup['block_inventory'][5]['rows'],setup['block_inventory'][7]['rows']]).astype(np.int64)
    require(array_hash(ids)==plan['joint_rows_sha256'] and len(ids)==3888,'joint canonical row hash')
    support=np.zeros(18144,bool);support[ids]=True
    by_name={x['name']:x for x in rows};checked=[]
    for item in plan['states']:
        row=by_name[item['name']];name=item['name']
        require(row['input_state']==item['state'] and row['old_direction_arrays']==item['v25_arrays'],'named parent/cache identity')
        require(row['input_state']==old_rows[name]['input_state'],'same consumed cold state')
        require(set(row['gates'])=={'cached_eta8_identity','control','QR','stationarity','recombination','local_solve','outside_J_zero','inequality'} and all(v is True for v in row['gates'].values()),'failed or missing numerical witnesses')
        for key in ('eta8','eta9','g','h_norm','vj_norm','h_e8_coherence','QR_relative','orthogonality_relative','stationarity_operation_relative'):
            require(np.isfinite(row[key]) and row[key]>=0,'nonfinite/negative metric '+key)
        require(row['QR_relative']<=1e-10 and row['orthogonality_relative']<=1e-10 and row['stationarity_operation_relative']<=1e-8,'unsafe thin algebra')
        pair=row['independent_recombination']
        require(all(np.isfinite(pair[k]) and 0<=pair[k]<=limit for k,limit in [('full_b_relative',1e-11),('operation_relative',1e-10)]),'missing or unsafe original recombination')
        values=io.physical_state(item,SimpleNamespace(nt=18144,np=40,size=18184));r=values['residual'][:18144];nr=float(np.linalg.norm(r))
        data=cached_directions(item['v25_arrays'],18144);receipt=row['diagnostic_arrays'];p=Path(receipt['path']).resolve()
        require(p.is_relative_to(io.ARTIFACT_ROOT) and file_hash(p)==receipt['sha256'],'new evidence path/hash')
        with np.load(p,allow_pickle=False) as f:arrays={k:np.array(f[k]) for k in ('joint_direction','joint_image','innovation','coefficients','old_e8','diagnostic_residual')}
        for key,value in arrays.items():
            require(np.isfinite(value).all() and array_hash(value)==receipt[key+'_sha256'],'new member hash/finite '+key)
            require(value.shape==((9,) if key=='coefficients' else (18144,)),'new member shape '+key)
        V=data['images'];qj=arrays['joint_direction'];vj=arrays['joint_image'];h=arrays['innovation'];coef=arrays['coefficients']
        e8=r-V@data['coefficients'];thin=r-V@coef[:8]-coef[8]*vj;actual=arrays['diagnostic_residual']
        require(nr>0 and np.count_nonzero(qj[~support])==0,'support and nonzero residual')
        norms=np.linalg.norm(V,axis=0);require(np.all(norms>0),'qualified old column norms')
        W=np.column_stack((V/norms,vj/np.linalg.norm(vj)))
        eta8=float(np.linalg.norm(e8)/nr);eta9=float(np.linalg.norm(actual)/nr);g=eta9/eta8
        require(abs(eta8-row['eta8'])<=1e-11 and abs(eta9-row['eta9'])<=1e-11 and abs(g-row['g'])<=1e-11,'actual eta/g differs')
        require(np.linalg.norm(actual-thin)/row['full_b_norm']<=1e-11 and eta9<=eta8+1e-10,'saved original response differs from thin prediction')
        require(np.linalg.norm(e8-arrays['old_e8'])/row['full_b_norm']<=1e-11,'cached eight residual differs')
        perp=float(np.linalg.norm((V/norms).conj().T@h)/(np.linalg.norm(h)*np.sqrt(8)))
        require(perp<=1e-10 and coef[8]!=0,'new resolved innovation certificate')
        # At a stationary nine-column point, old_c-new_c = gamma*projection_c.
        # This checks the saved projection without a fresh QR, SVD or normal solve.
        projection=V@((data['coefficients']-coef[:8])/coef[8])
        span_difference=float(np.linalg.norm(vj-h-projection)/np.linalg.norm(vj))
        require(span_difference<=1e-10,'innovation and old-space part do not reconstruct')
        station=float(np.linalg.norm(W.conj().T@thin)/(np.linalg.norm(W)*(nr+np.linalg.norm(r-thin))))
        require(station<=1e-8,'recomputed stationarity fails')
        coherence=float(abs(np.vdot(h,e8))/(np.linalg.norm(h)*np.linalg.norm(e8)))
        require(abs(coherence-row['h_e8_coherence'])<=1e-10 and abs(coherence**2-(1-g*g))<=1e-10,'innovation reduction identity')
        require(np.linalg.norm(h)>row['h_roundoff_floor'] and np.linalg.norm(h)/np.linalg.norm(vj)>1e-12 and row['rank']==9,'new direction unresolved')
        checked.append(dict(name=name,eta8=eta8,eta9=eta9,g=g,h_e8_coherence=coherence,
            conditional_squared_fraction_removed=1-g*g,norm_reduction_relative_to_e8=1-g,
            innovation_orthogonal_operation_relative=perp,innovation_span_identity_relative=span_difference,
            stationarity_recomputed=station,actual_saved_response_thin_full_b_difference=float(np.linalg.norm(actual-thin)/row['full_b_norm']),
            rank_role='old qualified eight plus independently certified nonzero orthogonal innovation',
            no_new_action=True,no_new_decomposition=True,no_factor_reader=True))
    decision=('JOINT_EXTRA_DIRECTION_SIGNAL' if all(x['g']<=.75 for x in checked) else
              'FIXED_JOINT_DIRECTION_INSUFFICIENT' if all(x['g']>=.95 for x in checked) else 'STATE_DEPENDENT_INCONCLUSIVE')
    require(decision==result['decision'],'pre-registered decision differs')
    return dict(status='CHECKED',rows=checked,decision=decision,raw_status_not_sufficient=True,
                scope='fixed saved arrays/hash-bound original witnesses; no new S/SH/LU/QR/SVD/field')


def collect():
    result,index=read_result();checked=verify_cached(result);RECORDS.mkdir(exist_ok=True)
    write_json(RECORDS/'cached_array_checker_v26.json',checked)
    old=io.checked_json(json.loads(io.PLAN_PATH.read_text())['v25_result'],io.ROOT/'benchmarks/artifacts/task042/v25')
    write_json(RECORDS/'fixed_inventory_checker_v26.json',check_arrays(old))
    metrics=[{k:x[k] for k in ('name','eta8','eta9','g','h_e8_coherence','conditional_squared_fraction_removed','norm_reduction_relative_to_e8')} for x in checked['rows']]
    csv_write(RECORDS/'direction_metrics_v26.csv',metrics)
    write_json(RECORDS/'joint_numerical_gates_v26.json',{k:result[k] for k in ('status','decision','source_sha','matrix','factor_inventory','factor_status','factor_safety','joint_checks','readonly_reload','old_diagonal_checks','bidirectional_coupling','capacity','assembly')})
    write_json(RECORDS/'extra_direction_gates_v26.json',dict(source_sha=result['source_sha'],rows=[{k:v for k,v in x.items() if k not in ('input_state','old_direction_arrays')} for x in result['rows']]))
    write_json(RECORDS/'input_inventory_v26.json',dict(pre_registration=pointer(io.PLAN_PATH),plan=json.loads(io.PLAN_PATH.read_text()),actual_input_sha256=result['input_sha256'],physical_identity=result['physical_identity'],operator_packet=result['operator_packet'],factor_receipts_bound_at_actor_reload=True,no_additional_factor_read=True))
    write_json(RECORDS/'raw_index_v26.json',dict(source_sha=result['source_sha'],raw=index,
        parent_namespace_readonly=True,arrays=[x['diagnostic_arrays'] for x in result['rows']],
        independent_checker_source=pointer(Path(__file__)),no_new_solver_states=True))
    print(json.dumps(checked,ensure_ascii=False))


if __name__=='__main__':collect()
