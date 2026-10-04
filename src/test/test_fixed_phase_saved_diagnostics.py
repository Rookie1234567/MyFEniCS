"""Small fixtures for frozen negative-state selection and independent audits."""

import json
from types import SimpleNamespace
import numpy as np
import pytest

from src.solvers.fixed_phase_saved_diagnostics import (
    inspect_state,
    choose_closed_negative,
)
from benchmarks.fixed_phase_checker import saved_port_recovery


def test_interior_port_support_preserves_exact_zero_and_nonzero_terms():
    from benchmarks.fixed_phase_checker import interior_port_support

    arrays = dict(
        masters=np.array([0, 2, 3]),
        idofs=np.array([[2]]),
        br=np.array([0, 1, 1]),
        bv=np.array([1, 0, 1e-20], complex),
        dr=np.array([0, 1]),
        dv=np.array([1, 0], complex),
    )
    r = interior_port_support(arrays)
    assert r["blocks"]["bv"]["exact_nonzeros"] == 1
    assert r["blocks"]["bv"]["exact_zeros"] == 1
    assert r["blocks"]["dv"]["exact_nonzeros"] == 0
    assert r["no_terms_removed"] and not r["accuracy_or_recovery_qualified"]
    with pytest.raises(ValueError):
        interior_port_support(dict(arrays, idofs=np.array([[1]])))


def fixture():
    native = dict(
        H=np.array([2.0]),
        dp=np.array([0, 0]),
        dr=np.array([0, 1]),
        dv=np.array([2.0, 1j]),
        gp=np.zeros(1, complex),
        masters=np.array([0, 3]),
        background=np.array([0.2, 0.7], complex),
        background_alpha=np.array([2j]),
    )
    c = np.array([1 + 0.1j, 0.7 - 0.3j])
    a = np.array([(2 * c[0] + 1j * c[1]) / 2])
    state = dict(
        c_scattered=c,
        c_total=c + native["background"],
        alpha_scattered=a,
        alpha_total=a + native["background_alpha"],
        background=native["background"].copy(),
        background_alpha=native["background_alpha"].copy(),
        masters=native["masters"].copy(),
    )
    return native, state


def test_complete_negative_layout_and_raw_port_recovery():
    native, state = fixture()
    p = SimpleNamespace(size=2, np=1, a=native)
    inspect_state(p, state)
    result = saved_port_recovery(native, state)
    assert result["original_port_recovery_relative"] <= 1e-14
    assert result["no_FE_or_solver_calls"]


@pytest.mark.parametrize("kind", ["master", "background", "affine", "dtype", "missing"])
def test_corrupted_negative_state_is_rejected(kind):
    native, state = fixture()
    p = SimpleNamespace(size=2, np=1, a=native)
    if kind == "master":
        state["masters"] = np.array([3, 0])
    if kind == "background":
        state["background"] = np.array([0.1, 0.1], complex)
    if kind == "affine":
        state["c_total"] = state["c_total"] + 0.1
    if kind == "dtype":
        state["c_scattered"] = state["c_scattered"].astype(np.complex64)
    if kind == "missing":
        state.pop("masters")
    with pytest.raises((ValueError, KeyError)):
        inspect_state(p, state)


def test_wrong_saved_alpha_stays_a_negative():
    native, state = fixture()
    state["alpha_scattered"] = state["alpha_scattered"] + 1
    state["alpha_total"] = state["alpha_scattered"] + state["background_alpha"]
    r = saved_port_recovery(native, state)
    assert r["original_port_recovery_relative"] > 1e-10


def setup_closed(root, *, cleared=True, released=True):
    d = root / "results/task42extra/task42extra_v20_o3_0"
    d.mkdir(parents=True)
    artifact = root / "benchmarks/artifacts/task42extra/saved"
    artifact.mkdir(parents=True)
    for name in ("native.npz", "field_state.npz", "identity.json"):
        (artifact / name).write_bytes(b"fixture path only, not a numerical state")
    (d / "run_manifest.json").write_text(
        json.dumps(
            dict(
                artifact_directory=str(artifact),
                role="O3",
                group="B",
                stage="v20_o3",
                source_sha="fixture_source",
            )
        )
    )
    (d / "run_summary.json").write_text(json.dumps(dict(descendants_cleared=cleared)))
    (d / "worker_failure.json").write_text(
        json.dumps(dict(source_sha="fixture_source", reason="RECOVERY_FAILED"))
    )
    (d / "events.jsonl").write_text(
        json.dumps(
            dict(
                phase="reference_release_before_postprocessing",
                values=dict(
                    factor_released=released,
                    matrix_released=True,
                    rss_before_release_bytes=500,
                    rss_after_release_bytes=200,
                ),
            )
        )
        + "\n"
    )
    return d


def test_only_closed_released_saved_state_is_selected(tmp_path):
    setup_closed(tmp_path)
    assert choose_closed_negative(tmp_path, "O3") is not None


@pytest.mark.parametrize("kind", ["active", "factor", "missing", "source", "scope"])
def test_invalid_negative_source_is_not_reused(tmp_path, kind):
    d = setup_closed(tmp_path, cleared=kind != "active", released=kind != "factor")
    if kind == "missing":
        (tmp_path / "benchmarks/artifacts/task42extra/saved/field_state.npz").unlink()
    if kind == "source":
        (d / "worker_failure.json").write_text(
            json.dumps(dict(source_sha="foreign", reason="FAILED"))
        )
    if kind == "scope":
        m = json.loads((d / "run_manifest.json").read_text())
        m["artifact_directory"] = str(tmp_path / "foreign")
        (d / "run_manifest.json").write_text(json.dumps(m))
    if kind in ("source", "scope"):
        with pytest.raises(ValueError):
            choose_closed_negative(tmp_path, "O3")
    else:
        assert choose_closed_negative(tmp_path, "O3") is None


def test_pure_recovery_rejects_missing_and_corrupt_port_map():
    native, state = fixture()
    damaged = dict(state)
    damaged.pop("masters")
    with pytest.raises(ValueError):
        saved_port_recovery(native, damaged)
    damaged = dict(native, dr=np.array([0, 2]))
    with pytest.raises(ValueError):
        saved_port_recovery(damaged, state)


def test_ordinary_vs_phase_control_never_becomes_accuracy_authority():
    from src.test.test_fixed_phase_contract import _saved_physics_fixture
    from benchmarks.fixed_phase_checker import compare_from_arrays

    z = _saved_physics_fixture()
    for k in (
        "selected_total_E",
        "selected_total_H",
        "selected_scattered_E",
        "selected_scattered_H",
    ):
        z[k] = np.ones((6, 3), complex)
    for k in ("total_projection", "scattered_projection", "outgoing_origin"):
        z[k] = np.ones(340, complex)
    eq = dict.fromkeys(
        (
            "native_relative",
            "augmented_relative",
            "original_total_augmented_relative",
            "independent_physical_weak",
            "recovery",
        ),
        0.0,
    )
    eq.update(channels=340, full_FE_recovered=True)
    raw = np.zeros((6, 4, 3))
    raw[:, :, 1:] = 1
    r = compare_from_arrays(
        {"O3_vs_E3_q15": raw, "O3_vs_E3_q30": raw.copy()},
        {"O3": z, "E3": z},
        {"O3": eq, "E3": eq},
    )
    assert not r["reference_qualified"]
    assert not r["comparisons"]["O3_vs_E3"]["qualified"]
