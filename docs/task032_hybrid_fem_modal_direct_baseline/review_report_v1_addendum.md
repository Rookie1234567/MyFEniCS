# REVIEW REPORT V1 ADDENDUM：真实复杂端部、M 的含义与 1 TB 可行性修正

## 0. 本补充的身份

```text
review = Task032 review_report_v1_addendum
parent_review = review_report_v1.md
branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
status = mandatory clarification before Codex response
supersedes = review_report_v1 sections 6, 7 and the pure-modal-first part of section 12
formal h5/h3 rerun required = no
h2 or 0.7 nm run required = no
```

本补充根据用户对未来真实服务结构的进一步说明，修正原审阅报告中的路线判断。未来目标不是当前规则 benchmark 的最简求解，而是：

```text
bottom complex 3D FEM region
+ middle z-invariant modal region
+ top complex 3D FEM region
```

未来 `z=0` 和 `z=120 nm` 附近可能存在曲边、圆角、任意三维材料分布和更复杂几何。因此，上下两部分精确三维 Nédélec FEM 是方法设计中的必要能力，不是应被 pure-modal 路线删除的临时冗余。

---

# 1. 对原 Review V1 第 6–7 节的修正

## 1.1 y 不变性不能作为未来主路线假设

当前 Case080 恰好满足 `grating_width_y = period_y`，但这是测试阶段为了先证明 Hybrid 方法而选择的简单结构。未来服务结构可能依赖完整 `(x,y,z)`，至少上下复杂区域会破坏 y 不变性，中间区域也只能冻结为：

$$
\varepsilon(x,y,z)=\varepsilon(x,y),
$$

不能进一步假设：

$$
\varepsilon(x,y)=\varepsilon(x).
$$

因此：

| 原建议 | 修正决定 |
|---|---|
| y-invariant / 单 harmonic sector 作为下一主线 | **撤回，不作为未来服务路线 Gate** |
| generic 2D cross-section QEP | **继续保留，是真实目标所需通用能力** |
| y-sector 分块 | 只允许作为当前规则 benchmark 的可选诊断或性能对照 |
| 用 y 对称性预测 0.7 nm 模态数只有数百 | **不得用于未来资源预算** |

## 1.2 pure-modal 不能替代未来 Hybrid

对当前完全规则的测试结构，pure-modal/EME 可以构造独立参考，但未来 `z=0`、`z=120 nm` 两端不是平面截面，无法仅用少数平面间的模式匹配完整描述。

因此：

```text
pure-modal = optional benchmark/reference for the current simple geometry
Hybrid FEM–Modal = retained target architecture for future complex geometry
```

Codex 不再被要求把 pure-modal solver 作为下一 Task 的 P0。若以后实现，只能作为：

- 当前规则结构的独立 reference；
- Hybrid 接口符号和模态截断的对照；
- 不改变未来保留上下精确 3D FEM 的路线。

---

# 2. M 到底是什么

Task032 中的 `M` 是：

> **中间 z 不变区域在每一个传播方向上保留的二维截面 Maxwell 本征模数量。**

当前 unknown convention 为：

```text
M forward modes  : a_b+
M backward modes : a_t-
total internal modal amplitudes = 2M
```

所以当前 `M=160` 表示：

```text
forward retained modes  = 160
backward retained modes = 160
internal modal unknowns = 320
```

`M` 不是：

- 三维网格数量；
- 二维截面自由度数量；
- 外部上下端口的 80 个 Fourier-DtN auxiliary unknown；
- 固定后永远不变的物理常数。

它是一个模态截断参数，包含传播模以及为表示接口近场所需的衰减模。它必须随波长、角度、材料、接口位置和几何重新做截断收敛。

## 2.1 M 增大时哪些对象增长

