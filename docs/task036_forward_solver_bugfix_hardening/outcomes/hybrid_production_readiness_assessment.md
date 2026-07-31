# Hybrid 升级为 production 的代码与证据审阅报告

## 0. 报告身份

```text
document_status = architecture_and_production_readiness_assessment
task_branch = codex/20260730-task36-forward-solver-bugfix-hardening
original_reviewed_branch_head = e7f8bd1526b9434ff35b9c823a136fb7f6e4395d
rectified_against_evidence_head = 7ea6c043dd32732f675a60da36fba31862639e15
latest_numerical_source = c8725e9eedc8a558719008f8762bc79eca48fbb7
new_PDE = not_run
numerical_source_modified = no
ordinary_default = unchanged
master_merge = not_authorized
```

本报告最初是 Task036 Review V4 结束后的架构审阅；现已根据 Review V5 的接口内移结果和
后续 exact Cauchy / port-operator / 16-channel sensitivity audit 完成必要整改。它不改写任何
正式数值结果，也不把离线审计写成 actual Hybrid candidate。报告复核了
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
selected M120 core operator = qualified_inside_selected_space
interface inward-movement lane = closed_controlled_negative
10/110 nm interface = target_to_restore_with_local_port_enrichment
endpoint joint Cauchy = incomplete
frozen next enrichment = transfer_optimal_port_modes
replicated M^2 / all-mode RHS / local LU = must_remove
2.5D production assumption = forbidden
```

在未来真正三维结构和 `0.7 nm` 波长下，全域均匀 Full3D 不是现实主线。Hybrid 必须保留，
但不能靠继续优化当前 direct runner 或把 `M120` 固定到所有波长来完成。当前证据把问题
清楚地分成两层：

1. **当前尺度的物理闭合问题**：M120 selected core 的 40/60/100 nm exact FE port action
   与当前 scalar-CG modal operator 一致到约 `2e-11`，但固定 `z=10/110 nm` 端部的
   joint electric/traction Cauchy space 不完整。把接口内移到 `30/90` 或 `40/80 nm` 虽改善
   energy 和中心场，仍只有 `79/96` fixed channels，因此继续移动接口已经关闭。
2. **目标尺度的复杂度问题**：当前 all-mode MUMPS QEP、复制的 modal square、全量
   `N_local x M` multi-RHS 和 local MUMPS LU 在 `0.7 nm` 必然失控。

因此 production 路线应为：

```text
exact joint-Cauchy fixture / transfer-optimal local port modes
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
| 接口内移 | 30/90 与 40/80 均为 79/96；energy 和中心场改善，但 16 个通道持续失败；40/80 峰值已达 Full3D 的 94.79% | measured controlled negative | 关闭继续移动接口 | [Response V5](../response_v5.md) |
| scalar-CG 逐模态传播 | 40/60/100 nm exact FE selected port operator 与当前 modal operator 相差 `1.59e-11–1.95e-11` | measured audit | 保留；selected M120 core 已资格化 | [exact Cauchy audit](exact_cauchy_port_operator_audit.md) |
| M120 endpoint joint-Cauchy space | electric aggregate residual `1.10e-6`，traction `2.36e-5`，joint `1.68e-5` | measured negative | E-only trace qualification 不足，需局部 port enrichment | [exact Cauchy audit](exact_cauchy_port_operator_audit.md) |
| right/left port pairing | whitened condition `1.00001975`，inf-sup 最小奇异值 `0.99998025` | measured pass | 不是 pairing 退化 | [exact Cauchy audit](exact_cauchy_port_operator_audit.md) |
| 16-channel sensitivity | 达到 95% 方向能量需要 16/16 个方向 | measured negative for low-rank hypothesis | 不选逐通道 adjoint-mode enrichment | [exact Cauchy audit](exact_cauchy_port_operator_audit.md) |
| 扩大 M 的 direct 路线 | A049-P M492 峰值 19.405 GiB，高于 Full3D 10.161 GiB，且接口误差形成平台 | measured controlled negative | 关闭 M240/M480/M492 direct 扩张 | [Hybrid validity map](hybrid_validity_map.md) |
| static Hybrid 内存 | p6/h10 M120 为 7.544 GiB，Full3D static 为 14.722 GiB | measured, same MPI8 campaign | 已有约 48.8% Full3D→Hybrid 降幅，但还不是 0.7 nm 架构 | [Task035c summary](../../task035c_hybrid_channel_memory_closure/outcomes/summary.md) |
| direct 实现的 0.7 nm 可扩展性 | current layout 最大单对象机械外推约 1,595.60 TiB | predicted stress projection, not RSS | 明确不可行 | [0.7 nm assessment](../../task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md) |
| automatic h/p | local-h/local-p component pass；blind automatic cycle incomplete | measured components + controlled negatives | 组件可复用，controller 不得直接生产化 | [Task035e review](../../task035e_reference_blind_multilevel_hp_adaptivity/review_report_v1.md) |

