from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.linalg import lu_factor


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = (
    ROOT
    / "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity"
    / "generate_local_h_attempt2_authority.py"
)
CHECKER = (
    ROOT
    / "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity"
    / "check_local_h_attempt2_authority.py"
)
MPI2_V3_RECORD = (
    ROOT
    / "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity"
    / "records/local_h_attempt2_mpi2_v3.json"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "task035d_local_h_attempt2_authority",
        GENERATOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "task035d_local_h_attempt2_checker",
        CHECKER,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _signature(seed: int) -> dict[str, object]:
    return {
        "size": 2,
        "linf": 2.0 + seed,
        "l2": 2.5 + seed,
        "sum": [1.0 + seed, -0.5],
        "weighted_sum": [0.25, 0.75 + seed],
        "normalized_quantized_1e10_sha256": f"{seed:064x}",
        "sample_indices": [0, 1],
        "normalized_samples": [[0.5, 0.25], [1.0, -0.5]],
    }


def _fixture(seed: int, mpi_size: int) -> dict[str, object]:
    names = (
        "matrix_action_root",
        "matrix_action_probe",
        "right_reduced_rhs",
        "left_reduced_rhs",
        "zero_rhs_full_recovery",
        "nonzero_rhs_full_recovery",
    )
    return {
        "stable_identity": {"seed": seed},
        "assembly_audit": {
            "interior_recovery_operator_residual_max": 1.0e-14,
            "interior_adjoint_operator_residual_max": 2.0e-14,
            "trace_constraint_owner_routing_qualified": True,
        },
        "cell_trace_binding_audit": {
            "pde_launch_ownership_gate": True,
            "full_dense_entity_catalog_replicated": False,
            "cross_rank_hanging_patch_count": 0 if mpi_size == 1 else 1,
            "cross_rank_hanging_relation_count": 0 if mpi_size == 1 else 1,
            "cross_rank_hanging_participant_entity_count": (
                0 if mpi_size == 1 else 1
            ),
            "cross_rank_hanging_remote_participant_entity_count": (
                0 if mpi_size == 1 else 1
            ),
            "cross_rank_hanging_remote_lookup_counts_by_rank": (
                [0] * mpi_size
                if mpi_size == 1
                else [1] + [0] * (mpi_size - 1)
            ),
            "owner_routed_trace_cache_audit": {
                "request_reply_count_closes": True,
            },
        },
        "observables": {
            **{name: _signature(seed) for name in names},
            "component_gram": {
                "expected_primal_norm": 3.0,
                "observed_primal_norm": 3.0,
                "expected_dual_norm": 4.0,
                "observed_dual_norm": 4.0,
            },
            "full_trace_recovery_max_abs_error": 3.0e-14,
            "full_active_rhs_recovery_mapping_max_abs_error": 4.0e-14,
            "zero_rhs_recovered_interior_equation_relative_residual": (
                5.0e-14
            ),
            "nonzero_rhs_recovered_interior_equation_relative_residual": (
                6.0e-14
            ),
        },
    }


def _record(mpi_size: int) -> dict[str, object]:
    return {
        "pass": True,
        "mpi_size": mpi_size,
        "source_sha": "a" * 40,
        "numerical_files": {},
        "fixture_config": {"fixture": True},
        "fixture_config_sha256": "c" * 64,
        "environment": {
            "rank_environments": [
                {
                    "qualified_activation": "1",
                    "python_executable": "/fixture/python",
                    "dolfinx": "fixture",
                    "basix": "fixture",
                    "petsc4py": "fixture",
                    "mpi4py": "fixture",
                    "petsc_scalar_type": "complex128",
                    "petsc_int_type": "int32",
                    "mpi_vendor": ["fixture", [1, 0, 0]],
                    "mpi_library_version": "fixture",
                }
            ]
        },
        "heavy_pde_started": False,
        "pde_accuracy_credit": False,
        "distributed_scalability_qualified": False,
        "pde_launch_ownership_gate": True,
        "stable_identity": {"fixture": True},
        "p5_trace_p6_interior_hanging_floquet": _fixture(1, mpi_size),
    }


def test_attempt2_lu_reconstruction_supports_equation_residual_oracle() -> None:
    module = _load_generator()
    rng = np.random.default_rng(352021)
    matrix = (
        rng.standard_normal((9, 9))
        + 1j * rng.standard_normal((9, 9))
        + 4.0 * np.eye(9)
    )
    reconstructed = module._matrix_from_lu_factor(lu_factor(matrix))
    np.testing.assert_allclose(
        reconstructed,
        matrix,
        rtol=2.0e-14,
        atol=2.0e-14,
    )


def test_attempt2_comparison_accepts_only_mpi1_mpi2_mpi8_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_generator()
    monkeypatch.setattr(
        module,
        "_recompute_record_pass",
        lambda _payload: (True, []),
    )
    monkeypatch.setattr(module, "NUMERICAL_FILES", ())
    monkeypatch.setattr(module, "CASE_DIR", tmp_path)
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "a" * 40,
    )
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    paths = []
    for mpi_size in (1, 2, 8):
        path = (
            records_dir
            / f"local_h_attempt2_mpi{mpi_size}_v3.json"
        )
        path.write_text(json.dumps(_record(mpi_size)), encoding="utf-8")
        paths.append(path)
    result = module.compare_authorities(tuple(paths))
    assert result["pass"] is True
    assert result["mpi_sizes"] == [1, 2, 8]
    assert result["pde_launch_gate"] is False
    assert result["diagnostic_only"] is True


