"""V17 explicit one-run slice inputs; immutable operator and reference barrier."""
import json
import re
import tomllib
from pathlib import Path
from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.solvers.neural_fe_action_packet import file_hash

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v17'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/resumable_full_trace_v17.json'
FAMILY='RESUMABLE_FULL_TRACE_CAMPAIGN'
STAGES=('PREFLIGHT','GPOLY','GNN','GMRES_GPOLY','GMRES_GNN','VERIFY')


def load_resumable_trace(path):
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if b'[task042_v17]' not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v17'];stage=item['stage']
        if set(cfg)!={'schema_version','task042_v17'} or cfg['schema_version']!=1:raise ValueError('explicit V17 schema required')
        if set(item)!={'stage','run_id','material_table_id','decoder_family','target_iteration'}:raise ValueError('V17 keys differ')
        if stage not in STAGES or not re.fullmatch(r'task042_v17_[a-z0-9_]+',item['run_id']):raise ValueError('unregistered stage/run')
        target=item['target_iteration']
        if not isinstance(target,int) or not 0<=target<=8192 or (stage in ('GPOLY','GNN') and target%512):raise ValueError('invalid logical slice target')
        plan,design,material,fe=plan_and_operator();own=json.loads(PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('frozen operator differs')
        if item['decoder_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('family/material differs')
        if stage!='VERIFY' and (ARTIFACT_ROOT/'FROZEN.json').exists():raise ValueError('V17 reference barrier: queue frozen')
        from src.solvers.resumable_trace_window import BUDGET_PATH,ledger,snapshot
        budget=json.loads(BUDGET_PATH.read_text()) if BUDGET_PATH.exists() else None
        timeout=900 if stage=='PREFLIGHT' else 600 if stage=='VERIFY' else 9000
        if stage in ('GPOLY','GNN','GMRES_GPOLY','GMRES_GNN') and budget:
            family=stage.removeprefix('GMRES_');used=ledger()['routes'][family]['wall_seconds']
            ceiling=budget['uniform_route_wall_seconds']-(0 if stage.startswith('GMRES_') else budget['GMRES_reserved_seconds'])
            timeout=max(1.,ceiling-used)
        timeout=min(timeout,snapshot()['heavy_remaining_seconds'])
    except (OSError,ValueError,KeyError,tomllib.TOMLDecodeError) as error:
        raise InputError(f'Task042 V17 identity/input: {error}') from error
    return RunSpecification(identity=dict(model_id='task042_v17_fixed_0p7nm_p3_micro',run_id=item['run_id'],batch='V17_RESUMABLE_FULL_TRACE_CAMPAIGN'),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='resumable_full_trace_campaign_explicit_opt_in'),solver=dict(preconditioner='task042_v17_'+stage.lower()),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),
        output=dict(results_root='results/task042'),derived=dict(stage='V17-'+stage,environment_mode='fe' if stage=='VERIFY' else 'pure',
            plan_sha256=file_hash(PLAN_PATH),physical_model_complete=True,physical_operator_sha256=plan['physical_model_sha256'],
            decoder_family=FAMILY,route_budget=budget,target_iteration=target,identity_hash_meaning='unchanged original S/b; serial resumable full trace; REF7 after queue freeze'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def previous_name(stage):return None


def publish(name,path):
    from src.runners.task042_shared import write_json
    entry=dict(path=str(path),sha256=file_hash(path))
    with (ARTIFACT_ROOT/'index_history.jsonl').open('a') as stream:stream.write(json.dumps(dict(name=name,**entry))+'\n')
    write_json(ARTIFACT_ROOT/(name+'.json'),entry)


def read_result(name):
    entry=json.loads((ARTIFACT_ROOT/(name+'.json')).read_text());path=Path(entry['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path)!=entry['sha256']:raise ValueError('V17 result ownership/hash differs')
    result=json.loads(path.read_text())
    if result['plan_sha256']!=file_hash(PLAN_PATH) or (result['reference_arrays_read'] and name!='VERIFY'):raise ValueError('V17 plan/reference differs')
    return result,path
