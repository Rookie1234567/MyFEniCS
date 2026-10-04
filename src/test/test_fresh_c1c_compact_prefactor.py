"""Selected-witness nonvacuity and coupling injection, no FE/JIT."""
import numpy as np
import pytest
from scipy import sparse
from src.solvers.fresh_c1c_compact_prefactor import STATUS,check_prefactor,_compare

@pytest.mark.parametrize('report',[{}, {'status':STATUS,'q':1},
 {'status':STATUS,'q':0,'twist':0,'global_q_factor_count':1},
 {'status':STATUS,'q':0,'twist':0,'global_q_factor_count':0,'full_C1c_qualified':True}])
def test_partial_witness_cannot_claim_lost_inventory_or_full_chain(report):
    def no_load(_):raise AssertionError('invalid inventory must stop before numeric loading')
    with pytest.raises(ValueError):check_prefactor(report,no_load,reference=None,allocation_gate=None)

def test_strict_reference_comparison_catches_injected_coupling_and_conjugation():
    reference=sparse.csr_matrix(np.array([[2+1j,.2+.3j],[.1-.4j,3-.2j]]))
    assert _compare(reference,reference,limit=1e-11,label='same')['passed']
    changed=reference.copy();changed[0,1]+=.01
    assert not _compare(changed,reference,limit=1e-11,label='injected')['passed']
    assert not _compare(reference.conjugate(),reference,limit=1e-11,label='wrong_dual')['passed']
