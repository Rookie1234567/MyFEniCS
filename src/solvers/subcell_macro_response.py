"""Fixed one-cell responses and one macro-trace/subcell physical deployment."""
import gc
import hashlib
import numpy as np
from scipy import sparse
from scipy.linalg import lu_factor,lu_solve
from src.runners.task042_shared import write_json
from .scattering_anchor import relative,save_arrays
from .scattering_anchor_checks import checked_arrays
from .hcurl_affine_phase_tensor import AffinePhaseReferenceTensor,axis_widths
from .subcell_response_kernel import MacroLayout,MacroResponse,ChildBlock,transform


def small_mesh(bounds,r,p):
    from mpi4py import MPI
    from dolfinx import fem,default_real_type
    from basix.ufl import element
    from src.geometry.mesh_builder_3d import _structured_hexa_mesh
    lo,hi=np.asarray(bounds);axes=[np.asarray([lo[a]+(hi[a]-lo[a])*j/r for j in range(r+1)]) for a in range(3)]
    mesh=_structured_hexa_mesh(MPI.COMM_SELF,*axes)
    V=fem.functionspace(mesh,element('N1curl',mesh.basix_cell(),p,dtype=default_real_type))
    return V


def factory(V,cfg,journal):
    from .fixed_phase_fem import carrier
    with journal.measured('local_phase_reference_p'+str(cfg.nedelec_degree)):
        return AffinePhaseReferenceTensor(V.element.basix_element,kappa=carrier(cfg),k0=cfg.k0,mu=cfg.mu_r,
            epsilon_by_tag={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating},q=2*cfg.nedelec_degree+3)


def blocks_for(V,layout,tag,raw_factory,cache,journal):
    result=[]
    for c in layout.cells:
        xyz=V.mesh.geometry.x[V.mesh.geometry.dofmap[c]];widths=axis_widths(xyz);p=int(V.mesh.topology.get_cell_permutation_info()[c])
        key=(int(tag),widths.tobytes(),p)
        if key not in cache:
            with journal.measured('child_complete_raw_internal_LU_response'):
                A=raw_factory.tensor(tag=tag,widths=widths);T=transform(V,int(c));A=np.ascontiguousarray(T@A@T.T)
                cache[key]=ChildBlock(A,V.element.basix_element)
            d=journal.folder/'child_complete_packets';d.mkdir(exist_ok=True)
            identity=hashlib.sha256(repr(key).encode()+str(raw_factory.element.hash()).encode()+raw_factory.kappa.tobytes()).hexdigest()
            receipt=save_arrays(d/(identity+'.npz'),raw=cache[key].raw,child_schur=cache[key].S,interior_factor=cache[key].lu[0],interior_pivots=cache[key].lu[1],interior_from_trace=cache[key].X,trace_from_interior=cache[key].Ati,widths=widths,kappa=raw_factory.kappa)
            write_json(d/(identity+'.json'),dict(tag=int(tag),degree=raw_factory.element.degree,element_hash=int(raw_factory.element.hash()),permutation=p,k0=raw_factory.k0,mu=raw_factory.mu,epsilon=raw_factory.epsilon[tag],arrays=receipt,producer=journal.source_state['source_sha'],backend=raw_factory.backend))
            journal.event('child_local_class_saved',tag=int(tag),permutation=p,widths=widths,class_count=len(cache),bytes=cache[key].bytes(),packet=receipt['sha256'])
        result.append(cache[key])
    return result


def select_cell(geometry,cfg,descriptor):
    xyz=geometry['geometry_x'][geometry['geometry_dofmap']];bounds=np.array([[x.min(axis=0),x.max(axis=0)] for x in xyz])
    box=np.asarray(descriptor['notch_box_nm']).reshape(3,2);centers=bounds.mean(axis=1)
    notch=np.flatnonzero(np.all((centers>box[:,0])&(centers<box[:,1]),axis=1))
    candidates=[]
    for c,tag in enumerate(geometry['cell_tags']):
        if tag not in (cfg.tags.grating,cfg.tags.substrate):continue
        for j in notch:
            if geometry['cell_tags'][j]!=cfg.tags.air:continue
            touch=[a for a in range(3) if bounds[c,1,a]==bounds[j,0,a] or bounds[c,0,a]==bounds[j,1,a]]
            if len(touch)!=1:continue
            a=touch[0]
            if all(min(bounds[c,1,k],bounds[j,1,k])>max(bounds[c,0,k],bounds[j,0,k]) for k in range(3) if k!=a):
                h=bounds[c,1]-bounds[c,0];candidates.append((float(h.max()/h.min()),tuple(centers[c]),c,int(tag),int(j)))
    if not candidates:raise ValueError('no Si macro with a true notch shared face')
    candidate=sorted(candidates,key=lambda x:(-x[0],x[1]))[0]
    return dict(cell=candidate[2],tag=candidate[3],notch_cell=candidate[4],aspect=candidate[0],center=candidate[1],bounds=bounds[candidate[2]],
        selection='maximum exact aspect then center lexicographic; selected before C6 coefficient read')


