# Hybrid 升级为 production 的代码与证据审阅报告

## 0. 报告身份

```text
document_status = architecture_and_production_readiness_assessment
task_branch = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_branch_head = e7f8bd1526b9434ff35b9c823a136fb7f6e4395d
new_PDE = not_run
numerical_source_modified = no
ordinary_default = unchanged
master_merge = not_authorized
```

本报告是 Task036 Review V4 结束后的架构审阅，不改写其正式数值结论。报告复核了
Task032、Task033、Task035c、Task035e 和 Task036 的主要结果链，以及 Hybrid 相关的
QEP、mode classification、传播、接口投影、strong trace、局部静态凝聚、直接
Modal-Schur 和场恢复实现。审阅覆盖约 1.1 万行 Hybrid 核心模块的结构、关键数据流和
显式可扩展性边界；它不是对全仓库所有无关模块的逐行代码证明。

本报告只使用已有源码、文档和 raw artifact。没有运行新的 Full3D 或 Hybrid PDE，也没有
把新的推断写成 measured solver pass。

## 1. 结论先行

```text
Hybrid as the 0.7 nm main route = necessary_and_credible
current direct Hybrid = research/reference implementation
Hybrid production candidate today = none
strong trace algebra = retain
scalar-CG diagonal propagation = retain
fixed 10/110 nm interface placement = reopen
replicated M^2 / all-mode RHS / local LU = must_remove
2.5D production assumption = forbidden
```

在未来真正三维结构和 `0.7 nm` 波长下，全域均匀 Full3D 不是现实主线。Hybrid 必须保留，
但不能靠继续优化当前 direct runner 或把 `M120` 固定到所有波长来完成。当前证据把问题
清楚地分成两层：

1. **当前尺度的物理闭合问题**：M120 physical QEP space 在固定 `z=10/110 nm`
   接口处不能完整表示 Full3D 端点近场；这不是 strong-trace 消元错误，也没有证据证明
   是显著模式之间的轴向 mixing。
2. **目标尺度的复杂度问题**：当前 all-mode MUMPS QEP、复制的 modal square、全量
   `N_local x M` multi-RHS 和 local MUMPS LU 在 `0.7 nm` 必然失控。

因此 production 路线应为：

```text
asymptotic interface placement / certified port space
→ strong-trace Hybrid direct physical closure at 13.5 nm
→ distributed and streamed generic modal core
→ matrix-free strong-trace Hybrid FGMRES
→ local 3D exact-sequence h/p and trace-aware preconditioning
→ 13.5 → 5 → 2 → 1 → 0.7 nm continuation
```

过去建议的 Full3D static-condensed iterative 不应成为最终产品路线；它仍有价值，但角色应
调整为：

- 小尺度数值 reference；
- 上下局部 3D endcap 迭代 kernel 的开发台；
- Hybrid block preconditioner 的可复用局部求解组件。

## 2. 当前证据给出的能力边界

