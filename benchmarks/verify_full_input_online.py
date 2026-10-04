"""One paid cache-only final checker/analysis; never rebuild or solve a PDE."""
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from benchmarks.check_full_input_online import main as check_main
from src.io.full_input_online import read_result
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers import full_input_online_window as window
from src.solvers.neural_fe_action_packet import array_hash,file_hash


def saved_residual_analysis():
    r,_=read_result('ONLINE');state=r['final']['state']
    with np.load(state['path'],allow_pickle=False) as data:
        residual=np.array(data['residual'])
    if array_hash(residual)!=state['residual_sha256']:
        raise ValueError('saved final residual member mismatch')
    mapping=r['map_check']['map'];mp=Path(mapping['path'])
    if file_hash(mp)!=mapping['sha256']:
        raise ValueError('saved residual geometry map container')
    with np.load(mp,allow_pickle=False) as data:
        groups=np.array(data['patch_id'])
    if array_hash(groups)!=mapping['patch_id_sha256']:
        raise ValueError('saved residual geometry map member')
    rn=float(np.linalg.norm(residual));rows=[]
    for b in range(8):
        norm=float(np.linalg.norm(residual[:18144][groups==b]))
        rows.append(dict(block=b,rows=int(np.sum(groups==b)),residual_norm=norm,
            squared_fraction_of_full_residual=norm**2/rn**2))
    j=float(np.linalg.norm(residual[:18144][(groups==5)|(groups==7)]))
    outer=float(np.linalg.norm(residual[:18144][(groups!=5)&(groups!=7)]))
    port=float(np.linalg.norm(residual[18144:]))
    partition_error=abs(sum(x['residual_norm']**2 for x in rows)+port**2-rn**2)/rn**2
    if partition_error>1e-12:
        raise ValueError('saved residual partition identity')
    result=dict(status='SAVED_RESIDUAL_ANALYSIS',regions=rows,J_norm=j,O_norm=outer,
        port_norm=port,total_norm=rn,partition_squared_relative_error=partition_error,
        J_squared_fraction=j*j/(rn*rn),O_squared_fraction=outer*outer/(rn*rn),
        scope='canonical residual coefficients, not material energy or physical field integrals',
        no_new_actions=True,no_factor_or_reference_read=True,
        original_Schur=r['final']['audit']['schur_relative'],
        cold_initial_Schur=r['initial_schur_relative'],
        residual_reduction_fraction=1-r['final']['audit']['schur_relative']/r['initial_schur_relative'],
        solver_cycle_inclusive_seconds=r['final']['cycle_inclusive_wall_seconds'],
        original_and_fast_actions=r['actual_equivalent_actions'])
    write_json(Path(state['path']).parents[3]/'saved_residual_analysis.json',result)
    return result


def main():
    from src.runners.actual_loss_block_descent import _pure_blas_threads
    folder=Path(os.environ['TASK042_V35_AUX_DIRECTORY']);window.guard_worker_parent()
    targets=['src/test/test_task042_v35_online.py','src/test/test_task042_v35_cache.py']
    for filename in [*window.implementation_hashes(),'benchmarks/verify_full_input_online.py',*targets]:
        if filename.endswith('.py'):compile((ROOT/filename).read_bytes(),filename,'exec')
    command=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        '--basetemp='+str(folder/'fixtures'),*targets,'--junitxml='+str(folder/'pytest.xml')]
    with (folder/'pytest.stdout').open('w') as out,(folder/'pytest.stderr').open('w') as err:
        test=subprocess.run(command,stdout=out,stderr=err)
    if test.returncode:
        raise RuntimeError('V35 final-source checker tests failed; retain raw evidence')
    check_main();analysis=saved_residual_analysis()
    write_json(folder/'final_cache_check.json',dict(status='CHECKED',command=command,
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        numerical_source=read_result('ONLINE')[0]['source_sha'],
        tests=dict(returncode=0,stdout_sha256=file_hash(folder/'pytest.stdout')),
        threads=_pure_blas_threads(),affinity=sorted(os.sched_getaffinity(0)),
        new_actions=0,new_factor_reads=0,new_LU=0,no_reference_read=True,analysis=analysis))
    return 0


if __name__=='__main__':
    sys.exit(main())
