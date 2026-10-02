"""Isolated coordinate contracts; these are not physical FE qualification."""
import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

ROOT=Path(__file__).parents[1]/'solvers'


def _class(name,file):
    tree=ast.parse((ROOT/file).read_text())
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==name)
    namespace={'np':np}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(ROOT/file),'exec'),namespace)
    return namespace[name]


class _MomentBlocks:
    """Fixed nonunitary moment blocks used solely for coordinate unit tests."""
    def __init__(self,ny):
        self.ny,self.width=ny,3968
        self.independent=np.arange(ny*3968)
        self.bases=('coordinate_contract',);self.slots={'coordinate_contract':(0,3968)}
        self.dimension_counts={3:2160*ny};self.y_widths=np.ones(ny)
        self.matrices=[np.array([[2+j/10,1j/3],[.5,1.5-j/20]],complex) for j in range(ny)]
    def transform(self,values,*,direction):
        values=np.asarray(values);out=np.empty_like(values)
        for j,m in enumerate(self.matrices):
            if direction in ('primal_to_canonical','dual_from_canonical','functional_from_canonical'):m=np.linalg.inv(m)
            if direction.startswith('dual_'):m=m.conj().T
            elif direction.startswith('functional_'):m=m.T
            segment=values[j*3968:(j+1)*3968]
            if values.ndim==1:out[j*3968:(j+1)*3968]=(segment.reshape(-1,2)@m.T).reshape(-1)
            else:out[j*3968:(j+1)*3968]=np.einsum('ab,ibk->iak',m,segment.reshape(-1,2,values.shape[1])).reshape(segment.shape)
        return out


@pytest.fixture(params=(0,1))
def transport(request):
    T=_class('TwoCellNativeTransport','y_orbit_two_cell_transport.py')
    ky=.37;period=4.;eta=np.exp(1j*(ky*period+2*np.pi*request.param)/4)
    return T(_MomentBlocks(4),_MomentBlocks(2),twist_index=request.param,eta=eta,
             global_phase=np.exp(1j*ky*period),global_ky=ky,global_period_y=period)


def _values(n,offset=0):
    j=np.arange(n)+offset
    return np.cos(.13*j)+1j*np.sin(.31*j)


def test_nonunitary_native_dual_pairing(transport):
    x=_values(7936);b=_values(15872,17)
    lhs=np.vdot(b,transport.lift_primal(x));rhs=np.vdot(transport.fold_dual(b),x)
    assert abs(lhs-rhs)<1e-12*max(abs(lhs),abs(rhs),1)


def test_complete_primal_extraction_and_two_column_panel(transport):
    x=np.column_stack((_values(7936),_values(7936,11)))
    assert np.linalg.norm(transport.extract_primal(transport.lift_primal(x))-x)<1e-12*np.linalg.norm(x)


def test_C_and_already_conjugated_D_inverse_coordinates(transport):
    v=_values(7936)
    assert np.linalg.norm(transport.fold_raw_coupling(transport.lift_raw_coupling(v))-v)<1e-12*np.linalg.norm(v)
    assert np.linalg.norm(transport.fold_raw_projection(transport.lift_raw_projection(v))-v)<1e-12*np.linalg.norm(v)
    x=_values(7936,19);D=transport.lift_raw_projection(v)
    assert abs(np.dot(D,transport.lift_primal(x))-np.sqrt(2)*np.dot(v,x))<1e-12*max(abs(np.dot(D,transport.lift_primal(x))),1)


def test_principal_square_root_cannot_select_q1_q3(transport):
    if transport.b==1:
        assert abs(np.sqrt(transport.tau)-transport.eta)>1


def test_candidate_has_no_global_or_q_factor_entry():
    text=(ROOT/'y_orbit_two_cell_audit.py').read_text()
    tree=ast.parse(text)
    forbidden={'splu','lu_factor','SparseAllQFactor','build_condensed_reference','solve_notched_fgmres'}
    calls={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    assert not calls & forbidden
    assert 'candidate_full_Ny_CSR_created' in text
    assert 'global_and_q_factors' in text


def test_full_original_map_builder_is_not_called_in_orchestration():
    tree=ast.parse((ROOT/'y_orbit_two_cell_audit.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_two_cell_operator_audit')
    calls=[n for n in ast.walk(function) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='build_y_orbit_layout']
    assert len(calls)==1 and isinstance(calls[0].args[2],ast.Name) and calls[0].args[2].id=='local_cfg'
    assert {k.arg for k in calls[0].keywords}=={'wrap_phase_y','cell_phase_y'}


def test_all_FE_columns_and_all_aliases_not_base_n_only():
    text=(ROOT/'y_orbit_two_cell_audit.py').read_text()
    assert 'range(0,3968,32)' in text and 'range(532)' in text
    assert 'original_mode_indices' in text and 'raw_C_fold' not in text # generated names are per C/D


def test_metadata_only_collection_has_no_global_sparse_matrix():
    tree=ast.parse((ROOT/'task40extra_y_orbit_reference.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='collect_y_orbit_entities')
    assert not any(isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='sparse' for n in ast.walk(node))


def test_metric_comparison_has_measured_gate_and_no_round_keys():
    text=(ROOT/'y_orbit_two_cell_audit.py').read_text()
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='_actual_cells')
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='round' for n in ast.walk(node))
    assert 'maximum_actual_vertex_difference' in ast.get_source_segment(text,node)
