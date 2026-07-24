"""Audit Task035b DtN-port phase conventions from accepted artifacts.

This module is intentionally independent of the PDE stack.  It reads
SHA-bound compact records and their raw diffraction-order JSON files, then
recomputes only relationships that are observable in those artifacts.  It
does not solve a PDE, import DOLFINx/PETSc, or claim that an internally
consistent convention is independently physically correct.
"""

from __future__ import annotations

from copy import deepcopy
import cmath
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "task035b.dtn-port-phase-authority.v1"
GEOMETRY = "Task034 fixed rectangular block grating"
EXPECTED_AMPLITUDE_CONVENTION = (
    "auxiliary unknown a_j is the total-field port projection. "
    "top outgoing amplitude = a_j - incident_projection_j; "
    "bottom outgoing amplitude = a_j. Power uses boundary-plane "
    "outgoing amplitude after applying boundary_phase."
)
EXPECTED_MODAL_REFERENCE = (
    "top=physical_z_max; bottom=physical_z_min; "
    "bottom lossy power uses boundary-plane phase attenuation"
)
EXPECTED_POWER_SOURCE = "dtn_port_modal_amplitudes"
EXPECTED_SIGNIFICANT_CHANNELS = tuple(
    (side, order_m, 0, "s")
    for side in ("bottom", "top")
    for order_m in (-7, -5, -4, -2, -1, 0)
)
SIGNIFICANT_POWER_FLOOR = 1.0e-8
ABS_TOLERANCE = 1.0e-12


class AuthorityValidationError(ValueError):
    """Raised when a source hash or immutable artifact identity is invalid."""


def _global_source(
    *,
    sample_id: str,
    degree: int,
    h_nm: float,
    record_path: str,
    record_sha256: str,
    source_sha: str,
    raw_relative_to_run_directory: str,
    raw_sha256: str,
    mesh_cells: list[int],
    mesh_sha256: str,
    cell_tag_sha256: str,
    facet_tag_sha256: str,
) -> dict[str, Any]:
    role = "coarse" if degree == 5 else "enriched"
    return {
        "sample_id": sample_id,
        "degree": degree,
        "h_nm": h_nm,
        "record_path": record_path,
        "record_sha256": record_sha256,
        "raw_relative_to_run_directory": raw_relative_to_run_directory,
        "raw_sha256": raw_sha256,
        "raw_order_count": 80,
        "record_role": role,
        "record_expectations": {
            "status": "actual_global_r5_pass",
            "qualification.pass": True,
            "source.commit_sha": source_sha,
            "source.tracked_source_dirty": False,
            "source.stable_and_clean_after": True,
            "target_identity.geometry": GEOMETRY,
            "target_identity.mesh_backend": "boundary-fitted conforming hexahedron",
            "common_mesh_identity.mesh_cell_type": "hexahedron",
            "common_mesh_identity.mesh_cells_resolved": mesh_cells,
            "common_mesh_identity.partition_independent_mesh_sha256": mesh_sha256,
            "common_mesh_identity.cell_tag_sha256": cell_tag_sha256,
            "common_mesh_identity.facet_tag_sha256": facet_tag_sha256,
            f"{role}.degree": degree,
            f"{role}.h_nm": h_nm,
            f"{role}.mpi_size": 8,
            f"{role}.official_result": True,
        },
    }


_H15_RECORD = (
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
    "records/global_hexa_p5_p6_h15_assembly_time_condensed_independent_mpi8.json"
)
_H15_RECORD_SHA256 = "59859ef7b49ac6c40e2e3d803a366c71742a29411f7d9591384c62dc8fa923f9"
_H15_SOURCE_SHA = "5d75c5ed8ae0dd4382eccf0c47e22fce01391184"
_H15_MESH_SHA256 = "f6ed05e9f88f05cb88631698c2fe6692f054bfd41fd615272efda436362e3cc0"
_H15_CELL_TAG_SHA256 = "a326daa4edcb470ab6159b30be56a8c69619d0a61290b8f96aadce098a187d63"
_H15_FACET_TAG_SHA256 = "e898956f4c0eb1b463e0bca42033b832b5a9b350c44da659f1578c13aa2a9797"

