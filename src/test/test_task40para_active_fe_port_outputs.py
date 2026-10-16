from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest


def _contract(*, parent_count=4, active_count=4, parent_sha=None, active_sha=None):
    parent_sha = parent_sha or "a" * 64
    active_sha = active_sha or (parent_sha if parent_count == active_count else "b" * 64)
    return {
        "schema": "task40.active_fe_port_outputs.v2",
        "operator_scope": "task40.phi90.rectangle_R_reference",
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
        "parent_inventory_scope": "task40.rectangle_R13",
        "parent_mode_count": parent_count,
        "parent_mode_sha256": parent_sha,
        "active_mode_count": active_count,
        "active_mode_sha256": active_sha,
        "selection_policy": "explicit_symmetric_rectangle_v1",
        "selected_parent_indices_sha256": None if parent_count == active_count else "c" * 64,
        "dtn_sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
        "dtn_sparse_cutoff_relative_tolerance": 1.0e-13,
        "dtn_sparse_cutoff_identity_sha256": "d" * 64,
    }


def _identity_kwargs():
    return {
        "sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
        "sparse_cutoff_relative_tolerance": 1.0e-13,
        "sparse_cutoff_identity_sha256": "d" * 64,
    }


def test_active_fe_output_identity_carries_distinct_parent_and_active_scope():
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _active_fe_port_output_identity,
    )

    identity = _active_fe_port_output_identity(
        _contract(parent_count=10, active_count=4),
        active_mode_count=4,
        active_mode_sha256="b" * 64,
        **_identity_kwargs(),
    )
    assert identity["output_scope"] == "ACTIVE_FE_DTN_PORTS"
    assert identity["parent_mode_count"] == 10
    assert identity["parent_mode_sha256"] == "a" * 64
    assert identity["active_mode_count"] == 4
    assert identity["active_mode_sha256"] == "b" * 64
    assert identity["selected_parent_indices_sha256"] == "c" * 64
    assert identity["omitted_channel_values"] == "NOT_COMPUTED"
    assert identity["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert identity["dtn_sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"


def test_active_fe_unfiltered_contract_requires_parent_active_identity_match():
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _active_fe_port_output_identity,
    )

    identity = _active_fe_port_output_identity(
        _contract(parent_count=4, active_count=4),
        active_mode_count=4,
        active_mode_sha256="a" * 64,
        **_identity_kwargs(),
    )
    assert identity["omitted_channel_values"] == "NONE_WITHIN_DECLARED_PARENT"
    bad = _contract(parent_count=4, active_count=4, active_sha="b" * 64)
    with pytest.raises(ValueError, match="unfiltered"):
        _active_fe_port_output_identity(
            bad, active_mode_count=4, active_mode_sha256="b" * 64,
            **_identity_kwargs(),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("active_count", "counts"),
        ("active_hash", "live DtN carrier"),
        ("missing_selection", "parent-index identity"),
        ("legacy_n0", "legacy N0"),
        ("false_full", "cannot certify"),
        ("cutoff_policy", "cutoff identity"),
        ("cutoff_identity", "cutoff identity"),
    ],
)
def test_active_fe_output_contract_rejects_scope_or_identity_aliases(mutation, message):
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _active_fe_port_output_identity,
    )

    contract = _contract(parent_count=8, active_count=4)
    live_sha = "b" * 64
    if mutation == "active_count":
        contract["active_mode_count"] = 5
    elif mutation == "active_hash":
        contract["active_mode_sha256"] = "d" * 64
    elif mutation == "missing_selection":
        contract["selected_parent_indices_sha256"] = None
    elif mutation == "legacy_n0":
        contract["operator_scope"] = "A6_n0"
    elif mutation == "false_full":
        contract["full_dtn_status"] = "FULL_DTN_VERIFIED"
    elif mutation == "cutoff_policy":
        contract["dtn_sparse_cutoff_policy"] = "absolute_floor_relative_v1"
    elif mutation == "cutoff_identity":
        contract["dtn_sparse_cutoff_identity_sha256"] = "e" * 64

    with pytest.raises(ValueError, match=message):
        _active_fe_port_output_identity(
            contract, active_mode_count=4, active_mode_sha256=live_sha,
            **_identity_kwargs(),
        )


