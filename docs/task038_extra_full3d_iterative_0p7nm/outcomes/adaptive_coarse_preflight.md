# Adaptive trace-harmonic coarse preflight（D0）

这里的 adaptive coarse 是一个很小的“全局误差修正空间”：局部 smoother 处理近距离误差，coarse basis 处理跨 slab 的长距离误差。它不是把完整 FE 矩阵集中到一个 rank，也不是提前宣称 0.7 nm production solver。D0 只完成身份、算术和预算核对；没有写数值核心，没有运行 D1–D4 或 PDE。

## source 与启动 preflight

| 项目 | D0 实测/记录值 |
|---|---|
| source Git SHA | `9705e6e84a4b491a7d9fc87b20e12f1938232b07` |
| base master / merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| upstream（开始前） | `9705e6e84a4b491a7d9fc87b20e12f1938232b07` |
| activation | `source scripts/activate_myfenics_wsl.sh`，marker `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| `sys.executable` | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` |
| repo `.venv` | `/home/shenjh/Projects/MyFEniCSx_task37_extra/.venv`，realpath 与上述 qualified environment 相同 |
| Python | `3.12.3` |
| MPI | Open MPI `4.1.6`，mpi4py `3.1.5`，preflight size `1` |
| PETSc / SLEPc | PETSc `3.19.6` / SLEPc `3.19.2` |
| DOLFINx / Basix | `0.10.0.post2` / `0.10.0` |
| PETSc scalar / int | `complex128` / `int32` |
| threads | `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`NUMEXPR_NUM_THREADS=1` |
| `MemAvailable` | `13,541,793,792 B` |
| system swap | total `42,949,672,960 B`，free `42,931,998,720 B`，observed used `17,674,240 B` |
| disk | total `1,081,101,176,832 B`，free `943,581,122,560 B` |

`.venv` 是当前 checkout 中的 qualified activation 入口，物理环境由它指向共享的已资格化 surrogate venv；这不是把 Windows Python 或另一套 MPI 混入本次执行。上表的 swap 是启动观察值，不是 D1–D4 的 `swap=0` 通过；D0 没有启动重型计算，后续每个正式阶段仍须重新测量并 fail-closed。

## 精确 full-space 算术

当前 full-space 行数固定为 `N=173,802`。complex128 每个系数为 `16 B`，所以一个完整向量的精确数值字节数为：

```text
N × 16 = 173,802 × 16 = 2,780,832 B
```

若保存 `Z` 与同样形状的 `AZ`，rank ladder 的精确总数值字节数为：

```text
2 × N × 16 × r = 5,561,664 × r B
```

| coarse rank `r` | `Z+AZ` 精确 bytes | 十进制 GB | MiB（`bytes / 1,048,576`） |
|---:|---:|---:|---:|
| 16 | `88,986,624 B` | `0.088986624 GB` | `84.8642578125 MiB` |
| 32 | `177,973,248 B` | `0.177973248 GB` | `169.728515625 MiB` |
| 48 | `266,959,872 B` | `0.266959872 GB` | `254.5927734375 MiB` |
| 64 | `355,946,496 B` | `0.355946496 GB` | `339.45703125 MiB` |

这里的 `Z/AZ` 数字量是 global owner-local shards 的总和，不是每个 rank 都保存的完整 basis。每个 rank 只保留自己拥有的 row shard，并通过有限的 owner/ghost 路由协作；禁止 per-rank full basis replication 和 FE-sized numeric allgather。

## 最小可实现 retained 布局预算

以下是实现上限预算，不是 D0 的实测对象大小；未知的 Python 对象、UFL/JIT cache、allocator 碎片和进程树峰值均明确保留为 `not_measured`，没有填成 0。

| owner-local item | 预算 bytes | 类型/口径 |
|---|---:|---|
| owned row IDs、shard offsets、ghost route | `16,000,000` | budget；每 rank 的本地索引/通信元数据 |
| canonical key、digest、class/phase/MPC descriptors | `8,000,000` | budget；bounded metadata，不是 numeric FE vector |
| restriction/prolongation support、PoU weights/index | `12,000,000` | budget；只保存 owner-local support |
| `E`/正交化/小型 coarse oracle workspace（`r<=64`） | `4,000,000` | budget；`E` 本身在 r64 仅 `64×64×16=65,536 B`，其余为有界工作预算 |
| 固定 source/temporary apply scratch | `16,000,000` | budget；不复制完整 basis |
| lifecycle、bounded telemetry、compact manifest buffers | `8,000,000` | budget；不含 raw/canonical 大 shard |
| **metadata/work 合计** | **`64,000,000`** | **budget cap** |

因此 rank64 的最小布局上界是：

```text
355,946,496 B (Z+AZ exact arithmetic)
+64,000,000 B (metadata/work budget)
=419,946,496 B (derived budget upper bound)
```

它低于 `424,000,000 B` retained hard cap，预算余量为 `4,053,504 B`。该结论是 `exact + budget` 的 preflight 算术，不是 simultaneous process-tree measurement，也不是 complete-workflow memory pass。

## cold build/JIT 与 online apply 的分离

`cold build/JIT/setup` 包括 mesh/MPC 对象、UFL/FFCx 编译、basis 构造、正交化和 coarse operator 准备；D0 对它们的 process-tree 峰值记为 `not_measured`。`online apply` 才是已经存在的对象参与 action、局部路由和 coarse correction 的阶段；adaptive coarse 的 online 峰值同样 `not_measured`。

已有 Candidate A gradient 的 process-tree measured peak 是 `1,323,728,896 B`。把它和 rank64 的 `Z+AZ` 精确算术相加得到：

```text
1,323,728,896 + 355,946,496 = 1,679,675,392 B
```

这只是 derived preflight（`1.679675392 GB`，`1601.86328125 MiB`），不是两者同时驻留的测量，更不是完整 workflow 通过。A physical 的 cold peak `5,145,784,320 B` 也不能被改写成 adaptive coarse 的预测或通过。

## D0 Gate 与数据分类

| Gate/字段 | D0 结论 |
|---|---|
| rank ladder | 只允许 `16/32/48/64`；exact arithmetic 已列出 |
| rank64 `Z+AZ` | `355,946,496 B`，exact；不超过该项 `355,946,496 B` |
| coarse metadata/work | `64,000,000 B`，budget cap |
| rank64 total retained | `419,946,496 B`，derived budget upper bound；低于 `424,000,000 B` |
| no FE-sized numeric allgather | planned forbidden；后续 D1/D2 checker 必须从实际 audit 验证 |
| no replicated full basis per rank | planned owner-local layout；不是每 rank 完整复制 |
| no global AIJ/Schur/sparse factor | planned forbidden；D0 未构造此类对象 |
| swap | 启动观察值非零；D1–D4 formal/resource Gate 未运行，不能宣称 `swap=0` |
| cold build/JIT/setup peak | `not_measured` |
| adaptive online peak | `not_measured` |

“measured”仅指表中明确标出的环境/A gradient 既有实测；“exact”指字节算术；“derived”指由 exact/measured 数值推导；“budget”指实现上限；“not_measured”不等于通过或失败。D0 记录本身不是 coarse solver implementation，也不授权 D1 以外的 heavy case。

