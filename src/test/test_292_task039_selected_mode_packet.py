import gc
import inspect
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from benchmarks.task039_v4_selected_mode_packet import (
    build_task039_v4_packet_metadata,
    consume_task039_v4_selected_mode_packet,
    load_task039_v4_selected_mode_packet,
    Task039V4SelectedModeMmapContext,
    stream_task039_v4_selected_mode_columns,
    write_task039_v4_selected_mode_packet,
)
from src.modes.selected_mode_packet import (
    MODE_PACKET_SCHEMA,
    write_selected_mode_packet,
)
import src.modes.selected_mode_packet as selected_mode_packet
from src.modes.stable_propagation import build_two_sided_propagation
from src.coupling.hybrid_internal_modes import HybridInternalModeCoupling
import src.solvers.hybrid_fem_modal_augmented_direct as direct_solver
import benchmarks.run_task032_phase6_augmented as direct_runner
import benchmarks.run_task037b_hybrid_iterative as hybrid_runner


V4_PACKET_SCOPE = "task039_v4_h4_m480"


def _shared_directory(tmp_path: Path) -> tuple[Path, MPI.Intracomm]:
    comm = MPI.COMM_WORLD
    directory = Path(comm.bcast(str(tmp_path), root=0))
    if comm.rank == 0:
        shutil.rmtree(directory, ignore_errors=True)
    comm.barrier()
    return directory, comm


def _identity(comm: MPI.Intracomm, scope: str = V4_PACKET_SCOPE) -> dict[str, object]:
    return {
        "source_sha": "0123456789abcdef0123456789abcdef01234567",
        "input_sha256": "input-sha",
        "resolved_sha256": "resolved-sha",
        "physical_sha256": "physical-sha",
        "mesh": "mesh-sha",
        "mode_count": 480,
        "scope": scope,
        "external_keys": "external-key-set-sha",
        "mpi": comm.size,
    }


def _metadata() -> dict[str, object]:
    reciprocal_pairs = [
        {
            "positive_index": index,
            "negative_index": index,
            "relative_beta_error": 1.0e-14,
            "electric_mass_overlap": [1.0, 0.0],
            "opposite_direction": True,
            "passive_branches_valid": True,
        }
        for index in range(480)
    ]
    mode_diagnostics = [
        {
            "index": index,
            "beta": [1.0, 0.0],
            "direction": "forward",
            "kind": "propagating",
            "passive_branch_valid": True,
            "right_polynomial_relative_residual": 1.0e-14,
            "left_polynomial_relative_residual": 2.0e-14,
        }
        for index in range(480)
    ]
    return {
        "trace_mapping": {"layout": "cross_section_rows"},
        "canonical_mapping": {"active": "selected_mode_columns"},
        "gram_authority": {
            "positive": {"condition": 1.25, "max_identity_error": 2.0e-13},
            "negative": {"condition": 1.30, "max_identity_error": 3.0e-13},
        },
        "qep_diagnostics": {
            "positive": {"right_residual_max": 3.0e-14},
            "negative": {"right_residual_max": 4.0e-14},
        },
        "selection_diagnostics": {
            "positive": {
                "candidate_modes": 960,
                "selected_modes": 480,
            },
            "negative": {
                "candidate_modes": 960,
                "selected_modes": 480,
            },
        },
        "basis_audits": {
            "positive": {"status": "measured", "rotation": None},
            "negative": {"status": "measured", "rotation": None},
        },
        "reciprocal_pairing": {
            "complete": True,
            "count": 480,
            "pairs": reciprocal_pairs,
        },
        "target_beta_per_nm": [1.0, 0.0],
        "mode_diagnostics": {
            "positive": mode_diagnostics,
            "negative": [{**row, "direction": "backward"} for row in mode_diagnostics],
        },
        "operator_authority": {
            "full_shape": [12, 12],
            "reduced_shape": [6, 6],
            "field_degree": 6,
            "geometry_degree": 6,
            "coefficient_degree": 0,
            "quadrature_degree": 8,
            "quadrature_policy": "fake",
        },
        "external_mode_counts": {"bottom": 600, "top": 600},
    }


