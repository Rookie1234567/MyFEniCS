# Floquet-carrier envelope H(curl)：理论、离散与 0.7 nm 设计

## 1. 它要解决什么问题

当前 5 nm 成功 Hybrid workflow 峰值约为 `80 GiB`。这不是物理下限，但如果离散网格为了
保持每波长分辨率而满足 `h proportional to lambda`，三维体自由度的朴素包络是：

```math
N(\lambda)\propto h^{-3}\propto\lambda^{-3}.
```

因此：

```math
\frac{N(1\ \mathrm{nm})}{N(5\ \mathrm{nm})}
\approx 5^3=125,
```

```math
\frac{N(0.7\ \mathrm{nm})}{N(5\ \mathrm{nm})}
\approx
\left(\frac{5}{0.7}\right)^3
\approx 364.43.
```

即使错误地假设现有内存只线性增长，`80 GiB` 也会变成约 `10 TiB` 和 `28.5 TiB`。
matrix-free、bounded local factors 和 distributed data 可以大幅降低每个自由度的字节数，
但未必单独足以抵消约 `364x` 的体自由度增长。

本路线改变的不是线性求解器，而是离散 trial space：

> 把已知的快速波相位显式写进基函数，让有限元未知量主要表示缓变 envelope，从而减少
> 每个波长所需的网格点和全局自由度。

## 2. 基础物理方程

频域电场方程写为：

```math
\nabla\times
\left(
\mu_r^{-1}\nabla\times\mathbf E
\right)
-
k_0^2\varepsilon_r\mathbf E
=
\mathbf f.
```

原项目仍保持：

```text
complex128
Nedelec H(curl)
complex lossy epsilon
double Floquet x/y
physical Fourier-DtN in z
```

本路线不改变 Maxwell 方程，只改变 `E` 的表示方式。

## 3. 单载波 phase extraction

先考虑一个固定载波 `kappa`：

```math
\mathbf E(\mathbf x)
=
e^{i\boldsymbol\kappa\cdot\mathbf x}
\mathbf u(\mathbf x).
```

利用乘积法则：

```math
\nabla\times
\left(
e^{i\boldsymbol\kappa\cdot\mathbf x}\mathbf u
\right)
=
e^{i\boldsymbol\kappa\cdot\mathbf x}
\left(
\nabla\times\mathbf u
+
i\boldsymbol\kappa\times\mathbf u
\right).
```

定义 shifted curl：

```math
\mathcal C_{\boldsymbol\kappa}\mathbf u
=
\nabla\times\mathbf u
+
i\boldsymbol\kappa\times\mathbf u.
```

同一载波下，体弱式变为：

```math
a_{\boldsymbol\kappa}(\mathbf u,\mathbf v)
=
\int_\Omega
\mu_r^{-1}
\mathcal C_{\boldsymbol\kappa}\mathbf u
\cdot
\overline{
\mathcal C_{\boldsymbol\kappa}\mathbf v
}
-
k_0^2\varepsilon_r
\mathbf u\cdot\overline{\mathbf v}
\;d\Omega.
```

标准 Nédélec 空间仍用于 `u`。乘以光滑相位函数保持 `H(curl)` regularity，因此 reconstructed
field 仍是 curl-conforming。

## 4. 多载波离散

单一 incident carrier 不能描述所有反射、透射、衍射和局部散射。采用 carrier family：

```math
\mathbf E_h
=
\sum_{\alpha=1}^{N_c}
e^{i\boldsymbol\kappa_\alpha\cdot\mathbf x}
\mathbf u_{\alpha,h}.
```

对 trial carrier `p` 和 test carrier `q`，体块为：

```math
a_{qp}(\mathbf u_p,\mathbf v_q)
=
\int_\Omega
e^{i(
\boldsymbol\kappa_p-
\overline{\boldsymbol\kappa_q}
)\cdot\mathbf x}
\left[
\mu_r^{-1}
\mathcal C_{\boldsymbol\kappa_p}\mathbf u_p
\cdot
\overline{
\mathcal C_{\boldsymbol\kappa_q}\mathbf v_q
}
-
k_0^2\varepsilon_r
\mathbf u_p\cdot\overline{\mathbf v_q}
\right]
d\Omega.
```

对传播 carrier，`kappa` 为实数；对 z 方向 evanescent carrier，`beta` 可以为复数，因此
test phase 必须使用 `conjugate(kappa_q)`，不能写成简单的 `kappa_p-kappa_q`。

矩阵是 carrier block system：

```math
\begin{bmatrix}
A_{11} & A_{12} & \cdots \\
A_{21} & A_{22} & \cdots \\
\vdots & \vdots & \ddots
\end{bmatrix}
\begin{bmatrix}
u_1\\u_2\\\vdots
\end{bmatrix}
=
\begin{bmatrix}
b_1\\b_2\\\vdots
\end{bmatrix}.
```