Task035c 的结果尤其重要：矩阵 rows 和 NNZ 已显著下降，说明 Hybrid 消元本身确有工程
价值。峰值没有同步按 NNZ 比例下降，是因为 local factors、QEP modes、field recovery、
middle reconstruction 和序列化对象仍在生命周期上重叠，不是因为降维没有意义。

## 3. Task036 trace、接口内移与 exact Cauchy 的完整证据链

### 3.1 E-trace 预选只是一项诊断

原 one-cell oracle source 为
`c70ad32e3cb741f382e2cc901e056ae1ea0ba284`。同一 A004-S Full3D exact tangential E
trace 在 11 个 z 平面投影进同一 M120 physical QEP space 后，质量范数相对残差为：

| z 平面，nm | exact M120 E-trace projection residual | `1e-8` diagnostic | 数据身份 |
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

这些值正确说明 electric near-field content 向中间快速衰减，但它们不能单独证明 actual
Maxwell port closure，因为完整接口状态还包含与 `n x H` 成比例的离散 weak conormal。

### 3.2 接口内移 actual 已关闭该路线

Review V5 随后实际运行了 `30/90` 和 `40/80 nm` 两个接口点：

| model | modal middle | fixed channels | energy closure | peak / Full3D | 判定 |
|---|---:|---:|---:|---:|---|
| old 10/110 | 100 nm | 77/96 | `1.531666e-5` | 74.82% | physics fail |
| I1 30/90 | 60 nm | 79/96 | `7.539015e-6` | 78.59% | physics fail, resource pass |
| I2 40/80 | 40 nm | 79/96 | `4.845332e-6` | 94.79% | physics and resource fail |

接口内移改善了 energy、R/T/A 总量和中心场，却没有消除 16 个持续失败通道；I2 的资源又
已经接近 Full3D。因此“继续移动接口直到通过”以及普通 E-trace evanescent buffer 均已作为
controlled negative 关闭。10/110 nm 仍是希望恢复的高压缩接口，而不是已资格化接口。

### 3.3 Exact Cauchy 把根因收窄到端部 joint port space

后续审计 numerical source 为
`c8725e9eedc8a558719008f8762bc79eca48fbb7`。它没有运行新的 forward PDE，而是用 frozen
Full3D traces 和 exact one-cell Schur action 分别拟合 electric、traction 和 joint Cauchy：

| best approximation | aggregate relative | max cell relative | 结论 |
|---|---:|---:|---|
| tangential electric | `1.099844e-6` | `2.072564e-6` | E-only 缺口存在但较小 |
| magnetic/traction | `2.364065e-5` | `4.609620e-5` | 主要端部缺口 |
| joint Cauchy | `1.677328e-5` | `3.214277e-5` | 当前 M120 port space 不完整 |

traction aggregate residual 是 electric 的约 21.5 倍。right/left port pair 白化后的 condition
为 `1.00001975`，inf-sup 最小奇异值为 `0.99998025`，所以根因不是 port pairing 退化。

### 3.4 M120 core propagation 已被 exact FE operator 对照保留

| middle length | exact FE selected port operator vs current modal operator |
|---:|---:|
| 40 nm | `1.593747e-11` |
| 60 nm | `1.749079e-11` |
| 100 nm | `1.951491e-11` |

这组对照推翻了“剩余误差可能主要来自 selected core propagation 累积”的暂定解释。当前
scalar-CG modal core 在 selected M120 space 内是正确的，不应改成 dense propagation。

16 个持续失败通道的 sensitivity 达到 95% 方向能量需要 16/16 个方向，因此也不应选择
逐通道 adjoint modes。下一步只冻结：

