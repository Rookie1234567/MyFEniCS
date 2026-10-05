"""Finite complete Maxwell/DtN anchor and independent output consumers.

This opt-in adapter uses the existing local FE forms, exact cell condensation
and original uncondensed action. The reference factor is restricted to this
finite authority; it is never a production p4 inverse. Numerical data are
saved before derived summaries. No learned model is evaluated here.
"""
from __future__ import annotations

import contextlib
import gc
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import sparse
from scipy.linalg import lu_factor, lu_solve

from src.runners.task042_shared import write_json
from .scattering_anchor_scope import ROOT, ARTIFACT, plan_record, stage, window


def relative(delta, reference):
    return float(np.linalg.norm(delta) / max(np.linalg.norm(reference), 1e-30))


def array_hash(a):
    a = np.ascontiguousarray(a)
    return hashlib.sha256(a.dtype.str.encode()+str(a.shape).encode()+a.tobytes()).hexdigest()


def save_arrays(path, **arrays):
    path = Path(path)
    temp = path.with_suffix('.partial.npz')
    with temp.open('wb') as out:
        np.savez(out, **arrays)
        out.flush(); os.fsync(out.fileno())
    os.replace(temp, path)
    return {"path":str(path), "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "members":{k:{"shape":list(v.shape), "dtype":str(v.dtype), "sha256":array_hash(v)} for k,v in arrays.items()}}


class Journal:
    def __init__(self, folder):
        self.folder = Path(folder); self.began = time.perf_counter()
        self.timings = {}; self.lifetimes = []; self.calls = {"A":0, "AH":0, "factor":0}

    def event(self, name, **data):
        window.require_live()
        row = {"event":name, "elapsed_s":time.perf_counter()-self.began,
               "RSS_bytes":int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))*1024,
               "clock":window.snapshot(), **data}
        with (self.folder/'events.jsonl').open('a') as out:
            out.write(json.dumps(row, default=lambda x: x.item() if isinstance(x,np.generic) else str(x))+'\n');out.flush()
        print(name, round(row['elapsed_s'],3), flush=True)
        return row

    @contextlib.contextmanager
    def measured(self, name):
        start = time.perf_counter(); self.event(name+'_begin')
        try: yield
        finally:
            self.timings[name] = self.timings.get(name,0.)+time.perf_counter()-start
            self.event(name+'_end', seconds=self.timings[name])

    def allocation(self, name, facts):
        added = int(facts.get('matrix_payload_bytes',0))+int(facts.get('workspace_bytes',0))
        rss = int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))*1024
        self.event('allocation_'+name, planned_new_bytes=added)
        if rss+added > 8*2**30:
            raise MemoryError('finite anchor planned simultaneous allocation exceeds8GiB')


def configuration(case, degree=4):
    from src.common.config_3d import SimulationConfig3D
    from src.common.optical_material_table import load_si_optical_constants
    p=plan_record()['physical_descriptor']; axes=p['geometry']['axes_nm']
    material=load_si_optical_constants('0.7')
    s=7/135
    return SimulationConfig3D(
        case_name=f'task042_v49_{case.lower()}_p{degree}', stage_case='stage4_block_grating',
        geometry_kind='rectangular_block_grating', lambda0=.7, n_air=1+0j, mu_r=1+0j,
        n_substrate=material.n,n_grating=material.n,period_x=50*s,period_y=25*s,
        z_min=-10*s,z_max=130*s,air_height=130*s,substrate_thickness=10*s,
        grating_height=120*s,grating_width_x=17*s,grating_width_y=25*s,interface_z=0.,
        use_floquet_xy=True,use_pml=False,stage4_boundary_model='dtn_port',
        stage4_dtn_order_policy='manual',diffraction_zero_order_only=False,
        diffraction_order_max_m=9,diffraction_order_max_n=3,
        incident_theta_deg=89.,incident_phi_deg=5.,polarization_kind='s',custom_polarization=None,
        incident_amplitude=1+0j,nedelec_degree=degree,visualization_degree=degree,
        mesh_cell_type='hexahedron',mesh_spacing_mode='boundary_fitted',mesh_axis_cell_counts=(4,4,5),
        mesh_axis_x_values=tuple(axes['x']),mesh_axis_y_values=tuple(axes['y']),mesh_axis_z_values=tuple(axes['z']),
        mesh_axis_z_profile='task042.v49.frozen',mesh_plan_id='task042.v49.frozen',
        mesh_target_size=max(max(np.diff(a)) for a in axes.values()),
        diffraction_sample_count_x=32,diffraction_sample_count_y=32)


