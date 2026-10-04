"""Independent physical saved-field integration across exact common subcells.

This module never solves or factors. Envelope coefficients are evaluated with
the physical product derivative; all complex modes and denominators survive.
"""

from itertools import product
import gc
from time import perf_counter
import numpy as np

from src.solvers.fixed_phase_fem import build_model
from src.solvers.fixed_phase_qualification import evaluate
from src.solvers.feinn_discretization_audit import atomic_npz
from src.solvers.feinn_native import load_native
from src.solvers.fixed_phase_reference import ROLES

SAMPLE_ORIGINAL_NM = np.array(
    [[5, 3, -5], [5, 3, 20], [20, 3, 20], [29, 10, 60], [40, 20, 125], [20, 10, 100]]
)


def local_fields(model, cell, coefficients, points):
    """Contract coefficients before Piola/derivative expansion (bounded memory)."""
    import basix
    from scipy import sparse

    V, msh = model["space"], model["data"].mesh
    cache = model.setdefault("_field_static_cache", {})
    key = (len(points), points.tobytes())
    if cache.get("points_key") != key:
        cache.clear()
        cache["points_key"] = key
        cache["tab"] = V.element.basix_element.tabulate(1, points)
        cache["orientation"] = {}
    tab = cache["tab"]
    msh.topology.create_entity_permutations()
    info = int(msh.topology.get_cell_permutation_info()[cell])
    if info not in cache["orientation"]:
        dim = V.element.basix_element.dim
        T = np.eye(dim).ravel()
        V.element.T_apply(T, np.asarray([info], np.uint32), dim)
        cache["orientation"][info] = sparse.csr_matrix(T.reshape(dim, dim))
    c = cache["orientation"][info].T @ coefficients
    vertices = basix.cell.geometry(basix.CellType.hexahedron)
    coords = msh.geometry.x[msh.geometry.dofmap[cell]]
    fit = np.linalg.lstsq(np.column_stack((np.ones(8), vertices)), coords, rcond=None)[
        0
    ]
    J, origin = fit[1:].T, fit[0]
    inv = np.linalg.inv(J)
    E = np.einsum("qia,i->qa", tab[0], c) @ inv
    d = np.einsum("rqia,i,ab,rd->dqb", tab[1:4], c, inv, inv, optimize=True)
    curl = np.column_stack(
        (d[1, :, 2] - d[2, :, 1], d[2, :, 0] - d[0, :, 2], d[0, :, 1] - d[1, :, 0])
    )
    physical = points @ J.T + origin
    g = np.exp(1j * (physical @ model["kappa"]))[:, None]
    return (
        g * E,
        g * (curl + 1j * np.cross(model["kappa"], E)),
        physical,
        np.linalg.det(J),
    )


def channels(model, alpha_scattered, alpha_total):
    from src.solvers.dtn_port_3d import (
        _outgoing_projection,
        _mode_boundary_phase,
        _mode_power_at_boundary,
        _mode_carries_outward_power,
        _port_power_metrics,
    )
    from src.common.modes_3d import incident_power_3d

    cfg, modes = model["cfg"], model["bundle"]["modes"]
    inc = model["bundle"]["incident_projections"]
    outgoing = np.asarray(
        [_outgoing_projection(a, i, m.side) for m, a, i in zip(modes, alpha_total, inc)]
    )
    boundary = outgoing * np.asarray([_mode_boundary_phase(m, cfg) for m in modes])
    powers = np.asarray(
        [
            _mode_power_at_boundary(m, cfg, a) / incident_power_3d(cfg)
            if _mode_carries_outward_power(m)
            else 0.0
            for m, a in zip(modes, outgoing)
        ]
    )
    arrays = dict(
        total_projection=alpha_total,
        scattered_projection=alpha_scattered,
        outgoing_origin=outgoing,
        outgoing_boundary=boundary,
        per_level_power=powers,
    )
    return arrays, _port_power_metrics(cfg, modes, alpha_total, inc)


