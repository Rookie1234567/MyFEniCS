"""V31 thin pre-test driver; no production action or factor payload reads."""
import json,os,subprocess,sys,time
from pathlib import Path
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json

SCOPE=('src/test/test_task042_v31_workflow.py','src/test/test_task042_v28_cached_checker.py',
       'src/test/test_task042_v29_checker.py','src/test/test_task042_v30_entry.py',
       'src/test/test_task042_v27_return_direction.py')


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--batch',choices=('v31','v32','v33','v34'),default='v31')
    parser.add_argument('tests',nargs='*')
    args=parser.parse_args()
    from src.runners.actual_loss_block_descent import _pure_blas_threads
    import numpy as np,scipy
    if os.environ.get('TASK042_ACTIVATION')!='1' or os.environ.get('TASK042_ENV_MODE')!='pure':
        raise RuntimeError('qualified Task042 pure activation required')
    folder=(Path(os.environ['TASK042_'+args.batch.upper()+'_AUX_DIRECTORY'])/'tests' if args.batch in ('v32','v33','v34')
            else ROOT/'tmp/task042/v31/tests')
    folder.mkdir(parents=True,exist_ok=True)
    v34_scope=('src/test/test_task042_v34_workflow.py','src/test/test_task042_v33_workflow.py',
        'src/test/test_task042_v32_workflow.py::test_storage_scope_and_boundary',
        'src/test/test_task042_v32_workflow.py::test_v32_actual_workflow_through_independent_checker',
        'src/test/test_task042_v31_workflow.py::test_failed_prequalification_stops_formal_route')
    scope=tuple(args.tests) if args.tests else v34_scope if args.batch=='v34' else (('src/test/test_task042_v33_workflow.py',
        'src/test/test_task042_v32_workflow.py::test_storage_scope_and_boundary',
        'src/test/test_task042_v32_workflow.py::test_v32_actual_workflow_through_independent_checker',
        'src/test/test_task042_v31_workflow.py::test_failed_prequalification_stops_formal_route') if args.batch=='v33' else (('src/test/test_task042_v32_workflow.py',
        'src/test/test_task042_v31_workflow.py::test_failed_prequalification_stops_formal_route',
        'src/test/test_task042_v31_workflow.py::test_actual_study_two_states_through_collector',
        'src/test/test_task042_v31_workflow.py::test_actual_workflow_reader_failure_preserves_partial_accounting')
        if args.batch=='v32' else SCOPE))
    if args.batch in ('v33','v34'):
        if args.batch=='v34':from src.solvers import full_input_block_v34_window as qualified_window
        else:from src.solvers import full_input_block_v33_window as qualified_window
        compiled=[]
        for rel in qualified_window.QUALIFICATION_FILES:
            if rel.endswith('.py'):
                compile((ROOT/rel).read_text(),rel,'exec');compiled.append(rel)
        write_json(folder/'compilation.json',dict(files=compiled,status='COMPILED_IN_MEMORY'))
    getters=_pure_blas_threads()
    environment=dict(python=sys.executable,numpy=np.__version__,scipy=scipy.__version__,BLAS=getters,
        affinity=sorted(os.sched_getaffinity(0)),MPI=1,math_threads=1,DataLoader0=True,
        torch_imported='torch' in sys.modules,FE_imported='dolfinx' in sys.modules,
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        command=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',*scope,
            '--basetemp='+str(folder/'fixtures'),'--junitxml='+str(folder/'junit.xml')])
    write_json(folder/'environment.json',environment)
    began=time.perf_counter()
    with (folder/'stdout.txt').open('w') as out,(folder/'stderr.txt').open('w') as err:
        result=subprocess.run(environment['command'],stdout=out,stderr=err,check=False)
    write_json(folder/'entry_result.json',dict(exit_code=result.returncode,elapsed_seconds=time.perf_counter()-began,
        environment=environment,status='PASSED' if result.returncode==0 else 'FAILED'))
    if args.batch in ('v32','v33','v34') and result.returncode==0:
        if args.batch=='v34':
            from src.solvers import full_input_block_v34_window as w
        elif args.batch=='v33':
            from src.solvers import full_input_block_v33_window as w
        else:
            from src.solvers import return_block_v32_window as w
        from src.solvers.neural_fe_action_packet import file_hash
        # Only the complete focused scope confers formal qualification. Targeted
        # repair replays remain evidence; they cannot pretend to cover omitted gates.
        required=('src/test/test_task042_'+args.batch+'_workflow.py',
                  'src/test/test_task042_v31_workflow.py::test_failed_prequalification_stops_formal_route')
        if all(p in scope for p in required) and (args.batch!='v34' or all(p in scope for p in v34_scope)):
            write_json(folder/'qualification.json',dict(status='PASSED',source_sha=environment['source_sha'],
                implementation_hashes=w.implementation_hashes(),coverage=list(w.REQUIRED_COVERAGE),
                scope=list(scope),test_receipt=dict(path=str(folder/'entry_result.json'),sha256=file_hash(folder/'entry_result.json')),
                previous_failures=[str(p) for p in w.TMP.glob('aux_pre_*/summary.json')
                                   if json.loads(p.read_text())['leader_exit_code']!=0]))
    print((folder/'stdout.txt').read_text());print((folder/'stderr.txt').read_text(),file=sys.stderr)
    return result.returncode

if __name__=='__main__':sys.exit(main())
