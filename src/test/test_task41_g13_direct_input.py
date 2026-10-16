from __future__ import annotations

import hashlib
import copy
import json
from dataclasses import replace
from pathlib import Path
import time

import numpy as np
import pytest

from src.common.modes_3d import outgoing_port_modes_3d
from src.geometry.task41_phi90_profile import (
    TASK41_G13_A1_RUN_ID,
    TASK41_G13_GEOMETRY_IDENTITY,
    TASK41_MODEL_ID,
    TASK41_SI_INDEX_BY_WAVELENGTH_NM,
    TASK41_MUMPS_EXACT_ICNTL,
    task41_incident_eh_fields,
    task41_direct_summary_errors,
    task41_payload_errors,
)
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/task41extra_phi90_p50x50_g17x20/g13_p6_direct_a1.dat"


def _payload():
    return load_and_resolve(INPUT).as_jsonable()


def test_task41_g13_resolves_new_physics_mesh_and_mode_inventory():
    payload = _payload()
    assert task41_payload_errors(payload) == []
    cfg = simulation_config_3d_from_normalized(payload)

    assert cfg.period_x == 50.0
    assert cfg.period_y == 50.0
    assert cfg.grating_width_x == 17.0
    assert cfg.grating_width_y == 20.0
    assert cfg.grating_height == 120.0
    requested_counts = tuple(cfg.mesh_axis_cell_counts_requested)
    assert requested_counts == (10, 10, 14)
    assert payload["discretization"]["mesh_axis_cell_counts"] == [10, 10, 14]
    # This is the production axis planner used by build_hexahedral_mesh. The
    # generic cfg.mesh_cells property is only the h-based fallback (5, 5, 14)
    # when an exact axis plan is present.
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    axis_plan = _stage4_axis_plan(cfg, comm_size=1)
    assert tuple(axis_plan.mesh_cells_resolved) == requested_counts
    assert tuple(
        len(axis) - 1
        for axis in (axis_plan.x_values, axis_plan.y_values, axis_plan.z_values)
    ) == requested_counts
    assert cfg.air_void_box_nm is None
    assert cfg.cell_notch is None
    assert payload["geometry"]["geometry_identity"] == TASK41_G13_GEOMETRY_IDENTITY
    assert payload["materials"]["n_substrate"] == list(
        TASK41_SI_INDEX_BY_WAVELENGTH_NM[13.5]
    )
    assert payload["materials"]["n_grating"] == list(
        TASK41_SI_INDEX_BY_WAVELENGTH_NM[13.5]
    )
    assert cfg.grating_width_x * cfg.grating_width_y * cfg.grating_height == 40800.0
    assert cfg.period_x * cfg.period_y * cfg.substrate_thickness == 25000.0
    assert 15.0 in payload["discretization"]["mesh_axis_y_values"]
    assert 35.0 in payload["discretization"]["mesh_axis_y_values"]

    direction = cfg.direction_vector
    wavevector = cfg.wavevector
    electric = cfg.incident_amplitude * cfg.polarization_vector
    assert np.isclose(direction[0], 0.0, atol=1.0e-14)
    assert direction[1] > 0.0 and direction[2] < 0.0
    assert np.isclose(wavevector[0], 0.0, atol=1.0e-14)
    assert wavevector[1].real > 0.0 and wavevector[2].real < 0.0
    assert np.allclose(electric, (-1.0, 0.0, 0.0), atol=1.0e-14)
    incident_fields = task41_incident_eh_fields(cfg)
    magnetic_si = np.asarray(
        [complex(*pair) for pair in incident_fields["incident_magnetic_field_A_per_m"]]
    )
    assert magnetic_si[1].real > 0.0 and magnetic_si[2].real > 0.0
    assert np.isclose(
        np.linalg.norm(magnetic_si),
        cfg.electric_field_scale_V_per_m / 376.730313668,
        rtol=2.0e-6,
    )
    assert payload["derived"]["incident_magnetic_field_A_per_m"] == (
        incident_fields["incident_magnetic_field_A_per_m"]
    )
    assert abs(cfg.floquet_phase_y - 1.0) > 0.1

    modes = outgoing_port_modes_3d(cfg)
    assert modes
    assert {mode.side for mode in modes} == {"top", "bottom"}
    assert any(mode.m != 0 or mode.n != 0 for mode in modes)
    assert all(np.all(np.isfinite(mode.k_vector)) for mode in modes)
    assert all(np.all(np.isfinite(mode.e_vector)) for mode in modes)
    assert all(np.all(np.isfinite(mode.h_vector)) for mode in modes)


