# 合并建议

当前建议：`review_required_before_master = true`，`ordinary_default_changed = false`，`Task030 status = workstation_memory_success_with_qualifications`。

建议合并：

- active/master-aware nonmatching H(curl) transfer、MPI CSR cache 和精确 condensed Galerkin 研究基础设施；
- local diagonal shift 与 factor-only subdomain storage；
- symmetric pre/post two-level composition的显式 opt-in 支持；
- Benchmark060、门槛、轻量 h5/h3/h2 records、测试和完整正负结果文档。

不得提升为 ordinary default：

- p/h GMG、patch/Vanka 候选；
- Modal Woodbury、x-harmonic enlarged coarse、restart80；
- AMS/HX、TFQMR 或任何未跑目标 p2/h5 的 profile；
- h2 首次未收敛和资格复跑的 heavy artifacts；
- transfer cache、网格、矩阵、场和逐步日志。

Task27-derived `compact physical-slab low-memory experimental profile` 的 h5/h3 已在 final implementation HEAD clean 复跑，达到 `workstation_memory_success_with_qualifications`；h2 保留为 reviewed historical dirty-worktree reference，1873 步未达到 1200 的工程偏好。真正 p/h multigrid solver 仍为 negative。Review V2 R1/R2/D1/V1 回应完成后，仍须等待 ChatGPT final review 和用户明确许可，再按 selective merge 边界合入 master。

`hcurl_multilevel.py` 的 validated infrastructure API 只包含 active DoF、nonmatching transfer/cache/validation 和 condensed Galerkin；失败的 Jacobi、p/h multilevel 与 Woodbury 候选仅留在 research runner/tests，不通过普通 `src.solvers` 导出。不得整体合并 research lane，也不得在 Task30 分支直接启动 Task31。

Task27 ILU1 与 Task30 ILU0 的 reported factor nnz 相同，不能把内存下降写成已证明的 factor-nnz compression。factor-only 只验证 PETSc 3.24.0 complex build，跨版本需回归。
