"""C2.1b real p6/h50 custom-nested owner/topology smoke.

This is a small structural smoke, not a p6/h10 formal run.  The only
numeric collection below is test-side canonical-packet capture for the
MPI1/MPI2 identity comparison; production routing remains owner-local.
"""

from __future__ import annotations

import os
import pytest


if os.environ.get("TASK038_RUN_C2_1B_REAL") != "1":
    pytest.skip(
        "C2.1b real MPI smoke is explicit research/archive opt-in",
        allow_module_level=True,
    )


import json
import resource
from types import SimpleNamespace
from pathlib import Path

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import (
    _mark_boundary_facets,
    _mark_cells,
    _stage4_axis_plan,
    _structured_hexa_mesh,
)
from src.solvers.fullspace_lor_memory_first_foundation import _canonical_raw_map
from src.solvers.fullspace_lor_native_hx_fixture import (
    _P1IdentityTransfer,
    _assemble_sparse,
    _edge_records,
    _p1_transfer_local_indices,
    _piecewise_positive_coefficients,
    _refined_axis,
    _l2_analytic_values,
    build_frozen_fullspace_primal_source,
)
from src.solvers.fullspace_lor_nested_hmg import build_nested_lor_edge_hmg
from src.solvers import fullspace_lor_nested_hmg_runtime as nested_runtime
from src.solvers.fullspace_lor_topology import build_canonical_lor_subedge_topology
from src.solvers.fullspace_lor_transfer import build_local_lor_transfer
from src.solvers.hcurl_canonical_vector import compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_full_fe_dual_packets,
    extract_canonical_full_fe_packets,
)

def _positive_matrix(space, floquet, mesh_object, cell_tags, cfg):
    import ufl

    mu, mass, _ = _piecewise_positive_coefficients(mesh_object, cell_tags, cfg)
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    matrix = _assemble_sparse(
        (mu * ufl.inner(ufl.curl(trial), ufl.curl(test))
         + mass * ufl.inner(trial, test)) * ufl.dx,
        mpc=floquet.mpc,
    )
    del mu, mass, trial, test
    return matrix


