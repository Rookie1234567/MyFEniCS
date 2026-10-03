"""Compact V25 evidence and independent cached-array checks; no new action/LS."""
import csv,json
from pathlib import Path

import numpy as np

from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import file_hash,array_hash
from src.runners.task042_shared import write_json

RECORDS=ROOT/'docs/task042_neural_coarse_inverse/outcomes/records'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v25'


def fixed_inventory(result,plan=None):
    """Reject an incomplete, mislabeled or unbound inventory before any arrays."""
    from src.io.block_direction_diagnostic import NAMES,PLAN_PATH,checked_json
    plan=json.loads(PLAN_PATH.read_text()) if plan is None else plan
    items=plan['states'];rows=result['rows']
    if (len(items)!=3 or {x['name'] for x in items}!=set(NAMES)
            or len(rows)!=3 or {x.get('name') for x in rows}!=set(NAMES)):
        raise ValueError('fixed three-state inventory missing/duplicate/wrong name')
    by_name={x['name']:x for x in rows}
    for item in items:
        row=by_name[item['name']]
        if row['input_state']!=item['state']:
            raise ValueError('fixed state path/container/member identity differs')
        parent=checked_json(item['parent_result'],ROOT/'benchmarks/artifacts/task042/v24')
        if (parent['source_sha']!=plan['upstream_source_sha']
                or parent['operator_packet']['sha256']!=plan['action_sha256']):
            raise ValueError('fixed parent source/operator identity differs')
        selected=parent['start'] if item['name'].endswith('INITIAL') else parent['cycles'][3]
        if selected['state']!=item['state']:
            raise ValueError('fixed parent/state binding differs')
        expected_gates={'diagonal','recombination','qr','stationarity','inequality',
            'numerical_full_direction_rank','columns_resolved','whole_response_resolved'}
        if (set(row['gates'])!=expected_gates or not all(x is True for x in row['gates'].values())
                or row['rank']!=8 or row['status']!='DIAGNOSTIC_COMPLETE'):
            raise ValueError('missing/failed numerical gates or rank')
        scalar_keys=('eta_unit','eta1','eta8','residual_norm','full_physical_b_norm',
            'QR_relative','orthogonality_relative','stationarity_operation_relative')
        if any(not np.isfinite(row[k]) or row[k]<0 for k in scalar_keys):
            raise ValueError('nonfinite/negative diagnostic metric')
        if (row['QR_relative']>1e-10 or row['orthogonality_relative']>1e-10
                or row['stationarity_operation_relative']>1e-8
                or row['residual_norm']==0 or row['full_physical_b_norm']==0):
            raise ValueError('numerical identity evidence unsafe')
        if (set(row['independent_recombination'])!={'unit','best'}
                or len(row['diagonal_witnesses'])!=8):
            raise ValueError('missing recombination/diagonal evidence')
    return [by_name[name] for name in NAMES]


def pointer(path):
    path=Path(path).resolve()
    return dict(path=str(path),sha256=file_hash(path),bytes=path.stat().st_size)


def csv_write(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)


