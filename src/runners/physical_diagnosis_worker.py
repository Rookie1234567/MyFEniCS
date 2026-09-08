"""Fixed no-reference diagnostic sequence, with one packet per completed probe."""
import hashlib
import json
import os
from pathlib import Path
import signal
import sys

import numpy as np

from .physical_intermediate import WorkflowLedger,_atomic_json
from .workflow_timebase import TimebaseInconsistency


def save_packet(directory,name,facts):
    """Keep numerical arrays ignored; scalar records reference a hashed NPZ."""
    arrays={}
    def compact(value):
        if isinstance(value,np.ndarray):
            key='array_'+str(len(arrays));arrays[key]=value
            return dict(array_key=key,shape=list(value.shape),dtype=str(value.dtype))
        if isinstance(value,dict):return {k:compact(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [compact(v) for v in value]
        return value
    record=compact(facts)
    if arrays:
        path=directory/(name+'.npz')
        temporary=path.with_suffix('.npz.tmp')
        with temporary.open('wb') as stream:
            np.savez(stream,**arrays)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        record['arrays']=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    _atomic_json(directory/(name+'.json'),record)


def run_diagnosis(input_path,inventory_path,directory,source_sha,*,completion_v4=False):
    from mpi4py import MPI
    from petsc4py import PETSc
    import petsc4py,slepc4py,dolfinx,mpi4py,basix
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from benchmarks.run_task038_full3d_t5 import _mesh_identity
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_physical_intermediate_runtime import (
        build_physical_intermediate_solver,destroy_physical_intermediate_solver,qualify_physical_intermediate_setup)
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import build_physical_rhs
    from src.solvers.physical_error_diagnostics import (component_diagnostics,coarse_diagnostics,
        evaluate_profiles,evaluate_residual_profiles,homogeneity_check)
    from src.solvers.physical_error_metric import interpolate_known_error
    from .physical_diagnosis import DiagnosticActions
    if (MPI.COMM_WORLD.size!=1 or PETSc.ScalarType is not np.complex128 or
        PETSc.IntType is not np.int32 or os.environ.get('_MYFENICS_WSL_QUALIFIED_ACTIVATION')!='1' or
        os.environ.get('PHYSICAL_TIMEBASE_GUARD')!='1' or not os.path.samefile(sys.executable,'.venv/bin/python')):
        raise RuntimeError('diagnostic MPI1/qualified complex ABI/clock guard failed')
    threads={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}
    if set(threads.values())!={'1'}:
        raise RuntimeError('diagnostic threads must all be one')
    if 'Open MPI' not in MPI.Get_library_version():
        raise RuntimeError('diagnostic requires the qualified MPI stack')
    payload=load_and_resolve(input_path).as_jsonable()
    cfg=simulation_config_3d_from_normalized(payload)
    inventory=json.loads(inventory_path.read_text())
    reused=None
    if completion_v4:
        from .physical_diagnostic_completion import reuse_v3
        reused=reuse_v3(inventory)
    selected=[s for s in inventory['samples'] if s['label'] in ('A2R160','LIGHT448','JOINT448')]
    if [s['label'] for s in selected]!=['A2R160','LIGHT448','JOINT448']:
        raise ValueError('frozen primary sample order changed')
    parent=int(os.environ['PHYSICAL_WATCHDOG_PARENT_PID'])
    cap=int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])
    ledger=WorkflowLedger(directory,Path(os.environ['PHYSICAL_WATCHDOG_PHASE_PATH']))
    handlers={sig:signal.signal(sig,lambda value,_frame:setattr(ledger,'stop_signal',value))
              for sig in (signal.SIGTERM,signal.SIGINT)}
    def sample():
        if ledger.stop_signal is not None:raise InterruptedError('diagnostic stop requested')
        record=process_tree_snapshot(parent,ledger.phase,None);envelope=memory_envelope()
        record['launch_cap_bytes']=min(cap,record['rss_bytes']+envelope['effective_available_bytes']-envelope['reserve_bytes'])
        if (not record['all_status_readable'] or record['rss_bytes']>=record['launch_cap_bytes'] or
                record['swap_bytes']!=0):raise RuntimeError('diagnostic resource gate failed')
        return record
    bundle,actions,rhs={},None,None
    summary=dict(status='STARTED',source_sha=source_sha,reference='REFERENCE_UNAVAILABLE_ON_16GB',
                 complete_pc_calls=0,independent_smoother_calls=0,official_result=None,
                 abi=dict(python=sys.executable,scalar='complex128',integer='int32',threads=threads,
                 modules={m.__name__:dict(path=m.__file__,version=getattr(m,'__version__',None))
                          for m in (petsc4py,slepc4py,dolfinx,mpi4py,basix)}))
    _atomic_json(directory/'input_resolved.json',payload)
    (directory/'input_original.dat').write_bytes(input_path.read_bytes())
    save_packet(directory,'environment',summary)
    try:
        bundle=build_physical_intermediate_solver(cfg,MPI.COMM_WORLD,resource_sample=sample,
                    marker=ledger.marker,reference=True,defer_reference=completion_v4)
        qualification=qualify_physical_intermediate_setup(bundle,marker=ledger.marker,resource_sample=sample)
        mesh_identity=_mesh_identity(bundle['levels']['mesh'])
        save_packet(directory,'setup_identity',dict(qualification=qualification,mesh=mesh_identity,
            quadrature=bundle['actions']['volume_quadrature_metadata'],
            factor=None if completion_v4 else bundle['reference_factor'].audit))
        for key in ('canonical_connectivity_sha256','canonical_geometry_sha256','cells_global'):
            if mesh_identity[key]!=inventory['mesh_witness']['identity'][key]:
                raise RuntimeError('rebuilt mesh differs from frozen same-model witness: '+key)
        actions=DiagnosticActions(bundle,cfg,ledger.marker,timebase_policy=ledger.timebase_policy)
        ledger.set_phase('profile')
        rhs,rhs_facts=build_physical_rhs(bundle['fine'])
        b=np.array(rhs.array[actions.A.indices],copy=True)
        save_packet(directory,'rhs',dict(b=b,role='dual',facts=rhs_facts))
        fine=bundle['fine'];space=bundle['levels']['spaces'][6];floquet=bundle['levels']['floquets'][6]
        mesh=space.mesh;mesh.topology.create_entity_permutations()
        for degree,metric in actions.metrics.items():
            level_space,mpc=metric.space,metric.floquet.mpc
            coefficients,offsets=mpc.coefficients()
            name='native_constraint_map_p'+str(degree)
            save_packet(directory,name,dict(dofmap=np.array(level_space.dofmap.list),
                geometry=np.array(mesh.geometry.x),geometry_dofmap=np.array(mesh.geometry.dofmap),
                permutations=np.array(mesh.topology.get_cell_permutation_info()),
                slaves=np.array(mpc.slaves),masters=np.array(mpc.masters.array),
                coefficients=np.array(coefficients),offsets=np.array(offsets),independent_indices=metric.mass.indices,
                provenance='reconstructed same-mesh/ABI native map; cross-checked by operator hash and stored residual'))
            metric.audit.update(source_sha=source_sha,k0=cfg.k0,mesh=mesh_identity,
                native_map_sha256=hashlib.sha256((directory/(name+'.npz')).read_bytes()).hexdigest())
            metric.audit['identity_sha256']=hashlib.sha256(json.dumps(metric.audit,sort_keys=True).encode()).hexdigest()
        modes=list(fine['mode_rows'])
        from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest
        _,mode_bytes,mode_sha=build_ordered_mode_manifest(fine['modes'],cfg)
        if mode_sha!=fine['mode_sha256']:raise RuntimeError('rebuilt mode manifest mismatch')
        (directory/'mode_manifest.json').write_bytes(mode_bytes)
        unique={}
        for row in modes:
            key=(row['side'],row['m'],row['n'])
            unique.setdefault(key,row)
        incident=next(r for r in modes if r['side']=='top' and r['m']==0 and r['n']==0 and r['polarization']=='s')
        near=sorted((r for r in unique.values() if (r['side'],r['m'],r['n'])!=('top',0,0)),
                    key=lambda r:abs(complex(r['beta'])))[:3]
        save_packet(directory,'modes',dict(mode_sha256=fine['mode_sha256'],mode_manifest_path=str(directory/'mode_manifest.json'),inventory=modes,
            selected=[incident]+near,selection='incident plus three closest abs(outgoing kz) distinct side/order branches'))
        if completion_v4:
            from .physical_diagnostic_completion import run_completion_controls
            run_completion_controls(bundle,cfg,actions,b,inventory,directory,source_sha,ledger,sample,summary,reused)
            return summary
        snapshots=[]
        for source in selected:
            ledger.marker(source['label']+'_identity_started',{})
            path=Path(source['path']);manifest=json.loads((path/'manifest.json').read_text())
            raw_path=path/'solution_rank0.npy';raw=np.load(raw_path,allow_pickle=False)
            operator=hashlib.sha256(json.dumps(dict(source_sha=manifest['source_sha'],physical=manifest['physical_model_sha256'],
                modes=fine['mode_sha256'],quadrature=bundle['actions']['volume_quadrature_metadata']),sort_keys=True).encode()).hexdigest()
            if (hashlib.sha256((path/'manifest.json').read_bytes()).hexdigest()!=source['manifest_sha256'] or
                hashlib.sha256(raw_path.read_bytes()).hexdigest()!=source['solution_sha256'] or
                manifest['physical_model_sha256']!=payload['provenance']['physical_model_sha256'] or
                operator!=manifest['operator_identity_sha256'] or raw.shape!=(actions.A.source.getLocalSize(),) or
                not np.isfinite(raw).all() or np.any(raw[floquet.mpc.slaves]!=0)):
                raise RuntimeError(source['label']+' source/operator/constraint identity mismatch')
            x=raw[actions.A.indices].copy();ax=actions.A(x);r=b-ax
            residual=float(np.linalg.norm(r)/np.linalg.norm(b))
            component=component_diagnostics(actions.components,x)
            identity=float(np.linalg.norm(component['sum_vector']-ax)/max(np.linalg.norm(ax),np.finfo(float).tiny))
            facts=dict(label=source['label'],x=x,r=r,ax=ax,component=component,recomputed_true_residual=residual,
                stored_true_residual=manifest['explicit_true_residual'],component_identity_relative=identity,
                operator_sha256=operator,remaining_field_error='UNAVAILABLE_NO_REFERENCE',
                action_bridge_checks=dict(A=actions.A.audit,components={k:v.audit for k,v in actions.components.items()}),
                metric_identity={k:v.audit for k,v in actions.metrics.items()})
            save_packet(directory,source['label']+'_identity',facts)
            if abs(residual-manifest['explicit_true_residual'])>1e-10*max(residual,manifest['explicit_true_residual']) or identity>1e-11:
                raise RuntimeError(source['label']+' residual/component action mismatch')
            snapshots.append((source['label'],x,r))
        for label,x,r in snapshots:
            for name,pc in actions.profiles.items():
                ledger.marker(label+'_'+name+'_probe_started',{})
                facts=evaluate_residual_profiles(actions.A,actions.M0,r,{name:pc},checkpoint=sample)
                summary['complete_pc_calls']+=1
                save_packet(directory,label+'_'+name,dict(**facts,cost=actions.timings[-1],
                    bridge_checks=[v.audit for v in actions.bridges],**summary))
            save_packet(directory,label+'_field_cells',dict(role='unconverged primal field, not true error',
                        **actions.metrics[6].cell_energies(x,checkpoint=sample)))
        e=interpolate_known_error(space,floquet,cfg,actions.A.indices)
        q=actions.A(e);scale=np.linalg.norm(q);e=e/scale;q=q/scale
        save_packet(directory,'known_error',dict(e=e,q=q,normalization_scale=float(scale),recipe=inventory['known_error']))
        # Qualify native p4 mass as the diagonal source for P^H M0 P on one legal vector.
        c=actions.PH(e);pc=actions.P(c);left=actions.PH(actions.M0(pc));right=actions.metrics[4].mass(c)
        relative=float(np.linalg.norm(left-right)/max(np.linalg.norm(right),np.finfo(float).tiny))
        save_packet(directory,'mass_galerkin',dict(relative=relative,limit=1e-10))
        if relative>1e-10:raise RuntimeError('native p4 mass differs from P^H M0 P')
        projection=actions.project(e)
        save_packet(directory,'known_projection',dict(**projection,projection_seconds=actions.projection_seconds))
        if projection['parallel'] is not None:
            save_packet(directory,'known_coarse',coarse_diagnostics(actions.A,actions.M0,actions.P,actions.PH,
                        actions.solve,e,projection))
        corrections={}
        for name,pc in actions.profiles.items():
            facts=evaluate_profiles(actions.A,actions.M0,e,{name:pc},checkpoint=sample)
            corrections[name]=facts['profiles'][name]['correction']
            known_q=facts['normalized_q']
            summary['complete_pc_calls']+=1
            save_packet(directory,'known_'+name,dict(**facts,cost=actions.timings[-1],completed_pc_calls=summary['complete_pc_calls']))
        for name,pc in actions.profiles.items():
            facts=homogeneity_check(known_q,{name:corrections[name]},{name:pc},checkpoint=sample)
            summary['complete_pc_calls']+=1
            save_packet(directory,'known_homogeneity_'+name,dict(relative_errors=facts,cost=actions.timings[-1],completed_pc_calls=summary['complete_pc_calls']))
        if projection['status']=='PROJECTION_CLOSED' and np.linalg.norm(projection['perpendicular'])>0:
            perp=projection['perpendicular']
            for name,smoother in actions.smoothers.items():
                facts=evaluate_profiles(actions.A,actions.M0,perp,{name:smoother},checkpoint=sample)
                summary['independent_smoother_calls']+=1
                save_packet(directory,'complement_'+name,dict(**facts,cost=actions.timings[-1],completed_smoother_calls=summary['independent_smoother_calls']))
                repeated=homogeneity_check(facts['normalized_q'],{name:facts['profiles'][name]['correction']},{name:smoother},checkpoint=sample)
                summary['independent_smoother_calls']+=1
                save_packet(directory,'complement_homogeneity_'+name,dict(relative_errors=repeated,cost=actions.timings[-1],completed_smoother_calls=summary['independent_smoother_calls']))
        save_packet(directory,'known_field_cells',actions.metrics[6].cell_energies(e,checkpoint=sample))
        summary.update(status='DIAGNOSTICS_COMPLETED',projection_seconds=actions.projection_seconds,
                       restart_causality='UNRESOLVED_no_new_Hessenberg_or_restart_run',timings=actions.timings)
    except BaseException as exc:
        summary.update(status='TIMEBASE_INCONSISTENCY' if isinstance(exc,TimebaseInconsistency) else 'DIAGNOSTICS_FAILED',
                       exception_type=type(exc).__name__,exception=str(exc),last_stage=ledger.last_stage)
        raise
    finally:
        if actions is not None:
            summary['bridge_checks']=[v.audit for v in actions.bridges]
            summary['metric_identity']={k:dict(**v.audit,bridge_checks={n:b.audit for n,b in v.bridges.items()})
                                        for k,v in actions.metrics.items()}
        from .physical_diagnostic_completion import finalize_diagnostics
        finalizers=[]
        if actions is not None:finalizers.append(actions.destroy)
        if rhs is not None:finalizers.append(rhs.destroy)
        finalizers.append(lambda:destroy_physical_intermediate_solver(bundle))
        try:
            finalize_diagnostics(summary,finalizers,
                lambda:_atomic_json(directory/'diagnostic_summary.json',summary),sys.exc_info()[1])
        finally:
            for sig,handler in handlers.items():signal.signal(sig,handler)
