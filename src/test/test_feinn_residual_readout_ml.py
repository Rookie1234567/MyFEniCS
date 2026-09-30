"""The saved G coordinate inverse reaches the original real/imag readout."""

import ast
from pathlib import Path
import numpy as np
import torch

from src.solvers.feinn_torch import CoordinateField
from src.solvers.feinn_readout import readout, write_readout, frozen_hashes
from src.solvers.feinn_restricted_residual import original_readout


def test_G_coordinates_into_paired_weights_and_bias_with_frozen_hidden():
    model = CoordinateField([[-1, 1]] * 3)
    hidden = frozen_hashes(model)
    rng = np.random.default_rng(421601)
    pi = rng.permutation(195)
    basis = dict(
        permutation=pi,
        scales=np.linspace(0.2, 5, 195),
        singular_values=np.linspace(10, 1, 195),
        vh=np.eye(195, dtype=complex),
    )
    y = 1j * rng.normal(size=195)
    a = original_readout(y, basis)
    write_readout(model, a)
    assert np.array_equal(readout(model), a)
    assert frozen_hashes(model) == hidden
    points = torch.tensor(rng.normal(size=(5, 3)), dtype=torch.float64)
    with torch.no_grad():
        normalized = (points - model.center) / model.half_width
        h = model.envelopes[:-1](normalized).numpy()
        expected = np.column_stack((h, np.ones(5))) @ a.reshape(3, 65).T
        actual = model(points).numpy()
    assert np.linalg.norm(actual - expected) / np.linalg.norm(expected) < 1e-13
    assert np.linalg.norm(a.reshape(3, 65)[:, 64]) > 0


def test_FE_module_top_level_imports_remain_without_Torch():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/solvers/feinn_reference.py").read_text())
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert "torch" not in ast.unparse(node)
            assert "feinn_residual_readout" not in ast.unparse(node)
