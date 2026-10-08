"""Complete physical tetra fields and common-domain quadrature, no DG projection."""
import numpy as np
from src.runners.task042_shared import write_json
from .scattering_anchor import relative,save_arrays
from .scattering_accuracy_fields import analytic
from .independent_tetra_reference import TetraEvaluator,CachedTetraEvaluator,restore_field


def selected_points(physical):
    from .independent_tetra_scope import plan_record
    original=plan_record()['physical_descriptor']['geometry']['axes_nm']
    out=[]
    for f in (1,2):
        axes=[np.asarray(original[a]) for a in ('x','y','z')]
        z=axes[2];axes[2]=np.asarray([l+(r-l)*j/f for l,r in zip(z[:-1],z[1:]) for j in range(f)]+[z[-1]])
        mids=[(a[:-1]+a[1:])/2 for a in axes]
        out.extend((x,y,z) for z in mids[2] for y in mids[1] for x in mids[0])
    if len(out)!=240:raise ValueError('fixed 80+160 physical selected inventory')
    return np.asarray(out)


def locate(ev,points):
    """Actual affine barycentric inclusion; deterministic geometric side rule."""
    bounds=ev.bounds
    result=[]
    for point in points:
        ids=np.flatnonzero(np.all((point>=bounds[:,0]-1e-12)&(point<=bounds[:,1]+1e-12),axis=1))
        valid=[]
        for c in ids:
            J,o,_=ev.geometry[int(c)];r=np.linalg.solve(J,point-o)
            if np.min(r)>=-1e-11 and r.sum()<=1+1e-11:valid.append(int(c))
        if not valid:raise ValueError('physical point outside actual tetra cell')
        # Geometry ordering is invariant under native cell renumbering. Prefer
        # high coordinate side on a shared material/artificial face.
        result.append(max(valid,key=lambda c:tuple(bounds[c].mean(axis=0))+tuple(ev.geometry[c][0].ravel())))
    return np.asarray(result,np.int32)


def evaluate_selected(f,cfg,kappa,pp):
    ev=TetraEvaluator(f.function_space,0,kappa,quadrature_tables=False);ids=locate(ev,pp)
    out={k:np.zeros((len(pp),3),complex) for k in ('E','H','curl')}
    for c in np.unique(ids):
        mask=ids==c;v=ev.at(f,int(c),pp[mask],cfg.k0)
        for k in out:out[k][mask]=v[k]
    return out,ids,ev.eval_checks


