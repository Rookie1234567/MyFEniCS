from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.run_task035_actual_r5 import (
    _fixed_trace_resource_preflight,
    _parse_args,
    _qualify_fixed_trace,
    _worker,
)
from src.geometry.research_axis_profiles import (
    TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
    TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM,
    TASK035B_R5_SLAB_BISECT_PROFILE,
)


_SHA = "a" * 64
_H13_IDENTITY = {
    "partition_independent_mesh_sha256": (
        "6d4bf800caedc07020e8d93e8fdb49cac4abd0e71a2cc29d1aea88f3a2927b08"
    ),
    "cell_tag_sha256": (
        "46d288e1fae15f801988516b1579ecc14285f1472a9220f451cfa89efb6ef71e"
    ),
    "facet_tag_sha256": (
        "442cd53e48103cfe55224a270b04c92cc61032ac128a5490d5349936d7d850d5"
    ),
}


def _fixed_trace_arguments(
    *,
    profile: str,
    h_nm: str,
    directional_axis: str = "z",
    parent: bool = False,
) -> list[str]:
    values = [
        "--coarse-degree",
        "5",
        "--enriched-degree",
        "6",
        "--h-nm",
        h_nm,
        "--mesh-cell-type",
        "hexahedron",
        "--mpi-size",
        "8",
        "--fixed-trace-control-record",
        "control.json",
        "--fixed-trace-control-sha256",
        _SHA,
        "--fixed-trace-significant-channel-reference-record",
        "significant.json",
        "--fixed-trace-significant-channel-reference-sha256",
        _SHA,
        "--fixed-trace-degree",
        "5",
        "--fixed-interior-degree",
        "6",
        "--fixed-trace-directional-recovery",
        "--fixed-trace-directional-axis",
        directional_axis,
        "--fixed-trace-explicit-z-profile",
        profile,
    ]
    if parent:
        values.extend(
            [
                "--fixed-trace-directional-parent-record",
                "h14.json",
                "--fixed-trace-directional-parent-sha256",
                _SHA,
            ]
        )
    return values


def _h13_args():
    return _parse_args(
        _fixed_trace_arguments(
            profile=TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
            h_nm="13",
            parent=True,
        )
    )


def test_h13_top_phase_parse_and_preflight_are_frozen() -> None:
    args = _h13_args()
    assert args.fixed_trace_explicit_z_profile == (
        TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
    )
    assert args.fixed_trace_directional_parent_record == Path("h14.json")
    preflight = _fixed_trace_resource_preflight(args)
    assert preflight["pass"] is True
    assert preflight["directional_axis"] == "z"
    assert preflight["directional_mesh_change_semantics"] == (
        "fixed_dof_h13_top2_phase_redistribution_not_refinement"
    )
    assert preflight["explicit_z_profile_contract"] == {
        "profile": TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
        "nominal_h_nm": 13.0,
        "directional_parent_required": True,
        "directional_parent_bound": True,
        "target_identity_flag": "h13_top_phase_redistribution",
        "directional_mesh_change_semantics": (
            "fixed_dof_h13_top2_phase_redistribution_not_refinement"
        ),
    }
    axis = preflight["axis_plan"]
    assert axis["mesh_cells_resolved"] == [6, 2, 12]
    assert axis["h13_changed_z_indices"] == [9, 10]
    assert axis["axis_sha256"]["z"] == (
        "6f8892c60ecae93aa2b34dc4208de296c83a3cd39410e3e4e94872fc225b79b8"
    )
    assert all(
        axis["expected_mesh_identity"][key] == value
        for key, value in _H13_IDENTITY.items()
    )
    resources = preflight["predicted_resources"]
    assert resources["num_mesh_cells"] == 144
    assert resources["candidate_dofs"] == 89_740
    assert resources["expected_active_rows"] == 20_120


def test_r5_explicit_profile_behavior_is_preserved() -> None:
    args = _parse_args(
        _fixed_trace_arguments(
            profile=TASK035B_R5_SLAB_BISECT_PROFILE,
            h_nm="14",
        )
    )
    preflight = _fixed_trace_resource_preflight(args)
    assert preflight["pass"] is True
    assert preflight["explicit_z_profile_contract"][
        "directional_parent_required"
    ] is False
    assert preflight["explicit_z_profile_contract"][
        "directional_parent_bound"
    ] is False
    assert preflight["directional_mesh_change_semantics"] == (
        "exact_h14_r5_slab_bisect_not_nested_refinement"
    )
    assert preflight["axis_plan"]["axis_sha256"]["z"] == (
        "9048a25cdb01a0ef2aa123bc5f7ec66116a2320ed42376e63ec22679e5f3c6d8"
    )


