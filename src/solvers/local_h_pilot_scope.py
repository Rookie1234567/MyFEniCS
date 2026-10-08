"""V64 full tetra p6 and one frozen local-h mesh; no old window reopening."""
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from .independent_tetra_scope import TetraWindow
from .fine_tetra_scope import implementation_hashes as parent_hashes

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v64'
PLAN=ROOT/'input/task042_neural_coarse_inverse/p6_reference_local_h_v64.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v64'
STAGES=('PREFLIGHT','P6','L4','VERIFY_COST');SOLVES=('P6','L4')


class PilotWindow(TetraWindow):
    def available_at_boundary(self,role):
        reserve=6600 if role in SOLVES else 180
        used=0.
        for r in self.ledger()['runs']:
            if r['role']!=role:continue
            p=Path(r['folder'])/'run_summary.json'
            used+=json.loads(p.read_text())['launch_wall_seconds'] if p.exists() else r['elapsed_seconds']
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,
            self.total-self.charged_wall()-reserve,self.snapshot()['heavy_remaining_seconds']-reserve)

    def launcher_overhead(self):
        from .scattering_accuracy_scope import AccuracyWindow
        seconds=AccuracyWindow.launcher_overhead(self)
        return seconds+one_run_overhead(self.TMP,self.ledger()['runs'])


def one_run_overhead(folder,runs,*,roles=None):
    """Include rejected entry calls; match retries by their actual UTC interval."""
    seconds=0.
    for path in folder.glob('*_one_run*/receipt.json'):
        receipt=json.loads(path.read_text());begin=datetime.fromisoformat(receipt['start_utc']);end=datetime.fromisoformat(receipt['end_utc'])
        role=path.parent.name.split('_one_run')[0]
        if roles is not None and role not in roles:continue
        matched=[r for r in runs if r['role']==role and r['source_sha']==receipt['source_sha']
            and begin<=datetime.fromisoformat(r['before_clock']['observed_utc'])<=end]
        if len(matched)>1:raise ValueError('one-run receipt contains multiple stage entries')
        if matched:
            summary=Path(matched[0]['folder'])/'run_summary.json'
            covered=json.loads(summary.read_text())['launch_wall_seconds'] if summary.exists() else matched[0]['elapsed_seconds']
        else:
            # The entry failed before begin(); its already-paid probe must not
            # be charged twice, while storage/identity/startup work remains paid.
            covered=0.
            for probe in folder.glob('probe_*.json'):
                p=json.loads(probe.read_text());observation=Path(p['receipt_path'])
                if observation.exists():
                    observed=json.loads(observation.read_text())
                    if begin<=datetime.fromisoformat(observed['utc'])<=end:covered+=p['elapsed_seconds']
        seconds+=max(0.,receipt['elapsed_seconds']-covered)
    return seconds


window=PilotWindow(ROOT/'tmp/task042/v64',label='V64',total=36000,component=36000,auxiliary=36000,probe=120,reserve=180,bootstrap=0)


def memory_budget(role,p=None):
    p=json.loads(PLAN.read_text()) if p is None else p
    return dict(p['memory_profiles'][role if role in SOLVES else 'default'])


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='b2cf084ee0269b87acfacef314475a70702f4266' or p['stages']!=list(STAGES):raise ValueError('V64 authority')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[40*2**30,280*2**30,50*2**30,512*2**20]:raise ValueError('V64 storage authority')
    for role,wanted in [('P6',[192,224,256]),('L4',[128,160,192]),('PREFLIGHT',[64,80,96])]:
        if [memory_budget(role,p)[k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=wanted:raise ValueError('V64 role memory authority')
    return p


def checked_record(path):
    row=json.loads(Path(path).read_text());p=Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V64 frozen pointer identity')
    return json.loads(p.read_text())


def case_spec(role):
    role=role if role in SOLVES else 'P6';s=copy.deepcopy(plan_record()['cases'][role])
    pointer=ARTIFACT/'local_mesh_spec.json'
    if role=='L4' and pointer.exists():s.update(checked_record(pointer))
    return s


def physical_for(role):
    from .fine_tetra_scope import physical_for as parent_physical
    p=copy.deepcopy(parent_physical('A'));s=case_spec(role)
    p['geometry'].update(cells=s['cells'],grid='V64_FROZEN_LOCAL_H' if s.get('mesh_override') else 'Z2_H2',mesh='actual saved compatible tetra' if s.get('mesh_override') else p['geometry']['mesh'])
    if s.get('mesh_override'):
        p['geometry'].update(mesh_override=s['mesh_override'],actual_mesh_expected_notch_tetrahedra=s['notch_tetrahedra'])
    p['discretization'].update(degree=s['degree'],FE=s['independent'],rows=s['rows'],production_body_q=2*s['degree']+3,oracle_body_q=2*s['degree']+5)
    return p


def stage(role):return checked_record(ARTIFACT/(role+'.json'))


def require_stage(role):
    if role not in SOLVES:raise ValueError('V64 fixed solve inventory')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V64 queue frozen')
    n=sum(json.loads(l).get('event')=='h_bounded_numeric_factor_begin' for p in ARTIFACT.glob('*/events.jsonl') for l in p.read_text().splitlines())
    if n>=3:raise RuntimeError('V64 maximum three numeric attempts')
    s=stage('PREFLIGHT')
    if not s['pass_gate']:raise RuntimeError('V64 preflight identity gate')
    if role=='L4' and not s['local_mesh']['admitted']:raise RuntimeError('V64 local mesh not qualified/capacity not admitted')
    if (ARTIFACT/(role+'.json')).exists() and stage(role).get('arrays'):raise RuntimeError('returned field: saved consumer only')
    if window.available_at_boundary(role)<plan_record()['forecast_case_seconds'][role]:raise RuntimeError('V64 complete case plus output/compare reserve does not fit')


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    r=parent_hashes()
    paths=['src/solvers/local_h_pilot_scope.py','src/solvers/local_h_pilot.py','src/solvers/tetra_local_marking.py',
        'src/solvers/tetra_mesh_override.py','src/adaptivity/periodic_tetra_refinement.py','src/geometry/tetra_mesh_audit.py',
        'benchmarks/qualify_local_h_pilot.py','benchmarks/collect_local_h_pilot.py','benchmarks/check_tetra_preparation.py','src/test/test_local_h_pilot.py',str(PLAN.relative_to(ROOT))]
    r.update({n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in paths});return r
