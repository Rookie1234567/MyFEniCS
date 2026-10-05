"""Focused opt-in, physical identity and independent algebra regressions."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from src.io.scattering_accuracy import load_scattering_accuracy
from src.io.input_loader import InputError
from src.solvers.scattering_accuracy_scope import ROOT, STAGES, SOLVES, plan_record
from src.solvers.scattering_accuracy import configuration
from src.solvers.scattering_accuracy_boundary import pack_carrier, carrier_pair
from types import SimpleNamespace


class AccuracyTests(unittest.TestCase):
    def test_all_one_run_entries_are_registered(self):
        paths=list((ROOT/'input/task042_neural_coarse_inverse').glob('v50_*.dat'))
        specs=[load_scattering_accuracy(p) for p in paths]
        self.assertEqual({s.derived['stage'] for s in specs},set(STAGES))
        self.assertEqual(len(specs),len(STAGES))
        self.assertEqual(len(SOLVES),5)
        for s in specs:
            self.assertEqual(s.derived['preparation_scope'],'v50')
            self.assertEqual(s.execution['terminate_memory_gib'],24)
            self.assertEqual(s.boundary,load_scattering_accuracy(paths[0]).boundary)

    def test_invalid_inventory_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.dat'
            p.write_text('schema_version=1\n[task042_v50]\nstage="FLAT_P7"\nrun_id="task042_v50_bad"\n')
            with self.assertRaises(InputError):load_scattering_accuracy(p)

    def test_actual_material_alias_and_fixed_physics(self):
        c=configuration('FLAT',5)
        self.assertEqual(c.n_substrate,.999885140474+4.32477054e-6j)
        self.assertEqual(c.lambda0,.7);self.assertEqual(c.stage4_dtn_quadrature_degree,47)
        self.assertEqual((c.diffraction_order_max_m,c.diffraction_order_max_n),(9,3))
        from src.common.analytic_fields_3d import fresnel_reference
        self.assertAlmostEqual(fresnel_reference(c)['R'],.11343340891957432,delta=1e-11)

    def test_x2_preserves_original_domain_and_material_breaks(self):
        a=configuration('NOTCH',5);b=configuration('NOTCH',6,'X2')
        self.assertEqual(b.mesh_axis_x_values[::2],a.mesh_axis_x_values)
        self.assertEqual(b.mesh_axis_y_values,a.mesh_axis_y_values)
        self.assertEqual(b.mesh_axis_z_values,a.mesh_axis_z_values)
        with self.assertRaises(ValueError):configuration('NOTCH',7)

    def test_frozen_live_window_storage_limits(self):
        from src.runners.port_preparation import storage_limits,context
        p=plan_record();limits=storage_limits('v50')
        self.assertEqual(limits['task_storage_bytes'],32*2**30)
        self.assertEqual(limits['new_storage_bytes'],4*2**30)
        self.assertEqual(context('v50')[0].label,'V50')
        self.assertEqual(p['review_commit'],'da151228815b08126dc636d3e195673ba04fe45f')

    def test_live_storage_retains_immutable_baseline(self):
        from src.runners.port_preparation import PreparationHealth
        from unittest.mock import patch
        with self.assertRaises(ValueError):PreparationHealth(Path('/tmp'),[],'v50')
        h=PreparationHealth(Path('/tmp'),[],'v50',baseline_storage={'task_artifact_bytes':1000,'new_bytes':100})
        with patch.object(h,'own_bytes',return_value=130):self.assertEqual(h.live_task_bytes(),1030)

    def test_complex_nonmutual_full532_functionals(self):
        rng=np.random.default_rng(50);n=11
        entries=[];ids=[]
        for i in range(532):
            entries.append(SimpleNamespace(coupling_rows=np.arange(n),projection_rows=np.arange(n),
                coupling_values=rng.normal(size=n)+1j*rng.normal(size=n),
                projection_values=rng.normal(size=n)+1j*rng.normal(size=n),normalization_h=float(i+1)))
            ids.append(dict(mode_index=i,side='top',m=i,n=0,polarization='s'))
        c=SimpleNamespace(entries=entries)
        self.assertTrue(carrier_pair(c,c,ids)['pass'])
        packed=pack_carrier(c);self.assertEqual(len(packed['offsets']),533)
        A=sum(np.outer(e.coupling_values,e.projection_values)/e.normalization_h for e in entries)
        x=rng.normal(size=n)+1j*rng.normal(size=n)
        adjoint=sum(np.conj(e.projection_values)*np.vdot(e.coupling_values,x)/e.normalization_h for e in entries)
        self.assertLess(np.linalg.norm(adjoint-A.conj().T@x),1e-12)
        entries[0].coupling_values[0]+=.01
        old=SimpleNamespace(entries=[SimpleNamespace(**{k:getattr(e,k) for k in ('coupling_rows','projection_rows','normalization_h')},coupling_values=e.coupling_values.copy(),projection_values=e.projection_values.copy()) for e in entries])
        old.entries[0].coupling_values[0]-=.01
        self.assertFalse(carrier_pair(c,old,ids)['pass'])
        with self.assertRaises(ValueError):carrier_pair(SimpleNamespace(entries=[]),c,ids)

    def test_public_carrier_preserves_tiny_nonzero_components(self):
        # This needs the already qualified FE ABI, but constructs no mesh/form.
        from mpi4py import MPI
        from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory,build_fullspace_dtn_carrier_from_surface
        cfg=configuration('FLAT',5);modes,_,_=build_dynamic_mode_inventory(cfg)
        index=SimpleNamespace(local_range=(0,2),size_local=2,size_global=2,local_to_global=lambda x:np.asarray(x))
        mpc=SimpleNamespace(function_space=SimpleNamespace(mesh=SimpleNamespace(comm=MPI.COMM_SELF),dofmap=SimpleNamespace(index_map=index)),slaves=np.array([],np.int32))
        component=SimpleNamespace(assemble_entries=lambda mode,mpc:(np.array([0,1]),np.array([1e-120,2e-120],complex)))
        assemblers={(s,j):component for s in ('top','bottom') for j in (0,1)}
        raw=build_fullspace_dtn_carrier_from_surface(modes,assemblers,mpc,cfg,retain_all_nonzero=True)
        legacy=build_fullspace_dtn_carrier_from_surface(modes,assemblers,mpc,cfg)
        self.assertTrue(any(np.any(e.coupling_values!=0) for e in raw.entries))
        self.assertTrue(all(len(e.coupling_values)==0 for e in legacy.entries))

    def test_background_cross_terms_are_not_added_norms(self):
        rng=np.random.default_rng(50);t=rng.normal(size=31)+1j*rng.normal(size=31);b=rng.normal(size=31)+1j*rng.normal(size=31)
        cross=-2*np.vdot(t,b).real
        self.assertAlmostEqual(np.vdot(t-b,t-b).real,np.vdot(t,t).real+np.vdot(b,b).real+cross,11)

    def test_small_nonzero_reference_has_no_absolute_floor(self):
        from src.solvers.scattering_accuracy_checks import norm_pair
        self.assertTrue(norm_pair(np.array([1e-180]),np.array([1e-180]))['pass_gate'])
        self.assertFalse(norm_pair(np.array([2e-180]),np.array([1e-180]))['pass_gate'])
        self.assertEqual(norm_pair(np.array([2e-180]),np.array([1e-180]))['relative'],1.)

    def test_original_closed_window_not_required_by_parser(self):
        from unittest.mock import patch
        with patch('src.solvers.scattering_anchor_scope.window.require_live',side_effect=RuntimeError('closed')):
            self.assertEqual(load_scattering_accuracy(ROOT/'input/task042_neural_coarse_inverse/v50_boundary.dat').derived['stage'],'BOUNDARY')

    def test_alias_strings_and_no_new_training(self):
        p=plan_record()
        self.assertEqual(p['frozen_surface_q'],[47,63])
        self.assertEqual(p['complete_solve_cap'],5)
        table=json.loads((ROOT/'input/materials/si_optical_constants_v1.json').read_text())
        self.assertIn('0.699999988',json.dumps(table))


if __name__=='__main__':unittest.main()
