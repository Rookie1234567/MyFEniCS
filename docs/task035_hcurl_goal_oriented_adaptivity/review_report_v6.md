# Task035 Review V6：高阶收敛、2 TiB 资源反推与 Task035b 拆分决定

## 1. 审查结论

```text
review_status = TASK035_RESEARCH_ACCEPTED_TASK035B_SPINOFF_AUTHORIZED
branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
branch_head_at_review = 74e21c233d501f2dc13690fd9e84769f8e82e84d
review_scope = Task035 latest adaptive evidence + COMSOL p2-p6 direct/iterative convergence
research_adaptive_mechanism = proven
actual_discrete_DWR = pass
periodic_tetra_backend = research_pass
same_degree_adaptive_vs_uniform_tetra = positive
same_error_replacement_for_strict_R00_and_R = not_yet_proven
COMSOL_high_order_R00_R_T_convergence = accepted_as_external_cross_solver_evidence
COMSOL_A_total_convergence = qualified_only_pending_definition_audit
p6_h10 = useful_low_cost_high_p_baseline_not_continuum_truth
recommended_13p5nm_full_domain_equivalent_dof = <=90000
preferred_13p5nm_full_domain_equivalent_dof = 65000_to_75000
Task035b = authorized_as_stacked_branch_from_this_review_commit
Task035_master_merge = not_authorized
```

Task035 已经完成“真实目标量驱动自适应能否在双周期 Maxwell/DtN 问题上工作”的主要科学验证。新的 COMSOL p5/p6 数据进一步改变了工程判断：当前结构的大部分区域具有很强的高阶可逼近性，未来最值得发展的路线不是低阶网格持续全域减小 `h`，而是：

```text
较粗但几何可信的高阶基线
+
目标量驱动的少量局部 h
+
真正局部的 p 保留/提升/降低
+
必要时静态凝聚或低存储迭代
```

Task035 当前分支应作为已审查的科学与证据基线保留。后续围绕“从高阶基线再压缩约 50%、建立真正 local hp、并把结果映射到 0.7 nm / 2 TiB 资源目标”的工作拆分为 Task035b。Task035b 不从 `master` 重建，而从本 Review 提交后的 Task035 完整证据树创建 stacked branch，以避免复制或丢失尚未合入 master 的 adaptive 实现和 records。

---

## 2. COMSOL p5/p6 结果是否可信

### 2.1 高阶收敛中心

p4 细网格、p5、p6，以及六面体和四面体多条序列共同指向：

```text
R(0,0) ≈ 0.000752895
R_total ≈ 0.000762014
T_total ≈ 0.6027075
A_closure = 1 - R - T ≈ 0.3965305
```

这不是由单个 `p6/h10` 点推断，而是由以下互相独立的离散结果支持：

- p4 tetra h3/h2.5；
- p4 hexa h2.5/h2；
- p5 tetra h6；
- p6 tetra h7/h8/h9；
- p6 hexa h7.5。

因此，`R(0,0)`、`R_total` 和 `T_total` 的高阶收敛趋势可信。COMSOL `A_total` 对积分域、后处理和能量残差更加敏感；跨代码和跨离散比较时，优先使用 `A_closure=1-R-T`，并把 `A_total` 单独审计。

### 2.2 p6/hexa/h10 的准确角色

`p6/hexa/h10`：

```text
DoF = 173882
R00 = 0.000753784
R = 0.000762904
T = 0.602701310
physical memory at saved-solution history = 22.75 GB
```

相对上述高阶收敛中心：

```text
|ΔR00| ≈ 8.89e-7，relative ≈ 0.118%
|ΔR|   ≈ 8.90e-7，relative ≈ 0.117%
|ΔT|   ≈ 6.19e-6，relative ≈ 0.0010%
```

所以该点是非常有价值的低成本高阶基线，但不是连续真解，也不应单独决定 Task035b 的容差。Task035b 必须先在 FEniCS/Nédélec 中重建同一趋势，并使用：