def test_task40_active_fe_outputs_use_port_files_and_never_sampled_dft(monkeypatch, tmp_path):
    from src.common import modes_3d
    from src.postprocessing import diffraction_3d, postprocess_3d, rta_3d
    from src.runners.p6_condensed_direct import _direct_output_policy
    from src.solvers import dtn_port_3d
    from src.solvers import fullspace_same_mesh_hcurl_pmg_physical as physical

    active_sha = "b" * 64
    route = {
        "family": "task40_phi90",
        "operator_scope": "task40.phi90.box2",
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
        "parent_inventory_scope": "task40.phi90.R13_parent",
        "parent_count": 10,
        "parent_sha256": "a" * 64,
        "active_count": 4,
        "active_sha256": active_sha,
        "selection_policy": "explicit_box2_rectangle_v1",
        "selected_parent_indices_sha256": "c" * 64,
        "sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
        "sparse_cutoff_relative_tolerance": 1.0e-13,
        "sparse_cutoff_identity_sha256": "d" * 64,
    }
    policy = _direct_output_policy(route)
    assert policy["active_port_outputs_only"] is False
    assert policy["diffraction_source"] == "active_finite_element_dtn_port_outputs"

    field = SimpleNamespace(x=SimpleNamespace(array=np.ones(3, complex)))
    monkeypatch.setattr(physical, "restore_p0_full_field", lambda *a, **k: field)
    monkeypatch.setattr(
        dtn_port_3d,
        "_port_power_metrics",
        lambda *a: {"R_total": 0.2, "T_total": 0.7},
    )
    monkeypatch.setattr(modes_3d, "incident_power_3d", lambda cfg: 1.0)
    monkeypatch.setattr(
        postprocess_3d, "save_airbox_3d_fields", lambda *a: {"saved": True}
    )
    monkeypatch.setattr(
        rta_3d, "compute_volume_absorption_3d", lambda *a, **k: {"A_volume_total": 0.1}
    )
    monkeypatch.setattr(
        diffraction_3d,
        "compute_diffraction_orders_3d",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("sampled DFT is not the formal FE port output")
        ),
    )
    written = []
    monkeypatch.setattr(dtn_port_3d, "_write_port_outputs", lambda *a: written.append(a))

    bundle = {
        "setup": {
            "floquets": {6: object()},
            "mesh_data": SimpleNamespace(mesh=SimpleNamespace(comm=object())),
        },
        "cfg": object(),
        "modes": [SimpleNamespace(m=i, n=0) for i in range(4)],
        "incident_projections": [0j] * 4,
        "mode_sha256": active_sha,
        "dtn_sparse_cutoff_policy": route["sparse_cutoff_policy"],
        "dtn_sparse_cutoff_relative_tolerance": route[
            "sparse_cutoff_relative_tolerance"
        ],
        "dtn_sparse_cutoff_identity_sha256": route[
            "sparse_cutoff_identity_sha256"
        ],
        "dtn_action": SimpleNamespace(recover_auxiliary=lambda u: np.zeros(4, complex)),
    }
    output = physical.recover_p0_outputs(
        bundle,
        object(),
        tmp_path,
        export_all_port_modes=True,
        active_fe_port_output_contract=policy["active_fe_port_output_contract"],
    )
    assert len(written) == 1 and len(written[0][2]) == 4
    assert output["diffraction_metrics"]["status"] == "ACTIVE_FE_PORT_OUTPUT"
    assert output["diffraction_metrics"]["sampling_dft_used"] is False
    assert output["port_metrics"]["operator_scope"] == route["operator_scope"]
    assert output["port_metrics"]["parent_mode_count"] == 10
    assert output["port_metrics"]["active_mode_count"] == 4
    assert output["port_metrics"]["omitted_channel_values"] == "NOT_COMPUTED"
    json.dumps(output["diffraction_metrics"])
