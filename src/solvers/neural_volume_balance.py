"""Small offline split of original uncondensed Maxwell body action."""

from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.neural_fe_action_packet import array_hash, file_hash


def volume_balance(design, packet, reference, states, artifact, *, heartbeat):
    from petsc4py import PETSc

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _build_split_volume_action,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.neural_fe_pilot import physical_config
    from src.solvers.neural_trace_dolfinx import pilot_space

    cfg, _ = physical_config(design)
    if (
        cfg.use_pml
        or cfg.divergence_penalty != 0
        or cfg.stage4_boundary_model.lower() != "dtn_port"
    ):
        raise ValueError("reviewed original no-PML/no-Robin volume only")
    began = perf_counter()
    _, data, space, _, _, _, _ = pilot_space(design)
    interior = space.element.basix_element.entity_dofs[3][0]
    if not np.array_equal(
        np.asarray(space.dofmap.list)[:, interior], packet.a["idofs"]
    ):
        raise ValueError("original FE coordinate numbering differs")
    floquet = build_double_floquet_mpc(space, data, cfg)
    volume = _build_split_volume_action(
        data,
        cfg,
        space,
        floquet,
        jit_options=SAME_MESH_JIT_OPTIONS,
        volume_quadrature_metadata=(
            {"quadrature_degree": 15},
            {"quadrature_degree": 15},
        ),
    )
    setup_seconds = perf_counter() - began
    source = PETSc.Vec().createSeq(packet.full_rows)
    rows = []
    costs = {
        "setup_seconds": setup_seconds,
        "curl_seconds": 0.0,
        "mass_seconds": 0.0,
        "original_V_seconds": 0.0,
    }
    try:
        reference_field = packet.recover(reference)
        field_map = {"REF7_SCATTERED": reference_field}
        checks = {}
        for name, z in states.items():
            delta = reference - z
            field = packet.recover(delta, rhs_i=np.zeros_like(packet.a["i_rhs"]))
            paired = reference_field - packet.recover(z)
            difference = float(
                np.linalg.norm(field - paired) / max(np.linalg.norm(field), 1e-12)
            )
            if (
                difference > 1e-10
                or np.max(np.abs(field[packet.a["slaves"]]), initial=0) != 0
            ):
                raise ValueError("offline error recovery identity failed")
            checks[name] = {
                "homogeneous_recovery_pair": difference,
                "error_z_sha256": array_hash(delta),
                "default_affine_recover_on_error_used": False,
            }
            field_map[name + "_ERROR"] = field
        for name, field in field_map.items():
            heartbeat("volume_balance_vector", state=name)
            source.array[:] = field
            started = perf_counter()
            curl = np.array(
                volume.component_actions["curl"].apply(source).getArray(readonly=True),
                copy=True,
            )
            costs["curl_seconds"] += perf_counter() - started
            started = perf_counter()
            mass = np.array(
                volume.component_actions["material_mass"]
                .apply(source)
                .getArray(readonly=True),
                copy=True,
            )
            costs["mass_seconds"] += perf_counter() - started
            started = perf_counter()
            original = packet.uncondensed(field, np.zeros(40, np.complex128))[0]
            costs["original_V_seconds"] += perf_counter() - started
            total = curl + mass
            residual = total - original
            scale = float(
                np.linalg.norm(curl) + np.linalg.norm(mass) + np.linalg.norm(original)
            )
            pair = float(np.linalg.norm(residual) / max(scale, 1e-12))
            cross = np.vdot(curl, mass)
            expanded = float(
                np.vdot(curl, curl).real + np.vdot(mass, mass).real + 2 * cross.real
            )
            square = float(np.vdot(total, total).real)
            square_scale = float(
                np.linalg.norm(curl) ** 2 + np.linalg.norm(mass) ** 2 + 2 * abs(cross)
            )
            square_pair = abs(expanded - square) / max(square_scale, 1e-24)
            if max(pair, square_pair) > 1e-10:
                raise ValueError(
                    "original V split/recombination operation identity failed"
                )
            path = Path(artifact) / (name.lower() + "_volume_actions.npz")
            np.savez(
                path,
                field=field,
                curl=curl,
                negative_epsilon_mass=mass,
                original_V=original,
            )
            rows.append(
                {
                    "state": name,
                    "field_coefficient_norm": float(np.linalg.norm(field)),
                    "curl_norm": float(np.linalg.norm(curl)),
                    "negative_epsilon_mass_norm": float(np.linalg.norm(mass)),
                    "original_V_norm": float(np.linalg.norm(original)),
                    "combined_norm": float(np.linalg.norm(total)),
                    "original_boundary_body_norm": 0.0,
                    "boundary_reason": "Original no-PML/no-Robin DtN body V has no surface term; full port coupling unchanged and separately retained in original packet",
                    "complex_curl_mass_inner_product": cross,
                    "expanded_square": expanded,
                    "combined_square": square,
                    "cross_identity_operation_relative": square_pair,
                    "split_original_V_operation_relative": pair,
                    "split_original_V_result_relative": float(
                        np.linalg.norm(residual) / max(np.linalg.norm(original), 1e-12)
                    ),
                    "cancellation_ratio": float(
                        np.linalg.norm(total)
                        / max(np.linalg.norm(curl) + np.linalg.norm(mass), 1e-12)
                    ),
                    "raw": {"path": str(path), "sha256": file_hash(path)},
                    "shared_contributions_assembled_before_norm": True,
                    "separate_condensation": False,
                    "condition_number_or_spectrum_claimed": False,
                }
            )
        return {
            "status": "DIAGNOSTIC_COMPLETED",
            "rows": rows,
            "homogeneous_recovery": checks,
            "costs_seconds": costs,
            "operator_actions": {
                "curl": len(rows),
                "mass": len(rows),
                "packet_V": len(rows),
            },
            "FE_global_CSR_constructed": False,
            "global_factor_constructed": False,
            "accurate_reference_feedback": False,
            "full_region_integral_campaign_repeated": False,
            "borrowed_split_operator_audit": dict(volume.audit),
        }
    finally:
        source.destroy()
        volume.destroy()
