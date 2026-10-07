"""Frozen wave-field samples and an independent, status-free array audit.

No neural forward or optimization is used here. FE sampling is a separate
postprocessing role; the array checker only recomputes original equations,
field norms, channels and absorption from hash-bound saved data.
"""

import hashlib
import json
from pathlib import Path

import numpy as np


def complex_array(value):
    if isinstance(value, dict) and set(value) == {"real", "imag"}:
        return complex(value["real"], value["imag"])
    if isinstance(value, list):
        return np.asarray([complex_array(v) for v in value])
    return np.asarray(value)


def weighted_norm(values, weights):
    return float(np.sqrt(np.sum(weights * np.sum(abs(values) ** 2, axis=-1))))


def relative_error(difference, reference, natural=1.0, *, weights=None):
    norm = (
        (lambda v: weighted_norm(v, weights)) if weights is not None else np.linalg.norm
    )
    numerator = float(norm(difference))
    denominator = float(max(norm(reference), 1e-12 * natural))
    return dict(
        absolute=numerator, denominator=denominator, relative=numerator / denominator
    )


def save_complete_field_samples(
    model, packet, moments, reference, states, artifact, marker
):
    """All cells and components through independent DOLFINx FE evaluation."""
    import basix
    import ufl
    from dolfinx import fem
    from src.common.modes_3d import incident_power_3d
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from src.solvers.learned_coarse_inverse import native_numpy_apply
    from src.solvers.neural_wave_greedy import atomic_npz

    cfg, data, floquet = model["cfg"], model["data"], model["floquet"]
    quad, weights = basix.make_quadrature(basix.CellType.hexahedron, 15)
    nc = len(model["centers"])
    field = fem.Function(floquet.mpc.function_space)
    independent_action = native_numpy_apply(model["bundle"])
    expression = fem.Expression(
        ufl.as_vector(
            [field[j] for j in range(3)] + [ufl.curl(field)[j] for j in range(3)]
        ),
        quad,
    )
    volume_weights = abs(np.linalg.det(moments["jacobians"]))[:, None] * weights[None]
    epsilon = np.zeros(nc)
    epsilon[data.cell_tags.find(cfg.tags.grating)] = complex(cfg.eps_grating).imag
    epsilon[data.cell_tags.find(cfg.tags.substrate)] = complex(cfg.eps_substrate).imag
    arrays = dict(
        weights=volume_weights,
        epsilon_imag=epsilon,
        k0=np.array(cfg.k0),
        mu_r=np.array(cfg.mu_r),
        incident_power=np.array(incident_power_3d(cfg)),
        reference_c=reference,
        background_c=packet.a["background"],
    )
    mpc_checks = {}
    coefficients, offsets = floquet.mpc.coefficients()
    for name, c in {
        "background": packet.a["background"],
        "REFERENCE": reference,
        **states,
    }.items():
        # restore_p0_full_field expands the original MPC once. Sampling copies
        # the expanded coefficients; it does not apply the constraint again.
        restored = restore_p0_full_field(floquet, packet.storage(c))
        field.x.array[:] = restored.x.array
        defect = np.asarray(
            [
                field.x.array[s]
                - np.dot(
                    coefficients[offsets[s] : offsets[s + 1]],
                    field.x.array[floquet.mpc.masters.links(int(s))],
                )
                for s in floquet.mpc.slaves
            ]
        )
        mpc_checks[name] = float(
            np.linalg.norm(defect) / max(np.linalg.norm(field.x.array), 1e-30)
        )
        samples = np.empty((nc, len(quad), 6), np.complex128)
        for first in range(0, nc, 8):
            cells = np.arange(first, min(first + 8, nc), dtype=np.int32)
            samples[first : first + len(cells)] = expression.eval(
                data.mesh, cells
            ).reshape(len(cells), len(quad), 6)
        arrays[name + "_E"] = samples[:, :, :3].copy()
        arrays[name + "_curl"] = samples[:, :, 3:].copy()
        if name not in ("background", "REFERENCE"):
            arrays[name + "_c"] = c
        if name != "background":
            # Retain the actual independently assembled FE action vector, not
            # just the producer's scalar norm. The pure role recomputes its
            # residual and pairs it with the frozen packet action.
            arrays[name + "_independent_total_action"] = independent_action(
                packet.storage(packet.a["background"] + c)
            )[packet.a["masters"]]
        marker(
            "independent_complete_field_samples",
            dict(
                name=name,
                cells=nc,
                quadrature=15,
                samples_per_cell=len(quad),
                MPC_relative=mpc_checks[name],
            ),
        )
    path = Path(artifact) / "complete_FE_field_samples_q15.npz"
    atomic_npz(path, **arrays)
    return path, mpc_checks


