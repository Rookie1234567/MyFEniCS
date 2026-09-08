"""Thin supervision and borrowed-solver wiring for bounded error diagnostics."""
from pathlib import Path

from .workflow_timebase import (checked_interval, clock_sample, ClockBudget, STRICT,
                               CONSERVATIVE_REALTIME, POLICY_VERSION, TimebaseInconsistency)


def supervise_diagnosis(command, directory, *, phase_path, expected_sha, kind,
                        remaining_seconds, cache_path=None):
    """Use the same outer guard for diagnostics and the optional run_case direct.

    Caller supplies the already-reviewed command and shared remaining budget;
    this function never chooses another solver or starts a retry.
    """
    from benchmarks.subreaper_watchdog import supervise
    from .task038_launcher import _physical_source_gate
    if kind not in ('diagnosis','reference','completion_v4'):
        raise ValueError('unknown diagnostic workflow kind')
    limit = min(remaining_seconds,{'reference':3600,'diagnosis':7200,'completion_v4':5400}[kind])
    state = _physical_source_gate(Path.cwd(),expected_sha)
    result = supervise(command,Path(directory),wall_seconds=limit,phase_path=Path(phase_path),
                       source_state=state,interval=.25,grace_seconds=2,
                       hard_stop_immediate=True,timebase_guard=True,cache_path=cache_path,
                       timebase_policy=CONSERVATIVE_REALTIME,
                       worker_environment={} if cache_path is None else {'XDG_CACHE_HOME':str(cache_path)})
    result['source_after'] = _physical_source_gate(Path.cwd(),expected_sha)
    return result


