"""Explicit V34 namespace; original physical loader and B_full study unchanged."""
import sys
from src.io.return_block_diagnostic import ROOT, checked_json, physical_state, previous_name
from src.io.return_block_diagnostic import load_return_diagnostic as _load
from src.solvers.full_input_block_correction import FAMILY
from src.solvers import full_input_block_v34_window as window
from src.solvers.neural_fe_action_packet import file_hash

LABEL = 'V34'
ARTIFACT_ROOT = ROOT/'benchmarks/artifacts/task042/v34'
PLAN_PATH = ROOT/'input/task042_neural_coarse_inverse/full_input_block_v34.json'


def load_return_diagnostic(path):
    return _load(path, namespace=sys.modules[__name__])


def publish(name, path):
    from src.runners.task042_shared import write_json
    write_json(ARTIFACT_ROOT/(name+'.json'),dict(path=str(path),sha256=file_hash(path)))
