"""The returned-state entry must consume bytes, never re-enter solve_h2."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from benchmarks.consume_saved_subcell import existing_receipt,tangent_reductions,ambient_reductions


class SavedConsumer(unittest.TestCase):
    def test_actual_stage_dispatch_before_pde(self):
        from src.solvers.local_subcell_study import execute,scope
        state=dict(memory_budget=scope.plan_record()['memory_budget'],postprocessing_resume={'path':'saved'})
        with tempfile.TemporaryDirectory() as d,patch('benchmarks.consume_saved_subcell.consume',return_value={'consumer_only':True}) as f,patch('src.solvers.subcell_macro_deployment.solve_h2',side_effect=AssertionError('no fourth factor')):
            self.assertTrue(execute('H2',Path(d),state)['consumer_only'])
            f.assert_called_once();self.assertIs(f.call_args.args[-1],state)

    def test_actual_saved_metrics_and_inventory_failures(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'raw.npz';pairs=np.zeros((3,6),int);pairs[:,-1]=[0,1,2]
            metrics=np.array([[1e-14,2.,2.,0.,5e-15]]*3)
            np.savez(p,metrics=metrics,face_pairs=pairs)
            r=existing_receipt(p);self.assertTrue(tangent_reductions(r)['pass_gate'])
            original=p.read_bytes();self.assertEqual(existing_receipt(p),r);self.assertEqual(p.read_bytes(),original)
            pairs[2,-1]=1;np.savez(p,metrics=metrics,face_pairs=pairs)
            with self.assertRaisesRegex(ValueError,'face kinds'):tangent_reductions(existing_receipt(p))
            metrics[0,4]=1.;np.savez(p,metrics=metrics,face_pairs=pairs)
            with self.assertRaisesRegex(ValueError,'denominator identity'):tangent_reductions(existing_receipt(p))
            np.savez(p,bad=np.array([np.nan]))
            with self.assertRaisesRegex(ValueError,'nonfinite'):existing_receipt(p)

    def test_ambient_defect_does_not_claim_full_solution(self):
        v=dict(rhs=np.array([1.+2j,3.-1j]),volume_inside=np.array([1j,2]),volume_trace=np.array([1j,1.-1j]),
            volume_action=np.array([2j,3.-1j]),residual=np.array([1.+0j,0j]),augmented_top=np.array([1.+0j,0j]),
            native_boundary_action=np.zeros(2,complex),coupling_action=np.zeros(2,complex),port_residual=np.zeros(40,complex),projected=np.ones(40,complex),
            internal_numerators=np.array([1e-15]),internal_operation_scale=np.array([1.]),u_storage=np.zeros(2,complex),slaves=np.array([1]))
        norms,rec=ambient_reductions(v)
        self.assertGreater(norms['true'],1e-3);self.assertEqual(norms['identity'],0.)
        self.assertLess(rec['internal_operation_scaled_max'],1e-10)


if __name__=='__main__':unittest.main()
