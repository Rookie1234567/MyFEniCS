# Task038-extra Review V9 P8 summary

## 当前范围与结论

| 项目 | 状态 | 关键事实 |
|---|---|---|
| formal branch/source | 已冻结 | `codex/20260820-task38-extra-full3d-iterative-0p7nm` / P1 source `891ef7fba8cb7d154ad9cac61d67652f02063fbb` |
| base | 只读 merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| P0 | PASS | `ba901631` fresh v2；checkpoint/restart、explicit residual、PC legality 和 provenance 闭合 |
| P1 v2 | HARD STOP | 9/16 已运行：8 个 p2 PASS，p3 MPI1/random 固定 2000 步失败 |
| P1 failure | 数值 Gate | final explicit true residual `0.01027838962263555 > 1e-8`；不是内存、swap、ABI 或 checker failure |
| P2–P7 | `not_run_by_gate` | 没有 p6/h10、physical、h5、2 TiB 或 PDE 新结果 |

P1 使用固定 `right GMRES / restart=20 / residual replacement=20 / max_it=2000`。它每 20 步销毁 Krylov 基并从当前解继续；这控制长期内存，但不能保证更高 p 阶仍在固定上限内收敛。详细 9 案事实与 SHA 在 `outcomes/memory_first_small_v2.md` 和 `outcomes/records/memory_first_small_v2.json`。

## 已运行 small cases

| group | cases | final residual范围 | iteration范围 | 结论 |
|---|---|---:|---:|---|
| p2 MPI1 | random/gradient/curl/checkerboard | `8.5985e-11–7.6297e-9` | 60–80 | 4/4 PASS |
| p2 MPI2 | random/gradient/curl/checkerboard | `9.7988e-11–7.6486e-9` | 60–80 | 4/4 PASS |
| p3 MPI1 | random | `1.027838962263555e-2` | 2000 | FAIL_AT_FIXED_MEMORY_ITERATION_CAP |

所有已运行案 worker rc=0、cycle process-tree/rank swap=0、PC finite/repeat/input/primal 合同通过。p3 有 100 个 20-step cycles；完整 100-cycle history 留在 raw，10 个 checkpoint 标量 iteration/residual 摘要已进入 compact；无大数组进入 Git。

## 资源口径

P1 cycle RSS 是 rank-root process-tree ledger；MPI2 不含 launcher。GNU `/usr/bin/time -v` 的最大 RSS 是 worker/launcher 观察，不能当完整 process-tree/cgroup authority。共享 `/init.scope` 的 `13,799,424 B` 仅为 non-dedicated diagnostic；正式 process-tree/rank swap 与 GNU time `Swaps` 都为 0。P1 没有触发 V9 的 p6/h10 `<2,000,000,000 B` workflow Gate。

## 保留的旧结论

| 历史证据 | 处理 |
|---|---|
| V8 M0 negative、9f orientation fix、scalar owner debt | 原样保留；9f 是 research fix，不提升 ordinary default |
| old L2 one-apply | 永久 FAIL：`1.7348663090876784 > 0.45` |
| old v1 80-step performance | FAIL，未重分类 |
| additive-v2 | formally CLOSED |
| P0 | PASS 只归属于 `ba901631` fresh v2 |

## 未运行范围

`lor_hx_p6h10_setup_v2.md`、`lor_hx_p6h10_positive_longrun_v2.md`、`lor_hx_p6h10_physical_longrun_v2.md`、`lor_hx_p6h10_mpi2_v2.md`、`lor_hx_h5_scaling_v2.md` 和 `feasibility_0p7nm_2tib_v3.md` 均明确为 `not_run_by_gate`。对应 compact 入口为 `outcomes/records/memory_first_small_v2.json` 与 `outcomes/records/memory_first_small_v2_checker.json`。因此 p6/h10 inventory、5000 步 positive history、exact physical Maxwell、E/H、R/T/A、recovery、MPI2 physics、h5 scaling、2 TiB 三情景和完整 0.7 nm PDE 都未验证。

## 证据与合入边界

轻量入口为 `outcomes/records/memory_first_small_v2.json`、`outcomes/records/memory_first_small_v2_checker.json`；9 案 record/check/raw 路径和 SHA 逐项绑定，p3 的旧 `check.json` 与修正 `check_v2.json` 同时保留。P1 runner/checker 代码可审阅，但当前 multiplicative-v1 memory-first family 因 p3 p-robust convergence 关闭；不得整体合入 ordinary default。V8 negative 和所有失败 raw 均 `do-not-delete`。若要继续，必须先有新 review 决定新的正确性/性能路线，不能用 restart、omega、shift 或扫描绕过本 hard stop。

## Review V10 Q0 closeout

V10 Q0 只执行了 p3/h50、MPI1、random 的 exact-reference triage。它用小模型的直接 LU/MUMPS 解替代近似辅助 solve，目的是区分“LOR 基础代数有问题”与“近似 HX/PCGAMG 不够强”；这不是生产算法变更。

| 阶段 | 状态 | 关键事实 |
|---|---|---|
| Q0 Reference E | `LOR_AUXILIARY_FOUNDATION_FAIL` | 500 步/25 cycles 后 explicit rho=`4.203423379090078e-4 > 1e-8`；exact edge residual=`9.13154427545479e-16` |
| Q0 Reference N | diagnostic only | final rho=`2.1958595524302254e-3`；四个 nodal direct residual 均约 `5.13e-16–5.24e-16`；一个 raw evidence 坐标混用相对差=`2.8019257502717445` |
| Q1–Q5 | `not_run_by_Q0_hard_stop` | 不再运行 p3 50k、p6 setup、p6 positive 或 physical Maxwell |

E/N 的 finite、repeat、input unchanged、high primal constraint、high RHS repeat、owner route、orientation、phase-once 均有 raw evidence。最大 cycle process-tree RSS=`185102336 B`、swap=`0`；GNU time 单 worker Maximum RSS=`293908 KiB`，不是 process-tree/cgroup authority。

本次 worker 因路径抄写实际使用 `task038_extra3d_q0_v10` 和 `task038_extra3d_iterative_0p7nm`；完成后两份 compact 才做 byte-preserving relocation 到含 `full3d` 的 `outcomes/records/`，内部实际 command/raw/record 字段未改。见 [p3 exact-reference triage](p3_exact_reference_triage.md) 及 relocated records。该 Q0 hard stop 不改变旧 V8/V9 negative、P0 PASS 或 additive-v2 CLOSED，也不证明 p6/h10、2 TiB 或 0.7 nm PDE 可行。

N 的 `0.0` 仅是由 `remaining + edge_action` 推出的 inferred/derived re-encoded initial 与自身的定义性比较；现有 raw 没有独立保存的重编码初始 packet，因此它不作为整个 replay PASS 证据。正式 checker 的 `2.8019257502717445` FAIL 原样保留。

Q0 code-only commit `47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f` 新增的是 research benchmark harness、独立 checker 和 focused test；production numerical core 与 ordinary default 未改。Q0 focused test 为 `7 passed`，旧 `test300`+`test302` M0/P1 回归为 `26 passed`，compileall/AST/diff-check 通过；Ruff 在资格化环境不可用且未安装。formal 结束、Q6 提交前的 measured Git snapshot 为 ahead/behind=`1/0`；当前未提交项只有 Q6 docs/compact，最终 closeout commit/push 状态不在本摘要中预填。