def _branches(comm: MPI.Intracomm) -> tuple[dict[str, object], tuple[int, int]]:
    rows = 3
    start = rows * comm.rank
    base = np.arange(rows * 480, dtype=np.float64).reshape(rows, 480)
    beta = (
        np.arange(480, dtype=np.float64) + 1j * np.arange(480, dtype=np.float64) / 100.0
    )
    return {
        "positive": {
            "right_full": (base + 1.0 + comm.rank).astype(np.complex128),
            "left_full": (2.0 * base + 2.0 + 1j * comm.rank).astype(np.complex128),
            "beta": beta,
            "direction": "forward",
        },
        "negative": {
            "right_full": (3.0 * base + 3.0 + 2j * comm.rank).astype(np.complex128),
            "left_full": (4.0 * base + 4.0 + 3j * comm.rank).astype(np.complex128),
            "beta": beta * -1.0,
            "direction": "backward",
        },
    }, (start, start + rows)


class _FakeVec:
    def __init__(self, values: np.ndarray, start: int) -> None:
        self.values = np.asarray(values, dtype=np.complex128)
        self.start = int(start)

    def getOwnershipRange(self) -> tuple[int, int]:
        return self.start, self.start + self.values.size

    def getArray(self, *, readonly: bool = False) -> np.ndarray:
        assert readonly
        return self.values


def _fake_basis(
    branch: dict[str, object], ownership: tuple[int, int]
) -> SimpleNamespace:
    modes = []
    for index, beta in enumerate(branch["beta"]):
        modes.append(
            SimpleNamespace(
                right=SimpleNamespace(
                    right_full=_FakeVec(branch["right_full"][:, index], ownership[0]),
                    polynomial_relative_residual=1.0e-14,
                ),
                left_full=_FakeVec(branch["left_full"][:, index], ownership[0]),
                beta=beta,
                left_polynomial_relative_residual=2.0e-14,
                kind="propagating",
                direction=branch["direction"],
                passive_branch_valid=True,
            )
        )
    groups = tuple(
        SimpleNamespace(
            indices=tuple(range(start, start + 8)),
            beta_center=branch["beta"][start],
            max_relative_beta_spread=1.0e-8,
            overlap_condition=1.1,
            normalization_method="fake",
            post_normalization_identity_error=1.0e-14,
        )
        for start in range(0, 480, 8)
    )
    return SimpleNamespace(
        modes=modes,
        groups=groups,
        max_identity_error=3.0e-13,
        max_entry_identity_error=2.0e-13,
        left_pair_relative_errors=(1.0e-14,) * 480,
    )


def test_task039_v4_packet_metadata_is_compact_authority() -> None:
    comm = MPI.COMM_SELF
    branches, ownership = _branches(comm)
    positive = _fake_basis(branches["positive"], ownership)
    negative = _fake_basis(branches["negative"], ownership)
    report = SimpleNamespace(solver="TOAR", converged_modes=480, iteration_count=7)
    selection = SimpleNamespace(
        requested_modes=480,
        candidate_modes=960,
        selected_modes=480,
        desired_direction="forward",
    )
    metadata = build_task039_v4_packet_metadata(
        positive_basis=positive,
        negative_basis=negative,
        positive_qep_report=report,
        negative_qep_report=report,
        positive_selection=selection,
        negative_selection=selection,
    )
    assert set(metadata["gram_authority"]) == {"positive", "negative"}
    assert len(metadata["mode_diagnostics"]["positive"]) == 480
    assert metadata["qep_diagnostics"]["positive"]["solver"] == "TOAR"
    assert metadata["trace_mapping"]["persisted"] is False
    assert "biorthogonality_matrix" not in metadata["gram_authority"]["positive"]


