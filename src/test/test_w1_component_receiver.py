"""W1 opt-in identity/consumer/clock tests: pure fixtures, no native solve."""

import datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.io.w1_receiver_contract import (
    MATH_COMMIT,
    load_w1,
    require_same_binding,
    validate_inventory,
    validate_originals,
)
from src.runners.w1_component_receiver import (
    charged_seconds,
    native_command,
    prerequisite,
    remaining,
)
from src.runners.w1_component_payload import atomic_arrays, guard, source_modules
from src.solvers.w1_boundary_components import (
    centered_phase_pair,
    consumers,
    relative_terms,
    run_local,
    probe_actions,
)

ROOT = Path(__file__).resolve().parents[2]


def spec_fixture(tmp_path):
    raw = (ROOT / "input/task042extra_feinn_5nm/v25_w1_control.dat").read_text()
    path = tmp_path / "one.dat"
    path.write_text(raw)
    return path


def inventory():
    z = {"real": 1.0, "imag": -0.2}
    rows = [
        {
            "side": side,
            "m": m,
            "n": -3,
            "polarization": pol,
            "mode_index": i,
            "k_vector": [dict(z) for _ in range(3)],
            "e_vector": [dict(z) for _ in range(3)],
            "traction_vector": [dict(z) for _ in range(3)],
            "projection_denominator": 0.75,
        }
        for i, (side, pol, m) in enumerate(
            [("top", "s", 1), ("top", "p", 1), ("bottom", "s", 1), ("bottom", "p", 1)]
        )
    ]
    keys = [[r["side"], r["m"], r["n"], r["polarization"]] for r in rows]
    key_sha = hashlib.sha256(
        json.dumps(keys, separators=(",", ":")).encode()
    ).hexdigest()
    ledger = {
        "target_mode_physical_identity_sha256": "physical",
        "original_size_ordered_mode_inventory_identity_sha256": "inventory",
    }
    return (
        {"modes": rows},
        ledger,
        {
            "count": 4,
            "key_sha": key_sha,
            "physical_sha": "physical",
            "inventory_sha": "inventory",
        },
    )


def test_one_dat_explicit_paths_and_ordinary_is_unchanged(tmp_path):
    path = spec_fixture(tmp_path)
    spec = load_w1(path)
    assert spec["math_commit"] == MATH_COMMIT
    assert spec["quadrature_degree"] == 60
    assert Path(spec["manifest_path"]).is_absolute()
    assert spec["manifest_path"] != spec["ledger_path"]
    path.write_text("schema_version = 1\n")
    assert load_w1(path) is None


@pytest.mark.parametrize(
    "old,new",
    [
        ("quadrature_degree = 60", "quadrature_degree = 30"),
        ("main_centered_nm", "unclear_units"),
        ("[25.0, 12.5, 0.0]", "[0.0, 0.0, 0.0]"),
        (MATH_COMMIT, "a" * 40),
        ('stage = "control"', 'stage = "w2"'),
    ],
)
def test_no_q_scan_or_silent_coordinate_source_change(tmp_path, old, new):
    path = spec_fixture(tmp_path)
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(ValueError, match="FIXED"):
        load_w1(path)


def test_no_extra_fields_or_output_escape(tmp_path):
    path = spec_fixture(tmp_path)
    original = path.read_text()
    path.write_text(original + "allow_global_factor = true\n")
    with pytest.raises(ValueError, match="FIELDS"):
        load_w1(path)
    path.write_text(
        original.replace(
            'output_root = "benchmarks/artifacts/task42extra/w1_receiver/v25"',
            'output_root = "/tmp/other"',
        )
    )
    with pytest.raises(ValueError, match="ESCAPES"):
        load_w1(path)


def test_missing_original_is_real_not_run(tmp_path):
    path = spec_fixture(tmp_path)
    spec = load_w1(path)
    spec.update(
        manifest_path=str(tmp_path / "no-manifest"),
        ledger_path=str(tmp_path / "no-ledger"),
    )
    result = validate_originals(spec)
    assert result["status"] == "NOT_RUN_INPUT_UNAVAILABLE"
    assert not result["received"] and len(result["missing"]) == 2


