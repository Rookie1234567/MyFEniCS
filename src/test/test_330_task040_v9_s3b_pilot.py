"""Focused Task040 V9-E S3b pilot contracts."""

from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.solvers.floquet_background_hcurl_s3_formal import (
    compare_s3_candidate_source_to_baseline,
    validate_s3_j1_baseline_manifest,
)
from src.solvers.floquet_background_hcurl_s3_pilot import (
    S3B_CANDIDATE_R64_LIMIT,
    S3B_CANDIDATE_R256_LIMIT,
    S3B_CONDITIONAL_PASS,
    S3B_CONDITIONAL_UNSTABLE,
    S3B_EXPECTED_ACTIVE_ROWS,
    S3B_EXPECTED_MODE_COUNT,
    S3B_EXPECTED_ROWS_PER_MODE,
    S3B_EXTERNAL_SOURCE_COLUMN,
    S3B_EXTERNAL_SOURCE_LABEL,
    S3B_EXTERNAL_SOURCE_SEED,
    S3B_EXTERNAL_SOURCE_SIGN,
    S3B_FGMRES_INITIAL_MAX_IT,
    S3B_FGMRES_RESTART,
    S3B_INITIAL_NO_SIGNAL,
    S3B_INITIAL_POSITIVE,
    S3B_INITIAL_UNSTABLE,
    S3B_MAX_LOCAL_ROWS,
    S3B_NEXT_CONDITIONAL_256,
    S3B_NEXT_FIVE_SOURCE_BOTTOM,
    S3B_NEXT_FIXED_LOR,
    S3FixedRightFgmres,
    adjudicate_s3_b1_conditional_gate,
    adjudicate_s3_b1_initial_gate,
    build_s3_b1_background_config,
)

_SOURCE_SHA = "a" * 40
_INPUT_PATH = "/tmp/task040_s3b_input.dat"
_INPUT_SHA256 = "b" * 64
_PHYSICAL_MODEL_SHA256 = "c" * 64
_MANIFEST_SHA256 = "d" * 64
_HASHES = {
    "canonical_key_set_sha256": "1" * 64,
    "canonical_value_sha256": "2" * 64,
    "source_definition_sha256": "3" * 64,
    "source_canonical_identity_sha256": "4" * 64,
}


