from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from src.solvers.task40_v22_operator_probe import (
    _RollingDigest,
    _V22NativeFacetRule,
    _accumulate_cell_mode_support,
    _cell_support_row_counts,
    _compact_reference_mode_indices,
    _load_v23_action_checkpoint,
    _mapped_port_face_global_rows,
    _same_v23_mpc_function_space_layout,
    _summarize_cell_mode_support,
    _v23_actual_axis_values,
    _v23_checkpoint_directory,
    _write_v22_action_checkpoint,
)
from src.runners.task40_v10_campaign import TASK40_V23_CAMPAIGN_SHA256


def test_v23_axis_values_use_resolved_coordinate_vectors_not_cell_counts():
    axes = {"x": [0.0, 1.0, 2.0], "y": [0.0, 0.5], "z": [0.0, 3.0]}
    resolved = {
        "discretization": {
            f"mesh_axis_{axis}_values": values for axis, values in axes.items()
        },
        "geometry_facts": {"actual_axes": [2, 1, 1]},
    }

    assert _v23_actual_axis_values(resolved) == axes


class _FakeDofMap:
    @staticmethod
    def cell_dofs(_cell_id):
        return np.arange(882, dtype=np.int32)


class _FakeIndexMap:
    size_global = 900

    @staticmethod
    def local_to_global(local_rows):
        return (881 - np.asarray(local_rows, dtype=np.int64)).astype(np.int32)


class _FakePolynomial:
    @staticmethod
    def integral_native(*_args):
        values = np.zeros((882, 2), dtype=np.complex128)
        values[0, 0] = 1.0 + 0.0j
        values[1, 0] = 0.25 + 0.5j
        values[2, 0] = 1e-13 + 0.0j
        values[3, 0] = np.nextafter(1e-13, np.inf) + 0.0j
        values[4, 1] = 2.0 - 1.0j
        return values


class _FakeIndex:
    size_global = 900

    @staticmethod
    def local_to_global(local_rows):
        return _FakeIndexMap.local_to_global(local_rows)


class _FakeElement:
    needs_dof_transformations = False
    space_dimension = 882


def _rule():
    lower = np.array([0.0, 0.0, 0.0])
    upper = np.array([1.0, 1.0, 1.0])
    ordered = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [1, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [0, 1, 1],
            [1, 1, 1],
        ],
        dtype=np.float64,
    )
    row = {
        "side": "bottom",
        "class_id": "fixture",
        "cell_id": 0,
        "cell_permutation": 0,
        "facet_id": 0,
        "cell_bounds_nm": np.column_stack((lower, upper)),
        "ordered_cell_coordinates_nm": ordered,
    }
    space = SimpleNamespace(
        mesh=SimpleNamespace(comm=SimpleNamespace(size=1)),
        dofmap=SimpleNamespace(cell_dofs=_FakeDofMap.cell_dofs),
        element=_FakeElement(),
    )
    return _V22NativeFacetRule(
        space=space,
        dof_index_map=_FakeIndex(),
        mapping_rows=[row, {**row, "side": "top", "cell_id": 1, "facet_id": 1}],
        permutation_info=np.array([0, 0], dtype=np.uint32),
        polynomial=_FakePolynomial(),
        quadrature_degree=4,
        cfg=SimpleNamespace(),
        mpc_expansions={
            880: (np.array([899], dtype=np.int64), np.array([0.5 + 0.25j]))
        },
    )


def _mode(side="bottom", m=1, n=0, polarization="s", k=0.25):
    return SimpleNamespace(
        side=side,
        m=m,
        n=n,
        polarization=polarization,
        alpha=0.0 + 0.0j,
        gamma=0.0 + 0.0j,
        k_vector=np.array([k, 0.0, 0.0]),
    )


