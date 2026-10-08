"""Focused contracts and a real three-box H(curl)/Floquet fixture."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.high_order_floquet_trace import face_coefficient_transform
from src.coupling.hybrid_internal_modes import _destroy_pending_exact_overrides
from src.coupling.hybrid_one_cell_exact_traction import (
    EXACT_ONE_CELL_TRACTION_MODEL,
    ExactOneCellCoupling,
    _transfer_entity_block,
    congruent_trace_identity,
    embed_exact_trace_columns_dense_reference,
    exact_model_record,
    require_congruent_trace_identity,
    split_exact_local_amplitude_blocks,
    transfer_congruent_endpoint_columns,
    transfer_congruent_endpoint_dual_columns,
)
from src.coupling.hybrid_one_cell_exact_traction_builder import (
    _identity_comparison_slices,
    _sampled_direct_relift_metadata,
    _validate_sampled_direct_relift_contract,
)
from src.coupling.hybrid_one_cell_exact_traction_builder import (
    _one_cell_config as build_one_cell_config,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d, stage4_axis_plan
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.stable_propagation import build_two_sided_propagation
from src.solvers import one_cell_trace_schur as one_cell_trace_schur_module
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_static_field_recovery import _add_internal_tractions
from src.solvers.one_cell_trace_schur import (
    EndpointModeLifter,
    _active_values_for_port,
    apply_directional_endpoint_columns,
    assemble_directional_endpoint_columns,
    build_one_cell_two_port_schur_action,
    identify_endpoint_active_rows,
)
from src.solvers.one_cell_trace_schur import (
    _factor as factor_one_cell_interior,
)


def test_one_cell_interior_factor_forwards_explicit_stage_factory() -> None:
    matrix = object()
    expected_factor = object()
    calls: list[tuple[object, int]] = []

    def stage_factory(source: object, *, icntl14: int) -> object:
        calls.append((source, icntl14))
        return expected_factor

    factor = factor_one_cell_interior(matrix, stage_factory=stage_factory)
    assert factor is expected_factor
    assert calls == [(matrix, 100)]


def test_one_cell_schur_builder_forwards_stage_factory_to_same_interior_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBlock:
        def __init__(self, *, nnz: int = 0) -> None:
            self.nnz = nnz
            self.destroyed = False

        def getInfo(self, _info_type: object) -> dict[str, float]:
            return {"nz_used": float(self.nnz)}

        def destroy(self) -> None:
            self.destroyed = True

    class FakeStageFactor:
        explicit_staged_direct_factor = True

        def __init__(self) -> None:
            self.destroyed = False

        def destroy(self) -> dict[str, object]:
            self.destroyed = True
            return {
                "factor_released": True,
                "destroy_error_code": 0,
            }

    blocks = tuple(FakeBlock(nnz=4 if index == 3 else 0) for index in range(4))
    expected_factor = FakeStageFactor()
    calls: list[tuple[object, int]] = []
    matrix = object()
    rows = SimpleNamespace(
        port_active=np.asarray([0, 1], dtype=np.int64),
        interior_active=np.asarray([2], dtype=np.int64),
        left_active=np.asarray([0], dtype=np.int64),
        right_active=np.asarray([1], dtype=np.int64),
    )

    def partition(
        _matrix: object,
        _port_active: object,
        _interior_active: object,
    ) -> tuple[FakeBlock, ...]:
        return blocks

    def stage_factory(source: object, *, icntl14: int) -> FakeStageFactor:
        calls.append((source, icntl14))
        return expected_factor

    monkeypatch.setattr(
        one_cell_trace_schur_module,
        "_partition_sparse_matrix",
        partition,
    )
    action = build_one_cell_two_port_schur_action(
        matrix, rows, stage_factory=stage_factory  # type: ignore[arg-type]
    )
    assert calls == [(blocks[3], 100)]
    assert action.factor is expected_factor
    action.destroy()
    assert expected_factor.destroyed is True
    assert all(block.destroyed for block in blocks)


def test_exact_model_is_explicit_and_not_production_qualified() -> None:
    record = exact_model_record(True)
    assert record["model"] == EXACT_ONE_CELL_TRACTION_MODEL
    assert record["research_only"] is True
    assert record["production_qualified"] is False
    assert exact_model_record(False)["model"] == "ordinary_default"


@pytest.mark.parametrize(
    ("h_nm", "expected_xy_cells"),
    [(10.0, (6, 3)), (5.0, (12, 5))],
)
def test_exact_builder_matches_source_xy_axis_plan(
    h_nm: float, expected_xy_cells: tuple[int, int]
) -> None:
    cfg = target_stage4_config(degree=6, h_nm=h_nm)
    comm_size = MPI.COMM_WORLD.size
    source_plan = stage4_axis_plan(cfg, comm_size)
    one_cell = build_one_cell_config(cfg, comm_size)
    one_cell_plan = stage4_axis_plan(one_cell, comm_size)

    assert one_cell.z_min == 0.0
    assert one_cell.z_max == 10.0
    assert one_cell.mesh_axis_cell_counts == (*expected_xy_cells, 1)
    assert one_cell.mesh_axis_z_values == (0.0, 10.0)
    assert one_cell.mesh_axis_z_profile == "task037c_x3_uniform_10nm_one_cell"
    assert source_plan.mesh_cells_resolved[:2] == expected_xy_cells
    assert one_cell_plan.mesh_cells_resolved == (*expected_xy_cells, 1)
    np.testing.assert_allclose(one_cell_plan.x_values, source_plan.x_values)
    np.testing.assert_allclose(one_cell_plan.y_values, source_plan.y_values)
    np.testing.assert_allclose(one_cell_plan.z_values, (0.0, 10.0))


def test_exact_blocks_split_each_local_amplitude_and_keep_sign_contract() -> None:
    forward = np.asarray([[1, 2], [3, 4], [5, 6], [7, 8]], dtype=np.complex128)
    backward = 2.0 * forward
    blocks = split_exact_local_amplitude_blocks(
        forward,
        backward,
        left_rows=2,
        right_rows=2,
        forward_factors=[2, 4],
        backward_factors=[3, 5],
    )
    np.testing.assert_allclose(blocks["bottom_forward"], [[1, 2], [3, 4]])
    np.testing.assert_allclose(blocks["top_forward"], [[2.5, 1.5], [3.5, 2]])
    np.testing.assert_allclose(blocks["bottom_backward"], [[2 / 3, 4 / 5], [2, 8 / 5]])
    np.testing.assert_allclose(blocks["top_backward"], [[10, 12], [14, 16]])


def test_exact_blocks_reject_zero_factor() -> None:
    with pytest.raises(ValueError, match="finite and nonzero"):
        split_exact_local_amplitude_blocks(
            np.ones((2, 1)),
            np.ones((2, 1)),
            left_rows=1,
            right_rows=1,
            forward_factors=[0],
            backward_factors=[1],
        )


def test_entity_block_dual_transfer_preserves_vdot_pairing() -> None:
    source_transform = np.asarray([[1.0, 0.25], [0.0, 1.0]], dtype=np.complex128)
    target_transform = np.asarray([[0.75, -0.5], [0.25, 1.25]], dtype=np.complex128)
    source_phase = 1.0 + 0.25j
    target_phase = 0.8 - 0.1j
    primal = np.asarray([[1.0 + 2.0j, -2.0 + 0.5j], [3.0 - 1.0j, 0.25 + 4.0j]])
    dual = np.asarray([[2.0 - 0.5j, 1.0 + 0.25j], [-1.0 + 3.0j, 2.5 - 2.0j]])
    target_primal = _transfer_entity_block(
        primal,
        source_transform,
        source_phase,
        target_transform,
        target_phase,
    )
    target_dual = _transfer_entity_block(
        dual,
        source_transform,
        source_phase,
        target_transform,
        target_phase,
        dual=True,
    )
    for column in range(primal.shape[1]):
        assert (
            abs(
                np.vdot(target_primal[:, column], target_dual[:, column])
                - np.vdot(primal[:, column], dual[:, column])
            )
            <= 1.0e-12
        )


def test_p6_face_entity_transfer_covers_non_diagonal_basix_block() -> None:
    transform = face_coefficient_transform(6, (1, 3, 0, 2))
    assert transform.shape[0] == transform.shape[1]
    off_diagonal = transform - np.diag(np.diag(transform))
    assert np.linalg.norm(off_diagonal) > 1.0e-12
    canonical = np.arange(transform.shape[1], dtype=np.complex128) + 1.0j
    stored = transform @ canonical
    recovered = _transfer_entity_block(
        stored[:, None],
        transform,
        1.0 + 0.0j,
        np.eye(transform.shape[0], dtype=np.complex128),
        1.0 + 0.0j,
    )
    np.testing.assert_allclose(recovered[:, 0], canonical, rtol=0.0, atol=1.0e-12)


def test_floquet_phase_identity_is_explicit_and_fail_closed() -> None:
    from src.coupling.hybrid_one_cell_exact_traction import _floquet_phase_identity

    source = SimpleNamespace(
        phase_x=1.0 + 0.25j,
        phase_y=0.75 - 0.5j,
        phase_corner=(1.0 + 0.25j) * (0.75 - 0.5j),
    )
    same = _floquet_phase_identity(source, SimpleNamespace(**vars(source)))
    assert same["floquet_phase_identity"] is True
    assert same["floquet_phase_delta_max"] == 0.0
    changed = SimpleNamespace(**vars(source))
    changed.phase_y += 1.0e-8
    with pytest.raises(RuntimeError, match="phases differ"):
        _floquet_phase_identity(source, changed)
    nan_phase = SimpleNamespace(**vars(source))
    nan_phase.phase_x = complex(np.nan, 0.0)
    with pytest.raises(RuntimeError, match="must be finite"):
        _floquet_phase_identity(source, nan_phase)


def test_exact_one_cell_and_hybrid_propagation_lengths_are_distinct() -> None:
    modes = (
        SimpleNamespace(
            beta=0.01 + 0.0j,
            direction="forward",
            passive_branch_valid=True,
        ),
        SimpleNamespace(
            beta=-0.01 + 0.0j,
            direction="backward",
            passive_branch_valid=True,
        ),
    )
    cell = build_two_sided_propagation(
        modes,
        10.0,
        propagation_model="full3d_uniform_cg",
        axial_fem_degree=2,
        axial_h_nm=10.0,
    )
    middle = build_two_sided_propagation(
        modes,
        100.0,
        propagation_model="full3d_uniform_cg",
        axial_fem_degree=2,
        axial_h_nm=10.0,
    )
    assert cell.length_nm == 10.0
    assert middle.length_nm == 100.0
    assert not np.allclose(cell.forward.factors, middle.forward.factors)
    assert not np.allclose(cell.backward.factors, middle.backward.factors)


def test_exact_recovery_does_not_reassemble_scalar_traction() -> None:
    result = _add_internal_tractions(
        None,
        SimpleNamespace(modal_traction_model=EXACT_ONE_CELL_TRACTION_MODEL),
        np.zeros(2, dtype=np.complex128),
        None,
    )
    assert result["internal_mode_surface_vectors_reassembled"] == 0
    assert result["traction_beta_source"] == "not_used_exact_one_cell_schur"
    assert result["exact_reduced_trace_columns"] is True
    assert result["zero_eliminated_interior_support"] is True


def test_row_identity_and_embedding_are_ordered_and_fail_closed() -> None:
    exact = np.asarray([[1 + 2j, 2], [3, 4 - 1j]], dtype=np.complex128)
    audit = require_congruent_trace_identity(exact, exact + 1.0e-14, side="bottom")
    assert audit["pass"] is True
    assert audit["rows"] == 2
    assert audit["columns"] == 2
    with pytest.raises(ValueError, match="shapes differ"):
        congruent_trace_identity(exact, exact[:1], side="top")
    embedded = embed_exact_trace_columns_dense_reference([4, 1], exact, local_fe_rows=6)
    np.testing.assert_allclose(embedded[[4, 1]], exact)
    assert np.count_nonzero(embedded[[0, 2, 3, 5]]) == 0


def test_endpoint_transfer_rejects_row_count_mismatch() -> None:
    with pytest.raises(ValueError, match="Source/target endpoint row counts differ"):
        transfer_congruent_endpoint_columns(
            np.ones((2, 1), dtype=np.complex128),
            None,
            None,
            None,
            [0, 1],
            None,
            None,
            None,
            [0, 1, 2],
            source_endpoint="left",
            target_endpoint="right",
        )


def test_row_identity_rejects_material_difference() -> None:
    exact = np.eye(2, dtype=np.complex128)
    with pytest.raises(RuntimeError, match="identity failed"):
        require_congruent_trace_identity(exact, exact + 1.0e-3, side="top")


def test_exact_carrier_reports_four_blocks_and_release() -> None:
    blocks = {
        name: np.ones((2, 3), dtype=np.complex128)
        for name in (
            "bottom_forward",
            "top_forward",
            "bottom_backward",
            "top_backward",
        )
    }
    carrier = ExactOneCellCoupling(
        blocks=blocks,
        bottom_rows=np.asarray([2, 4]),
        top_rows=np.asarray([1, 3]),
        row_identity={
            "bottom": {"positive": {"pass": True}, "raw_negative": {"pass": True}},
            "top": {"positive": {"pass": True}, "raw_negative": {"pass": True}},
        },
        action_audit={"port_rows": 4, "interior_rows": 6, "interior_matrix_nnz": 12},
    )
    audit = carrier.audit()
    assert audit["block_shapes"]["bottom_forward"] == [2, 3]
    assert audit["dense_endpoint_square_formed"] is False
    assert audit["exact_reduced_trace_columns"] is True
    assert audit["port_rows"] == 4
    assert audit["interior_rows"] == 6
    assert audit["interior_matrix_nnz"] == 12
    assert audit["transient_released"] is True


def test_sampled_direct_relift_contract_preserves_order_and_branch_slices() -> None:
    mode_count = 6
    columns = [5, 6, 0, 7, 4, 10, 1, 11]
    roles = {str(column): ["sample"] for column in columns}
    payload = {
        "columns": columns,
        "mode_count_per_direction": mode_count,
        "roles": roles,
    }
    contract_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    plan = _validate_sampled_direct_relift_contract(
        {
            **payload,
            "sha256": contract_sha256,
            "fresh_packet_binding": {
                "sampled_column_contract_sha256": contract_sha256
            },
        },
        mode_count,
    )
    assert plan["global_columns"] == (5, 6, 0, 7, 4, 10, 1, 11)
    assert plan["positive_global_columns"] == (5, 0, 4, 1)
    assert plan["negative_global_columns"] == (6, 7, 10, 11)
    assert plan["positive_positions"] == (0, 2, 4, 6)
    assert plan["negative_positions"] == (1, 3, 5, 7)
    omitted = {2, 3, 8, 9}
    assert omitted.isdisjoint(plan["global_columns"])
    transferred = np.arange(24, dtype=np.float64).reshape(2, 12).astype(
        np.complex128
    )
    sampled_primal_input = transferred[:, columns]
    sampled_primal_output = sampled_primal_input.copy()
    assert sampled_primal_input.shape[1] == 8
    assert sampled_primal_output.shape[1] == 8
    positive, positive_reference, negative, negative_reference = (
        _identity_comparison_slices(
            sampled_primal_output, sampled_primal_input, plan, mode_count
        )
    )
    np.testing.assert_array_equal(positive, transferred[:, [5, 0, 4, 1]])
    np.testing.assert_array_equal(
        positive_reference, sampled_primal_input[:, [0, 2, 4, 6]]
    )
    np.testing.assert_array_equal(negative, transferred[:, [6, 7, 10, 11]])
    np.testing.assert_array_equal(
        negative_reference, sampled_primal_input[:, [1, 3, 5, 7]]
    )
    full = _identity_comparison_slices(
        transferred, transferred, None, mode_count
    )
    np.testing.assert_array_equal(full[0], transferred[:, :mode_count])
    np.testing.assert_array_equal(full[2], transferred[:, mode_count:])
    assert _sampled_direct_relift_metadata(plan, mode_count) == {
        "sampled_column_contract_sha256": plan["sha256"],
        "sample_global_columns": columns,
        "direct_relift_columns": 8,
        "primal_validation_transfer_columns": 8,
        "dual_operator_transfer_columns": 12,
        "total_operator_source_columns": 12,
        "validation_scope": "all-row canonical bijection plus hash-bound sampled values",
    }


def test_sampled_direct_relift_contract_rejects_changed_sha_or_binding() -> None:
    columns = [0, 1, 2, 4, 5, 6, 7, 8]
    payload = {
        "columns": columns,
        "mode_count_per_direction": 5,
        "roles": {str(column): ["sample"] for column in columns},
    }
    contract_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    contract = {
        **payload,
        "sha256": contract_sha256,
        "fresh_packet_binding": {
            "sampled_column_contract_sha256": contract_sha256
        },
    }
    changed = {**contract, "columns": [0, 1, 2, 3, 5, 6, 7, 8]}
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        _validate_sampled_direct_relift_contract(changed, 5)
    mismatched_binding = {
        **contract,
        "fresh_packet_binding": {"sampled_column_contract_sha256": "0" * 64},
    }
    with pytest.raises(ValueError, match="binding SHA256 mismatch"):
        _validate_sampled_direct_relift_contract(mismatched_binding, 5)


@pytest.mark.parametrize("columns", ([0, 0, 4], [0, 8], [0, 1], [4, 5]))
def test_sampled_direct_relift_contract_rejects_invalid_coverage(columns) -> None:
    with pytest.raises(ValueError, match="Sampled direct re-lift contract"):
        _validate_sampled_direct_relift_contract(
            {
                "columns": columns,
                "mode_count_per_direction": 4,
                "roles": {str(column): ["sample"] for column in columns},
                "sha256": "a" * 64,
                "fresh_packet_binding": {
                    "sampled_column_contract_sha256": "a" * 64
                },
            },
            4,
        )


def test_pending_exact_override_cleanup_only_releases_unclaimed_pairs() -> None:
    class Probe:
        def __init__(self) -> None:
            self.destroy_count = 0

        def destroy(self) -> None:
            self.destroy_count += 1

    bottom = (Probe(), Probe())
    top = (Probe(), Probe())
    pending = {"bottom": bottom, "top": top}
    transferred = pending.pop("bottom")
    _destroy_pending_exact_overrides(pending)
    assert all(item.destroy_count == 0 for item in transferred)
    assert all(item.destroy_count == 1 for item in top)
    assert pending == {}


def test_real_p2_double_floquet_endpoint_and_local_interface_identity(tmp_path) -> None:
    """Compare independent bottom/middle/top p2 H(curl) Floquet boxes."""

    base = build_one_cell_config(
        target_stage4_config(degree=2, h_nm=10.0), MPI.COMM_WORLD.size
    )
    comm = MPI.COMM_WORLD

    def box_config(label: str, z0: float, z1: float):
        return replace(
            base,
            case_name=f"task037c_x3_{label}_box",
            z_min=z0,
            z_max=z1,
            air_height=z1 - z0,
            substrate_thickness=0.0,
            interface_z=z0,
            grating_height=z1 - z0,
            mesh_axis_z_values=(z0, z1),
            mesh_axis_z_profile=f"task037c_x3_{label}_10nm_one_cell",
        )

    def build_box(cfg, root, materialize):
        mesh_data = build_airbox_mesh_3d(cfg, root)
        V = fem.functionspace(
            mesh_data.mesh,
            element(
                "N1curl",
                mesh_data.mesh.basix_cell(),
                cfg.nedelec_trace_degree_resolved,
                dtype=default_real_type,
            ),
        )
        bilinear, _ = _build_variational_forms(mesh_data.mesh, mesh_data, cfg, V)
        floquet = build_double_floquet_mpc(V, mesh_data, cfg)
        condensed = build_unconstrained_assembly_time_condensation(
            fem.form(bilinear),
            V,
            mesh_data.cell_tags,
            mpc=floquet.mpc,
            materialize_global_matrix=materialize,
            retain_local_schur_for_matrix_free=not materialize,
        )
        assert (condensed.matrix is not None) is materialize
        tdim = mesh_data.mesh.topology.dim
        left_facets = mesh.locate_entities_boundary(
            mesh_data.mesh,
            tdim - 1,
            lambda x: np.isclose(x[2], cfg.domain_z_min),
        )
        right_facets = mesh.locate_entities_boundary(
            mesh_data.mesh,
            tdim - 1,
            lambda x: np.isclose(x[2], cfg.domain_z_max),
        )
        rows = identify_endpoint_active_rows(
            V,
            condensed,
            left_facets=left_facets,
            right_facets=right_facets,
        )
        return mesh_data, V, floquet, condensed, rows, left_facets, right_facets

    shared_root = Path(comm.bcast(str(tmp_path / "mpi_shared"), root=0))
    if comm.rank == 0:
        shared_root.mkdir(parents=True, exist_ok=True)
    comm.Barrier()
    middle = build_box(box_config("middle", 0.0, 10.0), shared_root / "middle", True)
    bottom = build_box(box_config("bottom", -10.0, 0.0), shared_root / "bottom", False)
    top = build_box(box_config("top", 10.0, 20.0), shared_root / "top", False)
    cross_section = build_matching_cross_section(base, "stage4_xy", comm=comm)
    spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
    positive_like = fem.Function(spaces.transverse)
    positive_like.interpolate(lambda x: np.vstack((1.0 + x[0], 2.0 + x[1])))
    positive_like.x.scatter_forward()
    raw_negative_like = fem.Function(spaces.transverse)
    raw_negative_like.interpolate(
        lambda x: np.vstack((3.0 - 0.5 * x[1], 1.0 + 0.25 * x[0]))
    )
    raw_negative_like.x.scatter_forward()

    def endpoint_pair(box, lifter, source, left_rows, right_rows):
        _, _, floquet, condensed, _, _, _ = box
        field = lifter.lift(source)
        floquet.mpc.homogenize(field)
        field.x.scatter_forward()
        return (
            _active_values_for_port(field, condensed, left_rows),
            _active_values_for_port(field, condensed, right_rows),
        )

    try:
        middle_lifter = EndpointModeLifter(middle[1], max(base.period_x, base.period_y))
        bottom_lifter = EndpointModeLifter(bottom[1], max(base.period_x, base.period_y))
        top_lifter = EndpointModeLifter(top[1], max(base.period_x, base.period_y))
        middle_pos_left, middle_pos_right = endpoint_pair(
            middle,
            middle_lifter,
            positive_like,
            middle[4].left_active,
            middle[4].right_active,
        )
        _, bottom_pos_right = endpoint_pair(
            bottom,
            bottom_lifter,
            positive_like,
            bottom[4].left_active,
            bottom[4].right_active,
        )
        top_pos_left, _ = endpoint_pair(
            top,
            top_lifter,
            positive_like,
            top[4].left_active,
            top[4].right_active,
        )
        middle_neg_left, middle_neg_right = endpoint_pair(
            middle,
            middle_lifter,
            raw_negative_like,
            middle[4].left_active,
            middle[4].right_active,
        )
        _, bottom_neg_right = endpoint_pair(
            bottom,
            bottom_lifter,
            raw_negative_like,
            bottom[4].left_active,
            bottom[4].right_active,
        )
        top_neg_left, _ = endpoint_pair(
            top,
            top_lifter,
            raw_negative_like,
            top[4].left_active,
            top[4].right_active,
        )
        bottom_pos_transferred, bottom_transfer_audit = (
            transfer_congruent_endpoint_columns(
                middle_pos_left[:, None],
                middle[1],
                middle[3],
                middle[2],
                middle[4].left_active,
                bottom[1],
                bottom[3],
                bottom[2],
                bottom[4].right_active,
                source_endpoint="left",
                target_endpoint="right",
            )
        )
        top_pos_transferred, top_transfer_audit = transfer_congruent_endpoint_columns(
            middle_pos_right[:, None],
            middle[1],
            middle[3],
            middle[2],
            middle[4].right_active,
            top[1],
            top[3],
            top[2],
            top[4].left_active,
            source_endpoint="right",
            target_endpoint="left",
        )
        bottom_neg_transferred, bottom_negative_transfer_audit = (
            transfer_congruent_endpoint_columns(
                middle_neg_left[:, None],
                middle[1],
                middle[3],
                middle[2],
                middle[4].left_active,
                bottom[1],
                bottom[3],
                bottom[2],
                bottom[4].right_active,
                source_endpoint="left",
                target_endpoint="right",
            )
        )
        top_neg_transferred, top_negative_transfer_audit = (
            transfer_congruent_endpoint_columns(
                middle_neg_right[:, None],
                middle[1],
                middle[3],
                middle[2],
                middle[4].right_active,
                top[1],
                top[3],
                top[2],
                top[4].left_active,
                source_endpoint="right",
                target_endpoint="left",
            )
        )
        audits = {
            "bottom_positive_like": require_congruent_trace_identity(
                bottom_pos_transferred, bottom_pos_right[:, None], side="bottom"
            ),
            "top_positive_like": require_congruent_trace_identity(
                top_pos_transferred, top_pos_left[:, None], side="top"
            ),
            "bottom_raw_negative_like": require_congruent_trace_identity(
                bottom_neg_transferred, bottom_neg_right[:, None], side="bottom"
            ),
            "top_raw_negative_like": require_congruent_trace_identity(
                top_neg_transferred, top_neg_left[:, None], side="top"
            ),
        }
        transfer_audits = {
            "bottom_positive_like": bottom_transfer_audit,
            "top_positive_like": top_transfer_audit,
            "bottom_raw_negative_like": bottom_negative_transfer_audit,
            "top_raw_negative_like": top_negative_transfer_audit,
        }
        assert all(item["bijection"] for item in transfer_audits.values())
        assert all(item["entity_block_count"] > 0 for item in transfer_audits.values())
        assert all(
            item["max_entity_block_size"] <= 12 for item in transfer_audits.values()
        )
        if comm.rank == 0:
            print(
                "x3 row identity relative_l2: "
                + ", ".join(
                    f"{name}={audit['relative_l2']:.3e}"
                    for name, audit in audits.items()
                )
            )
        assert all(audit["pass"] is True for audit in audits.values())
        assert all(audit["relative_l2"] <= 1.0e-10 for audit in audits.values())
        assert all(
            np.linalg.norm(values) > 0.0
            for values in (middle_pos_left, middle_neg_left)
        )
        action = build_one_cell_two_port_schur_action(middle[3].matrix, middle[4])
        try:
            flux = action.apply_columns(
                np.eye(action.port_rows, 1, dtype=np.complex128)
            )
            assert flux.shape == (action.port_rows, 1)
            assert np.all(np.isfinite(flux))
            assert action.dense_interface_square_formed is False
        finally:
            action.destroy()
    finally:
        for box in (bottom, top, middle):
            box[3].destroy()


def _task037c_probe_segment_config(
    base_cfg,
    label: str,
    z0: float,
    z1: float,
    nz: int,
    *,
    case_prefix: str = "proposed_formula_test_only",
):
    updates = {
        "case_name": f"{case_prefix}_{label}",
        "z_min": z0,
        "z_max": z1,
        "air_height": z1 - z0,
        "substrate_thickness": 0.0,
        "interface_z": z0,
        "grating_height": z1 - z0,
        "grating_width_x": base_cfg.period_x,
        "grating_width_y": base_cfg.period_y,
        "mesh_cell_type": "hexahedron",
        "mesh_spacing_mode": "boundary_fitted",
        "mesh_axis_cell_counts": (2, 2, nz),
        "mesh_axis_z_values": tuple(np.linspace(z0, z1, nz + 1)),
        "mesh_axis_z_profile": f"{case_prefix}_{label}_z",
    }
    return replace(base_cfg, **updates)


def _task037c_destroy_probe_box(box) -> None:
    if box["action"] is not None:
        box["action"].destroy()
        box["action"] = None
    if box["condensed"] is not None:
        box["condensed"].destroy()
        box["condensed"] = None
    if box["floquet"] is not None:
        destroy = getattr(box["floquet"].mpc, "destroy", None)
        if callable(destroy):
            destroy()
        box["floquet"] = None


def _task037c_build_probe_box(cfg, root: Path):
    box = {
        "mesh_data": None,
        "space": None,
        "floquet": None,
        "condensed": None,
        "rows": None,
        "action": None,
    }
    try:
        box["mesh_data"] = build_airbox_mesh_3d(cfg, root)
        box["space"] = fem.functionspace(
            box["mesh_data"].mesh,
            element(
                "N1curl",
                box["mesh_data"].mesh.basix_cell(),
                cfg.nedelec_trace_degree_resolved,
                dtype=default_real_type,
            ),
        )
        bilinear, _ = _build_variational_forms(
            box["mesh_data"].mesh,
            box["mesh_data"],
            cfg,
            box["space"],
        )
        box["floquet"] = build_double_floquet_mpc(
            box["space"], box["mesh_data"], cfg
        )
        box["condensed"] = build_unconstrained_assembly_time_condensation(
            fem.form(bilinear),
            box["space"],
            box["mesh_data"].cell_tags,
            mpc=box["floquet"].mpc,
            materialize_global_matrix=True,
        )
        assert box["condensed"].matrix is not None
        tdim = box["mesh_data"].mesh.topology.dim
        left_facets = mesh.locate_entities_boundary(
            box["mesh_data"].mesh,
            tdim - 1,
            lambda x: np.isclose(x[2], cfg.domain_z_min),
        )
        right_facets = mesh.locate_entities_boundary(
            box["mesh_data"].mesh,
            tdim - 1,
            lambda x: np.isclose(x[2], cfg.domain_z_max),
        )
        box["rows"] = identify_endpoint_active_rows(
            box["space"],
            box["condensed"],
            left_facets=left_facets,
            right_facets=right_facets,
        )
        return box
    except Exception:
        _task037c_destroy_probe_box(box)
        raise


def _task037c_probe_endpoint_trace(box, lifter, source):
    field = lifter.lift(source)
    box["floquet"].mpc.homogenize(field)
    field.x.scatter_forward()
    return (
        _active_values_for_port(
            field, box["condensed"], box["rows"].left_active
        ),
        _active_values_for_port(
            field, box["condensed"], box["rows"].right_active
        ),
    )


def _task037c_probe_elimination_audit(
    action,
    columns,
    *,
    mesh_cells_z: int,
    action_values=None,
):
    """Share the two-node residual/action audit without hiding an extra apply."""
    ports = np.asarray(columns, dtype=np.complex128)
    assert ports.shape == (action.port_rows, 2)
    assert np.all(np.isfinite(ports))
    recovered = action.recover_homogeneous_columns(ports)
    action_values_source = (
        "fresh_action_apply_columns"
        if action_values is None
        else "reused_caller_action_values"
    )
    endpoint_action = (
        action.apply_columns(ports) if action_values is None else action_values
    )
    endpoint_action = np.asarray(endpoint_action, dtype=np.complex128)
    assert endpoint_action.shape == ports.shape
    assert np.all(np.isfinite(endpoint_action))

    matrices = {
        "Aip_port": (action.A_ip, "right"),
        "Aip_rhs": (action.A_ip, "left"),
        "Aii_solution": (action.A_ii, "right"),
        "Aii_residual": (action.A_ii, "left"),
        "App_port": (action.A_pp, "right"),
        "App_value": (action.A_pp, "left"),
        "Api_interior": (action.A_pi, "right"),
        "Api_value": (action.A_pi, "left"),
    }
    vectors = {}
    tolerance = 5.0e-9
    equations, block_checks = [], []
    try:
        for name, (matrix, side) in matrices.items():
            factory = matrix.createVecRight if side == "right" else matrix.createVecLeft
            vectors[name] = factory()
        for column in range(ports.shape[1]):
            for name, values in (
                ("Aip_port", ports),
                ("App_port", ports),
                ("Aii_solution", recovered[action.interior_active]),
                ("Api_interior", recovered[action.interior_active]),
            ):
                first, last = map(int, vectors[name].getOwnershipRange())
                vectors[name].getArray()[:] = values[first:last, column]
                vectors[name].assemble()
            action.A_ip.mult(vectors["Aip_port"], vectors["Aip_rhs"])
            action.A_ii.mult(
                vectors["Aii_solution"], vectors["Aii_residual"]
            )
            vectors["Aii_residual"].axpy(1.0, vectors["Aip_rhs"])
            rhs = action._replicated_values(vectors["Aip_rhs"])
            residual = action._replicated_values(vectors["Aii_residual"])
            rhs_norm = float(np.linalg.norm(rhs))
            residual_norm = float(np.linalg.norm(residual))
            finite = bool(
                np.all(np.isfinite(rhs))
                and np.all(np.isfinite(residual))
                and np.isfinite(rhs_norm)
                and np.isfinite(residual_norm)
            )
            assert finite
            relative = residual_norm / rhs_norm if rhs_norm > 0.0 else None
            branch = (
                "relative_to_norm_Aip_up"
                if relative is not None
                else "absolute_zero_rhs"
            )
            passed = bool(
                relative <= tolerance
                if relative is not None
                else residual_norm <= tolerance
            )
            equations.append(
                {
                    "column": column,
                    "equation": "A_ii*u_i + A_ip*u_p",
                    "norm_Aip_up": rhs_norm,
                    "residual_norm": residual_norm,
                    "relative_residual": relative,
                    "normalization_branch": branch,
                    "limit": tolerance,
                    "finite": finite,
                    "pass": passed,
                }
            )
            assert passed

            action.A_pp.mult(vectors["App_port"], vectors["App_value"])
            action.A_pi.mult(
                vectors["Api_interior"], vectors["Api_value"]
            )
            vectors["App_value"].axpy(1.0, vectors["Api_value"])
            block_action = action._replicated_values(vectors["App_value"])
            difference = block_action - endpoint_action[:, column]
            action_norm = float(np.linalg.norm(endpoint_action[:, column]))
            block_norm = float(np.linalg.norm(block_action))
            difference_norm = float(np.linalg.norm(difference))
            finite = bool(
                np.all(np.isfinite(block_action))
                and np.all(np.isfinite(difference))
                and all(
                    np.isfinite(value)
                    for value in (action_norm, block_norm, difference_norm)
                )
            )
            assert finite
            scale = max(action_norm, block_norm)
            relative = difference_norm / scale if scale > 0.0 else None
            branch = (
                "relative_to_endpoint_action_norm"
                if relative is not None
                else "absolute_zero_action"
            )
            passed = bool(
                relative <= tolerance
                if relative is not None
                else difference_norm <= tolerance
            )
            block_checks.append(
                {
                    "column": column,
                    "equation": "A_pp*u_p + A_pi*u_i",
                    "endpoint_action_norm": action_norm,
                    "block_action_norm": block_norm,
                    "difference_norm": difference_norm,
                    "relative_difference": relative,
                    "normalization_branch": branch,
                    "limit": tolerance,
                    "finite": finite,
                    "pass": passed,
                }
            )
            assert passed
    finally:
        for vector in reversed(tuple(vectors.values())):
            vector.destroy()

    nz, p = int(mesh_cells_z), 6
    xy_periodic_dofs = 2 * (2 * p) ** 2 * (nz * p + 1) + (2 * p) ** 2 * nz * p
    cell_interior_dofs = 4 * nz * 3 * p * (p - 1) ** 2
    active_row_estimate = xy_periodic_dofs - cell_interior_dofs
    recheck_rhs_solves = int(ports.shape[1]) if action_values is None else 0
    recheck_matmult_calls = 3 if action_values is None else 0
    return {
        "audit": {
            "factor_constructions": 1,
            "recovery_rhs_backsolves": int(ports.shape[1]),
            "action_recheck_rhs_backsolves": recheck_rhs_solves,
            "extra_diagnostic_rhs_backsolves": int(ports.shape[1])
            + recheck_rhs_solves,
            "action_values_source": action_values_source,
            "diagnostic_sparse_matmult_calls": 5 * int(ports.shape[1]),
            "action_recheck_sparse_matmult_calls": recheck_matmult_calls,
            "total_audit_sparse_matmult_calls": 5 * int(ports.shape[1])
            + recheck_matmult_calls,
            "static_matrix_row_estimate": {
                "p": p,
                "basis": "xy-Floquet p6 H(curl) DOFs minus cell interiors",
                "mesh_cells": 4 * nz,
                "xy_floquet_full_dofs": int(xy_periodic_dofs),
                "cell_interior_dofs_removed": int(cell_interior_dofs),
                "active_trace_rows": int(active_row_estimate),
                "endpoint_port_rows_estimate": 576,
                "endpoint_partition_interior_rows": int(
                    active_row_estimate - 576
                ),
            },
            "runtime_matrix_rows": {
                "active_trace_rows": int(action.A_pp.getSize()[0])
                + int(action.A_ii.getSize()[0]),
                "port_rows": int(action.port_rows),
                "interior_rows": int(action.interior_rows),
                "interior_matrix_nnz": int(action.interior_matrix_nnz),
            },
            "inner_equation_residuals": equations,
            "endpoint_block_consistency": block_checks,
        },
        "endpoint_action": endpoint_action,
    }


def test_proposed_local10_global20_formula_reports_direct_l20_29_response(
    tmp_path,
) -> None:
    """Report a test-only local10/global20 formula against direct L20 FE.

    The material and incident Bloch wavevector come from the registered
    0.7 nm pilot, while each test segment extends W over the full x/y period
    to form a homogeneous-W subproblem with an analytic continuum plane-wave
    beta and an FE-interpolated trace.  It is not the patterned pilot
    cross-section or its selected QEP modes; coarse transverse interpolation
    and numerical dispersion may also contribute to a response difference.
    Both operators receive the same two endpoint columns after canonical
    coordinate transfer.  The direct endpoint Schur response is compared
    with the four test-only local traction blocks; the comparison has no
    model-equivalence threshold.  A pass means only that the diagnostic
    comparison is finite, its endpoint maps close, and each linear interior
    elimination meets the existing 5e-9 linear accuracy check.  It does not
    isolate the local10 model error, exclude transverse discretization error,
    or qualify a pilot/QEP mode or a Hybrid run.
    """
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        pytest.skip("proposed_formula_test_only comparison is serial-scoped")

    pilot_path = (
        Path(__file__).resolve().parents[2]
        / "input/official/task041/side_balh/"
        "w0p7nm_p6h0p70_m400_mpi8_cell_condensed_pilot.dat"
    )
    pilot_spec = load_and_resolve(pilot_path)
    pilot_cfg = simulation_config_3d_from_normalized(pilot_spec.as_jsonable())
    assert pilot_cfg.lambda0 == pytest.approx(0.7)
    assert pilot_cfg.nedelec_trace_degree_resolved == 6
    assert pilot_cfg.period_x == pytest.approx(10.0)
    assert pilot_cfg.period_y == pytest.approx(5.0)
    assert pilot_cfg.grating_width_x == pytest.approx(3.4)
    assert pilot_cfg.grating_width_y == pytest.approx(5.0)
    assert pilot_cfg.n_grating == complex(
        0.9995903781323069, 0.00012887909720587614
    )

    def segment_config(label: str, z0: float, z1: float, nz: int):
        return _task037c_probe_segment_config(pilot_cfg, label, z0, z1, nz)

    destroy_box = _task037c_destroy_probe_box
    build_box = _task037c_build_probe_box
    endpoint_trace = _task037c_probe_endpoint_trace

    def local_four_blocks(box, left_trace, right_trace, lam10, mu10):
        positive_flux = apply_directional_endpoint_columns(
            box["action"],
            left_trace[:, None],
            right_trace[:, None],
            multipliers=(lam10,),
        )
        negative_flux = apply_directional_endpoint_columns(
            box["action"],
            mu10 * left_trace[:, None],
            right_trace[:, None],
            multipliers=(1.0 + 0.0j,),
        )
        zero = np.zeros_like(positive_flux)
        return split_exact_local_amplitude_blocks(
            np.column_stack((positive_flux[:, 0], zero[:, 0])),
            np.column_stack((zero[:, 0], negative_flux[:, 0])),
            left_rows=len(box["rows"].left_active),
            right_rows=len(box["rows"].right_active),
            forward_factors=(lam10, 1.0 + 0.0j),
            backward_factors=(1.0 + 0.0j, mu10),
        )

    elimination_audit = _task037c_probe_elimination_audit

    local_cell = reference = None
    try:
        local_cfg = segment_config("homogeneous_W_local_L10", 2.0, 12.0, 1)
        reference_cfg = segment_config("direct_L20_Nz29", 2.0, 22.0, 29)
        assert local_cfg.mesh_axis_cell_counts == (2, 2, 1)
        assert reference_cfg.mesh_axis_cell_counts == (2, 2, 29)
        local_cell = build_box(local_cfg, tmp_path / "local_L10")
        reference = build_box(
            reference_cfg,
            tmp_path / "direct_L20_Nz29",
        )

        cross_section = build_matching_cross_section(local_cfg, "stage4_xy", comm=comm)
        spaces = build_cross_section_spaces(cross_section, transverse_degree=6)
        probe_trace = fem.Function(spaces.transverse)
        probe_trace.interpolate(
            lambda x: np.vstack(
                (
                    np.zeros(x.shape[1], dtype=np.complex128),
                    np.exp(1j * (pilot_cfg.kx * x[0] + pilot_cfg.ky * x[1])),
                )
            )
        )
        probe_trace.x.scatter_forward()
        lifters = {
            "local": EndpointModeLifter(
                local_cell["space"], max(pilot_cfg.period_x, pilot_cfg.period_y)
            ),
            "reference": EndpointModeLifter(
                reference["space"], max(pilot_cfg.period_x, pilot_cfg.period_y)
            ),
        }
        local_left, local_right = endpoint_trace(
            local_cell, lifters["local"], probe_trace
        )
        reference_left, reference_right = endpoint_trace(
            reference, lifters["reference"], probe_trace
        )

        # The canonical endpoint map aligns the same transverse x/y entities
        # at z=2 and z=22; the local cell's z=12 interior endpoint is not
        # mistaken for either full-interval boundary.  Primal uses T; the
        # traction transfer below uses the existing dual T^{-H} operation.
        trace_maps = (
            (local_cell, "left", local_left, reference, "left", reference_left),
            (local_cell, "right", local_right, reference, "right", reference_right),
        )
        trace_map_audits = []
        for source_box, source_end, values, target_box, target_end, target in trace_maps:
            transferred, _ = transfer_congruent_endpoint_columns(
                values[:, None],
                source_box["space"],
                source_box["condensed"],
                source_box["floquet"],
                getattr(source_box["rows"], f"{source_end}_active"),
                target_box["space"],
                target_box["condensed"],
                target_box["floquet"],
                getattr(target_box["rows"], f"{target_end}_active"),
                source_endpoint=source_end,
                target_endpoint=target_end,
            )
            trace_map_audits.append(
                {
                    "scenario": f"{source_end}_to_{target_end}",
                    "identity": require_congruent_trace_identity(
                        transferred,
                        target[:, None],
                        side="bottom" if source_end == "left" else "top",
                    ),
                }
            )

        beta_squared = (
            (pilot_cfg.k0 * pilot_cfg.grating_index) ** 2
            - pilot_cfg.kx**2
            - pilot_cfg.ky**2
        )
        beta_forward = complex(np.sqrt(complex(beta_squared)))
        if beta_forward.imag < 0.0 or (
            abs(beta_forward.imag) <= 1.0e-14 and beta_forward.real < 0.0
        ):
            beta_forward = -beta_forward
        probe_modes = (
            SimpleNamespace(
                beta=beta_forward,
                direction="forward",
                passive_branch_valid=True,
            ),
            SimpleNamespace(
                beta=-beta_forward,
                direction="backward",
                passive_branch_valid=True,
            ),
        )
        local_propagation = build_two_sided_propagation(
            probe_modes,
            10.0,
            propagation_model="full3d_uniform_cg",
            axial_fem_degree=6,
            axial_h_nm=10.0,
        )
        full_propagation = build_two_sided_propagation(
            probe_modes,
            20.0,
            propagation_model="full3d_uniform_cg",
            axial_fem_degree=6,
            axial_h_nm=20.0 / 29.0,
        )
        lam10 = local_propagation.forward.factors[0]
        mu10 = local_propagation.backward.factors[0]
        lam20 = full_propagation.forward.factors[0]
        mu20 = full_propagation.backward.factors[0]

        local_columns = np.column_stack(
            (
                assemble_directional_endpoint_columns(
                    local_left[:, None],
                    local_right[:, None],
                    multipliers=(lam20,),
                )[:, 0],
                assemble_directional_endpoint_columns(
                    mu20 * local_left[:, None],
                    local_right[:, None],
                    multipliers=(1.0 + 0.0j,),
                )[:, 0],
            )
        )
        local_left_inputs = local_columns[: len(local_cell["rows"].left_active), :]
        local_right_inputs = local_columns[len(local_cell["rows"].left_active) :, :]
        reference_left_inputs, _ = transfer_congruent_endpoint_columns(
            local_left_inputs,
            local_cell["space"],
            local_cell["condensed"],
            local_cell["floquet"],
            local_cell["rows"].left_active,
            reference["space"],
            reference["condensed"],
            reference["floquet"],
            reference["rows"].left_active,
            source_endpoint="left",
            target_endpoint="left",
        )
        reference_right_inputs, _ = transfer_congruent_endpoint_columns(
            local_right_inputs,
            local_cell["space"],
            local_cell["condensed"],
            local_cell["floquet"],
            local_cell["rows"].right_active,
            reference["space"],
            reference["condensed"],
            reference["floquet"],
            reference["rows"].right_active,
            source_endpoint="right",
            target_endpoint="right",
        )
        reference_columns = np.vstack(
            (reference_left_inputs, reference_right_inputs)
        )
        reference_expected_columns = np.column_stack(
            (
                assemble_directional_endpoint_columns(
                    reference_left[:, None],
                    reference_right[:, None],
                    multipliers=(lam20,),
                )[:, 0],
                assemble_directional_endpoint_columns(
                    mu20 * reference_left[:, None],
                    reference_right[:, None],
                    multipliers=(1.0 + 0.0j,),
                )[:, 0],
            )
        )
        common_input_audits = (
            require_congruent_trace_identity(
                reference_left_inputs,
                reference_expected_columns[: len(reference["rows"].left_active), :],
                side="bottom",
            ),
            require_congruent_trace_identity(
                reference_right_inputs,
                reference_expected_columns[
                    len(reference["rows"].left_active) :, :
                ],
                side="top",
            ),
        )
        probe_trace_norm = float(np.linalg.norm(np.concatenate((local_left, local_right))))
        assert np.isfinite(probe_trace_norm)
        assert probe_trace_norm > 0.0
        local_input_norm = float(np.linalg.norm(local_columns))
        reference_input_norm = float(np.linalg.norm(reference_columns))
        local_column_norms = np.linalg.norm(local_columns, axis=0)
        reference_column_norms = np.linalg.norm(reference_columns, axis=0)
        assert np.isfinite(local_input_norm) and local_input_norm > 0.0
        assert np.isfinite(reference_input_norm) and reference_input_norm > 0.0
        assert np.all(np.isfinite(local_column_norms)) and np.all(local_column_norms > 0.0)
        assert np.all(np.isfinite(reference_column_norms)) and np.all(reference_column_norms > 0.0)

        local_cell["action"] = build_one_cell_two_port_schur_action(
            local_cell["condensed"].matrix,
            local_cell["rows"],
        )
        local_blocks = local_four_blocks(
            local_cell, local_left, local_right, lam10, mu10
        )
        local_elimination_result = elimination_audit(
            local_cell["action"],
            local_columns,
            mesh_cells_z=1,
        )
        local_elimination = local_elimination_result["audit"]
        local_action_flux = local_elimination_result["endpoint_action"]
        local_cell["action"].destroy()
        local_cell["action"] = None

        reference["action"] = build_one_cell_two_port_schur_action(
            reference["condensed"].matrix,
            reference["rows"],
        )
        direct_flux = reference["action"].apply_columns(reference_columns)
        reference_elimination = elimination_audit(
            reference["action"],
            reference_columns,
            mesh_cells_z=29,
            action_values=direct_flux,
        )["audit"]

        # Proposed test-only composition of the four local traction blocks:
        # F_bottom = B_bottom^+ + mu20 * B_bottom^-; F_top = lam20 * B_top^+ + B_top^-.
        proposed_bottom_local = np.column_stack(
            (
                local_blocks["bottom_forward"][:, 0],
                mu20 * local_blocks["bottom_backward"][:, 1],
            )
        )
        proposed_top_local = np.column_stack(
            (
                lam20 * local_blocks["top_forward"][:, 0],
                local_blocks["top_backward"][:, 1],
            )
        )
        proposed_bottom, bottom_dual_audit = (
            transfer_congruent_endpoint_dual_columns(
                proposed_bottom_local,
                local_cell["space"],
                local_cell["condensed"],
                local_cell["floquet"],
                local_cell["rows"].left_active,
                reference["space"],
                reference["condensed"],
                reference["floquet"],
                reference["rows"].left_active,
                source_endpoint="left",
                target_endpoint="left",
            )
        )
        proposed_top, top_dual_audit = transfer_congruent_endpoint_dual_columns(
            proposed_top_local,
            local_cell["space"],
            local_cell["condensed"],
            local_cell["floquet"],
            local_cell["rows"].right_active,
            reference["space"],
            reference["condensed"],
            reference["floquet"],
            reference["rows"].right_active,
            source_endpoint="right",
            target_endpoint="right",
        )
        assert bottom_dual_audit["bijection"] is True
        assert top_dual_audit["bijection"] is True
        proposed_flux = np.vstack((proposed_bottom, proposed_top))
        assert proposed_flux.shape == direct_flux.shape
        assert np.all(np.isfinite(proposed_flux))
        assert np.all(np.isfinite(direct_flux))
        proposed_column_norms = np.linalg.norm(proposed_flux, axis=0)
        direct_column_norms = np.linalg.norm(direct_flux, axis=0)
        assert np.all(np.isfinite(proposed_column_norms))
        assert np.all(np.isfinite(direct_column_norms))
        assert np.all(proposed_column_norms > 0.0)
        assert np.all(direct_column_norms > 0.0)

        absolute_l2 = float(np.linalg.norm(proposed_flux - direct_flux))
        proposed_norm = float(np.linalg.norm(proposed_flux))
        direct_norm = float(np.linalg.norm(direct_flux))
        assert np.isfinite(proposed_norm)
        assert np.isfinite(direct_norm)
        scale = max(proposed_norm, direct_norm)
        relative_l2 = absolute_l2 / scale if scale > 0.0 else None
        assert np.isfinite(absolute_l2)
        if relative_l2 is not None:
            assert np.isfinite(relative_l2)
        assert all(
            audit["identity"]["pass"] is True for audit in trace_map_audits
        )
        assert all(audit["pass"] is True for audit in common_input_audits)
        assert local_elimination["factor_constructions"] == 1
        assert reference_elimination["factor_constructions"] == 1
        local_action_norm = float(np.linalg.norm(local_action_flux))
        assert np.isfinite(local_action_norm) and local_action_norm > 0.0
        assert direct_norm > 0.0
        assert proposed_norm > 0.0
        assert scale > 0.0
        assert relative_l2 is not None
        diagnostic_rhs_backsolves = (
            local_elimination["extra_diagnostic_rhs_backsolves"]
            + reference_elimination["extra_diagnostic_rhs_backsolves"]
        )
        assert diagnostic_rhs_backsolves == 6
        report = {
            "scenario": "proposed_formula_test_only",
            "comparison": "direct_L20_Nz29_p6_vs_local_L10_p6_formula",
            "probe": {
                "beta_source": "continuum homogeneous-W dispersion",
                "trace_source": "continuum plane wave interpolated in p6 FE space",
                "selected_qep_mode": False,
                "transverse_interpolation_or_dispersion_may_contribute": True,
                "beta_real": float(beta_forward.real),
                "beta_imag": float(beta_forward.imag),
                "trace_norm": probe_trace_norm,
                "local_two_column_input_norm": local_input_norm,
                "reference_two_column_input_norm": reference_input_norm,
            },
            "endpoint_identity": {
                "raw_maps": trace_map_audits,
                "same_two_input_columns": list(common_input_audits),
            },
            "elimination": {
                "equation": "A_ii*u_i + A_ip*u_p",
                "norm_reference": "norm(A_ip*u_p)",
                "limit": 5.0e-9,
                "model_equivalence_gate": None,
                "local_L10": local_elimination,
                "direct_L20_Nz29": reference_elimination,
            },
            "factor_work": {
                "factor_constructions": {"local_L10": 1, "direct_L20_Nz29": 1},
                "added_backsolve_rhs": {
                    "local_action_plus_recovery": local_elimination[
                        "extra_diagnostic_rhs_backsolves"
                    ],
                    "direct_recovery": reference_elimination[
                        "extra_diagnostic_rhs_backsolves"
                    ],
                    "total": diagnostic_rhs_backsolves,
                },
                "added_sparse_matmult": {
                    "local_L10": local_elimination[
                        "diagnostic_sparse_matmult_calls"
                    ],
                    "direct_L20_Nz29": reference_elimination[
                        "diagnostic_sparse_matmult_calls"
                    ],
                    "total": 20,
                },
                "all_backsolve_rhs": {
                    "local_L10": 6,
                    "direct_L20_Nz29": 4,
                    "total": 10,
                },
                "factor_release_order": "local before direct reference",
            },
            "model_response_difference_no_threshold": {
                "absolute_l2": absolute_l2,
                "relative_l2": relative_l2,
                "direct_norm": direct_norm,
                "proposed_norm": proposed_norm,
                "threshold": None,
            },
            "rows": {
                "static_estimate": {
                    "local_L10": local_elimination["static_matrix_row_estimate"],
                    "direct_L20_Nz29": reference_elimination[
                        "static_matrix_row_estimate"
                    ],
                },
                "runtime_to_be_measured": {
                    "local_L10": local_elimination["runtime_matrix_rows"],
                    "direct_L20_Nz29": reference_elimination["runtime_matrix_rows"],
                },
            },
            "dual_entity_blocks": [
                int(bottom_dual_audit["entity_block_count"]),
                int(top_dual_audit["entity_block_count"]),
            ],
        }
        print(
            "proposed_formula_test_only_json="
            + json.dumps(report, sort_keys=True, allow_nan=False)
        )
    finally:
        for box in (local_cell, reference):
            if box is not None:
                destroy_box(box)


def test_proposed_normal_incidence_homogeneous_w_matched_h_stitch_control(
    tmp_path,
) -> None:
    """Compare two one-cell formulas with one direct normal-incidence L20 FE action.

    This is a homogeneous-W, q=0 diagnostic, not the grazing-incidence pilot
    or a selected QEP mode.  The matched h=20/29 local cell checks whether the
    existing four-block formula stitches one repeated axial FE cell correctly;
    the historical h=10 cell is reported without a model-equivalence gate.
    """
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("normal-incidence local-cell stitch diagnostic supports MPI1/2")
    shared_root = Path(
        comm.bcast(str(tmp_path / "normal_incidence_control_shared"), root=0)
    )
    if comm.rank == 0:
        shared_root.mkdir(parents=True, exist_ok=True)
    comm.Barrier()

    pilot_path = (
        Path(__file__).resolve().parents[2]
        / "input/official/task041/side_balh/"
        "w0p7nm_p6h0p70_m400_mpi8_cell_condensed_pilot.dat"
    )
    pilot_spec = load_and_resolve(pilot_path)
    pilot_cfg = simulation_config_3d_from_normalized(pilot_spec.as_jsonable())
    cfg = replace(pilot_cfg, incident_theta_deg=0.0, incident_phi_deg=0.0)
    assert cfg.incident_theta_deg == 0.0 and cfg.incident_phi_deg == 0.0
    assert cfg.kx == 0.0j and cfg.ky == 0.0j
    assert complex(cfg.mu_r) == 1.0 + 0.0j
    assert cfg.nedelec_trace_degree_resolved == 6

    length_nm = 20.0
    global_h_nm = length_nm / 29.0
    z_bottom_nm, z_top_nm = 2.0, 22.0

    def segment_config(label: str, z0: float, z1: float, nz: int):
        return _task037c_probe_segment_config(
            cfg,
            label,
            z0,
            z1,
            nz,
            case_prefix="normal_incidence_control_only",
        )

    destroy_box = _task037c_destroy_probe_box
    build_box = _task037c_build_probe_box
    endpoint_trace = _task037c_probe_endpoint_trace
    elimination_audit = _task037c_probe_elimination_audit

    beta = complex(cfg.k0 * cfg.grating_index)
    modes = (
        SimpleNamespace(beta=beta, direction="forward", passive_branch_valid=True),
        SimpleNamespace(beta=-beta, direction="backward", passive_branch_valid=True),
    )
    global_propagation = build_two_sided_propagation(
        modes,
        length_nm,
        propagation_model="full3d_uniform_cg",
        axial_fem_degree=6,
        axial_h_nm=global_h_nm,
    )
    lambda_global = complex(global_propagation.forward.factors[0])
    mu_global = complex(global_propagation.backward.factors[0])

    reference_cfg = segment_config(
        "direct_L20_Nz29", z_bottom_nm, z_top_nm, 29
    )
    reference = None
    factor_counts = {"constructions": 0, "live": 0, "maximum_live": 0}

    def build_action(box):
        box["action"] = build_one_cell_two_port_schur_action(
            box["condensed"].matrix, box["rows"]
        )
        factor_counts["constructions"] += 1
        factor_counts["live"] += 1
        factor_counts["maximum_live"] = max(
            factor_counts["maximum_live"], factor_counts["live"]
        )

    def destroy_counted_box(box) -> None:
        was_live = box is not None and box.get("action") is not None
        if box is not None:
            destroy_box(box)
        if was_live:
            factor_counts["live"] -= 1

    observations = []
    probe_trace_before = None
    reference_audit = None
    trace_norm = None
    matched_response_pass = None
    try:
        reference = build_box(reference_cfg, shared_root / "normal_reference_L20")
        build_action(reference)
        cross_section = build_matching_cross_section(
            reference_cfg, "stage4_xy", comm=comm
        )
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=6
        )
        probe_trace = fem.Function(spaces.transverse)
        probe_trace.interpolate(
            lambda x: np.vstack(
                (
                    np.zeros(x.shape[1], dtype=np.complex128),
                    np.ones(x.shape[1], dtype=np.complex128),
                )
            )
        )
        probe_trace.x.scatter_forward()
        probe_trace_before = probe_trace.x.array.copy()
        ref_lifter = EndpointModeLifter(
            reference["space"], max(cfg.period_x, cfg.period_y)
        )
        reference_left, reference_right = endpoint_trace(
            reference, ref_lifter, probe_trace
        )
        trace_norm = float(
            np.linalg.norm(np.concatenate((reference_left, reference_right)))
        )
        assert np.isfinite(trace_norm) and trace_norm > 0.0

        reference_forward = assemble_directional_endpoint_columns(
            reference_left[:, None],
            reference_right[:, None],
            multipliers=(lambda_global,),
        )
        reference_backward = assemble_directional_endpoint_columns(
            mu_global * reference_left[:, None],
            reference_right[:, None],
            multipliers=(1.0 + 0.0j,),
        )
        reference_columns = np.column_stack(
            (reference_forward[:, 0], reference_backward[:, 0])
        )
        direct_flux = reference["action"].apply_columns(reference_columns)
        reference_audit_result = elimination_audit(
            reference["action"],
            reference_columns,
            mesh_cells_z=29,
            action_values=direct_flux,
        )
        reference_audit = reference_audit_result["audit"]
        assert np.all(np.isfinite(direct_flux))
        direct_norm = float(np.linalg.norm(direct_flux))
        assert np.isfinite(direct_norm) and direct_norm > 0.0

        for label, local_h_nm in (
            ("historical_local10_h10", 10.0),
            ("matched_axial_h20_over_29", global_h_nm),
        ):
            local_box = None
            try:
                local_cfg = segment_config(
                    label, z_bottom_nm, z_bottom_nm + local_h_nm, 1
                )
                local_box = build_box(
                    local_cfg, shared_root / f"normal_{label}"
                )
                build_action(local_box)
                local_lifter = EndpointModeLifter(
                    local_box["space"], max(cfg.period_x, cfg.period_y)
                )
                local_left, local_right = endpoint_trace(
                    local_box, local_lifter, probe_trace
                )
                identity_checks = []
                for endpoint, local_values, reference_values in (
                    ("left", local_left, reference_left),
                    ("right", local_right, reference_right),
                ):
                    local_rows = getattr(local_box["rows"], f"{endpoint}_active")
                    reference_rows = getattr(
                        reference["rows"], f"{endpoint}_active"
                    )
                    transferred, _ = transfer_congruent_endpoint_columns(
                        local_values[:, None],
                        local_box["space"],
                        local_box["condensed"],
                        local_box["floquet"],
                        local_rows,
                        reference["space"],
                        reference["condensed"],
                        reference["floquet"],
                        reference_rows,
                        source_endpoint=endpoint,
                        target_endpoint=endpoint,
                    )
                    identity = require_congruent_trace_identity(
                        transferred,
                        reference_values[:, None],
                        side="bottom" if endpoint == "left" else "top",
                    )
                    identity_checks.append(identity)
                    assert identity["pass"] is True

                local_propagation = build_two_sided_propagation(
                    modes,
                    local_h_nm,
                    propagation_model="full3d_uniform_cg",
                    axial_fem_degree=6,
                    axial_h_nm=local_h_nm,
                )
                lambda_h = complex(local_propagation.forward.factors[0])
                mu_h = complex(local_propagation.backward.factors[0])
                forward_flux = apply_directional_endpoint_columns(
                    local_box["action"],
                    local_left[:, None],
                    local_right[:, None],
                    multipliers=(lambda_h,),
                )
                backward_flux = apply_directional_endpoint_columns(
                    local_box["action"],
                    mu_h * local_left[:, None],
                    local_right[:, None],
                    multipliers=(1.0 + 0.0j,),
                )
                local_forward = assemble_directional_endpoint_columns(
                    local_left[:, None],
                    local_right[:, None],
                    multipliers=(lambda_h,),
                )
                local_backward = assemble_directional_endpoint_columns(
                    mu_h * local_left[:, None],
                    local_right[:, None],
                    multipliers=(1.0 + 0.0j,),
                )
                local_columns = np.column_stack(
                    (local_forward[:, 0], local_backward[:, 0])
                )
                local_action_values = np.column_stack(
                    (forward_flux[:, 0], backward_flux[:, 0])
                )
                local_columns_norm = float(np.linalg.norm(local_columns))
                local_action_norm = float(np.linalg.norm(local_action_values))
                assert np.isfinite(local_columns_norm) and local_columns_norm > 0.0
                assert np.isfinite(local_action_norm) and local_action_norm > 0.0
                local_audit_result = elimination_audit(
                    local_box["action"],
                    local_columns,
                    mesh_cells_z=1,
                    action_values=local_action_values,
                )
                local_audit = local_audit_result["audit"]

                zero = np.zeros_like(forward_flux)
                blocks = split_exact_local_amplitude_blocks(
                    np.column_stack((forward_flux[:, 0], zero[:, 0])),
                    np.column_stack((zero[:, 0], backward_flux[:, 0])),
                    left_rows=len(local_box["rows"].left_active),
                    right_rows=len(local_box["rows"].right_active),
                    forward_factors=(lambda_h, 1.0 + 0.0j),
                    backward_factors=(1.0 + 0.0j, mu_h),
                )
                bottom_local = np.column_stack(
                    (
                        blocks["bottom_forward"][:, 0],
                        mu_global * blocks["bottom_backward"][:, 1],
                    )
                )
                top_local = np.column_stack(
                    (
                        lambda_global * blocks["top_forward"][:, 0],
                        blocks["top_backward"][:, 1],
                    )
                )
                bottom_global, bottom_map = (
                    transfer_congruent_endpoint_dual_columns(
                        bottom_local,
                        local_box["space"],
                        local_box["condensed"],
                        local_box["floquet"],
                        local_box["rows"].left_active,
                        reference["space"],
                        reference["condensed"],
                        reference["floquet"],
                        reference["rows"].left_active,
                        source_endpoint="left",
                        target_endpoint="left",
                    )
                )
                top_global, top_map = transfer_congruent_endpoint_dual_columns(
                    top_local,
                    local_box["space"],
                    local_box["condensed"],
                    local_box["floquet"],
                    local_box["rows"].right_active,
                    reference["space"],
                    reference["condensed"],
                    reference["floquet"],
                    reference["rows"].right_active,
                    source_endpoint="right",
                    target_endpoint="right",
                )
                assert bottom_map["bijection"] is True
                assert top_map["bijection"] is True
                proposed_flux = np.vstack((bottom_global, top_global))
                assert proposed_flux.shape == direct_flux.shape
                assert np.all(np.isfinite(proposed_flux))
                proposed_norm = float(np.linalg.norm(proposed_flux))
                absolute_difference = float(
                    np.linalg.norm(proposed_flux - direct_flux)
                )
                scale = max(proposed_norm, direct_norm)
                assert all(
                    np.isfinite(value)
                    for value in (proposed_norm, absolute_difference, scale)
                )
                assert proposed_norm > 0.0 and direct_norm > 0.0 and scale > 0.0
                relative_difference = absolute_difference / scale
                matched = label == "matched_axial_h20_over_29"
                response_pass = (
                    bool(relative_difference <= 5.0e-9) if matched else None
                )
                if matched:
                    matched_response_pass = response_pass
                observations.append(
                    {
                        "local_case": label,
                        "local_length_nm": float(local_h_nm),
                        "local_axial_h_nm": float(local_h_nm),
                        "local_interval_nm": [
                            z_bottom_nm,
                            z_bottom_nm + float(local_h_nm),
                        ],
                        "local_lambda_h": [lambda_h.real, lambda_h.imag],
                        "local_mu_h": [mu_h.real, mu_h.imag],
                        "global_lambda_L20": [
                            lambda_global.real,
                            lambda_global.imag,
                        ],
                        "global_mu_L20": [mu_global.real, mu_global.imag],
                        "endpoint_trace_identity": identity_checks,
                        "dual_transfer_bijection": [
                            bottom_map["bijection"],
                            top_map["bijection"],
                        ],
                        "local_elimination_audit": local_audit,
                        "proposed_flux_norm": proposed_norm,
                        "direct_reference_flux_norm": direct_norm,
                        "response_difference_absolute_l2": absolute_difference,
                        "response_difference_relative_l2": relative_difference,
                        "response_equivalence_limit": 5.0e-9 if matched else None,
                        "response_equivalence_pass": response_pass,
                    }
                )
            finally:
                if local_box is not None:
                    destroy_counted_box(local_box)

        np.testing.assert_array_equal(probe_trace.x.array, probe_trace_before)
    finally:
        if reference is not None:
            destroy_counted_box(reference)

    assert factor_counts["constructions"] == 3
    assert factor_counts["live"] == 0
    assert factor_counts["maximum_live"] == 2
    assert len(observations) == 2
    assert reference_audit is not None
    report = {
        "scenario": "normal_incidence_homogeneous_W_diagnostic",
        "mpi_size": int(comm.size),
        "qep_mode_selected": False,
        "input_dat_modified": False,
        "incidence": {
            "incident_theta_deg": cfg.incident_theta_deg,
            "incident_phi_deg": cfg.incident_phi_deg,
            "kx": [cfg.kx.real, cfg.kx.imag],
            "ky": [cfg.ky.real, cfg.ky.imag],
            "probe": "nonzero constant tangential Ey in the p6 FE trace space",
        },
        "material": {
            "source": "registered W pilot material, reused in this homogeneous diagnostic",
            "n": [cfg.grating_index.real, cfg.grating_index.imag],
            "mu_r": [complex(cfg.mu_r).real, complex(cfg.mu_r).imag],
            "beta_continuum_per_nm": [beta.real, beta.imag],
            "beta_definition": "exactly k0*n, with mu_r=1",
        },
        "discretization": {
            "transverse_cells": [2, 2],
            "nedelec_trace_degree": 6,
            "reference_global_interval_nm": [z_bottom_nm, z_top_nm],
            "reference_global_length_nm": length_nm,
            "reference_axial_cells": 29,
            "reference_axial_h_nm": global_h_nm,
            "reference_endpoint_trace_norm": trace_norm,
            "reference_elimination_audit": reference_audit,
            "endpoint_mapping_scope": (
                "left/right transverse x-y trace rows are coordinate-congruent; "
                "the representative local z interval is separately recorded "
                "and is not the full reference z interval"
            ),
        },
        "linear_accuracy_and_stitching": {
            "internal_and_endpoint_equation_limit": 5.0e-9,
            "matched_h_control_is_same_axial_discretization_chain_stitch_check": True,
            "historical_h10_response_has_no_equivalence_threshold": True,
            "cases": observations,
        },
        "factor_and_operation_counts": {
            "basis": "explicit OneCellTwoPortSchurAction call-path accounting; not independently instrumented runtime counters",
            "factor_construction_calls": factor_counts["constructions"],
            "maximum_simultaneously_live_factors": factor_counts["maximum_live"],
            "simultaneous_factor_scope": (
                "one direct L20 action and at most one local one-cell action; "
                "other assembly/storage objects are not included in this factor count"
            ),
            "local_factor_lifecycle": (
                "each local action is destroyed before constructing the next; "
                "the single direct reference action remains live"
            ),
            "factor_cleanup_complete": factor_counts["live"] == 0,
            "factor_rhs_solves": {
                "per_local_case": 4,
                "reference": 4,
                "all_three_systems": 12,
                "basis": "two one-column traction apply matSolves plus two audit recovery solves per local; one two-column reference apply plus two audit recovery solves",
            },
            "sparse_matrix_products": {
                "per_local_case": 16,
                "reference": 13,
                "all_three_systems": 45,
                "basis": "3 products per action.apply_columns call, one A_ip.mult per recovery column, and four explicit Aip/Aii/App/Api matvecs per audited column; local audit reuses the two traction outputs",
                "scope": "static PETSc sparse product call count, excluding assembly and communication",
            },
            "rows_and_nnz": {
                "reference": reference_audit["runtime_matrix_rows"],
                "locals": [
                    case["local_elimination_audit"]["runtime_matrix_rows"]
                    for case in observations
                ],
            },
        },
        "scope_boundary": [
            "This compares homogeneous-W normal-incidence FE responses and does not use a selected discrete QEP mode.",
            "A matched-h pass is only an algebraic stitch check for the repeated axial FE cell, not pilot qualification.",
            "The h10 response difference has no pass threshold and is not attributable solely to local-cell length.",
            "No production guard, input, packet, QEP, or FE workflow is modified or qualified by this diagnostic test.",
        ],
    }
    if comm.rank == 0:
        print(
            "normal_incidence_control_test_only_json="
            + json.dumps(report, sort_keys=True, allow_nan=False)
        )
    assert matched_response_pass is True


def test_matched_uniform_axial_cell_strategy_uses_resolved_global_step(
    monkeypatch,
) -> None:
    """Keep the registered W0.7 local exact cell on the global L20/N29 step."""
    from src.coupling import hybrid_internal_modes

    cfg = target_stage4_config(degree=6, h_nm=0.7)
    propagation_calls = []

    def capture_propagation(_modes, length_nm, **kwargs):
        propagation_calls.append(
            (
                float(length_nm),
                float(kwargs["axial_h_nm"]),
                int(kwargs["axial_fem_degree"]),
                kwargs["propagation_model"],
            )
        )
        return SimpleNamespace(
            length_nm=float(length_nm),
            propagation_model=kwargs["propagation_model"],
        )

    monkeypatch.setattr(
        hybrid_internal_modes,
        "build_two_sided_propagation",
        capture_propagation,
    )

    def resolve(cfg_value, strategy, length_nm):
        global_h_nm, cell_count = (
            hybrid_internal_modes._resolve_uniform_middle_propagation(
                length_nm, float(cfg_value.mesh_target_size)
            )
        )
        result = hybrid_internal_modes._build_exact_one_cell_local_propagation(
            (),
            cfg_value,
            strategy=strategy,
            length_nm=length_nm,
            propagation_model="full3d_uniform_cg",
            modal_traction_model="full3d_one_cell_exact_schur",
            global_axial_h_nm=global_h_nm,
            global_axial_cell_count=cell_count,
        )
        return global_h_nm, cell_count, result

    global_h_nm, global_cell_count, matched = resolve(
        cfg, "matched_uniform_axial_cell", 20.0
    )
    assert global_cell_count == 29 and global_h_nm == 20.0 / 29.0
    matched_strategy, matched_h_nm, matched_propagation = matched
    assert matched_strategy == "matched_uniform_axial_cell"
    assert matched_h_nm == global_h_nm
    assert matched_propagation.length_nm == global_h_nm
    assert propagation_calls[-1] == (
        global_h_nm,
        global_h_nm,
        6,
        "full3d_uniform_cg",
    )
    matched_cfg = build_one_cell_config(
        cfg,
        1,
        cell_length_nm=matched_h_nm,
        strategy=matched_strategy,
    )
    matched_plan = stage4_axis_plan(matched_cfg, 1)
    source_plan = stage4_axis_plan(cfg, 1)
    assert matched_cfg.z_min == 0.0
    assert matched_cfg.z_max == global_h_nm
    assert matched_cfg.mesh_axis_z_values == (0.0, global_h_nm)
    assert matched_cfg.mesh_axis_z_profile == (
        "task041_w0p7_matched_uniform_axial_cell"
    )
    assert matched_plan.mesh_cells_resolved[:2] == source_plan.mesh_cells_resolved[:2]
    np.testing.assert_array_equal(matched_plan.x_values, source_plan.x_values)
    np.testing.assert_array_equal(matched_plan.y_values, source_plan.y_values)

    _, _, legacy = resolve(cfg, None, 100.0)
    legacy_strategy, local10_h_nm, _ = legacy
    assert legacy_strategy == "historical_local10_global100"
    assert local10_h_nm == 10.0
    assert propagation_calls[-1] == (10.0, 10.0, 6, "full3d_uniform_cg")
    historical_cfg = build_one_cell_config(cfg, 1)
    assert historical_cfg.z_max == 10.0
    assert historical_cfg.mesh_axis_z_profile == (
        "task037c_x3_uniform_10nm_one_cell"
    )

    with pytest.raises(ValueError, match="100 nm middle interval"):
        resolve(cfg, None, 20.0)
    p4_cfg = target_stage4_config(degree=4, h_nm=0.7)
    with pytest.raises(ValueError, match="registered p6/h0.70"):
        resolve(p4_cfg, "matched_uniform_axial_cell", 20.0)
