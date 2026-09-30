"""Thin V16 opt-in dispatch using the existing shared Stage and supervisors."""

import sys
import traceback
from pathlib import Path

from src.io import augmented_trace_lsqr as io
from src.runners.orthonormal_trace_reprofile import Stage
from src.solvers import augmented_trace_window as window
from src.solvers.augmented_trace_lsqr import FAMILY, LIMITS


def main():
    window.guard_worker_parent()
    specification=io.load_augmented_trace(sys.argv[1]);directory=Path(sys.argv[2]).resolve()
    stage=Stage(specification,directory,io_module=io,window_module=window,
                limits=LIMITS,action_limit=50000,family=FAMILY)
    result={}
    try:
        from src.solvers.augmented_trace_study import preflight,solve_route,verify
        if stage.own_plan['resident_upper_bytes']>8*2**30:raise MemoryError('V16 resident plan exceeds 8GiB')
        if stage.name=='PREFLIGHT':result=preflight(stage)
        elif stage.name=='VERIFY':result=verify(stage)
        else:result=solve_route(stage)
        if specification.derived['environment_mode']=='pure':
            from src.runners.actual_loss_block_descent import _pure_blas_threads
            result['threads']=_pure_blas_threads()
    except Exception as error:
        result.update(status='FAILED',error=type(error).__name__+': '+str(error),queue_frozen=True)
        traceback.print_exc();raise
    finally:
        owned_bytes=sum(p.stat().st_size for p in io.ARTIFACT_ROOT.rglob('*') if p.is_file())
        result['new_batch_artifact_bytes']=owned_bytes
        result['artifact_budget_qualified']=owned_bytes<=3*2**30
        stage.finish(result)


if __name__=='__main__':main()
