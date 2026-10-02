"""Thin V21 adapter; all numerical action/recycle work lives in solvers."""
import subprocess
import sys
import time
import traceback
from pathlib import Path
from src.io import exact_action_recycling as io
from src.runners.orthonormal_trace_reprofile import Stage
from src.runners.task042_shared import write_json
from src.solvers import exact_recycle_window as window


class RecycleStage(Stage):
    def __init__(self,specification,directory):
        self.base=window.ledger();self.run_started=time.monotonic()
        if self.base['active'] is not None:raise ValueError('V21 own actor already active')
        super().__init__(specification,directory,io_module=io,window_module=window,
            limits=dict(original_audits=320,field_states=12),action_limit=100000,family=io.FAMILY)
        self.fast=None;self.reserve=32;self.last_written=0
        self.carry_actions=self.base['charged']['actions']
        self.counts=dict(original_audits=self.base['charged']['audits'],field_states=self.base['charged']['field_states'])
        self.base['active']=dict(directory=str(directory),source_sha=self.source,completed={},upper={})
        write_json(window.LEDGER_PATH,self.base);self.durable()
        self.meta.update(global_p3_incomplete_factor_constructed=False,factor_status='NO_GLOBAL_FACTOR',
            global_K_CSR_constructed=False,Q_U_R_loaded=False,hidden_training=False)
        original=self.packet.apply
        def oracle_apply(x,adjoint=False):
            self.guard(extra_actions=1)
            if self.actions()-self.last_written>=16:self.durable()
            return original(x,adjoint=adjoint)
        # This only guards/counts the preserved OLD method; never dispatches fast.
        self.packet.apply=oracle_apply

    def actions(self):
        return self.packet.counts['S']+self.packet.counts['SH']+(sum(self.fast.counts.values()) if self.fast is not None else 0)

    def guard(self,*,extra_actions=0,large=False):
        self.sample();window.require_live(heavy=True,margin=300 if large else 10)
        actions=self.actions() if hasattr(self,'fast') else 0
        if self.carry_actions+actions+extra_actions>100000:raise RuntimeError('V21 global action cap')
        prior=self.base['routes'].get(self.name,{}).get('actions',0)
        if prior+actions+extra_actions>io.ROUTE_ACTION[self.name]:raise RuntimeError('V21 route action cap')
        wall=self.base['routes'].get(self.name,{}).get('wall_seconds',0.)+time.monotonic()-self.run_started
        if wall>io.ROUTE_WALL[self.name]-10:raise RuntimeError('V21 fixed route wall reached')
        now=time.monotonic()
        if now-getattr(self,'last_artifact_check',0)>5:
            payload=sum(p.stat().st_size for p in io.ARTIFACT_ROOT.rglob('*') if p.is_file())
            if payload>2*2**30:raise MemoryError('V21 persistent artifact cap')
            self.last_artifact_check=now

    def attach_fast(self):
        from src.solvers.class_batch_action import ClassBatchAction
        self.fast=ClassBatchAction(self.packet);original=self.fast.apply
        def apply(x,adjoint=False):
            self.guard(extra_actions=1)
            if self.actions()-self.last_written>=16:self.durable()
            return original(x,adjoint=adjoint)
        self.fast.apply=apply
        return self.fast

    def durable(self):
        done=dict(actions=self.actions(),audits=self.counts['original_audits']-self.base['charged']['audits'],
                  field_states=self.counts['field_states']-self.base['charged']['field_states'])
        upper=dict(done,actions=done['actions']+self.reserve,audits=done['audits']+(2 if self.reserve else 0))
        row=window.ledger();row['active'].update(completed=done,upper=upper)
        write_json(window.LEDGER_PATH,row);self.last_written=done['actions']

    def reserve_cycle(self):
        self.guard(extra_actions=384)
        self.reserve=384;self.durable()

    def returned(self,inner):
        self.reserve=32;self.durable()

    def finish(self,result):
        self.reserve=0 if result.get('status')!='FAILED' else self.reserve;self.durable()
        result.update(new_backend_action_counts=self.fast.counts.copy() if self.fast else dict(S=0,SH=0),
                      new_backend_costs_seconds=self.fast.costs.copy() if self.fast else {},
                      all_incremental_equivalent_actions=self.actions(),
                      numerical_actor_wall_seconds=time.monotonic()-self.run_started,shared_workstation=True)
        self.carry_actions+=sum(self.fast.counts.values()) if self.fast else 0
        super().finish(result)


def main():
    window.guard_worker_parent();spec=io.load_recycling(sys.argv[1]);stage=RecycleStage(spec,Path(sys.argv[2]).resolve());result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V21 active source changed')
        from src.solvers.exact_action_recycle_study import preflight,route,load_state
        if stage.name=='PREFLIGHT':result=preflight(stage)
        elif stage.name=='VERIFY':
            from src.solvers.gmres_residual_completion import verify
            result=verify(stage,state_loader=load_state)
        else:result=route(stage)
    except Exception as error:
        result.update(status='FAILED',error=type(error).__name__+': '+str(error));traceback.print_exc();raise
    finally:stage.finish(result)


if __name__=='__main__':main()