def self_physics(model, packet, c, alpha, artifact, marker, budget):
    import basix
    from src.common.modes_3d import incident_power_3d

    start = perf_counter()
    qp, qw = basix.make_quadrature(basix.CellType.hexahedron, 15)
    local = packet.expand(c)
    total = packet.expand(c + packet.a["background"])
    norms = np.zeros(4)
    absorption = dict.fromkeys(("air", "substrate", "grating"), 0.0)
    cfg = model["cfg"]
    eps = {
        cfg.tags.air: cfg.eps_r,
        cfg.tags.substrate: cfg.eps_substrate,
        cfg.tags.grating: cfg.eps_grating,
    }
    names = {
        cfg.tags.air: "air",
        cfg.tags.substrate: "substrate",
        cfg.tags.grating: "grating",
    }
    # Save physical full-field values at original volume quadrature, not only
    # coefficients or port traces. Bounded one-cell evaluation.
    rows_e, rows_c, rows_se, rows_sc, points, weights = [], [], [], [], [], []
    for cell in range(packet.nc):
        if cell % 8 == 0:
            budget("physical reconstruction")
        E, C, x, det = local_fields(model, cell, total[cell], qp)
        SE, SC, _, _ = local_fields(model, cell, local[cell], qp)
        w = det * qw
        for i, values in enumerate((E, C / cfg.k0, SE, SC / cfg.k0)):
            norms[i] += np.sum(w * np.sum(abs(values) ** 2, axis=1))
        tag = model["tags"][cell]
        absorption[names[tag]] += (
            0.5
            * cfg.k0
            * complex(eps[tag]).imag
            * np.sum(w * np.sum(abs(E) ** 2, axis=1))
            / incident_power_3d(cfg)
        )
        rows_e.append(E)
        rows_c.append(C)
        rows_se.append(SE)
        rows_sc.append(SC)
        points.append(x)
        weights.append(w)
    arrays, port = channels(model, alpha, alpha + packet.a["background_alpha"])
    modes = model["bundle"]["modes"]
    arrays.update(
        cell_material_tag=np.asarray(model["tags"]),
        cell_epsilon=np.asarray([eps[t] for t in model["tags"]]),
        k0=np.asarray(cfg.k0),
        mu_r=np.asarray(cfg.mu_r),
        incident_power=np.asarray(incident_power_3d(cfg)),
        port_area=np.asarray(cfg.period_x * cfg.period_y),
        mode_keys=np.asarray(
            [[m.side, str(m.m), str(m.n), m.polarization] for m in modes]
        ),
        mode_k=np.asarray([m.k_vector for m in modes]),
        mode_e=np.asarray([m.e_vector for m in modes]),
        mode_boundary_z=np.asarray(
            [
                cfg.physical_z_max if m.side == "top" else cfg.physical_z_min
                for m in modes
            ]
        ),
    )
    sample = SAMPLE_ORIGINAL_NM * 7 / 135
    ET, CT = evaluate(model, packet, c + packet.a["background"], sample)
    ES, CS = evaluate(model, packet, c, sample)
    arrays.update(
        selected_total_E=ET,
        selected_total_H=CT / (1j * cfg.k0 * cfg.mu_r),
        selected_scattered_E=ES,
        selected_scattered_H=CS / (1j * cfg.k0 * cfg.mu_r),
        selected_points_nm=sample,
        quadrature_points_nm=np.asarray(points),
        quadrature_weights_nm3=np.asarray(weights),
        total_E=np.asarray(rows_e),
        total_curl=np.asarray(rows_c),
        total_H=np.asarray(rows_c) / (1j * cfg.k0 * cfg.mu_r),
        scattered_E=np.asarray(rows_se),
        scattered_curl=np.asarray(rows_sc),
        scattered_H=np.asarray(rows_sc) / (1j * cfg.k0 * cfg.mu_r),
        physical_field_norms=np.sqrt(norms),
    )
    atomic_npz(artifact / "observables.npz", **arrays)
    av = float(sum(absorption.values()))
    energy = abs(port["R_total"] + port["T_total"] + av - 1)
    value = dict(
        port=port,
        A_volume=av,
        absorption_regions=absorption,
        energy_closure=energy,
        absorption_balance_gap=abs(port["A_balance"] - av),
        norms=np.sqrt(norms).tolist(),
        norm_order=[
            "total_E",
            "total_scaled_curl",
            "scattered_E",
            "scattered_scaled_curl",
        ],
        physical_H_definition="curl(E)/(i*k0*mu_r); code units",
        integration_degree=15,
        full_complex_channel_families=4,
        channels=len(alpha),
        postprocess_seconds=perf_counter() - start,
        physical_gate_passed=energy <= 1e-5,
    )
    marker("physical_full_field_saved", value)
    return value


