# Task036 Review Report V5：Hybrid production readiness 审阅与渐近接口闭合路线

## 1. 审阅身份与决定

```text
review = Task036 Review V5
branch = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head = 9b1a318514d3c52806d0311bac8ba7fb8729b8f5
reviewed_document = outcomes/hybrid_production_readiness_assessment.md
assessment_disposition = APPROVED_WITH_MATERIAL_CORRECTIONS
ordinary_default = unchanged
master_merge = not_authorized
Hybrid_today = research_only_not_production_qualified
Hybrid_0p7_role = strategic_conditional_route_not_proven_necessary
Full3D_iterative_role = near_term_production_baseline_and_mandatory_fallback
next_numerical_action = bounded_asymptotic_interface_closure
full_parameter_scan = paused
new_modal_architecture = not_authorized_before_interface_closure
final_response_document = required
```

Codex 的 `hybrid_production_readiness_assessment.md` 总体上是合理的，而且抓住了 Review V4
之后最有价值的新证据：当前 M120 physical QEP trace space 在 `z=10/110 nm` 端点不够，
但同一空间进入中间区域后投影残差快速下降。这使“接口距离端部散射区太近”成为当前最优先、
成本最低、证据最直接的假设。

本审阅批准继续 Hybrid，但对报告中的四个表述作实质修正：

1. Hybrid 对 0.7 nm 是**重要且可信的条件性战略路线**，不是已经证明的“必要唯一主线”；
2. Full3D static-condensed iterative 不能被降格为纯 reference，它是近期必须推进的生产基线、
   无 z-invariant middle 时的唯一可靠 fallback，也是 Hybrid endcap solver / PC 的开发基础；
3. `M≈16,029/方向` 只能作为真正三维 phase-space 量级估算，不能称为对任意 patterned
   cross-section 的严格解析下限或正式 M 预算；
4. `z=30/90 nm` 是首个最小 buffer 候选，但 top 侧 `8.69e-9` 只刚刚通过 `1e-8`，
   不能在它一次失败后立即跳到全新 optimal-port architecture。最多允许一个更深、已有
   exact-trace margin 支撑的候选，然后必须收口。

---

## 2. 对 readiness assessment 的逐项判定

### 2.1 认可：当前 direct Hybrid 只能是 research/reference implementation

现有 direct 路径含有：

- all-mode MUMPS shift-invert QEP；
- replicated modal square / modal vectors；
- all-mode dense multi-RHS；
- local MUMPS LU；
- mode / factor / recovery / record 生命周期重叠。

这些对象在 M 随波长显著增长时具有错误的复杂度。继续调 MUMPS、释放顺序或直接法参数，
不能把它变成 0.7 nm production architecture。报告要求去掉 replicated global `M^2`、
全量 `N_local×M` 常驻对象和 local direct factors，这一判断成立。

### 2.2 认可：strong trace 与 scalar-CG diagonal propagation 应保留

Review V3/V4 已分别证明：

```text
strong trace algebra / row map / Petrov flux / recovery = pass
strong trace resource advantage                         = pass
significant scalar-CG one-cell Bloch residual            = pass
projected significant off-diagonal mixing               = not observed
```

因此不得再围绕：

- trace complement；
- penalty；
- dense `R D` projector；
- M120 内部的无证据 dense matrix propagation；

继续试错。

这里的“保留”仍有范围边界：scalar-CG propagation 只在当前规则、均匀 z-chain、p1–p6、
相同 Full3D 离散合同内有证据。进入新波长、非均匀 z、曲面或新 port basis 后必须重新资格化，
不能写成全参数域永久冻结。

### 2.3 重点认可：接口位置是当前最高价值的物理闭合变量

A004-S 的 exact FE trace 投影残差为：

| z, nm | M120 exact trace residual |
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

其空间分布与“端部附近保留了被 M120 截断的 evanescent / boundary-layer content，进入
z-invariant interior 后迅速衰减”的解释一致。

