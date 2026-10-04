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


def test_ordered_mode_receipt_reads_literal_list_and_rejects_hash(tmp_path):
    from src.solvers.native_entity_study import ordered_modes_from_receipt
    from src.solvers.native_recovery_packets import sha

    p = tmp_path / "modes.json"
    modes = [{"side": "top", "mode_index": 0}, {"side": "bottom", "mode_index": 1}]
    p.write_text(json.dumps(modes))
    receipt = {"path": str(p), "sha256": sha(p)}
    assert ordered_modes_from_receipt(receipt, expected_count=2) == modes
    with pytest.raises(ValueError, match="complete frozen"):
        ordered_modes_from_receipt(receipt)
    p.write_text("[]")
    with pytest.raises(ValueError, match="bytes hash"):
        ordered_modes_from_receipt(receipt, expected_count=2)


def test_complete_boundary_adjoint_uses_saved_independent_dual():
    from src.solvers.native_entity_study import apply_frozen_boundary_adjoint

    class Action:
        def apply(self, value, *, adjoint=False):
            assert adjoint
            return value * (2 - 3j)

    inputs = {"x": np.array([1 + 2j]), "y": np.array([-4 + 7j])}
    assert np.array_equal(apply_frozen_boundary_adjoint(Action(), inputs), inputs["y"] * (2 - 3j))
    assert not np.array_equal(apply_frozen_boundary_adjoint(Action(), inputs), inputs["x"] * (2 - 3j))


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


def test_native_p6_actual_T_apply_requires_flat_contiguous_channels():
    import basix.ufl
    from dolfinx.fem.element import finiteelement
    from dolfinx.mesh import CellType

    element = finiteelement(
        CellType.hexahedron, basix.ufl.element("N1curl", "hexahedron", 6), np.float64
    )
    value = np.arange(882 * 2, dtype=np.float64).reshape(882, 2)
    with pytest.raises(TypeError, match="incompatible function arguments"):
        element.T_apply(value, np.array([0], np.uint32), 2)
    original = value.copy()
    element.T_apply(value.ravel(), np.array([0], np.uint32), 2)
    assert np.array_equal(value, original)


@pytest.mark.parametrize(
    "fault", ["none", "phase", "owner", "missing_face", "missing_rank"]
)
def test_literal_owner_checker_end_to_end_inventory_faults(tmp_path, fault):
    from benchmarks.check_native_entities import check_packets
    from src.solvers.port_component_study import array_file

    arrays = {}
    sizes = {}
    for dimension in (1, 2):
        keys = []
        for axis in range(3):
            for i in range(2):
                for j in range(2):
                    for k in range(2):
                        low = [i, j, k]
                        if (dimension == 1 and low[axis] != 0) or (
                            dimension == 2
                            and any(low[a] != 0 for a in range(3) if a != axis)
                        ):
                            continue
                        keys.append([dimension, axis, *low])
        keys = np.array(keys, np.int64)
        master, phase = periodic_master(keys, (1, 1, 1), (np.exp(0.3j), np.exp(-0.2j)))
        lookup = {tuple(key): i for i, key in enumerate(keys)}
        gid = np.arange(len(keys), dtype=np.int64)
        ids = np.array([lookup[tuple(key)] for key in master], np.int64)
        sizes[str(dimension)] = {"owned": len(keys), "ghost": 0, "global": len(keys)}
        for name, value in (
            ("keys", keys),
            ("native_ids", gid),
            ("owners", np.zeros(len(keys), np.int32)),
            ("master_keys", master),
            ("master_ids", ids),
            ("master_owners", np.zeros(len(keys), np.int32)),
            ("phase", phase),
        ):
            arrays[f"entity{dimension}_" + name] = value
    if fault == "phase":
        arrays["entity1_phase"][1] *= np.exp(0.1j)
    if fault == "owner":
        arrays["entity2_master_owners"][0] = 1
    if fault == "missing_face":
        arrays["entity2_keys"] = arrays["entity2_keys"][:-1]
    arrays.update(
        cell_native_ids=np.array([0], np.int64),
        cell_tags=np.array([1], np.int32),
        cell_raw_class_local=np.array([0], np.int32),
        coordinates=np.array(
            [[i, j, k] for k in (0.0, 1.0) for j in (0.0, 1.0) for i in (0.0, 1.0)],
            np.float64,
        ),
        cell_vertices=np.array([list(range(8))], np.int32),
        boundary_facets=np.arange(6, dtype=np.int32),
    )
    sizes["3"] = {"owned": 1, "ghost": 0, "global": 1}
    receipt = array_file(tmp_path / "literal.npz", **arrays)
    record = {
        "rank": 0,
        "MPI_size": 1,
        "commit": True,
        "numeric": receipt,
        "metadata": {
            "entity_sizes": sizes,
            "raw_classes": [
                {"tag": 1, "width_hex": [float(1).hex()] * 3, "count": 1, "index": 0}
            ],
            "axis_cells": [1, 1, 1],
            "phases": [[np.cos(0.3), np.sin(0.3)], [np.cos(-0.2), np.sin(-0.2)]],
        },
    }
    if fault in ("owner", "missing_face", "missing_rank"):
        with pytest.raises(ValueError):
            check_packets([] if fault == "missing_rank" else [record])
    else:
        assert check_packets([record])["passed"] == (fault == "none")


