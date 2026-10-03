"""V31 thin pre-test driver; no production action or factor payload reads."""
import json,os,subprocess,sys,time
from pathlib import Path
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json

SCOPE=('src/test/test_task042_v31_workflow.py','src/test/test_task042_v28_cached_checker.py',
       'src/test/test_task042_v29_checker.py','src/test/test_task042_v30_entry.py',
       'src/test/test_task042_v27_return_direction.py')


def main():
    from src.runners.actual_loss_block_descent import _pure_blas_threads
    import numpy as np,scipy
    if os.environ.get('TASK042_ACTIVATION')!='1' or os.environ.get('TASK042_ENV_MODE')!='pure':
        raise RuntimeError('qualified Task042 pure activation required')
    folder=ROOT/'tmp/task042/v31/tests';folder.mkdir(parents=True,exist_ok=True)
    getters=_pure_blas_threads()
    environment=dict(python=sys.executable,numpy=np.__version__,scipy=scipy.__version__,BLAS=getters,
        affinity=sorted(os.sched_getaffinity(0)),MPI=1,math_threads=1,DataLoader0=True,
        torch_imported='torch' in sys.modules,FE_imported='dolfinx' in sys.modules,
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        command=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',*SCOPE,
            '--basetemp='+str(folder/'fixtures'),'--junitxml='+str(folder/'junit.xml')])
    write_json(folder/'environment.json',environment)
    began=time.perf_counter()
    with (folder/'stdout.txt').open('w') as out,(folder/'stderr.txt').open('w') as err:
        result=subprocess.run(environment['command'],stdout=out,stderr=err,check=False)
    write_json(folder/'entry_result.json',dict(exit_code=result.returncode,elapsed_seconds=time.perf_counter()-began,
        environment=environment,status='PASSED' if result.returncode==0 else 'FAILED'))
    print((folder/'stdout.txt').read_text());print((folder/'stderr.txt').read_text(),file=sys.stderr)
    return result.returncode

if __name__=='__main__':sys.exit(main())
