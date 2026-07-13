# 合并建议

当前建议：`review_required_before_master = true`，`ordinary_default_changed = false`。

建议合并：

- active/master-aware nonmatching H(curl) transfer、MPI CSR cache 和精确 condensed Galerkin 基础设施；
- local diagonal shift 与 factor-only subdomain storage；
- symmetric pre/post two-level composition的显式 opt-in 支持；
- Benchmark060、门槛、轻量 h5/h3/h2 records、测试和完整正负结果文档。

不得提升为 ordinary default：

- p/h GMG、patch/Vanka 候选；
- Modal Woodbury、x-harmonic enlarged coarse、restart80；
- AMS/HX、TFQMR 或任何未跑目标 p2/h5 的 profile；
- h2 首次未收敛和资格复跑的 heavy artifacts；
- transfer cache、网格、矩阵、场和逐步日志。

最终 profile 已在冻结 h5/h3/h2 上达到 `workstation_success`，但 1873 步未达到 1200 的工程偏好，只作为 Case060 / workstation runner 的显式参数组合。待 ChatGPT review 和用户明确许可后再决定是否 selective merge 到 master。