def test_task039_v4_streams_one_mode_pair_without_vec_hydration(tmp_path):
    comm = MPI.COMM_WORLD
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    positive = _fake_basis(branches["positive"], ownership)
    negative = _fake_basis(branches["negative"], ownership)
    identity = _identity(comm)
    write_task039_v4_selected_mode_packet(
        directory,
        positive_basis=positive,
        negative_basis=negative,
        identity=identity,
        metadata=_metadata(),
        comm=comm,
    )
    manifest = directory / "manifest.json"
    manifest_sha = selected_mode_packet._sha256_file(manifest)
    context = Task039V4SelectedModeMmapContext(
        manifest,
        identity=identity,
        expected_manifest_sha256=manifest_sha,
        comm=comm,
    )
    pair = context.mode_pair("positive", 3)
    assert context.diagnostics == {
        "released": False,
        "mmap_mapping_count": 4,
        "arrays_retained": True,
        "full_vec_count": 0,
        "mode_count": 480,
    }
    assert pair["right_local"].shape == (ownership[1] - ownership[0],)
    assert pair["left_local"].shape == (ownership[1] - ownership[0],)
    context.release()
    assert context.diagnostics["released"] is True
    assert context.diagnostics["mmap_mapping_count"] == 0
    seen = []

    def consume(index, right, left, metadata):
        seen.append((index, right.copy(), left.copy(), dict(metadata)))
        assert isinstance(right, np.ndarray)
        assert isinstance(left, np.ndarray)
        assert metadata["batch_size"] == 1

    result = stream_task039_v4_selected_mode_columns(
        manifest,
        identity=identity,
        expected_manifest_sha256=manifest_sha,
        branch="positive",
        indices=(3, 7),
        callback=consume,
        comm=comm,
    )
    assert result == {
        "branch": "positive",
        "mode_count": 480,
        "selected_count": 2,
        "batch_size": 1,
        "arrays_retained": False,
        "consumer_qep_required": False,
    }
    assert [item[0] for item in seen] == [3, 7]
    np.testing.assert_array_equal(seen[0][1], branches["positive"]["right_full"][:, 3])
    np.testing.assert_array_equal(seen[1][2], branches["positive"]["left_full"][:, 7])


def test_task039_packet_gate_metrics_use_authority_without_hydrated_qep_attrs() -> None:
    authority = {
        "positive": {
            "gram": {"max_identity_error": 2.0e-13},
            "mode_diagnostics": [
                {
                    "right_polynomial_relative_residual": 1.0e-14,
                    "left_polynomial_relative_residual": 2.0e-14,
                }
            ],
        },
        "negative": {
            "gram": {"max_identity_error": 3.0e-13},
            "mode_diagnostics": [
                {
                    "right_polynomial_relative_residual": 3.0e-14,
                    "left_polynomial_relative_residual": 4.0e-14,
                }
            ],
        },
    }
    metrics = direct_runner._task039_packet_gate_metrics(authority)
    assert metrics == {
        "biorthogonality_error": 3.0e-13,
        "qep_residual": 4.0e-14,
    }


def test_task039_deferred_recovery_and_mode_basis_lifecycle(monkeypatch) -> None:
    comm = MPI.COMM_SELF
    branches, ownership = _branches(comm)
    positive = _fake_basis(branches["positive"], ownership)
    negative = _fake_basis(branches["negative"], ownership)
    coupling = HybridInternalModeCoupling(
        projection=SimpleNamespace(),
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        propagation=SimpleNamespace(),
        modal_traction_model="continuous_qep_beta",
        positive_traction_beta_per_nm=(),
        negative_traction_beta_per_nm=(),
        negative_trace_to_positive=np.zeros((480, 480), dtype=np.complex128),
        positive_projection_identity_error=0.0,
        mode_count_per_direction=480,
        interface_quadrature_degree=1,
        spaces=SimpleNamespace(),
        positive_basis=positive,
        negative_basis=negative,
    )
    detached = coupling.detach_mode_bases()
    assert detached == (positive, negative)
    assert coupling.positive_basis is None
    assert coupling.negative_basis is None
    coupling.attach_mode_bases(*detached)
    assert coupling.positive_basis is positive
    assert coupling.negative_basis is negative

    recovery_calls = []
    monkeypatch.setattr(
        direct_solver,
        "recover_hybrid_static_local_field",
        lambda system, *_args: recovery_calls.append(system.side) or system.side,
    )
    solution = SimpleNamespace(
        bottom="bottom_solution",
        top="top_solution",
        modal_amplitudes=np.zeros(960, dtype=np.complex128),
        bottom_recovered=None,
        top_recovered=None,
        ksp=None,
    )
    bottom_system = SimpleNamespace(side="bottom", static_condensation=object())
    top_system = SimpleNamespace(side="top", static_condensation=object())
    with pytest.raises(RuntimeError, match="factor to be released"):
        direct_solver.recover_deferred_hybrid_static_solution(
            SimpleNamespace(
                bottom="bottom_solution",
                top="top_solution",
                modal_amplitudes=np.zeros(960, dtype=np.complex128),
                bottom_recovered=None,
                top_recovered=None,
                ksp=object(),
            ),
            bottom_system,
            top_system,
            coupling,
        )
    direct_solver.recover_deferred_hybrid_static_solution(
        solution, bottom_system, top_system, coupling
    )
    assert recovery_calls == ["bottom", "top"]
    assert solution.bottom_recovered == "bottom"
    assert solution.top_recovered == "top"
    coupling.detach_mode_bases()
    with pytest.raises(RuntimeError, match="attached modal bases"):
        direct_solver.recover_deferred_hybrid_static_solution(
            SimpleNamespace(
                bottom="bottom_solution",
                top="top_solution",
                modal_amplitudes=np.zeros(960, dtype=np.complex128),
                bottom_recovered=None,
                top_recovered=None,
                ksp=None,
            ),
            bottom_system,
            top_system,
            coupling,
        )


