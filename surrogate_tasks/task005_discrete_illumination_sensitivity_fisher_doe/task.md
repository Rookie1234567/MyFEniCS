# Task005 Task Book：离散照明灵敏度、Fisher DOE 与局部恢复验证

## 0. Summary

Task004 已正式关闭为 `closed_controlled_negative`。本任务不得恢复连续角度代理，而应直接回答：

> 在 13.5 nm、S 入射、nominal 几何 \(h_0=120\,\mathrm{nm},w_0=17\,\mathrm{nm}\) 附近，哪些有限离散照明及其组合最有利于区分高度和宽度？

核心路线：

```text
train112 nominal response reuse
+ Full3D p5/Ny4 central finite differences
+ derivative step audit
+ non-redundant measurable response contracts
+ scaled Jacobian / Fisher information
+ exhaustive 1–4 angle combination ranking
+ off-centre nonlinear recovery validation
```

本任务结束时最多只能形成一个离散照明 DOE lock。不得开始正式结构代理或参数反演。

---

## 1. Mandatory reading and repository gate

开始前完整阅读：

```text
root AGENTS.md
surrogate_tasks/AGENTS.md
surrogate_tasks/task004_nominal_geometry_angle_surrogate/TASK004_FINAL_STATUS.json
surrogate_tasks/task004_nominal_geometry_angle_surrogate/TASK004_CONTROLLED_NEGATIVE_CLOSEOUT.md
surrogate_tasks/task004_nominal_geometry_angle_surrogate/review_report_v9.md
本README
本task.md
```

必须确认：

```text
branch   = codex/only-one-13p5nm-surrogate-inversion
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
working tree clean before formal execution
```

禁止 merge/rebase/cherry-pick master、Task037 或其他分支。

---

## 2. Immutable forward and nominal-data identity

### 2.1 Forward solver

所有新 FEM 必须使用只读 forward worktree，精确绑定：

```text
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
model_id           = S_PROD_FULL3D_STATIC_P5_H10_NY4
solver_route_id    = full3d_static_uniform_n1curl_p5_h10_ny4
finite element     = uniform N1curl p5
mesh               = (Nx,Ny,Nz)=(6,4,14)
static condensation= assembly-time
MUMPS               = ICNTL(14)=40
MPI                 = 2
threads/rank        = 1
incident            = S
wavelength          = 13.5 nm
observable          = task002.fixed-n0-orders.v3
output              = compact_surrogate_record
```

不得用当前代理开发 HEAD 作为 forward baseline。

### 2.2 Nominal authority

nominal response 只来自：

```text
dataset_id = task004_angle_nominal_p5_ny4_train112_v1
training_tuple_sha256 = 00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68
```

固定：

```text
h0 = 120.0 nm
w0 = 17.0 nm
```

中心几何不得重算。必须从 train112 读取 raw fixed-order mother response、R/T/A、mask、source/config hashes。

---

## 3. Frozen discrete illumination design

建立不可变：

```text
outcomes/DISCRETE_ANGLE_DESIGN.json
```

候选顺序固定为：

| ID | grazing | azimuth |
|---|---:|---:|
| A00 | 0.5 | 0 |
| A01 | 0.5 | 45 |
| A02 | 0.5 | 90 |
| A03 | 1.0 | 15 |
| A04 | 1.0 | 60 |
| A05 | 2.0 | 0 |
| A06 | 2.0 | 45 |
| A07 | 2.0 | 90 |
| A08 | 4.0 | 15 |
| A09 | 4.0 | 60 |
| A10 | 4.0 | 90 |
| A11 | 6.0 | 30 |
| A12 | 6.0 | 75 |
| A13 | 8.0 | 45 |
| A14 | 10.0 | 0 |
| A15 | 10.0 | 90 |

每个 tuple 必须在 train112 中恰好出现一次。checker 必须从数组重建并验证：

```text
exact count = 16
no duplicates
all nominal tuples found exactly once
all fixed h/w/wavelength/polarization identities match
Task001 baseline pair A14+A15 present
point tuple hash frozen
```

若任何 Gate 失败，M1 forbidden。

---

## 4. Parameter perturbation schema

### 4.1 Initial steps

