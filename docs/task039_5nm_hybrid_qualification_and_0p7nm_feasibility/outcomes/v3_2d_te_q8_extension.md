# V3-2 research extension: 2D TE Q8 reference funnel

本文件记录用户授权的 post-V3 research-only Q8 扩展。它验证的是二维 TE 的高阶有限元离散与相邻网格收敛，不改写原 Q6 结果，也不解锁 V3-3 或三维/Hybrid 运行。

## 结论

Q8 的 h3→h2 与 h2→h1.5 两个相邻网格比较均通过冻结的六类 checker Gate，因此本扩展分类为 `Q8_P1_ESTABLISHED`。原 Q6 funnel 的 P1 仍保持历史结论“未建立”：Q6 的 h3↔h2 失败，不能用 Q8 的结果覆盖它。

完整紧凑证据在 [task039_v3_2d_te_q8_extension_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_2d_te_q8_extension_v1.json)。三份 raw run 与两份比较 JSON 位于 `results/` ignored 目录，record 只绑定路径与 SHA256。

## 离散空间与物理身份

二维 TE 求解器只有一个标量未知量 `Ez`，因此使用标量 Lagrange 元，而不是三维矢量 Nédélec 元；在映射到三维 S/TE 记号时，这个二维 `Ez` 就是三维的 `Ey`，不是另一组独立字段。Q8 表示每个四边形单元上的八次张量积多项式。三次正式 run 的真实空间身份相同：`family=Lagrange`、`cell=quadrilateral`、`degree=8`、`variant=gll_warped`、Basix 空间维数 81；实际 global dofs 随网格变化并在下表列出。

固定物理为 5 nm、1° grazing、phi=0°、S/TE、`2d_port` 显式 DtN、N=21、MPI1。每个正式 run 的 43 行阶次清单均完整，top 传播阶为 -19..0，bottom 为 -19..-1；selected `Ey/Hx/Hz` 均为 `[7,40]` 且 finite。

## 三个 Q8 formal case

| case | h (nm) | cells | global dofs | reduced dofs | rows | linear NNZ | reduced NNZ | residual | R | T | A_balance | A_volume | closure | solver elapsed (s) | RSS/PSS/USS (MiB) | swap | own |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| h3 | 3.0 | 882 | 56,985 | 56,592 | 56,985 | 5,689,329 | 5,684,832 | 1.90393e-12 | 0.7325886854 | 0.0002229322 | 0.2671883824 | 0.2671883791 | -3.29557e-09 | 37.551 | 1302.129 / 1275.557 / 1262.832 | 0 | PASS |
| h2 | 2.0 | 1,890 | 121,737 | 121,176 | 121,737 | 12,193,617 | 12,187,152 | 3.41301e-12 | 0.7325886666 | 0.0002229322 | 0.2671884012 | 0.2671883979 | -3.29563e-09 | 39.045 | 2738.891 / 2717.575 / 2705.203 | 0 | PASS |
| h1.5 | 1.5 | 3,420 | 219,929 | 219,168 | 219,929 | 22,059,761 | 22,051,008 | 1.30947e-11 | 0.7325886666 | 0.0002229322 | 0.2671884012 | 0.2671883979 | -3.29646e-09 | 108.994 | 5394.770 / 5381.691 / 5372.774 | 0 | PASS |

`R/T/A` 均来自 DtN port authority；`closure = R + T + A_volume - 1`。每个 run 的 exit status 是 0，launcher classification 是 `worker_exit0`。表中是 solver elapsed；没有独立拆分 factorization-only timing。资源峰值是 launcher-owned process-tree 的逐指标峰值，PSS/USS 可能发生在不同采样点；不是对象容量相加。

## 相邻网格比较

| pair | scalar max abs (≤1e-6) | closure max abs (≤1e-8) | primary power max rel (≤1e-4) | all-order weighted power (≤1e-5) | Ey rel L2 (≤1e-3) | Hx/Hz concat rel L2 (≤2e-3) | primary rows | coordinates | overall |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Q8 h3↔h2 | 1.87618e-08 PASS | 3.29563e-09 PASS | 6.35966e-08 PASS | 2.57205e-08 PASS | 1.67324e-06 PASS | 9.81893e-06 PASS | 11 | exact | PASS |
| Q8 h2↔h1.5 | 2.67817e-11 PASS | 3.29646e-09 PASS | 1.30268e-09 PASS | 3.68646e-11 PASS | 4.15832e-08 PASS | 4.13074e-07 PASS | 11 | exact | PASS |

`primary rows` 使用 `max(left_power,right_power) >= 1e-6`；本次每一对均有 11 行。all-order 指 top 反射与 bottom 透射的 43 行之和，分母为所有配对功率最大值之和并以 `1e-30` 作下限。两个比较 JSON 的 SHA256 分别为 `da985bdf0da360fb984646c24011fb721227d79039f0e0520275263e30f3692f` 与 `ded7d9e9aced4df07eaac8bd1143d0a91930676068518a74e3bf165ec4c72fe7`。

## 与历史 Q6 的诊断对比

最细 h1.5 的 Q8 与现有 Q6 记录作资源诊断如下；这不是跨阶次的物理 Gate，也不改变 Q6 的历史负结论。

| h1.5 case | degree | global dofs | linear NNZ | solver elapsed (s) | RSS (MiB) | PSS (MiB) | USS (MiB) | Q8/Q6 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Q6 historical | 6 | 123,907 | 7,976,689 | 31.455 | 2420.512 | 2399.134 | 2386.758 | baseline |
| Q8 research | 8 | 219,929 | 22,059,761 | 108.994 | 5394.770 | 5381.691 | 5372.774 | dofs 1.775×; NNZ 2.766×; elapsed 3.465×; RSS 2.229× |

对应的最细网格物理量只作 Q6/Q8 诊断，不是 Gate：

| h1.5 | R | T | A_balance | A_volume |
|---|---:|---:|---:|---:|
| Q6 historical | 0.7325886918393777 | 0.00022293222459536006 | 0.26718837593602696 | 0.2671883726404462 |
| Q8 research | 0.7325886665680106 | 0.0002229322436290485 | 0.26718840118836035 | 0.2671883978918967 |
| abs(Q8−Q6) | 2.52714e-08 | 1.90337e-11 | 2.52523e-08 | 2.52515e-08 |

这些跨阶次差值不替代同阶次相邻网格 Gate。

Q6 数据来自既有 [V3-2 funnel record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_2d_te_reference_funnel_v1.json)，Q6 的原始 P1 未建立事实保持不变。Q8 只证明 degree=8 的两个相邻网格对通过；没有把 Q8 与 Q6 的跨阶次差异当成收敛 Gate。

## 证据与边界

- capability/source SHA：`13d0d555173be794ff57d1351ddc7f4334236331`；三次 Q8 raw 的 source SHA 相同。
- 三个输入分别为 [Q8 h3](../../../input/official/task039/5nm_1deg_2d_te_p8h3_direct_mpi1.dat)、[Q8 h2](../../../input/official/task039/5nm_1deg_2d_te_p8h2_direct_mpi1.dat)、[Q8 h1.5](../../../input/official/task039/5nm_1deg_2d_te_p8h1p5_direct_mpi1.dat)。
- 输入、resolved config、DtN power/orders、selected-field metadata/NPZ 的逐 case 哈希均在 compact record 中；raw artifacts 不入 Git。
- 这是 research-only post-V3 extension；原 Q6 输入、V3-2 record/outcome、3D/Hybrid defaults 均未改写。V3-3 至 V3-10、h1、p10、MPI>1、P/phi≠0°、0.7 nm 均未运行。