def test_task039_direct_factor_release_rejects_incomplete_cleanup() -> None:
    solution = SimpleNamespace(converged_reason=1, relative_residual=0.0, ksp=object())
    system = SimpleNamespace(_destroyed=False)
    events: list[str] = []

    def release_factorization() -> dict[str, bool]:
        solution.ksp = None
        events.append("factor_release")
        return {"released": True}

    def destroy_system() -> None:
        system._destroyed = True
        events.append("system_destroy")

    solution.release_factorization = release_factorization
    system.destroy = destroy_system
    with pytest.raises(RuntimeError, match="lifecycle failed"):
        direct_runner._release_task039_direct_factor_before_postprocess(
            solution,
            system,
            lambda: {"collective_call_completed": False},
            {"factor_count": 1},
        )
    assert events == ["factor_release", "system_destroy"]


def test_build_frozen_setup_consumes_packet_without_qep(
    monkeypatch, tmp_path: Path
) -> None:
    comm = MPI.COMM_SELF
    branches, ownership = _branches(comm)
    positive = _fake_basis(branches["positive"], ownership)
    negative = _fake_basis(branches["negative"], ownership)
    packet = write_task039_v4_selected_mode_packet(
        tmp_path,
        positive_basis=positive,
        negative_basis=negative,
        identity=_identity(comm),
        metadata=_metadata(),
        comm=comm,
    )
    calls: list[str] = []

    monkeypatch.setattr(
        hybrid_runner,
        "assemble_quadratic_beta_operators",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("consumer path must not assemble QEP operators")
        ),
    )
    monkeypatch.setattr(
        hybrid_runner, "build_matching_cross_section", lambda *a, **k: object()
    )
    monkeypatch.setattr(
        hybrid_runner, "build_cross_section_spaces", lambda *a, **k: object()
    )

    def fake_side(cfg, side, **kwargs):
        calls.append(f"{side}_build")
        value = SimpleNamespace(side=side, external_modes=[], _destroyed=False)

        def destroy() -> None:
            value._destroyed = True
            calls.append(f"{side}_destroy")

        value.destroy = destroy
        return value

    monkeypatch.setattr(
        hybrid_runner, "assemble_hybrid_local_dtn_action_system", fake_side
    )
    coupling = SimpleNamespace(internal_unknown_count=0, _destroyed=False)

    def destroy_coupling() -> None:
        coupling._destroyed = True
        calls.append("coupling_destroy")

    coupling.destroy = destroy_coupling
    monkeypatch.setattr(
        hybrid_runner, "build_hybrid_internal_mode_coupling", lambda *a, **k: coupling
    )
    profile = SimpleNamespace(
        degree=6,
        h_nm=5.0,
        modal_degree=6,
        modal_h_nm=5.0,
        incident_grazing_deg=1.0,
        incident_phi_deg=0.0,
        polarization_kind="s",
        bottom_interface_nm=10.0,
        top_interface_nm=110.0,
        internal_propagation_model="full3d_uniform_cg",
        internal_traction_model="scalar_cg_discrete_derivative",
    )
    cfg = SimpleNamespace()
    setup = hybrid_runner.build_frozen_m10_setup(
        comm,
        profile=profile,
        cfg_override=cfg,
        modal_cfg_override=SimpleNamespace(),
        selected_mode_packet_manifest=tmp_path / "manifest.json",
        selected_mode_packet_identity=_identity(comm),
        selected_mode_packet_manifest_sha256=packet["manifest_sha256"],
    )
    assert setup.qep_release["qep_calls"] == 0
    assert setup.qep_release["packet_mmap_released"] is True
    assert setup.qep_release["consumer_kind"] == "iterative"
    assert setup.qep_release["packet_manifest"] == str(tmp_path / "manifest.json")
    assert setup.qep_release["packet_manifest_sha256"] == packet["manifest_sha256"]
    assert setup.qep_release["packet_identity_sha256"] == packet["identity_sha256"]
    assert len(setup.positive.modes) == len(setup.negative.modes) == 480
    assert setup.mode_selection["external_modes"] == {"bottom": 0, "top": 0}
    release = hybrid_runner.release_frozen_m10_objects(setup, None, comm)
    assert release["pass"] is True
    assert coupling._destroyed is True
    assert setup.bottom._destroyed is True
    assert setup.top._destroyed is True
    assert setup.packet_consumer_bundle.packet_consumer_diagnostics["destroyed"] is True
    assert calls[-3:] == ["coupling_destroy", "bottom_destroy", "top_destroy"]
    second_release = hybrid_runner.release_frozen_m10_objects(setup, None, comm)
    assert second_release["pass"] is True
    assert calls.count("coupling_destroy") == 1
    assert calls.count("bottom_destroy") == 1
    assert calls.count("top_destroy") == 1


