"""V56 saved consumers and one conditional transverse solve; old scopes read-only."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
NAMESPACE='v56'
PLAN=ROOT/'input/task042_neural_coarse_inverse/saved_field_closure_v56.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v56'
STAGES=('S','T6','VERIFY_COST')
SOLVES=('T6',)


class ClosureWindow(AccuracyWindow):
    def remaining(self,role):
        self.require_ready()
        return self.available_at_boundary(role)

    def available_at_boundary(self,role):
        # Read-only inside the already claimed worker; require_ready correctly
        # refuses a second launch while active, so must not be called here.
        p=plan_record();reserve=1800 if role=='T6' else 180
        used=sum(json.loads((Path(r['folder'])/'run_summary.json').read_text()).get('launch_wall_seconds',r['elapsed_seconds'])
            if (Path(r['folder'])/'run_summary.json').exists() else r['elapsed_seconds']
            for r in self.ledger()['runs'] if r['role']==role)
        return min(p['case_wall_seconds'].get(role,900)-used,self.total-self.charged_wall()-reserve,
            self.snapshot()['heavy_remaining_seconds']-reserve)


window=ClosureWindow(ROOT/'tmp/task042/v56',label='V56',total=18000,
    component=18000,auxiliary=18000,probe=120,reserve=180,bootstrap=1.880938676)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='18e597ba6f3193f1c54a292a258d9af8891c9c84' or p['stages']!=list(STAGES):raise ValueError('V56 authority/stage inventory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[8*2**30,92*2**30,50*2**30,512*2**20]:raise ValueError('V56 storage contract')
    if p['memory_budget']!=dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96,neighbor_growth_gib=384,extra_cache_workspace_gib=2) or p['assembly_row_cap']!=100000:raise ValueError('V56 capacity contract')
    return p


def implementation_hashes():
    from .phase_spatial_resolution_scope import implementation_hashes as previous
    names=list(previous())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/phase_saved_closure_scope.py','src/solvers/phase_saved_closure.py',
        'src/solvers/phase_saved_uncondensed.py','src/solvers/phase_target_bridge.py',
        'src/postprocessing/phase_volume_quadrature.py','src/test/test_phase_saved_closure.py',
        'benchmarks/qualify_phase_saved_closure.py','benchmarks/collect_phase_saved_closure.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());path=Path(row['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V56 stage identity')
    return json.loads(path.read_text())


def parent(role):
    if role in ('R6','R7'):
        from .phase_spatial_resolution_scope import parent as previous
        return previous(role)
    if role!='H7':raise ValueError('V56 parent inventory')
    p=plan_record()['saved_H7'];path=ROOT/p['minimal_path']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=p['minimal_sha256']:raise ValueError('H7 producer receipt changed')
    r=json.loads(path.read_text())
    if r['source']['source_sha']!=p['solve_source_sha'] or r['arrays']['sha256']!=p['npz_sha256'] or r['arrays']['members']['u_storage']['sha256']!=p['u_sha256']:raise ValueError('H7 saved scientific identity')
    if r['case_spec']!=plan_record()['cases']['H7']:raise ValueError('H7 physical/discrete case identity')
    r.update(source_sha=p['solve_source_sha'],equation_pass=all(r['original_audit'][k]<=1e-6 for k in ('true','native','augmented','port')),
        original_status=r['status'],minimal_state_receipt=dict(path=str(path),sha256=p['minimal_sha256']),mode_sha256=r['mode_sha256'])
    return r


def read(role):return parent(role) if role in ('R6','R7','H7') else stage(role)


def case_spec(role):return dict(plan_record()['cases']['T6' if role=='T6' else 'H7'])


def physical_output_options():return dict(volume_backend='direct_phase_quadrature')


def raw_tensor_reader(role,bundle,journal):
    if role!='T6':raise RuntimeError('saved H7 consumer must never request tensors')
    from .phase_raw_tensor_reader import ReadonlyRawTensorProvider
    return ReadonlyRawTensorProvider([plan_record()['raw_tensor_parents'][k] for k in ('p6_Z2','p6_Z4')],bundle,journal,ROOT)


def require_stage(role):
    if role!='T6':raise RuntimeError('only one conditional new solve')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V56 queue frozen')
    saved=stage('S')
    if not saved['complete_saved_closure']:raise RuntimeError('H7 saved closure incomplete')
    if all(p['pass_gate'] for p in saved['comparisons'].values()):raise RuntimeError('no spatial or cross-p failure to admit T6')
    a=json.loads((window.TMP/'T6_admission.json').read_text())
    if not a['admitted'] or a['splits']!=[2,1,2]:raise RuntimeError('fixed x transverse admission')
    for item in a['evidence']:
        if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('T6 admission identity')
    need=1800 if (window.TMP/'T6_post_resume.json').exists() else a['forecast_complete_case_seconds']
    if window.available_at_boundary('T6')<need:raise RuntimeError('T6 complete case and audit budget no longer fits')
    if (ARTIFACT/'T6.json').exists() and stage('T6').get('returned_arrays') and not (window.TMP/'T6_post_resume.json').exists():raise RuntimeError('one complete new solve already returned; consume saved state')


def postprocessing_record(role):
    if role!='T6':raise ValueError('only the one new T6 return may be consumed')
    r=json.loads((window.TMP/'T6_post_resume.json').read_text());receipt=r['minimal_state_receipt'];path=Path(receipt['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('V56 saved return identity')
    original=json.loads(path.read_text())
    if r['arrays']!=original['arrays'] or r['case_spec']!=case_spec(role) or r['source']!=original['source']:raise ValueError('V56 saved return scientific identity')
    raw=r['raw_tensor_manifest_receipt'];manifest=Path(raw['path']).resolve()
    if manifest!=path.parent/'raw_tensor/manifest.json' or hashlib.sha256(manifest.read_bytes()).hexdigest()!=raw['sha256']:raise ValueError('V56 saved raw manifest identity')
    return r


def verification_inventory_for(role):
    path=window.TMP/'scientific_queue_frozen.json'
    return path if role=='VERIFY_COST' and path.exists() else None
