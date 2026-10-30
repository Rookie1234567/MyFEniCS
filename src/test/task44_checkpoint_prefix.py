"""Owner-only tiny actual FFCx raw-cache + sparse binary schema control, not PDE."""
from pathlib import Path
import json
import time


def run(directory):
    import numpy as np
    import ufl
    from basix.ufl import element
    from dolfinx import mesh,fem
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.io.sixlayer_input import resolve_sixlayer_input,build_sixlayer_config
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.hcurl_assembly_time_condensation import _canonical_axis_aligned_coordinates,_cell_integral_kernels,_tabulate_raw_tensor_class
    from src.solvers.volume_tensor_checkpoint import VolumeTensorCheckpoint
    from src.solvers.pre_factor_checkpoint import save_pre_factor_checkpoint,FAILED_CHECKPOINT_ROOTS
    from src.common.runtime_resource_policy import resource_policy,admit
    from src.common.strict_json import atomic_json
    from benchmarks.supervision_task44.stage_admission_v1 import admit as actual_admit
    root=Path(__file__).resolve().parents[2];d=Path(directory);d.mkdir(exist_ok=False,parents=True)
    started=time.monotonic();facts={'status':'RUNNING','scope':'p1 one-cell software/schema prefix; not six-layer PDE or p6 tensor qualification'};objects=[];primary=None
    try:
        _,resolved=resolve_sixlayer_input(root/'input/task44_sixlayer/A.dat');cfg=build_sixlayer_config(resolved)
        msh=mesh.create_unit_cube(MPI.COMM_SELF,1,1,1,cell_type=mesh.CellType.hexahedron)
        V=fem.functionspace(msh,element('N1curl','hexahedron',1))
        tags=mesh.meshtags(msh,3,np.array([0],dtype=np.int32),np.array([cfg.tags.air],dtype=np.int32))
        u,v=ufl.TrialFunction(V),ufl.TestFunction(V)
        terms=_build_physical_volume_terms(cfg,u,v,ufl.Measure('dx',domain=msh,subdomain_data=tags))
        compiled=fem.form(terms[0]+terms[1]);kernels=_cell_integral_kernels(compiled,sum_duplicate_cell_integrals=True)
        coords,_=_canonical_axis_aligned_coordinates(msh,0,tolerance=1e-11,preserve_exact_geometry=True)
        calls=[]
        def compute():
            calls.append(1)
            return _tabulate_raw_tensor_class(compiled,kernels,coords,tag=cfg.tags.air,dimension=V.element.space_dimension)
        with resource_policy(actual_admit):
            policy=VolumeTensorCheckpoint(cfg,d/'raw_cache',d/'raw_progress.jsonl')
            a,ra=policy(compiled,kernels,coords,cfg.tags.air,V.element.space_dimension,compute)
            b,rb=policy(compiled,kernels,coords,cfg.tags.air,V.element.space_dimension,compute)
            policy.verify()
            direct=_tabulate_raw_tensor_class(compiled,kernels,coords,tag=cfg.tags.air,dimension=V.element.space_dimension)
            facts['raw']={'cold_hit':ra['cache_hit'],'warm_hit':rb['cache_hit'],'callback_calls':len(calls),
                          'cold_warm_exact':bool(np.array_equal(a,b)),'independent_same_kernel_exact':bool(np.array_equal(a,direct)),
                          'shape':list(a.shape),'receipts':[ra,rb]}
            if ra['cache_hit'] or not rb['cache_hit'] or len(calls)!=1 or not np.array_equal(a,b) or not np.array_equal(a,direct):
                raise RuntimeError('actual raw-cache cold/warm/native identity control')
            A=PETSc.Mat().createAIJ([2,2],nnz=2,comm=PETSc.COMM_SELF);objects.append(A)
            A.setValues([0,1],[0,1],np.array([[4+1j,1-.2j],[-.3+.5j,3-.4j]],dtype=PETSc.ScalarType));A.assemble()
            rhs=A.createVecRight();objects.append(rhs);rhs.setValues([0,1],[1+2j,3-.1j]);rhs.assemble()
            facts['binary']=save_pre_factor_checkpoint(A,rhs,d/'binary',admit=admit)
        facts['status']='EXACT_RAW_CACHE_AND_BINARY_PREFIX_PASS_NOT_PDE'
    except BaseException as exc:primary=exc;facts.update(status='FAILED',error=repr(exc));raise
    finally:
        errors=[]
        if FAILED_CHECKPOINT_ROOTS:errors.append('retained binary viewer dependency graph')
        else:
            for obj in reversed(objects):
                try:obj.destroy()
                except BaseException as exc:errors.append(repr(exc));FAILED_CHECKPOINT_ROOTS.append(tuple(objects));break
        facts.update(elapsed_seconds=time.monotonic()-started,cleanup_errors=errors,cleanup_complete=not errors)
        if errors:facts['status']='FAILED_CLEANUP'
        try:atomic_json(d/'result.json',facts)
        except BaseException as exc:
            if primary is not None:primary.add_note('prefix result publication: '+repr(exc))
            else:raise
        if errors and primary is None:raise RuntimeError('prefix cleanup failed')
    return facts

if __name__=='__main__':
    import sys
    print(json.dumps(run(sys.argv[1]),allow_nan=False))
