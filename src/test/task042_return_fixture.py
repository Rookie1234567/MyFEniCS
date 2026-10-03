"""Isolated synthetic complete packets; no production artifact or window read."""
from copy import deepcopy
from pathlib import Path
import json
import numpy as np
from src.solvers.joint_block_direction import pair
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.runners.task042_shared import write_json
from benchmarks.task042_return_certificates import BLOCKS,EXPECTED,factor_sources


def certify_flow(row,a,r,W9,ids):
    a.update(cached_joint_image=W9[:,-1],cached_joint_inner_image=r[ids])
    scales=dict(w=10.,d=10.,feedback=0.,qret=20.)
    def cert(vector,value):
        return dict(input_array_sha256=array_hash(vector),weights=[value],expanded_cell_norms=[1.],
            C_norm=0.,closed_port_norm=0.,value=value)
    row.update(operator_action_sha256='a'*64,action_operation_scales=scales,
        scale_provenance=dict(method='cell_S_expand_plus_C_port_bound',action_sha256='a'*64,
            scales=scales,old_scales=row['old_operation_scales'],qj=cert(W9[:,-1],row['old_operation_scales'][-1]),
            operands={key:cert(a[member],scales[key]) for key,member in
                      [('w','w'),('d','direction'),('feedback','feedback'),('qret','return_direction')]}),
        identity=dict(exact_trace_port_z_concat=True,homogeneous_direction=True,internal_particular_added=False,
            saved_trace_residual_full_b_relative=0.,saved_full_residual_full_b_relative=0.,
            port_reclosure_operation_relative=0.,port_residual_full_b_relative=0.),
        cached_original_pair=pair(W9[:,-1],W9[:,-1]),cached_joint_inner_pair=pair(r[ids],r[ids]),
        cancellation=dict(error_norm=float(np.linalg.norm(a['image'][ids])),operation_scale=10.,operation_relative=0.,
            original_rhs_inner_pair=pair(a['return_image'][ids],r[ids]),
            d_linearity=pair(a['image'],a['feedback_image']-a['aw']),
            return_linearity=pair(a['return_image'],W9[:,-1]+a['image']),
            pre_cancel_Aw_inner_norm=float(np.linalg.norm(a['aw'][ids])),
            pre_cancel_feedback_inner_norm=float(np.linalg.norm(a['feedback_image'][ids]))))


def certify_inventory(result,plan,sources=None):
    if sources is None:
        sources={str(b):dict(source_sha='d'*40,rows_sha256='c'*64,row_count=1,
            files={k:dict(path='/fixture/'+str(b)+'/'+k,sha256='b'*64,array_sha256='c'*64) for k in ('matrix','LU','pivots')}) for b in BLOCKS}
    factors=[]
    for b in BLOCKS:
        expected=sources[str(b)];seeds=(422601,422602) if b=='J' else (422401+2*b,422402+2*b)
        witnesses=[]
        for seed in seeds:
            w=dict(seed=seed,solve_relative=0.,solve_operation_relative=0.,solve_error_norm=0.,rhs_norm=1.,
                solve_operand_scale=2.,original_principal_action=pair(np.ones(1),np.ones(1)))
            if b=='J':w['original_adjoint_action']=pair(np.ones(1),np.ones(1))
            witnesses.append(w)
        factors.append(dict(block=b,source_sha=expected['source_sha'],rows_sha256=expected['rows_sha256'],
            row_count=expected['row_count'],solve_calls=4,RHS_columns=4,triangular_passes=8,qualified=True,refactored=False,
            witnesses=witnesses,files=[dict(key=k,path=v['path'],container_sha256=v['sha256'],array_sha256=v['array_sha256'],
                readonly=True,full_hash_copy=False,container_stream_hash_reads=1,numeric_mmap_loads=1,array_hash_scans=1)
                for k,v in expected['files'].items()]))
    result.update(factor_reloads=factors,port_rhs_inventory=[dict(adjoint=i<2,shape=[40],RHS_columns=1) for i in range(35)],
        run_directory='/fixture/run',input_sha256='e'*64,plan_sha256='f'*64)
    plan['fixture_sources']=sources
    result['fixture_manifest']=dict(source_sha=result['source_sha'],input_sha256=result['input_sha256'],
        plan_sha256=result['plan_sha256'],completed_budget_counts=deepcopy(EXPECTED),completed_action_counts=dict(S=34,SH=2,audit=0))
    result['fixture_ledger']=dict(active=None,charged=deepcopy(EXPECTED),runs=[dict(directory=result['run_directory'],
        source_sha=result['source_sha'],exact_counts=True,classification='COMPLETED',counts=deepcopy(EXPECTED),
        completed=deepcopy(EXPECTED),upper=deepcopy(EXPECTED))])


def json_receipt(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);write_json(path,value)
    return dict(path=str(path),sha256=file_hash(path))


def arrays_receipt(path,**arrays):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as stream:np.savez(stream,**arrays)
    return dict(path=str(path),sha256=file_hash(path),**{k+'_sha256':array_hash(v) for k,v in arrays.items()})


