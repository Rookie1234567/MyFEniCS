"""Focused contracts and a real three-box H(curl)/Floquet fixture."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI

from benchmarks.run_task037c_exact_traction_column_audit import _one_cell_config
from src.constraints.high_order_floquet_trace import face_coefficient_transform
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
)
from src.coupling.hybrid_one_cell_exact_traction_builder import (
    _one_cell_config as build_one_cell_config,
)
from src.coupling.hybrid_internal_modes import _destroy_pending_exact_overrides
from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_static_field_recovery import _add_internal_tractions
from src.solvers.one_cell_trace_schur import (
    EndpointModeLifter,
    _active_values_for_port,
    build_one_cell_two_port_schur_action,
    identify_endpoint_active_rows,
)
from src.modes.stable_propagation import build_two_sided_propagation


def test_exact_model_is_explicit_and_not_production_qualified() -> None:
    record = exact_model_record(True)
    assert record["model"] == EXACT_ONE_CELL_TRACTION_MODEL
    assert record["research_only"] is True
    assert record["production_qualified"] is False
    assert exact_model_record(False)["model"] == "ordinary_default"


def test_exact_builder_uses_frozen_ten_nm_one_cell_config() -> None:
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    one_cell = build_one_cell_config(cfg)
    assert one_cell.z_min == 0.0
    assert one_cell.z_max == 10.0
    assert one_cell.mesh_axis_cell_counts == (6, 3, 1)
    assert one_cell.mesh_axis_z_values == (0.0, 10.0)
    assert one_cell.mesh_axis_z_profile == "task037c_x3_uniform_10nm_one_cell"


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

    base = _one_cell_config(target_stage4_config(degree=2, h_nm=10.0))
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
