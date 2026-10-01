"""Frozen V8 FE compare-only audit; labels are first read here for C.

This module has no Torch imports and never assembles or factors Maxwell/Gram.
"""

from pathlib import Path

import numpy as np
from scipy import sparse

from src.solvers.feinn_native import load_native
from src.solvers.feinn_error_geometry import reference_label
from src.solvers.feinn_fem import build_model
from src.solvers.feinn_reference import field_physics, _region_field_errors
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    destroy_same_mesh_physical_action,
)


def paired(left, right):
    absolute = float(np.linalg.norm(left - right))
    denominator = float(max(np.linalg.norm(right), 1e-12))
    return dict(
        absolute=absolute, denominator=denominator, relative=absolute / denominator
    )


def gram_energy(G, c):
    value = np.vdot(c, G @ c)
    if value.real < -1e-14 or abs(value.imag) > 1e-10 * max(abs(value.real), 1e-30):
        raise ValueError("COMPARISON_GRAM_ENERGY_INVALID")
    return float(max(0.0, value.real))


def norm_identity(energy, l2, scaled_curl, *, ell=5, k0=2 * np.pi / 5):
    physical = float(l2**2 + (ell * k0) ** 2 * scaled_curl**2)
    relative = abs(energy - physical) / max(energy, physical, 1e-30)
    return dict(
        G_energy=energy,
        L2_energy=float(l2**2),
        weighted_scaled_curl_energy=float((ell * k0) ** 2 * scaled_curl**2),
        physical_energy=physical,
        relative=relative,
        passed=relative <= 1e-10,
    )


