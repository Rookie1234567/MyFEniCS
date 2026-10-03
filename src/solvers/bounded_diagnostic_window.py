"""Immutable one-actor diagnostic window with write-ahead quota accounting."""
import json
import time
from pathlib import Path
from src.runners.task042_shared import write_json, _json_metadata
from src.solvers.exact_recycle_window import evaluate_window


class DiagnosticWindow:
    def __init__(self,folder,caps,label):
        self.TMP=Path(folder);self.CAPS=caps;self.label=label
        self.WINDOW_PATH=self.TMP/'window.json';self.LEDGER_PATH=self.TMP/'ledger.json'
        self.JOURNAL_PATH=self.TMP/'progress_journal.jsonl'

    def snapshot(self):
        return evaluate_window(json.loads(self.WINDOW_PATH.read_text()),utc_seconds=time.time(),
            monotonic=time.monotonic(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())

    def require_live(self,*,heavy=True,margin=0):
        value=self.snapshot()
        if value['heavy_remaining_seconds' if heavy else 'total_remaining_seconds']<=margin:
            raise RuntimeError(self.label+' immutable deadline reached')
        return value

    def auxiliary_wall(self):
        return sum(json.loads(p.read_text())['elapsed_seconds'] for p in self.TMP.glob('aux_*/summary.json'))

    def journal(self,event,**fields):
        row=dict(event=event,clock=self.snapshot(),shared_workstation=True,**fields)
        with self.JOURNAL_PATH.open('a') as f:
            f.write(json.dumps(_json_metadata(row),ensure_ascii=False,allow_nan=False)+'\n');f.flush()
        return row

    def ledger(self):
        if not self.LEDGER_PATH.exists():
            write_json(self.LEDGER_PATH,dict(charged=dict.fromkeys(self.CAPS,0),runs=[],active=None,closed=False,actor_wall_seconds=0.))
        return json.loads(self.LEDGER_PATH.read_text())

    def validate_increment(self,charged,completed,key,n=1):
        if key not in self.CAPS or not isinstance(n,int) or n<0 or charged[key]+completed[key]+n>self.CAPS[key]:
            raise RuntimeError(self.label+' '+key+' immutable cap')

    def guard_worker_parent(self):
        import ctypes,os,signal
        expected=int(os.environ['TASK042_WATCHDOG_PARENT_PID']);lib=ctypes.CDLL(None,use_errno=True)
        if lib.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:
            raise RuntimeError(self.label+' own supervisor disappeared')
        self.require_live()

    def settle_run(self,directory,summary,launch_wall_seconds):
        row=self.ledger();active=row['active']
        if active is None:active=dict(directory=str(directory),source_sha=summary['source_state']['source_sha'],
            completed=dict.fromkeys(self.CAPS,0),upper=dict.fromkeys(self.CAPS,0))
        if active['directory']!=str(directory):raise ValueError(self.label+' actor identity differs')
        clean=summary['classification']=='COMPLETED' and summary['leader_exit_code']==0
        charge=active['completed'] if clean else active['upper']
        for key,value in charge.items():row['charged'][key]+=value
        row['actor_wall_seconds']+=summary['elapsed_seconds']
        lower=active['completed'] if clean else dict.fromkeys(self.CAPS,0)
        if not clean:lower['actions']=active['completed']['actions']
        row['runs'].append(dict(directory=str(directory),source_sha=active['source_sha'],classification=summary['classification'],
            counts=charge,completed=lower,upper=active['upper'],exact_counts=clean,
            actor_wall_seconds=summary['elapsed_seconds'],launch_wall_seconds=launch_wall_seconds,
            rss_peak_bytes=summary['sampled_process_tree_rss_peak_bytes'],swap_peak_bytes=summary['sampled_process_tree_swap_peak_bytes'],
            descendants_cleared=summary['descendants_cleared']))
        row['active']=None;write_json(self.LEDGER_PATH,row);self.journal('one_run_accounted',run=row['runs'][-1])
        return row
