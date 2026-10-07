"""Small mathematical and live-namespace regressions; no PDE or old replay."""
import unittest
import numpy as np
import basix
from src.solvers.hcurl_affine_phase_tensor import AffinePhaseReferenceTensor,axis_widths
from src.solvers.common_continuous_weak import design,tests,volume_parts,common_layout


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
        expected,_=raw_direction_action(self.element,coords,d,k,2.3,eps,1.,4)
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
        self.assertIn('p7',scope.plan_record()['raw_tensor_parents'])
        self.assertNotIn('p7_Z2',scope.plan_record()['raw_tensor_parents'])

    def test_actual_layout_helper_consumes_function_space(self):
        from types import SimpleNamespace
        geo={'axes_nm':{'x':[0.,1.,2.,3.,4.],'y':[0.,1.,2.,3.,4.],'z':[-1.,0.,1.,2.,3.,4.]}}
        points=basix.cell.geometry(basix.CellType.hexahedron)*[4.,4.,5.]+[0.,0.,-1.]
        mesh=SimpleNamespace(geometry=SimpleNamespace(x=points,dofmap=np.arange(8).reshape(1,8)))
        boxes,parents=common_layout(SimpleNamespace(mesh=mesh),design(geo,[.7,.2,0.]))
        self.assertEqual(boxes.shape,(640,2,3));self.assertTrue(np.all(parents==0))

    def test_actual_continuous_flat_lift_sign_and_operation_scale(self):
        from src.solvers.common_continuous_weak import boundary_parts
        from src.solvers.common_weak_phase_scope import plan_record
        from src.solvers.phase_explicit_accuracy import configuration
        from src.solvers.fixed_phase_fem import carrier
        from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
        from src.solvers.scattering_accuracy_fields import analytic
        from src.common.analytic_fields_3d import fresnel_reference
        from src.solvers.dtn_port_3d import _incident_projection_onto_top_mode
        cfg=configuration('NOTCH',6,'ORIGINAL');cfg.diffraction_order_max_m=11;cfg.diffraction_order_max_n=4
        modes,_,_=build_dynamic_mode_inventory(cfg)
        self.assertEqual(len(modes),828)
        definition=design(plan_record()['physical_descriptor']['geometry'],carrier(cfg))
        f=fresnel_reference(cfg);port=np.asarray([_incident_projection_onto_top_mode(m,cfg)+
            (cfg.incident_amplitude*(f['r'] if m.side=='top' else f['t']) if (m.m,m.n,m.polarization)==(0,0,'s') else 0)
            for m in modes])
        dt,load,_=boundary_parts(cfg,modes,port,definition);summed=np.zeros((5,24),complex);op=np.zeros(24)
        nodes,w=np.polynomial.legendre.leggauss(16);area=(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)
        for a,b in zip(cfg.mesh_axis_z_values[:-1],cfg.mesh_axis_z_values[1:]):
            xyz=np.column_stack((np.full(16,cfg.x_min+.13),np.full(16,cfg.y_min+.27),a+(nodes+1)*(b-a)/2))
            v,cv=tests(xyz,definition);parts,bound=volume_parts(analytic(cfg,xyz),xyz,w*(b-a)*area/2,v,cv,
                kappa=carrier(cfg),k0=cfg.k0,epsilon=cfg.eps_substrate if (a+b)/2<0 else cfg.eps_air,mu=cfg.mu_r,return_operation=True)
            summed+=parts;op+=bound
        good=load-dt-summed.sum(axis=0);wrong=load+dt-summed.sum(axis=0)
        self.assertLess(np.max(np.abs(good[12:16])),1e-10)
        self.assertGreater(np.max(np.abs(wrong[12:16])),.01)
        self.assertTrue(np.all(op+1e-12>=np.abs(summed).sum(axis=0)))

    def test_new_y_cell_cuts_and_actual_modal_checker(self):
        from types import SimpleNamespace
        from benchmarks.collect_phase_explicit_accuracy import expected_modal_count
        geo={'axes_nm':{'x':[0.,1.,2.,3.,4.],'y':[0.,1.,2.,3.,4.],'z':[-1.,0.,1.,2.,3.,4.]}}
        verts=basix.cell.geometry(basix.CellType.hexahedron)
        coordinates=np.vstack((verts*[4.,1.5,5.]+[0.,0.,-1.],verts*[4.,2.5,5.]+[0.,1.5,-1.]))
        mesh=SimpleNamespace(geometry=SimpleNamespace(x=coordinates,dofmap=np.arange(16).reshape(2,8)))
        boxes,parents=common_layout(SimpleNamespace(mesh=mesh),design(geo,[.7,.2,0.]))
        self.assertEqual(len(boxes),800)
        self.assertTrue(np.all((boxes[:,1,1]<=1.5)|(boxes[:,0,1]>=1.5)))
        self.assertEqual(set(parents),{0,1})
        scope=SimpleNamespace(NAMESPACE='v57')
        self.assertEqual(expected_modal_count({'case_spec':{'complete_modes':828}},scope),828)
        with self.assertRaises(ValueError):expected_modal_count({'case_spec':{'complete_modes':829}},scope)

    def test_actual_recovery_checker_with_near_zero_internal_rhs(self):
        from benchmarks.collect_common_weak_phase import local_recovery_check
        a=np.array([[3+1j,2-.4j],[.7+.2j,1.5-.1j]])
        co=np.array([-(2-.4j)/(3+1j),1.],complex);i=np.array([0]);t=np.array([1])
        v=dict(actual_coefficients=co,internal_rows=i,trace_rows=t,internal_rhs=(a@co)[i],recovered_internal=co[i]*(1+1e-15))
        result=local_recovery_check(a,v)
        self.assertTrue(result['pass_gate']);self.assertGreater(result['operation_scale'],1.)
        v['recovered_internal']=co[i]*.99
        self.assertFalse(local_recovery_check(a,v)['pass_gate'])


if __name__=='__main__':unittest.main()
