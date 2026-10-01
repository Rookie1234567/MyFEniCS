"""Hash-bound independent matrix/residual checker; never re-runs the solver."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import sparse


def check(directory: Path):
    report = json.loads((directory / "pilot_report.json").read_text())
    if report.get("status") != "ARCHITECTURE_IDENTITY_AND_NOTCH_PASS":
        return {"evidence_valid": False, "gate_pass": False, "reason": "no completed architecture report"}
    artifacts = report["artifacts"]
    def load(label):
        descriptor = artifacts[label]
        path = (directory / descriptor["path"]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("artifact escapes its run directory")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != descriptor["file_sha256"]:
            raise ValueError("artifact hash mismatch: " + label)
        array = np.load(path, allow_pickle=False, mmap_mode="r")
        if list(array.shape) != descriptor["shape"] or str(array.dtype) != descriptor["dtype"]:
            raise ValueError("artifact descriptor mismatch: " + label)
        return array
    n = int(report["layout"]["independent_rows"])
    q = sparse.csr_matrix((load("Q_data"), load("Q_indices"), load("Q_indptr")), shape=(n, n))
    r_inverse = sparse.csr_matrix((load("R_inverse_data"), load("R_inverse_indices"), load("R_inverse_indptr")), shape=(n, n))
    fourier = sparse.csr_matrix((load("F_data"), load("F_indices"), load("F_indptr")), shape=(n, n))
    rhs = {label: load(label + "_rhs") for label in ("generic", "physical")}
    regular_matrix = load("A0_original")
    notch_matrix = load("A_notch_original")
    checks = []
    def add(name, value, limit):
        checks.append({"name": name, "measured": float(value), "limit": float(limit),
                       "pass": bool(np.isfinite(value) and value <= limit)})
    for prefix, matrix in (("A0", regular_matrix), ("notch", notch_matrix)):
        for label, b in rhs.items():
            direct = load(prefix + "_direct_" + label)
            candidate = load(prefix + ("_modal_" if prefix == "A0" else "_iterative_") + label)
            scale = max(float(np.linalg.norm(b)), np.finfo(float).tiny)
            add(prefix + "_direct_" + label + "_matrix_true_residual", np.linalg.norm(b - matrix @ direct) / scale, 1e-10)
            add(prefix + "_candidate_" + label + "_matrix_true_residual", np.linalg.norm(b - matrix @ candidate) / scale, 1e-10)
            add(prefix + "_" + label + "_direct_difference", np.linalg.norm(candidate - direct) / max(np.linalg.norm(direct), np.finfo(float).tiny), 1e-9)
    modal_rhs = np.asarray(q.conj().T @ rhs["generic"]).reshape(report["layout"]["ny"], report["layout"]["rows_per_q"])
    norms = np.linalg.norm(modal_rhs, axis=1)
    all_q = bool(np.min(norms) / np.linalg.norm(norms) >= 1e-3)
    aliases = report["ports"]["alias_groups"]
    alias_complete = len([entry for entries in aliases.values() for entry in entries]) == report["ports"]["mode_count"]
    alias_complete = alias_complete and all(aliases[str(i)] for i in range(report["layout"]["ny"]))
    ns = {entry["n"] for entry in aliases["1"]}
    alias_complete = alias_complete and {1, -3}.issubset(ns)
    # Native form-action residuals are live authority, not independently reproducible from NPY.
    live_native = all(packet["full_original_true_residual"] <= 1e-10
                      for group in (report["regular_sources"], report["notched_sources"]) for packet in group.values())
    port_symmetry = max(report["ports"][key] for key in (
        "coupling_off_q_relative_max", "projection_off_q_relative_max",
        "augmented_C_covariance_relative_max", "augmented_D_covariance_relative_max")) <= 1e-11
    physical_modal = np.asarray(fourier.conj().T @ (r_inverse @ load("notch_iterative_physical"))).reshape(report["layout"]["ny"], report["layout"]["rows_per_q"])
    physical_q_relative = float(np.linalg.norm(physical_modal[1:]) / np.linalg.norm(physical_modal))
    physical_q = physical_q_relative > 1e-12
    live_augmented = all(max(packet["augmented_FE_true_residual"], packet["augmented_port_closure_relative"],
                             packet["augmented_vs_original_residual_relative"]) <= 1e-10
                         for group in (report["regular_sources"], report["notched_sources"]) for packet in group.values())
    return {"schema": "task40extra.y-orbit-checker.v1", "evidence_valid": True,
            "gate_pass": bool(all(item["pass"] for item in checks) and all_q and alias_complete and live_native and port_symmetry and physical_q and live_augmented),
            "checks": checks, "generic_all_q_excitation": all_q, "all_port_aliases_retained": alias_complete,
            "live_native_residual_authority_present": live_native, "live_port_symmetry": port_symmetry,
            "notch_physical_nonzero_q_content": physical_q,
            "notch_physical_nonzero_q_relative_recomputed": physical_q_relative,
            "live_augmented_residual_authority": live_augmented,
            "resource_authority": "separate existing whole-tree watchdog, must be reviewed independently",
            "qualification": "small full3D algebra architecture only, not target field/accuracy/memory"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    try:
        result = check(args.run_directory.resolve())
    except Exception as exc:
        result = {"evidence_valid": False, "gate_pass": False, "error_type": type(exc).__name__, "error": str(exc)}
    (args.run_directory / "independent_checker.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
