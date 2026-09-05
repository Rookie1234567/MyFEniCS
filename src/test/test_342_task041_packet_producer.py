"""Focused Task041 mode-prep and dynamic selected-packet contracts."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks import run_task032_phase6_augmented
from benchmarks import task041_exact_side_workflow as workflow
from benchmarks.task039_v4_selected_mode_packet import (
    TASK039_V4_SELECTED_MODE_COUNT,
    TASK041_SELECTED_MODE_IDENTITY_SCHEMA,
    hydrate_task039_v4_selected_mode_packet,
    load_task039_v4_selected_mode_packet,
    task041_selected_mode_scope,
    write_task039_v4_selected_mode_packet,
)
from src.io.input_validation import load_and_resolve, task041_profile_errors
from src.io.resolved_config import resolved_config_sha256

ROOT = Path(__file__).resolve().parents[2]
TASK041_INPUT = ROOT / workflow.TASK041_INPUT


def test_task041_validated_payload_recomputes_complete_identity() -> None:
    specification = load_and_resolve(TASK041_INPUT)
    normalized = specification.as_jsonable()
    assert task041_profile_errors(normalized) == []
    resolved_sha = resolved_config_sha256(specification)
    identity = workflow.build_task041_packet_identity(
        specification,
        normalized,
        "a" * 40,
        resolved_sha,
    )
    assert identity["schema"] == TASK041_SELECTED_MODE_IDENTITY_SCHEMA
    assert identity["mode_count"] == TASK039_V4_SELECTED_MODE_COUNT
    assert identity["mpi_size"] == 1
    assert identity["scope"] == task041_selected_mode_scope(480, 1)
    assert identity["external_keys"]["count"] > 0
    assert len(identity["external_keys"]["sha256"]) == 64
    assert identity["model_id"].endswith("_m480")
    assert identity["run_id"] == "task041_5nm_p6h4_m480_mpi1"


def test_task041_identity_rejects_non_self_consistent_payload() -> None:
    specification = load_and_resolve(TASK041_INPUT)
    normalized = specification.as_jsonable()
    normalized["method"]["requested_modes_per_direction"] = 800
    with pytest.raises(workflow.Task041ModePrepError):
        workflow.build_task041_packet_identity(
            specification,
            normalized,
            "a" * 40,
            resolved_config_sha256(specification),
        )


def test_inner_mpi_environment_removes_only_job_binding_variables() -> None:
    environment = {
        "PATH": "/bin",
        "LD_LIBRARY_PATH": "/lib",
        "PYTHONPATH": "/src",
        "MYFENICS_NATIVE_COMPLEX_ENV": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "DISPLAY": ":0",
        "XAUTHORITY": "/tmp/xauth",
        "OMPI_COMM_WORLD_SIZE": "1",
        "PMIX_RANK": "0",
        "PMI_SIZE": "1",
        "UNRELATED": "kept",
    }
    cleaned = workflow.task041_inner_mpi_environment(environment)
    assert cleaned == {
        "PATH": "/bin",
        "LD_LIBRARY_PATH": "/lib",
        "PYTHONPATH": "/src",
        "MYFENICS_NATIVE_COMPLEX_ENV": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "UNRELATED": "kept",
    }
    assert "DISPLAY" not in cleaned
    assert "XAUTHORITY" not in cleaned


def test_mode_prep_command_is_fresh_inner_mpi1() -> None:
    command = workflow.build_task041_mode_prep_command(
        ROOT / ".venv/bin/python",
        TASK041_INPUT,
        ROOT / "results/task041-test",
        "b" * 40,
    )
    assert command[:6] == [
        "mpiexec",
        "-n",
        "1",
        str(ROOT / ".venv/bin/python"),
        "-m",
        "benchmarks.task041_exact_side_workflow",
    ]
    assert "--worker" in command
    assert "--phase" in command
    assert command[command.index("--phase") + 1] == "mode-prep"
    assert "--source-sha" in command
    assert "python" not in command[:3]


def test_task041_shortwave_mode_prep_uses_mpi8_contract(monkeypatch, tmp_path):
    input_path = ROOT / "input/official/task041/3nm_p6h3_m800_mpi8.dat"
    captured = {}

    class Comm:
        rank = 0
        size = 8

        @staticmethod
        def bcast(value, root=0):
            del root
            return value

        @staticmethod
        def Barrier():
            return None

    def fake_producer(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        packet_directory = Path(
            argv[argv.index("--selected-mode-packet-producer-dir") + 1]
        )
        packet_directory.mkdir(parents=True)
        (packet_directory / "manifest.json").write_text("{}", encoding="utf-8")
        return {
            "task041_mode_prep": True,
            "local_systems": "not_run",
            "coupling": "not_run",
            "factor": "not_run",
            "solve": "not_run",
            "recovery": "not_run",
        }

    monkeypatch.setattr(run_task032_phase6_augmented, "main", fake_producer)
    monkeypatch.setattr(workflow, "_environment_snapshot", lambda: {"marker": "1"})
    monkeypatch.setattr(workflow, "_memavailable_bytes", lambda: 2**50)
    monkeypatch.setattr(
        workflow,
        "_resource_snapshot",
        lambda: {
            "memory_authority_bytes": 1,
            "job_no_swap": True,
            "process_tree": {"rss_bytes": 1, "swap_bytes": 0},
        },
    )
    monkeypatch.setattr(
        workflow, "simulation_config_3d_from_normalized", lambda payload: SimpleNamespace()
    )
    result = workflow.run_task041_mode_prep(
        input_path=input_path,
        run_directory=tmp_path / "mode-prep",
        source_sha="a" * 40,
        comm=Comm(),
    )

    identity = result["identity"]
    assert identity["schema"] == "task041.selected_mode_packet.identity.v2"
    assert identity["mode_count"] == 800
    assert identity["mpi_size"] == 8
    assert identity["mesh"]["mesh_target_nm"] == 3.0
    assert identity["mesh"]["nedelec_degree"] == 6
    assert result["profile"] == workflow.TASK041_SHORTWAVE_MODE_PREP_PROFILE
    assert captured["argv"][captured["argv"].index("--h-nm") + 1] == "3"
    assert captured["argv"][captured["argv"].index("--requested-modes") + 1] == "800"
    assert (tmp_path / "mode-prep" / "mode_prep_summary.json").is_file()


def test_task041_producer_argv_enables_retained_subspace_dual_rotation() -> None:
    command = workflow._producer_argv(
        ROOT / "packet",
        ROOT / "identity.json",
        ROOT / "producer.json",
        "b" * 40,
        480,
    )
    assert command.count("--retained-subspace-dual-rotation") == 1
    assert command[command.index("--h-nm") + 1] == "4"
    assert command[command.index("--degree") + 1] == "6"
    assert command[command.index("--modal-h-nm") + 1] == "4"
    assert command[command.index("--modal-degree") + 1] == "6"
    assert command[command.index("--incident-grazing-deg") + 1] == "1"
    assert command[command.index("--polarization-kind") + 1] == "s"
    assert command[command.index("--requested-modes") + 1] == "480"
    assert command[command.index("--candidate-modes") + 1] == "960"
    assert command[command.index("--internal-propagation-model") + 1] == (
        "full3d_uniform_cg"
    )
    assert command[command.index("--internal-traction-model") + 1] == (
        "full3d_one_cell_exact_schur"
    )


def test_task039_default_scope_remains_fixed() -> None:
    assert TASK039_V4_SELECTED_MODE_COUNT == 480
    assert task041_selected_mode_scope(480, 1) == "task041_5nm_p6h4_m480_mpi1"


def test_task032_exposes_private_task041_mode_prep_hook() -> None:
    signature = inspect.signature(run_task032_phase6_augmented.main)
    assert "task041_mode_prep" in signature.parameters
    source = inspect.getsource(run_task032_phase6_augmented._parse_args)
    assert "selected-mode-packet-producer-dir" in source


def test_mode_prep_does_not_register_a_consumer_or_solver() -> None:
    source = inspect.getsource(workflow.run_task041_mode_prep)
    assert "selected_mode_packet" in source
    assert "consumer" not in source.lower()
    assert "fgmres" not in source.lower()
    assert "recovery" in source.lower()


def test_inner_environment_does_not_mutate_input() -> None:
    environment = {
        "OMPI_COMM_WORLD_RANK": "0",
        "PATH": os.environ.get("PATH", ""),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "DISPLAY": ":1",
        "XAUTHORITY": "/tmp/other",
    }
    original = dict(environment)
    cleaned = workflow.task041_inner_mpi_environment(environment)
    assert environment == original
    assert "DISPLAY" not in cleaned and "XAUTHORITY" not in cleaned

    incomplete = {"PATH": "/bin", "OMP_NUM_THREADS": "8"}
    forced = workflow.task041_inner_mpi_environment(incomplete)
    assert all(forced[name] == "1" for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ))
    assert incomplete == {"PATH": "/bin", "OMP_NUM_THREADS": "8"}


def test_task041_m2_packet_writer_loader_hydrate_roundtrip(tmp_path: Path) -> None:
    identity = {
        "schema": TASK041_SELECTED_MODE_IDENTITY_SCHEMA,
        "scope": task041_selected_mode_scope(2, 1),
        "source_sha": "a" * 40,
        "input_sha256": "b" * 64,
        "resolved_sha256": "c" * 64,
        "physical_sha256": "d" * 64,
        "wavelength_nm": 5.0,
        "model_id": "task041_5nm_exact_side_hybrid_iterative_p6h4_m2",
        "run_id": "task041_5nm_p6h4_m2_mpi1",
        "mesh": {
            "cell_type": "hexahedron",
            "kind": "full3d_uniform_cg",
            "mesh_target_nm": 4.0,
            "nedelec_degree": 6,
            "spacing_mode": "boundary_fitted",
        },
        "mode_count": 2,
        "mpi_size": 1,
        "external_keys": {"count": 2, "sha256": "e" * 64},
    }
    vectors: list[PETSc.Vec] = []
    bases = {}
    for branch, sign in (("positive", 1), ("negative", -1)):
        modes = []
        for index in range(2):
            right = PETSc.Vec().createMPI((2, 2), comm=MPI.COMM_SELF)
            left = PETSc.Vec().createMPI((2, 2), comm=MPI.COMM_SELF)
            right.getArray()[:] = np.asarray(
                [sign * (index + 1), 1j * (index + 2)], dtype=np.complex128
            )
            left.getArray()[:] = np.asarray(
                [sign * (index + 3), 1j * (index + 4)], dtype=np.complex128
            )
            vectors.extend((right, left))
            modes.append(
                SimpleNamespace(
                    beta=complex(sign * (index + 1), 0.25),
                    direction="down" if sign > 0 else "up",
                    kind="external",
                    passive_branch_valid=True,
                    right=SimpleNamespace(right_full=right),
                    left_full=left,
                )
            )
        bases[branch] = SimpleNamespace(
            modes=modes,
            groups=[SimpleNamespace(indices=(0, 1))],
        )
    metadata = {
        name: {"positive": {}, "negative": {}}
        for name in ("gram_authority", "qep_diagnostics", "selection_diagnostics")
    }
    metadata.update({"trace_mapping": {}, "canonical_mapping": {}})
    try:
        packet = write_task039_v4_selected_mode_packet(
            tmp_path / "packet",
            positive_basis=bases["positive"],
            negative_basis=bases["negative"],
            identity=identity,
            metadata=metadata,
            comm=MPI.COMM_SELF,
        )
        loaded = load_task039_v4_selected_mode_packet(
            Path(packet["manifest"]), identity=identity, comm=MPI.COMM_SELF
        )
        assert loaded["mode_count"] == 2
        assert loaded["scope"] == task041_selected_mode_scope(2, 1)
        assert loaded["positive"]["right_full"].shape == (2, 2)
        bundle = hydrate_task039_v4_selected_mode_packet(loaded, comm=MPI.COMM_SELF)
        assert len(bundle.positive_basis.modes) == 2
        assert bundle.packet_consumer_diagnostics["mode_count"] == 2
        bundle.destroy()
        assert bundle.packet_consumer_diagnostics["destroyed"] is True
    finally:
        for vector in vectors:
            vector.destroy()
