from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import benchmarks.task039_full3d_identity as full3d_identity
from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.task039_hybrid_direct_identity import (
    check_hybrid_direct_identity,
    main,
)


PLANES = np.asarray([10.0, 30.0, 60.0, 90.0, 110.0], dtype=np.float64)
PAYLOAD_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "E_V_per_m",
    "H_A_per_m",
    "modal_amplitudes",
    "bottom_q",
    "top_q",
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _inventory() -> dict[str, object]:
    keys: list[dict[str, object]] = []
    for side, spatial_count in (("bottom", 150), ("top", 152)):
        for polarization in ("s", "p"):
            keys.extend(
                {
                    "side": side,
                    "m": index,
                    "n": 0,
                    "polarization": polarization,
                }
                for index in range(spatial_count)
            )
    return {
        "keys": keys,
        "modes": [
            {"key": key, "propagating": True, "rayleigh_warning": False} for key in keys
        ],
        "counts": {
            "total": 604,
            "per_side": {"bottom": 300, "top": 304},
            "spatial": 302,
            "polarization": {"s": 302, "p": 302},
            "propagating": 604,
            "nonpropagating": 0,
            "rayleigh_warning": 0,
        },
    }


def _inventory_v3() -> dict[str, object]:
    keys: list[dict[str, object]] = []
    for side, spatial_count in (("bottom", 148), ("top", 152)):
        for polarization in ("s", "p"):
            keys.extend(
                {
                    "side": side,
                    "m": index,
                    "n": 0,
                    "polarization": polarization,
                }
                for index in range(spatial_count)
            )
    return {
        "keys": keys,
        "modes": [
            {"key": key, "propagating": True, "rayleigh_warning": False} for key in keys
        ],
        "counts": {
            "total": 600,
            "per_side": {"bottom": 296, "top": 304},
            "spatial": 300,
            "polarization": {"P": 300, "S": 300},
            "propagating": 598,
            "nonpropagating": 2,
            "rayleigh_warning": 0,
        },
    }


def _orders(inventory: dict[str, object]) -> list[dict[str, object]]:
    rows = []
    for index, key in enumerate(inventory["keys"]):
        rows.append(
            {
                **key,
                "power_ratio": 0.5 if index == 0 else 1.0e-9,
                "outgoing_amplitude": [1.0, 0.0] if index == 0 else [0.001, 0.0],
            }
        )
    return rows


def _arrays() -> dict[str, np.ndarray]:
    base = np.arange(5 * 20 * 40 * 3, dtype=np.float64).reshape(5, 20, 40, 3)
    return {
        "x_nm": np.arange(40, dtype=np.float64),
        "y_nm": np.arange(20, dtype=np.float64),
        "z_nm": PLANES.copy(),
        "E_V_per_m": (base + 1j * base / 100).astype(np.complex128),
        "H_A_per_m": (base / 10 + 1j * base / 50).astype(np.complex128),
    }


def _payload(numeric_dir: Path, inventory: dict[str, object]) -> dict[str, object]:
    side_counts = inventory["counts"]["per_side"]
    arrays = {
        **_arrays(),
        "modal_amplitudes": np.arange(4, dtype=np.float64).astype(np.complex128),
        "bottom_q": np.ones(side_counts["bottom"], dtype=np.complex128),
        "top_q": np.ones(side_counts["top"], dtype=np.complex128),
    }
    path = numeric_dir / "task039_direct_payload.npz"
    np.savez(path, **arrays)
    metadata = {}
    for key, array in arrays.items():
        metadata[key] = {
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "bytes": int(array.nbytes),
            "sha256": hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest(),
            "finite": True,
        }
    return {
        "schema": "task039.hybrid-direct-payload.v1",
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "keys": list(PAYLOAD_KEYS),
        "arrays": metadata,
    }


def _canonical_role(numeric_dir: Path, side: str, role: str) -> dict[str, object]:
    role_dir = numeric_dir / "canonical"
    role_dir.mkdir(exist_ok=True)
    manifest_role = f"{side}_{role}"
    packets = [
        ((manifest_role, index), complex(index + 1, index / 10)) for index in range(32)
    ]
    shards = []
    for rank in range(8):
        path = role_dir / f"{manifest_role}_rank{rank}.jsonl"
        metadata = write_canonical_packet_shard(
            path, packets[rank::8], audit_packets=True
        )
        shards.append({**metadata, "rank": rank})
    manifest = canonical_shard_manifest(
        role=manifest_role,
        mpi_size=8,
        shard_metadata=shards,
        extractor_audit={"by_rank": [{} for _ in range(8)]},
    )
    path = role_dir / f"{manifest_role}.manifest.json"
    digest = write_canonical_manifest(path, manifest)
    return {
        "pass": True,
        "manifest": f"canonical/{path.name}",
        "manifest_sha256": digest,
        "global_summed_packet_count": 32,
    }


