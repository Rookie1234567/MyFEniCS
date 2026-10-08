"""Only new V64 contracts: actual ancestry, saved mesh, marking and role budgets."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from src.solvers import local_h_pilot_scope as scope
from src.solvers.tetra_local_marking import freeze_marking


class LocalHPilotTests(unittest.TestCase):
    def test_fixed_global_norm_and_minimum_prefix_geometry_tie(self):
        d=np.array([[3.,0.,100.],[3.,0.,0.],[0.,2.,0.],[0.,1.,0.]])
        keys=[(3,),(1,),(2,),(0,)]
        r=freeze_marking(d,[6.,3.],keys)
        np.testing.assert_allclose(r['eta_squared'],[.5,.5,2/3,1/3])
        self.assertEqual(r['indices'].tolist(),[2,1])
        self.assertAlmostEqual(r['coverage'],7/12)
        self.assertLess(r['eta_squared'][r['order'][:len(r['indices'])-1]].sum(),.5*r['total_indicator'])
        with self.assertRaisesRegex(ValueError,'fixed'):freeze_marking(d,[6,3],keys,theta=.4)
        with self.assertRaisesRegex(ValueError,'zero'):freeze_marking(np.zeros((4,3)),[6,3],keys)
        with self.assertRaisesRegex(ValueError,'unique'):freeze_marking(d,[6,3],[(1,)]*4)

    def test_actual_four_entries_and_case_budget_propagation(self):
        from src.io.independent_tetra_reference import load_tetra_reference
        from src.runners.port_preparation import preparation_memory_envelope,context,storage_limits
        for role,plan,stop in [('PREFLIGHT',64,96),('P6',192,256),('L4',128,192),('VERIFY_COST',64,96)]:
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'case.dat';p.write_text(f'schema_version=1\n[task042_v64]\nstage="{role}"\nrun_id="task042_v64_test"\n')
                r=load_tetra_reference(p,scope_module=scope)
            self.assertEqual(r.execution['planning_memory_gib'],plan);self.assertEqual(r.execution['terminate_memory_gib'],stop)
            self.assertEqual(r.boundary['complete_modes'],828)
            with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2048*2**30,reserve_bytes=0,system_reserve_bytes=128*2**30)):
                e=preparation_memory_envelope('v64',role)
            self.assertEqual(e['planning_cap_bytes'],plan*2**30);self.assertEqual(e['launch_cap_bytes'],stop*2**30)
        self.assertIs(context('v64')[0],scope.window)
        self.assertEqual(storage_limits('v64')['task_storage_bytes'],280*2**30)
        p6=scope.case_spec('P6');self.assertEqual((p6['degree'],p6['rows'],p6['assembly_row_cap']),(6,981180,1000000))
        import basix
        e=basix.create_element(basix.ElementFamily.N1E,basix.CellType.tetrahedron,6,basix.LagrangeVariant.legendre)
        self.assertEqual(e.dim,216);self.assertEqual(e.embedded_superdegree,6)

    def test_real_refinement_parent_composition_saved_mesh_and_MPC(self):
        from mpi4py import MPI
        from dolfinx import mesh as dm
        from src.solvers.independent_tetra_reference import configuration,make_setup
        from src.geometry.mesh_builder_3d import _structured_tet_mesh_from_axes,_mark_cells,_mark_boundary_facets,AirBox3DMesh
        from src.adaptivity.periodic_tetra_refinement import refine_periodic_marked_tetra_mesh
        from src.solvers.scattering_anchor import save_arrays
        from types import SimpleNamespace
        from contextlib import nullcontext
        from src.solvers.tetra_mesh_override import load_mesh
        physical=scope.physical_for('P6');cfg=configuration(dict(case='FLAT',degree=2,complete_modes=828),physical)
        m=_structured_tet_mesh_from_axes(MPI.COMM_SELF,np.array([0,cfg.period_x/2,cfg.period_x]),np.array([0,cfg.period_y/2,cfg.period_y]),np.array([cfg.z_min,0,cfg.z_max]))
        tags=_mark_cells(m,cfg);facets,boundary=_mark_boundary_facets(m,cfg)
        template=AirBox3DMesh(m,tags,facets,boundary,'tetrahedron',(2,2,2),[],'test',{}, {},{})
        refined,report=refine_periodic_marked_tetra_mesh(template,cfg,[3],full_boundary_synchronization=False,return_parent_map=True)
        self.assertFalse(report['periodic_edge_closure']['full_periodic_boundary_synchronization'])
        parent=report['original_parent_cells'];self.assertEqual(len(parent),refined.mesh.topology.index_map(3).size_local)
        def volumes(mesh):
            x=mesh.geometry.x[mesh.geometry.dofmap];return np.abs(np.linalg.det(np.transpose(x[:,1:]-x[:,:1],(0,2,1))))/6
        np.testing.assert_allclose(np.bincount(parent,weights=volumes(refined.mesh),minlength=len(volumes(m))),volumes(m),rtol=1e-12,atol=1e-13)
        with tempfile.TemporaryDirectory() as td:
            f=Path(td);idx=np.arange(len(parent),dtype=np.int32);mid=dm.compute_midpoints(refined.mesh,3,idx)
            values=np.where(mid[:,2]>0,cfg.tags.air,cfg.tags.substrate).astype(np.int32)
            r=save_arrays(f/'mesh.npz',geometry_x=refined.mesh.geometry.x,geometry_dofmap=refined.mesh.geometry.dofmap,
                cell_tags=values,regular_tags=values,original_parent_cell=parent)
            m1,t1,_,p1,reg1=load_mesh(r,cfg);m2,t2,_,p2,reg2=load_mesh(r,cfg)
            np.testing.assert_array_equal(m1.geometry.x,m2.geometry.x);np.testing.assert_array_equal(m1.geometry.dofmap,m2.geometry.dofmap)
            np.testing.assert_array_equal(p1,p2);np.testing.assert_array_equal(t1.values,t2.values);np.testing.assert_array_equal(reg1,reg2)
            # A separate full periodic mesh exercises the real setup override,
            # without depending on any current campaign clock or doing a PDE.
            idx=np.arange(len(volumes(m)),dtype=np.int32);mid=dm.compute_midpoints(m,3,idx);values=np.where(mid[:,2]>0,cfg.tags.air,cfg.tags.substrate).astype(np.int32)
            r=save_arrays(f/'periodic.npz',geometry_x=m.geometry.x,geometry_dofmap=m.geometry.dofmap,
                cell_tags=values,regular_tags=values,original_parent_cell=np.arange(len(values)))
            spec=dict(case='FLAT',degree=2,h_ratio=1,cells=len(values),independent=None,rows=None,complete_modes=828,mesh_override=r,notch_tetrahedra=0)
            s=make_setup(spec,physical,SimpleNamespace(measured=lambda _:nullcontext()))
            self.assertEqual(s['spec']['degree'],2);self.assertEqual(len(s['geometry']['original_parent_cell']),len(values))
            self.assertLess(s['P'].shape[1],s['P'].shape[0])
            self.assertFalse(np.array_equal(s['geometry']['geometry_x'],scope.physical_for('P6')['geometry']['axes_nm']['x']))
            data=(f/'periodic.npz').read_bytes();(f/'periodic.npz').write_bytes(data[:-2])
            with self.assertRaises(ValueError):load_mesh(r,cfg)

    def test_L4_shape_refusal_never_blocks_P6_and_no_other_p(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with patch.object(scope,'ARTIFACT',root),patch.object(scope.window,'TMP',root),patch.object(scope,'stage',return_value=dict(pass_gate=True,local_mesh=dict(admitted=False))),patch.object(scope.window,'available_at_boundary',return_value=40000):
                scope.require_stage('P6')
                with self.assertRaisesRegex(RuntimeError,'local mesh'):scope.require_stage('L4')
                with self.assertRaisesRegex(ValueError,'inventory'):scope.require_stage('TC6')


if __name__=='__main__':unittest.main()
