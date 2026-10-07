"""V59 fixed-trace finite authority, independent of all closed scopes."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
NAMESPACE='v59'
PLAN=ROOT/'input/task042_neural_coarse_inverse/trace_interior_enrichment_v59.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v59'
STAGES=('PREFLIGHT','M67','M68','VERIFY_COST')
SOLVES=('M67','M68')


class EnrichmentWindow(AccuracyWindow):
    def available_at_boundary(self,role):
        reserve=1800 if role in SOLVES else 180
        used=sum(json.loads((Path(r['folder'])/'run_summary.json').read_text()).get('launch_wall_seconds',r['elapsed_seconds'])
            if (Path(r['folder'])/'run_summary.json').exists() else r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,self.total-self.charged_wall()-reserve,
            self.snapshot()['heavy_remaining_seconds']-reserve)

    def remaining(self,role):
        self.require_ready();return self.available_at_boundary(role)


window=EnrichmentWindow(ROOT/'tmp/task042/v59',label='V59',total=21600,component=21600,auxiliary=21600,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='e75eb2c6b4d3319e9ccb109ef5fa9debc1f60287' or p['stages']!=list(STAGES):raise ValueError('V59 authority')
    if p['memory_budget']!=dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96,neighbor_growth_gib=384,extra_cache_workspace_gib=2):raise ValueError('V59 memory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[12*2**30,102*2**30,50*2**30,512*2**20]:raise ValueError('V59 storage')
    return p


def implementation_hashes():
    from .phase_deployment_scope import implementation_hashes as previous
    names=list(previous())+[str(PLAN.relative_to(ROOT)), 'src/solvers/trace_interior_scope.py','src/solvers/trace_interior_restriction.py',
        'src/solvers/trace_interior_study.py','src/test/test_trace_interior.py','benchmarks/qualify_trace_interior.py','benchmarks/collect_trace_interior.py',
        'src/constraints/floquet_3d.py','src/constraints/high_order_floquet_trace.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V59 stage identity')
    return json.loads(p.read_text())


def parent(role):
    from .phase_deployment_scope import parent as previous
    if role not in ('R6','R7'):raise ValueError('only original kappa parents')
    return previous(role)


def read(role):return parent(role) if role in ('R6','R7') else stage(role)
def case_spec(role):return dict(plan_record()['cases'][role if role in SOLVES else 'M67'])
def physical_output_options():return dict(volume_backend='direct_phase_quadrature')


def require_stage(role):
    if role not in SOLVES:raise ValueError('only two fixed interior degrees')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V59 frozen')
    pre=stage('PREFLIGHT')
    if not pre['degrees'][str(case_spec(role)['degree'])]['pass_gate']:raise RuntimeError('own ambient degree qualification fails')
    if (ARTIFACT/(role+'.json')).exists() and stage(role).get('returned_arrays') and not (window.TMP/(role+'_post_resume.json')).exists():raise RuntimeError('returned state consume only')
    if window.available_at_boundary(role)<plan_record()['forecast_case_seconds'][role]:raise RuntimeError('case plus full audit reserve does not fit')


def boundary_provider(cfg,setup,folder,journal):
    from .phase_boundary_checkpoint import StudyBoundaryProvider
    return StudyBoundaryProvider(cfg,setup,folder,journal)


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json'
    return p if role=='VERIFY_COST' and p.exists() else None
