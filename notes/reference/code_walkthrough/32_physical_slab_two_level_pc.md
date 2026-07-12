# 物理分片两级预条件器

## sparse coarse vectors

`SparseCoarseVector(indices,values,global_size)` 在 `__post_init__` 验证形状/排序；`compress_petsc_vector` 只存超过阈值的全局项。`storage_bytes` 用于内存审计。

## `SparseGalerkinTwoLevelPc`

构造阶段：

1. 接收 matrix-free operator 和 sparse basis；
2. 重建每列并执行真实 `A*z_j`；
3. 形成 `Z^H A Z`；
4. 检查 rank/condition 并 dense factor；
5. 可连接 smoother。

`apply` 计算 coarse correction、更新 residual，再调用 smoother。diagnostics 暴露 coarse rank/condition/action error/basis bytes/apply count。`destroy` 释放 PETSc work vectors 和 smoother 引用。

## slab 构造

benchmark `_complete_physical_slabs` 在每 rank 由本地 cell midpoint 选择 z 范围，转成 global DOF；`gather_global_subdomain_indices` 合并为完整子域。`balanced_subdomain_owners` 按行数分配 16 个 slab。

## `DistributedPhysicalSlabSmoother`

每个 owner：

1. 创建全局/局部 scatter；
2. 提取 shifted-F submatrix；
3. 建 local GMRES + ILU factor；
4. apply 时收集 RHS、owner 解、reverse ADD 回全局；
5. sm2 用固定两步 inner GMRES 组合一次 Schwarz PC 和真实 action。

空 owner、重叠、两色装配、重复 apply 和 destroy 都有 MPI test。`global_factor_rows/nnz` 与 max/min owner rows 写入 diagnostics，解释总 RSS。

## 限制

类本身可接收不同 subdomain，但“qualified”只属于 benchmark config 的 16 slab、overlap .25、shift .1、ILU1、sm2。调用类成功不自动获得生产标签。
