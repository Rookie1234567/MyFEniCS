"""Pure contracts for the connected Task38 Hybrid iterative adapter."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.execution_plan import dry_run_payload, method_adapter_available
from src.io.input_loader import InputError
from src.runners.task038_hybrid_iterative import run_hybrid_iterative
from src.runners.task038_input_worker import _dispatch_resolved_payload


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "input/templates/hybrid_iterative_example.dat"
OFFICIAL = ROOT / ("input/official/grazing1_phi0_hybrid_iterative_m120_mpi8.dat")
SOURCE_SHA = "a" * 40


def _payload(path: Path = OFFICIAL) -> dict:
    return load_and_resolve(path).as_jsonable()


def _record(*, online_pass: bool = True) -> dict:
    return {
        "record_schema": "task037c.hybrid-iterative-online.v1",
        "status": "online_candidate_pass_awaiting_offline_checker",
        "online_pass": online_pass,
        "ordinary_default_changed": False,
        "explicit_opt_in": True,
        "profile": {
            "profile_id": "task037c.robustness.grazing1.v1",
            "target": "hybrid",
            "degree": 6,
            "h_nm": 10.0,
            "modal_degree": 6,
            "modal_h_nm": 10.0,
            "wavelength_nm": 13.5,
            "polarization_kind": "s",
            "incident_grazing_deg": 1.0,
            "incident_phi_deg": 0.0,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "requested_modes": 120,
            "candidate_modes": 240,
            "internal_propagation_model": "full3d_uniform_cg",
            "internal_traction_model": "full3d_one_cell_exact_schur",
            "operator_identity": "exact_monolithic_hybrid_operator",
            "solver_path": "block-ldu-action-full-solve",
            "preconditioner_identity": (
                "fixed_whole_endcap_ilu0_plus_dynamic_dtn_woodbury_"
                "two_pass_residual_correction"
            ),
            "subdomain_count": 1,
            "overlap": 0.0,
            "ilu_level": 0,
            "shift": 0.1,
            "restart": 90,
            "max_it": 4500,
            "rtol": 5.0e-9,
            "initial_guess": "zero",
            "mpi_size": 8,
            "assembly_backend": "assembly_time_static_condensed",
            "side_residual_correction_steps": 2,
        },
        "source": {
            "before": {"commit_sha": SOURCE_SHA},
            "after": {
                "head": SOURCE_SHA,
                "clean": True,
                "matches_verified_clean_sha": True,
            },
        },
        "qualification": {
            key: True
            for key in (
                "numerical_pass",
                "release_pass",
                "recovery_pass",
                "physics_pass",
                "lifecycle_pass",
                "source_after_pass",
                "final_release_pass",
                "cfg_audit_pass",
                "mode_identity_pass",
                "error_free",
            )
        },
        "linear": {
            "reason": 2,
            "iterations": 1472,
            "postsolve_residuals": {
                "reported_relative_residual": 3.9e-9,
                "global_true_relative_residual": 3.9e-9,
                "bottom_true_relative_residual": 4.9e-9,
                "top_true_relative_residual": 3.1e-9,
                "modal_true_relative_residual": 2.0e-15,
            },
            "release": {"pass": True},
        },
        "physics": {
            "port_power": {"R_total": 0.36, "T_total": 0.013},
            "absorption": {"A_volume_total": 0.621},
            "energy": {"closure": 1.0e-10},
            "traction": {
                "bottom": {"relative_dual": 4.9e-9},
                "top": {"relative_dual": 3.1e-9},
            },
            "external_orders": [{"side": "top", "m": 0, "n": 0}],
            "order_audit": {"pass": True},
            "own_physics_pass": True,
            "canonical_pass": True,
        },
        "final_release": {"pass": True},
    }


def _run(payload, tmp_path, *, record=None, seen=None):
    def fake_runner(argv):
        if seen is not None:
            seen["argv"] = argv
        return deepcopy(record or _record())

    return run_hybrid_iterative(
        payload,
        tmp_path / "run",
        runner=fake_runner,
        source_sha=SOURCE_SHA,
    )


def test_template_and_official_are_connected_and_dry_run_is_stable():
    for path in (TEMPLATE, OFFICIAL):
        specification = load_and_resolve(path)
        assert specification.method["kind"] == "hybrid_iterative"
        assert method_adapter_available("hybrid_iterative") is True
        payload = dry_run_payload(specification)
        assert payload["resolved_method_adapter"] == {
            "identity": "task038.hybrid_iterative",
            "status": "connected",
        }
        assert payload["requested_modes_per_direction"] == 120


def test_adapter_maps_exact_profile_argv_and_never_nests_mpiexec(tmp_path):
    seen = {}
    result = _run(_payload(), tmp_path, seen=seen)
    assert result["passed"] is True
    argv = seen["argv"]
    assert "mpiexec" not in argv
    assert argv[0:3] == [
        "--task037c-robustness-gate",
        "--case-label",
        _payload()["run_id"],
    ]
    assert argv[argv.index("--requested-modes") + 1] == "120"
    assert argv[argv.index("--mpi-size") + 1] == "8"
    assert argv[argv.index("--internal-traction-model") + 1] == (
        "full3d_one_cell_exact_schur"
    )
    assert argv[argv.index("--verified-clean-sha") + 1] == SOURCE_SHA
    assert argv[argv.index("--run-dir") + 1].endswith("/run/numerical_output")
    memory_stages = Path(argv[argv.index("--memory-stages") + 1])
    assert (
        memory_stages
        == Path(result["numerical_output_directory"]) / "memory_stages.jsonl"
    )
    assert not memory_stages.exists()
    assert argv[-1] == "--task037c-two-pass-side-correction"
    assert result["numerical_output_directory"].endswith("/run/numerical_output")


@pytest.mark.parametrize(
    ("section", "key", "value"),
    (
        ("geometry", "period_x_nm", 51.0),
        ("materials", "n_grating", (0.9991, 0.0018)),
        ("incidence", "wavelength_nm", 14.0),
        ("incidence", "azimuth_deg", 2.0),
        ("method", "requested_modes_per_direction", 160),
        ("method", "traction_model", "scalar_cg_discrete_derivative"),
        ("solver", "side_residual_correction_steps", 1),
        ("solver", "restart", 60),
        ("solver", "max_iterations", 1600),
        ("solver", "relative_tolerance", 1.0e-8),
        ("solver", "ilu_shift", 0.2),
        ("output", "export_canonical_vectors", False),
    ),
)
def test_adapter_rejects_fields_not_consumed_by_legacy_profile(
    tmp_path, section, key, value
):
    payload = _payload()
    payload[section][key] = value
    with pytest.raises(ValueError, match="Task37c iterative adapter|requires"):
        _run(payload, tmp_path)


def test_resource_and_directory_controls_remain_input_driven(tmp_path):
    payload = _payload()
    payload["execution"].update(
        warning_memory_gib=8.0,
        terminate_memory_gib=16.0,
        timeout_seconds=60,
    )
    payload["output"].update(
        results_root=str(tmp_path / "custom-results"), unique_output=False
    )
    result = _run(payload, tmp_path)
    assert result["passed"] is True


@pytest.mark.parametrize(
    ("old", "new"),
    (
        ("period_x_nm = 50.0", "period_x_nm = 51.0"),
        (
            "n_grating = [0.999002304859, 0.00182649365]",
            "n_grating = [0.999102304859, 0.00182649365]",
        ),
        ("wavelength_nm = 13.5", "wavelength_nm = 14.0"),
        ("mpi_size = 8", "mpi_size = 4"),
        (
            "requested_modes_per_direction = 120",
            "requested_modes_per_direction = 160",
        ),
        (
            'traction_model = "full3d_one_cell_exact_schur"',
            'traction_model = "scalar_cg_discrete_derivative"',
        ),
        ("side_residual_correction_steps = 2", "side_residual_correction_steps = 1"),
    ),
)
def test_dat_profile_variants_fail_during_load_and_resolve(tmp_path, old, new):
    text = OFFICIAL.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "variant.dat"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(InputError, match="Task37c iterative adapter"):
        load_and_resolve(path)


@pytest.mark.parametrize(
    "change",
    (
        lambda record: record.update(online_pass=False),
        lambda record: record["linear"].update(reason=None),
        lambda record: record["linear"]["postsolve_residuals"].update(
            global_true_relative_residual=6.0e-9
        ),
        lambda record: record["physics"]["traction"]["bottom"].update(
            relative_dual=2.0e-8
        ),
        lambda record: record["final_release"].update({"pass": False}),
        lambda record: record["source"]["after"].update(head="b" * 40),
    ),
)
def test_negative_online_record_is_not_authoritative(tmp_path, change):
    record = _record()
    change(record)
    result = _run(_payload(), tmp_path, record=record)
    assert result["passed"] is False
    assert result["errors"]


def test_worker_dispatch_forwards_iterative_source_attestation(monkeypatch, tmp_path):
    import src.runners.task038_hybrid_iterative as adapter_module

    seen = {}

    def fake_adapter(payload, output_directory, *, source_sha=None):
        seen["source_sha"] = source_sha
        seen["payload"] = payload
        return {"passed": True, "errors": []}

    monkeypatch.setattr(adapter_module, "run_hybrid_iterative", fake_adapter)
    status, errors = _dispatch_resolved_payload(
        _payload(),
        expected_method="hybrid_iterative",
        output_directory=tmp_path,
        expected_source_sha=SOURCE_SHA,
    )
    assert status == 0
    assert errors == []
    assert seen["source_sha"] == SOURCE_SHA


def test_task37c_runner_profile_defaults_remain_explicit_and_exact():
    from benchmarks.run_task037b_hybrid_iterative import parse_args, profile_from_args

    args = parse_args(
        [
            "--task037c-robustness-gate",
            "--case-label",
            "case",
            "--run-dir",
            "/tmp/task038-test-run",
            "--output",
            "/tmp/task038-test-record.json",
            "--verified-clean-sha",
            SOURCE_SHA,
            "--incident-phi-deg",
            "0",
            "--requested-modes",
            "120",
            "--mpi-size",
            "8",
            "--internal-traction-model",
            "full3d_one_cell_exact_schur",
            "--task037c-two-pass-side-correction",
        ]
    )
    profile = profile_from_args(args)
    assert profile.requested_modes == 120
    assert profile.candidate_modes == 240
    assert profile.max_it == 4500
    assert profile.side_residual_correction_steps == 2
