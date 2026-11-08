"""Convert saved Maxwell 3D DtN/Floquet outputs to the project SAXS protocol.

The public intensity is a DWBA-compatible equivalent scattering intensity,
not an SI detector irradiance.  This module reads formal port-mode amplitudes;
sampled Fourier/diagnostic powers are never promoted to the primary signal.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


PRIMARY_FEM_ORDERS = tuple((-index, 0) for index in range(1, 6))
EXTRA_2D_FEM_ORDERS = ((0, -1), (-1, -1), (-2, -1))
DEFAULT_PHASE_REFERENCE_Z_NM = 120.0


def _complex(value: Any, *, field: str) -> complex:
    if isinstance(value, complex):
        return value
    if isinstance(value, Mapping):
        if "real" in value and "imag" in value:
            return complex(float(value["real"]), float(value["imag"]))
        if "re" in value and "im" in value:
            return complex(float(value["re"]), float(value["im"]))
    if isinstance(value, (tuple, list, np.ndarray)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    if isinstance(value, str):
        return complex(value.replace("i", "j"))
    if isinstance(value, (int, float, np.number)):
        return complex(value)
    raise ValueError(f"cannot parse complex field {field}: {value!r}")


def _complex_pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _positive_sqrt(value: complex) -> complex:
    root = complex(np.sqrt(complex(value)))
    if root.real < 0.0 or (abs(root.real) < 1.0e-14 and root.imag < 0.0):
        root = -root
    return root


def _load_run(saved_solution: Any) -> dict[str, Any]:
    """Read one completed run directory without modifying its artifacts."""
    if isinstance(saved_solution, Mapping):
        if "run_directory" in saved_solution:
            path = Path(saved_solution["run_directory"])
        elif "orders" in saved_solution:
            run = dict(saved_solution)
            _validate_run_evidence(run)
            return run
        else:
            raise ValueError("saved_solution mapping needs run_directory or orders")
    else:
        path = Path(saved_solution)
    if path.is_file():
        path = path.parent
    output = path / "numerical_output"
    if not output.is_dir() and path.name == "numerical_output":
        output = path
        path = path.parent
    orders_path = output / "dtn_port_diffraction_orders_3d.json"
    if not orders_path.is_file():
        raise FileNotFoundError(f"formal DtN modal output is missing: {orders_path}")
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("orders"), list):
        raise ValueError(f"invalid formal DtN modal output: {orders_path}")
    loaded: dict[str, Any] = {
        "orders": payload["orders"],
        "port_metrics": payload.get("metrics", {}),
        "run_directory": str(path.resolve()),
        "modal_output_path": str(orders_path.resolve()),
    }
    for filename, key in (
        ("run_manifest.json", "run_manifest"),
        ("run_summary.json", "run_summary"),
        ("resolved_config.json", "resolved_config"),
        ("p6_condensed_direct_summary.json", "solver_summary"),
    ):
        candidate = path / filename
        if candidate.is_file():
            loaded[key] = json.loads(candidate.read_text(encoding="utf-8"))
    _validate_run_evidence(loaded)
    return loaded


def _validate_run_evidence(run: Mapping[str, Any]) -> None:
    provenance = run.get("provenance", {})
    if provenance.get("kind") == "synthetic_test_fixture":
        return
    run_summary = run.get("run_summary")
    manifest = run.get("run_manifest")
    solver = run.get("solver_summary")
    if not isinstance(run_summary, Mapping) or not isinstance(manifest, Mapping):
        raise ValueError("formal SAXS output requires a saved run manifest and terminal run summary")
    if (
        run_summary.get("status") != "finished"
        or run_summary.get("exit_status") != 0
        or run_summary.get("result_classification") != "worker_exit0"
        or manifest.get("status") != "finished"
        or manifest.get("exit_status") != 0
        or manifest.get("execution_mode") != "full_solve"
    ):
        raise ValueError("formal SAXS output requires a completed full-solve run with exit status zero")
    if not isinstance(solver, Mapping):
        raise ValueError("formal SAXS output requires a P6 condensed-direct solver summary")
    if (
        solver.get("passed") is not True
        or solver.get("complete_solve") is not True
        or solver.get("errors") not in ([], None)
    ):
        raise ValueError("formal SAXS output requires a passed, complete P6 solver summary")


def _source_identity(source: Any) -> tuple[str, str] | None:
    if source is None:
        return None
    if isinstance(source, (str, Path)):
        return ("path", str(Path(source).resolve()))
    if isinstance(source, Mapping):
        if "run_directory" in source:
            return ("path", str(Path(source["run_directory"]).resolve()))
        manifest = source.get("run_manifest", {})
        if manifest.get("run_id") is not None:
            return ("run_id", str(manifest["run_id"]))
        return ("object", str(id(source)))
    return ("object", str(id(source)))


def _runs_for_channels(
    saved_solution: Any,
    channel_count: int,
    ray_count: int,
    poses: np.ndarray,
) -> list[list[dict[str, Any] | None]]:
    """Resolve an explicit channel/ray run map and reject cross-coordinate reuse."""
    explicit = isinstance(saved_solution, Mapping) and "runs_by_channel_ray" in saved_solution
    if explicit:
        source_grid = [list(row) for row in saved_solution["runs_by_channel_ray"]]
        if len(source_grid) != channel_count or any(len(row) != ray_count for row in source_grid):
            raise ValueError("runs_by_channel_ray must have shape (channels,rays)")
    else:
        if isinstance(saved_solution, Mapping) and "runs" in saved_solution:
            ray_sources = list(saved_solution["runs"])
        elif isinstance(saved_solution, Sequence) and not isinstance(
            saved_solution, (str, bytes, Path)
        ):
            ray_sources = list(saved_solution)
        else:
            ray_sources = [saved_solution]
        if len(ray_sources) != ray_count:
            raise ValueError(
                "multiple rays require one independently solved saved run per ray; "
                "the center solution is never copied"
            )
        if np.unique(poses).size > 1:
            raise ValueError(
                "multiple sample poses require explicit saved_solution.runs_by_channel_ray"
            )
        source_grid = [list(ray_sources) for _ in range(channel_count)]

    identities: dict[tuple[float, int], tuple[str, str] | None] = {}
    used_coordinates: dict[tuple[str, str], tuple[float, int]] = {}
    loaded: list[list[dict[str, Any] | None]] = []
    for channel, row in enumerate(source_grid):
        loaded_row: list[dict[str, Any] | None] = []
        for ray, source in enumerate(row):
            identity = _source_identity(source)
            coordinate = (float(poses[channel]), ray)
            previous = identities.get(coordinate)
            if coordinate in identities and previous != identity:
                raise ValueError(
                    "all order channels at the same pose/ray must use the same saved FEM run"
                )
            identities[coordinate] = identity
            if identity is not None:
                prior_coordinate = used_coordinates.get(identity)
                if prior_coordinate is not None and prior_coordinate != coordinate:
                    raise ValueError(
                        "a saved FEM run cannot be reused for another pose or incident ray"
                    )
                used_coordinates[identity] = coordinate
            loaded_row.append(None if source is None else _load_run(source))
        loaded.append(loaded_row)
    return loaded


def _run_incidence(run: Mapping[str, Any]) -> Mapping[str, Any]:
    return run.get("resolved_config", {}).get("incidence", {})


def _run_geometry(run: Mapping[str, Any]) -> Mapping[str, Any]:
    return run.get("resolved_config", {}).get("geometry", {})


def _basis(alpha: complex, gamma: complex, kz: complex, k0: float) -> tuple[np.ndarray, np.ndarray]:
    kt = float(np.sqrt(abs(alpha) ** 2 + abs(gamma) ** 2))
    if kt <= 1.0e-14 * max(k0, 1.0):
        return (
            np.asarray((1.0 + 0.0j, 0.0j, 0.0j)),
            np.asarray((0.0j, 1.0 + 0.0j, 0.0j)),
        )
    s_hat = np.asarray((-gamma / kt, alpha / kt, 0.0j), dtype=np.complex128)
    direction = np.asarray((alpha, gamma, kz), dtype=np.complex128) / k0
    p_hat = np.cross(direction, s_hat)
    p_norm = float(np.sqrt(np.sum(np.abs(p_hat) ** 2)))
    if not np.isfinite(p_norm) or p_norm <= 0.0:
        raise ValueError("cannot construct the FEM outgoing S/P polarization basis")
    return s_hat, p_hat / p_norm


def _phase_shift(amplitude: complex, kz_per_nm: complex, from_z_nm: float, to_z_nm: float) -> complex:
    # The FEM uses exp(+i k.r - i omega t); move one modal coefficient to a
    # common horizontal reference plane without independently zeroing phase.
    return amplitude * np.exp(1j * kz_per_nm * (to_z_nm - from_z_nm))


def finish_intensity(
    raw: np.ndarray,
    pose_deg: Sequence[float],
    *,
    normalization: str = "mean",
    scale: float = 1.0,
    scale_mean: float = 1.0,
    bk: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the DWBA per-pose normalization to ``(1,1,C,L)`` raw intensity."""
    raw = np.asarray(raw, dtype=np.float64)
    if raw.ndim != 4 or raw.shape[:2] != (1, 1):
        raise ValueError("raw SAXS intensity must have shape (1,1,channels,rays)")
    if not np.isfinite(raw).all() or np.any(raw < 0.0):
        raise ValueError("raw SAXS intensity must be finite and nonnegative")
    poses = np.asarray(pose_deg, dtype=np.float64).reshape(-1)
    if poses.shape != (raw.shape[2],):
        raise ValueError("one pose coordinate is required per SAXS channel")
    result = raw.copy()
    normalizers = np.ones(raw.shape[2], dtype=np.float64)
    for pose in np.unique(poses):
        indices = np.flatnonzero(poses == pose)
        channel_integrals = raw[0, 0, indices, :].sum(axis=-1)
        if normalization == "mean":
            normalizer = float(channel_integrals.mean())
        elif normalization == "sum":
            normalizer = float(channel_integrals.sum())
        elif normalization == "none":
            normalizer = 1.0
        else:
            raise ValueError("normalization must be 'mean', 'sum', or 'none'")
        if not np.isfinite(normalizer) or normalizer <= 0.0:
            raise ValueError(f"pose {pose:g} has a nonpositive SAXS normalizer")
        result[0, 0, indices, :] /= normalizer
        normalizers[indices] = normalizer
    result = result * float(scale) * float(scale_mean) + float(bk) / raw.shape[-1]
    return result, normalizers


