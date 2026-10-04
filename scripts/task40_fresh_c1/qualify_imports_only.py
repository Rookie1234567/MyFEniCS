"""Fresh installed runtime import/scalar/MPI/API witness; no FE/PDE/factor."""
import argparse, hashlib, importlib, json, os, pathlib, platform, sys, time, traceback
parser=argparse.ArgumentParser();parser.add_argument('--record',required=True);args=parser.parse_args()
r={'schema':'fresh-runtime-imports-only.v1','status':'PARTIAL','started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'python':sys.version,'executable':sys.executable,'prefix':sys.prefix,'platform':platform.platform(),'modules':{},'FE_action':'NOT_RUN','C1':'NOT_RUN','matrix_creation_calls':0,'factor_calls':0,'PDE_calls':0,'old_ABI_inherited':False,'process_local_UCX_TLS':os.environ.get('UCX_TLS'),'threads':{k:os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']}}
def save():
 pathlib.Path(args.record).write_text(json.dumps(r,indent=2,default=str)+'\n')
try:
 for name in ['numpy','scipy','mpi4py','petsc4py','basix','ufl','ffcx','dolfinx','dolfinx_mpc','pytest','psutil']:
  m=importlib.import_module(name);r['modules'][name]={'version':getattr(m,'__version__',None),'file':getattr(m,'__file__',None)};save()
 import numpy as np
 from mpi4py import MPI
 from petsc4py import PETSc
 import dolfinx
 import basix
 from importlib.metadata import version
 r['MPI']={'library_version':MPI.Get_library_version(),'size':MPI.COMM_WORLD.size,'rank':MPI.COMM_WORLD.rank,'extension_file':MPI.__file__}
 r['PETSc']={'version':PETSc.Sys.getVersion(),'version_info':PETSc.Sys.getVersionInfo(),'scalar_dtype':np.dtype(PETSc.ScalarType).name,'int_dtype':np.dtype(PETSc.IntType).name,'mumps_enabled':PETSc.Sys.hasExternalPackage('mumps'),'public_PC_methods':{k:hasattr(PETSc.PC,k) for k in ['setType','setOperators','setFactorSolverType','setFactorSetUpSolverType','getFactorMatrix','setUp']},'public_Mat_methods':{k:hasattr(PETSc.Mat,k) for k in ['solve','setMumpsIcntl','getMumpsIcntl','getMumpsInfo','getMumpsInfog']}}
 r['dolfinx_default_scalar_dtype']=np.dtype(dolfinx.default_scalar_type).name
 r['MPC_package_version']=version('dolfinx_mpc')
 maps=pathlib.Path('/proc/self/maps').read_text().splitlines()
 r['loaded_numerical_libraries']=sorted(set(line.split()[-1] for line in maps if '/' in line and any(k in line for k in ['libmpi','libpetsc','mumps','dolfinx','basix','openblas','libstdc++'])))
 r['source_sha256']=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
 assert sys.version_info[:2]==(3,12)
 assert np.dtype(PETSc.ScalarType)==np.dtype(np.complex128)
 assert np.dtype(dolfinx.default_scalar_type)==np.dtype(np.complex128)
 assert np.dtype(PETSc.IntType)==np.dtype(np.int32)
 assert PETSc.Sys.getVersion()==(3,25,6)
 assert dolfinx.__version__=='0.10.0' and basix.__version__=='0.10.0'
 assert r['MPC_package_version']=='0.10.5'
 assert MPI.COMM_WORLD.size==1 and MPI.COMM_WORLD.rank==0
 assert 'MPICH' in MPI.Get_library_version() and '5.0.1' in MPI.Get_library_version()
 assert r['process_local_UCX_TLS']=='self'
 assert all(r['PETSc']['public_PC_methods'].values())
 assert all(r['PETSc']['public_Mat_methods'].values())
 assert r['PETSc']['mumps_enabled']
 assert all(v=='1' for v in r['threads'].values())
 prefix=pathlib.Path(sys.prefix).resolve()
 numerical=[pathlib.Path(p).resolve() for p in r['loaded_numerical_libraries'] if any(k in p for k in ['libmpi','libpetsc','mumps','dolfinx','basix','openblas'])]
 offenders=[str(p) for p in numerical if not p.is_relative_to(prefix)]
 r['external_numerical_library_paths']=offenders
 r['old_ABI_inherited']=bool(offenders or os.environ.get('PYTHONPATH') or os.environ.get('PYTHONHOME') or os.environ.get('LD_PRELOAD') or os.environ.get('LD_LIBRARY_PATH'))
 assert r['old_ABI_inherited'] is False
 r['status']='IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION';r['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());save()
 print(json.dumps({k:r[k] for k in ['status','executable','MPI','PETSc','C1']},default=str))
except BaseException:
 r['status']='FAILED_IMPORT_SCALAR_MPI_API';r['traceback']=traceback.format_exc();save();raise
