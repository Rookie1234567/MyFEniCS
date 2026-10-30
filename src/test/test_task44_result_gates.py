"""Result contract negatives; no FE and no surrogate labels."""
import copy
from pathlib import Path
import unittest
from src.runners.sixlayer_case import validate_outputs,validate_floquet
from src.io.sixlayer_input import resolve_sixlayer_input,build_sixlayer_config

class ResultGateTests(unittest.TestCase):
    def setUp(self):
        _,self.resolved=resolve_sixlayer_input(Path(__file__).resolve().parents[2]/'input/task44_sixlayer/A.dat')
        self.plan=self.resolved['mesh_plan'];self.cfg=build_sixlayer_config(self.resolved)
        self.summary=dict(R_total=.2,T_total=.7,R00_s=.1,R00_p=.02,R00_total=.12,A_balance=.1)
        self.absorption={'regions':{name:{'cell_count':2,'status':'ok','volume_nm3':volume,'A_volume':.1/7}
                         for name,volume in self.plan['expected_region_volumes_nm3'].items() if name!='air'},'A_volume_total':.1}
        self.original={'passed':True,'relative_residual':1e-10}
    def test_all_power_identities(self):
        self.assertEqual(validate_outputs(self.summary,self.absorption,self.original,self.plan)['R_total'],.2)
        for changes in ({'R00_s':.3,'R00_total':.32},{'A_balance':.3},{'R_total':float('nan')},{'R00_s':-.001}):
            with self.assertRaises(ValueError):validate_outputs(self.summary|changes,self.absorption,self.original,self.plan)
    def test_missing_material_never_silently_dropped(self):
        for value in (None,float('nan')):
            a=copy.deepcopy(self.absorption);next(iter(a['regions'].values()))['A_volume']=value
            with self.assertRaises(ValueError):validate_outputs(self.summary,a,self.original,self.plan)
        a=copy.deepcopy(self.absorption);next(iter(a['regions'].values()))['cell_count']=0
        with self.assertRaises(ValueError):validate_outputs(self.summary,a,self.original,self.plan)
    def test_full_rr_required(self):
        for original in ({'passed':False,'relative_residual':1e-10},{'passed':True,'relative_residual':2e-6},
                         {'passed':True,'relative_residual':float('nan')}):
            with self.assertRaises(ValueError):validate_outputs(self.summary,self.absorption,original,self.plan)
    def test_actual_phase_and_count(self):
        s={k:0 for k in ('floquet_x_face_mismatch','floquet_y_face_mismatch','floquet_edge_corner_mismatch',
                        'floquet_edge_corner_constraint_phase_mismatch','max_face_pairing_coordinate_error')}
        s.update({k:12 for k in ('floquet_num_constraints','floquet_num_x_constraints','floquet_num_y_constraints','floquet_num_corner_constraints')})
        s.update(floquet_constraint_phase_x=self.cfg.floquet_phase_x,floquet_constraint_phase_y=self.cfg.floquet_phase_y,
                 floquet_constraint_phase_corner=self.cfg.floquet_phase_x*self.cfg.floquet_phase_y)
        validate_floquet(s,self.cfg)
        for change in ({'floquet_constraint_phase_y':1},{'floquet_num_constraints':0},{'floquet_x_face_mismatch':float('nan')}):
            with self.assertRaises(ValueError):validate_floquet(s|change,self.cfg)

if __name__=='__main__':unittest.main()
