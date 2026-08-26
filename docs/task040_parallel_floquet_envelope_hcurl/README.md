# Task040 并行研究：Floquet-carrier envelope H(curl)

## 0. 分支身份

```text
repository          = Rookie1234567/MyFEniCS
branch              = chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
base_commit         = 860141710514ee46bcaaccaaf21155f2308faa5d
base_task40_branch  = codex/20260822-task40-hybrid-side-factor-pc
creation_authority  = user explicit instruction on 2026-08-27
status              = parallel research preparation
merge_approval      = NO
ordinary_default    = unchanged
master_write        = forbidden
task40_branch_write = forbidden from this branch
```

本分支与 Codex 正在执行的 Task040 Review V6 **并行而不竞争**：

- Codex 主线研究如何用 full-interface wave transmission、moving-PML 或 adaptive
  Schwarz 更好地求解当前 5 nm 细网格方程；
- 本分支研究如何从离散层面减少“每个波长必须产生的体自由度”，即用满足同一 Floquet
  相位的平面波载波承担快速振荡，让标准 Nédélec envelope 主要描述材料、几何和散射引起的
  缓变部分。

这条路线的目标不是立即替换现有 production solver，而是回答：

> 能否在保持 `H(curl)` conformity、complex128、双 Floquet 和任意三维材料耦合的前提下，
> 把 0.7 nm 问题的自由度增长从朴素三维均匀细化的 `lambda^-3` 包络显著压低？

## 1. 核心方法

场写为多个 Floquet-compatible carrier 与 Nédélec envelope 的叠加：

```math
\mathbf E_h(\mathbf x)
=
\sum_{\alpha\in\mathcal C}
\exp(i\boldsymbol\kappa_\alpha\cdot\mathbf x)
\mathbf u_{\alpha,h}(\mathbf x).
```

每个 `u_alpha,h` 仍属于标准 `H(curl)` Nédélec 空间。快速振荡由
`exp(i kappa_alpha dot x)` 表示，envelope 负责：

```text
material contrast
non-separable 3D geometry
mode conversion
localized defect/interface fields
carrier之间的耦合
```

详细弱式、边界条件、矩阵结构、内存模型和 Gate 见：

- [scalability_addendum.md](scalability_addendum.md)（**先读；覆盖 global carrier 扩展边界**）
- [theory_and_design.md](theory_and_design.md)
- [method_landscape.md](method_landscape.md)
- [codex_handoff.md](codex_handoff.md)
- [outcomes/lightweight_reference_validation.md](outcomes/lightweight_reference_validation.md)

关键可扩展性边界：

```text
physical DtN external channel inventory
!=
volume carrier active set
```

global carriers只用于早期机制验证，固定 `16`、条件 `32`；0.7 nm production目标是附着在
局部全局 Nédélec support 上的 bounded carrier active sets。

## 2. 已准备的代码

```text
src/solvers/floquet_envelope_hcurl.py
src/test/test_318_task040_parallel_floquet_envelope.py
```

代码目前包含：

```text
2D direct/reciprocal lattice
Bloch-compatible carrier generation
Floquet multiplier identity audit
shifted curl product rule
cross-carrier phase
isotropic Maxwell block reference density
sampled carrier Gram/rank audit
deterministic carrier pruning
naive wavelength/memory scaling helpers
UFL shifted-curl and block-integrand helpers
```

它们均为 opt-in research helper，不从公共 solver API 导出，也不改变任何普通路径。

## 3. 当前证据边界

已完成的是纯 NumPy 参考代数和 Python 语法验证；尚未完成：

```text
DOLFINx/UFL complex form compilation
double-Floquet MPC integration
PETSc MatNest/MatShell assembly
DtN carrier mapping
manufactured Maxwell PDE
5 nm authority comparison
0.7 nm reduced PDE
```

因此当前状态只能称为：

```text
FLOQUET_ENVELOPE_REFERENCE_ALGEBRA_PREPARED
```

不能称为 solver pass、DoF reduction pass 或 0.7 nm feasibility pass。