def make_setup(case, degree, journal):
    from mpi4py import MPI
    from dolfinx import mesh as dxmesh
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    cfg=configuration(case,degree)
    with journal.measured('mesh_MPC'):
        setup=_build_same_mesh_levels(cfg,MPI.COMM_SELF,(degree,),include_positive_coefficients=False)
        mesh=setup['mesh']; tags=setup['mesh_data'].cell_tags
        centers=dxmesh.compute_midpoints(mesh,3,tags.indices)
        regular=tags.values.copy(); values=regular.copy()
        if case=='NOTCH':
            box=np.array(plan_record()['physical_descriptor']['geometry']['notch_box_nm']).reshape(3,2)
            hit=np.all((centers >= box[:,0]) & (centers <= box[:,1]),axis=1) & (regular==cfg.tags.grating)
            if hit.sum()!=2:raise ValueError('genuine geometric notch must change exactly2Si cells')
            values[hit]=cfg.tags.air
            setup['mesh_data'].cell_tags=dxmesh.meshtags(mesh,3,tags.indices,values)
        return cfg,setup,{'cell_centers':centers,'cell_tags':values,'regular_tags':regular,
                          'geometry_x':mesh.geometry.x.copy(),'geometry_dofmap':mesh.geometry.dofmap.copy()}


def build_bundle(cfg,setup,journal):
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action, build_physical_rhs
    with journal.measured('JIT_tensor_CD_H_original_action'):
        bundle=build_same_mesh_physical_action(setup,cfg,cfg.nedelec_degree)
    with journal.measured('physical_RHS'):
        rhs,rf=build_physical_rhs(bundle)
    if len(bundle['modes'])!=532:raise ValueError('all532aliases required')
    journal.event('physical_objects_ready', mode_sha256=bundle['mode_sha256'], surface_q=bundle['dtn_quadrature_degree'],rhs_norm=rhs.norm())
    return bundle,rhs,rf


def boundary_support(bundle):
    mesh=bundle['setup']['mesh'];space=bundle['setup']['spaces'][bundle['degree']]
    mesh.topology.create_connectivity(2,3); links=mesh.topology.connectivity(2,3)
    groups=[]
    for tag in (bundle['cfg'].tags.z_min,bundle['cfg'].tags.z_max):
        groups.append(np.asarray(sorted({int(c) for f in bundle['setup']['mesh_data'].facet_tags.find(tag) for c in links.links(f)}),dtype=np.int32))
    byrow=tuple(0 if e.mode_identity['side']=='bottom' else 1 for e in bundle['dtn_action'].carrier.entries)
    return tuple(groups),byrow


def condense(bundle,journal):
    from dolfinx import fem
    from .hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
    from .p4_cell_condensed_inverse import assemble_condensed_ports,P4CellCondensedInverse
    cfg=bundle['cfg'];degree=bundle['degree'];space=bundle['setup']['spaces'][degree];floquet=bundle['setup']['floquets'][degree]
    groups,rowgroups=boundary_support(bundle)
    with journal.measured('condensation_local_factors'):
        compiled=fem.form(bundle['volume_action'].bilinear_form)
        system=build_unconstrained_assembly_time_condensation(compiled,space,bundle['setup']['mesh_data'].cell_tags,
            mpc=floquet.mpc,appended_global_rows=532,appended_support_owned_cell_groups=groups,
            appended_support_group_by_row=rowgroups,dense_appended_block=True,
            sum_duplicate_cell_integrals=True,strict_local_checks=True,defer_final_assembly=True,
            geometry_identity_policy='raw_unrounded',share_identity_cache=True,
            retain_local_schur_for_matrix_free=True,retain_local_original_for_native_audit=True)
        del compiled
        terms=assemble_condensed_ports(system,bundle['dtn_action'].carrier)
        inverse=P4CellCondensedInverse(system,None,port_terms=terms,owns_condensed=True,owns_factor=False)
    if degree==4 and (system.full_rows,system.active_rows,system.active_interior_rows)!=(17204,7232,8640):
        raise ValueError('frozen full native/trace/interior dimensions differ')
    if degree==4 and system.active_rows+532>10000:raise MemoryError('finite p4 authority row capacity')
    journal.event('condensed_objects_ready',rows=system.active_rows+532,nnz=int(system.matrix.getInfo()['nz_used']),
                  cell_classes=len(system.interior_lu_by_class),independent_FE=system.active_rows+system.active_interior_rows)
    return system,inverse


