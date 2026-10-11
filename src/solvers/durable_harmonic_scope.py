"""V75 single immutable twelve-hour authority, with no H/I stage deadline."""
import copy
import hashlib
import json
from pathlib import Path

from src.runners.task042_shared import write_json
from . import harmonic_trace_scope as prior
from .bounded_trace_scope import IterativeWindow

ROOT=prior.ROOT;NAMESPACE='v75'
PLAN=ROOT/'input/task042_neural_coarse_inverse/durable_harmonic_v75.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v75'
STAGES=('PREFLIGHT','HARMONIC_PREPARE','HARMONIC','VERIFY_COST');SOLVES=('HARMONIC',)


class DurableHarmonicWindow(IterativeWindow):
    def case_remaining(self,case=None,*,active=False):
        # Same clock before, during and after a stage; nested timers are diagnostics.
        return self.snapshot()['heavy_remaining_seconds']

    def available_at_boundary(self,role):
        return min(self.snapshot()['heavy_remaining_seconds']-180,
            self.total-self.charged_wall()-180)

    def remaining(self,role):
        self.require_ready()
        return self.available_at_boundary(role)


window=DurableHarmonicWindow(ROOT/'tmp/task042/v75',label='V75',total=39600,
    component=39600,auxiliary=39600,probe=120,reserve=180,bootstrap=0)


def numeric_time_admission(remaining,numeric_upper,*,ksp_upper=10800,output_reserve=4500):
    needed=float(numeric_upper)+ksp_upper+output_reserve
    return dict(remaining_seconds=float(remaining),numeric_upper_seconds=float(numeric_upper),
        KSP_upper_seconds=ksp_upper,output_reserve_seconds=output_reserve,
        required_seconds=needed,admitted=remaining>=needed)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='02703c5ce56a18b134b50eded39645cb422a0d95' or p['stages']!=list(STAGES):raise ValueError('V75 unique authority')
    if hashlib.sha256((ROOT/'docs/task042_neural_coarse_inverse/review_report_v73.md').read_bytes()).hexdigest()!=p['review_sha256']:raise ValueError('V75 report identity')
    if (p['action_limit'],p['qualification_action_limit'],p['iteration_limit'],p['restart'],p['iteration_seconds'])!=(800,12,256,128,10800):raise ValueError('V75 fixed iterative limits')
    if p['numeric_future_minimum_bytes']!=12*2**30 or p['factor_double_symbolic_sum_bytes']!=80*2**30:raise ValueError('V75 bounded PC policy')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[32*2**30,696*2**30,50*2**30,512*2**20]:raise ValueError('V75 storage policy')
    if p['total_loaded_seconds']!=39600 or p['total_window_seconds']!=43200:raise ValueError('V75 single clock')
    if set(p['case_wall_seconds'].values())!={39600}:raise ValueError('V75 no old per-stage hard cap')
    return p


checked_json=prior.checked_json
physical_for=prior.physical_for
joint_equation_pass=prior.joint_equation_pass


def parent_preparation():return checked_json(plan_record()['reuse_parents']['PC_SETUP'])
def memory_budget(role):return dict(plan_record()['memory_profiles']['ITERATE' if role in ('HARMONIC_PREPARE','HARMONIC') else 'default'])
def case_spec(role):
    s=copy.deepcopy(plan_record()['cases']['P5']);s['memory_budget']=memory_budget(role);return s
def method_for(role):return prior.method_for(role)
def solver_for(role):return prior.solver_for(role)


def saved_json(receipt):
    path=Path(receipt['path']).resolve()
    if not any(path.is_relative_to(p) for p in (ARTIFACT,window.TMP)) or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('V75 saved path/hash')
    return json.loads(path.read_text())


def stage(role):return saved_json(json.loads((ARTIFACT/(role+'.json')).read_text()))
def iteration_record():
    h=stage('HARMONIC_PREPARE');p=copy.deepcopy(parent_preparation())
    p.update(coarse_matrix=h['coarse_matrix'],coarse_symbolic=h['coarse_symbolic'],harmonic_transfer=h['transfer'],Z=h['transfer']['skeleton'])
    return p


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V75 batch frozen: saved consumers only')
    if role=='HARMONIC_PREPARE' and not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V75 mathematical asset compatibility')
    if role=='HARMONIC':
        if not stage('HARMONIC_PREPARE')['pass_gate']:raise RuntimeError('V75 full harmonic mathematics and capacity')
        if (window.TMP/(role+'_candidate_frozen.json')).exists():raise RuntimeError('V75 returned candidate: saved consumer only')
        p=window.TMP/'KSP_attempts.json';n=json.loads(p.read_text())['count'] if p.exists() else 0
        if n>=2:raise RuntimeError('V75 one solve and one located continuation only')
        if n:
            repair=window.TMP/'located_iteration_repair.json'
            if not repair.exists() or not json.loads(repair.read_text()).get('located_and_fixed'):raise RuntimeError('V75 continuation requires located implementation repair')


def begin_ksp(role,state):
    p=window.TMP/'KSP_attempts.json';r=json.loads(p.read_text()) if p.exists() else dict(count=0,rows=[])
    if r['count']>=2:raise RuntimeError('V75 attempts exhausted')
    import time
    r['count']+=1;r['rows'].append(dict(role=role,source=state['source_sha'],monotonic=time.monotonic()));write_json(p,r)


def freeze_candidate(role,returned,state):write_json(window.TMP/(role+'_candidate_frozen.json'),dict(role=role,retained=returned,source=state['source_sha']))
def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    names=list(prior.implementation_hashes())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/durable_harmonic_scope.py','src/solvers/durable_harmonic_study.py',
        'src/solvers/durable_galerkin.py','src/test/test_durable_harmonic.py',
        'benchmarks/qualify_durable_harmonic.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
