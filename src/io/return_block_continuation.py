"""Explicit V28 namespace over the unchanged return diagnostic contract."""
import sys
from src.io.return_block_diagnostic import FAMILY,ROOT,checked_json,physical_state,previous_name
from src.io.return_block_diagnostic import load_return_diagnostic as _load
from src.solvers import return_block_continuation_window as window
from src.solvers.neural_fe_action_packet import file_hash
LABEL='V28'
ARTIFACT_ROOT=ROOT/'benchmarks/artifacts/task042/v28'
PLAN_PATH=ROOT/'input/task042_neural_coarse_inverse/return_block_direction_v28.json'
def load_return_diagnostic(path):return _load(path,namespace=sys.modules[__name__])
def publish(name,path):
    from src.runners.task042_shared import write_json
    write_json(ARTIFACT_ROOT/(name+'.json'),dict(path=str(path),sha256=file_hash(path)))
