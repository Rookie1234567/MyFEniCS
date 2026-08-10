# Task037-extra Review Report V7：H1R3 全部通过，授权低于 2 GB 的 PDE 快速推进路线

## 0. 审阅身份与最终决定

```text
review                         = Task037-extra Review Report V7
working_branch                 = codex/20260806-task37-iterative-extra-development
reviewed_handoff               = docs/task37_extra_development/response_v6.md
reviewed_H1R3_0R_source        = 5529a0159ac5b1500b4ccbd17ad962e2a875f3f1
reviewed_H1R3_1_source         = c133a803d6086f6df8bf2cf703a53b43a79419c1
reviewed_H1R3_2_source         = d25669db29a25608685cce3bfff1f63379885aa5
H1R3_0R                        = ACCEPTED_PASS
H1R3_1                         = ACCEPTED_PASS
H1R3_2                         = ACCEPTED_PASS
action_layer                   = QUALIFIED_FOR_PDE_PRECONDITIONER_DEVELOPMENT
new_authorized_lane            = Candidate H-PDE fast track
H2                             = UNLOCKED_WITH_SEQUENTIAL_GATES
H3_geometric_MG                = DEFERRED_UNTIL_FIRST_H10_PDE_RESULT
H4_time_harmonic_PDE           = CONDITIONALLY_AUTHORIZED_AFTER_H2_GATES
full_PDE_memory_hard_target    = process-tree RSS < 2,000,000,000 B
swap                           = strictly_zero
bounded_codex_autonomy         = AUTHORIZED
create_new_branch              = FORBIDDEN
pull_request                   = FORBIDDEN
merge_to_master                = PERMANENTLY_NOT_PLANNED
ordinary_default_change        = FORBIDDEN
```

本审阅接受 H1R3.0R、H1R3.1 和 H1R3.2 的数值、MPI、资源、缩放和证据闭合。
Candidate H 的 full-space rank-one matrix-free volume action 已经证明：

- p6/h10 MPI1 连续作用无 RSS 爬升；
- p6/h10 MPI2 与 MPI1 canonical identity 闭合；
- p6/h5 retained payload、临时缓冲和 action 时间近似线性增长；
- 不形成 global matrix、condensed Schur、dense cell tensor 或任何 factor；
- 当前 action-only 峰值远低于用户的 2 GB 目标。

但用户最终目标仍未完成。当前尚未证明：

- 一个低存储预条件器能够近似 `A^{-1}r`；
- 原始时谐 Maxwell + Floquet + DtN 方程能够收敛；
- 完整 KSP、预条件器、DtN、恢复和后处理同时存在时峰值仍低于 2 GB；
- R/T/A、体吸收和 12+12 通道与 p6/h10 直接法 authority 一致。

为尽快推进 PDE，本审阅不再要求每个小型执行问题都停下来等待主审。Codex 获得受控自主权：
在本报告明确列出的架构、参数集合、内存上限和运行次数内，可以自行修复 runner、MPI、
MPC、遥测、内存生命周期、局部 block、coarse basis 和 DtN 接线问题，并继续顺序 Gate。
不得借此改变物理问题、放宽 2 GB 上限或开启无界算法搜索。

---

# 1. 最新 H1R3 证据审阅

## 1.1 H1R3.0R：MPI1 warm-repeat

| 指标 | 实测 |
|---|---:|
| rows / constraints | `173802 / 9210` |
| candidate applies | `12` |
| steady apply median | `1.1820809360360727 s` |
| first / last relative error | `2.7326039504560278e-17 / 2.7326039504560278e-17` |
| deterministic | `true`，12 次 output SHA 完全一致 |
| retained payload | `6151104 B` |
| packed temporary | `3556224 B` |
| steady RSS span | `0 B` |
| completed process-tree peak | `340541440 B` |
| swap | `0` |
| status | `PASS` |

该结果证明 future KSP 反复调用 volume action 时，没有观察到 packing 数组累积、allocator
持续增长或数值漂移。

## 1.2 H1R3.1：MPI2 partition identity

| 指标 | 实测 |
|---|---:|
| same-run relative error | `2.663167576790903e-17` |
| MPI2 vs MPI1 canonical relative L2 | `5.727032975605686e-15` |
| missing / extra / duplicate | `0 / 0 / 0` |
| candidate second apply | `0.6196997419465333 s` |
| retained global sum | `6988752 B` |
| payload / row | `40.21099872268444 B/row` |
| process-tree peak | `636989440 B` |
| swap | `0` |
| status | `PASS` |

