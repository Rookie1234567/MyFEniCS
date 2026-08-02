# Task036 Reply to Review V6：接受方向，收窄低秩 Hybrid 恢复路线

## 0. 文档身份

```text
document                      = Task036 Reply to Review Report V6
reviewed_review               = review_report_v6.md
reviewed_review_commit        = dd44fdf7a6aca3f26326dfbb39c0cd1d35bf34b8
reviewed_numerical_head       = 0b43ec291bdf28b47bdaa7e2e99a66c97d4716c6
branch                        = codex/20260730-task36-forward-solver-bugfix-hardening
decision                      = ACCEPT_DIRECTION_WITH_MANDATORY_EXECUTION_REVISIONS
implementation                = not_started_by_this_reply
new_forward_PDE               = not_run
iterative_solver              = forbidden_in_current_batch
p6_generalization             = deferred_until_p5_candidate_pass
RCWA_coupling                 = not_authorized_in_current_batch
ordinary_default              = unchanged
master_merge                  = not_authorized
```

本文是用户要求形成的 **Review V6 执行前回复与范围收敛文件**。它不覆盖或删除
`review_report_v6.md`，也不冒充 Codex 完成实现后必须提交的 `response_v6.md`。

Review V6 的总体判断是正确的：exact FE trace-chain 已证明 direct Hybrid 域分解能够在
小掠射角和 P 偏振下恢复 Full3D，但它依赖完整 1200 维接口，因此当前只应称为
`research_oracle`；下一步应先判断 exact trace-chain 是否存在真正可压缩的端口空间。

本回复接受这一方向，但不批准 V6 原文中的全部 B0--B3、四档 rank、RCWA 映射、p6 clean
rerun 和层次矩阵研究同时展开。执行前必须先修正 localized-buffer 的代数等价风险，并按本文
冻结的顺序推进。

---

## 1. 结论先行

| V6 事项 | 回复决定 | 原因 |
|---|---|---|
| exact FE trace-chain 作为老师算子 | 接受 | 已有同源码 direct-vs-direct、完整 observable 和资源证据 |
| M120/M240 作为完整全局接口空间 | 接受 controlled negative | A007-P、strong trace、M 扩张和 joint-Cauchy 审计均否定 |
| M120 作为长程 core | 接受并保留 | selected-space exact FE operator 对照约为 `2e-11` |
| 先做低秩容量审计、后写 actual solver | 接受 | 能在低成本阶段提前停止无望路线 |
| localized buffer 直接凝聚回原 M120 | 不接受原表述 | 若保留坐标仍是原 M120，则只改变消元位置，不改变物理解 |
| B0--B3 四种 basis 同时开发 | 收窄 | 首批只允许 B0、B1 和完整 oracle B∞ |
| rank `120/240/360/480` 全部执行 | 收窄 | 固定 M120 核心已是 240 个 primal columns；离线只比较 `r=0/40/80/120`，即总维数 `240/280/320/360` |
| clean A007/A004/p6 三点前置 | 收窄 | 先只 clean 复现 A007；p6 当前需要非平凡泛化，不能伪装成重跑 |
| RCWA 进入首批 basis 实现 | 暂缓 | 当前 Task036 分支没有可审计的 RCWA 报告、代码身份和完整通道数据 |
| iterative/FGMRES/PC | 继续禁止 | 用户未授权；本批只研究 direct Hybrid 接口压缩 |
| master merge | 继续禁止 | Task036 仍是 research branch，必须后续选择性审查 |

正式建议为：

```text
clean A007 exact-oracle anchor
→ B0/B1/B∞ 离线同维容量审计
→ anti-equivalence + resource upper-bound Gate
→ 只实现一个 M120+r localized corrector
→ A004-S actual
→ A007-P confirmation
```

任何前置 Gate 失败均停止，不自动切换 RCWA、POD、H-matrix、p6 或迭代法。

---