| 对象 | 当前规模 | 随 M 的增长 |
|---|---:|---:|
| forward/backward modal amplitudes | `2M` | `O(M)` |
| right/left mode vectors | `N_xy x M` | `O(N_xy M)` |
| interface projection / traction | `N_interface x M` | `O(N_interface M)` |
| augmented total rows | `N_bottom + N_top + 2M` | `O(M)` 增量 |
| modal constraint / Modal-Schur | `(2M) x (2M)` | `O(M^2)` |
| current dense multi-RHS | `N_local x (2M+1)` | `O(N_local M)` |
| current QEP candidate count | approximately `2M` per target branch | 至少 `O(M)` eigenpairs |

因此，M 越大，系统确实越大。但在当前 h3/M160 中，`2M=320` 相对于约 68,476 个上下局部 unknown 仍很小；目前矩阵行数的主要来源是 local 3D FEM。到了 0.7 nm，若 M 增长到数千或数万，显式模态存储、稠密 Modal-Schur 和全量 multi-RHS 才会成为同等甚至更严重的瓶颈。

## 2.2 M 不能只追求越大越好

正确策略是：

```text
从较小 M 开始
→ 检查 R/T/A、显著衍射级复振幅、接口 residual
→ 增加 M
→ 达到截断 Gate 后停止
```

当前主点从 M20/M40 继续到 M120/M160 才形成可信平台；`M=160` 只资格化当前 13.5 nm、10° grazing、S 主点，不得直接用于 0.7 nm 预算。

---

# 3. Hybrid 与 full 3D 的系统规模对比

Codex 必须在重写后的 `outcomes/summary.md` 和 0.7 nm scalability report 中加入以下类型的对比表。至少同时列出 FE DoF、外部 auxiliary、内部 modal unknown、总矩阵 rows、assembled NNZ、矩阵缩减倍数、R/T/A 误差和内存口径。

## 3.1 当前已有的精确 rows/NNZ 对比

| mesh | 方法 | Nédélec/local unknown 身份 | external aux | internal modal | total matrix rows | assembled NNZ | 数据身份 |
|---|---|---:|---:|---:|---:|---:|---|
| h5 | full 3D | 44,698 Nédélec | 80 | 0 | 44,778 | 4,896,156 | measured clean record |
| h5 | Hybrid augmented, M160 | bottom/top systems 6,866 + 6,866 rows | included 40+40 in local rows | 320 | 14,052 | 2,000,624 | measured clean record |
| h3 | full 3D | 198,438 Nédélec | 80 | 0 | 198,518 | 21,317,860 | measured clean record |
| h3 | Hybrid augmented, M160 | bottom/top systems 34,238 + 34,238 rows | included 40+40 in local rows | 320 | 68,796 | 8,594,673 | measured clean record |

## 3.2 缩减比例

| mesh | rows full/Hybrid | rows reduction | NNZ full/Hybrid | NNZ reduction |
|---|---:|---:|---:|---:|
| h5 | 3.187x | 68.62% | 2.447x | 59.14% |
| h3 | 2.886x | 65.35% | 2.480x | 59.68% |

这张表证明 Hybrid 已经产生真实的代数规模下降，而不仅是物理域概念变化。

但必须同时解释：

- Hybrid 还增加二维 QEP、左右模式、接口 projection 和模式重构成本；
- 总时间不一定按 rows/NNZ 同比例下降；
- full-3D 与 Hybrid 现有内存记录不是全部采用同一种 simultaneous RSS sampler，不能直接计算精确内存下降百分比；
- 如果需要精确内存 A/B，可把同 sampler full-3D h5/h3 作为 P1，不阻塞本次 response。

## 3.3 summary 中还应增加的规模项

Codex 必须补充：

```text
full 3D cells / local Hybrid cells
full 3D FE DoF / bottom FE DoF / top FE DoF
external Fourier-DtN unknowns
M per direction / total 2M modal unknowns
QEP full/reduced DoF
interface trace DoF
assembled rows and NNZ
local LU factor NNZ
projection/traction NNZ
modal Schur bytes
multi-RHS bytes
```