def test_task039_direct_packet_main_skips_qep_and_uses_augmented_chain(
    monkeypatch, tmp_path: Path
) -> None:
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    packet = write_task039_v4_selected_mode_packet(
        directory,
        positive_basis=_fake_basis(branches["positive"], ownership),
        negative_basis=_fake_basis(branches["negative"], ownership),
        identity=_identity(comm),
        metadata=_metadata(),
        comm=comm,
    )
    identity_path = directory / "identity.json"
    if comm.rank == 0:
        identity_path.write_text(json.dumps(_identity(comm)), encoding="utf-8")
    comm.barrier()
    events: list[str] = []
    import benchmarks.task039_v4_selected_mode_packet as packet_adapter

    real_consume = packet_adapter.consume_task039_v4_selected_mode_packet
    consumed_diagnostics = []

    def tracked_consume(*args, **kwargs):
        bundle = real_consume(*args, **kwargs)
        events.append("packet_hydrate")
        consumed_diagnostics.append(bundle.packet_consumer_diagnostics)
        destroy = bundle.destroy

        def tracked_destroy() -> None:
            events.append("packet_destroy")
            destroy()

        bundle.destroy = tracked_destroy
        return bundle

    monkeypatch.setattr(
        packet_adapter,
        "consume_task039_v4_selected_mode_packet",
        tracked_consume,
    )

    monkeypatch.setattr(
        direct_runner,
        "_source_provenance",
        lambda *args, **kwargs: {
            "commit_sha": "0" * 40,
            "git_dirty": False,
            "tracked_source_dirty": False,
        },
    )
    monkeypatch.setattr(
        direct_runner,
        "_task035c_worker_authority_gate",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        direct_runner,
        "build_matching_cross_section",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        direct_runner, "build_cross_section_spaces", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(
        direct_runner,
        "analytic_homogeneous_beta",
        lambda *args, **kwargs: 1.0 + 0.0j,
    )
    monkeypatch.setattr(
        direct_runner,
        "assemble_quadratic_beta_operators",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("direct packet consumer must not assemble QEP")
        ),
    )

    def fake_local(*args, **kwargs):
        side = args[1]
        events.append(f"{side}_local_build")
        value = SimpleNamespace(
            side=side,
            external_modes=[],
            _destroyed=False,
        )

        def destroy() -> None:
            if not value._destroyed:
                value._destroyed = True
                events.append(f"{side}_local_destroy")

        value.destroy = destroy
        return value

    monkeypatch.setattr(direct_runner, "assemble_hybrid_local_dtn_system", fake_local)
    coupling = SimpleNamespace(
        _destroyed=False,
        bases_attached=True,
        positive_basis=object(),
        negative_basis=object(),
    )
    detached_states = []

    def detach_mode_bases():
        events.append("packet_detach")
        coupling.bases_attached = False
        detached = (coupling.positive_basis, coupling.negative_basis)
        coupling.positive_basis = None
        coupling.negative_basis = None
        detached_states.append(
            (coupling.positive_basis is None, coupling.negative_basis is None)
        )
        return detached

    def attach_mode_bases(positive_basis, negative_basis):
        events.append("packet_attach")
        coupling.bases_attached = True
        coupling.positive_basis = positive_basis
        coupling.negative_basis = negative_basis

    coupling.detach_mode_bases = detach_mode_bases
    coupling.attach_mode_bases = attach_mode_bases

    def destroy_coupling() -> None:
        if not coupling._destroyed:
            coupling._destroyed = True
            events.append("coupling_destroy")

    coupling.destroy = destroy_coupling
    monkeypatch.setattr(
        direct_runner,
        "build_hybrid_internal_mode_coupling",
        lambda *args, **kwargs: events.append("coupling_build") or coupling,
    )
    system = SimpleNamespace(
        _destroyed=False,
        A=SimpleNamespace(getSize=lambda: (12, 12)),
        matrix_stats={},
        block_shapes={},
        inserted_nnz_by_block={},
        dense_interface_square_formed=False,
    )

    def destroy_system() -> None:
        if not system._destroyed:
            system._destroyed = True
            events.append("augmented_destroy")

    system.destroy = destroy_system
    monkeypatch.setattr(
        direct_runner,
        "build_hybrid_augmented_direct_system",
        lambda *args, **kwargs: events.append("augmented_build") or system,
    )
    solution = SimpleNamespace(
        relative_residual=0.0,
        converged_reason=1,
        ksp=object(),
        mumps_icntl_14_requested_percent=100,
        mumps_icntl_14_observed_percent=100,
        mumps_workspace_relaxation_verified=True,
    )

    def release_solution() -> dict[str, object]:
        events.append("factor_release")
        solution.ksp = None
        return {"released": True}

    solution.release_factorization = release_solution
    solution.destroy = lambda: events.append("solution_destroy")
    monkeypatch.setattr(
        direct_runner,
        "_petsc_factor_inventory",
        lambda _ksp: {"factor_count": 1},
    )
    monkeypatch.setattr(
        hybrid_runner,
        "collective_heap_cleanup",
        lambda _comm: (
            events.append("heap_cleanup") or {"collective_call_completed": True}
        ),
    )

    def fake_solve(*args, **kwargs):
        assert kwargs["defer_static_recovery"] is True
        assert kwargs["mumps_workspace_relaxation_percent"] == 100
        events.append("solve")
        return solution

    monkeypatch.setattr(direct_runner, "solve_hybrid_augmented_direct", fake_solve)

    class _StopAfterDirectLifecycle(RuntimeError):
        pass

    monkeypatch.setattr(
        direct_runner,
        "evaluate_hybrid_augmented_solution",
        lambda *args, **kwargs: (
            events.append("evaluate")
            or {
                "port_power": {
                    "R_total": 0.0,
                    "T_total": 0.0,
                    "A_balance": 0.0,
                    "R_plus_T": 0.0,
                }
            }
        ),
    )
    monkeypatch.setattr(
        direct_runner,
        "recover_deferred_hybrid_static_solution",
        lambda *args, **kwargs: (
            events.append("deferred_recovery")
            or (_ for _ in ()).throw(_StopAfterDirectLifecycle())
        ),
    )
    cfg = SimpleNamespace(
        case_name="task039_5nm_v4_direct",
        nedelec_degree=6,
        mesh_target_size=5.0,
        incident_theta_deg=89.0,
        polarization_kind="s",
        stage4_full3d_assembly_backend="assembly_time_static_condensed",
        n_air=1.0,
    )
    args = [
        "--degree",
        "6",
        "--h-nm",
        "5",
        "--modal-degree",
        "6",
        "--modal-h-nm",
        "5",
        "--incident-grazing-deg",
        "1",
        "--polarization-kind",
        "s",
        "--requested-modes",
        "480",
        "--candidate-modes",
        "960",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "full3d_one_cell_exact_schur",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--verified-clean-sha",
        "0" * 40,
        "--selected-mode-packet-consumer-manifest",
        str(directory / "manifest.json"),
        "--selected-mode-packet-consumer-identity-json",
        str(identity_path),
        "--selected-mode-packet-consumer-manifest-sha256",
        packet["manifest_sha256"],
    ]
    with pytest.raises(_StopAfterDirectLifecycle):
        direct_runner.main(
            args,
            config_override=cfg,
            canonical_export_prefix="task039_direct",
        )
    assert events[:16] == [
        "packet_hydrate",
        "bottom_local_build",
        "top_local_build",
        "coupling_build",
        "packet_detach",
        "packet_destroy",
        "heap_cleanup",
        "augmented_build",
        "solve",
        "evaluate",
        "factor_release",
        "augmented_destroy",
        "heap_cleanup",
        "packet_hydrate",
        "packet_attach",
        "deferred_recovery",
    ]
    assert "qep" not in events
    assert solution.ksp is None
    assert system._destroyed is True
    assert consumed_diagnostics[0]["destroyed"] is True
    assert consumed_diagnostics[0]["vector_count_after_destroy"] == 0
    assert detached_states[0] == (True, True)
    comm.barrier()