```text
transfer_optimal_port_modes
```

它应从两端短 buffer 的 exact discrete transfer operator 中提取最重要的 joint
trace/traction directions，corrector 只在端部局部存在并随后 Schur 凝聚；不得改变跨越完整
100 nm 的 M120 core，也不得同时实现其他 enrichment family。完整证据见
[`exact_cauchy_port_operator_audit.md`](exact_cauchy_port_operator_audit.md)。

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
| scalar-CG discrete axial correction | 保留 | 40/60/100 nm selected port action 与 exact FE 相差约 `2e-11` |
| strong trace relation `g_s = R_s L_s a` | 保留 | 真正删除自由 trace complement，代数和资源已通过 |
| Petrov left trace / flux rows | 保留离散形式 | 代数 residual 已通过；port basis 仍须补足 physical joint Cauchy，不得把两者混为一谈 |
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

固定几何距离和 E-only projection 都不是可靠 production 规则。port 选择至少需要以下四类
证据：

| 指标 | 用途 | 建议 Gate | 失败动作 |
|---|---|---:|---|
| exact或可计算的 joint E/traction Cauchy residual | 判断 port space 能否表示完整 Maxwell 接口状态 | 与冻结 channel/59-goal tolerance 绑定 | 增加 transfer-optimal local port modes |
| transfer singular-value tail 与结构成本 | 判断遗漏方向的重要性和压缩代价 | tail 与 memory budget 同时通过 | 停止或减小 local enrichment，不改 global M |
| strong trace identity与Petrov flux residual | 判断离散耦合正确 | `<=1e-10 / <=1e-8` | 实现失败，停止 |
| actual 59-goal/channel closure | 判断误差是否影响服务输出 | 全部通过 | 不得用接口诊断替代物理 Gate |

在可运行 Full3D 的 13.5 nm qualification 阶段，可以用 exact Full3D joint Cauchy data
资格化 transfer-optimal basis。进入更短波长后，不能依赖 unavailable Full3D truth，必须由
transfer singular-value tail、双 buffer enrichment 差和 goal-weighted port residual 提供
在线/离线证书。

`z=30/90 nm` 和 `z=40/80 nm` actual 已经失败。最新审计只冻结一种 port 架构：

```text
transfer_optimal_port_modes
```

其作用是用短端部 buffer 的 exact discrete transfer operator 补足 joint trace/traction
directions，同时保留 10/110 nm 接口和完整 100 nm M120 core。不得退回：

- 单 cell 或手选 face enrichment；
- projection-energy 排名；
- penalty；
- dense `R D` projector；
- failing-channel 专用 adjoint modes；
- 继续移动接口或普通 E-trace buffer；
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
| P0 optimal-port fixture | 从现有 exact short-buffer operator 提取一批 transfer-optimal joint-Cauchy modes；不运行 forward PDE | exact Cauchy audit complete | joint residual 显著下降、orientation/row-map正确、无 dense interface square、资源预估通过 | 停止该 direct enrichment，不扫模式数或公式 |
| P1 A004-S actual | 在 10/110 nm、完整 100 nm M120 core 上只运行一个 p5/h10 MPI8 candidate | P0 pass | 96/96 channels、energy、residual、trace、zero swap及资源 Gate全部通过 | 保留 raw negative并停止，不调阈值 |
| P2 参数锚点 | A004-S 通过后运行 A049-P、A001-P；再做 p6/h10 59-goal authority | P1 pass | S/P、低/高掠角、方位角 anchor 全通过 | 停止 broad scan，修同一根因 |
| P3 scalable modal core | distributed mode ownership、streaming、no replicated M²、no all-mode RHS | P2 direct physics pass | MPI identity、mode convergence、内存近似随 M/rank 分摊 | 不进入短波长 |
| P4 Hybrid iterative | matrix-free strong-trace operator + local trace-aware FGMRES | P3 pass | direct equivalence、59/59、全通道、true residual、warm/cold资源 | 迭代不收敛则修PC，不用 direct 冒充 |
| P5 h/p endcap | local exact-sequence h/p 与最小 buffer | P4 pass | same-error rows、NNZ proxy、whole-job memory符合预算 | 保留 controlled negative，重新选local space |
| P6 波长 continuation | `13.5→5→2→1→0.7 nm` | 前一波长全部 Gate pass | 每步材料、M、buffer、h/p、资源和59-goal更新 | 在当前波长 fail closed |