DEFAULT_AUTHORITY_MANIFEST: dict[str, Any] = {
    "schema_version": "task035b.dtn-port-phase-authority-manifest.v1",
    "geometry": GEOMETRY,
    "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
    "expected_significant_channels": [
        {
            "side": side,
            "m": order_m,
            "n": order_n,
            "polarization": polarization,
        }
        for side, order_m, order_n, polarization in EXPECTED_SIGNIFICANT_CHANNELS
    ],
    "sources": [
        _global_source(
            sample_id="p6_h10",
            degree=6,
            h_nm=10.0,
            record_path=(
                "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
                "records/global_hexa_p5_p6_h10_assembly_time_condensed_"
                "independent_mpi8.json"
            ),
            record_sha256=(
                "9f7f44efb52b44c587ef59a57524849e08da81a6fcd5d90ec18e7b69e4f33ded"
            ),
            source_sha="e9d35bb77636302e18112bf1ab81fdc40f64efba",
            raw_relative_to_run_directory=(
                "enriched_p6/dtn_port_diffraction_orders_3d.json"
            ),
            raw_sha256=(
                "d2a1b882bd76f947056cd930261c6c8b6f338c6e37aeff39a5e649f96288edff"
            ),
            mesh_cells=[6, 3, 14],
            mesh_sha256=(
                "f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857"
            ),
            cell_tag_sha256=(
                "42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131"
            ),
            facet_tag_sha256=(
                "0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd"
            ),
        ),
        _global_source(
            sample_id="p5_h15",
            degree=5,
            h_nm=15.0,
            record_path=_H15_RECORD,
            record_sha256=_H15_RECORD_SHA256,
            source_sha=_H15_SOURCE_SHA,
            raw_relative_to_run_directory=(
                "coarse_p5/dtn_port_diffraction_orders_3d.json"
            ),
            raw_sha256=(
                "0bb1f7835132eedef825698f4e12d49aee979574a09f3da0b239363331a3daa3"
            ),
            mesh_cells=[6, 2, 10],
            mesh_sha256=_H15_MESH_SHA256,
            cell_tag_sha256=_H15_CELL_TAG_SHA256,
            facet_tag_sha256=_H15_FACET_TAG_SHA256,
        ),
        _global_source(
            sample_id="p6_h15",
            degree=6,
            h_nm=15.0,
            record_path=_H15_RECORD,
            record_sha256=_H15_RECORD_SHA256,
            source_sha=_H15_SOURCE_SHA,
            raw_relative_to_run_directory=(
                "enriched_p6/dtn_port_diffraction_orders_3d.json"
            ),
            raw_sha256=(
                "e803ae7454b5e5088de76795f23d961f806c73274aac28b733bceb6e6a29c6c3"
            ),
            mesh_cells=[6, 2, 10],
            mesh_sha256=_H15_MESH_SHA256,
            cell_tag_sha256=_H15_CELL_TAG_SHA256,
            facet_tag_sha256=_H15_FACET_TAG_SHA256,
        ),
        {
            "sample_id": "fixed_p5trace_p6interior_h15",
            "degree": "p5_trace_p6_interior",
            "h_nm": 15.0,
            "record_path": (
                "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
                "records/fixed_p5trace_p6interior_h15_tensor_dedup_"
                "preallocation_mpi8.json"
            ),
            "record_sha256": (
                "1ffde81be08c24232e62c1d2dfbf1b7ad2dcb3623444ea40af68b5c6585758e3"
            ),
            "raw_relative_to_run_directory": (
                "candidate/dtn_port_diffraction_orders_3d.json"
            ),
            "raw_sha256": (
                "e585cdce2dfc10e10eb52198a56009d2ff5725fbb09d869706d88d9eb9e1d06e"
            ),
            "raw_order_count": 80,
            "record_role": "candidate",
            "record_expectations": {
                "status": "actual_fixed_trace_controlled_negative",
                "qualification.pass": True,
                "source.commit_sha": "7f61d554b0441d7b224c096aba402d3b3ac2baa6",
                "source.tracked_source_dirty": False,
                "source.stable_and_clean_after": True,
                "target_identity.geometry": GEOMETRY,
                "target_identity.h_nm": 15.0,
                "target_identity.trace_degree": 5,
                "target_identity.interior_degree": 6,
                "candidate.degree": 6,
                "candidate.h_nm": 15.0,
                "candidate.mpi_size": 8,
                "candidate.official_result": True,
                "same_mesh_global_p6_baseline.pass": True,
                (
                    "same_mesh_global_p6_baseline.candidate."
                    "partition_independent_mesh_sha256"
                ): _H15_MESH_SHA256,
                "same_mesh_global_p6_baseline.candidate.cell_tag_sha256": (
                    _H15_CELL_TAG_SHA256
                ),
                "same_mesh_global_p6_baseline.candidate.facet_tag_sha256": (
                    _H15_FACET_TAG_SHA256
                ),
            },
        },
    ],
}


