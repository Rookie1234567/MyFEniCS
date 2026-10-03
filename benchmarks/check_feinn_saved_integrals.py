"""Independent saved-energy/region checker; no FE reconstruction or optimizer."""

import argparse
import json
from pathlib import Path

import numpy as np

from src.solvers.neural_fe_action_packet import array_hash

REGIONS = (
    "air_notch",
    "air_other",
    "periodic_boundary_neighbor",
    "material_interface_neighbor",
)


def need(value, reason):
    if not value:
        raise ValueError(reason)


def same(a, b, reason, tolerance=1e-10):
    a, b = np.asarray(a), np.asarray(b)
    need(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), reason)
    # A large curl denominator must not mask corruption of a near-zero E floor.
    scale = np.maximum(np.maximum(np.abs(a), np.abs(b)), 1e-30)
    need(np.all(np.abs(a - b) <= tolerance * scale), reason)


def verify(result, arrays, original):
    need(
        result["status"] == "SAVED_FIELD_INTEGRALS_COMPLETE", "INCOMPLETE_FIELD_RECORD"
    )
    need(set(result["regions"]) == set(REGIONS), "FIXED_REGION_KEYS")
    need(result["regions_are_overlapping_not_additive"] is True, "OVERLAP_POLICY")
    for key in (
        "pde_only_solve",
        "production_initialization_allowed",
        "official_candidate_results",
        "pde_only_solver_qualified",
    ):
        need(result[key] is False, "DIAGNOSTIC_USE_POLICY")
    need(
        result["Gram_factor_created"] is False
        and result["Maxwell_factor_created"] is False,
        "NO_FACTOR",
    )
    need(
        all(
            result[k] == 0
            for k in ("A_actions", "AH_actions", "G_actions", "Gsolve_count")
        ),
        "NO_OPERATOR_ACTION",
    )
    volumes = np.asarray(arrays["cell_volumes_nm3"])
    need(
        volumes.ndim == 1 and np.isfinite(volumes).all() and np.all(volumes > 0),
        "CELL_VOLUMES",
    )
    total = float(volumes.sum())
    same(total, result["total_volume_nm3"], "TOTAL_VOLUME")
    energy = {
        key: np.asarray(arrays["energy_" + key])
        for key in ("before", "after", "delta", "minus", "reference", "reference_total")
    }
    for key, value in energy.items():
        need(
            value.shape == (2,) and np.isfinite(value).all() and np.all(value >= 0),
            "FINITE_RAW_ENERGY",
        )
        same(value, result["energies"][key], "RAW_ENERGY_RECORD")
    terms = {}
    for i, name in enumerate(("E_L2", "scaled_curl_L2")):
        cross = (energy["after"][i] - energy["minus"][i]) / 2
        change = energy["after"][i] - energy["before"][i]
        update = energy["delta"][i]
        scale = max(energy["before"][i], energy["after"][i], abs(cross) + update)
        defect = abs(change - cross - update) / scale
        need(defect <= 1e-8, "SIGNED_CROSS_CLOSURE")
        raw = dict(
            before=energy["before"][i],
            after=energy["after"][i],
            cross=cross,
            change=change,
            update_energy=update,
            reconstructed_change=cross + update,
            operation_scale=scale,
            defect=defect,
            reference_energy=energy["reference"][i],
        )
        for key, value in raw.items():
            same(
                value,
                result["energy_terms"][name][key],
                "CROSS_TERM_RECORD",
                1e-8 if key == "defect" else 1e-10,
            )
        terms[name] = raw
    need(result["ell_nm"] == 5.0 and result["k0_per_nm"] > 0, "ORIGINAL_CURL_SCALE")
    G = {}
    for key, state in (("before", "M3600"), ("after", "Mfinal")):
        combined = energy[key][0] + (5 * result["k0_per_nm"]) ** 2 * energy[key][1]
        measured = original["rows"][state]["field_G_squared"]
        defect = abs(combined - measured) / measured
        need(np.isfinite(defect) and defect <= 1e-8, "RAW_G_PAIRING")
        same(
            measured,
            result["G_norm_identity"][key]["sparse_G_energy"],
            "ORIGINAL_G_ENERGY",
        )
        same(
            combined,
            result["G_norm_identity"][key]["integrated_G_energy"],
            "INTEGRATED_G_ENERGY",
        )
        G[key] = dict(relative=defect, integrated=combined, original=measured)
    need(
        all(np.isfinite(x) and 0 <= x <= 1e-10 for x in result["MPC"].values()),
        "ACTUAL_MPC",
    )
    for kind, key in (("scattered", "reference"), ("total", "reference_total")):
        row = result["global_denominators"][kind]
        same(row["reference_energy"], energy[key], "GLOBAL_REFERENCE")
        floor = 1e-12 * np.sqrt(total)
        same(row["incident_floor"], floor, "GLOBAL_FLOOR")
        same(
            row["actual_denominator"],
            np.maximum(np.sqrt(energy[key]), floor),
            "GLOBAL_DENOMINATOR",
        )
    regions = {}
    for name in REGIONS:
        row = result["regions"][name]
        cells = np.asarray(arrays["cells_" + name])
        need(
            cells.ndim == 1
            and np.issubdtype(cells.dtype, np.integer)
            and len(cells) > 0
            and len(np.unique(cells)) == len(cells)
            and cells.min() >= 0
            and cells.max() < len(volumes),
            "REGION_CELL_IDS",
        )
        need(
            row["cells"] == len(cells) and row["cell_ids_sha256"] == array_hash(cells),
            "REGION_CELL_HASH",
        )
        volume = float(volumes[cells].sum())
        same(volume, row["volume_nm3"], "REGION_VOLUME")
        reference = np.asarray(arrays[name + "_reference_energy"])
        need(
            reference.shape == (2,)
            and np.isfinite(reference).all()
            and np.all(reference >= 0),
            "REGION_REFERENCE",
        )
        same(reference, row["reference_energy"], "REGION_REFERENCE_RECORD")
        denom = np.maximum(np.sqrt(reference), 1e-12 * np.sqrt(volume))
        computed = {}
        for state, key in (("M3600", "before"), ("Mfinal", "after")):
            stored = row["states"][state]
            value = np.asarray(arrays[name + "_" + state + "_error_energy"])
            need(
                value.shape == (2,) and np.isfinite(value).all() and np.all(value >= 0),
                "REGION_ERROR",
            )
            fraction = np.divide(
                value, energy[key], out=np.zeros(2), where=energy[key] > 0
            )
            concentration = fraction / (volume / total)
            vals = dict(
                error_energy=value,
                absolute=np.sqrt(value),
                actual_denominator=denom,
                relative=np.sqrt(value) / denom,
                incident_floor=1e-12 * np.sqrt(volume),
                volume_fraction=volume / total,
                error_energy_fraction=fraction,
                concentration=concentration,
            )
            for item, expected in vals.items():
                same(stored[item], expected, "REGION_DERIVED_" + item)
            need(
                stored["near_zero_reference"]
                == (np.sqrt(reference) <= 1e-12 * np.sqrt(volume)).tolist(),
                "NEAR_ZERO_RULE",
            )
            need(
                np.isfinite(stored["MPC_relative"])
                and 0 <= stored["MPC_relative"] <= 1e-10,
                "REGION_MPC",
            )
            computed[state] = dict(error_energy=value, concentration=concentration)
        for item in ("error_energy", "concentration"):
            same(
                row["increment"][item],
                computed["Mfinal"][item] - computed["M3600"][item],
                "REGION_INCREMENT",
            )
        regions[name] = dict(
            volume_nm3=volume,
            cell_ids_sha256=array_hash(cells),
            before_concentration=computed["M3600"]["concentration"].tolist(),
            after_concentration=computed["Mfinal"]["concentration"].tolist(),
        )
    return dict(
        status="PASS",
        raw_energy_checked=True,
        fixed_regions_checked=True,
        regions_not_summed=True,
        terms=terms,
        G_norm_identity=G,
        regions=regions,
        new_FE_or_operator_actions=0,
        producer_or_optimizer_calls=0,
    )


def main():
    from src.runners.feinn_workflow import load_index, sha, write_json
    from src.runners.feinn_native_constraint_arrays import source

    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()
    head = source()
    index = load_index("v18_saved_field_integrals", file_keys=("vectors", "result"))
    original = load_index("v12_saved_field_attribution", file_keys=("result",))
    result = json.loads(Path(index["files"]["result"]["path"]).read_text())
    with np.load(index["files"]["vectors"]["path"], allow_pickle=False) as arrays:
        out = verify(result, arrays, original["result"])
    out.update(
        source_sha=head,
        result=index["files"]["result"],
        vectors=index["files"]["vectors"],
        original_G_record=original["files"]["result"],
        checker_file_sha256=sha(__file__),
    )
    need(not Path(args.output).exists(), "IMMUTABLE_CHECKER_OUTPUT")
    write_json(args.output, out)
    print(json.dumps(dict(status=out["status"], regions=len(out["regions"]))))


if __name__ == "__main__":
    main()
