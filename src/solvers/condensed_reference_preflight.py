"""Symbolic-only observer of the existing condensed direct assembly.

Never returns a no-global-factor solver snapshot and never calls numeric.
The owning DtN flow catches the typed exit only to release its live objects.
"""
import hashlib
from collections import Counter
from collections.abc import Mapping
from dataclasses import fields, is_dataclass

import numpy as np


class CondensedPreflightExit(Exception):
    def __init__(self, record, error=None):
        self.record, self.error = record, error
        super().__init__(record['status'])

    def release(self, objects):
        """The owner supplies objects; preserve the primary failure separately."""
        seen=set()
        for value in objects:
            if value is None or id(value) in seen:continue
            seen.add(id(value))
            try:value.destroy()
            except Exception as exc:
                self.record.setdefault('cleanup_errors',[]).append(
                    dict(type=type(exc).__name__,message=str(exc)))
        if self.record.get('cleanup_errors'):
            self.record['status']='PREFLIGHT_CLEANUP_FAILED'


def retained_payload(system):
    """Count distinct ndarray backing allocations, including aliased identity maps."""
    owners={}; entries=[]
    def visit(value, path):
        if isinstance(value,np.ndarray):
            owner=value
            while isinstance(owner.base,np.ndarray):owner=owner.base
            key=id(owner)
            if key not in owners:
                owners[key]=len(entries)
                entries.append(dict(first_reference=path,bytes=int(owner.nbytes),
                    shape=list(owner.shape),dtype=str(owner.dtype),references=1))
            else:entries[owners[key]]['references']+=1
        elif isinstance(value,Mapping):
            for key,item in value.items():visit(item,path+'/'+repr(key))
        elif isinstance(value,(tuple,list)):
            for index,item in enumerate(value):visit(item,path+'/'+str(index))
        elif is_dataclass(value):
            for field in fields(value):visit(getattr(value,field.name),path+'/'+field.name)
    names=('interior_from_trace_by_class','interior_lu_by_class',
        'interior_rhs_projection_by_class','interior_solution_embedding_by_class',
        'trace_from_interior_rhs_by_class','interior_residual_projection_by_class',
        'cell_recovery_maps','trace_constraints','owned_trace_original_dofs',
        'retained_local_schur_by_class')
    for name in names:visit(getattr(system,name),name)
    counts=Counter(repr(cell.class_key) for cell in system.cell_recovery_maps)
    keys=sorted(counts)
    return dict(unique_ndarray_bytes=sum(e['bytes'] for e in entries),allocations=entries,
        exact_oriented_class_count=len(system.interior_lu_by_class),
        cell_count=len(system.cell_recovery_maps),cells_per_class={k:counts[k] for k in keys},
        class_keys_sha256=hashlib.sha256('\n'.join(keys).encode()).hexdigest(),
        scope='live ndarray backing payload only; identity aliases counted once; Python/PETSc/allocator excluded',
        build_audit=system.build_audit,
        retained_local_schur=system.retained_local_schur_by_class is not None)


def capacity_forecast(resource, raw_info, system):
    """Transparent arithmetic inventory, not a fitted predictor or admission gate."""
    estimate_mb=max(int(raw_info['infog']['16']),int(raw_info['infog']['17']))
    if estimate_mb<=0:raise ValueError('MUMPS symbolic memory estimate unavailable')
    factor_estimate=estimate_mb*1_000_000
    # Planned future reference: bounded solution/RHS/residual fields and recovery.
    payloads=dict(full_vectors=8*system.full_rows*16,
        augmented_vectors=4*(system.active_rows+system.appended_rows)*16,
        recovered_interiors=system.interior_rows*16,
        trace_gather_and_copy=2*system.active_rows*16)
    future=sum(payloads.values())
    arithmetic=int(resource['rss_bytes'])+factor_estimate+future
    return dict(classification='partial_arithmetic_inventory_not_peak_upper_bound',
        current_tree_rss_bytes=resource['rss_bytes'],
        current_includes_matrix_and_live_local_caches=True,
        symbolic_mumps_incore_memory_estimate_bytes=factor_estimate,
        symbolic_memory_units='decimal MB; INFOG16/17 include MUMPS in-core factorization data, not just factor values',
        future_vector_payloads=payloads,future_vector_payload_bytes=future,
        arithmetic_rss_plus_mumps_plus_vectors_bytes=arithmetic,
        dynamic_cap_bytes=resource['launch_cap_bytes'],
        arithmetic_headroom_bytes=resource['launch_cap_bytes']-arithmetic,
        strict_total_peak_upper_bound_bytes=None,numeric_authorized_by_forecast=False,
        unknown=['current symbolic RSS may overlap with INFOG16/17 internal data; no calibrated total peak bound',
                 'numeric fill/pivot sensitivity and ICNTL14 effect on estimate',
                 'FFCx/full original-A6 verification action workspace and allocator high-water',
                 'future payload counts require confirmation against final reference wiring'],
        decision='NUMERIC_NOT_RUN_REVIEW_REQUIRED')


class CondensedSymbolicPreflight:
    """Borrow an assembled A, save analysis, and exit before snapshot dispatch."""
    def __init__(self, *, sample, save, marker, identity, factor_factory=None):
        self.sample,self.save,self.marker,self.identity=sample,save,marker,identity
        self.factor_factory=factor_factory

    def __call__(self, request):
        record=dict(status='PREFLIGHT_STARTED',identity=self.identity,
            numeric_called=False,solve_called=False,symbolic_calls=0,cleanup_errors=[])
        factor=None;error=None
        try:
            if request.A.getComm().getSize()!=1:
                raise ValueError('fine reference capacity preflight requires MPI1')
            system=request.static_condensed_system
            record.update(rows=request.A.getSize()[0],n_fe=request.n_fe,n_aux=request.n_aux,
                matrix_info=request.A.getInfo(),retained_payload=retained_payload(system),
                before_symbolic_resource=self.sample())
            if (system.full_rows,request.n_fe,request.n_aux)!=(173802,51192,80):
                raise ValueError('frozen fine-reference dimensions differ')
            self.save('assembled_preflight',record)
            self.marker('fine_reference_symbolic_started',dict(rows=record['rows']))
            factory=self.factor_factory
            if factory is None:
                from .fullspace_v17_p3_oracle import _MumpsFactor
                factory=_MumpsFactor
            factor=factory(request.A)
            factor.symbolic(request.A)
            record['symbolic_calls']=1
            record['symbolic_info']=factor.info((22,29))
            record['mumps_memory_controls']=factor.symbolic_memory_settings()
            record['after_symbolic_resource']=self.sample()
            record['preferred_ordering']=factor.preferred_ordering
            self.save('symbolic_raw',record)
            record['forecast']=capacity_forecast(record['after_symbolic_resource'],
                record['symbolic_info'],system)
            record['status']='SYMBOLIC_PREFLIGHT_COMPLETED_NUMERIC_NOT_RUN'
            self.save('symbolic_preflight',record)
            self.marker('fine_reference_symbolic_completed',dict(status=record['status'],
                numeric_called=False,solve_called=False,forecast=record['forecast']))
        except Exception as exc:
            error=exc
            record.update(status='SYMBOLIC_PREFLIGHT_FAILED',primary_error=dict(
                type=type(exc).__name__,message=str(exc)))
        finally:
            if factor is not None:
                try:factor.destroy()
                except Exception as exc:
                    record['cleanup_errors'].append(dict(type=type(exc).__name__,message=str(exc)))
                    record['status']='PREFLIGHT_CLEANUP_FAILED'
        raise CondensedPreflightExit(record,error) from error
