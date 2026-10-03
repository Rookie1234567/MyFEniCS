"""V31 alone: old windows remain closed; fixed auxiliary receipts are charged."""
from src.io.task042_profile import ROOT
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.solvers.return_block_window import CAPS

CARRIED_SECONDS=39.94901336694602
TMP=ROOT/'tmp/task042/v31'
_window=DiagnosticWindow(TMP,CAPS,'V31',carried_auxiliary_seconds=CARRIED_SECONDS,
    fixed_auxiliary_summaries=(TMP/'aux_pre/auxiliary_summary.json',TMP/'aux_check/auxiliary_summary.json'))
WINDOW_PATH=_window.WINDOW_PATH;LEDGER_PATH=_window.LEDGER_PATH;JOURNAL_PATH=_window.JOURNAL_PATH
snapshot=_window.snapshot;require_live=_window.require_live;auxiliary_wall=_window.auxiliary_wall
journal=_window.journal;ledger=_window.ledger;validate_increment=_window.validate_increment
guard_worker_parent=_window.guard_worker_parent;settle_run=_window.settle_run