@pytest.mark.parametrize(
    "values",
    (
        _fixed_trace_arguments(
            profile=TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
            h_nm="14",
            parent=True,
        ),
        _fixed_trace_arguments(
            profile=TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
            h_nm="13",
            directional_axis="x",
            parent=True,
        ),
        _fixed_trace_arguments(
            profile=TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
            h_nm="13",
            parent=False,
        ),
        _fixed_trace_arguments(
            profile=TASK035B_R5_SLAB_BISECT_PROFILE,
            h_nm="14",
            parent=True,
        ),
        _fixed_trace_arguments(
            profile="arbitrary_user_coordinates",
            h_nm="13",
            parent=True,
        ),
    ),
)
def test_explicit_profile_wrong_context_fails_closed(
    values: list[str],
) -> None:
    with pytest.raises(SystemExit):
        _parse_args(values)


def test_h13_profile_is_propagated_to_worker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.adaptivity import target_fixed_trace_candidate as candidate

    captured = {}

    def fake_run(out_dir, **kwargs):
        captured["out_dir"] = out_dir
        captured.update(kwargs)
        return {"status": "contract_only_no_pde"}

    monkeypatch.setattr(
        candidate,
        "run_target_fixed_trace_candidate",
        fake_run,
    )
    args = _parse_args(
        [
            *_fixed_trace_arguments(
                profile=(
                    TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
                ),
                h_nm="13",
                parent=True,
            ),
            "--worker",
            "--run-dir",
            str(tmp_path),
        ]
    )
    assert _worker(args) == 0
    assert captured["out_dir"] == tmp_path
    assert captured["explicit_z_profile"] == (
        TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
    )
    assert captured["directional_recovery"] is True
    assert captured["directional_axis"] == "z"
    assert captured["mesh_axis_cell_counts"] is None
    assert captured["directional_parent_record"] == Path("h14.json")
    assert captured["directional_parent_sha256"] == _SHA
    written = json.loads(
        (tmp_path / "actual_r5_result.json").read_text(encoding="utf-8")
    )
    assert written["status"] == "contract_only_no_pde"


def test_h13_profile_qualifier_contract_is_mutation_closed() -> None:
    args = _h13_args()
    args.fixed_trace_resource_preflight = (
        _fixed_trace_resource_preflight(args)
    )
    z_values = list(
        TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM
    )
    result = {
        "candidate": {
            "h_nm": 13.0,
            "summary": {
                "config": {
                    "mesh_axis_cell_counts_requested": [6, 2, 12],
                    "mesh_axis_z_values_requested": z_values,
                    "mesh_axis_z_profile_requested": (
                        TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
                    ),
                },
                "mesh_spacing_mode_resolved": (
                    "boundary_fitted_exact_counts_explicit_z"
                ),
                "mesh_cell_type_actual": "hexahedron",
                "num_mesh_cells": 144,
                "mesh_cells_resolved": [6, 2, 12],
            },
            "high_order_resource_audit": {
                "mesh_identity": dict(_H13_IDENTITY),
            },
        },
        "target_identity": {
            "geometry": "Task034 fixed rectangular block grating",
            "trace_degree": 5,
            "interior_degree": 6,
            "directional_axis": "z",
            "directional_mesh_change_semantics": (
                "fixed_dof_h13_top2_phase_redistribution_not_refinement"
            ),
            "mesh_axis_cell_counts_requested": [6, 2, 12],
            "mesh_axis_z_values_requested": z_values,
            "explicit_z_profile": (
                TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
            ),
            "r5_slab_bisect": False,
            "h13_top_phase_redistribution": True,
        },
        "directional_parent_authority": {
            "status": "qualified_positive_h14_parent",
            "required": True,
            "sha256": _SHA,
        },
    }

    def qualify(payload):
        return _qualify_fixed_trace(
            payload,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler={
                "max_observed_worker_rank_count": 8,
                "max_process_tree_swap_mb": 0.0,
            },
        )["checks"]

    checks = qualify(result)
    assert checks["explicit_z_profile_contract"] is True
    assert checks[
        "explicit_mesh_and_tag_hashes_match_frozen_identity"
    ] is True
    assert checks[
        "fixed_rectangular_directional_topology_identity"
    ] is True
    assert checks["directional_parent_requirement_classified"] is True

    result["target_identity"][
        "h13_top_phase_redistribution"
    ] = False
    assert qualify(result)["explicit_z_profile_contract"] is False
    result["target_identity"][
        "h13_top_phase_redistribution"
    ] = True
    result["candidate"]["high_order_resource_audit"]["mesh_identity"][
        "cell_tag_sha256"
    ] = "wrong"
    assert qualify(result)[
        "explicit_mesh_and_tag_hashes_match_frozen_identity"
    ] is False