因此 remote master、ghost accumulation、MPC `R^H` 和 slave identity 在完整 p6/h10
MPI2 下已获得正式 action-only 资格。

## 1.3 H1R3.2：p6/h5 h-refinement scaling

| 指标 | 实测 |
|---|---:|
| rows / cells / axes / constraints | `1127502 / 1680 / (12,5,28) / 34542` |
| relative error | `2.868804640065144e-17` |
| retained payload | `38290752 B` |
| retained payload / row | `33.9606954134006 B/row` |
| packed temporary / row | `21.027155605932407 B/row` |
| payload exponent | `0.9779306095631883` |
| candidate second apply | `7.548130201874301 s` |
| action seconds / row | `6.694560366078553e-6 s/row` |
| process-tree peak | `638500864 B` |
| peak increment slope | `312.42468700849327 B/row` |
| swap | `0` |
| status | `PASS` |

H1R3.2 的 action-only p6/h1 线性外推约为：

```math
P_{h1,action,pred}
=
36.692207894\times 10^9\ \mathrm{B}
\approx
34.172\ \mathrm{GiB}.
```

它不是 full solver 预测，但相对未来 2 TiB 总预算是积极信号：volume action 本身不再是
内存瓶颈。未来的主要风险已经转移到 smoother、coarse basis、Krylov vectors、DtN 和
迭代次数。

---

# 2. 当前 p6/h10 PDE 的严格内存预算

用户要求完整 MPI1 PDE 的 process-tree RSS 严格低于：

```math
M_{hard}=2,000,000,000\ \mathrm{B}.
```

H1R3.0R action worker 的 completed peak 为：

```math
M_{action}=340,541,440\ \mathrm{B}.
```

理论剩余空间为：

```math
M_{headroom}
=
2,000,000,000-340,541,440
=
1,659,458,560\ \mathrm{B}.
```

这不表示所有下面对象可以简单相加到该数值，因为 setup、solve 和 recovery 可以分阶段释放；
但它给出了必须遵守的设计上限。

## 2.1 在线 solve 阶段预算

| 对象 | 预算上限 |
|---|---:|
| exact-class local block factors + block metadata | `<= 400,000,000 B` |
| full-space 75D wave basis `Z` | `<= 240,000,000 B` |
| retained `AZ` | `0 B`，setup 后必须释放 |
| KSP basis + PC work vectors | `<= 300,000,000 B` |
| matrix-free DtN + boundary/mode arrays | `<= 150,000,000 B` |
| coarse dense matrix/factor + telemetry | `<= 50,000,000 B` |
| allocator/MPI/runtime reserve | `>= 250,000,000 B` |

一个 full-space p6/h10 complex128 vector 的纯 owned storage 约为：

```math
173802\times16
=
2,780,832\ \mathrm{B}.
```

75 个 full-space coarse vectors 的纯数值 storage 约为：

```math
173802\times75\times16
=
208,562,400\ \mathrm{B}.
```

因此 75D wave basis 在当前 h10 上可进入 2 GB 预算，但只允许保留 `Z` 和小型 coarse
matrix；`AZ` 必须逐列生成 coarse matrix 后释放，不得与整个 solve 同时常驻。

## 2.2 预运行 live-set Gate

在任何 20-step PDE screen 前，必须根据真实对象 bytes 计算：

```text
predicted simultaneous live set <= 1,750,000,000 B
```

若预测超过该值，不启动 PDE。优先通过以下生命周期修复降内存：

1. 释放 reference action、assembled authority 和 canonical export 对象；
2. coarse setup 逐列计算 `AZ`，只保留 `Z` 与 `E^{-1}`；
3. FGMRES restart 从 30 降到 20；
4. solver 结束后先销毁 KSP/PC/coarse/block factors，再做场恢复与后处理；
5. 必要时将 solve 与 recovery/postprocess 放在连续 subprocess 中，以操作系统回收阶段高水位。

禁止通过降低 p、增大 h、减少 DtN 通道或跳过物理 Gate 来满足内存预算。

## 2.3 Watchdog Gate