## 2. 对 V6 核心事实的接受

### 2.1 exact trace-chain 的正确定位

接受以下三层命名：

```text
physical-QEP modal Hybrid M120/M240
    = robust full-channel controlled negative

exact FE trace-chain direct
    = same-discretization equivalence pass / research oracle

scalable compressed Hybrid
    = not implemented
```

exact trace-chain 已证明：

- P 偏振和小掠射角不是 Hybrid 域分解的天然禁区；
- endpoint sign、DtN、traction、recovery 和逐 cell Schur 链可以闭合；
- 旧 Hybrid 的主要错误来自截断接口空间，而不是 selected M120 core 内的传播公式；
- 取消接口降阶可以恢复 Full3D，但不能由此宣称低维 modal Hybrid 已经修好。

### 2.2 M120 应保留为 core，而不是继续扩张为全局 port

当前证据支持：

```text
M120 long-range core            = retain
M120 endpoint joint-Cauchy port = insufficient
M240/M480/M492 heavy PDE sweep  = closed
```

因此后续候选不能再要求同一组 physical-QEP modes 同时承担长程传播与端部 evanescent、
boundary-layer 和 traction 信息。新增空间必须针对端部缺失的 joint-Cauchy 方向，并且保持
局部、可释放和可审计。

### 2.3 低秩容量审计值得做，但只值得做成有界决策实验

本回复同意利用 exact trace-chain 计算：

- joint electric/traction Cauchy best approximation；
- projected exact-operator action error；
- frozen channel/goal replay error；
- Gram、inf-sup、Floquet orientation 和 near-degenerate identity；
- 候选的 resident bytes、action wall、rows、NNZ 和峰值上界。

这些数据能回答 direct Hybrid 是否仍具有真正低秩接口，而不必先开发新的 forward solver。

---

## 3. P0：localized-buffer 必须先关闭代数等价风险

### 3.1 为什么“局部凝聚”本身不能修复物理

把 exact endcap/buffer 的未知量分为 core-facing 坐标 `a` 与内部坐标 `c`：

$$
\begin{bmatrix}
K_{aa} & K_{ac} \\
K_{ca} & K_{cc}
\end{bmatrix}
\begin{bmatrix}
a \\
c
\end{bmatrix}
=
\begin{bmatrix}
f_a \\
f_c
\end{bmatrix}.
$$

精确消去 `c` 后：

$$
K_{\mathrm{eff}}
=K_{aa}-K_{ac}K_{cc}^{-1}K_{ca}.
$$

如果：

1. buffer 几何、离散和边界条件不变；
2. core-facing retained coordinates 仍是与历史 `30/90` 或 `40/80` 完全相同的 M120；
3. Schur 消元是精确的；

那么“把 buffer 未知量留在全局系统”与“先在局部组件中精确消元”在代数上等价。后者可以
降低全局 rows 和生命周期峰值，却不能把历史 `79/96` 自动变成 `96/96`。

因此 V6 第 4.1 节中的：

```text
exact buffer
→ local condensation
→ original M120 core-facing port
```

不能单独作为物理修复理由。

### 3.2 合格候选必须显式包含新的端部补空间

候选 port 应写成：

$$
R_{\mathrm{port}}
=\left[R_{\mathrm{core}},R_{\mathrm{corr}}\right],
$$

其中：

- `R_core` 是已资格化的 M120 长程 core；
- `R_corr` 是 `r` 个新的 Cauchy-complete 端部方向；
- `R_corr` 可以只在短 buffer 内传播或被局部消元；
- 但它必须在 external-to-core effective operator 中留下可测的非零修正；
- 不得在到达原 M120 core-facing port 前完全消失后仍宣称修复。

即使 `R_corr` 最终被局部 Schur 消去，也必须报告：

$$
\Delta K_{\mathrm{corr}}
=K_{\mathrm{candidate}}-K_{\mathrm{old\ M120}}.
$$

