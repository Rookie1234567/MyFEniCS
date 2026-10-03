from benchmarks.task042_full_block_algebra import run,fixtures,normalized_error
import numpy as np


def test_three_fixed_fixtures_and_non_contraction():
    result=run()
    assert result['records'][1]['residual_norm_ratio']==6
    assert result['records'][2]['status']=='SINGULAR_LOCAL_REJECTED'
    assert [x[1].shape for x in fixtures()]==[(8,8),(2,2),(2,2)]


def test_zero_denominator_is_explicit():
    assert normalized_error(np.zeros(2),np.zeros(2))==0
    assert normalized_error(np.ones(2),np.zeros(2))==1