```text
FEniCS same-code high-p convergence
+
COMSOL p4-p6 cross-solver convergence center
```

双重证据冻结正式误差 Gate。

### 2.3 为什么 p6/h10 的内存仍然很高

这不是异常，也不与 DoF 减少矛盾。MUMPS 直接法内存主要由消元前沿和 factor fill 决定，不由 DoF 单独决定。

从 COMSOL 记录粗算：

```text
p4/hexa/h5:  339972 DoF, 25.49 GB  ≈ 79 KiB/DoF
p6/hexa/h10: 173882 DoF, 22.75 GB  ≈ 137 KiB/DoF
```

高阶单元会带来：

- 每个单元更多 edge/face/interior 模式；
- 每行更宽的耦合邻域；
- 更大的稠密局部块；
- 更大的消元 front；
- 更高的 factor fill；
- 更高的高阶几何、约束和后处理工作集。

因此 DoF 减少约 49%，直接法内存只减少约 11%，是可以解释的。COMSOL 报告中的内存还是保存解历史值，不是独立进程树峰值，因此只能用于相对趋势。

Task035b 必须同时优化：

```text
DoF
NNZ / average row width
factor NNZ / front size
interior-mode condensation
peak memory
```

不能只以 DoF 压缩宣称内存压缩。

---

## 3. 不规则结构是否必须全域低阶小 h

否。未来结构不规则，并不等于整个计算域都必须改成低阶、小尺寸单元。

应区分：

### 3.1 平滑曲面或缓变结构

例如圆角、平滑侧壁和连续曲面。若使用可信的高阶几何映射或曲面贴合网格，场在大部分子域仍可能光滑，高阶 `p` 仍然有效。

### 3.2 尖角、材料跳跃和局部奇异

这些区域的高阶系数衰减会变慢，单纯提高 `p` 效率下降，应局部减小 `h`，同时在远离奇异区的平滑区域保留高阶。

### 3.3 粗糙、缺陷或真正三维非规则区域

只在受影响区域增加局部网格和较低/中等 `p`；规则层、均匀介质和大部分传播区仍可使用较粗高阶离散。

因此真正目标是：

```text
smooth + goal-sensitive      -> p
singular/interface-sensitive -> h
smooth + low goal impact     -> lower p / keep coarse
```

而不是“结构一不规则，就全域退回 p2 和极小 h”。

---

## 4. 从 13.5 nm 到 0.7 nm 的 DoF 反推

令：

```text
s = 13.5 / 0.7 = 19.285714
s^3 = 7173.105
```

如果保持相同的每波长分辨率，三维体积 DoF 机械增长约 7173 倍。

Task032/034 的同网格 Hybrid 证据表明：

- h5/h3 total rows 相对 Full3D 减少约 65%–69%；
- p4/h5 local FE DoF 约为 Full3D DoF 的 0.296；
- 为覆盖接口、复杂几何和未来不规则结构，Task035b 采用：

```text
f_H = 0.30  nominal Hybrid local-volume factor
f_H = 0.35  conservative factor
f_H = 0.40  irregular-geometry stress factor
```

13.5 nm 的 Full3D-equivalent DoF 与 0.7 nm local-3D FE DoF 的规划关系为：

```text
N_local,0.7 ≈ N_equiv,13.5 × 7173.105 × f_H
```

| 13.5 nm Full3D-equivalent DoF | 0.7 nm local FE，f=0.30 | f=0.35 | f=0.40 |
|---:|---:|---:|---:|
| 173,882（COMSOL p6/h10） | 374 M | 437 M | 499 M |
| 129,005（Task035 h37.5 adaptive p5） | 278 M | 324 M | 370 M |
| 90,000 | 194 M | 226 M | 258 M |
| 86,941（p6/h10 再压缩 50%） | 187 M | 218 M | 249 M |
| 70,000 | 151 M | 176 M | 201 M |