### 3.3 强制 anti-equivalence Gate

V6 后续实施必须恢复 V5 的 anti-equivalence 思想，至少证明：

| Gate | 必须报告 |
|---|---|
| candidate 与 old `30/90 M120` action 差 | metric-whitened probe 上的相对差与数值不确定度 |
| candidate 与 old `40/80 M120` action 差 | 同上 |
| corrector 的有效修正 | `ΔK_corr` action norm，不得落入 estimator/solve noise |
| candidate exact-action error | 必须严格小于两个历史负对照 |
| candidate joint-Cauchy error | 必须严格小于两个历史负对照 |
| full-trace limit | 明确 candidate 增秩后趋向哪个 exact operator |

若 candidate 只是在存储上更小、数值上复现历史 shifted-interface M120，则分类为：

```text
LOCAL_CONDENSATION_RESOURCE_REWRITE_ONLY
physics_credit = none
actual_PDE = not_authorized
```

---

## 4. P0：统一 rank 与成本口径

Review V6 的 `120/240/360/480` 与“per directional pair”存在歧义。后续不得再用
“rank 120”同时表示单方向模式数和双向 trace columns。所有表必须同时报告：

| 字段 | 定义 |
|---|---|
| `M_per_direction` | forward 或 backward 单方向模式数 |
| `d_core_primal_per_side` | core 每侧总 primal columns；当前 M120 为 `240` |
| `r_corrector_primal_per_side` | 每侧经 Cauchy-metric 正交化后、不在 core span 内的新增 corrector columns |
| `d_port_primal_per_side` | actual candidate 的唯一 primal columns；当前必须等于 `240 + r_corrector_primal_per_side` |
| `d_left_test_per_side` | left/Petrov columns，不得与 primal 重复计入未知量 |
| `global_retained_rows` | actual global system 中真正保留的 rows |
| `resident_dense_bytes` | 同时常驻的 dense basis/operator bytes |
| `transient_dense_bytes` | 有界 materialization 阶段临时 bytes |

同 rank 比较统一使用 `d_port_primal_per_side`，不得把 B0 的单方向 `M` 与 B1 的双向
或 joint-Cauchy 总列数直接比较。`R_corr` 在计数前必须从 `R_core` 的
Cauchy-metric span 中投影出去；否则重复列不能冒充新容量。

首轮冻结：

```text
d_core_primal_per_side = 240
r_corrector_primal_per_side = 0, 40, 80, 120
d_port_primal_per_side = 240, 280, 320, 360
d_port > 360 = not_run_in_current_batch
```

当前 physical-QEP M120 的正式 baseline 对应：

```text
M_per_direction       = 120
d_core_primal_per_side = 240
d_port_primal_per_side = 240
```

因此 V6 中单列的 `rank=120` 不再作为 actual candidate：在上述统一口径下，它必须
删掉一半已资格化的双向 M120 core，比已知的负对照更弱，且不再是本文批准的
`M120+r` 架构。

---

## 5. 修订后的执行阶段

### Stage R0：clean-source exact-oracle 最小复现

#### 范围

只运行：

```text
A007-P p5/h10/Ny4/MPI8 exact FE trace-chain direct
```

暂不运行：

```text
A004-S clean rerun
p6/h10 exact trace-chain
full repository pytest
```

原因：当前代码仍大量绑定 p5 的 `1250/1200` trace identity 和固定 10-cell chain。p6 需要
真正的动态 trace-dimension 泛化，不能作为“冻结 oracle 后的简单重跑”。

#### R0 Gate

- clean committed source；
- qualified PETSc `complex128/int32`；
- fixed BLAS/OpenMP threads、CPU affinity 和 MPI rank identity；
- 80/80 fixed channels；
- exact Full3D same-source observable comparison；
- true residual、R/T/A、joint-Cauchy、DtN、Floquet 和 projection Gate 全部通过；
- simultaneous process-tree peak、external wall 和 zero swap；
- targeted serial/MPI tests、Ruff、compileall 和 `git diff --check`。

