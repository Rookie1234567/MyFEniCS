"""One input is one physical calculation in the fixed V51 window."""
import copy
import hashlib
import json
import re
import tomllib
from pathlib import Path
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.solvers.phase_explicit_accuracy_scope import ROOT,PLAN,STAGES,plan_record,window


def load_phase_explicit_accuracy(path):
    path=Path(path).resolve();raw=path.read_bytes();v=tomllib.loads(raw.decode());item=v.get('task042_v51',{})
    if set(v)!={'schema_version','task042_v51'} or v['schema_version']!=1 or set(item)!={'stage','run_id'} or item.get('stage') not in STAGES or not re.fullmatch('task042_v51_[a-z0-9_]+',item.get('run_id','')):
        raise InputError('V51 explicit one-run schema')
    p=plan_record();physical=copy.deepcopy(p['physical_descriptor']);role=item['stage']
    case='NOTCH' if role.startswith('NOTCH') else 'FLAT';degree=5 if role in ('FLAT_P5','NOTCH_P5','NOTCH_HPROBE') else 4
    grid='ORIGINAL'
    if role=='NOTCH_HPROBE':
        selection=ROOT/'tmp/task042/v51/h_selection.json'
        if selection.exists():
            pick=json.loads(selection.read_text());grid=pick['grid']
            axis=grid[0].lower();a=physical['geometry']['axes_nm'][axis]
            physical['geometry']['axes_nm'][axis]=[x for l,r in zip(a[:-1],a[1:]) for x in (l,(l+r)/2)]+[a[-1]]
        else:
            grid='PENDING_N5_INDICATOR'
            physical['geometry']['axes_status']='conditional slot only; no selected refined geometry yet'
    physical['geometry'].update(physical_case=case,notch_active=case=='NOTCH',grid=grid,cell_count=160 if grid!='ORIGINAL' else 80)
    physical['discretization']={'degree':degree,'surface_quadrature_degree':47,'independent_surface_reference_q':63,
        'surface_quadrature_rule':'all nonzero532; q47 separable / independent q63 Basix2D',
        'volume_form':'full curl(u)+i*kappa cross u in trial AND test',
        'unknown':'TOTAL_ENVELOPE','representation':'E=exp(i*kappa.x)*u; not polynomial projection',
        'kappa':'physical real (kx_inc,ky_inc,0)','MPC':'unit envelope x/y; physical incidence unchanged'}
    resume=window.TMP/(role+'_post_resume.json')
    resumed={}
    if resume.exists():
        record=json.loads(resume.read_text())
        if role!='NOTCH_P5' or record['role']!=role:
            raise InputError('V51 saved-return postprocessing inventory')
        resumed={'postprocessing_resume':{'path':str(resume),'sha256':hashlib.sha256(resume.read_bytes()).hexdigest(),
            'solve_source_sha':record['solve_source_sha'],'parent_array_sha256':record['arrays']['sha256'],
            'purpose':'audit/output of already returned saved physical state; no new solve'}}
    if role=='VERIFY_COST':
        frozen=window.TMP/'scientific_queue_frozen.json'
        resumed['verification_inventory']={'status':'PENDING_QUEUE_FREEZE'}
        if frozen.exists():
            f=json.loads(frozen.read_text())
            resumed['verification_inventory']={'path':str(frozen),'sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),
                'parents':{k:v['pointer']['sha256'] for k,v in f['completed_solves'].items()}}
    return RunSpecification(identity={'model_id':'task042_v51_phase_accuracy','run_id':item['run_id'],'batch':p['batch']},
        geometry=physical['geometry'],materials=physical['materials'],incidence=physical['incidence'],discretization=physical['discretization'],boundary=physical['boundary'],
        method={'kind':'fixed_phase_full3d_accuracy_opt_in'},solver={'degree':degree},
        execution={'mpi_size':1,'timeout_seconds':3600,'warning_memory_gib':20,'terminate_memory_gib':24,'require_zero_swap':True},
        output={'results_root':'results/task042'},derived={'stage':role,'physical_case':case,'grid':grid,'preparation_scope':'v51','environment_mode':'fe',
            'storage_limits':{k:p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')},'plan_sha256':hashlib.sha256(PLAN.read_bytes()).hexdigest(),**resumed},
        source_path=path,raw_input_bytes=raw,input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=hashlib.sha256(json.dumps(physical,sort_keys=True,separators=(',',':')).encode()).hexdigest(),expected_output_parent=ROOT/'results/task042')
