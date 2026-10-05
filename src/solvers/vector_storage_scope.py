"""V48 immutable, storage-only, opt-in campaign and clean-source guard."""
import json
import subprocess
from pathlib import Path

from src.solvers.bound_array_identity import file_hash, read_json
from src.solvers.trace_selection_scope import SelectionWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / 'input/task042_neural_coarse_inverse/vector_storage_v48.json'
ARTIFACT = ROOT / 'benchmarks/artifacts/task042/v48'
CAPS = {'actions': 0, 'B_actions': 0}


class StorageWindow(SelectionWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.CAPS = CAPS

    def remaining(self, role):
        self.require_ready()
        rows = self.ledger()['runs']
        prefix = 'P2_' if role.startswith('P2_') else 'P3_' if role.startswith('P3_') else 'P4_' if role.startswith('P4_') else 'auxiliary_'
        limit = {'P2_':1800, 'P3_':900, 'P4_':180, 'auxiliary_':720}[prefix]
        used = sum(r['elapsed_seconds'] for r in rows if r['role'].startswith(prefix)) if prefix != 'auxiliary_' else sum(r['elapsed_seconds'] for r in rows if not r['role'].startswith(('P2_', 'P3_', 'P4_')))
        return min(limit-used, self.total-self.reserve-self.charged_wall(), self.snapshot()['heavy_remaining_seconds'])


window = StorageWindow(ROOT/'tmp/task042/v48', label='V48', total=3600,
                       component=1800, auxiliary=720, probe=90, reserve=180, bootstrap=0)


def plan_record():
    p = json.loads(PLAN.read_text())
    if p['review_commit'] != 'e73baa45f59c0fcfc12ee1c00614c6933568f27e' or p['A_AH_B'] != 0:
        raise ValueError('V48 authority/no original action')
    if [p[k] for k in ('new_storage_bytes','task_storage_bytes','free_bytes','evidence_reserve_bytes')] != [2**30,24*2**30,50*2**30,256*2**20]:
        raise ValueError('V48 frozen/live storage')
    return p


def implementation_hashes():
    names = ['scripts/activate_task042.sh','src/runners/port_preparation.py',
             'src/runners/task042_shared.py','benchmarks/subreaper_watchdog.py',
             'src/solvers/port_preparation_window.py','src/solvers/neural_decision_scope.py',
             'src/solvers/trace_selection_scope.py','src/solvers/vector_storage_scope.py',
             'src/solvers/lossless_vector_bank.py','src/solvers/causal_storage_predictor.py',
             'src/solvers/vector_storage_study.py','src/solvers/bound_array_identity.py',
             'benchmarks/check_vector_bank.py','benchmarks/qualify_vector_storage.py',
             'src/test/test_lossless_vector_bank.py',str(PLAN.relative_to(ROOT))]
    return {n:file_hash(ROOT/n) for n in names}


def assert_snapshot(expected_sha, actual_sha, expected_hashes, actual_hashes, dirty):
    if dirty or expected_sha != actual_sha or expected_hashes != actual_hashes:
        raise RuntimeError('scientific reader rejected source HEAD/worktree snapshot')


def guard_source(folder):
    state = json.loads((Path(folder)/'run_manifest.json').read_text())
    git = ['git','-c','gc.auto=0','-c','maintenance.auto=false']
    sha = subprocess.check_output(git+['rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty = subprocess.check_output(git+['status','--porcelain'],cwd=ROOT,text=True)
    hashes = implementation_hashes()
    assert_snapshot(state['source_sha'],sha,state['implementation_hashes'],hashes,dirty)
    # Bind the snapshot to committed blobs too, rather than trusting a caller's
    # self-reported current hash. This precedes any scientific array access.
    import hashlib
    for n,h in hashes.items():
        blob = subprocess.check_output(git+['show',sha+':'+n],cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != h:
            raise RuntimeError('uncommitted scientific implementation: '+n)
    return {'source_sha':sha,'implementation_hashes':hashes,'clean':True}


def stage(name):
    return read_json(json.loads((ARTIFACT/(name+'.json')).read_text()),ROOT)
