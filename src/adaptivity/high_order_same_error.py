"""Strict cross-mesh same-error audit for Task035b high-order candidates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIELD_SHARD_COUNT = 8
_SIGNIFICANT_POWER_FLOOR = 1.0e-8
_POWER_TOLERANCE_FLOOR = 1.0e-12
_AMPLITUDE_TOLERANCE_FLOOR = 1.0e-10
_FIELD_RELATIVE_L2_FLOOR = 1.0e-12
_FIELD_MAXIMUM_FLOOR = 1.0e-10
_INTERFACE_OFFSET_NM = 1.0e-4


@dataclass(frozen=True)
class ProbeSet:
    """Candidate-independent physical points and quadrature weights."""

    name: str
    points: Any
    weights: Any
    region_labels: tuple[str, ...]
    definition: dict[str, Any]
    sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe_sha256(points: Any, weights: Any) -> str:
    import numpy as np

    canonical = np.ascontiguousarray(
        np.column_stack((points, weights)),
        dtype="<f8",
    )
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _tensor_box(
    lower: Sequence[float],
    upper: Sequence[float],
    orders: Sequence[int],
) -> tuple[Any, Any]:
    import numpy as np
    from numpy.polynomial.legendre import leggauss

    coordinates = []
    weights = []
    for low, high, order in zip(lower, upper, orders, strict=True):
        nodes, node_weights = leggauss(int(order))
        coordinates.append(
            0.5 * (float(low) + float(high))
            + 0.5 * (float(high) - float(low)) * nodes
        )
        weights.append(0.5 * (float(high) - float(low)) * node_weights)
    points = np.stack(
        np.meshgrid(*coordinates, indexing="ij"),
        axis=-1,
    ).reshape(-1, 3)
    tensor_weights = np.prod(
        np.stack(np.meshgrid(*weights, indexing="ij"), axis=-1),
        axis=-1,
    ).reshape(-1)
    return points, tensor_weights


def _tensor_plane(
    *,
    fixed_axis: int,
    fixed_value: float,
    first_interval: tuple[float, float],
    second_interval: tuple[float, float],
    tangential_orders: tuple[int, int],
) -> tuple[Any, Any]:
    import numpy as np
    from numpy.polynomial.legendre import leggauss

    free_axes = tuple(axis for axis in range(3) if axis != int(fixed_axis))
    coordinates: list[Any] = [None, None, None]
    weights: list[Any] = [None, None, None]
    coordinates[fixed_axis] = np.asarray([float(fixed_value)])
    weights[fixed_axis] = np.asarray([1.0])
    for axis, interval, order in zip(
        free_axes,
        (first_interval, second_interval),
        tangential_orders,
        strict=True,
    ):
        nodes, node_weights = leggauss(int(order))
        low, high = (float(interval[0]), float(interval[1]))
        coordinates[axis] = 0.5 * (low + high) + 0.5 * (high - low) * nodes
        weights[axis] = 0.5 * (high - low) * node_weights
    points = np.stack(
        np.meshgrid(*coordinates, indexing="ij"),
        axis=-1,
    ).reshape(-1, 3)
    tensor_weights = np.prod(
        np.stack(np.meshgrid(*weights, indexing="ij"), axis=-1),
        axis=-1,
    ).reshape(-1)
    return points, tensor_weights


def build_task034_fixed_probe_sets() -> dict[str, ProbeSet]:
    """Build frozen even-order probes that avoid every material boundary."""

    import numpy as np

    volume_regions = (
        ("substrate", (0.0, 0.0, -10.0), (50.0, 25.0, 0.0), (4, 4, 4)),
        ("left_air", (0.0, 0.0, 0.0), (16.5, 25.0, 120.0), (4, 4, 6)),
        ("grating", (16.5, 0.0, 0.0), (33.5, 25.0, 120.0), (4, 4, 6)),
        ("right_air", (33.5, 0.0, 0.0), (50.0, 25.0, 120.0), (4, 4, 6)),
        ("top_air", (0.0, 0.0, 120.0), (50.0, 25.0, 130.0), (4, 4, 4)),
    )
    volume_points: list[Any] = []
    volume_weights: list[Any] = []
    volume_labels: list[str] = []
    for label, lower, upper, orders in volume_regions:
        points, weights = _tensor_box(lower, upper, orders)
        volume_points.append(points)
        volume_weights.append(weights)
        volume_labels.extend([label] * len(points))
    volume_point_array = np.concatenate(volume_points)
    volume_weight_array = np.concatenate(volume_weights)
    volume_definition = {
        "rule": "open Gauss-Legendre tensor products in five disjoint materials",
        "regions": [
            {
                "label": label,
                "lower_nm": list(lower),
                "upper_nm": list(upper),
                "orders": list(orders),
            }
            for label, lower, upper, orders in volume_regions
        ],
    }

    interface_points: list[Any] = []
    interface_weights: list[Any] = []
    interface_labels: list[str] = []

    def add_plane(
        label: str,
        *,
        fixed_axis: int,
        fixed_value: float,
        first_interval: tuple[float, float],
        second_interval: tuple[float, float],
        orders: tuple[int, int],
    ) -> None:
        points, weights = _tensor_plane(
            fixed_axis=fixed_axis,
            fixed_value=fixed_value,
            first_interval=first_interval,
            second_interval=second_interval,
            tangential_orders=orders,
        )
        interface_points.append(points)
        interface_weights.append(weights)
        interface_labels.extend([label] * len(points))

    sides = ((-1.0, "minus"), (1.0, "plus"))
    for interval_label, x_interval in (
        ("left_air", (0.0, 16.5)),
        ("grating", (16.5, 33.5)),
        ("right_air", (33.5, 50.0)),
    ):
        for side, side_label in sides:
            add_plane(
                f"substrate_z0_{side_label}_{interval_label}",
                fixed_axis=2,
                fixed_value=side * _INTERFACE_OFFSET_NM,
                first_interval=x_interval,
                second_interval=(0.0, 25.0),
                orders=(6, 4),
            )
    for side, side_label in sides:
        add_plane(
            f"grating_top_{side_label}",
            fixed_axis=2,
            fixed_value=120.0 + side * _INTERFACE_OFFSET_NM,
            first_interval=(16.5, 33.5),
            second_interval=(0.0, 25.0),
            orders=(6, 4),
        )
    for x_value, wall_label in ((16.5, "left"), (33.5, "right")):
        for side, side_label in sides:
            add_plane(
                f"grating_sidewall_{wall_label}_{side_label}",
                fixed_axis=0,
                fixed_value=x_value + side * _INTERFACE_OFFSET_NM,
                first_interval=(0.0, 25.0),
                second_interval=(0.0, 120.0),
                orders=(4, 8),
            )
    interface_point_array = np.concatenate(interface_points)
    interface_weight_array = np.concatenate(interface_weights)
    interface_definition = {
        "rule": (
            "open Gauss-Legendre tangential rules on both physical sides of "
            "the substrate, grating-top, and sidewall interfaces"
        ),
        "normal_offset_nm": _INTERFACE_OFFSET_NM,
        "substrate_plane_x_intervals_nm": [
            [0.0, 16.5],
            [16.5, 33.5],
            [33.5, 50.0],
        ],
        "substrate_plane_xy_orders": [6, 4],
        "grating_top_xy_orders": [6, 4],
        "sidewall_yz_orders": [4, 8],
    }
    return {
        "volume": ProbeSet(
            name="volume",
            points=volume_point_array,
            weights=volume_weight_array,
            region_labels=tuple(volume_labels),
            definition=volume_definition,
            sha256=_probe_sha256(volume_point_array, volume_weight_array),
        ),
        "interface": ProbeSet(
            name="interface",
            points=interface_point_array,
            weights=interface_weight_array,
            region_labels=tuple(interface_labels),
            definition=interface_definition,
            sha256=_probe_sha256(interface_point_array, interface_weight_array),
        ),
    }


def _field_shard_paths(run_dir: Path) -> list[Path]:
    return [
        run_dir / f"fields_3d_for_paraview_rank{rank:04d}.vtu"
        for rank in range(_FIELD_SHARD_COUNT)
    ]


def _sample_lagrange_hex_position_fallback(
    grid: Any,
    points: Any,
    unresolved: Any,
    real: Any,
    imaginary: Any,
) -> dict[str, Any]:
    """Evaluate locator misses against one explicit owned cell at a time."""

    import numpy as np
    from vtkmodules.vtkCommonCore import reference

    query_points = np.asarray(points, dtype=np.float64)
    unresolved_mask = np.asarray(unresolved, dtype=bool)
    point_count = len(query_points)
    valid = np.zeros(point_count, dtype=bool)
    values = np.zeros((point_count, 3), dtype=np.complex128)
    if not np.any(unresolved_mask):
        return {
            "valid": valid,
            "values": values,
            "ambiguous": [],
        }
    cell_bounds = np.asarray(
        [
            grid.GetCell(cell_index).GetBounds()
            for cell_index in range(grid.n_cells)
        ],
        dtype=np.float64,
    )
    scale = max(
        1.0,
        float(np.max(np.abs(query_points), initial=0.0)),
        float(np.max(np.abs(cell_bounds), initial=0.0)),
    )
    tolerance = max(1.0e-12, 64.0 * np.finfo(np.float64).eps * scale)
    real_values = np.asarray(real)
    imaginary_values = np.asarray(imaginary)
    ambiguous: list[dict[str, Any]] = []
    for point_index in np.flatnonzero(unresolved_mask):
        point = query_points[point_index]
        candidates = np.flatnonzero(
            (point[0] >= cell_bounds[:, 0] - tolerance)
            & (point[0] <= cell_bounds[:, 1] + tolerance)
            & (point[1] >= cell_bounds[:, 2] - tolerance)
            & (point[1] <= cell_bounds[:, 3] + tolerance)
            & (point[2] >= cell_bounds[:, 4] - tolerance)
            & (point[2] <= cell_bounds[:, 5] + tolerance)
        )
        matches: list[Any] = []
        for cell_index in candidates:
            cell = grid.GetCell(int(cell_index))
            if int(cell.GetCellType()) != 72:
                raise ValueError(
                    "field fallback encountered a non-Lagrange-hexa cell"
                )
            weights = [0.0] * int(cell.GetNumberOfPoints())
            status = cell.EvaluatePosition(
                point,
                [0.0, 0.0, 0.0],
                reference(0),
                [0.0, 0.0, 0.0],
                reference(0.0),
                weights,
            )
            if int(status) != 1:
                continue
            weight_array = np.asarray(weights, dtype=np.float64)
            if (
                not np.all(np.isfinite(weight_array))
                or not math.isclose(
                    float(np.sum(weight_array)),
                    1.0,
                    rel_tol=0.0,
                    abs_tol=5.0e-11,
                )
            ):
                raise ValueError(
                    "field fallback produced invalid interpolation weights"
                )
            point_ids = np.asarray(
                [
                    cell.GetPointId(local_index)
                    for local_index in range(cell.GetNumberOfPoints())
                ],
                dtype=np.int64,
            )
            matches.append(
                weight_array @ real_values[point_ids]
                + 1j * (weight_array @ imaginary_values[point_ids])
            )
        if len(matches) == 1:
            valid[point_index] = True
            values[point_index] = matches[0]
        elif len(matches) > 1:
            ambiguous.append(
                {
                    "index": int(point_index),
                    "match_count": len(matches),
                    "coordinate_nm": [
                        float(value) for value in point
                    ],
                }
            )
    return {
        "valid": valid,
        "values": values,
        "ambiguous": ambiguous,
        "bounding_box_tolerance": tolerance,
    }


def sample_owned_vtu_shards(
    shard_paths: Sequence[Path],
    probes: ProbeSet,
) -> dict[str, Any]:
    """Sample mutually owned partition shards and fail on missing/duplicate hits."""

    import numpy as np
    import pyvista as pv

    if len(shard_paths) != _FIELD_SHARD_COUNT:
        raise ValueError("Task035b field audit requires exactly eight MPI shards")
    point_count = len(probes.points)
    values = np.zeros((point_count, 3), dtype=np.complex128)
    hit_count = np.zeros(point_count, dtype=np.int32)
    authorities: list[dict[str, Any]] = []
    for rank, raw_path in enumerate(shard_paths):
        path = Path(raw_path)
        expected_suffix = f"rank{rank:04d}.vtu"
        if not path.is_file() or not path.name.endswith(expected_suffix):
            raise ValueError(f"missing or misordered field shard: {path}")
        grid = pv.read(path)
        cell_types = sorted(int(value) for value in set(grid.celltypes.tolist()))
        if cell_types != [72]:
            raise ValueError(
                f"field shard is not a Lagrange-hexa grid: {path}: {cell_types}"
            )
        sampled = pv.PolyData(probes.points).sample(
            grid,
            pass_cell_data=False,
            snap_to_closest_point=False,
        )
        valid = np.asarray(
            sampled.point_data["vtkValidPointMask"],
            dtype=bool,
        )
        real = np.asarray(sampled.point_data["E_tot_V_per_m_real"])
        imaginary = np.asarray(sampled.point_data["E_tot_V_per_m_imag"])
        if real.shape != (point_count, 3) or imaginary.shape != (point_count, 3):
            raise ValueError(f"field shard has an unexpected E-vector shape: {path}")
        fallback = _sample_lagrange_hex_position_fallback(
            grid,
            probes.points,
            ~valid,
            np.asarray(grid.point_data["E_tot_V_per_m_real"]),
            np.asarray(grid.point_data["E_tot_V_per_m_imag"]),
        )
        if fallback["ambiguous"]:
            raise ValueError(
                "field fallback found multiple owned cells: "
                + json.dumps(fallback["ambiguous"][:10], sort_keys=True)
            )
        fallback_valid = np.asarray(fallback["valid"], dtype=bool)
        shard_valid = valid | fallback_valid
        values[valid] = real[valid] + 1j * imaginary[valid]
        values[fallback_valid] = fallback["values"][fallback_valid]
        hit_count[shard_valid] += 1
        authorities.append(
            {
                "rank": rank,
                "path": str(path.resolve()),
                "sha256": _sha256(path),
                "cell_count": int(grid.n_cells),
                "point_count": int(grid.n_points),
                "cell_types": cell_types,
                "probe_hits": int(np.count_nonzero(shard_valid)),
                "standard_locator_probe_hits": int(
                    np.count_nonzero(valid)
                ),
                "explicit_cell_position_fallback_hits": int(
                    np.count_nonzero(fallback_valid)
                ),
            }
        )
    invalid = np.flatnonzero(hit_count != 1)
    if len(invalid):
        examples = [
            {
                "index": int(index),
                "hit_count": int(hit_count[index]),
                "coordinate_nm": [
                    float(value) for value in probes.points[index]
                ],
            }
            for index in invalid[:10]
        ]
        raise ValueError(
            "fixed field probes do not have unique MPI-shard ownership: "
            + json.dumps(examples, sort_keys=True)
        )
    if not np.all(np.isfinite(values.real)) or not np.all(
        np.isfinite(values.imag)
    ):
        raise ValueError("fixed field probes contain non-finite complex E values")
    return {
        "values": values,
        "authority": {
            "probe_count": point_count,
            "unique_hit_histogram": {"1": point_count},
            "all_probes_covered_exactly_once": True,
            "explicit_cell_position_fallback": (
                "only standard-locator misses; per-owned-cell bounds plus "
                "vtkLagrangeHexahedron.EvaluatePosition; unique ownership "
                "remains mandatory"
            ),
            "explicit_cell_position_fallback_hit_count": sum(
                row["explicit_cell_position_fallback_hits"]
                for row in authorities
            ),
            "shards": authorities,
        },
    }


def _weighted_field_metric(
    p5: Any,
    p6: Any,
    candidate: Any,
    weights: Any,
) -> dict[str, Any]:
    import numpy as np

    reference_energy = float(
        np.sum(weights[:, None] * np.abs(p6) ** 2)
    )
    if not math.isfinite(reference_energy) or reference_energy <= 0.0:
        raise ValueError("fixed field probes have zero or non-finite reference energy")
    p5_delta = p5 - p6
    candidate_delta = candidate - p6
    p5_relative_l2 = math.sqrt(
        float(np.sum(weights[:, None] * np.abs(p5_delta) ** 2))
        / reference_energy
    )
    candidate_relative_l2 = math.sqrt(
        float(np.sum(weights[:, None] * np.abs(candidate_delta) ** 2))
        / reference_energy
    )
    p5_maximum = float(np.max(np.linalg.norm(p5_delta, axis=1)))
    candidate_maximum = float(
        np.max(np.linalg.norm(candidate_delta, axis=1))
    )
    relative_tolerance = max(p5_relative_l2, _FIELD_RELATIVE_L2_FLOOR)
    maximum_tolerance = max(p5_maximum, _FIELD_MAXIMUM_FLOOR)
    return {
        "reference_weighted_energy": reference_energy,
        "global_p5_vs_p6_weighted_relative_l2": p5_relative_l2,
        "candidate_vs_p6_weighted_relative_l2": candidate_relative_l2,
        "same_code_p5p6_weighted_relative_l2_tolerance": relative_tolerance,
        "global_p5_vs_p6_max_pointwise_absolute_error": p5_maximum,
        "candidate_vs_p6_max_pointwise_absolute_error": candidate_maximum,
        "same_code_p5p6_max_pointwise_tolerance": maximum_tolerance,
        "weighted_relative_l2_pass": candidate_relative_l2 <= relative_tolerance,
        "maximum_pointwise_pass": candidate_maximum <= maximum_tolerance,
        "pass": (
            candidate_relative_l2 <= relative_tolerance
            and candidate_maximum <= maximum_tolerance
        ),
    }


def compare_cross_mesh_fields(
    *,
    global_p5_dir: Path,
    global_p6_dir: Path,
    candidate_p6_dir: Path,
) -> dict[str, Any]:
    """Compare p5/p6/candidate complex fields at frozen physical probes."""

    probe_sets = build_task034_fixed_probe_sets()
    sampled: dict[str, dict[str, dict[str, Any]]] = {}
    directories = {
        "global_p5_control": Path(global_p5_dir),
        "global_p6_reference": Path(global_p6_dir),
        "candidate_p6": Path(candidate_p6_dir),
    }
    for selection_name, probes in probe_sets.items():
        sampled[selection_name] = {
            label: sample_owned_vtu_shards(
                _field_shard_paths(directory),
                probes,
            )
            for label, directory in directories.items()
        }
    selections: dict[str, Any] = {}
    for name, probes in probe_sets.items():
        values = sampled[name]
        metric = _weighted_field_metric(
            values["global_p5_control"]["values"],
            values["global_p6_reference"]["values"],
            values["candidate_p6"]["values"],
            probes.weights,
        )
        selections[name] = {
            "probe_count": len(probes.points),
            "quadrature_weight_sum": float(probes.weights.sum()),
            "probe_sha256": probes.sha256,
            "definition": probes.definition,
            "region_counts": {
                label: probes.region_labels.count(label)
                for label in sorted(set(probes.region_labels))
            },
            "sampling_authorities": {
                label: result["authority"] for label, result in values.items()
            },
            **metric,
        }
    return {
        "schema_version": "task035b.cross-mesh-field-comparison.v1",
        "status": "measured_frozen_physical_gauss_probes",
        "method": (
            "weighted complex-E comparison at candidate-independent open "
            "Gauss-Legendre probes, with exactly-one-shard ownership"
        ),
        "no_native_point_intersection": True,
        "no_probe_dropping": True,
        "no_threshold_relaxation": True,
        "relative_l2_floor": _FIELD_RELATIVE_L2_FLOOR,
        "maximum_pointwise_floor": _FIELD_MAXIMUM_FLOOR,
        "selections": selections,
        "pass": all(selection["pass"] for selection in selections.values()),
    }


def _complex_pair(values: Sequence[float]) -> complex:
    return complex(float(values[0]), float(values[1]))


def _channel_key(entry: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(entry["side"]),
        int(entry["m"]),
        int(entry["n"]),
        str(entry["polarization"]),
    )


def _load_channels(path: Path) -> dict[tuple[str, int, int, str], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    orders = payload["orders"]
    channels = {_channel_key(entry): entry for entry in orders}
    if len(channels) != len(orders):
        raise ValueError(
            f"diffraction authority contains duplicate identities: {path}"
        )
    return channels


def _ordered_channel_identity_sha256(path: Path) -> tuple[int, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    identities = [
        _channel_key(entry) for entry in payload["orders"]
    ]
    digest = hashlib.sha256(
        json.dumps(
            identities,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return len(identities), digest


def _values_close(left: Any, right: Any, *, tolerance: float = 1.0e-13) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            float(left),
            float(right),
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _values_close(a, b, tolerance=tolerance)
            for a, b in zip(left, right, strict=True)
        )
    return left == right


def compare_diffraction_channels(
    *,
    global_p5_path: Path,
    global_p6_path: Path,
    candidate_p6_path: Path,
    significant_power_floor: float = _SIGNIFICANT_POWER_FLOOR,
    allow_candidate_extra_modes: bool = False,
    expected_candidate_ordered_identity_sha256: str | None = None,
) -> dict[str, Any]:
    """Apply the frozen h10 p5-to-p6 band to every significant channel."""

    paths = {
        "global_p5_control": Path(global_p5_path),
        "global_p6_reference": Path(global_p6_path),
        "candidate_p6": Path(candidate_p6_path),
    }
    channels = {label: _load_channels(path) for label, path in paths.items()}
    identities = {label: set(values) for label, values in channels.items()}
    reference_identities = identities["global_p6_reference"]
    if identities["global_p5_control"] != reference_identities:
        raise ValueError("p5 and p6 diffraction identities differ")
    candidate_extra_identities = (
        identities["candidate_p6"] - reference_identities
    )
    if allow_candidate_extra_modes:
        if not reference_identities.issubset(
            identities["candidate_p6"]
        ):
            raise ValueError(
                "candidate diffraction identities omit frozen reference "
                "modes"
            )
    elif identities["candidate_p6"] != reference_identities:
        raise ValueError(
            "p5, p6, and candidate diffraction identities differ"
        )
    analytic_fields = (
        "direction",
        "medium",
        "order_m",
        "order_n",
        "alpha",
        "gamma",
        "beta",
        "kz",
        "vertical_sign",
        "propagating",
        "power_carrying",
        "rayleigh_warning",
        "refractive_index",
        "boundary_phase",
    )
    rows: list[dict[str, Any]] = []
    analytic_identity_pass = True
    for key in sorted(reference_identities):
        p5 = channels["global_p5_control"][key]
        p6 = channels["global_p6_reference"][key]
        candidate = channels["candidate_p6"][key]
        analytic_match = all(
            _values_close(p5.get(field), p6.get(field))
            and _values_close(p6.get(field), candidate.get(field))
            for field in analytic_fields
        )
        analytic_identity_pass &= analytic_match
        p5_power = float(p5["power_ratio"])
        p6_power = float(p6["power_ratio"])
        candidate_power = float(candidate["power_ratio"])
        p5_amplitude = _complex_pair(
            p5["outgoing_amplitude_at_boundary"]
        )
        p6_amplitude = _complex_pair(
            p6["outgoing_amplitude_at_boundary"]
        )
        candidate_amplitude = _complex_pair(
            candidate["outgoing_amplitude_at_boundary"]
        )
        significant = (
            max(p5_power, p6_power, candidate_power)
            >= float(significant_power_floor)
        )
        power_tolerance = max(
            abs(p6_power - p5_power),
            _POWER_TOLERANCE_FLOOR,
        )
        amplitude_tolerance = max(
            abs(p6_amplitude - p5_amplitude),
            _AMPLITUDE_TOLERANCE_FLOOR,
        )
        power_error = abs(candidate_power - p6_power)
        amplitude_error = abs(candidate_amplitude - p6_amplitude)
        rows.append(
            {
                "side": key[0],
                "m": key[1],
                "n": key[2],
                "polarization": key[3],
                "analytic_identity_pass": analytic_match,
                "significant": significant,
                "global_p5_power_ratio": p5_power,
                "global_p6_power_ratio": p6_power,
                "candidate_power_ratio": candidate_power,
                "candidate_vs_p6_power_absolute_error": power_error,
                "same_code_p5p6_power_tolerance": power_tolerance,
                "power_pass": (not significant) or power_error <= power_tolerance,
                "global_p5_outgoing_amplitude_at_boundary": [
                    p5_amplitude.real,
                    p5_amplitude.imag,
                ],
                "global_p6_outgoing_amplitude_at_boundary": [
                    p6_amplitude.real,
                    p6_amplitude.imag,
                ],
                "candidate_outgoing_amplitude_at_boundary": [
                    candidate_amplitude.real,
                    candidate_amplitude.imag,
                ],
                "candidate_vs_p6_amplitude_absolute_error": amplitude_error,
                "same_code_p5p6_amplitude_tolerance": amplitude_tolerance,
                "complex_amplitude_pass": (
                    (not significant)
                    or amplitude_error <= amplitude_tolerance
                ),
            }
        )
    significant_rows = [row for row in rows if row["significant"]]
    power_gate = all(row["power_pass"] for row in significant_rows)
    amplitude_gate = all(
        row["complex_amplitude_pass"] for row in significant_rows
    )
    candidate_extra_rows = [
        channels["candidate_p6"][key]
        for key in sorted(candidate_extra_identities)
    ]

    def finite_value(value: Any) -> bool:
        if isinstance(value, (int, float)):
            return math.isfinite(float(value))
        if isinstance(value, list):
            return all(finite_value(item) for item in value)
        return False

    extra_analytic_fields = (
        "alpha",
        "gamma",
        "beta",
        "kz",
        "refractive_index",
        "boundary_phase",
    )
    extra_mode_audit = {
        "allowed": bool(allow_candidate_extra_modes),
        "count": len(candidate_extra_rows),
        "all_nonpropagating": all(
            row.get("propagating") is False
            for row in candidate_extra_rows
        ),
        "side_medium_identity_pass": all(
            (
                row.get("side") == "top"
                and row.get("medium") == "air"
            )
            or (
                row.get("side") == "bottom"
                and row.get("medium") == "substrate"
            )
            for row in candidate_extra_rows
        ),
        "analytic_fields_finite": all(
            all(
                finite_value(row.get(field))
                for field in extra_analytic_fields
            )
            for row in candidate_extra_rows
        ),
        "power_carrying_count_diagnostic_only": sum(
            row.get("power_carrying") is True
            for row in candidate_extra_rows
        ),
        "nonzero_power_count_diagnostic_only": sum(
            abs(float(row.get("power_ratio", 0.0)))
            > _POWER_TOLERANCE_FLOOR
            for row in candidate_extra_rows
        ),
        "identities": [
            {
                "side": key[0],
                "m": key[1],
                "n": key[2],
                "polarization": key[3],
            }
            for key in sorted(candidate_extra_identities)
        ],
    }
    extra_mode_audit["pass"] = bool(
        (
            allow_candidate_extra_modes
            and extra_mode_audit["count"] > 0
            and extra_mode_audit["all_nonpropagating"]
            and extra_mode_audit["side_medium_identity_pass"]
            and extra_mode_audit["analytic_fields_finite"]
        )
        or (
            not allow_candidate_extra_modes
            and extra_mode_audit["count"] == 0
        )
    )
    candidate_order_count, candidate_ordered_identity_sha256 = (
        _ordered_channel_identity_sha256(paths["candidate_p6"])
    )
    ordered_identity_audit = {
        "order_count": candidate_order_count,
        "unique_identity_count": len(identities["candidate_p6"]),
        "ordered_identity_sha256": (
            candidate_ordered_identity_sha256
        ),
        "expected_ordered_identity_sha256": (
            expected_candidate_ordered_identity_sha256
        ),
        "pass": (
            candidate_order_count == len(identities["candidate_p6"])
            and (
                expected_candidate_ordered_identity_sha256 is None
                or candidate_ordered_identity_sha256
                == expected_candidate_ordered_identity_sha256
            )
        ),
    }
    return {
        "schema_version": "task035b.cross-mesh-channel-comparison.v1",
        "same_code_band_definition": (
            "absolute h10 p5-to-p6 change, frozen before the h15 candidate"
        ),
        "significant_power_floor": float(significant_power_floor),
        "power_tolerance_floor": _POWER_TOLERANCE_FLOOR,
        "amplitude_tolerance_floor": _AMPLITUDE_TOLERANCE_FLOOR,
        "channel_count": len(rows),
        "significant_channel_count": len(significant_rows),
        "significant_power_pass_count": sum(
            row["power_pass"] for row in significant_rows
        ),
        "significant_complex_amplitude_pass_count": sum(
            row["complex_amplitude_pass"] for row in significant_rows
        ),
        "analytic_channel_identity_pass": analytic_identity_pass,
        "candidate_extra_mode_audit": extra_mode_audit,
        "candidate_ordered_identity_audit": ordered_identity_audit,
        "significant_order_power_gate_pass": power_gate,
        "significant_complex_amplitude_gate_pass": amplitude_gate,
        "authorities": {
            label: {
                "path": str(path.resolve()),
                "sha256": _sha256(path),
            }
            for label, path in paths.items()
        },
        "channels": rows,
        "pass": (
            analytic_identity_pass
            and power_gate
            and amplitude_gate
            and extra_mode_audit["pass"]
            and ordered_identity_audit["pass"]
        ),
    }


def compare_significant_channels_to_reference_v1(
    *,
    candidate_path: Path,
    reference_record_path: Path,
    reference_record_sha256: str,
) -> dict[str, Any]:
    """Apply the exact frozen 12-channel v0 gate carried by reference v1.

    The broader 80-channel comparison remains a useful diagnostic, but it
    cannot define the formal Review-V1 channel identity.  This function binds
    the candidate to the mechanically validated reference record and uses only
    each channel's unchanged h10 p5-to-p6 acceptance tolerance.  The wider
    numerical convergence band is never consumed as a Gate.
    """

    reference_path = Path(reference_record_path).resolve()
    candidate_path = Path(candidate_path).resolve()
    actual_sha256 = _sha256(reference_path)
    if actual_sha256 != str(reference_record_sha256).lower():
        raise ValueError("significant-channel reference v1 SHA256 mismatch")
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    convergence = reference.get("reference_convergence_summary") or {}
    selection = reference.get("significant_channel_selection") or {}
    manifest = reference.get("authority_manifest") or {}
    if (
        reference.get("schema_version")
        != "task035b.significant-channel-reference.v1"
        or reference.get("status")
        != "significant_channel_reference_v1_frozen"
        or reference.get("pass") is not True
        or reference.get("mechanical_validation_pass") is not True
        or selection.get("channel_count") != 12
        or selection.get("expected_and_observed_identity_match") is not True
        or convergence.get("all_12_channels_converged") is not True
        or manifest.get("mechanically_validated") is not True
    ):
        raise ValueError(
            "significant-channel reference v1 is not a qualified frozen "
            "12-channel authority"
        )
    reference_rows: dict[
        tuple[str, int, int, str],
        dict[str, Any],
    ] = {}
    for row in reference.get("channels") or []:
        channel = row.get("channel") or {}
        key = (
            str(channel.get("side")),
            int(channel.get("m")),
            int(channel.get("n")),
            str(channel.get("polarization")),
        )
        if key in reference_rows:
            raise ValueError(
                "significant-channel reference v1 contains a duplicate "
                f"channel {key}"
            )
        reference_rows[key] = row
    if len(reference_rows) != 12:
        raise ValueError(
            "significant-channel reference v1 does not contain exactly "
            "12 unique channels"
        )

    candidate_rows = _load_channels(candidate_path)
    analytic_fields = (
        "direction",
        "medium",
        "order_m",
        "order_n",
        "alpha",
        "gamma",
        "beta",
        "kz",
        "vertical_sign",
        "propagating",
        "power_carrying",
        "rayleigh_warning",
        "refractive_index",
        "boundary_phase",
    )
    rows: list[dict[str, Any]] = []
    for key in sorted(reference_rows):
        if key not in candidate_rows:
            raise ValueError(
                "candidate is missing frozen significant channel "
                f"{key}"
            )
        reference_row = reference_rows[key]
        candidate = candidate_rows[key]
        analytic_identity = reference_row.get("analytic_identity") or {}
        analytic_match = all(
            _values_close(
                candidate.get(field),
                analytic_identity.get(field),
            )
            for field in analytic_fields
        )
        center = reference_row.get("reference_center") or {}
        gate = reference_row.get("unchanged_v0_acceptance_gate") or {}
        if (
            gate.get("unchanged_v0_formula_verified") is not True
            or gate.get("uses_numerical_convergence_band") is not False
            or gate.get("uses_h15_or_fixed_diagnostics") is not False
        ):
            raise ValueError(
                "reference v1 channel does not preserve the unchanged v0 "
                f"Gate for {key}"
            )
        power_tolerance = float(gate["power_absolute_tolerance"])
        amplitude_tolerance = float(
            gate["complex_amplitude_absolute_tolerance"]
        )
        reference_power = float(center["power"])
        reference_amplitude = _complex_pair(
            center["complex_amplitude"]
        )
        candidate_power = float(candidate["power_ratio"])
        candidate_amplitude = _complex_pair(
            candidate["outgoing_amplitude_at_boundary"]
        )
        finite_values = (
            power_tolerance,
            amplitude_tolerance,
            reference_power,
            candidate_power,
            reference_amplitude.real,
            reference_amplitude.imag,
            candidate_amplitude.real,
            candidate_amplitude.imag,
        )
        if (
            not all(math.isfinite(value) for value in finite_values)
            or power_tolerance <= 0.0
            or amplitude_tolerance <= 0.0
            or reference_power <= 0.0
            or candidate_power < 0.0
        ):
            raise ValueError(
                "significant-channel reference/candidate values are not "
                f"finite physical Gate inputs for {key}"
            )
        power_error = abs(candidate_power - reference_power)
        amplitude_error = abs(candidate_amplitude - reference_amplitude)
        if not (
            math.isfinite(power_error)
            and math.isfinite(amplitude_error)
        ):
            raise ValueError(
                "significant-channel errors are not finite for "
                f"{key}"
            )
        rows.append(
            {
                "side": key[0],
                "m": key[1],
                "n": key[2],
                "polarization": key[3],
                "analytic_identity_pass": analytic_match,
                "reference_power_ratio": reference_power,
                "candidate_power_ratio": candidate_power,
                "candidate_vs_reference_power_absolute_error": power_error,
                "unchanged_v0_power_tolerance": power_tolerance,
                "power_pass": (
                    analytic_match and power_error <= power_tolerance
                ),
                "reference_outgoing_amplitude_at_boundary": [
                    reference_amplitude.real,
                    reference_amplitude.imag,
                ],
                "candidate_outgoing_amplitude_at_boundary": [
                    candidate_amplitude.real,
                    candidate_amplitude.imag,
                ],
                "candidate_vs_reference_amplitude_absolute_error": (
                    amplitude_error
                ),
                "unchanged_v0_complex_amplitude_tolerance": (
                    amplitude_tolerance
                ),
                "complex_amplitude_pass": (
                    analytic_match
                    and amplitude_error <= amplitude_tolerance
                ),
            }
        )
    power_count = sum(row["power_pass"] for row in rows)
    amplitude_count = sum(
        row["complex_amplitude_pass"] for row in rows
    )
    analytic_pass = all(
        row["analytic_identity_pass"] for row in rows
    )
    return {
        "schema_version": (
            "task035b.significant-channel-reference-v1-comparison.v1"
        ),
        "status": (
            "all_12_significant_channels_pass"
            if analytic_pass and power_count == 12 and amplitude_count == 12
            else "significant_channel_controlled_negative"
        ),
        "reference_authority": {
            "path": str(reference_path),
            "sha256": actual_sha256,
            "reference_payload_sha256": reference.get(
                "reference_payload_sha256"
            ),
        },
        "candidate_authority": {
            "path": str(candidate_path),
            "sha256": _sha256(candidate_path),
        },
        "frozen_significant_channel_count": 12,
        "significant_power_pass_count": power_count,
        "significant_complex_amplitude_pass_count": amplitude_count,
        "all_12_significant_powers_pass": power_count == 12,
        "all_12_significant_complex_amplitudes_pass": (
            amplitude_count == 12
        ),
        "analytic_channel_identity_pass": analytic_pass,
        "acceptance_gate": (
            "unchanged v0 h10 p5-to-p6 absolute corrections only"
        ),
        "numerical_convergence_band_used_as_gate": False,
        "thresholds_relaxed": False,
        "channels": rows,
        "pass": (
            analytic_pass and power_count == 12 and amplitude_count == 12
        ),
    }


def compare_observables(
    candidate: dict[str, Any],
    global_p5: dict[str, Any],
    global_p6: dict[str, Any],
) -> dict[str, Any]:
    """Compare strict scalar goals and the normalized R/T/A-closure vector."""

    values = {
        "R00_total": (
            float(candidate["R00_total"]),
            float(global_p5["R00_total"]),
            float(global_p6["R00_total"]),
        ),
        "R_total": (
            float(candidate["R_total"]),
            float(global_p5["R_total"]),
            float(global_p6["R_total"]),
        ),
        "T_total": (
            float(candidate["T_total"]),
            float(global_p5["T_total"]),
            float(global_p6["T_total"]),
        ),
        "A_closure": (
            1.0 - float(candidate["R_total"]) - float(candidate["T_total"]),
            1.0 - float(global_p5["R_total"]) - float(global_p5["T_total"]),
            1.0 - float(global_p6["R_total"]) - float(global_p6["T_total"]),
        ),
    }
    observables: dict[str, Any] = {}
    normalized_vector: list[float] = []
    for name, (candidate_value, p5_value, p6_value) in values.items():
        tolerance = max(abs(p6_value - p5_value), 1.0e-12)
        error = abs(candidate_value - p6_value)
        normalized_error = error / tolerance
        if name in {"R_total", "T_total", "A_closure"}:
            normalized_vector.append(normalized_error)
        observables[name] = {
            "candidate": candidate_value,
            "global_p5_control": p5_value,
            "global_p6_reference": p6_value,
            "candidate_vs_p6_absolute_error": error,
            "same_code_p5p6_tolerance": tolerance,
            "normalized_error": normalized_error,
            "pass": error <= tolerance,
        }
    normalized_l2 = math.sqrt(sum(value * value for value in normalized_vector))
    reference_radius = math.sqrt(3.0)
    scalar_pass = all(row["pass"] for row in observables.values())
    vector_pass = normalized_l2 <= reference_radius
    return {
        "schema_version": "task035b.cross-mesh-observable-comparison.v1",
        "same_code_band_definition": (
            "absolute h10 p5-to-p6 change, frozen before the h15 candidate"
        ),
        "observables": observables,
        "normalized_R_T_Aclosure_l2": normalized_l2,
        "normalized_R_T_Aclosure_reference_radius": reference_radius,
        "all_scalar_same_code_bands_pass": scalar_pass,
        "normalized_R_T_Aclosure_vector_pass": vector_pass,
        "pass": scalar_pass and vector_pass,
    }


def _run_dir(record: dict[str, Any]) -> Path:
    path = Path(record["raw_evidence"]["run_directory"])
    return path if path.is_absolute() else _REPO_ROOT / path


def _load_summary(run_dir: Path, level: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = run_dir / level / "run_summary.json"
    if not path.is_file():
        raise ValueError(f"missing raw solver summary: {path}")
    return json.loads(path.read_text(encoding="utf-8")), {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
    }


def _physical_config(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "stage_case",
        "geometry_kind",
        "lambda0",
        "n_air",
        "mu_r",
        "period_x",
        "period_y",
        "z_min",
        "z_max",
        "air_height",
        "substrate_thickness",
        "grating_height",
        "grating_width_x",
        "grating_width_y",
        "n_substrate",
        "n_grating",
        "substrate_material_label",
        "grating_material_label",
        "interface_z",
        "scattering_background",
        "stage4_boundary_model",
        "stage4_dtn_order_policy",
        "stage4_dtn_assembly",
        "use_floquet_xy",
        "use_pml",
        "incident_theta_deg",
        "incident_phi_deg",
        "polarization_kind",
        "custom_polarization",
        "incident_amplitude",
        "incident_e0_v_per_m",
        "tags",
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "physical_z_min",
        "physical_z_max",
        "domain_z_min",
        "domain_z_max",
        "propagation_direction",
        "polarization",
        "wavevector",
        "floquet_phase_x",
        "floquet_phase_y",
        "eps_air",
        "eps_substrate",
        "eps_grating",
        "grating_index",
        "grating_bounds",
        "k0",
        "omega",
    )
    config = summary["config"]
    missing = [key for key in keys if key not in config]
    if missing:
        raise ValueError(f"raw solver config is incomplete: {missing}")
    return {key: config[key] for key in keys}


def _periodic_orientation_audit(summary: dict[str, Any]) -> dict[str, Any]:
    mismatch_keys = (
        "floquet_max_face_transform_fit_residual",
        "floquet_max_edge_midpoint_pairing_error",
        "floquet_max_face_midpoint_pairing_error",
        "floquet_edge_corner_constraint_phase_mismatch",
        "floquet_x_face_mismatch",
        "floquet_y_face_mismatch",
        "floquet_edge_corner_mismatch",
    )
    mismatches = {key: float(summary[key]) for key in mismatch_keys}
    orientation = summary["nedelec_orientation_factor_stats"]
    trace_map = summary["cell_static_condensation"]["trace_constraints"]
    degree = int(summary["nedelec_degree"])
    checks = {
        "floquet_enabled": summary.get("use_floquet_xy") is True,
        "topological_trace_mode": summary.get(
            "floquet_constraint_mode_resolved"
        )
        == f"topological_trace_p{degree}",
        "positive_constraints": int(summary.get("floquet_num_constraints", 0))
        > 0,
        "edge_slave_master_counts_match": int(
            summary.get("floquet_num_slave_edges", -1)
        )
        == int(summary.get("floquet_num_matched_master_edges", -2)),
        "face_slave_master_counts_match": int(
            summary.get("floquet_num_slave_faces", -1)
        )
        == int(summary.get("floquet_num_matched_master_faces", -2)),
        "all_periodic_mismatches_zero": all(
            abs(value) <= 1.0e-12 for value in mismatches.values()
        ),
        "exact_basix_entity_transforms": orientation.get(
            "uses_exact_basix_entity_transforms"
        )
        is True,
        "no_local_moment_fit": orientation.get("uses_local_moment_fit") is False,
        "distributed_exact_mapping": orientation.get("mapping_kind")
        == f"distributed_exact_topological_trace_p{degree}",
        "orientation_factors_are_signed_permutations": set(
            float(value)
            for value in orientation.get("unique_rounded_real", [])
        ).issubset({-1.0, 0.0, 1.0}),
        "orientation_maximum_is_one": math.isclose(
            float(orientation.get("max_abs", math.inf)),
            1.0,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ),
        "no_full_boundary_gather": orientation.get(
            "used_full_boundary_gather"
        )
        is False,
        "no_dense_boundary_square": orientation.get(
            "created_dense_boundary_square"
        )
        is False,
        "exact_trace_expansion": trace_map.get("status")
        == "exact_mpc_trace_expansion_built",
        "constraint_before_matrix_insertion": trace_map.get(
            "constraint_applied_before_global_matrix_insertion"
        )
        is True,
        "no_embedded_slave_identity_rows": trace_map.get(
            "embedded_identity_slave_rows_allocated"
        )
        is False,
    }
    return {
        "degree": degree,
        "mismatches": mismatches,
        "orientation": orientation,
        "trace_constraint_map": trace_map,
        "checks": checks,
        "pass": all(checks.values()),
    }


def _full_residual_audit(summary: dict[str, Any]) -> dict[str, Any]:
    cell = summary["cell_static_condensation"]
    explicit = cell["full_explicit_true_residual"]
    operator = cell["full_operator_true_residual"]
    top = float(summary["linear_system_relative_residual"])
    explicit_value = float(explicit["linear_system_relative_residual"])
    operator_value = float(operator["linear_system_relative_residual"])
    method = str(explicit.get("full_operator_residual_method", ""))
    checks = {
        "finite": all(
            math.isfinite(value)
            for value in (top, explicit_value, operator_value)
        ),
        "le_1e-9": explicit_value <= 1.0e-9,
        "top_level_matches": math.isclose(
            top,
            explicit_value,
            rel_tol=0.0,
            abs_tol=1.0e-16,
        ),
        "operator_matches": math.isclose(
            operator_value,
            explicit_value,
            rel_tol=0.0,
            abs_tol=1.0e-16,
        ),
        "explicit_reduced_trace_dtn": "reduced trace+DtN" in method,
        "matrix_free_eliminated_interior": "matrix-free" in method,
        "no_full_global_matrix_for_residual": explicit.get(
            "full_global_matrix_allocated_for_residual"
        )
        is False,
        "no_full_trace_matrix_for_residual": explicit.get(
            "full_trace_matrix_allocated_for_residual"
        )
        is False,
    }
    return {
        "linear_system_rhs_norm": explicit.get("linear_system_rhs_norm"),
        "linear_system_solution_norm": explicit.get(
            "linear_system_solution_norm"
        ),
        "linear_system_residual_norm": explicit.get(
            "linear_system_residual_norm"
        ),
        "linear_system_relative_residual": explicit_value,
        "reduced_trace_dtn_residual_norm": explicit.get(
            "reduced_trace_dtn_residual_norm"
        ),
        "eliminated_cell_interior_residual_norm": explicit.get(
            "eliminated_cell_interior_residual_norm"
        ),
        "full_operator_residual_method": method,
        "checks": checks,
        "pass": all(checks.values()),
    }


def audit_identity_and_residuals(
    *,
    control_record: dict[str, Any],
    candidate_record: dict[str, Any],
    control_summaries: dict[str, dict[str, Any]],
    candidate_summary: dict[str, Any],
) -> dict[str, Any]:
    """Audit geometry, tags, periodicity, orientation, and explicit residuals."""

    summaries = {
        "global_p5_control": control_summaries["coarse_p5"],
        "global_p6_reference": control_summaries["enriched_p6"],
        "candidate_p6": candidate_summary,
    }
    physical_configs = {
        label: _physical_config(summary) for label, summary in summaries.items()
    }
    physical_identity = (
        physical_configs["global_p5_control"]
        == physical_configs["global_p6_reference"]
        == physical_configs["candidate_p6"]
    )
    reference_volumes = summaries["global_p6_reference"]["domain_tag_volumes"]
    volume_checks = {
        label: all(
            math.isclose(
                float(summary["domain_tag_volumes"][tag]),
                float(reference_volumes[tag]),
                rel_tol=1.0e-10,
                abs_tol=1.0e-8,
            )
            for tag in reference_volumes
        )
        for label, summary in summaries.items()
    }
    plane_checks = {
        label: (
            summary["mesh_material_plane_alignment"].get("all_aligned") is True
            and summary["mesh_material_plane_alignment"].get("checked")
            == summaries["global_p6_reference"][
                "mesh_material_plane_alignment"
            ].get("checked")
        )
        for label, summary in summaries.items()
    }
    periodic_orientation = {
        label: _periodic_orientation_audit(summary)
        for label, summary in summaries.items()
    }
    residuals = {
        label: _full_residual_audit(summary)
        for label, summary in summaries.items()
    }
    control_mesh = control_record["common_mesh_identity"]
    candidate_mesh = candidate_record["common_mesh_identity"]
    control_mesh_consistent = all(
        control_mesh
        == control_record[level]["high_order_resource_audit"]["mesh_identity"]
        for level in ("coarse", "enriched")
    )
    candidate_mesh_consistent = all(
        candidate_mesh
        == candidate_record[level]["high_order_resource_audit"]["mesh_identity"]
        for level in ("coarse", "enriched")
    )
    cross_mesh_different = all(
        control_mesh[key] != candidate_mesh[key]
        for key in (
            "partition_independent_mesh_sha256",
            "cell_tag_sha256",
            "facet_tag_sha256",
        )
    )
    record_checks = {
        "control_formal_pass": control_record.get("status")
        == "actual_global_r5_pass"
        and (control_record.get("qualification") or {}).get("pass") is True,
        "candidate_formal_pass": candidate_record.get("status")
        == "actual_global_r5_pass"
        and (candidate_record.get("qualification") or {}).get("pass") is True,
        "control_source_stable": (control_record.get("source") or {}).get(
            "stable_and_clean_after"
        )
        is True,
        "candidate_source_stable": (candidate_record.get("source") or {}).get(
            "stable_and_clean_after"
        )
        is True,
        "target_identity_equal": control_record.get("target_identity")
        == candidate_record.get("target_identity"),
        "both_same_mesh_pairs": control_record.get("same_mesh_hashes") is True
        and candidate_record.get("same_mesh_hashes") is True,
        "both_single_mesh_instances": control_record.get(
            "single_in_memory_mesh_instance"
        )
        is True
        and candidate_record.get("single_in_memory_mesh_instance") is True,
        "mpi8": all(
            int(summary.get("mpi_size", -1)) == 8
            for summary in summaries.values()
        ),
        "zero_swap": float(
            control_record["resource_authority"]["max_process_tree_swap_mb"]
        )
        == 0.0
        and float(
            candidate_record["resource_authority"]["max_process_tree_swap_mb"]
        )
        == 0.0,
        "physical_config_whitelist_equal": physical_identity,
        "domain_tag_volumes_equal": all(volume_checks.values()),
        "material_planes_equal_and_aligned": all(plane_checks.values()),
        "control_mesh_identity_consistent": control_mesh_consistent,
        "candidate_mesh_identity_consistent": candidate_mesh_consistent,
        "cross_mesh_hashes_expected_different": cross_mesh_different,
        "all_periodic_orientation_audits_pass": all(
            audit["pass"] for audit in periodic_orientation.values()
        ),
        "all_full_explicit_residuals_pass": all(
            audit["pass"] for audit in residuals.values()
        ),
    }
    return {
        "schema_version": "task035b.cross-mesh-identity-residual-audit.v1",
        "physical_config_whitelist": physical_configs,
        "domain_tag_volume_checks": volume_checks,
        "material_plane_checks": plane_checks,
        "mesh_identities": {
            "global_h10_control": control_mesh,
            "candidate_h15": candidate_mesh,
        },
        "periodic_orientation": periodic_orientation,
        "full_explicit_true_residuals": residuals,
        "checks": record_checks,
        "pass": all(record_checks.values()),
    }


def _stage_peak_gib(record: dict[str, Any], stage: str) -> float:
    matches = [
        row
        for row in record["resource_authority"]["stage_peaks"]
        if row["stage"] == stage
    ]
    if len(matches) != 1:
        raise ValueError(f"formal record has no unique {stage!r} resource peak")
    return float(matches[0]["max_mpi_process_tree_rss_mb"]) / 1024.0


def _resource_metrics(
    record: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    matrix = summary["stage4_dtn_floquet_independent_matrix_stats"]
    factor_inventory = summary["stage4_dtn_factor_inventory"]
    factor = factor_inventory["matrix_stats"]
    matrix_nnz = int(matrix["matrix_nnz_used"])
    corrected_factor_nnz = factor_inventory.get("factor_nnz_corrected")
    factor_nnz = int(
        corrected_factor_nnz
        if corrected_factor_nnz is not None
        else factor["matrix_nnz_used"]
    )
    factor_nnz_source = (
        factor_inventory.get("factor_nnz_corrected_source")
        if corrected_factor_nnz is not None
        else "petsc_factor_matrix_stats.matrix_nnz_used"
    )
    return {
        "full3d_equivalent_dofs": int(summary["num_nedelec_dofs"]),
        "active_rows": int(matrix["matrix_rows"]),
        "matrix_nnz": matrix_nnz,
        "matrix_average_row_width": float(
            matrix["matrix_average_nnz_per_row"]
        ),
        "matrix_maximum_row_width": int(matrix["matrix_maximum_nnz_per_row"]),
        "factor_nnz": factor_nnz,
        "factor_nnz_source": factor_nnz_source,
        "factor_fill": factor_nnz / matrix_nnz,
        "overall_process_tree_peak_gib": float(
            record["resource_authority"]["memory_authority_gib"]
        ),
        "p6_solve_stage_process_tree_peak_gib": _stage_peak_gib(
            record,
            "actual_r5_enriched_solve",
        ),
        "assembly_seconds": float(
            summary["stage4_dtn_base_matrix_assembly_seconds"]
        ),
        "assembly_time_total_build_seconds": float(
            summary["stage4_dtn_assembly_time_total_build_seconds"]
        ),
        "mumps_setup_seconds": float(summary["stage4_dtn_ksp_setup_seconds"]),
        "mumps_solve_seconds": float(summary["stage4_dtn_ksp_solve_seconds"]),
        "linear_solve_seconds": float(summary["stage4_dtn_linear_solve_seconds"]),
        "cell_recovery_seconds": float(
            summary["stage4_dtn_cell_static_condensation_recovery_seconds"]
        ),
        "solver_elapsed_seconds": float(summary["elapsed_seconds"]),
    }


def compare_resources(
    *,
    control_record: dict[str, Any],
    candidate_record: dict[str, Any],
    global_p6_summary: dict[str, Any],
    candidate_p6_summary: dict[str, Any],
) -> dict[str, Any]:
    reference = _resource_metrics(control_record, global_p6_summary)
    candidate = _resource_metrics(candidate_record, candidate_p6_summary)
    ratio_fields = (
        "full3d_equivalent_dofs",
        "active_rows",
        "matrix_nnz",
        "factor_nnz",
        "overall_process_tree_peak_gib",
        "p6_solve_stage_process_tree_peak_gib",
        "assembly_seconds",
        "mumps_setup_seconds",
        "solver_elapsed_seconds",
    )
    ratios = {
        f"{field}_compression": float(reference[field]) / float(candidate[field])
        for field in ratio_fields
    }
    checks = {
        "minimum_dof_target_le_90000": candidate[
            "full3d_equivalent_dofs"
        ]
        <= 90000,
        "global_p6_compression_ge_2": ratios[
            "full3d_equivalent_dofs_compression"
        ]
        >= 2.0,
        "active_rows_reduced": candidate["active_rows"] < reference["active_rows"],
        "matrix_nnz_reduced": candidate["matrix_nnz"] < reference["matrix_nnz"],
        "factor_nnz_reduced": candidate["factor_nnz"] < reference["factor_nnz"],
        "overall_peak_reduced": candidate[
            "overall_process_tree_peak_gib"
        ]
        < reference["overall_process_tree_peak_gib"],
        "p6_stage_peak_reduced": candidate[
            "p6_solve_stage_process_tree_peak_gib"
        ]
        < reference["p6_solve_stage_process_tree_peak_gib"],
        "assembly_reduced": candidate["assembly_seconds"]
        < reference["assembly_seconds"],
        "mumps_setup_reduced": candidate["mumps_setup_seconds"]
        < reference["mumps_setup_seconds"],
    }
    return {
        "schema_version": "task035b.cross-mesh-resource-comparison.v1",
        "global_h10_p6_reference": reference,
        "candidate_h15_p6": candidate,
        "compression_ratios": ratios,
        "checks": checks,
        "pass": all(checks.values()),
    }


def audit_global_p6_same_error(
    *,
    control_record_path: Path,
    control_record_sha256: str,
    candidate_record_path: Path,
    candidate_record_sha256: str,
) -> dict[str, Any]:
    """Build the complete h15-candidate audit without rerunning a PDE."""

    control_record_path = Path(control_record_path).resolve()
    candidate_record_path = Path(candidate_record_path).resolve()
    if _sha256(control_record_path) != str(control_record_sha256):
        raise ValueError("Task035b global p5/p6 control SHA256 mismatch")
    if _sha256(candidate_record_path) != str(candidate_record_sha256):
        raise ValueError("Task035b compressed candidate SHA256 mismatch")
    control_record = json.loads(control_record_path.read_text(encoding="utf-8"))
    candidate_record = json.loads(
        candidate_record_path.read_text(encoding="utf-8")
    )
    control_dir = _run_dir(control_record)
    candidate_dir = _run_dir(candidate_record)
    control_p5, control_p5_authority = _load_summary(
        control_dir,
        "coarse_p5",
    )
    control_p6, control_p6_authority = _load_summary(
        control_dir,
        "enriched_p6",
    )
    candidate_p6, candidate_p6_authority = _load_summary(
        candidate_dir,
        "enriched_p6",
    )
    observable_comparison = compare_observables(
        candidate_p6,
        control_p5,
        control_p6,
    )
    channel_comparison = compare_diffraction_channels(
        global_p5_path=control_dir
        / "coarse_p5"
        / "dtn_port_diffraction_orders_3d.json",
        global_p6_path=control_dir
        / "enriched_p6"
        / "dtn_port_diffraction_orders_3d.json",
        candidate_p6_path=candidate_dir
        / "enriched_p6"
        / "dtn_port_diffraction_orders_3d.json",
    )
    field_comparison = compare_cross_mesh_fields(
        global_p5_dir=control_dir / "coarse_p5",
        global_p6_dir=control_dir / "enriched_p6",
        candidate_p6_dir=candidate_dir / "enriched_p6",
    )
    identity_and_residuals = audit_identity_and_residuals(
        control_record=control_record,
        candidate_record=candidate_record,
        control_summaries={
            "coarse_p5": control_p5,
            "enriched_p6": control_p6,
        },
        candidate_summary=candidate_p6,
    )
    resource_comparison = compare_resources(
        control_record=control_record,
        candidate_record=candidate_record,
        global_p6_summary=control_p6,
        candidate_p6_summary=candidate_p6,
    )
    accuracy_pass = bool(
        observable_comparison["pass"]
        and channel_comparison["pass"]
        and field_comparison["pass"]
    )
    execution_pass = bool(identity_and_residuals["pass"])
    resource_pass = bool(resource_comparison["pass"])
    candidate_same_error_pass = execution_pass and accuracy_pass and resource_pass
    status = (
        "same_error_compression_pass"
        if candidate_same_error_pass
        else "controlled_negative_full_same_error_gate"
        if execution_pass and resource_pass
        else "same_error_audit_fail"
    )
    return {
        "schema_version": "task035b.global-p6-cross-mesh-same-error.v1",
        "benchmark_id": "task035b_global_p6_same_error_comparison",
        "status": status,
        "pass": candidate_same_error_pass,
        "audit_complete": True,
        "candidate_same_error_pass": candidate_same_error_pass,
        "classification": {
            "full_same_error": (
                "positive" if candidate_same_error_pass else "controlled_negative"
            ),
            "scalar_field_resource_signal": (
                "positive"
                if observable_comparison["pass"]
                and field_comparison["pass"]
                and resource_pass
                else "negative"
            ),
            "channel_signal": (
                "positive" if channel_comparison["pass"] else "negative"
            ),
        },
        "no_threshold_relaxation": True,
        "ordinary_default_changed": False,
        "control_authority": {
            "path": str(control_record_path),
            "sha256": control_record_sha256,
            "source_commit_sha": control_record["source"]["commit_sha"],
            "raw_summaries": {
                "global_p5": control_p5_authority,
                "global_p6": control_p6_authority,
            },
        },
        "candidate_authority": {
            "path": str(candidate_record_path),
            "sha256": candidate_record_sha256,
            "source_commit_sha": candidate_record["source"]["commit_sha"],
            "raw_summary": candidate_p6_authority,
        },
        "identity_and_full_residual_gate": identity_and_residuals,
        "strict_observable_gate": observable_comparison,
        "significant_diffraction_channel_gate": channel_comparison,
        "selected_field_interface_error_gate": field_comparison,
        "resource_gate": resource_comparison,
        "failed_gates": [
            name
            for name, passed in (
                ("identity_and_full_residual", execution_pass),
                ("strict_observables", observable_comparison["pass"]),
                ("significant_diffraction_channels", channel_comparison["pass"]),
                ("selected_field_interface", field_comparison["pass"]),
                ("resource", resource_pass),
            )
            if not passed
        ],
    }


__all__ = [
    "ProbeSet",
    "audit_global_p6_same_error",
    "audit_identity_and_residuals",
    "build_task034_fixed_probe_sets",
    "compare_cross_mesh_fields",
    "compare_diffraction_channels",
    "compare_significant_channels_to_reference_v1",
    "compare_observables",
    "compare_resources",
    "sample_owned_vtu_shards",
]
