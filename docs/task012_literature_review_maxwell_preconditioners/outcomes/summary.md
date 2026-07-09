# 结果总结

## 任务

task012 是文献调研与路线设计任务，不继续新增求解器 profile，也不运行新的大算例。本轮目标是把 task008-task011 的已有数值证据和 Maxwell/H(curl) 迭代求解器文献放在一起，判断下一轮最值得实现的迭代器与预条件器路线。

## 分支

`codex/20260707-literature-review-maxwell-preconditioners`

## 结论先行

最推荐的下一轮路线不是继续调 Jacobi/ASM/ILU，也不是直接把 complex hypre AMS 接进 Stage 4，而是：

```text
FGMRES 外迭代
+ real-imag split 的 H(curl) FE block 预条件器
+ real-valued AMS/HX 或低阶/p-coarsened auxiliary space
+ 小维 Rayleigh/Floquet modal deflation 或 DtN-aware coarse correction
```

更具体地说，先做最小 Task013：把当前 complex Stage 4 FE 主块拆成 real block，先在 FE-only / reduced Stage 4 上验证 real AMS/HX block PC 是否能显著降低 true residual；随后再把 DtN auxiliary unknowns 与 Rayleigh/Floquet 模态粗空间接入。这个方向同时利用了 task011 中 real AMS/HX 的正信号和本问题独有的 DtN/Floquet 模态结构。

## 1. 文献中最接近本项目的求解路线

最接近的是三条证据的交汇，而不是单篇文献的现成答案：

| 证据链 | 与本项目的关系 | 结论 |
|---|---|---|
| Hiptmair-Xu / hypre AMS | 针对 H(curl) Nedelec 正定或半正定 Maxwell 块，task011 real FE-only 已验证少步收敛 | 适合作为 FE 主块预条件器核心 |
| time-harmonic Maxwell real block / DDM / block PC | 文献中常把 complex Maxwell 写成 real/imag block，并用 block PC 或 DDM 处理 | 支持绕开当前 complex hypre 崩溃 |
| biperiodic Maxwell DtN / RCWA / Fourier modal | 本项目的 z 端口本身就是 Rayleigh/Floquet modal DtN | 支持构造小维 modal coarse/deflation 或 layered-background approximate inverse |

没有找到“DOLFINx + Nedelec + Floquet periodic + auxiliary DtN port + complex material + R/T/A”的完全现成求解器。因此真正有希望的路线会是定制组合。

## 2. 已被本项目实验降级的方向

| 方向 | 本项目证据 | 结论 |
|---|---|---|
| Jacobi-Krylov | task009/task011 中 p=2 h=5/h=4 均不收敛，最佳 true residual 仍约 0.234 | 仅保留为低内存失败基线 |
| one-level ASM/RAS + ILU/local LU | task009 现成 profile 停滞或发散；文献也指出 high-frequency Maxwell 下普通 ILU/ASM 慢 | 不再微调 |
| generic GAMG/BoomerAMG | task009 不收敛或崩溃，且不是 H(curl) 结构化 PC | 不作为主线 |
| complex hypre AMS 直接路径 | task011 最小 complex p=1 h=10 触发 malloc invalid size / PETSc signal 11 | 禁止直接接入 Stage 4 |
| MUMPS-BLR 作为最终答案 | task010 p=2 h=2 可复现 R/T/A，但内存只从 direct 约 20.53 GB 降到约 17.85 GB，h=1.5 仍被 kill | 作为 fallback，不是低内存迭代法 |

## 3. AMS/HX 是否仍值得继续

值得继续，但必须改变实现方式。

task011 的 real FE-only positive Maxwell 结果是本轮最强本地正证据：`p=2 h=5` 用 7 次迭代达到 true residual `4.024e-7`。hypre 官方文档说明 AMS 是 edge finite element Maxwell solver，需要 discrete gradient、edge constant vectors 或 high-order interpolation 等 auxiliary data；PETSc 也明确 `pc_hypre_type=ams` 需要这些 auxiliary data。因此 task011 的实现方向是对的。

风险也很明确：

| 风险 | 处理方式 |
|---|---|
| complex hypre AMS 崩溃 | 不再直接使用 complex AMS；转成 real block 或构造 real auxiliary PC |
| p=2 h=4 real AMS 内存压力 | 先审计 H1 degree、G、Pi、Aalpha/Abeta 与 AMG hierarchy；优先低阶/p-coarsened auxiliary |
| FE-only 与 Stage 4 差异 | 分阶段：FE-only real block -> reduced Stage 4 -> full FE/aux DtN block |

## 4. 是否有文献支持 real/imag split + real AMS

有中等强度支持，但不是“完全同问题直接证明”。

Beuchler 等 time-harmonic Maxwell DDM 论文显式把 complex Maxwell 离散系统写成 real/imag block，并在 block preconditioner/DDM 框架中求解。Fressart 等 2025 年并行求解器比较也把 HX/AMS 与 BLR 作为最有希望方向之一。hypre AMS 与 Hiptmair-Xu 文献支持 real-valued H(curl) auxiliary-space 预条件。把这些合起来，可以支持本项目下一步做：

```text
A = Ar + i Ai
real(A) = [[Ar, -Ai], [Ai, Ar]]
P ≈ blockdiag(B_AMS, B_AMS)
```

但需要诚实说明：针对本项目的 Floquet periodic + DtN auxiliary 增广系统，文献没有直接给出可照搬方案。这里的科研机会正是在 real AMS/HX 与 Rayleigh/DtN 模态粗空间之间建立桥。

## 5. Rayleigh/Floquet coarse space、DtN-aware PC 与 FEM-RCWA hybrid

直接以“Rayleigh mode preconditioner for FEM grating Maxwell”为题的强文献证据较少；这反而说明该方向可能有原创空间。间接证据包括：

