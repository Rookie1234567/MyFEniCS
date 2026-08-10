from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from dolfinx import fem

import benchmarks.run_task037_extra_h2 as runner
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space


def _source(sha: str = "a" * 40) -> dict[str, object]:
    return {
        "source_commit_full_sha": sha,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _runtime() -> dict[str, object]:
    return {
        "qualified_activation": "1",
        "sys_executable": str(runner.ROOT / ".venv" / "bin" / "python"),
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "python_version": "3.12.0",
        "petsc_version": "3.19.6",
        "dolfinx_version": "test",
        "basix_version": "test",
        "ffcx_version": "test",
        "ufl_version": "test",
        "ffcx_header_signature": "test",
        "ufcx_header_signature": "test",
        "sysconfig": {"CC": "cc", "CFLAGS": "", "SOABI": "test", "EXT_SUFFIX": ".so"},
        "compiler": {
            "sysconfig_cc": "cc",
            "probe_command": ["cc", "--version"],
            "version_line": "cc test",
        },
    }


def _form(role: str, *, hit: bool, cache_dir: Path) -> dict[str, object]:
    return {
        "role": role,
        "ufl_signature": f"ufl-{role}",
        "ufcx_signature": f"ufcx-{role}",
        "module_name": f"libffcx_forms_{role}",
        "ffcx_signature_stem": role,
        "code_state": (
            "hit_no_new_decl_impl" if hit else "cold_decl_impl_generated"
        ),
        "code_sha256": None if hit else "c" * 64,
        "jit_options": runner._form_jit_options(cache_dir),
        "form_compiler_options": {"scalar_type": "complex128"},
        "proxy_identity": ["B0", "test"],
        "element_signature": ["N1curl", "test"],
        "cache_files": [],
    }


def _progress(path: Path, phase: str) -> None:
    path.write_text(
        "".join(
            json.dumps(
                {
                    "schema": runner.R1_PROGRESS_SCHEMA,
                    "event": event,
                    "phase": phase,
                    "elapsed_wall_seconds": float(index),
                    "rank": 0,
                },
                sort_keys=True,
            )
            + "\n"
            for index, event in enumerate(runner._r1_expected_progress(phase))
        ),
        encoding="utf-8",
    )


def _timeline(path: Path, phase: str) -> None:
    if phase == "stage":
        live = {
            "progress_event": "curl_form_compile_started",
            "pids": [100, 101],
            "process_count": 2,
            "compiler_descendant_pids": [101],
        }
    else:
        live = {
            "progress_event": "curl_cache_load_started",
            "pids": [200],
            "process_count": 1,
            "compiler_descendant_pids": [],
        }
    samples = [
        {
            "schema": runner.R1_PROGRESS_SCHEMA,
            "sample_kind": "worker",
            "phase": phase,
            "elapsed_wall_seconds": 0.5,
            "root_pid": live["pids"][0],
            "rss_bytes": 100 if phase == "stage" else 200,
            "swap_bytes": 0,
            "all_status_readable": True,
            **live,
        },
        {
            "schema": runner.R1_PROGRESS_SCHEMA,
            "sample_kind": "final",
            "phase": phase,
            "elapsed_wall_seconds": 1.0,
            "return_code": 0,
        },
    ]
    path.write_text(
        "".join(json.dumps(sample, sort_keys=True) + "\n" for sample in samples),
        encoding="utf-8",
    )


def _write_good_raw(root: Path) -> None:
    root.mkdir()
    cache = root / "jit_cache"
    cache.mkdir()
    for role in ("curl", "mass"):
        for suffix in (".c", ".o", ".cpython-312-x86_64-linux-gnu.so", ".c.cached"):
            (cache / f"libffcx_forms_{role}{suffix}").write_bytes(b"cache")
    cache_inventory = runner._r1_cache_snapshot(cache)
    source = _source()
    runtime = _runtime()
    stage_forms = [_form("curl", hit=False, cache_dir=cache), _form("mass", hit=False, cache_dir=cache)]
    hit_forms = [_form("curl", hit=True, cache_dir=cache), _form("mass", hit=True, cache_dir=cache)]
    for form in stage_forms + hit_forms:
        form["cache_files"] = [
            item for item in cache_inventory
            if item["path"].startswith(form["module_name"] + ".")
        ]
    stage = runner.attach_evidence_sha256(
        {
            "schema": runner.R1_STAGE_WORKER_SCHEMA,
            "status": "measurement_complete",
            "scope": runner._r1_scope(),
            "phase": "stage",
            "source_at_start": source,
            "source_at_end": source,
            "runtime_identity": runtime,
            "initial_cache_empty": True,
            "forms": stage_forms,
            "cache_inventory": cache_inventory,
            "cache_inventory_sha256": runner._r1_cache_digest(cache_inventory),
            "identity": runner._r1_identity(),
            "phase_identity": runner._r1_phase_identity("stage"),
            "error": None,
            "elapsed_wall_seconds": 1.0,
        }
    )
    runner._write_json(root / "stage_summary.json", stage)
    _progress(root / "stage_progress.jsonl", "stage")
    (root / "stage_stdout.txt").write_text("", encoding="utf-8")
    _timeline(root / "stage_timeline.jsonl", "stage")
    hit = runner.attach_evidence_sha256(
        {
            "schema": runner.R1_HIT_WORKER_SCHEMA,
            "status": "measurement_complete",
            "scope": runner._r1_scope(),
            "phase": "hit",
            "source_at_start": source,
            "source_at_end": source,
            "runtime_identity": runtime,
            "r0_authority": runner._r1_read_r0_authority(),
            "stage_manifest_sha256": runner._sha256_file(
                root / "stage_summary.json"
            ),
            "cache_before": cache_inventory,
            "cache_after": cache_inventory,
            "cache_unchanged": True,
            "measurement": {
                "global_cells": 252,
                "local_nloc": 882,
                "global_rows": runner.H2A_FIXED_GLOBAL_ROWS,
                "constraint_count": runner.H2A_FIXED_CONSTRAINT_COUNT,
            },
            "forms": hit_forms,
            "identity": runner._r1_identity(),
            "phase_identity": runner._r1_phase_identity("hit"),
            "error": None,
            "elapsed_wall_seconds": 1.0,
        }
    )
    runner._write_json(root / "hit_summary.json", hit)
    _progress(root / "hit_progress.jsonl", "hit")
    (root / "hit_stdout.txt").write_text("", encoding="utf-8")
    _timeline(root / "hit_timeline.jsonl", "hit")
    stage_phase = {
        "phase": "stage",
        "command": runner._r1_worker_command(
            root, "stage", runtime["sys_executable"]
        ),
        "root_pid": 100,
        "return_code": 0,
        "termination": None,
        "completion_elapsed_seconds": 1.0,
        "controller_elapsed_start": 0.0,
        "controller_elapsed_end": 1.0,
        "live_sample_count": 1,
        "process_tree_peak_rss_bytes": 100,
        "process_tree_swap_bytes": 0,
        "observed_process_tree_pids": [101],
        "observed_compiler_descendant_pids": [101],
        "processes_gone_before_hit": True,
        "hit_started_after_stage_exit": True,
    }
    hit_phase = {
        "phase": "hit",
        "command": runner._r1_worker_command(
            root, "hit", runtime["sys_executable"]
        ),
        "root_pid": 200,
        "return_code": 0,
        "termination": None,
        "completion_elapsed_seconds": 1.0,
        "controller_elapsed_start": 1.1,
        "controller_elapsed_end": 2.1,
        "live_sample_count": 1,
        "process_tree_peak_rss_bytes": 200,
        "process_tree_swap_bytes": 0,
        "observed_process_tree_pids": [],
        "observed_compiler_descendant_pids": [],
    }
    names = (
        "stage_progress.jsonl",
        "stage_stdout.txt",
        "stage_summary.json",
        "stage_timeline.jsonl",
        "hit_progress.jsonl",
        "hit_stdout.txt",
        "hit_summary.json",
        "hit_timeline.jsonl",
    )
    watchdog = runner.attach_evidence_sha256(
        {
            "schema": runner.R1_WATCHDOG_SCHEMA,
            "status": "pass",
            "run_dir": str(root.resolve()),
            "scope": runner._r1_scope(),
            "runtime_identity": runtime,
            "source_at_start": source,
            "source_at_end": source,
            "source_clean_and_stable": True,
            "stage": stage_phase,
            "hit": hit_phase,
            "error": None,
            "completion_elapsed_seconds": 2.1,
            "raw_artifacts": {
                name: runner._r1_artifact(root / name) for name in names
            },
        }
    )
    runner._write_json(root / "r1_watchdog_summary.json", watchdog)


def test_r1_fixed_commands_and_phase_contract():
    args = runner._parser().parse_args(
        ["r1-watchdog", "--run-dir", "relative-run"]
    )
    assert args.command == "r1-watchdog"
    command = runner._r1_worker_command(
        Path("relative-run"), "stage", "/qualified/.venv/bin/python"
    )
    assert "mpiexec" not in command
    assert command[0] == "/qualified/.venv/bin/python"
    assert command[-1] == str(Path("relative-run").resolve())
    assert "floquet_mpc_started" not in runner._r1_expected_progress("stage")
    assert all(
        "tensor" not in event and "factor" not in event
        for event in runner._r1_expected_progress("stage")
    )
    assert all(
        "discovery" not in event and "tensor" not in event
        for event in runner._r1_expected_progress("hit")
    )


def test_r1_cache_snapshot_and_form_code_states(tmp_path: Path):
    cache = tmp_path / "jit_cache"
    cache.mkdir()
    item = cache / "libffcx_forms_test.c"
    item.write_text("first", encoding="utf-8")
    before = runner._r1_cache_snapshot(cache)
    assert before[0]["bytes"] == 5
    assert runner._r1_form_code_state(("decl", "impl"))[0] == (
        "cold_decl_impl_generated"
    )
    assert runner._r1_form_code_state((None, None)) == (
        "hit_no_new_decl_impl",
        None,
    )
    item.write_text("second", encoding="utf-8")
    assert runner._r1_cache_snapshot(cache) != before


def test_r1_stage_worker_does_not_call_mpc_tensor_or_factor(monkeypatch, tmp_path):
    class _Source:
        def as_jsonable(self):
            return _source()

    class _Module:
        def __init__(self, name):
            self.__name__ = name

        class ffi:
            @staticmethod
            def string(_signature):
                return b"ufcx"

    class _Form:
        def __init__(self, role, hit):
            self.code = (None, None) if hit else ("decl", "impl")
            self.module = _Module(f"libffcx_forms_{role}")
            self.ufcx_form = SimpleNamespace(signature=b"signature")

    class _UFL:
        def __init__(self, role):
            self.role = role

        def signature(self):
            return f"ufl-{self.role}"

    monkeypatch.setattr(
        runner,
        "inspect_tracked_source",
        lambda _root: _Source(),
    )
    monkeypatch.setattr(
        runner,
        "_r1_runtime_identity",
        lambda **_kwargs: _runtime(),
    )
    monkeypatch.setattr(
        runner,
        "target_stage4_config",
        lambda **_kwargs: SimpleNamespace(k0=1.0, mu_r=1.0),
    )
    class _IndexMap:
        size_global = runner.H2A_FIXED_GLOBAL_ROWS

    class _Topology:
        @staticmethod
        def index_map(_dim):
            return SimpleNamespace(size_global=252)

    mesh_data = SimpleNamespace(mesh=SimpleNamespace(topology=_Topology()))
    monkeypatch.setattr(runner, "build_airbox_mesh_3d", lambda *_args: mesh_data)
    function_space = SimpleNamespace(
        dofmap=SimpleNamespace(index_map=_IndexMap(), index_map_bs=1),
        element=SimpleNamespace(space_dimension=882),
    )
    monkeypatch.setattr(
        runner,
        "_create_nedelec_space",
        lambda *_args: function_space,
    )
    monkeypatch.setattr(
        runner,
        "_proxy_ufl_forms",
        lambda _space, _mesh_data, _cfg: (_UFL("curl"), _UFL("mass")),
    )
    form_calls = [0]
    monkeypatch.setattr(
        runner.fem,
        "form",
        lambda form, **_kwargs: (
            form_calls.__setitem__(0, form_calls[0] + 1)
            or _Form(form.role, form_calls[0] > 2)
        ),
    )
    monkeypatch.setattr(
        runner,
        "_canonical_basis_signature",
        lambda _space: ["test-element"],
    )
    monkeypatch.setattr(
        runner,
        "_proxy_identity",
        lambda _cfg: ["B0", "test"],
    )
    cache_entries = [
        {"path": f"libffcx_forms_{role}{suffix}", "bytes": 5,
         "mtime_ns": 1, "sha256": "d" * 64}
        for role in ("curl", "mass")
        for suffix in (".c", ".o", ".cpython-312-x86_64-linux-gnu.so", ".c.cached")
    ]
    snapshot_calls = [0]

    def snapshot(_cache):
        snapshot_calls[0] += 1
        return [] if snapshot_calls[0] == 1 else cache_entries

    monkeypatch.setattr(runner, "_r1_cache_snapshot", snapshot)
    allow_hit = [False]

    def build_mpc(*_args):
        if not allow_hit[0]:
            pytest.fail("stage must not build MPC")
        return SimpleNamespace(num_constraints=runner.H2A_FIXED_CONSTRAINT_COUNT)

    monkeypatch.setattr(runner, "build_double_floquet_mpc", build_mpc)
    monkeypatch.setattr(
        runner,
        "tabulate_task037_extra_h2a_cell_tensor",
        lambda *_args: pytest.fail("stage must not tabulate tensors"),
    )
    monkeypatch.setattr(
        runner,
        "build_task037_extra_h2a_block_cache",
        lambda *_args: pytest.fail("stage must not build factors"),
    )
    monkeypatch.setattr(
        runner, "MPI", SimpleNamespace(COMM_WORLD=SimpleNamespace(size=1))
    )
    result = runner._r1_run_stage_worker(
        SimpleNamespace(run_dir=str(tmp_path / "stage"))
    )
    assert result == 0
    allow_hit[0] = True
    hit_result = runner._r1_run_hit_worker(
        SimpleNamespace(run_dir=str(tmp_path / "stage"))
    )
    assert hit_result == 0
    summary = json.loads(
        (tmp_path / "stage" / "stage_summary.json").read_text()
    )
    assert summary["phase_identity"] == runner._r1_phase_identity("stage")
    hit = json.loads((tmp_path / "stage" / "hit_summary.json").read_text())
    assert hit["stage_manifest_sha256"] == runner._sha256_file(
        tmp_path / "stage" / "stage_summary.json"
    )
    assert hit["measurement"] == {
        "global_cells": 252,
        "local_nloc": 882,
        "global_rows": runner.H2A_FIXED_GLOBAL_ROWS,
        "constraint_count": runner.H2A_FIXED_CONSTRAINT_COUNT,
    }
    _progress_events = runner._r1_progress_events(
        tmp_path / "stage" / "hit_progress.jsonl"
    )
    assert _progress_events
    assert _progress_events[:2] == [
        "r0_record_validation_started", "r0_record_validation_ready"
    ]


def _rewrite_summary(root: Path, name: str, mutate) -> None:
    path = root / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    runner._write_json(path, runner.attach_evidence_sha256(payload))


@pytest.mark.parametrize(
    ("mutation", "check"),
    (("form_key", "forms"), ("cache_file", "cache"), ("cache_bytes", "cache"),
     ("compiler_child", "hit_cache_load"), ("measurement", "hit_measurement"),
     ("rss", "phase_resources")),
)
def test_r1_checker_fail_closed_mutations(tmp_path: Path, mutation: str, check: str):
    root = tmp_path / "raw"
    _write_good_raw(root)
    if mutation == "form_key":
        _rewrite_summary(root, "stage_summary.json", lambda item: item["forms"][0].pop("module_name"))
    elif mutation == "cache_file":
        (root / "jit_cache/libffcx_forms_curl.o").unlink()
    elif mutation == "cache_bytes":
        (root / "jit_cache/libffcx_forms_curl.c").write_bytes(b"changed")
    elif mutation == "compiler_child":
        path = root / "hit_timeline.jsonl"
        sample = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        sample["compiler_descendant_pids"] = [999]
        path.write_text(json.dumps(sample) + "\n" + path.read_text(encoding="utf-8").split("\n", 1)[1], encoding="utf-8")
    elif mutation == "measurement":
        _rewrite_summary(root, "hit_summary.json", lambda item: item["measurement"].__setitem__("global_rows", 1))
    else:
        path = root / "stage_timeline.jsonl"
        path.write_text(path.read_text(encoding="utf-8").replace('"rss_bytes": 100', '"rss_bytes": 1800000000'), encoding="utf-8")
    result = runner._r1_check_raw(root)
    assert result["pass"] is False
    assert result["watchdog_checks"][check] is False


def test_r1_good_checker_and_hash_bound_mutations(tmp_path: Path):
    root = tmp_path / "raw"
    _write_good_raw(root)
    result = runner._r1_check_raw(root)
    assert result["pass"], result["problems"]
    assert result["measurements"]["r0_authority"]["class_count"] == 24
    assert result["measurements"]["stage"] == {
        **result["measurements"]["stage"],
        "completion_elapsed_seconds": 1.0,
        "process_tree_peak_rss_bytes": 100,
        "swap_bytes": 0,
        "compiler_descendant_pids": [101],
        "compiler_descendant_count": 1,
        "processes_gone_before_hit": True,
    }
    assert result["measurements"]["hit"]["measurement"] == {
        "global_cells": 252, "local_nloc": 882,
        "global_rows": runner.H2A_FIXED_GLOBAL_ROWS,
        "constraint_count": runner.H2A_FIXED_CONSTRAINT_COUNT,
    }
    assert result["measurements"]["hit"]["compiler_child_process_count"] == 0
    assert result["measurements"]["hit"]["form_jit_cache_hit"] is True
    assert result["measurements"]["hit"]["c_source_regeneration"] is False


def test_r1_actual_p2_cold_then_cache_hit(tmp_path: Path):
    cfg = target_stage4_config(degree=2, h_nm=10.0)
    mesh_data = build_airbox_mesh_3d(cfg, tmp_path / "mesh")
    function_space = _create_nedelec_space(mesh_data.mesh, cfg)
    curl_ufl, mass_ufl = runner._proxy_ufl_forms(
        function_space, mesh_data, cfg
    )
    cache_dir = tmp_path / "dedicated-jit-cache"
    cache_dir.mkdir()
    cold_forms = [
        fem.form(form, jit_options=runner._form_jit_options(cache_dir))
        for form in (curl_ufl, mass_ufl)
    ]
    assert all(
        runner._r1_form_code_state(form.code)[0]
        == "cold_decl_impl_generated"
        for form in cold_forms
    )
    snapshot = runner._r1_cache_snapshot(cache_dir)
    cold_records = [
        runner._r1_form_record(
            role=role, ufl_form=ufl, compiled_form=compiled,
            cache_dir=cache_dir, cfg=cfg, function_space=function_space,
        )
        for role, ufl, compiled in zip(
            ("curl", "mass"), (curl_ufl, mass_ufl), cold_forms
        )
    ]
    runner._r1_bind_cache_files(cold_records, snapshot)
    assert all(runner._r1_cache_files_valid(form["cache_files"]) for form in cold_records)
    del cold_forms
    hit_forms = [
        fem.form(form, jit_options=runner._form_jit_options(cache_dir))
        for form in (curl_ufl, mass_ufl)
    ]
    assert all(
        runner._r1_form_code_state(form.code)[0]
        == "hit_no_new_decl_impl"
        for form in hit_forms
    )
    hit_records = [
        runner._r1_form_record(
            role=role, ufl_form=ufl, compiled_form=compiled,
            cache_dir=cache_dir, cfg=cfg, function_space=function_space,
        )
        for role, ufl, compiled in zip(
            ("curl", "mass"), (curl_ufl, mass_ufl), hit_forms
        )
    ]
    after = runner._r1_cache_snapshot(cache_dir)
    runner._r1_bind_cache_files(hit_records, after)
    assert after == snapshot
    assert runner._r1_forms_match(cold_records, hit_records, cache_dir)