def _write_hybrid(
    root: Path,
    inventory: dict[str, object],
    mode: int,
    *,
    model_id: str | None = None,
    h_nm: float = 10.0,
    incident_grazing_deg: float = 10.0,
) -> None:
    numeric_dir = root / "numerical_output"
    numeric_dir.mkdir(parents=True)
    payload_descriptor = _payload(numeric_dir, inventory)
    canonical_exports = {
        side: {
            "roles": {
                role: _canonical_role(numeric_dir, side, role)
                for role in ("active_trace", "full_fe")
            }
        }
        for side in ("bottom", "top")
    }
    numeric = {
        "case": {
            "requested_modes_per_direction": mode,
            "wavelength_nm": 5.0,
            "degree": 6,
            "h_nm": h_nm,
            "polarization_kind": "s",
            "incident_grazing_deg": incident_grazing_deg,
        },
        "mpi_size": 8,
        "external_mode_inventory": inventory,
        "qualification": {
            "integration_pass": True,
            "official_record": False,
            "mode_count_converged": False,
        },
        "solve": {"true_relative_residual": 2.0e-10},
        "validation": {
            "port_power": {"R_total": 0.4, "T_total": 0.2, "A_balance": 0.4},
            "interface_e_projection": {"combined_relative_residual": 2.0e-10},
            "fe_modal_traction_equilibrium": {
                "bottom_relative_residual": 2.0e-10,
                "top_relative_residual": 3.0e-10,
            },
            "external_diffraction_orders": _orders(inventory),
        },
        "physical_field_reconstruction": {
            "volume_absorption": {
                "A_volume_total": 0.4,
                "energy_closure_error": 2.0e-8,
            },
            "task039_direct_payload": payload_descriptor,
        },
        "hybrid_system": {
            "internal_unknown_count": 4,
            "primary_solver_path": "augmented",
            "block_shapes": {"H_modal": [2 * mode, 2 * mode]},
        },
        "qep": {
            "full_shape": [2 * mode, 2 * mode],
            "reduced_shape": [mode, mode],
            "positive_directional_selection": {
                "requested_modes": mode,
                "candidate_modes": 2 * mode,
                "selected_modes": mode,
            },
            "negative_directional_selection": {
                "requested_modes": mode,
                "candidate_modes": 2 * mode,
                "selected_modes": mode,
            },
        },
        "object_payload_ledger": {
            "modal_schur_bytes": 0,
            "retained_right_left_eigenvector_bytes": 4096,
            "local_or_augmented_factor_inventory": {
                "augmented": {
                    "available": True,
                    "factor_solver_type": "mumps",
                    "matrix_stats": {"matrix_rows": 100, "matrix_nnz_used": 2000},
                }
            },
            "projection_matrix": {
                "bottom": {"matrix_memory_estimate_bytes": 1000},
                "top": {"matrix_memory_estimate_bytes": 1100},
            },
        },
        "timing_seconds_max_rank": 1.25,
        "gates": {
            name: True
            for name in (
                "monolithic_true_relative_residual_le_1e-9",
                "primary_direct_true_relative_residual_le_1e-9",
                "interface_e_projection_relative_residual_le_1e-8",
                "fe_modal_traction_equilibrium_relative_residual_le_1e-8",
                "assembled_interface_h_t_exact_dual_le_1e-8",
                "volume_energy_closure_abs_le_1e-5",
                "external_port_rta_finite",
            )
        },
        "canonical_exports": {
            **canonical_exports,
        },
    }
    source_sha = "a" * 40
    manifest = {
        "status": "finished",
        "exit_status": 0,
        "source_sha": source_sha,
        "input_sha256": "b" * 64,
        "resolved_config_sha256": "c" * 64,
        "physical_model_sha256": "d" * 64,
        "mpi_size": 8,
        "method": "hybrid_direct",
        "model_id": model_id or f"task039_5nm_hybrid_direct_m{mode}",
        "resolved_method_adapter": "task039.hybrid_direct",
        "external_mode_inventory": inventory,
    }
    _write_json(root / "run_manifest.json", manifest)
    _write_json(
        root / "run_summary.json",
        {
            "status": "finished",
            "exit_status": 0,
            "resource_authority": {
                "process_tree_peak_rss_mb": 100.0,
                "peak_pss_mb": 90.0,
                "peak_uss_mb": 80.0,
                "process_tree_peak_swap_mb": 0.0,
            },
        },
    )
    _write_json(numeric_dir / "run_summary.json", numeric)


