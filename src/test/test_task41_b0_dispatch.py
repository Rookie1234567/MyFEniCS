from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from src.geometry.task41_phi90_profile import (
    TASK41_B0_COMPARISON_GROUP,
    TASK41_B0_GEOMETRY_IDENTITY,
    TASK41_B0_PRECONDITIONER,
    TASK41_B0_RUN_ID,
    task41_payload_errors,
)
from src.runners.task41_p0_contract import (
    TASK41_B0_BOOTSTRAP_TREATMENT,
    TASK41_B0_CONTROLLER_RELATIVE,
    TASK41_B0_INPUT_RELATIVE,
    TASK41_B0_SERVICE_RELATIVE,
    TASK41_B0_T0_BASIS,
    TASK41_B0_T0_SOURCE_SHA,
    TASK41_B0_T0_UTC,
    TASK41_B0_WINDOW_RELATIVE,
    TASK41_BRANCH,
    TASK41_CLOSEOUT_SECONDS,
    TASK41_HOST_RESERVE_BYTES,
    TASK41_MODEL_ID,
    TASK41_NUMERICAL_SECONDS,
    TASK41_P0_CONTRACT_SCHEMA,
    TASK41_P0_WINDOW_SCHEMA,
    TASK41_TASK_MEMORY_MAX_BYTES,
    TASK41_TOTAL_SECONDS,
    contract_relative_path,
)
from src.runners.task40_v10_campaign import _utc_ns
from src.runners.workflow_timebase import clock_sample
from src.io.execution_plan import resolved_config_bytes
from src.io.input_validation import load_and_resolve


def _utc_z(nanoseconds: int) -> str:
    seconds, fraction = divmod(nanoseconds, 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds)) + f".{fraction:09d}Z"


