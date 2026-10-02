"""Explicit one-run V23 inputs, image identity and role-restricted readers."""
import json,re,tomllib
from pathlib import Path
from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.solvers.neural_fe_action_packet import file_hash,array_hash
from src.solvers.p1_image_minres import FAMILY

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v23'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/p1_image_minres_v23.json'
STAGES=('SETUP','COMPARE','M','Z','VERIFY')
FILES=dict(SETUP='p1_image_setup',COMPARE='p1_coarse_compare',M='p1_image_mr_warm',Z='p1_image_mr_zero',VERIFY='verify')
ROUTE_WALL=dict(SETUP=1800,COMPARE=300,M=1800,Z=2400,VERIFY=600)
ROUTE_ACTION=dict(SETUP=1408,COMPARE=160,M=10000,Z=20000,VERIFY=1000)

def load_image_minres(path):
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if b'[task042_v23]' not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v23'];stage=item['stage']
        if set(cfg)!={'schema_version','task042_v23'} or cfg['schema_version']!=1 or set(item)!={'stage','run_id','material_table_id','decoder_family'}:raise ValueError('explicit V23 schema required')
        if stage not in STAGES or not re.fullmatch(r'task042_v23_[a-z0-9_]+',item['run_id']):raise ValueError('V23 unregistered one-run stage')
        plan,design,material,fe=plan_and_operator();own=json.loads(PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('V23 frozen physical operator differs')
        if item['decoder_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('V23 material/family differs')
        if stage!='VERIFY' and (ARTIFACT_ROOT/'FROZEN.json').exists():raise ValueError('V23 frozen reference barrier')
        from src.solvers.p1_image_window import require_live,ledger
        clock=require_live();prior=ledger()['routes'].get(stage,{}).get('wall_seconds',0.)
        timeout=min(ROUTE_WALL[stage]-prior,clock['heavy_remaining_seconds'])
        if timeout<=0:raise ValueError('V23 time budget exhausted')
    except (OSError,ValueError,RuntimeError,KeyError,tomllib.TOMLDecodeError) as error:raise InputError(f'Task042 V23 identity/input: {error}') from error
    return RunSpecification(identity=dict(model_id='task042_v23_fixed_0p7nm_p3_micro',run_id=item['run_id'],batch='V23_'+FAMILY),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='p1_image_minres_explicit_opt_in'),solver=dict(preconditioner='task042_v23_'+stage.lower()),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),output=dict(results_root='results/task042'),
        derived=dict(stage='V23-'+stage,environment_mode='fe' if stage=='VERIFY' else 'pure',plan_sha256=file_hash(PLAN_PATH),
            physical_model_complete=True,physical_operator_sha256=plan['physical_model_sha256'],decoder_family=FAMILY,
            identity_hash_meaning='original S/b; fixed T/Ac/tau; one thin image QR; independent oracle; reference only after freeze'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')

def previous_name(stage):return None

def publish(name,path):
    from src.runners.task042_shared import write_json
    ARTIFACT_ROOT.mkdir(parents=True,exist_ok=True);entry=dict(path=str(path),sha256=file_hash(path))
    with (ARTIFACT_ROOT/'index_history.jsonl').open('a') as f:f.write(json.dumps(dict(name=name,**entry))+'\n')
    write_json(ARTIFACT_ROOT/(name+'.json'),entry)

def read_result(name):
    entry=json.loads((ARTIFACT_ROOT/(name+'.json')).read_text());path=Path(entry['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path)!=entry['sha256']:raise ValueError('V23 result ownership/hash')
    result=json.loads(path.read_text())
    if result['plan_sha256']!=file_hash(PLAN_PATH) or (result['reference_arrays_read'] and name!='VERIFY'):raise ValueError('V23 plan/reference role')
    return result,path

def physical_state(item,*,role,nt,np_,size):
    if role in ('IMAGE_SETUP','ZERO'):raise ValueError('V23 role forbids parent-state decoding')
    path=Path(item['state']['path']).resolve()
    if role=='OWN_ZERO' and not path.is_relative_to((ARTIFACT_ROOT/'Z').resolve()):raise ValueError('cold may decode only own returned states')
    from src.io import p1_trace_galerkin as previous
    return previous.physical_state(item,role='WARM',nt=nt,np_=np_,size=size,allowed_versions=('v21','v23'),allowed_root=ROOT)

def load_coarse(plan,packet):
    """Only frozen V22 coarse arrays; does not even open a warm state."""
    import numpy as np
    from scipy.sparse import load_npz
    root=ROOT/'benchmarks/artifacts/task042/v22'
    for key in ('T','Ac'):
        p=Path(plan[key]['path']).resolve()
        if not p.is_relative_to(root) or file_hash(p)!=plan[key]['sha256']:raise ValueError('V23 '+key+' upstream file identity')
    T=load_npz(plan['T']['path']);Ac=np.load(plan['Ac']['path'],allow_pickle=False)
    if list(T.shape)!=plan['T']['shape'] or list(Ac.shape)!=plan['Ac']['shape']:raise ValueError('V23 coarse shape')
    if T.shape!=(packet.nt,1248) or array_hash(packet.a['masters'])!=plan['T']['canonical_master_sha256'] or array_hash(Ac)!=plan['Ac']['array_sha256']:raise ValueError('V23 coarse numeric/canonical identity')
    upstream=json.loads(Path(plan['upstream_SETUP_result']['path']).read_text())
    if file_hash(plan['upstream_SETUP_result']['path'])!=plan['upstream_SETUP_result']['sha256']:raise ValueError('V22 coarse manifest hash')
    # CSR member hashes are stored in the original transfer qualification.
    def search(x):
        if isinstance(x,dict):
            if set(('data_sha256','indices_sha256','indptr_sha256'))<=set(x):return x
            for value in x.values():
                found=search(value)
                if found:return found
        return None
    checks=search(upstream['transfer_checks'])
    if checks is None:raise ValueError('V22 T member hash inventory missing')
    for key,value in [('data',T.data),('indices',T.indices),('indptr',T.indptr)]:
        if array_hash(value)!=checks[key+'_sha256']:raise ValueError('V23 T '+key+' member hash')
    return T,Ac
