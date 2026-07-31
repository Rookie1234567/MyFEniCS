# Task036 Review Report V4：单元离散 Bloch 审计与 Hybrid 轴向传播闭合

## 1. 审阅身份与决定

```text
review = Task036 Review V4
branch = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head = 74e4eb3be87a0c0a05f4c2df963b1cc00f9c4f99
ordinary_default = unchanged
master_merge = not_authorized
strong_trace_algebra = pass
strong_trace_resource = pass
strong_trace_physical_qualification = fail
trace_complement_root_hypothesis = falsified_by_actual_anchor
next_action = exact_one_cell_discrete_bloch_audit
projected_matrix_propagation = conditional_on_audit
full_parameter_scan = paused
final_response_document = required
```

本审阅接受 Review V3 的 strong trace-subspace 数值实现作为研究能力：它正确删除了内部
接口上未受模态投影控制的有限元 trace complement，并保持了明显的 Hybrid 资源优势。
但 A004-S 的正式结果也证明：该 complement 不是当前衍射通道与能量误差的主因。

因此，本轮不得继续修改 strong-trace 约束、扩大 M、恢复 226 点扫描，或继续围绕接口
补空间增加罚项和诊断。下一步必须直接检查中间规则区域的轴向传播模型是否真正匹配同一
Full3D Nédélec 离散。

本审阅授权两级工作：

1. **必须先完成一个真实 z-cell 的离散 Bloch 审计；**
2. **只有审计明确证明逐模态对角传播不成立时，才实现小型 projected discrete Bloch
   / matrix-valued propagation。**

若审计不支持这一根因，必须停止，不得为了延续 Hybrid 路线而先写新传播框架。

---

## 2. 对 Review V3 结果的重新分类

### 2.1 strong trace 实现本身已经通过

A004-S 的实测结果为：

| 指标 | 实测 | Gate | 结论 |
|---|---:|---:|---|
| reduced true residual | `2.2893e-11` | `1e-9` | pass |
| bottom/top `D R-I` | `2.7638e-12 / 2.4151e-12` | `1e-10` | pass |
| bottom/top strong trace identity | `0 / 0` | `1e-10` | pass |
| bottom/top Petrov traction | `2.9292e-11 / 6.8286e-11` | `1e-8` | pass |
| direct tangential projection | `1.100e-12` | `1e-10` | pass |
| sampled physical interface `E_t` jump | `4.588e-15` | diagnostic | machine precision |
| strong system rows | `13,296` | lower than Full3D | pass |
| peak RSS | `7.893 GiB` | `<=0.85 Full3D` | pass |
| swap | `0` | `0` | pass |

旧 projection-only Hybrid 的接口跳跃约为 `9.272e-5`，strong trace 将其降低到机器
精度。因此：

```text
strong_trace_equation = implemented_correctly
interface_row_map = implemented_correctly
Petrov_flux_rows = implemented_correctly
static_recovery = implemented_correctly
resource_advantage = retained
```

后续文档不得继续把这一结果笼统写成 `strong_trace implementation failed`。更准确的状态是：

```text
STRONG_TRACE_ALGEBRA_AND_RESOURCE_PASS
AXIAL_MODAL_MODEL_PHYSICAL_CLOSURE_FAIL
```

### 2.2 物理资格化仍然失败

A004-S 仍有：

```text
abs(R + T + A_volume - 1) = 1.531666e-5 > 1e-5
fixed channels            = 77/96
```

而且 strong trace 与 old Hybrid 的：

- R/T/A 几乎相同；
- 19 个失败通道完全相同；
- 最大通道 power 变化约 `1.47e-9`；
- energy closure 仍约 `1.53e-5`。

因此，Review V2 的“自由 trace complement 是主要散射误差来源”假设已被实际 PDE 否定。

---

## 3. 当前根因排序

### 3.1 已基本排除的方向

以下方向不应继续作为主修复路线：

1. **线性求解失败**：true residual 已通过；
2. **接口电场补空间**：strong trace 已将其消除，但输出不变；
3. **traction 弱式错误**：exact Petrov traction 已通过；
4. **left/right 双正交失败**：完整 row norm 已通过；
5. **P 偏振切向投影污染**：Task036 已修复，A004-S 本身还是 S；
6. **单纯 M 不足**：A004-S 的 M120→M240 energy 与 forward mismatch 基本不变；
7. **通用端口法向或能量 ledger 符号错误**：A049-P 历史同一套 ledger 可达到约 `1e-6`
   closure，当前没有全局一致的 sign bug 证据；
8. **普通 Gauss 积分不足**：middle volume 已改为实际 scalar-CG cell polynomial 并使用
   相应 Gauss 阶次。

### 3.2 当前最强机制信号