def _make_petsc_vec(
    values: np.ndarray, ownership: tuple[int, int], comm: MPI.Intracomm
):
    local_size = ownership[1] - ownership[0]
    vector = PETSc.Vec().createMPI((local_size, local_size * comm.size), comm=comm)
    assert tuple(int(value) for value in vector.getOwnershipRange()) == ownership
    vector.getArray()[:] = values
    return vector


def test_task039_v4_streaming_roundtrip_hydrates_two_bases_and_collective_gram(
    tmp_path: Path,
) -> None:
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    positive_basis = _fake_basis(branches["positive"], ownership)
    negative_basis = _fake_basis(branches["negative"], ownership)
    result = write_task039_v4_selected_mode_packet(
        directory,
        positive_basis=positive_basis,
        negative_basis=negative_basis,
        identity=_identity(comm),
        metadata=_metadata(),
        comm=comm,
    )
    loaded = load_task039_v4_selected_mode_packet(
        directory / "manifest.json",
        identity=_identity(comm),
        expected_manifest_sha256=result["manifest_sha256"],
        comm=comm,
    )
    assert loaded["schema"] == MODE_PACKET_SCHEMA
    assert loaded["scope"] == V4_PACKET_SCOPE
    assert loaded["global_size"] == 3 * comm.size
    for branch_name in ("positive", "negative"):
        for side in ("right_full", "left_full"):
            array = loaded[branch_name][side]
            assert isinstance(array, np.memmap)
            assert array.shape == (480, ownership[1] - ownership[0])
            assert array.flags.writeable is False
        assert loaded["selection"][branch_name]["passive_branch_valid"] == [True] * 480
    hydrated = consume_task039_v4_selected_mode_packet(
        directory / "manifest.json",
        identity=_identity(comm),
        expected_manifest_sha256=result["manifest_sha256"],
        consumer_kind="direct",
        comm=comm,
    )
    assert len(hydrated.positive_basis.modes) == 480
    assert len(hydrated.negative_basis.modes) == 480
    assert hydrated.positive_basis is not hydrated.negative_basis
    assert all(
        mode.left_full is not None
        for basis in (hydrated.positive_basis, hydrated.negative_basis)
        for mode in basis.modes
    )
    assert hydrated.packet_consumer_diagnostics["vector_count_before_destroy"] == 1920
    old_propagation = build_two_sided_propagation(
        [*positive_basis.modes, *negative_basis.modes], 1.0
    )
    new_propagation = build_two_sided_propagation(
        [*hydrated.positive_basis.modes, *hydrated.negative_basis.modes], 1.0
    )
    assert old_propagation.forward.factors == new_propagation.forward.factors
    assert old_propagation.backward.factors == new_propagation.backward.factors
    old_vectors = []
    try:
        for index in (0, 239, 479):
            old_left = _make_petsc_vec(
                branches["positive"]["left_full"][:, index], ownership, comm
            )
            old_right = _make_petsc_vec(
                branches["positive"]["right_full"][:, index], ownership, comm
            )
            old_vectors.extend((old_left, old_right))
            new_mode = hydrated.positive_basis.modes[index]
            assert np.isclose(
                complex(old_left.dot(old_right)),
                complex(new_mode.left_full.dot(new_mode.right.right_full)),
            )
    finally:
        for vector in old_vectors:
            vector.destroy()
    diagnostics = hydrated.packet_consumer_diagnostics
    assert diagnostics["consumer_kind"] == "direct"
    assert diagnostics["qep_calls"] == 0
    assert diagnostics["consumer_qep_required"] is False
    assert diagnostics["manifest_path"] == str(directory / "manifest.json")
    assert diagnostics["manifest_sha256"] == result["manifest_sha256"]
    assert diagnostics["identity_sha256"] == result["identity_sha256"]
    assert diagnostics["rank_historical_peak_rss_after_hydrate"] > 0.0
    assert diagnostics["hydrate_rss_delta_mib"] == "not_measured"
    hydrated.destroy()
    assert diagnostics["destroyed"] is True
    assert diagnostics["vector_count_after_destroy"] == 0
    iterative_hydrated = consume_task039_v4_selected_mode_packet(
        directory / "manifest.json",
        identity=_identity(comm),
        expected_manifest_sha256=result["manifest_sha256"],
        consumer_kind="iterative",
        comm=comm,
    )
    iterative_diagnostics = iterative_hydrated.packet_consumer_diagnostics
    assert iterative_diagnostics["consumer_kind"] == "iterative"
    assert iterative_diagnostics["qep_calls"] == 0
    assert iterative_diagnostics["manifest_path"] == diagnostics["manifest_path"]
    assert iterative_diagnostics["manifest_sha256"] == diagnostics["manifest_sha256"]
    assert iterative_diagnostics["identity_sha256"] == diagnostics["identity_sha256"]
    iterative_hydrated.destroy()
    del hydrated, loaded, result
    gc.collect()
    comm.barrier()


