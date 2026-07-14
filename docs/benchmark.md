# Benchmark 体系

编号功能目录见 [`../benchmarks/cases/README.md`](../benchmarks/cases/README.md)；每个 case 固定 22 项问题/参数/命令/证据/限制契约。

## 分层结果

| Level | 内容 | 结果 |
|---|---|---|
| L1 | compile、full unit、2D DtN、3D Stage1 | 通过 |
| L2 | condensation等价、transpose、backsub、MPI owner/cache | 通过 |
| L3 direct | target p2 h5/h3 rerun，h2 reviewed reference | 通过 |
| L3 iterative | Task27 target p2 h5/h3/h2 canonical | 全通过 |
| L3 Task30 | compact physical-slab low-memory h5/h3/h2 | `workstation_memory_success_with_qualifications`；h5/h3 为 clean final-HEAD 复跑，h2 为 reviewed historical reference |

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

[`Case060`](../benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md) 同时保存“正确但性能失败”的 nonmatching H(curl) transfer/Galerkin 基础设施和最终低内存正反馈。五个 p/h 候选 100 步真残差为 `0.375–0.680`，不得提升；最终成功求解器不是 p/h GMG，而是 Task27-derived physical-slab + 75D wave-coarse 架构，Task30 在其上使用 symmetric pre/post ILU0、subdomain-local shift、factor-only storage 与 restart90。

| h/nm | iterations | full true residual | peak RSS | 相对 Task27 |
|---:|---:|---:|---:|---:|
| 5 | 855 | 9.92491e-7 | 1.688 GB | memory -15.24%，iterations -28.81% |
| 3 | 962 | 9.90389e-7 | 3.793 GB | memory -25.37%，iterations -3.12% |
| 2 qualified | 1873 | 9.97223e-7 | 9.375 GB | memory -28.33%，workstation pass；iterations target missed |

h5/h3/h2 official R/T/A 对 direct 的最大差分别为 `5.44e-9`、`7.72e-10` 与 `6.56e-9`。最终实现提交 `5b81359daee0874793c44b019d9c914b334db483` 上的 clean h3 复跑峰值为 3.792912 GB，同时通过 `<=3.8 GB` 绝对线，并较 Task27 降低 25.37%。Case060 最终分类为 `workstation_memory_success_with_qualifications`；h2 的 1873 步仍未达到 1200 目标，ordinary default 和 Case031 canonical records 不变。

三份正式 lightweight records 已进入 manifest，checker 可重复生成同一 `benchmark_summary.csv`，并执行 203 项 Gate。h5/h3 是 final implementation HEAD `5b81359daee0874793c44b019d9c914b334db483` 的 clean 复跑，heavy JSON SHA-256 分别为 `2be05820cf69db67ba72b257c44624c08e15f7f7ceeae6e479eed2a9e68523f3` 与 `48c9bb51b89a99b7ba1653f8c95f8450e7917f987274c1aef631464484275232`；h2 明确保留为 `reviewed_historical_dirty_worktree_reference`，不是 clean final-HEAD 复跑。Task27 ILU1 与 Task30 ILU0 的 reported slab-factor nnz 相同，因此该统计口径保持 `measurement_unresolved`，内存下降不归因于已证明的 factor-nnz compression。

## Task031 Case070

[`Case070`](../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md) 在 Task030 Review V3 合入后的 clean master 上运行，使用 external 0.25 s simultaneous RSS/cgroup/swap/stage sampler。最终 candidate 保留 Task030 physical-slab/wave coarse 与 FGMRES90，改为 overlap0.125、public MPC matrix-free fine action 和 compact lifecycle。普通默认、物理、80 modes、exact condensation 与 official R/T/A 都不改变。

| h/nm | iterations | full true residual | simultaneous worker peak | Task030 reduction | solve/total s |
|---:|---:|---:|---:|---:|---:|
| 5 | 1157 | `9.959903e-7` | 1.619598 GiB | 4.032% | 350.851 / 374.342 |
| 3 | 1994 | `9.973853e-7` | 3.474346 GiB | 8.399% | 2311.581 / 2370.351 |
| 2 | 1977 | `9.998454e-7` | 7.897675 GiB | 15.756% | 11982.581 / 12173.086 |

h3 同时通过 `<=3.50 GiB` 与 `>=8%`；h2 在两套 8.501/8.587 GiB 中央预测、9.447 GiB 上界和 9.5/11 GiB watchdog 放行后完成，无 swap。h2 official R/T/A 为 `0.001342934186 / 0.599213235569 / 0.399443835926`，对 direct 最大差 `6.125e-9`。classification 是 `strong_memory_success_slow_but_memory_efficient`：memory 强成功，但 solve 约为 Task030 的 5.01x。

Case070 还固定 PC linearity、matrix-free action、factor fingerprint、overlap/selective solver 与 lifecycle 负/正证据。16 个 factor 全部 unique，禁止近似 dedup；adaptive PC 非线性，普通 GMRES fail closed。三份 best records、baseline、screen、object/PC/memory records 可提交，完整 timeline 与场输出只留在 ignored `benchmarks/artifacts/cases/070/`。
