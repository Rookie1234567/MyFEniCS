"""Immutable V54 p/order-DtN scope; historical namespaces stay closed."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
NAMESPACE='v54'
PLAN=ROOT/'input/task042_neural_coarse_inverse/p_order_dtn_v54.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v54'
STAGES=('D','R7','R6','C','VERIFY_COST')
SOLVES=('R7','R6','C')


class SeparationWindow(AccuracyWindow):
    def remaining(self,role):
        self.require_ready();p=plan_record();reserve=2000 if role in SOLVES else 180
        used=0.
        for row in self.ledger()['runs']:
            if row['role']!=role:continue
            path=Path(row['folder'])/'run_summary.json'
            used+=json.loads(path.read_text())['launch_wall_seconds'] if path.exists() else row['elapsed_seconds']
        return min(p['case_wall_seconds'].get(role,900)-used,self.total-self.charged_wall()-reserve,
            self.snapshot()['heavy_remaining_seconds']-reserve)


window=SeparationWindow(ROOT/'tmp/task042/v54',label='V54',total=18000,
    component=18000,auxiliary=18000,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='bcc059f63478b468dff29a8a70d69a5710f2ca4d' or p['stages']!=list(STAGES):raise ValueError('V54 authority/stage inventory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[10*2**30,68*2**30,50*2**30,256*2**20]:raise ValueError('V54 frozen storage inventory')
    if p['memory_budget']!=dict(planning_gib=32,warning_gib=40,sampled_stop_gib=48,neighbor_growth_gib=384,extra_cache_workspace_gib=2):raise ValueError('V54 live memory contract')
    return p


def implementation_hashes():
    from .phase_hp_completion_scope import implementation_hashes as previous
    names=list(previous())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/phase_p_order_dtn_scope.py','src/solvers/phase_p_order_dtn.py',
        'src/solvers/phase_p_order_consistency.py','src/solvers/phase_raw_tensor_reader.py',
        'src/test/test_phase_p_order_dtn.py','benchmarks/qualify_phase_p_order_dtn.py',
        'benchmarks/collect_phase_p_order_dtn.py','benchmarks/check_phase_p_order_dtn.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(role):
    pointer=json.loads((ARTIFACT/(role+'.json')).read_text());path=Path(pointer['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=pointer['sha256']:raise ValueError('V54 immutable stage identity')
    return json.loads(path.read_text())


def parent(role):
    spec=plan_record()['parents'][role];pointer=ROOT/spec['pointer']
    if hashlib.sha256(pointer.read_bytes()).hexdigest()!=spec['pointer_sha256']:raise ValueError('V54 parent pointer changed')
    row=json.loads(pointer.read_text());path=Path(row['path']).resolve()
    if not path.is_relative_to(ROOT/'benchmarks/artifacts/task042'/spec['namespace']) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V54 parent result hash')
    value=json.loads(path.read_text())
    if value['arrays']['sha256']!=spec['array_sha256'] or value['source_sha']!=spec['source_sha'] or not value['equation_pass']:raise ValueError('V54 parent scientific identity')
    return value


def read(role):return parent(role) if role in ('P','B','A') else stage(role)


def case_spec(role):return dict(plan_record()['cases']['R7' if role in ('D','VERIFY_COST') else role])


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V54 queue frozen')
    if not stage('D')['same_p_paths_trusted']:raise RuntimeError('original equations untrusted; isolate dependent solves')
    if role=='C':
        admission=json.loads((window.TMP/'C_admission.json').read_text())
        for item in admission['evidence']:
            if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('V54 C evidence hash')
        if not admission['admitted'] or not all(stage(r)['equation_pass'] for r in ('R7','R6')):raise RuntimeError('V54 C not admitted')
    if sum((ARTIFACT/(s+'.json')).exists() and bool(stage(s).get('returned_arrays')) for s in SOLVES)>=4:raise RuntimeError('V54 four solves consumed')


def raw_tensor_reader(role,bundle,journal):
    from .phase_raw_tensor_reader import ReadonlyRawTensorProvider
    names=('B',) if case_spec(role)['degree']==7 else ('A',)
    return ReadonlyRawTensorProvider([plan_record()['raw_tensor_parents'][n] for n in names],bundle,journal,ROOT)


def project_mode_parent(role,bundle,rhs,geometry,folder,journal):
    from .phase_p_order_dtn import project_with_residual_identity
    return project_with_residual_identity(read({'R7':'B','R6':'P','C':'R7'}[role]),bundle,rhs,geometry,folder,journal)


def cached_comparisons():
    rows=[]
    for path in sorted((ARTIFACT/'comparisons').glob('*.json')):
        r=json.loads(path.read_text());rows.append(dict(pair=path.stem.split('_'),path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            pass_gate=r['pass_gate'],fields=r['fields'],selected=r['selected'],power_differences=r['power_differences'],quadrature_operation_scaled=r['quadrature_operation_scaled']))
    return rows



def verification_basis_identity(setup, result):
    from .phase_raw_tensor_reader import live_basis_identity
    return live_basis_identity(setup['spaces'][result['degree']].element.basix_element,
        result['raw_tensor_checkpoint']['classes'])
