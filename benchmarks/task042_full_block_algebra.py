"""V29 isolated n<=24 algebra fixtures. Not imported by any solver/runner."""
import numpy as np
from src.solvers.neural_fe_action_packet import array_hash

SEED = 422901


def fixtures():
    rng=np.random.default_rng(SEED)
    A=3*np.eye(8,dtype=np.complex128)+.07*(rng.standard_normal((8,8))+1j*rng.standard_normal((8,8)))
    return [('NON_HERMITIAN_8',A,[0,1],[[2],[3],[4],[5],[6],[7]]),
            ('NON_CONTRACTION_2',np.array([[1,2],[3,1]],np.complex128),[0],[[1]]),
            ('SINGULAR_LOCAL_2',np.array([[0,1],[1,2]],np.complex128),[0],[[1]])]


def embedded_inverse(A,groups):
    n=len(A);out=np.zeros_like(A)
    for ids in groups:
        block=A[np.ix_(ids,ids)]
        # Explicit small inverse is a test oracle only, never a deployed PC.
        out[np.ix_(ids,ids)]=np.linalg.solve(block,np.eye(len(ids),dtype=np.complex128))
    return out


def normalized_error(left,right):
    err=float(np.linalg.norm(left-right));scale=float(np.linalg.norm(left)+np.linalg.norm(right))
    if scale==0:return 0. if err==0 else None
    return err/scale


def run():
    records=[]
    for name,A,J,O in fixtures():
        n=len(A);identity=np.eye(n,dtype=np.complex128)
        base=dict(name=name,n=n,seed=SEED,dtype=str(A.dtype),matrix_sha256=array_hash(A),J=J,outer_groups=O)
        try:BJ=embedded_inverse(A,[J]);LO=embedded_inverse(A,O)
        except np.linalg.LinAlgError:
            records.append(dict(base,status='SINGULAR_LOCAL_REJECTED',no_shift_or_repartition=True));continue
        Bret=BJ-(identity-BJ@A)@LO@A@BJ
        Bfull=BJ+(identity-BJ@A)@LO@(identity-A@BJ)
        # Actual chronological application: J -> residual -> outer -> J.
        def apply(r):
            q1=BJ@r;u=LO@(r-A@q1);feedback=BJ@(A@u)
            assert np.count_nonzero(q1[[i for i in range(n) if i not in J]])==0
            assert np.count_nonzero(u[J])==0
            assert np.count_nonzero(feedback[[i for i in range(n) if i not in J]])==0
            return q1+u-feedback
        r=np.arange(1,n+1,dtype=np.complex128)*(1+.2j)
        s=r[::-1].copy()*(.3-.7j)
        full=np.column_stack([apply(identity[:,i]) for i in range(n)])
        checks=dict(difference=normalized_error(Bfull-Bret,(identity-BJ@A)@LO),
            chronological=normalized_error(full,Bfull),zero=normalized_error(apply(np.zeros(n,complex)),np.zeros(n,complex)),
            complex_linearity=normalized_error(apply((.4+.8j)*r+(.2-.3j)*s),(.4+.8j)*apply(r)+(.2-.3j)*apply(s)))
        # Block-triangular factorization proves invertibility without requiring
        # the full A to be positive, Hermitian, or a residual contraction.
        order=J+[i for group in O for i in group];Ar=A[np.ix_(order,order)];j=len(J)
        Dinv=LO[np.ix_(order,order)][j:,j:];Jinv=BJ[np.ix_(order,order)][:j,:j]
        upper=np.eye(n,dtype=complex);upper[:j,j:]=-Jinv@Ar[:j,j:]
        diagonal=np.zeros((n,n),complex);diagonal[:j,:j]=Jinv;diagonal[j:,j:]=Dinv
        lower=np.eye(n,dtype=complex);lower[j:,:j]=-Ar[j:,:j]@Jinv
        checks['triangular_factorization']=normalized_error(Bfull[np.ix_(order,order)],upper@diagonal@lower)
        assert all(v is not None and v<=1e-12 for v in checks.values()),checks
        record=dict(base,status='ALGEBRA_CHECKED',checks=checks,
            deployment_counts=dict(J_solves=2,outer_solves_each=1,outer_blocks=len(O),original_A_propagations=2,
                                   final_true_residual_and_port_closure='separate'),
            invertible_local_blocks_full_space_action=True,convergence_not_implied=True)
        if name=='NON_CONTRACTION_2':
            r=np.array([0,1],complex);q=apply(r);e=r-A@q
            assert normalized_error(Bfull,np.array([[7,-2],[-3,1]],complex))<=1e-12
            assert np.array_equal(Bret@r,np.zeros(2)) and np.array_equal(q,[-2,1]) and np.array_equal(e,[0,6])
            record.update(external_input=[0,1],Bret_output=[0,0],Bfull_output=[-2,1],true_remaining=[0,6],
                          residual_norm_ratio=6.,interpretation='full-space action does not guarantee contraction')
        records.append(record)
    assert len(records)==3 and records[-1]['status']=='SINGULAR_LOCAL_REJECTED'
    return dict(status='SMALL_ALGEBRA_ONLY_CHECKED',fixed_fixture_count=3,records=records,
                real_action_calls=0,real_factor_reads=0,production_PC_registered=False)
