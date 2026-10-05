"""Task40's narrow regression for the Task042 boundary component reuse."""

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from src.solvers.directional_boundary import (
    BoundaryLayout,
    DirectionalBoundaryAction,
    FacetPolynomial,
)
from src.solvers.native_boundary_adapter import (
    NativeBoundaryAdapter,
    independent_trace_port_terms,
)
from src.solvers.task40_w1_local_probe import (
    _direct_full_basis_integral,
    analytic_full_basis_integral,
    direct_single_face_projection,
)
from src.solvers import task40_w1_local_probe
from src.solvers.task40_w1_moment_reference import AnalyticMomentBoundaryReference
from benchmarks import check_task40_w1_boundary_probe as v10_checker
from benchmarks import run_task40_w1_boundary_probe as v10_runner
from benchmarks.check_task40_w1_boundary_probe import (
    _recompute_v10_full_BD_rows,
    _recompute_v10_local_cases,
    _v10_local_algebra_check,
)


def _element():
    import basix.ufl

    return basix.ufl.element("N1curl", "hexahedron", 6).basix_element


def _modes():
    return [
        {
            "side": side,
            "k_vector": [0.2 + 0.13 * j, -0.17 + 0.09 * j, 0.31],
            "reference_plane_nm": 0.0 if side == "bottom" else 2.0,
            "e_vector": [1 + 0.2j, 0.3 - 0.1j, 0],
            "traction_vector": [0.7 - 0.8j, -0.9 + 0.2j, 0],
            "projection_denominator": 1.3 + j,
        }
        for side in ("bottom", "top")
        for j in range(2)
    ]


@pytest.mark.parametrize("q", [30, 60])
def test_directional_action_matches_explicit_complete_facet_sum(q):
    import basix

    polynomial = FacetPolynomial(_element())
    layout = BoundaryLayout(
        [0.0, 0.6, 1.5], [0.0, 0.8, 1.9], polynomial,
        (np.exp(0.3j), np.exp(-0.2j)),
    )
    modes = _modes()
    action = DirectionalBoundaryAction(layout, modes, q)
    trace = np.arange(1, layout.rows + 1, dtype=np.float64).astype(np.complex128)
    direct = np.zeros((len(modes), 2), dtype=np.complex128)
    rule, weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
    for m, mode in enumerate(modes):
        side = mode["side"]
        zeta = 0.0 if side == "bottom" else 1.0
        tab = polynomial.element.tabulate(
            0, np.column_stack((rule, np.full(len(rule), zeta)))
        )[0][:, polynomial.active[side], :2]
        for i in range(layout.nx):
            for j in range(layout.ny):
                dx = layout.x[i + 1] - layout.x[i]
                dy = layout.y[j + 1] - layout.y[j]
                pts = np.column_stack((
                    layout.x[i] + dx * rule[:, 0],
                    layout.y[j] + dy * rule[:, 1],
                    np.full(len(rule), mode["reference_plane_nm"]),
                ))
                basis_integral = np.einsum(
                    "q,qjc->jc",
                    weights * np.exp(-1j * np.conj(pts @ mode["k_vector"])),
                    tab,
                ) * np.array([dy, dx])
                ids = layout.maps[side][i, j]
                local = trace[ids] * layout.weights[side][i, j]
                direct[m] += local @ basis_integral
    np.testing.assert_allclose(action.project_components(trace), direct, rtol=2e-11, atol=2e-11)


