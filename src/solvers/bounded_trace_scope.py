"""Immutable V71 local/coarse iterative authority; all parents read-only."""
import copy
import hashlib
import json
import time
from pathlib import Path
from .durable_l5_scope import DurableWindow
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]; NAMESPACE='v71'
PLAN=ROOT/'input/task042_neural_coarse_inverse/bounded_trace_iterative_v71.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v71'
STAGES=('PREFLIGHT','PC_SETUP','ITERATE','VERIFY_COST'); SOLVES=('ITERATE',)


class IterativeWindow(DurableWindow):
    def case_remaining(self,case=None,*,active=False):
        used=self.charged_wall()
        current=self.ledger()['active']
        if active and current is not None:
            used+=time.monotonic()-current['before_clock']['observed_monotonic']
        return self.total-used

    def available_at_boundary(self,role):
        used=sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,
                   self.total-self.charged_wall()-180,
                   self.snapshot()['heavy_remaining_seconds']-180)

    def require_live(self,*,heavy=True,margin=0):
        return AccuracyWindow.require_live(self,heavy=heavy,margin=margin)


window=IterativeWindow(ROOT/'tmp/task042/v71',label='V71',total=43200,
                      component=43200,auxiliary=43200,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='41ee5ea56e19de48bee71792cbcd7081ba6e755c' or p['stages']!=list(STAGES):
        raise ValueError('V71 unique authority/stages')
    if hashlib.sha256((ROOT/'docs/task042_neural_coarse_inverse/review_report_v69.md').read_bytes()).hexdigest()!=p['review_sha256']:
        raise ValueError('V71 report identity')
    if (p['action_limit'],p['iteration_limit'],p['iteration_seconds'])!=(600,256,21600):
        raise ValueError('V71 cumulative action/iteration/time')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[32*2**30,632*2**30,50*2**30,512*2**20]:
        raise ValueError('V71 live/frozen storage')
    for role,values in [('default',[64,80,96]),('PC_SETUP',[96,112,128]),('ITERATE',[96,112,128])]:
        if [p['memory_profiles'][role][k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=values:
            raise ValueError('V71 role-specific memory')
    return p


def memory_budget(role):
    return dict(plan_record()['memory_profiles'][role if role in ('PC_SETUP','ITERATE') else 'default'])


def case_spec(role):
    s=copy.deepcopy(plan_record()['cases']['P5']);s['memory_budget']=memory_budget(role)
    return s


def physical_for(role):
    from .assembly_tetra_scope import physical_for as prior
    return copy.deepcopy(prior('SOLVE'))


def stage(role):
    r=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(r['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:
        raise ValueError('V71 stage pointer identity')
    return json.loads(p.read_text())


def method_for(role):
    return dict(kind='BOUNDED_TRACE_RIGHT_FGMRES_RAS_GALERKIN',static_condensation=True,
                full_global_K=False,full_global_S=False,global_fine_factor=False,
                restart=32,max_it=256,coarse='original960tet_p2_trace_Galerkin_plus828port')


def solver_for(role):
    return dict(degree=5,kind='FGMRES',side='RIGHT',restart=32,max_it=256,
                retained_true_target=1e-11,local_coarse_direct='MUMPS',global_fine_factor=False,
                static_condensation=True)


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists():
        raise RuntimeError('V71 frozen candidate: consumer only')
    if role in ('PC_SETUP','ITERATE') and not stage('PREFLIGHT')['pass_gate']:
        raise RuntimeError('V71 original local action qualification')
    if role=='ITERATE' and not stage('PC_SETUP')['pass_gate']:
        raise RuntimeError('V71 bounded owner/Galerkin/factor qualification')


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json'
    return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    from .assembly_tetra_scope import implementation_hashes as prior
    names=list(prior())+[str(PLAN.relative_to(ROOT)), 'src/solvers/bounded_trace_scope.py',
        'src/solvers/hot_tetra_trace.py','src/solvers/bounded_trace_pc.py',
        'src/solvers/bounded_trace_study.py','src/solvers/physical_retained_fgmres.py',
        'src/test/test_bounded_trace_iterative.py','benchmarks/qualify_bounded_trace.py',
        'benchmarks/collect_bounded_trace.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
