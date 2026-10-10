"""Stable same-space field subtraction; no PDE assembly or solve."""
import basix
import numpy as np
import pytest
from mpi4py import MPI
from dolfinx import fem,mesh
from basix.ufl import element
from src.solvers.independent_tetra_reference import TetraEvaluator,CachedTetraEvaluator
from src.solvers.tetra_polynomial_difference import same_native_difference


def test_coefficient_first_preserves_complex_phase_curl_and_rejects_other_basis():
    m=mesh.create_unit_cube(MPI.COMM_SELF,1,1,1,cell_type=mesh.CellType.tetrahedron)
    V=fem.functionspace(m,element('N1curl',basix.CellType.tetrahedron,5))
    f,g=fem.Function(V),fem.Function(V)
    j=np.arange(len(f.x.array));f.x.array[:]=np.sin(j)+1j*np.cos(j)
    g.x.array[:]=f.x.array+1e-10*(np.cos(j*.13)+1j*np.sin(j*.19))
    delta=same_native_difference(f,g);kappa=np.array([8.94,.78,0.])
    direct=TetraEvaluator(V,31,kappa);cached=CachedTetraEvaluator(V,13,kappa)
    points,weights,values=direct.cell(delta,0,8.97)
    actual=cached.at(delta,0,points,8.97)
    for key in ('E','H','curl'):
        expected=np.sum(weights[:,None]*np.abs(values[key])**2)
        got=np.sum(weights[:,None]*np.abs(actual[key])**2)
        assert abs(got-expected)/expected<2e-6
    assert np.array_equal(delta.x.array,g.x.array-f.x.array)
    W=fem.functionspace(m,element('N1curl',basix.CellType.tetrahedron,4))
    with pytest.raises(ValueError,match='identical native basis'):
        same_native_difference(f,fem.Function(W))
