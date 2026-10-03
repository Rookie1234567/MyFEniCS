"""V28 opt-in continuation; V27 window stays closed and costs remain charged."""
from src.io.task042_profile import ROOT
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.solvers.return_block_window import CAPS
CARRIED_V27_AUXILIARY_SECONDS=12.366657367907465
_window=DiagnosticWindow(ROOT/'tmp/task042/v28',CAPS,'V28',carried_auxiliary_seconds=CARRIED_V27_AUXILIARY_SECONDS)
TMP=_window.TMP;WINDOW_PATH=_window.WINDOW_PATH;LEDGER_PATH=_window.LEDGER_PATH;JOURNAL_PATH=_window.JOURNAL_PATH
snapshot=_window.snapshot;require_live=_window.require_live;auxiliary_wall=_window.auxiliary_wall
journal=_window.journal;ledger=_window.ledger;validate_increment=_window.validate_increment
guard_worker_parent=_window.guard_worker_parent;settle_run=_window.settle_run
