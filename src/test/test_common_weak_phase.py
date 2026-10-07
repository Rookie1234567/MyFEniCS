"""Small mathematical and live-namespace regressions; no PDE or old replay."""
import unittest
import numpy as np
import basix
from src.solvers.hcurl_affine_phase_tensor import AffinePhaseReferenceTensor,axis_widths
from src.solvers.common_continuous_weak import design,tests,volume_parts


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.element=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,2,
            basix.LagrangeVariant.legendre)

    def test_complete_conjugate_phase_against_direct_quadrature(self):
        from src.solvers.phase_p_order_consistency import raw_direction_action
        k=np.array([.7,-.3,.2]);h=np.array([.3,.8,.5]);eps=1.2+.17j
        f=AffinePhaseReferenceTensor(self.element,kappa=k,k0=2.3,epsilon_by_tag={3:eps},q=7)
        ref=basix.cell.geometry(basix.CellType.hexahedron);coords=ref*h
        rng=np.random.default_rng(571);d=rng.normal(size=self.element.dim)+1j*rng.normal(size=self.element.dim)
        expected=raw_direction_action(self.element,coords,d,k,2.3,eps,1.,4)
        actual=f.tensor(tag=3,widths=h)@d
        self.assertLess(np.linalg.norm(actual-expected)/np.linalg.norm(expected),1e-12)
        wrong=f.base.tensor(tag=3,widths=h)@d
        self.assertGreater(np.linalg.norm(wrong-expected)/np.linalg.norm(expected),.01)
        self.assertEqual(f.audit['reference_component_count'],15)

    def test_kappa_zero_and_reject_unsupported_geometry(self):
        f=AffinePhaseReferenceTensor(self.element,kappa=[0.,0.,0.],k0=2.,epsilon_by_tag={1:1+.2j},q=7)
        self.assertTrue(np.allclose(f.tensor(tag=1,widths=[1.,2.,3.]),f.base.tensor(tag=1,widths=[1.,2.,3.]),rtol=1e-14,atol=1e-14))
        with self.assertRaises(ValueError):AffinePhaseReferenceTensor(self.element,kappa=[1j,0,0],k0=2.,epsilon_by_tag={1:1},q=7)
        x=basix.cell.geometry(basix.CellType.hexahedron).copy();x[7,0]+=.1
        with self.assertRaises(ValueError):axis_widths(x)

    def test_independent_continuous_covariant_gradient_and_nonzero_lifts(self):
        geo={'axes_nm':{'x':[0.,1.,2.,3.,4.],'y':[0.,1.,2.,3.,4.],'z':[-1.,0.,1.,2.,3.,4.]}}
        k=np.array([.7,.2,0.]);definition=design(geo,k)
        points=np.array([[1.3,1.4,.3],[2.1,1.8,1.2]])
        v,c=tests(points,definition)
        self.assertEqual(v.shape,(24,2,3))
        for j in (3,7,11):self.assertLess(np.max(np.abs(c[j]+1j*np.cross(k,v[j]))),1e-15)
        top,_=tests(np.array([[1.3,1.4,4.]]),definition)
        self.assertGreater(np.linalg.norm(top[12:]),1.)
        physical={'E':np.ones((2,3),complex),'curl':np.ones((2,3),complex)*(1+.1j)}
        parts=volume_parts(physical,points,np.ones(2),v,c,kappa=k,k0=2.,epsilon=1+.3j,mu=1.)
        self.assertEqual(parts.shape,(5,24));self.assertGreater(np.linalg.norm(parts),1.)

    def test_v57_case_schema_and_memory_storage_propagation(self):
        from src.solvers import common_weak_phase_scope as scope
        from src.io.phase_notch_hp import load_phase_notch_hp
        from src.runners.port_preparation import storage_limits,context
        for role in scope.STAGES:
            import pathlib
            paths=list((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v57_*.dat'))
            matched=[load_phase_notch_hp(p,scope=scope) for p in paths]
            r=next(x for x in matched if x.derived['stage']==role)
            self.assertEqual(r.execution['planning_memory_gib'],64)
            self.assertEqual(r.derived['storage_limits'],storage_limits('v57'))
        self.assertEqual(context('v57')[0].TMP,scope.window.TMP)


if __name__=='__main__':unittest.main()
