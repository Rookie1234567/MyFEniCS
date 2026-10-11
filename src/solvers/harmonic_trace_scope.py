"""V74 independent window and harmonic-only reuse authority."""
import copy
import hashlib
import json
import time

from src.runners.task042_shared import write_json
from . import reused_trace_scope as prior
from .restart_feedback_scope import joint_equation_pass

ROOT=prior.ROOT;NAMESPACE='v74';PLAN=ROOT/'input/task042_neural_coarse_inverse/harmonic_trace_v74.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v74'
STAGES=('PREFLIGHT','HARMONIC_PREPARE','HARMONIC','VERIFY_COST');SOLVES=('HARMONIC',)


class HarmonicWindow(prior.ReuseWindow):
    def case_remaining(self,case=None,*,active=False):
        role=self.ledger()['active']['role'] if active and self.ledger()['active'] else case
        if role=='HARMONIC':group=('HARMONIC',)
        elif role in ('PREFLIGHT','HARMONIC_PREPARE'):group=('PREFLIGHT','HARMONIC_PREPARE')
        else:return self.total-self.charged_wall()
        used=sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role'] in group)
        current=self.ledger()['active']
        current_seconds=max(0,time.monotonic()-current['before_clock']['observed_monotonic']) if current else 0.
        if active and current and current['role'] in group:
            used+=current_seconds
        limit=21600 if role=='HARMONIC' else 14400
        # charged_wall contains settled intervals. The live interval is already
        # in used above and is not unsegmented implementation time a second time.
        if role!='HARMONIC':
            elapsed=time.monotonic()-json.loads(self.WINDOW_PATH.read_text())['start_monotonic']
            used+=max(0,elapsed-self.charged_wall()-current_seconds)
            # H is first in the queue: setup, tests, waits and adaptation from
            # the first immutable clock all belong to its four-hour allowance.
            used=max(used,elapsed)
        return min(limit-used,self.total-self.charged_wall())

    def available_at_boundary(self,role):
        return min(plan_record()['case_wall_seconds'].get(role,900),self.case_remaining(role),
            self.total-self.charged_wall()-180,self.snapshot()['heavy_remaining_seconds']-180)


window=HarmonicWindow(ROOT/'tmp/task042/v74',label='V74',total=39600,component=39600,auxiliary=39600,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='6fcc95ea94b869d738c00c5f3e11c7025dd52f13' or p['stages']!=list(STAGES):raise ValueError('V74 authority')
    if hashlib.sha256((ROOT/'docs/task042_neural_coarse_inverse/review_report_v72.md').read_bytes()).hexdigest()!=p['review_sha256']:raise ValueError('V74 report changed')
    if (p['action_limit'],p['qualification_action_limit'],p['iteration_limit'],p['restart'],p['iteration_seconds'])!=(800,12,256,128,10800):raise ValueError('V74 fixed counters')
    if p['numeric_future_minimum_bytes']!=12*2**30 or p['factor_double_symbolic_sum_bytes']!=80*2**30:raise ValueError('V74 factor/future policy')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[32*2**30,696*2**30,50*2**30,512*2**20]:raise ValueError('V74 storage policy')
    return p


checked_json=prior.checked_json
parent_preparation=prior.parent_preparation
physical_for=prior.physical_for


def saved_json(receipt):
    from pathlib import Path
    path=Path(receipt['path']).resolve()
    if not any(path.is_relative_to(p) for p in (ARTIFACT,window.TMP)) or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('V74 saved path/hash')
    return json.loads(path.read_text())


def memory_budget(role):return dict(plan_record()['memory_profiles']['ITERATE' if role in ('HARMONIC_PREPARE','HARMONIC') else 'default'])
def case_spec(role):
    s=copy.deepcopy(plan_record()['cases']['P5']);s['memory_budget']=memory_budget(role);return s

def method_for(role):return dict(prior.method_for(role),restart=128,coarse='LOCAL_MAXWELL_HARMONIC_P2_SKELETON_PLUS_PORT',PC_variant='additive')
def solver_for(role):return dict(prior.solver_for(role),restart=128,PC_variant='additive')


def stage(role):
    receipt=json.loads((ARTIFACT/(role+'.json')).read_text())
    return saved_json(receipt)


def iteration_record():
    h=stage('HARMONIC_PREPARE');p=copy.deepcopy(parent_preparation())
    p.update(coarse_matrix=h['coarse_matrix'],coarse_symbolic=h['coarse_symbolic'],harmonic_transfer=h['transfer'],Z=h['transfer']['skeleton'])
    return p


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V74 batch frozen: consumer only')
    if role=='HARMONIC_PREPARE' and not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V74 original/parent qualification')
    if role=='HARMONIC':
        if not stage('HARMONIC_PREPARE')['pass_gate']:raise RuntimeError('V74 harmonic mathematics/capacity')
        if (window.TMP/(role+'_candidate_frozen.json')).exists():raise RuntimeError('V74 returned field: consumer only')
        p=window.TMP/'KSP_attempts.json'
        n=json.loads(p.read_text())['count'] if p.exists() else 0
        if n>=2:raise RuntimeError('V74 formal KSP attempt cap')
        if n:
            repair=window.TMP/'located_iteration_repair.json'
            if not repair.exists() or not json.loads(repair.read_text()).get('located_and_fixed'):raise RuntimeError('V74 continuation requires located repair')


def begin_ksp(role,state):
    p=window.TMP/'KSP_attempts.json';r=json.loads(p.read_text()) if p.exists() else dict(count=0,rows=[])
    if r['count']>=2:raise RuntimeError('V74 KSP attempts exhausted')
    r['count']+=1;r['rows'].append(dict(role=role,source=state['source_sha'],monotonic=time.monotonic()));write_json(p,r)


def freeze_candidate(role,returned,state):write_json(window.TMP/(role+'_candidate_frozen.json'),dict(role=role,retained=returned,source=state['source_sha']))
def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    names=list(prior.implementation_hashes())+[str(PLAN.relative_to(ROOT)),'src/solvers/harmonic_trace_scope.py',
        'src/solvers/harmonic_trace_coarse.py','src/solvers/harmonic_trace_study.py','src/test/test_harmonic_trace.py',
        'benchmarks/qualify_harmonic_trace.py','benchmarks/collect_harmonic_trace.py','benchmarks/collect_restart_feedback.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
