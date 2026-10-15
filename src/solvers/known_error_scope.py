"""V79 saved-only mathematical consumer; no PC or solve entry exists."""
import copy
import hashlib
import json
from pathlib import Path
from . import uninterrupted_jacobi_scope as prior

ROOT=prior.ROOT;NAMESPACE='v79'
PLAN=ROOT/'input/task042_neural_coarse_inverse/known_error_v79.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v79'
STAGES=('KNOWN_ERROR','EXPORT')
window=prior.historical.ControlledWindow(ROOT/'tmp/task042/v79',label='V79',
    total=2700,component=2700,auxiliary=2700,probe=120,reserve=120,bootstrap=0)
checked_json=prior.checked_json
physical_for=prior.physical_for


def plan_record():
    p=json.loads(PLAN.read_text())
    if (p['review_commit']!='1c355cf7bb8a856f5987e4b0b459f85cf8d657b2'
        or hashlib.sha256((ROOT/'docs/task042_neural_coarse_inverse/review_report_v77.md').read_bytes()).hexdigest()!=p['review_sha256']
        or p['stages']!=list(STAGES) or p['action_limit']!=8):
        raise ValueError('V79 immutable authority/quota')
    return p


def memory_budget(role):return dict(plan_record()['memory_budget'])
def case_spec(role):
    s=copy.deepcopy(plan_record()['cases']['P5']);s['memory_budget']=memory_budget(role)
    return s
def method_for(role):return dict(kind='KNOWN_SAME_DISCRETE_ERROR_DIAGNOSTIC',full_global_K=False,full_global_S=False,global_fine_factor=False)
def solver_for(role):return dict(degree=5,kind='SAVED_ONLY',max_it=0,new_numeric=0)
def verification_inventory_for(role):return None


def stage(role):
    v=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(v['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=v['sha256']:
        raise ValueError('V79 saved result identity')
    return json.loads(p.read_text())


def implementation_hashes():
    names=list(prior.implementation_hashes())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/known_error_scope.py','src/solvers/known_error_budget.py',
        'src/solvers/tetra_coefficient_action.py','src/solvers/tetra_polynomial_difference.py',
        'src/solvers/actual_error_diagnostics.py','src/solvers/physical_error_diagnostics.py',
        'benchmarks/qualify_known_error.py','src/test/test_known_error_budget.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
