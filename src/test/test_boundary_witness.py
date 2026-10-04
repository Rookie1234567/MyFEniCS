"""Pure, complex, shared-row negatives for the new opt-in boundary path."""

import copy
from dataclasses import replace

import numpy as np
import pytest

from src.solvers.bounded_port_provider import BoundedPortProvider
from src.solvers.solver_consumer_contract import FIELDS, compare_fields
from src.solvers.tiled_port_action import PortTile, TiledPortAction
from src.test.test_task042_v36_ports import Source, explicit


class TileSource:
    def __init__(self, owner=(0, 9)):
        self.base = Source(owner=owner)
        self.rows = copy.deepcopy(self.base.rows)
        for i, row in enumerate(self.rows):
            row.update(projection_denominator=i + 1.3, tile_ids=["face-a", "face-b"])
        self.key = "tiles-complex-shared-v1"
        self.corrupt = None

    def tile_ids(self, i):
        return tuple(self.rows[i]["tile_ids"])

    def upper_bytes(self, i, t):
        return 9 * 48

    def load_tile(self, i, t, key):
        if key != self.key:
            raise ValueError("source")
        f = self.base(i, self.base.key)
        cr, pr = f.coupling_rows.copy(), f.projection_rows.copy()
        cv, pv = f.coupling_values.copy() / 2, f.projection_values.copy() / 2
        if self.corrupt == "phase":
            cv *= np.exp(0.31j)
        if self.corrupt == "conjugate":
            pv = pv.conj()
        if self.corrupt == "transpose":
            cv, pv = pv.copy(), cv.copy()
        for a in (cr, pr, cv, pv):
            a.flags.writeable = False
        return PortTile(t, cr, cv, pr, pv)


def action(source, **kw):
    return TiledPortAction(
        source.rows,
        source,
        source_identity=source.key,
        global_rows=9,
        ownership_range=source.base.owner,
        **kw,
    )


def test_shared_tiles_complete_complex_actions():
    s = TileSource()
    a = action(s)
    A, C, D = explicit(Source())
    rng = np.random.default_rng(423701)
    x = rng.normal(size=9) + 1j * rng.normal(size=9)
    y = rng.normal(size=9) + 1j * rng.normal(size=9)
    np.testing.assert_allclose(a.apply(x), A @ x, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        a.apply(y, adjoint=True), A.conj().T @ y, rtol=1e-12, atol=1e-12
    )
    np.testing.assert_allclose(a.recover(x), D @ x, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        a.modal_rhs(np.ones(5, complex)), C @ np.ones(5), rtol=1e-12, atol=1e-12
    )
    np.testing.assert_allclose(
        a.apply((0.3 - 0.7j) * x), (0.3 - 0.7j) * a.apply(x), rtol=1e-12, atol=1e-12
    )
    assert a.stats["numeric_cache_peak_bytes"] <= 432 and len(a.receipts) == 5
    assert not a.apply(np.zeros(9, complex)).any()


@pytest.mark.parametrize("fault", ["phase", "conjugate", "transpose"])
def test_bad_phase_or_conjugate_is_numerically_detected(fault):
    s = TileSource()
    s.corrupt = fault
    a = action(s)
    A, _, _ = explicit(Source())
    assert np.linalg.norm(a.apply(np.arange(9) + 1j) - (A @ (np.arange(9) + 1j))) > 1e-4


def test_bad_inventory_and_bound_before_creator():
    s = TileSource()
    s.rows[0]["tile_ids"] = ["face-a", "face-a"]
    with pytest.raises(ValueError, match="inventory"):
        action(s)
    s = TileSource()
    a = action(s, tile_bytes=4)
    with pytest.raises(MemoryError, match="capacity"):
        a.apply(np.ones(9, complex))
    assert a.stats["tile_loads"] == 0
    s = TileSource()
    a = action(s)
    s.rows[0]["tile_ids"].pop()
    with pytest.raises(ValueError, match="identity"):
        a.apply(np.ones(9, complex))


def test_tile_hash_and_H_replay():
    s = TileSource()
    s.expected_hash = lambda *_: "bad"
    with pytest.raises(ValueError, match="hash"):
        action(s).apply(np.ones(9, complex))
    s = TileSource()
    a = action(s)
    a.apply(np.ones(9, complex))
    a.identities[0]["projection_denominator"] += 1
    with pytest.raises(ValueError, match="identity"):
        a.apply(np.ones(9, complex))


