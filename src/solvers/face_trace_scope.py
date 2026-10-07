"""V61 fixed face inventory, independent immutable window and cost scope."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2];NAMESPACE='v61'
PLAN=ROOT/'input/task042_neural_coarse_inverse/face_trace_enrichment_v61.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v61'
STAGES=('PREFLIGHT','FX','FXY','VERIFY_COST');SOLVES=('FX','FXY')


class FaceWindow(AccuracyWindow):
    def available_at_boundary(self,role):
        reserve=1800 if role in SOLVES else 180
        used=0.
        for r in self.ledger()['runs']:
            if r['role']!=role:continue
            p=Path(r['folder'])/'run_summary.json';used+=json.loads(p.read_text())['launch_wall_seconds'] if p.exists() else r['elapsed_seconds']
        return min(plan_record()['case_wall_seconds'].get(role,900)-used,self.total-self.charged_wall()-reserve,self.snapshot()['heavy_remaining_seconds']-reserve)
    def remaining(self,role):self.require_ready();return self.available_at_boundary(role)
    def launcher_overhead(self):
        seconds=super().launcher_overhead()
        for r in self.ledger()['runs']:
            if r['role'] not in STAGES:continue
            receipts=[p for p in self.TMP.glob(r['role']+'_one_run*/receipt.json') if json.loads(p.read_text())['source_sha']==r['source_sha']]
            summary=Path(r['folder'])/'run_summary.json'
            if len(receipts)==1 and summary.exists():seconds+=max(0.,json.loads(receipts[0].read_text())['elapsed_seconds']-json.loads(summary.read_text())['launch_wall_seconds'])
        return seconds


window=FaceWindow(ROOT/'tmp/task042/v61',label='V61',total=28800,component=28800,auxiliary=28800,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='9077e392a367afd7b90b61a85c1e0952f256b4ee' or p['stages']!=list(STAGES):raise ValueError('V61 authority')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[32*2**30,180*2**30,50*2**30,512*2**20]:raise ValueError('V61 live storage limits')
    if p['memory_budget']!=dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96,neighbor_growth_gib=384,extra_cache_workspace_gib=2) or p['r2_class_cache_bytes']!=16*2**30:raise ValueError('V61 live local/global memory')
    return p


def stage(role):
    row=json.loads((ARTIFACT/(role+'.json')).read_text());p=Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('V61 stage identity')
    return json.loads(p.read_text())


def parent(role):
    from . import local_subcell_scope as previous
    if role=='H2':return previous.stage('H2')
    if role in ('R6','R7'):return previous.parent(role)
    raise ValueError('V61 readonly parent inventory')
def case_spec(role):return dict(plan_record()['cases'][role if role in SOLVES else 'FXY'])
def physical_output_options():return dict(volume_backend='direct_phase_quadrature')
def verification_inventory_for(role):
    p=window.TMP/'scientific_queue_frozen.json';return p if role=='VERIFY_COST' and p.exists() else None


def numeric_factor_attempts():
    book=window.ledger();rows=list(book['runs'])+([] if book['active'] is None else [book['active']]);seen=set();n=0
    for r in rows:
        d=ARTIFACT/Path(r['folder']).name
        if d in seen:continue
        seen.add(d);p=d/'events.jsonl'
        if p.exists():n+=sum(json.loads(line).get('event')=='h_bounded_numeric_factor_begin' for line in p.read_text().splitlines())
    return n


def require_stage(role):
    if role not in SOLVES:raise ValueError('V61 planned solve inventory')
    if numeric_factor_attempts()>=3:raise RuntimeError('V61 numeric factor cap including failures')
    if (window.TMP/'scientific_queue_frozen.json').exists():raise RuntimeError('V61 queue frozen')
    if not stage('PREFLIGHT')['pass_gate']:raise RuntimeError('V61 new face mapping not qualified')
    if (ARTIFACT/(role+'.json')).exists() and stage(role).get('returned_arrays'):raise RuntimeError('returned vector saved-consumer only')
    if window.available_at_boundary(role)<plan_record()['forecast_case_seconds'][role]:raise RuntimeError('V61 complete case and audit reserve does not fit')


def implementation_hashes():
    from .local_subcell_scope import implementation_hashes as prior
    names=list(prior())+[str(PLAN.relative_to(ROOT)),'src/solvers/face_trace_scope.py','src/solvers/face_trace_basis.py',
        'src/solvers/face_trace_mapping.py','src/solvers/face_trace_response.py','src/solvers/face_trace_study.py',
        'src/io/phase_notch_hp.py','src/test/test_face_trace_enrichment.py','benchmarks/qualify_face_trace.py','benchmarks/collect_face_trace.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}
