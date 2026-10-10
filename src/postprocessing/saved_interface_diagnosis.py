"""Read-only interface layers and fixed directional limits of saved fields.

These supplementary one-sided values never replace the original 240 points.
No global quadrature, PDE, marking or factor is performed here.
"""
import itertools
import time
from collections import defaultdict

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.scattering_anchor import save_arrays,relative
from src.solvers.scattering_anchor_checks import checked_arrays


def interface_layers(vertices,tags):
    faces=defaultdict(list)
    for c,vs in enumerate(vertices):
        for face in itertools.combinations(vs,3):faces[tuple(sorted(map(int,face)))].append(c)
    adjacent=[set() for _ in vertices];interface=set();pairs=[]
    for face,cc in faces.items():
        if len(cc)==2:
            a,b=cc;adjacent[a].add(b);adjacent[b].add(a)
            if tags[a]!=tags[b]:interface.update(cc);pairs.append((a,b))
        elif len(cc)!=1:raise ValueError('nonmanifold frozen tetra face')
    nextlayer=set().union(*(adjacent[c] for c in interface)) if interface else set()
    nextlayer-=interface
    labels=np.full(len(vertices),2,np.int32)
    labels[list(interface)]=0;labels[list(nextlayer)]=1
    return labels,np.asarray(pairs,np.int64).reshape(-1,2)


def point_sides(ev,point,directions):
    ids=np.flatnonzero(np.all((point>=ev.bounds[:,0]-1e-12)&(point<=ev.bounds[:,1]+1e-12),axis=1))
    incident=[];bary=[];derivatives=[]
    for c in ids:
        J,o,_=ev.geometry[int(c)];inverse=np.linalg.inv(J);r=inverse@(point-o);lam=np.r_[1-r.sum(),r]
        if lam.min()<-1e-11:continue
        dr=directions@inverse.T;dl=np.column_stack((-dr.sum(axis=1),dr))
        incident.append(int(c));bary.append(lam);derivatives.append(dl)
    if not incident:raise ValueError('fixed point outside saved mesh')
    sides=[]
    for d in range(len(directions)):
        possible=[]
        for c,lam,dl in zip(incident,bary,derivatives,strict=True):
            zero=np.abs(lam)<=1e-11
            if np.all(dl[d,zero]>1e-12):possible.append(c)
        sides.append(possible[0] if len(possible)==1 else -1)
    owner=max(incident,key=lambda c:tuple(ev.bounds[c].mean(axis=0))+tuple(ev.geometry[c][0].ravel()))
    return incident,np.asarray(bary),np.asarray(sides,np.int32),owner


