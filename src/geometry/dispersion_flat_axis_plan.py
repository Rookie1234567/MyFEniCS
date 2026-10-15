"""Frozen axes for the bounded 0.7 nm flat-layer dispersion cases.

The z tuple is copied from the actual coordinates in the V7 p6 mesh-evidence
summary recorded below; it is not regenerated from a nominal target size.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Mapping
from itertools import pairwise

AXIS_PLAN_ID = "task39extra.dispersion.flat_0p7.p6.x1nm.y2.zv7.v1"
AXIS_PLAN_IDS = frozenset({AXIS_PLAN_ID})
AXIS_SOURCE_SUMMARY = "results/euv_grazing1_phi0/v7_interleave_0p7nm_aniso_p6_direct_q160_n0_full__full3d_direct__mpi1__Mna/20261014T062635.999684Z/p6_condensed_direct_summary.json"
AXIS_SOURCE_SUMMARY_SHA256 = '992a2b2c6e9306ac7a540edc707e53ad2a3d7da0a47d7f6a50c28ad0924d1671'
Z_AXIS_SHA256_LE_F64 = '1ed103579b90a9aa9eda3531bf5e3d0b67c605a3da7c1010e81b913581c4371d'
Z_AXIS_NM = (
(-10.0, -9.411764705882353, -8.823529411764707, -8.235294117647058, -7.647058823529411,
 -7.0588235294117645, -6.470588235294118, -5.88235294117647, -5.294117647058823,
 -4.705882352941177, -4.117647058823529, -3.5294117647058822, -2.9411764705882355,
 -2.352941176470588, -1.7647058823529402, -1.1764705882352935, -0.5882352941176467, 0.0,
 0.6, 1.2, 1.7999999999999998, 2.4, 3.0, 3.5999999999999996, 4.2, 4.8,
 5.3999999999999995, 6.0, 6.6, 7.199999999999999, 7.8, 8.4, 9.0, 9.6, 10.2,
 10.799999999999999, 11.4, 12.0, 12.6, 13.2, 13.799999999999999, 14.399999999999999,
 15.0, 15.6, 16.2, 16.8, 17.4, 18.0, 18.599999999999998, 19.2, 19.8, 20.4, 21.0,
 21.599999999999998, 22.2, 22.8, 23.4, 24.0, 24.599999999999998, 25.2, 25.8, 26.4, 27.0,
 27.599999999999998, 28.2, 28.799999999999997, 29.4, 30.0, 30.599999999999998, 31.2,
 31.799999999999997, 32.4, 33.0, 33.6, 34.199999999999996, 34.8, 35.4, 36.0, 36.6,
 37.199999999999996, 37.8, 38.4, 39.0, 39.6, 40.199999999999996, 40.8, 41.4, 42.0, 42.6,
 43.199999999999996, 43.8, 44.4, 45.0, 45.6, 46.199999999999996, 46.8, 47.4, 48.0, 48.6,
 49.199999999999996, 49.8, 50.4, 51.0, 51.6, 52.199999999999996, 52.8, 53.4, 54.0, 54.6,
 55.199999999999996, 55.8, 56.4, 57.0, 57.599999999999994, 58.199999999999996, 58.8,
 59.4, 60.0, 60.599999999999994, 61.199999999999996, 61.8, 62.4, 63.0,
 63.599999999999994, 64.2, 64.8, 65.39999999999999, 66.0, 66.6, 67.2, 67.8,
 68.39999999999999, 69.0, 69.6, 70.2, 70.8, 71.39999999999999, 72.0, 72.6, 73.2, 73.8,
 74.39999999999999, 75.0, 75.6, 76.2, 76.8, 77.39999999999999, 78.0, 78.6, 79.2, 79.8,
 80.39999999999999, 81.0, 81.6, 82.2, 82.8, 83.39999999999999, 84.0, 84.6, 85.2, 85.8,
 86.39999999999999, 87.0, 87.6, 88.2, 88.8, 89.39999999999999, 90.0, 90.6, 91.2, 91.8,
 92.39999999999999, 93.0, 93.6, 94.2, 94.8, 95.39999999999999, 96.0, 96.6, 97.2, 97.8,
 98.39999999999999, 99.0, 99.6, 100.2, 100.8, 101.39999999999999, 102.0, 102.6, 103.2,
 103.8, 104.39999999999999, 105.0, 105.6, 106.2, 106.8, 107.39999999999999, 108.0,
 108.6, 109.2, 109.8, 110.39999999999999, 111.0, 111.6, 112.2, 112.8,
 113.39999999999999, 114.0, 114.6, 115.19999999999999, 115.8, 116.39999999999999, 117.0,
 117.6, 118.19999999999999, 118.8, 119.39999999999999, 120.0, 120.58823529411765,
 121.17647058823529, 121.76470588235294, 122.3529411764706, 122.94117647058823,
 123.52941176470588, 124.11764705882354, 124.70588235294117, 125.29411764705883,
 125.88235294117646, 126.47058823529412, 127.05882352941177, 127.6470588235294,
 128.23529411764707, 128.8235294117647, 129.41176470588235, 130.0)
)


def axis_sha256_le_f64(values: tuple[float, ...]) -> str:
    return hashlib.sha256(b"".join(struct.pack("<d", float(v)) for v in values)).hexdigest()


def flat_axis_plan(nx: int) -> dict:
    nx = int(nx)
    if nx not in (2, 4, 8):
        raise ValueError("flat dispersion nx must be one of 2, 4, or 8")
    x = tuple(float(i) / nx for i in range(nx + 1))
    y = (0.0, 12.5, 25.0)
    if len(Z_AXIS_NM) != 235 or axis_sha256_le_f64(Z_AXIS_NM) != Z_AXIS_SHA256_LE_F64:
        raise RuntimeError("frozen V7 z-axis data failed its embedded identity")
    payload = {
        "plan_id": AXIS_PLAN_ID,
        "nx": nx,
        "axis_cell_counts": [nx, 2, 234],
        "x_nm": x,
        "y_nm": y,
        "z_nm": Z_AXIS_NM,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    payload["plan_sha256"] = hashlib.sha256(encoded).hexdigest()
    payload["axis_sha256_le_f64"] = {
        "x": axis_sha256_le_f64(x),
        "y": axis_sha256_le_f64(y),
        "z": Z_AXIS_SHA256_LE_F64,
    }
    return payload


def flat_axis_plan_sha256(nx: int) -> str:
    return str(flat_axis_plan(nx)["plan_sha256"])


def validate_frozen_dispersion_flat_axes(
    discretization: Mapping[str, object],
) -> dict[str, tuple[float, ...]]:
    """Validate one exact x/y/z tensor mesh from the bounded flat study."""

    plan_id = discretization.get("mesh_plan_id")
    if plan_id not in AXIS_PLAN_IDS:
        raise ValueError("input does not select the frozen dispersion flat axis plan")
    counts = tuple(int(value) for value in discretization.get("mesh_axis_cell_counts") or ())
    if len(counts) != 3 or counts[1:] != (2, 234) or counts[0] not in (2, 4, 8):
        raise ValueError("dispersion flat axis cell counts must be (2|4|8, 2, 234)")
    plan = flat_axis_plan(counts[0])
    if discretization.get("mesh_plan_sha256") != plan["plan_sha256"]:
        raise ValueError("dispersion flat mesh-plan SHA differs")
    expected = {"x": plan["x_nm"], "y": plan["y_nm"], "z": plan["z_nm"]}
    resolved: dict[str, tuple[float, ...]] = {}
    for axis in ("x", "y", "z"):
        raw = discretization.get(f"mesh_axis_{axis}_values")
        if not isinstance(raw, (list, tuple)) or len(raw) != len(expected[axis]):
            raise ValueError(f"dispersion flat mesh_axis_{axis}_values has wrong length")
        values = tuple(float(value) for value in raw)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"dispersion flat mesh_axis_{axis}_values are non-finite")
        if values != expected[axis]:
            raise ValueError(f"dispersion flat mesh_axis_{axis}_values differ from plan")
        if any(right <= left for left, right in pairwise(values)):
            raise ValueError(f"dispersion flat mesh_axis_{axis}_values are not increasing")
        resolved[axis] = values
    return resolved


def is_dispersion_flat_p6_plan(cfg: object) -> bool:
    return (
        getattr(cfg, "mesh_plan_id", None) == AXIS_PLAN_ID
        and int(getattr(cfg, "nedelec_degree", -1)) == 6
        and getattr(cfg, "stage_case", None) == "stage4_flat_layer_sanity"
        and getattr(cfg, "geometry_kind", None) == "rectangular_block_grating"
    )