R0 失败时只修 source/runtime identity 或与复现直接相关的 bug，不进入容量研究。

### Stage R1：B0/B1/B∞ 离线容量审计

#### 唯一允许的 basis

```text
B0(r) = physical-QEP expansion with the same total dimension 240+r
B1(r) = M120 core plus r Cauchy-metric-orthogonal residual directions selected from
        full-interface discrete Bloch modes of the same one-cell FE/Schur discretization
B∞ = full 1200-dimensional exact FE trace oracle
```

本阶段不实现 RCWA、POD、HSS、HODLR、H-matrix 或 actual forward solver。

#### 为什么 B1 优先

B1 与老师算子共享：

- 同一 3D Nédélec 离散；
- 同一 p/h、Floquet constraint 和 orientation；
- 同一 one-cell Schur action；
- 同一 joint electric/traction Cauchy metric；
- 同一 lossy/non-Hermitian left/right convention。

因此它是新映射最少、最能直接检验“physical-QEP basis 选择错误还是接口本身不可低秩”的
候选。

#### R1 rank 顺序与早停

```text
1. r = 0，d_port = 240：已知 M120 基线
2. r = 40/80/120，d_port = 280/320/360：在同一次 B0/B1 action 与谱分解上读取前缀
3. 每个总维数必须比较 B0(r) 与 B1(r)，不允许只报最优方案
4. d_port > 360 本批不运行
```

这不是四次 forward PDE：B0 与 B1 各自只构造一次最大 360 维的离线 action/basis，
`40/80/120` 是同一结果的冻结前缀检查点。不得为每个 rank 复制 runner或重做
Full3D/exact-trace-chain solve。

若 `d_port=360` 时：

- singular tail 没有明确下降趋势；或
- joint-Cauchy/operator error 仍比 Gate 高多个数量级；或
- 预测达到 Gate 所需 rank 接近完整 trace；

则立即记录：

```text
LOW_RANK_INTERFACE_COMPRESSION_NOT_DEMONSTRATED_AT_13P5NM
```

随后停止，不运行更高 rank，不切换 B2/B3。

#### R1 防止验证泄漏

本批 B0/B1 必须只由 one-cell FE/QEP/Schur operator 构造，不允许吸收 Full3D 或
exact-trace-chain solution snapshot。因此不建设训练数据集，只冻结两类评价身份：

- `capacity audit set`：用于 joint-Cauchy/operator 容量度量与选择首个通过的冻结 rank；
- `holdout observable set`：不得参与 basis 或 rank 选择，只用于最终 replay 判定。

POD 或目标相关数据即使未来获批，也不得使用同一 Full3D solution snapshot 训练后再把它作为
通过证据。

#### R1 数值 Gate

至少同时满足：

```text
joint-Cauchy max relative residual <= 1e-8
projected exact-operator action error <= 1e-8
all frozen holdout channel/goal replay = pass
Gram / inf-sup / orientation / near-degenerate identity = pass
anti-equivalence vs old 30/90 and 40/80 = pass
```

若 reachable-source 与 worst-case full-space metric 使用不同 Gate，必须并列表述，不得把
reachable-manifold pass 写成任意 1200 维 Cauchy source 的 uniform pass。

#### R1 资源 Gate

资源预测必须由当前 H5-K1/H5-M1 同源码实测对象生命周期校准，并给出中心值和不确定性。
授权 actual implementation 的条件为：

```text
predicted_peak_center + prediction_uncertainty
    <= 0.70 * same-input Full3D measured peak

no resident global 1200 x 1200 square
no global 11 x 1200 trace unknowns
zero-swap design
external wall model <= Full3D measured wall
```

不能只用 rows 或 NNZ 比例推断 peak pass。

