"""Focused V6-2 runner, resource-plan, and raw-checker contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
import pytest

import benchmarks.check_task040_v6_2_interface_schur as checker
import benchmarks.task040_level_a as level_a
import benchmarks.task040_level_a_watchdog as watchdog
import benchmarks.task040_v6_2_interface_schur as runner
from src.solvers.hybrid_bare_f_authority import (
    _source_definition_sha256,
    _source_semantic_descriptor,
)
from src.solvers.hybrid_exact_qualification import ExactQualificationContractError
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
        "bare_f_operator_hash": HEX,
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
        "bare_f_operator_hash": HEX,
        "canonical_to_current_roundtrip_relative": 0.0,
        "rank_local_shard_binding_sha256": HEX,
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


def _qualification_plan() -> dict[str, Any]:
    return runner.build_v6_2_exact_qualification_plan()


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
    """Exercise the real exact orchestration boundary without packet writes."""

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
        return {
            "status": (
                "completed_exact_numerical_gate_negative_continuation_allowed"
            ),
            "classification": "V6_EXACT_QUALIFICATION_GATE_FAIL",
            "source_records": [
                {
                    "label": label,
                    "full_residual_gate_pass": False,
                    "packetization_gate_pass": False,
                    "fgmres": {
                        "packetization_gate_error": None,
                        "checkpoint_history": [],
                    },
                }
                for label in labels[:2]
            ],
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
        "exact_qualification_plan": _qualification_plan(),
    }


def _make_checker_fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "formal"
    root.mkdir()
    audit_sha = _write_json(root / "operator_semantics_audit.json", {"pass": True})
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
        "classification": "ignored_prefilled_value",
        "source_sha": FORMAL_SOURCE_SHA,
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "identity_preflight": {"pass": True, "checks": {"source": True}},
        "resource_preflight": {"pass": True, "checks": {"resource": True}},
        "operator_semantics_audit": {
            "path": "operator_semantics_audit.json",
            "sha256": audit_sha,
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
        "exact_qualification_plan": _qualification_plan(),
        "research_only": True,
    }
    manifest_path = root / "v6_2_manifest.json"
    _write_json(manifest_path, manifest)
    return root, manifest_path


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
    assert plan["exact_qualification_plan"]["status"] == "designed_not_run"
    assert plan["exact_qualification_plan"]["checkpoints"] == [16, 32, 64, 128]
    assert (
        plan["exact_qualification_plan"]["frozen_owner_row_arrays"]
        == "not_loaded; complex PETSc owner-order values, never row ids"
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
    assert watched["watchdog"]["v6_2_identity_only"] is True
    assert "v6_2_preflight_only" not in watched["watchdog"]
    assert "--watchdog-hard-stop-bytes" in watched["worker_argv"]
    assert watched["worker_argv"].count("--v6-2-interface-schur") == 1


def test_v6_2_resource_preflight_uses_observed_environment_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import benchmarks.task034_wsl_resources as resources

    hard_stop = 45 * 2**30
    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "1")
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
    assert result["evidence_checks"]["evidence_rank_mapping_count_observed"] is True
    assert result["gate_checks"]["rank_deterministic_scalars"] is True
    assert result["gate_checks"]["rank_mapping_count_sum"] is True
    assert all(not item["path"].endswith(".npy") for item in result["read_files"])


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
    assert observed["evidence_checks"]["evidence_rank_zero_linearity_consistent"] is False


def test_v6_2_checker_accepts_complete_evidence_with_identity_gate_negative(
    tmp_path: Path,
) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    for descriptor in manifest["rank_artifacts"]:
        rank_path = root / descriptor["path"]
        artifact = json.loads(rank_path.read_text())
        artifact["zero_error"] = 1.0e-4
        descriptor["sha256"] = _write_json(rank_path, artifact)
    manifest["zero_error"] = 1.0e-4
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