def _detector_projection(
    result: Mapping[str, Any], detector: Mapping[str, Any]
) -> dict[str, Any]:
    distance = float(detector.get("distance_m", 0.2))
    shape = tuple(int(value) for value in detector.get("shape", (512, 512)))
    pixel = float(detector.get("pixel_size_m", 0.00012))
    first = np.asarray(
        detector.get("first_center_yz_m", (-0.03066, -0.00194)), dtype=np.float64
    )
    if len(shape) != 2 or min(shape) <= 0 or pixel <= 0.0 or distance <= 0.0:
        raise ValueError("invalid SAXS detector geometry")
    if first.shape != (2,):
        raise ValueError("first_center_yz_m must contain horizontal and vertical coordinates")
    k = np.asarray(result["k_out_saxs_over_k0"], dtype=np.complex128).real
    forward = k[:, :, 0] > 0.0
    denominator = np.where(forward, k[:, :, 0], np.nan)
    yz = distance * k[:, :, 1:3] / denominator[:, :, None]
    column = np.floor((yz[:, :, 0] - first[0]) / pixel + 0.5)
    row = np.floor((yz[:, :, 1] - first[1]) / pixel + 0.5)
    inside = (
        forward
        & np.asarray(result["propagating"], dtype=bool)
        & np.asarray(result["calculated_mask"], dtype=bool)
        & (column >= 0)
        & (column < shape[1])
        & (row >= 0)
        & (row < shape[0])
    )
    pixel_rc = np.full(k.shape[:2] + (2,), -1, dtype=np.int64)
    pixel_rc[inside] = np.stack((row[inside], column[inside]), axis=-1).astype(np.int64)
    image = np.zeros(shape, dtype=np.float64)
    intensity = np.asarray(result["intensity"], dtype=np.float64)[0, 0]
    np.add.at(image, (pixel_rc[:, :, 0][inside], pixel_rc[:, :, 1][inside]), intensity[inside])
    return {
        "detector_position_yz_m": yz,
        "detector_pixel_rc": pixel_rc,
        "in_detector": inside,
        "detector_image": image,
        "detected_order_intensity": np.where(inside, intensity, 0.0).sum(axis=-1),
        "detector_distance_m": np.asarray(distance),
        "detector_pixel_size_m": np.asarray(pixel),
        "detector_first_center_yz_m": first,
        "detector_origin_saxs_xyz_m": np.asarray((distance, first[0], first[1])),
        "detector_normal_saxs": np.asarray((1.0, 0.0, 0.0)),
        "detector_basis_y_saxs": np.asarray((0.0, 1.0, 0.0)),
        "detector_basis_z_saxs": np.asarray((0.0, 0.0, 1.0)),
        "detector_signal_units": np.asarray(
            "normalized SAXS intensity accumulated at ideal points; not W/m2 or photons"
        ),
        "detector_model": np.asarray("single-plane-wave point deposition; not finite spot"),
    }


