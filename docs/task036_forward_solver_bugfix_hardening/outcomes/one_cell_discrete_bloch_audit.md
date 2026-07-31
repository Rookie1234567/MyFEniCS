# Task036 单 z-cell exact discrete Bloch 审计

## 1. 最终结论

```text
review = Task036 Review V4
phase_a = completed_fail_closed
phase_a_classification = D_OR_PHASE_A_INDETERMINATE
scalar_cg_significant_mode_audit = pass
broad_or_certified_block_mode_mixing = not_proven
current_M120_trace_space_exact_projection = fail
phase_b_projected_or_block_propagation = forbidden_not_implemented
production_solver_change = none
ordinary_default = unchanged
```

这轮要回答的问题很窄：把中间规则区域切出一个真实的 10 nm 三维
Nédélec 单元后，现有每个横截面模式各自独立传播的 scalar-CG 公式，是否会在离散单元
中产生足以解释 Hybrid 误差的模式互混。

答案是 **没有得到这种证据**。对 Full3D 实际场中有显著权重的模式，逐模态传播残差低于
`1e-10`；投影后四个 Schur 块的整体非对角残差约为 `3.3e-12`。唯一超过局部
`1e-8` 阈值的 connected component 只含非显著尾部模式，而且 exact Full3D 场没有给出
与它一致的物理误差方向。

真正失败的是更前面的基础条件：当前 M120 right/left trace space 对 exact Full3D
端点切向场的最大质量范数投影残差为 `5.224931e-6`，高于 Review V4 的 `1e-8`
Gate。换句话说，把现有 M120 基底内部的对角传播改成一个 `120 x 120` 矩阵，仍无法
补回不在该空间中的端点场成分。因此 Phase B 没有数学授权。

## 2. 数值与源码身份

| 项目 | authority |
|---|---|
| 分支 | `codex/20260730-task36-forward-solver-bugfix-hardening` |
| Phase A 起始 HEAD | `ec8d49f65d7094899ffdb3edb1f50ca2ce5c4005` |
| 正式数值源码 | `c70ad32e3cb741f382e2cc901e056ae1ea0ba284` |
| 环境 | WSL Ubuntu，qualified activation |
| PETSc | `complex128`, `int32` |
| 正式 MPI | MPI8 |
| one-cell | A004-S，p5，`(6,4,1)`，10 nm，stage4_xy |
| exact Full3D oracle | A004-S，p5/h10，实际 `(6,4,14)`，MPI8 |
| 模态 | M120，从 240 个 QEP candidates 中选择 |

正式 Phase A JSON：

```text
benchmarks/artifacts/task036/
  c70ad32e3cb741f382e2cc901e056ae1ea0ba284/
  review_v4_one_cell/mpi8_m120_exact_oracle.json
sha256 = 021bc075adcc4acaa0f9202fe70fad1d9755113091dd8e74e0f141ed2bd89d09
```

这是 ignored 本地数值 artifact；本文只记录相对路径、身份和哈希，不把大型场文件加入
Git。

## 3. 真实单元、静态凝聚与端口 Schur

静态凝聚先在每个三维单元内部消去只属于该单元的未知量，只留下可与相邻单元连接的
切向 trace。这样可以检查真实离散传播，又不需要建立 100 nm 的完整中间三维体网格。

| 指标 | 数值 |
|---|---:|
| 原始 H(curl) rows | 10,755 |
| cell-interior rows | 5,760 |
| Floquet 前 trace rows | 4,995 |
| Floquet-independent rows | 4,440 |
| left/right active trace rows | 1,200 / 1,200 |
| axial internal active rows | 2,040 |
| one-cell matrix NNZ | 1,987,800 |
| 二次 Schur internal matrix NNZ | 658,200 |
| 每个 projected block shape | `120 x 120` |
| `S_LL/S_LR/S_RL/S_RR` numerical NNZ | 3,325 / 3,120 / 3,124 / 3,319 |
| full trace-size dense square | 未形成 |

standard 与 assembly-time static 的 exact matrix 等价性使用已有 MPI1 authority：

```text
relative Frobenius = 4.3274364883260015e-15
authority source   = 5cdcd748a986995f78faf93c9c914134cf60a2c3
authority sha256   = 95deeb8d6f0e133b328ab59f4e2de08b40aae0f4b44363bea178d6ddf9598c44
```