def check_arrays(result,plan=None):
    """Recompute eta and block cross identities without another QR/SVD or S."""
    ordered=fixed_inventory(result,plan)
    setup_item=(json.loads((ROOT/'input/task042_neural_coarse_inverse/block_residual_direction_v25.json').read_text()) if plan is None else plan)['local_setup']
    assert file_hash(setup_item['path'])==setup_item['sha256']
    setup=json.loads(Path(setup_item['path']).read_text())
    groups=[np.asarray(x['rows'],np.int64) for x in setup['block_inventory']]
    checks=[]
    for row in ordered:
        item=row['input_state'];assert file_hash(item['path'])==item['sha256']
        with np.load(item['path'],allow_pickle=False) as f:rfull=np.array(f['residual'])
        assert array_hash(rfull)==item['residual_sha256']
        r=rfull[:18144];nr=np.linalg.norm(r)
        receipt=row['diagnostic_arrays'];assert file_hash(receipt['path'])==receipt['sha256']
        with np.load(receipt['path'],allow_pickle=False) as f:
            data={k:np.array(f[k]) for k in ('directions','images','coefficients','local_q','diagnostic_residual')}
        for key,value in data.items():
            assert np.isfinite(value).all() and array_hash(value)==receipt[key+'_sha256']
        V,q,c=data['images'],data['directions'],data['coefficients'];v=V.sum(axis=1)
        assert V.shape==q.shape==(18144,8) and c.shape==(8,)
        alpha=np.vdot(v,r)/np.vdot(v,v)
        metrics=dict(eta_unit=float(np.linalg.norm(r-v)/nr),eta1=float(np.linalg.norm(r-alpha*v)/nr),eta8=float(np.linalg.norm(r-V@c)/nr))
        for key,value in metrics.items():assert abs(value-row[key])<=1e-11,(row['name'],key)
        assert metrics['eta8']<=metrics['eta1']+1e-10 and metrics['eta1']<=min(1.,metrics['eta_unit'])+1e-10
        np.testing.assert_allclose(q.sum(axis=1),data['local_q'],rtol=0,atol=0)
        norms=np.linalg.norm(V,axis=0)
        W=V/norms
        station=float(np.linalg.norm(W.conj().T@(r-V@c))/(np.linalg.norm(W)*(nr+np.linalg.norm(V@c))))
        assert station<=1e-8 and row['rank']==8
        assert min(row['singular_values'])/max(row['singular_values'])>=1e-12
        error=np.linalg.norm(data['diagnostic_residual']-(r-V@c))
        assert error/row['full_physical_b_norm']<=1e-11
        assert all(v['full_b_relative']<=1e-11 and v['operation_relative']<=1e-10 for v in row['independent_recombination'].values())
        assert all(w['operation_relative']<=1e-10 for w in row['diagonal_witnesses'])
        for j,ids in enumerate(groups):
            outside=np.setdiff1d(np.arange(18144),ids)
            assert np.count_nonzero(q[outside,j])==0
            X=V[ids];cross=X.conj().T@X
            stored=np.array([[complex(v['real'],v['imag']) for v in line] for line in row['block_response'][j]['complex_cross_products']])
            np.testing.assert_allclose(cross,stored,rtol=1e-12,atol=1e-24)
            assert row['block_response'][j]['cross_square_identity_operation_relative']<=1e-10
        checks.append(dict(name=row['name'],**metrics,stationarity_recomputed=station,
            true_vs_thin_saved_difference_full_b_relative=float(error/row['full_physical_b_norm']),
            independent_cached_array_checks=True,no_new_action=True,no_new_decomposition=True))
    by_name={x['name']:x for x in checks}
    finals=[by_name[name] for name in ('V24-LZ-CYCLE4','V24-LCZ-CYCLE4')]
    decision='EIGHT_DIRECTIONS_WEAK' if all(x['eta8']>=.9 for x in finals) else 'OTHER_PREDECLARED_BRANCH'
    assert decision==result['decision']
    assert result['action_counts']['S']+result['action_counts']['SH']==39<=64
    counts=result['budget_counts']
    for key,cap in dict(L8=3,local_lu_solve=96,local_triangular_pass=192,factor_readers=2,thin_decompositions=3).items():assert counts[key]<=cap
    assert counts['local_lu_solve']==40 and counts['local_triangular_pass']==80
    assert not result['reference_arrays_read'] and not result['Q_U_R_D_L_loaded'] and result['new_solver_states']==0
    return dict(status='CHECKED',rows=checks,decision=decision,raw_flags_not_sufficient=True,
        scope='cached directions/images/scalars only; no new S, QR, SVD, factor or field integration')


