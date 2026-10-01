"""Centered receipt/output contracts only; no PDE/factor is launched here."""
import copy
import hashlib
import json

import numpy as np
import pytest

from src.solvers import y_orbit_centered_evidence as evidence
from benchmarks import run_y_orbit_sparse_probe as runner


def _output_fixture():
    values = {}
    for name, scale in (("plane_total_auxiliary","mode_local_amplitude_scale"),
        ("plane_outgoing_auxiliary","mode_local_amplitude_scale"),("plane_electric","plane_electric_scale"),
        ("plane_magnetic","plane_magnetic_scale"),("direct_plane_outgoing_power_diagnostic","mode_power_operation_scale")):
        values["regular_generic_"+name] = np.zeros((532,3) if "electric" in name or "magnetic" in name else 532)
        values["regular_generic_"+scale] = np.ones(532)
    return values


def test_per_mode_scale_cannot_hide_weak_channel_behind_large_modes():
    exact = _output_fixture(); candidate = copy.deepcopy(exact)
    exact["regular_generic_plane_total_auxiliary"][1:] = 1e12
    candidate["regular_generic_plane_total_auxiliary"][1:] = 1e12
    candidate["regular_generic_plane_total_auxiliary"][0] = 1e-8
    checks = evidence.compare_mode_evidence(candidate.__getitem__,exact.__getitem__,"regular_generic")
    assert checks["plane_total_auxiliary"]["passed"] is False
    assert checks["plane_total_auxiliary"]["worst_mode_index"] == 0


def test_zero_local_scale_has_no_invented_absolute_floor():
    exact = _output_fixture(); candidate = copy.deepcopy(exact)
    exact["regular_generic_mode_local_amplitude_scale"][0] = 0
    candidate["regular_generic_mode_local_amplitude_scale"][0] = 0
    assert all(c["passed"] for c in evidence.compare_mode_evidence(candidate.__getitem__,exact.__getitem__,"regular_generic").values())
    candidate["regular_generic_plane_total_auxiliary"][0] = 1e-100
    with pytest.raises(ValueError,match="zero local"):
        evidence.compare_mode_evidence(candidate.__getitem__,exact.__getitem__,"regular_generic")


def test_every_mode_is_required_even_for_cancellation_zero_outputs():
    values = _output_fixture()
    values["regular_generic_plane_electric"] = np.zeros((531,3))
    with pytest.raises(ValueError,match="complete centered"):
        evidence.compare_mode_evidence(values.__getitem__,values.__getitem__,"regular_generic")


def _write(path,value):
    path.write_text(json.dumps(value,sort_keys=True,allow_nan=False))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authority_fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,"ROOT",tmp_path); monkeypatch.setattr(runner,"ARTIFACT_ROOT",tmp_path)
    source={"head":"f"*40,"branch":"task40extra_dot_parallel_cloud","dirty":"","files_sha256":{}}
    environment={"qualification_manifest_sha256":"abi"}
    report={"status":"CENTERED_DENSE_AUTHORITY_PASS","dtn_phase_gauge":"boundary_plane","degree":2,
       "source_clean_unchanged":True,"source":source,"environment":environment,
       "source_names":list(evidence.SOURCES),"regular_sources":dict.fromkeys(evidence.SOURCES,{}),
       "notched_sources":dict.fromkeys(evidence.SOURCES,{}),"identity":evidence.COMPONENT_IDENTITY,"artifacts":{}}
    # Exercise required-inventory generation without running numerical code.
    probe=copy.deepcopy(report)
    # The required keys are independently enumerable in this contract fixture.
    keys={"A0_original","A_notch_original","independent_storage_rows","actual_interior_positions"}
    keys|={"full_mpc_"+n for n in ("slaves","masters","coefficients","offsets")}
    suffixes=("rhs_storage","solution_storage","original_action","volume_action","coupling_action",
      "auxiliary_ports","projection","normalization_h","recovered_field","plane_total_auxiliary",
      "plane_outgoing_auxiliary","plane_incident_projections","direct_plane_outgoing_power_diagnostic",
      "plane_electric","plane_magnetic","mode_local_amplitude_scale","plane_electric_scale",
      "plane_magnetic_scale","mode_power_operation_scale")
    for n in evidence.SOURCES:
        keys|={n+"_rhs","A0_direct_"+n,"A0_modal_"+n,"notch_direct_"+n,"notch_iterative_"+n}
        keys|={p+n+"_"+s for p in ("direct_regular_","regular_","direct_notch_","notch_") for s in suffixes}
    report["artifacts"]={k:{"fixture_only":True} for k in keys}
    assert set(evidence.require_centered_dense_inventory(report)) == keys
    path=tmp_path/"pilot_report.json";digest=_write(path,report)
    provenance_hash=_write(tmp_path/"provenance.json",{"source":source,"environment":environment})
    watched={"classification":"COMPLETED","source_state":source,"sampled_process_tree_swap_peak_bytes":0,
      "descendants_cleared":True,"process_tree_all_identity_complete":True,"process_tree_all_status_readable":True,
      "sampled_process_tree_rss_peak_bytes":123}
    _write(tmp_path/"summary.json",watched)
    d=tmp_path/"checker_supervision";d.mkdir();whash=_write(d/"summary.json",watched)
    checker={"gate_pass":True,"evidence_valid":True,"report_sha256":digest,"provenance_sha256":provenance_hash,
      "artifact_manifest_sha256":evidence.digest_json(report["artifacts"]),"source":source,"environment":environment,
      "identity":report["identity"],"degree":2,
      "checker_watchdog_receipt":{"path":"checker_supervision/summary.json","sha256":whash}}
    _write(tmp_path/"independent_checker.json",checker)
    return path,digest,source,environment,checker,probe


