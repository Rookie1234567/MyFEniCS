# Task032 Phase 6c 内部模态稀疏耦合块

## 1. 本子步骤的边界

`src/coupling/hybrid_internal_modes.py` 把 Phase 5 的二维左右模投影、Phase 4 的稳定传播和
Phase 6a/6b 的上下局部 FEM-DtN 块连接起来。本步只建立内部接口所需的稀疏矩阵和小型模态块，
尚不装配最终 monolithic augmented matrix，也不调用 MUMPS，因此不产生 Hybrid R/T/A。

内部未知量按两端入射方向保存：

```text
bottom incoming = a_b+   (M)
top incoming    = a_t-   (M)
total internal unknowns = 2M
total interface equations = 2M
```

负向接口迹先投影到正向 canonical trace basis，得到一个 `M x M` 小矩阵；不会把正、负两套迹
直接拼成伪 `4M` 接口空间。传播只使用 `P+` 和 `P-` 的被动衰减因子，不形成 growing inverse。

## 2. 单接口稀疏块

`HybridInterfaceModeBlocks` 为 bottom/top 各保存：

```text
projection:        M x N_local_augmented
positive_traction: N_local_augmented x M
negative_traction: N_local_augmented x M
negative_trace_to_positive: M x M
```

前三者是分布式 PETSc AIJ；只有与模态数相关的映射和传播因子可以作为小型 dense 数组复制。
代码不会建立 `N_interface x N_interface` dense 矩阵，也不会把完整三维场或完整二维模态
allgather 到 rank 0。

接口投影不能直接复用二维截面的 raw Gram，因为三维局部 Nédélec/MPC 坐标表示会改变离散表面
内积。实现先把左右迹提升到每个真实接口，组装 surface Gram，再求其小型逆。条件数超过
`1e12` 时 fail closed；正向基的单位阵误差和负向映射都会显式记录。

## 3. 牵引与法向

对 `E=(E_x,E_y,E_z) exp(i beta z)` 和局部法向 `n=s e_z`，代码使用：

```text
curl(E) x n = s * (
    i*beta*E_x - d_x(E_z),
   -d_y(E_z) + i*beta*E_y
)
```

bottom local FEM 的 `s=+1`，top 的 `s=-1`。按照既有 Stage-4 弱式约定，插入 FE 行的是
`-traction`。一个可复用 DOLFINx Expression 依次更新场、`beta` 和法向，避免每个模态重复 JIT。

## 4. MPI 点值路由

二维截面和三维接口共享结构化 x/y 轴。初始化阶段只 allgather 小型轴坐标与 owned-cell key，
由 `(x,y) -> structured cell -> owner rank` 确定源单元；每次提升用 `alltoall` 交换请求点及两个
复切向分量。

一个关键约束是：collective 交换必须在 `Function.interpolate` 回调之外显式完成。DOLFINx 可以在
没有本地 cell 的 rank 上跳过回调；若回调内部调用 collective，不同 rank 的调用次数可能不一致并
造成死锁。当前实现先由所有 rank 计算并缓存本地点值，再用不含通信的 local-only callback 完成插值。

## 5. 验证

```bash
python -m unittest -v src.test.test_38_task032_hybrid_internal_modes
mpiexec -n 2 python -m unittest -v src.test.test_38_task032_hybrid_internal_modes
mpiexec -n 4 python -m unittest -v src.test.test_38_task032_hybrid_internal_modes
```

最终结果为 serial `4/4`、MPI2 每 rank `4/4`、MPI4 每 rank `4/4`。测试覆盖：

- `2M` unknown/equation 方阵合同；
- 无 growing inverse 的双向传播；
- bottom/top 正向和负向迹的投影 round trip；
- 显式相反法向及牵引场逐值变号；
- 投影与牵引块有限、非零且不形成 dense 接口平方块；
- MPI 下 distributed ownership，不聚集完整 field/mode。

测试使用两条解析 Bloch 切向场隔离接口代数和 ownership；真实 QEP basis、最终增广矩阵残差、
接口 E/H 连续性、MUMPS solve 与 R/T/A 属于下一子步骤。

## 6. 已记录的负结果

早期版本把通用点归属和 collective 放进插值回调，MPI 测试无法可靠退出；测试辅助函数还曾反复
创建临时 `field.x.petsc_vec` 包装器，导致 PETSc collective 次序错位。最终实现分别改成回调外的
确定性结构化路由，以及基于 owned DoF 和已有 `system.b` layout 的测试向量。长测试今后使用具名
容器、短周期日志轮询和显式删除，避免 shell timeout 留下孤儿容器。

## 7. Phase 6e target-cell 路由修复

M6 高阶对证明“只按 `(x,y)` 任选 source cell”不足以插值 Nédélec 边界值：
法向分量在二维内部边界可能双值。当前 lifter 为每个 3D target cell 的插值点
附带匹配的 2D source-cell key，并验证 cell-major/point-major 排列。新增两列的
bottom/top 映射误差由最高 `1.24e-2` 降到约 `2e-14`，通信仍只限接口点和值。
