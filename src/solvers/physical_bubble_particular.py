"""Fixed saved-data interior/trace diagnosis; no FE space or global solve."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from scipy.linalg import lu_factor,lu_solve
from .condensed_fine_reference import project_unconstrained_mpc_dual

SOURCE='d9462e486360a86e9635b504f37a0b762c2bf896'
ROOT=Path('benchmarks/artifacts/task39extra/v6_bubble_enriched_component')/SOURCE/'a2r160_g1'
READOUT=Path('benchmarks/artifacts/task39extra/v6_recursive/bubble_enriched_readout.json')
READOUT_SHA='ef9b7d06c3b44ef2da122946d75e7ff9d1c364dc1fa3ed2933defae4075e5fcb'


def expand_primal(value,mapping):
    """One finalized MPI1 primal backsubstitution; never apply C^H here."""
    result=np.array(value,copy=True)
    if np.any(result[mapping['slaves']]!=0):raise ValueError('primal input must be slave-zero')
    for slave in mapping['slaves']:
        a,b=mapping['offsets'][slave:slave+2]
        result[slave]=np.dot(mapping['coefficients'][a:b],result[mapping['masters'][a:b]])
    return result


def resolve_primal(candidates,dofmap,mapping):
    """Canonical shared rows; reject disagreement instead of averaging."""
    n=len(mapping['offsets'])-1;result=np.zeros(n,complex);seen=np.zeros(n,bool);defect=0.
    scale=max(max(np.max(np.abs(v),initial=0) for v in candidates),np.finfo(float).tiny)
    for rows,values in zip(dofmap,candidates,strict=True):
        old=seen[rows]
        defect=max(defect,float(np.max(np.abs(result[rows[old]]-values[old]),initial=0))/scale)
        result[rows[~old]]=values[~old];seen[rows]=True
    if not seen.all():raise ValueError('frozen dofmap does not cover owned rows')
    algebraic=result.copy();algebraic[mapping['slaves']]=0
    constraint=float(np.linalg.norm(result-expand_primal(algebraic,mapping))/max(np.linalg.norm(result),np.finfo(float).tiny))
    return algebraic,dict(shared_relative=defect,MPC_relative=constraint)


def cached_interior_action(value,mapping,cell_classes,classes,*,sample=lambda:None):
    """Full A action only for zero-trace interior input: DtN is identically zero."""
    expanded=expand_primal(value,mapping);out=np.zeros_like(expanded)
    sampled=set();sample()
    for cell,key in enumerate(cell_classes):
        if key not in sampled:sample();sampled.add(key)
        rows=mapping['dofmap'][cell];item=classes[key]
        if np.any(expanded[rows][item['boundary']]!=0):raise ValueError('cached volume-only action requires exact zero trace')
        np.add.at(out,rows,item['A']@expanded[rows])
    sample()
    return project_unconstrained_mpc_dual(out,mapping)


def gram_report(gram):
    """Keep complex cross terms; coordinate projections need not be metric-orthogonal."""
    if not np.isfinite(gram).all():raise ValueError('nonfinite metric Gram')
    norm=np.linalg.norm;scale=max(norm(gram),np.finfo(float).tiny)
    if np.min(np.diag(gram).real)<-1e-11*scale:raise ValueError('negative metric diagonal')
    if norm(gram-gram.conj().T)/scale>1e-11:raise ValueError('non-Hermitian metric Gram')
    return dict(gram=gram,diagonal=np.diag(gram).real,
        cross_2real={(str(i)+','+str(j)):float(2*gram[i,j].real) for i in range(len(gram)) for j in range(i+1,len(gram))})


def coefficient_defects(v,w,q,t,R,Q,boundary):
    """Participating-operator scales, not physical field norms."""
    if not all(np.isfinite(x).all() for x in (v,w,q,t,R,Q)):
        return dict.fromkeys(('Rd','Rq','QHt','q_boundary'),float('inf'))
    norm=np.linalg.norm;tiny=np.finfo(float).tiny;d=v-w
    return dict(Rd=float(norm(R@d)/max(norm(R)*(norm(v)+norm(w)),tiny)),
        Rq=float(norm(R@q)/max(norm(R)*norm(q),tiny)),
        QHt=float(norm(Q.conj().T@t)/max(norm(Q)*(norm(d)+norm(q)),tiny)),
        q_boundary=float(norm(q[boundary])/max(norm(q),tiny)))


def run_particular_diagnostic(cfg,comm,binding_path,directory,*,sample,marker):
    from src.runners.physical_diagnosis_worker import save_packet
    from src.runners.physical_diagnostic_completion import load_packet
    from src.runners.physical_recursive_controls import load_p4_failure_input
    from src.geometry.mesh_builder_3d import _stage4_axis_plan,_structured_hexa_mesh,_mark_cells
    from .fullspace_same_mesh_hcurl_pmg import _n1e,_dof_transform
    from .hcurl_affine_isotropic_tensor import AffineIsotropicMaxwellTensorSpec,AffineIsotropicMaxwellTensorFactory
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    save=lambda n,f:save_packet(directory,n,f)
    counts=dict(mesh=0,functionspace=0,local_LU=0,local_rhs=0,cached_A4=0,I4=0,H6=0,global_factor=0,
        metric_groups=0,metric_class_grams=0,metric_cell_grams=0)
    elapsed={};payload_peak=0
    def timed(name,fn):
        start=time.perf_counter()
        try:return fn()
        finally:elapsed[name]=elapsed.get(name,0.)+time.perf_counter()-start
    def payload(*objects):
        nonlocal payload_peak
        roots={}
        def walk(x):
            if isinstance(x,np.ndarray):
                while isinstance(x.base,np.ndarray):x=x.base
                roots[id(x)]=x.nbytes
            elif isinstance(x,dict):
                for v in x.values():walk(v)
            elif isinstance(x,(tuple,list)):
                for v in x:walk(v)
        for x in objects:walk(x)
        used=sum(roots.values())+16*1024**2;payload_peak=max(payload_peak,used)
        if used>128*1024**2:raise MemoryError('local payload plus 16MiB scratch policy exceeds 128MiB')
        sample()
    try:
        if comm.size!=1:raise ValueError('fixed MPI1 diagnostic')
        if hashlib.sha256(READOUT.read_bytes()).hexdigest()!=READOUT_SHA:raise ValueError('saved component readout identity differs')
        authority=json.loads(READOUT.read_text());hashes={e['path']:e['sha256'] for e in authority['evidence']}
        def old(name):
            path=ROOT/'records'/(name+'.json')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=hashes[str(path)]:raise ValueError('old packet identity differs: '+name)
            return load_packet(path)
        data=load_p4_failure_input(binding_path);mapping=data['map'];n=len(mapping['offsets'])-1
        if np.intersect1d(mapping['slaves'],mapping['masters']).size:raise ValueError('nested MPC not supported by saved map')
        cg=old('bubble_Cg');inner=old('bubble_I4_result');reference=np.zeros(n,complex)
        reference[mapping['independent_indices']]=data['arrays']['y']
        g=np.zeros(n,complex);g[mapping['independent_indices']]=data['arrays']['g']
        errors=[reference,reference-cg['solution'],reference-inner['solution']];rhs=np.column_stack([g,cg['residual']])
        save('particular_inputs',dict(source=SOURCE,binding=data['binding'],mapping=data['binding']['packets']['map'],
            g=g,errors=errors,rhs=rhs,I4_residual=inner['residual'],normalization=data['scale']))
        if not np.array_equal(g,cg['rhs']) or not np.array_equal(g,inner['rhs']):raise ValueError('same normalized RHS differs')
        marker('particular_mesh_started',dict(source=SOURCE))
        plan=_stage4_axis_plan(cfg,comm.size)
        mesh=timed('mesh',lambda:_structured_hexa_mesh(comm,plan.x_values,plan.y_values,plan.z_values,
            preserve_input_partition=cfg.stage4_preserve_structured_input_partition));counts['mesh']=1
        tags=_mark_cells(mesh,cfg);mesh.topology.create_entities(1);mesh.topology.create_entities(2);mesh.topology.create_entity_permutations()
        actual=dict(geometry=np.asarray(mesh.geometry.x),geometry_dofmap=np.asarray(mesh.geometry.dofmap),permutations=np.asarray(mesh.topology.get_cell_permutation_info()))
        bridge={k:bool(np.array_equal(v,mapping[k])) for k,v in actual.items()}
        save('particular_map_bridge',dict(fields=bridge,source_map_hash=data['binding']['packets']['map']['sha256'],
            dof_MPC='reuse immutable saved arrays, no new functionspace',relative_error=0. if all(bridge.values()) else 1.))
        if not all(bridge.values()):raise ValueError('original mesh/map bridge failed')
        classes={};identities={};orientations={};e4,e2=_n1e(4),_n1e(2)
        for i in range(18):
            prefix=f'bubble_class_{i:03d}';identity=old(prefix+'_identity');key=identity['sha256'];identities[key]=identity['key']
            h=old(prefix+'_bubble_harmonic')
            classes[key]={k:h[k] for k in ('A','P','R','Q','D','W')}
            classes[key]['boundary']=np.setdiff1d(np.arange(300),e4.entity_dofs[3][0]);del h
            payload(classes,mapping,errors,rhs,data,cg,inner)
        material={cfg.tags.air:cfg.eps_r,cfg.tags.substrate:cfg.substrate_index**2,cfg.tags.grating:cfg.grating_index**2}
        cell_tags=dict(zip(tags.indices.tolist(),tags.values.tolist()));cell_classes=[];widths_by_key={}
        quad=[dict(quadrature_degree=15,quadrature_rule='default')]*2
        for cell,geometry_rows in enumerate(mapping['geometry_dofmap']):
            xyz=mapping['geometry'][geometry_rows];widths=xyz.max(axis=0)-xyz.min(axis=0)
            J=np.column_stack([xyz[1]-xyz[0],xyz[2]-xyz[0],xyz[4]-xyz[0]])
            tag=int(cell_tags[cell]);eps=complex(material[tag]);info=int(mapping['permutations'][cell])
            key=dict(J=[v.hex() for v in J.ravel()],widths=[v.hex() for v in widths],tag=tag,eps=[eps.real.hex(),eps.imag.hex()],
                mu=[complex(cfg.mu_r).real.hex(),complex(cfg.mu_r).imag.hex()],k0=float(cfg.k0).hex(),quadrature=quad,
                orientation=info,element_hashes=[int(e4.hash()),int(e2.hash())])
            digest=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()
            if digest not in identities or identities[digest]!=key:raise ValueError('exact saved physical class missing')
            cell_classes.append(digest);widths_by_key[digest]=widths
            if info not in orientations:orientations[info]=_dof_transform(e4,info)
        interior_rows=mapping['dofmap'][:,e4.entity_dofs[3][0]].ravel()
        if len(cell_classes)!=252 or len(np.unique(interior_rows))!=len(interior_rows) or np.intersect1d(interior_rows,mapping['slaves']).size:
            raise ValueError('cell interiors are not uniquely owned unconstrained rows')
        save('particular_class_map',dict(cell_classes=cell_classes,identities=identities,qualification_repeated=False,
            interior_rows_unique=True,cell_count=252,orientation_count=len(orientations)))
        marker('particular_energy_bridge_started',dict(classes=18,cells=252))
        factory=timed('metric_grams',lambda:AffineIsotropicMaxwellTensorFactory(e4,AffineIsotropicMaxwellTensorSpec(
            curl_coefficient=0,mass_coefficient_by_tag={0:1},quadrature_degree=15)))
        def metrics(fields):
            sample();counts['metric_groups']+=1
            expanded=np.column_stack([expand_primal(v,mapping) for v in fields]);k=len(fields)
            totals={name:np.zeros((k,k),complex) for name in ('M0','scaled_curl')};cells={name:np.zeros((len(cell_classes),k,k),complex) for name in totals}
            for key in classes:
                sample()
                widths=widths_by_key[key];det=float(np.prod(widths));tf=orientations[identities[key]['orientation']]
                for name,parts,weights in (('M0',factory.mass_components,det/widths**2),('scaled_curl',factory.curl_components,widths**2/det/cfg.k0**2)):
                    counts['metric_class_grams']+=1
                    gram=sum(float(w)*v for w,v in zip(weights,parts));gram=tf@gram@tf.T
                    for cell,cell_key in enumerate(cell_classes):
                        if cell_key!=key:continue
                        counts['metric_cell_grams']+=1
                        values=expanded[mapping['dofmap'][cell]];entry=values.conj().T@gram@values
                        cells[name][cell]=entry;totals[name]+=entry
            sample()
            return totals,cells
        expected=[(old('bubble_Cg_fields')['fields'][k]['reference_energy'],old('bubble_Cg_fields')['fields'][k]['remaining_energy'],old('bubble_I4_fields')['fields'][k]['remaining_energy']) for k in ('M0','scaled_curl')]
        baseline,_=timed('energy_bridge',lambda:metrics(errors));energy_bridge={name:[float(abs(baseline[name][i,i].real-expected[j][i])/expected[j][i]) for i in range(3)] for j,name in enumerate(baseline)}
        save('particular_energy_bridge',dict(measured=baseline,expected=expected,relative=energy_bridge,limit=1e-10))
        if (not np.isfinite(expected).all() or not all(np.isfinite(v).all() for v in baseline.values())
            or not all(np.isfinite(row).all() for row in energy_bridge.values())
            or max(v for row in energy_bridge.values() for v in row)>1e-10):
            raise ValueError('original six field energies differ or are nonfinite')
        payload(classes,orientations,mapping,errors,rhs,data,cg,inner,factory.mass_components,factory.curl_components)
        for number,error in enumerate(errors):
            marker('particular_decomposition_started',dict(input=number))
            expanded=expand_primal(error,mapping);ws=[];qs=[]
            for cell,key in enumerate(cell_classes):
                v=expanded[mapping['dofmap'][cell]];item=classes[key];w=item['W']@(item['R']@v);d=v-w
                ws.append(w);qs.append(item['Q']@(item['Q'].conj().T@d))
            w,wfacts=resolve_primal(ws,mapping['dofmap'],mapping);q,qfacts=resolve_primal(qs,mapping['dofmap'],mapping);t=error-w-q
            closure=float(np.linalg.norm(error-w-q-t)/max(np.linalg.norm(error),np.finfo(float).tiny))
            constraints=dict(Rd=0.,Rq=0.,QHt=0.,q_boundary=0.)
            qt=expand_primal(q,mapping);tt=expand_primal(t,mapping)
            for cell,key in enumerate(cell_classes):
                item=classes[key];rows=mapping['dofmap'][cell]
                defects=coefficient_defects(expanded[rows],ws[cell],qt[rows],tt[rows],item['R'],item['Q'],item['boundary'])
                for name,value in defects.items():constraints[name]=max(constraints[name],value)
            save(f'particular_decomposition_{number}_vectors',dict(error=error,w=w,q=q,t=t,constraints=constraints,closure=closure,shared=[wfacts,qfacts]))
            if not np.isfinite(list(constraints.values())).all() or max(constraints.values())>1e-11:
                raise ValueError('coefficient decomposition identity failed')
            gram,cell_gram=timed('decomposition_metrics',lambda:metrics([w,q,t]))
            reports={k:dict(gram_report(v),field_norm_ratios=np.sqrt(np.maximum(np.diag(v).real,0)/expected[j][number])) for j,(k,v) in enumerate(gram.items())}
            facts=dict(w=w,q=q,t=t,constraints=constraints,closure=closure,shared=[wfacts,qfacts],metrics=reports,cell_gram=cell_gram,cell_tags=cell_tags)
            save(f'particular_decomposition_{number}',facts)
            if max(closure,*[v for row in (wfacts,qfacts) for v in row.values()])>1e-11:raise ValueError('decomposition shared/MPC identity failed')
            for j,name in enumerate(gram):
                if abs(gram[name].sum().real-expected[j][number])/expected[j][number]>1e-11:raise ValueError('cross-term energy closure failed')
        response=np.zeros_like(rhs)
        for index,key in enumerate(classes):
            sample();marker('particular_local_response_started',dict(index=index,class_key=key))
            item=classes[key];members=[c for c,k in enumerate(cell_classes) if k==key]
            loads=np.column_stack([item['Q'].conj().T@rhs[mapping['dofmap'][c],j] for c in members for j in range(2)])
            save(f'particular_local_{index:02d}_rhs',dict(class_key=key,cells=members,rhs=loads))
            counts['local_LU']+=1;factor=timed('local_LU',lambda:lu_factor(item['D']))
            counts['local_rhs']+=loads.shape[1];alpha=timed('local_rhs',lambda:lu_solve(factor,loads))
            residual=item['D']@alpha-loads;relative=float(np.linalg.norm(residual)/max(np.linalg.norm(loads),np.finfo(float).tiny))
            backward=float(np.linalg.norm(residual)/max(np.linalg.norm(item['D'])*np.linalg.norm(alpha)+np.linalg.norm(loads),np.finfo(float).tiny))
            save(f'particular_local_{index:02d}_response',dict(alpha=alpha,residual=residual,relative=relative,backward=backward))
            if not np.isfinite(relative+backward) or max(relative,backward)>1e-11:raise ValueError('local particular LU solve failed')
            for j,c in enumerate(members):
                rows=mapping['dofmap'][c];interior=e4.entity_dofs[3][0]
                response[rows[interior],:]=(item['Q']@alpha[:,2*j:2*j+2])[interior]
            del factor,alpha,loads,residual
        payload(classes,orientations,mapping,errors,rhs,response,data,cg,inner,factory.mass_components,factory.curl_components)
        for j in range(2):
            marker('particular_E_started',dict(input=j))
            save(f'particular_E_{j}_input_response',dict(rhs=rhs[:,j],Er=response[:,j]))
            counts['cached_A4']+=1;applied=timed('cached_A4',lambda:cached_interior_action(response[:,j],mapping,cell_classes,classes,sample=sample))
            remaining=rhs[:,j]-applied;lhs=[];before=[];after=[]
            for c,key in enumerate(cell_classes):
                rows=mapping['dofmap'][c];Q=classes[key]['Q'];lhs.append(Q.conj().T@remaining[rows]);before.append(Q.conj().T@rhs[rows,j]);after.append(Q.conj().T@applied[rows])
            qdef=float(np.linalg.norm(lhs)/max(np.linalg.norm(before)+np.linalg.norm(after),np.finfo(float).tiny))
            gram,cell_gram=timed('particular_metrics',lambda:metrics([errors[j],response[:,j]]))
            save(f'particular_E_{j}',dict(rhs=rhs[:,j],Er=response[:,j],AEr=applied,residual=remaining,QH_residual=np.asarray(lhs),
                QH_relative=qdef,dual_relative=float(np.linalg.norm(remaining)/np.linalg.norm(rhs[:,j])),
                metrics={k:dict(gram_report(v),Er_field_ratio=float(np.sqrt(max(v[1,1].real,0)/v[0,0].real)),
                    remaining_field_ratio=float(np.sqrt(max(v[0,0].real+v[1,1].real-2*v[0,1].real,0)/v[0,0].real))) for k,v in gram.items()},cell_gram=cell_gram,meaning='post-correction only, not full PQ inverse'))
            if not np.isfinite(qdef) or qdef>1e-11:raise ValueError('QH(r-AEr) identity failed')
        save('particular_summary',dict(status='DIAGNOSTIC_COMPLETED_NOT_SOLVER_QUALIFICATION',counts=counts,seconds=elapsed,energy_bridge=energy_bridge,G5_closed=False))
        marker('particular_complete',dict(counts=counts))
    finally:
        save('particular_costs',dict(counts=counts,seconds=elapsed,payload_peak_with_scratch_policy=payload_peak,
            scratch_policy_bytes=16*1024**2,payload_limit=128*1024**2,scope='named ndarray backing storage plus scratch policy; parent RSS authoritative'))
