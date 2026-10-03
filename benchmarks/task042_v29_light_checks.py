"""One prepared V29 command: pure qualification, focused tests, cached records."""
import compileall,json,os,subprocess,sys,time,ctypes
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import scipy
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from benchmarks.task042_full_block_algebra import run as algebra
from benchmarks.task042_v29_cached_analysis import cpu_reasons,cost_ledger

OUTPUT=ROOT/'docs/task042_neural_coarse_inverse/outcomes/records'
SCOPE=[
 'src/test/test_task042_v29_checker.py','src/test/test_task042_v29_algebra.py',
 'src/test/test_task042_v28_cached_checker.py','src/test/test_task042_v27_return_direction.py',
 'src/test/test_task042_v26_joint_direction.py','src/test/test_task042_v25_block_direction.py',
 'src/test/test_task042_v26_inventory.py','src/test/test_24_repository_work_principles.py',
 'src/test/test_183_development_model_registry_markdown.py']


def main():
    start=time.monotonic();source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert os.environ['TASK042_ENV_MODE']=='pure' and os.environ['TASK042_ACTIVATION']=='1'
    assert Path(sys.prefix)==ROOT/'.venv' and Path.cwd()==ROOT and len(os.sched_getaffinity(0))==1
    threads=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS','OMP_THREAD_LIMIT')
    assert all(os.environ[k]=='1' for k in threads) and os.environ['CUDA_VISIBLE_DEVICES']==''
    pools=[]
    for path in sorted({x.split()[-1] for x in Path('/proc/self/maps').read_text().splitlines() if 'openblas' in x and x.split()[-1].startswith('/')}):
        lib=ctypes.CDLL(path)
        for name in ('openblas_get_num_threads','openblas_get_num_threads64_','scipy_openblas_get_num_threads','scipy_openblas_get_num_threads64_'):
            if hasattr(lib,name):
                getter=getattr(lib,name);getter.restype=ctypes.c_int;assert getter()==1
                pools.append(dict(path=path,function=name,threads=1));break
    assert pools and not any(x in sys.modules for x in ('torch','dolfinx','petsc4py','mpi4py','ffcx'))
    write_json(OUTPUT/'environment_v29.json',dict(source_sha=source,python=sys.executable,numpy=np.__version__,scipy=scipy.__version__,
        affinity=sorted(os.sched_getaffinity(0)),MPI=1,math_threads=1,actual_BLAS=pools,DataLoader_workers=0,
        FE_JIT=False,Torch_loaded=False,GPU_used=False,bytecode_disabled=sys.dont_write_bytecode,
        caches={k:os.environ[k] for k in ('TMPDIR','PYTHONPYCACHEPREFIX','XDG_CACHE_HOME')},shared_workstation=True))
    # Independent records remain useful even if a later regression fails.
    cpu_reasons(OUTPUT);cost_ledger(OUTPUT)
    began=time.monotonic();result=algebra();result.update(source_sha=source,elapsed_seconds=time.monotonic()-began)
    write_json(OUTPUT/'full_space_algebra_v29.json',result)
    command=[sys.executable,'-m','pytest','-q','--basetemp',str(ROOT/'tmp/task042/v29/pytest'),*SCOPE]
    began=time.monotonic();proc=subprocess.run(command,check=False);elapsed=time.monotonic()-began
    paths=['benchmarks/collect_task042_return_direction.py','benchmarks/task042_return_certificates.py',
        'benchmarks/task042_full_block_algebra.py','benchmarks/task042_v29_cached_analysis.py','benchmarks/task042_v29_light_checks.py',
        'benchmarks/task042_diagnostic_auxiliary.py','src/runners/return_block_diagnostic.py','src/solvers/return_block_study.py',
        'src/solvers/return_block_direction.py','src/test/task042_return_fixture.py','src/test/test_task042_v29_checker.py']
    compile_ok=all(compileall.compile_file(str(ROOT/p),quiet=1) for p in paths)
    write_json(OUTPUT/'tests_v29.json',dict(status='PASSED' if proc.returncode==0 and compile_ok else 'FAILED',source_sha=source,
        command=command,returncode=proc.returncode,wall_seconds=elapsed,compileall=compile_ok,scope=SCOPE,
        auxiliary_inner_wall_seconds=time.monotonic()-start,CI='NOT_RUN',full_repository='NOT_RUN',FE_MPI='NOT_RUN',
        utc=datetime.now(timezone.utc).isoformat()))
    return 0 if proc.returncode==0 and compile_ok else 1


if __name__=='__main__':sys.exit(main())
