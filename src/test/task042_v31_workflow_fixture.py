"""Actual study wiring at 18144/40, with a 16-dimensional synthetic action.

Only IO/readers are stubs; run, return algebra, thin workflow, writer, stage
finish, durable accounting and cached collector execute their real code.
No production payload is opened and no full-size square matrix is built.
"""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import json,time
import numpy as np
from scipy.linalg import lu_factor,lu_solve,lstsq
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.runners.task042_shared import write_json
from src.test.task042_return_fixture import json_receipt


def arrays_receipt(path,**arrays):
    """Compress sparse synthetic inputs only; production writer stays unchanged."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as stream:np.savez_compressed(stream,**arrays)
    return dict(path=str(path),sha256=file_hash(path),**{k+'_sha256':array_hash(v) for k,v in arrays.items()})


def workflow(root,monkeypatch,*,reject_state=False,batch='v31'):
    if batch not in ('v31','v32','v33'):raise ValueError('unapproved workflow namespace')
    from src.solvers import return_block_study as study,joint_block_study as oldstudy
    from src.solvers.return_block_direction import SelectedBundle,NAMES,FAMILY
    from src.solvers.return_block_window import CAPS
    from src.solvers.bounded_diagnostic_window import DiagnosticWindow
    from src.runners.return_block_diagnostic import ReturnStage
    from src.io.block_direction_diagnostic import checked_json,NAMES as OLD_NAMES
    from src.io.p1_trace_galerkin import physical_state
    from benchmarks import collect_task042_block_direction as oldcollector
    from benchmarks.collect_task042_return_direction import collect
    if batch=='v33':
        from src.solvers import full_input_block_study as study
        from src.solvers.full_input_block_correction import FAMILY,CAPS
        from benchmarks.task042_full_input_checker import collect
    root=Path(root).resolve();art=root/'benchmarks/artifacts/task042';nt=18144
    rows=(2913,2676,2289,2076,2439,2220,1863,1668)
    groups=np.repeat(np.arange(8),rows);ids=np.flatnonzero((groups==5)|(groups==7))
    first=np.r_[0,np.cumsum(rows)[:-1]];active=np.ravel(np.column_stack((first,first+1)))
    rng=np.random.default_rng(423101)
    A=2*np.eye(16)+.04*(rng.normal(size=(16,16))+1j*rng.normal(size=(16,16)))
    C=.01*(rng.normal(size=(16,40))+1j*rng.normal(size=(16,40)))
    F=.01*(rng.normal(size=(40,16))+1j*rng.normal(size=(40,16)))
    H=np.diag(1+np.arange(40)/40+.2j)
    K=A+C@np.linalg.solve(H,F)
    def bar(x):
        y=2*x.copy();y[active]=A@x[active];return y
    def raw(x,adjoint=False):
        t,p=x[:nt],x[nt:];out=2*t.copy()
        if adjoint:
            out[active]=K.conj().T@t[active]+F.conj().T@p
            return np.r_[out,C.conj().T@t[active]+H.conj().T@p]
        out[active]=K@t[active]+C@p
        return np.r_[out,F@t[active]+H@p]
    b=np.zeros(nt+40,complex);b[active]=rng.normal(size=16)+1j*rng.normal(size=16)
    b[nt:]=.3+.2j+np.arange(40)*.01
    packet=SimpleNamespace(nt=nt,np=40,size=nt+40,lt=1,nc=1,bnorm=float(np.linalg.norm(b)),
        a=dict(b=b,masters=np.arange(nt),Hhat=H,erows=np.array([0]),evals=np.ones(1),
            classes=np.array([0]),S=np.array([[[10+0j]]])),counts=dict(S=0,SH=0,audit=0),costs=dict(S=0.,SH=0.))
    packet._expand=lambda x:x[None,:]
    window_dir=root/'tmp/task042'/batch;window_dir.mkdir(parents=True)
    json_receipt(window_dir/'window.json',dict(start_utc=time.time(),start_monotonic=time.monotonic(),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),heavy_limit_seconds=4500,total_limit_seconds=5400))
    w=DiagnosticWindow(window_dir,CAPS,batch.upper()+'-fixture')
    # evaluate_window accepts ISO UTC; keep the real implementation here too.
    from datetime import datetime,timezone
    window=json.loads(w.WINDOW_PATH.read_text());window['start_utc']=datetime.now(timezone.utc).isoformat();write_json(w.WINDOW_PATH,window)
    stage=ReturnStage.__new__(ReturnStage);stage.window=w;stage.base=w.ledger();stage.counts=dict.fromkeys(CAPS,0)
    stage.source='d'*40;stage.directory=root/'results/task042/fixture';stage.directory.mkdir(parents=True)
    stage.artifact=art/batch/'run';stage.artifact.mkdir(parents=True);stage.packet=packet
    stage.name='DIAGNOSTIC';stage.family=FAMILY;stage.carry_actions=0;stage.historical_lower=0.
    stage.run_started=time.monotonic();stage.began=time.perf_counter();stage.actor_limit=600;stage.artifact_limit=32*2**20
    stage.guard=lambda **kw:None;stage.sample=lambda:dict(rss_bytes=0)
    stage.base['active']=dict(directory=str(stage.directory),source_sha=stage.source,completed=stage.counts.copy(),upper=stage.counts.copy())
    write_json(w.LEDGER_PATH,stage.base)
    def counted(x,adjoint=False):
        stage.reserve('actions');y=raw(x,adjoint);stage.counts['actions']+=1
        packet.counts['SH' if adjoint else 'S']+=1;stage.durable();return y
    packet.apply=counted
    def factor_item(block,idx):
        n=len(idx)
        return dict(block=block,rows=idx.tolist(),**{key:dict(path=str(art/'v24'/'factors'/str(block)/key),
            sha256='b'*64,array_sha256='c'*64,shape=[n] if key=='pivots' else [n,n]) for key in ('matrix','LU','pivots')})
    setup=dict(block_inventory=[factor_item(i,np.flatnonzero(groups==i)) for i in range(8)],source_sha='1'*40,
        operator_packet=dict(sha256='a'*64))
    jitem=factor_item('J',ids)
    for key in ('matrix','LU','pivots'):jitem[key]['path']=str(art/'v26/factors'/key)
    prior=dict(source_sha='3'*40,operator_packet=dict(sha256='a'*64),rows=[],matrix=jitem['matrix'],
        factor_inventory={k:jitem[k] for k in ('LU','pivots')},factor_safety=dict(qualified=True,rcond1_estimate=.5))
    ret=dict(status='DIAGNOSTIC_COMPLETE',source_sha='4'*40,operator_packet=dict(sha256='a'*64),rows=[])
    old=dict(source_sha='2'*40,operator_packet=dict(sha256='a'*64),rows=[])
    plan=dict(upstream_source_sha='1'*40,v25_source_sha='2'*40,v26_source_sha='3'*40,
        action_sha256='a'*64,physical_sha256='a'*64,mode_sha256='a'*64,
        canonical_master_sha256=array_hash(packet.a['masters']),b_sha256=array_hash(b),map={},states=[],
        joint_rows_sha256=array_hash(ids))
    oldplan=dict(upstream_source_sha='1'*40,action_sha256='a'*64,states=[])
    direction=np.zeros((nt,8),complex);direction[active[::2],np.arange(8)]=1
    images=np.column_stack([bar(x) for x in direction.T])
    jpositions=np.flatnonzero(np.isin(active,ids));jactive=active[jpositions]
    for i,name in enumerate(NAMES):
        t=np.zeros(nt,complex);t[active]=(.1+i*.04)*(np.arange(16)+.2j)
        port=np.linalg.solve(H,b[nt:]-F@t[active]);z=np.r_[t,port];res=b-raw(z);r=res[:nt]
        state=arrays_receipt(art/'v24'/(name+'.npz'),trace=t,port=port,z=z,residual=res)
        parent=json_receipt(art/'v24'/(name+'.json'),dict(source_sha='1'*40,operator_packet=dict(sha256='a'*64),
            cycles=[{},{},{},dict(state=state)],start=dict(state=state)))
        qj=np.zeros(nt,complex);qj[jactive]=np.linalg.solve(A[np.ix_(jpositions,jpositions)],r[jactive]);vj=bar(qj)
        if batch=='v33':
            # Genuine fixed block inverses on this residual, not fitted columns.
            direction=np.zeros((nt,8),complex)
            for block in range(8):
                positions=np.flatnonzero(groups[active]==block)
                direction[active[positions],block]=np.linalg.solve(A[np.ix_(positions,positions)],r[active[positions]])
            images=np.column_stack([bar(x) for x in direction.T])
        W9=np.column_stack((images,vj));c9=lstsq(W9[active],r[active],cond=1e-12,lapack_driver='gelsd')[0];e9=r-W9@c9
        v25=arrays_receipt(art/'v25'/(name+'.npz'),directions=direction,images=images,coefficients=np.zeros(8,complex))
        v26=arrays_receipt(art/'v26'/(name+'.npz'),joint_direction=qj,joint_image=vj,coefficients=c9,diagnostic_residual=e9)
        item=dict(name=name,parent_result=parent,state=state,v25_arrays=v25,v26_arrays=v26)
        if batch=='v33':
            wret=np.zeros(nt,complex)
            for block in (0,1,2,3,4,6):
                positions=np.flatnonzero(groups[active]==block)
                wret[active[positions]]=np.linalg.solve(A[np.ix_(positions,positions)],vj[active[positions]])
            qret=qj-wret
            qret[jactive]+=np.linalg.solve(A[np.ix_(jpositions,jpositions)],bar(wret)[jactive])
            v32=arrays_receipt(art/'v32'/(name+'.npz'),return_direction=qret,return_image=bar(qret))
            item['v32_arrays']=v32
            ret['rows'].append(dict(name=name,input_state=state,diagnostic_arrays=v32,v25_arrays=v25,v26_arrays=v26,trustworthy=True,gates=dict(qualified=True)))
        plan['states'].append(item)
        prior['rows'].append(dict(name=name,input_state=state,diagnostic_arrays=v26,old_direction_arrays=v25,trustworthy=True,
            new_direction_resolved=True,rank=9,gates=dict(baseline=True),eta9=float(np.linalg.norm(e9)/np.linalg.norm(r)),full_b_norm=packet.bnorm))
        oldrow=dict(name=name,input_state=state,status='DIAGNOSTIC_COMPLETE',rank=8,diagnostic_arrays=v25,
            operation_scales=[100.]*8,gates=dict.fromkeys(('diagonal','recombination','qr','stationarity','inequality',
                'numerical_full_direction_rank','columns_resolved','whole_response_resolved'),True),
            eta_unit=1.,eta1=1.,eta8=1.,residual_norm=float(np.linalg.norm(r)),full_physical_b_norm=packet.bnorm,
            QR_relative=0.,orthogonality_relative=0.,stationarity_operation_relative=0.,
            independent_recombination={'unit':{},'best':{}},diagonal_witnesses=[{}]*8)
        old['rows'].append(oldrow);oldplan['states'].append(dict(name=name,state=state,parent_result=parent))
        if i==0:
            initial=deepcopy(oldrow);initial['name']=OLD_NAMES[0];old['rows'].append(initial)
            oldplan['states'].append(dict(name=OLD_NAMES[0],state=state,parent_result=parent))
    if batch=='v33':
        plan['v32_result']=json_receipt(art/'v32/result.json',ret);plan['v32_source_sha']='4'*40
    plan['local_setup']=json_receipt(art/'v24/setup.json',setup)
    plan['v26_result']=json_receipt(art/'v26/result.json',prior);plan['v25_result']=json_receipt(art/'v25/result.json',old)
    plan_path=root/'plan.json';json_receipt(plan_path,plan);stage.own_plan=plan
    stage.meta=dict(source_sha=stage.source,input_sha256='e'*64,plan_sha256=file_hash(plan_path),operator_packet=dict(sha256='a'*64),
        complete_ports=40,reference_arrays_read=False,Q_U_R_D_L_loaded=False,global_p4_factor_constructed=False)
    write_json(stage.directory/'run_manifest.json',dict(source_sha=stage.source,input_sha256='e'*64))
    io=SimpleNamespace(ROOT=root,LABEL=batch.upper(),FAMILY=FAMILY,PLAN_PATH=plan_path,ARTIFACT_ROOT=art/batch,checked_json=checked_json,
        physical_state=lambda item,p:physical_state(item,role='WARM',nt=p.nt,np_=p.np,size=p.size,allowed_versions=('v24',),allowed_root=root),
        publish=lambda name,path:json_receipt(art/batch/(name+'.json'),dict(path=str(path),sha256=file_hash(path))))
    stage.io=io;monkeypatch.setattr(study,'io',io,raising=False);monkeypatch.setattr(oldstudy,'io',io)
    monkeypatch.setattr(study,'mapping',lambda stage:(groups,{'fixture':True}))
    monkeypatch.setattr(study,'local_readiness',lambda *a,**k:dict(qualified=True,fixture=True))
    def direct_c(p,e):
        v=np.zeros(nt,complex);v[active]=C@e;return v
    monkeypatch.setattr(study,'direct_C',direct_c)
    original_inventory=oldcollector.fixed_inventory
    monkeypatch.setattr(oldcollector,'fixed_inventory',lambda value,*a,**k:original_inventory(value,oldplan,root=root))
    class Principal:
        def __init__(self,idx,adjoint=False):self.idx=idx;self.adj=adjoint
        def __matmul__(self,x):
            full=np.zeros(nt,complex);full[self.idx]=x;y=2*full
            y[active]=(A.conj().T if self.adj else A)@full[active];return y[self.idx]
        def conj(self):return SimpleNamespace(T=Principal(self.idx,True))
    class Bundle:
        witnesses=SelectedBundle.witnesses
        def __init__(self,item,allowed,*,kind,count,guard):
            count('factor_readers');self.rows=np.asarray(item['rows']);self.A=Principal(self.rows);self.A1=10.
            self.count,self.kind=count,kind;self.calls=self.RHS_columns=0;self.seconds=self.load_seconds=0.
            self.pivots=np.zeros(len(self.rows),np.int32)
            self.positions=np.flatnonzero(np.isin(active,self.rows));self.local=np.searchsorted(self.rows,active[self.positions])
            self.factor=lu_factor(A[np.ix_(self.positions,self.positions)])
            self.receipts=[dict(key=k,path=v['path'],container_sha256=v['sha256'],array_sha256=v['array_sha256'],readonly=True,
                full_hash_copy=False,container_stream_hash_reads=1,numeric_mmap_loads=1,array_hash_scans=1) for k,v in item.items() if k in ('matrix','LU','pivots')]
        def solve(self,rhs):
            self.count(self.kind+'_lu_solve');self.count('explicit_triangular_pass',2)
            out=rhs/2;out[self.local]=lu_solve(self.factor,rhs[self.local]);self.calls+=1;self.RHS_columns+=1;return out
        def close(self):pass
    monkeypatch.setattr(study,'SelectedBundle',Bundle)
    if reject_state:
        def rejected_state(*args):raise ValueError('synthetic state reader rejection')
        io.physical_state=rejected_state
    try:
        result=study.run(stage)  # The formerly unbound relative call executes here.
    except ValueError as error:
        if not reject_state or str(error)!='synthetic state reader rejection':raise
        result=dict(stage.partial_result,status='FAILED',error=str(error))
    stage.finish(result)    # Real ReturnStage/Stage writer and manifest seal.
    w.settle_run(stage.directory,dict(classification='FAILED' if reject_state else 'COMPLETED',leader_exit_code=1 if reject_state else 0,source_state=dict(source_sha=stage.source),
        elapsed_seconds=time.monotonic()-stage.run_started,sampled_process_tree_rss_peak_bytes=0,
        sampled_process_tree_swap_peak_bytes=0,descendants_cleared=True),0.)
    out=collect(root=root,plan_path=plan_path,artifact_root=art/batch,records=root/'records',
        ledger_path=w.LEDGER_PATH,nt=nt,old_plan=oldplan,**({} if batch=='v33' else dict(batch=batch)))
    return result,out,w.ledger()
