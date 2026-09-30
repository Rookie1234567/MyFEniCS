"""Output row pairing, complex bias and frozen feature extraction."""

import numpy as np

from src.solvers.feinn_readout import (
    readout,
    write_readout,
    frozen_hashes,
    feature_columns,
)
from src.solvers.feinn_torch import CoordinateField, CompleteMomentMap


def test_complex_layout_and_independent_complete_mapping():
    model = CoordinateField([[-1, 1]] * 3)
    hidden = frozen_hashes(model)
    rng = np.random.default_rng(421501)
    a = rng.standard_normal(195) + 1j * rng.standard_normal(195)
    write_readout(model, a)
    assert np.array_equal(readout(model), a)
    assert frozen_hashes(model) == hidden
    points = rng.standard_normal((7, 3))
    p = dict(
        reference_points=points,
        interpolation=rng.standard_normal((5, 21)),
        transforms=np.array([np.eye(5), np.diag([-1, 1, -1, 1, 1])]),
        jacobians=np.array([[[1, 0.1, 0], [0, 2, 0.2], [0.3, 0, 1]], np.eye(3)]),
        origins=np.zeros((2, 3)),
        orientation_ids=np.array([0, 1]),
        owner_rows=np.array([[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]),
        active_rows=10,
    )
    mapping = CompleteMomentMap(p)
    Phi, construction = feature_columns(model, mapping, lambda *_: None, float("inf"))
    assert construction["hidden_cell_batches"] == 1
    assert (
        np.linalg.norm(Phi @ a - mapping.forward(model, 8)) / np.linalg.norm(Phi @ a)
        < 1e-13
    )
    assert np.linalg.norm(mapping.forward(model, 1) - mapping.forward(model, 8)) < 1e-12
    assert frozen_hashes(model) == hidden


def test_supervised_readout_input_labels_and_FE_import_isolation():
    import ast
    from src.io.feinn_pilot import ROOT, load_pilot

    for path in (ROOT / "input/task042extra_feinn_5nm").glob("v5_*.dat"):
        spec = load_pilot(path)
        assert spec.derived["reference_used_for_training"]
        assert not spec.derived["official_candidate_results"]
    # No top-level Torch/readout module import may contaminate FE paths.
    for filename in ("feinn_reference.py",):
        tree = ast.parse((ROOT / "src/solvers" / filename).read_text())
        imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        assert all(
            "feinn_readout" not in ast.unparse(n) and "torch" not in ast.unparse(n)
            for n in imports
        )
