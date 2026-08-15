from __future__ import annotations

import hashlib
import json
import builtins
import re
from pathlib import Path

import numpy as np
import pytest

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.task039_full3d_identity import check_full3d_identity, main, _load_run


def _inventory() -> dict[str, object]:
    keys: list[dict[str, object]] = []
    for side, count in (("bottom", 150), ("top", 152)):
        for polarization in ("s", "p"):
            keys.extend(
                [
                    {
                        "side": side,
                        "m": index,
                        "n": 0,
                        "polarization": polarization,
                    }
                    for index in range(count)
                ]
            )
    return {
        "keys": keys,
        "modes": [
            {"key": key, "propagating": True, "rayleigh_warning": False} for key in keys
        ],
        "counts": {
            "total": 604,
            "bottom": 300,
            "top": 304,
            "spatial": 302,
            "polarization": {"s": 302, "p": 302},
            "propagating": 604,
            "nonpropagating": 0,
            "rayleigh_warning": 0,
        },
    }


def _json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _write_canonical_role(directory: Path, role: str) -> dict[str, object]:
    role_dir = directory / "canonical"
    role_dir.mkdir(exist_ok=True)
    packets = [((role, index), complex(index + 1, index / 10)) for index in range(32)]
    shards = []
    for rank in range(8):
        shard_path = role_dir / f"{role}_rank{rank}.jsonl"
        metadata = write_canonical_packet_shard(
            shard_path, packets[rank::8], audit_packets=True
        )
        shards.append({**metadata, "rank": rank, "local_duplicate_count": 0})
    manifest = canonical_shard_manifest(
        role=role,
        mpi_size=8,
        shard_metadata=shards,
        extractor_audit={"by_rank": [{} for _ in range(8)]},
    )
    manifest_path = role_dir / f"{role}.manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    return {
        "manifest": f"canonical/{role}.manifest.json",
        "manifest_sha256": manifest_sha,
        "global_summed_packet_count": 32,
        "schema_version": "task037.canonical-vector-manifest.v1",
    }


