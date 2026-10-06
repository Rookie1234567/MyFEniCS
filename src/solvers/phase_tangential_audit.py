"""Read-only electric tangential trace audit on actual shared/periodic faces.

Normal E and discrete H are deliberately not subjected to strong continuity.
Physical carrier is removed once on each side, leaving the periodic envelope.
"""
import hashlib
import time
import numpy as np
from .scattering_anchor import save_arrays
from .phase_evaluation_cache import CachedPhaseEvaluator,ExactTabulations


def tangential_metrics(first,second,axis,incident_scale=1.):
    a=np.array(first,complex,copy=True);b=np.array(second,complex,copy=True)
    a[:,axis]=0;b[:,axis]=0
    numerator=float(np.linalg.norm(a-b));operation=float(np.linalg.norm(a)+np.linalg.norm(b))
    frozen=float(incident_scale*np.sqrt(len(a)))
    near_zero=operation<=1e-12*frozen
    denominator=frozen if near_zero else operation
    return dict(numerator=numerator,operation_scale=operation,denominator=denominator,
        near_zero=near_zero,relative=numerator/max(denominator,1e-30))


def audit_tangential(field,bundle,folder,role,journal):
    from dolfinx import cpp
    mesh=field.function_space.mesh;mesh.topology.create_connectivity(2,3)
    links=mesh.topology.connectivity(2,3);nf=mesh.topology.index_map(2).size_local
    faces=np.arange(nf,dtype=np.int32)
    gd=cpp.mesh.entities_to_geometry(mesh._cpp_object,2,faces,False)
    bounds=np.asarray([[mesh.geometry.x[g].min(axis=0),mesh.geometry.x[g].max(axis=0)] for g in gd])
    width=bounds[:,1]-bounds[:,0];axis=np.argmin(width,axis=1)
    if np.any(np.min(width,axis=1)>1e-11):raise ValueError('tangential audit requires actual axis-aligned faces')
    domain=np.asarray([mesh.geometry.x.min(axis=0),mesh.geometry.x.max(axis=0)])
    pairs=[];boundary={}
    for f in faces:
        cells=list(map(int,links.links(int(f))))
        if len(cells)==2:pairs.append((int(f),int(f),cells[0],cells[1],int(axis[f]),0))
        elif len(cells)==1 and axis[f]<2:boundary[int(f)]=cells[0]
        elif len(cells)!=1:raise ValueError('actual face cell inventory')
    for d in (0,1):
        low=[f for f in boundary if axis[f]==d and abs(bounds[f,0,d]-domain[0,d])<1e-11]
        high=[f for f in boundary if axis[f]==d and abs(bounds[f,0,d]-domain[1,d])<1e-11]
        used=set()
        for f in low:
            transverse=[i for i in range(3) if i!=d]
            matches=[h for h in high if np.allclose(bounds[f][:,transverse],bounds[h][:,transverse],rtol=0,atol=1e-12)]
            if len(matches)!=1 or matches[0] in used:raise ValueError('actual periodic face pairing')
            h=matches[0];used.add(h);pairs.append((f,h,boundary[f],boundary[h],d,d+1))
        if len(used)!=len(high) or not low:raise ValueError('complete periodic face inventory')
    nodes,weights=np.polynomial.legendre.leggauss(8);nodes=(nodes+1)/2
    grid=np.asarray(np.meshgrid(nodes,nodes,indexing='ij')).reshape(2,-1).T
    ev=CachedPhaseEvaluator(field.function_space,1,bundle['kappa'],cache=ExactTabulations(256*2**20))
    metrics=[];geometry=[];began=time.perf_counter()
    with journal.measured(role+'_actual_shared_periodic_tangential_E_8x8'):
        for f,h,c,e,d,kind in pairs:
            transverse=[i for i in range(3) if i!=d];pts=np.empty((64,3))
            pts[:,d]=bounds[f,0,d];pts[:,transverse]=bounds[f,0,transverse]+grid*(bounds[f,1,transverse]-bounds[f,0,transverse])
            other=pts.copy();other[:,d]=bounds[h,0,d]
            a=ev.at(field,c,pts,bundle['cfg'].k0)['E']*np.exp(-1j*(pts@bundle['kappa']))[:,None]
            b=ev.at(field,e,other,bundle['cfg'].k0)['E']*np.exp(-1j*(other@bundle['kappa']))[:,None]
            m=tangential_metrics(a,b,d,1.);metrics.append([m['numerator'],m['operation_scale'],m['denominator'],float(m['near_zero']),m['relative']])
            geometry.append([bounds[f,0],bounds[f,1],bounds[h,0],bounds[h,1]])
    a=np.asarray(metrics);overall=float(np.linalg.norm(a[:,0])/max(np.linalg.norm(a[:,2]),1e-30));worst=int(np.argmax(a[:,4]))
    arrays=save_arrays(folder/(role+'_actual_tangential_faces.npz'),face_pairs=np.asarray(pairs,np.int64),face_geometry=np.asarray(geometry),metrics=a,
        cell_permutations=ev.permutations,kappa=bundle['kappa'],gauss_nodes=nodes,gauss_weights=weights)
    return dict(pass_gate=overall<=1e-10 and float(a[:,4].max())<=1e-10,overall_operation_relative=overall,
        maximum_face_operation_relative=float(a[:,4].max()),worst_face_pair=pairs[worst],
        face_count=len(pairs),internal_faces=sum(p[-1]==0 for p in pairs),periodic_x_faces=sum(p[-1]==1 for p in pairs),periodic_y_faces=sum(p[-1]==2 for p in pairs),
        arrays=arrays,seconds=time.perf_counter()-began,actual_native_eval_checks=ev.eval_checks,
        geometry_sha256=hashlib.sha256(bounds.tobytes()).hexdigest(),cache=ev.cache.record(),
        field='physical E / exp(i*kappa.x) on both sides; tangential envelope only',incident_amplitude=1.,near_zero_operation_threshold=1e-12,
        quadrature='8x8 Gauss per face; no strong normal E or H requirement',new_factor_count=0,new_solve_count=0)
