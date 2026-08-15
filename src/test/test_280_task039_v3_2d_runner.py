"""Focused V3 2D artifact, closure, field-sign, and telemetry contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from benchmarks.task039_memory_telemetry import task039_v3_2d_formal_profile
from src.io import load_and_resolve
from src.io.input_validation import simulation_config_2d_from_normalized
from src.runners import task038_2d, task038_launcher as launcher
from src.runners.task038_2d import _v3_2d_authority_errors
from src.postprocessing import te_reference


ROOT = Path(__file__).resolve().parents[2]
V3_H5 = ROOT / "input/official/task039/5nm_1deg_2d_te_p6h5_direct_mpi1.dat"


def _finite_authority(memory=1024):
    return {
        "memory_authority_bytes": memory,
        "process_tree": {
            "rss_bytes": memory,
            "swap_bytes": 0,
            "root_pid": 4242,
            "all_status_readable": True,
            "smaps": {
                "complete": True,
                "pss_bytes": memory,
                "uss_bytes": memory // 2,
            },
        },
        "job_cgroup": {"dedicated_job_cgroup": False, "swap_current_bytes": None},
    }


class _OnePollProcess:
    pid = 4242

    def __init__(self):
        self.returncode = None
        self._polls = 0

    def poll(self):
        self._polls += 1
        if self._polls > 1:
            self.returncode = 0
        return self.returncode

    def wait(self):
        self.returncode = 0
        return 0


def _order_row(order=0):
    return {
        "order": order,
        "top_propagating": -19 <= order <= 0,
        "bottom_propagating": -19 <= order <= -1,
        "reflected_Ez_real": 0.1,
        "reflected_Ez_imag": 0.02,
        "transmitted_Ez_real": 0.8,
        "transmitted_Ez_imag": -0.01,
        "R_order": 0.2,
        "T_order": 0.3,
    }


def _field_descriptor(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    arrays = {
        "x_nm": np.arange(40, dtype=np.float64),
        "z_nm": np.arange(7, dtype=np.float64),
        "electric_y_V_per_m": np.ones((7, 40), dtype=np.complex128),
        "magnetic_x_A_per_m": np.ones((7, 40), dtype=np.complex128),
        "magnetic_z_A_per_m": np.ones((7, 40), dtype=np.complex128),
    }
    payload = tmp_path / "fields.npz"
    metadata = tmp_path / "fields.json"
    np.savez(payload, **arrays)
    metadata.write_text('{"schema":"test"}\n', encoding="utf-8")
    return {
        "payload_path": payload.name,
        "metadata_path": metadata.name,
        "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
    }


def _write_dtn_files(tmp_path: Path, metrics):
    (tmp_path / "dtn_port_power_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    (tmp_path / "dtn_port_diffraction_orders.json").write_text(
        json.dumps(metrics["orders"], indent=2) + "\n", encoding="utf-8"
    )


def test_v3_profile_is_explicit_and_ordinary_is_not_formal():
    specification = load_and_resolve(V3_H5)
    assert task039_v3_2d_formal_profile(specification.as_jsonable()) is True
    ordinary = load_and_resolve(ROOT / "input/templates/ordinary_2d_example.dat")
    assert task039_v3_2d_formal_profile(ordinary.as_jsonable()) is False


def test_v3_plane_wave_mapping_uses_real_cfg_values():
    specification = load_and_resolve(V3_H5)
    cfg = simulation_config_2d_from_normalized(specification.as_jsonable())
    kx = cfg.kx
    kz = cfg.ky
    beta = np.sqrt((cfg.k0 * cfg.n_air) ** 2 - kx**2 + 0j)
    h2_scaled = np.asarray([kz, -kx], dtype=np.complex128)
    h3 = np.cross(np.asarray([kx, 0.0, -beta]), np.asarray([0.0, 1.0, 0.0])) / cfg.k0
    np.testing.assert_allclose(
        h3[[0, 2]], -h2_scaled / cfg.k0, rtol=1.0e-12, atol=1.0e-13
    )
    p2d = 0.5 * float(np.real(beta)) * cfg.period_x
    p3d_scaled = 0.5 * float(np.real(beta / cfg.k0)) * cfg.period_x * 25.0
    assert abs(p2d - p3d_scaled * cfg.k0 / 25.0) / max(abs(p2d), 1.0e-30) <= 1.0e-12


def test_selected_field_export_has_signed_physical_h_mapping(monkeypatch, tmp_path):
    specification = load_and_resolve(V3_H5)
    cfg = simulation_config_2d_from_normalized(specification.as_jsonable())
    hx = object()
    hz = object()
    monkeypatch.setattr(te_reference, "_scaled_hx_function", lambda *_args: hx)
    monkeypatch.setattr(te_reference, "_scaled_te_hz_function", lambda *_args: hz)

    def sample(function, *_args):
        value = 1.0 if function is hx else 2.0 if function is hz else 3.0
        return np.full(40, value, dtype=np.complex128)

    monkeypatch.setattr(te_reference, "_sample_scalar_on_wrapped_line", sample)
    descriptor = te_reference.write_v3_2d_selected_fields(cfg, object(), tmp_path)
    with np.load(tmp_path / descriptor["payload_path"], allow_pickle=False) as arrays:
        np.testing.assert_allclose(
            arrays["magnetic_x_A_per_m"],
            -cfg.magnetic_field_scale_A_per_m / cfg.k0,
        )
        np.testing.assert_allclose(
            arrays["magnetic_z_A_per_m"],
            -2.0 * cfg.magnetic_field_scale_A_per_m / cfg.k0,
        )


def test_v3_authority_uses_dtn_observables_and_independent_closure(tmp_path):
    metrics = {
        "R_total": 0.2,
        "T_total": 0.3,
        "R_plus_T": 0.5,
        "A_balance": 0.5,
        "A_volume": 0.5,
        "energy_residual_1_minus_R_minus_T": 0.5,
        "orders": [_order_row(order) for order in range(-21, 22)],
        "port_dtn_order_count": 21,
    }
    descriptor = _field_descriptor(tmp_path)
    _write_dtn_files(tmp_path, metrics)
    summary = {
        "reduced_linear_residual": 1.0e-12,
        "power_metrics": {"R_total": float("nan")},
        "dtn_port_power_metrics": metrics,
        "v3_selected_fields": descriptor,
    }
    assert _v3_2d_authority_errors(summary, tmp_path) == []


def test_v3_run_2d_uses_dtn_authority_and_rejects_bad_dtn_closure(tmp_path):
    specification = load_and_resolve(V3_H5)

    def fake_solver(_cfg, output_directory, _backend):
        metrics = {
            "R_total": 0.2,
            "T_total": 0.3,
            "R_plus_T": 0.5,
            "A_balance": 0.5,
            "A_volume": 0.5,
            "orders": [_order_row(order) for order in range(-21, 22)],
            "port_dtn_order_count": 21,
        }
        descriptor = _field_descriptor(output_directory)
        _write_dtn_files(output_directory, metrics)
        return {
            "reduced_linear_residual": 1.0e-12,
            "power_metrics": {"R_total": float("nan")},
            "dtn_port_power_metrics": metrics,
            "v3_selected_fields": descriptor,
            "elapsed_seconds": 0.1,
        }

    passed = task038_2d.run_2d(
        specification.as_jsonable(), tmp_path / "good", solver_runner=fake_solver
    )
    assert passed["passed"] is True
    assert Path(passed["v3_2d_reference_record"]).is_file()

    def bad_solver(_cfg, output_directory, _backend):
        result = fake_solver(_cfg, output_directory, _backend)
        result["dtn_port_power_metrics"]["A_volume"] = 0.4
        return result

    failed = task038_2d.run_2d(
        specification.as_jsonable(), tmp_path / "bad", solver_runner=bad_solver
    )
    assert failed["passed"] is False
    assert "energy closure" in " ".join(failed["errors"])
    assert "raw power field disagrees" in " ".join(failed["errors"])
    assert not (tmp_path / "bad/numerical_output/v3_2d_reference.json").exists()

    record = json.loads(
        (tmp_path / "good/numerical_output/v3_2d_reference.json").read_text(
            encoding="utf-8"
        )
    )
    resolved = specification.as_jsonable()
    assert record["model_id"] == resolved["model_id"]
    assert (
        record["provenance"]["input_sha256"] == resolved["provenance"]["input_sha256"]
    )
    assert (
        record["provenance"]["physical_model_sha256"]
        == resolved["provenance"]["physical_model_sha256"]
    )


def test_v3_run_2d_requires_both_dtn_artifacts(tmp_path):
    specification = load_and_resolve(V3_H5)

    def missing_artifacts_solver(_cfg, output_directory, _backend):
        descriptor = _field_descriptor(output_directory)
        return {
            "reduced_linear_residual": 1.0e-12,
            "power_metrics": {"R_total": float("nan")},
            "dtn_port_power_metrics": {
                "R_total": 0.2,
                "T_total": 0.3,
                "R_plus_T": 0.5,
                "A_balance": 0.5,
                "A_volume": 0.5,
                "orders": [_order_row(order) for order in range(-21, 22)],
                "port_dtn_order_count": 21,
            },
            "v3_selected_fields": descriptor,
        }

    result = task038_2d.run_2d(
        specification.as_jsonable(),
        tmp_path / "missing",
        solver_runner=missing_artifacts_solver,
    )
    assert result["passed"] is False
    assert "required DtN artifact" in " ".join(result["errors"])
    assert not (tmp_path / "missing/numerical_output/v3_2d_reference.json").exists()


def test_v3_run_2d_rejects_inconsistent_raw_dtn_json(tmp_path):
    specification = load_and_resolve(V3_H5)

    def corrupt_raw_solver(_cfg, output_directory, _backend):
        metrics = {
            "R_total": 0.2,
            "T_total": 0.3,
            "R_plus_T": 0.5,
            "A_balance": 0.5,
            "A_volume": 0.5,
            "orders": [_order_row(order) for order in range(-21, 22)],
            "port_dtn_order_count": 21,
        }
        descriptor = _field_descriptor(output_directory)
        _write_dtn_files(output_directory, metrics)
        raw_power_path = output_directory / "dtn_port_power_metrics.json"
        raw_power = json.loads(raw_power_path.read_text(encoding="utf-8"))
        raw_power["R_total"] = 0.25
        raw_power_path.write_text(
            json.dumps(raw_power, indent=2) + "\n", encoding="utf-8"
        )
        return {
            "reduced_linear_residual": 1.0e-12,
            "power_metrics": {"R_total": float("nan")},
            "dtn_port_power_metrics": metrics,
            "v3_selected_fields": descriptor,
        }

    result = task038_2d.run_2d(
        specification.as_jsonable(),
        tmp_path / "corrupt",
        solver_runner=corrupt_raw_solver,
    )
    assert result["passed"] is False
    assert "raw power field disagrees" in " ".join(result["errors"])
    assert not (tmp_path / "corrupt/numerical_output/v3_2d_reference.json").exists()


def test_v3_launcher_persists_process_tree_samples_only_for_formal_profile(
    monkeypatch, tmp_path
):
    specification = replace(
        load_and_resolve(V3_H5), expected_output_parent=tmp_path / "results"
    )
    monkeypatch.setattr(
        launcher,
        "_task039_memory_budget",
        lambda _execution=None: {
            "configured_warning_memory_gib": 8.0,
            "effective_terminate_memory_gib": 10.0,
        },
    )
    result = launcher.launch_specification(
        specification,
        source_sha="a" * 40,
        timestamp="20260815T000000.000000Z",
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        popen_factory=lambda *_args, **_kwargs: _OnePollProcess(),
        sample_factory=lambda _pid: _finite_authority(),
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    run_directory = Path(result["run_directory"])
    samples = run_directory / "numerical_output/process_tree_samples.jsonl"
    assert samples.is_file()
    assert len(samples.read_text(encoding="utf-8").splitlines()) >= 1
    summary = json.loads(Path(result["summary"]).read_text(encoding="utf-8"))
    assert summary["resource_authority"]["v3_2d_formal_telemetry"]["sample_count"] >= 1
    assert summary["resource_authority"]["v3_2d_formal_telemetry"][
        "stage_aligned_status"
    ] == ("not_applicable_2d_reference")
