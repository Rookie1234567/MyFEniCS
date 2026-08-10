from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest

import benchmarks.run_task037_extra_h2 as h2
from benchmarks.task033_case090_pde_core import attach_evidence_sha256
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.hcurl_assembly_time_condensation import (
    _cell_integral_kernels,
)
from src.solvers.hcurl_exact_class_block_cache import build_b0_proxy_tensor
from src.constraints.floquet_3d_high_order import floquet_geometry_tolerance


def _identity(sha: str = "a" * 40):
    return {
        "source_commit_full_sha": sha,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _audit(*, global_cell_count: int, class_count: int, global_rows: int):
    inventory = [
        {
            "class_id": 0,
            "class_key_sha256": "1" * 64,
            "numeric_tensor_sha256": "2" * 64,
            "factor_id": 0,
        }
    ]
    for class_id in range(1, class_count):
        inventory.append(
            {
                "class_id": class_id,
                "class_key_sha256": format(class_id + 1, "x") * 64,
                "numeric_tensor_sha256": format(class_id + 2, "x") * 64,
                "factor_id": class_id,
            }
        )
    cell_class_ids = list(range(class_count))
    cell_factor_ids = list(range(class_count))
    digest = h2.hashlib.sha256(
        h2._key_json(
            (
                tuple(inventory),
                tuple(cell_class_ids),
                tuple(cell_factor_ids),
            )
        ).encode("utf-8")
    ).hexdigest()
    audit = {
        "unique_class_count": class_count,
        "global_cell_count": global_cell_count,
        "global_rows": global_rows,
        "global_unique_factor_count": class_count,
        "global_factor_count_sum": class_count,
        "numeric_hash_dedup_count": 0,
        "retained_block_factor_payload_with_metadata_global_sum_bytes": 200,
        "retained_numeric_payload_components": {
            "factor_values_bytes": 128,
            "factor_pivot_indices_bytes": 16,
        },
        "retained_numeric_payload_local_bytes": 144,
        "retained_numeric_payload_global_sum_bytes": 144,
        "retained_numeric_payload_global_max_bytes": 144,
        "retained_block_factor_payload_local_bytes": 144,
        "retained_block_factor_metadata_global_sum_bytes": 56,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "retained_dense_cell_matrix_count": 0,
        "per_cell_factor_count": 0,
        "slab_factor_count": 0,
        "ksp_created": False,
        "dtn_used": False,
        "inventory_only": True,
        "Bc_inverse_implemented": False,
        "ordinary_default_changed": False,
        "factor_values_finite": True,
        "factor_pivots_finite": True,
        "deterministic_class_inventory_closed": True,
        "deterministic_class_inventory_sha256": digest,
        "class_inventory": inventory,
        "cell_class_ids": cell_class_ids,
        "cell_factor_ids": cell_factor_ids,
    }
    return audit


def _worker_raw():
    runtime_executable = str(h2.ROOT / ".venv" / "bin" / "python")

    def case(
        label,
        degree,
        h_nm,
        cell_count,
        class_count,
        global_rows,
        constraint_count,
    ):
        return {
            "label": label,
            "degree": degree,
            "h_nm": h_nm,
            "global_cell_count": cell_count,
            "global_rows": global_rows,
            "constraint_count": constraint_count,
            "cache_audit": _audit(
                global_cell_count=cell_count,
                class_count=class_count,
                global_rows=global_rows,
            ),
        }

    return {
        "schema": h2.H2A_WORKER_SCHEMA,
        "status": "measurement_complete",
        "scope": h2._fixed_scope(),
        "source_at_start": _identity(),
        "source_at_end": _identity(),
        "runtime_identity": {
            "qualified_activation": "1",
            "sys_executable": runtime_executable,
            "threads": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            },
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
        },
        "cases": [
            case("p6_h10", 6, 10.0, 10, 2, 173802, 9210),
            case("p2_h10", 2, 10.0, 10, 2, 20, 1),
            case("p2_h5", 2, 5.0, 100, 3, 20, 1),
        ],
        "refinement": {
            "coarse": {
                "label": "p2_h10",
                "global_cell_count": 10,
                "unique_class_count": 2,
            },
            "refined": {
                "label": "p2_h5",
                "global_cell_count": 100,
                "unique_class_count": 3,
            },
        },
        "inventory_only": True,
        "Bc_inverse_implemented": False,
        "error": None,
    }


