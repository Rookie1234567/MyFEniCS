# Task007 Task Book：Schneider-style 两参数 objective-GP Bayesian optimization benchmark

## 0. Summary

本任务参考 Schneider et al. 的参数重建思路，但使用我们自己的 EUV 光栅、尺寸范围和固定照明。

关键区别：

```text
Task003/004/006：学习多输出 forward response y(x)
Task007：对一组给定 measurement y_M，直接学习标量 objective F(x|y_M)
```

输入仅为：

\[
\mathbf x=(h,w),
\qquad
h\in[115,125]\,\mathrm{nm},
\quad
w\in[16,18]\,\mathrm{nm}.
\]

第一轮是完全可复现的 stored-response replay benchmark，不运行新 FEM。完成后停止等待审阅。

---

## 1. Mandatory reading and branch gate

完整阅读：

```text
root AGENTS.md
surrogate_tasks/AGENTS.md
surrogate_tasks/task006_fixed_illumination_hw_surrogate/review_report_v3.md
surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/
    outcomes/DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json
本 README.md
本 task.md
```

确认：

```text
branch   = codex/only-one-13p5nm-surrogate-inversion
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
working tree clean before formal execution
```

不得 merge/rebase/cherry-pick master、Task037 或其他分支。

---

## 2. Literature contract and exact interpretation

参考文献：

```text
P.-I. Schneider et al.
Using Gaussian process regression for efficient parameter reconstruction
Proc. SPIE 10959, 1095911 (2019)
DOI 10.1117/12.2513268
arXiv:1903.12128
```

博客/论文中的核心流程是：

1. 对给定 measurement vector 构造 posterior 或 negative-log posterior；
2. 将预计算 forward responses 转换成该 measurement 对应的 scalar objective values；
3. 用 Matérn Gaussian process 学习 objective，而不是要求 GP 准确重建全部 optical response；
4. 用 expected improvement 选择新的参数；
5. 比较 offline-trained BO、cold-start BO 和局部/随机基准。

Task007 第一版不使用 objective derivative observations，因为当前完整二维域没有统一、独立的 response Jacobian 数据。不得假称复现了论文的 derivative-enhanced variant。

---

## 3. Frozen physical and observable identity

```text
wavelength_nm       = 13.5
incident polarization = S
height domain       = [115,125] nm
width domain        = [16,18] nm
A05                 = grazing 2 deg, azimuth 0 deg
A07                 = grazing 2 deg, azimuth 90 deg
A09                 = grazing 4 deg, azimuth 60 deg
forward identity    = fdf961545f217d620e22800f2704ae9913a6d270
model               = Full3D static uniform N1curl p5/h10/Ny4
observable schema   = task002.fixed-n0-orders.v3
```

### 3.1 Primary measurement contract J1

按固定顺序：

```text
A05 reflection m=0 order-total power
A05 transmission m=0 order-total power
A07 reflection m=0 order-total power
A07 transmission m=0 order-total power
A09 reflection m=0 order-total power
A09 transmission m=0 order-total power
```

共 6 个观测量。必须使用 S+P 的 `order_total_power`，不得拆分或改变 channel identity。

### 3.2 Secondary measurement contract J0

按相同角度顺序使用：

```text
R_total, T_total
```

共 6 个观测量。J0 与 J1 必须分别形成 objective；不得在同一个 likelihood 中同时加入 aggregate 与其 m=0 order power，避免重复计数。

### 3.3 Noise scenarios

沿用 Task005 provisional scenarios：

\[
\sigma_{N1}(y)=\sqrt{(0.01|y|)^2+(10^{-4})^2},
\]

\[
\sigma_{N2}(y)=\sqrt{(0.02|y|)^2+(5\times10^{-4})^2}.
\]

它们只是 synthetic benchmark 权重，不是实验标定 covariance。

---

## 4. Scalar MAP objective

对 target measurement \(\mathbf y_M\) 和任意 replay geometry \(\mathbf x\)：

\[
F(\mathbf x\mid\mathbf y_M)
=
\frac12
\bigl(\mathbf y_M-\mathbf y(\mathbf x)\bigr)^T
\Gamma^{-1}
\bigl(\mathbf y_M-\mathbf y(\mathbf x)\bigr)
+\Phi_{\rm prior}(\mathbf x).
\]

第一版 prior 为 bounded uniform prior：

```text
Phi_prior = 0 inside [115,125] x [16,18]
Phi_prior = +infinity outside
```

GP target 为：

\[
f(\mathbf x)=\log_{10}(F(\mathbf x)+\epsilon_F),
\qquad \epsilon_F=10^{-12}.
\]

