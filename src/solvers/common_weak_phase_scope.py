"""V57 fixed-window namespace; all parent windows stay closed/read-only."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
NAMESPACE='v57'
PLAN=ROOT/'input/task042_neural_coarse_inverse/common_weak_phase_v57.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v57'
STAGES=('D','K','B6','Y6','VERIFY_COST')
SOLVES=('B6','Y6')


class PhaseWindow(AccuracyWindow):
    def remaining(self,role):
        self.require_ready()
        return self.available_at_boundary(role)

    def available_at_boundary(self,role):
        reserve=1800 if role in SOLVES else 180
        used=sum(json.loads((Path(r['folder'])/'run_summary.json').read_text()).get('launch_wall_seconds',r['elapsed_seconds'])
            if (Path(r['folder'])/'run_summary.json').exists() else r['elapsed_seconds']
            for r in self.ledger()['runs'] if r['role']==role)
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,
            self.total-self.charged_wall()-reserve,self.snapshot()['heavy_remaining_seconds']-reserve)


window=PhaseWindow(ROOT/'tmp/task042/v57',label='V57',total=18000,
    component=18000,auxiliary=18000,probe=120,reserve=180,bootstrap=0.)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='e08e598146f8bcd5a25d7bcf0364cf8c94c9f091' or p['stages']!=list(STAGES):raise ValueError('V57 authority inventory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[10*2**30,102*2**30,50*2**30,512*2**20]:raise ValueError('V57 storage contract')
    if p['memory_budget']!=dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96,neighbor_growth_gib=384,extra_cache_workspace_gib=2):raise ValueError('V57 live memory contract')
    return p


def implementation_hashes():
    from .phase_saved_closure_scope import implementation_hashes as previous
    names=list(previous())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/common_weak_phase_scope.py','src/solvers/common_weak_phase.py',
        'src/solvers/common_continuous_weak.py','src/solvers/hcurl_affine_phase_tensor.py',
        'src/solvers/phase_reference_provider.py','src/test/test_common_weak_phase.py',
        'benchmarks/qualify_common_weak_phase.py','benchmarks/collect_common_weak_phase.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());path=Path(row['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V57 pointer identity')
    return json.loads(path.read_text())


def parent(role):
    if role in ('R6','R7'):
        from .phase_spatial_resolution_scope import parent as old
        return old(role)
    key='S' if role=='H7' else 'T6' if role=='T6' else None
    if key is None:raise ValueError('four frozen parent states only')
    p=plan_record()['frozen_saved_stages'][key];path=ROOT/p['pointer']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=p['sha256']:raise ValueError('V56 pointer changed')
    ptr=json.loads(path.read_text());raw=Path(ptr['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=p['result_sha256']:raise ValueError('V56 final result changed')
    r=json.loads(raw)
    return r['H7'] if key=='S' else r


def case_spec(role):return dict(plan_record()['cases'][role if role in SOLVES else 'B6'])
def physical_output_options():return dict(volume_backend='direct_phase_quadrature')
def read(role):return parent(role) if role in ('R6','R7','T6','H7') else stage(role)


def require_stage(role):
    if role not in SOLVES:raise ValueError('only two new solves')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V57 queue frozen')
    k=stage('K')
    if role=='B6' and not k.get('p6_pass'):raise RuntimeError('p6 provider not qualified')
    completed=[s for s in SOLVES if (ARTIFACT/(s+'.json')).exists() and stage(s).get('returned_arrays')]
    if len(completed)>=2 and not (window.TMP/(role+'_post_resume.json')).exists():raise RuntimeError('two new solves exhausted')
    if role in completed and not (window.TMP/(role+'_post_resume.json')).exists():raise RuntimeError('saved return exists; consume only')
    needed=plan_record().get('forecast_case_seconds',{}).get(role,2500 if role=='B6' else 4000)
    if window.available_at_boundary(role)<needed:raise RuntimeError('complete case with 1800s audit reserve does not fit')


def raw_tensor_reader(role,bundle,journal):
    if role=='B6' or (role=='Y6' and (ARTIFACT/'B6.json').exists() and stage('B6').get('backend_reproduction_pass')):
        from .phase_reference_provider import PhaseReferenceProvider
        return PhaseReferenceProvider(bundle,journal)
    from .phase_raw_tensor_reader import ReadonlyRawTensorProvider
    return ReadonlyRawTensorProvider([plan_record()['raw_tensor_parents']['p6_Z2'],plan_record()['raw_tensor_parents']['p6_Z4']],bundle,journal,ROOT)


def postprocessing_record(role):
    r=json.loads((window.TMP/(role+'_post_resume.json')).read_text());receipt=r['minimal_state_receipt'];path=Path(receipt['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('V57 saved return receipt')
    original=json.loads(path.read_text())
    if r['arrays']!=original['arrays'] or r['case_spec']!=case_spec(role) or r['source']!=original['source']:raise ValueError('V57 saved return identity')
    return r


def verification_inventory_for(role):
    path=window.TMP/'scientific_queue_frozen.json'
    return path if role=='VERIFY_COST' and path.exists() else None
