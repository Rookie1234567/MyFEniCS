from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import subprocess

import pytest

from src.forward_data.orders import FIXED_M_ORDERS, extract_fixed_orders
from src.forward_data.schema import (
    TASK001_OBSERVABLE_SCHEMA_VERSION,
    ForwardParameters,
    Task001ForwardParameters,
    task001_parameter_catalog,
)
from src.forward_data.task001_config import task001_config_identity
from src.forward_data.task001_campaign import task001_hybrid_command
from src.forward_data import task001_campaign
from src.forward_data.resource_policy import GIB, predict_p6_h7p5
from src.forward_data.topology import topology_audit
from src.forward_data.watchdog import (
    EXIT_CONTROLLED_MEMORY,
    EXIT_CONTROLLED_TIMEOUT,
    run_with_watchdog,
)
from src.forward_data import watchdog
from benchmarks.run_task032_phase6_augmented import _parse_args


def _parameters(**updates) -> Task001ForwardParameters:
    values = dict(
        height_nm=120.0, width_x_nm=17.0, theta_deg=80.0, phi_deg=0.0,
        incident_polarization="S", model_id="HF10",
    )
    values.update(updates)
    return Task001ForwardParameters(**values)


def test_v2_schema_boundaries_and_v1_compatibility() -> None:
    assert task001_parameter_catalog()["physics"]["wavelength_nm"]["allowed"] == [13.5]
    for height in (115.0, 125.0):
        for width in (16.0, 18.0):
            _parameters(height_nm=height, width_x_nm=width).validate()
    for field, value, message in (
        ("height_nm", 114.9, "height_nm"), ("width_x_nm", 18.1, "width_x_nm"),
        ("theta_deg", 79.0, "theta_deg"), ("phi_deg", 45.0, "phi_deg"),
        ("incident_polarization", "X", "polarization"), ("mpi_ranks", 8, "mpi_ranks"),
    ):
        with pytest.raises(ValueError, match=message):
            _parameters(**{field: value}).validate()
    legacy = ForwardParameters.from_mapping({"model_id": "euv_2d_complex_absorption_v1"})
    assert legacy.preset == "2d_complex_absorption"


def test_config_factory_has_exact_identity() -> None:
    identity = task001_config_identity(_parameters(height_nm=115, width_x_nm=16, phi_deg=90, incident_polarization="P"))
    assert identity["axis_cell_counts"] == [6, 3, 14]
    assert identity["theta_deg"] == 80
    assert identity["phi_deg"] == 90
    assert identity["polarization"] == "P"
    assert identity["solver_path"] == "modal-schur-memory-minimal"


def test_task001_dry_command_identity(tmp_path: Path) -> None:
    command = task001_hybrid_command(
        _parameters(), root=tmp_path, baseline_sha="a" * 40,
        output_record=tmp_path / "record.json", memory_stages=tmp_path / "stages.jsonl",
    )
    assert command[:3] == ["mpiexec", "-n", "2"]
    assert "--task001-surrogate-pilot-gate" in command
    assert command[command.index("--degree") + 1] == "6"
    assert command[command.index("--candidate-modes") + 1] == "240"
    assert command[command.index("--verified-clean-sha") + 1] == "a" * 40
    module_index = command.index("benchmarks.run_task032_phase6_augmented")
    parsed = _parse_args(command[module_index + 1 :])
    assert parsed.task001_surrogate_pilot_gate is True
    assert parsed.task001_model_id == "HF10"


def test_task001_lf5_cli_is_explicitly_supported(tmp_path: Path) -> None:
    command = task001_hybrid_command(
        _parameters(model_id="LF5"), root=tmp_path, baseline_sha="b" * 40,
        output_record=tmp_path / "record.json", memory_stages=tmp_path / "stages.jsonl",
    )
    parsed = _parse_args(command[command.index("benchmarks.run_task032_phase6_augmented") + 1 :])
    assert parsed.degree == parsed.modal_degree == 5


def test_p6_h7p5_prediction_has_three_conservative_estimates() -> None:
    prediction = predict_p6_h7p5(measured_h10_peak_bytes=8 * GIB)
    assert prediction["h10_axis_counts"] == [6, 3, 14]
    assert prediction["h7p5_axis_counts"] == [9, 4, 20]
    assert len(prediction["estimates"]) == 3
    assert prediction["central_estimate_bytes"] > 8 * GIB
    assert prediction["conservative_estimate_bytes"] >= prediction["central_estimate_bytes"]


def test_task001_formal_preflight_fails_closed_on_dirty_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        task001_campaign, "source_identity",
        lambda root: {"dirty": True, "source_sha": "a" * 40},
    )
    with pytest.raises(RuntimeError, match="clean source"):
        task001_campaign.formal_preflight(tmp_path, "a" * 40)


@pytest.mark.parametrize("model_id,counts", [("HF10", [6, 3, 14]), ("HF7P5", [9, 4, 20])])
def test_fixed_topology_across_nine_geometry_points(model_id: str, counts: list[int]) -> None:
    audits = [
        topology_audit(_parameters(model_id=model_id, height_nm=height, width_x_nm=width))
        for height in (115.0, 120.0, 125.0)
        for width in (16.0, 17.0, 18.0)
    ]
    for field in ("axis_cell_counts", "logical_topology_sha256", "material_region_cell_counts", "floquet_pairing_counts", "element_identity"):
        assert len({json.dumps(row[field], sort_keys=True) for row in audits}) == 1
    assert audits[0]["axis_cell_counts"] == counts
    assert all(row["positive_volume"] and row["material_plane_alignment"] for row in audits)
    assert min(row["minimum_axis_jacobian"] for row in audits) > 0
    assert max(row["maximum_aspect_ratio"] for row in audits) < 5


