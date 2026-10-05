"""V50 immutable accuracy scope; no historical ledger is reopened."""
import hashlib
import json
from pathlib import Path

from src.solvers.scattering_anchor_scope import AnchorWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / 'input/task042_neural_coarse_inverse/scattering_accuracy_v50.json'
ARTIFACT = ROOT / 'benchmarks/artifacts/task042/v50'
STAGES = ('BOUNDARY', 'ATTRIBUTION', 'SCREEN', 'FLAT_P5', 'FLAT_SELECTED',
          'NOTCH_LOW', 'NOTCH_HIGH', 'GRAM_CONTROL', 'VERIFY', 'COST')
SOLVES = ('FLAT_P5', 'FLAT_SELECTED', 'NOTCH_LOW', 'NOTCH_HIGH', 'GRAM_CONTROL')
class AccuracyWindow(AnchorWindow):
    def remaining(self, role):
        self.require_ready()
        return min(3600 if role in STAGES else 900,
                   self.total-self.charged_wall(), self.snapshot()['heavy_remaining_seconds'])


window = AccuracyWindow(ROOT/'tmp/task042/v50', label='V50', total=18000,
                      component=18000, auxiliary=18000, probe=120,
                      reserve=600, bootstrap=0)


def plan_record():
    p = json.loads(PLAN.read_text())
    if p['review_commit'] != 'da151228815b08126dc636d3e195673ba04fe45f' or p['stages'] != list(STAGES):
        raise ValueError('V50 authority/stage inventory')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')] != [4*2**30,32*2**30,50*2**30,256*2**20]:
        raise ValueError('V50 frozen/live storage limits')
    return p


def implementation_hashes():
    from src.solvers.scattering_anchor_scope import implementation_hashes as parent
    names = list(parent()) + ['src/solvers/scattering_accuracy_scope.py',
        'src/solvers/scattering_accuracy.py','src/solvers/scattering_accuracy_boundary.py',
        'src/solvers/scattering_accuracy_fields.py','src/io/scattering_accuracy.py',
        'src/test/test_scattering_accuracy.py','benchmarks/qualify_scattering_accuracy.py',
        'benchmarks/collect_scattering_accuracy.py',str(PLAN.relative_to(ROOT)),
        'src/solvers/hcurl_affine_isotropic_tensor.py','src/solvers/target_boundary_witness.py',
        'src/solvers/directional_boundary.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))}


def stage(name):
    row = json.loads((ARTIFACT/(name+'.json')).read_text())
    p = Path(row['path']).resolve()
    if not p.is_relative_to(ARTIFACT) or hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
        raise ValueError('V50 stage pointer identity')
    return json.loads(p.read_text())


def selection():
    try:return stage('SCREEN')['selection']
    except FileNotFoundError:return {'grid':'X2','low_degree':5,'high_degree':6,'admitted':False,'status':'pending_screen'}
