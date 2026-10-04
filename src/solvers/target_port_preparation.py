"""Original-size configuration, exact tensor counts and bounded-port planning.

This entry never builds a volume mesh, DoF numbering, matrix or solve. The
discretization is a capacity scenario, not a production accuracy assertion.
"""

import hashlib
from pathlib import Path

import numpy as np
import tomllib

from src.common.config_3d import SimulationConfig3D
from src.common.optical_material_table import load_si_optical_constants
from src.geometry.neural_micro_pilot import hexa_inventory
from src.solvers.bounded_port_provider import json_bytes

ROOT = Path(__file__).resolve().parents[2]
SEED = "input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat"
SEED_BASE = "ccd357885f7f9be84efe3be07868cc94f13d93fc"
SEED_BLOB = "0c5211a0e99b4f1b74ad5e4223b5d91066b57816"


def target_config():
    seed = tomllib.loads((ROOT / SEED).read_text())
    g, i = seed["geometry"], seed["incidence"]
    material = load_si_optical_constants(0.7)
    cfg = SimulationConfig3D(
        case_name="task042_v36_target_capacity_only",
        stage_case="stage4_block_grating",
        geometry_kind=g["geometry_kind"],
        lambda0=0.7,
        period_x=g["period_x_nm"],
        period_y=g["period_y_nm"],
        z_min=g["z_min_nm"],
        z_max=g["z_max_nm"],
        air_height=g["air_height_nm"],
        substrate_thickness=g["substrate_thickness_nm"],
        grating_width_x=g["grating_width_x_nm"],
        grating_width_y=g["grating_width_y_nm"],
        grating_height=g["grating_height_nm"],
        interface_z=g["interface_z_nm"],
        n_air=1 + 0j,
        n_substrate=material.n,
        n_grating=material.n,
        mu_r=1 + 0j,
        incident_theta_deg=90 - i["grazing_angle_deg"],
        incident_phi_deg=i["azimuth_deg"],
        polarization_kind=i["polarization"],
        custom_polarization=None,
        incident_amplitude=i["electric_amplitude"],
        use_floquet_xy=True,
        use_pml=False,
        nedelec_degree=6,
        mesh_target_size=0.7,
        mesh_cell_type="hexahedron",
        mesh_spacing_mode="boundary_fitted",
        diffraction_zero_order_only=False,
    )
    return cfg, material


