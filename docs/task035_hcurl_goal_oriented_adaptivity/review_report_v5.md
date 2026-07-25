# Task035 Review V5：当前自适应结果解释与下一步 hp 精度恢复路线

## 1. 审查结论

```text
review_status = RESULTS_ACCEPTED_WITH_QUALIFICATIONS_CONTINUE_HP_ACCURACY_RECOVERY
branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
branch_head_at_review = 5a15ae50ab7b642e22742e5c081fc035e33ba493
execution_mode = continuous_autonomous_research
actual_global_R5 = mechanism_pass_but_cost_efficiency_negative
actual_discrete_DWR = pass
periodic_tetra_backend = research_pass
selected_research_strategy_10deg = p4_p5_R_total_DWR_theta0p7_one_h_cycle
current_adaptivity_class = quasi_hp_global_p_pair_plus_local_h_refinement
true_cellwise_hp = not_yet_implemented
mesh_coarsening = not_yet_implemented
same_error_replacement_of_structured_p4_h7p5 = not_yet_achieved
production_estimator_selected = false
production_backend_selected = false
ordinary_default_changed = false
master_merge = not_authorized
continuous_research_after_this_review = authorized
```

本轮审查接受 Task035 已完成的真实 Maxwell/DtN 正问题、离散伴随、目标量驱动 DWR、周期四面体局部细化、高阶 p4/p5/p6、MPI8、资源监测和均匀/结构化对照结果。

Task035 已经证明：

```text
1. 双周期 tetra target pipeline 可以局部细化并重新求解；
2. actual R5 与 actual DWR 都可以在目标 Maxwell 系统上计算；
3. DWR marking 可以在同阶 tetra 对照下产生明确正收益；
4. 高阶起点 + 一次局部 h 细化优于低阶起点 + 多轮 h 细化；
5. 第二轮或更多 h 细化容易被周期 closure、DoF、fill 和内存增长抵消；
6. 当前自适应尚未在严格 same-error 条件下替代 structured p4/h7.5。
```

因此，当前工作不是失败，也不是已经完成 production hp adaptivity。准确状态是：

```text
research adaptive mechanism = proven
research DWR marking benefit = proven against same-degree uniform tetra
strict engineering replacement = not yet proven
```

Codex 继续采用连续自主研究模式，不因本 Review 停止等待。后续重点应从“继续增加 h-refinement 轮数”转向“初始 h、全局 p、局部 h/p 决策与多目标误差之间的合理分配”。

---

## 2. R5 与 DWR 的准确定位

### 2.1 R5

Task035 中的 `R5` 是项目内部对 hierarchical/two-level estimator 的编号，不表示五阶残差。

其核心是比较两个嵌套或近似嵌套离散空间中的解：

```text
E_coarse
与
E_enriched
```

例如：

```text
p2 与 p3
p3 与 p4
p4 与 p5
```

再将：

```text
E_enriched - E_coarse
```

的能量或场差局部化到每个 coarse cell。它回答：

> 哪些区域的低阶解和高阶解差异最大，说明场还没有被充分解析？

当前 actual global R5 已完成真实目标 PDE、owned-cell contribution、全局能量闭合、Dörfler marking、周期 closure、局部 refine 和连续重新求解。

但是，纯 R5 两轮自适应虽然收敛，在相近成本下仍被 true-uniform tetra refinement 明确击败。因此准确结论为：

```text
R5 estimator mechanism = pass
R5 field-error diagnostic = useful
pure R5 production marking = controlled negative
```

R5 仍适合作为：

- enriched correction magnitude；
- 场误差诊断；
- smoothness/hp 决策的输入；
- DWR 的独立对照。

不建议继续纯 R5 第三轮 h-refinement。

### 2.2 DWR

`DWR` 是 Dual-Weighted Residual，即伴随加权残差。

正问题为：

```text
A E = b
```

目标量可为：

