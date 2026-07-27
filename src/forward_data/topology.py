"""Deterministic fixed-topology audit for Task001 structured hexa plans."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from src.geometry.mesh_builder_3d import stage4_axis_plan

from .schema import Task001ForwardParameters
from .task001_config import task001_stage4_config


def _logical_topology_hash(counts: tuple[int, int, int]) -> str:
    nx, ny, nz = counts
    cells = []
    node = lambda i, j, k: i + (nx + 1) * (j + (ny + 1) * k)
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                cells.append([
                    node(i, j, k), node(i + 1, j, k), node(i, j + 1, k), node(i + 1, j + 1, k),
                    node(i, j, k + 1), node(i + 1, j, k + 1), node(i, j + 1, k + 1), node(i + 1, j + 1, k + 1),
                ])
    payload = json.dumps(cells, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def topology_audit(parameters: Task001ForwardParameters, *, comm_size: int | None = None) -> dict[str, Any]:
    cfg = task001_stage4_config(parameters)
    plan = stage4_axis_plan(cfg, parameters.mpi_ranks if comm_size is None else comm_size)
    axes = tuple(np.asarray(values, dtype=float) for values in (plan.x_values, plan.y_values, plan.z_values))
    counts = tuple(len(values) - 1 for values in axes)
    widths = [np.diff(values) for values in axes]
    min_width = min(float(np.min(values)) for values in widths)
    max_width = max(float(np.max(values)) for values in widths)
    volumes = np.multiply.outer(np.multiply.outer(widths[0], widths[1]), widths[2]).reshape(-1)
    material_counts = {"substrate": 0, "grating": 0, "air": 0}
    for x in 0.5 * (axes[0][:-1] + axes[0][1:]):
        for _y in 0.5 * (axes[1][:-1] + axes[1][1:]):
            for z in 0.5 * (axes[2][:-1] + axes[2][1:]):
                if z < cfg.interface_z:
                    material_counts["substrate"] += 1
                elif cfg.grating_x_min < x < cfg.grating_x_max and z < cfg.grating_z_max:
                    material_counts["grating"] += 1
                else:
                    material_counts["air"] += 1
    return {
        "model_id": parameters.model_id,
        "axis_cell_counts": list(counts),
        "logical_topology_sha256": _logical_topology_hash(counts),
        "material_region_cell_counts": material_counts,
        "floquet_pairing_counts": {"x": counts[1] * counts[2], "y": counts[0] * counts[2]},
        "interface_facet_count": counts[0] * counts[1],
        "element_identity": f"N1E-hexa-p{cfg.nedelec_degree}",
        "minimum_axis_jacobian": min_width,
        "minimum_cell_volume": float(np.min(volumes)),
        "maximum_aspect_ratio": max_width / min_width,
        "positive_volume": bool(np.all(volumes > 0.0)),
        "material_plane_alignment": bool(plan.material_plane_alignment["all_aligned"]),
        "coordinate_sha256": hashlib.sha256(
            b"".join(values.astype("<f8", copy=False).tobytes() for values in axes)
        ).hexdigest(),
    }