def _write_run(root: Path, role: str, inventory: dict[str, object]) -> None:
    numeric_dir = root / "numerical_output"
    numeric_dir.mkdir(parents=True)
    canonical_roles = {
        name: _write_canonical_role(numeric_dir, name)
        for name in ("active_trace", "full_fe")
    }
    base = np.arange(5 * 20 * 40 * 3, dtype=np.float64).reshape(5, 20, 40, 3)
    arrays = {
        "x_nm": np.arange(40, dtype=np.float64),
        "y_nm": np.arange(20, dtype=np.float64),
        "z_nm": np.asarray([10.0, 30.0, 60.0, 90.0, 110.0]),
        "E_V_per_m": (base + 1j * base / 100).astype(np.complex128),
        "H_A_per_m": (base / 10 + 1j * base / 50).astype(np.complex128),
    }
    archive_path = numeric_dir / "full3d_reference_samples.npz"
    np.savez(archive_path, **arrays)
    archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    _json(
        numeric_dir / "full3d_reference_samples.json",
        {
            "archive": archive_path.name,
            "archive_bytes": archive_path.stat().st_size,
            "archive_sha256": archive_sha,
            "array_shape_z_y_x_component": [5, 20, 40, 3],
            "components": ["x", "y", "z"],
            "plane_metrics": [{"z_nm": z} for z in arrays["z_nm"]],
        },
    )
    orders = []
    for index, key in enumerate(inventory["keys"]):
        orders.append(
            {
                "side": key["side"],
                "m": key["m"],
                "n": key["n"],
                "polarization": key["polarization"],
                "power_ratio": 0.5 if index == 0 else 1.0e-9,
                "outgoing_amplitude": [1.0, 0.0] if index == 0 else [0.001, 0.0],
            }
        )
    _json(numeric_dir / "dtn_port_diffraction_orders_3d.json", {"orders": orders})
    physical_sha = "d" * 64
    canonical_key = (
        "full3d_direct_canonical_export"
        if role == "direct"
        else "task037_m3a_canonical_export"
    )
    numeric: dict[str, object] = {
        "case_status": "completed",
        "official_result": True,
        "mpi_size": 8,
        "lambda0_nm": 5.0,
        "nedelec_degree": 6,
        "mesh_target_size": 10.0,
        "polarization_kind": "s",
        "incident_theta_deg": 80.0,
        "incident_phi_deg": 0.0,
        "stage4_full3d_assembly_backend_actual": "assembly_time_static_condensed",
        "stage4_dtn_order_policy": "auto_propagating",
        "dtn_port_mode_count": 604,
        "R_total": 0.4,
        "T_total": 0.2,
        "A_balance": 0.4,
        "A_volume_total": 0.4,
        "energy_closure_error_port_volume": 2.0e-8,
        "full3d_reference_archive_sha256": archive_sha,
        canonical_key: {"status": "completed", "roles": canonical_roles},
    }
    if role == "iterative":
        numeric.update(
            {
                "external_mode_inventory": inventory,
                "external_linear_solver_port": True,
                "ksp_converged": True,
                "ksp_converged_reason": 4,
                "ksp_iterations": 120,
                "global_A_materialized": False,
                "global_F_materialized": False,
                "external_solver_profile": "never_materialized_owner_local_overlap0125_partition",
                "stage4_energy_balance_pass": True,
                "linear_system_relative_residual": 1.0e-7,
                "task039_solver_profile": {
                    "screen_iterations": 4000,
                    "restart": 90,
                    "relative_tolerance": 1.0e-6,
                    "initial_guess": "zero",
                    "preconditioner": "full3d_m3a_physical_slab_two_level",
                },
                "task039_m3a_core_audit": {
                    "matrix_type": "python_action_only",
                    "global_A_materialized": False,
                    "global_F_materialized": False,
                    "solver_profile": "never_materialized_owner_local_overlap0125_partition",
                    "external_reported_relative_residual": 2.0e-7,
                    "external_condensed_true_residual": 3.0e-7,
                    "external_full_augmented_true_residual": 4.0e-7,
                    "candidate": {
                        "outer_ksp": "fgmres",
                        "pc_side": "right",
                        "norm_type": "unpreconditioned",
                        "restart": 90,
                        "rtol": 1.0e-6,
                        "atol": 0.0,
                        "max_it": 4000,
                        "num_slabs": 16,
                        "overlap_fraction": 0.125,
                        "interpolation": "partition",
                        "absorption_shift": 0.1,
                    },
                    "no_global_factor_inventory": {
                        "global_direct_factor_count": 0,
                        "global_schur_matrix_materialized": False,
                        "global_A_materialized": False,
                        "global_F_materialized": False,
                    },
                },
            }
        )
    source_sha = "a" * 40
    manifest = {
        "status": "finished",
        "exit_status": 0,
        "source_sha": source_sha,
        "input_sha256": "b" * 64,
        "resolved_config_sha256": "c" * 64,
        "physical_model_sha256": physical_sha,
        "mpi_size": 8,
        "method": "full3d_direct" if role == "direct" else "full3d_iterative",
        "model_id": f"task039_5nm_{'full3d_direct' if role == 'direct' else 'full3d_iterative'}",
        "run_id": f"task039_5nm_{role}_p6h10_mpi8",
        "resolved_method_adapter": (
            "task038.full3d_direct" if role == "direct" else "task039.full3d_iterative"
        ),
        "external_mode_inventory": inventory,
    }
    _json(root / "run_manifest.json", manifest)
    _json(
        root / "run_summary.json",
        {
            "status": "finished",
            "exit_status": 0,
            "resource_authority": {
                "process_tree_peak_rss_mb": 100.0,
                "peak_pss_mb": 90.0,
                "peak_uss_mb": 80.0,
                "process_tree_peak_swap_mb": 0.0,
                "telemetry_status": "measured",
            },
        },
    )
    _json(numeric_dir / "run_summary.json", numeric)


@pytest.fixture
def run_pair(tmp_path: Path) -> tuple[Path, Path]:
    inventory = _inventory()
    direct = tmp_path / "direct"
    iterative = tmp_path / "iterative"
    _write_run(direct, "direct", inventory)
    _write_run(iterative, "iterative", inventory)
    return direct, iterative


