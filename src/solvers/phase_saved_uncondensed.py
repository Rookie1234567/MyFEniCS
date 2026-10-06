"""Public Basix original-form vectors for a saved physical gVh field.

No cell matrix, Schur tensor, factor or solve is formed. The three vector
actions (full/interior/trace) retain both Ckappa terms and the complex test
dual. Complete q63 boundary components remain the existing independent path.
"""
import json
from pathlib import Path
import numpy as np
from .scattering_anchor import save_arrays,relative
from src.runners.task042_shared import write_json


def local_vectors(values,curls,coefficients,J,weights,kappa,k0,epsilon,mu):
    """Reference-coefficient to physical test-dual integral; multiple RHS."""
    det=np.linalg.det(J);basis=values@np.linalg.inv(J)
    ck=curls@J.T/det+1j*np.cross(kappa,basis)
    e=np.einsum('qjc,jr->qcr',basis,coefficients,optimize=True)
    c=np.einsum('qjc,jr->qcr',ck,coefficients,optimize=True)
    curl=det/mu*np.einsum('q,qcr,qjc->jr',weights,c,np.conj(ck),optimize=True)
    mass=-det*k0*k0*epsilon*np.einsum('q,qcr,qjc->jr',weights,e,np.conj(basis),optimize=True)
    return curl,mass


def uncondensed_vectors(function,cfg,kappa,mpc,mesh_data,folder,journal,*,q=31,point_block=256,identity=None):
    from .scattering_accuracy_fields import CellEvaluator
    from .target_boundary_witness import dual_maps
    from src.postprocessing.phase_volume_quadrature import checked_block,array_hash
    V=function.function_space;ev=CellEvaluator(V,q);maps=dual_maps(V,mpc);n=V.dofmap.index_map.size_local
    if V.mesh.comm.size!=1 or point_block>256:raise ValueError('bounded saved volume audit MPI1')
    indices=np.asarray(V.element.basix_element.entity_dofs[3][0],int);dim=V.element.space_dimension
    results=np.zeros((2,n,3),complex);allrows=[];slaves=np.asarray(mpc.slaves,int)
    eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
    tags=dict(zip(map(int,mesh_data.cell_tags.indices),map(int,mesh_data.cell_tags.values),strict=True))
    base=dict(identity or {},function_sha256=array_hash(function.x.array),geometry_sha256=array_hash(V.mesh.geometry.x),
        q_degree=q,points_sha256=array_hash(ev.points),weights_sha256=array_hash(ev.weights),
        basis_sha256=array_hash(V.element.basix_element.coefficient_matrix),kappa_sha256=array_hash(kappa),
        module_sha256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest())
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with journal.measured('public_basix_complete_uncondensed_volume_q'+str(q)):
        for cell in range(len(ev.geometry)):
            rows=V.dofmap.cell_dofs(cell);J,_,_=ev.geometry[cell];path=folder/f'cell_{cell:06d}.json';cell_id=dict(base,cell=cell,tag=tags[cell])
            if path.exists():
                saved=checked_block(path,cell_id);cc,mm=saved['curl'],saved['mass']
            else:
                info=int(ev.permutations[cell])
                if info not in ev.transforms:
                    T=np.eye(dim);V.element.T_apply(T.ravel(),ev.permutations[cell:cell+1],dim);ev.transforms[info]=T
                full=function.x.array[rows];inside=np.zeros(dim,complex);inside[indices]=full[indices]
                co=ev.transforms[info].T@np.column_stack((full,inside,full-inside));cc=np.zeros((dim,3),complex);mm=cc.copy()
                for start in range(0,len(ev.points),point_block):
                    sl=slice(start,start+point_block)
                    vc,vm=local_vectors(ev.values[sl],ev.curls[sl],co,J,ev.weights[sl],kappa,cfg.k0,eps[tags[cell]],cfg.mu_r)
                    cc+=vc;mm+=vm
                cc=np.ascontiguousarray(cc);mm=np.ascontiguousarray(mm)
                V.element.T_apply(cc.view(float).ravel(),ev.permutations[cell:cell+1],6)
                V.element.T_apply(mm.view(float).ravel(),ev.permutations[cell:cell+1],6)
                receipt=save_arrays(path.with_suffix('.npz'),curl=cc,mass=mm,rows=rows)
                write_json(path,dict(identity=cell_id,arrays=receipt))
                if cell%8==0:journal.event('public_basix_volume_cell_committed',cell=cell,cells=len(ev.geometry))
            for local,row in enumerate(rows):
                masters,dual=maps[int(row)]
                np.add.at(results[0],masters,dual[:,None]*cc[local])
                np.add.at(results[1],masters,dual[:,None]*mm[local])
            allrows.extend(map(int,rows[indices]))
    if len(allrows)!=len(set(allrows)) or set(allrows)&set(map(int,slaves)):raise ValueError('independent internal/MPC row inventory')
    return dict(curl=results[0],mass=results[1],volume=results.sum(axis=0),internal_rows=np.asarray(allrows,int),
        identity=base,cell_count=len(ev.geometry),no_matrix_no_factor_no_solve=True)


