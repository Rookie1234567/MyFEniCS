"""Strict Task38 input validation and pure resolved-spec construction."""

from __future__ import annotations

from difflib import get_close_matches
from copy import deepcopy
from hashlib import sha256
from math import isclose, isfinite
from pathlib import Path
import re
from typing import Any, Mapping
import tomllib

import numpy as np

from .input_loader import InputError, LoadedInput
from .resolved_config import canonical_json_bytes
from .run_specification import RunSpecification
from .input_schema import (
    FIELD_SPECS_BY_KEY,
    IDENTITY_KEYS,
    METHOD_KINDS,
    PUBLIC_FIELD_SPECS,
    SECTION_NAMES,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_IDENTITY_SET = set(IDENTITY_KEYS)
_SECTION_SET = set(SECTION_NAMES)


def _error(path: str, message: str) -> InputError:
    return InputError(f"{path}: {message}")


def _suggest(value: str, choices: tuple[str, ...] | list[str] | set[str]) -> str:
    match = get_close_matches(value, list(choices), n=1, cutoff=0.45)
    return f"; did you mean {match[0]!r}?" if match else ""


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(path, "expected a finite number")
    result = float(value)
    if not isfinite(result):
        raise _error(path, "NaN and infinity are not allowed")
    return result


def _parse_default(spec: Any) -> Any:
    if spec.default is None:
        return None
    if spec.value_type in {"string", "path", "enum"}:
        return spec.default
    try:
        return tomllib.loads(f"value = {spec.default}\n")["value"]
    except (tomllib.TOMLDecodeError, TypeError) as exc:
        raise InputError(f"schema default for {spec.key} is invalid: {exc}") from exc


def _parse_value(spec: Any, value: Any) -> Any:
    path = spec.key
    value_type = spec.value_type
    if value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _error(path, "expected an integer; boolean is not an integer")
        result: Any = int(value)
    elif value_type == "float":
        result = _finite_number(value, path)
    elif value_type in {"string", "path"}:
        if not isinstance(value, str):
            raise _error(path, "expected a string")
        if not value:
            raise _error(path, "must not be empty")
        result = value
    elif value_type == "enum":
        if not isinstance(value, str):
            raise _error(path, "expected a string enum")
        result = value
    elif value_type == "boolean":
        if not isinstance(value, bool):
            raise _error(path, "expected a TOML boolean")
        result = value
    elif value_type == "complex_pair":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise _error(path, "expected [real, imag]")
        result = tuple(
            _finite_number(item, f"{path}[{index}]") for index, item in enumerate(value)
        )
    elif value_type == "complex_vector3":
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise _error(path, "expected three [real, imag] pairs")
        result = tuple(
            _parse_complex_pair(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    elif value_type == "float_array":
        if not isinstance(value, (list, tuple)):
            raise _error(path, "expected an array of finite numbers")
        result = tuple(
            _finite_number(item, f"{path}[{index}]") for index, item in enumerate(value)
        )
    else:
        raise InputError(f"schema has unsupported value type {value_type!r} for {path}")

    if spec.allowed:
        candidate = result if value_type == "enum" else str(result)
        if candidate not in spec.allowed:
            choices = ", ".join(spec.allowed)
            suggestion = (
                _suggest(str(result), spec.allowed) if value_type == "enum" else ""
            )
            raise _error(
                path,
                f"value {result!r} is not allowed ({choices}){suggestion}",
            )
    return result


def _parse_complex_pair(value: Any, path: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise _error(path, "expected [real, imag]")
    return tuple(
        _finite_number(item, f"{path}[{index}]") for index, item in enumerate(value)
    )


def _applicable(spec: Any, dimension: int, method: str) -> bool:
    return bool(
        "all" in spec.applicability
        or f"{dimension}d" in spec.applicability
        or method in spec.applicability
    )


def _validate_root(document: Mapping[str, Any]) -> None:
    expected = set(IDENTITY_KEYS) | _SECTION_SET
    for key in document:
        if key not in expected:
            raise _error(
                str(key),
                "unknown top-level key" + _suggest(str(key), sorted(expected)),
            )
    for key in IDENTITY_KEYS:
        if key not in document:
            raise _error(key, "missing required identity key")
    for section in SECTION_NAMES:
        if section not in document:
            raise _error(section, "missing required section")
        if not isinstance(document[section], Mapping):
            raise _error(section, "must be a TOML table")


def _validate_sections(document: Mapping[str, Any]) -> dict[str, Any]:
    _validate_root(document)
    identity: dict[str, Any] = {}
    identity_specs = {
        spec.key: spec for spec in PUBLIC_FIELD_SPECS if "." not in spec.key
    }
    for key in IDENTITY_KEYS:
        identity[key] = _parse_value(identity_specs[key], document[key])
    if identity["schema_version"] != 1:
        raise _error("schema_version", "only schema version 1 is supported")
    for key in ("model_id", "run_id", "comparison_group"):
        if not _SAFE_ID.fullmatch(identity[key]):
            raise _error(key, "must match [A-Za-z0-9_.-]+")

    dimension = identity["dimension"]
    method_table = document["method"]
    if "kind" not in method_table:
        raise _error("method.kind", "missing required field")
    method_spec = FIELD_SPECS_BY_KEY["method.kind"]
    method = _parse_value(method_spec, method_table["kind"])
    if method not in METHOD_KINDS:
        raise _error(
            "method.kind", f"unknown method {method!r}{_suggest(method, METHOD_KINDS)}"
        )

    normalized: dict[str, Any] = dict(identity)
    for section in SECTION_NAMES:
        raw_section = document[section]
        known = {
            spec.key.split(".", 1)[1]
            for spec in PUBLIC_FIELD_SPECS
            if spec.key.startswith(f"{section}.")
        }
        for key in raw_section:
            if key not in known:
                dotted = f"{section}.{key}"
                raise _error(
                    dotted,
                    "unknown field" + _suggest(dotted, sorted(FIELD_SPECS_BY_KEY)),
                )

        values: dict[str, Any] = {}
        for spec in PUBLIC_FIELD_SPECS:
            if not spec.key.startswith(f"{section}."):
                continue
            field = spec.key.split(".", 1)[1]
            active = _applicable(spec, dimension, method)
            supplied = field in raw_section
            if not active:
                if supplied:
                    raise _error(
                        spec.key, "field is not applicable to this dimension/method"
                    )
                continue
            if supplied:
                values[field] = _parse_value(spec, raw_section[field])
            elif spec.required:
                raise _error(spec.key, "missing required field")
            elif spec.default is not None:
                values[field] = _parse_value(spec, _parse_default(spec))
        normalized[section] = values

    _validate_cross_fields(normalized)
    return normalized


def _require(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise _error(path, "missing required conditional field")
    return mapping[key]


def _same_profile_value(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            _same_profile_value(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


_TASK039_DELTA = 0.00603145547
_TASK039_BETA = 0.00435380777
_TASK039_N = (0.99396854453, 0.00435380777)
_TASK039_EPSILON_R = (0.9879545118729887, 0.00865509594462061)
_TASK039_MODE_CANDIDATES = (120, 240, 480, 960)
TASK039_M960_TRACE_GATE_POLICY = "task039_m960_backward_stable_v1"
TASK039_E7_TRACE_FAMILY_SHA256 = (
    "5fd8351050fb4849b87084de9465b218745805ecda7e4a83109bcd7a472aaedd"
)
_TASK039_MODEL_ID_PATTERNS = {
    "full3d_direct": r"task039_5nm_full3d_direct",
    "full3d_iterative": r"task039_5nm_full3d_iterative",
    "hybrid_direct": r"task039_5nm_hybrid_direct_m(120|240|480|960)",
    "hybrid_iterative": r"task039_5nm_hybrid_iterative_m(120|240|480|960)_candidate",
}


def task039_model_id_matches(
    method: str,
    model_id: str,
    requested_modes: Any | None = None,
) -> bool:
    """Match one finite Task39 model identity and, for Hybrid, its M."""

    pattern = _TASK039_MODEL_ID_PATTERNS.get(str(method))
    if pattern is None:
        return False
    match = re.fullmatch(pattern, str(model_id))
    if match is None:
        return False
    if str(method).startswith("hybrid_") and requested_modes is not None:
        return int(match.group(1)) == int(requested_modes)
    return True


def _is_task039_5nm(config: Mapping[str, Any]) -> bool:
    method = config.get("method")
    kind = method.get("kind") if isinstance(method, Mapping) else None
    return task039_model_id_matches(kind, str(config.get("model_id", "")))


def _is_task039_candidate(config: Mapping[str, Any]) -> bool:
    return str(config.get("model_id", "")).startswith("task039_5nm")


def task039_material_provenance(
    config: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the 5 nm metadata derived from the sole public ``n`` input.

    ``delta`` and ``beta`` are provenance metadata, not additional material
    inputs.  The resolved dielectric value is always computed as ``n**2``;
    this helper never changes the sign of the supplied imaginary component.
    """

    if not _is_task039_5nm(config):
        return None
    materials = config.get("materials")
    incidence = config.get("incidence")
    if not isinstance(materials, Mapping) or not isinstance(incidence, Mapping):
        return None
    substrate = materials.get("n_substrate")
    grating = materials.get("n_grating")
    if (
        incidence.get("wavelength_nm") != 5.0
        or not _same_profile_value(substrate, _TASK039_N)
        or not _same_profile_value(grating, _TASK039_N)
    ):
        return None
    n = complex(float(substrate[0]), float(substrate[1]))
    epsilon = n**2
    if not (
        isclose(
            epsilon.real,
            _TASK039_EPSILON_R[0],
            rel_tol=1.0e-13,
            abs_tol=1.0e-15,
        )
        and isclose(
            epsilon.imag,
            _TASK039_EPSILON_R[1],
            rel_tol=1.0e-13,
            abs_tol=1.0e-15,
        )
    ):
        return None
    return {
        "source": "derived_from_materials.n_substrate_and_n_grating",
        "independent_input": "n",
        "delta": _TASK039_DELTA,
        "beta": _TASK039_BETA,
        "n": [float(n.real), float(n.imag)],
        "epsilon_r": [float(epsilon.real), float(epsilon.imag)],
        "wavelength_nm": 5.0,
        "air_label": "air",
        "substrate_label": materials.get("substrate_name"),
        "grating_label": materials.get("grating_name"),
        "imaginary_sign_preserved": True,
    }


def _task039_inventory_from_modes(
    modes: Any,
    *,
    selection: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize keys plus finite channel metadata from one mode enumeration."""

    rows = sorted(
        (
            {
                "side": str(mode.side),
                "m": int(mode.m),
                "n": int(mode.n),
                "polarization": str(mode.polarization),
                "beta": [
                    float(complex(mode.beta).real),
                    float(complex(mode.beta).imag),
                ],
                "propagating": bool(mode.propagating),
                "rayleigh_warning": bool(mode.rayleigh_warning),
            }
            for mode in modes
        ),
        key=lambda item: (
            item["side"],
            item["m"],
            item["n"],
            item["polarization"],
        ),
    )
    if any(not isfinite(float(component)) for row in rows for component in row["beta"]):
        raise ValueError("Task39 dynamic mode inventory contains non-finite beta")
    keys = [
        {
            "side": row["side"],
            "m": row["m"],
            "n": row["n"],
            "polarization": row["polarization"],
        }
        for row in rows
    ]
    per_side: dict[str, int] = {}
    per_side_spatial: dict[str, set[tuple[int, int]]] = {}
    polarization_counts = {"S": 0, "P": 0}
    polarization_per_side: dict[str, dict[str, int]] = {}
    for row in rows:
        side = row["side"]
        per_side[side] = per_side.get(side, 0) + 1
        per_side_spatial.setdefault(side, set()).add((row["m"], row["n"]))
        pol = row["polarization"].upper()
        polarization_per_side.setdefault(side, {"S": 0, "P": 0})
        if pol in polarization_counts:
            polarization_counts[pol] += 1
            polarization_per_side[side][pol] += 1
    payload = {
        "source": "outgoing_port_modes_3d",
        "selection": selection,
        "count": len(keys),
        "keys": keys,
        "modes": rows,
        "counts": {
            "per_side": per_side,
            "unique_spatial_mn": len({(row["m"], row["n"]) for row in rows}),
            "unique_spatial_mn_per_side": {
                side: len(values) for side, values in per_side_spatial.items()
            },
            "polarization": polarization_counts,
            "polarization_per_side": polarization_per_side,
            "propagating": sum(row["propagating"] for row in rows),
            "nonpropagating": sum(not row["propagating"] for row in rows),
            "rayleigh_warning": sum(row["rayleigh_warning"] for row in rows),
        },
        "reporting_bounds_are_not_selection": True,
    }
    if extra:
        payload.update(extra)
    return payload


def _task039_dynamic_external_mode_inventory_from_cfg(cfg: Any) -> dict[str, Any]:
    """Serialize the dynamic DtN mode keys selected from one resolved cfg."""

    from src.common.modes_3d import outgoing_port_modes_3d

    return _task039_inventory_from_modes(
        outgoing_port_modes_3d(cfg),
        selection="dynamic_physical_propagation_inventory",
    )


def task039_dynamic_external_mode_inventory(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the full dynamic external mode-key inventory for a normalized cfg."""

    return _task039_dynamic_external_mode_inventory_from_cfg(
        simulation_config_3d_from_normalized(config)
    )


def task039_air_side_external_mode_inventory(
    cfg: Any,
    *,
    wavelength_nm: float = 0.7,
) -> dict[str, Any]:
    """Enumerate only the air-side 0.7 nm component without material claims."""

    if float(wavelength_nm) != 0.7:
        raise ValueError("Task39 air-side inventory is fixed at 0.7 nm")
    air_cfg = deepcopy(cfg)
    air_cfg.lambda0 = 0.7
    air_cfg.n_air = 1.0 + 0.0j
    air_cfg.n_substrate = None
    air_cfg.n_grating = None
    air_cfg.stage4_dtn_order_policy = "auto_propagating"
    air_cfg.diffraction_order_max_m = None
    air_cfg.diffraction_order_max_n = None
    from src.common.modes_3d import outgoing_port_modes_3d

    modes = outgoing_port_modes_3d(air_cfg)
    return _task039_inventory_from_modes(
        (mode for mode in modes if mode.side == "top"),
        selection="top_air_only_dynamic_physical_propagation_inventory",
        extra={
            "air_n": [1.0, 0.0],
            "wavelength_nm": 0.7,
            "material_status": "0P7NM_MATERIAL_INPUT_INCOMPLETE",
            "substrate_dependent": "pending",
            "full_pde_allowed": False,
            "full_pde_error": "0P7NM_MATERIAL_INPUT_INCOMPLETE",
        },
    )


def task039_07nm_launch_error(config: Mapping[str, Any]) -> str | None:
    """Reject any future 0.7 nm full launch before worker dispatch."""

    if (
        config.get("dimension") == 3
        and re.fullmatch(r"task039_0p7nm(?:[_-].*)?", str(config.get("model_id", "")))
        and isinstance(config.get("incidence"), Mapping)
        and config["incidence"].get("wavelength_nm") == 0.7
    ):
        return "0P7NM_MATERIAL_INPUT_INCOMPLETE"
    return None


def task039_profile_errors(config: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return errors for the finite, explicit Task39 p6/h10 profiles."""

    method = config["method"]
    kind = method["kind"]
    if not task039_model_id_matches(
        kind,
        str(config.get("model_id", "")),
        method.get("requested_modes_per_direction"),
    ):
        errors: list[tuple[str, str]] = [
            (
                "model_id",
                f"Task39 {kind} requires its finite model_id and matching M",
            )
        ]
    else:
        errors = []
    expected: tuple[tuple[str, str, Any], ...] = (
        ("geometry", "geometry_kind", "rectangular_block_grating"),
        ("geometry", "period_x_nm", 50.0),
        ("geometry", "period_y_nm", 25.0),
        ("geometry", "z_min_nm", -10.0),
        ("geometry", "z_max_nm", 130.0),
        ("geometry", "interface_z_nm", 0.0),
        ("geometry", "air_height_nm", 130.0),
        ("geometry", "substrate_thickness_nm", 10.0),
        ("geometry", "grating_width_x_nm", 17.0),
        ("geometry", "grating_width_y_nm", 25.0),
        ("geometry", "grating_height_nm", 120.0),
        ("materials", "n_air", (1.0, 0.0)),
        ("materials", "mu_r", (1.0, 0.0)),
        ("materials", "n_substrate", _TASK039_N),
        ("materials", "n_grating", _TASK039_N),
        ("materials", "substrate_name", "Task39 5nm material"),
        ("materials", "grating_name", "Task39 5nm material"),
        ("incidence", "wavelength_nm", 5.0),
        ("incidence", "grazing_angle_deg", 10.0),
        ("incidence", "azimuth_deg", 0.0),
        ("incidence", "polarization", "s"),
        ("incidence", "electric_amplitude", 1.0),
        ("discretization", "nedelec_degree", 6),
        ("discretization", "visualization_degree", 6),
        ("discretization", "mesh_cell_type", "hexahedron"),
        ("discretization", "mesh_spacing_mode", "boundary_fitted"),
        ("discretization", "assembly_backend", "assembly_time_static_condensed"),
        ("discretization", "floquet_constraint_mode", "auto"),
        ("boundary", "use_floquet_x", True),
        ("boundary", "use_floquet_y", True),
        ("boundary", "vertical_boundary", "dtn_port"),
        ("boundary", "scattering_background", "layered"),
        ("boundary", "dtn_order_policy", "auto_propagating"),
        ("boundary", "dtn_assembly", "auxiliary"),
        ("boundary", "use_pml", False),
        ("boundary", "pml_alpha", 5.0),
        ("execution", "timeout_seconds", 21600),
        ("execution", "require_zero_swap", True),
        ("output", "export_fields", True),
        ("output", "export_diffraction_orders", True),
        ("output", "export_modal_amplitudes", True),
        ("output", "export_reference_planes", True),
        ("output", "reference_plane_z_nm", (10.0, 30.0, 60.0, 90.0, 110.0)),
        ("output", "sample_count_x", 40),
        ("output", "sample_count_y", 20),
        ("output", "diffraction_sample_count_x", 32),
        ("output", "diffraction_sample_count_y", 32),
        ("output", "probe_fraction", 0.75),
        ("output", "diffraction_order_max_m", 2),
        ("output", "diffraction_order_max_n", 2),
        ("output", "unique_output", True),
    )
    for section, key, expected_value in expected:
        actual = config[section].get(key)
        if not _same_profile_value(actual, expected_value):
            errors.append((f"{section}.{key}", f"Task39 requires {expected_value!r}"))
    mesh_target_nm = config["discretization"].get("mesh_target_nm")
    allowed_mesh_targets = (10.0, 7.5, 6.0, 5.0) if kind == "full3d_direct" else (10.0,)
    if not any(
        isinstance(mesh_target_nm, (int, float))
        and isclose(float(mesh_target_nm), target, rel_tol=0.0, abs_tol=1.0e-12)
        for target in allowed_mesh_targets
    ):
        errors.append(
            (
                "discretization.mesh_target_nm",
                f"Task39 {kind} allows only {allowed_mesh_targets!r}",
            )
        )
    grid_direct = kind == "full3d_direct" and any(
        isinstance(mesh_target_nm, (int, float))
        and isclose(float(mesh_target_nm), target, rel_tol=0.0, abs_tol=1.0e-12)
        for target in (7.5, 6.0, 5.0)
    )
    m480_mpi1_solver_only = (
        kind == "hybrid_iterative"
        and config["execution"].get("mpi_size") == 1
        and method.get("requested_modes_per_direction") == 480
    )
    expected_warning = (
        45.0 if m480_mpi1_solver_only else 170.0 if grid_direct else 180.0
    )
    expected_termination = (
        48.0 if m480_mpi1_solver_only else 195.0 if grid_direct else 220.0
    )
    for key, expected_value in (
        ("warning_memory_gib", expected_warning),
        ("terminate_memory_gib", expected_termination),
    ):
        if config["execution"].get(key) != expected_value:
            errors.append(
                (
                    f"execution.{key}",
                    f"Task39 requires {expected_value!r} for this mesh/profile",
                )
            )
    provenance = task039_material_provenance(config)
    if provenance is None:
        errors.append(
            (
                "materials",
                "Task39 requires the 5 nm n-only material provenance contract",
            )
        )
    output = config["output"]
    expected_canonical = kind in {
        "full3d_direct",
        "full3d_iterative",
        "hybrid_direct",
        "hybrid_iterative",
    }
    if output.get("export_canonical_vectors") is not expected_canonical:
        errors.append(
            (
                "output.export_canonical_vectors",
                f"Task39 {kind} requires {expected_canonical}",
            )
        )
    if kind == "full3d_direct":
        if config["execution"]["mpi_size"] != 8:
            errors.append(("execution.mpi_size", "Task39 Full3D direct requires MPI8"))
        solver = config["solver"]
        if solver.get("direct_solver_profile") != "default":
            errors.append(
                ("solver.direct_solver_profile", "Task39 direct requires default")
            )
        if solver.get("linear_solver") != "direct":
            errors.append(("solver.linear_solver", "Task39 direct requires direct"))
    elif kind == "full3d_iterative":
        if config["execution"]["mpi_size"] != 8:
            errors.append(
                ("execution.mpi_size", "Task39 Full3D iterative requires MPI8")
            )
        expected_solver = {
            "linear_solver": "fgmres",
            "preconditioner": "full3d_m3a_physical_slab_two_level",
            "restart": 90,
            "max_iterations": 4000,
            "relative_tolerance": 1.0e-6,
            "absolute_tolerance": 0.0,
            "initial_guess": "zero",
        }
        for key, value in expected_solver.items():
            if config["solver"].get(key) != value:
                errors.append((f"solver.{key}", f"Task39 requires {value!r}"))
    else:
        expected_solver = {
            "linear_solver": "direct" if kind == "hybrid_direct" else "fgmres",
            "preconditioner": (
                "hybrid_block_ldu_ilu0_dtn_woodbury"
                if kind == "hybrid_iterative"
                else None
            ),
            "restart": 90 if kind == "hybrid_iterative" else None,
            "max_iterations": 6000 if kind == "hybrid_iterative" else None,
            "relative_tolerance": 5.0e-9 if kind == "hybrid_iterative" else None,
            "absolute_tolerance": 0.0 if kind == "hybrid_iterative" else None,
            "initial_guess": "zero" if kind == "hybrid_iterative" else None,
            "ilu_level": 0 if kind == "hybrid_iterative" else None,
            "ilu_shift": 0.1 if kind == "hybrid_iterative" else None,
            "subdomain_count_per_endcap": 1 if kind == "hybrid_iterative" else None,
            "overlap_fraction": 0.0 if kind == "hybrid_iterative" else None,
            "side_residual_correction_steps": 2 if kind == "hybrid_iterative" else None,
        }
        for key, value in expected_solver.items():
            if value is not None and config["solver"].get(key) != value:
                errors.append((f"solver.{key}", f"Task39 requires {value!r}"))
        if kind == "hybrid_direct":
            if config["execution"]["mpi_size"] != 8:
                errors.append(
                    ("execution.mpi_size", "Task39 Hybrid direct requires MPI8")
                )
            if config["solver"].get("direct_solver_profile") != "default":
                errors.append(
                    ("solver.direct_solver_profile", "Task39 direct requires default")
                )
            if (
                method.get("requested_modes_per_direction")
                not in _TASK039_MODE_CANDIDATES
            ):
                errors.append(
                    (
                        "method.requested_modes_per_direction",
                        "Task39 Hybrid direct allows only 120/240/480/960",
                    )
                )
        else:
            if config["execution"]["mpi_size"] not in {1, 8}:
                errors.append(
                    (
                        "execution.mpi_size",
                        "Task39 Hybrid iterative allows only MPI1 or MPI8",
                    )
                )
            if (
                method.get("requested_modes_per_direction")
                not in _TASK039_MODE_CANDIDATES
            ):
                errors.append(
                    (
                        "method.requested_modes_per_direction",
                        "Task39 Hybrid iterative allows only numeric 120/240/480/960",
                    )
                )
    if kind in {"hybrid_direct", "hybrid_iterative"}:
        if (
            method.get("bottom_interface_nm"),
            method.get("top_interface_nm"),
        ) != (10.0, 110.0):
            errors.append(("method", "Task39 Hybrid interfaces must be 10/110 nm"))
        if (
            method.get("propagation_model"),
            method.get("traction_model"),
        ) != ("full3d_uniform_cg", "full3d_one_cell_exact_schur"):
            errors.append(("method", "Task39 Hybrid requires the full3d exact pair"))
    policy = method.get("canonical_trace_gate_policy")
    family_sha = method.get("canonical_trace_family_sha256")
    if policy is not None or family_sha is not None:
        if not (
            kind == "hybrid_direct"
            and method.get("requested_modes_per_direction") == 960
            and config["execution"].get("mpi_size") == 8
        ):
            errors.append(
                (
                    "method.canonical_trace_gate_policy",
                    "Task039 trace Gate is restricted to Hybrid direct M960 MPI8",
                )
            )
        if policy != TASK039_M960_TRACE_GATE_POLICY:
            errors.append(
                (
                    "method.canonical_trace_gate_policy",
                    f"must equal {TASK039_M960_TRACE_GATE_POLICY!r}",
                )
            )
        if family_sha != TASK039_E7_TRACE_FAMILY_SHA256:
            errors.append(
                (
                    "method.canonical_trace_family_sha256",
                    "must equal the approved Task39 E7 family record SHA256",
                )
            )
    return errors


def task038_hybrid_iterative_profile_errors(
    config: Mapping[str, Any],
) -> list[tuple[str, str]]:
    """Return errors for the finite public profile connected to Task37c.

    The historical Task37c runner constructs its own frozen target profile and
    therefore cannot safely consume arbitrary public fields.  This explicit
    table keeps the Task38 adapter fail-closed until a fully input-driven
    iterative runner exists; it is deliberately not a general capability
    registry.
    """

    expected: tuple[tuple[str, str, Any], ...] = (
        ("geometry", "geometry_kind", "rectangular_block_grating"),
        ("geometry", "period_x_nm", 50.0),
        ("geometry", "period_y_nm", 25.0),
        ("geometry", "z_min_nm", -10.0),
        ("geometry", "z_max_nm", 130.0),
        ("geometry", "interface_z_nm", 0.0),
        ("geometry", "air_height_nm", 130.0),
        ("geometry", "substrate_thickness_nm", 10.0),
        ("geometry", "grating_width_x_nm", 17.0),
        ("geometry", "grating_width_y_nm", 25.0),
        ("geometry", "grating_height_nm", 120.0),
        ("materials", "n_air", (1.0, 0.0)),
        ("materials", "mu_r", (1.0, 0.0)),
        ("materials", "substrate_name", "Si / silicon"),
        ("materials", "grating_name", "Si / silicon"),
        ("materials", "n_substrate", (0.999002304859, 0.00182649365)),
        ("materials", "n_grating", (0.999002304859, 0.00182649365)),
        ("incidence", "wavelength_nm", 13.5),
        ("incidence", "grazing_angle_deg", 1.0),
        ("incidence", "polarization", "s"),
        ("incidence", "electric_amplitude", 1.0),
        ("discretization", "nedelec_degree", 6),
        ("discretization", "visualization_degree", 6),
        ("discretization", "mesh_target_nm", 10.0),
        ("discretization", "mesh_cell_type", "hexahedron"),
        ("discretization", "mesh_spacing_mode", "boundary_fitted"),
        ("discretization", "assembly_backend", "assembly_time_static_condensed"),
        ("discretization", "floquet_constraint_mode", "auto"),
        ("boundary", "vertical_boundary", "dtn_port"),
        ("boundary", "scattering_background", "layered"),
        ("boundary", "use_floquet_x", True),
        ("boundary", "use_floquet_y", True),
        ("boundary", "dtn_order_policy", "auto_propagating"),
        ("boundary", "dtn_assembly", "auxiliary"),
        ("boundary", "use_pml", False),
        ("boundary", "pml_alpha", 5.0),
        ("method", "bottom_interface_nm", 10.0),
        ("method", "top_interface_nm", 110.0),
        ("method", "requested_modes_per_direction", 120),
        ("method", "propagation_model", "full3d_uniform_cg"),
        ("method", "traction_model", "full3d_one_cell_exact_schur"),
        ("solver", "linear_solver", "fgmres"),
        ("solver", "preconditioner", "hybrid_block_ldu_ilu0_dtn_woodbury"),
        ("solver", "restart", 90),
        ("solver", "max_iterations", 4500),
        ("solver", "relative_tolerance", 5.0e-9),
        ("solver", "absolute_tolerance", 0.0),
        ("solver", "initial_guess", "zero"),
        ("solver", "ilu_level", 0),
        ("solver", "ilu_shift", 0.1),
        ("solver", "subdomain_count_per_endcap", 1),
        ("solver", "overlap_fraction", 0.0),
        ("solver", "side_residual_correction_steps", 2),
        ("execution", "require_zero_swap", True),
        ("output", "export_fields", True),
        ("output", "export_diffraction_orders", True),
        ("output", "export_canonical_vectors", True),
        ("output", "export_modal_amplitudes", True),
        ("output", "export_reference_planes", True),
        ("output", "reference_plane_z_nm", (10.0, 30.0, 60.0, 90.0, 110.0)),
        ("output", "sample_count_x", 40),
        ("output", "sample_count_y", 20),
        ("output", "diffraction_sample_count_x", 24),
        ("output", "diffraction_sample_count_y", 24),
        ("output", "top_probe_z_nm", 110.0),
        ("output", "bottom_probe_z_nm", 10.0),
        ("output", "probe_fraction", 0.75),
        ("output", "diffraction_order_max_m", 2),
        ("output", "diffraction_order_max_n", 2),
    )
    errors: list[tuple[str, str]] = []
    for section, key, expected_value in expected:
        values = config[section]
        actual = values.get(key)
        if not _same_profile_value(actual, expected_value):
            errors.append(
                (
                    f"{section}.{key}",
                    f"Task37c iterative adapter requires {expected_value!r}",
                )
            )
    if config["execution"].get("mpi_size") not in {1, 8}:
        errors.append(
            (
                "execution.mpi_size",
                "Task37c iterative adapter accepts only MPI1 or MPI8",
            )
        )
    incidence = config["incidence"]
    if incidence.get("azimuth_deg") not in {-5.0, 0.0, 5.0}:
        errors.append(
            (
                "incidence.azimuth_deg",
                "Task37c iterative adapter accepts only -5, 0, or 5 degrees",
            )
        )
    for key in (
        "nedelec_trace_degree",
        "nedelec_interior_degree",
        "mesh_refined_size_nm",
        "mesh_refinement_radius_nm",
    ):
        if key in config["discretization"]:
            errors.append(
                (
                    f"discretization.{key}",
                    "Task37c iterative adapter does not accept this override",
                )
            )
    return errors


def _validate_cross_fields(config: Mapping[str, Any]) -> None:
    dimension = config["dimension"]
    geometry = config["geometry"]
    materials = config["materials"]
    incidence = config["incidence"]
    discretization = config["discretization"]
    d = discretization
    boundary = config["boundary"]
    method = config["method"]
    solver = config["solver"]
    execution = config["execution"]
    output = config["output"]
    kind = method["kind"]
    geometry_kind = geometry["geometry_kind"]
    model_id = str(config.get("model_id", ""))
    if (
        method.get("canonical_trace_gate_policy") is not None
        or method.get("canonical_trace_family_sha256") is not None
    ) and not _is_task039_candidate(config):
        raise _error(
            "method.canonical_trace_gate_policy",
            "Task039 canonical trace Gate fields are not valid for this model",
        )
    if model_id.startswith("task039_"):
        if model_id.startswith("task039_0p7nm"):
            if incidence.get("wavelength_nm") != 0.7:
                raise _error(
                    "incidence.wavelength_nm",
                    "0.7 nm component-only identity requires wavelength_nm=0.7",
                )
        elif not task039_model_id_matches(
            kind,
            model_id,
            method.get("requested_modes_per_direction"),
        ):
            raise _error(
                "model_id",
                "unsupported finite Task39 identity for this method and M",
            )

    if dimension == 2:
        if not kind.startswith("2d_"):
            raise _error("method.kind", "2D inputs require 2d_scattered or 2d_port")
        if geometry_kind not in {"euv_grating_2d", "layered_2d"}:
            raise _error(
                "geometry.geometry_kind",
                "2D geometry must be euv_grating_2d or layered_2d",
            )
        if discretization["mesh_cell_type"] not in {"triangle", "quadrilateral"}:
            raise _error(
                "discretization.mesh_cell_type", "2D allows triangle or quadrilateral"
            )
        if incidence["polarization"] not in {"tm", "te"}:
            raise _error("incidence.polarization", "2D allows only tm or te")
        if boundary.get("use_floquet_x") is not True:
            raise _error(
                "boundary.use_floquet_x",
                "2D periodic constraint contract requires true",
            )
        if "use_floquet_y" in boundary:
            raise _error("boundary.use_floquet_y", "2D must not provide use_floquet_y")
        if kind == "2d_scattered":
            if (
                boundary.get("vertical_boundary") != "pml"
                or boundary.get("use_pml") is not True
            ):
                raise _error(
                    "boundary",
                    "2d_scattered requires vertical_boundary=pml and use_pml=true",
                )
            _require(
                boundary, "scattering_background", "boundary.scattering_background"
            )
        else:
            if boundary["vertical_boundary"] not in {"dtn", "robin"}:
                raise _error(
                    "boundary.vertical_boundary", "2d_port requires dtn or robin"
                )
            if method["constraint_backend"] == "mpc_auto":
                raise _error(
                    "method.constraint_backend",
                    "2d_port does not support mpc_auto",
                )
            if boundary["vertical_boundary"] == "dtn":
                if method["constraint_backend"] != "manual":
                    raise _error(
                        "method.constraint_backend",
                        "2D Fourier DtN port requires manual constraints",
                    )
                if config["execution"]["mpi_size"] != 1:
                    raise _error(
                        "execution.mpi_size",
                        "2D Fourier DtN port is qualified only for MPI1",
                    )
                if (
                    incidence["polarization"] == "te"
                    and boundary.get("dtn_order_policy") != "zero_order"
                ):
                    raise _error(
                        "boundary.dtn_order_policy",
                        "TE Fourier DtN currently supports only zero_order",
                    )
            elif method["constraint_backend"] not in {"manual", "mpc_official"}:
                raise _error(
                    "method.constraint_backend",
                    "2D Robin port requires manual or mpc_official constraints",
                )
            if (
                boundary.get("use_pml") is True
                and boundary["vertical_boundary"] != "pml"
            ):
                raise _error(
                    "boundary.use_pml",
                    "PML cannot be combined with a non-PML 2D port boundary",
                )
        if solver["linear_solver"] != "direct":
            raise _error("solver.linear_solver", "2D public paths use direct")
    else:
        if kind in {"2d_scattered", "2d_port"}:
            raise _error("method.kind", "3D inputs require a 3D method")
        if geometry_kind not in {
            "airbox",
            "fresnel_interface",
            "flat_layer",
            "rectangular_block_grating",
        }:
            raise _error("geometry.geometry_kind", "invalid 3D geometry kind")
        if discretization["mesh_cell_type"] not in {
            "auto",
            "tetrahedron",
            "hexahedron",
        }:
            raise _error(
                "discretization.mesh_cell_type",
                "3D allows auto, tetrahedron, or hexahedron",
            )
        if incidence["polarization"] not in {"s", "p", "custom"}:
            raise _error("incidence.polarization", "3D allows s, p, or custom")
        if boundary["vertical_boundary"] not in {
            "dtn_port",
            "pml",
            "robin0",
            "strong_dirichlet",
        }:
            raise _error(
                "boundary.vertical_boundary",
                "3D allows dtn_port, pml, robin0, or strong_dirichlet",
            )
        floquet_xy = boundary.get("use_floquet_x")
        if floquet_xy != boundary.get("use_floquet_y"):
            raise _error("boundary.use_floquet_x", "3D Floquet x/y values must agree")
        if (geometry_kind != "airbox" or boundary.get("use_pml")) and not floquet_xy:
            raise _error(
                "boundary.use_floquet_x",
                "3D grating, Fresnel, and PML airbox stages require dual Floquet",
            )
        grating = geometry_kind == "rectangular_block_grating"
        grazing = "grazing_angle_deg" in incidence
        tilt = "tilt_from_downward_z_deg" in incidence
        if grazing == tilt:
            raise _error(
                "incidence",
                "provide exactly one of grazing_angle_deg or tilt_from_downward_z_deg",
            )
        if grating and not grazing:
            raise _error(
                "incidence.grazing_angle_deg", "required for 3D grating/Stage4"
            )
        if not grating and not tilt:
            raise _error(
                "incidence.tilt_from_downward_z_deg", "required for airbox/Fresnel"
            )
        if grazing and not 0.0 < incidence["grazing_angle_deg"] <= 90.0:
            raise _error(
                "incidence.grazing_angle_deg", "must satisfy 0 < grazing <= 90 degrees"
            )
        if tilt and not 0.0 <= incidence["tilt_from_downward_z_deg"] <= 90.0:
            raise _error(
                "incidence.tilt_from_downward_z_deg",
                "must satisfy 0 <= tilt <= 90 degrees",
            )
        if kind == "full3d_direct" and solver["linear_solver"] != "direct":
            raise _error("solver.linear_solver", "full3d_direct requires direct")
        if kind == "full3d_direct" and _is_task039_candidate(config):
            profile_errors = task039_profile_errors(config)
            if profile_errors:
                path, message = profile_errors[0]
                raise _error(path, message)
        if kind == "full3d_iterative":
            if not _is_task039_candidate(config):
                raise _error(
                    "method.kind",
                    "full3d_iterative is currently limited to the Task39 5 nm profile",
                )
            if solver["linear_solver"] != "fgmres":
                raise _error("solver.linear_solver", "full3d_iterative requires fgmres")
            if solver.get("preconditioner") != "full3d_m3a_physical_slab_two_level":
                raise _error(
                    "solver.preconditioner",
                    "full3d_iterative requires the accepted M3a physical-slab profile",
                )
            profile_errors = task039_profile_errors(config)
            if profile_errors:
                path, message = profile_errors[0]
                raise _error(path, message)
        if kind == "hybrid_direct":
            if solver["linear_solver"] != "direct":
                raise _error("solver.linear_solver", "hybrid_direct requires direct")
            allowed_degrees = (
                {1, 2, 3, 4, 6} if _is_task039_candidate(config) else {1, 2, 3, 4}
            )
            if discretization["nedelec_degree"] not in allowed_degrees:
                raise _error(
                    "discretization.nedelec_degree",
                    "hybrid_direct supports degrees 1 through 4; Task39 adds p6",
                )
            if solver.get("direct_solver_profile") != "default":
                raise _error(
                    "solver.direct_solver_profile",
                    "hybrid_direct only supports direct_solver_profile=default",
                )
            expected_assembly = (
                "assembly_time_static_condensed"
                if _is_task039_candidate(config)
                else "standard_full"
            )
            if discretization["assembly_backend"] != expected_assembly:
                raise _error(
                    "discretization.assembly_backend",
                    f"hybrid_direct requires {expected_assembly}",
                )
            expected_pair = (
                ("full3d_uniform_cg", "full3d_one_cell_exact_schur")
                if _is_task039_candidate(config)
                else ("continuous_beta", "continuous_qep_beta")
            )
            if (
                method["propagation_model"],
                method["traction_model"],
            ) != expected_pair:
                raise _error(
                    "method",
                    (
                        "hybrid_direct does not support this propagation/traction pair"
                        if _is_task039_candidate(config)
                        else "hybrid_direct adapter supports only "
                        "continuous_beta + continuous_qep_beta"
                    ),
                )
            for key in (
                "export_fields",
                "export_diffraction_orders",
                "export_modal_amplitudes",
                "export_reference_planes",
            ):
                if output.get(key) is not True:
                    raise _error(
                        f"output.{key}",
                        "hybrid_direct requires the supported Case080 output combination",
                    )
            expected_canonical = _is_task039_candidate(config)
            if output.get("export_canonical_vectors") is not expected_canonical:
                raise _error(
                    "output.export_canonical_vectors",
                    (
                        "Task39 hybrid_direct requires canonical vector export"
                        if expected_canonical
                        else "hybrid_direct canonical vector export is not supported"
                    ),
                )
            if output.get("unique_output") is not True:
                raise _error(
                    "output.unique_output",
                    "hybrid_direct requires unique_output=true",
                )
            if (
                output.get("diffraction_order_max_m") != 2
                or output.get("diffraction_order_max_n") != 2
            ):
                raise _error(
                    "output.diffraction_order_max_m",
                    "hybrid_direct supports only the accepted 2 x 2 reporting bounds",
                )
            if any(
                not method["bottom_interface_nm"] <= value <= method["top_interface_nm"]
                for value in output.get("reference_plane_z_nm", ())
            ):
                raise _error(
                    "output.reference_plane_z_nm",
                    "hybrid_direct reference planes must lie between its interfaces",
                )
            if _is_task039_candidate(config):
                profile_errors = task039_profile_errors(config)
                if profile_errors:
                    path, message = profile_errors[0]
                    raise _error(path, message)
        if kind == "hybrid_iterative":
            if solver["linear_solver"] != "fgmres":
                raise _error("solver.linear_solver", "hybrid_iterative requires fgmres")
            if solver["preconditioner"] != "hybrid_block_ldu_ilu0_dtn_woodbury":
                raise _error(
                    "solver.preconditioner",
                    "only the accepted hybrid block-LDU preconditioner is public",
                )
            if d["assembly_backend"] != "assembly_time_static_condensed":
                raise _error(
                    "discretization.assembly_backend",
                    "hybrid_iterative requires assembly_time_static_condensed",
                )
            if (
                method["propagation_model"],
                method["traction_model"],
            ) not in {
                ("full3d_uniform_cg", "scalar_cg_discrete_derivative"),
                ("full3d_uniform_cg", "full3d_one_cell_exact_schur"),
            }:
                raise _error(
                    "method",
                    "hybrid_iterative has no public support for this propagation/traction pair",
                )
            if (
                solver["ilu_level"],
                solver["subdomain_count_per_endcap"],
                solver["overlap_fraction"],
            ) != (0, 1, 0.0):
                raise _error(
                    "solver",
                    "hybrid_iterative requires ILU(0), one subdomain per endcap, and zero overlap",
                )
        if geometry_kind == "rectangular_block_grating":
            _require(
                boundary, "scattering_background", "boundary.scattering_background"
            )
            if boundary["scattering_background"] != "layered":
                raise _error(
                    "boundary.scattering_background",
                    "Stage4 rectangular grating currently requires layered",
                )
        elif geometry_kind == "flat_layer":
            if kind != "full3d_direct":
                raise _error(
                    "method.kind",
                    "flat_layer is currently connected only for full3d_direct",
                )
            if boundary.get("scattering_background") != "layered":
                raise _error(
                    "boundary.scattering_background",
                    "Stage4 flat layer currently requires layered",
                )
            if boundary["vertical_boundary"] != "dtn_port":
                raise _error(
                    "boundary.vertical_boundary",
                    "Stage4 flat layer requires dtn_port",
                )

        if geometry_kind == "fresnel_interface":
            if boundary["vertical_boundary"] != "pml":
                raise _error(
                    "boundary.vertical_boundary",
                    "fresnel_interface requires vertical_boundary=pml",
                )
        elif geometry_kind == "airbox":
            if boundary["use_pml"]:
                if boundary["vertical_boundary"] != "pml":
                    raise _error(
                        "boundary.vertical_boundary",
                        "airbox with PML requires vertical_boundary=pml",
                    )
            elif boundary["vertical_boundary"] != "strong_dirichlet":
                raise _error(
                    "boundary.vertical_boundary",
                    "airbox without PML uses strong_dirichlet",
                )
        else:
            if boundary["vertical_boundary"] == "strong_dirichlet":
                raise _error(
                    "boundary.vertical_boundary",
                    "Stage4 grating does not use strong_dirichlet",
                )

    if kind == "hybrid_direct" or kind == "hybrid_iterative":
        if method["bottom_interface_nm"] >= method["top_interface_nm"]:
            raise _error("method", "bottom_interface_nm must be below top_interface_nm")
        if kind == "hybrid_direct" and method["requested_modes_per_direction"] < 2:
            raise _error(
                "method.requested_modes_per_direction",
                "hybrid_direct requires at least two modes per direction",
            )
        if kind == "hybrid_iterative" and method["requested_modes_per_direction"] <= 0:
            raise _error("method.requested_modes_per_direction", "must be positive")
        if dimension != 3 or geometry_kind != "rectangular_block_grating":
            raise _error(
                "method.kind",
                "Hybrid public methods require a 3D rectangular Stage4 grating",
            )
        allowed_hybrid_cells = (
            {"auto", "hexahedron"} if kind == "hybrid_direct" else {"hexahedron"}
        )
        if d["mesh_cell_type"] not in allowed_hybrid_cells:
            raise _error(
                "discretization.mesh_cell_type",
                "hybrid_direct requires auto or hexahedron; hybrid_iterative requires hexahedron",
            )
        if boundary["vertical_boundary"] != "dtn_port":
            raise _error("boundary.vertical_boundary", "Hybrid requires dtn_port")
        if boundary.get("dtn_assembly") != "auxiliary":
            raise _error(
                "boundary.dtn_assembly", "Hybrid requires auxiliary DtN assembly"
            )
        if boundary.get("use_pml") is True:
            raise _error("boundary.use_pml", "Hybrid does not support PML")
        if boundary.get("scattering_background") != "layered":
            raise _error(
                "boundary.scattering_background", "Hybrid requires layered background"
            )
        if not (
            geometry["interface_z_nm"]
            < method["bottom_interface_nm"]
            < method["top_interface_nm"]
            < geometry["interface_z_nm"] + geometry["grating_height_nm"]
        ):
            raise _error(
                "method",
                "Hybrid interfaces must lie strictly inside the uniform grating slab",
            )
        if kind == "hybrid_iterative":
            profile_errors = (
                task039_profile_errors(config)
                if _is_task039_candidate(config)
                else task038_hybrid_iterative_profile_errors(config)
            )
            if profile_errors:
                path, message = profile_errors[0]
                raise _error(path, message)

    if incidence["polarization"] == "custom":
        if dimension != 3 or "custom_polarization" not in incidence:
            raise _error(
                "incidence.custom_polarization",
                "required only for 3D custom polarization",
            )
    elif "custom_polarization" in incidence:
        raise _error(
            "incidence.custom_polarization", "allowed only with polarization=custom"
        )
    if dimension == 2 and not isfinite(incidence["tilt_from_downward_y_deg"]):
        raise _error("incidence.tilt_from_downward_y_deg", "must be finite")
    if incidence["wavelength_nm"] <= 0.0:
        raise _error("incidence.wavelength_nm", "must be positive")
    if dimension == 3:
        from src.common.config_3d import SimulationConfig3D

        theta = (
            90.0 - incidence["grazing_angle_deg"]
            if "grazing_angle_deg" in incidence
            else incidence["tilt_from_downward_z_deg"]
        )
        try:
            SimulationConfig3D(
                lambda0=incidence["wavelength_nm"],
                n_air=_complex(materials["n_air"]),
                incident_theta_deg=theta,
                incident_phi_deg=incidence["azimuth_deg"],
                polarization_kind=incidence["polarization"],
                custom_polarization=(
                    None
                    if "custom_polarization" not in incidence
                    else tuple(
                        _complex(pair) for pair in incidence["custom_polarization"]
                    )
                ),
            ).polarization_vector
        except ValueError as exc:
            raise _error("incidence", str(exc)) from exc

    for key in ("period_x_nm", "air_height_nm"):
        if geometry[key] <= 0.0:
            raise _error(f"geometry.{key}", "must be positive")
    if dimension == 3 and geometry["period_y_nm"] <= 0.0:
        raise _error("geometry.period_y_nm", "must be positive")
    if geometry["substrate_thickness_nm"] < 0.0:
        raise _error("geometry.substrate_thickness_nm", "must be non-negative")
    if dimension == 3:
        if not geometry["z_min_nm"] < geometry["interface_z_nm"] < geometry["z_max_nm"]:
            raise _error(
                "geometry.interface_z_nm",
                "must lie strictly between z_min_nm and z_max_nm",
            )
        if not isclose(
            geometry["air_height_nm"],
            geometry["z_max_nm"] - geometry["interface_z_nm"],
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise _error(
                "geometry.air_height_nm",
                "must equal z_max_nm - interface_z_nm",
            )
        if not isclose(
            geometry["substrate_thickness_nm"],
            geometry["interface_z_nm"] - geometry["z_min_nm"],
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise _error(
                "geometry.substrate_thickness_nm",
                "must equal interface_z_nm - z_min_nm",
            )
    is_grating = geometry_kind in {"euv_grating_2d", "rectangular_block_grating"}
    if not is_grating:
        geometry.setdefault("grating_width_x_nm", 0.0)
        geometry.setdefault("grating_height_nm", 0.0)
        if dimension == 3:
            geometry.setdefault("grating_width_y_nm", 0.0)
    if is_grating:
        for key in ("grating_width_x_nm", "grating_height_nm"):
            _require(geometry, key, f"geometry.{key}")
        if dimension == 3:
            _require(geometry, "grating_width_y_nm", "geometry.grating_width_y_nm")
    if dimension == 2 or geometry_kind in {
        "fresnel_interface",
        "flat_layer",
        "rectangular_block_grating",
    }:
        _require(materials, "n_substrate", "materials.n_substrate")
    if dimension == 2 or geometry_kind in {"rectangular_block_grating"}:
        _require(materials, "n_grating", "materials.n_grating")
    for key in ("grating_width_x_nm", "grating_height_nm"):
        if key in geometry:
            if geometry[key] < 0.0:
                raise _error(f"geometry.{key}", "must be non-negative")
            if is_grating and geometry[key] <= 0.0:
                raise _error(
                    f"geometry.{key}",
                    "is required and must be positive for grating geometry",
                )
            if not is_grating and geometry[key] != 0.0:
                raise _error(
                    f"geometry.{key}",
                    "must be omitted or zero for non-grating geometry",
                )
    if dimension == 3 and "grating_width_y_nm" in geometry:
        if geometry["grating_width_y_nm"] < 0.0:
            raise _error("geometry.grating_width_y_nm", "must be non-negative")
        if is_grating and geometry["grating_width_y_nm"] <= 0.0:
            raise _error(
                "geometry.grating_width_y_nm", "required for 3D grating geometry"
            )
        if not is_grating and geometry["grating_width_y_nm"] != 0.0:
            raise _error(
                "geometry.grating_width_y_nm",
                "must be omitted or zero for non-grating geometry",
            )
    if geometry.get("grating_width_x_nm", 0.0) > geometry["period_x_nm"]:
        raise _error("geometry.grating_width_x_nm", "must not exceed period_x_nm")
    if (
        dimension == 2
        and geometry.get("grating_height_nm", 0.0) > geometry["air_height_nm"]
    ):
        raise _error(
            "geometry.grating_height_nm", "must not exceed air_height_nm in 2D"
        )
    if (
        dimension == 3
        and geometry.get("grating_width_y_nm", 0.0) > geometry["period_y_nm"]
    ):
        raise _error("geometry.grating_width_y_nm", "must not exceed period_y_nm")
    if (
        dimension == 3
        and geometry.get("grating_height_nm", 0.0)
        > geometry["z_max_nm"] - geometry["interface_z_nm"]
    ):
        raise _error("geometry.grating_height_nm", "must fit below z_max_nm")

    if dimension == 3:
        trace = discretization.get("nedelec_trace_degree")
        interior = discretization.get("nedelec_interior_degree")
        if (trace is None) != (interior is None):
            raise _error(
                "discretization", "trace and interior degree must be supplied together"
            )
    if discretization.get("mesh_spacing_mode") == "local_refined":
        if (
            "mesh_refined_size_nm" not in discretization
            or "mesh_refinement_radius_nm" not in discretization
        ):
            raise _error(
                "discretization", "local_refined requires refined size and radius"
            )
    elif (
        "mesh_refined_size_nm" in discretization
        or "mesh_refinement_radius_nm" in discretization
    ):
        raise _error(
            "discretization", "refinement size/radius are only valid for local_refined"
        )
    for key in ("nedelec_degree", "visualization_degree"):
        if discretization[key] < 1:
            raise _error(f"discretization.{key}", "must be at least one")
    for key in ("nedelec_trace_degree", "nedelec_interior_degree"):
        if key in discretization and discretization[key] < 1:
            raise _error(f"discretization.{key}", "must be at least one")
    if discretization["mesh_target_nm"] <= 0.0:
        raise _error("discretization.mesh_target_nm", "must be positive")
    if dimension == 2:
        if discretization["near_field_margin_x_nm"] < 0.0:
            raise _error(
                "discretization.near_field_margin_x_nm",
                "must be non-negative",
            )
        if discretization["near_field_air_top_nm"] <= 0.0:
            raise _error("discretization.near_field_air_top_nm", "must be positive")
        if discretization["near_field_sub_depth_nm"] <= 0.0:
            raise _error("discretization.near_field_sub_depth_nm", "must be positive")
    if (
        "mesh_refined_size_nm" in discretization
        and discretization["mesh_refined_size_nm"] <= 0.0
    ):
        raise _error("discretization.mesh_refined_size_nm", "must be positive")
    if (
        "mesh_refinement_radius_nm" in discretization
        and discretization["mesh_refinement_radius_nm"] <= 0.0
    ):
        raise _error("discretization.mesh_refinement_radius_nm", "must be positive")

    vertical = boundary["vertical_boundary"]
    is_dtn = vertical in {"dtn", "dtn_port"}
    for key in ("dtn_order_policy", "dtn_assembly"):
        if is_dtn and key not in boundary:
            raise _error(f"boundary.{key}", "required for a DtN boundary")
        if not is_dtn and key in boundary:
            raise _error(f"boundary.{key}", "only valid for a DtN boundary")
    if dimension == 3 and is_dtn and boundary.get("dtn_assembly") != "auxiliary":
        raise _error(
            "boundary.dtn_assembly", "3D public DtN assembly must be auxiliary"
        )
    if dimension == 2 and boundary.get("dtn_assembly") == "explicit":
        if kind != "2d_port" or boundary.get("dtn_order_policy") not in {
            "zero_order",
            "auto_propagating",
        }:
            raise _error(
                "boundary.dtn_assembly",
                "2D explicit DtN is public only for zero_order or auto_propagating 2d_port",
            )
    if vertical == "pml":
        if boundary.get("use_pml") is not True:
            raise _error("boundary.use_pml", "must be true for a PML boundary")
        for key in ("pml_top_thickness_nm", "pml_bottom_thickness_nm"):
            if key not in boundary or boundary[key] <= 0.0:
                raise _error(f"boundary.{key}", "positive thickness required for PML")
        if boundary.get("pml_alpha", 0.0) <= 0.0:
            raise _error("boundary.pml_alpha", "must be positive for PML")
    elif boundary.get("use_pml") is True:
        raise _error(
            "boundary.use_pml", "true is only valid with vertical_boundary=pml"
        )
    if "pml_top_thickness_nm" in boundary and boundary["pml_top_thickness_nm"] < 0.0:
        raise _error("boundary.pml_top_thickness_nm", "must be non-negative")
    if (
        "pml_bottom_thickness_nm" in boundary
        and boundary["pml_bottom_thickness_nm"] < 0.0
    ):
        raise _error("boundary.pml_bottom_thickness_nm", "must be non-negative")
    if vertical != "pml" and any(
        key in boundary for key in ("pml_top_thickness_nm", "pml_bottom_thickness_nm")
    ):
        raise _error(
            "boundary", "PML thickness fields are only valid for a PML boundary"
        )

    if execution["mpi_size"] < 1:
        raise _error("execution.mpi_size", "must be at least one")
    if execution["warning_memory_gib"] <= 0 or execution["terminate_memory_gib"] <= 0:
        raise _error("execution", "memory thresholds must be positive")
    if execution["warning_memory_gib"] >= execution["terminate_memory_gib"]:
        raise _error(
            "execution", "warning_memory_gib must be below terminate_memory_gib"
        )
    if execution["timeout_seconds"] <= 0:
        raise _error("execution.timeout_seconds", "must be positive")

    if dimension == 3:
        if output["export_reference_planes"]:
            _require(output, "reference_plane_z_nm", "output.reference_plane_z_nm")
            if not output["reference_plane_z_nm"]:
                raise _error("output.reference_plane_z_nm", "must not be empty")
            if output["sample_count_x"] <= 0 or output["sample_count_y"] <= 0:
                raise _error("output", "reference sample counts must be positive")
            if any(
                not geometry["z_min_nm"] <= value <= geometry["z_max_nm"]
                for value in output["reference_plane_z_nm"]
            ):
                raise _error(
                    "output.reference_plane_z_nm",
                    "planes must lie inside z bounds",
                )
        elif "reference_plane_z_nm" in output:
            raise _error(
                "output", "reference-plane fields require export_reference_planes=true"
            )
    if output["export_diffraction_orders"]:
        _require(output, "diffraction_order_max_m", "output.diffraction_order_max_m")
        if dimension == 3:
            _require(
                output, "diffraction_order_max_n", "output.diffraction_order_max_n"
            )
    if "diffraction_order_max_m" in output and output["diffraction_order_max_m"] < 0:
        raise _error("output.diffraction_order_max_m", "must be non-negative")
    if (
        dimension == 3
        and "diffraction_order_max_n" in output
        and output["diffraction_order_max_n"] < 0
    ):
        raise _error("output.diffraction_order_max_n", "must be non-negative")
    if dimension == 3 and not (0.0 < output["probe_fraction"] < 1.0):
        raise _error("output.probe_fraction", "must lie strictly between zero and one")
    if dimension == 2 and output["power_probe_num_points"] <= 1:
        raise _error("output.power_probe_num_points", "must be greater than one")
    if dimension == 3:
        for key in ("diffraction_sample_count_x", "diffraction_sample_count_y"):
            if output[key] <= 0:
                raise _error(f"output.{key}", "must be positive")
    if "electric_amplitude" in incidence and incidence["electric_amplitude"] < 0.0:
        raise _error("incidence.electric_amplitude", "must be non-negative")
    if kind in {"hybrid_iterative", "full3d_iterative"}:
        for key in ("restart", "max_iterations", "subdomain_count_per_endcap"):
            if key in solver and solver[key] <= 0:
                raise _error(f"solver.{key}", "must be positive")
        if solver["relative_tolerance"] <= 0.0 or solver["absolute_tolerance"] < 0.0:
            raise _error("solver", "tolerances must be relative>0 and absolute>=0")
    if kind == "hybrid_iterative":
        if solver["ilu_level"] < 0 or solver["ilu_shift"] < 0.0:
            raise _error("solver", "ILU level/shift must be non-negative")
        if not 0.0 <= solver["overlap_fraction"] < 1.0:
            raise _error("solver.overlap_fraction", "must satisfy 0 <= value < 1")


def _validate_loaded_input(loaded: LoadedInput) -> dict[str, Any]:
    """Validate and return a detached normalized public configuration."""

    return _validate_sections(_plain(loaded.document))


def _complex(pair: tuple[float, float]) -> complex:
    return complex(pair[0], pair[1])


def _complex_json(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return _complex_json(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"cannot convert {type(value).__name__} to JSON")


def simulation_config_2d_from_normalized(config: Mapping[str, Any]):
    from src.common.config import SimulationConfig

    g = config["geometry"]
    m = config["materials"]
    i = config["incidence"]
    d = config["discretization"]
    b = config["boundary"]
    method = config["method"]
    out = config["output"]
    is_port = method["kind"] == "2d_port"
    pml = b.get("use_pml", False)
    cfg = SimulationConfig(
        case_name=config["model_id"],
        calculation_method="port" if is_port else "scattered",
        constraint_backend=method["constraint_backend"],
        port_boundary_model="dtn" if b["vertical_boundary"] == "dtn" else "robin",
        scattering_background=b.get("scattering_background", "layered"),
        polarization_type=i["polarization"].upper(),
        period_x=g["period_x_nm"],
        air_height=g["air_height_nm"],
        substrate_thickness=g["substrate_thickness_nm"],
        pml_top_thickness=b.get("pml_top_thickness_nm", 0.0),
        pml_bottom_thickness=b.get("pml_bottom_thickness_nm", 0.0),
        grating_width=g.get("grating_width_x_nm", 0.0),
        grating_height=g.get("grating_height_nm", 0.0),
        lambda0=i["wavelength_nm"],
        incident_angle_deg=i["tilt_from_downward_y_deg"],
        n_air=_complex(m["n_air"]),
        n_substrate=(
            None if m.get("n_substrate") is None else _complex(m["n_substrate"])
        ),
        n_grating=(None if m.get("n_grating") is None else _complex(m["n_grating"])),
        use_pml=pml,
        port_use_pml=pml if is_port else False,
        port_incident_amplitude=complex(i["electric_amplitude"], 0.0),
        incident_e0_v_per_m=i["electric_amplitude"],
        port_dtn_order_count=0,
        port_dtn_assembly=b.get("dtn_assembly", "auxiliary"),
        port_use_diffraction_orders=b.get("dtn_order_policy") == "auto_propagating",
        unique_output=out["unique_output"],
        compute_power_metrics=out["compute_power_metrics"],
        diffraction_order_count=out.get("diffraction_order_max_m", 0),
        power_probe_num_points=out["power_probe_num_points"],
        nedelec_degree=d["nedelec_degree"],
        visualization_degree=d["visualization_degree"],
        generate_png_plots=out["generate_png_plots"],
        mesh_target_size=d["mesh_target_nm"],
        mesh_cell_shape=d["mesh_cell_type"],
        mesh_lock_near_field_template=d["lock_near_field_template"],
        near_field_margin_x=d["near_field_margin_x_nm"],
        near_field_air_top=d["near_field_air_top_nm"],
        near_field_sub_depth=d["near_field_sub_depth_nm"],
        pml_alpha=b.get("pml_alpha", 5.0),
    )
    return cfg


def _build_2d_config(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg = simulation_config_2d_from_normalized(config)
    return {
        "internal": {"incident_theta_deg": cfg.incident_angle_deg},
        "k0": cfg.k0,
        "omega": cfg.omega,
        "wavevector": [_complex_json(cfg.kx), _complex_json(cfg.ky)],
        "polarization": list(cfg.polarization),
        "floquet_phase": _complex_json(cfg.floquet_phase),
        "mesh_cell_type_resolved": cfg.mesh_cell_shape,
        "total_height": cfg.total_height,
        "config_properties": {
            "x_min": cfg.x_min,
            "x_max": cfg.x_max,
            "y_min": cfg.y_min,
            "y_max": cfg.y_max,
            "eps_air": _complex_json(cfg.eps_air),
            "eps_substrate": _complex_json(cfg.eps_substrate),
            "eps_grating": _complex_json(cfg.eps_grating),
        },
    }


def simulation_config_3d_from_normalized(
    config: Mapping[str, Any],
):
    """Build the runtime 3D config from the already-normalized public fields.

    T2 resolution and the later Full3D adapter deliberately share this one
    field mapping.  The adapter must not reconstruct a second public schema.
    """

    from src.common.config_3d import SimulationConfig3D

    g = config["geometry"]
    m = config["materials"]
    i = config["incidence"]
    d = config["discretization"]
    b = config["boundary"]
    solver = config["solver"]
    out = config["output"]
    theta = (
        90.0 - i["grazing_angle_deg"]
        if "grazing_angle_deg" in i
        else i["tilt_from_downward_z_deg"]
    )
    if g["geometry_kind"] == "rectangular_block_grating":
        stage_case = "stage4_block_grating"
    elif g["geometry_kind"] == "flat_layer":
        stage_case = "stage4_flat_layer_sanity"
    elif g["geometry_kind"] == "fresnel_interface":
        stage_case = "fresnel_interface"
    elif b.get("use_floquet_x") and not b.get("use_pml"):
        stage_case = "floquet_airbox"
    elif b.get("use_pml"):
        stage_case = "pml_airbox"
    else:
        stage_case = "stage1_airbox"
    runtime_geometry_kind = (
        "rectangular_block_grating"
        if g["geometry_kind"] == "flat_layer"
        else g["geometry_kind"]
    )
    reporting_requested = (
        out.get("export_diffraction_orders", False)
        and out.get("diffraction_order_max_m") is not None
        and out.get("diffraction_order_max_n") is not None
    )
    return SimulationConfig3D(
        case_name=config["model_id"],
        stage_case=stage_case,
        geometry_kind=runtime_geometry_kind,
        lambda0=i["wavelength_nm"],
        n_air=_complex(m["n_air"]),
        mu_r=_complex(m["mu_r"]),
        period_x=g["period_x_nm"],
        period_y=g["period_y_nm"],
        z_min=g["z_min_nm"],
        z_max=g["z_max_nm"],
        air_height=g["air_height_nm"],
        substrate_thickness=g["substrate_thickness_nm"],
        grating_height=g.get("grating_height_nm", 0.0),
        grating_width_x=g.get("grating_width_x_nm", 0.0),
        grating_width_y=g.get("grating_width_y_nm", 0.0),
        n_substrate=(
            None if m.get("n_substrate") is None else _complex(m["n_substrate"])
        ),
        n_grating=(None if m.get("n_grating") is None else _complex(m["n_grating"])),
        substrate_material_label=m.get("substrate_name"),
        grating_material_label=m.get("grating_name"),
        interface_z=g["interface_z_nm"],
        scattering_background=b.get("scattering_background", "layered"),
        stage4_boundary_model=b["vertical_boundary"],
        stage4_dtn_order_policy=b.get("dtn_order_policy", "auto_propagating"),
        stage4_dtn_assembly=b.get("dtn_assembly", "auxiliary"),
        use_floquet_xy=b.get("use_floquet_x", False),
        use_pml=b.get("use_pml", False),
        pml_top_thickness=b.get("pml_top_thickness_nm", 0.0),
        pml_bottom_thickness=b.get("pml_bottom_thickness_nm", 0.0),
        pml_alpha=b.get("pml_alpha", 5.0),
        incident_theta_deg=theta,
        incident_phi_deg=i["azimuth_deg"],
        polarization_kind=i["polarization"],
        custom_polarization=None
        if "custom_polarization" not in i
        else tuple(_complex(pair) for pair in i["custom_polarization"]),
        incident_amplitude=complex(i["electric_amplitude"], 0.0),
        incident_e0_v_per_m=i["electric_amplitude"],
        nedelec_degree=d["nedelec_degree"],
        nedelec_trace_degree=d.get("nedelec_trace_degree"),
        nedelec_interior_degree=d.get("nedelec_interior_degree"),
        visualization_degree=d["visualization_degree"],
        mesh_target_size=d["mesh_target_nm"],
        mesh_cell_type=d["mesh_cell_type"],
        mesh_spacing_mode=d.get("mesh_spacing_mode", "auto"),
        mesh_refined_size=d.get("mesh_refined_size_nm"),
        mesh_refinement_radius=d.get("mesh_refinement_radius_nm"),
        floquet_constraint_mode=d.get("floquet_constraint_mode", "auto"),
        diffraction_zero_order_only=not reporting_requested,
        # These public requests are reporting bounds only.  DtN mode selection
        # uses stage4_dtn_order_policy independently below.
        diffraction_order_max_m=None,
        diffraction_order_max_n=None,
        reporting_diffraction_order_max_m=out.get("diffraction_order_max_m"),
        reporting_diffraction_order_max_n=out.get("diffraction_order_max_n"),
        diffraction_sample_count_x=out["diffraction_sample_count_x"],
        diffraction_sample_count_y=out["diffraction_sample_count_y"],
        diffraction_top_probe_z=out.get("top_probe_z_nm"),
        diffraction_bottom_probe_z=out.get("bottom_probe_z_nm"),
        diffraction_probe_fraction=out["probe_fraction"],
        full3d_reference_export=out["export_reference_planes"],
        full3d_reference_plane_z=tuple(out.get("reference_plane_z_nm", ())),
        full3d_reference_sample_count_x=out["sample_count_x"],
        full3d_reference_sample_count_y=out["sample_count_y"],
        petsc_direct_solver_profile=solver.get("direct_solver_profile", "default"),
        stage4_full3d_assembly_backend=d.get("assembly_backend", "standard_full"),
        unique_output=out["unique_output"],
    )


def _build_3d_config(config: Mapping[str, Any]) -> dict[str, Any]:
    from src.common.config_3d import (
        qualify_stage4_full3d_assembly_backend,
        resolve_stage4_full3d_assembly_backend,
    )

    i = config["incidence"]
    d = config["discretization"]
    cfg = simulation_config_3d_from_normalized(config)
    theta = cfg.incident_theta_deg
    try:
        fixed_trace_contract = cfg.nedelec_fixed_trace_contract
        trace_degree_resolved = cfg.nedelec_trace_degree_resolved
    except ValueError as exc:
        raise _error("discretization", str(exc)) from exc
    floquet_mode = d.get("floquet_constraint_mode", "auto")
    if (
        floquet_mode in {"topological_edges", "sparse_facet"}
        and trace_degree_resolved != 1
    ):
        raise _error(
            "discretization.floquet_constraint_mode",
            "topological_edges/sparse_facet require resolved trace degree 1",
        )
    if floquet_mode == "topological_trace_p2" and trace_degree_resolved != 2:
        raise _error(
            "discretization.floquet_constraint_mode",
            "topological_trace_p2 requires resolved trace degree 2",
        )
    try:
        assembly_audit = resolve_stage4_full3d_assembly_backend(cfg, apply=False)
        assembly_qualification = qualify_stage4_full3d_assembly_backend(
            cfg, audit=assembly_audit
        )
    except ValueError as exc:
        raise _error("discretization.assembly_backend", str(exc)) from exc
    derived = {
        "internal": {
            "incident_theta_deg": theta,
            "incident_phi_deg": i["azimuth_deg"],
            "stage_case": cfg.stage_case,
        },
        "k0": cfg.k0,
        "omega": cfg.omega,
        "direction_vector": _jsonable(cfg.direction_vector),
        "wavevector": _jsonable(cfg.wavevector),
        "polarization": _jsonable(cfg.polarization_vector),
        "floquet_phase_x": _complex_json(cfg.floquet_phase_x),
        "floquet_phase_y": _complex_json(cfg.floquet_phase_y),
        "mesh_cells": list(cfg.mesh_cells),
        "mesh_cell_type_resolved": cfg.mesh_cell_type_resolved,
        "mesh_spacing_mode_requested": cfg.mesh_spacing_mode_requested,
        "domain_z_min": cfg.domain_z_min,
        "domain_z_max": cfg.domain_z_max,
        "physical_bounds": {
            "x_min": cfg.x_min,
            "x_max": cfg.x_max,
            "y_min": cfg.y_min,
            "y_max": cfg.y_max,
        },
        "config_properties": {
            "eps_air": _complex_json(cfg.eps_air),
            "eps_substrate": _complex_json(cfg.eps_substrate),
            "eps_grating": _complex_json(cfg.eps_grating),
            "grating_x_min": cfg.grating_x_min,
            "grating_x_max": cfg.grating_x_max,
            "grating_y_min": cfg.grating_y_min,
            "grating_y_max": cfg.grating_y_max,
        },
        "stage4_assembly_backend_audit": {
            "resolution": assembly_audit,
            "qualification": assembly_qualification,
        },
        "nedelec_trace_contract": fixed_trace_contract,
        "nedelec_trace_degree_resolved": trace_degree_resolved,
        "floquet_constraint_mode_requested": floquet_mode,
    }
    material_provenance = task039_material_provenance(config)
    if material_provenance is not None:
        derived["material_provenance"] = material_provenance
        derived["external_mode_inventory"] = (
            _task039_dynamic_external_mode_inventory_from_cfg(cfg)
        )
    return derived


def resolve_loaded_input(loaded: LoadedInput) -> RunSpecification:
    """Validate one loaded input and resolve its derived pure configuration."""

    normalized = _validate_loaded_input(loaded)
    dimension = normalized["dimension"]
    derived = (
        _build_2d_config(normalized) if dimension == 2 else _build_3d_config(normalized)
    )
    physical = {
        section: normalized[section]
        for section in (
            "geometry",
            "materials",
            "incidence",
            "discretization",
            "boundary",
        )
    }
    physical_sha = sha256(canonical_json_bytes(physical)).hexdigest()
    output = normalized["output"]
    method = normalized["method"]["kind"]
    modes = normalized["method"].get("requested_modes_per_direction")
    mode_text = "na" if modes is None else str(modes)
    parent = (
        Path(output["results_root"])
        / normalized["model_id"]
        / (
            f"{normalized['run_id']}__{method}__mpi{normalized['execution']['mpi_size']}__M{mode_text}"
        )
    )
    return RunSpecification(
        identity={key: normalized[key] for key in IDENTITY_KEYS},
        geometry=normalized["geometry"],
        materials=normalized["materials"],
        incidence=normalized["incidence"],
        discretization=normalized["discretization"],
        boundary=normalized["boundary"],
        method=normalized["method"],
        solver=normalized["solver"],
        execution=normalized["execution"],
        output=normalized["output"],
        derived=derived,
        source_path=loaded.source_path,
        raw_input_bytes=loaded.raw_input_bytes,
        input_sha256=loaded.input_sha256,
        physical_model_sha256=physical_sha,
        expected_output_parent=parent,
    )


def load_and_resolve(path: str | Path) -> RunSpecification:
    from .input_loader import load_dat_input

    return resolve_loaded_input(load_dat_input(path))


__all__ = [
    "InputError",
    "load_and_resolve",
    "resolve_loaded_input",
    "simulation_config_2d_from_normalized",
    "simulation_config_3d_from_normalized",
    "task039_07nm_launch_error",
    "task039_air_side_external_mode_inventory",
    "task039_dynamic_external_mode_inventory",
    "task039_material_provenance",
    "task039_model_id_matches",
    "task039_profile_errors",
]