```text
warning threshold     = 1,750,000,000 B
controlled termination = 1,950,000,000 B
formal completed peak  < 2,000,000,000 B
swap                   = 0
```

终止阈值低于正式上限，用于给 0.25 s 采样间隔和终止延迟留出安全余量。

---

# 3. 快速 PDE 路线的总体架构

本审阅授权的第一条 PDE 架构为：

```text
exact full-space matrix-free volume action
+ matrix-free DtN action
+ exact-class-reused overlapping element-block smoother
+ fixed 75D full-space wave coarse correction
+ right FGMRES(restart 20 or 30)
```

它有意复用历史唯一成功的结构原则：

```text
强局部误差处理
+
显式波传播 coarse
+
flexible outer Krylov
```

但不再保存 16 个 growing trace-slab ILU factors。

## 3.1 为什么暂时不先做完整 geometric MG

H3 geometric multigrid 对最终 p6/h1 仍可能有价值，但它需要新建嵌套 H(curl) transfer、
coarse communicator 和多层 solver。为了尽快获得第一次低于 2 GB 的时谐 PDE 结果，V7
决定先使用已经有历史正证据的 fixed wave coarse，并把 geometric MG 推迟到第一条 h10 PDE
full result之后。

若 element-block + 75D wave coarse 在 h10 完全没有收敛信号，不能据此宣布所有 full-space
multigrid 都失败；但本 fast track 将停止，届时再重新审阅 H3。

---

# 4. H2A：exact-class block inventory 与 factor memory Gate

## 4.1 Coercive local operator

第一阶段局部 block 使用强制性 proxy：

```math
B_0
=
K_{curl}
+
k_0^2M_{|\epsilon|}.
```

这不是最终时谐方程，只用于证明局部 block inverse 和 smoother 能稳定处理 full-space
H(curl) 误差。

## 4.2 Exact class key

每个 local block class 必须至少绑定：

```text
cell widths/Jacobian class
material tag and coefficients
Basix orientation/permutation class
boundary/Floquet constraint pattern
local DoF ordering
proxy/shift identity
```

只允许 exact class reuse。不得将数值近似但不相同的 block强行共享。

p6 cell block 的 dense complex128 matrix payload约为：

```math
882^2\times16
=
12,446,784\ \mathrm{B}
\approx
11.87\ \mathrm{MiB}.
```

32 个完全独立 class 的纯 LU value storage约为 380 MiB，因此冻结 Gate 为：

```text
unique exact block classes <= 32
retained block-factor payload <= 400,000,000 B
no per-cell factor
no slab factor
```

若 class 数超过 32，只允许：

- 修正错误的 class key 过度区分；
- exact numeric hash dedup；
- 共享 symbolic/local mapping；

不得 approximate merge 或删除物理差异。

## 4.3 H2A 输出

```text
benchmarks/cases/101_task37_extra_development/records/h2_block_class_inventory.json
docs/task37_extra_development/outcomes/h2_block_class_inventory.md
```

必须报告 h10 与一个小型 refinement fixture 的 class count，证明重复细化不会因 cell 数增长而
线性增加 class 数。

---

# 5. H2B：coercive block smoother 与 two-level oracle

## 5.1 Smoother

优先实现 deterministic colored symmetric overlapping cell-block smoother：

```text
forward colored cell sweep
+
backward colored cell sweep
+
multiplicity/partition-of-unity weighting
```

局部 solve 使用 H2A 的 class-shared factor。不得每个 cell 保存 factor；cell 只能保存 class ID
和最小 local gather/scatter identity。

Codex 可以在 additive weighted 与 symmetric colored 两种固定形式之间自行选择；若 additive
one-apply contraction明显不足，可直接切换到 symmetric colored，不需要等待新 review。禁止继续扩展
为 edge-star、face-star 或大量 patch 类型，除非本报告的 block memory Gate仍然满足且 raw 明确证明
cell block遗漏一个单一的界面模式。

## 5.2 Residual sources

至少测试：

```text
gradient-dominated
curl-dominated
mixed
checkerboard/high-frequency
```

定义：

```math
\rho_s
=
\frac{\|r-B_0M_s^{-1}r\|_2}{\|r\|_2}.
```

最低 Gate：

```text
all sources finite and deterministic
checkerboard/high-frequency rho <= 0.70
mixed rho <= 0.85
gradient-dominated rho <= 0.95
curl-dominated rho <= 0.95
block factor payload <= 400,000,000 B
H2 worker completed peak <= 1,100,000,000 B
swap = 0
```

