from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse

from benchmarks.run_task033_full3d_watchdog import (
    _parse_args,
    _task035d_selective_face_controlled_negative,
    _worker_command,
    main,
)
from benchmarks.task035d_case097_checker import (
    SIGNIFICANT_REFERENCE_PATH,
    SIGNIFICANT_REFERENCE_SHA256,
    Task035dEvidenceError,
    _bound_candidate_run_directory,
    _candidate_launch_contract,
    _load_selective_face_dwr_evidence,
    evaluate_task035d_case097_candidate,
)
from benchmarks.task035d_case097_gates import (
    TASK035D_CASE097_BACKEND,
    TASK035D_LOCAL_H_ENTITY_CATALOG_SHA256,
    TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256,
    TASK035D_LOCAL_H_PLAN_FILE_SHA256,
    TASK035D_LOCAL_H_TRANSFER_ENTITY_CATALOG_SHA256,
    TASK035D_LOCAL_H_TRANSFER_FLATTENED_GRAPH_SHA256,
)
from benchmarks.task035d_selective_face_case097_gates import (
    TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS,
    TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256,
    TASK035D_SELECTIVE_FACE_AUTHORITY_PATH,
    TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS,
    TASK035D_SELECTIVE_FACE_PHYSICAL_AUTHORITY_SHA256,
    TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256,
    TASK035D_SELECTIVE_FACE_PLAN_NAME,
    TASK035D_SELECTIVE_FACE_PLAN_PATH,
    TASK035D_SELECTIVE_FACE_TRANSFER_ENTITY_CATALOG_SHA256,
    TASK035D_SELECTIVE_FACE_TRANSFER_FLATTENED_GRAPH_SHA256,
    _finite_nonnegative_le,
    task035d_case097_selective_face_plan_authority_gate,
)
from benchmarks.task035d_selective_face_dwr_checker import (
    _csr_sha256,
    _transfer_csr_sha256,
    load_selective_face_coarse_endpoint,
    task035d_selective_face_dwr_report_gate,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / TASK035D_SELECTIVE_FACE_PLAN_PATH
AUTHORITY_PATH = ROOT / TASK035D_SELECTIVE_FACE_AUTHORITY_PATH
SOURCE_SHA = "a" * 40
COARSE_MANIFEST_PATH = Path("/tmp/task035d-test-selective-face/manifest.json").resolve()
COARSE_MANIFEST_SHA256 = "e" * 64
COARSE_ARRAYS_SHA256 = "f" * 64


def _channel_label(channel: dict) -> str:
    prefix = "R" if channel["side"] == "top" else "T"
    return f"{prefix}({channel['m']},{channel['n']})_{channel['polarization']}"


def _goal_label(channel: dict, quantity: str) -> str:
    prefix = "R" if channel["side"] == "top" else "T"
    return (
        f"{prefix}_m{channel['m']}_n{channel['n']}_{channel['polarization']}_{quantity}"
    )


def _relative_gate(*, absolute: float, relative: float) -> dict:
    scale = 1.0
    return {
        "pass": True,
        "error_l2_norm": 0.0,
        "scale_l2_norm": scale,
        "relative_error": 0.0,
        "acceptance_limit": absolute + relative * scale,
    }


def _primal_residual_gate() -> dict:
    return {
        "schema_version": "task035d.primal-residual-gate.v1",
        "checks": {
            "finite": True,
            "nonnegative": True,
            "reduced_trace_dtn_relative_residual_le_1e-9": True,
            "full_explicit_true_relative_residual_le_1e-9": True,
        },
        "limit": 1.0e-9,
        "reduced_trace_dtn_relative_residual": 0.0,
        "full_explicit_true_relative_residual": 0.0,
        "pass": True,
    }


def _linear_residual(rhs_norm: float = 1.0) -> dict:
    return {
        "rhs_norm": float(rhs_norm),
        "residual_norm": 0.0,
        "relative_residual": 0.0,
    }


def _complex_pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _unit_content_identity(seed: str) -> dict:
    size = 18_670
    partitions = []
    for rank in range(8):
        start = size * rank // 8
        end = size * (rank + 1) // 8
        partitions.append(
            {
                "rank": rank,
                "world_rank": rank,
                "ownership_start": start,
                "ownership_end": end,
                "owned_value_count": end - start,
                "owned_content_sha256": hashlib.sha256(
                    f"{seed}:{rank}:{start}:{end}".encode()
                ).hexdigest(),
            }
        )
    communicator_payload = {
        "schema_version": "task035b.mpi-communicator-content.v1",
        "size": 8,
        "ordered_world_ranks": list(range(8)),
    }
    payload = {
        "schema_version": ("task035b.petsc-adjoint-partition-content.v1"),
        "global_size": size,
        "scalar_dtype": "complex128",
        "mpi_size": 8,
        "communicator_content_sha256": hashlib.sha256(
            json.dumps(
                communicator_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "communicator_ordered_world_ranks": list(range(8)),
        "global_value_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "partitions": partitions,
    }
    return {
        **payload,
        "global_content_sha256": hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
    }


def _array_sha256(values: np.ndarray, namespace: str) -> str:
    array = np.ascontiguousarray(values, dtype=np.dtype("<c16"))
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(np.asarray(array.shape, dtype=np.dtype("<i8")).tobytes())
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _json_sha256(value: object, *, namespace: str | None = None) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    digest = hashlib.sha256()
    if namespace is not None:
        digest.update(namespace.encode("ascii"))
        digest.update(b"\0")
    digest.update(encoded)
    return digest.hexdigest()


def _coarse_mode_identity(authority: dict) -> tuple[dict, dict[str, int]]:
    modes = [
        {
            "side": row["channel"]["side"],
            "m": row["channel"]["m"],
            "n": row["channel"]["n"],
            "polarization": row["channel"]["polarization"],
        }
        for row in authority["channels"]
    ]
    modes.extend(
        {
            "side": "top",
            "m": 10_000 + index,
            "n": 0,
            "polarization": "s",
        }
        for index in range(80 - len(modes))
    )
    identity = {
        "mode_count": 80,
        "ordered_modes": modes,
        "ordered_modes_sha256": _json_sha256(
            modes,
            namespace="task035d.ordered-dtn-modes.v1",
        ),
    }
    return (
        identity,
        {_channel_label(mode): index for index, mode in enumerate(modes)},
    )


def _coarse_entity_catalog() -> list[dict]:
    rows = [
        {
            "dimension": 2,
            "geometry_key": list(key),
            "degree": 5,
            "canonical_points": [[index, 0, 0]],
            "mode_count": 40,
        }
        for index, key in enumerate(sorted(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS))
    ]
    rows.append(
        {
            "dimension": 1,
            "geometry_key": [999_999],
            "degree": 5,
            "canonical_points": [[999_999, 0, 0]],
            "mode_count": 23_875 - 40 * len(rows),
        }
    )
    return rows


def _passing_dwr_fixture(authority: dict) -> tuple[dict, dict]:
    face_keys = sorted(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS)
    auxiliary_b = np.zeros(80, dtype=np.complex128)
    incident = np.zeros(80, dtype=np.complex128)
    coordinate_scales = np.ones(80, dtype=np.complex128)
    channels: dict[str, dict] = {}
    basis_goals: dict[str, dict] = {}
    goal_rows: dict[str, dict] = {}
    unit_pairing_content: dict[str, dict] = {}
    accumulated = {
        key: {
            "goal_contributions": {},
            "maximum": 0.0,
            "sum": 0.0,
        }
        for key in face_keys
    }
    for mode_index, authority_row in enumerate(authority["channels"]):
        channel = dict(authority_row["channel"])
        channel_name = _channel_label(channel)
        scale = complex(1.0, 0.005 * (mode_index + 1))
        phase = complex(
            math.cos(0.01 * mode_index),
            math.sin(0.01 * mode_index),
        )
        outgoing_b = complex(
            0.2 + 0.01 * mode_index,
            0.015 * ((mode_index % 3) - 1),
        )
        incoming = complex(0.05, 0.01) if channel["side"] == "top" else 0.0 + 0.0j
        auxiliary_b[mode_index] = outgoing_b + incoming
        incident[mode_index] = incoming
        coordinate_scales[mode_index] = scale
        outgoing_a = outgoing_b + complex(
            1.0e-6 * (mode_index + 1),
            -0.5e-6 * (mode_index + 1),
        )
        unit_effective = scale * (outgoing_a - outgoing_b)
        channel_goal_labels: list[str] = []
        gate = authority_row["unchanged_v0_acceptance_gate"]
        for quantity in (
            "power",
            "amplitude_real",
            "amplitude_imag",
        ):
            label = _goal_label(channel, quantity)
            tolerance = float(
                gate[
                    "power_absolute_tolerance"
                    if quantity == "power"
                    else "complex_amplitude_absolute_tolerance"
                ]
            )
            weight = 0.25 + 0.01 * mode_index
            if quantity == "power":
                value_a = weight * abs(outgoing_a) ** 2
                value_b = weight * abs(outgoing_b) ** 2
                gamma = (
                    2.0 * weight * (0.5 * (outgoing_a + outgoing_b)) / scale.conjugate()
                )
                basis_scalar = 2.0 * weight * outgoing_a / scale.conjugate()
                reported_weight: float | None = weight
                scaling_semantics = "exact_A_B_midpoint_power_gradient"
            else:
                boundary_a = outgoing_a * phase
                boundary_b = outgoing_b * phase
                value_a = (
                    boundary_a.real if quantity == "amplitude_real" else boundary_a.imag
                )
                value_b = (
                    boundary_b.real if quantity == "amplitude_real" else boundary_b.imag
                )
                gamma = (
                    phase.conjugate() / scale.conjugate()
                    if quantity == "amplitude_real"
                    else 1j * phase.conjugate() / scale.conjugate()
                )
                basis_scalar = gamma
                reported_weight = None
                scaling_semantics = "exact_affine_amplitude_gradient"
            global_pairing = gamma.conjugate() * unit_effective
            actual_delta = value_a - value_b
            estimate = global_pairing.real
            residual_bound = 0.0
            roundoff = (
                512.0
                * math.ulp(1.0)
                * max(abs(value_a), abs(value_b), abs(estimate), 1.0)
            )
            closure_limit = 8.0 * (residual_bound + roundoff)
            face_pairings = [
                global_pairing / len(face_keys) for _ in face_keys
            ]
            face_sum = sum(face_pairings, 0.0 + 0.0j)
            face_error = global_pairing - face_sum
            face_absolute_sum = sum(abs(value) for value in face_pairings)
            face_roundoff = (
                512.0
                * math.ulp(1.0)
                * max(
                    abs(global_pairing),
                    face_absolute_sum,
                    tolerance,
                    1.0,
                )
            )
            face_theoretical_limit = 8.0 * (abs(gamma) * 5.0e-9 + face_roundoff)
            face_budget = 0.05 * tolerance
            face_limit = max(
                8.0 * face_roundoff,
                min(face_theoretical_limit, face_budget),
            )
            face_rows = []
            for key, pairing in zip(
                face_keys,
                face_pairings,
                strict=True,
            ):
                signed = pairing.real
                normalized = abs(signed) / tolerance
                face_rows.append(
                    {
                        "geometry_key": list(key),
                        "complex_pairing": [
                            pairing.real,
                            pairing.imag,
                        ],
                        "signed_real_contribution": signed,
                        "absolute_marking_weight": abs(signed),
                        "normalized_absolute_contribution": normalized,
                    }
                )
                accumulated[key]["goal_contributions"][label] = signed
                accumulated[key]["maximum"] = max(
                    float(accumulated[key]["maximum"]),
                    normalized,
                )
                accumulated[key]["sum"] = float(accumulated[key]["sum"]) + normalized
            metadata = {
                "side": channel["side"],
                "m": channel["m"],
                "n": channel["n"],
                "polarization": channel["polarization"],
                "quantity": quantity,
                "label": label,
            }
            basis_goals[label] = {
                "goal": metadata,
                "pass": True,
                "actual_discrete_system": True,
                "auxiliary_mode_index": mode_index,
                "augmented_global_index": 18_590 + mode_index,
                "outgoing_amplitude": _complex_pair(outgoing_a),
                "boundary_phase": _complex_pair(phase),
                "power_weight": reported_weight,
                "gradient_norm": abs(basis_scalar),
                "gradient_scalar_solver_coordinate": _complex_pair(basis_scalar),
                "auxiliary_coordinate_scale": _complex_pair(scale),
                "goal_value": value_a,
                "unit_channel_label": channel_name,
                "unit_adjoint_scalar": _complex_pair(basis_scalar),
                "gradient_scaling_relative_error": 0.0,
                "scaled_adjoint_residual": _linear_residual(abs(basis_scalar)),
                "independent_factor_backsolve_performed": False,
                "recovered_from_unit_channel_adjoint": True,
            }
            channel_goal_labels.append(label)
            goal_rows[label] = {
                "goal": metadata,
                "pass": True,
                "value_a": value_a,
                "value_b": value_b,
                "actual_goal_delta_a_minus_b": actual_delta,
                "signed_dwr_estimate": estimate,
                "signed_goal_closure_error": estimate - actual_delta,
                "goal_closure_limit": closure_limit,
                "unit_adjoint_residual_error_bound": 0.0,
                "unit_adjoint_l2_norm": 1.0,
                "endpoint_closure_does_not_use_partition_error": True,
                "unexplained_residual_complex_pairing": [
                    face_error.real,
                    face_error.imag,
                ],
                "scaling_semantics": scaling_semantics,
                "goal_scalar_inputs": {
                    "quantity": quantity,
                    "coordinate_scale": _complex_pair(scale),
                    "boundary_phase": _complex_pair(phase),
                    "power_weight": reported_weight,
                    "outgoing_a": _complex_pair(outgoing_a),
                    "outgoing_b": _complex_pair(outgoing_b),
                },
                "unit_adjoint_goal_scalar": [gamma.real, gamma.imag],
                "global_complex_pairing": [
                    global_pairing.real,
                    global_pairing.imag,
                ],
                "selected_face_complex_pairing_sum": [
                    face_sum.real,
                    face_sum.imag,
                ],
                "selected_face_pairing_closure_error": [
                    face_error.real,
                    face_error.imag,
                ],
                "selected_face_pairing_closure_limit": face_limit,
                "selected_face_pairing_theoretical_limit": (face_theoretical_limit),
                "selected_face_pairing_tolerance_budget": face_budget,
                "selected_face_pairing_closure_pass": True,
                "face_contributions": face_rows,
                "unchanged_v0_absolute_tolerance": tolerance,
            }
        unit_identity = _unit_content_identity(channel_name)
        channels[channel_name] = {
            "schema_version": "task035d.dtn-unit-channel-gradient.v1",
            "status": "dtn_unit_channel_gradient_built",
            "pass": True,
            "auxiliary_mode_index": mode_index,
            "augmented_global_index": 18_590 + mode_index,
            "gradient_norm": 1.0,
            "solver_coordinate_gradient": [1.0, 0.0],
            "canonical_channel_identity": channel,
            "ordinary_default_changed": False,
            "transpose_converged_reason": 1,
            "adjoint_residual": _linear_residual(),
            "complex_adjoint_equation": "A^H z = g",
            "adjoint_solve_method": (
                "z=conj(KSPSolveTranspose(conj(g))); reuse_forward_direct_factor"
            ),
            "forward_factor_reused": True,
            "goal_labels": channel_goal_labels,
            "goal_count": 3,
            "unit_adjoint_content_identity": unit_identity,
            "unit_adjoint_content_sha256": unit_identity["global_value_sha256"],
            "independent_factor_backsolve_performed": True,
            "unit_adjoint_l2_norm": 1.0,
        }
        unit_pairing_content[channel_name] = {
            "effective": _complex_pair(unit_effective),
            "unexplained": [0.0, 0.0],
            "faces": {
                str(key): _complex_pair(unit_effective / len(face_keys))
                for key in face_keys
            },
            "adjoint_l2_norm": 1.0,
        }
    ranked = [
        {
            "geometry_key": list(key),
            "maximum_normalized_absolute_contribution": (accumulated[key]["maximum"]),
            "sum_normalized_absolute_contribution": (accumulated[key]["sum"]),
            "goal_contributions": accumulated[key]["goal_contributions"],
        }
        for key in sorted(
            face_keys,
            key=lambda key: (-float(accumulated[key]["maximum"]), key),
        )
    ]
    transfer_checks = {
        "same_physical_entity_geometry_catalog": True,
        "only_selected_whole_faces_change_degree": True,
        "full_face_closure_embedding_is_nested": True,
        "edge_to_face_coupling_is_present": True,
        "reference_face_closure_has_no_outside_coupling": True,
        "physical_constraint_graph_injection_closes": True,
        "selected_patch_injection_is_full_rank": True,
        "each_graph_expanded_face_has_20_quotient_modes": True,
        "face_generators_form_direct_sum": True,
        "face_generators_are_global_complement": True,
        "generator_and_orthonormal_projectors_agree": True,
        "face_generator_gram_is_well_conditioned": True,
        "root_dimension_delta_is_20_per_selected_face": True,
        "complement_dimension_is_20_per_selected_face": True,
        "complement_is_solver_coordinate_orthogonal": True,
        "complement_is_solver_coordinate_orthonormal": True,
        "auxiliary_coordinates_are_identity": True,
        "no_hidden_global_p6_matrix": True,
    }
    root_support_catalog = [
        {
            "geometry_key": list(key),
            "physical_closure_rows": 80,
            "independent_root_support_rows": 80,
            "constrained_physical_closure_rows": (
                5 if index == 0 else 0
            ),
            "coarse_root_support_columns": 60,
            "local_injection_rank": 60,
            "local_rank_tolerance": 1.0e-12,
            "local_smallest_singular_value": 0.01,
            "local_condition_number": 240.0,
            "local_complement_dimension": 20,
        }
        for index, key in enumerate(face_keys)
    ]
    face_generator_slices = {
        str(key): [20 * index, 20 * (index + 1)]
        for index, key in enumerate(sorted(face_keys))
    }
    mode_identity, mode_index_by_channel = _coarse_mode_identity(authority)
    entity_catalog = _coarse_entity_catalog()
    mesh_sha256 = "7" * 64
    normalized_config_sha256 = "8" * 64
    incident_projections_sha256 = _array_sha256(
        incident,
        "task035d.selective-face-incident-projections.v1",
    )
    coordinate_scales_sha256 = _array_sha256(
        coordinate_scales,
        "task035d.selective-face-coordinate-scales.v1",
    )
    coarse_candidate = {
        "candidate_id": "h15_top_air_local_h_v1",
        "source_sha": SOURCE_SHA,
        "plan_file_sha256": TASK035D_LOCAL_H_PLAN_FILE_SHA256,
        "actual_full3d_equivalent_active_fe_dofs": 82_925,
        "cell_interior_degree_sha256": "b" * 64,
    }
    endpoint_identity = {
        "source_sha": SOURCE_SHA,
        "mesh_sha256": mesh_sha256,
        "normalized_config_sha256": normalized_config_sha256,
        "ordered_modes_sha256": mode_identity["ordered_modes_sha256"],
        "cell_interior_degree_sha256": "b" * 64,
        "incident_projections_sha256": incident_projections_sha256,
        "auxiliary_coordinate_scales_sha256": coordinate_scales_sha256,
    }
    endpoint_identity_authorities = {
        "schema_version": "task035d.selective-face-endpoint-identities.v1",
        "coarse": endpoint_identity,
        "enriched": dict(endpoint_identity),
    }
    endpoint = {
        "manifest_path": str(COARSE_MANIFEST_PATH),
        "manifest_sha256": COARSE_MANIFEST_SHA256,
        "arrays_sha256": COARSE_ARRAYS_SHA256,
        "source_sha": SOURCE_SHA,
        "candidate": coarse_candidate,
        "significant_channel_authority": {
            "sha256": SIGNIFICANT_REFERENCE_SHA256,
            "physical_channel_count": 12,
            "real_goal_count": 36,
        },
        "mode_identity": mode_identity,
        "mode_index_by_channel": mode_index_by_channel,
        "mesh_identity": {
            "partition_independent_mesh_sha256": mesh_sha256,
        },
        "normalized_config_identity": {
            "normalized_config_sha256": normalized_config_sha256,
        },
        "vector_identity": {
            "incident_projections_sha256": incident_projections_sha256,
            "coordinate_scales_sha256": coordinate_scales_sha256,
        },
        "primal_residual_gate": _primal_residual_gate(),
        "physical_entity_catalog": entity_catalog,
        "physical_entity_catalog_sha256": _json_sha256(
            entity_catalog,
            namespace="task035d.selective-face-entity-catalog.v1",
        ),
        "authority_entity_catalog_sha256": (
            TASK035D_LOCAL_H_ENTITY_CATALOG_SHA256
        ),
        "transfer_entity_catalog_sha256": (
            TASK035D_LOCAL_H_TRANSFER_ENTITY_CATALOG_SHA256
        ),
        "transfer_flattened_graph_sha256": (
            TASK035D_LOCAL_H_TRANSFER_FLATTENED_GRAPH_SHA256
        ),
        "auxiliary_values_b": auxiliary_b,
        "incident_projections": incident,
        "coordinate_scales": coordinate_scales,
    }
    report = {
        "schema_version": "task035d.selective-face-cross-trace-dwr.v1",
        "status": "selective_face_cross_trace_live_dwr_pass",
        "pass": True,
        "controlled_negative": False,
        "ordinary_default_changed": False,
        "same_trace_only": False,
        "actual_cross_trace_primal_prolongation_used": True,
        "coarse_snapshot": {
            "manifest_path": str(COARSE_MANIFEST_PATH),
            "manifest_sha256": COARSE_MANIFEST_SHA256,
            "candidate": coarse_candidate,
        },
        "enriched_candidate": {
            "candidate_id": TASK035D_SELECTIVE_FACE_PLAN_NAME,
            "source_sha": SOURCE_SHA,
            "plan_file_sha256": (TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
            "actual_full3d_equivalent_active_fe_dofs": (
                TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS
            ),
            "cell_interior_degree_sha256": "b" * 64,
        },
        "identity_checks": {
            "same_source_sha": True,
            "same_mesh": True,
            "same_normalized_config": True,
            "same_ordered_modes": True,
            "same_cell_interior_degree_map": True,
            "same_incident_projections": True,
            "same_auxiliary_coordinate_scales": True,
        },
        "endpoint_identity_authorities": endpoint_identity_authorities,
        "root_transfer": {
            "schema_version": ("task035d.selective-face-physical-root-transfer.v2"),
            "status": "selective_face_physical_root_transfer_pass",
            "pass": True,
            "coarse_raw_trace_rows": 23_875,
            "selected_p6_face_count": len(face_keys),
            "selected_p6_face_geometry_keys": [list(key) for key in face_keys],
            "trace_dimension_delta": 200,
            "reference_face_closure_shape": [80, 60],
            "reference_face_closure_rank": 60,
            "reference_face_closure_rank_tolerance": 1.0e-12,
            "reference_face_closure_smallest_singular_value": 0.01,
            "reference_face_closure_condition_number": 240.0,
            "reference_face_generator_face_block_rank": 20,
            "reference_closure_target_from_outside_source_max": 0.0,
            "reference_outside_target_from_closure_source_max": 0.0,
            "reference_face_closure_injection_sha256": "e" * 64,
            "reference_edge_identity_error_max": 0.0,
            "reference_edge_target_face_source_error_max": 0.0,
            "reference_face_target_edge_source_max": 0.5,
            "reference_face_interior_block_error_max": 0.0,
            "affected_root_row_count": 745,
            "affected_coarse_column_count": 545,
            "dense_patch_shape": [745, 545],
            "full_width_dense_transfer_materialized": False,
            "selected_patch_injection_rank": 545,
            "selected_patch_rank_tolerance": 1.0e-12,
            "selected_patch_smallest_singular_value": 0.01,
            "selected_patch_condition_number": 250.0,
            "selected_face_root_support_catalog": root_support_catalog,
            "selected_face_root_support_catalog_sha256": _json_sha256(
                root_support_catalog
            ),
            "face_generator_rank": 200,
            "face_generator_rank_tolerance": 1.0e-12,
            "face_generator_smallest_singular_value": 0.5,
            "face_generator_condition_number": 2.0,
            "face_generator_gram_condition_number": 2.0,
            "face_generator_global_cross_error_max": 0.0,
            "face_generator_projector_error_max": 0.0,
            "face_generator_slices_sha256": _json_sha256(
                face_generator_slices
            ),
            "face_generator_gram_sha256": "a" * 64,
            "coarse_independent_trace_rows": 18_390,
            "enriched_raw_trace_rows": 24_075,
            "enriched_independent_trace_rows": 18_590,
            "auxiliary_rows": 80,
            "coarse_input_identity": {
                "declared_physical_authority_sha256": (
                    TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256
                ),
                "entity_catalog_sha256": (
                    TASK035D_LOCAL_H_TRANSFER_ENTITY_CATALOG_SHA256
                ),
                "flattened_graph_sha256": (
                    TASK035D_LOCAL_H_TRANSFER_FLATTENED_GRAPH_SHA256
                ),
                "raw_trace_rows": 23_875,
                "independent_trace_rows": 18_390,
            },
            "enriched_input_identity": {
                "declared_physical_authority_sha256": (
                    TASK035D_SELECTIVE_FACE_PHYSICAL_AUTHORITY_SHA256
                ),
                "entity_catalog_sha256": (
                    TASK035D_SELECTIVE_FACE_TRANSFER_ENTITY_CATALOG_SHA256
                ),
                "flattened_graph_sha256": (
                    TASK035D_SELECTIVE_FACE_TRANSFER_FLATTENED_GRAPH_SHA256
                ),
                "raw_trace_rows": 24_075,
                "independent_trace_rows": 18_590,
            },
            "changed_entities": [
                {
                    "dimension": 2,
                    "geometry_key": list(key),
                    "coarse_degree": 5,
                    "enriched_degree": 6,
                    "coarse_modes": 40,
                    "enriched_modes": 60,
                }
                for key in face_keys
            ],
            "physical_injection_sha256": "3" * 64,
            "trace_injection_sha256": "c" * 64,
            "total_injection_sha256": "4" * 64,
            "trace_complement_projector_sha256": "d" * 64,
            "complement_basis_sha256_noncanonical": "5" * 64,
            "selected_root_positions_sha256": "6" * 64,
            "complement_basis_is_identity_authority": False,
            "graph_injection_closure_error_max": 0.0,
            "complement_cross_error_max": 0.0,
            "complement_gram_error_max": 0.0,
            "checks": transfer_checks,
            "cross_trace_dwr_scope": (
                "whole non-periodic physical p6 faces with "
                "graph-expanded closure-root support"
            ),
            "periodic_selected_face_backend_supported_but_dwr_v2": False,
            "physical_closure_rows_assumed_independent_roots": False,
            "signed_face_attribution": (
                "direct_sum_face_generators_with_full_gram_decomposition"
            ),
            "ordinary_default_changed": False,
        },
        "galerkin_audit": {
            "schema_version": ("task035d.selective-face-cross-trace-galerkin-audit.v1"),
            "status": "selective_face_cross_trace_galerkin_pass",
            "pass": True,
            "checks": {
                "rhs_galerkin_identity": True,
                "all_operator_galerkin_probes": True,
                "injected_coarse_solution_is_galerkin_orthogonal": True,
                "effective_residual_lies_in_selected_face_complement": True,
            },
            "rhs": _relative_gate(absolute=5.0e-10, relative=2.0e-9),
            "operator_probes": [
                {
                    "probe": index,
                    **_relative_gate(
                        absolute=5.0e-10,
                        relative=2.0e-9,
                    ),
                }
                for index in range(3)
            ],
            "injected_coarse_galerkin_orthogonality": _relative_gate(
                absolute=1.0e-9,
                relative=5.0e-9,
            ),
            "residuals": {
                "coarse_l2_norm": 0.0,
                "enriched_endpoint_l2_norm": 0.0,
                "complement_unexplained_l2_norm": 0.0,
                "complement_unexplained_limit": 5.0e-9,
            },
            "full_matrix_equality_claimed": False,
            "actual_endpoint_dwr_closure_is_mandatory": True,
        },
        "primal_endpoints": {
            "coarse_residual_gate": _primal_residual_gate(),
            "enriched_residual_gate": _primal_residual_gate(),
            "state_delta_l2_norm": 1.0,
        },
        "significant_channel_authority": {
            "sha256": SIGNIFICANT_REFERENCE_SHA256,
            "physical_channel_count": 12,
            "real_goal_count": 36,
        },
        "unit_channel_adjoint_basis": {
            "schema_version": ("task035d.actual-dtn-unit-channel-adjoint-basis.v2"),
            "status": "actual_dtn_unit_channel_adjoint_basis_pass",
            "pass": True,
            "actual_discrete_system": True,
            "ordinary_default_changed": False,
            "requested_real_goal_count": 36,
            "independent_power_goal_count": 12,
            "independent_complex_amplitude_component_goal_count": 24,
            "complete_complex_amplitude_channel_count": 12,
            "physical_channel_count": 12,
            "unit_adjoint_solve_count": 12,
            "uncompressed_adjoint_solve_count": 36,
            "complex_linear_backsolve_basis_rank": 12,
            "expected_complex_linear_backsolve_basis_rank": 12,
            "real_functional_gradient_span_rank": 24,
            "expected_real_functional_gradient_span_rank": 24,
            "one_unit_gradient_per_auxiliary_coordinate": True,
            "per_goal_scaled_adjoint_residual_checked": True,
            "complex_conjugation": "Hermitian A^H, never plain transpose",
            "channels": channels,
            "goals": basis_goals,
        },
        "unit_pairing_content": unit_pairing_content,
        "unit_pairing_content_identity": {
            "schema_version": (
                "task035d.selective-face-unit-pairing-content.v1"
            ),
            "sha256": _json_sha256(
                unit_pairing_content,
                namespace=(
                    "task035d.selective-face-unit-pairings.v1"
                ),
            ),
            "mpi_size": 8,
            "all_ranks_identical": True,
        },
        "goal_dwr": {
            "schema_version": ("task035d.selective-face-live-36-goal-dwr.v1"),
            "status": "selective_face_live_36_goal_dwr_pass",
            "pass": True,
            "requested_real_goal_count": 36,
            "passed_real_goal_count": 36,
            "power_goal_count": 12,
            "power_goal_pass_count": 12,
            "complex_amplitude_component_goal_count": 24,
            "complex_amplitude_component_goal_pass_count": 24,
            "goals": goal_rows,
        },
        "selected_face_multigoal_marking": {
            "face_count": len(face_keys),
            "ranked_faces": ranked,
            "signed_contributions_used_for_goal_closure": True,
            "absolute_contributions_used_for_marking_only": True,
        },
        "formal_boundary": {
            "this_report_qualifies_the_actual_selected_face_action": True,
            "this_report_does_not_select_unrun_faces": True,
            "full_case095_physics_gate_still_independent": True,
            "hybrid_credit_locked_until_full_full3d_gate": True,
        },
    }
    return report, endpoint


class Task035dSelectiveFaceRunnerCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.significant = json.loads(
            SIGNIFICANT_REFERENCE_PATH.read_text(encoding="utf-8")
        )

    def _dwr_gate(self, report: dict, endpoint: dict) -> dict:
        return task035d_selective_face_dwr_report_gate(
            report,
            self.significant,
            endpoint,
            expected_source_sha=SOURCE_SHA,
            expected_coarse_plan_sha256=(TASK035D_LOCAL_H_PLAN_FILE_SHA256),
            expected_enriched_plan_sha256=(TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
            expected_coarse_manifest_sha256=(COARSE_MANIFEST_SHA256),
            expected_significant_channel_authority_sha256=(
                SIGNIFICANT_REFERENCE_SHA256
            ),
        )

    def test_frozen_selective_face_plan_and_authority_gate(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
        gate = task035d_case097_selective_face_plan_authority_gate(
            plan,
            authority,
            expected_plan_file_sha256=(TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
            observed_plan_file_sha256=hashlib.sha256(
                PLAN_PATH.read_bytes()
            ).hexdigest(),
            expected_authority_sha256=(TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256),
            observed_authority_sha256=hashlib.sha256(
                AUTHORITY_PATH.read_bytes()
            ).hexdigest(),
            plan_is_tracked=True,
            authority_is_tracked=True,
            plan_path_from_root=TASK035D_SELECTIVE_FACE_PLAN_PATH,
            authority_path_from_root=(TASK035D_SELECTIVE_FACE_AUTHORITY_PATH),
        )
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(
            gate["plan_identity"]["actual_conforming_active_fe_dofs"],
            TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS,
        )
        drifted = copy.deepcopy(authority)
        drifted["stable_identity"]["selected_p6_face_count"] = 9
        drifted_gate = task035d_case097_selective_face_plan_authority_gate(
            plan,
            drifted,
            expected_plan_file_sha256=(TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
            observed_plan_file_sha256=(TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
            expected_authority_sha256=(TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256),
            observed_authority_sha256=(TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256),
            plan_is_tracked=True,
            authority_is_tracked=True,
            plan_path_from_root=TASK035D_SELECTIVE_FACE_PLAN_PATH,
            authority_path_from_root=(TASK035D_SELECTIVE_FACE_AUTHORITY_PATH),
        )
        self.assertFalse(drifted_gate["pass"])

    def test_dwr_gate_recomputes_goal_and_face_inventories(self) -> None:
        report, endpoint = _passing_dwr_fixture(self.significant)
        gate = self._dwr_gate(report, endpoint)
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertEqual(gate["recomputed_goal_pass_count"], 36)
        self.assertFalse(gate["goal_oriented_selection_credit"])
        self.assertTrue(gate["posthoc_actual_action_attribution"])

        inflated = copy.deepcopy(report)
        first = next(iter(inflated["goal_dwr"]["goals"].values()))
        first["goal_closure_limit"] *= 100.0
        inflated_gate = self._dwr_gate(inflated, endpoint)
        self.assertFalse(inflated_gate["pass"])
        self.assertIn(
            "all_36_goal_closures_recomputed",
            inflated_gate["failures"],
        )

        wrong_goal = copy.deepcopy(report)
        label, row = wrong_goal["goal_dwr"]["goals"].popitem()
        wrong_goal["goal_dwr"]["goals"][f"{label}_forged"] = row
        wrong_goal_gate = self._dwr_gate(wrong_goal, endpoint)
        self.assertFalse(wrong_goal_gate["pass"])
        self.assertIn("goal_inventory_exact", wrong_goal_gate["failures"])

        wrong_face = copy.deepcopy(report)
        first_goal = next(iter(wrong_face["goal_dwr"]["goals"].values()))
        first_goal["face_contributions"][0]["geometry_key"][-1] += 1
        wrong_face_gate = self._dwr_gate(wrong_face, endpoint)
        self.assertFalse(wrong_face_gate["pass"])
        self.assertIn(
            "all_36_goal_closures_recomputed",
            wrong_face_gate["failures"],
        )

    def test_dwr_gate_rejects_forged_raw_identities_and_scalars(self) -> None:
        report, endpoint = _passing_dwr_fixture(self.significant)

        forged_gamma = copy.deepcopy(report)
        first = next(iter(forged_gamma["goal_dwr"]["goals"].values()))
        first["unit_adjoint_goal_scalar"] = [123456.0, -789.0]
        self.assertFalse(self._dwr_gate(forged_gamma, endpoint)["pass"])

        inconsistent_residual = copy.deepcopy(report)
        channel = next(
            iter(
                inconsistent_residual["unit_channel_adjoint_basis"]["channels"].values()
            )
        )
        channel["adjoint_residual"]["residual_norm"] = 1.0
        self.assertFalse(self._dwr_gate(inconsistent_residual, endpoint)["pass"])

        malformed_residual = copy.deepcopy(report)
        channel = next(
            iter(malformed_residual["unit_channel_adjoint_basis"]["channels"].values())
        )
        channel["adjoint_residual"] = [1]
        self.assertFalse(self._dwr_gate(malformed_residual, endpoint)["pass"])

        made_up_identity = copy.deepcopy(report)
        made_up_identity["identity_checks"] = {"made_up": True}
        self.assertFalse(self._dwr_gate(made_up_identity, endpoint)["pass"])

        forged_enriched_mesh = copy.deepcopy(report)
        forged_enriched_mesh["endpoint_identity_authorities"]["enriched"][
            "mesh_sha256"
        ] = "0" * 64
        self.assertFalse(self._dwr_gate(forged_enriched_mesh, endpoint)["pass"])

        forged_enriched_config = copy.deepcopy(report)
        forged_enriched_config["endpoint_identity_authorities"]["enriched"][
            "normalized_config_sha256"
        ] = "0" * 64
        self.assertFalse(self._dwr_gate(forged_enriched_config, endpoint)["pass"])

        invalid_cell_identity = copy.deepcopy(report)
        invalid_cell_identity["enriched_candidate"]["cell_interior_degree_sha256"] = (
            "not-a-digest"
        )
        self.assertFalse(self._dwr_gate(invalid_cell_identity, endpoint)["pass"])

        made_up_transfer = copy.deepcopy(report)
        made_up_transfer["root_transfer"]["checks"] = {"made_up": True}
        self.assertFalse(self._dwr_gate(made_up_transfer, endpoint)["pass"])

        stale_face_interior_transfer = copy.deepcopy(report)
        stale_face_interior_transfer["root_transfer"]["schema_version"] = (
            "task035d.selective-face-physical-root-transfer.v1"
        )
        self.assertFalse(
            self._dwr_gate(stale_face_interior_transfer, endpoint)["pass"]
        )

        missing_edge_coupling = copy.deepcopy(report)
        missing_edge_coupling["root_transfer"][
            "reference_face_target_edge_source_max"
        ] = 0.0
        self.assertFalse(
            self._dwr_gate(missing_edge_coupling, endpoint)["pass"]
        )

        fake_root_support = copy.deepcopy(report)
        for row in fake_root_support["root_transfer"][
            "selected_face_root_support_catalog"
        ]:
            row["constrained_physical_closure_rows"] = 0
        self.assertFalse(
            self._dwr_gate(fake_root_support, endpoint)["pass"]
        )

        negative_norm = copy.deepcopy(report)
        negative_norm["root_transfer"]["complement_gram_error_max"] = -1.0
        self.assertFalse(self._dwr_gate(negative_norm, endpoint)["pass"])

        stale_manifest = copy.deepcopy(report)
        stale_manifest["coarse_snapshot"]["manifest_sha256"] = "0" * 64
        self.assertFalse(self._dwr_gate(stale_manifest, endpoint)["pass"])

        zero_unit_rhs = copy.deepcopy(report)
        channel = next(
            iter(zero_unit_rhs["unit_channel_adjoint_basis"]["channels"].values())
        )
        channel["adjoint_residual"]["rhs_norm"] = 0.0
        self.assertFalse(self._dwr_gate(zero_unit_rhs, endpoint)["pass"])

        wrong_scaled_rhs = copy.deepcopy(report)
        goal = next(
            iter(wrong_scaled_rhs["unit_channel_adjoint_basis"]["goals"].values())
        )
        goal["scaled_adjoint_residual"]["rhs_norm"] = 0.0
        self.assertFalse(self._dwr_gate(wrong_scaled_rhs, endpoint)["pass"])

        duplicated_adjoint = copy.deepcopy(report)
        channels = list(
        duplicated_adjoint["unit_channel_adjoint_basis"]["channels"].values()
        )
        channels[1]["unit_adjoint_content_identity"] = copy.deepcopy(
            channels[0]["unit_adjoint_content_identity"]
        )
        channels[1]["unit_adjoint_content_sha256"] = channels[0][
            "unit_adjoint_content_sha256"
        ]
        self.assertFalse(self._dwr_gate(duplicated_adjoint, endpoint)["pass"])

        divergent_rank_pairing = copy.deepcopy(report)
        first_pairing = next(
            iter(divergent_rank_pairing["unit_pairing_content"].values())
        )
        first_pairing["effective"][0] = 1.0
        self.assertFalse(
            self._dwr_gate(divergent_rank_pairing, endpoint)["pass"]
        )

        self_consistent_but_unlinked_pairing = copy.deepcopy(report)
        first_pairing = next(
            iter(
                self_consistent_but_unlinked_pairing[
                    "unit_pairing_content"
                ].values()
            )
        )
        first_pairing["effective"][0] += 1.0
        self_consistent_but_unlinked_pairing[
            "unit_pairing_content_identity"
        ]["sha256"] = _json_sha256(
            self_consistent_but_unlinked_pairing["unit_pairing_content"],
            namespace="task035d.selective-face-unit-pairings.v1",
        )
        self.assertFalse(
            self._dwr_gate(self_consistent_but_unlinked_pairing, endpoint)["pass"]
        )

        wrong_mode = copy.deepcopy(report)
        channel = next(
            iter(wrong_mode["unit_channel_adjoint_basis"]["channels"].values())
        )
        channel["auxiliary_mode_index"] += 1
        channel["augmented_global_index"] += 1
        self.assertFalse(self._dwr_gate(wrong_mode, endpoint)["pass"])

        malformed_changed_entity = copy.deepcopy(report)
        malformed_changed_entity["root_transfer"]["changed_entities"][0][
            "geometry_key"
        ] = None
        malformed_gate = self._dwr_gate(
            malformed_changed_entity,
            endpoint,
        )
        self.assertFalse(malformed_gate["pass"])

        forged_raw_source = copy.deepcopy(endpoint)
        forged_raw_source["source_sha"] = "0" * 40
        self.assertFalse(self._dwr_gate(report, forged_raw_source)["pass"])

        forged_raw_modes = copy.deepcopy(endpoint)
        forged_raw_modes["mode_identity"]["ordered_modes"][0]["m"] += 1
        self.assertFalse(self._dwr_gate(report, forged_raw_modes)["pass"])

        numerical_negative = copy.deepcopy(report)
        numerical_negative.update(
            {
                "status": "selective_face_cross_trace_live_dwr_fail",
                "pass": False,
                "controlled_negative": True,
                "canonical": False,
                "production_qualified": False,
            }
        )
        numerical_negative["goal_dwr"]["status"] = (
            "selective_face_live_36_goal_dwr_fail"
        )
        numerical_negative["goal_dwr"]["pass"] = False
        self.assertTrue(
            _task035d_selective_face_controlled_negative(
                numerical_negative,
                report_sha256="f" * 64,
            )
        )
        corrupted_evidence = copy.deepcopy(numerical_negative)
        corrupted_evidence["schema_version"] = "forged"
        self.assertFalse(
            _task035d_selective_face_controlled_negative(
                corrupted_evidence,
                report_sha256="f" * 64,
            )
        )
        self.assertFalse(
            _task035d_selective_face_controlled_negative(
                numerical_negative,
                report_sha256=None,
            )
        )
        minimal_stub = {
            "schema_version": ("task035d.selective-face-cross-trace-dwr.v1"),
            "status": "selective_face_cross_trace_live_dwr_fail",
            "pass": False,
            "controlled_negative": True,
            "ordinary_default_changed": False,
        }
        self.assertFalse(
            _task035d_selective_face_controlled_negative(
                minimal_stub,
                report_sha256="f" * 64,
            )
        )

    def test_candidate_requires_dwr_and_all_physics_gates(self) -> None:
        all_pass = {"pass": True}
        watchdog = {
            "return_code": 0,
            "terminated_for_memory": False,
            "terminated_for_timeout": False,
            "terminated_for_authority_unreadable": False,
            "qualification": {"pass": True},
        }
        result = evaluate_task035d_case097_candidate(
            watchdog=watchdog,
            launch_gate=all_pass,
            solver_gate={
                "pass": True,
                "checks": {"ordinary_default_and_lifecycle": True},
            },
            channel_comparison={
                "pass": True,
                "significant_power_pass_count": 12,
                "significant_complex_amplitude_pass_count": 12,
            },
            observable_comparison=all_pass,
            energy_comparison=all_pass,
            field_comparison=all_pass,
            resource_comparison=all_pass,
            actual_channel_dwr={"pass": True},
            candidate_id=TASK035D_SELECTIVE_FACE_PLAN_NAME,
        )
        self.assertTrue(result["pass"])
        self.assertFalse(result["selection_credit"]["goal_oriented_selection_credit"])
        self.assertTrue(result["selection_credit"]["posthoc_actual_action_attribution"])
        self.assertFalse(result["complete_combined_hp_credit"])

        stale_watchdog = copy.deepcopy(watchdog)
        stale_watchdog["qualification"]["pass"] = False
        requalified = evaluate_task035d_case097_candidate(
            watchdog=stale_watchdog,
            launch_gate=all_pass,
            solver_gate={
                "pass": True,
                "checks": {"ordinary_default_and_lifecycle": True},
            },
            channel_comparison={
                "pass": True,
                "significant_power_pass_count": 12,
                "significant_complex_amplitude_pass_count": 12,
            },
            observable_comparison=all_pass,
            energy_comparison=all_pass,
            field_comparison=all_pass,
            resource_comparison=all_pass,
            actual_channel_dwr={"pass": True},
            watchdog_checker_requalified=True,
            candidate_id=TASK035D_SELECTIVE_FACE_PLAN_NAME,
        )
        self.assertTrue(requalified["pass"])
        self.assertTrue(
            requalified["checks"]["watchdog_structural_qualification"]
        )

        no_dwr = evaluate_task035d_case097_candidate(
            watchdog=watchdog,
            launch_gate=all_pass,
            solver_gate={
                "pass": True,
                "checks": {"ordinary_default_and_lifecycle": True},
            },
            channel_comparison={
                "pass": True,
                "significant_power_pass_count": 12,
                "significant_complex_amplitude_pass_count": 12,
            },
            observable_comparison=all_pass,
            energy_comparison=all_pass,
            field_comparison=all_pass,
            resource_comparison=all_pass,
            actual_channel_dwr={"pass": False},
            candidate_id=TASK035D_SELECTIVE_FACE_PLAN_NAME,
        )
        self.assertFalse(no_dwr["pass"])
        self.assertIn(
            "actual_cross_trace_36_goal_dwr",
            no_dwr["failures"],
        )

        eleven_power = copy.deepcopy(result["channel_comparison"])
        eleven_power["significant_power_pass_count"] = 11
        physics_fail = evaluate_task035d_case097_candidate(
            watchdog=watchdog,
            launch_gate=all_pass,
            solver_gate={
                "pass": True,
                "checks": {"ordinary_default_and_lifecycle": True},
            },
            channel_comparison=eleven_power,
            observable_comparison=all_pass,
            energy_comparison=all_pass,
            field_comparison=all_pass,
            resource_comparison=all_pass,
            actual_channel_dwr={"pass": True},
            candidate_id=TASK035D_SELECTIVE_FACE_PLAN_NAME,
        )
        self.assertFalse(physics_fail["pass"])

    def test_launch_contract_binds_cross_trace_inputs(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
        embedded = task035d_case097_selective_face_plan_authority_gate(
            plan,
            authority,
            expected_plan_file_sha256=(TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
            observed_plan_file_sha256=(TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
            expected_authority_sha256=(TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256),
            observed_authority_sha256=(TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256),
            plan_is_tracked=True,
            authority_is_tracked=True,
            plan_path_from_root=TASK035D_SELECTIVE_FACE_PLAN_PATH,
            authority_path_from_root=(TASK035D_SELECTIVE_FACE_AUTHORITY_PATH),
        )
        self.assertTrue(embedded["pass"])
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text('{"snapshot": true}\n', encoding="utf-8")
            manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
            run_dir = Path(temporary) / "run"
            run_dir.mkdir()
            descriptor_path = run_dir / "parent_launch_descriptor.json"
            worker_contract = {
                "degree": 6,
                "h_nm": 15.0,
                "polarization_kind": "s",
                "run_kind": "full-solve",
                "mpi_size": 8,
                "profile": "default",
                "run_dir": str(run_dir.resolve()),
                "stage4_full3d_assembly_backend": (TASK035D_CASE097_BACKEND),
                "task035d_case097_gate": True,
                "task035d_candidate_id": (TASK035D_SELECTIVE_FACE_PLAN_NAME),
                "task035d_nested_p_dwr_phase": None,
                "task035d_selective_face_dwr_phase": ("enriched-evaluate"),
                "task035d_plan_authority_sha256": (
                    TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256
                ),
                "task035d_significant_channel_authority_sha256": (
                    SIGNIFICANT_REFERENCE_SHA256
                ),
                "task035d_coarse_snapshot_manifest_sha256": None,
                "task035d_selective_face_coarse_manifest_sha256": (manifest_sha),
                "verified_clean_sha": SOURCE_SHA,
            }
            parent_payload = {
                "schema_version": "task033.watchdog-parent-launch.v1",
                "token_sha256": "8" * 64,
                "parent_process": {
                    "pid": 100,
                    "parent_pid": 10,
                    "start_time_ticks": 123,
                    "role": "resource_watchdog_parent",
                },
                "worker_contract": worker_contract,
            }
            descriptor_path.write_text(
                json.dumps(
                    parent_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            descriptor_sha = hashlib.sha256(descriptor_path.read_bytes()).hexdigest()
            command = [
                "mpiexec",
                "-n",
                "8",
                str(ROOT / ".venv" / "bin" / "python"),
                "-m",
                "benchmarks.run_task033_full3d_watchdog",
                "--worker",
                "--degree",
                "6",
                "--h-nm",
                "15.0",
                "--polarization-kind",
                "s",
                "--run-kind",
                "full-solve",
                "--mpi-size",
                "8",
                "--profile",
                "default",
                "--stage4-full3d-assembly-backend",
                TASK035D_CASE097_BACKEND,
                "--run-dir",
                str(run_dir),
                "--stage4-local-h-refinement-plan",
                str(PLAN_PATH),
                "--stage4-local-h-refinement-plan-sha256",
                TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256,
                "--task035d-case097-gate",
                "--task035d-candidate-id",
                TASK035D_SELECTIVE_FACE_PLAN_NAME,
                "--task035d-plan-authority",
                str(AUTHORITY_PATH),
                "--task035d-plan-authority-sha256",
                TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256,
                "--task035d-selective-face-dwr-phase",
                "enriched-evaluate",
                "--task035d-significant-channel-authority",
                str(SIGNIFICANT_REFERENCE_PATH),
                "--task035d-significant-channel-authority-sha256",
                SIGNIFICANT_REFERENCE_SHA256,
                "--task035d-selective-face-coarse-manifest",
                str(manifest),
                "--task035d-selective-face-coarse-manifest-sha256",
                manifest_sha,
                "--verified-clean-sha",
                SOURCE_SHA,
                "--parent-launch-descriptor",
                str(descriptor_path),
                "--parent-launch-descriptor-sha256",
                descriptor_sha,
            ]
            selective_launch = {
                "schema_version": (
                    "task035d.selective-face-cross-trace-launch-gate.v1"
                ),
                "phase": "enriched-evaluate",
                "pass": True,
                "failures": [],
                "checks": {"all_inputs": True},
                "significant_channel_authority": {
                    "path": str(SIGNIFICANT_REFERENCE_PATH.relative_to(ROOT)),
                    "sha256": SIGNIFICANT_REFERENCE_SHA256,
                },
                "coarse_snapshot": {
                    "path": str(manifest.resolve()),
                    "sha256": manifest_sha,
                    "artifact_gate": {"pass": True},
                },
                "same_trace_only": False,
                "cross_trace_primal_prolongation": True,
                "dense_local_schur_persistence": False,
            }
            record = {
                "command": command,
                "task035d_candidate_id": (TASK035D_SELECTIVE_FACE_PLAN_NAME),
                "task035d_case097_launch_gate": embedded,
                "task035d_selective_face_launch_gate": selective_launch,
                "resource_policy": {"swap_allowed": False},
                "no_swap": True,
                "task035d_accuracy_credit": (
                    "pending_independent_12_channel_and_field_checker"
                ),
                "parent_launch_descriptor": {
                    "path": str(descriptor_path),
                    "sha256": descriptor_sha,
                    "payload": parent_payload,
                    "secret_token_persisted": False,
                },
            }
            contract = _candidate_launch_contract(
                record,
                source_sha=SOURCE_SHA,
                candidate_id=TASK035D_SELECTIVE_FACE_PLAN_NAME,
            )
            self.assertTrue(contract["pass"])
            self.assertEqual(contract["run_dir"], str(run_dir.resolve()))
            self.assertEqual(
                _bound_candidate_run_directory(
                    {"run_directory": str(run_dir)},
                    contract,
                ),
                run_dir.resolve(),
            )
            other_run = Path(temporary) / "other-run"
            other_run.mkdir()
            with self.assertRaisesRegex(ValueError, "directories differ"):
                _bound_candidate_run_directory(
                    {"run_directory": str(other_run)},
                    contract,
                )
            forged = copy.deepcopy(record)
            index = forged["command"].index(
                "--task035d-significant-channel-authority-sha256"
            )
            forged["command"][index + 1] = "0" * 64
            with self.assertRaises(ValueError):
                _candidate_launch_contract(
                    forged,
                    source_sha=SOURCE_SHA,
                    candidate_id=TASK035D_SELECTIVE_FACE_PLAN_NAME,
                )
            bypass = copy.deepcopy(record)
            for option in (
                "--parent-launch-descriptor-sha256",
                "--parent-launch-descriptor",
            ):
                option_index = bypass["command"].index(option)
                del bypass["command"][option_index : option_index + 2]
            with self.assertRaises(ValueError):
                _candidate_launch_contract(
                    bypass,
                    source_sha=SOURCE_SHA,
                    candidate_id=TASK035D_SELECTIVE_FACE_PLAN_NAME,
                )

    def test_runner_parser_and_worker_command_preserve_dwr_endpoints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text('{"snapshot": true}\n', encoding="utf-8")
            manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
            cli = [
                "--degree",
                "6",
                "--h-nm",
                "15",
                "--polarization-kind",
                "s",
                "--run-kind",
                "full-solve",
                "--mpi-size",
                "8",
                "--profile",
                "default",
                "--stage4-full3d-assembly-backend",
                TASK035D_CASE097_BACKEND,
                "--task035d-case097-gate",
                "--task035d-candidate-id",
                TASK035D_SELECTIVE_FACE_PLAN_NAME,
                "--stage4-local-h-refinement-plan",
                str(PLAN_PATH),
                "--stage4-local-h-refinement-plan-sha256",
                TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256,
                "--task035d-plan-authority",
                str(AUTHORITY_PATH),
                "--task035d-plan-authority-sha256",
                TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256,
                "--task035d-selective-face-dwr-phase",
                "enriched-evaluate",
                "--task035d-significant-channel-authority",
                str(SIGNIFICANT_REFERENCE_PATH),
                "--task035d-significant-channel-authority-sha256",
                SIGNIFICANT_REFERENCE_SHA256,
                "--task035d-selective-face-coarse-manifest",
                str(manifest),
                "--task035d-selective-face-coarse-manifest-sha256",
                manifest_sha,
                "--verified-clean-sha",
                SOURCE_SHA,
            ]
            args = _parse_args(cli)
            command = _worker_command(
                args,
                Path(temporary) / "run",
            )
            self.assertEqual(
                command[command.index("--task035d-selective-face-dwr-phase") + 1],
                "enriched-evaluate",
            )
            self.assertEqual(
                command[
                    command.index("--task035d-selective-face-coarse-manifest-sha256")
                    + 1
                ],
                manifest_sha,
            )

            mutually_exclusive = [
                *cli,
                "--task035d-nested-p-dwr-phase",
                "enriched-evaluate",
            ]
            with self.assertRaises(SystemExit):
                _parse_args(mutually_exclusive)

    def test_coarse_endpoint_loader_and_worker_parent_gate(self) -> None:
        self.assertTrue(_finite_nonnegative_le(0.0, 1.0e-9))
        self.assertFalse(_finite_nonnegative_le(-1.0, 1.0e-9))
        self.assertFalse(_finite_nonnegative_le(-math.inf, 1.0e-9))
        self.assertFalse(_finite_nonnegative_le(math.nan, 1.0e-9))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            arrays_path = root / "coarse_arrays.npz"
            passing_report, passing_endpoint = _passing_dwr_fixture(self.significant)
            auxiliary = np.asarray(
                passing_endpoint["auxiliary_values_b"],
                dtype=np.complex128,
            )
            incident = np.asarray(
                passing_endpoint["incident_projections"],
                dtype=np.complex128,
            )
            scales = np.asarray(
                passing_endpoint["coordinate_scales"],
                dtype=np.complex128,
            )
            state = np.zeros(18_470, dtype=np.complex128)
            rhs = np.zeros(18_470, dtype=np.complex128)
            rhs[0] = 1.0
            action = rhs.copy()
            residual = rhs - action
            probes = np.zeros((18_470, 3), dtype=np.complex128)
            probes[0, 0] = 1.0
            probes[-1, 1] = 1.0
            probes[1, 2] = 1.0 / math.sqrt(2.0)
            probes[-1, 2] = 1.0 / math.sqrt(2.0)
            probe_actions = np.zeros_like(probes)
            graph = sparse.vstack(
                (
                    sparse.eye(18_390, dtype=np.complex128, format="csr"),
                    sparse.csr_matrix(
                        (23_875 - 18_390, 18_390),
                        dtype=np.complex128,
                    ),
                ),
                format="csr",
            )
            np.savez(
                arrays_path,
                schema_version=np.asarray(["task035d.selective-face-coarse-arrays.v1"]),
                state_b=state,
                rhs_b=rhs,
                action_b_on_b=action,
                residual_b=residual,
                probe_vectors=probes,
                probe_actions=probe_actions,
                auxiliary_values_b=auxiliary,
                incident_projections=incident,
                coordinate_scales=scales,
                physical_graph_data=np.asarray(
                    graph.data,
                    dtype=np.complex128,
                ),
                physical_graph_indices=np.asarray(
                    graph.indices,
                    dtype=np.int64,
                ),
                physical_graph_indptr=np.asarray(
                    graph.indptr,
                    dtype=np.int64,
                ),
                physical_graph_shape=np.asarray(
                    graph.shape,
                    dtype=np.int64,
                ),
            )
            arrays_sha = hashlib.sha256(arrays_path.read_bytes()).hexdigest()
            mode_identity, _mode_map = _coarse_mode_identity(self.significant)
            entity_catalog = _coarse_entity_catalog()
            normalized_config = {"fixture": "coarse"}
            transfer_catalog_sha = _json_sha256(entity_catalog)
            authority_catalog_sha = _json_sha256(
                [
                    [
                        row["dimension"],
                        row["geometry_key"],
                        row["canonical_points"],
                        row["mode_count"],
                    ]
                    for row in entity_catalog
                ]
            )
            transfer_graph_sha = _transfer_csr_sha256(graph)
            fixture_candidate = {
                "candidate_id": "h15_top_air_local_h_v1",
                "source_sha": SOURCE_SHA,
                "plan_file_sha256": (TASK035D_LOCAL_H_PLAN_FILE_SHA256),
                "actual_full3d_equivalent_active_fe_dofs": 82_925,
                "cell_interior_degree_sha256": "b" * 64,
            }
            physical_graph_sha = _csr_sha256(
                graph,
                namespace="task035d.selective-face-physical-graph.v1",
            )
            normalized_config_sha = _json_sha256(
                normalized_config,
                namespace="task035d.same-trace-physics-config.v1",
            )
            fixture_mesh_sha = "9" * 64
            manifest = {
                "schema_version": ("task035d.selective-face-coarse-snapshot.v1"),
                "status": "selective_face_coarse_snapshot_pass",
                "pass": True,
                "ordinary_default_changed": False,
                "base_trace_degree": 5,
                "independent_trace_rows": 18_390,
                "auxiliary_rows": 80,
                "matrix_rows": 18_470,
                "source_sha": SOURCE_SHA,
                "candidate": fixture_candidate,
                "significant_channel_authority": {
                    "sha256": SIGNIFICANT_REFERENCE_SHA256,
                    "physical_channel_count": 12,
                    "real_goal_count": 36,
                },
                "mode_identity": mode_identity,
                "normalized_config_identity": {
                    "normalized_config": normalized_config,
                    "normalized_config_sha256": normalized_config_sha,
                },
                "mesh_identity": {
                    "partition_independent_mesh_sha256": fixture_mesh_sha,
                },
                "primal_residual_gate": _primal_residual_gate(),
                "physical_entity_catalog": entity_catalog,
                "physical_entity_catalog_sha256": _json_sha256(
                    entity_catalog,
                    namespace=("task035d.selective-face-entity-catalog.v1"),
                ),
                "physical_root_raw_indices": list(range(18_390)),
                "physical_graph_sha256": physical_graph_sha,
                "physical_authority_sha256": (
                    TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256
                ),
                "matrix_vector_ownership_ranges": [
                    [
                        18_470 * rank // 8,
                        18_470 * (rank + 1) // 8,
                    ]
                    for rank in range(8)
                ],
                "probe_contract": {
                    "probe_count": 3,
                    "roles": [
                        "trace_only_random",
                        "auxiliary_only_random",
                        "combined_random",
                    ],
                    "seed_identity": {
                        "candidate": fixture_candidate,
                        "mesh_sha256": fixture_mesh_sha,
                        "config_sha256": normalized_config_sha,
                        "mode_sha256": mode_identity["ordered_modes_sha256"],
                        "physical_graph_sha256": physical_graph_sha,
                    },
                    "probe_vectors_sha256": _array_sha256(
                        probes,
                        "task035d.selective-face-probes.v1",
                    ),
                    "probe_actions_sha256": _array_sha256(
                        probe_actions,
                        "task035d.selective-face-probe-actions.v1",
                    ),
                },
                "arrays": {
                    "path": "coarse_arrays.npz",
                    "sha256": arrays_sha,
                },
                "vector_identity": {
                    "state_b_sha256": _array_sha256(
                        state,
                        "task035d.selective-face-state-b.v1",
                    ),
                    "rhs_b_sha256": _array_sha256(
                        rhs,
                        "task035d.selective-face-rhs-b.v1",
                    ),
                    "action_b_on_b_sha256": _array_sha256(
                        action,
                        "task035d.selective-face-action-b.v1",
                    ),
                    "residual_b_sha256": _array_sha256(
                        residual,
                        "task035d.selective-face-residual-b.v1",
                    ),
                    "auxiliary_values_b_sha256": _array_sha256(
                        auxiliary,
                        "task035d.selective-face-auxiliary-values-b.v1",
                    ),
                    "incident_projections_sha256": _array_sha256(
                        incident,
                        "task035d.selective-face-incident-projections.v1",
                    ),
                    "coordinate_scales_sha256": _array_sha256(
                        scales,
                        "task035d.selective-face-coordinate-scales.v1",
                    ),
                    "relative_residual": 0.0,
                },
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            with (
                patch(
                    "benchmarks.task035d_selective_face_dwr_checker."
                    "TASK035D_LOCAL_H_ENTITY_CATALOG_SHA256",
                    authority_catalog_sha,
                ),
                patch(
                    "benchmarks.task035d_selective_face_dwr_checker."
                    "TASK035D_LOCAL_H_TRANSFER_ENTITY_CATALOG_SHA256",
                    transfer_catalog_sha,
                ),
                patch(
                    "benchmarks.task035d_selective_face_dwr_checker."
                    "TASK035D_LOCAL_H_TRANSFER_FLATTENED_GRAPH_SHA256",
                    transfer_graph_sha,
                ),
            ):
                endpoint = load_selective_face_coarse_endpoint(
                    manifest_path,
                    expected_manifest_sha256=manifest_sha,
                )
                passing_report["coarse_snapshot"] = {
                    "manifest_path": str(manifest_path),
                    "manifest_sha256": manifest_sha,
                    "candidate": fixture_candidate,
                }
                passing_report["root_transfer"]["coarse_input_identity"][
                    "entity_catalog_sha256"
                ] = transfer_catalog_sha
                passing_report["root_transfer"]["coarse_input_identity"][
                    "flattened_graph_sha256"
                ] = transfer_graph_sha
                raw_endpoint_identity = {
                    "source_sha": endpoint["source_sha"],
                    "mesh_sha256": endpoint["mesh_identity"][
                        "partition_independent_mesh_sha256"
                    ],
                    "normalized_config_sha256": endpoint["normalized_config_identity"][
                        "normalized_config_sha256"
                    ],
                    "ordered_modes_sha256": endpoint["mode_identity"][
                        "ordered_modes_sha256"
                    ],
                    "cell_interior_degree_sha256": endpoint["candidate"][
                        "cell_interior_degree_sha256"
                    ],
                    "incident_projections_sha256": endpoint["vector_identity"][
                        "incident_projections_sha256"
                    ],
                    "auxiliary_coordinate_scales_sha256": endpoint["vector_identity"][
                        "coordinate_scales_sha256"
                    ],
                }
                passing_report["endpoint_identity_authorities"] = {
                    "schema_version": (
                        "task035d.selective-face-endpoint-identities.v1"
                    ),
                    "coarse": raw_endpoint_identity,
                    "enriched": dict(raw_endpoint_identity),
                }
                independent_gate = task035d_selective_face_dwr_report_gate(
                    passing_report,
                    self.significant,
                    endpoint,
                    expected_source_sha=SOURCE_SHA,
                    expected_coarse_plan_sha256=(TASK035D_LOCAL_H_PLAN_FILE_SHA256),
                    expected_enriched_plan_sha256=(
                        TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256
                    ),
                    expected_coarse_manifest_sha256=manifest_sha,
                    expected_significant_channel_authority_sha256=(
                        SIGNIFICANT_REFERENCE_SHA256
                    ),
                )
                self.assertTrue(
                    independent_gate["pass"],
                    independent_gate["failures"],
                )
                candidate_run = root / "candidate"
                candidate_run.mkdir()
                report_path = candidate_run / "selective_face_dwr_report.json"
                report_path.write_text(
                    json.dumps(passing_report, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
                candidate_evidence = {
                    "record": {
                        "task035d_selective_face_evidence": {
                            "phase": "enriched-evaluate",
                            "path": str(report_path),
                            "sha256": report_sha,
                            "payload": passing_report,
                            "independent_checker": independent_gate,
                        }
                    },
                    "run_dir": candidate_run,
                    "launch_contract": {
                        "selective_face_coarse_manifest": {
                            "path": str(manifest_path),
                            "sha256": manifest_sha,
                        }
                    },
                    "source_sha": SOURCE_SHA,
                }
                formal = _load_selective_face_dwr_evidence(
                    candidate_evidence,
                    significant_channel_authority=self.significant,
                )
                self.assertTrue(formal["pass"])
                self.assertFalse(formal["checker_contract_false_negative"])

                stale_candidate = copy.deepcopy(candidate_evidence)
                stale_gate = stale_candidate["record"][
                    "task035d_selective_face_evidence"
                ]["independent_checker"]
                false_checks = {
                    "coarse_snapshot_manifest_and_modal_endpoint",
                    "all_endpoint_identities",
                    "actual_cross_trace_transfer",
                    "twelve_actual_unit_adjoints_recomputed",
                    "all_36_goal_closures_recomputed",
                    "ten_face_multigoal_partition_recomputed",
                }
                stale_gate["status"] = (
                    "selective_face_cross_trace_dwr_checker_fail"
                )
                stale_gate["pass"] = False
                stale_gate["failures"] = sorted(false_checks)
                stale_gate["failed_goal_labels"] = sorted(
                    passing_report["goal_dwr"]["goals"]
                )
                stale_gate["recomputed_goal_pass_count"] = 0
                stale_gate["recomputed_power_goal_pass_count"] = 0
                stale_gate[
                    "recomputed_amplitude_component_goal_pass_count"
                ] = 0
                stale_gate["posthoc_actual_action_attribution"] = False
                for name in false_checks:
                    stale_gate["checks"][name] = False
                with self.assertRaisesRegex(
                    Task035dEvidenceError,
                    "embedded and recomputed selective-face DWR Gates differ",
                ):
                    _load_selective_face_dwr_evidence(
                        stale_candidate,
                        significant_channel_authority=self.significant,
                    )
                with patch(
                    "benchmarks.task035d_case097_checker."
                    "_SELECTIVE_FACE_HASH_SEMANTICS_NUMERICAL_SOURCE_SHA",
                    SOURCE_SHA,
                ):
                    requalified = _load_selective_face_dwr_evidence(
                        stale_candidate,
                        significant_channel_authority=self.significant,
                    )
                self.assertTrue(requalified["pass"])
                self.assertTrue(
                    requalified["checker_contract_false_negative"]
                )
            self.assertEqual(endpoint["manifest_sha256"], manifest_sha)
            self.assertTrue(np.array_equal(endpoint["auxiliary_values_b"], auxiliary))

            np.savez(
                arrays_path,
                auxiliary_values_b=auxiliary,
                incident_projections=incident,
                coordinate_scales=np.zeros(80, dtype=np.complex128),
            )
            with self.assertRaises(ValueError):
                load_selective_face_coarse_endpoint(
                    manifest_path,
                    expected_manifest_sha256=manifest_sha,
                )

            with self.assertRaisesRegex(SystemExit, "process-bound"):
                main(
                    [
                        "--worker",
                        "--run-dir",
                        str(root / "direct-worker"),
                        "--degree",
                        "2",
                        "--h-nm",
                        "5",
                        "--polarization-kind",
                        "s",
                        "--run-kind",
                        "assembly-only",
                        "--mpi-size",
                        "1",
                        "--profile",
                        "default",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