```text
coarse:
    delta_h = 2.5 nm
    delta_w = 0.5 nm

half:
    delta_h = 1.25 nm
    delta_w = 0.25 nm
```

所有扰动保持在原参数域：

```text
h in [115,125] nm
w in [16,18] nm
```

### 4.2 States

对任一角度 \(a\)：

```text
H-: (h0-delta_h, w0)
H+: (h0+delta_h, w0)
W-: (h0, w0-delta_w)
W+: (h0, w0+delta_w)
```

中央差分：

\[
D_h(a;\delta_h)=\frac{\mathbf y(H^+)-\mathbf y(H^-)}{2\delta_h},
\qquad
D_w(a;\delta_w)=\frac{\mathbf y(W^+)-\mathbf y(W^-)}{2\delta_w}.
\]

每个 record 必须保留 raw mother response，不得只保存导数。

---

## 5. Measurement contracts

Fisher 必须按互不重复的观测合同分别计算。

### M0: aggregate_RT

```text
response = [R_total, T_total]
A_balance = derived audit only
```

不得同时将 A 放入 Fisher，因为 \(A=1-R-T\)。

### M1: order_total_robust

```text
response = active fixed-order total power (outgoing S + outgoing P)
nominal/perturbed maximum power >= 1e-3
aggregate R/T/A excluded
```

### M2: order_total_extended

```text
response = active fixed-order total power
nominal/perturbed maximum power >= 1e-5
aggregate R/T/A excluded
absolute noise floor mandatory
```

### M3: polarization_resolved_diagnostic

```text
response = active outgoing S and P powers separately
power threshold = 1e-3
aggregate and order-total excluded
status = diagnostic unless measurement analyzer is later confirmed
```

### Channel rules

- `power_carrying=false` means structural null, not zero measurement；
- channel must have identical analytic propagation identity across nominal and geometry perturbations；
- if a channel is nonfinite, missing or fails raw/fixed ledger, the angle record fails；
- complex amplitudes, phases, Stokes parameters and ratios are excluded from formal M0–M2；
- secondary weak channels remain in audit but do not enter robust primary Fisher.

---

## 6. Provisional noise contracts

For a measured power \(y\in[0,1]\)：

### N1 baseline

\[
\sigma(y)=\sqrt{(0.01y)^2+(10^{-4})^2}.
\]

### N2 conservative

\[
\sigma(y)=\sqrt{(0.02y)^2+(5\times10^{-4})^2}.
\]

Assume diagonal covariance for this exploratory DOE only. Must state:

```text
provisional noise scenario
not an experimentally calibrated covariance
CRLB is a local design metric, not achieved metrology uncertainty
```

Optional ideal-noise diagnostics may be reported but cannot determine final ranking.

---

## 7. M0 — design and code preflight

### Required outputs

```text
outcomes/DISCRETE_ANGLE_DESIGN.json
outcomes/PERTURBATION_SCHEMA.json
outcomes/NOMINAL_REUSE_REPORT.json
benchmarks/cases/131_task005_design_and_step_audit/
```

### Required code

Prefer isolated modules:

```text
src/surrogate/doe/design.py
src/surrogate/doe/sensitivity.py
src/surrogate/doe/fisher.py
src/surrogate/doe/recovery.py
```

Do not refactor core Maxwell code.

### M0 Gate

```text
16/16 nominal tuples exact
single source SHA and schema
Task004 files read-only
no FEM launched
checker pass
```

---

## 8. M1 — finite-difference step audit

### 8.1 Audit angles

```text
A00 = (0.5,0)
A07 = (2,90)
A09 = (4,60)
A14 = (10,0)
A15 = (10,90)
```

For each angle run both coarse and half states：

```text
coarse H-/H+/W-/W+
half   H-/H+/W-/W+
```

At most 40 audit FEM records.

### 8.2 Direct-solve Gate per record

At minimum preserve Task004 production Gates：

```text
status = measured_pass
true residual <= 1e-9
energy closure <= 1e-7
actual topology = planned topology
fixed/raw power ledger pass
n!=0 leakage pass
zero unexplained swap
cleanup complete
single source/config identity
```

The first unexplained failure stops M1.

