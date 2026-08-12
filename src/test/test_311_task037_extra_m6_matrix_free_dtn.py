from __future__ import annotations

import hashlib
import inspect
import json
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _assemble_mpc_vector,
    _assemble_mpc_form_vector,
    _dtn_surface_quadrature_degree,
    _incident_projection_onto_top_mode,
    _incident_top_traction_form,
    _mode_projection_denominator,
    _set_scalar_constant,
    _traction_vector,
)
from src.solvers.hcurl_canonical_vector import compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    iter_canonical_full_fe_owner_packets,
)
from src.solvers.hcurl_fullspace_dtn import (
    FullspaceDtnCarrier,
    FullspaceDtnModeEntries,
    build_fullspace_dtn_action,
    build_fullspace_dtn_carrier_from_surface,
)


def _synthetic_entries(comm: MPI.Intracomm):
    global_rows = 6
    mode_c = (
        (np.asarray((0, 2)), np.asarray((1.0 + 0.2j, -0.3 + 0.4j))),
        (np.asarray((1, 3)), np.asarray((0.5 - 0.1j, 0.7 + 0.2j))),
    )
    mode_d = (
        (np.asarray((1, 3)), np.asarray((0.8 + 0.1j, -0.2 + 0.5j))),
        (np.asarray((0, 2)), np.asarray((-0.4 + 0.3j, 0.6 - 0.2j))),
    )
    probe = PETSc.Vec().createMPI(
        (global_rows // comm.size + (comm.rank < global_rows % comm.size), global_rows),
        comm=comm,
    )
    start, end = map(int, probe.getOwnershipRange())
    probe.destroy()
    entries = []
    for index, ((c_rows, c_values), (d_rows, d_values)) in enumerate(
        zip(mode_c, mode_d, strict=True)
    ):
        c_mask = (c_rows >= start) & (c_rows < end)
        d_mask = (d_rows >= start) & (d_rows < end)
        entries.append(
            FullspaceDtnModeEntries(
                ("synthetic", index),
                c_rows[c_mask],
                c_values[c_mask],
                d_rows[d_mask],
                d_values[d_mask],
                _synthetic_identity(index),
            )
        )
    slaves = np.asarray((global_rows - 1,), dtype=PETSc.IntType)
    local_slaves = slaves[(slaves >= start) & (slaves < end)]
    return (
        entries,
        mode_c,
        mode_d,
        global_rows,
        (start, end),
        local_slaves,
    )


def _synthetic_identity(index: int) -> dict[str, object]:
    return {
        "schema": "m6-fullspace-dtn-mode-v1",
        "mode_index": int(index),
        "side": "synthetic",
        "m": int(index),
        "n": 0,
        "polarization": "synthetic",
        "alpha": 0.1 + 0.02j * index,
        "gamma": -0.2 + 0.03j * index,
        "beta": 0.4 + 0.01j * index,
        "k_vector": (0.1 + 0.0j, 0.2 + 0.0j, 0.4 + 0.01j * index),
        "e_vector": (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
        "power_per_unit_amplitude": 1.0 + index,
        "rayleigh_warning": False,
        "projection_denominator": 1.0 + index,
        "traction_vector": (0.0 + 0.0j, 1.0 + 0.0j, 0.0 + 0.0j),
        "refractive_index": 1.0 + 0.1 * index,
        "vertical_sign": 1,
        "h_vector": (0.0 + 0.0j, 0.0 + 1.0j, 0.0 + 0.0j),
        "electric_tangential_norm_sq": 1.5 + index,
        "propagating": True,
    }


def _new_owned_vec(global_rows: int, ownership: tuple[int, int], comm):
    start, end = ownership
    return PETSc.Vec().createMPI((end - start, global_rows), comm=comm)


def _fill_global_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    start, end = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = values[start:end]


def _relative_owned(first: np.ndarray, second: np.ndarray, comm) -> float:
    difference = np.asarray(first, dtype=np.complex128) - np.asarray(
        second, dtype=np.complex128
    )
    numerator = comm.allreduce(float(np.vdot(difference, difference).real), op=MPI.SUM)
    denominator = comm.allreduce(
        float(np.vdot(np.asarray(second, dtype=np.complex128), second).real),
        op=MPI.SUM,
    )
    return float(np.sqrt(numerator) / max(np.sqrt(denominator), 1.0e-30))


def test_m6a_identity_h_carrier_action_and_exact_layout() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("M6A carrier is executable under MPI1/MPI2 focused fixture")
    entries, mode_c, mode_d, global_rows, ownership, local_slaves = _synthetic_entries(
        comm
    )
    carrier = FullspaceDtnCarrier(
        entries,
        global_rows=global_rows,
        ownership_range=ownership,
        slave_rows=local_slaves,
        expected_mode_count=2,
        comm=comm,
    )
    audit = carrier.audit
    assert audit["fine_space"] == "uncondensed_fullspace"
    assert audit["fixed_H"] == "identity"
    assert audit["explicit_C_materialized_count"] == 0
    assert audit["explicit_D_materialized_count"] == 0
    assert audit["ordinary_default"] is False
    assert audit["retained_payload_scope"] == (
        "numpy arrays + retained canonical manifest bytes"
    )
    assert audit["python_object_overhead_included"] is False
    assert audit["petsc_object_overhead_included"] is False
    assert audit["retained_bytes"] == sum(audit["retained_components_bytes"].values())
    assert audit["bounded_work_bytes"] == 2 * 2 * np.dtype(np.complex128).itemsize
    assert audit["bounded_work_bytes_global_sum"] == comm.size * audit["bounded_work_bytes"]
    assert audit["retained_plus_work_local_bytes"] == audit["retained_plus_work_bytes"]
    assert hashlib.sha256(carrier.mode_manifest_bytes).hexdigest() == audit[
        "mode_manifest_sha256"
    ]
    assert json.loads(carrier.mode_manifest_bytes)["mode_count"] == 2
    swapped_carrier = FullspaceDtnCarrier(
        list(reversed(entries)),
        global_rows=global_rows,
        ownership_range=ownership,
        slave_rows=local_slaves,
        expected_mode_count=2,
        comm=comm,
    )
    original_modes = json.loads(carrier.mode_manifest_bytes)["modes"]
    swapped_modes = json.loads(swapped_carrier.mode_manifest_bytes)["modes"]
    assert audit["mode_manifest_sha256"] != swapped_carrier.audit["mode_manifest_sha256"]
    assert {
        json.dumps(mode, sort_keys=True) for mode in original_modes
    } == {json.dumps(mode, sort_keys=True) for mode in swapped_modes}
    missing_identity = _synthetic_identity(13)
    del missing_identity["traction_vector"]
    with pytest.raises(ValueError, match="missing fields"):
        FullspaceDtnCarrier(
            [
                FullspaceDtnModeEntries(
                    ("missing-identity",),
                    np.empty(0, dtype=PETSc.IntType),
                    np.empty(0, dtype=np.complex128),
                    np.empty(0, dtype=PETSc.IntType),
                    np.empty(0, dtype=np.complex128),
                    missing_identity,
                )
            ],
            global_rows=global_rows,
            ownership_range=ownership,
            expected_mode_count=1,
        )

    with pytest.raises(ValueError, match="locally owned"):
        FullspaceDtnCarrier(
            [
                FullspaceDtnModeEntries(
                    ("bad",),
                    np.asarray((global_rows,)),
                    np.asarray((1.0 + 0.0j,)),
                    np.empty(0),
                    np.empty(0, dtype=np.complex128),
                    _synthetic_identity(0),
                )
            ],
            global_rows=global_rows,
            ownership_range=ownership,
            expected_mode_count=1,
        )
    with pytest.raises(ValueError, match="unique"):
        FullspaceDtnCarrier(
            [
                FullspaceDtnModeEntries(
                    ("duplicate",),
                    np.asarray((ownership[0], ownership[0])),
                    np.asarray((1.0 + 0.0j, 2.0 + 0.0j)),
                    np.empty(0),
                    np.empty(0, dtype=np.complex128),
                    _synthetic_identity(0),
                )
            ],
            global_rows=global_rows,
            ownership_range=ownership,
            expected_mode_count=1,
        )
    if local_slaves.size:
        with pytest.raises(ValueError, match="slave row"):
            FullspaceDtnCarrier(
                [
                    FullspaceDtnModeEntries(
                        ("slave",),
                        local_slaves,
                            np.ones(local_slaves.size, dtype=np.complex128),
                            np.empty(0),
                            np.empty(0, dtype=np.complex128),
                            _synthetic_identity(0),
                        )
                ],
                global_rows=global_rows,
                ownership_range=ownership,
                slave_rows=local_slaves,
                expected_mode_count=1,
            )

    action = build_fullspace_dtn_action(carrier, comm=comm)
    action_source = inspect.getsource(type(action))
    assert ".assemble(" not in action_source
    assert inspect.getsource(type(action)._modal_values).count("Allreduce") == 1
    assert "Allreduce" not in inspect.getsource(type(action).apply_modal_incident_rhs)
    assert "Allreduce" not in inspect.getsource(type(action).compose_physical_rhs)
    source = _new_owned_vec(global_rows, ownership, comm)
    target = source.duplicate()
    physical_rhs = source.duplicate()
    perturbed = source.duplicate()
    perturbed_target = source.duplicate()
    try:
        x = np.asarray(
            [0.5 + 0.07 * index + 1j * (0.2 - 0.03 * index) for index in range(global_rows)],
            dtype=np.complex128,
        )
        _fill_global_values(source, x)
        source.copy(result=perturbed)
        if local_slaves.size:
            perturbed.getArray()[local_slaves - ownership[0]] += 17.0 - 9.0j

        action.apply(source, target)
        action.apply(perturbed, perturbed_target)
        action.matrix.mult(source, target)
        target_values = np.asarray(target.getArray(readonly=True), dtype=np.complex128)
        perturbed_values = np.asarray(
            perturbed_target.getArray(readonly=True), dtype=np.complex128
        )
        assert _relative_owned(target_values, perturbed_values, comm) <= 1.0e-13

        c_dense = np.zeros((2, global_rows), dtype=np.complex128)
        d_dense = np.zeros((2, global_rows), dtype=np.complex128)
        for index, ((c_rows, c_values), (d_rows, d_values)) in enumerate(
            zip(mode_c, mode_d, strict=True)
        ):
            c_dense[index, c_rows] = c_values
            d_dense[index, d_rows] = d_values
        expected_global = -(c_dense.T @ (d_dense @ x))
        start, end = ownership
        expected = expected_global[start:end].copy()
        if local_slaves.size:
            expected[local_slaves - start] = 0.0
        assert _relative_owned(target_values, expected, comm) <= 1.0e-13
        assert np.array_equal(target_values, np.asarray(target.getArray(readonly=True)))
        assert np.allclose(action.recover_auxiliary(source), -(d_dense @ x), atol=1.0e-13)
        amplitudes = np.asarray((0.3 - 0.2j, -0.1 + 0.4j), dtype=np.complex128)
        action.apply_modal_incident_rhs(amplitudes, physical_rhs)
        expected_rhs = c_dense.T @ amplitudes
        if local_slaves.size:
            expected_rhs[local_slaves] = 0.0
        assert _relative_owned(
            physical_rhs.getArray(readonly=True), expected_rhs[ownership[0] : ownership[1]], comm
        ) <= 1.0e-13
        assert action.apply_count == 3
        action.apply(source, target)
        assert action.apply_count == 4
    finally:
        action.destroy()
        source.destroy()
        target.destroy()
        physical_rhs.destroy()
        perturbed.destroy()
        perturbed_target.destroy()


def _m6a_tiny_mesh_data(comm):
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    points = (
        np.asarray((cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64),
        np.asarray((cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64),
    )
    msh = mesh.create_box(
        comm,
        points,
        (2, 2, 2),
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    fdim = msh.topology.dim - 1
    boundary_specs = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
        (cfg.tags.z_min, lambda x: np.isclose(x[2], cfg.physical_z_min)),
        (cfg.tags.z_max, lambda x: np.isclose(x[2], cfg.physical_z_max)),
    )
    facet_indices = []
    facet_values = []
    for tag, marker in boundary_specs:
        facets = mesh.locate_entities_boundary(msh, fdim, marker)
        facet_indices.append(facets)
        facet_values.append(np.full(len(facets), tag, dtype=np.int32))
    facet_index = np.concatenate(facet_indices).astype(np.int32)
    facet_value = np.concatenate(facet_values).astype(np.int32)
    order = np.argsort(facet_index)
    return cfg, SimpleNamespace(
        mesh=msh,
        facet_tags=mesh.meshtags(
            msh,
            fdim,
            facet_index[order],
            facet_value[order],
        ),
    )


def _new_mpc_vector(mpc):
    index_map = mpc.function_space.dofmap.index_map
    return create_vector([(index_map, mpc.function_space.dofmap.index_map_bs)])


def _direct_surface_action(modes, assemblers, mpc, cfg, source):
    comm = cfg.mesh.comm if hasattr(cfg, "mesh") else mpc.function_space.mesh.comm
    start, end = map(int, source.getOwnershipRange())
    source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
    local_modal = np.zeros(len(modes), dtype=np.complex128)
    local_c = np.zeros((len(modes), end - start), dtype=np.complex128)
    for index, mode in enumerate(modes):
        component_values = []
        for component in (0, 1):
            assembler = assemblers[(mode.side, component)]
            _set_scalar_constant(assembler.alpha, mode.alpha)
            _set_scalar_constant(assembler.gamma, mode.gamma)
            _set_scalar_constant(assembler.kz, mode.k_vector[2])
            vector = _assemble_mpc_form_vector(assembler.form, mpc)
            try:
                values = np.asarray(
                    vector.getArray(readonly=True), dtype=np.complex128
                ).copy()
            finally:
                vector.destroy()
            assert values.size == end - start
            component_values.append(values)
        ell = mode.e_vector[0] * component_values[0] + mode.e_vector[1] * component_values[1]
        traction = _traction_vector(mode, cfg)
        c_values = -(
            traction[0] * component_values[0]
            + traction[1] * component_values[1]
        )
        denominator = _mode_projection_denominator(mode, cfg)
        local_modal[index] = np.dot(
            -np.conjugate(ell) / denominator,
            source_values,
        )
        local_c[index, :] = c_values
    global_modal = np.empty_like(local_modal)
    comm.Allreduce(local_modal, global_modal, op=MPI.SUM)
    expected = np.zeros(end - start, dtype=np.complex128)
    for index in range(len(modes)):
        expected += -global_modal[index] * local_c[index]
    return expected


def _direct_surface_modal_rhs(modes, assemblers, mpc, cfg, source, amplitudes):
    """Freshly assemble the actual ``C b`` modal incident correction for the test."""

    start, end = map(int, source.getOwnershipRange())
    amplitudes = np.asarray(amplitudes, dtype=np.complex128)
    expected = np.zeros(end - start, dtype=np.complex128)
    for amplitude, mode in zip(amplitudes, modes, strict=True):
        component_values = []
        for component in (0, 1):
            assembler = assemblers[(mode.side, component)]
            _set_scalar_constant(assembler.alpha, mode.alpha)
            _set_scalar_constant(assembler.gamma, mode.gamma)
            _set_scalar_constant(assembler.kz, mode.k_vector[2])
            vector = _assemble_mpc_form_vector(assembler.form, mpc)
            try:
                values = np.asarray(
                    vector.getArray(readonly=True), dtype=np.complex128
                ).copy()
            finally:
                vector.destroy()
            assert values.size == end - start
            component_values.append(values)
        traction = _traction_vector(mode, cfg)
        c_values = -(
            traction[0] * component_values[0]
            + traction[1] * component_values[1]
        )
        expected += complex(amplitude) * c_values
    return expected


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="M6A tiny full-space fixture is executable under MPI1/MPI2 focused fixture",
)
def test_m6a_tiny_floquet_surface_action_and_mpi2_repeat_feasibility() -> None:
    comm = MPI.COMM_WORLD
    cfg, mesh_data = _m6a_tiny_mesh_data(comm)
    modes = outgoing_port_modes_3d(cfg)
    assert len(modes) == 80
    assert abs(complex(cfg.floquet_phase_x) - 1.0) > 1.0e-6
    p6_space = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    floquet = build_double_floquet_mpc(p6_space, mesh_data, cfg)
    assert floquet.num_edge_constraints > 0
    assert floquet.num_face_constraints > 0
    assert complex(floquet.phase_x) == complex(cfg.floquet_phase_x)
    assert complex(floquet.phase_corner) == complex(
        cfg.floquet_phase_x * cfg.floquet_phase_y
    )
    qdegree = _dtn_surface_quadrature_degree(cfg, modes)
    surface_tags = {"top": cfg.tags.z_max, "bottom": cfg.tags.z_min}
    assemblers = {
        (side, component): _ReusableSurfaceComponentAssembler(
            p6_space,
            mesh_data,
            surface_tags[side],
            component,
            quadrature_degree=qdegree,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes,
        assemblers,
        floquet.mpc,
        cfg,
    )
    action = build_fullspace_dtn_action(carrier, comm=comm)
    source = _new_mpc_vector(floquet.mpc)
    target = _new_mpc_vector(floquet.mpc)
    repeat = _new_mpc_vector(floquet.mpc)
    base_traction = _assemble_mpc_vector(
        _incident_top_traction_form(p6_space, mesh_data, cfg),
        floquet.mpc,
    )
    modal_rhs = _new_mpc_vector(floquet.mpc)
    physical_rhs = _new_mpc_vector(floquet.mpc)
    slave_source = _new_mpc_vector(floquet.mpc)
    slave_target = _new_mpc_vector(floquet.mpc)
    try:
        start, end = map(int, source.getOwnershipRange())
        with source.localForm() as local:
            local.set(0.0)
            global_ids = np.arange(start, end, dtype=np.float64)
            local.array_w[: end - start] = np.sin(0.017 * global_ids) + 1j * np.cos(
                0.023 * global_ids
            )
        source.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        projections = tuple(
            _incident_projection_onto_top_mode(mode, cfg) for mode in modes
        )
        assert max(abs(value) for value in projections) > 0.0
        base_values = np.asarray(
            base_traction.getArray(readonly=True), dtype=np.complex128
        )
        assert np.linalg.norm(base_values) > 0.0
        action.apply_modal_incident_rhs(projections, modal_rhs)
        direct_modal_rhs = _direct_surface_modal_rhs(
            modes, assemblers, floquet.mpc, cfg, source, projections
        )
        modal_values = np.asarray(modal_rhs.getArray(readonly=True), dtype=np.complex128)
        assert np.linalg.norm(direct_modal_rhs) > 0.0
        assert _relative_owned(modal_values, direct_modal_rhs, comm) <= 1.0e-11
        action.compose_physical_rhs(base_traction, projections, physical_rhs)
        composed_values = np.asarray(
            physical_rhs.getArray(readonly=True), dtype=np.complex128
        )
        assert _relative_owned(
            composed_values,
            base_values + direct_modal_rhs,
            comm,
        ) <= 1.0e-13
        action.apply(source, target)
        action.apply(source, repeat)
        source.copy(result=slave_source)
        local_slaves = np.asarray(floquet.mpc.slaves, dtype=np.int32)
        local_slaves = local_slaves[
            local_slaves < int(p6_space.dofmap.index_map.size_local)
        ]
        if local_slaves.size:
            slave_source.getArray()[local_slaves] += 11.0 - 7.0j
        action.apply(slave_source, slave_target)
        expected = _direct_surface_action(modes, assemblers, floquet.mpc, cfg, source)
        observed = np.asarray(target.getArray(readonly=True), dtype=np.complex128)
        assert _relative_owned(observed, expected, comm) <= 1.0e-11
        assert np.array_equal(observed, np.asarray(repeat.getArray(readonly=True)))
        assert _relative_owned(
            observed,
            np.asarray(slave_target.getArray(readonly=True), dtype=np.complex128),
            comm,
        ) <= 1.0e-11
        if local_slaves.size:
            assert np.array_equal(observed[local_slaves], np.zeros(local_slaves.size))
        audit = action.audit
        assert audit["mode_count"] == 80
        assert audit["explicit_C_materialized_count"] == 0
        assert audit["explicit_D_materialized_count"] == 0
        assert audit["fixed_H"] == "identity"
        assert audit["fine_space"] == "uncondensed_fullspace"
        assert audit["condensation"] is False
        assert audit["ordinary_default"] is False
        assert len(audit["mode_manifest_sha256"]) == 64
        assert audit["retained_plus_work_gate"] is True
        assert audit["retained_plus_work_global_sum_bytes"] <= 150_000_000
        assert audit["retained_bytes"] == audit["retained_numeric_bytes"] + audit[
            "retained_identity_bytes"
        ]
        assert audit["retained_plus_work_global_sum_bytes"] == (
            audit["retained_bytes_global_sum"]
            + audit["bounded_work_bytes_global_sum"]
        )
        manifest = json.loads(carrier.mode_manifest_bytes)
        required_mode_fields = {
            "schema",
            "mode_index",
            "side",
            "m",
            "n",
            "polarization",
            "alpha",
            "gamma",
            "beta",
            "k_vector",
            "e_vector",
            "power_per_unit_amplitude",
            "rayleigh_warning",
            "projection_denominator",
            "traction_vector",
            "refractive_index",
            "vertical_sign",
            "h_vector",
            "electric_tangential_norm_sq",
            "propagating",
        }
        assert manifest["mode_count"] == 80
        assert all(required_mode_fields <= set(mode) for mode in manifest["modes"])
        packets = tuple(
            iter_canonical_full_fe_owner_packets(
                p6_space,
                floquet.mpc,
                target,
                floquet,
            )
        )
        repeat_packets = tuple(
            iter_canonical_full_fe_owner_packets(
                p6_space,
                floquet.mpc,
                repeat,
                floquet,
            )
        )
        comparison = compare_canonical_packets(
            packets,
            repeat_packets,
            relative_tolerance=1.0e-12,
        )
        assert comparison["pass"]
        # Same-run repeat only; independent MPI1-vs-MPI2 identity is deferred_to_formal_runner.
        # This test-only tiny oracle gather never enters the candidate action.
        gathered = comm.allgather(packets)
        repeat_gathered = comm.allgather(repeat_packets)
        merged = tuple(packet for rank_packets in gathered for packet in rank_packets)
        repeat_merged = tuple(
            packet for rank_packets in repeat_gathered for packet in rank_packets
        )
        global_comparison = compare_canonical_packets(
            merged,
            repeat_merged,
            relative_tolerance=1.0e-12,
        )
        assert global_comparison["pass"]
        assert global_comparison["duplicate_left_count"] == 0
        assert global_comparison["duplicate_right_count"] == 0
    finally:
        action.destroy()
        source.destroy()
        target.destroy()
        repeat.destroy()
        base_traction.destroy()
        modal_rhs.destroy()
        physical_rhs.destroy()
        slave_source.destroy()
        slave_target.destroy()


def test_m6a_core_does_not_use_mat_getinfo() -> None:
    from src.solvers import hcurl_fullspace_dtn

    source = inspect.getsource(hcurl_fullspace_dtn)
    assert "getInfo" not in source
    assert "createAIJ" not in source
    assert "createSubMatrix" not in source
