# Task036 Review Report V5：exact Cauchy 审计与 transfer-optimal port 闭合路线

## 1. 审阅身份与最终决定

```text
review = Task036 Review V5（原文件原位更新，不新建版本）
branch = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head = 7ea6c043dd32732f675a60da36fba31862639e15
reviewed_response = response_v5.md，含第13节最新审计
reviewed_audit = outcomes/exact_cauchy_port_operator_audit.md
audit_disposition = APPROVED_WITH_CRITICAL_ARCHITECTURE_QUALIFICATIONS
ordinary_default = unchanged
master_merge = not_authorized
Hybrid_production = fail_closed
current_M120_core_operator = qualified_inside_selected_space
endpoint_joint_Cauchy_port_space = incomplete
transfer_optimal_family = approved_for_capacity_audit_only
actual_transfer_candidate = not_authorized_before_capacity_gate
unrelated_research = paused
final_response_document = response_v5.md继续原位维护
```

最新审计是有效且有价值的。它进一步排除了三个此前可能继续浪费时间的方向：

1. 当前 M120 selected space 内的 scalar-CG 中间传播算子不是主要错误；
2. right/left port pair 没有发生物理退化；
3. 16 个持续失败通道并不由两三个共同 output-adjoint 方向支配。

审计把剩余问题收缩为：

> 当前 physical-QEP M120 空间对端部完整 Maxwell Cauchy 数据，尤其离散
> magnetic/traction trace，表示不足；只检查切向电场会显著低估这个缺口。

因此批准把下一候选 family 冻结为：

```text
transfer_optimal_port_modes
```

但这里只批准**容量与低秩可行性审计**，不批准立即搭建正式 transfer solver。最新数据尚未
证明该 family 具有足够快的奇异值衰减，也没有证明它能以低资源修复 96 个通道。

---

## 2. 最新审计的量化结论

### 2.1 当前 M120 core operator 已经闭合

| middle length | exact FE selected operator vs current modal operator |
|---:|---:|
| 40 nm | `1.593747e-11` |
| 60 nm | `1.749079e-11` |
| 100 nm | `1.951491e-11` |

star-product solve 的最大相对残差不高于 `1.76e-16`。这说明在当前 selected M120
right/left space 内，真实 one-cell FE port action 与现有 scalar-CG modal action 已一致到
约 `2e-11`。

正式决定：

```text
modify_scalar_CG_core_propagation = forbidden_without_new_evidence
implement_dense_M120_matrix_propagation = forbidden
resume_M240_M480_M492 = forbidden
```

### 2.2 缺口位于 joint Cauchy port space

| best approximation | aggregate relative | max cell relative |
|---|---:|---:|
| tangential electric | `1.099844e-6` | `2.072564e-6` |
| magnetic/traction | `2.364065e-5` | `4.609620e-5` |
| joint Cauchy | `1.677328e-5` | `3.214277e-5` |

traction aggregate residual 约为 electric residual 的 `21.5` 倍。端部 cell 的 joint residual
分别为：

```text
10–20 nm   = 1.477075e-5
100–110 nm = 3.214277e-5
```

中心 cell 已下降到约 `1e-10`。因此：

```text
E-only port qualification = insufficient
endpoint joint trace/traction representation = current primary blocker
```

### 2.3 port pair 稳定，不是 Gram 退化

| 指标 | 数值 |
|---|---:|
| raw right self-Gram condition | `3.117939e4` |
| raw left self-Gram condition | `4.226209e4` |
| whitened pair condition | `1.00001975` |
| inf-sup smallest singular value | `0.99998025` |

raw condition 主要来自坐标尺度；白化后的 pairing 接近等距。不得继续通过修改
biorthogonal normalization、放宽 Gram Gate 或重新配对 mode 来追逐当前通道误差。

### 2.4 16 个失败通道不是低秩共同方向

| 指标 | 数值 |
|---|---:|
| first direction energy fraction | `6.3915%` |
| first two directions | `12.7827%` |
| rank for 90% | `15` |
| rank for 95% | `16` |
| rank for 99% | `16` |
| max local adjoint residual | `1.776730e-12` |

