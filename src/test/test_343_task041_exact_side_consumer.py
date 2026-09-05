"""Pure contracts for the Task041 fresh-packet exact-side consumer."""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from benchmarks import run_task037b_hybrid_iterative as iterative_runner
from benchmarks import task039_v3_7_orchestration as orchestration
from benchmarks import task039_v4_selected_mode_packet as packet
from benchmarks import task041_exact_side_workflow as task041
from src.io.input_validation import load_and_resolve
from src.io.resolved_config import resolved_config_sha256
from src.solvers.hybrid_fem_modal_augmented_direct import HybridAugmentedLayout
from src.solvers.hybrid_fem_modal_block_ldu import HybridBlockLduIterativeConfig

ROOT = Path(__file__).resolve().parents[2]
TASK041_INPUT = ROOT / task041.TASK041_INPUT


class _FakeVec:
    def duplicate(self):
        return _FakeVec()

    def copy(self, other):
        del other

    def destroy(self):
        return None


class _FakeIterative:
    def __init__(self):
        self.solution = _FakeVec()
        self.postsolve_audit = {
            "pass": True,
            "reported_relative_residual": 1.0e-12,
            "global_true_relative_residual": 1.0e-12,
            "bottom_true_relative_residual": 1.0e-12,
            "top_true_relative_residual": 1.0e-12,
            "modal_true_relative_residual": 1.0e-12,
        }
        self.converged_reason = 1
        self.iterations = 2
        self.block_relative_residuals = {"bottom": 1.0e-12, "top": 1.0e-12}
        self.timing = {}
        self.inventory = {}

    def destroy(self):
        return None


def test_task041_packet_identity_reorders_inventory_without_hash_change():
    specification = load_and_resolve(TASK041_INPUT)
    normalized = specification.as_jsonable()
    resolved_sha = resolved_config_sha256(specification)
    identity = task041.build_task041_packet_identity(
        specification,
        normalized,
        "a" * 40,
        resolved_sha,
    )
    assert identity["external_keys"]["sha256"] == (
        "ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a"
    )
    reordered = {
        **normalized,
        "derived": {
            **normalized["derived"],
            "external_mode_inventory": {
                **normalized["derived"]["external_mode_inventory"],
                "keys": list(
                    reversed(normalized["derived"]["external_mode_inventory"]["keys"])
                ),
            },
        },
    }
    reordered_identity = task041.build_task041_packet_identity(
        specification,
        reordered,
        "a" * 40,
        resolved_sha,
    )

    assert reordered_identity["external_keys"] == identity["external_keys"]


@pytest.mark.parametrize(
    ("field", "value", "missing"),
    [
        ("side", "middle", False),
        ("m", "0", False),
        ("n", 0.5, False),
        ("polarization", "q", False),
        ("side", None, True),
        ("m", None, True),
        ("n", None, True),
        ("polarization", None, True),
    ],
)
def test_task041_external_key_hash_rejects_invalid_or_missing_physical_fields(
    field, value, missing
):
    key = {
        "side": "bottom",
        "m": 0,
        "n": 0,
        "polarization": "s",
    }
    if missing:
        del key[field]
    else:
        key[field] = value

    with pytest.raises(task041.Task041ModePrepError, match=field):
        task041._task041_canonical_mode_keys_sha256([key])


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (None, {"ksp_type": "gmres", "restart": 10, "fixed": True}),
        (
            task041.task041_consumer_iterative_config(),
            {"ksp_type": "fgmres", "restart": 90, "fixed": False},
        ),
    ],
)
def test_outer_solver_effective_config_preserves_task39_default(
    monkeypatch, tmp_path, config, expected
):
    captured = {}

    def fake_solve(operator, rhs, context, *, config, progress_callback):
        del operator, rhs, context, progress_callback
        captured["config"] = config
        return _FakeIterative()

    monkeypatch.setattr(orchestration, "_default_rhs", lambda setup, layout: _FakeVec())
    monkeypatch.setattr(
        orchestration, "solve_hybrid_block_ldu_iterative", fake_solve
    )
    release = {
        "factor_cleanup_pass": True,
        "actions_destroyed": True,
        "component_cleanup_pass": True,
        "collective_heap_cleanup": {"collective_call_completed": True},
        "factor_count_after_cleanup": {"bottom": 0, "top": 0},
    }
    kwargs = {
        "setup": object(),
        "layout": object(),
        "operator": object(),
        "context": object(),
        "comm": object(),
        "marker_callback": lambda stage, detail: None,
        "recovery_runner": lambda *args: {"pass": True},
        "producer": {},
        "run_directory": tmp_path,
        "release_before_recovery": lambda: release,
    }
    if config is not None:
        kwargs["iterative_config"] = config
    result = orchestration._run_v7_h4_exact_side_full_formal(**kwargs)
    effective = captured["config"]
    assert str(effective.ksp_type).lower() == expected["ksp_type"]
    assert effective.restart == expected["restart"]
    assert effective.fixed_preconditioner is expected["fixed"]
    assert result["solve"]["restart"] == expected["restart"]
    if config is not None:
        assert result["solve"]["max_it"] == 4000
        assert result["solve"]["threshold"] == 5.0e-9