def test_attempt2_comparison_fails_closed_on_observable_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_generator()
    monkeypatch.setattr(
        module,
        "_recompute_record_pass",
        lambda _payload: (True, []),
    )
    monkeypatch.setattr(module, "NUMERICAL_FILES", ())
    monkeypatch.setattr(module, "CASE_DIR", tmp_path)
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "a" * 40,
    )
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    paths = []
    for mpi_size in (1, 2, 8):
        payload = _record(mpi_size)
        if mpi_size == 8:
            payload["p5_trace_p6_interior_hanging_floquet"][
                "observables"
            ]["matrix_action_root"][
                "normalized_samples"
            ][0][0] += 0.25
        path = (
            records_dir
            / f"local_h_attempt2_mpi{mpi_size}_v3.json"
        )
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(path)
    result = module.compare_authorities(tuple(paths))
    assert result["pass"] is False
    assert (
        "p5_trace_p6_interior_hanging_floquet_"
        "matrix_action_root_mpi_identity"
    ) in result["failures"]


@pytest.mark.parametrize(
    "content",
    (
        "{not-json",
        '{"mpi_size": NaN}',
        '{"mpi_size": 1}',
    ),
)
def test_independent_checker_returns_structured_failure_for_bad_records(
    tmp_path: Path,
    content: str,
) -> None:
    module = _load_checker()
    paths = []
    for mpi_size in (1, 2, 8):
        path = tmp_path / f"bad-mpi{mpi_size}.json"
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    result = module.check_records(tuple(paths))
    assert result["pass"] is False
    assert result["status"] == "local_h_attempt2_evidence_fail"
    assert result["failures"]


def test_attempt2_signature_accepts_scale_normalized_cancelled_moment() -> None:
    left = _signature(1)
    right = json.loads(json.dumps(left))
    left["linf"] = 90.39870735838991
    right["linf"] = 90.39870735842221
    left["l2"] = 549.3292489233214
    right["l2"] = 549.3292489236558
    left["sum"] = [10.007053159472093, -577.2361390197937]
    right["sum"] = [10.007053167409254, -577.2361390030103]
    left["weighted_sum"] = [888.592494408143, 5610.578421213141]
    right["weighted_sum"] = [888.5924944116579, 5610.5784212138005]
    assert _load_checker()._signature_matches(left, right) is True
    assert _load_generator()._signature_matches(left, right) is True


def test_attempt2_signature_rejects_material_normalized_moment_tamper() -> None:
    left = _signature(1)
    right = json.loads(json.dumps(left))
    right["sum"][0] += 1.0e-6 * float(right["linf"])
    assert _load_checker()._signature_matches(left, right) is False
    assert _load_generator()._signature_matches(left, right) is False