```text
R_total
T_total
A_volume
R00
某个衍射级振幅或功率
```

对目标量求导后，求离散伴随问题：

```text
A^H z = dJ/dE
```

局部 DWR 指标的含义是：

```text
局部离散残差
×
该位置误差对目标量的敏感度
```

它回答：

> 哪些区域的误差最影响指定的工程输出？

当前 actual DtN adjoint、R/T gradient、adjoint true residual、cell/face localization 和 Dörfler marking 均已通过。DWR 比 R5 更适合当前问题，因为用户主要关心 R/T/A 和衍射输出，而不是要求整个场处处具有同等精度。

---

## 3. 当前结果接受范围

### 3.1 Pure R5 自适应

两轮 p2/p3 actual R5 adaptive sequence：

| cycle | cells | p2 DoF | p3 DoF | p2 fixed-ref error | p3 fixed-ref error |
|---:|---:|---:|---:|---:|---:|
| 0 | 180 | 1,470 | 4,011 | 1.202635 | 1.147343 |
| 1 | 1,308 | 9,504 | 26,730 | 1.087687 | 0.142113 |
| 2 | 8,785 | 60,330 | 172,257 | 0.195353 | 0.007041 |

该序列证明了：

- estimator-marked refine 工作；
- periodic closure 工作；
- tetra tag/Floquet/DtN rebuild 工作；
- fixed-reference error 连续下降；
- true residual 和 no-swap Gate 通过。

但 true-uniform level2 为：

| route | cells | p2/p3 DoF | p2/p3 error | peak GiB | wall s |
|---|---:|---:|---:|---:|---:|
| R5 adaptive cycle2 | 8,785 | 60,330 / 172,257 | 0.195353 / 0.007041 | 6.401 | 295.96 |
| uniform level2 | 11,520 | 78,000 / 223,656 | 0.010697 / 0.001227 | 8.473 | 523.44 |

R5 adaptive 节省资源，但误差显著更大。因此不继续纯 R5 marking 主线。

### 3.2 p3/p4 DWR

同阶 tetra 对照：

| route | cells | p4 DoF | observable error | peak GiB | wall s |
|---|---:|---:|---:|---:|---:|
| uniform level1 | 1,440 | 63,104 | 0.00597711 | 4.020 | 27.81 |
| DWR theta=0.5 cycle1 | 1,268 | 55,884 | 0.00460020 | 3.983 | 37.80 |

一轮 DWR 使用约 11% 更少 p4 DoF，并将误差降低约 23%，是明确的 goal-oriented marking 正结果。

第二轮 DWR 达到 315,444 p4 DoF、18.831 GiB，虽然误差继续下降，但被 structured p4/h7.5 在误差、DoF 和内存上同时支配。因此：

```text
DWR first local-h cycle = positive
DWR second local-h cycle = cost-dominated negative
```

### 3.3 p4/p5 DWR

当前选择的 research strategy：

```text
p4/p5
R_total discrete-adjoint DWR
Dörfler theta = 0.7
one full-periodic-sleeve tetra refinement
MPI8
```

同阶 tetra 对照：

| route | p5 DoF | fixed-reference error | peak GiB |
|---|---:|---:|---:|
| uniform tetra p5 | 116,120 | 0.000735191 | 8.011 |
| DWR theta=0.7 adaptive p5 | 106,355 | 0.000538286 | 8.080 |

DWR adaptive 相比同阶 uniform tetra：

- DoF 少约 8.4%；
- 误差低约 26.8%；
- 内存近似相同，其中 adaptive 还包含 adjoint；
- 所有 forward/adjoint residual、periodic、orientation、mesh-quality 和 watchdog Gate 通过。

因此：

```text
DWR marking benefit beyond global p5 = proven
```

但 structured p4/h7.5 的误差约为 `3.278e-4`，仍优于 adaptive p5 的 `5.383e-4`。当前 adaptive p5 是 Pareto tradeoff，不是 strict same-error replacement。

