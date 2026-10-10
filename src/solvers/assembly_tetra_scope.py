"""Immutable V70 authority and cumulative assembly/solve/action budget."""
import copy
import hashlib
import json
import time
from pathlib import Path
from .durable_l5_scope import DurableWindow
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v70'
PLAN=ROOT/'input/task042_neural_coarse_inverse/assembly_time_tetra_v70.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v70'
STAGES=('PREFLIGHT','BUILD','ACTION','SOLVE','VERIFY_COST');SOLVES=('SOLVE',)


class AssemblyWindow(DurableWindow):
    def case_remaining(self,case=None,*,active=False):
        # Every formal stage, test, failed probe and wrapper remains globally
        # charged. There is no fresh per-dat ten-hour case allowance.
        used=self.charged_wall()
        if active and self.ledger()['active'] is not None:
            used+=time.monotonic()-self.ledger()['active']['before_clock']['observed_monotonic']
        return self.total-used

    def available_at_boundary(self,role):
        used=sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        quota=plan_record()['case_wall_seconds'].get(role,900)-used
        return min(quota,self.case_remaining()-180,self.snapshot()['heavy_remaining_seconds']-180)

    def require_live(self,*,heavy=True,margin=0):
        return AccuracyWindow.require_live(self,heavy=heavy,margin=margin)


window=AssemblyWindow(ROOT/'tmp/task042/v70',label='V70',total=36000,component=36000,auxiliary=36000,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='7eb964ce194748d5c3510a4dc1798e312282aa57' or p['stages']!=list(STAGES):raise ValueError('V70 unique authority')
    if hashlib.sha256((ROOT/'docs/task042_neural_coarse_inverse/review_report_v68.md').read_bytes()).hexdigest()!=p['review_sha256']:raise ValueError('V70 report SHA256')
    if p['total_loaded_seconds']!=36000 or p['assembly_row_cap']!=1300000:raise ValueError('V70 time/retained row quota')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[40*2**30,600*2**30,50*2**30,512*2**20]:raise ValueError('V70 storage')
    for role,v in [('default',[64,80,96]),('BUILD',[256,320,384]),('SOLVE',[256,320,384])]:
        if [p['memory_profiles'][role][k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=v:raise ValueError('V70 scoped memory')
    return p


def memory_budget(role):return dict(plan_record()['memory_profiles'][role if role in ('BUILD','SOLVE') else 'default'])
def case_spec(role):return copy.deepcopy(plan_record()['cases']['P5'])


def physical_for(role):
    from .durable_l5_scope import physical_for as prior
    p=copy.deepcopy(prior('SOLVE_COMPLETE'))
    p['discretization'].update(degree=5,FE=1943745,rows=1944573,production_body_q=13,oracle_body_q=15)
    return p


def stage(role):
    r=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(r['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('V70 stage dependency')
    return json.loads(p.read_text())


def numeric_attempts():
    return sum(json.loads(line).get('event')=='h_bounded_numeric_factor_begin' for p in ARTIFACT.glob('*/events.jsonl') for line in p.read_text().splitlines())


def method_for(role):return dict(kind='ASSEMBLY_TIME_EXACT_TETRA_CELL_CONDENSATION',static_condensation=True,full_p5_space_retained=True,full_global_K=False)


def require_stage(role):
    if role not in ('BUILD','ACTION','SOLVE'):raise ValueError('V70 explicit stage')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V70 queue frozen')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V70 cell kernel qualification')
    if role in ('ACTION','SOLVE') and not stage('BUILD')['pass_gate']:raise RuntimeError('V70 original reduction qualification')
    if role=='SOLVE':
        if any(ARTIFACT.glob('*/retained_audit_pending.json')):raise RuntimeError('legal returned vector: saved-only consumer')
        n=numeric_attempts()
        if n>=2:raise RuntimeError('V70 numeric cap')
        if n:
            p=window.TMP/'located_numeric_repair.json'
            if not p.exists() or not json.loads(p.read_text()).get('located_and_fixed'):raise RuntimeError('V70 second numeric needs located repair/no return')


def numeric_guard(role,journal):
    remaining=min(window.snapshot()['heavy_remaining_seconds'],window.case_remaining(active=True))
    required=plan_record()['forecast_numeric_upper_seconds']+3600
    journal.event('v70_numeric_complete_output_time_admission',remaining_seconds=remaining,required_seconds=required,admitted=remaining>=required)
    if remaining<required:raise RuntimeError('V70 numeric and complete output reserve')


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    from .exact_tetra_scope import implementation_hashes as prior
    names=list(prior())+[str(PLAN.relative_to(ROOT)),'src/solvers/assembly_tetra_scope.py','src/solvers/assembly_tetra_study.py',
        'src/solvers/tetra_cell_kernel.py','src/solvers/tetra_assembly_packet.py','benchmarks/qualify_assembly_tetra.py',
        'benchmarks/collect_assembly_tetra.py','src/test/test_tetra_assembly_packet.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
