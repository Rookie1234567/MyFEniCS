"""Bounded complex fixtures, exact cell pullback and independent extra images."""
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import lu_factor,lu_solve,lstsq

from src.solvers.joint_block_direction import (assemble_selected,JointSolve,
    factor_once,qualification,extra_direction,selected_rows,capacity,decision)
from src.solvers.joint_block_window import CAPS,validate_increment
from src.test.test_task042_v22_p1_trace import dense_case
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.joint_block_study import checked_array


def random(rng,shape):return rng.standard_normal(shape)+1j*rng.standard_normal(shape)


def test_selected_assembly_uses_every_cell_duplicate_phase_and_nonmutual_ports():
    rng=np.random.default_rng(422600);n,lt,nc,np_=8,4,3,40
    erows=np.repeat(np.arange(nc*lt),2);eids=rng.integers(0,n,len(erows));evals=random(rng,len(erows))
    cells=[]
    for c in range(nc):
        E=np.zeros((lt,n),complex);take=(erows//lt)==c
        np.add.at(E,(erows[take]-c*lt,eids[take]),evals[take]);cells.append(E)
    S=random(rng,(nc,lt,lt));D=random(rng,(nc,np_,lt));C=random(rng,(n,np_));H=40*np.eye(np_)+random(rng,(np_,np_))
    dp=np.array([0,2,2,2]);dr=np.array([3,1,1,6]);dv=random(rng,4)
    a=dict(erows=erows,eids=eids,evals=evals,classes=np.arange(nc),S=S,Dhat=D,dp=dp,dr=dr,dv=dv)
    packet=SimpleNamespace(nt=n,np=np_,nc=nc,lt=lt,a=a)
    K=sum(E.conj().T@Sc@E for E,Sc in zip(cells,S,strict=True));F=-sum(Dc@E for E,Dc in zip(cells,D,strict=True))
    np.add.at(F,(dp,dr),-dv);A=K-C@np.linalg.solve(H,F)
    ids=np.array([0,1,3,6]);events=[]
    actual,report=assemble_selected(packet,ids,C,lambda r:np.linalg.solve(H,r),event=lambda **x:events.append(x))
    np.testing.assert_allclose(actual,A[np.ix_(ids,ids)],rtol=1e-12,atol=1e-11)
    assert report['all_cells_visited']==3 and report['port_matrix_RHS_columns']==4
    assert not report['global_fine_matrix'] and not report['F_C_adjoint_assumed'] and events
    assert np.linalg.norm(F-C.conj().T)>1


def test_true_complex_bar_chain_and_extra_direction_match_independent_dense_ls():
    packet,bar,z,A,*_=dense_case(n=16);rhs=packet.a['b'];t=.3*z[:16]
    r=bar.reduced_rhs(rhs)-bar.apply(t);ids=np.array([0,2,5,7,10,12,14,15]);block=A[np.ix_(ids,ids)]
    counts=Counter();count=lambda k,n=1:counts.update({k:n})
    factor,safety=factor_once(block,count=count);assert safety['qualified']
    joint=JointSolve(16,ids,block,factor,count=count);assert qualification(joint,bar.apply,bar.adjoint)['qualified']
    assert counts['joint_LU_attempts']==1 and counts['gecon_triangular_pass_upper']==22
    rng=np.random.default_rng(422620);directions=random(rng,(16,8));images=A@directions
    c=lstsq(images,r,cond=1e-12,lapack_driver='gelsd')[0]
    result,arrays=extra_direction(r,directions,images,c,joint,bar.apply,bnorm=packet.bnorm,
        old_scales=np.linalg.norm(images,axis=0),count=count)
    assert result['trustworthy'] and result['new_direction_resolved'] and result['rank']==9
    direct=np.column_stack((images,A@arrays['joint_direction']));coef=lstsq(direct,r,cond=1e-12,lapack_driver='gelsd')[0]
    np.testing.assert_allclose(r-arrays['diagnostic_residual'],direct@coef,atol=1e-10)
    assert result['eta9']<=result['eta8']+1e-10 and counts['thin_decompositions']==1
    assert np.linalg.norm(bar.close(t,rhs)[-40:])>0
    assert np.linalg.norm(packet.S[:16,-40:]-packet.S[-40:,:16].conj().T)>1


def test_duplicate_new_direction_is_explicitly_unresolved_not_huge_coefficient():
    A=np.eye(16,dtype=complex);ids=np.array([0,1]);joint=JointSolve(16,ids,A[np.ix_(ids,ids)],lu_factor(A[np.ix_(ids,ids)]))
    directions=np.eye(16,8,dtype=complex);r=np.ones(16,complex)
    out,arrays=extra_direction(r,directions,directions,np.ones(8,complex),joint,lambda x:x,
        bnorm=1,old_scales=np.ones(8))
    assert out['status']=='REDUNDANT_OR_UNRESOLVED' and not out['new_direction_resolved']
    assert abs(arrays['coefficients'][-1])==0 and out['eta9']==out['eta8']
    assert out['h_norm']<=out['h_roundoff_floor']


def test_zero_new_response_and_zero_residual_never_create_a_positive_signal():
    A=np.eye(16,dtype=complex);ids=np.array([14,15]);joint=JointSolve(16,ids,A[np.ix_(ids,ids)],lu_factor(A[np.ix_(ids,ids)]))
    d=np.eye(16,8,dtype=complex);r=np.zeros(16,complex)
    out,arrays=extra_direction(r,d,d,np.zeros(8),joint,lambda x:x,bnorm=1,old_scales=np.ones(8))
    assert not out['trustworthy'] and out['g'] is None and out['h_over_vj']==0
    assert np.count_nonzero(arrays['joint_direction'])==0


def test_fixed_factor_singularity_and_missing_partition_do_not_trigger_rescue():
    counts=Counter()
    with pytest.raises(Exception):factor_once(np.zeros((3,3),complex),count=lambda k,n=1:counts.update({k:n}))
    assert counts['joint_LU_attempts']==1
    with pytest.raises(ValueError):selected_rows(np.zeros(18144,dtype=int))
    assert capacity(3888,18144)['explicit_matrix_LU_bytes']==483729408


def test_named_two_state_decision_and_nonrefreshable_caps():
    names=('V24-LZ-CYCLE4','V24-LCZ-CYCLE4');row=dict(trustworthy=True,new_direction_resolved=True,g=.5)
    rows=[dict(row,name=n) for n in names];assert decision(rows)=='JOINT_EXTRA_DIRECTION_SIGNAL'
    assert decision([rows[0],rows[0]])=='NUMERICALLY_UNRESOLVED'
    assert decision([dict(x,g=.99) for x in rows])=='FIXED_JOINT_DIRECTION_INSUFFICIENT'
    done=dict.fromkeys(CAPS,0);done['joint_LU_attempts']=1
    with pytest.raises(RuntimeError,match='cap'):validate_increment(dict.fromkeys(CAPS,0),done,'joint_LU_attempts')
    done['actions']=64
    with pytest.raises(RuntimeError,match='cap'):validate_increment(dict.fromkeys(CAPS,0),done,'actions')
    done['thin_decompositions']=2
    with pytest.raises(RuntimeError,match='cap'):validate_increment(dict.fromkeys(CAPS,0),done,'thin_decompositions')


def test_readonly_factor_reload_has_private_pivots_and_rejects_bad_hash(tmp_path):
    rng=np.random.default_rng(422621);A=10*np.eye(8)+random(rng,(8,8));factor=lu_factor(A)
    receipts=[]
    for name,value in zip(('matrix','LU','pivots'),(A,*factor),strict=True):
        path=tmp_path/(name+'.npy');np.save(path,value)
        receipts.append(dict(path=str(path),sha256=file_hash(path),shape=list(value.shape),array_sha256=array_hash(value)))
    arrays=[checked_array(x,tmp_path) for x in receipts]
    joint=JointSolve(8,np.arange(8),arrays[0],arrays[1:]);rhs=random(rng,8)
    assert not arrays[1].flags.writeable and not arrays[2].flags.writeable
    assert joint.factor[1].flags.writeable and not np.shares_memory(joint.factor[1],arrays[2])
    np.testing.assert_allclose(A@joint.solve(rhs),rhs,atol=1e-12)
    with pytest.raises(ValueError,match='path/hash'):checked_array(dict(receipts[0],sha256='bad'),tmp_path)
    with pytest.raises(ValueError,match='shape/mode'):checked_array(dict(receipts[0],shape=[7,7]),tmp_path)
    path=tmp_path/'half.npy';path.write_bytes(b'incomplete')
    with pytest.raises(ValueError):checked_array(dict(receipts[0],path=str(path)),tmp_path)


def test_actual_one_run_schema_stage_registration_and_no_old_default_change(tmp_path):
    from pathlib import Path
    from src.io.joint_block_diagnostic import load_joint_diagnostic
    from src.io.input_loader import InputError
    from src.io.task042_profile import TASK042_PROFILES
    from src.runners.block_direction_diagnostic import DirectionStage
    import inspect
    root=Path(__file__).resolve().parents[2]
    spec=load_joint_diagnostic(root/'input/task042_neural_coarse_inverse/v26_joint_block_diagnostic.dat')
    assert spec.derived['stage']=='V26-DIAGNOSTIC' and TASK042_PROFILES[spec.solver['preconditioner']]=='V26-DIAGNOSTIC'
    assert spec.execution['mpi_size']==1 and spec.derived['environment_mode']=='pure'
    bad=tmp_path/'bad.dat';text=(root/'input/task042_neural_coarse_inverse/v26_joint_block_diagnostic.dat').read_text()
    for original,replacement in [('DIAGNOSTIC','CONTINUE'),('schema_version = 1','schema_version = 2'),
                                  ('USER_20260929_V1','UNKNOWN')]:
        bad.write_text(text.replace(original,replacement))
        with pytest.raises(InputError):load_joint_diagnostic(bad)
    assert load_joint_diagnostic(root/'input/task042_neural_coarse_inverse/v25_block_residual_diagnostic.dat') is None
    signature=inspect.signature(DirectionStage)
    assert signature.parameters['actor_limit'].default==600 and signature.parameters['artifact_limit'].default==128*2**20
