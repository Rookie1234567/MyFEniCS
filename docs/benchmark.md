# Benchmark 体系

编号功能目录见 [`../benchmarks/cases/README.md`](../benchmarks/cases/README.md)；每个 case 固定 22 项问题/参数/命令/证据/限制契约。

## 分层结果

| Level | 内容 | 结果 |
|---|---|---|
| L1 | compile、full unit、2D DtN、3D Stage1 | 通过 |
| L2 | condensation等价、transpose、backsub、MPI owner/cache | 通过 |
| L3 direct | target p2 h5/h3 rerun，h2 reviewed reference | 通过 |
| L3 iterative | Task27 target p2 h5/h3/h2 canonical | 全通过 |
| L3 Task30 | compact low-memory h5/h3/h2 | 全通过；h2 1873 步、9.374729 GB，experimental opt-in |

## 目标模型

50 x 25 x 140 nm 周期单元，17 x 25 x 120 nm Si光栅，13.5 nm，theta_from_z=80 deg，phi=0，s偏振，N1curl p=2。

## 数值对照

| h/nm | direct RSS | iterative RSS | iterative steps | iterative true residual |
|---:|---:|---:|---:|---:|
| 5 | 2.293 GB | 1.991 GB | 1201 | 9.83949e-7 |
| 3 | 8.182 GB | 5.082 GB | 993 | 9.93265e-7 |
| 2 | 20.533 GB reviewed | 13.080 GB | 1804 | 9.99738e-7 |

## 物理结果

| h/nm | R | T | A_volume | closure |
|---:|---:|---:|---:|---:|
| 5 | 0.0890216032 | 0.4425882752 | 0.4683901190 | -2.55e-9 |
| 3 | 0.00461303245 | 0.5836533646 | 0.4117336036 | 6.18e-10 |
| 2 | 0.00134293630 | 0.5992132418 | 0.3994438284 | 6.58e-9 |

## 解释

h5的粗网格R明显偏高，不能作为收敛物理结论。h3/h2的R/T/A向Task008 direct reference收敛。三网格均满足显式真残差gate，但迭代数不单调，因此当前准确称谓是 mesh-robust workstation production candidate。

canonical records 位于 `benchmarks/records/` 与 recorded case 的 `records/`，完整表见 `benchmarks/benchmark_summary.csv`。Response V3 的 checker 自动计算 143 项 Gate，并核对 case files、SHA references、2D explicit/auxiliary、lossy/lossless、record ID、求解资格、物理模型和 artifact provenance。普通运行仍写 `results/`；benchmark 重型输出显式写被忽略的 `benchmarks/artifacts/`。环境状态为 `qualified_local_image`，不是无条件 clean-machine reproducible。

## Task029 Case050

[`Case050`](../benchmarks/cases/050_stage4_direct_memory_forensics/README.md) 从 Task28 merge 后的 `master` 建立，区分 MPI worker simultaneous RSS、各 rank 历史峰值和、cgroup memory 与 swap，并保存 base/augmented/factor inventory。MPI4 h5/h3 baseline 为 2328.145 / 8651.098 MB；最佳 default MUMPS MPI2 为 1655.484 / 7343.137 MB，即下降 28.893% / 15.119%。候选 full residual/R/T/A 全通过且零 swap，但 h3 低于 20%，所以 Case050 以 `diagnostic_success` 收口。h2 预测区间 18.882–27.913 GiB，Gate 不通过且未运行。Task28 canonical records 保持只读，完整 timeline 和 solver output 只写 ignored artifacts。

Review V1 的条件式线程审计也归入 Case050：PETSc 3.24.0 / MUMPS 5.8.1 实际链接 system OpenBLAS 0.3.26 pthread，线程控制 API 可用；但固定 CPU `0-3` 的 MPI1×4 在 KSPSetUp 只使用 0.999/1.054 核均值/峰值，Stage4 48.273 s，相对 MPI1×1 speedup 仅 1.054×。因此 `threaded_direct_capability=unavailable_in_current_image`，threaded h3 明确 `not_run`。轻量记录为 [`h5_threaded_direct_audit.json`](../benchmarks/cases/050_stage4_direct_memory_forensics/records/h5_threaded_direct_audit.json)。

Task029 Review V2 已接受 Case050 为诊断 benchmark 并批准其基础设施进入 master；该接受不代表存在 qualified low-memory direct profile。最终状态仍为 `diagnostic_success`、`engineering_success=no`、h2 `not_run`、ordinary default unchanged。

## Task030 Case060

[`Case060`](../benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md) 同时保存“正确但性能失败”的 nonmatching H(curl) transfer/Galerkin 基础设施和最终低内存正反馈。五个 p/h 候选 100 步真残差为 `0.375–0.680`，不得提升；最终候选保留 75D wave coarse，使用 symmetric pre/post ILU0、subdomain-local shift、factor-only storage 与 restart90。

| h/nm | iterations | full true residual | peak RSS | 相对 Task27 |
|---:|---:|---:|---:|---:|
| 5 | 855 | 9.92491e-7 | 1.696 GB | memory -14.82%，iterations -28.81% |
| 3 | 962 | 9.90389e-7 | 3.808 GB | memory -25.08%，iterations -3.12% |
| 2 qualified | 1873 | 9.97223e-7 | 9.375 GB | memory -28.33%，workstation pass；iterations target missed |

h5/h3/h2 official R/T/A 对 direct 的最大差分别为 `5.44e-9`、`7.72e-10` 与 `6.56e-9`。Case060 达到冻结目标的 `workstation_success`，但仍是显式 experimental profile；1873 步未达到 1200 目标，ordinary default 和 Case031 canonical records 不变。
