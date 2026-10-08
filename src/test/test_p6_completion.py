"""New namespace, one cumulative case and unchanged historical readers."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.solvers import p6_completion_scope as scope
from src.io.independent_tetra_reference import load_tetra_reference


class CompletionTests(unittest.TestCase):
    def test_real_entries_and_end_to_end_memory_scope(self):
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        for role in scope.STAGES:
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'case.dat';p.write_text(f'schema_version=1\n[task042_v65]\nstage="{role}"\nrun_id="task042_v65_fixture"\n')
                s=load_tetra_reference(p,scope_module=scope)
            expected=192 if role in scope.P6_ROLES else 64
            self.assertEqual(s.execution['planning_memory_gib'],expected)
            self.assertEqual(s.execution['timeout_seconds'],36000 if role in scope.P6_ROLES else scope.plan_record()['case_wall_seconds'][role])
            self.assertEqual((s.geometry['cells'],s.discretization['degree'],s.discretization['rows']),(7680,6,981180))
            self.assertEqual(s.boundary['complete_modes'],828)
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,reserve_bytes=0,system_reserve_bytes=128*2**30)):
                envelope=preparation_memory_envelope('v65',role)
            self.assertEqual(envelope['planning_cap_bytes'],expected*2**30)
            self.assertEqual(envelope['launch_cap_bytes'],(256 if role in scope.P6_ROLES else 96)*2**30)
        self.assertIs(context('v65')[0],scope.window)
        self.assertEqual(storage_limits('v65')['task_storage_bytes'],344*2**30)

    def test_prepare_solve_resume_share_one_36000_case(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);w=scope.CompletionWindow(p,label='fixture',total=39600,component=39600,auxiliary=39600)
            rows=[]
            for role,seconds in [('PREFLIGHT',300),('PREPARE',12200),('SOLVE_COMPLETE',2500),('SOLVE_COMPLETE',600)]:
                rows.append(dict(role=role,elapsed_seconds=seconds,folder=str(p/role)))
            with patch.object(w,'ledger',return_value=dict(runs=rows,active=None)):
                self.assertEqual(w.case_used(),15300)
                self.assertEqual(w.case_remaining(),20700)
            # Entry-only preflight failures must not consume the P6 group.
            a=p/'PREFLIGHT_one_run01';a.mkdir();(a/'receipt.json').write_text(json.dumps(dict(start_utc='2026-10-08T00:00:00+00:00',end_utc='2026-10-08T00:01:00+00:00',elapsed_seconds=60,source_sha='fixture')))
            with patch.object(w,'ledger',return_value=dict(runs=rows,active=None)):
                self.assertEqual(w.case_used(),15300)

    def test_old16_and192_symbolic_capacity_have_distinct_outcomes(self):
        from src.solvers.phase_explicit_accuracy_capacity import numeric_plan
        info=dict(infog={'16':70000,'17':68000})
        self.assertFalse(numeric_plan(20*2**30,info,16*2**30)['admitted'])
        self.assertTrue(numeric_plan(20*2**30,info,192*2**30)['admitted'])
        self.assertFalse(numeric_plan(100*2**30,info,192*2**30)['admitted'])


if __name__=='__main__':unittest.main()