该值是 **MPI1 实测并由 MPI8 正式审计复用的 foundation fixture**，不能写成 MPI8
重新实测。复用时检查了冻结文件哈希、schema、case、ABI、命令、行数、NNZ、Git
祖先关系和矩阵内核文件未变化。MPI8 live one-cell 的全局 row/NNZ 不变量与 MPI1
authority 一致；分区相关 row SHA 不作跨 MPI 比较。

## 4. 符号、Floquet 与 trace basis

Petrov 投影用 left trace 作为测试基。它的作用类似“带权坐标尺”：在有损、非自伴
问题中，不能用 right basis 自己代替这个坐标尺。

| Gate | 实测 | 限值 | 结论 |
|---|---:|---:|---|
| analytic Bloch polynomial residual | `2.0065e-16` | `1e-10` | pass |
| analytic outward-flux balance | `1.0033e-16` | `1e-10` | pass |
| analytic wrong-sign negative control | `1.38134` | `>1e-6` | pass |
| actual FE wrong-sign negative control | `9.02877e-2` | `>1e-6` | pass |
| right lift Floquet/orientation closure | `1.7392e-15` | `1e-10` | pass |
| left lift Floquet/orientation closure | `1.7307e-15` | `1e-10` | pass |
| negative trace span residual | `4.0392e-15` | `1e-10` | pass |
| negative coordinate condition | `1.00000000000011` | `1e12` | pass |
| Gram condition | `2.98887e3` | `1e12` | pass |
| projection coefficient round trip | `2.7749e-14` | `1e-10` | pass |
| `D R-I` | `1.03894e-14` | `1e-10` | pass |
| internal two-sided trace identity | `5.45961e-15` | `1e-10` | pass |

Floquet 约束为 555 条，其中 edge 155、face 400；几何配对误差为 0，并使用 exact
Basix entity transforms。没有 probe fit、全边界 gather 或稠密 boundary square。

## 5. one-cell Bloch residual

离散单元的端点关系按统一 outward-normal 约定写为

```text
g_R = lambda g_L
f_R = -lambda f_L
```

从而检查

```text
[S_RL + lambda(S_RR + S_LL) + lambda^2 S_LR] r_j = 0.
```

“significant”不是按模态编号猜测，而是用 11 个 exact Full3D trace 平面独立分解出的
正向/反向系数权重，保留累计权重的 `1 - 1e-8`。

| 指标 | forward | backward | Gate/解释 |
|---|---:|---:|---|
| significant max `rho` | `6.39675e-11` | `6.50899e-11` | `<=1e-10`, pass |
| weighted `rho` | `4.28745e-13` | `3.84179e-13` | pass |
| all-mode max `rho` | `2.89728e-8` | `2.94898e-8` | 尾部弱模态诊断 |
| projected off-diagonal ratio | `3.35919e-12` | `3.30137e-12` | `<=1e-8`, pass |
| connected components | 1 | 1 | 仅非显著尾部 |
| component indices | `34,35,114–117` | 同左 | 不在 significant set |

因此，all-mode 最大值不能被用来宣称主导物理模式发生互混。它出现在传播因子很小的弱
模态上，按单列归一化后被放大；整体算子和实际有权重模式均通过。

作为对照，未经 scalar-CG 离散修正、直接使用 continuous beta 时：

| 指标 | forward | backward |
|---|---:|---:|
| significant max `rho` | `8.97703e-6` | `8.97703e-6` |
| weighted `rho` | `1.44039e-8` | `5.84606e-9` |
| projected off-diagonal ratio | `9.05066e-6` | `9.05066e-6` |

这说明现有 scalar-CG 修正本身有明确价值；本轮没有发现理由用 projected matrix
propagation 替换它。

## 6. exact Full3D coefficient oracle

exact oracle 直接保存 11 个结构化 z 平面的 canonical FE trace，并按

```text
G = W^H B_gamma R
D = G^-1 W^H B_gamma
c_n = D g_n
```

求系数。它不使用 ParaView 插值场，也不使用原来的 `40 x 20` sampled fit。

### 6.1 Full3D solve Gate

| 指标 | 实测 | Gate | 结论 |
|---|---:|---:|---|
| Nédélec DoF | 134,320 | identity | pass |
| condensed+DtN rows | 46,656 | identity | pass |
| matrix NNZ | 26,952,096 | identity | pass |
| factor NNZ | 164,378,718 | measured | recorded |
| true relative residual | `8.31689e-11` | `1e-9` | pass |
| energy closure | `-1.61182e-12` | `1e-5` | pass |
| `R/T/Aclosure` | `0.6214607484 / 0.0062480785 / 0.3722911731` | official | pass |
| Floquet x/y/edge-corner mismatch | `0 / 0 / 0` | exact | pass |
| solve elapsed | `132.598 s` | measured | recorded |
| complete audit elapsed | `200.895 s` | measured | recorded |

