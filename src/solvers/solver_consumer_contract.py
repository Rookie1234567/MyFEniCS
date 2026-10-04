"""Read-only field-level consumer checks; no solver dispatch or hash shortcut."""

import numpy as np

FIELDS = (
    "geometry",
    "material",
    "wavelength",
    "incidence",
    "background",
    "modes",
    "reference_planes",
    "complex_floquet",
    "degree",
    "canonical_rows",
    "internal_recovery",
)


def compare_fields(required, offered, *, conversions=None, scientific_qualified=False):
    conversions = conversions or {}
    records = []
    for field in FIELDS:
        need = required.get(field)
        have = offered.get(field)
        if have is None:
            status = "EVIDENCE_MISSING"
        elif have == need:
            status = "EXACT_FIELD_MATCH"
        elif field in conversions:
            converted, proof = conversions[field]
            status = (
                "VERIFIED_SCHEMA_OR_COORDINATE_CONVERSION"
                if converted == need and proof
                else "CONVERSION_NOT_QUALIFIED"
            )
        else:
            status = "PHYSICAL_OR_DISCRETE_DIFFERENCE"
        records.append(
            {"field": field, "required": need, "offered": have, "status": status}
        )
    passed = all(
        r["status"] in ("EXACT_FIELD_MATCH", "VERIFIED_SCHEMA_OR_COORDINATE_CONVERSION")
        for r in records
    )
    return {
        "status": "SOLVER_PACKAGE_QUALIFIED"
        if passed and scientific_qualified
        else "SOLVER_PACKAGE_NOT_QUALIFIED",
        "fields": records,
        "scientific_qualified": scientific_qualified,
        "serialized_physical_hash_comparison_used": False,
        "target_solve_authorized": False,
    }


def complex_distance(a, b):
    return float(np.linalg.norm(np.array(a) - np.array(b)))
