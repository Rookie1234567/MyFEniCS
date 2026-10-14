from __future__ import annotations

import math

import pytest

from src.geometry.task39extra_v6_f5_mesh_plan import (
    BASELINE_SOURCE_SHA,
    CONFIG_3D_GIT_BLOB_OID,
    F5_X_VALUES_NM,
    F5_Y2_PLAN_ID,
    F5_Y2_VALUES_NM,
    F5_Z_VALUES_NM,
    MESH_BUILDER_GIT_BLOB_OID,
    f5_axis_plan_sha256,
    validate_frozen_f5_axes,
)


def _payload(plan_id: str = F5_Y2_PLAN_ID) -> dict:
    return {
        "mesh_plan_id": plan_id,
        "mesh_plan_sha256": f5_axis_plan_sha256(plan_id),
        "mesh_axis_cell_counts": (
            len(F5_X_VALUES_NM) - 1,
            len(F5_Y2_VALUES_NM) - 1,
            len(F5_Z_VALUES_NM) - 1,
        ),
        "mesh_axis_x_values": F5_X_VALUES_NM,
        "mesh_axis_y_values": F5_Y2_VALUES_NM,
        "mesh_axis_z_values": F5_Z_VALUES_NM,
    }


def test_f5_two_layer_plan_keeps_baseline_xz_and_exact_y() -> None:
    axes = validate_frozen_f5_axes(_payload())
    assert axes["x"] == F5_X_VALUES_NM
    assert axes["z"] == F5_Z_VALUES_NM
    assert axes["y"] == (0.0, 12.5, 25.0)
    assert math.prod(len(axes[axis]) - 1 for axis in ("x", "y", "z")) == 1080


def test_f5_axis_plan_rejects_unsupported_y_plan_or_modified_coordinates() -> None:
    payload = _payload()
    payload["mesh_axis_y_values"] = (0.0, 25.0)
    with pytest.raises(ValueError, match="cell counts|values"):
        validate_frozen_f5_axes(payload)

    payload = _payload()
    payload["mesh_axis_x_values"] = (0.0, *F5_X_VALUES_NM[2:])
    with pytest.raises(ValueError, match="values"):
        validate_frozen_f5_axes(payload)


def test_f5_axis_plan_rejects_bad_hash_count_and_nonfinite_values() -> None:
    payload = _payload()
    payload["mesh_plan_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA"):
        validate_frozen_f5_axes(payload)

    payload = _payload()
    payload["mesh_axis_cell_counts"] = (15, 7, 36)
    with pytest.raises(ValueError, match="counts"):
        validate_frozen_f5_axes(payload)

    payload = _payload()
    payload["mesh_axis_y_values"] = (0.0, float("nan"), 25.0)
    with pytest.raises(ValueError, match="SHA|non-finite"):
        validate_frozen_f5_axes(payload)


def test_f5_axis_provenance_distinguishes_commit_from_blob_oids() -> None:
    assert len(BASELINE_SOURCE_SHA) == 40
    assert len(MESH_BUILDER_GIT_BLOB_OID) == 40
    assert len(CONFIG_3D_GIT_BLOB_OID) == 40
    assert BASELINE_SOURCE_SHA != MESH_BUILDER_GIT_BLOB_OID

