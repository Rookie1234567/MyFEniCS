"""Only V55 parent inventory, tangential meaning and explicit capacity wiring."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from src.solvers import phase_spatial_resolution_scope as scope
from src.solvers.phase_tangential_audit import tangential_metrics
from src.solvers.phase_explicit_accuracy_capacity import numeric_plan
from src.io.phase_notch_hp import descriptor,load_phase_notch_hp


class SpatialTests(unittest.TestCase):
    def test_tangential_not_normal_or_discrete_H(self):
        a=np.array([[1+2j,3-1j,5j],[2j,-4+3j,2.]])
        b=a.copy();b[:,0]+=100
        self.assertEqual(tangential_metrics(a,b,0)['relative'],0.)
        b[:,1]+=.1j
        self.assertGreater(tangential_metrics(a,b,0)['relative'],1e-10)
        small=np.zeros((64,3),complex);d=small.copy();d[:,1]=1e-15j
        m=tangential_metrics(small,d,0)
        self.assertTrue(m['near_zero']);self.assertEqual(m['denominator'],8.)
        self.assertLess(m['relative'],1e-10)

    def test_physical_carrier_removed_once_not_twice(self):
        k=np.array([3.,2.,0.]);pts=np.array([[0.,.3,.7],[0.,.6,.1]])
        peer=pts+[2.,0.,0.];u=np.array([[1+2j,2-3j,1j],[2.,1j,4.]])
        a=u*np.exp(1j*(pts@k))[:,None];b=u*np.exp(1j*(peer@k))[:,None]
        self.assertLess(tangential_metrics(a*np.exp(-1j*(pts@k))[:,None],b*np.exp(-1j*(peer@k))[:,None],0)['relative'],1e-14)
        self.assertGreater(tangential_metrics(a,b,0)['relative'],1e-10)

    def test_actual_resources_and_degree_rows(self):
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        self.assertEqual(context('v55')[0].label,'V55');self.assertEqual(storage_limits('v55')['task_storage_bytes'],84*2**30)
        with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2*1024*2**30,effective_total_bytes=2*1024*2**30,system_reserve_bytes=205*2**30,reserve_bytes=(205+128)*2**30)):
            r=preparation_memory_envelope('v55');self.assertEqual(r['launch_cap_bytes'],96*2**30);self.assertEqual(r['planning_cap_bytes'],64*2**30)
            self.assertEqual(preparation_memory_envelope('v54')['launch_cap_bytes'],48*2**30)
        old=json.loads((scope.ROOT/scope.plan_record()['old_hp_symbolic_record']).read_text())
        for gib,result in ((16,False),(32,True),(64,True)):
            self.assertEqual(numeric_plan(old['tree']['rss_bytes'],old['info'],gib*2**30)['admitted'],result)
        self.assertFalse(numeric_plan(64*2**30,old['info'],64*2**30)['admitted'])
        p,s=descriptor('H7',scope=scope);self.assertEqual((s['degree'],s['cells'],s['rows']),(7,320,89756))
        self.assertEqual(np.prod([len(a)-1 for a in p['geometry']['axes_nm'].values()]),320)
        for f in (scope.ROOT/'input/task042_neural_coarse_inverse').glob('v55_*.dat'):
            v=load_phase_notch_hp(f,scope=scope)
            self.assertEqual([v.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],[64,80,96])
        self.assertEqual(load_phase_notch_hp(scope.ROOT/'input/task042_neural_coarse_inverse/v54_notch_z2_p7_m828.dat',scope=__import__('src.solvers.phase_p_order_dtn_scope',fromlist=['scope'])).execution['planning_memory_gib'],32)

    def test_assembly_cap_optin_not_default(self):
        from src.solvers.phase_notch_hp_capacity import storage_envelope
        args=dict(rows=89756,native=1,cells=1,dimension=1,interior=0,raw_classes=1,oriented_classes=1,graph_nnz=1,boundary_support_sum=1,boundary_cells=1,modes=828,planning_limit_bytes=64*2**30)
        self.assertFalse(storage_envelope(**args)['admitted'])
        self.assertTrue(storage_envelope(**args,row_cap=100000)['admitted'])
        self.assertFalse(storage_envelope(**(args|dict(rows=100001)),row_cap=100000)['admitted'])

    def test_prior_audit_inventory_does_not_freeze_live_queue(self):
        from src.solvers.phase_notch_hp import verify_cost
        from src.runners.task042_shared import write_json
        with tempfile.TemporaryDirectory(dir=scope.window.TMP) as d:
            folder=Path(d);inventory=folder/'prior_audit_inventory.json';write_json(inventory,dict(completed_solves={}))
            fake=SimpleNamespace(window=SimpleNamespace(TMP=folder),stage=lambda r:None,cached_comparisons=lambda:[])
            journal=SimpleNamespace(source_state=dict(verification_inventory=dict(sha256=hashlib.sha256(inventory.read_bytes()).hexdigest())),timings={},calls={})
            r=verify_cost(folder,journal,scope=fake,inventory_path=inventory,read_state=lambda r:None,output_role='Q0')
            self.assertEqual(r['role'],'Q0');self.assertEqual(r['new_factor_count'],0)
            self.assertFalse((folder/'scientific_queue_frozen.json').exists())
            journal.source_state['verification_inventory']['sha256']='wrong'
            with self.assertRaisesRegex(ValueError,'frozen queue binding'):verify_cost(folder,journal,scope=fake,inventory_path=inventory)


if __name__=='__main__':unittest.main()
