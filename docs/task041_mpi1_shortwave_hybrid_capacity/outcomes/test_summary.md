# Test summary

本轮是 docs-only 受控停止；按主控指令没有运行 pytest、MPI、PDE、compile、ruff 或任何 formal。后续 focused suite 由主控另行授权，本文件不虚构测试结果。

| 项目 | 状态 | 说明 |
|---|---|---|
| 20260907 3 nm fresh | 已有 artifact | consumer_exit(solution_snapshot_destroyed)，IMPLEMENTATION_FAILURE；五残差仅 diagnostic marker only，formal_result/gates/physics=null；资源与 cleanup lifecycle 保留 |
| 20260908 3 nm retry | 已有 artifact | solve/recovery mechanics通过，own physics closure失败；candidate only |
| 5 nm Task039 inherited MPI8 | 已有 authority | full numerical/recovery/physics pass；不是本机复现 |
| 5 nm Task041 local MPI8 | 已有 authority | solve/recovery/physics pass；独立本机 reproduction |
| 5 nm source-only S1 | 已有 audit | keys/roundtrip/repeat通过，但 source semantics Gate失败 |
| 5 nm MPI1 | 四次 attempt | 保留 producer/resource、external-key 和 terminal-sample 的精确失败层次；equivalence未建立 |
| 2 nm、3 nm后续 M/MPI1 | not_run | NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE |

20260907 producer 事实：qep_begin=0.192512509 s、qep_ready=17998.540383 s、producer peak=16.784275055 GiB、packet bytes=913401973、packet write max-rank=0.963676714 s、consumer_qep_required=false。qep_begin 到 qep_ready 不被统称为 eigensolve。

完整 raw factor_inventory 已保存在 ignored roots；compact docs 仅摘录 bottom/top corrected NNZ、MUMPS factor-only、ICNTL14=40 和关键 lifecycle 字段，本轮不倾倒 raw。仍缺：5 nm MPI1 合格 packet、consumer/workflow 内存 authority 和完整 equivalence；3 nm official RTA、M/grid convergence；2 nm 全部结果；逐 rank 或分阶段 PSS/USS；完整 raw 数组和逐通道复核。上述项目均标为 NA 或 not_run，不补猜值。
