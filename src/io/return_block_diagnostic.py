"""Explicit single-run two-cold-state return diagnostic; no other stage."""
import json,re,tomllib
from pathlib import Path
from src.io.task042_profile import ROOT
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.autonomous_neural_head import plan_and_operator
from src.io.block_direction_diagnostic import checked_json,physical_state
from src.solvers.neural_fe_action_packet import file_hash
from src.solvers.return_block_direction import FAMILY,NAMES,OUTER_BLOCKS

ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v27'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/return_block_direction_v27.json'


def load_return_diagnostic(path, *, namespace=None):
    import sys
    io=sys.modules[__name__] if namespace is None else namespace
    label=getattr(io,"LABEL","V27"); section="task042_"+label.lower()
    path=Path(path).resolve()
    try:raw=path.read_bytes()
    except OSError:return None
    if ('['+section+']').encode() not in raw:return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg[section]
        if set(cfg)!={'schema_version',section} or cfg['schema_version']!=1 or set(item)!={'stage','run_id','material_table_id','diagnostic_family'}:
            raise ValueError('explicit V27 schema required')
        if item['stage']!='DIAGNOSTIC' or not re.fullmatch('task042_'+label.lower()+'_[a-z0-9_]+',item['run_id']):raise ValueError('V27 one diagnostic only')
        plan,design,material,fe=plan_and_operator();own=json.loads(io.PLAN_PATH.read_text())
        if own['action_sha256']!=fe['packet']['sha256'] or own['physical_sha256']!=plan['physical_model_sha256']:raise ValueError('V27 original operator identity')
        if item['diagnostic_family']!=FAMILY or item['material_table_id']!=material.provenance['material_table_id']:raise ValueError('V27 material/family differs')
        if tuple(x['name'] for x in own['states'])!=NAMES or own['outer_blocks']!=list(OUTER_BLOCKS) or own['joint_blocks']!=[5,7] or own['joint_rows']!=3888:
            raise ValueError('fixed two cold states and return path only')
        window=io.window if hasattr(io,"window") else __import__("src.solvers.return_block_window",fromlist=["ledger"])
        require_live,ledger,auxiliary_wall=window.require_live,window.ledger,window.auxiliary_wall
        if label=="V28":
            for row in own["states"]:
                parent=row["parent_result"]
                if not parent["path"] or not re.fullmatch("[0-9a-f]{64}",parent["sha256"]):raise ValueError("nonempty parent_result required")
            attempt=window.TMP/"formal_admission_attempt.json"
            if attempt.exists() and not __import__("os").environ.get("TASK042_V28_ADMITTED_WORKER"):raise ValueError("V28 formal admission already consumed")
        clock=require_live(margin=900);book=ledger()
        if book['closed'] or book['active'] is not None or book['runs']:raise ValueError('V27 closed/active/already consumed')
        timeout=min(600-book['actor_wall_seconds']-auxiliary_wall(),clock['heavy_remaining_seconds'])
        if timeout<=0:raise ValueError('V27 cumulative actor plus auxiliary exhausted')
    except (OSError,ValueError,KeyError,RuntimeError,tomllib.TOMLDecodeError) as e:raise InputError(f'Task042 V27: {e}') from e
    return RunSpecification(identity=dict(model_id='task042_'+label.lower()+'_fixed_return_diagnostic',run_id=item['run_id'],batch=label+'_'+FAMILY),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='return_direction_explicit_opt_in'),solver=dict(preconditioner='task042_'+label.lower()+'_diagnostic'),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),output=dict(results_root='results/task042'),
        derived=dict(stage=label+'-DIAGNOSTIC',environment_mode='pure',plan_sha256=file_hash(io.PLAN_PATH),physical_model_complete=True,
            physical_operator_sha256=plan['physical_model_sha256'],decoder_family=FAMILY,
            identity_hash_meaning='original S/b; two frozen cold residuals; one J-O-J direction; rank<=3888; not a full-space PC'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def previous_name(stage):return None


def publish(name,path):
    from src.runners.task042_shared import write_json
    write_json(ARTIFACT_ROOT/(name+'.json'),dict(path=str(path),sha256=file_hash(path)))
