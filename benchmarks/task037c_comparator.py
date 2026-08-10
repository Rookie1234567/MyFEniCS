"""Read-only comparison contracts for Task37c evidence.

The three loaders below consume the production records only:

* direct Hybrid uses the memory-watchdog summary and its bound ignored solver
  record;
* iterative Hybrid uses the iterative watchdog and its bound online record;
* Full3D uses the promoted Full3D watchdog record itself.

The module never starts a solver and never reconstructs physical fields.  It
only reloads hash-bound evidence and compares already exported values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.canonical_vector_artifacts import compare_canonical_manifests
from benchmarks.task037c_robustness import choose_m_robust


COMPARATOR_SCHEMA = "task037c.offline-comparator.v1"
ROOT = Path(__file__).resolve().parents[1]
ARRAY_KEYS = frozenset(
    {
        "x_nm",
        "y_nm",
        "z_nm",
        "E_V_per_m",
        "H_A_per_m",
        "modal_amplitudes",
        "bottom_q",
        "top_q",
    }
)
FULL3D_ARRAY_KEYS = frozenset({"x_nm", "y_nm", "z_nm", "E_V_per_m", "H_A_per_m"})
PHI_VALUES = (-5.0, 0.0, 5.0)
TOTAL_M120_TOL = 1.0e-6
TOTAL_FULL3D_TOL = 1.0e-5
SIGNIFICANT_RELATIVE_TOL = 1.0e-4
INTERFACE_PROJECTION_TOL = 1.0e-8
INTERFACE_E_TOL = 5.0e-3
INTERFACE_H_FULL3D_TOL = 1.0e-2
FIELD_RELATIVE_TOL = 5.0e-3
Q_RELATIVE_TOL = 1.0e-6
CANONICAL_RELATIVE_TOL = 1.0e-5
MODAL_MAGNITUDE_TOL = 1.0e-6


@dataclass(frozen=True)
class NormalizedCase:
    method: str
    mpi_size: int
    requested_modes: int | None
    phi_deg: float
    source_sha: str
    record: Mapping[str, Any]
    payload_path: Path
    payload_sha256: str
    payload: Mapping[str, np.ndarray]
    observables: Mapping[str, float]
    orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]]
    mode_keys: Mapping[str, tuple[tuple[str, int, int, str], ...]]
    canonical: Mapping[tuple[str, str], tuple[Path, str]]
    interface_projection: float | None
    own_pass: bool
    official: bool


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hex_digest(value: Any, length: int) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"expected lowercase {length}-hex digest")
    return value


def _complex_value(value: Any) -> complex:
    if isinstance(value, list):
        if len(value) != 2:
            raise ValueError("JSON complex value must have two entries")
        real, imag = (float(item) for item in value)
        if not math.isfinite(real) or not math.isfinite(imag):
            raise ValueError("JSON complex value is not finite")
        return complex(real, imag)
    coefficient = complex(value)
    if not math.isfinite(coefficient.real) or not math.isfinite(coefficient.imag):
        raise ValueError("complex value is not finite")
    return coefficient


def _resolve_path(anchor: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("artifact path must be a non-empty string")
    raw = Path(value)
    if raw.is_absolute():
        candidate = raw
    else:
        candidates = (anchor.parent / raw, ROOT / raw)
        candidate = next((item for item in candidates if item.is_file()), None)
        if candidate is None:
            raise FileNotFoundError(f"artifact is missing: {value}")
    if not candidate.is_file():
        raise FileNotFoundError(f"artifact is missing: {value}")
    return candidate.resolve()


def _resolve_full3d_path(run_directory: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Full3D artifact path is missing")
    raw = Path(value)
    candidate = raw if raw.is_absolute() else run_directory / raw
    if not candidate.is_file():
        raise FileNotFoundError(f"Full3D artifact is missing: {value}")
    return candidate.resolve()


def _bind_file(
    descriptor: Mapping[str, Any], anchor: Path, label: str
) -> tuple[Path, str]:
    path = _resolve_path(anchor, descriptor.get("path"))
    expected = _hex_digest(descriptor.get("sha256"), 64)
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{label} SHA mismatch")
    if "bytes" in descriptor and int(descriptor["bytes"]) != path.stat().st_size:
        raise ValueError(f"{label} byte count mismatch")
    return path, actual


def _bind_full3d_file(
    descriptor: Mapping[str, Any], run_directory: Path, label: str
) -> tuple[Path, str]:
    path = _resolve_full3d_path(run_directory, descriptor.get("path"))
    expected = _hex_digest(descriptor.get("sha256"), 64)
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{label} SHA mismatch")
    if int(descriptor.get("bytes")) != path.stat().st_size:
        raise ValueError(f"{label} byte count mismatch")
    return path, actual


def _load_json(path: Path, expected_sha: str) -> Mapping[str, Any]:
    actual = _sha256(path)
    if actual != _hex_digest(expected_sha, 64):
        raise ValueError(f"JSON SHA mismatch: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON: {path}") from error
    return _mapping(value, str(path))


def _full3d_run_directory(record: Mapping[str, Any]) -> Path:
    raw_evidence = _mapping(record.get("raw_evidence"), "full3d.raw_evidence")
    value = raw_evidence.get("run_directory")
    if not isinstance(value, str) or not value:
        raise ValueError("Full3D raw_evidence.run_directory is missing")
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_dir():
        raise FileNotFoundError("Full3D raw evidence run directory is missing")
    return path.resolve()


def _watchdog_source_sha(watchdog: Mapping[str, Any]) -> str:
    source = _mapping(
        watchdog.get("source_preflight", watchdog.get("source")),
        "watchdog.source",
    )
    value = source.get("head", source.get("commit_sha"))
    if value is None:
        value = source.get("verified_clean_sha")
    return str(value).lower()


def _check_watchdog_qualification(
    watchdog: Mapping[str, Any], method: str
) -> tuple[bool, bool]:
    if watchdog.get("failures", []) != []:
        raise ValueError("watchdog has failures")
    status = watchdog.get("status")
    if method == "direct":
        required = {
            "status": status == "task037c_direct_robustness_pass",
            "formal_pass": watchdog.get("formal_pass") is True,
            "official_result": watchdog.get("official_result") is True,
            "task037c_direct_pass": watchdog.get("task037c_direct_pass") is True,
            "return_code": watchdog.get("return_code") == 0,
            "no_swap": watchdog.get("no_swap") is True,
            "source_gate": _mapping(watchdog.get("source_gate"), "source_gate").get(
                "pass"
            )
            is True,
            "launch_gate": _mapping(watchdog.get("launch_gate"), "launch_gate").get(
                "pass"
            )
            is True,
            "memory_authority_pass": watchdog.get("memory_authority_pass") is True,
        }
        if not all(required.values()):
            raise ValueError("direct watchdog qualification did not pass")
        return True, True
    if method == "iterative":
        qualification = _mapping(
            watchdog.get("qualification"), "watchdog.qualification"
        )
        required = {
            "status": status == "watchdog_pass_awaiting_offline_checker",
            "qualification": qualification.get("pass") is True,
            "online_official": watchdog.get("official_result") in (None, False),
        }
        if not all(required.values()):
            raise ValueError("iterative watchdog qualification did not pass")
        return True, False
    if method == "full3d":
        solver_summary = _mapping(
            watchdog.get("solver_summary"), "full3d.solver_summary"
        )
        qualification = _mapping(watchdog.get("qualification"), "full3d.qualification")
        required = {
            "status": status == "task037c_full3d_robustness_pass",
            "qualification": qualification.get("pass") is True,
            "official_result": solver_summary.get("official_result") is True,
            "return_code": watchdog.get("return_code") == 0,
            "no_swap": watchdog.get("no_swap") is True,
        }
        if not all(required.values()):
            raise ValueError("Full3D watchdog qualification did not pass")
        return True, True
    raise ValueError(f"unsupported method: {method}")


def _record_identity(record: Mapping[str, Any], method: str) -> dict[str, Any]:
    if method == "direct":
        metadata = _mapping(record.get("metadata"), "direct.metadata")
        case = _mapping(record.get("case"), "direct.case")
        identity = {
            "source_sha": metadata.get("commit_sha"),
            "theta_deg": case.get("incident_theta_deg"),
            "grazing_deg": case.get("incident_grazing_deg"),
            "phi_deg": metadata.get("incident_phi_deg"),
            "polarization": case.get("polarization_kind"),
            "requested_modes": case.get("requested_modes_per_direction"),
            "mpi_size": metadata.get("mpi_size"),
        }
    elif method == "iterative":
        profile = _mapping(record.get("profile"), "iterative.profile")
        source = _mapping(record.get("source"), "iterative.source")
        before = _mapping(source.get("before"), "iterative.source.before")
        identity = {
            "source_sha": before.get("verified_clean_sha"),
            "theta_deg": 90.0 - float(profile["incident_grazing_deg"]),
            "grazing_deg": profile["incident_grazing_deg"],
            "phi_deg": profile["incident_phi_deg"],
            "polarization": profile["polarization_kind"],
            "requested_modes": profile["requested_modes"],
            "mpi_size": profile.get("mpi_size"),
        }
    elif method == "full3d":
        solver_summary = _mapping(record.get("solver_summary"), "full3d.solver_summary")
        config = _mapping(solver_summary.get("config"), "full3d.solver_summary.config")
        source = _mapping(record.get("source"), "full3d.source")
        identity = {
            "source_sha": source.get("commit_sha"),
            "theta_deg": config.get("incident_theta_deg"),
            "grazing_deg": 90.0 - float(config["incident_theta_deg"]),
            "phi_deg": config.get("incident_phi_deg"),
            "polarization": config.get("polarization_kind"),
            "requested_modes": config.get("requested_modes"),
            "mpi_size": record.get("mpi_size"),
        }
    else:
        raise ValueError(f"unsupported method: {method}")
    for key in ("source_sha", "theta_deg", "grazing_deg", "phi_deg", "polarization"):
        if identity.get(key) is None:
            raise ValueError(f"record identity is missing {key}")
    return identity


def _check_identity(
    watchdog: Mapping[str, Any],
    record: Mapping[str, Any],
    method: str,
    expected_source_sha: str,
    expected_phi: float,
) -> dict[str, Any]:
    source_sha = _hex_digest(expected_source_sha, 40)
    identity = _record_identity(record, method)
    if str(identity["source_sha"]).lower() != source_sha:
        raise ValueError("record source SHA does not match expected source")
    if _watchdog_source_sha(watchdog) != source_sha:
        raise ValueError("watchdog source SHA does not match expected source")
    if not math.isclose(float(identity["theta_deg"]), 89.0, abs_tol=1.0e-12):
        raise ValueError("Task37c theta must be 89 degrees")
    if not math.isclose(float(identity["grazing_deg"]), 1.0, abs_tol=1.0e-12):
        raise ValueError("Task37c grazing must be 1 degree")
    if not math.isclose(float(identity["phi_deg"]), expected_phi, abs_tol=1.0e-12):
        raise ValueError("record phi does not match requested phi")
    if identity["polarization"] != "s":
        raise ValueError("Task37c comparator requires S polarization")
    return identity


def _descriptor_from_record(
    record: Mapping[str, Any], method: str
) -> Mapping[str, Any]:
    if method == "direct":
        physical = _mapping(
            record.get("physical_field_reconstruction"),
            "direct.physical_field_reconstruction",
        )
        return _mapping(physical.get("task037c_direct_payload"), "direct.payload")
    if method == "iterative":
        physics = _mapping(record.get("physics"), "iterative.physics")
        return _mapping(physics.get("own_grid"), "iterative.physics.own_grid")
    raise ValueError("Full3D uses its reference export, not a payload descriptor")


def _descriptor_arrays(
    archive: Mapping[str, np.ndarray],
    descriptor: Mapping[str, Any],
    names: frozenset[str],
    label: str,
    *,
    require_finite_descriptor: bool,
) -> None:
    if set(archive) != names:
        raise ValueError(f"{label} payload keys are not exact")
    descriptors = _mapping(descriptor.get("arrays"), f"{label}.arrays")
    if set(descriptors) != names:
        raise ValueError(f"{label} payload descriptors are not exact")
    for name, value in archive.items():
        item = _mapping(descriptors[name], f"{label}.{name}")
        if list(value.shape) != list(item.get("shape", [])):
            raise ValueError(f"{label} descriptor shape mismatch")
        if str(value.dtype) != item.get("dtype"):
            raise ValueError(f"{label} descriptor dtype mismatch")
        observed = hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
        if observed != item.get("sha256"):
            raise ValueError(f"{label} descriptor hash mismatch")
        if require_finite_descriptor and item.get("finite") is not True:
            raise ValueError(f"{label} descriptor finite flag is not true")


def _validate_payload_arrays(payload: Mapping[str, np.ndarray], method: str) -> None:
    if payload["x_nm"].shape != (40,) or payload["y_nm"].shape != (20,):
        raise ValueError(f"{method} payload coordinate shape is invalid")
    if payload["z_nm"].shape != (5,) or not np.allclose(
        payload["z_nm"], [10.0, 30.0, 60.0, 90.0, 110.0], atol=1.0e-12, rtol=0.0
    ):
        raise ValueError(f"{method} payload z planes are invalid")
    if payload["E_V_per_m"].shape != (5, 20, 40, 3):
        raise ValueError(f"{method} electric field shape is invalid")
    if payload["H_A_per_m"].shape != (5, 20, 40, 3):
        raise ValueError(f"{method} magnetic field shape is invalid")
    if not np.iscomplexobj(payload["E_V_per_m"]) or not np.iscomplexobj(
        payload["H_A_per_m"]
    ):
        raise ValueError(f"{method} field arrays must be complex")
    for name, value in payload.items():
        if not np.all(np.isfinite(value)):
            raise ValueError(f"{method} payload {name} is not finite")


def _load_full3d_payload(
    record: Mapping[str, Any], run_directory: Path
) -> tuple[Path, str, dict[str, np.ndarray]]:
    solver_summary = _mapping(record.get("solver_summary"), "full3d.solver_summary")
    qualification = _mapping(record.get("qualification"), "full3d.qualification")
    reference = _mapping(
        qualification.get("reference_export"), "full3d.reference_export"
    )
    metadata = _mapping(reference.get("metadata"), "full3d.reference_export.metadata")
    archive_descriptor = {
        "path": reference.get("archive"),
        "sha256": metadata.get("archive_sha256"),
        "bytes": metadata.get("archive_bytes"),
    }
    archive_path, digest = _bind_full3d_file(
        archive_descriptor, run_directory, "full3d.reference_archive"
    )
    summary_archive = _resolve_full3d_path(
        run_directory, solver_summary.get("full3d_reference_archive")
    )
    if summary_archive != archive_path:
        raise ValueError("Full3D reference archive binding does not match summary")
    with np.load(archive_path, allow_pickle=False) as archive:
        archive_names = set(archive.files)
        if not FULL3D_ARRAY_KEYS.issubset(archive_names):
            raise ValueError("Full3D payload is missing required arrays")
        payload = {name: np.asarray(archive[name]).copy() for name in FULL3D_ARRAY_KEYS}
    _validate_payload_arrays(payload, "Full3D")
    return archive_path, digest, payload


def _load_hybrid_payload(
    record: Mapping[str, Any], method: str, anchor: Path
) -> tuple[Path, str, dict[str, np.ndarray]]:
    descriptor = _descriptor_from_record(record, method)
    if set(descriptor.get("keys", ())) != ARRAY_KEYS:
        raise ValueError(f"{method} payload metadata keys are not exact")
    path, digest = _bind_file(descriptor, anchor, f"{method}.payload")
    with np.load(path, allow_pickle=False) as archive:
        payload = {name: np.asarray(archive[name]).copy() for name in archive.files}
    _descriptor_arrays(
        payload,
        descriptor,
        ARRAY_KEYS,
        f"{method}.payload",
        require_finite_descriptor=method == "direct",
    )
    _validate_payload_arrays(payload, method)
    for name in ("modal_amplitudes", "bottom_q", "top_q"):
        if payload[name].ndim != 1 or payload[name].size == 0:
            raise ValueError(f"{method} payload {name} shape is invalid")
    return path, digest, payload


def _observables(record: Mapping[str, Any], method: str) -> dict[str, float]:
    if method == "direct":
        physical = _mapping(
            record.get("physical_field_reconstruction"), "direct.physics"
        )
        validation = _mapping(record.get("validation"), "direct.validation")
        port = _mapping(validation.get("port_power"), "direct.port_power")
        absorption = _mapping(physical.get("volume_absorption"), "direct.absorption")
        source = {
            "R": port.get("R_total"),
            "T": port.get("T_total"),
            "A": port.get("A_balance"),
            "A_volume": absorption.get("A_volume_total"),
            "closure": absorption.get("energy_closure_error"),
        }
    elif method == "iterative":
        physics = _mapping(record.get("physics"), "iterative.physics")
        source = _mapping(physics.get("energy"), "iterative.physics.energy")
    elif method == "full3d":
        source = _mapping(record.get("solver_summary"), "full3d.solver_summary")
        source = {
            "R": source.get("R_total"),
            "T": source.get("T_total"),
            "A": source.get("A_balance"),
            "A_volume": source.get("A_volume_total"),
            "closure": source.get("energy_closure_error_port_volume"),
        }
    else:
        raise ValueError(f"unsupported method: {method}")
    result = {
        name: float(source[name]) for name in ("R", "T", "A", "A_volume", "closure")
    }
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("observables contain a non-finite value")
    return result


def _order_rows(record: Mapping[str, Any], method: str, record_path: Path) -> list[Any]:
    if method == "direct":
        return _mapping(record.get("validation"), "direct.validation").get(
            "external_diffraction_orders"
        )
    if method == "iterative":
        return _mapping(record.get("physics"), "iterative.physics").get(
            "external_orders"
        )
    qualification = _mapping(record.get("qualification"), "full3d.qualification")
    gate = _mapping(qualification.get("external_orders"), "full3d.external_orders")
    descriptor = {
        "path": gate.get("path"),
        "sha256": gate.get("observed_sha256"),
        "bytes": gate.get("bytes"),
    }
    run_directory = _full3d_run_directory(record)
    path, _digest = _bind_full3d_file(descriptor, run_directory, "full3d.orders")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Full3D orders JSON is invalid") from error
    return _mapping(payload, "full3d.orders.json").get("orders")


def _orders(
    record: Mapping[str, Any], method: str, record_path: Path
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    rows = _order_rows(record, method, record_path)
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise ValueError(f"{method} external order rows are missing")
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    side_counts = {"bottom": 0, "top": 0}
    for raw in rows:
        row = _mapping(raw, f"{method}.external_order")
        side = row.get("side")
        m = row.get("m")
        n = row.get("n")
        polarization = row.get("polarization")
        if (
            side not in {"bottom", "top"}
            or isinstance(m, bool)
            or not isinstance(m, int)
            or isinstance(n, bool)
            or not isinstance(n, int)
            or polarization not in {"s", "p"}
        ):
            raise ValueError(f"{method} external order identity is invalid")
        key = (str(side), int(m), int(n), str(polarization))
        if key in result:
            raise ValueError(f"{method} external order keys are not unique")
        beta_name = "beta_per_nm" if "beta_per_nm" in row else "beta"
        beta = _complex_value(row.get(beta_name))
        power_name = "power" if "power" in row else "power_ratio"
        power = float(row.get(power_name))
        if not math.isfinite(power):
            raise ValueError(f"{method} external order power is not finite")
        normalized = dict(row)
        normalized["power"] = power
        if method == "full3d":
            index = side_counts[str(side)]
        else:
            index = row.get("local_auxiliary_index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError(f"{method} external order index is invalid")
        if method != "full3d":
            normalized["local_auxiliary_index"] = int(index)
        normalized["beta"] = beta
        result[key] = normalized
        side_counts[str(side)] += 1
    return result


def _canonical_bindings(
    record: Mapping[str, Any], method: str, anchor: Path
) -> dict[tuple[str, str], tuple[Path, str]]:
    if method == "direct":
        physical = _mapping(
            record.get("physical_field_reconstruction"), "direct.physics"
        )
        canonical = physical.get("task037c_canonical_export")
    elif method == "iterative":
        canonical = _mapping(record.get("physics"), "iterative.physics").get(
            "canonical"
        )
    else:
        return {}
    canonical = _mapping(canonical, f"{method}.canonical")
    bindings: dict[tuple[str, str], tuple[Path, str]] = {}
    for side in ("bottom", "top"):
        side_value = _mapping(canonical.get(side), f"{method}.canonical.{side}")
        roles = _mapping(side_value.get("roles"), f"{method}.canonical.{side}.roles")
        for role in ("active_trace", "full_fe"):
            item = _mapping(roles.get(role), f"{method}.canonical.{side}.{role}")
            path, digest = _bind_file(
                {
                    "path": item.get("manifest"),
                    "sha256": item.get("manifest_sha256"),
                },
                anchor,
                f"{method}.{side}.{role}",
            )
            bindings[(side, role)] = (path, digest)
    return bindings


def _interface_projection(record: Mapping[str, Any], method: str) -> float | None:
    if method == "full3d":
        return None
    if method == "direct":
        validation = _mapping(record.get("validation"), "direct.validation")
        projection = _mapping(
            validation.get("interface_e_projection"), "direct.interface_e_projection"
        )
        value = float(projection["combined_relative_residual"])
    else:
        physics = _mapping(record.get("physics"), "iterative.physics")
        continuity = _mapping(
            physics.get("interface_continuity"), "iterative.interface_continuity"
        )
        value = max(
            float(
                _mapping(continuity[side], f"{side}.interface")["electric_tangential"][
                    "relative_l2"
                ]
            )
            for side in ("bottom", "top")
        )
    if not math.isfinite(value):
        raise ValueError("interface projection is not finite")
    return value


def _expected_modal_count(record: Mapping[str, Any], method: str) -> int | None:
    if method == "direct":
        hybrid_system = _mapping(record.get("hybrid_system"), "direct.hybrid_system")
        value = hybrid_system.get("internal_unknown_count")
    else:
        inventory = _mapping(
            _mapping(record.get("linear"), "iterative.linear").get("inventory"),
            "iterative.linear.inventory",
        )
        block_ldu = _mapping(
            inventory.get("block_ldu"), "iterative.linear.inventory.block_ldu"
        )
        modal = block_ldu.get("modal_schur")
        value = _mapping(modal, "iterative.linear.inventory.modal_schur").get(
            "shape", [None]
        )[0]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{method} modal dimension is invalid")
    return int(value)


def _load_case(
    watchdog_path: Path,
    watchdog_sha256: str,
    *,
    method: str,
    expected_source_sha: str,
    expected_phi: float,
) -> NormalizedCase:
    watchdog = _load_json(watchdog_path, watchdog_sha256)
    if method not in {"full3d", "direct", "iterative"}:
        raise ValueError("unsupported method")
    _check_watchdog_qualification(watchdog, method)
    _hex_digest(expected_source_sha, 40)
    if expected_phi not in PHI_VALUES:
        raise ValueError("unsupported Task37c phi")
    if method == "full3d":
        record_path = watchdog_path.resolve()
        record = watchdog
        artifact_anchor = _full3d_run_directory(record)
    else:
        if method == "direct":
            descriptor = {
                "path": watchdog.get("solver_record_ignored_path"),
                "sha256": watchdog.get("solver_record_sha256"),
            }
        else:
            descriptor = _mapping(
                watchdog.get("online_record"), "watchdog.online_record"
            )
            if (
                descriptor.get("json_valid") is not True
                or descriptor.get("online_pass") is not True
                or descriptor.get("status")
                != "online_candidate_pass_awaiting_offline_checker"
            ):
                raise ValueError("iterative online record descriptor is not qualified")
        record_path, _ = _bind_file(descriptor, watchdog_path, f"{method}.record")
        record = _load_json(record_path, str(descriptor.get("sha256")))
        artifact_anchor = record_path
    identity = _check_identity(
        watchdog, record, method, expected_source_sha, expected_phi
    )
    if method == "iterative":
        source = _mapping(record.get("source"), "iterative.source")
        before = _mapping(source.get("before"), "iterative.source.before")
        after = _mapping(source.get("after"), "iterative.source.after")
        if (
            before.get("verified_clean_sha") != expected_source_sha
            or after.get("head") != expected_source_sha
            or after.get("verified_clean_sha") != expected_source_sha
            or after.get("clean") is not True
            or after.get("matches_verified_clean_sha") is not True
        ):
            raise ValueError("iterative source before/after binding is not clean")
        if (
            record.get("online_pass") is not True
            or record.get("status") != "online_candidate_pass_awaiting_offline_checker"
        ):
            raise ValueError("iterative online record is not qualified")
    requested_modes = identity.get("requested_modes")
    mpi_size = int(identity.get("mpi_size") or watchdog.get("mpi_size") or 0)
    if method == "full3d":
        if requested_modes is not None or mpi_size != 8:
            raise ValueError("Full3D identity is outside the Task37c scope")
    elif method == "direct":
        if requested_modes not in {120, 160} or mpi_size != 8:
            raise ValueError("direct identity is outside the Task37c scope")
    elif requested_modes not in {120, 160} or mpi_size not in {1, 8}:
        raise ValueError("iterative identity is outside the Task37c scope")
    if method == "full3d":
        payload_path, payload_sha, payload = _load_full3d_payload(
            record, artifact_anchor
        )
    else:
        payload_path, payload_sha, payload = _load_hybrid_payload(
            record, method, artifact_anchor
        )
    orders = _orders(record, method, record_path)
    mode_keys = {
        side: tuple(sorted(key for key in orders if key[0] == side))
        for side in ("bottom", "top")
    }
    if any(not keys for keys in mode_keys.values()):
        raise ValueError("both dynamic side mode sets are required")
    if method != "full3d":
        if payload["bottom_q"].size != len(mode_keys["bottom"]):
            raise ValueError("bottom q dimension does not match its mode set")
        if payload["top_q"].size != len(mode_keys["top"]):
            raise ValueError("top q dimension does not match its mode set")
        modal_count = _expected_modal_count(record, method)
        if modal_count is not None and payload["modal_amplitudes"].size != modal_count:
            raise ValueError("modal dimension does not match the recorded system")
        for side in ("bottom", "top"):
            indexes = [orders[key]["local_auxiliary_index"] for key in mode_keys[side]]
            if sorted(indexes) != list(range(len(indexes))):
                raise ValueError(f"{side} local auxiliary indexes are not exact")
        canonical = _canonical_bindings(record, method, record_path)
        if len(canonical) != 4:
            raise ValueError("Hybrid canonical bindings are incomplete")
    else:
        canonical = {}
    if method == "direct":
        own_pass = (
            _mapping(record.get("qualification"), "direct.qualification").get(
                "task037c_direct_pass"
            )
            is True
        )
    elif method == "iterative":
        own_pass = record.get("online_pass") is True
    else:
        own_pass = (
            _mapping(record.get("qualification"), "full3d.qualification").get("pass")
            is True
        )
    if not own_pass:
        raise ValueError(f"{method} own qualification did not pass")
    return NormalizedCase(
        method=method,
        mpi_size=mpi_size,
        requested_modes=(None if requested_modes is None else int(requested_modes)),
        phi_deg=float(identity["phi_deg"]),
        source_sha=str(identity["source_sha"]).lower(),
        record=record,
        payload_path=payload_path,
        payload_sha256=payload_sha,
        payload=payload,
        observables=_observables(record, method),
        orders=orders,
        mode_keys=mode_keys,
        canonical=canonical,
        interface_projection=_interface_projection(record, method),
        own_pass=own_pass,
        official=_check_watchdog_qualification(watchdog, method)[1],
    )


def load_full3d_case(
    watchdog_path: Path,
    watchdog_sha256: str,
    *,
    expected_source_sha: str,
    expected_phi: float,
) -> NormalizedCase:
    return _load_case(
        watchdog_path,
        watchdog_sha256,
        method="full3d",
        expected_source_sha=expected_source_sha,
        expected_phi=expected_phi,
    )


def load_direct_case(
    watchdog_path: Path,
    watchdog_sha256: str,
    *,
    expected_source_sha: str,
    expected_phi: float,
) -> NormalizedCase:
    return _load_case(
        watchdog_path,
        watchdog_sha256,
        method="direct",
        expected_source_sha=expected_source_sha,
        expected_phi=expected_phi,
    )


def load_iterative_case(
    watchdog_path: Path,
    watchdog_sha256: str,
    *,
    expected_source_sha: str,
    expected_phi: float,
) -> NormalizedCase:
    return _load_case(
        watchdog_path,
        watchdog_sha256,
        method="iterative",
        expected_source_sha=expected_source_sha,
        expected_phi=expected_phi,
    )


def _safe_compare(label: str, function: Any, *args: Any) -> dict[str, Any]:
    try:
        return function(*args)
    except (KeyError, TypeError, ValueError, OSError) as error:
        return {"pass": False, "failures": [f"{label}:{error}"]}


def _identity_match(left: NormalizedCase, right: NormalizedCase) -> None:
    if left.source_sha != right.source_sha or not math.isclose(
        left.phi_deg, right.phi_deg, abs_tol=1.0e-12
    ):
        raise ValueError("case source or phi identity mismatch")
    if left.mode_keys != right.mode_keys:
        raise ValueError("case mode keys do not match exactly")


def _coordinates_equal(left: NormalizedCase, right: NormalizedCase) -> dict[str, Any]:
    fields = {
        name: bool(np.array_equal(left.payload[name], right.payload[name]))
        for name in ("x_nm", "y_nm", "z_nm")
    }
    return {"fields": fields, "pass": all(fields.values())}


def _absolute_fields(
    left: Mapping[str, float],
    right: Mapping[str, float],
    fields: Sequence[str],
    tolerance: float,
) -> dict[str, Any]:
    rows = {}
    for field in fields:
        delta = abs(float(left[field]) - float(right[field]))
        rows[field] = {
            "abs_delta": delta,
            "pass": math.isfinite(delta) and delta <= tolerance,
        }
    return {"fields": rows, "pass": all(row["pass"] for row in rows.values())}


def _significant_orders(
    left: NormalizedCase, right: NormalizedCase, tolerance: float
) -> dict[str, Any]:
    _identity_match(left, right)
    rows = {}
    for key in sorted(left.orders):
        lpower = float(left.orders[key]["power"])
        rpower = float(right.orders[key]["power"])
        if max(abs(lpower), abs(rpower)) >= 1.0e-8:
            relative = abs(lpower - rpower) / max(abs(lpower), abs(rpower), 1.0e-30)
            rows[str(key)] = {"relative_delta": relative, "pass": relative <= tolerance}
    if not rows:
        raise ValueError("no significant external order was available")
    return {
        "count": len(rows),
        "fields": rows,
        "pass": all(row["pass"] for row in rows.values()),
    }


def _field_relative(
    left: np.ndarray, right: np.ndarray, *, interface: bool, tolerance: float
) -> dict[str, Any]:
    if left.shape != right.shape:
        raise ValueError("field shape mismatch")
    if interface:
        sections = {
            "bottom": (left[0, ..., :2], right[0, ..., :2]),
            "top": (left[-1, ..., :2], right[-1, ..., :2]),
        }
    else:
        sections = {
            f"z_index_{index}": (left[index], right[index]) for index in (1, 2, 3)
        }
    details = {}
    for name, (left_section, right_section) in sections.items():
        relative = float(
            np.linalg.norm(left_section - right_section)
            / max(
                np.linalg.norm(left_section),
                np.linalg.norm(right_section),
                1.0e-30,
            )
        )
        details[name] = {
            "relative_l2": relative,
            "pass": math.isfinite(relative) and relative <= tolerance,
        }
    maximum = max(item["relative_l2"] for item in details.values())
    return {
        "details": details,
        "max_relative_l2": maximum,
        "pass": math.isfinite(maximum) and maximum <= tolerance,
    }


def _canonical_compare(left: NormalizedCase, right: NormalizedCase) -> dict[str, Any]:
    if set(left.canonical) != set(right.canonical):
        raise ValueError("canonical role set does not match exactly")
    results = {}
    for key in sorted(left.canonical):
        left_path, left_sha = left.canonical[key]
        right_path, right_sha = right.canonical[key]
        results[str(key)] = compare_canonical_manifests(
            left_path,
            right_path,
            left_sha256=left_sha,
            right_sha256=right_sha,
            relative_tolerance=CANONICAL_RELATIVE_TOL,
        )
    return {"roles": results, "pass": all(item["pass"] for item in results.values())}


def _q_relative(left: NormalizedCase, right: NormalizedCase) -> dict[str, Any]:
    _identity_match(left, right)
    rows = {}
    for side in ("bottom", "top"):
        left_by_key = {
            key: left.payload[f"{side}_q"][left.orders[key]["local_auxiliary_index"]]
            for key in left.mode_keys[side]
        }
        right_by_key = {
            key: right.payload[f"{side}_q"][right.orders[key]["local_auxiliary_index"]]
            for key in right.mode_keys[side]
        }
        left_vector = np.asarray([left_by_key[key] for key in sorted(left_by_key)])
        right_vector = np.asarray([right_by_key[key] for key in sorted(right_by_key)])
        relative = float(
            np.linalg.norm(left_vector - right_vector)
            / max(np.linalg.norm(left_vector), np.linalg.norm(right_vector), 1.0e-30)
        )
        rows[side] = {
            "relative_l2": relative,
            "pass": math.isfinite(relative) and relative <= Q_RELATIVE_TOL,
        }
    return {"sides": rows, "pass": all(row["pass"] for row in rows.values())}


def _modal_magnitude(left: NormalizedCase, right: NormalizedCase) -> dict[str, Any]:
    left_values = np.abs(
        np.asarray(left.payload["modal_amplitudes"], dtype=np.complex128)
    )
    right_values = np.abs(
        np.asarray(right.payload["modal_amplitudes"], dtype=np.complex128)
    )
    if left_values.shape != right_values.shape:
        raise ValueError("modal magnitude shape mismatch")
    relative = float(
        np.linalg.norm(left_values - right_values)
        / max(np.linalg.norm(left_values), np.linalg.norm(right_values), 1.0e-30)
    )
    return {
        "relative_l2": relative,
        "pass": math.isfinite(relative) and relative <= MODAL_MAGNITUDE_TOL,
    }


def _compare_m120_m160_impl(
    left: NormalizedCase, right: NormalizedCase
) -> dict[str, Any]:
    if left.method != "direct" or right.method != "direct":
        raise ValueError("M120/M160 comparison requires direct Hybrid cases")
    if left.mpi_size != 8 or right.mpi_size != 8:
        raise ValueError("M120/M160 comparison requires MPI8 cases")
    if {left.requested_modes, right.requested_modes} != {120, 160}:
        raise ValueError("M120/M160 comparison requires exactly M120 and M160")
    if left.requested_modes == right.requested_modes:
        raise ValueError("M120/M160 comparison requires distinct modal counts")
    _identity_match(left, right)
    totals = _absolute_fields(
        left.observables, right.observables, ("R", "T", "A"), TOTAL_M120_TOL
    )
    significant = _significant_orders(left, right, SIGNIFICANT_RELATIVE_TOL)
    if left.interface_projection is None or right.interface_projection is None:
        raise ValueError("M120/M160 interface projection is missing")
    projection = max(left.interface_projection, right.interface_projection)
    coordinates = _coordinates_equal(left, right)
    fields = {
        "interface_projection": {
            "value": projection,
            "pass": projection <= INTERFACE_PROJECTION_TOL,
        },
        "middle_E": _field_relative(
            left.payload["E_V_per_m"],
            right.payload["E_V_per_m"],
            interface=False,
            tolerance=FIELD_RELATIVE_TOL,
        ),
        "middle_H": _field_relative(
            left.payload["H_A_per_m"],
            right.payload["H_A_per_m"],
            interface=False,
            tolerance=FIELD_RELATIVE_TOL,
        ),
    }
    checks = [
        left.own_pass,
        right.own_pass,
        totals["pass"],
        significant["pass"],
        coordinates["pass"],
    ]
    checks.extend(row["pass"] for row in fields.values())
    return {
        "comparison": "m120_vs_m160",
        "coordinates": coordinates,
        "totals": totals,
        "significant_orders": significant,
        "fields": fields,
        "pass": all(checks),
    }


def compare_m120_m160(left: NormalizedCase, right: NormalizedCase) -> dict[str, Any]:
    return _safe_compare("m120_vs_m160", _compare_m120_m160_impl, left, right)


def _compare_hybrid_full3d_impl(
    hybrid: NormalizedCase, full3d: NormalizedCase
) -> dict[str, Any]:
    if hybrid.method not in {"direct", "iterative"} or full3d.method != "full3d":
        raise ValueError("Hybrid/Full3D comparison received the wrong methods")
    if not full3d.official:
        raise ValueError("Full3D authority is not official")
    if hybrid.mpi_size != 8 or full3d.mpi_size != 8:
        raise ValueError("Hybrid/Full3D comparison requires MPI8 cases")
    _identity_match(hybrid, full3d)
    coordinates = _coordinates_equal(hybrid, full3d)
    totals = _absolute_fields(
        hybrid.observables,
        full3d.observables,
        ("R", "T", "A", "A_volume"),
        TOTAL_FULL3D_TOL,
    )
    closure = {
        "hybrid": {
            "abs_value": abs(hybrid.observables["closure"]),
            "pass": abs(hybrid.observables["closure"]) <= TOTAL_FULL3D_TOL,
        },
        "full3d": {
            "abs_value": abs(full3d.observables["closure"]),
            "pass": abs(full3d.observables["closure"]) <= TOTAL_FULL3D_TOL,
        },
    }
    significant = _significant_orders(hybrid, full3d, SIGNIFICANT_RELATIVE_TOL)
    fields = {
        "interface_E": _field_relative(
            hybrid.payload["E_V_per_m"],
            full3d.payload["E_V_per_m"],
            interface=True,
            tolerance=INTERFACE_E_TOL,
        ),
        "interface_H": _field_relative(
            hybrid.payload["H_A_per_m"],
            full3d.payload["H_A_per_m"],
            interface=True,
            tolerance=INTERFACE_H_FULL3D_TOL,
        ),
        "middle_E": _field_relative(
            hybrid.payload["E_V_per_m"],
            full3d.payload["E_V_per_m"],
            interface=False,
            tolerance=FIELD_RELATIVE_TOL,
        ),
        "middle_H": _field_relative(
            hybrid.payload["H_A_per_m"],
            full3d.payload["H_A_per_m"],
            interface=False,
            tolerance=FIELD_RELATIVE_TOL,
        ),
    }
    checks = [
        hybrid.own_pass,
        full3d.own_pass,
        totals["pass"],
        significant["pass"],
        coordinates["pass"],
    ]
    checks.extend(item["pass"] for item in closure.values())
    checks.extend(item["pass"] for item in fields.values())
    return {
        "comparison": "hybrid_vs_full3d",
        "coordinates": coordinates,
        "totals": totals,
        "closure": closure,
        "significant_orders": significant,
        "fields": fields,
        "pass": all(checks),
    }


def compare_hybrid_full3d(
    hybrid: NormalizedCase, full3d: NormalizedCase
) -> dict[str, Any]:
    return _safe_compare(
        "hybrid_vs_full3d", _compare_hybrid_full3d_impl, hybrid, full3d
    )


def _compare_same_equation_impl(
    left: NormalizedCase, right: NormalizedCase, comparison: str
) -> dict[str, Any]:
    if left.requested_modes is None or right.requested_modes is None:
        raise ValueError("same-equation comparison requires requested modes")
    if left.requested_modes != right.requested_modes:
        raise ValueError("same-equation comparison requires equal requested modes")
    _identity_match(left, right)
    coordinates = _coordinates_equal(left, right)
    totals = _absolute_fields(
        left.observables, right.observables, ("R", "T", "A", "A_volume"), TOTAL_M120_TOL
    )
    q = _q_relative(left, right)
    significant = _significant_orders(left, right, SIGNIFICANT_RELATIVE_TOL)
    canonical = _canonical_compare(left, right)
    fields = {
        "interface_E": _field_relative(
            left.payload["E_V_per_m"],
            right.payload["E_V_per_m"],
            interface=True,
            tolerance=FIELD_RELATIVE_TOL,
        ),
        "interface_H": _field_relative(
            left.payload["H_A_per_m"],
            right.payload["H_A_per_m"],
            interface=True,
            tolerance=FIELD_RELATIVE_TOL,
        ),
        "middle_E": _field_relative(
            left.payload["E_V_per_m"],
            right.payload["E_V_per_m"],
            interface=False,
            tolerance=FIELD_RELATIVE_TOL,
        ),
        "middle_H": _field_relative(
            left.payload["H_A_per_m"],
            right.payload["H_A_per_m"],
            interface=False,
            tolerance=FIELD_RELATIVE_TOL,
        ),
    }
    modal = _modal_magnitude(left, right)
    checks = [
        left.own_pass,
        right.own_pass,
        totals["pass"],
        q["pass"],
        significant["pass"],
        canonical["pass"],
        modal["pass"],
        coordinates["pass"],
    ]
    checks.extend(item["pass"] for item in fields.values())
    return {
        "comparison": comparison,
        "coordinates": coordinates,
        "totals": totals,
        "q": q,
        "significant_orders": significant,
        "canonical": canonical,
        "fields": fields,
        "modal_magnitude": modal,
        "pass": all(checks),
    }


def _compare_iterative_direct_impl(
    iterative: NormalizedCase, direct: NormalizedCase
) -> dict[str, Any]:
    if iterative.method != "iterative" or direct.method != "direct":
        raise ValueError("iterative/direct comparison received the wrong methods")
    if iterative.mpi_size != 8 or direct.mpi_size != 8:
        raise ValueError("iterative/direct comparison requires MPI8 cases")
    return _compare_same_equation_impl(iterative, direct, "iterative_vs_direct")


def compare_iterative_direct(
    iterative: NormalizedCase, direct: NormalizedCase
) -> dict[str, Any]:
    return _safe_compare(
        "iterative_vs_direct", _compare_iterative_direct_impl, iterative, direct
    )


def compare_mpi8_mpi1(mpi8: NormalizedCase, mpi1: NormalizedCase) -> dict[str, Any]:
    if mpi8.method != "iterative" or mpi1.method != "iterative":
        return {
            "comparison": "mpi8_vs_mpi1",
            "pass": False,
            "failures": ["mpi8_vs_mpi1:both cases must be iterative"],
        }
    if mpi8.mpi_size != 8 or mpi1.mpi_size != 1:
        return {
            "comparison": "mpi8_vs_mpi1",
            "pass": False,
            "failures": ["mpi8_vs_mpi1:MPI identities are not 8 and 1"],
        }
    return _safe_compare(
        "mpi8_vs_mpi1", _compare_same_equation_impl, mpi8, mpi1, "mpi8_vs_mpi1"
    )


def compare_mirror_power(left: NormalizedCase, right: NormalizedCase) -> dict[str, Any]:
    try:
        if {left.phi_deg, right.phi_deg} != {-5.0, 5.0}:
            raise ValueError("mirror diagnostic requires phi=-5 and phi=+5")
        if left.source_sha != right.source_sha:
            raise ValueError("mirror source SHA mismatch")
        if left.method != right.method:
            raise ValueError("mirror comparison requires the same method")
        if left.requested_modes != right.requested_modes:
            raise ValueError("mirror comparison requires equal requested modes")
        if left.mpi_size != right.mpi_size:
            raise ValueError("mirror comparison requires equal MPI size")
        mapped_right = {
            (side, m, -n, polarization): row
            for (side, m, n, polarization), row in right.orders.items()
        }
        if set(left.orders) != set(mapped_right):
            raise ValueError("mirror mode keys do not match under n reflection")
        coordinates = _coordinates_equal(left, right)
        totals = _absolute_fields(
            left.observables, right.observables, ("R", "T", "A"), TOTAL_M120_TOL
        )
        rows = {}
        for key in sorted(left.orders):
            lpower = float(left.orders[key]["power"])
            rpower = float(mapped_right[key]["power"])
            if max(abs(lpower), abs(rpower)) >= 1.0e-8:
                relative = abs(lpower - rpower) / max(abs(lpower), abs(rpower), 1.0e-30)
                rows[str(key)] = {
                    "relative_delta": relative,
                    "pass": relative <= SIGNIFICANT_RELATIVE_TOL,
                }
        if not rows:
            raise ValueError("mirror comparison has no significant order")
        power = {"fields": rows, "pass": all(row["pass"] for row in rows.values())}
        return {
            "comparison": "mirror_power",
            "coordinates": coordinates,
            "totals": totals,
            "power": power,
            "amplitude": "not_run_without_phase_map",
            "pass": coordinates["pass"] and totals["pass"] and power["pass"],
        }
    except (KeyError, TypeError, ValueError, OSError) as error:
        return {
            "comparison": "mirror_power",
            "amplitude": "not_run_without_phase_map",
            "pass": False,
            "failures": [f"mirror_power:{error}"],
        }


def compare_m_selection(
    m120_results: Sequence[Mapping[str, Any]],
    m160_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return choose_m_robust(m120_results, m160_results)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=COMPARATOR_SCHEMA)
    parser.add_argument("--left-watchdog", type=Path, required=True)
    parser.add_argument("--left-watchdog-sha256", required=True)
    parser.add_argument(
        "--left-method", choices=("full3d", "direct", "iterative"), required=True
    )
    parser.add_argument("--right-watchdog", type=Path, required=True)
    parser.add_argument("--right-watchdog-sha256", required=True)
    parser.add_argument(
        "--right-method", choices=("full3d", "direct", "iterative"), required=True
    )
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--left-phi", type=float, required=True)
    parser.add_argument("--right-phi", type=float, required=True)
    parser.add_argument(
        "--comparison",
        choices=(
            "m120_m160",
            "hybrid_full3d",
            "iterative_direct",
            "mpi8_mpi1",
            "mirror",
        ),
        required=True,
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _load_method_case(
    method: str,
    watchdog_path: Path,
    watchdog_sha: str,
    source_sha: str,
    phi: float,
) -> NormalizedCase:
    if method == "full3d":
        return load_full3d_case(
            watchdog_path,
            watchdog_sha,
            expected_source_sha=source_sha,
            expected_phi=phi,
        )
    if method == "direct":
        return load_direct_case(
            watchdog_path,
            watchdog_sha,
            expected_source_sha=source_sha,
            expected_phi=phi,
        )
    if method == "iterative":
        return load_iterative_case(
            watchdog_path,
            watchdog_sha,
            expected_source_sha=source_sha,
            expected_phi=phi,
        )
    raise ValueError(f"unsupported method: {method}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        left = _load_method_case(
            args.left_method,
            args.left_watchdog,
            args.left_watchdog_sha256,
            args.expected_source_sha,
            args.left_phi,
        )
        right = _load_method_case(
            args.right_method,
            args.right_watchdog,
            args.right_watchdog_sha256,
            args.expected_source_sha,
            args.right_phi,
        )
        if args.comparison == "m120_m160":
            result = compare_m120_m160(left, right)
        elif args.comparison == "hybrid_full3d":
            result = compare_hybrid_full3d(left, right)
        elif args.comparison == "iterative_direct":
            result = compare_iterative_direct(left, right)
        elif args.comparison == "mpi8_mpi1":
            result = compare_mpi8_mpi1(left, right)
        else:
            result = compare_mirror_power(left, right)
    except (KeyError, TypeError, ValueError, OSError) as error:
        result = {"pass": False, "failures": [f"load:{error}"]}
    output = {"schema": COMPARATOR_SCHEMA, **result}
    rendered = json.dumps(output, indent=2, sort_keys=True)
    if args.output is None:
        print(rendered)
    else:
        if args.output.exists():
            raise SystemExit("comparator output already exists")
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if output["pass"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