class DirectFactor:
    def __init__(self,matrix,journal):
        from petsc4py import PETSc
        self.ksp=None;self.factor=None;self.journal=journal
        with journal.measured('global_finite_factor_setup'):
            if PETSc.Sys.hasExternalPackage('mumps'):
                self.backend='PETSc_PREONLY_LU_MUMPS'
                self.ksp=PETSc.KSP().create(PETSc.COMM_SELF);self.ksp.setOperators(matrix)
                self.ksp.setType('preonly');pc=self.ksp.getPC();pc.setType('lu');pc.setFactorSolverType('mumps');self.ksp.setUp()
            else:
                from scipy.sparse.linalg import splu
                self.backend='SuperLU_COLAMD_FIXED_FALLBACK_BACKEND_UNAVAILABLE'
                ip,ix,v=matrix.getValuesCSR();csr=sparse.csr_matrix((v,ix,ip),shape=matrix.getSize())
                self.factor=splu(csr.tocsc(),permc_spec='COLAMD')
        journal.event('factor_present',backend=self.backend,factor_class='FINITE_AUTHORITY_EXACT_FACTOR_PRESENT')

    def solve_repeated(self,rhs,target):
        self.journal.calls['factor']+=1
        if self.ksp is not None:self.ksp.solve(rhs,target)
        else:target.array[:]=self.factor.solve(rhs.array)

    def destroy(self):
        if self.ksp is not None:self.ksp.destroy();self.ksp=None
        self.factor=None;gc.collect();self.journal.event('global_finite_factor_released')


def audit_original(bundle, rhs, solution, port, journal):
    """Independent original uncondensed volume+allDtN, not condensed CSR."""
    from petsc4py import PETSc
    target=rhs.duplicate()
    try:
        bundle['physical_action'].apply(solution,target);journal.calls['A']+=1
        native=rhs.array-target.array
        volume=bundle['volume_action'].apply(solution).array.copy()
        coupling=np.zeros_like(volume); projected=[];h=[]
        for e,a in zip(bundle['dtn_action'].carrier.entries,port,strict=True):
            np.add.at(coupling,e.coupling_rows,e.coupling_values*a)
            projected.append(np.dot(e.projection_values,solution.array[e.projection_rows]));h.append(e.normalization_h)
        projected=np.array(projected);h=np.array(h); pr=projected-h*port
        top=rhs.array-volume-coupling
        reconstructed=top.copy()
        for e,v in zip(bundle['dtn_action'].carrier.entries,pr,strict=True):
            np.add.at(reconstructed,e.coupling_rows,-e.coupling_values*v/e.normalization_h)
        # Uncondensed element oracle is retained independently by the system.
        norms={'true':relative(native,rhs.array),'native':relative(native,rhs.array),
               'augmented':relative(top,rhs.array),'port':relative(pr,projected),
               'identity':relative(native-reconstructed,np.maximum(np.abs(rhs.array),np.abs(target.array))),
               'slave_zero':bool(np.all(solution.array[bundle['setup']['floquets'][bundle['degree']].mpc.slaves]==0))}
        return norms,{'residual':native.copy(),'volume_action':volume,'coupling_action':coupling,
                      'augmented_residual':top,'port_residual':pr,'projected':projected,'H':h}
    finally:target.destroy()


