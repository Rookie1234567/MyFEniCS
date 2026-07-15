from __future__ import annotations

import cmath
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # The fixed DOLFINx image keeps this optional.
    Draft202012Validator = None  # type: ignore[assignment,misc]


CASE_ID = "090_high_order_3d_floquet_hcurl"
SCHEMA_VERSION = "task033.case090.oracle-plan.v1"
CORE_GATE_SCHEMA_VERSION = "task033.case090.core-gates.v1"

WAVELENGTH_NM = 13.5
FIXTURE_PERIOD_X_NM = 10.0
FIXTURE_PERIOD_Y_NM = 10.0
FIXTURE_Z_MIN_NM = -5.0
FIXTURE_Z_MAX_NM = 5.0
AIR_INDEX = 1.0 + 0.0j
CURRENT_SI_INDEX = 0.999002304859 + 0.00182649365j

DEGREES = (1, 2, 3, 4)
MESH_TARGETS_NM = (5.0, 2.5)
MPI_SIZES = (1, 2, 4)
POLARIZATIONS = ("s", "p")
GRAZING_ANGLES_DEG = (1.0, 5.0, 10.0)

CORE_GATE_LIMITS = {
    "constraint_round_trip_relative_error": 1.0e-12,
    "bloch_trace_mismatch": 1.0e-11,
    "reduced_full_action_relative_error": 1.0e-11,
    "full_true_residual": 1.0e-10,
    "mpi_result_difference": 1.0e-10,
}
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CASE_ROOT = Path(__file__).resolve().parents[2] / "benchmarks" / "cases" / CASE_ID


def _finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _stable_float(value: float) -> float:
    """Serialize libm results reproducibly across the host and Docker image."""

    result = float(format(_finite(value, name="serialized float"), ".13g"))
    return 0.0 if result == 0.0 else result


def _complex_json(value: complex) -> dict[str, float]:
    number = complex(value)
    return {
        "real": _stable_float(number.real),
        "imag": _stable_float(number.imag),
    }


def complex_from_json(value: Mapping[str, object]) -> complex:
    """Decode the Case090 JSON representation of one complex scalar."""

    if set(value) != {"real", "imag"}:
        raise ValueError("A complex scalar must contain exactly real and imag.")
    return complex(
        _finite(value["real"], name="real"),
        _finite(value["imag"], name="imag"),
    )


def theta_from_normal_deg(grazing_deg: float) -> float:
    """Convert a grazing angle measured from the surface to the normal angle."""

    grazing = _finite(grazing_deg, name="grazing_deg")
    if not 0.0 < grazing < 90.0:
        raise ValueError("grazing_deg must lie strictly between 0 and 90 degrees.")
    return 90.0 - grazing


def incident_direction(
    grazing_deg: float, *, phi_deg: float = 0.0
) -> tuple[float, float, float]:
    """Return the unit direction for incidence from upper air toward minus z."""

    theta = math.radians(theta_from_normal_deg(grazing_deg))
    phi = math.radians(_finite(phi_deg, name="phi_deg"))
    return (
        math.sin(theta) * math.cos(phi),
        math.sin(theta) * math.sin(phi),
        -math.cos(theta),
    )


def polarization_vector(
    grazing_deg: float, polarization: str, *, phi_deg: float = 0.0
) -> tuple[float, float, float]:
    """Return the S or P electric unit vector for the downward incident wave."""

    kind = str(polarization).lower()
    if kind not in POLARIZATIONS:
        raise ValueError("polarization must be 's' or 'p'.")
    phi = math.radians(_finite(phi_deg, name="phi_deg"))
    s_hat = (-math.sin(phi), math.cos(phi), 0.0)
    if kind == "s":
        return s_hat
    direction = incident_direction(grazing_deg, phi_deg=phi_deg)
    # P uses k-hat cross S.  This is the convention already used by the 3D
    # analytic-field path and fixes the reflected-P amplitude sign.
    return (
        direction[1] * s_hat[2] - direction[2] * s_hat[1],
        direction[2] * s_hat[0] - direction[0] * s_hat[2],
        direction[0] * s_hat[1] - direction[1] * s_hat[0],
    )


def _cross(
    left: Sequence[complex], right: Sequence[complex]
) -> tuple[complex, complex, complex]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _scaled(
    scalar: complex, vector: Sequence[complex]
) -> tuple[complex, complex, complex]:
    return tuple(complex(scalar) * complex(value) for value in vector)  # type: ignore[return-value]


