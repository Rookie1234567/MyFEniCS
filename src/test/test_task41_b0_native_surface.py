from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    _task41_compare_sparse_functional,
    _task41_native_probe_indices,
)
from src.solvers.task40_v25_selected_q0 import _q0_reference_surface_inventory


class _Connectivity:
    def __init__(self, links):
        self._links = links

    def links(self, index):
        return np.asarray(self._links[int(index)], dtype=np.int32)


class _FacetTags:
    indices = np.asarray([10, 11], dtype=np.int32)
    values = np.asarray([4, 5], dtype=np.int32)

    @staticmethod
    def find(tag):
        return _FacetTags.indices[_FacetTags.values == int(tag)].astype(np.int32)


class _Topology:
    dim = 3

    def __init__(self):
        self._f2c = _Connectivity({10: [0], 11: [1]})

    @staticmethod
    def create_entity_permutations():
        return None

    @staticmethod
    def create_connectivity(_source, _target):
        return None

    def connectivity(self, _source, _target):
        return self._f2c

    @staticmethod
    def index_map(_dimension):
        return SimpleNamespace(size_local=2)

    @staticmethod
    def get_cell_permutation_info():
        return np.asarray([3, 7], dtype=np.uint32)


def _hex_points(lower, upper):
    x0, y0, z0 = lower
    x1, y1, z1 = upper
    return np.asarray(
        [
            [x0, y0, z0], [x1, y0, z0], [x0, y1, z0], [x1, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x0, y1, z1], [x1, y1, z1],
        ],
        dtype=np.float64,
    )


def _reference_inventory_fixture():
    points = np.vstack((_hex_points((0, 0, 0), (1, 1, 1)), _hex_points((0, 0, 1), (1, 1, 2))))
    mesh = SimpleNamespace(
        comm=SimpleNamespace(size=1),
        topology=_Topology(),
        geometry=SimpleNamespace(
            x=points,
            dofmap=np.arange(16, dtype=np.int32).reshape(2, 8),
        ),
    )
    cell_dofs = [
        np.arange(882, dtype=np.int32),
        np.arange(882, dtype=np.int32) + 882,
    ]
    index_map = SimpleNamespace(local_to_global=lambda rows: np.asarray(rows, dtype=np.int64))
    space = SimpleNamespace(
        mesh=mesh,
        element=SimpleNamespace(
            basix_element=SimpleNamespace(degree=6),
            space_dimension=882,
        ),
        dofmap=SimpleNamespace(
            index_map=index_map,
            cell_dofs=lambda cell: cell_dofs[int(cell)],
        ),
    )
    mesh_data = SimpleNamespace(facet_tags=_FacetTags())
    cfg = SimpleNamespace(
        mesh_axis_cell_counts=(1, 1, 2),
        tags=SimpleNamespace(z_min=4, z_max=5),
        physical_z_min=0.0,
        physical_z_max=2.0,
    )
    return mesh_data, space, cfg


def _mode(side, m, polarization, alpha, k):
    return SimpleNamespace(
        side=side,
        m=m,
        n=0,
        polarization=polarization,
        alpha=complex(alpha),
        gamma=0.0j,
        k_vector=np.asarray([k, 0.0, 1.0], dtype=np.complex128),
    )


def test_q0_surface_inventory_preserves_actual_cell_permutations_and_both_ports():
    mesh_data, space, cfg = _reference_inventory_fixture()

    rows, support_groups, allowed_rows, permutation, facts = _q0_reference_surface_inventory(
        mesh_data, space, cfg
    )

    assert [row["side"] for row in rows] == ["bottom", "top"]
    assert [row["cell_permutation"] for row in rows] == [3, 7]
    assert permutation.tolist() == [3, 7]
    assert [len(rows) for rows in support_groups] == [1, 1]
    assert [len(rows) for rows in allowed_rows] == [882, 882]
    assert facts["facet_count_by_side"] == {"bottom": 1, "top": 1}


def test_q0_surface_inventory_rejects_noncanonical_cell_geometry():
    mesh_data, space, cfg = _reference_inventory_fixture()
    space.mesh.geometry.x[1, 0] += 0.1

    with pytest.raises(ValueError, match="canonical affine hexahedron order"):
        _q0_reference_surface_inventory(mesh_data, space, cfg)