def complete_output(s,b,x,folder,journal):
    from .dtn_port_3d import _port_power_metrics,_write_port_outputs
    from src.common.modes_3d import incident_power_3d
    from src.common.analytic_fields_3d import fresnel_reference
    cfg=s['cfg'];f=restore_field(s,x[:s['P'].shape[1]]);port=x[s['P'].shape[1]:];pp=selected_points(s['physical'])
    with journal.measured('full_physical_E_H_curl_240_points'):
        v,ids,checks=evaluate_selected(f,cfg,s['kappa'],pp);bg=analytic(cfg,pp)
        vals=dict(envelope_native_full=f.x.array.copy(),kappa=s['kappa'],selected_points=pp,selected_parent=ids)
        for k in v:vals['selected_'+k+'_total']=v[k];vals['selected_'+k+'_scattered']=v[k]-bg[k]
        fields=save_arrays(folder/'fields.npz',**vals)
    integrals=[];flat=[]
    with journal.measured('complete_tetra_volume_and_analytic_q23_q31'):
        for q in (23,31):
            ev=TetraEvaluator(s['V'],q,s['kappa']);cell=[];err=[];total=[]
            for c,tag in zip(s['data'].cell_tags.indices,s['data'].cell_tags.values,strict=True):
                points,w,actual=ev.cell(f,int(c),cfg.k0);known=analytic(cfg,points)
                eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}[int(tag)]
                total.append([float(np.sum(w[:,None]*np.abs(actual[k])**2)) for k in ('E','H','curl')])
                cell.append([float(np.sum(w)),float(np.sum(w[:,None]*np.abs(actual['E'])**2))*eps.imag])
                err.append([[float(np.sum(w[:,None]*np.abs(actual[k]-known[k])**2)),float(np.sum(w[:,None]*np.abs(known[k])**2))] for k in ('E','H','curl')])
            rec=save_arrays(folder/f'volume_q{q}.npz',per_cell_volume_absorption=np.asarray(cell),per_cell_analytic_squared=np.asarray(err),per_cell_total_squared=np.asarray(total))
            integrals.append(dict(q=q,arrays=rec,sums=np.asarray(cell).sum(axis=0)));flat.append(np.asarray(err).sum(axis=0))
    scale=cfg.k0/(2*incident_power_3d(cfg));av=float(integrals[-1]['sums'][1]*scale)
    qdef=abs(integrals[0]['sums'][1]-integrals[1]['sums'][1])/max(abs(integrals[1]['sums'][1]),1e-30)
    with journal.measured('all828_complex_channel_powers_and_output'):
        pm=_port_power_metrics(cfg,list(b['modes']),port,list(b['projections']))
        _write_port_outputs(folder,cfg,list(b['modes']),port,list(b['projections']),pm,s['mesh'].comm)
    energy=float(pm['R_total']+pm['T_total']+av-1)
    output=dict(fields=fields,port_metrics=pm,volume_metrics=dict(A_volume_total=av,energy_closure_error=energy,quadrature_relative=qdef),
        integrals=integrals,native_evaluation_max=max(checks),mode_manifest_sha256=b['digest'],complete_modes=len(b['modes']),
        authoritative_field='full native envelope, actual tetra mesh/basis/MPC, kappa; physical gVh and complete curl',
        H_units='Hcode=curl(E)/(i*k0*mu); physical H=Hcode/eta0')
    accuracy=None
    if s['spec']['case']=='FLAT':
        from .dtn_port_3d import _mode_boundary_phase,_mode_power_at_boundary
        fr=fresnel_reference(cfg);ref=np.zeros(828,complex);refpower=np.zeros(828)
        beta=next(m.beta for m in b['modes'] if (m.side,m.m,m.n,m.polarization)==('bottom',0,0,'s'))
        R=float(fr['R']);T=float(fr['T']*np.exp(2*beta.imag*cfg.physical_z_min))
        for i,m in enumerate(b['modes']):
            if (m.m,m.n,m.polarization)==(0,0,'s'):
                ref[i]=cfg.incident_amplitude*(fr['r'] if m.side=='top' else fr['t']);refpower[i]=R if m.side=='top' else T
        ref+=b['projections'];phases=np.array([_mode_boundary_phase(m,cfg) for m in b['modes']])
        power=np.array([_mode_power_at_boundary(m,cfg,complex(a-i))/incident_power_3d(cfg) for m,a,i in zip(b['modes'],port,b['projections'],strict=True)])
        mode_delta=(port-ref)*phases;field={k:float(np.sqrt(t[0]/t[1])) for k,t in zip(('E','H','curl'),flat[-1],strict=True)}
        selected={k:relative(v[k]-bg[k],bg[k]) for k in v}
        volume=float(integrals[-1]['sums'][0]);scattered={k:float(np.sqrt(t[0])/(np.sqrt(volume)*(cfg.k0 if k=='curl' else 1))) for k,t in zip(('E','H','curl'),flat[-1],strict=True)}
        differences=dict(R=abs(pm['R_total']-R),T=abs(pm['T_total']-T),A=abs(pm['A_balance']-(1-R-T)),
            A_volume=abs(av-(1-R-T)),single_mode=float(np.max(np.abs(power-refpower))),energy=abs(energy))
        qw=float(np.max(np.abs(flat[0]-flat[1])/np.maximum(flat[1][:,1,None],1e-30)))
        refarrays=save_arrays(folder/'flat_analytic.npz',reference_port=ref,reference_power=refpower,actual_power=power,mode_boundary_difference=mode_delta,
            q23_integrals=flat[0],q31_integrals=flat[1])
        accuracy=dict(fields=field,selected=selected,scattered_incident_scaled=scattered,power=differences,complex_mode_max=float(np.max(np.abs(mode_delta))),
            quadrature_operation_scaled=qw,arrays=refarrays,pass_gate=max([*field.values(),*selected.values(),*scattered.values(),float(np.max(np.abs(mode_delta)))])<=1e-4 and
            max(differences[k] for k in ('R','T','A','A_volume','energy'))<=1e-5 and differences['single_mode']<=1e-6 and qw<=1e-10)
    write_json(folder/'complete_output.json',output);return output,accuracy