def _order(side: str, m: int, n: int, pol: str, power: float | None, propagating: bool = True):
    return {
        "side": side, "m": m, "n": n, "polarization": pol,
        "power": power, "propagating": propagating,
        "outgoing_amplitude_at_boundary": [float(m), float(n)],
    }


def test_order_extractor_fixed_identity_null_and_leakage() -> None:
    rows = [
        _order(side, m, 0, pol, None if m == 1 else 0.01, m != 1)
        for side in ("bottom", "top") for m in reversed(FIXED_M_ORDERS) for pol in ("p", "s")
    ]
    rows.extend([_order("top", 2, 1, "s", 0.003), _order("bottom", 2, -1, "p", 0.004)])
    result = extract_fixed_orders(rows)
    assert result["schema_version"] == TASK001_OBSERVABLE_SCHEMA_VERSION
    assert result["fixed_m_order"] == list(FIXED_M_ORDERS)
    assert result["n_nonzero_leakage_power"] == pytest.approx(0.007)
    assert result["missing"] == []
    assert [row["m"] for row in result["orders"][:18:2]] == list(FIXED_M_ORDERS)
    assert all(row["power"] is None for row in result["orders"] if row["m"] == 1)


def test_order_extractor_reports_missing_and_duplicate() -> None:
    result = extract_fixed_orders([_order("top", 0, 0, "s", 0.1)])
    assert len(result["missing"]) == 35
    with pytest.raises(ValueError, match="duplicate"):
        extract_fixed_orders([_order("top", 0, 0, "s", 0.1)] * 2)


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONUNBUFFERED": "1"}


def test_watchdog_completed_streaming_and_heartbeat(tmp_path: Path) -> None:
    result = run_with_watchdog(
        [sys.executable, "-c", "print('ready', flush=True)"], cwd=tmp_path, env=_env(),
        output_dir=tmp_path / "ok", timeout_seconds=5, memory_limit_bytes=512 * 1024**2,
        sample_interval_seconds=0.02, heartbeat_seconds=0.02,
    )
    assert result.status == "completed" and result.return_code == 0 and result.cleanup_complete
    assert "ready" in (tmp_path / "ok" / "stdout.log").read_text()
    assert (tmp_path / "ok" / "resource_timeline.jsonl").is_file()


def test_watchdog_tolerates_proc_exit_race(monkeypatch: pytest.MonkeyPatch) -> None:
    def vanished(_path: Path) -> str:
        raise ProcessLookupError(3, "process vanished")

    monkeypatch.setattr(Path, "read_text", vanished)
    assert watchdog._memory_for_pid(123456) is None


def test_watchdog_timeout_cleans_owned_process_group(tmp_path: Path) -> None:
    code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)"
    result = run_with_watchdog(
        [sys.executable, "-c", code], cwd=tmp_path, env=_env(), output_dir=tmp_path / "timeout",
        timeout_seconds=0.15, memory_limit_bytes=512 * 1024**2, sample_interval_seconds=0.02,
        grace_seconds=0.1,
    )
    assert result.status == "controlled_stop_timeout"
    assert result.return_code == EXIT_CONTROLLED_TIMEOUT
    with pytest.raises(ProcessLookupError):
        os.killpg(result.process_group_id, 0)


def test_watchdog_memory_stop(tmp_path: Path) -> None:
    result = run_with_watchdog(
        [sys.executable, "-c", "x=bytearray(64*1024*1024); import time; time.sleep(30)"],
        cwd=tmp_path, env=_env(), output_dir=tmp_path / "memory", timeout_seconds=5,
        memory_limit_bytes=24 * 1024**2, sample_interval_seconds=0.02, grace_seconds=0.1,
    )
    assert result.status == "controlled_stop_resource_memory"
    assert result.return_code == EXIT_CONTROLLED_MEMORY
    assert result.peak_rss_bytes >= 24 * 1024**2


def test_watchdog_signal_cleans_owned_process_group(tmp_path: Path) -> None:
    result_path = tmp_path / "signal_result.json"
    output_dir = tmp_path / "signal_watchdog"
    helper = (
        "import json,os,sys; from dataclasses import asdict; from pathlib import Path; "
        "from src.forward_data.watchdog import run_with_watchdog; "
        f"r=run_with_watchdog([sys.executable,'-c','import time; time.sleep(30)'],cwd=Path({str(tmp_path)!r}),"
        f"env=os.environ,output_dir=Path({str(output_dir)!r}),timeout_seconds=30,memory_limit_bytes=536870912,"
        "sample_interval_seconds=.02,grace_seconds=.1); "
        f"Path({str(result_path)!r}).write_text(json.dumps(asdict(r)))"
    )
    process = subprocess.Popen([sys.executable, "-c", helper], cwd=Path(__file__).resolve().parents[2])
    time.sleep(0.2)
    process.terminate()
    assert process.wait(timeout=5) == 0
    result = json.loads(result_path.read_text())
    assert result["status"] == "controlled_stop_signal"
    assert result["return_code"] == 128 + 15
    with pytest.raises(ProcessLookupError):
        os.killpg(result["process_group_id"], 0)
