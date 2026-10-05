"""Fixed finite accuracy controls, sharing the original Maxwell solve/audit.

The surface integral callback is opt-in. Original FFCx volume actions remain
independent of both the condensed matrix and the optional six-Gram tensor.
No neural model or target-scale object is constructed in this package.
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import gc
import time
import numpy as np

from src.runners.task042_shared import write_json, _json_metadata
from .scattering_accuracy_scope import plan_record, stage, selection, window, SOLVES
from .scattering_anchor import (Journal, configuration as original_configuration,
    condense, DirectFactor, audit_original, outputs, save_arrays, relative)
from .scattering_anchor_checks import checked_arrays, native_recovery_action_split_check


def configuration(case, degree=5, grid='ORIGINAL'):
    if case not in ('FLAT','NOTCH') or grid not in ('ORIGINAL','X2') or degree not in (4,5,6):
        raise ValueError('fixed V50 geometry/degree inventory')
    cfg=original_configuration('NOTCH',degree)
    axes=plan_record()['physical_descriptor']['geometry']['axes_nm']
    x=list(axes['x'])
    if grid=='X2':x=[v for a,b in zip(x[:-1],x[1:]) for v in (a,(a+b)/2)]+[x[-1]]
    cfg=replace(cfg,case_name=f'task042_v50_{case.lower()}_{grid.lower()}_p{degree}',
        mesh_axis_x_values=tuple(x),mesh_axis_cell_counts=(len(x)-1,4,5),
        mesh_plan_id='task042.v50.fixed',mesh_axis_z_profile='task042.v50.fixed')
    cfg.stage4_dtn_quadrature_degree=47
    return cfg


def make_setup(case,degree,grid,journal):
    from mpi4py import MPI
    from dolfinx import mesh as dxmesh, fem, default_real_type
    from basix.ufl import element
    from src.geometry.mesh_builder_3d import _structured_hexa_mesh,_mark_boundary_facets,_mark_cells
    from src.constraints.floquet_3d import build_double_floquet_mpc
    cfg=configuration(case,degree,grid)
    with journal.measured(f'mesh_MPC_{case}_{grid}_p{degree}'):
        mesh=_structured_hexa_mesh(MPI.COMM_SELF,cfg.mesh_axis_x_values,cfg.mesh_axis_y_values,cfg.mesh_axis_z_values,
            preserve_input_partition=cfg.stage4_preserve_structured_input_partition)
        facet_tags,_=_mark_boundary_facets(mesh,cfg);tags=_mark_cells(mesh,cfg)
        centers=dxmesh.compute_midpoints(mesh,3,tags.indices);regular=tags.values.copy();values=regular.copy()
        if case=='FLAT':values[centers[:,2]>0]=cfg.tags.air
        else:
            box=np.asarray(plan_record()['physical_descriptor']['geometry']['notch_box_nm']).reshape(3,2)
            hit=np.all((centers>=box[:,0])&(centers<=box[:,1]),axis=1)&(regular==cfg.tags.grating)
            if hit.sum()!=(2 if grid=='ORIGINAL' else 4):raise ValueError('original genuine notch material support changed')
            values[hit]=cfg.tags.air
        tags=dxmesh.meshtags(mesh,3,tags.indices,values)
        V=fem.functionspace(mesh,element('N1curl',mesh.basix_cell(),degree,dtype=default_real_type))
        data=SimpleNamespace(mesh=mesh,cell_tags=tags,facet_tags=facet_tags)
        floquet=build_double_floquet_mpc(V,data,cfg)
        return cfg,dict(mesh=mesh,mesh_data=data,spaces={degree:V},floquets={degree:floquet}),dict(
            cell_centers=centers,cell_tags=values,regular_tags=regular,geometry_x=mesh.geometry.x.copy(),geometry_dofmap=mesh.geometry.dofmap.copy())


def build_bundle(cfg,setup,journal,*,q=47):
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action
    from .scattering_accuracy_boundary import SurfaceComponents
    holder={}
    def surface(V,data,cfg,oldq,*,jit_options):
        src=SurfaceComponents(V,setup['floquets'][cfg.nedelec_degree].mpc,cfg,q,method='separable' if q==47 else 'basix2d')
        holder['source']=src
        return src.assemblers()
    with journal.measured('JIT_original_volume_full532_CD_H'):
        bundle=build_same_mesh_physical_action(setup,cfg,cfg.nedelec_degree,surface_assembler_factory=surface,retain_all_surface_entries=True)
    bundle['dtn_quadrature_degree']=q
    from petsc4py import PETSc
    with journal.measured('physical_RHS'):
        base=PETSc.Vec().createSeq(setup['spaces'][cfg.nedelec_degree].dofmap.index_map.size_local,comm=PETSc.COMM_SELF)
        base.array[:]=holder['source'].incident_traction();rhs=base.duplicate()
        try:bundle['physical_action'].compose_physical_rhs(base,bundle['incident_projections'],rhs)
        finally:base.destroy()
    # The carrier owns its sparse copies; do not retain another entire basis cache.
    bundle['boundary_cost']=dict(seconds=holder['source'].seconds,unique_modes=holder['source'].calls,q=q,method=holder['source'].method)
    return bundle,rhs,dict(generation='complete physical traction plus exact analytic incident projections',q=q,mode_count=len(bundle['modes']))


def capacity(setup,cfg,journal):
    V=setup['spaces'][cfg.nedelec_degree];n=V.dofmap.index_map.size_local
    nc=setup['mesh'].topology.index_map(3).size_local
    ni=nc*len(V.element.basix_element.entity_dofs[3][0]);slaves=len(setup['floquets'][cfg.nedelec_degree].mpc.slaves)
    nt=n-ni-slaves;rows=nt+532;dim=V.element.space_dimension
    # Three dense global-sized envelopes (matrix/factor/workspace), and
    # conservative local-class/cache/ports plus one GiB of FE/runtime.
    local=nc*dim*dim*16*3
    envelope=3*rows*rows*16+local+n*532*16*2+2**30
    facts=dict(native=n,independent=n-slaves,trace=nt,internal=ni,rows=rows,cells=nc,
        full_dense_single_payload=rows*rows*16,local_cache_conservative=local,
        planned_simultaneous_bytes=envelope,limit_bytes=16*2**30,admitted=rows<=35000 and envelope<=16*2**30,
        status='PREDICTED_DENSE_ENVELOPE',opaque_factor_actual='unknown; tree RSS supervised')
    journal.event('capacity_before_allocation',**facts)
    return facts


class GramProvider:
    """Exact raw-class callback, with original curl/mass and orientation checks."""
    def __init__(self,bundle,folder,journal,*,use_gram=False):
        from dolfinx import fem
        from .hcurl_affine_isotropic_tensor import AffineIsotropicMaxwellTensorFactory,AffineIsotropicMaxwellTensorSpec
        from .hcurl_assembly_time_condensation import _cell_integral_kernels
        cfg=bundle['cfg'];V=bundle['setup']['spaces'][bundle['degree']]
        mass={cfg.tags.air:-cfg.k0**2*cfg.eps_air,cfg.tags.substrate:-cfg.k0**2*cfg.eps_substrate,cfg.tags.grating:-cfg.k0**2*cfg.eps_grating}
        self.factory=AffineIsotropicMaxwellTensorFactory(V.element.basix_element,
            AffineIsotropicMaxwellTensorSpec(1/cfg.mu_r,mass))
        self.forms={k:fem.form(v._bilinear_form) for k,v in bundle['volume_action'].component_actions.items()}
        self.kernels={k:_cell_integral_kernels(v,sum_duplicate_cell_integrals=True) for k,v in self.forms.items()}
        mesh=V.mesh;mesh.topology.create_entity_permutations()
        info=mesh.topology.get_cell_permutation_info();self.transforms=[]
        for p in np.unique(info):
            T=np.eye(V.element.space_dimension);V.element.T_apply(T.ravel(),np.asarray([p],dtype=np.uint32),V.element.space_dimension)
            self.transforms.append((int(p),T))
        self.rows=[];self.folder=folder;self.journal=journal;self.use_gram=use_gram;self.elapsed=0.;self.failed=False

    def __call__(self,form,kernels,coordinates,*,tag,dimension):
        from .hcurl_assembly_time_condensation import _tabulate_raw_tensor_class
        began=time.perf_counter()
        original=_tabulate_raw_tensor_class(form,kernels,coordinates,tag=tag,dimension=dimension)
        widths=tuple(np.ptp(np.asarray(coordinates).reshape(-1,3),axis=0));g=self.factory.tensor(tag=tag,widths=widths)
        m=self.factory.mass_tensor(tag=tag,widths=widths);c=g-m
        components={k:_tabulate_raw_tensor_class(f,self.kernels[k],coordinates,tag=tag,dimension=dimension) for k,f in self.forms.items()}
        # Operation-scale denominators retain curl and mass before cancellation.
        scale=np.linalg.norm(components['curl'])+np.linalg.norm(components['material_mass'])
        checks={k:float(np.linalg.norm(delta)/max(den,1e-300)) for k,delta,den in (
            ('full',g-original,scale),('curl',c-components['curl'],np.linalg.norm(components['curl'])),
            ('mass',m-components['material_mass'],np.linalg.norm(components['material_mass'])))}
        oriented=[]
        for info,T in self.transforms:
            oriented.append(dict(permutation=info,operation_scaled=float(np.linalg.norm(T@(g-original)@T.T)/max(scale,1e-300))))
        good=max(*checks.values(),*(r['operation_scaled'] for r in oriented))<=1e-10
        self.failed|=not good
        if not (self.folder/'reference_grams.npz').exists():
            save_arrays(self.folder/'reference_grams.npz',mass=np.asarray(self.factory.mass_components),curl=np.asarray(self.factory.curl_components))
        receipt=save_arrays(self.folder/f'raw_class_{len(self.rows):03d}.npz',coordinates=coordinates,original=original,
            curl_original=components['curl'],mass_original=components['material_mass'])
        self.rows.append(dict(index=len(self.rows),tag=tag,widths=widths,checks=checks,oriented=oriented,pass_gate=good,arrays=receipt))
        self.elapsed+=time.perf_counter()-began
        write_json(self.folder/'tensor_checks.json',self.report())
        # A failing optimization never prevents the original numerical route.
        return g if self.use_gram and good else original

    def report(self):
        return dict(all_actual_classes=self.rows,pass_gate=not self.failed,seconds=self.elapsed,
            factory=dict(self.factory.audit),requested_gram=self.use_gram,
            failed_class_fallback='original FFCx tensor; no approximate class merge')


def saved_equation_attribution(folder,journal):
    """Old fields with independently verified boundary, no factor/re-solve."""
    from .scattering_anchor_scope import stage as old_stage
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    from .hcurl_assembly_time_condensation import _cell_integral_kernels,_canonical_axis_aligned_coordinates
    from dolfinx import fem
    rows=[]
    for degree in (4,5):
        parent=old_stage('REFERENCE_NOTCH' if degree==4 else 'REFERENCE_NOTCH_P5')
        old=checked_arrays(parent['arrays']);cfg,setup,geometry=make_setup('NOTCH',degree,'ORIGINAL',journal)
        for k in ('geometry_x','geometry_dofmap','cell_tags','cell_centers'):
            if not np.array_equal(old[k],geometry[k]):raise ValueError('old/new frozen geometry '+k)
        bundle,rhs,_=build_bundle(cfg,setup,journal);u=rhs.duplicate();u.array[:]=old['u_storage']
        try:
            port=bundle['dtn_action'].recover_auxiliary(u)
            norms,vectors=audit_original(bundle,rhs,u,port,journal)
            qualified=save_arrays(folder/f'p{degree}_saved_field_q47_audit.npz',rhs=rhs.array.copy(),port=port,**vectors)
            from .scattering_accuracy_boundary import carrier
            c63,src63,_,_,_=carrier(setup['spaces'][degree],setup['floquets'][degree].mpc,cfg,63)
            from .fullspace_dtn_action import FullspaceDtnAction
            action=FullspaceDtnAction(c63,comm=setup['mesh'].comm)
            base=rhs.duplicate();new_rhs=rhs.duplicate();dtn=rhs.duplicate()
            try:
                base.array[:]=src63.incident_traction();action.compose_physical_rhs(base,bundle['incident_projections'],new_rhs)
                action.apply(u,dtn);r63=new_rhs.array-vectors['volume_action']-dtn.array
                den63=new_rhs.array.copy();port63=action.recover_auxiliary(u)
                v63=save_arrays(folder/f'p{degree}_saved_field_q63_audit.npz',rhs=den63,port=port63,residual=r63)
            finally:base.destroy();new_rhs.destroy();dtn.destroy();action.destroy()
            journal.calls['A']+=1
            tensor_dir=folder/f'p{degree}_all_actual_classes';tensor_dir.mkdir()
            provider=GramProvider(bundle,tensor_dir,journal)
            form=fem.form(bundle['volume_action'].bilinear_form);kernels=_cell_integral_kernels(form,sum_duplicate_cell_integrals=True)
            mesh=setup['mesh'];seen=set();assignment=[]
            with journal.measured(f'p{degree}_all_actual_raw_oriented_curl_mass'):
                for cell,tag in enumerate(geometry['cell_tags']):
                    coordinates,widths=_canonical_axis_aligned_coordinates(mesh,cell,tolerance=1e-12,geometry_identity_policy='raw_unrounded')
                    key=(int(tag),*widths);assignment.append(key)
                    if key in seen:continue
                    provider(form,kernels,coordinates,tag=int(tag),dimension=setup['spaces'][degree].element.space_dimension);seen.add(key)
            rows.append(dict(degree=degree,parent_source=parent['source_sha'],parent_npz_hash=parent['arrays']['sha256'],
                old_q=23 if degree==4 else 25,new_q47_audit=norms,new_q63_true=relative(r63,den63),
                old_native_true=parent['original_audit']['true'],rhs_change_relative=relative(old['rhs']-rhs.array,rhs.array),
                q47_q63_residual_difference=relative(vectors['residual']-r63,rhs.array),arrays47=qualified,arrays63=v63,
                tensor_checks=provider.report(),actual_cell_class_assignment=assignment,original_volume_form_audit=dict(bundle['volume_action'].audit)))
            journal.event('saved_field_new_boundary_audit_saved',degree=degree,rho=norms['true'],tensor_classes=len(seen))
        finally:u.destroy();rhs.destroy();destroy_same_mesh_physical_action(bundle)
    return rows


def analytic_comparison(bundle,u,geometry,folder,journal):
    from .scattering_accuracy_fields import CellEvaluator,analytic,cell_regions
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from src.common.analytic_fields_3d import fresnel_reference
    cfg=bundle['cfg'];E=restore_p0_full_field(bundle['setup']['floquets'][bundle['degree']],u)
    ev=CellEvaluator(E.function_space,31);parts,_,_=cell_regions(geometry,cfg)
    sums={k:np.zeros(2) for k in ('E','H','curl')};per=[]
    for c in range(len(geometry['cell_centers'])):
        points,w,value=ev.cell(E,c,cfg.k0);known=analytic(cfg,points);detail=[]
        for k in sums:
            pair=np.array([np.sum(w[:,None]*np.abs(value[k]-known[k])**2),np.sum(w[:,None]*np.abs(known[k])**2)],float)
            sums[k]+=pair;detail.append(pair)
        per.append(detail)
    centers=geometry['cell_centers'];known=analytic(cfg,centers)
    selected=E.eval(centers,np.arange(len(centers),dtype=np.int32))
    receipt=save_arrays(folder/'analytic_error.npz',per_cell_squared=np.asarray(per),selected_E=selected,
        analytic_selected_E=known['E'],analytic_selected_H=known['H'],analytic_selected_curl=known['curl'])
    errors={k:dict(difference_squared=float(v[0]),reference_squared=float(v[1]),relative=float(np.sqrt(v[0]/v[1]))) for k,v in sums.items()}
    r=fresnel_reference(cfg)
    return dict(fields=errors,selected_E_relative=relative(selected-known['E'],known['E']),
        pass_gate=all(v['relative']<=1e-4 for v in errors.values()) and relative(selected-known['E'],known['E'])<=1e-4,
        arrays=receipt,Fresnel=_json_metadata(r),regions={k:int(v.sum()) for k,v in parts.items()},q=31,
        zero_scattering_scale='fixed incident field amplitude1; incident power, never analytic zero norm')


def solve(role,folder,journal):
    if not stage('BOUNDARY')['q47_q63_pass']:return dict(status='NOT_RUN_BOUNDARY_GATE',role=role)
    chosen=selection();case='FLAT' if role.startswith('FLAT') else 'NOTCH';degree=5;grid='ORIGINAL'
    if role in ('FLAT_SELECTED','NOTCH_LOW','NOTCH_HIGH'):
        if not chosen['admitted']:return dict(status='NOT_RUN_REPRESENTATION_GATE',selection=chosen,role=role)
        grid=chosen['grid'];degree=chosen['low_degree'] if role=='NOTCH_LOW' else chosen['high_degree']
    if role=='GRAM_CONTROL':
        # Only the explicitly authorized original NOTCH p5 control; no newp.
        degree=5;grid='ORIGINAL'
    cfg,setup,geometry=make_setup(case,degree,grid,journal);cap=capacity(setup,cfg,journal)
    if not cap['admitted']:return dict(status='NOT_RUN_CAPACITY_GATE',capacity=cap,role=role)
    bundle=rhs=system=inverse=u=factor=None
    try:
        bundle,rhs,rf=build_bundle(cfg,setup,journal)
        provider=GramProvider(bundle,folder,journal,use_gram=role=='GRAM_CONTROL')
        system,inverse=condense(bundle,journal,expected=None,raw_tensor_provider=provider)
        write_json(folder/'build_audit.json',system.build_audit)
        write_json(folder/'original_volume_forms.json',dict(components={k:[dict(metadata=i.metadata(),subdomain=str(i.subdomain_id()),estimated_polynomial_degree=str(i.integrand())) for i in v._bilinear_form.integrals()]
            for k,v in bundle['volume_action'].component_actions.items()},element=str(setup['spaces'][degree].element.basix_element),
            polynomial_reason='axis-aligned affine cell, constant material; Nedelec degree p; products at most2p; Fourier/incident not polynomial'))
        factor=DirectFactor(system.matrix,journal);inverse.factor=factor
        with journal.measured('solve_minimal_recovery'):
            u=inverse.apply(rhs);port=inverse.last_port_solution.copy()
        # Save immediately, before any derived audit or field output can fail.
        early=save_arrays(folder/'returned_solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),**geometry)
        journal.event('returned_solution_saved_before_audit',sha256=early['sha256'])
        norms,vectors=audit_original(bundle,rhs,u,port,journal);refinements=[]
        for _ in range(2):
            if max(norms['true'],norms['augmented'],norms['port'])<=1e-10:break
            correction=rhs.duplicate();correction.array[:]=vectors['residual']
            with journal.measured('fixed_refinement'):
                delta=inverse.apply(correction);u.axpy(1,delta);port+=inverse.last_port_solution
            delta.destroy();correction.destroy();norms,vectors=audit_original(bundle,rhs,u,port,journal);refinements.append(norms)
        arrays=save_arrays(folder/'solution.npz',u_storage=u.array.copy(),port=port,rhs=rhs.array.copy(),
            slaves=np.asarray(setup['floquets'][degree].mpc.slaves),**geometry,**vectors)
        inverse.factor=None;factor.destroy();factor=None
        system.matrix.destroy();system.matrix=None;gc.collect();journal.event('condensed_matrix_released_before_output')
        _,recovery,recovery_vec=native_recovery_action_split_check(bundle,u,rhs,port,vectors,journal)
        rec_arrays=save_arrays(folder/'recovery.npz',**recovery_vec)
        output=outputs(bundle,u,port,folder,journal)
        accuracy=analytic_comparison(bundle,u,geometry,folder,journal) if case=='FLAT' else None
        return dict(status='COMPLETED',role=role,case=case,degree=degree,grid=grid,capacity=cap,arrays=arrays,returned_arrays=early,
            original_audit=norms,recovery=recovery,recovery_arrays=rec_arrays,output=output,analytic=accuracy,
            build_audit=_json_metadata(system.build_audit),tensor_checks=provider.report(),fixed_refinements=refinements,
            boundary=bundle['boundary_cost'],mode_sha256=bundle['mode_sha256'],RHS=rf,
            timings=journal.timings,calls=journal.calls,NN_training=0,original_A_oracle='independent original FFCx plus complete surface carrier')
    finally:
        if factor is not None:factor.destroy()
        if u is not None:u.destroy()
        if rhs is not None:rhs.destroy()
        if inverse is not None:inverse.destroy()
        if bundle is not None:
            from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
            destroy_same_mesh_physical_action(bundle)


def verify(folder,journal):
    from petsc4py import PETSc
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    rows=[]
    for role in SOLVES:
        try:r=stage(role)
        except FileNotFoundError:continue
        if r['status']!='COMPLETED':continue
        cfg,setup,geometry=make_setup(r['case'],r['degree'],r['grid'],journal)
        # Independently integrated q63 surface plus untouched original volume.
        bundle,rhs,_=build_bundle(cfg,setup,journal,q=63);u=rhs.duplicate()
        try:
            v=checked_arrays(r['arrays'])
            for k in ('geometry_x','geometry_dofmap','cell_tags','cell_centers'):
                if not np.array_equal(geometry[k],v[k]):raise ValueError('frozen/live geometry '+k)
            rhs_diff=relative(v['rhs']-rhs.array,rhs.array);u.array[:]=v['u_storage']
            port=np.asarray(bundle['dtn_action'].recover_auxiliary(u))
            norms,values=audit_original(bundle,rhs,u,port,journal)
            _,recovery,recovery_vec=native_recovery_action_split_check(bundle,u,rhs,port,values,journal)
            rec=save_arrays(folder/(role+'_independent_audit.npz'),port=port,**values,**recovery_vec)
            eq=max(norms[k] for k in ('true','native','augmented','port'))<=1e-6 and norms['identity']<=1e-10 and norms['slave_zero']
            internal=max(recovery['operation_scaled_interior'],recovery['max_cell_operation_scaled'],recovery['split_action_identity_operation_scale'])<=1e-10
            power=r['output']['port_metrics'];vol=r['output']['volume_metrics']
            rows.append(dict(role=role,case=r['case'],degree=r['degree'],grid=r['grid'],q47_q63_rhs_relative=rhs_diff,
                original_audit=norms,recovery=recovery,arrays=rec,equation_pass=eq,recovery_pass=internal,
                power=power,volume=vol,analytic=r.get('analytic'),source_parent=r['source_sha'],parent_array=r['arrays']['sha256']))
        finally:u.destroy();rhs.destroy();destroy_same_mesh_physical_action(bundle)
    return dict(status='COMPLETED',rows=rows,independent_surface_q=63,calls=journal.calls,timings=journal.timings,
        target_qualified=False,NN20_qualified=False)


def cost(folder,journal):
    from .scattering_accuracy_scope import ARTIFACT
    rows=[]
    for role in SOLVES:
        try:r=stage(role)
        except FileNotFoundError:continue
        if r['status']=='COMPLETED':rows.append(dict(role=role,timings=r['timings'],capacity=r['capacity'],build_audit=r['build_audit'],
            original_audit=r['original_audit'],tensor_checks_pass=r['tensor_checks']['pass_gate'],actual_array_hash=r['arrays']['sha256'],
            true_complete_N1='worker wall plus launcher/admission/output/independent audit; assembled in final collector; unknown stages not0'))
    return dict(status='COMPLETED',rows=rows,selection=selection(),artifact_root=str(ARTIFACT),
        learning_object='full physical FE+DtN coefficients bypassing measured preparation, audited by original equation',
        necessary_condition='fV-H >= .2 T_B; cold teacher, training, load, correction, audit all included',
        correctness_denominator='no new accurate baseline unless FLAT and adjacent fixed532 field/power gates pass',
        NN_trained=False,target_qualified=False,NN20_qualified=False,clock=window.snapshot())


def execute(role,folder,state):
    journal=Journal(folder,window_scope=window,planning_limit_bytes=16*2**30)
    if role=='BOUNDARY':
        from .scattering_accuracy_boundary import boundary_stage
        return boundary_stage(folder,journal,make_setup)
    if role=='ATTRIBUTION':
        from .scattering_accuracy_fields import saved_attribution
        r=saved_attribution(folder,journal,make_setup)
        r['saved_original_equation_rechecks']=saved_equation_attribution(folder,journal)
        return r
    if role=='SCREEN':
        from .scattering_accuracy_fields import representation_screen
        return representation_screen(folder,journal,make_setup)
    if role in SOLVES:return solve(role,folder,journal)
    if role=='VERIFY':return verify(folder,journal)
    if role=='COST':return cost(folder,journal)
    raise ValueError('V50 stage inventory')
