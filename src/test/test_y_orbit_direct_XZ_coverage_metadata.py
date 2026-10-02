"""Execute production coverage predicates/orbit control flow on saved actual metadata.
The separate supervised replay checks every original numeric cell and q sum.
These focused tests never create a FE mesh, form, factor or PDE solution.
"""
from pathlib import Path
import ast,copy,json,unittest
import numpy as np
from src.solvers import y_orbit_direct_operator_qualification as production
from src.solvers.y_orbit_direct_profile import direct_profile_metadata

ROOT=Path(__file__).parents[2]
PACKET=ROOT.parent/'experiments/y_orbit_XZ_coverage_diagnostics/attempt2_complete_primitives.json'
SOURCE=ROOT/'src/solvers/y_orbit_direct_operator_qualification.py'

def coverage_gate():
    tree=ast.parse(SOURCE.read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_check_source')
    statement=next(n for n in function.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
        and any(isinstance(x,ast.Constant) and x.value=='complete actual cell/grid/interior coverage is not exhaustive' for x in n.value.args))
    namespace={'_require':production._require,'INTERIOR_DIMENSION':108}
    def run(source,metadata):
        cells=source['cells'];namespace.update(metadata=metadata,expected_cells=metadata.local_cell_count if source['local_two_cell'] else metadata.cell_count,
            ny=2 if source['local_two_cell'] else 4,seen_cells={c['cell_index'] for c in cells},seen_grid={tuple(c['grid']) for c in cells},
            seen_interiors=set(range(len(cells)*108)))
        exec(compile(ast.Module(body=[statement],type_ignores=[]),str(SOURCE),'exec'),namespace)
    return run

def orbit_flow(receipt,metadata):
    # Execute the complete production grouping/pair-validation control flow;
    # q matrix products themselves are independently recomputed by full replay.
    def pair_sums(source,cells,etas,**kw):
        if not cells:raise ValueError('missing actual orbit')
        zero=np.zeros((1,1),dtype=complex);one=np.ones((1,1),dtype=complex)
        return [0],{(p,q):one.copy() if p==q else zero.copy() for p in range(len(etas)) for q in range(len(etas))}
    old=production._orbit_pair_sums
    production._orbit_pair_sums=pair_sums
    try:return production._check_orbits(receipt,load=None,gate=None,metadata=metadata)
    finally:production._orbit_pair_sums=old

@unittest.skipUnless(PACKET.exists(),'actual scaled-XZ evidence packet absent; public replay is a separate qualification')
class ActualSavedXZCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.receipt=json.loads(PACKET.read_text());cls.metadata=direct_profile_metadata('XZ')

    def test_all_actual_global_and_both_local_ID_grid_coverage(self):
        gate=coverage_gate()
        for source in [self.receipt['global_source'],*self.receipt['local_sources']]:gate(source,self.metadata)
        self.assertEqual([s['cell_count'] for s in [self.receipt['global_source'],*self.receipt['local_sources']]],[168,84,84])

    def test_production_orbit_flow_visits_all42_groups_and16_8_pairs(self):
        result=orbit_flow(self.receipt,self.metadata);self.assertEqual(len(result),42)
        self.assertEqual(sum(len(r['all_global_q_pairs']) for r in result),42*16)
        self.assertEqual(sum(len(t['all2x2_pairs']) for r in result for t in r['local_twists']),42*8)

    def test_missing_orbit_duplicate_or_swapped_grid_is_rejected(self):
        gate=coverage_gate()
        for kind in ('missing','duplicate','swapped'):
            source=copy.deepcopy(self.receipt['global_source'])
            if kind=='missing':source['cells']=[c for c in source['cells'] if c['grid'][0:3:2]!=[5,6]]
            elif kind=='duplicate':source['cells'][-1]=copy.deepcopy(source['cells'][-2])
            else:source['cells'][-1]['grid'][0],source['cells'][-1]['grid'][2]=source['cells'][-1]['grid'][2],source['cells'][-1]['grid'][0]
            with self.subTest(kind=kind),self.assertRaises(ValueError):gate(source,self.metadata)
        wrong=copy.deepcopy(self.receipt);wrong['local_sources'][1]['cells']=[c for c in wrong['local_sources'][1]['cells'] if c['grid'][0:3:2]!=[5,6]]
        with self.assertRaises(ValueError):orbit_flow(wrong,self.metadata)

    def test_X30_grid_branch_remains_and_XZ_cannot_pass_as_X(self):
        x=direct_profile_metadata('X');gate=coverage_gate();subset=copy.deepcopy(self.receipt)
        for source in [subset['global_source'],*subset['local_sources']]:
            source['cells']=[c for c in source['cells'] if c['grid'][2]<5]
            for i,c in enumerate(source['cells']):c['cell_index']=i
            gate(source,x)
        self.assertEqual(len(orbit_flow(subset,x)),30)
        with self.assertRaises(ValueError):gate(self.receipt['global_source'],x)

    def test_wrong_actual_axes_and_swapped_profile_source_rejected_before_numeric_load(self):
        source=copy.deepcopy(self.receipt['global_source']);source['axes'][2][1],source['axes'][2][2]=source['axes'][2][2],source['axes'][2][1]
        with self.assertRaisesRegex(ValueError,'cardinalities'):
            production._check_source(source,load=None,gate=None,metadata=self.metadata)
        with self.assertRaisesRegex(ValueError,'cardinalities'):
            production._check_source(self.receipt['global_source'],load=None,gate=None,metadata=direct_profile_metadata('X'))

if __name__=='__main__':unittest.main()