这足以否决“加两三个 failing-channel 专用模式”的方案。但这些是 local endcap adjoints 在
M120 Petrov 坐标中的方向审计，不是完整 coupled-Hybrid / Full3D output adjoint，因此不能
反向宣称生产 port basis 必须至少有 16 个新模式，也不能据此决定模式数。

局部 fixed-trace prediction 的向量相对误差为 `0.999467`，只获得方向结构 credit，不获得
逐通道定量预测 credit。

---

## 3. 对审计报告的认可与必要修正

### 3.1 认可：transfer-optimal family 是当前最合理的单一路线

transfer-operator port reduction 的基本思想是：由局部 PDE 的真实传递算子构造低维空间，
而不是继续按 `|beta|`、普通 E-trace 能量或手工通道挑模式。经典 component static
condensation 中，最优 port space 由 transfer operator 的奇异向量，或等价的
`T^*T` 特征问题得到。

本项目可借用这一构造思想，但必须保持一个重要边界：现有严格理论通常建立在椭圆/可控
局部问题上；当前频域、有损、非 Hermitian Maxwell 系统不能未经证明直接继承“指数收敛”
或严格 Kolmogorov 最优性。Task036 只能把它作为离散数值构造，并以实际 singular tail、
Cauchy residual 和 96-channel PDE 验证决定成败。

参考方法：

- K. Smetana and A. T. Patera, *Optimal Local Approximation Spaces for Component-Based
  Static Condensation Procedures*, SIAM J. Sci. Comput. 38 (2016), DOI `10.1137/15M1009603`；
- A. Buhr and K. Smetana, *Randomized Local Model Order Reduction*, SIAM J. Sci. Comput.
  40 (2018), DOI `10.1137/17M1138480`。

### 3.2 关键修正：不能只“压缩 40/80 的 full-3D buffers”

已有 actual 结果是：

```text
30/90 exact 3D endcaps + M120 core = 79/96
40/80 exact 3D endcaps + M120 core = 79/96
```

因此，若新的 transfer basis 只是近似原 `10→40` 与 `80→110` full-3D buffer，并在
`40/80` 仍连接到完全相同的 M120 core port space，那么其极限只能复现已经失败的
`40/80` 模型，不能合理期待自动达到 `96/96`。

正式要求：

> transfer corrector 必须改变或丰富 core-facing joint-Cauchy port space / effective port
> operator，而不能只把已经失败的 shifted-interface buffer 做低秩压缩。

这意味着 corrector 可以是局部的、最终被 Schur 凝聚，但它必须在 core-facing port
operator中留下可验证的修正；不得被强制在 `40/80` 处完全消失后仍声称可以修复余下通道。

### 3.3 joint Cauchy norm 必须改成离散算子一致的度量

本轮 joint fit 分别用全局 electric norm 和 traction norm做无量纲化，是合理诊断，但不能
直接成为 transfer eigenproblem 的 production inner product。

下一阶段必须明确：

```text
trial trace norm
adjoint/test trace norm
traction Riesz map
E/H单位与阻抗缩放
lossy/non-Hermitian adjoint convention
```

优先采用与 one-cell Schur / trace mass 一致的正定离散度量，并先在 homogeneous S/P
fixture中证明：

- 单位缩放不改变物理子空间；
- top/bottom orientation一致；
- right/left transfer pair可稳定白化；
- `D R-I`和Petrov flux合同仍闭合。

### 3.4 已撤销 diagnostic 必须永久撤销

`exact_cauchy.all_internal_conormal_cancellation_relative≈1.37` 来自左右端面不同
row numbering/orientation下的直接向量相加，没有物理意义。后续任何文档、Gate或模式选择
不得再引用该值；只能使用共同 Petrov 坐标重放的连续性结果。

同样，fixed-coordinate `0.949` test complement 依赖Euclidean坐标尺度，不得写成
“94.9%物理能量缺失”。

---

