"""Only new phase/constraint/port algebra and opt-in wiring regressions."""
import unittest
from types import SimpleNamespace
import numpy as np
from src.solvers.fixed_phase_fem import carrier,envelope_configuration,port_coordinate_scales
from src.solvers.phase_explicit_accuracy_scope import ROOT,STAGES,plan_record
from src.solvers.phase_explicit_accuracy import configuration
from src.io.phase_explicit_accuracy import load_phase_explicit_accuracy


class PhaseTests(unittest.TestCase):
    def test_carrier_and_physical_incidence_are_not_changed(self):
        c=configuration('FLAT',4);k=carrier(c);e=envelope_configuration(c,k)
        self.assertEqual(e.kx,c.kx);self.assertEqual(e.ky,c.ky)
        self.assertAlmostEqual(e.floquet_phase_x,1);self.assertAlmostEqual(e.floquet_phase_y,1)
        self.assertEqual(c.n_substrate,.999885140474+4.32477054e-6j)
        self.assertEqual(c.lambda0,.7)
        np.testing.assert_equal(carrier(c,False),np.zeros(3))
        with self.assertRaises(ValueError):carrier(SimpleNamespace(kx=1+1j,ky=2))

    def test_complete_transformed_curl_trial_and_test(self):
        rng=np.random.default_rng(51);k=np.array([2.,.1,0]);x=rng.normal(size=3)
        u=rng.normal(size=3)+1j*rng.normal(size=3);v=rng.normal(size=3)+1j*rng.normal(size=3)
        cu=rng.normal(size=3)+1j*rng.normal(size=3);cv=rng.normal(size=3)+1j*rng.normal(size=3)
        g=np.exp(1j*k@x);C=lambda u,c:c+1j*np.cross(k,u)
        a=np.vdot(g*C(v,cv),g*C(u,cu));b=np.vdot(C(v,cv),C(u,cu))
        self.assertLess(abs(a-b),1e-12)
        self.assertGreater(abs(a-np.vdot(cv,C(u,cu))),.1)

    def test_nonHermitian_nonmutual_nonzero_affine_internal_port(self):
        from src.solvers.scattering_anchor import small_condensation_witness
        self.assertLess(small_condensation_witness()['relative'],1e-12)

    def test_exact_port_coordinates_do_not_change_solution(self):
        rng=np.random.default_rng(51);nt=3;nm=40;A=rng.normal(size=(43,43))+1j*rng.normal(size=(43,43))+60*np.eye(43)
        b=rng.normal(size=43)+1j*rng.normal(size=43);H=np.exp(np.linspace(-3,3,nm));phase=np.exp(np.linspace(-2,2,nm)+.3j)
        left,right=port_coordinate_scales(nt,H,phase)
        z=right*np.linalg.solve(left[:,None]*A*right[None,:],left*b)
        self.assertLess(np.linalg.norm(A@z-b)/np.linalg.norm(b),1e-12)
        with self.assertRaises(ValueError):port_coordinate_scales(nt,H,phase*0)

    def test_real_ufl_has_new_identity_and_zero_carrier_degeneracy(self):
        import ufl
        from basix.ufl import element
        from src.solvers.common_3d_forms import _build_physical_volume_terms
        c=configuration('FLAT',4);domain=ufl.Mesh(element('Lagrange','hexahedron',1,shape=(3,)))
        V=ufl.FunctionSpace(domain,element('N1curl','hexahedron',4));u=ufl.TrialFunction(V);v=ufl.TestFunction(V);dx=ufl.Measure('dx',domain=domain)
        ordinary=sum(_build_physical_volume_terms(c,u,v,dx));zero=sum(_build_physical_volume_terms(c,u,v,dx,phase_carrier=np.zeros(3)))
        phase=sum(_build_physical_volume_terms(c,u,v,dx,phase_carrier=carrier(c)))
        from ufl.algorithms import expand_derivatives
        self.assertEqual(expand_derivatives(ordinary).signature(),expand_derivatives(zero).signature())
        self.assertNotEqual(ordinary.signature(),phase.signature())

    def test_actual_dat_and_live_storage_inventory(self):
        files=list((ROOT/'input/task042_neural_coarse_inverse').glob('v51_*.dat'));specs=[load_phase_explicit_accuracy(p) for p in files]
        self.assertEqual(len(specs),8);self.assertEqual({s.derived['stage'] for s in specs},set(STAGES))
        from src.runners.port_preparation import storage_limits,context
        self.assertEqual(storage_limits('v51')['task_storage_bytes'],38*2**30)
        self.assertEqual(context('v51')[0].label,'V51')
        self.assertEqual(plan_record()['complete_solve_cap'],6)
        self.assertTrue(all(s.derived['environment_mode']=='fe' for s in specs))


if __name__=='__main__':unittest.main()