def error(diff, reference, natural=1.0):
    absolute = float(np.linalg.norm(diff))
    norm = float(np.linalg.norm(reference))
    denominator = max(norm, natural * 1e-12)
    return dict(
        absolute=absolute,
        original_reference_norm=norm,
        denominator=denominator,
        near_zero=norm < natural * 1e-12,
        natural_scale=natural,
        relative=absolute / denominator,
    )


def compare(indices, artifact, marker, budget):
    import basix
    from src.geometry.fixed_phase_plan import physical_design

    models, packets, states, obs = {}, {}, {}, {}
    for role, idx in indices.items():
        mesh, degree, phase = ROLES[role]
        models[role] = build_model(
            physical_design(mesh), degree, phase, operators=False
        )
        packets[role] = load_native(idx["files"]["native"]["path"])
        with np.load(idx["files"]["field"]["path"], allow_pickle=False) as z:
            states[role] = {
                k: np.array(z[k])
                for k in ("c_scattered", "c_total", "alpha_scattered", "alpha_total")
            }
        with np.load(idx["files"]["observables"]["path"], allow_pickle=False) as z:
            obs[role] = {
                k: np.array(z[k])
                for k in z.files
                if not k.startswith(
                    (
                        "quadrature_",
                        "total_E",
                        "total_H",
                        "total_curl",
                        "scattered_E",
                        "scattered_H",
                        "scattered_curl",
                    )
                )
            }
        if (
            models[role]["record"]["physical_model_sha256"]
            != idx["result"]["identity"]["physical_model_sha256"]
        ):
            raise ValueError("COMPARE_PHYSICAL_IDENTITY_CHANGED")
        for key in (
            "mesh_coordinates_sha256",
            "geometry_cell_dofs_sha256",
            "cell_tags_sha256",
            "mode_manifest_sha256",
            "native_rows",
            "slaves",
            "degree",
        ):
            if models[role]["record"][key] != idx["result"]["identity"][key]:
                raise ValueError("COMPARE_DISCRETE_IDENTITY_CHANGED:" + key)
        if not np.array_equal(
            models[role]["space"].dofmap.list, packets[role].a["cell_dofs"]
        ):
            raise ValueError("COMPARE_COEFFICIENT_CELL_ORDER_CHANGED")
    physical = {
        idx["result"]["identity"]["physical_model_sha256"] for idx in indices.values()
    }
    modes = {
        idx["result"]["identity"]["mode_manifest_sha256"] for idx in indices.values()
    }
    if len(physical) != 1 or len(modes) != 1:
        raise ValueError("CROSS_SPACE_PHYSICS_OR_PORT_KEYS_NOT_IDENTICAL")
    pairs = [(r, "O6") for r in ("O3", "E3", "E4")] + [("E3", "E4")]
    names = ["total_E", "total_scaled_curl", "scattered_E", "scattered_scaled_curl"]
    region_names = ["all", "air", "substrate", "grating", "notch", "interface_band"]
    axes = [
        np.unique(
            np.round(np.concatenate([m["axes"][axis] for m in models.values()]), 14)
        )
        for axis in range(3)
    ]
    local = {
        r: {k: packets[r].expand(c) for k, c in states[r].items() if k.startswith("c_")}
        for r in indices
    }
    geometry_lookup = {}
    for role, model in models.items():
        boxes = np.asarray(
            [
                model["data"].mesh.geometry.x[model["data"].mesh.geometry.dofmap[cell]]
                for cell in range(packets[role].nc)
            ]
        )
        geometry_lookup[role] = (boxes.min(axis=1), boxes.max(axis=1))
    q_results = {}
    for q in (15, 30):
        qp, qw = basix.make_quadrature(basix.CellType.hexahedron, q)
        sums = {
            f"{left}_vs_{right}": np.zeros((len(region_names), 4, 3))
            for left, right in pairs
        }
        for subcell, ijk in enumerate(product(*(range(len(a) - 1) for a in axes))):
            if subcell % 8 == 0:
                budget("common subcell independent comparison")
            low = np.array([axes[j][ijk[j]] for j in range(3)])
            high = np.array([axes[j][ijk[j] + 1] for j in range(3)])
            x = low + qp * (high - low)
            w = np.prod(high - low) * qw
            center = (low + high) / 2
            fields = {}
            for role, model in models.items():
                lows, highs = geometry_lookup[role]
                choices = np.flatnonzero(
                    np.all(center >= lows - 1e-12, axis=1)
                    & np.all(center <= highs + 1e-12, axis=1)
                )
                if len(choices) != 1:
                    raise ValueError("COMMON_SUBCELL_NOT_UNIQUE")
                cell = choices[0]
                coords = model["data"].mesh.geometry.x[
                    model["data"].mesh.geometry.dofmap[cell]
                ]
                fit = np.linalg.lstsq(
                    np.column_stack(
                        (np.ones(8), basix.cell.geometry(basix.CellType.hexahedron))
                    ),
                    coords,
                    rcond=None,
                )[0]
                ref = np.linalg.solve(fit[1:].T, (x - fit[0]).T).T
                E, C, _, _ = local_fields(
                    model, cell, local[role]["c_total"][cell], ref
                )
                SE, SC, _, _ = local_fields(
                    model, cell, local[role]["c_scattered"][cell], ref
                )
                fields[role] = (E, C / model["cfg"].k0, SE, SC / model["cfg"].k0)
            from src.geometry.neural_micro_pilot import material_tags

            g = models["E3"]["design"]["geometry"]
            tags, notch = material_tags(
                x,
                substrate_z=g["substrate_z_nm"],
                block_bounds=g["block_bounds_nm"],
                notch_bounds=g["notch_bounds_nm"],
            )
            cfg = models["E3"]["cfg"]
            masks = [
                np.ones(len(x), bool),
                tags == cfg.tags.air,
                tags == cfg.tags.substrate,
                tags == cfg.tags.grating,
                notch,
            ]
            plane_sets = ([16.5, 25, 33.5], [6.25, 18.75], [0, 40, 80, 120])
            band = np.zeros(len(x), bool)
            for axis, planes in enumerate(plane_sets):
                band |= np.any(
                    abs(x[:, axis, None] - np.asarray(planes) * 7 / 135) <= 7 / 135,
                    axis=1,
                )
            masks.append(band)
            for left, right in pairs:
                for i, (L, R) in enumerate(zip(fields[left], fields[right])):
                    raw = np.column_stack(
                        (
                            np.sum(abs(L - R) ** 2, axis=1),
                            np.sum(abs(R) ** 2, axis=1),
                            np.sum(abs(L) ** 2, axis=1),
                        )
                    )
                    for j, mask in enumerate(masks):
                        sums[f"{left}_vs_{right}"][j, i] += np.sum(
                            w[mask, None] * raw[mask], axis=0
                        )
        q_results[q] = sums
        marker("common_subcell_q" + str(q) + "_complete", dict(subcells=subcell + 1))
    comparisons = {}
    ref_qualified = (
        indices["O6"]["result"]["checker"]["passed"]
        and indices["O6"]["result"]["physics"]["physical_gate_passed"]
    )
    for left, right in pairs:
        key = f"{left}_vs_{right}"
        fields = {}
        for j, reg in enumerate(region_names):
            fields[reg] = {
                name: dict(
                    absolute=float(np.sqrt(row[0])),
                    original_reference_norm=float(np.sqrt(row[1])),
                    candidate_norm=float(np.sqrt(row[2])),
                    denominator=max(float(np.sqrt(row[1])), 1e-12),
                    relative=float(np.sqrt(row[0]))
                    / max(float(np.sqrt(row[1])), 1e-12),
                    near_zero=bool(row[1] < 1e-24),
                )
                for name, row in zip(names, q_results[15][key][j])
            }
        complex_errors = {}
        for name in (
            "selected_total_E",
            "selected_total_H",
            "selected_scattered_E",
            "selected_scattered_H",
            "total_projection",
            "scattered_projection",
            "outgoing_origin",
            "outgoing_boundary",
        ):
            complex_errors[name] = error(
                obs[left][name] - obs[right][name], obs[right][name]
            )
            if name.startswith("selected"):
                for point in range(6):
                    complex_errors[name + "_point_" + str(point)] = error(
                        obs[left][name][point] - obs[right][name][point],
                        obs[right][name][point],
                    )
        powers = {
            name: abs(
                indices[left]["result"]["physics"]["port"][name]
                - indices[right]["result"]["physics"]["port"][name]
            )
            for name in (
                "R_total",
                "T_total",
                "A_balance",
                "R00_s",
                "R00_p",
                "R00_total",
            )
        }
        powers["A_volume"] = abs(
            indices[left]["result"]["physics"]["A_volume"]
            - indices[right]["result"]["physics"]["A_volume"]
        )
        level = float(
            np.max(abs(obs[left]["per_level_power"] - obs[right]["per_level_power"]))
        )
        drift = float(
            np.max(
                abs(q_results[30][key] - q_results[15][key])
                / np.maximum(abs(q_results[30][key]), 1e-24)
            )
        )
        threshold = 1e-3 if right == "E4" else 1e-4
        field_pass = all(
            v["relative"] <= threshold for v in fields["all"].values()
        ) and all(v["relative"] <= threshold for v in complex_errors.values())
        power_pass = max(powers.values()) <= 1e-5 and level <= 1e-6
        comparisons[key] = dict(
            fields=fields,
            complex_errors=complex_errors,
            powers_absolute=powers,
            per_level_power_max_absolute=level,
            q15_q30_squared_integral_relative=drift,
            field_threshold=threshold,
            field_passed=field_pass,
            power_passed=power_pass,
            strict_passed=bool(
                ref_qualified and field_pass and power_pass and drift <= 1e-8
            ),
            reference_status="QUALIFIED_DISCRETE_ONLY" if ref_qualified else "UNKNOWN",
        )
    atomic_npz(
        artifact / "comparison_integrals.npz",
        **{
            f"{key}_q{q}": value
            for q, rows in q_results.items()
            for key, value in rows.items()
        },
    )
    for m in models.values():
        m.get("_field_static_cache", {}).clear()
    gc.collect()
    return dict(
        stage_qualified=True,
        comparisons=comparisons,
        reference_qualified=bool(ref_qualified),
        FE_representation_benefit="UNKNOWN_PENDING_MATCHED_PRECISION_AND_COST",
        neural_gain="NOT_TESTED",
        no_new_solve_or_factor=True,
        sample_points_nm=(SAMPLE_ORIGINAL_NM * 7 / 135).tolist(),
        regions=region_names,
        interface_band_nm=7 / 135,
        common_subcells=int(np.prod([len(a) - 1 for a in axes])),
        continuum_accuracy_qualified=False,
    ), dict(integrals=artifact / "comparison_integrals.npz")