def test_compact_component_matches_full_vector_bitwise_with_mpc_and_cutoff_rows():
    rule = _rule()
    result = rule.compare_full_domain_reference(_mode(), 0)

    assert result["status"] == "PASS_EXACT"
    assert result["retained_values_bitwise_equal"] is True
    assert result["raw_mpc_slave_rows_nonzero_before_pullback"] == 1
    assert result["compact_row_count"] < rule.native_size
    rows, values = rule.assemble_component(_mode(), 0)
    assert rows.tolist() == sorted(rows.tolist())
    assert 880 not in rows
    assert 899 in rows
    master_value = values[np.searchsorted(rows, 899)]
    assert master_value == np.conjugate(0.5 + 0.25j) * (0.25 + 0.5j)
    # The equality-at-cutoff entry is dropped; the next representable value is retained.
    assert 879 not in rows
    assert 878 in rows


class _FakeCellToFacet:
    @staticmethod
    def links(_cell_id):
        return np.array([31, 32, 33, 34, 35, 36], dtype=np.int32)


def test_port_face_inventory_uses_real_p6_entity_closure_and_cached_dofmap_rows():
    from basix.ufl import element

    p6 = element("N1curl", "hexahedron", 6).basix_element
    face_dofs = np.asarray(p6.entity_dofs[2][0], dtype=np.int32)
    closure_dofs = np.asarray(p6.entity_closure_dofs[2][0], dtype=np.int32)
    assert p6.dim == 882
    assert len(closure_dofs) > len(face_dofs)
    cell_rows = np.arange(p6.dim, dtype=np.int64) + 20_000
    cached_rows = {0: cell_rows}

    actual = _mapped_port_face_global_rows(
        [{"cell_id": 0, "facet_id": 31}],
        _FakeCellToFacet(),
        cached_rows,
        p6.entity_closure_dofs[2],
    )

    assert actual == set(map(int, cell_rows[closure_dofs]))
    assert set(map(int, cell_rows[face_dofs])) < actual


def test_compact_reference_mode_selection_includes_first_middle_last_and_s_p_pairs():
    modes = [
        _mode("bottom", 1, 0, "s", 0.1),
        _mode("bottom", 1, 0, "p", 0.1),
        _mode("bottom", 2, 0, "s", 0.2),
        _mode("bottom", 3, 0, "s", 0.3),
        _mode("bottom", 3, 0, "p", 0.3),
        _mode("top", 1, 0, "s", 0.4),
        _mode("top", 2, 0, "s", 0.5),
        _mode("top", 3, 0, "s", 0.6),
    ]

    selected = _compact_reference_mode_indices(modes)

    assert 0 in selected["bottom"] and 1 in selected["bottom"]
    assert 2 in selected["bottom"]
    assert 3 in selected["bottom"] and 4 in selected["bottom"]
    assert set(selected["top"]) == {5, 6, 7}


def test_cell_multiplicity_counts_modes_once_and_deduplicates_B_D_union():
    cell_ids = np.array([7, 9], dtype=np.int64)
    interior_rows = np.array([100, 101, 200], dtype=np.int64)
    interior_cells = np.array([7, 7, 9], dtype=np.int64)
    mode_counts = {
        metric: np.zeros(2, dtype=np.int64) for metric in ("B", "D", "union")
    }
    row_memberships = {
        metric: np.zeros(2, dtype=np.int64) for metric in ("B", "D", "union")
    }

    def add_mode(metric, rows):
        counts = _cell_support_row_counts(
            rows,
            interior_rows_sorted=interior_rows,
            interior_cell_ids_sorted=interior_cells,
            cell_ids_sorted=cell_ids,
        )
        _accumulate_cell_mode_support(mode_counts[metric], row_memberships[metric], counts)

    # Two B rows in one cell are still one m_c hit. D overlaps that cell and
    # also hits the second; the per-mode union counts each cell only once.
    b_rows = np.array([100, 101], dtype=np.int64)
    d_rows = np.array([101, 200], dtype=np.int64)
    add_mode("B", b_rows)
    add_mode("D", d_rows)
    add_mode("union", np.union1d(b_rows, d_rows))
    add_mode("B", np.array([100], dtype=np.int64))
    add_mode("D", np.array([], dtype=np.int64))
    add_mode("union", np.array([100], dtype=np.int64))

    assert mode_counts["B"].tolist() == [2, 0]
    assert mode_counts["D"].tolist() == [1, 1]
    assert mode_counts["union"].tolist() == [2, 1]
    assert row_memberships["B"].tolist() == [3, 0]
    assert row_memberships["D"].tolist() == [1, 1]
    assert row_memberships["union"].tolist() == [3, 1]
    summary = _summarize_cell_mode_support(mode_counts["union"], expected_mode_count=2)
    assert summary["histogram_by_modes_0_to_expected"] == [0, 1, 1]
    assert summary["sum"] == 3
    assert summary["sum_squares"] == 5


