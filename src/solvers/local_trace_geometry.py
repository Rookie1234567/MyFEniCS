"""Complete canonical edge/face entities on the one frozen FE mesh."""

import numpy as np

from src.solvers.local_trace_features import boxes,patch_ids


def canonical_entity_map(space,moments,mpc,design):
    from dolfinx import mesh
    topology=space.mesh.topology
    if not np.array_equal(space.dofmap.list,moments['native_cell_dofs']):
        raise ValueError('local geometry/native dof order differs from frozen packet')
    n=int(moments['active_rows']); rows=moments['owner_rows']
    if np.intersect1d(moments['master_native_rows'],mpc.slaves).size:
        raise ValueError('periodic slave is not an independent trace unknown')
    layout=space.element.basix_element.entity_dofs
    entity={};centers={};connectivity={}
    for dimension in (1,2):
        topology.create_connectivity(3,dimension)
        connectivity[dimension]=topology.connectivity(3,dimension)
        ids=np.arange(topology.index_map(dimension).size_local,dtype=np.int32)
        centers[dimension]=mesh.compute_midpoints(space.mesh,dimension,ids)
        for local_id,dofs in enumerate(layout[dimension]):
            for moment,position in enumerate(dofs):
                entity[position]=(dimension,local_id,moment)
    mapped=dict(row=np.arange(n,dtype=np.int64),entity_dim=np.empty(n,np.int64),
                entity_id=np.empty(n,np.int64),entity_moment=np.empty(n,np.int64),
                master_native=np.array(moments['master_native_rows'],np.int64),
                owner_cell=np.empty(n,np.int64),owner_position=np.empty(n,np.int64),
                orientation_id=np.empty(n,np.int64),physical_center=np.empty((n,3)))
    native_entities={};seen=np.zeros(n,np.int64)
    for cell,cell_dofs in enumerate(moments['native_cell_dofs']):
        for position,(dimension,local_id,moment) in entity.items():
            eid=int(connectivity[dimension].links(cell)[local_id])
            native=int(cell_dofs[position]); identity=(dimension,eid)
            old=native_entities.setdefault(native,identity)
            if old!=identity:raise ValueError('one native dof split over distinct entities')
            row=int(rows[cell,position])
            if row<0:continue
            seen[row]+=1
            for key,value in (('entity_dim',dimension),('entity_id',eid),
                              ('entity_moment',moment),('owner_cell',cell),
                              ('owner_position',position),
                              ('orientation_id',int(moments['orientation_ids'][cell]))):
                mapped[key][row]=value
            if native!=mapped['master_native'][row]:raise ValueError('master row order differs')
            mapped['physical_center'][row]=centers[dimension][eid]
    if not np.all(seen==1):raise ValueError('canonical trace missing/duplicated')
    mapped['patch_id'],mapped['periodic_representative_center']=patch_ids(mapped['physical_center'],design['geometry']['bounds_nm'])
    mapped['boxes']=boxes(design['geometry']['bounds_nm'])
    groups={}
    for d,e,p in zip(mapped['entity_dim'],mapped['entity_id'],mapped['patch_id'],strict=True):
        key=(int(d),int(e))
        if groups.setdefault(key,int(p))!=p:raise ValueError('high moments of entity split across patches')
    counts=np.bincount(mapped['patch_id'],minlength=8)
    if np.any(counts==0):raise ValueError('empty geometric patch')
    return mapped,dict(canonical_rows=n,patch_rows=counts.tolist(),complete_entity_count=len(groups),
        slaves_added=0,slave_rows=len(mpc.slaves),same_entity_moments_never_split=True,
        rule='canonical master complete edge/face center; cut ties lower; upper periodic center uses equivalent representative',
        native_integral_coordinates_unchanged=True,owner_used_only_for_original_moment_evaluation=True)


def independent_local_interpolation(moments,mapping,space,mpc,wavevector,weights,libraries):
    from basix import ufl as basix_ufl
    from dolfinx import fem
    from src.solvers.neural_trace_dolfinx import extended_moment_element
    from src.solvers.local_trace_features import extension_field,polynomial_features,numpy_hidden_features
    custom=extended_moment_element(space.element.basix_element,15)
    witness=fem.functionspace(space.mesh,basix_ufl.wrap_element(custom))
    if not np.array_equal(witness.dofmap.list,space.dofmap.list):raise ValueError('q15 interpolation reordered dofs')
    records=[]
    for family in ('POLY','NN'):
        scalar=polynomial_features if family=='POLY' else lambda x:numpy_hidden_features(x,weights)
        rng=np.random.default_rng(421503)
        coefficient=rng.standard_normal((3,65))+1j*rng.standard_normal((3,65))
        coefficient/=np.linalg.norm(coefficient)
        actual=np.zeros(int(moments['active_rows']),complex)
        expected=np.zeros_like(actual)
        for patch,box in enumerate(mapping['boxes']):
            field=fem.Function(witness)
            field.interpolate(lambda x,box=box:extension_field(x.T,box,wavevector,coefficient,scalar).T)
            rows=np.flatnonzero(mapping['patch_id']==patch)
            expected[rows]=field.x.array[moments['master_native_rows'][rows]]
            actual[rows]=libraries[family][patch]@coefficient.reshape(-1)
        interpolation=float(np.linalg.norm(actual-expected)/np.linalg.norm(expected))
        expanded=fem.Function(mpc.function_space);expanded.x.array[:]=0
        expanded.x.array[moments['master_native_rows']]=actual
        before=float(np.linalg.norm(expanded.x.array[mpc.slaves]))
        mpc.backsubstitution(expanded)
        co,offset=mpc.coefficients();defects=[]
        for slave in mpc.slaves:
            defects.append(expanded.x.array[slave]-np.dot(co[offset[slave]:offset[slave+1]],expanded.x.array[mpc.masters.links(int(slave))]))
        constraint=float(np.linalg.norm(defects)/np.linalg.norm(expanded.x.array))
        records.append(dict(family=family,interpolation_relative=interpolation,
            MPC_expansion_relative=constraint,slave_zero_before=before,
            orientation_classes=int(len(np.unique(moments['orientation_ids']))),
            all_edge_face_moments=True,global_extension_interpolated_before_row_selection=True,
            qualified=bool(interpolation<=1e-10 and constraint<=1e-10 and before==0)))
    return records
