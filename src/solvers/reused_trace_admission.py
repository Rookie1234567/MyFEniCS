"""Explicit reuse policy and bounded numeric workspace; no new partition/PC."""
import numpy as np


def reuse_gate(checks, preparation, capacity_bytes=80*2**30):
    from benchmarks.collect_bounded_trace import symbolic_gate
    # The old capacity conclusion is recomputed at its OLD limit, never edited.
    old = symbolic_gate(preparation['analysis'], preparation['coarse_symbolic'])
    mathematics = bool(checks['mathematics_pass'] and checks['original_action']['pass_gate']
                       and checks['owner']['all_trace_writeback_once'])
    if checks['capacity'] != old or preparation['pass_gate'] != (mathematics and old['admitted']):
        raise ValueError('immutable V71 checker/producer disagreement')
    if len(preparation['matrices']) != 38 or preparation['coarse_symbolic']['rows'] != 7068:
        raise ValueError('V72 exactly saved 38 patches and coarse7068')
    if capacity_bytes != 80*2**30:
        raise ValueError('V72 factor subbudget is fixed80GiB')
    new = dict(old, limit_bytes=capacity_bytes, admitted=old['double_symbolic_sum_bytes'] <= capacity_bytes,
               excess_bytes=max(0, old['double_symbolic_sum_bytes']-capacity_bytes))
    return dict(mathematics_pass=mathematics, old_capacity=old, capacity=new,
                pass_gate=mathematics and new['admitted'], numeric_admission=False,
                old_PC_SETUP_pass_gate=preparation['pass_gate'], historical_result_unchanged=True)


def future_workspace(rows, full_rows, native_rows, maximum_patch_rows, maximum_patch_nnz):
    # Resident Z/maps/oracle/boundary are in live RSS. Count FUTURE live work.
    parts = dict(Krylov_V_Z=65*rows*16, additional_retained_and_PC=12*rows*16,
                 recovery_and_original_vectors=8*full_rows*16+4*native_rows*16,
                 largest_patch_CSR_and_PETSc_workspace=2*(maximum_patch_nnz*24+(maximum_patch_rows+1)*8),
                 triangular_rhs_and_output=4*maximum_patch_rows*16,
                 extra_field_workspace=2*2**30)
    return dict(components=parts, enumerated_bytes=sum(parts.values()),
                minimum_bytes=8*2**30, reserved_bytes=max(8*2**30,sum(parts.values())))


def numeric_gate(tree, not_factored_double_bytes, workspace, limit_bytes=96*2**30):
    if limit_bytes != 96*2**30 or workspace['reserved_bytes'] < 8*2**30:
        raise ValueError('V72 numeric policy')
    planned = int(tree['rss_bytes'])+int(not_factored_double_bytes)+int(workspace['reserved_bytes'])
    return dict(tree=tree, remaining_double_symbolic_bytes=int(not_factored_double_bytes),
                future_workspace=workspace, planned_simultaneous_bytes=planned, limit_bytes=limit_bytes,
                admitted=tree['swap_bytes']==0 and planned<=limit_bytes,
                excess_bytes=max(0,planned-limit_bytes))


def continuation_state(arrays, expected, receipt):
    """Only THIS campaign, same A/RHS/scales, finite complete retained vector."""
    if receipt['namespace'] != 'v72' or receipt['operator_identity'] != expected['operator_identity']:
        raise ValueError('V72 continuation operator/namespace')
    for k in ('bhat','left','right'):
        if not np.array_equal(arrays[k], expected[k]):
            raise ValueError('V72 continuation RHS/scales')
    v = arrays['scaled_retained']
    if v.shape != expected['bhat'].shape or v.dtype != np.complex128 or not np.isfinite(v).all():
        raise ValueError('V72 continuation vector')
    if not 0 <= receipt['iterations_consumed'] < 256 or not 0 <= receipt['iteration_seconds_consumed'] < 21600:
        raise ValueError('V72 cumulative continuation budget')
    return v.copy()
