"""Opt-in 2D TE reference artifacts for the Task39 1-degree reduction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import ufl
from petsc4py import PETSc
from dolfinx import fem

from ..common.config import SimulationConfig
from .power_metrics import _sample_scalar_on_wrapped_line, _scaled_hx_function


def _scaled_te_hz_function(E_total, cfg: SimulationConfig):
    """Build the 2D TE scaled ``H_z=-d_x(E_z)/i`` field."""

    mesh = E_total.function_space.mesh
    degree = max(int(cfg.nedelec_degree), 1)
    space = fem.functionspace(mesh, ("DG", degree))
    points = space.element.interpolation_points
    if callable(points):
        points = points()
    expression = fem.Expression(-ufl.Dx(E_total, 0) / PETSc.ScalarType(1j), points)
    hz_scaled = fem.Function(space, name="Hz_scaled")
    hz_scaled.interpolate(expression)
    hz_scaled.x.scatter_forward()
    return hz_scaled


def write_v3_2d_selected_fields(
    cfg: SimulationConfig, E_total, out_dir: Path
) -> dict[str, object]:
    """Write the fixed common x-z ``E_y/H_x/H_z`` V3 reference sample."""

    if cfg.case_name != "task039_5nm_v3_1deg_s5":
        raise ValueError("V3 2D selected-field export requires the Task39 V3 model")
    x_nm = cfg.x_min + (np.arange(40, dtype=np.float64) + 0.5) * cfg.period_x / 40.0
    z_nm = np.asarray((-5.0, 5.0, 30.0, 60.0, 90.0, 115.0, 125.0))
    hx_scaled = _scaled_hx_function(E_total, cfg)
    hz_scaled = _scaled_te_hz_function(E_total, cfg)
    electric = []
    magnetic_x = []
    magnetic_z = []
    for z_value in z_nm:
        electric.append(
            _sample_scalar_on_wrapped_line(E_total, x_nm, float(z_value), cfg)
            * cfg.electric_field_scale_V_per_m
        )
        magnetic_x.append(
            -_sample_scalar_on_wrapped_line(hx_scaled, x_nm, float(z_value), cfg)
            * cfg.magnetic_field_scale_A_per_m
            / cfg.k0
        )
        magnetic_z.append(
            -_sample_scalar_on_wrapped_line(hz_scaled, x_nm, float(z_value), cfg)
            * cfg.magnetic_field_scale_A_per_m
            / cfg.k0
        )
    arrays = {
        "x_nm": x_nm,
        "z_nm": z_nm,
        "electric_y_V_per_m": np.asarray(electric, dtype=np.complex128),
        "magnetic_x_A_per_m": np.asarray(magnetic_x, dtype=np.complex128),
        "magnetic_z_A_per_m": np.asarray(magnetic_z, dtype=np.complex128),
    }
    if not all(np.all(np.isfinite(value)) for value in arrays.values()):
        raise RuntimeError("V3 2D selected field sample contains non-finite values")
    out_dir.mkdir(parents=True, exist_ok=True)
    payload_path = out_dir / "v3_2d_selected_fields.npz"
    metadata_path = out_dir / "v3_2d_selected_fields.json"
    np.savez(payload_path, **arrays)
    payload_sha = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    descriptors = {
        name: {"shape": list(value.shape), "dtype": str(value.dtype)}
        for name, value in arrays.items()
    }
    metadata = {
        "schema": "task039.v3-2d-selected-fields.v1",
        "source": "solved_scalar_TE_field",
        "coordinate_mapping": "2d_(x,y)_to_3d_(x,z)",
        "field_components": {
            "electric_y": "E_y=E_z_2d",
            "magnetic_x": "H_x=-H2D_x_scaled*magnetic_scale/k0",
            "magnetic_z": "H_z=-H2D_y_scaled*magnetic_scale/k0",
        },
        "sampling": "40 x-midpoints on seven fixed interior z planes; Floquet phase applied",
        "units": {"x_nm": "nm", "z_nm": "nm", "electric": "V/m", "magnetic": "A/m"},
        "array_descriptors": descriptors,
        "payload_path": payload_path.name,
        "payload_sha256": payload_sha,
    }
    metadata_bytes = (
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    metadata_path.write_bytes(metadata_bytes)
    return {
        "schema": metadata["schema"],
        "payload_path": payload_path.name,
        "payload_sha256": payload_sha,
        "payload_bytes": payload_path.stat().st_size,
        "metadata_path": metadata_path.name,
        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "metadata_bytes": len(metadata_bytes),
        "array_descriptors": descriptors,
    }


__all__ = ["write_v3_2d_selected_fields"]