# 4. 下一步唯一主线：Transfer Capacity Gate（不运行 forward PDE）

## 4.1 执行边界

```text
new Full3D/Hybrid forward PDE           = forbidden in Stage T0
new campaign/state machine              = forbidden
interface scan                          = forbidden
M240/M480/M492 global PDE               = forbidden
strong-trace rewrite                    = forbidden
core propagation rewrite                = forbidden
failing-channel mode-by-mode enrichment = forbidden
iterative/hp/wavelength work            = paused
ordinary default                        = unchanged
master merge                            = not authorized
```

允许一个 task-local transfer-capacity driver 和一个 compact analyzer。不得复制现有
Full3D/Hybrid runner，也不得先搭完整 production framework。

## 4.2 T0a：先提交精确离散定义

在写数值实现前，Codex须在 outcome 中用不超过约两页写清：

1. buffer/component 的外边界、inner/core-facing port 和 oversampling区域；
2. source space包含哪些可实现的 Maxwell boundary data；
3. transfer map输出是 electric、traction还是joint-Cauchy harmonic state；
4. 使用什么正定、无量纲离散内积；
5. primal right modes与adjoint left/Petrov modes如何成对构造；
6. corrector如何局部存在并被Schur凝聚；
7. corrector如何在core-facing operator中留下修正，而不是退化为失败的40/80模型；
8. working-set复杂度和禁止的全局常驻对象。

建议的离散对象为 current M120 core 的 complement transfer：

```text
T_perp = (I - Pi_core^C) T_buffer
```

其中 `Pi_core^C` 是使用离散 joint-Cauchy/Schur度量定义的core投影。奇异向量只用于补充
M120遗漏的Cauchy方向，不能重新替换已经资格化的core传播。

## 4.3 T0b：冻结的capacity审计

复用现有 one-cell Schur与11-plane Full3D traces，完成以下离线结果：

### A. singular-value tail

分别对bottom/top transfer-complement报告：

```text
sigma_i
cumulative captured transfer energy
rank for tail <= 1e-6 / 1e-8 / 1e-10
left/right whitening and inf-sup
```

不能只在A004单个解向量上做POD后称为transfer-optimal；source space必须包含一组可实现
边界激励，或使用可审计的randomized range approximation与概率误差界。

### B. equal-dimension comparison

在同一资源维数下比较：

1. current physical-QEP M120；
2. 从candidate QEP family重新优化选择的相同维数space；
3. `M120 core + r` transfer correctors。

必须报告：

- 端点 electric / traction / joint-Cauchy residual；
- 11个平面的max与aggregate residual；
- exact FE port-action error；
- core-facing residual；
- transfer tail；
- Gram/inf-sup；
- mode localization/decay depth。

这一步要回答：问题是“模式数量不够”，还是“当前120维子空间选择不对”。

### C. shifted-interface dominance check

新的space必须证明它在相同或更低结构成本下，至少在离线Cauchy/operator指标上严格优于：

```text
30/90 actual architecture
40/80 actual architecture
```

若只能复现40/80的port space，不授权actual candidate。

### D. resource preflight

冻结一个由谱尾自动确定的rank，不允许actual后再调rank。必须满足：

```text
no global corrector amplitude spanning the whole 100 nm
no replicated full-interface square in production path
no resident N_trace x r block outside bounded assembly/streaming stage
assembled rows and matrix NNZ < I1 30/90 authority
predicted whole-job peak <= 0.85 * Full3D authority
zero-swap design
```

`I1 30/90`的authority为：

```text
rows       = 26,256
matrix NNZ = 16,512,096
peak       = 8.291 GiB
```

transfer candidate必须在保持原 `10/110` 3D endcaps的同时，结构上优于这个已知但物理失败的
厚endcap方案。

## 4.4 T0接受条件

只有同时满足以下条件，才允许进入actual implementation：

