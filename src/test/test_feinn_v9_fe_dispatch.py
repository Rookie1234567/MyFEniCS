"""FE compare-only dispatch must not import the ML/Torch training module."""

import subprocess
import sys


def test_FE_compare_dispatch_selects_FE_only_before_ML_import():
    code = """
import sys, importlib.abc
from unittest.mock import patch
class NoTorch(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'torch' or fullname.startswith('torch.'):
            raise AssertionError('FE_TOP_LEVEL_TORCH_IMPORT')
sys.meta_path.insert(0, NoTorch())
from src.runners.feinn_gn_campaign import dispatch
with patch('src.solvers.feinn_phase_compare.compare', return_value=({'FE_only': True}, {})):
    for stage in ('v9_gn_compare', 'v9_fit_gn_compare'):
        result, _ = dispatch(stage, {}, None, None, {}, lambda _: {})
        assert result['FE_only']
assert 'torch' not in sys.modules
assert 'src.solvers.feinn_gn_training' not in sys.modules
"""
    # Inherits the caller's qualified activation and library environment.
    subprocess.run([sys.executable, "-c", code], check=True)