### 8.3 Step comparison

For each parameter and each measurement contract, form noise-whitened derivative vectors：

\[
\widetilde D=\Sigma^{-1/2}D.
\]

Compare coarse vs half：

```text
cosine(whitened coarse, whitened half) >= 0.98
relative L2 difference <= 0.20
sign agreement among top-SNR channels >= 0.80
```

Top-SNR channels are ranked by：

\[
\frac{|D_j|s_p}{\sigma_j},
\]

where \(s_h=5\,\mathrm{nm}\), \(s_w=1\,\mathrm{nm}\).

### 8.4 Production-step decision

`delta_h` and `delta_w` may be selected independently.

Decision rules：

1. At least 4/5 audit angles pass for M0 and M1 under N1；
2. A14 and A15 must not both fail for the same parameter；
3. Prefer half step when both pass and half-step numerical signal remains above the FEM/post-processing noise floor；
4. Prefer coarse step only when half step exhibits worse reproducibility or cancellation；
5. Preserve Richardson diagnostic at audit angles：
   \[
   D_R=(4D_{half}-D_{coarse})/3,
   \]
   but do not mix Richardson and central differences in the production dataset.

Output：

```text
outcomes/FINITE_DIFFERENCE_STEP_AUDIT.json
outcomes/FINITE_DIFFERENCE_STEP_AUDIT.md
outcomes/PRODUCTION_STEP_LOCK.json
```

If M1 Gate fails, stop; M2 forbidden.

---

## 9. M2 — full 16-angle sensitivity dataset

### 9.1 Runs

For every A00–A15, run four states using frozen production steps. Reuse matching M1 records exactly; do not rerun them.

### 9.2 Dataset

Create immutable：

```text
dataset_id = task005_discrete_angle_hw_sensitivity_p5_ny4_v1
```

At minimum store：

```text
angles.npy                      (16,2)
nominal_inputs.npy              (16,4)
nominal_aggregates.npy
nominal_order_powers.npy
perturbed_inputs.npy            (16,4 states,4 inputs)
perturbed_aggregates.npy
affected order powers / masks
Dh arrays by contract
Dw arrays by contract
channel identities and tiers
noise sigma arrays N1/N2
formal record IDs and hashes
step audit identity
```

Do not mix raw amplitude phase into formal Fisher arrays.

### 9.3 Derivative quality

For each angle report：

```text
finite / nonfinite
norm(Dh), norm(Dw)
noise-whitened norm
cosine(Dh,Dw)
rank of local J
dominant channels
channel SNR
energy derivative consistency: dR+ dT + dA ≈ 0
```

An angle may be retained as a negative/weak candidate, but any angle with invalid FEM or derivative identity makes the dataset incomplete and stops the task.

### 9.4 Independent checker

Create Case132 or later checker that reconstructs central differences from raw perturbation arrays and verifies exact tuple/source/config identity.

---

## 10. M3 — Fisher DOE

### 10.1 Parameter scaling

\[
\theta_h=(h-h_0)/5,
\qquad
\theta_w=(w-w_0)/1.
\]

If \(J_{hw}\) uses physical nm derivatives：

\[
J_\theta=J_{hw}\begin{bmatrix}5&0\\0&1\end{bmatrix}.
\]

### 10.2 Per-angle Fisher

For angle \(a\), contract \(M\), noise \(N\)：

\[
F_{a,M,N}=J_{a,M}^{T}\Sigma_{a,M,N}^{-1}J_{a,M}.
\]

For a set \(S\)：

\[
F_{S,M,N}=\sum_{a\in S}F_{a,M,N}.
\]

### 10.3 Metrics

Report：

```text
rank
singular/eigenvalues
minimum eigenvalue
condition number
logdet with explicit regularization policy
trace(inv(F)) when full rank
scaled covariance / CRLB
physical sigma_h and sigma_w
parameter correlation rho_hw
```

Never invert a rank-deficient matrix silently.

### 10.4 Exhaustive combinations

Compute：

```text
16 singles
120 pairs
560 triples
1820 quadruples
```

Rank separately for each M0/M1/M2 and N1/N2.

### 10.5 Robust ranking

A recommended set must：