def _summed(
    left: Sequence[complex], right: Sequence[complex]
) -> tuple[complex, complex, complex]:
    return tuple(complex(a) + complex(b) for a, b in zip(left, right))  # type: ignore[return-value]


def _complex_vector_json(vector: Sequence[complex]) -> list[dict[str, float]]:
    if len(vector) != 3:
        raise ValueError("A field vector must contain exactly three components.")
    return [_complex_json(value) for value in vector]


def _phase_sample(
    *,
    point_nm: Sequence[float],
    wavevector_per_nm: Sequence[complex],
    electric_basis: Sequence[complex],
    magnetic_code_basis: Sequence[complex],
    amplitude: complex,
) -> tuple[dict[str, Any], tuple[complex, ...], tuple[complex, ...]]:
    phase = cmath.exp(
        1j
        * sum(
            complex(k) * float(coordinate)
            for k, coordinate in zip(wavevector_per_nm, point_nm)
        )
    )
    electric = _scaled(amplitude * phase, electric_basis)
    magnetic = _scaled(amplitude * phase, magnetic_code_basis)
    return (
        {
            "wavevector_per_nm": _complex_vector_json(wavevector_per_nm),
            "electric_basis": _complex_vector_json(electric_basis),
            "magnetic_code_basis": _complex_vector_json(magnetic_code_basis),
            "amplitude": _complex_json(amplitude),
            "phase": _complex_json(phase),
            "electric_field": _complex_vector_json(electric),
            "magnetic_code_field": _complex_vector_json(magnetic),
        },
        electric,
        magnetic,
    )


def _positive_sqrt(value: complex) -> complex:
    root = cmath.sqrt(complex(value))
    if root.imag < -1.0e-14 or (abs(root.imag) <= 1.0e-14 and root.real < 0.0):
        root = -root
    return root


def plane_wave_oracle(
    *,
    grazing_deg: float,
    polarization: str,
    phi_deg: float = 0.0,
    wavelength_nm: float = WAVELENGTH_NM,
    refractive_index: complex = AIR_INDEX,
    period_x_nm: float = FIXTURE_PERIOD_X_NM,
    period_y_nm: float = FIXTURE_PERIOD_Y_NM,
) -> dict[str, Any]:
    """Build an analytic downward Bloch plane-wave oracle.

    The phasor convention is ``exp(i k dot r)`` with ``exp(-i omega t)``.
    Complex vectors are serialized component-wise to keep the record JSON-only.
    """

    wavelength = _finite(wavelength_nm, name="wavelength_nm")
    period_x = _finite(period_x_nm, name="period_x_nm")
    period_y = _finite(period_y_nm, name="period_y_nm")
    if wavelength <= 0.0 or period_x <= 0.0 or period_y <= 0.0:
        raise ValueError("Wavelength and periods must be positive.")
    n_medium = complex(refractive_index)
    if abs(n_medium) == 0.0:
        raise ValueError("refractive_index must be nonzero.")

    kind = str(polarization).lower()
    direction = incident_direction(grazing_deg, phi_deg=phi_deg)
    e_hat = polarization_vector(grazing_deg, kind, phi_deg=phi_deg)
    k0 = 2.0 * math.pi / wavelength
    wavevector = tuple(k0 * n_medium * component for component in direction)
    e_complex = tuple(complex(component) for component in e_hat)
    h_code = tuple(value / k0 for value in _cross(wavevector, e_complex))
    phase_x = cmath.exp(1j * wavevector[0] * period_x)
    phase_y = cmath.exp(1j * wavevector[1] * period_y)

    sample_point = (2.0, 3.0, -1.0)
    sample_phase = cmath.exp(
        1j * sum(k * coordinate for k, coordinate in zip(wavevector, sample_point))
    )
    return {
        "oracle_type": "analytic_bloch_plane_wave",
        "field_convention": "exp(i*k_dot_r) with exp(-i*omega*t)",
        "incident_side": "upper_air",
        "propagation_z": "minus_z",
        "wavelength_nm": wavelength,
        "refractive_index": _complex_json(n_medium),
        "grazing_deg_from_surface": _stable_float(grazing_deg),
        "theta_deg_from_normal": _stable_float(theta_from_normal_deg(grazing_deg)),
        "phi_deg": _stable_float(phi_deg),
        "polarization": kind,
        "direction": [_stable_float(value) for value in direction],
        "wavevector_per_nm": [_complex_json(value) for value in wavevector],
        "electric_unit_vector": [_complex_json(value) for value in e_complex],
        "magnetic_code_unit_vector": [_complex_json(value) for value in h_code],
        "bloch_phase_plus_period": {
            "x": _complex_json(phase_x),
            "y": _complex_json(phase_y),
        },
        "sample": {
            "point_nm": list(sample_point),
            "electric_field": [
                _complex_json(sample_phase * value) for value in e_complex
            ],
            "magnetic_code_field": [
                _complex_json(sample_phase * value) for value in h_code
            ],
        },
    }


