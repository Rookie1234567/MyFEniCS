"""Metadata and call-contract checks; no mesh, factor or PDE execution."""

import ast
import hashlib
import json
from pathlib import Path

import pytest

from src.runners.physical_retained_condensed_v20 import _persist_n0_inventory
from src.solvers.fullspace_dtn_action import (
    FULLSPACE_DTN_MANIFEST_SCHEMA,
    FULLSPACE_DTN_PROFILE,
    _canonical_json_bytes,
)


def inventory(rows):
    payload = {"schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
               "profile": FULLSPACE_DTN_PROFILE, "mode_count": len(rows), "modes": rows}
    return ((), rows, hashlib.sha256(_canonical_json_bytes(payload)).hexdigest())


def test_inventory_files_preserve_parent_and_remap_without_zero_fill(tmp_path):
    rows = [{"side": "top", "m": -1, "n": n, "polarization": "s"}
            for n in (-1, 0, 1)]
    parent, active = inventory(rows), inventory([rows[1]])
    artifacts = _persist_n0_inventory(tmp_path, parent, active, {"policy": "n0"}, (1,))
    for label, packet in artifacts.items():
        data = (tmp_path / packet["filename"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == packet["sha256"]
        assert len(data) == packet["bytes"]
        if label == "parent":
            assert packet["sha256"] == parent[2]
    mapping = json.loads((tmp_path / artifacts["index_map"]["filename"]).read_text())
    assert mapping["old_to_new"] == [-1, 0, -1]
    assert mapping["retained_keys"] == [["top", -1, 0, "s"]]
    assert mapping["omitted_keys"] == [["top", -1, -1, "s"], ["top", -1, 1, "s"]]
    assert "never filled with zero" in mapping["omitted_values_policy"]
    with pytest.raises(FileExistsError):
        _persist_n0_inventory(tmp_path, parent, active, {}, (1,))


def test_inventory_rejects_manifest_hash_mismatch(tmp_path):
    with pytest.raises(ValueError, match="live manifest"):
        _persist_n0_inventory(tmp_path, ((), [], "bad"), inventory([]), {}, ())
    assert not list(tmp_path.iterdir())


def test_runtime_wires_selection_to_both_spaces_and_scoped_residual_to_ksp():
    path = Path(__file__).parents[1] / "runners/physical_retained_condensed_v20.py"
    tree = ast.parse(path.read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)]
    builders = [call for call in calls if call.func.id == "build_same_mesh_physical_action"]
    assert len(builders) == 2
    for call in builders:
        keys = [key.arg for key in call.keywords]
        assert len(keys) == len(set(keys))
        for key in ("operator_selection", "selected_parent_indices", "quadrature_mode_inventory"):
            assert key in keys
    solve = [call for call in calls if call.func.id == "run_retained_fgmres"]
    assert len(solve) == 1
    assert ast.unparse(next(key.value for key in solve[0].keywords
                            if key.arg == "physical_residual_key")) == "physical_residual_key"
    endpoint = [call for call in calls if call.func.id == "observe_full_dtn_endpoint"]
    assert len(endpoint) == 1
    assert {key.arg for key in endpoint[0].keywords} >= {
        "storage_solution", "n0_residual", "selected_parent_indices",
        "active_entries", "omitted_incident_rhs_zero",
    }