## 5.3 75D wave coarse

H2B 的 global two-level oracle使用固定 75D full-space wave basis：

```math
Z\in\mathbb C^{N\times75}.
```

要求：

- 优先复用/迁移 Task027/Task030 已验证有效的 physical z-wave construction；
- basis 必须在 full-space p6/MPC identity 下重新验证；
- rank 必须为 75，或明确报告实际独立 rank；
- coarse matrix逐列 action构造；
- 只保留 `Z` 与 small dense coarse factor；
- 不保留完整 `AZ`；
- online additional retained payload `<=240,000,000 B`。

coarse correction 使用当前被求解算子的 Galerkin matrix：

```math
E=Z^HBZ.
```

coercive two-level PC 顺序固定为：

```text
pre-smooth
-> exact residual
-> wave coarse correction
-> exact residual
-> post-smooth
```

## 5.4 Coercive global solve Gate

允许在 p6/h10 MPI1 上求一个固定 coercive manufactured RHS：

```text
right FGMRES restart = 20 or 30
relative tolerance   = 1e-8
maximum iterations   = 400
```

Gate：

```text
explicit true residual <= 1e-8
reported/true residual agreement <= 1e-10 absolute or 1e-3 relative
iterations <= 400
completed process-tree peak <= 1,600,000,000 B
swap = 0
no global matrix / no Schur / no growing factor
```

H2B 通过后，Codex 可直接进入 H4A，不需再次等待审阅。

---

# 6. H4A：原始时谐 PDE 的 matrix-free 20/100/200-step 漏斗

## 6.1 Exact operator

最终 fine operator必须保持：

```math
A
=
K_{curl}
-
k_0^2M_{\epsilon}
+
A_{DtN}.
```

要求：

- volume 使用 H1R3 qualified rank-one action；
- DtN 使用 action-only/matrix-free coupling；
- primary path 中 explicit dense `C/D` count为 0；
- actual incident RHS、Floquet identity和 80-mode authority保持冻结；
- 不静态凝聚；
- 不形成 global A；
- 不形成 p6 slab factor。

若 Task037 matrix-free DtN 遥测/API仍有执行问题，Codex 获准自行修复 `MatPython` stats、
Vec layout、MPI ownership、mode packing和生命周期；不得改变 DtN 数学定义、模式集合或物理归一化。

## 6.2 Absorptive local proxy

时谐 PDE 的 local smoother使用：

```math
B_{\beta}
=
K_{curl}
-
k_0^2M_{\epsilon}
+
i\beta k_0^2M_{|\epsilon|}.
```

允许的固定候选只有：

```text
beta = 1.0
beta = 0.5
```

Codex 可以根据四源 one-apply contraction自行选择第一个 beta；若 20/100/200 screen出现明确
平台，可以使用另一个 beta再运行一次。不得扫描更多 beta。

wave coarse 使用 exact fine operator的 Galerkin matrix：

```math
E_A=Z^HAZ.
```

同样只保留 `Z` 和 small dense factor，不保留 `AZ`。

## 6.3 KSP 与内存

```text
outer KSP      = right FGMRES
restart        = 30，若 live-set预测超限则固定改为20
true residual  = every 10 iterations
screen         = 20 -> 100 -> 200
```

禁止 restart 90。KSP/PC setup完成后、正式迭代前必须输出真实 live-set ledger。

## 6.4 Screen Gate

时间可以较长，因此本报告将主要 Gate放在残差趋势和内存，而不是短 wall。

最低趋势 Gate：

| 点 | 最低要求 |
|---|---:|
| 20 steps | true residual `<=0.60` |
| 100 steps | true residual `<=0.20` |
| 200 steps | true residual `<=0.08` |
| 150->200 | 至少再下降 `15%`，不得形成 B2/B4 型平台 |

Preferred Gate：

```text
20-step  <= 0.20
100-step <= 0.05
200-step <= 0.01
```

所有 screen 同时要求：

```text
completed process-tree peak < 2,000,000,000 B
swap = 0
reported/true residual consistent
all vectors finite
no official RTA before convergence
```

若 200-step 达到 minimum Gate，可直接进入 full solve。时间较长不是停止理由，只要内存受控、
残差仍持续下降且 predicted full iterations `<=5000`。

