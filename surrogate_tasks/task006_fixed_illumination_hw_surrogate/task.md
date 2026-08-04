# Task006 Task Book：固定 A05/A07/A09 照明的二维 h/w 前向代理

## 0. Summary

Task005 已选择并局部验证三组固定照明：

```text
A05 = grazing 2°, azimuth 0°
A07 = grazing 2°, azimuth 90°
A09 = grazing 4°, azimuth 60°
```

Task006 的目标是建立：

\[
(h,w)\longrightarrow \mathbf y_{A05,A07,A09},
\]

其中：

```text
h in [115,125] nm
w in [16,18] nm
wavelength = 13.5 nm
incident polarization = S
```

本任务不再将角度作为连续输入。第一轮只完成 37 个 training geometries 的数据生成和 training-only 代理资格化，随后停止等待审阅；不得运行 12 个 blind geometries，不得开始正式反演。

---

## 1. Mandatory reading and repository gate

开始前完整阅读：

```text
root AGENTS.md
surrogate_tasks/AGENTS.md
surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/review_report_v2.md
surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes/DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json
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

## 2. Task005 metadata closeout must precede Task006

不得修改 Task005 V1/V2 lock 或原始/派生数据包。先建立：

```text
surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/
    TASK005_FINAL_STATUS.json
    TASK005_APPROVED_CLOSEOUT.md
