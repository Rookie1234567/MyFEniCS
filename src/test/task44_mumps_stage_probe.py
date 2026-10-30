"""Owner-run bounded 2x2 public MUMPS stage/API qualification, not PDE."""
from __future__ import annotations
import json
import math
from pathlib import Path
import sys
import time


def run(directory):
    import numpy as np
    from petsc4py import PETSc
    from src.solvers.bounded_mumps import PublicMumpsFactor,load_public_shim,FAILED_OWNERS
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    objects=[];factor=None;primary=None;facts={};started=time.monotonic()
    try:
        api,identity=load_public_shim(directory)
        A=PETSc.Mat().createAIJ([2,2],nnz=2,comm=PETSc.COMM_SELF);objects.append(A)
        values=np.array([[4+1j,1-.2j],[-.3+.5j,3-.4j]],dtype=PETSc.ScalarType)
        A.setValues([0,1],[0,1],values);A.assemble()
        b=A.createVecRight();objects.append(b);b.setValues([0,1],[1+2j,3-.1j]);b.assemble()
        x=b.duplicate();objects.append(x);r=b.duplicate();objects.append(r)
        controls={14:100,24:1,35:0,22:0}
        factor=PublicMumpsFactor(A,api,controls=controls)
        info=factor.symbolic()
        facts.update(symbolic_INFOG=info,numeric_done_after_symbolic=factor.numeric_done,
                     controls=factor.controls,identity=identity)
        if factor.numeric_done or info["1"]<0 or max(info["16"],info["26"])<=0:
            raise RuntimeError("symbolic-only stage certificate failed")
        factor.numeric();factor.solve(b,x);A.mult(x,r);r.axpy(-1,b)
        rr=float(r.norm()/b.norm());ref=np.linalg.solve(values,np.asarray(b.array))
        err=float(np.linalg.norm(x.array-ref)/np.linalg.norm(ref))
        facts.update(relative_residual=rr,numpy_solution_relative_error=err)
        factor.close();factor=None
        # Independent ordinary KSP route with exactly the same controls.
        k=PETSc.KSP().create(PETSc.COMM_SELF);objects.append(k);k.setOperators(A);k.setType("preonly")
        pc=k.getPC();pc.setType("lu");pc.setFactorSolverType("mumps");pc.setFactorSetUpSolverType()
        F=pc.getFactorMatrix()
        ordinary_primary=None
        try:
            for index,value in controls.items():F.setMumpsIcntl(index,value)
            k.setUp()
            ordinary_info={str(i):int(F.getMumpsInfog(i)) for i in (16,26)}
            k.solve(b,r)
            delta=float(np.linalg.norm(r.array-x.array)/np.linalg.norm(x.array))
            facts.update(ordinary_INFOG=ordinary_info,ordinary_vs_staged_solution_relative_error=delta,
                         ordinary_controls={str(i):int(F.getMumpsIcntl(i)) for i in controls})
        except BaseException as exc:ordinary_primary=exc;raise
        finally:
            try:F.destroy()
            except BaseException as cleanup:
                FAILED_OWNERS.append((F,k,objects))
                if ordinary_primary is not None:ordinary_primary.add_note("factor reference cleanup: "+repr(cleanup))
                else:raise
        if not all(math.isfinite(v) and 0<=v<=1e-12 for v in (rr,err,delta)):
            raise RuntimeError("public staged/ordinary exact solution oracle")
        if facts["ordinary_controls"]!=facts["controls"]:raise RuntimeError("ordinary controls mismatch")
        if any(ordinary_info[str(i)]!=info[str(i)] for i in (16,26)):
            raise RuntimeError("ordinary and isolated symbolic estimates differ on tiny")
        facts.update(status="PUBLIC_MUMPS_STAGES_TINY_PASS_NOT_PDE",elapsed_seconds=time.monotonic()-started)
    except BaseException as exc:primary=exc;facts.update(status="FAILED",error=repr(exc));raise
    finally:
        cleanup=[]
        if factor is not None:
            try:factor.close()
            except BaseException as error:
                cleanup.append(repr(error))
                if primary is not None:primary.add_note(repr(error))
        if FAILED_OWNERS:
            FAILED_OWNERS.append(tuple(objects));cleanup.append("retained factor dependency graph")
        else:
            for obj in reversed(objects):
                try:obj.destroy()
                except BaseException as exc:
                    FAILED_OWNERS.append(tuple(objects));cleanup.append(repr(exc));break
        facts["cleanup_errors"]=cleanup;facts["cleanup_complete"]=not cleanup and not FAILED_OWNERS
        if cleanup:facts["status"]="FAILED_CLEANUP"
        try:(directory/"result.json").write_text(json.dumps(facts,indent=2,allow_nan=False))
        except BaseException as error:
            if primary is not None:primary.add_note("result publication: "+repr(error))
            else:raise
        if cleanup and primary is None:raise RuntimeError("native cleanup failed")
    return facts


if __name__=="__main__":
    print(json.dumps(run(sys.argv[1]),allow_nan=False))