def manufactured_load(V,layout,parent_el,parent_coefficient,cfg,tag,kappa):
    """Independent public Basix test-dual integrals of a fixed bubble field."""
    import basix
    el=V.element.basix_element;points,w=basix.make_quadrature(basix.CellType.hexahedron,31)
    tab=el.tabulate(1,points);value=tab[0];curl=np.stack((tab[2,:,:,2]-tab[3,:,:,1],tab[3,:,:,0]-tab[1,:,:,2],tab[1,:,:,1]-tab[2,:,:,0]),axis=2)
    out=np.zeros(len(layout.native_rows),complex);mlo,mhi=layout.bounds;mh=mhi-mlo
    eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}[tag]
    for c,rows in zip(layout.cells,layout.child_rows,strict=True):
        x=V.mesh.geometry.x[V.mesh.geometry.dofmap[c]];lo=x.min(axis=0);h=x.max(axis=0)-lo;J=np.diag(h);det=np.prod(h)
        parentpoints=(lo+points*h-mlo)/mh;pt=parent_el.tabulate(1,parentpoints)
        pv=pt[0]/mh;pc=np.stack((pt[2,:,:,2]-pt[3,:,:,1],pt[3,:,:,0]-pt[1,:,:,2],pt[1,:,:,1]-pt[2,:,:,0]),axis=2)*mh/np.prod(mh)
        E=np.einsum('qjc,j->qc',pv,parent_coefficient);C=np.einsum('qjc,j->qc',pc,parent_coefficient)+1j*np.cross(kappa,E)
        basis=value/h;ck=curl*h/det+1j*np.cross(kappa,basis)
        f=det/cfg.mu_r*np.einsum('q,qc,qjc->j',w,C,np.conj(ck))-det*cfg.k0**2*eps*np.einsum('q,qc,qjc->j',w,E,np.conj(basis))
        f=transform(V,int(c))@f;np.add.at(out,rows,f)
    return out


def evaluate_local(V,layout,coeff,points,kappa,k0):
    el=V.element.basix_element;result={k:np.zeros((len(points),3),complex) for k in ('E','H')};bounds=[]
    for c in layout.cells:
        x=V.mesh.geometry.x[V.mesh.geometry.dofmap[c]];bounds.append([x.min(axis=0),x.max(axis=0)])
    bounds=np.asarray(bounds);upper=bounds[:,1].max(axis=0)
    for index,(c,rows,box) in enumerate(zip(layout.cells,layout.child_rows,bounds,strict=True)):
        mask=np.all((points>=box[0])&((points<box[1])|((points==upper)&(box[1]==upper))),axis=1)
        if not mask.any():continue
        h=box[1]-box[0];pp=(points[mask]-box[0])/h;tab=el.tabulate(1,pp);co=transform(V,int(c)).T@coeff[rows]
        E=np.einsum('qjc,j->qc',tab[0],co)/h
        C=np.einsum('qjc,j->qc',np.stack((tab[2,:,:,2]-tab[3,:,:,1],tab[3,:,:,0]-tab[1,:,:,2],tab[1,:,:,1]-tab[2,:,:,0]),axis=2),co)*h/np.prod(h)+1j*np.cross(kappa,E)
        phase=np.exp(1j*(points[mask]@kappa))[:,None];result['E'][mask]=phase*E;result['H'][mask]=phase*C/(1j*k0)
    return result