## 6.5 一个受控 long-tail fallback

若 200-step residual未达到 minimum Gate，但局部 block contraction和前 100 步有明显正信号，
Codex 允许从当前 FGMRES 提取一次 harmonic Ritz augmentation：

```text
16 vectors first
32 vectors only if 16-vector capacity rank不足
```

augmentation加入现有 wave coarse，不替换它。额外 online retained payload必须
`<=100,000,000 B`。只允许一次 augmentation campaign，不得无界 recycling/deflation 扫描。

---

# 7. H4B：完整 p6/h10 PDE 与物理 Gate

只有 H4A 200-step minimum Gate通过才进入。

## 7.1 Full solve

```text
relative true-residual target = 1e-6
maximum iterations            = 5000
full-run timeout              = 12 hours safety limit
process-tree RSS              < 2,000,000,000 B
swap                          = 0
```

用户允许较长时间，因此 wall time不是 primary failure，只要：

- residual持续下降；
- 内存不超过 hard target；
- 无 nonfinite；
- projected wall仍有界。

## 7.2 生命周期

为保证最终峰值：

```text
solve stage:
  action + KSP + block factors + Z + DtN

then destroy:
  KSP / PC / block factors / Z / DtN work / temporary basis

then recovery/postprocess stage:
  field / explicit residual / RTA / channels
```

若 Python allocator使已释放对象仍保留高水位，允许在同一 run provenance下使用两个顺序
subprocess：solve 写出 canonical solution，第二个 subprocess读取并后处理。不得把 hot factor放硬盘反复读。

## 7.3 必须通过的数值和物理 Gate

```text
full-space explicit true residual <= 1e-6
augmented/DtN residual            <= 1e-6
reported/true residual consistent
R/T/A closure pass
volume absorption pass
12/12 significant channel power pass
12/12 boundary complex amplitude pass
canonical full-field identity pass
completed process-tree peak < 2,000,000,000 B
swap = 0
```

对照 authority 使用冻结的 p6/h10直接法结果。不得只比较总 R/T，而跳过逐通道复振幅。

正式 full原则上只运行一次；若第一次因本报告允许范围内的明确代码/执行缺陷失败，Codex可修复后
再运行一次，并保留首次 raw。不得因收敛慢而改物理或放宽 residual Gate。

---

# 8. Codex 受控自主权

用户希望加快推进。本审阅授权 Codex 在以下范围内自行解决问题，无需每个小问题等待新的
review。

## 8.1 可以自行修复

- runner、CLI、路径、schema、hash、checker和 fail-closed telemetry；
- MPI collective、ghost update、remote master和 MPC `R^H`；
- deterministic class key、exact hash dedup、coloring与 multiplicity weights；
- PETSc Vec/MatPython/KSP 生命周期和 buffer reuse；
- object release、restart20/30选择、subprocess staging；
- matrix-free DtN layout、mode packing、unsupported stats telemetry；
- wave basis full-space lift、orthonormalization、rank检测和逐列 coarse setup；
- one root-cause numerical implementation error in block smoother/coarse correction；
- timeout增加至本报告上限，只要 memory/error Gate不变。

## 8.2 允许的运行/修复次数

```text
component/unit/focused tests        = 不限，但必须有明确目的
H2A/H2B heavy rerun after code fix  = 每阶段最多2次
H4A screen candidate campaigns      = 最多3个
  - initial beta
  - alternate beta
  - optional Ritz augmentation
H4B official full                   = 最多2次
  - first formal run
  - one rerun after explicit code/execution fix
```

Codex不需要在这些授权次数内每次停下来等待审阅，但必须保留每次 raw、commit和失败分类。

## 8.3 仍然禁止

- 新建分支、PR、merge、rebase、cherry-pick或 force push；
- 修改 master或 ordinary default；
- 安装新依赖或切换有限元框架；
- 改 p、h、几何、材料、入射、Floquet、DtN模式集合或物理归一化；
- 放宽 2,000,000,000 B hard target；
- global assembled p6 matrix；
- static-condensed trace作为 Candidate H fine operator；
- per-cell factor、16-slab factor、disk-backed hot factors；
- LOR-HX 重开；
- beta无界扫描、patch类型无界扩张、20--90步 local Krylov；
- 未收敛时输出 official R/T/A；
- 删除或重写负结果 raw。

