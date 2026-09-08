"""Explicit midpoint material edit on the existing mesh; no remeshing."""
import numpy as np


def apply_cell_notch(midpoints, tags, cfg):
    if cfg.cell_notch != 'positive_x_middle_y_z40_80':
        raise ValueError('unknown cell notch recipe')
    x, y, z = np.asarray(midpoints).T
    selected = ((tags == cfg.tags.grating) & (x > 0) &
                (np.abs(y) < cfg.period_y/4) & (z >= 40) & (z < 80))
    result = np.array(tags, copy=True)
    result[selected] = cfg.tags.air
    return result


def audit_cell_notch(mesh_data, cfg):
    """Record actual canonical cells and require both y and z variation."""
    import hashlib
    import json
    from dolfinx import mesh
    msh = mesh_data.mesh
    cells = mesh_data.cell_tags.indices
    centers = mesh.compute_midpoints(msh,msh.topology.dim,cells)
    tags = mesh_data.cell_tags.values
    x,y,z=centers.T
    block = ((x>=cfg.grating_x_min)&(x<=cfg.grating_x_max)&
             (y>=cfg.grating_y_min)&(y<=cfg.grating_y_max)&
             (z>=cfg.grating_z_min)&(z<=cfg.grating_z_max))
    changed=block&(x>0)&(np.abs(y)<cfg.period_y/4)&(z>=40)&(z<80)
    if not np.any(changed) or not np.all(tags[changed]==cfg.tags.air):
        raise ValueError('notch selector empty or actual tags disagree')
    def varies(axis):
        groups={}
        for point,tag in zip(centers[block],tags[block]):
            key=tuple(np.round(np.delete(point,axis),10))
            groups.setdefault(key,set()).add(int(tag))
        return any(len(v)>1 for v in groups.values())
    yvar,zvar=varies(1),varies(2)
    if not (yvar and zvar):
        raise ValueError('notch does not break both y and z material invariance')
    rows=[]
    for cell,center,tag,edited in zip(cells,centers,tags,changed):
        vertices=sorted(map(list,msh.geometry.x[msh.geometry.dofmap[cell]].tolist()))
        rows.append(dict(vertices=vertices,center=center.tolist(),tag=int(tag),changed=bool(edited)))
    rows.sort(key=lambda row:row['vertices'])
    return dict(recipe=cfg.cell_notch,changed_cells=int(changed.sum()),
                y_nonseparable=yvar,z_nonseparable=zvar,canonical_cells=rows,
                canonical_material_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