@pytest.mark.parametrize("fault", ["none", "phase", "owner", "missing_face", "missing_rank", "permutation", "dual"])
def test_full_saved_boundary_routing_checker_from_actual_adapter(tmp_path, fault):
    import basix.ufl
    from mpi4py import MPI

    from benchmarks.check_native_entities import check_routing
    from src.solvers.native_entity_adapter import CompleteEntityAdapter, boundary_rows
    from src.solvers.port_component_study import array_file

    x = np.arange(144, dtype=float) * (0.1 + 0.2j) + 1 - 0.7j
    phases = (np.exp(0.3j), np.exp(-0.2j))
    arrays, top_arrays, sizes = {}, {}, {}
    left = right = 0j
    for d, moments in ((1, 6), (2, 60)):
        keys = []
        for side in (0, 1):
            if d == 2:
                keys.append([2, 2, 0, 0, side])
            else:
                for axis in (0, 1):
                    for endpoint in (0, 1):
                        low = [0, 0, side]
                        low[1 - axis] = endpoint
                        keys.append([1, axis, *low])
        keys = np.array(keys, np.int64)
        masters, phase = periodic_master(keys, (1, 1, 1), phases)
        gid = np.arange(len(keys), dtype=np.int64)
        lookup = {tuple(k): i for i, k in enumerate(keys)}
        requested = np.array([lookup[tuple(k)] for k in masters], np.int64)
        canonical = np.flatnonzero(np.all(keys == masters, axis=1))
        rows = boundary_rows(keys[canonical], (1, 1, 1), d)
        perm = np.tile([1, 0] if d == 1 else [0, 2, 1, 3], (len(keys), 1)).astype(np.int8)
        owner = np.zeros(len(keys), np.int32)
        adapter = CompleteEntityAdapter(MPI.COMM_SELF, gid[canonical], requested, owner, phase, perm, d)
        values = np.ascontiguousarray(x[rows])
        extracted = adapter.extract(values)
        dual = np.arange(len(keys) * moments).reshape(len(keys), moments) * (0.01 - 0.02j) + 0.5j
        scatter = np.zeros_like(values)
        adapter.scatter_into(dual, scatter)
        left += np.vdot(dual, extracted)
        right += np.vdot(scatter, values)
        for name, value in (("canonical_rows", rows), ("owned_native_ids", gid[canonical]),
                            ("physical_native_ids", gid), ("physical_keys", keys),
                            ("requested_master_ids", requested), ("requested_master_owners", owner),
                            ("permutation", perm), ("phase", phase), ("owned_values", values),
                            ("extracted", extracted), ("physical_dual", dual), ("scattered_dual", scatter)):
            arrays[f"boundary{d}_" + name] = value
        for name, value in (("native_ids", gid), ("keys", keys), ("master_ids", requested),
                            ("master_owners", owner), ("vertex_permutations", perm)):
            top_arrays[f"entity{d}_" + name] = value
        sizes[str(d)] = {"owned": len(keys), "ghost": 0, "global": len(keys)}
    arrays.update(global_duality_left=np.array([left]), global_duality_right=np.array([right]))
    if fault == "phase":
        arrays["boundary1_phase"][1] *= np.exp(0.1j)
    if fault == "owner":
        arrays["boundary1_requested_master_owners"] = np.ones(8, np.int32)
    if fault == "missing_face":
        arrays["boundary2_physical_native_ids"] = arrays["boundary2_physical_native_ids"][:-1]
    if fault == "permutation":
        arrays["boundary2_permutation"] = np.tile([0, 1, 2, 3], (2, 1)).astype(np.int8)
    if fault == "dual":
        arrays["boundary1_scattered_dual"][0, 0] += 1
    packet = {"rank": 0, "MPI_size": 1, "commit": True,
              "numeric": array_file(tmp_path / "routing.npz", **arrays)}
    topology = {"rank": 0, "MPI_size": 1, "commit": True,
                "numeric": array_file(tmp_path / "topology.npz", **top_arrays),
                "metadata": {"axis_cells": [1, 1, 1], "phases": [[p.real, p.imag] for p in phases], "entity_sizes": sizes}}
    generators = basix.ufl.element("N1curl", "hexahedron", 6).basix_element.entity_transformations()
    direction = array_file(tmp_path / "directions.npz", interval_transform=generators["interval"],
                           quadrilateral_transform=generators["quadrilateral"])
    action = array_file(tmp_path / "actions.npz", frozen_input=x)
    def call():
        return check_routing([] if fault == "missing_rank" else [packet], 144,
                             topology=[topology], actions=action, directions=direction, expected_ranks=1)
    if fault in ("owner", "missing_face", "missing_rank", "permutation"):
        with pytest.raises(ValueError):
            call()
    else:
        assert call()["passed"] == (fault == "none")


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