### 9.1 P1 actual 的资源口径

local transfer-optimal correctors 会增加少量端部状态，所以 P1 的第一目标是同时证明物理闭合
和仍有明确降维收益，不应在 fixture 前承诺 50% 内存下降。最低资源 Gate 可继续使用：

```text
whole-job Hybrid peak <= 0.85 * same-input Full3D peak
zero swap
```

P3/P4 完成 distributed/modal streaming 和 local iterative 后，再把 13.5 nm engineering
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
- M、transfer-optimal port basis、local buffer 和 local h/p 均有独立收敛证据。

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
| 继续把接口从30/90向内移动 | closed controlled negative | 40/80仍为79/96且峰值已达Full3D的94.79% |
| 普通 E-trace evanescent buffer | closed controlled negative | E-only诊断不能闭合joint Cauchy和16个通道 |
| dense projected/block propagation | not justified | exact one-cell audit没有证明 significant cross-mode mixing |
| 继续修改 strong-trace方程 | closed | 代数、trace和Petrov residual已通过 |
| failing-channel adjoint modes | not selected | 95% sensitivity energy需要16/16方向，缺少低秩收益 |
| penalty或全维Lagrange multiplier | forbidden | 掩盖trial/test space错误并破坏降维 |
| direct MUMPS微调作为0.7路线 | closed | 复杂度错误，不能靠生命周期小修复 |
| Task035e现有blind cellwise predictor | not production | single/four-cell actual与post-action audit均为负 |
| 先做226点扫描 | paused | anchor物理闭合前只会重复同一失败 |
| 0.7 nm固定M120 | physically invalid target | generic propagating mode floor已约16,029/方向 |

## 12. 对下一独立开发批次的建议

下一批次应只做一个明确主线：

```text
generic-3D Hybrid transfer-optimal joint-Cauchy port closure
```

建议顺序：

1. 不重跑 Full3D，复用现有 exact Cauchy traces、one-cell Schur blocks 和 16-channel
   sensitivity；
2. 从两端短 buffer 的 exact discrete transfer operator 提取一批
   `transfer_optimal_port_modes`，score 同时包含 joint trace/traction 误差和结构成本；
3. 先通过纯 fixture：joint-Cauchy residual 显著下降、right/left orientation 与 Floquet
   row-map一致、无 dense interface square、correctors 可在短 buffer 内局部 Schur 凝聚；
4. 只有 fixture 全部通过，才在 `10/110 nm` 接口和完整 100 nm M120 core 上运行一个
   p5/h10、MPI8、strong-trace A004-S actual；
5. 若 96/96、energy、residual、trace 和资源全部通过，再运行 A049-P 和 A001-P；
6. 三个 anchor 通过后，用 p6/h10 59-goal authority关闭高阶资格；
7. 然后停止 direct 扫描，开始 distributed/streamed modal core 和 matrix-free Hybrid
   FGMRES。

如果第 3 步 fixture 或第 4 步唯一 actual candidate 失败，保存 controlled negative 并停止
该 direct enrichment；不得继续改变模式数、阈值、接口位置、global M 或 ranking 公式。

## 13. 最终判断

Hybrid 目前不是“方法失败”，而是：

```text
domain-decomposition concept = validated
strong-trace algebra = validated
current significant-mode propagation = validated
fixed endpoint port-space placement = failed
interface inward-movement = closed controlled negative
endpoint joint Cauchy = incomplete
next frozen family = transfer_optimal_port_modes
current direct implementation scalability = failed
production architecture = incomplete
```

对 0.7 nm 真正三维结构，最现实的路线不是退回全域 Full3D，也不是要求 M 永远保持120，
而是让：

- 3D FEM 只覆盖不可模态化的端部和必要 evanescent buffer；
- generic modal middle 承担长 z 区域；
- port basis 通过 joint-Cauchy/transfer 证书，并用局部 correctors 恢复大 middle；
- modal core 与 M 近似线性扩展；
- local 3D blocks 使用 exact-sequence h/p、static condensation 和低存储迭代；
- 每个波长都由完整物理、数值和资源 Gate fail closed。

只有这五部分同时成立，Hybrid 才能真正从当前 research/reference implementation 提升为
面向反演服务的 production forward solver。
