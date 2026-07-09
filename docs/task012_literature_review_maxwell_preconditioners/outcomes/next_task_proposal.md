# 下一任务提案

## 推荐下一任务

Task013：real-split AMS/HX block preconditioner minimal prototype

## 为什么先做这个

这是当前证据最强、工程范围可控、且最可能突破 task009-task011 负结果的路线：

| 依据 | 内容 |
|---|---|
| 本地正证据 | task011 real FE-only AMS/HX 在 p=2 h=5 用 7 次迭代达到 true residual `4.024e-7` |
| 本地负证据 | complex AMS 直接崩溃；Jacobi/ASM/ILU/GAMG 均无 production candidate |
| 文献支持 | HX/AMS 是 H(curl) 正统辅助空间预条件器；time-harmonic Maxwell 可写成 real/imag block |
| 科学价值 | 如果 real AMS/HX 与 DtN/Rayleigh 模态粗空间能结合，可能形成针对周期光栅 Maxwell 的定制低内存求解路线 |

## 需要的输入

```text
docs/task012_literature_review_maxwell_preconditioners/outcomes/summary.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/recommended_routes.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/physics_custom_preconditioner_ideas.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/ams_hx_smoke_notes.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/matrix_free_matvec_feasibility.md
src/studies/run_ams_hx_smoke.py
src/solvers/common_3d_solve.py
src/solvers/dtn_port_3d.py
```

## 实现范围

最小范围：

```text
1. 新增 real-split AMS/HX smoke runner；
2. 先覆盖 FE-only complex Maxwell block；
3. 可选扩展到 reduced Stage 4 FE block，但不直接 full production；
4. 记录 G/Pi/Aalpha/Abeta/AMS setup memory；
5. 输出 residual-only 结果，不收敛不输出 official R/T/A。
```

建议不要在 Task013 做：

```text
full p=2 h=2 direct-scale run
full p=2 h=1.5 stress run
matrix-free Stage 4 MatShell
完整 RCWA-like inverse
复杂 two-level DDM
```

## 测试算例

| 阶段 | case | 目标 |
|---|---|---|
| A | FE-only complex p=1 h=10 | 验证 real split 与 AMS 不崩溃 |
| B | FE-only complex p=1 h=5 | 与 task011 real AMS 量级对比 |
| C | FE-only complex p=2 h=5 | 验证 p=2 是否仍能少步收敛 |
| D | reduced Stage 4 p=1 h=5 | 初步检查 Floquet/DtN 或 FE/aux block 影响 |
| E | optional p=2 h=5 Stage 4 diagnostic | 只在 A-D 成功后运行 |

## 成功标准

```text
1. A-C 至少一个 p=2 case true_relative_residual_norm <= 1e-6；
2. p=2 h=5 的 residual 明显优于 task011 Jacobi best；
3. 没有 PETSc/hypre signal 11；
4. 记录清楚 AMS setup RSS 和 auxiliary matrix 规模；
5. 若 Stage 4 diagnostic 收敛，R/T/A 与 direct/BLR coarse reference 一致到可解释范围。
```

## 停止标准

```text
1. FE-only p=1 h=5 即崩溃或内存不可接受；
2. p=2 h=5 true residual 仍停在 1e-1 量级；
3. real block 构造导致 direct residual 与 complex reference 不一致；
4. AMS auxiliary data 无法与 DOLFINx/Basix Nedelec 空间稳定对应；
5. 内存主要由 high-order Pi/G hierarchy 失控，且低阶 auxiliary 也无法改善。
```

## 预计时间和风险

| 项目 | 判断 |
|---|---|
| 时间 | 中等；主要是矩阵转换、real block 与 AMS auxiliary data 调通 |
| 风险 | 中高；DOLFINx/PETSc real/complex build 和 hypre AMS 接口可能有工程坑 |
| 回报 | 高；若成功，可与 Rayleigh/Floquet modal deflation 组合成真正物理预条件器 |

## 后续 Task014 草案

若 Task013 显示 real-split AMS 有收敛潜力，Task014 建议做：

```text
Rayleigh/Floquet modal deflation coarse correction
```

目标是用 DtN port 已有 modal basis 构造低维 coarse space，叠加到 Task013 的 AMS/HX PC 上，专门处理传播和近截止衍射级次导致的全局慢误差。
