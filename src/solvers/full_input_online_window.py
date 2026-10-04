"""V35 new online scope: immutable clock, paid probes and conservative quotas."""
import hashlib
import json
import signal
import time
from pathlib import Path

from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers.bounded_diagnostic_window import DiagnosticWindow

TMP = ROOT / 'tmp/task042/v35'
CAPS = dict(actions=2200, pc_apply=550, factor_readers=14,
            joint_lu_solve=1120, outer_lu_solve=3420,
            explicit_triangular_pass=9200, port_factors=6,
            port_solves=2400, port_rhs_columns=2400, original_audits=4,
            arnoldi=512, cycles=2)


class OnlineWindow(DiagnosticWindow):
    def __init__(self, folder):
        super().__init__(folder, CAPS, 'V35')

    def probe_wall(self):
        return sum(json.loads(p.read_text())['elapsed_seconds']
                   for p in self.TMP.glob('probe_*.json'))

    def auxiliary_wall(self):
        return super().auxiliary_wall() + sum(r['actor_wall_seconds']
            for r in self.ledger()['runs'] if r.get('role')=='VERIFY')

    def charged_wall(self):
        return self.auxiliary_wall() + self.probe_wall() + self.ledger()['actor_wall_seconds']

    def require_retry_ready(self):
        self.require_live(margin=30)
        if self.ledger()['closed'] or self.ledger()['active'] is not None:
            raise RuntimeError('V35 closed/active boundary')
        p = self.TMP / 'resource_wait.json'
        if p.exists() and time.monotonic() < json.loads(p.read_text())['next_probe_monotonic']:
            raise RuntimeError('RESOURCE_WAIT: paid backoff has not elapsed')
        if self.probe_wall() >= 20 or self.charged_wall() >= 870:
            raise RuntimeError('V35 probe/total budget exhausted')

    def wait_after_stop(self, cause, receipt):
        p = self.TMP / 'resource_wait.json'
        previous = json.loads(p.read_text()) if p.exists() else {}
        repetitions = previous.get('repetitions', 0) + 1
        delay = min(1800., 120. * 2 ** min(repetitions - 1, 4))
        write_json(p, dict(cause=cause, repetitions=repetitions,
                          backoff_seconds=delay, next_probe_monotonic=time.monotonic()+delay,
                          receipt_path=str(receipt)))
        self.journal('resource_wait', cause=cause, backoff_seconds=delay)

    def admission(self, probe, *, receipt_path, source_sha=None, **kwargs):
        self.require_retry_ready()
        seconds = min(20-self.probe_wall(), 870-self.charged_wall(),
                      self.require_live()['heavy_remaining_seconds'])
        path = self.TMP / ('probe_%03d.json' % (len(list(self.TMP.glob('probe_*.json')))+1))
        receipt = Path(receipt_path)
        began = time.monotonic()
        baseline, error = None, None
        old = signal.getsignal(signal.SIGALRM)
        def expired(*_):
            raise TimeoutError('V35 paid probe limit')
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            baseline = probe(receipt_path=receipt, **kwargs)
            return baseline
        except Exception as exc:
            error = repr(exc)
            raw = json.loads(receipt.read_text()) if receipt.exists() else {}
            failed = [k for k, v in raw.get('gates', {}).items() if v == 'FAIL']
            if failed:
                self.wait_after_stop(','.join(failed), receipt)
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
            with path.open('x') as stream:
                json.dump(dict(elapsed_seconds=time.monotonic()-began, source_sha=source_sha,
                               receipt_path=str(receipt), admitted=baseline is not None,
                               error=error, overlapped_supervised_interval=False), stream)

    def actor_timeout(self):
        return min(600-self.ledger()['actor_wall_seconds'], 870-self.charged_wall(),
                   self.require_live()['heavy_remaining_seconds'])

    def settle_run(self, directory, summary, launch_wall_seconds):
        # Preserve the pending operation upper bound before settling it.
        write_json(Path(directory)/'settlement_counts.json', self.ledger()['active'])
        result = super().settle_run(directory, summary, launch_wall_seconds)
        result['runs'][-1]['role'] = summary['stage'].split('-',1)[1]
        if result['runs'][-1]['role']=='VERIFY':
            result['actor_wall_seconds'] -= summary['elapsed_seconds']
        write_json(self.LEDGER_PATH,result)
        if summary['classification'] == 'RESOURCE_CONTROLLED_STOP' and summary['descendants_cleared']:
            self.wait_after_stop('RESOURCE_CONTROLLED_STOP', Path(directory)/'run_summary.json')
        return result


_window = OnlineWindow(TMP)
WINDOW_PATH, LEDGER_PATH = _window.WINDOW_PATH, _window.LEDGER_PATH
JOURNAL_PATH = _window.JOURNAL_PATH
snapshot, require_live, ledger = _window.snapshot, _window.require_live, _window.ledger
journal, validate_increment = _window.journal, _window.validate_increment
guard_worker_parent, settle_run = _window.guard_worker_parent, _window.settle_run
admission, require_retry_ready = _window.admission, _window.require_retry_ready
actor_timeout, auxiliary_wall = _window.actor_timeout, _window.auxiliary_wall
charged_wall, probe_wall = _window.charged_wall, _window.probe_wall


def implementation_hashes():
    paths = ('src/solvers/full_input_online.py', 'src/solvers/full_input_online_study.py',
             'src/solvers/full_input_online_window.py', 'src/runners/full_input_online.py',
             'src/io/full_input_online.py', 'src/runners/task042_shared.py',
             'scripts/run_case.py', 'benchmarks/check_full_input_online.py',
             'src/solvers/gmres_cycle_commit.py', 'src/solvers/resumable_trace_gmres.py',
             'src/solvers/return_block_direction.py', 'src/solvers/class_batch_action.py',
             'src/solvers/neural_fe_action_packet.py', 'src/solvers/neural_fe_blind_reference.py',
             'benchmarks/qualify_full_input_online.py', 'src/test/test_task042_v35_online.py',
             'src/io/task042_profile.py', 'src/runners/diagnostic_storage.py',
             'input/task042_neural_coarse_inverse/full_input_online_v35.json',
             'input/task042_neural_coarse_inverse/v35_online_cold.dat',
             'input/task042_neural_coarse_inverse/v35_verify.dat')
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}


def require_qualification():
    p = TMP/'pre_qualification.json'
    proof = json.loads(p.read_text())
    if proof['status'] != 'PASSED' or proof['implementation_hashes'] != implementation_hashes():
        raise ValueError('V35 current implementation qualification missing/mismatch')
    receipt = Path(proof['test_receipt']['path']).resolve()
    if not receipt.is_relative_to(TMP) or hashlib.sha256(receipt.read_bytes()).hexdigest() != proof['test_receipt']['sha256']:
        raise ValueError('V35 test receipt mismatch')
    run = json.loads((receipt.parent/'summary.json').read_text())
    tests = json.loads(receipt.read_text())
    if (run['classification']!='COMPLETED' or run['leader_exit_code']!=0
            or not run['descendants_cleared'] or tests['status']!='PASSED'
            or tests['implementation_hashes']!=proof['implementation_hashes']):
        raise ValueError('V35 supervised final-source tests not successful')
    return proof
