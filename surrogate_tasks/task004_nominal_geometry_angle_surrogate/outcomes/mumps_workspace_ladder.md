# M0R/M1R：MUMPS workspace ladder

本轮把原先的 direct-LU 工作区失败与角度物理分开。历史 clean-SHA
`7fe366304023c32bf2e8ddcacdb2ada9996d3e7c` 在 `(h,w,grazing,azimuth) =
(120,17,0.5,0)` 首次尝试中得到 `INFOG(1)=-9, INFO(2)=919260`，但没有
产生正式场记录。本轮建立的数值基线是
`fdf961545f217d620e22800f2704ae9913a6d270`，仍使用 ordinary in-core
MUMPS、Full3D static uniform N1curl p5/h10/Ny4、MPI2、每 rank 单线程。

`mat_mumps_icntl_14` 被写入 prefixed KSP 的 PETSc options、config identity、
execution identity 和 factor inventory。两个独立 fresh-process attempts
在 40% 下都完成 full solve，且观测值也确认 MUMPS 实际消费了 40%。

| attempt | requested/actual ICNTL(14) | wall s | peak RSS GiB | peak PSS GiB | swap | residual | energy closure |
|---|---:|---:|---:|---:|---:|---:|---:|
| 01 | 40 / 40 | 167.069 | 6.243 | 6.071 | 0 | `2.8504e-11` | `1.0900e-12` |
| 02 | 40 / 40 | 124.873 | 5.811 | 5.620 | 0 | `2.8504e-11` | `1.0900e-12` |

两次运行的 `INFOG/RINFOG`、矩阵尺寸/NNZ、topology identity、实际 factor
类型、true residual、功率账本和 zero-swap 记录均存在。40 已满足“连续两次
fresh-process full solve 通过”的最小稳定条件，因此按规则冻结 40；没有
无理由运行 80/120，也没有切换 OOC/BLR、网格、阶数、MPI 或物理参数。

证据：`benchmarks/artifacts/cases/124_task004_mumps_workspace_and_anchor_requalification/mumps_workspace_ladder.json`。