def local_study(folder,journal,scope):
    from dataclasses import replace
    from .phase_notch_hp import configured_setup
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    import basix,time,traceback
    begin=time.perf_counter();spec=scope.case_spec('LOCAL_RESPONSE')
    cfg,setup,geo=configured_setup(spec,journal,scope=scope)
    selected=select_cell(geo,cfg,scope.plan_record()['physical_descriptor']['geometry']);write_json(folder/'selected_cell.json',selected)
    parent=scope.parent('C6');v=checked_arrays(parent['arrays']);V=setup['spaces'][6]
    if not all(np.array_equal(geo[k],v[k]) for k in geo):raise ValueError('C6 actual geometry identity')
    field=restore_p0_full_field(setup['floquets'][6],v['u_storage']);c=selected['cell'];pel=V.element.basix_element
    ii=np.asarray(pel.entity_dofs[3][0],int);tt=np.setdiff1d(np.arange(pel.dim),ii);parent_co=transform(V,c).T@field.x.array[V.dofmap.cell_dofs(c)]
    trace=parent_co[tt];actual_internal=v['rhs'][V.dofmap.cell_dofs(c)[ii]]
    if np.linalg.norm(actual_internal)>1e-10*max(np.linalg.norm(v['rhs']),1e-30):raise ValueError('saved physical internal RHS is incompatible with source-free total Maxwell form')
    physical_source_identity=dict(total_volume_source='identically zero in frozen physical descriptor',saved_internal_rhs_norm=float(np.linalg.norm(actual_internal)),saved_full_rhs_norm=float(np.linalg.norm(v['rhs'])),boundary_numerical_roundoff_separate=True)
    manufactured=np.zeros(pel.dim,complex);manufactured[ii[:7]]=[1+.2j,-.4+.7j,.3-.1j,.8j,-.2, .1+.4j,.6-.3j]
    frozen=save_arrays(folder/'fixed_local_loads.npz',C6_reference_trace=trace,C6_actual_internal_rhs=actual_internal,manufactured_parent_reference_coefficient=manufactured,parent_geometry=selected['bounds'],kappa=v['kappa'])
    spaces={};rows=[];factories={}
    for name,p,r in (('P6',6,1),('P7',7,1),('P8',8,1),('R2',6,2),('R4',6,4)):
        if time.perf_counter()-begin>3300:
            rows.append(dict(space=name,status='NOT_RUN_LOCAL_60MIN_RESERVE'));continue
        d=folder/name;d.mkdir();vv=small_mesh(selected['bounds'],r,p);el=vv.element.basix_element
        layout=MacroLayout.build(vv,np.arange(vv.mesh.topology.index_map(3).size_local),selected['bounds'])
        localcfg=replace(cfg,nedelec_degree=p)
        if p not in factories:factories[p]=factory(vv,localcfg,journal)
        childcache={};blocks=blocks_for(vv,layout,selected['tag'],factories[p],childcache,journal)
        outputs=[]
        if r==1:
            from .phase_p_order_consistency import interpolation_operator
            I=interpolation_operator(pel,el);inside=np.asarray(el.entity_dofs[3][0],int);boundary=np.setdiff1d(np.arange(el.dim),inside)
            T=transform(vv,0);lift=(T@I)[:,tt];A=blocks[0].raw;lu=blocks[0].lu
            for load in ('physical','manufactured'):
                f=np.zeros(el.dim,complex) if load=='physical' else manufactured_load(vv,layout,pel,manufactured,cfg,selected['tag'],v['kappa'])
                # MacroLayout native row order is cell local order for one cell.
                u=np.zeros(el.dim,complex);u[boundary]=lift[boundary]@trace if load=='physical' else 0
                u[inside]=lu_solve(lu,f[inside]-A[np.ix_(inside,boundary)]@u[boundary])
                residual=A@u-f;q=lift[boundary].conj().T@residual[boundary]
                outputs.append((u,q,relative(residual[inside],np.maximum(np.abs(f[inside]),np.abs(A[np.ix_(inside,boundary)]@u[boundary]))),f.copy()))
            capacity=dict(macro_rows=el.dim,child_internal_rows=len(inside),LU_backward=max(b.backward_error for b in blocks))
        else:
            try:
                macro=MacroResponse(layout,blocks,journal,response=(r==2));capacity=macro.capacity
            except (MemoryError,ValueError) as error:
                if r!=4:raise
                (d/'failure.stderr').write_text(traceback.format_exc())
                rows.append(dict(space=name,status='BLOCKED_LOCAL_R4',error=repr(error),dependent_global_r2_blocked=False))
                write_json(folder/'local_response_progress.json',dict(selection=selected,rows=rows));continue
            for load in ('physical','manufactured'):
                f=np.zeros(len(layout.native_rows),complex) if load=='physical' else manufactured_load(vv,layout,pel,manufactured,cfg,selected['tag'],v['kappa'])
                u=macro.recover(trace if load=='physical' else np.zeros(432,complex),f);q,residual=macro.reaction(u,f)
                internal=np.setdiff1d(np.arange(len(u)),layout.boundary)
                scale=np.zeros_like(u)
                for m,B in zip(layout.child_rows,blocks,strict=True):np.add.at(scale,m,np.abs(B.raw)@np.abs(u[m]))
                outputs.append((u,q,float(np.linalg.norm(residual[internal])/max(np.linalg.norm(scale[internal])+np.linalg.norm(f[internal]),1e-30)),f.copy()))
            capacity['LU_backward']=max(macro.backward,max(b.backward_error for b in blocks));del macro
        records=[]
        for load,(u,q,error,f) in zip(('physical','manufactured'),outputs,strict=True):
            records.append(dict(load=load,operation_scaled_internal=error,arrays=save_arrays(d/(load+'.npz'),local_native=u,feedback=q,local_rhs=f,native_rows=layout.native_rows)))
        row=dict(space=name,status='COMPLETED',degree=p,r=r,capacity=capacity,loads=records,structural_zero=layout.structural_zero_operation,shared=layout.shared_boundary_operation,physical_tangential=layout.tangential_operation)
        rows.append(row);spaces[name]=(vv,layout,outputs);write_json(folder/'local_response_progress.json',dict(selection=selected,rows=rows))
        journal.event('local_response_space_committed',space=name,elapsed_seconds=time.perf_counter()-begin)
    pairs=[];lo,hi=selected['bounds']
    for a,b in (('R2','R4'),('P6','P7'),('P7','P8'),('P6','R2')):
        if a not in spaces or b not in spaces:continue
        if time.perf_counter()-begin>3300:break
        pair=[];interrupted=False
        for q in (23,31):
            pts,w=basix.make_quadrature(basix.CellType.hexahedron,q);r=4;total=np.zeros((2,2,2))
            for x in range(r):
                for y in range(r):
                    for z in range(r):
                        if time.perf_counter()-begin>3300:
                            interrupted=True;break
                        h=(hi-lo)/r;points=lo+(np.array([x,y,z])+pts)*h;weights=w*np.prod(h)
                        for li in range(2):
                            va=evaluate_local(spaces[a][0],spaces[a][1],spaces[a][2][li][0],points,v['kappa'],cfg.k0)
                            vb=evaluate_local(spaces[b][0],spaces[b][1],spaces[b][2][li][0],points,v['kappa'],cfg.k0)
                            for fi,key in enumerate(('E','H')):total[li,fi]+=[np.sum(weights[:,None]*np.abs(va[key]-vb[key])**2),np.sum(weights[:,None]*np.abs(vb[key])**2)]
                    if interrupted:break
                if interrupted:break
            if interrupted:break
            pair.append(total)
        if interrupted:
            write_json(folder/'comparison_time_limit.json',dict(pair=[a,b],classification='PARTIAL_LOCAL_COMPARISON_TIME_LIMIT',completed=pairs,elapsed_seconds=time.perf_counter()-begin))
            break
        differences=np.sqrt(pair[-1][:,:,0]/np.maximum(pair[-1][:,:,1],1e-30));feedback=[relative(spaces[a][2][li][1]-spaces[b][2][li][1],spaces[b][2][li][1]) for li in range(2)]
        op=float(np.max(np.abs(pair[0]-pair[1])/np.maximum(pair[-1][:,:,1,None],1e-30)))
        pairs.append(dict(first=a,second=b,fields_relative=differences,feedback_fixed_432_coordinate_relative=feedback,
            feedback_scope='fixed macro reference trace dual coordinates; not a physical mass norm',
            manufactured_feedback_relative_is_not_gate='exact polynomial weak load has zero boundary reaction; relative roundoff diagnostic only',
            quadrature_operation_scaled=op,arrays=save_arrays(folder/(a+'_'+b+'.npz'),q23=pair[0],q31=pair[1]),
            pass_increment=bool(max(differences[0])<=1e-4 and feedback[0]<=1e-4 and op<=1e-10),increment_gate_scope='physical C6 trace/source response; manufactured nonzero-source recovery has its separate operation gate'))
        write_json(folder/'local_response_comparisons.json',dict(pairs=pairs))
    trusted={r['space']:r for r in rows if r.get('status')=='COMPLETED'}
    math=all(name in trusted and max(x['operation_scaled_internal'] for x in trusted[name]['loads'])<=1e-10 and trusted[name]['capacity']['LU_backward']<=1e-10 for name in ('P6','R2'))
    result=dict(status='COMPLETED' if len(spaces)==5 and len(pairs)==4 else 'PARTIAL',role='LOCAL_RESPONSE',selection=selected,loads=frozen,rows=rows,pairs=pairs,mathematics_pass=math,
        new_complete_solves=0,new_global_factors=0,physical_source_identity=physical_source_identity,local_response_not_full_scattering=True,elapsed_local=time.perf_counter()-begin,source=journal.source_state,timings=journal.timings,
        H2_mathematics_prerequisite='P6 and R2 mapping/affine recovery/operation scales; R4 increment or capacity does not gate global R2')
    write_json(folder/'local_scientific_result.json',result);return result


def execute_stage(role,folder,journal,scope):
    if role=='LOCAL_RESPONSE':return local_study(folder,journal,scope)
    if role=='H2':
        from .subcell_macro_deployment import solve_h2
        return solve_h2(folder,journal,scope)
    raise ValueError('fixed local/subcell role inventory')
