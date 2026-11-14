"""Wavelength-specific Si optical identity for the workstation PSTDDM pilot.

This module uses the repository's archived CXRO/Henke ``si.nff`` bytes. It is
stdlib-only and performs no mesh construction or native-library imports.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "docs/task44_sixlayer_surrogate_0p7nm/materials_sources/si.nff"
SOURCE_SHA256 = "2bbd2aef0292aa392a61942b1c401171b5bc30bb77ab1cab9c08b6264048019a"
HC_EV_NM = 1239.8419843320025
AVOGADRO_PER_MOL = 6.02214076e23
ELECTRON_RADIUS_M = 2.8179403205e-15
SI_DENSITY_KG_M3 = 2329.1
SI_MOLAR_MASS_G_MOL = 28.0855
SI_K_EDGE_EV = 1839.0
TIME_CONVENTION = "exp(i*k dot r) exp(-i*omega*t)"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _read_table(path: Path) -> tuple[bytes, list[dict[str, float | int]]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("CXRO Si source must be a regular, non-symlink file")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"CXRO Si source SHA mismatch: {digest}")
    rows: list[dict[str, float | int]] = []
    for line_number, line in enumerate(raw.decode("ascii").splitlines(), start=1):
        if line_number == 1:
            if line.split() != ["E(eV)", "f1", "f2"]:
                raise ValueError("unexpected CXRO Si table header")
            continue
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError(f"invalid CXRO Si row at line {line_number}")
        energy, f1, f2 = map(float, fields)
        if not all(math.isfinite(value) for value in (energy, f1, f2)):
            raise ValueError(f"nonfinite CXRO Si row at line {line_number}")
        if energy <= 0.0 or f2 < 0.0 or (rows and energy <= rows[-1]["energy_eV"]):
            raise ValueError(f"invalid or unordered CXRO Si row at line {line_number}")
        rows.append({"line": line_number, "energy_eV": energy, "f1": f1, "f2": f2})
    if len(rows) < 2:
        raise ValueError("CXRO Si source has fewer than two data rows")
    return raw, rows


def derive_si_optical_identity(wavelength_nm: float, *, source_path: Path | None = None) -> dict[str, object]:
    """Derive passive complex ``n`` from linearly interpolated CXRO f1/f2.

    Interpolation is linear in photon energy and is permitted only between a
    real adjacent-row bracket. It refuses extrapolation, undefined f1 values,
    and a bracket that crosses the tabulated Si K edge.
    """
    wavelength_nm = float(wavelength_nm)
    if not math.isfinite(wavelength_nm) or wavelength_nm <= 0.0:
        raise ValueError("wavelength must be finite and positive")
    path = SOURCE_PATH if source_path is None else Path(source_path)
    raw, rows = _read_table(path)
    energy = HC_EV_NM / wavelength_nm
    energies = [float(row["energy_eV"]) for row in rows]
    if not energies[0] <= energy <= energies[-1]:
        raise ValueError("target photon energy is outside the archived table; extrapolation is forbidden")
    lower_index = min(max(bisect.bisect_right(energies, energy) - 1, 0), len(rows) - 2)
    low, high = rows[lower_index:lower_index + 2]
    low_e, high_e = float(low["energy_eV"]), float(high["energy_eV"])
    if (low_e < SI_K_EDGE_EV <= high_e) or float(low["f1"]) <= -9999.0 or float(high["f1"]) <= -9999.0:
        raise ValueError("Si interpolation bracket is undefined or crosses the 1839 eV K edge")
    fraction = (energy - low_e) / (high_e - low_e)
    f1 = float(low["f1"]) + fraction * (float(high["f1"]) - float(low["f1"]))
    f2 = float(low["f2"]) + fraction * (float(high["f2"]) - float(low["f2"]))
    number_density = SI_DENSITY_KG_M3 / (SI_MOLAR_MASS_G_MOL / 1000.0) * AVOGADRO_PER_MOL
    prefactor = (ELECTRON_RADIUS_M * (wavelength_nm * 1.0e-9) ** 2
                 * number_density / (2.0 * math.pi))
    delta, beta = prefactor * f1, prefactor * f2
    index = complex(1.0 - delta, beta)
    epsilon = index * index
    if beta <= 0.0 or epsilon.imag <= 0.0:
        raise ValueError("derived Si must be passive for the exp(-i omega t) convention")
    raw_sha = hashlib.sha256(raw).hexdigest()
    identity: dict[str, object] = {
        "schema": "pstddm.si_optical_identity.v1",
        "source": {"path": "docs/task44_sixlayer_surrogate_0p7nm/materials_sources/si.nff",
                   "sha256": raw_sha, "bytes": len(raw)},
        "wavelength_nm": wavelength_nm, "photon_energy_eV": energy,
        "bracket_rows": [low, high], "interpolation_fraction": fraction,
        "interpolation": "linear_in_photon_energy_for_f1_and_f2",
        "extrapolated": False, "edge_check_eV": SI_K_EDGE_EV,
        "f1": f1, "f2": f2,
        "density_kg_m3": SI_DENSITY_KG_M3,
        "molar_mass_g_mol": SI_MOLAR_MASS_G_MOL,
        "formula": "delta+i*beta = r_e*lambda_m^2*N_Si/(2*pi)*(f1+i*f2); n=1-delta+i*beta",
        "time_convention": TIME_CONVENTION,
        "n": [float(index.real), float(index.imag)],
        "epsilon_r": [float(epsilon.real), float(epsilon.imag)],
        "mu_r": [1.0, 0.0],
    }
    identity["identity_sha256"] = hashlib.sha256(_canonical(identity)).hexdigest()
    return identity
