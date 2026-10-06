"""V53 explicit resources and forward p/h triangle; no old ledger is reopened."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
NAMESPACE='v53'
PLAN=ROOT/'input/task042_neural_coarse_inverse/phase_hp_completion_v53.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v53'
STAGES=('SETUP','A','B','M','VERIFY_COST')
SOLVES=('A','B','M')


class CompletionWindow(AccuracyWindow):
    def remaining(self,role):
        self.require_ready();p=plan_record()
        reserve=2000 if role in SOLVES else 180
        used=0.
        for row in self.ledger()['runs']:
            if row['role']!=role:continue
            path=Path(row['folder'])/'run_summary.json'
            used+=json.loads(path.read_text())['launch_wall_seconds'] if path.exists() else row['elapsed_seconds']
        return min(p['case_wall_seconds'].get(role,900)-used,
            self.total-self.charged_wall()-reserve,self.snapshot()['heavy_remaining_seconds']-reserve)


window=CompletionWindow(ROOT/'tmp/task042/v53',label='V53',total=18000,
    component=18000,auxiliary=18000,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='bc509db93ed905b945bab7cb21a5f6bbaaa23288' or p['stages']!=list(STAGES):
        raise ValueError('V53 authority/stage inventory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[12*2**30,58*2**30,50*2**30,256*2**20]:
        raise ValueError('V53 frozen/live storage inventory')
    if p['memory_budget']!=dict(planning_gib=32,warning_gib=40,sampled_stop_gib=48,neighbor_growth_gib=384,extra_cache_workspace_gib=2):
        raise ValueError('V53 explicit resource inventory')
    return p


def implementation_hashes():
    from .phase_notch_hp_scope import implementation_hashes as previous
    names=list(previous())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/phase_hp_completion_scope.py','src/solvers/phase_hp_completion.py',
        'src/solvers/phase_evaluation_cache.py','src/solvers/phase_tensor_checkpoint.py',
        'src/test/test_phase_hp_completion.py','benchmarks/qualify_phase_hp_completion.py',
        'benchmarks/collect_phase_hp_completion.py','src/runners/diagnostic_storage.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(role):
    pointer=json.loads((ARTIFACT/(role+'.json')).read_text());path=Path(pointer['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=pointer['sha256']:
        raise ValueError('V53 immutable stage identity')
    return json.loads(path.read_text())


def parent(role):
    p=plan_record()['parents'][role];pointer=ROOT/p['pointer']
    if hashlib.sha256(pointer.read_bytes()).hexdigest()!=p['pointer_sha256']:raise ValueError('V52 parent pointer changed')
    from .phase_notch_hp_scope import stage as old_stage
    r=old_stage(role)
    if r['arrays']['sha256']!=p['array_sha256'] or not r['equation_pass']:raise ValueError('V52 parent actual identity')
    return r


def read(role):return parent(role) if role in ('H','P') else stage(role)


def cached_comparisons():
    from .phase_hp_completion import cached_comparisons as collect
    return collect()


def case_spec(role):
    if role in ('SETUP','VERIFY_COST'):role='B'
    return dict(plan_record()['cases'][role])


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V53 solve queue frozen')
    if not stage('SETUP')['pass_gate']:raise RuntimeError('V53 actual preflight not qualified')
    if role=='M':
        admission=json.loads((window.TMP/'M_admission.json').read_text())
        if not admission['admitted'] or admission['parent_role']!='P':raise ValueError('V53 fixed P mode admission')
        for pair in ('P_A','P_B','A_B'):
            path=ARTIFACT/'comparisons'/(pair+'.json');r=json.loads(path.read_text())
            if not r['pass_gate'] or hashlib.sha256(path.read_bytes()).hexdigest()!=admission['comparison_hashes'][pair]:
                raise ValueError('V53 complete forward triangle not qualified')
    completed=sum((ARTIFACT/(s+'.json')).exists() and bool(stage(s).get('returned_arrays')) for s in SOLVES)
    if completed>=3:raise RuntimeError('V53 three complete solves consumed')
