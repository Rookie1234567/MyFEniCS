"""Exact reachable master support; no magnitude or mathematical-zero dropping."""
import numpy as np


def reachable_support(cell_dofs,cells,maps):
    values=[]
    for cell in cells:
        for row in cell_dofs(int(cell)):
            values.extend(maps[int(row)][0])
    return np.unique(np.asarray(values,dtype=np.int64))


def compact_index(rows,native):
    rows=np.asarray(rows,dtype=np.int64)
    if len(rows)!=len(np.unique(rows)) or np.any(rows<0) or np.any(rows>=native):raise ValueError('boundary support inventory')
    index=np.full(native,-1,np.int64);index[rows]=np.arange(len(rows))
    return index


def support_row(index,master):
    if master<0 or master>=len(index) or index[master]<0:raise ValueError('boundary write outside proved owner/MPC support')
    return int(index[master])


def side_supports(setup):
    from .target_boundary_witness import dual_maps
    V=setup['V'];mesh=setup['mesh'];mesh.topology.create_connectivity(2,3)
    fc=mesh.topology.connectivity(2,3);maps=dual_maps(V,setup['floquet'].mpc)
    return {side:reachable_support(V.dofmap.cell_dofs,[int(fc.links(int(f))[0]) for f in setup['data'].facet_tags.find(tag)],maps)
        for side,tag in (('top',setup['cfg'].tags.z_max),('bottom',setup['cfg'].tags.z_min))}
