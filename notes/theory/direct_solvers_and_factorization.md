# 直接求解器与因子分解

## 1. 系统性质

频域 Maxwell + 损耗 + 出射 DtN 的矩阵通常是复数、非 Hermitian、不定。普通 3D 路径使用 PETSc `KSPPREONLY + PCLU`，即不做 Krylov 迭代，直接调用稀疏 LU 后端。

## 2. default

串行由 PETSc 可用 LU 处理；MPI 时代码只接受真正的并行 LU 包，当前限定环境为 MUMPS。若 MPI 镜像没有 MUMPS，`common_3d_solve._prepare_direct_lu_options_for_comm` 明确拒绝运行，防止把每 rank 局部 LU 静默当成全局解。

## 3. MUMPS OOC

`mumps_ooc` 设置 `ICNTL(22)=1` 和工作空间余量。MUMPS 可把部分因子写到 `results/.../mumps_ooc_files`。成功后代码清理临时文件；失败时保留现场并报告文件数/字节。

OOC 主要交换 RAM 与磁盘 I/O，不减少矩阵阶数，也不保证分析/排序阶段一定低内存。

## 4. MUMPS BLR

`mumps_blr` 设置 `ICNTL(35)=1`、`CNTL(7)=1e-5`。BLR 对 frontal matrix 的块做低秩近似，仍完成 MUMPS 直接因子分解。阈值越松通常压缩越强、误差风险越高。

必须同时验证：真残差、direct baseline 的 R/T/A 差、RSS 和耗时。它不是 FGMRES，也不是“迭代求解器 1”。MUMPS 官方说明见 <https://mumps-solver.org/doc/userguide_5.8.2.pdf>。

## 5. assemble-only

`matrix_diagnostics_assemble_only` 只组装最终系统和矩阵统计，跳过 factor/solve。它能回答行数、nnz、装配 RSS，但不能回答 LU 能否分配因子，更不能产出可信 RTA。过去出现“装配 RSS 可接受但 direct 失败”，原因正是稀疏 LU fill-in 在 factorization 才发生。

## 6. 内存字段

| 字段 | 解释 |
|---|---|
| per-rank RSS | 单个 MPI 进程峰值 |
| total peak RSS | 各 rank 峰值和的上界 |
| current total | 某一监控时刻总驻留 |
| OOC bytes | 因子落盘体积，不等于节省 RAM |

工作站容量判断看全进程树总峰值，并同时看 swap。`run_3d_memory_profile.py` 监控子进程树；benchmark 迭代 record 使用 MPI allreduce 汇总 rank RSS。

## 7. 当前角色

direct 是小/中网格基线和迭代 RTA 对照；14 GB 下 p=2 h=2 的工程路径是限定 MPI4 迭代器。不要因 direct 更“精确”就无视资源边界，也不要因迭代收敛就删除 direct 交叉验证。
