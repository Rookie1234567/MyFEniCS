"""Frozen Task40 V20 original-size AUTO port inventory.

This module reads the reviewed mode rows and checks them against the explicit
target input. It never calls the AUTO mode generator.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


TARGET_MODE_MANIFEST_PATH = (
    "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/"
    "original_size_auto_mode_manifest.json"
)
TARGET_MODE_LEDGER_PATH = (
    "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/"
    "target_ledger.json"
)
TARGET_MODE_MANIFEST_SHA256 = "52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d"
TARGET_MODE_KEY_SHA256 = "03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec"
TARGET_MODE_PHYSICAL_IDENTITY_SHA256 = "a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f"
TARGET_MODE_INVENTORY_IDENTITY_SHA256 = "39b457c3f0b9d8db5f85a8f1482734513d48670c017d4c8060cae734bdcd0c12"
TARGET_MODE_LEDGER_SHA256 = "8dd917dbb7252bfb0abca81213f3d3cba93cd1f35010a55cbf8c27e2f32ecd4a"
TARGET_MODE_COUNT = 32060
TARGET_MODE_SIDE_COUNTS = {"top": 16030, "bottom": 16030}
TARGET_MODE_POLARIZATION_COUNTS = {"s": 16030, "p": 16030}
TARGET_REFERENCE_PLANES_NM = {"top": 130.0, "bottom": -10.0}


def _complex(value: Any, name: str) -> complex:
    if isinstance(value, Mapping):
        result = complex(float(value["real"]), float(value["imag"]))
    else:
        result = complex(value)
    if not np.isfinite((result.real, result.imag)).all():
        raise ValueError(f"frozen AUTO {name} is not finite")
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _close(actual: Any, expected: float, *, atol: float = 2.0e-12) -> bool:
    try:
        value = float(actual)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(value) and np.isclose(value, expected, rtol=0.0, atol=atol))


def _complex_pair(value: Any) -> complex:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("target V20 complex material values must be [real, imag]")
    result = complex(float(value[0]), float(value[1]))
    if not np.isfinite((result.real, result.imag)).all():
        raise ValueError("target V20 complex material value is non-finite")
    return result


def _verify_physical_identity(
    config: Mapping[str, Any], identity: Mapping[str, Any]
) -> None:
    geometry = config.get("geometry", {})
    materials = config.get("materials", {})
    incidence = config.get("incidence", {})
    boundary = config.get("boundary", {})
    expected_geometry = identity.get("geometry", {})
    scalar_pairs = (
        (geometry.get("period_x_nm"), expected_geometry.get("period_x_nm")),
        (geometry.get("period_y_nm"), expected_geometry.get("period_y_nm")),
        (geometry.get("z_min_nm"), expected_geometry.get("z_min_nm")),
        (geometry.get("z_max_nm"), expected_geometry.get("z_max_nm")),
        (geometry.get("grating_height_nm"), expected_geometry.get("grating_height_nm")),
        (geometry.get("grating_width_x_nm"), expected_geometry.get("grating_width_x_nm")),
        (geometry.get("grating_width_y_nm"), expected_geometry.get("grating_width_y_nm")),
    )
    if not all(_close(actual, float(expected)) for actual, expected in scalar_pairs):
        raise ValueError("target geometry does not match the frozen AUTO external-port identity")
    actual_void = geometry.get("air_void_box_nm")
    expected_void = expected_geometry.get("air_void_box_nm")
    if (
        not isinstance(actual_void, (list, tuple))
        or not isinstance(expected_void, (list, tuple))
        or len(actual_void) != 6
        or len(expected_void) != 6
        or not all(_close(a, float(e)) for a, e in zip(actual_void, expected_void, strict=True))
    ):
        raise ValueError("target notch coordinates differ from the frozen V20 recipe")

    top = identity.get("materials", {}).get("top_external_medium", {})
    bottom = identity.get("materials", {}).get("bottom_external_medium", {})
    if _complex_pair(materials.get("n_air")) != _complex_pair(top.get("refractive_index")):
        raise ValueError("target top material differs from the frozen AUTO identity")
    if _complex_pair(materials.get("n_substrate")) != _complex_pair(bottom.get("refractive_index")):
        raise ValueError("target substrate differs from the frozen AUTO identity")
    if _complex_pair(materials.get("mu_r")) != _complex_pair(top.get("relative_permeability")):
        raise ValueError("target permeability differs from the frozen AUTO identity")
    frozen_incidence = identity.get("incidence", {})
    incidence_pairs = (
        (incidence.get("grazing_angle_deg"), frozen_incidence.get("grazing_angle_deg")),
        (incidence.get("azimuth_deg"), frozen_incidence.get("azimuth_deg")),
        (incidence.get("electric_amplitude"), frozen_incidence.get("electric_amplitude", [None])[0]),
    )
    if (
        not all(_close(actual, float(expected)) for actual, expected in incidence_pairs)
        or incidence.get("polarization") != frozen_incidence.get("polarization")
        or not _close(incidence.get("wavelength_nm"), float(identity.get("wavelength_nm")))
    ):
        raise ValueError("target incidence differs from the frozen AUTO identity")
    if (
        boundary.get("dtn_order_policy") != "auto_propagating"
        or identity.get("ports", {}).get("order_policy") != "auto_propagating"
        or boundary.get("vertical_boundary") != "dtn_port"
    ):
        raise ValueError("target boundary must use the frozen AUTO propagating-port policy")


def load_v20_target_mode_inventory(
    config: Mapping[str, Any],
) -> tuple[tuple[Any, ...], tuple[Mapping[str, Any], ...], str, dict[str, Any]]:
    """Load and validate the exact saved 32060-row V20 target mode table."""

    from src.common.modes_3d import PortMode3D

    root = Path(__file__).resolve().parents[2]
    execution = config.get("execution", {})
    if not isinstance(execution, Mapping):
        raise ValueError("target V20 input has no execution identity")
    if (
        execution.get("task40_mode_manifest_path") != TARGET_MODE_MANIFEST_PATH
        or execution.get("task40_target_ledger_path") != TARGET_MODE_LEDGER_PATH
        or execution.get("task40_mode_manifest_sha256") != TARGET_MODE_MANIFEST_SHA256
        or execution.get("task40_mode_key_sha256") != TARGET_MODE_KEY_SHA256
        or execution.get("task40_target_physical_identity_sha256")
        != TARGET_MODE_PHYSICAL_IDENTITY_SHA256
        or execution.get("task40_target_inventory_identity_sha256")
        != TARGET_MODE_INVENTORY_IDENTITY_SHA256
        or execution.get("task40_target_ledger_sha256") != TARGET_MODE_LEDGER_SHA256
    ):
        raise ValueError("target V20 input is not bound to the frozen AUTO mode identity")
    manifest_path = (root / TARGET_MODE_MANIFEST_PATH).resolve()
    ledger_path = (root / TARGET_MODE_LEDGER_PATH).resolve()
    if manifest_path != root / TARGET_MODE_MANIFEST_PATH or ledger_path != root / TARGET_MODE_LEDGER_PATH:
        raise ValueError("target V20 mode identity paths escaped the repository root")
    if _file_sha256(manifest_path) != TARGET_MODE_MANIFEST_SHA256:
        raise ValueError("frozen original-size mode manifest SHA-256 mismatch")
    actual_ledger_sha256 = _file_sha256(ledger_path)
    if actual_ledger_sha256 != TARGET_MODE_LEDGER_SHA256:
        raise ValueError("frozen target ledger file SHA-256 mismatch")

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if (
        ledger.get("target_mode_physical_identity_sha256")
        != TARGET_MODE_PHYSICAL_IDENTITY_SHA256
        or ledger.get("original_size_ordered_mode_inventory_identity_sha256")
        != TARGET_MODE_INVENTORY_IDENTITY_SHA256
    ):
        raise ValueError("target ledger physical or ordered-inventory identity mismatch")
    actual_physical_sha256 = hashlib.sha256(
        _canonical_json_bytes(ledger.get("target_mode_physical_identity"))
    ).hexdigest()
    actual_inventory_sha256 = hashlib.sha256(
        _canonical_json_bytes(ledger.get("original_size_ordered_mode_inventory_identity"))
    ).hexdigest()
    if (
        actual_physical_sha256 != TARGET_MODE_PHYSICAL_IDENTITY_SHA256
        or actual_inventory_sha256 != TARGET_MODE_INVENTORY_IDENTITY_SHA256
    ):
        raise ValueError("target ledger canonical identity content hash mismatch")
    identity = ledger.get("target_mode_physical_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("target ledger omits its physical mode identity")
    _verify_physical_identity(config, identity)

    recorded_generator_hashes = ledger.get("generator_source_sha256")
    if not isinstance(recorded_generator_hashes, Mapping):
        raise ValueError("target ledger omits the AUTO generator source lineage")
    generator_source_comparison = {}
    for relative, recorded_sha256 in recorded_generator_hashes.items():
        source_path = (root / str(relative)).resolve()
        if source_path != root / str(relative) or not source_path.is_file():
            raise ValueError("recorded AUTO generator source path is unavailable or escaped")
        current_sha256 = _file_sha256(source_path)
        generator_source_comparison[str(relative)] = {
            "recorded_sha256": str(recorded_sha256),
            "current_sha256": current_sha256,
            "matches": current_sha256 == recorded_sha256,
        }

    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = document.get("modes")
    if document.get("mode_count") != TARGET_MODE_COUNT or not isinstance(rows, list) or len(rows) != TARGET_MODE_COUNT:
        raise ValueError("frozen target AUTO inventory must contain exactly 32060 ordered modes")
    keys = []
    side_counts = {"top": 0, "bottom": 0}
    polarization_counts = {"s": 0, "p": 0}
    periods = (
        float(config["geometry"]["period_x_nm"]),
        float(config["geometry"]["period_y_nm"]),
    )
    wavelength = float(config["incidence"]["wavelength_nm"])
    grazing = np.deg2rad(float(config["incidence"]["grazing_angle_deg"]))
    azimuth = np.deg2rad(float(config["incidence"]["azimuth_deg"]))
    k0 = 2.0 * np.pi / wavelength
    incident_alpha = k0 * float(np.real(_complex_pair(config["materials"]["n_air"]))) * np.cos(grazing) * np.cos(azimuth)
    incident_gamma = k0 * float(np.real(_complex_pair(config["materials"]["n_air"]))) * np.cos(grazing) * np.sin(azimuth)
    modes = []
    frozen_rows = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or row.get("mode_index") != index:
            raise ValueError("frozen target AUTO rows are not in exact mode_index order")
        side = row.get("side")
        polarization = row.get("polarization")
        if side not in side_counts or polarization not in polarization_counts:
            raise ValueError("frozen target AUTO row has an invalid side or polarization")
        side_counts[side] += 1
        polarization_counts[polarization] += 1
        m, n = row.get("m"), row.get("n")
        if type(m) is not int or type(n) is not int:
            raise ValueError("frozen target AUTO row has a non-integer order key")
        keys.append([side, m, n, polarization])
        alpha = _complex(row.get("alpha"), "alpha")
        gamma = _complex(row.get("gamma"), "gamma")
        beta = _complex(row.get("beta"), "beta")
        k = np.asarray([_complex(value, "k_vector") for value in row.get("k_vector", ())], dtype=np.complex128)
        e = np.asarray([_complex(value, "e_vector") for value in row.get("e_vector", ())], dtype=np.complex128)
        h = np.asarray([_complex(value, "h_vector") for value in row.get("h_vector", ())], dtype=np.complex128)
        if k.shape != (3,) or e.shape != (3,) or h.shape != (3,):
            raise ValueError("frozen target AUTO vector has the wrong dimension")
        if (
            abs(alpha - (incident_alpha + 2.0 * np.pi * m / periods[0])) > 2.0e-10
            or abs(gamma - (incident_gamma + 2.0 * np.pi * n / periods[1])) > 2.0e-10
            or abs(k[0] - alpha) > 2.0e-12
            or abs(k[1] - gamma) > 2.0e-12
            or abs(k[2] - int(row.get("vertical_sign")) * beta) > 2.0e-12
            or not _close(float(row.get("projection_denominator")), float(row.get("projection_denominator")))
            or float(row["projection_denominator"]) <= 0.0
        ):
            raise ValueError("frozen target AUTO wavevector/phase differs from this input")
        expected_index = (
            _complex_pair(config["materials"]["n_air"])
            if side == "top"
            else _complex_pair(config["materials"]["n_substrate"])
        )
        if _complex(row.get("refractive_index"), "refractive_index") != expected_index:
            raise ValueError("frozen target AUTO row uses a different port medium")
        if not np.isfinite(e).all() or not np.isfinite(h).all() or not np.isfinite(k).all():
            raise ValueError("frozen target AUTO vector contains non-finite values")
        mode = PortMode3D(
            side=str(side),
            m=m,
            n=n,
            polarization=str(polarization),
            alpha=alpha,
            gamma=gamma,
            beta=beta,
            refractive_index=expected_index,
            vertical_sign=int(row["vertical_sign"]),
            e_vector=e,
            k_vector=k,
            h_vector=h,
            electric_tangential_norm_sq=float(row["electric_tangential_norm_sq"]),
            power_per_unit_amplitude=float(row["power_per_unit_amplitude"]),
            propagating=bool(row["propagating"]),
            rayleigh_warning=bool(row["rayleigh_warning"]),
        )
        modes.append(mode)
        frozen = dict(row)
        frozen["reference_plane_nm"] = TARGET_REFERENCE_PLANES_NM[side]
        frozen_rows.append(frozen)

    key_sha = hashlib.sha256(
        json.dumps(keys, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if (
        key_sha != TARGET_MODE_KEY_SHA256
        or side_counts != TARGET_MODE_SIDE_COUNTS
        or polarization_counts != TARGET_MODE_POLARIZATION_COUNTS
    ):
        raise ValueError("frozen target AUTO ordered keys/side/polarization inventory mismatch")
    metadata = {
        "schema": "task40extra.review_v20_original_size_auto_modes.v1",
        "mode_manifest_path": TARGET_MODE_MANIFEST_PATH,
        "mode_manifest_sha256": TARGET_MODE_MANIFEST_SHA256,
        "ordered_mode_key_sha256": key_sha,
        "physical_identity_sha256": TARGET_MODE_PHYSICAL_IDENTITY_SHA256,
        "inventory_identity_sha256": TARGET_MODE_INVENTORY_IDENTITY_SHA256,
        "ledger_path": TARGET_MODE_LEDGER_PATH,
        "ledger_file_sha256": actual_ledger_sha256,
        "generator": ledger.get("generator"),
        "generator_source_sha256_recorded": dict(recorded_generator_hashes),
        "generator_source_comparison": generator_source_comparison,
        "generator_source_matches_current": all(
            item["matches"] for item in generator_source_comparison.values()
        ),
        "source_input_lineage": {
            "input_sha256": ledger.get("source_input_sha256"),
            "physical_model_sha256": ledger.get("source_input_physical_model_sha256"),
            "physical_model_scope": ledger.get("source_input_physical_model_sha256_scope"),
            "note": "source input was the earlier shrunken Gx784 case, not this original-size V20 dat",
        },
        "ledger_canonical_physical_identity_sha256": actual_physical_sha256,
        "ledger_canonical_inventory_identity_sha256": actual_inventory_sha256,
        "mode_count": len(modes),
        "side_counts": side_counts,
        "polarization_counts": polarization_counts,
        "phase_wavevector_check": "PASS",
        "generated_or_reenumerated": False,
    }
    return tuple(modes), tuple(frozen_rows), TARGET_MODE_MANIFEST_SHA256, metadata


__all__ = [
    "TARGET_MODE_COUNT",
    "TARGET_MODE_INVENTORY_IDENTITY_SHA256",
    "TARGET_MODE_KEY_SHA256",
    "TARGET_MODE_LEDGER_PATH",
    "TARGET_MODE_LEDGER_SHA256",
    "TARGET_MODE_MANIFEST_PATH",
    "TARGET_MODE_MANIFEST_SHA256",
    "TARGET_MODE_PHYSICAL_IDENTITY_SHA256",
    "load_v20_target_mode_inventory",
]