def common_tetra_difference(first,second,cfg,journal,folder,q,pp):
    """Integrate on a contained common tetra partition, without interpolation."""
    f,g=first,second
    a=CachedTetraEvaluator(f.function_space,q,np.array([cfg.kx,cfg.ky,0]).real)
    b=CachedTetraEvaluator(g.function_space,q,a.kappa)
    names=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered');per=[]
    with journal.measured('common_tetra_physical_integrals_q'+str(q)):
        for c in range(len(b.geometry)):
            points,w,vb=b.cell(g,c,cfg.k0);mid=points.mean(axis=0);parent=int(locate(a,mid[None,:])[0])
            J,o,_=a.geometry[parent];refs=(points-o)@np.linalg.inv(J).T
            if refs.min()<-1e-10 or np.max(refs.sum(axis=1))>1+1e-10:raise ValueError('common tetra crosses first real cell')
            va=a.at(f,parent,points,cfg.k0);known=analytic(cfg,points);cell=[]
            for name in names:
                k=name.split('_')[0];x=va[k];y=vb[k]
                if name.endswith('scattered'):x=x-known[k];y=y-known[k]
                cell.append([np.sum(w[:,None]*np.abs(y-x)**2),np.sum(w[:,None]*np.abs(y)**2),np.sum(w[:,None]*np.abs(known[k])**2)])
            per.append(cell)
            if c%128==0:journal.event('common_tetra_block_saved_progress',q=q,cell=c)
        av,ia,_=evaluate_selected(f,cfg,a.kappa,pp);bv,ib,_=evaluate_selected(g,cfg,b.kappa,pp);bg=analytic(cfg,pp)
        select={};arrays={}
        for name in names:
            k=name.split('_')[0];x=av[k];y=bv[k]
            if name.endswith('scattered'):x=x-bg[k];y=y-bg[k]
            select[name]=relative(x-y,y);arrays['selected_'+name+'_first']=x;arrays['selected_'+name+'_second']=y
    sums=np.asarray(per).sum(axis=0);fields={k:dict(difference_squared=float(s[0]),reference_squared=float(s[1]),incident_squared=float(s[2]),
        relative=float(np.sqrt(s[0])/max(np.sqrt(s[1]),1e-12))) for k,s in zip(names,sums,strict=True)}
    receipt=save_arrays(folder/f'common_q{q}.npz',per_cell_integrals=np.asarray(per),selected_points=pp,selected_parent_first=ia,selected_parent_second=ib,**arrays)
    return dict(fields=fields,selected=select,arrays=receipt,q=q,pass_gate=max([v['relative'] for v in fields.values()]+list(select.values()))<=1e-4)


