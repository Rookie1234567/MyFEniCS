"""Explicit heavy-window authorization modes, without host mutation."""

import pytest

from src.io.input_loader import InputError
from src.io.native_capacity_profile import (
    V6_F5_P6_DIRECT_FULL600_PROFILE,
    V6_F5_P6_DIRECT_N0_PROFILE,
)
from src.runners.reviewed_workstation_admission import (
    _parallel_authorized_profile,
    _window_authorization,
)


def test_cross_project_parallel_is_explicit_and_scoped_to_f5_direct_profiles():
    assert _parallel_authorized_profile(V6_F5_P6_DIRECT_FULL600_PROFILE)
    assert _parallel_authorized_profile(V6_F5_P6_DIRECT_N0_PROFILE)
    assert not _parallel_authorized_profile('dual_condensed_balh_native_5nm_v5')

    mode = _window_authorization('parallel_authorized', parallel_allowed=True)
    assert mode == {
        'window_mode': 'user_authorized_cross_project_parallel',
        'user_exclusive_window_confirmation': False,
        'user_parallel_window_authorization': True,
    }


def test_legacy_coordinated_mode_remains_exclusive_and_unmodified():
    mode = _window_authorization('coordinated', parallel_allowed=False)
    assert mode == {
        'window_mode': 'user_coordinated_exclusive',
        'user_exclusive_window_confirmation': True,
        'user_parallel_window_authorization': False,
    }


@pytest.mark.parametrize('value', [None, '', 'parallel_authorized', 'unknown'])
def test_missing_or_unscoped_parallel_authorization_is_rejected(value):
    with pytest.raises(InputError):
        _window_authorization(value, parallel_allowed=False)


def test_unknown_window_mode_is_rejected_even_for_direct_profile():
    assert _parallel_authorized_profile(V6_F5_P6_DIRECT_FULL600_PROFILE)
    with pytest.raises(InputError):
        _window_authorization('anything_else', parallel_allowed=True)
