"""Small reader-identity tests for the separately bound P8 execution retry."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity import (
    compare_round1_candidate,
    h100_anchor,
    round1_candidates,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs/task43_hp_adaptivity/outcomes/records/v16_r9_p8_contract.json"
RECOVERY_PATH = ROOT / round1_candidates._V18_P8_EXECUTION_RECOVERY_REL
COMPARISON_RECOVERY_PATH = ROOT / round1_candidates._V18_P8_COMPARISON_RECOVERY_REL
RUNTIME_IDENTITY_PATH = Path(
    os.environ.get("TASK43_V11_ATTEMPT_ROOT", "/tmp")
) / "v18_runtime_identity.json"


def _check_live_t_worker_identity() -> dict:
    saved = json.loads(RUNTIME_IDENTITY_PATH.read_text(encoding="utf-8"))
    return h100_anchor._require_v11_watchdog_worker_identity(
        require_unused_phase_file=False,
        expected_identity=saved["v11_watchdog_worker_identity"],
    )


def test_00_v18_t_records_live_runtime_abi_affinity_parent_and_trace() -> None:
    """First T test records the actual pytest worker's qualified execution envelope."""

    from mpi4py import MPI

    runtime = h100_anchor._check_v11_runtime_envelope(MPI.COMM_WORLD)
    identity = h100_anchor._require_v11_watchdog_worker_identity(
        require_unused_phase_file=False
    )
    attempt_root = Path(os.environ["TASK43_V11_ATTEMPT_ROOT"])
    record = {
        "schema": "task43.v18.p8.runtime-identity.v1",
        "phase": "T",
        "runtime_envelope": runtime,
        "v11_watchdog_worker_identity": identity,
        "identity_ledger": {
            "first_check": "_check_v11_runtime_envelope",
            "subsequent_check_policy": "require_unused_phase_file=False",
            "worker_pid": os.getpid(),
            "watchdog_pid": identity["watchdog_pid"],
            "tracer_pid": identity["tracer_pid"],
            "phase_path": identity["phase_path"],
        },
    }
    tmp = RUNTIME_IDENTITY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, RUNTIME_IDENTITY_PATH)
    assert runtime["mpi_size"] == 1
    assert runtime["petsc_scalar_type"] == "<class 'numpy.complex128'>"
    assert identity["direct_watchdog_parent_verified"] is True
    assert identity["tracer_descends_from_watchdog"] is True
    assert identity["worker_tid_affinities"]
    assert all(item["cpu_list"] == [1] for item in identity["worker_tid_affinities"])


def test_01_v18_t_fixture_checks_reuse_the_live_worker_identity() -> None:
    _check_live_t_worker_identity()


def test_02_v18_current_manifest_t_reader_binds_51_sources_and_contract() -> None:
    contract, contract_sha256 = round1_candidates._load_v16_p8_contract(
        CONTRACT_PATH
    )
    recovery = round1_candidates._load_v18_p8_execution_recovery(
        RECOVERY_PATH,
        contract=contract,
        contract_sha256=contract_sha256,
        phase="T",
    )
    current_source = recovery["source_binding"]["current_source_sha256"]
    expected_source = {
        **round1_candidates._v11_source_snapshot(),
        CONTRACT_PATH.relative_to(ROOT).as_posix(): contract_sha256,
    }
    assert current_source == expected_source
    assert len(current_source) == 51
    assert contract_sha256 == "8305bc7bbef3dfc33145a9032a9ce7628b3648f43b4900a982c4b0528f38bc1b"
    assert contract["authority"]["review_commit"] == "f72e1c8d031de7acc374f0806ddac06099c461c4"