| 能力或问题 | 当前证据 | 数据身份 | production 判定 | 主要证据 |
|---|---|---|---|---|
| Hybrid 域分解能真实减少代数规模 | p6/h10 static Hybrid M120 为 17,168 rows、12,313,232 matrix NNZ；Full3D static 为 51,272 rows、41,989,040 NNZ | measured, MPI8 | 架构正信号 | [Task035c summary](../../task035c_hybrid_channel_memory_closure/outcomes/summary.md) |
| 已资格化主点的通道闭合 | Task035c p6/h10 M120/M160 均为 12/12 power + 12/12 complex amplitude | measured | 证明方法不是概念性降维 | [Task035c summary](../../task035c_hybrid_channel_memory_closure/outcomes/summary.md) |
| strong trace 方程 | `D R-I`、trace identity、Petrov traction 和 reduced residual 均通过；接口跳跃降至 `4.588e-15` | measured | 保留为 production 离散基础 | [strong-trace result](strong_trace_hybrid_anchor_results.md) |
| strong trace 的物理闭合 | A004-S 仍只有 77/96 fixed channels，energy closure 为 `1.531666e-5` | measured negative | 不能单独提升为 production | [strong-trace result](strong_trace_hybrid_anchor_results.md) |
| scalar-CG 逐模态传播 | significant `rho=6.40e-11/6.51e-11`，projected offdiag 约 `3.3e-12` | measured audit | 保留；不得无证据改成 dense matrix propagation | [Response V4](../response_v4.md) |
| M120 endpoint trace space | bottom/top projection residual 为 `3.51e-6/5.22e-6`，高于 `1e-8` | measured negative | 当前固定接口不合格 | [Response V4](../response_v4.md) |
| 扩大 M 的 direct 路线 | A049-P M492 峰值 19.405 GiB，高于 Full3D 10.161 GiB，且接口误差形成平台 | measured controlled negative | 关闭 M240/M480/M492 direct 扩张 | [Hybrid validity map](hybrid_validity_map.md) |
| static Hybrid 内存 | p6/h10 M120 为 7.544 GiB，Full3D static 为 14.722 GiB | measured, same MPI8 campaign | 已有约 48.8% Full3D→Hybrid 降幅，但还不是 0.7 nm 架构 | [Task035c summary](../../task035c_hybrid_channel_memory_closure/outcomes/summary.md) |
| direct 实现的 0.7 nm 可扩展性 | current layout 最大单对象机械外推约 1,595.60 TiB | predicted stress projection, not RSS | 明确不可行 | [0.7 nm assessment](../../task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md) |
| automatic h/p | local-h/local-p component pass；blind automatic cycle incomplete | measured components + controlled negatives | 组件可复用，controller 不得直接生产化 | [Task035e review](../../task035e_reference_blind_multilevel_hp_adaptivity/review_report_v1.md) |

Task035c 的结果尤其重要：矩阵 rows 和 NNZ 已显著下降，说明 Hybrid 消元本身确有工程
价值。峰值没有同步按 NNZ 比例下降，是因为 local factors、QEP modes、field recovery、
middle reconstruction 和序列化对象仍在生命周期上重叠，不是因为降维没有意义。

## 3. Task036 exact trace 数据揭示的新优先级

Task036 raw authority：

```text
numerical_source_sha =
    c70ad32e3cb741f382e2cc901e056ae1ea0ba284
raw_artifact =
    benchmarks/artifacts/task036/
    c70ad32e3cb741f382e2cc901e056ae1ea0ba284/
    review_v4_one_cell/mpi8_m120_exact_oracle.json
raw_sha256 =
    021bc075adcc4acaa0f9202fe70fad1d9755113091dd8e74e0f141ed2bd89d09
```

同一 A004-S Full3D exact trace 在 11 个 z 平面投影进同一 M120 physical QEP space 后，
质量范数相对残差为：

| z 平面，nm | exact M120 trace projection residual | `1e-8` Gate | 数据身份 |
|---:|---:|---|---|
| 10 | `3.514657e-6` | fail | measured raw artifact |
| 20 | `9.780687e-8` | fail | measured raw artifact |
| 30 | `2.881134e-9` | pass | measured raw artifact |
| 40 | `8.852074e-11` | pass | measured raw artifact |
| 50 | `2.860216e-12` | pass | measured raw artifact |
| 60 | `7.992046e-13` | pass | measured raw artifact |
| 70 | `1.629599e-11` | pass | measured raw artifact |
| 80 | `3.717959e-10` | pass | measured raw artifact |
| 90 | `8.687626e-9` | pass | measured raw artifact |
| 100 | `2.089942e-7` | fail | measured raw artifact |
| 110 | `5.224931e-6` | fail | measured raw artifact |

这是当前最有判别力的机制信号。误差不是贯穿整个 modal middle，而是集中在离上下端部
最近的平面，向内部快速衰减。它支持以下解释：

> `z=10/110 nm` 接口离端部散射或边界层太近，M120 physical modes 被迫表示仍含明显
> evanescent boundary-layer content 的场。进入真正渐近的 z-invariant interior 后，同一
> M120 space 已满足 `1e-8` trace Gate。

因此，下一步最优先的不是：

- 增大 M；
- 修改 strong-trace 约束；
- 增加 penalty；
- 实现 dense projected propagation；
- 继续大范围参数扫描。

最优先的是**把接口位置和 local 3D buffer 厚度提升为数值选择量**。现有
[`hybrid_local_mesh.py`](../../../src/geometry/hybrid_local_mesh.py) 已接受显式
`bottom_interface_z_nm` 和 `top_interface_z_nm`；主要限制来自历史 runner Gate 把正式
Task035c/036 点冻结在 `10/110 nm`，不是 mesh core 完全无法表示其他接口。