def reference(case,degree,folder,journal):
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    cfg,setup,geometry=make_setup(case,degree,journal)
    bundle=rhs=system=inverse=solution=factor=None
    try:
        bundle,rhs,rf=build_bundle(cfg,setup,journal)
        system,inverse=condense(bundle,journal)
        factor=DirectFactor(system.matrix,journal);inverse.factor=factor
        with journal.measured('solve_and_minimal_internal_recovery'):
            solution=inverse.apply(rhs)
            port=inverse.last_port_solution.copy()
        with journal.measured('original_audit'):
            norms,vectors=audit_original(bundle,rhs,solution,port,journal)
        refinements=[]
        for count in range(2):
            if max(norms['true'],norms['augmented'],norms['port'])<=1e-10:break
            correction=rhs.duplicate();correction.array[:]=vectors['residual']
            with journal.measured('fixed_refinement'):
                delta=inverse.apply(correction);solution.axpy(1,delta);port+=inverse.last_port_solution
            delta.destroy();correction.destroy()
            norms,vectors=audit_original(bundle,rhs,solution,port,journal);refinements.append(dict(norms))
        arrays=save_arrays(folder/'solution.npz',u_storage=solution.array.copy(),port=port,rhs=rhs.array.copy(),
            independent=np.setdiff1d(np.arange(system.full_rows),setup['floquets'][degree].mpc.slaves),
            slaves=np.asarray(setup['floquets'][degree].mpc.slaves),**geometry,**vectors)
        journal.event('minimal_recovery_packet_saved',npz_sha256=arrays['sha256'])
        inverse.factor=None;factor.destroy();factor=None
        # The original FFCx forms/action survive factor/matrix release.
        system.matrix.destroy();system.matrix=None;gc.collect();journal.event('condensed_matrix_released')
        output=outputs(bundle,solution,port,folder,journal)
        return {'status':'COMPLETED','case':case,'degree':degree,'engine':'FULL3D_ASSEMBLY_TIME_EXACT_REFERENCE',
                'arrays':arrays,'original_audit':norms,'fixed_refinements':refinements,'output':output,
                'dimensions':{'native':system.full_rows,'trace':system.active_rows,'internal':system.active_interior_rows,'ports':532},
                'RHS':rf,'timings':journal.timings,'calls':journal.calls,'cold_N1':'process/numerical preparation cold; OS/JIT cache state recorded',
                'equation_pass':max(norms['true'],norms['native'],norms['augmented'],norms['port'])<=1e-6 and norms['identity']<=1e-10 and norms['slave_zero']}
    finally:
        if factor is not None:factor.destroy()
        if solution is not None:solution.destroy()
        if rhs is not None:rhs.destroy()
        if inverse is not None:inverse.destroy()
        if bundle is not None:destroy_same_mesh_physical_action(bundle)


