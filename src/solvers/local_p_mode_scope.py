"""V67 independent p5 and p4-mode cases on one immutable tetra mesh."""
import copy
import hashlib
import json
import time
from pathlib import Path
from .independent_tetra_scope import TetraWindow
from .local_h_pilot_scope import one_run_overhead

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v67'
PLAN=ROOT/'input/task042_neural_coarse_inverse/local_p_modes_v67.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v67'
STAGES=('PREFLIGHT','PREPARE','SOLVE_COMPLETE','M4','VERIFY_COST')
SOLVES=('SOLVE_COMPLETE','M4');GROUPS={'L5':('PREPARE','SOLVE_COMPLETE'),'M4':('M4',)}


class LocalModeWindow(TetraWindow):
    def launcher_overhead(self):
        from .scattering_accuracy_scope import AccuracyWindow
        return AccuracyWindow.launcher_overhead(self)+one_run_overhead(self.TMP,self.ledger()['runs'])

    def case_used(self,case='L5',*,active=False):
        book=self.ledger();roles=GROUPS[case];used=0.
        for r in book['runs']:
            if r['role'] not in roles:continue
            p=Path(r['folder'])/'run_summary.json'
            used+=json.loads(p.read_text())['launch_wall_seconds'] if p.exists() else r['elapsed_seconds']
        used+=one_run_overhead(self.TMP,book['runs'],roles=roles)
        if active and book['active'] is not None and book['active']['role'] in roles:
            used+=max(0.,time.monotonic()-book['active']['before_clock']['observed_monotonic'])
        return used

    def case_remaining(self,case=None,*,active=False):
        current=self.ledger()['active']
        if case is None:case='M4' if current is not None and current['role']=='M4' else 'L5'
        return plan_record()['cumulative_case_seconds'][case]-self.case_used(case,active=active)

    def available_at_boundary(self,role):
        quota=plan_record()['case_wall_seconds'].get(role,900)
        for case,roles in GROUPS.items():
            if role in roles:quota=min(quota,self.case_remaining(case))
        return min(quota,self.total-self.charged_wall()-180,self.snapshot()['heavy_remaining_seconds']-180)

    def require_live(self,*,heavy=True,margin=0):
        v=super().require_live(heavy=heavy,margin=margin);a=self.ledger()['active']
        if heavy and a is not None and a['role'] in (*GROUPS['L5'],*GROUPS['M4']) and self.case_remaining(active=True)<=margin:
            raise RuntimeError('V67 cumulative case deadline')
        return v


window=LocalModeWindow(ROOT/'tmp/task042/v67',label='V67',total=39600,component=39600,auxiliary=39600,probe=120,reserve=180,bootstrap=0)


def memory_budget(role,p=None):
    p=json.loads(PLAN.read_text()) if p is None else p
    return dict(p['memory_profiles']['L5' if role in GROUPS['L5'] else 'M4' if role=='M4' else 'default'])


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='067da63d90a7c659f8c7c159a9a16644e5049b48' or p['stages']!=list(STAGES):raise ValueError('V67 authority')
    if p['assembly_row_cap']!=2000000 or p['total_loaded_seconds']!=39600 or p['cumulative_case_seconds']!={'L5':36000,'M4':10800}:raise ValueError('V67 quota')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[72*2**30,480*2**30,50*2**30,512*2**20]:raise ValueError('V67 storage')
    for role,wanted in [('PREPARE',[256,320,384]),('SOLVE_COMPLETE',[256,320,384]),('M4',[192,224,256]),('PREFLIGHT',[64,80,96])]:
        if [memory_budget(role,p)[k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=wanted:raise ValueError('V67 memory authority')
    return p


def stage(role):
    r=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(r['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('V67 stage identity')
    return json.loads(p.read_text())


def case_spec(role):
    key='M4' if role=='M4' else 'L5'
    s=copy.deepcopy(plan_record()['cases'][key])
    if key=='L5' and (ARTIFACT/'PREFLIGHT.json').exists():s.update(stage('PREFLIGHT')['actual_L5_spec'])
    return s


def physical_for(role):
    from .frozen_local_h_scope import physical_for as prior
    p=copy.deepcopy(prior('L4M' if role=='M4' else 'SOLVE_COMPLETE'));s=case_spec(role);degree=s['degree']
    p['discretization'].update(degree=degree,FE=s['independent'],rows=s['rows'],production_body_q=2*degree+3,oracle_body_q=2*degree+5)
    return p


def prepared_parent(role):
    if role=='M4':
        from .frozen_local_h_scope import stage as prior
        return prior('PREPARE')
    if role=='SOLVE_COMPLETE':return stage('PREPARE')
    raise ValueError('V67 explicit body producer role')


def numeric_attempts():
    return sum(json.loads(l).get('event')=='h_bounded_numeric_factor_begin' for p in ARTIFACT.glob('*/events.jsonl') for l in p.read_text().splitlines())


def require_stage(role):
    if role not in (*GROUPS['L5'],*GROUPS['M4']):raise ValueError('V67 planned stages')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V67 final queue frozen')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V67 qualification')
    if role in SOLVES:
        if numeric_attempts()>=2:raise RuntimeError('V67 two numeric attempts')
        if not prepared_parent(role).get('checkpoint'):raise RuntimeError('V67 explicit body parent missing')
        for p in ARTIFACT.glob('*/returned_audit_pending.json'):
            if json.loads(p.read_text()).get('role')==role:raise RuntimeError('returned field: saved consumer only')
        key='M4' if role=='M4' else 'L5'
        if window.available_at_boundary(role)<plan_record()['forecast_numeric_seconds'][key]+4500:raise RuntimeError('V67 numeric/output reserve')
    if role=='PREPARE' and not (window.TMP/'forecast_before_prepare.json').is_file():raise RuntimeError('V67 forecast before preparation')


def numeric_guard(role,journal):
    key='M4' if role=='M4' else 'L5'
    remaining=min(window.snapshot()['heavy_remaining_seconds'],window.total-window.charged_wall(),window.case_remaining(active=True))
    needed=plan_record()['forecast_numeric_seconds'][key]+4500
    journal.event('v67_after_symbolic_numeric_time_admission',remaining_seconds=remaining,required_seconds=needed,admitted=remaining>=needed)
    if remaining<needed:raise RuntimeError('V67 after-symbolic output reserve')


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    from .frozen_local_h_scope import implementation_hashes as prior
    r=prior();names=['src/solvers/local_p_mode_scope.py','src/solvers/local_p_mode_study.py','benchmarks/collect_local_p_modes.py',
        'benchmarks/qualify_local_p_modes.py','src/test/test_local_p_modes.py',str(PLAN.relative_to(ROOT))]
    r.update({n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names});return r
