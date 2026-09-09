"""One bounded condensed reference; release LU before native A6 verification.

The observer exits with evidence and never returns a no-global-factor snapshot.
Exactly one augmented correction precedes release; no native correction/rebuild.
"""
import numpy as np

from .condensed_reference_preflight import CondensedPreflightExit, retained_payload


class FineReferenceExit(CondensedPreflightExit):
    pass


class FineReferenceCapacityRejected(RuntimeError):
    pass


def native_map_arrays(space,floquet):
    """Read the borrowed finalized mesh/space/MPC; allocate no new FE objects."""
    from .fullspace_physical_intermediate_runtime import owned_slave_indices
    mesh=space.mesh;mesh.topology.create_entity_permutations()
    coefficients,offsets=floquet.mpc.coefficients()
    rows=space.dofmap.index_map.size_local*space.dofmap.index_map_bs
    return dict(dofmap=np.array(space.dofmap.list),geometry=np.array(mesh.geometry.x),
        geometry_dofmap=np.array(mesh.geometry.dofmap),permutations=np.array(mesh.topology.get_cell_permutation_info()),
        slaves=np.array(floquet.mpc.slaves),masters=np.array(floquet.mpc.masters.array),
        coefficients=np.array(coefficients),offsets=np.array(offsets),
        independent_indices=np.setdiff1d(np.arange(rows),owned_slave_indices(space,floquet)))


def project_unconstrained_mpc_dual(values,mapping):
    """C^H of a full unconstrained MPI1 load, never a zero-slave residual inverse."""
    values=np.asarray(values);n=len(values)
    slaves,masters,offsets,coefficients=(mapping[k] for k in ('slaves','masters','offsets','coefficients'))
    if (values.ndim!=1 or not np.isfinite(values).all() or len(offsets)!=n+1
        or offsets[0]!=0 or offsets[-1]!=len(masters) or len(masters)!=len(coefficients)
        or np.any(np.diff(offsets)<0) or not np.isfinite(coefficients).all()
        or np.any(slaves<0) or np.any(slaves>=n) or np.any(masters<0) or np.any(masters>=n)
        or len(np.unique(slaves))!=len(slaves) or len(np.intersect1d(slaves,masters))):
        raise ValueError('invalid finalized MPI1 MPC load mapping')
    result=values.copy()
    for slave in slaves:
        start,end=offsets[slave:slave+2]
        np.add.at(result,masters[start:end],np.conj(coefficients[start:end])*values[slave])
    result[slaves]=0
    return result


def pre_numeric_rhs_gate(full_rhs,mapping,witness,actual_degree,expected_degree,save):
    """Save the exact load comparison, and reject before symbolic/numeric."""
    mismatched=[key for key,value in mapping.items() if not np.array_equal(value,witness['map'][key])]
    if mismatched:
        save('reference_pre_numeric_rhs',dict(status='MAPPING_REJECTED',mismatched=mismatched))
        raise ValueError('pre-numeric native map mismatch: '+','.join(mismatched))
    projected=project_unconstrained_mpc_dual(full_rhs,mapping)
    native=witness['rhs']['b'];indices=mapping['independent_indices']
    relative=relative_difference(projected[indices],native)
    facts=dict(status='RHS_PASS' if relative<=1e-10 and actual_degree==expected_degree else 'RHS_REJECTED',
        relative_difference=relative,limit=1e-10,actual_incident_quadrature_degree=actual_degree,
        expected_native_quadrature_degree=expected_degree,map_exact=True,
        definition='C^H of borrowed unconstrained full RHS compared with frozen native independent b')
    save('reference_pre_numeric_rhs',dict(**facts,projected_full_rhs=projected,
        native_independent_rhs=native,difference=projected[indices]-native,witness=witness['evidence']))
    if facts['status']!='RHS_PASS':raise ValueError('pre-numeric original RHS/quadrature mismatch')
    return facts


def numeric_allowance(resource, raw_info, future_bytes):
    """Single ICNTL23 allocation cap, with an explicit engineering reserve."""
    reserve=512*1024**2
    estimate=max(int(raw_info['infog'][str(i)]) for i in (16,17))
    hard_cap=int(resource['launch_cap_bytes'])
    planning_cap=int(resource.get('numeric_planning_cap_bytes',hard_cap))
    allocation_cap=min(hard_cap,planning_cap)
    available=allocation_cap-int(resource['rss_bytes'])-int(future_bytes)-reserve
    limit_mb=available//1_000_000
    return dict(status='ADMISSIBLE' if estimate>0 and limit_mb>=estimate else 'CAPACITY_NOT_ADMITTED',
        baseline_tree_rss_bytes=int(resource['rss_bytes']),dynamic_cap_bytes=allocation_cap,
        hard_cap_bytes=hard_cap,numeric_planning_cap_bytes=planning_cap,
        future_bytes=int(future_bytes),engineering_reserve_bytes=reserve,
        icntl23_mb=int(limit_mb),symbolic_estimate_mb=estimate,
        units='decimal MB',classification='bounded_allocation_policy_not_peak_prediction',
        uncertainty='symbolic baseline can overlap MUMPS estimate; allocator/pivot/workspaces remain uncertain',
        verification_lifecycle='LU released before native A6/RHS compilation and verification')


