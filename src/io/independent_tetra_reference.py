"""Explicit full tetra one-run descriptor; never an active hex template."""
import hashlib
import json
import re
import tomllib
from pathlib import Path
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.solvers import independent_tetra_scope as scope


def load_tetra_reference(path):
    path=Path(path).resolve();raw=path.read_bytes();v=tomllib.loads(raw.decode());item=v.get('task042_v62',{})
    if set(v)!={'schema_version','task042_v62'} or v['schema_version']!=1 or set(item)!={'stage','run_id'} or item.get('stage') not in scope.STAGES or not re.fullmatch('task042_v62_[a-z0-9_]+',item.get('run_id','')):
        raise InputError('V62 explicit one-run tetra schema')
    role=item['stage'];p=scope.plan_record();physical=scope.physical_for(role);spec=scope.case_spec(role);m=p['memory_budget']
    extra={}
    frozen=scope.verification_inventory_for(role)
    if frozen is not None:extra['verification_inventory']={'path':str(frozen),'sha256':hashlib.sha256(frozen.read_bytes()).hexdigest()}
    resume=scope.window.TMP/(role+'_post_resume.json')
    if resume.exists():extra['postprocessing_resume']={'path':str(resume),'sha256':hashlib.sha256(resume.read_bytes()).hexdigest()}
    return RunSpecification(identity={'model_id':'task042_v62_full_tetra','run_id':item['run_id'],'batch':p['batch']},
        geometry=physical['geometry'],materials=physical['materials'],incidence=physical['incidence'],discretization=physical['discretization'],boundary=physical['boundary'],
        method={'kind':'FULL_UNCONDENSED_TETRA_N1CURL_PHASE_UFL'},solver={'degree':spec['degree'],'direct':'MUMPS','static_condensation':False},
        execution={'mpi_size':1,'timeout_seconds':p['case_wall_seconds'][role],
            'planning_memory_gib':m['planning_gib'],'warning_memory_gib':m['warning_gib'],'terminate_memory_gib':m['sampled_stop_gib'],'require_zero_swap':True},
        output={'results_root':'results/task042'},derived={'stage':role,'preparation_scope':'v62','environment_mode':'fe','physical_case':spec['case'],
            'case_spec':spec,'memory_budget':m,'grid':physical['geometry']['grid'],
            'storage_limits':{k:p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')},
            'plan_sha256':hashlib.sha256(scope.PLAN.read_bytes()).hexdigest(),**extra},source_path=path,raw_input_bytes=raw,input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=hashlib.sha256(json.dumps(physical,sort_keys=True,separators=(',',':')).encode()).hexdigest(),expected_output_parent=scope.ROOT/'results/task042')
