"""Pure-stdlib arithmetic controls for the live in-core workspace budget."""
import copy
import unittest
from src.solvers.bounded_mumps import incore_memory_budget


class IncoreBudgetTests(unittest.TestCase):
    def setUp(self):
        self.info={"16":4388,"26":1234}
        self.obs={"effective_cap_bytes":7803170816,"live_tree_and_supervisor_bytes":1819619328,
                  "margin_bytes":536870912,"system":{"available":7350177792}}
    def budget(self,**kw):
        return incore_memory_budget(kw.get('info',self.info),kw.get('nnz',25977356),
                                   kw.get('obs',self.obs),available_floor_bytes=kw.get('floor',2**30))
    def test_actual_first_A_observations_are_not_a_numeric_result(self):
        r=self.budget(); self.assertTrue(r['passed']);self.assertEqual(r['numeric_ICNTL23_MB'],4538)
        self.assertEqual(r['petsc_conversion_upper_bytes'],623456544)
        self.assertLessEqual(self.obs['live_tree_and_supervisor_bytes']+r['future_numeric_bytes']+2**29,self.obs['effective_cap_bytes'])
    def test_ooc_estimate_does_not_admit_incore(self):
        o=copy.deepcopy(self.obs);o['effective_cap_bytes']-=200_000_000
        r=self.budget(obs=o);self.assertFalse(r['passed']);self.assertGreater(r['numeric_ICNTL23_MB'],1234)
    def test_available_headroom_independently_limits(self):
        o=copy.deepcopy(self.obs);o['system']['available']=5_000_000_000
        self.assertFalse(self.budget(obs=o)['passed'])
    def test_no_rounding_up_into_reserve(self):
        r=self.budget();self.assertLess(r['workspace_budget_bytes']-1_000_000*r['numeric_ICNTL23_MB'],1_000_000)
        self.assertGreaterEqual(r['workspace_budget_bytes']-1_000_000*r['numeric_ICNTL23_MB'],0)
    def test_invalid_counts_and_floors(self):
        for changes in ({'nnz':True},{'nnz':0},{'nnz':1.5},{'floor':0},{'floor':True},{'info':{'16':float('nan'),'26':1}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.budget(**changes)
    def test_missing_margin_not_lent_to_mumps(self):
        o=copy.deepcopy(self.obs);o['margin_bytes']=2**29-1
        with self.assertRaises(ValueError):self.budget(obs=o)
    def test_negative_headroom_records_rejection(self):
        o=copy.deepcopy(self.obs);o['effective_cap_bytes']=100
        r=self.budget(obs=o);self.assertFalse(r['passed']);self.assertLess(r['numeric_ICNTL23_MB'],0)

class CheckpointMuTests(unittest.TestCase):
    def test_real_complex_unit_and_reject_controls(self):
        from src.solvers.volume_tensor_checkpoint import _lossless_unit_mu
        self.assertEqual(_lossless_unit_mu(1+0j),1.0)
        self.assertEqual(_lossless_unit_mu(1.0),1.0)
        for value in (True,1+1e-20j,2+0j,complex(float('nan'),0),complex(1,float('inf')),'1'):
            with self.subTest(value=value),self.assertRaises((TypeError,ValueError)):_lossless_unit_mu(value)


if __name__=='__main__':unittest.main()
