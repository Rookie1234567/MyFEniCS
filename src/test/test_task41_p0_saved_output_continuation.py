from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
import sys
from types import SimpleNamespace

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
    _task41_v6_candidate_producer_contract,
    _task41_v6_report_requires_prefix_qualification,
    compare_task41_p0_b0_saved_y_g_arrays,
)
from src.runners import task41_p0_contract
from src.runners.task40_v10_campaign import FixedCampaignWindow
from src.runners.workflow_timebase import clock_sample
from scripts.task40_v20_service_workflow import (
    _run_task41_p0_saved_output_service,
    _task41_p0_checker_only_snapshot_identity,
    _run_task41_p0_service,
)


def test_saved_y_g_comparison_distinguishes_rhs_only_change(tmp_path: Path) -> None:
    arrays = {
        "v6_y": np.array([[1 + 2j, 3 - 1j], [2 + 0j, 4 + 2j]], dtype=np.complex128),
        "v6_g": np.array([[0 + 1j, 1 + 0j], [1 - 1j, 2 + 0j]], dtype=np.complex128),
    }
    arrays["v9_y"] = arrays["v6_y"].copy()
    arrays["v9_g"] = arrays["v6_g"].copy()
    arrays["v9_g"][1, 0] += 0.25 - 0.5j
    paths = {}
    hashes = {}
    for name, array in arrays.items():
        path = tmp_path / f"{name}.npy"
        np.save(path, array, allow_pickle=False)
        paths[name] = path
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    result = compare_task41_p0_b0_saved_y_g_arrays(
        v6_y_path=paths["v6_y"],
        v6_g_path=paths["v6_g"],
        v9_y_path=paths["v9_y"],
        v9_g_path=paths["v9_g"],
        expected_sha256s=hashes,
        expected_shape=(2, 2),
        trace_rows=1,
        target_rows=(1,),
        denominators=(10.0, 20.0),
        block_rows=1,
    )

    assert result["status"] == "COMPLETED"
    assert result["data_integrity"] is True
    assert result["vectors"]["delta_y"]["norm2_by_column"] == [0.0, 0.0]
    assert result["vectors"]["delta_g"]["norm2_by_column"][0] == pytest.approx(0.3125)
    assert result["vectors"]["delta_g"]["norm2_by_column"][1] == 0.0
    assert result["energy_identity"]["residual_lhs_minus_rhs_by_column"] == pytest.approx(
        [0.0, 0.0], abs=1e-14
    )
    assert result["trace_port_split"]["status"] == "COMPLETED"
    assert result["vectors"]["d9"]["norm2_by_region_and_column"]["trace"] != [0.0, 0.0]
    assert result["vectors"]["d9"]["norm2_by_region_and_column"]["port"] != [0.0, 0.0]
    assert result["vectors"]["d9"]["maxima_by_region_and_column"]["port"]["abs_row"][0] == 1
    assert result["vectors"]["d9"]["norm_over_frozen_denominator_by_region_and_column"]["port"][0] > 0
    assert result["selected_row_slices"]["1"]["d9"][0] == [0.75, 1.5]
    assert result["subtraction_associativity"]["status"] == "COMPLETED"
    assert result["vectors"]["d9"]["top10_energy_coverage_by_column"] == pytest.approx([1.0, 1.0])
    assert result["numerical_accumulation"]["independent_scalar_reduction"] is True
    assert result["energy_identity"]["independent_minus_numpy_2real_inner_by_column"] == pytest.approx(
        [0.0, 0.0], abs=1e-14
    )
    assert result["full_length_delta_arrays_saved"] is False
    assert result["official_result"] is False


def test_saved_y_g_comparison_reports_changes_on_both_sides_and_rejects_bad_hash(
    tmp_path: Path,
) -> None:
    arrays = {
        "v6_y": np.array([[1 + 0j, 0 + 2j], [2 + 1j, 3 - 1j]], dtype=np.complex128),
        "v6_g": np.array([[0 + 0j, 1 + 1j], [1 + 0j, 1 + 0j]], dtype=np.complex128),
        "v9_y": np.array([[1.25 - 0.5j, 0 + 2j], [2 + 1j, 2.5 - 1j]], dtype=np.complex128),
        "v9_g": np.array([[0.5 + 0j, 1 + 1j], [1 + 0j, 1.5 + 0.25j]], dtype=np.complex128),
    }
    paths = {}
    hashes = {}
    for name, array in arrays.items():
        path = tmp_path / f"{name}.npy"
        np.save(path, array, allow_pickle=False)
        paths[name] = path
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    kwargs = {
        "v6_y_path": paths["v6_y"],
        "v6_g_path": paths["v6_g"],
        "v9_y_path": paths["v9_y"],
        "v9_g_path": paths["v9_g"],
        "expected_sha256s": hashes,
        "expected_shape": (2, 2),
        "trace_rows": 1,
        "denominators": (3.0, 5.0),
        "block_rows": 2,
    }
    result = compare_task41_p0_b0_saved_y_g_arrays(**kwargs)
    assert result["vectors"]["delta_y"]["norm2_by_column"][0] > 0
    assert result["vectors"]["delta_g"]["norm2_by_column"][0] > 0
    assert result["vectors"]["delta_y"]["norm2_by_column"][1] > 0
    assert result["vectors"]["delta_g"]["norm2_by_column"][1] > 0
    assert result["vectors"]["y9_g6"]["norm2_by_column"][0] != result[
        "vectors"
    ]["y6_g9"]["norm2_by_column"][0]
    assert result["energy_identity"]["residual_lhs_minus_rhs_by_column"] == pytest.approx(
        [0.0, 0.0], abs=1e-13
    )
    bad_hashes = dict(hashes, v9_g="0" * 64)
    with pytest.raises(ValueError, match="v9_g differs from its bound SHA-256"):
        compare_task41_p0_b0_saved_y_g_arrays(**{**kwargs, "expected_sha256s": bad_hashes})


def test_saved_diagnostics_prepare_binds_scope_and_reuses_entry_source_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_spec = task41_p0_contract._task41_case("B0")
    root = tmp_path / "repo"
    root.mkdir()
    source_shas = ["a" * 40]

    def fake_git(_root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return source_shas[0]
        if args == ("branch", "--show-current"):
            return task41_p0_contract.TASK41_BRANCH
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        raise AssertionError(f"unexpected git query: {args!r}")

    monkeypatch.setattr(task41_p0_contract, "_git", fake_git)
    monkeypatch.setattr(
        task41_p0_contract, "verify_task41_b0_saved_surface_donor", lambda *a, **k: None
    )
    monkeypatch.setattr(
        task41_p0_contract, "validate_task41_specification", lambda *a, **k: None
    )

    input_path = root / case_spec["input_relative"]
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"test-only B0 specification")
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    specification = SimpleNamespace(
        input_sha256=input_sha,
        identity={
            "model_id": task41_p0_contract.TASK41_MODEL_ID,
            "run_id": case_spec["run_id"],
        },
        physical_model_sha256="d" * 64,
        method={"kind": case_spec["method"]},
        execution={"mpi_size": 1},
        as_jsonable=lambda: {},
    )
    from src.geometry import task41_phi90_profile
    from src.io import execution_plan, input_validation

    monkeypatch.setattr(input_validation, "load_and_resolve", lambda _path: specification)
    monkeypatch.setattr(task41_phi90_profile, "task41_payload_errors", lambda _value: [])
    monkeypatch.setattr(execution_plan, "resolved_config_bytes", lambda _spec: b"test-config")

    runtime = root / "runtime"
    python = runtime / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    python.chmod(0o755)
    abi_receipt = root / "abi.json"
    abi_receipt.write_text("{}\n", encoding="utf-8")
    jit_cache = root / "jit-cache"
    jit_cache.mkdir()
    monkeypatch.setattr(
        task41_p0_contract,
        "_check_task41_native_receipt",
        lambda path, _runtime: hashlib.sha256(path.read_bytes()).hexdigest(),
    )

    controller = root / task41_p0_contract.TASK41_B0_CONTROLLER_RELATIVE
    controller.mkdir(parents=True)
    v9_ledger = controller / "campaign_accounting_v9_24h.jsonl"
    v9_ledger.write_text("{}\n", encoding="utf-8")
    v9_window = root / task41_p0_contract.TASK41_B0_V9_WINDOW_RELATIVE
    v9_window.parent.mkdir(parents=True, exist_ok=True)
    v9_window.write_text(
        json.dumps({"accounting_path": str(v9_ledger.resolve())}), encoding="utf-8"
    )

    utc_ns = [1_800_000_000_000_000_000]

    def fake_clock_sample(*, include_boot_id: bool = False) -> dict[str, object]:
        utc_ns[0] += 10_000_000
        sample: dict[str, object] = {
            "monotonic": 1_000.0 + (utc_ns[0] - 1_800_000_000_000_000_000) / 1e9,
            "boottime": 2_000.0 + (utc_ns[0] - 1_800_000_000_000_000_000) / 1e9,
            "utc_ns": utc_ns[0],
            "boot_id": "saved-diagnostics-test-boot",
        }
        return sample if include_boot_id else sample

    monkeypatch.setattr(task41_p0_contract, "clock_sample", fake_clock_sample)
    kwargs = {
        "runtime_prefix": runtime,
        "abi_receipt": abi_receipt,
        "jit_cache": jit_cache,
        "current_root": root,
        "case_id": "B0",
        "b0_saved_diagnostics_6h": True,
    }
    first = task41_p0_contract.prepare_task41_p0(**kwargs)
    window_path = root / first["window_path"]
    first_window_raw = window_path.read_bytes()
    first_window = json.loads(first_window_raw)
    assert first_window["total_seconds"] == 21_600.0
    assert first_window["numerical_seconds"] == 20_400.0
    assert first_window["closeout_seconds"] == 1_200.0
    assert first_window["source_sha"] == "a" * 40

    source_shas[0] = "b" * 40
    second = task41_p0_contract.prepare_task41_p0(**kwargs)
    assert second["window_path"] == first["window_path"]
    assert second["window_sha256"] == first["window_sha256"]
    assert window_path.read_bytes() == first_window_raw

    contract_path = root / second["contract_path"]
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["source"]["sha"] == "b" * 40
    assert contract["window"]["entry_source_sha"] == "a" * 40
    assert contract["numerical_strategy"] == {
        "schema": "task41.p0.b0.internal_rhs_strategy.v1",
        "internal_rhs_strategy": task41_p0_contract.TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
    }
    assert contract["execution_scope"] == task41_p0_contract.TASK41_B0_SAVED_DIAGNOSTICS_SCOPE
    assert second["service_command"] is None
    assert second["saved_diagnostics_output_root"] == str(
        Path("results") / task41_p0_contract.TASK41_MODEL_ID / "task41_p0_saved_diagnostics_6h" / second["window_sha256"]
    )