### 3.4 p5/p6 与 50% DoF Gate

以 structured p4/h5 的 339,892 DoF 为参考，50% DoF 上限为 169,946。

| route | DoF | DoF saving | R | R/T/A vector error | peak GiB |
|---|---:|---:|---:|---:|---:|
| structured p4/h5 reference | 339,892 | 0% | 0.0007663134 | 0 | 28.888 |
| structured p4/h7.5 | 147,844 | 56.50% | 0.0008024690 | 3.278e-4 | 12.724 |
| uniform tetra p5 | 116,120 | 65.84% | 0.0007956866 | 7.352e-4 | 8.011 |
| DWR tetra p6 theta=0.3 | 161,700 | 52.43% | 0.0008194492 | 8.089e-5 | 13.326 |
| DWR tetra p6 theta=0.4 | 167,784 | 50.64% | 0.0008176842 | 1.022e-4 | 13.994 |

p6 adaptive 的完整 `(R,T,A_volume)` 向量误差优于 structured p4/h7.5，但单独 `R` 的误差略差于 p4/h7.5 的严格 R-only control。因此：

```text
multi-observable accuracy = strong positive
strict R-only control = fail
50%-DoF plus strict-R combined gate = controlled negative
```

这说明当前“精度是否达到”的答案依赖目标定义。后续必须同时保存两类 authority，不得用一个口径覆盖另一个：

```text
A. full R/T/A normalized multi-goal accuracy
B. strict R-only accuracy audit
```

---

## 4. Uniform tetra p5 的准确网格身份

`Uniform tetra p5` 不是简单的固定 `h=50 nm`，也不能严谨地直接写成最终 `h=25 nm`。

正式运行身份为：

```text
initial nominal mesh parameter = h50
mesh cell type = tetrahedron
uniform refinement levels = 1
final cells = 1,440
coarse degree = p4
coarse DoF = 63,104
enriched degree = p5
enriched DoF = 116,120
MPI = 8
```

因此推荐名称为：

```text
h50-base + one true-uniform tetra refinement + p4/p5 solve
```

一级 tetra refinement 后，不同边界贴合单元的 edge length、cell diameter 和质量不完全一致。最终 authority 应使用：

- mesh hash；
- cell count；
- cell-diameter/volume/quality 分布；
- DoF；
- polynomial degree；
- refinement level。

不得只用一个模糊的最终 h 值表示。

---

## 5. 当前是不是 hp 自适应

当前方法准确分类为：

```text
global-p enrichment
+
local h-refinement
```

也可以称为：

```text
quasi-hp adaptivity
```

当前实际过程类似：

```text
全域 p4 解
+
全域 p5 enriched/adjoint 解
→ DWR marking
→ 部分区域进行 h-refinement
→ 新网格上再次全域 p4/p5 solve
```

或：

```text
全域 p5/p6
+
局部 h-refinement
```

它还不是严格 cellwise hp adaptivity，因为当前尚未实现：

- 每个 cell 独立的 p_K；
- p-nonconforming H(curl) interface constraints；
- local p increase/decrease；
- mesh derefinement/coarsening；
- 每个 marked cell 在 h 与 p 之间的自动选择。

当前也没有“把已经很细的区域自动粗化”。实际采用的是：

```text
从较粗网格开始
→ 只对重要区域细化
→ 其余区域保持原尺度
```

这与从细网格出发主动 coarsen 不同。

---

## 6. 下一步总体判断

用户提出的方向是合理的：

```text
先用局部 h 将计算资源集中到关键区域
→ 如果精度仍不足，优先尝试 p+1
→ 避免继续第二层、第三层大范围 h-refinement
```

当前 measured evidence 强烈支持这一方向：

