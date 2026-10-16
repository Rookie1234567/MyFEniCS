from __future__ import annotations

import hashlib
import importlib.util
import json
import shlex
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "docs/task40para_phi90_mesh_modes_direct/scripts"
RECORDS = ROOT / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
WORKER_PATH = SCRIPTS / "d13_saved_field_scale_homogeneous_worker_v2.py"
ACCOUNTING_PATH = SCRIPTS / "d13_scale_homogeneous_cutoff_accounting.py"
WORKER_SPEC = importlib.util.spec_from_file_location("task40_scale_candidate_worker_v2_test", WORKER_PATH)
assert WORKER_SPEC is not None and WORKER_SPEC.loader is not None
WORKER = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(WORKER)


class _SerialComm:
    def allreduce(self, value, op=None):
        return value


class _PetscComm:
    def tompi4py(self):
        return _SerialComm()


class _Vec:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.complex128)

    def getOwnershipRange(self):
        return 0, self.values.size

    def getArray(self, readonly=True):
        assert readonly is True
        return self.values

    def getComm(self):
        return _PetscComm()


def _complex_json(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _json_safe(value):
    if isinstance(value, complex):
        return _complex_json(value)
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v2_wrapper_capture_accounting_attach_chain_uses_same_boundary_units():
    import d13_cutoff_stage_accounting as legacy_accounting

    import src.solvers.dtn_port_3d as dtn_port

    original_vec = dtn_port._vec_nonzero_owned_entries
    original_combine = dtn_port._combine_owned_entries
    original_legacy_route = legacy_accounting.route_cutoff_accounting
    exact_keys = [
        ("top", -4, 0, "p"),
        ("top", 0, 0, "s"),
        ("top", 4, 0, "p"),
        ("bottom", -4, 0, "p"),
        ("bottom", 0, 0, "s"),
        ("bottom", 4, 0, "p"),
    ]
    saved_total_raw = 2.5e27 + 1.0e27j
    boundary_phase = 4.0e-29 + 0j
    saved_total_boundary = saved_total_raw * boundary_phase
    saved_incident_raw = 0.5e27 - 0.2e27j
    saved_outgoing_boundary = 0.03 - 0.01j
    capture_calls = []
    v4_modes = []

    class _BaseWorker:
        @staticmethod
        def _cutoff_stage_capture(*, token):
            capture_calls.append(token)
            import d13_cutoff_stage_accounting as active_accounting

            import src.solvers.dtn_port_3d as active_dtn

            mode_results = []
            for index, key in enumerate(exact_keys):
                scale = 1.0 + 0.1 * index
                raw_components = (
                    (
                        np.arange(4, dtype=np.int64),
                        np.asarray(
                            [
                                (2.0e-30 + 0.5e-30j) * scale,
                                (4.0e-43 - 1.0e-43j) * scale,
                                (3.0e-35 + 0j) * scale,
                                (0.5e-30 - 0.25e-30j) * scale,
                            ],
                            dtype=np.complex128,
                        ),
                    ),
                    (
                        np.arange(4, dtype=np.int64),
                        np.asarray(
                            [
                                (-0.8e-30 + 0.2e-30j) * scale,
                                (2.0e-43 + 3.0e-43j) * scale,
                                (5.0e-35 - 1.0e-35j) * scale,
                                (0.4e-30 + 0.1e-30j) * scale,
                            ],
                            dtype=np.complex128,
                        ),
                    ),
                )
                projection_coefficients = (0.75 + 0.2j, -0.35 + 0.1j)
                coupling_coefficients = (-0.2 + 0.3j, 0.55 - 0.15j)
                filtered_components = []
                for _rows, values in raw_components:
                    rows, kept = active_dtn._vec_nonzero_owned_entries(
                        _Vec(values), relative_tol=1.0e-13
                    )
                    filtered_components.append((rows, kept))
                projection_rows, projection_values = active_dtn._combine_owned_entries(
                    tuple(filtered_components),
                    projection_coefficients,
                    comm=_SerialComm(),
                    relative_tol=1.0e-13,
                )
                coupling_rows, coupling_values = active_dtn._combine_owned_entries(
                    tuple(filtered_components),
                    coupling_coefficients,
                    comm=_SerialComm(),
                    relative_tol=1.0e-13,
                )
                storage = np.asarray(
                    [
                        1.0e27 + 0.2e27j,
                        -0.5e27 + 0.7e27j,
                        0.3e27 - 0.1e27j,
                        0.8e27 + 0.4e27j,
                    ],
                    dtype=np.complex128,
                )
                projection_route = active_accounting.route_cutoff_accounting(
                    raw_components,
                    tuple(filtered_components),
                    projection_coefficients,
                    projection_rows,
                    projection_values,
                    storage,
                    conjugate_combined_values=True,
                )
                coupling_route = active_accounting.route_cutoff_accounting(
                    raw_components,
                    tuple(filtered_components),
                    coupling_coefficients,
                    coupling_rows,
                    coupling_values,
                    storage,
                    conjugate_combined_values=False,
                )
                H = 2.5
                old_boundary = saved_total_boundary + (0.01 + 0.004j)
                old_n = old_boundary * H / boundary_phase
                new_projection = {
                    "after_merged_cutoff_N_complex": projection_route[
                        "after_production_merged_cutoff_dot_complex"
                    ],
                    "saved_total_auxiliary_projection_complex": saved_total_raw,
                    "saved_incident_projection_complex_separate": saved_incident_raw,
                    "saved_outgoing_boundary_amplitude_complex_separate": saved_outgoing_boundary,
                    "H": H,
                    "boundary_phase_P": boundary_phase,
                }
                mode_results.append(
                    {
                        "exact_signed_mode_key": list(key),
                        "component_stage_records": [
                            {
                                "production_rows_values_sha256": f"fake-{index}",
                                "production_entry_count": 8,
                            }
                        ],
                        "production_stage_two_routes": {
                            "projection": projection_route,
                            "coupling": coupling_route,
                        },
                        "projection": new_projection,
                    }
                )
                v4_modes.append(
                    {
                        "exact_signed_mode_key": list(key),
                        "component_stage_records": [{"legacy_fixture": True}],
                        "production_stage_two_routes": {
                            "projection": {"legacy_fixture": True},
                            "coupling": {"legacy_fixture": True},
                        },
                        "projection": {
                            "merged_cut_boundary_total_amplitude_complex": _complex_json(
                                old_boundary
                            ),
                            "after_merged_cutoff_N_complex": _complex_json(old_n),
                            "saved_total_auxiliary_projection_complex": _complex_json(
                                saved_total_raw
                            ),
                        },
                    }
                )
            return {
                "unchanged_production_cutoff": {"historical_floor": 1.0e-30},
                "six_exact_signed_key_results": mode_results,
            }

    base_worker = _BaseWorker()
    saved_capture = WORKER._install_candidate_capture(base_worker)
    try:
        capture_result = base_worker._cutoff_stage_capture(token="one-call")
    finally:
        base_worker._cutoff_stage_capture = saved_capture

    assert capture_calls == ["one-call"]  # exact one call to the saved original capture
    assert dtn_port._vec_nonzero_owned_entries is original_vec
    assert dtn_port._combine_owned_entries is original_combine
    assert legacy_accounting.route_cutoff_accounting is original_legacy_route

    candidate_report = {
        "cases": [
            {
                "run_directory_id": "saved-y2-run",
                "diagnostic_only_cutoff_stage_capture": _json_safe(capture_result),
            }
        ]
    }
    v4_report = {
        "cases": [
            {
                "run_directory_id": "saved-y2-run",
                "carrier_comparison_gate": {"status": "FAIL"},
                "qualification": "NO_CARRIER_COMPARISON",
                "diagnostic_only_cutoff_stage_capture": {
                    "six_exact_signed_key_results": v4_modes
                },
            }
        ]
    }
    WORKER._attach_frozen_v4_comparison(candidate_report, v4_report)

    candidate_case = candidate_report["cases"][0]
    attached_capture = candidate_case["diagnostic_only_cutoff_stage_capture"]
    attached_modes = attached_capture["six_exact_signed_key_results"]
    assert len(attached_modes) == 6
    for mode in attached_modes:
        routes = mode["candidate_scale_homogeneous_stage_two_routes"]
        assert "after_candidate_merged_cutoff_dot_complex" in routes["coupling"]
        assert "after_production_merged_cutoff_dot_complex" not in routes["coupling"]
        comparison = mode["candidate_vs_legacy_and_untruncated"]
        raw_saved = comparison["saved_total_auxiliary_projection_raw_complex"]
        boundary_saved = comparison["saved_total_auxiliary_boundary_complex"]
        assert WORKER._decode_complex(raw_saved) == saved_total_raw
        assert WORKER._decode_complex(boundary_saved) == saved_total_boundary
        assert comparison["comparison_space"] == "boundary_amplitude"
        assert comparison["legacy_v4_boundary_minus_saved_total_boundary_abs"] == pytest.approx(
            abs(0.01 + 0.004j)
        )
        candidate_projection = WORKER._decode_complex(
            routes["projection"]["after_candidate_merged_cutoff_dot_complex"]
        )
        saved_projection = candidate_projection / 2.5 * boundary_phase
        assert comparison["candidate_boundary_minus_saved_total_boundary_abs"] == pytest.approx(
            abs(saved_projection - saved_total_boundary)
        )
        assert comparison["saved_incident_projection_complex_separate"] == _complex_json(
            saved_incident_raw
        )
        assert comparison["saved_outgoing_boundary_amplitude_complex_separate"] == _complex_json(
            saved_outgoing_boundary
        )
        assert "legacy_v4_boundary_minus_saved_total_abs" not in comparison
    assert candidate_case["original_v4_carrier_gate"]["status"] == "FAIL"
    assert candidate_case["qualification"].startswith("DIAGNOSTIC_ONLY")


def test_v2_contract_marks_modified_source_changed_but_preserves_legacy_default():
    contract_path = RECORDS / "d13_saved_field_scale_homogeneous_cutoff_contract_v2.json"
    sidecar_path = RECORDS / "d13_saved_field_scale_homogeneous_cutoff_launch_v2.json"
    contract = json.loads(contract_path.read_text())
    sidecar = json.loads(sidecar_path.read_text())
    source_path = ROOT / "src/solvers/dtn_port_3d.py"
    worker_path = SCRIPTS / "d13_saved_field_scale_homogeneous_worker_v2.py"
    supervisor_path = SCRIPTS / "d13_saved_field_scale_homogeneous_supervisor_v2.py"

    assert sidecar["contract_sha256"] == _sha(contract_path)
    assert sidecar["worker_sha256"] == _sha(worker_path)
    assert sidecar["supervisor_sha256"] == _sha(supervisor_path)
    assert contract["execution_authorized"] is False
    assert sidecar["execution_authorized"] is False
    assert contract["analysis_source_file_sha256"]["src/solvers/dtn_port_3d.py"] != _sha(source_path)
    assert "src/solvers/dtn_port_3d.py" not in contract["analysis_source_files_identical_to_y2_source"]
    source_change = contract["candidate_source_changes"]
    assert source_change["tracked_path"] == "src/solvers/dtn_port_3d.py"
    assert source_change["legacy_default_behavior"] == "PRESERVED"
    assert sidecar["output_directory"].endswith("_v2")
    assert Path(sidecar["output_directory"]).name.endswith("_v2")
    with pytest.raises(ValueError, match="candidate source hash changed"):
        WORKER._verify_candidate_contract(
            contract_path, contract, require_execution_authorized=False
        )
    supervisor = WORKER._load_module(
        "task40_scale_candidate_supervisor_v2_test", supervisor_path
    )
    supervisor._validate_worker_command(
        sidecar["worker_command_argv"],
        contract_path.resolve(),
        Path(sidecar["report_path"]).resolve(),
        contract,
    )
    exec_lines = [
        line.strip()[5:].split(" >> ", 1)[0]
        for line in sidecar["shell_command"].splitlines()
        if line.strip().startswith("exec ")
    ]
    assert len(exec_lines) == 1
    assert shlex.split(exec_lines[0]) == sidecar["exec_argv"]
