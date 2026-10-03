"""Thin one-run V27 entry using the established adapter/watchdog/writer."""
import subprocess,sys,traceback,time
from pathlib import Path
from src.io import return_block_diagnostic as io
from src.solvers import return_block_window as window
from src.runners.block_direction_diagnostic import DirectionStage


class ReturnStage(DirectionStage):
    def finish(self,result):
        # Metadata seal only. No new physical action, factor, or decomposition.
        from src.solvers.neural_fe_action_packet import file_hash
        from src.runners.task042_shared import write_json
        import json
        path=self.directory/'run_manifest.json';manifest=json.loads(path.read_text())
        manifest.update(completed_budget_counts=self.counts.copy(),completed_action_counts=self.packet.counts.copy(),
            plan_sha256=self.meta['plan_sha256'])
        write_json(path,manifest)
        result.update(run_directory=str(self.directory),run_manifest=dict(path=str(path),sha256=file_hash(path)),
            ledger_path=str(self.window.LEDGER_PATH))
        super().finish(result)

    def guard(self,**kwargs):
        super().guard(**kwargs)
        if getattr(self.io,'LABEL','V27')=='V31' and time.monotonic()-self.run_started>=470:
            raise RuntimeError('V31 actor cutoff/cleanup margin')
        now=time.monotonic()
        if now-getattr(self,'last_new_storage_check',0)>5:
            roots=[self.io.ARTIFACT_ROOT,self.directory,*((self.io.ROOT/'tmp/task042').glob('v27*'))]
            if getattr(self.io,'LABEL','V27')=='V31':
                roots=[self.io.ARTIFACT_ROOT,self.directory,self.window.TMP]
                size=sum(p.stat().st_size for root in roots for p in root.rglob('*') if p.is_file())
                if size>32*2**20:raise MemoryError('V31 new outputs including TMP cap')
                roots=[*(self.io.ROOT/'tmp/task042').glob('v2[789]*'),*(self.io.ROOT/'tmp/task042').glob('v3[01]*'),
                    *(self.io.ROOT/'benchmarks/artifacts/task042').glob('v2[789]'),*(self.io.ROOT/'benchmarks/artifacts/task042').glob('v3[01]')]
            if getattr(self.io,'LABEL','V27')=='V28':
                roots.extend([self.io.ROOT/'benchmarks/artifacts/task042/v27',*((self.io.ROOT/'tmp/task042').glob('v28*'))])
            size=sum(p.stat().st_size for root in roots for p in root.rglob('*') if p.is_file())
            if size>128*2**20:raise MemoryError('V27 new persistent outputs including TMP cap')
            self.last_new_storage_check=now


def main():
    global io,window
    if b'[task042_v31]' in Path(sys.argv[1]).read_bytes():
        from src.io import return_block_v31 as io
        from src.solvers import return_block_v31_window as window
    elif b'[task042_v28]' in Path(sys.argv[1]).read_bytes():
        from src.io import return_block_continuation as io
        from src.solvers import return_block_continuation_window as window
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