def _build_small_foundation(comm):
    """Build only the p6 parent and p6-refined p1 raw data needed by C2."""

    cfg = target_stage4_config(degree=6, h_nm=50.0)
    plan = _stage4_axis_plan(cfg, comm.size)
    parent_axes = tuple(
        np.asarray(axis, dtype=np.float64)
        for axis in (plan.x_values, plan.y_values, plan.z_values)
    )
    high_mesh = _structured_hexa_mesh(
        comm,
        *parent_axes,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    high_facets, _ = _mark_boundary_facets(high_mesh, cfg)
    high_cells = _mark_cells(high_mesh, cfg)
    high_data = SimpleNamespace(
        mesh=high_mesh, cell_tags=high_cells, facet_tags=high_facets
    )
    high_space = fem.functionspace(
        high_mesh,
        element("N1curl", high_mesh.basix_cell(), 6, dtype=default_real_type),
    )
    high_floquet = build_double_floquet_mpc(high_space, high_data, cfg)
    high_topology = build_canonical_lor_subedge_topology(
        high_space,
        high_floquet,
        build_local_lor_transfer(6),
    )

    refined_axes = tuple(_refined_axis(axis, 6) for axis in parent_axes)
    low_mesh = _structured_hexa_mesh(
        comm,
        *refined_axes,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    low_facets, _ = _mark_boundary_facets(low_mesh, cfg)
    low_cells = _mark_cells(low_mesh, cfg)
    low_data = SimpleNamespace(
        mesh=low_mesh, cell_tags=low_cells, facet_tags=low_facets
    )
    low_cfg = target_stage4_config(degree=1, h_nm=50.0)
    low_space = fem.functionspace(
        low_mesh,
        element("N1curl", low_mesh.basix_cell(), 1, dtype=default_real_type),
    )
    low_floquet = build_double_floquet_mpc(low_space, low_data, low_cfg)
    low_permutations = np.asarray(
        [
            _p1_transfer_local_indices(low_space, cell)
            for cell in range(int(low_mesh.topology.index_map(3).size_local))
        ],
        dtype=np.int32,
    )
    low_matrix = _positive_matrix(low_space, low_floquet, low_mesh, low_cells, low_cfg)
    low_topology = build_canonical_lor_subedge_topology(
        low_space, low_floquet, _P1IdentityTransfer()
    )
    low_node_space = fem.functionspace(
        low_mesh,
        element("Lagrange", low_mesh.basix_cell(), 1, dtype=default_real_type),
    )
    low_records, _ = _edge_records(low_space, low_node_space)
    low_raw_map = _canonical_raw_map(
        low_space,
        low_node_space,
        low_records,
        refined_axes,
        owner_ids=low_topology.owned_edge_ids,
        local_permutations=low_permutations,
        validate_local_owner_layout=False,
    )
    del low_node_space, low_records
    foundation = SimpleNamespace(
        cfg=cfg,
        high_mesh=high_mesh,
        high_data=high_data,
        high_space=high_space,
        high_floquet=high_floquet,
        high_topology=high_topology,
        low_matrix=low_matrix,
        low_edge_space=low_space,
        low_floquet=low_floquet,
        low_topology=low_topology,
        low_raw_map=low_raw_map,
        low_p1_transfer_local_indices=low_permutations,
    )
    return foundation, parent_axes


def _build_small_extension(comm):
    foundation, parent_axes = _build_small_foundation(comm)
    level6 = nested_runtime._build_level6_for_nested(foundation)
    h3star = h1star = None
    try:
        h3star = nested_runtime._build_nested_level(
            foundation, "h3star", parent_axes
        )
        h1star = nested_runtime._build_nested_level(
            foundation, "h1star", parent_axes
        )
        local = build_nested_lor_edge_hmg()
        transfer_63 = nested_runtime._OwnerPacketTransfer(
            level6,
            h3star,
            local.h6_to_h3star,
            allowed_pairs=nested_runtime.NESTED_HMG_PAIRS,
            route_schema=nested_runtime.NESTED_HMG_RUNTIME_SCHEMA,
            pair_key=nested_runtime.NESTED_HMG_PAIRS[0],
        )
        transfer_31 = nested_runtime._OwnerPacketTransfer(
            h3star,
            h1star,
            local.h3star_to_h1star,
            allowed_pairs=nested_runtime.NESTED_HMG_PAIRS,
            route_schema=nested_runtime.NESTED_HMG_RUNTIME_SCHEMA,
            pair_key=nested_runtime.NESTED_HMG_PAIRS[1],
        )
        extension = nested_runtime.NestedHmgHierarchyExtension(
            foundation, level6, h3star, h1star, transfer_63, transfer_31
        )
    except Exception:
        if h1star is not None:
            h1star.destroy()
        if h3star is not None:
            h3star.destroy()
        level6.destroy()
        _destroy_foundation(foundation)
        raise
    return extension


def _destroy_foundation(foundation):
    for value in (foundation.low_matrix, foundation.low_floquet, foundation.high_floquet):
        if value is not None and hasattr(value, "destroy"):
            value.destroy()
        elif value is not None and hasattr(value, "mpc") and hasattr(value.mpc, "destroy"):
            value.mpc.destroy()


def _finite_global(values, comm):
    local = int(np.all(np.isfinite(np.asarray(values))))
    return bool(comm.allreduce(local, op=MPI.MIN))


def _analytic_primal_source(space, floquet, cfg):
    field = fem.Function(floquet.mpc.function_space)
    field.interpolate(lambda coordinates: _l2_analytic_values("gradient", coordinates, cfg))
    field.x.scatter_forward()
    floquet.mpc.homogenize(field)
    field.x.scatter_forward()
    floquet.mpc.backsubstitution(field)
    field.x.scatter_forward()
    result = field.x.petsc_vec.copy()
    del field
    return result


def _relative(left, right):
    difference = left.copy()
    difference.axpy(-1.0, right)
    value = float(difference.norm() / max(right.norm(), np.finfo(float).tiny))
    difference.destroy()
    return value


def _scalar_relative(left, right):
    return float(abs(left - right) / max(abs(left), abs(right), np.finfo(float).tiny))


def _canonical_key_encode(value):
    if value is None:
        return ["none"]
    if isinstance(value, tuple):
        return ["tuple", [_canonical_key_encode(item) for item in value]]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, float):
        return ["float", value.hex()]
    raise TypeError(f"unsupported canonical key component: {type(value)!r}")


def _canonical_key_decode(value):
    tag = value[0]
    if tag == "none":
        return None
    if tag == "tuple":
        return tuple(_canonical_key_decode(item) for item in value[1])
    if tag == "str":
        return str(value[1])
    if tag == "bool":
        return bool(value[1])
    if tag == "int":
        return int(value[1])
    if tag == "float":
        return float.fromhex(value[1])
    raise ValueError(f"unsupported encoded canonical key tag: {tag!r}")


def _owned_packet_work(comm, left, right):
    left_ids, left_values = left
    right_ids, right_values = right
    if not np.array_equal(left_ids, right_ids):
        raise AssertionError("owner packet ids do not align for work identity")
    local = np.vdot(
        np.asarray(left_values, dtype=np.complex128),
        np.asarray(right_values, dtype=np.complex128),
    )
    return comm.allreduce(local, op=MPI.SUM)


def _packet_relative(left, right):
    left_ids, left_values = left
    right_ids, right_values = right
    if not np.array_equal(left_ids, right_ids):
        raise AssertionError("owner packet ids do not align")
    left_values = np.asarray(left_values, dtype=np.complex128)
    right_values = np.asarray(right_values, dtype=np.complex128)
    return float(
        np.linalg.norm(left_values - right_values)
        / max(np.linalg.norm(right_values), np.finfo(float).tiny)
    )


def _inventory(level):
    parent = level.parent_topology
    raw = level.raw_topology
    if not np.array_equal(parent.owned_edge_ids, raw.owned_edge_ids):
        raise AssertionError(f"{level.level_key} parent/raw owned IDs differ")
    facts = {}
    for name, topology in (("parent", parent), ("raw", raw)):
        owned = np.asarray(topology.owned_edge_ids)
        unique = np.asarray(topology.unique_edge_ids)
        assert owned.dtype == np.dtype(np.uint32)
        assert unique.dtype == np.dtype(np.uint32)
        assert np.array_equal(owned, np.sort(owned))
        assert np.array_equal(unique, np.sort(unique))
        assert int(topology.audit["global_unique_edge_count"]) > 0
        assert topology.audit["phase_application"] == "once_in_canonical_owner_route"
        facts[name] = {
            "local_owned": int(owned.size),
            "local_unique": int(unique.size),
            "global_unique": int(topology.audit["global_unique_edge_count"]),
        }
    assert facts["parent"]["global_unique"] == facts["raw"]["global_unique"]
    return facts


def _capture_or_compare(comm, name, packets):
    gathered = comm.gather(tuple(packets), root=0)
    capture_dir = os.environ.get("C2_CAPTURE_DIR")
    if not capture_dir:
        raise AssertionError("C2_CAPTURE_DIR is required for the cross-MPI smoke")
    path = Path(capture_dir) / f"{name}_mpi{comm.size}.json"
    other = Path(capture_dir) / f"{name}_mpi{3 - comm.size}.json"
    result = None
    if comm.rank == 0:
        flat = tuple(packet for block in gathered for packet in block)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(
                [
                    {
                        "key": _canonical_key_encode(key),
                        "real": float(value.real),
                        "imag": float(value.imag),
                    }
                    for key, value in flat
                ],
                handle,
                sort_keys=True,
                separators=(",", ":"),
            )
        local_keys = [key for key, _value in flat]
        duplicate_count = len(local_keys) - len(set(local_keys))
        if duplicate_count:
            raise AssertionError(f"{name} canonical packets duplicate within run")
        if other.is_file():
            with other.open(encoding="utf-8") as handle:
                reference = tuple(
                    (
                        _canonical_key_decode(row["key"]),
                        complex(row["real"], row["imag"]),
                    )
                    for row in json.load(handle)
                )
            result = compare_canonical_packets(
                flat, reference, relative_tolerance=1.0e-11
            )
            assert result["duplicate_left_count"] == 0
            assert result["duplicate_right_count"] == 0
            assert result["missing_key_count"] == 0
            assert result["extra_key_count"] == 0
            assert result["relative_coefficient_l2"] <= 1.0e-11
        print(json.dumps({"canonical": name, "count": len(flat), "comparison": result}, sort_keys=True))
    comm.barrier()
    return result


def _resource_facts(comm):
    usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    swap = 0
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmSwap:"):
                swap = int(line.split()[1]) * 1024
                break
    except OSError:
        swap = -1
    peak = int(comm.allreduce(usage, op=MPI.MAX))
    max_swap = int(comm.allreduce(swap, op=MPI.MAX))
    return {"rank_max_rss_bytes": peak, "rank_max_swap_bytes": max_swap}


def test_real_nested_hmg_owner_topology_smoke():
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("C2.1b smoke is qualified only for MPI1 and MPI2")
    extension = _build_small_extension(comm)
    vectors = []
    try:
        assert extension.audit["levels"] == ("h6", "h3star", "h1star")
        assert extension.audit["pairs"] == (
            ("h6", "h3star"),
            ("h3star", "h1star"),
        )
        assert extension.audit["h3star_standard_polynomial_space"] is False
        assert extension.audit["global_transfer_matrix"] is False
        assert extension.audit["numeric_allgather"] is False
        assert extension.audit["smoother_built"] is False
        assert extension.audit["ksp_created"] is False
        levels = extension.levels
        inventories = {key: _inventory(level) for key, level in levels.items()}
        assert inventories["h6"]["parent"]["global_unique"] == inventories["h6"]["raw"]["global_unique"]
        local = build_nested_lor_edge_hmg()
        assert local.audit["h3star_is_standard_polynomial_level"] is False
        assert local.audit["composition_direct_edge_relative"] <= 1.0e-11

        level_sources = {}
        level_bridge_facts = {}
        violations = []
        for level_key, level in levels.items():
            primal_source = _analytic_primal_source(
                level.raw_space, level.raw_floquet, extension.foundation.cfg
            )
            dual_source, _ = build_frozen_fullspace_primal_source(
                level.raw_space,
                level.raw_floquet,
                extension.foundation.cfg,
                "gradient",
            )
            vectors.extend((primal_source, dual_source))
            assert primal_source.norm() > 0.0
            assert dual_source.norm() > 0.0
            assert _finite_global(primal_source.getArray(readonly=True), comm)
            assert _finite_global(dual_source.getArray(readonly=True), comm)
            primal_before = primal_source.getArray(readonly=True).copy()
            dual_before = dual_source.getArray(readonly=True).copy()
            primal_packet = level.primal_to_owner(primal_source)
            dual_packet = level.dual_to_owner(dual_source)
            primal_roundtrip = level.owner_to_primal(primal_packet)
            dual_roundtrip = level.owner_to_dual(dual_packet)
            vectors.extend((primal_roundtrip, dual_roundtrip))
            assert _finite_global(primal_roundtrip.getArray(readonly=True), comm)
            assert _finite_global(dual_roundtrip.getArray(readonly=True), comm)
            primal_roundtrip_packet = level.primal_to_owner(primal_roundtrip)
            primal_owner_roundtrip = _packet_relative(
                primal_packet, primal_roundtrip_packet
            )
            dual_roundtrip_relative = _relative(dual_source, dual_roundtrip)
            if primal_owner_roundtrip > 1.0e-11:
                violations.append(f"{level_key} primal owner roundtrip")
            if dual_roundtrip_relative > 1.0e-11:
                violations.append(f"{level_key} dual roundtrip")
            assert np.array_equal(
                primal_source.getArray(readonly=True), primal_before
            )
            assert np.array_equal(dual_source.getArray(readonly=True), dual_before)
            owner_work = _owned_packet_work(comm, primal_packet, dual_packet)
            raw_work = primal_source.dot(dual_source)
            bridge_relative = _scalar_relative(raw_work, owner_work)
            if bridge_relative > 1.0e-11:
                violations.append(f"{level_key} raw/owner bridge work")
            level_sources[level_key] = {
                "primal": primal_source,
                "dual": dual_source,
            }
            level_bridge_facts[level_key] = {
                "primal_roundtrip_relative": _relative(
                    primal_source, primal_roundtrip
                ),
                "primal_owner_roundtrip_relative": primal_owner_roundtrip,
                "dual_roundtrip_relative": dual_roundtrip_relative,
                "raw_work": [float(raw_work.real), float(raw_work.imag)],
                "owner_work": [float(owner_work.real), float(owner_work.imag)],
                "work_relative": bridge_relative,
                "owned_count": int(primal_packet[0].size),
            }

        pair_facts = {}
        for pair in nested_runtime.NESTED_HMG_PAIRS:
            transfer = extension.transfers[pair]
            fine = levels[pair[0]]
            coarse = levels[pair[1]]
            _inventory(fine)
            _inventory(coarse)
            assert transfer.audit["global_transfer_matrix"] is False
            assert transfer.audit["numeric_allgather"] is False
            assert transfer.audit["orientation_phase_scope"] == "owned by parent topology routes"
            coarse_source = level_sources[pair[1]]["primal"]
            fine_dual = level_sources[pair[0]]["dual"]
            assert coarse_source.norm() > 0.0
            assert fine_dual.norm() > 0.0
            assert _finite_global(coarse_source.getArray(readonly=True), comm)
            assert _finite_global(fine_dual.getArray(readonly=True), comm)
            coarse_before = coarse_source.getArray(readonly=True).copy()
            fine_before = fine_dual.getArray(readonly=True).copy()
            primal = fine.matrix.createVecRight()
            adjoint = coarse.matrix.createVecRight()
            primal_repeat = fine.matrix.createVecRight()
            adjoint_repeat = coarse.matrix.createVecRight()
            vectors.extend((primal, adjoint, primal_repeat, adjoint_repeat))
            extension.apply_primal_into(pair, coarse_source, primal)
            extension.apply_adjoint_into(pair, fine_dual, adjoint)
            extension.apply_primal_into(pair, coarse_source, primal_repeat)
            extension.apply_adjoint_into(pair, fine_dual, adjoint_repeat)
            assert _finite_global(primal.getArray(readonly=True), comm)
            assert _finite_global(adjoint.getArray(readonly=True), comm)
            assert _relative(primal, primal_repeat) == 0.0
            assert _relative(adjoint, adjoint_repeat) == 0.0
            assert np.array_equal(coarse_source.getArray(readonly=True), coarse_before)
            assert np.array_equal(fine_dual.getArray(readonly=True), fine_before)
            fine_primal_packet = fine.primal_to_owner(primal)
            fine_dual_packet = fine.dual_to_owner(fine_dual)
            coarse_primal_packet = coarse.primal_to_owner(coarse_source)
            coarse_adjoint_packet = coarse.dual_to_owner(adjoint)
            lhs = _owned_packet_work(comm, fine_primal_packet, fine_dual_packet)
            rhs = _owned_packet_work(comm, coarse_primal_packet, coarse_adjoint_packet)
            work_relative = _scalar_relative(lhs, rhs)
            if work_relative > 1.0e-11:
                violations.append(f"{pair[0]}->{pair[1]} transfer work")
            pair_facts[f"{pair[0]}->{pair[1]}"] = {
                "shape": transfer.audit["local_map"],
                "work_relative": work_relative,
                "raw_petsc_work_relative": _scalar_relative(
                    primal.dot(fine_dual), coarse_source.dot(adjoint)
                ),
                "fine_inventory": _inventory(fine),
                "coarse_inventory": _inventory(coarse),
                "phase_application": fine.parent_topology.audit["phase_application"],
            }
            if pair == ("h6", "h3star"):
                primal_packets, primal_audit = extract_canonical_full_fe_packets(
                    fine.raw_space, primal, fine.raw_floquet
                )
                dual_packets, dual_audit = extract_canonical_full_fe_dual_packets(
                    coarse.raw_space, coarse.raw_floquet.mpc, adjoint
                )
                _capture_or_compare(comm, "primal", primal_packets)
                _capture_or_compare(comm, "dual", dual_packets)
                assert primal_audit["summed_local_duplicate_count"] == 0
                assert dual_audit["summed_local_duplicate_count"] == 0
        if comm.rank == 0:
            print(
                json.dumps(
                    {"levels": level_bridge_facts, "pairs": pair_facts},
                    sort_keys=True,
                )
            )
        resource_facts = _resource_facts(comm)
        if resource_facts["rank_max_rss_bytes"] >= 500_000_000:
            violations.append("rank RSS resource")
        if resource_facts["rank_max_swap_bytes"] != 0:
            violations.append("rank swap resource")
        if comm.rank == 0:
            print(
                json.dumps(
                    {
                        "inventories": inventories,
                        "levels": level_bridge_facts,
                        "pairs": pair_facts,
                        "resource": resource_facts,
                        "violations": violations,
                    },
                    sort_keys=True,
                )
            )
        assert not violations, "; ".join(violations)
    finally:
        for vector in vectors:
            vector.destroy()
        foundation = extension.foundation
        extension.destroy()
        _destroy_foundation(foundation)