def _build_product(
    *,
    E: np.ndarray,
    Z0H: np.ndarray,
    k_model_per_nm: np.ndarray,
    formal_R_s: np.ndarray,
    formal_R_p: np.ndarray,
    calculated: np.ndarray,
    orders: np.ndarray,
    poses: np.ndarray,
    beam_distribution_deg: np.ndarray,
    beam_weights: np.ndarray,
    wavelength_nm: float,
    cell_period_nm: tuple[float, float],
    normalization: str,
    scale: float,
    scale_mean: float,
    bk: float,
    period_number: tuple[int, int],
    disorder_factor: np.ndarray | float = 1.0,
    incident_E_amplitude: np.ndarray | complex = 1.0,
    phase_reference_z_nm: float = DEFAULT_PHASE_REFERENCE_Z_NM,
    coordinate_transform_pose_deg: bool = True,
) -> dict[str, Any]:
    E = np.asarray(E, dtype=np.complex128)
    Z0H = np.asarray(Z0H, dtype=np.complex128)
    k_model = np.asarray(k_model_per_nm, dtype=np.complex128)
    channel_count, ray_count = calculated.shape
    if E.shape != (channel_count, ray_count, 3) or Z0H.shape != E.shape:
        raise ValueError("E and Z0H must have shape (channels,rays,3)")
    if k_model.shape != E.shape or orders.shape != (channel_count, 2):
        raise ValueError("wavevectors and FEM order labels do not match channels/rays")
    if beam_distribution_deg.shape != (ray_count, 2) or beam_weights.shape != (ray_count,):
        raise ValueError("beam distribution/weights do not match the illumination axis")
    if np.any(beam_weights < 0.0) or not np.isfinite(beam_weights).all():
        raise ValueError("beam weights must be finite and nonnegative")
    missing = (beam_weights[None, :] > 0.0) & ~calculated
    if np.any(missing):
        raise ValueError("Missing positive-weight incident solves; cannot publish a complete SAXS tensor")
    if not np.isfinite(E[calculated]).all() or not np.isfinite(Z0H[calculated]).all():
        raise ValueError("solved modal E/H must be finite")
    if not np.isfinite(k_model).all():
        raise ValueError("all requested outgoing wavevectors must be finite")

    k0 = 2.0 * np.pi / float(wavelength_nm)
    k_norm = k_model / k0
    k_saxs = k_norm.copy()
    for channel, pose in enumerate(poses):
        if coordinate_transform_pose_deg:
            angle = np.deg2rad(float(pose))
            model_x, model_y = k_norm[channel, :, 0].copy(), k_norm[channel, :, 1].copy()
            k_saxs[channel, :, 0] = np.sin(angle) * model_x + np.cos(angle) * model_y
            k_saxs[channel, :, 1] = np.cos(angle) * model_x - np.sin(angle) * model_y

    alpha_i = np.deg2rad(beam_distribution_deg[:, 0])[None, :]
    alpha_f = np.full((channel_count, ray_count), np.nan, dtype=np.float64)
    theta_f = np.full_like(alpha_f, np.nan)
    prop = (k_norm[:, :, 2].real > 0.0) & (np.abs(k_norm[:, :, 2].imag) < 1.0e-10)
    alpha_f[prop] = np.arcsin(np.clip(k_norm[:, :, 2].real[prop], -1.0, 1.0))
    theta_f[prop] = np.arctan2(k_saxs[:, :, 1].real[prop], k_saxs[:, :, 0].real[prop])

    incident_phi_model = np.empty((channel_count, ray_count), dtype=np.float64)
    k_in_model = np.empty((channel_count, ray_count, 3), dtype=np.float64)
    for channel, pose in enumerate(poses):
        incident_phi_model[channel] = 90.0 - float(pose) - beam_distribution_deg[:, 1]
        ai = np.deg2rad(beam_distribution_deg[:, 0])
        phi = np.deg2rad(incident_phi_model[channel])
        k_in_model[channel, :, 0] = np.cos(ai) * np.cos(phi)
        k_in_model[channel, :, 1] = np.cos(ai) * np.sin(phi)
        k_in_model[channel, :, 2] = -np.sin(ai)
    q_model = k0 * (k_norm - k_in_model)
    reciprocal_xy = np.empty((channel_count, 2), dtype=np.float64)
    reciprocal_xy[:, 0] = orders[:, 0] * (2.0 * np.pi / cell_period_nm[0])
    reciprocal_xy[:, 1] = orders[:, 1] * (2.0 * np.pi / cell_period_nm[1])
    if not np.allclose(q_model[:, :, :2].real, reciprocal_xy[:, None, :], atol=1.0e-10):
        raise ValueError("saved FEM wavevectors and order labels violate the +G convention")

    R_s = np.asarray(formal_R_s, dtype=np.float64)
    R_p = np.asarray(formal_R_p, dtype=np.float64)
    if R_s.shape != (channel_count, ray_count) or R_p.shape != R_s.shape:
        raise ValueError("formal per-polarization powers must match channel/ray coordinates")
    if np.any(R_s < -1.0e-12) or np.any(R_p < -1.0e-12):
        raise ValueError("formal reflected powers must be nonnegative")
    R_s = np.maximum(R_s, 0.0)
    R_p = np.maximum(R_p, 0.0)
    R_total = R_s + R_p
    disorder = np.broadcast_to(np.asarray(disorder_factor, dtype=np.float64), R_s.shape)
    if not np.isfinite(disorder).all() or np.any(disorder < 0.0):
        raise ValueError("disorder_factor must be finite and nonnegative")
    sq = float(np.prod(2 * np.asarray(period_number, dtype=np.int64) + 1))
    area = float(np.prod(np.asarray(cell_period_nm, dtype=np.float64)))
    conversion = (
        area**2
        * np.sin(alpha_i)
        * np.where(prop, k_norm[:, :, 2].real, 0.0)
        / k0**2
    )
    raw_values = (
        beam_weights[None, :]
        * sq**2
        * disorder
        * R_total
        * conversion
    )
    raw = raw_values.reshape(1, 1, channel_count, ray_count)
    intensity, normalizers = finish_intensity(
        raw,
        poses,
        normalization=normalization,
        scale=scale,
        scale_mean=scale_mean,
        bk=bk,
    )
    q_saxs = q_model.copy()
    for channel, pose in enumerate(poses):
        angle = np.deg2rad(float(pose))
        qx, qy = q_model[channel, :, 0].copy(), q_model[channel, :, 1].copy()
        q_saxs[channel, :, 0] = np.sin(angle) * qx + np.cos(angle) * qy
        q_saxs[channel, :, 1] = np.cos(angle) * qx - np.sin(angle) * qy

    result: dict[str, Any] = {
        "intensity": intensity,
        "active_angle": np.stack((alpha_f, theta_f), axis=0),
        "intensity_raw": raw,
        "integrated_intensity": intensity.sum(axis=-1),
        "normalizers": normalizers,
        "normalization": np.asarray(normalization),
        "scale": np.asarray(scale, dtype=np.float64),
        "scale_mean": np.asarray(scale_mean, dtype=np.float64),
        "bk": np.asarray(bk, dtype=np.float64),
        "beam_weights_applied": np.asarray(True),
        "beam_weights": beam_weights,
        "beam_distribution_deg": beam_distribution_deg,
        "incident_phi_model_deg": incident_phi_model,
        "incident_grazing_deg": beam_distribution_deg[:, 0],
        "incident_E_amplitude": np.asarray(incident_E_amplitude, dtype=np.complex128),
        "phi_deg": poses,
        "azimuth_deg": poses,
        "fem_orders": orders,
        "order_index": orders[:, ::-1].copy(),
        "calculated_mask": calculated,
        "propagating": prop,
        "physical_valid_mask": calculated & prop,
        "q_vector_model_per_nm": q_model,
        "q_vector_saxs_per_nm": q_saxs,
        "k_out_model_per_nm": k_model,
        "k_out_over_k0": k_norm,
        "k_out_saxs_over_k0": k_saxs,
        "k_in_model_over_k0": k_in_model,
        "reflection_efficiency_diagnostic": R_total.reshape(1, 1, channel_count, ray_count),
        "R_s": R_s,
        "R_p": R_p,
        "R_total": R_total,
        "R_to_raw_I_factor": (raw_values / np.where(R_total != 0.0, R_total, 1.0)),
        "cell_period_nm": np.asarray(cell_period_nm, dtype=np.float64),
        "cell_area_nm2": np.asarray(area, dtype=np.float64),
        "period_number": np.asarray(period_number, dtype=np.int64),
        "array_factor_amplitude": np.asarray(sq, dtype=np.float64),
        "disorder_factor": disorder,
        "wavelength_nm": np.asarray(wavelength_nm, dtype=np.float64),
        "k0_per_nm": np.asarray(k0, dtype=np.float64),
        "phase_reference_z_nm": np.asarray(phase_reference_z_nm, dtype=np.float64),
        "time_convention": np.asarray("exp(-i omega t); outgoing spatial factor exp(+i k.r)"),
        "phase_basis": np.asarray("FEM Floquet S/P basis; p = normalize(khat cross s)"),
        "model_to_saxs_matrix": np.asarray(
            [
                [
                    [np.sin(np.deg2rad(pose)), np.cos(np.deg2rad(pose)), 0.0],
                    [np.cos(np.deg2rad(pose)), -np.sin(np.deg2rad(pose)), 0.0],
                    [0.0, 0.0, 1.0],
                ]
                for pose in poses
            ],
            dtype=np.float64,
        ),
        "coordinate_transform_handedness": np.asarray(-1),
        "phase_xy_origin_nm": np.asarray((0.0, 0.0)),
        "intensity_units": np.asarray(
            "DWBA-compatible equivalent scattering intensity; not W/m2 or photon count"
        ),
        "power_source": np.asarray("formal DtN outgoing modal power ratios"),
    }
    # Constructed and retained to make complex outgoing fields available to
    # future coherent processing at the same reference plane.
    result["outgoing_E_model"] = E
    result["outgoing_Z0H_model"] = Z0H
    return result


