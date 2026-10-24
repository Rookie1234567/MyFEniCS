"""D5C-Y7 non-square R5 cutoff profiles and worker contracts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io.input_validation import load_and_resolve
from src.io.native_capacity_profile import (
    TASK40_PHI90_D5C_MODAL_PROFILE_BY_CASE,
    TASK40_PHI90_D5C_MODAL_RECTANGLES,
    native_profile_facts,
)
from src.runners.p6_condensed_direct import (
    _build_task40_rectangle_inventory,
    _direct_output_policy,
    _direct_run_contract,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input/task40para_phi90_mesh_modes_direct"
EXPECTED = {
    "M7_N9": (1140, 506, 826, 2.2807358642310815e-3),
    "M9_N14": (2204, 962, 1588, 1.1166163736995964e-3),
    "M9_N20": (3116, 1230, 2178, 2.6496148892488354e-5),
    "M10_N20": (3444, 1230, 2342, 7.626844689333332e-6),
}
PARENT_SHA = "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"


def _canonical_sha(value):
    encoded = json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _parent_inventory():
    modes = []
    rows = []
    for side in ("top", "bottom"):
        for m in range(-11, 12):
            for n in range(-20, 21):
                for polarization in ("s", "p"):
                    index = len(rows)
                    modes.append(
                        SimpleNamespace(
                            side=side, m=m, n=n, polarization=polarization
                        )
                    )
                    rows.append(
                        {
                            "mode_index": index,
                            "side": side,
                            "m": m,
                            "n": n,
                            "polarization": polarization,
                        }
                    )
    return tuple(modes), tuple(rows), PARENT_SHA


@pytest.mark.parametrize("label", tuple(EXPECTED))
def test_d5c_y7_modal_input_and_profile_preserve_parent_physics_and_r5(label):
    run_id = TASK40_PHI90_D5C_MODAL_PROFILE_BY_CASE[label]
    data = INPUT_DIR / f"d5c_y7_cut_{label.lower()}_r5_p6_direct.dat"
    spec = load_and_resolve(data)
    parent_spec = load_and_resolve(
        INPUT_DIR / "d5c_y7_r5_p6_direct.dat"
    )
    normalized = spec.as_jsonable()
    parent_normalized = parent_spec.as_jsonable()
    profile = native_profile_facts(run_id)
    options = profile["component_options"]
    mode = options["mode_selection"]
    route = _direct_run_contract(run_id)
    expected_count, prop, power, lower_bound = EXPECTED[label]
    m_max, n_max = TASK40_PHI90_D5C_MODAL_RECTANGLES[label]["bounds"]

    assert spec.identity["run_id"] == run_id
    assert normalized["solver"]["native_capacity_profile"] == run_id
    assert spec.physical_model_sha256 == parent_spec.physical_model_sha256
    for axis in ("x", "y", "z"):
        assert normalized["discretization"][f"mesh_axis_{axis}_values"] == (
            parent_normalized["discretization"][f"mesh_axis_{axis}_values"]
        )
    assert normalized["discretization"]["mesh_axis_cell_counts"] == [6, 30, 6]
    assert normalized["output"]["diffraction_order_max_m"] == 11
    assert normalized["output"]["diffraction_order_max_n"] == 20
    assert profile["operator_scope"].endswith(
        f"R5_parent_to_{label}_finite_rectangle"
    )
    assert mode["parent_inventory_scope"] == "R5_finite_rectangle_including_evanescent"
    assert mode["reference_identity"] == options["modal_truncation"]["parent_identity"]
    assert mode["reference_identity"]["run_directory"].endswith(
        "20261024T061944.262318Z"
    )
    assert mode["reference_identity"]["resolved_config_sha256"] == (
        "70943fba5c3531904651688371978d15afa0fc2fcfe447d6b6b31e1b4ff0047a"
    )
    assert mode["reference_identity"]["axis_cell_counts"] == [6, 30, 6]
    assert mode["policy"] == "explicit_centered_rectangle_subrectangle_from_parent_v1"
    assert mode["expected_mode_count"] == 3772
    assert mode["expected_mode_sha256"] == PARENT_SHA
    assert mode["active_rectangle_max_abs_m_n"] == [m_max, n_max]
    assert mode["expected_active_mode_count"] == expected_count
    assert mode["expected_active_mode_sha256"] == (
        TASK40_PHI90_D5C_MODAL_RECTANGLES[label]["active_mode_sha256"]
    )
    assert mode["expected_active_propagating_count"] == prop
    assert mode["expected_active_power_carrying_count"] == power
    assert mode["quadrature_inventory"] == "full_D5C_Y7_R5_parent_inventory"
    assert options["surface_quadrature"]["degree"] == 39
    assert options["volume_quadrature"]["degree"] == 15
    assert options["dtn_sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"
    assert route["parent_count"] == 3772
    assert route["parent_identity"] == mode["reference_identity"]
    assert route["active_count"] == expected_count
    assert route["selection_policy"] == mode["policy"]
    assert route["active_rectangle_max_abs_m_n"] == [m_max, n_max]
    assert route["residual_scope"] == (
        f"A6_D5C_Y7_R5_{label}_active_rectangle"
    )
    assert route["residual_scope"] != "A6_full_R5"
    assert route["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert route["omitted_boundary_relative_l2_lower_bound"] == lower_bound
    assert route["propagating_count"] == prop
    assert route["power_carrying_count"] == power
    output = _direct_output_policy(route)
    assert output["dtn_output_mode_count"] == expected_count
    assert output["omitted_dtn_channels"] == "NOT_COMPUTED"


@pytest.mark.parametrize("label", tuple(EXPECTED))
def test_d5c_y7_centered_rectangle_selection_binds_signed_keys_and_parent_indices(
    monkeypatch, label
):
    import src.solvers.fullspace_dtn_action as dtn

    profile = native_profile_facts(
        TASK40_PHI90_D5C_MODAL_PROFILE_BY_CASE[label]
    )["component_options"]["mode_selection"]
    route = _direct_run_contract(TASK40_PHI90_D5C_MODAL_PROFILE_BY_CASE[label])
    parent = _parent_inventory()
    m_max, n_max = route["active_rectangle_max_abs_m_n"]
    indices = tuple(
        index
        for index, mode in enumerate(parent[0])
        if abs(mode.m) <= m_max and abs(mode.n) <= n_max
    )
    active_rows = []
    for new_index, old_index in enumerate(indices):
        row = parent[1][old_index]
        active_rows.append({**row, "mode_index": new_index})

    def fake_manifest(active_modes, _cfg):
        assert len(active_modes) == EXPECTED[label][0]
        return tuple(active_rows), b"focused-test", profile["expected_active_mode_sha256"]

    monkeypatch.setattr(dtn, "build_ordered_mode_manifest", fake_manifest, raising=False)
    monkeypatch.setattr(
        dtn, "_canonical_json_bytes",
        lambda value: json.dumps(
            value, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"), sort_keys=True
        ).encode("ascii"),
        raising=False,
    )
    active, selection, selected = _build_task40_rectangle_inventory(
        parent, object(), route
    )
    assert selected == indices
    assert selection["policy"] == profile["policy"]
    assert selection["selected_parent_indices_sha256"] == profile[
        "expected_selected_parent_indices_sha256"
    ]
    assert selection["selected_signed_keys_sha256"] == profile[
        "expected_selected_signed_keys_sha256"
    ]
    assert selection["active_rectangle_max_abs_m_n"] == [m_max, n_max]
    assert len(active[0]) == EXPECTED[label][0]
    selected_keys = {
        (row["side"], row["m"], row["n"], row["polarization"])
        for row in active[1]
    }
    special = ("top", 0, -20, "s")
    assert special in {
        (row["side"], row["m"], row["n"], row["polarization"])
        for row in parent[1]
    }
    assert (special in selected_keys) is (label in {"M9_N20", "M10_N20"})
    assert selection["parent_mode_count"] == 3772


def test_d5c_y7_modal_selector_rejects_square_policy_for_non_square_rectangle():
    from src.runners.p6_condensed_direct import _direct_run_contract

    route = _direct_run_contract(
        TASK40_PHI90_D5C_MODAL_PROFILE_BY_CASE["M7_N9"]
    )
    route["selection_policy"] = "explicit_symmetric_subrectangle_from_parent_v1"
    with pytest.raises(ValueError, match="equal m/n bounds"):
        _build_task40_rectangle_inventory(_parent_inventory(), object(), route)


def test_d5c_y7_modal_selector_rejects_signed_key_hash_drift(monkeypatch):
    import src.solvers.fullspace_dtn_action as dtn

    route = _direct_run_contract(
        TASK40_PHI90_D5C_MODAL_PROFILE_BY_CASE["M9_N20"]
    )
    route["expected_selected_signed_keys_sha256"] = "0" * 64
    monkeypatch.setattr(
        dtn, "build_ordered_mode_manifest",
        lambda active, cfg: ((), b"", route["active_sha256"]),
        raising=False,
    )
    with pytest.raises(ValueError, match="signed keys"):
        _build_task40_rectangle_inventory(_parent_inventory(), object(), route)
