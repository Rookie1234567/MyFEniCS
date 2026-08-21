"""Focused R3 primal canonical roundtrip and checker contracts."""

from __future__ import annotations

import inspect
import json

import numpy as np
import pytest
from dolfinx import fem
from mpi4py import MPI

from benchmarks import run_task038_full3d_r3 as runner
from benchmarks import task038_full3d_r3_checker as checker
from src.common.analytic_fields_3d import electric_field_code_values
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_canonical_vector import compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_full_fe_packets,
    reconstruct_canonical_full_fe_function,
)
from src.test.test_46_task033_high_order_floquet_topology import _fixed_target_fixture


def test_r3_path_boundary_and_old_dual_hard_stop_contract() -> None:
    assert runner.R3_SOURCE_NAME == "CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE"
    assert checker.R3_SOURCE_NAME == runner.R3_SOURCE_NAME
    source = inspect.getsource(runner._run_case)
    assert "reconstruct_canonical_full_fe_function" in source
    assert "empirical_scaling" in source
    assert runner.R3_SOURCE_NAME in runner.__dict__.values()
    assert "run_task038_full3d_t3" not in source
    assert "del historical_field" not in source
    assert "roundtrip_field is not historical_field" not in source
    assert "_ReusableSurfaceComponentAssembler" in inspect.getsource(
        runner._make_surface_assemblers
    )
    assert "m6b_iter200_residual.npy" in inspect.getsource(
        runner._old_residual_diagnostic
    )


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial primal roundtrip")
def test_r3_primal_roundtrip_uses_existing_physical_map() -> None:
    cfg, mesh_data, raw_space = _fixed_target_fixture(2, h_nm=50.0)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    field = fem.Function(space)
    field.interpolate(lambda x: electric_field_code_values(cfg, x.T).T)
    field.x.scatter_forward()
    packets, audit = extract_canonical_full_fe_packets(
        space, field.x.petsc_vec, floquet_data
    )
    restored = reconstruct_canonical_full_fe_function(space, packets, floquet_data)
    restored_packets, restored_audit = extract_canonical_full_fe_packets(
        space, restored.x.petsc_vec, floquet_data
    )
    comparison = compare_canonical_packets(
        packets, restored_packets, relative_tolerance=1.0e-12
    )
    assert comparison["pass"], comparison
    assert audit["local_duplicate_count"] == 0
    assert restored_audit["local_duplicate_count"] == 0
    assert audit.get("numeric_allgather", False) is False
    assert np.all(np.isfinite(restored.x.array))


def test_r3_checker_recomputes_residual_and_rejects_path_a_default(tmp_path) -> None:
    key = (
        "full_fe_dual",
        1,
        ((0, 0, 0), (1, 0, 0)),
        0,
        ("canonical_edge", "contract"),
        None,
        (1.0, 0.0),
    )
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )

    def manifest(label, value):
        directory = tmp_path / label
        directory.mkdir()
        shard = directory / "rank0000.jsonl"
        metadata = write_canonical_packet_shard(shard, ((key, value),), audit_packets=True)
        path = directory / "manifest.json"
        write_canonical_manifest(
            path,
            canonical_shard_manifest(
                role="full_fe_dual",
                mpi_size=1,
                shard_metadata=[metadata],
                extractor_audit={"role": "full_fe_dual"},
            ),
        )
        return {
            "kind": "canonical_packet_manifest",
            "role": "full_fe_dual",
            "manifest_relative_path": str(path.relative_to(tmp_path)),
            "manifest_sha256": checker._sha256_path(path),
            "packet_count": 1,
            "duplicate_count": 0,
            "finite": True,
        }

    artifacts = {
        "primal_source": None,
        "primal_roundtrip": None,
        "current_rhs": manifest("rhs", 2.0 + 0.0j),
        "action": manifest("action", 1.0 + 0.0j),
        "action_repeat": manifest("repeat", 1.0 + 0.0j),
        "residual": manifest("residual", 1.0 + 0.0j),
    }
    record = {
        "schema": checker.R3_SCHEMA,
        "profile": checker.R3_PROFILE,
        "source_name": checker.R3_SOURCE_NAME,
        "path_a": {
            "status": "NOT_QUALIFIED",
            "fit_or_scaling": "forbidden_and_not_attempted",
        },
        "path_b": {
            "source_name": checker.R3_SOURCE_NAME,
            "empirical_scaling": False,
        },
        "source": {
            "expected_sha": "a" * 40,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "tracked_status_start": "",
            "tracked_status_end": "",
        },
        "input": {
            "template_bytes": checker.EXPECTED_INPUT_BYTES,
            "template_sha256": checker.EXPECTED_INPUT_SHA256,
            "resolved_config_bytes": checker.EXPECTED_RESOLVED_BYTES,
            "resolved_config_sha256": checker.EXPECTED_RESOLVED_SHA256,
            "physical_model_sha256": checker.EXPECTED_PHYSICAL_MODEL_SHA256,
        },
        "model": {
            "mode_count": checker.EXPECTED_MODE_COUNT,
            "mode_manifest_sha256": checker.EXPECTED_MODE_MANIFEST_SHA256,
        },
        "raw_dir": str(tmp_path),
        "mpi": {"size": 2},
        "artifacts": artifacts,
        "observations": {
            "apply_count": 2,
            "apply_telemetry": [
                {"rank_max_current_swap_bytes": 0},
                {"rank_max_current_swap_bytes": 0},
            ],
        },
        "operator": {
            "audit": {
                "operator": "A_volume_plus_dynamic_DtN",
                "t4_transmission_included": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "ksp_created": False,
                "numeric_allgather": False,
            },
            "audit_artifact": {"relative_path": "missing"},
            "audit_sha256": "",
        },
        "pde_solved": False,
        "ksp_created": False,
    }
    result = checker.check_record(record)
    assert result["derived"]["residual_recompute"]["pass"] is True
    assert result["gates"]["path_a_not_qualified"] is True
    assert result["status"] == "fail"
