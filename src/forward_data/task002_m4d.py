"""Task002 Review-V6 M4D y-alias diagnostic configuration and analysis."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from mpi4py import MPI

from src.postprocessing.full3d_reference import _sample_distributed_function
from src.solvers.dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _combine_owned_entries,
    _dtn_surface_quadrature_degree,
    _incident_projection_onto_top_mode,
    _mode_projection_from_solution,
    _outgoing_projection,
)

from .provenance import canonical_hash
from .task002_full3d import build_task002_full3d_config
from .task002_schema import Task002ForwardParameters


M4D_SCHEMA_VERSION = "task002.m4d-y-alias-diagnostic.v1"
FAILED_POINT = Task002ForwardParameters(
    height_nm=116.446369998157,
    width_x_nm=17.513626368716,
    grazing_deg=4.538499870338,
    azimuth_deg=54.420819282532,
    model_id="S_PROD_FULL3D_STATIC_P5_H10_NY4",
)
AZIMUTH_STENCIL = (
    50.0, 51.0, 52.0, 53.0, 53.5, 54.0, 54.25, 54.5,
    54.75, 55.0, 55.5, 56.0, 57.0, 58.0,
)
Y_CELL_COUNTS = (3, 4, 5, 6)
SURFACE_QUADRATURE_DEGREES: tuple[int | None, ...] = (None, 31, 39, 47)
INDEPENDENT_PROJECTION_QUADRATURE = 63


def build_task002_m4d_config(
    parameters: Task002ForwardParameters,
    *,
    y_cells: int = 3,
    surface_quadrature_degree: int | None = None,
):
    """Build an opt-in diagnostic config without changing production defaults."""

    if int(y_cells) not in Y_CELL_COUNTS:
        raise ValueError(f"M4D y_cells must be one of {Y_CELL_COUNTS}")
    if surface_quadrature_degree is not None and int(surface_quadrature_degree) < 1:
        raise ValueError("surface quadrature degree must be positive")
    cfg = build_task002_full3d_config(
        parameters, output_profile="compact_surrogate_record",
    )
    cfg.mesh_axis_cell_counts = (6, int(y_cells), 14)
    cfg.stage4_dtn_quadrature_degree = (
        None if surface_quadrature_degree is None
        else int(surface_quadrature_degree)
    )
    cfg.case_name = (
        f"task002_m4d_ny{y_cells}_q"
        f"{surface_quadrature_degree or 'auto'}_h{parameters.height_nm:g}_"
        f"w{parameters.width_x_nm:g}_g{parameters.grazing_deg:g}_"
        f"a{parameters.azimuth_deg:g}"
    ).replace(".", "p")
    return cfg


def m4d_config_identity(
    parameters: Task002ForwardParameters,
    *,
    y_cells: int,
    surface_quadrature_degree: int | None,
) -> dict[str, Any]:
    value = {
        "schema_version": M4D_SCHEMA_VERSION,
        "parameters": parameters.as_dict(),
        "axis_cell_counts": [6, int(y_cells), 14],
        "surface_quadrature_degree_requested": surface_quadrature_degree,
        "assembly_backend": "assembly_time_static_condensed",
        "element": "uniform N1curl p5",
        "mpi_ranks": 2,
        "threads_per_rank": 1,
        "role": "diagnostic_only_not_dataset_eligible",
    }
    return {**value, "identity_sha256": canonical_hash(value)}


def alias_kinematics(parameters: Task002ForwardParameters) -> dict[str, float]:
    k0 = 2.0 * math.pi / float(parameters.wavelength_nm)
    gy = 2.0 * math.pi / 25.0
    ky = k0 * math.cos(math.radians(parameters.grazing_deg)) * math.sin(
        math.radians(parameters.azimuth_deg)
    )
    return {
        "k0_per_nm": k0,
        "Gy_per_nm": gy,
        "ky_per_nm": ky,
        "two_ky_minus_3Gy_per_nm": 2.0 * ky - 3.0 * gy,
    }


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _mode_identity(mode) -> dict[str, Any]:
    return {
        "side": mode.side,
        "m": int(mode.m),
        "n": int(mode.n),
        "polarization": str(mode.polarization).lower(),
        "alpha": _complex_pair(mode.alpha),
        "gamma": _complex_pair(mode.gamma),
        "beta": _complex_pair(mode.beta),
    }


def _mode_lookup(modes: Iterable[Any]) -> dict[tuple[str, int, int, str], Any]:
    return {
        (mode.side, int(mode.m), int(mode.n), str(mode.polarization).lower()): mode
        for mode in modes
    }


def _normalized_sparse_overlap(
    left: tuple[np.ndarray, np.ndarray],
    right: tuple[np.ndarray, np.ndarray],
    comm,
) -> dict[str, Any]:
    li, lv = left
    ri, rv = right
    right_map = {int(index): complex(value) for index, value in zip(ri, rv, strict=True)}
    cross_local = sum(
        np.conj(complex(value)) * right_map.get(int(index), 0.0j)
        for index, value in zip(li, lv, strict=True)
    )
    left_local = float(np.vdot(lv, lv).real)
    right_local = float(np.vdot(rv, rv).real)
    cross = complex(comm.allreduce(cross_local, op=MPI.SUM))
    left_norm_sq = float(comm.allreduce(left_local, op=MPI.SUM))
    right_norm_sq = float(comm.allreduce(right_local, op=MPI.SUM))
    scale = math.sqrt(max(left_norm_sq * right_norm_sq, 1.0e-300))
    normalized = cross / scale
    gram = np.asarray(
        [[1.0, normalized], [np.conj(normalized), 1.0]], dtype=np.complex128,
    )
    singular = np.linalg.svd(gram, compute_uv=False)
    return {
        "normalized_overlap": _complex_pair(normalized),
        "normalized_overlap_abs": float(abs(normalized)),
        "gram_singular_values": [float(value) for value in singular],
        "gram_condition_number": float(
            singular[0] / max(singular[-1], np.finfo(float).tiny)
        ),
        "left_norm_sq": left_norm_sq,
        "right_norm_sq": right_norm_sq,
    }


def _surface_vector_entries(mode, *, field, mesh_data, cfg, floquet_data, q: int):
    tag = cfg.tags.z_max if mode.side == "top" else cfg.tags.z_min
    assemblers = (
        _ReusableSurfaceComponentAssembler(
            field.function_space, mesh_data, tag, 0, quadrature_degree=q,
        ),
        _ReusableSurfaceComponentAssembler(
            field.function_space, mesh_data, tag, 1, quadrature_degree=q,
        ),
    )
    components = tuple(assembler.assemble_entries(mode, floquet_data.mpc) for assembler in assemblers)
    return _combine_owned_entries(components, (mode.e_vector[0], mode.e_vector[1]))


def _demodulated_y_audit(field, cfg, parameters: Task002ForwardParameters) -> dict[str, Any]:
    nx, ny = 4, 96
    xs = cfg.x_min + (np.arange(nx) + 0.5) * (cfg.x_max - cfg.x_min) / nx
    ys = cfg.y_min + (np.arange(ny) + 0.5) * (cfg.y_max - cfg.y_min) / ny
    eps = 1.0e-7 * (cfg.domain_z_max - cfg.domain_z_min)
    z_rows = {
        "top_port_inner": cfg.domain_z_max - eps,
        "bottom_port_inner": cfg.domain_z_min + eps,
        "air_volume": 0.5 * (cfg.grating_z_max + cfg.domain_z_max),
        "grating_volume": 0.5 * (cfg.interface_z + cfg.grating_z_max),
    }
    ky = alias_kinematics(parameters)["ky_per_nm"]
    rows = []
    for name, z in z_rows.items():
        points = np.asarray([[x, y, z] for x in xs for y in ys], dtype=float)
        z_sides = np.ones(len(points), dtype=np.int8)
        values = _sample_distributed_function(field, points, z_sides).reshape(nx, ny, -1)
        demodulated = values * np.exp(-1j * ky * ys)[None, :, None]
        spectrum = np.fft.fft(demodulated, axis=1) / ny
        energy = np.sum(np.abs(spectrum) ** 2, axis=(0, 2))
        total = float(np.sum(energy))
        n_minus_3_bin = (-3) % ny
        mean = np.mean(demodulated, axis=1, keepdims=True)
        variation = np.linalg.norm(demodulated - mean) / max(np.linalg.norm(demodulated), 1.0e-300)
        rows.append({
            "location": name,
            "z_nm": float(z),
            "relative_y_variation_l2": float(variation),
            "fourier_energy_fraction_n0": float(energy[0] / max(total, 1.0e-300)),
            "fourier_energy_fraction_n_minus_3": float(energy[n_minus_3_bin] / max(total, 1.0e-300)),
            "sample_count_x": nx,
            "sample_count_y": ny,
        })
    return {"demodulation": "E_total * exp(-i*ky*y)", "rows": rows}


def build_m4d_solution_diagnostics(
    *, field, mesh_data, config, floquet_data, dtn_result,
    parameters: Task002ForwardParameters,
) -> dict[str, Any]:
    """Measure independent projections and actual-trace Gram conditioning."""

    context = dtn_result["goal_context"]
    modes = context["modes"]
    aux = np.asarray(context["auxiliary_values"], dtype=np.complex128)
    incident = np.asarray(context["incident_projections"], dtype=np.complex128)
    lookup = _mode_lookup(modes)
    mode_indices = {id(mode): index for index, mode in enumerate(modes)}
    current_q = _dtn_surface_quadrature_degree(config, modes)
    selected = []
    power_carrying = []
    for side in ("top", "bottom"):
        for n in (0, -3):
            for polarization in ("s", "p"):
                mode = lookup.get((side, 0, n, polarization))
                if mode is None:
                    continue
                index = mode_indices[id(mode)]
                auxiliary_outgoing = _outgoing_projection(aux[index], incident[index], side)
                direct_total = _mode_projection_from_solution(
                    field, mode, mesh_data, config,
                    quadrature_degree=INDEPENDENT_PROJECTION_QUADRATURE,
                )
                direct_outgoing = _outgoing_projection(direct_total, incident[index], side)
                selected.append({
                    **_mode_identity(mode),
                    "auxiliary_total_projection": _complex_pair(aux[index]),
                    "auxiliary_outgoing_amplitude": _complex_pair(auxiliary_outgoing),
                    "direct_total_projection_q63": _complex_pair(direct_total),
                    "direct_outgoing_amplitude_q63": _complex_pair(direct_outgoing),
                    "auxiliary_minus_direct_outgoing_abs": float(abs(auxiliary_outgoing - direct_outgoing)),
                })
    for index, mode in enumerate(modes):
        if not bool(mode.power_per_unit_amplitude > 0.0):
            continue
        auxiliary_outgoing = _outgoing_projection(aux[index], incident[index], mode.side)
        direct_total = _mode_projection_from_solution(
            field, mode, mesh_data, config,
            quadrature_degree=INDEPENDENT_PROJECTION_QUADRATURE,
        )
        direct_outgoing = _outgoing_projection(direct_total, incident[index], mode.side)
        power_carrying.append({
            **_mode_identity(mode),
            "auxiliary_outgoing_amplitude": _complex_pair(auxiliary_outgoing),
            "direct_outgoing_amplitude_q63": _complex_pair(direct_outgoing),
            "absolute_difference": float(abs(auxiliary_outgoing - direct_outgoing)),
        })
    gram = []
    for q in sorted({int(current_q), 47, INDEPENDENT_PROJECTION_QUADRATURE}):
        for side in ("top", "bottom"):
            for polarization in ("s", "p"):
                left = lookup.get((side, 0, 0, polarization))
                right = lookup.get((side, 0, -3, polarization))
                if left is None or right is None:
                    continue
                left_entries = _surface_vector_entries(
                    left, field=field, mesh_data=mesh_data, cfg=config,
                    floquet_data=floquet_data, q=q,
                )
                right_entries = _surface_vector_entries(
                    right, field=field, mesh_data=mesh_data, cfg=config,
                    floquet_data=floquet_data, q=q,
                )
                gram.append({
                    "side": side,
                    "polarization": polarization,
                    "quadrature_degree": q,
                    **_normalized_sparse_overlap(left_entries, right_entries, mesh_data.mesh.comm),
                })
    return {
        "schema_version": M4D_SCHEMA_VERSION,
        "current_surface_quadrature_degree": int(current_q),
        "independent_projection_quadrature_degree": INDEPENDENT_PROJECTION_QUADRATURE,
        "selected_mode_projection_comparison": selected,
        "power_carrying_tangential_projection_comparison": power_carrying,
        "power_carrying_tangential_projection_gate": {
            "threshold": 1.0e-10,
            "maximum_absolute_difference": max(
                (row["absolute_difference"] for row in power_carrying), default=0.0,
            ),
            "pass": all(row["absolute_difference"] <= 1.0e-10 for row in power_carrying),
        },
        "port_vector_gram_condition": gram,
        "demodulated_field_audit": _demodulated_y_audit(field, config, parameters),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