未被 record 直接给出的量必须标为 `derived`，不能标为 measured。

---

# 4. 1 TB 内存下，Hybrid + 迭代法是否有机会计算 0.7 nm

## 4.1 结论

```text
current direct Hybrid at 0.7 nm = no
uniform 0.1 nm Hybrid + current Task31-style iterative = probably no
Hybrid + h/p/adaptive reduction + low-storage matrix-free iterative
       + scalable modal core = credible but high-risk opportunity within 1 TB
```

因此答案不是“肯定可以”，也不是“肯定不行”，而是：

> **存在一条工程上可信的 1 TB 路线，但必须同时把 local 3D unknown 数和每 DoF 内存压到目标区间，并重构当前显式 modal core。**

## 4.2 local 3D unknown 数量级

当前 h3 Hybrid 两个 local systems 总 rows 约 68,476（不含 320 internal modes）。若保持当前总 local 厚度 40 nm，均匀从 h=3 nm 缩到 0.1 nm，三维尺度因子为：

$$
\left(\frac{3}{0.1}\right)^3=27000,
$$

得到约：

$$
6.85\times10^4\times27000\approx1.85\times10^9
$$

local unknowns。

若未来精确三维区域确实主要为两个 10 nm 复杂端部，总 local 厚度从当前 40 nm 降至约 20 nm，则粗略减半为：

$$
N_{local}\approx9.2\times10^8.
$$

这两个数字都是 `uniform-grid derived estimate`，不是未来真实自适应 DoF。

## 4.3 单个 complex128 向量预算

| local unknowns | 1 个 complex128 vector | 20 vectors | 40 vectors |
|---:|---:|---:|---:|
| 200 million | 2.98 GiB | 59.6 GiB | 119.2 GiB |
| 300 million | 4.47 GiB | 89.4 GiB | 178.8 GiB |
| 500 million | 7.45 GiB | 149.0 GiB | 298.0 GiB |
| 920 million | 13.71 GiB | 274.2 GiB | 548.4 GiB |
| 1.85 billion | 27.57 GiB | 551.3 GiB | 1.08 TiB |

实际 FGMRES 还可能同时存 Krylov basis 和 preconditioned basis。大 restart 的 FGMRES 在数亿至十亿 DoF 下不可接受；必须采用低 restart、低存储 recycling、固定线性 PC 配合法律允许的低存储 Krylov，或其他受验证的短存储策略。

## 4.4 1 TB 的建议工程预算

不能把 1 TiB 全部给未知向量。应至少预留：

| 项目 | 建议预算 |
|---|---:|
| OS / MPI / runtime / allocator margin | 80–120 GiB |
| local mesh, DoF maps, coefficients and geometry | 80–180 GiB |
| Krylov / solution / work vectors | 100–220 GiB |
| matrix-free multilevel / Schwarz PC | 200–350 GiB |
| distributed/streamed modal core | 100–250 GiB |
| safety margin | 80–150 GiB |

这些是设计预算，不是实测结果。由此得到推荐 Gate：

| total local FE unknowns after h/p | 1 TB 判断 |
|---:|---|
| `<= 2e8` | 较有希望 |
| `2e8–3.5e8` | 可行候选区，应重点争取 |
| `3.5e8–5e8` | 高风险边界区 |
| `>5e8` | 大概率超出 1 TB 或无安全余量 |
| `~9e8` uniform estimate | 不应作为目标离散直接进入求解 |

所以 Task033/Task034 的关键目标不是只减少 20% DoF，而是把约 `9e8` 的均匀局部估计压到大约 `2e8–3.5e8`，即至少约 3–5 倍；若当前 40 nm local 厚度无法缩短，则需要更大的 5–10 倍综合压缩。

## 4.5 每 DoF 内存目标

