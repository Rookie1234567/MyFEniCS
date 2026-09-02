# Task038-extra 参考边界：截至 Review V16 的只读物理求解启示

## 1. 来源、快照与用途

```text
reference branch = codex/20260820-task38-extra-full3d-iterative-0p7nm
reference HEAD   = 40dc1faeebfaa48c66b6e50c9406f148c4b720e1
latest review    = docs/task038_extra_full3d_iterative_0p7nm/review_report_v16.md
latest response  = docs/task038_extra_full3d_iterative_0p7nm/response_v16.md
Task40 branch    = codex/20260822-task40-hybrid-side-factor-pc
Task40 pre-update HEAD = 8d04f76ce17b2eaaa9fa66b7ecb2be0de66846ee
```

Task038-extra 只作为 **read-only numerical and architecture reference**。Task40 不修改
Task038-extra，不整体 merge/cherry-pick 该分支，不复用其 raw result、旧 checkpoint、
benchmark orchestration 或 task-numbered runner，也不把 Task038-extra 的 component result
冒充 Task40 numerical pass。

本文件的用途只有两个：

1. 避免 Task40 重复验证已经充分证明的 positive-operator 事实；
2. 避免 Task40 在真实 physical Maxwell 上重复 Task038-extra 已经暴露的同类失败结构。

---

## 2. 早期 N2 local-factor 参考仍然有效，但不再是主要结论

Task038-extra N2 曾证明：相同数值类的局部复数块可以按 canonical descriptor 分组，
使用 packed complex128 factor，并保持 deterministic owner routing、orientation/Floquet
metadata、packed solve、round-trip residual 和独立 lifecycle 证据。

| 项目 | 只读事实 | Task40 边界 |
|---|---:|---|
| N2 record | `outcomes/records/n2_local_factor_la_v2.json` | read-only |
| rows | 882 | 不是 Task40 local-row qualification |
| factorization residual | `8.158904706122267e-16` | local algebra only |
| condition estimate | `57576704.11589122` | conditioning warning |
| packed round-trip relative error | `0` | storage/solve identity only |
| process-tree peak | `1487814656 B` | historical reference only |
| swap | `0 B` | historical reference only |

N2 当时因 marker registration 受控停止，不能作为 Task40 production qualification。
Task40 可继续复用其 owner-local、canonical identity、factor-class 和 lifecycle 思想，但
这些工程事实不能回答真实 physical Maxwell 是否收敛。

---

## 3. Task038-extra V13：positive hierarchy 已经充分证明

Task038-extra 在同一物理 mesh 上建立了：

```text
p6 matrix-free positive action
→ same-mesh p3 sparse positive operator
→ same-mesh p1 sparse positive operator
→ small p1 development factor
```

固定 p6/h10、13.5 nm、MPI1 的四种 positive probe 结果为：

| source | iterations | final explicit true residual | peak RSS |
|---|---:|---:|---:|
| random | 200 | `5.550975220267439e-9` | `1517903872 B` |
| gradient | 220 | `2.7889793119815017e-9` | `1516544000 B` |
| curl | 180 | `5.6105046279899595e-9` | `1536192512 B` |
| checkerboard | 200 | `7.760965317017376e-9` | `1533190144 B` |

该结果证明：same-mesh p-transfer、positive p-multigrid/LOR 类局部层级和固定内存
restart lifecycle 对正定辅助问题有效。

### Task40 的冻结解释

Task40 **不再重复运行 positive-operator qualification**。以后若复用 LOR、positive pMG、
Chebyshev/Jacobi smoother 或 bounded positive local inverse，可把已有 component pass 当作
工程基础；新的正式计算必须直接进入 physical operator identity 或 physical true-residual
screen。

不得把 positive pass 写成 physical Maxwell pass。

---

## 4. Task038-extra V14：真实 physical Maxwell 在约 0.484 平台化

相同 selected positive hierarchy 用于真实 Maxwell 后，权威 checkpoint 为：

| checkpoint | explicit physical true residual |
|---:|---:|
| 500 | `0.48387099430079733` |
| 1000 | `0.4837947981092168` |

500→1000 的相对下降仅为 `0.000157472120623114`，约 `0.01575%`。运行随后在
checkpoint-1500 前由用户停止，正式分类保持：

```text
CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED
```

该结果不是 fixed-cap 20000-step failure，也没有 official E/H、R/T/A、A_volume 或
channels；但它已经足以说明：

