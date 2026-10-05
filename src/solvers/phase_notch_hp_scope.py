"""V52 finite hp accuracy queue with its own immutable, charged window."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT=Path(__file__).resolve().parents[2]
PLAN=ROOT/'input/task042_neural_coarse_inverse/phase_notch_hp_v52.json'
ARTIFACT=ROOT/'benchmarks/artifacts/task042/v52'
STAGES=('SETUP','H','P','HP','T','M','VERIFY_COST')
SOLVES=STAGES[1:-1]


class HPWindow(AccuracyWindow):
    def remaining(self,role):
        self.require_ready()
        reserve=1200 if role in SOLVES else 180
        limits=plan_record().get('case_wall_seconds',{})
        used=sum(json.loads((Path(r['folder'])/'run_summary.json').read_text()).get('launch_wall_seconds',r['elapsed_seconds']) if (Path(r['folder'])/'run_summary.json').exists() else r['elapsed_seconds'] for r in self.ledger()['runs'] if r['role']==role)
        return min(float(limits.get(role,3600 if role in STAGES else 900))-used,
                   self.total-self.charged_wall()-reserve,
                   self.snapshot()['heavy_remaining_seconds']-reserve)


window=HPWindow(ROOT/'tmp/task042/v52',label='V52',total=18000,
                component=18000,auxiliary=18000,probe=120,reserve=180,bootstrap=0)


def plan_record():
    p=json.loads(PLAN.read_text())
    if p['review_commit']!='f89b4585c1e19e6e08f051dcbf65ec7643302ea8' or p['stages']!=list(STAGES):
        raise ValueError('V52 authority and stage inventory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')]!=[8*2**30,46*2**30,50*2**30,256*2**20]:
        raise ValueError('V52 frozen/live storage inventory')
    return p


def implementation_hashes():
    from .phase_explicit_accuracy_scope import implementation_hashes as parent
    names=list(parent())+[str(PLAN.relative_to(ROOT)),
        'src/solvers/phase_notch_hp_scope.py','src/solvers/phase_notch_hp.py',
        'src/solvers/phase_notch_hp_capacity.py','src/solvers/phase_notch_hp_fields.py','src/solvers/phase_notch_hp_modes.py',
        'src/io/phase_notch_hp.py','src/test/test_phase_notch_hp.py',
        'benchmarks/qualify_phase_notch_hp.py','benchmarks/collect_phase_notch_hp.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(name):
    pointer=json.loads((ARTIFACT/(name+'.json')).read_text());path=Path(pointer['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest()!=pointer['sha256']:
        raise ValueError('V52 immutable stage identity')
    return json.loads(path.read_text())


def case_spec(role):
    p=plan_record()
    if role in ('SETUP','VERIFY_COST'):role='P'
    row=dict(p['cases'][role])
    if role=='T':
        s=window.TMP/'transverse_selection.json'
        if not s.exists():return dict(row,status='CONDITIONAL_PENDING',splits=None)
        pick=json.loads(s.read_text());row.update(splits=pick['splits'],selection=pick)
    if role=='M':
        s=window.TMP/'mode_selection.json'
        if not s.exists():return dict(row,status='CONDITIONAL_PENDING',splits=None,degree=None)
        pick=json.loads(s.read_text());row.update(pick['case_spec'],complete_modes=828,selection=pick)
        row['rows']=row['trace']+828
    row.setdefault('complete_modes',532)
    return row
