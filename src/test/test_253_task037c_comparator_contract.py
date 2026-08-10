from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.task037c_comparator import (
    compare_hybrid_full3d,
    compare_iterative_direct,
    compare_m120_m160,
    compare_mpi8_mpi1,
    compare_mirror_power,
    compare_m_selection,
    load_direct_case,
    load_full3d_case,
    load_iterative_case,
)


SOURCE_SHA = "a" * 40


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_descriptor(value: np.ndarray) -> dict[str, Any]:
    value = np.ascontiguousarray(value)
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "sha256": hashlib.sha256(value.tobytes()).hexdigest(),
        "finite": True,
    }


def _write_canonical(root: Path, tag: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for side in ("bottom", "top"):
        roles: dict[str, Any] = {}
        for role in ("active_trace", "full_fe"):
            shard_path = root / f"{tag}_{side}_{role}.jsonl"
            shard = write_canonical_packet_shard(
                shard_path,
                [((side, role, 0), 1.0 + 0.0j), ((side, role, 1), 2.0 + 0.0j)],
                audit_packets=True,
            )
            manifest_path = root / f"{tag}_{side}_{role}.json"
            manifest = canonical_shard_manifest(
                role=f"{side}_{role}",
                mpi_size=1,
                shard_metadata=[shard],
                extractor_audit={"by_rank": [{"local_packet_count": 2}]},
            )
            manifest_sha = write_canonical_manifest(manifest_path, manifest)
            roles[role] = {
                "manifest": str(manifest_path),
                "manifest_sha256": manifest_sha,
            }
        result[side] = {"roles": roles}
    return result


def _write_payload(
    root: Path,
    tag: str,
    *,
    include_finite: bool = True,
    modal_count: int = 4,
    bottom_count: int = 2,
    top_count: int = 3,
) -> dict[str, Any]:
    arrays = {
        "x_nm": np.arange(40, dtype=np.float64),
        "y_nm": np.arange(20, dtype=np.float64),
        "z_nm": np.asarray([10.0, 30.0, 60.0, 90.0, 110.0]),
        "E_V_per_m": np.ones((5, 20, 40, 3), dtype=np.complex128),
        "H_A_per_m": np.full((5, 20, 40, 3), 2.0 + 0.0j, dtype=np.complex128),
        "modal_amplitudes": np.arange(modal_count, dtype=np.complex128) + 1.0,
        "bottom_q": np.arange(bottom_count, dtype=np.complex128) + 1.0,
        "top_q": np.arange(top_count, dtype=np.complex128) + 3.0,
    }
    path = root / f"{tag}.npz"
    np.savez(path, **arrays)
    descriptor = {
        "schema_version": "task037c.direct-hybrid-payload.v1",
        "path": str(path),
        "sha256": _file_sha(path),
        "bytes": path.stat().st_size,
        "keys": sorted(arrays),
        "arrays": {name: _array_descriptor(value) for name, value in arrays.items()},
    }
    if not include_finite:
        for item in descriptor["arrays"].values():
            item.pop("finite")
    return descriptor


def _order_rows(*, mirror: bool = False, full3d: bool = False) -> list[dict[str, Any]]:
    identities = [
        ("bottom", 0, 0, "s"),
        ("bottom", -1, 1, "s"),
        ("top", 0, 0, "s"),
        ("top", 1, 0, "s"),
        ("top", -1, 1, "s"),
    ]
    rows = []
    for index, (side, m, n, polarization) in enumerate(identities):
        row = {
            "side": side,
            "m": m,
            "n": -n if mirror else n,
            "polarization": polarization,
            "power_ratio": 1.0e-8 if index == 1 else 0.1 + index,
        }
        if full3d:
            row.update({"beta": [1.0, 0.0], "auxiliary_index": index})
        else:
            row.update(
                {
                    "beta_per_nm": [1.0, 0.0],
                    "local_auxiliary_index": index if side == "bottom" else index - 2,
                }
            )
        rows.append(row)
    return rows


def _write_direct_or_iterative_record(
    root: Path,
    *,
    method: str,
    tag: str,
    phi: float = 0.0,
    requested_modes: int = 120,
    mpi_size: int = 8,
    mirror: bool = False,
) -> tuple[Path, str]:
    payload = _write_payload(
        root,
        f"{tag}_payload",
        include_finite=method == "direct",
    )
    rows = _order_rows(mirror=mirror)
    canonical = _write_canonical(root, tag)
    observables = {
        "R_total": 0.1,
        "T_total": 0.2,
        "A_balance": 0.7,
        "A_volume_total": 0.7,
        "energy_closure_error": 0.0,
    }
    record: dict[str, Any] = {
        "metadata": {
            "commit_sha": SOURCE_SHA,
            "incident_phi_deg": phi,
            "mpi_size": mpi_size,
        },
        "case": {
            "incident_theta_deg": 89.0,
            "incident_grazing_deg": 1.0,
            "polarization_kind": "s",
            "requested_modes_per_direction": requested_modes,
        },
        "hybrid_system": {"internal_unknown_count": 4},
        "validation": {
            "port_power": {
                "R_total": observables["R_total"],
                "T_total": observables["T_total"],
                "A_balance": observables["A_balance"],
            },
            "interface_e_projection": {"combined_relative_residual": 1.0e-10},
            "external_diffraction_orders": rows,
        },
        "physical_field_reconstruction": {
            "volume_absorption": observables,
            "task037c_direct_payload": payload,
            "task037c_canonical_export": canonical,
        },
        "qualification": {"task037c_direct_pass": True},
    }
    if method == "iterative":
        for key in (
            "metadata",
            "case",
            "hybrid_system",
            "validation",
            "physical_field_reconstruction",
            "qualification",
        ):
            record.pop(key, None)
        record.update(
            {
                "profile": {
                    "incident_grazing_deg": 1.0,
                    "incident_phi_deg": phi,
                    "polarization_kind": "s",
                    "requested_modes": requested_modes,
                    "mpi_size": mpi_size,
                },
                "source": {
                    "before": {"verified_clean_sha": SOURCE_SHA},
                    "after": {
                        "head": SOURCE_SHA,
                        "verified_clean_sha": SOURCE_SHA,
                        "clean": True,
                        "matches_verified_clean_sha": True,
                    },
                },
                "physics": {
                    "energy": {
                        "R": observables["R_total"],
                        "T": observables["T_total"],
                        "A": observables["A_balance"],
                        "A_volume": observables["A_volume_total"],
                        "closure": observables["energy_closure_error"],
                    },
                    "external_orders": rows,
                    "interface_continuity": {
                        "bottom": {"electric_tangential": {"relative_l2": 1.0e-10}},
                        "top": {"electric_tangential": {"relative_l2": 1.0e-10}},
                    },
                    "own_grid": payload,
                    "canonical": canonical,
                },
                "linear": {
                    "inventory": {"block_ldu": {"modal_schur": {"shape": [4, 4]}}}
                },
                "online_pass": True,
                "status": "online_candidate_pass_awaiting_offline_checker",
                "qualification": {"pass": True},
            }
        )
    record_path = root / f"{tag}_record.json"
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    record_sha = _file_sha(record_path)
    watchdog: dict[str, Any] = {
        "schema": "task037c.synthetic-watchdog.v1",
        "source": {"head": SOURCE_SHA, "verified_clean_sha": SOURCE_SHA},
        "mpi_size": mpi_size,
        "failures": [],
    }
    if method == "direct":
        watchdog["source"] = {"commit_sha": SOURCE_SHA}
        watchdog.update(
            {
                "status": "task037c_direct_robustness_pass",
                "formal_pass": True,
                "official_result": True,
                "task037c_direct_pass": True,
                "return_code": 0,
                "no_swap": True,
                "memory_authority_pass": True,
                "source_gate": {"pass": True},
                "launch_gate": {"pass": True},
                "solver_record_ignored_path": str(record_path),
                "solver_record_sha256": record_sha,
            }
        )
    else:
        watchdog["source_preflight"] = {
            "head": SOURCE_SHA,
            "verified_clean_sha": SOURCE_SHA,
        }
        watchdog.update(
            {
                "status": "watchdog_pass_awaiting_offline_checker",
                "qualification": {"pass": True},
                "official_result": False,
                "online_record": {
                    "path": str(record_path),
                    "sha256": record_sha,
                    "json_valid": True,
                    "online_pass": True,
                    "status": "online_candidate_pass_awaiting_offline_checker",
                },
            }
        )
    path = root / f"{tag}_watchdog.json"
    path.write_text(json.dumps(watchdog, sort_keys=True) + "\n", encoding="utf-8")
    return path, _file_sha(path)


def _write_full3d_watchdog(root: Path, tag: str) -> tuple[Path, str]:
    run_directory = root / f"{tag}_run"
    run_directory.mkdir()
    payload = _write_payload(run_directory, f"{tag}_full3d")
    with np.load(payload["path"], allow_pickle=False) as archive:
        full_arrays = {
            name: np.asarray(archive[name])
            for name in ("x_nm", "y_nm", "z_nm", "E_V_per_m", "H_A_per_m")
        }
    full_arrays.update(
        {
            "interface_z_nm": np.asarray([10.0, 110.0], dtype=np.float64),
            "E_t_interface_V_per_m": np.ones((2, 20, 40, 2), dtype=np.complex128),
            "H_t_interface_A_per_m": np.ones((2, 20, 40, 2), dtype=np.complex128),
        }
    )
    full_payload_path = run_directory / f"{tag}_full3d_reference.npz"
    np.savez(full_payload_path, **full_arrays)
    order_path = run_directory / "dtn_port_diffraction_orders_3d.json"
    order_rows = _order_rows(full3d=True)
    order_path.write_text(json.dumps({"orders": order_rows}) + "\n", encoding="utf-8")
    archive_metadata = {
        "archive_sha256": _file_sha(full_payload_path),
        "archive_bytes": full_payload_path.stat().st_size,
    }
    qualification = {
        "pass": True,
        "external_orders": {
            "path": str(order_path.resolve()),
            "observed_sha256": _file_sha(order_path),
            "bytes": order_path.stat().st_size,
            "count": len(order_rows),
            "keys_unique": True,
            "all_finite": True,
            "pass": True,
        },
        "reference_export": {
            "archive": str(full_payload_path.resolve()),
            "metadata": archive_metadata,
            "pass": True,
        },
    }
    watchdog: dict[str, Any] = {
        "schema": "task037c.full3d-watchdog.v1",
        "status": "task037c_full3d_robustness_pass",
        "source": {"commit_sha": SOURCE_SHA},
        "return_code": 0,
        "no_swap": True,
        "mpi_size": 8,
        "qualification": qualification,
        "raw_evidence": {"run_directory": str(run_directory.resolve())},
        "solver_summary": {
            "official_result": True,
            "config": {
                "incident_theta_deg": 89.0,
                "incident_phi_deg": 0.0,
                "polarization_kind": "s",
            },
            "R_total": 0.1,
            "T_total": 0.2,
            "A_balance": 0.7,
            "A_volume_total": 0.7,
            "energy_closure_error_port_volume": 0.0,
            "full3d_reference_archive": str(full_payload_path.resolve()),
            "dtn_port_orders_json": str(order_path.name),
        },
    }
    path = root / f"{tag}_watchdog.json"
    path.write_text(json.dumps(watchdog, sort_keys=True) + "\n", encoding="utf-8")
    return path, _file_sha(path)


def _load_set(tmp_path: Path) -> dict[str, Any]:
    direct120_path, direct120_sha = _write_direct_or_iterative_record(
        tmp_path, method="direct", tag="direct120"
    )
    direct160_path, direct160_sha = _write_direct_or_iterative_record(
        tmp_path, method="direct", tag="direct160", requested_modes=160
    )
    iterative_path, iterative_sha = _write_direct_or_iterative_record(
        tmp_path, method="iterative", tag="iterative"
    )
    mpi1_path, mpi1_sha = _write_direct_or_iterative_record(
        tmp_path, method="iterative", tag="mpi1", mpi_size=1
    )
    full_path, full_sha = _write_full3d_watchdog(tmp_path, "full3d")
    return {
        "direct120": load_direct_case(
            direct120_path,
            direct120_sha,
            expected_source_sha=SOURCE_SHA,
            expected_phi=0.0,
        ),
        "direct160": load_direct_case(
            direct160_path,
            direct160_sha,
            expected_source_sha=SOURCE_SHA,
            expected_phi=0.0,
        ),
        "iterative": load_iterative_case(
            iterative_path,
            iterative_sha,
            expected_source_sha=SOURCE_SHA,
            expected_phi=0.0,
        ),
        "mpi1": load_iterative_case(
            mpi1_path, mpi1_sha, expected_source_sha=SOURCE_SHA, expected_phi=0.0
        ),
        "full3d": load_full3d_case(
            full_path, full_sha, expected_source_sha=SOURCE_SHA, expected_phi=0.0
        ),
        "direct120_path": direct120_path,
    }


def test_loaders_and_three_comparisons_use_production_layers(tmp_path: Path) -> None:
    cases = _load_set(tmp_path)
    direct120 = cases["direct120"]
    assert len(direct120.mode_keys["bottom"]) == 2
    assert len(direct120.mode_keys["top"]) == 3
    assert compare_m120_m160(direct120, cases["direct160"])["pass"]
    assert compare_hybrid_full3d(direct120, cases["full3d"])["pass"]
    assert compare_iterative_direct(cases["iterative"], direct120)["pass"]
    assert compare_mpi8_mpi1(cases["iterative"], cases["mpi1"])["pass"]
    assert (
        compare_m_selection(
            [
                {
                    "phi_deg": phi,
                    "direct_pass": True,
                    "m120_vs_m160_pass": True,
                    "full3d_pass": True,
                }
                for phi in (-5.0, 0.0, 5.0)
            ],
            [],
        )["selected_m_robust"]
        == 120
    )


def test_mirror_is_power_only_and_hash_tamper_fails_closed(tmp_path: Path) -> None:
    left_path, left_sha = _write_direct_or_iterative_record(
        tmp_path, method="direct", tag="minus", phi=-5.0
    )
    right_path, right_sha = _write_direct_or_iterative_record(
        tmp_path, method="direct", tag="plus", phi=5.0, mirror=True
    )
    left = load_direct_case(
        left_path, left_sha, expected_source_sha=SOURCE_SHA, expected_phi=-5.0
    )
    right = load_direct_case(
        right_path, right_sha, expected_source_sha=SOURCE_SHA, expected_phi=5.0
    )
    mirror = compare_mirror_power(left, right)
    assert mirror["pass"]
    assert mirror["amplitude"] == "not_run_without_phase_map"
    with np.testing.assert_raises(ValueError):
        load_direct_case(
            left_path, "b" * 64, expected_source_sha=SOURCE_SHA, expected_phi=-5.0
        )


def test_actual_layers_have_no_shortcut_carriers(tmp_path: Path) -> None:
    path, _sha = _write_direct_or_iterative_record(
        tmp_path, method="direct", tag="direct"
    )
    record = json.loads((tmp_path / "direct_record.json").read_text(encoding="utf-8"))
    assert "identity" not in record
    assert "payload" not in record
    assert "orders" not in record
    assert "canonical" not in record
    assert "solver_record" not in record
    assert "record" not in json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "missing", ("source_gate", "launch_gate", "memory_authority_pass")
)
def test_direct_watchdog_requires_all_independent_gates(
    tmp_path: Path, missing: str
) -> None:
    path, _sha = _write_direct_or_iterative_record(
        tmp_path, method="direct", tag=f"direct_{missing}"
    )
    watchdog = json.loads(path.read_text(encoding="utf-8"))
    watchdog.pop(missing)
    path.write_text(json.dumps(watchdog) + "\n", encoding="utf-8")
    with pytest.raises((KeyError, ValueError, TypeError)):
        load_direct_case(
            path,
            _file_sha(path),
            expected_source_sha=SOURCE_SHA,
            expected_phi=0.0,
        )


