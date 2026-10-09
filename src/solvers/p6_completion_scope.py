"""V65 immutable scope: one P6, coefficient-first audit and sealed body CSR."""
import copy
import hashlib
import json
import time
from pathlib import Path
from .independent_tetra_scope import TetraWindow
from .fine_tetra_scope import implementation_hashes as parent_hashes
from .local_h_pilot_scope import one_run_overhead

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v65'
PLAN=ROOT/'input/task042_neural_coarse_inverse/coefficient_first_p6_v65.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v65'
STAGES=('PREFLIGHT','PREPARE','SOLVE_COMPLETE','VERIFY_COST')
SOLVES=('SOLVE_COMPLETE',);P6_ROLES=('PREPARE','SOLVE_COMPLETE')
CASE_CHARGE_ROLES=(*P6_ROLES,'VERIFY_COST')


class CompletionWindow(TetraWindow):
    def launcher_overhead(self):
        from .scattering_accuracy_scope import AccuracyWindow
        return AccuracyWindow.launcher_overhead(self)+one_run_overhead(self.TMP,self.ledger()['runs'])

    def case_used(self,*,active=False):
        book=self.ledger();used=0.
        for r in book['runs']:
            if r['role'] not in CASE_CHARGE_ROLES:continue
            p=Path(r['folder'])/'run_summary.json'
            used+=json.loads(p.read_text())['launch_wall_seconds'] if p.exists() else r['elapsed_seconds']
        # Include failed entry calls; already-covered supervised calls are not
        # charged again. The scope-wide paid ledger also includes every probe.
        used+=one_run_overhead(self.TMP,book['runs'],roles=CASE_CHARGE_ROLES)
        if active and book['active'] is not None and book['active']['role'] in CASE_CHARGE_ROLES:
            used+=max(0.,time.monotonic()-book['active']['before_clock']['observed_monotonic'])
        return used

    def case_remaining(self,*,active=False):return 36000-self.case_used(active=active)

    def available_at_boundary(self,role):
        allowed=min(self.case_remaining(),plan_record()['case_wall_seconds'][role]) if role in CASE_CHARGE_ROLES else plan_record()['case_wall_seconds'].get(role,900)
        return min(allowed,self.total-self.charged_wall()-180,self.snapshot()['heavy_remaining_seconds']-180)

    def require_live(self,*,heavy=True,margin=0):
        value=super().require_live(heavy=heavy,margin=margin)
        book=self.ledger()
        if heavy and book['active'] is not None and book['active']['role'] in CASE_CHARGE_ROLES and self.case_remaining(active=True)<=margin:
            raise RuntimeError('V65 cumulative P6 36000s case boundary')
        return value


window=CompletionWindow(ROOT/'tmp/task042/v65',label='V65',total=39600,component=39600,auxiliary=39600,probe=120,reserve=180,bootstrap=0)


def memory_budget(role,p=None):
    p=json.loads(PLAN.read_text()) if p is None else p
    return dict(p['memory_profiles']['P6' if role in P6_ROLES else 'default'])


def numeric_guard(role,journal):
    """Recheck the shared time reserve after symbolic, immediately before numeric."""
    if role!='SOLVE_COMPLETE':raise ValueError('V65 unique numeric role')
    remaining=min(window.snapshot()['heavy_remaining_seconds'],window.total-window.charged_wall(),
        window.case_remaining(active=True))
    reserve=plan_record()['numeric_audit_output_reserve_seconds']
    journal.event('p6_after_symbolic_numeric_time_admission',remaining_seconds=remaining,
        required_reserve_seconds=reserve,admitted=remaining>=reserve)
    if remaining<reserve:raise RuntimeError('V65 post-symbolic cumulative audit/output reserve')


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='1cc254583559969b3fdeb9385104011d5f479a50' or p['stages']!=list(STAGES):raise ValueError('V65 authority')
    if p['p6_cumulative_case_seconds']!=36000 or p['total_loaded_seconds']!=39600 or p['assembly_row_cap']!=1000000:raise ValueError('V65 fixed quota')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[64*2**30,344*2**30,50*2**30,512*2**20]:raise ValueError('V65 storage authority')
    for role,values in [('PREPARE',[192,224,256]),('SOLVE_COMPLETE',[192,224,256]),('PREFLIGHT',[64,80,96])]:
        if [memory_budget(role,p)[k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=values:raise ValueError('V65 scoped memory authority')
    return p


def case_spec(role):return copy.deepcopy(plan_record()['cases']['P6'])


def physical_for(role):
    # Exact same finite descriptor; never recompute from rounded summary data.
    from .local_h_pilot_scope import physical_for as prior
    return copy.deepcopy(prior('P6'))


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V65 stage identity')
    return json.loads(p.read_text())


def require_stage(role):
    if role not in P6_ROLES:raise ValueError('V65 fixed P6 stage')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V65 queue frozen')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V65 coefficient-first oracle not qualified')
    if role=='SOLVE_COMPLETE':
        if not stage('PREPARE').get('checkpoint'):raise RuntimeError('V65 body CSR not sealed')
        n=sum(json.loads(l).get('event')=='h_bounded_numeric_factor_begin' for p in ARTIFACT.glob('*/events.jsonl') for l in p.read_text().splitlines())
        if n>=2:raise RuntimeError('V65 numeric attempt cap')
        if list(ARTIFACT.glob('*/returned_audit_pending.json')):raise RuntimeError('returned coefficients exist: saved consumer only')
    if window.available_at_boundary(role)<=4500:raise RuntimeError('V65 cumulative case/output reserve')


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    r=parent_hashes()
    names=['src/solvers/p6_completion_scope.py','src/solvers/p6_completion_study.py','src/solvers/tetra_coefficient_action.py',
        'src/solvers/tetra_body_checkpoint.py','src/test/test_tetra_coefficient_action.py','src/test/test_p6_completion.py',
        'benchmarks/qualify_p6_completion.py','benchmarks/collect_p6_completion.py','src/solvers/local_h_pilot_scope.py',
        'input/task042_neural_coarse_inverse/p6_reference_local_h_v64.json',str(PLAN.relative_to(ROOT))]
    r.update({n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names})
    return r
