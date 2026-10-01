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
from src.runners.feinn_cached_gn_campaign import dispatch as cached_dispatch
with patch('src.solvers.feinn_phase_compare.compare', return_value=({'FE_only': True}, {})), patch('src.runners.feinn_cached_gn_campaign.selected_routes', return_value={}):
    for stage in ('v10_gn_compare', 'v10_fit_compare'):
        result, _ = cached_dispatch(stage, {}, None, None, {}, lambda _: {})
        assert result['FE_only']
assert 'torch' not in sys.modules
assert 'src.solvers.feinn_derivative_reuse' not in sys.modules
"""
    # Inherits the caller's qualified activation and library environment.
    subprocess.run([sys.executable, "-c", code], check=True)


def test_failed_attempt_wall_is_charged_only_to_its_own_route():
    from src.runners.feinn_cached_gn_campaign import route_spent_seconds

    rows = [
        dict(
            path="/results/task42extra_v10_plain_cached_gn_1/run_summary.json",
            seconds=157,
        ),
        dict(
            path="/results/task42extra_v10_plain_cached_gn_2/run_summary.json",
            seconds=31,
        ),
        dict(
            path="/results/task42extra_v10_phase_cached_gn_1/run_summary.json",
            seconds=80,
        ),
        dict(path="/checks/v10_B_test/summary.json", seconds=4),
    ]
    assert route_spent_seconds("v10_plain_cached_gn", rows) == 188
    assert route_spent_seconds("v10_phase_cached_gn", rows) == 80
