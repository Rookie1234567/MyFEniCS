"""V51 fixed-clock opt-in; never reopens an earlier research ledger."""
import hashlib
import json
from pathlib import Path
from .scattering_accuracy_scope import AccuracyWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT/'input/task042_neural_coarse_inverse/phase_explicit_accuracy_v51.json'
ARTIFACT = ROOT/'benchmarks/artifacts/task042/v51'
STAGES = ('SETUP','FLAT_P4','FLAT_P5','NOTCH_P4','NOTCH_P5','NOTCH_HPROBE','ORDINARY_CONTROL','VERIFY_COST')
SOLVES = STAGES[1:-1]


class PhaseWindow(AccuracyWindow):
    def remaining(self, role):
        self.require_ready()
        return min(3600 if role in STAGES else 900,
                   self.total-self.reserve-self.charged_wall(), self.snapshot()['heavy_remaining_seconds'])


window = PhaseWindow(ROOT/'tmp/task042/v51',label='V51',total=18000,
                     component=18000,auxiliary=18000,probe=120,reserve=600,bootstrap=0)


def plan_record():
    p = json.loads(PLAN.read_text())
    if p['review_commit'] != '97ca0d4e2d90f7479a757e66d43061b7d54bf3aa' or p['stages'] != list(STAGES):
        raise ValueError('V51 frozen authority/inventory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')] != [6*2**30,38*2**30,50*2**30,256*2**20]:
        raise ValueError('V51 frozen/live storage')
    return p


def implementation_hashes():
    names = plan_record()['local_numeric_closure'] + [str(PLAN.relative_to(ROOT)),
        'src/solvers/phase_explicit_accuracy_scope.py','src/solvers/phase_explicit_accuracy.py',
        'src/solvers/phase_explicit_accuracy_fields.py','src/solvers/fixed_phase_fem.py',
        'src/solvers/phase_explicit_accuracy_capacity.py',
        'src/io/phase_explicit_accuracy.py','src/runners/port_preparation.py',
        'scripts/run_case.py','scripts/activate_task042.sh','benchmarks/subreaper_watchdog.py',
        'src/test/test_phase_explicit_accuracy.py','benchmarks/qualify_phase_explicit_accuracy.py',
        'benchmarks/collect_phase_explicit_accuracy.py',
        'input/materials/si_optical_constants_v1.json']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(name):
    p = json.loads((ARTIFACT/(name+'.json')).read_text());path = Path(p['path']).resolve()
    if not path.is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest() != p['sha256']:
        raise ValueError('V51 immutable stage pointer')
    return json.loads(path.read_text())
