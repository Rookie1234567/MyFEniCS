"""Execute production interior helpers against complete real Basix metadata."""
from pathlib import Path
from types import SimpleNamespace
import ast,unittest
import numpy as np
import basix
from src.solvers.y_orbit_centered_evidence import fixture_interior_positions,interior_only_rhs
from src.solvers.y_orbit_direct_profile import direct_profile_metadata

ROOT=Path(__file__).resolve().parents[2]

def metadata_space(degree,cells,full_rows,independent=None,interior_rows=None):
    element=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,degree,lagrange_variant=basix.LagrangeVariant.legendre)
    local=np.asarray(element.entity_dofs[3][0],dtype=np.int64)
    rows=np.arange(len(local)*cells,dtype=np.int64) if interior_rows is None else np.asarray(interior_rows,dtype=np.int64)
    if rows.shape!=(cells*len(local),):raise ValueError('complete interior metadata required')
    # Only the exact original interior gather is used by the production helper.
    # This view does not construct a mesh, FE space, forms, matrix or solution.
    def dofs(cell):
        values=np.zeros(element.dim,dtype=np.int64);values[local]=rows[cell*len(local):(cell+1)*len(local)];return values
    topology=SimpleNamespace(index_map=lambda dim:SimpleNamespace(size_local=cells))
    space=SimpleNamespace(element=SimpleNamespace(basix_element=element),dofmap=SimpleNamespace(cell_dofs=dofs),mesh=SimpleNamespace(topology=topology))
    layout=SimpleNamespace(full_rows=full_rows,independent=np.arange(full_rows) if independent is None else np.asarray(independent))
    return space,layout

class ProductionInteriorProfileTests(unittest.TestCase):
    def test_actual_X_and_XZ_Basix_interior_branches_and_complete_load(self):
        for name,expected in [('X',12960),('XZ',18144)]:
            m=direct_profile_metadata(name);s,l=metadata_space(4,m.cell_count,m.storage_rows)
            positions=fixture_interior_positions(s,l,direct_profile=name)
            self.assertEqual(len(positions),expected);self.assertEqual(len(np.unique(positions)),expected)
            rhs=interior_only_rhs(s,l,direct_profile=name)
            self.assertEqual(np.count_nonzero(rhs),expected);self.assertAlmostEqual(float(np.linalg.norm(rhs)),1.)

    def test_ordinary_p2_p4_None_metadata_branches_unchanged(self):
        for degree,expected in [(2,480),(4,8640)]:
            s,l=metadata_space(degree,80,2394 if degree==2 else 17204)
            self.assertEqual(len(fixture_interior_positions(s,l)),expected)

    def test_Y_unknown_wrong_degree_rows_missing_or_duplicate_interior_rejected(self):
        m=direct_profile_metadata('XZ');s,l=metadata_space(4,m.cell_count,m.storage_rows)
        for name in ('Y','other'):
            with self.assertRaises(ValueError):fixture_interior_positions(s,l,direct_profile=name)
        for degree in (2,6):
            wrong,layout=metadata_space(degree,m.cell_count,max(m.storage_rows,3*degree*(degree-1)**2*m.cell_count))
            with self.assertRaises(ValueError):fixture_interior_positions(wrong,layout,direct_profile='XZ')
        with self.assertRaises(ValueError):fixture_interior_positions(s,SimpleNamespace(full_rows=m.storage_rows-1,independent=l.independent),direct_profile='XZ')
        wrong,layout=metadata_space(4,m.cell_count-1,m.storage_rows)
        with self.assertRaises(ValueError):fixture_interior_positions(wrong,layout,direct_profile='XZ')
        rows=np.arange(m.interior_rows);rows[-1]=rows[-2];wrong,layout=metadata_space(4,m.cell_count,m.storage_rows,interior_rows=rows)
        with self.assertRaises(ValueError):fixture_interior_positions(wrong,layout,direct_profile='XZ')

    def test_production_source_change_is_exact_profile_enum_and_message_only(self):
        text=(ROOT/'src/solvers/y_orbit_centered_evidence.py').read_text()
        self.assertEqual(text.count("profile.name not in ('X','XZ') or degree!=4 or layout.full_rows!=profile.storage_rows"),1)
        tree=ast.parse(text);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='fixture_interior_positions')
        body=ast.unparse(fn);self.assertIn('profile.interior_rows',body);self.assertIn('len(rows) != expected',body);self.assertIn('len(positions) != expected',body)

if __name__=='__main__':unittest.main()