def fresnel_oracle(
    *,
    grazing_deg: float,
    polarization: str,
    n_incident: complex = AIR_INDEX,
    n_transmitted: complex = CURRENT_SI_INDEX,
) -> dict[str, Any]:
    """Return complex E-amplitude and interface-power Fresnel data.

    P amplitudes use the local ``k-hat cross S`` basis on each propagation
    direction.  Consequently the normal-incidence P reflection coefficient has
    the opposite scalar sign from S while representing the same tangential E.
    """

    kind = str(polarization).lower()
    if kind not in POLARIZATIONS:
        raise ValueError("polarization must be 's' or 'p'.")
    n1 = complex(n_incident)
    n2 = complex(n_transmitted)
    if abs(n1) == 0.0 or abs(n2) == 0.0:
        raise ValueError("Fresnel refractive indices must be nonzero.")

    theta_i = math.radians(theta_from_normal_deg(grazing_deg))
    sin_i = math.sin(theta_i)
    cos_i = math.cos(theta_i)
    sin_t = n1 / n2 * sin_i
    cos_t = _positive_sqrt(1.0 - sin_t * sin_t)

    r_s = (n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)
    t_s = 2.0 * n1 * cos_i / (n1 * cos_i + n2 * cos_t)
    r_p = (n2 * cos_i - n1 * cos_t) / (n2 * cos_i + n1 * cos_t)
    t_p = 2.0 * n1 * cos_i / (n2 * cos_i + n1 * cos_t)
    reflection = r_s if kind == "s" else r_p
    transmission = t_s if kind == "s" else t_p
    if kind == "s":
        incident_normal_admittance = (n1 * cos_i).real
        transmitted_normal_admittance = (n2 * cos_t).real
    else:
        # With the local k-hat x S electric basis, P has H_y=-n E_amp.
        # The lossy-medium normal flux is therefore Re(conj(n)*cos(theta)),
        # not the S-polarized Re(n*cos(theta)) expression.
        incident_normal_admittance = (n1.conjugate() * cos_i).real
        transmitted_normal_admittance = (n2.conjugate() * cos_t).real
    if incident_normal_admittance <= 0.0:
        raise ValueError("Incident Fresnel normal admittance must be positive.")
    admittance_ratio = transmitted_normal_admittance / incident_normal_admittance
    reflectance = abs(reflection) ** 2
    transmittance = admittance_ratio * abs(transmission) ** 2

    k0 = 2.0 * math.pi / WAVELENGTH_NM
    zero = 0.0 + 0.0j
    s_basis = (zero, 1.0 + 0.0j, zero)
    incident_direction_complex = (
        complex(sin_i),
        zero,
        complex(-cos_i),
    )
    reflected_direction_complex = (
        complex(sin_i),
        zero,
        complex(cos_i),
    )
    transmitted_direction_complex = (sin_t, zero, -cos_t)
    if kind == "s":
        incident_e_basis = s_basis
        reflected_e_basis = s_basis
        transmitted_e_basis = s_basis
    else:
        incident_e_basis = _cross(incident_direction_complex, s_basis)
        reflected_e_basis = _cross(reflected_direction_complex, s_basis)
        transmitted_e_basis = _cross(transmitted_direction_complex, s_basis)
    incident_wavevector = _scaled(k0 * n1, incident_direction_complex)
    reflected_wavevector = _scaled(k0 * n1, reflected_direction_complex)
    transmitted_wavevector = _scaled(k0 * n2, transmitted_direction_complex)
    incident_h_basis = _cross(_scaled(n1, incident_direction_complex), incident_e_basis)
    reflected_h_basis = _cross(
        _scaled(n1, reflected_direction_complex), reflected_e_basis
    )
    transmitted_h_basis = _cross(
        _scaled(n2, transmitted_direction_complex), transmitted_e_basis
    )
    upper_point_nm = (2.0, 3.0, 1.0)
    lower_point_nm = (2.0, 3.0, -1.0)
    incident_sample, incident_e, incident_h = _phase_sample(
        point_nm=upper_point_nm,
        wavevector_per_nm=incident_wavevector,
        electric_basis=incident_e_basis,
        magnetic_code_basis=incident_h_basis,
        amplitude=1.0 + 0.0j,
    )
    reflected_sample, reflected_e, reflected_h = _phase_sample(
        point_nm=upper_point_nm,
        wavevector_per_nm=reflected_wavevector,
        electric_basis=reflected_e_basis,
        magnetic_code_basis=reflected_h_basis,
        amplitude=reflection,
    )
    transmitted_sample, _transmitted_e, _transmitted_h = _phase_sample(
        point_nm=lower_point_nm,
        wavevector_per_nm=transmitted_wavevector,
        electric_basis=transmitted_e_basis,
        magnetic_code_basis=transmitted_h_basis,
        amplitude=transmission,
    )
    field_phase_samples = {
        "upper_point_nm": list(upper_point_nm),
        "lower_point_nm": list(lower_point_nm),
        "incident": incident_sample,
        "reflected": reflected_sample,
        "upper_total": {
            "electric_field": _complex_vector_json(_summed(incident_e, reflected_e)),
            "magnetic_code_field": _complex_vector_json(
                _summed(incident_h, reflected_h)
            ),
        },
        "transmitted": transmitted_sample,
    }

    return {
        "oracle_type": "complex_fresnel_interface",
        "amplitude_basis": "analytic_s_or_k_over_k0n_cross_s_electric_basis",
        "grazing_deg_from_surface": _stable_float(grazing_deg),
        "theta_deg_from_normal": _stable_float(theta_from_normal_deg(grazing_deg)),
        "polarization": kind,
        "n_incident": _complex_json(n1),
        "n_transmitted": _complex_json(n2),
        "cos_theta_transmitted": _complex_json(cos_t),
        "r": _complex_json(reflection),
        "t": _complex_json(transmission),
        "R_interface": _stable_float(reflectance),
        "T_into_substrate_at_interface": _stable_float(transmittance),
        "interface_power_closure": _stable_float(reflectance + transmittance),
        "normal_power_admittance_ratio": _stable_float(admittance_ratio),
        "field_phase_samples": field_phase_samples,
        "substrate_is_absorbing": bool(n2.imag > 0.0),
        "interpretation": (
            "T is downward flux crossing z=0; absorption occurs below the "
            "semi-infinite interface and is not a finite-volume A record."
        ),
    }


