"""Fixed gate_cd material authority copied from the preserved user conditions."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

GATE_CD_CONDITIONS_SHA256 = (
    "d85db27dbad9170c59b0a83e3e090a39db35c6974e5b71094aa8df6748b313d2"
)

# Physical cell tags are deliberately outside the legacy 1..5 volume/PML tags
# and 11..16 exterior-facet tags.  Each fin/MDI layer retains its own output
# identity even when adjacent layers share the same epsilon.
_BASE_REGION_TAGS = {
    "Air": 101,
    "Si_substrate": 102,
    "Si_Fin0": 103,
    "STI_SiO2": 104,
    "Si_poly": 105,
    "Gate_SiO2": 106,
    "SiN": 107,
}

GATE_CD_EPSILON_R = {
    "Air": complex(1.0, 0.0),
    "Si": complex(0.9997525478045688, 0.000009266001361097818),
    "Si_poly": complex(0.9997525478045688, 0.000009266001361097818),
    "SiO2": complex(0.9997230630587056, 0.00001782515900542709),
    "SiGe": complex(0.9997455480845561, 0.00007739189092108909),
    "SiN": complex(0.9997243144507715, 0.00001240364665357174),
}

GATE_CD_N_COMPLEX = {
    "Air": complex(1.0, 0.0),
    "Si": complex(0.999876266258, 0.00000463357401),
    "Si_poly": complex(0.999876266258, 0.00000463357401),
    "SiO2": complex(0.999861521981, 0.00000891381387),
    "SiGe": complex(0.999872766697, 0.0000387008695),
    "SiN": complex(0.999862147743, 0.00000620267838),
}

_STACK_REGION_MATERIALS = {
    "Fin1": "Si",
    "Fin2": "SiGe",
    "Fin3": "Si",
    "Fin4": "SiGe",
    "Fin5": "Si",
    "Fin6": "SiGe",
    "Fin7": "Si",
    "Fin8": "SiGe",
    "MDI": "SiO2",
    "Fin9": "SiGe",
    "Fin10": "Si",
    "Fin11": "SiGe",
    "Fin12": "Si",
    "Fin13": "SiGe",
    "Fin14": "Si",
    "Fin15": "SiGe",
}
GATE_CD_REGION_TAGS = {
    **_BASE_REGION_TAGS,
    **{label: 108 + index for index, label in enumerate(_STACK_REGION_MATERIALS)},
}
GATE_CD_REGION_MATERIAL = {
    "Air": "Air",
    "Si_substrate": "Si",
    "Si_Fin0": "Si",
    "STI_SiO2": "SiO2",
    "Si_poly": "Si_poly",
    "Gate_SiO2": "SiO2",
    "SiN": "SiN",
    **_STACK_REGION_MATERIALS,
}
GATE_CD_REGION_EPSILON = {
    label: GATE_CD_EPSILON_R[material]
    for label, material in GATE_CD_REGION_MATERIAL.items()
}


def gate_cd_region_entries() -> tuple[dict[str, object], ...]:
    """Return the complete, stable tag/label/epsilon table for this profile."""

    return tuple(
        {
            "tag": int(GATE_CD_REGION_TAGS[label]),
            "label": label,
            "material_name": GATE_CD_REGION_MATERIAL[label],
            "epsilon_r": GATE_CD_REGION_EPSILON[label],
            "n_complex": GATE_CD_N_COMPLEX[GATE_CD_REGION_MATERIAL[label]],
        }
        for label in GATE_CD_REGION_TAGS
    )


def validate_gate_cd_region_entries(
    entries: object,
) -> tuple[dict[str, object], ...]:
    """Fail closed unless every user-defined physical region is represented."""

    if not isinstance(entries, (tuple, list)) or not entries:
        raise ValueError("gate_cd requires an explicit non-empty material-region map")
    normalized: list[dict[str, object]] = []
    seen_tags: set[int] = set()
    seen_labels: set[str] = set()
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise TypeError("gate_cd material-region entries must be mappings")
        tag = int(raw["tag"])
        label = str(raw["label"])
        material_name = str(raw["material_name"])
        epsilon = complex(raw["epsilon_r"])
        n_value = complex(raw["n_complex"])
        if tag in seen_tags or label in seen_labels:
            raise ValueError("gate_cd material-region tags and labels must be unique")
        if not label or not all(
            isfinite(value)
            for value in (epsilon.real, epsilon.imag, n_value.real, n_value.imag)
        ):
            raise ValueError("gate_cd material-region values must be finite")
        seen_tags.add(tag)
        seen_labels.add(label)
        normalized.append(
            {
                "tag": tag,
                "label": label,
                "material_name": material_name,
                "epsilon_r": epsilon,
                "n_complex": n_value,
            }
        )
    expected = set(GATE_CD_REGION_TAGS)
    if seen_labels != expected or seen_tags != set(GATE_CD_REGION_TAGS.values()):
        raise ValueError(
            "gate_cd material map must cover exactly the fixed physical regions"
        )
    ordered = {str(entry["label"]): entry for entry in normalized}
    result = tuple(ordered[label] for label in GATE_CD_REGION_TAGS)
    for expected_entry, actual in zip(gate_cd_region_entries(), result, strict=True):
        if (
            int(expected_entry["tag"]) != int(actual["tag"])
            or str(expected_entry["material_name"]) != str(actual["material_name"])
            or complex(expected_entry["epsilon_r"]) != complex(actual["epsilon_r"])
            or complex(expected_entry["n_complex"]) != complex(actual["n_complex"])
        ):
            raise ValueError(
                "gate_cd material map differs from the preserved user constants"
            )
    return result
