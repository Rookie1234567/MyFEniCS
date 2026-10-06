from __future__ import annotations

import builtins
from types import SimpleNamespace

from dolfinx import fem, mesh
from mpi4py import MPI
import numpy as np
import pytest

from src.postprocessing.postprocess_3d import (
    _optional_pyvista_module,
    _owned_point_mask,
    _save_scientific_field_npz,
    save_airbox_3d_fields,
)
from src.test.stage2_test_utils import stage4_block_config


def test_scientific_complex_field_and_owned_point_scope_survive_missing_pyvista(
    tmp_path, monkeypatch
):
    original_import = builtins.__import__

    def no_pyvista(name, *args, **kwargs):
        if name == "pyvista":
            raise ModuleNotFoundError("optional PyVista package is absent", name="pyvista")
        return original_import(name, *args, **kwargs)

    mesh = SimpleNamespace(
        topology=SimpleNamespace(
            dim=3,
            index_map=lambda _dim: SimpleNamespace(size_local=2),
        )
    )
    space = SimpleNamespace(
        mesh=mesh,
        dofmap=SimpleNamespace(
            cell_dofs=lambda cell: np.asarray(([0, 1], [1, 2], [3, 4])[cell], dtype=np.int32)
        ),
    )
    owned = _owned_point_mask(space, 5)
    assert owned.tolist() == [True, True, True, False, False]

    electric = np.arange(15, dtype=np.float64).reshape(5, 3).astype(np.complex128)
    electric[:, 1] += 1j * np.arange(5)
    magnetic = (2.0 - 0.5j) * electric
    out = _save_scientific_field_npz(
        tmp_path / "airbox_fields_3d_scientific.npz",
        {
            "schema": np.asarray("task40extra.airbox_scientific_fields.v1"),
            "E_total_V_per_m": electric,
            "H_curl_A_per_m": magnetic,
            "owned_point_mask": owned,
            "postprocess_point_scope": np.asarray("owned_cells_only"),
            "mpi_rank": np.asarray([0], dtype=np.int32),
            "mpi_size": np.asarray([1], dtype=np.int32),
        },
    )
    monkeypatch.setattr(builtins, "__import__", no_pyvista)
    pyvista, missing = _optional_pyvista_module()
    assert pyvista is None
    assert missing == "pyvista"
    assert out.is_file()
    with np.load(out, allow_pickle=False) as saved:
        assert np.array_equal(saved["E_total_V_per_m"], electric)
        assert np.array_equal(saved["H_curl_A_per_m"], magnetic)
        assert saved["E_total_V_per_m"].dtype == np.dtype(np.complex128)
        assert saved["owned_point_mask"].tolist() == owned.tolist()
        assert saved["postprocess_point_scope"].item() == "owned_cells_only"

    def broken_visualization(name, *args, **kwargs):
        if name == "pyvista":
            raise RuntimeError("unexpected visualization failure")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_visualization)
    with pytest.raises(RuntimeError, match="unexpected visualization failure"):
        _optional_pyvista_module()


def test_save_airbox_exports_science_before_optional_pyvista_skip(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def no_pyvista(name, *args, **kwargs):
        if name == "pyvista":
            raise ModuleNotFoundError("optional PyVista package is absent", name="pyvista")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pyvista)
    cfg = stage4_block_config(
        stage_case="stage4_block_grating",
        stage4_boundary_model="dtn_port",
        stage4_dtn_order_policy="zero_order",
        stage4_dtn_assembly="auxiliary",
        use_pml=False,
        pml_top_thickness=0.0,
        pml_bottom_thickness=0.0,
    )
    small_mesh = mesh.create_unit_cube(MPI.COMM_SELF, 1, 1, 1)
    tdim = small_mesh.topology.dim
    num_cells = small_mesh.topology.index_map(tdim).size_local
    cell_tags = mesh.meshtags(
        small_mesh,
        tdim,
        np.arange(num_cells, dtype=np.int32),
        np.full(num_cells, cfg.tags.air, dtype=np.int32),
    )
    mesh_data = SimpleNamespace(mesh=small_mesh, cell_tags=cell_tags)
    space = fem.functionspace(small_mesh, ("N1curl", 1))
    electric = fem.Function(space, name="E_total")
    electric.interpolate(
        lambda x: np.vstack(
            (
                np.ones(x.shape[1], dtype=np.complex128),
                np.zeros(x.shape[1], dtype=np.complex128),
                np.zeros(x.shape[1], dtype=np.complex128),
            )
        )
    )

    exported = save_airbox_3d_fields(
        mesh_data, cfg, electric, tmp_path / "science_before_viewer"
    )
    assert exported["scientific_fields_saved"] is True
    assert exported["visualization_status"] == "skipped_missing_dependency"
    assert exported["visualization_missing_dependency"] == "pyvista"
    assert exported["paraview_file"] is None
    assert exported["paraview_owned_cell_filter_applied"] is None
    assert exported["paraview_local_cells_written"] is None
    assert exported["scientific_field_npz_point_scope"] == "serial_all_cells"
    assert exported["scientific_field_npz_mpi_size"] == 1
    scientific_path = tmp_path / "science_before_viewer" / "airbox_fields_3d_scientific.npz"
    assert scientific_path.is_file()
    with np.load(scientific_path, allow_pickle=False) as saved:
        assert saved["mpi_rank"].item() == 0
        assert saved["mpi_size"].item() == 1
        assert saved["postprocess_point_scope"].item() == "serial_all_cells"
        assert saved["owned_point_mask"].all()
        assert np.isfinite(saved["E_total_V_per_m"]).all()
        assert np.isfinite(saved["H_curl_A_per_m"]).all()
        assert np.allclose(saved["E_total_code"][:, 0], 1.0)
