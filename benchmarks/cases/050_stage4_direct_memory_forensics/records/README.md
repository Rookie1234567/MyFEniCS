# Case050 records

此目录只保存通过 Task029 Gate 后选定的轻量、可审查 summary record。开发期间的 candidate JSON、完整 memory timeline、solver log、mesh、field、factor 与 OOC scratch 全部保留在 gitignored 的 `benchmarks/artifacts/cases/050/`。

- `h5_baseline.json` / `h3_baseline.json`：Task29 MPI4 遥测基线。
- `h5_mpi2_candidate.json`：最佳 in-core 候选的 h5 数值与 20% 内存门禁均通过。
- `h3_mpi2_candidate.json`：同一候选完整数值通过，但内存仅下降 15.119%，因此明确拒绝工程资格和 h2 解锁。
- `h5_threaded_direct_audit.json`：固定 CPU `0-3` 的 MPI4×1、MPI2×2、MPI1×4、MPI1×1 摘要；数值均通过，但 MPI1×4 KSPSetUp 仍约 1 核，最终身份为 `unavailable_in_current_image`。

候选 record 的 `status=pass` 只表示完整求解与数值 Gate 通过；最终性能处置必须读取 `candidate_disposition` 和 `qualification.memory_reduction_20pct_gate`。

Task28 的 direct/workstation canonical records 不得复制覆盖到此目录。

## 已冻结记录

- `h5_baseline.json`：MPI4、p2、default MUMPS 的完整 h5 baseline；source SHA 为 `208aaab149ca5c2be0aae09a8d893bfa02e3f8cc`，数值 Gate、factor inventory 与零 swap 均通过。
- `h3_baseline.json`：MPI4、p2、default MUMPS 的完整 h3 baseline；source SHA 为 `fba69d88ea8590ea01537b7561edff1684f25135`，full solve、数值 Gate、factor inventory 与零 swap 均通过。

h5/h3 baseline 已闭合；threaded h3 因 h5 T1/T3 失败而 `not_run`，h2 仍由 guarded Gate 锁定。
