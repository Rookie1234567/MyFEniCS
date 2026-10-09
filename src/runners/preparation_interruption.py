"""Conservative settlement when an external interruption lost the launcher receipt.

This never reconstructs numerical state or grants permission to replay a solve.
The caller must first record that the entire owned process inventory is absent.
"""
from datetime import datetime
import math


def interrupted_summary(active, samples, observation, *, outer_exit_code):
    if not samples or observation['live_matching_actors']:
        raise ValueError('interrupted process inventory incomplete or still live')
    pids = {m['pid'] for s in samples for m in s['members']}
    encoded = observation['absent_recorded_pids']
    absent = {int(k):v for k,v in encoded.items()}
    if len(absent) != len(encoded) or set(absent) != pids or not all(v is True for v in absent.values()):
        raise ValueError('every recorded descendant must be absent')
    before = active['before_clock']
    if observation['boot_id'] != before['boot_id']:
        raise ValueError('interrupted accounting boot identity')
    upper = max(observation['monotonic']-before['observed_monotonic'],
        (datetime.fromisoformat(observation['utc'])-datetime.fromisoformat(before['observed_utc'])).total_seconds())
    lower = max(s['elapsed_seconds'] for s in samples)
    if not math.isfinite(upper) or upper < lower or any(not math.isfinite(s['elapsed_seconds']) or s['elapsed_seconds'] < 0 for s in samples):
        raise ValueError('interrupted accounting interval')
    return dict(classification='INTERRUPTED_NO_RETURN_UNKNOWN_CAUSE', leader_exit_code=None,
        outer_exit_code=outer_exit_code, elapsed_seconds=upper,
        elapsed_lower_seconds=lower, elapsed_upper_seconds=upper,
        elapsed_scope='last live supervised sample through first recorded complete absence; upper charged',
        source_sha=active['source_sha'], descendants_cleared=True, remaining_child_pids=[],
        sampled_process_tree_rss_peak_bytes=max(s['rss_bytes'] for s in samples),
        sampled_process_tree_swap_peak_bytes=max(s['swap_bytes'] for s in samples),
        unobserved_tail_seconds=upper-lower, samples=len(samples),
        no_returned_numerical_state=True, numeric_or_Arnoldi_state_reconstructed=False,
        last_health_stop_reason=samples[-1].get('opt_in_health_check',{}).get('stop_reason'),
        observed_resource_gate_failure_not_inferred=True, replay_authorized=False)