def complete_packet(root,kind='positive'):
    """Two synthetic parents; the collector creates the fresh records directory."""
    from src.test.test_task042_v28_cached_checker import fixture,inventory_fixture
    from src.io.block_direction_diagnostic import NAMES as OLD_NAMES
    from benchmarks.collect_task042_return_direction import classify
    from benchmarks.collect_task042_block_direction import fixed_inventory
    root=Path(root).resolve();art=root/'benchmarks/artifacts/task042';out=root/'records'
    result,plan=inventory_fixture();plan.pop('fixture_sources',None)
    plan.update(upstream_source_sha='1'*40,v25_source_sha='2'*40,v26_source_sha='3'*40)
    # Factor metadata is synthetic and no payload is read or solved.
    groups=[[i] for i in range(8)];groups[5]=[8];groups[7]=[]
    def bundle(b,rows):
        return dict(block=b,rows=rows,**{k:dict(path=str(art/'v24'/str(b)/k),sha256='b'*64,
                    array_sha256='c'*64) for k in ('matrix','LU','pivots')})
    setup=dict(block_inventory=[bundle(b,x) for b,x in enumerate(groups)],source_sha='1'*40)
    prior=dict(source_sha='3'*40,rows=[],matrix=bundle('J',[8])['matrix'],
        factor_inventory={k:bundle('J',[8])[k] for k in ('LU','pivots')})
    old=dict(source_sha='2'*40,rows=[])
    oldplan=dict(upstream_source_sha='1'*40,action_sha256=plan['action_sha256'],states=[])
    for i,item in enumerate(plan['states']):
        row,a,r,W,c9,e9,ids=fixture(kind);row['name']=item['name']
        t=np.arange(16,dtype=complex)*(.1+i*.03);port=np.ones(40,complex)*(1+i+.2j)
        z=np.r_[t,port];rf=np.r_[r,np.zeros(40,complex)]
        state=arrays_receipt(art/'v24'/(item['name']+'.npz'),trace=t,port=port,z=z,residual=rf)
        parent=json_receipt(art/'v24'/(item['name']+'.json'),dict(source_sha='1'*40,
            operator_packet=dict(sha256=plan['action_sha256']),cycles=[{},{},{},dict(state=state)],start=dict(state=state)))
        v25=arrays_receipt(art/'v25'/(item['name']+'.npz'),images=W[:,:8])
        v26=arrays_receipt(art/'v26'/(item['name']+'.npz'),joint_direction=W[:,-1],joint_image=W[:,-1],coefficients=c9,diagnostic_residual=e9)
        item.update(parent_result=parent,state=state,v25_arrays=v25,v26_arrays=v26)
        a.update(audited_full_residual=rf,reclosed_port=port)
        row.update(parent_result=parent,input_state=state,v25_arrays=v25,v26_arrays=v26,
            diagnostic_arrays=arrays_receipt(art/'v28'/(item['name']+'.npz'),**a))
        result['rows'][i]=row
        prior['rows'].append(dict(name=item['name'],input_state=state,diagnostic_arrays=v26,old_direction_arrays=v25,
            trustworthy=True,new_direction_resolved=True,rank=9,gates={'baseline':True},full_b_norm=10.))
        oldrow=dict(name=item['name'],input_state=state,status='DIAGNOSTIC_COMPLETE',rank=8,
            diagnostic_arrays=v25,operation_scales=[1.]*8,
            gates=dict.fromkeys(('diagonal','recombination','qr','stationarity','inequality','numerical_full_direction_rank',
                                  'columns_resolved','whole_response_resolved'),True),eta_unit=1.,eta1=1.,eta8=1.,residual_norm=float(np.linalg.norm(r)),
            full_physical_b_norm=10.,QR_relative=0.,orthogonality_relative=0.,stationarity_operation_relative=0.,
            independent_recombination={'unit':{},'best':{}},diagonal_witnesses=[{}]*8)
        old['rows'].append(oldrow);oldplan['states'].append(dict(name=item['name'],state=state,parent_result=parent))
        if i==0:
            initial=deepcopy(oldrow);initial['name']=OLD_NAMES[0];old['rows'].append(initial)
            oldplan['states'].append(dict(name=OLD_NAMES[0],state=state,parent_result=parent))
    plan['local_setup']=json_receipt(art/'v24'/'setup.json',setup)
    plan['v26_result']=json_receipt(art/'v26'/'result.json',prior)
    plan['v25_result']=json_receipt(art/'v25'/'result.json',old)
    plan['joint_rows_sha256']=array_hash(np.array([8],np.int64))
    certify_inventory(result,plan,factor_sources(setup,prior,plan))
    plan.pop('fixture_sources');plan_path=root/'plan.json';json_receipt(plan_path,plan)
    result['plan_sha256']=file_hash(plan_path);run=root/'results/task042/fixture';result['run_directory']=str(run)
    manifest=result.pop('fixture_manifest');manifest['plan_sha256']=result['plan_sha256']
    result['run_manifest']=json_receipt(run/'run_manifest.json',manifest)
    ledger=result.pop('fixture_ledger');ledger['runs'][0]['directory']=str(run)
    ledger_path=root/'tmp/task042/v28/ledger.json';json_receipt(ledger_path,ledger)
    result['ledger_path']=str(ledger_path)
    result['decision']=classify([dict(new_direction_resolved=x['new_direction_resolved'],g10=x['g10']) for x in result['rows']])
    raw=art/'v28'/'result.json';idx=json_receipt(raw,result);json_receipt(art/'v28'/'DIAGNOSTIC.json',idx)
    return dict(root=root,plan_path=plan_path,artifact_root=art/'v28',records=out,ledger_path=ledger_path,nt=16,old_plan=oldplan),raw,result


def republish(raw,result):
    ref=json_receipt(raw,result);json_receipt(raw.parent/'DIAGNOSTIC.json',ref)
