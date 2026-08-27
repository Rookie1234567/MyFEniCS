# Fixed low-order-refined matrix-free H(curl) 路线

## 0. 它与 h/p 自适应不同

本路线不回答：

```text
哪个cell细化h
哪个cell升p
```

它保持规则 mesh和固定高阶 `p`，只为每个高阶 element建立一个确定性的 low-order-refined
auxiliary representation。因此没有 DWR controller、reference-blind action selection或局部
accepted/rejected state machine。

## 1. 核心结构

fine operator：

```math
A_p:
V_p^{\mathrm{Nedelec}}
\rightarrow
(V_p^{\mathrm{Nedelec}})'.
```

不形成 high-order sparse matrix，而用 sum factorization / partial assembly施加。

构造 low-order-refined space：

```math
V_{\mathrm{LOR}},
```

和 transfer：

```math
T:
V_{\mathrm{LOR}}
\leftrightarrow
V_p.
```

对 positive de Rham operator，目标是 spectral equivalence：

```math
c_1
\langle A_{\mathrm{LOR}}v,v\rangle
\le
\langle A_p Tv,Tv\rangle
\le
c_2
\langle A_{\mathrm{LOR}}v,v\rangle,
```

其中常数尽量不依赖 `h,p`。

## 2. time-harmonic Maxwell中的用法

不能直接声称 indefinite `A` 与 LOR spectrally equivalent。建议只用于辅助 PC：

```math
P_\sigma
=
\operatorname{curl}\mu^{-1}\operatorname{curl}
-k_0^2\epsilon
-i\sigma M,
```

或：

```math
P_+
=
\operatorname{curl}\mu^{-1}\operatorname{curl}
+\tau M.
```

外层：

```text
FGMRES on exact complex128 A
```

内层：

```text
LOR sparse operator
+ AMS/AMG
+ bounded Schwarz
```

## 3. 与项目现有组件的关系

可复用：

```text
Task030 H(curl) transfer/Galerkin infrastructure
static-condensed active/master maps
MPC slave backsub/homogenize
factor-only bounded local lifecycle
```

必须新增：

```text
tensor-product interpolation-histopolation basis
fixed refined de Rham complex
matrix-free p6 cell action
Floquet-compatible LOR constraints
complex shifted auxiliary cycle
```

不得把 Task030 已失败的 792D p1 global coarse原样当作本路线。

## 4. 资源目标

```text
high-order AIJ               = 0
high-order global factor     = 0
LOR operator storage         = O(N)
local factor rows            <=1024
full basis replication       = false
FE-sized allgather           = false
```

LOR mesh未知量可能比 high-order DoF多一个常数倍，因此必须记录真实：

```text
fine DoF
LOR DoF
LOR NNZ
AMG hierarchy bytes
transfer bytes
work vectors
```

## 5. Gate

```text
L0 tensor-product basis/local exactness
L1 one-element and periodic-box commuting/action tests
L2 positive/shifted h10 and h5 solve
L3 current 5 nm side local-service pilot
```

L2 minimum：

```text
iterations ratio h5/h10 <=2
PC bytes growth <=1.3 power in DoF
```

L3 minimum：

```text
same full-interface/sweep outer residual improves >=4x
no full-cross-section factor
```

没有 L2 mesh/p robustness，不进入 5 nm h4 heavy。