### Stage R2：只实现一个 M120+r localized candidate

R1 通过后，只实现 B1 的首次通过 rank，不同时保留多个 candidate。

候选必须满足：

```text
exact boundary-layer response
+ r-dimensional Cauchy-complete endpoint corrector
+ M120 long-range core
```

实现边界：

- full 1200-dimensional planes只允许在 local action/materialization 内短暂存在；
- global unknowns不得包含11个完整trace planes；
- 不形成长期常驻的global `1200 x 1200` blocks；
- bottom/top local factors按顺序或固定分组处理，使用后立即释放；
- corrector可以局部消元，但必须通过第3节的 `ΔK_corr` 和 anti-equivalence Gate；
- global system必须明显小于Full3D，并绑定同一 source identity；
- 不新增自动basis选择器、campaign、state machine、retry或fallback。

若实际实现预计需要：

```text
新增大型数值framework
或
同时修改超过3个核心架构层
或
在未形成首个action fixture前新增超过约500行非测试代码
```

则停止并返回 review，不继续向外扩展。

### Stage R3：actual direct anchor

第一点只运行：

```text
A004-S
p5/h10/Ny4
0.5° grazing / 45° azimuth / S
MPI8
direct only
```

Gate 保持 V6 的严格要求：

```text
96/96 channels
abs(R+T+A_volume-1) <= 1e-5
max abs(Delta R/T/A_volume vs Full3D) <= 1e-4
true residual <= 1e-9
joint-Cauchy / Petrov / DtN / Floquet = pass
zero swap
whole-job measured peak <= 0.70 * Full3D
external wall <= Full3D
```

通过后才运行 A007-P 作为 P 偏振确认。失败则保留 artifact并停止，不调 rank、不换 basis、
不放宽 Gate。

### Stage R4：后续项目，不属于当前批准批次

以下全部保持未授权：

```text
p6 dynamic trace generalization
RCWA-FE coupling
transfer/POD production basis
HSS/HODLR/H-matrix framework
FGMRES / iterative / PC
h/p adaptivity
wavelength continuation
broad angle scan
surrogate / inversion
```

只有 p5 的 A004-S 和 A007-P 均通过后，才由下一轮 review 决定 p6 与网格缩放研究。

---

## 6. RCWA 的单独处置

Review V6 引用的 RCWA 三波长结果当前未在 Task036 分支中绑定：

- report path；
- code/source SHA；
- input geometry/material hash；
- raw channel amplitudes；
- process-tree memory口径。

因此 RCWA 目前只获得 `promising_external_signal`，不获得 B2 capacity authority。

若未来提供完整可审计入口，应先做一个独立 solver 对照：

```text
same A004-S or A007-P input
→ stable S-matrix RCWA
→ complete diffraction complex amplitudes
→ joint E/H trace
→ Full3D / exact trace-chain comparison
```

只有独立 RCWA 本身通过完整合同后，才决定：

1. 直接将 RCWA 用作规则几何的 production/reference solver；或
2. 继续研究 FEM--RCWA port coupling。

不得为了统一 Hybrid 形式，先开发接口耦合再证明 RCWA 自身正确。

---

## 7. 代码规模与“不过度防御”合同

本轮执行必须保持：

- 不新增 package、campaign、dataset schema、receipt、scheduler 或状态机；
- 不新增自动 rank tuner；
- 不增加多套 solver retry/fallback；
- 不捕获数值异常后静默换 basis；
- 不为每个角度、偏振或 rank复制 runner；
- 不把 capacity analyzer扩展成新的forward solver；
- 不修改 ordinary default；
- 不重构与 B0/B1 action无关的六千行综合 runner；
- 失败证据原样保留，不用更宽 Gate改写为通过。

允许：

- 一个职责单一的离线 B0/B1 analyzer；
- 必要的 discrete Bloch trace mapping；
- 小型 exact-action、orientation、dual-pairing和anti-equivalence fixture；
- compact JSON/CSV/Markdown evidence；
- R1通过后一个职责单一的production-candidate module。

