# Task007 Review Report V2：M3 连续 sequential BO 算法通过、稳健性审计与物理 pilot 前置路线

## 1. 审阅结论

本轮正式批准并保留 Task007 M3 Level-A 的实现、结果与负结果：

```text
continuous sequential objective-GP BO loop        = approved
frozen Legendre-3 response oracle identity         = approved
12 off-grid targets                                = approved
fixed N1/N2 synthetic-noise realizations           = approved
J1/N1 P2 Sobol37                                   = 12/12 MAP hits, approved
J1/N2 P2 Sobol37                                   = 12/12 MAP hits, approved
J1/N1 and J1/N2 P1 Sobol12                         = 12/12 MAP hits, approved
J0/N1 P2                                           = 11/12, retain negative
existing train37 sequential comparison             = retain as design evidence
Task007 V1 one-shot posterior-mean negative         = retain unchanged
Case147 evidence-integrity checker                 = pass
new FEM                                             = 0
Task006 lock / data mutation                        = false
```

当前最准确的科学状态是：

```text
Schneider-style core sequential BO algorithm
on a frozen continuous surrogate oracle             = qualified

derivative-enhanced Schneider variant               = not reproduced
physical Full3D/FEM online reconstruction            = not qualified
experimental inversion                               = not authorized
```

Task007 V1 的 P3 负结果仍只表示：

```text
one_shot_offline_posterior_mean_not_qualified
```

M3 已证明，前述负结果不是“两参数不可重建”，而是一次性 GP 均值最小化并不是正确的 sequential BO 流程。

---

## 2. 主要结果的正确解释

### 2.1 主 J1 合同已经通过算法 benchmark

主观测合同 J1 为 A05/A07/A09 三照明下的 m=0 reflection/transmission order-total powers，共六个标量。主方法 P2 使用 37 个固定 Sobol 几何初始化 objective GP：

| 场景 | MAP 命中 | median online queries | p90 | max |
|---|---:|---:|---:|---:|
| J1 / N1 | 12/12 | 3.0 | 4.8 | 5 |
| J1 / N2 | 12/12 | 2.0 | 3.0 | 3 |

P1 Sobol12 也在 J1/N1、J1/N2 下均为 12/12，median queries 分别为 5.5 和 5.0。

这说明：

> 当标量 objective 可以在连续域中被真实查询并逐步加入 GP 时，二维 h/w 的 sequential BO 能稳定找到 noisy oracle MAP。

### 2.2 Existing train37 的问题主要是采样设计，而非参数不可辨识

使用现有 Task006 train37 作为 initialization 的 sequential EI 对照为：

```text
J1/N1 = 9/12
J1/N2 = 10/12
```

而相同数量的 Sobol37 为 12/12。这说明原 train37 的边界重采样设计适合前向代理与内部验证，但不是 objective BO 最优的全域空间填充设计。

### 2.3 J0 secondary negative 必须保留

P2 的 J0/N1 为 11/12，不能写成全部通过。J0/N2 为 12/12。J1 与 J0 仍必须保持独立 objective，不得把 aggregate 与其主要衍射级同时加入一个 likelihood。

---

## 3. M3 实现中已确认正确的部分

### 3.1 没有 target objective 泄漏

- 12 个目标均不属于 train37；
- hidden target 不在 cold5、Sobol12、Sobol37 或 existing train37 initialization 中；
- 每个 online objective 只有在 acquisition 正式提出该几何后才进入 observed set；
- GP 每轮重新拟合并更新；
- 主指标使用 best actually evaluated point，而不是未经查询的 GP posterior minimum。

### 3.2 Noisy MAP 没有被强制为 hidden target 或零 objective

每个 target/contract/noise 组合先生成固定噪声 measurement，再对冻结 oracle objective 求连续 MAP。48 个 MAP objective 全部为正，因此不再存在 V1 中未观测 `F=0 -> log10F=-12` 的针尖问题。

### 3.3 身份与边界保持正确

```text
oracle candidate          = frozen Task006 Legendre-3
Task006 model-lock SHA    = unchanged
train37 manifest SHA      = unchanged
new FEM                   = 0
Task006 failed tuples     = not retried
```

M3 结果不得回写为 Task006 blind qualification，也不得改写 Task006 的 paused status。

---

## 4. 当前结果仍不能被解释为物理反演通过

### 4.1 measurement 与 online oracle 来自同一个响应代理

M3 的 hidden measurement、offline responses、online query responses 和 oracle MAP 全部由同一个冻结 Legendre-3 response model生成。因此它没有包含：

```text
Full3D discretization error
surrogate-oracle discrepancy
online FEM numerical failures
experimental model discrepancy
real measurement covariance
```

M3 是重要的算法验证，但它是 self-consistent oracle benchmark，不是独立物理验证。