1. be full rank for both N1 and N2；
2. be full rank for M0 and M1；
3. maximize worst-case minimum eigenvalue；
4. then maximize worst-case logdet；
5. then minimize worst-case condition number；
6. prefer fewer illuminations when information scores are within 5%；
7. report whether ranking changes under M2 extended weak channels.

M3 outputs：

```text
outcomes/FISHER_SINGLE_ANGLE.json
outcomes/FISHER_COMBINATION_RANKING.json
outcomes/FISHER_COMBINATION_RANKING.md
outcomes/TASK001_BASELINE_PAIR_COMPARISON.json
```

Must explicitly compare A14+A15 with all new pairs/triples.

---

## 11. M4 — off-centre nonlinear recovery validation

### 11.1 Final set

Select one recommended three-angle set using only M3 frozen criteria. Freeze its tuple hash before nonlinear FEM.

### 11.2 Test geometries

```text
G1 = (h=118.75, w=16.75) nm
G2 = (h=121.25, w=17.25) nm
G3 = (h=118.75, w=17.25) nm
```

Run the three selected angles at G1–G3：maximum 9 FEM solves.

### 11.3 Recovery

For each test geometry：

\[
\Delta\widehat p=
(J^T\Sigma^{-1}J)^{-1}J^T\Sigma^{-1}
(\mathbf y_{test}-\mathbf y_0).
\]

Report for M0/M1 and N1/N2 weighting：

```text
truth delta_h/delta_w
recovered delta_h/delta_w
height and width error
response reconstruction residual
linearization residual vs measurement noise
```

Primary noiseless readiness Gate：

```text
abs(height error) <= 0.5 nm
abs(width error)  <= 0.1 nm
for all G1–G3 under M1/N1
```

A derived Monte Carlo noise study may be run from N1/N2 without new FEM, but it is diagnostic and cannot replace the noiseless Gate.

If M4 fails：

- preserve Fisher results；
- do not create DOE lock；
- recommend a fixed-angle nonlinear structural surrogate as the next task.

---

## 12. M5 — final lock and stop

Only if M0–M4 pass, create：

```text
outcomes/DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json
```

Lock must include：

```text
forward solver SHA
dataset IDs and file hashes
16-angle design hash
production delta_h/delta_w
measurement/noise contracts
selected pair/triple and ranking criteria
Task001 baseline comparison
Fisher matrices and metrics
nonlinear validation records
order-resolved qualification scope
explicit statement: no formal inversion performed
```

Then write：

```text
outcomes/test_summary.md
response_v1.md
```

Push current branch and stop for review.

---

## 13. FEM budget and resource discipline

Hard budget：

```text
M1 audit             <= 40
M2 production total <= 64 production-step states, with M1 reuse
M4 nonlinear         <= 9
unique new FEM total <= 96
```

Exact existing artifacts may reduce the count only when tuple, source SHA, config hash, schema and formal record all match.

Execution：

```text
max_parallel_forward_solves = 1
OMP_NUM_THREADS = 1
OPENBLAS_NUM_THREADS = 1
MKL_NUM_THREADS = 1
NUMEXPR_NUM_THREADS = 1
```

Do not run formal FEM on `/mnt/c` or `/mnt/d`. Do not use Docker. Watchdog may terminate only its own process group.

---

## 14. Prohibitions

Task005 may not：

- reopen Task004；
- run Task003/Task004 frozen validation；
- alter forward SHA or MUMPS profile；
- use P incident；
- add wavelength/material/sidewall/roughness parameters；
- train an arbitrary-angle model；
- include duplicate observables in one Fisher matrix；
- claim experimental uncertainty from provisional N1/N2；
- begin Bayesian inversion, optimization against measured data or final structural surrogate；
- exceed the 96-FEM hard budget；
- continue after an unexplained numerical failure.

---

## 15. Completion status

A successful Task005 means：

```text
finite-difference steps qualified
16-angle sensitivity dataset complete
Fisher ranking complete
Task001 baseline pair compared
one three-angle set passes off-centre local recovery
DOE lock created
```

It does not mean：

```text
height/width inversion completed
surrogate model completed
experimental angle design finalized
five/six-parameter extension solved
```

Those require a new reviewed task.
