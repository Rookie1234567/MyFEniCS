"""V66 consumes the immutable V64 mesh; separate case and campaign budgets."""
import copy
import hashlib
import json
import time
from pathlib import Path
from .independent_tetra_scope import TetraWindow
from .local_h_pilot_scope import one_run_overhead

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v66'
PLAN=ROOT/'input/task042_neural_coarse_inverse/frozen_local_h_v66.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v66'
STAGES=('PREFLIGHT','PREPARE','SOLVE_COMPLETE','COMPARE_GATE','L4M','VERIFY_COST')
SOLVES=('SOLVE_COMPLETE','L4M');L4_ROLES=('PREPARE',*SOLVES)
GROUPS={'L4F':('PREPARE','SOLVE_COMPLETE','COMPARE_GATE'),'L4M':('L4M',)}


class FrozenWindow(TetraWindow):
    def launcher_overhead(self):
        from .scattering_accuracy_scope import AccuracyWindow
        return AccuracyWindow.launcher_overhead(self)+one_run_overhead(self.TMP,self.ledger()['runs'])

    def case_used(self,case='L4F',*,active=False):
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
        if case is None:case='L4M' if current is not None and current['role']=='L4M' else 'L4F'
        return plan_record()['cumulative_case_seconds'][case]-self.case_used(case,active=active)

    def available_at_boundary(self,role):
        quota=plan_record()['case_wall_seconds'].get(role,900)
        if role in GROUPS['L4F']:quota=min(quota,self.case_remaining('L4F'))
        if role=='L4M':quota=min(quota,self.case_remaining('L4M'))
        return min(quota,self.total-self.charged_wall()-180,self.snapshot()['heavy_remaining_seconds']-180)

    def require_live(self,*,heavy=True,margin=0):
        value=super().require_live(heavy=heavy,margin=margin);current=self.ledger()['active']
        if heavy and current is not None and current['role'] in (*GROUPS['L4F'],*GROUPS['L4M']) and self.case_remaining(active=True)<=margin:
            raise RuntimeError('V66 cumulative case deadline')
        return value


window=FrozenWindow(ROOT/'tmp/task042/v66',label='V66',total=36000,component=36000,auxiliary=36000,probe=120,reserve=180,bootstrap=0)


def memory_budget(role,p=None):
    p=json.loads(PLAN.read_text()) if p is None else p
    return dict(p['memory_profiles']['L4' if role in L4_ROLES else 'default'])


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='5a6689d321b74233b104c8b0ce5bab7d7bd8e39e' or p['stages']!=list(STAGES):raise ValueError('V66 authority')
    if p['assembly_row_cap']!=1050000 or p['total_loaded_seconds']!=36000 or p['cumulative_case_seconds']!={'L4F':28800,'L4M':10800}:raise ValueError('V66 fixed quota')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[64*2**30,408*2**30,50*2**30,512*2**20]:raise ValueError('V66 storage authority')
    for role,wanted in [('PREPARE',[192,224,256]),('SOLVE_COMPLETE',[192,224,256]),('L4M',[192,224,256]),('PREFLIGHT',[64,80,96])]:
        if [memory_budget(role,p)[k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=wanted:raise ValueError('V66 memory authority')
    return p


def case_spec(role):return copy.deepcopy(plan_record()['cases']['L4M' if role=='L4M' else 'L4F'])


def physical_for(role):
    from .local_h_pilot_scope import physical_for as parent
    p=copy.deepcopy(parent('L4'));s=case_spec(role)
    p['discretization'].update(degree=4,FE=s['independent'],rows=s['rows'],production_body_q=11,oracle_body_q=13)
    n=s['complete_modes'];mm,nn={828:(11,4),1188:(13,5)}[n]
    p['boundary'].update(complete_modes=n,manual_m=[-mm,mm],manual_n=[-nn,nn])
    return p


def stage(role):
    r=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(r['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('V66 stage identity')
    return json.loads(p.read_text())


def numeric_attempts():
    return sum(json.loads(l).get('event')=='h_bounded_numeric_factor_begin' for p in ARTIFACT.glob('*/events.jsonl') for l in p.read_text().splitlines())


def require_stage(role):
    if role not in L4_ROLES:raise ValueError('V66 planned body/numeric stages')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V66 final queue frozen')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V66 p4/frozen mesh qualification')
    if role in SOLVES:
        if numeric_attempts()>=2:raise RuntimeError('V66 maximum two numeric attempts including failures')
        if not stage('PREPARE').get('checkpoint'):raise RuntimeError('V66 body checkpoint missing')
        if list(ARTIFACT.glob('*/returned_audit_pending.json')):
            for p in ARTIFACT.glob('*/returned_audit_pending.json'):
                if json.loads(p.read_text()).get('role')==role:raise RuntimeError('returned coefficients: saved consumer only')
    if role=='L4M':
        d=stage('COMPARE_GATE')
        if not d['joint_space_pass'] or not d['complete_physical_pass']:raise RuntimeError('V66 M not admitted by joint spatial/physical evidence')
    if role=='PREPARE' and not (window.TMP/'forecast_before_prepare.json').is_file():raise RuntimeError('V66 forecast must precede preparation')
    if role in SOLVES and window.available_at_boundary(role)<plan_record()['forecast_numeric_seconds']['L4M' if role=='L4M' else 'L4F']+4500:
        raise RuntimeError('V66 complete numeric and audit/output reserve')


def numeric_guard(role,journal):
    if role not in SOLVES:raise ValueError('V66 numeric role')
    remaining=min(window.snapshot()['heavy_remaining_seconds'],window.total-window.charged_wall(),window.case_remaining(active=True))
    required=plan_record()['forecast_numeric_seconds']['L4M' if role=='L4M' else 'L4F']+4500
    journal.event('v66_after_symbolic_numeric_time_admission',remaining_seconds=remaining,required_seconds=required,admitted=remaining>=required)
    if remaining<required:raise RuntimeError('V66 after-symbolic numeric/output reserve')


def verification_inventory_for(role):
    name='l4f_comparison_inventory.json' if role=='COMPARE_GATE' else 'scientific_queue_frozen.json'
    p=window.TMP/name;return p if role in ('COMPARE_GATE','VERIFY_COST') and p.exists() else None


def implementation_hashes():
    from .p6_completion_scope import implementation_hashes as parent
    r=parent();names=['src/solvers/frozen_local_h_scope.py','src/solvers/frozen_local_h_study.py',
        'benchmarks/collect_frozen_local_h.py','benchmarks/qualify_frozen_local_h.py','src/solvers/tetra_polynomial_difference.py','src/postprocessing/paired_field_norms.py',
        'src/test/test_frozen_local_h.py',str(PLAN.relative_to(ROOT))]
    r.update({n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names});return r
