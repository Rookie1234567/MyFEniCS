"""Read-only V29/V30/V31 comparison of already-saved same-discrete arrays."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path.cwd()
RUNS = {
    "V29": ROOT / "results/euv_grazing1_phi0/task39extra_v29_a4_tensor_h6_original_h7p5_v1__full3d_iterative__mpi1__Mna/20260924T125506.302465Z",
    "V30": ROOT / "results/euv_grazing1_phi0/task39extra_v30_workstation_guided_original_h7p5_v1__full3d_iterative__mpi1__Mna/20260928T143049.147807Z",
    "V31": ROOT / "results/euv_grazing1_phi0/task39extra_v31_projection_layout_original_h7p5_user_authorized_recovery_v1__full3d_iterative__mpi1__Mna/20260929T061422.313883Z",
}
COORDS = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
FIELDS = ("E_V_per_m", "H_A_per_m", "E_t_interface_V_per_m", "H_t_interface_A_per_m")


def rel_l2(current: np.ndarray, reference: np.ndarray) -> float:
    denominator = float(np.linalg.norm(reference.ravel()))
    delta = current - reference
    return float(np.linalg.norm(delta.ravel()) / denominator) if denominator else float(np.max(np.abs(delta), initial=0.0))


def mode_key(row: dict) -> tuple[str, int, int, str]:
    return str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"])


def load_run(root: Path) -> dict:
    solution_meta = json.loads((root / "x2_retained_final.json").read_text())
    output_meta = json.loads((root / "official_output/q4_output.json").read_text())
    orders = json.loads((root / "numerical_output/dtn_port_diffraction_orders_3d.json").read_text())["orders"]
    with np.load(root / "x2_retained_final.npz", allow_pickle=False) as archive:
        full_field = np.asarray(archive[solution_meta["full_solution"]["array_key"]])
    with np.load(root / "numerical_output/full3d_reference_samples.npz", allow_pickle=False) as archive:
        samples = {name: np.asarray(archive[name]) for name in (*COORDS, *FIELDS)}
    with np.load(root / "official_output/q4_output.npz", allow_pickle=False) as archive:
        official_vector = np.asarray(archive["array_0"])
    return {
        "root": root,
        "solution_meta": solution_meta,
        "full_field": full_field,
        "samples": samples,
        "official_vector": official_vector,
        "orders": orders,
        "official_identity": output_meta["identity"],
    }


def compare(current: dict, reference: dict, reference_name: str) -> dict:
    a_id, b_id = current["official_identity"], reference["official_identity"]
    id_checks = {
        "physical_model": a_id.get("physical_model_sha256") == b_id.get("physical_model_sha256"),
        "p4_dof_map": a_id.get("p4_native_map_sha256") == b_id.get("p4_native_map_sha256"),
        "p6_dof_map": a_id.get("p6_native_map_sha256") == b_id.get("p6_native_map_sha256"),
        "ordered_modes": a_id.get("ordered_mode_sha256") == b_id.get("ordered_mode_sha256"),
        "p4_matrix": a_id.get("condensed_matrix_identity", {}).get("csr_sha256") == b_id.get("condensed_matrix_identity", {}).get("csr_sha256"),
    }
    coordinates = {name: bool(np.array_equal(current["samples"][name], reference["samples"][name])) for name in COORDS}
    sample_metrics = {}
    for name in FIELDS:
        a, b = current["samples"][name], reference["samples"][name]
        sample_metrics[name] = {
            "shape": list(a.shape),
            "relative_l2": rel_l2(a, b),
            "max_absolute": float(np.max(np.abs(a - b), initial=0.0)),
        }
    a_field, b_field = current["full_field"], reference["full_field"]
    a_official, b_official = current["official_vector"], reference["official_vector"]
    a_orders, b_orders = current["orders"], reference["orders"]
    a_keys, b_keys = [mode_key(row) for row in a_orders], [mode_key(row) for row in b_orders]
    same_order = a_keys == b_keys
    per_mode, amplitude = {}, {"relative_l2": None, "max_absolute": None}
    if same_order:
        for field in ("R", "T", "power_ratio", "modal_power_code_units"):
            per_mode[field] = max(abs(float(a[field]) - float(b[field])) for a, b in zip(a_orders, b_orders))
        a_amp = np.array([complex(*row["outgoing_amplitude"]) for row in a_orders])
        b_amp = np.array([complex(*row["outgoing_amplitude"]) for row in b_orders])
        amplitude = {"relative_l2": rel_l2(a_amp, b_amp), "max_absolute": float(np.max(np.abs(a_amp - b_amp), initial=0.0))}
    return {
        "reference": reference_name,
        "binding_identity_checks": id_checks,
        "all_binding_identities_equal": all(id_checks.values()),
        "input_sha_equal": a_id.get("input_sha256") == b_id.get("input_sha256"),
        "sample_coordinates_exact": coordinates,
        "same_coordinate_E_H_samples": sample_metrics,
        "full_field_coefficient_vector_euclidean_not_FE_norm": {
            "shape": list(a_field.shape),
            "relative_l2": rel_l2(a_field, b_field),
            "max_absolute": float(np.max(np.abs(a_field - b_field), initial=0.0)),
        },
        "official_80_vector": {
            "shape": list(a_official.shape),
            "relative_l2": rel_l2(a_official, b_official),
            "max_absolute": float(np.max(np.abs(a_official - b_official), initial=0.0)),
        },
        "ordered_mode_keys": {"current_count": len(a_keys), "reference_count": len(b_keys), "exact_order_match": same_order},
        "per_mode_absolute_power_differences": per_mode,
        "outgoing_modal_amplitudes": amplitude,
    }


def main() -> None:
    loaded = {name: load_run(path) for name, path in RUNS.items()}
    print(json.dumps({
        "scope": "read-only existing arrays; no solver, assembly, factor, or PDE",
        "comparisons": {
            "V31_vs_V29": compare(loaded["V31"], loaded["V29"], "V29"),
            "V31_vs_V30": compare(loaded["V31"], loaded["V30"], "V30"),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
