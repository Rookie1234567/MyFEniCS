"""Thin V15 adapter: existing stage supervision, isolated random initialization."""

import json
import sys
import traceback
from pathlib import Path

import numpy as np

from src.io import local_trace_representation as io
from src.runners.orthonormal_trace_reprofile import Stage,atomic_arrays
from src.runners.task042_shared import write_json
from src.solvers import local_trace_window as window
from src.solvers.local_trace_head import FAMILY,LIMITS


def hidden_child(work):
    from src.solvers.neural_trace_torch import NeuralTrace,qualify_threads
    from src.solvers.local_trace_features import numpy_hidden_features
    import torch
    window.guard_worker_parent('TASK042_NUMERICAL_PARENT_PID')
    request=json.loads((work/'hidden_request.json').read_text())
    threads=qualify_threads()
    model=NeuralTrace(request['bounds'],request['wavelength_nm'],seed=request['seed'])
    weights={}
    for j,index in enumerate((0,2,4)):
        weights['w'+str(j)]=model.envelopes[index].weight.detach().numpy().copy()
        weights['b'+str(j)]=model.envelopes[index].bias.detach().numpy().copy()
    rng=np.random.default_rng(421504);xi=rng.uniform(-2,2,(97,3))
    with torch.no_grad():
        features=model.envelopes[:-1](torch.as_tensor(xi,dtype=torch.float64)).numpy()
    actual=numpy_hidden_features(xi,weights)[:,1:]
    error=float(np.linalg.norm(features-actual)/np.linalg.norm(features))
    if error>1e-12:raise ValueError('isolated NumPy/Torch fixed hidden forward differs')
    record=atomic_arrays(work/'random_hidden_weights.npz',**weights)
    write_json(work/'hidden_initialization.json',dict(weights=record,seed=420906,hidden_real_parameters=8576,
        hidden_trainable=False,NN7_or_reference_read=False,numpy_Torch_forward_relative=error,
        source_sha=request['source_sha'],threads=threads))


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--hidden-child':
        hidden_child(Path(sys.argv[2]));return
    window.guard_worker_parent()
    specification=io.load_local_trace(sys.argv[1]);directory=Path(sys.argv[2]).resolve()
    stage=Stage(specification,directory,io_module=io,window_module=window,
                limits=LIMITS,action_limit=12000,family=FAMILY)
    result={}
    try:
        from src.solvers.local_trace_study import setup,local_solve,union_solve,verify
        if stage.own_plan['resident_upper_bytes']>8*2**30:
            raise MemoryError('V15 resident plan exceeds 8GiB')
        if stage.name=='SETUP':result=setup(stage)
        elif stage.name.startswith('LOCAL_'):result=local_solve(stage,stage.name.split('_')[1])
        elif stage.name.startswith('UNION_'):result=union_solve(stage,stage.name.split('_')[1])
        elif stage.name=='VERIFY':result=verify(stage)
        else:raise ValueError('unknown one-run stage')
        if specification.derived['environment_mode']=='pure':
            from src.runners.actual_loss_block_descent import _pure_blas_threads
            result['threads']=_pure_blas_threads()
    except Exception as error:
        result.update(status='FAILED',error=type(error).__name__+': '+str(error),queue_frozen=True)
        traceback.print_exc();raise
    finally:
        bytes_owned=sum(p.stat().st_size for p in io.ARTIFACT_ROOT.rglob('*') if p.is_file())
        result['new_batch_artifact_bytes']=bytes_owned
        result['artifact_budget_qualified']=bytes_owned<=3*2**30
        stage.finish(result)


if __name__=='__main__':main()
