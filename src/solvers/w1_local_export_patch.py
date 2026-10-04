"""Explicit, exports-only patch over the frozen c354afa local module.

The immutable snapshot is never edited. A separately hashed per-run module
exports intermediates already computed by the same factor/stream loops.
No new solve, quadrature, zero threshold or numerical algorithm is added.
"""

import ast
import hashlib
import os
from pathlib import Path


def export_source(source):
    replacements = [
        (
            '    S_V = Vtt - Vti @ lu_solve(local["factor"], Vit)',
            '    solve_Vit = lu_solve(local["factor"], Vit)\n    S_V = Vtt - Vti @ solve_Vit',
        ),
        (
            "    local_integral_calls = 0",
            "    saved_Bi = np.empty((len(active_indices), ni), dtype=np.complex128)\n"
            "    saved_Bt = np.empty((len(active_indices), nt), dtype=np.complex128)\n"
            "    saved_Di = np.empty_like(saved_Bi)\n    saved_Dt = np.empty_like(saved_Bt)\n"
            "    positions = {int(index): pos for pos, index in enumerate(active_indices)}\n"
            "    local_integral_calls = 0",
        ),
        (
            "            Bi_alpha += bi * alpha[index]",
            "            saved_Bi[positions[int(index)]] = bi\n"
            "            saved_Bt[positions[int(index)]] = bt\n            Bi_alpha += bi * alpha[index]",
        ),
        (
            "            qhat_alpha[index] += di @ solve_b_alpha",
            "            saved_Di[positions[int(index)]] = di\n"
            "            saved_Dt[positions[int(index)]] = dt\n            qhat_alpha[index] += di @ solve_b_alpha",
        ),
        (
            '            "qhat_alpha": qhat_alpha,',
            '            "active_mode_indices": active_indices,\n'
            '            "saved_Bi": saved_Bi,\n            "saved_Bt": saved_Bt,\n'
            '            "saved_Di": saved_Di,\n            "saved_Dt": saved_Dt,\n'
            '            "solve_internal_B": solve_b_alpha,\n'
            '            "solve_internal_rhs": solve_fi,\n'
            '            "solve_internal_trace": solve_vit_trace,\n'
            '            "solve_Vit": solve_Vit,\n            "reduced_trace_matrix": S_V,\n'
            '            "reduced_trace_B_alpha": Bhat_alpha,\n'
            '            "reduced_trace_rhs": ft - Vti @ solve_fi,\n'
            '            "original_trace_residual": original_trace_lhs,\n'
            '            "reduced_trace_residual": reduced_trace_lhs,\n'
            '            "qhat_alpha": qhat_alpha,',
        ),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError("W1_EXPORT_PATCH_BASE_CONTEXT_CHANGED")
        source = source.replace(before, after)
    ast.parse(source)
    return source


def materialize_export_module(base_path, output):
    base = Path(base_path).read_bytes()
    patched = export_source(base.decode()).encode()
    output = Path(output)
    temporary = output.with_suffix(".tmp")
    with temporary.open("wb") as out:
        out.write(patched)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, output)
    return {
        "baseline_sha256": hashlib.sha256(base).hexdigest(),
        "patched_sha256": hashlib.sha256(patched).hexdigest(),
        "path": str(output),
        "patch_scope": "export only; all original factor/solve calls retained once",
    }
