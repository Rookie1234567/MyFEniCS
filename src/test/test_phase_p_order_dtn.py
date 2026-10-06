"""Only new reader, finite inventories, full-body transfer and V54 wiring."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from src.solvers import phase_p_order_dtn_scope as scope
from src.solvers.phase_notch_hp_modes import finite_mode_ranges,keyed_modes
from src.io.phase_notch_hp import descriptor,load_phase_notch_hp


class SeparationTests(unittest.TestCase):
    def test_explicit_inventory_unknown_rejected(self):
        self.assertEqual([finite_mode_ranges(n) for n in (532,828,1188)],[(9,3),(11,4),(13,5)])
        for n in (40,829,0,None):
            with self.assertRaises(ValueError):finite_mode_ranges(n)
        m,n=finite_mode_ranges(1188)
        payload=dict(reference_planes={'top_z':1.,'bottom_z':0.},orders=[dict(side=s,m=i,n=j,polarization=p) for s in ('top','bottom') for i in range(-m,m+1) for j in range(-n,n+1) for p in ('s','p')])
        self.assertEqual(len(keyed_modes(payload,1188)),1188)
        payload['orders'][-1]=payload['orders'][0]
        with self.assertRaises(ValueError):keyed_modes(payload,1188)

    def test_actual_dat_scope_capacities_and_closed_isolation(self):
        rows=[load_phase_notch_hp(p,scope=scope) for p in (scope.ROOT/'input/task042_neural_coarse_inverse').glob('v54_*.dat')]
        self.assertEqual({r.derived['stage'] for r in rows},set(scope.STAGES))
        for role,count,degree,condensed in [('R7',828,7,46076),('R6',828,6,33660),('C',1188,7,46436)]:
            physical,spec=descriptor(role,scope=scope)
            self.assertEqual((physical['boundary']['complete_modes'],spec['degree'],spec['rows']),(count,degree,condensed))
            self.assertEqual(np.prod([len(x)-1 for x in physical['geometry']['axes_nm'].values()]),160)
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        self.assertEqual(context('v54')[0].label,'V54')
        self.assertEqual(storage_limits('v54')['task_storage_bytes'],68*2**30)
        with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2*1024*2**30,effective_total_bytes=2*1024*2**30,system_reserve_bytes=205*2**30,reserve_bytes=(205+128)*2**30)):
            self.assertEqual(preparation_memory_envelope('v54')['launch_cap_bytes'],48*2**30)
        for r in rows:self.assertEqual([r.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],[32,40,48])

    def test_basix_full_not_trace_embedding_and_complex_dual(self):
        import basix
        e=[basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,p,basix.LagrangeVariant.legendre) for p in (2,3)]
        I=basix.compute_interpolation_operator(*e);rng=np.random.default_rng(5400)
        from src.solvers.phase_p_order_consistency import interpolation_operator
        self.assertTrue(np.array_equal(I,interpolation_operator(e[0]._e,e[1]._e)))
        u=rng.normal(size=e[0].dim)+1j*rng.normal(size=e[0].dim);v=rng.normal(size=e[1].dim)+1j*rng.normal(size=e[1].dim)
        points=np.array([[.13,.41,.73],[.23,.36,.51]])
        a=np.einsum('dqjc,j->dqc',e[0].tabulate(1,points),u);b=np.einsum('dqjc,j->dqc',e[1].tabulate(1,points),I@u)
        self.assertLess(np.linalg.norm(a-b)/np.linalg.norm(a),1e-11)
        self.assertLess(abs(np.vdot(v,I@u)-np.vdot(I.conj().T@v,u)),1e-11)
        self.assertGreater(np.linalg.norm(I[np.array(e[1].entity_dofs[3][0]),:]@u),0)

    def test_readonly_raw_exact_reuse_rejects_bad_hash(self):
        from src.solvers.phase_tensor_checkpoint import RawTensorCheckpoint
        from src.solvers.phase_raw_tensor_reader import ReadonlyRawTensorProvider
        from src.solvers.scattering_anchor import save_arrays
        with tempfile.TemporaryDirectory(dir=scope.window.TMP) as d:
            d=Path(d);coords=np.arange(24,dtype=float);key=RawTensorCheckpoint.key(coords,1);a=save_arrays(d/'tensor.npz',tensor=np.array([[2+3j]]),coordinates=coords,kappa=np.array([1.,2.,0.]))
            class FFI:
                @staticmethod
                def string(x):return x
            e=SimpleNamespace(hash=lambda:42)
            form=SimpleNamespace(module=SimpleNamespace(ffi=FFI()),ufcx_form=SimpleNamespace(signature=b'signature'),function_spaces=[SimpleNamespace(element=SimpleNamespace(basix_element=e))])
            reader=ReadonlyRawTensorProvider.__new__(ReadonlyRawTensorProvider)
            from contextlib import nullcontext
            reader.journal=SimpleNamespace(measured=lambda x:nullcontext(),event=lambda *a,**kw:None,source_state={'source_sha':'live'})
            reader.bundle={'kappa':np.array([1.,2.,0.])};reader.seconds=0;reader.hits=[];reader.misses=[]
            entry=dict(key=key,tag=1,dimension=1,dtype='complex128',element_hash=42,form_signature='signature',kappa=[1.,2.,0.],arrays=a,producer_sha='old')
            reader.entries={key:[(entry,{'path':'old','sha256':'manifest'})]}
            value,identity=reader.load(form,coords,tag=1,dimension=1)
            self.assertEqual(value[0,0],2+3j);self.assertIn('reused_parent',identity)
            self.assertIsNone(reader.load(form,np.nextafter(coords,np.inf),tag=1,dimension=1))
            entry['arrays']['sha256']='wrong'
            with self.assertRaises(ValueError):reader.load(form,coords,tag=1,dimension=1)


if __name__=='__main__':unittest.main()