def test_task41_worker_contract_rejects_physics_and_identity_drift():
    payload = _payload()
    assert payload["run_id"] == TASK41_G13_A1_RUN_ID
    assert task41_payload_errors(payload) == []

    wrong_geometry = dict(payload)
    wrong_geometry["geometry"] = dict(payload["geometry"], grating_width_y_nm=25.0)
    assert any(
        "geometry.grating_width_y_nm" in error
        for error in task41_payload_errors(wrong_geometry)
    )

    wrong_identity = dict(payload, run_id="task40_stale_ny8_case")
    assert "run_id is not a registered Task41 case" in task41_payload_errors(
        wrong_identity
    )
    assert task41_payload_errors(dict(payload, model_id="another_model")) == []


def test_task41_supervised_worker_contract_checks_resolved_physics(tmp_path, monkeypatch):
    from src.io.execution_plan import METHOD_ADAPTERS
    from src.runners import task41_p0_contract
    from src.runners.task038_input_worker import validate_worker_contract

    monkeypatch.setenv("TASK41_P0_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK41_P0_CONTRACT_PATH", str(tmp_path / "contract.json"))
    monkeypatch.setenv("TASK41_P0_CONTRACT_SHA256", "f" * 64)

    payload = _payload()
    input_bytes = INPUT.read_bytes()
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    source_sha = "a" * 40

    def contract_errors(resolved):
        resolved_bytes = json.dumps(
            resolved, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
        resolved_path = tmp_path / "resolved_config.json"
        manifest_path = tmp_path / "run_manifest.json"
        resolved_path.write_bytes(resolved_bytes)
        (tmp_path / "input_original.dat").write_bytes(input_bytes)
        method = resolved["method"]["kind"]
        adapter = METHOD_ADAPTERS[method]
        manifest_path.write_text(
            json.dumps(
                {
                    "input_path": resolved["provenance"]["source_path"],
                    "mpi_size": 1,
                    "method": method,
                    "resolved_method_adapter": adapter,
                    "input_sha256": input_sha,
                    "physical_model_sha256": resolved["provenance"][
                        "physical_model_sha256"
                    ],
                    "source_sha": source_sha,
                    "resolved_config_sha256": resolved_sha,
                    "output_directory": str(tmp_path.resolve()),
                    "numerical_output_directory": str(
                        (tmp_path / "numerical_output").resolve()
                    ),
                    "model_id": resolved["model_id"],
                    "run_id": resolved["run_id"],
                    "comparison_group": resolved["comparison_group"],
                    "solver": resolved["solver"],
                    "requested_modes": None,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        contract = {
            "source": {"sha": source_sha},
            "case": {
                "input_sha256": input_sha,
                "physical_model_sha256": resolved["provenance"][
                    "physical_model_sha256"
                ],
                "resolved_config_sha256": resolved_sha,
                "model_id": resolved["model_id"],
                "run_id": resolved["run_id"],
                "method": method,
                "mpi_size": 1,
            },
        }
        monkeypatch.setattr(
            task41_p0_contract,
            "require_task41_p0_contract",
            lambda *_args, **_kwargs: (contract, "f" * 64),
        )
        monkeypatch.setattr(
            task41_p0_contract,
            "load_task41_p0_fixed_window",
            lambda *_args, **_kwargs: object(),
        )
        return validate_worker_contract(
            resolved_config=resolved_path,
            manifest=manifest_path,
            expected_input_sha256=input_sha,
            expected_physical_model_sha256=resolved["provenance"][
                "physical_model_sha256"
            ],
            expected_source_sha=source_sha,
            expected_mpi_size=1,
            expected_method=method,
            expected_adapter=adapter,
            expected_output_directory=tmp_path,
            expected_resolved_config_sha256=resolved_sha,
            actual_mpi_size=1,
        )

    assert contract_errors(payload) == []
    changed = dict(payload)
    changed["geometry"] = dict(payload["geometry"], grating_width_y_nm=25.0)
    assert any("geometry.grating_width_y_nm" in error for error in contract_errors(changed))


def test_task41_task038_worker_dispatches_to_shared_full3d_direct_adapter(
    tmp_path, monkeypatch
):
    from src.runners import task038_full3d_direct, task038_input_worker

    payload = _payload()
    calls = []

    def fake_direct(resolved_payload, run_directory):
        calls.append((resolved_payload, run_directory))
        return {"passed": True, "errors": [], "summary": {"case_status": "completed"}}

    monkeypatch.setattr(task038_full3d_direct, "run_full3d_direct", fake_direct)
    exit_code, errors = task038_input_worker._dispatch_resolved_payload(
        payload,
        expected_method="full3d_direct",
        output_directory=tmp_path,
    )
    assert (exit_code, errors) == (0, [])
    assert calls == [(payload, tmp_path)]


def test_task41_static_condensation_passes_task_specific_builder_flags(
    monkeypatch,
):
    from src.solvers import dtn_port_3d

    payload = _payload()
    cfg = simulation_config_3d_from_normalized(payload)
    captured = {}

    def fake_builder(compiled_form, function_space, cell_tags, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        dtn_port_3d,
        "build_unconstrained_assembly_time_condensation",
        fake_builder,
    )
    result = dtn_port_3d._build_stage4_assembly_time_condensation(
        object(), object(), object(), cfg=cfg, mpc=object()
    )
    assert result is not None
    assert captured["sum_duplicate_cell_integrals"] is True
    assert captured["strict_local_checks"] is True
    assert captured["share_identity_cache"] is True
    assert captured["preserve_exact_geometry"] is True

    captured.clear()
    ordinary_cfg = replace(cfg, geometry_identity=None)
    dtn_port_3d._build_stage4_assembly_time_condensation(
        object(), object(), object(), cfg=ordinary_cfg, mpc=object()
    )
    assert captured["sum_duplicate_cell_integrals"] is False
    assert captured["strict_local_checks"] is False
    assert captured["share_identity_cache"] is False
    assert captured["preserve_exact_geometry"] is False


def test_task41_direct_profile_pins_exact_mumps_controls(monkeypatch):
    from mpi4py import MPI

    from src.solvers import common_3d_solve

    cfg = simulation_config_3d_from_normalized(_payload())
    monkeypatch.setattr(common_3d_solve, "_has_petsc_package", lambda _name: True)
    monkeypatch.setattr(common_3d_solve, "_apply_global_petsc_options", lambda *_: None)

    options, selected, disabled = common_3d_solve._prepare_direct_lu_options_for_comm(
        MPI.COMM_SELF, cfg
    )
    assert disabled is None
    assert selected == "mumps"
    assert options["pc_factor_mat_solver_type"] == "mumps"
    for index, value in TASK41_MUMPS_EXACT_ICNTL.items():
        assert options[f"mat_mumps_icntl_{index}"] == value
    assert "mat_mumps_icntl_14" not in options

    class Factor:
        @staticmethod
        def getMumpsIcntl(index):
            return TASK41_MUMPS_EXACT_ICNTL[index]

    class PC:
        @staticmethod
        def getFactorSolverType():
            return "mumps"

        @staticmethod
        def getFactorMatrix():
            return Factor()

    class KSP:
        @staticmethod
        def getPC():
            return PC()

    readback = common_3d_solve._mumps_control_readback(
        KSP(), TASK41_MUMPS_EXACT_ICNTL
    )
    assert readback["pass"] is True
    assert readback["observed_icntl"] == {
        str(index): value for index, value in TASK41_MUMPS_EXACT_ICNTL.items()
    }


def _task41_authority_fixture(tmp_path, *, residual_values=(6e-9 + 0j, 8e-9 + 0j)):
    output = tmp_path / "numerical_output"
    output.mkdir(parents=True)
    rhs = np.asarray([1.0 + 0j, 0.0 + 0j], dtype="<c16")
    residual = np.asarray(residual_values, dtype="<c16")
    recovered_field = np.asarray([1.0 + 0j, 2.0 + 0j], dtype="<c16")
    slave_rows = np.asarray([1], dtype=np.int32)
    rank_path = output / "task41_native_full_a6_rank_00000.npz"
    np.savez(
        rank_path,
        rhs=rhs,
        residual=residual,
        recovered_field=recovered_field,
        mpc_slave_local_rows=slave_rows,
    )
    rank_record = {
        "rank": 0,
        "owned_dof_count": 2,
        "rhs_norm_squared": float(np.vdot(rhs, rhs).real),
        "residual_norm_squared": float(np.vdot(residual, residual).real),
        "residual_max_abs": float(np.max(np.abs(residual))),
        "rank_artifact_file": rank_path.name,
        "rank_artifact_sha256": hashlib.sha256(rank_path.read_bytes()).hexdigest(),
        "rank_artifact_bytes": rank_path.stat().st_size,
        "recovered_field_sha256": hashlib.sha256(
            np.ascontiguousarray(recovered_field).view(np.uint8)
        ).hexdigest(),
        "vector_bytes_local": {
            "rhs": rhs.nbytes,
            "zeroed_solution": recovered_field.nbytes,
            "residual": residual.nbytes,
            "recovered_field": recovered_field.nbytes,
        },
        "action_bytes_local": {
            "volume_retained": 0,
            "volume_last_apply_temporary": 0,
            "dtn_retained": 0,
            "dtn_apply_workspace": 0,
        },
        "tracked_workspace_bytes_local": int(
            rhs.nbytes + residual.nbytes + 2 * recovered_field.nbytes
        ),
    }
    residual_norm = float(np.linalg.norm(residual))
    native = {
        "schema": "task41.native_full_a6_residual.v1",
        "operator": "A_volume_plus_dynamic_DtN",
        "fullspace_mpc_volume_action": True,
        "fullspace_dtn_action": True,
        "field_representation": "recovered_physical_fe_field_after_mpc_backsubstitution",
        "action_input_representation": (
            "recovered_field_copy_with_owned_mpc_slave_entries_zeroed"
        ),
        "action_input_mpc_slave_entries_zeroed": True,
        "mpi_size": 1,
        "global_dof_count": 2,
        "mode_count": 1,
        "mode_manifest_sha256": "a" * 64,
        "rank_local_records": [rank_record],
        "rhs_norm": 1.0,
        "residual_norm": residual_norm,
        "relative_residual": residual_norm,
        "elapsed_seconds": 0.01,
        "residual_max_abs": float(np.max(np.abs(residual))),
    }
    digest = hashlib.sha256(
        json.dumps(native, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    native["record_sha256"] = digest
    native["artifact_file"] = "task41_native_full_a6_residual.json"
    (output / native["artifact_file"]).write_text(
        json.dumps(
            {key: value for key, value in native.items() if key != "artifact_file"},
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    def save_stage_record(filename, record):
        digest = hashlib.sha256(
            json.dumps(
                record, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        (output / filename).write_text(
            json.dumps(
                {**record, "record_sha256": digest},
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return {**record, "record_sha256": digest, "artifact_file": filename}

    expected_icntl = {
        str(index): value for index, value in TASK41_MUMPS_EXACT_ICNTL.items()
    }
    admission = save_stage_record(
        "task41_mumps_symbolic_admission.json",
        {
            "schema": "task41.mumps_symbolic_admission.v1",
            "status": "ADMISSIBLE",
            "mpi_size": 1,
            "symbolic_calls": 1,
            "numeric_called": False,
            "probe_factor_released_before_ksp_setup": True,
            "final_admission_sample_after_probe_release": True,
            "exact_icntl_expected": expected_icntl,
            "symbolic_probe_control_readback": expected_icntl,
            "symbolic_info": {"infog": {"1": 0, "16": 10, "17": 12}},
            "post_release_resource": {
                "job_no_swap": True,
                "memory_authority_bytes": 1 << 30,
                "process_tree": {
                    "all_status_readable": True,
                    "rss_bytes": 1 << 30,
                    "swap_bytes": 0,
                },
            },
            "post_release_memory_envelope": {
                "memory_policy": "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
                "cgroup_limits": [],
                "launch_cap_bytes": 1 << 40,
                "reserve_bytes": 64 * 1024**3,
            },
            "decision_errors": [],
        },
    )
    numeric_stage = save_stage_record(
        "task41_mumps_numeric_stage.json",
        {
            "schema": "task41.mumps_numeric_stage.v1",
            "status": "COMPLETED",
            "numeric_called": True,
            "numeric_completed": True,
            "ksp_setup_repeats_symbolic_before_numeric": True,
            "symbolic_admission_record_sha256": admission["record_sha256"],
            "actual_pc_factor_solver_type": "mumps",
            "factor_released_before_native_a6": True,
            "ksp_destroy_called": True,
            "pc_python_reference_deleted_before_ksp_destroy": True,
            "petsc_garbage_cleanup_called": True,
            "resource_after_factor_release": {
                "job_no_swap": True,
                "memory_authority_bytes": 1 << 30,
                "process_tree": {
                    "all_status_readable": True,
                    "rss_bytes": 1 << 30,
                    "swap_bytes": 0,
                },
            },
            "memory_envelope_after_factor_release": {
                "memory_policy": "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
                "cgroup_limits": [],
                "launch_cap_bytes": 1 << 40,
                "reserve_bytes": 64 * 1024**3,
            },
            "mumps_control_readback": {
                "pass": True,
                "observed_icntl": expected_icntl,
            },
            "factor_inventory_after_setup": {
                "factor_solver_type": "mumps",
                "mumps_api_available": True,
                "mumps_raw_infog": {"1": 0, "16": 10, "17": 12},
            },
        },
    )
    native["mumps_factor_released_before_native_a6"] = True
    native["mumps_factor_release_record_sha256"] = numeric_stage["record_sha256"]
    native_digest_payload = {
        key: value
        for key, value in native.items()
        if key not in {"record_sha256", "artifact_file"}
    }
    native["record_sha256"] = hashlib.sha256(
        json.dumps(
            native_digest_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    (output / native["artifact_file"]).write_text(
        json.dumps(
            {
                key: value
                for key, value in native.items()
                if key != "artifact_file"
            },
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    volume = {
        "method": "volume_absorption",
        "role": "absorption_check",
        "status": "ok",
        "power_source": "volume_integral_Im_epsilon_E2",
        "field_model_for_absorption": "total_field",
        "pml_cells_excluded": True,
        "air_cells_excluded": True,
        "incident_power_code_units": 2.0,
        "regions": {
            name: {
                "status": "ok",
                "cell_count": 1,
                "volume_nm3": 10.0,
                "Im_epsilon_r": 0.001,
                "absorbed_power_code_units": 0.2,
                "A_volume": 0.1,
            }
            for name in ("grating", "substrate")
        },
        "A_grating": 0.1,
        "A_substrate": 0.1,
        "A_volume_total": 0.2,
    }
    port = {
        "method": "port",
        "role": "primary",
        "status": "ok",
        "power_source": "dtn_port_modal_amplitudes",
        "R_total": 0.3,
        "T_total": 0.5,
        "A_balance": 0.2,
        "orders": [{}],
    }
    for filename, value in (
        ("volume_absorption.json", volume),
        ("port_power.json", port),
    ):
        (output / filename).write_text(json.dumps(value), encoding="utf-8")

    summary = {
        "case_status": "completed",
        "official_result": True,
        "actual_pc_factor_solver_type": "mumps",
        "petsc_direct_solver_profile": "mumps_exact",
        "stage4_full3d_assembly_backend_actual": "assembly_time_static_condensed",
        "stage4_assembly_time_cell_static_condensation": True,
        "stage4_floquet_slave_elimination": True,
        "mumps_control_readback": {
            "observed_icntl": {
                str(index): value
                for index, value in TASK41_MUMPS_EXACT_ICNTL.items()
            },
            "pass": True,
        },
        "cell_static_condensation": {
            "recovery": {
                "status": "full_field_recovered_without_full_global_matrix",
                "recovered_interior_rows": 1,
                "full_global_matrix_allocated": False,
            }
        },
        "task41_native_full_a6": native,
        "task41_mumps_symbolic_admission": admission,
        "task41_mumps_numeric_stage": numeric_stage,
        "task41_native_a6_gate_pass": residual_norm <= 1.0e-6,
        "official_rta_gate_pass": residual_norm <= 1.0e-6,
        "num_nedelec_dofs": 2,
        "linear_system_relative_residual": 1e-8,
        "R_total": 0.3,
        "T_total": 0.5,
        "A_balance": 0.2,
        "A_volume_total": 0.2,
        "energy_closure_error_port_volume": 0.0,
        "A_port_balance_minus_A_volume_total": 0.0,
    }
    return summary, output


def test_task41_direct_authority_checks_native_a6_recovery_and_energy(tmp_path):
    summary, output = _task41_authority_fixture(tmp_path)
    assert task41_direct_summary_errors(summary, output) == []

    missing_readback = dict(summary)
    missing_readback.pop("mumps_control_readback")
    assert any(
        "MUMPS ICNTL readback" in error
        for error in task41_direct_summary_errors(missing_readback, output)
    )

    missing_recovery = dict(summary)
    missing_recovery["cell_static_condensation"] = {}
    assert any(
        "recovery" in error
        for error in task41_direct_summary_errors(missing_recovery, output)
    )


def test_task41_direct_authority_rejects_native_a6_and_energy_counterexamples(tmp_path):
    summary, output = _task41_authority_fixture(
        tmp_path / "a6", residual_values=(2.0e-6 + 0j, 0.0 + 0j)
    )
    from src.solvers.common_3d_case_flow import (
        _official_result_after_stage4_gates,
        _task41_native_a6_gate_failed,
    )
    from src.solvers.dtn_port_3d import _task41_official_rta_gate_passes

    assert _task41_official_rta_gate_passes(
        summary["task41_native_full_a6"], True
    ) is False
    assert _official_result_after_stage4_gates(
        True,
        external_solver_snapshot=False,
        external_rta_gate_pass=None,
        task41_native_a6_gate_pass=summary["task41_native_a6_gate_pass"],
    ) is False
    assert _task41_native_a6_gate_failed(
        {
            "task41_native_full_a6": summary["task41_native_full_a6"],
            "task41_native_a6_gate_pass": summary["task41_native_a6_gate_pass"],
        }
    ) is True
    assert any(
        "native full A6 relative residual exceeds 1e-6" in error
        for error in task41_direct_summary_errors(summary, output)
    )

    summary, output = _task41_authority_fixture(tmp_path / "energy")
    port_path = output / "port_power.json"
    port = json.loads(port_path.read_text(encoding="utf-8"))
    port["R_total"] = 0.31
    port_path.write_text(json.dumps(port), encoding="utf-8")
    errors = task41_direct_summary_errors(summary, output)
    assert any("energy error exceeds 1e-5" in error for error in errors)

    summary, output = _task41_authority_fixture(tmp_path / "volume")
    volume_path = output / "volume_absorption.json"
    volume = json.loads(volume_path.read_text(encoding="utf-8"))
    volume["regions"]["grating"]["absorbed_power_code_units"] = 0.3
    volume_path.write_text(json.dumps(volume), encoding="utf-8")
    assert any(
        "normalization does not recompute" in error
        for error in task41_direct_summary_errors(summary, output)
    )


def test_task41_p0_checker_uses_persisted_launcher_shapes_and_rechecks_native_a6(
    tmp_path, monkeypatch
):
    from src.io import load_and_resolve
    from src.runners import task41_p0_checker
    from src.runners.task038_launcher import _initial_summary, _write_bootstrap

    specification = load_and_resolve(INPUT)
    input_path = tmp_path / "input/task41extra_phi90_p50x50_g17x20/g13_p6_direct_a1.dat"
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(INPUT.read_bytes())
    run_directory = tmp_path / "results/task41/a1"
    run_directory.mkdir(parents=True)
    source_sha = "a" * 40
    manifest, resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=source_sha,
        adapter_identity="task038.full3d_direct",
        start_time="2026-10-16T00:00:00Z",
    )
    numerical_output = run_directory / "numerical_output"
    output_summary, _ = _task41_authority_fixture(run_directory)
    numerical_summary_path = numerical_output / "run_summary.json"
    numerical_summary_path.write_text(
        json.dumps(output_summary, sort_keys=True), encoding="utf-8"
    )
    launcher_summary = _initial_summary(manifest)
    launcher_summary.update(
        status="completed", result_classification="worker_exit0", exit_status=0
    )
    summary_path = run_directory / "run_summary.json"
    summary_path.write_text(json.dumps(launcher_summary), encoding="utf-8")
    manifest_path = run_directory / "run_manifest.json"
    case = {
        "input_path": "input/task41extra_phi90_p50x50_g17x20/g13_p6_direct_a1.dat",
        "input_sha256": specification.input_sha256,
        "model_id": specification.identity["model_id"],
        "run_id": specification.identity["run_id"],
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_sha,
        "method": specification.method["kind"],
        "mpi_size": specification.execution["mpi_size"],
    }
    contract = {
        "task_id": specification.identity["model_id"],
        "source": {"sha": source_sha},
        "case": case,
        "window": {
            "path": "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_controller/execution_window.json",
            "sha256": "b" * 64,
        },
    }
    monkeypatch.setattr(
        task41_p0_checker,
        "require_task41_p0_contract",
        lambda *args, **kwargs: (contract, "c" * 64),
    )
    monkeypatch.setattr(task41_p0_checker, "load_and_resolve", lambda _path: specification)
    monkeypatch.setattr(
        task41_p0_checker,
        "validate_task41_specification",
        lambda *_args, **_kwargs: None,
    )
    output_path = tmp_path / "evidence/checker.json"
    result = task41_p0_checker.check_task41_p0(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output=numerical_output,
        contract_path=tmp_path / "contract.json",
        contract_sha256="c" * 64,
        output_path=output_path,
        repo_root=tmp_path,
    )
    assert result["checker_passed"] is True, result["errors"]
    assert result["launcher_result_classification"] == "worker_exit0"

    output_summary["task41_native_a6_gate_pass"] = False
    numerical_summary_path.write_text(
        json.dumps(output_summary, sort_keys=True), encoding="utf-8"
    )
    failed = task41_p0_checker.check_task41_p0(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output=numerical_output,
        contract_path=tmp_path / "contract.json",
        contract_sha256="c" * 64,
        output_path=output_path,
        repo_root=tmp_path,
    )
    assert failed["checker_passed"] is False
    assert any("native full A6 gate" in error for error in failed["errors"])
    assert failed["raw_evidence_retained"] is True


def test_task41_mumps_admission_uses_info_co_resident_and_ancestor_headroom():
    from src.solvers.dtn_port_3d import _task41_mumps_admission_decision

    symbolic = {"infog": {"16": 1024, "17": 1536}}
    resource = {
        "memory_authority_bytes": 1 << 30,
        "job_no_swap": True,
        "process_tree": {
            "rss_bytes": 1 << 30,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
    }
    envelope = {
        "mem_total_bytes": 512 * 1024**3,
        "host_mem_available_bytes": 256 * 1024**3,
        "reserve_bytes": 64 * 1024**3,
        "launch_cap_bytes": 192 * 1024**3,
        "cgroup_limits": [{"path": "/sys/fs/cgroup", "limit_bytes": 1 << 40}],
    }
    decision = _task41_mumps_admission_decision(
        symbolic, resource, envelope, 100_000
    )
    assert decision["status"] == "ADMISSIBLE"
    assert decision["factor_estimate_multiplier"] == 2
    assert decision["host_reserve_bytes"] == 64 * 1024**3
    assert decision["available_growth_bytes"] == 192 * 1024**3

    constrained = dict(envelope, launch_cap_bytes=1 << 30)
    assert (
        _task41_mumps_admission_decision(
            symbolic, resource, constrained, 100_000
        )["status"]
        == "CAPACITY_NOT_ADMITTED"
    )
    swapped = dict(resource, job_no_swap=False)
    assert (
        _task41_mumps_admission_decision(
            symbolic, swapped, envelope, 100_000
        )["status"]
        == "CAPACITY_NOT_ADMITTED"
    )


def test_task41_tiny_complex_mumps_staged_call_chain(tmp_path, monkeypatch):
    """Exercise real PETSc/MUMPS staging and release without an FE model."""

    from mpi4py import MPI
    from petsc4py import PETSc

    if not PETSc.Sys.hasExternalPackage("mumps"):
        pytest.skip("the active PETSc build has no MUMPS package")

    import benchmarks.subreaper_watchdog as watchdog
    import benchmarks.task034_wsl_resources as task_resources
    from src.solvers import dtn_port_3d
    from src.solvers.common_3d_solve import DirectSolveFailure

    # This test-only fixture admits a tiny matrix without consulting the
    # workstation's real 64 GiB host reserve. Production calls keep the real
    # resource samplers and memory envelope by default.
    def resource_sample(_pid):
        return {
            "fixture_scope": "tiny_petcs_mumps_test_only",
            "memory_authority_bytes": 1 << 30,
            "job_no_swap": True,
            "process_tree": {
                "rss_bytes": 1 << 30,
                "swap_bytes": 0,
                "all_status_readable": True,
            },
        }

    def memory_envelope(*_args, **_kwargs):
        return {
            "fixture_scope": "tiny_petcs_mumps_test_only",
            "memory_policy": "synthetic_test_fixture_only",
            "mem_total_bytes": 1 << 50,
            "host_mem_available_bytes": 1 << 49,
            "reserve_bytes": 64 * 1024**3,
            "launch_cap_bytes": 1 << 40,
            "cgroup_limits": [],
        }

    real_symbolic_admission = dtn_port_3d._task41_mumps_symbolic_admission
    real_admission_decision = dtn_port_3d._task41_mumps_admission_decision

    def tiny_matrix_admission_decision(
        symbolic_info, resource, envelope, matrix_rows, **kwargs
    ):
        # MUMPS reports memory estimates in integer MB; a 2x2 probe rounds
        # INFOG(16/17) to zero. Preserve that raw readback in the admission
        # artifact, but inject a 1 MB estimate into the policy function so the
        # test can reach the real KSP numeric/release path. This never runs in
        # production and cannot qualify a Task41 case.
        adjusted = copy.deepcopy(symbolic_info)
        actual = {
            str(index): adjusted.get("infog", {}).get(str(index))
            for index in (16, 17)
        }
        infog = adjusted.setdefault("infog", {})
        for index in (16, 17):
            infog[str(index)] = max(1, int(infog.get(str(index), 0) or 0))
        decision = real_admission_decision(
            adjusted, resource, envelope, matrix_rows, **kwargs
        )
        decision["test_only_symbolic_estimate_fixture"] = {
            "scope": "tiny_petcs_mumps_test_only",
            "actual_mumps_infog_16_17": actual,
            "admission_infog_16_17": {
                str(index): infog[str(index)] for index in (16, 17)
            },
        }
        return decision

    def fixture_symbolic_admission(matrix, comm, out_dir, *, matrix_rows):
        return real_symbolic_admission(
            matrix,
            comm,
            out_dir,
            matrix_rows=matrix_rows,
            resource_sample_factory=resource_sample,
            memory_envelope_factory=memory_envelope,
        )

    monkeypatch.setattr(
        dtn_port_3d,
        "_task41_mumps_symbolic_admission",
        fixture_symbolic_admission,
    )
    monkeypatch.setattr(
        dtn_port_3d,
        "_task41_mumps_admission_decision",
        tiny_matrix_admission_decision,
    )
    # The post-solve release audit uses these module-level imports directly.
    monkeypatch.setattr(task_resources, "resource_authority_sample", resource_sample)
    monkeypatch.setattr(watchdog, "memory_envelope", memory_envelope)

    matrix = PETSc.Mat().createAIJ(
        size=(2, 2), nnz=2, comm=MPI.COMM_SELF
    )
    matrix.setUp()
    matrix.setValues(
        [0, 1],
        [0, 1],
        np.asarray(
            [[4.0 + 1.0j, 1.0 - 1.0j], [2.0 + 0.5j, 3.0 - 2.0j]],
            dtype=PETSc.ScalarType,
        ),
    )
    matrix.assemble()
    exact = matrix.createVecRight()
    exact.setValues([0, 1], np.asarray([1.0 + 2.0j, -0.5 + 0.25j]))
    exact.assemble()
    rhs = matrix.createVecLeft()
    matrix.mult(exact, rhs)

    options = {
        "ksp_type": "preonly",
        "pc_type": "lu",
        "pc_factor_mat_solver_type": "mumps",
        **{
            f"mat_mumps_icntl_{index}": value
            for index, value in TASK41_MUMPS_EXACT_ICNTL.items()
        },
    }
    solved = None
    ksp = None
    try:
        solved, ksp, telemetry = dtn_port_3d._solve_augmented_system(
            matrix,
            rhs,
            options,
            "task41_tiny_mumps_test_",
            out_dir=tmp_path,
            comm=MPI.COMM_SELF,
            started=time.perf_counter(),
            dofs=2,
            matrix_stats={"matrix_rows": 2, "matrix_nnz_used": 4},
            task41_mumps_staged_admission=True,
        )

        assert ksp is None  # factor/KSP released before the independent A6 step
        assert np.allclose(solved.getArray(readonly=True), exact.getArray())
        state = telemetry["task41_ksp_state_after_solve"]
        assert state["converged_reason"] > 0
        assert state["factor_solver_type"] == "mumps"
        assert state["mumps_control_readback"]["pass"] is True
        assert state["mumps_control_readback"]["observed_icntl"] == {
            str(index): value
            for index, value in TASK41_MUMPS_EXACT_ICNTL.items()
        }

        admission = telemetry["task41_mumps_symbolic_admission"]
        assert admission["status"] == "ADMISSIBLE"
        assert admission["symbolic_calls"] == 1
        assert admission["numeric_called"] is False
        assert admission["probe_factor_released_before_ksp_setup"] is True
        assert admission["final_admission_sample_after_probe_release"] is True
        assert admission["post_release_resource"]["fixture_scope"] == (
            "tiny_petcs_mumps_test_only"
        )
        assert admission["test_only_symbolic_estimate_fixture"]["scope"] == (
            "tiny_petcs_mumps_test_only"
        )

        numeric_stage = telemetry["task41_mumps_numeric_stage"]
        assert numeric_stage["status"] == "COMPLETED"
        assert numeric_stage["numeric_completed"] is True
        assert numeric_stage["ksp_setup_repeats_symbolic_before_numeric"] is True
        assert numeric_stage["factor_released_before_native_a6"] is True
        assert numeric_stage["ksp_destroy_called"] is True
        assert numeric_stage["pc_python_reference_deleted_before_ksp_destroy"] is True
        assert numeric_stage["petsc_garbage_cleanup_called"] is True
        assert numeric_stage["memory_envelope_after_factor_release"][
            "fixture_scope"
        ] == "tiny_petcs_mumps_test_only"

        for artifact_name, expected_schema in (
            (
                "task41_mumps_symbolic_admission.json",
                "task41.mumps_symbolic_admission.v1",
            ),
            (
                "task41_mumps_numeric_stage.json",
                "task41.mumps_numeric_stage.v1",
            ),
        ):
            record = json.loads((tmp_path / artifact_name).read_text())
            digest = record.pop("record_sha256")
            actual = hashlib.sha256(
                json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            assert digest == actual
            assert record["schema"] == expected_schema
    except DirectSolveFailure as exc:
        exc.cleanup()
        raise
    finally:
        if ksp is not None:
            ksp.destroy()
        if solved is not None:
            solved.destroy()
        rhs.destroy()
        exact.destroy()
        matrix.destroy()