A004-S 现有 Full3D sampled E/H oracle 报告：

```text
selected forward propagation coefficient mismatch  = 3.9956e-3
selected backward propagation coefficient mismatch = 8.3073e-5
```

M240 的 forward mismatch 仍约 `3.9961e-3`。这说明增加模式数没有修复主导 forward
传播差异。

当前中间传播把每个二维横截面 QEP 模式独立处理：

```text
beta_j -> scalar-CG corrected beta_j -> diagonal propagation factor_j
```

也就是默认一个 Full3D z-cell 仍由当前横截面模态逐个对角化。低掠射、非零方位角、
near-degenerate 和 lossy 非自伴情况下，这一假设可能不成立；真实离散单元可能产生
mode-to-mode mixing。

但现有 `40 x 20` sampled oracle 只是采样最小二乘，不是严格 FE 质量矩阵投影。因此：

```text
axial cross-mode mixing = leading hypothesis
axial cross-mode mixing = not yet proven
```

必须先完成下一节的 exact one-cell 审计。

---

## 4. Phase A：真实单 z-cell 离散 Bloch 审计

### 4.1 目标

回答唯一问题：

> 当前二维 QEP 模式加逐模态 scalar-CG propagation，是否真的是同一 p/h/mesh 的三维
> Nédélec 中间单元的离散传播本征结构？

这一阶段不运行完整 Hybrid anchor，不修改 production solver，不恢复扫描。

### 4.2 单元定义

装配中间规则区域的一个真实 z-cell：

```text
x-y mesh       = 与对应 Full3D 完全相同
z cells        = 1
z length       = 10 nm
polynomial p   = 与 anchor 相同
Ny             = 4
material       = stage4_xy
Floquet        = 同输入 kx/ky 和 orientation
quadrature     = 同 Full3D policy
scalar type    = complex128
MPI            = 1/2 fixture，随后 MPI8 micro authority
```

不得用独立简化单元、标量 Helmholtz 单元或采样点替代真实 H(curl) 单元。

### 4.3 静态凝聚与两端口 Schur 块

将单元内部自由度静态凝聚，只保留左右 z 面独立切向 trace。按统一 outward-normal 约定记录：

```text
[f_L]   [S_LL  S_LR] [g_L]
[f_R] = [S_RL  S_RR] [g_R]
```

必须保存：

- full/condensed row identities；
- left/right trace row sets；
- Floquet slave/orientation closure；
- interface mass和right/left trace basis；
- 不形成全周期 100 nm 三维体网格；
- 不形成与完整 trace 维数相同的长期稠密 square。

### 4.4 exact FE coefficient oracle

现有 sampled oracle只能作为对照。新增 exact oracle必须使用：

```text
trace mass B_gamma
right traces R
left traces W
G = W^H B_gamma R
D = G^-1 W^H B_gamma
```

从实际 Full3D interface trace 得到 exact Petrov coefficients。优先复用现有 same-input
Full3D raw field/vector authority。

如果现有 artifact没有保存足以恢复 exact FE trace 的向量，允许只为以下目的重跑一个
same-input Full3D anchor：

```text
export bottom/top exact interface trace vectors
```

不得借此恢复角度扫描或重复无关后处理。

exact oracle必须报告：

- bottom/top projection residual；
- Gram condition；
- forward/backward coefficient mismatch；
- sampled 与 exact oracle 的差；
- mode/group-wise mismatch；
- near-degenerate subspace-wise mismatch。

### 4.5 当前 scalar-CG multiplier 的 one-cell Bloch residual

在一致 outward-normal 约定下，若：

```text
g_R = lambda g_L
f_R = -lambda f_L
```

则单元离散 Bloch 多项式为：

```text
[S_RL + lambda(S_RR + S_LL) + lambda^2 S_LR] g_L = 0
```

Codex必须先在 homogeneous analytic/FE fixture 中验证符号和端点约定，不能直接把此式
硬编码到正式路径。

对每个当前 right trace `r_j` 和 scalar-CG multiplier `lambda_j` 计算：

```text
rho_j =
 ||[S_RL + lambda_j(S_RR + S_LL) + lambda_j^2 S_LR] r_j||
 / operator_scale_j
```

同时计算：

- significant-mode最大与加权 `rho_j`；
- near-degenerate group/subspace residual；
- residual 对 continuous-beta 与 scalar-CG beta 的比较；
- projected off-diagonal mixing ratio；
- mixing是否集中在少数 connected blocks。

### 4.6 审计判定

#### A. 当前传播通过单元审计

若：

```text
significant-mode rho <= 1e-10
projected off-diagonal ratio <= 1e-8
exact coefficient mismatch不支持matrix mixing解释
```

