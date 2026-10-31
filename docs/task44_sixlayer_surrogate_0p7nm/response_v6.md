# Task44 执行响应 v6：DtN 倏逝模态对照真残差门失败

## 本轮结论

以 B 为基线的 DtN 倏逝模态壳层对照已运行。端口模式范围增加后，完整线性系统求解返回了向量，但全系统显式真残差远超合同限值，因此数值结果被拒绝，official R/T/A 后处理没有运行。本次没有得到可用于和 B 比较的 R_total、T_total、R00_total，也没有计算能量闭合；DtN 模态截断稳定性仍属未判定。

这是数值残差 Gate 失败，不是资源 Gate 停止。服务的 128 GiB 内存上限、零 swap、CPU 与身份监控通过；服务退出后清理了全部子进程。当前证据尚未确定残差巨大的根因，因而不作根因推断，也不把失败样本纳入 GP。

## 对照问题与计算

有限高度的 DtN 端口把半空间中的出射电磁场转成边界模态关系。倏逝模态在离开结构后会衰减，远处不携带传播功率，但仍可能影响结构附近的场。增加一圈模态的目的，是检查有限模式范围是否足以稳定反射和透射结果。

本次沿用 B 的六层几何、材料、[3,6,8] 贴体网格、P6、双 Floquet、MPI1、装配期静态凝聚和 MUMPS exact；DtN 使用 auxiliary 装配和手动阶次上限 m=4、n=8。实际加入 612 个 DtN auxiliary 未知量。输入还把 diffraction_order_max_n 从 7 提至 8、diffraction_sample_count_y 从 15 提至 17，用于扩展输出报告范围与采样。输出采样设置不改变有限元方程。

B 的参考值为 R_total=0.0952190944953505、T_total=0.8831311299072778、R00_total=0.0952186487281771。因为本次没有通过残差 Gate 的场，不能将任何诊断通量当成 official 结果，也不能计算壳层相对 B 的输出变化。

## 数值 Gate 与实际结果

| 检查项 | 合同 / 含义 | 实测结果 | 判定 |
|---|---|---|---|
| 完整系统相对真残差 | 不超过 1e-6 | 残差范数 209779683028.43216；RHS 范数 1.2920851858750981；独立相除重算 162357470948.29 | failed；比限值高约 1.62e17 倍 |
| PETSc KSP 状态 | 求解器内部诊断 | preonly 报告 CONVERGED_ITS、1 次迭代、内部 residual norm 为 0 | 不能替代完整真残差检查；真残差 Gate 失败 |
| official R/T/A 与能量闭合 | 只从通过残差 Gate 的场计算 | postprocess_skipped=true；R_total、T_total、A_volume_total 没有有限值；能量闭合未计算 | not_run |
| 规模 | 完整自由度与实际凝聚系统分开 | 99,894 个完整 Nédélec DoF；29,808 个迹行 + 612 个 DtN auxiliary 行 = 30,420 系统行；25,143,076 used NNZ | measured |

数值摘要将 case_status 记为 failed_stage4_true_residual_gate，official_result=false，physical_benchmark_candidate=false。虽然 PETSc preonly 显示一次直接求解调用已返回，但完整系统中计算出的解不满足 1e-6 残差门。任务当前不判断该差异来自矩阵尺度、端口模态、凝聚、线性系统条件数或其他因素。

## 运行身份与资源

| 项目 | 记录 |
|---|---|
| Run / service / Invocation | task44_accuracy_dtn_evanescent_shell_20261031 / task44-sample-accuracy-dtn-shell1.service / 4f142c76cd4041eea9755bdbb762e288 |
| 输入 SHA-256 | f9b05549ca72a0f99bba1083f7fefb62b61ea057c0c77a4c1a7d6f31b3554c99 |
| 物理模型 SHA-256 / source SHA | 324e2d311fb41127bccd4ba32058507cd874911ec75cfe965732f9c97fe9d006 / b390bc11e3df855c24b7fbcebfab9459c8923ad8 |
| 执行准入 | CPU 8；cgroup cap 137,438,953,472 B（128 GiB）；swap 上限 0 B。启动时 MemAvailable 2,102,490,845,184 B；扣除 412,316,860,416 B reserve 后余量为 1,544,145,096,704 B |
| 耗时 | numerical run summary 1,891.633 s；Stage 4 端口装配与求解 1,884.331 s；KSP setup 42.850 s；KSP solve 0.699 s；service 全生命周期 1,912.940 s。worker wall 未单独记录 |
| 内存 / swap | 同时进程树 RSS 峰值 8,085,782,528 B；专属 cgroup memory peak 8,921,956,352 B；两类 swap 峰值均为 0 B |
| 监控 / 清场 | resource authority 5,125 次采样、无 warning；完整进程身份 1,481 次采样；cgroup swap 353 次采样且通过；service classification=WORKER_FAILED；descendants_cleared=true，剩余子 PID 为空 |

## 证据入口

- [输入](../../input/task44_accuracy_dtn_evanescent_shell_v1.dat)
- [数值 run summary](../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/numerical_output/run_summary.json)
- [外层 run summary](../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/run_summary.json)
- [run manifest](../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/run_manifest.json)
- [worker output](../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/worker_stdout.txt)
- [service summary](../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-dtn-shell1.service/service_summary.json)
- [watchdog summary](../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-dtn-shell1.service/watchdog/summary.json)

| 证据文件 | SHA-256 |
|---|---|
| 数值 run summary | 83a011943ab0920142cc796c2cd22061b286e1efbeeaadedb7b6faf00de91e65 |
| 外层 run summary | 875d8c14a54323180c816b81db658d418b236d80d12f152ca070944e930368d9 |
| service summary | ec739e568a2d4c3dae78b87c11de68cbf3d19737a814346024c6212a2365529f |
| watchdog summary | 7bae79c89608a91924f6feeed3876b8f8fd1024a18fd210969a7c22871bfdb30 |

下一项按已批准顺序是顶部空气间距 0.5 → 1.0 nm。运行前重新核验输入与 B 的差异、Task44/Task40 邻任务、CPU、128 GiB 资源余量、ABI、cgroup 零 swap 和 service identity；结果必须独立通过完整残差门与能量闭合门，才可和 B 比较 R_total、T_total、R00_total。当前资格 attempt 已使用 4/12；空气间距项运行后剩 7 次。y 稳定性失败、DtN 真残差失败及 z 单方向通过都需保留，A–D 的 GP 资格不变；有限元 GP 训练、开发评估、盲测与标准尺寸仍未运行。
