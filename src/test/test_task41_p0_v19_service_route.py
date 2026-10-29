from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import task40_v20_service_workflow as workflow
from benchmarks import subreaper_watchdog as watchdog
from src.runners import task41_p0_contract as contract_module
from src.runners import task40_v10_campaign as campaign_module
from src.runners import task41_p0_v18_saved_jz as v18_worker
from src.runners import task41_p0_v19_native_rank1 as v19_capture


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> tuple[Path, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path, _sha(path)


def test_v19_prior_accounting_binds_v18_receipt_compacts_and_actual_window_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source_sha = "f" * 40
    window_relative = Path("benchmarks/artifacts/fixture/v18-window.json")
    monkeypatch.setattr(contract_module, "TASK41_B0_V18_SAVED_JZ_WINDOW_RELATIVE", window_relative)
    monkeypatch.setattr(workflow, "_TASK41_P0_V19_PRIOR_V18_SOURCE_SHA", source_sha)
    window_path, window_sha = _write_json(
        root / window_relative,
        {
            "schema": "task41.p0.execution_window.v1",
            "task_id": contract_module.TASK41_MODEL_ID,
            "scope": copy.deepcopy(contract_module.TASK41_B0_V18_SAVED_JZ_SCOPE),
            "source_sha": workflow._TASK41_P0_V19_PRIOR_V18_WINDOW_ENTRY_SOURCE_SHA,
            "t0_utc": "2026-10-29T00:50:15.000000000Z",
            "numerical_deadline_utc": "2026-10-29T06:30:15.000000000Z",
            "deadline_utc": "2026-10-29T06:50:15.000000000Z",
        },
    )
    monkeypatch.setattr(workflow, "_TASK41_P0_V19_PRIOR_V18_WINDOW_SHA256", window_sha)

    contract_path, contract_sha = _write_json(
        root / contract_module.TASK41_B0_CONTROLLER_RELATIVE
        / f"execution_contract_source_{source_sha}_v18_saved_jz_candidate_6h.json",
        {
            "branch": contract_module.TASK41_BRANCH,
            "source": {"sha": source_sha},
            "execution_scope": copy.deepcopy(contract_module.TASK41_B0_V18_SAVED_JZ_SCOPE),
            "window": {"path": window_relative.as_posix(), "sha256": window_sha},
        },
    )
    monkeypatch.setattr(workflow, "_TASK41_P0_V19_PRIOR_V18_CONTRACT_SHA256", contract_sha)

    # Model the unchanged V18 helper's current stat result while preserving its
    # historical receipt values. The new note is added after the V18 snapshot.
    v17_tree = root / "results" / contract_module.TASK41_MODEL_ID / "prior-v17-window"
    v17_tree.mkdir(parents=True)
    (v17_tree / "existing.bin").write_bytes(b"v" * 300)
    prior_identity = {
        "receipt_path": "/fixture/v17-receipt.json",
        "receipt_sha256": "1" * 64,
        "contract_path": "/fixture/v17-contract.json",
        "contract_sha256": "2" * 64,
        "window_path": "/fixture/v17-window.json",
        "window_sha256": "3" * 64,
        "recorded_cumulative_raw_artifact_bytes": 1_000,
        "bound_raw_artifact_bytes_stat_deduplicated": 800,
        "window_output_tree_bytes_recorded": 275,
    }

    def current_v17_accounting(*, repo_root: Path) -> dict[str, Any]:
        assert repo_root.resolve() == root.resolve()
        actual = sum(item.stat().st_size for item in v17_tree.rglob("*") if item.is_file())
        return {
            **prior_identity,
            "window_output_tree_bytes_stat": actual,
            "window_output_tree_bytes_conservative": max(275, actual),
        }

    monkeypatch.setattr(workflow, "_task41_p0_v18_prior_evidence_accounting", current_v17_accounting)
    prior_v17_at_v18_closeout = current_v17_accounting(repo_root=root)

    compact_relative = Path("docs/fixture/v18_compact.json")
    compact_path = root / compact_relative
    receipt_relative = (
        Path("results") / contract_module.TASK41_MODEL_ID
        / "task41_p0_saved_diagnostics_6h" / window_sha
        / "selected_incident_replay" / "attempt02.service" / "task41_p0_service_receipt.json"
    )
    output_root = (
        root / "results" / contract_module.TASK41_MODEL_ID
        / "task41_p0_saved_diagnostics_6h" / window_sha
        / "selected_incident_replay" / "attempt02"
    )
    output_root.mkdir(parents=True)
    (output_root / "actual-window-output.bin").write_bytes(b"x" * 701)
    receipt_path = root / receipt_relative
    budget = {
        "status": "POST_WRITE_CHECKED",
        "recorded_cumulative_raw_artifact_bytes": 1_000,
        "bound_raw_artifact_bytes_stat_deduplicated": 900,
        "window_output_tree_bytes": 450,
        "current_invocation_bytes": 400,
        "prior_window_accounting": prior_v17_at_v18_closeout,
    }
    receipt, _ = _write_json(
        receipt_path,
        {
            "schema": "task41.p0.saved_output_service_receipt.v1",
            "status": "completed",
            "mode": "saved_b0_v18_saved_jz_candidate",
            "receipt_path": str(receipt_path.resolve()),
            "contract_path": str(contract_path.resolve()),
            "contract_sha256": contract_sha,
            "window_path": str(window_path.resolve()),
            "window_sha256": window_sha,
            "consumer_branch": contract_module.TASK41_BRANCH,
            "consumer_source_sha": source_sha,
            "checker_source_sha": source_sha,
            "consumer_output_root": str(output_root.resolve()),
            "result_classification": "V18_SAVED_JZ_AUDIT_COMPLETED",
            "v18_worker_completed": True,
            "v18_independent_check_completed": True,
            "official_result": False,
            "scientific_qualified": False,
            "full_owner_unlocked": False,
            "saved_diagnostics_disk_budget": budget,
        },
    )
    receipt_sha = _sha(receipt)
    monkeypatch.setattr(workflow, "_TASK41_P0_V19_PRIOR_V18_SERVICE_RECEIPT_SHA256", receipt_sha)
    monkeypatch.setattr(
        workflow, "_TASK41_P0_V19_PRIOR_V18_SERVICE_RECEIPT_BYTES", receipt.stat().st_size
    )

    historical_v17_tree = prior_v17_at_v18_closeout["window_output_tree_bytes_conservative"]
    resource_relative = Path("docs/fixture/v18_resource_compact.json")
    resource = {
        "schema": "task41.p0.v18.resource_compact.v1",
        "source_sha": source_sha,
        "window_sha256": window_sha,
        "attempt": "attempt02",
        "exit": {"classification": "V18_SAVED_JZ_AUDIT_COMPLETED"},
        "disk_and_evidence": {
            "recorded_cumulative_raw_artifact_bytes": 1_000,
            "prior_window_output_tree_conservative_bytes": historical_v17_tree,
            "current_invocation_output_tree_bytes": 400,
            "cumulative_evidence_formula_bytes": {
                "recorded_cumulative_raw_artifact_bytes": 1_000,
                "prior_window_output_tree_conservative_bytes": historical_v17_tree,
                "current_invocation_output_tree_bytes": 400,
            },
            "cumulative_evidence_conservative_bytes": 1_000 + historical_v17_tree + 400,
        },
    }
    _, resource_sha = _write_json(root / resource_relative, resource)
    monkeypatch.setattr(workflow, "_TASK41_P0_V19_PRIOR_V18_RESOURCE_COMPACT_RELATIVE", resource_relative)
    monkeypatch.setattr(workflow, "_TASK41_P0_V19_PRIOR_V18_RESOURCE_COMPACT_SHA256", resource_sha)
    compact, _ = _write_json(
        compact_path,
        {
            "schema": "task41.p0.v18.saved_jz_closeout.v1",
            "source": {"branch": contract_module.TASK41_BRANCH, "sha": source_sha},
            "scope": {
                "status": "COMPLETED_LOCAL_MIXED_NOT_QUALIFIED",
                "official_result": False,
                "scientific_qualified": False,
            },
            "artifact_refs": {
                "service_receipt": {
                    "path": receipt_relative.as_posix(),
                    "bytes": receipt.stat().st_size,
                    "sha256": receipt_sha,
                }
            },
        },
    )
    monkeypatch.setitem(
        v19_capture.SOURCE_BINDINGS,
        "v18_compact",
        (compact_relative.as_posix(), _sha(compact)),
    )

    # This addition is legitimate later evidence. It raises today's V17 stat but
    # cannot rewrite the historical V18 receipt/compact snapshot.
    (v17_tree / "later-closeout-note.txt").write_bytes(b"z" * 4096)
    current_v17 = current_v17_accounting(repo_root=root)

    accounted = workflow._task41_p0_v19_prior_evidence_accounting(repo_root=root)

    actual_v18_tree_bytes = sum(
        item.stat().st_size for item in output_root.parent.parent.rglob("*") if item.is_file()
    )
    assert accounted["recorded_cumulative_raw_artifact_bytes"] == 1_000
    assert accounted["bound_raw_artifact_bytes_stat_deduplicated"] == 900
    assert accounted["v18_window_output_tree_bytes_stat"] == actual_v18_tree_bytes
    assert accounted["v18_window_output_tree_bytes_conservative"] == max(
        450, 400, actual_v18_tree_bytes
    )
    assert current_v17["window_output_tree_bytes_conservative"] > historical_v17_tree
    assert accounted["window_output_tree_bytes_conservative"] == (
        current_v17["window_output_tree_bytes_conservative"]
        + max(450, 400, actual_v18_tree_bytes)
    )
    assert accounted["v18_service_receipt_sha256"] == receipt_sha
    assert accounted["v18_resource_compact_sha256"] == resource_sha

    receipt_path.write_text(receipt_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="service receipt SHA-256 differs"):
        workflow._task41_p0_v19_prior_evidence_accounting(repo_root=root)


def test_v19_service_uses_real_supervise_and_checker_cli_then_rechecks_without_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").symlink_to(Path(__file__).resolve().parents[1], target_is_directory=True)
    model_root = root / "results" / contract_module.TASK41_MODEL_ID
    model_root.mkdir(parents=True)
    run_root = model_root / "fixture-v17-run"
    run_root.mkdir()
    source_binding_relative = Path("results") / contract_module.TASK41_MODEL_ID / "fixture-v17.json"
    source_report = root / source_binding_relative
    source_report.parent.mkdir(parents=True, exist_ok=True)
    source_report.write_text('{"schema":"deliberately incomplete synthetic donor"}\n', encoding="utf-8")
    source_binding = (source_binding_relative.as_posix(), _sha(source_report))

    # The V19 command validator still hashes every registered source input. Only
    # the ignored, unavailable V17 report is replaced with this tiny real file.
    fixture_bindings = dict(v19_capture.SOURCE_BINDINGS)
    fixture_bindings["v17_report"] = source_binding
    for name in ("v18_compact", "v3_donor_closeout"):
        relative, expected_sha = fixture_bindings[name]
        source_path = Path(__file__).resolve().parents[2] / relative
        assert _sha(source_path) == expected_sha
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination)

    input_path = root / "input" / "fixture_b0.dat"
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"synthetic service input\n")
    fixture_support = root / "fixture_support"
    fixture_support.mkdir()
    fixture_support.joinpath("sitecustomize.py").write_text(
        textwrap.dedent(
            """
            import hashlib
            import json
            import os
            from pathlib import Path

            from src.runners import task41_p0_contract as contract_module
            from src.runners import task41_p0_v19_native_rank1 as capture_module
                from src.runners import task40_v10_campaign as campaign_module

                campaign_module.CAMPAIGN_SECONDS = 21600.0
                campaign_module.CLOSEOUT_RESERVE_SECONDS = 1200.0

            bindings = json.loads(os.environ["TASK41_P0_TEST_SOURCE_BINDINGS"])
            capture_module.SOURCE_BINDINGS = {
                name: (value["path"], value["sha256"])
                for name, value in bindings.items()
            }

            def fixture_require_contract(path, *, expected_sha256=None, current_root=None, **_kwargs):
                contract_path = Path(path)
                if not contract_path.is_absolute():
                    contract_path = Path(current_root or Path.cwd()) / contract_path
                raw = contract_path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if expected_sha256 is not None and digest != expected_sha256:
                    raise ValueError("fixture contract SHA differs")
                return json.loads(raw), digest

            contract_module.require_task41_p0_contract = fixture_require_contract
            """
        ),
        encoding="utf-8",
    )
    worker_script = root / "fixture_worker.py"
    worker_script.write_text(
        textwrap.dedent(
            """
            import argparse
            import hashlib
            import json
            import os
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--output-dir", required=True)
            parser.add_argument("--contract-path", required=True)
            parser.add_argument("--contract-sha256", required=True)
            parser.add_argument("--window-sha256", required=True)
            parser.add_argument("--worker-count", required=True)
            args = parser.parse_args()
            output = Path(args.output_dir)
            output.mkdir(parents=True, exist_ok=True)
            count_path = Path(args.worker_count)
            with count_path.open("a", encoding="utf-8") as stream:
                stream.write("worker\\n")
            contract_path = Path(args.contract_path).resolve()
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            identity = {
                "execution_scope": contract["execution_scope"],
                "consumer_contract_sha256": args.contract_sha256,
                "consumer_window_sha256": args.window_sha256,
            }
            identity_sha = hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            receipt = {
                "schema": "task41.p0.v19.selected_native_rank1_worker_receipt.v1",
                "status": "COMPLETED_LOCAL_NATIVE_RANK1_CAPTURE",
                "consumer_contract_path": str(contract_path),
                "consumer_contract_sha256": args.contract_sha256,
                "consumer_source_sha": contract["source"]["sha"],
                "consumer_window_sha256": args.window_sha256,
                "run_identity": identity,
                "run_identity_sha256": identity_sha,
                "original_donor": {"source_sha": "0" * 40},
                "source_bindings": {
                    "v17_report_path": str(Path(os.environ["TASK41_P0_TEST_V17_PATH"]).resolve()),
                    "v17_report_sha256": os.environ["TASK41_P0_TEST_V17_SHA256"],
                },
                "fresh_v17_map_identity": {},
                "mpc_restriction_support": {},
                "actual_integral_inventory": {},
                "component_column_captures": [],
                "stage_timings_seconds": {
                    name: 0.0 for name in (
                        "mesh_construction_seconds", "fresh_map_validation_seconds",
                        "form_jit_action_construction_seconds", "coefficient_table_packing_seconds",
                        "selected_coefficient_row_packing_seconds", "kernel_execution_seconds",
                        "direction_transform_seconds", "term_archive_save_seconds",
                    )
                },
                "worker_function_elapsed_seconds_pre_receipt_write": 0.0,
                "rank2_kernel_outputs": 0,
                "factorizations": 0,
                "getrs": 0,
                "full_native_action": False,
                "official_result": False,
                "scientific_qualified": False,
                "full_owner_unlocked": False,
            }
            receipt_path = output / f"task41_p0_v19_native_rank1_worker_{args.contract_sha256}.json"
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\\n",
                encoding="utf-8",
            )
            progress = {
                "schema": "task41.p0.v19.selected_native_rank1_progress.v1",
                "run_identity": identity,
                "run_identity_sha256": identity_sha,
                "terms": {},
            }
            (output / "task41_p0_v19_native_rank1_progress.json").write_text(
                json.dumps(progress, sort_keys=True, separators=(",", ":")) + "\\n",
                encoding="utf-8",
            )
            """
        ),
        encoding="utf-8",
    )
    ignore = root / ".gitignore"
    ignore.write_text(
        "/results/\n/benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller/\n",
        encoding="utf-8",
    )

    branch = contract_module.TASK41_BRANCH
    subprocess.run(["git", "init", "--quiet", "--initial-branch", branch], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "add", ".gitignore", "src", "fixture_support", "fixture_worker.py", "input", "docs"], cwd=root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "synthetic producer source"], cwd=root, check=True)
    producer_source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    window_path = root / contract_module.TASK41_B0_V19_NATIVE_RANK1_WINDOW_RELATIVE
    window_path.parent.mkdir(parents=True, exist_ok=True)
    window_path, window_sha = _write_json(window_path, {"schema": "synthetic fixed-window fixture"})
    anchor = campaign_module.clock_sample(include_boot_id=True)
    t0_ns = int(anchor["utc_ns"])
    window = campaign_module.FixedCampaignWindow(
        path=window_path.resolve(),
        sha256=window_sha,
        payload={"accounting_path": str(window_path.with_suffix(".jsonl").resolve())},
        anchor=anchor,
        t0_utc_ns=t0_ns,
        deadline_utc_ns=t0_ns + 21_600_000_000_000,
        total_seconds=21_600.0,
        bootstrap_seconds=0.0,
        closeout_seconds=1_200.0,
    )
    input_sha = _sha(input_path)
    resources = {
        "task_memory_max_bytes": 8 * 1024**3,
        "host_reserve_bytes": 1 * 1024**3,
        "memory_swap_max_bytes": 0,
    }
    raw_policy = {
        "scope": "task41_b0_v3_recovery_evidence",
        "raw_artifact_limit_bytes": 16 * 1024**3,
        "free_space_floor_bytes": 2 * 1024**3,
        "authorization": "user_20261019_16gib_evidence_only",
        "new_evidence_limit_bytes": contract_module.TASK41_B0_V19_NATIVE_RANK1_NEW_EVIDENCE_BYTES,
    }

    def write_contract(source_sha: str) -> tuple[dict[str, Any], Path, str]:
        contract = {
            "schema": contract_module.TASK41_P0_CONTRACT_SCHEMA,
            "task_id": contract_module.TASK41_MODEL_ID,
            "branch": branch,
            "source": {"sha": source_sha},
            "case": {
                "model_id": contract_module.TASK41_MODEL_ID,
                "run_id": contract_module.TASK41_B0_RUN_ID,
                "input_sha256": input_sha,
            },
            "runtime": {
            "runtime_prefix": str(Path(sys.executable).parent.parent),
                "abi_receipt_sha256": "a" * 64,
            },
            "execution_scope": copy.deepcopy(contract_module.TASK41_B0_V19_NATIVE_RANK1_SCOPE),
            "numerical_strategy": {"internal_rhs_strategy": "same_lu_rhs_solve"},
            "window": {
                "path": contract_module.TASK41_B0_V19_NATIVE_RANK1_WINDOW_RELATIVE.as_posix(),
                "sha256": window_sha,
                "total_seconds": 21_600.0,
                "numerical_seconds": 20_400.0,
                "closeout_seconds": 1_200.0,
            },
            "resources": resources,
            "time": {"total_seconds": 21_600.0, "numerical_seconds": 20_400.0},
            "evidence": {"raw_disk_policy": raw_policy},
        }
        path = (
            root / contract_module.TASK41_B0_CONTROLLER_RELATIVE
            / f"execution_contract_source_{source_sha}_v19_selected_native_rank1_6h.json"
        )
        _, digest = _write_json(path, contract)
        return contract, path, digest

    consumer_contract, contract_path, contract_sha = write_contract(producer_source_sha)
    bindings_payload = {
        name: {"path": relative, "sha256": digest}
        for name, (relative, digest) in fixture_bindings.items()
    }
    monkeypatch.setattr(v19_capture, "SOURCE_BINDINGS", fixture_bindings)
    monkeypatch.setattr(
        workflow,
        "_task41_p0_v19_prior_evidence_accounting",
        lambda **_kwargs: {
            "recorded_cumulative_raw_artifact_bytes": 0,
            "bound_raw_artifact_bytes_stat_deduplicated": 0,
            "window_output_tree_bytes_conservative": 0,
        },
    )
    monkeypatch.setattr(v18_worker, "stat_bound_raw_artifact_inventory", lambda **_kwargs: [])
    monkeypatch.setattr(
        workflow.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=128 * 1024**3, used=64 * 1024**3, free=64 * 1024**3),
    )
    monkeypatch.setattr(
        contract_module,
        "require_task41_p0_contract",
        lambda path, *, expected_sha256=None, **_kwargs: (
            json.loads(Path(path).read_text(encoding="utf-8")),
            _sha(Path(path)),
        ) if _sha(Path(path)) == expected_sha256 else (_ for _ in ()).throw(ValueError("fixture contract SHA differs")),
    )
    monkeypatch.setattr(contract_module, "load_task41_p0_fixed_window", lambda *_args, **_kwargs: window)
    monkeypatch.setattr(
        watchdog,
        "cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": True,
            "readable": True,
            "swap_current_bytes": 0,
            "memory_current_bytes": 0,
            "memory_max_bytes": resources["task_memory_max_bytes"],
        },
    )
    original_require = contract_module.require_task41_p0_contract

    def sitecustomize_require(path: str | Path, *, expected_sha256: str | None = None, current_root: str | Path | None = None, **_kwargs: Any):
        contract_path_value = Path(path)
        if not contract_path_value.is_absolute():
            contract_path_value = Path(current_root or root) / contract_path_value
        digest = _sha(contract_path_value)
        if expected_sha256 != digest:
            raise ValueError("fixture contract SHA differs")
        return json.loads(contract_path_value.read_text(encoding="utf-8")), digest

    assert original_require is not None
    # The sitecustomize admission and fixture-source binding were committed
    # before the synthetic source commits above; it is immutable during routes.
    worker_count = model_root / "fixture-worker-count.txt"
    def fake_worker_command(
        *, python: str, repo_root: Path, output_directory: Path,
        contract_path: Path, contract_sha256: str, budget_context: Path,
        budget_context_sha256: str,
    ) -> list[str]:
        return [
            python, str(worker_script),
            "--output-dir", str(output_directory),
            "--contract-path", str(contract_path),
            "--contract-sha256", contract_sha256,
            "--window-sha256", window.sha256,
            "--worker-count", str(worker_count),
        ]

    monkeypatch.setattr(workflow, "_task41_p0_v19_worker_command", fake_worker_command)
    source_file = root / "fixture_source_revision.txt"
    source_file.write_text("producer revision\n", encoding="utf-8")
    subprocess.run(["git", "add", "fixture_source_revision.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "fixture contract source marker"], cwd=root, check=True)
    producer_source_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    consumer_contract, contract_path, contract_sha = write_contract(producer_source_sha)
    output_root = (
        model_root / "task41_p0_saved_diagnostics_6h" / window_sha
        / "selected_incident_replay" / "attempt01"
    )

    def route_environment(
        contract: dict[str, Any], path: Path, digest: str,
        *, output_directory: Path | None = None,
        checker_only: bool = False, receipt_sha: str | None = None,
        receipt_path: Path | None = None,
    ) -> dict[str, str]:
        current_sha = contract["source"]["sha"]
        selected_output = output_directory or output_root
        environment = {
            "PYTHONPATH": os.pathsep.join(
                item for item in (
                    str(fixture_support), str(root), os.environ.get("PYTHONPATH", "")
                ) if item
            ),
            "TASK41_P0_STRICT_EXECUTION": "1",
            "TASK41_P0_CONTRACT_PATH": str(path.resolve()),
            "TASK41_P0_CONTRACT_SHA256": digest,
            "TASK41_P0_EXECUTION_WINDOW_PATH": str(window.path.resolve()),
            "TASK41_P0_EXECUTION_WINDOW_SHA256": window.sha256,
            "TASK41_P0_TASK_MEMORY_MAX_BYTES": str(resources["task_memory_max_bytes"]),
            "TASK41_P0_HOST_RESERVE_BYTES": str(resources["host_reserve_bytes"]),
            "TASK41_P0_MEMORY_SWAP_MAX_BYTES": "0",
            "TASK41_P0_EXPECTED_SOURCE_SHA": current_sha,
            "TASK41_P0_SAVED_OUTPUT_CONTINUATION": "1",
            "TASK41_P0_CONSUMER_SOURCE_SHA": current_sha,
            "TASK41_P0_CHECKER_SOURCE_SHA": current_sha,
            "TASK41_P0_V19_NATIVE_RANK1": "1",
            "TASK41_P0_V19_OUTPUT_DIRECTORY": str(selected_output),
            "TASK41_P0_TEST_SOURCE_BINDINGS": json.dumps(bindings_payload, separators=(",", ":")),
            "TASK41_P0_TEST_V17_PATH": str(source_report.resolve()),
            "TASK41_P0_TEST_V17_SHA256": source_binding[1],
        }
        if checker_only:
            environment.update({
                "TASK41_P0_V19_CHECKER_ONLY": "1",
                "TASK41_P0_V19_RECEIPT_SHA256": str(receipt_sha),
                "TASK41_P0_V19_RECEIPT_PATH": str(receipt_path),
            })
        return environment

    def call_route(
        *, unit: str, contract: dict[str, Any], path: Path, digest: str,
        checker_only: bool = False, receipt_sha: str | None = None,
        receipt_path: Path | None = None, output: Path | None = None,
        supervise: Any = watchdog.supervise,
    ) -> int:
        selected_output = output or output_root
        return workflow._run_task41_p0_saved_output_service(
            unit=unit,
            runtime_prefix=Path(sys.executable).parent.parent,
            environment=route_environment(
                contract, path, digest, output_directory=selected_output,
                checker_only=checker_only,
                receipt_sha=receipt_sha, receipt_path=receipt_path,
            ),
            window=window,
            contract=contract,
            contract_path=path,
            contract_sha=digest,
            case_id="B0",
            run_root=run_root,
            output_root=selected_output,
            consumer_source_sha=contract["source"]["sha"],
            checker_only=True,
            checker_snapshot_path=None,
            checker_snapshot_sha256=None,
            b0_v19_native_rank1_mode=True,
            v19_checker_only=checker_only,
            v19_receipt_sha256=receipt_sha,
            v19_receipt_path=receipt_path,
            input_path=input_path,
            activation_command=["fixture-qualified-activation"],
            activation_identity="synthetic-contract-admission-only",
            preflight={"passed": True, "synthetic": True},
            preflight_command=["fixture-abi-admission"],
            cgroup_start={"fixture": "synthetic-cgroup-admission"},
            service_entry_accounting={"fixture": True},
            service_start_sample={"fixture": True},
            repo_root=root,
            supervise=supervise,
            sha256_file=contract_module.sha256_file,
        )

    calls: list[tuple[list[str], Path, dict[str, Any]]] = []
    def actual_supervise(command: list[str], directory: Path, **options: Any) -> dict[str, Any]:
        calls.append((list(command), directory, options))
        return watchdog.supervise(command, directory, **options)

    with monkeypatch.context() as patcher:
        patcher.chdir(root)
        patcher.setattr(campaign_module, "CAMPAIGN_SECONDS", 21_600.0)
        patcher.setattr(campaign_module, "CLOSEOUT_RESERVE_SECONDS", 1_200.0)
        patcher.setattr(contract_module, "_git", lambda _root, *args: (
            producer_source_sha if args == ("rev-parse", "HEAD")
            else branch if args == ("branch", "--show-current")
            else ""
        ))
        patcher.setattr(contract_module, "require_task41_p0_contract", sitecustomize_require)
        patcher.setattr(contract_module, "load_task41_p0_fixed_window", lambda *_args, **_kwargs: window)
        patcher.setattr(watchdog, "cgroup_snapshot", lambda _pid: {
            "dedicated_job_cgroup": True, "readable": True, "swap_current_bytes": 0,
            "memory_current_bytes": 0, "memory_max_bytes": resources["task_memory_max_bytes"],
        })
        capture_result = call_route(
            unit="v19-fixture-capture.service", contract=consumer_contract,
            path=contract_path, digest=contract_sha, supervise=actual_supervise,
        )
        assert capture_result == 0

        receipt_path = output_root / f"task41_p0_v19_native_rank1_worker_{contract_sha}.json"
        receipt_sha = _sha(receipt_path)
        producer_contract_before = contract_path.read_bytes()
        assert worker_count.read_text(encoding="utf-8").splitlines() == ["worker"]
        first_receipt_path = output_root.with_name("attempt01.service-v19-fixture-capture") / "task41_p0_service_receipt.json"
        first_receipt = json.loads(first_receipt_path.read_text(encoding="utf-8"))
        first_report_path = output_root.with_name("attempt01.service-v19-fixture-capture") / "task41_p0_v19_independent_check.json"
        first_report = json.loads(first_report_path.read_text(encoding="utf-8"))
        assert first_receipt["v19_worker_completed"] is True
        assert first_receipt["v19_independent_check_completed"] is True
        assert first_receipt["v19_capture_status"] == "CAPTURE_COMPLETED"
        assert first_receipt["v19_audit_status"] == "AUDIT_COMPLETED"
        assert first_report["audit_completed"] is True
        assert first_report["native_binding_status"] == "NATIVE_REPLAY_UNBOUND"
        assert first_report["official_result"] is False
        assert first_report["scientific_qualified"] is False
        assert first_report["full_owner_unlocked"] is False

        # Advance only the synthetic Git source. The saved producer receipt and
        # producer contract remain byte-for-byte bound to the previous source.
        source_file.write_text("new consumer revision\n", encoding="utf-8")
        subprocess.run(["git", "add", "fixture_source_revision.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "new consumer source"], cwd=root, check=True)
        consumer_source_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
        assert consumer_source_sha != producer_source_sha
        new_contract, new_contract_path, new_contract_sha = write_contract(consumer_source_sha)
        current_head = consumer_source_sha
        patcher.setattr(contract_module, "_git", lambda _root, *args: (
            current_head if args == ("rev-parse", "HEAD")
            else branch if args == ("branch", "--show-current")
            else ""
        ))

        def fail_read_only_checker(
            command: list[str], directory: Path, **options: Any,
        ) -> dict[str, Any]:
            if command[1:3] == ["-m", "src.runners.task41_p0_v19_checker"]:
                raise RuntimeError("synthetic read-only checker interruption")
            return actual_supervise(command, directory, **options)

        assert call_route(
            unit="v19-fixture-readonly-error.service", contract=new_contract,
            path=new_contract_path, digest=new_contract_sha, checker_only=True,
            receipt_sha=receipt_sha, receipt_path=receipt_path,
            supervise=fail_read_only_checker,
        ) == 3
        assert worker_count.read_text(encoding="utf-8").splitlines() == ["worker"]
        error_service_dir = output_root.with_name(
            "attempt01.service-v19-fixture-readonly-error"
        )
        error_receipt = json.loads(
            (error_service_dir / "task41_p0_service_receipt.json").read_text(encoding="utf-8")
        )
        assert error_receipt["v19_worker_completed"] is True
        assert error_receipt["v19_capture_status"] == "READ_ONLY_RECEIPT_BOUND"
        assert error_receipt["v19_audit_status"] == "AUDIT_INCOMPLETE"
        assert error_receipt["v19_audit_completed"] is False
        assert error_receipt["status"] == "failed_raw_evidence_retained"

        assert call_route(
            unit="v19-fixture-readonly-review.service", contract=new_contract,
            path=new_contract_path, digest=new_contract_sha, checker_only=True,
            receipt_sha=receipt_sha, receipt_path=receipt_path, supervise=actual_supervise,
        ) == 0
        assert worker_count.read_text(encoding="utf-8").splitlines() == ["worker"]
        assert contract_path.read_bytes() == producer_contract_before
        assert json.loads(receipt_path.read_text(encoding="utf-8"))["consumer_source_sha"] == producer_source_sha
        second_service_dir = output_root.with_name("attempt01.service-v19-fixture-readonly-review")
        second_receipt = json.loads((second_service_dir / "task41_p0_service_receipt.json").read_text(encoding="utf-8"))
        second_report = json.loads((second_service_dir / "task41_p0_v19_independent_check.json").read_text(encoding="utf-8"))
        assert second_receipt["v19_worker_route"] == "READ_ONLY_EXISTING_RECEIPT"
        assert second_receipt["v19_worker_completed"] is True
        assert second_receipt["v19_independent_check_completed"] is True
        assert second_report["audit_completed"] is True
        assert second_report["native_binding_status"] == "NATIVE_REPLAY_UNBOUND"
        assert second_report["official_result"] is False
        assert second_report["scientific_qualified"] is False
        assert second_report["full_owner_unlocked"] is False
        assert [
            row[0][2] if row[0][1] == "-m" else Path(row[0][1]).name
            for row in calls
        ] == [
            "fixture_worker.py",
            "src.runners.task41_p0_v19_checker",
            "src.runners.task41_p0_v19_checker",
        ]

        before_rejections = len(calls)
        assert call_route(
            unit="v19-fixture-bad-hash.service", contract=new_contract,
            path=new_contract_path, digest=new_contract_sha, checker_only=True,
            receipt_sha="0" * 64, receipt_path=receipt_path, supervise=actual_supervise,
        ) == 3
        bad_scope_contract = copy.deepcopy(new_contract)
        bad_scope_contract["execution_scope"] = {**bad_scope_contract["execution_scope"], "full_q_scan": True}
        bad_scope_output = (
            model_root / "task41_p0_saved_diagnostics_6h" / window_sha
            / "selected_incident_replay" / "attempt02"
        )
        assert call_route(
            unit="v19-fixture-bad-scope.service", contract=bad_scope_contract,
            path=new_contract_path, digest=new_contract_sha, output=bad_scope_output,
            supervise=actual_supervise,
        ) == 3
        assert len(calls) == before_rejections
        assert worker_count.read_text(encoding="utf-8").splitlines() == ["worker"]