def test_present_wrong_original_refused_before_consumer(tmp_path):
    spec = load_w1(spec_fixture(tmp_path))
    for field in ("manifest_path", "ledger_path"):
        p = tmp_path / field
        p.write_text("{}")
        spec[field] = str(p)
    with pytest.raises(ValueError, match="HASH_OR_LEDGER"):
        validate_originals(spec)


def test_complete_inventory_fixture():
    document, ledger, options = inventory()
    assert len(validate_inventory(document, ledger, **options)) == 4


@pytest.mark.parametrize(
    "damage", ["order", "missing", "duplicate", "ledger", "H", "complex", "index"]
)
def test_damaged_original_records_rejected(damage):
    document, ledger, options = inventory()
    if damage == "order":
        document["modes"].reverse()
    if damage == "missing":
        document["modes"].pop()
    if damage == "duplicate":
        document["modes"][1] = document["modes"][0]
    if damage == "ledger":
        ledger["original_size_ordered_mode_inventory_identity_sha256"] = "other"
    if damage == "H":
        document["modes"][0]["projection_denominator"] = 0
    if damage == "complex":
        document["modes"][0]["e_vector"][0]["imag"] = float("nan")
    if damage == "index":
        document["modes"][0]["mode_index"] = -1
    with pytest.raises(ValueError, match="W1_"):
        validate_inventory(document, ledger, **options)


def test_worker_checker_cannot_use_different_input_binding(tmp_path):
    spec = load_w1(spec_fixture(tmp_path))
    with pytest.raises(ValueError, match="CONSUMER_BINDING"):
        require_same_binding(
            {"contract": {}, "receiver_source_sha": "a" * 40}, spec, consumer="checker"
        )


def test_native_command_uses_same_binding_and_one_abi_shell(tmp_path):
    command = native_command(
        tmp_path / "frozen", tmp_path / "run", tmp_path / "binding.json"
    )[-1]
    assert command.index("qualify_imports_only.py") < command.index(
        "activate_native_complex.sh"
    )
    assert "w1_component_payload.py" in command and "--binding " in command
    assert "run_task40_w1_boundary_probe.py" not in command
    assert "OMP_NUM_THREADS=1" in command
    assert ".venv-ml" not in command and "torch" not in command


def test_q60_is_explicit_in_all_numerical_consumers():
    assert set(consumers(60).values()) == {60} and len(consumers(60)) == 8
    with pytest.raises(ValueError):
        consumers(30)


def test_local_native_stream_receives_q60_and_all_loads(tmp_path):
    spec = load_w1(spec_fixture(tmp_path))
    spec["stage"] = "p4_top"
    layout = SimpleNamespace(x=np.linspace(-25, 25, 273), y=np.linspace(-12.5, 12.5, 5))
    config = SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2))
    called = {}

    def stream(**kwargs):
        called.update(kwargs)
        return {"arrays": {"witness_direct_q30_rule_points": np.array([0.5])}}

    result = run_local(spec, [1, 2, 3, 4], layout, config=config, stream=stream)
    assert called["boundary_quadrature_degree"] == 60
    assert len(called["known_interior_solution"]) == 108
    assert len(called["trace_values"]) == 192
    assert len(called["mode_alpha"]) == 4
    assert np.linalg.norm(called["known_interior_solution"]) > 0
    assert "witness_direct_q60_rule_points" in result["arrays"]
    assert not result["physical_incident_rhs_qualified"]


def test_centered_absolute_phase_is_reversible_without_changing_H():
    k = np.array([[0.7, -0.3, 0.4j], [-0.1, 0.6, -0.2j]])
    forward, reverse = centered_phase_pair(k, [25, 12.5, 0])
    np.testing.assert_allclose(forward * reverse, 1, rtol=1e-15)
    np.testing.assert_allclose(abs(forward), 1, rtol=1e-15)
    assert not np.allclose(forward, 1)


