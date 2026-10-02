"""Single short V25 actor over the established runner and whole-tree watchdog."""
import subprocess,sys,time,traceback
from pathlib import Path
from src.io import block_direction_diagnostic as io
from src.solvers import block_direction_window as window
from src.runners.orthonormal_trace_reprofile import Stage
from src.runners.task042_shared import write_json


class DirectionStage(Stage):
    def __init__(self,specification,directory):
        self.base=window.ledger();self.run_started=time.monotonic()
        if self.base['active'] is not None:raise RuntimeError('V25 duplicate actor')
        super().__init__(specification,directory,io_module=io,window_module=window,
            limits=window.CAPS,action_limit=64,family=io.FAMILY)
        self.base['active']=dict(directory=str(directory),source_sha=self.source,
            completed=self.counts.copy(),upper=self.counts.copy())
        write_json(window.LEDGER_PATH,self.base)
        original=self.packet.apply
        def apply(x,adjoint=False):
            self.guard();self.reserve('actions')
            y=original(x,adjoint=adjoint)
            self.counts['actions']+=1;self.durable();return y
        self.packet.apply=apply
        from src.runners.actual_loss_block_descent import _pure_blas_threads
        self.meta.update(actual_BLAS_pools=_pure_blas_threads(),hidden_training=False,
            Q_U_R_D_L_loaded=False,teacher_arrays_read=False,reference_arrays_read=False,
            global_tall_image_QR_present=False,new_local_assemblies=0,new_local_factors=0,
            new_solver_states=0,field_recovery_calls=0,FE_field_validation=False)

    def guard(self,**kwargs):
        self.sample();window.require_live(margin=10)
        if self.base['actor_wall_seconds']+time.monotonic()-self.run_started>=590:
            raise RuntimeError('V25 cumulative actor cutoff/cleanup margin')
        if sum(p.stat().st_size for p in io.ARTIFACT_ROOT.rglob('*') if p.is_file())>128*2**20:
            raise MemoryError('V25 persistent artifact cap')
        now=time.monotonic()
        if now-getattr(self,'last_disk_check',0)>5:
            if sum(p.stat().st_size for p in (io.ROOT/'benchmarks/artifacts/task042').rglob('*') if p.is_file())>20*2**30:
                raise MemoryError('Task042 global artifact cap')
            self.last_disk_check=now

    def reserve(self,key,n=1):
        window.validate_increment(self.base['charged'],self.counts,key,n)
        row=window.ledger();upper=self.counts.copy();upper[key]+=n
        row['active'].update(completed=self.counts.copy(),upper=upper)
        write_json(window.LEDGER_PATH,row)

    def durable(self):
        row=window.ledger();row['active'].update(completed=self.counts.copy(),upper=self.counts.copy())
        write_json(window.LEDGER_PATH,row)

    def pc_count(self,key,n=1):
        self.guard();self.reserve(key,n);self.counts[key]+=n;self.durable()

    def finish(self,result):
        result.update(charged_counter_role='completed counts for clean run; write-ahead upper on interruption',
            historical_formal_lower_bound_seconds=77102.629289102,historical_auxiliary='unknown retained')
        super().finish(result)


def main():
    window.guard_worker_parent()
    stage=DirectionStage(io.load_block_diagnostic(sys.argv[1]),Path(sys.argv[2]).resolve());result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V25 active source changed')
        from src.solvers.block_direction_study import run
        result=run(stage)
    except Exception as error:
        result.update(getattr(stage,'partial_result',{}));result.update(status='FAILED',error=type(error).__name__+': '+str(error))
        traceback.print_exc();raise
    finally:stage.finish(result)


if __name__=='__main__':main()