def solve_and_release(request, record, *, sample, marker, save, factor_factory=None):
    """One symbolic/numeric and two MatSolve calls; release before recovery."""
    from .fullspace_v17_p3_oracle import _MumpsFactor
    system=request.static_condensed_system
    factor=None;x=original=residual=delta=None
    try:
        x=request.b.duplicate();x.set(0)
        factor=(factor_factory or _MumpsFactor)(request.A)
        marker('fine_reference_symbolic_started',{})
        factor.symbolic(request.A);record['symbolic_calls']=1
        record['symbolic_info']=factor.info((22,29))
        record['controls_before']=factor.symbolic_memory_settings()
        # Recovery runs after LU release. These conservative vector allowances
        # nevertheless remain reserved during numeric; native actions are absent.
        future=8*system.full_rows*16+4*(system.active_rows+system.appended_rows)*16
        future+=system.interior_rows*16+2*system.active_rows*16
        record['admission']=numeric_allowance(sample(),record['symbolic_info'],future)
        save('reference_numeric_admission',record)
        if record['admission']['status']!='ADMISSIBLE':
            raise FineReferenceCapacityRejected('single ICNTL23 allowance below symbolic estimate')
        factor.set_memory_limit_mb(record['admission']['icntl23_mb'])
        record['controls_numeric']=factor.symbolic_memory_settings()
        marker('fine_reference_numeric_started',record['admission'])
        sample();record['numeric_called']=True
        factor.numeric(request.A);record['numeric_calls']=1
        record['numeric_info']=factor.info((22,29))
        marker('fine_reference_numeric_completed',record['numeric_info'])
        save('reference_numeric',record)
        sample();marker('fine_reference_solve_started',{})
        record['solve_called']=True
        factor.solve(request.b,x);record['solve_calls']=1
        marker('fine_reference_solve_completed',{})
        if not np.isfinite(x.array).all():raise ValueError('nonfinite condensed solution')
        original=x.copy();residual=x.duplicate();delta=x.duplicate()
        request.A.mult(x,residual);residual.aypx(-1,request.b)
        denominator=float(request.b.norm())
        if denominator==0:raise ValueError('zero augmented incident RHS')
        record['augmented_relative_before']=float(residual.norm()/denominator)
        save('reference_augmented_initial',dict(x=original.array,rhs=request.b.array,
            residual=residual.array,relative_residual=record['augmented_relative_before'],
            identity=record['identity'],qualified=False))
        marker('fine_reference_augmented_correction_started',{})
        sample();factor.solve_repeated(residual,delta);record['solve_calls']=2
        record['correction_calls']=1
        if not np.isfinite(delta.array).all():raise ValueError('nonfinite augmented correction')
        record['augmented_delta_relative']=float(delta.norm()/max(original.norm(),np.finfo(float).tiny))
        x.axpy(1,delta);request.A.mult(x,residual);residual.aypx(-1,request.b)
        record['augmented_relative_after']=float(residual.norm()/denominator)
        save('reference_augmented_corrected',dict(x=x.array,delta=delta.array,residual=residual.array,
            relative_residual=record['augmented_relative_after'],delta_relative=record['augmented_delta_relative'],
            identity=record['identity'],qualified=False,kind='one fixed augmented correction; not native A6 refinement'))
        marker('fine_reference_augmented_correction_completed',dict(
            before=record['augmented_relative_before'],after=record['augmented_relative_after'],
            delta_relative=record['augmented_delta_relative']))
    except BaseException:
        if x is not None:x.destroy();x=None
        if original is not None:original.destroy();original=None
        raise
    finally:
        for value in (residual,delta):
            if value is not None:
                try:value.destroy()
                except Exception as exc:
                    record['cleanup_errors'].append(dict(type=type(exc).__name__,message=str(exc)))
        if factor is not None:
            try:factor.destroy()
            except Exception as exc:
                record['cleanup_errors'].append(dict(type=type(exc).__name__,message=str(exc)))
        record['factor_released']=not record['cleanup_errors']
    if record['cleanup_errors']:
        x.destroy();original.destroy()
        raise RuntimeError('factor cleanup failed; native verification forbidden')
    try:marker('fine_reference_factor_released',{})
    except BaseException:
        x.destroy();original.destroy()
        raise
    return original,x