class DiagnosticActions:
    """Borrow one existing S6/A6/P64/p4 stack; add unchanged LIGHT plus metrics.

    The caller builds/qualifies and eventually destroys that single stack.
    This object owns only its extra H6, metric actions and vector bridges.
    """

    def __init__(self,bundle,cfg,marker,*,timebase_policy=STRICT):
        from src.solvers.physical_error_metric import LosslessFEMetric,SerialAction
        from src.solvers.physical_light_setup import build_light_h6_setup
        self.bridges,self.metrics,self.light = [],{},None
        self.timings=[]
        self.timebase_policy=timebase_policy
        self.projection_seconds=0.
        self.projection_diagonal=None
        levels,fine = bundle['levels'],bundle['fine']
        transfer = bundle['actions']['transfers'][(6,4)]
        def bridge(action,source=6,target=6,result='target'):
            value=SerialAction(levels['spaces'][source],levels['floquets'][source],action,
                result=result,target_space=levels['spaces'][target],target_floquet=levels['floquets'][target])
            self.bridges.append(value)
            return value
        def timed(name,action):
            action.audit['label']=name
            def apply(x):
                marker(name+'_started',{})
                start=clock_sample()
                result=action(x)
                interval=checked_interval(start,clock_sample(),policy=self.timebase_policy)
                self.timings.append(dict(name=name,**interval))
                marker(name+'_complete',interval)
                return result
            return apply
        self.bridge, self.timed, self.marker = bridge, timed, marker
        try:
            self.A = bridge(fine['physical_action'].apply)
            self.components={k:bridge(v.apply,result='borrowed') for k,v in
                             fine['volume_action'].component_actions.items()}
            self.components['dtn']=bridge(fine['dtn_action'].apply)
            self.P=bridge(transfer.apply_primal,4,6,'owned')
            self.PH=bridge(transfer.apply_adjoint,6,4,'owned')
            for degree in (6,4):
                marker('lossless_metric_started',dict(degree=degree))
                self.metrics[degree]=LosslessFEMetric(levels,degree,cfg.k0,bundle['actions']['volume_quadrature_metadata'])
                marker('lossless_metric_complete',self.metrics[degree].audit)
            self.M0=self.metrics[6].mass
            self.light=build_light_h6_setup(levels,cfg,marker)
            h6=self.light['h6']
            self.profiles={}
            if 'reference_factor' in bundle:
                self.attach_reference(bundle)
            self.smoothers={name:timed(name,bridge(pc.apply,result='owned')) for name,pc in
                            [('H6',h6),('S6_complement',bundle['positive']['upper_cycle'])]}
        except BaseException:
            self.destroy()
            raise

    def attach_reference(self,bundle):
        from src.solvers.fullspace_physical_intermediate import PhysicalIntermediatePreconditioner
        reference=bundle['reference_factor']
        def solve(rhs):
            return reference.solve_intermediate(rhs)['final_solution']
        self.solve=self.timed('diagnostic_p4',self.bridge(solve,4,4,'owned'))
        policy=getattr(reference,'diagnostic_refinement_v4',None)
        pcs={'S6':bundle['pc']}
        for name,joint in [('LIGHT',False),('JOINT',True)]:
            pcs[name]=PhysicalIntermediatePreconditioner(bundle['fine']['physical_action'],
                self.light['h6'],bundle['actions']['transfers'][(6,4)],reference,
                positive_identity='H6',outer_max_it=2048,joint_mr=joint,stage_callback=self.marker,
                diagnostic_before_middle=None if policy is None else policy.before_middle)
        self.profiles={name:self.timed(name,self.bridge(pc.apply,result='owned')) for name,pc in pcs.items()}

    def project(self,e,*,checkpoint=lambda: None,retain_approximation=False):
        """Share the 1800s projection allowance, including diagonal setup."""
        from src.solvers.physical_error_diagnostics import project_error, ProjectionLimit
        start=clock_sample()
        projection_budget=ClockBudget(start,policy=self.timebase_policy)
        def check():
            checkpoint()
            if self.projection_seconds+projection_budget.update(clock_sample())['budget_seconds']>=1800:
                raise ProjectionLimit('cumulative projection budget exhausted')
        try:
            check()
            if self.projection_diagonal is None:
                self.projection_diagonal=self.metrics[4].diagonal(checkpoint=check)
            return project_error(self.P,self.PH,self.M0,self.projection_diagonal,e,checkpoint=check)
        except ProjectionLimit as exc:
            if not retain_approximation:
                return dict(status='PROJECTION_UNRESOLVED',reason=str(exc),parallel=None,perpendicular=None)
            # Diagonal setup expired before CG: zero is still a legal approximation.
            import numpy as np
            def exhausted():
                raise ProjectionLimit(str(exc))
            return project_error(self.P,self.PH,self.M0,
                np.ones(self.P.indices.size),e,checkpoint=exhausted)
        finally:
            self.projection_seconds+=projection_budget.update(clock_sample())['budget_seconds']

    def destroy(self):
        for bridge in self.bridges: bridge.destroy()
        for metric in self.metrics.values(): metric.destroy()
        if self.light is not None:
            self.light['h6'].destroy()
            self.light['p6_shell'].destroy()
        self.bridges.clear()
        self.metrics.clear()
        self.light=None


