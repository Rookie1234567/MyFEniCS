"""V33 opt-in window; each auxiliary attempt is immutable and charged once."""
import hashlib
import json
from pathlib import Path
from src.io.task042_profile import ROOT
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.solvers.full_input_block_correction import CAPS

CARRIED_SECONDS = 151.4889468078036
TMP = ROOT / 'tmp/task042/v33'
_window = DiagnosticWindow(TMP, CAPS, 'V33', carried_auxiliary_seconds=CARRIED_SECONDS)
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
    'src/runners/diagnostic_storage.py', 'src/solvers/full_input_block_v33_window.py',
    'src/io/full_input_block_v33.py', 'src/io/return_block_diagnostic.py',
    'src/io/task042_profile.py', 'scripts/run_case.py',
    'src/runners/return_block_diagnostic.py', 'src/runners/task042_shared.py',
    'src/solvers/full_input_block_study.py', 'src/solvers/full_input_block_correction.py', 'src/solvers/return_block_direction.py',
    'src/solvers/bounded_diagnostic_window.py',
    'benchmarks/task042_diagnostic_auxiliary.py', 'benchmarks/task042_v31_checks.py',
    'benchmarks/collect_task042_return_direction.py', 'benchmarks/task042_full_input_checker.py',
    'benchmarks/task042_return_certificates.py',
    'src/test/task042_v31_workflow_fixture.py', 'src/test/test_task042_v33_workflow.py',
    'input/task042_neural_coarse_inverse/full_input_block_v33.json',
    'input/task042_neural_coarse_inverse/v33_full_input_diagnostic.dat',
)
REQUIRED_COVERAGE = ('storage_scope', 'actual_study_workflow', 'namespace',
                     'accounting', 'closed_rejection', 'former_fixture', 'fixed_full_input', 'cached_checker')


def implementation_hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in QUALIFICATION_FILES}


def require_qualification():
    pointer = json.loads((TMP / 'pre_qualification.json').read_text())
    path = Path(pointer['path']).resolve()
    if not path.is_relative_to(TMP.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != pointer['sha256']:
        raise ValueError('V33 qualification receipt path/hash')
    proof = json.loads(path.read_text())
    summary = json.loads((path.parent.parent / 'summary.json').read_text())
    if (summary['classification'] != 'COMPLETED' or summary['leader_exit_code'] != 0
            or summary['source_state']['source_sha'] != proof['source_sha']
            or proof['status'] != 'PASSED'
            or tuple(proof['coverage']) != REQUIRED_COVERAGE
            or proof['implementation_hashes'] != implementation_hashes()):
        raise ValueError('V33 pre-test qualification invalid for current implementation')
    test = Path(proof['test_receipt']['path']).resolve()
    if not test.is_relative_to(path.parent) or hashlib.sha256(test.read_bytes()).hexdigest() != proof['test_receipt']['sha256']:
        raise ValueError('V33 test receipt differs')
    return proof


def actor_timeout(clock, book):
    # All failed auxiliary attempts remain charged; reserve checker and cleanup.
    return min(180., 600. - auxiliary_wall() - book['actor_wall_seconds'] - 20. - 10.,
               clock['heavy_remaining_seconds'])


def allow_entry_repair():
    """Only a settled software failure with zero of every real operation."""
    book=ledger()
    return (not book['closed'] and book['active'] is None and bool(book['runs'])
            and all(run['classification']=='WORKER_FAILED' and not any(run['counts'].values())
                    and not any(run['upper'].values()) and run['descendants_cleared']
                    for run in book['runs']))
