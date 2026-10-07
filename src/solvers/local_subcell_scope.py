"""V60 local assembly authority, with its own nonrefreshable ten-hour clock."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
NAMESPACE='v60'
PLAN=ROOT/'input/task042_neural_coarse_inverse/local_assembly_subcell_v60.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v60'
STAGES=('PREFLIGHT','C67','LOCAL_RESPONSE','H2','VERIFY_COST')
SOLVES=('C67','H2')


class LocalWindow(AccuracyWindow):
    def available_at_boundary(self,role):
        # The supervised worker is already registered active. Read its fixed
        # allowance without reapplying the launch-only active-null guard.
        reserve=1800 if role in SOLVES else 180
        used=0.
        for r in self.ledger()['runs']:
            if r['role']!=role:continue
            p=Path(r['folder'])/'run_summary.json'
            used+=json.loads(p.read_text())['launch_wall_seconds'] if p.exists() else r['elapsed_seconds']
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,
            self.total-self.charged_wall()-reserve,self.snapshot()['heavy_remaining_seconds']-reserve)

    def launcher_overhead(self):
        seconds=super().launcher_overhead()
        for r in self.ledger()['runs']:
            if r['role'] not in STAGES:continue
            receipts=[p for p in self.TMP.glob(r['role']+'_one_run*/receipt.json')
                if json.loads(p.read_text())['source_sha']==r['source_sha']]
            summary=Path(r['folder'])/'run_summary.json'
            if len(receipts)!=1 or not summary.exists():continue
            receipt=json.loads(receipts[0].read_text())
            seconds+=max(0.,receipt['elapsed_seconds']-json.loads(summary.read_text())['launch_wall_seconds'])
        return seconds

    def remaining(self,role):
        self.require_ready()
        return self.available_at_boundary(role)


window=LocalWindow(ROOT/'tmp/task042/v60',label='V60',total=28800,component=28800,auxiliary=28800,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='7514fbedf6253807966f0aad7b1b864e908efd8e' or p['stages']!=list(STAGES):raise ValueError('V60 authority')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[16*2**30,140*2**30,50*2**30,512*2**20]:raise ValueError('V60 storage binding')
    if p['memory_budget']!=dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96,neighbor_growth_gib=384,extra_cache_workspace_gib=2):raise ValueError('V60 live memory identity')
    return p


def implementation_hashes():
    from .trace_interior_scope import implementation_hashes as prior
    names=list(prior())+[str(PLAN.relative_to(ROOT)),'src/solvers/local_subcell_scope.py','src/solvers/local_trace_assembly.py',
        'src/solvers/local_subcell_study.py','src/solvers/subcell_macro_response.py','src/test/test_local_subcell.py',
        'benchmarks/qualify_local_subcell.py','benchmarks/collect_local_subcell.py','benchmarks/consume_saved_subcell.py','src/test/test_saved_subcell_consumer.py','benchmarks/compact_local_subcell_raw.py','src/test/test_local_subcell_archive.py','src/solvers/local_schur_bank.py','src/solvers/subcell_preparation_checkpoint.py','src/solvers/subcell_response_kernel.py','src/solvers/subcell_macro_deployment.py','src/test/test_subcell_response_workflow.py','benchmarks/collect_phase_explicit_accuracy.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V60 stage identity')
    return json.loads(p.read_text())


def parent(role):
    from .trace_interior_scope import stage as previous,parent as previous_parent
    from .phase_deployment_scope import stage as deployed
    if role in ('M67','M68'):return previous(role)
    if role in ('R6','R7'):return previous_parent(role)
    if role=='C6':return deployed('C6')
    raise ValueError('frozen parent inventory')


def case_spec(role):
    if role=='LOCAL_RESPONSE':return dict(degree=6,splits=[1,1,2],cells=160,independent=104832,trace=32832,internal=72000,rows=0,complete_modes=828,
        computation='one preselected local macro; no global PDE or factor',local_inventory=['P6','P7','P8','R2_P6','R4_P6'])
    return dict(plan_record()['cases'][role if role in SOLVES else 'C67'])
def physical_output_options():return dict(volume_backend='direct_phase_quadrature')


def numeric_factor_attempts():
    ledger=window.ledger();rows=list(ledger['runs'])
    if ledger['active'] is not None:rows.append(ledger['active'])
    seen=set();count=0
    for row in rows:
        folder=ARTIFACT/Path(row['folder']).name
        if folder in seen:continue
        seen.add(folder);p=folder/'events.jsonl'
        if p.exists():count+=sum(json.loads(line).get('event')=='h_bounded_numeric_factor_begin' for line in p.read_text().splitlines())
    return count


def require_stage(role):
    if role not in SOLVES:raise ValueError('V60 fixed solve inventory')
    if numeric_factor_attempts()>=3 and not (window.TMP/(role+'_post_resume.json')).exists():raise RuntimeError('V60 three numeric attempt ceiling includes failures')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V60 frozen')
    pre=stage('PREFLIGHT')
    if not pre['pass_gate']:raise RuntimeError('new entity map not qualified')
    if role=='H2':
        if not stage('C67')['independent']['equation_pass']:raise RuntimeError('C67 original form not trustworthy')
        if not stage('LOCAL_RESPONSE').get('mathematics_pass',False):raise RuntimeError('local subcell algebra/mapping not qualified')
    if (ARTIFACT/(role+'.json')).exists() and stage(role).get('returned_arrays') and not (window.TMP/(role+'_post_resume.json')).exists():raise RuntimeError('returned vector consume only')
    if window.available_at_boundary(role)<plan_record()['forecast_case_seconds'][role]:raise RuntimeError('complete case and audit reserve does not fit')


def boundary_provider(cfg,setup,folder,journal):
    from .phase_boundary_checkpoint import StudyBoundaryProvider
    return StudyBoundaryProvider(cfg,setup,folder,journal,entity_face_support=True)


def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json'
    return p if role=='VERIFY_COST' and p.exists() else None