```text
transfer tail <= 1e-8 in frozen joint-Cauchy norm
frozen A004 exact joint-Cauchy max residual <= 1e-8
exact selected/core-facing port-action error <= 1e-8
D R-I / Petrov / orientation / Gram Gate pass
required rank fixed before PDE
resource preflight pass
architecture is not algebraically equivalent to failed 40/80 M120 model
```

若任一失败：

```text
TRANSFER_OPTIMAL_PORT_CAPACITY_FAIL
```

停止，不写正式transfer solver，不运行A004-S。下一次Review再决定full-interface discrete
Bloch port basis或更高层Hybrid分解，不能自动切换。

---

# 5. Stage T1：仅在T0通过后实现一个actual candidate

## 5.1 最小实现

允许新增一个职责单一的数值模块，复用：

- one-cell / multi-cell discrete Schur action；
- strong-trace trial/test装配；
- existing local static condensation；
- current M120 scalar-CG core；
- current R/T/A和96-channel postprocess。

不得新建campaign、状态机、receipt体系或另一套QEP solver。

right correctors和left/Petrov correctors必须由同一个transfer pair生成并完成白化。extra
corrector amplitudes必须局部凝聚，不能变成跨越整个100 nm的global M扩张。

## 5.2 exact fixture与preflight

actual PDE前必须通过：

```text
homogeneous S/P transfer round trip
lossy/non-Hermitian primal-adjoint pair
Floquet edge/face orientation
standard/static equivalence
joint-Cauchy projection
core-facing operator correction
no dense interface square
no global extra-mode replication
factor/memory preflight
```

## 5.3 唯一actual PDE

只运行：

```text
A004-S
p5/h10/Ny4
0.5° grazing / 45° azimuth / S
interfaces = 10/110 nm
core = M120
transfer-corrector rank = T0 frozen value
strong trace + static condensation
MPI8
```

不得先运行多个rank、多个buffer或多个阈值。

正式Gate：

```text
96/96 fixed channels                           pass
abs(R+T+A_volume-1)                           <= 1e-5
max abs(Delta R/T/A_volume vs Full3D)          <= 1e-4
reduced true residual                          <= 1e-9
strong trace / transfer identity               <= 1e-10
Petrov traction                                <= 1e-8
external DtN / noninterface residual           pass
zero swap                                      true
whole-job peak                                 <= 0.85 * Full3D peak
rows / NNZ / peak materially below I1 30/90
```

若通过：

```text
A004_TRANSFER_OPTIMAL_PORT_PASS
```

随后停止等待Review，不自动运行P偏振、p6、59-goal或参数扫描。

若失败：

```text
A004_TRANSFER_OPTIMAL_PORT_FAIL
```

保留全部artifact并停止。不得根据actual结果再改rank、阈值、权重或buffer后重跑。

---

# 6. 当前明确不做的工作

```text
Hybrid FGMRES / iterative
whole-domain Full3D iterative production study
local h/p endcap integration
wavelength continuation
P anchors
p6 / 59-goal
226-point scan
surrogate / inversion
RCWA
M sweep PDE
interface-position sweep
```

这些工作不被永久否定，但在A004 port-space闭合前均不应分散主线。

---

# 7. 交付要求

Stage T0结束后必须新增：

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/
  transfer_optimal_port_capacity_audit.md

benchmarks/cases/099_strong_trace_hybrid_fixture/records/
  a004_transfer_optimal_port_capacity_v1.json
```

并在原文件继续追加：

```text
docs/task036_forward_solver_bugfix_hardening/response_v5.md
```

若T0不通过，response必须明确写：

- 哪个transfer tail或resource Gate失败；
- 为什么没有实现solver；
- 为什么没有运行PDE。

若T0通过并完成T1，还需新增：

```text
outcomes/transfer_optimal_port_candidate.md
```

response必须逐项比较：

```text
Full3D
old 10/110 strong Hybrid
30/90
40/80
transfer-optimal 10/110
```

报告rows、NNZ、factor、RSS/PSS/USS、wall、R/T/A、96通道、joint-Cauchy、transfer tail和
所有Gate。

任务结束后提交、推送当前同名远程分支并停止。不得修改或合并master。
