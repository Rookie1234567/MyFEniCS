# Task007 Review Report V1：离散 replay 成功、连续 MAP 误译诊断与 Schneider-faithful BO 修正

## 1. 审阅结论

Task007 V1 的结果不得概括为“两个参数仍然无法重建”。准确结论为：

```text
objective identity                         = pass
J1/J0 replay unique minimizer             = 11/11 pass
trained37 discrete replay BO              = 11/11 exact hit in 1 query
cold5 discrete replay BO                  = pass, median about 6 queries
random discrete replay                    = pass, median about 23–24 queries
one-shot continuous GP posterior mean MAP = 2/11 pass under frozen tolerance
Schneider method reproduced faithfully    = no
formal physical inversion                 = no
```

V1 已证明：对冻结的 48 点 replay universe，37 个离线 objective 值足以使 EI 在第一次离散查询中选中每个隐藏 target；这是一项有效的离散排序/查询结果。

V1 没有证明连续两参数重建失败。P3 只是“用 37 点拟合一次 objective GP，然后直接最小化 posterior mean”，并未执行 Schneider et al. 的连续 sequential Bayesian optimization。因此 P3 的 controlled-negative 只能归类为：

```text
one_shot_offline_posterior_mean_not_qualified
```

不得上升为：

```text
Schneider objective-GP failed
h/w not identifiable
six parameters are easier than two parameters
```

---

## 2. 原论文与 Task007 V1 的关键差异

### 2.1 原论文不是一次性 posterior-mean inversion

Schneider et al. 使用连续 Bayesian optimization：

1. 用预计算样本初始化 objective GP；
2. 在连续参数域优化 acquisition；
3. 对新参数真正运行 forward simulation，得到新的 objective；
4. 把新观测加入 GP；
5. 重复最多 150 次；
6. 评价已实际查询点中达到的 objective 和距 MAP 的距离。

Task007 P3 只做：

```text
37 offline points
-> fit GP once
-> minimize posterior mean once
-> no continuous EI query
-> no online objective observation
-> no GP update
```

因此 P3 不是论文中的主要方法。

### 2.2 原论文使用 100 个 Sobol 点及 objective derivatives

原研究为每次实验准备 100 个 6D Sobol training samples，并在每个点提供 posterior/objective 值及六个参数方向的导数。每个点不仅贡献一个函数值，还贡献六个梯度分量。

Task007 V1 使用：

```text
37 objective values
0 derivative observations
```

参数维数较低并不能抵消训练信息量的巨大差异。

### 2.3 原论文的测量向量远比当前 6 个标量丰富

原案例使用 S/P 偏振、两个方位角以及随入射倾角变化的完整反射强度谱。六个几何参数由一组较高维的 angular spectra 约束。

Task007 primary J1 只有：

```text
3 illuminations x (reflection m=0 + transmission m=0) = 6 scalars
```

参数数量不是可辨识性的唯一决定因素；测量维数、灵敏度方向和噪声合同同样重要。

### 2.4 当前 synthetic objective 人为制造了未观测的尖锐零值井

Task007 使用同一个 forward model 的无噪声 response 作为 synthetic measurement，因此：

```text
F(x_target) = 0
log10(F + 1e-12) = -12
```

而最近的 37 点离线 objective 在 J1/N1 下，中位最优 F 约为 10.7，即 log10F 约为 1。

所以 GP 只看到邻域中约 `O(1)` 的 log objective，却被要求在从未观察的内部位置推断一个约低 13 个数量级的 `-12` 尖井。平滑 Matérn GP 没有数据依据做出这种预测。

原论文使用真实实验数据，measurement noise 和 model discrepancy 使 MAP objective 通常不是精确零；其 log objective 不具有当前人为构造的 `-12` 单点针尖。

### 2.5 当前 offline design 不是面向 continuous objective GP 的 Sobol design

Task006 train37 最初为前向代理和 blind split 设计：

```text
24 / 37 geometries are boundary points
13 / 37 are interior points
```

这种设计适合覆盖参数矩形边界，但不等价于原论文的全域 Sobol space-filling design。P3 的目标恰好是内部连续极小值，因此训练点分布并不理想。

### 2.6 当前容差比原论文“进入测量不确定度区域”的标准严格得多

Task007 P3 要求：

```text
|dh| <= 0.25 nm
|dw| <= 0.05 nm
```

原论文按各参数局部测量不确定度归一化距离判断，例如其报告的 height 和 CD 标准差约为 2.484 nm 与 0.395 nm。不同物理系统不能直接数值对照，但 Task007 的绝对参数容差显著更严，不能用论文的“六参数成功”直接推断当前一次性 P3 必须通过。

---

## 3. 对当前结果的正确解释

### 3.1 P2 离散 replay 确实成功

P2 在 48 个已知候选坐标中执行 EI；target tuple 本身属于候选集合，但其 objective 只有被 query 后才揭示。11/11 第一次 query 命中，说明 objective GP 能利用 37 个离线 objective 正确判断最值得查询的离散内部点。

这不是 target-response leakage，但它只是有限候选主动搜索，不是连续参数重建。

### 3.2 P3 失败不说明 h/w 不可辨识

