from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path

import pytest

from benchmarks import postprocess_task40_review_v4_directional_cross as runner
from benchmarks import subreaper_watchdog


def test_parent_uses_fresh_watchdog_directory_and_review_v4_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "result.json"
    expected_watchdog = output.parent / "four_corner_volume_v1_watchdog"

    attempted_fe_imports: list[str] = []
    original_import = builtins.__import__
    forbidden = (
        "dolfinx",
        "src.postprocessing.task40_saved_field_h_comparison",
        "benchmarks.postprocess_task40_p1_saved_fields_common_subcells",
    )

    def record_import(name: str, *args: object, **kwargs: object) -> object:
        if any(name == item or name.startswith(item + ".") for item in forbidden):
            attempted_fe_imports.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", record_import)

    def fake_supervise(command: list[str], directory: Path, **kwargs: object) -> dict:
        assert directory == expected_watchdog
        assert not directory.exists()
        assert attempted_fe_imports == []
        assert command[1:3] == [
            "-m", "benchmarks.postprocess_task40_review_v4_directional_cross"
        ]
        assert kwargs["wall_seconds"] == 43_200
        assert kwargs["interval"] == 0.25
        assert kwargs["grace_seconds"] == 30
        assert kwargs["hard_stop_immediate"] is True
        assert kwargs["stop_on_global_swap"] is False
        assert kwargs["allow_swap_observation"] is False
        assert kwargs["memory_policy"] == subreaper_watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY
        assert kwargs["pss_sampling_policy"] == "disabled_by_profile"
        assert kwargs["time_policy"] == "observe_only"
        environment = kwargs["worker_environment"]
        assert environment["OMP_NUM_THREADS"] == "1"
        assert environment["OPENBLAS_NUM_THREADS"] == "1"
        assert command[command.index("--output") + 1] == str(output)
        output.write_text("{}", encoding="utf-8")
        return {"leader_exit_code": 0}

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(runner.__file__),
            "--output",
            str(output),
        ],
    )

    assert runner.main() == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {}


def test_atomic_result_rejects_nonfinite_numbers(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    with pytest.raises(ValueError):
        runner._atomic_json(output, {"value": float("nan")})

    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_mode_diagnostics_keep_first_and_g1_denominators() -> None:
    from benchmarks import postprocess_task40_review_v4_modes as modes

    key = ("top", 0, 0, "s")
    inventories = {
        "G00": {key: {"outgoing_amplitude_at_boundary": [1.0, 0.0]}},
        "G10": {key: {"outgoing_amplitude_at_boundary": [2.0, 0.0]}},
        "G01": {key: {"outgoing_amplitude_at_boundary": [4.0, 0.0]}},
        "G11": {key: {"outgoing_amplitude_at_boundary": [8.0, 0.0]}},
    }
    comparison = {
        "all_ordered_mode_comparisons": [
            {
                "key": list(key),
                "absolute_amplitude_difference": 2.0,
                "relative_difference_to_first_amplitude": 2.0,
            }
        ]
    }

    modes._add_g1_normalization(comparison, inventories["G11"])
    interaction = modes._interaction_rows(inventories)

    assert comparison["all_ordered_mode_comparisons"][0][
        "relative_difference_to_first_amplitude"
    ] == 2.0
    assert comparison["all_ordered_mode_comparisons"][0][
        "g1_normalized_amplitude_difference"
    ] == 0.25
    assert comparison["all_ordered_mode_comparisons"][0][
        "g1_normalized_denominator"
    ] == 8.0
    assert len(interaction) == 1
    assert interaction[0]["mixed_complex"] == [3.0, 0.0]
    assert interaction[0]["relative_to_G00_amplitude"] == 3.0
    assert interaction[0]["incident_normalized_mixed_difference"] == 3.0
    assert interaction[0]["g1_normalized_mixed_difference"] == 0.375
