"""Six explicit V15 stages, frozen identities and one-way reference barrier."""

import json
import tomllib
from pathlib import Path

from src.io.autonomous_neural_head import plan_and_operator
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import file_hash

ARTIFACT_ROOT = ROOT/'benchmarks/artifacts/task042/v15'
PLAN_PATH = ROOT/'input/task042_neural_coarse_inverse/local_trace_representation_v15.json'
FAMILY = 'LOCAL_TRACE_REPRESENTATION_COMPARISON'
STAGES = dict(SETUP=('fe',1800), LOCAL_POLY=('pure',1800), LOCAL_NN=('pure',1800),
              UNION_POLY=('pure',3600), UNION_NN=('pure',2400), VERIFY=('fe',900))
CHAIN = dict(LOCAL_POLY='SETUP', LOCAL_NN='LOCAL_POLY', UNION_POLY='LOCAL_NN', UNION_NN='UNION_POLY')


def load_local_trace(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b'[task042_v15]' not in raw:
        return None
    try:
        cfg = tomllib.loads(raw.decode()); item = cfg['task042_v15']
        if set(cfg) != {'schema_version','task042_v15'} or cfg['schema_version'] != 1:
            raise ValueError('V15 explicit opt-in required')
        if set(item) != {'stage','run_id','material_table_id','decoder_family'}:
            raise ValueError('V15 keys differ')
        stage = item['stage']
        if stage not in STAGES or item['run_id'] != 'task042_v15_'+stage.lower():
            raise ValueError('unregistered V15 one-run stage')
        if item['decoder_family'] != FAMILY:
            raise ValueError('local block decoder family differs')
        plan, design, material, fe = plan_and_operator()
        own = json.loads(PLAN_PATH.read_text())
        if own['action_sha256'] != fe['packet']['sha256'] or own['physical_sha256'] != plan['physical_model_sha256']:
            raise ValueError('V15 frozen action/physics differs')
        if item['material_table_id'] != material.provenance['material_table_id']:
            raise ValueError('canonical material differs')
        if stage != 'VERIFY' and (ARTIFACT_ROOT/'VERIFY.json').exists():
            raise ValueError('V15 reference barrier: solver queue is closed')
        mode, timeout = STAGES[stage]
    except (OSError,ValueError,KeyError,tomllib.TOMLDecodeError) as error:
        raise InputError(f'Task042 V15 input/identity error: {error}') from error
    return RunSpecification(
        identity=dict(model_id='task042_v15_fixed_0p7nm_p3_micro',run_id=item['run_id'],batch='V15_LOCAL_TRACE_REPRESENTATION_COMPARISON'),
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],
        discretization=design['finite_element'],boundary=design['boundary'],
        method=dict(kind='local_trace_representation_explicit_opt_in'),
        solver=dict(preconditioner='task042_v15_'+stage.lower()),
        execution=dict(mpi_size=1,timeout_seconds=timeout,warning_memory_gib=12,terminate_memory_gib=16,require_zero_swap=True),
        output=dict(results_root='results/task042'),
        derived=dict(stage='V15-'+stage,environment_mode=mode,plan_sha256=file_hash(PLAN_PATH),
                     physical_model_complete=True,physical_operator_sha256=plan['physical_model_sha256'],
                     decoder_family=FAMILY,identity_hash_meaning='original V7 physical action/RHS; local block Qc; REF7 only after queue freeze'),
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),
        physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def previous_name(stage):
    if stage != 'VERIFY':
        return CHAIN.get(stage)
    for name in ('UNION_NN','UNION_POLY','LOCAL_NN','LOCAL_POLY','SETUP'):
        if (ARTIFACT_ROOT/(name+'.json')).exists():
            return name
    raise ValueError('no frozen V15 queue')


def publish(name,path):
    from src.runners.task042_shared import write_json
    entry = dict(path=str(path),sha256=file_hash(path))
    with (ARTIFACT_ROOT/'index_history.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(name=name,**entry))+'\n')
    write_json(ARTIFACT_ROOT/(name+'.json'),entry)


def read_result(name):
    entry = json.loads((ARTIFACT_ROOT/(name+'.json')).read_text())
    path = Path(entry['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path) != entry['sha256']:
        raise ValueError('V15 result path/hash differs')
    result = json.loads(path.read_text())
    if result['plan_sha256'] != file_hash(PLAN_PATH) or (result['reference_arrays_read'] and name != 'VERIFY'):
        raise ValueError('V15 plan/reference barrier differs')
    return result,path