def geometry_contract(cfg, material):
    regular = {
        "bounds_nm": [
            [cfg.x_min, cfg.x_max],
            [cfg.y_min, cfg.y_max],
            [cfg.z_min, cfg.z_max],
        ],
        "block_bounds_nm": [
            [cfg.grating_x_min, cfg.grating_x_max],
            [cfg.grating_y_min, cfg.grating_y_max],
            [0.0, 120.0],
        ],
        "interface_z_nm": 0.0,
        "tags": {
            "air": 1,
            "substrate": 2,
            "grating": 3,
            "x_min": 11,
            "x_max": 12,
            "y_min": 13,
            "y_max": 14,
            "z_min": 15,
            "z_max": 16,
        },
        "reference_planes_nm": {"top": cfg.z_max, "bottom": cfg.z_min},
        "output_probe_planes_nm": {"top": 127.5, "bottom": -7.5},
        "coordinate_convention": "legacy SimulationConfig3D x=[0,50], y=[0,25]; centered block x=[16.5,33.5], y=[0,25]",
        "units": "nm; code-unit E/H amplitudes; exp(-i omega t)",
        "dimensionality": "full three-dimensional Nedelec; no y-invariant reduction",
    }
    # This existing selector is a tag edit at cell midpoints. With legacy
    # non-centered axes x>0 selects the full block x span, y<6.25 the first
    # quarter. Do not silently reinterpret it as a centered half-notch.
    notch = {
        "regular_parent_sha256": hashlib.sha256(json_bytes(regular)).hexdigest(),
        "selector": "positive_x_middle_y_z40_80",
        "source": "src/geometry/cell_notch.py:apply_cell_notch",
        "rule": "grating tag AND x>0 AND abs(y)<period_y/4 AND 40<=z<80",
        "selected_bounds_nm": [[16.5, 33.5], [0.0, 6.25], [40.0, 80.0]],
        "excluded_upper_y_boundary": True,
        "midpoint_tag_rule": True,
        "alignment_required_nm": {
            "x": [0.0, 16.5, 33.5, 50.0],
            "y": [0.0, 6.25, 25.0],
            "z": [-10.0, 0.0, 40.0, 80.0, 120.0, 130.0],
        },
        "not_target_regular_geometry": True,
        "nonseparable_capability_witness_only": True,
        "old_misaligned_mesh_not_an_analytic_notch": True,
    }
    recipe = {
        "schema": "target-port.contract.v1",
        "regular_geometry": regular,
        "regular_geometry_sha256": hashlib.sha256(json_bytes(regular)).hexdigest(),
        "nonseparable_witness": notch,
        "witness_sha256": hashlib.sha256(json_bytes(notch)).hexdigest(),
        "geometry_source": {
            "path": SEED,
            "base_sha": SEED_BASE,
            "blob": SEED_BLOB,
            "current_sha256": hashlib.sha256((ROOT / SEED).read_bytes()).hexdigest(),
        },
        "materials": material.provenance,
        "n_si": [material.n.real, material.n.imag],
        "epsilon_si": [material.epsilon.real, material.epsilon.imag],
        "material_assignment": "substrate/grating/layered background/bottom port use same selected Si",
        "n_air": [1.0, 0.0],
        "mu_r": [1.0, 0.0],
        "nominal_wavelength_nm": "0.7",
        "source_wavelength_nm": "0.699999988",
        "wavelength_nm": 0.7,
        "incidence": {
            "grazing_degrees": 1.0,
            "azimuth_degrees": 0.0,
            "polarization": "s",
            "amplitude": 1.0,
        },
        "boundary": {
            "x": "Floquet",
            "y": "Floquet",
            "vertical": "open DtN",
            "background": "layered",
            "pml": False,
        },
        "capacity_scenario": {
            "degree": 6,
            "maximum_axis_spacing_nm": 0.7,
            "quadrature_degree": 15,
            "status": "CAPACITY_SCENARIO_NOT_ACCURACY_QUALIFIED",
        },
        "status": "TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED",
    }
    recipe["physical_contract_sha256"] = hashlib.sha256(json_bytes(recipe)).hexdigest()
    return recipe


