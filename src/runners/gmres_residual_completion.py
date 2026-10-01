"""Thin V18 adapter: original Stage/action/audit, separate library/algorithm."""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

from src.io import gmres_residual_completion as io
from src.runners.orthonormal_trace_reprofile import Stage
from src.runners.task042_shared import write_json
from src.solvers import residual_completion_window as window

LIMITS=dict(new_A_columns=6196,image_QR=2,original_audits=512,field_states=12)


class CompletionStage(Stage):
    def __init__(self,specification,directory):
        self.run_started=time.monotonic();name=specification.derived['stage'].removeprefix('V18-')
        self.algorithm_name,self.family_name=io.stage_route(name)
        if (self.algorithm_name,self.family_name)!=(specification.derived['algorithm'],specification.derived['library']):
            raise ValueError('V18 stage/algorithm/library registration differs')
        self.base=window.ledger()
        if self.base.get('active') is not None:raise ValueError('another owned V18 worker still active')
        self.restart={'G64':64,'G256':256}.get(self.algorithm_name,0)
        self.reservation=self.restart+16 if self.restart else 64
        self.base['active']=dict(directory=str(directory),stage=name,algorithm=self.algorithm_name,family=self.family_name,
            actions_lower=0,actions_upper=self.reservation,audits_lower=0,audits_upper=2,
            updates_lower=0,updates_upper=16 if self.algorithm_name=='R' else 0,
            arnoldi_lower=0,arnoldi_upper=self.restart,source_sha=(directory/'source_sha.txt').read_text().strip())
        write_json(window.LEDGER_PATH,self.base)
        super().__init__(specification,directory,io_module=io,window_module=window,limits=LIMITS,action_limit=66000,family=io.FAMILY)
        self.carry_actions=self.base['actions_upper']
        self.counts=dict(new_A_columns=self.base['new_A_columns'],image_QR=self.base['image_QR'],original_audits=self.base['audits_upper'],field_states=self.base['field_states'])
        self.started=dict(S=0,SH=0);self.new_updates=0;self.arnoldi_run=0;self.gmres_pending=False;self.last_written=0
        self.numeric_io=dict(started=0,completed=0,bytes_completed=0,wall_completed_seconds=0.)
        original=self.packet.apply
        def apply(x,adjoint=False):
            if self.packet.counts['S']+self.packet.counts['SH']-self.last_written>=32:self.durable_counts()
            self.guard(extra_actions=1);self.started['SH' if adjoint else 'S']+=1
            return original(x,adjoint=adjoint)
        self.packet.apply=apply

    def guard(self,*,extra_actions=0,large=False):
        super().guard(extra_actions=extra_actions,large=large)
        total=self.packet.counts['S']+self.packet.counts['SH']
        if self.family_name:
            prior=self.base['routes'][self.family_name];budget=json.loads(window.BUDGET_PATH.read_text())
            if prior['actions_upper']+total+extra_actions>28000:raise RuntimeError('V18 per-library original action cap')
            elapsed=time.monotonic()-self.run_started
            if prior['wall_seconds']+elapsed>budget['uniform_route_wall_seconds']-10:raise RuntimeError('V18 library wall boundary')
            if self.restart and prior['G_wall_seconds']+elapsed>budget['GMRES_total_ceiling_seconds']-10:raise RuntimeError('V18 G64/G256 total wall boundary')
        elif self.algorithm_name=='F0' and (total+extra_actions>256 or time.monotonic()-self.run_started>590):
            raise RuntimeError('V18 F0 action/wall boundary')

    def durable_counts(self,*,reserve=None):
        reserve=self.reservation if reserve is None else reserve
        row=window.ledger();total=self.packet.counts['S']+self.packet.counts['SH']
        row['active'].update(actions_lower=total,actions_upper=total+reserve,
            audits_lower=self.counts['original_audits']-self.base['audits_upper'],
            audits_upper=self.counts['original_audits']-self.base['audits_upper']+(2 if reserve else 0),
            updates_lower=self.new_updates,updates_upper=self.new_updates+(16 if reserve and self.algorithm_name=='R' else 0),
            arnoldi_lower=self.arnoldi_run,arnoldi_upper=self.arnoldi_run+(self.restart if reserve and self.gmres_pending else 0),
            started=self.started.copy(),completed=self.packet.counts.copy(),numeric_io=self.numeric_io.copy(),
            new_A_columns=self.counts['new_A_columns']-self.base['new_A_columns'],image_QR=self.counts['image_QR']-self.base['image_QR'],
            field_states=self.counts['field_states']-self.base['field_states'],
            correction_restarts=self.base['routes'][self.family_name]['correction_restarts'] if self.family_name else 0)
        write_json(window.LEDGER_PATH,row);self.last_written=total

    def gmres_returned(self,inner):
        self.arnoldi_run+=inner['inner_iterations'];self.gmres_pending=False;self.durable_counts(reserve=16)

    def begin_numeric_io(self):
        self.numeric_io['started']+=1;self.durable_counts();return time.perf_counter()

    def complete_numeric_io(self,began,path):
        self.numeric_io['completed']+=1;self.numeric_io['bytes_completed']+=Path(path).stat().st_size
        self.numeric_io['wall_completed_seconds']+=time.perf_counter()-began

    def finish(self,result):
        result['numeric_io']=dict(self.numeric_io,scope='this worker; inclusive atomic-save/hash wall, not additive to worker total')
        result.update(algorithm=self.algorithm_name,library=self.family_name,new_Arnoldi_iterations=self.arnoldi_run)
        self.durable_counts(reserve=self.reservation if result.get('status')=='FAILED' else 0)
        super().finish(result)


def execute_stage(stage):
    from src.solvers.gmres_residual_completion import preflight,gmres_route,continue_route,verify
    if stage.own_plan['resident_upper_bytes']>8*2**30:raise MemoryError('V18 resident plan exceeds 8GiB')
    if stage.algorithm_name=='F0':return preflight(stage)
    if stage.algorithm_name=='V':return verify(stage)
    if stage.restart:return gmres_route(stage)
    return continue_route(stage)


def main():
    window.guard_worker_parent();specification=io.load_residual_completion(sys.argv[1]);directory=Path(sys.argv[2]).resolve()
    stage=CompletionStage(specification,directory);result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V18 source changed after clean launch')
        result=execute_stage(stage)
        if specification.derived['environment_mode']=='pure':
            from src.runners.actual_loss_block_descent import _pure_blas_threads
            result['threads']=_pure_blas_threads()
    except Exception as error:
        result.update(status='FAILED',error=type(error).__name__+': '+str(error),queue_frozen=True)
        traceback.print_exc();raise
    finally:stage.finish(result)


if __name__=='__main__':main()
