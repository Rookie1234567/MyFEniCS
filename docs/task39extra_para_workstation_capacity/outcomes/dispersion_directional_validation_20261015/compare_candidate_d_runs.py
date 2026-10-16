#!/usr/bin/env python3
"""Offline comparison of the original 0.7 nm grid and candidate D.

Reads only the two runs' compact diffraction-order JSON and bounded complex
sample NPZs, plus the previously archived 143-order RCWA power table. It does
not read resource streams, full fields, matrices, factors, or checkpoints.
No phase alignment is applied to complex amplitudes or field samples.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np


OLD_RUN = Path(
    "results/euv_grazing1_phi0/"
    "v7_interleave_0p7nm_aniso_p6_direct_q160_n0_full__full3d_direct__mpi1__Mna/"
    "20261014T062635.999684Z"
)
CANDIDATE_D_RUN = Path(
    "results/euv_grazing1_phi0/"
    "v7_interleave_0p7nm_aniso_p6_direct_d_cross_changed_q160_n0_full__full3d_direct__mpi1__Mna/"
    "20261015T104602.092954Z"
)
RCWA_TABLE = Path(
    "docs/task39extra_para_workstation_capacity/outcomes/"
    "rcwa_fe_comparison_0p7nm_20261015/orders_comparison_143.csv"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json_bytes(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"expected JSON object: {path}")
    return obj, raw


def load_orders(run: Path) -> tuple[dict[tuple[int, int], dict[str, Any]], dict[str, str]]:
    path = run / "numerical_output/dtn_port_diffraction_orders_3d.json"
    document, raw = load_json_bytes(path)
    rows = document.get("orders")
    if not isinstance(rows, list) or len(rows) != 572:
        raise ValueError(f"expected 572 active modal rows in {path}")
    grouped: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        key = (int(row["m"]), int(row["n"]))
        item = grouped.setdefault(key, {"R": 0.0, "T": 0.0, "amplitudes": {}})
        side = str(row["side"])
        pol = str(row["polarization"])
        if side == "top":
            item["R"] += float(row["R"])
        elif side == "bottom":
            item["T"] += float(row["T"])
        else:
            raise ValueError(f"unexpected side {side!r}")
        amplitude = row.get("outgoing_amplitude_at_boundary")
        if not isinstance(amplitude, list) or len(amplitude) != 2:
            raise ValueError("missing complex boundary-plane outgoing amplitude")
        item["amplitudes"][(side, pol)] = complex(float(amplitude[0]), float(amplitude[1]))
    if len(grouped) != 143:
        raise ValueError(f"expected 143 diffraction orders, got {len(grouped)}")
    return grouped, {str(path): sha256_bytes(raw)}


def load_rcwa(path: Path) -> tuple[dict[tuple[int, int], dict[str, float]], str]:
    raw = path.read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    table = {
        (int(row["m"]), int(row["n"])): {
            "R": float(row["R_RCWA_report"]),
            "T": float(row["T_RCWA_report"]),
            "R_FE_original_A": float(row["R_FE"]),
            "T_FE_original_A": float(row["T_FE"]),
        }
        for row in rows
    }
    if len(table) != 143:
        raise ValueError(f"expected 143 RCWA orders, got {len(table)}")
    return table, sha256_bytes(raw)


def read_sample_archive(run: Path, name: str) -> tuple[dict[str, np.ndarray], str]:
    raw = (run / "numerical_output" / name).read_bytes()
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    return arrays, sha256_bytes(raw)


def array_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    if reference.shape != candidate.shape:
        raise ValueError(f"shape mismatch {reference.shape} != {candidate.shape}")
    if not np.isfinite(reference).all() or not np.isfinite(candidate).all():
        raise ValueError("non-finite sample values")
    delta = candidate - reference
    ref_norm = float(np.linalg.norm(reference.ravel()))
    ref_peak = float(np.max(np.abs(reference)))
    result: dict[str, Any] = {
        "shape": list(reference.shape),
        "finite": True,
        "relative_l2": float(np.linalg.norm(delta.ravel()) / ref_norm) if ref_norm else None,
        "max_abs_difference": float(np.max(np.abs(delta))),
        "reference_peak_abs": ref_peak,
        "max_abs_difference_over_reference_peak": float(np.max(np.abs(delta)) / ref_peak) if ref_peak else None,
        "phase_alignment": "none",
    }
    if reference.ndim >= 1 and reference.shape[0] == 5:
        result["per_z_relative_l2"] = [
            {
                "z_nm": float(z),
                "relative_l2": float(
                    np.linalg.norm((candidate[index] - reference[index]).ravel())
                    / np.linalg.norm(reference[index].ravel())
                ),
            }
            for index, z in enumerate((10.0, 30.0, 60.0, 90.0, 110.0))
        ]
    return result


def compare_fields(old_run: Path, new_run: Path) -> dict[str, Any]:
    old, old_hash = read_sample_archive(old_run, "full3d_reference_samples.npz")
    new, new_hash = read_sample_archive(new_run, "full3d_reference_samples.npz")
    coordinate_keys = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
    coordinate_match = {
        key: bool(np.array_equal(old[key], new[key])) for key in coordinate_keys
    }
    if not all(coordinate_match.values()):
        raise ValueError(f"sample coordinates are not identical: {coordinate_match}")
    field_names = (
        "E_V_per_m",
        "H_A_per_m",
        "E_t_interface_V_per_m",
        "H_t_interface_A_per_m",
    )
    fields = {key: array_metrics(old[key], new[key]) for key in field_names}
    old_curl, old_curl_hash = read_sample_archive(old_run, "v7_curl_samples.npz")
    new_curl, new_curl_hash = read_sample_archive(new_run, "v7_curl_samples.npz")
    for key in ("x_nm", "y_nm", "z_nm"):
        coordinate_match[f"curl_{key}"] = bool(np.array_equal(old_curl[key], new_curl[key]))
    if not all(coordinate_match.values()):
        raise ValueError(f"curl sample coordinates are not identical: {coordinate_match}")
    return {
        "coordinate_match_exact": coordinate_match,
        "sample_coordinates": {
            "x_count": int(old["x_nm"].size),
            "y_count": int(old["y_nm"].size),
            "z_nm": [float(value) for value in old["z_nm"]],
            "interface_z_nm": [float(value) for value in old["interface_z_nm"]],
        },
        "field_sample_count": int(old["E_V_per_m"].shape[0] * old["E_V_per_m"].shape[1] * old["E_V_per_m"].shape[2]),
        "fields": fields,
        "curl_E_code_per_nm": array_metrics(old_curl["curl_E_code_per_nm"], new_curl["curl_E_code_per_nm"]),
        "archives": {
            "old_full3d_reference_samples_npz_sha256": old_hash,
            "candidate_d_full3d_reference_samples_npz_sha256": new_hash,
            "old_v7_curl_samples_npz_sha256": old_curl_hash,
            "candidate_d_v7_curl_samples_npz_sha256": new_curl_hash,
        },
        "interpretation": "bounded exported samples only; no full-field norm or exact grating reference",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--old-run", type=Path, default=OLD_RUN)
    parser.add_argument("--candidate-d-run", type=Path, default=CANDIDATE_D_RUN)
    parser.add_argument("--rcwa-table", type=Path, default=RCWA_TABLE)
    parser.add_argument("--csv-out", type=Path, default=Path(__file__).with_name("candidate_d_orders_143.csv"))
    parser.add_argument("--json-out", type=Path, default=Path(__file__).with_name("candidate_d_comparison.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    old_run = (repo / args.old_run).resolve() if not args.old_run.is_absolute() else args.old_run.resolve()
    new_run = (repo / args.candidate_d_run).resolve() if not args.candidate_d_run.is_absolute() else args.candidate_d_run.resolve()
    rcwa_path = (repo / args.rcwa_table).resolve() if not args.rcwa_table.is_absolute() else args.rcwa_table.resolve()

    old, old_hashes = load_orders(old_run)
    new, new_hashes = load_orders(new_run)
    rcwa, rcwa_hash = load_rcwa(rcwa_path)
    keys = sorted(old)
    if set(keys) != set(new) or set(keys) != set(rcwa):
        raise ValueError("old A, candidate D, and RCWA order inventories differ")
    rows: list[dict[str, Any]] = []
    threshold = 1e-8
    for key in keys:
        a, d, r = old[key], new[key], rcwa[key]
        if not math_close(a["R"], r["R_FE_original_A"]) or not math_close(a["T"], r["T_FE_original_A"]):
            raise ValueError(f"archived RCWA comparison FE columns do not match old A at {key}")
        significant = max(a["R"], a["T"], d["R"], d["T"], r["R"], r["T"]) >= threshold
        row: dict[str, Any] = {
            "m": key[0],
            "n": key[1],
            "significant_union_ge_1e-8": significant,
            "R_old_A": a["R"],
            "R_candidate_D": d["R"],
            "R_RCWA_report": r["R"],
            "R_D_minus_A": d["R"] - a["R"],
            "R_D_minus_RCWA": d["R"] - r["R"],
            "T_old_A": a["T"],
            "T_candidate_D": d["T"],
            "T_RCWA_report": r["T"],
            "T_D_minus_A": d["T"] - a["T"],
            "T_D_minus_RCWA": d["T"] - r["T"],
        }
        for side, pol in (("top", "s"), ("top", "p"), ("bottom", "s"), ("bottom", "p")):
            name = f"{side}_{pol}"
            amp_a = a["amplitudes"][(side, pol)]
            amp_d = d["amplitudes"][(side, pol)]
            row[f"amp_{name}_A_re"] = amp_a.real
            row[f"amp_{name}_A_im"] = amp_a.imag
            row[f"amp_{name}_D_re"] = amp_d.real
            row[f"amp_{name}_D_im"] = amp_d.imag
            row[f"amp_{name}_D_minus_A_abs"] = abs(amp_d - amp_a)
        rows.append(row)

    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    def power_totals(grouped: dict[tuple[int, int], dict[str, Any]]) -> dict[str, float]:
        return {name: float(sum(value[name] for value in grouped.values())) for name in ("R", "T")}

    significant_rows = [row for row in rows if row["significant_union_ge_1e-8"]]
    tail_rows = [row for row in rows if not row["significant_union_ge_1e-8"]]
    max_order_errors: dict[str, Any] = {}
    for quantity in ("R", "T"):
        max_order_errors[quantity] = {
            "candidate_D_minus_old_A": max(
                [
                    {"abs": abs(row[f"{quantity}_D_minus_A"]), "m": row["m"], "n": row["n"]}
                    for row in rows
                ],
                key=lambda item: item["abs"],
            ),
            "candidate_D_minus_RCWA": max(
                [
                    {"abs": abs(row[f"{quantity}_D_minus_RCWA"]), "m": row["m"], "n": row["n"]}
                    for row in rows
                ],
                key=lambda item: item["abs"],
            ),
        }
    summary: dict[str, Any] = {
        "schema": "task39extra.candidate-d-offline-comparison.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "comparison_scope": "CROSS_CHANGED_GRID_DIAGNOSTIC",
        "orders_count": len(rows),
        "significant_threshold": threshold,
        "significant_union_count": len(significant_rows),
        "tail_count": len(tail_rows),
        "grid_change": "old A hx=0.5 nm and z 17/200/17; candidate D hx=0.25 nm and z 9/100/9; both p6, y=2, same material/incidence/mode set",
        "phase_alignment": "none",
        "total_power_sums": {
            "old_A_FE": power_totals(old),
            "candidate_D_FE": power_totals(new),
            "RCWA_report": {name: float(sum(value[name] for value in rcwa.values())) for name in ("R", "T")},
        },
        "max_per_order_absolute_difference": max_order_errors,
        "significant_union_R_T_sums": {
            "old_A": {q: float(sum(row[f"{q}_old_A"] for row in significant_rows)) for q in ("R", "T")},
            "candidate_D": {q: float(sum(row[f"{q}_candidate_D"] for row in significant_rows)) for q in ("R", "T")},
            "RCWA": {q: float(sum(row[f"{q}_RCWA_report"] for row in significant_rows)) for q in ("R", "T")},
        },
        "tail_R_T_sums": {
            "old_A": {q: float(sum(row[f"{q}_old_A"] for row in tail_rows)) for q in ("R", "T")},
            "candidate_D": {q: float(sum(row[f"{q}_candidate_D"] for row in tail_rows)) for q in ("R", "T")},
            "RCWA": {q: float(sum(row[f"{q}_RCWA_report"] for row in tail_rows)) for q in ("R", "T")},
        },
        "field_sample_comparison": compare_fields(old_run, new_run),
        "input_artifacts": {
            "old_orders_json": old_hashes,
            "candidate_d_orders_json": new_hashes,
            "rcwa_orders_csv": {str(rcwa_path): rcwa_hash},
        },
        "per_order_csv": str(args.csv_out),
    }
    args.json_out.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("schema", "orders_count", "significant_union_count", "tail_count", "total_power_sums", "max_per_order_absolute_difference", "field_sample_comparison")}, ensure_ascii=False, sort_keys=True, indent=2))


def math_close(left: float, right: float) -> bool:
    return abs(left - right) <= max(2e-15, 2e-13 * max(abs(left), abs(right)))


if __name__ == "__main__":
    main()