所有 11 个 target 在 48 点真实 objective 中都是唯一全局最小值；Task005 Fisher 和 Task006 synthetic recovery 也已经给出 h/w 可辨识的积极证据。

P3 的错误来源是：

```text
wrong algorithmic question
+ no online continuous observations
+ no gradients
+ zero-objective log cliff
+ boundary-heavy offline design
```

而不是“两个结构参数太难”。

### 3.3 GP 警告支持模型错配诊断

2022 次 fit 中记录 1626 个 optimizer warnings 和 1558 个 hyperparameter boundary collisions。LML 均有限，所以程序没有崩溃；但大量边界碰撞说明当前 objective target 与核/尺度合同存在明显张力，不能只靠一次 posterior-mean minimization解释连续最低点。

---

## 4. Task007 V1 状态冻结

保留所有现有文件和负结果，不改写：

```text
BAYESIAN_OPTIMIZATION_REPLAY.json
MAP_RECOVERY_SUMMARY.json
OBJECTIVE_GP_MODEL_AUDIT.json
Case146 checker
response_v1.md
```

状态冻结为：

```text
discrete_replay_BO              = passed
continuous_one_shot_P3          = controlled_negative
Schneider_faithful_continuous_BO = not_yet_executed
formal_inversion                = false
```

不得把 P3 删除后声称完整 benchmark 全面成功，也不得把 P3 负结果称为 Schneider 方法失败。

---

## 5. 下一步：M3 Schneider-faithful continuous BO benchmark

下一轮应停止 P3 路线，建立真正的 continuous sequential BO。

### 5.1 两层 benchmark

#### Level A：算法正确性 benchmark，允许零新 FEM

使用一个冻结的连续 response oracle，仅用于验证 BO 算法：

```text
oracle = Task006 locked Legendre-3 response model
label  = surrogate-oracle algorithm benchmark
```

该层不是物理资格化，也不得使用其结果批准 Task006；它只回答 continuous EI、online update 和 MAP recovery 实现是否正确。

#### Level B：真实 forward pilot，后续单独授权

Level A 通过后，才考虑 1–3 个 target 的真实 online Full3D FEM BO。不得在本轮自动运行。

### 5.2 Synthetic measurement 不再使用无噪声精确零目标

每个 off-grid target 使用固定 seed 生成：

```text
y_M = y_oracle(x*) + epsilon

epsilon ~ N(0, Gamma_N1) 或 N(0, Gamma_N2)
```

然后先在连续 oracle 上高精度求出真正的 objective MAP：

```text
x_MAP = argmin F(x | y_M)
```

评价 BO 恢复的是 `x_MAP`，而不是强制等于无噪声 hidden truth。

若保留无噪声诊断，应使用平滑变换：

```text
log10(1 + F)
```

而不是 `log10(F + 1e-12)` 形成未观测的 -12 尖井。正式 trained/noisy benchmark可继续使用 log10F，因为 F_MAP 不再为零。

### 5.3 真正的 continuous BO 循环

每一次迭代必须：

1. 用当前 observed objective 拟合 GP；
2. 在连续 `[115,125] x [16,18]` 域中全局优化 EI；
3. 在 EI 参数点调用连续 oracle；
4. 获取该点真实 objective；
5. 加入 observed set；
6. 更新 GP；
7. 记录 best actually evaluated point；
8. 重复最多 20 次。

主要成功指标应基于：

```text
best evaluated geometry
best evaluated F
queries to enter MAP tolerance
```

而不是只最小化一次 GP posterior mean。

当 EI 很小时，可按原论文建议冻结切换规则：

```text
continuous BO -> bounded L-BFGS-B / Powell local refinement
```

### 5.4 Offline design

比较两种初始化：

```text
D0 = existing train37 objective values
D1 = 37-point Sobol space-filling objective values from frozen surrogate oracle
```

D1 不运行 FEM，仅用于判断原 train37 边界型设计是否限制了 objective GP。

### 5.5 有限方法集合

```text
B0 random continuous search
B1 multi-start L-BFGS-B on oracle objective
P0 cold5 continuous BO
P1 Sobol12-trained continuous BO
P2 Sobol37-trained continuous BO
P3 existing-train37 continuous BO
```

不再设置 one-shot posterior-mean P3 为主 Gate。

### 5.6 建议 Gate

至少 12 个 off-grid target、每个 N1/N2 各固定一个 noise realization：

```text
trained37/Sobol37:
  >= 11/12 targets within |h-h_MAP| <= 0.25 nm and |w-w_MAP| <= 0.05 nm
  median online queries <= 8
  all targets <= 20 queries

cold5:
  report only; no forced speed-up claim
```

同时保存所有失败，不调整 target、noise seed 或容差。

---

## 6. 当前授权边界

本报告仅批准 M3 Level A 的 no-FEM algorithm benchmark。

禁止：

```text
Task006 residual retries
新 Full3D FEM
修改 Task006 model lock
把 surrogate oracle benchmark 称为物理验证
正式 Bayesian posterior sampling
新增结构参数、波长或 P 入射
```

M3 Level A 完成后提交结果并停止等待下一轮审阅。只有算法 benchmark 通过，才决定是否投入少量真实 FEM online pilot。
