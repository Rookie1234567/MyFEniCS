"""Bounded full-body p embedding and independent raw tensor witnesses.

No trace-only transfer, condensation, global matrix, factor or solve. The
dual uses a unique native-row definition then the actual MPC pullback.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from .scattering_anchor import save_arrays,relative
from .scattering_anchor_checks import checked_arrays


def interpolation_operator(low,high):
    """Basix public API accepts wrappers; DOLFINx exposes the C++ element."""
    import basix
    from basix.finite_element import FiniteElement
    a=low if hasattr(low,'_e') else FiniteElement(low)
    b=high if hasattr(high,'_e') else FiniteElement(high)
    return basix.compute_interpolation_operator(a,b)


class FullBodyEmbedding:
    def __init__(self,low,high):
        import basix
        from .target_boundary_witness import dual_maps
        self.low,self.high=low,high
        self.V6=low.mpc.function_space;self.V7=high.mpc.function_space
        self.I=interpolation_operator(self.V6.element.basix_element,self.V7.element.basix_element)
        for V in (self.V6,self.V7):V.mesh.topology.create_entity_permutations()
        self.p6=self.V6.mesh.topology.get_cell_permutation_info();self.p7=self.V7.mesh.topology.get_cell_permutation_info()
        self.n6=self.V6.dofmap.index_map.size_local;self.n7=self.V7.dofmap.index_map.size_local
        self.maps=dual_maps(self.V6,low.mpc);self.local={}
        self.rows6=[];self.rows7=[];self.owner=np.full(self.n7,-1,np.int32)
        for c in range(len(self.p7)):
            a=self.V6.dofmap.cell_dofs(c).copy();b=self.V7.dofmap.cell_dofs(c).copy()
            self.rows6.append(a);self.rows7.append(b)
            mask=self.owner[b]<0;self.owner[b[mask]]=c
            key=(int(self.p6[c]),int(self.p7[c]))
            if key not in self.local:
                T=[]
                for V,p in ((self.V6,self.p6),(self.V7,self.p7)):
                    t=np.eye(V.element.space_dimension);V.element.T_apply(t.ravel(),p[c:c+1],len(t));T.append(t)
                    if relative(t@t.T-np.eye(len(t)),np.eye(len(t)))>1e-12:raise ValueError('embedding transform is not orthogonal; do not assume inverse')
                self.local[key]=T[1]@self.I@T[0].T
        if np.any(self.owner<0):raise ValueError('full native row ownership missing')
        self.slaves7=np.asarray(high.mpc.slaves)

    def forward(self,source):
        from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
        field=restore_p0_full_field(self.low,np.asarray(source));out=np.zeros(self.n7,complex);defects=[]
        for c,(a,b) in enumerate(zip(self.rows6,self.rows7,strict=True)):
            v=self.local[int(self.p6[c]),int(self.p7[c])]@field.x.array[a];owner=self.owner[b]==c
            out[b[owner]]=v[owner]
        for c,(a,b) in enumerate(zip(self.rows6,self.rows7,strict=True)):
            v=self.local[int(self.p6[c]),int(self.p7[c])]@field.x.array[a]
            defects.append(np.linalg.norm(v-out[b]))
        self.shared_defect=float(max(defects,default=0)/max(np.linalg.norm(out),1e-30))
        out[self.slaves7]=0
        return out

    def adjoint(self,source):
        source=np.asarray(source);out=np.zeros(self.n6,complex)
        independent=np.ones(self.n7,bool);independent[self.slaves7]=False
        for c,(a,b) in enumerate(zip(self.rows6,self.rows7,strict=True)):
            mask=(self.owner[b]==c)&independent[b];values=np.zeros(len(b),complex);values[mask]=source[b[mask]]
            local=self.local[int(self.p6[c]),int(self.p7[c])].conj().T@values
            np.add.at(out,a,local)
        result=np.zeros_like(out)
        for v,(masters,coefficients) in zip(out,self.maps,strict=True):np.add.at(result,masters,coefficients*v)
        return result


def raw_direction_action(element,coordinates,coefficient,kappa,k0,epsilon,mu,points_per_axis):
    """Public Basix affine integration, independent of FFCx tensor kernels."""
    import basix
    x,w=np.polynomial.legendre.leggauss(points_per_axis);x=(x+1)/2;w=w/2
    points=np.stack(np.meshgrid(x,x,x,indexing='ij'),axis=-1).reshape(-1,3)
    weights=np.einsum('i,j,k->ijk',w,w,w).ravel()
    affine=np.linalg.lstsq(np.column_stack((basix.cell.geometry(basix.CellType.hexahedron),np.ones(8))),np.asarray(coordinates).reshape(8,3),rcond=None)[0]
    J=affine[:3].T;det=np.linalg.det(J);inv=np.linalg.inv(J)
    if det<=0:raise ValueError('independent raw positive affine geometry')
    tab=element.tabulate(1,points)
    values=tab[0]@inv
    curls=np.stack((tab[2,:,:,2]-tab[3,:,:,1],tab[3,:,:,0]-tab[1,:,:,2],tab[1,:,:,1]-tab[2,:,:,0]),axis=2)@J.T/det
    del tab
    e=np.einsum('qjc,j->qc',values,coefficient);c=np.einsum('qjc,j->qc',curls,coefficient)
    ik=1j*np.cross(kappa,values);ie=1j*np.cross(kappa,e);weight=weights*det
    curl=np.einsum('q,qjc,qc->j',weight,np.conj(curls),c)/mu
    cross=(np.einsum('q,qjc,qc->j',weight,np.conj(curls),ie)+np.einsum('q,qjc,qc->j',weight,np.conj(ik),c)+np.einsum('q,qjc,qc->j',weight,np.conj(ik),ie))/mu
    mass=-k0**2*epsilon*np.einsum('q,qjc,qc->j',weight,np.conj(values),e)
    return curl+cross+mass,dict(curl=curl,kappa_cross=cross,mass=mass)


def diagnose(folder,journal,scope):
    from .phase_notch_hp import restore_record,configured_setup
    from .phase_evaluation_cache import CachedPhaseEvaluator
    from .phase_explicit_accuracy_fields import PhaseEvaluator
    from .phase_explicit_accuracy import build_bundle
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field,destroy_same_mesh_physical_action
    from petsc4py import PETSc
    parent={r:scope.parent(r) for r in ('P','B')}
    restored={r:restore_record(parent[r],journal,scope=scope) for r in parent}
    a,b=restored['P'],restored['B'];identity=[]
    for key in a[2]:
        equal=np.array_equal(a[2][key],b[2][key]);identity.append(dict(field=key,equal=equal))
        if not equal:raise ValueError('cross p physical geometry/material differs: '+key)
    if parent['P']['mode_sha256']!=parent['B']['mode_sha256']:raise ValueError('cross p mode inventory')
    if not np.array_equal(checked_arrays(parent['P']['arrays'])['kappa'],checked_arrays(parent['B']['arrays'])['kappa']):raise ValueError('cross p kappa')
    from .fixed_phase_fem import carrier
    cfg=b[0];kappa=carrier(cfg);old=PhaseEvaluator(b[3].function_space,3,kappa);new=CachedPhaseEvaluator(b[3].function_space,3,kappa)
    from .scattering_accuracy_fields import cell_regions
    parts,_,_=cell_regions(b[2],cfg);cells=set(int(np.flatnonzero(mask)[0]) for mask in parts.values() if np.any(mask))
    cells.update(map(int,np.unique(old.permutations,return_index=True)[1]))
    evaluated=[];field_witness={}
    with journal.measured('saved_p7_full_Ckappa_direct_cached_pair'):
        for c in sorted(cells):
            J,o,_=old.geometry[c];points=np.array([[.17,.31,.61],[.42,.53,.79]])@J.T+o
            x=old.at(b[3],c,points,cfg.k0);y=new.at(b[3],c,points,cfg.k0)
            for key in x:
                evaluated.append(dict(cell=c,permutation=int(old.permutations[c]),component=key,operation=relative(x[key]-y[key],x[key])))
                field_witness[f'{c}_{key}_old']=x[key];field_witness[f'{c}_{key}_new']=y[key]
    saved_eval=dict(rows=evaluated,pass_gate=all(r['operation']<=1e-11 for r in evaluated),arrays=save_arrays(folder/'saved_B_evaluation.npz',**field_witness))
    write_json(folder/'saved_B_evaluation.json',saved_eval)
    embedding=FullBodyEmbedding(a[1]['floquets'][6],b[1]['floquets'][7]);rng=np.random.default_rng(5406)
    witnesses=[];bundles={};rhs={};original_qualified=True
    try:
        for role,row in restored.items():bundles[role],rhs[role]=build_bundle(row[0],row[1],journal)
        for label in ('COMPLEX_0','COMPLEX_1','SAVED_P'):
            u=checked_arrays(parent['P']['arrays'])['u_storage'] if label=='SAVED_P' else rng.standard_normal(embedding.n6)+1j*rng.standard_normal(embedding.n6)
            u=np.asarray(u).copy();u[a[1]['floquets'][6].mpc.slaves]=0
            with journal.measured('full_body_embedding_'+label):
                Ju=embedding.forward(u);field6=restore_p0_full_field(a[1]['floquets'][6],u);field7=restore_p0_full_field(b[1]['floquets'][7],Ju)
                e6=PhaseEvaluator(field6.function_space,3,kappa);e7=PhaseEvaluator(field7.function_space,3,kappa);physical=[]
                for c in sorted(cells):
                    J,o,_=e6.geometry[c];points=np.array([[.17,.31,.61],[.42,.53,.79]])@J.T+o
                    x=e6.at(field6,c,points,cfg.k0);y=e7.at(field7,c,points,cfg.k0)
                    physical.extend(relative(x[key]-y[key],x[key]) for key in x)
                q=rng.standard_normal(embedding.n7)+1j*rng.standard_normal(embedding.n7);q[embedding.slaves7]=0
                dual_left=np.vdot(q,Ju);dual_right=np.vdot(embedding.adjoint(q),u)
                dual=abs(dual_left-dual_right)/max(np.linalg.norm(q)*np.linalg.norm(Ju),1e-30)
                actions=[]
                for role,values in (('P',u),('B',Ju)):
                    src=rhs[role].duplicate();out=src.duplicate();src.array[:]=values
                    try:bundles[role]['physical_action'].apply(src,out);actions.append(out.array.copy());journal.calls['A']+=1
                    finally:src.destroy();out.destroy()
                pulled=embedding.adjoint(actions[1]);op=relative(actions[0]-pulled,actions[0])
                load=relative(rhs['P'].array-embedding.adjoint(rhs['B'].array),rhs['P'].array)
                arrays=save_arrays(folder/(label+'.npz'),u=u,Ju=Ju,action6=actions[0],action7=actions[1],dual_action7=pulled,rhs6=rhs['P'].array.copy(),dual_rhs7=embedding.adjoint(rhs['B'].array))
                item=dict(label=label,physical_max=max(physical),dual_operation=float(dual),shared_operation=embedding.shared_defect,
                    operator_operation=op,load_operation=load,arrays=arrays,pass_gate=max(physical)<=1e-11 and dual<=1e-10 and op<=1e-10 and load<=1e-10)
                witnesses.append(item);write_json(folder/'embedding_progress.json',dict(rows=witnesses))
        contract=scope.plan_record()['raw_tensor_parents']['B'];manifest=scope.ROOT/contract['path']
        if hashlib.sha256(manifest.read_bytes()).hexdigest()!=contract['sha256']:raise ValueError('D raw manifest hash')
        packet=json.loads(manifest.read_text());raw_rows=[];raw_directions=rng.standard_normal((2,1344))+1j*rng.standard_normal((2,1344))
        element=b[3].function_space.element.basix_element
        from dolfinx import fem
        reader=scope.raw_tensor_reader('R7',bundles['B'],journal)
        compiled=fem.form(bundles['B']['volume_action'].bilinear_form)
        for entry in packet['classes']:
            values=checked_arrays(entry['arrays']);tensor=values['tensor'];checks=[];vectors={}
            hit=reader.load(compiled,values['coordinates'],tag=entry['tag'],dimension=1344)
            if hit is None:raise ValueError('actual p7 reader mathematical dependency mismatch')
            if not np.array_equal(hit[0],tensor):raise ValueError('independently reopened cached tensor differs')
            epsilon={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}[entry['tag']]
            with journal.measured('independent_raw_direction_'+entry['key'][:12]):
                for n,coef in enumerate(raw_directions):
                    actual=tensor@coef;answers=[];scales=[]
                    for points in (11,13):
                        expected,split=raw_direction_action(element,values['coordinates'],coef,kappa,cfg.k0,epsilon,cfg.mu_r,points)
                        scale=sum(np.linalg.norm(x) for x in split.values());answers.append(expected);scales.append(scale)
                        vectors[f'q{points}_d{n}']=expected
                        for component,action in split.items():vectors[f'q{points}_d{n}_{component}']=action
                    numerator=float(np.linalg.norm(actual-answers[-1]));operation=numerator/max(scales[-1],1e-30)
                    checks.append(dict(direction=n,operation=operation,numerator=numerator,operation_denominator=float(scales[-1]),quadrature_pair_operation=float(np.linalg.norm(answers[0]-answers[1])/max(scales[-1],1e-30)),points_per_axis=[11,13]))
                    vectors[f'raw_d{n}']=actual;vectors[f'coefficient_d{n}']=coef
            raw_rows.append(dict(key=entry['key'],tag=entry['tag'],parent_sha256=entry['arrays']['sha256'],checks=checks,
                arrays=save_arrays(folder/(entry['key']+'_action.npz'),**vectors),pass_gate=all(max(c['operation'],c['quadrature_pair_operation'])<=1e-10 for c in checks)))
            write_json(folder/'raw_direction_progress.json',dict(rows=raw_rows,expected_classes=len(packet['classes'])))
        raw_gate=all(row['pass_gate'] for row in raw_rows)
        # Failed new bridge evidence does not by itself invalidate an already
        # audited original equation. Raw-vs-independent-volume disagreement
        # does require isolation and diagnosis before any dependent solve.
        original_qualified=raw_gate and saved_eval['pass_gate']
        passed=original_qualified and all(w['pass_gate'] for w in witnesses)
        return dict(status='COMPLETED',role='D',pass_gate=passed,same_p_paths_trusted=original_qualified,
            classification='CROSS_P_WITNESSES_PASS' if passed else 'CROSS_P_CONSISTENCY_NOT_ESTABLISHED',
            parent_hashes={r:parent[r]['arrays']['sha256'] for r in parent},identity=identity,saved_evaluation=saved_eval,
            embedding=witnesses,raw_directions=raw_rows,raw_reader=reader.record(),raw_classes=len(raw_rows),new_complete_solves=0,new_factor_count=0,
            notes='full uncondensed body, exact closed all532 DtN; no condensation/transfer commutation assumed',timings=journal.timings,calls=journal.calls)
    finally:
        for value in rhs.values():value.destroy()
        for bundle in bundles.values():destroy_same_mesh_physical_action(bundle)


def recheck_saved_operation_scale(folder,journal,scope,state):
    """Supplement saved witnesses with true component scales; no raw replay."""
    from .phase_notch_hp import restore_record
    from .phase_explicit_accuracy import build_bundle
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    resume=scope.window.TMP/'D_post_resume.json';binding=json.loads(resume.read_text())
    if hashlib.sha256(resume.read_bytes()).hexdigest()!=state['postprocessing_resume']['sha256']:raise ValueError('D scale supplement resolved identity')
    path=Path(binding['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=binding['sha256']:raise ValueError('D original witness changed')
    previous=json.loads(path.read_text())
    if previous['role']!='D' or not previous['same_p_paths_trusted']:raise ValueError('D original equation evidence not qualified')
    restored={r:restore_record(scope.parent(r),journal,scope=scope) for r in ('P','B')}
    embedding=FullBodyEmbedding(restored['P'][1]['floquets'][6],restored['B'][1]['floquets'][7]);bundles={};rhs={};rows=[]
    try:
        for role,row in restored.items():bundles[role],rhs[role]=build_bundle(row[0],row[1],journal)
        for row in previous['embedding']:
            saved=checked_arrays(row['arrays']);components={};scales=[]
            with journal.measured('saved_embedding_component_scale_'+row['label']):
                for role,name in (('P','u'),('B','Ju')):
                    src=rhs[role].duplicate();src.array[:]=saved[name];dtn=src.duplicate()
                    try:
                        for key,action in bundles[role]['volume_action'].component_actions.items():components[role+'_'+key]=action.apply(src).array.copy()
                        bundles[role]['dtn_action'].apply(src,dtn);components[role+'_DtN']=dtn.array.copy();journal.calls['A']+=1
                    finally:src.destroy();dtn.destroy()
                total6=sum(components['P_'+k] for k in ('curl','material_mass','DtN'))
                total7=sum(components['B_'+k] for k in ('curl','material_mass','DtN'))
                pulled={k:embedding.adjoint(components['B_'+k]) for k in ('curl','material_mass','DtN')}
                scales=[np.linalg.norm(v) for k,v in components.items() if k.startswith('P_')]+[np.linalg.norm(v) for v in pulled.values()]
                denominator=float(sum(scales));numerator=float(np.linalg.norm(saved['action6']-saved['dual_action7']))
                reproduction=max(np.linalg.norm(total6-saved['action6']),np.linalg.norm(embedding.adjoint(total7-saved['action7'])))/max(denominator,1e-30)
                operation=numerator/max(denominator,1e-30)
                receipt=save_arrays(folder/(row['label']+'_components.npz'),**components,**{'dual_B_'+k:v for k,v in pulled.items()})
            item={**row,'historical_result_scale_operation':row['operator_operation'],'historical_pass_gate':row['pass_gate'],
                'operator_operation':operation,'operator_numerator':numerator,'operator_denominator':denominator,
                'component_norms':scales,'component_arrays':receipt,'reproduction_operation':float(reproduction)}
            item['pass_gate']=max(item['physical_max'],item['dual_operation'],item['shared_operation'],item['load_operation'],operation,reproduction)<=1e-10 and item['physical_max']<=1e-11
            rows.append(item);write_json(folder/'embedding_scale_progress.json',dict(rows=rows))
        passed=all(r['pass_gate'] for r in rows)
        return dict(status='COMPLETED',role='D',pass_gate=passed,same_p_paths_trusted=True,
            classification='CROSS_P_WITNESSES_PASS' if passed else 'CROSS_P_CONSISTENCY_NOT_ESTABLISHED',
            original_D_evidence=binding,embedding=rows,raw_classes=previous['raw_classes'],raw_replayed=False,
            saved_evaluation=previous['saved_evaluation'],parent_hashes=previous['parent_hashes'],
            new_complete_solves=0,new_factor_count=0,timings=journal.timings,calls=journal.calls,
            scale='assembled Ckappa-curl, material mass and all532 DtN; both sides; old result denominator retained')
    finally:
        for value in rhs.values():value.destroy()
        for bundle in bundles.values():destroy_same_mesh_physical_action(bundle)