### 4.2 P2 的 37 个初始化点不是零成本

当前报告只统计 online queries。对于未来真实 Full3D 路线，每个初始化 geometry 需要 A05/A07/A09 三次 FEM；该响应库可在多个 measurement 之间复用，但第一次建立并非免费。

J1/N1 的典型总 response-evaluation 账本为：

```text
P1 Sobol12: 12 offline + 5.5 median online ≈ 17.5
P2 Sobol37: 37 offline + 3.0 median online ≈ 40.0
```

对于单个待测对象，P1 更省总查询；若同一 response library 服务很多 measurement，P2 的 offline 成本可摊销。按当前中位数，P2 在约 10 个以上 measurement 时才开始优于 P1 的摊销成本；N2 的交叉点约为 9 个 measurement。

现有 train37 已经是 sunk cost，但其 MAP hit rate 较低。下一步应先研究少量 Sobol augmentation，而不是直接重新计算完整 Sobol37 FEM 库。

### 4.3 当前停止规则使用了隐藏 oracle MAP

`run_sequential_bo` 在 best evaluated point 进入已知 oracle-MAP tolerance 时停止。该规则不会改变“首次命中 MAP 容差”的 query 数，因此现有 first-hit 指标仍有效；但真实反演时 MAP 未知，不能作为可部署 stopping rule。

后续必须使用 response-blind stopping，例如：

```text
EI below threshold
+ objective improvement stagnation
+ maximum query budget
```

然后仅在 benchmark 结束后用隐藏 MAP 评分。

### 4.4 Oracle MAP 尚缺少独立全局最优复核

当前 MAP 由 161x161 grid 加多起点 L-BFGS-B 得到；部分局部优化 run 报告 line-search failure，但多个起点通常收敛到同一 objective。Case147 重新计算了报告 MAP 上的 objective，却没有用第二种全局算法独立证明没有更低极小值。

因为 queries-to-MAP 的定义依赖该 reference MAP，物理 pilot 前必须补充独立 MAP stability audit。

### 4.5 Case147 是强 evidence checker，但不是第二套 acquisition 实现

Case147 核验了：

```text
source hashes
measurement/noise identities
query objective values
history/best-point/query-count
GP update count/LML finiteness
no target initialization leakage
```

但它复用了同一 `continuous.py` oracle/utility，并没有逐步独立重拟合 GP、重新最大化 EI 并验证每个 chosen query。45,054 项检查不能被描述成“独立重现全部 acquisition 算法”。

### 4.6 一个噪声 realization 不足以说明统计稳健性

每个 target/contract/noise 当前只有一个固定 noise seed。12/12 可能代表算法稳定，也可能部分受这组噪声 realization 影响。进入 Full3D pilot 前，应先在 surrogate oracle 上执行有限的 noise Monte Carlo。

### 4.7 GP warning 仍需分类

M3 共：

```text
sequential GP updates          = 1361
selected-run warnings          = 2028
selected-run boundary hits     = 196
bounded local refinements      = 473
```

所有 LML 有限，结果没有因此作废；但下一轮必须按 warning 类型、kernel 参数和方法分组报告，避免用一个总数掩盖重复的超参数边界问题。

---

## 5. 正式状态

```text
Task007 V1 discrete replay             = approved as discrete-query evidence
Task007 V1 one-shot continuous P3      = controlled negative, retained
Task007 M3 Level-A sequential BO       = approved with scope limitations
primary J1 surrogate-oracle algorithm  = qualified
physical online-FEM BO                 = not yet authorized
formal Bayesian inversion              = not authorized
```

---

## 6. Required M4A：无新 FEM 的稳健性与独立性闭合

M4A 新 FEM 预算为 0。不得修改 M3 artifacts、targets、noise seeds 或原 traces；新增 companion evidence。

### 6.1 Independent oracle-MAP stability audit

对全部 48 个 target/contract/noise 组合，使用与现有 grid+L-BFGS-B 不同的确定性方法复核，例如：

```text
finer independent grid or adaptive subdivision
+ scipy differential_evolution / SHGO（二选一并冻结）
+ bounded local polish
```

保存：

```text
原MAP与复核MAP
objective difference
h/w difference
是否存在 objective-equivalent multiple minima
optimizer/evaluation counts
```

建议 Gate：

```text
abs(F_new-F_old) <= 1e-6 * max(1,abs(F_old))
且 |dh| <= 0.02 nm, |dw| <= 0.005 nm
```

若坐标不一致但 objective 等价，应报告 multi-minimum/non-identifiability，而不是强行选择一个唯一 MAP。

### 6.2 Standalone acquisition replay

至少对 primary J1 的以下 24 条 P2 trajectories：

```text
12 targets x N1/N2
```

