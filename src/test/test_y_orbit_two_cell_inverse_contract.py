"""Isolated coordinate/source contracts, never physical FE qualification."""
import ast
from pathlib import Path
from types import SimpleNamespace
from types import MappingProxyType
from collections.abc import Mapping
import numpy as np
import pytest
import copy

ROOT=Path(__file__).parents[1]/'solvers'

def _layout_class():
    tree=ast.parse((ROOT/'y_orbit_two_cell_inverse.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='StreamedFullYLayout')
    ns={'np':np};exec(compile(ast.Module(body=[node],type_ignores=[]),'isolated_native_layout','exec'),ns)
    return ns['StreamedFullYLayout']

class _MomentCoordinates:
    ny,width,full_rows=4,3968,17204
    independent=np.arange(15872)
    def transform(self,v,*,direction):
        # Fixed complex nonunitary coordinates test the algebra only.
        weights=(1.2+.1j)*np.ones(15872)
        if direction=='primal_to_canonical':return np.asarray(v)/weights
        if direction=='primal_from_canonical':return weights*np.asarray(v)
        if direction=='dual_to_canonical':return weights.conj()*np.asarray(v)
        if direction=='dual_from_canonical':return np.asarray(v)/weights.conj()
        raise ValueError('explicit direction required')

@pytest.fixture
def layout():
    cfg=SimpleNamespace(ky=.23,period_y=4.,floquet_phase_y=np.exp(1j*.92))
    return _layout_class()(_MomentCoordinates(),cfg)

def test_small_DFT_retains_all_native_channels_and_primal_inverse(layout):
    j=np.arange(15872);x=np.cos(.23*j)+1j*np.sin(.37*j)
    assert np.linalg.norm(layout.primal_from_modal(layout.primal_to_modal(x))-x)<1e-12*np.linalg.norm(x)
    assert layout.cell_dft.shape==(4,4)
    assert all(v>0 for v in layout.modal_norms(x,dual=False))

def test_nonunitary_dual_pairing_and_dual_inverse(layout):
    j=np.arange(15872);u=np.cos(.11*j)+1j*np.sin(.31*j);b=np.sin(.17*j)+1j*np.cos(.43*j)
    lhs=np.vdot(b,layout.primal_from_modal(u));rhs=np.vdot(layout.dual_to_modal(b),u)
    assert abs(lhs-rhs)<1e-12*max(abs(lhs),abs(rhs),1)
    recovered=layout.entities.transform(layout._dft(layout.dual_to_modal(b),adjoint=False),direction='dual_from_canonical')
    assert np.linalg.norm(recovered-b)<1e-12*np.linalg.norm(b)

def test_prefactor_returns_before_any_global_q_factor_constructor():
    tree=ast.parse((ROOT/'y_orbit_two_cell_inverse_probe.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_quotient_inverse_probe')
    text=ast.unparse(fn)
    assert text.index("stage == 'prefactor'")<text.index('FourBranchFactors(')
    assert 'QUOTIENT_PREFACTOR_COMPARE_PASS' in text
    assert 'raw_literal_qualification_rerun' in text

def test_complete_recovery_keeps_dual_and_auxiliary_scales():
    text=(ROOT/'y_orbit_two_cell_inverse.py').read_text()
    tree=ast.parse(text)
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='apply_augmented')
    code=ast.unparse(method)
    assert 'transport.fold_dual(rhs)' in code and 'transport.lift_primal(' in code
    assert 'rhs_is_mpc_dual=True' in code and 'expand_trace=False' in code
    assert 'ports[ids] / np.sqrt(2)' in code and '/ np.sqrt(2)' in code
    assert 'recover_storage(' in code

def test_public_factor_has_no_L_U_statistics_copies():
    tree=ast.parse((ROOT/'y_orbit_two_cell_inverse.py').read_text())
    assert not any(isinstance(n,ast.Attribute) and n.attr in ('L','U') for n in ast.walk(tree))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='FourBranchFactors')
    code=ast.unparse(cls)
    assert 'LU_fill_and_workspace_unknown=True' in code
    assert 'factor_workspace_allowance_bytes=remaining' in code
    assert 'retained_factor_count=len(self.factors)' in code
    assert 'all_four_retained_simultaneously=True' in code

def test_old_numerical_dependencies_are_not_reimplemented():
    text=(ROOT/'y_orbit_two_cell_inverse_probe.py').read_text()
    assert 'solve_notched_fgmres' in text and 'original_packet' in text and 'recovered_field_and_modes' in text
    assert 'qualify_quotient_raw_bundle(' not in text and 'build_same_mesh_physical_action(' not in text
    assert 'assemble_original_dense(' not in text and 'build_condensed_reference(' not in text


def _identity_fixture():
    tree=ast.parse((ROOT/'y_orbit_two_cell_inverse_probe.py').read_text())
    node=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_recovery_identity_gate'))
    node.body=[n for n in node.body if not isinstance(n,ast.ImportFrom)]
    def json_types(v):
        if isinstance(v,Mapping):return {k:json_types(x) for k,x in v.items()}
        if isinstance(v,(tuple,list)):return [json_types(x) for x in v]
        return v
    ns={'np':np,'_jsonable':json_types}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'isolated_recovery_identity','exec'),ns)
    rows={k:np.arange(3,dtype=np.int32) for k in ('independent_storage_rows','trace_original_rows','interior_original_rows','slave_storage_rows')}
    tensors={str(j):{'raw_sha256':str(j),'oriented_sha256':str(j),'dtype':'complex128','shape':[300,300]} for j in range(20)}
    policy={'key_dependencies':['material','metric','orientation','basis','kernel_counts','complex128'],
            'scope':'single builder invocation; no cross-form reuse',
            'policy_signatures':{'actual_space':{'dimension':300,'dtype':'complex128','element_hash':7,
                'kernel_ids':[1,2,3],'kernel_counts':[[1,1],[2,1],[3,1]],'raw_tensor_evaluator':None,'ufcx_form_signature':'new'}}}
    actual={'action_only_complete_tensor_identities':tensors,'operator_cache_identity':policy}
    old=copy.deepcopy(actual);old['operator_cache_identity']['policy_signatures']['actual_space']['ufcx_form_signature']='historical'
    condensed=SimpleNamespace(independent_original_rows=rows['independent_storage_rows'],
        trace_original_rows=rows['trace_original_rows'],interior_original_rows=rows['interior_original_rows'],audit={'condensation':actual})
    setup={'floquets':{4:SimpleNamespace(mpc=SimpleNamespace(slaves=rows['slave_storage_rows']))}}
    authority=SimpleNamespace(load=lambda key:rows[key.removeprefix('twist_0_')],
        report={'twists':[{'condensation':{'condensation':old}}]})
    return ns['_recovery_identity_gate'],condensed,setup,authority,actual

