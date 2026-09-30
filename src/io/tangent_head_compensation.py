"""Explicit, one-stage V13 inputs and hash-bound result inventory."""

import json
import tomllib
from pathlib import Path

from src.io.autonomous_neural_head import plan_and_operator
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.stable_head_varpro import PLAN_PATH
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import file_hash

V13_ROOT=ROOT/'benchmarks/artifacts/task042/v13'
STAGES={'TANGENT':('ml',1800),'RESPONSE':('ml',900),
        'COMPENSATE':('ml',10000),'VERIFY':('fe',900)}


def load_tangent_head(path):
    path=Path(path).resolve()
    try:
        raw=path.read_bytes()
    except OSError:
        return None
    if b'[task042_v13]' not in raw:
        return None
    try:
        cfg=tomllib.loads(raw.decode());item=cfg['task042_v13']
        if set(cfg)!={'schema_version','task042_v13'} or cfg['schema_version']!=1:
            raise ValueError('explicit V13 opt-in required')
        if set(item)!={'stage','run_id','material_table_id'} or item['stage'] not in STAGES:
            raise ValueError('unregistered V13 stage/keys')
        if item['run_id']!='task042_v13_'+item['stage'].lower():
            raise ValueError('one-stage run ID differs')
        plan,design,material,fe=plan_and_operator()
        if item['material_table_id']!=material.provenance['material_table_id']:
            raise ValueError('canonical material differs')
        if fe['packet']['sha256']!='9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454':
            raise ValueError('original action packet differs')
        mode,timeout=STAGES[item['stage']]
    except (ValueError,KeyError,OSError,tomllib.TOMLDecodeError) as error:
        raise InputError(f'Task042 V13 identity/input error: {error}') from error
    return RunSpecification(
        identity={'model_id':'task042_v13_fixed_0p7nm_p3_micro','run_id':item['run_id'],'batch':'V13_TANGENT_SCALE_AND_HEAD_COMPENSATION'},
        geometry=design['geometry'],materials=material.provenance,incidence=design['incidence'],
        discretization=design['finite_element'],boundary=design['boundary'],
        method={'kind':'tangent_head_compensation_explicit_opt_in'},
        solver={'preconditioner':'task042_v13_'+item['stage'].lower()},
        execution={'mpi_size':1,'timeout_seconds':timeout,'warning_memory_gib':12,
                   'terminate_memory_gib':16,'require_zero_swap':True},
        output={'results_root':'results/task042'},
        derived={'stage':'V13-'+item['stage'],'environment_mode':mode,
                 'plan_sha256':file_hash(PLAN_PATH),'physical_model_complete':True,
                 'physical_operator_sha256':plan['physical_model_sha256'],
                 'identity_hash_meaning':'unchanged V7 physical action and RHS; REF7 excluded before VERIFY'},
        source_path=path,raw_input_bytes=raw,input_sha256=file_hash(path),
        physical_model_sha256=plan['physical_model_sha256'],expected_output_parent=ROOT/'results/task042')


def publish(name,path):
    V13_ROOT.mkdir(parents=True,exist_ok=True)
    entry={'path':str(path),'sha256':file_hash(path)}
    with (V13_ROOT/'index_history.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(name=name,**entry))+'\n')
    (V13_ROOT/(name+'.json')).write_text(json.dumps(entry,indent=2)+'\n')


def read_result(name):
    entry=json.loads((V13_ROOT/(name+'.json')).read_text())
    path=Path(entry['path']).resolve()
    if not path.is_relative_to(V13_ROOT) or file_hash(path)!=entry['sha256']:
        raise ValueError('V13 result path/hash differs')
    result=json.loads(path.read_text())
    if result['plan_sha256']!=file_hash(PLAN_PATH) or result['reference_arrays_read'] and name!='VERIFY':
        raise ValueError('V13 plan or reference barrier differs')
    return result,path
