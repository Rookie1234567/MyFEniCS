"""V19 thin adapter over the qualified stage/accounting/physical audit."""
import subprocess
import sys
import traceback
from pathlib import Path
from src.io import post_lsqr_polish as io
from src.solvers import post_lsqr_window as window
from src.runners.gmres_residual_completion import CompletionStage


def execute_stage(stage):
    from src.solvers.post_lsqr_polish import load_state, route
    from src.solvers.gmres_residual_completion import preflight, verify
    if stage.own_plan['resident_upper_bytes']>8*2**30:raise MemoryError('V19 planned resident capacity')
    if stage.algorithm_name=='C0':return preflight(stage,state_loader=load_state)
    if stage.algorithm_name=='V':return verify(stage,state_loader=load_state)
    return route(stage)


def main():
    window.guard_worker_parent()
    spec=io.load_post_lsqr(sys.argv[1]);directory=Path(sys.argv[2]).resolve()
    stage=CompletionStage(spec,directory,io_module=io,window_module=window,batch='V19');result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:
            raise RuntimeError('V19 runtime source changed after clean launch')
        result=execute_stage(stage)
        if spec.derived['environment_mode']=='pure':
            from src.runners.actual_loss_block_descent import _pure_blas_threads
            result['threads']=_pure_blas_threads()
    except Exception as error:
        result.update(status='FAILED',error=type(error).__name__+': '+str(error),queue_frozen=True)
        traceback.print_exc();raise
    finally:stage.finish(result)


if __name__=='__main__':main()