`z=30/90 nm` 是已有 raw trace 支持的第一个对称、双侧都通过 `1e-8` 的候选，但这只是
**接口预选正信号**，不是 actual Hybrid pass。扩大 local endcaps 会增加局部 3D rows，
所以 production selector 应寻找“满足 trace margin 的最靠外接口”，而不是无边界地把
modal middle 缩短。

## 4. production 几何边界：统一按真正 3D 处理

本项目未来结构按真正三维问题规划。即使当前矩形 benchmark 看起来存在 y 方向对称，也
不得把 2.5D、单一 y-sector 或约 286 模的特殊估算作为 production 可行性依据。

正式边界为：

- 上下端部可以具有完整 `epsilon(x,y,z)` 变化，使用 3D Nédélec FEM；
- 中间只有在确实满足 `epsilon(x,y,z)=epsilon(x,y)` 的非零厚度区段内，才允许二维
  截面模式沿 z 传播；
- 截面 modal core 必须按 generic `epsilon(x,y)` 处理；
- 方位角、S/P、Floquet orientation 和非零 y diffraction orders 都保留；
- 若未来结构在整个 z 高度都没有任何 z-invariant interior，本 Hybrid 分解将失去可消元
  的 middle region，必须 fail closed，不能虚构资源优势。

0.7 nm generic 传播模式的解析下限约为：

$$
M_{\mathrm{prop}}
\approx
\frac{2\pi L_xL_y}{\lambda^2}
\approx
16{,}029
\quad \text{per direction}.
$$

这只是传播模式下限，尚未包含 evanescent buffer。机械沿用 13.5 nm 的 3.7 倍安全系数
得到 `M=59,306` 只用于暴露风险，不是推荐或收敛预测。

因此 production 目标不能是“0.7 nm 仍固定 M120”，而应是：

```text
M close to the physically required floor
+ certified evanescent buffer
+ memory and communication approximately linear in M
```

## 5. 为什么 current direct 架构不能机械放大

在 generic lower bound `M=16,029` 时，一个 complex128 `(2M) x (2M)` dense square
已经约为 `15.31 GiB`。四个这样的数组约为 `61.25 GiB`；如果在 48 个 rank 上复制，
仅这一类对象就约为 `2.87 TiB`，还没有包含 QEP eigenvectors、local FEM、Krylov vectors
或场恢复。

当前代码已经诚实标出这些边界：

- [`quadratic_beta_eigenproblem.py`](../../../src/modes/quadratic_beta_eigenproblem.py)
  使用 all-modes MUMPS shift-invert，只资格化当前尺度；
- [`hybrid_fem_modal_augmented_direct.py`](../../../src/solvers/hybrid_fem_modal_augmented_direct.py)
  把 modal rows 放在最后一个 rank；
- [`hybrid_fem_modal_schur_direct.py`](../../../src/solvers/hybrid_fem_modal_schur_direct.py)
  建立 replicated modal vector、local MUMPS LU 和 `[f,C]` 全量 dense multi-RHS；
- [`hybrid_field_reconstruction.py`](../../../src/postprocessing/hybrid_field_reconstruction.py)
  已限定为 selected-plane reconstruction，但 mode/plane 生命周期仍需进一步流式化。

production working-set 合同应改为：

$$
\mathcal{M}_{\mathrm{work}}
=
O(N_{\mathrm{end}})
+O(N_{\Gamma}b)
+O(Mb)
+O\!\left(n_{\mathrm{Krylov}}(N_{\mathrm{end}}+M)\right),
$$

其中 `b` 是固定或受预算约束的 mode block size，不能随 M 退化成 M。必须禁止：

$$
O(M^2 \times N_{\mathrm{rank}}),
\qquad
O(N_{\mathrm{local}}M),
\qquad
O(N_{xy}M)
$$

以全量常驻对象出现。

## 6. 建议的 production 数值架构

### 6.1 保留的数学基础