def test_task41_b0_diagnostic_grid_keys_are_separate_from_official_port_count(tmp_path):
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.task40_v10_worker import (
        _single_side_diffraction_order_count_passed,
        _task41_b0_diagnostic_mode_keys,
    )

    repository_input = Path(__file__).resolve().parents[2] / TASK41_B0_INPUT_RELATIVE
    specification = load_and_resolve(repository_input)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    diagnostic_keys = _task41_b0_diagnostic_mode_keys(cfg)
    assert len(diagnostic_keys) == 17 * 17 * 2 == 578

    rows_path = tmp_path / "diffraction_orders_3d.json"
    rows = [
        {"m": m, "n": n, "polarization": polarization}
        for m, n, polarization in sorted(diagnostic_keys)
    ]
    rows_path.write_text(
        json.dumps(
            {
                "metrics": {"diffraction_channel_count": len(rows)},
                "orders": rows,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = {
        "diffraction_channel_count": len(rows),
        "diffraction_metrics": {
            "diffraction_channel_count": len(rows),
            "diffraction_orders_json": str(rows_path),
        },
    }
    assert _single_side_diffraction_order_count_passed(
        output, 64_120, diagnostic_mode_keys=diagnostic_keys
    )
    assert not _single_side_diffraction_order_count_passed(output, 64_120)

    rows.pop()
    rows_path.write_text(
        json.dumps({"metrics": {"diffraction_channel_count": 578}, "orders": rows})
        + "\n",
        encoding="utf-8",
    )
    assert not _single_side_diffraction_order_count_passed(
        output, 64_120, diagnostic_mode_keys=diagnostic_keys
    )


def test_task41_b0_carrier_upper_bound_counts_two_pairs_slave_rows_and_full_vector():
    from src.runners.task40_v10_worker import _task41_b0_carrier_memory_upper_bound

    class Connectivity:
        def __init__(self, links):
            self._links = links

        def links(self, index):
            return np.asarray(self._links[index], dtype=np.int32)

    class Topology:
        def __init__(self):
            self._facet_to_cell = Connectivity({0: [0], 1: [1]})
            self._cell_to_facet = Connectivity({0: [0], 1: [1]})

        def create_connectivity(self, *_args):
            return None

        def connectivity(self, dim0, dim1):
            return self._facet_to_cell if (dim0, dim1) == (2, 3) else self._cell_to_facet

        def index_map(self, _dim):
            return SimpleNamespace(size_local=2)

    topology = Topology()
    mesh = SimpleNamespace(topology=topology)
    dof_index_map = SimpleNamespace(size_local=6, num_ghosts=2)
    space = SimpleNamespace(
        element=SimpleNamespace(
            basix_element=SimpleNamespace(
                entity_closure_dofs={2: (np.asarray([0, 1]), np.asarray([0, 1]))}
            )
        ),
        dofmap=SimpleNamespace(
            index_map=dof_index_map,
            index_map_bs=1,
            cell_dofs=lambda cell: np.asarray(
                (3 * cell, 3 * cell + 1, 3 * cell + 2), dtype=np.int32
            ),
        ),
    )
    mesh_data = SimpleNamespace(
        mesh=mesh,
        facet_tags=SimpleNamespace(find=lambda tag: (0,) if tag == 1 else (1,)),
    )
    mpc = SimpleNamespace(slaves=np.asarray([1, 3, 7], dtype=np.int32))
    setup = {
        "mesh_data": mesh_data,
        "spaces": [None] * 6 + [space],
        "floquets": [None] * 6 + [SimpleNamespace(mpc=mpc)],
    }
    cfg = SimpleNamespace(tags=SimpleNamespace(z_min=1, z_max=2))
    modes = (
        SimpleNamespace(side="bottom"),
        SimpleNamespace(side="top"),
        SimpleNamespace(side="top"),
    )

    bound = _task41_b0_carrier_memory_upper_bound(setup, cfg, modes)

    assert bound["boundary_trace_dof_count_by_side"] == {"bottom": 2, "top": 2}
    assert bound["sparse_payload_bytes_per_row_per_mode"] == 2 * (8 + 16)
    assert bound["canonical_carrier_payload_upper_bytes"] == 288
    assert bound["fullspace_mpc_owned_slave_row_count_upper"] == 2
    assert bound["fullspace_mpc_slave_rows_retained_upper_bytes"] == 16
    assert bound["fullspace_mpc_slave_constructor_peak_upper_bytes"] == 48
    assert bound["owned_full_vector_row_count"] == 6
    assert bound["ghost_full_vector_row_count_upper"] == 2
    assert bound["full_vector_scan_gather_workspace_upper_bytes"] == 64 * 8
    assert bound["component_sort_workspace_upper_bytes"] == 8 * 2 * (8 + 16)
    assert bound["component_workspace_upper_bytes"] == 512 * 1024**2 + 8 * 2 * (8 + 16)
    assert "not a measured payload" in bound["support_basis"]
    assert bound["measurement_status"] == "not_a_measured_process_memory_peak"


def _dispatch_fixture(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], str]:
    import src.runners.task41_p0_contract as contract_module

    source_sha = "c" * 40
    input_path = root / TASK41_B0_INPUT_RELATIVE
    input_path.parent.mkdir(parents=True)
    repository_input = Path(__file__).resolve().parents[2] / TASK41_B0_INPUT_RELATIVE
    shutil.copyfile(repository_input, input_path)
    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    assert task41_payload_errors(payload) == []

    runtime = root / "qualified-runtime"
    python_path = runtime / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o755)
    abi_receipt = root / "abi_receipt.json"
    abi_receipt.write_text(
        json.dumps(
            {
                "status": "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION",
                "runtime_profile": "native_linux",
                "prefix": str(runtime.resolve()),
                "PETSc": {"scalar_dtype": "complex128", "int_dtype": "int32"},
                "MPI": {"size": 1, "rank": 0},
            }
        ),
        encoding="utf-8",
    )
    jit_cache = root / "jit-cache"
    jit_cache.mkdir()

    anchor = clock_sample(include_boot_id=True)
    t0_ns = _utc_ns(TASK41_B0_T0_UTC)
    bootstrap = (int(anchor["utc_ns"]) - t0_ns) / 1.0e9
    window_payload = {
        "schema": TASK41_P0_WINDOW_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "source_sha": TASK41_B0_T0_SOURCE_SHA,
        "t0_utc": TASK41_B0_T0_UTC,
        "numerical_deadline_utc": _utc_z(
            t0_ns + int(TASK41_NUMERICAL_SECONDS * 1_000_000_000)
        ),
        "deadline_utc": _utc_z(t0_ns + int(TASK41_TOTAL_SECONDS * 1_000_000_000)),
        "total_seconds": TASK41_TOTAL_SECONDS,
        "numerical_seconds": TASK41_NUMERICAL_SECONDS,
        "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
        "anchor": anchor,
        "accounting_path": str(
            (root / TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v10.jsonl").resolve()
        ),
        "t0_basis": TASK41_B0_T0_BASIS,
        "bootstrap_utc_elapsed_seconds": bootstrap,
        "bootstrap_boottime_elapsed_seconds": None,
        "bootstrap_time_treatment": TASK41_B0_BOOTSTRAP_TREATMENT,
    }
    window_path = root / TASK41_B0_WINDOW_RELATIVE
    window_path.parent.mkdir(parents=True)
    window_path.write_text(
        json.dumps(window_payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    window_sha = hashlib.sha256(window_path.read_bytes()).hexdigest()
    resolved_sha = hashlib.sha256(resolved_config_bytes(specification)).hexdigest()
    contract = {
        "schema": TASK41_P0_CONTRACT_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "branch": TASK41_BRANCH,
        "source": {"sha": source_sha},
        "case": {
            "input_path": str(TASK41_B0_INPUT_RELATIVE),
            "input_sha256": specification.input_sha256,
            "model_id": specification.identity["model_id"],
            "run_id": specification.identity["run_id"],
            "physical_model_sha256": specification.physical_model_sha256,
            "resolved_config_sha256": resolved_sha,
            "method": specification.method["kind"],
            "mpi_size": specification.execution["mpi_size"],
            "profile_identity": TASK41_B0_PRECONDITIONER,
            "solver_stage": "TASK41_B0",
            "comparison_group": TASK41_B0_COMPARISON_GROUP,
            "geometry_identity": TASK41_B0_GEOMETRY_IDENTITY,
        },
        "runtime": {
            "profile": "native_linux",
            "runtime_prefix": str(runtime),
            "abi_receipt_path": str(abi_receipt),
            "abi_receipt_sha256": hashlib.sha256(abi_receipt.read_bytes()).hexdigest(),
            "jit_cache": str(jit_cache),
            "mpi_ranks": 1,
            "math_threads": 1,
        },
        "window": {
            "path": str(TASK41_B0_WINDOW_RELATIVE),
            "sha256": window_sha,
            "entry_source_sha": TASK41_B0_T0_SOURCE_SHA,
        },
        "resources": {
            "task_memory_max_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
            "host_reserve_bytes": TASK41_HOST_RESERVE_BYTES,
            "memory_swap_max_bytes": 0,
        },
        "time": {
            "total_seconds": TASK41_TOTAL_SECONDS,
            "numerical_seconds": TASK41_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
        },
        "evidence": {
            "service_directory": str(
                root / TASK41_B0_SERVICE_RELATIVE / f"service_source_{source_sha}"
            ),
        },
    }
    contract_path = root / contract_relative_path(source_sha, "B0")
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(
        json.dumps(contract, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        contract_module,
        "_git",
        lambda _root, *args: (
            source_sha
            if args == ("rev-parse", "HEAD")
            else TASK41_BRANCH
            if args == ("branch", "--show-current")
            else ""
            if args == ("status", "--porcelain", "--untracked-files=normal")
            else (_ for _ in ()).throw(AssertionError(f"unexpected git query: {args}"))
        ),
    )
    for key, value in {
        "TASK41_P0_STRICT_EXECUTION": "1",
        "TASK41_P0_CONTRACT_PATH": str(contract_path.resolve()),
        "TASK41_P0_CONTRACT_SHA256": contract_sha,
        "TASK41_P0_EXECUTION_WINDOW_PATH": str(window_path.resolve()),
        "TASK41_P0_EXECUTION_WINDOW_SHA256": window_sha,
    }.items():
        monkeypatch.setenv(key, value)
    return payload, source_sha


def test_task41_b0_dispatch_binds_contract_and_preserves_mixed_reference_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.runners.task038_full3d_iterative as iterative
    import src.runners.task40_v10_worker as worker

    payload, source_sha = _dispatch_fixture(tmp_path, monkeypatch)
    original_binding = iterative._task41_b0_dispatch_binding
    monkeypatch.setattr(
        iterative,
        "_task41_b0_dispatch_binding",
        lambda data, *, source_sha: original_binding(
            data, source_sha=source_sha, current_root=tmp_path
        ),
    )
    calls: list[dict[str, Any]] = []

    def capture_worker(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, "kwargs": kwargs})
        return {"passed": False, "status": "fixture_capture"}

    monkeypatch.setattr(worker, "run_task40_v10_p6_reference_worker", capture_worker)
    result = iterative.run_full3d_iterative(
        payload, tmp_path / "run", source_sha=source_sha
    )
    assert result["status"] == "fixture_capture"
    assert len(calls) == 1
    call = calls[0]["kwargs"]
    binding = call["task41_contract_binding"]
    assert binding["case_id"] == "B0"
    assert binding["source_sha"] == source_sha
    assert binding["input_sha256"] == payload["provenance"]["input_sha256"]
    assert binding["comparison_binding"] is None
    assert call["profile_identity"] == TASK41_B0_PRECONDITIONER
    assert call["share_transform_bank"] is True
    assert worker._include_mixed_fe_port_reference_cases(
        route_contract=None, task41_p0_iterative=True
    ) is True


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("geometry", "grating_width_y_nm", 21.0),
        ("materials", "n_grating", [1.0, 0.0]),
        ("geometry", "cell_notch", {"width_nm": 1.0}),
    ],
)
def test_task41_b0_dispatch_rejects_modified_physical_inputs_before_worker(
    section: str, key: str, value: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.runners.task038_full3d_iterative as iterative
    import src.runners.task40_v10_worker as worker

    payload, source_sha = _dispatch_fixture(tmp_path, monkeypatch)
    payload[section][key] = value
    calls: list[bool] = []
    monkeypatch.setattr(
        worker,
        "run_task40_v10_p6_reference_worker",
        lambda *_args, **_kwargs: calls.append(True),
    )
    with pytest.raises(ValueError, match="dispatcher rejected input"):
        iterative.run_full3d_iterative(payload, tmp_path / "run", source_sha=source_sha)
    assert calls == []


def _b0_inventory_fixture(
    run_directory: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    source_sha: str,
    input_sha256: str,
    contract_path: Path,
    contract_sha256: str,
    window_path: Path,
    window_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from src.solvers import task41_b0_mode_inventory as inventory_module

    # Synthetic persistence/checker fixture: these labels exercise the frozen
    # inventory shape and are not mode-generation evidence.
    q_counts = list(inventory_module.TASK41_B0_EXPECTED_Q_PORT_COUNTS)
    assert sum(q_counts) == inventory_module.TASK41_B0_MODE_COUNT
    sector_counts = [q_counts[t] + q_counts[t + 100] for t in range(100)]
    assert min(sector_counts) == 524 and max(sector_counts) == 816

    assignments = [q for q, count in enumerate(q_counts) for _ in range(count)]
    mode_manifest_bytes = ("[" + ",".join("0" for _ in assignments) + "]\n").encode()
    mode_sha256 = hashlib.sha256(mode_manifest_bytes).hexdigest()
    mode_identity = dict(inventory_module.TASK41_B0_MODE_MANIFEST_IDENTITIES[1])
    mode_identity.update(
        identity="task41_b0_fixture_mode_manifest_v1",
        manifest_sha256=mode_sha256,
        manifest_bytes=len(mode_manifest_bytes),
        mode_assignment_sha256_int16le=hashlib.sha256(
            np.asarray(assignments, dtype="<i2").tobytes(order="C")
        ).hexdigest(),
    )
    monkeypatch.setattr(
        inventory_module, "TASK41_B0_MODE_MANIFEST_IDENTITIES", (mode_identity,)
    )
    abi_facts = {
        "profile_identity": mode_identity["profile_identity"],
        "runtime_profile": mode_identity["runtime_profile"],
        "qualification": mode_identity["abi_qualification"],
        "receipt_sha256": mode_identity["abi_receipt_sha256"],
        "scalar": mode_identity["scalar"],
        "integer": mode_identity["integer"],
        "mpi_size": mode_identity["mpi_size"],
    }
    run_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = run_directory / "task41_b0_mode_manifest.json"
    manifest_path.write_bytes(mode_manifest_bytes)
    assignment_path = run_directory / "task41_b0_q_assignment.json"
    assignment_payload = {
        "schema": "task41.b0.q_assignment.v1",
        "source_sha": source_sha,
        "input_sha256": input_sha256,
        "mode_manifest_sha256": mode_sha256,
        "mode_manifest_bytes": len(mode_manifest_bytes),
        "mode_manifest_identity": mode_identity,
        "mode_assignment_sha256_int16le": mode_identity[
            "mode_assignment_sha256_int16le"
        ],
        "mode_count": len(assignments),
        "q_count": 200,
        "assignments": assignments,
    }
    assignment_bytes = (
        json.dumps(assignment_payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    assignment_path.write_bytes(assignment_bytes)
    facts = {
        "schema": "task41.b0.mode_q_inventory.v1",
        "status": "LIVE_PRODUCTION_MODE_MANIFEST_MATCH",
        "mode_count": len(assignments),
        "mode_manifest_sha256": mode_sha256,
        "mode_manifest_bytes": len(mode_manifest_bytes),
        "mode_manifest_identity": mode_identity,
        "mode_assignment_sha256_int16le": mode_identity[
            "mode_assignment_sha256_int16le"
        ],
        "q_count": 200,
        "q_port_counts": q_counts,
        "empty_q_indices": list(range(1, 58)),
        "active_q_count": 143,
        "sector_count": 100,
        "sector_port_counts": sector_counts,
        "profile_identity": TASK41_B0_PRECONDITIONER,
        "all_q_required": True,
        "all_sectors_nonempty": True,
        "fe_mesh_or_dofmap_built": False,
        "source_sha": source_sha,
        "input_sha256": input_sha256,
        "registered_abi_bound_identity_match": True,
        "mode_manifest_path": str(manifest_path),
        "mode_manifest_file_sha256": mode_sha256,
        "q_assignment_path": str(assignment_path),
        "q_assignment_file_sha256": hashlib.sha256(assignment_bytes).hexdigest(),
        "q_assignment_bytes": len(assignment_bytes),
        "persistence": "exclusive_create_no_replacement",
    }
    periodic = {
        "schema": "task41extra.b0_p6_periodic_profile.v1",
        "name": TASK41_B0_PRECONDITIONER,
        "q_count": 200,
        "mode_count": len(assignments),
        "q_port_counts": q_counts,
        "sector_port_counts": sector_counts,
    }
    summary = {
        "run_id": TASK41_B0_RUN_ID,
        "profile": TASK41_B0_PRECONDITIONER,
        "stage": "TASK41_B0",
        "source_sha": source_sha,
        "abi": abi_facts,
        "reference_pc_strategy": "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15",
        "q_assembly_strategy": "ROW_TILE_BOUNDED_CSR_V17",
        "factor_lifecycle_strategy": "ALL_Q_RESIDENT",
        "precision_status": "NOT_QUALIFIED",
        "mode_truncation_status": "MODE_TRUNCATION_UNQUALIFIED",
        "comparison_authority": None,
        "live_mode_inventory_status": "LIVE_CAPTURED_AND_HASH_VERIFIED",
        "b0_mode_inventory": facts,
        "periodic_inventory_expectations": periodic,
        "campaign_authority": {
            "case_id": "B0",
            "task41_contract_path": str(contract_path.resolve()),
            "task41_contract_sha256": contract_sha256,
            "source_sha": source_sha,
            "campaign_window_path": str(window_path.resolve()),
            "campaign_window_sha256": window_sha256,
        },
    }
    contract = {
        "source": {"sha": source_sha},
        "case": {
            "run_id": TASK41_B0_RUN_ID,
            "profile_identity": TASK41_B0_PRECONDITIONER,
            "solver_stage": "TASK41_B0",
            "comparison_group": TASK41_B0_COMPARISON_GROUP,
            "geometry_identity": TASK41_B0_GEOMETRY_IDENTITY,
            "method": "full3d_iterative",
            "input_sha256": input_sha256,
        },
        "window": {"path": str(window_path), "sha256": window_sha256},
        "runtime": {
            "profile": mode_identity["runtime_profile"],
            "abi_receipt_sha256": mode_identity["abi_receipt_sha256"],
        },
        "comparison": None,
        "q_csr_reuse": None,
    }
    return summary, contract


def test_task41_b0_checker_reopens_inventory_and_rejects_q_assignment_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.runners.task41_p0_checker import _task41_b0_numerical_checks

    contract_path = tmp_path / "execution_contract.json"
    contract_path.write_text("fixture contract", encoding="utf-8")
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    repo_root = tmp_path / "repo"
    window_path = repo_root / TASK41_B0_WINDOW_RELATIVE
    window_sha = "f" * 64
    summary, contract = _b0_inventory_fixture(
        repo_root / "run",
        monkeypatch=monkeypatch,
        source_sha="c" * 40,
        input_sha256="d" * 64,
        contract_path=contract_path,
        contract_sha256=contract_sha,
        window_path=window_path,
        window_sha256=window_sha,
    )
    checks = _task41_b0_numerical_checks(
        summary,
        repo_root / "run" / "numerical_output",
        contract,
        contract_path=contract_path,
        contract_sha256=contract_sha,
        repo_root=repo_root,
    )
    assert checks["passed"] is False  # The fixture intentionally has no FE/PDE outputs.
    assert checks["verified_profile_capability"]["verified"] is True
    assert checks["verified_profile_capability"]["q_count"] == 200
    assert checks["q_port_counts_recomputed"] == summary["b0_mode_inventory"]["q_port_counts"]

    assignment_path = Path(summary["b0_mode_inventory"]["q_assignment_path"])
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    assignment["assignments"][0] = 1
    assignment_path.write_text(json.dumps(assignment), encoding="utf-8")
    failed = _task41_b0_numerical_checks(
        summary,
        repo_root / "run" / "numerical_output",
        contract,
        contract_path=contract_path,
        contract_sha256=contract_sha,
        repo_root=repo_root,
    )
    assert failed["passed"] is False
    assert any("q-assignment" in error for error in failed["errors"])


def test_task41_b0_capability_reaches_both_v15_registry_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.runners.task41_p0_checker import _task41_b0_numerical_checks
    from src.runners.task40_v10_output_checker import (
        _registered_v15_profile_inventory as output_inventory,
    )
    from src.solvers.augmented_reference_correction import (
        _registered_v15_profile_inventory as solver_inventory,
    )

    contract_path = tmp_path / "execution_contract.json"
    contract_path.write_text("fixture contract", encoding="utf-8")
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    repo_root = tmp_path / "repo"
    window_path = repo_root / TASK41_B0_WINDOW_RELATIVE
    summary, contract = _b0_inventory_fixture(
        repo_root / "run",
        monkeypatch=monkeypatch,
        source_sha="c" * 40,
        input_sha256="d" * 64,
        contract_path=contract_path,
        contract_sha256=contract_sha,
        window_path=window_path,
        window_sha256="f" * 64,
    )
    checks = _task41_b0_numerical_checks(
        summary,
        repo_root / "run" / "numerical_output",
        contract,
        contract_path=contract_path,
        contract_sha256=contract_sha,
        repo_root=repo_root,
    )
    capability = checks["verified_profile_capability"]
    for registry in (solver_inventory, output_inventory):
        resolved = registry(
            TASK41_B0_PRECONDITIONER, b0_profile_capability=capability
        )
        assert resolved["q_count"] == 200
        assert resolved["mode_count"] == 64_120
        assert resolved["twist_count"] == 100
        invalid_count = {**capability, "mode_count": 64_119}
        with pytest.raises(ValueError, match="capability|allocation"):
            registry(
                TASK41_B0_PRECONDITIONER,
                b0_profile_capability=invalid_count,
            )
