"""Focused actual V49 schema/finite authority tests, no historical actor."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.io.scattering_anchor import load_scattering_anchor
from src.solvers.scattering_anchor import configuration, small_condensation_witness, save_arrays
from src.solvers.scattering_anchor_scope import ROOT, STAGES, plan_record


class AnchorTests(unittest.TestCase):
    def test_actual_eight_entrypoint_inventory(self):
        entries=list((ROOT/'input/task042_neural_coarse_inverse').glob('v49_*.dat'))
        self.assertEqual(len(entries),8)
        specs=[load_scattering_anchor(p) for p in entries]
        self.assertEqual({s.derived['stage'] for s in specs},set(STAGES))
        self.assertEqual(len({s.physical_model_sha256 for s in specs}),1)
        self.assertEqual({s.execution['terminate_memory_gib'] for s in specs},{16})

    def test_unknown_or_multiple_stage_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'bad.dat'
            path.write_text('schema_version=1\n[task042_v49]\nstage="OLD_WINDOW"\nrun_id="task042_v49_test"')
            with self.assertRaises(ValueError):load_scattering_anchor(path)

    def test_material_physics_axes_frozen(self):
        c=configuration('NOTCH')
        self.assertEqual(c.n_grating,complex(.999885140474,4.32477054e-6))
        self.assertEqual(c.substrate_index,c.n_grating)
        self.assertEqual(c.nedelec_degree,4)
        self.assertEqual(c.incident_theta_deg,89)
        self.assertEqual(c.incident_phi_deg,5)
        self.assertEqual((c.diffraction_order_max_m,c.diffraction_order_max_n),(9,3))
        self.assertEqual(plan_record()['physical_descriptor']['geometry']['notch_expected_changed_cells'],2)

    def test_complex_nonmutual40port_affine_chain(self):
        self.assertLess(small_condensation_witness()['relative'],1e-12)

    def test_save_arrays_failure_retains_completed_vector(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'packet.npz';save_arrays(path,z=np.arange(12,dtype=np.complex128))
            before=path.read_bytes()
            with patch('numpy.savez',side_effect=RuntimeError('intentional serialisation interruption')):
                with self.assertRaises(RuntimeError):save_arrays(path,z=np.ones(12,complex))
            self.assertEqual(path.read_bytes(),before)
            self.assertTrue(np.array_equal(np.load(path)['z'],np.arange(12)))


if __name__=='__main__':unittest.main()
