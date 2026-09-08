# Test summary

QEP focused suite 在 native ABI、线程全1下完成；本轮未运行 PDE、formal、full suite、ruff 或 compileall。

新增 controlled-stop node 首次仅因 fake config 缺 `n_air` 失败，最小修正测试夹具后=`1 passed`（wall=`2.15 s`）；最终四节点 serial=`4 passed`（wall=`1.32 s`），MPI2 每 rank=`4 passed`（wall=`1.69 s`）。此前 `1.34 s` 是不存在 test node 的 collection 命令拼写错误（`no tests ran`），不是代码失败。

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

优化记录：旧 reciprocal mass overlap 为 `3PN` MatMult（M800=`1,920,000`、M1200=`4,320,000`），新实现为 `P+N`（1600/2400），仍保留完整 P×N dots/Hungarian assignment；K0/K1/K2 Frobenius norms 每 operator tuple 一次，公式/Gate不变；`timings[reciprocal_pairing]` 已进入 producer controlled-stop record。新归约顺序只承诺 Gate 内浮点等价；下一次 packet 是新的 source-bound hash，仍须通过 canonical/selection Gate，不承诺与旧 packet byte-identical。当前无 post-change formal performance 数据，M1200 未运行，Task041 physics stop 仍有效。

完整 raw factor_inventory 已保存在 ignored roots；compact docs 仅摘录 bottom/top corrected NNZ、MUMPS factor-only、ICNTL14=40 和关键 lifecycle 字段，本轮不倾倒 raw。仍缺：5 nm MPI1 合格 packet、consumer/workflow 内存 authority 和完整 equivalence；3 nm official RTA、M/grid convergence；2 nm 全部结果；逐 rank 或分阶段 PSS/USS；完整 raw 数组和逐通道复核。上述项目均标为 NA 或 not_run，不补猜值。
