"""Common physical quadrature, analytic background and representation checks.

Full vector products retain their complex cross terms. Native coefficients
are transformed to the reference element before covariant Piola evaluation;
an independent DOLFINx Function.eval witness checks this implementation.
No PDE is solved in a representation screen.
"""
from pathlib import Path
import numpy as np

from src.solvers.scattering_anchor import relative, save_arrays


def analytic(cfg,points):
    from src.common.analytic_fields_3d import electric_field_code_values,magnetic_field_code_values
    e=electric_field_code_values(cfg,points);h=magnetic_field_code_values(cfg,points)
    return {'E':e,'H':h,'curl':1j*cfg.k0*cfg.mu_r*h}


class CellEvaluator:
    def __init__(self,space,q):
        import basix
        self.space=space;self.mesh=space.mesh
        self.points,self.weights=basix.make_quadrature(basix.CellType.hexahedron,q)
        tab=space.element.basix_element.tabulate(1,self.points)
        self.values=tab[0]
        self.curls=np.stack((tab[2,:,:,2]-tab[3,:,:,1],tab[3,:,:,0]-tab[1,:,:,2],tab[1,:,:,1]-tab[2,:,:,0]),axis=2)
        del tab
        ref=basix.cell.geometry(basix.CellType.hexahedron);fit=np.column_stack((ref,np.ones(8)))
        self.mesh.topology.create_entity_permutations();self.permutations=self.mesh.topology.get_cell_permutation_info()
        self.geometry=[];self.transforms={}
        for c in range(self.mesh.topology.index_map(3).size_local):
            x=self.mesh.geometry.x[self.mesh.geometry.dofmap[c]]
            affine=np.linalg.lstsq(fit,x,rcond=None)[0];J=affine[:3].T;origin=affine[3];det=np.linalg.det(J)
            if det<=0 or np.linalg.norm(fit@affine-x)>1e-11:raise ValueError('physical evaluation affine geometry')
            self.geometry.append((J,origin,det))
        self.eval_checks=[]

    def cell(self,function,c,k0):
        J,o,det=self.geometry[c]
        info=int(self.permutations[c]);dim=self.space.element.space_dimension
        if info not in self.transforms:
            T=np.eye(dim,dtype=np.float64)
            self.space.element.T_apply(T.ravel(),self.permutations[c:c+1],dim)
            self.transforms[info]=T
        coefficient=self.transforms[info].T@function.x.array[self.space.dofmap.cell_dofs(c)]
        e=np.einsum('qjc,j->qc',self.values,coefficient)@np.linalg.inv(J)
        curl=(np.einsum('qjc,j->qc',self.curls,coefficient)@J.T)/det
        points=self.points@J.T+o
        if len(self.eval_checks)<4:
            witness=np.array([0,len(points)//2,len(points)-1])
            native=function.eval(points[witness],np.full(3,c,np.int32))
            check=relative(e[witness]-native,native);self.eval_checks.append(check)
            if check>1e-11:raise ValueError('independent native field evaluation orientation/Piola gate')
        return points,self.weights*det,{'E':e,'H':curl/(1j*k0),'curl':curl}


def cell_regions(geometry,cfg):
    from src.solvers.scattering_accuracy_scope import plan_record
    p=plan_record();centers=geometry['cell_centers'];tags=geometry['cell_tags']
    box=np.asarray(p['physical_descriptor']['geometry']['notch_box_nm']).reshape(3,2)
    notch=np.all((centers>=box[:,0])&(centers<=box[:,1]),axis=1)
    parts={'air_excluding_notch':(tags==cfg.tags.air)&~notch,
           'notch_air':(tags==cfg.tags.air)&notch,'substrate':tags==cfg.tags.substrate,
           'Si_block':tags==cfg.tags.grating}
    if not np.all(np.sum(list(parts.values()),axis=0)==1):raise ValueError('region partition missing or repeated cell')
    original_x=np.asarray(p['physical_descriptor']['geometry']['axes_nm']['x'])
    stripes={f'x_strip_{i}':(centers[:,0]>=a)&(centers[:,0]<b if i<3 else centers[:,0]<=b)
             for i,(a,b) in enumerate(zip(original_x[:-1],original_x[1:]))}
    if not np.all(np.sum(list(stripes.values()),axis=0)==1):raise ValueError('x stripe partition')
    widths=np.array([max(np.diff(p['physical_descriptor']['geometry']['axes_nm'][a])) for a in ('x','y','z')])
    neighborhood=np.all((centers>=box[:,0]-widths)&(centers<=box[:,1]+widths),axis=1)
    return parts,stripes,neighborhood


def screen_integrals(setup,cfg,geometry,*,q):
    from dolfinx import fem
    from src.solvers.common_3d_fields import stage4_layered_background_field
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from petsc4py import PETSc
    V=setup['spaces'][cfg.nedelec_degree];f=stage4_layered_background_field(V,cfg)
    mpc=setup['floquets'][cfg.nedelec_degree].mpc;slaves=np.asarray(mpc.slaves)
    stored=PETSc.Vec().createSeq(len(f.x.array),comm=PETSc.COMM_SELF);stored.array[:]=f.x.array;stored.array[slaves]=0
    try:constrained=restore_p0_full_field(setup['floquets'][cfg.nedelec_degree],stored)
    finally:stored.destroy()
    defect=relative(constrained.x.array-f.x.array,f.x.array)
    evaluator=CellEvaluator(V,q);sums={name:[0.,0.] for name in ('E','H','curl')}
    parts,stripes,_=cell_regions(geometry,cfg);regions={k:{name:[0.,0.] for name in sums} for k in parts}
    per_cell=[]
    for c in range(len(geometry['cell_centers'])):
        points,w,values=evaluator.cell(constrained,c,cfg.k0);known=analytic(cfg,points)
        detail={}
        for name in sums:
            num=float(np.sum(w[:,None]*np.abs(values[name]-known[name])**2));den=float(np.sum(w[:,None]*np.abs(known[name])**2))
            sums[name][0]+=num;sums[name][1]+=den;detail[name]=[num,den]
            for k,mask in parts.items():
                if mask[c]:regions[k][name][0]+=num;regions[k][name][1]+=den
        per_cell.append(detail)
    def record(pair):return dict(difference_squared=pair[0],reference_squared=pair[1],relative=np.sqrt(pair[0])/max(np.sqrt(pair[1]),1e-12))
    return {'q':q,'fields':{k:record(v) for k,v in sums.items()},'regions':{k:{n:record(v) for n,v in names.items()} for k,names in regions.items()},
            'region_counts':{k:int(mask.sum()) for k,mask in parts.items()},'MPC_coefficient_relative':defect,
            'Function_eval_max_relative':max(evaluator.eval_checks),'per_cell':per_cell,
            'coefficient_norm':float(np.linalg.norm(constrained.x.array)),
            'coefficient_role':'interpolated analytic background; not a solution or teacher'}


def representation_screen(folder,journal,make_setup):
    rows=[]
    for grid in ('ORIGINAL','X2'):
        for degree in (5,6):
            cfg,setup,geo=make_setup('FLAT',degree,grid,journal)
            with journal.measured(f'screen_{grid}_p{degree}'):
                low=screen_integrals(setup,cfg,geo,q=23);high=screen_integrals(setup,cfg,geo,q=31)
            qdef=max(abs(low['fields'][k][s]-high['fields'][k][s])/max(abs(high['fields'][k][s]),1e-30)
                     for k in ('E','H','curl') for s in ('difference_squared','reference_squared'))
            passed=all(high['fields'][k]['relative']<=1e-4 for k in ('E','H','curl')) and high['MPC_coefficient_relative']<=1e-10 and qdef<=1e-10
            row=dict(grid=grid,degree=degree,cell_count=len(geo['cell_centers']),native=setup['spaces'][degree].dofmap.index_map.size_global,
                     full_independent=setup['spaces'][degree].dofmap.index_map.size_global-len(setup['floquets'][degree].mpc.slaves),
                     q23=low,q31=high,quadrature_pair_max_relative=qdef,representation_pass=passed)
            rows.append(row);journal.event('representation_screen_saved',grid=grid,degree=degree,passed=passed,
                                          E=high['fields']['E']['relative'],H=high['fields']['H']['relative'])
            del setup
    bykey={(r['grid'],r['degree']):r for r in rows}
    selected='ORIGINAL' if bykey['ORIGINAL',6]['representation_pass'] else 'X2'
    selection=dict(grid=selected,low_degree=5,high_degree=6,admitted=bykey[selected,6]['representation_pass'],
                   status='fixed_pair_selected' if bykey[selected,6]['representation_pass'] else 'FOUR_SPACE_REPRESENTATION_NEGATIVE',
                   rule='prefer original p5/p6 if fine representation passes; otherwise fixed x-halved p5/p6; no PDE-result selection')
    return {'status':'COMPLETED','spaces':rows,'selection':selection,'new_solves':0,'timings':journal.timings,'calls':journal.calls}


def saved_attribution(folder,journal,make_setup):
    from dolfinx import fem
    from basix.ufl import element
    from dataclasses import replace
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.scattering_anchor_scope import stage as old_stage
    from src.solvers.scattering_anchor_checks import checked_arrays
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from src.solvers.common_3d_fields import stage4_layered_background_field
    from petsc4py import PETSc
    parents=[old_stage(n) for n in ('REFERENCE_NOTCH','REFERENCE_NOTCH_P5')]
    arrays=[checked_arrays(p['arrays']) for p in parents]
    cfg,setup,geo=make_setup('NOTCH',5,'ORIGINAL',journal)
    functions=[];backgrounds=[]
    for degree,a in zip((4,5),arrays):
        V=setup['spaces'][5] if degree==5 else fem.functionspace(setup['mesh'],element('N1curl',setup['mesh'].basix_cell(),degree))
        floquet=setup['floquets'][5] if degree==5 else build_double_floquet_mpc(V,setup['mesh_data'],replace(cfg,nedelec_degree=degree,visualization_degree=degree))
        if not np.array_equal(a['slaves'],floquet.mpc.slaves):raise ValueError('frozen canonical slave identity')
        for key in ('geometry_x','geometry_dofmap','cell_centers','cell_tags'):
            if not np.array_equal(a[key],geo[key]):raise ValueError('saved common physical geometry '+key)
        vec=PETSc.Vec().createSeq(len(a['u_storage']),comm=PETSc.COMM_SELF);vec.array[:]=a['u_storage']
        try:functions.append(restore_p0_full_field(floquet,vec))
        finally:vec.destroy()
        backgrounds.append(stage4_layered_background_field(V,cfg))
    parts,stripes,near=cell_regions(geo,cfg);groups={'whole':np.ones(len(geo['cell_centers']),bool),**parts,**stripes,'notch_neighborhood_OVERLAPPING':near}
    sums={group:{name:dict(total_delta2=0.,FE_background_delta2=0.,old_scattered_delta2=0.,cross=0.,
                           p4_total2=0.,p5_total2=0.,p4_analytic_scattered2=0.,p5_analytic_scattered2=0.,analytic_background2=0.,
                           FE4_background_error2=0.,FE5_background_error2=0.) for name in ('E','H','curl')} for group in groups}
    evaluators=[CellEvaluator(f.function_space,31) for f in functions]
    point_arrays={k:[] for k in ('physical_points','weights','total4','total5','analytic_E','analytic_H','FE_background4','FE_background5')}
    with journal.measured('saved_p4_p5_analytic_background_region_integrals'):
        for c in range(len(geo['cell_centers'])):
            points,w,v4=evaluators[0].cell(functions[0],c,cfg.k0);points5,w5,v5=evaluators[1].cell(functions[1],c,cfg.k0)
            if not np.allclose(points,points5,rtol=0,atol=1e-14) or not np.allclose(w,w5,rtol=1e-14,atol=0):raise ValueError('common physical quadrature')
            _,_,bg4=evaluators[0].cell(backgrounds[0],c,cfg.k0);_,_,bg5=evaluators[1].cell(backgrounds[1],c,cfg.k0)
            known=analytic(cfg,points)
            for name in ('E','H','curl'):
                dt=v5[name]-v4[name];db=bg5[name]-bg4[name];ds=dt-db
                def sq(v):return float(np.sum(w[:,None]*np.abs(v)**2))
                values=dict(total_delta2=sq(dt),FE_background_delta2=sq(db),old_scattered_delta2=sq(ds),
                    cross=float(-2*np.real(np.sum(w[:,None]*np.conj(dt)*db))),p4_total2=sq(v4[name]),p5_total2=sq(v5[name]),
                    p4_analytic_scattered2=sq(v4[name]-known[name]),p5_analytic_scattered2=sq(v5[name]-known[name]),
                    analytic_background2=sq(known[name]),FE4_background_error2=sq(bg4[name]-known[name]),FE5_background_error2=sq(bg5[name]-known[name]))
                for g,mask in groups.items():
                    if mask[c]:
                        for k,value in values.items():sums[g][name][k]+=value
            # Complete per-cell integral values are retained, not a giant
            # duplicated point×basis atlas. Selected arrays already exist.
    maxidentity=max(abs(s['old_scattered_delta2']-(s['total_delta2']+s['FE_background_delta2']+s['cross']))/max(s['old_scattered_delta2'],1e-30) for v in sums.values() for s in v.values())
    if maxidentity>1e-10:raise ValueError('full complex cross-term identity')
    return dict(status='COMPLETED',parents=[dict(source_sha=p['source_sha'],npz_sha256=p['arrays']['sha256']) for p in parents],
                quadrature=31,region_counts={g:int(mask.sum()) for g,mask in groups.items()},integrals=sums,
                cross_identity_max_relative=maxidentity,common_analytic_background=True,
                overlapping_region_excluded_from_partition_sum=True,timings=journal.timings,calls=journal.calls)