def test_task039_v5_h5_packet_scope_keeps_consumer_qep_zero_and_release(
    tmp_path: Path,
) -> None:
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    identity = _identity(comm, scope="task039_v5_h5_m480")
    bases = {
        name: _fake_basis(branches[name], ownership)
        for name in ("positive", "negative")
    }
    result = write_task039_v4_selected_mode_packet(
        directory,
        positive_basis=bases["positive"],
        negative_basis=bases["negative"],
        identity=identity,
        metadata=_metadata(),
        comm=comm,
    )
    loaded = load_task039_v4_selected_mode_packet(
        directory / "manifest.json",
        identity=identity,
        expected_manifest_sha256=result["manifest_sha256"],
        comm=comm,
    )
    assert loaded["scope"] == "task039_v5_h5_m480"
    consumed = consume_task039_v4_selected_mode_packet(
        directory / "manifest.json",
        identity=identity,
        expected_manifest_sha256=result["manifest_sha256"],
        consumer_kind="direct",
        comm=comm,
    )
    assert consumed.packet_consumer_diagnostics["qep_calls"] == 0
    assert consumed.packet_consumer_diagnostics["consumer_qep_required"] is False
    consumed.destroy()
    assert consumed.packet_consumer_diagnostics["vector_count_after_destroy"] == 0
    del loaded, consumed
    comm.barrier()