def main():
    import argparse,hashlib,json,sys
    from .physical_intermediate import _atomic_json
    from .task038_launcher import _physical_source_gate
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--expected-sha',required=True)
    parser.add_argument('--remaining-seconds',type=float,required=True)
    parser.add_argument('--cache-path',type=Path)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--completion-v4',action='store_true')
    args=parser.parse_args()
    _physical_source_gate(Path.cwd(),args.expected_sha)
    if args.worker:
        from .physical_diagnosis_worker import run_diagnosis
        run_diagnosis(args.input,args.inventory,args.directory,args.expected_sha,completion_v4=args.completion_v4)
        return 0
    args.directory.mkdir(parents=True,exist_ok=False)
    workflow_limit=5400 if args.completion_v4 else 7200
    start=clock_sample()
    pre_budget=ClockBudget(start,policy=CONSERVATIVE_REALTIME)
    post_budget=None
    def cache_inventory():
        records=[]
        for p in ([] if args.cache_path is None else sorted(args.cache_path.rglob('*'))):
            if p.is_file():
                records.append(dict(path=str(p),bytes=p.stat().st_size,
                    sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
                (post_budget or pre_budget).update(clock_sample())
        return records
    manifest=dict(source_sha=args.expected_sha,clock_start=start,
        timebase_policy=CONSERVATIVE_REALTIME,timebase_policy_version=POLICY_VERSION,
        input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
        inventory_sha256=hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        cache_before=cache_inventory(),kind='no-reference D1/D3',
        complete_pc_limit=15,independent_smoother_limit=4,projection_seconds=1800,
        reference='not_run_capacity_unqualified')
    if args.completion_v4:
        manifest.update(kind='completion_v4',complete_pc_limit=8,logical_p4_rhs_limit=10,
                        external_MatSolve_limit=30,workflow_limit_seconds=5400)
    _atomic_json(args.directory/'launch.json',manifest)
    command=['mpiexec','-n','1',sys.executable,'-m','src.runners.physical_diagnosis',
        '--worker','--directory',str(args.directory),'--input',str(args.input),
        '--inventory',str(args.inventory),'--expected-sha',args.expected_sha,
        '--remaining-seconds',str(args.remaining_seconds)]
    if args.completion_v4:
        command.append('--completion-v4')
    result=None
    try:
        result=supervise_diagnosis(command,args.directory/'watchdog',phase_path=args.directory/'phase.json',
            expected_sha=args.expected_sha,kind='completion_v4' if args.completion_v4 else 'diagnosis',
            remaining_seconds=min(workflow_limit,args.remaining_seconds)-pre_budget.update(clock_sample())['budget_seconds'],
            cache_path=args.cache_path)
        manifest['supervision']=result
        manifest['pre_supervision_interval']=pre_budget.update(result['clock_start'])
        post_budget=ClockBudget(result['clock_end'],policy=CONSERVATIVE_REALTIME)
        manifest['cache_after']=cache_inventory()
    except BaseException as exc:
        manifest['finalization_error']=dict(type=type(exc).__name__,message=str(exc))
        if result is None or result['classification']=='COMPLETED':
            manifest['classification']='LAUNCH_OR_FINALIZATION_FAILED'
        raise
    finally:
        manifest['clock_end']=clock_sample()
        try:
            manifest['interval']=checked_interval(start,manifest['clock_end'],policy=CONSERVATIVE_REALTIME)
            if result is not None and post_budget is not None:
                manifest['post_supervision_interval']=post_budget.update(manifest['clock_end'])
                charge=(pre_budget.seconds+result['workflow_clock_interval']['budget_seconds']+
                        post_budget.seconds)
                manifest['budget_complete']=result['workflow_clock_interval'].get('budget_complete',True)
            else:
                charge=pre_budget.update(manifest['clock_end'])['budget_seconds']
            manifest['interval']['budget_seconds']=charge
            if charge>min(workflow_limit,args.remaining_seconds):
                manifest['workflow_limit_exceeded']=True
                if (result is not None and result['classification']=='COMPLETED' and
                        'classification' not in manifest):
                    manifest['classification']='PERFORMANCE_CONTROLLED_STOP'
        except TimebaseInconsistency as exc:
            manifest['final_clock_error']=str(exc)
            if result is None or result['classification']=='COMPLETED':
                manifest['classification']='TIMEBASE_INCONSISTENCY'
        manifest.setdefault('classification',result['classification'] if result is not None else 'LAUNCH_OR_FINALIZATION_FAILED')
        _atomic_json(args.directory/'launch.json',manifest)
    classification=manifest['classification']
    print(json.dumps(dict(classification=classification,directory=str(args.directory))))
    return 0 if classification=='COMPLETED' else 2


if __name__=='__main__':
    raise SystemExit(main())