```

并更新 Task005 README/summary。

最终状态必须记录：

```text
M0-M4 implementation SHA = d24395b377259da129a81384f88d8a4ad74602d2
M5R generator commit SHA = 25327ab792a580fb198f07e59564c84149e952a1
M5R source file SHA256   = exact SHA256(src/surrogate/doe/m5r.py)
V2 lock file SHA256      = exact bytes
review authority          = review_report_v2.md
Task005 final status       = approved_closed
Task006 authorization      = M0-M2 only
```

这是 provenance closeout，不运行 FEM。

---

## 3. Immutable forward identity

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

---

## 4. Fixed illumination contract

冻结顺序：

| angle ID | grazing | azimuth |
|---|---:|---:|
| A05 | 2° | 0° |
| A07 | 2° | 90° |
| A09 | 4° | 60° |

建立：

```text
outcomes/FIXED_ILLUMINATION_CONTRACT.json
```

必须绑定 Task005 V2 lock、angle tuple、M1 frozen channel identities、M4 recovery evidence和所有 hashes。

三角度顺序是数据轴身份，不得自动排序或重命名。

---

## 5. Geometry domain and frozen 7x7 mother grid

### 5.1 Nodes

```text
h_nodes_nm = [115,117.5,118.75,120,121.25,122.5,125]
w_nodes_nm = [16,16.5,16.75,17,17.25,17.5,18]
```

母网格共 49 个 geometry tuples。

### 5.2 Initial training geometries: exactly 37

#### A. 全部边界点：24

所有满足以下任一条件的母网格点：

```text
h = 115 or 125
w = 16 or 18
```

角点只计一次。

#### B. 已有三角度完整记录的中心附近点：8

```text
(120,17)
(118.75,17)
(121.25,17)
(120,16.75)
(120,17.25)
(118.75,16.75)
(118.75,17.25)
(121.25,17.25)
```

#### C. coarse-axis points：4

```text
(117.5,17)
(122.5,17)
(120,16.5)
(120,17.5)
```

Task005 中 A07/A09 已有 matching records；A05 缺失，必须只补 A05，不得重复运行 A07/A09。

#### D. 缺失对称象限点：1

```text
(121.25,16.75)
```

以上并集必须恰好 37 个 geometry tuples，无重复。

### 5.3 Frozen blind geometries: exactly 12

母网格中剩余内部点冻结为 blind design：

```text
(117.5,16.5)
(117.5,16.75)
(117.5,17.25)
(117.5,17.5)
(118.75,16.5)
(118.75,17.5)
(121.25,16.5)
(121.25,17.5)
(122.5,16.5)
(122.5,16.75)
(122.5,17.25)
(122.5,17.5)
```

第一轮不得运行这些点的任何 A05/A07/A09 FEM，也不得通过其他 artifact 搜索或近似匹配读取其响应。

### 5.4 Required design artifacts

```text
outcomes/HW_MOTHER_GRID.json
outcomes/HW_TRAIN37_DESIGN.json
outcomes/HW_BLIND12_DESIGN.json
outcomes/HW_REUSE_INVENTORY.json
```

设计 checker 必须验证：

```text
49 = 37 + 12
no overlap
exact tuple hashes
all boundary points in training
blind points all strictly interior
all existing reused records exact-match source/config/schema
no blind response accessed
```

---

## 6. Reuse policy and initial FEM budget

### 6.1 Exact reusable common points

允许从 Task004/Task005 artifacts 复用三角度都完整的 8 个 geometry tuples。

### 6.2 Partial coarse-axis reuse

四个 coarse-axis tuples 只复用 A07/A09；每个点新增 A05 一次。

### 6.3 New initial training solves

```text
24 boundary geometries x 3 angles          = 72
4 coarse-axis geometries x A05 only        = 4
1 missing-quadrant geometry x 3 angles     = 3
-----------------------------------------------
initial new FEM hard count                  = 79
```

不得以近似参数、不同 source SHA、不同 config hash 或不同 observable schema 复用记录。

---

## 7. Forward-data Gate

每个新或复用 record 必须重新检查：

```text
status = measured_pass
source_sha = frozen forward SHA
source_dirty = false
true residual <= 1e-9
energy closure <= 1e-7
planned topology = actual topology
fixed/raw power ledger pass
n!=0 leakage pass
zero unexplained swap
cleanup complete
observable/config hashes exact
```

任一未解释失败立即停止；不得跳过 geometry 后继续形成不完整训练集。

运行纪律：

```text
max_parallel_forward_solves = 1
OMP_NUM_THREADS = 1
OPENBLAS_NUM_THREADS = 1
MKL_NUM_THREADS = 1
NUMEXPR_NUM_THREADS = 1
```

---

## 8. Output contracts

Task006 必须将两个正式合同分开建模、分开评分。

### S0: aggregate composition

每个角度：

```text
R_total
T_total
A_balance = 1-R-T
```

训练 latent：

\[
z_R=\log\frac{R+\epsilon}{A+\epsilon},
\qquad
z_T=\log\frac{T+\epsilon}{A+\epsilon}.
\]

预测后 softmax 恢复，严格保证：

```text
R,T,A >= 0
R+T+A = 1
```

### S1: robust fixed-order total powers

使用 Task005 M1 为 A05/A07/A09 冻结的 channel identities。

对每个角度、每个 side，构造：

```text
selected robust channel powers
other = side total - sum(selected robust channels)
```

采用 sidewise composition/fractions，使：

```text
all selected powers >= 0
sum(selected + other) = predicted R or T
```

禁止：

```text
inactive channel zero-fill
每个geometry重新选择channel
将S0和S1重复计入同一个正式likelihood
```

若 frozen channel 在某个 geometry 中 mask=false、nonfinite 或账本不闭合，任务受控停止并等待审阅。

### S2: M2 weak-channel diagnostic

可以保存与评分，但不得决定第一轮生产模型资格。

---

## 9. Immutable training dataset

建立：

```text
dataset_id = task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1
```

至少保存：

```text
geometries.npy                  (37,2)
angle_contract.npy             (3,2)
inputs_by_angle.npy             (37,3,4)
aggregates.npy                  (37,3,4)
order powers / masks
S0 latent targets
S1 sidewise fractions + residual-other
sample IDs / formal hashes / execution hashes
reuse/new provenance
source SHA / config / observable identities
file hashes and immutable manifest
```

建立独立 Case checker，从 raw mother records 重建 compact arrays、S0/S1 transformations和全部 hashes。

---

## 10. Finite surrogate candidates

只比较：

### B1: orthogonal polynomial baseline

```text
tensor Chebyshev or Legendre
degree 2,3,4
explicit regularization and condition-number report
```

### B2: local RBF baseline

```text
finite frozen neighbor/smoothing choices
cross-fitted residual interval
```

### P1: primary exact GP

```text
Matérn-5/2 ARD exact GP
scaled h,w input
explicit nugget/jitter
finite deterministic optimizer restarts
CPU
```

### P2: optional trend + GP residual

仅当 B1 显示明确低阶趋势时比较一次。

禁止 neural network、random forest、SVR 或无边界 kernel/model zoo。

---

## 11. Geometry-grouped training-only CV

### 11.1 Fold rule

冻结 deterministic 5-fold geometry splits。

一个 held-out geometry 的：

```text
A05
A07
A09
全部S0/S1 targets
```

必须同时作为 test。禁止将三个角度行拆散后随机交叉验证。

### 11.2 Forward metrics

每个 angle/target、每个合同报告：

```text
NRMSE
p95 absolute error
max absolute error
noise-normalized |error|/sigma under N1/N2
boundary/interior breakdown
nearest training distance
predictive interval coverage and half-width
```

### 11.3 Frozen training-only readiness Gates

S0 每个 target：

```text
NRMSE <= 0.01
p95 absolute error <= 0.005
max absolute error <= 0.015
composition exact <= 1e-12
```

S1 每个 primary channel：

```text
NRMSE <= 0.02
p95 noise-normalized absolute error under N1 <= 0.75
max noise-normalized absolute error under N1 <= 2.0
sidewise ledger <= 1e-12
```

Cross-fitted uncertainty：

```text
coverage >= 0.90
all interval widths finite and positive
p95 interval half-width <= 1.0 * corresponding N1 sigma
```

若经验表明某个冻结 Gate 与零附近响应产生不可解释的病态指标，必须报告并停止，不得自行改 Gate。

---

## 12. Held-out synthetic recovery in outer CV

对每个 outer-test geometry，将其真实 FEM S0 或 S1 response 当作 synthetic observation；只使用 outer-training surrogate，通过以下方式恢复 h,w：

```text
coarse deterministic domain grid search
+ bounded local optimization
+ multiple deterministic starts
```

不得用 test truth 初始化优化器。

Primary readiness 使用 S1/N1 weighting，并报告 S0/N1、S0/N2、S1/N2 诊断。

训练内恢复 Gate：

```text
p95 |height error| <= 0.25 nm
p95 |width error|  <= 0.05 nm
max |height error| <= 0.50 nm
max |width error|  <= 0.10 nm
no unresolved multimodal/tie case
```

所有 rejected/nonconverged cases 必须计入失败，不能从统计中删除。

---

## 13. First-execution stages

### M0 — closeout, design and static code

完成：

```text
Task005 final metadata closeout
fixed illumination contract
49-point mother grid
37 train / 12 blind split
reuse inventory
training/blind tuple hashes
static loader/transform/model/checker tests
```

不得运行 FEM，直到 M0 checker 通过。

### M1 — train37 forward campaign

严格执行 79 个新 FEM hard count；复用既有 exact records。形成不可变 train37 dataset。

### M2 — training-only surrogate qualification

完成 finite candidate comparison、grouped CV、uncertainty和 held-out synthetic recovery。

输出：

```text
outcomes/TRAIN37_MODEL_COMPARISON.json
outcomes/TRAIN37_OOF_PREDICTIONS.json
outcomes/TRAIN37_SYNTHETIC_RECOVERY.json
outcomes/TRAIN37_UNCERTAINTY.json
outcomes/TRAINING_MODEL_SELECTION_CANDIDATE.json
response_v1.md
```

即使全部 training Gates 通过，第一轮也不得运行 blind12；只允许生成：

```text
status = training_candidate_review_pending
```

然后停止等待 ChatGPT 审阅。

---

## 14. Prohibitions

第一轮不得：

- 运行 blind12 的任何 FEM；
- geometry active learning；
- 读取或搜索可能对应 blind12 的旧响应；
- 开始正式 Bayesian inversion；
- 使用实验数据；
- 恢复 Task004 任意角度代理；
- 增加 P 偏振、波长、材料或更多几何参数；
- 更改 forward SHA、mesh、p、MUMPS profile；
- 超出 79 个初始新 FEM；
- 将 GP variance 称为连续 Maxwell 真值不确定度。

---

## 15. Completion boundary

本轮成功仅表示：

```text
Task005 final closeout complete
37-geometry fixed-angle dataset complete
training-only forward surrogate candidate qualified
training-only synthetic recovery qualified
```

不表示：

```text
blind validation passed
formal inversion completed
experimental uncertainty calibrated
five/six-parameter surrogate solved
```

完成 M2 后提交、推送当前唯一代理分支并停止等待审阅。