def fixture_contract() -> dict[str, Any]:
    """Return the frozen, JSON-safe Case090 microfixture semantics."""

    geometry = {
        "x_nm": [0.0, 10.0],
        "y_nm": [0.0, 10.0],
        "z_nm": [FIXTURE_Z_MIN_NM, FIXTURE_Z_MAX_NM],
        "period_x_nm": FIXTURE_PERIOD_X_NM,
        "period_y_nm": FIXTURE_PERIOD_Y_NM,
    }
    common = {
        "wavelength_nm": WAVELENGTH_NM,
        "phi_deg": 0.0,
        "boundary_xy": "double_floquet",
        "field_convention": "exp(i*k_dot_r) with exp(-i*omega*t)",
        "incident_side": "upper_air",
    }
    return {
        "fixture_a_air_box": {
            "fixture_id": "case090_fixture_a_air_box_10nm",
            "purpose": "analytic high-order Hcurl/Floquet algebra qualification",
            "geometry": dict(geometry),
            "material": {"uniform": "air", "n": _complex_json(AIR_INDEX)},
            "incidence": {
                **common,
                "primary_grazing_deg": 10.0,
                "polarizations": list(POLARIZATIONS),
            },
        },
        "fixture_b_flat_air_si": {
            "fixture_id": "case090_fixture_b_flat_air_si_10nm",
            "purpose": "analytic complex Fresnel and field-phase qualification",
            "geometry": {**geometry, "interface_z_nm": 0.0},
            "material": {
                "upper": {"label": "air", "n": _complex_json(AIR_INDEX)},
                "lower": {
                    "label": "current_Si_13p5nm",
                    "n": _complex_json(CURRENT_SI_INDEX),
                },
            },
            "incidence": {
                **common,
                "primary_grazing_deg": 10.0,
                "smoke_grazing_deg": [1.0, 5.0],
                "polarizations": list(POLARIZATIONS),
            },
            "outer_z_treatment": "existing_analytic_homogeneous_port_or_reviewed_fresnel_path",
        },
    }