def outputs(bundle,solution,port,folder,journal):
    """Full complex FE/DG fields, selected fields and all modal powers."""
    from dolfinx import fem
    from basix.ufl import element
    import ufl
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from .dtn_port_3d import _port_power_metrics,_write_port_outputs
    from src.common.modes_3d import incident_power_3d
    from src.postprocessing.rta_3d import compute_volume_absorption_3d
    from .common_3d_fields import stage4_layered_background_field
    cfg=bundle['cfg'];setup=bundle['setup'];degree=bundle['degree']
    with journal.measured('field_EH_curl_output'):
        E=restore_p0_full_field(setup['floquets'][degree],solution)
        bg=stage4_layered_background_field(E.function_space,cfg)
        es=fem.Function(E.function_space);es.x.array[:]=E.x.array-bg.x.array;es.x.scatter_forward()
        V=fem.functionspace(setup['mesh'],element('DG',setup['mesh'].basix_cell(),degree,shape=(3,)))
        pts=V.element.interpolation_points
        if callable(pts):pts=pts()
        vals={}
        for name,expr in (('E_total',E),('E_scattered',es),('curl_total',ufl.curl(E)),('curl_scattered',ufl.curl(es)),
                          ('H_total',ufl.curl(E)/(1j*cfg.k0*cfg.mu_r)),('H_scattered',ufl.curl(es)/(1j*cfg.k0*cfg.mu_r))):
            f=fem.Function(V);f.interpolate(fem.Expression(expr,pts));vals[name]=f.x.array.copy()
        vals['field_coordinates']=V.tabulate_dof_coordinates()
        # Fixed independent physical points: actual cell centers, one per cell.
        centers=np.load(folder/'solution.npz')['cell_centers'];cells=np.arange(len(centers),dtype=np.int32)
        vals['selected_points']=centers
        vals['selected_E_total']=E.eval(centers,cells);vals['selected_E_scattered']=es.eval(centers,cells)
        for name in ('H_total','H_scattered','curl_total','curl_scattered'):
            f=fem.Function(V);f.x.array[:]=vals[name];vals['selected_'+name]=f.eval(centers,cells)
        fields=save_arrays(folder/'fields.npz',**vals)
    with journal.measured('all532_modes_power_absorption'):
        pm=_port_power_metrics(cfg,list(bundle['modes']),port,list(bundle['incident_projections']))
        _write_port_outputs(folder,cfg,list(bundle['modes']),port,list(bundle['incident_projections']),pm,setup['mesh'].comm)
        vm=compute_volume_absorption_3d(setup['mesh_data'],cfg,E,folder,incident_power=incident_power_3d(cfg),port_metrics=pm)
    return {'fields':fields,'port_metrics':pm,'volume_metrics':vm,'mode_manifest_sha256':bundle['mode_sha256'],
            'surface_quadrature_degree':bundle['dtn_quadrature_degree'], 'time_convention':'exp(-i omega t)',
            'H_units':'code units: curl(E)/(i*k0*mu); physical A/m multiply1/eta0',
            'field_comparison_floor':1e-12,'energy_limit':1e-5,'total_scattered_definition':'original layered background subtracted in full native FE space'}


def small_condensation_witness():
    rng=np.random.default_rng(49001);a=rng.normal(size=(7,7))+1j*rng.normal(size=(7,7))+8*np.eye(7)
    b=rng.normal(size=(7,40))+1j*rng.normal(size=(7,40));d=rng.normal(size=(40,7))+1j*rng.normal(size=(40,7));h=50*np.eye(40)+rng.normal(size=(40,40))+1j*rng.normal(size=(40,40))
    full=np.block([[a,b],[-d,h]]);r=rng.normal(size=47)+1j*rng.normal(size=47)
    i=np.array([0,1,2]);t=np.array([3,4,5,6]);order=np.r_[t,7+np.arange(40)]
    Ai=full[np.ix_(i,i)];Li=full[np.ix_(order,i)];Ri=full[np.ix_(i,order)]
    S=full[np.ix_(order,order)]-Li@np.linalg.solve(Ai,Ri)
    red=r[order]-Li@np.linalg.solve(Ai,r[i]);z=np.linalg.solve(S,red);u=np.empty(47,complex);u[order]=z;u[i]=np.linalg.solve(Ai,r[i]-Ri@z)
    err=relative(full@u-r,r)
    if err>1e-12:raise ValueError('nonHermitian nonmutual40port affine condensation')
    return {'relative':err,'nonzero_internal':True,'nonzero40port':True,'F_not_C_H':True}


