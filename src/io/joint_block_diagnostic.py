"""Explicit one-run V26; only hash-bound physical states and old directions."""
import json,re,tomllib
from pathlib import Path
from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.io.block_direction_diagnostic import checked_json,physical_state
from src.solvers.neural_fe_action_packet import file_hash
from src.solvers.joint_block_direction import FAMILY

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v26'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/joint_block_direction_v26.json'
NAMES=('V24-LZ-CYCLE4','V24-LCZ-CYCLE4')


def load_joint_diagnostic(path):
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if b'[task042_v26]' not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v26']
        if set(cfg)!={'schema_version','task042_v26'} or cfg['schema_version']!=1 or set(item)!={'stage','run_id','material_table_id','diagnostic_family'}:
            raise ValueError('explicit V26 schema required')
        if item['stage']!='DIAGNOSTIC' or not re.fullmatch(r'task042_v26_[a-z0-9_]+',item['run_id']):raise ValueError('V26 one diagnostic only')
        plan,design,material,fe=plan_and_operator();own=json.loads(PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('V26 original operator identity')
        if item['diagnostic_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('V26 material/family differs')
        if tuple(x['name'] for x in own['states'])!=NAMES or own['joint_blocks']!=[5,7] or own['joint_rows']!=3888:
            raise ValueError('two frozen states and fixed joint union only')
        from src.solvers.joint_block_window import require_live,ledger,auxiliary_wall
        clock=require_live(margin=1200);row=ledger()
        if row['closed'] or row['active'] is not None or row['runs']:raise ValueError('V26 closed/active/already consumed')
        timeout=min(900-row['actor_wall_seconds']-auxiliary_wall(),clock['heavy_remaining_seconds'])
        if timeout<=0:raise ValueError('V26 cumulative actor wall exhausted')
    except (OSError,ValueError,KeyError,RuntimeError,tomllib.TOMLDecodeError) as e:raise InputError(f'Task042 V26: {e}') from e
    return RunSpecification(identity=dict(model_id='task042_v26_fixed_joint_5_7_diagnostic',run_id=item['run_id'],batch='V26_'+FAMILY),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='joint_block_diagnostic_explicit_opt_in'),solver=dict(preconditioner='task042_v26_diagnostic'),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),output=dict(results_root='results/task042'),
        derived=dict(stage='V26-DIAGNOSTIC',environment_mode='pure',plan_sha256=file_hash(PLAN_PATH),physical_model_complete=True,
            physical_operator_sha256=plan['physical_model_sha256'],decoder_family=FAMILY,
            identity_hash_meaning='original S/b; two frozen cold residuals; one joint5/7 direction; no solver/reference'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def previous_name(stage):return None


def publish(name,path):
    from src.runners.task042_shared import write_json
    write_json(ARTIFACT_ROOT/(name+'.json'),dict(path=str(path),sha256=file_hash(path)))
