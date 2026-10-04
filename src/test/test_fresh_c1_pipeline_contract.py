"""Fresh C1 metadata negatives only; no FE, JIT, matrix or solver execution."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.fresh_c1_contract import (
    P6_WORKER_STATUS, P6_CHECKER_STATUS, P6_CORE_STATUS, FRESH_LIMITS,
    TREE_CAP_BYTES, WALL_SECONDS, validate_profile, validate_component_packets,resolve_storage_budget,
    validate_shared_fixture, validate_resource_receipt, near_zero_output_check,
)
from benchmarks.run_y_orbit_sparse_probe import _fresh_resource,_fresh_storage_budget


def _packets():
    source={"head":"a"*40,"branch":"task40extra_dot_parallel_cloud","dirty":"","files_sha256":{}}
    environment={"scope":"imports_only"}
    inventory={"degree":6,"cell_count":80,"local_dimension":882,
        "local_interiors":450,"local_traces":432,"storage_rows":55950,
        "independent_rows":52992,"interior_rows":36000,"active_trace_rows":16992,"port_rows":532}
    budget=resolve_storage_budget("p6-component")
    core={"status":P6_CORE_STATUS,"same_system_and_carrier":True,
        "global_p6_matrix_created":False,"global_p6_factor_created":False,"quotient_constructed":False,
        "actual_inventory":inventory,"limits":dict(FRESH_LIMITS),
        "storage_budget_contract":budget,
        "snapshot":{"members":[{"name":"synthetic"}],"archive_payload_limit_bytes":budget["primitive_export_limit_bytes"]}}
    report={"status":P6_WORKER_STATUS,"fresh_fixture_c1":"p6-component",
        "source_clean_unchanged":True,"source":source,"environment":environment,"component":core,
        "storage_budget_contract":budget}
    checker={"status":P6_CHECKER_STATUS,"gate_pass":True,"evidence_valid":True,
        "source":source,"environment":environment,"storage_budget_contract":budget,
        "report_sha256":"r","provenance_sha256":"p",
        "artifact_manifest_sha256":"m","checks":[{"name":"synthetic","passed":True}],
        "cells_checked":list(range(80)),"q_alias_counts_recomputed":[76,152,152,152],
        "all_saved_members_hash_checked":True,"unique_saved_members_checked":1,
        "negative_controls":{name:{"separated":True} for name in
            ("omitted_correction","wrong_sign","wrong_conjugation","Hhat_substituted_for_original_H")}}
    return report,checker,dict(expected_source=source,expected_environment=environment,
        report_sha256="r",provenance_sha256="p",artifact_manifest_sha256="m")


@pytest.mark.parametrize("stage,degree",[("p6-component",6),("p4-chain",4)])
def test_explicit_fresh_profiles(stage,degree):
    receipt=validate_profile(stage,degree=degree,auxiliary_gauge="positive-h",
        dtn_phase_gauge="boundary_plane",live_component_oracle=True)
    assert receipt["limits"]==FRESH_LIMITS
    assert receipt["near_zero_output"]["existing_operation_scaled_limits_changed"] is False
    assert receipt["unknown_cold_JIT_and_fill"]


def test_explicit_c1a768_budget_preserves_all_other_resource_and_math_limits():
    args=SimpleNamespace(fresh_fixture_c1="p6-component",c1a_raw_budget_mib=768,
                         research_memory_gib=3,research_wall_seconds=4500)
    budget=_fresh_storage_budget(args)
    assert budget=={"selector":"c1a_768MiB_v1","c1a_raw_budget_mib":768,
        "primitive_export_limit_bytes":768*1024**2,
        "full_packet_uncompressed_limit_bytes":1024**3}
    assert _fresh_resource(args)==(TREE_CAP_BYTES,WALL_SECONDS)
    receipt=validate_profile("p6-component",degree=6,auxiliary_gauge="positive-h",
        dtn_phase_gauge="boundary_plane",live_component_oracle=True,c1a_raw_budget_mib=768)
    assert receipt["storage_budget_contract"]==budget and receipt["limits"]==FRESH_LIMITS
    assert receipt["uncompressed_raw_export_budget_bytes"]==768*1024**2


@pytest.mark.parametrize("stage,flag",[(None,768),("p4-chain",768),("p6-component",512),
    ("p6-component",1024),("p6-component",True),("p6-component",768.0)])
def test_c1a_budget_cannot_expand_other_profiles_or_accept_arbitrary_values(stage,flag):
    with pytest.raises(ValueError,match="C1a-only"):
        _fresh_storage_budget(SimpleNamespace(fresh_fixture_c1=stage,c1a_raw_budget_mib=flag))


def test_default_primitive_budget_stays512_even_on_fresh_p6():
    for stage in (None,"p6-component","p4-chain"):
        assert _fresh_storage_budget(SimpleNamespace(fresh_fixture_c1=stage))=={
            "selector":"legacy_512MiB","c1a_raw_budget_mib":None,
            "primitive_export_limit_bytes":512*1024**2,
            "full_packet_uncompressed_limit_bytes":None}


@pytest.mark.parametrize("changed",[{"degree":2},{"auxiliary_gauge":"raw"},
    {"dtn_phase_gauge":"global_z"},{"live_component_oracle":False},
    {"historical_authority_requested":True}])
def test_wrong_fresh_profile_rejected(changed):
    values=dict(degree=6,auxiliary_gauge="positive-h",dtn_phase_gauge="boundary_plane",live_component_oracle=True)
    values.update(changed)
    with pytest.raises(ValueError): validate_profile("p6-component",**values)


def test_old_default_budget_and_named_fresh_budget():
    args=SimpleNamespace(fresh_fixture_c1=None,research_memory_gib=None,research_wall_seconds=None)
    assert _fresh_resource(args)==(3*1024**3//2,600)
    args.fresh_fixture_c1="p6-component";args.research_memory_gib=3;args.research_wall_seconds=4500
    assert _fresh_resource(args)==(TREE_CAP_BYTES,WALL_SECONDS)
    args.fresh_fixture_c1=None
    with pytest.raises(ValueError):_fresh_resource(args)
    args.fresh_fixture_c1="p6-component";args.research_wall_seconds=600
    with pytest.raises(ValueError):_fresh_resource(args)


def test_component_binding_positive_metadata_only():
    report,checker,kwargs=_packets()
    result=validate_component_packets(report,checker,**kwargs)
    assert result["component_checker_bound"] and "component only" in result["p6_scope"]


@pytest.mark.parametrize("field,value",[("report_sha256","swapped"),("provenance_sha256","stale"),
    ("artifact_manifest_sha256","wrong"),("evidence_valid",False),("checks",[]),
    ("cells_checked",list(range(79))),("q_alias_counts_recomputed",[76,152,152,151]),
    ("negative_controls",{}),("unique_saved_members_checked",0)])
def test_stale_or_vacuous_component_checker_rejected(field,value):
    report,checker,kwargs=_packets();checker[field]=value
    with pytest.raises(ValueError):validate_component_packets(report,checker,**kwargs)


def test_missing_interior_or_p6_global_factor_rejected():
    for field,value in (("global_p6_factor_created",True),("same_system_and_carrier",False)):
        report,checker,kwargs=_packets();report["component"][field]=value
        with pytest.raises(ValueError):validate_component_packets(report,checker,**kwargs)
    report,checker,kwargs=_packets();report["component"]["actual_inventory"]["interior_rows"]-=1
    with pytest.raises(ValueError):validate_component_packets(report,checker,**kwargs)


def test_exact_shared_fixture_binding():
    report=dict(input_sha256="i",axes_nm={"x":[0,1]},mode_manifest_sha256="m",shared_fixture_configuration={"lambda":.7})
    receipt=dict(fixture_input_sha256="i",axes_nm={"x":[0,1]},physical_generator_manifest_sha256="m",shared_fixture_configuration={"lambda":.7})
    assert validate_shared_fixture(report,receipt)
    for key in report:
        altered=deepcopy(report);altered[key]=None
        with pytest.raises(ValueError):validate_shared_fixture(altered,receipt)


def test_resource_receipt_readable_complete_zero_swap_required():
    source={"head":"a"};resource=dict(tree_cap_bytes=TREE_CAP_BYTES,wall_seconds=WALL_SECONDS)
    summary=dict(classification="COMPLETED",source_state=source,sampled_process_tree_swap_peak_bytes=0,
        descendants_cleared=True,process_tree_all_status_readable=True,process_tree_all_identity_complete=True,
        sampled_process_tree_rss_peak_bytes=100000,elapsed_seconds=1)
    assert validate_resource_receipt(summary,resource,source)
    for key,value in (("process_tree_all_status_readable",False),("process_tree_all_identity_complete",False),
        ("sampled_process_tree_swap_peak_bytes",1),("elapsed_seconds",4501),("source_state",{})):
        altered=dict(summary);altered[key]=value
        with pytest.raises(ValueError):validate_resource_receipt(altered,resource,source)


def test_nearzero_is_fixed_supplement_and_catches_absolute_error():
    expected=np.zeros(532,dtype=complex);actual=expected.copy()
    assert near_zero_output_check(actual,expected,normalization=1,name="E")["passed"]
    actual[1]=2e-12
    receipt=near_zero_output_check(actual,expected,normalization=1,name="E")
    assert not receipt["passed"] and receipt["supplement_to_unchanged_operation_scale_gate"]
    assert receipt["absolute_normalized_error_upper"]==1e-12
    with pytest.raises(ValueError):near_zero_output_check(actual[:-1],expected[:-1],normalization=1,name="E")
    with pytest.raises(ValueError):near_zero_output_check(actual,expected,normalization=0,name="E")