def tangential_check(s,f,folder):
    """Physical shared and xy-periodic tangential E, not normal E or H."""
    mesh=s['mesh'];mesh.topology.create_connectivity(2,0);mesh.topology.create_connectivity(2,3)
    mesh.topology.create_connectivity(0,3)
    from dolfinx import mesh as dm
    vertices=np.arange(mesh.topology.index_map(0).size_local,dtype=np.int32)
    coords=mesh.geometry.x[dm.entities_to_geometry(mesh,0,vertices,False).reshape(-1)]
    fv=mesh.topology.connectivity(2,0);fc=mesh.topology.connectivity(2,3)
    ev=CachedTetraEvaluator(f.function_space,0,s['kappa'],quadrature_tables=False);rows=[]
    rule=np.array([[.2,.2],[.3,.1],[.1,.3]])
    def compare(a,b,translation,phase):
        va=coords[fv.links(a)]
        pts=va[0]+rule[:,0,None]*(va[1]-va[0])+rule[:,1,None]*(va[2]-va[0])
        n=np.cross(va[1]-va[0],va[2]-va[0]);n/=np.linalg.norm(n)
        ca=int(fc.links(a)[0]);cb=int(fc.links(b)[-1])
        x=ev.at(f,ca,pts,s['cfg'].k0)['E'];y=ev.at(f,cb,pts+translation,s['cfg'].k0)['E']/phase
        delta=np.cross(n,x-y);scale=max(np.linalg.norm(x),np.linalg.norm(y),1e-30)
        return float(np.linalg.norm(delta)/scale)
    for facet in range(mesh.topology.index_map(2).size_local):
        if len(fc.links(facet))==2:rows.append([facet,facet,compare(facet,facet,np.zeros(3),1.)])
    cfg=s['cfg']
    for lowtag,hightag,axis,period in ((cfg.tags.x_min,cfg.tags.x_max,0,cfg.period_x),(cfg.tags.y_min,cfg.tags.y_max,1,cfg.period_y)):
        lookup={tuple(sorted(map(tuple,coords[fv.links(int(f))][:,[j for j in range(3) if j!=axis]]))):int(f) for f in s['data'].facet_tags.find(hightag)}
        for facet in s['data'].facet_tags.find(lowtag):
            key=tuple(sorted(map(tuple,coords[fv.links(int(facet))][:,[j for j in range(3) if j!=axis]])))
            if key not in lookup:raise ValueError('periodic boundary triangle not translation-compatible')
            shift=np.zeros(3);shift[axis]=period;phase=np.exp(1j*s['kappa'][axis]*period)
            rows.append([int(facet),lookup[key],compare(int(facet),lookup[key],shift,phase)])
    arr=np.asarray(rows);receipt=save_arrays(folder/'physical_tangential_faces.npz',per_face=arr)
    maximum=float(arr[:,2].max());return dict(maximum=maximum,face_count=len(rows),arrays=receipt,pass_gate=maximum<=1e-10,
        tested='tangential physical E only; actual shared and translated periodic triangles')