def test_attempt2_output_contract_cannot_overwrite_history() -> None:
    generator = _load_generator()
    checker = _load_checker()
    historical = (
        ROOT
        / "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity"
        / "records/local_h_attempt2_mpi_identity_v1.json"
    )
    before = historical.read_bytes()
    with pytest.raises(ValueError, match="MPI-specific v3"):
        generator._validate_output_target(
            historical,
            mpi_size=1,
            comparison=False,
        )
    formal_inputs = tuple(
        checker.RECORD_DIR / checker.EXPECTED_NAMES[mpi_size]
        for mpi_size in (1, 2, 8)
    )
    with pytest.raises(ValueError, match="formal v3 identity"):
        checker._validate_cli_paths(formal_inputs, historical)
    assert historical.read_bytes() == before


def test_checker_detects_dirty_live_numerical_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_checker()
    committed = {
        relative: "a" * 64
        for relative in module.NUMERICAL_RELATIVE_FILES
    }
    tampered = module.NUMERICAL_RELATIVE_FILES[0]
    monkeypatch.setattr(
        module,
        "_solver_blob_manifest",
        lambda _head: committed,
    )
    monkeypatch.setattr(
        module,
        "_sha256",
        lambda path: (
            "b" * 64
            if Path(path).resolve() == (module.ROOT / tampered).resolve()
            else "a" * 64
        ),
    )
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "",
    )
    identity = module._live_numerical_source_identity("c" * 40)
    assert identity["verified_clean_numerical_source"] is False
    assert identity["mismatched_files"] == [tampered]


@pytest.mark.parametrize(
    ("path", "value", "expected_failure"),
    (
        (
            (
                "p5_trace_p6_interior_hanging_floquet",
                "cell_trace_binding_audit",
                "full_dense_entity_catalog_replicated",
            ),
            True,
            "owner_routed_cache",
        ),
        (
            (
                "p5_trace_p6_interior_hanging_floquet",
                "cell_trace_binding_audit",
                "owner_routed_trace_cache_audit",
                "wrong_owner_reply_count",
            ),
            1,
            "owner_routed_cache",
        ),
        (
            (
                "p5_trace_p6_interior_hanging_floquet",
                "cell_trace_binding_audit",
                "owner_routed_trace_cache_audit",
                "request_reply_count_closes",
            ),
            False,
            "owner_routed_cache",
        ),
        (
            (
                "p5_trace_p6_interior_hanging_floquet",
                "cell_trace_binding_audit",
                "remote_resolution_sha256",
            ),
            "0" * 64,
            "cross_rank_hanging_owner_path",
        ),
        (
            (
                "p5_trace_p6_interior_hanging_floquet",
                "cell_trace_binding_audit",
                "owner_routed_trace_cache_audit",
                "active_trace_work_ownership_ranges",
            ),
            [[0, 9000], [9000, 8100]],
            "owner_routed_cache",
        ),
        (
            (
                "p5_trace_p6_interior_hanging_floquet",
                "cell_trace_binding_audit",
                "hanging_cell_ghost_counts_by_rank",
            ),
            [],
            "cross_rank_hanging_owner_path",
        ),
        (
            (
                "p5_trace_p6_interior_hanging_floquet",
                "cell_trace_binding_audit",
                "cross_rank_hanging_remote_participant_entities",
            ),
            [],
            "cross_rank_hanging_owner_path",
        ),
        (
            (
                "component_resource_ledger",
                "retained_entity_block_cache_bytes_global_sum",
            ),
            -1,
            "resource_semantics",
        ),
        (
            (
                "component_resource_ledger",
                "outgoing_reply_logical_bytes_by_rank",
            ),
            [],
            "resource_semantics",
        ),
        (
            ("distributed_scalability_qualified",),
            True,
            "declared_scope",
        ),
        (
            ("pde_launch_ownership_gate",),
            False,
            "declared_scope",
        ),
    ),
)
def test_independent_v3_checker_rejects_owner_routing_tamper(
    path: tuple[str, ...],
    value: object,
    expected_failure: str,
) -> None:
    if not MPI2_V3_RECORD.exists():
        pytest.skip("v3 formal authority is generated after source commit")
    module = _load_checker()
    payload = copy.deepcopy(module._strict_load(MPI2_V3_RECORD))
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    failures = module._validate_record(
        MPI2_V3_RECORD,
        payload,
        prior_manifest=module._prior_authority_manifest(),
        history_manifest=module._attempt2_history_immutability_manifest(),
    )
    assert expected_failure in failures
