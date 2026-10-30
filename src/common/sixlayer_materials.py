"""Source-bound Task44 optical constants; stdlib only, no PDE or native imports.

This is an explicit, fixed 0.7 nm independent-atom TEST model, not measured
SiGe/SiO2 film data. Loading validates the complete document against its small
immutable raw-data bundle and reproduces every derived optical value.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_REL = "docs/task44_sixlayer_surrogate_0p7nm/materials_sources"
DEFAULT_PATH = ROOT / "input/materials/task44_0p7nm.json"
BASE_SHA = "db790f92a186988c5147f1828d15c07034e7c430"
SOURCE_HASHES = {
    "si.nff": "2bbd2aef0292aa392a61942b1c401171b5bc30bb77ab1cab9c08b6264048019a",
    "ge.nff": "269103885de8c55eab88e3d3fc17286cf49d5e8ad664f720838f96061296637d",
    "o.nff": "adb1540b11008383aaef0b8c4f5fb1a2bc5df14f3717ac4d58fc54fff92ba6cb",
    "base_si_material_identity.json": "5faedf276aba2918cc399c018936964b059127f135e24ea2bf2ba493e3d9876b",
    "density_source_observation.json": "b4da182d9133f3849f4b382fdd371be112950d8221cff64f6689d389b9e077cf",
}
MOLAR_MASSES = {"Si": 28.0855, "Ge": 72.64, "O": 15.9994}
HC_EV_NM = 1239.8419843320025
AVOGADRO = 6.02214076e23
ELECTRON_RADIUS_M = 2.8179403205e-15
LAMBDA_NM = 0.7
TIME_CONVENTION = "exp(i*k dot r) exp(-i*omega*t)"


def _canonical(value):
    """Exact JSON types; reject arbitrary objects, nonfinite values and bool numbers."""
    def check(v):
        if v is None or type(v) in (str, bool, int):
            return
        if type(v) is float:
            if not math.isfinite(v):
                raise ValueError("nonfinite material value")
            return
        if type(v) is list:
            for x in v:
                check(x)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for x in v.values():
                check(x)
            return
        raise ValueError("material identity must contain only exact JSON types")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _sha(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _read_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    def bad_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    _canonical(value)
    return value


def _source_bytes(name, source_dir):
    path = Path(source_dir) / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"source must be an existing regular file: {name}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if name in SOURCE_HASHES and digest != SOURCE_HASHES[name]:
        raise ValueError(f"immutable source SHA mismatch: {name}")
    return raw, {"path": f"{SOURCE_REL}/{name}", "bytes": len(raw), "sha256": digest}


def interpolate_scattering_factor(raw, energy_eV):
    """Linear-in-E interpolation of f1/f2, never extrapolation.

    The fixed caller additionally binds the exact target brackets; this helper
    does NOT certify arbitrary interpolation across an absorption threshold.
    """
    if type(energy_eV) not in (float, int) or not math.isfinite(energy_eV):
        raise ValueError("finite photon energy required")
    rows = []
    for line, text in enumerate(raw.decode("ascii").splitlines(), 1):
        if line == 1:
            if text.split() != ["E(eV)", "f1", "f2"]:
                raise ValueError("unexpected CXRO header")
            continue
        if not text.strip():
            continue
        values = [float(x) for x in text.split()]
        if len(values) != 3 or not all(math.isfinite(x) for x in values):
            raise ValueError("invalid scattering-factor row")
        if values[0] <= 0 or values[2] < 0:
            raise ValueError("invalid energy or absorption factor")
        if rows and values[0] <= rows[-1]["energy_eV"]:
            raise ValueError("energies must be strictly increasing")
        rows.append(dict(zip(("energy_eV", "f1", "f2"), values), line=line))
    if len(rows) < 2 or not rows[0]["energy_eV"] <= energy_eV <= rows[-1]["energy_eV"]:
        raise ValueError("extrapolation is forbidden")
    index = bisect.bisect_right([r["energy_eV"] for r in rows], energy_eV) - 1
    index = min(index, len(rows) - 2)
    low, high = rows[index:index + 2]
    if min(low["f1"], high["f1"]) <= -9999:
        raise ValueError("undefined CXRO f1 cannot be interpolated")
    t = (energy_eV - low["energy_eV"]) / (high["energy_eV"] - low["energy_eV"])
    return {"energy_eV": energy_eV, "bracket": [low, high], "fraction": t,
            "f1": low["f1"] + t * (high["f1"] - low["f1"]),
            "f2": low["f2"] + t * (high["f2"] - low["f2"]),
            "interpolation": "linear_in_photon_energy_for_f1_and_f2", "extrapolated": False}


def _derive(stoichiometry, density_kg_m3, factors):
    mass = sum(amount * MOLAR_MASSES[element] for element, amount in stoichiometry.items())
    number_density = density_kg_m3 / (mass / 1000.0) * AVOGADRO
    f1 = sum(amount * factors[element]["f1"] for element, amount in stoichiometry.items())
    f2 = sum(amount * factors[element]["f2"] for element, amount in stoichiometry.items())
    prefactor = ELECTRON_RADIUS_M * (LAMBDA_NM * 1e-9)**2 * number_density / (2.0 * math.pi)
    delta, beta = prefactor * f1, prefactor * f2
    n = complex(1.0 - delta, beta)
    eps = n * n
    if not all(math.isfinite(x) for x in (delta, beta, n.real, n.imag, eps.real, eps.imag)):
        raise ValueError("nonfinite optical calculation")
    if beta <= 0 or eps.imag <= 0:
        raise ValueError("passive loss required with exp(-i*omega*t)")
    return {"molar_mass_g_mol": mass, "formula_unit_number_density_m3": number_density,
            "f1_sum": f1, "f2_sum": f2, "delta": delta, "beta": beta,
            "n": {"real": n.real, "imag": n.imag},
            "epsilon_r": {"real": eps.real, "imag": eps.imag}, "mu_r": 1.0}


def sixlayer_order():
    """Bottom to top; substrate separately uses the SAME Si identity."""
    return ("Si", "SiGe", "Si", "SiGe", "Si", "SiO2")


def derive_material_document(source_dir=None):
    """Reproduce the fixed document solely from the bundled source data."""
    source_dir = Path(source_dir) if source_dir is not None else ROOT / SOURCE_REL
    source_records, factors = {}, {}
    for element in MOLAR_MASSES:
        raw, record = _source_bytes(element.lower() + ".nff", source_dir)
        record.update(url=f"https://henke.lbl.gov/optical_constants/sf/{element.lower()}.nff",
                      retrieved_date_utc="2026-10-30")
        source_records[element] = record
        factors[element] = interpolate_scattering_factor(raw, HC_EV_NM / LAMBDA_NM)
    expected_brackets = {"Si": [1756.82, 1785.24], "Ge": [1752.89, 1781.24], "O": [1752.89, 1781.24]}
    for element, energies in expected_brackets.items():
        if [r["energy_eV"] for r in factors[element]["bracket"]] != energies:
            raise ValueError("fixed 0.7 nm bracket changed")
    raw, base_record = _source_bytes("base_si_material_identity.json", source_dir)
    base = _read_json(raw)
    density_raw, density_record = _source_bytes("density_source_observation.json", source_dir)
    density_observation = _read_json(density_raw)
    if (density_observation["formula_transcription"] != "rho_g_cm3 = 2.329 + 3.493*x - 0.499*x*x"
            or density_observation["x"] != 0.3 or density_observation["temperature_K"] != 300
            or density_observation["original_html_sha256"] is not None):
        raise ValueError("density observation contract changed")
    base_record.update(repository="Rookie1234567/MyFEniCS", commit=BASE_SHA,
                       original_path="docs/task40extra_0p7nm_engineering/outcomes/records/material_identity.json")
    x = 0.3
    density_alloy = (2.329 + 3.493 * x - 0.499 * x * x) * 1000.0
    definitions = {
        "Si": ({"Si": 1.0}, 2329.1, "INHERITED_SOURCE_VERIFIED_ELEMENTAL_DERIVATION"),
        "SiGe": ({"Si": 0.7, "Ge": 0.3}, density_alloy, "DERIVED_INDEPENDENT_ATOM_ALLOY_NOT_MEASURED"),
        "SiO2": ({"Si": 1.0, "O": 2.0}, 2200.0, "DERIVED_INDEPENDENT_ATOM_COMPOUND_NOT_MEASURED"),
    }
    materials = {}
    for name, (stoichiometry, density, status) in definitions.items():
        calculation = _derive(stoichiometry, density, factors)
        if name == "Si":
            inherited = base["calculation"]
            if (calculation["n"] != {k: inherited["solver_refractive_index"][k] for k in ("real", "imag")}
                    or calculation["epsilon_r"] != inherited["solver_epsilon_r"]):
                raise ValueError("Si must remain exactly equal to the frozen base, not a new interpolation")
        amount_sum = sum(stoichiometry.values())
        item = {"status": status, "stoichiometry": stoichiometry,
                "atomic_fractions": {k: v / amount_sum for k, v in stoichiometry.items()},
                "density_kg_m3": density, "calculation": calculation,
                "element_source_sha256": {k: source_records[k]["sha256"] for k in stoichiometry}}
        if name == "Si":
            item["density_basis"] = "Inherited 2.3291 g/cm^3 at 20 C; do not replace with alloy endpoint 2.329"
            item["inherited_material_model_sha256"] = base["material_model_sha256"]
        elif name == "SiGe":
            item["density_basis"] = "Declared 300 K bulk random-alloy test assumption; relaxed, not sample measured"
        else:
            item["density_basis"] = "Task44 explicitly specified amorphous SiO2 test density 2.2 g/cm^3"
        item["identity_sha256"] = _sha(item)
        materials[name] = item
    return {
        "schema": "task44.sixlayer_materials.v1", "wavelength_nm": LAMBDA_NM,
        "photon_energy_eV": HC_EV_NM / LAMBDA_NM,
        "units": {"wavelength": "nm", "energy": "eV", "density": "kg/m^3", "molar_mass": "g/mol"},
        "convention": {"solver_phase": TIME_CONVENTION, "n": "1-delta+i*beta", "epsilon_r": "n*n",
                       "cxro_n": "1-delta-i*beta", "conversion": "complex_conjugate_of_CXRO_n",
                       "passivity": "beta>0 and Im(epsilon_r)>0", "mu_r": 1.0},
        "constants": {"hc_eV_nm": HC_EV_NM, "avogadro_mol_inverse": AVOGADRO,
                      "classical_electron_radius_m": ELECTRON_RADIUS_M, "molar_masses_g_mol": dict(MOLAR_MASSES)},
        "derivation": {"number_density": "rho_kg_m3/(M_formula_g_mol/1000)*N_A",
                       "delta_beta": "r_e*lambda_m^2*N_formula/(2*pi) * sum(stoich_i*f1_or_f2_i)",
                       "alloy_composition": "atomic fractions, NOT mass fractions or linear n/epsilon mixing",
                       "SiO2_number_density": "formula units per m^3; total atomic density is three times this",
                       "interpolation": "linear in energy for both f1 and f2, inherited Si convention; no extrapolation"},
        "layer_order_bottom_to_top": list(sixlayer_order()), "substrate_material": "Si",
        "external_air": {"n": {"real": 1.0, "imag": 0.0}, "epsilon_r": {"real": 1.0, "imag": 0.0}},
        "materials": materials, "atomic_scattering_factors": factors,
        "sources": {"atomic_tables": source_records, "inherited_Si": base_record,
                    "alloy_density_observation": density_record},
        "reference_urls": {
            "atomic_model": "https://henke.lbl.gov/optical_constants/intro.html",
            "CXRO_sign": "https://henke.lbl.gov/optical_constants/pert_form.html",
            "alloy_density": density_observation["url"],
            "Ge_molar_mass": "https://webbook.nist.gov/cgi/cbook.cgi?ID=C7440564&Mask=20",
            "O2_molar_mass_divide_by_two": "https://webbook.nist.gov/cgi/cbook.cgi?ID=C7782447&Mask=20",
            "Si_molar_mass": base["source"]["molar_mass_url"],
            "Si_density": base["source"]["density_reference_url"]},
        "limitations": [
            "Derived independent-atom model, not measured SiGe or amorphous-SiO2 optical constants.",
            "No sample-specific density, strain, oxidation, intermixing, roughness or bonding correction.",
            "Si target is below the tabulated 1838.8/1839.0 eV K-edge; its bracket does not cross the edge; this does not quantify chemical-state errors.",
            "No statistical error bar or film-accuracy guarantee; printed digits are reproducibility, not physical precision.",
            "Sub-nanometre continuum layer geometry is a numerical surrogate-method test, not validated atomistic fabrication physics.",
            "The Ge/O molar masses are explicitly frozen NIST WebBook values, not a claim to latest isotope-specific weights."]}


def validate_material_document(document, source_dir=None):
    expected = derive_material_document(source_dir)
    if _canonical(document) != _canonical(expected):
        raise ValueError("material document differs from the complete fixed source-derived contract")
    return expected


def load_sixlayer_materials(path=None):
    """Return complex maps plus exact JSON identity and document/file SHA256."""
    path = DEFAULT_PATH if path is None else Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("material document must be a regular existing file")
    raw = path.read_bytes()
    identity = validate_material_document(_read_json(raw))
    n, eps = {"air": 1.0 + 0.0j}, {"air": 1.0 + 0.0j}
    for name, material in identity["materials"].items():
        calc = material["calculation"]
        n[name] = complex(**calc["n"])
        eps[name] = complex(**calc["epsilon_r"])
    return {"refractive_indices": n, "epsilon_r": eps, "identity": identity,
            "identity_sha256": _sha(identity), "file_sha256": hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Create the material JSON; refuse an existing file")
    args = parser.parse_args()
    if args.write:
        with DEFAULT_PATH.open("x", encoding="utf-8") as stream:
            json.dump(derive_material_document(), stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    result = load_sixlayer_materials()
    print(json.dumps({k: result[k] for k in ("identity_sha256", "file_sha256")}, sort_keys=True))


if __name__ == "__main__":
    main()
