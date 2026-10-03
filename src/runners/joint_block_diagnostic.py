"""Thin V26 entry; shares the V25 bounded adapter without changing defaults."""
import subprocess,sys,traceback
from pathlib import Path
from src.io import joint_block_diagnostic as io
from src.solvers import joint_block_window as window
from src.runners.block_direction_diagnostic import DirectionStage


def main():
    window.guard_worker_parent()
    stage=DirectionStage(io.load_joint_diagnostic(sys.argv[1]),Path(sys.argv[2]).resolve(),
        io_module=io,window_module=window,actor_limit=900,artifact_limit=768*2**20,
        historical_lower=77128.294516111)
    result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V26 active source changed')
        from src.solvers.joint_block_study import run
        result=run(stage)
    except Exception as error:
        result.update(getattr(stage,'partial_result',{}));result.update(status='FAILED',error=type(error).__name__+': '+str(error))
        traceback.print_exc();raise
    finally:stage.finish(result)


if __name__=='__main__':main()