则不得实现 projected Bloch QEP。此时应停止并审查：

- Full3D trace coefficient extraction；
- mode identity / ordering；
- external/local coupling；
- fixed-channel comparison identity。

#### B. 误差集中于少数近简并子空间

若总体 mixing 很小，但少数 near-degenerate connected components 中残差显著，则只实现：

```text
block-matrix propagation on certified connected components
```

不得直接升级为全 `M x M` propagation。

#### C. 广泛的 off-diagonal mixing 得到证明

若：

```text
significant-mode residual明显大于离散误差背景
且多个非相邻mode/group存在稳定off-diagonal coupling
且exact oracle与该误差方向一致
```

则进入 Phase B 的 projected discrete Bloch QEP。

#### D. 当前 R/W trace space 本身失秩或条件恶化

若 projected space无法稳定表示 one-cell trace operator，则停止本路线，并把下一候选记录为：

```text
full-interface discrete Bloch modes
or transfer-eigenmode optimal port basis
```

不得在 Task036 中无审阅地直接展开。

---

## 5. Phase B：conditional projected discrete Bloch propagation

只有 Phase A 结论为 C，或结论 B 要求有限 block传播时，才允许修改传播核心。

### 5.1 小型 projected cell QEP

将单元 Schur 块投影到当前 right/left trace space。按经过 fixture验证的normal convention
形成：

```text
K0 = W^H S_RL R
K1 = W^H (S_RR + S_LL) R
K2 = W^H S_LR R

(K0 + lambda K1 + lambda^2 K2)c = 0
```

其中 `W` 必须使用当前 Petrov normalization；lossy/非自伴问题不得用 `R^H` 替代。

### 5.2 传播表示

允许：

- SLEPc PEP / ordered generalized Schur；
- left/right biorthogonal propagation basis；
- connected block matrix propagation；
- repeated-cell composition或稳定的 `lambda^N`。

禁止：

- 显式使用病态 `C^-1` 而无condition/audit；
- growing inverse transfer factors；
- 形成完整 trace-space dense propagator；
- 恢复中间100 nm完整3D体网格；
- 用Full3D结果直接拟合一个仅对A004有效的经验矩阵。

### 5.3 保持 Hybrid 优势

正式 solver继续使用：

```text
端部 local 3D FEM
+ strong trace restriction
+ M120 modal amplitudes
+ one-cell-derived matrix propagation
```

中间100 nm仍不铺设完整三维网格。新增长期存储应为 `O(M^2)` 小矩阵；M120下一个
complex128 `120 x 120` 矩阵约0.22 MiB。

实际资源仍必须由MUMPS factorization测量，不能只凭small-block大小宣布成功。

---

## 6. 实际验证顺序

### 6.1 control

先使用历史已经闭合的 Task035c 高掠射 S 主点作为 control：

```text
p6/h10
10° grazing
0° azimuth
S
M120
```

要求新的 one-cell/model propagation不得破坏原有同网格 Full3D闭合。

### 6.2 target 1：A004-S

```text
p5/h10
0.5° grazing
45° azimuth
S
Ny4
M120
static condensation
MPI8
```

必须达到：

```text
one-cell projected Bloch residual             <= 1e-10
strong trace identity                         <= 1e-10
Petrov traction residual                      <= 1e-8
true residual                                 <= 1e-9
forward exact coefficient mismatch            <= 4e-4
energy closure                                <= 1e-5
same-p Full3D max abs Delta R/T/A              <= 1e-4
fixed channels                                96/96
peak memory                                   <= 0.85 Full3D
zero swap                                     true
```

其中 `4e-4` 表示相对现有约 `3.996e-3` 至少改善一个数量级；它是机制Gate，不替代
最终通道和能量Gate。

### 6.3 target 2/3

只有 A004-S 完整通过后，依次运行：

```text
A049-P : p5/h10, 10°/90°, P, M120
A001-P : p5/h10, 0.5°/0°,  P, M120
```

不得先运行P点来绕过A004-S失败。

### 6.4 M扩展

默认禁止提高M。只有满足：

```text
projected discrete propagation机制全部通过
A004-S只剩明确的modal truncation
预测M160 peak仍低于0.85 Full3D
```

才允许一个M160；不得恢复M240/M480/M492。

---

## 7. 停止与路线切换

### 7.1 立即停止 Hybrid production 路线

任一条件满足即停止：

1. one-cell exact审计不支持axial mixing，而无新的明确根因；
2. projected discrete Bloch实现后A004-S fixed channels仍保持旧失败集合；
3. forward exact coefficient mismatch未改善至少一个数量级；
4. energy仍约 `1.53e-5` 平台；
5. strong Hybrid peak超过Full3D的85%；
6. 需要恢复完整中间3D体网格才能闭合；
7. 需要经验性energy correction、penalty或放宽Gate。