@pytest.mark.parametrize("order", ["q8", "q10"])
def test_v18_p5_h8_candidate_label_allows_only_historical_alias(order: str) -> None:
    """Exercise the exact saved P5 field consumed by the real comparison loop."""

    contract, _ = round1_candidates._load_v16_p8_contract(CONTRACT_PATH)
    roles = {item["role"]: item for item in contract["inputs"]}
    p5_path = ROOT / roles["V15_P5_comparison_record"]["path"]
    p5 = json.loads(p5_path.read_text(encoding="utf-8"))
    saved = p5["results"][order]["R9_H8"]
    assert saved["modal_metrics"]["candidate_label"] == "v11_r9_h8"

    canonical = copy.deepcopy(saved)
    canonical["modal_metrics"]["candidate_label"] = "R9_H8"
    compare_round1_candidate._v16_require_saved_p5_candidate_metrics_match(
        saved,
        canonical,
        candidate_label="R9_H8",
        context=f"P5.{order}.R9_H8",
    )

    unknown_alias = copy.deepcopy(saved)
    unknown_alias["modal_metrics"]["candidate_label"] = "v11_h8_unapproved"
    with pytest.raises(ValueError, match=f"P5\\.{order}\\.R9_H8.modal_metrics.candidate_label"):
        compare_round1_candidate._v16_require_saved_p5_candidate_metrics_match(
            unknown_alias,
            canonical,
            candidate_label="R9_H8",
            context=f"P5.{order}.R9_H8",
        )

    numeric_mismatch = copy.deepcopy(canonical)
    numeric_mismatch["eta"] = float(numeric_mismatch["eta"]) + 1.0e-6
    with pytest.raises(ValueError, match=f"P5\\.{order}\\.R9_H8.eta"):
        compare_round1_candidate._v16_require_saved_p5_candidate_metrics_match(
            saved,
            numeric_mismatch,
            candidate_label="R9_H8",
            context=f"P5.{order}.R9_H8",
        )


def _load_current_c_recovery():
    contract, contract_sha256 = round1_candidates._load_v16_p8_contract(
        CONTRACT_PATH
    )
    recovery = round1_candidates._load_v18_p8_execution_recovery(
        RECOVERY_PATH,
        contract=contract,
        contract_sha256=contract_sha256,
        phase="C",
        comparison_recovery_path=COMPARISON_RECOVERY_PATH,
    )
    return contract, contract_sha256, recovery


def test_v18_c_recovery_uses_actual_comparison_and_historical_f_readers() -> None:
    _, contract_sha256, recovery = _load_current_c_recovery()
    frozen = compare_round1_candidate._v16_p8_frozen_endpoint(
        CONTRACT_PATH,
        ROOT / "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json",
        execution_recovery_path=RECOVERY_PATH,
        comparison_recovery_path=COMPARISON_RECOVERY_PATH,
    )
    assert recovery["selected_phase"] == "C"
    assert frozen["contract_sha256"] == contract_sha256
    assert frozen["source_id"] == "S_MAIN"
    assert frozen["comparison_recovery"]["root"] == recovery[
        "comparison_recovery"
    ]["root"]
    assert frozen["source_snapshot"] == recovery["comparison_recovery"][
        "source_binding"
    ]["current_source_sha256"]
    assert frozen["historical_source_snapshot"] == recovery["source_binding"][
        "current_source_sha256"
    ]


def test_v18_c_recovery_actual_reader_rejects_unapproved_source_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract, contract_sha256 = round1_candidates._load_v16_p8_contract(
        CONTRACT_PATH
    )
    original = round1_candidates._v11_source_snapshot

    def with_unapproved_delta() -> dict[str, str]:
        changed = original()
        changed["benchmarks/subreaper_watchdog.py"] = "0" * 64
        return changed

    monkeypatch.setattr(
        round1_candidates, "_v11_source_snapshot", with_unapproved_delta
    )
    with pytest.raises(ValueError, match="C-only recovery source delta"):
        round1_candidates._load_v18_p8_execution_recovery(
            RECOVERY_PATH,
            contract=contract,
            contract_sha256=contract_sha256,
            phase="C",
            comparison_recovery_path=COMPARISON_RECOVERY_PATH,
        )


