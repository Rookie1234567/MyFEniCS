"""Explicit one-run V24 inputs, image identity and role-restricted readers."""
import json,re,tomllib
from pathlib import Path
from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.solvers.neural_fe_action_packet import file_hash,array_hash
from src.solvers.local_block_coarse import FAMILY

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v24'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/local_block_coarse_v24.json'
STAGES=('SETUP','LW','LCW','LZ','LCZ','VERIFY')
FILES=dict(SETUP='local_block_setup',LW='local_warm',LCW='local_coarse_warm',LZ='local_zero',LCZ='local_coarse_zero',VERIFY='verify')
ROUTE_WALL=dict(SETUP=2400,LW=1200,LCW=1200,LZ=1800,LCZ=1800,VERIFY=600)
ROUTE_ACTION=dict(SETUP=512,LW=8000,LCW=10000,LZ=16000,LCZ=20000,VERIFY=1000)

def load_local_block(path):
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if b'[task042_v24]' not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v24'];stage=item['stage']
        if set(cfg)!={'schema_version','task042_v24'} or cfg['schema_version']!=1 or set(item)!={'stage','run_id','material_table_id','decoder_family','target_cycles'}:raise ValueError('explicit V24 schema required')
        if item['target_cycles'] not in ((0,) if stage in ('SETUP','VERIFY') else (4,)) or stage not in STAGES or not re.fullmatch(r'task042_v24_[a-z0-9_]+',item['run_id']):raise ValueError('V24 unregistered one-run stage; Review21 section10 permits first four cycles only')
        plan,design,material,fe=plan_and_operator();own=json.loads(PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('V24 frozen physical operator differs')
        if item['decoder_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('V24 material/family differs')
        if stage!='VERIFY' and (ARTIFACT_ROOT/'FROZEN.json').exists():raise ValueError('V24 frozen reference barrier')
        from src.solvers.local_block_window import require_live,ledger
        clock=require_live();prior=ledger()['routes'].get(stage,{}).get('wall_seconds',0.)
        timeout=min(ROUTE_WALL[stage]-prior,clock['heavy_remaining_seconds'])
        if timeout<=0:raise ValueError('V24 time budget exhausted')
    except (OSError,ValueError,RuntimeError,KeyError,tomllib.TOMLDecodeError) as error:raise InputError(f'Task042 V24 identity/input: {error}') from error
    return RunSpecification(identity=dict(model_id='task042_v24_fixed_0p7nm_p3_micro',run_id=item['run_id'],batch='V24_'+FAMILY),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='local_block_coarse_explicit_opt_in'),solver=dict(preconditioner='task042_v24_'+stage.lower()),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),output=dict(results_root='results/task042'),
        derived=dict(stage='V24-'+stage,environment_mode='fe' if stage=='VERIFY' else 'pure',plan_sha256=file_hash(PLAN_PATH),
            physical_model_complete=True,physical_operator_sha256=plan['physical_model_sha256'],decoder_family=FAMILY,
            target_cycles=item['target_cycles'],identity_hash_meaning='original S/b; fixed eight geometric principal LU blocks; reused T/U/R; independent oracle'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')

def previous_name(stage):return None

def publish(name,path):
    from src.runners.task042_shared import write_json
    ARTIFACT_ROOT.mkdir(parents=True,exist_ok=True);entry=dict(path=str(path),sha256=file_hash(path))
    with (ARTIFACT_ROOT/'index_history.jsonl').open('a') as f:f.write(json.dumps(dict(name=name,**entry))+'\n')
    write_json(ARTIFACT_ROOT/(name+'.json'),entry)

def read_result(name):
    entry=json.loads((ARTIFACT_ROOT/(name+'.json')).read_text());path=Path(entry['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path)!=entry['sha256']:raise ValueError('V24 result ownership/hash')
    result=json.loads(path.read_text())
    if result['plan_sha256']!=file_hash(PLAN_PATH) or (result['reference_arrays_read'] and name!='VERIFY'):raise ValueError('V24 plan/reference role')
    return result,path

def physical_state(item,*,role,nt,np_,size):
    if role in ('SETUP','ZERO'):raise ValueError('V24 role forbids parent-state decoding')
    path=Path(item['state']['path']).resolve()
    if role.startswith('OWN_ZERO_') and not path.is_relative_to((ARTIFACT_ROOT/role.removeprefix('OWN_ZERO_')).resolve()):raise ValueError('cold may decode only own returned states')
    from src.io import p1_trace_galerkin as previous
    return previous.physical_state(item,role='WARM',nt=nt,np_=np_,size=size,allowed_versions=('v21','v24'),allowed_root=ROOT)

def load_trace(plan,packet):
    import numpy as np
    from scipy.sparse import load_npz
    item=plan['T'];p=Path(item['path']).resolve()
    if not p.is_relative_to(ROOT/'benchmarks/artifacts/task042/v22') or file_hash(p)!=item['sha256']:raise ValueError('T path/hash')
    T=load_npz(p)
    if T.shape!=(packet.nt,1248) or array_hash(packet.a['masters'])!=item['canonical_master_sha256']:raise ValueError('T canonical identity')
    manifest=plan['upstream_SETUP_result']
    if file_hash(manifest['path'])!=manifest['sha256']:raise ValueError('T qualification manifest hash')
    old=json.loads(Path(manifest['path']).read_text())
    def find(x):
        if isinstance(x,dict):
            if set(('data_sha256','indices_sha256','indptr_sha256'))<=set(x):return x
            for v in x.values():
                got=find(v)
                if got:return got
        return None
    checks=find(old['transfer_checks'])
    if checks is None:raise ValueError('T CSR member inventory absent')
    for key in ('data','indices','indptr'):
        if array_hash(getattr(T,key))!=checks[key+'_sha256']:raise ValueError('T member '+key)
    return T
