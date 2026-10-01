"""Small V20 stage adapter over the existing action, writer and watchdog."""
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path
from src.io import fixed_p3_ilu0 as io
from src.runners.orthonormal_trace_reprofile import Stage
from src.runners.task042_shared import write_json
from src.solvers import fixed_p3_ilu0_window as window


class ILUStage(Stage):
    def __init__(self,specification,directory):
        self.base=window.ledger();self.run_started=time.monotonic()
        if self.base['active'] is not None:raise ValueError('V20 actor already active')
        super().__init__(specification,directory,io_module=io,window_module=window,
            limits=dict(original_audits=120,field_states=12),action_limit=35000,family=io.FAMILY)
        self.carry_actions=self.base['charged']['actions']
        self.counts=dict(original_audits=self.base['charged']['audits'],field_states=self.base['charged']['field_states'])
        self.aux=dict(B0=0,F=0,K_assemblies=0,factor_setups=0)
        self.last_written=0;self.reserve=32
        self.base['active']=dict(directory=str(directory),source_sha=self.source,completed={},upper={})
        write_json(window.LEDGER_PATH,self.base);self.durable()
        self.meta.update(global_p3_incomplete_factor_constructed=False,
                         factor_status='NOT_YET_CONSTRUCTED',global_K_CSR_constructed=False)
        original=self.packet.apply
        def apply(x,adjoint=False):
            self.guard(extra_actions=1)
            if sum(self.packet.counts[k] for k in ('S','SH'))-self.last_written>=16:self.durable()
            return original(x,adjoint=adjoint)
        self.packet.apply=apply

    def guard(self,*,extra_actions=0,large=False):
        super().guard(extra_actions=extra_actions,large=large)
        now=time.monotonic()
        if now-getattr(self,'last_artifact_check',0)>5:
            payload=sum(p.stat().st_size for p in io.ARTIFACT_ROOT.rglob('*') if p.is_file())
            if payload>2*2**30:raise MemoryError('V20 new persistent artifact cap')
            self.last_artifact_check=now
        prior=self.base['routes'].get(self.name,{}).get('wall_seconds',0.)
        if time.monotonic()-self.run_started+prior>io.ROUTE_WALL[self.name]-5:
            raise RuntimeError('V20 fixed route wall reached')
        for key in self.aux if hasattr(self,'aux') else ():
            if self.base['charged'][key]+self.aux[key]>window.CAPS[key]:raise RuntimeError('V20 '+key+' cap')

    def pc_count(self,key,n=1):
        self.guard()
        if self.base['charged'][key]+self.aux[key]+n>window.CAPS[key]:raise RuntimeError('V20 '+key+' cap')
        self.aux[key]+=n
        if key in ('K_assemblies','factor_setups') or self.aux[key]%16==0:self.durable()

    def durable(self):
        done=dict(self.aux,actions=self.packet.counts['S']+self.packet.counts['SH'],
                  audits=self.counts['original_audits']-self.base['charged']['audits'],
                  field_states=self.counts['field_states']-self.base['charged']['field_states'])
        upper=done.copy()
        for key in ('actions','B0','F'):upper[key]+=self.reserve
        upper['audits']+=2 if self.reserve else 0
        row=window.ledger();row['active'].update(completed=done,upper=upper)
        write_json(window.LEDGER_PATH,row);self.last_written=done['actions']

    def finish(self,result):
        self.reserve=0 if result.get('status')!='FAILED' else 320;self.durable()
        result.update(aux_counts=self.aux.copy(),numerical_actor_wall_seconds=time.monotonic()-self.run_started,
                      shared_workstation=True)
        super().finish(result)


def execute_stage(stage):
    from src.solvers.fixed_p3_ilu0_study import setup,route,load_state
    if stage.name=='SETUP':return setup(stage)
    if stage.name=='VERIFY':
        from src.solvers.gmres_residual_completion import verify
        return verify(stage,state_loader=load_state)
    return route(stage)


def main():
    window.guard_worker_parent();spec=io.load_fixed_ilu0(sys.argv[1]);stage=ILUStage(spec,Path(sys.argv[2]).resolve());result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V20 active source changed')
        result=execute_stage(stage)
    except Exception as error:
        result.update(status='FAILED',error=type(error).__name__+': '+str(error));traceback.print_exc();raise
    finally:stage.finish(result)


if __name__=='__main__':main()
