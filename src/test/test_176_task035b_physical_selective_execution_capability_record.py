from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RECORD_PATH = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "physical_selective_trace_execution_capability_v2.json"
)
EXPECTED_BINDINGS = {
    "src/constraints/selective_p6_trace_expansion.py": (
        "4fc870279e79e559044e97dc6f919c63b5ee5bafb956e378081490b3bf03dcc7"
    ),
    "src/solvers/common_3d_case_flow.py": (
        "c42959c0470ea3e5c64f20b78d201fb018d6ab23dc503ad0a160c1e77b2e3c3f"
    ),
    "src/solvers/dtn_port_3d.py": (
        "cb46c673dd8ad04f28a07a02d9d6cdc60e63a96eef6caf35fdc91130207f9db2"
    ),
    "src/solvers/solve_maxwell_3d_stage_4b_block_grating.py": (
        "a5f909f0384f33ded357859c6cecf1a52585ea174924b1a5be7d690dafc2b86b"
    ),
    "src/solvers/selective_p6_trace_matrix_free.py": (
        "586cca429068948117cfcd4139cf4669eb89510848397d35e5a7362822b89475"
    ),
    "src/adaptivity/formal_h14_live_capture_bridge.py": (
        "7a654b18872c25c19cd83ac5716747d94fb7c196a9f3dd7cd9e4cfd8eb966582"
    ),
    "src/test/test_147_task035b_actual_selective_trace_expansion.py": (
        "392c04ddf94ea352830c38a0fc17e31297590d3e320339459a6be958895aa4cb"
    ),
    "src/test/test_171_task035b_actual_selective_trace_stage4_wiring.py": (
        "3aad6a9f14353d3da15c12ef6700b0d434c16463e3fd0b8d8d40ff473c935d00"
    ),
    "src/test/test_172_task035b_selective_p6_trace_matrix_free.py": (
        "c14eba313f3bfaa8137646f8f5e0d8a109f9ab7d2ecf0d4413b2a89a7fc027f4"
    ),
    "src/test/test_174_task035b_stage4_pre_release_capture.py": (
        "0a2ecf405d96f95c2f908d31b31803b13f141508a5e6f63e2a8c8e54f2c01700"
    ),
}
MUST_REMAIN_FALSE = {
    "actual_channel_dwr_selection",
    "actual_enriched_residual_weighted_channel_dwr",
    "formal_actual_pde_ready",
    "formal_candidate_pass",
    "hybrid",
    "hybrid_eligible",
    "hybrid_launch_authorized",
    "official_physics_result",
    "production_execution_enabled",
    "production_selective_solver_qualified",
    "runner_wired",
    "twelve_of_twelve_complex_amplitude_claimed",
    "twelve_of_twelve_power_claimed",
}


def _record() -> dict[str, Any]:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping_items(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key), child
            yield from _mapping_items(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mapping_items(child)


def _keyword_default(source_path: Path, function: str, keyword: str) -> Any:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function
    )
    defaults = dict(zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True))
    default = next(
        value for argument, value in defaults.items() if argument.arg == keyword
    )
    return ast.literal_eval(default)


def test_all_bound_source_and_test_hashes_recompute() -> None:
    record = _record()
    bindings = record["file_bindings"]
    observed = {entry["path"]: entry["sha256"] for entry in bindings}

    assert len(observed) == len(bindings)
    assert observed == EXPECTED_BINDINGS
    assert record["file_hashes_are_authority"] is True
    assert record["worktree_clean_claimed"] is False
    for relative_path, expected_hash in EXPECTED_BINDINGS.items():
        assert _sha256(ROOT / relative_path) == expected_hash


def test_record_cannot_overclaim_actual_pde_dwr_or_hybrid() -> None:
    record = _record()
    assert record["capability_pass"] is True
    assert record["classification"] == (
        "positive_fixture_and_correctness_capability"
    )
    assert "does not qualify an actual selective candidate" in record[
        "pass_semantics"
    ]
    assert record["formal_pde_started"] is False
    assert record["heavy_pde_rerun"] is False
    assert record["diagnostic_physics_result"] is False
    assert record["ordinary_default_changed"] is False

    for key, value in _mapping_items(record):
        if key in MUST_REMAIN_FALSE:
            assert value is False, f"{key} must remain false"

    boundary = record["formal_accuracy_boundary"]
    assert boundary["runner_wired_scope"] == (
        "formal_h14_live_capture_and_actual_channel_dwr"
    )
    assert boundary["selective_candidate_count"] == 0
    assert boundary["selective_pde_run_count"] == 0
    assert boundary["power_gate_pass_count"] == 0
    assert boundary["complex_amplitude_gate_pass_count"] == 0
    assert boundary["hybrid_run_status"] == (
        "not_run_by_selected_candidate_gate"
    )
    assert all(
        value is None for value in record["official_physics_outputs"].values()
    )
    assert record["decision"]["authorize_actual_channel_dwr_selection"] is False
    assert record["decision"]["authorize_selective_candidate_pde"] is False
    assert record["decision"]["authorize_hybrid"] is False


def test_record_matches_default_off_source_capabilities() -> None:
    runner = (
        ROOT / "src/solvers/solve_maxwell_3d_stage_4b_block_grating.py"
    )
    for keyword in (
        "stage4_pre_release_numerical_capture",
        "actual_selective_trace_expansion_factory",
    ):
        assert (
            _keyword_default(
                runner,
                "run_stage4b_block_grating_3d_case",
                keyword,
            )
            is None
        )

    dtn_source = (ROOT / "src/solvers/dtn_port_3d.py").read_text(
        encoding="utf-8"
    )
    assert '"constraint_argument": "caller_trace_expansion"' in dtn_source
    assert '"legacy_mpc_passed_to_condensation": False' in dtn_source
    assert '"full_p6_trace_matrix_materialized": False' in dtn_source
    assert '"inactive_missing_p6_rows_allocated": 0' in dtn_source

    matrix_free_source = (
        ROOT / "src/solvers/selective_p6_trace_matrix_free.py"
    ).read_text(encoding="utf-8")
    for contract in (
        '"global_explicit_matrix_constructed": False',
        '"replicated_active_vector_allocated": False',
        '"full_vector_allreduce_used_by_action": False',
        '"full_vector_allgather_used_by_action": False',
        '"production_execution_enabled": False',
    ):
        assert contract in matrix_free_source

    bridge_source = (
        ROOT / "src/adaptivity/formal_h14_live_capture_bridge.py"
    ).read_text(encoding="utf-8")
    assert "formal_actual_pde_ready=False" in bridge_source
    assert '"formal_actual_pde_ready": False' in bridge_source
    assert '"runner_wired": False' in bridge_source


def test_pre_release_callback_precedes_release_in_source_flow() -> None:
    source = (ROOT / "src/solvers/common_3d_case_flow.py").read_text(
        encoding="utf-8"
    )
    invocation = source.rindex(
        "_invoke_stage4_pre_release_numerical_capture("
    )
    release = source.index("system_ksp.destroy()", invocation)
    postprocess = source.index("field_metrics = save_airbox_3d_fields(", invocation)

    assert invocation < release < postprocess
    assert '"solver_objects_released": False' in source
    assert '"postprocess_started": False' in source