这给出清晰结论：

> 以 `p6/h10` 的 173,882 DoF 为新高阶基线，再做约 50% 的同误差压缩，得到约 86,941 DoF，正好落入 Task032 提出的 0.7 nm `200M FE DoF preferred / 200M–350M candidate` 区域。

所以“在 p6/h10 基础上继续压缩 50%”是现实而有意义的 **stretch engineering target**，不是随意数字。

---

## 5. 2 TiB 内存下的合理 13.5 nm 目标

Task032 的条件资源模型使用：

```text
2 kB/DoF = preferred low-storage envelope
3 kB/DoF = hard exploratory envelope
```

这些不是当前代码已经实现的测量值，而是 matrix-free / low-storage iterative 的设计区间。

若 13.5 nm 压缩到 86,941 DoF：

| Hybrid factor | 0.7 nm local FE DoF | 2 kB/DoF | 3 kB/DoF |
|---:|---:|---:|---:|
| 0.30 | 187 M | 349 GiB | 523 GiB |
| 0.35 | 218 M | 407 GiB | 610 GiB |
| 0.40 | 249 M | 465 GiB | 697 GiB |

2 TiB 总内存还必须容纳：

- mesh、geometry、coefficients；
- Krylov 和 solution vectors；
- multilevel/Schwarz preconditioner；
- distributed/streamed modal core；
- QEP、interface trace 和 M/DtN 数据；
- runtime、allocator 和 safety margin。

因此 Task035b 采用三级目标：

```text
minimum engineering target:
    N_equiv,13.5 <= 90000

preferred robust target:
    N_equiv,13.5 = 65000–75000

stretch target:
    <=60000, only if all physics and independent error gates pass
```

解释：

- `<=90k` 对当前规则几何和 nominal Hybrid factor 可映射到约 200M local FE；
- `65k–75k` 为未来不规则几何、modal core 和预条件器保留更大余量；
- 相对 p4/h5 的 339,972 DoF，90k 是约 3.78x 压缩，70k 是约 4.86x 压缩；
- 相对 p6/h10 的 173,882 DoF，90k 是约 1.93x，70k 是约 2.48x。

因此用户提出的“p6/h10 再压缩 50%”与最低工程目标基本一致；为了未来不规则结构，Task035b 的优选目标应更接近 65k–75k。

---

## 6. Hybrid、迭代与 hp 的贡献如何组合

不能简单把所有百分比相乘后当作实测峰值，但可用于规划。

### 6.1 高阶 global-p 已测信号

```text
p4/hexa/h5: 339972 DoF
p6/hexa/h10: 173882 DoF
```

约 1.96x DoF 降维，且 R/T 接近高阶收敛中心。

### 6.2 Task035 adaptive 已测信号

```text
p4/h5 reference: 339892 DoF
h37.5 tetra p5 one-cycle DWR: 129005 DoF
```

约 2.63x DoF 降维，完整 R/T/A vector 很好，但 strict R/R00 尚未完成同误差替代。

### 6.3 Hybrid 已测信号

13.5 nm 同网格结果显示：

```text
Full3D -> Hybrid total rows reduction ≈ 65%–69%
local FE fraction ≈ 0.30
```

Hybrid 是 0.7 nm 主路线的必要降维，但会把复杂度转移到 QEP、M、interface 和 modal Schur。

### 6.4 当前迭代法已测信号

COMSOL 二阶 matched-grid 结果中：

```text
tetra h1.5: direct 114.95 GB -> GMRES+GMG 64.47 GB, about 1.78x reduction
hexa h1.0:  direct 138.22 GB -> GMRES+GMG 78.27 GB, about 1.77x reduction
```

这证明迭代路线可以降低内存，但当前 assembled GMRES+一层 GMG 仍远未达到 2–3 kB/DoF 的最终目标。0.7 nm 需要 matrix-free / partial assembly、H(curl) multilevel/auxiliary-space、低 restart 和分布式 coarse space。