def mode_inventory(cfg):
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

    modes, rows, digest = build_dynamic_mode_inventory(cfg)
    from src.solvers.dtn_port_3d import _mode_boundary_phase, _mode_power_at_boundary

    keys = [(m.side, m.m, m.n, m.polarization) for m in modes]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicated ordered modes")
    # Independent enclosing integer box, enlarged by one; do not copy the
    # outgoing_port_modes loop bounds. Check both side dispersions.
    radius = max(abs(cfg.n_air), abs(cfg.substrate_index)) * cfg.k0
    mx = int(np.ceil((radius + abs(cfg.kx)) * cfg.period_x / (2 * np.pi))) + 1
    my = int(np.ceil((radius + abs(cfg.ky)) * cfg.period_y / (2 * np.pi))) + 1
    expected, dispersion_max = [], 0.0
    for side, nmedium in [("top", cfg.n_air), ("bottom", cfg.substrate_index)]:
        for m in range(-mx, mx + 1):
            for n in range(-my, my + 1):
                a, g = (
                    cfg.kx + 2 * np.pi * m / cfg.period_x,
                    cfg.ky + 2 * np.pi * n / cfg.period_y,
                )
                d = (cfg.k0 * nmedium) ** 2 - a * a - g * g
                beta = np.sqrt(complex(d))
                if beta.imag < -1e-14 or (abs(beta.imag) < 1e-14 and beta.real < 0):
                    beta = -beta
                propagating = beta.real > 1e-12 and d.real > -1e-10 * max(
                    abs(d), abs(beta) ** 2, 1e-30
                )
                if propagating or (m, n) == (0, 0):
                    expected.extend([(side, m, n, "s"), (side, m, n, "p")])
    if keys != expected:
        raise ValueError("independent integer/dispersion inventory disagrees")
    enriched = []
    for mode, row in zip(modes, rows, strict=True):
        d = (cfg.k0 * mode.refractive_index) ** 2 - mode.alpha**2 - mode.gamma**2
        dispersion_max = max(dispersion_max, abs(mode.beta**2 - d) / max(abs(d), 1e-30))
        plane = cfg.z_max if mode.side == "top" else cfg.z_min
        enriched.append(
            dict(
                row,
                reference_plane_nm=plane,
                reference_plane_phase=_mode_boundary_phase(mode, cfg),
                floquet_phases=[
                    np.exp(1j * cfg.kx * cfg.period_x),
                    np.exp(1j * cfg.ky * cfg.period_y),
                ],
                power_at_reference_unit_amplitude=_mode_power_at_boundary(
                    mode, cfg, 1.0
                ),
                original_H_definition="area*||E_t||^2*abs(exp(i*k_z*z_side))^2; original Hp diagonal, NOT Hhat",
            )
        )
    if dispersion_max > 1e-12:
        raise ValueError("mode dispersion identity")
    summary = {
        "mode_count": len(modes),
        "top": sum(m.side == "top" for m in modes),
        "bottom": sum(m.side == "bottom" for m in modes),
        "original_mode_manifest_sha256": digest,
        "enriched_manifest_sha256": hashlib.sha256(json_bytes(enriched)).hexdigest(),
        "integer_enclosing_box": [mx, my],
        "independent_ordered_match": True,
        "maximum_dispersion_relative": dispersion_max,
        "classification_counts": {
            k: sum(row["classification"] == k for row in rows)
            for k in ("propagating", "evanescent", "near-cutoff")
        },
        "truncation_status": "CHANNEL_TRUNCATION_UNQUALIFIED",
        "dot_32060_historical_only": True,
    }
    return enriched, summary


