# Task036 Review Report V5：Hybrid 物理闭合、接口诊断与大 middle 区域恢复路线

## 1. 审阅身份与优先级

```text
review = Task036 Review V5
branch = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head = 9b1a318514d3c52806d0311bac8ba7fb8729b8f5
reviewed_document = outcomes/hybrid_production_readiness_assessment.md
assessment_disposition = APPROVED_WITH_MATERIAL_CORRECTIONS
ordinary_default = unchanged
master_merge = not_authorized
Hybrid_today = research_only_not_production_qualified
Hybrid_or_equivalent_dimensional_reduction_for_current_0p7_target = practically_required
whole_domain_Full3D_iterative_alone_for_0p7 = insufficient
current_task_primary_goal = close_Hybrid_physics_and_recover_large_modal_middle
Hybrid_FGMRES = deferred_not_current_work
wavelength_continuation_to_0p7 = deferred_not_current_work
full_parameter_scan = paused
final_response_document = required
```

Codex 的 `hybrid_production_readiness_assessment.md` 总体方向合理，尤其正确识别了当前
`M120` physical-QEP trace space 在 `z=10/110 nm` 端点不够，而进入中间区域后投影残差
快速衰减。当前最有价值的根因假设是：

> 原 `10/110 nm` 接口离上下端部散射区或 evanescent boundary layer 太近，当前截断
> port space 被迫表示尚未衰减的近场尾部。

本 Review 对上一版优先级作如下修正：

1. 对当前具有较长 `z`-不变中间区、且最终目标为 `0.7 nm` 的结构，Hybrid 或等价的
   真正维度约简在工程上几乎是必要的第一层压缩；whole-domain Full3D 即使叠加静态
   凝聚和迭代法，也不能单独承担最终规模。
2. 当前阶段先解决 Hybrid 物理闭合与大 middle 区域恢复，不在本 Review 中启动 Hybrid
   FGMRES、whole-domain Full3D iterative、local h/p、代理模型、反演或波长 continuation。
3. 移动接口到 `30/90` 或 `40/80 nm` 是**根因诊断和物理锚点**，不是默认最终生产方案。
   它可能通过增加 3D endcap 厚度换取精度，同时显著侵蚀 Hybrid 的自由度与内存收益。
4. 如果缩短 middle 区域后成功，下一步必须利用这一证据，在保持原 `10/110 nm` 大
   modal middle 的前提下补回端点 boundary-layer trace，而不是直接接受厚 endcap 作为
   最终答案。
5. `M≈16,029/方向` 只可写成真正三维 phase-space 的数量级估算，不是任意 patterned
   cross-section 的严格下限或正式 M 预算。

---

## 2. 已确认结论：不得重复研究

以下结果已有实际数值或严格审计支持，当前不得重新发明同类候选：

```text
P tangential direct projection bug                         = fixed
reciprocal high-order trace identity                       = fixed
exact variational traction dual                            = fixed
propagation / traction / recovery beta identity            = fixed
near-degenerate connected-component normalization          = fixed/research-qualified
strong trace g_s = R_s L_s a algebra                       = pass
strong trace resource reduction                            = pass
free trace complement as main scattering-error root        = falsified
significant scalar-CG one-cell diagonal propagation        = pass
broad M120 internal cross-mode mixing                       = not supported
M240/M480/M492 global direct expansion                      = closed controlled negative
226-point scan before anchor closure                        = paused
```

A004-S exact Full3D trace 投影到相同 M120 space 后为：

| z, nm | exact M120 trace residual |
|---:|---:|
| 10 | `3.514657e-6` |
| 20 | `9.780687e-8` |
| 30 | `2.881134e-9` |
| 40 | `8.852074e-11` |
| 50 | `2.860216e-12` |
| 60 | `7.992046e-13` |
| 70 | `1.629599e-11` |
| 80 | `3.717959e-10` |
| 90 | `8.687626e-9` |
| 100 | `2.089942e-7` |
| 110 | `5.224931e-6` |

该空间分布使接口位置成为当前第一优先变量，但它尚未证明 actual Hybrid 会通过。

---

## 3. 缩短 middle 区域到底验证什么？

### 3.1 原分解与两个候选

全域为 `z=-10...130 nm`，总厚度 140 nm。

| 接口 | bottom/top 3D endcap | 3D 总厚度 | modal middle | 被 modal 消去的 z 比例 |
|---|---:|---:|---:|---:|
| `10/110` | 20 / 20 nm | 40 nm | 100 nm | 71.4% |
| `30/90` | 40 / 40 nm | 80 nm | 60 nm | 42.9% |
| `40/80` | 50 / 50 nm | 100 nm | 40 nm | 28.6% |

所以 `30/90` 会把局部 3D 厚度约翻倍，`40/80` 会增加到原来的约 2.5 倍。