---

## 8. 批准矩阵

| 阶段或工作 | 当前决定 | 解锁条件 |
|---|---|---|
| R0 clean A007-P | 批准 | 当前即可执行 |
| R1 B0/B1/B∞ offline | 条件批准 | R0 pass |
| R1 `r=40/80/120` 离线前缀审计 | 条件批准 | R0 pass；只构造一次最大 basis/action |
| `d_port>360` | 不批准 | 下一轮 review |
| R2一个 localized candidate | 锁定 | R1全部数值、anti-equivalence和资源Gate pass |
| R3 A004-S actual | 锁定 | R2 fixtures和preflight pass |
| A007-P confirmation | 锁定 | A004-S全部Gate pass |
| p6/h10 exact trace | 不批准本批 | p5两个anchor通过并完成新review |
| RCWA独立复核 | 暂缓 | 提供可审计report/code/raw入口 |
| RCWA-FE coupling | 不批准本批 | RCWA独立完整合同pass和新review |
| transfer/POD | 不批准本批 | B1 controlled negative后新review |
| HSS/HODLR/H-matrix | 不批准本批 | 先有实际block-rank谱证据 |
| iterative/FGMRES/PC | 不批准 | 用户另行授权 |
| broad scan | 不批准 | 两个direct anchor通过并由新review授权 |
| master merge | 不批准 | 最终选择性合并审查和用户授权 |

---

## 9. 交付和停止语义

R0/R1 每一阶段都必须在同一 `response_v6.md` 中追加：

- source SHA 和 normalized source identity；
- 实际运行/未运行列表；
- rank 的完整口径；
- 数值 Gate 原值；
- resource measured/predicted身份；
- negative和early-stop原因；
- 修改文件与代码规模；
- tests与工作树状态。

R1 若失败，最终状态为：

```text
exact_trace_chain_oracle = qualified
low_rank_direct_Hybrid   = not_demonstrated
actual_reduced_PDE       = not_run_by_capacity_gate
```

这不是“工作白做了”，而是以较低成本确定 direct 接口压缩在当前13.5 nm离散下没有足够空间。

R3 若通过，才能写：

```text
compressed direct Hybrid = p5 anchor pass
```

不得外推为 p6、0.7 nm、2 TB 或 iterative production pass。

---

## 10. 最终回复决定

```text
Review V6 strategic direction          = accepted
Review V6 execution plan as written    = not accepted wholesale
localized buffer with unchanged M120   = algebraic-equivalence risk / must revise
first capacity family                  = B0 + B1 + B∞ only
normalized offline dimensions          = 240 / 280 / 320 / 360
fixed core / corrector checkpoints      = 240 + 0 / 40 / 80 / 120
first clean PDE                        = A007-P p5/h10 only
first actual reduced PDE               = A004-S p5/h10 only
RCWA / POD / H-matrix / p6 / iterative = deferred
master merge                           = not authorized
```

最值得做的是一个严格有界的 discrete-Bloch 低秩容量判定，而不是一次性建设四条 basis 路线。
只有候选在远低于完整1200维时同时通过 joint-Cauchy、operator、holdout observable、
anti-equivalence和峰值上界，才值得继续开发 actual direct Hybrid。

---

## 11. 对 Review V6 第11节的最终执行澄清

```text
reviewed_supplement_commit = 0379aab1749db93bde6cbb5ba9a89f4586c65a17
supplement_disposition     = ACCEPTED_WITH_TWO_BINDING_CLARIFICATIONS
current_execution_scope   = R0 + R1 only
R2_R3                      = locked_until_response_v6_supervisory_review
```

Review V6 第11节没有否定本回复的核心纠偏。以下修订全部接受并纳入执行：

