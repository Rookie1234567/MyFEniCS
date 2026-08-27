# Structured Floquet-background FFT/Kronecker H(curl) 预条件器

## 0. 当前定位

```text
status                      = reference algebra prepared
exact physical operator     = unchanged
ordinary default            = unchanged
production qualification    = no
recommended first PDE       = tiny homogeneous/layered periodic box
5nm h4 heavy run            = forbidden before small gates
```

代码入口：

```text
src/solvers/floquet_background_hcurl.py
src/test/test_319_task040_parallel_background_hcurl.py
```

当前代码是 fully-periodic constant-coefficient NumPy oracle。生产目标不是三维全周期，而是：

```text
FFT in x/y
+
bounded 1D z solve per transverse harmonic
```

---

## 1. 精确问题与 background split

精确离散仍近似：

```math
A
=
\operatorname{curl}\mu^{-1}(x)\operatorname{curl}
-k_0^2\epsilon(x)
+\mathcal D_{\mathrm{physical}}.
```

选择 background：

```math
A_0
=
\operatorname{curl}\mu_0^{-1}(z)\operatorname{curl}
-k_0^2\epsilon_0(z)
+\mathcal D_0.
```

外层求解：

```math
A x = b.
```

右预条件器为：

```math
P_\sigma^{-1}
=
(A_0+\sigma M)^{-1}.
```

`A_0`、`sigma` 和 `D_0` 只属于 PC。official field、R/T/A和true residual全部使用 exact `A`。

---

## 2. Floquet Fourier decomposition

在周期 x/y 平面：

```math
\mathbf u(x,y,z)
=
\sum_{m,n}
\widehat{\mathbf u}_{mn}(z)
\exp\left(
i(\mathbf k_B+\mathbf G_{mn})\cdot\mathbf x_t
\right).
```

其中：

```math
\mathbf G_{mn}
=
m\mathbf b_1+n\mathbf b_2.
```

对 x/y homogeneous或 z-layered background，`A_0` 在 `(m,n)` 上 block diagonal：

```text
forward distributed FFT
-> independent z blocks
-> inverse distributed FFT
```

真实三维材料只在 exact action `A` 中耦合这些 harmonics。

---

## 3. fully-periodic reference symbol

为了验证 sign和 transverse/longitudinal splitting，先考虑完全均匀、三方向周期的 reference。

对 Fourier wavevector `k`：

```math
\widehat{\operatorname{curl}\operatorname{curl}}
=
|\mathbf k|^2 I-\mathbf k\mathbf k^T.
```

因此：

```math
\widehat A_0(\mathbf k)
=
\mu_0^{-1}
\left(
|\mathbf k|^2 I-\mathbf k\mathbf k^T
\right)
-k_0^2\epsilon_0 I
+\sigma I.
```

定义：

```math
P_L
=
\frac{\mathbf k\mathbf k^T}{|\mathbf k|^2},
```

```math
P_T
=
I-P_L.
```

则：

```math
\widehat A_0
=
a_T P_T+a_L P_L,
```

其中：

```math
a_T
=
\mu_0^{-1}|\mathbf k|^2-k_0^2\epsilon_0+\sigma,
```

```math
a_L
=
-k_0^2\epsilon_0+\sigma.
```

只要两者不接近零：

```math
\widehat A_0^{-1}
=
a_T^{-1}P_T+a_L^{-1}P_L.
```

代码中的 `maxwell_symbol_inverse` 按该公式实现，并与 dense `3x3` inverse比较。

---

## 4. open-z production target

真实 side/Full3D问题不在 z 周期。对每个 transverse harmonic：

```math
\mathbf k_t
=
\mathbf k_B+\mathbf G_{mn},
```

保留 z 向 Nedelec/compatible discretization，得到小型 block-banded operator：

```math
A_{mn}^{(z)}
\widehat u_{mn}
=
\widehat r_{mn}.
```

生产候选的单次 apply：

```text
1. owner-distributed trace/volume packing
2. x/y FFT
3. for each local (m,n):
       solve 1D z block with fixed background/PML
4. inverse FFT
5. unpack to PETSc Vec
```

允许：

```text
banded direct per mode if block width is bounded
1D multigrid/cyclic reduction
bounded batches
```

禁止：

```text
one 3D factor
all-mode dense coupling matrix
all harmonics replicated per rank
```

---

## 5. background选择

只允许两个固定 candidate：

```text
B0 constant:
    one complex epsilon0/mu0 from a frozen volume or energy-weighted rule

B1 z-layered:
    exact material layers where geometry is laterally uniform
    frozen x/y average in heterogeneous slices
```

吸收 shift首先继承：

```text
dimensionless shift = 0.1
```

仅作为初始 fixed identity，不在正式 case扫描。若 B0/B1均无信号，停止 A1并转 adaptive Schwarz。

---

## 6. 与高阶 H(curl) matrix-free 的组合

fine exact action：

```text
high-order p6 Nedelec
matrix-free sum-factorized cell kernels
static condensation/recovery unchanged
```

background PC：

```text
low-order-refined or structured tensor-product auxiliary representation
FFT x/y
1D z solve
```

这允许：

```text
exact arbitrary-3D physics
+
cheap regular-background inverse
```

而无需 ordinary hp adaptivity。

---

## 7. 数值 Gate

### S0：pure NumPy oracle

已准备：

```text
Bloch FFT frequency order
symbol/inverse identity
transverse/longitudinal projectors
periodic FFT operator/inverse round-trip
working-set payload estimate
```

Gate：

```text
symbol inverse error <=1e-12
FFT round-trip       <=2e-12
```

### S1：DOLFINx homogeneous manufactured case

```text
small periodic box
complex epsilon
one Bloch phase
ordinary Nedelec exact operator
background PC MatShell
```

Gate：

```text
action identity                 <=1e-10
true residual                   <=1e-9
ordinary/envelope field match   <=1e-9
```

### S2：flat/layered scattering

使用现有 physical DtN，但 small mesh：

```text
B0 constant
B1 z-layered
```

正信号：

```text
r32 <=0.1
or residual improve >=8x vs identity/Jacobi
all R/T/A/channel authority pass after convergence
```

### S3：规则三维 grating reduced pilot

只在 S2通过后运行。固定一个 13.5 nm 或 coarse 5 nm案例，不直接上 p6/h4。

minimum：

```text
r64 <=0.5
and >=4x improvement vs current low-memory PC
and no explicit global F/factor
```

strong：

```text
true residual <=1e-6 within 256
peak memory lower than matched assembled candidate
```

S3无 minimum即停止 A1，不扫描 background/shift菜单。

---

## 8. 0.7 nm 延伸合同

A1本身不降低 DoF，但可把每个 DoF 的 storage从 sparse matrix/factor转为：

```text
field vectors
material/geometric coefficients
FFT buffers
bounded z-block data
```

高位目标：

```text
operator bytes/DoF bounded
PC bytes/DoF bounded
apply O(N log N_xy)
iteration growth measured on wavelength ladder
```

必须沿：

```text
13.5 / 5 / 2 / 1 nm reduced pilots
```

测 iteration与bytes/DoF后，才可预测0.7 nm。不能只把5 nm RSS乘364，也不能把FFT oracle冒充
arbitrary-3D pass。