def _requirement(
    fixture: str, grazing_deg: float, mesh_target_nm: float, mpi_size: int
) -> tuple[str, str]:
    if fixture == "fixture_a_air_box":
        return "required", "two_mesh_all_rank_plane_wave_contract"
    if grazing_deg == 10.0:
        return "required", "primary_fresnel_contract"
    if mesh_target_nm == 5.0 and mpi_size == 1:
        return "smoke", "lightweight_angle_entry_smoke"
    return "not_run", "lightweight_angle_smoke_scope"


def _core_gate_state(
    payload: Mapping[str, Any] | None,
) -> tuple[
    str,
    list[str],
    str | None,
    str | None,
    str | None,
    list[dict[str, int]],
    bool,
    bool,
]:
    if payload is None:
        return (
            "not_provided",
            ["core gate record was not provided"],
            None,
            None,
            None,
            [],
            False,
            False,
        )
    problems: list[str] = []
    if payload.get("schema_version") != CORE_GATE_SCHEMA_VERSION:
        problems.append("wrong core gate schema_version")
    if payload.get("record_type") != "high_order_floquet_core_gate_result":
        problems.append("wrong core gate record_type")
    if payload.get("case_id") != CASE_ID:
        problems.append("wrong core gate case_id")
    identity = payload.get("identity")
    if not isinstance(identity, Mapping):
        problems.append("missing core gate identity")
    else:
        if identity.get("is_pde_run") is not True:
            problems.append("core gate is not a PDE run")
        if identity.get("is_solver_pass") is not True:
            problems.append("core gate is not a solver pass")
        if identity.get("tracked_source_dirty") is not False:
            problems.append("core gate source is not clean")
        source_commit_full_sha = identity.get("source_commit_full_sha")
        if not isinstance(source_commit_full_sha, str) or not _FULL_SHA_RE.fullmatch(
            source_commit_full_sha
        ):
            problems.append("missing/invalid clean source_commit_full_sha")
            source_commit_full_sha = None
    if not isinstance(identity, Mapping):
        source_commit_full_sha = None
    gates = payload.get("gates")
    gate_by_name: dict[str, Mapping[str, Any]] = {}
    if isinstance(gates, list):
        gate_names = [
            str(gate.get("name")) for gate in gates if isinstance(gate, Mapping)
        ]
        if len(gate_names) != len(set(gate_names)):
            problems.append("core gate names must be unique")
        gate_by_name = {
            str(gate.get("name")): gate for gate in gates if isinstance(gate, Mapping)
        }
    else:
        problems.append("core gate gates must be a list")
    for name, limit in CORE_GATE_LIMITS.items():
        gate = gate_by_name.get(name)
        if gate is None:
            problems.append(f"missing core gate {name}")
            continue
        try:
            raw_observed = gate.get("observed")
            if isinstance(raw_observed, bool):
                raise TypeError
            observed = _finite(raw_observed, name=name)
        except (TypeError, ValueError):
            problems.append(f"invalid observed value for {name}")
            continue
        if gate.get("passed") is not True or observed < 0.0 or observed > limit:
            problems.append(f"failed core gate {name}")
    if payload.get("all_core_gates_passed") is not True:
        problems.append("all_core_gates_passed is not true")

    expected_pairs = {
        (degree, mpi_size) for degree in DEGREES for mpi_size in MPI_SIZES
    }
    observed_pairs: set[tuple[int, int]] = set()
    coverage = payload.get("coverage")
    if not isinstance(coverage, list):
        problems.append("core gate coverage must be a list")
    else:
        for index, item in enumerate(coverage):
            if not isinstance(item, Mapping):
                problems.append(f"core gate coverage {index} must be an object")
                continue
            if set(item) != {
                "degree",
                "mpi_size",
                "core_algebra_gates_passed",
            }:
                problems.append(f"core gate coverage {index} has wrong fields")
                continue
            degree = item.get("degree")
            mpi_size = item.get("mpi_size")
            pair = (degree, mpi_size)
            if (
                type(degree) is not int
                or type(mpi_size) is not int
                or pair not in expected_pairs
            ):
                problems.append(f"core gate coverage {index} has invalid p/MPI pair")
                continue
            if pair in observed_pairs:
                problems.append(f"duplicate core gate coverage pair {pair}")
                continue
            observed_pairs.add(pair)  # type: ignore[arg-type]
            if item.get("core_algebra_gates_passed") is not True:
                problems.append(f"failed core algebra coverage pair {pair}")
        if observed_pairs != expected_pairs:
            missing_pairs = sorted(expected_pairs - observed_pairs)
            extra_pairs = sorted(observed_pairs - expected_pairs)
            problems.append(
                "core gate coverage must be exactly p1-4 x MPI1/2/4; "
                f"missing={missing_pairs}, extra={extra_pairs}"
            )

    storage = payload.get("storage_contract")
    storage_vetoes_passed = False
    if not isinstance(storage, Mapping):
        problems.append("missing core gate storage_contract")
    elif set(storage) != {
        "sparse_distributed_constraints",
        "global_boundary_allgather_used",
        "dense_boundary_square_formed",
    }:
        problems.append("core gate storage_contract has wrong fields")
    else:
        storage_vetoes_passed = (
            storage.get("sparse_distributed_constraints") is True
            and storage.get("global_boundary_allgather_used") is False
            and storage.get("dense_boundary_square_formed") is False
        )
        if not storage_vetoes_passed:
            problems.append(
                "core gate storage veto failed: constraints must be sparse with "
                "no global boundary allgather or dense boundary square"
            )

    regression = payload.get("ordinary_regression")
    p1_p2_regression_passed = False
    if not isinstance(regression, Mapping):
        problems.append("missing core gate ordinary_regression")
    elif set(regression) != {
        "p1_existing_floquet_passed",
        "p2_existing_floquet_passed",
    }:
        problems.append("core gate ordinary_regression has wrong fields")
    else:
        p1_p2_regression_passed = (
            regression.get("p1_existing_floquet_passed") is True
            and regression.get("p2_existing_floquet_passed") is True
        )
        if not p1_p2_regression_passed:
            problems.append("ordinary p1/p2 Floquet regression did not pass")

    evidence_id = payload.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        problems.append("missing core gate evidence_id")
        evidence_id = None
    evidence_sha256 = payload.get("evidence_sha256")
    if not isinstance(evidence_sha256, str) or not _SHA256_RE.fullmatch(
        evidence_sha256
    ):
        problems.append("missing/invalid core gate evidence_sha256")
        evidence_sha256 = None
    validated_coverage = [
        {"degree": degree, "mpi_size": mpi_size}
        for degree, mpi_size in sorted(observed_pairs)
    ]
    status = "failed" if problems else "passed"
    return (
        status,
        problems,
        evidence_id,
        evidence_sha256,
        source_commit_full_sha,
        validated_coverage,
        storage_vetoes_passed,
        p1_p2_regression_passed,
    )


