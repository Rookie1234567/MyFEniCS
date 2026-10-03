"""V34 opt-in: paid repairs and bounded resource waits, with unchanged per-run math."""
import hashlib
import json
import signal
import time
from pathlib import Path
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.solvers.full_input_block_correction import CAPS, EXPECTED
from src.solvers.full_input_block_v33_window import QUALIFICATION_FILES as V33_FILES, check_qualification

CARRIED_SECONDS = 161.20563597988803
CAMPAIGN_CAPS = dict(CAPS, actions=96, factor_readers=3, joint_lu_solve=12,
    explicit_triangular_pass=24, port_factors=3, port_solves=96, port_rhs_columns=96)
TMP = ROOT / 'tmp/task042/v34'


class PaidDiagnosticWindow(DiagnosticWindow):
    def __init__(self, folder):
        super().__init__(folder, CAPS, 'V34', carried_auxiliary_seconds=CARRIED_SECONDS)

    def probe_wall(self):
        return sum(json.loads(p.read_text())['elapsed_seconds'] for p in self.TMP.glob('probe_*.json'))

    def auxiliary_wall(self):
        # Probes run outside supervised intervals: charge once, never overlap.
        return super().auxiliary_wall() + self.probe_wall()

    def validate_increment(self, charged, completed, key, n=1):
        if (key not in CAPS or type(n) is not int or n < 0 or completed[key]+n > CAPS[key]
                or charged[key]+completed[key]+n > CAMPAIGN_CAPS[key]):
            raise RuntimeError('V34 '+key+' per-attempt/cumulative immutable cap')

    def actor_timeout(self, clock, book):
        return min(180., 300.-book['actor_wall_seconds'],
            600.-self.auxiliary_wall()-book['actor_wall_seconds']-20.-10., clock['heavy_remaining_seconds'])

    def allow_entry_repair(self):
        book = self.ledger()
        return (not book['closed'] and book['active'] is None and bool(book['runs'])
            and all(r['classification'] != 'COMPLETED' and r['descendants_cleared'] for r in book['runs'])
            and all(book['charged'][k]+EXPECTED[k] <= CAMPAIGN_CAPS[k] for k in CAPS)
            and self.actor_timeout(self.snapshot(), book) > 10)

    def require_retry_ready(self):
        self.require_live(margin=30)
        path = self.TMP/'resource_wait.json'
        if path.exists() and time.monotonic() < json.loads(path.read_text())['next_probe_monotonic']:
            raise RuntimeError('RESOURCE_WAIT: immutable receipt retained; backoff not elapsed')
        if self.probe_wall() >= 20:
            raise RuntimeError('RESOURCE_DEFERRED: 20-second cumulative admission probe cap')

    def wait_after_stop(self, cause, receipt_path):
        """Only after own tree is cleared; WAIT never grants admission itself."""
        path=self.TMP/'resource_wait.json'
        previous=json.loads(path.read_text()) if path.exists() else {}
        repetitions=previous.get('repetitions',0)+1 if previous.get('cause')==cause else 1
        delay=min(1800.,120.*2**min(repetitions-1,4))
        write_json(path,dict(status='RESOURCE_WAIT',cause=cause,repetitions=repetitions,
            backoff_seconds=delay,next_probe_monotonic=time.monotonic()+delay,receipt_path=str(receipt_path)))
        self.journal('resource_wait_after_own_stop',cause=cause,backoff_seconds=delay,receipt_path=str(receipt_path))

    def admission(self, probe, *, receipt_path, **kwargs):
        """One timed fresh probe; rejection releases the caller's own scoped lock."""
        self.require_retry_ready()
        remaining = min(20.-self.probe_wall(), self.require_live()['heavy_remaining_seconds'],
            600.-self.auxiliary_wall()-self.ledger()['actor_wall_seconds']-10.)
        if remaining <= 0:
            raise RuntimeError('RESOURCE_DEFERRED: admission budget exhausted')
        receipts = list(self.TMP.glob('probe_*.json'))
        target = self.TMP/('probe_%03d.json' % (len(receipts)+1))
        receipt_path = Path(receipt_path)
        source_sha = kwargs.pop('source_sha', None)
        began = time.monotonic(); error = None; baseline = None
        old_handler = signal.getsignal(signal.SIGALRM)
        def expired(*_):
            raise TimeoutError('V34 remaining admission probe budget reached')
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            baseline = probe(receipt_path=receipt_path, **kwargs)
            return baseline
        except Exception as exc:
            error = repr(exc)
            # Only actual resource-gate refusals become WAIT; software bugs stay
            # software failures and can be repaired in the same frozen window.
            raw = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
            rejected = [k for k,v in raw.get('gates',{}).items() if v == 'FAIL']
            if rejected:
                prior = self.TMP/'resource_wait.json'
                previous = json.loads(prior.read_text()) if prior.exists() else {}
                cause = ','.join(rejected)
                repetitions = previous.get('repetitions',0)+1 if previous.get('cause')==cause else 1
                delay = min(1800.,120.*2**min(repetitions-1,4))
                write_json(prior,dict(status='RESOURCE_WAIT',cause=cause,repetitions=repetitions,
                    backoff_seconds=delay,next_probe_monotonic=time.monotonic()+delay,
                    receipt_path=str(receipt_path),error=error))
                self.journal('resource_wait',cause=cause,backoff_seconds=delay,receipt_path=str(receipt_path))
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL,0); signal.signal(signal.SIGALRM,old_handler)
            elapsed = time.monotonic()-began
            record = dict(elapsed_seconds=elapsed,source_sha=source_sha,
                receipt_path=str(receipt_path),receipt_sha256=(hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                    if receipt_path.exists() else None),error=error,admitted=baseline is not None,
                overlapped_supervised_interval=False)
            with target.open('x') as stream:
                json.dump(record,stream,allow_nan=False);stream.flush()

    def settle_run(self, directory, summary, launch_wall_seconds):
        # Runner first persists the raw supervisor result. Every failed charge is
        # bound to that immutable source/exit/cleanup receipt for cached checking.
        raw = Path(directory)/'run_summary.json'
        saved = json.loads(raw.read_text())
        if saved != summary:
            raise ValueError('V34 raw settlement summary differs')
        active = self.ledger()['active']
        if active is None:
            active = dict(source_sha=summary['source_state']['source_sha'],
                completed=dict.fromkeys(CAPS,0),upper=dict.fromkeys(CAPS,0))
        counts_path = Path(directory)/'settlement_counts.json'
        write_json(counts_path,active)
        book = super().settle_run(directory,summary,launch_wall_seconds)
        book['runs'][-1]['summary_receipt'] = dict(path=str(raw),sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
        book['runs'][-1]['write_ahead_receipt'] = dict(path=str(counts_path),sha256=hashlib.sha256(counts_path.read_bytes()).hexdigest())
        write_json(self.LEDGER_PATH,book)
        if summary['classification']=='RESOURCE_CONTROLLED_STOP' and summary['descendants_cleared']:
            self.wait_after_stop('RESOURCE_CONTROLLED_STOP',raw)
        return book


_window = PaidDiagnosticWindow(TMP)
WINDOW_PATH = _window.WINDOW_PATH
LEDGER_PATH = _window.LEDGER_PATH
JOURNAL_PATH = _window.JOURNAL_PATH
snapshot = _window.snapshot
require_live = _window.require_live
auxiliary_wall = _window.auxiliary_wall
probe_wall = _window.probe_wall
journal = _window.journal
ledger = _window.ledger
validate_increment = _window.validate_increment
guard_worker_parent = _window.guard_worker_parent
settle_run = _window.settle_run
actor_timeout = _window.actor_timeout
allow_entry_repair = _window.allow_entry_repair
require_retry_ready = _window.require_retry_ready
admission = _window.admission
wait_after_stop = _window.wait_after_stop
QUALIFICATION_FILES = tuple(dict.fromkeys((*V33_FILES,
    'src/solvers/full_input_block_v34_window.py','src/io/full_input_block_v34.py',
    'src/test/test_task042_v34_workflow.py',
    'input/task042_neural_coarse_inverse/full_input_block_v34.json',
    'input/task042_neural_coarse_inverse/v34_full_input_diagnostic.dat')))
REQUIRED_COVERAGE = ('storage_scope','actual_study_workflow','residual_tolerance',
    'charged_reentry','resource_wait','two_layer_accounting','namespace','closed_rejection',
    'former_fixture','fixed_full_input','cached_checker')


def implementation_hashes():
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in QUALIFICATION_FILES}


def require_qualification():
    return check_qualification(TMP, REQUIRED_COVERAGE, implementation_hashes())