这不是 actual Hybrid pass，但它比继续增加 M、修改传播或扫描角度更有判别力。现有
`build_hybrid_local_mesh(...)` 已接受显式 bottom/top interface，因此下一步主要是解除
Task-local runner 的冻结接口，而不是重写 mesh core。

### 2.4 部分反驳：`Hybrid as the 0.7 nm main route = necessary`

该表述证据不足，原因如下：

1. 报告自身规定：若实际结构没有非零厚度的 `epsilon(x,y,z)=epsilon(x,y)` 区段，Hybrid
   必须 fail closed；因此它不可能是所有未来真实三维结构的必要路线。
2. Full3D exact-sequence h/p + static condensation + matrix-free iterative 尚未在 0.7 nm
   被证明不可行，只是均匀 Full3D 明确不可行。
3. 当前 Hybrid 尚无 production anchor，不能把一个未闭合的研究路径提前定义为唯一产品。

正确定位应为：

```text
Hybrid = strategic high-upside route for geometries with a sufficiently long
         z-invariant interior
Full3D iterative = near-term production baseline and universal fallback
```

两条路线共享：

- assembly-time static condensation；
- H(curl)/trace-aware local preconditioner；
- exact-sequence active-space；
- memory / residual / 59-goal contracts。

因此推进 Full3D iterative 不是与 Hybrid 竞争的重复投资，而是在建设 Hybrid 必需的 local
endcap kernel。

### 2.5 部分反驳：`M≈16,029/方向` 不能作为严格 lower bound

`2πL_xL_y/λ²` 可以作为包含双偏振的横向 phase-space 量级估算，用来证明 M120 不可能
机械迁移到 0.7 nm，也足以暴露 replicated `M²` 风险。

但它依赖：

- 折射率与材料分布；
- cutoff 定义；
- 极化计数；
- patterned cross-section 的实际 spectrum；
- 目标误差所需的 evanescent buffer；
- 可利用的 symmetry / degeneracy。

所以文档后续应统一写：

```text
order-of-magnitude propagating-channel estimate
not a certified modal count or rigorous lower bound
```

正式 M 只能由 wavelength-specific spectrum、port residual、evanescent tail 和目标量闭合
共同决定。

### 2.6 需要修正：单个 `z=30/90` 失败后不能立刻跳新 port architecture

`z=30/90` 是“最靠外且双侧首次通过 `1e-8`”的候选，但 margin 不均衡：

```text
bottom z=30 : 2.88e-9
 top   z=90 : 8.69e-9
```

特别是 top 侧只比 Gate 小约 15%。一个 actual Hybrid 的 weak-channel 或 energy failure
可能只是这一安全余量不够，而不是 physical QEP family 已经失败。

已有 exact trace 同时给出了更深候选：

```text
bottom z=40 : 8.85e-11
 top   z=80 : 3.72e-10
```

因此 interface route 允许一个严格有界的两级测试：

```text
P0a = z=30/90  minimal-buffer candidate
P0b = z=40/80  safety-margin candidate, conditional only
```

不得扫描 `20/100, 25/95, 30/90, ...` 一长串阈值，也不得在看到结果后反复移动接口。

---

## 3. 下一轮唯一主线：bounded asymptotic-interface closure

### 3.1 总体边界

```text
new campaign / state machine / evidence framework = forbidden
new QEP / optimal-port architecture              = forbidden in this batch
M240 / M480 / M492                                = forbidden
226-point scan                                     = paused
strong-trace formulation changes                  = forbidden
ordinary default                                   = unchanged
master merge                                       = not authorized
maximum new actual Hybrid anchors before review   = 2 for A004-S
```

允许：

- 解除 explicit interface 参数的 Task-local Gate；
- 修复由非默认接口暴露的真实 row-map / phase-length / local-mesh bug；
- 增加最小的 interface identity 和 material-invariance检查；
- 复用现有 strong-trace solver、Full3D authority和后处理。