def test_full3d_identity_positive_fixture(run_pair: tuple[Path, Path]) -> None:
    direct, iterative = run_pair
    result = check_full3d_identity(direct, iterative)
    assert result["pass"] is True
    assert result["classification"] == "A2_FULL3D_IDENTITY_PASS"
    assert result["inventory"]["count"] == 604
    assert result["inventory"]["exact_match"] is True
    assert result["inventory"]["numeric_inventory_available"] is False
    assert result["inventory"]["numeric_inventory_exact"] == "not_applicable"
    assert result["runs"]["iterative"]["inventory"]["numeric_inventory_exact"] is True
    expected_artifacts = {
        "run_manifest",
        "outer_run_summary",
        "numerical_run_summary",
        "diffraction_orders",
        "reference_json",
        "reference_archive",
        "active_trace_canonical_manifest",
        "full_fe_canonical_manifest",
    }
    for role in ("direct", "iterative"):
        artifacts = result["runs"][role]["artifacts"]
        assert set(artifacts) == expected_artifacts
        for artifact in artifacts.values():
            assert artifact["path"]
            assert re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
    assert result["comparisons"]["significant_orders"]["count"] == 1
    assert result["comparisons"]["selected_reference"]["E_V_per_m"]["pass"] is True
    assert result["comparisons"]["selected_reference"]["H_A_per_m"]["pass"] is True
    assert result["comparisons"]["canonical"]["active_trace"]["pass"] is True
    assert result["comparisons"]["canonical"]["full_fe"]["pass"] is True


def test_v3_1deg_profile_uses_dynamic_inventory_without_relaxing_legacy(
    run_pair: tuple[Path, Path],
) -> None:
    direct, _iterative = run_pair
    manifest_path = direct / "run_manifest.json"
    manifest = _read(manifest_path)
    manifest["model_id"] = "task039_5nm_v3_1deg_s5_full3d"
    manifest["external_mode_inventory"]["keys"] = manifest["external_mode_inventory"][
        "keys"
    ][:-1]
    _write(manifest_path, manifest)
    numeric_path = direct / "numerical_output/run_summary.json"
    numeric = _read(numeric_path)
    numeric["incident_theta_deg"] = 89.0
    numeric["mesh_target_size"] = 5.0
    numeric["dtn_port_mode_count"] = 603
    _write(numeric_path, numeric)
    orders_path = direct / "numerical_output/dtn_port_diffraction_orders_3d.json"
    orders = _read(orders_path)
    orders["orders"] = orders["orders"][:-1]
    _write(orders_path, orders)
    loaded = _load_run(
        direct,
        "direct",
        expected_mesh_target_size=5.0,
        profile="v3_1deg",
    )
    assert loaded["profile"] == "v3_1deg"
    assert loaded["manifest"]["model_id"] == "task039_5nm_v3_1deg_s5_full3d"
    assert loaded["inventory"]["count"] == 603


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    _json(path, value)


def test_inventory_key_mismatch_fails_closed(run_pair: tuple[Path, Path]) -> None:
    _direct, iterative = run_pair
    manifest_path = iterative / "run_manifest.json"
    manifest = _read(manifest_path)
    manifest["external_mode_inventory"]["keys"].pop()
    _write(manifest_path, manifest)
    result = check_full3d_identity(*run_pair)
    assert result["pass"] is False
    assert "604 unique keys" in result["errors"][0]


def test_significant_power_mismatch_fails(run_pair: tuple[Path, Path]) -> None:
    _direct, iterative = run_pair
    path = iterative / "numerical_output/dtn_port_diffraction_orders_3d.json"
    payload = _read(path)
    payload["orders"][0]["power_ratio"] = 0.5002
    _write(path, payload)
    result = check_full3d_identity(*run_pair)
    assert result["pass"] is False
    assert "significant diffraction order" in " ".join(result["errors"])


