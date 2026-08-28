"""Focused V6-2 runner, resource-plan, and raw-checker contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
import pytest

import benchmarks.check_task040_v7_scale_normalized_identity as v7_checker
import benchmarks.check_task040_v6_2_interface_schur as checker
import benchmarks.task040_level_a as level_a
import benchmarks.task040_level_a_watchdog as watchdog
import benchmarks.task040_v6_2_interface_schur as runner
from src.solvers.hybrid_bare_f_authority import (
    _source_definition_sha256,
    _source_semantic_descriptor,
)
from src.solvers.hybrid_exact_qualification import (
    ExactQualificationContractError,
    hash_array_bytes_sha256,
    rank_local_shard_binding_sha256,
    write_current_exact_solution_packet,
)
from src.solvers.hybrid_interface_packet_dolfinx import (
    build_gamma_canonical_layout,
    make_gamma_entity_block,
)


FORMAL_SOURCE_SHA = "a" * 40
CHECKER_SOURCE_SHA = "b" * 40
HEX = "c" * 64


def _tiny_gamma_layout(side: str) -> Any:
    block = make_gamma_entity_block(
        name=f"{side}_shared_lifecycle_block",
        entity_dimension=1,
        physical_entity=side,
        raw_row_ids=(0,),
        canonical_to_raw=np.eye(1, dtype=np.complex128),
        orientation_state={"side": side, "orientation": 1},
        floquet_master=0,
        floquet_coefficient=1.0 + 0.0j,
        canonical_key_records=(
            {
                "role": "active_trace",
                "entity_dimension": 1,
                "physical_entity": side,
                "entity_local_basis_index": 0,
                "orientation_state": {"side": side, "orientation": 1},
                "floquet_master": 0,
                "floquet_coefficient": [1.0, 0.0],
            },
        ),
    )
    return build_gamma_canonical_layout(
        (block,),
        (0,),
        plane_identity={"side": side, "z_index": 2 if side == "lower" else 4},
        comm=MPI.COMM_SELF,
    )


def _formal_descriptor(
    root: Path,
    *,
    label: str,
    rank: int = 0,
    mpi_size: int = 1,
    global_size: int = 2,
    owner_range: tuple[int, int] = (0, 2),
) -> dict[str, Any]:
    frozen_source_sha = runner.V6_2_FROZEN_V5_RHS_PRODUCER_SOURCE_SHA
    provenance = {
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "selected_manifest_sha256": HEX,
        "selected_identity_sha256": HEX,
        "resolved_config_sha256": HEX,
        "source_sha": frozen_source_sha,
    }
    source_definition_provenance = {
        "committed_source_sha": frozen_source_sha,
        **{field: HEX for field in provenance if field != "source_sha"},
    }
    source_metadata: dict[str, Any] = {
        "source": "tiny_v6_2_fixture",
        "kind": "canonical_random",
        "source_sha": frozen_source_sha,
        **{field: HEX for field in provenance if field != "source_sha"},
        "seed": 761 + list(runner.V6_2_EXACT_QUALIFICATION_SOURCES).index(label),
        "numeric_formula": "sha256(canonical_physical_key)+seed",
    }
    if label == "external_dtn_coupling":
        source_metadata.update(
            {
                "kind": "minimal_surface_coupling_column",
                "mode_index": 177,
                "mode_key": {
                    "side": "bottom",
                    "m": 0,
                    "n": 0,
                    "polarization": "s",
                },
                "traction_coefficients": [[1.0, 0.0], [0.0, 1.0]],
                "surface_quadrature_degree": 37,
                "sign": -1.0,
                "external_mode_authority": {
                    "count": 296,
                    "index177_key": {"mode": 177},
                },
            }
        )
    elif label.startswith("modal_traction_"):
        source_metadata.update(
            {
                "kind": "current_layout_full3d_one_cell_exact_schur_column",
                "selected_mode_packet_branch": (
                    "positive" if label.endswith("positive") else "negative"
                ),
                "selected_mode_packet_index": 281 if label.endswith("positive") else 283,
                "selected_mode_packet_mode_key": {
                    "direction": "forward"
                    if label.endswith("positive")
                    else "backward",
                    "kind": "lossy_propagating",
                },
                "selected_mode_packet_beta": [0.5, 0.01],
                "selected_mode_packet_manifest_sha256": HEX,
                "selected_mode_packet_identity_sha256": HEX,
                "surface_load_convention": "frozen_full3d_one_cell_exact_schur",
                "sign_convention": "matrix_column_as_stored/no_extra_sign",
                "propagation_model": "full3d_uniform_cg",
                "propagation_axial_fem_degree": 6,
                "propagation_axial_h_nm": 10.0,
            }
        )
    source_definition_descriptor = _source_semantic_descriptor(
        label=label,
        metadata=source_metadata,
        provenance=source_definition_provenance,
    )
    source_definition_sha = _source_definition_sha256(
        label=label,
        metadata=source_metadata,
        provenance=source_definition_provenance,
    )
    source_definition = {
        **source_metadata,
        "bare_f_operator_hash": runner.V6_2_FROZEN_V5_BARE_F_OPERATOR_HASH,
        "canonical_key_set_sha256": HEX,
        "provenance": source_definition_provenance,
        "rhs_repeat": {
            "finite": True,
            "pass": True,
            "relative_difference": 0.0,
        },
        "source_definition_descriptor": source_definition_descriptor,
        "source_definition_sha256": source_definition_sha,
    }
    identity = {
        "array_sha256": HEX,
        "canonical_key_count_local": 2,
        "canonical_key_set_sha256": HEX,
        "dtype": "complex128",
        "global_size": global_size,
        "local_size": owner_range[1] - owner_range[0],
        "owner_row_array_sha256": HEX,
        "owner_row_order": "petsc_current_ownership_range",
        "ownership_range": list(owner_range),
        "raw_global_row_remap": False,
        "global_sha256": HEX,
        "canonical_to_current_roundtrip_relative": 0.0,
    }
    return {
        "schema": "task040.v5.current_bare_f_authority_vector.v1",
        "side": "bottom",
        "label": label,
        "role": "rhs",
        "dtype": "complex128",
        "global_size": global_size,
        "local_size": owner_range[1] - owner_range[0],
        "ownership_range": list(owner_range),
        "metadata_path": f"rank{rank:04d}/bottom_{label}_rhs.json",
        "array_path": f"rank{rank:04d}/bottom_{label}_rhs.npy",
        "array_sha256": HEX,
        "owner_row_array_path": f"rank{rank:04d}/bottom_{label}_rhs_owner_rows.npy",
        "owner_row_array_sha256": HEX,
        "owner_row_order": "petsc_current_ownership_range",
        "canonical_layout_path": f"rank{rank:04d}/canonical_active_layout.json",
        "canonical_layout_sha256": HEX,
        "canonical_key_set_sha256": HEX,
        "canonical_key_count_local": 2,
        "global_sha256": HEX,
        "source_definition_sha256": source_definition_sha,
        "bare_f_operator_hash": runner.V6_2_FROZEN_V5_BARE_F_OPERATOR_HASH,
        "canonical_to_current_roundtrip_relative": 0.0,
        "rank_local_shard_binding_sha256": rank_local_shard_binding_sha256(
            rank=rank,
            label=label,
            role="rhs",
            source_definition_sha256=source_definition_sha,
            key_set_sha256=HEX,
            canonical_layout_sha256=HEX,
            identity=identity,
            source_provenance=provenance,
            bare_f_operator_hash=runner.V6_2_FROZEN_V5_BARE_F_OPERATOR_HASH,
            rhs_repeat=source_definition["rhs_repeat"],
        ),
        "raw_global_row_remap": False,
        "source_provenance": provenance,
        "source_definition": source_definition,
        "vector_identity": identity,
    }


def _formal_binding_fixture(tmp_path: Path) -> tuple[dict[str, Any], PETSc.Mat]:
    frozen_root = tmp_path / "worker" / "bare_f_authority"
    frozen_root.mkdir(parents=True)
    labels = runner.V6_2_EXACT_QUALIFICATION_SOURCES
    descriptors: dict[str, dict[str, Any]] = {}
    for label in labels:
        descriptor = _formal_descriptor(frozen_root, label=label)
        metadata_path = frozen_root / descriptor["metadata_path"]
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(metadata_path, descriptor)
        descriptors[label] = json.loads(json.dumps(descriptor))
    configuration = {
        "descriptors": descriptors,
        "canonical_roundtrip": {label: lambda *_args: 0.0 for label in labels},
    }
    matrix = PETSc.Mat().createAIJ(
        size=((2, 2), (2, 2)), nnz=1, comm=PETSc.COMM_SELF
    )
    matrix.setValue(0, 0, PETSc.ScalarType(1.0))
    matrix.setValue(1, 1, PETSc.ScalarType(1.0))
    matrix.assemble()
    return configuration, matrix


def _formal_identity_preflight() -> dict[str, Any]:
    return {
        "pass": True,
        "observed": {
            "input_sha256": HEX,
            "physical_model_sha256": HEX,
            "selected_manifest_sha256": HEX,
            "selected_identity_sha256": HEX,
            "resolved_config_sha256": HEX,
        },
    }


def _write_json(path: Path, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, indent=2).encode() + b"\n"
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def _v7_raw_metric_fixture() -> dict[str, Any]:
    ids = {str(group): f"group{group}:runtime" for group in range(3)}
    alpha = {
        "real": v7_checker.LINEARITY_ALPHA_REAL,
        "imag": v7_checker.LINEARITY_ALPHA_IMAG,
        "abs": v7_checker.LINEARITY_ALPHA_ABS,
    }
    structure = {
        "layout": {
            "global_size": 7,
            "lower_global_rows": 4,
            "upper_global_rows": 3,
            "owner_local_mapping_count": 7,
            "canonical_position_bijection": True,
            "coverage_exact": True,
            "owner_distributed": True,
        },
        "factor_count_ready": 3,
        "factor_count_ready_observed": 3,
        "numeric_allgather": False,
        "fe_numeric_allgather": False,
        "full_interface_numeric_replica": False,
        "scratch_vectors_allocated_per_apply": 0,
    }

    def ratio_terms(kind: str) -> dict[str, Any]:
        if kind == "identity":
            terms = {"diff": 1.0e-12, "naction": 2.0, "nfull": 2.0}
            ratio = v7_checker.identity_relative(terms)
        elif kind == "backward":
            terms = {"residual": 1.0e-13, "n_aii_x": 1.0, "n_rhs": 1.0}
            ratio = v7_checker.backward_relative(terms)
        else:
            terms = {"diff": 1.0e-13, "n1": 1.0, "n2": 1.0}
            ratio = v7_checker.repeat_relative(terms)
        return {"terms": terms, "relative": ratio}

    def group(group: int) -> dict[str, Any]:
        before = 10 + group
        after = before + 2

        def diag(count: int) -> dict[str, Any]:
            return {
                "solve_count": count,
                "factor_identity": ids[str(group)],
                "readback": True,
            }
        return {
            "group": group,
            "rhs_norm": 1.0,
            "solution1_norm": 1.0,
            "solution2_norm": 1.0,
            "repeat": ratio_terms("repeat"),
            "solve_count_before": before,
            "solve_count_after": after,
            "solve_count_delta": 2,
            "factor_identity_before": ids[str(group)],
            "factor_identity_after": ids[str(group)],
            "factor_diagnostics_before": diag(before),
            "factor_diagnostics_after": diag(after),
            "backward": ratio_terms("backward"),
            "finite": True,
        }

    def identity(source: int, exponent: int) -> dict[str, Any]:
        def variant(diff: float) -> dict[str, Any]:
            terms = {"diff": diff, "naction": 2.0, "nfull": 2.0}
            repeat = {"diff": 1.0e-13, "n1": 2.0, "n2": 2.0}
            return {
                "output_norm": 2.0,
                "finite": True,
                "identity": {
                    "terms": terms,
                    "relative": v7_checker.identity_relative(terms),
                },
                "repeat": {
                    "terms": repeat,
                    "relative": v7_checker.repeat_relative(repeat),
                },
            }

        eta = {"diff": 1.0e-13, "nd0": 2.0, "nd1": 2.0}
        return {
            "source_index": source,
            "scale_exponent": exponent,
            "scale": float(2.0**exponent),
            "source_norm": float(2.0**exponent),
            "layer_a": {"groups": [group(value) for value in range(3)]},
            "layer_c": {
                "full": {
                    "output_norm": 2.0,
                    "interior_residual_norm": 1.0e-13,
                    "finite": True,
                },
                "d0": variant(1.0e-12),
                "d1": variant(2.0e-12),
                "d0_d1": {
                    "terms": eta,
                    "eta": v7_checker.relative_from_terms(
                        eta["diff"], eta["nd0"], eta["nd1"]
                    ),
                },
                "contribution_output_norms": {
                    name: {"output_norm": 0.5, "finite": True}
                    for name in v7_checker.CONTRIBUTION_NAMES
                },
                "roundtrip_error": 1.0e-13,
            },
        }

    def linearity(exponent: int) -> dict[str, Any]:
        def linearity_entry() -> dict[str, Any]:
            terms = {
                "diff": 1.0e-13,
                "ncombined": 2.0,
                "nleft": 1.0,
                "alpha_abs": v7_checker.LINEARITY_ALPHA_ABS,
                "nright": 1.0,
            }
            return {"terms": terms, "relative": v7_checker.linearity_relative(terms)}

        groups = {
            name: (
                1 if name.startswith("middle")
                else 0 if name.startswith("lower") else 2
            )
            for name in v7_checker.CONTRIBUTION_NAMES
        }
        layer_b = {
            name: {
                "group": group_value,
                "output_norms": {"left": 1.0, "right": 1.0, "combined": 2.0},
                "repeat": ratio_terms("repeat"),
                "linearity": linearity_entry(),
                "finite": True,
            }
            for name, group_value in groups.items()
        }
        layer_c = {
            name: {
                "output_norms": {"left": 1.0, "right": 1.0, "combined": 2.0},
                **linearity_entry(),
                "finite": True,
            }
            for name in ("d0", "d1")
        }
        return {
            "scale_exponent": exponent,
            "scale": float(2.0**exponent),
            "left_source_index": 10,
            "right_source_index": 11,
            "alpha": alpha,
            "input_norms": {"left": 1.0, "right": 1.0, "combined": 2.0},
            "layer_b": layer_b,
            "layer_c": layer_c,
        }

    legacy = {
        "scale_exponent": 0,
        "scale": 1.0,
        "deterministic": [
            {
                "vector_index": index,
                "gamma_action_error": (
                    1.0e-9
                    if index == v7_checker.IDENTITY_SOURCE_INDICES[0]
                    else 1.0e-12
                ),
                "full_interior_residual_error": 1.0e-13,
                "roundtrip_error": 1.0e-13,
                "repeat_error": 1.0e-13,
            }
            for index in v7_checker.IDENTITY_SOURCE_INDICES
        ],
        "zero_error": 0.0,
        "linearity_error": 1.0e-13,
        "thresholds": dict(v7_checker.LEGACY_THRESHOLDS),
        "gate": {
            **dict.fromkeys(v7_checker.LEGACY_THRESHOLDS, True),
            "full_elimination_gamma": False,
            "three_deterministic_vectors": True,
        },
        "gate_pass": False,
        "relative_metrics_not_used": True,
    }
    return {
        "schema": v7_checker.SCHEMA,
        "status": "diagnostics_only",
        "classification": "not_formal_adjudication",
        "formal_adjudication": False,
        "next_required_stage": "independent_raw_checker_then_formal_integration",
        "safe_denominator": v7_checker.SAFE_DENOMINATOR,
        "identity_source_indices": list(v7_checker.IDENTITY_SOURCE_INDICES),
        "linearity_source_indices": list(v7_checker.LINEARITY_SOURCE_INDICES),
        "scales": [
            {"exponent": exponent, "scale": float(2.0**exponent)}
            for exponent in v7_checker.SCALE_EXPONENTS
        ],
        "linearity_alpha": alpha,
        "d1_contribution_order": list(v7_checker.CONTRIBUTION_NAMES),
        "structure": {"before": structure, "after": structure},
        "factor_setup": {
            "same_action": True,
            "same_factor_setup": True,
            "factor_identity_by_group": ids,
            "factor_readback_by_group": {
                group: {"factor_identity": identity, "readback": True}
                for group, identity in ids.items()
            },
        },
        "identity_records": [
            identity(source, exponent)
            for exponent in v7_checker.SCALE_EXPONENTS
            for source in v7_checker.IDENTITY_SOURCE_INDICES
        ],
        "linearity_records": [
            linearity(exponent) for exponent in v7_checker.SCALE_EXPONENTS
        ],
        "legacy_v6_2_absolute_diagnostic": legacy,
        "runner_claims": {
            "gate_pass": False,
            "classification": "forged_runner_claim",
        },
    }


def _qualification_plan() -> dict[str, Any]:
    return runner.build_v6_2_exact_qualification_plan()


def _legacy_qualification_plan() -> dict[str, Any]:
    plan = _qualification_plan()
    plan.update(
        {
            "status": "designed_not_run",
            "execution_mode": "identity_only",
            "identity_only": True,
            "frozen_owner_row_arrays": (
                "not_loaded; complex PETSc owner-order values, never row ids"
            ),
        }
    )
    return plan


def test_v6_2_evidence_status_reports_executed_exact_and_continuation() -> None:
    exact_summary = runner._compact_exact_stage_summary(
        {
            "status": "completed_exact_numerical_gate_negative_continuation_allowed",
            "classification": "V6_EXACT_QUALIFICATION_GATE_FAIL",
        }
    )
    continuation_summary = runner._compact_exact_stage_summary(
        {
            "status": "completed_v6_3_identity_probe",
            "classification": "V6_3_IDENTITY_FAIL",
        }
    )

    assert exact_summary["executed"] is True
    assert continuation_summary["executed"] is True
    assert (
        runner._exact_pde_status(exact_summary)
        == "exact_interface_fgmres_with_full_bare_f_residual_run"
    )
    assert runner._combined_v6_2_status(
        identity_gate_pass=False,
        exact_consensus=True,
        exact_executed=True,
        continuation_consensus=True,
        continuation_executed=True,
    ) == "completed_v6_2_identity_exact_qualification_and_v6_3_continuation"


def test_v6_2_formal_binding_separates_frozen_rhs_and_current_source(
    tmp_path: Path,
) -> None:
    configuration, matrix = _formal_binding_fixture(tmp_path)
    frozen_root = tmp_path / "worker" / "bare_f_authority"
    run_root = tmp_path / "fresh-run"
    raw_descriptors = deepcopy(configuration["descriptors"])
    raw_metadata_hashes = {
        label: hashlib.sha256(
            (frozen_root / raw_descriptors[label]["metadata_path"]).read_bytes()
        ).hexdigest()
        for label in runner.V6_2_EXACT_QUALIFICATION_SOURCES
    }
    try:
        bound = runner._bind_v6_2_formal_exact_configuration(
            configuration,
            exact_spool_root=frozen_root,
            run_directory=run_root,
            identity_preflight=_formal_identity_preflight(),
            bare_operator=matrix,
            bare_operator_hash=HEX,
            source_sha=FORMAL_SOURCE_SHA,
        )
        assert (
            bound["source_provenance"]["source_sha"]
            == runner.V6_2_FROZEN_V5_RHS_PRODUCER_SOURCE_SHA
        )
        assert bound["source_provenance"]["source_sha"] != FORMAL_SOURCE_SHA
        assert (
            bound["validation"]["expected_source_sha256"]
            == runner.V6_2_FROZEN_V5_RHS_PRODUCER_SOURCE_SHA
        )
        assert bound["validation"]["expected_operator_hash"] == HEX
        assert bound["packet_root"] == str((run_root / "exact_packets").resolve())
        assert bound["base_directory"] == str(frozen_root.resolve())
        bridge = {
            "schema": "task040.v6_2.operator_identity_bridge.v1",
            "status": "frozen_rhs_rebound_to_live_bare_f",
            "frozen_bare_f_operator_hash": (
                runner.V6_2_FROZEN_V5_BARE_F_OPERATOR_HASH
            ),
            "qualification_live_bare_f_operator_hash": HEX,
            "raw_descriptor_metadata_unchanged": True,
            "numeric_rhs_arrays_unchanged": True,
            "runtime_binding_recomputed": True,
            "shared_input_model_authority": True,
        }
        assert bound["operator_identity_bridge"] == bridge
        assert configuration["descriptors"] == raw_descriptors
        for label in runner.V6_2_EXACT_QUALIFICATION_SOURCES:
            raw = raw_descriptors[label]
            runtime = bound["descriptors"][label]
            expected_runtime = deepcopy(raw)
            expected_runtime["bare_f_operator_hash"] = HEX
            expected_runtime["source_definition"]["bare_f_operator_hash"] = HEX
            expected_runtime["rank_local_shard_binding_sha256"] = (
                rank_local_shard_binding_sha256(
                    rank=0,
                    label=label,
                    role=runtime["role"],
                    source_definition_sha256=runtime["source_definition_sha256"],
                    key_set_sha256=runtime["canonical_key_set_sha256"],
                    canonical_layout_sha256=runtime["canonical_layout_sha256"],
                    identity=runtime["vector_identity"],
                    source_provenance=runtime["source_provenance"],
                    bare_f_operator_hash=HEX,
                    rhs_repeat=runtime["source_definition"]["rhs_repeat"],
                )
            )
            assert runtime == expected_runtime
            assert runtime["rank_local_shard_binding_sha256"] != raw[
                "rank_local_shard_binding_sha256"
            ]
            assert (
                bound["frozen_rhs_descriptor_metadata_sha256"][label]
                == raw_metadata_hashes[label]
            )
        compact = runner._compact_exact_stage_summary(
            {
                "operator_identity_bridge": bridge,
                "authority_identity_chain": {
                    "operator_identity_bridge": bridge,
                },
            }
        )
        assert compact["operator_identity_bridge"] == bridge
        assert compact["authority_identity_chain"]["operator_identity_bridge"] == bridge
    finally:
        matrix.destroy()


@pytest.mark.parametrize("mutation", ("root", "packet", "source", "descriptor", "operator", "callbacks"))
def test_v6_2_formal_binding_rejects_untrusted_authority_mutations(
    tmp_path: Path,
    mutation: str,
) -> None:
    configuration, matrix = _formal_binding_fixture(tmp_path)
    frozen_root = tmp_path / "worker" / "bare_f_authority"
    run_root = tmp_path / "fresh-run"
    mutated = deepcopy(configuration)
    if mutation == "root":
        mutated["frozen_root"] = str(tmp_path / "other-root")
    elif mutation == "packet":
        mutated["packet_root"] = str(tmp_path / "caller-packet-root")
    elif mutation == "source":
        mutated["source_provenance"] = {
            "source_sha": FORMAL_SOURCE_SHA,
            "input_sha256": HEX,
            "physical_model_sha256": HEX,
            "selected_manifest_sha256": HEX,
            "selected_identity_sha256": HEX,
            "resolved_config_sha256": HEX,
        }
    elif mutation == "descriptor":
        mutated["descriptors"]["external_dtn_coupling"]["source_provenance"][
            "source_sha"
        ] = FORMAL_SOURCE_SHA
    elif mutation == "operator":
        mutated["descriptors"]["external_dtn_coupling"][
            "bare_f_operator_hash"
        ] = "d" * 64
    else:
        mutated["canonical_roundtrip"].pop("fixed_random_repeat_0")
    try:
        with pytest.raises((TypeError, ValueError, runner.PETSc.Error)):
            runner._bind_v6_2_formal_exact_configuration(
                mutated,
                exact_spool_root=frozen_root,
                run_directory=run_root,
                identity_preflight=_formal_identity_preflight(),
                bare_operator=matrix,
                bare_operator_hash=HEX,
                source_sha=FORMAL_SOURCE_SHA,
            )
    finally:
        matrix.destroy()


def test_v6_2_formal_binding_rejects_shuffled_five_source_order(
    tmp_path: Path,
) -> None:
    configuration, matrix = _formal_binding_fixture(tmp_path)
    frozen_root = tmp_path / "worker" / "bare_f_authority"
    try:
        configuration["descriptors"] = dict(
            reversed(tuple(configuration["descriptors"].items()))
        )
        with pytest.raises(ValueError, match="sources in order"):
            runner._bind_v6_2_formal_exact_configuration(
                configuration,
                exact_spool_root=frozen_root,
                run_directory=tmp_path / "fresh-run",
                identity_preflight=_formal_identity_preflight(),
                bare_operator=matrix,
                bare_operator_hash=HEX,
                source_sha=FORMAL_SOURCE_SHA,
            )
    finally:
        matrix.destroy()


def test_v6_2_exact_runner_wires_tolerance_and_negative_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise discarded partial packets at the exact orchestration boundary."""

    configuration, matrix = _formal_binding_fixture(tmp_path)
    frozen_root = tmp_path / "worker" / "bare_f_authority"
    packet_root = tmp_path / "fresh-run" / "exact_packets"
    labels = runner.V6_2_EXACT_QUALIFICATION_SOURCES
    descriptors = configuration["descriptors"]
    frozen_provenance = descriptors[labels[0]]["source_provenance"]
    qualification_provenance = {
        **frozen_provenance,
        "source_sha": FORMAL_SOURCE_SHA,
    }
    descriptor_hashes = {
        label: hashlib.sha256(
            (frozen_root / descriptors[label]["metadata_path"]).read_bytes()
        ).hexdigest()
        for label in labels
    }
    lower = _tiny_gamma_layout("lower")
    upper = _tiny_gamma_layout("upper")
    captured_factory: dict[str, Any] = {}
    captured_family: dict[str, Any] = {}

    def fake_packet_consumer(**kwargs: Any) -> object:
        captured_factory.update(kwargs)
        return object()

    def fake_family(
        observed_descriptors: Mapping[str, Mapping[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        assert observed_descriptors is descriptors
        assert tuple(observed_descriptors) == labels
        captured_family.update(kwargs)
        first_label, second_label = labels[:2]
        packet_root.mkdir(parents=True, exist_ok=True)
        (packet_root / "partial.json").write_text("{}")
        return {
            "status": (
                "completed_exact_numerical_gate_negative_continuation_allowed"
            ),
            "classification": "V6_EXACT_QUALIFICATION_GATE_FAIL",
            "source_records": [
                {
                    "label": first_label,
                    "full_residual_gate_pass": True,
                    "packetization_gate_pass": True,
                    "fgmres": {
                        "packetization_gate_error": None,
                        "checkpoint_history": [],
                        "accepted_solution_packet_audit": {
                            "packet_write": {"partial": "dummy"},
                        },
                    },
                },
                {
                    "label": second_label,
                    "full_residual_gate_pass": False,
                    "packetization_gate_pass": False,
                    "fgmres": {
                        "packetization_gate_error": None,
                        "checkpoint_history": [],
                    },
                },
            ],
            "initial_pair_gate_pass": False,
            "all_sources_gate_pass": False,
        }

    monkeypatch.setattr(
        runner,
        "make_current_exact_solution_packet_consumer",
        fake_packet_consumer,
    )
    monkeypatch.setattr(runner, "run_exact_qualification_family", fake_family)
    tolerance = 4.0e-7
    try:
        result = runner.run_v6_2_exact_qualification_packets(
            descriptors=descriptors,
            base_directory=frozen_root,
            interface_operator=matrix,
            bare_operator=matrix,
            schur_action=object(),
            system=SimpleNamespace(name="live-system"),
            canonical_layout=SimpleNamespace(name="joint-layout"),
            lower_gamma_layout=lower,
            upper_gamma_layout=upper,
            canonical_roundtrip={label: lambda *_args: 0.0 for label in labels},
            canonical_packets_for_vector=lambda *_args: (),
            gamma_canonical_values_for_vector=lambda *_args: np.zeros(
                1, dtype=np.complex128
            ),
            exact_output_canonical_roundtrip=lambda *_args: 0.0,
            packet_root=packet_root,
            frozen_root=frozen_root,
            source_provenance=frozen_provenance,
            qualification_source_provenance=qualification_provenance,
            frozen_rhs_descriptor_metadata_sha256=descriptor_hashes,
            comm=MPI.COMM_SELF,
            max_iterations=1,
            full_residual_tolerance=tolerance,
        )
        assert captured_factory["full_residual_tolerance"] == tolerance
        assert captured_family["full_residual_tolerance"] == tolerance
        assert captured_family["accepted_solution_consumer"] is not None
        assert result["family"]["all_sources_gate_pass"] is False
        assert result["packet_aggregate"] == {}
        assert result["packet_aggregate_gate_pass"] is False
        assert result["packet_root"] == str(packet_root)
        assert not packet_root.exists()
        assert result["initial_pair_publication"] == {
            "initial_pair_gate_pass": False,
            "status": "failed_then_discarded",
            "packet_root_exists_after_gate": False,
        }
        assert result["frozen_rhs_source_provenance"] == frozen_provenance
        assert result["qualification_source_provenance"] == qualification_provenance
        json.dumps(result, sort_keys=True)
    finally:
        lower = None
        upper = None
        matrix.destroy()


class _SharedLifecycleAction:
    def __init__(self) -> None:
        self.diagnostics = {
            "factor_lifecycle": {
                "ready": 3,
                "destroyed": False,
                "after_cleanup": None,
                "simultaneous_max": 3,
            }
        }

    def destroy(self) -> None:
        lifecycle = self.diagnostics["factor_lifecycle"]
        lifecycle["destroyed"] = True
        lifecycle["after_cleanup"] = 0


def _shared_lifecycle_fixture() -> tuple[_SharedLifecycleAction, PETSc.Mat, Any, Any, Any]:
    action = _SharedLifecycleAction()
    matrix = PETSc.Mat().createAIJ(
        size=((1, 1), (1, 1)), nnz=1, comm=PETSc.COMM_SELF
    )
    matrix.setValue(0, 0, PETSc.ScalarType(1.0))
    matrix.assemble()
    lower = _tiny_gamma_layout("lower")
    upper = _tiny_gamma_layout("upper")
    joint = SimpleNamespace(
        lower_global_count=1,
        upper_global_count=1,
        audit={
            "canonical_order": "Gamma_L_then_Gamma_U_by_physical_key",
            "canonical_key_order_sha256": HEX,
            "coverage_exact": True,
            "canonical_position_bijection": True,
            "owner_local_mapping": True,
        },
    )
    return action, matrix, lower, upper, joint


def test_v6_2_shared_lifecycle_keeps_objects_and_allows_numeric_negative_continuation() -> None:
    action, matrix, lower, upper, joint = _shared_lifecycle_fixture()
    exact_seen: dict[str, Any] = {}
    continuation_seen: dict[str, Any] = {}
    wrong = object()
    qualification_source_provenance = {
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "selected_manifest_sha256": HEX,
        "selected_identity_sha256": HEX,
        "resolved_config_sha256": HEX,
        "source_sha": "d" * 40,
    }
    frozen_rhs_descriptor_metadata_sha256 = {
        label: HEX for label in runner.V6_2_EXACT_QUALIFICATION_SOURCES
    }

    def exact_runner(
        *,
        qualification_source_provenance: Mapping[str, Any],
        frozen_rhs_descriptor_metadata_sha256: Mapping[str, str],
        **kwargs: Any,
    ) -> dict[str, Any]:
        for key, expected in (
            ("system", system),
            ("schur_action", action),
            ("interface_operator", matrix),
            ("bare_operator", matrix),
            ("lower_gamma_layout", lower),
            ("upper_gamma_layout", upper),
            ("canonical_layout", joint),
        ):
            assert kwargs[key] is expected
        exact_seen.update(
            {
                **kwargs,
                "qualification_source_provenance": qualification_source_provenance,
                "frozen_rhs_descriptor_metadata_sha256": (
                    frozen_rhs_descriptor_metadata_sha256
                ),
            }
        )
        return {
            "status": "completed_exact_numerical_gate_negative_continuation_allowed",
            "classification": "V6_EXACT_QUALIFICATION_GATE_FAIL",
        }

    def continuation(payload: Mapping[str, Any]) -> dict[str, Any]:
        for key, expected in (
            ("system", system),
            ("schur_action", action),
            ("interface_operator", matrix),
            ("bare_operator", matrix),
            ("lower_gamma_layout", lower),
            ("upper_gamma_layout", upper),
            ("canonical_layout", joint),
        ):
            assert payload[key] is expected
        continuation_seen.update(payload)
        return {"status": "completed_v6_3_identity_probe"}

    system = SimpleNamespace(name="live-system")
    try:
        result = runner._run_v6_2_shared_current_lifecycle(
            action=action,
            system=system,
            interface_operator=matrix,
            bare_operator=matrix,
            exact_configuration={
                "system": wrong,
                "schur_action": wrong,
                "lower_gamma_layout": wrong,
                "upper_gamma_layout": wrong,
                "canonical_layout": wrong,
                "qualification_source_provenance": qualification_source_provenance,
                "frozen_rhs_descriptor_metadata_sha256": (
                    frozen_rhs_descriptor_metadata_sha256
                ),
                "user_option": "preserved",
            },
            exact_runner=exact_runner,
            expected_factor_count=3,
            gamma_layouts={"lower": lower, "upper": upper},
            canonical_layout=joint,
            continuation=continuation,
        )
        assert exact_seen["user_option"] == "preserved"
        assert exact_seen["qualification_source_provenance"] is (
            qualification_source_provenance
        )
        assert exact_seen["frozen_rhs_descriptor_metadata_sha256"] is (
            frozen_rhs_descriptor_metadata_sha256
        )
        assert result["same_live_action"] is True
        assert result["same_layout_objects_injected"] is True
        assert result["factor_lifecycle_after_exact"]["ready"] == 3
        assert result["factor_lifecycle_after_continuation"]["ready"] == 3
        assert continuation_seen["exact_qualification"]["classification"] == (
            "V6_EXACT_QUALIFICATION_GATE_FAIL"
        )
        action.destroy()
        assert action.diagnostics["factor_lifecycle"]["after_cleanup"] == 0
        assert action.diagnostics["factor_lifecycle"]["destroyed"] is True
    finally:
        matrix.destroy()


def test_v6_2_shared_lifecycle_packet_contract_blocks_continuation() -> None:
    action, matrix, lower, upper, joint = _shared_lifecycle_fixture()
    continuation_called = False

    def exact_runner(**_kwargs: Any) -> dict[str, Any]:
        raise ExactQualificationContractError("packet writer contract")

    def continuation(_payload: Mapping[str, Any]) -> dict[str, Any]:
        nonlocal continuation_called
        continuation_called = True
        return {}

    try:
        with pytest.raises(ExactQualificationContractError, match="packet writer"):
            runner._run_v6_2_shared_current_lifecycle(
                action=action,
                system=SimpleNamespace(name="live-system"),
                interface_operator=matrix,
                bare_operator=matrix,
                exact_configuration={},
                exact_runner=exact_runner,
                expected_factor_count=3,
                gamma_layouts={"lower": lower, "upper": upper},
                canonical_layout=joint,
                continuation=continuation,
            )
        assert continuation_called is False
        assert action.diagnostics["factor_lifecycle"]["destroyed"] is False
    finally:
        matrix.destroy()


def _identity_gate() -> dict[str, bool]:
    return {
        "zero_map": True,
        "repeat": True,
        "linearity": True,
        "restriction_prolongation": True,
        "full_elimination_gamma": True,
        "full_elimination_interior": True,
        "three_deterministic_vectors": True,
        "group_solve_count": True,
        "joint_size": True,
        "numeric_allgather": True,
        "full_interface_replica": True,
        "layout_coverage_exact": True,
        "layout_counts_7560_plus_7560": True,
        "layout_canonical_l_then_u": True,
        "layout_owner_distributed": True,
        "layout_position_bijection": True,
        "factor_ready_three_observed": True,
        "factor_simultaneous_max_three_observed": True,
        "factor_after_cleanup_zero_observed": True,
        "factor_action_destroyed": True,
    }


def _deterministic_vectors() -> list[dict[str, Any]]:
    return [
        {
            "vector_index": index,
            "gamma_action_error": 0.0,
            "full_interior_residual_error": 0.0,
            "solve_count": 3,
            "roundtrip_error": 0.0,
            "repeat_error": 0.0,
        }
        for index in range(3)
    ]


def _rank_artifact(rank: int, identity: dict[str, bool]) -> dict[str, Any]:
    layout = {
        "global_size": checker.EXPECTED_JOINT_COUNT,
        "owner_local_mapping_count": 1890,
        "owner_distributed": True,
        "coverage_exact": True,
        "canonical_position_bijection": True,
    }
    return {
        "schema": checker.EXPECTED_RANK_SCHEMA,
        "rank": rank,
        "mpi_size": checker.EXPECTED_MPI_SIZE,
        "source_sha": FORMAL_SOURCE_SHA,
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "bare_f_operator_hash": HEX,
        "identity_preflight": {"pass": True, "checks": {"source": True}},
        "resource_preflight_pass": True,
        "system_inventory": {},
        "matrix_objects": {"C": 0, "D": 0, "H": 0},
        "qep_calls": 0,
        "canonical_interface_layout": layout,
        "canonical_mapping_sha256": HEX,
        "canonical_mapping_count": 1890,
        "group_rows": {},
        "support_audits": {},
        "support_metadata_replicated": True,
        "deterministic_vectors": _deterministic_vectors(),
        "zero_error": 0.0,
        "linearity_error": 0.0,
        "identity_gate": identity,
        "gate_pass": all(identity.values()),
        "classification": (
            "V6_2_FULL_INTERFACE_SCHUR_PASS"
            if all(identity.values())
            else "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
        ),
        "factor_lifecycle_before": {
            "ready": 3,
            "after_cleanup": None,
            "simultaneous_max": 3,
        },
        "factor_lifecycle_after": {
            "ready": 3,
            "after_cleanup": 0,
            "simultaneous_max": 3,
        },
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "numeric_allgather": False,
        "fe_numeric_allgather": False,
        "full_interface_numeric_replica": False,
        "raw_global_row_remap": False,
        "exact_output_vectors_loaded": 0,
        "pde_solve": "not_run",
        "exact_qualification_plan": _legacy_qualification_plan(),
    }


def _make_checker_fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "formal"
    root.mkdir()
    operator_audit = {
        "schema": "task040.v5.operator_semantics_audit.v1",
        "source_sha": FORMAL_SOURCE_SHA,
        "pass": True,
        "checks": {"operator_identity": True},
        "current_authority": {
            "static_path_identity": True,
            "operator": "explicit_current_bare_F",
            "factor": "ResearchExactFactorInverse(F)",
            "C_D_H_constructed": {"C": 0, "D": 0, "H": 0},
            "qep_calls": 0,
            "top_system_constructed": False,
            "full_coupling_constructed": False,
            "woodbury_inverse": False,
            "physical_dtn_operator": False,
        },
        "modal_source_identity": {
            "pass": True,
            "repair": {
                "qep_calls": 0,
                "top_system_constructed": False,
                "full_coupling_constructed": False,
                "scalar_cg_substitution": False,
            },
        },
    }
    operator_audit["record_sha256"] = hashlib.sha256(
        json.dumps(
            operator_audit,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    audit_sha = _write_json(
        root / "operator_semantics_audit.json",
        operator_audit,
    )
    identity = _identity_gate()
    descriptors = []
    artifacts = []
    for rank in range(checker.EXPECTED_MPI_SIZE):
        artifact = _rank_artifact(rank, identity)
        path = root / f"rank{rank:04d}.json"
        artifact_sha = _write_json(path, artifact)
        descriptors.append(
            {
                "rank": rank,
                "path": path.name,
                "sha256": artifact_sha,
                "canonical_mapping_count": artifact["canonical_mapping_count"],
                "canonical_mapping_sha256": HEX,
                "factor_lifecycle_after": artifact["factor_lifecycle_after"],
            }
        )
        artifacts.append(artifact)
    after = [artifact["factor_lifecycle_after"] for artifact in artifacts]
    manifest = {
        "schema": checker.EXPECTED_FORMAL_SCHEMA,
        "method": "task040_v6_2_full_interface_schur",
        "profile": "task040.v6_2.h4.full_interface.v1",
        "mpi_size": checker.EXPECTED_MPI_SIZE,
        "status": "completed_v6_2_identity",
        "classification": "V6_2_FULL_INTERFACE_SCHUR_PASS",
        "source_sha": FORMAL_SOURCE_SHA,
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "identity_preflight": {"pass": True, "checks": {"source": True}},
        "resource_preflight": {"pass": True, "checks": {"resource": True}},
        "operator_semantics_audit": {
            "path": "operator_semantics_audit.json",
            "sha256": audit_sha,
            "content_sha256": operator_audit["record_sha256"],
        },
        "system_created": True,
        "system_inventory": {},
        "matrix_objects": {"C": 0, "D": 0, "H": 0},
        "qep_calls": 0,
        "bare_f_operator_hash": HEX,
        "factored_operator": "none",
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "exact_output_vectors_loaded": 0,
        "pde_solve": "not_run",
        "canonical_interface_layout": {
            "global_size": checker.EXPECTED_JOINT_COUNT,
            "lower_global_rows": checker.EXPECTED_LOWER_COUNT,
            "upper_global_rows": checker.EXPECTED_UPPER_COUNT,
            "canonical_order": "Gamma_L_then_Gamma_U_by_physical_key",
            "canonical_position_bijection": True,
            "coverage_exact": True,
            "owner_distributed": True,
            "root_metadata_gather": True,
            "per_rank_full_interface_replica": False,
            "numeric_allgather": False,
            "value_basis": "current_raw_active_coefficients",
            "canonical_block_transforms_applied": False,
        },
        "gamma_counts": {
            "Gamma_L": checker.EXPECTED_LOWER_COUNT,
            "Gamma_U": checker.EXPECTED_UPPER_COUNT,
            "joint": checker.EXPECTED_JOINT_COUNT,
        },
        "group_rows": {},
        "support_audits": {},
        "support_metadata_replicated": True,
        "deterministic_vectors": _deterministic_vectors(),
        "zero_error": 0.0,
        "linearity_error": 0.0,
        "identity_gate": identity,
        "gate_pass": all(identity.values()),
        "factor_lifecycle": {
            "before": {"ready": 3, "after_cleanup": None, "simultaneous_max": 3},
            "after_by_rank": after,
            "construction_count": 3,
            "destruction_count": 3,
            "simultaneous_max": 3,
            "rank_consensus": True,
        },
        "numeric_allgather": False,
        "fe_numeric_allgather": False,
        "full_interface_numeric_replica": False,
        "root_metadata_gather": True,
        "per_rank_full_interface_replica": False,
        "raw_global_row_remap": False,
        "rank_artifacts": descriptors,
        "downstream": {},
        "exact_qualification_plan": _legacy_qualification_plan(),
        "research_only": True,
    }
    manifest_path = root / "v6_2_manifest.json"
    run_summary_path = root / "run_summary.json"
    run_summary_sha = _write_json(
        run_summary_path,
        {"schema": "task040.level_a.run_summary.v1", "status": "complete"},
    )
    _write_json(
        root.parent / "watchdog_summary.json",
        {
            "schema": "task040.level_a.watchdog.v1",
            "method": manifest["method"],
            "source_sha": manifest["source_sha"],
            "termination_reason": "natural_exit",
            "return_code": 0,
            "elapsed_seconds": 1.0,
            "authoritative_sample_count": 1,
            "peak_rss_bytes": 1024,
            "peak_swap_bytes": 0,
            "peak_dedicated_cgroup_swap_bytes": 0,
            "hard_stop_bytes": 45 * 2**30,
            "timeout_seconds": 21600.0,
            "all_status_readable": True,
            "swap_authority_readable": True,
            "run_summary_present": True,
            "run_summary_sha256": run_summary_sha,
        },
    )
    _write_json(manifest_path, manifest)
    return root, manifest_path


def _make_packet_aggregate_checker_fixture(
    tmp_path: Path,
) -> tuple[
    Path,
    dict[str, Any],
    dict[int, dict[str, dict[str, Any]]],
    dict[str, str],
    dict[str, str],
]:
    """Build a small-file, eight-rank packet aggregate for raw checker tests."""

    root = tmp_path / "packet-formal"
    packet_root = root / "packets"
    root.mkdir()
    frozen_provenance = {
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "selected_manifest_sha256": HEX,
        "selected_identity_sha256": HEX,
        "resolved_config_sha256": HEX,
        "source_sha": checker.EXPECTED_FROZEN_RHS_SOURCE_SHA,
    }
    qualification_provenance = {
        **frozen_provenance,
        "source_sha": FORMAL_SOURCE_SHA,
    }
    expected_by_rank: dict[int, dict[str, dict[str, Any]]] = {}
    rank_manifests: list[dict[str, Any]] = []
    for rank in range(checker.EXPECTED_MPI_SIZE):
        canonical_values = np.asarray([rank + 1.0 + 0.5j], dtype=np.complex128)
        owner_values = np.asarray([10.0 + rank + 0.25j], dtype=np.complex128)
        gamma_lower_values = np.arange(
            945, dtype=np.float64
        ).astype(np.complex128) + (rank + 1.0j)
        gamma_upper_values = np.arange(
            945, dtype=np.float64
        ).astype(np.complex128) + (2 * rank + 1.0j)
        arrays = {
            "exact_output_canonical": canonical_values,
            "exact_output_owner_rows": owner_values,
            "gamma_l_canonical": gamma_lower_values,
            "gamma_u_canonical": gamma_upper_values,
        }

        def identity(role: str, values: np.ndarray) -> dict[str, Any]:
            if role == "exact_output_canonical":
                return {
                    "label": "aggregate_checker",
                    "role": role,
                    "dtype": "complex128",
                    "rank": rank,
                    "mpi_size": checker.EXPECTED_MPI_SIZE,
                    "value_sha256": hash_array_bytes_sha256(values),
                    "source_definition_sha256": HEX,
                    "bare_f_operator_hash": HEX,
                    "canonical_layout_sha256": "d" * 64,
                    "canonical_key_set_sha256": HEX,
                    "source_provenance": deepcopy(frozen_provenance),
                    "canonical_key_count_local": 1,
                    "global_active_size": checker.EXPECTED_MPI_SIZE,
                    "canonical_key_order_sha256": f"{rank + 1:064x}",
                    "canonical_key_set_local_sha256": f"{rank + 11:064x}",
                    "canonical_roundtrip_relative": 0.0,
                }
            if role == "exact_output_owner_rows":
                return {
                    "label": "aggregate_checker",
                    "role": role,
                    "dtype": "complex128",
                    "rank": rank,
                    "mpi_size": checker.EXPECTED_MPI_SIZE,
                    "value_sha256": hash_array_bytes_sha256(values),
                    "source_definition_sha256": HEX,
                    "bare_f_operator_hash": HEX,
                    "canonical_layout_sha256": "d" * 64,
                    "canonical_key_set_sha256": HEX,
                    "source_provenance": deepcopy(frozen_provenance),
                    "local_size": 1,
                    "global_size": checker.EXPECTED_MPI_SIZE,
                    "ownership_range": [rank, rank + 1],
                    "owner_row_order": "petsc_current_ownership_range",
                }
            side = "e" if role == "gamma_l_canonical" else "f"
            return {
                "label": "aggregate_checker",
                "role": role,
                "dtype": "complex128",
                "rank": rank,
                "mpi_size": checker.EXPECTED_MPI_SIZE,
                "value_sha256": hash_array_bytes_sha256(values),
                "source_definition_sha256": HEX,
                "bare_f_operator_hash": HEX,
                "canonical_layout_sha256": side * 64,
                "canonical_key_set_sha256": HEX,
                "source_provenance": deepcopy(frozen_provenance),
                "canonical_key_count_local": 945,
                "canonical_global_size": 7560,
                "canonical_key_order_sha256": f"{rank + 21:064x}",
                "canonical_key_set_local_sha256": f"{rank + 31:064x}",
                "gamma_transform_sha256": f"{rank + 41:064x}",
            }

        identities = {
            role: identity(role, values) for role, values in arrays.items()
        }
        packets = write_current_exact_solution_packet(
            root=packet_root,
            rank=rank,
            label="aggregate_checker",
            packet_values=arrays,
            packet_identities=identities,
        )
        expected_by_rank[rank] = packets
        rank_manifests.append({"rank": rank, "roles": packets})

    descriptor_hashes_by_rank = [
        {
            source_label: f"{rank + 1:064x}"
            for source_label in checker._EXACT_SOURCE_ORDER
        }
        for rank in range(checker.EXPECTED_MPI_SIZE)
    ]
    descriptor_binding = hashlib.sha256(
        json.dumps(
            descriptor_hashes_by_rank,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    payload = {
        "schema": "task040.v6.current_exact_packet_rank_manifest.v1",
        "label": "aggregate_checker",
        "mpi_size": checker.EXPECTED_MPI_SIZE,
        "rank_count": checker.EXPECTED_MPI_SIZE,
        "role_count": 4,
        "role_count_per_rank": 4,
        "source_provenance": frozen_provenance,
        "bare_f_operator_hash": HEX,
        "qualification_source_provenance": qualification_provenance,
        "frozen_rhs_descriptor_metadata_sha256_by_rank": descriptor_hashes_by_rank,
        "frozen_rhs_descriptor_metadata_binding_sha256": descriptor_binding,
        "rank_manifests": rank_manifests,
        "numeric_allgather": False,
        "full_numeric_replica": False,
    }
    aggregate_path = root / "aggregate.json"
    aggregate_sha = _write_json(aggregate_path, payload)
    descriptor = {
        "schema": "task040.v6.current_exact_packet_rank_manifest.v1",
        "path": aggregate_path.name,
        "sha256": aggregate_sha,
        "label": "aggregate_checker",
        "mpi_size": checker.EXPECTED_MPI_SIZE,
        "rank_count": checker.EXPECTED_MPI_SIZE,
        "role_count": 4,
        "role_count_per_rank": 4,
        "source_provenance": frozen_provenance,
        "qualification_source_provenance": qualification_provenance,
        "bare_f_operator_hash": HEX,
        "numeric_allgather": False,
        "full_numeric_replica": False,
        "frozen_rhs_descriptor_metadata_sha256_by_rank": descriptor_hashes_by_rank,
        "frozen_rhs_descriptor_metadata_binding_sha256": descriptor_binding,
    }
    return (
        root,
        descriptor,
        expected_by_rank,
        frozen_provenance,
        qualification_provenance,
    )


def _rewrite_packet_for_checker_tamper(
    packet: Mapping[str, Any],
    *,
    updates: Mapping[str, Any],
    values: np.ndarray | None = None,
) -> dict[str, Any]:
    """Rewrite a role's artifact chain and return its self-consistent record."""

    updated = dict(packet)
    updated.update(updates)
    array_path = Path(str(packet["array_path"]))
    if values is not None:
        np.save(array_path, np.asarray(values, dtype=np.complex128), allow_pickle=False)
        updated["value_sha256"] = hash_array_bytes_sha256(values)
        updated["array_sha256"] = updated["value_sha256"]
        updated["shard_sha256"] = hashlib.sha256(array_path.read_bytes()).hexdigest()
    metadata_path = Path(str(packet["path"]))
    manifest_path = Path(str(packet["manifest_path"]))
    metadata = json.loads(metadata_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    metadata.update(updates)
    manifest.update(updates)
    if values is not None:
        metadata.update(
            {
                "value_sha256": updated["value_sha256"],
                "array_sha256": updated["array_sha256"],
                "shard_sha256": updated["shard_sha256"],
            }
        )
        manifest.update(
            {
                "value_sha256": updated["value_sha256"],
                "array_sha256": updated["array_sha256"],
                "shard_sha256": updated["shard_sha256"],
            }
        )
    updated["metadata_sha256"] = _write_json(metadata_path, metadata)
    manifest["metadata_sha256"] = updated["metadata_sha256"]
    updated["manifest_sha256"] = _write_json(manifest_path, manifest)
    return updated


def _rewrite_checker_aggregate(
    root: Path,
    descriptor: Mapping[str, Any],
    *,
    rank: int,
    role: str,
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    aggregate_path = root / str(descriptor["path"])
    payload = json.loads(aggregate_path.read_text())
    payload["rank_manifests"][rank]["roles"][role] = packet
    aggregate_sha = _write_json(aggregate_path, payload)
    result = dict(descriptor)
    result["sha256"] = aggregate_sha
    return result


def _executed_provenance(source_sha: str) -> dict[str, str]:
    return {
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "selected_manifest_sha256": HEX,
        "selected_identity_sha256": HEX,
        "resolved_config_sha256": HEX,
        "source_sha": source_sha,
    }


def _executed_checkpoint(
    label: str,
    iteration: int,
    relative: float,
    *,
    accepted: bool,
    gamma_rows_local_count: int = 0,
    active_local_size: int = 1,
) -> dict[str, Any]:
    if not 0 <= gamma_rows_local_count <= active_local_size:
        raise ValueError("synthetic recovery counts must partition the active rows")
    return {
        "label": label,
        "iteration": iteration,
        "restart": 32,
        "checkpoint_kind": "mandatory",
        "interface_true_residual_norm": relative,
        "interface_true_residual_relative": relative,
        "full_true_residual_norm": relative,
        "full_true_residual_relative": relative,
        "rhs_norm_denominator": 1.0,
        "interface_rhs_norm_denominator": 1.0,
        "full_residual_tolerance": 1.0e-9,
        "finite": True,
        "accepted_full_solution": accepted,
        "recovery": {
            "gamma_rows_local": {
                "count": gamma_rows_local_count,
                "dtype": "int64",
                "sha256": "1" * 64,
            },
            "interior_rows_local": {
                "count": active_local_size - gamma_rows_local_count,
                "dtype": "int64",
                "sha256": "2" * 64,
            },
            "group_interior_solve_count": 3,
            "interior_rhs_norms": [1.0, 2.0, 3.0],
            "interior_rhs_nonzero": True,
        },
    }


def _executed_128_observation(relative: float) -> dict[str, Any]:
    direct_gate = bool(relative <= 0.8)
    resource = {
        "pass": True,
        "hard_limit_bytes": 45 * 2**30,
        "rss_bytes": 1024,
        "swap_bytes": 0.0,
        "all_status_readable": True,
        "wall_observation": {
            "elapsed_seconds": 1.0,
            "budget_seconds": 21600.0,
        },
    }
    return {
        "target_checkpoint": 256,
        "residual_gate": direct_gate,
        "authorized": direct_gate,
        "authorization_consensus": True,
        "authorized_by_rank": [direct_gate] * checker.EXPECTED_MPI_SIZE,
        "resource_snapshot": resource,
        "resource_observation": {
            "current_sample_only": True,
            "current_rss_bytes": 1024,
            "current_swap_bytes": 0.0,
            "all_status_readable": True,
            "pass": True,
        },
        "resource_gate": True,
        "wall_observation": {
            "elapsed_seconds": 1.0,
            "budget_seconds": 21600.0,
        },
        "wall_gate": None,
        "residual_observation": {
            "checkpoint": 128,
            "observed_checkpoint_sequence": [16, 32, 64, 128],
            "required_checkpoint_iterations": [16, 32, 64, 128, 256],
            "r64": relative,
            "r128": relative,
            "r256": None,
            "drop_64_to_128_decade": 0.0,
            "r128_threshold_gate": direct_gate,
            "drop_64_to_128_gate": False,
            "monotone_history": False,
        },
    }


def _executed_fgmres(
    label: str,
    *,
    packet_ready: bool,
    packet_audit: Mapping[str, Any] | None = None,
    gamma_rows_local_count: int = 0,
    active_local_size: int = 1,
) -> dict[str, Any]:
    relative = 5.0e-10 if packet_ready else 0.9
    rows = [
        _executed_checkpoint(
            label,
            iteration,
            relative,
            accepted=packet_ready,
            gamma_rows_local_count=gamma_rows_local_count,
            active_local_size=active_local_size,
        )
        for iteration in (16, 32, 64, 128)
    ]
    result: dict[str, Any] = {
        "schema": "task040.v6.exact_interface_fgmres.v1",
        "label": label,
        "restart": 32,
        "mandatory_checkpoints": [16, 32, 64, 128],
        "conditional_checkpoints": [256, 512],
        "checkpoints": {str(row["iteration"]): row for row in rows},
        "final_iteration": 128,
        "final_record": rows[-1],
        "early_final_record": None,
        "checkpoint_history": rows,
        "stopped_at_happy_breakdown": False,
        "conditional_authorized": {
            "256": packet_ready,
            "512": False,
        },
        "conditional_completed": {"256": False, "512": False},
        "conditional_gate_observations": {
            "128": _executed_128_observation(relative),
        },
        "full_residual_tolerance": 1.0e-9,
        "accepted_solution_present": packet_ready,
        "accepted_solution_consumed": packet_ready,
        "accepted_solution_released_by_driver": packet_ready,
        "accepted_solution_iteration": 128 if packet_ready else None,
        "numeric_allgather": False,
        "full_numeric_replica": False,
        "identity_preconditioner": True,
        "active_rhs_unchanged": True,
        "condensed_rhs_unchanged": True,
        "full_rhs_norm": 1.0,
        "interface_rhs_norm": 1.0,
        "active_rhs_initial_sha256": HEX,
        "active_rhs_final_sha256": HEX,
        "condensed_rhs_initial_sha256": HEX,
        "condensed_rhs_final_sha256": HEX,
    }
    if packet_ready:
        result["accepted_solution_packet_audit"] = packet_audit
    return result


def _executed_packet_identities(
    *,
    rank: int,
    label: str,
    arrays: Mapping[str, np.ndarray],
    frozen_provenance: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    source_definition = f"{0x500 + list(checker._EXACT_SOURCE_ORDER).index(label):064x}"
    common = {
        "label": label,
        "dtype": "complex128",
        "rank": rank,
        "mpi_size": checker.EXPECTED_MPI_SIZE,
        "source_definition_sha256": source_definition,
        "bare_f_operator_hash": HEX,
        "canonical_key_set_sha256": "c" * 64,
        "source_provenance": deepcopy(dict(frozen_provenance)),
    }
    identities: dict[str, dict[str, Any]] = {}
    identities["exact_output_canonical"] = {
        **common,
        "role": "exact_output_canonical",
        "value_sha256": hash_array_bytes_sha256(arrays["exact_output_canonical"]),
        "canonical_layout_sha256": "d" * 64,
        "canonical_key_count_local": 1,
        "global_active_size": checker.EXPECTED_MPI_SIZE,
        "canonical_key_order_sha256": f"{1000 + rank:064x}",
        "canonical_key_set_local_sha256": f"{2000 + rank:064x}",
        "canonical_roundtrip_relative": 0.0,
    }
    identities["exact_output_owner_rows"] = {
        **common,
        "role": "exact_output_owner_rows",
        "value_sha256": hash_array_bytes_sha256(arrays["exact_output_owner_rows"]),
        "canonical_layout_sha256": "d" * 64,
        "local_size": 1,
        "global_size": checker.EXPECTED_MPI_SIZE,
        "ownership_range": [rank, rank + 1],
        "owner_row_order": "petsc_current_ownership_range",
    }
    for role, layout_digest, transform_digest in (
        ("gamma_l_canonical", "e" * 64, "1" * 64),
        ("gamma_u_canonical", "f" * 64, "2" * 64),
    ):
        identities[role] = {
            **common,
            "role": role,
            "value_sha256": hash_array_bytes_sha256(arrays[role]),
            "canonical_layout_sha256": layout_digest,
            "canonical_key_count_local": 945,
            "canonical_global_size": 7560,
            "canonical_key_order_sha256": f"{3000 + rank:064x}",
            "canonical_key_set_local_sha256": f"{4000 + rank:064x}",
            "gamma_transform_sha256": transform_digest,
        }
    return identities


def _executed_adapter_audit(
    *,
    rank: int,
    label: str,
    frozen_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the compact post-release adapter proof used by executed fixtures."""

    source_definition = f"{0x500 + list(checker._EXACT_SOURCE_ORDER).index(label):064x}"
    canonical_layout = "d" * 64
    canonical_key_set = "c" * 64
    active_global_size = checker.EXPECTED_JOINT_COUNT
    active_local_size = active_global_size // checker.EXPECTED_MPI_SIZE
    rank_records: list[dict[str, Any]] = []
    for rank_index in range(checker.EXPECTED_MPI_SIZE):
        array_sha = f"{0x9000 + rank_index:064x}"
        owner_sha = f"{0xA000 + rank_index:064x}"
        rank_records.append(
            {
                "rank": rank_index,
                "mpi_size": checker.EXPECTED_MPI_SIZE,
                "label": label,
                "role": "rhs",
                "global_size": active_global_size,
                "local_size": active_local_size,
                "ownership_range": [
                    rank_index * active_local_size,
                    (rank_index + 1) * active_local_size,
                ],
                "array_sha256": array_sha,
                "owner_row_array_sha256": owner_sha,
                "canonical_layout_sha256": canonical_layout,
                "canonical_key_set_sha256": canonical_key_set,
                "global_sha256": None,
                "canonical_layout_rank": rank_index,
                "canonical_layout_mpi_size": checker.EXPECTED_MPI_SIZE,
                "source_definition_sha256": source_definition,
                "rank_local_shard_binding_sha256": f"{0xB000 + rank_index:064x}",
                "bare_f_operator_hash": HEX,
                "source_sha": frozen_provenance["source_sha"],
                "source_provenance": deepcopy(dict(frozen_provenance)),
            }
        )
    global_sha = hashlib.sha256(
        "\n".join(record["array_sha256"] for record in rank_records).encode("ascii")
    ).hexdigest()
    for record in rank_records:
        record["global_sha256"] = global_sha
    local_array_sha = f"{0x9000 + rank:064x}"
    local_owner_sha = f"{0xA000 + rank:064x}"
    load = {
        "label": label,
        "role": "rhs",
        "schema": "task040.v5.current_bare_f_authority_vector.v1",
        "side": "bottom",
        "dtype": "complex128",
        "owner_row_values_not_row_ids": True,
        "raw_global_row_remap": False,
        "source_sha": frozen_provenance["source_sha"],
        "source_provenance": deepcopy(dict(frozen_provenance)),
        "source_definition_sha256": source_definition,
        "bare_f_operator_hash": HEX,
        "array_sha256": local_array_sha,
        "array_sha256_observed": local_array_sha,
        "owner_row_array_sha256": local_owner_sha,
        "owner_row_array_sha256_observed": local_owner_sha,
        "canonical_layout_sha256": canonical_layout,
        "canonical_layout_sha256_observed": canonical_layout,
        "canonical_key_set_sha256": canonical_key_set,
        "canonical_key_order_sha256": f"{0xC000 + rank:064x}",
        "canonical_key_set_local_sha256": f"{0xD000 + rank:064x}",
        "canonical_key_count_local": 1,
        "global_sha256": global_sha,
        "rank_local_shard_binding_sha256": f"{0xB000 + rank:064x}",
        "local_size": active_local_size,
        "global_size": active_global_size,
        "ownership_range": [
            rank * active_local_size,
            (rank + 1) * active_local_size,
        ],
        "canonical_layout_rank": rank,
        "canonical_layout_mpi_size": checker.EXPECTED_MPI_SIZE,
        "canonical_roundtrip_relative": 0.0,
        "canonical_to_current_roundtrip_relative": 0.0,
        "rhs_repeat": {"pass": True, "relative_difference": 0.0},
        "canonical_values_loaded": True,
        "owner_values_loaded": True,
        "numeric_values_loaded": True,
        "owner_row_array_loaded": True,
        "canonical_values_retained": False,
        "owner_values_retained": False,
        "distributed": {
            "label": label,
            "role": "rhs",
            "global_size": active_global_size,
            "rank_records": rank_records,
            "owner_local": True,
            "numeric_allgather": False,
            "full_numeric_replica": False,
            "ownership_coverage_exact": True,
            "global_sha256": global_sha,
        },
    }
    return {
        "load": load,
        "condensed_rhs_built": True,
        "interior_rhs_group_count": 3,
        "numeric_allgather": False,
        "full_numeric_replica": False,
        "retained_during_callbacks": True,
        "released_by_driver": True,
        "destroyed_after_source": True,
    }


def _make_executed_checker_fixture(
    tmp_path: Path,
    *,
    packet_ready: bool,
) -> tuple[Path, Path]:
    """Create an executed eight-rank checker root through the real file chain."""

    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    executed_plan = _qualification_plan()
    executed_plan.update(
        {
            "status": "configured_same_process_exact",
            "execution_mode": "same_process_exact",
            "identity_only": False,
            "frozen_owner_row_arrays": (
                "loaded per source only after fixed metadata/shard/canonical/live-roundtrip validation; "
                "never interpreted as row ids"
            ),
        }
    )
    manifest["exact_qualification_plan"] = executed_plan
    frozen_provenance = _executed_provenance(checker.EXPECTED_FROZEN_RHS_SOURCE_SHA)
    qualification_provenance = _executed_provenance(FORMAL_SOURCE_SHA)
    descriptor_hashes_by_rank = [
        {
            label: f"{0x700 + rank * 10 + index:064x}"
            for index, label in enumerate(checker._EXACT_SOURCE_ORDER)
        }
        for rank in range(checker.EXPECTED_MPI_SIZE)
    ]
    aggregate_refs: dict[str, dict[str, Any]] = {}
    expected_packets_by_rank: dict[int, dict[str, dict[str, Any]]] = {}
    packet_root = root / "packets"
    aggregate_root = root / "aggregates"
    labels = (
        checker._EXACT_SOURCE_ORDER
        if packet_ready
        else checker._EXACT_SOURCE_ORDER[:2]
    )
    packet_labels = checker._EXACT_SOURCE_ORDER if packet_ready else ()
    if packet_ready:
        aggregate_root.mkdir(parents=True, exist_ok=True)
    for label in packet_labels:
        rank_manifests: list[dict[str, Any]] = []
        for rank in range(checker.EXPECTED_MPI_SIZE):
            gamma_l = np.arange(945, dtype=np.float64).astype(np.complex128)
            gamma_l += rank + 1j
            gamma_u = np.arange(945, dtype=np.float64).astype(np.complex128)
            gamma_u += 2 * rank + 1j
            arrays = {
                "exact_output_canonical": np.asarray(
                    [rank + 1.0 + 0.1j], dtype=np.complex128
                ),
                "exact_output_owner_rows": np.asarray(
                    [rank + 1.0 + 0.2j], dtype=np.complex128
                ),
                "gamma_l_canonical": gamma_l,
                "gamma_u_canonical": gamma_u,
            }
            identities = _executed_packet_identities(
                rank=rank,
                label=label,
                arrays=arrays,
                frozen_provenance=frozen_provenance,
            )
            packets = write_current_exact_solution_packet(
                root=packet_root,
                rank=rank,
                label=label,
                packet_values=arrays,
                packet_identities=identities,
                source_provenance=frozen_provenance,
            )
            expected_packets_by_rank.setdefault(rank, {})[label] = {
                **identities,
            }
            expected_packets_by_rank[rank][label]["packet_write"] = packets
            rank_manifests.append({"rank": rank, "roles": packets})
        payload = {
            "schema": "task040.v6.current_exact_packet_rank_manifest.v1",
            "label": label,
            "mpi_size": checker.EXPECTED_MPI_SIZE,
            "rank_count": checker.EXPECTED_MPI_SIZE,
            "role_count": 4,
            "role_count_per_rank": 4,
            "source_provenance": frozen_provenance,
            "bare_f_operator_hash": HEX,
            "qualification_source_provenance": qualification_provenance,
            "frozen_rhs_descriptor_metadata_sha256_by_rank": descriptor_hashes_by_rank,
            "frozen_rhs_descriptor_metadata_binding_sha256": hashlib.sha256(
                json.dumps(
                    descriptor_hashes_by_rank,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "rank_manifests": rank_manifests,
            "numeric_allgather": False,
            "full_numeric_replica": False,
        }
        aggregate_path = aggregate_root / f"{label}.json"
        aggregate_sha = _write_json(aggregate_path, payload)
        aggregate_refs[label] = {
            "schema": payload["schema"],
            "path": str(aggregate_path.relative_to(root)),
            "sha256": aggregate_sha,
            "label": label,
            "mpi_size": checker.EXPECTED_MPI_SIZE,
            "rank_count": checker.EXPECTED_MPI_SIZE,
            "role_count": 4,
            "role_count_per_rank": 4,
            "source_provenance": frozen_provenance,
            "bare_f_operator_hash": HEX,
            "qualification_source_provenance": qualification_provenance,
            "frozen_rhs_descriptor_metadata_sha256_by_rank": descriptor_hashes_by_rank,
            "frozen_rhs_descriptor_metadata_binding_sha256": payload[
                "frozen_rhs_descriptor_metadata_binding_sha256"
            ],
            "numeric_allgather": False,
            "full_numeric_replica": False,
        }

    exact_references: list[dict[str, Any]] = []
    compact_by_rank: dict[int, dict[str, Any]] = {}
    for rank in range(checker.EXPECTED_MPI_SIZE):
        records: list[dict[str, Any]] = []
        for label in labels:
            packet_audit = None
            if packet_ready:
                packet_audit = {
                    "packet_write": expected_packets_by_rank[rank][label][
                        "packet_write"
                    ],
                    "expected_packet_identities": {
                        role: expected_packets_by_rank[rank][label][role]
                        for role in (
                            "exact_output_canonical",
                            "exact_output_owner_rows",
                            "gamma_l_canonical",
                            "gamma_u_canonical",
                        )
                    },
                }
            fgmres = _executed_fgmres(
                label,
                packet_ready=packet_ready,
                packet_audit=packet_audit,
                gamma_rows_local_count=1890,
                active_local_size=1890,
            )
            records.append(
                {
                    "label": label,
                    "best_full_true_residual_relative": (
                        5.0e-10 if packet_ready else 0.9
                    ),
                    "full_residual_gate_pass": packet_ready,
                    "packetization_gate_pass": packet_ready,
                    "adapter": _executed_adapter_audit(
                        rank=rank,
                        label=label,
                        frozen_provenance=frozen_provenance,
                    ),
                    "fgmres": fgmres,
                }
            )
        family = {
            "schema": "task040.v6.exact_qualification_family.v1",
            "ordered_labels": list(checker._EXACT_SOURCE_ORDER),
            "initial_labels": list(checker._EXACT_SOURCE_ORDER[:2]),
            "source_records": records,
            "skipped_labels": (
                [] if packet_ready else list(checker._EXACT_SOURCE_ORDER[2:])
            ),
            "initial_pair_gate_pass": packet_ready,
            "all_sources_gate_pass": packet_ready,
            "full_residual_tolerance": 1.0e-9,
            "packetization_required": True,
            "status": (
                "completed_initial_pair_and_remaining_sources"
                if packet_ready
                else "completed_exact_numerical_gate_negative_continuation_allowed"
            ),
            "classification": (
                "V6_EXACT_QUALIFICATION_READY"
                if packet_ready
                else "V6_EXACT_QUALIFICATION_GATE_FAIL"
            ),
            "normal_numerical_negative": not packet_ready,
            "numeric_allgather": False,
            "full_numeric_replica": False,
        }
        exact_result = {
            "schema": "task040.v6_2.exact_qualification_packets.v1",
            "status": (
                "completed_all_sources_and_packet_aggregate"
                if packet_ready
                else "completed_exact_numerical_gate_negative_continuation_allowed"
            ),
            "classification": (
                "V6_EXACT_QUALIFICATION_READY_WITH_PACKETS"
                if packet_ready
                else "V6_EXACT_QUALIFICATION_GATE_FAIL"
            ),
            "source_order": list(checker._EXACT_SOURCE_ORDER),
            "family": family,
            "packet_root": str(packet_root),
            "initial_pair_publication": {
                "initial_pair_gate_pass": packet_ready,
                "status": (
                    "passed_then_published"
                    if packet_ready
                    else "failed_then_discarded"
                ),
                "packet_root_exists_after_gate": packet_root.exists(),
            },
            "packet_aggregate": aggregate_refs if packet_ready else {},
            "packet_aggregate_gate_pass": packet_ready,
            "frozen_rhs_source_provenance": frozen_provenance,
            "qualification_source_provenance": qualification_provenance,
            "frozen_rhs_descriptor_metadata_sha256": descriptor_hashes_by_rank[rank],
            "authority_identity_chain": {
                "frozen_rhs_source_provenance": frozen_provenance,
                "qualification_source_provenance": qualification_provenance,
                "frozen_rhs_descriptor_metadata_sha256": descriptor_hashes_by_rank[rank],
            },
            "numeric_allgather": False,
            "full_numeric_replica": False,
        }
        exact_output_vectors_loaded = checker._exact_output_vectors_loaded_count(
            exact_result
        )
        compact, _identities = checker._exact_detail_semantic_signature(exact_result)
        compact = checker._recomputed_exact_compact_summary(exact_result, compact)
        compact_by_rank[rank] = compact
        detail_path = root / f"rank{rank:04d}" / "v6_2_exact_qualification.json"
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_payload = {
            "schema": "task040.v6_2.exact_qualification_rank_artifact.v1",
            "rank": rank,
            "mpi_size": checker.EXPECTED_MPI_SIZE,
            "qualification_source_sha": FORMAL_SOURCE_SHA,
            "frozen_rhs_source_sha": checker.EXPECTED_FROZEN_RHS_SOURCE_SHA,
            "bare_f_operator_hash": HEX,
            "frozen_rhs_source_provenance": frozen_provenance,
            "qualification_source_provenance": qualification_provenance,
            "formal_sequence_start_scope": (
                "run_v6_2_interface_schur_entry_before_preflight_and_artifact_setup"
            ),
            "frozen_rhs_descriptor_metadata_sha256": descriptor_hashes_by_rank[rank],
            "exact_result": exact_result,
        }
        detail_sha = _write_json(detail_path, detail_payload)
        reference = {
            "path": str(detail_path.relative_to(root)),
            "sha256": detail_sha,
            "rank": rank,
            "mpi_size": checker.EXPECTED_MPI_SIZE,
            "qualification_source_sha": FORMAL_SOURCE_SHA,
            "frozen_rhs_source_sha": checker.EXPECTED_FROZEN_RHS_SOURCE_SHA,
            "formal_sequence_start_scope": detail_payload[
                "formal_sequence_start_scope"
            ],
            "frozen_rhs_descriptor_metadata_sha256": descriptor_hashes_by_rank[rank],
        }
        exact_references.append(reference)
        rank_path = root / f"rank{rank:04d}.json"
        rank_artifact = json.loads(rank_path.read_text())
        rank_artifact.update(
            {
                "exact_qualification_artifact": reference,
                "exact_qualification": compact,
                "formal_sequence_start_scope": detail_payload[
                    "formal_sequence_start_scope"
                ],
                "pde_solve": "exact_interface_fgmres_with_full_bare_f_residual_run",
                "exact_output_vectors_loaded": exact_output_vectors_loaded,
            }
        )
        _write_json(rank_path, rank_artifact)
        manifest["rank_artifacts"][rank]["sha256"] = hashlib.sha256(
            rank_path.read_bytes()
        ).hexdigest()
        manifest["rank_artifacts"][rank]["exact_qualification"] = compact
        manifest["rank_artifacts"][rank]["formal_sequence_start_scope"] = detail_payload[
            "formal_sequence_start_scope"
        ]
        manifest["rank_artifacts"][rank]["exact_qualification_artifact"] = reference
        manifest["rank_artifacts"][rank][
            "exact_output_vectors_loaded"
        ] = exact_output_vectors_loaded
        manifest["rank_artifacts"][rank]["pde_solve"] = rank_artifact["pde_solve"]

    manifest["status"] = "completed_v6_2_exact_qualification"
    manifest["source_sha"] = FORMAL_SOURCE_SHA
    manifest["exact_output_vectors_loaded"] = manifest["rank_artifacts"][0][
        "exact_output_vectors_loaded"
    ]
    manifest["pde_solve"] = "exact_interface_fgmres_with_full_bare_f_residual_run"
    manifest["formal_sequence_start_scope"] = (
        "run_v6_2_interface_schur_entry_before_preflight_and_artifact_setup"
    )
    manifest["exact_qualification_artifacts"] = exact_references
    manifest["exact_qualification_artifact_chain_sha256"] = hashlib.sha256(
        json.dumps(exact_references, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    manifest["exact_qualification"] = {
        "executed": True,
        "rank_consensus": True,
        "summary": compact_by_rank[0],
        "by_rank": None,
    }
    manifest["downstream"] = {
        "status": "not_run_by_v6_3_not_connected",
        "executed": False,
    }
    _write_json(manifest_path, manifest)
    return root, manifest_path


def _rewrite_executed_detail_reference(
    root: Path,
    manifest_path: Path,
    *,
    rank: int,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """Mutate one detail and refresh its outer rank/root hash chain."""

    manifest = json.loads(manifest_path.read_text())
    reference = deepcopy(manifest["exact_qualification_artifacts"][rank])
    detail_path = root / str(reference["path"])
    detail = json.loads(detail_path.read_text())
    mutate(detail)
    reference["sha256"] = _write_json(detail_path, detail)
    manifest["exact_qualification_artifacts"][rank] = reference

    rank_descriptor = manifest["rank_artifacts"][rank]
    rank_path = root / str(rank_descriptor["path"])
    rank_artifact = json.loads(rank_path.read_text())
    rank_artifact["exact_qualification_artifact"] = reference
    rank_descriptor["exact_qualification_artifact"] = reference
    rank_descriptor["sha256"] = _write_json(rank_path, rank_artifact)
    manifest["rank_artifacts"][rank] = rank_descriptor
    manifest["exact_qualification_artifact_chain_sha256"] = hashlib.sha256(
        json.dumps(
            manifest["exact_qualification_artifacts"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write_json(manifest_path, manifest)


def _rehash_packet_value_and_outer_chain(
    root: Path,
    manifest_path: Path,
    *,
    label: str,
    role: str,
) -> None:
    """Change one NPY and refresh packet/aggregate/detail wrappers only.

    The live expected identity retained in each exact detail is deliberately
    left unchanged.  A checker must therefore reject this fully rehashed
    writer-side mutation instead of trusting the outer descriptor chain.
    """

    manifest = json.loads(manifest_path.read_text())
    root_summary = manifest["exact_qualification"]["summary"]
    aggregate_reference = deepcopy(root_summary["packet_aggregate_refs"][label])
    aggregate_path = root / str(aggregate_reference["path"])
    aggregate = json.loads(aggregate_path.read_text())
    packet = deepcopy(aggregate["rank_manifests"][0]["roles"][role])
    array_path = Path(str(packet["array_path"]))
    values = np.load(array_path, allow_pickle=False)
    values = np.asarray(values).copy()
    values[0] += np.complex128(0.375 + 0.125j)
    np.save(array_path, values, allow_pickle=False)
    value_sha = hash_array_bytes_sha256(values)
    packet.update(
        {
            "value_sha256": value_sha,
            "array_sha256": value_sha,
            "shard_sha256": hashlib.sha256(array_path.read_bytes()).hexdigest(),
        }
    )
    metadata_path = Path(str(packet["path"]))
    metadata = json.loads(metadata_path.read_text())
    metadata.update(
        {
            "value_sha256": value_sha,
            "array_sha256": value_sha,
            "shard_sha256": packet["shard_sha256"],
        }
    )
    packet["metadata_sha256"] = _write_json(metadata_path, metadata)
    packet_manifest_path = Path(str(packet["manifest_path"]))
    packet_manifest = json.loads(packet_manifest_path.read_text())
    packet_manifest.update(
        {
            "value_sha256": value_sha,
            "array_sha256": value_sha,
            "shard_sha256": packet["shard_sha256"],
            "metadata_sha256": packet["metadata_sha256"],
        }
    )
    packet["manifest_sha256"] = _write_json(packet_manifest_path, packet_manifest)
    aggregate["rank_manifests"][0]["roles"][role] = packet
    aggregate_sha = _write_json(aggregate_path, aggregate)
    aggregate_reference["sha256"] = aggregate_sha

    for rank in range(checker.EXPECTED_MPI_SIZE):
        detail_reference = manifest["exact_qualification_artifacts"][rank]
        detail_path = root / str(detail_reference["path"])
        detail = json.loads(detail_path.read_text())
        exact_result = detail["exact_result"]
        exact_result["packet_aggregate"][label]["sha256"] = aggregate_sha
        compact, _identities = checker._exact_detail_semantic_signature(exact_result)
        compact = checker._recomputed_exact_compact_summary(exact_result, compact)
        detail_reference = deepcopy(detail_reference)
        detail_reference["sha256"] = _write_json(detail_path, detail)
        manifest["exact_qualification_artifacts"][rank] = detail_reference

        rank_descriptor = manifest["rank_artifacts"][rank]
        rank_path = root / str(rank_descriptor["path"])
        rank_artifact = json.loads(rank_path.read_text())
        rank_artifact["exact_qualification_artifact"] = detail_reference
        rank_artifact["exact_qualification"] = compact
        rank_descriptor["exact_qualification_artifact"] = detail_reference
        rank_descriptor["exact_qualification"] = compact
        rank_descriptor["sha256"] = _write_json(rank_path, rank_artifact)
        manifest["rank_artifacts"][rank] = rank_descriptor

    manifest["exact_qualification"]["summary"] = compact
    manifest["exact_qualification_artifact_chain_sha256"] = hashlib.sha256(
        json.dumps(
            manifest["exact_qualification_artifacts"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write_json(manifest_path, manifest)


def _run_checker_cli(root: Path, output: Path) -> tuple[int, dict[str, Any]]:
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    return exit_code, json.loads(output.read_text())


def test_v6_2_runner_exact_artifact_reference_binds_formal_scope(
    tmp_path: Path,
) -> None:
    exact_result = {
        "frozen_rhs_source_provenance": _executed_provenance(
            checker.EXPECTED_FROZEN_RHS_SOURCE_SHA
        ),
        "frozen_rhs_descriptor_metadata_sha256": {
            label: f"{index + 1:064x}"
            for index, label in enumerate(checker._EXACT_SOURCE_ORDER)
        },
    }
    exact_path = tmp_path / "rank0000" / "v6_2_exact_qualification.json"
    reference = runner._build_exact_qualification_artifact_reference(
        rank=0,
        mpi_size=checker.EXPECTED_MPI_SIZE,
        exact_rank_path=exact_path,
        output_root=tmp_path,
        source_sha=FORMAL_SOURCE_SHA,
        exact_result=exact_result,
        formal_sequence_start_scope=runner.V6_2_FORMAL_SEQUENCE_START_SCOPE,
    )
    assert reference["path"] == "rank0000/v6_2_exact_qualification.json"
    assert (
        reference["formal_sequence_start_scope"]
        == "run_v6_2_interface_schur_entry_before_preflight_and_artifact_setup"
    )
    assert reference["qualification_source_sha"] == FORMAL_SOURCE_SHA


@pytest.mark.parametrize("packet_ready", [False, True])
def test_v6_2_checker_cli_reopens_executed_exact_chain(
    tmp_path: Path,
    packet_ready: bool,
) -> None:
    root, _manifest_path = _make_executed_checker_fixture(
        tmp_path,
        packet_ready=packet_ready,
    )
    output = tmp_path / ("packet-ready.json" if packet_ready else "negative.json")
    exit_code, observed = _run_checker_cli(root, output)
    assert exit_code == 0
    assert observed["evidence_valid"] is True
    assert observed["checker_pass"] is True
    assert observed["executed_exact"] is True
    assert observed["npy_read"] is packet_ready
    assert observed["evidence_checks"]["npy_read_contract"] is True
    if packet_ready:
        assert observed["gate_pass"] is True
        assert observed["classification"] == "V6_2_FULL_INTERFACE_SCHUR_PASS"
        assert observed["gate_checks"]["exact_packet_aggregate_gate"] is True
        assert any(item.get("kind") == "npy" for item in observed["read_files"])
    else:
        assert observed["gate_pass"] is False
        assert (
            observed["classification"]
            == "V6_2_FULL_INTERFACE_SCHUR_NUMERICAL_NEGATIVE"
        )
        assert observed["gate_checks"]["exact_detail_numerical_gate"] is False
        assert all(item.get("kind") != "npy" for item in observed["read_files"])


@pytest.mark.parametrize(
    "tamper",
    [
        "live_roundtrip",
        "producer_roundtrip",
        "producer_roundtrip_missing",
        "loaded_flag",
        "retained_flag",
        "global_hash",
        "owner_coverage",
        "recovery",
        "recovery_paired_counts",
    ],
)
def test_v6_2_checker_rejects_rehashed_adapter_audit_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    root, manifest_path = _make_executed_checker_fixture(
        tmp_path,
        packet_ready=False,
    )

    def mutate(detail: dict[str, Any]) -> None:
        record = detail["exact_result"]["family"]["source_records"][0]
        adapter = record["adapter"]
        load = adapter["load"]
        if tamper == "live_roundtrip":
            load["canonical_roundtrip_relative"] = 1.0e-6
        elif tamper == "producer_roundtrip":
            load["canonical_to_current_roundtrip_relative"] = 1.0e-6
        elif tamper == "producer_roundtrip_missing":
            load.pop("canonical_to_current_roundtrip_relative")
        elif tamper == "loaded_flag":
            load["canonical_values_loaded"] = False
        elif tamper == "retained_flag":
            load["canonical_values_retained"] = True
        elif tamper == "global_hash":
            wrong = "e" * 64
            load["global_sha256"] = wrong
            load["distributed"]["global_sha256"] = wrong
            for rank_record in load["distributed"]["rank_records"]:
                rank_record["global_sha256"] = wrong
        elif tamper == "owner_coverage":
            load["distributed"]["rank_records"][1]["ownership_range"] = [2, 3]
        elif tamper == "recovery":
            record["fgmres"]["checkpoint_history"][0]["recovery"][
                "gamma_rows_local"
            ]["count"] = 1
        elif tamper == "recovery_paired_counts":
            recovery = record["fgmres"]["checkpoint_history"][0]["recovery"]
            recovery["gamma_rows_local"]["count"] = 1889
            recovery["interior_rows_local"]["count"] = 1
        else:
            raise AssertionError(f"unexpected adapter tamper: {tamper}")

    _rewrite_executed_detail_reference(
        root,
        manifest_path,
        rank=0,
        mutate=mutate,
    )
    output = tmp_path / f"adapter-{tamper}.json"
    exit_code, observed = _run_checker_cli(root, output)
    assert exit_code == 2
    assert observed["checker_pass"] is False
    assert observed["evidence_valid"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"


@pytest.mark.parametrize(
    "tamper",
    [
        "exact_residual",
        "exact_classification",
        "conditional_authorization",
        "conditional_prefix_history",
        "formal_scope",
        "root_compact_summary",
    ],
)
def test_v6_2_checker_rejects_rehashed_executed_detail_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    root, manifest_path = _make_executed_checker_fixture(
        tmp_path,
        packet_ready=False,
    )

    def mutate(detail: dict[str, Any]) -> None:
        exact_result = detail["exact_result"]
        record = exact_result["family"]["source_records"][0]
        fgmres = record["fgmres"]
        if tamper == "exact_residual":
            fgmres["checkpoint_history"][0]["full_true_residual_norm"] = 0.8
        elif tamper == "exact_classification":
            exact_result["classification"] = "V6_EXACT_QUALIFICATION_READY_WITH_PACKETS"
        elif tamper == "conditional_authorization":
            fgmres["conditional_authorized"]["256"] = True
        elif tamper == "conditional_prefix_history":
            fgmres["conditional_gate_observations"]["128"][
                "residual_observation"
            ]["observed_checkpoint_sequence"] = [16, 32, 128]
        elif tamper == "formal_scope":
            detail["formal_sequence_start_scope"] = "tampered_scope"
        else:
            raise AssertionError(f"unexpected detail tamper: {tamper}")

    if tamper == "root_compact_summary":
        manifest = json.loads(manifest_path.read_text())
        manifest["exact_qualification"]["summary"]["classification"] = "tampered"
        _write_json(manifest_path, manifest)
    else:
        _rewrite_executed_detail_reference(
            root,
            manifest_path,
            rank=0,
            mutate=mutate,
        )

    output = tmp_path / f"{tamper}.json"
    exit_code, observed = _run_checker_cli(root, output)
    assert exit_code == 2
    assert observed["checker_pass"] is False
    assert observed["evidence_valid"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"


def test_v6_2_checker_rejects_npy_value_after_rehashing_outer_chain(
    tmp_path: Path,
) -> None:
    root, manifest_path = _make_executed_checker_fixture(
        tmp_path,
        packet_ready=True,
    )
    _rehash_packet_value_and_outer_chain(
        root,
        manifest_path,
        label=checker._EXACT_SOURCE_ORDER[0],
        role="exact_output_canonical",
    )
    output = tmp_path / "npy-value-tamper.json"
    exit_code, observed = _run_checker_cli(root, output)
    assert exit_code == 2
    assert observed["checker_pass"] is False
    assert observed["evidence_valid"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"


def test_v6_2_checker_recomputes_packet_aggregate_distributed_contract(
    tmp_path: Path,
) -> None:
    (
        root,
        aggregate,
        expected_by_rank,
        frozen_provenance,
        qualification_provenance,
    ) = _make_packet_aggregate_checker_fixture(tmp_path)
    valid, error = checker._check_packet_aggregate_chain(
        root,
        "aggregate_checker",
        aggregate,
        [],
        expected_identities_by_rank=expected_by_rank,
        expected_qualification_provenance=qualification_provenance,
        expected_frozen_source_provenance=frozen_provenance,
        expected_bare_f_operator_hash=HEX,
    )
    assert valid, error


def test_v6_2_checker_rejects_rehashed_aggregate_count_tamper(
    tmp_path: Path,
) -> None:
    (
        root,
        aggregate,
        expected_by_rank,
        frozen_provenance,
        qualification_provenance,
    ) = _make_packet_aggregate_checker_fixture(tmp_path)
    aggregate_path = root / str(aggregate["path"])
    payload = json.loads(aggregate_path.read_text())
    payload["role_count"] = 3
    aggregate["role_count"] = 3
    aggregate["sha256"] = _write_json(aggregate_path, payload)
    valid, error = checker._check_packet_aggregate_chain(
        root,
        "aggregate_checker",
        aggregate,
        [],
        expected_identities_by_rank=expected_by_rank,
        expected_qualification_provenance=qualification_provenance,
        expected_frozen_source_provenance=frozen_provenance,
        expected_bare_f_operator_hash=HEX,
    )
    assert not valid, error


@pytest.mark.parametrize("tamper", ["ownership_gap", "canonical_count"])
def test_v6_2_checker_rejects_rehashed_packet_aggregate_layout_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    (
        root,
        aggregate,
        expected_by_rank,
        frozen_provenance,
        qualification_provenance,
    ) = _make_packet_aggregate_checker_fixture(tmp_path)
    rank = 1 if tamper == "ownership_gap" else 0
    role = (
        "exact_output_owner_rows"
        if tamper == "ownership_gap"
        else "exact_output_canonical"
    )
    updates: dict[str, Any]
    values = None
    if tamper == "ownership_gap":
        updates = {"ownership_range": [2, 3]}
    else:
        updates = {"canonical_key_count_local": 2}
        values = np.asarray([1.0 + 0.5j, 2.0 + 0.5j], dtype=np.complex128)
    packet = _rewrite_packet_for_checker_tamper(
        expected_by_rank[rank][role], updates=updates, values=values
    )
    expected_by_rank[rank][role] = packet
    tampered_aggregate = _rewrite_checker_aggregate(
        root,
        aggregate,
        rank=rank,
        role=role,
        packet=packet,
    )
    valid, error = checker._check_packet_aggregate_chain(
        root,
        "aggregate_checker",
        tampered_aggregate,
        [],
        expected_identities_by_rank=expected_by_rank,
        expected_qualification_provenance=qualification_provenance,
        expected_frozen_source_provenance=frozen_provenance,
        expected_bare_f_operator_hash=HEX,
    )
    assert not valid, error


@pytest.mark.parametrize("tamper", ["descriptor_only", "descriptor_and_payload"])
def test_v6_2_checker_rejects_rehashed_packet_aggregate_bare_hash_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    (
        root,
        aggregate,
        expected_by_rank,
        frozen_provenance,
        qualification_provenance,
    ) = _make_packet_aggregate_checker_fixture(tmp_path)
    wrong_hash = "e" * 64
    tampered_aggregate = dict(aggregate)
    tampered_aggregate["bare_f_operator_hash"] = wrong_hash
    aggregate_path = root / str(aggregate["path"])
    if tamper == "descriptor_and_payload":
        payload = json.loads(aggregate_path.read_text())
        payload["bare_f_operator_hash"] = wrong_hash
        tampered_sha = _write_json(aggregate_path, payload)
        tampered_aggregate["sha256"] = tampered_sha
    valid, error = checker._check_packet_aggregate_chain(
        root,
        "aggregate_checker",
        tampered_aggregate,
        [],
        expected_identities_by_rank=expected_by_rank,
        expected_qualification_provenance=qualification_provenance,
        expected_frozen_source_provenance=frozen_provenance,
        expected_bare_f_operator_hash=HEX,
    )
    assert not valid, error


def test_v6_2_checker_rejects_rehashed_cross_role_source_definition_tamper(
    tmp_path: Path,
) -> None:
    (
        root,
        aggregate,
        expected_by_rank,
        frozen_provenance,
        qualification_provenance,
    ) = _make_packet_aggregate_checker_fixture(tmp_path)
    role = "gamma_l_canonical"
    packet = _rewrite_packet_for_checker_tamper(
        expected_by_rank[0][role],
        updates={"source_definition_sha256": "d" * 64},
    )
    expected_by_rank[0][role] = packet
    aggregate = _rewrite_checker_aggregate(
        root,
        aggregate,
        rank=0,
        role=role,
        packet=packet,
    )
    valid, error = checker._check_packet_aggregate_chain(
        root,
        "aggregate_checker",
        aggregate,
        [],
        expected_identities_by_rank=expected_by_rank,
        expected_qualification_provenance=qualification_provenance,
        expected_frozen_source_provenance=frozen_provenance,
        expected_bare_f_operator_hash=HEX,
    )
    assert not valid, error


def test_v6_2_checker_rejects_self_consistent_wrong_packet_writer_identity(
    tmp_path: Path,
) -> None:
    root, _aggregate, expected_by_rank, _frozen, _qualification = (
        _make_packet_aggregate_checker_fixture(tmp_path)
    )
    packet = dict(expected_by_rank[0]["exact_output_canonical"])
    wrong_identity = "test.writer"
    packet["writer_identity"] = wrong_identity
    metadata_path = Path(str(packet["path"]))
    manifest_path = Path(str(packet["manifest_path"]))
    metadata = json.loads(metadata_path.read_text())
    metadata["writer_identity"] = wrong_identity
    metadata_sha = _write_json(metadata_path, metadata)
    manifest = json.loads(manifest_path.read_text())
    manifest["writer_identity"] = wrong_identity
    manifest["metadata_sha256"] = metadata_sha
    manifest_sha = _write_json(manifest_path, manifest)
    packet["metadata_sha256"] = metadata_sha
    packet["manifest_sha256"] = manifest_sha
    valid, error = checker._check_packet_file_chain(
        root,
        "aggregate_checker",
        "exact_output_canonical",
        packet,
        [],
    )
    assert not valid
    assert error is not None and "writer identity" in error


def test_v6_2_linearity_probe_copies_source_into_combined() -> None:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, 4), (PETSc.DECIDE, 4)),
        nnz=1,
        comm=PETSc.COMM_SELF,
    )
    for row in range(4):
        matrix.setValue(row, row, PETSc.ScalarType(1.0 + 0.0j))
    matrix.assemble()

    captured_sources: list[np.ndarray] = []

    class _RecordingMatrix:
        @staticmethod
        def createVecLeft() -> PETSc.Vec:
            return matrix.createVecLeft()

        @staticmethod
        def mult(source: PETSc.Vec, target: PETSc.Vec) -> None:
            captured_sources.append(np.asarray(source.array).copy())
            matrix.mult(source, target)

    class _IdentityAction:
        @staticmethod
        def create_interface_vector() -> PETSc.Vec:
            return matrix.createVecRight()

    try:
        assert runner._linearity_probe(
            MPI.COMM_SELF, _RecordingMatrix, _IdentityAction
        ) <= runner.V6_2_ROUNDTRIP_TOLERANCE
        positions = np.arange(4, dtype=np.float64)
        expected = PETSc.ScalarType(
            11 * (0.125 + 0.00001 * positions)
            + 1j * (0.03125 * 11 + 0.000003 * positions)
        )
        assert len(captured_sources) == 3
        np.testing.assert_allclose(captured_sources[0], expected)
    finally:
        matrix.destroy()


def test_v6_2_linearity_probe_distributed_owner_rows() -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("run this owner-row smoke with mpiexec -n 2")
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, 4), (PETSc.DECIDE, 4)),
        nnz=1,
        comm=MPI.COMM_WORLD,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValue(row, row, PETSc.ScalarType(1.0 + 0.0j))
    matrix.assemble()

    class _IdentityAction:
        @staticmethod
        def create_interface_vector() -> PETSc.Vec:
            return matrix.createVecRight()

    try:
        assert runner._linearity_probe(
            MPI.COMM_WORLD, matrix, _IdentityAction
        ) <= runner.V6_2_ROUNDTRIP_TOLERANCE
    finally:
        matrix.destroy()


def test_v6_2_plan_binds_resource_and_post_identity_qualification(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.dat"
    spool_root = tmp_path / "frozen-spool"
    run_root = tmp_path / "run"
    watchdog_root = tmp_path / "watchdog"
    plan = level_a.build_task040_level_a_plan(
        input_path=input_path,
        exact_spool_root=spool_root,
        run_directory=run_root,
        source_sha=FORMAL_SOURCE_SHA,
        v6_2_interface_schur=True,
    )
    assert plan["mpi_size"] == 8
    assert plan["threads"] == 1
    assert plan["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert plan["minimum_mem_available_bytes"] == 49 * 2**30
    assert plan["exact_qualification_plan"]["status"] == "configured_same_process_exact"
    assert plan["exact_qualification_plan"]["checkpoints"] == [16, 32, 64, 128]
    assert (
        plan["exact_qualification_plan"]["frozen_owner_row_arrays"]
        .startswith("loaded per source only after")
    )
    assert "raw_global_row_remap" in plan["forbidden"]
    assert "full_side_factor" in plan["forbidden"]

    watched = watchdog.build_task040_level_a_watchdog_plan(
        input_path=input_path,
        exact_spool_root=spool_root,
        run_directory=watchdog_root,
        source_sha=FORMAL_SOURCE_SHA,
        v6_2_interface_schur=True,
    )
    assert watched["watchdog"]["hard_stop_bytes"] == 45 * 2**30
    assert watched["watchdog"]["minimum_mem_available_bytes"] == 49 * 2**30
    assert watched["watchdog"]["process_tree_watchdog_enabled"] is True
    assert watched["watchdog"]["v6_2_identity_only"] is False
    assert "v6_2_preflight_only" not in watched["watchdog"]
    assert "--watchdog-hard-stop-bytes" in watched["worker_argv"]
    assert watched["worker_argv"].count("--v6-2-interface-schur") == 1

    v7_plan = level_a.build_task040_level_a_plan(
        input_path=input_path,
        exact_spool_root=spool_root,
        run_directory=tmp_path / "v7-run",
        source_sha=FORMAL_SOURCE_SHA,
        v7_scale_normalized_identity=True,
    )
    assert v7_plan["v7_scale_normalized_identity"] is True
    assert v7_plan["schema"] == runner.V7_SCALE_NORMALIZED_IDENTITY_FORMAL_SCHEMA
    assert v7_plan["system_created"] is False
    assert v7_plan["timeout_seconds"] == 21600
    assert v7_plan["pde_solve"] == "full_spectrum_continuation_required"
    assert v7_plan["full_spectrum_continuation"] == "required"
    assert v7_plan["exact_qualification"] == "intentional_not_run_by_v7_direct_mainline"
    assert v7_plan["root_metadata_gather"] is True
    assert v7_plan["metadata_only_descriptor_gather"] is True
    assert v7_plan["conditional_authorized"] == {"refinement": "one_evidence_driven_refinement", "separator_closure": "one_evidence_driven_separator_closure"}
    assert {"threshold_relaxation", "refinement_count_or_parameter_scan", "repeated_separator_closure", "mumps_parameter_scan", "raw_petsc_row_fft"} <= set(v7_plan["forbidden"])
    assert {"refinement", "separator_closure"}.isdisjoint(v7_plan["forbidden"])
    with pytest.raises(ValueError, match="mutually exclusive"):
        level_a.build_task040_level_a_plan(
            input_path=input_path,
            exact_spool_root=spool_root,
            run_directory=tmp_path / "v7-conflict",
            source_sha=FORMAL_SOURCE_SHA,
            v6_2_interface_schur=True,
            v7_scale_normalized_identity=True,
        )
    v7_watched = watchdog.build_task040_level_a_watchdog_plan(
        input_path=input_path,
        exact_spool_root=spool_root,
        run_directory=tmp_path / "v7-watchdog",
        source_sha=FORMAL_SOURCE_SHA,
        v7_scale_normalized_identity=True,
    )
    assert v7_watched["watchdog"]["hard_stop_bytes"] == 45 * 2**30
    assert v7_watched["watchdog"]["timeout_seconds"] == 21600
    assert v7_watched["watchdog"]["v7_identity_target_seconds"] == v7_plan["identity_target_seconds"]
    assert v7_watched["watchdog"]["v7_identity_hard_seconds"] == v7_plan["identity_hard_seconds"]
    assert v7_watched["watchdog"]["root_metadata_gather"] is True
    assert v7_watched["watchdog"]["metadata_only_descriptor_gather"] is True
    assert v7_watched["worker_argv"].count(
        runner.V7_SCALE_NORMALIZED_IDENTITY_FLAG
    ) == 1
    assert "--v6-2-interface-schur" not in v7_watched["worker_argv"]

    v7_stop_root = tmp_path / "v7-stop"
    stopped = runner.run_v6_2_interface_schur(
        None,
        None,
        comm=MPI.COMM_SELF,
        exact_spool_root=tmp_path / "unavailable-frozen-root",
        run_directory=v7_stop_root,
        source_sha=FORMAL_SOURCE_SHA,
        input_path=input_path,
        input_sha256=HEX,
        physical_model_sha256=HEX,
        v7_scale_normalized_identity=True,
    )
    assert stopped["status"] == "not_run_by_v7_continuation_gate"
    assert stopped["system_created"] is False
    assert stopped["v7_progress_gate"]["exact_not_run"] is True
    assert not v7_stop_root.exists()


@pytest.mark.parametrize("restart", [True, False, 0, -1, 3.5, "32"])
def test_v6_2_formal_numeric_options_reject_invalid_restart(
    restart: Any,
) -> None:
    with pytest.raises(ValueError, match="restart must be a positive integer"):
        runner._v6_2_formal_numeric_options({"restart": restart})


def test_v6_2_resource_preflight_uses_observed_environment_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import benchmarks.task034_wsl_resources as resources

    hard_stop = 45 * 2**30
    monkeypatch.setenv("MYFENICS_NATIVE_COMPLEX_ENV", "1")
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setattr(
        resources,
        "wsl_memory_snapshot",
        lambda: {"mem_available_bytes": 50 * 2**30},
    )
    monkeypatch.setattr(
        level_a,
        "_worker_current_resource",
        lambda comm, hard_limit_bytes: {
            "swap_bytes": 0,
            "all_status_readable": True,
            "pass": True,
        },
    )
    monkeypatch.setattr(
        runner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=21 * 2**30),
    )

    observed = runner._resource_preflight(
        MPI.COMM_SELF,
        tmp_path,
        hard_stop_bytes=hard_stop,
        watchdog_hard_stop_bytes=hard_stop,
    )
    assert observed["checks"]["mem_available_at_least_minimum"] is True
    assert observed["checks"]["watchdog_hard_stop_matches_worker"] is True
    assert observed["checks"]["swap_zero"] is True
    assert observed["minimum_mem_available_bytes"] == 49 * 2**30
    assert observed["watchdog_hard_stop_bytes"] == hard_stop
    assert observed["pass"] is False
    assert observed["checks"]["mpi_size_8"] is False


def test_v6_2_checker_validates_rank_artifacts_and_gate(tmp_path: Path) -> None:
    root, _manifest_path = _make_checker_fixture(tmp_path)
    output = tmp_path / "checker.json"
    result = checker.check_v6_2_interface_schur(
        formal_root=root,
        formal_source_sha=FORMAL_SOURCE_SHA,
        checker_source_sha=CHECKER_SOURCE_SHA,
        output=output,
    )
    assert result["evidence_valid"] is True
    assert result["checker_pass"] is True
    assert result["gate_pass"] is True
    assert result["classification"] == "V6_2_FULL_INTERFACE_SCHUR_PASS"
    assert result["evidence_checks"]["watchdog_audit"] is True
    assert result["watchdog_audit"]["valid"] is True
    assert result["evidence_checks"]["evidence_rank_mapping_count_observed"] is True
    assert result["gate_checks"]["rank_deterministic_scalars"] is True
    assert result["gate_checks"]["rank_mapping_count_sum"] is True
    assert all(not item["path"].endswith(".npy") for item in result["read_files"])
    watchdog_path = root.parent / "watchdog_summary.json"
    watchdog_summary = json.loads(watchdog_path.read_text(encoding="utf-8"))
    watchdog_summary["peak_rss_bytes"] = checker.EXPECTED_HARD_STOP_BYTES
    _write_json(watchdog_path, watchdog_summary)
    failed = checker.check_v6_2_interface_schur(
        formal_root=root,
        formal_source_sha=FORMAL_SOURCE_SHA,
        checker_source_sha=CHECKER_SOURCE_SHA,
        output=output,
    )
    assert failed["evidence_checks"]["watchdog_audit"] is False
    assert failed["evidence_valid"] is False
    assert failed["checker_pass"] is False


def test_v7_raw_checker_recomputes_metrics_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    payload = _v7_raw_metric_fixture()
    checked = v7_checker.check_v7_scale_normalized_identity(payload)
    assert checked["checker_pass"] is True
    assert checked["evidence_valid"] is True
    assert checked["formal_adjudication"] is False
    assert checked["classification"] == "not_formal_adjudication"
    assert checked["gate_candidates"]["d0_pass_candidate"] is True
    assert checked["gate_candidates"]["d1_pass_candidate"] is True
    assert checked["gate_candidates"]["legacy_absolute_gate"] is False
    assert checked["selected_candidate"] == "d0_lower_memory"
    assert checked["next_required_stage"] == (
        "formal_integration_requires_full_spectrum_continuation"
    )
    assert checked["runner_claims"]["gate_pass"] is False

    bundle_root = tmp_path / "v7-bundle"
    rank_root = bundle_root / "rank0000"
    rank_root.mkdir(parents=True)
    descriptor = runner._write_v7_identity_bundle(
        rank_root=rank_root,
        output_root=bundle_root,
        raw_metrics=payload,
        checker_result=checked,
        source_sha=FORMAL_SOURCE_SHA,
        input_sha256=HEX,
        physical_model_sha256=HEX,
        elapsed_seconds=1.25,
        selected_operator={"candidate": checked["selected_candidate"]},
    )
    bundle = json.loads(
        (rank_root / "v7_scale_normalized_identity_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    assert descriptor["readback_valid"] is True
    assert descriptor["sha256"] == runner.hash_file_sha256(
        rank_root / "v7_scale_normalized_identity_bundle.json"
    )
    assert runner._v7_canonical_json_sha256(bundle["raw"]) == bundle["raw_sha256"] == descriptor["raw_sha256"]
    assert runner._v7_canonical_json_sha256(bundle["checker"]) == bundle["checker_sha256"] == descriptor["checker_sha256"]
    assert "bundle_sha256" not in bundle
    consensus_input = {
        "mpi_size": 1,
        "evidence_valid": True,
        "checker_pass": True,
        "d0_pass_candidate": True,
        "d1_pass_candidate": True,
        "formal_adjudication": False,
        "selected_candidate": "d0_lower_memory",
        "next_required_stage": "formal_integration_requires_full_spectrum_continuation",
        "expected_next_required_stage": "formal_integration_requires_full_spectrum_continuation",
        "identity_elapsed_seconds": 1.25,
        "bundle_readback_valid": True,
    }
    consensus = runner._v7_compact_decision_consensus(MPI.COMM_SELF, consensus_input)
    assert consensus["metadata_only"] is True
    assert consensus["evidence_valid_consensus"] is True
    assert consensus["d0_pass_candidate"] is True
    assert consensus["d1_pass_candidate"] is True
    assert consensus["formal_adjudication"] is False
    assert consensus["expected_next_required_stage"] == "formal_integration_requires_full_spectrum_continuation"
    assert consensus["selected_candidate_consensus"] is True
    assert consensus["mpi_size_8"] is False
    assert consensus["pass"] is False

    class MetadataComm:
        size = 8

        def allgather(self, value: Mapping[str, Any]) -> list[dict[str, Any]]:
            return [dict(value) for _ in range(self.size)]

    passed = runner._v7_compact_decision_consensus(
        MetadataComm(), {**consensus_input, "mpi_size": 8}
    )
    assert passed["pass"] is True

    forged_claim = deepcopy(payload)
    forged_claim["runner_claims"]["gate_pass"] = True
    forged = v7_checker.check_v7_scale_normalized_identity(forged_claim)
    assert forged["checker_pass"] is True
    assert forged["gate_candidates"]["d0_pass_candidate"] is True
    assert forged["gate_candidates"]["d1_pass_candidate"] is True

    raw_tamper = deepcopy(payload)
    raw_tamper["identity_records"][0]["layer_c"]["d0"]["identity"]["terms"][
        "diff"
    ] = 1.0
    rejected = v7_checker.check_v7_scale_normalized_identity(raw_tamper)
    assert rejected["checker_pass"] is True
    assert rejected["gate_candidates"]["d0_pass_candidate"] is False
    assert rejected["gate_candidates"]["d1_pass_candidate"] is True
    assert rejected["gate_candidates"]["partition_audit_trigger"] is False

    both_tampered = deepcopy(raw_tamper)
    both_tampered["identity_records"][0]["layer_c"]["d1"]["identity"]["terms"][
        "diff"
    ] = 1.0
    both = v7_checker.check_v7_scale_normalized_identity(both_tampered)
    assert both["checker_pass"] is False
    assert both["gate_candidates"]["d0_pass_candidate"] is False
    assert both["gate_candidates"]["d1_pass_candidate"] is False
    assert both["gate_candidates"]["partition_audit_trigger"] is True
    assert both["next_required_stage"] == "group_partition_closure_audit"

    group_tamper = deepcopy(payload)
    group_tamper["identity_records"][0]["layer_a"]["groups"][0]["repeat"][
        "terms"
    ]["diff"] = 1.0
    refined = v7_checker.check_v7_scale_normalized_identity(group_tamper)
    assert refined["checker_pass"] is False
    assert refined["gate_candidates"]["group_refinement_trigger"] is True
    assert refined["next_required_stage"] == "conditional_one_residual_correction"

    layer_b_tamper = deepcopy(payload)
    layer_b_tamper["linearity_records"][0]["layer_b"]["middle_boundary"][
        "repeat"
    ]["terms"]["diff"] = 1.0
    layer_b_failed = v7_checker.check_v7_scale_normalized_identity(layer_b_tamper)
    assert layer_b_failed["evidence_valid"] is True
    assert layer_b_failed["gate_candidates"]["d0_identity"] is True
    assert layer_b_failed["gate_candidates"]["d1_identity"] is True
    assert layer_b_failed["gate_candidates"]["d0_pass_candidate"] is False
    assert layer_b_failed["gate_candidates"]["d1_pass_candidate"] is False
    assert layer_b_failed["gate_candidates"]["partition_audit_trigger"] is False
    assert layer_b_failed["selected_candidate"] is None
    assert layer_b_failed["next_required_stage"] == (
        "resolve_group_local_or_structural_identity_gate"
    )

    assert v7_checker.relative_from_terms(1.0e-300, 0.0, 0.0) == 1.0
    for mutation in ("source", "scale", "group"):
        missing = deepcopy(payload)
        if mutation == "source":
            missing["identity_records"][0].pop("source_index")
        elif mutation == "scale":
            missing["identity_records"][0].pop("scale")
        else:
            missing["identity_records"][0]["layer_a"]["groups"][0].pop(
                "group"
            )
        invalid = v7_checker.check_v7_scale_normalized_identity(missing)
        assert invalid["evidence_valid"] is False
        assert invalid["checker_pass"] is False


def test_v6_2_checker_accepts_requested_checkpoint_happy_breakdown() -> None:
    def source_record(label: str) -> dict[str, Any]:
        row = {
            "label": label,
            "iteration": 16,
            "restart": 16,
            "checkpoint_kind": "mandatory",
            "interface_true_residual_norm": 1.0,
            "interface_true_residual_relative": 1.0,
            "full_true_residual_norm": 0.5,
            "full_true_residual_relative": 0.5,
            "rhs_norm_denominator": 1.0,
            "interface_rhs_norm_denominator": 1.0,
            "full_residual_tolerance": 1.0e-9,
            "finite": True,
            "accepted_full_solution": False,
        }
        fgmres = {
            "schema": "task040.v6.exact_interface_fgmres.v1",
            "label": label,
            "restart": 16,
            "mandatory_checkpoints": [16, 32, 64, 128],
            "conditional_checkpoints": [256, 512],
            "checkpoints": {"16": row},
            "final_iteration": 16,
            "final_record": row,
            "early_final_record": None,
            "checkpoint_history": [row],
            "stopped_at_happy_breakdown": True,
            "conditional_authorized": {"256": False, "512": False},
            "conditional_completed": {"256": False, "512": False},
            "conditional_gate_observations": {},
            "full_residual_tolerance": 1.0e-9,
            "accepted_solution_present": False,
            "accepted_solution_consumed": False,
            "accepted_solution_released_by_driver": False,
            "numeric_allgather": False,
            "full_numeric_replica": False,
            "identity_preconditioner": True,
            "active_rhs_unchanged": True,
            "condensed_rhs_unchanged": True,
            "full_rhs_norm": 1.0,
            "interface_rhs_norm": 1.0,
            "active_rhs_initial_sha256": HEX,
            "active_rhs_final_sha256": HEX,
            "condensed_rhs_initial_sha256": HEX,
            "condensed_rhs_final_sha256": HEX,
        }
        return {
            "label": label,
            "best_full_true_residual_relative": 0.5,
            "full_residual_gate_pass": False,
            "packetization_gate_pass": False,
            "fgmres": fgmres,
        }

    records = [source_record(label) for label in checker._EXACT_SOURCE_ORDER[:2]]
    family = {
        "schema": "task040.v6.exact_qualification_family.v1",
        "ordered_labels": list(checker._EXACT_SOURCE_ORDER),
        "initial_labels": list(checker._EXACT_SOURCE_ORDER[:2]),
        "source_records": records,
        "skipped_labels": list(checker._EXACT_SOURCE_ORDER[2:]),
        "initial_pair_gate_pass": False,
        "all_sources_gate_pass": False,
        "full_residual_tolerance": 1.0e-9,
        "packetization_required": True,
        "status": "completed_exact_numerical_gate_negative_continuation_allowed",
        "classification": "V6_EXACT_QUALIFICATION_GATE_FAIL",
        "normal_numerical_negative": True,
        "numeric_allgather": False,
        "full_numeric_replica": False,
    }
    exact_result = {
        "schema": "task040.v6_2.exact_qualification_packets.v1",
        "status": "completed_exact_numerical_gate_negative_continuation_allowed",
        "classification": "V6_EXACT_QUALIFICATION_GATE_FAIL",
        "source_order": list(checker._EXACT_SOURCE_ORDER),
        "family": family,
        "numeric_allgather": False,
        "full_numeric_replica": False,
    }
    summary, _identities = checker._exact_detail_semantic_signature(exact_result)
    assert summary["numerical_negative"] is True
    assert summary["source_records"][0]["checkpoint_history"][0]["iteration"] == 16


def test_v6_2_checker_rejects_rank_scalar_tamper_after_descriptor_update(
    tmp_path: Path,
) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    tampered = root / "rank0003.json"
    payload = json.loads(tampered.read_text())
    payload["zero_error"] = 1.0e-4
    tampered_sha = _write_json(tampered, payload)
    manifest = json.loads(manifest_path.read_text())
    for descriptor in manifest["rank_artifacts"]:
        if descriptor["path"] == tampered.name:
            descriptor["sha256"] = tampered_sha
            break
    else:
        raise AssertionError("tampered rank descriptor was not found")
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-tampered.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    observed = json.loads(output.read_text())
    assert observed["checker_pass"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"
    assert observed["evidence_checks"][
        "evidence_rank_zero_linearity_consistent"
    ] is False


def _make_conditional_positive_checker_fixture(
    tmp_path: Path,
) -> tuple[Path, Path]:
    """Build a no-packet exact negative that legitimately reaches 512."""

    root, manifest_path = _make_executed_checker_fixture(
        tmp_path,
        packet_ready=False,
    )
    manifest = json.loads(manifest_path.read_text())
    compact_by_rank: dict[int, dict[str, Any]] = {}
    residuals = {
        16: 0.9,
        32: 0.8,
        64: 0.7,
        128: 0.6,
        256: 0.005,
        512: 0.004,
    }
    for rank in range(checker.EXPECTED_MPI_SIZE):
        reference = manifest["exact_qualification_artifacts"][rank]
        detail_path = root / str(reference["path"])
        detail = json.loads(detail_path.read_text())
        exact_result = detail["exact_result"]
        expected_gamma_local_count = manifest["rank_artifacts"][rank][
            "canonical_mapping_count"
        ]
        for record in exact_result["family"]["source_records"]:
            label = str(record["label"])
            active_local_size = record["adapter"]["load"]["local_size"]
            rows = []
            for iteration, value in residuals.items():
                row = _executed_checkpoint(
                    label,
                    iteration,
                    value,
                    accepted=False,
                    gamma_rows_local_count=expected_gamma_local_count,
                    active_local_size=active_local_size,
                )
                if iteration in {256, 512}:
                    row["checkpoint_kind"] = "conditional"
                rows.append(row)
            fgmres = record["fgmres"]
            fgmres.update(
                {
                    "checkpoints": {
                        str(row["iteration"]): row for row in rows
                    },
                    "final_iteration": 512,
                    "final_record": rows[-1],
                    "checkpoint_history": rows,
                    "conditional_authorized": {"256": True, "512": True},
                    "conditional_completed": {"256": True, "512": True},
                    "conditional_gate_observations": {
                        "128": _conditional_positive_128_observation(
                            residuals
                        ),
                        "256": _conditional_positive_256_observation(
                            residuals
                        ),
                    },
                    "accepted_solution_present": False,
                    "accepted_solution_consumed": False,
                    "accepted_solution_released_by_driver": False,
                    "accepted_solution_iteration": None,
                }
            )
            record["best_full_true_residual_relative"] = residuals[512]
            record["full_residual_gate_pass"] = False
            record["packetization_gate_pass"] = False
        compact, _identities = checker._exact_detail_semantic_signature(
            exact_result
        )
        compact = checker._recomputed_exact_compact_summary(
            exact_result,
            compact,
        )
        detail_sha = _write_json(detail_path, detail)
        reference = deepcopy(reference)
        reference["sha256"] = detail_sha
        manifest["exact_qualification_artifacts"][rank] = reference
        rank_descriptor = manifest["rank_artifacts"][rank]
        rank_path = root / str(rank_descriptor["path"])
        rank_artifact = json.loads(rank_path.read_text())
        rank_artifact["exact_qualification_artifact"] = reference
        rank_artifact["exact_qualification"] = compact
        rank_descriptor["exact_qualification_artifact"] = reference
        rank_descriptor["exact_qualification"] = compact
        rank_descriptor["sha256"] = _write_json(rank_path, rank_artifact)
        manifest["rank_artifacts"][rank] = rank_descriptor
        compact_by_rank[rank] = compact
    assert len({json.dumps(value, sort_keys=True) for value in compact_by_rank.values()}) == 1
    manifest["exact_qualification"]["summary"] = compact_by_rank[0]
    manifest["exact_qualification_artifact_chain_sha256"] = hashlib.sha256(
        json.dumps(
            manifest["exact_qualification_artifacts"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write_json(manifest_path, manifest)
    return root, manifest_path


def _conditional_positive_resource() -> dict[str, Any]:
    return {
        "pass": True,
        "hard_limit_bytes": 45 * 2**30,
        "rss_bytes": 1024,
        "swap_bytes": 0.0,
        "all_status_readable": True,
        "wall_observation": {
            "elapsed_seconds": 2.0,
            "budget_seconds": 21600.0,
        },
    }


def _conditional_positive_128_observation(
    residuals: Mapping[int, float],
) -> dict[str, Any]:
    observation = _executed_128_observation(residuals[128])
    drop = float(np.log10(residuals[64] / residuals[128]))
    observation["residual_observation"].update(
        {
            "r64": residuals[64],
            "r128": residuals[128],
            "drop_64_to_128_decade": drop,
        }
    )
    return observation


def _conditional_positive_256_observation(
    residuals: Mapping[int, float],
) -> dict[str, Any]:
    resource = _conditional_positive_resource()
    wall = dict(resource["wall_observation"])
    return {
        "target_checkpoint": 512,
        "residual_gate": True,
        "authorized": True,
        "authorization_consensus": True,
        "authorized_by_rank": [True] * checker.EXPECTED_MPI_SIZE,
        "resource_snapshot": resource,
        "resource_observation": {
            "current_sample_only": True,
            "current_rss_bytes": resource["rss_bytes"],
            "current_swap_bytes": resource["swap_bytes"],
            "all_status_readable": True,
            "pass": True,
        },
        "resource_gate": True,
        "wall_observation": wall,
        "wall_gate": True,
        "residual_observation": {
            "checkpoint": 256,
            "observed_checkpoint_sequence": [16, 32, 64, 128, 256],
            "required_checkpoint_iterations": [16, 32, 64, 128, 256],
            "r64": residuals[64],
            "r128": residuals[128],
            "r256": residuals[256],
            "drop_64_to_128_decade": None,
            "required_checkpoint_set_complete": True,
            "monotone_history": True,
        },
    }


def _rewrite_executed_detail_chain(
    root: Path,
    manifest_path: Path,
    *,
    mutate: Callable[[dict[str, Any]], None],
    preserve_compact: bool = False,
) -> None:
    """Rehash exact details and their outer references.

    Invalid semantic tamper fixtures must be written without asking the
    checker to recompute their compact summary.  In that mode the original
    compact summary remains the recorded claim while every changed detail
    and outer reference is still hash-bound.
    """

    manifest = json.loads(manifest_path.read_text())
    compact_by_rank: dict[int, dict[str, Any]] = {}
    for rank in range(checker.EXPECTED_MPI_SIZE):
        reference = deepcopy(manifest["exact_qualification_artifacts"][rank])
        detail_path = root / str(reference["path"])
        detail = json.loads(detail_path.read_text())
        rank_descriptor = manifest["rank_artifacts"][rank]
        rank_path = root / str(rank_descriptor["path"])
        rank_artifact = json.loads(rank_path.read_text())
        original_compact = deepcopy(rank_artifact["exact_qualification"])
        mutate(detail)
        if preserve_compact:
            compact = original_compact
        else:
            exact_result = detail["exact_result"]
            compact, _identities = checker._exact_detail_semantic_signature(
                exact_result
            )
            compact = checker._recomputed_exact_compact_summary(
                exact_result,
                compact,
            )
        reference["sha256"] = _write_json(detail_path, detail)
        manifest["exact_qualification_artifacts"][rank] = reference
        rank_artifact["exact_qualification_artifact"] = reference
        rank_artifact["exact_qualification"] = compact
        rank_descriptor["exact_qualification_artifact"] = reference
        rank_descriptor["exact_qualification"] = compact
        rank_descriptor["sha256"] = _write_json(rank_path, rank_artifact)
        manifest["rank_artifacts"][rank] = rank_descriptor
        compact_by_rank[rank] = compact
    manifest["exact_qualification"]["summary"] = compact_by_rank[0]
    manifest["exact_qualification_artifact_chain_sha256"] = hashlib.sha256(
        json.dumps(
            manifest["exact_qualification_artifacts"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write_json(manifest_path, manifest)


def _rewrite_full_formal_scope_chain(
    root: Path,
    manifest_path: Path,
    *,
    scope: str,
) -> None:
    """Change every formal-scope copy while preserving the outer hashes."""

    manifest = json.loads(manifest_path.read_text())
    references: list[dict[str, Any]] = []
    for rank in range(checker.EXPECTED_MPI_SIZE):
        reference = deepcopy(manifest["exact_qualification_artifacts"][rank])
        detail_path = root / str(reference["path"])
        detail = json.loads(detail_path.read_text())
        detail["formal_sequence_start_scope"] = scope
        reference["formal_sequence_start_scope"] = scope
        reference["sha256"] = _write_json(detail_path, detail)
        references.append(reference)
        rank_descriptor = manifest["rank_artifacts"][rank]
        rank_path = root / str(rank_descriptor["path"])
        rank_artifact = json.loads(rank_path.read_text())
        rank_artifact["formal_sequence_start_scope"] = scope
        rank_artifact["exact_qualification_artifact"] = reference
        rank_descriptor["formal_sequence_start_scope"] = scope
        rank_descriptor["exact_qualification_artifact"] = reference
        rank_descriptor["sha256"] = _write_json(rank_path, rank_artifact)
        manifest["rank_artifacts"][rank] = rank_descriptor
    manifest["exact_qualification_artifacts"] = references
    manifest["formal_sequence_start_scope"] = scope
    manifest["exact_qualification_artifact_chain_sha256"] = hashlib.sha256(
        json.dumps(references, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    _write_json(manifest_path, manifest)


@pytest.mark.parametrize(
    "tamper",
    [None, "authorization", "resource", "wall", "monotone"],
)
def test_v6_2_checker_recomputes_conditional_256_512_gate(
    tmp_path: Path,
    tamper: str | None,
) -> None:
    root, manifest_path = _make_conditional_positive_checker_fixture(tmp_path)
    if tamper is not None:

        def mutate(detail: dict[str, Any]) -> None:
            fgmres = detail["exact_result"]["family"]["source_records"][0][
                "fgmres"
            ]
            observation = fgmres["conditional_gate_observations"]["256"]
            if tamper == "authorization":
                fgmres["conditional_authorized"]["512"] = False
            elif tamper == "resource":
                hard_limit = checker.EXPECTED_HARD_STOP_BYTES
                resource = observation["resource_snapshot"]
                resource["rss_bytes"] = hard_limit
                observation["resource_observation"]["current_rss_bytes"] = (
                    hard_limit
                )
                resource["pass"] = False
                observation["resource_observation"]["pass"] = False
                observation["resource_gate"] = False
                fgmres["conditional_authorized"]["512"] = False
            elif tamper == "wall":
                resource_wall = observation["resource_snapshot"][
                    "wall_observation"
                ]
                resource_wall["elapsed_seconds"] = 21600.0
                observation["wall_observation"]["elapsed_seconds"] = 21600.0
                observation["wall_gate"] = False
                fgmres["conditional_authorized"]["512"] = False
            elif tamper == "monotone":
                observation["residual_observation"]["monotone_history"] = False
                fgmres["conditional_authorized"]["512"] = False
            else:
                raise AssertionError(f"unexpected conditional tamper: {tamper}")

        _rewrite_executed_detail_chain(
            root,
            manifest_path,
            mutate=mutate,
            preserve_compact=True,
        )
    output = tmp_path / (
        "conditional-positive.json"
        if tamper is None
        else f"conditional-{tamper}.json"
    )
    exit_code, observed = _run_checker_cli(root, output)
    if tamper is None:
        assert exit_code == 0
        assert observed["checker_pass"] is True
        assert observed["evidence_valid"] is True
        assert observed["gate_pass"] is False
        assert (
            observed["classification"]
            == "V6_2_FULL_INTERFACE_SCHUR_NUMERICAL_NEGATIVE"
        )
        for rank in range(checker.EXPECTED_MPI_SIZE):
            detail = json.loads(
                (
                    root
                    / f"rank{rank:04d}"
                    / "v6_2_exact_qualification.json"
                ).read_text()
            )
            for record in detail["exact_result"]["family"]["source_records"]:
                fgmres = record["fgmres"]
                assert fgmres["final_iteration"] == 512
                assert fgmres["conditional_authorized"] == {
                    "256": True,
                    "512": True,
                }
                assert fgmres["conditional_completed"] == {
                    "256": True,
                    "512": True,
                }
    else:
        assert exit_code == 2
        assert observed["checker_pass"] is False
        assert observed["evidence_valid"] is False
        assert observed["classification"] == "IMPLEMENTATION_FAILURE"


def test_v6_2_checker_rejects_rehashed_wrong_formal_scope_across_full_chain(
    tmp_path: Path,
) -> None:
    root, manifest_path = _make_executed_checker_fixture(
        tmp_path,
        packet_ready=False,
    )
    _rewrite_full_formal_scope_chain(
        root,
        manifest_path,
        scope="tampered_formal_entry_scope",
    )
    output = tmp_path / "wrong-formal-scope.json"
    exit_code, observed = _run_checker_cli(root, output)
    assert exit_code == 2
    assert observed["checker_pass"] is False
    assert observed["evidence_valid"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"


def test_v6_2_checker_accepts_complete_evidence_with_identity_gate_negative(
    tmp_path: Path,
) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    configured_scope = (
        "run_v6_2_interface_schur_entry_before_preflight_and_artifact_setup"
    )
    for descriptor in manifest["rank_artifacts"]:
        rank_path = root / descriptor["path"]
        artifact = json.loads(rank_path.read_text())
        artifact["identity_gate"]["zero_map"] = False
        artifact["zero_error"] = 1.0e-4
        artifact["gate_pass"] = False
        artifact["classification"] = "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
        artifact["formal_sequence_start_scope"] = configured_scope
        descriptor["sha256"] = _write_json(rank_path, artifact)
        descriptor["formal_sequence_start_scope"] = configured_scope
    manifest["identity_gate"]["zero_map"] = False
    manifest["zero_error"] = 1.0e-4
    manifest["gate_pass"] = False
    manifest["classification"] = "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
    manifest["formal_sequence_start_scope"] = configured_scope
    manifest["exact_qualification_artifacts"] = [None] * checker.EXPECTED_MPI_SIZE
    manifest["exact_qualification_plan"] = _qualification_plan()
    manifest["pde_solve"] = "not_run_by_v6_2_identity_gate"
    manifest["exact_qualification_artifact_chain_sha256"] = hashlib.sha256(
        json.dumps(
            manifest["exact_qualification_artifacts"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-negative.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    observed = json.loads(output.read_text())
    assert observed["evidence_valid"] is True
    assert observed["checker_pass"] is True
    assert observed["gate_pass"] is False
    assert observed["classification"] == "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
    assert observed["evidence_checks"]["rank_integrity"] is True
    assert observed["evidence_checks"]["pde_execution_contract"] is True
    assert observed["executed_exact"] is False
    assert observed["gate_checks"]["zero_map_le_1e-13"] is False


def test_v6_2_checker_rejects_nonmapping_lifecycle_entry(tmp_path: Path) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["factor_lifecycle"]["after_by_rank"][0] = None
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-lifecycle.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    observed = json.loads(output.read_text())
    assert observed["checker_pass"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"
    assert observed["evidence_checks"]["factor_lifecycle_recorded"] is False


def test_v6_2_checker_rejects_rank_root_lifecycle_mismatch(tmp_path: Path) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    descriptor = next(
        item for item in manifest["rank_artifacts"] if item["rank"] == 2
    )
    rank_path = root / descriptor["path"]
    artifact = json.loads(rank_path.read_text())
    artifact["factor_lifecycle_after"]["after_cleanup"] = 1
    descriptor["factor_lifecycle_after"] = artifact["factor_lifecycle_after"]
    descriptor["sha256"] = _write_json(rank_path, artifact)
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-lifecycle-mismatch.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    observed = json.loads(output.read_text())
    assert observed["checker_pass"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"
    assert observed["evidence_checks"]["evidence_rank_factor_lifecycle_consistent"] is False


def test_v6_2_checker_rejects_manifest_rank_lifecycle_tamper(tmp_path: Path) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["factor_lifecycle"]["after_by_rank"][4]["after_cleanup"] = 1
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-manifest-lifecycle-tamper.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    observed = json.loads(output.read_text())
    assert observed["checker_pass"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"
    assert observed["evidence_checks"]["evidence_rank_factor_lifecycle_consistent"] is False


def test_v6_2_checker_rejects_output_inside_formal_root(tmp_path: Path) -> None:
    root, _manifest_path = _make_checker_fixture(tmp_path)
    output = root / "not-allowed.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    assert not output.exists()


def test_v6_2_checker_rejects_false_operator_audit_pass(tmp_path: Path) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    audit_path = root / manifest["operator_semantics_audit"]["path"]
    audit = json.loads(audit_path.read_text())
    audit["pass"] = False
    manifest["operator_semantics_audit"]["sha256"] = _write_json(audit_path, audit)
    _write_json(manifest_path, manifest)
    result = checker.check_v6_2_interface_schur(
        formal_root=root,
        formal_source_sha=FORMAL_SOURCE_SHA,
        checker_source_sha=CHECKER_SOURCE_SHA,
    )
    assert result["checker_pass"] is False
    assert result["classification"] == "IMPLEMENTATION_FAILURE"
    assert result["evidence_checks"]["operator_semantics_audit"] is False


def test_v6_2_checker_rejects_rehashed_woodbury_operator_audit(
    tmp_path: Path,
) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    audit_path = root / manifest["operator_semantics_audit"]["path"]
    audit = json.loads(audit_path.read_text())
    audit["current_authority"]["woodbury_inverse"] = True
    content = dict(audit)
    content.pop("record_sha256", None)
    audit["record_sha256"] = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    audit_file_sha = _write_json(audit_path, audit)
    manifest["operator_semantics_audit"]["sha256"] = audit_file_sha
    manifest["operator_semantics_audit"]["content_sha256"] = audit["record_sha256"]
    _write_json(manifest_path, manifest)
    result = checker.check_v6_2_interface_schur(
        formal_root=root,
        formal_source_sha=FORMAL_SOURCE_SHA,
        checker_source_sha=CHECKER_SOURCE_SHA,
    )
    assert result["checker_pass"] is False
    assert result["classification"] == "IMPLEMENTATION_FAILURE"
    assert result["evidence_checks"]["operator_semantics_audit"] is False


@pytest.mark.parametrize(
    ("field", "value", "expected_gate"),
    (
        ("vector_index", 0, "vector_indexes_0_1_2"),
        ("solve_count", "3", "solve_count_values_valid"),
    ),
)
def test_v6_2_vector_gate_rejects_duplicate_or_string_observation(
    tmp_path: Path,
    field: str,
    value: Any,
    expected_gate: str,
) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    for descriptor in manifest["rank_artifacts"]:
        rank_path = root / descriptor["path"]
        artifact = json.loads(rank_path.read_text())
        artifact["deterministic_vectors"][1][field] = value
        descriptor["sha256"] = _write_json(rank_path, artifact)
    manifest["deterministic_vectors"][1][field] = value
    _write_json(manifest_path, manifest)
    result = checker.check_v6_2_interface_schur(
        formal_root=root,
        formal_source_sha=FORMAL_SOURCE_SHA,
        checker_source_sha=CHECKER_SOURCE_SHA,
    )
    assert result["gate_pass"] is False
    assert result["gate_checks"][expected_gate] is False