def _write_good_raw(run_dir: Path):
    worker = attach_evidence_sha256(_worker_raw())
    (run_dir / "run_summary.json").write_text(
        json.dumps(worker, sort_keys=True) + "\n", encoding="utf-8"
    )
    timeline = [
        {
            "schema": h2.H2A_PROGRESS_SCHEMA,
            "sample_kind": "worker",
            "rss_bytes": 100,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
        {
            "schema": h2.H2A_PROGRESS_SCHEMA,
            "sample_kind": "worker",
            "rss_bytes": 200,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
        {"schema": h2.H2A_PROGRESS_SCHEMA, "sample_kind": "final"},
    ]
    (run_dir / "watchdog_timeline.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in timeline),
        encoding="utf-8",
    )
    runtime_identity = worker["runtime_identity"]
    watchdog = attach_evidence_sha256(
        {
            "schema": h2.H2A_WATCHDOG_SCHEMA,
            "status": "pass",
            "command": h2._h2a_worker_command(
                run_dir, runtime_identity["sys_executable"]
            ),
            "scope": h2._fixed_scope(),
            "runtime_identity": runtime_identity,
            "source_at_start": _identity(),
            "source_at_end": _identity(),
            "source_clean_and_stable": True,
            "return_code": 0,
            "termination": None,
            "completion_elapsed_seconds": 1.5,
            "process_tree_peak_rss_bytes": 200,
            "process_tree_swap_bytes": 0,
            "worker_summary_present": True,
            "worker_evidence_valid": True,
            "worker_qualification_pass": True,
        }
    )
    (run_dir / "watchdog_summary.json").write_text(
        json.dumps(watchdog, sort_keys=True) + "\n", encoding="utf-8"
    )
    return worker, watchdog


def test_h2a_fixed_parser_has_no_relaxation_arguments():
    parser = h2._parser()
    worker = parser.parse_args(["worker", "--run-dir", "raw"])
    watchdog = parser.parse_args(["watchdog", "--run-dir", "raw"])
    checker = parser.parse_args(["check", "--run-dir", "raw", "--output", "check.json"])
    assert worker.command == "worker"
    assert watchdog.command == "watchdog"
    assert checker.command == "check"
    with pytest.raises(SystemExit):
        parser.parse_args(["worker", "--run-dir", "raw", "--degree", "2"])


def test_h2a_worker_uses_direct_qualified_singleton_command():
    run_dir = Path("relative-raw")
    executable = str(h2.ROOT / ".venv" / "bin" / "python")
    command = h2._h2a_worker_command(run_dir, executable)
    assert command[0] == executable
    assert "mpiexec" not in command
    assert command[1:5] == [
        "-m",
        "benchmarks.run_task037_extra_h2",
        "worker",
        "--run-dir",
    ]
    assert command[5] == str(run_dir.resolve())
    assert h2._fixed_scope()["mpi_size"] == 1
    assert h2._fixed_scope()["launch_mode"] == "mpi_singleton_direct"


def test_h2a_progress_marker_flushes_and_has_narrow_schema():
    class FlushCapture(io.StringIO):
        def __init__(self):
            super().__init__()
            self.flush_count = 0

        def flush(self):
            self.flush_count += 1
            return super().flush()

    stream = FlushCapture()
    marker = h2._emit_marker(
        stream,
        event="cache_ready",
        started=h2.time.perf_counter(),
        rank=0,
        case={"label": "p2_h10", "degree": 2, "h_nm": 10.0},
        class_id=1,
        cell_count=4,
        local_rows=8,
        global_rows=8,
    )
    record = json.loads(stream.getvalue())
    assert stream.flush_count == 1
    assert record["schema"] == h2.H2A_PROGRESS_SCHEMA
    assert record["event"] == marker["event"] == "cache_ready"
    assert record["class_id"] == 1


def test_h2a_checker_good_raw_and_refinement_recompute(tmp_path: Path):
    _write_good_raw(tmp_path)
    result = h2._check_h2a_raw(tmp_path)
    assert result["pass"] is True
    assert result["worker_qualification"]["pass"] is True
    assert result["timeline"]["peak_rss_bytes"] == 200
    measurements = result["measurements"]
    assert measurements["mpi_size"] == 1
    assert measurements["p6_h10"]["global_rows"] == 173802
    assert measurements["p6_h10"]["constraint_count"] == 9210
    assert measurements["p6_h10"]["global_cell_count"] == 10
    assert measurements["p6_h10"]["unique_class_count"] == 2
    assert measurements["p6_h10"]["global_unique_factor_count"] == 2
    assert measurements["p6_h10"]["numeric_hash_dedup_count"] == 0
    assert measurements["p2_h10"]["global_cell_count"] == 10
    assert measurements["p2_h5"]["global_cell_count"] == 100
    assert measurements["refinement"]["class_growth_strictly_sublinear"] is True
    assert measurements["process_tree"]["peak_rss_bytes"] == 200
    assert {
        item["path"] for item in result["raw_artifacts"].values()
    } == {
        "run_summary.json",
        "watchdog_summary.json",
        "watchdog_timeline.jsonl",
    }


@pytest.mark.parametrize("tag_name", ("air", "substrate", "grating"))
def test_h2a_production_material_and_proxy_identity(tag_name: str):
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    tag = int(getattr(cfg.tags, tag_name))
    expected_epsilon = {
        int(cfg.tags.air): complex(cfg.eps_air),
        int(cfg.tags.substrate): complex(cfg.eps_substrate),
        int(cfg.tags.grating): complex(cfg.eps_grating),
    }[tag]
    epsilon = h2._material_epsilon(cfg, tag)
    identity = h2._material_identity(cfg, tag)
    assert epsilon == expected_epsilon
    assert identity == (
        "epsilon_raw",
        expected_epsilon,
        "epsilon_abs",
        float(abs(expected_epsilon)),
        "mu_r",
        complex(cfg.mu_r),
        "curl_coefficient",
        complex(1.0 / cfg.mu_r),
    )
    assert h2._proxy_identity(cfg) == (
        "B0",
        "K_curl+k0^2*M_abs_epsilon",
        "k0",
        float(cfg.k0),
        "mu_r",
        complex(cfg.mu_r),
        "mass_coefficient",
        "unit-before-abs-epsilon",
    )


def test_h2a_default_proxy_forms_match_tagged_cell_authority(tmp_path: Path):
    cfg = target_stage4_config(degree=2, h_nm=10.0)
    mesh_data = build_airbox_mesh_3d(cfg, tmp_path / "production_mesh")
    function_space = _create_nedelec_space(mesh_data.mesh, cfg)
    curl_form, mass_form = h2._proxy_forms(function_space, mesh_data, cfg)
    assert tuple(sorted(_cell_integral_kernels(curl_form))) == (-1,)
    assert tuple(sorted(_cell_integral_kernels(mass_form))) == (-1,)

    u = h2.ufl.TrialFunction(function_space)
    v = h2.ufl.TestFunction(function_space)
    tagged_dx = h2.ufl.Measure(
        "dx",
        domain=mesh_data.mesh,
        subdomain_data=mesh_data.cell_tags,
    )
    tags = (cfg.tags.air, cfg.tags.substrate, cfg.tags.grating)
    tagged_curl = h2.fem.form(
        sum(
            h2.PETSc.ScalarType(1.0 / cfg.mu_r)
            * h2.ufl.inner(h2.ufl.curl(u), h2.ufl.curl(v))
            * tagged_dx(int(tag))
            for tag in tags
        )
    )
    tagged_mass = h2.fem.form(
        sum(
            h2.PETSc.ScalarType(1.0) * h2.ufl.inner(u, v) * tagged_dx(int(tag))
            for tag in tags
        )
    )
    owned_cells = int(mesh_data.mesh.topology.index_map(3).size_local)
    actual_tags = h2._cell_tag_array(mesh_data.cell_tags, owned_cells)
    tolerance = floquet_geometry_tolerance(cfg)
    assert actual_tags.size > 0
    for tag in np.unique(actual_tags):
        cell = int(np.flatnonzero(actual_tags == tag)[0])
        new_curl, _, new_curl_info = h2.tabulate_task037_extra_h2a_cell_tensor(
            curl_form,
            function_space,
            mesh_data.cell_tags,
            cell,
            geometry_tolerance=tolerance,
        )
        old_curl, _, old_curl_info = h2.tabulate_task037_extra_h2a_cell_tensor(
            tagged_curl,
            function_space,
            mesh_data.cell_tags,
            cell,
            geometry_tolerance=tolerance,
        )
        new_mass, _, new_mass_info = h2.tabulate_task037_extra_h2a_cell_tensor(
            mass_form,
            function_space,
            mesh_data.cell_tags,
            cell,
            geometry_tolerance=tolerance,
        )
        old_mass, _, old_mass_info = h2.tabulate_task037_extra_h2a_cell_tensor(
            tagged_mass,
            function_space,
            mesh_data.cell_tags,
            cell,
            geometry_tolerance=tolerance,
        )
        assert new_curl_info == old_curl_info == new_mass_info == old_mass_info
        for observed, reference in ((new_curl, old_curl), (new_mass, old_mass)):
            assert np.all(np.isfinite(observed))
            assert np.all(np.isfinite(reference))
            assert np.linalg.norm(observed - reference) / np.linalg.norm(reference) <= 1.0e-11
        new_b0 = build_b0_proxy_tensor(
            new_curl,
            new_mass,
            k0=float(cfg.k0),
            abs_epsilon=float(abs(h2._material_epsilon(cfg, int(tag)))),
        )
        old_b0 = build_b0_proxy_tensor(
            old_curl,
            old_mass,
            k0=float(cfg.k0),
            abs_epsilon=float(abs(h2._material_epsilon(cfg, int(tag)))),
        )
        assert np.linalg.norm(new_b0 - old_b0) / np.linalg.norm(old_b0) <= 1.0e-11


def test_h2a_proxy_forms_bind_fixed_o0_compile_policy(
    monkeypatch, tmp_path: Path
):
    cfg = target_stage4_config(degree=2, h_nm=10.0)
    mesh_data = build_airbox_mesh_3d(cfg, tmp_path / "policy_mesh")
    function_space = _create_nedelec_space(mesh_data.mesh, cfg)
    calls = []

    def capture_form(form, **kwargs):
        calls.append(kwargs)
        return form

    monkeypatch.setattr(h2.fem, "form", capture_form)
    h2._proxy_forms(function_space, mesh_data, cfg)
    expected = {
        "jit_options": {
            "cffi_extra_compile_args": ["-O0", "-g0"],
        }
    }
    assert calls == [expected, expected]
    assert h2._fixed_scope()["form_jit_compile_policy"] == expected[
        "jit_options"
    ]


@pytest.mark.parametrize("field", ("global_rows", "constraint_count"))
def test_h2a_p6_identity_is_frozen(tmp_path: Path, field: str):
    _write_good_raw(tmp_path)
    worker_path = tmp_path / "run_summary.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    worker["cases"][0][field] = 1
    worker_path.write_text(
        json.dumps(attach_evidence_sha256(worker), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert h2._check_h2a_raw(tmp_path)["pass"] is False


def test_h2a_runtime_identity_accepts_repository_and_qualified_venv_paths():
    identity = _worker_raw()["runtime_identity"]
    assert h2._runtime_identity_is_qualified(identity)
    identity["sys_executable"] = str(
        (h2.ROOT / ".venv").resolve() / "bin" / "python"
    )
    assert h2._runtime_identity_is_qualified(identity)
    identity["sys_executable"] = "/repo/.venv/bin/python"
    assert not h2._runtime_identity_is_qualified(identity)


def test_h2a_compact_measurements_fail_closed_when_source_is_missing(
    tmp_path: Path,
):
    _write_good_raw(tmp_path)
    worker_path = tmp_path / "run_summary.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    del worker["cases"][0]["global_rows"]
    worker_path.write_text(
        json.dumps(attach_evidence_sha256(worker), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = h2._check_h2a_raw(tmp_path)
    assert result["pass"] is False
    assert result["measurements"] is None


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_cell_schur",
        "class_limit",
        "factor_limit",
        "swap",
        "rss",
        "refinement",
        "refinement_binding",
        "cell_factor",
        "factor_count",
        "source_dirty",
        "worker_status",
    ),
)
def test_h2a_checker_fails_closed_for_representative_mutations(
    tmp_path: Path, mutation: str
):
    _write_good_raw(tmp_path)
    worker_path = tmp_path / "run_summary.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    timeline_path = tmp_path / "watchdog_timeline.jsonl"
    if mutation == "missing_cell_schur":
        del worker["cases"][0]["cache_audit"]["cell_schur_matrix_nnz"]
    elif mutation == "class_limit":
        worker["cases"][0]["cache_audit"]["unique_class_count"] = 33
    elif mutation == "factor_limit":
        worker["cases"][0]["cache_audit"][
            "retained_block_factor_payload_with_metadata_global_sum_bytes"
        ] = h2.H2A_FACTOR_PAYLOAD_LIMIT_BYTES + 1
    elif mutation == "refinement":
        worker["refinement"]["refined"]["unique_class_count"] = 20
    elif mutation == "refinement_binding":
        worker["refinement"]["coarse"]["global_cell_count"] = 11
    elif mutation == "cell_factor":
        audit = worker["cases"][0]["cache_audit"]
        audit["cell_factor_ids"][0] = 1
        audit["deterministic_class_inventory_sha256"] = h2.hashlib.sha256(
            h2._key_json(
                (
                    tuple(audit["class_inventory"]),
                    tuple(audit["cell_class_ids"]),
                    tuple(audit["cell_factor_ids"]),
                )
            ).encode("utf-8")
        ).hexdigest()
    elif mutation == "factor_count":
        worker["cases"][0]["cache_audit"]["global_unique_factor_count"] = 1
    elif mutation == "source_dirty":
        worker["source_at_end"]["tracked_source_dirty"] = True
    elif mutation == "worker_status":
        worker["status"] = "gate_failed"
    if mutation in {"swap", "rss"}:
        timeline = [
            {
                "schema": h2.H2A_PROGRESS_SCHEMA,
                "sample_kind": "worker",
                "rss_bytes": (
                    h2.H2A_RSS_LIMIT_BYTES + 1
                    if mutation == "rss"
                    else 200
                ),
                "swap_bytes": 1 if mutation == "swap" else 0,
                "all_status_readable": True,
            }
        ]
        timeline_path.write_text(
            "".join(json.dumps(item) + "\n" for item in timeline),
            encoding="utf-8",
        )
    worker_path.write_text(
        json.dumps(attach_evidence_sha256(worker), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = h2._check_h2a_raw(tmp_path)
    assert result["pass"] is False


def test_h2a_watchdog_uses_existing_termination_helper(monkeypatch):
    calls = []

    def fake_terminate(process, *, grace_seconds):
        calls.append((process, grace_seconds))
        return {"requested": True}

    monkeypatch.setattr(h2, "terminate_process_tree", fake_terminate)
    fake_process = object()
    assert h2._h2a_terminate_process_tree(fake_process)["requested"] is True
    assert calls == [(fake_process, 5.0)]
