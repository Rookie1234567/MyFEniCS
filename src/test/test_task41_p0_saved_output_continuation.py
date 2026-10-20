from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
import pytest

from src.runners.task41_p0_saved_output_continuation import (
    _link_saved_output,
    _require_service_envelope,
    _validate_original_attempt,
    _validate_original_solver_identity,
    _verify_linked_output_manifest,
    task41_diagnostic_diffraction_inventory,
    validate_saved_a6_packet,
    check_task41_p0_saved_output_continuation,
)
from src.runners.task41_p0_checker import (
    _task41_a2_diagnostic_inventory_from_data,
    _task41_mesh_actual_exact_candidate_profile,
    _task41_validate_v6_actual_qmetric_audit,
    _task41_validate_v6_prefix_qualification,
    _task41_v6_report_requires_prefix_qualification,
)
from src.runners import task41_p0_contract
from src.runners.task40_v10_campaign import FixedCampaignWindow
from src.runners.workflow_timebase import clock_sample
from scripts.task40_v20_service_workflow import (
    _run_task41_p0_saved_output_service,
    _task41_p0_checker_only_snapshot_identity,
    _run_task41_p0_service,
)


@pytest.mark.parametrize(
    ("report_name", "report", "expected_version"),
    [
        (
            "task41_p0_v5_mesh_actual_exact_attribution.json",
            {"schema": "task41.p0.v5.mesh_actual_exact_attribution_receipt.v1"},
            "v5",
        ),
        (
            "task41_p0_v6_actual_qmetric_candidate.json",
            {
                "schema": "task41.p0.v6.actual_qmetric_candidate_receipt.v1",
                "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
                "identity_audit": {
                    "candidate_evaluator_identity": (
                        "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
                    )
                },
            },
            "v6",
        ),
    ],
)
def test_mesh_actual_exact_candidate_checker_selects_frozen_profile(
    tmp_path: Path, report_name: str, report: dict[str, object], expected_version: str
) -> None:
    profile = _task41_mesh_actual_exact_candidate_profile(tmp_path / report_name, report)
    assert profile["version"] == expected_version
    assert profile["denominators_source"] == f"review_report_{expected_version}.md"
    assert profile["check_schema"].startswith(f"task41.p0.{expected_version}.")


def test_mesh_actual_exact_candidate_checker_rejects_unbound_v6_identity(tmp_path: Path) -> None:
    report = {
        "schema": "task41.p0.v6.actual_qmetric_candidate_receipt.v1",
        "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
        "identity_audit": {"candidate_evaluator_identity": "unexpected"},
    }
    with pytest.raises(ValueError, match="V6 actual-qmetric candidate identity"):
        _task41_mesh_actual_exact_candidate_profile(
            tmp_path / "task41_p0_v6_actual_qmetric_candidate.json", report
        )


def _v6_candidate_audit_fixture(tmp_path: Path):
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        CACHE_IDENTITY_SCHEMA,
        DIMENSION,
        EXPECTED_C_CACHE_SHA256,
        EXPECTED_C_SOURCE_BYTES,
        EXPECTED_C_SOURCE_SHA256,
        EXPECTED_GEOMETRY_TABLE_NAMES,
        EXPECTED_STATIC_TABLE_EXTENTS,
        EXPECTED_UFCX_MODULE_SHA256,
        EXPECTED_UFCX_SIGNATURE,
        FEATURE_NAMES,
        GEOMETRY_ORACLE_TRACE_SCHEMA,
        HELPER_COMPILER_FLAGS,
        IDENTITY,
        INTEGRAL_BODY_BY_TAG,
        POINT_BLOCK_SIZE,
        POINT_COUNT,
        QUALIFICATION_STATUS,
        REQUIRED_GEOMETRY_TRACE_FIELDS,
        V6_PREFIX_QUALIFICATION_SCHEMA,
        V6_PREFIX_SAMPLE_CELL_INDICES,
        _cache_identity_digest,
    )

    source_path = (tmp_path / "libffcx.c").resolve()
    evaluator_source_path = (tmp_path / "task41_actual_qmetric_blocked_gram.py").resolve()
    evaluator_source_path.write_text("# frozen evaluator fixture\n", encoding="utf-8")
    evaluator_source_sha256 = hashlib.sha256(evaluator_source_path.read_bytes()).hexdigest()
    body_map = {str(tag): digest for tag, digest in INTEGRAL_BODY_BY_TAG.items()}
    cache_payload = {
        "schema": CACHE_IDENTITY_SCHEMA,
        "implementation": IDENTITY,
        "evaluator_source_sha256": evaluator_source_sha256,
        "ffcx_c_source_sha256": EXPECTED_C_SOURCE_SHA256,
        "ffcx_compile_metadata_sha256": EXPECTED_C_CACHE_SHA256,
        "ffcx_module_sha256": EXPECTED_UFCX_MODULE_SHA256,
        "ufcx_signature": EXPECTED_UFCX_SIGNATURE,
        "reference_table_source_sha256": EXPECTED_C_SOURCE_SHA256,
        "integral_body_by_tag": body_map,
        "table_extent_contract": {
            "FE0": [1, 1, POINT_COUNT, DIMENSION],
            "FE2": [1, 1, POINT_COUNT, 8],
            "weights": [POINT_COUNT],
        },
        "compiler_flags": list(HELPER_COMPILER_FLAGS),
        "geometry_oracle_trace_schema": GEOMETRY_ORACLE_TRACE_SCHEMA,
    }
    cache_identity_sha256 = _cache_identity_digest(cache_payload)
    cache_identity = f"{IDENTITY}:{cache_identity_sha256}"
    reference_table_bytes = len(FEATURE_NAMES) * POINT_COUNT * DIMENSION * 8 + POINT_COUNT * 8
    shared_table_bytes_upper = reference_table_bytes + len(
        set(INTEGRAL_BODY_BY_TAG.values())
    ) * sum(
        int(np.prod(EXPECTED_STATIC_TABLE_EXTENTS[name])) * 8
        for name in EXPECTED_GEOMETRY_TABLE_NAMES
    )
    helper = {
        "source_path": str(source_path),
        "source_sha256": EXPECTED_C_SOURCE_SHA256,
        "source_bytes": EXPECTED_C_SOURCE_BYTES,
        "compile_metadata_path": str(Path(str(source_path) + ".cached")),
        "compile_metadata_sha256": EXPECTED_C_CACHE_SHA256,
        "helper_source_sha256": "a" * 64,
        "helper_source_bytes": 2048,
        "helper_library_sha256": "b" * 64,
        "helper_library_bytes": 4096,
        "helper_scratch_retained_bytes": 6144,
        "reference_table_names": list(FEATURE_NAMES),
        "reference_table_bytes": reference_table_bytes,
        "shared_table_bytes_upper": shared_table_bytes_upper,
        "reference_table_hashes": ["c" * 64] * len(FEATURE_NAMES),
        "reference_weight_sha256": "e" * 64,
        "reference_table_zero_counts": [0] * len(FEATURE_NAMES),
        "reference_table_zero_pattern_hashes": ["d" * 64] * len(FEATURE_NAMES),
        "static_table_declared_extents": {
            name: list(shape) for name, shape in EXPECTED_STATIC_TABLE_EXTENTS.items()
        },
        "geometry_trace_fields": sorted(REQUIRED_GEOMETRY_TRACE_FIELDS),
        "feature_pair_map": [[left, right] for left in range(12) for right in range(12)],
        "quadrature_point_count": POINT_COUNT,
        "geometry_helper_block_size": POINT_BLOCK_SIZE,
        "geometry_expression_source": "frozen_FFCx_Q907_Jacobian_and_fw_graph",
        "geometry_shortcut_used": False,
        "geometry_trace_source": "same_frozen_FFCx_scalar_graph_as_actual_qmetric_block",
        "original_kernel_oracle_generator": (
            "_FrozenFFCxGeometryHelper.original_kernel_oracle_source"
        ),
        "original_kernel_oracle_execution_status": "NOT_RUN_NO_WINDOW_APPROVAL",
        "original_kernel_oracle_execution_count": 0,
        "original_kernel_oracle_artifact_bytes": 0,
        "original_kernel_oracle_compile_audits": {},
        "compiler_flags": list(HELPER_COMPILER_FLAGS),
    }
    audit = {
        "candidate_evaluator_cache_identity": cache_identity,
        "candidate_evaluator_audit": {
            "implementation": IDENTITY,
            "qualification_status": QUALIFICATION_STATUS,
            "expected_ufcx_signature": EXPECTED_UFCX_SIGNATURE,
            "full_form_signature": EXPECTED_UFCX_SIGNATURE,
            "integral_body_by_tag": body_map,
            "ffcx_module_sha256": EXPECTED_UFCX_MODULE_SHA256,
            "ffcx_default_kernel_absent": True,
            "point_block_size": POINT_BLOCK_SIZE,
            "workspace_bytes_upper": 1024**3,
            "prepare_workspace_bytes_upper": 1024**3,
            "key_workspace_bytes_upper": 128 * 1024**2,
            "class_timing_metadata_bytes_upper": 16 * 1024**2,
            "class_timing_metadata_bytes": 512,
            "helper_scratch_bytes_upper": 128 * 1024**2,
            "original_kernel_oracle_scratch_bytes_upper": 512 * 1024**2,
            "original_kernel_oracle_workspace_bytes_upper": 1024**3,
            "original_kernel_oracle_source_bytes_upper": 2 * EXPECTED_C_SOURCE_BYTES,
            "geometry_oracle_comparison_records": [],
            "original_kernel_oracle_records": [],
            "prefix_qualification": {
                "schema": V6_PREFIX_QUALIFICATION_SCHEMA,
                "status": "P0_NOT_RUN_NO_WINDOW_APPROVAL",
                "required_sample_cell_indices": list(V6_PREFIX_SAMPLE_CELL_INDICES),
                "sample_count": 0,
                "required_sample_count": len(V6_PREFIX_SAMPLE_CELL_INDICES),
                "geometry_witness_count": 0,
                "full_admission_eligible": False,
                "records": [],
            },
            "cache_identity": cache_identity,
            "cache_identity_sha256": cache_identity_sha256,
            "cache_identity_payload": cache_payload,
            "evaluator_source_path": str(evaluator_source_path),
            "evaluator_source_sha256": evaluator_source_sha256,
            "class_count": 0,
            "class_seconds_summary": {"count": 0, "total": 0.0, "max": 0.0},
            "phase_seconds_by_stage": {
                "geometry": 0.0,
                "pack": 0.0,
                "gram": 0.0,
                "scatter": 0.0,
                "release": 0.0,
            },
            "mass_coefficient_conjugated": False,
            "hermitian_assumption": False,
            "raw_tensor_built_before_original_schur": True,
            "geometry_helper": helper,
        }
    }
    return audit, helper, evaluator_source_path