| 组件 | 决定 | 原因 |
|---|---|---|
| stable two-sided scattering propagation | 保留 | 避免 growing inverse，已有方向和被动性 Gate |
| scalar-CG discrete axial correction | 保留 | exact one-cell significant residual 与 offdiag 均通过 |
| strong trace relation `g_s = R_s L_s a` | 保留 | 真正删除自由 trace complement，代数和资源已通过 |
| Petrov left trace / flux rows | 保留 | traction residual 已通过 |
| assembly-time cell static condensation | 保留 | 高 p 时显著减少 active rows、matrix NNZ 和 factor inventory |
| full explicit true residual 与 official R/T/A | 保留 | production 最终可信度合同 |

### 6.2 必须替换的实现

| 当前实现 | production 替代 | 目标复杂度或资源行为 |
|---|---|---|
| all-modes MUMPS shift-invert QEP | distributed spectrum slicing、continuation 或 block eigensolve | 各 rank 只持有 mode slice；不形成单点 all-mode factor bottleneck |
| 完整 right/left eigenvector集常驻 | mode-block streaming、分布式持久化或可验证压缩 | working set 只含 `b` 个 modes |
| replicated global biorthogonal square | connected near-degenerate block normalization + distributed reductions | 不复制 global M² |
| last-rank modal ownership | contiguous distributed modal ownership | 负载和内存随 rank 分摊 |
| `[f,C]` all-mode dense multi-RHS | matrix-free `a → C a → local response → D u` action | 每次只作用一个 Krylov vector 或小 block |
| two local MUMPS LU | local 3D FGMRES / trace-aware H(curl) preconditioner | 不保留大 direct factors |
| explicit reduced dense Modal-Schur | PETSc shell/nest strong-trace operator | modal propagation维持 diagonal或小 connected blocks |
| factor、QEP、recovery、record 共驻 | sequential endcap lifecycle + streamed postprocess | peak 发生在唯一受控 solver stage |

### 6.3 推荐的全局迭代结构

全局未知量仍包含上下局部 3D retained trace/field 与双向 modal amplitudes，但不装配当前
direct monolithic factor。一个 matrix-free apply 应按以下顺序完成：

1. 对 modal amplitudes 以 block 方式执行 `R_sL_sa`；
2. 把接口 trace 作用到上下 local 3D operator；
3. 用 local H(curl)/trace-aware solver 或预条件器求局部响应；
4. 用 left Petrov trace 把局部 flux 投回 modal coordinates；
5. 加入 diagonal two-sided propagation 和 external DtN action；
6. 返回 strong-trace reduced residual。

外层使用 FGMRES。预条件器采用 block-triangular 或 approximate-Schur：

- 对角 local blocks：assembly-time static-condensed H(curl) multilevel、physical slab
  或 additive Schwarz；
- modal block：传播/阻抗对角项及 certified near-degenerate 小 block；
- interface correction：低精度 local trace response，不形成全量 `A^{-1}C`。

Task031 的 Full3D iterative 基础可以作为 local block 起点，但必须重新在 Hybrid endcap
上资格化，不能把历史 whole-domain profile 直接写成通过。

## 7. 接口与 port-space 的 production 选择规则

固定几何距离不是可靠 production 规则。接口选择至少需要以下四类证据：

| 指标 | 用途 | 建议 Gate | 失败动作 |
|---|---|---:|---|
| exact或可计算的 trace projection residual | 判断 physical modal space 能否表示接口场 | `<=1e-8`，并保留安全 margin | 扩大 local 3D buffer |
| evanescent tail / transfer singular-value tail | 判断被省略近场是否已衰减 | 与 59-goal tolerance 绑定 | 增加少量 evanescent modes或移动接口 |
| strong trace identity与Petrov flux residual | 判断离散耦合正确 | `<=1e-10 / <=1e-8` | 实现失败，停止 |
| actual 59-goal/channel closure | 判断误差是否影响服务输出 | 全部通过 | 不得用接口诊断替代物理 Gate |

在可运行 Full3D 的 13.5 nm qualification 阶段，接口可以由 exact Full3D trace 预选。进入
更短波长后，不能依赖 unavailable Full3D truth，必须由 transfer-eigenvalue tail、
双接口 buffer 加厚差和 goal-weighted port residual 提供在线/离线证书。

如果 `z=30/90 nm` actual Hybrid 仍失败，下一种且唯一值得进入的新 port 架构是：

```text
full-interface discrete Bloch modes
or
transfer-eigenmode optimal port basis
```

其作用是让 port basis 与实际 3D 离散 trace operator 一致。不得退回：

