from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import qmc

from benchmarks import run_task036_robustness_scan as scan_driver
from benchmarks.run_task036_robustness_scan import (
    _exclusive_cpu_sets,
    _full3d_command,
    _hybrid_command,
    _load_points,
    _mpi_binding_environment,
    _point_values,
)


ROOT = Path(__file__).resolve().parents[2]
POINTS = ROOT / "benchmarks/task036_robustness_scan_points.csv"
POINTS_SHA256 = "01701c580355b8870c3865a6cb631d4db53f12a1a8fc3a2eaba3da59a26812d4"


def _rows() -> list[dict[str, str]]:
    with POINTS.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _physical_rows(
    rows: list[dict[str, str]],
    round_name: str,
) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row["round"] == round_name
        and row["incident_polarization"] == "S"
    ]


def _physical_tuple(row: dict[str, str]) -> tuple[float, float, float, float]:
    return tuple(
        float(row[field])
        for field in (
            "height_nm",
            "width_x_nm",
            "grazing_deg",
            "azimuth_deg",
        )
    )


def test_task036_scan_table_is_frozen_and_complete() -> None:
    rows = _rows()
    assert hashlib.sha256(POINTS.read_bytes()).hexdigest() == POINTS_SHA256
    assert len(rows) == 226
    assert Counter(row["round"] for row in rows) == {
        "A": 116,
        "B": 64,
        "C": 32,
        "D": 14,
    }
    assert len({row["point_id"] for row in rows}) == len(rows)

    polarizations: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        polarizations[row["physical_tuple_id"]].add(
            row["incident_polarization"]
        )
        assert 115.0 <= float(row["height_nm"]) <= 125.0
        assert 16.0 <= float(row["width_x_nm"]) <= 18.0
        assert 0.5 <= float(row["grazing_deg"]) <= 10.0
        assert 0.0 <= float(row["azimuth_deg"]) <= 90.0
        assert row["h_nm"] == "10.000000000000"
        assert (row["nx"], row["ny"], row["nz"]) == ("6", "4", "14")
        assert row["full3d_backend"] == "static_condensation"
        assert row["hybrid_backend"] == "static_condensation"
        assert row["initial_m_per_direction"] == "120"
        assert row["full3d_required_first"] == "true"
        assert row["frozen_status"] == "scheduled"
    assert all(value == {"S", "P"} for value in polarizations.values())


def test_task036_round_a_and_b_match_review_v2() -> None:
    rows = _rows()
    round_a = [_physical_tuple(row) for row in _physical_rows(rows, "A")]
    expected_a = [
        (120.0, 17.0, grazing, azimuth)
        for grazing in (0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0)
        for azimuth in (0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0)
    ]
    expected_a.extend(
        (120.0, 17.0, grazing, azimuth)
        for grazing in (0.5, 4.538499870338, 10.0)
        for azimuth in (54.25, 54.5, 54.75)
    )
    assert round_a == expected_a

    sentinels = (
        (0.5, 0.0),
        (0.5, 45.0),
        (0.5, 90.0),
        (2.0, 45.0),
        (4.538499870338, 54.420819282532),
        (10.0, 0.0),
        (10.0, 45.0),
        (10.0, 90.0),
    )
    expected_b = [
        (height, width, grazing, azimuth)
        for height, width in (
            (115.0, 16.0),
            (115.0, 18.0),
            (125.0, 16.0),
            (125.0, 18.0),
        )
        for grazing, azimuth in sentinels
    ]
    assert [
        _physical_tuple(row) for row in _physical_rows(rows, "B")
    ] == expected_b


def test_task036_round_c_is_the_frozen_sobol_design() -> None:
    rows = _rows()
    actual = np.asarray(
        [_physical_tuple(row) for row in _physical_rows(rows, "C")]
    )
    unit = qmc.Sobol(d=4, scramble=True, seed=3601).random_base2(m=4)
    expected = qmc.scale(
        unit,
        [115.0, 16.0, 0.5, 0.0],
        [125.0, 18.0, 10.0, 90.0],
    )
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=5.0e-13)
    assert np.min(np.abs(actual[:, 3] - 45.0)) <= 2.0
    assert np.min(np.abs(actual[:, 3] - 54.5)) <= 0.1
    assert np.any(actual[:, 2] < 2.0)
    assert np.any((actual[:, 2] >= 2.0) & (actual[:, 2] <= 8.0))
    assert np.any(actual[:, 2] > 8.0)
    assert np.any((actual[:, 0] < 116.0) | (actual[:, 0] > 124.0))
    assert np.any((actual[:, 1] < 16.2) | (actual[:, 1] > 17.8))


