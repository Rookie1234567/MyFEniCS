"""V32 opt-in window; each auxiliary attempt is immutable and charged once."""
import hashlib
import json
from pathlib import Path
from src.io.task042_profile import ROOT
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.solvers.return_block_window import CAPS

CARRIED_SECONDS = 52.68017605994828
TMP = ROOT / 'tmp/task042/v32'
_window = DiagnosticWindow(TMP, CAPS, 'V32', carried_auxiliary_seconds=CARRIED_SECONDS)
WINDOW_PATH = _window.WINDOW_PATH
LEDGER_PATH = _window.LEDGER_PATH
JOURNAL_PATH = _window.JOURNAL_PATH
snapshot = _window.snapshot
require_live = _window.require_live
auxiliary_wall = _window.auxiliary_wall
journal = _window.journal
ledger = _window.ledger
validate_increment = _window.validate_increment
guard_worker_parent = _window.guard_worker_parent
settle_run = _window.settle_run

QUALIFICATION_FILES = (
    'src/runners/diagnostic_storage.py', 'src/solvers/return_block_v32_window.py',
    'src/io/return_block_v32.py', 'src/io/return_block_diagnostic.py',
    'src/io/task042_profile.py', 'scripts/run_case.py',
    'src/runners/return_block_diagnostic.py', 'src/runners/task042_shared.py',
    'src/solvers/return_block_study.py', 'src/solvers/return_block_direction.py',
    'src/solvers/bounded_diagnostic_window.py',
    'benchmarks/task042_diagnostic_auxiliary.py', 'benchmarks/task042_v31_checks.py',
    'benchmarks/collect_task042_return_direction.py',
    'src/test/task042_v31_workflow_fixture.py', 'src/test/test_task042_v32_workflow.py',
    'input/task042_neural_coarse_inverse/return_block_direction_v32.json',
    'input/task042_neural_coarse_inverse/v32_return_direction_diagnostic.dat',
)
REQUIRED_COVERAGE = ('storage_scope', 'actual_study_workflow', 'namespace',
                     'accounting', 'closed_rejection', 'former_fixture')


def implementation_hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in QUALIFICATION_FILES}


def require_qualification():
    pointer = json.loads((TMP / 'pre_qualification.json').read_text())
    path = Path(pointer['path']).resolve()
    if not path.is_relative_to(TMP.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != pointer['sha256']:
        raise ValueError('V32 qualification receipt path/hash')
    proof = json.loads(path.read_text())
    summary = json.loads((path.parent.parent / 'summary.json').read_text())
    if (summary['classification'] != 'COMPLETED' or summary['leader_exit_code'] != 0
            or summary['source_state']['source_sha'] != proof['source_sha']
            or proof['status'] != 'PASSED'
            or tuple(proof['coverage']) != REQUIRED_COVERAGE
            or proof['implementation_hashes'] != implementation_hashes()):
        raise ValueError('V32 pre-test qualification invalid for current implementation')
    test = Path(proof['test_receipt']['path']).resolve()
    if not test.is_relative_to(path.parent) or hashlib.sha256(test.read_bytes()).hexdigest() != proof['test_receipt']['sha256']:
        raise ValueError('V32 test receipt differs')
    return proof


def actor_timeout(clock, book):
    # All failed auxiliary attempts remain charged; reserve checker and cleanup.
    return min(480., 600. - auxiliary_wall() - book['actor_wall_seconds'] - 20. - 10.,
               clock['heavy_remaining_seconds'])
