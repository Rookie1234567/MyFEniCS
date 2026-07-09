# Block Preconditioner Feasibility

## 当前结构

Stage 4 DtN auxiliary formulation 的未知量可以分为：

```text
[ FE Nedelec field unknowns ; DtN auxiliary modal unknowns ]
```

本轮 shifted/positive operator P 对 FE block 构造了物理矩阵，但 auxiliary block 只放单位对角，并没有构造真实 Schur 近似。因此它只能验证 `KSP.setOperators(A, P)` 通路，不能代表完整 block preconditioner。

## task009 经验

现成 PETSc FieldSplit Schur + ASM/local LU 在 task009 已经失败，说明仅按 block 拆开而不利用 DtN 边界耦合结构，无法让该问题收敛。

## 后续可行方向

1. 显式提取 FE/aux coupling blocks。
2. auxiliary block 用小规模 dense/direct exact inverse。
3. FE block 用 MUMPS-BLR 或 HX/AMS。
4. Schur complement 可先做 lower/upper triangular block preconditioner，再测试 full Schur approximate。
5. 必须保留 official R/T/A gating：未收敛不输出正式物理解。

## 建议

block-Schur 可以作为 task011/012 的结构性开发方向，但短期不应优先于 MUMPS-BLR 工作站验证。