def diagnose(folder,journal,*,maximum_seconds=2700):
    from pathlib import Path
    from src.solvers import durable_l5_scope as L5,p6_completion_scope as P6
    from benchmarks.collect_independent_tetra import restored
    from src.solvers.independent_tetra_reference import TetraEvaluator
    from src.solvers.independent_tetra_fields import selected_points
    from src.solvers.scattering_accuracy_fields import analytic
    folder=Path(folder);folder.mkdir(exist_ok=False);began=time.monotonic()
    frozen=L5.stage('VERIFY_COST')['comparisons']['P6_L5'];raw=checked_arrays(frozen['arrays'])
    fine=L5.stage('SOLVE_COMPLETE');coarse=P6.stage('SOLVE_COMPLETE')
    s,v,f=restored(fine,journal);a,w,g=restored(coarse,journal)
    ev=TetraEvaluator(s['V'],0,s['kappa'],quadrature_tables=False)
    av=TetraEvaluator(a['V'],0,a['kappa'],quadrature_tables=False)
    vertices=s['geometry']['geometry_dofmap'];tags=s['geometry']['cell_tags']
    labels,interfaces=interface_layers(vertices,tags)
    volumes=np.asarray([abs(x[2])/6 for x in ev.geometry]);diff=raw['per_cell_difference']
    if diff.shape!=(len(volumes),3):raise ValueError('saved cell-difference inventory')
    layer_rows=[]
    for label in (0,1,2):
        hit=labels==label
        layer_rows.append(dict(layer=label,cells=int(hit.sum()),volume=float(volumes[hit].sum()),
            volume_fraction=float(volumes[hit].sum()/volumes.sum()),
            difference_squared=diff[hit].sum(axis=0).tolist(),
            fraction_of_saved_difference=(diff[hit].sum(axis=0)/np.maximum(diff.sum(axis=0),1e-300)).tolist()))
    directions=np.asarray(list(itertools.product((-1.,1.),repeat=3)))*np.sqrt([1.,2.,3.])
    directions/=np.linalg.norm(directions,axis=1)[:,None]
    pp=selected_points(fine['physical']);known=analytic(s['cfg'],pp)
    values=np.full((2,len(pp),8,6,3),np.nan+0j);valid=np.zeros((len(pp),8),bool);point_records=[]
    for j,point in enumerate(pp):
        if time.monotonic()-began>maximum_seconds:break
        fi,fb,fs,fo=point_sides(ev,point,directions);ci,cb,cs,co=point_sides(av,point,directions)
        vertices_at_point=[]
        for cell in fi:
            vv=s['geometry']['geometry_x'][vertices[cell]]
            if np.any(np.linalg.norm(vv-point,axis=1)<=1e-11):vertices_at_point.append(cell)
        row=dict(point=j,coordinates=point.tolist(),fine_incident_cells=fi,fine_materials=tags[fi].tolist(),
            fine_barycentric=fb.tolist(),coarse_incident_cells=ci,coarse_materials=a['geometry']['cell_tags'][ci].tolist(),
            coarse_barycentric=cb.tolist(),old_geometric_owner=[co,fo],
            saved_fine_owner=int(raw['selected_parent_second'][j]),
            fine_layer_counts=[int(np.count_nonzero(labels[fi]==k)) for k in (0,1,2)],
            at_actual_mesh_vertex=bool(vertices_at_point),directional_cell_pairs=[])
        for d,(fc,ac) in enumerate(zip(fs,cs,strict=True)):
            row['directional_cell_pairs'].append([int(ac),int(fc)])
            if fc<0 or ac<0:continue
            va=av.at(g,int(ac),point[None],a['cfg'].k0);vb=ev.at(f,int(fc),point[None],s['cfg'].k0)
            for k,name in enumerate(('E','H','curl')):
                values[0,j,d,k]=va[name][0];values[1,j,d,k]=vb[name][0]
                values[0,j,d,k+3]=va[name][0]-known[name][j]
                values[1,j,d,k+3]=vb[name][0]-known[name][j]
            valid[j,d]=True
        point_records.append(row)
        if j%16==0:write_json(folder/'point_progress.json',point_records)
    fields=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered')
    norms={}
    for k,name in enumerate(fields):
        x=values[0,:,:,k][valid];y=values[1,:,:,k][valid]
        norms[name]=dict(same_direction_relative=relative(x-y,y),directions_consumed=int(valid.sum()))
    spread={}
    for side,label in enumerate(('P6','L5')):
        spread[label]={}
        for k,name in enumerate(fields):
            maximum=0.
            for j in range(len(point_records)):
                z=values[side,j,:,k][valid[j]]
                if len(z)>1:maximum=max(maximum,float(np.max(np.linalg.norm(z[:,None]-z[None,:],axis=2))))
            spread[label][name]=dict(maximum_absolute_vector_spread=maximum)
    packet=save_arrays(folder/'diagnosis.npz',layer_labels=labels,material_interfaces=interfaces,
        volumes=volumes,saved_difference_squared=diff,directions=directions,points=pp,
        one_sided_six_fields=values,valid=valid)
    result=dict(status='COMPLETED' if len(point_records)==240 else 'PARTIAL',
        layers=layer_rows,layer_definition='0: cells touching true unlike-material face; 1: one additional face neighbor; 2: remaining domain',
        periodic_seams_are_not_material_interfaces=True,ports_not_material_interfaces=True,
        fixed_direction_pairs=norms,side_spreads=spread,points=point_records,arrays=packet,
        prior_comparison=frozen['arrays'],old_point_values_unchanged=True,not_a_global_error_bound=True,
        new_global_integrations=0,new_factors=0,new_solves=0,seconds=time.monotonic()-began)
    write_json(folder/'diagnosis.json',result);return result