以 A004-S 原 strong-trace 结构为一阶估计：

```text
old retained local rows = 6528 + 6528
modal rows              = 240
old total rows          = 13296
Full3D rows             = 46656
```

若局部 rows 近似随 endcap 厚度增长，则仅作 preflight 估算：

```text
30/90 rough rows ≈ 2.0 * (13296 - 240) + 240 = 26352
40/80 rough rows ≈ 2.5 * (13296 - 240) + 240 = 32880
```

对应约为 Full3D rows 的 56.5% 和 70.5%。这不是正式 authority；实际 NNZ、MUMPS fill
和 whole-job memory 必须实测。但它明确说明：**接口内移即使物理成功，也可能显著削弱
原 Hybrid 的资源优势。**

### 3.2 三类结果必须分开

#### A. 接口内移后物理仍失败

说明端点 boundary-layer representability 不是充分根因。不得继续扫描更多接口，也不得
直接开发局部 evanescent enrichment；应根据实际失败重新审查 port-space、外端部耦合或
fixed-channel identity。

#### B. 接口内移后物理通过，且资源仍明显优于 Full3D

说明：

```text
BOUNDARY_LAYER_TRUNCATION_ROOT_CONFIRMED
```

也就是 current physical-QEP mode family 和 scalar-CG propagation 在渐近中间区可以工作，
原失败主要来自接口过靠外、端点 evanescent content 未衰减。

该结果可作为可靠 fallback 和后续 port-enrichment 的真值锚点，但仍不能自动成为最终
生产接口，因为 modal middle 从 100 nm 缩短到 60 或 40 nm。

#### C. 接口内移后物理通过，但资源优势很小或消失

同样确认 boundary-layer 根因，但分类为：

```text
BOUNDARY_LAYER_ROOT_CONFIRMED_BUFFER_TOO_EXPENSIVE
```

此时严禁把“物理通过”写成 Hybrid production success。下一步必须回到原 `10/110 nm`
接口，通过**接口局部的模态/port enrichment**表示 boundary layer，而不是继续扩大 3D
endcap。

---

# 4. Stage I：有界的渐近接口诊断

## 4.1 总体边界

```text
new campaign / state machine / evidence framework = forbidden
M240 / M480 / M492 global solve                  = forbidden
226-point scan                                    = paused
strong-trace formulation changes                 = forbidden
Hybrid FGMRES                                     = deferred
wavelength continuation                          = deferred
ordinary default                                  = unchanged
master merge                                      = not authorized
maximum new actual A004-S interface candidates    = 2
```

允许：

- 解除 explicit interface 参数的 Task-local Gate；
- 修复由非默认接口暴露的真实 row-map、phase-length、material、recovery 或 ledger bug；
- 增加最小 interface identity 与 material-invariance 检查；
- 复用现有 strong-trace solver、same-input Full3D authority 和全部后处理。

## 4.2 Stage I0：离线和 assemble-only preflight

对以下两个冻结候选：

```text
I0a = interfaces 30/90 nm
I0b = interfaces 40/80 nm  # conditional safety-margin candidate
```

必须先完成：

1. 验证 modal middle 内逐层材料严格满足：

   ```text
   epsilon(x,y,z) = epsilon(x,y)
   ```

2. 验证接口为实际 mesh planes，x/y trace grid 与 cross-section完全匹配。
3. 验证 modal length、forward/backward scalar-CG cell count、traction beta、strong trace、
   field recovery 和 absorption ledger 全部绑定新接口，禁止残留 `10/110` 常量。
4. 报告 local z cells、retained rows、strong square rows、matrix NNZ preflight 和 modal
   middle length。
5. 报告相对原 `10/110` 与 Full3D 的结构收益：

   ```text
   rows ratio
   matrix NNZ ratio
   estimated local thickness ratio
   expected factor-risk classification
   ```

6. 从已有 exact trace authority冻结：

   ```text
   candidate
   bottom/top trace residual
   safety factor to 1e-8
   total 3D endcap thickness
   remaining modal-middle thickness
   ```

不得为该 preflight 重跑 Full3D。

## 4.3 Stage I1：A004-S，`30/90 nm`

固定：

```text
point          = A004-S
p/h/Ny         = p5 / h10 / Ny4
polarization   = S
grazing/phi    = 0.5° / 45°
M_core         = 120 per direction
coupling       = strong trace
backend        = assembly-time static condensation
MPI            = 8
interfaces     = 30 / 90 nm
```

必须报告：

- rows、matrix NNZ、factor NNZ、fill；
- simultaneous RSS/PSS/USS/swap；
- reduced residual四分量；
- `D R-I`、strong trace identity、Petrov traction；
- R00、R/T/Aclosure/Avolume、energy identity；
- 全部96个fixed channels；
- 与原`10/110` strong-trace逐通道差；
- actual资源收益相对Full3D和原Hybrid的变化。