def _baseline_manifest() -> tuple[dict[str, object], dict[str, object]]:
    checkpoints = {
        str(iteration): {
            "true_residual_absolute": absolute,
            "true_residual_relative": relative,
            "finite": True,
        }
        for iteration, absolute, relative in (
            (8, 0.8, 0.08),
            (16, 0.4, 0.04),
            (32, 0.2, 0.02),
            (64, 0.1, 0.01),
        )
    }
    source = {
        "label": S3B_EXTERNAL_SOURCE_LABEL,
        "seed": S3B_EXTERNAL_SOURCE_SEED,
        "column": S3B_EXTERNAL_SOURCE_COLUMN,
        "resolved_column": S3B_EXTERNAL_SOURCE_COLUMN,
        "sign": S3B_EXTERNAL_SOURCE_SIGN,
        "canonical_key_count": S3B_EXPECTED_ACTIVE_ROWS,
        **_HASHES,
        "source_norm": 2.0,
        "source_finite": True,
        "source_nonzero": True,
        "sign_application_count": 1,
        "extra_sign_applied": False,
        "additional_sign_scale": 1.0,
        "sign_embedded_in": "current_DtnBlockAssembler_C_traction_values",
        "raw_global_row_remap": False,
        "numeric_allgather": False,
        "full_vector_replication": False,
    }
    provenance = {
        "source_sha": _SOURCE_SHA,
        "input_path": _INPUT_PATH,
        "input_sha256": _INPUT_SHA256,
        "physical_model_sha256": _PHYSICAL_MODEL_SHA256,
        "mpi_size": 8,
        "threads": 1,
        "side": "bottom",
        "operator_identity": "system.fine_action",
        "full_A_used": False,
        "qep_calls": 0,
    }
    manifest = {
        "schema": "task040.v9_e.s3b_j1_baseline_formal.v1",
        "method": "task040_v9_e_s3b_j1_baseline_formal",
        "route": "V9_E_S3B",
        "classification": "S3B_J1_BASELINE_MEASURED",
        "baseline_only": True,
        "provenance": provenance,
        "fixed_contract": {
            "active_rows": S3B_EXPECTED_ACTIVE_ROWS,
            "source_label": S3B_EXTERNAL_SOURCE_LABEL,
            "source_seed": S3B_EXTERNAL_SOURCE_SEED,
            "source_column": S3B_EXTERNAL_SOURCE_COLUMN,
            "source_sign": S3B_EXTERNAL_SOURCE_SIGN,
            "fgmres_restart": S3B_FGMRES_RESTART,
            "fgmres_initial_max_it": S3B_FGMRES_INITIAL_MAX_IT,
            "rss_hard_bytes": 45 * 2**30,
            "swap_limit_bytes": 0,
            "wall_cap_seconds": 10800,
        },
        "source": source,
        "source_norm": source["source_norm"],
        "source_canonical_key_set_sha256": source["canonical_key_set_sha256"],
        "source_canonical_value_sha256": source["canonical_value_sha256"],
        "fgmres": {
            "checkpoint_complete": True,
            "finite": True,
            "breakdown": False,
            "iterations": S3B_FGMRES_INITIAL_MAX_IT,
            "setup_count": 1,
            "setup_reused": False,
            "checkpoints": checkpoints,
        },
        "j1": {"r64": checkpoints["64"]["true_residual_relative"]},
        "structure": {
            "j1_layer_factor_count_ready": 6,
            "j1_layer_factor_count_after_cleanup": 0,
            "full_cross_section_factor_count_ready": 6,
            "full_cross_section_factor_count_after_cleanup": 0,
            "candidate_max_local_rows_gate_status": "not_applicable",
        },
    }
    binding = {
        "source_sha": _SOURCE_SHA,
        "input_path": _INPUT_PATH,
        "input_sha256": _INPUT_SHA256,
        "physical_model_sha256": _PHYSICAL_MODEL_SHA256,
    }
    return manifest, binding


def _validated_baseline() -> tuple[dict[str, object], dict[str, object]]:
    manifest, binding = _baseline_manifest()
    validated = validate_s3_j1_baseline_manifest(
        manifest,
        _MANIFEST_SHA256,
        _MANIFEST_SHA256,
        **binding,
    )
    return validated, binding