停止后的production主线固定为：

```text
Full3D assembly-time static condensation
+ FGMRES
+ H(curl)/trace-aware preconditioner
```

Hybrid保留为研究分支，不得写成production成功。

### 7.2 后续可单独研究的方法

若 current physical modes无法压缩低掠射P接口空间，可以另立任务研究：

- full-interface discrete Bloch trace modes；
- transfer-eigenmode / optimal port basis；
- randomized local port reduction。

这些不属于本审阅的自动后续，不得在Task036中无界展开。

---

## 8. 开发效率与代码边界

本轮不设置机械代码行数上限，但必须遵守：

1. 先完成Phase A证据，再写Phase B数值核心；
2. 不新建campaign、状态机、receipt、hash或新watchdog框架；
3. 不复制Full3D/Hybrid runner主体；
4. one-cell assembler、audit和projected propagation应职责清晰；
5. 不为每个failure增加一层defensive wrapper；
6. 发现数学/索引/符号bug直接修核心，并补最小回归；
7. 同一问题不得通过新增多个互相重叠的diagnostic口径掩盖；
8. ordinary default保持不变；
9. 不merge master。

允许的主要新增模块建议不超过：

```text
one-cell discrete Bloch assembler/audit
projected discrete propagation（仅审计通过时）
对应tests
```

这不是要求强行合并成一个大文件；也不允许为任务调度再建立大型基础设施。

---

## 9. 必须生成的结果文档

### 9.1 Phase A 必须生成

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/
    one_cell_discrete_bloch_audit.md
```

至少包含：

- 单元与源码身份；
- Schur块shape/NNZ；
- normal/Floquet/orientation验证；
- exact coefficient oracle；
- sampled-vs-exact对比；
- per-mode/group Bloch residual；
- off-diagonal mixing图表；
- A/B/C/D判定；
- 是否授权Phase B。

### 9.2 Phase B若执行，必须生成

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/
    projected_discrete_bloch_results.md
```

至少包含：

- QEP/Schur formulation与符号验证；
- eigenvalue/passivity/condition；
- control与A004-S结果；
- old Hybrid / strong Hybrid / new propagation / Full3D四方比较；
- rows/NNZ/factor/memory/time；
- fixed channels完整统计；
- 是否运行P anchors；
- 最终production disposition。

---

## 10. Codex 必须提交 response

无论任务在Phase A停止，还是完成Phase B，Codex结束前都必须创建：

```text
docs/task036_forward_solver_bugfix_hardening/response_v1.md
```

该 response 必须使用通俗语言，不假设读者默认理解Bloch、Petrov、Schur或mode mixing。
不能只复制日志或测试计数。

response至少回答：

1. **这轮到底做了什么？**
2. **strong trace为什么没有修复衍射通道？**
3. **one-cell exact审计是否证明轴向cross-mode mixing？**
4. **是否实现了projected discrete Bloch propagation？为什么？**
5. **control、A004-S、A049-P、A001-P分别运行了什么、结果是什么？**
6. **Hybrid是否仍保持精度和内存优势？**
7. **哪些bug被真正修复，哪些只是诊断假设被否定？**
8. **当前production推荐是Hybrid还是Full3D iterative？**
9. **下一步只建议一条主线是什么？**

response必须包含：

- 起始与最终完整HEAD；
- 关键提交；
- 修改文件清单；
- 测试与MPI结果；
- actual PDE表格；
- 未运行项及原因；
- `git status --short`；
- 本地与远程分支ahead/behind；
- 明确确认master未修改、未合并。

Codex最终聊天回复也必须简要引用`response_v1.md`的结论，并给出其路径；不得只说
“已完成，请查看仓库”。

---

## 11. 最终授权语句

Codex下一轮只被授权：

```text
1. 完成exact one-cell discrete Bloch audit；
2. 根据A/B/C/D判定决定是否实现projected/block propagation；
3. 按固定顺序运行control与anchors；
4. 更新两个outcome文档；
5. 编写response_v1.md；
6. 推送同一Task036远程分支并停止。
```

禁止：

- 恢复226点扫描；
- 继续调strong-trace接口；
- M240/M480/M492；
- penalty/Nitsche/人工能量修正；
- 放宽channel/energy/residual Gate；
- 新代理模型、反演、h/p或迭代法实现；
- 自行merge master。

本审阅的核心原则是：

> 不再根据一个采样诊断直接启动大架构。先用真实Full3D单元离散证明传播根因；证明后只
> 修改传播层，证明不了就停止Hybrid生产化，并把工程主线转向Full3D静态凝聚迭代法。
