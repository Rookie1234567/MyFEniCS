from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

K_COUNTS = {1: 36, 2: 100, 3: 196, 4: 324}
ROOT = Path(__file__).resolve().parents[2]


def _fake_parent_inventory():
    modes = []
    rows = []
    for side in ("top", "bottom"):
        for m in range(-4, 5):
            for n in range(-8, 9):
                for polarization in ("s", "p"):
                    mode = SimpleNamespace(
                        side=side,
                        m=m,
                        n=n,
                        polarization=polarization,
                    )
                    modes.append(mode)
                    rows.append(
                        {
                            "mode_index": len(rows),
                            "side": side,
                            "m": m,
                            "n": n,
                            "polarization": polarization,
                        }
                    )
    return tuple(modes), tuple(rows), "p" * 64


def _canonical_sha(value):
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


@pytest.mark.parametrize("k,expected_count", sorted(K_COUNTS.items()))
def test_task40_k_profile_binds_parent_and_selected_mode_identities(k, expected_count):
    from src.io.native_capacity_profile import (
        TASK40_PHI90_D15_K_SELECTIONS,
        native_profile_facts,
    )
    from src.runners.p6_condensed_direct import (
        _bind_task40_selected_parent_index_identity,
        _direct_output_policy,
        _direct_run_contract,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _active_fe_port_output_identity,
    )

    identity = f"task40para_phi90_13p5_D15_Y3_K{k}_p6_direct_v1"
    profile = native_profile_facts(identity)
    options = profile["component_options"]
    mode = options["mode_selection"]
    route = _direct_run_contract(identity)

    assert profile["operator_scope"] == (
        f"task40_phi90_D15_Y3_R13_parent_to_K{k}_subrectangle"
    )
    assert options["directional_mesh_comparison"]["case"] == "Y3"
    assert options["directional_mesh_comparison"]["axis_cell_counts"] == [6, 10, 6]
    assert mode["parent_rectangle_max_abs_m_n"] == [4, 8]
    assert mode["active_rectangle_max_abs_m_n"] == [k, k]
    assert mode["expected_mode_count"] == 612
    assert mode["expected_active_mode_count"] == expected_count
    assert mode["expected_mode_sha256"] == (
        "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
    )
    assert (
        mode["expected_active_mode_sha256"]
        == TASK40_PHI90_D15_K_SELECTIONS[k]["active_mode_sha256"]
    )
    assert options["surface_quadrature"]["degree"] == 28
    assert options["dtn_sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"
    assert route["parent_count"] == 612
    assert route["active_count"] == expected_count
    assert route["truncated"] is True
    assert route["parent_rectangle_max_abs_m_n"] == [4, 8]
    assert route["active_rectangle_max_abs_m_n"] == [k, k]
    assert route["active_sha256"] == mode["expected_active_mode_sha256"]
    assert route["surface_quadrature_degree"] == 28
    assert route["direct_factor_evidence_mode_keys"] == tuple(
        key
        for side in ("top", "bottom")
        for key in ((side, -k, 0, "p"), (side, 0, 0, "s"), (side, k, 0, "p"))
    )

    route["parent_sha256"] = route["expected_mode_sha256"]
    route["sparse_cutoff_identity_sha256"] = "f" * 64
    _bind_task40_selected_parent_index_identity(
        route,
        {
            "selected_parent_indices_sha256": mode[
                "expected_selected_parent_indices_sha256"
            ]
        },
    )
    output = _direct_output_policy(route)
    assert output["active_port_outputs_only"] is False
    assert output["omitted_dtn_channels"] == "NOT_COMPUTED"
    identity = _active_fe_port_output_identity(
        output["active_fe_port_output_contract"],
        active_mode_count=expected_count,
        active_mode_sha256=route["active_sha256"],
        sparse_cutoff_policy=route["sparse_cutoff_policy"],
        sparse_cutoff_relative_tolerance=route["sparse_cutoff_relative_tolerance"],
        sparse_cutoff_identity_sha256=route["sparse_cutoff_identity_sha256"],
    )
    assert identity["omitted_channel_values"] == "NOT_COMPUTED"
    bad_route = dict(route, selected_parent_indices_sha256=None)
    with pytest.raises(ValueError, match="parent-index hash"):
        _bind_task40_selected_parent_index_identity(
            bad_route,
            {"selected_parent_indices_sha256": "0" * 64},
        )


@pytest.mark.parametrize("k,expected_count", sorted(K_COUNTS.items()))
def test_task40_rectangle_selector_preserves_exact_parent_order_and_hashes(
    monkeypatch, k, expected_count
):
    import src.solvers.fullspace_dtn_action as dtn
    from src.runners.p6_condensed_direct import _build_task40_rectangle_inventory

    parent_modes, parent_rows, parent_sha = _fake_parent_inventory()
    indices = tuple(
        i
        for i, mode in enumerate(parent_modes)
        if abs(mode.m) <= k and abs(mode.n) <= k
    )
    selected_key_rows = [
        {
            "side": parent_rows[i]["side"],
            "m": parent_rows[i]["m"],
            "n": parent_rows[i]["n"],
            "polarization": parent_rows[i]["polarization"],
        }
        for i in indices
    ]
    expected_active_sha = f"a{k}" * 32
    route = {
        "parent_count": 612,
        "expected_mode_sha256": parent_sha,
        "active_rectangle_max_abs_m_n": [k, k],
        "active_count": expected_count,
        "expected_selected_signed_keys_sha256": _canonical_sha(selected_key_rows),
        "expected_selected_parent_indices_sha256": _canonical_sha(list(indices)),
        "active_sha256": expected_active_sha,
        "operator_scope": f"test_Y3_K{k}",
    }

    def fake_manifest(modes, _cfg):
        rows = tuple(
            {
                "mode_index": index,
                "side": mode.side,
                "m": mode.m,
                "n": mode.n,
                "polarization": mode.polarization,
            }
            for index, mode in enumerate(modes)
        )
        return rows, b"test", expected_active_sha

    monkeypatch.setattr(
        dtn, "build_ordered_mode_manifest", fake_manifest, raising=False
    )
    active, selection, selected_indices = _build_task40_rectangle_inventory(
        (parent_modes, parent_rows, parent_sha), object(), route
    )

    assert len(active[0]) == expected_count
    assert selected_indices == indices
    assert selection["active_rectangle_max_abs_m_n"] == [k, k]
    assert selection["selected_parent_indices_sha256"] == _canonical_sha(list(indices))
    assert selection["selected_signed_keys_sha256"] == _canonical_sha(selected_key_rows)
    assert selection["side_polarization_counts"] == {
        f"{side}_{pol}": (2 * k + 1) ** 2
        for side in ("bottom", "top")
        for pol in ("s", "p")
    }
    assert all(active[1][i]["mode_index"] == i for i in range(expected_count))


def test_task40_rectangle_selector_rejects_parent_hash_or_key_drift(monkeypatch):
    import src.solvers.fullspace_dtn_action as dtn
    from src.runners.p6_condensed_direct import _build_task40_rectangle_inventory

    parent_modes, parent_rows, parent_sha = _fake_parent_inventory()
    indices = tuple(
        i
        for i, mode in enumerate(parent_modes)
        if abs(mode.m) <= 1 and abs(mode.n) <= 1
    )
    selected_key_rows = [
        {
            "side": parent_rows[i]["side"],
            "m": parent_rows[i]["m"],
            "n": parent_rows[i]["n"],
            "polarization": parent_rows[i]["polarization"],
        }
        for i in indices
    ]
    route = {
        "parent_count": 612,
        "expected_mode_sha256": parent_sha,
        "active_rectangle_max_abs_m_n": [1, 1],
        "active_count": 36,
        "expected_selected_signed_keys_sha256": _canonical_sha(selected_key_rows),
        "expected_selected_parent_indices_sha256": _canonical_sha(list(indices)),
        "active_sha256": "a1" * 32,
        "operator_scope": "test_Y3_K1",
    }
    monkeypatch.setattr(
        dtn,
        "build_ordered_mode_manifest",
        lambda modes, cfg: (
            tuple(
                {
                    "mode_index": i,
                    "side": mode.side,
                    "m": mode.m,
                    "n": mode.n,
                    "polarization": mode.polarization,
                }
                for i, mode in enumerate(modes)
            ),
            b"test",
            route["active_sha256"],
        ),
        raising=False,
    )
    bad_route = dict(route, expected_selected_signed_keys_sha256="0" * 64)
    with pytest.raises(ValueError, match="signed keys"):
        _build_task40_rectangle_inventory(
            (parent_modes, parent_rows, parent_sha), object(), bad_route
        )
    bad_parent = (parent_modes, parent_rows, "0" * 64)
    with pytest.raises(ValueError, match="exact frozen R13 parent"):
        _build_task40_rectangle_inventory(bad_parent, object(), route)


def test_physical_parent_selection_supports_rectangle_without_changing_n0():
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _expected_operator_parent_indices,
    )

    rows = tuple(
        {
            "mode_index": index,
            "side": side,
            "m": m,
            "n": n,
            "polarization": polarization,
        }
        for index, (side, m, n, polarization) in enumerate(
            (side, m, n, polarization)
            for side in ("top", "bottom")
            for m in range(-4, 5)
            for n in range(-8, 9)
            for polarization in ("s", "p")
        )
    )
    n0 = _expected_operator_parent_indices(
        rows,
        {"policy": "n_equals_zero_both_ports_both_polarizations"},
    )
    k1 = _expected_operator_parent_indices(
        rows,
        {
            "policy": "explicit_symmetric_subrectangle_from_parent_v1",
            "active_rectangle_max_abs_m_n": [1, 1],
        },
    )
    assert len(n0) == 36
    assert len(k1) == 36
    assert all(rows[i]["n"] == 0 for i in n0)
    assert all(abs(rows[i]["m"]) <= 1 and abs(rows[i]["n"]) <= 1 for i in k1)
    with pytest.raises(ValueError, match="malformed"):
        _expected_operator_parent_indices(
            rows,
            {
                "policy": "explicit_symmetric_subrectangle_from_parent_v1",
                "active_rectangle_max_abs_m_n": [1, 2],
            },
        )


