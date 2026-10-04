"""Small literal counterexamples; never clones old factors or JIT directories."""

import json

import numpy as np
import pytest

from src.solvers.native_entity_dependencies import digest, validate_envelope
from src.solvers.native_entity_protocol import (
    entity_keys,
    periodic_master,
    structured_counts,
)


@pytest.mark.parametrize(
    "key",
    [
        "physical",
        "material",
        "phase",
        "basis",
        "owner_protocol",
        "index_dtype",
        "scalar_dtype",
        "axes",
        "modes",
        "slave_semantics",
        "stage_dependencies",
    ],
)
def test_same_shape_wrong_identity_rejected(key):
    keys = [
        "physical",
        "material",
        "phase",
        "basis",
        "owner_protocol",
        "index_dtype",
        "scalar_dtype",
        "axes",
        "modes",
        "slave_semantics",
        "stage_dependencies",
    ]
    expected = {k: "correct" for k in keys}
    row = dict(
        expected,
        schema="native-entity-consumption.v1",
        commit=True,
        identity_sha256=digest(expected),
        parents=[],
        class_bindings=[],
    )
    validate_envelope(row, expected)
    row[key] = "wrong"
    with pytest.raises(ValueError, match="consumption identity"):
        validate_envelope(row, expected)


def test_system_rejects_another_self_consistent_class(tmp_path):
    expected = {
        k: "correct"
        for k in [
            "physical",
            "material",
            "phase",
            "basis",
            "owner_protocol",
            "index_dtype",
            "scalar_dtype",
            "axes",
            "modes",
            "slave_semantics",
            "stage_dependencies",
        ]
    }
    path = tmp_path / "system.json"
    path.write_text(
        json.dumps({"metadata": {"classes": [{"name": "wrong", "sha256": "other"}]}})
    )
    row = dict(
        expected,
        schema="native-entity-consumption.v1",
        commit=True,
        identity_sha256=digest(expected),
        parents=[],
        class_bindings=[
            {
                "system_path": str(path),
                "classes": [{"name": "correct", "sha256": "hash"}],
            }
        ],
    )
    with pytest.raises(ValueError, match="system class inventory"):
        validate_envelope(row, expected)


def test_periodic_corner_is_once_and_dual_conjugated():
    keys = np.array([[1, 2, 4, 4, 1], [2, 0, 4, 3, 1], [1, 0, 3, 4, 0]], np.int64)
    p = np.exp(0.7j), np.exp(-0.4j)
    master, phase = periodic_master(keys, (4, 4, 4), p)
    assert np.array_equal(master[0], [1, 2, 0, 0, 1])
    assert abs(phase[0] - p[0] * p[1]) < 1e-15
    x, dual = 0.7 - 0.2j, -0.3 + 1.1j
    assert (
        abs(np.vdot(dual, phase[0] * x) - np.vdot(phase[0].conjugate() * dual, x))
        < 1e-14
    )
    assert abs(np.vdot(dual, phase[0] * x) - np.vdot(phase[0] * dual, x)) > 0.1


def test_exact_geometry_keys_and_no_approximate_merging():
    axes = [np.array([0.0, 1.0, 2.0])] * 3
    coords = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    assert np.array_equal(entity_keys(coords, [[0, 1]], axes, 1), [[1, 0, 0, 0, 0]])
    coords[1, 0] = np.nextafter(1.0, 0.0)
    with pytest.raises(ValueError, match="exact axes"):
        entity_keys(coords, [[0, 1]], axes, 1)
    assert structured_counts((4, 4, 4)) == {
        "cells": 64,
        "vertices": 125,
        "edges": 300,
        "faces": 240,
        "boundary_faces": 96,
    }


def test_all_new_dat_dispatch_and_frozen_parent_identity():
    from src.io.port_preparation import load_preparation
    from src.solvers.native_entity_scope import ROOT, STAGES

    for name in STAGES:
        r = load_preparation(
            ROOT / ("input/task042_neural_coarse_inverse/v41_" + name.lower() + ".dat")
        )
        assert r.derived["stage"] == name and r.derived["preparation_scope"] == "v41"
        assert not r.derived["target_solve"]
        assert r.execution["mpi_size"] == {
            "BRIDGE2": 2,
            "BRIDGE4": 4,
            "TOPOLOGY": 2,
            "ROUTING": 2,
            "DEPLOY": 2,
        }.get(name, 1)


def test_rank_coverage_requires_actual_unique_ranks():
    from benchmarks.check_native_entities import ranks

    valid = [{"rank": i, "MPI_size": 2, "commit": True} for i in range(2)]
    ranks(valid, 2)
    with pytest.raises(ValueError, match="MPI rank inventory"):
        ranks(valid[:1], 2)
    with pytest.raises(ValueError, match="MPI rank inventory"):
        ranks([valid[0], valid[0]], 2)


def test_actual_complete_entity_workflow_nonzero_complex_and_failure():
    from mpi4py import MPI

    from src.solvers.native_entity_adapter import CompleteEntityAdapter

    for dimension, moments, permutations in (
        (1, 6, [[0, 1], [1, 0]]),
        (2, 60, [[0, 1, 2, 3], [1, 3, 0, 2]]),
    ):
        a = CompleteEntityAdapter(
            MPI.COMM_SELF,
            [7],
            [7, 7],
            [0, 0],
            np.array([1.0, np.exp(0.9j)]),
            permutations,
            dimension,
        )
        rng = np.random.default_rng(424101)
        x = (rng.normal(size=(1, moments)) + 1j * rng.normal(size=(1, moments))).astype(
            np.complex128
        )
        dual = (
            rng.normal(size=(2, moments)) + 1j * rng.normal(size=(2, moments))
        ).astype(np.complex128)
        out = a.extract(x)
        pull = np.zeros_like(x)
        a.scatter_into(dual, pull)
        assert (
            abs(np.vdot(dual, out) - np.vdot(pull, x)) / abs(np.vdot(pull, x)) < 1e-12
        )
        assert (
            np.linalg.norm(a.canonical_from_physical(out) - np.repeat(x, 2, axis=0))
            < 1e-11
        )
        assert np.array_equal(a.extract(np.zeros_like(x)), np.zeros_like(out))
        with pytest.raises(ValueError, match="wrong native owner"):
            CompleteEntityAdapter(
                MPI.COMM_SELF, [7], [8], [0], [1], [permutations[0]], dimension
            )


def test_short_deadline_clears_only_own_descendant_tree(tmp_path):
    import subprocess
    import sys

    # MPI leaves a daemon in pytest: use a dedicated supervision parent.
    code = (
        "import sys,json; from pathlib import Path; from benchmarks.subreaper_watchdog import supervise; "
        "r=supervise([sys.executable,'-c',\"import subprocess,time,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)\"],"
        "Path(sys.argv[1]),wall_seconds=1.5,interval=.25,rss_hard_limit_bytes=512*2**20,hard_stop_immediate=True); "
        "print(json.dumps(r))"
    )
    run = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "timeout")],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(run.stdout)
    assert result["classification"] != "COMPLETED"
    assert result["descendants_cleared"]
    assert result["elapsed_seconds"] < 10
