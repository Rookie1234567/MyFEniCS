"""Small V35 adapter over the established stage, admission and subreaper."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from benchmarks.subreaper_watchdog import supervise
from src.io import full_input_online as io
from src.runners.block_direction_diagnostic import DirectionStage
from src.runners.task042_shared import (write_json, audit, SharedHealth, shared_envelope)
from src.solvers import full_input_online_window as window


class OnlineStage(DirectionStage):
    def __init__(self, specification, directory):
        self.run_limit = specification.execution['timeout_seconds']
        super().__init__(specification, directory, io_module=io, window_module=window,
                         actor_limit=900, artifact_limit=32*2**20)

    def guard(self, **kwargs):
        self.sample(); self.window.require_live(margin=10)
        if time.monotonic()-self.run_started >= self.run_limit-10:
            raise RuntimeError('V35 stage charged wall / cleanup margin')
        if self.window.charged_wall()+time.monotonic()-self.run_started >= 870:
            raise RuntimeError('V35 total charged wall / cleanup reserve')
        now = time.monotonic()
        if now-getattr(self, 'last_storage_check', 0)>5:
            from src.runners.diagnostic_storage import enforce
            enforce(self.io.ROOT, batch=35)
            self.last_storage_check = now

    def audit(self, z):
        self.pc_count('original_audits')
        from scipy.linalg import lu_factor, lu_solve
        if not hasattr(self, 'audit_Hp_factor'):
            self.pc_count('port_factors')
            self.audit_Hp_factor = lu_factor(self.packet.a['Hp'], check_finite=True)
        def solve(rhs):
            self.pc_count('port_solves')
            self.pc_count('port_rhs_columns')
            return lu_solve(self.audit_Hp_factor, rhs, check_finite=True)
        return self.packet.audit(z, port_solver=solve)

    def finish(self, result):
        if hasattr(self, 'fast'):
            result.update(fast_action_counts=self.fast.counts.copy(),
                          fast_action_costs_seconds=self.fast.costs.copy())
        result.update(actual_equivalent_actions=self.counts['actions'])
        super().finish(result)


def execute_stage(stage):
    from src.solvers.full_input_online_study import run, verify
    return verify(stage) if stage.name=='VERIFY' else run(stage)


def auxiliary(command, phase, attempt):
    """Bounded foreground helper; every admitted failure stays charged."""
    from src.runners.diagnostic_storage import enforce
    window.require_retry_ready()
    if phase not in ('pre', 'check', 'docs') or not attempt.isdigit():
        raise ValueError('V35 registered auxiliary phase/attempt')
    seconds = min(250-window.auxiliary_wall(), 870-window.charged_wall(),
                  window.require_live()['heavy_remaining_seconds'])
    if seconds <= 5:
        raise RuntimeError('V35 auxiliary budget exhausted')
    enforce(io.ROOT, batch=35, reserve_bytes=4*2**20)
    folder = window.TMP/('aux_'+phase+'_'+attempt)
    folder.mkdir(parents=True, exist_ok=False)
    with (io.ROOT/'tmp/task042/task042_shared.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        source = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
        baseline = window.admission(audit, receipt_path=folder/'admission.json',
            source_sha=source, observed_activity=True, input_path=' '.join(command))
        os.sched_setaffinity(0, {baseline['cpu']}); os.nice(10)
        subprocess.run(['ionice','-c','3','-p',str(os.getpid())], check=True)
        write_json(folder/'baseline.json', baseline)
        result = supervise(command, folder/'supervision', wall_seconds=seconds-2,
            interval=.5, timebase_guard=True, hard_stop_immediate=True,
            rss_hard_limit_bytes=2*2**30, rss_warning_bytes=2**30,
            memory_envelope_provider=shared_envelope, include_pss=False,
            source_state=dict(source_sha=source, role='V35 '+phase, command=command),
            worker_environment={'TASK042_V35_AUX_DIRECTORY':str(folder),
                                'TASK042_WATCHDOG_PARENT_PID':str(os.getpid())},
            health_check=SharedHealth(folder, baseline['neighbor_processes']), stop_on_global_swap=False)
        write_json(folder/'summary.json', result)
        window.journal('auxiliary_settled', phase=phase, attempt=attempt,
                       seconds=result['elapsed_seconds'], classification=result['classification'])
        if result['classification']=='RESOURCE_CONTROLLED_STOP' and result['descendants_cleared']:
            window._window.wait_after_stop('RESOURCE_CONTROLLED_STOP', folder/'summary.json')
        print(json.dumps(dict(folder=str(folder), classification=result['classification'],
                             seconds=result['elapsed_seconds'], exit_code=result['leader_exit_code'])))
        return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 else 1


def main():
    if sys.argv[1]=='--aux':
        return auxiliary(sys.argv[4:], sys.argv[2], sys.argv[3])
    window.guard_worker_parent()
    stage = OnlineStage(io.load_online(sys.argv[1]), Path(sys.argv[2]).resolve())
    result = {}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:
            raise RuntimeError('V35 active source changed')
        result = execute_stage(stage)
    except Exception as exc:
        result = dict(getattr(stage,'partial_result',{}), status='FAILED', error=repr(exc))
        traceback.print_exc()
        raise
    finally:
        stage.finish(result)
    return 0


if __name__=='__main__':
    sys.exit(main())