@pytest.mark.parametrize(
    "outer_probe_config",
    [None, task041.task041_consumer_iterative_config()],
)
def test_run_v5_probe_boundary_preserves_default_and_task041_config(
    monkeypatch, outer_probe_config
):
    class Destroyable:
        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    class FakeAction:
        def __init__(self):
            self.operator = Destroyable()
            self.woodbury = SimpleNamespace(mark_borrowed_matrices_released=lambda: None)
            self.diagnostics = {
                "direct_factor_count": 1,
                "destroyed": False,
                "woodbury": {
                    "streaming_w_storage": False,
                    "F_H_matrices_released": True,
                    "W_resident": True,
                    "C_action_resident": False,
                    "C_action_owned": False,
                },
            }

        def destroy(self):
            self.diagnostics["direct_factor_count"] = 0
            self.diagnostics["destroyed"] = True

    class FakeContext(Destroyable):
        def __init__(self):
            super().__init__()
            self.inventory = {"modal_schur": {"status": "ready"}}

    class FakePC:
        def setType(self, value):
            self.type = value

        def setPythonContext(self, value):
            self.context = value

    class FakeKSP:
        Type = SimpleNamespace(GMRES="gmres", FGMRES="fgmres")
        instances: ClassVar[list] = []

        def __init__(self):
            self.pc = FakePC()
            self.initial_guess_calls = []
            self.tolerance_calls = []
            self.destroyed = False
            type(self).instances.append(self)

        def create(self, comm):
            self.comm = comm
            return self

        def setOperators(self, value):
            self.operator = value

        def setType(self, value):
            self.ksp_type = value

        def setGMRESRestart(self, value):
            self.restart = value

        def setPCSide(self, value):
            self.pc_side = value

        def setInitialGuessNonzero(self, value):
            self.initial_guess_calls.append(value)

        def setTolerances(self, **values):
            self.tolerance_calls.append(values)

        def getPC(self):
            return self.pc

        def setUp(self):
            self.setup_called = True

        def getType(self):
            return self.ksp_type

        def destroy(self):
            self.destroyed = True

    monkeypatch.setattr(
        orchestration,
        "PETSc",
        SimpleNamespace(
            KSP=FakeKSP,
            PC=SimpleNamespace(
                Type=SimpleNamespace(PYTHON="python"),
                Side=SimpleNamespace(RIGHT="right"),
            ),
        ),
    )
    monkeypatch.setattr(orchestration, "collective_heap_cleanup", lambda comm: {"collective_call_completed": True})
    monkeypatch.setattr(
        orchestration,
        "_v5_side_matrix_inventory",
        lambda side: {name: {"status": "fake"} for name in ("F", "C", "D", "H")},
    )
    monkeypatch.setattr(orchestration, "_petsc_matrix_stats", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        orchestration,
        "_build_research_explicit_side_components",
        lambda system: SimpleNamespace(F=object(), C=object(), D=object(), H=object()),
    )
    monkeypatch.setattr(
        orchestration,
        "_destroy_v5_side_components",
        lambda side, retain_d=False: {
            "H": True,
            "C": True,
            "F": True,
            "D": True,
            "D_retained": bool(retain_d),
        },
    )
    monkeypatch.setattr(
        orchestration,
        "create_research_exact_side_lu_action",
        lambda *args, **kwargs: FakeAction(),
    )
    monkeypatch.setattr(
        orchestration,
        "create_research_exact_side_lu_block_ldu_preconditioner",
        lambda *args, **kwargs: FakeContext(),
    )
    monkeypatch.setattr(
        orchestration,
        "create_hybrid_assembled_block_action",
        lambda *args, **kwargs: (Destroyable(), Destroyable()),
    )
    side = SimpleNamespace()
    coupling_side = SimpleNamespace(
        projection=object(), positive_traction=object(), negative_traction=object()
    )
    setup = SimpleNamespace(
        bottom=side,
        top=SimpleNamespace(),
        coupling=SimpleNamespace(bottom=coupling_side, top=coupling_side),
    )
    markers = []
    result = orchestration.run_v5_h4_exact_side_setup_only(
        setup,
        object(),
        comm=SimpleNamespace(rank=0, size=1),
        marker_callback=lambda stage, detail: markers.append((stage, detail)),
        sampled_column_contract={"columns": [0], "roles": {"0": ["probe"]}, "sha256": "a" * 64},
        full_formal_runner=lambda **kwargs: {"status": "full_formal_completed"},
        outer_probe_config=outer_probe_config,
    )
    ksp = FakeKSP.instances[-1]
    expected_type = "gmres" if outer_probe_config is None else "fgmres"
    expected_restart = 10 if outer_probe_config is None else 90
    assert ksp.ksp_type == expected_type
    assert ksp.restart == expected_restart
    assert ksp.pc_side == "right"
    assert ksp.destroyed is True
    if outer_probe_config is None:
        assert ksp.initial_guess_calls == []
        assert ksp.tolerance_calls == []
        assert result["outer_ksp"]["ksp_profile"] == "v5_exact_side_fixed_pc_gmres10"
        released = [detail for stage, detail in markers if stage == "outer_setup_probe_ksp_released"]
        assert released[-1]["formal_ksp_profile"] == "gmres_restart10"
    else:
        assert ksp.initial_guess_calls == [False]
        assert ksp.tolerance_calls == [{"rtol": 5.0e-9, "atol": 0.0, "max_it": 4000}]
        assert result["outer_ksp"]["max_it"] == 4000
        assert result["outer_ksp"]["threshold"] == 5.0e-9
        assert result["outer_ksp"]["initial_guess"] == "zero"