- A004 旧老师解只能在 numerical-kernel 和 artifact identity 全等时复用；
- `uniform_full_trace_diagnostic` 与 `reachable_physics_gate` 分开报告；
- holdout observable 必须由独立 reduced solve 得到，不允许用老师解投影冒充；
- reciprocal 和 near-degenerate block 必须整块保留；
- `ΔK_corr` 非零只是必要条件，候选还必须在 exact action、joint-Cauchy 和
  independent holdout 上严格优于旧负对照；
- RCWA、POD、p6 和 iterative 本批延期，但不做永久路线否定。

仅有以下两点必须作为 binding clarification，防止执行时改变用户的原始成功定义。

### 11.1 数学通过不等于 Hybrid 工程目标完成

Review 第11.7节的资源分层可用，但状态必须严格分开：

```text
physics_compression_pass
    = 只证明冻结物理流形可低秩表示

0.70 < predicted_peak_upper / Full3D <= 0.80
    = mathematical_positive_but_engineering_review_only
    = actual_not_authorized

predicted_peak_upper / Full3D > 0.80
    = no_meaningful_direct_Hybrid_advantage_in_this_batch
```

`0.70--0.80` 区间不应被写成数学失败，但也不得写成“Hybrid 已修复”、
`engineering pass` 或用它自动进入 actual PDE。

Review 第11.8节要求报告 cold/warm 四类时间口径是正确的，但对本批的单点
direct anchor，原 V6-3 的：

```text
whole-job external wall <= same-input Full3D external wall
```

仍是工程通过条件。cold setup 较慢不否定数学等价性，但会使本批“内存和耗时都优于
Full3D”的整体工程目标不通过。`warm_repeated_solve_wall` 可作为后续多 RHS/扫描服务的
独立资格，不能在当前单点报告中替代 whole-job cold wall。

### 11.2 代码行数不是数值 Gate，但仍是强制复审触发器

Review 第11.9节正确指出：代码行数不能代替物理正确性。但 `task.md` 第3.3节仍有明确治理
约束。因此统一解释为：

```text
about 500 new non-test lines before the first qualified action fixture
    != automatic numerical failure
    == mandatory stop-and-review trigger
```

到达该触发器时，必须报告文件、职责、行数、为何现有组件不足，并停止继续扩展。
它不等于路线永久失败，但不得因“算法完整性”而静默超过。同时仍必须满足 scope-based 约束：

- 不新增 generic framework、campaign、scheduler、fallback 或自动调参；
- 不同时重写 mode generation、coupling 和 global solver 三层；
- 不为 rank、角度、偏振或 RHS 复制 runner；
- 每个新模块职责单一，失败不自动换 basis 或放宽 Gate。

### 11.3 当前批次的最终放行边界

```text
R0 clean A007 exact-oracle reproduction                 = authorized
A004 frozen authority kernel/artifact identity audit    = authorized
conditional clean A004 rerun on identity mismatch       = authorized
R1 B0/B1/B∞ bounded offline capacity                     = authorized
R2 localized candidate                                  = locked
R3 actual A004/A007                                     = locked
RCWA / POD / p6 / iterative                             = not authorized
```

R1 还必须满足以下效率边界：

- `requested_dimension` 可因 reciprocal/near-degenerate block closure 向上取整，但
  `effective_block_closed_dimension` 仍不得超过 `360`；
- external incoming channels、parameter-tangent loads 和 holdout RHS 必须在同一已建立的
  exact/reduced operator 上批量求解，不得转化成数百次 Full3D、exact-trace 或 Hybrid PDE；
- B0/B1 各只构造一次最大 effective basis/action，rank 只读取冻结前缀；
- R1 结束必须提交 `response_v6.md` 并停止，由监督审阅决定是否解锁唯一 R2
  candidate，不再向用户反复请示。

因此，对当前问题的最终答复是：**R0/R1 可以立即执行；R2/R3 不可以提前开始。**
