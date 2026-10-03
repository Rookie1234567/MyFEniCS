"""V25 one-run schema and strictly physical, hash-bound cold-state reader."""
import json,re,tomllib
from pathlib import Path
from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.solvers.neural_fe_action_packet import file_hash
from src.solvers.block_residual_direction import FAMILY,FROZEN_NAMES

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v25'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/block_residual_direction_v25.json'
NAMES=FROZEN_NAMES


def load_block_diagnostic(path):
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if b'[task042_v25]' not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v25']
        if set(cfg)!={'schema_version','task042_v25'} or cfg['schema_version']!=1 or set(item)!={'stage','run_id','material_table_id','diagnostic_family'}:
            raise ValueError('explicit V25 schema required')
        if item['stage']!='DIAGNOSTIC' or not re.fullmatch(r'task042_v25_[a-z0-9_]+',item['run_id']):raise ValueError('V25 one diagnostic only')
        plan,design,material,fe=plan_and_operator();own=json.loads(PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('V25 original operator identity')
        if item['diagnostic_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('V25 material/family differs')
        if tuple(x['name'] for x in own['states'])!=NAMES:raise ValueError('three frozen cold states only')
        from src.solvers.block_direction_window import require_live,ledger
        clock=require_live(margin=900);row=ledger()
        if row['closed'] or row['active'] is not None:raise ValueError('V25 closed/active actor')
        if row['runs'] and not own.get('explicit_repair_reentry',False):raise ValueError('V25 already consumed; no silent replay')
        timeout=min(600-row['actor_wall_seconds'],clock['heavy_remaining_seconds'])
        if timeout<=0:raise ValueError('V25 actor wall exhausted')
    except (OSError,ValueError,KeyError,RuntimeError,tomllib.TOMLDecodeError) as e:raise InputError(f'Task042 V25: {e}') from e
    return RunSpecification(identity=dict(model_id='task042_v25_fixed_0p7nm_p3_diagnostic',run_id=item['run_id'],batch='V25_'+FAMILY),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='block_direction_diagnostic_explicit_opt_in'),solver=dict(preconditioner='task042_v25_diagnostic'),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),output=dict(results_root='results/task042'),
        derived=dict(stage='V25-DIAGNOSTIC',environment_mode='pure',plan_sha256=file_hash(PLAN_PATH),physical_model_complete=True,
            physical_operator_sha256=plan['physical_model_sha256'],decoder_family=FAMILY,
            identity_hash_meaning='original S/b; three frozen cold residuals; eight reused local LU directions; no solver states or reference'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def previous_name(stage):return None


def checked_json(item,root):
    path=Path(item['path']).resolve()
    if not path.is_relative_to(root) or file_hash(path)!=item['sha256']:raise ValueError('V25 upstream manifest path/hash')
    return json.loads(path.read_text())


def physical_state(item,packet):
    from src.io.p1_trace_galerkin import physical_state as reader
    return reader(item,role='WARM',nt=packet.nt,np_=packet.np,size=packet.size,allowed_versions=('v24',),allowed_root=ROOT)


def publish(name,path):
    from src.runners.task042_shared import write_json
    write_json(ARTIFACT_ROOT/(name+'.json'),dict(path=str(path),sha256=file_hash(path)))