def collect():
    index=json.loads((ARTIFACT/'DIAGNOSTIC.json').read_text());assert file_hash(index['path'])==index['sha256']
    result=json.loads(Path(index['path']).read_text());result_dir=Path(index['path']).parent
    run=ROOT/'results/task042'/result_dir.name
    checked=check_arrays(result)
    write_json(RECORDS/'cached_array_checker_v25.json',checked)
    metric_rows=[];responses=[];crosses=[];target_rows=[];gates=[]
    for row in result['rows']:
        metric_rows.append(dict(state=row['name'],status=row['status'],eta_unit=row['eta_unit'],eta1=row['eta1'],eta8=row['eta8'],
            reduction_fraction=1-row['eta8'],squared_residual_fraction_covered=1-row['eta8']**2,rank=row['rank'],
            alpha_real=row['alpha']['real'],alpha_imag=row['alpha']['imag'],coefficient_norm=row['coefficient_norm'],
            residual_norm=row['residual_norm'],full_b_norm=row['full_physical_b_norm'],diagnostic_seconds=row['diagnostic_seconds'],
            decomposition_seconds=row['decomposition_seconds'],source_sha=result['source_sha'],classification='offline diagnostic; not solver_pass'))
        gates.append({k:row[k] for k in ('name','status','gates','coefficients','response_column_norms','operation_scales','roundoff_floors','resolved_columns',
            'singular_values','rank','rank_threshold','driver','QR_relative','orthogonality_relative','stationarity_operation_relative',
            'identity','diagonal_witnesses','independent_recombination','diagnostic_arrays')})
        for target in row['block_response']:
            i=target['target_block']
            target_rows.append(dict(state=row['name'],target_block=i,coherent_norm=target['coherent_sum_norm'],
                individual_squared_sum=target['sum_individual_norm_sq'],twice_real_cross_sum=target['twice_real_cross_sum'],
                cancellation_ratio=target['cancellation_ratio'],square_identity_relative=target['cross_square_identity_operation_relative'],
                target_r_norm=target['original_target_residual_norm']))
            for j,norm in enumerate(target['response_norms']):
                responses.append(dict(state=row['name'],target_block=i,source_block=j,response_norm=norm,
                    response_over_full_b=norm/row['full_physical_b_norm'],response_over_current_r=norm/row['residual_norm'],
                    response_over_source_full_image=norm/row['response_column_norms'][j]))
                for k in range(j,8):
                    value=target['complex_cross_products'][j][k]
                    crosses.append(dict(state=row['name'],target_block=i,source_j=j,source_k=k,
                        cross_real=value['real'],cross_imag=value['imag']))
    for name,rows in [('direction_metrics',metric_rows),('block_response',responses),('target_coherence',target_rows),('complex_cross_terms',crosses)]:csv_write(RECORDS/(name+'_v25.csv'),rows)
    write_json(RECORDS/'numerical_gates_v25.json',dict(rows=gates,decision=result['decision'],cross_table='upper triangle; lower = complex conjugate',
        response_axes='target block i, source local direction j; 0-based canonical geometric labels',neural_20percent_increment='NOT_DEMONSTRATED'))
    setup=json.loads(Path(json.loads((ROOT/'input/task042_neural_coarse_inverse/block_residual_direction_v25.json').read_text())['local_setup']['path']).read_text())
    write_json(RECORDS/'input_inventory_v25.json',dict(pre_registration=pointer(ROOT/'input/task042_neural_coarse_inverse/block_residual_direction_v25.json'),
        contents=json.loads((ROOT/'input/task042_neural_coarse_inverse/block_residual_direction_v25.json').read_text()),
        local_factor_files=[dict(block=v['block'],row_count=len(v['rows']),**{k:v[k] for k in ('matrix','LU','pivots')}) for v in setup['block_inventory']],
        new_arrays=[row['diagnostic_arrays'] for row in result['rows']],forbidden_array_read=False))
    files={name:pointer(run/name) for name in ('source_sha.txt','input_original.dat','input_sha256.txt','physical_model_sha256.txt',
        'resolved_config.json','run_manifest.json','run_summary.json','resource_baseline.json','supervision/summary.json','supervision/resources.jsonl','supervision/worker.log')}
    write_json(RECORDS/'run_index_v25.json',dict(stage='V25-DIAGNOSTIC',actual_source_sha=result['source_sha'],result=index,files=files,
        row_artifacts=[dict(name=r['name'],metadata=pointer(result_dir/(r['name']+'.json')),arrays=r['diagnostic_arrays']) for r in result['rows']],
        solver_results=0,formal_FE=0,neural_training=0))
    print(json.dumps(dict(status='COLLECTED',decision=result['decision'],metrics=metric_rows),ensure_ascii=False))


if __name__=='__main__':collect()
