"""Complex matrix fixtures, no FEM assembly or formal component measurement."""
import numpy as np
from petsc4py import PETSc
from src.solvers.physical_projected_complement import ProjectedP4Complement, solve_projected_p4_complement
from src.solvers.physical_recursive_coarse import solve_physical_i4


def owned(matrix):
    def apply(x):
        y=x.copy();y.array[:]=matrix@x.array;return y
    return apply


def vector(a):
    x=PETSc.Vec().createSeq(len(a),comm=PETSc.COMM_SELF);x.array[:]=a;return x


def destroy_result(result):
    for k in ('solution','applied','residual'):result[k].destroy()


def test_complex_range_projected_nullspace_and_original_residual():
    rng=np.random.default_rng(381)
    A=rng.normal(size=(6,6))+1j*rng.normal(size=(6,6))+7*np.eye(6)
    P=np.eye(6,dtype=complex)[:,:2];C=P@np.linalg.solve(P.conj().T@A@P,P.conj().T)
    H=np.diag(1/np.diag(A));g=rng.normal(size=6)+1j*rng.normal(size=6)
    rhs=vector(g);p=vector(P@np.array([1+2j,3-1j]));ap=owned(A)(p);cp=owned(C)(ap)
    J=ProjectedP4Complement(owned(A),owned(C),owned(H),sample=lambda:None);j=J.apply(rhs)
    try:
        np.testing.assert_allclose(cp.array,p.array,atol=1e-12)
        np.testing.assert_allclose(P.conj().T@A@j.array,0,atol=1e-12)
        assert J.counts['C2_completed']==1
        result=solve_projected_p4_complement(rhs,owned(A),owned(C),owned(H),sample=lambda:None,save=lambda *a:None,clock=lambda:0.)
        try:
            f=result['facts'];actual=g-A@result['solution'].array
            np.testing.assert_allclose(result['residual'].array,actual,atol=1e-12)
            assert np.linalg.norm(actual)/np.linalg.norm(g)<=1e-4
            assert f['J_counts']['C2_completed']==f['inner']['B4_calls']
            assert f['counts']['initial_C2_completed']==f['counts']['final_A4_completed']==1
            assert f['inner']['ksp_create_count']==f['inner']['ksp_destroy_count']==1
            assert f['delta_zero_start'] and not f['reference_input']
            np.testing.assert_array_equal(rhs.array,g)
        finally:destroy_result(result)
    finally:
        for x in (rhs,p,ap,cp,j):x.destroy()


def test_original_normalization_does_not_relax_old_default():
    rhs=vector(np.array([100+100j,200-100j]));A=owned(np.eye(2))
    try:
        default=solve_physical_i4(rhs,A,A,target=1e-4,sample=lambda:None,save=lambda *a:None,clock=lambda:61.)
        strict=solve_physical_i4(rhs,A,A,target=1e-4,sample=lambda:None,save=lambda *a:None,clock=lambda:61.,residual_norm=1.)
        try:
            assert default['facts']['iterations']==strict['facts']['iterations']==0
            assert default['facts']['final_true_residual']==1.
            assert strict['facts']['final_true_residual']==rhs.norm()
            assert strict['facts']['status']=='INNER_INEXACT_AT_CAP'
        finally:destroy_result(default);destroy_result(strict)
    finally:rhs.destroy()


def test_preparation_exhausts_shared_budget_before_first_J():
    elapsed=[0.];A=np.array([[1,2j],[0,1]],complex);C=np.diag([1.,0.]);rhs=vector(np.array([1+1j,2-1j]))
    def coarse(x):
        assert elapsed[0]==0.;elapsed[0]=61.;return owned(C)(x)
    try:
        result=solve_projected_p4_complement(rhs,owned(A),coarse,owned(np.eye(2)),sample=lambda:None,save=lambda *a:None,clock=lambda:elapsed[0])
        try:
            f=result['facts'];assert f['timer_start_seconds']==0 and f['preparation_seconds']==61.
            assert f['inner']['iterations']==f['J_counts']['J_started']==0
            assert f['status']=='INNER_INEXACT_AT_CAP'
            np.testing.assert_allclose(result['residual'].array,rhs.array-A@result['solution'].array)
            assert f['seconds']==61.
        finally:destroy_result(result)
    finally:rhs.destroy()
