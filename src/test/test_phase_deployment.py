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
    def test_saved_consumer_public_output_verdict(self):
        from benchmarks.collect_phase_deployment import checked_state
        self.assertTrue(checked_state({'pass_gate':True},{'energy_pass':True})['pass_gate'])
        self.assertFalse(checked_state({'pass_gate':True},{'energy_pass':False})['pass_gate'])
        self.assertFalse(checked_state({'pass_gate':False},{'energy_pass':True})['pass_gate'])
        with self.assertRaises(KeyError):checked_state({'pass_gate':True},{})

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


    def test_target_bank_includes_preconditioned_directions(self):
        from benchmarks.collect_phase_deployment import target_scope
        record=target_scope([])
        for degree,rows in (('6',507608956),('7',699775356)):
            v=record['FGMRES_restart32'][degree]
            self.assertEqual((v['V_vectors'],v['Z_vectors']),(33,32))
            self.assertEqual(v['trace_plus_port_V_and_Z_bytes'],rows*16*(33+32))
            self.assertFalse(record['target_2TB_48h_qualified'])
            self.assertTrue(v['extra_solution_rhs_residual_workspace_not_included'])

    def test_increment_archive_preserves_literal_stdout_and_member_hashes(self):
        from benchmarks.collect_common_weak_phase import archive_increment
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);tmp=root/'tmp';artifact=root/'artifact';out=root/'records';folder=tmp/'aux';folder.mkdir(parents=True);artifact.mkdir();out.mkdir()
            (tmp/'stdout').write_text('nonempty scientific result\n');(tmp/'stderr').write_text('retained failure\n')
            values=np.array([1+2j,-3+4j]);receipt=save_arrays(artifact/'state.npz',z=values)
            s=SimpleNamespace(ROOT=root,NAMESPACE='v58',ARTIFACT=artifact,window=SimpleNamespace(TMP=tmp))
            archive_increment(folder,out,[],{},active_scope=s)
            index=json.loads((out/'raw_archive_index_v58.json').read_text())
            byname={Path(row['path']).name:row for row in index['files']}
            for name in ('stdout','stderr'):
                self.assertEqual((root/byname[name]['archived']).read_bytes(),(tmp/name).read_bytes())
            arrays=json.loads((out/'array_inventory_v58.json').read_text())
            self.assertEqual(arrays['files'][0]['members']['z']['sha256'],receipt['members']['z']['sha256'])
            self.assertEqual(hashlib.sha256((artifact/'state.npz').read_bytes()).hexdigest(),arrays['files'][0]['sha256'])

    def test_actual_v58_modal_inventory(self):
        from benchmarks.collect_phase_explicit_accuracy import expected_modal_count
        self.assertEqual(expected_modal_count({'case_spec':{'complete_modes':828}},SimpleNamespace(NAMESPACE='v58')),828)
        with self.assertRaises(ValueError):expected_modal_count({'case_spec':{'complete_modes':827}},SimpleNamespace(NAMESPACE='v58'))



if __name__=='__main__':unittest.main()
