"""Actual affine-hex topology/material audit against the independent plan."""
from __future__ import annotations


def audit_sixlayer_mesh(mesh_data,plan):
    from hashlib import sha256
    import basix
    import numpy as np
    from .sixlayer_block import cell_material_at
    msh=mesh_data.mesh
    if msh.comm.size!=1:raise ValueError("sixlayer mesh qualification requires MPI1")
    count=int(msh.topology.index_map(3).size_local)
    if count!=plan["cells"]:raise ValueError("actual cell count differs from declared plan")
    tags={int(i):int(t) for i,t in zip(mesh_data.cell_tags.indices,mesh_data.cell_tags.values,strict=True)}
    if set(tags)!=set(range(count)):raise ValueError("each cell must have exactly one actual material tag")
    reference=np.asarray(basix.geometry(basix.CellType.hexahedron),dtype=float)
    design=np.column_stack((np.ones(8),reference))
    volumes={name:0.0 for name in plan["expected_region_volumes_nm3"]}
    counts={name:0 for name in volumes};minimum=float("inf");max_fit=0.0
    for cell in range(count):
        coords=np.asarray(msh.geometry.x[msh.geometry.dofmap[cell],:3])
        if coords.shape!=(8,3):raise ValueError("affine eight-node hex required")
        affine=np.linalg.lstsq(design,coords,rcond=None)[0]
        defect=float(np.max(np.abs(design@affine-coords)))
        jacobian=float(np.linalg.det(affine[1:,:]))
        if not np.isfinite(jacobian) or jacobian<=0 or defect>1e-12:
            raise ValueError("nonpositive/nonaffine actual hex Jacobian")
        name,expected=cell_material_at(*np.mean(coords,axis=0),plan)
        if tags[cell]!=expected:raise ValueError("actual material differs from independent midpoint geometry")
        volumes[name]+=jacobian;counts[name]+=1;minimum=min(minimum,jacobian);max_fit=max(max_fit,defect)
    for name,expected in plan["expected_region_volumes_nm3"].items():
        if counts[name]<=0 or abs(volumes[name]-expected)>1e-11*max(1.0,expected):
            raise ValueError("actual material volume mismatch: "+name)
    coordinates=np.asarray(msh.geometry.x[:,:3])
    periodic={}
    for axis in (0,1):
        other=[j for j in range(3) if j!=axis]
        faces=[]
        for side in (0.0,2.5):
            rows=coordinates[np.isclose(coordinates[:,axis],side,rtol=0,atol=1e-12)][:,other]
            faces.append(sorted(set(tuple(float(x) for x in row) for row in rows)))
        if not faces[0] or faces[0]!=faces[1]:raise ValueError("periodic opposite mesh faces do not match")
        periodic["xy"[axis]]={"matching":True,"face_vertices":len(faces[0])}
    return {"schema":"sixlayer-actual-mesh-audit.v1","passed":True,"cells":count,
            "region_volumes_nm3":volumes,"region_cell_counts":counts,
            "minimum_Jacobian_determinant":minimum,"max_affine_coordinate_defect":max_fit,
            "periodic_opposite_faces":periodic,
            "coordinates_sha256":sha256(np.ascontiguousarray(coordinates,dtype="<f8").view(np.uint8)).hexdigest(),
            "geometry_dofmap_sha256":sha256(np.ascontiguousarray(msh.geometry.dofmap,dtype="<i4").view(np.uint8)).hexdigest(),
            "tags_sha256":sha256(np.asarray([tags[i] for i in range(count)],dtype="<i4").view(np.uint8)).hexdigest()}
