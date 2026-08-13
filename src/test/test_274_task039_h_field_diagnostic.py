"""Focused offline contracts for the Task39 Full3D H diagnostic tool."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import task039_h_field_diagnostic as diagnostic


def _offsets() -> dict[str, object]:
    return {
        "source": "mesh_element_interior",
        "bottom": {
            "role": "bottom_element_safe_offset",
            "element_id": 1,
            "slab_index": 1,
            "z_nm": 15.0,
            "distance_from_interface_nm": 5.0,
            "source": "mesh_element_interior_midpoint",
        },
        "top": {
            "role": "top_element_safe_offset",
            "element_id": 5,
            "slab_index": 5,
            "z_nm": 105.0,
            "distance_from_interface_nm": 5.0,
            "source": "mesh_element_interior_midpoint",
        },
    }


def _hybrid_arrays() -> dict[str, np.ndarray]:
    shape = (7, 20, 40, 3)
    scalar = np.ones(shape, dtype=np.complex128)
    return {
        "x_nm": np.arange(40.0),
        "y_nm": np.arange(20.0),
        "z_nm": np.asarray([10.0, 15.0, 30.0, 60.0, 90.0, 105.0, 110.0]),
        "native_E_V_per_m": scalar.copy(),
        "native_H_A_per_m": scalar.copy(),
        "curlE_E_V_per_m": scalar.copy(),
        "curlE_H_A_per_m": scalar.copy(),
        "native_flux": np.ones(7),
        "curlE_flux": np.ones(7),
        "native_energy": np.ones(7),
        "curlE_energy": np.ones(7),
    }


def _full_arrays() -> dict[str, np.ndarray]:
    hybrid = _hybrid_arrays()
    return {
        "x_nm": hybrid["x_nm"],
        "y_nm": hybrid["y_nm"],
        "z_nm": hybrid["z_nm"],
        "E_V_per_m": hybrid["native_E_V_per_m"],
        "H_A_per_m": hybrid["native_H_A_per_m"],
        "normal_poynting_flux_W_per_m2": hybrid["native_flux"],
        "vacuum_weighted_sampled_energy_J_per_m3": hybrid["native_energy"],
    }


def _write_payload(
    tmp_path: Path,
    name: str,
    arrays: dict[str, np.ndarray],
    metadata: dict[str, object],
) -> Path:
    payload = tmp_path / name
    np.savez(payload, **arrays)
    descriptor = {
        "schema": (
            "task039.hybrid-h-diagnostic.v1"
            if "native_E_V_per_m" in arrays
            else diagnostic.PAYLOAD_SCHEMA
        ),
        "keys": list(arrays),
        "archive_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "archive_bytes": payload.stat().st_size,
        "arrays": {
            key: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": diagnostic._array_sha256(value),
                "finite": True,
            }
            for key, value in arrays.items()
        },
        **metadata,
    }
    if "native_E_V_per_m" not in arrays:
        descriptor.update(
            {
                "source": "canonical_full_fe_offline_replay",
                "no_matrix_assembly": True,
                "no_linear_solve": True,
            }
        )
    payload.with_suffix(".json").write_text(
        json.dumps(descriptor) + "\n", encoding="utf-8"
    )
    return payload


def test_old_five_plane_identity_passes_and_fails() -> None:
    arrays = {
        "E_V_per_m": np.ones((5, 2, 3, 3), dtype=np.complex128),
        "H_A_per_m": np.ones((5, 2, 3, 3), dtype=np.complex128),
        "x_nm": np.arange(3.0),
        "y_nm": np.arange(2.0),
        "z_nm": np.asarray([10.0, 30.0, 60.0, 90.0, 110.0]),
    }
    assert diagnostic.old_five_plane_identity(
        arrays["E_V_per_m"],
        arrays["H_A_per_m"],
        arrays,
        (arrays["x_nm"], arrays["y_nm"], arrays["z_nm"]),
    )["pass"]
    changed = dict(arrays)
    changed["H_A_per_m"] = changed["H_A_per_m"].copy()
    changed["H_A_per_m"][0, 0, 0, 0] += 1.0e-4
    assert not diagnostic.old_five_plane_identity(
        arrays["E_V_per_m"],
        changed["H_A_per_m"],
        arrays,
        (arrays["x_nm"], arrays["y_nm"], arrays["z_nm"]),
    )["pass"]
    bad_coordinates = (
        arrays["x_nm"].copy(),
        arrays["y_nm"].copy(),
        arrays["z_nm"].copy(),
    )
    bad_coordinates[0][0] += 0.1
    assert not diagnostic.old_five_plane_identity(
        arrays["E_V_per_m"], arrays["H_A_per_m"], arrays, bad_coordinates
    )["pass"]


def test_replay_identity_normalizes_only_source_path() -> None:
    archived = {
        "method": {"kind": "full3d_direct"},
        "geometry": {"wavelength_nm": 5.0},
        "provenance": {"source_path": "/official/input.dat"},
    }
    replayed = {
        "method": {"kind": "full3d_direct"},
        "geometry": {"wavelength_nm": 5.0},
        "provenance": {"source_path": "/raw/input_original.dat"},
    }
    identity = diagnostic._normalized_replay_identity(replayed, archived)
    expected = hashlib.sha256(
        diagnostic.canonical_json_bytes(archived) + b"\n"
    ).hexdigest()
    assert identity["status"] == "pass"
    assert identity["normalization"] == "provenance.source_path_only"
    assert identity["normalized_sha256"] == expected
    changed = dict(replayed)
    changed["method"] = {"kind": "full3d_iterative"}
    assert (
        diagnostic._normalized_replay_identity(changed, archived)["normalized_sha256"]
        != expected
    )


def test_payload_metadata_hash_and_mapping(tmp_path: Path) -> None:
    hybrid = _hybrid_arrays()
    path = _write_payload(
        tmp_path,
        "hybrid.npz",
        hybrid,
        {
            "plane_roles": [
                "interface_bottom",
                "bottom_element_safe_offset",
                "lower_reference",
                "middle_reference",
                "upper_reference",
                "top_element_safe_offset",
                "interface_top",
            ],
            "offset_provenance": _offsets(),
            "curl_source": "complete_reconstructed_field_analytic_or_fe",
        },
    )
    metadata, loaded = diagnostic._load_payload(path, path.with_suffix(".json"), True)
    assert tuple(loaded) == diagnostic.HYBRID_KEYS
    assert metadata["archive_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert diagnostic._path_mapping(metadata, loaded, "hybrid")["fields"][
        "E_V_per_m"
    ].shape == (7, 20, 40, 3)


def test_compare_calls_only_existing_h_checker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hybrid = _hybrid_arrays()
    full = _full_arrays()
    roles = [
        "interface_bottom",
        "bottom_element_safe_offset",
        "lower_reference",
        "middle_reference",
        "upper_reference",
        "top_element_safe_offset",
        "interface_top",
    ]
    hpath = _write_payload(
        tmp_path,
        "hybrid.npz",
        hybrid,
        {
            "plane_roles": roles,
            "offset_provenance": _offsets(),
            "curl_source": "complete_reconstructed_field_analytic_or_fe",
        },
    )
    fpath = _write_payload(
        tmp_path,
        "full3d.npz",
        full,
        {"plane_roles": roles, "offset_provenance": _offsets()},
    )
    called = []

    def fake_checker(native, curl, full3d):
        called.append((native, curl, full3d))
        return {
            "classification": "M480_H_DISCREPANCY_UNRESOLVED",
            "diagnostic_complete": True,
            "pass": False,
        }

    monkeypatch.setattr(diagnostic, "diagnose_h_paths", fake_checker)
    result = diagnostic.compare_payloads(hpath, fpath)
    assert len(called) == 1
    assert result["source"] == "diagnose_h_paths"
    assert result["comparison"]["classification"] == "M480_H_DISCREPANCY_UNRESOLVED"


def test_replay_contract_has_no_solver_or_assembly_runner_calls() -> None:
    tree = ast.parse(Path(diagnostic.__file__).read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "replay_full3d"
    )
    calls = [
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert not any(name.lower() in {"solve", "assemble", "runner"} for name in calls)
    names = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "build_airbox_mesh_3d",
        "_create_nedelec_space",
        "build_double_floquet_mpc",
        "read_canonical_packet_shard",
        "reconstruct_canonical_full_fe_function",
    } <= names


def test_replay_requires_mpi8() -> None:
    with pytest.raises(diagnostic.ReplayIdentityError, match="MPI size 8"):
        diagnostic.replay_full3d(
            Path("missing-t3-root"),
            Path("unused-output"),
            comm=type("Comm", (), {"size": 1, "rank": 0})(),
        )