def engine(case,folder,journal):
    """Unchanged published FGMRES32, complete four-q regular reference.

    Local new ABI constructs the full80 bounded condensed reference before
    extracting all four branches. This replaces donor ignored authority readers
    and two40 assembly preparation only; the full regular inverse, primal/dual
    coordinates, outer original equation and all aliases are unchanged. It is
    not claimed to reproduce donor construction cost or run-source bytes.
    """
    from petsc4py import PETSc
    from scipy.sparse.linalg import splu
    from .scattering_y_orbit_reuse import build_y_orbit_layout,trace_layout_coordinates,FullOriginalAction,solve_notched_fgmres
    from .fullspace_same_mesh_hcurl_pmg_physical import build_physical_rhs,_build_split_volume_action,destroy_same_mesh_physical_action
    from .fullspace_physical_action import FullspacePhysicalAction
    from dolfinx import mesh as dxmesh
    cfg,setup,geometry=make_setup('REGULAR',4,journal)
    bundle=rhs=system=inverse=action=target_bundle=solution=None
    branch_factors=[];maps=[]
    try:
        bundle,rhs,rf=build_bundle(cfg,setup,journal)
        system,inverse=condense(bundle,journal)
        with journal.measured('canonical_mapping_all4q_factors'):
            layout=build_y_orbit_layout(setup['spaces'][4],setup['floquets'][4],cfg,
                plan_record()['physical_descriptor']['geometry']['axes_nm'])
            trace=trace_layout_coordinates(layout,system,allocation_gate=journal.allocation)
            qt=(trace['R_t']@trace['F_t']).tocsr()
            ip,ix,vd=system.matrix.getValuesCSR();csr=sparse.csr_matrix((vd,ix,ip),shape=system.matrix.getSize())
            h=np.array([e.normalization_h for e in bundle['dtn_action'].carrier.entries])
            branch_checks=[]
            for q in range(4):
                ids=np.array([i for i,m in enumerate(bundle['modes']) if int(m.n)%4==q],dtype=int)
                pm=sparse.csr_matrix((1/np.sqrt(h[ids]),(ids,np.arange(len(ids)))),shape=(532,len(ids)))
                qm=sparse.block_diag((qt[:,q*trace['trace_width']:(q+1)*trace['trace_width']],pm),format='csr')
                matrix=(qm.conj().T@csr@qm).tocsc()
                journal.allocation('q_'+str(q)+'_factor',{'matrix_payload_bytes':sum(a.nbytes for a in (matrix.data,matrix.indices,matrix.indptr)), 'workspace_bytes':128*2**20})
                factor=splu(matrix,permc_spec='COLAMD')
                w=np.cos(np.arange(matrix.shape[0])*.37)+1j*np.sin(np.arange(matrix.shape[0])*.23)
                x=factor.solve(w);err=relative(matrix@x-w,w)
                if err>1e-10:raise ValueError('newABI complete regular q factor residual')
                maps.append(qm);branch_factors.append(factor)
                branch_checks.append({'q':q,'rows':matrix.shape[0],'aliases':len(ids),'residual':err,'nnz':matrix.nnz})
                del matrix
            del csr,vd,ix,ip

        class ModalFactor:
            def solve_repeated(self,b,x):
                out=np.zeros(system.active_rows+532,complex)
                for qm,f in zip(maps,branch_factors,strict=True):out+=qm@f.solve(np.asarray(qm.conj().T@b.array))
                x.array[:]=out;journal.calls['factor']+=4

        inverse.factor=ModalFactor()

        class CompleteInverse:
            def apply_array(self,b):
                r=PETSc.Vec().createSeq(layout.full_rows,comm=PETSc.COMM_SELF);r.set(0);r.array[layout.independent]=b
                try:
                    x=inverse.apply(r)
                    try:return x.array[layout.independent].copy()
                    finally:x.destroy()
                finally:r.destroy()
            def apply(self,_pc,b,x):x.array[:]=self.apply_array(b.array)

        pc=CompleteInverse()
        # New independent real-action qualification before using this exact PC.
        rng=np.random.default_rng(49003);w=rng.standard_normal(len(layout.independent))+1j*rng.standard_normal(len(layout.independent))
        action=FullOriginalAction(bundle['physical_action'],layout)
        xp=pc.apply_array(w);defect=relative(action.apply(xp)-w,w)
        if defect>1e-10:raise ValueError('all4q regular inverse real uncondensed identity')
        journal.event('all4q_inverse_qualified',true_defect=defect,branch_checks=branch_checks)
        target_bundle=bundle
        if case=='NOTCH':
            tags=setup['mesh_data'].cell_tags;centers=geometry['cell_centers']
            box=np.array(plan_record()['physical_descriptor']['geometry']['notch_box_nm']).reshape(3,2)
            hit=np.all((centers>=box[:,0])&(centers<=box[:,1]),axis=1)&(tags.values==cfg.tags.grating)
            if hit.sum()!=2:raise ValueError('original notch physical cell inventory')
            values=tags.values.copy();values[hit]=cfg.tags.air;geometry['cell_tags']=values
            # PC bundle keeps original regular tags; target has independent tags.
            target_setup=dict(setup);target_mesh=SimpleNamespace(mesh=setup['mesh'],facet_tags=setup['mesh_data'].facet_tags,
                cell_tags=dxmesh.meshtags(setup['mesh'],3,tags.indices,values))
            target_setup['mesh_data']=target_mesh;target_cfg=configuration('NOTCH')
            with journal.measured('notch_original_volume'):
                volume=_build_split_volume_action(target_mesh,target_cfg,setup['spaces'][4],setup['floquets'][4],jit_options={})
                physical=FullspacePhysicalAction(volume,bundle['dtn_action'],owns_dtn=False)
            target_bundle={**bundle,'cfg':target_cfg,'setup':target_setup,'volume_action':volume,'physical_action':physical,'action':physical}
            action.close();action=FullOriginalAction(physical,layout)
            rhs.destroy();rhs,rf=build_physical_rhs(target_bundle)
        b=rhs.array[layout.independent].copy()
        with journal.measured('outer_original_FGMRES32'):
            u,krylov=solve_notched_fgmres(action,pc,b)
        solution=rhs.duplicate();solution.set(0);solution.array[layout.independent]=u
        port=target_bundle['dtn_action'].recover_auxiliary(solution).copy()
        # Persist the returned state before any expensive/fragile output.
        arrays=save_arrays(folder/'solution.npz',u_storage=solution.array.copy(),port=port,rhs=rhs.array.copy(),
            independent=layout.independent,slaves=np.asarray(setup['floquets'][4].mpc.slaves),**geometry)
        write_json(folder/'returned_state.json',{'arrays':arrays,'krylov':krylov,'audit_pending':True})
        norms,vectors=audit_original(target_bundle,rhs,solution,port,journal)
        residual_packet=save_arrays(folder/'audit_vectors.npz',**vectors)
        journal.calls['A']+=action.calls
        # Release all global/q factors and the condensed matrix before fields.
        inverse.factor=None;branch_factors.clear();maps.clear();gc.collect()
        system.matrix.destroy();system.matrix=None;journal.event('all4q_factors_matrix_released')
        output=outputs(target_bundle,solution,port,folder,journal)
        return {'status':'COMPLETED','case':case,'degree':4,'engine':'ALL4Q_REGULAR_REFERENCE_RIGHT_FGMRES32',
                'construction_adapter':'full80 local newABI condensed preparation; donor two40 authority readers not reused',
                'all_q':[0,1,2,3],'branch_checks':branch_checks,'PC_real_action_defect':defect,
                'arrays':arrays,'audit_arrays':residual_packet,'original_audit':norms,'krylov':krylov,'output':output,
                'RHS':rf,'timings':journal.timings,'calls':journal.calls,
                'equation_pass':max(norms['true'],norms['native'],norms['augmented'],norms['port'])<=1e-6 and norms['identity']<=1e-10 and norms['slave_zero']}
    finally:
        if action is not None:action.close()
        if solution is not None:solution.destroy()
        if rhs is not None:rhs.destroy()
        branch_factors.clear();maps.clear()
        if inverse is not None:inverse.destroy()
        if target_bundle is not None and target_bundle is not bundle:target_bundle['physical_action'].destroy()
        if bundle is not None:destroy_same_mesh_physical_action(bundle)