def test_distinct_compiler_signatures_require_exact_all_numeric_tensors():
    fn,c,s,a,_=_identity_fixture();result=fn(c,s,a,0,event=lambda *_:None)
    assert result['raw_oriented_tensor_exact_equal'] and result['cache_recipe_equal']
    assert result['compiler_signatures']['actual_space']=={'historical':'historical','new':'new'}
    assert result['new_volume_identity_claimed_equal_to_old_JIT'] is False

def test_frozen_historical_metadata_normalizes_without_identity_waiver():
    fn,c,s,a,_=_identity_fixture()
    def frozen(v):
        if isinstance(v,dict):return MappingProxyType({k:frozen(x) for k,x in v.items()})
        if isinstance(v,list):return tuple(frozen(x) for x in v)
        return v
    a.report=frozen(a.report)
    result=fn(c,s,a,0,event=lambda *_:None)
    assert result['raw_oriented_tensor_exact_equal'] and result['cache_recipe_equal']

@pytest.mark.parametrize('change',('row_dtype','tensor','recipe','missing_tensor'))
def test_recovery_identity_mismatch_stops_before_factor(change):
    fn,c,s,a,current=_identity_fixture()
    if change=='row_dtype':c.independent_original_rows=c.independent_original_rows.astype(np.int64)
    elif change=='tensor':current['action_only_complete_tensor_identities']['0']['raw_sha256']='changed'
    elif change=='recipe':current['operator_cache_identity']['policy_signatures']['actual_space']['kernel_ids']=[1,2]
    else:current['action_only_complete_tensor_identities'].pop('0')
    with pytest.raises(ValueError,match='before factor'):fn(c,s,a,0,event=lambda *_:None)
