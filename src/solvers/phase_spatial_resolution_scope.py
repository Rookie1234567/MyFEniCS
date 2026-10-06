"""V55 finite spatial-resolution authority, with separate prior/new audits."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
NAMESPACE='v55'
PLAN=ROOT/'input/task042_neural_coarse_inverse/spatial_resolution_v55.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v55'
STAGES=('Q0','SETUP','H7','T6','AUDIT_H7','AUDIT_T6','VERIFY_COST')
SOLVES=('H7','T6')


class ResolutionWindow(AccuracyWindow):
    def remaining(self,role):
        self.require_ready();p=plan_record();reserve=3000 if role in SOLVES else 180
        if role in SOLVES and (self.TMP/(role+'_post_resume.json')).exists():
            postprocessing_record(role)
            # The solve allocation has ended; consume its saved return within
            # the same cumulative case cap, leaving a separate original audit.
            reserve=900
        used=sum(json.loads((Path(r['folder'])/'run_summary.json').read_text())['launch_wall_seconds']
            if (Path(r['folder'])/'run_summary.json').exists() else r['elapsed_seconds']
            for r in self.ledger()['runs'] if r['role']==role)
        return min(p['case_wall_seconds'].get(role,900)-used,self.total-self.charged_wall()-reserve,
            self.snapshot()['heavy_remaining_seconds']-reserve)


def postprocessing_record(role):
    r=json.loads((window.TMP/(role+'_post_resume.json')).read_text())
    receipt=r['minimal_state_receipt'];path=Path(receipt['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:
        raise ValueError('V55 saved return identity')
    original=json.loads(path.read_text())
    if r['arrays']!=original['arrays'] or r['case_spec']!=case_spec(role) or r['source']!=original['source']:
        raise ValueError('V55 saved return scientific identity')
    raw=r['raw_tensor_manifest_receipt'];manifest=Path(raw['path']).resolve()
    if manifest!=path.parent/'raw_tensor/manifest.json' or hashlib.sha256(manifest.read_bytes()).hexdigest()!=raw['sha256']:
        raise ValueError('V55 saved raw manifest identity')
    return r


window=ResolutionWindow(ROOT/'tmp/task042/v55',label='V55',total=18000,
    component=18000,auxiliary=18000,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='e3b46656fd13b31a465a628f7fdeb863e32f38ed' or p['stages']!=list(STAGES):raise ValueError('V55 authority/stage inventory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[16*2**30,84*2**30,50*2**30,512*2**20]:raise ValueError('V55 storage contract')
    if p['memory_budget']!=dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96,neighbor_growth_gib=384,extra_cache_workspace_gib=2) or p['assembly_row_cap']!=100000:raise ValueError('V55 live capacity contract')
    return p


def implementation_hashes():
    from .phase_p_order_dtn_scope import implementation_hashes as previous
    names=list(previous())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/phase_spatial_resolution_scope.py','src/solvers/phase_spatial_resolution.py',
        'src/solvers/phase_tangential_audit.py','src/test/test_phase_spatial_resolution.py',
        'benchmarks/qualify_phase_spatial_resolution.py','benchmarks/collect_phase_spatial_resolution.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());path=Path(row['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V55 immutable stage identity')
    return json.loads(path.read_text())


def parent(role):
    spec=plan_record()['parents'][role];pointer=ROOT/spec['pointer']
    if hashlib.sha256(pointer.read_bytes()).hexdigest()!=spec['pointer_sha256']:raise ValueError('V55 parent pointer changed')
    item=json.loads(pointer.read_text());path=Path(item['path']).resolve()
    if not path.is_relative_to(ROOT/'benchmarks/artifacts/task042/v54') or hashlib.sha256(path.read_bytes()).hexdigest()!=spec['result_sha256'] or item['sha256']!=spec['result_sha256']:raise ValueError('V55 prior result identity')
    r=json.loads(path.read_text())
    if r['arrays']['sha256']!=spec['array_sha256'] or r['source_sha']!=spec['source_sha'] or not r['equation_pass']:raise ValueError('V55 prior scientific identity')
    return r


def read(role):return parent(role) if role in ('R6','R7','C') else stage(role)


def case_spec(role):
    if role=='Q0':return dict(parent('R7')['case_spec'])
    role='T6' if role=='AUDIT_T6' else 'H7' if role in ('SETUP','AUDIT_H7','VERIFY_COST') else role
    s=dict(plan_record()['cases'][role])
    if role=='T6':
        pick=window.TMP/'transverse_selection.json'
        if pick.exists():s['splits']=json.loads(pick.read_text())['splits']
    return s


def verification_inventory_for(role):
    name='prior_audit_inventory.json' if role=='Q0' else role+'_inventory.json' if role.startswith('AUDIT_') else 'scientific_queue_frozen.json' if role=='VERIFY_COST' else None
    return window.TMP/name if name and (window.TMP/name).exists() else None


def require_stage(role):
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V55 solve queue frozen')
    q=stage('Q0')
    if not q['pass_gate'] or not q['saved_checker_pass']:raise RuntimeError('V55 independent parent qualification incomplete')
    if not stage('SETUP')['pass_gate']:raise RuntimeError('V55 capacity/case preflight incomplete')
    if role=='T6':
        a=json.loads((window.TMP/'T6_admission.json').read_text())
        if not a['admitted'] or a['axis']!=json.loads((window.TMP/'transverse_selection.json').read_text())['selected_axis']:raise RuntimeError('V55 T6 not admitted')
        for r in a['evidence']:
            if hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('V55 T6 evidence changed')
    if sum((ARTIFACT/(r+'.json')).exists() and bool(stage(r).get('returned_arrays')) for r in SOLVES)>=3:raise RuntimeError('V55 new complete solve limit')


def raw_tensor_reader(role,bundle,journal):
    from .phase_raw_tensor_reader import ReadonlyRawTensorProvider
    keys=('p7',) if case_spec(role)['degree']==7 else ('p6_Z2','p6_Z4')
    return ReadonlyRawTensorProvider([plan_record()['raw_tensor_parents'][k] for k in keys],bundle,journal,ROOT)


def verification_basis_identity(setup,r):
    from .phase_raw_tensor_reader import live_basis_identity
    return live_basis_identity(setup['spaces'][r['degree']].element.basix_element,r['raw_tensor_checkpoint']['classes'])


def cached_comparisons():
    rows=[]
    for path in sorted((ARTIFACT/'comparisons').glob('*.json')):
        r=json.loads(path.read_text());rows.append(dict(pair=path.stem.split('_'),path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pass_gate=r['pass_gate'],fields=r['fields'],selected=r['selected'],power_differences=r['power_differences']))
    return rows
