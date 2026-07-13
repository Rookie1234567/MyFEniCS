# Benchmark 体系

编号功能目录见 [`../benchmarks/cases/README.md`](../benchmarks/cases/README.md)；每个 case 固定 22 项问题/参数/命令/证据/限制契约。

## 分层结果

| Level | 内容 | 结果 |
|---|---|---|
| L1 | compile、full unit、2D DtN、3D Stage1 | 通过 |
| L2 | condensation等价、transpose、backsub、MPI owner/cache | 通过 |
| L3 direct | target p2 h5/h3 rerun，h2 reviewed reference | 通过 |
| L3 iterative | target p2 h5/h3/h2 clean branch | 全通过 |

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

[`Case050`](../benchmarks/cases/050_stage4_direct_memory_forensics/README.md) 从 Task28 merge 后的 `master` 建立，专门区分 MPI worker 同时 RSS、各 rank 历史峰值和、cgroup memory 与 swap，并保存 base/augmented/factor inventory。h5/h3 是必跑 baseline；h2 默认锁定。Task28 canonical records 保持只读，Case050 的完整 timeline 和 solver output 写入 ignored artifacts。