def test_iterative_online_descriptor_requires_production_status(
    tmp_path: Path,
) -> None:
    path, _sha = _write_direct_or_iterative_record(
        tmp_path, method="iterative", tag="iterative_bad_descriptor"
    )
    watchdog = json.loads(path.read_text(encoding="utf-8"))
    watchdog["online_record"].pop("json_valid")
    path.write_text(json.dumps(watchdog) + "\n", encoding="utf-8")
    with pytest.raises((KeyError, ValueError, TypeError)):
        load_iterative_case(
            path,
            _file_sha(path),
            expected_source_sha=SOURCE_SHA,
            expected_phi=0.0,
        )


def test_mode_threshold_field_and_canonical_failures_are_not_passes(
    tmp_path: Path,
) -> None:
    cases = _load_set(tmp_path)
    left = cases["direct120"]
    right = cases["direct160"]
    changed_orders = dict(right.orders)
    key = sorted(changed_orders)[0]
    changed_orders[key] = {**changed_orders[key], "power": 0.101}
    changed = replace(right, orders=changed_orders)
    assert compare_m120_m160(left, changed)["pass"] is False
    assert compare_m120_m160(left, replace(right, mpi_size=1))["pass"] is False
    assert compare_m120_m160(left, replace(right, requested_modes=121))["pass"] is False
    mismatch = replace(right, mode_keys={"bottom": (), "top": right.mode_keys["top"]})
    assert compare_m120_m160(left, mismatch)["pass"] is False
    fields = dict(cases["full3d"].payload)
    fields["E_V_per_m"] = fields["E_V_per_m"].copy()
    fields["E_V_per_m"][2, 0, 0, 0] = 2.0 + 0.0j
    bad_field = replace(cases["full3d"], payload=fields)
    assert compare_hybrid_full3d(left, bad_field)["pass"] is False
    assert (
        compare_hybrid_full3d(left, replace(cases["full3d"], mpi_size=1))["pass"]
        is False
    )
    shifted_coordinates = dict(cases["direct160"].payload)
    shifted_coordinates["x_nm"] = shifted_coordinates["x_nm"].copy()
    shifted_coordinates["x_nm"][0] += 1.0
    shifted = replace(cases["direct160"], payload=shifted_coordinates)
    assert compare_m120_m160(left, shifted)["pass"] is False
