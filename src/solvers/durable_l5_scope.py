"""V68-only durable completion; V67 is a read-only qualified parent."""
import copy
import hashlib
import json
import time
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow
from .local_h_pilot_scope import one_run_overhead
from .local_p_mode_scope import auxiliary_wrapper_overhead

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v68'
PLAN=ROOT/'input/task042_neural_coarse_inverse/durable_l5_v68.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v68'
STAGES=('PREFLIGHT','SOLVE_COMPLETE','VERIFY_COST');SOLVES=('SOLVE_COMPLETE',)


class DurableWindow(AccuracyWindow):
    def launcher_overhead(self):
        runs=self.ledger()['runs']
        return (super().launcher_overhead()+one_run_overhead(self.TMP,runs)
                +auxiliary_wrapper_overhead(self.TMP,runs))

    def case_remaining(self,case='L5',*,active=False):
        book=self.ledger();used=0.
        for row in book['runs']:
            if row['role']!='SOLVE_COMPLETE':continue
            p=Path(row['folder'])/'run_summary.json'
            used+=json.loads(p.read_text())['launch_wall_seconds'] if p.exists() else row['elapsed_seconds']
        used+=one_run_overhead(self.TMP,book['runs'],roles=('SOLVE_COMPLETE',))
        if active and book['active'] is not None and book['active']['role']=='SOLVE_COMPLETE':
            used+=max(0.,time.monotonic()-book['active']['before_clock']['observed_monotonic'])
        return plan_record()['cumulative_case_seconds']['L5']-used

    def available_at_boundary(self,role):
        used=sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        cap=plan_record()['case_wall_seconds'].get(role,900)-used
        if role=='SOLVE_COMPLETE':cap=min(cap,self.case_remaining())
        return min(cap,self.total-self.charged_wall()-180,self.snapshot()['heavy_remaining_seconds']-180)

    def remaining(self,role):self.require_ready();return self.available_at_boundary(role)

    def require_live(self,*,heavy=True,margin=0):
        value=super().require_live(heavy=heavy,margin=margin)
        active=self.ledger()['active']
        if heavy and active is not None and active['role']=='SOLVE_COMPLETE' and self.case_remaining(active=True)<=margin:
            raise RuntimeError('V68 cumulative L5 deadline')
        return value


window=DurableWindow(ROOT/'tmp/task042/v68',label='V68',total=36000,
                    component=36000,auxiliary=36000,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='9934973deeed79d9dfc6aa40a69902960f191ef9' or p['stages']!=list(STAGES):raise ValueError('V68 authority')
    if p['assembly_row_cap']!=2000000 or p['total_loaded_seconds']!=36000 or p['cumulative_case_seconds']!={'L5':28800}:raise ValueError('V68 quota')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[32*2**30,512*2**30,50*2**30,512*2**20]:raise ValueError('V68 storage')
    for key,wanted in [('default',[64,80,96]),('L5',[256,320,384])]:
        if [p['memory_profiles'][key][k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=wanted:raise ValueError('V68 role memory')
    return p


def memory_budget(role):return dict(plan_record()['memory_profiles']['L5' if role=='SOLVE_COMPLETE' else 'default'])
def case_spec(role):return copy.deepcopy(plan_record()['cases']['L5'])


def physical_for(role):
    from .local_p_mode_scope import physical_for as prior
    p=copy.deepcopy(prior('SOLVE_COMPLETE'));s=case_spec(role)
    p['discretization'].update(degree=5,FE=s['independent'],rows=s['rows'],production_body_q=13,oracle_body_q=15)
    return p


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V68 stage identity')
    return json.loads(p.read_text())


def prepared_parent(role):
    if role!='SOLVE_COMPLETE':raise ValueError('V68 only read-only L5 PREPARE')
    from .local_p_mode_scope import stage as prior
    p=plan_record()['prepared_parent']
    if (p['namespace'],p['role'])!=('v67','PREPARE'):raise ValueError('wrong parent namespace/role')
    row=prior('PREPARE')
    if row['checkpoint']['sha256']!=p['checkpoint_manifest_sha256']:raise ValueError('wrong p5 body parent')
    return row


def numeric_attempts():
    return sum(json.loads(line).get('event')=='h_bounded_numeric_factor_begin'
               for p in ARTIFACT.glob('*/events.jsonl') for line in p.read_text().splitlines())


def require_stage(role):
    if role!='SOLVE_COMPLETE':raise ValueError('V68 unique solve')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V68 final queue frozen')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V68 preflight')
    if any(p.exists() for p in ARTIFACT.glob('*/returned_audit_pending.json')):raise RuntimeError('returned field: saved consumer only')
    n=numeric_attempts()
    if n>=2:raise RuntimeError('V68 numeric cap')
    if n:
        repair=window.TMP/'located_numeric_repair.json'
        if not repair.exists() or not json.loads(repair.read_text()).get('located_and_fixed'):
            raise RuntimeError('unknown interruption cannot authorize numeric replay')
    prepared_parent(role)
    if window.available_at_boundary(role)<plan_record()['forecast_numeric_upper_seconds']+4500:raise RuntimeError('V68 numeric/output reserve')


def numeric_guard(role,journal):
    remaining=min(window.snapshot()['heavy_remaining_seconds'],window.total-window.charged_wall(),window.case_remaining(active=True))
    needed=plan_record()['forecast_numeric_upper_seconds']+4500
    journal.event('v68_after_symbolic_time_admission',remaining_seconds=remaining,required_seconds=needed,admitted=remaining>=needed)
    if remaining<needed:raise RuntimeError('V68 numeric/output reserve')


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    from .local_p_mode_scope import implementation_hashes as prior
    names=list(prior())+[str(PLAN.relative_to(ROOT)),'src/solvers/durable_l5_scope.py',
        'src/solvers/durable_l5_study.py','src/runners/durable_stop_events.py',
        'src/test/test_durable_l5.py','benchmarks/collect_durable_l5.py','benchmarks/qualify_durable_l5.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