> positive/LOR hierarchy 能消除一部分局部误差，却不能单独处理真实 Maxwell 的负质量项、
> 复材料、DtN、近共振与全局波传播误差。

### 与 Task40 的一致证据

Task40 当前 physical bare-F external fixed-LOR pilot 在 256 步后的 explicit residual 为：

```text
0.7349227023138162
```

两个任务的物理、网格和 operator 范围不同，数值不能直接横向比较；但二者一致否定了：

```text
standalone positive/LOR inverse
≈
完整 physical Maxwell side inverse
```

因此 Task40 不得通过增加普通 LOR iteration、扫描 shift、改变 smoother 次数或重复
positive source 来继续该 standalone family。

---

## 5. Task038-extra V15：固定小型 Floquet correction 的 span 不足

Task038-extra 对 checkpoint-1000 residual 使用固定 rank-32 propagating/near-cutoff
Floquet correction，得到：

```text
captured residual energy = 0.002179823642496248
post-projection rho      = 0.9989094935766222
```

该 route 已按 span Gate 关闭，不能通过增加 rank、改变 mode/window/weight 或重命名为新
coarse 重新开启。

这与 Task40 的以下事实相互支持：

```text
旧 776-dimensional interface space不足
current two-plane full-spectrum kernel no-signal
unselected 630×160 coarse既接近fine规模又恶化residual
```

共同结论不是“所有 wave-aware coarse 都失败”，而是：

> 少量预先选定的外部波模，或未经物理/谱选择的大型局部候选集合，都不能自动代表完整
> 三维 physical error。

---

## 6. Task038-extra V16：physical p-coarse 是新候选，不是 LOR 重开

V16 提出的候选为：

```text
same_mesh_physical_pcoarse_v1
```

fine physical operator 为：

```math
A_6=K_{curl,6}-k_0^2M_{\epsilon,6}+T_{DtN,6}.
```

关键改变是 p3 coarse level 也使用同一真实物理：

```math
A_3=K_{curl,3}-k_0^2M_{\epsilon,3}+T_{DtN,3},
```

并计划审计：

```math
A_3v\approx P_{63}^{H}A_6P_{63}v.
```

候选流程为：

```text
positive/local pre-smoother
→ restrict the physical residual to p3
→ approximately solve the physical p3 Maxwell problem
→ prolongate the p3 physical correction
→ positive/local post-smoother
```

因此角色必须明确区分：

| 组件 | 角色 |
|---|---|
| LOR / positive pMG | local/high-order/gradient error smoother |
| physical p3 operator | global volume-wave correction，包含负质量、复材料和 DtN |
| outer FGMRES | flexible outer contract |

这是一种新的 **physical multilevel PC**，不是 standalone LOR 的参数修正。

### 当前证据边界

V16 Q0 只有 predicted live-set closure：

```text
central prediction    = 1714887192 B
hard-upper prediction = 1889004056 B
```

Q1 因 p6/h50 `r3_long_tail_derived` 缺少合法 current-mesh source authority，在任何
数值测量前受控停止：

```text
CONTROLLED_STOP_PREMEASUREMENT_PROVENANCE / NOT_QUALIFIED
```

因此 physical p-coarse 目前既没有 positive，也没有 numerical failure。Task40 不能把它
写成已证明方法，但可以把它作为下一项最小 physical mechanism candidate。

---

## 7. 最新 surface-quadrature 修复及 Task40 风险

Task038-extra 最新代码提交把 surface quadrature degree 从全局
`form_compiler_options` 改为每个 UFL surface integral 的 metadata：

```python
integral.reconstruct(
    metadata={
        **integral.metadata(),
        "quadrature_degree": degree,
    }
)
```

修复覆盖 surface source vector、reusable surface component、mode projection 和 surface
scalar integration。Task40 当前分支仍使用旧的 `form_compiler_options` 路径，而
`external_dtn_coupling` 正是通过 `_ReusableSurfaceComponentAssembler` 构造。

### Task40 必须先做的窄修

在任何新的 external physical formal 前，Task40 应选择性重写该通用 quadrature metadata
修复，并比较修复前后的：

```text
canonical physical key set
canonical source values / digest
source norm
relative vector difference
orientation and sign
Floquet phase exactly once
surface quadrature degree
```

决策边界：

