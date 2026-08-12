from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6 as m6


def _clean_source(sha: str = "a" * 40) -> dict[str, object]:
    return {
        "source_commit_full_sha": sha,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _runtime(mpi_size: int) -> dict[str, object]:
    return {
        "qualified_activation": "1",
        "sys_executable": str(Path(sys.executable)),
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "mpi_size": mpi_size,
        "linux_abi": True,
        "compiler": {
            "sysconfig_cc": "/usr/bin/cc",
            "probe_command": ["cc", "--version"],
            "version_line": "cc",
        },
        "package_paths": {
            "petsc4py": "/opt/venv/lib/petsc4py.so",
            "slepc4py": "/opt/venv/lib/slepc4py.so",
            "dolfinx": "/opt/venv/lib/dolfinx.so",
            "mpi4py": "/opt/venv/lib/mpi4py.so",
        },
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
    }


def _mode_manifest(tmp_path: Path) -> dict[str, object]:
    fields = {field: None for field in m6.M6A_MODE_IDENTITY_FIELDS}
    fields["schema"] = "m6-fullspace-dtn-mode-v1"
    modes = [{**fields, "mode_index": index} for index in range(m6.M6A_MODE_COUNT)]
    path = tmp_path / "mpi1_mode_manifest.json"
    path.write_text(
        json.dumps(
            {"schema": "m6-fullspace-dtn-mode-manifest-v1", "mode_count": 80, "modes": modes},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return m6._artifact(tmp_path, path.name)


def test_m6a_controller_has_only_standard_library_top_level_imports() -> None:
    tree = ast.parse(
        Path(m6.__file__).read_text(encoding="utf-8"),
        filename=str(m6.__file__),
    )
    forbidden = {"numpy", "mpi4py", "petsc4py", "dolfinx", "dolfinx_mpc"}
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] not in forbidden for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden


def test_m6a_fixed_scope_events_and_commands() -> None:
    scope = m6._m6a_scope(2, "mpi2")
    assert scope["global_rows"] == 173802
    assert scope["mode_count"] == 80
    assert scope["predicted_live_set_is_measurement"] is False
    assert scope["predicted_live_set_bytes"] <= scope["predicted_live_set_limit_bytes"]
    assert m6._event_order_valid(m6.M6A_EVENTS)
    assert not m6._event_order_valid(m6.M6A_EVENTS[:-1])
    command = m6._worker_command("/venv/bin/python", Path("/tmp/m6a"), "mpi2", 2)
    assert command[-6:] == [
        "--run-dir",
        "/tmp/m6a",
        "--phase",
        "mpi2",
        "--expected-mpi-size",
        "2",
    ]
    assert m6._worker_command("/venv/bin/python", Path("/tmp/m6a"), "mpi1", 1)[0] == "mpiexec"


def test_m6a_stage_gate_requires_clean_evidence_and_exit() -> None:
    source = _clean_source()
    stage = m6._attach_evidence(
        {
            "status": "measurement_complete",
            "scope": m6._m6a_scope(),
            "source_at_start": source,
            "source_at_end": source,
        }
    )
    process = {
        "return_code": 0,
        "termination": None,
        "processes_gone": True,
    }
    assert m6._stage_allows_online(process, stage, True)
    stage["status"] = "gate_failed"
    assert not m6._stage_allows_online(process, stage, True)
    assert not m6._stage_allows_online({**process, "return_code": 1}, stage, True)


def test_m6a_owned_array_contract_rejects_gap_overlap_and_missing(tmp_path: Path) -> None:
    left = m6._save_owned_array(
        tmp_path,
        "left",
        np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
        rank=0,
        ownership_range=(0, 2),
    )
    right = m6._save_owned_array(
        tmp_path,
        "right",
        np.asarray([3.0 + 0.0j, 4.0 + 0.0j]),
        rank=1,
        ownership_range=(2, 4),
    )
    loaded = m6._load_owned_vector(tmp_path, [left, right], 4)
    np.testing.assert_array_equal(loaded, np.asarray([1, 2, 3, 4], dtype=np.complex128))
    with pytest.raises(ValueError, match="owner-local array payload"):
        m6._load_owned_vector(tmp_path, [left, {**right, "ownership_range": [3, 5]}], 4)
    with pytest.raises(ValueError):
        m6._load_owned_vector(tmp_path, [{key: value for key, value in left.items() if key != "array_sha256"}], 2)


def test_m6a_checker_is_fail_closed_for_missing_raw() -> None:
    result = m6._check_raw(Path("/tmp/task037-m6a-nonexistent-fixture"))
    assert result["pass"] is False
    assert all(value is False for value in result["checks"].values())
    assert result["problems"]


def test_m6a_source_and_scope_missing_fields_fail_closed() -> None:
    source = _clean_source()
    assert m6._source_valid(source)
    assert not m6._source_valid({key: value for key, value in source.items() if key != "git_error"})
    assert not m6._source_pair_valid(source, {**source, "source_commit_full_sha": "b" * 40})
    assert m6._m6a_scope()["ordinary_default"] is False


def test_m6a_runtime_identity_stage_probe_and_online_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    compiler = {"sysconfig_cc": "/usr/bin/cc", "probe_command": ["cc", "--version"], "version_line": "cc"}

    class FakeH2B:
        @staticmethod
        def _lazy_h2a() -> object:
            return object()

        @staticmethod
        def _runtime_identity(_h2a: object, **kwargs: object) -> dict[str, object]:
            calls.append(dict(kwargs))
            return {
                "qualified_activation": "1",
                "sys_executable": str(Path(sys.executable)),
                "petsc_scalar_type": "complex128",
                "petsc_int_type": "int32",
                "threads": {
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "NUMEXPR_NUM_THREADS": "1",
                },
                "compiler": kwargs["compiler"] if kwargs["compiler"] is not None else compiler,
            }

    class FakeComm:
        size = 1

    stage = m6._worker_runtime_identity(FakeComm(), FakeH2B, compiler_probe=True)
    online = m6._worker_runtime_identity(
        FakeComm(), FakeH2B, compiler_probe=False, compiler=stage["compiler"]
    )
    assert calls == [
        {"compiler_probe": True, "compiler": None},
        {"compiler_probe": False, "compiler": compiler},
    ]
    assert m6._m6a_runtime_valid(stage, 1)
    assert m6._m6a_runtime_valid(online, 1)


def test_m6a_direct_phase_groups_reuse_two_components_per_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes = [
        SimpleNamespace(side="top", alpha=1 + 0j, gamma=2 + 0j, k_vector=(0, 0, 3 + 0j)),
        SimpleNamespace(side="top", alpha=1 + 0j, gamma=2 + 0j, k_vector=(0, 0, 3 + 0j)),
        SimpleNamespace(side="top", alpha=1 + 0j, gamma=4 + 0j, k_vector=(0, 0, 3 + 0j)),
    ]
    groups = m6._mode_phase_groups(modes)
    assert [indices for _key, indices in groups] == [(0, 1), (2,)]
    calls: list[str] = []

    def fake_component(assembler: str, _mode: object, _mpc: object) -> np.ndarray:
        calls.append(assembler)
        return np.ones(1, dtype=np.complex128)

    monkeypatch.setattr(m6, "_component_owned_values", fake_component)
    assemblers = {("top", 0): "component0", ("top", 1): "component1"}
    for _ in range(2):
        first, second = m6._fresh_phase_components(assemblers, modes, groups[0][1], None)
        del first, second
    first, second = m6._fresh_phase_components(assemblers, modes, groups[1][1], None)
    del first, second
    assert calls == ["component0", "component1", "component0", "component1", "component0", "component1"]


def test_m6a_progress_and_mode_manifest_are_file_bound(tmp_path: Path) -> None:
    progress = tmp_path / "mpi1_progress.jsonl"
    progress.write_text(
        "".join(
            json.dumps(
                {
                    "schema": f"{m6.M6A_SCHEMA}.progress.v1",
                    "phase": "mpi1",
                    "event": event,
                    "elapsed_wall_seconds": float(index),
                },
                sort_keys=True,
            )
            + "\n"
            for index, event in enumerate(m6.M6A_EVENTS)
        ),
        encoding="utf-8",
    )
    assert m6._progress_valid(progress, "mpi1", m6.M6A_EVENTS)
    progress.write_text(progress.read_text(encoding="utf-8").replace("candidate_ready", "direct_ready", 1), encoding="utf-8")
    assert not m6._progress_valid(progress, "mpi1", m6.M6A_EVENTS)
    mode = _mode_manifest(tmp_path)
    assert m6._mode_manifest_valid(tmp_path, mode)
    assert mode["sha256"] == _artifact_sha(tmp_path / mode["path"])
    reordered = json.loads((tmp_path / mode["path"]).read_text(encoding="utf-8"))
    reordered["modes"][0]["mode_index"] = 1
    (tmp_path / mode["path"]).write_text(json.dumps(reordered), encoding="utf-8")
    assert not m6._mode_manifest_valid(tmp_path, m6._artifact(tmp_path, mode["path"]))


def _artifact_sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m6a_phase_fixture_and_gate_tamper_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    progress = tmp_path / "mpi1_progress.jsonl"
    progress.write_text(
        "".join(
            json.dumps({"schema": f"{m6.M6A_SCHEMA}.progress.v1", "phase": "mpi1", "event": event, "elapsed_wall_seconds": float(index)}) + "\n"
            for index, event in enumerate(m6.M6A_EVENTS)
        ),
        encoding="utf-8",
    )
    mode = _mode_manifest(tmp_path)
    zero = np.zeros(m6.M6A_GLOBAL_ROWS, dtype=np.complex128)
    small = np.zeros(m6.M6A_MODE_COUNT, dtype=np.complex128)
    monkeypatch.setattr(m6, "_load_owned_vector", lambda *_args, **_kwargs: zero if _args[2] == m6.M6A_GLOBAL_ROWS else small)
    monkeypatch.setattr(m6, "_canonical_record", lambda *_args, **_kwargs: ({}, tuple()))
    monkeypatch.setattr(m6, "_h2b_module", lambda: type("FakeH2B", (), {"_cache_snapshot": staticmethod(lambda _path: {"files": []})})())
    audit = {
        "fine_space": "uncondensed_fullspace",
        "condensation": False,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "global_matrix_materialized": False,
        "augmented_matrix_materialized": False,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
        "mode_count": 80,
        "global_rows": m6.M6A_GLOBAL_ROWS,
        "fixed_H": "identity",
        "fe_sized_allgather": False,
        "ordinary_default": False,
        "modal_allreduce_count_per_apply": 1,
        "apply_count": 2,
        "retained_payload_scope": "numpy arrays + retained canonical manifest bytes",
        "python_object_overhead_included": False,
        "petsc_object_overhead_included": False,
        "matrix_type": "python_action_only",
        "retained_plus_work_limit_bytes": m6.M6A_RETAINED_WORK_LIMIT_BYTES,
        "retained_plus_work_global_sum_bytes": 1024,
        "retained_plus_work_gate": True,
        "mode_manifest_sha256": mode["sha256"],
    }
    records = {name: [] for name in ("candidate_action", "direct_action", "repeat_action", "candidate_physical_rhs", "direct_physical_rhs", "candidate_recovery", "direct_recovery", "repeat_recovery")}
    measurement = {
        "p6": {"global_cells": 252, "local_cells": 252, "local_nloc": 882, "global_rows": m6.M6A_GLOBAL_ROWS, "constraint_count": 9210},
        "local_cells_by_rank": [252],
        "events": list(m6.M6A_EVENTS),
        "cache": {"before": {"files": []}, "after": {"files": []}, "unchanged": True},
        "action_audit": audit,
        "arrays": records,
        "metrics": {key: 0.0 for key in ("candidate_direct_action_relative_error", "candidate_direct_physical_rhs_relative_error", "candidate_direct_recovery_relative_error", "candidate_repeat_action_relative_error", "candidate_repeat_recovery_relative_error")} | {"finite": True},
        "source": {"role": "source_primal", "canonical": {"path": "source.json", "sha256": "a" * 64, "role": "source_primal"}},
        "canonical": {
            "candidate_action_dual": {"path": "action.json", "sha256": "a" * 64, "role": "candidate_action_dual"},
            "candidate_physical_rhs_dual": {"path": "rhs.json", "sha256": "a" * 64, "role": "candidate_physical_rhs_dual"},
        },
        "mode_manifest": mode,
        "mode_manifest_sha256": mode["sha256"],
        "mode_manifest_sha_by_rank": [mode["sha256"]],
        "direct_oracle": {"explicit_C_materialized_count": 0, "explicit_D_materialized_count": 0, "global_matrix_materialized": False, "augmented_matrix_materialized": False, "schur_or_trace_operator_materialized": False, "streaming_passes": 2},
    }
    source = _clean_source()
    runtime = _runtime(1)
    summary = m6._attach_evidence({"schema": m6.M6A_WORKER_SCHEMA, "status": "measurement_complete", "source_at_start": source, "source_at_end": source, "runtime_identity": runtime, "runtime_identity_by_rank": [runtime], "scope": m6._m6a_scope(1, "mpi1"), "measurement": measurement})
    checks, _details = m6._phase_check(tmp_path, summary, phase="mpi1", expected_mpi_size=1)
    assert all(checks.values())
    tampered_audits = []
    missing_apply = dict(audit)
    missing_apply.pop("apply_count")
    tampered_audits.append(missing_apply)
    over_payload = dict(audit)
    over_payload["retained_plus_work_global_sum_bytes"] = m6.M6A_RETAINED_WORK_LIMIT_BYTES + 1
    tampered_audits.append(over_payload)
    explicit_matrix = dict(audit)
    explicit_matrix["explicit_C_materialized_count"] = 1
    tampered_audits.append(explicit_matrix)
    wrong_matrix_type = dict(audit)
    wrong_matrix_type["matrix_type"] = "aij"
    tampered_audits.append(wrong_matrix_type)
    wrong_limit = dict(audit)
    wrong_limit["retained_plus_work_limit_bytes"] -= 1
    tampered_audits.append(wrong_limit)
    for tampered in tampered_audits:
        bad_measurement = {**measurement, "action_audit": tampered}
        bad = m6._attach_evidence({**summary, "measurement": bad_measurement})
        bad_checks, _ = m6._phase_check(tmp_path, bad, phase="mpi1", expected_mpi_size=1)
        assert bad_checks["audit"] is False


def test_m6a_canonical_roles_are_not_interchangeable() -> None:
    assert m6._canonical_packet_role(((("full_fe",), 1.0 + 0.0j),), "full_fe")
    assert not m6._canonical_packet_role(((("full_fe",), 1.0 + 0.0j),), "full_fe_dual")


def test_m6a_watchdog_locks_mpi2_after_mpi1_worker_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    source = _clean_source()
    stage = m6._attach_evidence(
        {
            "schema": m6.M6A_STAGE_SCHEMA,
            "status": "measurement_complete",
            "scope": m6._m6a_scope(),
            "source_at_start": source,
            "source_at_end": source,
        }
    )

    class FakeH2B:
        def _light_source(self):
            return source

        def _worker_executable(self):
            return "/venv/bin/python"

        def _monitor_phase(self, _run_dir, phase, _command, _timeout, _limit):
            calls.append(phase)
            return {
                "status": "measurement_complete",
                "return_code": 0,
                "termination": None,
                "peak_rss_bytes": 1,
                "swap_bytes": 0,
            }

    monkeypatch.setattr(m6, "_h2b_module", lambda: FakeH2B())
    monkeypatch.setattr(m6, "_read_json", lambda _path: stage)
    monkeypatch.setattr(m6, "_stage_allows_online", lambda *_args: True)
    monkeypatch.setattr(m6, "_stage_summary_valid", lambda *_args: True)
    monkeypatch.setattr(m6, "_process_gate", lambda *_args, **_kwargs: (True, {"processes_gone": True}))
    monkeypatch.setattr(m6, "_phase_worker_gate", lambda *_args: (False, {"checks": {"numeric": False}}))
    monkeypatch.setattr(m6, "_raw_artifacts", lambda _run_dir: {})
    monkeypatch.setattr(m6, "_write_json", lambda *_args: None)

    assert m6._watchdog(tmp_path / "run") == 1
    assert calls == ["stage", "mpi1"]


def test_m6a_controlled_stop_records_missing_mpi2_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _clean_source()
    stage = m6._attach_evidence(
        {
            "schema": m6.M6A_STAGE_SCHEMA,
            "status": "measurement_complete",
            "scope": m6._m6a_scope(),
            "source_at_start": source,
            "source_at_end": source,
        }
    )
    captured: dict[str, object] = {}

    class FakeH2B:
        def _light_source(self):
            return source

        def _worker_executable(self):
            return "/venv/bin/python"

        def _monitor_phase(self, _run_dir, _phase, _command, _timeout, _limit):
            return {
                "status": "measurement_complete",
                "return_code": 0,
                "termination": None,
                "peak_rss_bytes": 1,
                "swap_bytes": 0,
            }

    monkeypatch.setattr(m6, "_h2b_module", lambda: FakeH2B())
    monkeypatch.setattr(m6, "_read_json", lambda _path: stage)
    monkeypatch.setattr(m6, "_stage_allows_online", lambda *_args: True)
    monkeypatch.setattr(m6, "_stage_summary_valid", lambda *_args: True)
    monkeypatch.setattr(m6, "_process_gate", lambda *_args, **_kwargs: (True, {"processes_gone": True}))
    monkeypatch.setattr(m6, "_phase_worker_gate", lambda *_args: (False, {"checks": {}}))
    monkeypatch.setattr(m6, "_write_json", lambda path, value: captured.update({"path": path, "value": value}))

    assert m6._watchdog(tmp_path / "run") == 1
    payload = captured["value"]
    assert payload["raw_artifacts"]["mpi2_worker_summary.json"]["present"] is False