### 4.3.1 物理 Gate

```text
96/96 fixed channels                           pass
abs(R + T + A_volume - 1)                     <= 1e-5
max abs(Delta R/T/A_volume vs Full3D)          <= 1e-4
reduced true residual                          <= 1e-9
strong trace identity                          <= 1e-10
Petrov traction                                <= 1e-8
external DtN / noninterface residual           pass
zero swap                                      true
```

### 4.3.2 资源 Gate

```text
engineering pass:
    whole-job peak <= 0.85 * same-input Full3D peak

physics-only pass:
    physical Gate全部通过，但resource Gate失败
```

两者不得混写。

## 4.4 Stage I2：条件性 `40/80 nm`

仅当 `30/90` 满足以下条件才运行：

1. algebra、strong trace、Petrov、Floquet、DtN和linear residual全部通过；
2. 相比`10/110`，fixed channels或energy存在明确方向性改善；
3. 剩余失败与top侧`30/90`安全余量不足相容；
4. assemble-only预估未显示明显高于Full3D的资源风险；
5. 未出现与interface位置无关的新共同根因。

`40/80`使用同一物理与资源Gate。

完成两个候选后严禁再扫描其他接口位置。

---

# 5. 若接口内移成功：如何恢复原 `10/110 nm` 大 modal middle

接口内移成功不是终点，而是为以下恢复路线提供因果证据。

目标固定为：

```text
3D endcaps仍约为20 nm + 20 nm
modal representation覆盖z=10...110 nm
core modes不过度增加
boundary-layer enrichment只在靠近两端的短区间存在
```

## 5.1 Stage R0：端点缺失分量与 mode-capacity 离线审计

使用现有 exact Full3D traces 和已计算的 QEP candidate modes，不运行新 PDE，计算：

```text
gamma_bottom = trace at z=10
q_bottom      = (I - R_core D_core) gamma_bottom

gamma_top    = trace at z=110
q_top         = (I - R_core D_core) gamma_top
```

并冻结：

1. `M=40/80/120/160/200/240` 的 exact trace projection residual；
2. 新增 modes 的 beta、decay length、方向、近简并组和 Gram condition；
3. 缺失分量 `q_bottom/q_top` 被额外 physical QEP evanescent modes 覆盖的比例；
4. 这些额外 modes 到 `z=30/90` 或 `40/80` 时的衰减量；
5. 所需额外模式是否只属于短程 evanescent tail，而不是核心传播通道。

该步骤的目的不是重新授权 global M240 solve，而是判断能否把额外模式**局部化**。

## 5.2 Stage R1：localized evanescent modal buffers

若现有 QEP mode family 能在合理额外规模下满足：

```text
endpoint exact trace residual <= 1e-8
extra-mode tail at inner buffer boundary <= tolerance
Gram / biorthogonality pass
```

则构造三段 modal representation：

```text
z=10...30   : M_core + M_bottom_buffer
z=30...90   : M_core only
z=90...110  : M_core + M_top_buffer
```

若 `40/80` 才有足够安全余量，则相应使用：

```text
z=10...40   : enriched bottom modal buffer
z=40...80   : M_core only
z=80...110  : enriched top modal buffer
```

核心原则：

- `M_core=120` 继续跨越完整大 middle；
- 高阶 evanescent modes 只在靠近对应端点的短 buffer 中传播；
- 它们在进入 core 前被局部静态消去或通过小型 scattering/Schur block凝聚；
- 不把全部 extra modes 作为跨100 nm的全局双向未知量；
- 不形成 replicated global `M_total²`；
- 3D endcap接口仍回到 `10/110 nm`。

这一路线的物理含义是：

> 用便宜的模态边界层补回原来需要额外20–30 nm三维FEM才能衰减的近场，而把长距离传播
> 继续交给小的核心mode space。

### R1 actual Gate

先只运行一个 A004-S：

```text
interfaces = 10/110 nm
core M = 120
localized buffer modes = frozen by R0
strong trace = enabled
```

必须同时满足：

```text
96/96 channels
energy and R/T/A Gate
trace / Petrov / residual Gate
whole-job peak <= 0.85 * Full3D
rows/NNZ/peak materially better than successful shifted-interface candidate
```

若通过，记录：

```text
WIDE_MIDDLE_LOCAL_EVANESCENT_RECOVERY_PASS
```

## 5.3 Stage R2：transfer-eigenmode / optimal port buffer basis

若：

- 现有 QEP candidate modes 到 M240 仍不能有效覆盖端点缺失分量；或
- 需要太多 extra physical modes，局部buffer也失去资源优势；或
- Gram/near-degenerate条件不稳定；