def test_v6_candidate_checker_rechecks_the_frozen_evaluator_audit(tmp_path: Path) -> None:
    audit, helper, _ = _v6_candidate_audit_fixture(tmp_path)
    _task41_validate_v6_actual_qmetric_audit(audit)
    helper["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="frozen source profile"):
        _task41_validate_v6_actual_qmetric_audit(audit)


@pytest.mark.parametrize("misbound_field", ["full_form_signature", "integral_body_by_tag"])
def test_v6_candidate_checker_rejects_misbound_profile_fields(
    tmp_path: Path, misbound_field: str
) -> None:
    audit, helper, _ = _v6_candidate_audit_fixture(tmp_path)
    candidate = audit["candidate_evaluator_audit"]
    if misbound_field == "full_form_signature":
        candidate["ufcx_form_signature"] = candidate["expected_ufcx_signature"]
        candidate["full_form_signature"] = "0" * len(
            candidate["expected_ufcx_signature"]
        )
    else:
        helper["integral_body_by_tag"] = dict(candidate["integral_body_by_tag"])
        candidate["integral_body_by_tag"]["1"] = "0" * 40
    with pytest.raises(ValueError, match="frozen source profile"):
        _task41_validate_v6_actual_qmetric_audit(audit)


def test_v6_no_window_prefix_cannot_admit_a_completed_candidate(tmp_path: Path) -> None:
    audit, _, _ = _v6_candidate_audit_fixture(tmp_path)
    assert not _task41_v6_report_requires_prefix_qualification(
        {"status": "P0_NOT_RUN_NO_WINDOW_APPROVAL", "candidate_numeric_status": "NOT_RUN"}
    )
    completed_negative = {
        "status": "ACTUAL_COORDINATES_INSUFFICIENT",
        "candidate_numeric_status": "ACTUAL_COORDINATES_INSUFFICIENT",
    }
    assert _task41_v6_report_requires_prefix_qualification(completed_negative)
    with pytest.raises(ValueError, match="P0 no-window record"):
        _task41_validate_v6_actual_qmetric_audit(
            audit, require_prefix_qualified=True
        )


def test_v6_forged_qualified_prefix_without_eight_records_is_rejected(
    tmp_path: Path,
) -> None:
    audit, _, _ = _v6_candidate_audit_fixture(tmp_path)
    prefix = audit["candidate_evaluator_audit"]["prefix_qualification"]
    prefix.update(
        {
            "status": "PREFIX_QUALIFIED",
            "geometry_witness_count": 1,
            "full_admission_eligible": True,
        }
    )
    with pytest.raises(ValueError, match="qualified prefix is incomplete"):
        _task41_validate_v6_actual_qmetric_audit(audit)


def test_v6_checker_distinguishes_a_qualified_prefix_inventory_from_p0_not_run() -> None:
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        V6_PREFIX_QUALIFICATION_SCHEMA,
        V6_PREFIX_SAMPLE_CELL_INDICES,
    )
    from src.runners.task41_p0_checker import TASK41_P0_V5_FROZEN_DENOMINATORS
    from src.runners.task41_p0_v4_volume_only_audit import TASK41_P0_V5_REFERENCE_CELLS

    records = []
    for cell_index in V6_PREFIX_SAMPLE_CELL_INDICES:
        saved = cell_index in TASK41_P0_V5_REFERENCE_CELLS
        witness = (
            {"status": "NOT_REQUIRED_V4_SAVED_ACTUAL_BLOCKS"}
            if saved
            else {"status": "BITWISE_EQUAL", "q_begin": 0, "q_end": 512}
        )
        record = {
            "cell_index": cell_index,
            "source": (
                "V4_SAVED_ACTUAL_BLOCKS"
                if saved
                else "ORIGINAL_FFCX_KERNEL_ORACLE"
            ),
            "coordinates_bitwise_identity_passed": True,
            "geometry_witness": witness,
            "status": "PASS",
            "admission_eligible": True,
            "comparisons": {
                "raw_tensor": {"status": "PASS", "relative_limit": 1.0e-11},
                "oriented_tensor": {"status": "PASS", "relative_limit": 1.0e-11},
                "K_G_J_L": {
                    name: {"status": "PASS", "relative_limit": 1.0e-11}
                    for name in ("K", "G", "J", "L")
                },
                "R_T_S": {
                    name: {"status": "PASS", "relative_limit": 1.0e-11}
                    for name in ("R", "T", "S")
                },
                "strict_lu": {"passed": True, "relative_limit": 1.0e-11},
                "reference_condensation_defects_relative": {
                    "KR_plus_G": 2.0e-8, "TK_plus_J": 1.5e-8
                },
                "candidate_condensation_defects_relative": {
                    "KR_plus_G": 3.0e-8, "TK_plus_J": 2.5e-8
                },
                "condensation_defects_classification": "diagnostic_only",
            },
        }
        if saved:
            record["reference_report_sha256"] = "a" * 64
            record["local_action_comparisons"] = [
                {
                    "column": column,
                    "state": state,
                    "selected_active_row": 5_458_716,
                    "frozen_denominator": TASK41_P0_V5_FROZEN_DENOMINATORS[column],
                    "selected_row_scale_check": "diagnostic_only",
                    "selected_row_difference_over_frozen_denominator": 0.0,
                    "full_local_action": {"absolute_frobenius": 2.0},
                    "full_local_action_scale_check": "diagnostic_only",
                    "full_local_action_difference_over_frozen_denominator": (
                        2.0 / TASK41_P0_V5_FROZEN_DENOMINATORS[column]
                    ),
                }
                for column in (0, 1)
                for state in ("known", "j0", "j3")
            ]
        records.append(record)
    qualification = {
        "schema": V6_PREFIX_QUALIFICATION_SCHEMA,
        "status": "PREFIX_QUALIFIED",
        "required_sample_cell_indices": list(V6_PREFIX_SAMPLE_CELL_INDICES),
        "sample_count": len(records),
        "required_sample_count": len(V6_PREFIX_SAMPLE_CELL_INDICES),
        "geometry_witness_count": 6,
        "full_admission_eligible": True,
        "records": records,
    }
    assert (
        _task41_validate_v6_prefix_qualification(
            qualification, require_qualified=False
        )
        == "PREFIX_QUALIFIED_INVENTORY"
    )
    assert (
        _task41_validate_v6_prefix_qualification(
            qualification, require_qualified=True
        )
        == "PREFIX_QUALIFIED"
    )
    assert (
        records[0]["comparisons"]["candidate_condensation_defects_relative"]["KR_plus_G"]
        > 1.0e-11
    )
    records[0]["comparisons"]["candidate_condensation_defects_relative"]["KR_plus_G"] = -1.0
    with pytest.raises(ValueError, match="invalid diagnostic condensation defects"):
        _task41_validate_v6_prefix_qualification(
            qualification, require_qualified=False
        )
    records[0]["comparisons"]["candidate_condensation_defects_relative"]["KR_plus_G"] = 3.0e-8
    records[0]["comparisons"]["condensation_defects_classification"] = "hard_gate"
    with pytest.raises(ValueError, match="mislabeled diagnostic_only"):
        _task41_validate_v6_prefix_qualification(
            qualification, require_qualified=False
        )
    records[0]["comparisons"]["condensation_defects_classification"] = "diagnostic_only"
    records[0]["local_action_comparisons"][0][
        "full_local_action_difference_over_frozen_denominator"
    ] = 100.0
    with pytest.raises(ValueError, match="saved-cell action evidence"):
        _task41_validate_v6_prefix_qualification(
            qualification, require_qualified=False
        )


def test_v6_candidate_checker_binds_cache_identity_to_evaluator_source(tmp_path: Path) -> None:
    audit, _, evaluator_source_path = _v6_candidate_audit_fixture(tmp_path)
    evaluator_source_path.write_text("# changed evaluator fixture\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen source profile"):
        _task41_validate_v6_actual_qmetric_audit(audit)


