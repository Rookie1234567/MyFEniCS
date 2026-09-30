"""Task40 direct-reference identity and lightweight watchdog wiring contracts."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.io import load_and_resolve
from src.runners.fine_reference_preflight import (
    _reference_process_tree_snapshot,
    _task40_matched_physical_identity,
)


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "input/task40extra_0p7nm_engineering"
G0_INPUT = INPUTS / "nonseparable_g0_p6_q4_review_v1.dat"
DIRECT_INPUT = INPUTS / "nonseparable_g0_p6_direct_reference.dat"


def test_task40_identity_allows_only_direct_assembly_backend_difference():
    g0 = load_and_resolve(G0_INPUT).as_jsonable()
    direct = load_and_resolve(DIRECT_INPUT).as_jsonable()

    identity = _task40_matched_physical_identity(direct, g0)
    assert identity["identity_difference"] == {
        "discretization.assembly_backend": [
            "standard_full",
            "assembly_time_static_condensed",
        ]
    }
    assert identity["physical_sha256"] == direct["provenance"][
        "physical_model_sha256"
    ]
    assert identity["physical_sha256"] != g0["provenance"]["physical_model_sha256"]
    assert identity["normalized_physical_sections_sha256"] == g0["provenance"][
        "physical_model_sha256"
    ]
    assert len(identity["normalized_physical_sections_sha256"]) == 64

    changed = deepcopy(direct)
    changed["geometry"]["air_void_box_nm"][0] += 1.0e-6
    with pytest.raises(ValueError, match="differ beyond assembly backend"):
        _task40_matched_physical_identity(changed, g0)
    with pytest.raises(ValueError, match="direct reference must use"):
        _task40_matched_physical_identity(g0, direct)


def test_task40_direct_output_callback_is_available_before_launch():
    from src.runners.physical_balanced_output import compare_task40_direct_reference

    assert callable(compare_task40_direct_reference)


def test_task40_result_record_binds_g0_subject_and_direct_reference():
    from src.runners.physical_balanced_output import task40_reference_record_identity

    record=task40_reference_record_identity(
        '/results/g0-iterative','/results/g0-direct',
        {'g0_input_sha256':'g0-input','final_residual_npz_sha256':'g0-residual'},
        {'source_sha':'direct-source','input_sha256':'direct-input',
         'physical_sha256':'direct-physical'})
    assert record['comparison_roles']=={
        'subject':'G0 iterative','reference':'G0 same-discrete direct'}
    assert record['subject_run_directory']=='/results/g0-iterative'
    assert record['reference_run_directory']=='/results/g0-direct'
    assert record['subject_hashes']['g0_input_sha256']=='g0-input'
    assert record['reference_identity']['input_sha256']=='direct-input'


def test_task40_sample_comparison_uses_direct_values_as_reference(tmp_path):
    from src.runners.physical_balanced_output import compare_full3d_sample_archives

    candidate_dir=tmp_path/'g0_iterative'
    reference_dir=tmp_path/'g0_direct'
    candidate_dir.mkdir();reference_dir.mkdir()
    coordinates=dict(x_nm=np.array([0.5,1.5]),y_nm=np.array([0.25]),
        z_nm=np.array([1.0]),interface_z_nm=np.array([0.0,2.0]))
    arrays={
        'E_V_per_m':np.ones((1,1,2,3),dtype=np.complex128),
        'H_A_per_m':np.ones((1,1,2,3),dtype=np.complex128),
        'E_t_interface_V_per_m':np.ones((2,1,2,2),dtype=np.complex128),
        'H_t_interface_A_per_m':np.ones((2,1,2,2),dtype=np.complex128),
    }
    metadata=[]
    for directory,scale in ((candidate_dir,1.1),(reference_dir,1.0)):
        archive=directory/'full3d_reference_samples.npz'
        np.savez_compressed(archive,**coordinates,**{
            name:value*scale for name,value in arrays.items()
        })
        meta={'archive':archive.name,
            'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'interface_trace_sides':['positive_z','negative_z'],
            'array_shape_z_y_x_component':[1,1,2,3],'point_count':2}
        (directory/'full3d_reference_samples.json').write_text(json.dumps(meta))
        metadata.append(meta)

    result=compare_full3d_sample_archives(candidate_dir,reference_dir)
    assert result['reference']=='G0_same_discrete_direct'
    assert result['sample_relative_differences']['E']==pytest.approx(0.1)
    assert result['sample_relative_differences']['H']==pytest.approx(0.1)


def test_task40_modal_power_and_energy_gate_roles_use_direct_reference(tmp_path):
    from src.runners.physical_balanced_output import (
        compare_modal_files, compare_power_totals, task40_direct_reference_gate,
        task40_energy_closure,
    )

    g0=tmp_path/'g0';direct=tmp_path/'direct'
    g0.mkdir();direct.mkdir()
    mode={'side':'top','m':0,'n':0,'polarization':'s'}
    for directory,amplitude,power_value in ((g0,1.1,0.21),(direct,1.0,0.2)):
        (directory/'dtn_port_diffraction_orders_3d.json').write_text(json.dumps({
            'metrics':{},'orders':[dict(mode,R=power_value,T=0.7)]}))
        (directory/'dtn_auxiliary_amplitudes_3d.json').write_text(json.dumps([
            dict(mode,outgoing_amplitude_at_boundary=[amplitude,0.0])]))
    modal=compare_modal_files(g0,direct)
    assert modal['amplitude_relative_difference']==pytest.approx(0.1)

    subject={'port_metrics':{'R_total':0.200001,'T_total':0.7,'A_balance':0.099999},
        'volume_metrics':{'A_volume_total':0.099999}}
    reference={'port_metrics':{'R_total':0.2,'T_total':0.7,'A_balance':0.1},
        'volume_metrics':{'A_volume_total':0.1}}
    power=compare_power_totals(subject,reference)
    assert power['total_current']['R']==0.200001
    assert power['total_reference']['R']==0.2
    energy=task40_energy_closure(reference)
    assert energy['A_balance_minus_A_volume_absolute']==0.0
    gate=task40_direct_reference_gate(
        {'L2':5e-5,'scaled_curl':5e-5},
        {'sample_relative_differences':{'E':5e-5,'H':5e-5}},
        {'amplitude_relative_difference':5e-5,'power_max_absolute_difference':5e-7},
        power,energy,energy)
    assert gate['status']=='MATCHED_REFERENCE_PASS'
    assert gate['checks']['direct_reference_energy_closure'] is True
    bad_reference_energy=dict(energy,A_balance_minus_A_volume_absolute=1.1e-5)
    failed_reference=task40_direct_reference_gate(
        {'L2':5e-5,'scaled_curl':5e-5},
        {'sample_relative_differences':{'E':5e-5,'H':5e-5}},
        {'amplitude_relative_difference':5e-5,'power_max_absolute_difference':5e-7},
        power,bad_reference_energy,energy)
    assert failed_reference['status']=='MATCHED_REFERENCE_FAIL'
    assert failed_reference['checks']['direct_reference_energy_closure'] is False
    too_far=task40_direct_reference_gate(
        {'L2':1.1e-4,'scaled_curl':5e-5},
        {'sample_relative_differences':{'E':5e-5,'H':5e-5}},
        {'amplitude_relative_difference':5e-5,'power_max_absolute_difference':5e-7},
        power,energy,energy)
    assert too_far['status']=='MATCHED_REFERENCE_FAIL'


def test_task40_process_tree_sampling_disables_pss_but_preserves_tree_facts():
    observed = {}
    facts = {
        "rss_bytes": 4096,
        "swap_bytes": 0,
        "identity_complete": True,
        "identity_count": 2,
        "members": [{"pid": 42, "start_ticks": 7}],
    }

    def snapshot(parent, phase, exit_code, *, pss_sampling_policy):
        observed.update(
            parent=parent,
            phase=phase,
            exit_code=exit_code,
            pss_sampling_policy=pss_sampling_policy,
        )
        return facts

    result = _reference_process_tree_snapshot(
        snapshot, 42, "fine_reference", task40_reference=True
    )
    assert observed == {
        "parent": 42,
        "phase": "fine_reference",
        "exit_code": None,
        "pss_sampling_policy": "disabled_by_profile",
    }
    assert result is facts
    assert (result["rss_bytes"], result["swap_bytes"], result["members"][0]["pid"]) == (
        4096,
        0,
        42,
    )


def test_task40_outer_watchdog_receives_physical_memory_and_pss_policies(
    tmp_path, monkeypatch
):
    from benchmarks import subreaper_watchdog
    from src.runners import physical_diagnosis, task038_launcher

    observed = {}
    facts = {
        "classification": "COMPLETED",
        "memory_policy": "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
        "pss_sampling_policy": "disabled_by_profile",
        "process_tree_samples": [{"rss_bytes": 4096, "swap_bytes": 0, "pid": 42}],
    }

    def fake_supervise(command, directory, **kwargs):
        observed.update(command=command, directory=directory, **kwargs)
        return facts

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    monkeypatch.setattr(task038_launcher, "_physical_source_gate", lambda *_: {"clean": True})
    result = physical_diagnosis.supervise_diagnosis(
        ["worker"],
        tmp_path / "watchdog",
        phase_path=tmp_path / "phase.json",
        expected_sha="a" * 40,
        kind="task40_reference",
        remaining_seconds=43200,
        memory_policy="PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
        pss_sampling_policy="disabled_by_profile",
        time_policy="observe_only",
    )
    assert observed["memory_policy"] == "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23"
    assert observed["pss_sampling_policy"] == "disabled_by_profile"
    assert observed["time_policy"] == "observe_only"
    assert observed["wall_seconds"] == 43200
    assert result["process_tree_samples"] == facts["process_tree_samples"]
    assert result["source_after"] == {"clean": True}
