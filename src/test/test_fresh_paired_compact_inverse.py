"""Pure algebra negative controls for the all-q pre-factor contract."""
import copy
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse
from src.solvers.fresh_paired_compact_inverse import require_paired_prefactor_inventory,compact_cache_numeric_identity


def fixture():
    blocks=[{'q':q,'shape':[n,n],'comparison':{'passed':True,'relative_Frobenius_error':1e-15,'relative_max_error':1e-15}} for q,n in enumerate((1884,1960,1960,1960))]
    cross=[{'p':p,'q':q,'diagonal_norms':[2.,3.],'absolute_Frobenius_norm':1e-15,'passed':True} for p,q in ((0,2),(2,0),(1,3),(3,1))]
    ids=[list(range(228)),list(range(228,532))]
    return blocks,cross,ids


def test_complete_prefactor_contract():require_paired_prefactor_inventory(*fixture())


@pytest.mark.parametrize('kind',('missingq','duplicateq','shape','wrong_frob','wrong_max','nan','missingcross','reversecross','injectedcross','one_small_diagonal','duplicateport','missingport','wrongsectors'))
def test_invalid_prefactor_controls(kind):
    blocks,cross,ids=fixture()
    if kind=='missingq':blocks.pop()
    elif kind=='duplicateq':blocks[3]['q']=2
    elif kind=='shape':blocks[3]['shape']=[1959,1959]
    elif kind=='wrong_frob':blocks[2]['comparison']['relative_Frobenius_error']=1e-5
    elif kind=='wrong_max':blocks[2]['comparison']['relative_max_error']=1e-5
    elif kind=='nan':blocks[2]['comparison']['relative_max_error']=float('nan')
    elif kind=='missingcross':cross.pop()
    elif kind=='reversecross':cross[3]['p']=1;cross[3]['q']=3
    elif kind=='injectedcross':cross[0]['absolute_Frobenius_norm']=1e-5
    elif kind=='one_small_diagonal':cross[0]['diagonal_norms']=[1e-6,1e10]
    elif kind=='duplicateport':ids[1][-1]=0
    elif kind=='missingport':ids[1].pop()
    elif kind=='wrongsectors':ids=[ids[1],ids[0]]
    with pytest.raises(ValueError):require_paired_prefactor_inventory(blocks,cross,ids)


def cache():
    cell=SimpleNamespace(**{k:np.arange(4,dtype=complex).reshape(2,2) for k in ('S_V','Bhat','Dhat','recovery','trace_from_interior','Di','XiB')},
        original_interiors=np.arange(2),original_trace=np.arange(2,4),active_ids=np.arange(2),ports=np.arange(2),
        expansion=sparse.eye(2,format='csr',dtype=complex),interior_lu=(np.eye(2,dtype=complex),np.arange(2,dtype=np.int32)))
    return SimpleNamespace(action=SimpleNamespace(_H_p=None,_Hhat=None,_cells=[cell],_direct_B_active={0:(np.arange(2),np.ones(2,complex))},_direct_D_active={},_original_port_block=SimpleNamespace(numeric_arrays=(np.ones(2,complex),))))


def test_cache_identity_stable_for_unchanged_payloads():
    owner=cache();assert compact_cache_numeric_identity(owner)==compact_cache_numeric_identity(copy.deepcopy(owner))


@pytest.mark.parametrize('name',('S_V','Bhat','Dhat','recovery','trace_from_interior','Di','XiB','LU','pivots','expansion','directC','originalH'))
def test_cache_changed_payload_is_caught(name):
    owner=cache();before=compact_cache_numeric_identity(owner);cell=owner.action._cells[0]
    if name=='LU':cell.interior_lu[0][0,0]+=1
    elif name=='pivots':cell.interior_lu[1][0]+=1
    elif name=='expansion':cell.expansion.data[0]+=1
    elif name=='directC':owner.action._direct_B_active[0][1][0]+=1
    elif name=='originalH':owner.action._original_port_block.numeric_arrays[0][0]+=1
    else:getattr(cell,name)[0,0]+=1
    assert compact_cache_numeric_identity(owner)!=before


@pytest.mark.parametrize('name',('_H_p','_Hhat'))
def test_port_square_cache_rejected(name):
    owner=cache();setattr(owner.action,name,np.eye(2))
    with pytest.raises(ValueError):compact_cache_numeric_identity(owner)
