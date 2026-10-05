"""One explicit V52 case; all active dimensions describe the actual model."""
import copy
import hashlib
import json
import re
import tomllib
from pathlib import Path
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.solvers.phase_notch_hp_scope import ROOT,PLAN,STAGES,plan_record,case_spec,window


def descriptor(role):
    p=plan_record();physical=copy.deepcopy(p['physical_descriptor']);spec=case_spec(role)
    geo=physical['geometry'];geo.update(physical_case='NOTCH',notch_active=True,cells=spec['cells'] if 'cells' in spec else None,
        cell_count=spec.get('cells'),splits=spec['splits'],grid='x'.join(map(str,spec['splits'])) if spec['splits'] else 'CONDITIONAL_PENDING')
    if spec['splits']:
        for axis,factor in zip(('x','y','z'),spec['splits'],strict=True):
            a=geo['axes_nm'][axis]
            geo['axes_nm'][axis]=[l+(r-l)*j/factor for l,r in zip(a[:-1],a[1:]) for j in range(factor)]+[a[-1]]
        geo['notch_expected_changed_cells']=2*spec['splits'][0]*spec['splits'][1]*spec['splits'][2]
    physical['discretization'].update(degree=spec['degree'],expected_FE_independent=spec.get('independent'),
        expected_trace=spec.get('trace'),expected_internal=spec.get('internal'),condensed_rows=spec.get('rows'),
        unknown='TOTAL_ENVELOPE',representation='E=exp(i*kappa.x)*u',MPC='unit envelope x/y',
        surface_quadrature_degree=47,independent_surface_reference_q=63)
    count=spec.get('complete_modes',532)
    physical['boundary'].update(manual_m=[-11,11] if count==828 else [-9,9],
        manual_n=[-4,4] if count==828 else [-3,3],complete_modes=count)
    return physical,spec


def load_phase_notch_hp(path):
    path=Path(path).resolve();raw=path.read_bytes();v=tomllib.loads(raw.decode());item=v.get('task042_v52',{})
    if set(v)!={'schema_version','task042_v52'} or v['schema_version']!=1 or set(item)!={'stage','run_id'} or item.get('stage') not in STAGES or not re.fullmatch('task042_v52_[a-z0-9_]+',item.get('run_id','')):
        raise InputError('V52 explicit one-run schema')
    p=plan_record();role=item['stage'];physical,spec=descriptor(role);extra={}
    for name,key in ((role+'_post_resume.json','postprocessing_resume'),('scientific_queue_frozen.json','verification_inventory')):
        f=window.TMP/name
        if f.exists() and (key=='postprocessing_resume' or role=='VERIFY_COST'):
            extra[key]={'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
    return RunSpecification(identity={'model_id':'task042_v52_phase_notch_hp','run_id':item['run_id'],'batch':p['batch']},
        geometry=physical['geometry'],materials=physical['materials'],incidence=physical['incidence'],
        discretization=physical['discretization'],boundary=physical['boundary'],
        method={'kind':'fixed_phase_full3d_hp_accuracy_opt_in'},solver={'degree':spec['degree']},
        execution={'mpi_size':1,'timeout_seconds':p.get('case_wall_seconds',{}).get(role,3600),
            'warning_memory_gib':20,'terminate_memory_gib':24,'require_zero_swap':True},
        output={'results_root':'results/task042'},derived={'stage':role,'preparation_scope':'v52','environment_mode':'fe',
            'physical_case':'NOTCH','case_spec':spec,'grid':physical['geometry']['grid'],
            'storage_limits':{k:p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')},
            'plan_sha256':hashlib.sha256(PLAN.read_bytes()).hexdigest(),**extra},source_path=path,raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=hashlib.sha256(json.dumps(physical,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        expected_output_parent=ROOT/'results/task042')
