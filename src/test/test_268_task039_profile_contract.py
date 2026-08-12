"""Pure Task39 material and finite-profile contracts (no solver launch)."""

from pathlib import Path
from math import isclose, pi
import inspect
from types import SimpleNamespace

import pytest
import numpy as np
from petsc4py import PETSc

from benchmarks.run_task032_phase6_augmented import _parse_args
from src.io.input_loader import InputError
from src.common.modes_3d import outgoing_port_modes_3d
from src.io.input_validation import (
    task039_07nm_launch_error,
    task039_air_side_external_mode_inventory,
    task039_dynamic_external_mode_inventory,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.execution_plan import dry_run_payload, method_adapter_identity
from src.postprocessing.diffraction_3d import _probe_z_locations
from src.runners.task038_input_worker import _dispatch_resolved_payload
from src.runners.task038_launcher import task039_resource_ledger
from src.runners import task038_launcher as launcher
from src.runners.task039_hybrid_direct import run_task039_hybrid_direct
from src.runners.task039_hybrid_direct import select_task039_hybrid_mode
from src.runners.task039_full3d_iterative import run_full3d_iterative
from src.runners.task039_hybrid_iterative import (
    make_task039_hybrid_iterative_profile,
    run_task039_hybrid_iterative,
)


ROOT = Path(__file__).resolve().parents[2]
TASK039 = ROOT / "input" / "official" / "task039"


TASK039_INPUTS = tuple(sorted(TASK039.glob("*.dat")))


def test_task039_inputs_are_numeric_finite_profiles_and_share_physics():
    specs = [load_and_resolve(path) for path in TASK039_INPUTS]

    assert len(specs) == 8
    assert {spec.method["kind"] for spec in specs} == {
        "full3d_direct",
        "full3d_iterative",
        "hybrid_direct",
        "hybrid_iterative",
    }
    assert {spec.execution["mpi_size"] for spec in specs} == {1, 8}
    assert {spec.method.get("requested_modes_per_direction") for spec in specs} == {
        None,
        120,
        240,
        480,
        960,
    }
    assert len({spec.physical_model_sha256 for spec in specs}) == 1

    for spec in specs:
        provenance = spec.derived["material_provenance"]
        assert provenance["independent_input"] == "n"
        assert provenance["delta"] == 0.00603145547
        assert provenance["beta"] == 0.00435380777
        assert list(provenance["n"]) == [0.99396854453, 0.00435380777]
        assert list(provenance["epsilon_r"]) == [
            0.9879545118729887,
            0.00865509594462061,
        ]
        assert provenance["wavelength_nm"] == 5.0
        assert provenance["air_label"] == "air"
        assert provenance["substrate_label"] == "Task39 5nm material"
        assert provenance["grating_label"] == "Task39 5nm material"
        assert provenance["imaginary_sign_preserved"] is True
        assert "epsilon" not in spec.materials
        assert spec.incidence["grazing_angle_deg"] == 10.0
        assert spec.derived["internal"]["incident_theta_deg"] == 80.0
        assert spec.incidence["azimuth_deg"] == 0.0
        assert spec.incidence["polarization"] == "s"
        assert spec.derived["stage4_assembly_backend_audit"]["qualification"]

        assert spec.output["export_canonical_vectors"] is True


def test_task039_material_provenance_is_not_added_to_ordinary_inputs():
    ordinary = load_and_resolve(ROOT / "input/templates/full3d_direct_example.dat")

    assert "material_provenance" not in ordinary.derived
    assert "air_name" not in ordinary.materials


def test_task039_probe_fraction_places_diffraction_probes_in_uniform_layers():
    expected_reference_planes = (10.0, 30.0, 60.0, 90.0, 110.0)

    for path in TASK039_INPUTS:
        spec = load_and_resolve(path)
        cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
        top_z, bottom_z = _probe_z_locations(cfg)

        assert top_z == 127.5
        assert bottom_z == -7.5
        assert cfg.grating_z_max < top_z < cfg.physical_z_max
        assert cfg.physical_z_min < bottom_z < cfg.interface_z
        assert cfg.full3d_reference_plane_z == expected_reference_planes


@pytest.mark.parametrize(
    ("filename", "replacement"),
    [
        (
            "5nm_p6h10_hybrid_direct_m120_mpi8.dat",
            (
                "requested_modes_per_direction = 120",
                "requested_modes_per_direction = 121",
            ),
        ),
        (
            "5nm_p6h10_full3d_iterative_mpi8.dat",
            (
                'preconditioner = "full3d_m3a_physical_slab_two_level"',
                'preconditioner = "hybrid_block_ldu_ilu0_dtn_woodbury"',
            ),
        ),
    ],
)
def test_task039_invalid_finite_profile_is_rejected(
    tmp_path: Path,
    filename: str,
    replacement: tuple[str, str],
):
    source = (TASK039 / filename).read_text(encoding="utf-8")
    changed = source.replace(*replacement)
    path = tmp_path / filename
    path.write_text(changed, encoding="utf-8")

    with pytest.raises(InputError):
        load_and_resolve(path)


def test_task039_hybrid_iterative_candidate_is_numeric_not_m_robust():
    path = TASK039 / "5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat"
    source = path.read_text(encoding="utf-8")

    assert "M_robust" not in source
    spec = load_and_resolve(path)
    assert spec.method["requested_modes_per_direction"] == 120
    assert spec.method["kind"] == "hybrid_iterative"
    assert spec.output["export_canonical_vectors"] is True


def test_task039_dynamic_outgoing_inventory_is_independent_of_reporting_bounds():
    spec = load_and_resolve(TASK039 / "5nm_p6h10_full3d_direct_mpi8.dat")
    cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
    modes = outgoing_port_modes_3d(cfg)
    keys = {(mode.side, mode.m, mode.n, mode.polarization) for mode in modes}

    assert len(keys) > 40
    assert {key[1:3] for key in keys} >= {(0, 0)}
    assert cfg.diffraction_order_max_m is None
    assert cfg.diffraction_order_max_n is None
    assert cfg.reporting_diffraction_order_max_m == 2
    assert cfg.reporting_diffraction_order_max_n == 2


def test_task039_all_methods_share_exact_dynamic_inventory_and_physical_identity():
    filenames = (
        "5nm_p6h10_full3d_direct_mpi8.dat",
        "5nm_p6h10_full3d_iterative_mpi8.dat",
        "5nm_p6h10_hybrid_direct_m120_mpi8.dat",
        "5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat",
    )
    specs = [load_and_resolve(TASK039 / filename) for filename in filenames]
    assert len({spec.physical_model_sha256 for spec in specs}) == 1
    inventories = [
        task039_dynamic_external_mode_inventory(spec.as_jsonable()) for spec in specs
    ]
    key_sets = []
    for inventory in inventories:
        json_keys = [
            [item["side"], item["m"], item["n"], item["polarization"]]
            for item in inventory["keys"]
        ]
        assert all(isinstance(key, list) and len(key) == 4 for key in json_keys)
        assert len(json_keys) == len({tuple(key) for key in json_keys})
        assert inventory["count"] > 40
        assert {tuple(key[1:3]) for key in json_keys} >= {(0, 0)}
        for side in ("top", "bottom"):
            side_rows = [key for key in json_keys if key[0] == side]
            counts = inventory["counts"]["polarization_per_side"].get(
                side, {"S": 0, "P": 0}
            )
            assert counts["S"] + counts["P"] == len(side_rows)
            assert counts["S"] == sum(key[3].upper() == "S" for key in side_rows)
            assert counts["P"] == sum(key[3].upper() == "P" for key in side_rows)
        key_sets.append(set(map(tuple, json_keys)))
    assert all(keys == key_sets[0] for keys in key_sets[1:])


def test_task039_air_only_component_is_top_side_and_full_launch_is_closed():
    spec = load_and_resolve(TASK039 / "5nm_p6h10_full3d_direct_mpi8.dat")
    cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
    inventory = task039_air_side_external_mode_inventory(cfg)
    assert inventory["count"] > 0
    assert inventory["material_status"] == "0P7NM_MATERIAL_INPUT_INCOMPLETE"
    assert inventory["full_pde_allowed"] is False
    assert all(item["side"] == "top" for item in inventory["keys"])
    assert not any(item["side"] == "bottom" for item in inventory["keys"])
    assert (
        task039_07nm_launch_error(
            {
                "dimension": 3,
                "model_id": "task039_0p7nm_air_component",
                "incidence": {"wavelength_nm": 0.7},
            }
        )
        == "0P7NM_MATERIAL_INPUT_INCOMPLETE"
    )
    assert task039_07nm_launch_error(spec.as_jsonable()) is None
    status, errors = _dispatch_resolved_payload(
        {
            "dimension": 3,
            "model_id": "task039_0p7nm_air_component",
            "incidence": {"wavelength_nm": 0.7},
        },
        expected_method="full3d_direct",
        output_directory=Path("/tmp/task039-no-pde"),
        expected_source_sha="a" * 40,
    )
    assert status == 4
    assert errors == ["0P7NM_MATERIAL_INPUT_INCOMPLETE"]


def test_task039_resource_ledger_uses_contract_limits_and_classifications():
    measured = task039_resource_ledger(
        256.0,
        observed_process_tree_gib=179.0,
        observed_swap_gib=0.0,
    )
    assert measured["warning_memory_gib"] == {
        "value": 180.0,
        "classification": "contract",
    }
    assert measured["hard_stop_memory_gib"]["value"] == 220.0
    assert measured["hard_stop_memory_gib"]["classification"] == "derived"
    assert measured["stop"] is False
    estimated = task039_resource_ledger(
        200.0,
        observed_process_tree_gib=180.0,
        observed_swap_gib=0.0,
        available_classification="estimated",
    )
    assert estimated["hard_stop_memory_gib"]["value"] == 180.0
    assert estimated["stop"] is True
    assert estimated["stop_reason"] == "memory_hard_stop"
    swapped = task039_resource_ledger(
        256.0,
        observed_process_tree_gib=10.0,
        observed_swap_gib=0.1,
    )
    assert swapped["stop"] is True
    assert swapped["stop_reason"] == "swap_policy_violation"


def test_task039_memory_budget_does_not_claim_unobserved_samples(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "wsl_memory_snapshot",
        lambda: {"mem_total_bytes": 256 * 1024**3},
    )
    monkeypatch.setattr(
        launcher,
        "cgroup_snapshot",
        lambda _scope: {"memory_limit_bytes": None},
    )

    budget = launcher._task039_memory_budget()

    assert "observed_process_tree_gib" not in budget
    assert "observed_swap_gib" not in budget
    assert "stop" not in budget
    assert "stop_reason" not in budget
    assert budget["actual_available_gib"]["classification"] == "measured"
    assert budget["hard_stop_memory_gib"]["classification"] == "derived"
    assert budget["source"]["classification"] == "measured"


def test_task039_launcher_uses_effective_budget_before_worker_sampling(
    monkeypatch, tmp_path: Path
):
    spec = load_and_resolve(TASK039 / "5nm_p6h10_full3d_direct_mpi8.dat")
    budget = {
        "effective_terminate_memory_gib": 1.0,
        "source": {"selected": "injected-test-limit"},
    }
    monkeypatch.setattr(launcher, "_task039_memory_budget", lambda: budget)

    class FakeProcess:
        pid = 12345

        def poll(self):
            return 0

        def wait(self):
            return 0

    terminated = []
    plan = SimpleNamespace(argv=("contract-probe",), contract_probe=True)
    result = launcher._run_worker(
        plan,
        spec,
        tmp_path,
        popen_factory=lambda *args, **kwargs: FakeProcess(),
        sample_factory=lambda _pid: {
            "process_tree": {
                "all_status_readable": True,
                "rss_bytes": 2 * 1024**3,
                "swap_bytes": 0,
            },
            "memory_authority_bytes": 2 * 1024**3,
            "job_cgroup": {},
        },
        terminate_factory=lambda process: terminated.append(process) or {},
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.0,
    )
    assert result["result_classification"] == "memory_terminate"
    assert terminated
    assert result["resource_authority"]["task039_memory_budget"] is budget


def test_task039_woodbury_large_dynamic_trace_has_finite_square_modal_system():
    from src.solvers.hybrid_local_dtn_woodbury import HybridLocalDtnWoodburyOracle

    active = 3
    spec = load_and_resolve(TASK039 / "5nm_p6h10_full3d_direct_mpi8.dat")
    inventory = task039_dynamic_external_mode_inventory(spec.as_jsonable())
    modes = inventory["counts"]["per_side"]["top"]
    assert modes > 40
    identity = np.eye(active, dtype=complex)
    coupling = np.full((active, modes), 1.0e-3 + 2.0e-4j)
    components = SimpleNamespace(
        F=PETSc.Mat().createDense((active, active), array=identity),
        C=PETSc.Mat().createDense((active, modes), array=coupling),
        D=PETSc.Mat().createDense((modes, active), array=coupling.conjugate().T * 0.1),
        H=PETSc.Mat().createDense(
            (modes, modes), array=2.0 * np.eye(modes, dtype=complex)
        ),
    )
    for matrix in (components.F, components.C, components.D, components.H):
        matrix.assemble()

    class IdentityInverse:
        def solve(self, source, target):
            source.copy(target)

    oracle = HybridLocalDtnWoodburyOracle(IdentityInverse(), components)
    diagnostics = oracle.diagnostics
    assert diagnostics["W_local_shape"] == [active, modes]
    assert diagnostics["K_shape"] == [modes, modes]
    assert diagnostics["K_rank"] == modes
    assert diagnostics["arrays_finite"] is True
    assert diagnostics["normal_equations"] is False
    assert diagnostics["K_condition_number"] < float("inf")
    oracle.destroy()
    for matrix in (components.F, components.C, components.D, components.H):
        matrix.destroy()


def test_task039_finite_dispatch_has_no_neural_or_learned_profile_family():
    from src.io.input_validation import task039_model_id_matches

    assert not task039_model_id_matches(
        "hybrid_iterative", "task039_5nm_neural_m120_candidate", 120
    )
    with pytest.raises(InputError):
        method_adapter_identity("hybrid_iterative", "task039_5nm_neural_m120_candidate")
    with pytest.raises(InputError, match="0P7NM_MATERIAL_INPUT_INCOMPLETE"):
        method_adapter_identity("full3d_direct", "task039_0p7nm_air_component")


def test_task039_hybrid_mode_selection_is_finite_and_not_a_campaign():
    assert select_task039_hybrid_mode(
        {
            120: {"own": True, "vs_next": True, "full3d": True},
            240: {"own": False, "vs_next": False, "full3d": False},
        }
    ) == {"status": "established", "selected_m": 120, "comparison_m": 240}
    assert select_task039_hybrid_mode(
        {
            120: {"own": True, "vs_next": False, "full3d": True},
            240: {"own": True, "vs_next": True, "full3d": True},
            480: {"own": False, "vs_next": False, "full3d": False},
        }
    ) == {"status": "established", "selected_m": 240, "comparison_m": 480}
    assert select_task039_hybrid_mode(
        {
            480: {"own": True, "vs_next": True, "full3d": True},
            960: {"own": True, "full3d": True},
        }
    ) == {"status": "established", "selected_m": 480, "comparison_m": 960}
    assert select_task039_hybrid_mode({960: {"own": True, "full3d": True}}) == {
        "status": "upper_cap",
        "selected_m": 960,
    }
    assert select_task039_hybrid_mode({120: {"own": False}})["status"] == (
        "not_established"
    )
    with pytest.raises(ValueError):
        select_task039_hybrid_mode({961: {"own": True}})


def _task039_direct_record(inventory):
    orders = [
        {
            **key,
            "beta_per_nm": 0.1 + 0.2j,
            "total_projection": 0.3 + 0.1j,
            "outgoing_amplitude": 0.4 + 0.05j,
            "power_ratio": 0.01,
        }
        for key in inventory["keys"]
    ]
    return {
        "qualification": {"integration_pass": True},
        "solve": {"true_relative_residual": 1.0e-12},
        "validation": {
            "port_power": {
                "R_total": 0.2,
                "T_total": 0.7,
                "A_balance": 0.1,
            },
            "external_diffraction_orders": orders,
        },
        "physical_field_reconstruction": {
            "volume_absorption": {
                "A_volume_total": 0.1,
                "energy_closure_error": 0.0,
            }
        },
        "canonical_exports": {
            side: {
                "roles": {
                    "active_trace": {"pass": True},
                    "full_fe": {"pass": True},
                }
            }
            for side in ("bottom", "top")
        },
        "external_mode_inventory": inventory,
    }


def _task039_iterative_record(profile, inventory, source_sha):
    mode_identity = {}
    for side in ("bottom", "top"):
        side_keys = [
            [item["side"], item["m"], item["n"], item["polarization"]]
            for item in inventory["keys"]
            if item["side"] == side
        ]
        mode_identity[side] = {
            "count": len(side_keys),
            "keys": side_keys,
            "keys_unique": len(side_keys) == len({tuple(key) for key in side_keys}),
            "beta_finite": True,
            "polarization_valid": True,
            "pass": True,
        }
    orders = [
        {
            **key,
            "beta_per_nm": [0.1, 0.0],
            "total_projection": [0.2, 0.0],
            "outgoing_amplitude": [0.3, 0.0],
        }
        for key in inventory["keys"]
    ]
    from benchmarks.task037c_robustness import profile_record

    return {
        "record_schema": profile.record_schema,
        "status": "online_candidate_pass_awaiting_offline_checker",
        "online_pass": True,
        "ordinary_default_changed": False,
        "explicit_opt_in": True,
        "source": {
            "before": {
                "commit_sha": source_sha,
                "tracked_source_dirty": False,
                "stable_and_clean_before": True,
            },
            "after": {
                "head": source_sha,
                "clean": True,
                "matches_verified_clean_sha": True,
            },
        },
        "profile": profile_record(profile),
        "authority_bindings": {
            "explicit_profile": {
                "profile_id": profile.profile_id,
                "requested_modes": profile.requested_modes,
                "mpi_size": profile.mpi_size,
            }
        },
        "qualification": {
            key: True
            for key in (
                "numerical_pass",
                "release_pass",
                "recovery_pass",
                "physics_pass",
                "lifecycle_pass",
                "source_after_pass",
                "final_release_pass",
                "cfg_audit_pass",
                "mode_identity_pass",
                "integration_performance_pass",
                "error_free",
            )
        },
        "linear": {
            "reason": 1,
            "iterations": 17,
            "postsolve_residuals": {
                key: 1.0e-12
                for key in (
                    "reported_relative_residual",
                    "global_true_relative_residual",
                    "bottom_true_relative_residual",
                    "top_true_relative_residual",
                    "modal_true_relative_residual",
                )
            },
            "release": {"pass": True},
        },
        "physics": {
            "port_power": {"R_total": 0.3, "T_total": 0.4},
            "absorption": {"A_volume_total": 0.3},
            "energy": {"closure": 0.0},
            "traction": {
                "bottom": {"relative_dual": 1.0e-10},
                "top": {"relative_dual": 1.0e-10},
            },
            "external_orders": orders,
            "own_physics_pass": True,
            "canonical_pass": True,
            "physics_pass": True,
        },
        "mode_identity": mode_identity,
        "final_release": {"pass": True},
        "external_mode_inventory": inventory,
    }


@pytest.mark.parametrize("mpi_size", (1, 8))
def test_task039_hybrid_iterative_passes_cfg_profile_and_inventory_to_runner(
    tmp_path: Path, mpi_size: int
):
    filename = f"5nm_p6h10_hybrid_iterative_m120_candidate_mpi{mpi_size}.dat"
    specification = load_and_resolve(TASK039 / filename)
    payload = specification.as_jsonable()
    captured = {}

    def fake_runner(argv, cfg, modal_cfg, profile, inventory):
        captured.update(
            argv=argv,
            cfg=cfg,
            modal_cfg=modal_cfg,
            profile=profile,
            inventory=inventory,
        )
        return _task039_iterative_record(profile, inventory, "f" * 40)

    result = run_task039_hybrid_iterative(
        payload,
        tmp_path,
        runner=fake_runner,
        source_sha="f" * 40,
    )
    assert result["passed"] is True
    assert captured["cfg"].lambda0 == 5.0
    assert captured["modal_cfg"].lambda0 == 5.0
    assert captured["cfg"].substrate_index == complex(0.99396854453, 0.00435380777)
    assert captured["cfg"].incident_theta_deg == 80.0
    assert captured["cfg"].polarization_kind == "s"
    assert captured["profile"].requested_modes == 120
    assert captured["profile"].candidate_modes == 240
    assert captured["profile"].mpi_size == mpi_size
    assert captured["profile"].max_it == 6000
    assert captured["profile"].restart == 90
    assert captured["profile"].rtol == 5.0e-9
    assert captured["profile"].shift == 0.1
    assert captured["profile"].side_residual_correction_steps == 2
    assert captured["inventory"]["count"] > 40
    assert captured["argv"][captured["argv"].index("--requested-modes") + 1] == "120"
    assert captured["argv"][captured["argv"].index("--mpi-size") + 1] == str(mpi_size)


@pytest.mark.parametrize(
    "record_change",
    (
        lambda record: record["source"]["after"].update({"head": "0" * 40}),
        lambda record: record["linear"]["postsolve_residuals"].update(
            {"modal_true_relative_residual": 6.0e-9}
        ),
        lambda record: record["physics"]["traction"]["bottom"].update(
            {"relative_dual": 2.0e-8}
        ),
        lambda record: record["physics"].update({"own_physics_pass": False}),
        lambda record: record["mode_identity"]["bottom"]["keys"].pop(),
    ),
)
def test_task039_hybrid_iterative_rejects_authority_mismatch(
    tmp_path: Path, record_change
):
    specification = load_and_resolve(
        TASK039 / "5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat"
    )

    def fake_runner(_argv, _cfg, _modal_cfg, profile, inventory):
        record = _task039_iterative_record(profile, inventory, "a" * 40)
        record_change(record)
        return record

    result = run_task039_hybrid_iterative(
        specification.as_jsonable(),
        tmp_path,
        runner=fake_runner,
        source_sha="a" * 40,
    )
    assert result["passed"] is False
    assert result["errors"]


@pytest.mark.parametrize("requested_modes", (120, 240, 480, 960))
def test_task039_hybrid_iterative_profile_factory_and_direction_are_finite(
    requested_modes: int,
):
    from benchmarks.task037c_robustness import direction_s_phase_audit

    default = direction_s_phase_audit(0.0)
    task039 = direction_s_phase_audit(0.0, wavelength_nm=5.0, grazing_deg=10.0)
    assert default["theta_deg"] == 89.0
    assert default["grazing_deg"] == 1.0
    assert task039["theta_deg"] == 80.0
    assert task039["grazing_deg"] == 10.0
    profile = make_task039_hybrid_iterative_profile(requested_modes, 1)
    assert profile.mpi_size == 1
    assert profile.requested_modes == requested_modes
    assert profile.candidate_modes == 2 * requested_modes
    with pytest.raises(ValueError):
        make_task039_hybrid_iterative_profile(121, 8)
    with pytest.raises(ValueError):
        make_task039_hybrid_iterative_profile(120, 4)


def test_task039_explicit_iterative_parser_seam_keeps_legacy_cli_choices(
    monkeypatch, tmp_path: Path
):
    from benchmarks import run_task037b_hybrid_iterative as iterative

    argv = [
        "--task037c-robustness-gate",
        "--case-label",
        "task039-m240",
        "--run-dir",
        str(tmp_path / "run"),
        "--output",
        str(tmp_path / "record.json"),
        "--verified-clean-sha",
        "a" * 40,
        "--incident-phi-deg",
        "0",
        "--requested-modes",
        "240",
        "--mpi-size",
        "8",
        "--internal-traction-model",
        "full3d_one_cell_exact_schur",
        "--task037c-two-pass-side-correction",
    ]
    with pytest.raises(SystemExit):
        iterative.parse_args(argv)

    captured = {}

    def fake_run(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return 0

    monkeypatch.setattr(iterative, "run_frozen_m10", fake_run)
    profile = make_task039_hybrid_iterative_profile(240, 8)
    result = iterative.run_explicit_hybrid_iterative_profile(
        argv,
        profile=profile,
        cfg_override=object(),
        modal_cfg_override=object(),
        external_mode_inventory={"keys": []},
    )
    assert result == 0
    assert captured["args"].requested_modes == 240
    assert captured["kwargs"]["profile_override"] == profile

    with pytest.raises(SystemExit):
        iterative.parse_args(
            [
                *argv[: argv.index("--requested-modes") + 1],
                "961",
                *argv[argv.index("--requested-modes") + 2 :],
            ],
            requested_modes_choices=(120, 240, 480, 960),
        )


def test_task039_hybrid_iterative_identity_and_worker_dispatch(monkeypatch, tmp_path):
    specification = load_and_resolve(
        TASK039 / "5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat"
    )
    payload = specification.as_jsonable()
    assert method_adapter_identity("hybrid_iterative") == "task038.hybrid_iterative"
    assert (
        method_adapter_identity("hybrid_iterative", payload["model_id"])
        == "task039.hybrid_iterative"
    )

    from src.runners.task038_input_worker import _dispatch_resolved_payload
    import src.runners.task039_hybrid_iterative as adapter_module

    captured = {}

    def fake_adapter(resolved, directory, **kwargs):
        captured.update(resolved=resolved, directory=directory, kwargs=kwargs)
        return {"passed": True, "errors": []}

    monkeypatch.setattr(adapter_module, "run_task039_hybrid_iterative", fake_adapter)
    status, errors = _dispatch_resolved_payload(
        payload,
        expected_method="hybrid_iterative",
        output_directory=tmp_path,
        expected_source_sha="c" * 40,
    )
    assert status == 0
    assert errors == []
    assert captured["kwargs"]["source_sha"] == "c" * 40


def test_task039_hybrid_iterative_rejects_unlisted_model_id(tmp_path: Path):
    specification = load_and_resolve(
        TASK039 / "5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat"
    )
    payload = specification.as_jsonable()
    payload["model_id"] = "task039_5nm_unlisted"
    with pytest.raises(ValueError, match="finite Task39 model_id"):
        run_task039_hybrid_iterative(payload, tmp_path, source_sha="d" * 40)


def test_task039_hybrid_iterative_rejects_model_m_mismatch(tmp_path: Path):
    specification = load_and_resolve(
        TASK039 / "5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat"
    )
    payload = specification.as_jsonable()
    payload["model_id"] = "task039_5nm_hybrid_iterative_m240_candidate"
    with pytest.raises(ValueError, match="model M"):
        run_task039_hybrid_iterative(payload, tmp_path, source_sha="d" * 40)


@pytest.mark.parametrize(
    ("filename", "requested_modes"),
    (
        ("5nm_p6h10_hybrid_direct_m120_mpi8.dat", 120),
        ("5nm_p6h10_hybrid_direct_m240_mpi8.dat", 240),
        ("5nm_p6h10_hybrid_direct_m480_mpi8.dat", 480),
        ("5nm_p6h10_hybrid_direct_m960_mpi8.dat", 960),
    ),
)
def test_task039_hybrid_direct_passes_finite_cfg_and_inventory_to_runner(
    tmp_path: Path, filename: str, requested_modes: int
):
    specification = load_and_resolve(TASK039 / filename)
    captured = {}

    def fake_runner(argv, cfg, canonical_export_prefix, external_mode_inventory):
        captured.update(
            argv=argv,
            cfg=cfg,
            canonical_export_prefix=canonical_export_prefix,
            external_mode_inventory=external_mode_inventory,
        )
        return _task039_direct_record(external_mode_inventory)

    result = run_task039_hybrid_direct(
        specification.as_jsonable(),
        tmp_path,
        runner=fake_runner,
        source_sha="a" * 40,
    )
    assert result["passed"] is True
    assert captured["canonical_export_prefix"] == "task039_direct"
    assert captured["cfg"].lambda0 == 5.0
    assert captured["cfg"].substrate_index == complex(0.99396854453, 0.00435380777)
    assert captured["cfg"].incident_theta_deg == 80.0
    assert captured["cfg"].stage4_full3d_assembly_backend == (
        "assembly_time_static_condensed"
    )
    assert captured["cfg"].reporting_diffraction_order_max_m == 2
    assert captured["cfg"].diffraction_order_max_m is None
    assert "--requested-modes" in captured["argv"]
    assert captured["argv"][captured["argv"].index("--requested-modes") + 1] == str(
        requested_modes
    )
    assert captured["argv"][captured["argv"].index("--candidate-modes") + 1] == str(
        2 * requested_modes
    )
    assert (
        captured["argv"][captured["argv"].index("--internal-traction-model") + 1]
        == "full3d_one_cell_exact_schur"
    )
    assert (
        captured["external_mode_inventory"]["keys"]
        == (result["external_mode_inventory"]["keys"])
    )
    parsed = _parse_args(captured["argv"], allow_task039=True)
    assert parsed.internal_traction_model == "full3d_one_cell_exact_schur"
    with pytest.raises(SystemExit):
        _parse_args(
            [*captured["argv"], "--allow-dirty-research"],
            allow_task039=True,
        )


def test_task039_hybrid_direct_rejects_model_m_mismatch(tmp_path: Path):
    specification = load_and_resolve(TASK039 / "5nm_p6h10_hybrid_direct_m120_mpi8.dat")
    payload = specification.as_jsonable()
    payload["model_id"] = "task039_5nm_hybrid_direct_m240"
    with pytest.raises(ValueError, match="model_id"):
        run_task039_hybrid_direct(
            payload,
            tmp_path,
            runner=lambda *_args: _task039_direct_record({"keys": []}),
            source_sha="a" * 40,
        )


@pytest.mark.parametrize(
    "record_change",
    (
        lambda record: record.pop("canonical_exports"),
        lambda record: record["external_mode_inventory"]["keys"].pop(),
        lambda record: record["validation"]["external_diffraction_orders"].pop(),
        lambda record: record["canonical_exports"]["bottom"]["roles"].pop("full_fe"),
        lambda record: record["validation"]["external_diffraction_orders"][0].update(
            beta_per_nm=float("inf")
        ),
    ),
)
def test_task039_hybrid_direct_rejects_incomplete_authority(
    tmp_path: Path, record_change
):
    specification = load_and_resolve(TASK039 / "5nm_p6h10_hybrid_direct_m120_mpi8.dat")

    def fake_runner(_argv, _cfg, _prefix, inventory):
        record = _task039_direct_record(inventory)
        record_change(record)
        return record

    result = run_task039_hybrid_direct(
        specification.as_jsonable(),
        tmp_path,
        runner=fake_runner,
        source_sha="b" * 40,
    )
    assert result["passed"] is False
    assert result["errors"]


def test_task039_identity_dispatch_and_legacy_seam_defaults_are_explicit(
    monkeypatch, tmp_path: Path
):
    specification = load_and_resolve(TASK039 / "5nm_p6h10_hybrid_direct_m120_mpi8.dat")
    assert method_adapter_identity("hybrid_direct") == "task038.hybrid_direct"
    assert (
        method_adapter_identity("hybrid_direct", specification.identity["model_id"])
        == "task039.hybrid_direct"
    )
    assert dry_run_payload(specification)["resolved_method_adapter"]["identity"] == (
        "task039.hybrid_direct"
    )

    from benchmarks import run_task032_phase6_augmented as benchmark

    signature = inspect.signature(benchmark.main)
    assert signature.parameters["canonical_export_prefix"].default is None
    assert signature.parameters["external_mode_inventory"].default is None
    with pytest.raises(SystemExit):
        _parse_args(["--internal-traction-model", "full3d_one_cell_exact_schur"])

    from src.runners.task038_input_worker import _dispatch_resolved_payload
    import src.runners.task039_hybrid_direct as adapter_module

    captured = {}

    def fake_adapter(payload, directory, **kwargs):
        captured.update(payload=payload, directory=directory, kwargs=kwargs)
        return {"passed": True, "errors": []}

    monkeypatch.setattr(adapter_module, "run_task039_hybrid_direct", fake_adapter)
    status, errors = _dispatch_resolved_payload(
        specification.as_jsonable(),
        expected_method="hybrid_direct",
        output_directory=tmp_path,
        expected_source_sha="c" * 40,
    )
    assert status == 0
    assert errors == []
    assert captured["kwargs"]["source_sha"] == "c" * 40


def test_task039_full3d_iterative_passes_resolved_cfg_and_frozen_solver_budget(
    tmp_path: Path,
):
    specification = load_and_resolve(TASK039 / "5nm_p6h10_full3d_iterative_mpi8.dat")
    captured = {}

    def fake_runner(cfg, output_directory, **kwargs):
        captured.update(cfg=cfg, output_directory=output_directory, kwargs=kwargs)
        (output_directory / "task039_m3a_core_audit.json").parent.mkdir(
            parents=True, exist_ok=True
        )
        (output_directory / "task039_m3a_core_audit.json").write_text(
            __import__("json").dumps(
                {
                    "candidate": {"restart": 90, "rtol": 1.0e-6, "max_it": 4000},
                    "solver_profile": (
                        "never_materialized_owner_local_overlap0125_partition"
                    ),
                    "no_global_factor_inventory": {"global_direct_factor_count": 0},
                    "external_reported_relative_residual": 1.0e-12,
                    "external_condensed_true_residual": 2.0e-12,
                    "external_full_augmented_true_residual": 3.0e-12,
                }
            ),
            encoding="utf-8",
        )
        summary = {
            "case_status": "completed",
            "official_result": True,
            "linear_system_relative_residual": 1.0e-12,
            "ksp_converged": True,
            "external_linear_solver_port": True,
            "external_solver_profile": (
                "never_materialized_owner_local_overlap0125_partition"
            ),
            "global_A_materialized": False,
            "global_F_materialized": False,
            "stage4_energy_balance_pass": True,
            "energy_closure_error_port_volume": 0.0,
            "task037_m3a_canonical_export": {
                "roles": {"active_trace": {}, "full_fe": {}}
            },
        }
        kwargs["solution_observer"](
            summary=summary,
            field=None,
            mesh_data=None,
            config=cfg,
            floquet_data=None,
            linear_system={},
            dtn_result={},
        )
        return summary

    result = run_full3d_iterative(
        specification.as_jsonable(),
        tmp_path,
        source_sha="d" * 40,
        solution_observer_factory=lambda _path: lambda **_kwargs: None,
        solver_runner=fake_runner,
    )
    assert result["passed"] is True
    assert isclose(2.0 * pi / captured["cfg"].k0, 5.0, rel_tol=0.0, abs_tol=1.0e-12)
    assert captured["cfg"].substrate_index == complex(0.99396854453, 0.00435380777)
    assert captured["cfg"].incident_theta_deg == 80.0
    assert captured["kwargs"]["screen_iterations"] == 4000
    assert captured["kwargs"]["canonical_vector_export"] is True
    assert callable(captured["kwargs"]["solution_observer"])
    assert callable(captured["kwargs"]["audit_observer"])
    assert result["summary"]["task039_m3a_core_audit"]["candidate"]["max_it"] == 4000
    assert (
        result["external_mode_inventory"]["keys"]
        == (result["summary"]["external_mode_inventory"]["keys"])
    )


def test_task039_full3d_iterative_rejects_noncanonical_source_sha(tmp_path: Path):
    specification = load_and_resolve(TASK039 / "5nm_p6h10_full3d_iterative_mpi8.dat")

    with pytest.raises(ValueError, match="lowercase source SHA"):
        run_full3d_iterative(
            specification.as_jsonable(),
            tmp_path,
            source_sha="Task39-test-source",
            solver_runner=lambda *_args, **_kwargs: {},
        )


def test_m3a_port_factory_keeps_task37_default_and_allows_task039_budget(
    monkeypatch,
    tmp_path: Path,
):
    from benchmarks import run_task033_full3d_watchdog as watchdog
    from src.solvers import static_condensed_iterative as core

    calls = []
    real_factory = core.build_never_materialized_overlap0125_partition_port

    def fake_core(request, *, screen_iterations, **_kwargs):
        calls.append(screen_iterations)
        return object(), {}

    monkeypatch.setattr(
        core, "solve_never_materialized_overlap0125_partition_fgmres", fake_core
    )

    default_factory_calls = []

    def fake_factory(**kwargs):
        default_factory_calls.append(kwargs["screen_iterations"])
        return object()

    monkeypatch.setattr(
        core, "build_never_materialized_overlap0125_partition_port", fake_factory
    )
    assert watchdog._task037_m3a_solver_port(tmp_path) is not None
    assert default_factory_calls == [3000]

    monkeypatch.setattr(
        core,
        "build_never_materialized_overlap0125_partition_port",
        real_factory,
    )
    port = core.build_never_materialized_overlap0125_partition_port(
        screen_iterations=4000
    )
    port(object())
    assert calls == [4000]


def test_task039_full3d_iterative_rejects_missing_external_or_canonical_authority(
    tmp_path: Path,
):
    specification = load_and_resolve(TASK039 / "5nm_p6h10_full3d_iterative_mpi8.dat")

    def fake_runner(_cfg, _output_directory, **_kwargs):
        return {
            "case_status": "completed",
            "official_result": True,
            "linear_system_relative_residual": 1.0e-12,
        }

    result = run_full3d_iterative(
        specification.as_jsonable(),
        tmp_path,
        source_sha="e" * 40,
        solver_runner=fake_runner,
    )
    assert result["passed"] is False
    assert any(
        "external solver port was not used" in error for error in result["errors"]
    )
    assert any("canonical active/full" in error for error in result["errors"])
