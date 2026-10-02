"""One explicit V22 stage and role-restricted physical state loading."""
import json,re,tomllib
from pathlib import Path
from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.solvers.neural_fe_action_packet import file_hash,array_hash

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v22'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/p1_trace_galerkin_v22.json'
FAMILY='P1_TRACE_GALERKIN_CORRECTION'
STAGES=('SETUP','N','P','Z','T','VERIFY')
ROUTE_WALL=dict(SETUP=1800,N=600,P=1800,Z=2400,T=900,VERIFY=600)
ROUTE_ACTION=dict(SETUP=512,N=1600,P=10000,Z=20000,T=5000,VERIFY=2000)
FILES=dict(SETUP='p1_trace_setup',N='control_warm',P='p1_coarse_warm',Z='p1_coarse_zero',T='p1_coarse_transfer',VERIFY='verify')

def load_p1_trace(path):
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if b'[task042_v22]' not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v22'];stage=item['stage']
        if set(cfg)!={'schema_version','task042_v22'} or cfg['schema_version']!=1 or set(item)!={'stage','run_id','material_table_id','decoder_family'}:raise ValueError('explicit V22 schema required')
        if stage not in STAGES or not re.fullmatch(r'task042_v22_[a-z0-9_]+',item['run_id']):raise ValueError('V22 unregistered one-run stage')
        plan,design,material,fe=plan_and_operator();own=json.loads(PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('V22 frozen physical operator differs')
        if item['decoder_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('V22 material/family differs')
        if stage!='VERIFY' and (ARTIFACT_ROOT/'FROZEN.json').exists():raise ValueError('V22 frozen reference barrier')
        from src.solvers.p1_trace_window import require_live,ledger
        clock=require_live();prior=ledger()['routes'].get(stage,{}).get('wall_seconds',0.)
        timeout=min(ROUTE_WALL[stage]-prior,clock['heavy_remaining_seconds'])
        if timeout<=0:raise ValueError('V22 time budget exhausted')
    except (OSError,ValueError,RuntimeError,KeyError,tomllib.TOMLDecodeError) as error:raise InputError(f'Task042 V22 identity/input: {error}') from error
    return RunSpecification(identity=dict(model_id='task042_v22_fixed_0p7nm_p3_micro',run_id=item['run_id'],batch='V22_'+FAMILY),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='p1_trace_galerkin_explicit_opt_in'),solver=dict(preconditioner='task042_v22_'+stage.lower()),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),output=dict(results_root='results/task042'),
        derived=dict(stage='V22-'+stage,environment_mode='fe' if stage in ('SETUP','VERIFY') else 'pure',plan_sha256=file_hash(PLAN_PATH),
            physical_model_complete=True,physical_operator_sha256=plan['physical_model_sha256'],decoder_family=FAMILY,
            identity_hash_meaning='original S/b; true p1 interpolation trace Galerkin; bounded global coarse LU disclosed; reference only after freeze'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')

def previous_name(stage):return None

def publish(name,path):
    from src.runners.task042_shared import write_json
    ARTIFACT_ROOT.mkdir(parents=True,exist_ok=True);entry=dict(path=str(path),sha256=file_hash(path))
    with (ARTIFACT_ROOT/'index_history.jsonl').open('a') as f:f.write(json.dumps(dict(name=name,**entry))+'\n')
    write_json(ARTIFACT_ROOT/(name+'.json'),entry)

def read_result(name):
    entry=json.loads((ARTIFACT_ROOT/(name+'.json')).read_text());path=Path(entry['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path)!=entry['sha256']:raise ValueError('V22 result ownership/hash')
    result=json.loads(path.read_text())
    if result['plan_sha256']!=file_hash(PLAN_PATH) or (result['reference_arrays_read'] and name!='VERIFY'):raise ValueError('V22 plan/reference role')
    return result,path

def physical_state(item,*,role,nt,np_,size):
    import numpy as np
    if role=='ZERO':raise ValueError('cold role forbids all parent-state decoding')
    state=item['state'];path=Path(state['path']).resolve();allowed=ROOT/'benchmarks/artifacts/task042'
    if not any(path.is_relative_to(allowed/name) for name in ('v19','v21','v22')) or file_hash(path)!=state['sha256']:raise ValueError('V22 physical parent ownership/hash')
    with np.load(path,allow_pickle=False) as f:
        arrays={key:np.array(f[key]) for key in ('trace','port','z','residual') if key in f.files}
    for key,shape in [('trace',(nt,)),('port',(np_,)),('z',(size,)),('residual',(size,))]:
        if key not in arrays or arrays[key].shape!=shape or not np.isfinite(arrays[key]).all():raise ValueError('V22 physical array inventory/nonfinite')
        if key+'_sha256' not in state or array_hash(arrays[key])!=state[key+'_sha256']:raise ValueError('V22 '+key+' member hash')
    if not np.array_equal(arrays['z'],np.r_[arrays['trace'],arrays['port']]):raise ValueError('V22 canonical trace+40-port order')
    return arrays
