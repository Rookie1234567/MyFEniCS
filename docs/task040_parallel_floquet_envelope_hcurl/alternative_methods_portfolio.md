# 并行方法组合：不把 0.7 nm 押在单一路线上

## 0. 结论

本目录最初围绕 `Floquet-carrier envelope H(curl)` 建立，但该方法对本项目仍属于高风险
tiny feasibility。新的并行研究组合按下列优先级执行：

```text
A1  structured Floquet-background FFT/Kronecker inverse
A2  matrix-free high-order H(curl) + low-order-refined auxiliary preconditioner
A3  Task040 Review V6 full-interface / moving-PML / adaptive Schwarz
B1  mixed-precision preconditioner with complex128 outer residual
B2  wavelength/parameter continuation and Krylov/coarse recycling
B3  directional compression of interface/DtN actions
C1  transmission-variable HDG/CHDG as a long-term discretization fallback
C2  Floquet-carrier envelope only as E1/E2/E3 go/no-go probe
```

其中：

- `A3` 由 Codex 在 Task040 执行分支推进；
- `A1/A2` 是本并行分支新增的主要准备工作；
- `B` 类只在已有数值收敛信号后使用；
- `C` 类需要改变离散或大幅重构，不能作为当前交付的第一选择。

自动 reference-blind h/p 自适应不重新作为主路线。Task035e 已证明 local-h/local-p
基础能力存在，但没有形成可靠的多目标 accepted candidate。

---

## 1. A1：structured Floquet-background FFT/Kronecker inverse

### 1.1 它解决什么

当前规则周期单胞、结构化 hexa 网格和双 Floquet 边界具有强烈的规则性。即使真实材料
`epsilon(x,y,z)` 是三维非可分离的，也可以选择一个可快速求逆的 reference background
`epsilon_0(z)` 或常数 `epsilon_0`：

```math
A = A_0 + \Delta A.
```

精确方程仍为：

```math
A x = b.
```

只把：

```math
P_\sigma = A_0 + \sigma M
```

作为 FGMRES 的右预条件器。`sigma` 是 PC-only absorption shift，不进入真实方程和物理输出。

### 1.2 为什么适合当前规则结构

在 x/y 周期方向作 Floquet Fourier 展开：

```math
u(x,y,z)
=
\sum_{m,n}
\widehat u_{mn}(z)
e^{i(k_B+G_{mn})\cdot x_t}.
```

对 homogeneous 或 z-layered background，不同 `(m,n)` 在 `A_0` 中解耦。每个 transverse
harmonic 只需要一个小型一维 z 向量问题：

```text
FFT x/y
-> many independent 1D z solves
-> inverse FFT x/y
```

因此目标复杂度是：

```text
storage  O(N)
apply    O(N log N_xy)
no 3D sparse factor
no full-interface dense basis
```

真实三维材料引起的 mode conversion仍由 exact matrix-free `A` 处理，不要求真实结构可分离。

### 1.3 与 RCWA 和 Hybrid 的区别

```text
RCWA/Hybrid:
    使用模态展开改变或消元真实求解域的一部分

background inverse:
    真实未知量仍是完整3D H(curl)场
    可分离背景只作为P^-1
    P失败不会改变方程，只会导致迭代慢
```

因此它可以用于 arbitrary-3D Full3D，也可作为 Task040 side local service。

### 1.4 主要风险

```text
material contrast太强，A0^-1 A聚类不足
near-resonance导致background symbol接近奇异
z向真实结构过强，1D background传播太粗
高阶Nedelec trace/FFT layout实现复杂
分布式FFT transpose和owner routing成本
```

失败时不扫描大量 background 参数。只允许一个 constant background 和一个 z-layered
background 对照；两者无信号即停止 A1。

---

## 2. A2：low-order-refined matrix-free H(curl)

### 2.1 它不是 h/p 自适应

这里不自动决定哪里加密或升阶。对于每个固定高阶 hexahedral Nedelec element，构造一个
固定的 low-order-refined auxiliary mesh。概念上：

```text
one p-th order element
<-> p x p x p lowest-order refined cells
```

fine high-order operator 用 sum factorization / matrix-free action施加；低阶 refined operator
用于 AMS/AMG/Schwarz preconditioning。

这是一种**预条件器表示变换**，不是 reference-blind hp controller。

### 2.2 目标结构

```math
A_p x = b,
```

外层保持 exact unshifted complex128 operator。预条件器内部使用 positive 或 absorbed proxy：

```math
P_\sigma
=
\operatorname{curl}\mu^{-1}\operatorname{curl}
-k_0^2\epsilon
-i\sigma M,
```

或者更保守的 positive proxy：

