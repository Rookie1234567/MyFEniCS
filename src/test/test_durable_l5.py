"""Only new control, parent binding and returned-vector safeguards."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from src.solvers import durable_l5_scope as scope


class DurableL5Tests(unittest.TestCase):
    def test_real_schema_live_budgets_and_explicit_readonly_parent(self):
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        for name,role in [('l5_resume_preflight','PREFLIGHT'),('l5_solve_complete','SOLVE_COMPLETE'),('compare_verify_cost','VERIFY_COST')]:
            s=load_tetra_reference(scope.ROOT/f'input/task042_neural_coarse_inverse/v68_{name}.dat',scope_module=scope)
            expected=[256,320,384] if role=='SOLVE_COMPLETE' else [64,80,96]
            self.assertEqual([s.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],expected)
            self.assertEqual((s.discretization['degree'],s.discretization['FE'],s.discretization['rows']),(5,1943745,1944573))
            self.assertEqual((s.discretization['production_body_q'],s.discretization['oracle_body_q'],s.boundary['complete_modes']),(13,15,828))
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,system_reserve_bytes=128*2**30,reserve_bytes=0)):
                e=preparation_memory_envelope('v68',role)
            self.assertEqual(e['planning_cap_bytes'],expected[0]*2**30);self.assertEqual(e['launch_cap_bytes'],expected[2]*2**30)
        self.assertIs(context('v68')[0],scope.window)
        self.assertEqual(storage_limits('v68')['task_storage_bytes'],512*2**30)
        with patch('src.solvers.local_p_mode_scope.require_stage',side_effect=AssertionError('old closed guard must never run')):
            self.assertEqual(scope.prepared_parent('SOLVE_COMPLETE')['checkpoint']['nnz'],439529923)
        with self.assertRaises(ValueError):scope.prepared_parent('M4')

    def test_same_bytes_qualification_is_bound_to_numerical_closure(self):
        from src.solvers.durable_l5_study import qualification
        r,p=qualification();self.assertEqual(len(r['errors']),2);self.assertTrue(p['sha256'])
        with patch('src.solvers.durable_l5_study.file_digest',return_value='wrong'):
            with self.assertRaisesRegex(ValueError,'qualification hash'):qualification()

    def test_returned_field_and_unknown_interruption_prevent_replay(self):
        with tempfile.TemporaryDirectory() as td,patch.object(scope,'ARTIFACT',Path(td)),patch.object(scope.window,'TMP',Path(td)),\
             patch.object(scope,'stage',return_value={'pass_gate':True}),patch.object(scope,'prepared_parent',return_value={}),\
             patch.object(scope.window,'available_at_boundary',return_value=24000),patch.object(scope,'numeric_attempts',return_value=0):
            scope.require_stage('SOLVE_COMPLETE')
            d=Path(td)/'producer';d.mkdir();(d/'returned_audit_pending.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'saved consumer'):scope.require_stage('SOLVE_COMPLETE')
            (d/'returned_audit_pending.json').unlink()
            with patch.object(scope,'numeric_attempts',return_value=1):
                with self.assertRaisesRegex(RuntimeError,'unknown interruption'):scope.require_stage('SOLVE_COMPLETE')

    def test_stop_event_is_fsynced_before_actual_send(self):
        from src.runners.durable_stop_events import StopEvents
        from benchmarks.subreaper_watchdog import _signal_children
        with tempfile.TemporaryDirectory() as td:
            log=StopEvents(Path(td)/'events.jsonl',{'seconds':12})
            fields=Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()
            def observe(pid,signum):
                rows=[json.loads(l) for l in log.path.read_text().splitlines()]
                self.assertEqual(rows[-1]['event'],'before_send');self.assertEqual(rows[-1]['target']['pid'],pid)
                self.assertEqual(rows[-1]['target']['start_ticks'],int(fields[19]))
            with patch('benchmarks.subreaper_watchdog._children',return_value={os.getpid():(os.getppid(),int(fields[19]))}),\
                 patch('benchmarks.subreaper_watchdog.os.kill',side_effect=observe):
                _signal_children(signal.SIGTERM,stop_events=log,reason='fixture')


class DurableProcessControls(unittest.TestCase):
    def test_short_poll_keeps_same_job_and_explicit_stop_clears_tree(self):
        started=time.monotonic()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            def start(name,worker):
                folder=root/name
                command=[sys.executable,'-m','benchmarks.subreaper_watchdog','--directory',str(folder),
                    '--wall-seconds','40','--interval','0.1','--durable-stop-events','--',sys.executable,'-c',worker]
                return folder,subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            folder,p=start('normal','import time; time.sleep(3); print("normal-return",flush=True)')
            try:
                with self.assertRaises(subprocess.TimeoutExpired):p.wait(timeout=.05)
                self.assertIsNone(p.poll())
                out,err=p.communicate(timeout=35)
                self.assertEqual(p.returncode,0,(out,err))
                summary=json.loads((folder/'summary.json').read_text())
                self.assertEqual(summary['classification'],'COMPLETED');self.assertTrue(summary['descendants_cleared'])
                stopped,p=start('explicit_stop','import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); time.sleep(60)')
                until=time.monotonic()+10
                while not (stopped/'resources.jsonl').exists() or not (stopped/'resources.jsonl').stat().st_size:
                    if p.poll() is not None or time.monotonic()>until:raise RuntimeError('fixture did not start')
                    time.sleep(.05)
                # The sender is known here because the fixture owns this call;
                # reception by the controller alone must still say unknown.
                p.send_signal(signal.SIGTERM);out,err=p.communicate(timeout=35)
                summary=json.loads((stopped/'summary.json').read_text())
                rows=[json.loads(l) for l in (stopped/'stop_events.jsonl').read_text().splitlines()]
                self.assertEqual(summary['classification'],'SIGNAL_STOP_SENDER_UNKNOWN',(out,err))
                self.assertTrue(summary['descendants_cleared'])
                receive=next(i for i,r in enumerate(rows) if r['event']=='received_signal')
                send=next(i for i,r in enumerate(rows) if r['event']=='before_send')
                self.assertLess(receive,send);self.assertEqual(rows[receive]['original_sender'],'unknown')
            finally:
                if p.poll() is None:p.kill();p.communicate()
        self.assertLess(time.monotonic()-started,90)


if __name__=='__main__':unittest.main()
