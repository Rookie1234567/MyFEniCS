"""Focused actual V49 schema/finite authority tests, no historical actor."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.io.scattering_anchor import load_scattering_anchor
from src.solvers.scattering_anchor import configuration, small_condensation_witness, save_arrays, relative
from src.solvers.scattering_anchor_scope import ROOT, STAGES, plan_record


class AnchorTests(unittest.TestCase):
    def test_actual_eight_entrypoint_inventory(self):
        entries=list((ROOT/'input/task042_neural_coarse_inverse').glob('v49_*.dat'))
        self.assertEqual(len(entries),8)
        specs=[load_scattering_anchor(p) for p in entries]
        self.assertEqual({s.derived['stage'] for s in specs},set(STAGES))
        bystage={s.derived['stage']:s for s in specs}
        self.assertEqual(bystage['REFERENCE_REGULAR'].physical_model_sha256,bystage['ENGINE_REGULAR'].physical_model_sha256)
        self.assertEqual(bystage['REFERENCE_NOTCH'].physical_model_sha256,bystage['ENGINE_NOTCH'].physical_model_sha256)
        self.assertNotEqual(bystage['REFERENCE_NOTCH'].physical_model_sha256,bystage['REFERENCE_NOTCH_P5'].physical_model_sha256)
        self.assertEqual(bystage['REFERENCE_NOTCH_P5'].discretization['degree'],5)
        self.assertEqual(bystage['REFERENCE_NOTCH_P5'].discretization['expected_trace'],11600)
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

    def test_actual_qualification_returns_and_persists_all_port_metadata(self):
        # Call the real qualification workflow with a separate explicit
        # non-Hermitian augmented operator, including tiny evanescent units.
        from src.solvers.scattering_anchor_two_cell import TwoCellInverse
        nt,np_=15872,532
        h=np.geomspace(1e-194,2.,np_);sh=np.sqrt(h)
        class Vec:
            def createSeq(self,n,comm=None):self.array=np.zeros(n,complex);return self
            def set(self,v):self.array[:]=v
            def destroy(self):pass
        class Action:
            def __init__(self,*args):self.calls=0
            def apply(self,x):
                self.calls+=1;y=x.copy();y[:np_]*=2;return y
            def close(self):pass
        entries=[SimpleNamespace(coupling_rows=np.array([i]),coupling_values=np.array([sh[i]]),
                   projection_rows=np.array([i]),projection_values=np.array([sh[i]]),normalization_h=h[i]) for i in range(np_)]
        pc=TwoCellInverse.__new__(TwoCellInverse)
        pc.original={'physical_action':None,'volume_action':SimpleNamespace(apply=lambda v:SimpleNamespace(array=v.array.copy())),
                     'dtn_action':SimpleNamespace(carrier=SimpleNamespace(entries=entries))}
        pc.layout=SimpleNamespace(full_rows=nt,independent=np.arange(nt));pc.checks=[]
        pc.journal=SimpleNamespace(calls={'A':0},event=lambda *args,**kw:None)
        def augmented(f,g):
            u=f.copy();u[:np_]=(f[:np_]-g/sh)/2
            return u,(g+sh*u[:np_])/h
        pc.apply_augmented=augmented;pc.apply_array=lambda f:augmented(f,np.zeros(np_,complex))[0]
        with tempfile.TemporaryDirectory() as t, patch.dict('sys.modules',{'petsc4py':SimpleNamespace(PETSc=SimpleNamespace(Vec=Vec,COMM_SELF=None))}), patch('src.solvers.scattering_anchor_two_cell.FullOriginalAction',Action):
            result=pc.qualify(Path(t))
            self.assertLess(max(result['norms'].values()),1e-12)
            self.assertEqual(result['arrays']['members']['port_H']['shape'],[532])
            self.assertEqual(set(np.load(result['arrays']['path']).files),set(result['arrays']['members']))

    def test_explicit_local_wrap_keeps_physical_wavevector(self):
        from dataclasses import replace
        from src.solvers.scattering_anchor_two_cell import PhaseConfiguration
        c=configuration('REGULAR');local=replace(c,period_y=c.period_y/2,grating_width_y=c.period_y/2)
        eta=np.exp(1j*(c.ky.real*c.period_y+2*np.pi)/4);p=PhaseConfiguration(local,eta**2)
        self.assertEqual(p.ky,c.ky);self.assertEqual(p.floquet_phase_y,eta**2)
        self.assertGreater(abs(p.floquet_phase_y-local.floquet_phase_y),.1)

    def test_large_finite_complex_norm_preserves_denominator(self):
        reference=np.array([1e190+2e190j,-3e190+1e190j])
        self.assertAlmostEqual(relative(.25*reference,reference),.25)
        self.assertEqual(relative(np.zeros(2),reference),0)

    def test_independent_frozen_member_checker_rejects_inventory_and_hash(self):
        from src.solvers.scattering_anchor_checks import checked_arrays
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'state.npz';a=np.array([1+2j,3-1j]);record=save_arrays(p,z=a)
            np.testing.assert_array_equal(checked_arrays(record)['z'],a)
            bad={**record,'members':{}}
            with self.assertRaisesRegex(ValueError,'inventory'):checked_arrays(bad)
            bad={**record,'members':{'z':{**record['members']['z'],'sha256':'0'*64}}}
            with self.assertRaisesRegex(ValueError,'member identity'):checked_arrays(bad)

    def test_numeric_writer_normalizes_small_lists_but_rejects_objects(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'state.npz';record=save_arrays(path,H=[1.,2.])
            self.assertEqual(record['members']['H']['shape'],[2])
            with self.assertRaisesRegex(TypeError,'Python objects'):save_arrays(path,data=[{'bad':1}])

    def test_actual_owner_snapshot_call_preserves_unique_backing_and_event(self):
        from src.solvers.scattering_anchor import Journal
        with tempfile.TemporaryDirectory() as t:
            journal=Journal(Path(t));events=[]
            journal.event=lambda name,**facts:events.append((name,facts))
            a=np.ones(32,complex);journal.owners('bounded',[a,a[2:],{'same':a}])
            self.assertEqual(events[0][0],'object_owner_snapshot')
            self.assertEqual(events[0][1]['owner_role'],'bounded')
            self.assertEqual(events[0][1]['unique_visible_numpy_owner_bytes'],a.nbytes)
            self.assertEqual(events[0][1]['unique_owner_count'],1)

    def test_save_arrays_failure_retains_completed_vector(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'packet.npz';save_arrays(path,z=np.arange(12,dtype=np.complex128))
            before=path.read_bytes()
            with patch('numpy.savez',side_effect=RuntimeError('intentional serialisation interruption')):
                with self.assertRaises(RuntimeError):save_arrays(path,z=np.ones(12,complex))
            self.assertEqual(path.read_bytes(),before)
            self.assertTrue(np.array_equal(np.load(path)['z'],np.arange(12)))


if __name__=='__main__':unittest.main()
