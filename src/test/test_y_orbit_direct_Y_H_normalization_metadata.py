"""Actual physical532 H formulas and exact protected-source seams; no FE/JIT/PDE."""
from pathlib import Path
from types import SimpleNamespace
import ast,copy,json,unittest
import numpy as np
from src.solvers.task40extra_y_orbit_reference import pilot_config
from src.solvers.y_orbit_direct_profile import build_direct_profile_config
from src.solvers.y_orbit_quotient_context import build_two_cell_assembly_config,build_two_cell_quotient_context
from src.common.modes_3d import outgoing_port_modes_3d
from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest
from src.solvers.dtn_boundary_phase_gauge import assembly_projection_denominator
from benchmarks.y_orbit_direct_source_contract import normalized_raw_observer_ast,RAW_OBSERVER_BASELINE_AST
ROOT=Path(__file__).parents[2]
SOURCE=ROOT/'src/solvers/fullspace_dtn_action.py'

_H_GATE_CODE=None

def production_H_gate(h,H,context):
    global _H_GATE_CODE
    if _H_GATE_CODE is not None:
        return exec(_H_GATE_CODE,{'np':np,'denominator':h,'global_h':H,'quotient_context':context})
    tree=ast.parse(SOURCE.read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_fullspace_dtn_carrier_from_surface')
    node=next(n for n in ast.walk(function) if isinstance(n,ast.If)
        and any(isinstance(x,ast.Raise) and isinstance(x.exc,ast.Call) and x.exc.args
        and isinstance(x.exc.args[0],ast.Constant) and x.exc.args[0].value=='quotient original plane H must equal global plane H / K' for x in n.body))
    _H_GATE_CODE=compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec')
    exec(_H_GATE_CODE,{'np':np,'denominator':h,'global_h':H,'quotient_context':context})

class ActualPhysicalHNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=pilot_config(ROOT/'input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat',azimuth_deg=5.)[0]

    def test_actual_all532_Y_sector_formulas_and_original_basis_role(self):
        cfg=build_direct_profile_config(self.base,'Y');local=build_two_cell_assembly_config(cfg,direct_profile='Y')
        modes=tuple(outgoing_port_modes_3d(cfg));rows,_,digest=build_ordered_mode_manifest(modes,cfg);inventory=(modes,rows,digest)
        seen=[];worst=0.
        for b,expected in enumerate((228,152,152)):
            ctx=build_two_cell_quotient_context(cfg,local,inventory,twist_index=b,direct_profile='Y')
            selected,_,_=ctx.select_inventory(cfg,local,inventory);self.assertEqual(len(selected),expected);self.assertEqual(ctx.replication_count,3)
            seen.extend(ctx.original_mode_indices)
            for mode in selected:
                h=assembly_projection_denominator(mode,local,'boundary_plane');H=assembly_projection_denominator(mode,cfg,'boundary_plane')
                production_H_gate(h,H,ctx);worst=max(worst,abs(3*h-H)/H)
                e=mode.e_vector;norm=float(sum(abs(complex(v))**2 for v in e[:2]));A=(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)
                self.assertTrue(np.isclose(A*norm,H,rtol=32*np.finfo(float).eps,atol=0))
                self.assertIn(mode.polarization,('s','p'));self.assertGreater(H,0)
                for K in (1,2,4):
                    with self.assertRaises(ValueError):production_H_gate(h,H,SimpleNamespace(replication_count=K))
                with self.assertRaises(ValueError):production_H_gate(h*1.000001,H,ctx)
        self.assertEqual(sorted(seen),list(range(532)));self.assertEqual(len(set(seen)),532)
        self.assertLessEqual(worst,32*np.finfo(float).eps)
        self.assertNotEqual(local.period_y,cfg.period_y/3)
        self.assertEqual(local.period_y,cfg.mesh_axis_y_values[2])

    def test_old_K2_actual_X_XZ_data_and_identity_remain(self):
        for name in ('X','XZ'):
            cfg=build_direct_profile_config(self.base,name);local=build_two_cell_assembly_config(cfg,direct_profile=name)
            for mode in outgoing_port_modes_3d(cfg):
                h=assembly_projection_denominator(mode,local,'boundary_plane');H=assembly_projection_denominator(mode,cfg,'boundary_plane')
                production_H_gate(h,H,SimpleNamespace(replication_count=2));self.assertEqual(1/2,0.5)

    def test_only_explicit_H_and_area_metadata_AST_exceptions_admitted(self):
        for name in ('fullspace_dtn_action.py','dtn_boundary_phase_gauge.py'):
            path='src/solvers/'+name;text=(ROOT/path).read_text()
            self.assertEqual(normalized_raw_observer_ast(path,text),RAW_OBSERVER_BASELINE_AST[path])
        text=SOURCE.read_text()
        for bad in ('denominator*4','denominator*2','denominator*quotient_context.replication_count*2'):
            wrong=text.replace('denominator*quotient_context.replication_count',bad)
            with self.assertRaises(ValueError):normalized_raw_observer_ast('src/solvers/fullspace_dtn_action.py',wrong)
        with self.assertRaises(ValueError):normalized_raw_observer_ast('src/solvers/fullspace_dtn_action.py',text.replace('1/quotient_context.replication_count','0.5'))
        area=(ROOT/'src/solvers/dtn_boundary_phase_gauge.py').read_text()
        with self.assertRaises(ValueError):normalized_raw_observer_ast('src/solvers/dtn_boundary_phase_gauge.py',area.replace('(cfg.y_max-cfg.y_min)*quotient_context.replication_count','(cfg.y_max-cfg.y_min)*4'))

if __name__=='__main__':unittest.main()