- 低阶 pure h 多轮细化不高效；
- 高阶 p3/p4、p4/p5 的第一轮 DWR 有正收益；
- 第二轮 local h 的成本迅速膨胀；
- p5/p6 可以显著提高完整 R/T/A 精度；
- 真正瓶颈已从“自适应是否可做”转为“h 与 p 如何分配，以及用什么 accuracy objective 决策”。

下一步不建议继续：

- pure R5 第三轮；
- p3/p4 DWR 第二轮或第三轮；
- full-sleeve p6 的无边界 theta 扫描；
- 仅为了让单个数字变好而重复已有重型 case；
- 将 sampled R1 重新包装为 production estimator。

---

## 7. 下一步路线 1：中等初始 h + 一次 DWR h-refinement

当前 tetra 主线从名义 `h50` base 开始。该起点非常粗，导致第一轮局部 refine 同时承担：

- 修正整个背景传播离散；
- 修正材料界面；
- 修正尖角；
- 修正目标量敏感区。

第二轮又因 periodic sleeve closure 产生大量额外单元。

因此最值得尝试的下一条路线不是继续第二轮 refine，而是重新选择一个适度更细、但仍明显低于 structured p4/h7.5 成本的初始 tetra 网格，然后只做一次 DWR local-h：

```text
candidate base h ≈ 40 nm 或经 preflight 选择的邻近值
p4/p5
R_total 或 multi-goal DWR
one local-h refinement
no second h cycle
```

候选数必须受限，不进行大范围 h 扫描。建议先用 cheap mesh/DoF/NNZ preflight 选择最多两个可区分点，例如：

```text
h50 authority
h40 candidate
必要时 h35-h37.5 单一补充点
```

主判断为：

- 是否达到或优于 structured p4/h7.5 的 accuracy control；
- 是否保持至少 50% DoF 节约；
- 是否优于同阶 true-uniform tetra；
- 一次 refinement 后是否已经进入停止区间。

该路线的物理含义是：

> 让背景传播由适中的基础网格承担，让 DWR 只负责真正的局部误差，而不是让第一轮自适应承担全局欠分辨误差。

---

## 8. 下一步路线 2：固定 adaptive mesh 后全局 p+1

当前结果已经说明，提高 p 通常比继续增加 h-refinement 层数更有效。

推荐流程：

```text
选择一轮 DWR 后的最佳 periodic tetra mesh
→ 固定 mesh，不再 refine
→ p4/p5 solve
→ 若精度不足，p5/p6 solve
→ 比较 R/T/A、R-only、DoF、NNZ、内存和时间
```

这就是用户提出的：

```text
局部 h 已经把单元放到关键区域
+
精度不足时使用 p+1 补足
```

仓库已经做过若干 p5/p6 authority 和 budget points，因此下一步不得重复无目的 p6 扫描。只允许增加能够解决明确歧义的最小点：

- 固定当前 selected adaptive mesh；
- 不增加第二层 h；
- 只提高一个全局 p；
- 明确检查是否跨过 strict R 与 multi-goal 两类 Gate；
- 若 p+1 仍不能在预算内补足精度，则关闭该 mesh，不继续 p+2 盲目扩展。

---

## 9. 下一步路线 3：多目标 DWR，而不是只盯 R_total

当前 selected strategy 主要使用 `R_total` DWR。它能提高反射率目标，但可能不能在同一标记中同时最优地控制：

```text
R
T
A_volume
R00
显著衍射级
```

p6 结果已经暴露出这种口径差异：完整 R/T/A 向量很好，但 strict R-only 略差。

建议建立明确的 multi-goal policy，优先采用多个伴随场后组合 cell indicator，而不是把不同量直接以量纲不一致的方式相加：

```text
solve adjoint for R
solve adjoint for T or A_volume when independent
optional adjoint for R00/order
→ normalize each local indicator by accepted tolerance/scale
→ combine by weighted L2 or max policy
```

例如概念性地：

```text
eta_K_multi^2
=
w_R eta_K,R^2
+
w_T eta_K,T^2
+
w_A eta_K,A^2
```

