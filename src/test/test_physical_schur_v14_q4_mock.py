"""Small Q4 API/lifecycle smoke tests without starting a PDE."""

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

import src.runners.physical_p4_schur_v14 as v14


class _Vec:
    live = []

    def __init__(self, values):
        self.array = np.asarray(values, dtype=np.complex128).copy()
        self.destroyed = False
        type(self).live.append(self)

    def copy(self):
        return type(self)(self.array)

    def duplicate(self):
        return type(self)(np.zeros_like(self.array))

    def destroy(self):
        self.destroyed = True

    def getLocalSize(self):
        return int(self.array.size)

    def norm(self):
        return float(np.linalg.norm(self.array))

    def axpy(self, alpha, other):
        self.array[:] += alpha * other.array

    def set(self, value):
        self.array[:] = value


class _Runtime:
    def __init__(self, tmp_path):
        self.directory = tmp_path
        self.root = tmp_path
        self.source_sha = "a" * 40
        self.workflow_reserved_seconds = 14400.0
        self.contract = {
            "resources": {
                "stage_budgets": {
                    "Q4_ORIGINAL": {
                        "solve_seconds": 10800.0,
                        "workflow_seconds": 14400.0,
                    }
                },
                "pc_soft_seconds": 25.0,
                "pc_hard_seconds": 30.0,
            }
        }
        self.stop_requested = False
        self.pc_soft_stop_requested = False
        self.workspace = {}
        self.events = []

    def marker(self, name, facts=None):
        self.events.append((name, facts))

    def sample(self, label=None):
        self.events.append(("sample", label))
        return {"label": label, "rss_bytes": 1}

    def reserve_workspace(self, label, amount):
        self.workspace[str(label)] = int(amount)
        self.events.append(("reserve_workspace", str(label), int(amount)))

    def release_workspace(self, label):
        self.workspace.pop(str(label), None)
        self.events.append(("release_workspace", str(label)))

    def begin_outer_solve(self):
        self.events.append(("begin_outer_solve",))

    def finish_outer_solve(self):
        self.events.append(("finish_outer_solve",))

    def begin_pc(self, sequence):
        self.events.append(("begin_pc", int(sequence)))

    def finish_pc(self, *, completed=True):
        self.events.append(("finish_pc", bool(completed)))
        return {"completed": bool(completed), "hard_limit_exceeded": False}

    def workflow_clock_interval(self):
        return {"budget_seconds": 10.0}

    def set_phase(self, phase):
        self.events.append(("phase", str(phase)))


class _Core:
    internal = [object()] * 42
    factor_facts = {"internal": [], "interface": {}}


class _Pair:
    def audit(self):
        return {"rows": 1}


class _PC:
    def __init__(self):
        self.apply_count = 0
        self.native_A4_count = 0
        self.last_apply_facts = {}
        self.coarse_calls = []
        self.balanced = SimpleNamespace(
            total_counts={"C": 0}, total_operation_seconds={"C": 0.0}
        )
        self.ledger = SimpleNamespace(
            A_count=0, PH_count=0, audit_count=0, A_seconds=0.0, PH_seconds=0.0
        )

    def apply(self, source):
        self.apply_count += 1
        return source.copy()

    def destroy(self):
        pass


