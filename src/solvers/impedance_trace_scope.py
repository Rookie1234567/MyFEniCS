"""V77 physical impedance on fixed halo cells, separate from all closed historical windows."""
import copy
import hashlib
import json
import time

from src.runners.task042_shared import write_json
from . import reused_trace_scope as prior
from .bounded_trace_scope import IterativeWindow

ROOT = prior.ROOT
NAMESPACE = 'v77'
PLAN = ROOT / 'input/task042_neural_coarse_inverse/physical_impedance_v77.json'
ARTIFACT = ROOT / 'benchmarks/artifacts/task042/v77'
STAGES = ('PRECHECK', 'PREPARE', 'ITERATE', 'VERIFY_COST')
SOLVES = ('ITERATE',)
fail_fast_fields = True


class ControlledWindow(IterativeWindow):
    def available_at_boundary(self, role):
        return min(self.total - self.charged_wall() - 180,
                   self.snapshot()['heavy_remaining_seconds'] - 180)

    def remaining(self, role):
        self.require_ready()
        return self.available_at_boundary(role)


window = ControlledWindow(ROOT / 'tmp/task042/v77', label='V77', total=19800,
    component=19800, auxiliary=19800, probe=120, reserve=180, bootstrap=0)
numeric_policy = dict(seconds=3600, output_reserve_seconds=4500,
                      minimum_workspace_bytes=12 * 2**30)


def plan_record():
    extra = json.loads(PLAN.read_text())
    report = ROOT / 'docs/task042_neural_coarse_inverse/review_report_v75.md'
    if (extra['review_commit'] != 'fc02a8612f1aa31b2c52366cc645acee6b5f8daf'
            or hashlib.sha256(report.read_bytes()).hexdigest() != extra['review_sha256']
            or extra['stages'] != list(STAGES)):
        raise ValueError('V77 unique authority')
    if (extra['action_limit'], extra['iteration_limit'], extra['restart'],
            extra['iteration_seconds'], extra['maximum_new_complete_solves']) != (800, 256, 128, 7200, 1):
        raise ValueError('V77 fixed scientific quota')
    if [extra[k] for k in ('new_storage_bytes', 'task_storage_bytes', 'free_bytes', 'evidence_reserve_bytes')] != [24*2**30, 696*2**30, 50*2**30, 512*2**20]:
        raise ValueError('V77 storage quota')
    p = copy.deepcopy(prior.plan_record())
    p.update(extra)
    return p


checked_json = prior.checked_json
physical_for = prior.physical_for


def memory_budget(role):
    return dict(plan_record()['memory_profiles']['impedance' if role in ('PREPARE','ITERATE') else 'default'])


def case_spec(role):
    s = copy.deepcopy(plan_record()['cases']['P5'])
    s['memory_budget'] = memory_budget(role)
    return s


def method_for(role):
    return dict(prior.method_for(role), kind='PHYSICAL_IMPEDANCE_HALO_FGMRES', restart=128,
                PC_variant=role, no_harmonic_coarse=True)


def solver_for(role):
    return dict(prior.solver_for(role), restart=128,
                max_it=256, PC_variant=role)


def saved_json(receipt):
    path = __import__('pathlib').Path(receipt['path']).resolve()
    if not any(path.is_relative_to(root) for root in (ARTIFACT, window.TMP)) or hashlib.sha256(path.read_bytes()).hexdigest() != receipt['sha256']:
        raise ValueError('V77 saved-consumer identity')
    return json.loads(path.read_text())


def stage(role):
    return saved_json(json.loads((ARTIFACT / (role + '.json')).read_text()))


def parent_preparation():
    return checked_json(plan_record()['reuse_parents']['PC_SETUP'])


def joint_equation_pass(record):
    e = record['iteration']['final_evaluation']
    return bool(e['schur_true_relative_residual'] <= 1e-11
        and all(e[k] <= 1e-6 for k in ('true', 'native', 'augmented', 'port'))
        and all(e[k] <= 1e-10 for k in ('MPC_identity', 'rhs_q47_q63', 'recovery_identity', 'Schur_original_identity'))
        and record['audit']['pass_gate'])


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists() and role!='VERIFY_COST':
        raise RuntimeError('V77 frozen')
    if role in ('PREPARE','ITERATE') and not stage('PRECHECK')['pass_gate']:
        raise RuntimeError('V77 two actual halo/face qualification gates')
    if role=='ITERATE':
        if not stage('PREPARE')['pass_gate']: raise RuntimeError('V77 new symbolic aggregate capacity')
        if (window.TMP/'ITERATE_candidate_frozen.json').exists():
            raise RuntimeError('legal vector: consume only')


def begin_ksp(role,state):
    path=window.TMP/'KSP_attempts.json'
    if path.exists(): raise RuntimeError('V77 one formal KSP; explicit repair protocol required to resume')
    write_json(path,dict(count=1,rows=[dict(role=role,source=state['source_sha'],monotonic=time.monotonic())]))


def freeze_candidate(role, arrays, state):
    write_json(window.TMP / (role + '_candidate_frozen.json'),
               dict(role=role, retained=arrays, source=state['source_sha']))


def ksp_seconds():
    seconds = 0.
    for role in SOLVES:
        pointer = ARTIFACT / (role + '.json')
        if pointer.exists():
            record = stage(role)
            seconds += record.get('iteration', {}).get('ksp_solve_monotonic_seconds', 0.)
    return seconds


def verification_inventory_for(role):
    p = window.TMP / 'scientific_queue_frozen.json'
    return p if role == 'VERIFY_COST' and p.exists() else None


def implementation_hashes():
    names=list(prior.implementation_hashes())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/impedance_trace_scope.py','src/solvers/impedance_trace_study.py',
        'src/solvers/physical_impedance_patch.py','src/solvers/controlled_trace_study.py',
        'benchmarks/qualify_impedance_trace.py','benchmarks/collect_controlled_trace.py',
        'src/test/test_physical_impedance_patch.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def effect_check(iteration,original,retained):
    rho=max(float(original),float(retained))
    limits={32:.30,64:.10,128:.001}
    limit=limits.get(iteration)
    return dict(iteration=iteration,original_true=float(original),retained_true=float(retained),rho=rho,limit=limit,evaluated=limit is not None,pass_gate=limit is None or rho<=limit)
