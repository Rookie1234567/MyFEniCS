"""P4 receipt/source-profile regressions only, never FE numerical qualification."""
import copy
import hashlib
import json

import pytest
import numpy as np

from src.solvers.y_orbit_centered_bridge import (
    AUTHORITY_HEAD, cross_head_source_binding, compare_bridge_discrete_contract,
)
from src.solvers.y_orbit_live_boundary_contract import validate_live_receipt
from src.test.test_y_orbit_live_boundary_contract import _receipt
from benchmarks.check_y_orbit_sparse_probe import _require_operation_scale_binding


def _source(head, files):
    return {"head":head,"branch":"task40extra_dot_parallel_cloud","dirty":"","files_sha256":files}


def test_cross_head_diff_records_exact_old_new_bytes_and_preserves_physical_sources():
    helper="src/solvers/dtn_boundary_plane_qualification.py"
    old=_source(AUTHORITY_HEAD,{helper:"old","src/solvers/dtn_port_3d.py":"physical"})
    new=_source("f"*40,{helper:"new","src/solvers/dtn_port_3d.py":"physical"})
    binding=cross_head_source_binding(old,new)
    assert binding["changed_dependencies"]==[{"path":helper,"authority_sha256":"old","executed_sha256":"new"}]
    new["files_sha256"]["src/solvers/dtn_port_3d.py"]="changed"
    with pytest.raises(ValueError,match="unreviewed"):
        cross_head_source_binding(old,new)


@pytest.mark.parametrize("field",["mesh","MPC","ABI","gauss_discrete_contract","element_degree"])
def test_matching_source_profile_never_hides_changed_discretization(field):
    helper="src/solvers/dtn_boundary_plane_qualification.py"
    binding=cross_head_source_binding(_source(AUTHORITY_HEAD,{helper:"old"}),_source("f"*40,{helper:"new"}))
    old={"source_sha256":{"dtn_boundary_plane_qualification.py":"old"},field:"unchanged"}
    new={"source_sha256":{"dtn_boundary_plane_qualification.py":"new"},field:"unchanged"}
    assert compare_bridge_discrete_contract(old,new,binding)["requires_all_2048_columns_and_four_load_controls"]
    new[field]="different"
    with pytest.raises(ValueError,match="fixed physical/discrete"):
        compare_bridge_discrete_contract(old,new,binding)


def test_context_helper_hash_must_match_the_recorded_source_diff():
    helper="src/solvers/dtn_boundary_plane_qualification.py"
    binding=cross_head_source_binding(_source(AUTHORITY_HEAD,{helper:"old"}),_source("f"*40,{helper:"new"}))
    with pytest.raises(ValueError,match="exact old/new"):
        compare_bridge_discrete_contract({"source_sha256":{"dtn_boundary_plane_qualification.py":"old"}},
            {"source_sha256":{"dtn_boundary_plane_qualification.py":"swapped"}},binding)


def _p4_receipt():
    r,keys=_receipt();r["degree"]=4
    c=r["raw_discrete_context"];c["element_degree"]=4;c["gauss"]["degree"]=23
    for record in r["primary_compiled_gauss"].values():
        record["rules"][0].update(degree=23,points={"sha256":"p4nodes","shape":[144,2]},
                                  weights={"sha256":"p4weights","shape":[144]})
    c["gauss"]["compiled_forms_verified"]=copy.deepcopy(r["primary_compiled_gauss"])
    r["independent_oracle_compiled_gauss"]={g+"/"+name:{"rules":copy.deepcopy(record["rules"])}
        for g in ("global_z","boundary_plane") for name,record in r["primary_compiled_gauss"].items()}
    r["incident_literal_gauss"]={"rules":copy.deepcopy(r["primary_compiled_gauss"]["top/0"]["rules"])}
    digest=hashlib.sha256(json.dumps(c,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")).hexdigest()
    r["identity"]["assembly_context_sha256"]=digest;r["assembly_context_sha256"]=digest
    return r,keys


def test_p4_requires_its_own_actual_basis_gauss_profile():
    r,keys=_p4_receipt()
    assert validate_live_receipt(r,physical_manifest="physical",ordered_keys=keys,expected_degree=4)
    with pytest.raises(ValueError):validate_live_receipt(r,physical_manifest="physical",ordered_keys=keys)
    p2,keys=_receipt()
    with pytest.raises(ValueError):validate_live_receipt(p2,physical_manifest="physical",ordered_keys=keys,expected_degree=4)


def test_p4_cannot_relabel_a_p2_compiled_rule_as_its_own():
    r,keys=_p4_receipt()
    r["primary_compiled_gauss"]["top/0"]["rules"][0]["points"]["shape"]=[100,2]
    with pytest.raises(ValueError):validate_live_receipt(r,physical_manifest="physical",ordered_keys=keys,expected_degree=4)


def test_inflated_saved_scale_cannot_mask_a_weak_mode_output_error():
    expected=np.ones(532);expected[0]=1e-20;expected[1:]=1e12
    saved=expected.copy()
    assert _require_operation_scale_binding(saved,expected,"amplitude")
    saved[0]=1e100
    with pytest.raises(ValueError,match="detached"):
        _require_operation_scale_binding(saved,expected,"amplitude")


def test_zero_expected_operation_scale_has_no_saved_absolute_floor():
    expected=np.ones(532);expected[0]=0
    saved=expected.copy();saved[0]=1e-200
    with pytest.raises(ValueError,match="exact zero"):
        _require_operation_scale_binding(saved,expected,"power")
