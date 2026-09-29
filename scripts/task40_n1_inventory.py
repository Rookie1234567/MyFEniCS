from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.config_3d import SimulationConfig3D
from src.geometry.task40_nonseparable_plan import task40_mesh_plan
from src.common.modes_3d import (
    enumerate_diffraction_orders_3d,
    outgoing_port_modes_3d,
)

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "docs/task40extra_0p7nm_engineering"
RECORDS = TASK / "outcomes/records"
RAW = RECORDS / "raw/si_nff_excerpt.tsv"
RAW_SOURCE = RECORDS / "raw/si.nff"
SCALE = Fraction(7, 135)
WAVELENGTH_NM = 0.7
HC_EV_NM = 1239.8419843320025
R_E_M = 2.8179403205e-15
N_A_PER_MOL = 6.02214076e23
SI_DENSITY_KG_M3 = 2329.1
SI_MOLAR_MASS_KG_MOL = 28.0855e-3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .encode("utf-8")
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def subdivide(points: list[Fraction], h: Fraction) -> tuple[list[Fraction], list[int]]:
    coordinates: list[Fraction] = [points[0]]
    interval_counts: list[int] = []
    for left, right in zip(points, points[1:]):
        count = ceil_fraction((right - left) / h)
        interval_counts.append(count)
        coordinates.extend(
            left + (right - left) * Fraction(i, count)
            for i in range(1, count + 1)
        )
    return coordinates, interval_counts


def nm_values(values: list[Fraction], offset: Fraction = Fraction(0)) -> list[float]:
    return [float((value + offset) * SCALE) for value in values]


