from __future__ import annotations

import ast
import importlib.util
import json
import os
import shlex
import subprocess
from pathlib import Path

import numpy as np

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "docs/task40para_phi90_mesh_modes_direct/scripts/d13_cutoff_stage_accounting.py"
)
SPEC = importlib.util.spec_from_file_location("task40_d13_cutoff_stage", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
WORKER_PATH = SCRIPT.with_name("d13_saved_field_cutoff_stage_worker.py")
WORKER_SPEC = importlib.util.spec_from_file_location("task40_d13_cutoff_worker", WORKER_PATH)
assert WORKER_SPEC is not None and WORKER_SPEC.loader is not None
WORKER = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(WORKER)


def _chain():
    raw = [
        (
            np.asarray([0, 1, 3], dtype=np.int64),
            np.asarray([1.0 + 2.0j, 1.0e-14 + 1.0e-14j, 2.0 + 0.5j]),
        ),
        (
            np.asarray([0, 2, 3], dtype=np.int64),
            np.asarray([-1.0 - 2.0j + 1.0e-14, 1.0e-14j, 0.5 - 0.25j]),
        ),
    ]
    filtered = [
        MODULE.expected_component_filter(*entry)[:2]
        for entry in raw
    ]
    _rows, _values, final_rows, final_values, _facts = MODULE.expected_merged_filter(
        filtered, (1.0 + 0.0j, 1.0 + 0.0j)
    )
    storage = np.asarray([2.0 - 0.5j, -3.0 + 4.0j, 7.0 + 2.0j, 0.25 - 1.0j])
    return raw, filtered, final_rows, final_values, storage


def test_production_cutoff_accounting_closes_complex_projection_and_coupling_dots():
    raw, filtered, final_rows, final_values, storage = _chain()
    projection = MODULE.route_cutoff_accounting(
        raw,
        filtered,
        (1.0 + 0.0j, 1.0 + 0.0j),
        final_rows,
        final_values,
        storage,
        conjugate_combined_values=True,
    )
    assert projection["closure_passed"] is True
    assert projection["merged_cutoff_delta_closure"]["closed_within_roundoff_bound"]
    assert projection["after_production_merged_cutoff_dot_complex"] == np.dot(
        np.conjugate(final_values), storage[final_rows]
    )
    assert projection["raw_untruncated_dot_complex"] != np.dot(
        MODULE.merge_without_cutoff(raw, (1.0, 1.0))[1],
        storage[MODULE.merge_without_cutoff(raw, (1.0, 1.0))[0]],
    )

    coupling_coefficients = (0.4 + 0.7j, -0.2 + 0.3j)
    c_rows, c_values, c_final_rows, c_final_values, _facts = MODULE.expected_merged_filter(
        filtered, coupling_coefficients
    )
    coupling = MODULE.route_cutoff_accounting(
        raw,
        filtered,
        coupling_coefficients,
        c_final_rows,
        c_final_values,
        storage,
        conjugate_combined_values=False,
    )
    assert coupling["closure_passed"] is True
    assert "non-conjugated" in coupling["dot_convention"]
    assert "not physical power" in coupling["dot_convention"]
    assert coupling["after_production_merged_cutoff_dot_complex"] == np.dot(
        c_final_values, storage[c_final_rows]
    )
    raw_coupling_rows, raw_coupling_values = MODULE.merge_without_cutoff(raw, coupling_coefficients)
    manual_nonconjugated = np.dot(raw_coupling_values, storage[raw_coupling_rows])
    manual_wrong_conjugated = np.dot(
        np.conjugate(raw_coupling_values), storage[raw_coupling_rows]
    )
    assert coupling["raw_untruncated_dot_complex"] == manual_nonconjugated
    assert coupling["raw_untruncated_dot_complex"] != manual_wrong_conjugated
    assert c_rows.size >= c_final_rows.size
    assert c_values.size == c_rows.size


def test_cutoff_accounting_rejects_nonclosing_final_vector_as_implementation_failure():
    raw, filtered, final_rows, final_values, storage = _chain()
    damaged = final_values.copy()
    damaged[0] += 1.0e-4j
    facts = MODULE.route_cutoff_accounting(
        raw,
        filtered,
        (1.0 + 0.0j, 1.0 + 0.0j),
        final_rows,
        damaged,
        storage,
        conjugate_combined_values=True,
    )
    assert facts["closure_passed"] is False
    assert facts["merged_cutoff_delta_closure"]["classification_if_not_closed"] == (
        "DIAGNOSTIC_IMPLEMENTATION_FAILURE_NOT_CUTOFF_EVIDENCE"
    )


def test_cutoff_terms_report_floor_and_relative_dominance_separately():
    floor = MODULE.cutoff_facts(np.asarray([1.0e-40 + 0j]))
    relative = MODULE.cutoff_facts(np.asarray([1.0 + 0j]))
    assert floor["dominant_cutoff_term"] == "absolute_floor"
    assert floor["actual_cutoff"] == 1.0e-30
    assert relative["dominant_cutoff_term"] == "relative_term"
    assert relative["actual_cutoff"] == 1.0e-13


def test_worker_requires_exact_six_signed_key_order_without_list_tuple_mismatch():
    rows = [
        {"side": side, "m": m, "n": n, "polarization": pol}
        for side, m, n, pol in WORKER.TARGET_KEYS
    ]
    WORKER._require_target_mode_order(rows)
    try:
        WORKER._require_target_mode_order([rows[0], *rows[2:], rows[1]])
    except ValueError as exc:
        assert "mode order" in str(exc)
    else:
        raise AssertionError("wrong signed-key order was accepted")


def test_worker_wires_actual_production_helpers_and_mpc_expanded_same_storage():
    worker = SCRIPT.with_name("d13_saved_field_cutoff_stage_worker.py")
    tree = ast.parse(worker.read_text())
    functions = {
        item.name: item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    capture = functions["_cutoff_stage_capture"]
    capture_calls = {
        node.func.id
        for node in ast.walk(capture)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_vec_nonzero_owned_entries" in capture_calls
    assert "_combine_owned_entries" in capture_calls
    assert "build_fullspace_dtn_carrier_from_surface" not in capture_calls
    assert "build_fullspace_dtn_action" not in capture_calls
    run_one = functions["_run_one"]
    call = next(
        node
        for node in ast.walk(run_one)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_cutoff_stage_capture"
    )
    keyword_values = {keyword.arg: keyword.value for keyword in call.keywords}
    assert isinstance(keyword_values["zero_slave_storage_field_values"], ast.Name)
    assert keyword_values["zero_slave_storage_field_values"].id == "storage"
    assert isinstance(keyword_values["mpc_backsubstituted_field"], ast.Name)
    assert keyword_values["mpc_backsubstituted_field"].id == "E_mpc"


def test_v4_contract_loads_and_supervisor_accepts_the_frozen_worker_argv():
    repo = Path(__file__).resolve().parents[2]
    records = repo / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
    scripts = repo / "docs/task40para_phi90_mesh_modes_direct/scripts"
    contract_path = records / "d13_saved_field_cutoff_stage_contract_v4.json"
    sidecar_path = records / "d13_saved_field_cutoff_stage_launch_v4.json"
    contract = json.loads(contract_path.read_text())
    sidecar = json.loads(sidecar_path.read_text())

    def load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    worker = load("task40_d13_cutoff_worker_package_test", scripts / "d13_saved_field_cutoff_stage_worker.py")
    supervisor = load("task40_d13_cutoff_supervisor_package_test", scripts / "d13_saved_field_cutoff_stage_supervisor.py")
    parsed_contract = worker._load_contract(contract_path)
    source_identity = worker._verify_analysis_source(parsed_contract)
    supervisor._validate_worker_command(
        sidecar["worker_command_argv"], contract_path, Path(sidecar["report_path"]), parsed_contract
    )
    shell_lines = [
        line.strip()
        for line in sidecar["shell_command"].splitlines()
        if line.strip().startswith("exec ")
    ]
    assert len(shell_lines) == 1
    shell_exec = shlex.split(shell_lines[0])[1:]
    if ">>" in shell_exec:
        shell_exec = shell_exec[: shell_exec.index(">>")]
    assert shell_exec == sidecar["exec_argv"]
    assert sidecar["exec_argv_matches_shell"] is True
    live_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert contract["analysis_source_head"] == live_head
    assert source_identity["analysis_source_head"] == live_head
    assert Path(source_identity["src_package_path"]) == repo / "src/__init__.py"
    assert Path(sidecar["output_directory"]).exists() is False
    assert os.environ["TASK40_SHARED_VENV_ROOT"] in sidecar["worker_command_argv"][8]
