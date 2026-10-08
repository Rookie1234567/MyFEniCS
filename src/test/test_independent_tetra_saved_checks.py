"""End-to-end saved-array checker: negative, zero and wrong inventories."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from benchmarks.check_independent_tetra import FIELDS,saved_pair
from src.solvers.scattering_anchor import save_arrays
from src.solvers.phase_notch_hp_modes import compare_payloads,AMPLITUDES


class SavedTetraCheckerTests(unittest.TestCase):
    def fixture(self,folder,*,zero=False):
        rows=[]
        for s in ('top','bottom'):
            for m in range(-11,12):
                for n in range(-4,5):
                    for p in ('s','p'):
                        row=dict(side=s,m=m,n=n,polarization=p,power_ratio=0.)
                        row.update({name:[.5,.25] for name in AMPLITUDES});rows.append(row)
        payload=dict(reference_planes={'top_z':1.,'bottom_z':0.},orders=rows)
        path=folder/'port_power.json';path.write_text(json.dumps(payload))
        pm=dict(R_total=.2,T_total=.7,A_balance=.1)
        vm=dict(A_volume_total=.1,energy_closure_error=0.)
        states=[dict(arrays=dict(sha256=str(j)),mode_power_path=str(path),output=dict(port_metrics=pm,volume_metrics=vm)) for j in range(2)]
        modes,vector=compare_payloads(payload,payload,828);modes['arrays']=save_arrays(folder/'modes.npz',**vector)
        points=np.arange(720,dtype=float).reshape(240,3);arrays=dict(selected_points=points)
        for name in FIELDS:
            arrays['selected_'+name+'_first']=np.ones((240,3),np.complex128)
            arrays['selected_'+name+'_second']=np.full((240,3),1. if zero else 1.01,np.complex128)
        arrays['per_cell_integrals']=np.tile([0. if zero else .01,100.,80.],(2,6,1))
        receipt=save_arrays(folder/'common.npz',**arrays)
        pair=dict(arrays=receipt,q23_arrays=receipt,quadrature_pair=[23,31],modes=modes,
            parent_array_sha256=['0','1'],fields={k:dict(relative=0. if zero else .01) for k in FIELDS},
            selected={k:0. if zero else .01/1.01 for k in FIELDS},pass_gate=not zero)
        return pair,states,points

    def test_negative_recomputed_and_zero_difference_is_not_failure(self):
        with tempfile.TemporaryDirectory() as td:
            pair,states,points=self.fixture(Path(td));r=saved_pair(pair,*states,expected_points=points)
            self.assertFalse(r['pass_gate']);self.assertFalse(r['published_gate_matches_recalculation'])
            self.assertEqual(r['new_solve'],0)
            pair,states,points=self.fixture(Path(td),zero=True);r=saved_pair(pair,*states,expected_points=points)
            self.assertTrue(r['pass_gate']);self.assertFalse(r['published_gate_matches_recalculation'])

    def test_parent_points_and_declared_metrics_do_not_override_arrays(self):
        with tempfile.TemporaryDirectory() as td:
            pair,states,points=self.fixture(Path(td))
            for kind in ('parent','metric','points'):
                bad=copy.deepcopy(pair);expected=points.copy()
                if kind=='parent':bad['parent_array_sha256'][0]='wrong'
                elif kind=='metric':bad['fields']['E_total']['relative']=0.
                else:expected[0,0]+=1.
                with self.assertRaises(ValueError):saved_pair(bad,*states,expected_points=expected)

    def test_complete_complex_vector_inventory_required(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);pair,states,points=self.fixture(folder)
            from src.solvers.scattering_anchor_checks import checked_arrays
            a=checked_arrays(pair['arrays']);a['selected_E_total_first']=a['selected_E_total_first'][:-1]
            pair['arrays']=save_arrays(folder/'bad.npz',**a)
            with self.assertRaises(ValueError):saved_pair(pair,*states,expected_points=points)


if __name__=='__main__':unittest.main()