```math
P_+
=
\operatorname{curl}\mu^{-1}\operatorname{curl}
+\tau M.
```

`P` 的 high-order action不物化；其 low-order-refined auxiliary matrix可以交给 AMS/AMG 或
bounded Schwarz。

### 2.3 为什么有价值

这条路线直接针对：

```text
p6 high-order operator bytes
high-order local factor size
matrix-free local/inner service
```

它可以与 A1 的 background inverse、Task040 的 full-interface sweep、moving-PML 或 adaptive
Schwarz叠加，而不是互相替代。

### 2.4 风险

现有 spectral-equivalence 理论主要针对 positive de Rham operators。time-harmonic indefinite
Maxwell 必须把 LOR 放在 shifted/positive auxiliary solve中，不能直接假定 unshifted问题
mesh-independent。

---

## 3. B1：mixed-precision PC

正式解和所有 true residual仍为：

```text
complex128
```

但以下对象可条件使用 `complex64`：

```text
local patch matrices/factors
background-symbol data
selected response cache
coarse work vectors
inner fixed-work Krylov
```

外层使用 FGMRES，并周期性用 complex128 exact action重算 residual。

潜在收益：

```text
PC resident bytes约减半
memory bandwidth压力下降
local setup/apply可能加速
```

边界：

```text
当前PETSc build的ScalarType固定为complex128
不能静默把全局A或official solution降精度
需要独立PCShell或外部local service
```

只有一个 complex128 candidate已经收敛或有强正信号后，才值得加入 mixed precision。它不能
挽救一个 residual接近1的预条件器。

---

## 4. B2：parameter continuation 与 recycling

最终反演会重复求解相近的：

```text
geometry
material parameters
angle
wavelength
```

因此第一套 0.7 nm forward solve建立后，应复用：

```text
mesh/topology
matrix-free kernels
background inverse
local hierarchy
adaptive coarse vectors
selected interface directions
Krylov recycle space
QEP/mode packets where physics permits
```

可以沿：

```text
13.5 -> 5 -> 2 -> 1 -> 0.7 nm
```

或参数反演迭代顺序作 continuation，用上一点的场作为初值并更新少量 coarse/response数据。

它不能降低第一套最大问题的 operator storage，但会显著影响反演总成本，所以必须在 solver
架构中预留 `rebuild / refresh / reuse` 接口。

---

## 5. B3：directional interface compression

完整 interface Schur 或 DtN transfer在高频下通常不是全局低秩，但按空间盒和传播方向分块后，
可能具有 directional low-rank / butterfly结构。

可用位置：

```text
full-interface Schur apply cache
moving-PML source-transfer maps
streaming DtN trace-to-mode transforms
selected long-range patch interactions
```

硬边界：

```text
不能形成dense 15120x15120或更大matrix
不能每rank复制完整factor
rank必须按directional block报告
必须有holdout action error
```

这是 full-interface route出现明确正信号后的压缩层，不应先于正确 operator/action。

---

## 6. C1：transmission-variable HDG/CHDG

另一条长期路线是更换离散：

```text
element interior E/H
-> element-local elimination
-> only transmission variables on skeleton remain global
```

近期 time-harmonic Maxwell CHDG 工作使用 transmission variables并研究 hybridized fixed-point
或 Krylov迭代。它可能使 wave transmission更自然地进入 global skeleton system。

但对本项目代价很大：

```text
重写Nedelec conforming离散
重做Floquet constraints
重做physical DtN
重做recovery和official R/T/A
重新建立全部authority
```

所以它只在 conforming Full3D/Hybrid factor-free路线长期无解时，作为独立新任务评估。

---

## 7. C2：carrier envelope 的正确定位

carrier enrichment只保留：

```text
E1 manufactured identity
E2 multi-diffraction tiny grating
E3 conditional fixed regular 3D grating
```

任何 E2不能同时取得 accuracy和至少2x unknown reduction，就停止。不得实现复杂 carrier
adaptivity，也不得把全部 DtN channels复制成 volume carriers。

---

## 8. 当前推荐顺序

```text
Codex Task040:
    full-interface -> moving-PML -> adaptive Schwarz

parallel branch:
    A1 NumPy symbol oracle
    -> A1 small x/y FFT + z solve
    -> A2 fixed LOR H(curl) design

only after positive solver signal:
    B1 mixed precision
    B2 recycling
    B3 directional compression

long-term fallback:
    C1 CHDG

tiny speculative:
    C2 carrier envelope
```

---

## 9. 明确停止的方向

```text
plain ILU/BLR parameter menus
Route C 256/512/1000
automatic reference-blind hp campaign
all physical channels as global volume carriers
explicit full DtN W
global sparse direct factor
dense global coarse factor
```
