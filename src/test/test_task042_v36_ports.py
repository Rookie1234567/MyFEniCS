"""Pure bounded supply/adjoint, isolation and actual public-entry regressions."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners.task042_shared import write_json
from src.solvers.bounded_port_provider import (
    BoundedPortAction,
    BoundedPortProvider,
    PortFunctional,
)
from src.solvers.port_preparation_window import PreparationWindow


class Source:
    def __init__(self, n=9, count=5, *, owner=None, empty=False):
        self.n, self.count, self.owner, self.empty = n, count, owner or (0, n), empty
        self.key = "fixture-source-v1"
        self.rows = [
            {
                "mode_index": i,
                "side": "top" if i < count // 2 else "bottom",
                "m": i,
                "n": 0,
                "polarization": "s",
            }
            for i in range(count)
        ]
        self.keys = [(i, r["side"], r["m"], 0, "s") for i, r in enumerate(self.rows)]
        self.fault = None

    def upper_bytes(self, index):
        return 48 * (0 if self.empty else self.owner[1] - self.owner[0]) + 8

    def __call__(self, index, source_identity):
        if source_identity != self.key:
            raise ValueError("source changed")
        rng = np.random.default_rng(423600 + index)
        C = rng.normal(size=self.n) + 1j * rng.normal(size=self.n)
        D = rng.normal(size=self.n) + 1j * rng.normal(size=self.n)
        a, b = self.owner
        rows = (
            np.arange(a, b, dtype=np.int64) if not self.empty else np.empty(0, np.int64)
        )
        cs, ds = C[rows].copy(), D[rows].copy()
        for array in (rows, cs, ds):
            array.flags.writeable = False
        identity = deepcopy(self.rows[index])
        if self.fault == "order":
            identity["mode_index"] += 1
        if self.fault == "mutable":
            cs.flags.writeable = True
        return PortFunctional(
            self.keys[index], rows, cs, rows, ds, index + 1.3, identity
        )

    def expected_hash(self, index):
        return "0" * 64 if self.fault == "hash" else None


def action_for(source, **kwargs):
    p = BoundedPortProvider(
        source.keys,
        source.rows,
        source,
        source_identity=source.key,
        global_rows=source.n,
        ownership_range=source.owner,
        max_modes=2,
        cache_bytes=2**20,
        **kwargs,
    )
    return BoundedPortAction(p)


def explicit(source):
    A = np.zeros((source.n, source.n), complex)
    C, D = [], []
    for i in range(source.count):
        f = source(i, source.key)
        A += np.outer(f.coupling_values, f.projection_values) / f.normalization_h
        C.append(f.coupling_values)
        D.append(f.projection_values / f.normalization_h)
    return A, np.column_stack(C), np.row_stack(D)


def test_nonhermitian_two_sides_forward_adjoint_complete_output_and_zero():
    source = Source()
    A, C, D = explicit(source)
    assert np.linalg.norm(A - A.conj().T) > 1
    action = action_for(source)
    rng = np.random.default_rng(423611)
    x = rng.normal(size=9) + 1j * rng.normal(size=9)
    y = rng.normal(size=9) + 1j * rng.normal(size=9)
    alpha = rng.normal(size=5) + 1j * rng.normal(size=5)
    np.testing.assert_allclose(action.apply(x), A @ x, atol=1e-13)
    np.testing.assert_allclose(
        action.apply(y, adjoint=True), A.conj().T @ y, atol=1e-13
    )
    np.testing.assert_allclose(action.recover(x), D @ x, atol=1e-13)
    np.testing.assert_allclose(action.modal_rhs(alpha), C @ alpha, atol=1e-13)
    np.testing.assert_allclose(
        np.vdot(y, action.apply(x)),
        np.vdot(action.apply(y, adjoint=True), x),
        atol=1e-13,
    )
    np.testing.assert_allclose(
        action.apply((0.7 - 0.4j) * x), (0.7 - 0.4j) * action.apply(x), atol=1e-13
    )
    np.testing.assert_array_equal(
        action.apply(np.zeros(9, complex)), np.zeros(9, complex)
    )
    action.provider.clear()
    assert action.provider.stats["created_live_peak"] <= 2
    assert action.provider.stats["evictions"] > 0


@pytest.mark.parametrize(
    "fault,match", [("order", "identity"), ("hash", "hash"), ("mutable", "read-only")]
)
def test_loader_rejects_bad_inventory_numeric_hash_and_writable_values(fault, match):
    s = Source()
    s.fault = fault
    with pytest.raises(ValueError, match=match):
        action_for(s).apply(np.ones(9, complex))


def test_single_mode_capacity_refuses_before_source_allocation():
    s = Source()
    s.__call__ = lambda *args: pytest.fail("allocation before capacity")
    p = BoundedPortProvider(
        s.keys,
        s.rows,
        s,
        source_identity=s.key,
        global_rows=9,
        ownership_range=(0, 9),
        max_modes=2,
        cache_bytes=100,
    )
    with pytest.raises(MemoryError, match="surface-row tiling"):
        p.visit(lambda *args: None)
    assert p.stats["loads"] == 0


@pytest.mark.parametrize("retain_array", [False, True])
def test_consumer_cannot_accumulate_early_batches(retain_array):
    p = action_for(Source()).provider
    leak = []

    def consume(start, fs):
        if start == 0:
            leak.append(fs[0].coupling_values if retain_array else fs[0])

    with pytest.raises(RuntimeError, match="retained"):
        p.visit(consume)
    leak.clear()
    p.clear()


def test_empty_owner_collectives_not_skipped_and_safe_interruption_reentry():
    s = Source(owner=(0, 0), empty=True)
    counts = []
    action = action_for(s)
    action.reduce = lambda x: counts.append(len(x)) or x.copy()
    np.testing.assert_array_equal(
        action.apply(np.empty(0, complex)), np.empty(0, complex)
    )
    assert counts == [2, 2, 1]
    p = action_for(Source()).provider

    def interrupt(start, fs):
        if start == 2:
            raise InterruptedError("fixture boundary")

    with pytest.raises(InterruptedError):
        p.visit(interrupt)
    # No partial consumer output is accepted; replay starts at mode 0.
    p.visit(lambda *args: None)
    p.clear()


def test_source_invalidates_only_own_cache_not_old_windows():
    s = Source()
    a = action_for(s)
    a.apply(np.ones(9, complex))
    a.provider.invalidate("new")
    with pytest.raises(ValueError, match="source changed"):
        a.apply(np.ones(9, complex))


def fixture_window(tmp_path):
    w = PreparationWindow(tmp_path)
    w.snapshot = lambda: {
        "heavy_remaining_seconds": 1000.0,
        "total_remaining_seconds": 1500.0,
    }
    return w


def test_new_scope_phase_read_commit_failure_reentry_and_closed(tmp_path):
    w = fixture_window(tmp_path)
    first = tmp_path / "phase1"
    first.mkdir()
    w.begin("INVENTORY", first, "a" * 40)
    with pytest.raises(RuntimeError, match="active"):
        w.require_ready()
    row = {
        "elapsed_seconds": 1.5,
        "classification": "WORKER_FAILED",
        "leader_exit_code": 1,
        "descendants_cleared": True,
        "sampled_process_tree_rss_peak_bytes": 100,
        "sampled_process_tree_swap_peak_bytes": 0,
    }
    w.settle(row, first)
    second = tmp_path / "phase2"
    second.mkdir()
    w.begin("INVENTORY", second, "b" * 40)
    w.settle(dict(row, classification="COMPLETED", leader_exit_code=0), second)
    assert len(w.ledger()["runs"]) == 2 and w.charged_wall() == pytest.approx(
        3 + 0.326941663
    )
    book = w.ledger()
    book["closed"] = True
    write_json(w.LEDGER_PATH, book)
    with pytest.raises(RuntimeError, match="closed"):
        w.require_ready()


def test_closed_history_and_negative_verify_barrier_use_isolated_scope(
    tmp_path, monkeypatch
):
    from src.io import full_input_online as io
    from src.io.input_loader import InputError
    from src.solvers import neural_fe_blind_reference as ref

    monkeypatch.setattr(
        ref, "independent_physics", lambda *a, **kw: pytest.fail("reference read")
    )
    plan = tmp_path / "plan.json"
    write_json(plan, {"action_sha256": "p", "physical_sha256": "q"})
    monkeypatch.setattr(io, "PLAN_PATH", plan)
    monkeypatch.setattr(
        io,
        "plan_and_operator",
        lambda: (
            {"physical_model_sha256": "q"},
            {"geometry": {}, "incidence": {}, "finite_element": {}, "boundary": {}},
            SimpleNamespace(
                provenance={
                    "material_table_id": "SI_OPTICAL_CONSTANTS_USER_20260929_V1"
                }
            ),
            {"packet": {"sha256": "p"}},
        ),
    )
    w = fixture_window(tmp_path)
    monkeypatch.setattr(io.window, "require_live", w.require_live)
    monkeypatch.setattr(io.window, "ledger", w.ledger)
    monkeypatch.setattr(
        io,
        "read_result",
        lambda *args: ({"status": "ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT"}, None),
    )
    path = io.ROOT / "input/task042_neural_coarse_inverse/v35_verify.dat"
    with pytest.raises(InputError, match="requires original equation pass"):
        io.load_online(path)
    book = w.ledger()
    book["closed"] = True
    write_json(w.LEDGER_PATH, book)
    with pytest.raises(InputError, match="closed/active"):
        io.load_online(path)


@pytest.mark.parametrize("stage", ["INVENTORY", "COMPONENT", "CHECK", "DEPLOY"])
def test_actual_dat_schema_and_public_validate_entry(stage, capsys):
    from scripts.run_case import main
    from src.io.port_preparation import load_preparation

    files = {
        "INVENTORY": "v36_target_inventory.dat",
        "COMPONENT": "v36_port_component.dat",
        "CHECK": "v36_port_checker.dat",
        "DEPLOY": "v36_deployment_package.dat",
    }
    path = Path("input/task042_neural_coarse_inverse") / files[stage]
    spec = load_preparation(path)
    assert spec.derived["stage"] == stage and spec.derived["target_solve"] is False
    if stage == "COMPONENT":
        plan = json.loads(
            Path(
                "input/task042_neural_coarse_inverse/port_preparation_v36.json"
            ).read_text()
        )
        assert list(spec.geometry["cells"]) == [8, 6, 8]
        assert spec.physical_model_sha256 == plan["micro_physical_sha256"]
        assert (
            spec.physical_model_sha256
            != spec.derived["target_physical_contract_sha256"]
        )
    assert main([str(path), "--validate-only"]) == 0
    assert json.loads(capsys.readouterr().out)["target_solve"] is False


def test_target_geometry_material_and_formula_calibration_without_FE():
    from src.geometry.neural_micro_pilot import hexa_inventory
    from src.solvers.target_port_preparation import geometry_contract, target_config

    cfg, material = target_config()
    c = geometry_contract(cfg, material)
    assert c["regular_geometry"]["block_bounds_nm"] == [
        [16.5, 33.5],
        [0.0, 25.0],
        [0.0, 120.0],
    ]
    assert material.n == 0.999885140474 + 4.32477054e-6j
    assert c["epsilon_si"] == [material.epsilon.real, material.epsilon.imag]
    assert c["source_wavelength_nm"] == "0.699999988"
    h = hexa_inventory((8, 6, 8), 3)
    assert [
        h[k]
        for k in (
            "independent_trace_rows",
            "interior_rows",
            "full_fe_rows",
            "periodic_slaves",
        )
    ] == [18144, 13824, 34050, 2082]


def test_writer_preserves_mapping_no_large_json_and_atomic_rollback(tmp_path):
    from types import MappingProxyType

    p = tmp_path / "receipt.json"
    write_json(
        p,
        MappingProxyType(
            {
                "numeric": "separate NPZ",
                "physical_identity": MappingProxyType({"key": 1}),
            }
        ),
    )
    old = hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="large arrays"):
        write_json(p, {"big": np.ones(5000)})
    assert hashlib.sha256(p.read_bytes()).hexdigest() == old
