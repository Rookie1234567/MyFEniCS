"""Common geometric subcells, evaluating both original gVh functions."""
import numpy as np
from .phase_explicit_accuracy_fields import PhaseEvaluator,analytic
from .scattering_anchor import relative,save_arrays


def mesh_bounds(space):
    m=space.mesh
    return np.asarray([[m.geometry.x[ds].min(axis=0),m.geometry.x[ds].max(axis=0)] for ds in m.geometry.dofmap])


def parents_at(bounds,points,*,interior=True):
    values=[]
    for point in points:
        if interior:
            ids=np.flatnonzero(np.all((point>bounds[:,0])&(point<bounds[:,1]),axis=1))
        else:
            # Fixed selected points can lie on an added artificial fine face;
            # a canonical half-open high-side cell resolves that FE trace.
            upper=bounds[:,1].max(axis=0)
            ids=np.flatnonzero(np.all((point>=bounds[:,0])&((point<bounds[:,1])|((point==upper)&(bounds[:,1]==upper))),axis=1))
        if len(ids)!=1:raise ValueError('common/selected physical point parent ambiguity')
        values.append(int(ids[0]))
    return np.asarray(values,np.int32)


def common_boxes(first,second):
    if not np.array_equal(first[:,0].min(axis=0),second[:,0].min(axis=0)) or not np.array_equal(first[:,1].max(axis=0),second[:,1].max(axis=0)):
        raise ValueError('physical domains differ')
    axes=[np.unique(np.concatenate((first[:,:,d].ravel(),second[:,:,d].ravel()))) for d in range(3)]
    boxes=np.asarray([[axes[0][i],axes[1][j],axes[2][k],axes[0][i+1],axes[1][j+1],axes[2][k+1]]
        for i in range(len(axes[0])-1) for j in range(len(axes[1])-1) for k in range(len(axes[2])-1)]).reshape(-1,2,3)
    if np.any(boxes[:,1]-boxes[:,0]<=0):raise ValueError('common positive geometric subdivision')
    mid=boxes.mean(axis=1);a=parents_at(first,mid);b=parents_at(second,mid)
    return boxes,a,b


def common_difference(first,second,cfg,journal,folder,*,q,selected_points,evaluator_factory=None):
    from .fixed_phase_fem import carrier
    factory=PhaseEvaluator if evaluator_factory is None else evaluator_factory
    k=carrier(cfg);a=factory(first.function_space,q,k);b=factory(second.function_space,q,k)
    ba,bb=mesh_bounds(first.function_space),mesh_bounds(second.function_space)
    boxes,pa,pb=common_boxes(ba,bb);names=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered')
    sums=np.zeros((6,3));per=[];components=[]
    with journal.measured('non_nested_common_physical_integrals_q'+str(q)):
        for box,i,j in zip(boxes,pa,pb,strict=True):
            size=box[1]-box[0];points=a.points*size+box[0];w=a.weights*np.prod(size)
            va=a.at(first,int(i),points,cfg.k0);vb=b.at(second,int(j),points,cfg.k0);bg=analytic(cfg,points)
            cell=[];parts=[]
            for name in names:
                key=name.split('_')[0];x=va[key];y=vb[key]
                if name.endswith('scattered'):x=x-bg[key];y=y-bg[key]
                triple=[np.sum(w[:,None]*np.abs(y-x)**2),np.sum(w[:,None]*np.abs(y)**2),np.sum(w[:,None]*np.abs(bg[key])**2)]
                cell.append(triple);parts.append(np.sum(w[:,None]*np.abs(y-x)**2,axis=0))
            per.append(cell);components.append(parts);sums+=cell
        pp=np.asarray(selected_points,float);ia=parents_at(ba,pp,interior=False);ib=parents_at(bb,pp,interior=False)
        values=[{key:np.zeros((len(pp),3),complex) for key in ('E','H','curl')} for _ in (0,1)]
        for ev,func,ids,out in ((a,first,ia,values[0]),(b,second,ib,values[1])):
            for c in np.unique(ids):
                mask=ids==c;v=ev.at(func,int(c),pp[mask],cfg.k0)
                for key in out:out[key][mask]=v[key]
        bg=analytic(cfg,pp);selected={};witness={}
        for name in names:
            key=name.split('_')[0];x=values[0][key];y=values[1][key]
            if name.endswith('scattered'):x=x-bg[key];y=y-bg[key]
            selected[name]=relative(x-y,y);witness['selected_'+name+'_first']=x;witness['selected_'+name+'_second']=y
    rows={key:dict(difference_L2=float(np.sqrt(s[0])),reference_L2=float(np.sqrt(s[1])),
        relative=float(np.sqrt(s[0])/max(np.sqrt(s[1]),1e-12)),incident_scaled=float(np.sqrt(s[0])/max(np.sqrt(s[2]),1e-12))) for key,s in zip(names,sums,strict=True)}
    arrays=save_arrays(folder/f'common_physical_difference_q{q}.npz',common_boxes=boxes,parent_first=pa,parent_second=pb,
        common_centers=boxes.mean(axis=1),per_cell_integrals=np.asarray(per),per_cell_component_error_squared=np.asarray(components),
        selected_points=pp,selected_parent_first=ia,selected_parent_second=ib,**witness)
    return dict(fields=rows,selected=selected,arrays=arrays,q=q,common_subcells=len(boxes),
        exact_cache=None if not hasattr(factory,'cache') else factory.cache.record(),
        independent_native_evaluation_max=[max(a.eval_checks,default=0.),max(b.eval_checks,default=0.)],
        full_cross_terms=True,geometry_pair='common actual geometric subdivision; no projection of either field',
        selected_rule='frozen V51 original and Z2 centers; canonical high side on artificial mesh faces',
        pass_gate=max([x['relative'] for x in rows.values()]+list(selected.values()))<=1e-4)