def compare(
    design,
    native_index,
    reference_index,
    routes,
    reconstructed,
    artifact,
    marker,
    manifest,
    *,
    supervised,
):
    packet = load_native(native_index["files"]["native"]["path"])
    reference, label = reference_label(
        native_index, reference_index, packet, used_for_training=supervised
    )
    G = sparse.load_npz(native_index["files"]["gram"]["path"])
    denominator = gram_energy(G, reference)
    if denominator <= 0:
        raise ValueError("POSITIVE_REFERENCE_GRAM_NORM_REQUIRED")
    states, data, recon_rows, shared_metadata = {}, {}, {}, {}
    for stage, index in routes.items():
        route = index["result"]["route"]
        with np.load(index["files"]["checkpoint"]["path"], allow_pickle=False) as item:
            c = np.array(item["c"])
            if (
                bool(item["reference_used_for_training"]) != supervised
                or bool(item["pde_only_solve"]) == supervised
                or bool(item["production_initialization_allowed"])
            ):
                raise ValueError("COMPARE_FROZEN_LABEL_BOUNDARY_FAILED")
        with np.load(reconstructed["files"][stage]["path"], allow_pickle=False) as item:
            actual, next_c = np.array(item["c"]), np.array(item["c_next"])
            if "c_Adam500" in item.files:
                states[route + "-ADAM500"] = np.array(item["c_Adam500"])
                shared_metadata[route + "-ADAM500"] = dict(
                    shared_work_point_closures=500
                )
            common = reconstructed["result"]["routes"][stage].get("common_wall")
            if common is not None:
                for key, field, suffix in (
                    ("new", "c_common_wall", "-COMMON-WALL"),
                    ("V8", "c_v8_common_wall", "-V8-COMMON-WALL"),
                ):
                    if field in item.files:
                        states[route + suffix] = np.array(item[field])
                        shared_metadata[route + suffix] = common[key]
        identity, quadrature = paired(actual, c), paired(next_c, actual)
        if identity["relative"] > 1e-12:
            raise ValueError("INDEPENDENT_RECONSTRUCTION_IDENTITY_FAILED")
        states[route] = actual
        data[route] = index
        recon_rows[route] = dict(
            parameters_to_saved_c=identity,
            next_quadrature_to_selected=quadrature,
            quadrature_pass=quadrature["relative"] <= 1e-8,
        )
    model = build_model(design, marker=marker)
    try:
        identity = native_index["result"]["identity"]
        if any(
            model["record"][key] != identity[key]
            for key in (
                "mesh_coordinates_sha256",
                "cell_tags_sha256",
                "mode_manifest_sha256",
            )
        ):
            raise ValueError("COMPARE_ORIGINAL_PHYSICAL_IDENTITY_FAILED")
        physics, comparisons = field_physics(
            model,
            packet,
            reference,
            states,
            Path(artifact),
            marker,
            diagnostic_only=supervised,
        )
        ref_norm = physics["reference_scattered_norms"]
        reference_identity = norm_identity(denominator, *ref_norm)
        rows = {}
        for route, c in states.items():
            comp = comparisons[route]
            errors = comp["errors"]
            # With the unchanged constant mu_r, H_code=curl(E)/(i*k0*mu_r).
            # Report absolute H norms, rather than only calling curl an H test.
            mu = abs(complex(model["cfg"].mu_r))
            for kind in ("total", "scattered"):
                err = errors[kind + "_scaled_curl"]
                errors[kind + "_H_code_L2"] = dict(
                    err,
                    absolute=err["absolute"] / mu,
                    denominator=err["denominator"] / mu,
                )
                physics["records"][route][kind + "_H_code_L2_norm"] = float(
                    physics["records"][route][kind + "_L2_scaled_curl_norms"][1] / mu
                )
            energy = gram_energy(G, c - reference)
            norm_pair = norm_identity(
                energy,
                errors["scattered_L2"]["absolute"],
                errors["scattered_scaled_curl"]["absolute"],
                k0=model["cfg"].k0,
            )
            if not norm_pair["passed"] or not reference_identity["passed"]:
                raise ValueError("GRAM_PHYSICAL_L2_CURL_IDENTITY_FAILED")
            eg = float(np.sqrt(energy / denominator))
            if route not in data:
                shared_policy = dict(
                    reference_used_for_training=supervised,
                    features_reference_exposed=supervised,
                    pde_only_solve=not supervised,
                    benchmark_previously_seen=True,
                    production_initialization_allowed=False,
                    pde_only_solver_qualified=False,
                    official_candidate_results=False,
                )
                comp.update(shared_policy, qualified=False)
                physics["records"][route].update(shared_policy)
                rows[route] = dict(
                    shared_work_point=shared_metadata[route],
                    G_field_error=eg,
                    norm_identity=norm_pair,
                    comparisons=comp,
                    **shared_policy,
                )
                continue
            reconstruction = recon_rows[route]
            numerical = bool(
                comp["numerical_reconstruction_pass"]
                and reconstruction["quadrature_pass"]
                and data[route]["result"]["failure"] is None
            )
            qualified = numerical and not supervised
            labels = dict(
                reference_used_for_training=supervised,
                features_reference_exposed=supervised,
                pde_only_solve=not supervised,
                benchmark_previously_seen=True,
                production_initialization_allowed=False,
                pde_only_solver_qualified=qualified,
                official_candidate_results=qualified,
            )
            comp.update(labels, qualified=qualified)
            physics["records"][route].update(labels)
            limits = max(
                eg,
                errors["scattered_L2"]["relative"],
                errors["scattered_scaled_curl"]["relative"],
            )
            if not reconstruction["quadrature_pass"]:
                category = "QUADRATURE_DRIFT"
            elif supervised:
                category = (
                    "REPRESENTATION_WITNESS_POSITIVE"
                    if limits <= 1e-3
                    else "PARTIAL_REPRESENTATION_WITNESS"
                    if limits <= 1e-2
                    else "REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED"
                )
            else:
                category = (
                    "PDE_ONLY_SAME_P3_DISCRETE_PASS"
                    if qualified
                    else "PDE_OPTIMIZATION_NEGATIVE"
                )
            region_scattered = _region_field_errors(model, packet, reference, c)
            region_total = _region_field_errors(
                model,
                packet,
                packet.a["background"] + reference,
                packet.a["background"] + c,
            )
            rows[route] = dict(
                category=category,
                G_field_error=eg,
                G_error_energy=energy,
                G_reference_energy=denominator,
                norm_identity=norm_pair,
                reconstruction=reconstruction,
                comparisons=comp,
                region_scattered=region_scattered,
                region_total=region_total,
                source_sha=data[route]["source_sha"],
                frozen_checkpoint=data[route]["files"]["checkpoint"],
                counts=data[route]["result"]["counts"],
                **labels,
            )
            marker(
                "frozen_new_route_compare",
                dict(
                    route=route,
                    category=category,
                    G_error=eg,
                    native=comp["equation_audit"]["native_relative"],
                    scattered_L2=errors["scattered_L2"]["relative"],
                    scattered_curl=errors["scattered_scaled_curl"]["relative"],
                ),
            )
        phase_name = next(
            index["result"]["route"]
            for index in routes.values()
            if index["result"]["phase"]
        )
        return dict(
            status=(
                "V9_FIT_GN_COMPARE_ONLY_COMPLETE"
                if supervised
                else "V9_PDE_GN_COMPARE_ONLY_COMPLETE"
            )
            if manifest["stage"].startswith("v9_")
            else "V8_REPRESENTATION_COMPARE_ONLY_COMPLETE"
            if supervised
            else "V8_PDE_COMPARE_ONLY_COMPLETE",
            routes=rows,
            physics=physics,
            reference_identity=label,
            reference_G_norm_identity=reference_identity,
            reference_loaded_only_after_candidates_frozen=not supervised,
            reference_recomputed=False,
            phase_strict_qualified=bool(rows[phase_name]["pde_only_solver_qualified"]),
            conditional_D_required=not supervised
            and not rows[phase_name]["pde_only_solver_qualified"],
            G_matvec_count=1 + len(states),
            Gsolve_count=0,
            Gram_factor_created=False,
            MUMPS_symbolic_numeric_solve_count=[0, 0, 0],
            Maxwell_factor_created=False,
            source_sha=manifest["source_sha"],
        ), {}
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
