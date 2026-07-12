# 研究路线与负结果

本文件解释哪些方法曾有正信号、为何没有进入普通默认路径。负结果用于避免重复试错，不表示这些算法在所有 Maxwell 问题上无效。

## 历史比较

| 路线 | 实际观察 | 当前结论 |
|---|---|---|
| 黑盒 GMRES/FGMRES/BiCGStab + Jacobi/ASM/ILU/GAMG/FieldSplit | target 不具 production 收敛性 | 不再只调 PETSc profile 名称 |
| MUMPS BLR | p=2 h=2 direct 可给低残差/RTA，h=1.5 资源仍失败 | direct fallback，不是低内存迭代终点 |
| complex AMS/HX | 当前 PETSc/hypre 组合崩溃/生命周期风险 | 不在默认 complex 路径启用 |
| real-split AMS/HX FE-only | p=2 h=5 正定代理问题有强正信号 | 可作 FE 工具，但不能代表完整 DtN 系统 |
| FE-AMS + auxiliary identity | auxiliary residual 占主导，改善有限 | block diagonal 耦合太弱 |
| sampled Schur correction | p=1 有正信号，p=2 h=5 未扩展 | 低维 lift 不足，且 MPI production 风险大 |
| matrix-free exact condensation | 代数等价通过 | 保留并成为正式算子 |
| fixed coarse + shifted physical slabs | h=5/3/2 MPI4 通过 | 当前限定生产档 |

## 为什么 FE-only 正信号不能直接外推

完整系统含 DtN 辅助耦合。只预条件 F 而把辅助块当 identity，会让 residual 经过 C/D 耦合重新回到 FE。Task 15/19 的诊断表明慢方向确实集中在端口相关分量，但用正定 AMS 代理近似 `F^{-1}C` 不足以表示不定 Maxwell 的真实 lift。

## AMS/HX 的保留价值

AMS/HX 基于离散 de Rham 结构和梯度空间，适合 H(curl) 正定 Maxwell-like 算子。它仍可能作为更成熟域分解中的局部 solver；但本仓库当前复杂数构建、p=2 高阶、MPC 和生命周期组合没有达到可维护生产状态，所以不应被普通 `main.py` 暗中启用。

## 当前突破的关键

成功路线同时解决三件事：

1. exact condensation 先消去小辅助块；
2. 75D coarse 捕获跨域 Floquet 慢模；
3. shifted physical slab 提供可分布的局部传播近似。

这比“换一个 Krylov 名称”更接近问题结构。

## 尚可研究但未承诺

- 自适应 spectral coarse space；
- impedance/optimized Schwarz 或 sweeping；
- 针对多层背景的近似逆；
- h<2 的分层网格与多级粗空间；
- AMS/HX 作为 slab 内部 solver 的稳定 complex/real-split 工程化。

开展新路线前必须定义 stop condition、直接/解析参考、三残差、RSS 与 RTA Gate，且实验代码与 ordinary default 隔离。更长历史数据见 `maxwell_iterative_preconditioners_task012.md` 和各 Task outcome。
