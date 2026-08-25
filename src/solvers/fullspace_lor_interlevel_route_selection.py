"""R0 contract primitives for the prospective interlevel route selection.

This module contains only frozen contract constants and a small pure-data gate
for the future Route A spectrum.  It does not build a mesh, matrix, transfer,
MPI object, or solver.
"""

from __future__ import annotations

import math
from typing import Any


SCHEMA = "task038.full3d.interlevel-route-selection.v1"
ROUTE_ORDER = ("A", "B", "C")
ROUTE_A = "A"
ROUTE_B = "B"
ROUTE_C = "C"

ROUTE_A_RANK = 144
HERMITIAN_LIMIT = 1.0e-12
ENDPOINT_RESIDUAL_LIMIT = 1.0e-10
LAMBDA_MIN_LIMIT = 0.10
LAMBDA_MAX_LIMIT = 10.0
CONDITION_LIMIT = 100.0
PROBE_COUNT = 6
PROBE_MIN = 0.10
PROBE_MAX = 10.0
PROBE_NAMES = (
    "random",
    "gradient",
    "curl",
    "checkerboard",
    "physical_component_derived",
    "r3_long_tail_derived",
)
ADJOINT_LIMIT = 1.0e-12
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
CONDITION_CLOSE_TOL = 1.0e-12
MATERIAL_CLASS_REQUIRED_FIELDS = (
    "class_digest",
    "material_coefficient_identity",
    "geometry_jacobian_identity",
    "rank",
    "sigma_min",
    "sigma_max",
    "hermitian_defect_b3",
    "hermitian_defect_g63",
    "minimum_eigenvalue_b3",
    "minimum_eigenvalue_g63",
    "lambda_min",
    "lambda_max",
    "spectral_condition",
    "endpoint_residual_min",
    "endpoint_residual_max",
    "finite",
)

ROUTE_A_REQUIRED_FIELDS = (
    "rank",
    "hermitian_defect_b3",
    "hermitian_defect_g63",
    "strict_spd_b3",
    "strict_spd_g63",
    "minimum_eigenvalue_b3",
    "minimum_eigenvalue_g63",
    "endpoint_residual_min",
    "endpoint_residual_max",
    "lambda_min",
    "lambda_max",
    "condition",
    "finite",
    "adjoint_work_relative",
    "linearity_relative",
    "repeat_relative",
    "input_unchanged",
    "phase_once",
    "probes",
)


