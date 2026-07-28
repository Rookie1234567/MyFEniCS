from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mpi4py import MPI
import numpy as np
import pytest
import ufl

from basix.ufl import element
from benchmarks.run_task033_full3d_watchdog import (
    _full3d_config,
    _parse_args,
    _worker_command,
    _worker_launch_contract,
)
from dolfinx import default_real_type, fem, mesh
from petsc4py import PETSc

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    SimulationConfig3D,
    qualify_stage4_full3d_assembly_backend,
    resolve_stage4_full3d_assembly_backend,
)
from src.solvers import hcurl_assembly_time_condensation as assembly_time
from src.solvers import hcurl_variable_p_reduction


class _FakeFFI:
    @staticmethod
    def string(value: bytes) -> bytes:
        return value


class _FakeElement:
    @staticmethod
    def hash() -> int:
        return 249_035


def _fake_policy() -> tuple[
    SimpleNamespace,
    dict[int, object],
    int,
]:
    compiled = SimpleNamespace(
        dtype=np.dtype(np.complex128),
        function_spaces=(
            SimpleNamespace(
                element=SimpleNamespace(
                    basix_element=_FakeElement(),
                )
            ),
        ),
        module=SimpleNamespace(ffi=_FakeFFI()),
        ufcx_form=SimpleNamespace(signature=b"test249-form-signature"),
    )
    return compiled, {-1: object(), 1: object()}, 2


def _classes() -> tuple[
    tuple[str, int, float, float, float],
    dict[tuple[str, int, float, float, float], np.ndarray],
]:
    key = ("test249_policy", 1, 1.0, 2.0, 3.0)
    coordinates = np.arange(24, dtype=np.float64)
    return key, {key: coordinates}


def _tensor() -> np.ndarray:
    return np.asarray(
        [
            [2.0 + 0.5j, -1.0 + 0.25j],
            [3.0 - 0.75j, 4.0 + 0.0j],
        ],
        dtype=np.complex128,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_persistent_raw_tensor_cache_is_off_by_default(
    tmp_path: Path,
) -> None:
    cfg = SimulationConfig3D()
    key, classes = _classes()
    with mock.patch.object(
        assembly_time,
        "_tabulate_raw_tensor_class",
        return_value=_tensor(),
    ) as tabulate:
        cache, audit, _seconds = assembly_time._global_raw_tensor_cache(
            MPI.COMM_SELF,
            classes,
            {"test249_policy": _fake_policy()},
        )

    assert np.array_equal(cache[key], _tensor())
    assert tabulate.call_count == 1
    assert audit["raw_tensor_persistent_cache"]["enabled"] is False
    assert audit["raw_tensor_persistent_cache"]["status"] == "disabled"
    assert audit["raw_tensor_kernel_evaluation_count_global"] == 1
    assert not list(tmp_path.rglob("*.npz"))
    assert cfg.stage4_raw_tensor_cache_directory is None
    assert cfg.stage4_raw_tensor_cache_namespace is None


def test_cold_then_warm_cache_is_exact_and_warm_skips_kernel(
    tmp_path: Path,
) -> None:
    key, classes = _classes()
    directory = tmp_path.resolve()
    namespace = "git-" + "a" * 40
    with mock.patch.object(
        assembly_time,
        "_tabulate_raw_tensor_class",
        return_value=_tensor(),
    ) as cold_tabulate:
        cold, cold_audit, _seconds = (
            assembly_time._global_raw_tensor_cache(
                MPI.COMM_SELF,
                classes,
                {"test249_policy": _fake_policy()},
                persistent_cache_directory=directory,
                persistent_cache_namespace=namespace,
            )
        )
    with mock.patch.object(
        assembly_time,
        "_tabulate_raw_tensor_class",
        side_effect=AssertionError("warm cache called the compiled kernel"),
    ) as warm_tabulate:
        warm, warm_audit, _seconds = (
            assembly_time._global_raw_tensor_cache(
                MPI.COMM_SELF,
                classes,
                {"test249_policy": _fake_policy()},
                persistent_cache_directory=directory,
                persistent_cache_namespace=namespace,
            )
        )

    assert cold_tabulate.call_count == 1
    assert warm_tabulate.call_count == 0
    assert np.array_equal(cold[key], warm[key])
    assert np.array_equal(warm[key], _tensor())
    assert cold_audit["raw_tensor_persistent_cache"]["status"] == (
        "cold_all_miss"
    )
    assert warm_audit["raw_tensor_persistent_cache"]["status"] == (
        "warm_all_hit"
    )
    assert cold_audit["raw_tensor_kernel_evaluation_count_global"] == 1
    assert warm_audit["raw_tensor_kernel_evaluation_count_global"] == 0
    assert (
        cold_audit["raw_tensor_persistent_cache"]["write_count_global"]
        == 1
    )
    assert (
        warm_audit["raw_tensor_persistent_cache"]["hit_count_global"]
        == 1
    )
    entries = list(directory.rglob("*.npz"))
    assert len(entries) == 1
    assert (entries[0].stat().st_mode & 0o777) == 0o600


def test_actual_compiled_form_cold_warm_matrices_are_exact(
    tmp_path: Path,
) -> None:
    msh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    owned_cells = msh.topology.index_map(msh.topology.dim).size_local
    cell_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    space = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(trial), ufl.curl(test))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(trial, test)
        )
        * dx(1)
    )
    keywords = {
        "persistent_raw_tensor_cache_directory": tmp_path.resolve(),
        "persistent_raw_tensor_cache_namespace": "git-" + "9" * 40,
    }
    cold = assembly_time.build_unconstrained_assembly_time_condensation(
        compiled,
        space,
        cell_tags,
        **keywords,
    )
    warm = assembly_time.build_unconstrained_assembly_time_condensation(
        compiled,
        space,
        cell_tags,
        **keywords,
    )
    try:
        difference = warm.matrix.copy()
        difference.axpy(-1.0, cold.matrix)
        assert float(difference.norm(PETSc.NormType.FROBENIUS)) == 0.0
        assert (
            cold.build_audit["raw_tensor_persistent_cache"]["status"]
            == "cold_all_miss"
        )
        assert (
            warm.build_audit["raw_tensor_persistent_cache"]["status"]
            == "warm_all_hit"
        )
        assert (
            warm.build_audit["raw_tensor_kernel_evaluation_count_global"]
            == 0
        )
        difference.destroy()
    finally:
        cold.destroy()
        warm.destroy()


