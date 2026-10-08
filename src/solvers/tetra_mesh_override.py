"""Hash-bound actual tetra connectivity and inherited labels, not uniform h metadata."""
import numpy as np


def load_mesh(receipt,cfg):
    from mpi4py import MPI
    from dolfinx import mesh as dm,default_real_type
    from basix.ufl import element
    import ufl
    from .scattering_anchor_checks import checked_arrays
    from src.geometry.mesh_builder_3d import _mark_boundary_facets
    a=checked_arrays(receipt)
    cells=np.asarray(a['geometry_dofmap'],np.int64);x=np.asarray(a['geometry_x'],float)
    if cells.ndim!=2 or cells.shape[1]!=4 or len(a['cell_tags'])!=len(cells):raise ValueError('actual saved tetra mesh inventory')
    domain=ufl.Mesh(element('Lagrange','tetrahedron',1,shape=(3,),dtype=default_real_type))
    msh=dm.create_mesh(MPI.COMM_SELF,cells,domain,x)
    original=np.asarray(msh.topology.original_cell_index,np.int64)
    if sorted(original.tolist())!=list(range(len(cells))):raise ValueError('mesh input cell permutation incomplete')
    tags=dm.meshtags(msh,3,np.arange(len(cells),dtype=np.int32),a['cell_tags'][original].astype(np.int32))
    facets,_=_mark_boundary_facets(msh,cfg)
    parent=a['original_parent_cell'][original]
    determinants=np.linalg.det(np.transpose(msh.geometry.x[msh.geometry.dofmap][:,1:]-msh.geometry.x[msh.geometry.dofmap][:,:1],(0,2,1)))
    if np.any(determinants<=0):raise ValueError('positive saved local tetra geometry')
    return msh,tags,facets,parent,a['regular_tags'][original]
