"""One explicit V20 stage per input, including opt-in global p3 ILU(0)."""
import json
import re
import tomllib
from pathlib import Path
from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.solvers.neural_fe_action_packet import file_hash

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v20'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/fixed_p3_ilu0_v20.json'
FAMILY='FIXED_P3_ILU0_PORT_QUALIFICATION'
STAGES=('SETUP','N','P0','P40','T','C','VERIFY')
ROUTE_WALL=dict(SETUP=1800,N=600,P0=1200,P40=1200,T=1200,C=1800,VERIFY=600)


def load_fixed_ilu0(path):
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if b'[task042_v20]' not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v20'];stage=item['stage']
        if set(cfg)!={'schema_version','task042_v20'} or cfg['schema_version']!=1 or set(item)!={'stage','run_id','material_table_id','decoder_family'}:
            raise ValueError('explicit V20 schema/keys required')
        if stage not in STAGES or not re.fullmatch(r'task042_v20_[a-z0-9_]+',item['run_id']):raise ValueError('unregistered V20 stage/run id')
        plan,design,material,fe=plan_and_operator();own=json.loads(PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('V20 frozen physical operator differs')
        if item['decoder_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('V20 material/family differs')
        if stage!='VERIFY' and (ARTIFACT_ROOT/'FROZEN.json').exists():raise ValueError('V20 queue already frozen; reference barrier')
        from src.solvers.fixed_p3_ilu0_window import snapshot,ledger
        prior=ledger()['routes'].get(stage,{}).get('wall_seconds',0.)
        timeout=max(1.,min(ROUTE_WALL[stage]-prior,snapshot()['heavy_remaining_seconds']))
    except (OSError,ValueError,KeyError,tomllib.TOMLDecodeError) as error:raise InputError(f'Task042 V20 identity/input: {error}') from error
    return RunSpecification(identity=dict(model_id='task042_v20_fixed_0p7nm_p3_micro',run_id=item['run_id'],batch='V20_'+FAMILY),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='fixed_p3_ilu0_explicit_opt_in'),solver=dict(preconditioner='task042_v20_'+stage.lower()),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),
        output=dict(results_root='results/task042'),derived=dict(stage='V20-'+stage,environment_mode='fe',
            plan_sha256=file_hash(PLAN_PATH),physical_model_complete=True,physical_operator_sha256=plan['physical_model_sha256'],decoder_family=FAMILY,
            identity_hash_meaning='original S/b unchanged; fixed global p3 incomplete factor only as right PC; REF7 only after freeze'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def previous_name(stage):return None


def publish(name,path):
    from src.runners.task042_shared import write_json
    entry=dict(path=str(path),sha256=file_hash(path))
    with (ARTIFACT_ROOT/'index_history.jsonl').open('a') as f:f.write(json.dumps(dict(name=name,**entry))+'\n')
    write_json(ARTIFACT_ROOT/(name+'.json'),entry)


def read_result(name):
    entry=json.loads((ARTIFACT_ROOT/(name+'.json')).read_text());path=Path(entry['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path)!=entry['sha256']:raise ValueError('V20 result ownership/hash differs')
    result=json.loads(path.read_text())
    if result['plan_sha256']!=file_hash(PLAN_PATH) or (result['reference_arrays_read'] and name!='VERIFY'):raise ValueError('V20 plan/reference differs')
    return result,path