- 单 cell 或手选 face enrichment；
- projection-energy 排名；
- penalty；
- dense `R D` projector；
- 无证据增加 M。

## 8. local 3D endcap 与 h/p 的角色

0.7 nm 的主要体积未知量将集中在上下局部 3D endcaps。Task032 的 uniform
`h=0.1 nm`、总 local thickness 20 nm 机械估算约为 9.23 亿 rows，仍不可接受。生产路线
需要同时压缩：

1. **buffer thickness**：只保留让 evanescent endpoint content 衰减所需的最小 3D 厚度；
2. **exact-sequence local h/p**：材料界面、尖锐场梯度和端部区域细化，平滑体区降阶或粗化；
3. **cell-interior condensation**：高阶 cell modes 在装配时消去；
4. **matrix-free local solve**：禁止 local direct factor 成为峰值。

Task035d/e 已证明 true local-h、p4/p5/p6 inactive-mode elimination、periodic/hanging 和
static condensation 组件可以工作，但 Task035e automatic blind action predictor 已失败。
因此近期 production 开发应：

- 复用 exact-sequence active-space 和 constraint components；
- 先使用冻结、可审阅的 structured/directional local plans；
- 用 global post-action residual、port error 和 59-goal变化接受或拒绝；
- 不直接恢复现有 blind cellwise controller。

设计目标仍可沿用：

```text
preferred local active rows <= 2e8
candidate zone             = 2e8 to 3.5e8
effective memory           <= 2 kB per active local DoF preferred
effective memory           <= 3 kB per active local DoF hard exploratory ceiling
```

## 9. production 资格化阶梯

| 阶段 | 最小工作 | 进入条件 | 退出 Gate | 失败决策 |
|---|---|---|---|---|
| P0 接口闭合 | 复用 A004-S exact trace，预选 `z=30/90 nm`；运行一个 p5/h10 M120 strong-trace actual | 现有 Review V4 evidence | 96/96 channels、energy、residual、trace、zero swap；仍有资源优势 | 若失败，进入一种 optimal-port architecture，不扫阈值 |
| P1 参数锚点 | A004-S 通过后运行 A049-P、A001-P；再做 p6/h10 59-goal authority | P0 pass | S/P、低/高掠角、方位角 anchor 全通过 | 停止 broad scan，修同一根因 |
| P2 scalable modal core | distributed mode ownership、streaming、no replicated M²、no all-mode RHS | P1 direct physics pass | MPI identity、mode convergence、内存近似随 M/rank 分摊 | 不进入短波长 |
| P3 Hybrid iterative | matrix-free strong-trace operator + local trace-aware FGMRES | P2 pass | direct equivalence、59/59、全通道、true residual、warm/cold资源 | 迭代不收敛则修PC，不用 direct 冒充 |
| P4 h/p endcap | local exact-sequence h/p 与最小 buffer | P3 pass | same-error rows、NNZ proxy、whole-job memory符合预算 | 保留 controlled negative，重新选local space |
| P5 波长 continuation | `13.5→5→2→1→0.7 nm` | 前一波长全部 Gate pass | 每步材料、M、buffer、h/p、资源和59-goal更新 | 在当前波长 fail closed |

### 9.1 P0 的资源口径

移动接口会扩大 local 3D blocks，所以 P0 的第一目标是证明物理闭合，不应提前承诺 50%
内存下降。最低资源 Gate 可继续使用：

```text
whole-job Hybrid peak <= 0.85 * same-input Full3D peak
zero swap
```

P2/P3 完成 distributed/modal streaming 和 local iterative 后，再把 13.5 nm engineering
目标收紧为：

```text
whole-job Hybrid peak <= 0.50 * Full3D static peak
```

在 0.7 nm 不再以不可运行的 Full3D 峰值为分母，而使用：

```text
preferred whole-job peak <= 1.5 TiB
hard whole-job peak      <= 2.0 TiB
zero swap
```

## 10. production release contract

Hybrid 只有同时通过以下合同，才能从 `experimental` 提升为 production profile。

### 10.1 数值

- full explicit true residual `<=1e-9`；
- R00、R、T、Aclosure、Avolume 与 energy identity 全部通过；
- 冻结 59-goal inventory 全部通过；
- 所有 significant power 和 complex amplitude 通过；
- weak channel 使用冻结 absolute Gate，不得删除；
- periodic、Floquet、orientation、tag、ownership 和 hanging closure 通过；
- strong trace identity、Petrov traction、external DtN residual 分项通过；
- M、interface buffer 和 local h/p 均有独立收敛证据。

