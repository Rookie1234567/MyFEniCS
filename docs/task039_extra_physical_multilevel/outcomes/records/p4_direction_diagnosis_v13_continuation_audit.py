"""Root review of saved V13 continuation packets; no FE/PC actions."""
import gc
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

started = time.perf_counter()
root = Path(sys.argv[1]).resolve()
checks = []
evidence = []


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def packet(name):
    path = root / "records" / (name + ".json")
    raw = json.loads(path.read_text())
    arrays = {}
    record = {"path": str(path), "sha256": digest(path)}
    if "arrays" in raw:
        archive_path = Path(raw["arrays"]["path"])
        actual_hash = digest(archive_path)
        assert actual_hash == raw["arrays"]["sha256"], str(archive_path)
        with np.load(archive_path, allow_pickle=False) as archive:
            arrays = {k: archive[k] for k in archive.files}
        record.update(npz=str(archive_path), npz_sha256=actual_hash)

    def expand(value):
        if isinstance(value, dict):
            if "array_key" in value:
                return arrays[value["array_key"]]
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v) for v in value]
        return value

    result = expand(raw)
    arrays.clear()
    evidence.append(record)
    return result


def compare(name, actual, expected, tolerance=1e-9):
    a, b = np.asarray(actual), np.asarray(expected)
    defect = float(np.linalg.norm(a - b) / max(1.0, float(np.linalg.norm(b))))
    checks.append({"name": name, "defect": defect, "tolerance": tolerance,
                   "pass": bool(np.isfinite(defect) and defect <= tolerance)})


def operation_compare(name, lhs, rhs, terms, tolerance=1e-10):
    scale = max(sum(float(np.linalg.norm(x)) for x in terms), np.finfo(float).tiny)
    defect = float(np.linalg.norm(lhs - rhs) / scale)
    checks.append({"name": name, "defect": defect, "tolerance": tolerance,
                   "pass": bool(np.isfinite(defect) and defect <= tolerance)})


def field_eta(y, facts):
    z = facts["r_factor"] @ (np.asarray(facts["column_scale"]) * y)
    energy = (float(facts["target_mass_squared"]) + float(np.vdot(z, z).real)
              - 2 * float(np.vdot(z, facts["rhs_small"]).real))
    return np.sqrt(max(0.0, energy) / facts["target_mass_squared"])