当前 Task031 h2 profile 大约为十几 kB/DoF，不能用于 0.7 nm 外推。未来生产 Hybrid iterative 应追求：

```text
local fine operator = matrix-free
assembled global fine matrix = absent
local direct LU = absent except tiny/coarse reference
preconditioner storage target = approximately O(N)
whole-solver effective memory target = preferably <=2 kB/FE DoF,
                                       hard exploratory ceiling <=3 kB/FE DoF
```

例如 300 million DoF：

```text
2 kB/DoF -> about 559 GiB
3 kB/DoF -> about 838 GiB
```

还要给 modal core 和安全余量留内存，所以 3 kB/DoF 已非常紧张。

## 4.6 modal core 同样必须重构

即使 local FE DoF 被压缩，当前实现仍不能在 1 TB 下机械扩大 M。未来必须做到：

```text
modal rows distributed across ranks
right/left modes streamed or compressed
only necessary trace/traction data retained
no replicated dense M^2 arrays
no all-mode N_local x (2M+1) dense multi-RHS
block/streamed RHS or matrix-free Schur action
adaptive M based on output and interface residual
spectrum slicing / continuation instead of one target requesting all modes
```

只有 local FE 和 modal core 两者都通过预算，才能进入正式 0.7 nm continuation。

---

# 5. 修正后的下一步顺序

原 Review V1 中“先做 y-invariant/pure-modal 主线”的建议被本补充撤回。新的主线为：

## Task033：Hybrid local h/p adaptivity and interface-budget optimization

保留上下精确三维 FEM，完成：

```text
local 3D interior h/p adaptivity
cross-section QEP h/p accuracy
matching interface trace policy
interface position / buffer thickness trade-off
R/T/A goal-oriented robust mesh
1 TB local-DoF budget
```

第一目标：在 13.5 nm 下用 direct reference 证明，同等误差时 local DoF 至少降低 3 倍，优选 5 倍。

## Task034：Scalable generic 2D modal core

不依赖 y 不变性，针对通用 `epsilon(x,y)`：

```text
distributed modal ownership
streamed/blocked right-left modes
adaptive modal truncation
block or matrix-free projection/Schur
no replicated M^2 core
no all-mode dense multi-RHS
resource model for M at 13.5/5/2/1/0.7 nm
```

## Task035：Final Hybrid iterative solver

针对 Task033 + Task034 的最终离散：

```text
matrix-free local FEM
low-memory H(curl) multilevel/Schwarz
scalable modal/interface action
outer flexible Krylov
low-restart or validated low-storage alternative
true residual + interface continuity + official R/T/A
```

## Task036：Wavelength continuation

最后执行：

```text
13.5 -> 5 -> 2 -> 1 -> 0.7 nm
```

每一步更新材料、网格、M、modal core、PC 和 1 TB 资源 Gate；失败时停止，不直接跳到 0.7 nm。

---

# 6. 对 Codex response 的新增 P0

除 `review_report_v1.md` 原有要求外，Codex 必须关闭：

```text
P0-H acknowledge this addendum and mark original sections 6/7 superseded
P0-I remove y-invariance and pure-modal-first from mandatory roadmap
P0-J explain M precisely in summary and scalability report
P0-K add full3D vs Hybrid h5/h3 rows/NNZ/DoF comparison tables
P0-L add 1 TB local-DoF and per-DoF memory budget
P0-M keep exact bottom/top 3D FEM as future target architecture
P0-N revise next plan to Task033 adaptivity -> Task034 scalable generic modal core
     -> Task035 iterative -> Task036 wavelength continuation
```

统一最终措辞：

```text
future complex 3D ends = required
pure modal = optional simple-geometry reference only
1 TB feasibility = credible conditional opportunity, not yet demonstrated
M = retained internal cross-section modes per direction
current M160 = 320 internal modal amplitudes
current direct Hybrid at 0.7 nm = infeasible
final Hybrid with h/p + scalable modal core + iterative = retained main route
```
