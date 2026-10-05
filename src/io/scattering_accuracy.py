"""One-run V50 opt-in descriptors, distinct physical and discretization IDs."""
import copy
import hashlib
import json
import re
import tomllib
from pathlib import Path

from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.solvers.scattering_accuracy_scope import ROOT, PLAN, STAGES, plan_record, selection


def load_scattering_accuracy(path):
    path = Path(path).resolve(); raw = path.read_bytes(); v = tomllib.loads(raw.decode())
    item = v.get('task042_v50', {})
    if set(v) != {'schema_version','task042_v50'} or v['schema_version'] != 1 or set(item) != {'stage','run_id'} or item.get('stage') not in STAGES or not re.fullmatch('task042_v50_[a-z0-9_]+',item.get('run_id','')):
        raise InputError('V50 explicit one-run schema')
    p = plan_record(); physical = copy.deepcopy(p['physical_descriptor']); role = item['stage']
    degree=5; grid='ORIGINAL'; case='COHORT'
    if role in ('FLAT_P5','FLAT_SELECTED'):case='FLAT'
    if role in ('NOTCH_LOW','NOTCH_HIGH','GRAM_CONTROL'):case='NOTCH'
    if role in ('FLAT_SELECTED','NOTCH_LOW','NOTCH_HIGH'):
        selected=selection(); grid=selected['grid']; degree=selected['low_degree'] if role=='NOTCH_LOW' else selected['high_degree']
    axes=physical['geometry']['axes_nm']
    if grid=='X2':axes['x']=[x for a,b in zip(axes['x'][:-1],axes['x'][1:]) for x in (a,(a+b)/2)]+[axes['x'][-1]]
    physical['geometry'].update(physical_case=case,notch_active=case=='NOTCH',grid=grid,
        flat_air_above_interface=case=='FLAT',cell_count=160 if grid=='X2' else 80)
    physical['discretization'].update(degree=degree,surface_quadrature_degree=47,
        independent_surface_reference_q=63,volume_form='original FFCx curlcurl-minus-complex-mass')
    for key in list(physical['discretization']):
        if key.startswith('expected_'):del physical['discretization'][key]
    return RunSpecification(identity={'model_id':'task042_v50_complete_accuracy','run_id':item['run_id'],'batch':p['batch']},
        geometry=physical['geometry'],materials=physical['materials'],incidence=physical['incidence'],
        discretization=physical['discretization'],boundary=physical['boundary'],
        method={'kind':'complete_scattering_accuracy_opt_in'},solver={'degree':degree},
        execution={'mpi_size':1,'timeout_seconds':3600,'warning_memory_gib':20,'terminate_memory_gib':24,'require_zero_swap':True},
        output={'results_root':'results/task042'},
        derived={'stage':role,'physical_case':case,'grid':grid,'preparation_scope':'v50','environment_mode':'fe',
            'storage_limits':{k:p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')},
            'plan_sha256':hashlib.sha256(PLAN.read_bytes()).hexdigest()},
        source_path=path,raw_input_bytes=raw,input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=hashlib.sha256(json.dumps(physical,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        expected_output_parent=ROOT/'results/task042')