### 3.2 Phase I0：纯离线与 assemble-only preflight

不得先运行重型 PDE。先完成：

1. 验证候选 modal middle 内逐层材料标签完全一致：

   ```text
   epsilon(x,y,z) = epsilon(x,y)
   ```

   对 `30/90` 和 `40/80` 分别报告；若不满足，候选无效，不得运行。

2. 验证 bottom/top interface 都是实际 mesh plane，x/y trace grid 与 cross-section完全匹配。
3. 验证 modal length、forward/backward scalar-CG cell count、traction beta和field recovery均
   使用新的 interface位置，禁止仍隐含 `10/110`。
4. 对两个候选给出无需 factorization 的结构预估：

   - local z cells；
   - retained rows；
   - strong square rows；
   - matrix NNZ preflight；
   - modal middle length；
   - 与 Full3D rows/NNZ 比。

5. 从已有 exact trace authority生成冻结表：

   ```text
   candidate
   bottom/top residual
   safety factor to 1e-8
   local total thickness
   remaining modal-middle thickness
   ```

不得为这一步重跑 Full3D。

### 3.3 Phase I1：A004-S P0a，`z=30/90 nm`

固定：

```text
point          = A004-S
p/h/Ny         = p5 / h10 / Ny4
polarization   = S
grazing/phi    = 0.5° / 45°
M              = 120 per direction
backend        = assembly-time static condensation
coupling       = strong trace
MPI            = 8
interfaces     = 30 / 90 nm
```

复用现有 same-input Full3D authority，不重跑 Full3D，除非 hash-bound input identity
无法闭合。

必须报告：

- rows、matrix NNZ、factor NNZ、fill；
- simultaneous RSS/PSS/USS/swap；
- true residual四分量；
- `D R-I`、strong trace identity、Petrov traction；
- R00、R/T/Aclosure/Avolume、energy identity；
- 全部96个fixed channels；
- 与 old `10/110` strong-trace结果逐项差；
- exact interface residual与actual channel error是否一致。

#### P0a接受 Gate

```text
96/96 fixed channels                           pass
abs(R+T+A_volume-1)                           <= 1e-5
max abs(Delta R/T/A_volume vs Full3D)          <= 1e-4
reduced true residual                          <= 1e-9
strong trace identity                          <= 1e-10
Petrov traction                                <= 1e-8
external DtN / noninterface residual           <= existing Gate
zero swap                                      true
whole-job peak                                 <= 0.85 * Full3D peak
```

若全部通过，P0a成为 `ASYMPTOTIC_INTERFACE_CLOSURE_PASS`，不运行P0b。

### 3.4 Phase I2：P0b 的唯一授权条件

只有 P0a 数值未通过，且同时满足以下条件，才允许运行 `z=40/80 nm`：

1. strong-trace、Petrov、linear residual、Floquet和DtN全部通过；
2. 失败集中在energy / fixed channels，而不是矩阵或恢复实现；
3. P0a相对`10/110`已表现出方向性改善，或actual interface diagnostic仍显示端点margin不足；
4. assemble-only preflight表明P0b不会明显超过Full3D资源；
5. 没有出现与interface位置无关的新共同根因。

P0b使用与P0a完全相同的Gate。

若P0b通过，记录：

```text
functional interface buffer = 40/80 nm for A004-S development anchor
```

但不得外推到P偏振、其他角度或其他波长。

若P0b仍失败，正式关闭当前physical-QEP M120 + interface-placement路线：

```text
CURRENT_PHYSICAL_QEP_PORT_SPACE_NOT_PRODUCTION_ROBUST
```

此时不得继续移动接口、增大M或修改strong trace。

---

## 4. A004-S 通过后的有限扩展

只有P0a或P0b通过后，才允许：

1. A049-P：10°/90°/P；
2. A001-P：0.5°/0°/P。

对每个P点：