def test_tampered_cache_fails_closed_without_overwrite(
    tmp_path: Path,
) -> None:
    _key, classes = _classes()
    directory = tmp_path.resolve()
    namespace = "git-" + "b" * 40
    with mock.patch.object(
        assembly_time,
        "_tabulate_raw_tensor_class",
        return_value=_tensor(),
    ):
        assembly_time._global_raw_tensor_cache(
            MPI.COMM_SELF,
            classes,
            {"test249_policy": _fake_policy()},
            persistent_cache_directory=directory,
            persistent_cache_namespace=namespace,
        )
    entry = next(directory.rglob("*.npz"))
    with np.load(entry, allow_pickle=False) as archive:
        tensor = np.asarray(archive["tensor"]).copy()
        metadata_json = np.asarray(archive["metadata_json"]).copy()
    tensor[0, 0] += 1.0
    with entry.open("wb") as handle:
        np.savez(
            handle,
            tensor=tensor,
            metadata_json=metadata_json,
        )
    os.chmod(entry, 0o600)
    tampered_sha256 = _sha256(entry)

    with mock.patch.object(
        assembly_time,
        "_tabulate_raw_tensor_class",
        side_effect=AssertionError("corruption must not trigger a rebuild"),
    ) as tabulate:
        with pytest.raises(
            RuntimeError,
            match="validation failed closed",
        ):
            assembly_time._global_raw_tensor_cache(
                MPI.COMM_SELF,
                classes,
                {"test249_policy": _fake_policy()},
                persistent_cache_directory=directory,
                persistent_cache_namespace=namespace,
            )

    assert tabulate.call_count == 0
    assert _sha256(entry) == tampered_sha256
    assert len(list(directory.rglob("*.npz"))) == 1


def test_task035e_watchdog_cache_defaults_below_artifact_root(
    tmp_path: Path,
) -> None:
    clean_sha = "c" * 40
    args = _parse_args(
        [
            "--degree",
            "6",
            "--h-nm",
            "10",
            "--run-kind",
            "assembly-only",
            "--mpi-size",
            "8",
            "--stage4-full3d-assembly-backend",
            "assembly_time_static_condensed",
            "--task035e-reference-certifier-gate",
            "--verified-clean-sha",
            clean_sha,
            "--artifact-root",
            str(tmp_path),
            "--stage4-raw-tensor-cache",
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )

    assert args.stage4_raw_tensor_cache is True
    assert args.stage4_raw_tensor_cache_directory == (
        tmp_path / "task035e_raw_tensor_cache"
    ).resolve()
    config = _full3d_config(args)
    assert config.stage4_raw_tensor_cache_directory == str(
        (tmp_path / "task035e_raw_tensor_cache").resolve()
    )
    assert config.stage4_raw_tensor_cache_namespace == f"git-{clean_sha}"
    contract = _worker_launch_contract(args)
    assert contract["stage4_raw_tensor_cache"] is True
    assert contract["stage4_raw_tensor_cache_namespace"] == f"git-{clean_sha}"
    command = _worker_command(args, args.run_dir)
    cache_index = command.index("--stage4-raw-tensor-cache-directory")
    assert command[cache_index + 1] == str(
        args.stage4_raw_tensor_cache_directory
    )


def test_config_cache_is_explicit_and_assembly_time_only(
    tmp_path: Path,
) -> None:
    cfg = SimulationConfig3D(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        mesh_cell_type="hexahedron",
        use_floquet_xy=True,
        use_pml=False,
        stage4_boundary_model="dtn_port",
        stage4_dtn_assembly="auxiliary",
        grating_width_x=17.0,
        grating_width_y=25.0,
        grating_height=120.0,
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        ),
        stage4_raw_tensor_cache_directory=str(tmp_path.resolve()),
        stage4_raw_tensor_cache_namespace="explicit-research-namespace",
    )
    resolved = resolve_stage4_full3d_assembly_backend(cfg, apply=True)
    qualification = qualify_stage4_full3d_assembly_backend(cfg, resolved)
    assert qualification["raw_tensor_cache"]["enabled"] is True
    assert qualification["raw_tensor_cache"]["ordinary_default_changed"] is False

    cfg.stage4_full3d_assembly_backend = "standard_full"
    cfg.stage4_cell_static_condensation = False
    cfg.stage4_assembly_time_cell_static_condensation = False
    cfg.stage4_floquet_slave_elimination = False
    with pytest.raises(ValueError, match="assembly-time"):
        qualify_stage4_full3d_assembly_backend(cfg)