### 10.2 参数域

- height、width、grazing、azimuth、S/P 的代表性边界和内部点；
- Wood anomaly、near-degenerate、grazing 和 lossy material 单独列入 stress set；
- 自动 mode tracking 在参数 continuation 中保持 identity；
- 不允许用一个 nominal S point 外推整个 production 域；
- unsupported geometry 必须 fail closed。

### 10.3 资源和软件

- modal ownership 分布式；
- 禁止 replicated global M²；
- 禁止 all-mode dense multi-RHS；
- field recovery 和 postprocess 以 mode/plane block streaming；
- simultaneous process-tree RSS、PSS、USS、swap 和 native object lifecycle 完整；
- MPI count identity 与负载均衡通过；
- warm repeated solve 能复用合法 QEP/geometry/material cache；
- cache key 改变材料、波长、Bloch phase、mesh或ABI时必须失效；
- ordinary default 只在完整 qualification 后改变。

## 11. 明确关闭或暂不进入的路线

| 路线 | 决定 | 原因 |
|---|---|---|
| 2.5D / y-invariant production budget | forbidden | 未来按真正 3D 结构处理，不能依赖当前视觉对称 |
| M240/M480/M492 direct 漏斗 | closed controlled negative | 精度平台且内存超过 Full3D |
| dense projected/block propagation | not justified | exact one-cell audit没有证明 significant cross-mode mixing |
| 继续修改 strong-trace方程 | closed | 代数、trace和Petrov residual已通过 |
| penalty或全维Lagrange multiplier | forbidden | 掩盖trial/test space错误并破坏降维 |
| direct MUMPS微调作为0.7路线 | closed | 复杂度错误，不能靠生命周期小修复 |
| Task035e现有blind cellwise predictor | not production | single/four-cell actual与post-action audit均为负 |
| 先做226点扫描 | paused | anchor物理闭合前只会重复同一失败 |
| 0.7 nm固定M120 | physically invalid target | generic propagating mode floor已约16,029/方向 |

## 12. 对下一独立开发批次的建议

下一批次应只做一个明确主线：

```text
generic-3D Hybrid asymptotic-interface closure
```

建议顺序：

1. 不重跑 Full3D，离线消费现有 11-plane exact trace；
2. 冻结 `z=30/90 nm` 作为第一个 actual interface candidate；
3. 只做使 Task036 explicit gate 接受该接口的最小改动，ordinary default 保持
   `10/110 nm` 或现有默认不变；
4. 运行一个 p5/h10、M120、MPI8、strong-trace A004-S actual；
5. 若 96/96、energy、residual、trace 和资源全部通过，再运行 A049-P 和 A001-P；
6. 三个 anchor 通过后，用 p6/h10 59-goal direct authority关闭高阶资格；
7. 然后停止 direct 扫描，开始 distributed/streamed modal core 和 matrix-free Hybrid
   FGMRES。

如果 `z=30/90 nm` actual 仍不能闭合，禁止继续尝试多个接口、M或penalty组合；下一步只
能立项 full-interface discrete Bloch / transfer-eigenmode optimal port basis，并先以
exact trace fixture 证明它确实降低 endpoint projection residual。

## 13. 最终判断

Hybrid 目前不是“方法失败”，而是：

```text
domain-decomposition concept = validated
strong-trace algebra = validated
current significant-mode propagation = validated
fixed endpoint port-space placement = failed
current direct implementation scalability = failed
production architecture = incomplete
```

对 0.7 nm 真正三维结构，最现实的路线不是退回全域 Full3D，也不是要求 M 永远保持120，
而是让：

- 3D FEM 只覆盖不可模态化的端部和必要 evanescent buffer；
- generic modal middle 承担长 z 区域；
- port basis 在渐近接口上取得资格；
- modal core 与 M 近似线性扩展；
- local 3D blocks 使用 exact-sequence h/p、static condensation 和低存储迭代；
- 每个波长都由完整物理、数值和资源 Gate fail closed。

只有这五部分同时成立，Hybrid 才能真正从当前 research/reference implementation 提升为
面向反演服务的 production forward solver。
