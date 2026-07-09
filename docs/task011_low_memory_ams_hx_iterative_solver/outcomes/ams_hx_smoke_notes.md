# AMS/HX Smoke Notes

## 结论

当前环境里，hypre AMS/HX 对 real-valued H(curl) FE-only Maxwell 块是可用的，但不能直接用于 complex-valued Stage 4 系统。

## 必答问题

`hypre` 是否可用：可用，`PETSc.Sys.hasExternalPackage("hypre")` 为 True。

AMS 是否可设置：可设置，`pc.setHYPREDiscreteGradient(G)` 和 `pc.setHYPRESetEdgeConstantVectors(...)` 均可调用。

G 矩阵怎么构造：使用 `dolfinx.fem.petsc.discrete_gradient(Q, V)`，其中 `Q` 是 Lagrange H1 空间，`V` 是 Nedelec H(curl) 空间。

H1 空间如何选：本轮采用 `degree + 1` 的 Lagrange 空间。对 `N1curl p=1` 使用 H1 degree 2，对 `N1curl p=2` 使用 H1 degree 3。

complex mode 是否可用：不可直接使用。最小 `p=1 h=10` complex AMS smoke 复现 `malloc(): invalid size` 与 PETSc signal 11。

Floquet / MPC / DtN 是否已接入：尚未接入。当前 smoke 只验证 FE-only positive Maxwell 块，未包含 Stage 4 的 complex DtN auxiliary 系统。

## 数值结果

| 模式 | p | h (nm) | H1 degree | 矩阵行数 | G 矩阵尺寸 | 迭代 | true relative residual | RSS upper (GB) | 结论 |
|---|---:|---:|---:|---:|---|---:|---:|---:|---|
| real | 1 | 10 | 2 | 906 | 906 x 2233 | 3 | 1.8962457516e-7 | 0.428 | 通过 |
| real | 1 | 5 | 2 | 5183 | 5183 x 13167 | 4 | 4.0339860323e-8 | 0.991 | 通过 |
| real | 2 | 5 | 3 | 37446 | 37446 x 42160 | 7 | 4.0244411713e-7 | 6.930 | 通过 |
| real | 2 | 4 | 3 | 未完成 | 未完成 | 未完成 | 无 | 12.86 GiB Docker 占用 | 内存压力停止 |
| complex | 1 | 10 | 2 | 未完成 | 已进入 AMS 路径 | 未完成 | 无 | 无 | PETSc signal 11 |

- real `p=1 h=10`：3 次迭代收敛，true relative residual `1.8962457516238405e-07`，RSS upper `0.428 GB`。
- real `p=1 h=5`：4 次迭代收敛，true relative residual `4.0339860322827845e-08`，RSS upper `0.991 GB`。
- real `p=2 h=5`：7 次迭代收敛，true relative residual `4.0244411713016064e-07`，RSS upper `6.930 GB`。
- real `p=2 h=4`：17 分钟后 Docker 内存达到 `12.86 GiB / 13.65 GiB`，未完成，已停止。
- complex `p=1 h=10`：在 AMS setup/solve 路径触发内存损坏和 PETSc SEGV。

## 判断

AMS/HX 值得继续做，但必须绕开 complex hypre AMS。下一步应做 real-imag split block preconditioner，而不是直接把 `pc_hypre_type=ams` 加到 complex Stage 4 KSP 上。