@pytest.fixture
def positive_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, Path]:
    inventory = _inventory()
    hybrid_m120 = tmp_path / "hybrid_m120"
    hybrid_m240 = tmp_path / "hybrid_m240"
    full3d = tmp_path / "full3d"
    _write_hybrid(hybrid_m120, inventory, 120)
    _write_hybrid(hybrid_m240, inventory, 240)
    full3d.mkdir()

    def fake_load_run(
        _run_dir: Path,
        _role: str,
        *,
        expected_mesh_target_size: float | None = 10.0,
    ) -> dict[str, object]:
        assert expected_mesh_target_size is None
        keys = tuple(
            (item["side"], item["m"], item["n"], item["polarization"])
            for item in inventory["keys"]
        )
        orders = {
            key: {
                "power_ratio": 0.5 if index == 0 else 1.0e-9,
                "outgoing_amplitude": 1.0 + 0.0j if index == 0 else 0.001 + 0.0j,
            }
            for index, key in enumerate(keys)
        }
        arrays = _arrays()
        return {
            "manifest": {
                "source_sha": "a" * 40,
                "physical_model_sha256": "d" * 64,
            },
            "numeric": {
                "R_total": 0.4,
                "T_total": 0.2,
                "A_balance": 0.4,
                "A_volume_total": 0.4,
                "energy_closure_error_port_volume": 2.0e-8,
                "mesh_target_size": 6.0,
            },
            "inventory": {"keys": keys},
            "orders": {"rows": orders},
            "reference": {
                "arrays": {
                    "E_V_per_m": arrays["E_V_per_m"],
                    "H_A_per_m": arrays["H_A_per_m"],
                },
                "coordinates": {key: arrays[key] for key in ("x_nm", "y_nm", "z_nm")},
            },
            "artifacts": {},
        }

    monkeypatch.setattr(full3d_identity, "_load_run", fake_load_run)
    record = tmp_path / "full3d_record.json"
    _write_json(record, {"raw_run_directory": "full3d"})
    return hybrid_m120, hybrid_m240, full3d, record


def test_own_adjacent_and_full3d_positive_with_augmented_telemetry(
    positive_runs: tuple[Path, Path, Path, Path],
) -> None:
    hybrid, adjacent, _full3d, record = positive_runs
    result = check_hybrid_direct_identity(
        hybrid, adjacent_run_dir=adjacent, full3d_record=record
    )
    assert result["pass"] is True
    assert result["classification"] == "HYBRID_DIRECT_DIAGNOSTIC_PASS_ONLY"
    assert result["production_validation_allowed"] is False
    assert result["blocked_by"] == "T4_5NM_FULL3D_ITERATIVE_NUMERICAL_NEGATIVE_AT_P6H10"
    assert result["own"]["qualification"]["official_record"] is False
    evidence = result["own"]["mode_evidence"]
    assert evidence["modal_schur_state"] == "not_materialized"
    assert (
        evidence["metrics"]["modal_schur_condition"]
        == "not_applicable_augmented_direct"
    )
    assert "augmented" in evidence["factor_inventory_components"]
    assert (
        evidence["factor_inventory_components"]["augmented"]["matrix_stats"][
            "matrix_rows"
        ]
        == 100
    )
    assert (
        evidence["projection_matrix_components"]["bottom"][
            "matrix_memory_estimate_bytes"
        ]
        == 1000
    )
    assert evidence["metrics"]["coupling_bytes_derived_sum"] == 2100
    assert evidence["metrics"]["coupling_bytes"] == 2100
    assert (
        evidence["metrics"]["coupling_bytes_classification"]
        == "derived_sum_of_projection_components"
    )
    assert evidence["mode_counts"]["positive_direction_counts"] == "not_available"
    assert result["comparisons"]["adjacent"]["coordinates_exact"]["pass"] is True
    assert (
        result["comparisons"]["full3d_diagnostic"]["coordinates_exact"]["pass"] is True
    )
    assert result["comparisons"]["full3d_diagnostic"]["reference_mesh_target_nm"] == 6.0
    assert result["comparisons"]["full3d_diagnostic"]["orders"]["keys_exact"] is True