def relative_difference(left,right):
    if left.shape!=right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError('incompatible/nonfinite identity vectors')
    return float(np.linalg.norm(left-right)/max(np.linalg.norm(right),np.finfo(float).tiny))


def residual_packet(x,b,ax,slaves):
    """Full native independent norm, with zero-slave storage verified explicitly."""
    for value in (x,b,ax):
        if value.shape!=b.shape or not np.isfinite(value).all() or np.any(value[slaves]!=0):
            raise ValueError('invalid native vector or nonzero slave row')
    norm=float(np.linalg.norm(b))
    if norm==0:raise ValueError('reference incident RHS is zero')
    residual=b-ax
    relative=float(np.linalg.norm(residual)/norm)
    return dict(x_ref=x,b=b,ax=ax,r=residual,relative_residual=relative,
        residual_limit=1e-10,status='REFERENCE_PASS' if relative<=1e-10 else 'REFERENCE_ACCURACY_UNRESOLVED',
        roles=dict(x_ref='primal zero-slave full storage',b='dual independent zero-slave',
                   ax='dual independent zero-slave',r='b-A6x_ref'),
        definition='native split exact volume plus streaming DtN; full independent norm')


class MatchedFineReference:
    def __init__(self,*,sample,save,marker,identity,witness,canonical_export, output_callback=None):
        self.sample,self.save,self.marker=sample,save,marker
        self.identity,self.witness,self.canonical_export=identity,witness,canonical_export
        self.output_callback=output_callback

    def __call__(self,request):
        from .dtn_port_3d import _assign_fe_solution_from_assembly_time_condensation
        from .fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata,owned_slave_indices
        from .fullspace_same_mesh_hcurl_pmg_physical import (
            build_same_mesh_physical_action,destroy_same_mesh_physical_action,build_physical_rhs)
        from .physical_error_metric import SerialAction
        record=dict(status='REFERENCE_STARTED',identity=self.identity,symbolic_calls=0,
            numeric_called=False,solve_called=False,numeric_calls=0,solve_calls=0,
            correction_calls=0,cleanup_errors=[],factor_released=False)
        x_aug=x_aug_initial=x=b=bridge=None;native={};error=None
        try:
            system=request.static_condensed_system
            if request.A.getComm().getSize()!=1 or request.full_rhs is None or request.mesh_data is None:
                raise ValueError('reference requires borrowed MPI1 mesh and full RHS')
            if (system.full_rows,request.n_fe,request.n_aux)!=(173802,51192,80):
                raise ValueError('frozen fine reference dimensions differ')
            record.update(retained_payload=retained_payload(system),matrix_info=request.A.getInfo(),
                          lifecycle='one augmented correction then LU release before recovery/native compile; no native refinement/rebuild')
            self.save('reference_assembled',record)
            from .dtn_port_3d import _dtn_surface_quadrature_degree
            from src.common.modes_3d import outgoing_port_modes_3d
            self.marker('fine_reference_rhs_gate_started',{})
            mapping=native_map_arrays(request.function_space,request.floquet_data)
            record['pre_numeric_rhs']=pre_numeric_rhs_gate(request.full_rhs.array,mapping,self.witness,
                request.incident_traction_quadrature_degree,
                _dtn_surface_quadrature_degree(request.config,outgoing_port_modes_3d(request.config)),self.save)
            self.save('reference_pre_numeric_map',dict(**mapping,identity=self.identity))
            del mapping
            self.marker('fine_reference_rhs_gate_completed',record['pre_numeric_rhs']);self.sample()
            x_aug_initial,x_aug=solve_and_release(request,record,sample=self.sample,marker=self.marker,save=self.save)
            self.sample();self.marker('fine_reference_recovery_started',{})
            initial_field,initial_x,initial_recovery=_assign_fe_solution_from_assembly_time_condensation(
                x_aug_initial,system,request.floquet_data,request.full_rhs)
            try:
                self.save('reference_candidate_initial',dict(x_ref=initial_x.array,
                    identity=self.identity,qualified=False,recovery=initial_recovery))
            finally:
                initial_x.destroy();del initial_field
            x_aug_initial.destroy();x_aug_initial=None
            field,x,recovery=_assign_fe_solution_from_assembly_time_condensation(
                x_aug,system,request.floquet_data,request.full_rhs)
            record['recovery']=recovery
            # Save an unqualified candidate even if subsequent compilation fails.
            self.save('reference_candidate',dict(x_ref=np.array(x.array,copy=True),
                x_aug=np.array(x_aug.array,copy=True),full_unconstrained_rhs=np.array(request.full_rhs.array,copy=True),
                identity=self.identity,qualified=False,recovery=recovery))
            x_aug.destroy();x_aug=None
            self.marker('fine_reference_recovery_completed',recovery)
            self.sample();self.marker('fine_reference_native_compile_started',{})
            space=request.function_space;mesh=space.mesh;floquet=request.floquet_data
            setup=dict(mesh=mesh,mesh_data=request.mesh_data,spaces={6:space},floquets={6:floquet})
            quadrature,integrals=fine_volume_quadrature_metadata(setup,request.config)
            native=build_same_mesh_physical_action(setup,request.config,6,volume_quadrature_metadata=quadrature)
            b,bfacts=build_physical_rhs(native)
            bridge=SerialAction(space,floquet,native['physical_action'].apply)
            record.update(quadrature=quadrature,integrals=integrals,native_rhs=bfacts,
                          native_mode_sha256=native['mode_sha256'])
            if native['mode_sha256']!=self.identity['mode_sha256']:raise ValueError('native mode mismatch')
            self.marker('fine_reference_native_compile_completed',{});self.sample()
            mapping=native_map_arrays(space,floquet)
            self.save('reference_native_map',dict(**mapping,ownership=list(x.getOwnershipRange()),identity=self.identity))
            for key,value in mapping.items():
                if not np.array_equal(value,self.witness['map'][key]):raise ValueError('native frozen map mismatch: '+key)
            self.marker('fine_reference_identity_started',{})
            ax_control=bridge(self.witness['control']['x'])
            checks=dict(frozen_A6_action=relative_difference(ax_control,self.witness['control']['ax']),
                        frozen_rhs=relative_difference(b.array[bridge.indices],self.witness['rhs']['b']),
                        repeated_A6_action=relative_difference(bridge(self.witness['control']['x']),ax_control))
            self.save('reference_identity',dict(checks=checks,quadrature=quadrature,identity=self.identity,
                native_control_ax=ax_control,witness=self.witness['evidence']))
            if max(checks.values())>1e-10:raise ValueError('frozen original A6/RHS bridge mismatch')
            self.marker('fine_reference_identity_completed',checks);self.sample()
            self.marker('fine_reference_residual_started',{})
            ax=x.duplicate()
            try:
                before=np.array(x.array,copy=True)
                native['physical_action'].apply(x,ax)
                if not np.array_equal(before,x.array):raise ValueError('native A6 mutated reference input')
                packet=residual_packet(np.array(x.array,copy=True),np.array(b.array,copy=True),
                    np.array(ax.array,copy=True),owned_slave_indices(space,floquet))
                packet.update(identity=self.identity,ownership=list(x.getOwnershipRange()),
                              witness=self.witness['evidence'],quadrature=quadrature,input_unchanged=True)
                # Failure vectors precede qualification; no official outputs are produced here.
                self.save('reference_full_residual',packet)
                record.update(status=packet['status'],relative_residual=packet['relative_residual'],
                              residual_limit=1e-10,identity_checks=checks)
            finally:ax.destroy()
            self.marker('fine_reference_residual_completed',dict(status=record['status'],relative=record['relative_residual']))
            self.sample()
            record['canonical']=self.canonical_export(field,floquet)
            record['canonical_qualified']=record['status']=='REFERENCE_PASS'
            if record['status']=='REFERENCE_PASS' and self.output_callback is not None:
                record['matched_output'] = self.output_callback(native,x)
            self.save('reference_result',record)
        except Exception as exc:
            error=exc
            record.update(status='REFERENCE_CAPACITY_NOT_ADMITTED' if isinstance(exc,FineReferenceCapacityRejected)
                          else 'REFERENCE_FAILED',primary_error=dict(type=type(exc).__name__,message=str(exc)))
        finally:
            for obj in (x_aug_initial,x_aug,x,b,bridge):
                if obj is not None:
                    try:obj.destroy()
                    except Exception as exc:record['cleanup_errors'].append(dict(type=type(exc).__name__,message=str(exc)))
            try:destroy_same_mesh_physical_action(native)
            except Exception as exc:record['cleanup_errors'].append(dict(type=type(exc).__name__,message=str(exc)))
            if record['cleanup_errors']:record['status']='REFERENCE_CLEANUP_FAILED'
        raise FineReferenceExit(record,error) from error
