"""V73 route freezes and immutable reuse; no V72 state is reopened."""
import copy
import hashlib
import json
import time

from src.runners.task042_shared import write_json
from . import reused_trace_scope as prior

ROOT=prior.ROOT; NAMESPACE='v73'
PLAN=ROOT/'input/task042_neural_coarse_inverse/restart_feedback_v73.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v73'
STAGES=('PRECHECK','R128','B128','VERIFY_COST'); SOLVES=('R128','B128')


class FeedbackWindow(prior.ReuseWindow):
    def available_at_boundary(self,role):
        used=sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,
                   self.total-self.charged_wall()-180,
                   self.snapshot()['heavy_remaining_seconds']-180)


window=FeedbackWindow(ROOT/'tmp/task042/v73',label='V73',total=36000,
    component=36000,auxiliary=36000,probe=120,reserve=180,bootstrap=0)


def plan_record():
    extra=json.loads(PLAN.read_text())
    if (extra['review_commit']!='f1504cffd4bdcd7bfe025c0ff8e544298e1b7995'
            or extra['stages']!=list(STAGES)
            or hashlib.sha256((ROOT/'docs/task042_neural_coarse_inverse/review_report_v71.md').read_bytes()).hexdigest()!=extra['review_sha256']):
        raise ValueError('V73 unique authority')
    if (extra['action_limit'],extra['iteration_limit'],extra['iteration_seconds'],extra['restart'])!=(1600,256,10800,128):
        raise ValueError('V73 fixed action/iteration policy')
    if [extra[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[32*2**30,664*2**30,50*2**30,512*2**20]:
        raise ValueError('V73 storage policy')
    p=copy.deepcopy(prior.plan_record());p.update(extra)
    if p['numeric_future_minimum_bytes']!=12*2**30 or p['factor_double_symbolic_sum_bytes']!=80*2**30:
        raise ValueError('V73 factor and workspace policy')
    return p


checked_json=prior.checked_json
parent_preparation=prior.parent_preparation
iteration_record=parent_preparation
physical_for=prior.physical_for


def memory_budget(role):
    return dict(plan_record()['memory_profiles']['ITERATE' if role in SOLVES else 'default'])


def case_spec(role):
    s=copy.deepcopy(plan_record()['cases']['P5']);s['memory_budget']=memory_budget(role);return s


def method_for(role):
    return dict(prior.method_for(role),restart=128,PC_variant='balanced' if role=='B128' else 'additive')


def solver_for(role):
    return dict(prior.solver_for(role),restart=128,PC_variant='balanced' if role=='B128' else 'additive')


def stage(role):
    return checked_json(json.loads((ARTIFACT/(role+'.json')).read_text()))


def joint_equation_pass(r):
    e=r['iteration']['final_evaluation']
    return bool(e['schur_true_relative_residual']<=1e-11
        and all(e[k]<=1e-6 for k in ('true','native','augmented','port'))
        and all(e[k]<=1e-10 for k in ('MPC_identity','rhs_q47_q63','recovery_identity','Schur_original_identity'))
        and r['audit']['pass_gate'])


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V73 batch frozen')
    if role not in SOLVES:return
    if not stage('PRECHECK')['pass_gate']:raise RuntimeError('V73 immutable mathematics and new capacity gate')
    if (window.TMP/(role+'_candidate_frozen.json')).exists():raise RuntimeError('V73 returned route: consumer only')
    if role=='B128':
        if not (window.TMP/'R128_candidate_frozen.json').exists():raise RuntimeError('R128 must return before B128')
        if joint_equation_pass(stage('R128')):raise RuntimeError('R128 passed: B128 cancelled')
        d=json.loads((window.TMP/'balanced_qualification.json').read_text())
        if not d['pass_gate']:raise RuntimeError('B128 feedback mathematics not qualified')
    attempts=window.TMP/'KSP_attempts.json'
    n=json.loads(attempts.read_text())['count'] if attempts.exists() else 0
    if n>=2:raise RuntimeError('V73 two formal KSP attempts exhausted')
    if n and any(r['role']==role for r in json.loads(attempts.read_text())['rows']):
        repair=window.TMP/'located_iteration_repair.json'
        if not repair.exists() or not json.loads(repair.read_text()).get('located_and_fixed'):
            raise RuntimeError('V73 repeated KSP requires located implementation repair')


def begin_ksp(role,state):
    p=window.TMP/'KSP_attempts.json';r=json.loads(p.read_text()) if p.exists() else dict(count=0,rows=[])
    if r['count']>=2:raise RuntimeError('V73 KSP attempts exhausted')
    r['count']+=1;r['rows'].append(dict(role=role,source=state['source_sha'],monotonic=time.monotonic()))
    write_json(p,r)


def freeze_candidate(role,returned,state):
    write_json(window.TMP/(role+'_candidate_frozen.json'),dict(role=role,retained=returned,source=state['source_sha']))


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    names=list(prior.implementation_hashes())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/restart_feedback_scope.py','src/solvers/trace_feedback_diagnostic.py',
        'benchmarks/collect_restart_feedback.py','benchmarks/qualify_restart_feedback.py',
        'src/test/test_restart_feedback.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
