# 3D 直接求解器 h=2.5 profile 对比报告

## 2026-07-02 更新：OOC 残留文件已自动化管理

首轮 h=2.5 `mumps_ooc` 测试曾留下约 9.7 GB OOC 文件。现在代码已改为：

```text
case_status = completed:
  自动删除 OOC 文件，summary 记录 removed_file_count / removed_file_bytes。

case_status != completed:
  保留 OOC 文件，summary 记录 retained_on_failure、tmpdir、residual_file_count、residual_file_bytes。
```

因此同类成功运行不再需要手动清理 `mumps_ooc_files/`；失败运行仍会保留现场并在报告字段中提示路径和大小。

## 2026-07-02 更新：根据测试结果清理代码入口

当前代码已经只保留：

```text
default
mumps_ooc
```

筛选结论：

| profile | 是否保留在代码里 | 原因 |
| --- | --- | --- |
| `default` | 保留 | 日常直接法入口；MPI 下使用 MUMPS |
| `mumps_ooc` | 保留 | 本轮 h=2.5 测试中内存最低，且是当前唯一有现实意义的直接法内存缓解手段 |
| `mumps` | 删除 | 与 `default` 重复 |
| `mumps_ooc_seq_analysis` | 删除 | 能跑但没有优于 `mumps_ooc` |
| `mumps_ooc_parallel_analysis` | 删除 | h=2.5 即接近 Docker 内存上限，不适合当前工作站主线 |
| `mumps_ooc_requested_legacy` | 删除 | 只用于复现旧错误，不应保留为正式选项 |
| `mkl_pardiso` | 删除 | 当前 PETSc 镜像不支持；未来需要重新构建 PETSc/MKL 后另测 |
| `superlu_dist` | 删除 | 当前可用但 h=2.5 未在可接受时间内完成 |
| `strumpack` | 删除 | 当前 PETSc 镜像不支持 |

注意：删除这些公开 profile 不代表它们永远没有研究价值，而是当前这份代码的主要任务是 Maxwell 模型和边界条件验证，过多求解器选项会增加理解成本。后续如果专门做“像 COMSOL 一样的大规模 direct solver”，应该单独建立 PETSc build / 服务器求解器评测，而不是把实验入口继续混在主代码中。

## 2026-07-01 首轮结果

测试对象：

```text
stage_case = stage4_block_grating
boundary = dtn_port
stage4_dtn_order_policy = zero_order
nedelec_degree = 1
mesh_target_size = 2.5 nm
MPI ranks = 8
```

注意：本测试使用 `zero_order` DtN，只作为求解器效率和内存诊断，不作为真实 grating 多衍射级物理结论。当前 R+T 约 0.616，说明 zero-order truncation 对该物理问题不够完整，但所有完成的 solver profile 得到相同 R+T，可用于比较求解器。

## PETSc 外部包可用性

当前 Docker 镜像中 PETSc 外部包状态：

| package | available |
| --- | --- |
| MUMPS | True |
| PT-SCOTCH | True |
| ParMETIS | False |
| MKL PARDISO | False |
| SuperLU_DIST | True |
| STRUMPACK | False |

## h=2.5 profile 对比表

| profile | status | factor solver | DOF | nnz | nnz/row | solve 秒 | total DtN 秒 | max RSS MB | OOC 残留 | R+T |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `default` | completed | mumps | 300940 | 9978862 | 33.16 | 288.01 | 317.06 | 2128.43 | 0 | 0.6164873424 |
| `mumps` | completed | mumps | 300940 | 9978862 | 33.16 | 263.76 | 271.71 | 2240.82 | 0 | 0.6164873424 |
| `mumps_ooc` | completed | mumps | 300940 | 9978862 | 33.16 | 247.72 | 249.03 | 1932.96 | 9.70 GB | 0.6164873424 |
| `mumps_ooc_seq_analysis` | completed | mumps | 300940 | 9978862 | 33.16 | 294.56 | 295.57 | 2048.94 | 9.73 GB | 0.6164873424 |
| `mumps_ooc_parallel_analysis` | stopped | mumps | 300940 |  |  | 未完成 | 未完成 | 接近 12.9 GiB | 约 2.37 GB 中途文件 |  |
| `mkl_pardiso` | failed before mesh | unavailable |  |  |  |  |  | 230.38 | 0 |  |
| `superlu_dist` | stopped | superlu_dist | 300940 |  |  | 未完成 | 未完成 | 350.39 at solve begin | 0 |  |
| `strumpack` | not run | unavailable |  |  |  |  |  |  |  |  |