def make_geometry_plan() -> dict[str, object]:
    chart_x = [
        Fraction(0),
        Fraction(33, 2),
        Fraction(25),
        Fraction(67, 2),
        Fraction(50),
    ]
    chart_y = [Fraction(0), Fraction(25, 4), Fraction(75, 4), Fraction(25)]
    z_planes = [
        Fraction(-10),
        Fraction(0),
        Fraction(40),
        Fraction(80),
        Fraction(120),
        Fraction(130),
    ]
    axis_points = {"x": chart_x, "y": chart_y, "z": z_planes}
    plans: dict[str, object] = {}
    for mesh_id, h in (("G0", Fraction(10)), ("G1", Fraction(15, 2))):
        axes: dict[str, list[float]] = {}
        counts: dict[str, list[int]] = {}
        for axis, points in axis_points.items():
            coordinates, interval_counts = subdivide(points, h)
            axes[axis] = nm_values(coordinates)
            counts[axis] = interval_counts
        cell_counts = {
            axis: sum(axis_counts) for axis, axis_counts in counts.items()
        }
        expected_plan = task40_mesh_plan(mesh_id)
        if (
            expected_plan["axis_segment_interval_counts"] != counts
            or expected_plan["axis_interval_counts"] != cell_counts
            or expected_plan["axis_coordinates_nm"] != axes
        ):
            raise ValueError("Inventory plan differs from the Task40 input validator plan.")
        plans[mesh_id] = {
            "target_h_nm": float(h * SCALE),
            "axis_segment_interval_counts": counts,
            "axis_interval_counts": cell_counts,
            "axis_coordinates_nm": axes,
            "expected_hexahedra": math.prod(cell_counts.values()),
            "mesh_plan_id": expected_plan["mesh_plan_id"],
            "mesh_plan_sha256": expected_plan["mesh_plan_sha256"],
            "classification": "derived_plan_not_measured_mesh",
        }

    scale = float(SCALE)
    volumes_s3 = {
        "unit_cell": 50 * 25 * 140,
        "substrate": 50 * 25 * 10,
        "gross_grating": 17 * 25 * 120,
        "air_void": Fraction(17, 2) * Fraction(25, 2) * 40,
    }
    si_s3 = volumes_s3["substrate"] + volumes_s3["gross_grating"] - volumes_s3["air_void"]
    air_s3 = volumes_s3["unit_cell"] - si_s3
    return {
        "schema": "task40extra.geometry_plan.v1",
        "status": "DERIVED_PLAN_PENDING_ACTUAL_BUILDER_AUDIT",
        "coordinate_chart": {
            "physical_x_nm": "[-25s,25s]",
            "physical_y_nm": "[-12.5s,12.5s]",
            "solver_chart_x_nm": "[0,50s]",
            "solver_chart_y_nm": "[0,25s]",
            "translation": {"x_nm": "x_physical+25s", "y_nm": "y_physical+12.5s"},
            "translation_note": (
                "This is a periodic-cell coordinate translation. It changes modal "
                "complex phases but leaves powers invariant; G0/G1 use the same chart."
            ),
            "s_exact": "7/135",
            "s_nm": scale,
            "geometry_is_3d_nonseparable": True,
        },
        "planes_in_scale_units": {
            "x": ["0", "33/2", "25", "67/2", "50"],
            "y": ["0", "25/4", "75/4", "25"],
            "z": ["-10", "0", "40", "80", "120", "130"],
        },
        "physical_material_regions_in_scale_units": {
            "substrate_si": {"x": ["0", "50"], "y": ["0", "25"], "z": ["-10", "0"]},
            "grating_si_before_void": {"x": ["33/2", "67/2"], "y": ["0", "25"], "z": ["0", "120"]},
            "air_void_cut_from_grating": {"x": ["25", "67/2"], "y": ["25/4", "75/4"], "z": ["40", "80"]},
            "void_box_nm": [
                float(Fraction(25) * SCALE),
                float(Fraction(67, 2) * SCALE),
                float(Fraction(25, 4) * SCALE),
                float(Fraction(75, 4) * SCALE),
                float(Fraction(40) * SCALE),
                float(Fraction(80) * SCALE),
            ],
        },
        "volumes": {
            "unit_cell_s3": volumes_s3["unit_cell"],
            "substrate_si_s3": volumes_s3["substrate"],
            "gross_grating_si_s3": volumes_s3["gross_grating"],
            "air_void_s3": float(volumes_s3["air_void"]),
            "total_si_s3": float(si_s3),
            "air_s3": float(air_s3),
            "si_volume_fraction": float(si_s3 / volumes_s3["unit_cell"]),
            "nm3_per_s3": scale**3,
            "unit_cell_nm3": volumes_s3["unit_cell"] * scale**3,
            "total_si_nm3": float(si_s3) * scale**3,
            "air_nm3": float(air_s3) * scale**3,
        },
        "meshes": plans,
        "identity_sha256": canonical_sha256(
            {
                "chart": ["7/135", "0..50s", "0..25s", "-10..130s"],
                "planes": {
                    "x": ["0", "33/2", "25", "67/2", "50"],
                    "y": ["0", "25/4", "75/4", "25"],
                    "z": ["-10", "0", "40", "80", "120", "130"],
                },
                "regions": {
                    "substrate": ["0", "50", "0", "25", "-10", "0"],
                    "grating": ["33/2", "67/2", "0", "25", "0", "120"],
                    "void": ["25", "67/2", "25/4", "75/4", "40", "80"],
                },
            }
        ),
    }


def read_raw_rows() -> tuple[list[dict[str, float]], bytes, bytes, list[int]]:
    excerpt_bytes = RAW.read_bytes()
    source_bytes = RAW_SOURCE.read_bytes()
    selected_energies = {
        1756.82, 1785.24, 1814.11, 1838.80, 1839.0, 1843.45
    }
    parsed: list[dict[str, float]] = []
    selected_bytes: list[bytes] = []
    source_line_numbers: list[int] = []
    for line_number, raw_line in enumerate(source_bytes.splitlines(keepends=True), 1):
        columns = raw_line.decode("ascii").strip().split("\t")
        if line_number == 1 or len(columns) != 3:
            continue
        energy, f1, f2 = (float(value) for value in columns)
        if energy in selected_energies:
            parsed.append({"energy_eV": energy, "f1": f1, "f2": f2})
            selected_bytes.append(raw_line)
            source_line_numbers.append(line_number)
    if [row["energy_eV"] for row in parsed] != sorted(selected_energies):
        raise ValueError("Official Si raw file is missing a required bracketing/edge row.")
    excerpt_data_rows = excerpt_bytes.decode("ascii").splitlines()[1:]
    excerpt_triples = [
        tuple(float(value) for value in line.split("\t"))
        for line in excerpt_data_rows
    ]
    parsed_triples = [
        (row["energy_eV"], row["f1"], row["f2"]) for row in parsed
    ]
    if excerpt_triples != parsed_triples:
        raise ValueError(
            "Stored excerpt and downloaded official Si (E, f1, f2) rows differ."
        )
    return parsed, source_bytes, b"".join(selected_bytes), source_line_numbers