def test_q60_generic_complex_and_nonzero_port_inputs_match_independent_panel_rule():
    polynomial = FacetPolynomial(_element())
    layout = BoundaryLayout(
        [0.0, 0.6, 1.5], [0.0, 0.8, 1.9], polynomial,
        (np.exp(0.3j), np.exp(-0.2j)),
    )
    modes = _modes()
    faces = [("top", 0, 0), ("bottom", 0, 0)]
    action = DirectionalBoundaryAction(
        layout, modes, 60, face_inventory=faces
    )
    reference = AnalyticMomentBoundaryReference(
        layout, modes, face_inventory=faces
    )
    index = np.arange(layout.rows, dtype=np.float64)
    trace = np.asarray(
        np.sin(0.37 * (index + 1)) + 0.2 * np.cos(0.11 * index)
        + 1j * (np.cos(0.23 * (index + 1)) - 0.3 * np.sin(0.17 * index)),
        dtype=np.complex128,
    )
    alpha = np.asarray(
        [0.3 + 0.7j, -0.5 + 0.2j, 0.8 - 0.1j, -0.2 - 0.9j],
        dtype=np.complex128,
    )
    components = action.project_components(trace)
    applied = action.apply(trace)
    port_rhs = action.modal_rhs(alpha)
    scattered = action.scatter_components(components)
    reference_components = reference.project_components(trace)
    reference_apply = reference.apply(trace)
    reference_port_rhs = reference.modal_rhs(alpha)
    reference_scattered = reference.scatter_components(components)
    assert np.isfinite(components).all() and np.linalg.norm(components) > 0
    assert np.isfinite(applied).all() and np.linalg.norm(applied) > 0
    assert np.isfinite(port_rhs).all() and np.linalg.norm(port_rhs) > 0
    component_scale = np.linalg.norm(reference_components, axis=1)
    assert np.all(component_scale > 0)
    assert np.max(
        np.linalg.norm(components - reference_components, axis=1) / component_scale
    ) <= 1e-10
    assert np.linalg.norm(applied - reference_apply) / np.linalg.norm(reference_apply) <= 1e-10
    assert np.linalg.norm(port_rhs - reference_port_rhs) / np.linalg.norm(reference_port_rhs) <= 1e-10
    assert np.linalg.norm(scattered - reference_scattered) / np.linalg.norm(reference_scattered) <= 1e-10
    for mode_index, mode in enumerate(modes):
        face_i, face_j = 0, 0
        direct = direct_single_face_projection(
            layout, mode, trace, 60, face_i, face_j
        )
        np.testing.assert_allclose(components[mode_index], direct, rtol=1e-12, atol=1e-12)


def test_native_adapter_adjoint_and_slave_storage_contract():
    matrix = csr_matrix(np.asarray([[1 + 0.3j, 2 - 0.2j, 0], [0, 0.5 - 0.7j, 0]], complex))
    adapter = NativeBoundaryAdapter(matrix, [1, 3], 3, 5, [2], identity="task40-fixture")
    x = np.asarray([0.2 + 1j, 3 - 0.1j, 0], dtype=np.complex128)
    y = np.asarray([1, 2 + 0.3j, -0.1j, 2 - 1j, 3], dtype=np.complex128)
    np.testing.assert_allclose(np.vdot(y, adapter.extract(x)), np.vdot(adapter.scatter(y), x))
    assert adapter.scatter(y)[2] == 0
    invalid = x.copy()
    invalid[2] = 1e-30
    with pytest.raises(ValueError, match="slave zero"):
        adapter.extract(invalid)


