"""One inexpensive uninterrupted Jacobi cycle; historical windows stay closed."""
import copy
import hashlib
import json
import time
from pathlib import Path

from src.runners.task042_shared import write_json
from . import controlled_trace_scope as historical

ROOT = historical.ROOT
NAMESPACE = 'v78'
PLAN = ROOT/'input/task042_neural_coarse_inverse/uninterrupted_jacobi_v78.json'
ARTIFACT = ROOT/'benchmarks/artifacts/task042/v78'
STAGES = ('PRECHECK', 'J128_CONTINUOUS', 'VERIFY_COST')
SOLVES = ('J128_CONTINUOUS',)
window = historical.ControlledWindow(ROOT/'tmp/task042/v78', label='V78',
    total=12600, component=12600, auxiliary=12600, probe=120, reserve=180, bootstrap=0)
fail_fast_fields = True
checked_json = historical.checked_json
physical_for = historical.physical_for
joint_equation_pass = historical.joint_equation_pass


def plan_record():
    p = json.loads(PLAN.read_text())
    report = ROOT/'docs/task042_neural_coarse_inverse/review_report_v76.md'
    if (p['review_commit'] != 'c126e154a7196cf427b4511a9e2e596fa5580993'
            or hashlib.sha256(report.read_bytes()).hexdigest() != p['review_sha256']
            or p['stages'] != list(STAGES)):
        raise ValueError('V78 unique authority')
    if (p['action_limit'], p['iteration_limit'], p['restart'], p['iteration_seconds'],
            p['maximum_new_complete_solves']) != (400, 256, 128, 3600, 1):
        raise ValueError('V78 fixed scientific quotas')
    if [p['memory_budget'][k] for k in ('planning_gib','warning_gib','sampled_stop_gib')] != [64,80,96]:
        raise ValueError('V78 memory is not the old PC allowance')
    return p


def memory_budget(role):
    return dict(plan_record()['memory_budget'])


def case_spec(role):
    s=copy.deepcopy(plan_record()['cases']['P5']); s['memory_budget']=memory_budget(role)
    return s


def method_for(role):
    return dict(kind='UNINTERRUPTED_COMPLEX_JACOBI_RIGHT_FGMRES',
        static_condensation=True, full_global_K=False, full_global_S=False,
        global_fine_factor=False, restart=128, max_it=256)


def solver_for(role):
    return dict(degree=5,kind='FGMRES',side='RIGHT',restart=128,max_it=256,
        retained_true_target=1e-11,PC_variant='COMPLEX_JACOBI',new_numeric=0)


def saved_json(receipt):
    path=Path(receipt['path']).resolve()
    if not any(path.is_relative_to(root) for root in (ARTIFACT,window.TMP)) or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:
        raise ValueError('V78 saved consumer identity')
    return json.loads(path.read_text())


def stage(role):
    return saved_json(json.loads((ARTIFACT/(role+'.json')).read_text()))


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists() and role!='VERIFY_COST':
        raise RuntimeError('V78 frozen: saved consumers only')
    if role in SOLVES:
        if not stage('PRECHECK')['pass_gate']: raise RuntimeError('V78 read-only asset gate')
        if (window.TMP/(role+'_candidate_frozen.json')).exists():
            raise RuntimeError('legal returned vector: consume only')
        if window.snapshot()['heavy_remaining_seconds'] < 3600+4500:
            raise RuntimeError('V78 full KSP and possible successful output reserve')


def begin_ksp(role,state):
    path=window.TMP/'KSP_attempts.json'
    if path.exists(): raise RuntimeError('V78 one normal KSP; explicit basis-loss repair required')
    write_json(path,dict(count=1,rows=[dict(role=role,source=state['source_sha'],monotonic=time.monotonic(),basis_lost=False)]))


def freeze_candidate(role, arrays, state):
    write_json(window.TMP/(role+'_candidate_frozen.json'),dict(role=role,retained=arrays,source=state['source_sha']))


def ksp_seconds():
    pointer=ARTIFACT/'J128_CONTINUOUS.json'
    return stage('J128_CONTINUOUS')['iteration']['ksp_solve_monotonic_seconds'] if pointer.exists() else 0.


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json'
    return p if role=='VERIFY_COST' and p.exists() else None


def effect_check(iteration,original,retained):
    rho=max(float(original),float(retained)); evaluated=iteration==128
    return dict(iteration=iteration,original_true=float(original),retained_true=float(retained),
        rho=rho,limit=.1 if evaluated else None,evaluated=evaluated,
        pass_gate=not evaluated or rho<=.1)


def iteration_policy():
    return dict(restart=128,max_it=256,residual_interval=32,
        evaluation_iterations=(0,32,64,96,128,160,192,224,256),
        retained_observation_iterations=(),effect_check=lambda row: effect_check(
            row['iteration'],row['true'],row['schur_true_relative_residual']))


def implementation_hashes():
    names=list(historical.implementation_hashes())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/uninterrupted_jacobi_scope.py','src/solvers/uninterrupted_jacobi_study.py',
        'benchmarks/qualify_uninterrupted_jacobi.py','src/test/test_uninterrupted_jacobi.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