def test_centered_authority_binds_complete_specific_checked_receipt(tmp_path,monkeypatch):
    p,d,s,e,_,_= _authority_fixture(tmp_path,monkeypatch)
    assert runner.SavedCenteredDenseP2Authority(p,d,s,e).receipt["dtn_phase_gauge"]=="boundary_plane"


@pytest.mark.parametrize("field",["report_sha256","provenance_sha256","artifact_manifest_sha256","source","environment","identity","degree"])
def test_stale_or_wrong_centered_checker_is_rejected(tmp_path,monkeypatch,field):
    p,d,s,e,c,_= _authority_fixture(tmp_path,monkeypatch)
    c[field]="wrong";_write(tmp_path/"independent_checker.json",c)
    with pytest.raises(RuntimeError,match="identity has not passed"):
        runner.SavedCenteredDenseP2Authority(p,d,s,e)


def test_empty_centered_inventory_is_rejected_before_factor(tmp_path,monkeypatch):
    _,_,_,_,_,probe= _authority_fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match="complete required"):
        evidence.require_centered_dense_inventory(probe)


def test_source_component_reuse_requires_exact_dependency_bytes(tmp_path,monkeypatch):
    p=tmp_path/"kernel.py";p.write_text("fixed")
    expected={"kernel.py":hashlib.sha256(p.read_bytes()).hexdigest()}
    monkeypatch.setattr(evidence,"COMPONENT_SOURCE_FILES",expected)
    monkeypatch.setattr(evidence,"COMPONENT_RECEIPT_FILES",{})
    assert evidence.verify_component_sources(tmp_path)["exact_unchanged_files"]==expected
    p.write_text("changed")
    with pytest.raises(RuntimeError,match="dependency changed"):
        evidence.verify_component_sources(tmp_path)


@pytest.mark.parametrize("status",["controlled_stop_global_output_inconsistent","controlled_stop_global_output_unrepresentable"])
def test_required_output_stop_is_logged_and_never_qualifies(status):
    events=[]
    packet={"status":status,"finite_plane_mode_count":532,"global_output_failure":{"mode_index":4,"reason":"fixed failure"}}
    with pytest.raises(ValueError,match="required centered output contract stopped"):
        evidence.require_output_packet(packet,label="physical",event=lambda name,data:events.append((name,data)))
    assert events[0][1]["passed"] is False
    assert events[0][1]["packet"]["global_output_failure"]["reason"]=="fixed failure"


def test_missing_actual_component_receipt_cannot_be_replaced_by_context_claim(tmp_path,monkeypatch):
    monkeypatch.setattr(evidence,"COMPONENT_SOURCE_FILES",{})
    with pytest.raises(FileNotFoundError):
        evidence.verify_component_sources(tmp_path)


@pytest.mark.parametrize("target",["field","rhs"])
def test_swapped_passing_native_packet_cannot_bind_a_different_solver_vector(target):
    independent=np.asarray([0,2]);field=np.asarray([1,0,3],dtype=complex);rhs=np.asarray([4,0,6],dtype=complex)
    assert evidence.bind_native_packet(field,rhs,np.asarray([1,3]),np.asarray([4,6]),independent)
    if target=="field": field[0]+=1
    else: rhs[2]+=1
    with pytest.raises(ValueError,match="detached"):
        evidence.bind_native_packet(field,rhs,np.asarray([1,3]),np.asarray([4,6]),independent)


def test_component_actual_hash_packet_precedes_unchanged_identity_failure():
    from types import SimpleNamespace
    entries=[SimpleNamespace(coupling_rows=np.asarray([0]),projection_rows=np.asarray([0])) for _ in range(532)]
    actual={**evidence.COMPONENT_IDENTITY,"assembly_context_sha256":"different"}
    carrier=SimpleNamespace(entries=entries,mode_manifest_sha256=actual["assembly_mode_manifest_sha256"],
         assembly_context_sha256="different",assembly_context={"MPC":{"hash":"actual"},"gauss":{"degree":19},"source_sha256":{}})
    bundle={**actual,"dtn_phase_gauge":"boundary_plane","mode_sha256":actual["physical_generator_manifest_sha256"],
      "dtn_action":SimpleNamespace(carrier=carrier),"cfg":SimpleNamespace(as_jsonable=lambda:{"fixture":"actual"})}
    events=[]
    with pytest.raises(RuntimeError,match="identity changed"):
        evidence.centered_identity(bundle,event=lambda name,packet:events.append((name,packet)))
    assert events[0][0]=="component_identity_before_assert"
    assert events[0][1]["mismatch_keys"]==["assembly_context_sha256"]
    assert events[0][1]["actual_discrete_context"]["MPC"]["hash"]=="actual"
    assert events[0][1]["diagnostic_only_acceptance_unchanged"] is True