必须同时保存未变换的 `F` 和变换后的 `log10F`。不得用目标点的已知零值初始化 GP，除非该点已被 acquisition 正式 query。

---

## 5. Frozen replay data

### 5.1 Offline source set

使用不可变 Task006 train37：

```text
benchmarks/artifacts/cases/137_task006_train37_dataset/train37/
```

共 37 个 geometry，每个 geometry 的 A05/A07/A09 三照明响应完整。

### 5.2 External target/query set

使用 Case141 中三照明均 `measured_pass` 的 11 个 geometry：

```text
(117.5,16.5)
(117.5,16.75)
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

以下 geometry 必须排除：

```text
(117.5,17.25)
```

原因是 A07/A09 没有通过 frozen forward residual Gate。

### 5.3 Replay universe

```text
37 offline geometries + 11 external geometries = 48 complete geometries
```

建立不可变 inventory，逐条绑定 source path、sample/formal hashes、forward identity 和 channel identities。

Task007 中的 11 个外部点称为 `external_replay_targets`，不得称为 Task006 formal blind pass。

---

## 6. Benchmark target protocol

对每个外部 geometry \(\mathbf x_*\)：

1. 其 stored response 作为 synthetic measurement \(\mathbf y_M\)；
2. 37 个 offline geometry 的 objective values 全部可用于 trained initialization；
3. 目标 geometry 的 objective 不得提前加入 GP；
4. acquisition 只有在 query 该 geometry 后才能获得其 objective truth；
5. query truth 只来自冻结 replay response，不调用 FEM。

必须验证：

```text
F(x*) <= 1e-12 before log floor
x* is a unique global minimizer over the 48-point replay universe
```

若某个 measurement contract/noise scenario 下存在多个数值不可区分 minimizers，必须保留并报告 non-identifiability，不能强行判定 exact recovery。

---

## 7. Finite method set

### B0 — nearest offline objective

直接返回 37 个 offline points 中 objective 最低者。它不是优化器，仅作为离散查表基准。

### B1 — random replay search

固定 initial points 后，对未观测 replay points 随机采样。使用预冻结 seeds；至少 100 个随机 repeats/target。

### P0 — cold-start Bayesian optimization

```text
initial observations = 5
six fixed maximin/Sobol-derived initial sets
kernel = Matérn-5/2 ARD
mean = constant
exact GP
acquisition = expected improvement
```

initial points 只能来自 train37，确保 external target 未被初始化观察。

### P1 — partially trained Bayesian optimization

```text
initial observations = 12 train37 points
six fixed maximin/Sobol-derived subsets
其余设置与 P0 相同
```

### P2 — fully offline-trained Bayesian optimization

```text
initial observations = all 37 train37 objective values
kernel = Matérn-5/2 ARD
acquisition = expected improvement
```

P2 是与 Schneider-style offline training 最接近的 primary 方法。

### P3 — posterior-mean MAP estimate

在 37-point objective GP 上，不调用 replay query，直接在连续 h/w 域内最小化 GP posterior mean：

```text
fixed dense grid
+ bounded local optimization
+ deterministic multistart
```

它用于判断 scalar objective GP 本身能否定位 MAP，不替代 BO query benchmark。

禁止加入新的 kernel/model zoo、神经网络、random forest 或 inverse neural network。

---

## 8. Gaussian-process and expected-improvement contract

输入缩放到 `[-1,1]^2`。

冻结：

```text
kernel            = Matérn-5/2 ARD
mean              = constant
jitter candidates = [1e-10,1e-8]
optimizer starts  = 8 deterministic starts
normalize_y       = true
```

只允许 training-only marginal likelihood 在两个 jitter 中选择；不得按 external target 的最终恢复成败切换 jitter。

最小化问题的 expected improvement：

\[
EI(\mathbf x)=
(y_{\min}-\mu)\Phi(z)+\sigma\phi(z),
\qquad
z=\frac{y_{\min}-\mu}{\sigma}.
\]

当 \(\sigma\) 近零时必须使用显式稳定分支。acquisition 并列时按冻结 replay geometry order 选择，不得随机改变。

---

## 9. Evaluation metrics

每个 target、contract、noise scenario 和 method 报告：

```text
best F versus online query count
simple regret
exact target hit count
queries to exact target
best parameter estimate after each query
|h-h*| and |w-w*|
normalized parameter distance
GP fitted kernel / LML / warnings
acquisition sequence and hashes
```

连续 P3 recovery tolerance：

```text
|h-h*| <= 0.25 nm
|w-w*| <= 0.05 nm
```

离散 replay exact-hit 指标要求查询到隐藏 target tuple 本身。

主要汇总：

```text
success fraction over 11 targets
median / p90 online queries
trained37 vs trained12 vs cold5 vs random
J1 vs J0
N1 vs N2 weighting
```

---

## 10. First-execution stages

### M0 — literature translation, inventory and objective audit

新 FEM 预算为 0。建立：

```text
outcomes/SCHNEIDER_METHOD_TRANSLATION.md
outcomes/REPLAY_DATA_INVENTORY.json
outcomes/REPLAY_TARGETS.json
outcomes/OBJECTIVE_CONTRACT.json
outcomes/OBJECTIVE_IDENTITY_AUDIT.json
```

独立 checker 必须验证：

```text
37 + 11 = 48 complete geometries
excluded incomplete geometry absent
all source/config/channel identities exact
no Task006 lock/data mutation
F(target)=0 within tolerance
no target objective leaked into initial GP
```

### M1 — deterministic objective-GP replay

实现 B0/B1/P0/P1/P2/P3，运行全部：

```text
11 targets
J1 and J0
N1 and N2
pre-frozen initial sets / random seeds
```

不调用 FEM。

### M2 — result qualification and benchmark report

生成：

```text
outcomes/OBJECTIVE_GP_MODEL_AUDIT.json
outcomes/BAYESIAN_OPTIMIZATION_REPLAY.json
outcomes/MAP_RECOVERY_SUMMARY.json
outcomes/METHOD_COMPARISON.md
outcomes/test_summary_v1.md
response_v1.md
```

建立独立 Case checker，从 raw stored responses 重建 objective arrays、GP initialization identity、acquisition sequence和全部汇总。

完成后停止等待审阅。

---

## 11. Readiness Gates

### 11.1 Objective identity

Primary J1/N1：

```text
unique replay minimizer at true target >= 10 / 11 targets
all objective arrays finite after log floor
no target leakage
```

若唯一最小值少于 10/11，应报告 measurement non-identifiability，而不是继续调 BO。

### 11.2 Fully trained BO

Primary J1/N1：

```text
exact target hit within <= 5 online queries for >= 10 / 11 targets
all 11 targets hit within <= 11 queries
no acquisition/query identity mismatch
```

### 11.3 Continuous scalar-GP MAP

Primary J1/N1：

```text
P3 recovery within h/w tolerance for >= 10 / 11 targets
no unconverged optimizer case silently removed
```

### 11.4 Comparative evidence

必须报告 P2 相对 cold-start BO 和 random search 的查询节省，但不预先规定必须达到某个倍数。若无加速，应保留为负 benchmark，不得修改 seeds、target set 或 method after seeing results。

J0、N2 和 synthetic noise Monte Carlo 作为 secondary diagnostics，不得覆盖 J1/N1 primary conclusion。

---

## 12. Why this benchmark is expected to be easier

预期成功率较高的原因：

1. 只有两个未知参数，而原论文处理六个；
2. GP 只拟合每个 measurement 对应的一个 scalar objective；
3. 三个照明已经由 Task005 Fisher DOE 选择，h/w 方向具有良好可辨识性；
4. 37 个预计算点已覆盖完整参数边界和中心区域；
5. 首轮使用同一 Full3D 模型生成的 synthetic measurements，没有实验 model discrepancy；
6. replay benchmark 不受新的 forward residual 失败影响。

但成功只表示算法 benchmark 成功，不表示真实实验反演、连续 Maxwell 真值或更多参数已经解决。

---

## 13. Prohibitions

首轮不得：

- 运行任何新 FEM；
- 重试 Task006 两个 residual failure；
- 修改 Task006 model lock 或 train37；
- 将 Case141 11 点重新称为 Task006 blind pass；
- 使用 target objective value 初始化 GP；
- 根据结果更换 target set、seeds、kernel 或 Gate；
- 开始 formal Bayesian posterior sampling；
- 增加 P polarization、波长、材料或新结构参数；
- 声称复现论文中的 derivative-enhanced GP。

---

## 14. Completion boundary

首轮成功仅表示：

```text
Schneider-style scalar-objective GP implemented
stored-response Bayesian-optimization replay completed
our two-parameter synthetic MAP benchmark quantified
```

不表示：

```text
Task006 blind validation passed
online direct-FEM BO passed
experimental inversion passed
formal uncertainty calibrated
```

M2 完成后提交并推送当前唯一代理分支，停止等待下一轮审阅。下一轮再决定是否授权少量 continuous direct-FEM Bayesian-optimization benchmark。
