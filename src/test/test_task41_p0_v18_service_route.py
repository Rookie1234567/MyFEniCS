"""Exercise the V18 registered service path with tiny, hash-bound saved inputs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import numpy as np

from scripts import task40_v20_service_workflow as workflow
from benchmarks import subreaper_watchdog as watchdog
from src.runners import task41_p0_contract as contract_module
from src.runners import task41_p0_v18_saved_jz as worker
from src.runners import task41_p0_v18_saved_jz_checker as checker


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> tuple[Path, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return path, _sha(path)


def _write_array(root: Path, name: str, value: np.ndarray) -> dict[str, Any]:
    path = root / f"{name}.npy"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, value, allow_pickle=False)
    return {
        "path": str(path.resolve()),
        "sha256": _sha(path),
        "bytes": path.stat().st_size,
        "shape": list(value.shape),
        "dtype": str(value.dtype),
    }


def _write_source_reports(root: Path, monkeypatch: Any) -> dict[str, tuple[str, str]]:
    model_root = root / "results" / contract_module.TASK41_MODEL_ID
    arrays_root = model_root / "v18_fixture_arrays"
    tensor = np.zeros((882, 882), dtype=np.complex128)
    tensor[450, 0] = complex(1.0, 0.25)
    z = np.zeros(450, dtype=np.complex128)
    z[0] = complex(1.0, -0.5)
    jz = tensor[450:882, :450] @ z
    baseline = -jz
    refs = {
        "tensor": _write_array(arrays_root, "oriented_tensor", tensor),
        "interior": _write_array(arrays_root, "interior_positions", np.arange(450, dtype=np.int64)),
        "trace": _write_array(arrays_root, "trace_positions", np.arange(450, 882, dtype=np.int64)),
        "data": _write_array(arrays_root, "trace_expansion_data", np.array([1.0 + 0.0j], dtype=np.complex128)),
        "indices": _write_array(arrays_root, "trace_expansion_indices", np.array([0], dtype=np.int64)),
        "indptr": _write_array(
            arrays_root, "trace_expansion_indptr",
            np.r_[np.array([0, 1], dtype=np.int64), np.ones(431, dtype=np.int64)],
        ),
        "z": _write_array(arrays_root, "z", z),
        "baseline": _write_array(arrays_root, "historical_minus_jz", baseline),
        "s": _write_array(arrays_root, "saved_s_action", np.zeros(432, dtype=np.complex128)),
        "u": _write_array(arrays_root, "known_interior", np.zeros(450, dtype=np.complex128)),
        "t": _write_array(arrays_root, "known_trace", np.zeros(432, dtype=np.complex128)),
    }
    def maps_for(label: str, active_row: int) -> dict[str, Any]:
        return {
            "active_ids": _write_array(
                arrays_root, f"{label}_active_ids", np.array([active_row], dtype=np.int64)
            ),
            "interior_positions": refs["interior"],
            "trace_positions": refs["trace"],
            "trace_expansion_data": refs["data"],
            "trace_expansion_indices": refs["indices"],
            "trace_expansion_indptr": refs["indptr"],
        }

    maps = maps_for("v17", 1_622_464)
    maps_v11 = maps_for("v14_v11", 87_567)
    maps_v8 = maps_for("v14_v8", 4_766_937)
    rhs = {
        "z0": refs["z"], "z0_minus_Jz": refs["baseline"],
        "final_z": refs["z"], "returned_minus_Jz": refs["baseline"],
    }
    model_reports = model_root / "v18_fixture_reports"
    v17_relative = Path("results") / contract_module.TASK41_MODEL_ID / "v18_fixture_reports" / "v17.json"
    v11_meta_relative = Path("results") / contract_module.TASK41_MODEL_ID / "v18_fixture_reports" / "v11_metadata.json"
    v11_meta_path = root / v11_meta_relative

    v17_payload = {
        "schema": "task41.p0.b0.v17.selected_two_cell_worker_receipt.v1",
        "status": "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY",
        "consumer_window_sha256": "7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54",
        "selected_two_cell_candidate_callback": {
            "scope": {"selected_active_row": 1_622_464, "selected_original_row": 5_218_672},
            "cells": [
                {
                    "cell_index": cell,
                    "candidate_artifacts": {"oriented_tensor": refs["tensor"]},
                    "fresh_map_artifacts": maps,
                    "columns": [
                        {
                            "cell_index": cell,
                            "rhs_artifacts": rhs,
                            "S_action_artifact": refs["s"],
                            "known_interior_local_artifact": refs["u"],
                            "known_trace_local_artifact": refs["t"],
                        }
                        for _ in range(2)
                    ],
                }
                for cell in (7873, 8014)
            ],
            "columns": [
                {
                    "column": col,
                    "native_rhs_t": [0.0, 0.0],
                    "native_volume_rhs_t": [0.0, 0.0],
                    "b_alpha_t": [0.0, 0.0],
                    "saved_y9": [0.0, 0.0],
                    "saved_g9": [float((2 * baseline[0]).real), float((2 * baseline[0]).imag)],
                    "saved_y15": [0.0, 0.0],
                    "saved_g15": [float((2 * baseline[0]).real), float((2 * baseline[0]).imag)],
                }
                for col in (0, 1)
            ],
        },
    }
    v17_path, v17_sha = _write_json(root / v17_relative, v17_payload)
    v11_meta_payload = {
        "schema": "task41.p0.v8.selected_trace_star_metadata_only_receipt.v1",
        "status": "COMPLETED_METADATA_ONLY",
        "selected_trace_star_metadata_only": {
            "selected_cells": [
                {"cell_index": cell, "arrays": maps_v11}
                for cell in (360, 446)
            ]
        },
    }
    _write_json(v11_meta_path, v11_meta_payload)
    v11_relative = model_reports.relative_to(root) / "v11.json"
    v11_payload = {
        "schema": "task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1",
        "status": "COMPLETED_LOCAL_CANDIDATE_REPLAY",
        "selected_metadata_report_path": str(v11_meta_path.resolve()),
    }
    v11_path, v11_sha = _write_json(root / v11_relative, v11_payload)
    v8_relative = model_reports.relative_to(root) / "v8.json"
    v8_payload = {
        "schema": "task41.p0.v8.selected_trace_star_audit_receipt.v1",
        "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
        "selected_trace_star_metadata": {
            "cell_artifacts": {
                str(cell): {"arrays": maps_v8}
                for cell in (23352, 23493)
            }
        },
    }
    v8_path, v8_sha = _write_json(root / v8_relative, v8_payload)
    v14_v11_relative = model_reports.relative_to(root) / "v14_v11.json"
    v14_v8_relative = model_reports.relative_to(root) / "v14_v8.json"

    def candidate_rhs(cells: tuple[int, int]) -> list[dict[str, Any]]:
        return [
            {
                "cell_index": cell, "column": col,
                "oriented_tensor": refs["tensor"], "final_z": refs["z"],
                "returned_correction": refs["baseline"],
            }
            for cell in cells for col in (0, 1)
        ]

    def production_rows(cells: tuple[int, int], *, states: tuple[str | None, ...]) -> list[dict[str, Any]]:
        return [
            {
                "column": col, **({"state": state} if state is not None else {}),
                "selected_active_row": 87_567 if cells == (360, 446) else 4_766_937,
                "selected_original_row": 250_113 if cells == (360, 446) else 15_440_235,
                "incident_cell_order": list(cells),
                "base_b_t": [0.0, 0.0], "b_alpha_row_used_once": [0.0, 0.0],
                "saved_y": [0.0, 0.0],
                "candidate_g_actual_returned_correction_cell_order": [
                    float((2 * baseline[0]).real), float((2 * baseline[0]).imag)
                ],
                "y_cell_s_action_sources": [refs["s"], refs["s"]],
            }
            for col in (0, 1) for state in states
        ]

    source_window_sha = "4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c"
    _write_json(root / v14_v11_relative, {
        "schema": "task41.p0.v14.saved_same_lu_rhs_candidate.v1",
        "status": "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
        "producer_report_sha256": v11_sha,
        "consumer_window_sha256": source_window_sha,
        "candidate_rhs": candidate_rhs((360, 446)),
        "production_order_rows": production_rows((360, 446), states=(None,)),
    })
    _write_json(root / v14_v8_relative, {
        "schema": "task41.p0.v14.saved_same_lu_rhs_candidate.v1",
        "status": "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
        "producer_report_sha256": v11_sha,
        "star_producer_report_sha256": v8_sha,
        "consumer_window_sha256": source_window_sha,
        "candidate_rhs": candidate_rhs((23352, 23493)),
        "production_order_rows": production_rows((23352, 23493), states=("j0", "j3")),
    })
    v14_v11_path = root / v14_v11_relative
    v14_v8_path = root / v14_v8_relative
    binding = {
        "v17": (str(v17_relative), v17_sha),
        "v14_v11": (str(v14_v11_relative), _sha(v14_v11_path)),
        "v14_v8": (str(v14_v8_relative), _sha(v14_v8_path)),
        "v11": (str(v11_relative), v11_sha),
        "v11_metadata": (str(v11_meta_relative), _sha(v11_meta_path)),
        "v8": (str(v8_relative), v8_sha),
    }
    monkeypatch.setattr(worker, "SOURCE_BINDINGS", binding)
    monkeypatch.setattr(checker, "SOURCE_BINDINGS", copy.deepcopy(binding))
    return binding


def test_v18_saved_output_service_runs_worker_and_independent_checker_in_one_route(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    root = tmp_path / "repo"
    model_root = root / "results" / contract_module.TASK41_MODEL_ID
    model_root.mkdir(parents=True)
    sources = _write_source_reports(root, monkeypatch)
    run_root = (root / sources["v17"][0]).resolve().parent

    window_path = root / contract_module.TASK41_B0_V18_SAVED_JZ_WINDOW_RELATIVE
    window_payload = {"schema": "fixture.window.v1", "t0_utc": "2026-10-01T00:00:00Z"}
    _, window_sha = _write_json(window_path, window_payload)
    window = SimpleNamespace(
        path=window_path, sha256=window_sha, accounting_path=window_path.with_suffix(".jsonl"),
        cutoff_seconds=20_400.0, closeout_seconds=1_200.0,
    )
    window.accounting_path.write_text("", encoding="utf-8")

    source_sha = "a" * 40
    contract = {
        "task_id": "Task41",
        "branch": contract_module.TASK41_BRANCH,
        "source": {"sha": source_sha},
        "case": {
            "model_id": contract_module.TASK41_MODEL_ID,
            "run_id": contract_module.TASK41_B0_RUN_ID,
            "input_sha256": "b" * 64,
        },
        "execution_scope": copy.deepcopy(contract_module.TASK41_B0_V18_SAVED_JZ_SCOPE),
        "numerical_strategy": {
            "schema": "task41.p0.b0.internal_rhs_strategy.v3",
            "internal_rhs_strategy": contract_module.TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
            "refinement_strategy": contract_module.TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
            "refinement_max_steps": 2,
            "jz_evaluation_strategy": "binary64_real_imag_fsum",
        },
        "window": {
            "path": contract_module.TASK41_B0_V18_SAVED_JZ_WINDOW_RELATIVE.as_posix(),
            "sha256": window_sha, "total_seconds": 21_600.0,
            "numerical_seconds": 20_400.0, "closeout_seconds": 1_200.0,
        },
        "resources": {
            "task_memory_max_bytes": 8 * 1024**3,
            "host_reserve_bytes": 1 * 1024**3,
            "memory_swap_max_bytes": 0,
        },
        "runtime": {
            "runtime_prefix": str(Path(sys.executable).parent.parent),
            "abi_receipt_sha256": "c" * 64,
        },
        "evidence": {
            "raw_disk_policy": {
                "scope": "task41_b0_v3_recovery_evidence",
                "raw_artifact_limit_bytes": 16 * 1024**3,
                "free_space_floor_bytes": 2 * 1024**3,
                "authorization": "user_20261019_16gib_evidence_only",
                "new_evidence_limit_bytes": contract_module.TASK41_B0_V18_SAVED_JZ_NEW_EVIDENCE_BYTES,
            },
        },
    }
    contract_path = (
        root / contract_module.TASK41_B0_CONTROLLER_RELATIVE
        / f"execution_contract_source_{source_sha}_v18_saved_jz_candidate_6h.json"
    )
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    _, contract_sha = _write_json(contract_path, contract)
    input_path = root / "benchmarks" / "fixture" / "task41_b0.json"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text("{}\n", encoding="utf-8")
    output_root = (
        model_root / "task41_p0_saved_diagnostics_6h" / window_sha
        / "selected_incident_replay" / "attempt01"
    )
    assert not output_root.exists()
    monkeypatch.setattr(
        workflow, "_task41_p0_v18_prior_evidence_accounting",
        lambda *, repo_root: {
            "recorded_cumulative_raw_artifact_bytes": 0,
            "bound_raw_artifact_bytes_stat_deduplicated": 0,
            "window_output_tree_bytes_conservative": 0,
        },
    )
    monkeypatch.setattr(
        workflow.shutil, "disk_usage",
        lambda _path: SimpleNamespace(total=128 * 1024**3, used=64 * 1024**3, free=64 * 1024**3),
    )
    calls: list[dict[str, Any]] = []

    def supervise(command: list[str], stage_dir: Path, **options: Any) -> dict[str, Any]:
        module_name = command[2]
        assert module_name in {
            "src.runners.task41_p0_v18_saved_jz",
            "src.runners.task41_p0_v18_saved_jz_checker",
        }
        calls.append({"command": command, "stage_dir": stage_dir, "options": options})
        flags = {command[index]: command[index + 1] for index in range(3, len(command) - 1, 2)}
        if module_name == "src.runners.task41_p0_v18_saved_jz":
            # The route leaves output-root creation to its worker.
            assert not output_root.exists()
            worker.produce_saved_jz_candidate(
                repo_root=root,
                output_dir=Path(flags["--output-dir"]),
                contract_path=Path(flags["--contract-path"]),
                contract_sha256=flags["--contract-sha256"],
                window_path=Path(flags["--window-path"]),
                window_sha256=flags["--window-sha256"],
            )
        else:
            assert output_root.is_dir()
            authorization = options["campaign_phase_authorization"]
            validator_environment = dict(options["worker_environment"])
            validator_environment.update({
                "TASK41_P0_STRICT_EXECUTION": "1",
                "TASK41_P0_SAVED_OUTPUT_CONTINUATION": "1",
                "TASK41_P0_CONSUMER_SOURCE_SHA": source_sha,
                "TASK41_P0_CHECKER_SOURCE_SHA": source_sha,
                "TASK41_P0_CONTRACT_PATH": str(contract_path.resolve()),
                "TASK41_P0_CONTRACT_SHA256": contract_sha,
            })

            def fake_git_run(args: list[str], **_kwargs: Any) -> SimpleNamespace:
                outputs = {
                    ("git", "rev-parse", "HEAD"): f"{source_sha}\n",
                    ("git", "branch", "--show-current"): f"{contract['branch']}\n",
                    ("git", "status", "--porcelain", "--untracked-files=normal"): "",
                }
                return SimpleNamespace(returncode=0, stdout=outputs[tuple(args)], stderr="")

            # Exercise the watchdog's registered entry point while simulating only
            # the source-control identity and contract loader for this tiny fixture.
            with monkeypatch.context() as patcher:
                patcher.chdir(root)
                patcher.setattr(watchdog.subprocess, "run", fake_git_run)
                patcher.setattr(
                    contract_module,
                    "require_task41_p0_contract",
                    lambda *_args, **_kwargs: (contract, contract_sha),
                )
                validated_authorization = watchdog._validate_campaign_closeout_authorization(
                    command=list(command),
                    campaign=window,
                    authorization=authorization,
                    worker_environment=validator_environment,
                )
                assert validated_authorization == authorization

                bad_command = list(command)
                bad_command[bad_command.index("--candidate-sha256") + 1] = "0" * 64
                bad_authorization = dict(authorization)
                bad_authorization["command_sha256"] = hashlib.sha256(
                    json.dumps(bad_command, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                ).hexdigest()
                import pytest
                with pytest.raises(ValueError, match="candidate/replay path, hash, or checker output identity differs"):
                    watchdog._validate_campaign_closeout_authorization(
                        command=bad_command,
                        campaign=window,
                        authorization=bad_authorization,
                        worker_environment=validator_environment,
                    )

            checker_result = checker.check_saved_jz_candidate(
                repo_root=root,
                candidate_path=Path(flags["--candidate-report"]),
                candidate_sha256=flags["--candidate-sha256"],
                replay_path=Path(flags["--replay-report"]),
                replay_sha256=flags["--replay-sha256"],
                contract_path=Path(flags["--contract-path"]),
                contract_sha256=flags["--contract-sha256"],
                window_path=Path(flags["--window-path"]),
                window_sha256=flags["--window-sha256"],
            )
            assert checker_result["package_bytes"] <= checker.MAX_REPORT_BYTES
        return {"classification": "COMPLETED", "leader_exit_code": 0, "descendants_cleared": True}

    environment = {
        "TASK41_P0_V18_SAVED_JZ_CANDIDATE": "1",
        "TASK41_P0_V18_OUTPUT_DIRECTORY": str(output_root),
        "TASK41_P0_CHECKER_SOURCE_SHA": source_sha,
        "TASK41_P0_CONTRACT_PATH": str(contract_path.resolve()),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
    }
    runtime_prefix = Path(contract["runtime"]["runtime_prefix"])
    result = workflow._run_task41_p0_saved_output_service(
        unit="fixture-v18.service", runtime_prefix=runtime_prefix, environment=environment,
        window=window, contract=contract, contract_path=contract_path, contract_sha=contract_sha,
        case_id="B0", run_root=run_root, output_root=output_root,
        consumer_source_sha=source_sha, checker_only=True, checker_snapshot_path=None,
        checker_snapshot_sha256=None, b0_v18_saved_jz_mode=True,
        input_path=input_path, activation_command=["fixture-activation"],
        activation_identity="fixture-qualified-activation", preflight={"passed": True},
        preflight_command=["fixture-preflight"], cgroup_start={"fixture": True},
        service_entry_accounting={"fixture": True}, service_start_sample={"fixture": True},
        repo_root=root, supervise=supervise, sha256_file=contract_module.sha256_file,
    )

    assert result == 0
    assert [call["command"][2] for call in calls] == [
        "src.runners.task41_p0_v18_saved_jz",
        "src.runners.task41_p0_v18_saved_jz_checker",
    ]
    assert calls[0]["options"]["campaign_phase"] == "numeric"
    assert calls[1]["options"]["campaign_phase"] == "closeout"
    assert calls[1]["options"]["campaign_phase_authorization"]["checker_kind"] == "task41_p0_b0_v18_saved_jz_checker"
    assert calls[0]["stage_dir"].name == "v18_saved_jz_worker_watchdog"
    assert calls[1]["stage_dir"].name == "v18_saved_jz_checker_watchdog"
    receipt_path = output_root.with_name("attempt01.service") / "task41_p0_service_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    check_path = output_root / "task41_p0_v18_independent_check.json"
    check = json.loads(check_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["result_classification"] == "V18_SAVED_JZ_AUDIT_COMPLETED"
    assert receipt["v18_worker_completed"] is True
    assert receipt["v18_independent_check_completed"] is True
    assert receipt["official_result"] is False
    assert receipt["scientific_qualified"] is False
    assert receipt["full_owner_unlocked"] is False
    assert check["audit_completed"] is True
    assert check["complete_jz_input_count"] == 16
    assert all(
        len(row["all_432_real_imag_component_errors"]) == 432
        for row in check["candidate_corrections"]
    )
    assert len(check["main_star_signed_D_decomposition"]) == 2
    assert not any(call["stage_dir"].exists() for call in calls)


def test_v18_service_entry_reaches_output_symlink_guard_before_contract_load(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    import pytest

    root = tmp_path / "repo"
    model_root = root / "results" / contract_module.TASK41_MODEL_ID
    source_report = model_root / "fixture" / "v17.json"
    source_report.parent.mkdir(parents=True)
    source_report.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        worker, "SOURCE_BINDINGS", {"v17": (source_report.relative_to(root).as_posix(), "a" * 64)}
    )
    target = tmp_path / "output-target"
    target.mkdir()
    output_link = root / "attempt01"
    output_link.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("TASK41_P0_V18_SAVED_JZ_CANDIDATE", "1")

    with pytest.raises(ValueError, match="Task41 V18 output directory cannot be a symlink"):
        workflow._run_task41_p0_service(
            unit="fixture-v18.service",
            runtime_prefix=Path(sys.executable).resolve().parent.parent,
            abi_receipt=tmp_path / "abi.json",
            jit_cache=tmp_path / "jit-cache",
            case_args=[],
            contract_path=root / "unused-contract.json",
            repo_root=root,
            v18_saved_jz_selector=True,
            v18_output_directory=output_link,
        )