权重应由工程容差或参考尺度定义，而不是为了让某个结果通过而事后调节。

下一步应先审计现有 `actual_dwr_combined_*` records 与代码：

- 已经测过的 combined lane 不得无目的重跑；
- 检查其目标归一化是否与当前 strict R / vector accuracy 双口径一致；
- 只有权重或目标定义确有缺陷时才修改并运行一个最小判别点；
- 不进行多权重网格搜索。

---

## 10. 下一步路线 4：真正的 local h/p 决策

最终理想方法不是每次统一全局 p+1，而是对每个 marked cell 决定：

```text
smooth and goal-sensitive → p-refine
nonsmooth/interface/corner → h-refine
low-impact → keep coarse；未来可考虑 coarsen
```

### 10.1 平滑性指标

可使用：

- hierarchical/modal coefficient decay；
- p4/p5/p6 correction ratio；
- local projection error；
- local patch enriched solve；
- analyticity/singularity diagnostic；
- material/interface/corner classification。

简单判断逻辑：

```text
高阶系数快速衰减：
    场在该 cell 内较光滑
    → 增加 p 更有效

高阶系数衰减慢：
    尖角、跳跃或局部奇异
    → 减小 h 更有效
```

### 10.2 实现分阶段

DOLFINx 中任意 cellwise variable-p 的 conforming H(curl) 空间与 Floquet 约束并不是现成的普通功能。直接一步实现生产级 local-p 风险很高。

推荐三步：

#### Step 1：hp classifier

先只计算每个 marked cell 的 `h_candidate` / `p_candidate` 决策，不改变全局 FE 空间。用现有 p4/p5/p6 解验证决策是否与真实 error reduction 一致。

#### Step 2：local p-enriched patch estimator

在局部 cell/edge-star patch 上做 p-enriched correction solve，用于估计“提高 p 的收益”，但正式全局 solve 仍采用统一 p。该步骤可以先改善 marking 和 h/p 选择，而不立即面对全局 variable-p constraints。

#### Step 3：regional/true local-p

只有前两步有正信号后，再研究：

- regional p blocks；
- p-nonconforming H(curl) constraints；
- hierarchical basis；
- static condensation/hybridization；
- cellwise variable-p；
- p interface orientation/Floquet qualification。

不要让最复杂的 variable-p infrastructure 阻塞当前可行的 quasi-hp 路线。

---

## 11. 下一步路线 5：coarsening 的位置

用户提出“部分地方粗化”在最终 hp 系统中是合理目标，但当前 Task035 没有实现 derefinement。

真正 coarsening 需要：

- 保留 parent/child refinement forest；
- 周期 master/slave 同步 derefine；
- 材料界面和 DtN 面不得被错误合并；
- Floquet trace topology 保持同构；
- field restriction/projection；
- coarsen 后重新检查 residual 和 official observables；
- 防止 refinement/coarsening 来回振荡。

当前优先级应低于：

```text
一次 local h
+
全局 p continuation
+
hp classifier
```

原因是当前起点本身很粗，主要问题不是“已有太多不必要细单元”，而是如何在第一次 refined mesh 上得到足够精度。

只有后续从较细初始网格或多轮自适应出发，才有必要引入 coarsening。

---

## 12. 推荐的有限实验矩阵

为避免再次出现无边界试验，下一轮最多同时维护：

```text
2 条主 lane
+
1 条 control/audit lane
```

### Main lane A：one-shot h + global p

```text
moderately finer tetra base
p4/p5 DWR
one local-h cycle
then fixed-mesh p5/p6
```

### Main lane B：multi-goal DWR

```text
current best base or mesh
R/T/A normalized multi-goal DWR
one local-h cycle
optional fixed-mesh p+1
```

### Control lane

```text
same-degree true-uniform tetra
+
structured p4/h7.5 authority
```

只有在以下正信号出现时扩大：