def verify(folder,journal):
    """Only this post-freeze process opens reference scientific arrays."""
    # The verified same-mesh fields are saved in identical complete DG order;
    # selected points and all original mode keys are also compared independently.
    rows=[]
    for case in ('REGULAR','NOTCH'):
        ref=stage('REFERENCE_'+case);candidate=stage('ENGINE_'+case)
        for packet in (ref,candidate):
            for item in (packet['arrays'],packet['output']['fields']):
                if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('frozen state bytes/hash')
        with np.load(ref['output']['fields']['path']) as r,np.load(candidate['output']['fields']['path']) as c:
            fields={name:relative(c[name]-r[name],r[name]) for name in r.files if name not in ('field_coordinates','selected_points')}
            if not np.array_equal(r['field_coordinates'],c['field_coordinates']) or not np.array_equal(r['selected_points'],c['selected_points']):raise ValueError('canonical same-mesh DG point inventory')
        with np.load(ref['arrays']['path']) as r,np.load(candidate['arrays']['path']) as c:
            channels=relative(c['port']-r['port'],r['port'])
            coefficients=relative(c['u_storage']-r['u_storage'],r['u_storage'])
        rp=ref['output']['port_metrics'];cp=candidate['output']['port_metrics']
        # Original approved metrics are preserved; exact keys are checked,
        # no conservation normalization or phase adjustment is made here.
        keys=[k for k in ('R_total','T_total','A_total','R','T','A') if k in rp and isinstance(rp[k],(int,float))]
        powers={k:abs(cp[k]-rp[k]) for k in keys}
        rows.append({'case':case,'fields':fields,'complex_channels':channels,'coefficients':coefficients,
                     'power_differences':powers,'candidate_equation_pass':candidate['equation_pass'],
                     'same_discrete_field_pass':max([channels,*fields.values()])<=1e-4,
                     'reference_original_audit':ref['original_audit'],'candidate_original_audit':candidate['original_audit']})
    write_json(folder/'pair_checks.json',rows)
    return {'status':'COMPLETED','pairs':rows,'reference_read_after_candidates_frozen':True,
            'TARGET_NOT_QUALIFIED':True,'NN_NOT_TRAINED_THIS_BATCH':True}


