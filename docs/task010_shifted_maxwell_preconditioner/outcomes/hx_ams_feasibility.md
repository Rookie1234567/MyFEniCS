# HX / AMS Feasibility

## 结论

完整 Hiptmair-Xu / hypre AMS 仍然是下一阶段最值得研究的物理预条件器，但 task010 不应把当前 minimal positive Maxwell P 误称为 HX/AMS。当前代码只实现了 positive/shifted Maxwell operator P，并用 ASM/ILU 或 local LU 近似反演；这不是 auxiliary-space Maxwell preconditioner。

## 当前环境可行性

- Docker complex-mode 环境中 PETSc 报告有 hypre 支持。
- hypre AMS 理论上适合 H(curl) Maxwell 预条件，但需要额外提供离散梯度、坐标/边元插值或等价 auxiliary-space 数据。
- 当前 Stage 4 系统是 complex-valued、Floquet-MPC constrained、DtN-auxiliary augmented matrix；直接套 `pc_hypre_type ams` 不足以定义完整预条件器。

## 需要实现的内容

1. 为 constrained Nedelec 空间构造 compatible H1 nodal auxiliary space。
2. 构造 discrete gradient / interpolation，并处理 Floquet 周期相位约束。
3. 对 complex Maxwell 系统决定 real split 或 complex AMS 近似路径；论文中的 HX 路线采用 real split positive Maxwell block。
4. 明确 DtN auxiliary unknowns 的处理：aux block identity 只是 smoke，不是 Schur 近似。
5. 与 MUMPS-BLR 做同一 h=5/h=4/h=3/h=2 benchmark 对照。

## 建议

task011 若继续迭代求解器研究，应把 HX/AMS 作为单独任务，而不是在当前 ASM/ILU positive P 上继续调参数。