## 8.4 必须立即停止的情况

```text
predicted live set > 1,750,000,000 B and lifecycle fixes cannot lower
watchdog reaches 1,950,000,000 B
swap nonzero
nonfinite values
explicit action/PC identity failure > 1e-11
block factors > 400,000,000 B
class count grows with cell count
200-step PDE residual forms an unambiguous plateau after all 3 authorized campaigns
physical Gate disagrees with direct authority after true residual convergence
need to change physics or install dependency
```

---

# 9. 执行顺序与输出

## 9.1 顺序

```text
P0  H2A block class inventory and memory preflight
P1  H2B four-source contraction
P2  H2B coercive two-level global solve
P3  matrix-free DtN + actual RHS identity
P4  H4A 20/100/200-step time-harmonic screen
P5  H4B full solve and official physics
```

任一阶段科学/内存 hard stop后停止后续阶段；单纯执行/schema问题可在授权范围内自行修复并继续。

## 9.2 Tracked records

```text
benchmarks/cases/101_task37_extra_development/records/h2_block_class_inventory.json
benchmarks/cases/101_task37_extra_development/records/h2_coercive_two_level.json
benchmarks/cases/101_task37_extra_development/records/h4_dtn_action_identity.json
benchmarks/cases/101_task37_extra_development/records/h4_pde_screen.json
benchmarks/cases/101_task37_extra_development/records/h4_pde_full.json
```

只创建实际运行阶段的 record。

## 9.3 Outcomes

```text
docs/task37_extra_development/outcomes/h2_block_class_inventory.md
docs/task37_extra_development/outcomes/h2_coercive_two_level.md
docs/task37_extra_development/outcomes/h4_dtn_action_identity.md
docs/task37_extra_development/outcomes/h4_pde_screen.md
docs/task37_extra_development/outcomes/h4_pde_full.md
```

## 9.4 Consolidated response

```text
docs/task37_extra_development/response_v7.md
```

不为每个小修复新建 response 版本。`response_v6.md`保持为冻结 H1R3 authority。

## 9.5 Heavy raw

全部放入 ignored artifact目录：

```text
benchmarks/artifacts/task037_extra_h2_*/
benchmarks/artifacts/task037_extra_h4_*/
```

---

# 10. 下一次审阅所需回答

最终 `response_v7.md` 必须明确回答：

1. exact block class count是多少，是否随 refinement保持有界？
2. block factor、wave basis、KSP、DtN和总 live-set分别占多少？
3. coercive four-source contraction与global solve是否通过？
4. 75D full-space wave coarse是否真正提供全局误差修正？
5. matrix-free DtN与现有 authority的action/recovery误差是多少？
6. time-harmonic 20/100/200-step true residual轨迹如何？
7. 是否出现 B2/B4 型长尾；若出现，beta/Ritz fallback是否有效？
8. 完整 PDE是否达到 `1e-6` true residual？
9. process-tree正式峰值是否严格小于 `2,000,000,000 B`？
10. R/T/A、体吸收、12/12 power、12/12 complex amplitude是否与直接法一致？
11. 哪些运行失败、修复了什么、每个 heavy运行对应哪个 clean SHA？
12. 当前架构是否仍具有 p6/h1 近线性内存潜力？

---

# 11. 给 Codex 的执行摘要

```text
只在 codex/20260806-task37-iterative-extra-development 工作。
禁止新分支、PR、master合并和 ordinary default修改。

完整阅读 response_v6.md 与 review_report_v7.md，以 V7 为最高优先级合同。

H1R3.0R、H1R3.1、H1R3.2 已正式通过。现在授权按顺序执行：
H2A block class inventory -> H2B coercive smoother/two-level solve -> DtN identity
-> H4A 20/100/200-step PDE screen -> H4B full PDE。

完整 PDE process-tree RSS必须严格低于2,000,000,000 B，swap=0。
预运行 predicted live set必须<=1,750,000,000 B；watchdog在1,950,000,000 B受控终止。

你可以在 V7 第8节范围内自行修复执行问题并继续，不需要每次等待审阅；
但不得改变物理、放宽内存/误差Gate、扫描无限参数、恢复global matrix或slab factors。

最终统一更新 response_v7.md，提交并只push当前extra分支。
```