def test_v23_mpc_space_layout_compares_owned_cells_and_global_dof_identity():
    from basix.ufl import element

    basix_element = element("N1curl", "hexahedron", 6).basix_element
    topology = SimpleNamespace(
        dim=3,
        index_map=lambda _dim: SimpleNamespace(size_local=2),
    )
    mesh = SimpleNamespace(comm=SimpleNamespace(size=2), topology=topology)
    cells = [
        np.arange(882, dtype=np.int32),
        np.arange(100, 982, dtype=np.int32),
    ]

    def make_index_map():
        return SimpleNamespace(
            size_global=20_181_348,
            size_local=1_000,
            local_range=(0, 1_000),
            num_ghosts=1,
            ghosts=np.asarray([20_000_000], dtype=np.int64),
            owners=np.asarray([1], dtype=np.int32),
        )

    def make_space_dofmap():
        return SimpleNamespace(
            index_map=make_index_map(),
            index_map_bs=1,
            cell_dofs=lambda cell: cells[int(cell)],
        )

    expected = SimpleNamespace(
        mesh=mesh,
        element=SimpleNamespace(basix_element=basix_element),
        dofmap=make_space_dofmap(),
    )
    mpc_cells = [cell.copy() for cell in cells]
    mpc_wrapper = SimpleNamespace(
        mesh=mesh,
        element=SimpleNamespace(basix_element=basix_element),
        dofmap=SimpleNamespace(
            index_map=make_index_map(),
            index_map_bs=1,
            cell_dofs=lambda cell: mpc_cells[int(cell)],
        ),
    )

    assert mpc_wrapper is not expected
    assert _same_v23_mpc_function_space_layout(expected, mpc_wrapper)

    mpc_wrapper.dofmap.index_map.size_global -= 1
    assert not _same_v23_mpc_function_space_layout(expected, mpc_wrapper)
    mpc_wrapper.dofmap.index_map.size_global = expected.dofmap.index_map.size_global

    mpc_wrapper.dofmap.index_map.local_range = (1, 1_001)
    assert not _same_v23_mpc_function_space_layout(expected, mpc_wrapper)
    mpc_wrapper.dofmap.index_map.local_range = expected.dofmap.index_map.local_range

    mpc_wrapper.dofmap.index_map.ghosts[0] -= 1
    assert not _same_v23_mpc_function_space_layout(expected, mpc_wrapper)
    mpc_wrapper.dofmap.index_map.ghosts[0] = expected.dofmap.index_map.ghosts[0]

    mpc_wrapper.dofmap.index_map.owners[0] = 0
    assert not _same_v23_mpc_function_space_layout(expected, mpc_wrapper)
    mpc_wrapper.dofmap.index_map.owners[0] = expected.dofmap.index_map.owners[0]

    # Keep cell zero identical: only a mismatch on the second owned cell rejects it.
    mpc_cells[1][0], mpc_cells[1][1] = mpc_cells[1][1], mpc_cells[1][0]
    assert not _same_v23_mpc_function_space_layout(expected, mpc_wrapper)