def build_execution_matrix(*, core_gate_passed: bool) -> list[dict[str, Any]]:
    """Build the complete p/mesh/MPI matrix without executing a PDE."""

    entries: list[dict[str, Any]] = []
    fixture_angles = {
        "fixture_a_air_box": (10.0,),
        "fixture_b_flat_air_si": GRAZING_ANGLES_DEG,
    }
    for fixture, angles in fixture_angles.items():
        for grazing_deg in angles:
            for polarization in POLARIZATIONS:
                for degree in DEGREES:
                    for mesh_target_nm in MESH_TARGETS_NM:
                        for mpi_size in MPI_SIZES:
                            requirement, rationale = _requirement(
                                fixture,
                                grazing_deg,
                                mesh_target_nm,
                                mpi_size,
                            )
                            if requirement == "not_run":
                                execution_status = "not_run_by_scope"
                                reason = rationale
                            elif core_gate_passed:
                                execution_status = "eligible_not_run"
                                reason = "planner_only_no_pde_execution"
                            else:
                                execution_status = "not_run_by_core_gate"
                                reason = "high_order_core_gate_not_passed"
                            mesh_label = str(mesh_target_nm).replace(".", "p")
                            entries.append(
                                {
                                    "matrix_id": (
                                        f"{fixture}_a{grazing_deg:g}_{polarization}_"
                                        f"p{degree}_h{mesh_label}_mpi{mpi_size}"
                                    ),
                                    "fixture": fixture,
                                    "grazing_deg_from_surface": grazing_deg,
                                    "theta_deg_from_normal": theta_from_normal_deg(
                                        grazing_deg
                                    ),
                                    "polarization": polarization,
                                    "degree": degree,
                                    "mesh_target_nm": mesh_target_nm,
                                    "mpi_size": mpi_size,
                                    "requirement": requirement,
                                    "requirement_rationale": rationale,
                                    "execution_status": execution_status,
                                    "result_identity": "not_run",
                                    "is_pde_run": False,
                                    "is_solver_pass": False,
                                    "not_run_reason": reason,
                                }
                            )
    return entries


