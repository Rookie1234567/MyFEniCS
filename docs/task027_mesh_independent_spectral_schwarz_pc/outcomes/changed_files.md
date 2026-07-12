# 本轮改动文件

## 求解器实现

| 文件 | 改动 |
|---|---|
| `src/solvers/spectral_schwarz.py` | 新增完整物理 slab 的 owner-computes additive Schwarz、负载均衡、一次 gather/reverse scatter、局部 ILU 和多步全局平滑支持；保留 sparse Galerkin coarse PC |
| `src/studies/run_task027_mesh_independent_spectral_schwarz.py` | 构造 MPI complete reduced-DoF slabs，接入 distributed-slab profile、平滑/后平滑/正交化诊断、RSS/swap/真残差/RTA 元数据 |
| `src/test/test_23_task027_spectral_schwarz.py` | 增加全局 slab、owner balance、dense action、两步平滑、重复 apply 和空 owner rank 的 MPI 回归 |

## 既有 Task027 实现

| 文件 | 内容 |
|---|---|
| `src/solvers/condensed_dtn.py` | 精确 transpose 与 Hermitian-transpose matrix-free action |
| `src/studies/run_task026_auxiliary_free_modal_port.py` | MPI local slab fragments、粗基构造和进度回调 |
| `src/studies/run_task023_petsc_mpi_fe_response_pc.py` | 受检查的运行时参数 override；ordinary default 不变 |
| `Dockerfile.task027_hpddm` | 独立 SLEPc+HPDDM research image |

## 文档与数据

`docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/` 新增或更新：

- 最终三网格 distributed physical-slab scaling、R/T/A、迭代比和内存表；
- 配置漏斗、Gate、排名、合并建议和下一步建议；
- h=2 production solver、残差历史、memory breakdown；
- `raw_runs/` 下所有 owner-slab、平滑、overlap、restart、局部迭代和正交化实验的小型证据。

同步更新：

```text
docs/README.md
notes/README.md
notes/reference/current_version_boundaries.md
notes/theory/task027_shifted_impedance_spectral_schwarz_convergence_framework.md
```

## 未纳入范围

- ordinary production default 未修改；
- `Results/` 大体积场、mesh、VTU 未进入 Git；
- 用户已有 `papers/` 未触碰；
- Task023 无关的本地 `system_metadata.json` 变化不纳入提交。