def test_untiled_H_cache_hit_reload_and_invalidate():
    s = Source()
    p = BoundedPortProvider(
        s.keys,
        s.rows,
        s,
        source_identity=s.key,
        global_rows=9,
        ownership_range=(0, 9),
        max_modes=1,
    )
    f = p._load(0)
    object.__setattr__(f, "normalization_h", f.normalization_h + 1)
    with pytest.raises(ValueError, match="cached H"):
        p._load(0)
    del f
    p.clear()
    old = s.__class__.__call__

    class Changed(Source):
        def __call__(self, i, key):
            return replace(old(self, i, key), normalization_h=i + 2.3)

    p.loader = Changed()
    with pytest.raises(ValueError, match="immutable source"):
        p._load(0)
    p.invalidate("new-source")
    p.loader.key = "new-source"
    assert p._load(0).normalization_h == 2.3
    p.identities[0]["m"] += 1
    with pytest.raises(ValueError, match="mutated"):
        p._load(0)


def test_consumer_fields_not_serialized_hash():
    a = dict.fromkeys(FIELDS, "same")
    b = dict(a)
    b["unrelated_serialized_hash"] = "different"
    assert (
        compare_fields(a, b, scientific_qualified=True)["status"]
        == "SOLVER_PACKAGE_QUALIFIED"
    )
    b["material"] = [0.99988511, 4.32e-6]
    a["material"] = [0.999885140474, 4.32477054e-6]
    assert (
        compare_fields(a, b)["fields"][1]["status"] == "PHYSICAL_OR_DISCRETE_DIFFERENCE"
    )
    b.pop("internal_recovery")
    assert compare_fields(a, b)["status"] == "SOLVER_PACKAGE_NOT_QUALIFIED"


def test_v37_stage_dispatch_does_not_open_old_windows():
    from pathlib import Path

    from src.io.port_preparation import load_preparation

    for path in Path("input/task042_neural_coarse_inverse").glob("v37_*.dat"):
        spec = load_preparation(path)
        assert (
            spec.derived["preparation_scope"] == "v37"
            and spec.derived["target_solve"] is False
        )


def test_short_deadline_clears_own_descendants(tmp_path):
    import subprocess
    import sys

    # Native tests may already own MPI helper children. A watchdog must be a
    # dedicated clean parent, so test its actual standalone process boundary.
    code = """import sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
s=supervise([sys.executable,'-c',"import subprocess,time; subprocess.Popen(['sleep','30']); time.sleep(30)"],
 Path(sys.argv[1]),wall_seconds=.7,interval=.1,timebase_guard=True,hard_stop_immediate=True,
 rss_hard_limit_bytes=2**30,rss_warning_bytes=2**29,include_pss=False,stop_on_global_swap=False)
assert s['classification']!='COMPLETED' and s['descendants_cleared']
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "stop")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr


def test_saved_array_inventory_and_hash_negatives(tmp_path):
    import hashlib

    from benchmarks.check_boundary_witness import read_arrays

    path = tmp_path / "witness.npz"
    a = np.array([1 + 2j, 3 - 1j], dtype=np.complex128)
    np.savez(path, a=a)
    receipt = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "members": {
            "a": {
                "shape": [2],
                "dtype": a.dtype.str,
                "sha256": hashlib.sha256(a.tobytes()).hexdigest(),
            }
        },
    }
    np.testing.assert_array_equal(read_arrays(receipt)["a"], a)
    altered = copy.deepcopy(receipt)
    altered["members"] = {}
    with pytest.raises(ValueError, match="inventory"):
        read_arrays(altered)
    altered = copy.deepcopy(receipt)
    altered["members"]["a"]["sha256"] = "bad"
    with pytest.raises(ValueError, match="member identity"):
        read_arrays(altered)
    altered = copy.deepcopy(receipt)
    altered["sha256"] = "bad"
    with pytest.raises(ValueError, match="file hash"):
        read_arrays(altered)


def test_live_storage_guard_preserves_original_shared_health(monkeypatch, tmp_path):
    from src.runners import port_preparation as runner

    monkeypatch.setattr(
        runner.SharedHealth,
        "__call__",
        lambda self: {"stop_reason": None, "original_psi_guard": "retained"},
    )
    monkeypatch.setattr(
        runner, "inventory_paths", lambda *_: {"bytes": 512 * 2**20 + 1}
    )
    guard = runner.PreparationHealth(tmp_path, [], "v37")
    assert guard()["stop_reason"] == "RESOURCE_CONTROLLED_STOP"
    assert guard()["original_psi_guard"] == "retained"
    # V36 ordinary behavior remains solely the existing shared health contract.
    assert runner.PreparationHealth(tmp_path, [], "v36")()["stop_reason"] is None