def _one_ray_fields(
    run: Mapping[str, Any] | None,
    order: tuple[int, int],
    *,
    pose_deg: float,
    beam: np.ndarray,
    wavelength_nm: float,
    period_nm: tuple[float, float],
    phase_reference_z_nm: float,
    incident_E_amplitude: complex,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float, bool, dict[str, Any]]:
    k0 = 2.0 * np.pi / wavelength_nm
    alpha_i = np.deg2rad(float(beam[0]))
    phi_model = np.deg2rad(90.0 - float(pose_deg) - float(beam[1]))
    kin = np.asarray(
        (np.cos(alpha_i) * np.cos(phi_model), np.cos(alpha_i) * np.sin(phi_model), -np.sin(alpha_i)),
        dtype=np.float64,
    )
    kout_xy = np.asarray(
        (kin[0] + order[0] * wavelength_nm / period_nm[0],
         kin[1] + order[1] * wavelength_nm / period_nm[1]),
        dtype=np.float64,
    )
    kz_expected = _positive_sqrt(complex(1.0 - np.dot(kout_xy, kout_xy)))
    k_expected = k0 * np.asarray((kout_xy[0], kout_xy[1], kz_expected), dtype=np.complex128)
    if run is None:
        return (
            np.zeros(3, dtype=np.complex128),
            np.zeros(3, dtype=np.complex128),
            k_expected,
            0.0,
            0.0,
            False,
            {},
        )
    rows = [
        row for row in run["orders"]
        if row.get("side") == "top"
        and int(row.get("m", row.get("order_m", 10**9))) == order[0]
        and int(row.get("n", row.get("order_n", 10**9))) == order[1]
    ]
    by_pol: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        polarization = str(row.get("polarization", ""))
        if polarization in {"s", "p"}:
            if polarization in by_pol:
                raise ValueError(f"duplicate formal top {polarization} port mode for FEM order {order}")
            by_pol[polarization] = row
    if not by_pol:
        return (
            np.zeros(3, dtype=np.complex128),
            np.zeros(3, dtype=np.complex128),
            k_expected,
            0.0,
            0.0,
            False,
            {},
        )
    if set(by_pol) != {"s", "p"}:
        raise ValueError(f"formal top FEM order {order} must retain both S and P mode rows")
    alpha = _complex(by_pol["s"].get("alpha"), field="alpha")
    gamma = _complex(by_pol["s"].get("gamma"), field="gamma")
    kz = _complex(by_pol["s"].get("kz"), field="kz")
    k_model = np.asarray((alpha, gamma, kz), dtype=np.complex128)
    if not np.allclose(k_model, k_expected, rtol=0.0, atol=2.0e-9 * max(k0, 1.0)):
        raise ValueError(
            f"formal outgoing wavevector for FEM order {order} disagrees with incident + reciprocal G"
        )
    if not np.allclose(
        np.asarray((_complex(by_pol["p"].get("alpha"), field="p.alpha"),
                    _complex(by_pol["p"].get("gamma"), field="p.gamma"),
                    _complex(by_pol["p"].get("kz"), field="p.kz"))),
        k_model,
        rtol=0.0,
        atol=1.0e-12 * max(k0, 1.0),
    ):
        raise ValueError(f"S/P formal mode wavevectors differ for FEM order {order}")
    port_z = float(
        run.get("port_metrics", {}).get(
            "dtn_port_top_reference_z",
            run.get("resolved_config", {}).get("geometry", {}).get("z_max_nm", phase_reference_z_nm),
        )
    )
    s_hat, p_hat = _basis(alpha, gamma, kz, k0)
    basis = {"s": s_hat, "p": p_hat}
    e = np.zeros(3, dtype=np.complex128)
    h = np.zeros(3, dtype=np.complex128)
    formal_power: dict[str, float] = {}
    amplitudes: dict[str, complex] = {}
    port_amplitudes: dict[str, complex] = {}
    origin_amplitudes: dict[str, complex] = {}
    boundary_phases: dict[str, complex | None] = {}
    for polarization, row in by_pol.items():
        if "R" not in row:
            raise ValueError(
                f"formal {polarization} port mode for FEM order {order} is missing its power ratio R"
            )
        origin_amplitude = _complex(
            row.get("outgoing_amplitude"), field=f"{polarization}.outgoing_amplitude"
        )
        origin_amplitudes[polarization] = origin_amplitude
        if "outgoing_amplitude_at_boundary" in row:
            port_amplitude = _complex(
                row["outgoing_amplitude_at_boundary"],
                field=f"{polarization}.outgoing_amplitude_at_boundary",
            )
        else:
            # Older exports store the origin-based coefficient only.
            port_amplitude = _phase_shift(origin_amplitude, kz, 0.0, port_z)
        port_amplitudes[polarization] = port_amplitude
        raw_boundary_phase = row.get("boundary_phase")
        boundary_phases[polarization] = (
            None
            if raw_boundary_phase is None
            else _complex(raw_boundary_phase, field=f"{polarization}.boundary_phase")
        )
        amp = _phase_shift(port_amplitude, kz, port_z, phase_reference_z_nm)
        if incident_E_amplitude == 0.0:
            raise ValueError("incident E amplitude cannot be zero")
        amp /= incident_E_amplitude
        amplitudes[polarization] = amp
        e += amp * basis[polarization]
        formal_power[polarization] = float(row["R"])
        if not np.isfinite(formal_power[polarization]) or formal_power[polarization] < -1.0e-12:
            raise ValueError(f"formal {polarization} power ratio for FEM order {order} is invalid")
    if bool(by_pol["s"].get("propagating", False)) != bool(
        by_pol["p"].get("propagating", False)
    ):
        raise ValueError(f"formal S/P propagation flags differ for FEM order {order}")
    h = np.cross(k_model / k0, e)
    if not np.isfinite(e).all() or not np.isfinite(h).all():
        raise ValueError(f"nonfinite translated outgoing E/H for FEM order {order}")
    detail = {
        "outgoing_amplitude_s": amplitudes["s"],
        "outgoing_amplitude_p": amplitudes["p"],
        "outgoing_amplitude_origin_s": origin_amplitudes["s"],
        "outgoing_amplitude_origin_p": origin_amplitudes["p"],
        "outgoing_amplitude_at_port_s": port_amplitudes["s"],
        "outgoing_amplitude_at_port_p": port_amplitudes["p"],
        "boundary_phase_s": boundary_phases["s"],
        "boundary_phase_p": boundary_phases["p"],
        "basis_s_model": s_hat,
        "basis_p_model": p_hat,
        "phase_reference_plane_z_nm": float(phase_reference_z_nm),
        "port_reference_plane_z_nm": port_z,
        "formal_R_s": formal_power["s"],
        "formal_R_p": formal_power["p"],
        "raw_outgoing_amplitude_s": _complex(
            by_pol["s"].get("outgoing_amplitude"), field="s.outgoing_amplitude"
        ),
        "raw_outgoing_amplitude_p": _complex(
            by_pol["p"].get("outgoing_amplitude"), field="p.outgoing_amplitude"
        ),
        "propagating": bool(by_pol["s"].get("propagating", False)),
        "power_carrying": bool(by_pol["s"].get("power_carrying", False)),
    }
    return (
        e,
        h,
        k_model,
        formal_power["s"],
        formal_power["p"],
        True,
        detail,
    )