def test_task041_consumer_configuration_and_fresh_command():
    config = task041.task041_consumer_iterative_config()
    assert isinstance(config, HybridBlockLduIterativeConfig)
    assert {
        "ksp_type": config.ksp_type,
        "restart": config.restart,
        "max_it": config.max_it,
        "threshold": config.threshold,
        "initial_guess": config.initial_guess,
        "fixed_preconditioner": config.fixed_preconditioner,
    } == {
        "ksp_type": "fgmres",
        "restart": 90,
        "max_it": 4000,
        "threshold": 5.0e-9,
        "initial_guess": "zero",
        "fixed_preconditioner": False,
    }
    command = task041.build_task041_consumer_command(
        "/repo/.venv/bin/python",
        task041.TASK041_INPUT,
        "producer/manifest.json",
        "producer/packet_identity.json",
        "a" * 64,
        "consumer-root",
        "b" * 40,
    )
    assert command[:4] == ["mpiexec", "-n", "1", "/repo/.venv/bin/python"]
    assert "--phase" in command and task041.TASK041_CONSUMER_PHASE in command
    assert "--packet-manifest" in command
    assert "--exact-spool-root" not in command
    producer_command = task041.build_task041_mode_prep_command(
        "/repo/.venv/bin/python",
        task041.TASK041_INPUT,
        "producer-root",
        "b" * 40,
    )
    assert producer_command[:4] == [
        "mpiexec",
        "-n",
        "1",
        "/repo/.venv/bin/python",
    ]


@pytest.mark.parametrize(
    ("filename", "model_id", "mode_count"),
    (
        (
            "3nm_p6h3_m800_mpi8.dat",
            "task041_3nm_exact_side_hybrid_iterative_p6h3_m800",
            800,
        ),
        (
            "3nm_p6h3_m1200_mpi8.dat",
            "task041_3nm_exact_side_hybrid_iterative_p6h3_m1200",
            1200,
        ),
    ),
)
def test_task041_shortwave_identity_and_mpi8_child_argv(
    filename: str, model_id: str, mode_count: int
):
    input_path = ROOT / "input/official/task041" / filename
    specification = load_and_resolve(input_path)
    identity = task041.build_task041_shortwave_packet_identity(
        specification,
        specification.as_jsonable(),
        "a" * 40,
        resolved_config_sha256(specification),
    )
    assert identity["schema"] == "task041.selected_mode_packet.identity.v2"
    assert identity["model_id"] == model_id
    assert identity["mode_count"] == mode_count
    assert identity["requested_modes_per_direction"] == mode_count
    assert identity["mpi_size"] == 8
    packet._require_task041_identity(identity)
    missing_partition = {
        key: value
        for key, value in identity.items()
        if key != "cross_section_partition"
    }
    with pytest.raises(ValueError, match="cross_section_partition"):
        packet._require_task041_identity(missing_partition)
    command = task041.build_task041_shortwave_mode_prep_command(
        "/repo/.venv/bin/python",
        specification,
        "producer-root",
        "a" * 40,
    )
    assert command[:4] == ["mpiexec", "-n", "8", "/repo/.venv/bin/python"]
    assert command[command.index("--input") + 1] == str(specification.source_path)