### 6.5 modal core 仍是独立硬门槛

Task034 0.7 nm current-layout stress test 中，replicated dense `M²`、all-mode RHS 和显式 mode vectors 均会超过 2 TiB。即使 local FE 压缩成功，也必须实现：

- distributed/streamed modes；
- no replicated dense `M²`；
- blocked/streamed Schur action；
- adaptive M / spectrum slicing；
- 生命周期 overlap 和 simultaneous peak 测量。

因此 Task035b 只负责把 local FE DoF 推入可行区，不宣称单独解决 0.7 nm。

---

## 7. Task035b 的科学重点

Task035b 不再从低阶粗网格开始做多轮 h-refinement。优先路线改为：

```text
可信 global-p5/p6 coarse baseline
→ high-order mode / goal sensitivity audit
→ 从准确的高阶空间删除不重要高阶模式
→ 在尖角/界面局部 h-refine
→ 只在 smooth + goal-sensitive 区域保留或提升 p
→ 与 global-p6 和 uniform controls 做 same-error 比较
```

### 7.1 为什么从 p6 向下压缩

从准确的 global-p6 起点做 p-coarsening，比从 p4 起点不断猜测哪里需要升 p 更容易建立 fail-closed 精度：

- 初始解已经接近收敛；
- 删除模式前后可直接测量目标量变化；
- DWR 可判断高阶模式对 R00/R/T 的作用；
- 低影响区域可降到 p4/p5；
- 尖角和界面可改用局部 h，而不是全域 p6。

### 7.2 不能只在 max-p 空间中把系数设零

若“局部降 p”只是在全局 p6 矩阵中把部分系数强制为零，而这些行列、耦合和消元 front 仍被装配，可能减少有效未知量但不减少内存。正式成功必须物理删除或凝聚不活跃模式，并实测：

```text
active rows
NNZ
factor NNZ / fill
peak memory
wall time
```

### 7.3 静态凝聚值得并行评估

高阶单元的大量 interior modes 可局部消元。Task035b 应审计：

- edge / face / interior DoF inventory；
- element-interior static condensation；
- condensed trace system rows 和 fill；
- 与 variable-p / local hp 的兼容性。

该路线可能比单纯减少总 DoF 更直接地解决 p6 直接法内存高的问题。

---

## 8. 分支与交付决定

创建 stacked branch：

```text
codex/20260723-task35b-high-order-local-hp-resource-envelope
```

基线必须是包含本 Review V6 的 Task035 branch HEAD，不是 `master`。原因：

- Task035 adaptive、DWR、periodic tetra、p5/p6 Floquet 和 records 尚未合入 master；
- Task035b 直接依赖这些实现；
- 从 master 新建会导致重复移植和证据断裂。

约束：

- Task035b 不得 merge master；
- Task035b 最终不能独立于 Task035 合并；
- 最终 selective merge 必须把 Task035 和 Task035b 的依赖关系统一审查；
- Task035 原分支保留为冻结审查基线，不再继续无关重型参数扫描。

Task035b 的正式任务书位于：

```text
docs/task035b_high_order_local_hp_resource_envelope/task.md
```

---

## 9. 本 Review 后的准确状态

```text
Task035 scientific question:
    true goal-oriented adaptivity can work = answered yes

Task035 engineering question:
    current adaptive tetra is universally best = answered no

new high-order evidence:
    global high-p coarse mesh is a first-class baseline = yes

50% compression beyond p6/h10:
    realistic stretch target for current geometry = yes
    guaranteed for future irregular geometry = no

preferred 13.5 nm equivalent DoF for 0.7 nm / 2 TiB planning:
    65k–75k

minimum engineering target:
    <=90k

remaining independent requirements:
    low-storage iterative + scalable modal core + wavelength continuation

master merge:
    not authorized
```
