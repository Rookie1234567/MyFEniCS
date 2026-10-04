"""One-run V35 online/conditional verify entries; no historical state reader."""
import json
import re
import tomllib

from src.io.task042_profile import ROOT
from src.io.autonomous_neural_head import plan_and_operator
from src.io.block_direction_diagnostic import checked_json
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.solvers import full_input_online_window as window
from src.solvers.full_input_online import FAMILY
from src.solvers.neural_fe_action_packet import file_hash

PLAN_PATH = ROOT/'input/task042_neural_coarse_inverse/full_input_online_v35.json'
ARTIFACT_ROOT = ROOT/'benchmarks/artifacts/task042/v35'
LABEL = 'V35'


def load_online(path):
    from pathlib import Path
    path = Path(path).resolve()
    raw = path.read_bytes()
    if b'[task042_v35]' not in raw:
        return None
    try:
        cfg = tomllib.loads(raw.decode())
        item = cfg['task042_v35']
        if (set(cfg) != {'schema_version', 'task042_v35'} or cfg['schema_version'] != 1
                or set(item) != {'stage', 'run_id', 'material_table_id'}
                or item['stage'] not in ('ONLINE', 'VERIFY')
                or not re.fullmatch(r'task042_v35_[a-z0-9_]+', item['run_id'])):
            raise ValueError('V35 explicit stage schema')
        original, design, material, fe = plan_and_operator()
        own = json.loads(PLAN_PATH.read_text())
        if (own['action_sha256'] != fe['packet']['sha256']
                or own['physical_sha256'] != original['physical_model_sha256']
                or item['material_table_id'] != material.provenance['material_table_id']):
            raise ValueError('V35 frozen operator/material identity')
        window.require_live(margin=30)
        book = window.ledger()
        if book['closed'] or book['active'] is not None:
            raise ValueError('V35 closed/active window')
        if item['stage'] == 'ONLINE':
            window.require_qualification()
            for pointer in ARTIFACT_ROOT.glob('ONLINE.json'):
                prior = read_result('ONLINE')[0]
                if prior['status'] not in ('FAILED', 'RESOURCE_CONTROLLED_STOP'):
                    raise ValueError('V35 completed numerical trajectory cannot repeat')
            timeout = window.actor_timeout()
        else:
            prior, _ = read_result('ONLINE')
            if prior['status'] != 'ORIGINAL_EQUATION_PASS':
                raise ValueError('V35 physical verification requires original equation pass')
            if (ARTIFACT_ROOT/'VERIFY.json').exists():
                raise ValueError('V35 unique verification consumed')
            timeout = min(250-window.auxiliary_wall(), 870-window.charged_wall())
        if timeout <= 10:
            raise ValueError('V35 charged time budget exhausted')
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        raise InputError('Task042 V35: '+str(exc)) from exc
    return RunSpecification(identity=dict(model_id='task042_v35_fixed_p3_micro',
        run_id=item['run_id'], batch='V35_ONLINE_SEVEN_REGION'), geometry=design['geometry'],
        materials=material.provenance, incidence=design['incidence'], discretization=design['finite_element'],
        boundary=design['boundary'], method=dict(kind='fixed_block_online_explicit_opt_in'),
        solver=dict(preconditioner='task042_v35_'+item['stage'].lower()),
        execution=dict(mpi_size=1, timeout_seconds=timeout, warning_memory_gib=12,
                       terminate_memory_gib=16, require_zero_swap=True), output=dict(results_root='results/task042'),
        derived=dict(stage='V35-'+item['stage'], environment_mode='fe' if item['stage']=='VERIFY' else 'pure',
                     plan_sha256=file_hash(PLAN_PATH), physical_model_complete=True,
                     physical_operator_sha256=own['physical_sha256'],
                     identity_hash_meaning='unchanged physical S/b; fixed arbitrary-RHS seven-region PC; zero trace'),
        source_path=path, raw_input_bytes=raw, input_sha256=file_hash(path),
        physical_model_sha256=own['physical_sha256'], expected_output_parent=ROOT/'results/task042')


def previous_name(stage):
    return None


def publish(name, path):
    from src.runners.task042_shared import write_json
    write_json(ARTIFACT_ROOT/(name+'.json'), dict(path=str(path), sha256=file_hash(path)))


def read_result(name):
    pointer = json.loads((ARTIFACT_ROOT/(name+'.json')).read_text())
    return checked_json(pointer, ARTIFACT_ROOT), pointer