def test_significant_complex_amplitude_phase_mismatch_fails(
    run_pair: tuple[Path, Path],
) -> None:
    _direct, iterative = run_pair
    path = iterative / "numerical_output/dtn_port_diffraction_orders_3d.json"
    payload = _read(path)
    payload["orders"][0]["outgoing_amplitude"] = [0.0, 1.0]
    _write(path, payload)
    result = check_full3d_identity(*run_pair)
    assert result["pass"] is False
    assert "significant diffraction order" in " ".join(result["errors"])


def test_selected_reference_mismatch_fails(run_pair: tuple[Path, Path]) -> None:
    _direct, iterative = run_pair
    numeric_dir = iterative / "numerical_output"
    reference_path = numeric_dir / "full3d_reference_samples.json"
    reference = _read(reference_path)
    archive_path = numeric_dir / reference["archive"]
    with np.load(archive_path, allow_pickle=False) as archive:
        arrays = {name: np.asarray(archive[name]).copy() for name in archive.files}
    arrays["E_V_per_m"][0, 0, 0, 0] += 1.0e6
    arrays["x_nm"][0] += 1.0
    np.savez(archive_path, **arrays)
    reference["archive_sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    reference["archive_bytes"] = archive_path.stat().st_size
    _write(reference_path, reference)
    result = check_full3d_identity(*run_pair)
    assert result["pass"] is False
    assert "selected E_V_per_m" in " ".join(result["errors"])
    assert result["comparisons"]["selected_reference"]["coordinates_exact"] is False


def test_canonical_coefficient_mismatch_fails(run_pair: tuple[Path, Path]) -> None:
    _direct, iterative = run_pair
    shard_path = iterative / "numerical_output/canonical/active_trace_rank0.jsonl"
    lines = shard_path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["value"][0] += 10.0
    lines[0] = json.dumps(row, sort_keys=True, separators=(",", ":"))
    shard_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = iterative / "numerical_output/canonical/active_trace.manifest.json"
    manifest = _read(manifest_path)
    manifest["per_rank_shards"][0]["file_sha256"] = hashlib.sha256(
        shard_path.read_bytes()
    ).hexdigest()
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    summary_path = iterative / "numerical_output/run_summary.json"
    numeric = _read(summary_path)
    numeric["task037_m3a_canonical_export"]["roles"]["active_trace"][
        "manifest_sha256"
    ] = manifest_sha
    _write(summary_path, numeric)
    result = check_full3d_identity(*run_pair)
    assert result["pass"] is False
    assert result["comparisons"]["canonical"]["active_trace"]["pass"] is False
    comparison = result["comparisons"]["canonical"]["active_trace"]
    assert comparison["missing_key_count"] == 0
    assert comparison["extra_key_count"] == 0
    assert comparison["duplicate_left_count"] == 0
    assert comparison["duplicate_right_count"] == 0
    assert comparison["left_shape"] == comparison["right_shape"]
    assert comparison["relative_coefficient_l2"] > 1.0e-5


def test_iterative_residual_gate_fails(run_pair: tuple[Path, Path]) -> None:
    _direct, iterative = run_pair
    path = iterative / "numerical_output/run_summary.json"
    numeric = _read(path)
    numeric["task039_m3a_core_audit"]["external_condensed_true_residual"] = 2.0e-6
    _write(path, numeric)
    result = check_full3d_identity(*run_pair)
    assert result["pass"] is False
    assert "condensed_true_residual" in " ".join(result["errors"])


def test_reference_archive_hash_mismatch_fails_closed(
    run_pair: tuple[Path, Path],
) -> None:
    _direct, iterative = run_pair
    path = iterative / "numerical_output/full3d_reference_samples.json"
    reference = _read(path)
    reference["archive_sha256"] = "0" * 64
    _write(path, reference)
    result = check_full3d_identity(*run_pair)
    assert result["pass"] is False
    assert "reference archive SHA256" in result["errors"][0]


def test_cli_is_read_only_and_does_not_import_solver_runner(
    run_pair: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    direct, iterative = run_pair
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("src.runners"):
            raise AssertionError(f"identity checker imported a solver runner: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert main(["--direct-run", str(direct), "--iterative-run", str(iterative)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pass"] is True
    assert payload["classification"] == "A2_FULL3D_IDENTITY_PASS"