- 先使用A004已通过的interface作为第一个candidate；
- 不得默认P与S具有相同buffer需求；
- 若失败，只允许离线/现有场证据判断是否属于interface representability；
- 未经新Review，不得为每个P点再开启多级interface扫描。

三个p5 anchors全部通过后，才运行一个p6/h10 59-goal strong-trace authority，随后停止
所有direct Hybrid物理扫描。

---

## 5. physical closure之后的架构顺序

只有上述三个anchor和p6 authority通过后，才进入readiness assessment提出的长期架构：

```text
P2 distributed / streamed modal core
→ P3 matrix-free strong-trace Hybrid FGMRES
→ P4 local exact-sequence h/p endcaps
→ P5 wavelength continuation
```

其中：

- modal ownership必须分布式；
-禁止replicated global `M²`；
-禁止all-mode dense multi-RHS；
- QEP/eigenvectors、trace action和field recovery按mode block流式；
- local endcap solver先在Full3D static-condensed iterative中资格化，再作为Hybrid block PC；
- 13.5 nm direct只作为physical/algebra authority，不作为0.7 nm计算架构。

---

## 6. Full3D iterative 不得再被延期

无论P0结果如何，下一个独立production任务都必须建立：

```text
Full3D assembly-time static condensation
+ FGMRES
+ H(curl)/trace-aware preconditioner
```

原因：

1. 它为没有z-invariant middle的真实结构提供fallback；
2. 它是Hybrid上下endcap的local solver/PC基础；
3. 它提供matrix-free、Krylov内存和预条件器实测，避免Hybrid架构先写后测；
4. 当前Task036不应继续无限串行阻塞迭代法主线。

本Review允许先完成最多两个A004-S interface anchors，然后Task036必须停止。不得在同一分支
继续开发distributed modal core或FGMRES。

---

## 7. 需要Codex修订的文档口径

完成下一轮后，Codex必须同步修订：

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/
  hybrid_production_readiness_assessment.md
  one_cell_discrete_bloch_audit.md
  strong_trace_hybrid_anchor_results.md
```

其中必须把：

```text
Hybrid as the 0.7 nm main route = necessary_and_credible
```

改为：

```text
Hybrid for 0.7 nm = strategic_conditional_route
condition = sufficiently long z-invariant interior + qualified port space
```

并把`M≈16,029/方向`统一标为：

```text
phase-space order-of-magnitude estimate
not a certified modal count or rigorous lower bound
```

不得删除原controlled negatives或把interface预选写成actual pass。

---

## 8. 最终Response要求

本轮结束前必须创建：

```text
docs/task036_forward_solver_bugfix_hardening/response_v5.md
```

Response必须用通俗语言回答：

1. readiness assessment哪些结论被认可，哪些被修正；
2. 为什么接口位置现在优先于增加M或更换传播；
3. `30/90`和条件性`40/80`实际运行了什么；
4. 每个candidate的96通道、energy、R/T/A和内存结果；
5. Hybrid是否在A004-S获得physical closure；
6. 若成功，下一P点是什么；若失败，哪条Hybrid路线正式关闭；
7. 为什么Full3D iterative仍必须进入下一独立任务；
8. 哪些代码值得保留，哪些仍是research-only；
9. 最终HEAD、修改文件、测试、PDE、工作树和远程同步状态。

最终聊天回复必须引用`response_v5.md`路径，不得只报告“已完成”。

---

## 9. 停止条件

任一条件满足立即停止Task036本轮：

1. P0a通过；
2. P0a失败且P0b不满足授权条件；
3. P0b完成，无论通过或失败；
4. 非默认接口暴露需要重写mesh/QEP/solverframework；
5. 候选modal interval不满足严格z-invariant material条件；
6. 需要增加M、罚项或新port basis才能继续；
7. 出现OOM、swap或无法解释的数值Gate失败。

停止后只提交结果、文档和必要的最小接口参数修复。不得恢复226点扫描，不得自行merge
master，不得在本分支开始Full3D iterative。
