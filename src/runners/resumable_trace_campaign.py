"""Thin V17 worker using qualified Stage, original packet and own supervisor."""
import json
import sys
import time
import traceback
from pathlib import Path
from src.io import resumable_trace_campaign as io
from src.runners.orthonormal_trace_reprofile import Stage
from src.runners.task042_shared import write_json
from src.solvers import resumable_trace_window as window

LIMITS=dict(new_A_columns=6196,image_QR=2,original_audits=420,field_states=12)


class CampaignStage(Stage):
    def __init__(self,specification,directory):
        self.run_started=time.monotonic()
        name=specification.derived['stage']
        self.family_name=name.removeprefix('GMRES_') if name not in ('PREFLIGHT','VERIFY') else None
        self.base=window.ledger()
        if self.base.get('active') is not None:
            raise ValueError('another owned V17 worker is still active')
        self.base['active']=dict(directory=str(directory),stage=name,family=self.family_name,
                                start_monotonic=self.run_started,reserved_actions=64,reserved_audits=2,
                                actions_lower=0,actions_upper=64,audits_lower=0,audits_upper=2,
                                updates_lower=0,updates_upper=0,
                                source_sha=(directory/'source_sha.txt').read_text().strip())
        write_json(window.LEDGER_PATH,self.base)
        super().__init__(specification,directory,io_module=io,window_module=window,limits=LIMITS,action_limit=56000,family=io.FAMILY)
        self.carry_actions=self.base['actions_upper']
        self.counts=dict(new_A_columns=self.base['new_A_columns'],image_QR=self.base['image_QR'],
                         original_audits=self.base['audits_upper'],field_states=self.base['field_states'])
        self.numeric_io=dict(started=0,completed=0,bytes_completed=0,wall_completed_seconds=0.);self.started=dict(S=0,SH=0);self.new_updates=0;self.last_written=0;self.reservation=64
        self.base['active']=dict(directory=str(directory),stage=self.name,family=self.family_name,
                                start_monotonic=self.run_started,reserved_actions=64,reserved_audits=2,
                                actions_lower=0,actions_upper=64,updates_lower=0,updates_upper=16,
                                source_sha=self.source)
        write_json(window.LEDGER_PATH,self.base)
        original=self.packet.apply
        def apply(x,adjoint=False):
            if self.packet.counts['S']+self.packet.counts['SH']-self.last_written>=32:
                self.durable_counts()
            self.guard(extra_actions=1)
            self.started['SH' if adjoint else 'S']+=1
            return original(x,adjoint=adjoint)
        self.packet.apply=apply

    def guard(self,*,extra_actions=0,large=False):
        super().guard(extra_actions=extra_actions,large=large)
        total=self.packet.counts['S']+self.packet.counts['SH']
        if self.family_name:
            prior=self.base['routes'][self.family_name]
            if prior['actions_upper']+total+extra_actions>24000:raise RuntimeError('V17 per-library action cap')
            from src.solvers.resumable_trace_window import BUDGET_PATH
            budget=json.loads(BUDGET_PATH.read_text())
            limit=budget['uniform_route_wall_seconds']-(0 if self.name.startswith('GMRES_') else budget['GMRES_reserved_seconds'])
            if prior['wall_seconds']+time.monotonic()-self.run_started>limit-10:raise RuntimeError('V17 route wall boundary')
        elif self.name=='PREFLIGHT' and (total+extra_actions>400 or time.monotonic()-self.run_started>890):
            raise RuntimeError('V17 R1 qualification action/wall boundary')

    def durable_counts(self,*,reserve=64):
        row=window.ledger();total=self.packet.counts['S']+self.packet.counts['SH']
        row['active'].update(actions_lower=total,actions_upper=total+reserve,updates_lower=self.new_updates,
                             updates_upper=self.new_updates+(16 if reserve and self.name in ('GPOLY','GNN') else 0),
                             numeric_io=self.numeric_io.copy(),
                             started=self.started.copy(),completed=self.packet.counts.copy(),
                             audits_lower=self.counts['original_audits']-self.base['audits_upper'],
                             audits_upper=self.counts['original_audits']-self.base['audits_upper']+(2 if reserve else 0),
                             new_A_columns=self.counts['new_A_columns']-self.base['new_A_columns'],
                             image_QR=self.counts['image_QR']-self.base['image_QR'],
                             field_states=self.counts['field_states']-self.base['field_states'],
                             correction_restarts=(self.base['routes'][self.family_name]['correction_restarts'] if self.family_name else 0))
        write_json(window.LEDGER_PATH,row)
        self.last_written=total

    def begin_numeric_io(self):
        self.numeric_io['started']+=1
        self.durable_counts()
        return time.perf_counter()

    def complete_numeric_io(self,began,path):
        self.numeric_io['completed']+=1
        self.numeric_io['bytes_completed']+=Path(path).stat().st_size
        self.numeric_io['wall_completed_seconds']+=time.perf_counter()-began

    def finish(self,result):
        result['numeric_io']=dict(self.numeric_io,scope='this worker; atomic numeric save plus hashes; wall already included in worker total')
        # An exception may leave an incomplete action/GK update. Retain its
        # bounded reserve; only a completed normal worker releases it.
        self.durable_counts(reserve=64 if result.get('status')=='FAILED' else 0)
        super().finish(result)


def main():
    window.guard_worker_parent()
    specification=io.load_resumable_trace(sys.argv[1]);directory=Path(sys.argv[2]).resolve()
    stage=CampaignStage(specification,directory);result={}
    try:
        from src.solvers.resumable_trace_study import preflight,continue_route,gmres_route,verify
        if stage.own_plan['resident_upper_bytes']>8*2**30:raise MemoryError('V17 resident plan exceeds 8GiB')
        if stage.name=='PREFLIGHT':result=preflight(stage)
        elif stage.name=='VERIFY':result=verify(stage)
        elif stage.name.startswith('GMRES_'):result=gmres_route(stage)
        else:result=continue_route(stage)
        if specification.derived['environment_mode']=='pure':
            from src.runners.actual_loss_block_descent import _pure_blas_threads
            result['threads']=_pure_blas_threads()
    except Exception as error:
        result.update(status='FAILED',error=type(error).__name__+': '+str(error),queue_frozen=True)
        traceback.print_exc();raise
    finally:stage.finish(result)


if __name__=='__main__':main()
