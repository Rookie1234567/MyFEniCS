"""Bounded batching of independent frozen-strategy wave candidates.

The candidates and their individual SVD problems are unchanged. Only their
complete moment and two-pass projection work is batched, at most eight
independent proposals / 64 neurons. Original A keeps its separately qualified
24-column / eight-cell blocks. No neuron or full FE unknown is removed.
"""

import numpy as np

from src.solvers.neural_wave_subspace import optimal_amplitudes


def screen_candidates(action, subspace, moments, patch, candidates, *, local, projector):
    if not candidates:
        return []
    width = len(candidates[0])
    if width not in (1, 2, 4, 8) or any(np.shape(q) != (width, 3) for q in candidates):
        raise ValueError("FROZEN_CANDIDATE_MODULE_LAYOUT_REQUIRED")
    block_count = 8
    if subspace.action.size * 3 * (width * block_count * 3) * 16 > 2 * 2**30:
        raise MemoryError("BOUNDED_SCREENING_TEMPORARY_2GIB_PLANNING_LINE")
    results = []
    for first in range(0, len(candidates), block_count):
        group = candidates[first:first + block_count]
        columns = moments.columns(patch, np.concatenate(group))
        original_A = np.empty_like(columns)
        for first_column in range(0, columns.shape[1], 24):
            selected_columns = slice(first_column, first_column + 24)
            original_A[:, selected_columns] = (
                local.columns(columns[:, selected_columns]) if local is not None
                else np.column_stack([action.apply(c) for c in columns[:, selected_columns].T])
            )
        projected = (
            subspace.project(original_A) if projector is None
            else projector.project(original_A, supported=True)
        )
        for j, q in enumerate(group):
            selected = slice(j * width * 3, (j + 1) * width * 3)
            try:
                p, _, record = optimal_amplitudes(
                    action, subspace, columns[:, selected],
                    applied_columns=original_A[:, selected], projector=projector,
                    projected_columns=projected[:, selected],
                )
                actual_columns = columns[:, selected]
                if record["original_two_pass_rounding_fallback"]:
                    # Near correlation can amplify even the rounding change
                    # of a batched phase/moment contraction. Rebuild this one
                    # candidate with the original per-module operations.
                    actual_columns = moments.columns(patch, q)
                    p, _, record = optimal_amplitudes(action, subspace, actual_columns)
                    record["original_two_pass_rounding_fallback"] = True
                    record["original_complete_candidate_rounding_fallback"] = True
                results.append((
                    record["score"], p.reshape(width, 3), actual_columns @ p,
                    record, None,
                ))
            except ValueError as error:
                if str(error) != "DEGENERATE_NEW_DIRECTION":
                    raise
                results.append(None)
    return results