在均匀背景中，不同 Fourier carriers 近似正交，块结构接近 diagonal。在非可分离三维材料中，
off-diagonal blocks 表示真实 mode conversion；因此该方法不是 RCWA 的 z-layer
可分离假设，而是“plane-wave carrier + arbitrary-3D FE envelope”的混合离散。

## 5. 双 Floquet compatibility

设周期基矢为 `a1,a2`，Bloch transverse vector 为 `k_B`，reciprocal vectors 满足：

```math
\mathbf a_i\cdot\mathbf b_j
=
2\pi\delta_{ij}.
```

选择：

```math
\boldsymbol\kappa_{mn,t}
=
\mathbf k_B
+
m\mathbf b_1
+
n\mathbf b_2.
```

则：

```math
e^{i\boldsymbol\kappa_{mn,t}\cdot\mathbf a_j}
=
e^{i\mathbf k_B\cdot\mathbf a_j}
e^{i2\pi\mathbb Z}
=
e^{i\mathbf k_B\cdot\mathbf a_j}.
```

因此每个 carrier 本身满足与原问题相同的 Floquet multiplier。如果 envelope 在 x/y 取
periodic phase `1`，每个重构项自动满足原 Bloch 条件。

实现时必须二选一，不能重复施加相位：

```text
推荐：
carrier包含 k_B + G_mn
envelope MPC使用 periodic phase=1

备选：
carrier只包含 G_mn
envelope继续使用原 k_B Floquet MPC
```

第一阶段推荐前者，因为它能同时抽取 incident Bloch phase。

## 6. carrier 选择

初始 carrier family 不应盲目包含所有模式。建议嵌套顺序：

```text
C0:
    incident carrier

C1:
    incident
    + top/bottom zero-order outgoing partners

C2:
    all propagating external Floquet orders

C3:
    propagating
    + near-cutoff evanescent orders

C4:
    residual-adaptive carriers
```

候选必须经过 sampled phase Gram audit。对采样点 `x_l` 和正权重 `w_l`：

```math
G_{\alpha\beta}
=
\frac{
\sum_l
w_l
e^{i\boldsymbol\kappa_\alpha\cdot\mathbf x_l}
\overline{
e^{i\boldsymbol\kappa_\beta\cdot\mathbf x_l}
}
}{
\|\phi_\alpha\|_w
\|\phi_\beta\|_w
}.
```

若 carrier family 数值 rank 不足或 condition 太大，应按确定性 modified Gram-Schmidt /
RRQR 删除近重复 carrier。不能通过 dense normal equations 处理病态 carrier。

## 7. 与 physical DtN 的关系

physical DtN 方程和 external channel inventory保持不变。carrier envelope 只改变 FE volume
representation。

在 homogeneous top/bottom port 上，每个 transverse carrier 对应一个 shifted Fourier order。
因此边界作用可写成：

```text
carrier index
-> physical Floquet order/key
-> existing outgoing beta/TE/TM normalization
-> streaming DtN action
```

不能建立：

```text
all carrier x all trace rows dense W
per-rank replicated modal basis
dense global carrier-to-port matrix
```

推荐使用：

```text
owner-distributed trace
bounded carrier batches
FFT/streaming mode action
```

这可以与 Task040 Review V6 的 full-interface Floquet-DtN sweep共享 channel mapping 和
streaming infrastructure。

## 8. 求解与预条件结构

最小 block preconditioner：

```math
P_0^{-1}
=
\operatorname{diag}
\left(
\widetilde A_{11}^{-1},
\ldots,
\widetilde A_{N_cN_c}^{-1}
\right).
```

每个 diagonal carrier block是 shifted-curl Maxwell envelope operator。它仍可能 indefinite，
因此 local/global service应采用：

```text
matrix-free high-order action
low-order-refined or p/h auxiliary hierarchy
bounded patch smoother
complex shifted auxiliary cycle
```

material-induced off-diagonal coupling可采用：

```text
FGMRES over MatNest/MatShell
carrier-space sparse graph correction
or bounded low-rank residual correction
```

不建议第一阶段直接 factor整个 carrier block system。

## 9. 为什么它可能削弱 lambda^-3

标准均匀细化的体自由度近似：

```math
N_{\mathrm{std}}
\sim
C_{\mathrm{std}}\lambda^{-3}.
```

若 carrier 已承担主要振荡，envelope mesh可以更接近由材料界面曲率、几何特征和 envelope
variation决定。一个研究假设是：

```math
N_{\mathrm{env}}
\sim
N_c(\lambda)
N_{\mathrm{geom}}.
```

在二维周期横截面中，可解析传播/近截止 carrier 数的最坏增长更接近 surface inventory：

```math
N_c(\lambda)
\sim
O(\lambda^{-2}),
```