def test_v18_q8_recovery_reads_bound_archive_without_sampling_or_copying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract, contract_sha256, recovery = _load_current_c_recovery()
    roles = {item["role"]: item for item in contract["inputs"]}
    p5_path = (ROOT / roles["V15_P5_q8_union_npz"]["path"]).resolve()
    with np.load(p5_path, allow_pickle=False) as archive:
        p5_sample = json.loads(
            np.asarray(archive["__task43_record_json__"], dtype=np.uint8)
            .tobytes()
            .decode("utf-8")
        )
        points = np.asarray(archive["points_nm"], dtype=np.float64).copy()
        weights = np.asarray(archive["weights_nm3"], dtype=np.float64).copy()
    q8_path = Path(recovery["comparison_recovery"]["q8_sample_path"])
    with np.load(q8_path, allow_pickle=False) as archive:
        saved = json.loads(
            np.asarray(archive["__task43_record_json__"], dtype=np.uint8)
            .tobytes()
            .decode("utf-8")
        )
    monkeypatch.setattr(
        compare_round1_candidate,
        "_sample_field",
        lambda *_args, **_kwargs: pytest.fail("q8 restoration sampler was called"),
    )
    loaded = compare_round1_candidate._v18_load_preserved_q8_sample(
        q8_path,
        expected_sha256=recovery["comparison_recovery"]["q8_sample_sha256"],
        contract_sha256=contract_sha256,
        f_terminal_sha256=saved["identity"]["F_terminal_sha256"],
        f_primary_packet_sha256=saved["identity"]["F_primary_packet_sha256"],
        p5_sample_path=p5_path,
        p5_sample_sha256=roles["V15_P5_q8_union_npz"]["sha256"],
        points=points,
        weights=weights,
        candidate_identity=saved["identity"]["candidate_identity"],
        mesh_identity=saved["identity"]["mesh_identity"],
    )
    assert loaded["npz_path"] == str(q8_path.resolve())
    assert loaded["npz_sha256"] == recovery["comparison_recovery"]["q8_sample_sha256"]
    assert loaded["record"]["identity"]["P8_sampled_once"] is True
    assert p5_sample["identity"]["quadrature_order"] == 8
    with pytest.raises(ValueError, match="mixed or unexpected identity"):
        compare_round1_candidate._v18_load_preserved_q8_sample(
            q8_path,
            expected_sha256=recovery["comparison_recovery"]["q8_sample_sha256"],
            contract_sha256=contract_sha256,
            f_terminal_sha256="0" * 64,
            f_primary_packet_sha256=saved["identity"]["F_primary_packet_sha256"],
            p5_sample_path=p5_path,
            p5_sample_sha256=roles["V15_P5_q8_union_npz"]["sha256"],
            points=points,
            weights=weights,
            candidate_identity=saved["identity"]["candidate_identity"],
            mesh_identity=saved["identity"]["mesh_identity"],
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return _sha256(path)


@pytest.fixture
def v18_reader_package(monkeypatch: pytest.MonkeyPatch):
    """Build a small on-disk S/F handoff consumed by the real F and C readers."""

    contract, contract_sha256 = round1_candidates._load_v16_p8_contract(
        CONTRACT_PATH
    )
    artifact_prefix = Path(contract["artifact_prefix"]).resolve()
    with tempfile.TemporaryDirectory(
        prefix=".v18_reader_fixture_", dir=artifact_prefix / "preparation"
    ) as fixture_name:
        fixture_root = Path(fixture_name)
        relative_base = fixture_root.relative_to(artifact_prefix)
        old_phases = round1_candidates._V18_P8_PHASES
        phases = copy.deepcopy(old_phases)
        roots = {
            name: (relative_base / name).as_posix()
            for name in ("T", "S", "F", "C")
        }
        for name, phase in phases.items():
            phase["root"] = roots[name]
        monkeypatch.setattr(round1_candidates, "_V18_P8_PHASES", phases)
        monkeypatch.setattr(
            round1_candidates,
            "_V18_P8_EXECUTION_RECOVERY_REL",
            fixture_root.relative_to(ROOT) / "execution_recovery.json",
        )
        binding_path = ROOT / round1_candidates._V18_P8_EXECUTION_RECOVERY_REL
        binding_sha256 = _write_json(binding_path, {"fixture": "reader-only"})
        manifest_path = str(binding_path.resolve())
        source_head = "a" * 40
        launch_script_path = ROOT / "benchmarks/task43_hp_adaptivity/v18_p8_stage_launch.sh"
        launch_script_sha256 = _sha256(launch_script_path)
        test_refs = {}
        for key, filename in (
            ("tracked_summary", "tracked_summary.json"),
            ("test_terminal", "test_terminal.json"),
            ("test_qualification", "test_qualification.json"),
            ("test_root_observation", "test_root_observation.json"),
            ("runtime_identity", "runtime_identity.json"),
        ):
            path = fixture_root / "test_evidence" / filename
            digest = _write_json(path, {"fixture": key})
            test_refs[key] = {"path": str(path.resolve()), "sha256": digest}

        recovery = {
            "phases": phases,
            "manifest_path": manifest_path,
            "manifest_sha256": binding_sha256,
            "tracked_summary_path": test_refs["tracked_summary"]["path"],
            "tracked_summary_sha256": test_refs["tracked_summary"]["sha256"],
            "test_terminal_path": test_refs["test_terminal"]["path"],
            "test_terminal_sha256": test_refs["test_terminal"]["sha256"],
            "test_qualification_path": test_refs["test_qualification"]["path"],
            "test_qualification_sha256": test_refs["test_qualification"]["sha256"],
            "test_root_observation_path": test_refs["test_root_observation"]["path"],
            "test_root_observation_sha256": test_refs["test_root_observation"]["sha256"],
            "runtime_identity_path": test_refs["runtime_identity"]["path"],
            "runtime_identity_sha256": test_refs["runtime_identity"]["sha256"],
            "launch_script_path": str(launch_script_path.resolve()),
            "launch_script_sha256": launch_script_sha256,
            "frozen_protocol": {"contract": {"sha256": contract_sha256}},
        }

        def load_recovery(_path, *, contract, contract_sha256, phase):
            assert contract_sha256 == _sha256(CONTRACT_PATH)
            assert contract["artifact_prefix"] == str(artifact_prefix)
            result = copy.deepcopy(recovery)
            result["selected_phase"] = phase
            return result

        monkeypatch.setattr(
            round1_candidates, "_load_v18_p8_execution_recovery", load_recovery
        )
        s_root = artifact_prefix / roots["S"]
        f_root = artifact_prefix / roots["F"]

        plan_path = s_root / "plan_output/plans/v16_r9_p8.json"
        audit_path = s_root / "plan_output/plans/v16_r9_p8.audit.json"
        bundle_path = s_root / "plan_output/plan_audit.json"
        joined_path = s_root / "v18_p8_space_joined_terminal.json"
        plan_sha = _write_json(
            plan_path,
            {
                "task43_candidate": {
                    "candidate_id": "v16_r9_p8",
                    "provenance": {"v16_contract_sha256": contract_sha256},
                }
            },
        )
        audit_sha = _write_json(
            audit_path,
            {
                "actual_space_gate": {"pass": True},
                "saved_p5_geometry_gate": {"pass": True},
                "forest": {},
                "degrees": {},
                "dofs": {},
                "space_authority_detail": {},
                "actual_geometry": {},
            },
        )
        bundle_sha = _write_json(
            bundle_path,
            {
                "pass": True,
                "pde_matrix_constructed": False,
                "factorization_performed": False,
                "solve_performed": False,
            },
        )
        observation_path = s_root / "root_observation.json"
        observation_sha = _write_json(observation_path, {"fixture": "root observation"})
        gates = {}
        for name in ("source", "input", "resource", "trace", "space", "old_samples"):
            evidence_path = s_root / "gate_evidence" / f"{name}.json"
            evidence_sha = _write_json(evidence_path, {"gate": name, "pass": True})
            gates[name] = {
                "pass": True,
                "evidence": {"path": str(evidence_path.resolve()), "sha256": evidence_sha},
            }
        watchdog_summary_path = s_root / "watchdog/summary.json"
        _write_json(
            watchdog_summary_path,
            {
                "classification": "COMPLETED",
                "leader_exit_code": 0,
                "descendants_cleared": True,
                "remaining_child_pids": [],
            },
        )
        (s_root / "launcher_exit_code.txt").write_text("0\n", encoding="ascii")
        (s_root / "watchdog_exit_code.txt").write_text("0\n", encoding="ascii")
        (s_root / "source_head.txt").write_text(source_head + "\n", encoding="ascii")
        _write_json(
            joined_path,
            {
                "schema": "task43.v16.p8-space-root-joined-terminal.v1",
                "status": "S_COMPLETE_ROOT_VERIFIED",
                "space_source_id": "S_MAIN",
                "contract_sha256": contract_sha256,
                "review_commit": "f72e1c8d031de7acc374f0806ddac06099c461c4",
                "launcher_exit_code": 0,
                "watchdog_exit_code": 0,
                "worker_exit_code": 0,
                "descendants_cleared": True,
                "remaining_child_pids": [],
                "products": {
                    "plan": {"path": str(plan_path.resolve()), "sha256": plan_sha},
                    "audit": {"path": str(audit_path.resolve()), "sha256": audit_sha},
                    "bundle": {"path": str(bundle_path.resolve()), "sha256": bundle_sha},
                },
                "gates": gates,
                "root_observation_record": {
                    "path": str(observation_path.resolve()),
                    "sha256": observation_sha,
                },
                "source_head": source_head,
                "execution_recovery_binding": {
                    "path": manifest_path,
                    "sha256": binding_sha256,
                    "phase": "S",
                },
            },
        )

        source_snapshot = h100_anchor._v11_source_snapshot()
        source_snapshot[CONTRACT_PATH.relative_to(ROOT).as_posix()] = contract_sha256
        source_entries = [
            {
                "path": name,
                "sha256": digest,
                "snapshot": str((ROOT / name).resolve()),
            }
            for name, digest in sorted(source_snapshot.items())
        ]
        contract_inputs = {
            str((ROOT / item["path"]).resolve()): item["sha256"]
            for item in contract["inputs"]
        }
        contract_inputs[str(CONTRACT_PATH.resolve())] = contract_sha256
        contract_inputs.update(
            {
                test_refs[name]["path"]: test_refs[name]["sha256"]
                for name in test_refs
            }
        )
        contract_inputs[recovery["launch_script_path"]] = launch_script_sha256
        contract_inputs.update(
            {
                str((ROOT / name).resolve()): digest
                for name, digest in source_snapshot.items()
            }
        )
        required_s_paths = [
            plan_path,
            audit_path,
            bundle_path,
            joined_path,
            watchdog_summary_path,
            s_root / "launcher_exit_code.txt",
            s_root / "watchdog_exit_code.txt",
            s_root / "source_head.txt",
            binding_path,
            observation_path,
            *[Path(gate["evidence"]["path"]) for gate in gates.values()],
            launch_script_path,
        ]
        recovery_input_paths = [
            Path(recovery[key])
            for key in (
                "tracked_summary_path",
                "test_terminal_path",
                "test_qualification_path",
                "test_root_observation_path",
                "runtime_identity_path",
            )
        ]
        input_snapshot = dict(contract_inputs)
        for path in [*required_s_paths, *recovery_input_paths]:
            input_snapshot[str(path.resolve())] = _sha256(path)

        launch_script_identity = {
            "path": str(launch_script_path.resolve()),
            "sha256": launch_script_sha256,
        }
        s_launch_path = s_root / "snapshots/launch_manifest.json"
        _write_json(
            s_launch_path,
            {
                "contract_sha256": contract_sha256,
                "space_source_id": "S_MAIN",
                "head": source_head,
                "source": source_entries,
                "inputs": [
                    {"path": path, "sha256": digest}
                    for path, digest in sorted(input_snapshot.items())
                ],
                "launch_script": launch_script_identity,
                "execution_recovery_binding": {
                    "path": manifest_path,
                    "sha256": binding_sha256,
                    "phase": "S",
                },
            },
        )
        input_snapshot[str(s_launch_path.resolve())] = _sha256(s_launch_path)
        f_launch_path = f_root / "snapshots/launch_manifest.json"
        _write_json(
            f_launch_path,
            {
                "contract_sha256": contract_sha256,
                "space_source_id": "S_MAIN",
                "head": source_head,
                "source": source_entries,
                "inputs": [
                    {"path": path, "sha256": digest}
                    for path, digest in sorted(input_snapshot.items())
                ],
                "launch_script": launch_script_identity,
                "execution_recovery_binding": {
                    "path": manifest_path,
                    "sha256": binding_sha256,
                    "phase": "F",
                },
            },
        )
        yield {
            "contract_sha256": contract_sha256,
            "binding_path": binding_path,
            "binding_sha256": binding_sha256,
            "f_root": f_root,
            "run_root": f_root / "run",
            "s_root": s_root,
            "launch_script_identity": launch_script_identity,
        }


def test_v18_f_reader_accepts_disk_bound_s_package(v18_reader_package) -> None:
    result = h100_anchor._load_v16_p8_context(
        CONTRACT_PATH,
        source_id="S_MAIN",
        run_root=v18_reader_package["run_root"],
        execution_recovery_path=v18_reader_package["binding_path"],
    )
    contract, contract_sha256, source_binding = result
    assert contract_sha256 == v18_reader_package["contract_sha256"]
    assert source_binding["space_source_id"] == "S_MAIN"
    assert Path(source_binding["joined_terminal_path"]).is_file()
    assert source_binding["execution_recovery_binding"]["phase"] == "F"
    assert contract["authority"]["review_commit"] == "f72e1c8d031de7acc374f0806ddac06099c461c4"


def test_v18_c_reader_accepts_bound_handoff_then_rejects_mixed_binding(
    v18_reader_package,
) -> None:
    good = compare_round1_candidate._v16_p8_frozen_endpoint
    with pytest.raises(FileNotFoundError, match="complete root-joined F product set"):
        good(
            CONTRACT_PATH,
            ROOT / "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json",
            execution_recovery_path=v18_reader_package["binding_path"],
        )

    launch_path = v18_reader_package["f_root"] / "snapshots/launch_manifest.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["execution_recovery_binding"]["phase"] = "S"
    _write_json(launch_path, launch)
    with pytest.raises(ValueError, match="another execution recovery binding"):
        good(
            CONTRACT_PATH,
            ROOT / "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json",
            execution_recovery_path=v18_reader_package["binding_path"],
        )


@pytest.mark.parametrize(
    ("mode", "signum"),
    [
        ("normal", None),
        ("term", signal.SIGTERM),
        ("int", signal.SIGINT),
        ("hup", signal.SIGHUP),
        ("prewatchdog_nonzero", None),
        ("missing_summary", None),
    ],
)
def test_v18_detached_watchdog_signal_lifecycle_records_terminal(
    tmp_path: Path, mode: str, signum: int | None
) -> None:
    script = ROOT / "benchmarks/task43_hp_adaptivity/v18_p8_stage_launch.sh"
    fixture_root = tmp_path / mode
    process = subprocess.Popen(
        ["bash", str(script), "--lifecycle-fixture", str(fixture_root), mode],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        ready = fixture_root / "fixture_ready.json"
        resources = fixture_root / "watchdog/resources.jsonl"
        deadline = time.monotonic() + 15.0
        needs_resource_sample = mode != "prewatchdog_nonzero"
        while (
            (not ready.is_file() or (needs_resource_sample and (not resources.is_file() or resources.stat().st_size == 0)))
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert ready.is_file(), "fixture launcher did not publish its bound child identity"
        if needs_resource_sample:
            assert resources.is_file() and resources.stat().st_size, (
                "watchdog did not install handlers and begin resource sampling"
            )
        if signum is not None:
            os.kill(process.pid, signum)
        code = process.wait(timeout=30.0)
        lifecycle = json.loads(
            (fixture_root / "launcher_exit.json").read_text(encoding="utf-8")
        )
        stage_terminal = json.loads(
            (fixture_root / "stage_terminal.json").read_text(encoding="utf-8")
        )
        if mode == "normal":
            summary = json.loads(
                (fixture_root / "watchdog/summary.json").read_text(encoding="utf-8")
            )
            assert code == 0
            assert lifecycle["classification"] == "COMPLETED"
            assert lifecycle["watchdog_exit_code"] == 0
            assert summary["classification"] == "COMPLETED"
            assert summary["descendants_cleared"] is True
            assert summary["remaining_child_pids"] == []
        elif mode in {"term", "int", "hup"}:
            summary = json.loads(
                (fixture_root / "watchdog/summary.json").read_text(encoding="utf-8")
            )
            assert code == 128 + signum
            assert lifecycle["received_signal"] == mode.upper()
            assert lifecycle["watchdog_exit_code"] == 2
            assert summary["classification"] == "USER_CONTROLLED_STOP"
            assert summary["descendants_cleared"] is True
            assert summary["remaining_child_pids"] == []
        else:
            expected_watchdog_exit = 23 if mode == "prewatchdog_nonzero" else 0
            assert code != 0
            assert lifecycle["classification"] == "INCOMPLETE"
            assert stage_terminal["classification"] == "INCOMPLETE"
            assert lifecycle["launcher_exit_code"] == code
            assert stage_terminal["launcher_exit_code"] == code
            assert lifecycle["watchdog_exit_code"] == expected_watchdog_exit
            assert stage_terminal["watchdog_exit_code"] == expected_watchdog_exit
            assert lifecycle["cleanup_pass"] is False
            assert lifecycle["summary_pass"] is False
            assert stage_terminal["watchdog_summary"] is None
    finally:
        if process.poll() is None:
            try:
                os.kill(process.pid, signal.SIGTERM)
                process.wait(timeout=15.0)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    process.wait(timeout=15.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5.0)