def test_selected_mode_packet_requires_explicit_scope(tmp_path: Path) -> None:
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    bases = {
        name: _fake_basis(branches[name], ownership)
        for name in ("positive", "negative")
    }
    with pytest.raises(ValueError, match="explicit scope"):
        write_selected_mode_packet(
            directory,
            bases,
            identity=_identity(comm),
            metadata=_metadata(),
            comm=comm,
        )
    comm.barrier()


def test_selected_mode_packet_hash_corruption_is_rejected(tmp_path: Path) -> None:
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    bases = {
        name: _fake_basis(branches[name], ownership)
        for name in ("positive", "negative")
    }
    result = write_task039_v4_selected_mode_packet(
        directory,
        positive_basis=bases["positive"],
        negative_basis=bases["negative"],
        identity=_identity(comm),
        metadata=_metadata(),
        comm=comm,
    )
    comm.barrier()
    with (directory / f"rank{comm.rank:04d}_positive_right.npy").open("ab") as stream:
        stream.write(b"corruption")
    comm.barrier()
    with pytest.raises(ValueError, match="shard hash mismatch"):
        load_task039_v4_selected_mode_packet(
            directory / "manifest.json",
            expected_manifest_sha256=result["manifest_sha256"],
            comm=comm,
        )
    comm.barrier()


def test_task039_v4_scope_binds_mode_count() -> None:
    identity = {"mode_count": 479}
    with pytest.raises(ValueError, match="mode_count=480"):
        from benchmarks.task039_v4_selected_mode_packet import (
            _require_task039_identity,
        )

        _require_task039_identity(identity)


def test_packet_core_has_no_solver_or_qep_dependency() -> None:
    source = inspect.getsource(selected_mode_packet)
    assert "petsc4py" not in source
    assert "quadratic_beta_eigenproblem" not in source
    assert "npz" not in source
    assert "read_bytes" in source
    assert selected_mode_packet.MODE_PACKET_SCHEMA == MODE_PACKET_SCHEMA
    manifest = {"qep_workspace_persisted": False, "consumer_qep_required": False}
    assert not {"eps", "st", "ksp", "pc", "factor", "workspace"}.intersection(manifest)
    json.dumps(manifest)