def test_s3b_b1_fixed_background_copy_and_two_level_gates() -> None:
    assert S3B_NEXT_FIXED_LOR == "V9_E_STRUCTURED_BACKGROUND_FIXED_LOR"
    cfg = target_stage4_config(degree=2, h_nm=100.0)
    background, audit = build_s3_b1_background_config(cfg)

    assert audit["material_model"] == "volume_average"
    assert audit["additional_absorbing_shift"] == 0.0
    assert audit["volume_average_weights"] == {"grating": 17.0 / 50.0, "air": 33.0 / 50.0}
    assert set(audit["changed_fields"]).issubset(
        {"case_name", "n_air", "n_grating"}
    )
    assert background.n_air == background.n_grating
    assert background.n_substrate == cfg.n_substrate
    assert S3B_EXPECTED_ACTIVE_ROWS == 8424
    assert S3B_EXPECTED_MODE_COUNT == 18
    assert S3B_EXPECTED_ROWS_PER_MODE == 468
    assert S3B_MAX_LOCAL_ROWS == 1024

    initial_positive = adjudicate_s3_b1_initial_gate(
        0.8,
        0.1,
        finite=True,
        breakdown=False,
        resource_ok=True,
    )
    assert initial_positive["classification"] == S3B_INITIAL_POSITIVE
    assert initial_positive["positive"] is True
    assert initial_positive["next_stage"] == S3B_NEXT_CONDITIONAL_256
    assert initial_positive["candidate_r64"] <= S3B_CANDIDATE_R64_LIMIT

    initial_no_signal = adjudicate_s3_b1_initial_gate(
        0.8,
        0.3,
        finite=True,
        breakdown=False,
        resource_ok=True,
    )
    assert initial_no_signal["classification"] == S3B_INITIAL_NO_SIGNAL
    assert initial_no_signal["next_stage"] == S3B_NEXT_FIXED_LOR

    initial_unstable = adjudicate_s3_b1_initial_gate(
        0.8,
        None,
        finite=False,
        breakdown=True,
        resource_ok=True,
    )
    assert initial_unstable["classification"] == S3B_INITIAL_UNSTABLE
    assert initial_unstable["next_stage"] == S3B_NEXT_FIXED_LOR

    conditional_pass = adjudicate_s3_b1_conditional_gate(
        0.5 * S3B_CANDIDATE_R256_LIMIT,
        finite=True,
        resource_ok=True,
    )
    assert conditional_pass["classification"] == S3B_CONDITIONAL_PASS
    assert conditional_pass["positive"] is True
    assert conditional_pass["next_stage"] == S3B_NEXT_FIVE_SOURCE_BOTTOM

    conditional_unstable = adjudicate_s3_b1_conditional_gate(
        None,
        finite=False,
        resource_ok=True,
    )
    assert conditional_unstable["classification"] == S3B_CONDITIONAL_UNSTABLE
    assert conditional_unstable["next_stage"] == S3B_NEXT_FIXED_LOR


def test_s3b_baseline_validator_and_candidate_comparator_real_schema() -> None:
    validated, binding = _validated_baseline()

    assert validated["validated"] is True
    assert validated["manifest_sha256"] == _MANIFEST_SHA256
    assert validated["source_norm"] == 2.0
    assert validated["source_definition_sha256"] == _HASHES["source_definition_sha256"]
    assert validated["source_canonical_identity_sha256"] == _HASHES[
        "source_canonical_identity_sha256"
    ]
    assert validated["provenance"] == _baseline_manifest()[0]["provenance"]

    candidate = deepcopy(validated["source"])
    comparison = compare_s3_candidate_source_to_baseline(candidate, validated)
    assert comparison["pass"] is True
    assert comparison["relative_norm_error"] == 0.0
    assert comparison["checks"]

    with pytest.raises(ValueError, match="1e-12"):
        compare_s3_candidate_source_to_baseline(
            candidate,
            validated,
            relative_tolerance=1.0e-10,
        )

    bad_alias_manifest = deepcopy(_baseline_manifest()[0])
    del bad_alias_manifest["source"]["source_definition_sha256"]
    bad_alias_manifest["source"]["canonical_definition_sha256"] = "3" * 64
    with pytest.raises(ValueError, match="source_definition_sha256"):
        validate_s3_j1_baseline_manifest(
            bad_alias_manifest,
            _MANIFEST_SHA256,
            _MANIFEST_SHA256,
            **binding,
        )


@pytest.mark.parametrize(
    ("field", "value", "check"),
    (
        ("column", S3B_EXTERNAL_SOURCE_COLUMN - 1, "column_matches_baseline_and_fixed"),
        ("extra_sign_applied", True, "extra_sign_applied_matches_baseline_and_fixed"),
        ("source_norm", 2.0 + 1.0e-9, "source_norm_relative_error_within_1e-12"),
    ),
)
def test_s3b_candidate_comparator_reports_representative_mismatches(
    field: str,
    value: object,
    check: str,
) -> None:
    validated, _ = _validated_baseline()
    candidate = deepcopy(validated["source"])
    candidate[field] = value

    comparison = compare_s3_candidate_source_to_baseline(candidate, validated)
    assert comparison["pass"] is False
    assert comparison["checks"][check] is False


