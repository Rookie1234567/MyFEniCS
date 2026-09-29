"""Offline, versioned Si constants with only explicitly authorized aliases."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

TABLE_ID = "SI_OPTICAL_CONSTANTS_USER_20260929_V1"
CANONICAL_PATH = (
    Path(__file__).resolve().parents[2] / "input/materials/si_optical_constants_v1.json"
)


@dataclass(frozen=True)
class MaterialSelection:
    n: complex
    epsilon: complex
    mu: complex
    provenance: dict


def decimal_conversion(delta, beta):
    """Exact decimal checks; runtime uses the full complex square."""
    with localcontext() as context:
        context.prec = 50
        real = Decimal(1) - Decimal(delta)
        imag = Decimal(beta)
        return real, imag, real * real - imag * imag, Decimal(2) * real * imag


def load_si_optical_constants(wavelength_nm, path=None):
    path = CANONICAL_PATH if path is None else Path(path)
    raw = path.read_bytes()
    table = json.loads(raw)
    if (
        table["material_table_id"] != TABLE_ID
        or table["time_convention"] != "exp(-i omega t)"
    ):
        raise ValueError("material table ID/time convention mismatch")
    try:
        query = Decimal(str(wavelength_nm))
    except InvalidOperation as error:
        raise ValueError("invalid vacuum wavelength") from error
    if not query.is_finite() or query <= 0:
        raise ValueError("invalid vacuum wavelength")
    matches = []
    for item in table["entries"]:
        labels = [item["nominal_wavelength_nm"], *item["accepted_source_aliases_nm"]]
        if query in [Decimal(label) for label in labels]:
            matches.append(item)
    if len(matches) != 1:
        raise ValueError(
            f"unregistered wavelength {wavelength_nm}; no interpolation or nearest matching"
        )
    item = matches[0]
    checks = decimal_conversion(item["delta"], item["beta"])
    stored = (*item["n_decimal"], *item["epsilon_decimal"])
    if checks != tuple(Decimal(value) for value in stored) or checks[1] <= 0:
        raise ValueError("material conversion/sign integrity failure")
    n = complex(float(checks[0]), float(checks[1]))
    epsilon = n * n
    tolerance = 16 * 2.220446049250313e-16 * max(1, abs(epsilon))
    if abs(epsilon - complex(float(checks[2]), float(checks[3]))) > tolerance:
        raise ValueError("complex128 material conversion mismatch")
    return MaterialSelection(
        n=n,
        epsilon=epsilon,
        mu=1 + 0j,
        provenance={
            "status": "MATERIAL_READY_USER_SUPPLIED",
            "material_table_id": table["material_table_id"],
            "canonical_path": str(path.resolve()),
            "material_table_sha256": hashlib.sha256(raw).hexdigest(),
            "query_wavelength_nm": str(wavelength_nm),
            "nominal_wavelength_nm": item["nominal_wavelength_nm"],
            "source_wavelength_nm": item["source_wavelength_nm"],
            "delta": item["delta"],
            "beta": item["beta"],
            "n_decimal": item["n_decimal"],
            "epsilon_decimal": item["epsilon_decimal"],
            "source_kind": item["source_kind"],
            "source": item["source"],
            "alias_reason": item["alias_reason"],
            "time_convention": table["time_convention"],
            "external_dataset_version": table["external_dataset_version"],
            "n_loaded": [n.real, n.imag],
            "epsilon_loaded": [epsilon.real, epsilon.imag],
            "air_n": [1.0, 0.0],
            "mu_r": [1.0, 0.0],
        },
    )