| 来源 | 给出的启发 |
|---|---|
| biperiodic Maxwell DtN FEM | Rayleigh/Floquet 模态和 DtN 截断是周期散射问题的自然边界变量 |
| RCWA / Fourier modal method | 周期层状结构可用 Fourier harmonics 与 scattering matrix 高效处理 |
| deflation / coarse-space Krylov 文献 | 少量全局慢模态可通过 coarse correction 移除 |

对本项目最自然的定制方案是：把已有 DtN port 中的 propagating/near-cutoff Rayleigh orders 构造成 coarse vectors `Z`，在 GMRES/FGMRES 中做 deflation：

```text
x <- x + Z (Z^* A Z)^(-1) Z^* r
```

这个粗空间维度很小，内存成本低，且直接瞄准周期光栅中最难由局部预条件器消除的长程传播误差。

## 6. shifted Maxwell / shifted Laplacian 是否值得重做

值得作为辅助层重做，但不能重复 task010 的 minimal shifted P + ASM/ILU。

文献对吸收型 Maxwell 和 shifted/absorbing preconditioner 的结论是：加吸收后 operator 更接近可用的椭圆型问题，但 inner solver 必须足够结构化，典型是 two-level DD、impedance Schwarz、multilevel 或 Maxwell-aware auxiliary space。task010 的失败符合这个判断，因为当时只是把 shifted/positive P 交给普通 ASM/ILU/local LU。

因此 shifted Maxwell 只有在以下组合中才值得继续：

```text
shifted/positive H(curl) block + real AMS/HX
shifted Maxwell + two-level DD / impedance interface
shifted layered-background approximate inverse
```

## 7. DDM / sweeping 是否适合当前周期光栅单胞

DDM/sweeping 对大物理域、高频传播问题有文献支持，但不是 task013 的第一优先级。原因：

| 判断 | 原因 |
|---|---|
| one-level ASM 已不值得 | task009 失败，文献也说明 high-frequency Maxwell 需要 coarse space 或 impedance interface |
| two-level DD 有潜力 | Bonazzoli 等给出吸收 Maxwell 的 two-level Schwarz 理论和大规模例子 |
| 当前单胞不适合先做 sweeping | 本项目是 50×25×140 nm 周期单胞，z 方向已有 DtN port；先利用 port modal 更直接 |

DDM 后续可作为工作站/集群路线，但 task013 应先做 real-split AMS 与 modal deflation。

## 8. matrix-free 应作为主线还是内存优化层

matrix-free 应作为内存优化层，不是主收敛路线。

task011 已证明 FE-only UFL action 与 assembled matrix matvec 一致到 `1e-15` 量级，这是非常有价值的内存优化基础。但 matrix-free 只减少 `A` 的存储，不会自动改善 indefinite Maxwell 的谱。没有可用 PC 时，matrix-free GMRES 仍会像 Jacobi-Krylov 一样停滞。

推荐顺序：

```text
先 assembled prototype 确认 PC 能收敛；
再 matrix-free 化 A 的 matvec；
PC 侧保留低阶/粗空间/AMS 矩阵。
```

## 9. 是否应暂停求解器实现

不应无限期暂停，但下一步实现必须非常小。

继续盲目新增 PETSc profile 应暂停；但完全不实现也会停在文献层面。最合适的动作是最小 Task013：只验证 real-split AMS/HX block PC 的可行性，并同时保留 Rayleigh/Floquet deflation 的接口设计，不直接跑 p=2 h=2 或 h=1.5 大算例。

## 10. 下一步推荐的 1-3 个任务

| 优先级 | 任务 | 目标 |
|---:|---|---|
| 1 | Task013 real-split AMS/HX block PC minimal prototype | 绕开 complex AMS 崩溃，验证 real block + AMS 是否能把 true residual 降到可用区间 |
| 2 | Task014 Rayleigh/Floquet modal deflation | 用 DtN port propagating/near-cutoff modes 构造低维 coarse correction |
| 3 | Task015 layered-background / RCWA-like approximate inverse feasibility | 为周期层状背景建立 Fourier/modal 近似逆，作为更物理的长期 PC |

## 关键结果

| 路线 | 当前推荐 |
|---|---|
| real-split AMS/HX + low-order/p-coarsened auxiliary | 第一主线 |
| Rayleigh/Floquet modal deflation | 第二主线，可与 AMS 叠加 |
| DtN-aware FE/aux block PC | 与上述两条组合推进 |
| layered-background / RCWA-like approximate inverse | 长期高潜力路线 |
| matrix-free + physics PC | PC 成功后再做 |
| BLR/H-matrix | fallback 与参考，不是最终低内存迭代法 |
| Jacobi/ASM/ILU/BoomerAMG | 停止作为主线 |

## 已知问题

- 文献中没有完全同构于本项目的开箱求解器；推荐路线含有研究性组合。
- AMS/HX 的高阶和 p=2 内存瓶颈仍需单独审计。
- Rayleigh/Floquet deflation 是强物理直觉和间接文献支持，不应在未验证前写成已成功。
- DOLFINx/PETSc 中 real-split block 与 MPC/DtN auxiliary 的工程复杂度较高，需要最小化 task013 范围。

## 下一轮审查问题

1. task013 是否先只做 FE-only real split，还是直接包含 Floquet MPC 但暂不含 DtN auxiliary？
2. Rayleigh coarse vectors 应先只取 propagating orders，还是把 near-cutoff evanescent orders 也纳入？
3. p-coarsened auxiliary 是先用 p=1 同网格，还是用同 p 粗网格？
4. 是否允许为 Task013 新增 Python PC / MatShell 原型，先追求小算例验证而非性能？