def common_hex_tetra_difference(hexfield,tetfield,cfg,kappa,journal,folder,q,pp):
    """A common geometric 6-tet integration partition; evaluate both originals."""
    import basix
    from itertools import permutations
    from .phase_evaluation_cache import CachedPhaseEvaluator
    from .phase_notch_hp_fields import mesh_bounds,parents_at
    a=CachedPhaseEvaluator(hexfield.function_space,0,kappa,quadrature_tables=False)
    b=CachedTetraEvaluator(tetfield.function_space,0,kappa,quadrature_tables=False)
    ba=mesh_bounds(hexfield.function_space);bb=b.bounds
    if not np.array_equal(ba[:,0].min(axis=0),bb[:,0].min(axis=0)) or not np.array_equal(ba[:,1].max(axis=0),bb[:,1].max(axis=0)):raise ValueError('common physical domains differ')
    axes=[np.unique(np.r_[ba[:,:,i].ravel(),bb[:,:,i].ravel()]) for i in range(3)]
    ref,weights=basix.make_quadrature(basix.CellType.tetrahedron,q)
    names=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered');per=[];geometries=[]
    blocks=folder/f'q{q}_contained_cells';blocks.mkdir(parents=True,exist_ok=True)
    with journal.measured('common_original_hex_tetra_q'+str(q)):
        for ix in range(len(axes[0])-1):
            for iy in range(len(axes[1])-1):
                for iz in range(len(axes[2])-1):
                    lo=np.array([axes[i][j] for i,j in enumerate((ix,iy,iz))]);hi=np.array([axes[i][j+1] for i,j in enumerate((ix,iy,iz))]);size=hi-lo
                    for order in permutations(range(3)):
                        vertices=[lo.copy()];v=lo.copy()
                        for i in order:v=v.copy();v[i]=hi[i];vertices.append(v)
                        xyz=np.array(vertices);J=(xyz[1:]-xyz[0]).T;o=xyz[0];centre=xyz.mean(axis=0)
                        ia=int(parents_at(ba,centre[None,:])[0]);ib=int(locate(b,centre[None,:])[0]);BJ,bo,_=b.geometry[ib]
                        bound=(xyz-bo)@np.linalg.inv(BJ).T
                        if bound.min()<-1e-10 or bound.sum(axis=1).max()>1+1e-10:raise ValueError('common integration tetra not contained in a real candidate cell')
                        index=len(per);path=blocks/f'cell_{index:06d}.json'
                        identity=dict(q=q,vertices=xyz.tolist(),hex_parent=ia,tetra_parent=ib)
                        if path.exists():
                            saved=__import__('json').loads(path.read_text())
                            if saved['identity']!=identity:raise ValueError('saved common geometric block identity')
                            cell=np.asarray(saved['integrals'])
                        else:
                            cell=np.zeros((6,3));det=abs(np.linalg.det(J))
                            for start in range(0,len(ref),256):
                                points=ref[start:start+256]@J.T+o;w=det*weights[start:start+256]
                                va=a.at(hexfield,ia,points,cfg.k0);vb=b.at(tetfield,ib,points,cfg.k0);known=analytic(cfg,points)
                                for j,name in enumerate(names):
                                    key=name.split('_')[0];x=va[key];y=vb[key]
                                    if name.endswith('scattered'):x=x-known[key];y=y-known[key]
                                    cell[j]+=[np.sum(w[:,None]*np.abs(y-x)**2),np.sum(w[:,None]*np.abs(y)**2),np.sum(w[:,None]*np.abs(known[key])**2)]
                            write_json(path,dict(identity=identity,integrals=cell))
                        per.append(cell);geometries.append(xyz)
                        if index%128==0:journal.event('contained_common_tetra_progress',q=q,cells=index)
    av={k:np.zeros((len(pp),3),complex) for k in ('E','H','curl')};ia=parents_at(ba,pp,interior=False)
    for i in np.unique(ia):
        mask=ia==i;r=a.at(hexfield,int(i),pp[mask],cfg.k0)
        for k in av:av[k][mask]=r[k]
    bv,ib,_=evaluate_selected(tetfield,cfg,kappa,pp);known=analytic(cfg,pp);sel={};arrays={}
    for name in names:
        k=name.split('_')[0];x=av[k];y=bv[k]
        if name.endswith('scattered'):x=x-known[k];y=y-known[k]
        sel[name]=relative(x-y,y);arrays['selected_'+name+'_first']=x;arrays['selected_'+name+'_second']=y
    sums=np.asarray(per).sum(axis=0);fields={k:dict(difference_squared=float(s[0]),reference_squared=float(s[1]),incident_squared=float(s[2]),relative=float(np.sqrt(s[0])/max(np.sqrt(s[1]),1e-12))) for k,s in zip(names,sums,strict=True)}
    rec=save_arrays(folder/f'common_q{q}.npz',per_cell_integrals=np.asarray(per),common_tetra_vertices=np.asarray(geometries),selected_points=pp,selected_parent_first=ia,selected_parent_second=ib,**arrays)
    return dict(q=q,fields=fields,selected=sel,arrays=rec,common_subcells=len(per),native_checks=[a.eval_checks,b.eval_checks],pass_gate=max([r['relative'] for r in fields.values()]+list(sel.values()))<=1e-4)