def test_task41_native_probe_covers_both_ports_s_p_near_and_distinct_wavevectors():
    modes = []
    for side, near, far in (("bottom", 0.01, 3.0), ("top", 0.02, 4.0)):
        modes.extend(
            [
                _mode(side, 0, "s", near, near),
                _mode(side, 0, "p", near, near),
                _mode(side, 7, "s", far, far),
            ]
        )

    selected = _task41_native_probe_indices(modes)
    chosen = [modes[index] for index in selected]

    for side in ("bottom", "top"):
        on_side = [mode for mode in chosen if mode.side == side]
        assert {mode.polarization for mode in on_side} == {"s", "p"}
        assert len({tuple(mode.k_vector) for mode in on_side}) == 2
        assert min(abs(mode.alpha) for mode in on_side) < 0.1
        assert max(abs(mode.alpha) for mode in on_side) > 1.0


def test_sparse_functional_pair_requires_equal_support_and_bounds_roundoff():
    rows = np.asarray([2, 5], dtype=np.int64)
    reference = (rows, np.asarray([1.0 + 2.0j, 3.0 - 1.0j]))
    close = (rows.copy(), np.asarray([1.0 + 2.0j, 3.0 - 1.0j + 1.0e-15]))
    different_support = (np.asarray([2, 6]), close[1])

    assert _task41_compare_sparse_functional(
        reference, close, relative_tolerance=1.0e-11
    )["pass"] is True
    mismatch = _task41_compare_sparse_functional(
        reference, different_support, relative_tolerance=1.0e-11
    )
    assert mismatch["pass"] is False
    assert mismatch["support_symmetric_difference_count"] == 2


class _SerialComm:
    @staticmethod
    def allreduce(value, op=None):
        del op
        return value


class _FakeNativeRule:
    candidate_rows = np.asarray([0, 1, 2], dtype=np.int64)

    def __init__(self):
        self.assembly_stats = {
            "component_assembly_calls": 0,
            "group_integral_phase_wall_seconds_total": 0.0,
            "mpc_pullback_phase_wall_seconds_total": 0.0,
            "global_filter_phase_wall_seconds_total": 0.0,
        }

    def compact_positions(self, rows):
        rows = np.asarray(rows, dtype=np.int64)
        positions = np.searchsorted(self.candidate_rows, rows)
        if not np.array_equal(self.candidate_rows[positions], rows):
            raise ValueError("fixture row escaped candidate range")
        return positions


class _FakeAssembler:
    def __init__(self, rule, side, component, *, production):
        self.rule = rule
        self.side = side
        self.component = component
        self.boundary_reference_z = 0.0 if side == "bottom" else 1.0
        self.assembly_stats = {"calls": 0, "last_filter_audit": {"global_cutoff": 1e-13}}
        self._production = production

    def assemble_entries(self, mode, _mpc):
        del mode
        rows = (
            np.asarray([0, 1], dtype=np.int64)
            if self.component == 0
            else np.asarray([1, 2], dtype=np.int64)
        )
        values = (
            np.asarray([1.0 + 0.1j, 0.5 - 0.2j], dtype=np.complex128)
            if self.component == 0
            else np.asarray([0.2 + 0.3j, 0.8 - 0.4j], dtype=np.complex128)
        )
        if self._production:
            self.assembly_stats["calls"] += 1
        else:
            self.rule.assembly_stats["component_assembly_calls"] += 1
            self.rule.assembly_stats["last_component_filter"] = {
                "post_mpc_global_cutoff": 1e-13,
                "retained_rows": len(rows),
            }
        return rows, values