@pytest.mark.parametrize("k,expected_count", sorted(K_COUNTS.items()))
def test_task40_k_dat_resolves_to_y3_geometry_and_parent_quadrature(k, expected_count):
    from src.geometry.mesh_builder_3d import stage4_axis_plan
    from src.io.input_validation import (
        load_and_resolve,
        simulation_config_3d_from_normalized,
    )
    from src.io.native_capacity_profile import native_profile_facts
    from src.runners.p6_condensed_direct import (
        _bind_task40_selected_parent_index_identity,
        _build_task40_rectangle_inventory,
        _direct_run_contract,
    )
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

    input_path = (
        ROOT
        / "input/task40para_phi90_mesh_modes_direct"
        / f"d15_y3_k{k}_r13_p6_direct.dat"
    )
    reference_path = (
        ROOT / "input/task40para_phi90_mesh_modes_direct/d15_y3_r13_p6_direct.dat"
    )
    specification = load_and_resolve(input_path)
    reference = load_and_resolve(reference_path)
    resolved = specification.as_jsonable()
    config = simulation_config_3d_from_normalized(resolved)
    profile_id = resolved["derived"]["native_capacity_profile"]["identity"]
    facts = native_profile_facts(profile_id)
    route = _direct_run_contract(profile_id)

    assert specification.physical_model_sha256 == reference.physical_model_sha256
    assert profile_id == f"task40para_phi90_13p5_D15_Y3_K{k}_p6_direct_v1"
    assert route["parent_count"] == 612
    assert route["active_count"] == expected_count
    assert route["parent_rectangle_max_abs_m_n"] == [4, 8]
    assert route["active_rectangle_max_abs_m_n"] == [k, k]
    assert facts["component_options"]["surface_quadrature"]["degree"] == 28
    assert facts["component_options"]["volume_quadrature"]["degree"] == 15
    assert facts["component_options"]["dtn_sparse_cutoff_relative_tolerance"] == 1.0e-13
    assert resolved["output"]["diffraction_order_max_m"] == 4
    assert resolved["output"]["diffraction_order_max_n"] == 8

    planned = stage4_axis_plan(config, comm_size=1)
    assert tuple(planned.mesh_cells_resolved) == (6, 10, 6)
    assert tuple(planned.x_values) == tuple(
        resolved["discretization"]["mesh_axis_x_values"]
    )
    assert tuple(planned.y_values) == tuple(
        resolved["discretization"]["mesh_axis_y_values"]
    )
    assert tuple(planned.z_values) == tuple(
        resolved["discretization"]["mesh_axis_z_values"]
    )

    config.stage4_dtn_order_policy = "explicit_rectangle"
    config.task40_dtn_rectangle_max_m = 4
    config.task40_dtn_rectangle_max_n = 8
    live_parent = build_dynamic_mode_inventory(config)
    active, selection, selected_indices = _build_task40_rectangle_inventory(
        live_parent, config, route
    )
    assert live_parent[2] == route["expected_mode_sha256"]
    assert len(live_parent[0]) == 612
    assert len(active[0]) == expected_count
    assert active[2] == route["active_sha256"]
    assert len(selected_indices) == expected_count
    assert (
        selection["selected_parent_indices_sha256"]
        == route["expected_selected_parent_indices_sha256"]
    )
    _bind_task40_selected_parent_index_identity(route, selection)
    assert (
        route["selected_parent_indices_sha256"]
        == selection["selected_parent_indices_sha256"]
    )
