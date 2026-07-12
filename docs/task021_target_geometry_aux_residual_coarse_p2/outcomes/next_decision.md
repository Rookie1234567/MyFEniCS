# Next Decision

## 结论

Task021 已经允许进入下一层验证：p=2 h=5 target reduced Stage4 system 达到 production-like true residual，因此可以开启 p=2 h=2 solver preflight，并规划 converged iterative solution 的 official R/T/A validation。

## 下一任务建议

| 优先级 | 任务 | 目标 | 停止条件 |
|---:|---|---|---|
| 1 | p=2 h=2 SPILU coupled PC m=1 preflight | 验证最小模式 top `(0,0)` s 是否仍能到 1e-6 | residual <= 1e-6 或资源接近 14 GB |
| 2 | p=2 h=2 SPILU block Schur PC preflight | 验证 full-aux Schur-aware PC 是否保持 2 个数量级以上优势 | residual <= 1e-6 或 SPILU setup 失败 |
| 3 | PETSc `PCShell` / `MatShell` prototype | 把 SciPy prototype 迁移到 solver-like PETSc 接口 | single-rank PETSc residual 与 SciPy 对齐 |
| 4 | official R/T/A validation | 用 converged iterative solution 输出 R/T/A/A_volume | 与 direct p=2 h=5 或 h=2 reference 对齐 |
| 5 | MPI safety audit | 检查 factorization / coarse selector / mode mapping 的并行语义 | MPI=2 smoke 通过或明确标注 serial-only |

## h=2 preflight 起点

| 候选 | 为什么先试 | 风险 |
|---|---|---|
| SPILU coupled PC m=1 | h=5 上只用一个物理模式就达到 `9.865457e-7`；coarse 空间最小 | h=2 时 FE block 更大，SPILU fill 可能过高 |
| SPILU coupled PC m=2 | h=5 上 `9.412760e-7`，比 m=1 略低 | 比 m=1 更慢 |
| SPILU block Schur PC full aux | h=5 上 `2.430285e-7` 且 history points=2 | full aux Schur 和 SPILU setup 更重 |
| exact FE-block Schur | 用作诊断上界 | 不适合作为低内存方案 |

## official R/T/A 参考

下一任务若计算 converged iterative solution 的 R/T/A，可先对齐已有 direct reference：

| reference | h_nm | R | T | A_volume | closure |
|---|---:|---:|---:|---:|---:|
| p=2 direct | 5.0 | 0.0890216029 | 0.4425882787 | 0.4683901184 | 1.0 |
| p=2 direct | 2.0 | 0.00134293285 | 0.5992132294 | 0.3994438377 | 1.0 |

## 不建议继续的事

1. 不再调 aux-only 参数；它在目标模型上已经失败。
2. 不再调 diag FE response；它只能把 residual 从 0.2026 推到约 0.18。
3. 不把 exact FE-block Schur 当成最终低内存迭代器。
4. 不直接进入 h=1.5 或 h=1；task008 已经显示这些规模会触发 direct/KSP setup 或 assemble 边界。