def make_material_identity() -> dict[str, object]:
    rows, source_bytes, rows_bytes, source_line_numbers = read_raw_rows()
    energy = HC_EV_NM / WAVELENGTH_NM
    left, right = rows[0], rows[1]
    t = (energy - left["energy_eV"]) / (right["energy_eV"] - left["energy_eV"])
    f1 = left["f1"] + t * (right["f1"] - left["f1"])
    f2 = left["f2"] + t * (right["f2"] - left["f2"])
    atom_density = SI_DENSITY_KG_M3 / SI_MOLAR_MASS_KG_MOL * N_A_PER_MOL
    wavelength_m = WAVELENGTH_NM * 1.0e-9
    prefactor = R_E_M * wavelength_m**2 * atom_density / (2.0 * math.pi)
    delta = prefactor * f1
    beta = prefactor * f2
    n_solver = complex(1.0 - delta, beta)
    eps_solver = n_solver**2
    physical_inputs = {
        "wavelength_nm": WAVELENGTH_NM,
        "energy_eV": energy,
        "f1": f1,
        "f2": f2,
        "density_kg_m3": SI_DENSITY_KG_M3,
        "molar_mass_kg_mol": SI_MOLAR_MASS_KG_MOL,
        "atom_density_per_m3": atom_density,
        "delta": delta,
        "beta": beta,
        "n_solver": [n_solver.real, n_solver.imag],
        "epsilon_solver": [eps_solver.real, eps_solver.imag],
        "source_rows_sha256": sha256(rows_bytes),
    }
    return {
        "schema": "task40extra.material_identity.v1",
        "status": "DERIVED_FROM_OFFICIAL_REFERENCE_DATA",
        "measurement_status": "published elemental scattering-factor data; not sample-specific measurement",
        "source": {
            "scattering_factors_url": "https://henke.lbl.gov/optical_constants/sf/si.nff",
            "index_convention_url": "https://henke.lbl.gov/optical_constants/pert_form.html",
            "density_reference_url": "https://www.nist.gov/document/nistir69692014092620160121revpdf",
            "molar_mass_url": "https://webbook.nist.gov/cgi/cbook.cgi?ID=C7440213&Mask=48&Units=SI",
            "classical_electron_radius_url": "https://physics.nist.gov/cuu/pdf/all.pdf",
            "retrieved_date": "2026-09-29",
            "source_line_number_kind": "1-based physical line numbers in the downloaded .nff file",
            "scattering_factor_source_lines": source_line_numbers,
            "interpolation_bracket_lines": source_line_numbers[:2],
            "original_data_path": str(RAW_SOURCE.relative_to(ROOT)),
            "original_data_sha256": sha256(source_bytes),
            "excerpt_path": str(RAW.relative_to(ROOT)),
            "excerpt_file_sha256": sha256(RAW.read_bytes()),
            "source_rows_sha256": sha256(rows_bytes),
            "raw_excerpt_rows": rows,
            "absorption_edge_context": {
                "below_edge": rows[3],
                "above_edge": rows[4],
                "edge_is_not_crossed_by_interpolation": True,
            },
        },
        "calculation": {
            "wavelength_nm": WAVELENGTH_NM,
            "energy_eV": energy,
            "energy_formula": "h*c/(e*lambda)",
            "hc_over_e_eV_nm": HC_EV_NM,
            "interpolation": "linear in photon energy between the two bracketing tabulated points",
            "interpolation_fraction": t,
            "density_kg_m3": SI_DENSITY_KG_M3,
            "density_source_units": "2.3291 g/cm^3 at 20 C converted to 2329.1 kg/m^3",
            "molar_mass_g_mol": SI_MOLAR_MASS_KG_MOL * 1000,
            "avogadro_constant_per_mol": N_A_PER_MOL,
            "classical_electron_radius_m": R_E_M,
            "atom_density_per_m3": atom_density,
            "f1": f1,
            "f2": f2,
            "delta": delta,
            "beta": beta,
            "cxro_refractive_index": {
                "real": 1.0 - delta,
                "imag": -beta,
                "expression": "1-delta-i*beta",
            },
            "solver_time_harmonic_convention": "exp(i*k dot r) exp(-i*omega*t)",
            "solver_refractive_index": {
                "real": n_solver.real,
                "imag": n_solver.imag,
                "expression": "conjugate of CXRO n for the solver's exp(-i*omega*t) passive-loss convention",
            },
            "solver_epsilon_r": {"real": eps_solver.real, "imag": eps_solver.imag},
            "k0_per_nm": 2.0 * math.pi / WAVELENGTH_NM,
            "precision_note": "Reported digits are arithmetic output; f1/f2 and density source precision limit physical significant digits.",
            "atomic_model_limit": "Independent-atom elemental scattering factor is not sample-specific and is weakly supported at atomic-scale feature sizes.",
        },
        "physical_model_inputs": physical_inputs,
        "material_model_sha256": canonical_sha256(physical_inputs),
    }


