# 面向物理结构的定制预条件器想法

## 想法 1：real-split AMS/HX block preconditioner

| 字段 | 内容 |
|---|---|
| idea_name | real-split AMS/HX block preconditioner |
| literature_basis | Hiptmair-Xu auxiliary space、hypre AMS、PETSc PCHYPRE、time-harmonic Maxwell real/imag block 文献 |
| physics_basis | complex Maxwell 的 real/imag 分裂保留原系统；AMS/HX 针对 H(curl) Nedelec 主块 |
| matrix_or_block_form | `[[Ar, -Ai], [Ai, Ar]]`，初始 PC 为 `blockdiag(B_AMS, B_AMS)` |
| how_to_apply_preconditioner | FGMRES 外迭代；每次 PC apply 将 real 和 imag 分量分别送入 real AMS KSP |
| expected_memory_cost | 中等；比 direct/BLR 低，但高阶 G/Pi/AMG hierarchy 可能显著占内存 |
| expected_convergence_benefit | 高；目标是把 Jacobi 的 `1e-1` true residual 量级降到 `1e-6` 附近 |
| implementation_steps | 先 FE-only real block；再 reduced Stage 4 FE block；再接 DtN auxiliary；最后调 p-coarsened auxiliary |
| risks | high-order AMS 内存、MPC 后 discrete gradient 一致性、complex material cross block 近似不足 |
| minimal_smoke_test | `p=1 h=5` FE-only complex matrix 的 real split，对比 complex direct residual；随后 `p=2 h=5` |
| success_criterion | true relative residual `<1e-6`，迭代数明显低于 Jacobi，RSS 不超过 BLR 同量级的一半为理想目标 |

## 想法 2：low-order / p-coarsened H(curl) auxiliary preconditioner

| 字段 | 内容 |
|---|---|
| idea_name | low-order or p-coarsened H(curl) auxiliary preconditioner |
| literature_basis | AMS/HX auxiliary-space theory；Bonazzoli 等指出高阶离散可用低阶 coarse space |
| physics_basis | p=2 主空间精度高，但预条件器只需捕捉低频/全局 H(curl) 误差 |
| matrix_or_block_form | p=2 Nedelec 主块 `A_p2`，PC 内部用 p=1 或粗网格 H(curl) operator `B_p1` |
| how_to_apply_preconditioner | 构造 p=1 prolongation/restriction 或同网格低阶 auxiliary；PC apply 中做 coarse H(curl) correction |
| expected_memory_cost | 低到中；目标是降低 task011 p=2 h=4 AMS 的 auxiliary hierarchy 内存 |
| expected_convergence_benefit | 中高；可能牺牲少量迭代数换显著内存下降 |
| implementation_steps | 记录 p=2 AMS 的 G/Pi/AMG memory；实现 p=1 auxiliary smoke；比较 p=2 h=5/h=4 |
| risks | prolongation 不兼容 Basix/DOLFINx Nedelec dof；p-coarsened correction 太弱 |
| minimal_smoke_test | FE-only p=2 h=5，用 p=1 auxiliary PC 与原 p+1 H1 AMS 对比 RSS 和迭代数 |
| success_criterion | 在 p=2 h=5 true residual `<1e-6`，RSS 低于 task011 原 AMS；p=2 h=4 不再触及 Docker memory ceiling |

## 想法 3：Rayleigh/Floquet modal deflation

| 字段 | 内容 |
|---|---|
| idea_name | Rayleigh/Floquet modal deflation |
| literature_basis | biperiodic Maxwell DtN、RCWA/Fourier modal、deflation/coarse-space Krylov 思想 |
| physics_basis | 周期光栅远场能量由少量 propagating Rayleigh orders 主导；近截止模态容易导致全局慢收敛 |
| matrix_or_block_form | `Z` 为 lifted Rayleigh/Floquet fields，coarse matrix `E = Z^* A Z` |
| how_to_apply_preconditioner | PC 或 outer correction 中加 `Z E^-1 Z^* r`；可与 AMS blockdiag 叠加 |
| expected_memory_cost | 很低；coarse dimension 约为 propagating/near-cutoff modes 数量 |
| expected_convergence_benefit | 高；如果慢误差主要是传播模态，可能显著降低 GMRES stagnation |
| implementation_steps | 从 DtN mode list 生成 top/bottom modal traces；向 FE 空间 lift；实现 small dense coarse solve；先 residual-only 测试 |
| risks | lift 到体场的向量不够接近真实误差；near-field 局部误差仍需 AMS/HX；coarse matrix 可能病态 |
| minimal_smoke_test | `p=1 h=5` 或 `p=2 h=5`，Jacobi-GMRES vs Jacobi+modal-deflation residual 曲线 |
| success_criterion | 相同 max_it 下 true residual 至少降低 10 倍；若与 AMS 叠加，迭代数明显减少 |

