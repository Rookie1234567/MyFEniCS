# Matrix-Free Matvec Feasibility

## 结论

FE-only Maxwell 块可以用 UFL action 实现 matrix-free matvec，并且与 assembled matrix matvec 在双精度舍入误差范围内一致。

## 验证方式

新增 `src/studies/run_matrix_free_matvec_smoke.py`。脚本对同一个 Nedelec 函数 `x` 同时计算：

- assembled matrix 路线：`A.mult(x, y_matrix)`
- matrix-free 路线：`assemble_vector(action(a, x))`

然后比较 `||y_matrix - y_action|| / ||y_matrix||`。

## 结果

| 模式 | p | h (nm) | 矩阵行数 | nnz | assembled matvec norm | action matvec norm | relative action error | RSS upper (GB) | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| complex | 1 | 5 | 5183 | 145223 | 95.8143360387 | 95.8143360387 | 3.2593413692e-16 | 0.359 | matvec 一致 |
| complex | 2 | 5 | 37446 | 3558492 | 6761.3717056641 | 6761.3717056641 | 7.5632180288e-16 | 0.445 | matvec 一致 |

- complex `p=1 h=5`：relative action error `3.2593413692268053e-16`，RSS upper `0.359 GB`。
- complex `p=2 h=5`：relative action error `7.563218028818796e-16`，RSS upper `0.445 GB`。

## 还不能直接生产使用的原因

这个烟测只覆盖 FE-only positive Maxwell 块。正式 Stage 4 还需要处理：

- Floquet MPC 约束后的向量映射。
- DtN auxiliary 增广变量。
- complex 系统的 real-imag split 预条件器。
- 与 KSP/PC 的 MatShell 或 Python PC 接口集成。

## 是否值得继续

值得。matrix-free 不会单独解决收敛问题，但它可以降低 A 矩阵存储压力，并与 real-split AMS/HX 预条件器结合。建议下一轮先做 real-split AMS 的 assembled prototype，确认收敛后再做 matrix-free 化。
