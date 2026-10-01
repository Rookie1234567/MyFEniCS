"""Explicit V19 one-run inputs, immutable physical packet, closed ref barrier."""
import json
import re
import tomllib
from pathlib import Path

from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.solvers.neural_fe_action_packet import file_hash

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v19'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/post_lsqr_polish_v19.json'
FAMILY='POST_LSQR_RESIDUAL_POLISH'
ROUTES={'PREFLIGHT':('C0',None),'VERIFY':('V',None),
        **{a+'_'+f:(a,f) for a in ('P','L') for f in ('GPOLY','GNN')}}
STAGES=tuple(ROUTES)


def stage_route(stage):
    if stage not in ROUTES:raise ValueError('unregistered V19 stage')
    return ROUTES[stage]


def load_post_lsqr(path):
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if b'[task042_v19]' not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v19'];stage=item['stage'];algorithm,library=stage_route(stage)
        keys={'stage','algorithm','library','run_id','material_table_id','decoder_family','target_iteration','target_cycles'}
        if set(cfg)!={'schema_version','task042_v19'} or cfg['schema_version']!=1 or set(item)!=keys:raise ValueError('explicit V19 schema/keys required')
        if item['algorithm']!=algorithm or item['library']!=(library or 'NONE'):raise ValueError('explicit algorithm/library differs')
        if not re.fullmatch(r'task042_v19_[a-z0-9_]+',item['run_id']):raise ValueError('invalid V19 run id')
        k,m=item['target_iteration'],item['target_cycles']
        if type(k)!=int or type(m)!=int:raise ValueError('integer targets required')
        if algorithm in ('P','L'):
            if m not in range(8,65,8) or k:raise ValueError('unregistered P/L cycle target')
        elif k or m:raise ValueError('C0/V have no solve targets')
        plan,design,material,fe=plan_and_operator();own=json.loads(PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('original S/b identity differs')
        if item['decoder_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('family/material differs')
        if stage!='VERIFY' and (ARTIFACT_ROOT/'FROZEN.json').exists():raise ValueError('V19 reference barrier: queue frozen')
        from src.solvers.post_lsqr_window import BUDGET_PATH,ledger,snapshot
        budget=json.loads(BUDGET_PATH.read_text()) if BUDGET_PATH.exists() else None
        timeout=600 if algorithm in ('C0','V') else 2700
        if library and budget:
            route=ledger()['routes'][stage];timeout=budget['uniform_route_wall_seconds']-route['wall_seconds']
        timeout=max(1.,min(timeout,snapshot()['heavy_remaining_seconds']))
    except (OSError,ValueError,KeyError,tomllib.TOMLDecodeError) as error:raise InputError(f'Task042 V19 identity/input: {error}') from error
    return RunSpecification(identity=dict(model_id='task042_v19_fixed_0p7nm_p3_micro',run_id=item['run_id'],batch='V19_POST_LSQR_RESIDUAL_POLISH'),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='post_lsqr_polish_explicit_opt_in'),solver=dict(preconditioner='task042_v19_'+stage.lower()),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),
        output=dict(results_root='results/task042'),derived=dict(stage='V19-'+stage,environment_mode='fe' if stage=='VERIFY' else 'pure',
            plan_sha256=file_hash(PLAN_PATH),physical_model_complete=True,physical_operator_sha256=plan['physical_model_sha256'],decoder_family=FAMILY,
            algorithm=algorithm,library=library,route_budget=budget,target_iteration=k,target_cycles=m,
            identity_hash_meaning='unchanged original S/b; V18 R-FINAL fixed starts; independent P/L; REF7 only after freeze'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def previous_name(stage):return None


def publish(name,path):
    from src.runners.task042_shared import write_json
    entry=dict(path=str(path),sha256=file_hash(path))
    with (ARTIFACT_ROOT/'index_history.jsonl').open('a') as f:f.write(json.dumps(dict(name=name,**entry))+'\n')
    write_json(ARTIFACT_ROOT/(name+'.json'),entry)


def read_result(name):
    entry=json.loads((ARTIFACT_ROOT/(name+'.json')).read_text());path=Path(entry['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path)!=entry['sha256']:raise ValueError('V19 result ownership/hash differs')
    result=json.loads(path.read_text())
    if result['plan_sha256']!=file_hash(PLAN_PATH) or (result['reference_arrays_read'] and name!='VERIFY'):raise ValueError('V19 plan/reference differs')
    return result,path


def write_input(path,stage,target,run_id):
    algorithm,library=stage_route(stage);path=Path(path)
    if path.exists():raise ValueError('one-run dat already exists')
    k=0;m=target if algorithm in ('P','L') else 0
    path.write_text(f'''schema_version = 1
[task042_v19]
stage = "{stage}"
algorithm = "{algorithm}"
library = "{library or 'NONE'}"
run_id = "{run_id}"
material_table_id = "SI_OPTICAL_CONSTANTS_USER_20260929_V1"
decoder_family = "{FAMILY}"
target_iteration = {k}
target_cycles = {m}
''')
    return path

ACTION_LIMIT=80000
ROUTE_ACTION_LIMIT=19500
CYCLE_RESERVE=320
LIMITS=dict(new_A_columns=0,image_QR=0,original_audits=300,field_states=12)

def route_key(algorithm,library):return algorithm+'_'+library if library else None