def test_fresh_sampled_contract_is_bound_to_current_manifest(tmp_path):
    identity = {
        "mode_count": 480,
        "mpi_size": 1,
        "scope": "task041_5nm_p6h4_m480_mpi1",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text("fresh packet", encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    contract = task041._task041_consumer_sampled_column_contract(
        identity, manifest, digest
    )
    assert contract["columns"] == list(task041.TASK041_CONSUMER_SAMPLE_COLUMNS)
    assert contract["fresh_packet_binding"]["packet_manifest_sha256"] == digest
    binding_payload = {
        key: contract["fresh_packet_binding"][key]
        for key in (
            "binding_semantics",
            "sampled_column_contract_sha256",
            "packet_identity_canonical_json",
            "packet_identity_sha256",
            "packet_manifest_sha256",
        )
    }
    assert hashlib.sha256(
        json.dumps(binding_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == contract["fresh_packet_binding"]["binding_sha256"]
    assert "manifest" not in contract["fresh_packet_binding"]
    assert contract["sha256"] == task041.TASK041_CONSUMER_SAMPLE_CONTRACT_SHA256


@pytest.mark.parametrize("order_case", ("valid", "missing", "extra", "duplicate"))
def test_consumer_authority_gate_is_recomputed_from_fresh_authority(
    tmp_path, order_case
):
    authority_path = tmp_path / "v3_7_hybrid_authority.json"
    source_sha = "b" * 40
    physical_sha = "c" * 64
    external_keys = [
        {
            "side": "bottom",
            "m": 0,
            "n": 0,
            "polarization": "s",
        },
        {
            "side": "bottom",
            "m": 1,
            "n": 0,
            "polarization": "p",
        },
    ]
    extra_key = {
        "side": "top",
        "m": 0,
        "n": 0,
        "polarization": "p",
    }
    external_orders_cases = {
        "valid": external_keys,
        "missing": external_keys[:1],
        "extra": [*external_keys, extra_key],
        "duplicate": [*external_keys, external_keys[0]],
    }
    identity = {
        "source_sha": source_sha,
        "physical_sha256": physical_sha,
        "model_id": "task041_test_model",
        "mpi_size": 1,
        "mode_count": 480,
        "external_keys": {
            "count": len(external_keys),
            "sha256": task041._task041_canonical_mode_keys_sha256(external_keys),
        },
    }
    authority_path.write_text(
        json.dumps(
            {
                "source_sha": source_sha,
                "physical_model_sha256": physical_sha,
                "model_id": identity["model_id"],
                "mpi_size": 1,
                "requested_modes": 480,
                "external_mode_inventory": {
                    "keys": list(reversed(external_keys))
                },
                "canonical": {
                    side: {
                        "roles": {
                            "active_trace": {"pass": True},
                            "full_fe": {"pass": True},
                        }
                    }
                    for side in ("bottom", "top")
                },
                "external_orders": external_orders_cases[order_case],
                "grid_payload": {
                    "arrays": {
                        name: {
                            "shape": [1],
                            "bytes": 1,
                            "sha256": "a" * 64,
                        }
                        for name in ("E_V_per_m", "H_A_per_m")
                    }
                },
                "interface_projection": 1.0e-9,
                "traction": {
                    "bottom": {"relative_residual": 1.0e-9},
                    "top": {"relative_residual": 1.0e-9},
                },
                "closure": 1.0e-6,
                "observables": {
                    "R_total": 0.1,
                    "T_total": 0.8,
                    "A_balance": 0.2,
                    "A_volume": 0.2,
                },
            }
        ),
        encoding="utf-8",
    )
    formal = {
        "solve": {
            "converged_reason": 1,
            "postsolve": {
                key: 1.0e-9
                for key in (
                    "reported_relative_residual",
                    "global_true_relative_residual",
                    "bottom_true_relative_residual",
                    "top_true_relative_residual",
                    "modal_true_relative_residual",
                )
            },
        },
        "recovery": {
            "pass": True,
            "physics_pass": True,
            "recovery_pass": True,
            "reports": {
                side: {
                    "external_q": {
                        "pass": False,
                        "auxiliary_relative_residual": 1.0e-12,
                    }
                }
                for side in ("bottom", "top")
            },
            "integrated_checker": {
                "status": "not_available",
                "pass": False,
            },
        },
    }
    gates = task041._task041_consumer_authority_gate(
        authority_path, formal, identity
    )
    expected_pass = order_case == "valid"
    assert gates["pass"] is expected_pass
    assert gates["ksp_reason_pass"] is True
    assert gates["authority_identity"]["pass"] is True
    assert gates["external_key_binding_pass"] is True
    assert gates["external_orders_key_binding_pass"] is expected_pass
    assert gates["external_q_residuals"] == {
        "bottom": 1.0e-12,
        "top": 1.0e-12,
    }
    assert gates["integrated_checker"]["status"] == "not_available"


@pytest.mark.parametrize(
    ("after_rss", "should_recover"),
    [(50, True), (100, False)],
)
def test_run_task041_consumer_full_mock_keeps_release_and_authority_evidence(
    monkeypatch, tmp_path, after_rss, should_recover
):
    @dataclass
    class FakeProfile:
        name: str = "task041-test-profile"

    class Comm:
        rank = 0
        size = 1

        @staticmethod
        def Barrier():
            return None

    source_sha = "b" * 40
    manifest_sha = "a" * 64
    external_key = {
        "side": "bottom",
        "m": 0,
        "n": 0,
        "polarization": "s",
    }
    identity = {
        "schema": "task041.selected_mode.identity.v1",
        "scope": "task041_5nm_p6h4_m480_mpi1",
        "source_sha": source_sha,
        "input_sha256": "c" * 64,
        "resolved_sha256": "d" * 64,
        "physical_sha256": "e" * 64,
        "wavelength_nm": 5.0,
        "model_id": "task041_5nm_exact_side_hybrid_iterative_p6h4_m480",
        "run_id": "task041_5nm_p6h4_m480_mpi1",
        "mode_count": 480,
        "mpi_size": 1,
        "external_keys": {
            "count": 1,
            "sha256": task041.canonical_mode_keys_sha256([external_key]),
        },
    }
    normalized = {"model_id": identity["model_id"], "run_id": identity["run_id"]}
    fake_modal_cfg = SimpleNamespace(name="task041-modal-cfg")

    class FakeCfg:
        def __deepcopy__(self, memo):
            del memo
            return fake_modal_cfg

    fake_cfg = FakeCfg()
    specification = SimpleNamespace(
        input_sha256=identity["input_sha256"],
        physical_model_sha256=identity["physical_sha256"],
        as_jsonable=lambda: normalized,
    )
    packet_manifest = tmp_path / "fresh" / "manifest.json"
    packet_manifest.parent.mkdir()
    packet_manifest.write_text("fresh packet", encoding="utf-8")
    packet_identity = tmp_path / "fresh" / "identity.json"
    packet_identity.write_text(json.dumps(identity), encoding="utf-8")
    captured = {"setup": {}, "run_v5": {}, "recovery_called": False}
    resource_state = {"after": False}

    def fake_resource_snapshot():
        rss = after_rss if resource_state["after"] else 100
        return {
            "process_tree": {"rss_bytes": rss, "swap_bytes": 0},
            "memory_authority_bytes": rss,
            "job_no_swap": True,
        }

    class FakeSetup:
        qep_release: ClassVar = {"qep_calls": 0, "consumer_qep_required": False}
        bottom = SimpleNamespace()
        top = SimpleNamespace()
        coupling = SimpleNamespace(internal_unknown_count=0)

    setup = FakeSetup()

    def fake_build_setup(**kwargs):
        captured["setup"].update(kwargs)
        kwargs["detail_stage_callback"](
            "selected_mode_packet_consumed", {"source": "fake setup"}
        )
        return setup

    def fake_authority():
        return {
            "source_sha": identity["source_sha"],
            "physical_model_sha256": identity["physical_sha256"],
            "model_id": identity["model_id"],
            "mpi_size": 1,
            "requested_modes": 480,
            "external_mode_inventory": {"keys": [external_key]},
            "canonical": {
                side: {
                    "roles": {
                        "active_trace": {"pass": True},
                        "full_fe": {"pass": True},
                    }
                }
                for side in ("bottom", "top")
            },
            "external_orders": [
                external_key
            ],
            "grid_payload": {
                "arrays": {
                    name: {"shape": [1], "bytes": 1, "sha256": "f" * 64}
                    for name in ("E_V_per_m", "H_A_per_m")
                }
            },
            "interface_projection": 1.0e-9,
            "traction": {
                "bottom": {"relative_residual": 1.0e-9},
                "top": {"relative_residual": 1.0e-9},
            },
            "closure": 1.0e-6,
            "observables": {
                "R_total": 0.1,
                "T_total": 0.8,
                "A_balance": 0.1,
                "A_volume": 0.1,
            },
        }

    solve_report = {
        "status": "completed",
        "pass": True,
        "converged_reason": 1,
        "postsolve": {
            key: 1.0e-9
            for key in (
                "reported_relative_residual",
                "global_true_relative_residual",
                "bottom_true_relative_residual",
                "top_true_relative_residual",
                "modal_true_relative_residual",
            )
        },
    }
    recovery = {
        "pass": True,
        "physics_pass": True,
        "recovery_pass": True,
        "reports": {
            side: {
                "external_q": {
                    "pass": False,
                    "auxiliary_relative_residual": 1.0e-12,
                }
            }
            for side in ("bottom", "top")
        },
        "integrated_checker": {"status": "not_available", "pass": False},
    }

    def fake_v7(**kwargs):
        callback = kwargs["marker_callback"]
        callback("outer_solve_begin", {"ksp_type": "fgmres", "restart": 90})
        callback("outer_solve_ready", {"solve_report": solve_report})
        release = kwargs["release_before_recovery"]()
        callback("outer_solve_objects_cleanup", {"release": release})
        if not release["rss_drop"]["pass"]:
            callback("solution_snapshot_destroyed", {"source": "fake v7 finally"})
            return {
                "status": "full_formal_lifecycle_failure",
                "solve": solve_report,
                "recovery": "not_run",
                "release_before_recovery": release,
            }
        callback("recovery_physics_begin", {})
        recovery_result = kwargs["recovery_runner"](
            kwargs["setup"],
            kwargs["layout"],
            object(),
            kwargs["run_directory"],
            kwargs["producer"],
        )
        callback("recovery_detail", {"source": "fake recovery report"})
        callback("recovery_physics_end", {"recovery": recovery_result})
        callback("solution_snapshot_destroyed", {"source": "fake v7 finally"})
        authority_path = (
            Path(kwargs["run_directory"])
            / "numerical_output"
            / "v3_7_hybrid_authority.json"
        )
        authority_path.parent.mkdir(parents=True, exist_ok=True)
        authority_path.write_text(json.dumps(fake_authority()), encoding="utf-8")
        return {
            "status": "full_formal_completed",
            "solve": solve_report,
            "recovery": recovery_result,
            "release_before_recovery": release,
            "authority_path": str(authority_path),
        }

    def fake_run_v5(setup_arg, layout_arg, **kwargs):
        captured["run_v5"].update(kwargs)
        formal = kwargs["full_formal_runner"](
            setup=setup_arg,
            layout=layout_arg,
            operator=object(),
            context=object(),
            comm=Comm(),
            marker_callback=kwargs["marker_callback"],
            release_before_recovery=lambda: (
                resource_state.__setitem__("after", True)
                or {
                    "factor_cleanup_pass": True,
                    "actions_destroyed": True,
                    "component_cleanup_pass": True,
                    "collective_heap_cleanup": {
                        "collective_call_completed": True
                    },
                    "factor_count_after_cleanup": {"bottom": 0, "top": 0},
                }
            ),
        )
        return {"full_formal": formal}

    monkeypatch.setattr(task041, "_environment_snapshot", lambda: {"marker": "1"})
    monkeypatch.setattr(task041, "_memavailable_bytes", lambda: 10**15)
    monkeypatch.setattr(task041, "_resource_snapshot", fake_resource_snapshot)
    monkeypatch.setattr(task041, "load_and_resolve", lambda path: specification)
    monkeypatch.setattr(
        task041,
        "simulation_config_3d_from_normalized",
        lambda payload: fake_cfg,
    )
    monkeypatch.setattr(task041, "task041_profile_errors", lambda payload: ())
    monkeypatch.setattr(task041, "resolved_config_sha256", lambda spec: "d" * 64)
    monkeypatch.setattr(task041, "build_task041_packet_identity", lambda *args: identity)
    monkeypatch.setattr(
        task041,
        "_task041_consumer_sampled_column_contract",
        lambda *args: {
            "columns": [0],
            "roles": {"0": ["fresh"]},
            "sha256": "f" * 64,
            "source": "fresh_packet_contract",
            "fresh_packet_binding": {
                "binding_semantics": "path_neutral_identity_and_manifest"
            },
        },
    )
    monkeypatch.setattr(task041, "_task041_consumer_profile", lambda: FakeProfile())
    monkeypatch.setattr(
        iterative_runner, "build_frozen_m10_setup", fake_build_setup
    )
    monkeypatch.setattr(
        iterative_runner,
        "release_frozen_m10_objects",
        lambda *args: {"pass": True},
    )
    monkeypatch.setattr(HybridAugmentedLayout, "build", staticmethod(lambda *args: object()))
    monkeypatch.setattr(orchestration, "run_v5_h4_exact_side_setup_only", fake_run_v5)
    monkeypatch.setattr(orchestration, "_run_v7_h4_exact_side_full_formal", fake_v7)
    monkeypatch.setattr(
        orchestration,
        "run_v3_7_recovery_runner",
        lambda *args, **kwargs: (captured.__setitem__("recovery_called", True) or recovery),
    )
    result = task041.run_task041_consumer(
        input_path="input.dat",
        packet_manifest=packet_manifest,
        packet_identity=packet_identity,
        packet_manifest_sha256=manifest_sha,
        run_directory=tmp_path / "consumer",
        source_sha=source_sha,
        comm=Comm(),
    )
    assert captured["setup"]["exact_one_cell_work_dir"].name == "exact_one_cell"
    assert captured["setup"]["cfg_override"] is fake_cfg
    assert captured["setup"]["modal_cfg_override"] is fake_modal_cfg
    assert captured["setup"]["selected_mode_packet_identity"] is identity
    assert captured["run_v5"]["v6_profile"] is False
    assert captured["run_v5"]["exact_spool_root"] is None
    assert captured["run_v5"]["packet_identity"] is identity
    assert captured["run_v5"]["sampled_column_contract"]["source"] == (
        "fresh_packet_contract"
    )
    config = captured["run_v5"]["outer_probe_config"]
    assert (config.ksp_type, config.restart, config.max_it, config.threshold) == (
        "fgmres",
        90,
        4000,
        5.0e-9,
    )
    observed = result["markers"]["observed"]
    marker_records = [
        json.loads(line)
        for line in (tmp_path / "consumer" / "markers.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    setup_marker = next(
        marker for marker in marker_records if marker["stage"] == "system_setup_stage"
    )
    assert setup_marker["detail"]["name"] == "selected_mode_packet_consumed"
    assert observed.index("system_setup_stage") < observed.index("system_ready")
    assert [
        task041.TASK041_CONSUMER_MARKER_SEQUENCE.index(stage)
        for stage in observed
    ] == sorted(
        task041.TASK041_CONSUMER_MARKER_SEQUENCE.index(stage)
        for stage in observed
    )
    for index, stage in enumerate(observed):
        if stage == "recovery_stage":
            assert index > observed.index("recovery_physics_begin")
    for destroy_stage in (
        "outer_ksp_destroyed",
        "bottom_top_factors_destroyed",
        "large_matrices_destroyed",
    ):
        assert destroy_stage in observed
    assert observed[-1] == "final_cleanup_complete"
    assert observed.index("outer_solve_objects_cleanup") < observed.index(
        "rss_drop_confirmed"
    )
    assert result["lifecycle"]["rss_drop_pass"] is should_recover
    assert result["lifecycle"]["rss_marker_emitted"] is True
    assert captured["recovery_called"] is should_recover
    rss_drop = result["lifecycle"]["outer_release"]["rss_drop"]
    assert rss_drop["rss_measurement"] == "process_tree.rss_bytes"
    assert rss_drop["before_high_water_memory_authority_bytes"] == 100
    assert rss_drop["after_cleanup_memory_authority_bytes"] == after_rss
    if should_recover:
        assert observed.index("rss_drop_confirmed") < observed.index("recovery_started")
        assert "recovery_stage" in observed
        assert result["status"] == "task041_consumer_completed"
        assert result["official_rta"]["status"] == "measured"
        assert result["gates"]["external_q_residuals"] == {
            "bottom": 1.0e-12,
            "top": 1.0e-12,
        }
        packet = json.loads(
            (tmp_path / "consumer" / "minimal_recovery_packet.json").read_text()
        )
        assert packet["json_contains_solution"] is False
        assert packet["snapshot_location"] == "process_memory"
        assert "official_outputs_written" in observed
    else:
        assert result["status"] == "full_formal_lifecycle_failure"
        assert result["classification"] == "TASK041_CONSUMER_LIFECYCLE_FAILURE"
        assert result["formal"]["recovery"] == "not_run"
        assert result["gates"]["status"] == (
            "not_run_due_to_formal_lifecycle_failure"
        )
        assert result["lifecycle"]["outer_release"]["rss_drop"]["pass"] is False


def test_task041_resource_gate_uses_authority_fields():
    sample = {
        "memory_authority_bytes": 1,
        "job_no_swap": True,
        "process_tree": {
            "rss_bytes": task041.TASK041_HARD_MEMORY_BYTES + 1,
            "swap_bytes": 99,
        },
    }
    started = time.monotonic()
    task041._check_resource(sample, started)
    with pytest.raises(task041.Task041ModePrepError):
        task041._check_resource(
            {
                "memory_authority_bytes": task041.TASK041_HARD_MEMORY_BYTES + 1,
                "job_no_swap": True,
                "process_tree": {"rss_bytes": 1, "swap_bytes": 0},
            },
            started,
        )
    with pytest.raises(task041.Task041ModePrepError):
        task041._check_resource(
            {
                "memory_authority_bytes": 1,
                "job_no_swap": False,
                "process_tree": {"rss_bytes": 1, "swap_bytes": 0},
            },
            started,
        )


def test_recovery_runner_returns_real_reports(monkeypatch, tmp_path):
    class Comm:
        rank = 0

    comm = Comm()
    mesh = SimpleNamespace(comm=comm)
    setup = SimpleNamespace(
        bottom=SimpleNamespace(b=object(), local_mesh=SimpleNamespace(mesh=mesh)),
        top=SimpleNamespace(b=object()),
    )

    class Layout:
        @staticmethod
        def split(*args):
            del args
            return object(), object(), object()

    reports = {
        "bottom": {
            "external_q": {
                "pass": True,
                "auxiliary_relative_residual": 1.0e-12,
            }
        },
        "top": {
            "external_q": {
                "pass": True,
                "auxiliary_relative_residual": 1.0e-12,
            }
        },
    }
    recovery = SimpleNamespace(
        recovery_pass=True,
        reports=reports,
        destroy=lambda: None,
    )
    physics = SimpleNamespace(physics_pass=True)
    monkeypatch.setattr(orchestration, "recover_frozen_m10", lambda *args, **kwargs: recovery)
    monkeypatch.setattr(
        orchestration, "run_frozen_m10_physics", lambda *args, **kwargs: physics
    )
    monkeypatch.setattr(
        orchestration, "_write_v3_7_candidate_authority", lambda *args: None
    )
    result = orchestration.run_v3_7_recovery_runner(
        setup,
        Layout(),
        object(),
        tmp_path,
        {},
        run_integrated_checker=False,
    )
    assert result["reports"] is reports


def test_task041_required_markers_and_resource_gate_are_explicit():
    sequence = task041.TASK041_CONSUMER_MARKER_SEQUENCE
    assert sequence.index("system_ready") < sequence.index("outer_solve_begin")
    assert sequence.index("outer_solve_ready") < sequence.index(
        "true_residual_complete"
    )
    assert sequence.index("true_residual_complete") < sequence.index(
        "minimal_recovery_packet_saved"
    )
    assert sequence.index("rss_drop_confirmed") < sequence.index("recovery_started")


def test_authority_parameterization_uses_task041_mpi1_and_modes(tmp_path):
    class Comm:
        rank = 0

        @staticmethod
        def barrier():
            return None

    physics = SimpleNamespace(
        own_grid={"status": "measured"},
        external_orders=[
            {
                "side": "bottom",
                "m": 0,
                "n": 0,
                "polarization": "s",
            }
        ],
        interface_e_projection={"combined_relative_residual": 1.0e-9},
        energy={"R": 0.1, "T": 0.8, "A": 0.1, "A_volume": 0.1, "closure": 0.0},
        traction={"bottom": {"relative_dual": 1.0e-9}, "top": {"relative_dual": 1.0e-9}},
        canonical={"status": "measured"},
    )
    path = orchestration._write_v3_7_candidate_authority(
        tmp_path,
        physics,
        {
            "consumer_model_id": "task041_5nm_p6h4_m480_mpi1",
            "consumer_source_sha": "a" * 40,
            "physical_model_sha256": "b" * 64,
            "mpi_size": 1,
            "requested_modes": 480,
            "qualification_scope": "task041_5nm_p6h4_m480_mpi1",
            "canonical_authority": True,
        },
        Comm(),
    )
    authority = json.loads(path.read_text(encoding="utf-8"))
    assert authority["mpi_size"] == 1
    assert authority["requested_modes"] == 480
    assert authority["canonical"] == {"status": "measured"}
    fallback_path = orchestration._write_v3_7_candidate_authority(
        tmp_path / "task39-fallback",
        physics,
        {
            "consumer_model_id": "task039_legacy",
            "consumer_source_sha": "c" * 40,
            "physical_model_sha256": "d" * 64,
        },
        Comm(),
    )
    fallback = json.loads(fallback_path.read_text(encoding="utf-8"))
    assert fallback["mpi_size"] == 8
    assert fallback["requested_modes"] == 480
