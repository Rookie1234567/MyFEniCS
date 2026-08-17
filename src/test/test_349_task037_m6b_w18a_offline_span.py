from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

import benchmarks.run_task037_extra_m6b as runner
from src.solvers import krylov_span_diagnostic as span


def _write_array(path: Path, value: np.ndarray) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, value)
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": runner._sha256_file(path),
        "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(value),
        "dtype": "complex128",
        "shape": [value.shape[0]],
    }


def _fixture(
    tmp_path: Path, source_sha: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    raw = tmp_path / "raw"
    arrays = {
        "rhs": np.asarray([1.0 + 0.2j, 2.0 - 0.1j, 0.1j, 0.2], dtype=np.complex128),
        "solution1": np.asarray([0.2 + 0.1j, 0.3 - 0.2j, 0.0, 0.1j], dtype=np.complex128),
        "solution2": np.asarray([0.1 - 0.2j, 0.4 + 0.1j, 0.2, -0.1j], dtype=np.complex128),
        "image1": np.asarray([1.0 + 0.1j, 0.0, 0.0, 0.0], dtype=np.complex128),
        "image2": np.asarray([0.0, 1.0 - 0.1j, 0.0, 0.0], dtype=np.complex128),
    }
    checkpoint_groups = []
    repeats = []
    for repeat in (1, 2):
        checkpoints = {}
        base = raw / "outer_checkpoints" / f"repeat{repeat}"
        for checkpoint in (1, 2):
            solution_key = "solution1" if checkpoint == 1 else "solution2"
            solution = arrays[solution_key]
            rhs_path = base / f"m6b_iter{checkpoint}_rhs.npy"
            solution_path = base / f"m6b_iter{checkpoint}_solution.npy"
            rhs = _write_array(rhs_path, arrays["rhs"])
            solution_descriptor = _write_array(solution_path, solution)
            rhs["path"] = rhs_path.name
            solution_descriptor["path"] = solution_path.name
            checkpoints[str(checkpoint)] = {
                "artifacts": {"rhs": rhs, "solution": solution_descriptor}
            }
        checkpoint_groups.append(
            {"repeat_index": repeat, "checkpoints": checkpoints}
        )
        repeats.append({"repeat_index": repeat, "checkpoints": checkpoints})
    physical_outputs = {}
    for repeat in (1, 2):
        for checkpoint in (1, 2):
            key = f"repeat{repeat}_checkpoint{checkpoint}"
            image = arrays["image1" if checkpoint == 1 else "image2"]
            path = raw / f"w18a_p_{key}.npy"
            descriptor = _write_array(path, image)
            descriptor["path"] = path.name
            physical_outputs[key] = descriptor
    source = {
        "source_commit_full_sha": source_sha,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "worktree_status_porcelain": [],
    }
    summary = {
        "schema": runner.M6B_W18A_SCHEMA,
        "phase": runner.M6B_W18A_PHASE,
        "source_at_start": source,
        "source_at_end": source,
        "core": {
            "repeats": repeats,
            "artifacts": {
                "outer_checkpoints": checkpoint_groups,
                "physical_outputs": physical_outputs,
            },
        },
    }
    summary_path = raw / runner.M6B_W18A_SUMMARY_FILENAME
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    formal = span.analyze_two_column_span(
        arrays["rhs"],
        arrays["image1"],
        arrays["image2"],
        arrays["solution1"],
        arrays["solution2"],
    )
    formal_rhos = formal["single_column_rho"]
    compact = {
        "schema": runner.M6B_W18A_CHECK_SCHEMA,
        "phase": runner.M6B_W18A_PHASE,
        "classification": "W18A_NESTED_AUXILIARY_NUMERIC_FAIL",
        "problems": ["worker_action_gate"],
        "producer_source_sha": source_sha,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "physical_screen_locked": True,
        "physical_screen_unlocked": False,
        "raw_dir": str(raw.resolve()),
        "worker_summary": {
            "path": runner.M6B_W18A_SUMMARY_FILENAME,
            "present": True,
            "bytes": summary_path.stat().st_size,
            "sha256": runner._sha256_file(summary_path),
        },
        "measured": {"rho": formal_rhos + formal_rhos},
    }
    compact_path = tmp_path / "w18a_v2.json"
    compact_path.write_text(
        json.dumps(runner._attach_evidence(compact), sort_keys=True),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "M6B_W18A_OFFLINE_SPAN_AUTHORITY_COMPACT_SHA256",
        runner._sha256_file(compact_path),
    )
    compact_value = runner._read_json(compact_path)
    monkeypatch.setattr(
        runner,
        "M6B_W18A_OFFLINE_SPAN_AUTHORITY_EVIDENCE_SHA256",
        compact_value["evidence_sha256"],
    )
    return raw, compact_path, tmp_path / "span.json"


def test_w18a_two_column_complex_span_passes_and_records_combination():
    rhs = np.asarray([1.0 + 0.2j, 2.0 - 0.1j, 0.1j, 0.2], dtype=np.complex128)
    first = np.asarray([1.0 + 0.1j, 0.0, 0.0, 0.0], dtype=np.complex128)
    second = np.asarray([0.0, 1.0 - 0.1j, 0.0, 0.0], dtype=np.complex128)
    result = span.analyze_two_column_span(rhs, first, second, rhs, rhs)

    assert result["pass"] is True
    assert result["rank"] == 2
    assert result["hermitian_defect"] <= 1.0e-11
    assert result["normal_closure"] <= 1.0e-11
    assert result["direct_rho"] <= span.W18A_SPAN_RHO_LIMIT
    assert len(result["single_column_rho"]) == 2
    assert result["solution_combination_norm"] > 0.0


def test_w18a_rank_deficient_span_fails_closed():
    rhs = np.ones(4, dtype=np.complex128)
    first = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.complex128)
    result = span.analyze_two_column_span(rhs, first, 2.0 * first, rhs, rhs)

    assert result["pass"] is False
    assert result["rank"] < 2
    assert "rank" in result["problems"]