@pytest.mark.parametrize("field", ["static_table_declared_extents", "reference_table_zero_pattern_hashes"])
def test_v6_candidate_checker_rejects_invalid_reference_table_structure(
    tmp_path: Path, field: str
) -> None:
    audit, helper, _ = _v6_candidate_audit_fixture(tmp_path)
    if field == "static_table_declared_extents":
        helper[field]["FE0_C0_Q907"][-1] -= 1
    else:
        helper[field].pop()
    with pytest.raises(ValueError, match="frozen source profile"):
        _task41_validate_v6_actual_qmetric_audit(audit)


def _write_a6_packet(path: Path, *, stored_native_relative: float | None = None) -> None:
    rhs = np.asarray([2.0 + 0j, 1.0 + 0j, -3.0 + 0j], dtype=np.complex128)
    solution = np.asarray([1.0 + 2j, -0.5j, 0.25 + 0j], dtype=np.complex128)
    target_residual = np.asarray([1.0e-8, -2.0e-8, 0.5e-8], dtype=np.complex128)
    native_residual = np.asarray([-1.5e-8, 0.5e-8, 1.0e-8], dtype=np.complex128)
    values = {
        "full_physical_rhs_storage": rhs,
        "full_solution_storage": solution,
        "target_backend_applied_storage": rhs - target_residual,
        "target_backend_residual_storage": target_residual,
        "native_witness_applied_storage": rhs - native_residual,
        "native_witness_residual_storage": native_residual,
    }
    npz_path = path.with_suffix(".npz")
    names = {name: f"array_{index}" for index, name in enumerate(values)}
    np.savez(npz_path, **{names[name]: value for name, value in values.items()})
    rhs_norm = float(np.linalg.norm(rhs))
    target_relative = float(np.linalg.norm(target_residual) / rhs_norm)
    native_relative = float(np.linalg.norm(native_residual) / rhs_norm)
    record = {
        "schema": "task40extra.review_v10_b0_candidate_independent_A6_residual.v1",
        "limit": 1.0e-6,
        "identity": {
            "source_sha": "a" * 40,
            "input_sha256": "b" * 64,
            "physical_model_sha256": "c" * 64,
        },
        "arrays": {"path": str(npz_path), "sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest()},
        "relative_residual": target_relative,
        "native_witness_relative_residual": (
            native_relative if stored_native_relative is None else stored_native_relative
        ),
    }
    for name, value in values.items():
        record[name] = {
            "array_key": names[name],
            "dtype": str(value.dtype),
            "shape": list(value.shape),
        }
    path.write_text(json.dumps(record), encoding="utf-8")


def test_saved_a6_packet_recomputes_target_and_native_residuals(tmp_path: Path) -> None:
    packet_path = tmp_path / "pre_release.json"
    _write_a6_packet(packet_path)

    solution, facts = validate_saved_a6_packet(
        packet_path,
        run_root=tmp_path,
        expected_source_sha="a" * 40,
        expected_input_sha256="b" * 64,
        expected_physical_model_sha256="c" * 64,
    )

    assert solution.shape == (3,)
    assert facts["packet_json_sha256"] == hashlib.sha256(packet_path.read_bytes()).hexdigest()
    assert all(row["passed"] for row in facts["residual_checks"])


def test_saved_a6_packet_rejects_changed_stored_native_residual(tmp_path: Path) -> None:
    packet_path = tmp_path / "post_release.json"
    _write_a6_packet(packet_path, stored_native_relative=0.0)

    with pytest.raises(ValueError, match="does not independently pass"):
        validate_saved_a6_packet(
            packet_path,
            run_root=tmp_path,
            expected_source_sha="a" * 40,
            expected_input_sha256="b" * 64,
            expected_physical_model_sha256="c" * 64,
        )


def test_continuation_hardlinks_preserve_saved_output_bytes(tmp_path: Path) -> None:
    source = tmp_path / "original" / "numerical_output"
    source.mkdir(parents=True)
    (source / "field.bin").write_bytes(b"saved field")
    (source / "orders.json").write_text('{"orders": []}\n', encoding="utf-8")
    nested_source = source / "E_3d_numerical.bp" / "part.0"
    nested_source.mkdir(parents=True)
    (nested_source / "mesh.bin").write_bytes(b"saved mesh")
    (source / "empty.bp").mkdir()
    destination = tmp_path / "continuation" / "numerical_output"

    manifest = _link_saved_output(source, destination)

    assert [row["name"] for row in manifest] == [
        "E_3d_numerical.bp/part.0/mesh.bin",
        "field.bin",
        "orders.json",
    ]
    assert all(row["same_inode"] for row in manifest)
    assert (destination / "field.bin").read_bytes() == (source / "field.bin").read_bytes()
    assert (destination / "E_3d_numerical.bp" / "part.0" / "mesh.bin").stat().st_ino == (
        nested_source / "mesh.bin"
    ).stat().st_ino
    assert (destination / "empty.bp").is_dir()
    verification = _verify_linked_output_manifest(
        {"numerical_output_path": str(source)},
        {
            "numerical_output_directory": str(destination),
            "numerical_output_manifest": manifest,
        },
    )
    assert verification["passed"] is True


def test_saved_output_hardlink_rejects_nested_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "original" / "numerical_output"
    nested = source / "E_3d_numerical.bp"
    nested.mkdir(parents=True)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside the producer output")
    (nested / "linked.bin").symlink_to(outside)

    with pytest.raises(ValueError, match="contains a symlink"):
        _link_saved_output(source, tmp_path / "continuation" / "numerical_output")


def test_saved_output_checker_wrapper_passes_keyword_only_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.runners.task41_p0_saved_output_continuation as continuation

    snapshot = tmp_path / "task41_p0_saved_output_checker_input.json"
    snapshot.write_text("{}\n", encoding="utf-8")
    expected_result = tmp_path / "retry" / "task41_p0_saved_output_checker_result.json"
    calls: list[dict[str, object]] = []

    def keyword_only_checker(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"checker_passed": True}

    monkeypatch.setattr(continuation, "_check_comparison_outputs", keyword_only_checker)

    result = check_task41_p0_saved_output_continuation(
        snapshot,
        contract_path=tmp_path / "contract.json",
        contract_sha256="f" * 64,
        repo_root=tmp_path,
        result_path=expected_result,
    )

    assert result == {"checker_passed": True}
    assert len(calls) == 1
    assert calls[0]["receipt_path"] == snapshot.resolve()
    assert calls[0]["result_path"] == expected_result


def test_checker_only_service_reuses_authorized_snapshot_and_skips_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.task40_v20_service_workflow as service_workflow
    import src.runners.task41_p0_contract as contract_module
    import src.runners.task40_v10_campaign as campaign_module
    import benchmarks.subreaper_watchdog as watchdog_module
    import benchmarks.task034_wsl_resources as resource_module

    repo_root = tmp_path
    results_root = repo_root / "results" / "model"
    producer_run = results_root / "producer_run"
    snapshot_directory = results_root / "saved_output_attempt7_consumer_retry3"
    producer_run.mkdir(parents=True)
    snapshot_directory.mkdir(parents=True)
    input_path = repo_root / "task41.dat"
    input_path.write_bytes(b"fixed Task41 fixture input\n")
    contract_path = repo_root / "contract.json"
    contract_path.write_text("{}\n", encoding="utf-8")
    runtime_prefix = repo_root / "runtime"
    fake_python = runtime_prefix / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text("checker-only service fixture interpreter\n", encoding="utf-8")
    contract_sha = "f" * 64
    window_sha = "e" * 64
    abi_sha = "d" * 64
    producer_sha = "a" * 40
    consumer_sha = "b" * 40
    checker_sha = "c" * 40
    branch = "task41extra_phi90_p50x50_g17x20"
    snapshot_path = snapshot_directory / "task41_p0_saved_output_checker_input.json"
    snapshot_payload = {
        "schema": "task41.p0.saved_output_continuation.v1",
        "status": "OUTPUTS_READY",
        "producer": {
            "source_sha": producer_sha,
            "run_directory": str(producer_run),
        },
        "consumer": {
            "source_sha": consumer_sha,
            "run_directory": str(snapshot_directory),
        },
    }
    snapshot_path.write_text(json.dumps(snapshot_payload), encoding="utf-8")
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot_sha = hashlib.sha256(snapshot_bytes).hexdigest()
    old_receipt_path = snapshot_directory / "task41_p0_saved_output_continuation_receipt.json"
    old_receipt_path.write_bytes(b'{"status":"FAILED_RAW_EVIDENCE_RETAINED"}\n')
    old_receipt_bytes = old_receipt_path.read_bytes()
    output_root = results_root / "saved_output_attempt7_checker_retry1"
    window = FixedCampaignWindow(
        path=repo_root / "execution_window.json",
        sha256=window_sha,
        payload={"accounting_path": str(repo_root / "window_accounting.jsonl")},
        anchor={},
        t0_utc_ns=100,
        deadline_utc_ns=1_800_000_000_100,
        total_seconds=1800.0,
        bootstrap_seconds=0.0,
        closeout_seconds=600.0,
    )
    contract = {
        "task_id": "task41-p0",
        "branch": branch,
        "source": {"sha": producer_sha},
        "window": {"path": str(window.path), "sha256": window_sha},
        "case": {
            "model_id": "model",
            "run_id": "task41extra_g13_p6_phi90_iterative_a2",
            "input_path": str(input_path),
            "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        },
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {
            "runtime_prefix": str(runtime_prefix),
            "abi_receipt_path": str(repo_root / "abi.json"),
            "jit_cache": str(repo_root / "jit"),
            "abi_receipt_sha256": abi_sha,
        },
    }
    environment = {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
        "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": abi_sha,
    }
    monkeypatch.setenv("TASK41_P0_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK41_P0_CONTRACT_PATH", str(contract_path.resolve()))
    monkeypatch.setenv("TASK41_P0_CONTRACT_SHA256", contract_sha)
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_PATH", str(window.path))
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_SHA256", window_sha)
    monkeypatch.setenv("TASK41_P0_EXPECTED_SOURCE_SHA", producer_sha)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_supervise(
        command: list[str], _directory: Path, **kwargs: object
    ) -> dict[str, object]:
        calls.append((command, kwargs))
        assert kwargs["campaign_phase"] == "closeout"
        assert kwargs["campaign_window_path"] == window.path
        assert kwargs["campaign_window_sha256"] == window_sha
        assert command[command.index("--saved-output-continuation-input") + 1] == str(snapshot_path)
        assert command[command.index("--output") + 1] == str(
            output_root / "task41_p0_saved_output_checker_result.json"
        )
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "checker_passed": True,
                    "producer_source_sha": producer_sha,
                    "consumer_source_sha": consumer_sha,
                    "checker_source_sha": checker_sha,
                    "checker_input_snapshot_sha256": snapshot_sha,
                }
            ),
            encoding="utf-8",
        )
        authorization = kwargs["campaign_phase_authorization"]
        assert authorization["source_sha"] == checker_sha
        assert authorization["input_paths"] == [str(snapshot_path)]
        assert authorization["input_sha256s"] == [snapshot_sha]
        watchdog_module._validate_campaign_closeout_authorization(
            command=command,
            campaign=window,
            authorization=authorization,
            worker_environment=kwargs["worker_environment"],
        )
        return {"classification": "COMPLETED", "leader_exit_code": 0}

    monkeypatch.setattr(
        contract_module,
        "require_task41_p0_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setattr(
        contract_module,
        "load_task41_p0_fixed_window",
        lambda *_args, **_kwargs: window,
    )
    monkeypatch.setattr(
        contract_module, "task41_case_id_for_run_id", lambda _run_id: "A2"
    )
    monkeypatch.setattr(
        contract_module,
        "__file__",
        str(repo_root / "src" / "runners" / "task41_p0_contract.py"),
    )
    monkeypatch.setattr(
        contract_module,
        "sha256_file",
        lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
    )

    class FakeCampaignAccount:
        def __init__(self, _window: FixedCampaignWindow) -> None:
            pass

        def record_sample(self, *, label: str, phase: str) -> dict[str, str]:
            return {"label": label, "phase": phase, "window_sha256": window_sha}

    monkeypatch.setattr(campaign_module, "CampaignAccount", FakeCampaignAccount)
    monkeypatch.setattr(
        resource_module,
        "cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": True,
            "readable": True,
            "memory_limit_bytes": 1 << 30,
            "swap_current_bytes": 0,
            "memory_current_bytes": 1 << 20,
        },
    )
    monkeypatch.setattr(watchdog_module, "supervise", fake_supervise)
    monkeypatch.setattr(service_workflow, "_activation_environment", lambda *_a, **_k: (environment.copy(), ["activate"], 0, ""))
    monkeypatch.setattr(
        service_workflow,
        "_abi_preflight",
        lambda *_args, **_kwargs: (
            ["python", "preflight"],
            0,
            json.dumps({"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1}),
            "",
        ),
    )
    monkeypatch.setattr(
        service_workflow.subprocess,
        "check_output",
        lambda command, **_kwargs: (
            branch + "\n" if command[-1] == "--show-current" else checker_sha + "\n"
        ),
    )
    def fake_git_run(command: list[str], **_kwargs: object) -> object:
        if command[1] == "merge-base":
            return type("GitResult", (), {"returncode": 0, "stdout": ""})()
        if command[1] == "rev-parse":
            return type("GitResult", (), {"returncode": 0, "stdout": checker_sha + "\n"})()
        if command[1] == "branch":
            return type("GitResult", (), {"returncode": 0, "stdout": branch + "\n"})()
        if command[1] == "status":
            return type("GitResult", (), {"returncode": 0, "stdout": ""})()
        raise AssertionError(f"unexpected Git command: {command}")

    monkeypatch.setattr(service_workflow.subprocess, "run", fake_git_run)
    monkeypatch.setattr(sys, "executable", str(fake_python.resolve()))
    monkeypatch.chdir(repo_root)

    with pytest.raises(ValueError, match="snapshot path/hash"):
        _task41_p0_checker_only_snapshot_identity(
            snapshot_path=snapshot_path,
            expected_sha256="0" * 64,
            contract=contract,
            checker_source_sha=checker_sha,
            repo_root=repo_root,
            sha256_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    result = _run_task41_p0_service(
        unit="task41-checker-only-test",
        runtime_prefix=runtime_prefix,
        abi_receipt=repo_root / "abi.json",
        jit_cache=repo_root / "jit",
        case_args=[
            "--task41-p0-saved-output-checker-only",
            "--checker-input",
            str(snapshot_path),
            "--checker-input-sha256",
            snapshot_sha,
            "--output-dir",
            str(output_root),
        ],
        contract_path=contract_path,
        repo_root=repo_root,
    )

    assert result == 0
    assert len(calls) == 1
    assert calls[0][1]["campaign_phase"] == "closeout"
    service_directory = output_root.with_name(output_root.name + ".service")
    service_receipt = json.loads(
        (service_directory / "task41_p0_service_receipt.json").read_text(encoding="utf-8")
    )
    assert service_receipt["status"] == "completed"
    assert service_receipt["mode"] == "checker_only"
    assert service_receipt["continuation_status"] == "outputs_ready_reused"
    assert "continuation_watchdog" not in service_receipt
    assert service_receipt["producer_source_sha"] == producer_sha
    assert service_receipt["consumer_source_sha"] == consumer_sha
    assert service_receipt["checker_source_sha"] == checker_sha
    assert service_receipt["required_checker_source_sha"] == checker_sha
    assert service_receipt["checker_input_snapshot_sha256"] == snapshot_sha
    assert not (snapshot_directory / "task41_p0_saved_output_checker_result.json").exists()
    assert snapshot_path.read_bytes() == snapshot_bytes
    assert old_receipt_path.read_bytes() == old_receipt_bytes


def test_service_binding_keeps_producer_contract_and_consumer_activation_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_sha = "f" * 64
    window_sha = "e" * 64
    abi_sha = "d" * 64
    producer_sha = "a" * 40
    consumer_sha = "b" * 40
    branch = "task41extra_phi90_p50x50_g17x20"
    contract_path = (tmp_path / "producer_contract.json").resolve()
    window_path = (tmp_path / "fixed_window.json").resolve()
    contract = {
        "branch": branch,
        "source": {"sha": producer_sha},
        "window": {"path": str(window_path), "sha256": window_sha},
        "resources": {"task_memory_max_bytes": 4096, "host_reserve_bytes": 1024},
        "runtime": {
            "runtime_prefix": str(Path(sys.executable).resolve().parents[1]),
            "abi_receipt_sha256": abi_sha,
        },
    }
    env = {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(contract_path),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
        "TASK41_P0_EXECUTION_WINDOW_PATH": str(window_path),
        "TASK41_P0_EXECUTION_WINDOW_SHA256": window_sha,
        "TASK41_P0_MEMORY_SWAP_MAX_BYTES": "0",
        "TASK41_P0_TASK_MEMORY_MAX_BYTES": "4096",
        "TASK41_P0_HOST_RESERVE_BYTES": "1024",
        "TASK41_P0_SAVED_OUTPUT_CONTINUATION": "1",
        "TASK41_P0_CONSUMER_SOURCE_SHA": consumer_sha,
        "TASK41_P0_EXPECTED_SOURCE_SHA": producer_sha,
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": abi_sha,
        "PHYSICAL_WATCHDOG_PARENT_PID": str(os.getppid()),
    }
    monkeypatch.setattr(os, "environ", env)
    monkeypatch.setattr(
        "src.runners.task41_p0_saved_output_continuation._source_identity",
        lambda _root: (consumer_sha, branch),
    )
    monkeypatch.setattr(
        "benchmarks.subreaper_watchdog.cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": True,
            "readable": True,
            "memory_limit_bytes": 4096,
            "swap_current_bytes": 0,
        },
    )
    _require_service_envelope(contract, contract_path, contract_sha, tmp_path)

    monkeypatch.setattr(
        task41_p0_contract,
        "require_task41_p0_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setattr(
        task41_p0_contract,
        "_saved_output_consumer_source_sha",
        lambda *_args, **_kwargs: consumer_sha,
    )
    env.update(
        {
            "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
            "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        }
    )
    identity = task41_p0_contract.qualified_activation_identity(env)
    assert identity == f"task41_p0_native_complex:{abi_sha}"
    assert isinstance(identity, str)

    env["TASK41_P0_CONSUMER_SOURCE_SHA"] = "c" * 40
    with pytest.raises(RuntimeError, match="producer and consumer source identities"):
        _require_service_envelope(contract, contract_path, contract_sha, tmp_path)


def test_service_call_chain_uses_string_activation_and_one_frozen_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path
    results_root = repo_root / "results" / "model"
    run_root = results_root / "attempt7"
    run_root.mkdir(parents=True)
    output_root = results_root / "continuation"
    contract_sha = "f" * 64
    window = FixedCampaignWindow(
        path=repo_root / "execution_window.json",
        sha256="e" * 64,
        payload={"accounting_path": str(repo_root / "window_accounting.jsonl")},
        anchor={},
        t0_utc_ns=100,
        deadline_utc_ns=1_800_000_000_100,
        total_seconds=1800.0,
        bootstrap_seconds=0.0,
        closeout_seconds=600.0,
    )
    contract = {
        "task_id": "task41-p0",
        "case": {"model_id": "model", "input_sha256": "a" * 64},
        "source": {"sha": "b" * 40},
        "branch": "task41extra_phi90_p50x50_g17x20",
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {"abi_receipt_sha256": "c" * 64},
    }
    activation = f"task41_p0_native_complex:{contract['runtime']['abi_receipt_sha256']}"
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_supervise(command: list[str], directory: Path, **kwargs: object) -> dict[str, object]:
        calls.append((command, kwargs))
        assert kwargs["campaign_window_path"] == window.path
        assert kwargs["campaign_window_sha256"] == window.sha256
        assert kwargs["tree_cap_bytes"] == contract["resources"]["task_memory_max_bytes"]
        assert kwargs["host_reserve_bytes"] == contract["resources"]["host_reserve_bytes"]
        if len(calls) == 1:
            assert kwargs["wall_seconds"] == window.cutoff_seconds
            output_root.mkdir()
            snapshot = output_root / "task41_p0_saved_output_checker_input.json"
            snapshot.write_text(json.dumps({"status": "OUTPUTS_READY"}))
            (output_root / "task41_p0_saved_output_continuation_receipt.json").write_text(
                json.dumps({"status": "OUTPUTS_READY"})
            )
            assert command[command.index("--consumer-source-sha") + 1] == "d" * 40
            assert command[command.index("--contract-sha256") + 1] == contract_sha
        else:
            assert kwargs["wall_seconds"] == window.closeout_seconds
            output_path = Path(command[command.index("--output") + 1])
            snapshot = output_root / "task41_p0_saved_output_checker_input.json"
            output_path.write_text(
                json.dumps(
                    {
                        "checker_passed": True,
                        "checker_input_snapshot_sha256": hashlib.sha256(
                            snapshot.read_bytes()
                        ).hexdigest(),
                    }
                )
            )
            assert command[command.index("--saved-output-continuation-input") + 1] == str(snapshot)
            assert command[command.index("--contract-sha256") + 1] == contract_sha
            assert kwargs["campaign_phase_authorization"]["source_sha"] == "d" * 40
            assert kwargs["campaign_phase_authorization"]["checker_kind"] == (
                "task41_p0_saved_output_continuation_checker"
            )
        return {"classification": "COMPLETED", "leader_exit_code": 0}

    import scripts.task40_v20_service_workflow as service_workflow

    monkeypatch.setattr(
        service_workflow.subprocess,
        "check_output",
        lambda command, **_kwargs: (
            "task41extra_phi90_p50x50_g17x20\n"
            if command[-1] == "--show-current"
            else "d" * 40 + "\n"
        ),
    )
    result = _run_task41_p0_saved_output_service(
        unit="task41-test",
        runtime_prefix=repo_root / "runtime",
        environment={"TASK41_P0_SAVED_OUTPUT_CONTINUATION": "1"},
        window=window,
        contract=contract,
        contract_path=repo_root / "contract.json",
        contract_sha=contract_sha,
        case_id="A2",
        run_root=run_root,
        output_root=output_root,
        consumer_source_sha="d" * 40,
        checker_only=False,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        input_path=repo_root / "input.dat",
        activation_command=["activate"],
        activation_identity=activation,
        preflight={"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1},
        preflight_command=["python", "preflight"],
        cgroup_start={"memory_limit_bytes": 1 << 30, "swap_current_bytes": 0},
        service_entry_accounting={"window_sha256": window.sha256},
        service_start_sample=clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
    )

    assert result == 0
    assert len(calls) == 2
    assert calls[0][1]["campaign_phase"] == "numeric"
    assert calls[1][1]["campaign_phase"] == "closeout"
    service_directory = output_root.with_name("continuation.service")
    assert calls[0][1]["phase_path"] == service_directory / "continuation_phase.json"
    assert calls[1][1]["phase_path"] == service_directory / "required_checker_phase.json"
    assert calls[0][1]["phase_path"] != calls[1][1]["phase_path"]
    assert calls[0][0][calls[0][0].index("--run-root") + 1] == str(run_root)
    assert calls[0][0][calls[0][0].index("--output-dir") + 1] == str(output_root)
    assert calls[1][0][calls[1][0].index("--output") + 1] == str(
        output_root / "task41_p0_saved_output_checker_result.json"
    )
    service_receipt = json.loads(
        (output_root.with_name("continuation.service") / "task41_p0_service_receipt.json")
        .read_text(encoding="utf-8")
    )
    assert service_receipt["producer_source_sha"] == "b" * 40
    assert service_receipt["consumer_source_sha"] == "d" * 40
    assert service_receipt["activation_identity"] == activation
    assert isinstance(service_receipt["activation_identity"], str)
    final_receipt = json.loads(
        (output_root / "task41_p0_saved_output_continuation_receipt.json")
        .read_text(encoding="utf-8")
    )
    checker_output = output_root / "task41_p0_saved_output_checker_result.json"
    checker_input = output_root / "task41_p0_saved_output_checker_input.json"
    assert final_receipt["status"] == "PASS"
    assert final_receipt["checker_input_snapshot_sha256"] == hashlib.sha256(
        checker_input.read_bytes()
    ).hexdigest()
    assert final_receipt["checker_result_sha256"] == hashlib.sha256(
        checker_output.read_bytes()
    ).hexdigest()


def test_task41_diffraction_inventory_checks_real_attempt7_snapshot() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "task41_p0_attempt7_diffraction_inventory.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    metrics = fixture["metrics"]
    orders = fixture["orders"]
    assert fixture["source_run_id"] == "task41extra_g13_p6_phi90_iterative_a2"
    assert len(orders) == 578

    runtime_gate = task41_diagnostic_diffraction_inventory(
        metrics, orders, expected_m_max=8, expected_n_max=8
    )
    checker_gate = _task41_a2_diagnostic_inventory_from_data(
        metrics, orders, expected_m_max=8, expected_n_max=8
    )
    assert runtime_gate["passed"] is True
    assert runtime_gate["expected_spatial_order_count"] == 289
    assert runtime_gate["expected_channel_count"] == 578
    assert checker_gate["passed"] is True

    missing = task41_diagnostic_diffraction_inventory(
        metrics, orders[:-1], expected_m_max=8, expected_n_max=8
    )
    assert missing["passed"] is False
    duplicate_orders = [*orders[:-1], orders[0]]
    duplicate = _task41_a2_diagnostic_inventory_from_data(
        metrics, duplicate_orders, expected_m_max=8, expected_n_max=8
    )
    assert duplicate["passed"] is False
    wrong_polarization = [*orders]
    wrong_polarization[0] = {**orders[0], "polarization": "x"}
    wrong_pol = _task41_a2_diagnostic_inventory_from_data(
        metrics, wrong_polarization, expected_m_max=8, expected_n_max=8
    )
    assert wrong_pol["passed"] is False
    wrong_bounds = _task41_a2_diagnostic_inventory_from_data(
        metrics, orders, expected_m_max=7, expected_n_max=8
    )
    assert wrong_bounds["passed"] is False


def test_only_the_known_saved_output_worker_failure_is_eligible(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    (run_root / "numerical_output").mkdir(parents=True)
    resolved_config = b'{"fixture":"Task41 frozen producer config"}\n'
    resolved_config_sha256 = hashlib.sha256(resolved_config).hexdigest()
    case = {
        "model_id": "task41extra_phi90_p50x50_g17x20",
        "run_id": "task41extra_g13_p6_phi90_iterative_a2",
        "method": "full3d_iterative",
        "mpi_size": 1,
        "input_sha256": "b" * 64,
        "physical_model_sha256": "c" * 64,
        "resolved_config_sha256": resolved_config_sha256,
    }
    contract = {
        "source": {"sha": "a" * 40},
        "case": case,
        "window": {"sha256": "d" * 64},
        "comparison": {"a1_binding_sha256": "e" * 64},
    }
    worker = {
        "status": "FAILED",
        "result_classification": "WORKER_FAILED",
        "official_result": False,
        "error": {
            "type": "ValueError",
            "message": "Task41 A1 full field representation failed the saved E/H sample witness",
        },
        "numeric_gates_passed": True,
        "source_sha": "a" * 40,
        "run_id": "task41extra_g13_p6_phi90_iterative_a2",
        "identity_packet": {
            "input_sha256": case["input_sha256"],
            "physical_model_sha256": case["physical_model_sha256"],
            "source_sha": "a" * 40,
            "run_id": case["run_id"],
        },
        "profile": "task41extra_g13_p6_phi90_a2_y_orbit_reference_v1",
        "stage": "TASK41_A2",
        "q_assembly_strategy": "ROW_TILE_BOUNDED_CSR_V17",
        "campaign_authority": {
            "task41_contract_sha256": "f" * 64,
            "campaign_window_sha256": "d" * 64,
            "a1_comparison_binding_sha256": "e" * 64,
        },
    }
    run_summary = {
        "status": "finished",
        "exit_status": 4,
        "result_classification": "WORKER_FAILED",
        "numerical_output_directory": str((run_root / "numerical_output").resolve()),
    }
    manifest = {
        "status": "finished",
        "result_classification": "WORKER_FAILED",
        "source_sha": "a" * 40,
        **case,
    }
    (run_root / "task40_v10_p6_candidate_summary.json").write_text(json.dumps(worker), encoding="utf-8")
    (run_root / "run_summary.json").write_text(json.dumps(run_summary), encoding="utf-8")
    (run_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_root / "resolved_config.json").write_bytes(resolved_config)

    original, _, _, evidence = _validate_original_attempt(run_root, contract, "f" * 64)
    assert original["result_classification"] == "WORKER_FAILED"
    assert evidence["worker_summary"]["sha256"]
    identity = _validate_original_solver_identity(original, case)
    assert "resolved_config_sha256" not in identity

    manifest["resolved_config_sha256"] = "0" * 64
    (run_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="run manifest identity differs.*resolved_config_sha256"):
        _validate_original_attempt(run_root, contract, "f" * 64)

    manifest["resolved_config_sha256"] = resolved_config_sha256
    (run_root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_root / "resolved_config.json").write_bytes(b'{"fixture":"changed"}\n')
    with pytest.raises(ValueError, match="resolved configuration differs"):
        _validate_original_attempt(run_root, contract, "f" * 64)

    (run_root / "resolved_config.json").write_bytes(resolved_config)

    worker["result_classification"] = "PASS"
    (run_root / "task40_v10_p6_candidate_summary.json").write_text(json.dumps(worker), encoding="utf-8")
    with pytest.raises(ValueError, match="not the preserved postprocessing-only failure"):
        _validate_original_attempt(run_root, contract, "f" * 64)


@pytest.mark.parametrize(
    ("volume_only", "geometry_pair", "v5_mode", "v5_complete", "v6_mode"),
    [
        (False, False, False, False, False),
        (True, False, False, False, False),
        (True, True, False, False, False),
        (True, False, True, False, False),
        (True, False, True, True, False),
        (True, False, True, True, True),
    ],
)
def test_b0_saved_evidence_audit_uses_supervised_service_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    volume_only: bool,
    geometry_pair: bool,
    v5_mode: bool,
    v5_complete: bool,
    v6_mode: bool,
) -> None:
    import scripts.task40_v20_service_workflow as service_workflow
    import src.runners.task41_p0_contract as contract_module
    import src.runners.task40_v10_campaign as campaign_module
    import benchmarks.subreaper_watchdog as watchdog_module
    import benchmarks.task034_wsl_resources as resource_module
    from src.runners.task41_p0_v4_volume_only_audit import (
        TASK41_P0_V4_SELECTED_ACTIVE_ROW,
        TASK41_P0_V4_SELECTED_ORIGINAL_ROW,
        TASK41_P0_V4_SOURCE_REPORT_SHA256,
        TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
    )

    repo_root = tmp_path
    results_root = repo_root / "results" / contract_module.TASK41_MODEL_ID
    donor_run = results_root / "donor_run"
    numerical_output = donor_run / "numerical_output"
    donor_run.mkdir(parents=True)
    donor_evidence = donor_run / "raw.npy"
    donor_evidence.write_bytes(b"immutable donor evidence")
    input_path = repo_root / "task41.dat"
    input_path.write_bytes(b"frozen B0 input\n")
    donor_config = donor_run / "resolved_config.json"
    donor_config.write_text('{"resolved": true}\n', encoding="utf-8")
    donor_summary = donor_run / "task40_v10_p6_candidate_summary.json"
    donor_summary.write_text('{"status": "FAIL"}\n', encoding="utf-8")
    donor_run_summary = donor_run / "run_summary.json"
    donor_run_summary.write_text(
        '{"run_id": "task41extra_b0_p6_phi90_07nm_iterative"}\n', encoding="utf-8"
    )
    donor_manifest = donor_run / "run_manifest.json"
    donor_manifest.write_text(
        json.dumps({
            "output_directory": str(donor_run),
            "numerical_output_directory": str(numerical_output),
        }),
        encoding="utf-8",
    )
    consumer_contract_path = repo_root / "consumer_contract.json"
    donor_contract_path = repo_root / "donor_contract.json"
    consumer_contract_path.write_text("{}\n", encoding="utf-8")
    donor_contract_path.write_text("{}\n", encoding="utf-8")
    runtime_prefix = repo_root / "runtime"
    fake_python = runtime_prefix / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text("fixture interpreter\n", encoding="utf-8")
    branch = contract_module.TASK41_BRANCH
    donor_source_sha = "a" * 40
    consumer_source_sha = "c" * 40
    consumer_contract_sha = "f" * 64
    donor_contract_sha = "b" * 64
    window_sha = "e" * 64
    abi_sha = "d" * 64
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    config_sha = hashlib.sha256(donor_config.read_bytes()).hexdigest()
    physical_sha = "9" * 64
    model_id = contract_module.TASK41_MODEL_ID
    donor_run_id = contract_module.TASK41_B0_RUN_ID
    consumer_run_id = contract_module.TASK41_B0_RUN_ID
    common_case = {
        "model_id": model_id,
        "method": "full3d_iterative",
        "mpi_size": 1,
        "input_path": str(input_path),
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": config_sha,
    }
    donor_contract = {
        "task_id": contract_module.TASK41_MODEL_ID,
        "branch": branch,
        "source": {"sha": donor_source_sha},
        "window": {"path": str(repo_root / "donor_window.json"), "sha256": "1" * 64},
        "case": {**common_case, "run_id": donor_run_id},
    }
    window = FixedCampaignWindow(
        path=repo_root / "consumer_window.json",
        sha256=window_sha,
        payload={"accounting_path": str(repo_root / "window_accounting.jsonl")},
        anchor={},
        t0_utc_ns=100,
        deadline_utc_ns=1_800_000_000_100,
        total_seconds=1800.0,
        bootstrap_seconds=0.0,
        closeout_seconds=600.0,
    )
    consumer_contract = {
        "task_id": contract_module.TASK41_MODEL_ID,
        "branch": branch,
        "source": {"sha": consumer_source_sha},
        "window": {"path": str(window.path), "sha256": window_sha},
        "case": {**common_case, "run_id": consumer_run_id},
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {
            "runtime_prefix": str(runtime_prefix),
            "abi_receipt_path": str(repo_root / "abi.json"),
            "jit_cache": str(repo_root / "jit"),
            "abi_receipt_sha256": abi_sha,
        },
    }
    donor_contract_path.write_text(json.dumps(donor_contract), encoding="utf-8")
    consumer_contract_path.write_text(json.dumps(consumer_contract), encoding="utf-8")
    output_root = results_root / "saved_b0_audit_attempt1"
    source_report_path = results_root / "v4_source" / "task41_p0_v4_volume_only_attribution.json"
    source_report_path.parent.mkdir(parents=True)
    source_report_path.write_text("{}\n", encoding="utf-8")
    geometry_reference_path = results_root / "v4_source" / "task41_p0_v4_geometry_pair_probe.json"
    geometry_reference_path.write_text("{}\n", encoding="utf-8")
    ffcx_c_source_path = repo_root / "frozen_ffcx_form.c"
    ffcx_c_source_path.write_text("/* frozen fixture */\n", encoding="utf-8")
    environment = {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
        "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": abi_sha,
    }
    monkeypatch.setenv("TASK41_P0_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK41_P0_CONTRACT_PATH", str(consumer_contract_path.resolve()))
    monkeypatch.setenv("TASK41_P0_CONTRACT_SHA256", consumer_contract_sha)
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_PATH", str(window.path))
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_SHA256", window_sha)
    monkeypatch.setenv("TASK41_P0_EXPECTED_SOURCE_SHA", consumer_source_sha)
    source_artifact_hash = hashlib.sha256(donor_evidence.read_bytes()).hexdigest()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_supervise(command: list[str], _directory: Path, **kwargs: object) -> dict[str, object]:
        calls.append((command, kwargs))
        assert not numerical_output.exists()
        assert Path(command[command.index("--numerical-output") + 1]) == numerical_output
        assert kwargs["campaign_window_sha256"] == window_sha
        if kwargs["campaign_phase"] == "numeric":
            assert volume_only is True
            assert command[1:4] == ["-m", "src.runners.task41_p0_v4_volume_only_audit", "--summary"]
            if geometry_pair:
                assert "--geometry-pair-only" in command
                assert command[command.index("--source-report") + 1] == str(source_report_path)
                volume_result = output_root / "task41_p0_v4_geometry_pair_probe.json"
                volume_result.write_text(json.dumps({
                    "status": "COMPLETED_GEOMETRY_PAIR_PROBE",
                    "geometry_pair_probe": {
                        "schema": "task41.p0.v4.geometry_pair_probe.v1",
                        "source_report_sha256": TASK41_P0_V4_SOURCE_REPORT_SHA256,
                        "selected_active_row": TASK41_P0_V4_SELECTED_ACTIVE_ROW,
                        "selected_original_row": TASK41_P0_V4_SELECTED_ORIGINAL_ROW,
                        "selected_cells": [{"cell_index": 26762}, {"cell_index": 26897}],
                    },
                }), encoding="utf-8")
            elif v5_complete:
                assert "--geometry-policy" in command
                assert command[command.index("--geometry-policy") + 1] == "mesh_actual_exact"
                assert Path(command[command.index("--geometry-reference-report") + 1]) == geometry_reference_path
                if v6_mode:
                    assert command[command.index("--raw-tensor-evaluator") + 1] == "actual_qmetric_blocked_gram"
                    assert Path(command[command.index("--ffcx-c-source") + 1]) == ffcx_c_source_path
                volume_result = output_root / (
                    "task41_p0_v6_actual_qmetric_candidate.json"
                    if v6_mode
                    else "task41_p0_v5_mesh_actual_exact_attribution.json"
                )
                evidence_dir = output_root / "volume_evidence"
                evidence_dir.mkdir()
                evidence_arrays = []
                for index in range(2):
                    artifact_path = evidence_dir / f"fixture-{index}.npy"
                    artifact_path.write_bytes(f"fixture-{index}".encode())
                    evidence_arrays.append({
                        "name": f"fixture-{index}",
                        "path": str(artifact_path),
                        "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                        "bytes": artifact_path.stat().st_size,
                        "shape": [1],
                        "dtype": "complex128",
                    })
                volume_result.write_text(
                    json.dumps({
                        "schema": (
                            "task41.p0.v6.actual_qmetric_candidate_receipt.v1"
                            if v6_mode
                            else "task41.p0.v5.mesh_actual_exact_attribution_receipt.v1"
                        ),
                        "status": "ACTUAL_COORDINATES_INSUFFICIENT",
                        "geometry_policy": "mesh_actual_exact",
                        "raw_tensor_evaluator": "actual_qmetric_blocked_gram" if v6_mode else None,
                        "donor_contract_sha256": donor_contract_sha,
                        "consumer_contract_sha256": consumer_contract_sha,
                        "geometry_reference_report_path": str(geometry_reference_path.resolve()),
                        "geometry_reference_report_sha256": TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
                        "candidate_numeric_status": "ACTUAL_COORDINATES_INSUFFICIENT",
                        "persisted_evidence_arrays": evidence_arrays,
                        "identity_audit": {
                            "completed": True,
                            "candidate_evaluator_identity": (
                                "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
                                if v6_mode
                                else None
                            ),
                            "candidate_full_action_gate": {"status": "ACTUAL_COORDINATES_INSUFFICIENT"},
                            "candidate_recovery_gate": {
                                "status": "ACTUAL_COORDINATES_INSUFFICIENT",
                                "native_volume_action_count": 2,
                            },
                            "global_geometry_native_elimination_attribution": {
                                "schema": (
                                    "task41.p0.v6.global_geometry_native_elimination_attribution.v1"
                                    if v6_mode
                                    else "task41.p0.v5.global_geometry_native_elimination_attribution.v1"
                                ),
                                "global_closure_status": "DIAGNOSTIC_ONLY",
                            },
                        },
                    }),
                    encoding="utf-8",
                )
            elif v5_mode:
                volume_result = output_root / (
                    "task41_p0_v6_actual_qmetric_candidate.json"
                    if v6_mode
                    else "task41_p0_v5_mesh_actual_exact_attribution.json"
                )
                volume_result.write_text(
                    json.dumps({
                        "status": "CANDIDATE_NOT_ADMITTED",
                        "candidate_admission": {"status": "CANDIDATE_NOT_ADMITTED"},
                    }),
                    encoding="utf-8",
                )
            else:
                assert "--geometry-pair-only" not in command
                volume_result = output_root / "task41_p0_v4_volume_only_attribution.json"
                volume_result.write_text(
                    json.dumps({"status": "COMPLETED", "identity_audit": {"completed": True}}),
                    encoding="utf-8",
                )
            return {
                "classification": "COMPLETED",
                "leader_exit_code": 3 if v5_mode and not v5_complete else 0,
            }
        assert kwargs["campaign_phase"] == "closeout"
        assert command[1:4] == ["-m", "src.runners.task41_p0_checker", "--saved-b0-evidence-audit"]
        assert "run_case.py" not in command
        if v5_complete:
            assert command[command.index("--mesh-actual-exact-report") + 1] == str(
                output_root
                / (
                    "task41_p0_v6_actual_qmetric_candidate.json"
                    if v6_mode
                    else "task41_p0_v5_mesh_actual_exact_attribution.json"
                )
            )
        elif v5_mode:
            assert "--mesh-actual-exact-report" not in command
        result_path = Path(command[command.index("--output") + 1])
        assert result_path == output_root / "task41_p0_b0_saved_evidence_audit.json"
        result_path.write_text(json.dumps({
            "audit_completed": True,
            "qualification_passed": False,
            "joint_action_passed": False,
            "official_result": False,
            **({
                "mesh_actual_exact_candidate_check": {
                    "check_completed": True,
                    "candidate_passed": False,
                }
            } if v5_complete else {}),
        }), encoding="utf-8")
        authorization = kwargs["campaign_phase_authorization"]
        assert authorization["checker_kind"] == "task41_p0_b0_saved_evidence_audit_checker"
        assert authorization["source_sha"] == consumer_source_sha
        assert donor_contract_path.resolve().as_posix() in authorization["input_paths"]
        watchdog_module._validate_campaign_closeout_authorization(
            command=command,
            campaign=window,
            authorization=authorization,
            worker_environment=kwargs["worker_environment"],
        )
        return {"classification": "COMPLETED", "leader_exit_code": 0}

    def require_contract(path: Path, **kwargs: object) -> tuple[dict[str, object], str]:
        if Path(path).resolve() == consumer_contract_path.resolve():
            assert kwargs["expected_sha256"] == consumer_contract_sha
            assert kwargs["check_current_source"] is True
            assert kwargs["require_clean_source"] is True
            return consumer_contract, consumer_contract_sha
        assert Path(path).resolve() == donor_contract_path.resolve()
        assert kwargs["expected_sha256"] == donor_contract_sha
        assert kwargs["check_current_source"] is False
        assert kwargs["require_clean_source"] is False
        return donor_contract, donor_contract_sha

    real_watchdog_sha256 = watchdog_module._sha256_file
    monkeypatch.setattr(
        watchdog_module,
        "_sha256_file",
        lambda path: (
            TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256
            if Path(path).resolve() == geometry_reference_path.resolve()
            else real_watchdog_sha256(path)
        ),
    )
    monkeypatch.setattr(contract_module, "require_task41_p0_contract", require_contract)
    monkeypatch.setattr(contract_module, "load_task41_p0_fixed_window", lambda *_a, **_k: window)
    monkeypatch.setattr(contract_module, "__file__", str(repo_root / "src/runners/task41_p0_contract.py"))
    monkeypatch.setattr(
        contract_module,
        "sha256_file",
        lambda path: (
            TASK41_P0_V4_SOURCE_REPORT_SHA256
            if Path(path).resolve() == source_report_path.resolve()
            else TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256
            if Path(path).resolve() == geometry_reference_path.resolve()
            else hashlib.sha256(Path(path).read_bytes()).hexdigest()
        ),
    )

    class FakeCampaignAccount:
        def __init__(self, _window: FixedCampaignWindow) -> None:
            pass

        def record_sample(self, *, label: str, phase: str) -> dict[str, str]:
            return {"label": label, "phase": phase, "window_sha256": window_sha256}

    window_sha256 = window_sha
    monkeypatch.setattr(campaign_module, "CampaignAccount", FakeCampaignAccount)
    monkeypatch.setattr(
        resource_module,
        "cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": True,
            "readable": True,
            "memory_limit_bytes": 1 << 30,
            "swap_current_bytes": 0,
            "memory_current_bytes": 1 << 20,
        },
    )
    monkeypatch.setattr(watchdog_module, "supervise", fake_supervise)
    monkeypatch.setattr(service_workflow, "_activation_environment", lambda *_a, **_k: (environment.copy(), ["activate"], 0, ""))
    monkeypatch.setattr(
        service_workflow,
        "_abi_preflight",
        lambda *_a, **_k: (["python", "preflight"], 0, json.dumps({"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1}), ""),
    )
    monkeypatch.setattr(
        service_workflow.subprocess,
        "check_output",
        lambda command, **_k: (branch if command[-1] == "--show-current" else consumer_source_sha) + "\n",
    )

    def fake_git_run(command: list[str], **_kwargs: object) -> object:
        if command[1] in {"rev-parse", "branch"}:
            value = consumer_source_sha + "\n" if command[1] == "rev-parse" else branch + "\n"
        elif command[1] == "status":
            value = ""
        else:
            raise AssertionError(f"unexpected Git command: {command}")
        return type("GitResult", (), {"returncode": 0, "stdout": value})()

    monkeypatch.setattr(service_workflow.subprocess, "run", fake_git_run)
    monkeypatch.setattr(sys, "executable", str(fake_python.resolve()))
    monkeypatch.chdir(repo_root)

    result = _run_task41_p0_service(
        unit="task41-b0-saved-audit-test",
        runtime_prefix=runtime_prefix,
        abi_receipt=repo_root / "abi.json",
        jit_cache=repo_root / "jit",
        case_args=[
            (
                "--task41-p0-saved-b0-volume-only-attribution"
                if volume_only
                else "--task41-p0-saved-b0-evidence-audit"
            ),
            "--donor-contract", str(donor_contract_path),
            "--donor-contract-sha256", donor_contract_sha,
            "--summary", str(donor_summary),
            "--numerical-output", str(numerical_output),
            "--output-dir", str(output_root),
            *( ["--geometry-pair-only", "--source-report", str(source_report_path)] if geometry_pair else [] ),
            *( ["--geometry-policy", "mesh_actual_exact", "--geometry-reference-report", str(geometry_reference_path)] if v5_mode else [] ),
            *( ["--raw-tensor-evaluator", "actual_qmetric_blocked_gram", "--ffcx-c-source", str(ffcx_c_source_path)] if v6_mode else [] ),
        ],
        contract_path=consumer_contract_path,
        repo_root=repo_root,
    )

    receipt = json.loads((output_root.with_name(output_root.name + ".service") / "task41_p0_service_receipt.json").read_text())
    assert result == (3 if v5_mode else 0), receipt.get("workflow_error")
    expected_calls = 1 if not volume_only or (v5_mode and not v5_complete) else 2
    assert len(calls) == expected_calls
    if volume_only:
        assert calls[0][1]["campaign_phase"] == "numeric"
        assert calls[0][1]["wall_seconds"] == window.cutoff_seconds
        if expected_calls == 2:
            assert calls[1][1]["campaign_phase"] == "closeout"
    else:
        assert calls[0][1]["campaign_phase"] == "closeout"
    assert receipt["status"] == (
        "failed_raw_evidence_retained" if v5_mode else "completed"
    )
    assert receipt["mode"] == (
        "saved_b0_v6_actual_qmetric_candidate"
        if v6_mode
        else "saved_b0_v5_mesh_actual_exact_candidate"
        if v5_mode
        else "saved_b0_v4_geometry_pair_probe"
        if geometry_pair
        else "saved_b0_v4_volume_only_attribution"
        if volume_only
        else "saved_b0_evidence_audit"
    )
    if geometry_pair:
        assert receipt["continuation_status"] == "v4_geometry_pair_probe_completed"
        assert receipt["geometry_pair_probe_command"][-3:] == [
            "--geometry-pair-only", "--source-report", str(source_report_path)
        ]
    if v5_mode:
        assert receipt["continuation_status"] == (
            "v6_actual_qmetric_candidate_completed"
            if v6_mode
            else "v5_mesh_actual_exact_candidate_completed"
            if v5_complete
            else "v6_actual_qmetric_candidate_failed_or_not_admitted"
            if v6_mode
            else "v5_mesh_actual_exact_candidate_failed_or_not_admitted"
        )
        if v5_complete:
            assert receipt["required_checker_result"]["audit_completed"] is True
            assert receipt["candidate_checker_status"] == "numerical_fail"
            assert receipt["candidate_numerical_passed"] is False
    if v5_mode and not v5_complete:
        assert receipt["required_checker_status"] == "not_run_candidate_not_admitted"
        assert receipt["candidate_checker_status"] == "not_applicable_candidate_not_built"
        assert "required_checker_result" not in receipt
    else:
        assert receipt["required_checker_status"] == "audit_completed"
        assert receipt["required_checker_result"]["official_result"] is False
    assert receipt["producer_source_sha"] == donor_source_sha
    assert receipt["consumer_source_sha"] == consumer_source_sha
    assert receipt["donor_source_sha"] == donor_source_sha
    assert "continuation_watchdog" not in receipt
    assert not numerical_output.exists()
    assert hashlib.sha256(donor_evidence.read_bytes()).hexdigest() == source_artifact_hash

    bad_output_root = results_root / "saved_b0_audit_bad_numerical_output_parent"
    with pytest.raises(
        ValueError,
        match="saved B0 audit donor paths or new consumer output directory differ",
    ):
        _run_task41_p0_service(
            unit="task41-b0-saved-audit-bad-path-test",
            runtime_prefix=runtime_prefix,
            abi_receipt=repo_root / "abi.json",
            jit_cache=repo_root / "jit",
            case_args=[
                "--task41-p0-saved-b0-evidence-audit",
                "--donor-contract", str(donor_contract_path),
                "--donor-contract-sha256", donor_contract_sha,
                "--summary", str(donor_summary),
                "--numerical-output", str(results_root / "other_donor" / "numerical_output"),
                "--output-dir", str(bad_output_root),
            ],
            contract_path=consumer_contract_path,
            repo_root=repo_root,
        )
    assert not bad_output_root.exists()


def test_b0_saved_evidence_checker_accepts_only_missing_bound_output_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.runners.task41_p0_checker as checker_module
    from src.runners.task41_p0_contract import TASK41_B0_RUN_ID, TASK41_MODEL_ID

    repo_root = tmp_path
    results_root = repo_root / "results" / TASK41_MODEL_ID
    donor_run = results_root / "donor_run"
    donor_run.mkdir(parents=True)
    numerical_output = donor_run / "numerical_output"
    input_bytes = b"frozen B0 input\n"
    input_path = repo_root / "b0_input.dat"
    input_path.write_bytes(input_bytes)
    (donor_run / "input_original.dat").write_bytes(input_bytes)
    config_path = donor_run / "resolved_config.json"
    config_path.write_bytes(b'{"resolved": true}\n')
    donor_evidence = donor_run / "raw.npy"
    donor_evidence.write_bytes(b"immutable donor evidence")
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    donor_source_sha = "a" * 40
    consumer_source_sha = "c" * 40
    donor_digest = "b" * 64
    consumer_digest = "f" * 64
    common_case = {
        "model_id": TASK41_MODEL_ID,
        "method": "full3d_iterative",
        "mpi_size": 1,
        "input_path": str(input_path),
        "input_sha256": input_sha,
        "physical_model_sha256": "9" * 64,
        "resolved_config_sha256": config_sha,
        "run_id": TASK41_B0_RUN_ID,
    }
    donor_contract = {
        "source": {"sha": donor_source_sha},
        "window": {"sha256": "1" * 64},
        "case": common_case,
    }
    consumer_contract = {
        "source": {"sha": consumer_source_sha},
        "window": {"sha256": "2" * 64},
        "case": common_case,
    }
    donor_contract_path = repo_root / "donor_contract.json"
    consumer_contract_path = repo_root / "consumer_contract.json"
    donor_contract_path.write_text("{}\n", encoding="utf-8")
    consumer_contract_path.write_text("{}\n", encoding="utf-8")
    donor_summary_path = donor_run / "task40_v10_p6_candidate_summary.json"
    donor_summary_path.write_text(json.dumps({"run_id": TASK41_B0_RUN_ID}), encoding="utf-8")
    run_manifest = {
        "run_id": TASK41_B0_RUN_ID,
        "model_id": TASK41_MODEL_ID,
        "method": "full3d_iterative",
        "mpi_size": 1,
        "input_sha256": input_sha,
        "physical_model_sha256": common_case["physical_model_sha256"],
        "resolved_config_sha256": config_sha,
        "source_sha": donor_source_sha,
        "output_directory": str(donor_run),
        "numerical_output_directory": str(numerical_output),
    }
    (donor_run / "run_manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")
    (donor_run / "run_summary.json").write_text(
        json.dumps({
            "run_id": TASK41_B0_RUN_ID,
            "output_directory": str(donor_run),
            "numerical_output_directory": str(numerical_output),
        }),
        encoding="utf-8",
    )

    def require_contract(path: Path, **kwargs: object) -> tuple[dict[str, object], str]:
        if Path(path).resolve() == donor_contract_path.resolve():
            assert kwargs["expected_sha256"] == donor_digest
            return donor_contract, donor_digest
        assert Path(path).resolve() == consumer_contract_path.resolve()
        assert kwargs["expected_sha256"] == consumer_digest
        return consumer_contract, consumer_digest

    monkeypatch.setattr(checker_module, "require_task41_p0_contract", require_contract)
    recovery_calls: list[Path] = []

    def fake_recovery_evidence_checks(
        _summary: object,
        output_path: Path,
        _contract: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        recovery_calls.append(output_path)
        assert output_path == numerical_output
        assert not output_path.exists()
        return {
            "audit_completed": True,
            "data_integrity": True,
            "recovery_passed": True,
            "joint_action_passed": False,
            "qualification_passed": False,
            "official_result": False,
            "errors": ["preserved full-action failure"],
            "checkpoints": [],
        }

    monkeypatch.setattr(
        checker_module,
        "_task41_b0_recovery_evidence_checks",
        fake_recovery_evidence_checks,
    )
    evidence_hash = hashlib.sha256(donor_evidence.read_bytes()).hexdigest()
    output_path = results_root / "saved_b0_audit" / "task41_p0_b0_saved_evidence_audit.json"
    result = checker_module.check_task41_p0_b0_saved_evidence_audit(
        summary_path=donor_summary_path,
        numerical_output=numerical_output,
        contract_path=donor_contract_path,
        contract_sha256=donor_digest,
        consumer_contract_path=consumer_contract_path,
        consumer_contract_sha256=consumer_digest,
        output_path=output_path,
        repo_root=repo_root,
    )
    assert result["audit_completed"] is True
    assert result["official_result"] is False
    assert result["joint_action_passed"] is False
    assert output_path.is_file()
    assert not numerical_output.exists()
    assert hashlib.sha256(donor_evidence.read_bytes()).hexdigest() == evidence_hash
    assert recovery_calls == [numerical_output]

    bad_output = results_root / "saved_b0_audit_wrong_parent" / "task41_p0_b0_saved_evidence_audit.json"
    with pytest.raises(ValueError, match="saved B0 donor numerical-output path differs"):
        checker_module.check_task41_p0_b0_saved_evidence_audit(
            summary_path=donor_summary_path,
            numerical_output=results_root / "other_donor" / "numerical_output",
            contract_path=donor_contract_path,
            contract_sha256=donor_digest,
            consumer_contract_path=consumer_contract_path,
            consumer_contract_sha256=consumer_digest,
            output_path=bad_output,
            repo_root=repo_root,
        )
    assert not bad_output.exists()
    assert recovery_calls == [numerical_output]
