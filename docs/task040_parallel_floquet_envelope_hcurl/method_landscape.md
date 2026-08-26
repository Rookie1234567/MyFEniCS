# 并行方法地图：为什么优先实现 carrier envelope

本页比较四条可以继续研究的路线。Codex 当前 Task040 Review V6 已在推进 full-interface
sweeping / moving-PML / adaptive Schwarz，本分支避免重复实现同一套机制。

## 1. 路线比较

| 路线 | 直接解决的 blocker | 对 0.7 nm 的潜在价值 | 当前分支决策 |
|---|---|---|---|
| Floquet-carrier envelope Nédélec | 体 DoF 随波长快速增长 | 可能把快速振荡从网格转移到载波，削弱 `lambda^-3` | **主实现** |
| low-order-refined matrix-free H(curl) | high-order bytes/DoF、局部/全局 shifted solve | 使每个 carrier block或Full3D block接近线性存储 | 作为主路线的 solver service 设计 |
| rational multi-shift H(curl) inverse | indefinite target operator难以被单一shift预处理 | 固定少量coercive shifted solves，任意3D适用 | 后续 fallback，先不写重型集成 |
| Trefftz/plane-wave DG/HDG | 标准 polynomial FEM 的 pollution 与 wavelength resolution | 最大潜在 DoF reduction，但需要新离散和接口通量 | 长期路线，不与当前代码同时大改 |

## 2. low-order-refined matrix-free support

对 high-order envelope operator `A_p`，构造 refined low-order operator `A_LOR`。理想的
谱等价关系为：

```math
c_1
\left\langle A_{\mathrm{LOR}}v,v\right\rangle
\le
\left\langle A_p v,v\right\rangle
\le
c_2
\left\langle A_{\mathrm{LOR}}v,v\right\rangle,
```

其中常数应尽量不随 `h` 和 `p` 恶化。

该结构主要服务 shifted/coercive auxiliary operator，而不是直接假设 indefinite Maxwell
target可由普通 multigrid解决。建议组合：

```text
target carrier block:
    unshifted matrix-free action

auxiliary cycle:
    complex-shifted H(curl)
    + LOR/AMS/HX
    + bounded patch smoother
```

它与 Task030 已验证的 transfer/Galerkin 基础设施兼容，但不能直接复用 Task030 已失败的
单一 792D p1 coarse。

## 3. rational multi-shift fallback

单一 absorption shift可能在高频下过弱或过强。可以用少量 shifted inverses逼近目标逆：

```math
A^{-1}
\approx
\sum_{j=1}^{n_s}
\omega_j
\left(
A+i\sigma_j M
\right)^{-1}.
```

每个 shifted system更接近 coercive，可使用 matrix-free H(curl) multilevel。权重和 shift
必须在小型谱区间上通过 residual-minimizing或contour/rational approximation确定，不能在
formal 5 nm case上做无边界菜单扫描。

进入条件：

```text
carrier-envelope E1/E2通过
但单一carrier-block auxiliary solve仍明显限制收敛
```

建议固定 `n_s=2` 或 `3` 的 tiny algebra pilot，而不是立即建立大规模 multi-shift cache。

## 4. Trefftz/plane-wave DG

Trefftz basis在每个局部单元内满足 homogeneous wave equation，可以显著降低短波问题的
polynomial pollution。Maxwell已有 plane-wave `H(curl)` conforming和ultra-weak/Trefftz
研究基础。

但它需要重新设计：

```text
element/interface numerical flux
material-jump treatment
Floquet coupling
DtN coupling
static condensation
recovery/postprocessing
```

因此它不是本轮最快可以交给 Codex验证的路线。若 global carrier envelope 在 E3 没有 DoF
收益，下一步应考虑 local partition-of-unity carrier或Trefftz DG，而不是继续增加 global
carrier数量。

## 5. 为什么当前先做 carrier envelope

它同时满足：

```text
保留标准Nedelec H(curl)
可用UFL直接表达shifted curl
任意3D epsilon(x)可直接进入弱式
可复用现有Floquet/DtN/modal inventory
可与V6 sweep/Schwarz叠加
轻量代数可以立即验证
```

最大的风险是 carrier conditioning 和 block coupling。当前代码因此先实现：

```text
Bloch identity
shifted-curl identity
cross-carrier phase
Gram/rank audit
deterministic carrier pruning
```

而不是先写一个无法审计的大型 PDE runner。
