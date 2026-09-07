"""Single-run R0 profile reservation and cumulative task computation ledger."""

import fcntl
import json
from pathlib import Path
import time

from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import REFERENCE_PROFILE
from .physical_intermediate import _atomic_json
from .physical_pc_profile import INPUT_SHA, verified_checkpoint


def launch_profile(specification, checkpoint, budget_path):
    from .task038_launcher import launch_specification

    if (specification.solver.get('preconditioner') != REFERENCE_PROFILE or
            specification.input_sha256 != INPUT_SHA):
        raise InputError('PC profile requires the unchanged A2R reference profile')
    try:
        verified_checkpoint(checkpoint, specification.physical_model_sha256)
    except (OSError, ValueError) as exc:
        raise InputError(str(exc)) from exc
    budget_path = Path(budget_path).resolve()
    budget_path.parent.mkdir(parents=True, exist_ok=True)
    with budget_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = json.loads(budget_path.read_text()) if budget_path.exists() else dict(
            schema='task39extra.review-v1-compute-budget.v1', limit_seconds=36000, attempts=[])
        if budget['limit_seconds'] != 36000:
            raise InputError('batch limit must be 36000 seconds')
        if any(a.get('kind') == 'R0_profile' for a in budget['attempts']):
            raise InputError('R0 profile attempt already reserved; no automatic rebuild/retry')
        if sum(a['elapsed_seconds'] for a in budget['attempts'])+1830 > 36000:
            raise InputError('insufficient batch budget for setup-inclusive profile and cleanup')
        started = time.monotonic()
        attempt = dict(kind='R0_profile', status='RESERVED', elapsed_seconds=1830,
                       reserved_seconds=1830, full_pc_limit=7, started_timestamp_ns=time.time_ns())
        budget['attempts'].append(attempt)
        _atomic_json(budget_path, budget)
        try:
            config = dict(checkpoint=str(Path(checkpoint).resolve()), budget_ledger=str(budget_path),
                          variant='R0', complete_pc_limit=7, batch_limit_seconds=1800,
                          deadline_monotonic=started+1800)
            result = launch_specification(specification, pc_profile=config)
            attempt.update(status=result['result_classification'], run_directory=result['run_directory'])
            return result
        except BaseException as exc:
            attempt.update(status='FAILED', exception_type=type(exc).__name__, exception_message=str(exc))
            raise
        finally:
            attempt['elapsed_seconds'] = time.monotonic()-started
            _atomic_json(budget_path, budget)