def cost_report(folder,journal):
    rows=[]
    for name in ('REFERENCE_REGULAR','REFERENCE_NOTCH','ENGINE_REGULAR','ENGINE_NOTCH','REFERENCE_NOTCH_P5'):
        try:r=stage(name)
        except FileNotFoundError:rows.append({'stage':name,'status':'not_run'});continue
        rows.append({'stage':name,'timings':r['timings'],'calls':r['calls'],'arrays':r['arrays'],
                     'equation_pass':r['equation_pass'],'training_seconds':0,'process_numerical_preparation_cold':True,
                     'OS_cache_flushed':False,'full_deployment_unknown':[]})
    return {'status':'COMPLETED','routes':rows,'research_ledger':window.ledger(),
            'NN_NOT_TRAINED_THIS_BATCH':True,'TARGET_NOT_QUALIFIED':True,
            'opportunity':'rank actual inclusive coldN1 phases after full observable qualification; no automatic new training'}


def execute(role,folder,state):
    folder=Path(folder);j=Journal(folder)
    if role=='PREFLIGHT':
        from petsc4py import PETSc
        import dolfinx,basix,mpi4py
        cfg=configuration('REGULAR')
        from .fullspace_dtn_action import build_dynamic_mode_inventory
        modes,rows,digest=build_dynamic_mode_inventory(cfg)
        from .dtn_port_3d import _dtn_surface_quadrature_degree
        if len(modes)!=532 or np.dtype(PETSc.ScalarType)!=np.dtype(np.complex128):raise ValueError('FE/mode gate')
        return {'status':'COMPLETED','witness':small_condensation_witness(),'mode_count':len(modes),'mode_sha256':digest,
                'surface_q':_dtn_surface_quadrature_degree(cfg,list(modes)), 'PETSc_scalar':str(PETSc.ScalarType),'PETSc_int':str(PETSc.IntType),
                'condensed_rows':7764,'full_dense_single_payload_bytes':7764**2*16,'planned_peak_bytes':8*2**30,
                'backend_mumps_available':PETSc.Sys.hasExternalPackage('mumps'),'NN_trained':False}
    if role.startswith('REFERENCE_'):
        degree=5 if role.endswith('_P5') else 4
        case='REGULAR' if role=='REFERENCE_REGULAR' else 'NOTCH'
        return reference(case,degree,folder,j)
    if role.startswith('ENGINE_'):
        return engine(role.removeprefix('ENGINE_'),folder,j)
    if role=='VERIFY_P4':return verify(folder,j)
    if role=='COST':return cost_report(folder,j)
    raise ValueError('unknown complete scattering stage')