- strict R 或 normalized R/T/A accuracy 明显接近/优于 control；
- 至少 50% DoF 节约保持；
- 同阶 adaptive 优于 uniform；
- p+1 比第二轮 h 明显高效；
- periodic/Floquet/Jacobian/MPI 和 residual 全部通过。

负信号出现时关闭 lane：

- p+1 后仍不能达到 accuracy control；
- h 更细只增加成本而不改善目标；
- multi-goal 只是在指标间转移误差；
- periodic sleeve overhead 再次吞噬局部性；
- factor fill 或内存抵消 DoF 节约。

---

## 13. 建议的自动决策树

```text
START
|
|-- Build moderately finer tetra base candidate
|-- Run p4/p5 + one DWR local-h cycle
|
|-- Does it meet strict-R and normalized-RTA accuracy under DoF budget?
|       |
|       |-- YES:
|       |     compare against uniform and structured authority
|       |     if cost positive → engineering candidate
|       |
|       |-- NO:
|             keep mesh fixed and run p5/p6 once
|             |
|             |-- Gate reached under budget?
|             |       |-- YES → quasi-hp candidate
|             |       |-- NO  → close this mesh/base
|
|-- In parallel audit multi-goal DWR
|       |
|       |-- positive → compare one-shot h + p continuation
|       |-- negative → preserve evidence and close
|
|-- If quasi-hp works but still wastes cells:
|       build hp classifier / local patch p estimator
|
|-- If all adaptive lanes fail strict same-error:
|       keep structured p4/h7.5 as engineering authority
|       report adaptive as Pareto/research capability
```

---

## 14. 测试与资源要求

继续采用 continuous autonomous research，不因单个步骤完成而停下等待。

测试节奏：

```text
small implementation change:
    targeted unit/fixture tests

one estimator/hp/backend lane closeout:
    serial + MPI2；high-order formal point uses MPI8 when justified

production numerical core change:
    corresponding accepted anchor/regression

major milestone or final merge preparation:
    full repository pytest
```

当前 HEAD 尚缺一次修复 classifier 后的完整 full repository regression。下一重大里程碑或最终 merge 前必须在正确 complex activation 下运行一次 full pytest；不得把 targeted recovery 表述成当前 HEAD full-regression pass。

Heavy run：

- one-heavy-case-at-a-time；
- clean committed source SHA；
- rows/NNZ/memory/swap/disk/OOC preflight；
- watchdog 和完整进程组终止；
- 不设置任意短 timeout；
- 不做无证据参数遍历；
- 不删除失败或 controlled-negative records。

---

## 15. 最终建议

当前最合理的技术判断不是“继续提高 h 精度”或“继续提高 p”二选一，而是：

```text
适中的背景 h
+
一次 DWR 局部 h-refinement
+
固定 adaptive mesh 后 global p+1
+
逐步引入 local h/p classifier
```

对当前固定结构、13.5 nm、S、10° grazing，短期最有希望达到严格精度并保持资源优势的路线是：

```text
moderately finer tetra base
→ p4/p5 multi-goal or R-total DWR
→ exactly one local-h cycle
→ fixed-mesh p5/p6 accuracy recovery
→ compare against true-uniform tetra and structured p4/h7.5
```

中期再升级为：

```text
DWR marking
+
hierarchical smoothness indicator
+
cell/patch h-vs-p decision
```

当前不应将 Task035 宣称为完整 true-hp production solver，但可以准确宣称：

```text
actual goal-oriented DWR adaptivity works;
periodic high-order tetra local refinement works;
one-shot high-order h-adaptivity beats same-degree uniform tetra;
the remaining problem is strict accuracy recovery and optimal h/p allocation.
```

Codex 可依据本 Review 继续自主执行上述路线，不需要逐阶段等待审查。只有准备改变 ordinary default、合并 master、需要用户凭据/系统操作、或所有合理路线均形成可审计负结论时才停止。
