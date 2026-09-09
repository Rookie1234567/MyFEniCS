"""Opt-in p4 coarse elimination; existing H4/A4/p2 operators are borrowed."""
import time
import numpy as np
from .physical_recursive_coarse import solve_physical_i4
from src.runners.workflow_timebase import ClockBudget, clock_sample, CONSERVATIVE_REALTIME


class ProjectedP4Complement:
    """J(v)=(I-C2 A4)H4 v, with one owned-vector coarse solve per call."""
    def __init__(self, action, coarse, smoother, *, sample):
        self.action,self.coarse,self.smoother,self.sample=action,coarse,smoother,sample
        self.counts={k:0 for k in ('J_started','J_completed','H4_started','H4_completed',
            'A4_started','A4_completed','C2_started','C2_completed')}
        self.operation_seconds={k:0. for k in ('H4','A4','C2')}

    def _call(self,name,action,x):
        self.sample();self.counts[name+'_started']+=1;start=time.perf_counter()
        try:
            value=action(x);self.counts[name+'_completed']+=1;return value
        finally:self.operation_seconds[name]+=time.perf_counter()-start

    def apply(self,x):
        self.counts['J_started']+=1
        h=ah=c=None
        try:
            h=self._call('H4',self.smoother,x)
            ah=self._call('A4',self.action,h)
            c=self._call('C2',self.coarse,ah)
            h.axpy(-1,c)
            if not np.isfinite(h.norm()):raise FloatingPointError('nonfinite projected J')
            self.counts['J_completed']+=1;value=h;h=None;return value
        finally:
            for v in (c,ah,h):
                if v is not None:v.destroy()


def solve_projected_p4_complement(rhs, action, coarse, smoother, *, sample, save,
                                  clock=None, stop_requested=lambda:False):
    """One bounded I4, c=C2g+delta; delta starts at zero, tolerance uses ||g||.

    The shared timer starts before C2g. No reference field enters this path.
    Returned solution/applied/residual are owned and refer to original g/A4.
    """
    budget=ClockBudget(clock_sample(),policy=CONSERVATIVE_REALTIME)
    seconds=clock or (lambda:budget.update(clock_sample())['budget_seconds'])
    start_seconds=seconds()  # Establish the timer before any coarse preparation.
    J=ProjectedP4Complement(action,coarse,smoother,sample=sample)
    counts={k:0 for k in ('initial_C2_started','initial_C2_completed','initial_A4_started',
        'initial_A4_completed','krylov_A4_started','krylov_A4_completed','final_A4_started','final_A4_completed')}
    times={k:0. for k in ('initial_C2','initial_A4','krylov_A4','final_A4')}
    c0=r0=result=solution=applied=residual=None
    inner_failure=success_facts=None
    def call(name,op,x):
        sample();counts[name+'_started']+=1;start=time.perf_counter()
        try:
            value=op(x);counts[name+'_completed']+=1;return value
        finally:times[name]+=time.perf_counter()-start
    def failed(name,facts):
        nonlocal inner_failure
        inner_failure=facts;save('projected_'+name,facts)
    def ledger():
        return dict(mechanism='projected_p4_complement_v1',counts=dict(counts),
            J_counts=dict(J.counts),operation_seconds=dict(times),J_operation_seconds=dict(J.operation_seconds),
            seconds=seconds(),timer_start_seconds=start_seconds,
            time_scope='whole I4 including C2g preparation, shared 60s conservative budget',
            counts_scope='krylov_A4 includes shared solver matvec plus explicit delta-residual checks')
    try:
        norm=float(rhs.norm())
        if not np.isfinite(norm):raise FloatingPointError('nonfinite original g')
        c0=call('initial_C2',coarse,rhs)
        applied=call('initial_A4',action,c0)
        r0=rhs.copy();r0.axpy(-1,applied);applied.destroy();applied=None
        preparation_seconds=seconds()
        result=solve_physical_i4(r0,lambda x:call('krylov_A4',action,x),J.apply,
            target=1e-4,sample=sample,save=failed,clock=seconds,stop_requested=stop_requested,
            residual_norm=norm)
        solution=c0.copy();solution.axpy(1,result['solution'])
        applied=call('final_A4',action,solution)
        residual=rhs.copy();residual.axpy(-1,applied)
        absolute=float(residual.norm());relative=absolute/norm if norm else (0. if absolute==0 else float('inf'))
        if not np.isfinite(relative):raise FloatingPointError('nonfinite original projected I4 residual')
        facts=ledger()
        facts.update(status='INNER_TARGET_REACHED' if relative<=1e-4 else 'INNER_INEXACT_AT_CAP',
            target=1e-4,final_true_residual=relative,eps_norm=absolute,rhs_norm=norm,
            reduced_rhs_norm=float(r0.norm()),preparation_seconds=preparation_seconds,
            initial_correction_zero=False,delta_zero_start=True,reference_input=False,
            inner=result['facts'],inner_callback_role='shared inner B4_calls/attempted.B4_calls count J here',
            original_residual_authority='g-A4(C2g+delta), normalized by ||g||')
        success_facts=facts
        value=dict(solution=solution,applied=applied,residual=residual,facts=facts)
        solution=applied=residual=None;return value
    except BaseException as exc:
        facts=ledger();facts.update(reason=str(exc),inner_failure=inner_failure,
            rhs=rhs.array.copy(),coarse_solution=c0.array.copy() if c0 is not None else None)
        save('projected_i4_failure',facts);raise
    finally:
        if result is not None:
            for k in ('solution','applied','residual'):result[k].destroy()
        for v in (c0,r0,solution,applied,residual):
            if v is not None:v.destroy()
        if success_facts is not None:
            success_facts['seconds']=seconds()
            success_facts['temporary_vectors_released']=True