class _BorrowedIdentityAction:
    def __init__(self) -> None:
        self.apply_count = 0
        self.destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("test borrowed action was destroyed")
        source.copy(target)
        self.apply_count += 1

    def destroy(self) -> None:
        self.destroyed = True


def _diagonal_operator(size: int, comm: MPI.Comm) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=1,
        comm=comm,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        # Distinct unit-circle eigenvalues prevent Krylov closure before 256 steps.
        phase = 2.0 * np.pi * (row + 0.5) / float(size)
        value = PETSc.ScalarType(np.exp(1j * phase))
        matrix.setValue(row, row, value)
    matrix.assemble()
    return matrix


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2 only")
def test_s3b_fixed_right_fgmres_tiny_diagonal_setup_reuse_and_lifecycle() -> None:
    comm = MPI.COMM_WORLD
    operator = None
    rhs = None
    solver = None
    action = _BorrowedIdentityAction()
    try:
        operator = _diagonal_operator(512, comm)
        rhs = operator.createVecRight()
        first, last = map(int, rhs.getOwnershipRange())
        rhs.array[:] = np.asarray(
            0.7 + 0.03j * (np.arange(first, last) + 1.0),
            dtype=PETSc.ScalarType,
        )
        rhs.assemble()

        solver = S3FixedRightFgmres(operator, action)
        ksp_identity = id(solver.ksp)
        solution_identity = id(solver.solution)
        diagnostics = solver.diagnostics
        assert diagnostics["setup_count"] == 1
        assert diagnostics["ksp_type"] == "fgmres"
        assert diagnostics["pc_side"] == "right"
        assert diagnostics["restart"] == S3B_FGMRES_RESTART
        assert diagnostics["max_it"] == S3B_FGMRES_INITIAL_MAX_IT
        assert diagnostics["zero_initial_guess"] is True
        assert diagnostics["operator_borrowed"] is True
        assert diagnostics["action_borrowed"] is True

        initial = solver.solve_initial(rhs, "tiny_diagonal")
        assert initial["iterations"] == S3B_FGMRES_INITIAL_MAX_IT
        assert initial["checkpoint_complete"] is True
        assert initial["finite"] is True
        assert initial["setup_count"] == 1
        assert initial["setup_reused"] is False

        explicit_gate = adjudicate_s3_b1_initial_gate(
            1.0,
            0.1,
            finite=True,
            breakdown=False,
            resource_ok=True,
        )
        assert explicit_gate["classification"] == S3B_INITIAL_POSITIVE
        conditional = solver.solve_conditional_to_256(
            rhs,
            "tiny_diagonal",
            explicit_gate,
        )
        assert conditional["total_iterations"] == 256
        assert conditional["checkpoint_complete"] is True
        assert conditional["finite"] is True
        assert conditional["setup_count"] == 1
        assert conditional["setup_reused"] is True
        assert conditional["continuation_strategy"] == (
            "same_ksp_pc_service_nonzero_initial_restart_continuation"
        )
        assert id(solver.ksp) == ksp_identity
        assert id(solver.solution) == solution_identity
        assert action.apply_count == solver.diagnostics["pc_apply_count"]
        assert action.apply_count > 0
        assert solver.diagnostics["initial_solve_count"] == 1
        assert solver.diagnostics["conditional_solve_count"] == 1
    finally:
        if solver is not None:
            solver.destroy()
            solver.destroy()
            assert solver.diagnostics["destroyed"] is True
            assert solver.diagnostics["pc_context_destroyed"] is True
            assert action.destroyed is False
        if operator is not None:
            assert operator.getSize() == (512, 512)
        if rhs is not None:
            rhs.destroy()
        if operator is not None:
            operator.destroy()
        action.destroy()