def postprocess_to_saxs(
    saved_solution: Any,
    acquisition: Mapping[str, Any],
) -> dict[str, Any]:
    """Build SAXS intensity and coordinates from saved formal FEM port modes.

    ``saved_solution`` may be one run for a single pose/ray, ``{"runs": [...]}``
    with one independent run per ray for a single pose, or
    ``{"runs_by_channel_ray": matrix}`` for explicit channel/ray assignments
    across multiple poses. Channels at one pose/ray must share a run, and a run
    cannot be reused at another pose or incident ray. ``acquisition`` uses
    degrees for incident grazing angle and beam azimuth, FEM signed ``(m,n)``
    orders, and one sample pose per channel. Missing positive-weight ray solves
    are rejected.
    """
    if not isinstance(acquisition, Mapping):
        raise TypeError("acquisition must be a mapping")
    orders = np.asarray(acquisition.get("fem_orders", PRIMARY_FEM_ORDERS), dtype=np.int64)
    if orders.ndim != 2 or orders.shape[1] != 2 or orders.shape[0] == 0:
        raise ValueError("fem_orders must have shape (channels,2)")
    poses = np.asarray(
        acquisition.get("pose_deg", acquisition.get("phi_deg", 6.0)), dtype=np.float64
    ).reshape(-1)
    if poses.size == 1:
        poses = np.full(orders.shape[0], float(poses[0]), dtype=np.float64)
    if poses.shape != (orders.shape[0],):
        raise ValueError("pose_deg must be scalar or contain one value per channel")
    pose_order_keys = {
        (float(poses[channel]), int(order[0]), int(order[1]))
        for channel, order in enumerate(orders)
    }
    if len(pose_order_keys) != orders.shape[0]:
        raise ValueError("fem_orders must not contain duplicates within the same sample pose")
    beams = np.asarray(
        acquisition.get("beam_distribution_deg", ((0.9, 0.0),)), dtype=np.float64
    )
    if beams.ndim != 2 or beams.shape[1] != 2 or not np.isfinite(beams).all():
        raise ValueError("beam_distribution_deg must have shape (rays,2): [alpha_i, beam_azimuth]")
    ray_count = int(beams.shape[0])
    weights = np.asarray(acquisition.get("beam_weights", np.ones(ray_count)), dtype=np.float64)
    if weights.shape != (ray_count,):
        raise ValueError("beam_weights must contain one value per incident direction")
    runs_by_channel_ray = _runs_for_channels(
        saved_solution, orders.shape[0], ray_count, poses
    )
    wavelength = float(acquisition.get("wavelength_nm", 0.7135227949132827))
    period = tuple(float(value) for value in acquisition.get("cell_period_nm", (50.0, 50.0)))
    if len(period) != 2 or min(period) <= 0.0:
        raise ValueError("cell_period_nm must contain two positive lengths")
    phase_z = float(acquisition.get("phase_reference_z_nm", DEFAULT_PHASE_REFERENCE_Z_NM))
    normalization = str(acquisition.get("normalization", "mean"))
    scale = float(acquisition.get("scale", 1.0))
    scale_mean = float(acquisition.get("scale_mean", 1.0))
    bk = float(acquisition.get("bk", 0.0))
    period_number = tuple(int(value) for value in acquisition.get("period_number", (0, 0)))
    if len(period_number) != 2 or any(value < 0 for value in period_number):
        raise ValueError("period_number must contain two nonnegative integers")
    dw_xy = float(acquisition.get("dw_xy_nm", 0.0))
    dw_z = float(acquisition.get("dw_z_nm", 0.0))
    if dw_xy != 0.0 or dw_z != 0.0:
        if "disorder_factor" not in acquisition:
            raise ValueError("nonzero disorder requires explicit per-channel/ray disorder_factor")
    disorder_factor = acquisition.get("disorder_factor", 1.0)
    incident_amplitudes = np.ones(
        (orders.shape[0], ray_count), dtype=np.complex128
    )
    for channel, pose in enumerate(poses):
        for ray, run in enumerate(runs_by_channel_ray[channel]):
            if run is None:
                if weights[ray] > 0.0:
                    raise ValueError(
                        "Missing positive-weight incident solve; cannot publish a complete SAXS tensor"
                    )
                continue
            incidence = _run_incidence(run)
            geometry = _run_geometry(run)
            if incidence:
                if not np.isclose(float(incidence.get("wavelength_nm", wavelength)), wavelength, rtol=0.0, atol=1e-14):
                    raise ValueError("acquisition wavelength differs from the saved FEM solution")
                if not np.isclose(float(incidence.get("grazing_angle_deg", beams[ray, 0])), beams[ray, 0], rtol=0.0, atol=1e-10):
                    raise ValueError("beam grazing angle differs from the saved FEM solution")
                incident_amplitudes[channel, ray] = _complex(
                    incidence.get("electric_amplitude", 1.0),
                    field="incident electric_amplitude",
                )
            if geometry:
                for key, expected in (("period_x_nm", period[0]), ("period_y_nm", period[1])):
                    if key in geometry and not np.isclose(float(geometry[key]), expected, rtol=0.0, atol=1e-12):
                        raise ValueError(f"cell period {key} differs from the saved FEM solution")
            source_azimuth = float(incidence.get("azimuth_deg", 90.0 - pose - beams[ray, 1])) if incidence else None
            required_phi = 90.0 - pose - beams[ray, 1]
            if source_azimuth is not None and not np.isclose(source_azimuth, required_phi, rtol=0.0, atol=1e-10):
                raise ValueError("saved FEM azimuth does not match acquisition pose and beam direction")

    C, L = orders.shape[0], ray_count
    E = np.zeros((C, L, 3), dtype=np.complex128)
    Z0H = np.zeros_like(E)
    k_model = np.zeros_like(E)
    Rs = np.zeros((C, L), dtype=np.float64)
    Rp = np.zeros_like(Rs)
    calculated = np.zeros((C, L), dtype=bool)
    details: list[list[dict[str, Any]]] = [[{} for _ in range(L)] for _ in range(C)]
    for channel, order_values in enumerate(orders):
        order = (int(order_values[0]), int(order_values[1]))
        for ray, run in enumerate(runs_by_channel_ray[channel]):
            fields = _one_ray_fields(
                run,
                order,
                pose_deg=float(poses[channel]),
                beam=beams[ray],
                wavelength_nm=wavelength,
                period_nm=period,
                phase_reference_z_nm=phase_z,
                incident_E_amplitude=incident_amplitudes[channel, ray],
            )
            E[channel, ray], Z0H[channel, ray], k_model[channel, ray] = fields[:3]
            Rs[channel, ray], Rp[channel, ray], calculated[channel, ray] = fields[3:6]
            details[channel][ray] = fields[6]
    product = _build_product(
        E=E,
        Z0H=Z0H,
        k_model_per_nm=k_model,
        formal_R_s=Rs,
        formal_R_p=Rp,
        calculated=calculated,
        orders=orders,
        poses=poses,
        beam_distribution_deg=beams,
        beam_weights=weights,
        wavelength_nm=wavelength,
        cell_period_nm=period,
        normalization=normalization,
        scale=scale,
        scale_mean=scale_mean,
        bk=bk,
        period_number=period_number,
        disorder_factor=disorder_factor,
        incident_E_amplitude=incident_amplitudes,
        phase_reference_z_nm=phase_z,
    )
    product["outgoing_amplitude_s"] = np.asarray(
        [[details[c][r].get("outgoing_amplitude_s", 0.0j) for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["outgoing_amplitude_p"] = np.asarray(
        [[details[c][r].get("outgoing_amplitude_p", 0.0j) for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["outgoing_amplitude_origin_s"] = np.asarray(
        [[details[c][r].get("outgoing_amplitude_origin_s", 0.0j) for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["outgoing_amplitude_origin_p"] = np.asarray(
        [[details[c][r].get("outgoing_amplitude_origin_p", 0.0j) for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["outgoing_amplitude_at_port_s"] = np.asarray(
        [[details[c][r].get("outgoing_amplitude_at_port_s", 0.0j) for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["outgoing_amplitude_at_port_p"] = np.asarray(
        [[details[c][r].get("outgoing_amplitude_at_port_p", 0.0j) for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["boundary_phase_s"] = np.asarray(
        [[details[c][r].get("boundary_phase_s") or 0.0j for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["boundary_phase_p"] = np.asarray(
        [[details[c][r].get("boundary_phase_p") or 0.0j for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["boundary_phase_present_s"] = np.asarray(
        [[details[c][r].get("boundary_phase_s") is not None for r in range(L)] for c in range(C)],
        dtype=bool,
    )
    product["boundary_phase_present_p"] = np.asarray(
        [[details[c][r].get("boundary_phase_p") is not None for r in range(L)] for c in range(C)],
        dtype=bool,
    )
    product["basis_s_model"] = np.asarray(
        [[details[c][r].get("basis_s_model", np.zeros(3, complex)) for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["basis_p_model"] = np.asarray(
        [[details[c][r].get("basis_p_model", np.zeros(3, complex)) for r in range(L)] for c in range(C)],
        dtype=np.complex128,
    )
    product["port_reference_plane_z_nm"] = np.asarray(
        [[details[c][r].get("port_reference_plane_z_nm", np.nan) for r in range(L)] for c in range(C)],
        dtype=np.float64,
    )
    product["formal_mode_power_sum_matches_R_total"] = np.asarray(
        np.allclose(product["R_s"] + product["R_p"], product["R_total"], rtol=0.0, atol=1e-14)
    )
    source_records: list[dict[str, Any]] = []
    source_record_indices: dict[tuple[str, str], int] = {}
    source_run_index = np.full((C, L), -1, dtype=np.int64)
    for channel in range(C):
        for ray in range(L):
            run = runs_by_channel_ray[channel][ray]
            if run is None:
                continue
            identity = _source_identity(run)
            assert identity is not None
            if identity not in source_record_indices:
                manifest = run.get("run_manifest", {})
                summary = run.get("run_summary", {})
                solver = run.get("solver_summary", {})
                official = solver.get("official_result", {})
                source_record_indices[identity] = len(source_records)
                source_records.append(
                    {
                        "run_id": manifest.get("run_id"),
                        "run_directory": run.get("run_directory"),
                        "modal_output_path": run.get("modal_output_path"),
                        "input_path": manifest.get("input_path"),
                        "input_sha256": manifest.get("input_sha256"),
                        "source_sha": manifest.get("source_sha"),
                        "native_capacity_profile": manifest.get("native_capacity_profile"),
                        "run_summary": summary,
                        "resolved_config": run.get("resolved_config", {}),
                        "solver_summary": {
                            "status": solver.get("status"),
                            "passed": solver.get("passed"),
                            "complete_solve": solver.get("complete_solve"),
                            "result_classification": solver.get("result_classification"),
                            "errors": solver.get("errors"),
                            "residuals": solver.get("residuals"),
                            "checks": solver.get("checks"),
                            "operator_scope": solver.get("operator_scope"),
                            "full_dtn_status": solver.get("full_dtn_status"),
                            "port_metrics": official.get("port_metrics", run.get("port_metrics", {})),
                            "volume_metrics": official.get("volume_metrics", {}),
                        },
                        "provenance": run.get("provenance", {"kind": "qualified_production_run"}),
                    }
                )
            source_run_index[channel, ray] = source_record_indices[identity]
    product["metadata"] = {
        "schema": "maxwell3d.saxs_result.v1",
        "source_runs": [[None if run is None else run.get("run_manifest", {}).get("run_id") for run in row] for row in runs_by_channel_ray],
        "source_input_sha256": [[None if run is None else run.get("run_manifest", {}).get("input_sha256") for run in row] for row in runs_by_channel_ray],
        "source_commit": [[None if run is None else run.get("run_manifest", {}).get("source_sha") for run in row] for row in runs_by_channel_ray],
        "source_modal_output": [[None if run is None else run.get("modal_output_path") for run in row] for row in runs_by_channel_ray],
        "result_classification": [[None if run is None else run.get("run_summary", {}).get("result_classification") for run in row] for row in runs_by_channel_ray],
        "source_run_index": source_run_index,
        "source_run_records": source_records,
        "source_conditions_and_materials": "resolved_config and solver summaries are retained per independent run in source_run_records",
        "official_power_source": "formal DtN outgoing port modes",
        "phase_reference_z_nm": phase_z,
        "xy_phase_origin_nm": [0.0, 0.0],
        "outgoing_complex_amplitude_reference": "same common z plane for every order; translated using exp(+i*kz*dz)",
        "basis_definition": "FEM s=(-gamma/kt,alpha/kt,0); p=normalize(khat cross s); coefficients retain FEM signs",
        "model_to_saxs_is_reflection": True,
        "model_to_saxs_determinant": -1,
        "H_vector_transformed_as_pseudovector": False,
        "array_factor": "Sq=product(2*N_i+1); scalar unit-cell factor for specified periodic extent",
        "disorder_parameters_nm": {"dw_xy": dw_xy, "dw_z": dw_z},
        "detector_product_is_finite_footprint": False,
        "saxs_intensity_absolute_calibration": False,
        "main_normalization_scope": "requested channels only, grouped by sample pose; extras are built separately",
        "raw_intensity_equation": "w*abs(Sq)^2*D*R_total*A_cell^2*sin(alpha_i)*sin(alpha_f)/k0^2",
    }
    if "detector" in acquisition and acquisition["detector"]:
        product.update(_detector_projection(product, acquisition["detector"]))
    extra_orders = acquisition.get("extra_fem_orders", EXTRA_2D_FEM_ORDERS)
    if extra_orders:
        extra_orders_array = np.asarray(extra_orders, dtype=np.int64)
        if extra_orders_array.ndim != 2 or extra_orders_array.shape[1] != 2:
            raise ValueError("extra_fem_orders must have shape (extra_channels,2)")
        unique_poses = np.unique(poses)
        extra_acquisition = dict(acquisition)
        extra_acquisition["fem_orders"] = np.tile(extra_orders_array, (unique_poses.size, 1))
        extra_acquisition["pose_deg"] = np.repeat(unique_poses, len(extra_orders_array))
        extra_acquisition["extra_fem_orders"] = []
        extra_acquisition["normalization"] = acquisition.get("extra_normalization", "mean")
        representative_channels = [int(np.flatnonzero(poses == pose)[0]) for pose in unique_poses]
        extra_run_map = [
            runs_by_channel_ray[channel]
            for channel in representative_channels
            for _ in range(len(extra_orders_array))
        ]
        extra = postprocess_to_saxs(
            {"runs_by_channel_ray": extra_run_map}, extra_acquisition
        )
        product["extra_orders"] = extra
    return product


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        if np.iscomplexobj(value):
            return [[_complex_pair(complex(item)) for item in row] for row in value] if value.ndim == 2 else _jsonable(value.tolist())
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return _complex_pair(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_saxs_result(result: Mapping[str, Any], output_directory: str | Path) -> dict[str, str]:
    """Write compact JSON, CSV and NPZ products without touching the FEM run."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    arrays = {key: value for key, value in result.items() if isinstance(value, np.ndarray)}
    extra = result.get("extra_orders")
    if isinstance(extra, Mapping):
        arrays.update(
            {f"extra__{key}": value for key, value in extra.items() if isinstance(value, np.ndarray)}
        )
    npz_path = output / "saxs_result.npz"
    np.savez_compressed(npz_path, **arrays)
    json_path = output / "saxs_result.json"
    json_path.write_text(
        json.dumps(_jsonable(result), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    csv_path = output / "saxs_orders.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        fields = [
            "channel", "ray", "fem_m", "fem_n", "dwba_N1", "dwba_N2", "pose_deg",
            "beam_grazing_deg", "beam_azimuth_deg", "weight", "calculated", "propagating",
            "amplitude_s_re", "amplitude_s_im", "amplitude_p_re", "amplitude_p_im",
            "origin_amplitude_s_re", "origin_amplitude_s_im",
            "origin_amplitude_p_re", "origin_amplitude_p_im",
            "port_amplitude_s_re", "port_amplitude_s_im",
            "port_amplitude_p_re", "port_amplitude_p_im",
            "boundary_phase_s_re", "boundary_phase_s_im", "boundary_phase_s_present",
            "boundary_phase_p_re", "boundary_phase_p_im", "boundary_phase_p_present",
            "phase_reference_plane_z_nm", "port_reference_plane_z_nm",
            "R_s", "R_p", "R_total", "alpha_f_rad", "theta_f_saxs_rad",
            "kout_x_per_nm", "kout_y_per_nm", "kout_z_re_per_nm", "kout_z_im_per_nm",
            "q_x_per_nm", "q_y_per_nm", "q_z_re_per_nm", "q_z_im_per_nm",
            "intensity_raw", "intensity", "integrated_intensity",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        C, L = result["calculated_mask"].shape
        for channel in range(C):
            for ray in range(L):
                kout = result["k_out_model_per_nm"][channel, ray]
                q = result["q_vector_model_per_nm"][channel, ray]
                amps = [result["outgoing_amplitude_s"][channel, ray], result["outgoing_amplitude_p"][channel, ray]]
                origin_amps = [
                    result["outgoing_amplitude_origin_s"][channel, ray],
                    result["outgoing_amplitude_origin_p"][channel, ray],
                ]
                port_amps = [
                    result["outgoing_amplitude_at_port_s"][channel, ray],
                    result["outgoing_amplitude_at_port_p"][channel, ray],
                ]
                boundary_phases = [
                    result["boundary_phase_s"][channel, ray],
                    result["boundary_phase_p"][channel, ray],
                ]
                writer.writerow({
                    "channel": channel, "ray": ray,
                    "fem_m": int(result["fem_orders"][channel, 0]), "fem_n": int(result["fem_orders"][channel, 1]),
                    "dwba_N1": int(result["order_index"][channel, 0]), "dwba_N2": int(result["order_index"][channel, 1]),
                    "pose_deg": float(result["phi_deg"][channel]),
                    "beam_grazing_deg": float(result["beam_distribution_deg"][ray, 0]),
                    "beam_azimuth_deg": float(result["beam_distribution_deg"][ray, 1]),
                    "weight": float(result["beam_weights"][ray]),
                    "calculated": bool(result["calculated_mask"][channel, ray]),
                    "propagating": bool(result["propagating"][channel, ray]),
                    "amplitude_s_re": float(amps[0].real), "amplitude_s_im": float(amps[0].imag),
                    "amplitude_p_re": float(amps[1].real), "amplitude_p_im": float(amps[1].imag),
                    "origin_amplitude_s_re": float(origin_amps[0].real),
                    "origin_amplitude_s_im": float(origin_amps[0].imag),
                    "origin_amplitude_p_re": float(origin_amps[1].real),
                    "origin_amplitude_p_im": float(origin_amps[1].imag),
                    "port_amplitude_s_re": float(port_amps[0].real),
                    "port_amplitude_s_im": float(port_amps[0].imag),
                    "port_amplitude_p_re": float(port_amps[1].real),
                    "port_amplitude_p_im": float(port_amps[1].imag),
                    "boundary_phase_s_re": float(boundary_phases[0].real),
                    "boundary_phase_s_im": float(boundary_phases[0].imag),
                    "boundary_phase_s_present": bool(result["boundary_phase_present_s"][channel, ray]),
                    "boundary_phase_p_re": float(boundary_phases[1].real),
                    "boundary_phase_p_im": float(boundary_phases[1].imag),
                    "boundary_phase_p_present": bool(result["boundary_phase_present_p"][channel, ray]),
                    "phase_reference_plane_z_nm": float(result["phase_reference_z_nm"]),
                    "port_reference_plane_z_nm": float(result["port_reference_plane_z_nm"][channel, ray]),
                    "R_s": float(result["R_s"][channel, ray]), "R_p": float(result["R_p"][channel, ray]),
                    "R_total": float(result["R_total"][channel, ray]),
                    "alpha_f_rad": float(result["active_angle"][0, channel, ray]),
                    "theta_f_saxs_rad": float(result["active_angle"][1, channel, ray]),
                    "kout_x_per_nm": float(kout[0].real), "kout_y_per_nm": float(kout[1].real),
                    "kout_z_re_per_nm": float(kout[2].real), "kout_z_im_per_nm": float(kout[2].imag),
                    "q_x_per_nm": float(q[0].real), "q_y_per_nm": float(q[1].real),
                    "q_z_re_per_nm": float(q[2].real), "q_z_im_per_nm": float(q[2].imag),
                    "intensity_raw": float(result["intensity_raw"][0, 0, channel, ray]),
                    "intensity": float(result["intensity"][0, 0, channel, ray]),
                    "integrated_intensity": float(result["integrated_intensity"][0, 0, channel]),
                })
    return {"npz": str(npz_path), "json": str(json_path), "csv": str(csv_path)}


__all__ = [
    "EXTRA_2D_FEM_ORDERS",
    "PRIMARY_FEM_ORDERS",
    "finish_intensity",
    "postprocess_to_saxs",
    "write_saxs_result",
]
