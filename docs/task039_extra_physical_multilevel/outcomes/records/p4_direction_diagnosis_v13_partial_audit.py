import sys
import time
import json
import hashlib
import gc
from pathlib import Path
import numpy as np
from scipy.linalg import qr

started = time.perf_counter()
root = Path(sys.argv[1])
checks = []


def packet(name):
    obj = json.loads((root / (name + ".json")).read_text())
    if "arrays" not in obj:
        return obj
    p = Path(obj["arrays"]["path"])
    assert hashlib.sha256(p.read_bytes()).hexdigest() == obj["arrays"]["sha256"]
    with np.load(p, allow_pickle=False) as z:

        def rec(v):
            if isinstance(v, dict) and "array_key" in v:
                return z[v["array_key"]]
            if isinstance(v, dict):
                return {k: rec(x) for k, x in v.items()}
            if isinstance(v, list):
                return [rec(x) for x in v]
            return v

        return rec(obj)


def ck(name, x, tol=1e-10):
    checks.append(
        dict(
            name=name,
            measured=float(x),
            limit=tol,
            passed=bool(np.isfinite(x) and x <= tol),
        )
    )


def rel(a, b):
    return np.linalg.norm(a - b) / max(
        np.linalg.norm(a), np.linalg.norm(b), np.finfo(float).tiny
    )


def ls(A, b):
    s = np.linalg.norm(A, axis=0)
    s[s == 0] = 1
    q, r = qr(
        np.array(A / s, order="F"),
        mode="economic",
        overwrite_a=True,
        check_finite=False,
    )
    c, _, rank, sing = np.linalg.lstsq(r, q.conj().T @ b, rcond=1e-12)
    return c / s, int(rank), sing.tolist()


p1 = packet("A2R160_BAL_H_p4_01_p1_direction_diagnosis")
p3 = packet("A2R160_BAL_H_p4_01_p3_response_columns")
m = packet("p0_metric_equivalence")
i = p3["p4_indices"]
g = p1["rhs_values"][i]
Z = p1["pc_outputs_values"][i]
Q = p1["A_pc_outputs_values"][i]
actual = p1["actual_solution_values"][i]
D = m["fixed_diagonal_values"]
sd = np.sqrt(D)
y, rank, _ = ls(Z, actual)
ck("actual_in_range_Z", rel(Z @ y, actual))
yr, _, _ = ls(Q, g)
ck("original_Z_min_projection", rel(Q @ yr, Q @ p1["residual_y"]))
ck(
    "actual_min_residual",
    abs(np.linalg.norm(g - Q @ yr) - np.linalg.norm(g - p1["actual_applied_values"][i]))
    / np.linalg.norm(g),
)
yd, _, _ = ls(Q / sd[:, None], g / sd)
ck("fixed_D_projection", rel(Q @ yd, Q @ p1["dual_y"]))
f = p1["facts"]["field_LS"]
R = f["r_factor"]
b = f["rhs_small"]
scale = np.array(f["column_scale"])
yf, _, _ = ls(R, b)
ck("oracle_Z_small_projection", rel(R @ yf, R @ (p1["field_y"] * scale)))
ck("oracle_basis_orthogonality", f["weighted_basis_orthogonality"])
for name, c in p1["facts"]["candidates"].items():
    ck(
        name + ":eta_raw_norm",
        abs(c["eta"] - np.sqrt(c["mass_squared"] / c["reference_mass_squared"])),
    )
    ck(
        name + ":curl_raw_norm",
        abs(c["eta_curl"] - np.sqrt(c["curl_squared"] / c["reference_curl_squared"])),
    )
# Use the saved A-images only. L field vectors a and t were not checkpointed before controlled stop.
AL = np.column_stack((Q, p3["A_a_values"], p3["p_images_values"], -p3["A_t_values"]))
del p3["p_columns_values"], p3["p_images_values"]
gc.collect()
yL, rankL, singL = ls(AL, g)
rhoL = float(np.linalg.norm(g - AL @ yL) / np.linalg.norm(g))
chosen = []
current = np.column_stack((AL[:, 4], AL[:, -1]))
for step in range(8):
    s = np.linalg.norm(current, axis=0)
    s[s == 0] = 1
    q, r = qr(np.array(current / s, order="F"), mode="economic", overwrite_a=True)
    u, sing, _ = np.linalg.svd(r, full_matrices=False)
    basis = q @ u[:, sing > sing[0] * 1e-12]
    residual = g - basis @ (basis.conj().T @ g)
    best = None
    score_max = -1
    for j in range(42):
        if j in chosen:
            continue
        col = AL[:, 5 + j]
        v = col.copy()
        for _ in range(2):
            v -= basis @ (basis.conj().T @ v)
        nv = np.linalg.norm(v)
        if nv <= 1e-12 * np.linalg.norm(col):
            continue
        score = abs(np.vdot(v, residual)) / (nv * np.linalg.norm(residual))
        if score > score_max:
            score_max = score
            best = j
    if best is None:
        break
    chosen.append(best)
    current = np.column_stack((current, AL[:, 5 + best]))
ck("selector_matches_saved_indices", 0 if chosen == p3["selected_indices"] else 1, 0)
ys, ranks, sings = ls(current, g)
rhoS = float(np.linalg.norm(g - current @ ys) / np.linalg.norm(g))
ck(
    "L_contains_Z_residual_nonworsening",
    max(0, rhoL - p1["facts"]["candidates"]["Z_residual"]["rho"]),
    1e-9,
)
result = dict(
    status="PARTIAL_SAVED_EVIDENCE_AUDITED",
    source_sha="e46fec48dc073a745e9b7e6c9186a147aefbc0a0",
    passed=all(x["passed"] for x in checks),
    checks=checks,
    available_input="A2R160_BAL_H_p4_01",
    p1_candidates=p1["facts"]["candidates"],
    P3_residual_only=dict(
        full_L_rho=rhoL,
        full_L_rank=rankL,
        full_L_singular=singL,
        selected_rho=rhoS,
        selected_rank=ranks,
        selected_indices=chosen,
        selected_singular=sings,
    ),
    counts=dict(PDE=0, PC=0, A4=0, M0=0, curl=0),
    missing=[
        "input02 and input09 direction observations",
        "P2 local images and a/t fields",
        "L and selected field/curl metrics",
        "full memory accounting at runtime",
    ],
    elapsed_seconds=time.perf_counter() - started,
)
Path("/tmp/task39extra-v13-root-partial-audit.json").write_text(
    json.dumps(result, indent=2)
)
print(
    json.dumps(
        dict(
            passed=result["passed"],
            checks=len(checks),
            failed=[x for x in checks if not x["passed"]],
            p3=result["P3_residual_only"],
            seconds=result["elapsed_seconds"],
        ),
        indent=2,
    )
)
