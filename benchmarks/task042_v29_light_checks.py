"""One bounded pure auxiliary entry; v30 is an explicit namespace opt-in."""
import argparse,json,os,subprocess,sys,time,ctypes,traceback
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import scipy
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import file_hash
from benchmarks.task042_full_block_algebra import run as algebra
from benchmarks.task042_v29_cached_analysis import cpu_reasons,cost_ledger,checked_batch

OUTPUT=ROOT/'docs/task042_neural_coarse_inverse/outcomes/records'
SCOPE=[
 'src/test/test_task042_v29_checker.py','src/test/test_task042_v29_algebra.py',
 'src/test/test_task042_v28_cached_checker.py','src/test/test_task042_v27_return_direction.py',
 'src/test/test_task042_v26_joint_direction.py','src/test/test_task042_v25_block_direction.py',
 'src/test/test_task042_v26_inventory.py','src/test/test_24_repository_work_principles.py',
 'src/test/test_183_development_model_registry_markdown.py']
NEW_SCOPE='src/test/test_task042_v30_entry.py'
COMPILE_PATHS=[
 'benchmarks/collect_task042_return_direction.py','benchmarks/collect_task042_block_direction.py',
 'benchmarks/task042_return_certificates.py','benchmarks/task042_full_block_algebra.py',
 'benchmarks/task042_v29_cached_analysis.py','benchmarks/task042_v29_light_checks.py',
 'benchmarks/task042_diagnostic_auxiliary.py','benchmarks/task042_admission_receipt.py',
 'src/runners/return_block_diagnostic.py','src/solvers/return_block_study.py',
 'src/solvers/return_block_direction.py','src/test/task042_return_fixture.py',
 *SCOPE,NEW_SCOPE]
REAL_COUNTS=dict.fromkeys(('actor','S','SH','factor_readers','local_solve','LU','gecon',
                          'QR_SVD','FE','iterations','training'),0)


def layout(batch):
    batch=checked_batch(batch)
    return OUTPUT,ROOT/'tmp/task042'/batch


def compiled_sources():
    records=[]
    for name in dict.fromkeys(COMPILE_PATHS):
        path=ROOT/name
        compile(path.read_text(),str(path),'exec')
        records.append(dict(path=str(path),sha256=file_hash(path),status='COMPILED_IN_MEMORY'))
    return records


def pytest_run(scratch,name,scope):
    folder=scratch/name;folder.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-m','pytest','-q','--tb=short','-p','no:cacheprovider',
             '--basetemp',str(folder/'pytest'),'--junitxml',str(folder/'junit.xml'),*scope]
    began=time.monotonic()
    proc=subprocess.run(command,capture_output=True,text=True,check=False)
    (folder/'stdout.log').write_text(proc.stdout);(folder/'stderr.log').write_text(proc.stderr)
    print(name,proc.stdout,proc.stderr,flush=True)
    result=dict(command=command,returncode=proc.returncode,wall_seconds=time.monotonic()-began,
                stdout=dict(path=str(folder/'stdout.log'),sha256=file_hash(folder/'stdout.log')),
                stderr=dict(path=str(folder/'stderr.log'),sha256=file_hash(folder/'stderr.log')),
                scope=scope,role='synthetic/cached-metadata tests; no real numeric payloads')
    write_json(folder/'result.json',result)
    return result


def execute(batch,output,scratch,source):
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
    write_json(output/f'environment_{batch}.json',dict(source_sha=source,python=sys.executable,numpy=np.__version__,scipy=scipy.__version__,
        affinity=sorted(os.sched_getaffinity(0)),MPI=1,math_threads=1,actual_BLAS=pools,DataLoader_workers=0,
        FE_JIT=False,Torch_loaded=False,GPU_used=False,bytecode_disabled=sys.dont_write_bytecode,
        caches={k:os.environ[k] for k in ('TMPDIR','PYTHONPYCACHEPREFIX','XDG_CACHE_HOME')},shared_workstation=True))
    compiles=compiled_sources();minimal=None
    if batch=='v30':
        minimal=pytest_run(scratch,'minimal',[NEW_SCOPE])
        write_json(output/'minimal_tests_v30.json',dict(source_sha=source,**minimal))
        if minimal['returncode']:return dict(status='FAILED_MINIMAL_REGRESSION',minimal=minimal,compilation=compiles),1
    # Use the complete cached analysis module, not an extracted AST function.
    cpu_reasons(output,batch=batch);cost_ledger(output,batch=batch)
    began=time.monotonic();result=algebra()
    result.update(source_sha=source,elapsed_seconds=time.monotonic()-began,role='fixed small-matrix algebra only')
    write_json(output/f'full_space_algebra_{batch}.json',result)
    scope=SCOPE+([NEW_SCOPE] if batch=='v30' else [])
    tests=pytest_run(scratch,'full_scope',scope)
    result=dict(status='PASSED' if tests['returncode']==0 else 'FAILED',source_sha=source,
                minimal=minimal,compilation=compiles,**tests,CI='NOT_RUN',full_repository='NOT_RUN',FE_MPI='NOT_RUN',
                real_counts=REAL_COUNTS,synthetic_consumption_is_not_real=True)
    write_json(output/f'tests_{batch}.json',result)
    return result,0 if tests['returncode']==0 else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--batch',choices=('v29','v30'),default='v29')
    batch=parser.parse_args().batch;output,scratch=layout(batch)
    output.mkdir(parents=True,exist_ok=True);scratch.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    try:
        result,code=execute(batch,output,scratch,source)
    except Exception as error:
        result=dict(status='FAILED_NEW_RUNTIME_ERROR',error=repr(error),traceback=traceback.format_exc());code=1
        print(result['traceback'],file=sys.stderr,flush=True)
    write_json(output/f'entry_result_{batch}.json',dict(batch=batch,source_sha=source,exit_code=code,
        status=result['status'],inner_wall_seconds=time.monotonic()-start,utc=datetime.now(timezone.utc).isoformat(),
        real_counts=REAL_COUNTS,synthetic_and_cached_only=True,detail=result))
    return code


if __name__=='__main__':sys.exit(main())
