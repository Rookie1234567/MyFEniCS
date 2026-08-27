# Task040 并行研究：规则结构求解器组合与 carrier tiny probe

> **当前优先级：**
>
> 1. [alternative_methods_portfolio.md](alternative_methods_portfolio.md)：全部路线与止损顺序；
> 2. [structured_background_fft_hcurl.md](structured_background_fft_hcurl.md)：规则周期结构的
>    Floquet FFT/Kronecker background inverse；
> 3. [low_order_refined_hcurl.md](low_order_refined_hcurl.md)：固定 LOR matrix-free H(curl)，
>    **不是** h/p 自适应；
> 4. [feasibility_reassessment.md](feasibility_reassessment.md)：carrier enrichment已降级为
>    `KNOWN_METHOD_FAMILY_BUT_PROJECT_FEASIBILITY_UNPROVEN`，只允许 tiny E1/E2/E3。

## 0. 分支身份

```text
repository          = Rookie1234567/MyFEniCS
branch              = chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
base_commit         = 860141710514ee46bcaaccaaf21155f2308faa5d
base_task40_branch  = codex/20260822-task40-hybrid-side-factor-pc
creation_authority  = user explicit instruction on 2026-08-27
status              = parallel research portfolio
merge_approval      = NO
ordinary_default    = unchanged
master_write        = forbidden
task40_branch_write = forbidden from this branch
```

本分支与 Codex 正在执行的 Task040 Review V6 **并行而不竞争**：

```text
Codex Task040:
    full-interface wave transmission
    moving-PML
    adaptive impedance Schwarz
    factor-free local service

本分支优先:
    structured Floquet-background inverse
    fixed low-order-refined matrix-free H(curl)

本分支低优先级:
    carrier envelope tiny go/no-go
```

核心原则是同时解决两类增长：

```text
DoF数量
+
每个DoF的operator/PC bytes
```

但不会重新押注自动 reference-blind h/p 自适应。Task035e 已证明 local-h/local-p组件有价值，
却没有形成可靠的多目标 accepted adaptive candidate。

## 1. A1：structured Floquet-background H(curl)

精确方程不变：

```math
A x=b.
```

选择 constant 或 z-layered periodic background `A0`，仅作为右预条件器：

```math
P_\sigma^{-1}
=
(A_0+\sigma M)^{-1}.
```

利用规则 x/y 周期结构：

```text
distributed FFT x/y
-> independent bounded z solves per (m,n)
-> inverse FFT x/y
```

目标：

```text
no 3D factor
storage O(N)
apply O(N log N_xy)
arbitrary-3D heterogeneity仍由exact A处理
```

已准备 reference code：

```text
src/solvers/floquet_background_hcurl.py
src/test/test_319_task040_parallel_background_hcurl.py
```

当前只验证 fully-periodic homogeneous Fourier symbol；open-z、DOLFINx、MPC和physical DtN
仍未验证。

## 2. A2：fixed LOR matrix-free H(curl)

它不是自动 h/p：

```text
mesh规则不变
p固定
每个高阶element建立确定性的low-order-refined auxiliary complex
```

fine p6 operator使用 matrix-free action，LOR operator只用于 shifted/positive auxiliary solve：

```text
FGMRES on exact complex128 Maxwell
+
LOR AMS/AMG/Schwarz preconditioner
```

目标是删除 high-order AIJ和增长型 local factors，而不是决定哪里细化。

## 3. carrier envelope：只保留 tiny probe

场表示：

```math
\mathbf E_h(\mathbf x)
=
\sum_{\alpha\in\mathcal C}
\exp(i\boldsymbol\kappa_\alpha\cdot\mathbf x)
\mathbf u_{\alpha,h}(\mathbf x).
```

该方法族有先例，但对本项目可行性未建立。只允许：

```text
E1 manufactured identity
E2 multi-diffraction tiny grating
E3 conditional regular 3D grating
```

E2不能同时保持完整 Maxwell observables并降低至少2x unknown，即停止；不做复杂 carrier
adaptivity，不把所有 physical DtN channels复制成 volume carriers。

已有参考代码：

```text
src/solvers/floquet_envelope_hcurl.py
src/test/test_318_task040_parallel_floquet_envelope.py
```

## 4. Codex handoff

读取：

- [codex_handoff_parallel_methods.md](codex_handoff_parallel_methods.md)
- [codex_handoff.md](codex_handoff.md)

优先运行：

```bash
python -m pytest -q \
  src/test/test_318_task040_parallel_floquet_envelope.py \
  src/test/test_319_task040_parallel_background_hcurl.py
```

当前隔离 NumPy参考结果：

```text
test318 = 6 passed
test319 = 6 passed
```

项目 qualified complex128环境仍需重跑，不得把纯 NumPy通过写成 DOLFINx/PDE pass。

## 5. 当前证据边界

尚未完成：

```text
DOLFINx/UFL background MatShell
x/y FFT + open-z solve
double-Floquet MPC integration
physical DtN integration
LOR basis/commuting transfer
5 nm authority comparison
0.7 nm reduced PDE
```

当前最强状态只能称为：

```text
STRUCTURED_BACKGROUND_REFERENCE_ALGEBRA_PREPARED
FLOQUET_ENVELOPE_REFERENCE_ALGEBRA_PREPARED
```

不能称为 solver pass、memory-scaling pass 或 0.7 nm feasibility pass。