def test_saved_p4_volume_tensor_reuse_skips_volume_form_assembly(monkeypatch):
    import basix
    import basix.ufl
    from dolfinx import mesh
    from mpi4py import MPI

    bounds = ((0.0, 0.6), (0.0, 0.8), (120.0, 130.0))
    lo = np.asarray([axis[0] for axis in bounds], dtype=np.float64)
    hi = np.asarray([axis[1] for axis in bounds], dtype=np.float64)
    msh = mesh.create_box(
        MPI.COMM_SELF,
        np.asarray([lo, hi]),
        [1, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    msh.topology.create_entity_permutations()
    geometry_map = np.asarray(msh.geometry.dofmap[0], dtype=np.int32)
    coordinates = np.ascontiguousarray(msh.geometry.x[geometry_map])
    cell_info = np.asarray(msh.topology.get_cell_permutation_info(), dtype=np.uint32)
    element = basix.ufl.element("N1curl", "hexahedron", 4).basix_element
    interior = np.asarray(element.entity_dofs[3][0], dtype=np.int64)
    trace = np.setdiff1d(np.arange(element.dim, dtype=np.int64), interior)
    tensor = np.eye(element.dim, dtype=np.complex128)
    saved_volume = {
        "tensor": tensor,
        "coordinates": coordinates,
        "cell_info": cell_info,
        "interior_positions": interior,
        "trace_positions": trace,
    }
    config = SimpleNamespace(
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
        eps_r=1.0 + 0.0j,
        substrate_index=3.0 + 0.0j,
        grating_index=3.0 + 0.0j,
        k0=1.0,
    )

    def forbidden_reassembly(*_args, **_kwargs):
        raise AssertionError("saved p4 reuse must not assemble its volume form")

    monkeypatch.setattr(task40_w1_local_probe, "_build_physical_volume_terms", forbidden_reassembly)
    local = task40_w1_local_probe._local_tensor(
        4, bounds, config, config.tags.air, saved_volume=saved_volume
    )
    np.testing.assert_array_equal(local["tensor"], tensor)
    assert local["volume_quadrature_policy"].startswith("reused hash-bound")
    assert local["form_integral_ids"] == []
    assert local["local_interior_dimension"] == 108


def test_v10_checker_recomputes_full_native_bd_rows_on_a_complex_off_origin_fixture():
    import basix
    import basix.ufl
    from dolfinx import mesh
    from mpi4py import MPI

    bounds = ((-3.0, -2.81), (1.25, 1.56), (120.0, 130.0))
    lo = np.asarray([axis[0] for axis in bounds], dtype=np.float64)
    hi = np.asarray([axis[1] for axis in bounds], dtype=np.float64)
    msh = mesh.create_box(
        MPI.COMM_SELF, np.asarray([lo, hi]), [1, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    msh.topology.create_entity_permutations()
    cell_info = np.asarray(msh.topology.get_cell_permutation_info(), dtype=np.uint32)
    geometry_map = np.asarray(msh.geometry.dofmap[0], dtype=np.int32)
    coordinates = np.ascontiguousarray(msh.geometry.x[geometry_map])
    modes = [{
        "side": "top",
        "k_vector": [0.41 - 0.07j, -0.28 + 0.03j, 0.13 + 0.02j],
        "e_vector": [1 + 0.2j, 0.3 - 0.1j, 0],
        "traction_vector": [0.7 - 0.8j, -0.9 + 0.2j, 0],
        "projection_denominator": 1.7,
    }]
    arrays = {
        "p6_q60_top_local_cell_coordinates": coordinates,
        "p6_q60_top_local_cell_orientation": cell_info,
    }
    checked = _recompute_v10_full_BD_rows(
        arrays, "p6_q60_top_", modes, degree=6, side="top"
    )
    assert checked["mode_count"] == checked["expected_mode_count"] == 1
    assert checked["all_native_rows_including_tiny_nonzero_checked"] is True
    assert checked["clipped_or_dropped_rows"] is False
    assert checked["pass"] is True


def test_v10_checker_recomputes_local_equations_and_uses_full_row_gate_only():
    prefix = "p6_q60_top_"
    A = np.eye(2, dtype=np.complex128)
    xi0 = np.asarray([1 + 0.2j])
    xt = np.asarray([0.5 - 0.1j])
    bi = np.asarray([0.3 + 0.2j])
    bt = np.asarray([0.1 + 0.3j])
    fi = A[:1, :1] @ xi0 + A[:1, 1:] @ xt + bi
    ft = A[1:, :1] @ xi0 + A[1:, 1:] @ xt + bt
    alpha = np.asarray([1 + 0.1j, 0.3 - 0.2j, -0.2 + 0.4j, 0.8 + 0.2j])
    port_rhs = np.asarray([0.2 + 0.1j, -0.1 + 0.3j, 0.05j, -0.07 + 0.04j])
    internal_b = np.asarray([0.2 + 0.0j, 0.1 + 0.0j, 0.04j, 0.03 - 0.01j])
    internal_f = np.asarray([0.1 + 0.0j, 0.05 + 0.0j, -0.02j, 0.01 + 0.02j])
    internal_trace = np.asarray([0.05 + 0.0j, 0.02 + 0.0j, 0.01j, -0.01 + 0.01j])
    internal_x = -internal_b + internal_f - internal_trace
    arrays = {
        prefix + "local_native_tensor": A,
        prefix + "interior_positions": np.asarray([0]),
        prefix + "trace_positions": np.asarray([1]),
        prefix + "recovered_interior": xi0,
        prefix + "interior_rhs": fi,
        prefix + "trace_values": xt,
        prefix + "trace_rhs": ft,
        prefix + "known_interior_solution": xi0,
        prefix + "Bi_alpha": bi,
        prefix + "Bt_alpha": bt,
        prefix + "mode_alpha": alpha,
        prefix + "port_rhs": port_rhs,
        prefix + "port_internal_B_correction": internal_b,
        prefix + "port_internal_rhs_correction": internal_f,
        prefix + "port_internal_recovered_correction": internal_x,
        prefix + "port_internal_trace_correction": internal_trace,
        prefix + "port_trace_action": np.asarray(
            [0.3 - 0.2j, 0.1 + 0.05j, -0.12 + 0.04j, 0.02 + 0.03j]
        ),
    }
    case = {"mode_count_full_ordered": 4, "analytic_full_row_crosscheck": {
        "status": "PASS", "verified_mode_count": 2, "expected_mode_count": 2,
        "B_full_native_rows_max_relative": 0.0,
        "D_full_native_rows_max_relative": 0.0,
        "B_internal_rows_max_absolute_error": 2e-30,
        "D_internal_rows_max_absolute_error": 2e-30,
        "small_nonzero_rows_clipped": False,
        "ordered_full_row_pair_digest_sha256": "0" * 64,
    }}
    checked = _v10_local_algebra_check(
        arrays, prefix, case, full_input_count=4, active_side_count=2
    )
    assert checked["pass"] is True


def test_v10_checker_recomputes_saved_controlled_negative_local_case(monkeypatch):
    observed = {}

    def local_check(arrays, prefix, case, *, full_input_count, active_side_count):
        observed["local"] = (prefix, full_input_count, active_side_count, case["case_status"])
        return {"pass": False, "known_state_recomputed_relative": 2.2e-11}

    def row_check(arrays, prefix, modes, *, degree, side):
        observed["rows"] = (prefix, degree, side)
        return {"pass": True, "mode_count": 16030}

    monkeypatch.setattr(v10_checker, "_v10_local_algebra_check", local_check)
    monkeypatch.setattr(v10_checker, "_recompute_v10_full_BD_rows", row_check)
    result = _recompute_v10_local_cases(
        {},
        [],
        [{"degree": 6, "side": "top", "case_status": "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE"}],
        full_input_count=32060,
        active_side_count=16030,
    )

    assert observed["local"] == (
        "p6_q60_top_", 32060, 16030, "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE"
    )
    assert observed["rows"] == ("p6_q60_top_", 6, "top")
    assert result[0]["recomputed"]["known_state_recomputed_relative"] == 2.2e-11
    assert result[0]["recomputed"]["case_status_agrees_with_recomputed_local_gate"] is True
    assert result[0]["recomputed"]["pass"] is False


def test_v10_checker_identity_separates_head_from_checker_file_hash():
    identity = v10_checker._v10_current_checker_identity()
    expected_head = v10_checker.subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=v10_checker.ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    expected_file_hash = hashlib.sha256(
        Path(v10_checker.__file__).resolve().read_bytes()
    ).hexdigest()

    assert identity == {
        "checker_source_sha": expected_head,
        "checker_file_sha256": expected_file_hash,
    }


def test_v10_bottom_resume_cli_dispatches_parent_without_fresh_extension(monkeypatch, tmp_path, capsys):
    observed = {}
    output = tmp_path / "bottom-resume"
    parent = tmp_path / "parent"
    expected = {
        "status": "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE",
        "checkpoint_stage": "BOTTOM_CONTINUATION_COMPLETE",
        "completed_local_objects": ["p4_top", "p6_top", "p4_bottom", "p6_bottom"],
        "all_local_equation_gates_pass": False,
        "elapsed_monotonic_seconds": 1.25,
    }

    def fake_resume(out, parent_out, *args):
        observed["paths"] = (Path(out), Path(parent_out))
        return expected

    monkeypatch.setattr(v10_runner, "run_v10_bottom_continuation", fake_resume)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_task40_w1_boundary_probe.py",
            "--output", str(output),
            "--v10-a-resume-bottom-from", str(parent),
        ],
    )

    assert v10_runner.main() == 0
    assert observed["paths"] == (output, parent)
    assert json.loads(capsys.readouterr().out)["completed_local_objects"] == expected[
        "completed_local_objects"
    ]


def test_v10_bottom_continuation_reuses_parent_and_runs_only_independent_bottom_objects(
    monkeypatch, tmp_path
):
    root = tmp_path.resolve()
    parent = root / "parent"
    (parent / "watchdog").mkdir(parents=True)
    output = root / "bottom-resume"
    (output / "watchdog").mkdir(parents=True)
    watchdog_summary_path = output / "watchdog" / "summary.json"
    watchdog_summary_path.write_text('{"status":"SUPERVISOR_CREATED"}')
    watchdog_summary_before = watchdog_summary_path.read_bytes()
    parent_arrays_path = parent / "parent_arrays.npz"
    parent_arrays_path.write_bytes(b"parent archive fixture")
    raw_path, reference_path = root / "w1_raw.npz", root / "v9_reference.npz"
    raw_path.write_bytes(b"frozen raw fixture")
    reference_path.write_bytes(b"frozen reference fixture")
    q60_apply = np.ones(156672, dtype=np.complex128)
    q60_components = np.ones((32060, 2), dtype=np.complex128)
    raw_arrays = {
        "q60_apply": q60_apply,
        "q60_components": q60_components,
        "surface_x_axis_nm": np.arange(273, dtype=np.float64),
        "surface_y_axis_nm": np.arange(5, dtype=np.float64),
        "floquet_phases": np.asarray([1.0 + 0j, 1.0 + 0j]),
        "representative_face_indices": np.asarray([[100, 1]], dtype=np.int64),
        "p4_bottom_local_native_tensor": np.eye(2, dtype=np.complex128),
        "p4_bottom_local_cell_coordinates": np.zeros((8, 3), dtype=np.float64),
        "p4_bottom_local_cell_orientation": np.asarray([0], dtype=np.int32),
        "p4_bottom_interior_positions": np.asarray([0], dtype=np.int64),
        "p4_bottom_trace_positions": np.asarray([1], dtype=np.int64),
        "p4_bottom_mode_alpha": np.ones(32060, dtype=np.complex128),
        "p4_bottom_trace_values": np.ones(1, dtype=np.complex128),
        "p4_bottom_known_interior_solution": np.ones(1, dtype=np.complex128),
    }
    reference_arrays = {
        "q60_apply_saved": q60_apply,
        "q60_components_saved": q60_components,
    }
    parent_arrays = {
        "generic_alpha": np.ones(32060, dtype=np.complex128),
        "generic_trace": np.ones(156672, dtype=np.complex128),
        "generic_q60_apply": np.ones(156672, dtype=np.complex128),
        "p4_q60_top_local_native_tensor": np.eye(2, dtype=np.complex128),
        "p6_q60_top_local_native_tensor": np.eye(2, dtype=np.complex128),
    }
    _sha = lambda value: hashlib.sha256(value).hexdigest()
    raw_sha, reference_sha = _sha(raw_path.read_bytes()), _sha(reference_path.read_bytes())
    q60_apply_sha = _sha(np.ascontiguousarray(q60_apply).tobytes())
    q60_components_sha = _sha(np.ascontiguousarray(q60_components).tobytes())
    producer_blob = b"frozen producer source fixture"
    producer_source_sha = "a" * 40
    inventory = {"ordered_key_count": 32060}
    q60_witness = {"status": "PASS_FINITE_WITNESSES", "witness_identity": "parent-q60"}

    def local_case(degree, side, status, state_relative):
        return {
            "degree": degree,
            "side": side,
            "case_status": status,
            "mode_count_full_ordered": 32060,
            "local_recovery_equation_relative": 0.0,
            "known_interior_solution_relative": state_relative,
            "local_original_trace_equation_relative": 0.0,
            "local_reduced_trace_equation_relative": 0.0,
            "local_trace_elimination_identity_relative": 0.0,
            "local_port_equation_relative": 0.0,
            "local_reduced_port_equation_relative": 0.0,
            "local_port_elimination_identity_relative": 0.0,
            "nonzero_internal_rhs_norm": 1.0,
            "nonzero_full_port_rhs_norm": 1.0,
            "nonzero_trace_rhs_norm": 1.0,
            "analytic_full_row_crosscheck": {"status": "PASS"},
            "small_key_native_carrier_witness": {"full_dof_direct_q30_gate_pass": True},
        }

    source_sha = _sha(producer_blob)
    parent_report = {
        "schema": "task40extra.review_v10_w1_a_saved_array_extension.v1",
        "completed_local_objects": ["p4_top", "p6_top"],
        "local_cases": [
            local_case(4, "top", "PASS", 0.0),
            local_case(6, "top", "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE", 2.2e-11),
        ],
        "q60_finite_witness": q60_witness,
        "input_inventory": inventory,
        "floquet_bridge": {"phase": "frozen"},
        "saved_w1_raw": {"path": "raw.npz", "sha256": raw_sha},
        "saved_v9_reference": {"path": "reference.npz", "sha256": reference_sha},
        "p4_volume_reused": True,
        "p6_volume_build_count": 1,
        "source_files_sha256": {"src/test/source_fixture.py": source_sha},
    }
    parent_arrays_meta = {
        "path": str(parent_arrays_path.relative_to(root)),
        "file_sha256": _sha(parent_arrays_path.read_bytes()),
        "file_bytes": parent_arrays_path.stat().st_size,
        "member_count": len(parent_arrays),
        "member_numeric_sha256": v10_runner._numeric_hashes(parent_arrays),
    }
    parent_report["arrays"] = parent_arrays_meta
    parent_report_path = parent / "w1_v10_a_extension_report.json"
    parent_report_path.write_text(json.dumps(parent_report))
    (parent / "watchdog" / "summary.json").write_text(json.dumps({
        "source_state": {
            "branch": "task40extra_0p7nm_engineering",
            "source_sha": producer_source_sha,
            "clean": True,
        }
    }))

    class FakeArchive:
        def __init__(self, arrays):
            self._arrays = arrays
            self.files = list(arrays)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __getitem__(self, name):
            return self._arrays[name]

    archive_map = {
        parent_arrays_path.resolve(): parent_arrays,
        raw_path.resolve(): raw_arrays,
        reference_path.resolve(): reference_arrays,
    }

    def fake_load(path, allow_pickle=False):
        assert allow_pickle is False
        return FakeArchive(archive_map[Path(path).resolve()])

    monkeypatch.setattr(v10_runner, "ROOT", root)
    monkeypatch.setattr(v10_runner.np, "load", fake_load)
    monkeypatch.setattr(v10_runner, "SAVED_W1_RAW_SHA256", raw_sha)
    monkeypatch.setattr(v10_runner, "SAVED_W9_REFERENCE_SHA256", reference_sha)
    monkeypatch.setattr(v10_runner, "SAVED_Q60_APPLY_SHA256", q60_apply_sha)
    monkeypatch.setattr(v10_runner, "SAVED_Q60_COMPONENTS_SHA256", q60_components_sha)
    monkeypatch.setattr(v10_runner, "_load_modes", lambda _path: ([{}] * 32060, inventory))
    monkeypatch.setattr(
        v10_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=producer_blob),
    )
    monkeypatch.setattr(v10_runner, "SimulationConfig3D", lambda **_kwargs: SimpleNamespace(
        tags=SimpleNamespace(substrate="substrate")
    ))
    monkeypatch.setattr(v10_runner, "FacetPolynomial", lambda _element: object())
    monkeypatch.setattr(v10_runner, "BoundaryLayout", lambda *_args: object())
    monkeypatch.setattr(v10_runner, "_make_element", lambda _degree: object())
    monkeypatch.setattr(v10_runner, "_source_file_hashes", lambda: {"current.py": "b" * 64})
    checkpoint_reports = []
    checkpoint_arrays = []

    def fake_atomic_npz(path, arrays):
        checkpoint_arrays.append(dict(arrays))
        return {
            "path": str(Path(path).relative_to(root)),
            "file_sha256": "c" * 64,
            "file_bytes": 10,
            "member_count": len(arrays),
            "member_numeric_sha256": v10_runner._numeric_hashes(arrays),
            "reopened_after_fsync": True,
        }

    monkeypatch.setattr(v10_runner, "_atomic_npz", fake_atomic_npz)
    monkeypatch.setattr(v10_runner, "_atomic_json", lambda _path, data: checkpoint_reports.append(data))
    calls = []

    def fake_stream(**kwargs):
        degree, side = kwargs["degree"], kwargs["side"]
        calls.append((degree, side))
        case = local_case(
            degree,
            side,
            "PASS",
            2.2e-11 if degree == 4 else 0.0,
        )
        case["arrays"] = {"fixture_bottom_object": np.asarray([degree], dtype=np.int64)}
        return case

    monkeypatch.setattr(v10_runner, "stream_boundary_correction", fake_stream)
    result = v10_runner.run_v10_bottom_continuation(
        output,
        parent,
        mode_path=root / "mode.json",
        raw_path=raw_path,
        reference_path=reference_path,
    )

    assert calls == [(4, "bottom"), (6, "bottom")]
    assert result["completed_local_objects"] == ["p4_top", "p6_top", "p4_bottom", "p6_bottom"]
    assert result["local_cases"][1]["case_status"] == "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE"
    assert result["local_cases"][2]["case_status"] == "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE"
    assert result["local_cases"][3]["case_status"] == "PASS"
    assert result["status"] == "CONTROLLED_NEGATIVE_LOCAL_EQUATION_GATE"
    assert result["parent_lineage"]["parent_producer_source_sha"] == producer_source_sha
    assert result["continuation"]["q60_finite_witness_recomputed"] is False
    assert result["continuation"]["top_local_objects_recomputed"] is False
    assert [item["checkpoint_stage"] for item in checkpoint_reports] == [
        "BOTTOM_CONTINUATION_STARTED", "BOTTOM_P4_CHECKPOINTED", "BOTTOM_CONTINUATION_COMPLETE"
    ]
    assert "p6_q60_top_local_native_tensor" in checkpoint_arrays[-1]
    assert "p4_q60_bottom_fixture_bottom_object" in checkpoint_arrays[-1]
    assert "p6_q60_bottom_fixture_bottom_object" in checkpoint_arrays[-1]
    assert _sha(parent_report_path.read_bytes()) == result["parent_lineage"]["parent_report_sha256"]
    assert watchdog_summary_path.read_bytes() == watchdog_summary_before


@pytest.mark.parametrize(
    "existing_result",
    ["w1_v10_a_extension_report.json", "w1_v10_a_extension_arrays.npz"],
)
def test_v10_bottom_continuation_rejects_existing_results_but_allows_watchdog_dir(
    monkeypatch, tmp_path, existing_result
):
    root = tmp_path.resolve()
    output = root / "bottom-resume"
    (output / "watchdog").mkdir(parents=True)
    (output / "watchdog" / "summary.json").write_text('{"status":"SUPERVISOR_CREATED"}')
    existing_path = output / existing_result
    existing_path.write_bytes(b"do not overwrite")
    monkeypatch.setattr(v10_runner, "ROOT", root)
    monkeypatch.setattr(
        v10_runner,
        "stream_boundary_correction",
        lambda **_kwargs: pytest.fail("existing result guard must run before any bottom computation"),
    )

    with pytest.raises(ValueError, match="already contains a V10 report or NPZ result"):
        v10_runner.run_v10_bottom_continuation(output, root / "parent")

    assert existing_path.read_bytes() == b"do not overwrite"


@pytest.mark.parametrize("degree", [4, 6])
@pytest.mark.parametrize("side", ["bottom", "top"])
def test_native_integral_retains_all_rows_against_direct_basix_quadrature(degree, side):
    import basix
    import basix.ufl

    element = basix.ufl.element("N1curl", "hexahedron", degree).basix_element
    polynomial = FacetPolynomial(element)
    J = np.diag([0.37, 0.21, 0.8])
    origin = np.asarray([-3.0, 1.25, 120.0 if side == "top" else -10.0])
    k = np.asarray([0.41 - 0.07j, -0.28 + 0.03j, 0.13], dtype=np.complex128)
    q = 30
    actual = polynomial.integral_native(side, k, J, origin, q)
    rule, weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
    zref = 1.0 if side == "top" else 0.0
    points_ref = np.column_stack((rule, np.full(len(rule), zref)))
    tab = element.tabulate(0, points_ref)[0][:, :, :2]
    points_phys = origin + points_ref * np.diag(J)
    phase = np.exp(1j * (points_phys @ k))
    expected = np.einsum("q,qjc->jc", weights * phase, tab, optimize=True)
    expected *= np.asarray([J[1, 1], J[0, 0]])
    np.testing.assert_allclose(actual, expected, rtol=2e-11, atol=2e-11)
    assert actual.shape == (element.dim, 2)
    assert len(polynomial.active[side]) < element.dim


@pytest.mark.parametrize("degree", [4, 6])
@pytest.mark.parametrize("side", ["bottom", "top"])
def test_direct_q30_full_dof_oracle_matches_candidate_integral(degree, side):
    import basix
    import basix.ufl

    element = basix.ufl.element("N1curl", "hexahedron", degree).basix_element
    polynomial = FacetPolynomial(element)
    lower = np.asarray([-5.25, 1.5, -10.0 if side == "bottom" else 120.0])
    extent = np.asarray([0.19, 0.31, 10.0])
    reference_vertices = basix.cell.geometry(basix.CellType.hexahedron)
    coordinates = lower + reference_vertices * extent
    k = np.asarray([0.21 - 0.03j, -0.17 + 0.01j, 0.07 + 0.02j])
    direct, rule, weights = _direct_full_basis_integral(
        element, side, k, coordinates, 30
    )
    candidate = polynomial.integral_native(
        side, k, np.diag(extent), lower, 30
    )
    np.testing.assert_allclose(direct, candidate, rtol=2e-11, atol=2e-11)
    assert rule.shape[1] == 2 and weights.shape == (len(rule),)
    assert direct.shape == (element.dim, 2)


def test_analytic_full_native_integral_applies_nonzero_xy_phase_once():
    import basix
    import basix.ufl

    element = basix.ufl.element("N1curl", "hexahedron", 6).basix_element
    polynomial = FacetPolynomial(element)
    side = "top"
    origin = np.asarray([-3.0, 1.25, 120.0])
    extent = np.asarray([0.19, 0.31, 10.0])
    J = np.diag(extent)
    vertices = basix.cell.geometry(basix.CellType.hexahedron)
    coordinates = origin + vertices * extent
    k = np.asarray([0.41 - 0.07j, -0.28 + 0.03j, 0.13 + 0.02j], dtype=np.complex128)
    candidate = polynomial.integral_native(side, k, J, origin, 60)
    analytic = analytic_full_basis_integral(polynomial, side, k, J, origin, dps=80)
    direct, _, _ = _direct_full_basis_integral(
        element, side, k, coordinates, quadrature_degree=60
    )
    np.testing.assert_allclose(analytic, direct, rtol=1e-11, atol=1e-11)
    np.testing.assert_allclose(candidate, direct, rtol=1e-11, atol=1e-11)


def test_direct_trace_carriers_use_owned_active_original_rows_only():
    # The slave row is exactly zero; the independent active rows survive with
    # their original ordering and are represented by the mainline P6 API.
    system = SimpleNamespace(
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=np.asarray([0, 2], dtype=np.int64),
            original_to_active={0: 0, 2: 1},
        )
    )
    C = np.asarray([[1 + 1j], [0], [2 - 1j]], dtype=np.complex128)
    D = np.asarray([[3 - 2j, 0, -0.5j]], dtype=np.complex128)
    terms = independent_trace_port_terms(system, C, D)
    assert len(terms) == 1
    np.testing.assert_array_equal(terms[0].B_original_rows, [0, 2])
    np.testing.assert_array_equal(terms[0].D_original_rows, [0, 2])
    with pytest.raises(ValueError, match="slave/interior support"):
        independent_trace_port_terms(system, C + np.asarray([[0], [1e-30], [0]]), D)