def test_task036_round_d_is_the_p6_pressure_set() -> None:
    rows = _rows()
    round_d = _physical_rows(rows, "D")
    assert all(row["nedelec_degree"] == "6" for row in round_d)
    assert [_physical_tuple(row) for row in round_d] == [
        (120.0, 17.0, grazing, azimuth)
        for grazing, azimuth in (
            (0.5, 0.0),
            (0.5, 45.0),
            (0.5, 90.0),
            (4.538499870338, 54.420819282532),
            (10.0, 0.0),
            (10.0, 45.0),
            (10.0, 90.0),
        )
    ]


def test_task036_driver_preserves_full3d_before_hybrid_identity(
    tmp_path: Path,
) -> None:
    selected = _load_points(
        POINTS,
        rounds={"A"},
        point_ids={"A001-P"},
        limit=None,
    )
    assert len(selected) == 1
    point = _point_values(selected[0])
    reference = tmp_path / "watchdog_summary.json"
    reference.write_text("full3d authority\n", encoding="utf-8")
    full3d = _full3d_command(
        point,
        source_sha="a" * 40,
        run_dir=tmp_path / "full3d",
        timeout_seconds=7200.0,
    )
    hybrid = _hybrid_command(
        point,
        source_sha="a" * 40,
        full3d_reference=reference,
        run_dir=tmp_path / "hybrid_m120",
        mode_count=120,
        timeout_seconds=7200.0,
        warning_gib=None,
        terminate_gib=None,
    )
    for command in (full3d, hybrid):
        rendered = " ".join(command)
        assert "--degree 5" in rendered
        assert "--h-nm 10.0" in rendered
        assert "--polarization-kind p" in rendered
        assert "--incident-grazing-deg 0.5" in rendered
        assert "--incident-phi-deg 0.0" in rendered
        assert "--grating-height-nm 120.0" in rendered
        assert "--grating-width-x-nm 17.0" in rendered
        assert "--task036-mesh-axis-cell-counts 6 4 14" in rendered
        assert "--task036-y-invariant-n0-alias-preflight" in rendered
        assert "--task036-dtn-direct-projection-audit" in rendered
        assert "--verified-clean-sha " + "a" * 40 in rendered
    assert "--task036-forward-robustness-gate" in full3d
    assert "--task036-domain-robustness-gate" in hybrid
    assert "--task036-scalar-stage4-reciprocal-basis" in hybrid
    assert hybrid[hybrid.index("--full3d-reference") + 1] == str(reference)
    assert hybrid[hybrid.index("--requested-modes") + 1] == "120"
    assert hybrid[hybrid.index("--candidate-modes") + 1] == "240"


def test_task036_parallel_dispatch_reserves_five_disjoint_mpi8_cpu_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scan_driver.os,
        "sched_getaffinity",
        lambda _pid: set(range(48)),
    )

    cpu_sets = _exclusive_cpu_sets(5)

    assert cpu_sets == tuple(
        tuple(range(first, first + 8))
        for first in (0, 8, 16, 24, 32)
    )
    assert len(set().union(*map(set, cpu_sets))) == 40


def test_task036_mpi_binding_keeps_each_rank_inside_the_cpu_lease() -> None:
    assert _mpi_binding_environment(tuple(range(8, 16))) == {
        "OMPI_MCA_hwloc_base_cpu_list": "8,9,10,11,12,13,14,15",
        "OMPI_MCA_hwloc_base_binding_policy": "cpu-list:ordered",
        "OMPI_MCA_hwloc_base_report_bindings": "true",
    }


def test_task036_parallel_dispatch_fails_closed_when_cpus_are_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scan_driver.os,
        "sched_getaffinity",
        lambda _pid: set(range(39)),
    )

    with pytest.raises(RuntimeError, match="needs 40 CPUs"):
        _exclusive_cpu_sets(5)