完成的四个 MUMPS profile 给出的矩阵和物理诊断完全一致，说明这些 profile 只是 LU 后端配置差异，不改变方程。

## 结果解读

当前 h=2.5 下，`mumps_ooc` 是本机 Docker 环境中最有希望的直接法 profile：

```text
1. 比显式 mumps 的峰值 RSS 低约 308 MB。
2. 本轮 wall solve 时间也略短，但这可能受系统缓存和 I/O 状态影响，不应过度解读。
3. 代价是产生约 9.7 GB OOC 文件，且求解结束后没有被 MUMPS 自动清理。
```

`mumps_ooc_seq_analysis` 更保守，但本轮更慢且内存略高，不是首选。

`mumps_ooc_parallel_analysis` 当前检测到 PT-SCOTCH 后进入了并行 analysis 路径，但在 h=2.5 就接近 Docker 内存上限。它不是当前工作站/Docker 配置下的推荐路径；后续可以在更大内存服务器上再测试。

`default` 在 MPI 下实际也选择 MUMPS，所以它与 `mumps` 是同一类路线。`mumps` 显式写法更适合报告复现；日常运行可用 `default`。

`mkl_pardiso` 当前 PETSc build 不支持。若目标是接近 COMSOL 的直接法体验，MKL PARDISO 是值得单独构建测试的路线。

`superlu_dist` 当前可用，但 h=2.5 测试未在可接受时间内完成。它暂时不是当前推荐求解器。

## 为什么当前不像 COMSOL 那样能算

从 assemble-only 和 h=2.5 对比可知：

```text
1. Floquet/MPC 没有让矩阵变稠：nnz/row 约 33。
2. DtN zero-order 分支没有增加 auxiliary dofs。
3. h=1.5 已能完成最终矩阵组装，说明瓶颈不是 FEM assembly。
4. 真正瓶颈是 direct LU factorization fill-in。
```

COMSOL 可以完成约 200 万自由度，通常依赖这些因素：

```text
1. 直接使用主机内存和磁盘，不受当前 Docker 13.65 GiB 内存上限限制。
2. 高度优化的 PARDISO/MUMPS 直接求解器和排序策略。
3. 自动 out-of-core 管理和更成熟的磁盘临时文件策略。
4. 共享内存多线程求解器可能比 MPI direct LU 少一些重复元数据。
```

当前 FEniCS/DOLFINx 路径中，原始矩阵 h=1.5 约 1.1 GB，但 LU 因子可能远超这个量级；当 Docker 内存只有十几 GB 时，MUMPS factorization 很容易变成内存和 I/O 双重瓶颈。

## 建议路线

短期推荐：

```text
1. 默认大模型先跑 assemble-only，确认 nnz/row 正常。
2. 直接法优先用 --petsc-direct-solver-profile mumps_ooc。
3. 把 mumps_ooc_files 放在快速 NVMe 上；成功运行会自动清理，失败运行保留残留用于诊断。
4. 对 h=2.5 或更细网格，不要同时启动多个求解容器。
```

中期如果坚持 direct solver：

```text
1. 在 Linux 服务器上跑，给进程更高物理内存。
2. 重建 PETSc：MUMPS + METIS/SCOTCH/PT-SCOTCH/ParMETIS。
3. 重建 PETSc：MKL PARDISO，并测试单机多线程 direct LU。
4. 对比 MUMPS OOC、MKL PARDISO OOC、SuperLU_DIST 在 h=2.5/h=2/h=1.5 的 factorization memory。
```

长期若目标是百万级以上常规计算，仍应考虑 Maxwell 专用迭代预条件器；但这不属于本轮 direct-only 任务。
