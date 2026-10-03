"""V27 alone; no operation can reopen the historical V26 ledger."""
from src.io.task042_profile import ROOT
from src.solvers.bounded_diagnostic_window import DiagnosticWindow

CAPS=dict(actions=64,factor_readers=7,outer_lu_solve=24,joint_lu_solve=8,
    explicit_triangular_pass=64,thin_decompositions=2,port_factors=1,port_solves=128,
    port_rhs_columns=128,new_assemblies=0,new_LU_attempts=0,new_gecon=0)
_window=DiagnosticWindow(ROOT/'tmp/task042/v27',CAPS,'V27')
TMP=_window.TMP;WINDOW_PATH=_window.WINDOW_PATH;LEDGER_PATH=_window.LEDGER_PATH;JOURNAL_PATH=_window.JOURNAL_PATH
snapshot=_window.snapshot;require_live=_window.require_live;auxiliary_wall=_window.auxiliary_wall
journal=_window.journal;ledger=_window.ledger;validate_increment=_window.validate_increment
guard_worker_parent=_window.guard_worker_parent;settle_run=_window.settle_run
