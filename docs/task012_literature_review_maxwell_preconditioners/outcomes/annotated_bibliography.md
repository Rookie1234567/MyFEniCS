# 文献注释

## 强相关来源

### Fressart et al. 2025

Fressart, E., Dubois, S., Gouarin, L., Massot, M., Nowak, M., & Spillane, N. (2025). *High Performance Parallel Solvers for the time-harmonic Maxwell Equations*. arXiv:2507.13066. https://arxiv.org/abs/2507.13066

- 阅读状态：read_key_sections，本地 PDF 也已抽取关键段落。
- 相关性：非常高。它比较 PETSc/MUMPS/hypre 中的 sparse approximate inverse、RAS、Hiptmair-Xu 和 MUMPS-BLR，问题也是 complex indefinite time-harmonic Maxwell。
- 对本项目的作用：支持 task009/task010 的经验判断：普通 RAS/SAI 不够，HX/AMS 与 BLR 是更值得关注的方向。
- 限制：不是周期光栅 Floquet/DtN auxiliary port 问题；结论仍是 work in progress。

### hypre AMS documentation

hypre project. *AMS Auxiliary-space Maxwell Solver*. https://hypre.readthedocs.io/en/latest/solvers-ams.html

- 阅读状态：read_key_sections。
- 相关性：高。官方文档说明 AMS 适用于 edge finite element Maxwell variational problem，并需要 discrete gradient、constant vectors 或 high-order interpolation。
- 对本项目的作用：解释 task011 为什么必须构造 `G`、edge constant vectors / high-order auxiliary data，也解释为什么 p=2 内存可能来自额外 auxiliary matrices。
- 限制：文档以 definite/semi-definite real Maxwell 为主，不保证 complex indefinite Stage 4 安全。

### PETSc PCHYPRE documentation

PETSc project. *PCHYPRE manual page*. https://petsc.org/release/manualpages/PC/PCHYPRE/

- 阅读状态：read_key_sections。
- 相关性：高。PETSc 明确 `pc_hypre_type=ams`/`ads` 需要 auxiliary data，如 discrete gradient、interpolations、Poisson matrices、edge constant vectors。
- 对本项目的作用：为 Task013 的 PETSc 接口设计提供约束。
- 限制：接口文档不解决 task011 complex AMS crash。

### Hiptmair and Xu 2007

Hiptmair, R., & Xu, J. (2007). *Nodal auxiliary space preconditioning in H(curl) and H(div) spaces*. SIAM Journal on Numerical Analysis. https://doi.org/10.1137/060660588

- 阅读状态：skimmed。
- 相关性：高，是 HX/AMS 理论基础。
- 对本项目的作用：说明 H(curl) Maxwell 不能直接用普通 nodal AMG，需要 de Rham-compatible auxiliary space。
- 限制：主要针对 definite H(curl)/H(div)，不是本项目完整 complex indefinite scattering system。

### Kolev and Vassilevski 2009

Kolev, T. V., & Vassilevski, P. S. (2009). *Parallel Auxiliary Space AMG for H(curl) Problems*. Journal of Computational Mathematics, 27(5), 604-623. https://doi.org/10.4208/jcm.2009.27.5.013

- 阅读状态：read_key_sections。
- 相关性：高，讨论 HX auxiliary-space preconditioner 的 parallel implementation。
- 对本项目的作用：支撑 hypre AMS/HX 作为 H(curl) 预条件器，而不是 generic AMG。
- 限制：文献强调 lowest-order Nedelec，task011 使用 p=2 时需要 high-order auxiliary data 与内存审计。

### Bonazzoli et al. 2017

Bonazzoli, M., Dolean, V., Graham, I. G., Spence, E. A., & Tournier, P.-H. (2017). *Domain decomposition preconditioning for the high-frequency time-harmonic Maxwell equations with absorption*. arXiv:1711.03789. https://arxiv.org/abs/1711.03789

- 阅读状态：read_key_sections。
- 相关性：中高。它是 high-frequency time-harmonic Maxwell with absorption 的 two-level Schwarz/DDM 理论文献。
- 对本项目的作用：说明 shifted/absorbing Maxwell 可以做预条件器，但 inner solver 不能是 task010 那样的普通 ASM/ILU；需要 coarse space、overlap、impedance/DD 结构。
- 限制：边界和几何不是 Floquet/DtN 周期光栅；DDM 工程量较大。

### Beuchler, Kinnewig, and Wick 2021

Beuchler, S., Kinnewig, S., & Wick, T. (2021). *Parallel domain decomposition solvers for the time harmonic Maxwell equations*. arXiv:2105.11993. https://arxiv.org/abs/2105.11993