def _patch_q4_dependencies(monkeypatch, fail):
    import src.runners.physical_macro_v12 as macro
    import src.solvers.fullspace_same_mesh_hcurl_pmg_physical as physical
    import src.solvers.physical_balanced_fgmres as fgmres

    calls = {"reference": 0, "packets": [], "checkpoints": []}
    physical_sha = "p" * 64

    @contextmanager
    def live_stack(*_args, **_kwargs):
        yield {
            "schema": "mock-stack",
            "partition": SimpleNamespace(audit=lambda: {"rows": 1}),
            "core": _Core(),
            "fint": object(),
            "representative_facts": {},
            "delta_facts": {"current_ordered_mode_sha256": "m"},
            "local_audit": {},
            "action_checks": {},
            "candidate_facts": {},
            "paired_facts": {},
            "coarse_pair": _Pair(),
        }

    @contextmanager
    def balanced_adapter(*_args, **_kwargs):
        yield _PC(), {"h6": SimpleNamespace(apply_count=0), "light_facts": {}}

    def save_packet(directory, name, facts, *, runtime=None):
        calls["packets"].append((str(directory), name, facts))
        return {"path": str(directory / f"{name}.json"), "name": name}

    def load_reference(*_args, **_kwargs):
        calls["reference"] += 1
        return {
            "model": {"physical_sha": physical_sha, "mode_sha": "m"},
            "reference_output": {"R": 0.3},
            "reference_output_dir": str(v14.Path("reference")),
            "x_ref": np.ones(4, dtype=np.complex128),
        }

    def fake_checkpoint(*_args, **_kwargs):
        calls["checkpoints"].append(int(_args[2]))
        return {"iteration": int(_args[2]), "path": "checkpoint"}

    def fake_rhs(_fine):
        return _Vec([1.0, 2.0, 3.0, 4.0]), {"rhs_norm": 5.477}

    def fake_run(rhs, action, pc, *, checkpoint, **_kwargs):
        # Exercise both callback contracts: A6 returns an owned Vec and the
        # whole PC is balanced/closed between actions.
        action_value = action(rhs)
        action_value.destroy()
        pc_value = pc(rhs)
        pc_value.destroy()
        for iteration in (0, 32, 64):
            snapshot = rhs.copy() if not fail else rhs.duplicate()
            checkpoint(iteration, snapshot, 0.1 if fail else 1.0e-7)
            snapshot.destroy()
        solution = rhs.copy() if not fail else rhs.duplicate()
        return {
            "final_solution": solution,
            # The failure branch deliberately reports a passing KSP residual;
            # the independent post-KSP A6 action below must reject it.
            "final_true_residual": 1.0e-7,
            "iterations": 64,
            "reason": 4,
            "status": "TRUE_RESIDUAL_PASS",
            "screen": None,
            "snapshots": [
                {"iteration": i, "solve_seconds": float(i)}
                for i in (0, 32, 64)
            ],
            "matvec_count": 1,
            "pc_apply_count": 1,
            "explicit_action_count": 1,
            "elapsed_seconds": 1.0,
            "ksp_create_count": 1,
            "ksp_solve_count": 1,
            "ksp_destroy_count": 1,
            "screen_enabled": True,
            "restart": 32,
            "max_it": 2048,
            "zero_start": True,
        }

    monkeypatch.setattr(v14, "_v14_interface_live_stack", live_stack)
    monkeypatch.setattr(v14, "_v14_balanced_adapter", balanced_adapter)
    monkeypatch.setattr(v14, "_v14_operator_identity", lambda *_a, **_k: (
        {"ordered_mode_sha256": "m"}, "o" * 64
    ))
    monkeypatch.setattr(v14, "_save_packet", save_packet)
    monkeypatch.setattr(v14, "_v14_p6_field_comparison", lambda *_a: {
        "L2": {"absolute_error_norm": 0.0, "reference_norm": 1.0, "relative": 0.0},
        "scaled_curl": {"absolute_error_norm": 0.0, "reference_norm": 1.0, "relative": 0.0},
    })
    monkeypatch.setattr(v14, "_v14_history_facts", lambda *_a, **_k: {"status": "mock"})
    monkeypatch.setattr(v14, "_v14_resource_facts", lambda *_a, **_k: {"gate": True})
    monkeypatch.setattr(v14, "_v14_physical_checks", lambda *_a: {"all": True})
    monkeypatch.setattr(macro, "_load_reference_binding", load_reference)
    monkeypatch.setattr(macro, "_write_checkpoint", fake_checkpoint)
    monkeypatch.setattr(macro, "_compare_saved_output", lambda *_a, **_k: {})
    monkeypatch.setattr(physical, "build_physical_rhs", fake_rhs)
    monkeypatch.setattr(physical, "recover_p0_outputs", lambda *_a, **_k: {"R": 0.3})
    monkeypatch.setattr(fgmres, "run_balanced_fgmres", fake_run)
    return calls


@pytest.mark.parametrize("fail", [True, False])
def test_q4_mock_covers_residual_failure_and_success_cleanup(tmp_path, monkeypatch, fail):
    _Vec.live = []
    calls = _patch_q4_dependencies(monkeypatch, fail)
    runtime = _Runtime(tmp_path)
    common = {
        "cfg": SimpleNamespace(cell_notch=None),
        "fine": {
            "mode_sha256": "m",
            "dtn_action": SimpleNamespace(carrier=SimpleNamespace(global_rows=4)),
            "physical_action": SimpleNamespace(
                apply=lambda source, target: target.array.__setitem__(slice(None), source.array)
            ),
        },
    }
    resolved = {
        "provenance": {
            "input_sha256": "i" * 64,
            "physical_model_sha256": "p" * 64,
        },
    }
    predecessor = {"required_stage": "Q3_INTERFACE_CONTROL", "qualified": True}

    result = v14._v14_q4_q5_fullspace(
        runtime, common, resolved, stage="Q4_ORIGINAL", predecessor=predecessor
    )

    assert calls["reference"] == 1
    assert calls["checkpoints"] == [0, 32, 64]
    assert result["solver"]["field_checkpoint_records"]
    assert result["solver"]["field_checkpoint_records"][-1]["iteration"] == 64
    assert any(
        label == "q4_reference_load" and amount == 64 << 20
        for label, amount in (
            (event[1], event[2])
            for event in runtime.events
            if event[0] == "reserve_workspace"
        )
    )
    independent = next(
        index
        for index, event in enumerate(runtime.events)
        if event[0] == "q4_independent_final_residual_complete"
    )
    finished = next(
        index
        for index, event in enumerate(runtime.events)
        if event[0] == "finish_outer_solve"
    )
    assert finished > independent
    assert all(vector.destroyed for vector in _Vec.live)
    assert runtime.workspace == {}
    if fail:
        assert not result["official_result"]
        assert result["output_role"] == "diagnostic_solution_only"
    else:
        assert result["official_result"]
        assert result["output_role"] == "official"
