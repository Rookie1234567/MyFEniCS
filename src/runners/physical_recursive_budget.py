"""One original LO G2 attempt, charged against the existing V6 compute ledger."""
import fcntl
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.physical_recursive_profile import RECURSIVE_LO
from .physical_intermediate import _atomic_json
from .workflow_timebase import ClockBudget, clock_sample, CONSERVATIVE_REALTIME


def launch_recursive_workflow(specification, budget_path):
    from .task038_launcher import launch_specification
    if budget_path is None:
        raise InputError('recursive G2 requires the existing V6 budget ledger')
    if specification.solver['preconditioner'] != RECURSIVE_LO or specification.geometry.get('cell_notch'):
        raise InputError('only original LO G2 is enabled; HI has no realized accuracy qualification')
    if specification.physical_model_sha256 != '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f':
        raise InputError('original physical identity differs')
    path=Path(budget_path).resolve()
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        budget=json.loads(path.read_text())
        if (budget.get('G0_G1_limit_seconds')!=5400 or budget.get('batch_limit_seconds')!=43200 or
                budget.get('old_V5_budget')!='not reused'):
            raise InputError('requires V6 compute budget; V5 budget is not reusable')
        if budget.get('g2_attempts'):
            raise InputError('unique G2 original LO attempt already reserved')
        if budget['batch_remaining'] < 14400:
            raise InputError('insufficient batch budget for workflow reservation')
        entry=dict(profile=RECURSIVE_LO,input_sha256=specification.input_sha256,
            status='RESERVED',reserved_seconds=14400)
        budget['g2_attempts']=[entry]
        budget['batch_remaining']-=14400
        budget['charged_including_reserve']+=14400
        _atomic_json(path,budget)
        clock=ClockBudget(clock_sample(),policy=CONSERVATIVE_REALTIME)
        try:
            result=launch_specification(specification)
            entry.update(status=result['result_classification'],run_directory=result['run_directory'],
                parent_classification=result.get('resource_authority',{}).get('classification'))
            return result
        except BaseException as exc:
            entry.update(status='FAILED',reason=str(exc));raise
        finally:
            entry['clock_interval']=clock.update(clock_sample())
            charge=entry['clock_interval']['budget_seconds'];entry['charged_seconds']=charge
            budget['batch_remaining']+=14400-charge
            budget['charged_including_reserve']+=charge-14400
            _atomic_json(path,budget)
