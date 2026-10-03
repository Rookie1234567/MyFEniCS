"""Thin one-run V27 entry using the established adapter/watchdog/writer."""
import subprocess,sys,traceback,time
from pathlib import Path
from src.io import return_block_diagnostic as io
from src.solvers import return_block_window as window
from src.runners.block_direction_diagnostic import DirectionStage


class ReturnStage(DirectionStage):
    def guard(self,**kwargs):
        super().guard(**kwargs)
        now=time.monotonic()
        if now-getattr(self,'last_new_storage_check',0)>5:
            roots=[self.io.ARTIFACT_ROOT,self.directory,*((self.io.ROOT/'tmp/task042').glob('v27*'))]
            size=sum(p.stat().st_size for root in roots for p in root.rglob('*') if p.is_file())
            if size>128*2**20:raise MemoryError('V27 new persistent outputs including TMP cap')
            self.last_new_storage_check=now


def main():
    window.guard_worker_parent()
    stage=ReturnStage(io.load_return_diagnostic(sys.argv[1]),Path(sys.argv[2]).resolve(),
        io_module=io,window_module=window,historical_lower=77161.55713859801)
    result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V27 active source changed')
        from src.solvers.return_block_study import run
        result=run(stage)
    except Exception as error:
        result.update(getattr(stage,'partial_result',{}));result.update(status='FAILED',error=type(error).__name__+': '+str(error))
        traceback.print_exc();raise
    finally:stage.finish(result)


if __name__=='__main__':main()