而不是 volume `O(lambda^-3)`。如果 z 相位也由 `beta` carriers抽取，envelope 的 z
分辨率可进一步由结构变化而不是自由空间波长控制。

这是待验证的 hypothesis，不是既成结论。实际总成本还取决于：

```text
carrier count
carrier coupling sparsity
envelope p/h accuracy
material discontinuity
quadrature cost
solver iteration growth
```

## 10. 与任意三维结构的关系

这条路线不要求材料沿 z 均匀。任意三维 `epsilon(x,y,z)` 直接进入 block integrals，产生
carrier conversion。适用边界是：

- carrier family足以覆盖主要传播方向；
- envelope 能以相对粗的 Nédélec mesh表示材料引起的振幅和方向变化；
- 强局部奇异场仍可能需要局部 h/p refinement；
- 极端随机/强散射区域可能需要很多 local carriers，此时收益会下降。

因此它比纯 Hybrid modal propagation更通用，但并不保证所有 arbitrary-3D case都能用很少
carriers。

## 11. 内存合同

最终 0.7 nm-oriented implementation 必须：

```text
high-order carrier blocks        = matrix-free
all carrier blocks assembled     = false
carrier batch size               = bounded
live carrier vectors             = bounded by restart/batch
full carrier basis replication   = false
physical DtN W                   = not materialized
local factor rows                <=1024 if factors exist
global direct factor             =0
carrier global dense factor      =0
FE-sized numeric allgather       =false
swap                             =0
```

若 `N_c` 增长导致所有 carrier fields 同时驻留，方法仍会失去意义。正式实现应允许：

```text
carrier batching
active-set carriers by region
checkpoint/recompute instead of full retention
```

## 12. 分阶段 Gate

### E0：纯代数

```text
reciprocal lattice identity      <=1e-13
Floquet multiplier mismatch      <=1e-12
shifted-curl product rule        <=1e-12
real-coefficient block symmetry  <=1e-12
duplicate carrier pruning        exact
```

### E1：单 carrier manufactured box

同一 coarse mesh上比较：

```text
ordinary E formulation
carrier-envelope u formulation
```

要求：

```text
matrix action relative error     <=1e-10
solution reconstruction error    <=1e-9
true residual                    <=1e-9
Floquet identity                 exact
```

### E2：双 carrier manufactured superposition

要求两个已知 plane waves均可重构，并检查 carrier block：

```text
MatNest action vs direct sum      <=1e-10
carrier Gram condition            <=1e10 after pruning
no phase double counting
```

### E3：5 nm flat/layered authority

使用现有 direct authority比较：

```text
R/T/A and selected fields
carrier count 1/propagating/near-cutoff
envelope mesh sequence
```

最低正信号：

```text
matched observable error
and envelope active DoF <= ordinary DoF / 4
```

### E4：5 nm non-separable 3D

只在 E3 通过后进入。要求：

```text
full true residual pass
R/T/A/E/H match
no dense carrier blocks
memory lower than ordinary matched-accuracy route
```

### E5：中间波长与 0.7 nm reduced pilot

顺序：

```text
5 nm
-> 2 nm or 1 nm reduced geometry
-> 0.7 nm reduced non-separable geometry
```

不得从 E3 直接跳到最大 0.7 nm。

## 13. 停止与切换

停止当前 global-carrier family并转 local carrier/other discretization，当出现：

```text
E2 carrier Gram无法在合理carrier数内稳定
E3 matched accuracy没有至少4x DoF reduction
carrier count增长接近volume DoF增长
quadrature/block coupling成本抵消DoF收益
E4 holdout geometry严重失效
```

此时保留 shifted-curl/UFL基础设施，后续可转为：

```text
local partition-of-unity carriers
Trefftz/plane-wave DG
carrier-informed coarse space
```

## 14. 参考依据

外部方法依据：

1. P. Ledger, K. Morgan, O. Hassan, N. P. Weatherill,
   *Plane wave H(curl) conforming finite elements for Maxwell's equations*,
   Computational Mechanics 31, 272–283 (2003),
   DOI `10.1007/s00466-003-0430-7`.
2. W. Pazner,
   *Efficient low-order refined preconditioners for high-order matrix-free
   continuous and discontinuous Galerkin methods*,
   arXiv `1908.07071`.
3. O. Cessenat and B. Després,
   *Using Plane Waves as Base Functions for Solving Time Harmonic Equations
   with the Ultra Weak Variational Formulation*,
   DOI `10.1142/S0218396X03001912`.

仓库内部依据：

```text
Task030:
    matrix-free/low-memory H(curl) infrastructure and full R/T/A closure

Task039:
    5 nm Full3D iterative residual 0.155 after 4000 steps,
    showing solver-only wavelength robustness remains insufficient

Task040:
    fixed 776 interface family no-signal,
    motivating full-interface physics and discretization-level reduction
```
