"""V72 consumes immutable V71 mathematics under its own capacity policy."""
import copy
import hashlib
import json
from pathlib import Path

from . import bounded_trace_scope as prior

ROOT = prior.ROOT
NAMESPACE = 'v72'
PLAN = ROOT / 'input/task042_neural_coarse_inverse/reused_trace_iterative_v72.json'
ARTIFACT = ROOT / 'benchmarks/artifacts/task042/v72'
STAGES = ('REUSE_ADMIT', 'ITERATE', 'VERIFY_COST')
SOLVES = ('ITERATE',)


class ReuseWindow(prior.IterativeWindow):
    def available_at_boundary(self, role):
        used = sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role'] == role)
        return min(plan_record()['case_wall_seconds'].get(role, 900) - used,
                   self.total - self.charged_wall() - 180,
                   self.snapshot()['heavy_remaining_seconds'] - 180)


window = ReuseWindow(ROOT / 'tmp/task042/v72', label='V72', total=43200,
                     component=43200, auxiliary=43200, probe=120, reserve=180, bootstrap=0)


def plan_record():
    p = json.loads(PLAN.read_text())
    if p['review_commit'] != '07d3f3d2aa6177cc015ac1a279900f7fbb14f4c7' or p['stages'] != list(STAGES):
        raise ValueError('V72 unique authority/stages')
    if hashlib.sha256((ROOT / 'docs/task042_neural_coarse_inverse/review_report_v70.md').read_bytes()).hexdigest() != p['review_sha256']:
        raise ValueError('V72 report identity')
    if (p['action_limit'], p['iteration_limit'], p['iteration_seconds'], p['numeric_qualification_seconds']) != (600, 256, 21600, 10800):
        raise ValueError('V72 fixed cumulative quotas')
    if p['factor_double_symbolic_sum_bytes'] != 80 * 2**30 or p['numeric_future_minimum_bytes'] != 8 * 2**30:
        raise ValueError('V72 explicit factor and future workspace policy')
    for role, values in [('default', [64, 80, 96]), ('ITERATE', [96, 112, 128])]:
        if [p['memory_profiles'][role][k] for k in ('planning_gib', 'warning_gib', 'sampled_stop_gib')] != values:
            raise ValueError('V72 role memory')
    if [p[k] for k in ('new_storage_bytes', 'task_storage_bytes', 'free_bytes', 'evidence_reserve_bytes')] != [32*2**30,632*2**30,50*2**30,512*2**20]:
        raise ValueError('V72 live storage')
    return p


def checked_json(receipt):
    p = Path(receipt['path']).resolve()
    if not p.is_relative_to(ROOT / 'benchmarks/artifacts/task042') or hashlib.sha256(p.read_bytes()).hexdigest() != receipt['sha256']:
        raise ValueError('V72 immutable parent identity')
    return json.loads(p.read_text())


def parent_preparation():
    return checked_json(plan_record()['reuse_parents']['PC_SETUP'])


def memory_budget(role):
    return dict(plan_record()['memory_profiles']['ITERATE' if role == 'ITERATE' else 'default'])


def case_spec(role):
    s = copy.deepcopy(plan_record()['cases']['P5']); s['memory_budget'] = memory_budget(role)
    return s


physical_for = prior.physical_for
method_for = prior.method_for
solver_for = prior.solver_for


def stage(role):
    r = json.loads((ARTIFACT / (role + '.json')).read_text())
    p = Path(r['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest() != r['sha256']:
        raise ValueError('V72 stage identity')
    return json.loads(p.read_text())


def iteration_record():
    return parent_preparation()


def require_stage(role):
    if (window.TMP / 'scientific_queue_frozen.json').exists():
        raise RuntimeError('V72 frozen: consumer only')
    if role == 'ITERATE' and not stage('REUSE_ADMIT')['pass_gate']:
        raise RuntimeError('V72 mathematical and new capacity admission required')


def verification_inventory_for(role):
    p = window.TMP / 'scientific_queue_frozen.json'
    return p if role == 'VERIFY_COST' and p.exists() else None


def implementation_hashes():
    names = list(prior.implementation_hashes()) + [str(PLAN.relative_to(ROOT)),
        'src/solvers/reused_trace_scope.py', 'src/solvers/reused_trace_admission.py',
        'benchmarks/qualify_reused_trace.py', 'src/test/test_reused_trace.py']
    return {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in sorted(set(names))}
