"""Only new case wiring, nonnested integration and sparse/mode guards."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from src.io.phase_notch_hp import descriptor,load_phase_notch_hp
from src.solvers.phase_notch_hp_scope import ROOT,STAGES,case_spec
from src.solvers.phase_notch_hp_capacity import storage_envelope
from src.solvers.phase_notch_hp_fields import common_boxes,common_difference


class HPTests(unittest.TestCase):
    def test_real_axes_degree_and_inventory(self):
        for role,p,cells,rows in (('H',5,320,44532),('P',6,160,33364),('HP',6,320,65044)):
            d,s=descriptor(role)
            self.assertEqual(d['discretization']['degree'],p)
            self.assertEqual(d['geometry']['cells'],cells)
            self.assertEqual(int(np.prod([len(a)-1 for a in d['geometry']['axes_nm'].values()])),cells)
            self.assertEqual(d['discretization']['condensed_rows'],rows)
            self.assertEqual(d['boundary']['complete_modes'],532)
            self.assertEqual(d['geometry']['notch_expected_changed_cells'],2*np.prod(s['splits']))
        with patch('src.solvers.phase_notch_hp_scope.case_spec') as unused:
            self.assertEqual(case_spec('P')['degree'],6)

    def test_all_new_dat_dispatch_validate_and_old_input_unchanged(self):
        specs=[load_phase_notch_hp(p) for p in sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v52_*.dat'))]
        self.assertEqual({s.derived['stage'] for s in specs},set(STAGES))
        for s in specs:
            self.assertEqual(s.derived['preparation_scope'],'v52')
            self.assertEqual(s.execution['terminate_memory_gib'],24)
            self.assertEqual(s.derived['storage_limits']['task_storage_bytes'],46*2**30)
        from src.io.phase_explicit_accuracy import load_phase_explicit_accuracy
        old=load_phase_explicit_accuracy(ROOT/'input/task042_neural_coarse_inverse/v51_notch_p4.dat')
        self.assertEqual(old.solver['degree'],4)
        self.assertEqual(old.derived['preparation_scope'],'v51')

    def test_capacity_new_rows_are_allowed_but_not_unconditional(self):
        args=dict(rows=65044,native=220000,cells=320,dimension=882,interior=450,raw_classes=32,oriented_classes=64,
            graph_nnz=12000000,boundary_support_sum=16000,boundary_cells=32,modes=532)
        r=storage_envelope(**args)
        self.assertTrue(r['admitted']);self.assertGreater(r['rows'],35000)
        self.assertFalse(storage_envelope(**(args|dict(rows=80001)))['admitted'])
        self.assertFalse(storage_envelope(**(args|dict(graph_nnz=1000000000)))['admitted'])
        from src.solvers.phase_explicit_accuracy_capacity import numeric_plan
        self.assertTrue(numeric_plan(3*2**30,{'infog':{'16':1000,'17':900}})['admitted'])
        self.assertFalse(numeric_plan(12*2**30,{'infog':{'16':4000,'17':900}})['admitted'])
        with self.assertRaises(ValueError):numeric_plan(0,{'infog':{'16':0,'17':0}})

    def test_actual828_inventory_and_physical_keys(self):
        from src.solvers.phase_explicit_accuracy import configuration
        from dataclasses import replace
        from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
        cfg=replace(configuration('NOTCH',6),diffraction_order_max_m=11,diffraction_order_max_n=4)
        modes,ids,_=build_dynamic_mode_inventory(cfg)
        keys=[tuple(x[k] for k in ('side','m','n','polarization')) for x in ids]
        self.assertEqual(len(modes),828);self.assertEqual(len(set(keys)),828)
        common=[x for x in keys if abs(x[1])<=9 and abs(x[2])<=3]
        self.assertEqual(len(common),532);self.assertEqual(len(keys)-len(common),296)
        from src.solvers.scattering_accuracy_boundary import carrier_pair
        with self.assertRaises(ValueError):carrier_pair(SimpleNamespace(entries=[]),SimpleNamespace(entries=[]),ids,expected_modes=828)

    def test_non_nested_common_integral_polynomial_counterexample(self):
        def space(axes):
            xyz=[];dof=[]
            for i in range(len(axes[0])-1):
                for j in range(len(axes[1])-1):
                    for k in range(len(axes[2])-1):
                        box=[axes[0][i:i+2],axes[1][j:j+2],axes[2][k:k+2]]
                        v=np.asarray([[x,y,z] for x in box[0] for y in box[1] for z in box[2]])
                        dof.append(np.arange(len(xyz),len(xyz)+8));xyz.extend(v)
            return SimpleNamespace(mesh=SimpleNamespace(geometry=SimpleNamespace(x=np.asarray(xyz),dofmap=np.asarray(dof))))
        a=SimpleNamespace(function_space=space(([0,.5,1],[0,1],[0,1])),offset=0.)
        b=SimpleNamespace(function_space=space(([0,1],[0,.5,1],[0,1])),offset=.01)
        class Eval:
            def __init__(self,space,q,k):
                nodes,w=np.polynomial.legendre.leggauss(4);nodes=(nodes+1)/2;w=w/2
                self.points=np.asarray([[x,y,z] for x in nodes for y in nodes for z in nodes]);self.weights=np.asarray([x*y*z for x in w for y in w for z in w]);self.eval_checks=[]
            def at(self,f,c,points,k0):
                x,y,z=points.T;v=x*x+y*z+f.offset*x*y
                e=np.column_stack((v,2*v,-v));return dict(E=e,H=e,curl=e)
        class Journal:
            def measured(self,name):
                import contextlib
                return contextlib.nullcontext()
        cfg=SimpleNamespace(kx=0,ky=0,k0=1)
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp/task042/v52') as t,patch('src.solvers.phase_notch_hp_fields.PhaseEvaluator',Eval),patch('src.solvers.phase_notch_hp_fields.analytic',lambda c,p:dict.fromkeys(('E','H','curl'),np.zeros((len(p),3)))):
            r=common_difference(a,b,cfg,Journal(),Path(t),q=23,selected_points=np.array([[.25,.25,.25],[.75,.75,.75]]))
            self.assertEqual(r['common_subcells'],4)
            self.assertAlmostEqual(r['fields']['E_total']['difference_L2']**2,6*.01**2/9,places=15)
            self.assertEqual(r['fields']['E_total']['difference_L2'],r['fields']['E_scattered']['difference_L2'])
        first=np.array([[[0,0,0],[.5,1,1]],[[.5,0,0],[1,1,1]]]);second=np.array([[[0,0,0],[1,.5,1]],[[0,.5,0],[1,1,1]]])
        boxes,pa,pb=common_boxes(first,second)
        self.assertEqual(len(boxes),4);self.assertEqual(np.prod(boxes[:,1]-boxes[:,0],axis=1).sum(),1.)

    def test_live_runner_scope_and_reserve(self):
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        w,art,plan,hashes=context('v52')
        self.assertEqual(w.label,'V52');self.assertIn('/v52',str(art))
        self.assertEqual(storage_limits('v52')['new_storage_bytes'],8*2**30)
        self.assertEqual(json.loads(plan.read_text())['assembly_row_cap'],80000)

    def test_physical_mode_pairing_not_auxiliary_index_and_added_inventory(self):
        from src.solvers.phase_notch_hp_modes import compare_payloads,keyed_modes
        def payload(m,n):
            rows=[]
            for side in ('top','bottom'):
                for i in range(-m,m+1):
                    for j in range(-n,n+1):
                        for pol in ('s','p'):
                            value=[.1*(i+20),.1*(j+20)]
                            rows.append(dict(side=side,m=i,n=j,polarization=pol,auxiliary_index=len(rows),power_ratio=.001,
                                auxiliary_amplitude_total_projection=value,outgoing_amplitude=value,outgoing_amplitude_at_boundary=value))
            return dict(reference_planes={'top_z':2.,'bottom_z':-1.},orders=rows)
        a=payload(11,4);b=payload(11,4);b['orders'].reverse()
        for i,row in enumerate(b['orders']):row['auxiliary_index']=i
        r,v=compare_payloads(a,b,828)
        self.assertEqual(r['outgoing_amplitude_at_boundary_relative'],0.)
        self.assertEqual(r['partitions']['added296']['count'],296)
        self.assertGreater(r['partitions']['added296']['reference_norm'],0.)
        self.assertEqual(v['power_first'].shape,(828,))
        b['orders'][0]=b['orders'][1]
        with self.assertRaises(ValueError):keyed_modes(b,828)
        with self.assertRaises(ValueError):keyed_modes(a,532)

    def test_saved_timeline_reader_complete_and_interrupted_lower_bound(self):
        from benchmarks.collect_phase_notch_hp import measured_timeline
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp/task042/v52') as d:
            p=Path(d)/'events.jsonl'
            rows=[dict(event='one_begin',elapsed_s=1.),dict(event='child_begin',elapsed_s=2.),
                dict(event='child_end',elapsed_s=4.),dict(event='one_end',elapsed_s=5.)]
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows));r=measured_timeline(p)
            self.assertTrue(r['complete']);self.assertEqual(sum(r['exclusive_seconds'].values()),4.)
            rows.append(dict(event='lost_begin',elapsed_s=6.))
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows));r=measured_timeline(p)
            self.assertFalse(r['complete']);self.assertEqual(r['unclosed_suffix_seconds'],'unknown')
            self.assertEqual(sum(r['exclusive_seconds'].values()),4.)

    def test_case_wall_does_not_reset_for_a_resume(self):
        from src.solvers.phase_notch_hp_scope import HPWindow
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp/task042/v52') as d:
            rd=Path(d);(rd/'run_summary.json').write_text(json.dumps(dict(launch_wall_seconds=130.)))
            w=HPWindow(rd,label='test',total=18000,component=18000,auxiliary=18000,probe=120,reserve=180,bootstrap=0)
            with patch.object(w,'require_ready'),patch.object(w,'charged_wall',return_value=200.),patch.object(w,'snapshot',return_value=dict(heavy_remaining_seconds=20000.)),patch.object(w,'ledger',return_value=dict(runs=[dict(role='H',folder=str(rd),elapsed_seconds=100.)])):
                self.assertEqual(w.remaining('H'),3470.)

    def test_saved_resource_sampling_uses_all_samples_and_real_gaps(self):
        from benchmarks.collect_phase_notch_hp import sampling_receipt
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp/task042/v52') as d:
            p=Path(d)/'resources.jsonl'
            rows=[dict(elapsed_seconds=t,rss_bytes=r,swap_bytes=s) for t,r,s in
                ((0.,10,0),(0.5,50,2),(3.2,30,0),(3.7,20,0))]
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            r=sampling_receipt(p)
            self.assertEqual(r['sample_count'],4)
            self.assertAlmostEqual(r['actual_max_sample_gap_seconds'],2.7)
            self.assertEqual(r['sampled_tree_peak_bytes'],50)
            self.assertEqual(r['own_swap_peak_bytes'],2)



if __name__=='__main__':unittest.main()