def default_authority_manifest() -> dict[str, Any]:
    """Return a caller-owned copy of the accepted authority manifest."""

    return deepcopy(DEFAULT_AUTHORITY_MANIFEST)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_repo_path(repo_root: Path, relative: str) -> Path:
    root = repo_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise AuthorityValidationError(
            f"authority path escapes repository: {relative}"
        ) from error
    if not path.is_file():
        raise AuthorityValidationError(f"authority file is missing: {relative}")
    return path


def _lookup(payload: Mapping[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for component in dotted_path.split("."):
        if not isinstance(value, Mapping) or component not in value:
            raise AuthorityValidationError(
                f"record identity field is missing: {dotted_path}"
            )
        value = value[component]
    return value


def _validate_expected_fields(
    payload: Mapping[str, Any],
    expectations: Mapping[str, Any],
    *,
    authority_name: str,
) -> None:
    for dotted_path, expected in expectations.items():
        actual = _lookup(payload, dotted_path)
        if actual != expected:
            raise AuthorityValidationError(
                f"{authority_name} identity mismatch for {dotted_path}: "
                f"expected {expected!r}, got {actual!r}"
            )


def _finite_float(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise AuthorityValidationError(f"{field} is not numeric") from error
    if not math.isfinite(result):
        raise AuthorityValidationError(f"{field} is not finite")
    return result


def _complex_pair(value: Any, *, field: str) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise AuthorityValidationError(
            f"{field} must be a [real, imag] pair"
        )
    return complex(
        _finite_float(value[0], field=f"{field}.real"),
        _finite_float(value[1], field=f"{field}.imag"),
    )


def _channel_key(order: Mapping[str, Any]) -> tuple[str, int, int, str]:
    try:
        return (
            str(order["side"]),
            int(order["m"]),
            int(order["n"]),
            str(order["polarization"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AuthorityValidationError(
            "raw order has an incomplete channel identity"
        ) from error


def _channel_label(key: tuple[str, int, int, str]) -> str:
    side, order_m, order_n, polarization = key
    observable = "T" if side == "bottom" else "R"
    return f"{observable}({order_m},{order_n})_{polarization}"


def _close(left: float | complex, right: float | complex) -> bool:
    return abs(left - right) <= ABS_TOLERANCE * max(
        1.0,
        abs(left),
        abs(right),
    )


def _identity_value_close(left: Any, right: Any) -> bool:
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _identity_value_close(a, b)
            for a, b in zip(left, right, strict=True)
        )
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return _close(float(left), float(right))
    return left == right


def _kinematic_identity(order: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "auxiliary_index",
        "side",
        "direction",
        "medium",
        "m",
        "n",
        "order_m",
        "order_n",
        "polarization",
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
        "incident_projection",
        "power_source",
    )
    identity: dict[str, Any] = {}
    for field in fields:
        if field not in order:
            raise AuthorityValidationError(
                f"raw order identity field is missing: {field}"
            )
        identity[field] = order[field]
    return identity


def _record_metric_identity(
    record: Mapping[str, Any],
    raw_metrics: Mapping[str, Any],
    role: str,
) -> None:
    for field in ("R00_total", "R_total", "T_total"):
        compact_value = _finite_float(
            _lookup(record, f"{role}.{field}"),
            field=f"{role}.{field}",
        )
        raw_value = _finite_float(
            _lookup(raw_metrics, field),
            field=f"metrics.{field}",
        )
        if not _close(compact_value, raw_value):
            raise AuthorityValidationError(
                f"raw/compact identity mismatch for {role}.{field}: "
                f"{compact_value!r} != {raw_value!r}"
            )


def _load_source(
    repo_root: Path,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    sample_id = str(source.get("sample_id", "unnamed"))
    record_relative = str(source["record_path"])
    record_path = _resolve_repo_path(repo_root, record_relative)
    record_sha = _sha256(record_path)
    expected_record_sha = str(source["record_sha256"])
    if record_sha != expected_record_sha:
        raise AuthorityValidationError(
            f"{sample_id} compact record SHA mismatch: expected "
            f"{expected_record_sha}, got {record_sha}"
        )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(record, Mapping):
        raise AuthorityValidationError(
            f"{sample_id} compact record is not a JSON object"
        )
    _validate_expected_fields(
        record,
        source["record_expectations"],
        authority_name=sample_id,
    )

    run_directory = _lookup(record, "raw_evidence.run_directory")
    if not isinstance(run_directory, str):
        raise AuthorityValidationError(
            f"{sample_id} raw run directory is not a string"
        )
    raw_relative = str(
        Path(run_directory) / str(source["raw_relative_to_run_directory"])
    )
    raw_path = _resolve_repo_path(repo_root, raw_relative)
    raw_sha = _sha256(raw_path)
    expected_raw_sha = str(source["raw_sha256"])
    if raw_sha != expected_raw_sha:
        raise AuthorityValidationError(
            f"{sample_id} raw order SHA mismatch: expected "
            f"{expected_raw_sha}, got {raw_sha}"
        )
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if (
        not isinstance(raw, Mapping)
        or not isinstance(raw.get("metrics"), Mapping)
        or not isinstance(raw.get("orders"), list)
    ):
        raise AuthorityValidationError(
            f"{sample_id} raw order artifact has an invalid schema"
        )
    orders = raw["orders"]
    expected_count = int(source["raw_order_count"])
    if len(orders) != expected_count:
        raise AuthorityValidationError(
            f"{sample_id} raw order count mismatch: expected "
            f"{expected_count}, got {len(orders)}"
        )
    role = str(source["record_role"])
    _record_metric_identity(record, raw["metrics"], role)
    keys = [_channel_key(order) for order in orders]
    if len(set(keys)) != len(keys):
        raise AuthorityValidationError(
            f"{sample_id} raw artifact has duplicate channel identities"
        )
    return {
        "sample_id": sample_id,
        "degree": source["degree"],
        "h_nm": float(source["h_nm"]),
        "record_path": record_relative,
        "record_sha256": record_sha,
        "raw_path": raw_relative,
        "raw_sha256": raw_sha,
        "source_sha": _lookup(record, "source.commit_sha"),
        "record_status": record["status"],
        "raw": raw,
    }


def _check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    *,
    maximum_error: float | None = None,
    detail: Any = None,
) -> None:
    row: dict[str, Any] = {
        "name": name,
        "status": "proved_from_artifact" if passed else "artifact_mismatch",
        "pass": bool(passed),
    }
    if maximum_error is not None:
        row["maximum_error"] = float(maximum_error)
        row["tolerance"] = ABS_TOLERANCE
    if detail is not None:
        row["detail"] = detail
    checks.append(row)


def _audit_source(loaded: Mapping[str, Any]) -> dict[str, Any]:
    raw = loaded["raw"]
    metrics = raw["metrics"]
    orders = raw["orders"]
    checks: list[dict[str, Any]] = []

    amplitude_convention = metrics.get("dtn_port_modal_amplitude_convention")
    modal_reference = metrics.get("dtn_port_modal_reference")
    power_source = metrics.get("power_source")
    _check(
        checks,
        "declared_complex_amplitude_convention",
        amplitude_convention == EXPECTED_AMPLITUDE_CONVENTION,
        detail=amplitude_convention,
    )
    _check(
        checks,
        "declared_reference_planes_and_lossy_attenuation",
        (
            modal_reference == EXPECTED_MODAL_REFERENCE
            and _close(
                _finite_float(
                    metrics.get("dtn_port_top_reference_z"),
                    field="dtn_port_top_reference_z",
                ),
                130.0,
            )
            and _close(
                _finite_float(
                    metrics.get("dtn_port_bottom_reference_z"),
                    field="dtn_port_bottom_reference_z",
                ),
                -10.0,
            )
        ),
        detail={
            "reference": modal_reference,
            "top_z": metrics.get("dtn_port_top_reference_z"),
            "bottom_z": metrics.get("dtn_port_bottom_reference_z"),
        },
    )
    _check(
        checks,
        "declared_modal_power_source",
        (
            power_source == EXPECTED_POWER_SOURCE
            and metrics.get("diffraction_total_power_source")
            == EXPECTED_POWER_SOURCE
            and all(
                order.get("power_source") == EXPECTED_POWER_SOURCE
                for order in orders
            )
        ),
        detail=power_source,
    )
    _check(
        checks,
        "declared_dtn_policy_and_assembly",
        (
            metrics.get("stage4_dtn_order_policy") == "auto_propagating"
            and metrics.get("stage4_dtn_assembly") == "auxiliary"
        ),
        detail={
            "stage4_dtn_order_policy": metrics.get(
                "stage4_dtn_order_policy"
            ),
            "stage4_dtn_assembly": metrics.get("stage4_dtn_assembly"),
            "stage4_dtn_evanescent_buffer": metrics.get(
                "stage4_dtn_evanescent_buffer"
            ),
        },
    )

    sign_errors: list[float] = []
    phase_errors: list[float] = []
    outgoing_errors: list[float] = []
    boundary_errors: list[float] = []
    power_ratio_errors: list[float] = []
    side_mapping_ok = True
    incident_support: list[tuple[str, int, int, str]] = []
    top_phase_modulus_errors: list[float] = []
    bottom_attenuation_ok = True
    incident_power = _finite_float(
        metrics.get("incident_power_code_units"),
        field="incident_power_code_units",
    )
    if incident_power <= 0.0:
        raise AuthorityValidationError(
            f"{loaded['sample_id']} incident power is not positive"
        )

    for order in orders:
        side, order_m, order_n, polarization = _channel_key(order)
        if order.get("order_m") != order_m or order.get("order_n") != order_n:
            side_mapping_ok = False
        expected_direction = (
            "outgoing_up" if side == "top" else "outgoing_down"
        )
        expected_vertical_sign = 1 if side == "top" else -1
        expected_medium = "air" if side == "top" else "substrate"
        if side not in ("top", "bottom"):
            side_mapping_ok = False
        if (
            order.get("direction") != expected_direction
            or order.get("vertical_sign") != expected_vertical_sign
            or order.get("medium") != expected_medium
        ):
            side_mapping_ok = False

        beta = _complex_pair(order.get("beta"), field="beta")
        kz = _complex_pair(order.get("kz"), field="kz")
        sign_errors.append(abs(kz - expected_vertical_sign * beta))
        reference_z = _finite_float(
            metrics.get(
                "dtn_port_top_reference_z"
                if side == "top"
                else "dtn_port_bottom_reference_z"
            ),
            field=f"{side}_reference_z",
        )
        phase = _complex_pair(
            order.get("boundary_phase"),
            field="boundary_phase",
        )
        phase_errors.append(abs(phase - cmath.exp(1j * kz * reference_z)))
        if side == "top":
            top_phase_modulus_errors.append(abs(abs(phase) - 1.0))
        elif abs(phase) > 1.0 + ABS_TOLERANCE:
            bottom_attenuation_ok = False

        auxiliary = _complex_pair(
            order.get("auxiliary_amplitude_total_projection"),
            field="auxiliary_amplitude_total_projection",
        )
        incident = _complex_pair(
            order.get("incident_projection"),
            field="incident_projection",
        )
        outgoing = _complex_pair(
            order.get("outgoing_amplitude"),
            field="outgoing_amplitude",
        )
        expected_outgoing = (
            auxiliary - incident if side == "top" else auxiliary
        )
        outgoing_errors.append(abs(outgoing - expected_outgoing))
        if abs(incident) > ABS_TOLERANCE:
            incident_support.append(
                (side, order_m, order_n, polarization)
            )
        boundary_amplitude = _complex_pair(
            order.get("outgoing_amplitude_at_boundary"),
            field="outgoing_amplitude_at_boundary",
        )
        boundary_errors.append(
            abs(boundary_amplitude - outgoing * phase)
        )

        modal_power = _finite_float(
            order.get("modal_power_code_units"),
            field="modal_power_code_units",
        )
        power_ratio = _finite_float(
            order.get("power_ratio"),
            field="power_ratio",
        )
        power_ratio_errors.append(
            abs(power_ratio - modal_power / incident_power)
        )
        power_carrying = bool(order.get("power_carrying"))
        expected_r = (
            power_ratio if side == "top" and power_carrying else 0.0
        )
        expected_t = (
            power_ratio if side == "bottom" and power_carrying else 0.0
        )
        if not _close(
            _finite_float(order.get("R"), field="R"),
            expected_r,
        ) or not _close(
            _finite_float(order.get("T"), field="T"),
            expected_t,
        ):
            side_mapping_ok = False

    max_sign_error = max(sign_errors, default=math.inf)
    max_phase_error = max(phase_errors, default=math.inf)
    max_outgoing_error = max(outgoing_errors, default=math.inf)
    max_boundary_error = max(boundary_errors, default=math.inf)
    max_power_ratio_error = max(power_ratio_errors, default=math.inf)
    max_top_modulus_error = max(top_phase_modulus_errors, default=math.inf)
    _check(
        checks,
        "side_direction_vertical_sign_and_power_side",
        side_mapping_ok and max_sign_error <= ABS_TOLERANCE,
        maximum_error=max_sign_error,
    )
    _check(
        checks,
        "reference_plane_phase_exp_i_kz_z",
        max_phase_error <= ABS_TOLERANCE,
        maximum_error=max_phase_error,
    )
    _check(
        checks,
        "top_phase_unit_modulus_bottom_lossy_attenuation",
        (
            max_top_modulus_error <= ABS_TOLERANCE
            and bottom_attenuation_ok
        ),
        maximum_error=max_top_modulus_error,
    )
    _check(
        checks,
        "incoming_subtraction_top_only",
        (
            max_outgoing_error <= ABS_TOLERANCE
            and set(incident_support) == {("top", 0, 0, "s")}
        ),
        maximum_error=max_outgoing_error,
        detail={
            "nonzero_incident_projection_channels": [
                _channel_label(key) for key in incident_support
            ]
        },
    )
    _check(
        checks,
        "outgoing_boundary_amplitude_phase_application",
        max_boundary_error <= ABS_TOLERANCE,
        maximum_error=max_boundary_error,
    )
    _check(
        checks,
        "modal_power_ratio_normalization",
        max_power_ratio_error <= ABS_TOLERANCE,
        maximum_error=max_power_ratio_error,
        detail={"incident_power_code_units": incident_power},
    )

    r_sum = sum(_finite_float(order["R"], field="R") for order in orders)
    t_sum = sum(_finite_float(order["T"], field="T") for order in orders)
    r00_sum = sum(
        _finite_float(order["R"], field="R")
        for order in orders
        if int(order["m"]) == 0 and int(order["n"]) == 0
    )
    a_balance = 1.0 - r_sum - t_sum
    total_errors = {
        "R_total": abs(
            r_sum - _finite_float(metrics.get("R_total"), field="R_total")
        ),
        "R_total_dtn_port_modal": abs(
            r_sum
            - _finite_float(
                metrics.get("R_total_dtn_port_modal"),
                field="R_total_dtn_port_modal",
            )
        ),
        "T_total": abs(
            t_sum - _finite_float(metrics.get("T_total"), field="T_total")
        ),
        "T_total_dtn_port_modal": abs(
            t_sum
            - _finite_float(
                metrics.get("T_total_dtn_port_modal"),
                field="T_total_dtn_port_modal",
            )
        ),
        "R00_total": abs(
            r00_sum
            - _finite_float(metrics.get("R00_total"), field="R00_total")
        ),
        "A_balance": abs(
            a_balance
            - _finite_float(metrics.get("A_balance"), field="A_balance")
        ),
    }
    _check(
        checks,
        "channel_sums_reproduce_R_R00_T_A_balance",
        max(total_errors.values()) <= ABS_TOLERANCE,
        maximum_error=max(total_errors.values()),
        detail=total_errors,
    )

    significant_rows = {
        _channel_key(order): order
        for order in orders
        if _channel_key(order) in EXPECTED_SIGNIFICANT_CHANNELS
    }
    floor_selected = {
        _channel_key(order)
        for order in orders
        if _finite_float(order.get("power_ratio"), field="power_ratio")
        >= SIGNIFICANT_POWER_FLOOR
    }
    _check(
        checks,
        "power_floor_selects_exactly_12_significant_channels",
        floor_selected == set(EXPECTED_SIGNIFICANT_CHANNELS),
        detail={
            "power_floor": SIGNIFICANT_POWER_FLOOR,
            "selected": [
                _channel_label(key) for key in sorted(floor_selected)
            ],
        },
    )
    _check(
        checks,
        "all_12_significant_channels_present",
        set(significant_rows) == set(EXPECTED_SIGNIFICANT_CHANNELS),
        detail=[
            _channel_label(key)
            for key in sorted(significant_rows)
        ],
    )
    significant_channel_checks = [
        {
            "channel": _channel_label(key),
            "side": key[0],
            "m": key[1],
            "n": key[2],
            "polarization": key[3],
            "direction": significant_rows[key]["direction"],
            "vertical_sign": significant_rows[key]["vertical_sign"],
            "kz": significant_rows[key]["kz"],
            "boundary_phase": significant_rows[key]["boundary_phase"],
            "incident_projection": significant_rows[key][
                "incident_projection"
            ],
            "outgoing_amplitude_at_boundary": significant_rows[key][
                "outgoing_amplitude_at_boundary"
            ],
            "power_ratio": significant_rows[key]["power_ratio"],
            "status": "proved_from_artifact",
        }
        for key in EXPECTED_SIGNIFICANT_CHANNELS
    ]
    return {
        "sample_id": loaded["sample_id"],
        "pass": all(check["pass"] for check in checks),
        "checks": checks,
        "significant_channel_checks": significant_channel_checks,
        "reported_dtn_evanescent_buffer": metrics.get(
            "stage4_dtn_evanescent_buffer"
        ),
        "reported_surface_quadrature_degree": metrics.get(
            "stage4_dtn_surface_quadrature_degree"
        ),
    }


def _cross_artifact_audit(
    loaded_sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reference = loaded_sources[0]
    reference_metrics = reference["raw"]["metrics"]
    reference_orders = {
        _channel_key(order): order for order in reference["raw"]["orders"]
    }
    checks: list[dict[str, Any]] = []
    channel_sets_match = True
    identities_match = True
    conventions_match = True
    for source in loaded_sources[1:]:
        metrics = source["raw"]["metrics"]
        orders = {
            _channel_key(order): order for order in source["raw"]["orders"]
        }
        if set(orders) != set(reference_orders):
            channel_sets_match = False
            continue
        for key in reference_orders:
            left = _kinematic_identity(reference_orders[key])
            right = _kinematic_identity(orders[key])
            if not _identity_value_close(left, right):
                identities_match = False
        for field in (
            "dtn_port_modal_amplitude_convention",
            "dtn_port_modal_reference",
            "dtn_port_top_reference_z",
            "dtn_port_bottom_reference_z",
            "incident_power_code_units",
            "power_source",
            "diffraction_total_power_source",
            "stage4_dtn_order_policy",
            "stage4_dtn_assembly",
            "dtn_port_mode_count",
            "dtn_port_top_mode_count",
            "dtn_port_bottom_mode_count",
        ):
            if not _identity_value_close(
                reference_metrics.get(field),
                metrics.get(field),
            ):
                conventions_match = False
    _check(
        checks,
        "same_80_channel_set",
        channel_sets_match,
        detail={"reference_sample": reference["sample_id"]},
    )
    _check(
        checks,
        "same_channel_kinematics_phase_and_incident_projection",
        channel_sets_match and identities_match,
        detail={
            "identity_fields": list(
                _kinematic_identity(
                    next(iter(reference_orders.values()))
                )
            )
        },
    )
    _check(
        checks,
        "same_declared_modal_convention_and_reference",
        conventions_match,
    )
    return {
        "reference_sample": reference["sample_id"],
        "pass": all(check["pass"] for check in checks),
        "checks": checks,
    }


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    if (
        manifest.get("schema_version")
        != "task035b.dtn-port-phase-authority-manifest.v1"
    ):
        raise AuthorityValidationError(
            "unexpected phase-authority manifest schema"
        )
    if manifest.get("geometry") != GEOMETRY:
        raise AuthorityValidationError(
            "phase-authority manifest geometry mismatch"
        )
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != 4:
        raise AuthorityValidationError(
            "phase-authority manifest must bind exactly four raw samples"
        )
    sample_ids = [str(source.get("sample_id")) for source in sources]
    if sample_ids != [
        "p6_h10",
        "p5_h15",
        "p6_h15",
        "fixed_p5trace_p6interior_h15",
    ]:
        raise AuthorityValidationError(
            "phase-authority manifest sample identity mismatch"
        )
    expected_channels = manifest.get("expected_significant_channels")
    if not isinstance(expected_channels, list):
        raise AuthorityValidationError(
            "phase-authority manifest lacks significant channels"
        )
    keys = {
        (
            str(row.get("side")),
            int(row.get("m")),
            int(row.get("n")),
            str(row.get("polarization")),
        )
        for row in expected_channels
    }
    if keys != set(EXPECTED_SIGNIFICANT_CHANNELS):
        raise AuthorityValidationError(
            "phase-authority manifest significant-channel identity mismatch"
        )


def build_dtn_port_phase_authority(
    repo_root: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, artifact-only phase-convention audit record."""

    selected_manifest = (
        default_authority_manifest()
        if manifest is None
        else deepcopy(dict(manifest))
    )
    _validate_manifest(selected_manifest)
    loaded_sources = [
        _load_source(repo_root, source)
        for source in selected_manifest["sources"]
    ]
    source_audits = [_audit_source(source) for source in loaded_sources]
    cross_artifact = _cross_artifact_audit(loaded_sources)
    passed = (
        all(audit["pass"] for audit in source_audits)
        and cross_artifact["pass"]
    )
    observed_buffer_values = {
        audit["reported_dtn_evanescent_buffer"]
        for audit in source_audits
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": "task035b_dtn_port_phase_authority",
        "status": (
            "artifact_convention_consistency_pass"
            if passed
            else "artifact_convention_inconsistency"
        ),
        "pass": passed,
        "scope": {
            "geometry": GEOMETRY,
            "method": "pure_artifact_recomputation",
            "heavy_pde_run": False,
            "ordinary_default_changed": False,
            "scientific_gate_relaxed": False,
            "significant_channel_count": 12,
            "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
        },
        "authorities": [
            {
                key: source[key]
                for key in (
                    "sample_id",
                    "degree",
                    "h_nm",
                    "record_path",
                    "record_sha256",
                    "raw_path",
                    "raw_sha256",
                    "source_sha",
                    "record_status",
                )
            }
            for source in loaded_sources
        ],
        "source_audits": source_audits,
        "cross_artifact_audit": cross_artifact,
        "root_cause_decision": {
            "classification": (
                "no_artifact_level_convention_mismatch_found"
                if passed
                else "artifact_level_convention_mismatch_found"
            ),
            "artifact_level_convention_change_explains_h15_channel_error": (
                False if passed else None
            ),
            "common_mode_physical_convention_error_excluded": False,
            "conclusion": (
                "The four accepted artifacts use the same recorded channel "
                "kinematics, reference-plane phase, incoming subtraction, "
                "power normalization, and boundary-amplitude convention. "
                "Therefore an artifact-level convention change does not "
                "explain their h15 channel differences. A common-mode "
                "implementation or physical-convention error is not excluded "
                "without an independent field/projection authority."
                if passed
                else "At least one artifact-level convention relationship "
                "is inconsistent; the mismatch must be resolved before this "
                "lane can support a root-cause conclusion."
            ),
        },
        "not_observable": [
            {
                "item": "physical_correctness_of_top_bottom_outgoing_sign",
                "status": "not_observable",
                "reason": (
                    "Artifacts prove internal side/direction/kz consistency "
                    "but provide no independent outward-flux or analytic-field "
                    "authority."
                ),
            },
            {
                "item": "absolute_modal_basis_phase_normalization",
                "status": "not_observable",
                "reason": (
                    "The modal basis vectors and raw projection integrals are "
                    "not stored; only their resulting amplitudes are stored."
                ),
            },
            {
                "item": "modal_power_prefactor_from_field_basis",
                "status": "not_observable",
                "reason": (
                    "Power ratios and channel sums are recomputable, but the "
                    "electric/magnetic modal basis needed to independently "
                    "recompute modal_power_code_units is absent."
                ),
            },
            {
                "item": "reference_plane_phase_against_independent_field_probe",
                "status": "not_observable",
                "reason": (
                    "The recorded boundary phase is algebraically consistent "
                    "with exp(i*kz*z), but no independent complex field "
                    "projection at a second plane is bound to these records."
                ),
            },
            {
                "item": "dtn_evanescent_buffer_convergence",
                "status": "not_observable",
                "reason": (
                    "All four artifacts report auto_propagating with 80 "
                    "power-carrying modes and do not bind a buffer sweep. "
                    "The recorded buffer values are "
                    f"{sorted(observed_buffer_values, key=str)!r}."
                ),
            },
            {
                "item": "surface_projection_quadrature_convergence",
                "status": "not_observable",
                "reason": (
                    "A quadrature degree is recorded, but no independent "
                    "quadrature sweep or raw integral samples are bound."
                ),
            },
            {
                "item": "incident_source_assembly_sign_before_solve",
                "status": "not_observable",
                "reason": (
                    "Artifacts expose post-solve incident subtraction, not "
                    "the independently assembled matrix/RHS source terms."
                ),
            },
        ],
    }
