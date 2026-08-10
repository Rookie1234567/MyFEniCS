from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks import run_task037_extra_h2 as runner
from benchmarks.task033_case090_pde_core import attach_evidence_sha256
from src.solvers.hcurl_exact_class_block_cache import (
    make_task037_extra_h2a_class_key,
)


def _source_identity() -> dict[str, object]:
    return {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _class_item(
    *, class_id: int = 0, cell_count: int = 4, nloc: int = 4
) -> dict[str, object]:
    reduced = 3
    return {
        "class_id": class_id,
        "class_key_sha256": "1" * 64,
        "cell_count": cell_count,
        "material_tag": 1,
        "material_identity": ["epsilon_raw", [2.0, 0.0], "epsilon_abs", 2.0],
        "cell_widths": [1.0, 1.0, 1.0],
        "orientation": [0],
        "constraint_pattern_sha256": "2" * 64,
        "constraint_pattern_kinds": ["edge:x"],
        "constraint_pattern_entry_count": 1,
        "local_nloc": nloc,
        "constrained_unique_reduced_row_count": reduced,
        "raw_lu_values_upper_bound_bytes": nloc * nloc * 16,
        "raw_lu_pivots_upper_bound_bytes": nloc * 4,
        "constrained_lu_values_upper_bound_bytes": reduced * reduced * 16,
        "constrained_lu_pivots_upper_bound_bytes": reduced * 4,
    }


def _case(
    label: str, degree: int, h_nm: float, *, cells: int, rows: int, constraints: int
) -> dict[str, object]:
    nloc = 882 if label == "p6_h10" else 4
    item = _class_item(cell_count=cells, nloc=nloc)
    inventory = [item]
    raw_values = nloc * nloc * 16
    raw_pivots = nloc * 4
    reduced_values = 3 * 3 * 16
    reduced_pivots = 3 * 4
    metadata_bytes = len(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    )
    audit = {
        "schema": f"{runner.R0_SCHEMA}.case-audit.v1",
        "global_cell_count": cells,
        "local_cell_count": cells,
        "global_rows": rows,
        "constraint_count": constraints,
        "unique_class_count": 1,
        "class_inventory": inventory,
        "class_inventory_digest": runner._r0_digest(tuple(inventory)),
        "independent_discovery_digest": runner._r0_digest(tuple(inventory)),
        "deterministic_discovery": True,
        "metadata_bytes": metadata_bytes,
        "raw_lu_values_upper_bound_global_sum_bytes": raw_values,
        "raw_lu_pivots_upper_bound_global_sum_bytes": raw_pivots,
        "constrained_lu_values_upper_bound_global_sum_bytes": reduced_values,
        "constrained_lu_pivots_upper_bound_global_sum_bytes": reduced_pivots,
        "factor_upper_bound_metadata_bytes": metadata_bytes,
        "factor_upper_bound_metadata_basis": "canonical_utf8_class_inventory",
        "factor_upper_bound_raw_with_metadata_bytes": raw_values
        + raw_pivots
        + metadata_bytes,
        "factor_upper_bound_constrained_with_metadata_bytes": reduced_values
        + reduced_pivots
        + metadata_bytes,
        "factor_upper_bound_requires_numeric_dedup": False,
        "factor_upper_bound_not_retained": True,
        "global_constraint_matrix_materialized": False,
        "inventory_only": True,
        "forbidden_absolute_identity": False,
        "identity_fields": [
            "cell_widths",
            "material_tag",
            "material_identity",
            "orientation",
            "constraint_pattern",
            "local_dof_ordering",
            "proxy_identity",
        ],
        "constraint_pattern_semantics": "normalized local expansion",
        "finite": True,
        "identity": runner._r0_identity(),
    }
    return {
        "label": label,
        "degree": degree,
        "h_nm": h_nm,
        "axis_cell_counts": [2, 2, 1],
        "global_cell_count": cells,
        "local_cell_count": cells,
        "global_rows": rows,
        "local_rows": rows,
        "constraint_count": constraints,
        "audit": audit,
    }


def _runtime() -> dict[str, object]:
    return {
        "qualified_activation": "1",
        "sys_executable": sys.executable,
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
    }


def _build_raw_fixture(root: Path, *, mutate=None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    worker = {
        "schema": runner.R0_WORKER_SCHEMA,
        "status": "measurement_complete",
        "scope": runner._r0_scope(),
        "source_at_start": _source_identity(),
        "source_at_end": _source_identity(),
        "runtime_identity": _runtime(),
        "cases": [
            _case("p6_h10", 6, 10.0, cells=4, rows=173802, constraints=9210),
            _case("p2_h10", 2, 10.0, cells=4, rows=100, constraints=4),
            _case("p2_h5", 2, 5.0, cells=16, rows=400, constraints=16),
        ],
        "error": None,
        "inventory_only": True,
    }
    watchdog = {
        "schema": runner.R0_WATCHDOG_SCHEMA,
        "status": "pass",
        "run_dir": str(root),
        "command": runner._r0_worker_command(root, sys.executable),
        "scope": runner._r0_scope(),
        "runtime_identity": _runtime(),
        "source_at_start": _source_identity(),
        "source_at_end": _source_identity(),
        "source_clean_and_stable": True,
        "return_code": 0,
        "termination": None,
        "completion_elapsed_seconds": 1.0,
        "live_sample_count": 1,
        "process_tree_peak_rss_bytes": 100,
        "process_tree_swap_bytes": 0,
        "worker_summary_present": True,
        "worker_evidence_valid": True,
        "worker_qualification_pass": True,
    }
    if mutate is not None:
        mutate(worker, watchdog)
    worker = attach_evidence_sha256(worker)
    runner._write_json(root / "run_summary.json", worker)
    (root / "r0_worker_stdout.txt").write_text("", encoding="utf-8")
    marker_events = (
        "mesh_build_started",
        "mesh_build_ready",
        "function_space_started",
        "function_space_ready",
        "floquet_mpc_started",
        "floquet_mpc_ready",
        "class_discovery_started",
        "class_discovery_ready",
        "case_release_started",
        "case_release_ready",
    )
    marker_lines = []
    for label, _degree, _h_nm in runner.R0_CASES:
        marker_lines.extend(
            json.dumps(
                {
                    "schema": runner.R0_PROGRESS_SCHEMA,
                    "event": event,
                    "case": label,
                }
            )
            for event in marker_events
        )
    marker_lines.append(
        json.dumps(
            {
                "schema": runner.R0_PROGRESS_SCHEMA,
                "event": "worker_summary_started",
                "case": None,
            }
        )
    )
    (root / "r0_progress.jsonl").write_text(
        "\n".join(marker_lines) + "\n", encoding="utf-8"
    )
    runner._write_json(root / "r0_root_pid.json", {"schema": "task037.extra.h2a.r0.root.v1", "root_pid": 123})
    (root / "r0_watchdog_timeline.jsonl").write_text(
        json.dumps(
            {
                "schema": runner.R0_PROGRESS_SCHEMA,
                "sample_kind": "worker",
                "root_pid": 123,
                "pids": [123],
                "process_count": 1,
                "rss_bytes": watchdog["process_tree_peak_rss_bytes"],
                "swap_bytes": watchdog["process_tree_swap_bytes"],
                "all_status_readable": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    names = (
        "r0_worker_stdout.txt",
        "r0_progress.jsonl",
        "r0_watchdog_timeline.jsonl",
        "r0_root_pid.json",
        "run_summary.json",
    )
    watchdog["raw_artifacts"] = {
        name: {
            "path": name,
            "bytes": (root / name).stat().st_size,
            "sha256": runner._sha256_file(root / name),
        }
        for name in names
    }
    watchdog = attach_evidence_sha256(watchdog)
    runner._write_json(root / "r0_watchdog_summary.json", watchdog)


def test_r0_parser_and_direct_singleton_command_are_fixed():
    args = runner._parser().parse_args(["r0-watchdog", "--run-dir", "relative"])
    assert args.command == "r0-watchdog"
    command = runner._r0_worker_command(Path("relative"), "/qualified/bin/python")
    assert "mpiexec" not in command
    assert command[0] == "/qualified/bin/python"
    assert command[3] == "r0-worker"
    with pytest.raises(SystemExit):
        runner._parser().parse_args(["r0-worker", "--run-dir", "x", "--degree", "2"])


def test_r0_reduced_row_union_handles_free_axes_corner_and_master_dedup():
    class FakeIndexMap:
        def local_to_global(self, local_rows):
            return np.asarray(local_rows, dtype=np.int64) + 100

    blocks = (
        SimpleNamespace(
            kind="x",
            slave_local_dofs=(1,),
            slave_global_dofs=(101,),
            master_global_dofs=(100, 200),
            coefficient_transform=np.asarray([[1.0, 0.0]], dtype=np.complex128),
        ),
        SimpleNamespace(
            kind="y",
            slave_local_dofs=(2,),
            slave_global_dofs=(102,),
            master_global_dofs=(200, 202),
            coefficient_transform=np.asarray([[0.0, 1.0]], dtype=np.complex128),
        ),
        SimpleNamespace(
            kind="corner",
            slave_local_dofs=(3,),
            slave_global_dofs=(103,),
            master_global_dofs=(202, 203),
            coefficient_transform=np.asarray([[1.0, 0.0]], dtype=np.complex128),
        ),
    )
    assert runner._r0_reduced_row_count(
        (), (0, 1, 2, 3), index_map=FakeIndexMap(), index_map_bs=1,
        phase_x=1.0 + 0.0j, phase_y=1.0 + 0.0j
    ) == 4
    assert runner._r0_reduced_row_count(
        blocks, (0, 1, 2, 3), index_map=FakeIndexMap(), index_map_bs=1,
        phase_x=1.0 + 0.0j, phase_y=1.0 + 0.0j
    ) == 2


def test_r0_key_excludes_absolute_identity_components():
    pattern = (
        {
            "topology": {
                "entity_kind": "edge",
                "direction": "x",
                "vertex_permutation": (0, 1),
                "cell_type": "hexahedron",
            },
            "local_slave": 0,
            "phase": 1.0 + 0.0j,
            "columns": ((1, 1.0 + 0.0j),),
        },
    )
    kwargs = {
        "cell_widths": (1.0, 1.0, 1.0),
        "material_tag": 1,
        "material_identity": ("epsilon", 2.0),
        "orientation": (0,),
        "constraint_pattern": pattern,
        "canonical_local_basis_signature": ("N1curl", 2, "canonical"),
        "proxy_identity": ("B0", "k0"),
    }
    assert make_task037_extra_h2a_class_key(**kwargs) == make_task037_extra_h2a_class_key(**kwargs)
    assert not runner._r0_has_forbidden_identity({"identity_fields": ["local_dof_ordering"]})
    assert not runner._r0_has_forbidden_identity(("N1curl", "canonical", "phase"))
    assert runner._r0_has_forbidden_identity({"global_row": 17})
    assert runner._r0_has_forbidden_identity({"owner": 1})
    assert runner._r0_has_forbidden_identity(("key", "global_row"))
    assert runner._r0_has_forbidden_identity(("owner", 3))
    assert runner._r0_has_forbidden_identity(("cell_id", 3))


def test_r0_actual_p2_discovery_never_enters_form_or_factor_path(monkeypatch, tmp_path):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("R0 must not call form/tensor/cache code")

    monkeypatch.setattr(runner, "_proxy_forms", forbidden)
    monkeypatch.setattr(runner.fem, "form", forbidden)
    monkeypatch.setattr(runner, "tabulate_task037_extra_h2a_cell_tensor", forbidden)
    monkeypatch.setattr(runner, "build_task037_extra_h2a_block_cache", forbidden)
    marker_stream = StringIO()
    result = runner._r0_run_case(
        comm=runner.MPI.COMM_SELF,
        case={"label": "p2_h10", "degree": 2, "h_nm": 10.0},
        run_dir=tmp_path,
        marker_stream=marker_stream,
        started=runner.time.perf_counter(),
    )
    assert result["global_cell_count"] > 0
    assert result["audit"]["unique_class_count"] <= 64
    assert result["audit"]["deterministic_discovery"] is True
    events = [json.loads(line)["event"] for line in marker_stream.getvalue().splitlines()]
    assert events.index("floquet_mpc_ready") < events.index("class_discovery_started")
    assert "form_compile_started" not in events
    assert "factorization_started" not in events


def test_r0_checker_good_fixture_projects_measurements(tmp_path):
    _build_raw_fixture(tmp_path)
    result = runner._r0_check_raw(tmp_path)
    assert result["pass"] is True
    assert result["measurements"]["p6_h10"]["global_rows"] == 173802
    assert result["measurements"]["p6_h10"]["local_nloc"] == 882
    assert result["measurements"]["p2_h10"]["global_cells"] == 4
    assert result["measurements"]["p2_h5"]["global_cells"] == 16
    assert result["measurements"]["refinement"]["class_growth_strictly_sublinear"] is True
    assert result["measurements"]["p6_h10"]["class_inventory"]
    assert result["measurements"]["p6_h10"]["identity"] == runner._r0_identity()
    assert result["measurements"]["p2_h10"]["inventory_digest"]
    assert result["measurements"]["raw_run_dir"] == str(tmp_path)
    assert result["watchdog_checks"]["runtime_identity_match"] is True


@pytest.mark.parametrize(
    "mutation",
    (
        "class_count",
        "digest",
        "both_digests",
        "absolute_identity",
        "identity_flag",
        "refinement",
        "rows",
        "constraints",
        "scope",
        "rss",
        "swap",
        "metadata",
        "missing_key",
        "runtime_mismatch",
        "command",
        "source_dirty",
        "run_dir",
        "raw_hash",
        "marker_form",
    ),
)
def test_r0_checker_fail_closed_mutations(tmp_path, mutation):
    def mutate(worker, watchdog):
        p6 = worker["cases"][0]
        if mutation == "class_count":
            p6["audit"]["unique_class_count"] = 65
        elif mutation == "digest":
            p6["audit"]["class_inventory_digest"] = "0" * 64
        elif mutation == "both_digests":
            p6["audit"]["class_inventory_digest"] = "0" * 64
            p6["audit"]["independent_discovery_digest"] = "0" * 64
        elif mutation == "absolute_identity":
            p6["audit"]["identity_fields"] = ["global_row"]
        elif mutation == "identity_flag":
            p6["audit"]["identity"]["condensation"] = True
        elif mutation == "refinement":
            worker["cases"][2]["global_cell_count"] = 4
        elif mutation == "rows":
            p6["global_rows"] = 173801
        elif mutation == "constraints":
            p6["constraint_count"] = 9209
        elif mutation == "scope":
            worker["scope"]["fine_space"] = "condensed"
        elif mutation == "rss":
            watchdog["process_tree_peak_rss_bytes"] = runner.R0_RSS_LIMIT_BYTES
        elif mutation == "swap":
            watchdog["process_tree_swap_bytes"] = 1
        elif mutation == "metadata":
            p6["audit"]["metadata_bytes"] += 1
        elif mutation == "missing_key":
            del p6["audit"]["identity"]["cell_schur_matrix_nnz"]
        elif mutation == "runtime_mismatch":
            watchdog["runtime_identity"]["threads"]["OMP_NUM_THREADS"] = "2"
        elif mutation == "command":
            watchdog["command"][3] = "r0-worker-mutated"
        elif mutation == "source_dirty":
            worker["source_at_start"]["tracked_source_dirty"] = True
        elif mutation == "run_dir":
            watchdog["run_dir"] = str(Path(watchdog["run_dir"]).parent / "other")

    _build_raw_fixture(tmp_path, mutate=mutate)
    if mutation == "raw_hash":
        (tmp_path / "r0_progress.jsonl").write_text(
            json.dumps(
                {
                    "schema": runner.R0_PROGRESS_SCHEMA,
                    "event": "raw_hash_mutation",
                    "case": "p6_h10",
                }
            )
            + "\n",
            encoding="utf-8",
        )
    elif mutation == "marker_form":
        with (tmp_path / "r0_progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "schema": runner.R0_PROGRESS_SCHEMA,
                        "event": "form_compile_started",
                        "case": "p6_h10",
                    }
                )
                + "\n"
            )
    result = runner._r0_check_raw(tmp_path)
    assert result["pass"] is False
    assert result["problems"]
