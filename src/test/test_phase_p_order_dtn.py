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
    def test_actual_carrier_pair_complete1188_and_unknown_rejected(self):
        from src.solvers.scattering_accuracy_boundary import carrier_pair,require_finite_carrier_inventory
        m,n=finite_mode_ranges(1188)
        ids=[dict(mode_index=k,side=s,m=i,n=j,polarization=p) for k,(s,i,j,p) in enumerate(
            (s,i,j,p) for s in ('top','bottom') for i in range(-m,m+1) for j in range(-n,n+1) for p in ('s','p'))]
        entries=[SimpleNamespace(coupling_rows=np.array([0,2]),coupling_values=np.array([1+2j,-3+.2j]),
            projection_rows=np.array([1,2]),projection_values=np.array([4-.5j,2+3j]),normalization_h=2+.7j) for _ in ids]
        carrier=SimpleNamespace(entries=entries)
        self.assertTrue(carrier_pair(carrier,carrier,ids,expected_modes=1188)['pass'])
        with self.assertRaises(ValueError):carrier_pair(carrier,carrier,ids[:-1],expected_modes=1188)
        with self.assertRaises(ValueError):carrier_pair(carrier,SimpleNamespace(entries=entries[:-1]),ids,expected_modes=1188)
        with self.assertRaises(ValueError):require_finite_carrier_inventory(ids[:829],829)

    def test_closed_residual_inventory_operation_scale(self):
        from src.solvers.phase_p_order_dtn import residual_inventory_identity
        old_rhs=np.array([1+2j,3-4j]);old_volume=np.array([1e5+3j,-2e5+4j]);old_boundary=old_rhs-old_volume
        new_rhs=old_rhs+np.array([.03j,.01]);new_volume=old_volume.copy();new_boundary=old_boundary+np.array([.02,.05j])
        old_r=old_rhs-old_volume-old_boundary;new_r=new_rhs-new_volume-new_boundary
        terms,metrics=residual_inventory_identity(old_rhs,new_rhs,old_r,new_r,old_volume,new_volume,old_boundary,new_boundary)
        self.assertLess(metrics['operation'],1e-10);self.assertGreater(metrics['denominator'],1e5)
        wrong,_=residual_inventory_identity(old_rhs,new_rhs,old_r,new_r,old_volume,new_volume,old_boundary+10,new_boundary)
        self.assertGreater(np.linalg.norm(wrong['identity_defect'])/metrics['denominator'],1e-10)
        self.assertGreater(np.linalg.norm(terms['load_delta']),0)
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

    def test_independent_inventory_checker_rejects_wrong_terms(self):
        from benchmarks.check_phase_p_order_dtn import check_inventory_identity
        from src.solvers.phase_p_order_dtn import residual_inventory_identity
        old_rhs=np.array([1+2j,3-4j]);old_volume=np.array([1e5+3j,-2e5+4j]);old_boundary=old_rhs-old_volume
        new_rhs=old_rhs+np.array([.03j,.01]);new_volume=old_volume.copy();new_boundary=old_boundary+np.array([.02,.05j])
        old_r=old_rhs-old_volume-old_boundary;new_r=new_rhs-new_volume-new_boundary
        terms,_=residual_inventory_identity(old_rhs,new_rhs,old_r,new_r,old_volume,new_volume,old_boundary,new_boundary)
        v=dict(rhs_old=old_rhs,rhs_new=new_rhs,old_residual=old_r,new_residual=new_r,old_volume=old_volume,
            new_volume=new_volume,old_closed_boundary=old_boundary,new_closed_boundary=new_boundary,**terms)
        self.assertTrue(check_inventory_identity(v)['pass_gate'])
        bad=dict(v,action_delta=terms['action_delta']+10)
        with self.assertRaises(ValueError):check_inventory_identity(bad)
        bad=dict(v);bad.pop('old_closed_boundary')
        with self.assertRaises(ValueError):check_inventory_identity(bad)
        bad=dict(v,old_residual=old_r+10,new_residual=new_r+10)
        with self.assertRaises(ValueError):check_inventory_identity(bad)

    def test_independent_raw_direction_checker_negative_inventory(self):
        from benchmarks.check_phase_p_order_dtn import check_raw_direction
        rng=np.random.default_rng(5407);coef=rng.normal(size=1344)+1j*rng.normal(size=1344)
        pieces=[coef*3,coef*(2+1j),coef*(-4+.3j)];total=sum(pieces)
        v={f'q13_d0_{k}':x for k,x in zip(('curl','kappa_cross','mass'),pieces,strict=True)}
        v.update({f'q11_d0_{k}':x.copy() for k,x in zip(('curl','kappa_cross','mass'),pieces,strict=True)})
        v.update(q13_d0=total,q11_d0=total.copy(),raw_d0=total.copy(),coefficient_d0=coef)
        self.assertTrue(check_raw_direction(v,0)['pass_gate'])
        bad=dict(v,raw_d0=total+.001)
        with self.assertRaises(ValueError):check_raw_direction(bad,0)
        bad=dict(v,coefficient_d0=np.zeros_like(coef))
        with self.assertRaises(ValueError):check_raw_direction(bad,0)
        bad=dict(v);bad.pop('q13_d0_kappa_cross')
        with self.assertRaises(ValueError):check_raw_direction(bad,0)

    def test_saved_modal_inventory_v54_and_legacy_default(self):
        from benchmarks.collect_phase_explicit_accuracy import expected_modal_count
        for count in (532,828,1188):
            self.assertEqual(expected_modal_count(dict(case_spec=dict(complete_modes=count)),scope),count)
        self.assertEqual(expected_modal_count({},SimpleNamespace(NAMESPACE='v51')),532)
        with self.assertRaises(ValueError):expected_modal_count(dict(case_spec=dict(complete_modes=829)),scope)

    def test_live_basis_identity_wrapper_and_mismatch(self):
        import basix
        from src.solvers.phase_raw_tensor_reader import live_basis_identity
        element=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,2,basix.LagrangeVariant.legendre)
        classes=[dict(element_hash=int(element.hash()),degree=2,dimension=element.dim,dtype='complex128')]
        actual=live_basis_identity(element._e,classes)
        self.assertEqual(actual['family'],'N1E');self.assertEqual(actual['lagrange_variant'],'legendre')
        self.assertEqual(actual['dof_ordering'],list(element.dof_ordering))
        with self.assertRaises(ValueError):live_basis_identity(element._e,[])
        with self.assertRaises(ValueError):live_basis_identity(element._e,[dict(classes[0],element_hash=42)])

    def test_v54_surface_cache_single_packet_and_old_default(self):
        from benchmarks.collect_phase_notch_hp import boundary_arrays
        receipts=[dict(sha256=str(i),value=np.array([i+1j])) for i in range(3)]
        with patch('benchmarks.collect_phase_notch_hp.checked_arrays',side_effect=lambda r:r['value']):
            cache={}
            for r in receipts:
                self.assertTrue(np.array_equal(boundary_arrays(r,cache,single=True),r['value']))
                self.assertEqual(list(cache),[r['sha256']])
            cache={}
            for r in receipts:boundary_arrays(r,cache)
            self.assertEqual(len(cache),3)

    def test_inventory_unchanged_body_binding(self):
        from benchmarks.check_phase_p_order_dtn import check_frozen_member
        from src.solvers.scattering_anchor import array_hash
        x=np.array([1+2j,-3+.5j],dtype=np.complex128)
        record=dict(members=dict(u_storage=dict(shape=[2],dtype='complex128',sha256=array_hash(x))))
        self.assertEqual(check_frozen_member(x,record,'u_storage'),array_hash(x))
        with self.assertRaises(ValueError):check_frozen_member(x+.01,record,'u_storage')
        with self.assertRaises(ValueError):check_frozen_member(x.astype(np.complex64),record,'u_storage')


if __name__=='__main__':unittest.main()
