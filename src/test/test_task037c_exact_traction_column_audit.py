"""Pure contracts for the Task37c X2 exact traction-column audit."""

import ast
from pathlib import Path

import numpy as np
import pytest

from benchmarks.run_task037c_exact_traction_column_audit import (
    _array_descriptor,
    _one_cell_config,
    _project_exact_modal_dual,
    _relative_metrics,
    _split_normalize_four_blocks,
)
from src.common.config_3d import target_stage4_config


def test_split_normalizes_local_amplitudes_without_mixing_sides() -> None:
    forward = np.asarray([[2.0], [4.0], [6.0], [8.0]], dtype=np.complex128)
    backward = np.asarray([[3.0], [6.0], [9.0], [12.0]], dtype=np.complex128)
    blocks = _split_normalize_four_blocks(
        forward,
        backward,
        left_rows=2,
        right_rows=2,
        forward_factors=[2.0],
        backward_factors=[3.0],
    )
    np.testing.assert_allclose(blocks["bottom_forward"], [[2.0], [4.0]])
    np.testing.assert_allclose(blocks["top_forward"], [[3.0], [4.0]])
    np.testing.assert_allclose(blocks["bottom_backward"], [[1.0], [2.0]])
    np.testing.assert_allclose(blocks["top_backward"], [[9.0], [12.0]])


def test_split_rejects_zero_propagation_factor() -> None:
    values = np.ones((2, 1), dtype=np.complex128)
    with pytest.raises(ValueError, match="finite and nonzero"):
        _split_normalize_four_blocks(
            values,
            values,
            left_rows=1,
            right_rows=1,
            forward_factors=[0.0],
            backward_factors=[1.0],
        )


def test_split_uses_one_propagation_factor_per_column() -> None:
    forward = np.asarray(
        [[2.0, 4.0], [4.0, 8.0], [6.0, 12.0], [8.0, 16.0]],
        dtype=np.complex128,
    )
    backward = np.asarray(
        [[3.0, 6.0], [6.0, 12.0], [9.0, 18.0], [12.0, 24.0]],
        dtype=np.complex128,
    )
    blocks = _split_normalize_four_blocks(
        forward,
        backward,
        left_rows=2,
        right_rows=2,
        forward_factors=[2.0, 4.0],
        backward_factors=[3.0, 6.0],
    )
    np.testing.assert_allclose(blocks["top_forward"], [[3.0, 3.0], [4.0, 4.0]])
    np.testing.assert_allclose(blocks["bottom_backward"], [[1.0, 1.0], [2.0, 2.0]])


def test_relative_metrics_report_matrix_and_column_statistics() -> None:
    reference = np.asarray([[1.0, 2.0], [0.0, 4.0]], dtype=np.complex128)
    candidate = reference.copy()
    candidate[1, 0] += 0.5
    metrics = _relative_metrics(reference, candidate)
    assert metrics["relative_frobenius"] > 0.0
    assert metrics["per_column_relative_max"] >= metrics["per_column_relative_median"]
    assert metrics["max_absolute"] == pytest.approx(0.5)
    assert metrics["norm_scale"] == pytest.approx(
        max(np.linalg.norm(reference), np.linalg.norm(candidate))
    )


def test_array_descriptor_is_compact_and_hash_bound() -> None:
    values = np.asarray([[1.0 + 2.0j, 3.0 + 4.0j]], dtype=np.complex128)
    descriptor = _array_descriptor("forward", values)
    assert descriptor["name"] == "forward"
    assert descriptor["shape"] == [1, 2]
    assert descriptor["bytes"] == values.nbytes
    assert len(descriptor["sha256"]) == 64
    assert descriptor["finite"] is True


def test_exact_modal_projection_is_identity_in_active_coordinates() -> None:
    petrov = np.eye(2, dtype=np.complex128)
    flux = np.asarray(
        [[1.0 + 2.0j, 3.0 - 4.0j], [5.0 + 6.0j, 7.0 - 8.0j]],
        dtype=np.complex128,
    )
    np.testing.assert_allclose(_project_exact_modal_dual(petrov, flux), flux)


def test_one_cell_config_has_frozen_geometry() -> None:
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    one_cell = _one_cell_config(cfg)
    assert one_cell.z_min == pytest.approx(0.0)
    assert one_cell.z_max == pytest.approx(10.0)
    assert one_cell.air_height == pytest.approx(10.0)
    assert one_cell.substrate_thickness == pytest.approx(0.0)
    assert one_cell.interface_z == pytest.approx(0.0)
    assert one_cell.grating_height == pytest.approx(10.0)
    assert one_cell.mesh_axis_cell_counts == (6, 3, 1)
    assert one_cell.mesh_axis_z_profile == "task037c_x2_one_cell_z0_z10"


def test_runner_has_no_endcap_import_or_builder() -> None:
    runner = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / ("run_task037c_exact_traction_column_audit.py")
    )
    tree = ast.parse(runner.read_text(encoding="utf-8"))
    imported = []
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                calls.append(function.id)
            elif isinstance(function, ast.Attribute):
                calls.append(function.attr)
    assert all("endcap" not in name.lower() for name in imported)
    assert all("endcap" not in name.lower() for name in calls)
