"""Independent persisted-array checker; no Basix, producer or field solve."""

import numpy as np


def check_arrays(path, oracle_path):
    with np.load(path, allow_pickle=False) as z:
        actual = {k: np.array(z[k]) for k in z.files}
    with np.load(oracle_path, allow_pickle=False) as z:
        ref = {k: np.array(z[k]) for k in z.files}

    def measure(a, b):
        numerator = float(np.sqrt(np.sum(abs(a - b) ** 2)))
        norm = float(np.sqrt(np.sum(abs(b) ** 2)))
        return dict(
            numerator=numerator,
            reference_norm=norm,
            denominator=max(norm, 1e-12),
            near_zero=norm < 1e-12,
            relative=numerator / max(norm, 1e-12),
        )

    moment = float(np.max(abs(actual["moment_values"] - ref["moment_oracle110"])))
    rows = {}
    finite = all(np.isfinite(v).all() for v in actual.values())
    for p in (4, 6):
        c, load = (ref[f"p{p}_{k}"] for k in ("directions", "load"))
        B, D, H = (ref[f"p{p}_{k}"] for k in ("B", "D", "H"))
        expected = dict(
            B=B,
            D=D,
            H=H,
            forward=B @ c.T,
            projection=(D @ c.T + load[:, None]) / H[:, None],
            adjoint=B.conj().T @ load,
        )
        metrics = {k: measure(actual[f"p{p}_{k}"], v) for k, v in expected.items()}
        rows[str(p)] = metrics
    passed = (
        finite
        and moment <= 1e-12
        and all(x["relative"] <= 1e-10 for r in rows.values() for x in r.values())
    )
    return dict(
        passed=bool(passed),
        moment_max_absolute=moment,
        finite=bool(finite),
        rows=rows,
        complete_modes=False,
        global_field_or_solver_qualified=False,
    )