本次没有外部同步 PSS/USS watchdog。`11.035 GiB` 只是 8 个 rank 各自历史 RSS 峰值之和
的上界，不是同时刻整进程树峰值，不能用作本轮 Hybrid 资源比较。

### 6.2 exact trace 与传播

| 指标 | 实测 | Gate/意义 |
|---|---:|---|
| exact trace max projection residual | `5.224931e-6` | `1e-8`, **fail** |
| bottom/top projection residual | `3.514657e-6 / 5.224931e-6` | 端点缺失分量 |
| middle planes最小 residual | `7.992046e-13` | 中间内部很小 |
| two-way pair condition | `32.4481` | pass |
| pair reconstruction residual | `1.57025e-16` | pass |
| scalar-CG exact forward mismatch | `2.00386e-7` | 小于 mixing 支持阈值 |
| scalar-CG exact backward mismatch | `9.21383e-9` | 小于 mixing 支持阈值 |
| sampled-vs-exact bottom coefficient差 | `7.99374e-6` | sampled 仅诊断 |
| sampled-vs-exact top coefficient差 | `1.19466e-5` | sampled 仅诊断 |

Review V3 的 sampled oracle 曾给出约 `3.9956e-3` forward mismatch；严格 FE 质量矩阵
投影后的跨单元 trace-metric mismatch 只有 `2.00386e-7`。因此旧采样值不能继续作为
matrix mixing 的证据。

## 7. A/B/C/D 判定

| 分类 | 是否成立 | 理由 |
|---|---|---|
| A：当前传播完整通过 | 否 | significant propagation 通过，但 exact M120 trace projection foundation 未通过 |
| B：少数认证近简并 block mixing | 否 | connected block 仅在非显著尾部，且未被同一 exact physical group 支持 |
| C：广泛 off-diagonal mixing | 否 | global off-diagonal 只有约 `3.3e-12`，exact mismatch 不对齐 |
| D：trace space/foundation 不足或审计不确定 | **是** | exact Full3D trace projection `5.224931e-6 > 1e-8` |

正式分类保持 artifact 的 fail-closed 名称：

```text
D_OR_PHASE_A_INDETERMINATE
```

这不是“证明 scalar-CG 完全无误”，而是证明 **现有证据不允许把问题归因为 M120 空间
内部的 mode mixing**。最明确的新信号是端点附近存在当前 M120 横截面物理模态空间
不能精确表示的 trace 内容。

## 8. Phase B 与 anchors

```text
projected/block discrete propagation = not_implemented
Task035c high-grazing S control       = not_run
A004-S Hybrid rerun                   = not_run
A049-P                                = not_run
A001-P                                = not_run
M160                                  = not_run
M240/M480/M492                        = forbidden_not_run
226-point scan                        = forbidden_not_run
iterative solver                      = not_started
```

由于 Phase A 没有授权 Phase B，上述运行若继续就会违背 Review V4：它们只能验证一个
没有根因证据的新传播实现。因此本轮在 Phase A 停止，没有用更多 PDE 掩盖负结论。

## 9. artifact 哈希

| artifact | SHA-256 |
|---|---|
| Phase A JSON | `021bc075adcc4acaa0f9202fe70fad1d9755113091dd8e74e0f141ed2bd89d09` |
| projected one-cell blocks | `40969385ba43f9e36cdcea7d61de6ac5bb97798450d16113f490102ce5d786fa` |
| exact 11-plane FE traces | `cbae01bfcf983caf29183a6f47a42b1db65f956bc114263cf77ea5182f20711c` |
| exact Petrov coefficients | `01644583e72400a966f88f5fa310d5c9a8b06a776f741041cdf07dddf1ba3c2b` |
| Full3D run summary | `d778fa49ffffaec20409a3bf87e0d8a9bda7643c30925362cf616849045f4b80` |

## 10. 唯一下一建议

Task036 在此停止，Hybrid 不提升为 production，也不在本任务进入迭代法。等待集中审阅
后，唯一 production 建议是另行授权
**Full3D assembly-time static condensation + FGMRES +
H(curl)/trace-aware preconditioner**；本轮只提出路线，不实现、不测试。

`full-interface discrete Bloch trace modes` 只保留为将来可另立任务的研究方向，不是本轮
自动下一步，也不能替代上述 production disposition。
