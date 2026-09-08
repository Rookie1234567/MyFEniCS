"""Thin supervision and borrowed-solver wiring for bounded error diagnostics."""
from pathlib import Path

from .workflow_timebase import checked_interval,clock_sample


def supervise_diagnosis(command, directory, *, phase_path, expected_sha, kind,
                        remaining_seconds, cache_path=None):
    """Use the same outer guard for diagnostics and the optional run_case direct.

    Caller supplies the already-reviewed command and shared remaining budget;
    this function never chooses another solver or starts a retry.
    """
    from benchmarks.subreaper_watchdog import supervise
    from .task038_launcher import _physical_source_gate
    if kind not in ('diagnosis','reference'):
        raise ValueError('unknown diagnostic workflow kind')
    limit = min(remaining_seconds,3600 if kind=='reference' else 7200)
    state = _physical_source_gate(Path.cwd(),expected_sha)
    result = supervise(command,Path(directory),wall_seconds=limit,phase_path=Path(phase_path),
                       source_state=state,interval=.25,grace_seconds=2,
                       hard_stop_immediate=True,timebase_guard=True,cache_path=cache_path,
                       worker_environment={} if cache_path is None else {'XDG_CACHE_HOME':str(cache_path)})
    result['source_after'] = _physical_source_gate(Path.cwd(),expected_sha)
    return result


class DiagnosticActions:
    """Borrow one existing S6/A6/P64/p4 stack; add unchanged LIGHT plus metrics.

    The caller builds/qualifies and eventually destroys that single stack.
    This object owns only its extra H6, metric actions and vector bridges.
    """

    def __init__(self,bundle,cfg,marker):
        from src.solvers.physical_error_metric import LosslessFEMetric,SerialAction
        from src.solvers.physical_light_setup import build_light_h6_setup
        from src.solvers.fullspace_physical_intermediate import PhysicalIntermediatePreconditioner
        self.bridges,self.metrics,self.light = [],{},None
        self.timings=[]
        self.projection_seconds=0.
        self.projection_diagonal=None
        levels,fine = bundle['levels'],bundle['fine']
        transfer,reference = bundle['actions']['transfers'][(6,4)],bundle['reference_factor']
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
                interval=checked_interval(start,clock_sample())
                self.timings.append(dict(name=name,**interval))
                marker(name+'_complete',interval)
                return result
            return apply
        try:
            self.A = bridge(fine['physical_action'].apply)
            self.components={k:bridge(v.apply,result='borrowed') for k,v in
                             fine['volume_action'].component_actions.items()}
            self.components['dtn']=bridge(fine['dtn_action'].apply)
            self.P=bridge(transfer.apply_primal,4,6,'owned')
            self.PH=bridge(transfer.apply_adjoint,6,4,'owned')
            def solve(rhs):
                return reference.solve_intermediate(rhs)['final_solution']
            self.solve=timed('diagnostic_p4',bridge(solve,4,4,'owned'))
            for degree in (6,4):
                marker('lossless_metric_started',dict(degree=degree))
                self.metrics[degree]=LosslessFEMetric(levels,degree,cfg.k0,bundle['actions']['volume_quadrature_metadata'])
                marker('lossless_metric_complete',self.metrics[degree].audit)
            self.M0=self.metrics[6].mass
            self.light=build_light_h6_setup(levels,cfg,marker)
            h6=self.light['h6']
            light=PhysicalIntermediatePreconditioner(fine['physical_action'],h6,transfer,reference,
                        positive_identity='H6',outer_max_it=2048,stage_callback=marker)
            joint=PhysicalIntermediatePreconditioner(fine['physical_action'],h6,transfer,reference,
                        positive_identity='H6',outer_max_it=2048,joint_mr=True,stage_callback=marker)
            self.profiles={name:timed(name,bridge(pc.apply,result='owned')) for name,pc in
                           [('S6',bundle['pc']),('LIGHT',light),('JOINT',joint)]}
            self.smoothers={name:timed(name,bridge(pc.apply,result='owned')) for name,pc in
                            [('H6',h6),('S6_complement',bundle['positive']['upper_cycle'])]}
        except BaseException:
            self.destroy()
            raise

    def project(self,e):
        """Share the 1800s projection allowance, including diagonal setup."""
        from src.solvers.physical_error_diagnostics import project_error
        class ProjectionLimit(RuntimeError):
            pass
        start=clock_sample()
        def check():
            if self.projection_seconds+checked_interval(start,clock_sample())['budget_seconds']>=1800:
                raise ProjectionLimit('cumulative projection budget exhausted')
        try:
            check()
            if self.projection_diagonal is None:
                self.projection_diagonal=self.metrics[4].diagonal(checkpoint=check)
            return project_error(self.P,self.PH,self.M0,self.projection_diagonal,e,checkpoint=check)
        except ProjectionLimit as exc:
            return dict(status='PROJECTION_UNRESOLVED',reason=str(exc),parallel=None,perpendicular=None)
        finally:
            self.projection_seconds+=checked_interval(start,clock_sample())['budget_seconds']

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
    args=parser.parse_args()
    _physical_source_gate(Path.cwd(),args.expected_sha)
    if args.worker:
        from .physical_diagnosis_worker import run_diagnosis
        run_diagnosis(args.input,args.inventory,args.directory,args.expected_sha)
        return 0
    args.directory.mkdir(parents=True,exist_ok=False)
    start=clock_sample()
    def cache_inventory():
        return [] if args.cache_path is None else [dict(path=str(p),bytes=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(args.cache_path.rglob('*')) if p.is_file()]
    manifest=dict(source_sha=args.expected_sha,clock_start=start,
        input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
        inventory_sha256=hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        cache_before=cache_inventory(),kind='no-reference D1/D3',
        complete_pc_limit=15,independent_smoother_limit=4,projection_seconds=1800,
        reference='not_run_capacity_unqualified')
    _atomic_json(args.directory/'launch.json',manifest)
    command=['mpiexec','-n','1',sys.executable,'-m','src.runners.physical_diagnosis',
        '--worker','--directory',str(args.directory),'--input',str(args.input),
        '--inventory',str(args.inventory),'--expected-sha',args.expected_sha,
        '--remaining-seconds',str(args.remaining_seconds)]
    result=supervise_diagnosis(command,args.directory/'watchdog',phase_path=args.directory/'phase.json',
        expected_sha=args.expected_sha,kind='diagnosis',
        remaining_seconds=min(7200,args.remaining_seconds)-checked_interval(start,clock_sample())['budget_seconds'],
        cache_path=args.cache_path)
    manifest.update(supervision=result,cache_after=cache_inventory(),clock_end=clock_sample())
    manifest['interval']=checked_interval(start,manifest['clock_end'])
    if manifest['interval']['budget_seconds']>min(7200,args.remaining_seconds):
        manifest['workflow_limit_exceeded']=True
        result['classification']='PERFORMANCE_CONTROLLED_STOP'
    _atomic_json(args.directory/'launch.json',manifest)
    print(json.dumps(dict(classification=result['classification'],directory=str(args.directory))))
    return 0 if result['classification']=='COMPLETED' else 2


if __name__=='__main__':
    raise SystemExit(main())
