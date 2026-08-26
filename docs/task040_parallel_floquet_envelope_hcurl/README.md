# Task040 并行研究：Floquet-carrier envelope H(curl)

> **先读：** [feasibility_reassessment.md](feasibility_reassessment.md)。本路线现已明确降级为
> `KNOWN_METHOD_FAMILY_BUT_PROJECT_FEASIBILITY_UNPROVEN`，只允许 E1/E2 tiny go/no-go；
> 不作为当前 0.7 nm 主路线，不允许在 tiny Gate 前投入 heavy run、复杂 carrier adaptivity
> 或大规模 local-carrier 开发。

## 0. 分支身份

```text
repository          = Rookie1234567/MyFEniCS
branch              = chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
base_commit         = 860141710514ee46bcaaccaaf21155f2308faa5d
base_task40_branch  = codex/20260822-task40-hybrid-side-factor-pc
creation_authority  = user explicit instruction on 2026-08-27
status              = high-risk tiny feasibility only
merge_approval      = NO
ordinary_default    = unchanged
master_write        = forbidden
task40_branch_write = forbidden from this branch
```

本分支与 Codex 正在执行的 Task040 Review V6 **并行而不竞争**：

- Codex 主线研究如何用 full-interface wave transmission、moving-PML 或 adaptive
  Schwarz 更好地求解当前 5 nm 细网格方程；
- 本分支只用很小的 manufactured/diffraction case 判断：用满足同一 Floquet 相位的平面波
  载波承担快速振荡，是否真的能在完整 Maxwell observable 保持一致时减少总未知量。

这条路线不能被解释为已经找到 0.7 nm 解法。它只回答：

> 在保持 `H(curl)` conformity、complex128 和双 Floquet 的 tiny/regular case 中，carrier
> enrichment是否有可重复、可量化的 DoF/内存收益；若 tiny case 都没有，立即停止。

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
`exp(i kappa_alpha dot x)` 表示，envelope 负责材料、几何和散射造成的剩余变化。

阅读顺序：

1. [feasibility_reassessment.md](feasibility_reassessment.md)
2. [scalability_addendum.md](scalability_addendum.md)
3. [theory_and_design.md](theory_and_design.md)
4. [method_landscape.md](method_landscape.md)
5. [codex_handoff.md](codex_handoff.md)
6. [outcomes/lightweight_reference_validation.md](outcomes/lightweight_reference_validation.md)

关键边界：

```text
physical DtN external channel inventory
!=
volume carrier active set
```

global carriers只允许 tiny E1/E2/E3 机制验证；最终 local carrier 设想在 E2 strong signal 前
不得实施。

## 2. 已准备的代码

```text
src/solvers/floquet_envelope_hcurl.py
src/test/test_318_task040_parallel_floquet_envelope.py
```

代码目前只包含参考代数、carrier identity、shifted curl、Gram/rank audit 和 UFL helper。
它们均为 opt-in research helper，不从公共 solver API 导出，也不改变任何普通路径。

## 3. 当前证据边界

已完成的是纯 NumPy 参考代数和 Python 语法验证；尚未完成：

```text
DOLFINx/UFL complex form compilation
double-Floquet MPC integration
PETSc MatNest/MatShell assembly
DtN carrier mapping
manufactured Maxwell PDE
matched-accuracy DoF comparison
5 nm authority comparison
0.7 nm reduced PDE
```

因此当前状态只能称为：

```text
FLOQUET_ENVELOPE_REFERENCE_ALGEBRA_PREPARED
```

不能称为 solver pass、DoF reduction pass 或 0.7 nm feasibility pass。
