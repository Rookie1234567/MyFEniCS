# Task37b V7 后 MPI 数量对照回应

本轮不是新算法，也不是 production qualification。它是用户在 V7 结项后授权的 research-only 诊断：冻结 M10 exact monolithic Hybrid iterative candidate，只改变 MPI size，分别运行 MPI1、MPI2、MPI4、MPI8。MPI1/2/4 来自 scaling carrier `28cbead4ef90a7fbe17d93ed8c9061e09bc92e3d`；MPI8 保留 M10 source `b291f3dfdf5f0064ff243038f6809172f811d7aa`。普通无 flag 路径和 MPI8 lock 没有改变。

| MPI | iterations | process-tree peak | total | 相对 MPI8 峰值节省 |
|---:|---:|---:|---:|---:|
| 1 | 794 | 1637.765625 MiB | 1035.158474470023 s | 72.7881460712443% |
| 2 | 758 | 2423.6640625 MiB | 687.5406564989826 s | 59.73026211175689% |
| 4 | 760 | 3907.26953125 MiB | 512.5570110660046 s | 35.07981476613738% |
| 8 | 792 | 6018.57421875 MiB | 467.8611913640052 s | 0% |

所有四次都通过五项 residual、上下 exact traction、recovery、own physics、energy、canonical/lifecycle；唯一 aggregate checker 也 `pass=true`、`failures=[]`。MPI4 是这台机器上本次样本的平衡点：相对 MPI8 少约 35.08% process-tree 峰值，只慢约 9.55%。MPI1 虽然最低，但耗时约为 MPI8 的 2.2125 倍。这里的“最低”只描述这台机器的这一次离散候选运行，不能外推一般 MPI 极限。

峰值阶段按 raw 记录：MPI1=`outer_iter_630`、MPI2=`outer_iter_270`、MPI4=`v6_pre_canonical_heap_cleanup_started`、MPI8=`v6_top_recovery_heap_cleanup_finished`。process-tree RSS 是资源权威口径；worker PSS/USS 只是同一采样的 companion，不能替代 RSS Gate。离线 checker 的约 30 秒、123.58203125 MiB RSS 不计入 online 峰值。

订单比较也需要严格区分口径：四路均为 80/80 key、12 significant、68 below-floor，12/12 power 与 12/12 amplitude 通过；报告中的 significant 最大误差是各 MPI Hybrid 对 frozen Full3D authority 的 12 通道误差，不是 MPI-vs-MPI8 逐通道误差。checker 没有提供 cross-MPI order 差值。raw modal coefficients 继续标为独立 QEP gauge 下不可逐项比较的 diagnostic；物理 magnitude 与坐标对齐的 E/H 通过。

完整逐路残差、R/T/A、A_volume、closure、timing、authority SHA 与 ignored raw 路径见[正式 MPI scaling 报告](outcomes/mpi_scaling_comparison.md)及[compact evidence](../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_mpi_scaling_1_2_4_8_v1.json)。本轮只整理已完成证据，未重跑 pytest、MPI、PDE、checker 或 CI；不能据此声称 continuum、mode-count、0.7 nm 或 production qualification，也不执行 master/Task37c 合入。
