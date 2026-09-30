"""Five explicit V16 stages and a one-way, hash-bound reference barrier."""

import json
import tomllib
from pathlib import Path

from src.io.autonomous_neural_head import plan_and_operator
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import file_hash

ARTIFACT_ROOT = ROOT / 'benchmarks/artifacts/task042/v16'
PLAN_PATH = ROOT / 'input/task042_neural_coarse_inverse/augmented_trace_lsqr_v16.json'
FAMILY = 'AUGMENTED_FULL_TRACE_LSQR'
STAGES = dict(PREFLIGHT=('pure',1800), ZERO=('pure',2700), GPOLY=('pure',2700),
              GNN=('pure',2700), VERIFY=('fe',600))
CHAIN = dict(ZERO='PREFLIGHT', GPOLY='ZERO', GNN='GPOLY')


def load_augmented_trace(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b'[task042_v16]' not in raw:
        return None
    try:
        cfg = tomllib.loads(raw.decode()); item = cfg['task042_v16']
        if set(cfg) != {'schema_version','task042_v16'} or cfg['schema_version'] != 1:
            raise ValueError('V16 explicit opt-in required')
        if set(item) != {'stage','run_id','material_table_id','decoder_family'}:
            raise ValueError('V16 keys differ')
        stage = item['stage']
        if stage not in STAGES or item['run_id'] != 'task042_v16_'+stage.lower() or item['decoder_family'] != FAMILY:
            raise ValueError('unregistered V16 stage/family')
        plan, design, material, fe = plan_and_operator()
        own = json.loads(PLAN_PATH.read_text())
        if own['action_sha256'] != fe['packet']['sha256'] or own['physical_sha256'] != plan['physical_model_sha256']:
            raise ValueError('frozen original operator identity differs')
        if item['material_table_id'] != material.provenance['material_table_id']:
            raise ValueError('canonical material differs')
        if stage != 'VERIFY' and (ARTIFACT_ROOT/'VERIFY.json').exists():
            raise ValueError('V16 reference barrier: solver queue closed')
        mode, timeout = STAGES[stage]
        from src.solvers.augmented_trace_window import BUDGET_PATH
        budget = json.loads(BUDGET_PATH.read_text()) if BUDGET_PATH.exists() else None
        if stage in ('ZERO','GPOLY','GNN') and budget:
            timeout = budget['uniform_route_wall_seconds']
            # Preflight GPOLY setup is part of this route, never free.
            if stage == 'GPOLY' and (ARTIFACT_ROOT/'PREFLIGHT.json').exists():
                pre,_ = read_result('PREFLIGHT')
                timeout = max(1., timeout-pre.get('augmented_setup',{}).get('setup_seconds',0.))
    except (OSError,ValueError,KeyError,tomllib.TOMLDecodeError) as error:
        raise InputError(f'Task042 V16 input/identity error: {error}') from error
    return RunSpecification(
        identity=dict(model_id='task042_v16_fixed_0p7nm_p3_micro',run_id=item['run_id'],batch='V16_AUGMENTED_FULL_TRACE_LSQR'),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],
        discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='augmented_full_trace_lsqr_explicit_opt_in'),
        solver=dict(preconditioner='task042_v16_'+stage.lower()),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,
                       terminate_memory_gib=16,require_zero_swap=True),
        output=dict(results_root='results/task042'),
        derived=dict(stage='V16-'+stage,environment_mode=mode,plan_sha256=file_hash(PLAN_PATH),
                     physical_model_complete=True,physical_operator_sha256=plan['physical_model_sha256'],
                     decoder_family=FAMILY,route_budget=budget,
                     identity_hash_meaning='original S/b; Qc plus complete trace complement; REF7 only after queue freeze'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),
        physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def previous_name(stage):
    if stage == 'PREFLIGHT' and (ARTIFACT_ROOT/'PREFLIGHT.json').exists():
        return 'PREFLIGHT'  # A bounded wiring replay retains all previous fees.
    if stage != 'VERIFY':
        return CHAIN.get(stage)
    for name in ('GNN','GPOLY','ZERO','PREFLIGHT'):
        if (ARTIFACT_ROOT/(name+'.json')).exists():
            return name
    raise ValueError('no frozen V16 queue')


def publish(name, path):
    from src.runners.task042_shared import write_json
    entry = dict(path=str(path),sha256=file_hash(path))
    with (ARTIFACT_ROOT/'index_history.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(name=name,**entry))+'\n')
    write_json(ARTIFACT_ROOT/(name+'.json'),entry)


def read_result(name):
    entry = json.loads((ARTIFACT_ROOT/(name+'.json')).read_text())
    path = Path(entry['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path) != entry['sha256']:
        raise ValueError('V16 result ownership/hash differs')
    result = json.loads(path.read_text())
    if result['plan_sha256'] != file_hash(PLAN_PATH) or (result['reference_arrays_read'] and name != 'VERIFY'):
        raise ValueError('V16 plan/reference barrier differs')
    return result, path
