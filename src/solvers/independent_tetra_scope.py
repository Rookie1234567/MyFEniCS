"""V62 independent full tetra scope; immutable clock and separate closed ledger."""
import hashlib
import json
from pathlib import Path
from .face_trace_scope import FaceWindow

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v62'
PLAN=ROOT/'input/task042_neural_coarse_inverse/independent_tetra_reference_v62.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v62'
STAGES=('PREFLIGHT','F4','F5','T4','T5','TH3','VERIFY_COST');SOLVES=('F4','F5','T4','T5','TH3')


class TetraWindow(FaceWindow):
    def launcher_overhead(self):
        from .scattering_accuracy_scope import AccuracyWindow
        seconds=AccuracyWindow.launcher_overhead(self)
        for r in self.ledger()['runs']:
            if r['role'] not in STAGES:continue
            receipts=[p for p in self.TMP.glob(r['role']+'_one_run*/receipt.json') if json.loads(p.read_text())['source_sha']==r['source_sha']]
            summary=Path(r['folder'])/'run_summary.json'
            if len(receipts)==1 and summary.exists():seconds+=max(0.,json.loads(receipts[0].read_text())['elapsed_seconds']-json.loads(summary.read_text())['launch_wall_seconds'])
        return seconds

    def available_at_boundary(self,role):
        reserve=1800 if role in SOLVES else 180
        used=sum(r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,
            self.total-self.charged_wall()-reserve,self.snapshot()['heavy_remaining_seconds']-reserve)


window=TetraWindow(ROOT/'tmp/task042/v62',label='V62',total=28800,component=28800,auxiliary=28800,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='b39df0051e6a0501528de54bf02987021188702e' or p['stages']!=list(STAGES):raise ValueError('V62 authority')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[20*2**30,200*2**30,50*2**30,512*2**20]:raise ValueError('V62 live storage identity')
    if p['memory_budget']!=dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96,neighbor_growth_gib=384,extra_cache_workspace_gib=2):raise ValueError('V62 memory identity')
    return p


def physical_for(role):
    import copy
    p=copy.deepcopy(plan_record()['physical_descriptor']);s=case_spec(role)
    for axis,factor in zip(('x','y','z'),(s['h_ratio'],s['h_ratio'],2*s['h_ratio']),strict=True):
        a=p['geometry']['axes_nm'][axis]
        p['geometry']['axes_nm'][axis]=[l+(r-l)*j/factor for l,r in zip(a[:-1],a[1:]) for j in range(factor)]+[a[-1]]
    source_count=p['geometry'].pop('notch_expected_changed_cells')
    p['geometry'].update(case=s['case'],cells=s['cells'],mesh='periodic-compatible six-tet Freudenthal boxes',grid='Z2_H'+str(s['h_ratio']),
        source80_macro_notch_cells=source_count,actual_mesh_expected_notch_tetrahedra=0 if s['case']=='FLAT' else 24*s['h_ratio']**3)
    p['discretization'].update(degree=s['degree'],family='N1curl',cell_type='tetrahedron',FE=s['independent'],rows=s['rows'],
        representation='gVh complete uncondensed',static_condensation=False,production_body_q=2*s['degree']+3,oracle_body_q=2*s['degree']+5)
    return p


def case_spec(role):return dict(plan_record()['cases'][role if role in SOLVES else 'T4'])


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V62 stage identity')
    return json.loads(p.read_text())


def require_stage(role):
    if role not in SOLVES:raise ValueError('V62 finite inventory')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V62 queue frozen')
    count=0
    for path in ARTIFACT.glob('*/events.jsonl'):
        count+=sum(json.loads(line)['event']=='h_bounded_numeric_factor_begin' for line in path.read_text().splitlines())
    if count>=5:raise RuntimeError('V62 maximum five numeric/complete attempts')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('tetra preflight not qualified')
    if role=='F5' and stage('F4').get('accuracy_pass'):raise RuntimeError('F5 not admitted: F4 accurate')
    if role in ('T4','T5','TH3') and not any((ARTIFACT/(f+'.json')).exists() and stage(f).get('accuracy_pass') and stage(f).get('equation_pass') for f in ('F4','F5')):
        raise RuntimeError('new tetra FLAT accuracy gate not passed')
    if role=='TH3' and not all(stage(r).get('equation_pass') for r in ('T4','T5')):raise RuntimeError('TH3 main fields not algebraically legal')
    if (ARTIFACT/(role+'.json')).exists() and stage(role).get('arrays'):raise RuntimeError('returned field: saved consumer only')
    if window.available_at_boundary(role)<plan_record()['forecast_case_seconds'][role]:raise RuntimeError('complete output and audit reserve do not fit')


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def implementation_hashes():
    names=['scripts/run_case.py','scripts/activate_task042.sh','src/runners/port_preparation.py','src/runners/task042_shared.py',
        'src/solvers/independent_tetra_reference.py','src/solvers/independent_tetra_fields.py','src/solvers/independent_tetra_scope.py',
        'src/solvers/independent_tetra_study.py','src/io/independent_tetra_reference.py','src/test/test_independent_tetra_reference.py',
        'benchmarks/qualify_independent_tetra.py','benchmarks/collect_independent_tetra.py','benchmarks/check_independent_tetra.py',
        'src/test/test_independent_tetra_saved_checks.py',str(PLAN.relative_to(ROOT)),
        'src/geometry/mesh_builder_3d.py','src/constraints/floquet_3d.py','src/constraints/floquet_3d_high_order.py',
        'src/constraints/high_order_floquet_trace.py','src/solvers/target_boundary_witness.py','src/solvers/fixed_phase_fem.py',
        'src/solvers/scattering_anchor.py','src/solvers/scattering_accuracy_fields.py','src/solvers/scattering_accuracy_boundary.py',
        'src/solvers/phase_evaluation_cache.py','src/solvers/phase_notch_hp_modes.py',
        'src/solvers/fullspace_dtn_action.py','src/solvers/dtn_port_3d.py','src/solvers/phase_explicit_accuracy.py',
        'src/solvers/phase_explicit_accuracy_capacity.py','src/solvers/fullspace_v17_p3_oracle.py','src/common/analytic_fields_3d.py',
        'src/common/config_3d.py','src/common/modes_3d.py','src/common/optical_material_table.py','input/materials/si_optical_constants_v1.json',
        'benchmarks/subreaper_watchdog.py','src/solvers/scattering_accuracy_scope.py','src/solvers/face_trace_scope.py',
        'src/solvers/phase_notch_hp.py','src/solvers/phase_notch_hp_fields.py','src/solvers/phase_explicit_accuracy_fields.py',
        'src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py','src/adaptivity/target_uniform_tetra_control.py',
        'benchmarks/collect_phase_explicit_accuracy.py','benchmarks/collect_phase_notch_hp.py',
        'benchmarks/collect_phase_deployment.py','benchmarks/collect_common_weak_phase.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