def test_pairing_runs_finite_live_mode_gate_and_persists_each_mode_callback():
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _task41_pair_native_surface_assemblers,
    )

    modes = []
    for side, near, far in (("bottom", 0.01, 3.0), ("top", 0.02, 4.0)):
        for polarization in ("s", "p"):
            modes.append(SimpleNamespace(
                side=side, m=0, n=0, polarization=polarization,
                alpha=complex(near), gamma=0.0j,
                k_vector=np.asarray([near, 0.0, 1.0], dtype=np.complex128),
                e_vector=np.asarray([1.0, 0.0, 0.0], dtype=np.complex128),
                electric_tangential_norm_sq=1.0,
            ))
        modes.append(SimpleNamespace(
            side=side, m=7, n=0, polarization="s",
            alpha=complex(far), gamma=0.0j,
            k_vector=np.asarray([far, 0.0, 1.0], dtype=np.complex128),
            e_vector=np.asarray([1.0, 0.0, 0.0], dtype=np.complex128),
            electric_tangential_norm_sq=1.0,
        ))
    rule = _FakeNativeRule()
    production = {}
    native = {}
    for side in ("bottom", "top"):
        for component in (0, 1):
            production[(side, component)] = _FakeAssembler(
                rule, side, component, production=True
            )
            native[(side, component)] = _FakeAssembler(
                rule, side, component, production=False
            )
    mpc = SimpleNamespace(
        function_space=SimpleNamespace(mesh=SimpleNamespace(comm=_SerialComm()))
    )
    cfg = SimpleNamespace(
        x_min=0.0, x_max=1.0, y_min=0.0, y_max=1.0,
        physical_z_min=0.0, physical_z_max=1.0,
    )
    callbacks = []

    result = _task41_pair_native_surface_assemblers(
        modes, production, native, mpc, cfg,
        relative_tolerance=1.0e-11,
        progress_callback=callbacks.append,
    )

    assert result["pass"] is True
    assert result["reference_norm_is_the_error_denominator"] is True
    assert result["mode_count"] == 6
    assert len(callbacks) == 6
    assert all(item["phase"] == "task41_b0_native_surface_pair_mode" for item in callbacks)
    assert all(item["status"] == "COMPLETE" for item in callbacks)
    assert all(item["mode_result"]["H_gauge_comparison"]["pass"] for item in callbacks)
    assert all(item["mode_result"]["D_raw_x_action_comparison"]["input_norm"] == pytest.approx(1.0) for item in callbacks)
    assert all(item["mode_result"]["D_raw_x_action_comparison"]["pass"] for item in callbacks)
    assert all(item["mode_result"]["reconstructed_dtn_action_comparison"]["pass"] for item in callbacks)
    assert all(item["mode_result"]["B_alpha_action_comparison"]["H_applied"] is False for item in callbacks)
    assert all(
        item["mode_result"]["component_filter_cutoffs"][0]["production"]["global_cutoff"] == 1e-13
        for item in callbacks
    )


def test_compact_task41_formula_matches_production_fullspace_dtn_action():
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.solvers.fullspace_dtn_action import (
        FullspaceDtnAction,
        FullspaceDtnCarrier,
        FullspaceDtnModeFunctional,
        _MODE_IDENTITY_FIELDS,
    )

    coupling_rows = np.asarray([0, 2], dtype=PETSc.IntType)
    coupling_values = np.asarray([1.0 + 2.0j, -0.5j], dtype=np.complex128)
    projection_rows = np.asarray([1, 2], dtype=PETSc.IntType)
    projection_values = np.asarray([0.5 + 0.1j, 2.0 - 0.5j], dtype=np.complex128)
    normalization_h = 2.5
    identity = {field: None for field in _MODE_IDENTITY_FIELDS}
    identity.update({"schema": "fixture", "mode_index": 0, "side": "top", "m": 0, "n": 0, "polarization": "s"})
    entry = FullspaceDtnModeFunctional(
        mode_key=("top", 0, 0, "s"),
        coupling_rows=coupling_rows,
        coupling_values=coupling_values,
        projection_rows=projection_rows,
        projection_values=projection_values,
        normalization_h=normalization_h,
        mode_identity=identity,
    )
    carrier = FullspaceDtnCarrier(
        (entry,), global_rows=3, ownership_range=(0, 3), comm=MPI.COMM_SELF
    )
    action = FullspaceDtnAction(carrier, comm=MPI.COMM_SELF)
    source = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
    target = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
    try:
        source_values = np.asarray([0.2 - 0.4j, 1.5 + 0.25j, -0.3 + 0.8j], dtype=np.complex128)
        source.setValues(np.arange(3, dtype=PETSc.IntType), source_values)
        source.assemble()
        action.apply(source, target)

        compact = np.zeros(3, dtype=np.complex128)
        d_raw_x = np.dot(projection_values, source_values[projection_rows])
        compact[coupling_rows] += coupling_values * (d_raw_x / normalization_h)
        np.testing.assert_allclose(
            np.asarray(target.getArray(readonly=True)), compact, rtol=0.0, atol=1.0e-14
        )

        alpha = 0.7 - 0.4j
        action.apply_modal_rhs((alpha,), target)
        b_alpha = np.zeros(3, dtype=np.complex128)
        b_alpha[coupling_rows] += alpha * coupling_values
        np.testing.assert_allclose(
            np.asarray(target.getArray(readonly=True)), b_alpha, rtol=0.0, atol=1.0e-14
        )
    finally:
        action.destroy()
        source.destroy()
        target.destroy()
