"""Focused actual V49 schema/finite authority tests, no historical actor."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_two_cell_full_dual_and_primal_are_paired(self):
        from src.solvers.scattering_y_orbit_reuse import TwoCellNativeTransport
        def entity(ny):
            return SimpleNamespace(ny=ny,width=3968,independent=np.arange(ny*3968),
                full_rows=17204 if ny==4 else 8940,bases=(),slots={},dimension_counts={3:8640 if ny==4 else 4320},
                y_widths=np.ones(ny),transform=lambda x,**kw:np.asarray(x))
        full,local=entity(4),entity(2);ky=.3;ly=4
        rng=np.random.default_rng(49);r=rng.normal(size=15872)+1j*rng.normal(size=15872)
        reconstruction=np.zeros_like(r)
        for b in (0,1):
            eta=np.exp(1j*(ky*ly+2*np.pi*b)/4)
            tr=TwoCellNativeTransport(full,local,twist_index=b,eta=eta,global_phase=np.exp(1j*ky*ly),global_ky=ky,global_period_y=ly)
            x=r[:7936];lift=tr.lift_primal(x);fold=tr.fold_dual(r)
            self.assertLess(abs(np.vdot(r,lift)-np.vdot(fold,x))/np.linalg.norm(r)**2,1e-13)
            reconstruction+=tr.lift_primal(tr.extract_primal(r))
        self.assertLess(np.linalg.norm(reconstruction-r)/np.linalg.norm(r),1e-13)

    def test_modal_factor_nonzero_auxiliary_rhs(self):
        from scipy import sparse
        from scipy.sparse.linalg import splu
        from src.solvers.scattering_anchor_two_cell import ModalFactor
        rng=np.random.default_rng(4904);a=rng.normal(size=(8,8))+1j*rng.normal(size=(8,8))+10*np.eye(8)
        a[:4,4:]=0;a[4:,:4]=0
        maps=[sparse.csr_matrix(np.eye(8)[:,i:i+4]) for i in (0,4)]
        factors=[splu(sparse.csc_matrix(a[i:i+4,i:i+4])) for i in (0,4)]
        j=SimpleNamespace(calls={'factor':0});f=ModalFactor(maps,factors,j,4)
        b=rng.normal(size=8)+1j*rng.normal(size=8);g=rng.normal(size=4)+1j*rng.normal(size=4)
        f.port_rhs[:]=g;x=SimpleNamespace(array=np.zeros(8,complex));f.solve_repeated(SimpleNamespace(array=b),x)
        rhs=b.copy();rhs[4:]+=g
        self.assertLess(np.linalg.norm(a@x.array-rhs)/np.linalg.norm(rhs),1e-13)
        self.assertEqual(j.calls['factor'],2)
        self.assertGreater(np.linalg.norm(a@x.array-b),.1)

    def test_explicit_local_wrap_keeps_physical_wavevector(self):
        from dataclasses import replace
        from src.solvers.scattering_anchor_two_cell import PhaseConfiguration
        c=configuration('REGULAR');local=replace(c,period_y=c.period_y/2,grating_width_y=c.period_y/2)
        eta=np.exp(1j*(c.ky.real*c.period_y+2*np.pi)/4);p=PhaseConfiguration(local,eta**2)
        self.assertEqual(p.ky,c.ky);self.assertEqual(p.floquet_phase_y,eta**2)
        self.assertGreater(abs(p.floquet_phase_y-local.floquet_phase_y),.1)

    def test_save_arrays_failure_retains_completed_vector(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'packet.npz';save_arrays(path,z=np.arange(12,dtype=np.complex128))
            before=path.read_bytes()
            with patch('numpy.savez',side_effect=RuntimeError('intentional serialisation interruption')):
                with self.assertRaises(RuntimeError):save_arrays(path,z=np.ones(12,complex))
            self.assertEqual(path.read_bytes(),before)
            self.assertTrue(np.array_equal(np.load(path)['z'],np.arange(12)))


if __name__=='__main__':unittest.main()