def test_watchdog_rejects_implicit_or_windows_mount_cache(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = [
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--run-kind",
        "assembly-only",
        "--mpi-size",
        "8",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--task035e-reference-certifier-gate",
        "--verified-clean-sha",
        "d" * 40,
    ]
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *base,
                "--stage4-raw-tensor-cache-directory",
                str(tmp_path),
            ]
        )
    assert "requires the explicit" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *base,
                "--stage4-raw-tensor-cache",
                "--stage4-raw-tensor-cache-directory",
                "/mnt/c/cache",
            ]
        )
    assert "Linux filesystem" in capsys.readouterr().err


def test_variable_p_reduction_cache_keywords_are_identity_passthrough(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = SimpleNamespace(comm=MPI.COMM_SELF)
    entity_map = SimpleNamespace(
        mesh=mesh,
        active_rows=10,
        active_trace_rows=6,
    )
    degree_plan = SimpleNamespace(
        entity_map=entity_map,
        audit={"pass": True},
    )
    transfer = SimpleNamespace(audit={"pass": True})
    periodic = SimpleNamespace(audit={"pass": True})
    system = SimpleNamespace(build_audit={})
    observed: list[dict[str, object]] = []

    monkeypatch.setattr(
        hcurl_variable_p_reduction,
        "load_variable_p_cell_degree_plan",
        lambda *_args, **_kwargs: degree_plan,
    )
    monkeypatch.setattr(
        hcurl_variable_p_reduction,
        "build_variable_p_periodic_constraint_map",
        lambda *_args, **_kwargs: periodic,
    )
    monkeypatch.setattr(
        hcurl_variable_p_reduction,
        "build_variable_p_global_transfer",
        lambda *_args, **_kwargs: transfer,
    )

    def build(*_args: object, **kwargs: object) -> SimpleNamespace:
        observed.append(dict(kwargs))
        return system

    monkeypatch.setattr(
        hcurl_variable_p_reduction,
        "build_variable_p_condensed_trace_system_from_compiled_form",
        build,
    )
    namespace = "git-" + "e" * 40
    hcurl_variable_p_reduction.build_variable_p_assembly_time_reduction(
        object(),
        SimpleNamespace(mesh=mesh),
        object(),
        degree_plan_path="synthetic.json",
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )
    hcurl_variable_p_reduction.build_variable_p_assembly_time_reduction(
        object(),
        SimpleNamespace(mesh=mesh),
        object(),
        degree_plan_path="synthetic.json",
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
        persistent_raw_tensor_cache_directory=tmp_path,
        persistent_raw_tensor_cache_namespace=namespace,
    )

    assert observed[0]["persistent_raw_tensor_cache_directory"] is None
    assert observed[0]["persistent_raw_tensor_cache_namespace"] is None
    assert observed[1]["persistent_raw_tensor_cache_directory"] is tmp_path
    assert observed[1]["persistent_raw_tensor_cache_namespace"] == namespace


def test_mpi_cache_audit_is_identical_and_one_owner_writes() -> None:
    comm = MPI.COMM_WORLD
    if comm.size < 2:
        pytest.skip("MPI metadata identity requires at least two ranks")
    if comm.rank == 0:
        import tempfile

        directory = tempfile.mkdtemp(
            prefix="myfenics-task035e-cache-mpi-",
            dir="/tmp",
        )
    else:
        directory = None
    directory = Path(comm.bcast(directory, root=0))
    key, classes = _classes()
    with mock.patch.object(
        assembly_time,
        "_tabulate_raw_tensor_class",
        return_value=_tensor(),
    ):
        cache, audit, _seconds = assembly_time._global_raw_tensor_cache(
            comm,
            classes,
            {"test249_policy": _fake_policy()},
            persistent_cache_directory=directory,
            persistent_cache_namespace="git-" + "f" * 40,
        )

    persistent = audit["raw_tensor_persistent_cache"]
    packets = comm.allgather(persistent)
    assert all(packet == packets[0] for packet in packets[1:])
    assert persistent["write_count_global"] == 1
    assert persistent["single_deterministic_owner_per_class"] is True
    assert np.array_equal(cache[key], _tensor())