@pytest.mark.parametrize("failure", [None, "dirty", "branch", "source", "legacy_scope"])
def test_saved_diagnostics_service_source_gate_allows_current_entry_only_for_v11_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    root = Path(task41_p0_contract.__file__).resolve().parents[2]
    head = "a" * 40
    contract_sha = "d" * 64
    abi_sha = "e" * 64
    runtime = Path(sys.executable).resolve().parents[1]
    contract = {
        "task_id": task41_p0_contract.TASK41_MODEL_ID,
        "branch": task41_p0_contract.TASK41_BRANCH,
        "source": {"sha": head if failure != "source" else "b" * 40},
        "execution_scope": task41_p0_contract.TASK41_B0_SAVED_DIAGNOSTICS_SCOPE,
        "case": {
            "model_id": task41_p0_contract.TASK41_MODEL_ID,
            "run_id": task41_p0_contract.TASK41_B0_RUN_ID,
            "input_path": "input/b0.dat",
        },
        "window": {
            "path": str(task41_p0_contract.TASK41_B0_SAVED_DIAGNOSTICS_WINDOW_RELATIVE),
            "sha256": "f" * 64,
            "entry_source_sha": head,
            "scope": task41_p0_contract.TASK41_B0_SAVED_DIAGNOSTICS_SCOPE,
            "authorization_sha256": "c" * 64,
        },
        "runtime": {
            "runtime_prefix": str(runtime),
            "abi_receipt_path": str(root / "abi.json"),
            "abi_receipt_sha256": abi_sha,
            "jit_cache": str(root / "jit"),
        },
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
    }
    if failure == "legacy_scope":
        contract.pop("execution_scope")
        contract["window"] = {
            "path": str(task41_p0_contract.TASK41_B0_V9_WINDOW_RELATIVE),
            "sha256": "f" * 64,
            "entry_source_sha": head,
        }
    current_branch = "wrong-branch" if failure == "branch" else task41_p0_contract.TASK41_BRANCH
    status = " M src/runners/example.py" if failure == "dirty" else ""

    def fake_git(_root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return head
        if args == ("branch", "--show-current"):
            return current_branch
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return status
        raise AssertionError(f"unexpected git query: {args!r}")

    def require_contract(_path: object, **kwargs: object) -> tuple[dict[str, object], str]:
        assert kwargs["current_root"] == root
        assert kwargs["check_current_source"] is False
        assert kwargs["require_clean_source"] is True
        return contract, contract_sha

    monkeypatch.setattr(task41_p0_contract, "_git", fake_git)
    monkeypatch.setattr(task41_p0_contract, "require_task41_p0_contract", require_contract)
    monkeypatch.setattr(
        task41_p0_contract,
        "load_task41_p0_fixed_window",
        lambda *_args, **_kwargs: SimpleNamespace(
            path=root / task41_p0_contract.TASK41_B0_SAVED_DIAGNOSTICS_WINDOW_RELATIVE,
            sha256="f" * 64,
        ),
    )
    if failure is not None:
        expected = "distinct consumer head" if failure == "legacy_scope" else "current contracted source"
        with pytest.raises(task41_p0_contract.Task41ContractError, match=expected):
            task41_p0_contract.launcher_values(
                tmp_path / "contract.json", current_root=root, saved_output_continuation=True
            )
        return

    values = task41_p0_contract.launcher_values(
        tmp_path / "contract.json", current_root=root, saved_output_continuation=True
    )
    assert values[-1] == head
    environment = {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(tmp_path / "contract.json"),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
        "TASK41_P0_SAVED_OUTPUT_CONTINUATION": "1",
        "TASK41_P0_B0_V9_FAILED_TERMINAL_AUDIT": "1",
        "TASK41_P0_CONSUMER_SOURCE_SHA": head,
        "TASK41_P0_EXPECTED_SOURCE_SHA": head,
        "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
        "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": abi_sha,
    }
    monkeypatch.setattr(
        task41_p0_contract, "require_task41_p0_contract", require_contract
    )
    assert task41_p0_contract.qualified_activation_identity(environment) == (
        f"task41_p0_native_complex:{abi_sha}"
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


def test_v7_saved_checker_recomputes_complex_balpha_scopes_and_state_binding(
    tmp_path: Path,
) -> None:
    from src.runners.task41_p0_checker import (
        _task41_b0_v7_attribution_state_recheck,
        _task41_b0_v7_map_original_rows_to_active,
        _task41_b0_v7_nonactive_rhs_difference,
    )

    active = np.asarray([2, 0], dtype=np.int64)
    volume_rhs = np.asarray([0.25 + 0.1j, 0.0j, 0.5 - 0.2j, 0.0j], dtype=np.complex128)
    beta = 0.18 + 0.13j
    native_rhs = volume_rhs.copy()
    native_rhs[0] += beta
    assert _task41_b0_v7_nonactive_rhs_difference(
        native_rhs, volume_rhs, active
    )["absolute_l2"] == 0.0
    bad_interior_rhs = native_rhs.copy()
    bad_interior_rhs[1] += 0.01j
    assert _task41_b0_v7_nonactive_rhs_difference(
        bad_interior_rhs, volume_rhs, active
    )["absolute_l2"] == pytest.approx(0.01)
    beta_rows = np.asarray([0], dtype=np.int64)
    beta_values = np.asarray([beta], dtype=np.complex128)
    beta_active = np.zeros(2, dtype=np.complex128)
    np.add.at(
        beta_active,
        _task41_b0_v7_map_original_rows_to_active(beta_rows, active),
        beta_values,
    )
    assert np.array_equal(beta_active, np.asarray([0.0j, beta]))
    d_volume = np.asarray([0.4 - 0.2j, -0.3 + 0.1j], dtype=np.complex128)
    state_inputs = []
    for native_action, T_r_i, delta_t in (
        (
            np.asarray([0.07 + 0.02j, 0.0j, -0.03 + 0.08j, 0.0j]),
            np.asarray([0.03 + 0.01j, -0.04 + 0.02j]),
            np.asarray([0.2 + 0.05j, -0.1 + 0.03j]),
        ),
        (
            np.asarray([-0.02 + 0.04j, 0.0j, 0.09 - 0.01j, 0.0j]),
            np.asarray([-0.06 + 0.02j, 0.08 - 0.03j]),
            np.asarray([-0.03 + 0.11j, 0.12 - 0.04j]),
        ),
    ):
        r_volume = volume_rhs[active] - native_action[active]
        delta_t_plus_Q = d_volume + r_volume + T_r_i
        attributed_terms = delta_t_plus_Q - delta_t
        r_full = native_rhs[active] - native_action[active] - beta_active
        state_inputs.append(
            {
                "native_action": native_action,
                "T_r_i": T_r_i,
                "delta_t": delta_t,
                "attributed_terms": attributed_terms,
                "reduce_r_volume": r_volume + T_r_i,
                "reduce_r_full": r_full + T_r_i,
            }
        )

    def recheck(
        state: dict[str, np.ndarray],
        *,
        beta_values: np.ndarray = beta_values,
        saved_d: np.ndarray = d_volume,
        evidence_directory: Path | None = None,
        evidence_prefix: str | None = None,
    ):
        return _task41_b0_v7_attribution_state_recheck(
            candidate_d_full=d_volume,
            candidate_d_volume=saved_d,
            active_original_rows=active,
            native_rhs=native_rhs,
            native_volume_rhs=volume_rhs,
            b_alpha_rows=beta_rows,
            b_alpha_values=beta_values,
            native_volume_action=state["native_action"],
            T_r_i=state["T_r_i"],
            delta_t=state["delta_t"],
            attributed_terms=state["attributed_terms"],
            reduce_r_volume=state["reduce_r_volume"],
            reduce_r_full=state["reduce_r_full"],
            frozen_denominator=2.0,
            evidence_directory=evidence_directory,
            evidence_prefix=evidence_prefix,
        )

    checked = [
        recheck(
            state_inputs[0],
            evidence_directory=tmp_path,
            evidence_prefix="task41_p0_v7_attribution_col0_j0",
        ),
        recheck(state_inputs[1]),
    ]
    for result in checked:
        diagnostics = result["diagnostics"]
        assert diagnostics["legacy_closure_minus_beta_active"]["absolute_l2"] < 1.0e-14
        assert diagnostics["corrected_full_closure"]["absolute_l2"] < 1.0e-14
        assert diagnostics["corrected_volume_closure"]["absolute_l2"] < 1.0e-14
        assert diagnostics["reduce_r_volume_vs_raw_trace_plus_T_r_i"]["absolute_l2"] < 1.0e-14
        assert diagnostics["reduce_r_full_vs_raw_trace_plus_T_r_i"]["absolute_l2"] < 1.0e-14
        assert diagnostics["d_hat_volume_minus_saved_d_volume"]["absolute_l2"] < 1.0e-14
        assert diagnostics["d_hat_full_minus_candidate_d_full"]["absolute_l2"] < 1.0e-14
    assert np.linalg.norm(checked[0]["_d_hat_volume"] - checked[1]["_d_hat_volume"]) < 1.0e-14
    assert set(checked[0]["persisted_closure_arrays"]) == {
        "corrected_full_closure",
        "corrected_volume_closure",
    }
    for artifact in checked[0]["persisted_closure_arrays"].values():
        path = Path(artifact["path"])
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        loaded = np.load(path, allow_pickle=False)
        assert loaded.shape == (2,)
        assert loaded.dtype == np.dtype(np.complex128)

    wrong_state = dict(state_inputs[0])
    wrong_state["native_action"] = state_inputs[1]["native_action"]
    assert recheck(wrong_state)["diagnostics"]["corrected_volume_closure"]["absolute_l2"] > 1.0e-2
    wrong_phase = recheck(state_inputs[0], beta_values=np.asarray([beta * (0.6 + 0.8j)]))
    assert wrong_phase["epsilon_rhs_native_minus_volume_minus_Balpha"]["absolute_l2"] > 1.0e-2
    old_d = recheck(state_inputs[0], saved_d=d_volume + 0.25)
    assert old_d["diagnostics"]["d_hat_volume_minus_saved_d_volume"]["absolute_l2"] > 0.3


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


def test_v6_global_attribution_uses_parent_identity_metadata(tmp_path: Path) -> None:
    from src.runners import task41_p0_checker as checker

    identity_audit, _, _ = _v6_candidate_audit_fixture(tmp_path)
    identity_audit["candidate_evaluator_identity"] = identity_audit[
        "candidate_evaluator_audit"
    ]["implementation"]
    checker._task41_validate_v6_actual_qmetric_audit(identity_audit)
    attribution = {
        "schema": "task41.p0.v6.global_geometry_native_elimination_attribution.v1",
        "columns": [{}, {}],
        "global_closure_status": "DIAGNOSTIC_ONLY",
        "diagnostic_scales": [
            "left_and_right_identity_norms",
            "frozen_candidate_denominator",
            "sum_of_accumulated_term_norms",
        ],
    }

    checker._task41_v6_global_attribution_identity_binding(attribution, identity_audit)
    for field in (
        "candidate_evaluator_identity",
        "candidate_evaluator_cache_identity",
    ):
        inconsistent = {**attribution, field: "wrong-parent-binding"}
        with pytest.raises(ValueError, match="differs from parent identity_audit"):
            checker._task41_v6_global_attribution_identity_binding(
                inconsistent, identity_audit
            )


@pytest.mark.parametrize("wrong_denominator", [True, False])
def test_v6_candidate_recheck_checks_frozen_row_denominator_before_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong_denominator: bool
) -> None:
    from src.runners import task41_p0_checker as checker

    report_path = (
        tmp_path
        / "results"
        / "task41extra_phi90_p50x50_g17x20"
        / "attempt"
        / "task41_p0_v6_actual_qmetric_candidate.json"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text("{}\n", encoding="utf-8")
    denominators = (2225.481253487629, 2225.4807123031883)
    incident = [
        {
            "column": column,
            "cell_count": 2,
            "frozen_denominator": denominators[column],
            "difference_over_frozen_denominator": 0.0,
        }
        for column in (0, 1, 0, 1, 0, 1)
    ]
    if wrong_denominator:
        incident[0]["frozen_denominator"] = 1.0
    report = {
        "schema": "task41.p0.v6.actual_qmetric_candidate_receipt.v1",
        "status": "ACTUAL_COORDINATES_INSUFFICIENT",
        "candidate_numeric_status": "ACTUAL_COORDINATES_INSUFFICIENT",
        "identity_audit": {},
        "candidate_prefix_qualification": {
            "original_failed_row_incident_contributions": incident,
        },
    }
    monkeypatch.setattr(checker, "_json_object", lambda *_args: report)
    monkeypatch.setattr(
        checker,
        "_task41_mesh_actual_exact_candidate_profile",
        lambda *_args: {
            "version": "v6",
            "candidate_prefix": "candidate",
            "attribution_prefix": "donor",
        },
    )
    monkeypatch.setattr(
        checker,
        "_task41_validate_v6_actual_qmetric_audit",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        checker,
        "_task41_validate_v6_prefix_qualification",
        lambda *_args, **_kwargs: "PREFIX_QUALIFIED",
    )

    expected_error = (
        "two saved-cell contributions on the frozen failed row"
        if wrong_denominator
        else "donor/consumer/geometry identity differs"
    )
    with pytest.raises(ValueError, match=expected_error):
        checker._task41_mesh_actual_exact_candidate_recheck(
            report_path,
            donor={},
            donor_contract_sha256="a" * 64,
            consumer={},
            consumer_contract_sha256="b" * 64,
            donor_contract={},
            repo_root=tmp_path,
            candidate_producer_contract={"source": {"sha": "c" * 40}},
            candidate_producer_contract_sha256="c" * 64,
        )


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


@pytest.mark.parametrize("failure", [None, "report_hash", "producer_case"])
def test_v6_saved_report_binds_producer_contract_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    import src.runners.task41_p0_checker as checker_module
    from src.runners.task41_p0_contract import (
        TASK41_B0_RUN_ID,
        TASK41_MODEL_ID,
        contract_relative_path,
    )

    repo_root = tmp_path
    results_root = repo_root / "results" / TASK41_MODEL_ID
    report_path = results_root / "attempt10" / "task41_p0_v6_actual_qmetric_candidate.json"
    report_path.parent.mkdir(parents=True)
    producer_source_sha = "a" * 40
    producer_contract_sha = "b" * 64
    window_sha = "c" * 64
    common_case = {
        "model_id": TASK41_MODEL_ID,
        "method": "full3d_iterative",
        "mpi_size": 1,
        "input_sha256": "d" * 64,
        "physical_model_sha256": "e" * 64,
        "resolved_config_sha256": "f" * 64,
        "run_id": TASK41_B0_RUN_ID,
    }
    producer_case = dict(common_case)
    if failure == "producer_case":
        producer_case["run_id"] = "unregistered-wrong-case"
    producer_contract = {
        "source": {"sha": producer_source_sha},
        "window": {"sha256": window_sha},
        "case": producer_case,
    }
    consumer_contract = {
        "source": {"sha": "1" * 40},
        "window": {"sha256": window_sha},
        "case": common_case,
    }
    producer_contract_path = repo_root / contract_relative_path(producer_source_sha, "B0")
    producer_contract_path.parent.mkdir(parents=True)
    producer_contract_path.write_text("{}\n", encoding="utf-8")
    report = {
        "schema": "task41.p0.v6.actual_qmetric_candidate_receipt.v1",
        "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
        "identity_audit": {
            "candidate_evaluator_identity": "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
        },
        "consumer_source_sha": producer_source_sha,
        "consumer_contract_path": str(producer_contract_path),
        "consumer_contract_sha256": producer_contract_sha,
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    expected_report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()

    def require_contract(path: Path, **kwargs: object) -> tuple[dict[str, object], str]:
        assert Path(path).resolve() == producer_contract_path.resolve()
        assert kwargs["expected_sha256"] == producer_contract_sha
        assert kwargs["check_current_source"] is False
        assert kwargs["require_clean_source"] is False
        assert kwargs["case_id"] == "B0"
        return producer_contract, producer_contract_sha

    monkeypatch.setattr(checker_module, "require_task41_p0_contract", require_contract)
    if failure == "report_hash":
        with pytest.raises(ValueError, match="report SHA-256"):
            _task41_v6_candidate_producer_contract(
                report_path,
                expected_report_sha256="0" * 64,
                consumer_contract=consumer_contract,
                repo_root=repo_root,
            )
        return
    if failure == "producer_case":
        with pytest.raises(ValueError):
            _task41_v6_candidate_producer_contract(
                report_path,
                expected_report_sha256=expected_report_sha,
                consumer_contract=consumer_contract,
                repo_root=repo_root,
            )
        return

    producer, digest = _task41_v6_candidate_producer_contract(
        report_path,
        expected_report_sha256=expected_report_sha,
        consumer_contract=consumer_contract,
        repo_root=repo_root,
    )
    assert producer is producer_contract
    assert digest == producer_contract_sha
    assert producer["source"]["sha"] != consumer_contract["source"]["sha"]
    assert producer["window"]["sha256"] == consumer_contract["window"]["sha256"]


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


def test_v9_saved_star_activation_allows_only_current_b0_screen_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_sha = "a" * 40
    contract_sha = "f" * 64
    abi_sha = "d" * 64
    branch = "task41extra_phi90_p50x50_g17x20"
    model_id = "task41extra_phi90_p50x50_g17x20"
    root = tmp_path
    contract_module_path = root / "src" / "runners" / "task41_p0_contract.py"
    contract_module_path.parent.mkdir(parents=True)
    monkeypatch.setattr(task41_p0_contract, "__file__", str(contract_module_path))
    results_root = root / "results" / model_id
    report_path = results_root / "v8_report" / "task41_p0_v8_selected_trace_star_audit.json"
    checker_path = results_root / "v8_checker" / "task41_p0_b0_saved_evidence_audit.json"
    report_path.parent.mkdir(parents=True)
    checker_path.parent.mkdir(parents=True)
    report_bytes = b"frozen V8 selected-trace report"
    checker_bytes = b"frozen V8 saved-evidence checker"
    report_path.write_bytes(report_bytes)
    checker_path.write_bytes(checker_bytes)
    result_path = results_root / "v9_saved_star_attempt" / "task41_p0_b0_v9_saved_star_screen.json"
    contract_path = root / "execution_contract.json"
    contract = {
        "branch": branch,
        "source": {"sha": source_sha},
        "case": {
            "run_id": task41_p0_contract.TASK41_B0_RUN_ID,
            "model_id": model_id,
        },
        "runtime": {
            "runtime_prefix": str(Path(sys.executable).resolve().parents[1]),
            "abi_receipt_sha256": abi_sha,
        },
    }
    source_checks: list[bool] = []

    def require_contract(*_args: object, **kwargs: object) -> tuple[dict[str, object], str]:
        source_checks.append(kwargs.get("check_current_source") is True)
        return contract, contract_sha

    def consumer_source(
        _contract: object, _root: Path, *, allow_current_source: bool = False
    ) -> str:
        return source_sha if allow_current_source else "b" * 40

    monkeypatch.setattr(task41_p0_contract, "require_task41_p0_contract", require_contract)
    monkeypatch.setattr(task41_p0_contract, "_saved_output_consumer_source_sha", consumer_source)
    env = {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(contract_path),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
        "TASK41_P0_SAVED_OUTPUT_CONTINUATION": "1",
        "TASK41_P0_B0_V9_SAVED_STAR_SCREEN": "1",
        "TASK41_P0_CONSUMER_SOURCE_SHA": source_sha,
        "TASK41_P0_CHECKER_SOURCE_SHA": source_sha,
        "TASK41_P0_EXPECTED_SOURCE_SHA": source_sha,
        "TASK41_P0_B0_V9_V8_REPORT_PATH": str(report_path),
        "TASK41_P0_B0_V9_V8_REPORT_SHA256": hashlib.sha256(report_bytes).hexdigest(),
        "TASK41_P0_B0_V9_V8_CHECKER_RESULT_PATH": str(checker_path),
        "TASK41_P0_B0_V9_V8_CHECKER_RESULT_SHA256": hashlib.sha256(checker_bytes).hexdigest(),
        "TASK41_P0_B0_V9_RESULT_PATH": str(result_path),
        "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
        "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": abi_sha,
    }
    assert task41_p0_contract.qualified_activation_identity(env) == (
        f"task41_p0_native_complex:{abi_sha}"
    )
    assert source_checks == [True]

    for key, value in (
        ("TASK41_P0_B0_V9_SAVED_STAR_SCREEN", "0"),
        ("TASK41_P0_CONSUMER_SOURCE_SHA", "c" * 40),
        ("TASK41_P0_CHECKER_SOURCE_SHA", "c" * 40),
        ("TASK41_P0_B0_V9_V8_REPORT_SHA256", "e" * 64),
        ("TASK41_P0_B0_V9_RESULT_PATH", str(root / "outside" / result_path.name)),
    ):
        invalid_env = dict(env)
        invalid_env[key] = value
        assert task41_p0_contract.qualified_activation_identity(invalid_env) is None

    legacy_env = dict(env)
    legacy_env.pop("TASK41_P0_B0_V9_SAVED_STAR_SCREEN")
    assert task41_p0_contract.qualified_activation_identity(legacy_env) is None

    non_b0_contract = dict(contract)
    non_b0_contract["case"] = {"run_id": "not-task41-b0", "model_id": model_id}
    monkeypatch.setattr(
        task41_p0_contract,
        "require_task41_p0_contract",
        lambda *_args, **_kwargs: (non_b0_contract, contract_sha),
    )
    assert task41_p0_contract.qualified_activation_identity(env) is None


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


def test_v9_saved_star_selector_passes_candidate_binding_guard_without_fe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.runners.task41_p0_checker as checker_module
    import src.runners.task41_p0_contract as contract_module
    import src.runners.task40_v10_campaign as campaign_module
    import benchmarks.subreaper_watchdog as watchdog_module
    import benchmarks.task034_wsl_resources as resource_module
    import scripts.task40_v20_service_workflow as service_workflow

    repo_root = tmp_path
    results_root = repo_root / "results" / contract_module.TASK41_MODEL_ID
    report_path = results_root / "v8_saved" / "task41_p0_v8_selected_trace_star_audit.json"
    checker_result_path = (
        results_root / "v8_checker" / "task41_p0_b0_saved_evidence_audit.json"
    )
    report_path.parent.mkdir(parents=True)
    checker_result_path.parent.mkdir(parents=True)
    report_array_path = report_path.parent / "selected_star.npy"
    report_array_path.write_bytes(b"saved V8 producer array")
    checker_array_path = checker_result_path.parent / "local_rhs_lu.npy"
    checker_array_path.write_bytes(b"saved V8 checker array")

    def saved_array_entry(path: Path) -> dict[str, object]:
        data = path.read_bytes()
        return {
            "path": path.name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    report_path.write_text(
        json.dumps({
            "schema": "task41.p0.v8.selected_trace_star_audit_receipt.v1",
            "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
            "persisted_evidence_arrays": [saved_array_entry(report_array_path)],
        }),
        encoding="utf-8",
    )
    checker_result_path.write_text(
        json.dumps({
            "schema": "task41.p0.b0.saved_evidence_audit.v1",
            "status": "COMPLETE",
            "mesh_actual_exact_candidate_check": {
                "check_completed": True,
                "local_rhs_lu_counterfactual": {
                    "array_artifacts": [saved_array_entry(checker_array_path)],
                },
            },
        }),
        encoding="utf-8",
    )
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    checker_sha256 = hashlib.sha256(checker_result_path.read_bytes()).hexdigest()
    monkeypatch.setattr(checker_module, "TASK41_P0_V9_V8_REPORT_SHA256", report_sha256)
    monkeypatch.setattr(
        checker_module, "TASK41_P0_V9_V8_CHECKER_RESULT_SHA256", checker_sha256
    )

    input_path = repo_root / "b0.dat"
    input_path.write_bytes(b"frozen B0 input\n")
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    contract_path = repo_root / "task41_p0_contract.json"
    contract_path.write_text("{}\n", encoding="utf-8")
    contract_sha256 = "e" * 64
    source_sha = "c" * 40
    abi_sha = "d" * 64
    runtime_prefix = Path(sys.executable).parent.parent
    abi_receipt = repo_root / "abi.json"
    jit_cache = repo_root / "jit"
    window_sha256 = "f" * 64
    window_path = repo_root / contract_module.TASK41_B0_V9_WINDOW_RELATIVE
    window = FixedCampaignWindow(
        path=window_path,
        sha256=window_sha256,
        payload={"accounting_path": str(repo_root / "accounting.jsonl")},
        anchor={},
        t0_utc_ns=100,
        deadline_utc_ns=86_400_000_000_100,
        total_seconds=86_400.0,
        bootstrap_seconds=0.0,
        closeout_seconds=1_200.0,
    )
    contract = {
        "task_id": contract_module.TASK41_MODEL_ID,
        "branch": contract_module.TASK41_BRANCH,
        "source": {"sha": source_sha},
        "window": {
            "path": str(contract_module.TASK41_B0_V9_WINDOW_RELATIVE),
            "sha256": window_sha256,
        },
        "numerical_strategy": {
            "internal_rhs_strategy": contract_module.TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
        },
        "case": {
            "model_id": contract_module.TASK41_MODEL_ID,
            "run_id": contract_module.TASK41_B0_RUN_ID,
            "method": "full3d_iterative",
            "mpi_size": 1,
            "input_path": str(input_path),
            "input_sha256": input_sha256,
            "physical_model_sha256": "9" * 64,
            "resolved_config_sha256": "8" * 64,
        },
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {
            "runtime_prefix": str(runtime_prefix),
            "abi_receipt_path": str(abi_receipt),
            "jit_cache": str(jit_cache),
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
    monkeypatch.setenv("TASK41_P0_CONTRACT_SHA256", contract_sha256)
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_PATH", str(window.path))
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_SHA256", window_sha256)
    monkeypatch.setenv("TASK41_P0_EXPECTED_SOURCE_SHA", source_sha)

    require_contract_checks: list[bool] = []

    def require_contract(path: Path, **kwargs: object) -> tuple[dict[str, object], str]:
        assert Path(path).resolve() == contract_path.resolve()
        assert kwargs["expected_sha256"] == contract_sha256
        assert kwargs["require_clean_source"] is True
        require_contract_checks.append(bool(kwargs["check_current_source"]))
        return contract, contract_sha256

    class FakeCampaignAccount:
        def __init__(self, _window: FixedCampaignWindow) -> None:
            pass

        def record_sample(self, *, label: str, phase: str) -> dict[str, str]:
            return {"label": label, "phase": phase, "window_sha256": window_sha256}

    monkeypatch.setattr(contract_module, "require_task41_p0_contract", require_contract)
    monkeypatch.setattr(
        contract_module, "load_task41_p0_fixed_window", lambda *_args, **_kwargs: window
    )
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
    monkeypatch.setattr(
        service_workflow, "_activation_environment",
        lambda *_args, **_kwargs: (environment.copy(), ["activate"], 0, ""),
    )
    monkeypatch.setattr(
        service_workflow, "_qualified_activation_identity", lambda _environment: "fixture-activation"
    )
    monkeypatch.setattr(
        service_workflow, "_abi_preflight",
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
            contract_module.TASK41_BRANCH
            if command[-1] == "--show-current"
            else source_sha
        )
        + "\n",
    )

    def fake_git_run(command: list[str], **_kwargs: object) -> object:
        if command[1] == "status":
            stdout = ""
        elif command[1] == "rev-parse":
            stdout = source_sha + "\n"
        elif command[1] == "branch":
            stdout = contract_module.TASK41_BRANCH + "\n"
        else:
            raise AssertionError(f"unexpected Git command: {command}")
        return type("GitResult", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(service_workflow.subprocess, "run", fake_git_run)
    output_root = results_root / "v9_saved_star_screen_attempt1"
    supervise_calls: list[list[str]] = []

    def fake_supervise(
        command: list[str], _directory: Path, **kwargs: object
    ) -> dict[str, object]:
        supervise_calls.append(command)
        assert command[1:4] == [
            "-m", "src.runners.task41_p0_checker", "--v9-saved-star-screen"
        ]
        assert "run_case.py" not in command
        assert kwargs["campaign_phase"] == "closeout"
        watchdog_module._validate_campaign_closeout_authorization(
            command=command,
            campaign=window,
            authorization=kwargs["campaign_phase_authorization"],
            worker_environment=kwargs["worker_environment"],
        )
        result_path = Path(command[command.index("--output") + 1])
        result_path.write_text(
            json.dumps({
                "schema": "task41.p0.b0.v9.saved_star_screen_result.v1",
                "status": "LOCAL_CANDIDATE_REJECTED",
                "screen_completed": True,
                "local_candidate_ready": False,
                "official_result": False,
            }),
            encoding="utf-8",
        )
        return {"classification": "COMPLETED", "leader_exit_code": 0}

    monkeypatch.setattr(watchdog_module, "supervise", fake_supervise)
    monkeypatch.setattr(
        watchdog_module, "_validate_task41_consumer_source", lambda *_args, **_kwargs: True
    )
    monkeypatch.chdir(repo_root)

    assert _run_task41_p0_service(
        unit="task41-v9-saved-star-screen-test",
        runtime_prefix=runtime_prefix,
        abi_receipt=abi_receipt,
        jit_cache=jit_cache,
        case_args=[
            "--task41-p0-saved-b0-v9-star-screen",
            "--v8-report",
            str(report_path),
            "--v8-report-sha256",
            report_sha256,
            "--v8-checker-result",
            str(checker_result_path),
            "--v8-checker-result-sha256",
            checker_sha256,
            "--output",
            str(output_root / "task41_p0_b0_v9_saved_star_screen.json"),
        ],
        contract_path=contract_path,
        repo_root=repo_root,
    ) == 0
    assert len(supervise_calls) == 1
    assert require_contract_checks == [True, False]
    receipt = json.loads(
        (output_root.with_name(output_root.name + ".service") / "task41_p0_service_receipt.json")
        .read_text(encoding="utf-8")
    )
    assert receipt["status"] == "completed"
    assert receipt["mode"] == "saved_b0_v9_saved_star_screen"
    assert receipt["required_checker_status"] == "audit_completed"
    assert receipt["candidate_screen_status"] == "LOCAL_CANDIDATE_REJECTED"
    assert receipt["local_candidate_ready"] is False
    assert receipt["continuation_status"] == "v9_saved_star_screen_completed"
    assert receipt["required_checker_authorization"]["checker_kind"] == (
        "task41_p0_b0_v9_saved_star_screen_checker"
    )


@pytest.mark.parametrize(
    (
        "volume_only",
        "geometry_pair",
        "v5_mode",
        "v5_complete",
        "v6_mode",
        "v6_saved_replay",
        "v8_mode",
        "v8_saved_replay",
    ),
    [
        (False, False, False, False, False, False, False, False),
        (True, False, False, False, False, False, False, False),
        (True, True, False, False, False, False, False, False),
        (True, False, True, False, False, False, False, False),
        (True, False, True, True, False, False, False, False),
        (True, False, True, True, True, False, False, False),
        (False, False, False, False, False, True, False, False),
        (False, False, False, False, False, False, True, False),
        (False, False, False, False, False, False, False, True),
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
    v6_saved_replay: bool,
    v8_mode: bool,
    v8_saved_replay: bool,
) -> None:
    import scripts.task40_v20_service_workflow as service_workflow
    import src.runners.task41_p0_contract as contract_module
    import src.runners.task41_p0_checker as checker_module
    import src.runners.task40_v10_campaign as campaign_module
    import benchmarks.subreaper_watchdog as watchdog_module
    import benchmarks.task034_wsl_resources as resource_module
    from src.runners.task41_p0_v4_volume_only_audit import (
        TASK41_P0_V4_SELECTED_ACTIVE_ROW,
        TASK41_P0_V4_SELECTED_ORIGINAL_ROW,
        TASK41_P0_V4_SOURCE_REPORT_SHA256,
        TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
        TASK41_P0_V8_SELECTED_ACTIVE_ROW,
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
    candidate_report_path = results_root / (
        "attempt_v8_saved" if v8_saved_replay else "attempt10"
    ) / (
        "task41_p0_v8_selected_trace_star_audit.json"
        if v8_saved_replay
        else "task41_p0_v6_actual_qmetric_candidate.json"
    )
    candidate_report_sha256: str | None = None
    candidate_producer_contract_path: Path | None = None
    candidate_array_paths: list[Path] = []
    candidate_producer_contract_sha256 = "7" * 64
    candidate_producer_source_sha = "8" * 40
    candidate_producer_contract: dict[str, object] = {
        "source": {"sha": candidate_producer_source_sha},
        "window": {"sha256": window_sha},
        "case": {**common_case, "run_id": consumer_run_id},
    }
    if v6_saved_replay:
        from src.runners.task41_p0_contract import contract_relative_path

        candidate_producer_contract_path = repo_root / contract_relative_path(
            candidate_producer_source_sha, "B0"
        )
        candidate_producer_contract_path.parent.mkdir(parents=True)
        candidate_producer_contract_path.write_text(
            json.dumps(candidate_producer_contract), encoding="utf-8"
        )
        candidate_report_path.parent.mkdir(parents=True)
        evidence_dir = candidate_report_path.parent / "actual_qmetric_blocked_gram"
        evidence_dir.mkdir()
        evidence_arrays = []
        for index in range(2):
            artifact_path = evidence_dir / f"saved-array-{index}.npy"
            artifact_path.write_bytes(f"saved-array-{index}".encode())
            candidate_array_paths.append(artifact_path.resolve())
            evidence_arrays.append({
                "name": artifact_path.name,
                "path": str(artifact_path.resolve()),
                "bytes": artifact_path.stat().st_size,
                "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            })
        candidate_report = {
            "schema": "task41.p0.v6.actual_qmetric_candidate_receipt.v1",
            "status": "ACTUAL_COORDINATES_INSUFFICIENT",
            "candidate_numeric_status": "ACTUAL_COORDINATES_INSUFFICIENT",
            "geometry_policy": "mesh_actual_exact",
            "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
            "identity_audit": {
                "candidate_evaluator_identity": "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
            },
            "donor_contract_sha256": donor_contract_sha,
            "consumer_source_sha": candidate_producer_source_sha,
            "consumer_contract_path": str(candidate_producer_contract_path.resolve()),
            "consumer_contract_sha256": candidate_producer_contract_sha256,
            "geometry_reference_report_path": str(geometry_reference_path.resolve()),
            "geometry_reference_report_sha256": TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
            "persisted_evidence_arrays": evidence_arrays,
        }
        candidate_report_path.write_text(json.dumps(candidate_report), encoding="utf-8")
        candidate_report_sha256 = hashlib.sha256(candidate_report_path.read_bytes()).hexdigest()
    ffcx_c_source_path = repo_root / "frozen_ffcx_form.c"
    ffcx_c_source_path.write_text("/* frozen fixture */\n", encoding="utf-8")
    v8_source_artifacts: dict[str, object] = {}
    if v8_mode or v8_saved_replay:
        source_root = results_root / "v8_authorized_sources"
        source_root.mkdir(parents=True)
        frozen_docs_root = Path(__file__).resolve().parents[2] / "docs"
        source_index_relatives = {
            "v6_index": Path(
                "task41extra_phi90_p50x50_g17x20/outcomes/"
                "b0_v6_actual_qmetric_hash_index_20261021.json"
            ),
            "v7_index": Path(
                "task41extra_phi90_p50x50_g17x20/outcomes/"
                "b0_v7_saved_attribution_20261021.json"
            ),
        }
        source_indexes = {}
        for key, relative in source_index_relatives.items():
            destination = repo_root / "docs" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((frozen_docs_root / relative).read_bytes())
            source_indexes[key] = {
                "path": str(destination.resolve()),
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            }

        def fixture_artifact(name: str, path: Path, payload: bytes) -> dict[str, object]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            return {
                "name": name,
                "path": str(path.resolve()),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "shape": [1],
                "dtype": "float64",
            }

        v6_report = fixture_artifact("v6-report", source_root / "v6-report.json", b'{"v6_report":true}\n')
        v7_report = fixture_artifact("v7-report", source_root / "v7-report.json", b'{"v7_report":true}\n')
        v6_array = fixture_artifact("v6-array", source_root / "v6-array.npy", b"v6-authorized-array")
        v7_array = fixture_artifact("v7-array", source_root / "v7-array.npy", b"v7-authorized-array")
        v8_source_artifacts = {
            "v6_index": source_indexes["v6_index"]["path"],
            "v6_index_sha256": source_indexes["v6_index"]["sha256"],
            "v6_report": v6_report["path"],
            "v6_report_sha256": v6_report["sha256"],
            "v7_index": source_indexes["v7_index"]["path"],
            "v7_index_sha256": source_indexes["v7_index"]["sha256"],
            "v7_report": v7_report["path"],
            "v7_report_sha256": v7_report["sha256"],
            "v6_arrays": {"v6-array": v6_array},
            "v7_arrays": {"v7-array": v7_array},
        }
    if v8_saved_replay:
        from src.runners.task41_p0_contract import contract_relative_path

        candidate_producer_source_sha = "8" * 40
        candidate_producer_contract_path = repo_root / contract_relative_path(
            candidate_producer_source_sha, "B0"
        )
        candidate_producer_contract_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_producer_contract = json.loads(json.dumps(consumer_contract))
        candidate_producer_contract["source"]["sha"] = candidate_producer_source_sha
        candidate_producer_contract_path.write_text(
            json.dumps(candidate_producer_contract), encoding="utf-8"
        )
        candidate_producer_contract_sha256 = hashlib.sha256(
            candidate_producer_contract_path.read_bytes()
        ).hexdigest()
        candidate_report_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = fixture_artifact(
            "v8-saved-array",
            candidate_report_path.parent / "saved_evidence.npy",
            b"pinned-v8-saved-array",
        )
        candidate_report = {
            "schema": "task41.p0.v8.selected_trace_star_audit_receipt.v1",
            "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
            "geometry_policy": "mesh_actual_exact",
            "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
            "donor_contract_sha256": donor_contract_sha,
            "consumer_source_sha": candidate_producer_source_sha,
            "consumer_contract_path": str(candidate_producer_contract_path.resolve()),
            "consumer_contract_sha256": candidate_producer_contract_sha256,
            "persisted_evidence_arrays": [artifact],
            "selected_trace_star_audit": {
                "schema": "task41.p0.v8.selected_trace_star_audit_result.v1",
                "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
                "metadata": {"selected_original_row": 5001},
                "p3_production_row_replay": {
                    "schema": "task41.p0.v8.selected_trace_star_p3_replay.v1",
                    "complete_incident_cell_coverage": True,
                    "incident_cell_count": 1,
                },
                "saved_operand_recomposition": {"source_artifacts": v8_source_artifacts},
            },
        }
        candidate_report_path.write_text(json.dumps(candidate_report), encoding="utf-8")
        candidate_report_sha256 = hashlib.sha256(candidate_report_path.read_bytes()).hexdigest()
        monkeypatch.setattr(
            checker_module,
            "TASK41_P0_V8_LEGACY_REPORT_SHA256",
            candidate_report_sha256,
        )
        monkeypatch.setattr(
            checker_module,
            "TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA",
            candidate_producer_source_sha,
        )
        monkeypatch.setattr(
            checker_module,
            "TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256",
            candidate_producer_contract_sha256,
        )
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
            assert volume_only is True or v8_mode is True
            assert command[1:4] == ["-m", "src.runners.task41_p0_v4_volume_only_audit", "--summary"]
            if v8_mode:
                assert command[command.index("--geometry-policy") + 1] == "mesh_actual_exact"
                assert command[command.index("--raw-tensor-evaluator") + 1] == "actual_qmetric_blocked_gram"
                assert Path(command[command.index("--ffcx-c-source") + 1]) == ffcx_c_source_path
                assert "--selected-trace-star-audit" in command
                array_record = fixture_artifact(
                    "v8-array",
                    output_root / "v8_evidence" / "selected_local.npy",
                    b"v8-authorized-array",
                )
                incident_cell = 103
                selected_star = {
                    "schema": "task41.p0.v8.selected_trace_star_audit_result.v1",
                    "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
                    "selected_active_row": TASK41_P0_V8_SELECTED_ACTIVE_ROW,
                    "metadata": {
                        "selected_original_row": 5001,
                        "incident_cell_order": [incident_cell],
                    },
                    "local_numeric_cell_identity_and_artifacts": [
                        {
                            "cell_index": incident_cell,
                            "is_target_row_incident": True,
                            "roles": [
                                {"role": "candidate", "source": "RECONSTRUCTED_SELECTED_CELL"},
                                {"role": "reference", "source": "RECONSTRUCTED_SELECTED_CELL"},
                            ],
                        }
                    ],
                    "p0_prefix_four_matrix_defects_and_state_actions": [{} for _ in range(8)],
                    "p3_production_row_replay": {
                        "schema": "task41.p0.v8.selected_trace_star_p3_replay.v1",
                        "complete_incident_cell_coverage": True,
                        "incident_cell_count": 1,
                    },
                    "saved_operand_recomposition": {"source_artifacts": v8_source_artifacts},
                }
                volume_result = output_root / "task41_p0_v8_selected_trace_star_audit.json"
                volume_result.write_text(
                    json.dumps({
                        "schema": "task41.p0.v8.selected_trace_star_audit_receipt.v1",
                        "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
                        "geometry_policy": "mesh_actual_exact",
                        "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
                        "donor_contract_sha256": donor_contract_sha,
                        "consumer_contract_sha256": consumer_contract_sha,
                        "independent_checker_status": "NOT_RUN",
                        "selected_trace_star_audit": selected_star,
                        "persisted_evidence_arrays": [array_record],
                    }),
                    encoding="utf-8",
                )
            elif geometry_pair:
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
        if v8_mode or v8_saved_replay:
            report_path = (
                candidate_report_path
                if v8_saved_replay
                else output_root / "task41_p0_v8_selected_trace_star_audit.json"
            )
            assert Path(command[command.index("--mesh-actual-exact-report") + 1]) == report_path
            assert command[command.index("--mesh-actual-exact-report-sha256") + 1] == (
                candidate_report_sha256
                if v8_saved_replay
                else hashlib.sha256(report_path.read_bytes()).hexdigest()
            )
            assert "--geometry-reference-report" not in command
            assert Path(command[command.index("--consumer-contract") + 1]) == consumer_contract_path
            assert command[command.index("--consumer-contract-sha256") + 1] == consumer_contract_sha
        if v6_saved_replay:
            assert command[command.index("--mesh-actual-exact-report") + 1] == str(candidate_report_path)
            assert command[command.index("--mesh-actual-exact-report-sha256") + 1] == candidate_report_sha256
        elif v5_complete:
            assert command[command.index("--mesh-actual-exact-report") + 1] == str(
                output_root
                / (
                    "task41_p0_v6_actual_qmetric_candidate.json"
                    if v6_mode
                    else "task41_p0_v5_mesh_actual_exact_attribution.json"
                )
            )
            assert "--mesh-actual-exact-report-sha256" in command
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
            } if v5_complete or v6_saved_replay or v8_mode or v8_saved_replay else {}),
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
        if v8_saved_replay and Path(path).resolve() == candidate_producer_contract_path.resolve():
            assert kwargs["expected_sha256"] == candidate_producer_contract_sha256
            assert kwargs["check_current_source"] is False
            assert kwargs["require_clean_source"] is False
            return candidate_producer_contract, candidate_producer_contract_sha256
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
    monkeypatch.setattr(checker_module, "require_task41_p0_contract", require_contract)
    if v6_saved_replay:
        def fake_candidate_producer_contract(
            report_path: Path,
            *,
            expected_report_sha256: str,
            consumer_contract: dict[str, object],
            repo_root: Path,
        ) -> tuple[dict[str, object], str]:
            assert Path(report_path).resolve() == candidate_report_path.resolve()
            assert expected_report_sha256 == candidate_report_sha256
            assert consumer_contract.get("source", {}).get("sha") == consumer_source_sha
            assert Path(repo_root).resolve() == tmp_path.resolve()
            return candidate_producer_contract, candidate_producer_contract_sha256

        monkeypatch.setattr(
            checker_module,
            "_task41_v6_candidate_producer_contract",
            fake_candidate_producer_contract,
        )
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
                "--task41-p0-saved-b0-selected-trace-star-audit"
                if v8_mode
                else "--task41-p0-saved-b0-volume-only-attribution"
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
            *( [
                "--mesh-actual-exact-report",
                str(candidate_report_path),
                "--mesh-actual-exact-report-sha256",
                str(candidate_report_sha256),
            ] if v6_saved_replay or v8_saved_replay else [] ),
            *( [
                "--geometry-policy", "mesh_actual_exact",
                "--raw-tensor-evaluator", "actual_qmetric_blocked_gram",
                "--ffcx-c-source", str(ffcx_c_source_path),
                "--selected-trace-star-audit",
            ] if v8_mode else [] ),
        ],
        contract_path=consumer_contract_path,
        repo_root=repo_root,
    )

    receipt = json.loads((output_root.with_name(output_root.name + ".service") / "task41_p0_service_receipt.json").read_text())
    assert result == (3 if v5_mode else 0), receipt.get("workflow_error")
    expected_calls = 2 if v8_mode else 1 if not volume_only or (v5_mode and not v5_complete) else 2
    assert len(calls) == expected_calls
    if volume_only or v8_mode:
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
        "saved_b0_v8_selected_trace_star_checker"
        if v8_saved_replay
        else
        "saved_b0_v8_selected_trace_star_audit"
        if v8_mode
        else "saved_b0_v6_candidate_evidence_audit"
        if v6_saved_replay
        else "saved_b0_v6_actual_qmetric_candidate"
        if v6_mode
        else "saved_b0_v5_mesh_actual_exact_candidate"
        if v5_mode
        else "saved_b0_v4_geometry_pair_probe"
        if geometry_pair
        else "saved_b0_v4_volume_only_attribution"
        if volume_only
        else "saved_b0_evidence_audit"
    )
    if v8_mode:
        assert receipt["continuation_status"] == "v8_selected_trace_star_audit_completed"
        assert receipt["selected_trace_star_checker_status"] == "independent_replay_completed"
        assert receipt["candidate_numerical_passed"] is None
        authorization = calls[1][1]["campaign_phase_authorization"]
        authorized = set(authorization["input_paths"])
        for key in ("v6_index", "v6_report", "v7_index", "v7_report"):
            assert v8_source_artifacts[key] in authorized
        for key in ("v6_arrays", "v7_arrays"):
            for artifact in v8_source_artifacts[key].values():
                assert artifact["path"] in authorized
    if v8_saved_replay:
        assert len(calls) == 1
        assert calls[0][1]["campaign_phase"] == "closeout"
        assert "volume_only_command" not in receipt
        assert "volume_only_watchdog" not in receipt
        assert receipt["candidate_report_replayed_read_only"] is True
        assert receipt["candidate_report_sha256"] == candidate_report_sha256
        assert receipt["selected_trace_star_checker_status"] == "independent_replay_completed"
        assert receipt["continuation_status"] == "v8_selected_trace_star_audit_completed"
        auth_inputs = receipt["required_checker_authorization"]["input_paths"]
        for bound_path in [
            candidate_report_path,
            candidate_producer_contract_path,
            *candidate_array_paths,
            *(
                [Path(v8_source_artifacts[key]) for key in ("v6_index", "v6_report", "v7_index", "v7_report")]
                + [Path(item["path"]) for group in ("v6_arrays", "v7_arrays") for item in v8_source_artifacts[group].values()]
            ),
        ]:
            assert bound_path.resolve().as_posix() in auth_inputs
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
    if v6_saved_replay:
        assert calls[0][1]["campaign_phase"] == "closeout"
        assert calls[0][0][1:4] == ["-m", "src.runners.task41_p0_checker", "--saved-b0-evidence-audit"]
        assert not any(
            marker in " ".join(calls[0][0]).lower()
            for marker in ("run_case.py", "volume_only_audit", "owner", "evaluator", "carrier", "factor")
        )
        assert "volume_only_command" not in receipt
        assert "volume_only_watchdog" not in receipt
        assert receipt["candidate_report_replayed_read_only"] is True
        assert receipt["candidate_report_sha256"] == candidate_report_sha256
        assert receipt["candidate_checker_status"] == "numerical_fail"
        assert receipt["candidate_numerical_passed"] is False
        assert receipt["continuation_status"] == "v6_saved_candidate_audit_completed"
        auth_inputs = receipt["required_checker_authorization"]["input_paths"]
        for bound_path in [candidate_report_path, candidate_producer_contract_path, *candidate_array_paths]:
            assert bound_path.resolve().as_posix() in auth_inputs
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


@pytest.mark.parametrize("wrong_donor", [False, True])
def test_v9_failed_terminal_audit_is_routed_through_saved_task41_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong_donor: bool
) -> None:
    import scripts.task40_v20_service_workflow as service_workflow
    import src.runners.task41_p0_contract as contract_module
    import src.runners.task40_v10_campaign as campaign_module
    import benchmarks.task034_wsl_resources as resource_module

    repo_root = tmp_path
    results_root = repo_root / "results" / contract_module.TASK41_MODEL_ID
    input_path = repo_root / "b0.dat"
    input_path.write_bytes(b"fixture B0 input\n")
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    runtime_prefix = repo_root / "runtime"
    abi_receipt = repo_root / "abi.json"
    jit_cache = repo_root / "jit"
    abi_receipt.write_text("{}\n", encoding="utf-8")
    run_root = (
        results_root
        / "task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna"
        / "20261022T052401.200732Z"
    )
    run_root.mkdir(parents=True)
    manifest_path = run_root / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "output_directory": str(run_root.resolve()),
                "numerical_output_directory": str((run_root / "numerical_output").resolve()),
            }
        ) + "\n",
        encoding="utf-8",
    )
    summary_path = run_root / "task40_v10_p6_candidate_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "b0_v9_compact_volume_audit": {},
                "b0_v9_independent_check": {},
            }
        ) + "\n",
        encoding="utf-8",
    )
    run_summary_path = run_root / "run_summary.json"
    run_summary_path.write_text("{}\n", encoding="utf-8")
    producer_contract_path = repo_root / "producer_contract.json"
    producer_contract_path.write_text("{}\n", encoding="utf-8")
    consumer_contract_path = repo_root / "consumer_contract.json"
    consumer_contract_path.write_text("{}\n", encoding="utf-8")
    source_sha = "c" * 40
    contract_sha = "f" * 64
    window_sha = "e" * 64
    v9_window_path = repo_root / contract_module.TASK41_B0_V9_WINDOW_RELATIVE
    saved_window_path = repo_root / contract_module.TASK41_B0_SAVED_DIAGNOSTICS_WINDOW_RELATIVE
    output_root = results_root / "task41_p0_saved_diagnostics_6h" / window_sha / "v9_failed_terminal_audit"
    contract_case = {
        "model_id": contract_module.TASK41_MODEL_ID,
        "run_id": contract_module.TASK41_B0_RUN_ID,
        "method": "full3d_iterative",
        "mpi_size": 1,
        "input_path": str(input_path),
        "input_sha256": input_sha,
        "physical_model_sha256": "9" * 64,
        "resolved_config_sha256": "8" * 64,
        "profile_identity": contract_module.TASK41_B0_PRECONDITIONER,
        "solver_stage": "TASK41_B0",
        "comparison_group": contract_module.TASK41_B0_COMPARISON_GROUP,
        "geometry_identity": "fixture-geometry",
    }
    base_contract = {
        "task_id": contract_module.TASK41_MODEL_ID,
        "branch": contract_module.TASK41_BRANCH,
        "source": {"sha": source_sha},
        "window": {"path": str(v9_window_path), "sha256": window_sha},
        "case": dict(contract_case),
        "numerical_strategy": {"internal_rhs_strategy": "same_lu_rhs_solve"},
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {
            "runtime_prefix": str(runtime_prefix),
            "abi_receipt_path": str(abi_receipt),
            "jit_cache": str(jit_cache),
            "abi_receipt_sha256": "d" * 64,
        },
    }
    producer_contract = json.loads(json.dumps(base_contract))
    producer_contract["window"]["sha256"] = "b" * 64
    consumer_contract = json.loads(json.dumps(base_contract))
    consumer_contract["source"]["sha"] = source_sha
    consumer_contract["window"] = {
        "path": str(saved_window_path),
        "sha256": window_sha,
        "entry_source_sha": source_sha,
        "scope": contract_module.TASK41_B0_SAVED_DIAGNOSTICS_SCOPE,
        "authorization_sha256": "9" * 64,
    }
    consumer_contract["execution_scope"] = contract_module.TASK41_B0_SAVED_DIAGNOSTICS_SCOPE
    if wrong_donor:
        producer_contract["case"]["input_sha256"] = "0" * 64
    producer_sha = "a" * 64

    class FakeWindow:
        path = saved_window_path
        sha256 = window_sha
        accounting_path = repo_root / "accounting.jsonl"
        closeout_seconds = 1200.0

    class FakeAccount:
        def __init__(self, _window):
            pass

        def record_sample(self, **_kwargs):
            return {"recorded": True}

    def require_contract(path, **_kwargs):
        return (
            (producer_contract, producer_sha)
            if Path(path) == producer_contract_path
            else (consumer_contract, contract_sha)
        )

    monkeypatch.setattr(contract_module, "require_task41_p0_contract", require_contract)
    monkeypatch.setattr(
        contract_module,
        "load_task41_p0_fixed_window",
        lambda *_args, **_kwargs: FakeWindow(),
    )
    monkeypatch.setattr(campaign_module, "CampaignAccount", FakeAccount)
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
    thread_environment = {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    monkeypatch.setattr(
        service_workflow,
        "_activation_environment",
        lambda *_args, **_kwargs: (thread_environment.copy(), ["activate"], 0, ""),
    )
    monkeypatch.setattr(service_workflow, "_qualified_activation_identity", lambda _env: "qualified")
    monkeypatch.setattr(
        service_workflow,
        "_abi_preflight",
        lambda *_args: (["preflight"], 0, json.dumps({
            "scalar_type": "complex128", "int_type": "int32", "mpi_size": 1
        }), ""),
    )
    captured: dict[str, object] = {}

    def capture_saved_service(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        service_workflow, "_run_task41_p0_saved_output_service", capture_saved_service
    )
    monkeypatch.setattr(
        service_workflow.subprocess,
        "check_output",
        lambda command, **_kwargs: (
            contract_module.TASK41_BRANCH
            if command[1] == "branch"
            else source_sha
        ),
    )
    monkeypatch.setenv("TASK41_P0_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK41_P0_CONTRACT_PATH", str(consumer_contract_path))
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_PATH", str(FakeWindow.path))
    monkeypatch.setenv("TASK41_P0_EXECUTION_WINDOW_SHA256", window_sha)
    monkeypatch.setenv("TASK41_P0_EXPECTED_SOURCE_SHA", source_sha)

    def run_service() -> int:
        return _run_task41_p0_service(
            unit="myfenics-case-fixture.service",
            runtime_prefix=runtime_prefix,
            abi_receipt=abi_receipt,
            jit_cache=jit_cache,
            case_args=[
                "--task41-p0-saved-b0-v9-failed-terminal-audit",
                "--producer-contract", str(producer_contract_path),
                "--producer-contract-sha256", producer_sha,
                "--run-root", str(run_root),
                "--summary", str(summary_path),
                "--manifest", str(manifest_path),
                "--output-dir", str(output_root),
            ],
            contract_path=consumer_contract_path,
            repo_root=repo_root,
        )

    if wrong_donor:
        with pytest.raises(ValueError, match="V9 producer and current consumer contracts differ in B0 identity"):
            run_service()
        assert captured == {}
        assert not output_root.exists()
        return

    result = run_service()
    assert result == 0
    assert captured["b0_v9_failed_terminal_audit_mode"] is True
    assert captured["checker_only"] is True
    assert captured["run_root"] == run_root
    assert captured["v9_terminal_manifest_path"] == manifest_path
    assert captured["v9_terminal_summary_path"] == summary_path
    assert captured["v9_terminal_producer_contract_path"] == producer_contract_path
    assert captured["contract"] is consumer_contract
    assert not (run_root / "numerical_output").exists()


def test_v9_failed_terminal_saved_service_completes_negative_audit_without_numeric_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.task40_v20_service_workflow as service_workflow
    import src.runners.task41_p0_contract as contract_module
    from src.runners import task41_p0_checker as checker_module
    from src.solvers import task41_v4_volume_only_audit as v4_audit
    from src.geometry.task41_phi90_profile import TASK41_B0_GEOMETRY_IDENTITY
    from src.test.test_task41_v4_volume_only_audit import (
        _task41_v9_compact_terminal_fixture,
    )

    monkeypatch.setattr(checker_module, "TASK41_P0_B0_SAVED_Y_G_SHAPE", (4, 2))
    repo_root = tmp_path / "fixture-repo"
    repo_root.mkdir()
    service_workflow.subprocess.run(
        ["git", "init", "-b", contract_module.TASK41_BRANCH],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    service_workflow.subprocess.run(
        ["git", "config", "user.email", "fixture@example.invalid"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    service_workflow.subprocess.run(
        ["git", "config", "user.name", "Task41 test fixture"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    (repo_root / "source_identity.txt").write_text("frozen fixture source\n", encoding="utf-8")
    service_workflow.subprocess.run(
        ["git", "add", "source_identity.txt"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    )
    service_workflow.subprocess.run(
        ["git", "commit", "-m", "fixture source identity"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    )
    consumer_source_sha = service_workflow.subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
    ).strip()
    model_id = contract_module.TASK41_MODEL_ID
    results_root = repo_root / "results" / model_id
    input_path = repo_root / "b0.dat"
    input_path.write_bytes(b"fixture DAT\n")
    checker, candidate_summary, _numerical_output, identity_path = (
        _task41_v9_compact_terminal_fixture(
            tmp_path,
            monkeypatch,
            action_passes=False,
            missing_numerical_output=True,
            service_repo_root=repo_root,
        )
    )
    run_root = identity_path.parent
    assert not (run_root / "numerical_output").exists()
    summary_path = run_root / "task40_v10_p6_candidate_summary.json"
    manifest_path = run_root / "run_manifest.json"
    run_summary_path = run_root / "run_summary.json"
    copied_input_path = run_root / "input_original.dat"
    resolved_config_path = run_root / "resolved_config.json"
    copied_input_path.write_bytes(input_path.read_bytes())
    resolved_config_path.write_text('{"resolved":true}\n', encoding="utf-8")
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    resolved_sha = hashlib.sha256(resolved_config_path.read_bytes()).hexdigest()
    physical_sha = "9" * 64
    window_path = repo_root / contract_module.TASK41_B0_V9_WINDOW_RELATIVE
    window_path.parent.mkdir(parents=True, exist_ok=True)
    window_path.write_text('{"fixture_window":true}\n', encoding="utf-8")
    window_sha = hashlib.sha256(window_path.read_bytes()).hexdigest()
    producer_source_sha = "a" * 40
    producer_contract_path = repo_root / "producer_contract.json"
    consumer_contract_path = repo_root / "consumer_contract.json"
    runtime_prefix = repo_root / "runtime"
    (runtime_prefix / "bin").mkdir(parents=True)
    (runtime_prefix / "bin" / "python").write_text("fixture python\n", encoding="utf-8")
    abi_receipt_path = repo_root / "abi.json"
    abi_receipt_path.write_text("{}\n", encoding="utf-8")
    jit_cache = repo_root / "jit"
    jit_cache.mkdir()
    case_spec = contract_module._task41_case("B0")
    common_case = {
        "model_id": model_id,
        "run_id": contract_module.TASK41_B0_RUN_ID,
        "method": case_spec["method"],
        "mpi_size": 1,
        "input_path": str(input_path.resolve()),
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "profile_identity": case_spec["profile_identity"],
        "solver_stage": case_spec["solver_stage"],
        "comparison_group": case_spec["comparison_group"],
        "geometry_identity": TASK41_B0_GEOMETRY_IDENTITY,
    }
    producer_contract = {
        "task_id": model_id,
        "branch": contract_module.TASK41_BRANCH,
        "source": {"sha": producer_source_sha},
        "window": {"path": str(window_path), "sha256": window_sha},
        "numerical_strategy": {
            "schema": "task41.p0.b0.internal_rhs_strategy.v1",
            "internal_rhs_strategy": "same_lu_rhs_solve",
        },
        "case": dict(common_case),
    }
    consumer_contract = {
        "task_id": model_id,
        "branch": contract_module.TASK41_BRANCH,
        "source": {"sha": consumer_source_sha},
        "window": {"path": str(window_path), "sha256": window_sha},
        "numerical_strategy": {
            "schema": "task41.p0.b0.internal_rhs_strategy.v1",
            "internal_rhs_strategy": "same_lu_rhs_solve",
        },
        "case": dict(common_case),
    }
    producer_contract_path.write_text(json.dumps(producer_contract), encoding="utf-8")
    consumer_contract_path.write_text(json.dumps(consumer_contract), encoding="utf-8")
    producer_contract_sha = hashlib.sha256(producer_contract_path.read_bytes()).hexdigest()
    consumer_contract_sha = hashlib.sha256(consumer_contract_path.read_bytes()).hexdigest()

    def require_contract(path, *, expected_sha256, **_kwargs):
        path = Path(path).resolve()
        expected = {
            producer_contract_path.resolve(): (producer_contract, producer_contract_sha),
            consumer_contract_path.resolve(): (consumer_contract, consumer_contract_sha),
        }
        contract, digest = expected[path]
        assert expected_sha256 == digest
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        return contract, digest

    monkeypatch.setattr(checker, "require_task41_p0_contract", require_contract)
    candidate_summary.update(run_id=contract_module.TASK41_B0_RUN_ID, source_sha=producer_source_sha)
    candidate_summary["campaign_authority"] = {
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "case_id": "B0",
        "task41_contract_path": str(producer_contract_path.resolve()),
        "task41_contract_sha256": producer_contract_sha,
        "source_sha": producer_source_sha,
        "campaign_window_path": str(window_path.resolve()),
        "campaign_window_sha256": window_sha,
    }
    summary_path.write_text(
        json.dumps(candidate_summary, sort_keys=True, allow_nan=False), encoding="utf-8"
    )
    manifest = {
        "model_id": model_id,
        "run_id": contract_module.TASK41_B0_RUN_ID,
        "method": case_spec["method"],
        "mpi_size": 1,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "source_sha": producer_source_sha,
        "output_directory": str(run_root.resolve()),
        "numerical_output_directory": str((run_root / "numerical_output").resolve()),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    run_summary_path.write_text(json.dumps({
        "run_id": contract_module.TASK41_B0_RUN_ID,
        "output_directory": str(run_root.resolve()),
        "numerical_output_directory": str((run_root / "numerical_output").resolve()),
    }), encoding="utf-8")
    assert checker_module.select_task41_p0_b0_v9_failed_terminal_audit_route(
        contract=producer_contract,
        run_case_returncode=7,
        run_root=run_root,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output_path=run_root / "numerical_output",
        repo_root=repo_root,
    ) == "v9_failed_terminal_audit"
    assert checker_module.select_task41_p0_b0_v9_failed_terminal_audit_route(
        contract=producer_contract,
        run_case_returncode=0,
        run_root=run_root,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output_path=run_root / "numerical_output",
        repo_root=repo_root,
    ) == "ordinary"
    assert checker_module.select_task41_p0_b0_v9_failed_terminal_audit_route(
        contract=producer_contract,
        run_case_returncode=None,
        explicit_saved_terminal=True,
        run_root=run_root,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output_path=run_root / "numerical_output",
        repo_root=repo_root,
    ) == "v9_failed_terminal_audit"
    output_root = results_root / "task41_p0_saved_diagnostics_6h" / window_sha / "v9_failed_terminal_audit"
    window = FixedCampaignWindow(
        path=window_path,
        sha256=window_sha,
        payload={"accounting_path": str(repo_root / "accounting.jsonl")},
        anchor={},
        t0_utc_ns=1,
        deadline_utc_ns=2,
        total_seconds=86400.0,
        bootstrap_seconds=0.0,
        closeout_seconds=1200.0,
    )
    contract = {
        "task_id": model_id,
        "branch": contract_module.TASK41_BRANCH,
        "source": {"sha": consumer_source_sha},
        "window": {"sha256": window.sha256},
        "case": dict(common_case),
        "resources": {
            "task_memory_max_bytes": 1 << 30,
            "host_reserve_bytes": 1 << 28,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {
            "runtime_prefix": str(runtime_prefix),
            "abi_receipt_path": str(abi_receipt_path),
            "abi_receipt_sha256": hashlib.sha256(abi_receipt_path.read_bytes()).hexdigest(),
            "jit_cache": str(jit_cache),
        },
    }
    commands: list[list[str]] = []
    checker_authorizations: list[dict[str, object]] = []

    def fake_supervise(command, *_args, **kwargs):
        commands.append(list(command))
        authorization = kwargs["campaign_phase_authorization"]
        checker_authorizations.append(dict(authorization))
        return_code = checker.main(command[3:])
        return {
            "classification": "COMPLETED" if return_code == 0 else "FAILED",
            "leader_exit_code": return_code,
        }

    def require_contract_for_checker(path, *, expected_sha256, **kwargs):
        path = Path(path).resolve()
        if path == producer_contract_path.resolve():
            return require_contract(path, expected_sha256=expected_sha256, **kwargs)
        return require_contract(path, expected_sha256=expected_sha256, **kwargs)

    monkeypatch.setattr(checker, "require_task41_p0_contract", require_contract_for_checker)
    result = service_workflow._run_task41_p0_saved_output_service(
        unit="myfenics-case-v9-audit.service",
        runtime_prefix=runtime_prefix,
        environment={"TASK41_P0_CHECKER_SOURCE_SHA": consumer_source_sha},
        window=window,
        contract=contract,
        contract_path=consumer_contract_path,
        contract_sha=consumer_contract_sha,
        case_id="B0",
        run_root=run_root,
        output_root=output_root,
        consumer_source_sha=consumer_source_sha,
        checker_only=True,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        b0_v9_failed_terminal_audit_mode=True,
        v9_terminal_producer_contract_path=producer_contract_path,
        v9_terminal_producer_contract_sha256=producer_contract_sha,
        v9_terminal_summary_path=summary_path,
        v9_terminal_manifest_path=run_root / "run_manifest.json",
        input_path=input_path,
        activation_command=["activate"],
        activation_identity="qualified",
        preflight={"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1},
        preflight_command=["preflight"],
        cgroup_start={"memory_current_bytes": 1},
        service_entry_accounting={"recorded": True},
        service_start_sample=clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=contract_module.sha256_file,
    )

    receipt = json.loads(
        (output_root.with_name(output_root.name + ".service") / "task41_p0_service_receipt.json")
        .read_text(encoding="utf-8")
    )
    assert result == 0
    assert len(commands) == 1
    assert "--v9-failed-terminal-audit" in commands[0]
    assert "--run-root" in commands[0]
    assert "--numerical-output" not in commands[0]
    assert receipt["status"] == "completed"
    assert receipt["required_checker_status"] == "audit_completed"
    assert receipt["result_classification"] == "SUPERVISED_NEGATIVE_RESULT_AUDIT_COMPLETED"
    assert receipt["action_passed"] is False
    assert receipt["recovery_status"] == "NOT_RUN_ACTION_GATE_FAILED"
    assert receipt["official_result"] is False

    # Reuse this fixture's producer, consumer, window, ABI, and watchdog setup
    # to exercise the saved-vector route through the real checker CLI.
    scope = contract_module.TASK41_B0_SAVED_DIAGNOSTICS_SCOPE
    consumer_contract["execution_scope"] = scope
    consumer_contract["evidence"] = {
        "raw_disk_policy": {
            "scope": "task41_b0_v3_recovery_evidence",
            "raw_artifact_limit_bytes": 16 << 30,
            "free_space_floor_bytes": 2 << 30,
            "authorization": "user_20261019_16gib_evidence_only",
            "new_evidence_limit_bytes": task41_p0_contract.TASK41_B0_SAVED_DIAGNOSTICS_NEW_EVIDENCE_LIMIT_BYTES,
        }
    }
    consumer_contract_path.write_text(json.dumps(consumer_contract), encoding="utf-8")
    consumer_contract_sha = hashlib.sha256(consumer_contract_path.read_bytes()).hexdigest()
    contract["execution_scope"] = scope
    contract["evidence"] = consumer_contract["evidence"]

    producer_service_dir = run_root / "v9_producer.service"
    producer_service_dir.mkdir()
    producer_contract["evidence"] = {"service_directory": str(producer_service_dir.resolve())}
    producer_contract_path.write_text(json.dumps(producer_contract), encoding="utf-8")
    producer_contract_sha = hashlib.sha256(producer_contract_path.read_bytes()).hexdigest()

    v9_report = json.loads(identity_path.read_text(encoding="utf-8"))
    donor_run = repo_root / contract_module.TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE
    donor_run.mkdir(parents=True, exist_ok=True)
    donor_arrays_root = donor_run / "mini_arrays"
    donor_arrays_root.mkdir()

    def save_donor_array(name: str, array: np.ndarray) -> dict[str, object]:
        path = donor_arrays_root / name
        np.save(path, array, allow_pickle=False)
        file_bytes = path.read_bytes()
        return {
            "path": str(path.relative_to(donor_run)),
            "bytes": len(file_bytes),
            "sha256": hashlib.sha256(file_bytes).hexdigest(),
            "array_sha256": hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest(),
            "shape": list(array.shape),
            "dtype": str(array.dtype),
        }

    donor_columns = []
    donor_inputs = []
    donor_payload_paths: set[str] = set()
    input_hash_fields = (
        "probe_values_sha256", "active_original_rows_sha256", "mapped_active_rows_sha256",
        "interior_rows_sha256", "interior_values_sha256", "raw_slave_rows_sha256",
        "raw_slave_values_sha256",
    )
    for column in range(2):
        artifacts = {
            "active_original_rows": save_donor_array(
                f"column_{column}_active.npy", np.array([10, 11], dtype=np.int64)
            ),
            "slave_rows": save_donor_array(
                f"column_{column}_slaves.npy", np.array([0, 1, 12], dtype=np.int64)
            ),
            "known_field": save_donor_array(
                f"column_{column}_known.npy",
                np.arange(13, dtype=np.float64).astype(np.complex128) + 1j * column,
            ),
            "native_rhs": save_donor_array(
                f"column_{column}_rhs.npy", np.zeros(13, dtype=np.complex128)
            ),
            "native_volume_rhs": save_donor_array(
                f"column_{column}_volume_rhs.npy", np.ones(13, dtype=np.complex128)
            ),
            "b_alpha_rows": save_donor_array(
                f"column_{column}_b_alpha_rows.npy", np.array([0], dtype=np.int64)
            ),
            "b_alpha_values": save_donor_array(
                f"column_{column}_b_alpha_values.npy", np.array([1 + 2j], dtype=np.complex128)
            ),
            "selected_B_frame_rows": save_donor_array(
                f"column_{column}_selected_B_rows.npy", np.array([0, 1], dtype=np.int64)
            ),
            "selected_B_frame_values": save_donor_array(
                f"column_{column}_selected_B_values.npy",
                np.array([0.5 + 0.25j, 1.5 - 0.75j], dtype=np.complex128),
            ),
        }
        donor_payload_paths.update(
            str((donor_run / record["path"]).resolve()) for record in artifacts.values()
        )
        donor_columns.append({"column": column, "mode_index": column, "artifacts": artifacts})
        donor_inputs.append({
            "mode_index": column,
            "mode_key": [column, 0],
            "probe_rows": 3,
            "active_trace_rows": 1,
            "cell_interior_rows": 1,
            "mpc_slave_rows": 1,
            **{name: f"{column + 1:064x}" for name in input_hash_fields},
            "port_alpha": [float(column + 1), float(column) / 4.0],
        })
    donor_manifest = {
        "schema": "task41.p0.b0.recovery_evidence.v1",
        "full_storage_rows": 13,
        "active_trace_rows": 2,
        "port_rows": 2,
        "columns": donor_columns,
        "input_identities": donor_inputs,
    }
    donor_manifest_path = donor_run / "task41_b0_recovery_manifest.json"
    donor_summary_path = donor_run / "task40_v10_p6_candidate_summary.json"
    donor_summary = json.loads(donor_summary_path.read_text(encoding="utf-8"))

    def write_mini_donor_manifest(manifest_payload: dict[str, object]) -> str:
        donor_manifest_path.write_text(
            json.dumps(manifest_payload, sort_keys=True), encoding="utf-8"
        )
        manifest_bytes = donor_manifest_path.read_bytes()
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        donor_summary["b0_recovery_evidence"] = {
            "manifest": {
                "path": str(donor_manifest_path.relative_to(donor_run)),
                "bytes": len(manifest_bytes),
                "sha256": digest,
            }
        }
        donor_summary_path.write_text(json.dumps(donor_summary, sort_keys=True), encoding="utf-8")
        monkeypatch.setattr(v4_audit, "TASK41_V4_DONOR_MANIFEST_SHA256", digest)
        return digest

    mini_donor_manifest_sha = write_mini_donor_manifest(donor_manifest)
    v9_report["donor_manifest_sha256"] = mini_donor_manifest_sha
    v9_report_path = run_root / "task41_p0_b0_v9_compact_volume_audit.json"
    v9_report_path.write_text(json.dumps(v9_report), encoding="utf-8")
    v9_report_sha = hashlib.sha256(v9_report_path.read_bytes()).hexdigest()
    v9_summary_path = run_root / "task40_v10_p6_candidate_summary.json"
    v9_summary_path.write_text(json.dumps({
        "run_id": contract_module.TASK41_B0_RUN_ID,
        "status": "finished",
        "result_classification": "WORKER_FAILED",
        "output_directory": str(run_root.resolve()),
    }), encoding="utf-8")
    v9_summary_sha = hashlib.sha256(v9_summary_path.read_bytes()).hexdigest()
    v9_receipt_path = producer_service_dir / "task41_p0_service_receipt.json"
    v9_receipt_path.write_text(json.dumps({
        "schema": "task41.p0.service_receipt.v1",
        "case_id": "B0",
        "run_case_returncode": 7,
        "contract_path": str(producer_contract_path.resolve()),
        "contract_sha256": producer_contract_sha,
        "source_sha": producer_source_sha,
    }), encoding="utf-8")
    v9_receipt_sha = hashlib.sha256(v9_receipt_path.read_bytes()).hexdigest()

    v6_source_sha = "f" * 40
    v6_contract_path = repo_root / "v6_producer_contract.json"
    v6_contract = {**producer_contract, "source": {"sha": v6_source_sha}}
    v6_contract_path.write_text(json.dumps(v6_contract), encoding="utf-8")
    v6_contract_sha = hashlib.sha256(v6_contract_path.read_bytes()).hexdigest()
    v6_run = results_root / "v6_saved_y_g_fixture"
    v6_run.mkdir()
    v6_arrays = {}
    for name, values in {
        "v6_y": np.array([[1 + 1j, 2], [2, 1 + 1j], [3, 2 + 1j], [1 + 2j, 4]]),
        "v6_g": np.array([[1j, 1], [1, 1j], [2, 1], [2j, 2]]),
    }.items():
        array_path = v6_run / f"{name}.npy"
        np.save(array_path, np.asarray(values, dtype=np.complex128), allow_pickle=False)
        data = array_path.read_bytes()
        v6_arrays[name] = {
            "name": name,
            "path": str(array_path.resolve()),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "dtype": "complex128",
            "shape": [4, 2],
        }
    v9_gate = v9_report["candidate_full_action_gate"]
    cache_identity = v9_report["candidate_evaluator_cache_identity"]
    v6_report_path = v6_run / "task41_p0_v6_actual_qmetric_candidate.json"
    v6_report_path.write_text(json.dumps({
        "schema": "task41.p0.v6.actual_qmetric_candidate_receipt.v1",
        "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
        "geometry_policy": "mesh_actual_exact",
        "consumer_source_sha": v6_source_sha,
        "consumer_contract_path": str(v6_contract_path.resolve()),
        "consumer_contract_sha256": v6_contract_sha,
        "donor_manifest_sha256": v9_report["donor_manifest_sha256"],
        "identity_audit": {
            "candidate_evaluator_identity": v9_report["candidate_evaluator_identity"],
            "candidate_evaluator_cache_identity": cache_identity,
            "candidate_evaluator_audit": {
                "cache_identity": cache_identity,
                "cache_identity_sha256": cache_identity.rsplit(":", 1)[-1],
                "full_form_signature": "fixture-full-form-signature",
            },
            "active_rows": v9_report["active_rows"],
            "saved_port_rows": v9_report["appended_rows"],
            "rhs_reducer": "fixture-reducer",
            "candidate_full_action_gate": {
                "full_action_artifact": "v6_y",
                "full_reduced_rhs_artifact": "v6_g",
                "columns": v9_gate["columns"],
                "relative_tolerance": v9_gate["relative_tolerance"],
            },
        },
        "persisted_evidence_arrays": [v6_arrays["v6_y"], v6_arrays["v6_g"]],
    }), encoding="utf-8")
    v6_report_sha = hashlib.sha256(v6_report_path.read_bytes()).hexdigest()

    v6_contract_bindings = {
        producer_contract_path.resolve(): (producer_contract, producer_contract_sha),
        consumer_contract_path.resolve(): (consumer_contract, consumer_contract_sha),
        v6_contract_path.resolve(): (v6_contract, v6_contract_sha),
    }

    def require_y_g_contract(path, *, expected_sha256, **_kwargs):
        contract_path = Path(path).resolve()
        payload, digest = v6_contract_bindings[contract_path]
        assert expected_sha256 == digest
        assert hashlib.sha256(contract_path.read_bytes()).hexdigest() == digest
        return payload, digest

    monkeypatch.setattr(checker_module, "require_task41_p0_contract", require_y_g_contract)
    real_compare = checker_module.compare_task41_p0_b0_saved_y_g_reports

    def compare_miniature(**kwargs):
        kwargs.update(
            repo_root=repo_root,
            expected_shape=(4, 2),
            trace_rows=3,
            target_rows=(3,),
            block_rows=2,
        )
        return real_compare(**kwargs)

    monkeypatch.setattr(checker_module, "compare_task41_p0_b0_saved_y_g_reports", compare_miniature)
    commands.clear()
    checker_authorizations.clear()
    y_g_output_root = results_root / "task41_p0_saved_diagnostics_6h" / window.sha256 / "saved_y_g_comparison" / "attempt01"
    budget_probe = output_root / "overbudget.sparse"
    with budget_probe.open("wb") as stream:
        stream.truncate(3 * 1024**3)
    commands.clear()
    overbudget_result = service_workflow._run_task41_p0_saved_output_service(
        unit="myfenics-case-y-g-overbudget.service",
        runtime_prefix=runtime_prefix,
        environment={"TASK41_P0_CHECKER_SOURCE_SHA": consumer_source_sha},
        window=window,
        contract=contract,
        contract_path=consumer_contract_path,
        contract_sha=consumer_contract_sha,
        case_id="B0",
        run_root=run_root,
        output_root=y_g_output_root,
        consumer_source_sha=consumer_source_sha,
        checker_only=True,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        b0_saved_y_g_comparison_mode=True,
        v6_y_g_report_path=v6_report_path,
        v6_y_g_report_sha256=v6_report_sha,
        v9_y_g_report_path=v9_report_path,
        v9_y_g_report_sha256=v9_report_sha,
        v9_y_g_summary_path=v9_summary_path,
        v9_y_g_summary_sha256=v9_summary_sha,
        v9_y_g_service_receipt_path=v9_receipt_path,
        v9_y_g_service_receipt_sha256=v9_receipt_sha,
        input_path=input_path,
        activation_command=["activate"],
        activation_identity="qualified fixture",
        preflight={"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1},
        preflight_command=["preflight"],
        cgroup_start={"memory_current_bytes": 1},
        service_entry_accounting={"recorded": True},
        service_start_sample=clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=contract_module.sha256_file,
    )
    assert overbudget_result == 3
    assert commands == []
    overbudget_receipt = json.loads(
        (y_g_output_root.with_name(y_g_output_root.name + ".service")
         / "task41_p0_service_receipt.json").read_text(encoding="utf-8")
    )
    assert "512 MiB window-wide cap" in overbudget_receipt["workflow_error"]["message"]
    budget_probe.unlink()
    shutil.rmtree(y_g_output_root, ignore_errors=True)
    shutil.rmtree(y_g_output_root.with_name(y_g_output_root.name + ".service"), ignore_errors=True)
    commands.clear()
    y_g_result = service_workflow._run_task41_p0_saved_output_service(
        unit="myfenics-case-y-g.service",
        runtime_prefix=runtime_prefix,
        environment={"TASK41_P0_CHECKER_SOURCE_SHA": consumer_source_sha},
        window=window,
        contract=contract,
        contract_path=consumer_contract_path,
        contract_sha=consumer_contract_sha,
        case_id="B0",
        run_root=run_root,
        output_root=y_g_output_root,
        consumer_source_sha=consumer_source_sha,
        checker_only=True,
        checker_snapshot_path=None,
        checker_snapshot_sha256=None,
        b0_saved_y_g_comparison_mode=True,
        v6_y_g_report_path=v6_report_path,
        v6_y_g_report_sha256=v6_report_sha,
        v9_y_g_report_path=v9_report_path,
        v9_y_g_report_sha256=v9_report_sha,
        v9_y_g_summary_path=v9_summary_path,
        v9_y_g_summary_sha256=v9_summary_sha,
        v9_y_g_service_receipt_path=v9_receipt_path,
        v9_y_g_service_receipt_sha256=v9_receipt_sha,
        input_path=input_path,
        activation_command=["activate"],
        activation_identity="qualified fixture",
        preflight={"scalar_type": "complex128", "int_type": "int32", "mpi_size": 1},
        preflight_command=["preflight"],
        cgroup_start={"memory_current_bytes": 1},
        service_entry_accounting={"recorded": True},
        service_start_sample=clock_sample(include_boot_id=True),
        repo_root=repo_root,
        supervise=fake_supervise,
        sha256_file=contract_module.sha256_file,
    )
    y_g_receipt = json.loads(
        (y_g_output_root.with_name(y_g_output_root.name + ".service")
         / "task41_p0_service_receipt.json").read_text(encoding="utf-8")
    )
    comparison_path = y_g_output_root / "task41_p0_b0_saved_y_g_comparison.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert y_g_result == 0
    assert len(commands) == len(checker_authorizations) == 1
    assert "--saved-b0-y-g-comparison" in commands[0]
    assert "--v6-report" in commands[0] and "--v9-service-receipt" in commands[0]
    assert "--numerical-output" not in commands[0]
    assert checker_authorizations[0]["checker_kind"] == "task41_p0_b0_saved_y_g_comparison_checker"
    assert len(checker_authorizations[0]["input_paths"]) >= 10
    authorized_paths = set(checker_authorizations[0]["input_paths"])
    assert str(donor_summary_path.resolve()) in authorized_paths
    assert str(donor_manifest_path.resolve()) in authorized_paths
    assert not (donor_payload_paths & authorized_paths)
    assert y_g_receipt["result_classification"] == "SAVED_VECTOR_COMPARISON_DIAGNOSTIC_ONLY"
    assert y_g_receipt["official_result"] is False
    assert y_g_receipt["required_checker_status"] == "diagnostic_completed"
    assert y_g_receipt["saved_y_g_comparison"]["status"] == "COMPLETED_DIAGNOSTIC_ONLY"
    assert y_g_receipt["saved_y_g_comparison"]["result_sha256"] == hashlib.sha256(
        comparison_path.read_bytes()
    ).hexdigest()
    assert y_g_receipt["saved_diagnostics_disk_budget"]["status"] == "POST_WRITE_CHECKED"
    assert y_g_receipt["saved_diagnostics_disk_budget"]["window_output_tree_bytes"] <= (
        task41_p0_contract.TASK41_B0_SAVED_DIAGNOSTICS_NEW_EVIDENCE_LIMIT_BYTES
    )
    assert y_g_receipt["saved_diagnostics_disk_budget"]["bound_raw_artifact_bytes_stat_deduplicated"] > 0
    assert comparison["status"] == "COMPLETED"
    assert comparison["errors"] == []
    assert comparison["official_result"] is False
    assert comparison["expected_shape"] == [4, 2]
    shared_identity = comparison["shared_donor_identity"]
    assert shared_identity["status"] == "HASH_BOUND_DONOR_METADATA_ONLY"
    assert shared_identity["payload_arrays_opened"] is False
    assert shared_identity["old_per_key_lu_identity"] == "UNKNOWN_NOT_PERSISTED_BY_V6"
    assert len(shared_identity["shared_mapping_and_known_rhs_identity"]) == 2
    assert shared_identity["shared_mapping_and_known_rhs_identity"][0]["artifacts"]["known_field"]["shape"] == [13]
    first_donor_column = shared_identity["shared_mapping_and_known_rhs_identity"][0]
    assert first_donor_column["input_recipe"]["active_trace_rows"] == 1
    assert first_donor_column["full_active_mapping_artifact"]["shape"] == [2]
    assert first_donor_column["artifacts"]["slave_rows"]["shape"] == [3]
    assert first_donor_column["input_recipe"]["active_original_rows_sha256"] != (
        first_donor_column["full_active_mapping_artifact"]["sha256"]
    )
    assert len(comparison["vectors"]["delta_y"]["block_energy_norm2_by_column"]) == 2
    assert all(len(column) == 2 for column in comparison["vectors"]["delta_y"]["block_energy_norm2_by_column"])
    assert not (y_g_output_root / "numerical_output").exists()

    def write_bound_reports_donor_hash(digest: str) -> tuple[str, str]:
        nonlocal v6_report_sha, v9_report_sha
        v9_report["donor_manifest_sha256"] = digest
        v9_report_path.write_text(json.dumps(v9_report), encoding="utf-8")
        v9_report_sha = hashlib.sha256(v9_report_path.read_bytes()).hexdigest()
        v6_payload = json.loads(v6_report_path.read_text(encoding="utf-8"))
        v6_payload["donor_manifest_sha256"] = digest
        v6_report_path.write_text(json.dumps(v6_payload), encoding="utf-8")
        v6_report_sha = hashlib.sha256(v6_report_path.read_bytes()).hexdigest()
        return v6_report_sha, v9_report_sha

    def direct_compare_kwargs(output_name: str) -> dict[str, object]:
        return {
            "v6_report_path": v6_report_path,
            "v6_report_sha256": v6_report_sha,
            "v9_report_path": v9_report_path,
            "v9_report_sha256": v9_report_sha,
            "v9_summary_path": v9_summary_path,
            "v9_summary_sha256": v9_summary_sha,
            "v9_service_receipt_path": v9_receipt_path,
            "v9_service_receipt_sha256": v9_receipt_sha,
            "consumer_contract_path": consumer_contract_path,
            "consumer_contract_sha256": consumer_contract_sha,
            "output_path": tmp_path / output_name,
            "repo_root": repo_root,
            "expected_shape": (4, 2),
            "trace_rows": 3,
            "target_rows": (3,),
            "block_rows": 2,
        }

    def forbid_comparison_array_open(*_args, **_kwargs):
        raise AssertionError("invalid donor binding reached one of the four comparison arrays")

    monkeypatch.setattr(checker_module.np, "load", forbid_comparison_array_open)
    # A V6/V9 disagreement and a mutually consistent but unfrozen hash must
    # both fail while only the hash-bound JSON metadata has been read.
    write_bound_reports_donor_hash(mini_donor_manifest_sha)
    v9_report["donor_manifest_sha256"] = "0" * 64
    v9_report_path.write_text(json.dumps(v9_report), encoding="utf-8")
    v9_report_sha = hashlib.sha256(v9_report_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="donor, row map"):
        real_compare(**direct_compare_kwargs("reject_v6_v9_donor_mismatch.json"))
    write_bound_reports_donor_hash("0" * 64)
    with pytest.raises(ValueError, match="frozen shared V4 donor manifest"):
        real_compare(**direct_compare_kwargs("reject_unfrozen_donor_hash.json"))

    # Even a mutually re-bound manifest is rejected if its column sequence is
    # malformed; the four saved comparison NPYs remain unopened.
    write_bound_reports_donor_hash(mini_donor_manifest_sha)
    donor_manifest["columns"][1]["column"] = 0
    wrong_column_sha = write_mini_donor_manifest(donor_manifest)
    write_bound_reports_donor_hash(wrong_column_sha)
    with pytest.raises(ValueError, match="columns or input recipes are out of order"):
        real_compare(**direct_compare_kwargs("reject_donor_column_order.json"))
