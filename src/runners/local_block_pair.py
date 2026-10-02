"""Small local/coarse adapter over existing Task042 stage and supervision."""
import sys,subprocess,traceback
from pathlib import Path
from src.io import local_block_pair as io
from src.solvers import local_block_window as window
from src.runners.p1_trace_galerkin import P1Stage
from src.runners.task042_shared import write_json


class LocalStage(P1Stage):
    def __init__(self,specification,directory):
        super().__init__(specification,directory,io_module=io,window_module=window,action_limit=45000,
            limits=dict(original_audits=160,field_states=12),family=io.FAMILY,
            pc_key='L8',triangular_key='R_triangular',triangular_per_PC=1)
        from src.runners.actual_loss_block_descent import _pure_blas_threads
        self.meta.update(actual_BLAS_pools=_pure_blas_threads(),local_factors_read_only=False,
            local_factors_present=False,global_tall_image_QR_present=False,neural_weights_loaded=False)

    def durable(self):
        super().durable()
        row=self.window.ledger();upper=row['active']['upper']
        upper['local_lu_solve']+=8*self.pc_reserve
        upper['local_triangular_pass']+=16*self.pc_reserve
        write_json(self.window.LEDGER_PATH,row)

    def reserve_cycle(self,*,pc):
        for key,n in [('local_lu_solve',2400),('local_triangular_pass',4800)]:
            if self.base['charged'][key]+self.aux[key]+n>self.window.CAPS[key]:raise RuntimeError('reserved local solve cap')
        return super().reserve_cycle(pc=pc)


def main():
    window.guard_worker_parent();stage=LocalStage(io.load_local_block(sys.argv[1]),Path(sys.argv[2]).resolve());result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V24 active source changed')
        from src.solvers.local_block_study import setup,route,load_state
        if stage.name=='SETUP':result=setup(stage)
        elif stage.name=='VERIFY':
            from src.solvers.gmres_residual_completion import verify
            result=verify(stage,state_loader=load_state)
        else:result=route(stage)
        if 'block_inventory' in result:
            path=stage.io.ARTIFACT_ROOT/'block_inventory.json';write_json(path,result['block_inventory'])
            from src.solvers.neural_fe_action_packet import file_hash
            result['block_inventory_sha256']=file_hash(path)
    except Exception as error:
        result.update(getattr(stage,'partial_result',{}));result.update(status='FAILED',error=type(error).__name__+': '+str(error));traceback.print_exc();raise
    finally:stage.finish(result)

if __name__=='__main__':main()
