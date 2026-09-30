"""V17 recovery proof: recurrence, independent reader, interrupted commit."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType

import numpy as np
import pytest
from src.solvers.resumable_trace_gmres import correction_cycle

from src.solvers.bounded_complex_lsqr import LSQRState,lsqr_steps
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint
from src.test.test_task042_v16_augmented import problem


@pytest.mark.parametrize('nonempty',[False,True])
def test_80_vs_32_independent_reader_48(tmp_path,nonempty):
    op,_,rhs=problem(nonempty);f=op.rhs(rhs)
    # Original projected matrices, including structural nullspace; independent
    # reader acts on exactly these fixed inputs, not a rebuilt/random operator.
    eye=np.eye(len(f),dtype=complex)
    A=np.column_stack([op.apply(eye[:,j]) for j in range(len(f))])
    apply=lambda x:A@x
    adjoint=lambda x:A.conj().T@x
    whole=LSQRState.initialize(adjoint,f)
    partial=LSQRState.initialize(adjoint,f)
    for _ in range(80):whole.step(apply,adjoint)
    for _ in range(32):partial.step(apply,adjoint)
    identity=dict(rhs='r',Q='nonempty' if nonempty else 'empty',algorithm=LSQRState.version)
    store=RollingCheckpoint(tmp_path/'slots',identity)
    store.save({'GK_'+k:np.asarray(v) for k,v in partial.export().items()},dict(actions_lower=65,actions_upper=129))
    np.savez(tmp_path/'problem.npz',A=A,f=f)
    code='''import json,numpy as np,sys
from pathlib import Path
from src.solvers.bounded_complex_lsqr import LSQRState
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint
p=Path(sys.argv[1]);_,a,_=RollingCheckpoint(p/'slots',json.loads(sys.argv[2])).read()
s=LSQRState.restore({k[3:]:v for k,v in a.items()});A=np.load(p/'problem.npz')['A']
for _ in range(48):s.step(lambda x:A@x,lambda x:A.conj().T@x)
np.savez(p/'restored.npz',**s.export())
'''
    subprocess.run([sys.executable,'-c',code,str(tmp_path),json.dumps(identity)],check=True)
    with np.load(tmp_path/'restored.npz') as resumed:
        for k,v in whole.export().items():np.testing.assert_array_equal(resumed[k],v)
        y=resumed['x']
    z=op.restore(y,rhs)['z'];z_whole=op.restore(whole.values['x'],rhs)['z']
    np.testing.assert_allclose(z,z_whole,atol=1e-12,rtol=1e-12)
    assert np.linalg.norm(op.bar.packet.apply(z)-op.bar.packet.apply(z_whole))<=1e-12*max(np.linalg.norm(rhs),1)


@pytest.mark.parametrize('where',['arrays_partial','arrays','manifest'])
def test_kill_half_write_preserves_prior_generation(tmp_path,where):
    store=RollingCheckpoint(tmp_path,dict(rhs='r',Q='q'))
    store.save(dict(x=np.ones(5,complex)),dict(iteration=16))
    code='''import os,signal,sys,numpy as np
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint
RollingCheckpoint(sys.argv[1],dict(rhs='r',Q='q')).save(dict(x=np.ones(5,complex)*2),dict(iteration=32),interrupt_after=sys.argv[2])
os.kill(os.getpid(),signal.SIGKILL)
'''
    p=subprocess.run([sys.executable,'-c',code,str(tmp_path),where])
    assert p.returncode==-9
    m,a,_=store.read();assert m['metadata']['iteration']==16 and np.all(a['x']==1)


def test_wrong_identity_corruption_metadata_and_two_slot_rollback(tmp_path):
    store=RollingCheckpoint(tmp_path,dict(rhs='r',Q='q'))
    store.save(dict(x=np.ones(4,complex)),MappingProxyType(dict(complex=np.complex128(2+3j),integer=np.int64(16))))
    store.save(dict(x=np.ones(4,complex)*2),dict(iteration=32))
    (tmp_path/'slot1.json').write_text('{}')
    m,a,errors=store.read();assert m['generation']==0 and np.all(a['x']==1) and errors
    assert m['metadata']['complex']==dict(real=2.,imag=3.)
    with pytest.raises(ValueError,match='no legal generation'):
        RollingCheckpoint(tmp_path,dict(rhs='wrong',Q='q')).read()
    with pytest.raises(ValueError,match='no legal generation'):
        RollingCheckpoint(tmp_path,dict(rhs='r',Q='wrong')).read()


def test_terminated_state_never_adds_epsilon_or_an_action():
    rhs=np.zeros(8,complex)
    forbidden=lambda x:(_ for _ in ()).throw(AssertionError('action on terminated state'))
    s=LSQRState.initialize(forbidden,rhs)
    assert s.values['terminated'] and not s.step(forbidden,forbidden)
    restored=LSQRState.restore(s.export());assert not restored.step(forbidden,forbidden)
    s=LSQRState.initialize(lambda x:np.zeros_like(x),np.ones(8,complex))
    assert s.values['alpha']==0 and s.values['terminated']
    broken=s.export();broken['terminated']=False
    with pytest.raises(ValueError,match='zero norm'):LSQRState.restore(broken)


def test_legacy_yields_stay_bit_identical():
    # Load the immutable pre-refactor algorithm as a test witness only.
    raw=subprocess.check_output(['git','show','f834c008110131433de0f269195de394a6856871:src/solvers/bounded_complex_lsqr.py'],text=True)
    scope={};exec(raw,scope)
    op,_,rhs=problem(True);f=op.rhs(rhs)
    old=scope['lsqr_steps'](op.apply,op.adjoint,f);new=lsqr_steps(op.apply,op.adjoint,f)
    for _ in range(20):
        a,b=next(old),next(new);assert a[0]==b[0] and a[2]==b[2]
        np.testing.assert_array_equal(a[1],b[1])


def test_gmres_complex_cycle_boundary_resume_and_counts(tmp_path):
    rng=np.random.default_rng(421701)
    A=rng.normal(size=(80,80))+1j*rng.normal(size=(80,80))+12*np.eye(80)
    rhs=rng.normal(size=80)+1j*rng.normal(size=80);base=rng.normal(size=80)+1j*rng.normal(size=80)
    counts=[]
    def cycle(t):
        next_t,record=correction_cycle(lambda x:A@x,t,rhs,np.linalg.norm(rhs))
        assert record['info'] in (0,1) and record['inner_iterations']<=64
        counts.append(record['inner_iterations']);return next_t
    first=cycle(base);np.save(tmp_path/'boundary.npy',first)
    full=cycle(first);restored=cycle(np.load(tmp_path/'boundary.npy'))
    np.testing.assert_array_equal(full,restored)
    assert np.linalg.norm(rhs-A@first)<np.linalg.norm(rhs-A@base)
    assert np.linalg.norm(rhs-A@full)<=np.linalg.norm(rhs-A@first)*(1+1e-8)
    assert counts[-1]==counts[-2]
