"""Thin V22 adapter over the established stage, watchdog and atomic writer."""
import sys,time,subprocess,traceback
from pathlib import Path
from src.io import p1_trace_galerkin as io
from src.solvers import p1_trace_window as window
from src.runners.orthonormal_trace_reprofile import Stage
from src.runners.task042_shared import write_json

class P1Stage(Stage):
    def __init__(self,specification,directory,*,io_module=io,window_module=window,
                 action_limit=40000,limits=None,family=None,pc_key='B',
                 triangular_key='coarse_triangular',triangular_per_PC=4):
        self.base=window_module.ledger();self.run_started=time.monotonic()
        if self.base['active'] is not None:raise ValueError('V22 actor already active')
        super().__init__(specification,directory,io_module=io_module,window_module=window_module,
            limits=limits or dict(original_audits=160,field_states=12),action_limit=action_limit,family=family or io_module.FAMILY)
        self.pc_key,self.triangular_key,self.triangular_per_PC=pc_key,triangular_key,triangular_per_PC
        self.fast=None;self.reserve=32;self.pc_reserve=0;self.last_written=0
        self.aux={k:0 for k in self.window.CAPS if k not in ('actions','audits','field_states')}
        self.carry_actions=self.base['charged']['actions'];self.counts=dict(original_audits=self.base['charged']['audits'],field_states=self.base['charged']['field_states'])
        self.base['active']=dict(directory=str(directory),source_sha=self.source,completed={},upper={});write_json(self.window.LEDGER_PATH,self.base);self.durable()
        self.meta.update(factor_status='NOT_CONSTRUCTED',global_K_CSR_constructed=False,Q_U_R_loaded=False,hidden_training=False)
        original=self.packet.apply
        def apply(x,adjoint=False):
            self.guard(extra_actions=1)
            if self.actions()-self.last_written>=16:self.durable()
            return original(x,adjoint=adjoint)
        self.packet.apply=apply

    def actions(self):return self.packet.counts['S']+self.packet.counts['SH']+(sum(self.fast.counts.values()) if self.fast else 0)

    def guard(self,*,extra_actions=0,large=False):
        self.sample();self.window.require_live(margin=300 if large else 10)
        actions=self.actions() if hasattr(self,'fast') else 0
        if self.carry_actions+actions+extra_actions>self.action_limit:raise RuntimeError('bounded global action cap')
        if self.base['routes'].get(self.name,{}).get('actions',0)+actions+extra_actions>self.io.ROUTE_ACTION[self.name]:raise RuntimeError('bounded route action cap')
        if self.base['routes'].get(self.name,{}).get('wall_seconds',0.)+time.monotonic()-self.run_started>self.io.ROUTE_WALL[self.name]-10:raise RuntimeError('bounded route wall')
        now=time.monotonic()
        if now-getattr(self,'last_artifact_check',0)>5:
            if sum(p.stat().st_size for p in self.io.ARTIFACT_ROOT.rglob('*') if p.is_file())>2*2**30:raise MemoryError('bounded persistent artifact cap')
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
        if self.base['charged'][key]+self.aux[key]+n>self.window.CAPS[key]:raise RuntimeError('bounded '+key+' cap')
        self.aux[key]+=n
        if key in ('transfer_builds','coarse_assemblies','factor_setups') or self.aux[key]%16==0:self.durable()

    def durable(self):
        done=dict(self.aux,actions=self.actions(),audits=self.counts['original_audits']-self.base['charged']['audits'],field_states=self.counts['field_states']-self.base['charged']['field_states'])
        upper=dict(done,actions=done['actions']+self.reserve,audits=done['audits']+(2 if self.reserve else 0))
        upper[self.pc_key]=done[self.pc_key]+self.pc_reserve
        upper[self.triangular_key]=done[self.triangular_key]+self.triangular_per_PC*self.pc_reserve
        row=self.window.ledger();row['active'].update(completed=done,upper=upper);write_json(self.window.LEDGER_PATH,row);self.last_written=done['actions']

    def reserve_cycle(self,*,pc):
        self.guard(extra_actions=600)
        if pc and (self.base['charged'][self.pc_key]+self.aux[self.pc_key]+300>self.window.CAPS[self.pc_key] or self.base['charged'][self.triangular_key]+self.aux[self.triangular_key]+300*self.triangular_per_PC>self.window.CAPS[self.triangular_key]):raise RuntimeError('bounded reserved coarse cycle budget')
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
            from src.solvers.p1_trace_error_diagnostic import frozen_callback
            result=verify(stage,state_loader=load_state,offline_diagnostic=frozen_callback(stage))
        else:result=route(stage)
    except Exception as error:
        result.update(getattr(stage,'partial_result',{}))
        result.update(status='FAILED',error=type(error).__name__+': '+str(error));traceback.print_exc();raise
    finally:stage.finish(result)

if __name__=='__main__':main()
