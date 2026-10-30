"""Independent uncondensed FE+auxiliary residual, streaming original port forms.

No candidate Schur matrix, local inverse, projected interior residual, or KSP
estimate participates. The FE action is freshly compiled UFL action on the
recovered physical field; the test space uses the original Floquet MPC.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import time

FAILED_RESIDUAL_ROOTS=[]


def original_augmented_residual(a,L,E_total,mesh_data,cfg,floquet_data,modes,
                               surface_assemblers,aux_values,incident_projections,out_dir):
    import numpy as np
    import ufl
    from .dtn_port_3d import (_assemble_mpc_vector,_incident_top_traction_form,
                             _mode_projection_denominator,_traction_vector,
                             _dtn_surface_quadrature_degree)
    if mesh_data.mesh.comm.size!=1:
        raise ValueError("streamed original augmented residual currently requires MPI1")
    n=E_total.function_space.dofmap.index_map.size_local
    if E_total.function_space.dofmap.index_map_bs!=1:
        raise ValueError("scalar-indexed Nedelec coefficients required")
    if len(aux_values)!=len(modes) or len(incident_projections)!=len(modes):
        raise ValueError("complete ordered auxiliary vectors required")
    objects=[];primary=None;started=time.monotonic();result=None
    try:
        # UFL action evaluates all cell coefficients at the recovered physical
        # field, then MPC assembly independently merges every full test row.
        action=_assemble_mpc_vector(ufl.action(a,E_total),floquet_data.mpc);objects.append(action)
        rhs=_assemble_mpc_vector(L,floquet_data.mpc);objects.append(rhs)
        incident=_assemble_mpc_vector(_incident_top_traction_form(E_total.function_space,mesh_data,cfg),
                                      floquet_data.mpc,quadrature_degree=_dtn_surface_quadrature_degree(cfg,modes))
        objects.append(incident);rhs.axpy(1.0,incident)
        x=np.asarray(E_total.x.array[:n],dtype=np.complex128).copy()
        slaves=np.asarray(floquet_data.mpc.slaves,dtype=np.int64)
        owned_slaves=slaves[slaves<n];x[owned_slaves]=0.0
        av=action.getArray();bv=rhs.getArray()
        aux_residual=np.empty(len(modes),dtype=np.complex128)
        column_records=[]
        for index,mode in enumerate(modes):
            components=[];component_primary=None
            try:
                for component in (0,1):
                    vector=surface_assemblers[(mode.side,component)].assemble_raw_mpc_vector(mode,floquet_data.mpc)
                    components.append(vector)
                v0,v1=(v.getArray(readonly=True) for v in components)
                traction=_traction_vector(mode,cfg)
                # Original augmented upper-right C = -traction functional.
                c=-(traction[0]*v0+traction[1]*v1)
                ell=mode.e_vector[0]*v0+mode.e_vector[1]*v1
                denominator=_mode_projection_denominator(mode,cfg)
                if not np.isfinite(denominator) or denominator<=0:raise RuntimeError("invalid modal normalization")
                d=-np.conj(ell)/denominator
                if not np.isfinite(c).all() or not np.isfinite(d).all():raise RuntimeError("nonfinite original C/D")
                av[:n]+=c[:n]*aux_values[index]
                bv[:n]+=c[:n]*incident_projections[index]
                aux_residual[index]=np.dot(d[:n],x)+aux_values[index]
                column_records.append({"index":index,"side":mode.side,"m":int(mode.m),"n":int(mode.n),
                    "polarization":mode.polarization,"normalization":float(denominator),
                    "C_sha256":sha256(np.ascontiguousarray(c[:n],dtype="<c16").view(np.uint8)).hexdigest(),
                    "D_sha256":sha256(np.ascontiguousarray(d[:n],dtype="<c16").view(np.uint8)).hexdigest()})
            except BaseException as exc:component_primary=exc;raise
            finally:
                for vector in reversed(components):
                    try:vector.destroy()
                    except BaseException as cleanup:
                        FAILED_RESIDUAL_ROOTS.append((components,objects,E_total,floquet_data))
                        if component_primary is not None:component_primary.add_note("surface vector cleanup: "+repr(cleanup))
                        else:raise
                        break
        residual=np.asarray(av[:n]-bv[:n],dtype=np.complex128)
        full_rhs=np.asarray(bv[:n],dtype=np.complex128).copy()
        for array in (x,residual,full_rhs,aux_residual,aux_values):
            if not np.isfinite(array).all():raise RuntimeError("nonfinite full original operator vector")
        # Embedded slave identity equations are x_slave=0, b_slave=0. All
        # physical equations have already been merged by MPC test assembly.
        slave_action=float(np.max(np.abs(residual[owned_slaves]),initial=0.0))
        if slave_action!=0:raise RuntimeError("MPC action unexpectedly retained slave test equations")
        rhs_norm=float(np.linalg.norm(full_rhs))
        residual_norm=float(np.hypot(np.linalg.norm(residual),np.linalg.norm(aux_residual)))
        if not np.isfinite(rhs_norm) or rhs_norm<=0:raise RuntimeError("nonzero finite full RHS required")
        rr=residual_norm/rhs_norm
        result={"schema":"original-full-augmented-residual.v1","relative_residual":rr,
                "rhs_norm":rhs_norm,"residual_norm":residual_norm,"full_FE_rows":int(n),
                "auxiliary_rows":len(modes),"complete_augmented_rows":int(n+len(modes)),
                "FE_residual_norm":float(np.linalg.norm(residual)),
                "auxiliary_residual_norm":float(np.linalg.norm(aux_residual)),
                "MPC_slave_test_residual_max":slave_action,"passed":bool(np.isfinite(rr) and rr<=1e-6),
                "uses_condensed_operator":False,"uses_projected_interior_residual":False,
                "surface_filter":"none: original pre-cutoff UFL functionals",
                "phase_gauge":cfg.dtn_phase_gauge or "global_z",
                "elapsed_seconds":time.monotonic()-started,"columns":column_records}
        output=Path(out_dir)/"original_full_augmented_vectors.npz"
        arrays={"rhs":full_rhs,"residual":residual,"auxiliary_residual":aux_residual,
                "independent_FE_coefficients":x,"auxiliary_coefficients":np.asarray(aux_values,dtype=np.complex128)}
        with output.open("xb") as f:
            np.savez(f,**arrays)
            f.flush();os.fsync(f.fileno())
        # Read one member at a time, not a second complete in-memory archive.
        members={}
        with np.load(output,allow_pickle=False) as saved:
            if set(saved.files)!=set(arrays):raise RuntimeError("full residual archive members")
            for name,expected in arrays.items():
                observed=saved[name]
                if (observed.dtype!=np.dtype("complex128") or observed.shape!=expected.shape
                        or not np.isfinite(observed).all() or not np.array_equal(observed,expected)):
                    raise RuntimeError("full residual saved member readback: "+name)
                members[name]={"shape":list(observed.shape),"dtype":str(observed.dtype),
                    "payload_sha256":sha256(np.ascontiguousarray(observed,dtype="<c16").view(np.uint8)).hexdigest()}
                del observed
        result["saved_members"]=members
        result["saved_readback_bitwise_equal"]=True
        result["vectors_file"]=output.name
        digest=sha256()
        with output.open("rb") as stream:
            for block in iter(lambda:stream.read(2**20),b""):digest.update(block)
        result["vectors_sha256"]=digest.hexdigest()
        (Path(out_dir)/"original_full_augmented_residual.json").write_text(json.dumps(result,indent=2,allow_nan=False))
        return result
    except BaseException as exc:primary=exc;raise
    finally:
        if FAILED_RESIDUAL_ROOTS:
            FAILED_RESIDUAL_ROOTS.append((objects,E_total,floquet_data))
        else:
            for obj in reversed(objects):
                try:obj.destroy()
                except BaseException as cleanup:
                    FAILED_RESIDUAL_ROOTS.append((objects,E_total,floquet_data))
                    if primary is not None:primary.add_note("residual cleanup: "+repr(cleanup))
                    else:raise
                    break