def _finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def check_route_a_measurement(facts: Any) -> dict[str, Any]:
    """Recompute the fixed Route A gates from a raw measurement mapping.

    The result separates malformed evidence (``contract_errors``) from a
    well-formed measurement that misses a numerical gate (``gate_failures``).
    No value is defaulted and no route B/C operation is performed here.
    """

    contract_errors: list[str] = []
    gate_failures: list[str] = []
    derived_condition: float | None = None
    if not isinstance(facts, dict):
        return {
            "passed": False,
            "contract_errors": ["route A measurement must be an object"],
            "gate_failures": [],
        }
    for key in ROUTE_A_REQUIRED_FIELDS:
        if key not in facts:
            contract_errors.append(f"missing route A field: {key}")
    if contract_errors:
        return {
            "passed": False,
            "contract_errors": contract_errors,
            "gate_failures": gate_failures,
        }

    if type(facts["rank"]) is not int:
        contract_errors.append("rank must be an integer")
    elif facts["rank"] != ROUTE_A_RANK:
        gate_failures.append(f"rank != {ROUTE_A_RANK}")

    for name in ("hermitian_defect_b3", "hermitian_defect_g63"):
        value = facts[name]
        if not _finite_number(value):
            contract_errors.append(f"{name}: finite number required")
        elif float(value) > HERMITIAN_LIMIT:
            gate_failures.append(f"{name} exceeds limit")
    for name in ("endpoint_residual_min", "endpoint_residual_max"):
        if not _finite_number(facts[name]):
            contract_errors.append(f"{name}: finite number required")
        elif float(facts[name]) > ENDPOINT_RESIDUAL_LIMIT:
            gate_failures.append(f"{name} exceeds limit")
    for name in ("minimum_eigenvalue_b3", "minimum_eigenvalue_g63"):
        if not _finite_number(facts[name]):
            contract_errors.append(f"{name}: finite number required")
        elif float(facts[name]) <= 0.0:
            gate_failures.append(f"{name} must be positive")

    for name, lower, upper in (
        ("lambda_min", LAMBDA_MIN_LIMIT, None),
        ("lambda_max", None, LAMBDA_MAX_LIMIT),
        ("condition", None, None),
    ):
        value = facts[name]
        if not _finite_number(value):
            contract_errors.append(f"{name}: finite number required")
        elif lower is not None and float(value) < lower:
            gate_failures.append(f"{name} < {lower}")
        elif upper is not None and float(value) > upper:
            gate_failures.append(f"{name} > {upper}")
    lambda_min = facts["lambda_min"]
    lambda_max = facts["lambda_max"]
    reported_condition = facts["condition"]
    if _finite_number(lambda_min) and _finite_number(lambda_max) and _finite_number(reported_condition):
        if float(lambda_min) <= 0.0:
            gate_failures.append("lambda_min must be positive for derived condition")
        else:
            derived_condition = float(lambda_max) / float(lambda_min)
            if derived_condition > CONDITION_LIMIT:
                gate_failures.append("derived condition > 100")
            if not math.isclose(
                float(reported_condition),
                derived_condition,
                rel_tol=CONDITION_CLOSE_TOL,
                abs_tol=CONDITION_CLOSE_TOL,
            ):
                contract_errors.append("reported condition does not match lambda ratio")

    for name in ("strict_spd_b3", "strict_spd_g63", "finite", "input_unchanged", "phase_once"):
        if type(facts[name]) is not bool:
            contract_errors.append(f"{name} must be boolean")
        elif not facts[name]:
            gate_failures.append(f"{name} is false")
    for name, limit in (
        ("adjoint_work_relative", ADJOINT_LIMIT),
        ("linearity_relative", LINEARITY_LIMIT),
        ("repeat_relative", REPEAT_LIMIT),
    ):
        value = facts[name]
        if not _finite_number(value):
            contract_errors.append(f"{name}: finite number required")
        elif float(value) > limit:
            gate_failures.append(f"{name} exceeds limit")

    probes = facts["probes"]
    if not isinstance(probes, list) or len(probes) != PROBE_COUNT:
        contract_errors.append(f"probes must contain exactly {PROBE_COUNT} entries")
    else:
        names: list[str] = []
        for index, probe in enumerate(probes):
            if not isinstance(probe, dict):
                contract_errors.append(f"probe {index} must be an object")
                continue
            for key in ("name", "q", "finite", "input_unchanged"):
                if key not in probe:
                    contract_errors.append(f"probe {index} missing {key}")
            if not all(key in probe for key in ("name", "q", "finite", "input_unchanged")):
                continue
            if type(probe["name"]) is not str:
                contract_errors.append(f"probe {index} name must be a string")
            else:
                names.append(probe["name"])
            if not _finite_number(probe["q"]):
                contract_errors.append(f"probe {index} q must be finite")
            elif not PROBE_MIN <= float(probe["q"]) <= PROBE_MAX:
                gate_failures.append(f"probe {index} q outside [{PROBE_MIN}, {PROBE_MAX}]")
            for key in ("finite", "input_unchanged"):
                if type(probe[key]) is not bool:
                    contract_errors.append(f"probe {index} {key} must be boolean")
                elif not probe[key]:
                    gate_failures.append(f"probe {index} {key} is false")
        if len(names) == PROBE_COUNT and names != list(PROBE_NAMES):
            contract_errors.append("probe names/order do not match frozen identities")

    return {
        "passed": not contract_errors and not gate_failures,
        "contract_errors": contract_errors,
        "gate_failures": gate_failures,
        "derived_condition": derived_condition,
    }


def next_route_after_route_a(route_a_passed: bool) -> str:
    """Return the frozen next-stage decision without running that stage."""

    if type(route_a_passed) is not bool:
        raise TypeError("route_a_passed must be bool")
    return "R2" if route_a_passed else ROUTE_B
