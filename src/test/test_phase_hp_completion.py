"""Only V53 budget wiring, p7 inventory and exact cache isolation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from src.solvers import phase_hp_completion_scope as scope
from src.solvers.phase_explicit_accuracy_capacity import numeric_plan
from src.io.phase_notch_hp import descriptor,load_phase_notch_hp
from src.solvers.phase_evaluation_cache import ExactTabulations


class CompletionTests(unittest.TestCase):
    def test_old_hp_scalar_planning_and_real_namespace(self):
        p=scope.plan_record();old=json.loads((scope.ROOT/p['old_hp_symbolic_record']).read_text())
        self.assertFalse(numeric_plan(old['tree']['rss_bytes'],old['info'])['admitted'])
        self.assertTrue(numeric_plan(old['tree']['rss_bytes'],old['info'],32*2**30)['admitted'])
        self.assertFalse(numeric_plan(32*2**30,old['info'],32*2**30)['admitted'])
        self.assertEqual(numeric_plan(old['tree']['rss_bytes'],old['info'],32*2**30)['planned_simultaneous_bytes'],22783656448)
        from src.runners.port_preparation import context,storage_limits,preparation_memory_envelope
        self.assertEqual(context('v53')[0].label,'V53')
        self.assertEqual(storage_limits('v53')['task_storage_bytes'],58*2**30)
        with patch('src.runners.port_preparation.shared_envelope',return_value=dict(effective_available_bytes=2*1024*2**30,effective_total_bytes=2*1024*2**30,system_reserve_bytes=205*2**30,reserve_bytes=(205+128)*2**30)):
            r=preparation_memory_envelope('v53')
            self.assertEqual(r['launch_cap_bytes'],48*2**30);self.assertEqual(r['planning_cap_bytes'],32*2**30)
            self.assertEqual(r['reserve_bytes'],(205+384)*2**30)

    def test_actual_cases_and_all_dat(self):
        for role,degree,rows,cells in (('A',6,65044,320),('B',7,45780,160),('M',6,33660,160)):
            d,s=descriptor(role,scope=scope)
            self.assertEqual(d['discretization']['degree'],degree)
            self.assertEqual(d['discretization']['condensed_rows'],rows)
            self.assertEqual(int(np.prod([len(a)-1 for a in d['geometry']['axes_nm'].values()])),cells)
        rows=[load_phase_notch_hp(p,scope=scope) for p in (scope.ROOT/'input/task042_neural_coarse_inverse').glob('v53_*.dat')]
        self.assertEqual({s.derived['stage'] for s in rows},set(scope.STAGES))
        for s in rows:
            self.assertEqual([s.execution[k] for k in ('planning_memory_gib','warning_memory_gib','terminate_memory_gib')],[32,40,48])
            self.assertEqual(s.derived['preparation_scope'],'v53')
        old=load_phase_notch_hp(scope.ROOT/'input/task042_neural_coarse_inverse/v52_notch_z4_p6.dat')
        self.assertEqual(old.execution['terminate_memory_gib'],24)

    def test_p7_basis_is_not_p6(self):
        import basix
        e=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,7,basix.LagrangeVariant.legendre)
        self.assertEqual(e.dim,1344);self.assertEqual(len(e.entity_dofs[3][0]),756)
        from src.constraints.floquet_3d import _qualified_constraint_mode
        with self.assertRaises(NotImplementedError):_qualified_constraint_mode(7,fixed_target_high_order=True)
        self.assertEqual(_qualified_constraint_mode(7,fixed_target_high_order=True,finite_authority_degree7=True),'topological_trace_p7')
        from src.constraints.high_order_floquet_trace import high_order_trace_layout,edge_coefficient_transform,face_basis_transform
        layout=high_order_trace_layout(7);self.assertEqual(layout.cell_interior_dofs,756)
        edge=edge_coefficient_transform(7,reversed_orientation=True)
        self.assertLess(np.linalg.norm(edge@edge-np.eye(7)),1e-11)
        for flag in (1,2):
            transform=face_basis_transform(7,flag)
            power=2 if flag==1 else 4
            self.assertLess(np.linalg.norm(np.linalg.matrix_power(transform,power)-np.eye(84)),1e-11)

    def test_exact_points_and_lru_capacity(self):
        class Element:
            def tabulate(self,d,p):return np.tile(np.asarray(p)[:,None,:],(4,1,2,1))
        e=Element();cache=ExactTabulations(limit_bytes=400);p=np.array([[.25,.5,.75]])
        a=cache.get(e,p);b=cache.get(e,p.copy());self.assertIs(a,b)
        self.assertFalse(a[0].flags.writeable)
        changed=p.copy();changed[0,0]=np.nextafter(changed[0,0],1.)
        cache.get(e,changed);self.assertEqual(cache.hits,1);self.assertEqual(cache.misses,2)
        cache.get(Element(),p);self.assertEqual(cache.misses,3);self.assertLessEqual(cache.bytes,400)

    def test_factor_constructor_uses_declared_limit(self):
        from src.solvers.phase_explicit_accuracy_capacity import AnalyzedDirectFactor
        class J:
            from contextlib import nullcontext
            def measured(self,n):return self.nullcontext()
            def event(self,*a,**k):pass
        class F:
            preferred_ordering='unchanged'
            def __init__(self,m):pass
            def symbolic(self,m):pass
            def info(self):return dict(infog={'16':6948,'17':6948})
            def symbolic_memory_settings(self):return dict(icntl={'22':0})
            def set_memory_limit_mb(self,mb):self.mb=mb
            def numeric(self,m):self.numeric_called=True
            def destroy(self):pass
        with tempfile.TemporaryDirectory(dir=scope.window.TMP) as d,patch.dict('os.environ',TASK042_WATCHDOG_PARENT_PID='1'),\
            patch('src.solvers.fullspace_v17_p3_oracle._MumpsFactor',F),\
            patch('benchmarks.task038_full3d_jit_staging.process_tree_snapshot',return_value=dict(rss_bytes=6740172800,swap_bytes=0)):
            f=AnalyzedDirectFactor(None,J(),Path(d),planning_limit_bytes=32*2**30)
            self.assertTrue(f.factor.numeric_called);self.assertEqual(f.factor.mb,13896)
            self.assertEqual(json.loads((Path(d)/'h_symbolic_capacity.json').read_text())['plan']['limit_bytes'],32*2**30)
            with self.assertRaises(MemoryError):AnalyzedDirectFactor(None,J(),Path(d),planning_limit_bytes=16*2**30)

    def test_actual_incremental_collector_namespace_writer(self):
        from benchmarks.collect_phase_notch_hp import collect
        from src.runners.task042_shared import write_json
        with tempfile.TemporaryDirectory(dir=scope.window.TMP) as d:
            root=Path(d);artifact=root/'artifact';artifact.mkdir();aux=root/'aux';aux.mkdir()
            write_json(root/'decision.json',dict(status='FIXTURE_NO_SOLVE'))
            live=SimpleNamespace(TMP=root,guard_worker_parent=lambda:None,ledger=lambda:dict(runs=[]),
                charged_wall=lambda:0.,snapshot=lambda:dict(fixture=True))
            fixture=SimpleNamespace(window=live,ARTIFACT=artifact,STAGES=(),SOLVES=(),NAMESPACE='v53',
                stage=lambda r:None,plan_record=scope.plan_record,parent=lambda r:dict(status='read_only_fixture'))
            with patch.dict('os.environ',TASK042_V36_AUX_DIRECTORY=str(aux)):
                collect(scope=fixture)
            receipt=json.loads((aux/'records/hp_accuracy_checks_v53.json').read_text())
            self.assertFalse(receipt['target_qualified'])
            self.assertFalse((aux/'records/hp_accuracy_checks_v52.json').exists())


if __name__=='__main__':unittest.main()