def test_canonical_role_requires_side_prefix(
    positive_runs: tuple[Path, Path, Path, Path],
) -> None:
    hybrid, _adjacent, _full3d, _record = positive_runs
    summary_path = hybrid / "numerical_output" / "run_summary.json"
    numeric = json.loads(summary_path.read_text(encoding="utf-8"))
    descriptor = numeric["canonical_exports"]["bottom"]["roles"]["active_trace"]
    manifest_path = hybrid / "numerical_output" / descriptor["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["role"] = "active_trace"
    _write_json(manifest_path, manifest)
    descriptor["manifest_sha256"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    _write_json(summary_path, numeric)
    result = check_hybrid_direct_identity(hybrid)
    assert result["pass"] is False


def test_exact_order_key_mismatch_fails(
    positive_runs: tuple[Path, Path, Path, Path],
) -> None:
    hybrid, adjacent, _full3d, _record = positive_runs
    path = adjacent / "numerical_output" / "run_summary.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["validation"]["external_diffraction_orders"][0]["m"] = 9999
    _write_json(path, value)
    result = check_hybrid_direct_identity(hybrid, adjacent_run_dir=adjacent)
    assert result["pass"] is False


def test_adjacent_total_and_field_gates_fail(
    positive_runs: tuple[Path, Path, Path, Path],
) -> None:
    hybrid, adjacent, _full3d, _record = positive_runs
    summary_path = adjacent / "numerical_output" / "run_summary.json"
    numeric = json.loads(summary_path.read_text(encoding="utf-8"))
    numeric["validation"]["port_power"]["R_total"] = 0.42
    _write_json(summary_path, numeric)
    result = check_hybrid_direct_identity(hybrid, adjacent_run_dir=adjacent)
    assert result["comparisons"]["adjacent"]["observables"]["pass"] is False

    numeric["validation"]["port_power"]["R_total"] = 0.4
    _write_json(summary_path, numeric)
    payload_path = adjacent / "numerical_output" / "task039_direct_payload.npz"
    with np.load(payload_path, allow_pickle=False) as archive:
        arrays = {key: np.asarray(archive[key]).copy() for key in archive.files}
    arrays["E_V_per_m"] *= 2.0
    np.savez(payload_path, **arrays)
    numeric = json.loads(summary_path.read_text(encoding="utf-8"))
    descriptor = numeric["physical_field_reconstruction"]["task039_direct_payload"]
    descriptor["sha256"] = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    for key, array in arrays.items():
        if key == "E_V_per_m":
            descriptor["arrays"][key]["sha256"] = hashlib.sha256(
                np.ascontiguousarray(array).tobytes()
            ).hexdigest()
    _write_json(summary_path, numeric)
    result = check_hybrid_direct_identity(hybrid, adjacent_run_dir=adjacent)
    assert result["comparisons"]["adjacent"]["selected_EH"]["pass"] is False


def test_cli_reports_blocked_diagnostic_without_writing_run(
    positive_runs: tuple[Path, Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    hybrid, adjacent, _full3d, record = positive_runs
    exit_code = main(
        [
            "--hybrid-run",
            str(hybrid),
            "--adjacent-run",
            str(adjacent),
            "--full3d-record",
            str(record),
        ]
    )
    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["production_validation_allowed"] is False
    assert output["comparisons"]["full3d_diagnostic"]["pass"] is True


def test_v3_model_identity_accepts_and_near_miss_rejects(tmp_path: Path) -> None:
    root = tmp_path / "hybrid_v3"
    _write_hybrid(
        root,
        _inventory_v3(),
        480,
        model_id="task039_5nm_v3_1deg_s5_hybrid_direct_m480",
        h_nm=5.0,
        incident_grazing_deg=1.0,
    )
    accepted = check_hybrid_direct_identity(root)
    assert accepted["pass"] is True
    assert accepted["own"]["model_id"] == ("task039_5nm_v3_1deg_s5_hybrid_direct_m480")
    assert accepted["own"]["inventory"]["count"] == 600

    manifest_path = root / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_id"] = "task039_5nm_v3_1deg_s5_hybrid_direct_m240"
    _write_json(manifest_path, manifest)
    rejected = check_hybrid_direct_identity(root)
    assert rejected["pass"] is False
    assert rejected["classification"] == "HYBRID_DIRECT_OWN_AUTHORITY_FAIL"
