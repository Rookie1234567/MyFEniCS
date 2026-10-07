"""Nonzero complex/gauge/canonical packet and namespace regressions."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np
from src.solvers.phase_boundary_checkpoint import packed_action,LoadedSurface,wave_key,digest
from src.solvers.phase_deployment import gauge_identity,quadrature_certificate
from src.solvers.phase_deployment_scope import numerical_carrier,case_spec
from src.solvers.scattering_anchor import save_arrays
from src.runners.task042_shared import write_json


class Tests(unittest.TestCase):
    def test_complex_action_and_adjoint(self):
        rng=np.random.default_rng(58);C=rng.normal(size=6)+1j*rng.normal(size=6);D=rng.normal(size=6)+1j*rng.normal(size=6)
        p=dict(offsets=np.array([0,3,6]),rows=np.array([0,1,2,1,2,3]),C=C,D=D,H=np.array([.7,1.3]))
        A=np.zeros((4,4),complex)
        for i,h in enumerate(p['H']):
            sl=slice(p['offsets'][i],p['offsets'][i+1]);rr=p['rows'][sl];A[np.ix_(rr,rr)]+=np.outer(C[sl],D[sl])/h
        x=rng.normal(size=4)+1j*rng.normal(size=4)
        np.testing.assert_allclose(packed_action(p,x),A@x,rtol=1e-14)
        np.testing.assert_allclose(packed_action(p,x,adjoint=True),A.conj().T@x,rtol=1e-14)
        self.assertGreater(np.linalg.norm(A-A.conj().T),1)

    def test_nonzero_phase_and_curl(self):
        rng=np.random.default_rng(6);p=rng.random((13,3));u=rng.normal(size=(13,3))+1j*rng.normal(size=(13,3));c=rng.normal(size=(13,3))+1j*rng.normal(size=(13,3))
        x=gauge_identity(p,u,c,np.array([8.94,.78,0]),np.array([0,4.847,0]))
        self.assertLess(max(x['E'],x['curl']),1e-14)

    def test_physical_incidence_unchanged(self):
        cfg=SimpleNamespace(kx=8.94,ky=.78,x_min=0,x_max=2.5925925925925926,y_min=0,y_max=1.2962962962962963)
        old=(cfg.kx,cfg.ky);k=numerical_carrier(cfg,case_spec('G6'))
        self.assertEqual(old,(cfg.kx,cfg.ky));self.assertEqual(k[0],cfg.kx);self.assertGreater(k[1],cfg.ky)

    def test_polynomial_q(self):
        import basix
        for p,q in ((6,15),(7,17)):
            e=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,p,lagrange_variant=basix.LagrangeVariant.gll_warped)
            self.assertTrue(quadrature_certificate(e,q)['pass_gate'])

    def test_loaded_component_inventory_and_live_identity(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);mpc=object();mode=SimpleNamespace(side='top',alpha=2+0j,gamma=3+0j,k_vector=[2,3,4j])
            ident=dict(native_rows=4,q=63,kappa=[1,2,0]);val=np.array([[1+2j,3j],[2j,4-1j]])
            rec=save_arrays(folder/'a.npz',component_offsets=np.array([0,2]),component_rows=np.array([0,3]),component_values=val,incident=np.arange(4,dtype=complex))
            write_json(folder/'a.json',dict(identity=ident,arrays=rec,keys=[wave_key(mode)],method='basix2d'))
            obj=LoadedSurface(folder/'a.json',None,mpc,None,63,[1,2,0],ident)
            rows,v=obj.components(mode);np.testing.assert_array_equal(v,val)
            rr,vv=obj.assemblers()['top',1].assemble_entries(mode,mpc);np.testing.assert_array_equal(vv,val[:,1])
            with self.assertRaisesRegex(ValueError,'identity'):LoadedSurface(folder/'a.json',None,mpc,None,47,[1,2,0],dict(ident,q=47))
            with self.assertRaisesRegex(ValueError,'MPC'):obj.assemblers()['top',0].assemble_entries(mode,object())
            self.assertEqual(digest(wave_key(mode)),digest(json.loads(json.dumps(json.loads((folder/'a.json').read_text())['keys'][0]))))

    def test_dat_and_live_budgets(self):
        from src.io.phase_notch_hp import load_phase_notch_hp
        from src.solvers import phase_deployment_scope as scope
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        self.assertIs(context('v58')[0],scope.window);self.assertEqual(storage_limits('v58')['new_storage_bytes'],12*2**30)
        for p in sorted((scope.ROOT/'input/task042_neural_coarse_inverse').glob('v58_*.dat')):
            r=load_phase_notch_hp(p,scope=scope);self.assertEqual(r.derived['preparation_scope'],'v58');self.assertEqual(r.execution['planning_memory_gib'],64)
            if r.derived['stage']=='G7':self.assertEqual(r.discretization['degree'],7);self.assertEqual(r.boundary['complete_modes'],828)


if __name__=='__main__':unittest.main()