```text
relative source difference <= 1e-12
    → 旧 external numerical evidence继续有效，不重跑旧 campaign

source发生实质变化
    → 只重跑受影响的同一 physical external case
    → 不重跑 positive operator、full-spectrum random source或全部LOR campaign
```

该修复不会改变 canonical random source，也不会消除 C0 近 fine-size coarse 的结构问题。

---

## 8. 对 Task40 下一步的事实裁决

### 8.1 不再继续的路线

```text
standalone fixed-LOR side inverse
更多 positive-operator qualification
普通 shift / smoother / iteration 参数扫描
fixed small-rank Floquet-only correction
当前 two-plane full-spectrum kernel
630×160 unselected near-fine coarse
owner-serial moving-PML
```

### 8.2 第一优先候选：Task40 physical p-coarse mechanism oracle

Task40 应先在 current bottom bare-F 的较小、合法 physical case 上构造：

```text
p6 exact physical bare-F action
same-mesh p3 physical bare-F coarse action
canonical P63 and P63^H on active trace spaces
existing bounded positive/LOR service only as pre/post smoother or inner PC
```

它必须直接测试 physical operator，不再先跑 positive probes。

#### Phase P0：identity 与 source closure

只做必要的 focused checks：

```text
P63/P63^H adjoint work
canonical owner identity
slave-zero and phase-once
linearity/repeat
p3 rediscretized action versus P63^H F6 P63
external source after quadrature fix
```

这些是实现前置，不是新的 positive qualification。

#### Phase P1：准确 p3 coarse-span oracle

固定两个 RHS：

```text
external_dtn_coupling
fixed_random_repeat_0
```

先用一个足够准确、仅用于 mechanism adjudication 的 p3 physical solve，测量一次
multiplicative cycle：

```text
local/positive pre
→ physical p3 correction
→ local/positive post
```

必须与以下基线比较：

```text
zero correction
local/LOR-only correction
physical p3 correction
```

建议继续 Gate：两源均满足下列至少一项：

```text
one-cycle true residual <= 0.5
或相对 local/LOR-only 至少改善 4 倍
```

若准确 p3 correction 对任一代表 RHS 都没有明显 signal，关闭 physical p-coarse，不再优化
其 inner solver。

#### Phase P2：只有 P1 有 signal 才实现 scalable inner solve

```text
physical p3 FGMRES
+
positive p3→p1 hierarchy / bounded local service
```

不允许把 p3 global direct factor提升为 production。随后才按 h10/reduced → h5 → h4
检查 wavelength/refinement robustness。

### 8.3 第二候选：wave-aware physical domain decomposition

若 physical p-coarse span oracle失败，或 p3 inner solve无法在 bounded memory 下形成 signal，
Task40 应切换到新的 PC，而不是继续修 LOR：

```text
bounded 3D physical Maxwell subdomains
optimized impedance or local-PML transmission
physical canonical interface variables
matrix-free distributed interface/coarse action
no full-cross-section factor
no fixed global rank32 assumption
```

这条路线的局部 service仍可使用已证明的 positive/LOR smoother，但全局传播必须由 physical
subdomain/interface mechanism承担。

---

## 9. 面向 0.7 nm 的长期边界

即使 physical p3 coarse 在 5 nm 有效，也不能把 same-fine-mesh p1 direct factor直接外推到
0.7 nm。最终层级必须演化为：

```text
p6 physical matrix-free
→ p3 physical matrix-free
→ distributed h-coarse / wave-aware DD
→ bounded iterative coarse solve
```

而不是：

```text
p6 → p3 → growing global p1 MUMPS factor
```

Task38extra 的主要启示是：

> positive hierarchy适合作为局部与层内工具；真实 Maxwell 的关键 blocker必须由包含真实
> wave physics 的全局 coarse 或 domain-decomposition mechanism解决。

---

## 10. 最终参考结论

```text
Task038-extra modification/merge                 = forbidden / not needed
repeat positive-operator qualification in Task40 = NO
reopen standalone LOR family                     = NO
retain LOR/positive service as smoother           = YES
next Task40 physical candidate                    = same-mesh physical p-coarse
first numerical question                          = does accurate p3 physical correction contract both external and random0?
if physical p-coarse has no signal                = switch to wave-aware physical DD
current 0.7 nm qualification                      = NOT_ESTABLISHED
```

本文件只更新只读证据边界和 Task40 设计启示，不授权 heavy run，不构成新的 Review Report，
也不改变 Task40、Task39、master、物理、M480 或 physical DtN 的正式 Gate。
