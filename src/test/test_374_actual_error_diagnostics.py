"""Small complex algebra and read-only, hash-bound real evidence smoke."""
import json
from pathlib import Path

import numpy as np
import pytest

from src.solvers.actual_error_diagnostics import (
    error_identity,saved_pc_error,cell_energy_summary,coarse_gap_closure)
from src.solvers.physical_error_diagnostics import project_error,coarse_diagnostics


def test_error_sign_and_saved_pc_scaling_without_new_action():
    a=np.array([[2,1j],[.3,4]],complex)
    ref=np.array([2+1j,3]);x=np.array([1j,2]);b=np.array([1,2j])
    rr=b-a@ref;ri=b-a@x
    result=error_identity(lambda v:a@v,ref,x,ri,rr,a@ref,a@x)
    assert result['closure_relative_to_operations']<1e-15
    scale=np.linalg.norm(ri);q=ri/scale;z=np.linalg.solve(a,q)
    packet=dict(normalization_scale=scale,normalized_q=q,
                profiles={'saved':dict(correction=z,applied_direction=a@z)})
    saved=saved_pc_error(lambda v:v,result['e'],ri,rr,packet)
    np.testing.assert_allclose(saved['normalized_Ae'],a@(ref-x)/scale)
    assert saved['new_PC_calls']==saved['new_A6_calls']==0
    profile=saved['profiles']['saved']
    assert profile['mr_true_residual_ratio']<1e-14
    assert profile['unit_field_ratio']>0  # nonzero r_ref is retained, not claimed exact
    with pytest.raises(ValueError):saved_pc_error(lambda v:v,result['e'],2*ri,rr,packet)
    with pytest.raises(ValueError):error_identity(lambda v:v,ref,x[:1],ri,rr,a@ref,a@x)


def test_complex_coarse_gap_and_energy_decomposition():
    p=np.array([[1,0],[1j,1],[0,2j]],complex);m=np.diag([2.,3.,4.])
    a=np.array([[2,1j,3],[.5,2,0],[1j,0,4]],complex)
    e=np.array([1+2j,3-1j,.5j]);adj=lambda v:p.conj().T@v
    a4=p.conj().T@a@p
    projection=project_error(lambda v:p@v,adj,lambda v:m@v,np.diag(p.conj().T@m@p),e)
    calls=[]
    def solve(g):
        calls.append(g.copy());return np.linalg.solve(a4,g)
    coarse=coarse_diagnostics(lambda v:a@v,lambda v:m@v,lambda v:p@v,adj,solve,e,
                              projection,identity_check=False,saved_q=a@e)
    gap=coarse_gap_closure(lambda v:a4@v,adj,lambda v:a@v,projection,coarse,lambda v:m@v)
    assert len(calls)==1
    assert gap['closure_relative_to_operations']<1e-14
    assert coarse['decomposition_relative_defect']<1e-14
    assert gap['projection_qualified']
    np.testing.assert_allclose(a4@gap['coarse_difference'],-gap['g_perp'])


def test_owned_cell_partition_totals():
    cells=dict(mass=np.array([1.,2.,3.]),curl=np.array([3.,4.,5.]),
        material_tags=np.array([1,2,1]),cell_centers=np.array([[0,0,0],[1,0,0],[0,0,1]]))
    result=cell_energy_summary(cells,6.,12.)
    assert max(result['global_relative_defects'].values())==0
    assert sum(v['mass'] for v in result['materials'].values())==6
    assert sum(v['curl'] for v in result['height_layers'].values())==12


def test_real_saved_evidence_load_without_fe():
    from src.runners.physical_diagnostic_completion import reuse_v3
    from src.runners.actual_error_diagnosis import load_actual_evidence,LABELS
    manifest=Path('input/task39extra/actual_error_evidence.json')
    if not Path(json.loads(manifest.read_text())['reference_audit']).exists():
        pytest.skip('local ignored formal evidence is unavailable')
    inventory=Path('docs/task039_extra_physical_multilevel/outcomes/records/nonconvergence_diagnosis_v3.json')
    result=load_actual_evidence(manifest,inventory,reuse_v3(json.loads(inventory.read_text())))
    assert result['reference']['relative_residual']<=1e-10
    for label in LABELS:
        for name in ('S6','LIGHT','JOINT'):
            assert result['packets'][label+'_'+name]['normalization_scale']>0
