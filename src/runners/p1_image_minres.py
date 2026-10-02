"""Thin V23 adapter over the qualified bounded action stage and supervisor."""
import sys,subprocess,traceback
from pathlib import Path
from src.io import p1_image_minres as io
from src.solvers import p1_image_window as window
from src.runners.p1_trace_galerkin import P1Stage

class ImageStage(P1Stage):
    def __init__(self,specification,directory):
        super().__init__(specification,directory,io_module=io,window_module=window,action_limit=32000,
            limits=dict(original_audits=120,field_states=10),family=io.FAMILY,
            pc_key='B_M',triangular_key='R_triangular',triangular_per_PC=1)
        self.meta.update(global_tall_image_QR_present=False,global_factor_constructed=False,
            bounded_Ac_LU_only_in_G_comparison=self.name=='COMPARE',raw_hidden_weights_loaded=False)
        from src.runners.actual_loss_block_descent import _pure_blas_threads
        self.meta['actual_BLAS_pools']=_pure_blas_threads()

def main():
    window.guard_worker_parent();stage=ImageStage(io.load_image_minres(sys.argv[1]),Path(sys.argv[2]).resolve());result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V23 active source changed')
        from src.solvers.p1_image_study import setup,compare,route,load_state
        if stage.name=='SETUP':result=setup(stage)
        elif stage.name=='COMPARE':result=compare(stage)
        elif stage.name=='VERIFY':
            from src.solvers.gmres_residual_completion import verify
            result=verify(stage,state_loader=load_state)
        else:result=route(stage)
    except Exception as error:
        result.update(getattr(stage,'partial_result',{}));result.update(status='FAILED',error=type(error).__name__+': '+str(error));traceback.print_exc();raise
    finally:stage.finish(result)

if __name__=='__main__':main()
