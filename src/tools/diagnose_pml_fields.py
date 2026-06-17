from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pyvista

from ..common.config import SimulationConfig, project_root
from ..solvers.solve_vector_maxwell import _json_default, run_case


DOMAIN_NAMES = {
    1: "air",
    2: "substrate",
    3: "grating",
    4: "top_pml",
    5: "bottom_pml",
}


def _cell_point_ids(grid: pyvista.UnstructuredGrid, cell_index: int) -> np.ndarray:
    return np.asarray(grid.get_cell(cell_index).point_ids, dtype=np.int64)


def _cell_mean_point_array(grid: pyvista.UnstructuredGrid, name: str) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(grid.point_data[name], dtype=np.float64)
    cell_values = np.empty(grid.n_cells, dtype=np.float64)
    cell_y = np.empty(grid.n_cells, dtype=np.float64)
    for cell_index in range(grid.n_cells):
        point_ids = _cell_point_ids(grid, cell_index)
        cell_values[cell_index] = float(np.mean(values[point_ids]))
        cell_y[cell_index] = float(np.mean(grid.points[point_ids, 1]))
    return cell_values, cell_y


def _stats(values: np.ndarray) -> dict[str, float | int]:
    if values.size == 0:
        return {"count": 0, "min": np.nan, "mean": np.nan, "max": np.nan, "p95": np.nan}
    return {
        "count": int(values.size),
        "min": float(np.min(values)),
        "mean": float(np.mean(values)),
        "max": float(np.max(values)),
        "p95": float(np.quantile(values, 0.95)),
    }


def diagnose_vtu(vtu_path: Path, cfg: SimulationConfig) -> dict[str, object]:
    grid = pyvista.read(vtu_path)
    if "domain_tag" not in grid.cell_data:
        raise RuntimeError(f"{vtu_path} does not contain cell_data['domain_tag']")
    if "E_scat_abs" not in grid.point_data:
        raise RuntimeError(f"{vtu_path} does not contain point_data['E_scat_abs']")

    domain_tag = np.asarray(grid.cell_data["domain_tag"], dtype=np.int32)
    e_scat_cell, cell_y = _cell_mean_point_array(grid, "E_scat_abs")
    e_total_cell, _ = _cell_mean_point_array(grid, "E_total_abs")

    by_domain: dict[str, object] = {}
    for tag in sorted(set(int(t) for t in domain_tag)):
        mask = domain_tag == tag
        name = DOMAIN_NAMES.get(tag, f"domain_{tag}")
        by_domain[name] = {
            "domain_tag": tag,
            "E_scat_abs": _stats(e_scat_cell[mask]),
            "E_total_abs": _stats(e_total_cell[mask]),
        }

    band_fraction = 0.15
    top_mask = domain_tag == cfg.tags.top_pml
    top_inner = top_mask & (cell_y <= cfg.physical_y_max + band_fraction * cfg.pml_top_thickness)
    top_outer = top_mask & (cell_y >= cfg.y_max - band_fraction * cfg.pml_top_thickness)

    bottom_mask = domain_tag == cfg.tags.bottom_pml
    bottom_inner = bottom_mask & (cell_y >= cfg.physical_y_min - band_fraction * cfg.pml_bottom_thickness)
    bottom_outer = bottom_mask & (cell_y <= cfg.y_min + band_fraction * cfg.pml_bottom_thickness)

    pml_bands = {
        "top_pml_inner_15_percent_near_physical_domain": _stats(e_scat_cell[top_inner]),
        "top_pml_outer_15_percent_near_truncation": _stats(e_scat_cell[top_outer]),
        "bottom_pml_inner_15_percent_near_physical_domain": _stats(e_scat_cell[bottom_inner]),
        "bottom_pml_outer_15_percent_near_truncation": _stats(e_scat_cell[bottom_outer]),
    }

    return {
        "vtu_path": str(vtu_path),
        "by_domain": by_domain,
        "pml_bands_for_E_scat_abs": pml_bands,
    }


def run_homogeneous_air_check(out_dir: Path, backend: str) -> dict[str, object]:
    cfg = SimulationConfig(
        case_name=f"homogeneous_air_pml_check_{backend}",
        n_air=1.0,
        n_substrate=1.0,
        n_grating=1.0,
        mesh_target_size=30.0,
        visualization_degree=2,
    )
    summary = run_case(cfg, out_dir, constraint_backend=backend)
    vtu_path = out_dir / "fields_for_paraview.vtu"
    diagnostics = diagnose_vtu(vtu_path, cfg)
    return {"run_summary": summary, "field_diagnostics": diagnostics}


def run_flat_substrate_check(out_dir: Path, backend: str) -> dict[str, object]:
    cfg = SimulationConfig(
        case_name=f"flat_substrate_reference_check_{backend}",
        n_air=1.0,
        n_substrate=1.45,
        n_grating=1.0,
        mesh_target_size=30.0,
        visualization_degree=2,
    )
    summary = run_case(cfg, out_dir, constraint_backend=backend)
    vtu_path = out_dir / "fields_for_paraview.vtu"
    diagnostics = diagnose_vtu(vtu_path, cfg)
    return {"run_summary": summary, "field_diagnostics": diagnostics}


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose scattered-field values in PML regions.")
    parser.add_argument(
        "--vtu",
        type=Path,
        default=project_root() / "results" / "air_substrate_grating_mpc_official" / "fields_for_paraview.vtu",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--homogeneous-air-check", action="store_true")
    parser.add_argument("--flat-substrate-check", action="store_true")
    parser.add_argument("--backend", choices=["manual", "mpc_official"], default="manual")
    args = parser.parse_args()

    cfg = SimulationConfig()
    report: dict[str, object] = {"current_case": diagnose_vtu(args.vtu, cfg)}
    if args.homogeneous_air_check:
        baseline_dir = project_root() / "results" / f"homogeneous_air_pml_check_{args.backend}"
        report["homogeneous_air_check"] = run_homogeneous_air_check(baseline_dir, args.backend)
    if args.flat_substrate_check:
        flat_dir = project_root() / "results" / f"flat_substrate_reference_check_{args.backend}"
        report["flat_substrate_check"] = run_flat_substrate_check(flat_dir, args.backend)

    output = args.output or args.vtu.with_name("pml_field_diagnostics.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