建立独立 replay checker，从每一步的 observed `(x,F)` 开始：

1. 重新拟合 frozen objective GP；
2. 重新计算 grid EI；
3. 重新执行连续 EI/local-refinement 规则；
4. 验证 chosen point、mode、EI 和 objective trace；
5. 不读取下一步 stored query 作为输入。

若计算允许，同时覆盖 P1 Sobol12。不得调用原 M3 runner 直接复制结果。

### 6.3 Response-blind stopping audit

冻结一个不知道 oracle MAP 的停止合同，例如：

```text
max online queries = 20
stop if max grid EI < 1e-3 for two consecutive updates
and best log-objective improvement < 1e-3 for three consecutive queries
```

重新执行 primary J1 P1/P2 trajectories，并在运行结束后才用 oracle MAP 评分。现有 first-hit 结果继续保留，不得覆盖。

### 6.4 Noise Monte Carlo

仅对 primary J1，冻结：

```text
12 off-grid targets
N1 and N2
10 new deterministic noise seeds per target/scenario
P1 Sobol12 and P2 Sobol37 only
```

至少报告：

```text
MAP-hit fraction within 20 online queries
median / p90 / max queries-to-MAP
response-blind stop success
failure target/noise taxonomy
MAP displacement from hidden geometry
```

M4A readiness Gate：

```text
P2: each N1/N2 MAP-hit fraction >= 0.90, median <= 8, p90 <= 15
P1: each N1/N2 MAP-hit fraction >= 0.85, median <= 10, p90 <= 18
```

这些是算法-oracle Gate，不是物理精度 Gate。

### 6.5 Offline/online cost and finite augmentation study

只比较以下冻结 initialization：

```text
I0 existing train37
I1 Sobol12
I2 Sobol37
I3 train37 + Sobol6
I4 train37 + Sobol12
```

不得增加更多 initialization zoo。报告：

```text
initial response count
median/p90 online queries
single-measurement total evaluations
total/amortized evaluations for 1, 10, 100 measurements
new physical FEM count relative to already-existing train37
```

该结果用于选择未来 Full3D pilot 的初始化方案。

### 6.6 GP warning taxonomy

按以下维度汇总 warning/boundary collisions：

```text
method
contract/noise
observed count
selected jitter
fitted length scales
constant/noise levels
warning message/category
```

不得为了减少 warning 在 M4A 中更改 kernel bounds；先诊断，后续另行冻结改动。

### 6.7 Required artifacts

```text
M4_MAP_STABILITY_AUDIT.json / .md
M4_ACQUISITION_REPLAY_AUDIT.json / .md
M4_RESPONSE_BLIND_STOPPING.json / .md
M4_NOISE_MONTE_CARLO.json / .md
M4_INITIALIZATION_COST_STUDY.json / .md
M4_GP_WARNING_TAXONOMY.json / .md
Case148 independent checker
response_v3.md
```

完成后停止等待 Review V3。

---

## 7. 后续物理 Level-B 方向（本轮尚不授权 FEM）

M4A 通过后，再决定真实 Full3D pilot。优先原则：

1. 不直接重新计算 37 个 Sobol geometry；
2. 先检查 `train37 + Sobol6/12` 是否达到 P2 级稳健性；
3. 若可行，只新增 18 或 36 个离线 FEM（每 geometry 三照明）；
4. 冻结一个或少量 off-grid hidden target；
5. measurement、initial library、online query 均使用同一 frozen Full3D identity；
6. response-blind stopping；
7. 任一 forward numerical failure单独归类，不得误判为 BO/反演失败；
8. 不根据 pilot response 换模型、改 acquisition 或改容差。

Level-B 至少要区分：

```text
algorithm failure
objective non-identifiability
forward numerical failure
surrogate/FEM discrepancy
measurement-noise effect
```

在 Review V3 前，不得运行上述新 FEM。

---

## 8. 给 Codex 的执行边界

```text
请执行 git pull --ff-only，并完整阅读：

surrogate_tasks/task007_schneider_objective_gp_benchmark/
review_report_v2.md

保留Task007 V1和M3全部结果，不得覆盖或重写。

严格执行M4A，new FEM=0：
- 独立复核48个oracle MAP；
- standalone重放J1 P2的24条acquisition trajectories；
- 建立不使用隐藏MAP的stopping rule；
- 对J1的P1/P2执行10-seed noise Monte Carlo；
- 比较train37、Sobol12、Sobol37、train37+Sobol6/12的总成本与稳健性；
- 汇总GP warning和boundary-collision类型；
- 建立Case148 checker和response_v3.md。

完成后推送并停止等待Review V3。
不得运行FEM、修改Task006 model lock、重试Task006失败点、开始正式反演或扩展参数。
```