def test_w18a_span_gate_rejects_weak_two_column_image():
    rhs = np.asarray([0.0, 0.0, 1.0, 1.0], dtype=np.complex128)
    first = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.complex128)
    second = np.asarray([0.0, 1.0, 0.0, 0.0], dtype=np.complex128)
    result = span.analyze_two_column_span(rhs, first, second, rhs, rhs)

    assert result["pass"] is False
    assert result["direct_rho"] > span.W18A_SPAN_RHO_LIMIT


def test_w18a_offline_fixture_authority_and_output_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", 4)
    raw, compact, output = _fixture(tmp_path, "a" * 40, monkeypatch)
    report = runner._m6b_w18a_offline_span_report(raw, compact, "a" * 40)

    assert report["pass"] is True
    assert report["derived"] is True
    assert report["not_action_run"] is True
    assert report["pde_pass"] is False
    assert report["checks"]["repeat_identity"] is True
    assert len(report["artifact_hashes"]) == 4
    assert report["analysis_repeats"][0]["rows"] == 4
    assert all(
        descriptor["shape"] == [4]
        for item in report["artifact_hashes"].values()
        for descriptor in item.values()
    )

    assert runner._run_m6b_w18a_offline_span(
        raw, compact, output, "a" * 40
    ) == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["qualified_for_bounded_followup"] is True
    assert "rhs" not in saved
    with pytest.raises(FileExistsError):
        runner._run_m6b_w18a_offline_span(raw, compact, output, "a" * 40)


@pytest.mark.parametrize("tamper", ["descriptor", "source"])
def test_w18a_offline_tampered_authority_fails_closed(tmp_path, monkeypatch, tamper):
    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", 4)
    raw, compact, output = _fixture(tmp_path, "a" * 40, monkeypatch)
    summary_path = raw / runner.M6B_W18A_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if tamper == "descriptor":
        summary["core"]["repeats"][0]["checkpoints"]["1"]["artifacts"]["rhs"][
            "array_sha256"
        ] = "0" * 64
    else:
        summary["source_at_start"]["source_commit_full_sha"] = "b" * 40
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")

    assert runner._run_m6b_w18a_offline_span(
        raw, compact, output, "a" * 40
    ) == 1
    failure = json.loads(output.read_text(encoding="utf-8"))
    assert failure["pass"] is False
    assert failure["problems"] == ["input_evidence"]


def test_w18a_parser_dispatch_and_offline_path_has_no_action_stack(tmp_path, monkeypatch):
    args = runner._parser().parse_args(
        [
            "m6b-w18a-offline-span",
            "--raw-dir",
            str(tmp_path / "raw"),
            "--w18a-compact",
            str(tmp_path / "v2.json"),
            "--output",
            str(tmp_path / "out.json"),
            "--expected-source-sha",
            "a" * 40,
        ]
    )
    assert args.command == "m6b-w18a-offline-span"
    seen = {}

    def fake(raw_dir, compact_path, output, expected_source_sha):
        seen.update(
            raw_dir=raw_dir,
            compact_path=compact_path,
            output=output,
            expected_source_sha=expected_source_sha,
        )
        return 17

    monkeypatch.setattr(runner, "_run_m6b_w18a_offline_span", fake)
    assert runner.main(
        [
            "m6b-w18a-offline-span",
            "--raw-dir",
            str(tmp_path / "raw"),
            "--w18a-compact",
            str(tmp_path / "v2.json"),
            "--output",
            str(tmp_path / "out.json"),
            "--expected-source-sha",
            "a" * 40,
        ]
    ) == 17
    assert seen["expected_source_sha"] == "a" * 40
    source = inspect.getsource(runner._m6b_w18a_offline_span_report)
    assert all(
        token not in source
        for token in ("dolfinx", "PETSc", "MPI", "build_m6b", "_run_m6b_w18a_diagnostic")
    )