def test_v23_checkpoint_round_trip_restores_exact_prefix_state(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "TASK40_V10_CAMPAIGN_WINDOW_SHA256", TASK40_V23_CAMPAIGN_SHA256
    )
    preflight = {
        "source_sha": "1" * 40,
        "input_sha256": "2" * 64,
        "physical_model_sha256": "3" * 64,
        "run_id": "fixture-run",
    }
    mode_inventory = {
        "mode_manifest_sha256": "4" * 64,
        "ordered_mode_key_sha256": "5" * 64,
    }
    candidate = np.array([10, 12, 15], dtype=np.int64)
    window_sha = TASK40_V23_CAMPAIGN_SHA256
    checkpoint_directory = _v23_checkpoint_directory(
        tmp_path,
        preflight=preflight,
        mode_inventory=mode_inventory,
        campaign_window_sha256=window_sha,
    )
    modes = [SimpleNamespace(side="bottom"), SimpleNamespace(side="top")]
    h_values = np.array([1.5, 2.5], dtype=np.float64)
    rng_state = np.random.default_rng(47).bit_generator.state
    stream = _RollingDigest()
    stream.update(b"prefix")
    filter_audit = {
        side: {
            str(component): {"retained_stream_sha256": "a" * 64}
            for component in (0, 1)
        }
        for side in ("bottom", "top")
    }
    categories = {
        side: {
            component: {
                category: 0
                for category in (
                    "interior",
                    "actual_port_face_trace",
                    "other_trace",
                    "slave",
                    "unknown",
                )
            }
            for component in ("B", "D")
        }
        for side in ("bottom", "top")
    }
    cell_state = {
        side: {
            metric: {
                "per_cell_mode_counts": np.array([1, 0], dtype=np.int64),
                "per_cell_interior_row_memberships": np.array([2, 0], dtype=np.int64),
            }
            for metric in ("B", "D", "union")
        }
        for side in ("bottom", "top")
    }
    output_directory = tmp_path / "run-output"
    checkpoint = _write_v22_action_checkpoint(
        output_directory,
        preflight=preflight,
        mode_inventory=mode_inventory,
        mode_count=2,
        mode_counts_by_side={"bottom": 1, "top": 1},
        class_mode_prefix={
            "bottom": {"class-bottom": 1},
            "top": {"class-top": 1},
        },
        support_rows_by_side={
            side: {"B": 1, "D": 2, "nonempty_B_modes": 1, "nonempty_D_modes": 1}
            for side in ("bottom", "top")
        },
        stream_digest=stream,
        component_filter_audit=filter_audit,
        b_action=np.array([1.0 + 2.0j, 0.0j, 0.0j]),
        d_values=np.array([3.0 + 1.0j, 4.0 + 2.0j]),
        h_values=h_values,
        candidate_rows=candidate,
        checkpoint_directory=checkpoint_directory,
        checkpoint_interval=256,
        restart_state={
            "field_sha256": "6" * 64,
            "rng_state": rng_state,
            "m_c_state": cell_state,
            "support_category_totals": categories,
            "calibration_results": {"bottom": {"status": "MEASURED"}},
            "mode_sweep_elapsed_seconds": 12.5,
            "mode_sweep_process_cpu_seconds": 11.0,
            "mode_timing_by_side": {
                "bottom": {"completed_modes": 1, "wall_seconds": 6.0, "process_cpu_seconds": 5.5},
                "top": {"completed_modes": 1, "wall_seconds": 6.0, "process_cpu_seconds": 5.5},
            },
            "expected_mode_counts_by_side": {"bottom": 1, "top": 1},
        },
    )
    assert checkpoint["next_mode_index"] == 2
    assert checkpoint["compact_candidate_rows_sha256"]
    assert checkpoint["checkpoint_json_path"].startswith("../")

    restored = _load_v23_action_checkpoint(
        checkpoint_directory,
        preflight=preflight,
        mode_inventory=mode_inventory,
        campaign_window_sha256=window_sha,
        candidate_rows=candidate,
        modes=modes,
        h_values=h_values,
        side_cell_counts={"bottom": 2, "top": 2},
        expected_field_sha256="6" * 64,
    )

    assert restored is not None
    assert restored["mode_count"] == 2
    assert np.array_equal(restored["b_action"], [1.0 + 2.0j, 0.0j, 0.0j])
    assert np.array_equal(restored["d_values"], [3.0 + 1.0j, 4.0 + 2.0j])
    assert restored["cell_state"]["bottom"]["B"]["per_cell_mode_counts"].tolist() == [1, 0]
    assert restored["stream_digest_state"] == stream.hexdigest()
    assert restored["rng_state"] == rng_state
    assert restored["mode_sweep_process_cpu_seconds"] == 11.0
    assert restored["mode_timing_by_side"]["top"]["completed_modes"] == 1
