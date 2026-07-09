# Next Decision

## Decision

停止把 `top_bottom_y` low-dimensional true-FE sampled Schur 作为 p=2 主线继续加深。下一轮应切换到 impedance domain decomposition / sweeping / two-level Schwarz 类路线。

## Why

Task019 证明：p=2 的 residual 确实集中在 selected auxiliary modes，但低维 Schur basis 不能有效消除它。这个失败形态和文献线索一致：time-harmonic Maxwell 的高频不定问题通常需要 impedance transmission、sweeping 或 adaptive coarse space，而不是仅靠正定 Maxwell AMS/HX 的局部 lift。

## Local Paper Signals

| paper file | relevant signal |
|---|---|
| `0610531v5.pdf` | optimized Schwarz for Maxwell |
| `2606.04982v1.pdf` | overlapping DDM with impedance boundary conditions for heterogeneous time-harmonic Maxwell |
| `2501.18305v2.pdf` | two-level weighted Schwarz with adaptive coarse space |
| `1809.05634v1.pdf` | sweeping preconditioner for quasi-periodic layered media |
| `1007.4291v2.pdf` | moving-PML sweeping preconditioner for indefinite waves |
| `A_Novel_Matrix-Free_Finite_Element_Method_for_Time-Harmonic_Maxwells_Equations.pdf` | high-order matrix-free FEM motivation |

## Candidate Task020 Routes

| route | why |
|---|---|
| impedance DDM / optimized Schwarz | 直接针对 time-harmonic Maxwell 不定传播，能处理子域间 outgoing 信息传递 |
| layered/sweeping preconditioner | 当前结构是 z 分层 grating + top/bottom port，天然适合 sweep |
| two-level weighted Schwarz with adaptive coarse space | 文献中对带吸收 Maxwell 有鲁棒 GMRES 思路，可能比固定 `top_bottom_y` 空间更强 |
| matrix-free high-order FE matvec + DDM preconditioner | p=2 组装矩阵和 Python/PETSc PC 已接近 14GB 内存上限 |

## Closed For Now

| route | reason |
|---|---|
| full p=2 h=2 | p=2 h=5 gate failed |
| full 708-mode Schur | 主导 mode 已定位，扩大 mode 不解决 FE coupling |
| PETSc selected FE-AMS same process | 生命周期风险仍在 |
| production R/T/A integration | 未达到 `1e-6`，也未达到 minimum useful gate |
