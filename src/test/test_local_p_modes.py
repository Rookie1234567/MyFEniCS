"""Independent producers, actual p5 quadrature and role-specific live budgets."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from src.solvers import local_p_mode_scope as scope
from src.io.independent_tetra_reference import load_tetra_reference


class LocalModeTests(unittest.TestCase):
    def test_dat_to_scope_to_live_budget_has_three_distinct_profiles(self):
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        for role in scope.STAGES:
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'one.dat';p.write_text(f'schema_version=1\n[task042_v67]\nstage="{role}"\nrun_id="task042_v67_fixture"\n')
                s=load_tetra_reference(p,scope_module=scope)
            modes=1188 if role=='M4' else 828;degree=4 if role=='M4' else 5
            profile=[192,224,256] if role=='M4' else [256,320,384] if role in scope.GROUPS['L5'] else [64,80,96]
            self.assertEqual([s.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],profile)
            self.assertEqual((s.boundary['complete_modes'],s.solver['degree'],s.geometry['cells']),(modes,degree,25576))
            self.assertEqual((s.discretization['production_body_q'],s.discretization['oracle_body_q']),(2*degree+3,2*degree+5))
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,system_reserve_bytes=128*2**30,reserve_bytes=0)):
                e=preparation_memory_envelope('v67',role)
            self.assertEqual(e['planning_cap_bytes'],profile[0]*2**30);self.assertEqual(e['launch_cap_bytes'],profile[2]*2**30)
        self.assertIs(context('v67')[0],scope.window)
        self.assertEqual(storage_limits('v67')['task_storage_bytes'],480*2**30)

    def test_M4_uses_old_p4_parent_even_if_new_L5_prepare_is_missing(self):
        with patch('src.solvers.frozen_local_h_scope.stage',return_value={'checkpoint':'old-p4'}) as prior,patch.object(scope,'stage',side_effect=FileNotFoundError('new p5 absent')):
            self.assertEqual(scope.prepared_parent('M4')['checkpoint'],'old-p4');prior.assert_called_once_with('PREPARE')
            with self.assertRaises(FileNotFoundError):scope.prepared_parent('SOLVE_COMPLETE')

    def test_M4_does_not_consume_old_space_gate_or_L5_status(self):
        with tempfile.TemporaryDirectory() as td,patch.object(scope.window,'TMP',Path(td)),patch.object(scope,'ARTIFACT',Path(td)),\
            patch.object(scope.window,'available_at_boundary',return_value=20000),patch.object(scope,'numeric_attempts',return_value=0),\
            patch.object(scope,'prepared_parent',return_value={'checkpoint':'healthy-p4'}),patch.object(scope,'stage',return_value={'pass_gate':True}) as calls:
            scope.require_stage('M4');calls.assert_called_once_with('PREFLIGHT')
            (Path(td)/'scientific_queue_frozen.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'final queue'):scope.require_stage('M4')

    def test_actual_study_passes_spec_q15_and_explicit_provider_to_solver(self):
        from src.solvers.local_p_mode_study import execute
        journal=SimpleNamespace(source_state=None)
        with patch('src.solvers.local_p_mode_study.Journal',return_value=journal),patch('src.solvers.independent_tetra_study.solve') as solve,\
            patch('src.solvers.local_p_mode_study.CoefficientFullAction',return_value='independent') as action:
            execute('SOLVE_COMPLETE',Path('/tmp/fixture'),dict(memory_budget=scope.memory_budget('SOLVE_COMPLETE'),stage='V67-SOLVE_COMPLETE'))
            kw=solve.call_args.kwargs;self.assertIs(kw['scope_module'],scope)
            kw['action_factory']({'spec':{'degree':5}},'q63');self.assertEqual(action.call_args.args[2],15)
            kw['action_factory']({'spec':{'degree':4}},'q63');self.assertEqual(action.call_args.args[2],13)

    def test_checkpoint_mode_change_still_rejects_wrong_degree(self):
        from src.solvers.tetra_body_checkpoint import body_fingerprint
        a=dict(physical=scope.physical_for('M4'),degree=4,local_dim=84,body_q=11,arrays={'actual':'p4'},kappa=[1,2,0])
        b=copy.deepcopy(a);b['physical']['boundary']['complete_modes']=828
        self.assertEqual(body_fingerprint(a),body_fingerprint(b))
        b['degree']=5;b['local_dim']=140;b['body_q']=13
        self.assertNotEqual(body_fingerprint(a),body_fingerprint(b))

    def test_cumulative_case_costs_do_not_refresh_on_resume(self):
        with tempfile.TemporaryDirectory() as td:
            w=scope.LocalModeWindow(Path(td),label='fixture',total=39600)
            rows=[dict(role=r,folder=str(Path(td)/r),elapsed_seconds=t) for r,t in [('PREPARE',9000),('SOLVE_COMPLETE',3000),('SOLVE_COMPLETE',500),('M4',1000)]]
            with patch.object(w,'ledger',return_value=dict(runs=rows,active=None)):
                self.assertEqual(w.case_remaining('L5'),23500);self.assertEqual(w.case_remaining('M4'),9800)

    def test_symbolic_is_not_a_time_or_memory_admission_ticket(self):
        from src.solvers.phase_explicit_accuracy_capacity import numeric_plan
        info=dict(infog={'16':100000,'17':100000})
        self.assertTrue(numeric_plan(30*2**30,info,256*2**30)['admitted'])
        self.assertFalse(numeric_plan(30*2**30,info,192*2**30)['admitted'])
        j=SimpleNamespace(event=lambda *a,**kw:None)
        with patch.object(scope.window,'snapshot',return_value={'heavy_remaining_seconds':20000}),patch.object(scope.window,'charged_wall',return_value=0),patch.object(scope.window,'case_remaining',return_value=11699):
            with self.assertRaisesRegex(RuntimeError,'output reserve'):scope.numeric_guard('SOLVE_COMPLETE',j)

    def test_auxiliary_rejection_and_returned_tail_are_paid_without_probe_recount(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);runs=[]
            for tag,start,elapsed,probe in [('01',0,43.,1.),('02',60,51.,2.),('03',120,.3,0.)]:
                outer=folder/('auxiliary_pre'+tag);outer.mkdir()
                stamp=lambda n:f'2026-10-09T09:{n//60:02d}:{n%60:02d}+00:00'
                receipt=dict(source_sha='source',start_utc=stamp(start),end_utc=stamp(start+int(elapsed)+1),elapsed_seconds=elapsed)
                (outer/'receipt.json').write_text(json.dumps(receipt))
                if probe:
                    own=folder/('aux_pre_'+tag);own.mkdir()
                    (own/'admission.json').write_text(json.dumps(dict(utc=stamp(start+1))))
                    (folder/('probe_'+tag+'.json')).write_text(json.dumps(dict(receipt_path=str(own/'admission.json'),elapsed_seconds=probe)))
                if tag=='02':
                    (own/'summary.json').write_text(json.dumps(dict(launch_wall_seconds=50.)))
                    runs.append(dict(source_sha='source',before_clock=dict(observed_utc=stamp(start+3)),folder=str(own),elapsed_seconds=47.))
            self.assertAlmostEqual(scope.auxiliary_wrapper_overhead(folder,runs),43.3)

    def test_external_interruption_preserves_unknown_cause_and_charges_upper(self):
        from src.runners.preparation_interruption import interrupted_summary
        active=dict(source_sha='old-source',before_clock=dict(boot_id='boot',observed_monotonic=10.,observed_utc='2026-10-09T00:00:00+00:00'))
        samples=[dict(elapsed_seconds=t,members=[dict(pid=7)],rss_bytes=b,swap_bytes=0) for t,b in [(4.,8),(5.,9)]]
        observation=dict(boot_id='boot',monotonic=17.,utc='2026-10-09T00:00:07+00:00',live_matching_actors=[],absent_recorded_pids={7:True})
        r=interrupted_summary(active,samples,observation,outer_exit_code=143)
        self.assertEqual((r['elapsed_lower_seconds'],r['elapsed_seconds'],r['unobserved_tail_seconds']),(5.,7.,2.))
        self.assertIsNone(r['leader_exit_code']);self.assertFalse(r['replay_authorized'])
        self.assertEqual(r['source_sha'],'old-source')
        for bad in (dict(observation,live_matching_actors=[7]),dict(observation,absent_recorded_pids={}),dict(observation,boot_id='other')):
            with self.assertRaises(ValueError):interrupted_summary(active,samples,bad,outer_exit_code=143)


if __name__=='__main__':unittest.main()
