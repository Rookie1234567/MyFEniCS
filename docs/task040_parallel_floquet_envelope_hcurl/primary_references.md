# Primary references and evidence boundaries

本页只登记与并行路线直接相关的 primary papers，并明确它们能支持什么、不能支持什么。

## 1. Low-order-refined de Rham preconditioning

```text
Will Pazner, Tzanio Kolev, Clark Dohrmann,
Low-order preconditioning for the high-order finite element de Rham complex,
arXiv:2203.02465
https://arxiv.org/abs/2203.02465
```

支持：

```text
high-order H(curl)/H(div) operator
low-order-refined auxiliary discretization
spectral equivalence independent of h and p for covered positive operators
matrix-free high-order application + scalable low-order preconditioning
```

不能直接支持：

```text
unshifted indefinite time-harmonic Maxwell convergence
complex lossy Floquet/DtN system
本项目p6/h4或0.7nm pass
```

因此本项目只把 LOR 用于 positive/shifted auxiliary PC。

## 2. Fully matrix-free factor-free Maxwell multilevel

```text
Shubin Fu,
A Fully Matrix-Free Three-Grid Preconditioner for the Time-Harmonic Maxwell
Equations at Extreme Scale,
arXiv:2608.22903
https://arxiv.org/abs/2608.22903
```

支持：

```text
unshifted fine Maxwell operator
shift confined to auxiliary 2h/4h cycle
factor-free coarse strategy
matrix-free Nedelec architecture is an active research direction
```

不能直接支持：

```text
本仓库DOLFINx实现
双Floquet/Fourier-DtN identity
complex material和当前geometry的迭代数
论文规模或时间在本工作站复现
```

## 3. Absorbed/coefficient-perturbed Maxwell preconditioning

```text
Euan A. Spence,
Preconditioning FEM discretisations of the high-frequency Maxwell equations by
either perturbing the coefficients or adding absorption,
arXiv:2504.13814
https://arxiv.org/abs/2504.13814
```

支持：

```text
用不同系数或增加absorption的Maxwell FEM operator作为preconditioner有理论依据
exact operator与preconditioner operator必须严格区分
```

不能直接给出本项目唯一shift或保证某个background inverse收敛。

## 4. FFT reference-operator pattern

```text
Martin Ladecky et al.,
Optimal FFT-accelerated Finite Element Solver for Homogenization,
arXiv:2203.02962
https://arxiv.org/abs/2203.02962
```

支持的只是算法模式：

```text
regular periodic mesh
homogeneous reference problem
Fourier-space block diagonal inverse
local FE basis retained
O(N log N) reference apply
```

该论文不是 time-harmonic Maxwell，因此不能作为 A1 Maxwell数值资格。A1必须通过本仓库的
Maxwell symbol、open-z、Floquet和PDE Gate。

## 5. Transmission-variable hybridization

```text
Ari E. Rappaport, Theophile Chaumont-Frelet, Axel Modave,
A hybridizable discontinuous Galerkin method with transmission variables for
time-harmonic electromagnetic problems,
arXiv:2505.04288
https://arxiv.org/abs/2505.04288
```

支持：

```text
将element interiors局部消元
用transmission variables形成global hybridized system
wave-transmission-oriented Maxwell离散值得作为长期fallback
```

不能支持直接替换当前 conforming Nedelec production path；Floquet、DtN、lossy material和
完整后处理均需重建。

## 6. Mixed precision and recycling

```text
Eda Oktay, Erin Carson,
Mixed Precision GMRES-based Iterative Refinement with Recycling,
arXiv:2201.09827
https://arxiv.org/abs/2201.09827
```

支持：

```text
low-precision preconditioner/factors
working-precision residual refinement
recycling across repeated correction solves
```

不能证明当前 indefinite Maxwell一定满足 mixed-precision convergence条件。只有 complex128
候选已有收敛信号后，才允许把PC/local service降精度。

## 7. Repository evidence

```text
Task030:
    matrix-free/transfer/local lifecycle infrastructure有正证据
    但旧792D p1 coarse不是成功GMG

Task039:
    5nm Full3D matrix-free outer + old slab PC在4000步停于约0.155

Task040:
    fixed 776 interface family和Route C无正信号

Task035e:
    local-h/local-p组件可用
    automatic reference-blind multi-goal hp candidate不存在
```

这些仓库事实决定当前优先级：

```text
structured background / full-interface physics
+
fixed LOR matrix-free local service
```

高于重新开展自动 hp 或全局 carrier expansion。