def make_mode_inventory(material: dict[str, object]) -> dict[str, object]:
    calc = material["calculation"]
    n_si = complex(
        calc["solver_refractive_index"]["real"],
        calc["solver_refractive_index"]["imag"],
    )
    s = float(SCALE)
    cfg = SimulationConfig3D(
        case_name="task40extra_nonseparable_0p7nm",
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=WAVELENGTH_NM,
        n_air=1.0 + 0.0j,
        period_x=50.0 * s,
        period_y=25.0 * s,
        z_min=-10.0 * s,
        z_max=130.0 * s,
        interface_z=0.0,
        grating_height=120.0 * s,
        grating_width_x=17.0 * s,
        grating_width_y=25.0 * s,
        n_substrate=n_si,
        n_grating=n_si,
        incident_theta_deg=89.0,
        incident_phi_deg=0.0,
        polarization_kind="s",
        stage4_dtn_order_policy="auto_propagating",
        diffraction_zero_order_only=False,
        diffraction_rayleigh_tol=1.0e-6,
        use_floquet_xy=True,
    )
    orders = enumerate_diffraction_orders_3d(cfg)
    modes = outgoing_port_modes_3d(cfg)
    by_side = {}
    for side in ("top", "bottom"):
        side_modes = [mode for mode in modes if mode.side == side]
        beta_positive = [
            abs(mode.beta) / cfg.k0
            for mode in side_modes
            if mode.propagating
        ]
        order_attr = "top_propagating" if side == "top" else "bottom_propagating"
        warning_attr = "rayleigh_warning_top" if side == "top" else "rayleigh_warning_bottom"
        by_side[side] = {
            "candidate_lattice_orders": len(orders),
            "propagating_orders": sum(bool(getattr(order, order_attr)) for order in orders),
            "evanescent_candidate_orders": sum(not bool(getattr(order, order_attr)) for order in orders),
            "selected_modes": len(side_modes),
            "selected_keys": [
                [mode.m, mode.n, mode.polarization] for mode in side_modes
            ],
            "minimum_propagating_abs_beta_over_k0": min(beta_positive),
            "rayleigh_warning_count_over_candidate_orders": sum(
                bool(getattr(order, warning_attr)) for order in orders
            ),
            "rayleigh_tolerance": cfg.diffraction_rayleigh_tol,
        }
    max_m = max(abs(order.m) for order in orders)
    max_n = max(abs(order.n) for order in orders)
    mode_records = []
    for mode in modes:
        mode_records.append(
            {
                "side": mode.side,
                "key": [mode.m, mode.n, mode.polarization],
                "propagating": mode.propagating,
                "rayleigh_warning": mode.rayleigh_warning,
                "beta_over_k0": [
                    float((mode.beta / cfg.k0).real),
                    float((mode.beta / cfg.k0).imag),
                ],
                "power_per_unit_amplitude": mode.power_per_unit_amplitude,
            }
        )
    return {
        "schema": "task40extra.mode_inventory.v1",
        "status": "ACTUAL_PRODUCTION_MODE_API_DIAGNOSTIC",
        "source_identity": {
            "git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "working_tree_dirty": bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=ROOT, text=True
                ).strip()
            ),
        },
        "generator": "src.common.modes_3d.enumerate_diffraction_orders_3d + outgoing_port_modes_3d",
        "configuration": {
            "wavelength_nm": WAVELENGTH_NM,
            "period_x_nm": cfg.period_x,
            "period_y_nm": cfg.period_y,
            "n_air": [1.0, 0.0],
            "n_substrate": [n_si.real, n_si.imag],
            "n_grating": [n_si.real, n_si.imag],
            "incident_theta_deg_from_downward_minus_z": 89.0,
            "incident_phi_deg": 0.0,
            "polarization": "s",
            "dtn_order_policy": cfg.stage4_dtn_order_policy,
            "rayleigh_warning_tolerance": cfg.diffraction_rayleigh_tol,
            "wavevector_per_nm": [
                float(value.real) for value in cfg.wavevector
            ],
            "dtn_cutoff_rule": (
                "auto bounds from actual k0, incident Bloch vector, periods, "
                "air and substrate indices; retain every propagating order plus "
                "zero order, with both polarizations"
            ),
            "candidate_max_abs_orders": {"m": max_m, "n": max_n},
        },
        "side_statistics": by_side,
        "selected_mode_count": len(modes),
        "modes": mode_records,
        "channel_truncation_qualification": "CHANNEL_TRUNCATION_UNQUALIFIED; no independent cutoff convergence was run",
    }