def independent_mode_power(physics, outgoing, k0, mu, incident_power):
    """Original outward Poynting power from saved physical k/e, all modes."""
    k, e = (
        complex_array(physics[key])
        for key in ("ordered_mode_k_vectors", "ordered_mode_e_vectors")
    )
    sides = np.asarray(physics["ordered_mode_sides"])
    phase = complex_array(physics["ordered_boundary_phase"])
    if k.shape != (40, 3) or e.shape != (40, 3):
        raise ValueError("COMPLETE_MODE_VECTOR_LAYOUT_REQUIRED")
    if not all(np.isfinite(v).all() for v in (k, e, phase, outgoing)):
        raise ValueError("FINITE_ORIGINAL_MODE_DATA_REQUIRED")
    e_boundary = e * (outgoing * phase)[:, None]
    h_boundary = np.cross(k, e_boundary) / (k0 * mu)
    sign = np.where(sides == "top", 1.0, -1.0)
    density = 0.5 * np.real(np.cross(e_boundary, h_boundary.conj())[:, 2]) * sign
    # The original port convention clips only negative outward power; lossy
    # evanescent modes with positive real flux remain included.
    return np.maximum(density, 0.0) * float(physics["port_area_nm2"]) / incident_power


def check_saved_arrays(action, physics, samples, reconstruction, mpc_checks, identity, *, names=None):
    """Recompute every Gate, ignoring producer status/pass/official labels."""
    names = tuple(names or ("FIXED_WAVE_GREEDY_CONTROL", "LEARNED_WAVE_GREEDY"))
    if set(physics["records"]) != {"REFERENCE", *names}:
        raise ValueError("COMPLETE_TWO_ROUTE_AND_REFERENCE_COVERAGE_REQUIRED")
    mode_manifest = physics["original_mode_manifest"]
    encoded = json.dumps(
        mode_manifest,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    if hashlib.sha256(encoded).hexdigest() != identity["mode_manifest_sha256"]:
        raise ValueError("ORIGINAL_PHYSICAL_MODE_HASH_FAILED")
    mode_rows = mode_manifest["modes"]
    keys = {(v["side"], v["m"], v["n"], v["polarization"]) for v in mode_rows}
    if (
        len(mode_rows) != 40
        or len(keys) != 40
        or [v["mode_index"] for v in mode_rows] != list(range(40))
    ):
        raise ValueError("COMPLETE_UNIQUE_ORDERED_PHYSICAL_MODES_REQUIRED")
    w = samples["weights"]
    if w.ndim != 2 or np.any(w <= 0) or not np.isfinite(w).all():
        raise ValueError("ORIGINAL_POSITIVE_VOLUME_WEIGHTS_REQUIRED")
    k0, mu, inc = (
        float(samples["k0"]),
        complex(samples["mu_r"]),
        float(samples["incident_power"]),
    )
    if not k0 > 0 or not inc > 0 or mu != 1 + 0j:
        raise ValueError("ORIGINAL_M5_UNITS_AND_MATERIAL_REQUIRED")
    if (
        samples["epsilon_imag"].shape != (w.shape[0],)
        or not np.isfinite(samples["epsilon_imag"]).all()
        or np.any(samples["epsilon_imag"] < 0)
        or not float(physics["port_area_nm2"]) > 0
    ):
        raise ValueError("ORIGINAL_PASSIVE_VOLUME_AND_PORT_GEOMETRY_REQUIRED")
    natural = float(np.sqrt(np.sum(w)))
    background = {key: samples["background_" + key] for key in ("E", "curl")}
    ref = physics["records"]["REFERENCE"]
    sides = np.asarray(physics["ordered_mode_sides"])
    if sides.shape != (40,) or not np.all(np.isin(sides, ("top", "bottom"))):
        raise ValueError("COMPLETE_PHYSICAL_SIDE_ALIGNMENT_REQUIRED")
    incident = complex_array(physics["ordered_incident_projection"])
    boundary_phase = complex_array(physics["ordered_boundary_phase"])
    if incident.shape != (40,) or boundary_phase.shape != (40,):
        raise ValueError("ORIGINAL_INCIDENT_AND_REFERENCE_PLANE_ALIGNMENT_REQUIRED")
    bounds = np.asarray(identity["model"]["geometry"]["bounds_nm"])
    area = float(np.prod(bounds[:2, 1] - bounds[:2, 0]))
    expected_k = complex_array([v["k_vector"] for v in mode_rows])
    expected_e = complex_array([v["e_vector"] for v in mode_rows])
    expected_phase = np.exp(
        1j * expected_k[:, 2] * np.where(sides == "top", bounds[2, 1], bounds[2, 0])
    )
    expected_H = (
        area * np.sum(abs(expected_e[:, :2]) ** 2, axis=1) * abs(expected_phase) ** 2
    )
    if (
        [v["side"] for v in mode_rows] != sides.tolist()
        or not np.array_equal(
            expected_k, complex_array(physics["ordered_mode_k_vectors"])
        )
        or not np.array_equal(
            expected_e, complex_array(physics["ordered_mode_e_vectors"])
        )
        or abs(float(physics["port_area_nm2"]) / area - 1) > 1e-12
        or abs(k0 / (2 * np.pi / identity["model"]["wavelength_nm"]) - 1) > 1e-12
        or np.max(abs(boundary_phase - expected_phase)) > 1e-12
        or relative_error(expected_H - action.a["H"], action.a["H"])["relative"] > 1e-10
    ):
        raise ValueError("ORIGINAL_UNITS_H_DIRECTION_AND_REFERENCE_PLANES_REQUIRED")
    for name, record in physics["records"].items():
        c = samples["reference_c"] if name == "REFERENCE" else samples[name + "_c"]
        scattered = action.alpha(c)
        total = action.a["background_alpha"] + scattered
        outgoing = total - np.where(sides == "top", incident, 0)
        for kind, expected in dict(
            scattered=scattered,
            total=total,
            outgoing=outgoing,
            boundary_outgoing=outgoing * boundary_phase,
        ).items():
            actual = complex_array(record["ordered_complex_" + kind + "_channels"])
            if (
                actual.shape != (40,)
                or not np.isfinite(actual).all()
                or relative_error(actual - expected, expected)["relative"] > 1e-10
            ):
                raise ValueError("ORIGINAL_COMPLEX_CHANNEL_DEFINITION_MISMATCH")
    for record in physics["records"].values():
        if any(
            not np.isfinite(float(record["port"][k]))
            for k in ("R_total", "T_total", "A_balance")
        ):
            raise ValueError("FINITE_ORIGINAL_POWER_REQUIRED")
        powers = np.asarray(record["ordered_per_channel_power"])
        if powers.shape != (40,) or not np.isfinite(powers).all():
            raise ValueError("FINITE_ALL_MODE_POWER_REQUIRED")
        if (
            max(
                abs(np.sum(powers[sides == "top"]) - record["port"]["R_total"]),
                abs(np.sum(powers[sides == "bottom"]) - record["port"]["T_total"]),
            )
            > 1e-10
        ):
            raise ValueError("AGGREGATE_AND_PER_MODE_POWER_INCONSISTENT")
        outgoing = complex_array(record["ordered_complex_outgoing_channels"])
        if outgoing.shape != (40,):
            raise ValueError("ALL_OUTGOING_MODES_REQUIRED")
        recomputed = independent_mode_power(physics, outgoing, k0, mu, inc)
        if np.max(abs(powers - recomputed)) > 1e-10:
            raise ValueError("POWER_NOT_FROM_ACTUAL_COMPLEX_MODE_FIELD")
    reference = {key: samples["REFERENCE_" + key] for key in ("E", "curl")}
    for key in background:
        if (
            background[key].shape != w.shape + (3,)
            or reference[key].shape != w.shape + (3,)
            or not np.isfinite(background[key]).all()
            or not np.isfinite(reference[key]).all()
        ):
            raise ValueError("COMPLETE_FIELD_SAMPLE_SHAPE_MISMATCH")
    ref_audit = action.audit(samples["reference_c"])

    def independent_equation(name, c):
        applied = samples[name + "_independent_total_action"]
        expected = action.apply(action.a["background"] + c)
        if applied.shape != expected.shape or not np.isfinite(applied).all():
            raise ValueError("COMPLETE_FINITE_INDEPENDENT_ACTION_REQUIRED")
        pairing = relative_error(applied - expected, expected)["relative"]
        if pairing > 1e-10:
            raise ValueError("INDEPENDENT_FE_AND_NATIVE_ACTION_PAIR_FAILED")
        return relative_error(applied - action.a["total_g"], action.a["total_g"])

    ref_independent = independent_equation("REFERENCE", samples["reference_c"])
    ref_pass = (
        max(
            ref_audit[k]
            for k in (
                "native_relative",
                "augmented_relative",
                "original_total_augmented_relative",
            )
        )
        <= 1e-10
    )
    ref_pass &= ref_independent["relative"] <= 1e-10
    ref_total = reference["E"] + background["E"]
    ref_volume = float(
        0.5
        * k0
        * np.sum(
            w * samples["epsilon_imag"][:, None] * np.sum(abs(ref_total) ** 2, axis=-1)
        )
        / inc
    )
    ref_closure = abs(ref["port"]["R_total"] + ref["port"]["T_total"] + ref_volume - 1)
    ref_pass &= (
        max(
            ref_closure,
            abs(ref["port"]["A_balance"] - ref_volume),
            abs(ref_volume - ref["volume"]["A_volume_total"]),
        )
        <= 1e-5
    )
    records = {}
    for name in names:
        candidate = physics["records"][name]
        errors = {}
        for key in ("E", "curl"):
            field = samples[name + "_" + key]
            if field.shape != w.shape + (3,) or not np.isfinite(field).all():
                raise ValueError("COMPLETE_FINITE_FIELD_REQUIRED")
            scale = 1 if key == "E" else k0
            difference = (field - reference[key]) / scale
            for kind, baseline in [
                ("scattered", reference[key]),
                ("total", reference[key] + background[key]),
            ]:
                errors[kind + "_" + key] = relative_error(
                    difference, baseline / scale, natural, weights=w
                )
                if key == "curl":
                    errors[kind + "_H_code"] = relative_error(
                        difference / 1j, baseline / (1j * k0 * mu), natural, weights=w
                    )
        for key in (
            "selected_total_E",
            "selected_total_H_code",
            "selected_scattered_E",
            "selected_scattered_H_code",
        ):
            a, b = complex_array(candidate[key]), complex_array(ref[key])
            if a.shape != (6, 3) or b.shape != (6, 3):
                raise ValueError("SIX_COMPLEX_FIELD_POINTS_REQUIRED")
            if not np.isfinite(a).all() or not np.isfinite(b).all():
                raise ValueError("FINITE_SIX_COMPLEX_FIELD_POINTS_REQUIRED")
            for i in range(6):
                errors[key + "_" + str(i)] = relative_error(a[i] - b[i], b[i])
        for key in ("total", "scattered", "outgoing", "boundary_outgoing"):
            a, b = (
                complex_array(candidate["ordered_complex_" + key + "_channels"]),
                complex_array(ref["ordered_complex_" + key + "_channels"]),
            )
            if a.shape != (40,) or b.shape != (40,):
                raise ValueError("ALL_FOUR_COMPLETE_40_CHANNEL_KINDS_REQUIRED")
            errors["complex_" + key + "_channels"] = relative_error(a - b, b)
        total = samples[name + "_E"] + background["E"]
        volume = float(
            0.5
            * k0
            * np.sum(
                w * samples["epsilon_imag"][:, None] * np.sum(abs(total) ** 2, axis=-1)
            )
            / inc
        )
        closure = abs(
            candidate["port"]["R_total"] + candidate["port"]["T_total"] + volume - 1
        )
        deltas = {
            k: abs(candidate["port"][k] - ref["port"][k])
            for k in ("R_total", "T_total", "A_balance")
        }
        deltas["A_volume"] = abs(volume - ref_volume)
        power_a, power_b = (
            np.asarray(candidate["ordered_per_channel_power"]),
            np.asarray(ref["ordered_per_channel_power"]),
        )
        if power_a.shape != (40,) or power_b.shape != (40,):
            raise ValueError("COMPLETE_PER_CHANNEL_POWER_REQUIRED")
        power = float(np.max(abs(power_a - power_b)))
        audit = action.audit(samples[name + "_c"])
        independent = independent_equation(name, samples[name + "_c"])
        alpha = action.alpha(samples[name + "_c"])
        total_alpha = action.a["background_alpha"] + alpha
        outgoing = total_alpha - np.where(sides == "top", incident, 0)
        expected_channels = dict(
            scattered=alpha,
            total=total_alpha,
            outgoing=outgoing,
            boundary_outgoing=outgoing * boundary_phase,
        )
        channel_identity = {
            key: relative_error(
                complex_array(candidate["ordered_complex_" + key + "_channels"])
                - expected,
                expected,
            )
            for key, expected in expected_channels.items()
        }
        port = max(audit["port_full_rhs_relative"], audit["port_operation_relative"])
        equation = (
            max(
                audit[k]
                for k in (
                    "native_relative",
                    "augmented_relative",
                    "original_total_augmented_relative",
                )
            )
            <= 1e-6
        )
        equation &= independent["relative"] <= 1e-6
        equation &= port <= 1e-10 and mpc_checks[name] <= 1e-10
        equation &= all(e["relative"] <= 1e-10 for e in channel_identity.values())
        field_pass = all(e["relative"] <= 1e-4 for e in errors.values())
        power_pass = (
            all(v <= 1e-5 for v in deltas.values())
            and closure <= 1e-5
            and power <= 1e-6
            and abs(candidate["port"]["A_balance"] - volume) <= 1e-5
            and abs(volume - candidate["volume"]["A_volume_total"]) <= 1e-5
        )
        rec = reconstruction[name]
        quadrature = (
            max(
                rec[k]
                for k in (
                    "coefficient_q30_q60_relative",
                    "original_action_q30_q60_load_relative",
                    "FE_norm_q15_q30_relative",
                )
            )
            <= 1e-8
        )
        mapping = rec["complete_model_mapping_relative"] <= 1e-10
        joint = bool(
            ref_pass
            and equation
            and field_pass
            and power_pass
            and quadrature
            and mapping
        )
        records[name] = dict(
            equation_audit=audit,
            independent_total_native=independent,
            port_recovery_relative=port,
            MPC_relative=mpc_checks[name],
            field_errors=errors,
            channel_definition_checks=channel_identity,
            A_volume=volume,
            power_absolute_differences=deltas,
            energy_closure=closure,
            max_per_mode_power_absolute=power,
            original_equation_pass=bool(equation),
            field_pass=bool(field_pass),
            power_pass=bool(power_pass),
            quadrature_pass=bool(quadrature),
            model_rebuild_pass=bool(mapping),
            m5_full_discrete_numerical_gate=joint,
            pde_only_solver_qualified=joint,
            official_candidate_results=joint,
            reference_used_for_training=False,
            features_reference_exposed=False,
            pde_only_solve=True,
            benchmark_previously_seen=True,
            production_initialization_allowed=False,
        )
    return dict(
        reference_pass=bool(ref_pass),
        reference_independent_total_native=ref_independent,
        reference_volume_absorption=ref_volume,
        reference_independent_energy_closure=ref_closure,
        records=records,
        statuses_trusted=False,
        full_size_0p7_target_qualified=False,
    )