def capacity_plan(cfg, mode_count, *, int_type_bits):
    from src.geometry.mesh_builder_3d import _axis_coordinates, stage4_axis_plan

    plan = stage4_axis_plan(cfg, 1)
    axes = {"x": plan.x_values, "y": plan.y_values, "z": plan.z_values}
    # Align the capability witness independently; do not alter the regular
    # physical object. Only short 1D lists are constructed.
    witness = {
        "x": _axis_coordinates(cfg.x_min, cfg.x_max, 0.7, (0.0, 16.5, 33.5)),
        "y": _axis_coordinates(cfg.y_min, cfg.y_max, 0.7, (0.0, 6.25)),
        "z": _axis_coordinates(-10.0, 130.0, 0.7, (0.0, 40.0, 80.0, 120.0)),
    }
    counts = tuple(len(axes[k]) - 1 for k in ("x", "y", "z"))
    inv = hexa_inventory(counts, 6)
    nx, ny, nz = counts
    if inv["independent_trace_rows"] != 6 * nx * ny * (3 * nz + 2) + 60 * nx * ny * (
        3 * nz + 1
    ):
        raise ValueError("independent periodic entity calibration")
    if hexa_inventory((8, 6, 8), 3) != dict(
        hexa_inventory((8, 6, 8), 3),
        independent_trace_rows=18144,
        interior_rows=13824,
        full_fe_rows=34050,
        periodic_slaves=2082,
    ):
        raise ValueError("frozen micro DoF calibration")
    for a in axes.values():
        if np.max(np.diff(a)) > 0.7 + 1e-12:
            raise ValueError("target maximum axis spacing")
    surface_rows = 2 * nx * ny * 6 + nx * ny * 60
    dense_port_bytes = 16 * mode_count**2
    objects = {
        "full_FE_complex_vector": {
            "bytes": 16 * inv["full_fe_rows"],
            "kind": "exact array payload",
        },
        "active_trace_complex_vector": {
            "bytes": 16 * inv["independent_trace_rows"],
            "kind": "exact array payload",
        },
        "interior_recovery_vector": {
            "bytes": 16 * inv["interior_rows"],
            "kind": "exact array payload",
        },
        "active_full_augmented_vector": {
            "bytes": 16
            * (inv["independent_trace_rows"] + inv["interior_rows"] + mode_count),
            "kind": "exact array payload",
        },
        "GMRES256_vectors": {
            "bytes": 16 * inv["independent_trace_rows"] * 258,
            "kind": "conditional upper only for 258 retained trace vectors; production algorithm unknown",
        },
        "all_cell_dense_full_matrices": {
            "bytes": 16 * inv["cells"] * inv["cell_dimension"] ** 2,
            "kind": "conditional payload if naively retained per cell; NOT required storage",
        },
        "one_cell_dense_full_matrix": {
            "bytes": 16 * inv["cell_dimension"] ** 2,
            "kind": "exact array payload",
        },
        "one_boundary_functional_pair": {
            "bytes": 48 * surface_rows + 8,
            "kind": "conditional full-boundary support; global mode split across owner ranks",
        },
        "resident_all_port_functionals": {
            "bytes": (48 * surface_rows + 8) * mode_count,
            "kind": "conditional payload if all modes resident; omitted by streaming provider",
        },
        "original_Hp_diagonal": {
            "bytes": 16 * mode_count,
            "kind": "exact diagonal payload",
        },
        "one_dense_Hhat_or_port_matrix": {
            "bytes": dense_port_bytes,
            "kind": "one complex128 Nport x Nport array; not assumed diagonal",
        },
        "two_dense_port_arrays": {
            "bytes": 2 * dense_port_bytes,
            "kind": "conditional if input plus LU both live; workspace UNKNOWN",
        },
        "port_amplitudes": {"bytes": 16 * mode_count, "kind": "exact output payload"},
        "integer_DoF_numbering": {
            "bytes": None,
            "kind": "UNKNOWN: excluded here; distributed graph/ghost representation",
        },
        "cell_recovery_class_store": {
            "bytes": None,
            "kind": "UNKNOWN: class count/material/geometry equivalence",
        },
        "MPI_PETSc_JIT_workspace": {"bytes": None, "kind": "UNKNOWN"},
        "solver_iterations_complete_N1": {
            "bytes": None,
            "kind": "UNKNOWN time and storage",
        },
        "IO_cache_shared_factor_lifetimes": {
            "bytes": None,
            "kind": "UNKNOWN; must supply lifecycle plan",
        },
    }
    risk_axes = {
        k: _axis_coordinates(
            float(a[0]),
            float(a[-1]),
            0.175,
            tuple(v for v in a if v in (0.0, 16.5, 33.5, 120.0)),
        )
        for k, a in axes.items()
    }
    risk = hexa_inventory(tuple(len(risk_axes[k]) - 1 for k in ("x", "y", "z")), 3)
    return {
        "schema": "target-port.capacity.v1",
        "axis_cells": list(counts),
        "axes_nm": {k: a.tolist() for k, a in axes.items()},
        "witness_axes_nm": {k: a.tolist() for k, a in witness.items()},
        "maximum_axis_spacing_nm": {
            k: float(np.max(np.diff(a))) for k, a in axes.items()
        },
        "material_plane_alignment": plan.material_plane_alignment,
        "counts": inv,
        "scenario": "p6 / maximum h=.7nm / q15; capacity only",
        "risk_p3_h0175": risk,
        "micro_count_calibration": hexa_inventory((8, 6, 8), 3),
        "int_type_bits": int_type_bits,
        "maximum_row_id": inv["full_fe_rows"] + mode_count - 1,
        "integer_range_pass": inv["full_fe_rows"] + mode_count
        <= 2 ** (int_type_bits - 1),
        "arrays": objects,
        "dense_port_object_origins": [
            "original Hp diagonal",
            "Hhat after interior elimination may be dense",
            "solver LU copy/workspace conditional",
            "no all-mode Gram/N^2 projector authorized",
        ],
        "total_simultaneous_peak_upper_bytes": None,
        "reason": "array bounds are not a complete simultaneous RSS bound",
        "target_task_peak_limit_bytes": 2_000_000_000_000,
        "target_complete_N1_seconds": 172800,
        "target_FE_assembly": "NOT_RUN",
        "target_qualification": "NOT_QUALIFIED",
        "neural20": "NOT_DEMONSTRATED",
    }
