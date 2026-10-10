"""V69 immutable authority, one cold condensed case and independent p5 modes."""
import copy
import hashlib
import json
import time
from pathlib import Path

from .durable_l5_scope import DurableWindow
from .local_h_pilot_scope import one_run_overhead

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v69'
PLAN=ROOT/'input/task042_neural_coarse_inverse/exact_tetra_p5_dtn_v69.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v69'
STAGES=('PREFLIGHT','PREPARE_C5','C5','M5','VERIFY_COST');SOLVES=('C5','M5')
GROUPS={'C5':('PREPARE_C5','C5'),'M5':('M5',)}


class ExactWindow(DurableWindow):
    def case_remaining(self,case=None,*,active=False):
        book=self.ledger();current=book['active']
        if case is None:case='M5' if current and current['role']=='M5' else 'C5'
        roles=GROUPS[case];used=0.
        for row in book['runs']:
            if row['role'] not in roles:continue
            p=Path(row['folder'])/'run_summary.json'
            used+=json.loads(p.read_text())['launch_wall_seconds'] if p.exists() else row['elapsed_seconds']
        used+=one_run_overhead(self.TMP,book['runs'],roles=roles)
        if active and current is not None and current['role'] in roles:
            used+=max(0.,time.monotonic()-current['before_clock']['observed_monotonic'])
        return plan_record()['cumulative_case_seconds'][case]-used

    def available_at_boundary(self,role):
        used=sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        quota=plan_record()['case_wall_seconds'].get(role,900)-used
        if role in GROUPS['C5']:quota=min(quota,self.case_remaining('C5'))
        if role=='M5':quota=min(quota,self.case_remaining('M5'))
        return min(quota,self.total-self.charged_wall()-180,self.snapshot()['heavy_remaining_seconds']-180)

    def require_live(self,*,heavy=True,margin=0):
        # Invoke the generic window, not the V68-specific cumulative L5 guard.
        from .scattering_accuracy_scope import AccuracyWindow
        value=AccuracyWindow.require_live(self,heavy=heavy,margin=margin)
        active=self.ledger()['active']
        if heavy and active and active['role'] in (*GROUPS['C5'],*GROUPS['M5']) and self.case_remaining(active=True)<=margin:
            raise RuntimeError('V69 cumulative case deadline')
        return value


window=ExactWindow(ROOT/'tmp/task042/v69',label='V69',total=36000,
                   component=36000,auxiliary=36000,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='0f7d19e692b49ff06557d95891a843a3803fcdd5' or p['stages']!=list(STAGES):raise ValueError('V69 remote authority')
    report=ROOT/'docs/task042_neural_coarse_inverse/review_report_v67.md'
    if hashlib.sha256(report.read_bytes()).hexdigest()!=p['review_sha256']:raise ValueError('V69 report identity')
    if p['total_loaded_seconds']!=36000 or p['cumulative_case_seconds']!={'C5':25200,'M5':14400}:raise ValueError('V69 immutable time')
    if p['assembly_row_cap']!=2000000 or p['reduced_row_cap']!=1300000:raise ValueError('V69 full/reduced dimensions')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[48*2**30,560*2**30,50*2**30,512*2**20]:raise ValueError('V69 storage')
    for role,wanted in [('default',[64,80,96]),('C5',[256,320,384]),('M5',[256,320,384])]:
        if [p['memory_profiles'][role][k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=wanted:raise ValueError('V69 memory')
    return p


def memory_budget(role):return dict(plan_record()['memory_profiles'][role if role in ('C5','PREPARE_C5','M5') and role!='PREPARE_C5' else 'C5' if role=='PREPARE_C5' else 'default'])
def case_spec(role):return copy.deepcopy(plan_record()['cases']['M5' if role=='M5' else 'C5'])


def physical_for(role):
    from .durable_l5_scope import physical_for as old
    p=copy.deepcopy(old('SOLVE_COMPLETE'));s=case_spec(role)
    p['discretization'].update(degree=5,FE=s['independent'],rows=s['rows'],production_body_q=13,oracle_body_q=15)
    if role=='M5':p['boundary'].update(manual_m=[-13,13],manual_n=[-5,5],complete_modes=1188)
    return p


def stage(role):
    r=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(r['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('V69 stage binding')
    return json.loads(p.read_text())


def numeric_attempts():
    return sum(json.loads(line).get('event')=='h_bounded_numeric_factor_begin'
               for p in ARTIFACT.glob('*/events.jsonl') for line in p.read_text().splitlines())


def method_for(role):
    decision=window.TMP/'M5_backend.json'
    full=role=='M5' and decision.exists() and json.loads(decision.read_text())['backend']=='FULL_UNCONDENSED'
    return dict(kind='FULL_UNCONDENSED_TETRA_N1CURL_PHASE_UFL' if full else 'EXACT_ASSEMBLED_TETRA_CELL_CONDENSATION',
                static_condensation=not full,full_p5_space_retained=True)


def require_stage(role):
    if role not in ('PREPARE_C5','C5','M5'):raise ValueError('V69 explicit calculation')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V69 final queue frozen')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V69 preflight')
    if role=='C5' and not stage('PREPARE_C5')['pass_gate']:raise RuntimeError('V69 reduction qualification')
    if role=='M5' and not (window.TMP/'M5_backend.json').exists():raise RuntimeError('V69 explicit mode backend decision')
    if role in SOLVES:
        for p in ARTIFACT.glob('*/returned_audit_pending.json'):
            r=json.loads(p.read_text())
            if r['role']==role:raise RuntimeError('returned field: saved consumer only')
        count=numeric_attempts()
        if count>=3:raise RuntimeError('V69 numeric cap')
        if count>=2:
            repair=window.TMP/'located_numeric_repair.json'
            if not repair.exists() or not json.loads(repair.read_text()).get('located_and_fixed'):raise RuntimeError('V69 third attempt only located repair')


def numeric_guard(role,journal):
    remaining=min(window.snapshot()['heavy_remaining_seconds'],window.total-window.charged_wall(),window.case_remaining(active=True))
    needed=plan_record()['forecast_numeric_upper_seconds']+3600
    journal.event('v69_numeric_output_time_admission',remaining_seconds=remaining,required_seconds=needed,admitted=remaining>=needed)
    if remaining<needed:raise RuntimeError('V69 numeric/full output reserve')


def verification_inventory_for(role):
    p=window.TMP/('scientific_queue_frozen.json' if (window.TMP/'scientific_queue_frozen.json').exists() else 'consumer_c5_inventory.json')
    return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    from .durable_l5_scope import implementation_hashes as prior
    names=list(prior())+[str(PLAN.relative_to(ROOT)),'src/solvers/exact_tetra_scope.py',
        'src/solvers/exact_tetra_condensation.py','src/solvers/exact_tetra_study.py',
        'src/solvers/hcurl_cell_static_condensation.py','benchmarks/collect_exact_tetra.py',
        'benchmarks/qualify_exact_tetra.py','src/test/test_exact_tetra_condensation.py',
        'src/postprocessing/saved_interface_diagnosis.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
