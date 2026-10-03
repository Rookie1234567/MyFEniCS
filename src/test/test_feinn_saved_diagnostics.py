import json
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter

import numpy as np
import pytest

from src.solvers.feinn_saved_attribution import DiagnosticActions


def test_read_whitelist_does_not_rehash_unused_history(monkeypatch, tmp_path):
    from src.runners import feinn_workflow as w

    used = tmp_path / "used.npz"
    used.write_bytes(b"original")
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            dict(
                files=dict(
                    native=dict(path=str(used), sha256=w.sha(used)),
                    history=dict(path=str(tmp_path / "absent"), sha256="missing"),
                )
            )
        )
    )
    monkeypatch.setattr(w, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(w, "index_path", lambda _: index)
    item = w.load_index("test", file_keys=("native",))
    assert set(item["files"]) == {"native"}
    used.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="ARTIFACT_IDENTITY_FAILED"):
        w.load_index("test", file_keys=("native",))


def test_action_caps_include_Gsolve_true_residual_matvec():
    p = SimpleNamespace(counts=dict(A=0, AH=0))

    def apply(v, adjoint=False):
        p.counts["AH" if adjoint else "A"] += 1
        return (2 - 1j if adjoint else 2 + 1j) * v

    p.apply = apply
    f = SimpleNamespace(solves=0)

    def solve(v):
        f.solves += 1
        return v / 2

    f.solve = solve
    lim = dict(A=1, AH=1, Gsolve=1, G_matvec=2)
    ops = DiagnosticActions(
        p,
        2 * np.eye(3),
        f,
        lim,
        dict(
            supervision_budget_origin_monotonic=perf_counter(),
            supervised_limit_seconds=1000,
        ),
    )
    v = np.ones(3, complex)
    assert np.allclose(ops.solve(v), v / 2)
    ops.gm(v)
    ops.A(v)
    ops.A(v, adjoint=True)
    assert ops.record() == dict(A=1, AH=1, Gsolve=1, G_matvec=2)
    with pytest.raises(RuntimeError, match="CAP_G_matvec"):
        ops.gm(v)
    with pytest.raises(RuntimeError, match="CAP_A"):
        ops.A(v)


def test_FE_diagnostic_top_level_remains_torch_free():
    import subprocess
    import sys

    code = 'import sys; import src.solvers.feinn_saved_field_diagnostics; assert "torch" not in sys.modules'
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


def test_group_directions_real_and_zero_groups_removed():
    # This source also checks the eight-group cap without importing Torch.
    import ast

    text = Path("src/solvers/feinn_local_reachability.py").read_text()
    tree = ast.parse(text)
    function = next(
        x
        for x in tree.body
        if isinstance(x, ast.FunctionDef) and x.name == "grouped_directions"
    )
    namespace = {"np": np}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), "group_fixture", "exec"),
        namespace,
    )
    groups = [("one", slice(0, 2)), ("two", slice(2, 4))]
    P, rows = namespace["grouped_directions"](
        groups,
        dict(
            PDE=np.array([3.0, 4.0, 0.0, 0.0]),
            reference_G=np.array([0.0, 0.0, 0.0, -2.0]),
        ),
    )
    assert P.shape == (4, 2) and np.isrealobj(P)
    assert np.allclose(np.linalg.norm(P, axis=0), 1)
    assert sum(x["status"] == "ZERO_DIRECTION_REMOVED" for x in rows) == 2