def test_original_norm_and_zero_flags_are_not_enlarged():
    value = np.array([1e-100 + 2e-100j, 3e-100j])
    result = relative_terms(value * 1.0001, value)
    assert result["denominator"] == result["reference_norm"] and not result["near_zero"]
    assert result["relative"] > 1e-5
    with pytest.raises(ValueError):
        relative_terms(value * float("nan"), value)


def test_monotonic_import_delay_and_save_reserve():
    utc = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)
    window = {
        "schema": "task42extra.w1-receiver-window.v1",
        "budget_seconds": 14400,
        "numerical_and_checker_budget_seconds": 7200,
        "delivery_reserve_seconds": 1800,
        "old_windows_not_reset": True,
        "deadline_monotonic": 2000,
        "deadline_utc": (utc + datetime.timedelta(seconds=1900)).isoformat(),
    }
    assert remaining(window, now=100, utc_now=utc) == 1900
    assert (
        remaining(window, now=190, utc_now=utc + datetime.timedelta(seconds=90)) == 1810
    )
    with pytest.raises(RuntimeError, match="TIMEBASE"):
        remaining(window, now=100, utc_now=utc + datetime.timedelta(seconds=6))
    window["budget_seconds"] = 7200
    with pytest.raises(ValueError):
        remaining(window, now=100, utc_now=utc)


def test_p2_requires_p1_before_native_tensor(tmp_path):
    (tmp_path / "control").mkdir()
    (tmp_path / "control/receiver_result.json").write_text(
        json.dumps(
            {
                "cleared": True,
                "component_status": "CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE",
            }
        )
    )
    (tmp_path / "boundary_check").mkdir()
    (tmp_path / "boundary_check/component_result.json").write_text(
        json.dumps({"status": "P1_Q60_FULL_MODE_FAIL", "coverage_complete": True})
    )
    with pytest.raises(ValueError, match="P1_FULL"):
        prerequisite("p6_top", tmp_path)


def test_atomic_raw_roundtrip_and_damaged_source(tmp_path):
    path = tmp_path / "one.npz"
    arrays = {"c": np.array([0.7 + 0.8j]), "q": np.array(60)}
    receipt = atomic_arrays(path, arrays)
    assert receipt["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert not path.with_suffix(".tmp").exists()
    with pytest.raises(FileNotFoundError):
        source_modules(
            ROOT, tmp_path, {"contract_source_manifest_path": str(tmp_path / "absent")}
        )


def test_deadline_guard_prevents_trial_in_save_window():
    import time

    now = datetime.datetime.now(datetime.timezone.utc)
    binding = {
        "window": {
            "deadline_monotonic": time.monotonic() + 500,
            "deadline_utc": (now + datetime.timedelta(seconds=500)).isoformat(),
        },
        "stage_deadline_monotonic": time.monotonic() + 149,
    }
    with pytest.raises(TimeoutError, match="SAVE_RESERVE"):
        guard(binding)


def test_pending_and_failed_work_is_charged_across_namespaces():
    entries = [
        {"origin_monotonic": 10, "elapsed_seconds": 20},
        {"origin_monotonic": 80},
    ]
    assert charged_seconds(entries, 100) == 40


def test_actual_action_and_load_api_get_one_q60():
    called = []

    class MockAction:
        def __init__(self, layout, modes, q, **kwargs):
            called.append((q, kwargs["face_inventory"]))

        def project_components(self, t):
            called.append("projection")
            return np.zeros((4, 2), complex)

        def recover(self, t):
            called.append("recovery")
            return np.zeros(4, complex)

        def apply(self, t, *, adjoint=False):
            called.append("adjoint" if adjoint else "forward")
            return t

        def modal_rhs(self, a):
            called.append("nonzero_load")
            assert np.linalg.norm(a) > 0
            return np.zeros(5, complex)

    result = probe_actions(
        SimpleNamespace(rows=5), [1, 2, 3, 4], 60, action_factory=MockAction
    )
    assert called[0] == (60, (("top", 100, 1), ("bottom", 100, 1)))
    assert set(called[1:]) == {
        "projection",
        "recovery",
        "forward",
        "adjoint",
        "nonzero_load",
    }
    assert result["trace"].dtype == np.complex128