def main() -> None:
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise SystemExit(
            "Activate the qualified Task40 environment before running this inventory."
        )
    material = make_material_identity()
    geometry = make_geometry_plan()
    modes = make_mode_inventory(material)
    material["geometry_identity_sha256"] = geometry["identity_sha256"]
    mode_identity = canonical_sha256(
        {
            "configuration": modes["configuration"],
            "side_statistics": modes["side_statistics"],
            "selected_keys": {
                side: modes["side_statistics"][side]["selected_keys"]
                for side in ("top", "bottom")
            },
        }
    )
    material["mode_inventory_identity_sha256"] = mode_identity
    material["physical_model_sha256"] = canonical_sha256(
        {
            "material_model_sha256": material["material_model_sha256"],
            "geometry_identity_sha256": geometry["identity_sha256"],
            "incident": {
                "grazing_angle_deg": 1.0,
                "azimuth_deg": 0.0,
                "polarization": "s",
            },
            "mode_inventory_identity_sha256": mode_identity,
        }
    )
    write_json(RECORDS / "material_identity.json", material)
    write_json(RECORDS / "geometry_plan.json", geometry)
    write_json(RECORDS / "mode_inventory.json", modes)
    phase_identity = {
        "schema": "task40extra.phase_i_physical_identity.v1",
        "material_model_sha256": material["material_model_sha256"],
        "physical_model_sha256": material["physical_model_sha256"],
        "geometry_identity_sha256": geometry["identity_sha256"],
        "mode_inventory_identity_sha256": mode_identity,
        "classification": "new physical identity; not inherited from 13.5nm Task39",
    }
    write_json(RECORDS / "phase_i_physical_identity.json", phase_identity)
    print(
        json.dumps(
            {
                "material_model_sha256": material["material_model_sha256"],
                "physical_model_sha256": material["physical_model_sha256"],
                "geometry_identity_sha256": geometry["identity_sha256"],
                "mode_inventory_identity_sha256": phase_identity[
                    "mode_inventory_identity_sha256"
                ],
                "selected_mode_count": modes["selected_mode_count"],
                "mesh_planned_cells": {
                    mesh: geometry["meshes"][mesh]["expected_hexahedra"]
                    for mesh in ("G0", "G1")
                },
                "records_dir": str(RECORDS),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
