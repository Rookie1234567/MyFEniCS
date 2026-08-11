"""Focused contracts and a real three-box H(curl)/Floquet fixture."""

from dataclasses import replace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI

from benchmarks.run_task037c_exact_traction_column_audit import _one_cell_config
from src.coupling.hybrid_one_cell_exact_traction import (
    EXACT_ONE_CELL_TRACTION_MODEL,
    ExactOneCellCoupling,
    congruent_trace_identity,
    embed_exact_trace_columns_dense_reference,
    exact_model_record,
    require_congruent_trace_identity,
    split_exact_local_amplitude_blocks,
)
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
from src.solvers.one_cell_trace_schur import (
    EndpointModeLifter,
    _active_values_for_port,
    build_one_cell_two_port_schur_action,
    identify_endpoint_active_rows,
)


def test_exact_model_is_explicit_and_not_production_qualified() -> None:
    record = exact_model_record(True)
    assert record["model"] == EXACT_ONE_CELL_TRACTION_MODEL
    assert record["research_only"] is True
    assert record["production_qualified"] is False
    assert exact_model_record(False)["model"] == "ordinary_default"


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
        return mesh_data, V, floquet, condensed, rows

    middle = build_box(box_config("middle", 0.0, 10.0), tmp_path / "middle", True)
    bottom = build_box(box_config("bottom", -10.0, 0.0), tmp_path / "bottom", False)
    top = build_box(box_config("top", 10.0, 20.0), tmp_path / "top", False)
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

    def endpoint_values(box, source, endpoint):
        mesh_data, V, floquet, condensed, rows = box
        field = EndpointModeLifter(V, max(base.period_x, base.period_y)).lift(source)
        floquet.mpc.homogenize(field)
        field.x.scatter_forward()
        return _active_values_for_port(field, condensed, getattr(rows, endpoint))

    try:
        middle_pos_left = endpoint_values(middle, positive_like, "left_active")
        middle_pos_right = endpoint_values(middle, positive_like, "right_active")
        bottom_pos_right = endpoint_values(bottom, positive_like, "right_active")
        top_pos_left = endpoint_values(top, positive_like, "left_active")
        middle_neg_left = endpoint_values(middle, raw_negative_like, "left_active")
        middle_neg_right = endpoint_values(middle, raw_negative_like, "right_active")
        bottom_neg_right = endpoint_values(bottom, raw_negative_like, "right_active")
        top_neg_left = endpoint_values(top, raw_negative_like, "left_active")
        audits = {
            "bottom_positive_like": require_congruent_trace_identity(
                middle_pos_left[:, None], bottom_pos_right[:, None], side="bottom"
            ),
            "top_positive_like": require_congruent_trace_identity(
                middle_pos_right[:, None], top_pos_left[:, None], side="top"
            ),
            "bottom_raw_negative_like": require_congruent_trace_identity(
                middle_neg_left[:, None], bottom_neg_right[:, None], side="bottom"
            ),
            "top_raw_negative_like": require_congruent_trace_identity(
                middle_neg_right[:, None], top_neg_left[:, None], side="top"
            ),
        }
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