## 想法 4：DtN-aware FE/aux block preconditioner

| 字段 | 内容 |
|---|---|
| idea_name | DtN-aware FE/aux block preconditioner |
| literature_basis | FEM-DtN biperiodic Maxwell；block preconditioner 文献；本项目 Stage 4 auxiliary DtN 装配 |
| physics_basis | Stage 4 矩阵天然分为 FE Nedelec unknowns 和 top/bottom modal auxiliary unknowns |
| matrix_or_block_form | `[[A_FE, C], [D, A_aux]]`，FE block 用 AMS，aux block 用 exact/diagonal modal solve |
| how_to_apply_preconditioner | block diagonal 起步，随后 triangular Schur approximation |
| expected_memory_cost | 低到中；auxiliary 维数小，主要成本在 FE AMS |
| expected_convergence_benefit | 中高；比 task009 generic FieldSplit 更贴合 DtN port |
| implementation_steps | 暴露 FE/aux IS；实现 aux exact solve；把 FE PC 接 real AMS；记录 Schur residual |
| risks | `C,D` coupling 对收敛很重要，block diagonal 可能仍弱；real/complex split 后 block 结构更复杂 |
| minimal_smoke_test | reduced DtN port case，blockdiag(FE AMS, aux exact) vs FE-only PC |
| success_criterion | block PC 比只预条件 FE 主块迭代数更低，且 R/T/A 与 direct 在 converged case 一致 |

## 想法 5：layered-background / RCWA-like approximate inverse

| 字段 | 内容 |
|---|---|
| idea_name | layered-background / RCWA-like approximate inverse |
| literature_basis | RCWA/Fourier modal method、Li factorization、periodic diffraction scattering matrices |
| physics_basis | 本项目是周期光栅；在忽略或等效处理 ridge 扰动时，层状背景可用 Fourier harmonics 快速求解 |
| matrix_or_block_form | `P^-1 ≈` layered periodic background Green operator；在 x/y Fourier space 分解，在 z 方向做 transfer/scattering solve |
| how_to_apply_preconditioner | residual -> Fourier/Rayleigh coefficients -> layer solve -> lift back to FE vector |
| expected_memory_cost | 低；主要存储小 Fourier harmonic blocks |
| expected_convergence_benefit | 潜在很高；能捕捉传播相位和 DtN 边界 |
| implementation_steps | 先 flat/layered case exact-like PC；再 homogenized ridge background；最后作为 low-rank correction 叠加 AMS |
| risks | 高对比不连续导致 Fourier convergence 慢；2D periodic/crossed grating factorization复杂；与 Nedelec FE 投影复杂 |
| minimal_smoke_test | small flat-layer / layered background，把 RCWA-like apply 与 direct solution 对比 |
| success_criterion | flat/layered case 少步收敛；block grating residual 曲线优于 AMS-only 或 Jacobi |

## 想法 6：matrix-free operator + physics preconditioner

| 字段 | 内容 |
|---|---|
| idea_name | matrix-free operator + physics preconditioner |
| literature_basis | matrix-free high-order FEM 思路；本项目 task011 UFL action smoke |
| physics_basis | 主矩阵 `A` 存储和装配占内存，但收敛仍由 physics PC 决定 |
| matrix_or_block_form | `A` 用 MatShell/action；PC 用低阶 AMS、modal coarse 或 DtN block |
| how_to_apply_preconditioner | FGMRES MatShell `mult` 调用 UFL action；PC apply 调用 assembled low-order/auxiliary structures |
| expected_memory_cost | 高收益；可减少 assembled A 的 AIJ 存储 |
| expected_convergence_benefit | 本身无；依赖 Route 1-4 |
| implementation_steps | 先 assembled PC 成功；再把 FE block matvec 换成 action；最后处理 MPC/DtN auxiliary |
| risks | Python MatShell 性能、MPI ghost update、MPC lifting、DtN auxiliary action |
| minimal_smoke_test | FE-only p=2 h=5 matrix-free FGMRES + same PC，对比 assembled FGMRES residual |
| success_criterion | residual 历史一致，RSS 明显下降，R/T/A 不改变 |