def build_case090_record(
    *, core_gate_payload: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Build a deterministic analytic-oracle record and fail-closed run plan."""

    (
        gate_status,
        gate_problems,
        evidence_id,
        evidence_sha256,
        source_commit_full_sha,
        validated_coverage,
        storage_vetoes_passed,
        p1_p2_regression_passed,
    ) = _core_gate_state(core_gate_payload)
    matrix = build_execution_matrix(core_gate_passed=gate_status == "passed")
    requirement_counts = Counter(entry["requirement"] for entry in matrix)
    execution_counts = Counter(entry["execution_status"] for entry in matrix)
    air_oracles = [
        plane_wave_oracle(grazing_deg=angle, polarization=polarization)
        for angle in GRAZING_ANGLES_DEG
        for polarization in POLARIZATIONS
    ]
    fresnel_oracles = [
        fresnel_oracle(grazing_deg=angle, polarization=polarization)
        for angle in GRAZING_ANGLES_DEG
        for polarization in POLARIZATIONS
    ]
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "analytical_oracle_and_execution_plan",
        "case_id": CASE_ID,
        "status": "not_run",
        "ordinary_default_changed": False,
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_physical_qualification_record": False,
            "evidence_scope": "analytic_oracles_and_fail_closed_matrix_only",
        },
        "core_gate": {
            "status": gate_status,
            "evidence_id": evidence_id,
            "evidence_sha256": evidence_sha256,
            "source_commit_full_sha": source_commit_full_sha,
            "problems": gate_problems,
            "required_limits": dict(CORE_GATE_LIMITS),
            "required_degree_mpi_coverage_count": len(DEGREES) * len(MPI_SIZES),
            "validated_degree_mpi_coverage": validated_coverage,
            "storage_vetoes_passed": storage_vetoes_passed,
            "p1_p2_regression_passed": p1_p2_regression_passed,
        },
        "fixtures": fixture_contract(),
        "oracles": {
            "air_plane_waves": air_oracles,
            "flat_air_si_fresnel": fresnel_oracles,
        },
        "matrix_axes": {
            "degrees": list(DEGREES),
            "mesh_targets_nm": list(MESH_TARGETS_NM),
            "mpi_sizes": list(MPI_SIZES),
            "polarizations": list(POLARIZATIONS),
            "fresnel_grazing_angles_deg": list(GRAZING_ANGLES_DEG),
        },
        "matrix_summary": {
            "total": len(matrix),
            "requirements": dict(sorted(requirement_counts.items())),
            "execution_statuses": dict(sorted(execution_counts.items())),
        },
        "execution_matrix": matrix,
        "promotion_rule": (
            "This planner never emits a PDE pass. A separate clean PDE record "
            "must satisfy every core gate before any physical qualification."
        ),
    }
    validate_case090_record(record)
    return record


def validate_case090_json_schema(record: Mapping[str, Any]) -> None:
    """Validate every nested Case090 field with Draft 2020-12 JSON Schema."""

    if Draft202012Validator is None:
        raise RuntimeError(
            "Draft 2020-12 validation requires the optional 'jsonschema' package."
        )
    schema_path = _CASE_ROOT / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    failures = sorted(
        validator.iter_errors(dict(record)),
        key=lambda failure: tuple(str(part) for part in failure.absolute_path),
    )
    if failures:
        rendered: list[str] = []
        for failure in failures[:8]:
            location = ".".join(str(part) for part in failure.absolute_path)
            rendered.append(f"{location or '<root>'}: {failure.message}")
        if len(failures) > len(rendered):
            rendered.append(f"... {len(failures) - len(rendered)} more errors")
        raise ValueError(
            "Case090 JSON Schema validation failed: " + "; ".join(rendered)
        )


def validate_case090_record(record: Mapping[str, Any]) -> None:
    """Validate the safety-critical subset of the Case090 JSON schema."""

    errors: list[str] = []
    required_top = {
        "schema_version",
        "record_type",
        "case_id",
        "status",
        "ordinary_default_changed",
        "identity",
        "core_gate",
        "fixtures",
        "oracles",
        "matrix_axes",
        "matrix_summary",
        "execution_matrix",
        "promotion_rule",
    }
    missing = sorted(required_top - set(record))
    if missing:
        errors.append(f"missing top-level fields: {missing}")
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("wrong schema_version")
    if record.get("record_type") != "analytical_oracle_and_execution_plan":
        errors.append("wrong record_type")
    if record.get("case_id") != CASE_ID:
        errors.append("wrong case_id")
    if record.get("status") != "not_run":
        errors.append("oracle plan status must remain not_run")
    if record.get("ordinary_default_changed") is not False:
        errors.append("ordinary_default_changed must be false")
    identity = record.get("identity")
    if not isinstance(identity, Mapping):
        errors.append("identity must be an object")
    elif any(
        identity.get(name) is not False
        for name in (
            "is_pde_run",
            "is_solver_pass",
            "is_physical_qualification_record",
        )
    ):
        errors.append("oracle plan cannot claim PDE, solver, or qualification pass")
    matrix = record.get("execution_matrix")
    core_gate = record.get("core_gate")
    if not isinstance(core_gate, Mapping) or core_gate.get("status") not in {
        "not_provided",
        "failed",
        "passed",
    }:
        errors.append("core_gate has an invalid status")
    core_gate_passed = (
        isinstance(core_gate, Mapping) and core_gate.get("status") == "passed"
    )
    if core_gate_passed:
        if not isinstance(core_gate.get("evidence_id"), str):
            errors.append("passed core_gate is missing evidence_id")
        evidence_sha256 = core_gate.get("evidence_sha256")
        if not isinstance(evidence_sha256, str) or not _SHA256_RE.fullmatch(
            evidence_sha256
        ):
            errors.append("passed core_gate is missing evidence_sha256")
        source_sha = core_gate.get("source_commit_full_sha")
        if not isinstance(source_sha, str) or not _FULL_SHA_RE.fullmatch(source_sha):
            errors.append("passed core_gate is missing clean source SHA")
        coverage = core_gate.get("validated_degree_mpi_coverage")
        expected_coverage = [
            {"degree": degree, "mpi_size": mpi_size}
            for degree in DEGREES
            for mpi_size in MPI_SIZES
        ]
        if coverage != expected_coverage:
            errors.append("passed core_gate lacks p1-4 x MPI1/2/4 coverage")
        if core_gate.get("storage_vetoes_passed") is not True:
            errors.append("passed core_gate lacks sparse/no-gather/no-dense proof")
        if core_gate.get("p1_p2_regression_passed") is not True:
            errors.append("passed core_gate lacks p1/p2 regression proof")
    if not isinstance(matrix, list) or len(matrix) != 192:
        errors.append("execution_matrix must contain the complete 192-entry plan")
    else:
        ids: set[str] = set()
        for index, entry in enumerate(matrix):
            if not isinstance(entry, Mapping):
                errors.append(f"matrix entry {index} must be an object")
                continue
            matrix_id = entry.get("matrix_id")
            if not isinstance(matrix_id, str) or matrix_id in ids:
                errors.append(f"matrix entry {index} has an invalid/duplicate id")
            else:
                ids.add(matrix_id)
            if entry.get("requirement") not in {"required", "smoke", "not_run"}:
                errors.append(f"matrix entry {index} has invalid requirement")
            if entry.get("execution_status") not in {
                "not_run_by_scope",
                "not_run_by_core_gate",
                "eligible_not_run",
            }:
                errors.append(f"matrix entry {index} has invalid execution_status")
            if entry.get("result_identity") != "not_run":
                errors.append(f"matrix entry {index} forged a result identity")
            if entry.get("is_pde_run") is not False:
                errors.append(f"matrix entry {index} forged a PDE run")
            if entry.get("is_solver_pass") is not False:
                errors.append(f"matrix entry {index} forged a solver pass")
            requirement = entry.get("requirement")
            execution_status = entry.get("execution_status")
            expected_execution = (
                "not_run_by_scope"
                if requirement == "not_run"
                else "eligible_not_run"
                if core_gate_passed
                else "not_run_by_core_gate"
            )
            if execution_status != expected_execution:
                errors.append(
                    f"matrix entry {index} is inconsistent with its core gate/scope"
                )
        requirement_counts = Counter(entry.get("requirement") for entry in matrix)
        if requirement_counts != Counter({"required": 96, "smoke": 16, "not_run": 80}):
            errors.append("execution_matrix requirement counts changed")
    if errors:
        raise ValueError("Invalid Case090 oracle plan: " + "; ".join(errors))
    if Draft202012Validator is not None:
        validate_case090_json_schema(record)
