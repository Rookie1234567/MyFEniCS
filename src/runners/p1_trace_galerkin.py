"""Thin V22 adapter over the established stage, watchdog and atomic writer."""
import sys,time,subprocess,traceback
from pathlib import Path
from src.io import p1_trace_galerkin as io
from src.solvers import p1_trace_window as window
from src.runners.orthonormal_trace_reprofile import Stage
from src.runners.task042_shared import write_json

class P1Stage(Stage):
    def __init__(self,specification,directory):
        self.base=window.ledger();self.run_started=time.monotonic()
        if self.base['active'] is not None:raise ValueError('V22 actor already active')
        super().__init__(specification,directory,io_module=io,window_module=window,
            limits=dict(original_audits=160,field_states=12),action_limit=40000,family=io.FAMILY)
        self.fast=None;self.reserve=32;self.pc_reserve=0;self.last_written=0
        self.aux={k:0 for k in window.CAPS if k not in ('actions','audits','field_states')}
        self.carry_actions=self.base['charged']['actions'];self.counts=dict(original_audits=self.base['charged']['audits'],field_states=self.base['charged']['field_states'])
        self.base['active']=dict(directory=str(directory),source_sha=self.source,completed={},upper={});write_json(window.LEDGER_PATH,self.base);self.durable()
        self.meta.update(factor_status='NOT_CONSTRUCTED',global_K_CSR_constructed=False,Q_U_R_loaded=False,hidden_training=False)
        original=self.packet.apply
        def apply(x,adjoint=False):
            self.guard(extra_actions=1)
            if self.actions()-self.last_written>=16:self.durable()
            return original(x,adjoint=adjoint)
        self.packet.apply=apply

    def actions(self):return self.packet.counts['S']+self.packet.counts['SH']+(sum(self.fast.counts.values()) if self.fast else 0)

    def guard(self,*,extra_actions=0,large=False):
        self.sample();window.require_live(margin=300 if large else 10)
        actions=self.actions() if hasattr(self,'fast') else 0
        if self.carry_actions+actions+extra_actions>40000:raise RuntimeError('V22 global action cap')
        if self.base['routes'].get(self.name,{}).get('actions',0)+actions+extra_actions>io.ROUTE_ACTION[self.name]:raise RuntimeError('V22 route action cap')
        if self.base['routes'].get(self.name,{}).get('wall_seconds',0.)+time.monotonic()-self.run_started>io.ROUTE_WALL[self.name]-10:raise RuntimeError('V22 route wall')
        now=time.monotonic()
        if now-getattr(self,'last_artifact_check',0)>5:
            if sum(p.stat().st_size for p in io.ARTIFACT_ROOT.rglob('*') if p.is_file())>2*2**30:raise MemoryError('V22 persistent artifact cap')
            self.last_artifact_check=now

    def attach_fast(self):
        from src.solvers.class_batch_action import ClassBatchAction
        if self.fast is not None:return self.fast
        self.fast=ClassBatchAction(self.packet);original=self.fast.apply
        def apply(x,adjoint=False):
            self.guard(extra_actions=1)
            if self.actions()-self.last_written>=16:self.durable()
            return original(x,adjoint=adjoint)
        self.fast.apply=apply;return self.fast

    def pc_count(self,key,n=1):
        self.guard()
        if self.base['charged'][key]+self.aux[key]+n>window.CAPS[key]:raise RuntimeError('V22 '+key+' cap')
        self.aux[key]+=n
        if key in ('transfer_builds','coarse_assemblies','factor_setups') or self.aux[key]%16==0:self.durable()

    def durable(self):
        done=dict(self.aux,actions=self.actions(),audits=self.counts['original_audits']-self.base['charged']['audits'],field_states=self.counts['field_states']-self.base['charged']['field_states'])
        upper=dict(done,actions=done['actions']+self.reserve,audits=done['audits']+(2 if self.reserve else 0),
            B=done['B']+self.pc_reserve,coarse_triangular=done['coarse_triangular']+4*self.pc_reserve)
        row=window.ledger();row['active'].update(completed=done,upper=upper);write_json(window.LEDGER_PATH,row);self.last_written=done['actions']

    def reserve_cycle(self,*,pc):
        self.guard(extra_actions=600)
        if pc and (self.base['charged']['B']+self.aux['B']+300>window.CAPS['B'] or self.base['charged']['coarse_triangular']+self.aux['coarse_triangular']+1200>window.CAPS['coarse_triangular']):raise RuntimeError('V22 reserved coarse cycle budget')
        self.reserve=600;self.pc_reserve=300 if pc else 0;self.durable()

    def returned(self,inner):self.reserve=32;self.pc_reserve=1;self.durable()

    def finish(self,result):
        if result.get('status')!='FAILED':self.reserve=0;self.pc_reserve=0
        self.durable();result.update(aux_counts=self.aux,new_backend_action_counts=self.fast.counts.copy() if self.fast else {},
            all_incremental_equivalent_actions=self.actions(),numerical_actor_wall_seconds=time.monotonic()-self.run_started,shared_workstation=True)
        self.carry_actions+=sum(self.fast.counts.values()) if self.fast else 0;super().finish(result)

def main():
    window.guard_worker_parent();stage=P1Stage(io.load_p1_trace(sys.argv[1]),Path(sys.argv[2]).resolve());result={}
    try:
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=stage.source:raise RuntimeError('V22 active source changed')
        from src.solvers.p1_trace_study import setup,route,load_state
        if stage.name=='SETUP':result=setup(stage)
        elif stage.name=='VERIFY':
            from src.solvers.gmres_residual_completion import verify
            result=verify(stage,state_loader=load_state)
        else:result=route(stage)
    except Exception as error:
        result.update(getattr(stage,'partial_result',{}))
        result.update(status='FAILED',error=type(error).__name__+': '+str(error));traceback.print_exc();raise
    finally:stage.finish(result)

if __name__=='__main__':main()
