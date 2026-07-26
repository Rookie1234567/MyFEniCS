from __future__ import annotations

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


def _fixture(seed: int) -> dict[str, object]:
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
        "stable_identity": {"fixture": True},
        "p5_trace_p6_interior_hanging_floquet": _fixture(1),
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
            / f"local_h_attempt2_mpi{mpi_size}_v2.json"
        )
        path.write_text(json.dumps(_record(mpi_size)), encoding="utf-8")
        paths.append(path)
    result = module.compare_authorities(tuple(paths))
    assert result["pass"] is True
    assert result["mpi_sizes"] == [1, 2, 8]


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
            / f"local_h_attempt2_mpi{mpi_size}_v2.json"
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