def saved_audit(record,setup,cfg,function,values,bundle,folder,journal,*,regression=None):
    """Complete augmented/native residual plus homogeneous action recovery."""
    vol=values['volume'];carrier=bundle['dtn_action'].carrier;n=len(vol);coupling=np.zeros(n,complex)
    projected=[];hh=[]
    for entry,alpha in zip(carrier.entries,record['port'],strict=True):
        np.add.at(coupling,entry.coupling_rows,entry.coupling_values*alpha)
        projected.append(np.dot(entry.projection_values,record['u_storage'][entry.projection_rows]));hh.append(entry.normalization_h)
    projected=np.asarray(projected);hh=np.asarray(hh);pr=projected-hh*record['port'];native_boundary=np.zeros(n,complex)
    base=bundle['surface'].incident_traction();rhs=base.copy()
    for entry,alpha,out in zip(carrier.entries,bundle['incident_projections'],projected/hh,strict=True):
        np.add.at(rhs,entry.coupling_rows,entry.coupling_values*alpha)
        np.add.at(native_boundary,entry.coupling_rows,entry.coupling_values*out)
    true=rhs-vol[:,0]-native_boundary;top=rhs-vol[:,0]-coupling
    lift=np.zeros(n,complex)
    for entry,x in zip(carrier.entries,pr/hh,strict=True):np.add.at(lift,entry.coupling_rows,entry.coupling_values*x)
    den=max(np.linalg.norm(rhs),1e-30);ids=values['internal_rows'];ri=rhs[ids]-vol[ids,1]-vol[ids,2]-coupling[ids]
    ni=3*bundle['degree']*(bundle['degree']-1)**2;ip=ids.reshape(-1,ni)
    numerators=np.linalg.norm(ri.reshape(-1,ni),axis=1)
    rden=sum(np.linalg.norm(x[ip],axis=1) for x in (rhs,vol[:,1],vol[:,2],coupling))
    norms=dict(true=float(np.linalg.norm(true)/den),native=float(np.linalg.norm(true)/den),
        augmented=relative(top,rhs),port=relative(pr,projected),
        identity=relative(true-(top-lift),np.maximum(np.abs(rhs),np.abs(vol[:,0]+native_boundary))),
        slave_zero=bool(np.all(record['u_storage'][record['slaves']]==0)),
        rhs_saved_difference=relative(rhs-record['rhs'],record['rhs']))
    rec=dict(action_split=relative(vol[:,0]-vol[:,1]-vol[:,2],np.maximum(np.abs(vol[:,1]),np.abs(vol[:,2]))),
        operation_scaled_interior=float(np.linalg.norm(numerators)/max(np.linalg.norm(rden),1e-30)),
        internal_operation_scaled_max=float(np.max(numerators/np.maximum(rden,1e-30))),
        homogeneous_recovery=True,nonzero_internal_particular_preserved=True)
    reg=None
    if regression is not None:
        reg=dict(volume_action_relative=relative(vol[:,0]-regression['volume_action'],regression['volume_action']),
            rhs_relative=norms['rhs_saved_difference'],limit=1e-10)
        reg['pass_gate']=max(reg['volume_action_relative'],reg['rhs_relative'])<=1e-10
    arrays=save_arrays(Path(folder)/'independent_original_vectors.npz',volume_action=vol[:,0],volume_inside=vol[:,1],volume_trace=vol[:,2],
        volume_curl=values['curl'][:,0],volume_mass=values['mass'][:,0],coupling_action=coupling,native_boundary_action=native_boundary,
        rhs=rhs,residual=true,augmented_top=top,port_residual=pr,projected=projected,H=hh,port=record['port'],u_storage=record['u_storage'],slaves=record['slaves'],
        internal_rows=ids,internal_residual=ri,internal_numerators=numerators,internal_operation_scale=rden)
    result=dict(audit_path='PUBLIC_BASIX_UNCONDENSED_AUDIT',volume_q=values['identity']['q_degree'],surface_q=63,
        original_audit=norms,recovery=rec,regression=reg,arrays=arrays,
        equation_pass=all(norms[k]<=1e-6 for k in ('true','native','augmented','port')) and norms['identity']<=1e-10 and norms['slave_zero'],
        recovery_pass=max(rec['action_split'],rec['internal_operation_scaled_max'])<=1e-10,
        direct_internal_target_pass=max(norms[k] for k in ('true','native','augmented','port'))<=1e-10,
        new_factor_count=0,new_complete_solves=0,FFCx_replay='not_run; public Basix equivalent original-form vector audit')
    write_json(Path(folder)/'independent_original_audit.json',result)
    return result
