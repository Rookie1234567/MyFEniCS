"""Raw failure-evidence inventory contracts; no physical experiment."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.check_y_orbit_sparse_probe import _raw_factor_inventory, _complete_interior_rhs, _bind_worker_dependencies


def _fixture(tmp_path):
    inventory = {}
    for q in range(2):
        for name in ("rhs_a", "rhs_b", "solution_a", "solution_b", "solution_a_repeat", "solution_sum"):
            key = f"q_{q}_{name}"
            p = tmp_path / (key + ".npy")
            np.save(p, np.ones(4, dtype=np.complex128), allow_pickle=False)
            inventory[key] = {"path": p.name, "file_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                              "finite_entries": 4, "nonfinite_entries": 0}
    return {"factor_raw_diagnostics": inventory,
            "reference_factor": {"input_blocks": [{"q": q, "shape": [4, 4]} for q in range(2)]}}


def test_all_expected_vectors_required_even_if_empty_dict_is_locally_finite(tmp_path):
    report = _fixture(tmp_path)
    report["factor_raw_diagnostics"] = {}
    with pytest.raises(ValueError, match="complete expected"):
        _raw_factor_inventory(report, tmp_path, 2)


def test_one_missing_raw_solution_vector_is_rejected(tmp_path):
    report = _fixture(tmp_path)
    del report["factor_raw_diagnostics"]["q_1_solution_sum"]
    with pytest.raises(ValueError, match="complete expected"):
        _raw_factor_inventory(report, tmp_path, 2)


def test_raw_nonfinite_entries_are_honest_failure_evidence_not_success(tmp_path):
    report = _fixture(tmp_path)
    assert _raw_factor_inventory(report, tmp_path, 2) is True
    key = "q_0_solution_a"
    descriptor = report["factor_raw_diagnostics"][key]
    p = tmp_path / descriptor["path"]
    np.save(p, np.asarray([1, np.nan, np.inf, 4], dtype=np.complex128), allow_pickle=False)
    descriptor.update(file_sha256=hashlib.sha256(p.read_bytes()).hexdigest(), finite_entries=2, nonfinite_entries=2)
    assert _raw_factor_inventory(report, tmp_path, 2) is False


def test_interior_RHS_flag_is_Python_bool_and_serializes_without_default_coercion():
    flag = _complete_interior_rhs(np.ones(4, dtype=complex), np.asarray([1, 3]), 2)
    assert type(flag) is bool
    assert json.loads(json.dumps({"complete_interiors": flag}, allow_nan=False))["complete_interiors"] is True


def test_checker_edit_exception_never_waives_numerical_config_input_hashes():
    common = {"branch": "task40extra_dot_parallel_cloud", "dirty": ""}
    old = {**common, "head": "a"*40, "files_sha256": {"src/solvers/y_orbit_sparse_probe.py": "same",
            "input/frozen.dat": "input_same", "benchmarks/check_y_orbit_sparse_probe.py": "old_checker"}}
    new = {**common, "head": "b"*40, "files_sha256": {**old["files_sha256"],
            "benchmarks/check_y_orbit_sparse_probe.py": "reviewed_checker"}}
    binding = _bind_worker_dependencies(old, new)
    assert binding["worker_head"] != binding["checker_head"]
    for path in ("src/solvers/y_orbit_sparse_probe.py", "input/frozen.dat"):
        changed = {**new, "files_sha256": {**new["files_sha256"], path: "changed"}}
        with pytest.raises(RuntimeError, match="byte-identical numerical"):
            _bind_worker_dependencies(old, changed)