则不继续扩大 physical-QEP M。下一选择是针对薄 buffer slab 构造
transfer-eigenmode/optimal port basis：

```text
bottom buffer operator : z=10 -> z=30/40
 top buffer operator   : z=110 -> z=90/80
```

basis只需逼近端部可达trace和其向core传递的分量，并使用transfer singular/eigenvalue tail
作为截断证书。它仍与`M_core=120`的长middle耦合，并在局部buffer处凝聚。

Stage R2不在接口测试未成功前实现。进入R2前，Codex必须先提交一页以内的离散算子、未知量、
复杂度和验收说明；不得直接搭建大型新framework。

## 5.4 full-interface discrete Bloch 的位置

Review V4已经证明当前significant scalar-CG one-cell propagation通过。因此full-interface
Bloch不是当前第一选择。

只有当transfer/optimal port分析表明缺失空间需要与实际3D one-cell trace operator严格一致、
且现有QEP family无法提供稳定basis时，才将full-interface discrete Bloch列为后续候选；
本批次不自动实施。

---

# 6. 若接口内移失败

若`30/90`和条件性`40/80`都未取得明确物理改善，则：

```text
ASYMPTOTIC_INTERFACE_HYPOTHESIS_NOT_SUFFICIENT
```

此时不得执行R1局部evanescent enrichment，因为其因果基础不存在。Codex必须用已有结果回答：

- actual trace residual已经下降，但哪些channels/energy仍不变；
- 误差是否来自external/endcap coupling、mode identity或fixed-channel postprocess；
- 是否存在same-input Full3D/Hybrid离散不一致。

完成一份root-cause delta表后停止等待Review，不得转去迭代法、波长continuation或广域扫描。

---

# 7. 本 Review 明确延期的工作

下列工作均不是当前Task036执行范围：

```text
Hybrid matrix-free FGMRES / block preconditioner
whole-domain Full3D iterative production study
local exact-sequence h/p endcap integration
13.5 -> 5 -> 2 -> 1 -> 0.7 nm continuation
distributed all-wavelength modal core
surrogate / inversion
226-point robustness scan
```

它们的重要性不被否定，但必须等当前Hybrid物理闭合和`10/110`恢复路线得到明确结论后另行
审阅。当前Codex不得提前实现这些模块。

---

# 8. 当前执行授权

本轮Codex连续执行以下有限主线：

```text
I0 preflight
→ I1 A004-S 30/90
→ 条件满足时 I2 A004-S 40/80
→ 若接口内移物理成功，执行 R0 离线capacity审计
→ 若R0明确支持，实施一个最小R1 localized-evanescent A004-S 10/110 candidate
→ 停止等待Review
```

限制：

- 不运行P偏振anchor；
- 不运行p6 59-goal；
- 不恢复参数扫描；
- 不进行global M sweep PDE；
- 不开发R2，除非下一次Review授权；
- 不开始迭代法或波长continuation；
- 不修改ordinary default；
- 不合并master。

---

# 9. Response V5要求

结束前必须创建：

```text
docs/task036_forward_solver_bugfix_hardening/response_v5.md
```

必须用通俗语言回答：

1. `30/90`和条件性`40/80`是否运行、各自是否物理通过；
2. 若通过，证明的是boundary-layer/interface-placement问题，还是其他问题；
3. endcap扩大后rows、NNZ、factor、RSS/PSS/USS和wall time增加多少；
4. modal middle从100 nm缩短到60/40 nm后，Hybrid资源收益损失多少；
5. 结果属于：
   - physics + resource pass；
   - physics pass but buffer too expensive；
   - physics fail；
6. R0的M-capacity和端点缺失分量结论；
7. 是否实施R1 localized evanescent buffers；
8. R1是否成功在`10/110 nm`恢复96/96、energy和资源优势；
9. 哪些结论是measured，哪些是结构估算或inference；
10. 最终HEAD、修改文件、测试、PDE、未运行项、工作树和远程同步状态。

最终聊天回复必须引用`response_v5.md`路径。

---

# 10. 停止条件

任一条件满足立即停止本轮：

1. I1物理通过且R0/R1完成；
2. I1失败且I2不满足授权条件；
3. I2完成后仍无明确物理改善；
4. R0证明physical QEP extra modes无法在合理局部规模覆盖端点缺失空间；
5. R1实际候选完成，无论通过或失败；
6. 非默认接口暴露需要重写mesh/QEP/solver framework；
7. 出现OOM、swap或无法解释的数值Gate失败；
8. 后续需要R2、迭代法、h/p或波长continuation才能继续。

停止后提交结果、必要的最小数值修改和`response_v5.md`，推送当前远程同名分支。不得创建
新的Review版本，不得自行merge master。
