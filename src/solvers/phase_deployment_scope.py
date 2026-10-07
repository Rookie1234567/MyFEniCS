"""V58 immutable deployment and paired-gauge queue, all parent scopes read-only."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
NAMESPACE='v58'
PLAN=ROOT/'input/task042_neural_coarse_inverse/deployment_paired_gauge_v58.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v58'
STAGES=('P','S','C6','G6','G7','VERIFY_COST')
SOLVES=('C6','G6','G7')


class DeploymentWindow(AccuracyWindow):
    def remaining(self,role):
        self.require_ready();return self.available_at_boundary(role)

    def available_at_boundary(self,role):
        reserve=1800 if role in SOLVES else 180
        used=sum(json.loads((Path(r['folder'])/'run_summary.json').read_text()).get('launch_wall_seconds',r['elapsed_seconds'])
            if (Path(r['folder'])/'run_summary.json').exists() else r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,self.total-self.charged_wall()-reserve,
            self.snapshot()['heavy_remaining_seconds']-reserve)


window=DeploymentWindow(ROOT/'tmp/task042/v58',label='V58',total=21600,component=21600,auxiliary=21600,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='721c2731da0ce02ef528345f7b6ffcea459b033c' or p['stages']!=list(STAGES):raise ValueError('V58 authority')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[12*2**30,102*2**30,50*2**30,512*2**20]:raise ValueError('V58 storage')
    if p['memory_budget']!=dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96,neighbor_growth_gib=384,extra_cache_workspace_gib=2):raise ValueError('V58 memory')
    return p


def implementation_hashes():
    from .common_weak_phase_scope import implementation_hashes as previous
    names=list(previous())+[str(PLAN.relative_to(ROOT)),'src/solvers/phase_deployment_scope.py',
        'src/solvers/phase_deployment.py','src/solvers/phase_boundary_checkpoint.py','src/solvers/phase_deployment_defect.py','src/test/test_phase_deployment.py',
        'benchmarks/qualify_phase_deployment.py','benchmarks/collect_phase_deployment.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V58 stage identity')
    return json.loads(p.read_text())


def parent(role):
    from .common_weak_phase_scope import stage as prior_stage,parent as prior_parent
    if role=='B6':return prior_stage('B6')
    if role in ('R6','R7'):return prior_parent(role)
    raise ValueError('V58 only three fixed parent states')


def read(role):return parent(role) if role in ('B6','R6','R7') else stage(role)
def case_spec(role):return dict(plan_record()['cases'][role if role in SOLVES else 'C6'])
def physical_output_options():return dict(volume_backend='direct_phase_quadrature')


def numerical_carrier(cfg,spec):
    from .fixed_phase_fem import carrier
    shift=np.asarray(spec.get('gauge_shift',[0,0]),int)
    if shift.tolist() not in ([0,0],[0,1]):raise ValueError('one frozen reciprocal gauge only')
    return carrier(cfg)+np.r_[2*np.pi*shift/np.asarray([cfg.x_max-cfg.x_min,cfg.y_max-cfg.y_min]),0.]


def require_stage(role):
    if role not in SOLVES:raise ValueError('V58 three solves only')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V58 queue frozen')
    p=stage('P')
    if not p.get('gauge_control_pass'):raise RuntimeError('physical/numerical carrier controls not qualified')
    returned=[s for s in SOLVES if (ARTIFACT/(s+'.json')).exists() and stage(s).get('returned_arrays')]
    if role in returned and not (window.TMP/(role+'_post_resume.json')).exists():raise RuntimeError('returned physical state consume only')
    if len(returned)>=3 and not (window.TMP/(role+'_post_resume.json')).exists():raise RuntimeError('three solve slots consumed')
    if window.available_at_boundary(role)<plan_record()['forecast_case_seconds'][role]:raise RuntimeError('complete case plus audit reserve does not fit')


def raw_tensor_reader(role,bundle,journal):
    from .phase_reference_provider import PhaseReferenceProvider
    return PhaseReferenceProvider(bundle,journal)


def boundary_provider(cfg,setup,folder,journal):
    from .phase_boundary_checkpoint import StudyBoundaryProvider
    return StudyBoundaryProvider(cfg,setup,folder,journal)


def deployment_postprocess(*args,**kwargs):
    from .phase_deployment import complete_deployment
    return complete_deployment(*args,**kwargs)


def postprocessing_record(role):
    r=json.loads((window.TMP/(role+'_post_resume.json')).read_text());p=Path(r['minimal_state_receipt']['path'])
    if hashlib.sha256(p.read_bytes()).hexdigest()!=r['minimal_state_receipt']['sha256']:raise ValueError('V58 returned identity')
    old=json.loads(p.read_text())
    if r['arrays']!=old['arrays'] or r['case_spec']!=case_spec(role):raise ValueError('V58 return payload')
    return r


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None
