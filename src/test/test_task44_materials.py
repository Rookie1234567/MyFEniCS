"""Task44 material arithmetic and fail-closed source controls (stdlib only)."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from src.common import sixlayer_materials as material


class TestTask44Materials(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = material.derive_material_document()

    def test_complete_document_and_loader(self):
        loaded = material.load_sixlayer_materials()
        self.assertEqual(loaded["identity"], self.document)
        self.assertEqual(set(loaded["epsilon_r"]), {"air", "Si", "SiGe", "SiO2"})
        self.assertEqual(material.sixlayer_order(), ("Si", "SiGe", "Si", "SiGe", "Si", "SiO2"))
        self.assertEqual(loaded["file_sha256"], hashlib.sha256(material.DEFAULT_PATH.read_bytes()).hexdigest())

    def test_inherited_Si_exact(self):
        loaded = material.load_sixlayer_materials()
        self.assertEqual(loaded["refractive_indices"]["Si"], complex(0.9998851703688496, 4.3236152269189515e-06))
        self.assertEqual(loaded["epsilon_r"]["Si"], complex(0.9997703539048498, 8.646237495554417e-06))

    def test_energy_and_independent_linear_interpolation(self):
        doc = self.document
        self.assertEqual(doc["photon_energy_eV"], 1771.2028347600037)
        for element, record in doc["atomic_scattering_factors"].items():
            a, b = record["bracket"]
            self.assertLess(a["energy_eV"], doc["photon_energy_eV"])
            self.assertLess(doc["photon_energy_eV"], b["energy_eV"])
            t = (doc["photon_energy_eV"] - a["energy_eV"]) / (b["energy_eV"] - a["energy_eV"])
            for field in ("f1", "f2"):
                self.assertEqual(record[field], a[field] + t * (b[field] - a[field]), element)
        self.assertLess(doc["atomic_scattering_factors"]["Si"]["bracket"][1]["energy_eV"], 1838.8)

    def test_mixture_uses_atomic_fraction_and_formula_unit_density(self):
        alloy = self.document["materials"]["SiGe"]
        silica = self.document["materials"]["SiO2"]
        self.assertEqual(alloy["stoichiometry"], {"Si": 0.7, "Ge": 0.3})
        self.assertEqual(alloy["atomic_fractions"], alloy["stoichiometry"])
        self.assertAlmostEqual(alloy["density_kg_m3"], 3331.99, places=10)
        self.assertEqual(alloy["calculation"]["molar_mass_g_mol"], 0.7 * 28.0855 + 0.3 * 72.64)
        self.assertEqual(silica["stoichiometry"], {"Si": 1.0, "O": 2.0})
        self.assertEqual(silica["atomic_fractions"], {"Si": 1 / 3, "O": 2 / 3})
        self.assertEqual(silica["calculation"]["molar_mass_g_mol"], 28.0855 + 2 * 15.9994)
        for row in (alloy, silica):
            c = row["calculation"]
            self.assertEqual(c["formula_unit_number_density_m3"], row["density_kg_m3"] / (c["molar_mass_g_mol"] / 1000) * material.AVOGADRO)

    def test_independent_optical_formula_passivity_and_distinct_materials(self):
        loaded = material.load_sixlayer_materials()
        self.assertEqual(len(set(loaded["refractive_indices"].values())), 4)
        for name, m in self.document["materials"].items():
            c = m["calculation"]
            factors = self.document["atomic_scattering_factors"]
            f = sum(v * complex(factors[e]["f1"], factors[e]["f2"]) for e, v in m["stoichiometry"].items())
            prefactor = material.ELECTRON_RADIUS_M * (0.7e-9)**2 * c["formula_unit_number_density_m3"] / (2 * math.pi)
            expected = complex(1 - prefactor * f.real, prefactor * f.imag)
            self.assertLess(abs(expected - loaded["refractive_indices"][name]), 1e-18)
            self.assertEqual(loaded["epsilon_r"][name], loaded["refractive_indices"][name] ** 2)
            self.assertGreater(loaded["epsilon_r"][name].imag, 0)
            self.assertNotIn("MEASURED_FILM", m["status"])

    def test_all_frozen_fields_reject_change(self):
        changes = [
            ("wavelength_nm", 13.5), ("photon_energy_eV", 0.7),
            ("units", {"wavelength": "m"}), ("convention", {"n": "1-delta-i*beta"}),
            ("layer_order_bottom_to_top", ["Si"] * 6), ("unknown_key", True),
        ]
        for key, value in changes:
            with self.subTest(key=key):
                doc = copy.deepcopy(self.document)
                doc[key] = value
                with self.assertRaises(ValueError):
                    material.validate_material_document(doc)
        for name in ("Si", "SiGe", "SiO2"):
            for key, value in [("density_kg_m3", 2201.0), ("status", "MEASURED"),
                               ("stoichiometry", {"Si": 2.0})]:
                with self.subTest(name=name, key=key):
                    doc = copy.deepcopy(self.document)
                    doc["materials"][name][key] = value
                    with self.assertRaises(ValueError):
                        material.validate_material_document(doc)

    def test_wrong_loss_or_copied_Si_is_rejected(self):
        for mode in ("gain", "copySi"):
            doc = copy.deepcopy(self.document)
            if mode == "gain":
                doc["materials"]["SiGe"]["calculation"]["n"]["imag"] *= -1
            else:
                doc["materials"]["SiGe"]["calculation"] = doc["materials"]["Si"]["calculation"]
            with self.assertRaises(ValueError):
                material.validate_material_document(doc)

    def test_json_finite_unknown_type_duplicate_and_signed_zero(self):
        for value in (float("nan"), float("inf"), object(), complex(1, 0)):
            doc = copy.deepcopy(self.document)
            doc["wavelength_nm"] = value
            with self.assertRaises(ValueError):
                material.validate_material_document(doc)
        doc = copy.deepcopy(self.document)
        doc["external_air"]["n"]["imag"] = -0.0
        with self.assertRaises(ValueError):
            material.validate_material_document(doc)
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'):
            with self.assertRaises(ValueError):
                material._read_json(raw)

    def test_no_extrapolation_or_undefined_f1(self):
        raw = (material.ROOT / material.SOURCE_REL / "si.nff").read_bytes()
        for e in (0.7, 30001, 10.1, float("nan"), True):
            with self.subTest(e=e), self.assertRaises(ValueError):
                material.interpolate_scattering_factor(raw, e)

    def test_whole_raw_source_hash_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            d = Path(temporary)
            original = material.ROOT / material.SOURCE_REL / "si.nff"
            (d / "si.nff").write_bytes(original.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                material._source_bytes("si.nff", d)
            (d / "si.nff").unlink()
            (d / "si.nff").symlink_to(original)
            with self.assertRaises(ValueError):
                material._source_bytes("si.nff", d)

    def test_roundtrip_order_and_per_material_identity(self):
        doc = json.loads(json.dumps(self.document, sort_keys=True))
        material.validate_material_document(doc)
        for row in doc["materials"].values():
            row = dict(row)
            digest = row.pop("identity_sha256")
            self.assertEqual(digest, material._sha(row))

    def test_returned_identity_cannot_mutate_source_constants(self):
        loaded = material.load_sixlayer_materials()
        loaded["identity"]["constants"]["molar_masses_g_mol"]["Si"] = 1.0
        loaded["epsilon_r"]["Si"] = 42.0j
        self.assertEqual(material.MOLAR_MASSES["Si"], 28.0855)
        self.assertEqual(material.load_sixlayer_materials()["identity"], self.document)


if __name__ == "__main__":
    unittest.main()