- 阅读状态：read_key_sections。
- 相关性：高。它显式采用 real/imag block 形式，并比较 ILU、additive Schwarz、Schur 和 block preconditioner。
- 对本项目的作用：为 real-split + block PC 提供直接类比；也佐证 task009 的普通 ILU/ASM 失败不是偶然。
- 限制：deal.II/Trilinos 路线，与 DOLFINx/PETSc/hypre 的实现细节不同。

### Jiang et al. 2018

Jiang, X., Li, P., Lv, J., Wang, Z., Wu, H., & Zheng, W. (2018). *An Adaptive Finite Element DtN Method for Maxwell's Equations in Biperiodic Structures*. arXiv:1811.12449. https://arxiv.org/abs/1811.12449

- 阅读状态：read_key_sections。
- 相关性：高。它直接讨论 biperiodic Maxwell diffraction、transparent boundary condition 和 DtN truncation。
- 对本项目的作用：说明 Rayleigh/Floquet DtN 是周期 Maxwell 的自然结构；支持把 modal unknowns 当成 coarse/Schur 预条件器对象。
- 限制：不是求解器/预条件器论文，主要是误差估计与自适应。

## 补充来源

### Liu and Ying 2018

Liu, F., & Ying, L. (2018). *Sparsifying preconditioner for the time-harmonic Maxwell's equations*. arXiv:1804.02297. https://arxiv.org/abs/1804.02297

- 阅读状态：abstract_only。
- 相关性：中等。提供 Green-function / integral-equation approximate inverse 的思路。
- 对本项目的作用：启发 layered-background 或 physics approximate inverse。
- 限制：integral formulation，不是 Nedelec FEM/DtN auxiliary；不能作为 Task013 主依据。

### Parvizi et al. 2022

Parvizi, M., Khodadadian, A., Beuchler, S., & Wick, T. (2022). *Hierarchical LU preconditioning for the time-harmonic Maxwell equations*. arXiv:2211.11303. https://arxiv.org/abs/2211.11303

- 阅读状态：skimmed。
- 相关性：中等。说明 H-matrix/H-LU 可作为 Maxwell 压缩因子化路线。
- 对本项目的作用：支持 BLR/H-matrix 作为 fallback 类别。
- 限制：仍偏压缩直接法，不是低内存物理迭代 PC。

### Li 1996 与 RCWA/Fourier modal 方法

Li, L. (1996). *Use of Fourier series in the analysis of discontinuous periodic structures*. Journal of the Optical Society of America A. https://doi.org/10.1364/JOSAA.13.001870

- 阅读状态：abstract_only。
- 相关性：中等。RCWA/Fourier modal 是周期光栅半解析方法基础。
- 对本项目的作用：支持 layered-background / RCWA-like approximate inverse 的长期方向。
- 限制：不是 FEM 预条件器；高对比和 crossed grating 的近场收敛需要谨慎。

### Weismann et al. 2015

Weismann, M., Gallagher, D. F. G., & Panoiu, N. C. (2015). *Accurate near-field calculation in the rigorous coupled-wave analysis method*. arXiv:1507.06364. https://arxiv.org/abs/1507.06364

- 阅读状态：skimmed。
- 相关性：中等。强调 RCWA 近场在材料边界处的 Gibbs/收敛问题。
- 对本项目的作用：提醒 RCWA-like PC 可以先做背景近似逆，但不要直接拿它替代 FEM truth。
- 限制：不是 Krylov PC 文献。

## 本地项目证据

### task008

- 阅读状态：full_read。
- 作用：提供 p=2 h=2 direct official reference：`R=0.0013429328462348958`、`T=0.5992132294442478`、`A=0.3994438377095067`。
- 限制：不是最终网格收敛解，只是当前本机 best-effort direct benchmark。

### task009

- 阅读状态：full_read。
- 作用：普通 PETSc iterative profiles 的负结果边界，避免重复做 Jacobi/ASM/ILU/GAMG/BoomerAMG。
- 限制：不否定真正物理预条件器。

### task010

- 阅读状态：full_read。
- 作用：BLR eps=1e-5 能复现 R/T/A；minimal shifted/positive P + ASM/ILU 不可用。
- 限制：BLR 是 fallback，不是最终低内存 iterative。

### task011

- 阅读状态：full_read。
- 作用：real FE-only AMS/HX 是最强正信号；complex AMS 直接路径不安全；matrix-free matvec 可行。
- 限制：FE-only smoke 还不是 Stage 4 solver。