summary = packet("p4_direction_summary")
for item in summary["inputs"]:
    stem = item["stem"]
    p1 = packet(stem + "_p1_direction_diagnosis")
    p2 = packet(stem + "_p2_observation")
    responses = packet(stem + "_p3_response_columns")
    p3 = packet(stem + "_p3_local_directions")
    ind = responses["p4_indices"]
    g, ref = p1["rhs_values"], p1["reference_values"]
    Z, AZ = p1["pc_outputs_values"][ind], p1["A_pc_outputs_values"][ind]
    a, d, t = p2["a_values"], p2["d_values"], p2["t_values"]
    Aa, Ad, At = p2["A_a_values"], p2["A_d_values"], p2["A_t_values"]
    p, Ap = responses["p_columns_values"], responses["p_images_values"]
    compare(stem + ":actual_in_Z", Z @ p1["reconstruction_y"], p1["actual_solution_values"][ind], 1e-10)
    compare(stem + ":reference_residual", g - p1["reference_A4_values"], p1["r_ref_values"], 1e-12)
    compare(stem + ":a_image", Aa[ind], responses["A_a_values"], 1e-12)
    compare(stem + ":t_image", At[ind], responses["A_t_values"], 1e-12)
    compare(stem + ":sum_pi", p.sum(axis=1), d[ind], 1e-10)
    compare(stem + ":sum_Api", Ap.sum(axis=1), Ad[ind], 1e-10)
    old_path = Path(item["old_control_packet"])
    old_record = json.loads(old_path.read_text())
    old_archive = Path(old_record["arrays"]["path"])
    old_hash = digest(old_archive)
    assert old_hash == old_record["arrays"]["sha256"]
    with np.load(old_archive, allow_pickle=False) as old_npz:
        old_bare = old_npz[old_record["bare_solution_values"]["array_key"]]
    operation_compare(stem + ":reconstructed_B4_vs_qualified_old_bare",
                      (a + d - t)[ind], old_bare[ind],
                      (a[ind], d[ind], t[ind], old_bare[ind]))
    evidence.append({"path": str(old_path), "sha256": digest(old_path),
                     "npz": str(old_archive), "npz_sha256": old_hash})
    stage_paths = [root / "records" / (stem + suffix + ".json")
                   for suffix in ("_p1_direction_diagnosis", "_p2_observation",
                                  "_p3_response_columns", "_p3_local_directions")]
    times = [p.stat().st_mtime_ns for p in stage_paths]
    checks.append({"name": stem + ":saved_phase_order",
                   "pass": all(x <= y for x, y in zip(times, times[1:])),
                   "evidence": "local JSON publication timestamps", "mtime_ns": times})
    eh = ref - a
    pou = np.zeros(g.size)
    reconstruction = np.zeros(g.size, dtype=np.complex128)
    for block in p2["local_blocks"]:
        ix, w = block["indices"], block["weights"]
        np.add.at(pou, ix, w)
        np.add.at(reconstruction, ix, w * (block["d_i"] - eh[ix]))
        lhs = block["D_i_d_i"] - block["D_i_R_i_e_h"]
        right = block["chi"] + p1["r_ref_values"][ix] + block["ell"]
        operation_compare(stem + f":local_identity_{block['block_index']}",
                          lhs, right, (lhs, right, block["chi"],
                                       p1["r_ref_values"][ix], block["ell"]))
    compare(stem + ":PoU", pou[ind], np.ones(ind.size), 1e-12)
    operation_compare(stem + ":global_recomposition", reconstruction[ind],
                      (d - eh)[ind], (reconstruction[ind], d[ind], eh[ind]))
    L = np.column_stack((Z, a[ind], p, -t[ind]))
    AL = np.column_stack((AZ, Aa[ind], Ap, -At[ind]))
    k = Z.shape[1]
    selected = list(p3["selected_indices"])
    selections = [k] + [k + 1 + i for i in selected] + [L.shape[1] - 1]
    full_selected_y = np.zeros(L.shape[1], dtype=np.complex128)
    full_selected_y[selections] = p3["selected_y"]
    ys = {"L_residual": p3["L_residual_y"], "L_field": p3["L_field_y"],
          "L_selected": full_selected_y}
    for name, key in [("actual", "reconstruction_y"), ("Z_residual", "residual_y"),
                      ("Z_field", "field_y"), ("Z_dual_mass", "dual_y")]:
        y = np.zeros(L.shape[1], dtype=np.complex128)
        y[:k] = p1[key]
        ys[name] = y
    for name, y in ys.items():
        facts = item["candidates"][name]
        rho = np.linalg.norm(g[ind] - AL @ y) / np.linalg.norm(g[ind])
        compare(stem + ":rho:" + name, rho, facts["rho"], 1e-8)
        compare(stem + ":eta_from_weighted_R:" + name,
                field_eta(y, p3["facts"]["L_field"]), facts["eta"], 1e-7)
        compare(stem + ":curl_norm_record:" + name,
                np.sqrt(facts["curl_squared"] / facts["reference_curl_squared"]),
                facts["eta_curl"], 1e-12)
    if L.shape[1] > 48:
        raise AssertionError("more than 48 columns")
    del p1, p2, responses, p3, L, AL, Z, AZ, p, Ap
    gc.collect()

output = {"status": "PASS" if all(c["pass"] for c in checks) else "FAILED",
          "source_sha": summary["source_sha"], "checks": checks, "evidence": evidence,
          "check_count": len(checks), "core_seconds": time.perf_counter() - started,
          "new_PC": 0, "new_A4": 0, "new_M0": 0, "new_curl": 0,
          "limitations": "Curl values are checked against saved squared norms; no fresh FE curl action. Weighted-R field check uses the saved measured metric factorization."}
Path(sys.argv[2]).write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps({k: v for k, v in output.items() if k not in ("checks", "evidence")}, indent=2))
if output["status"] != "PASS":
    print(json.dumps([c for c in checks if not c["pass"]], indent=2))
    sys.exit(1)
