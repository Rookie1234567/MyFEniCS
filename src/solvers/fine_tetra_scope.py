"""Frozen V63 finite tetra authority; B alone has the larger memory profile."""
import copy
import hashlib
import json
from pathlib import Path
from .independent_tetra_scope import TetraWindow, implementation_hashes as parent_hashes

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v63'
PLAN=ROOT/'input/task042_neural_coarse_inverse/fine_tetra_accuracy_v63.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v63'
STAGES=('PREFLIGHT','A','B','M','VERIFY_COST');SOLVES=('A','B','M')


class FineWindow(TetraWindow):
    def available_at_boundary(self,role):
        reserve=3000 if role in SOLVES else 180
        used=sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,
            self.total-self.charged_wall()-reserve,self.snapshot()['heavy_remaining_seconds']-reserve)

    def launcher_overhead(self):
        from .scattering_accuracy_scope import AccuracyWindow
        return AccuracyWindow.launcher_overhead(self)


window=FineWindow(ROOT/'tmp/task042/v63',label='V63',total=28800,component=28800,auxiliary=28800,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='a3bbf90bf37810911bf1fa287cb77a30f2b50832' or p['stages']!=list(STAGES):raise ValueError('V63 authority')
    if p['assembly_row_cap']!=600000 or p['maximum_new_solves']!=3:raise ValueError('V63 capacity/count authority')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[32*2**30,240*2**30,50*2**30,512*2**20]:raise ValueError('V63 storage authority')
    for role in STAGES:
        m=memory_budget(role,p)
        if [m[k] for k in ('planning_gib','warning_gib','sampled_stop_gib')]!=([128,160,192] if role=='B' else [64,80,96]):raise ValueError('V63 role memory authority')
    return p


def memory_budget(role,p=None):
    if role not in STAGES:role='PREFLIGHT'
    if p is None:p=json.loads(PLAN.read_text())
    return dict(p['memory_profiles']['B' if role=='B' else 'default'])


def case_spec(role):return dict(plan_record()['cases'][role if role in SOLVES else 'A'])


def physical_for(role):
    p=copy.deepcopy(plan_record()['physical_descriptor']);s=case_spec(role)
    for axis,factor in zip(('x','y','z'),(s['h_ratio'],s['h_ratio'],2*s['h_ratio']),strict=True):
        a=p['geometry']['axes_nm'][axis]
        p['geometry']['axes_nm'][axis]=[l+(r-l)*j/factor for l,r in zip(a[:-1],a[1:]) for j in range(factor)]+[a[-1]]
    source=p['geometry'].pop('notch_expected_changed_cells')
    p['geometry'].update(case=s['case'],cells=s['cells'],mesh='periodic-compatible six-tet Freudenthal boxes',grid='Z2_H2',
        source80_macro_notch_cells=source,actual_mesh_expected_notch_tetrahedra=192)
    p['discretization'].update(degree=s['degree'],family='N1curl',cell_type='tetrahedron',FE=s['independent'],rows=s['rows'],
        representation='gVh complete uncondensed',static_condensation=False,production_body_q=2*s['degree']+3,oracle_body_q=2*s['degree']+5)
    m,n={828:(11,4),1188:(13,5)}[s['complete_modes']]
    p['boundary'].update(manual_m=[-m,m],manual_n=[-n,n],complete_modes=s['complete_modes'])
    return p


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());path=Path(row['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V63 stage identity')
    return json.loads(path.read_text())


def require_stage(role):
    if role not in SOLVES:raise ValueError('V63 fixed inventory')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V63 queue frozen')
    count=sum(json.loads(line)['event']=='h_bounded_numeric_factor_begin' for path in ARTIFACT.glob('*/events.jsonl') for line in path.read_text().splitlines())
    if count>=3:raise RuntimeError('V63 maximum three numeric attempts')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V63 support/identity preflight gate')
    if role=='M':
        gate=json.loads((ARTIFACT/'A_B_gate.json').read_text())
        if not gate['pass_gate'] or gate['parent_array_sha256']!=[stage(r)['arrays']['sha256'] for r in ('A','B')]:raise RuntimeError('V63 M requires complete A/B increment')
    if (ARTIFACT/(role+'.json')).exists() and stage(role).get('arrays'):raise RuntimeError('returned field: saved consumer only')
    if window.available_at_boundary(role)<plan_record()['forecast_case_seconds'][role]:raise RuntimeError('V63 complete N1 plus 3000s reserve does not fit')


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    r=parent_hashes()
    paths=['src/solvers/fine_tetra_scope.py','src/solvers/fine_tetra_study.py','src/solvers/tetra_boundary_support.py',
        'src/solvers/tetra_polynomial_difference.py','benchmarks/qualify_fine_tetra.py','benchmarks/collect_fine_tetra.py',
        'src/test/test_fine_tetra.py',str(PLAN.relative_to(ROOT))]
    r.update({n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in paths})
    return r
