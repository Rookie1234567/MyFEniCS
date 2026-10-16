from pathlib import Path

from benchmarks.subreaper_watchdog import (
    _host_floor_swap_activity,
    _unreadable_sample_outcome,
    memory_envelope,
)
from src.runners.native_capacity import _native_capacity_host_lock
from src.runners.reviewed_workstation_admission import _classify_task40_solver_argv


def test_host_floor_memory_envelope_has_no_legacy_cap_or_reserve(monkeypatch):
    import benchmarks.subreaper_watchdog as watchdog
    import src.io.native_capacity_profile as profiles

    monkeypatch.setenv('PHYSICAL_NATIVE_CAPACITY', 'task40-test-profile')
    monkeypatch.setattr(watchdog, 'wsl_memory_snapshot', lambda: {
        'mem_total_bytes': 2_000_000_000_000,
        'mem_available_bytes': 1_500_000_000_000,
    })
    monkeypatch.setattr(watchdog, 'current_cgroup_path', lambda: None)
    monkeypatch.setattr(profiles, 'native_profile_facts', lambda _identity: {
        'resources': {
            'resource_stop_policy': 'host_available_floor_v1',
            'minimum_available_bytes': 64 * 1024**3,
        }
    })

    result = memory_envelope()

    assert result['effective_total_bytes'] == 2_000_000_000_000
    assert result['effective_available_bytes'] == 1_500_000_000_000
    assert result['minimum_available_bytes'] == 64 * 1024**3
    assert result['launch_cap_bytes'] is None
    assert result['planning_cap_bytes'] is None
    assert result['reserve_bytes'] is None


def test_legacy_memory_envelope_keeps_existing_profile_policy(monkeypatch):
    import benchmarks.subreaper_watchdog as watchdog
    import src.io.native_capacity_profile as profiles

    monkeypatch.setenv('PHYSICAL_NATIVE_CAPACITY', 'legacy-test-profile')
    monkeypatch.setattr(watchdog, 'wsl_memory_snapshot', lambda: {
        'mem_total_bytes': 1_000_000_000_000,
        'mem_available_bytes': 800_000_000_000,
    })
    monkeypatch.setattr(watchdog, 'current_cgroup_path', lambda: None)
    monkeypatch.setattr(profiles, 'native_profile_facts', lambda _identity: {
        'resources': {
            'resource_stop_policy': 'legacy',
            'reserve_min_bytes': 10_000_000_000,
            'absolute_cap_bytes': 100_000_000_000,
            'planning_cap_bytes': 90_000_000_000,
        }
    })

    result = memory_envelope()

    assert result['reserve_bytes'] == 150_000_000_000
    assert result['launch_cap_bytes'] == 100_000_000_000
    assert result['planning_cap_bytes'] == 90_000_000_000
    assert 'minimum_available_bytes' not in result


def test_host_floor_monitoring_uses_bounded_v3_retry():
    assert _unreadable_sample_outcome('host_available_floor_v1', 1, 0.1) is None
    assert _unreadable_sample_outcome('host_available_floor_v1', 3, 4.9) is None
    assert _unreadable_sample_outcome('host_available_floor_v1', 4, 4.9) == 'MONITORING_LOST'
    assert _unreadable_sample_outcome('host_available_floor_v1', 2, 5.0) == 'MONITORING_LOST'
    assert _unreadable_sample_outcome('legacy', 1, 0.1) == 'MONITORING_FAILED'


def test_host_floor_terminal_swap_is_observation_only_even_for_task_swap():
    baseline = {'pswpin_pages': 5, 'pswpout_pages': 8}
    task_only = _host_floor_swap_activity(
        4096, baseline, {'pswpin_pages': 5, 'pswpout_pages': 8}
    )
    both = _host_floor_swap_activity(
        4096, baseline, {'pswpin_pages': 6, 'pswpout_pages': 8}
    )
    global_only = _host_floor_swap_activity(
        0, baseline, {'pswpin_pages': 6, 'pswpout_pages': 8}
    )
    unknown = _host_floor_swap_activity(
        4096, {'pswpin_pages': None, 'pswpout_pages': None},
        {'pswpin_pages': 6, 'pswpout_pages': 8},
    )

    assert task_only == 'HOST_FLOOR_OBSERVE_ONLY_task_swap_observed_global_unchanged'
    assert both == 'HOST_FLOOR_OBSERVE_ONLY_task_and_global_swap_observed'
    assert global_only == 'HOST_FLOOR_OBSERVE_ONLY_global_swap_observed_task_zero'
    assert unknown == 'HOST_FLOOR_OBSERVE_ONLY_swap_attribution_unknown'
    assert all('zero_supported' not in value for value in (task_only, both, global_only, unknown))


def test_task40_solver_scan_classifies_real_argv_not_scanner_source_text():
    python = '/shared/venv/bin/python'
    assert _classify_task40_solver_argv([
        python, '-c', "print('run_case.py task038_input_worker')",
    ]) is None
    assert _classify_task40_solver_argv([
        python, '/work/scripts/run_case.py', 'case.dat',
    ]) == {
        'kind': 'task_solver', 'role': 'standard_run_case',
        'entrypoint': '/work/scripts/run_case.py',
    }
    assert _classify_task40_solver_argv([
        python, '-m', 'src.runners.task038_input_worker', 'case.dat',
    ])['role'] == 'task038_input_worker'
    assert _classify_task40_solver_argv([
        python, '-m', 'src.runners.task038_future_worker',
    ]) == {
        'kind': 'unknown_task_solver_role',
        'entrypoint': 'src.runners.task038_future_worker',
    }


def test_task40_uses_common_git_parent_lock_and_legacy_path_is_unchanged():
    root = Path(__file__).resolve().parents[2]
    task40_lock, common_git = _native_capacity_host_lock(
        root, 'task40para_phi90_13p5_D13_B_p6_direct_v1'
    )
    assert common_git == Path(
        '/home/fenics/Projects/Maxwell3D-Lab/task-repository.git'
    )
    assert task40_lock == common_git.parent/'native-capacity-heavy.lock'

    old_root = Path('/host/Maxwell3D-Lab/task39extra')
    legacy_lock, legacy_repo = _native_capacity_host_lock(old_root, 'balanced_h6_p4_native_5nm')
    assert legacy_lock == Path('/host/Maxwell3D-Lab/native-capacity-heavy.lock')
    assert legacy_repo == Path('/host/Maxwell3D-Lab/task-repository.git')
