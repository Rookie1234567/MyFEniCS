# H2B-P0 row-complete patch：formal lifecycle negative evidence

本记录对应 Review V9 的 H2B-P0 唯一 formal campaign。它只记录一次代表性 row-complete patch 试验的执行边界；由于 stage 在 form JIT 编译阶段被 watchdog 的 telemetry lifecycle 误终止，P0 online 没有启动。因此本记录是 NOT_QUALIFIED 的执行负证据，不是 P0 数值算法失败。

## 先用通俗语言说明

element block 只看中心 cell 自己贡献的局部矩阵。row-complete patch 则把所有会影响中心 cell 独立行的 touching cells 贡献都装配到同一个 882×882 局部算子中。这样可以检查“只因邻接 cell 被遗漏而导致的局部逆失效”这一种风险，但它仍然不是全局矩阵、全局约束矩阵或 PDE 求解器。

本次卡在更早的 form JIT/stage 生命周期：watchdog 观察编译子进程的 /proc 状态时遇到一次不可读，就终止了 stage 进程组。因 stage summary 没有生成，online、patch matrix、factor 和 source measurement 都没有开始。后来的 telemetry 修复只经过 focused tests，没有重新消耗 P0 formal campaign。

## 结论与永久边界

| 项目 | 实际结论 | 分类 |
|---|---|---|
| P0 formal budget | Review V9 contractual allowance=唯一一次；observed dispatch=stage 已启动并终止 | contractual + observed dispatch |
| formal source | d6f7cc4d1cb334a5666545783add7e171da00c52 | measured |
| watchdog | RC=1，status=gate_failed | measured |
| checker | RC=1，status=gate_failed，pass=false | measured |
| P0 Gate | NOT_QUALIFIED | measured |
| 数值算法结论 | 未进入数值阶段，不能判定算法失败或通过 | not_measured |
| P1 / H2B-K / H2D / H4 / PDE | 未运行、锁定 | not_run |

P0 compact 的 measurements 为 null，problem 是 raw_unreadable:FileNotFoundError。这里的 checker failure 表示 raw 不完整，不表示 row-complete operator 的 factor residual、solve residual 或五类 rho 不合格。

## 冻结范围

| 字段 | 值 | 分类 |
|---|---:|---|
| discretization | p6/h10 | measured scope |
| MPI | 1 | measured scope |
| full-space rows | 173802 | measured scope |
| Floquet identity rows | 9210 | measured scope |
| cells / local nloc | 252 / 882 | measured scope |
| operator | B0 = K_curl + k0^2 M_abs_epsilon；代码含 1/mu_r，固定 mu_r=1 | frozen identity |
| patch definition | R_P B0 R_P^T | frozen P0 scope |
| construction | touching-local-tensor streaming | frozen P0 scope |
| online RSS Gate | <1500000000 B | not reached |
| swap Gate | 0 B | stage measured 0；online not run |
| ordinary default | unchanged | measured identity |

永久 identity 也保持冻结：uncondensed full-space；condensation=false；global matrix、global constraint
matrix、static condensed operator、trace slab PC、B2/B4 local Krylov、KSP、DtN 和 PDE solve 均为
false；slab matrix/factor 为 0；ordinary default unchanged。它们是 scope/materialization identity，
不是 P0 数值通过。

## 实际执行阶段

| 阶段 | 实际值 | 含义 |
|---|---:|---|
| stage command | jit-worker | 已启动 |
| stage last marker | b0_compile_started | measured |
| stage elapsed | 58.98348014599833 s | measured |
| stage peak RSS | 1281662976 B | measured；终止前 stage 峰值 |
| stage swap | 0 B | measured |
| stage return code | -15 | measured |
| termination | process_tree_unreadable | measured |
| stage summary | 缺失 | measured |
| p0 command | null | measured |
| p0 payload | null | measured |
| online | 未启动 | not_run |

虽然 stage 峰值数值低于 1500000000 B，但 stage 没有正常完成，不能把它写成 P0 build 通过资源 Gate。没有生成 class/cell/touching inventory，也没有任何 P0 factor 或 source result。

## Telemetry 根因边界

stage timeline 在此前正式样本中能读取全部 PID；接近 58.95 秒时，PID/编译后代集合在最后样本附近发生变化，并出现一次 all_status_readable=false。旧 watchdog 将这次单帧 /proc status race 解释为 process_tree_unreadable 并终止进程组。它与短暂子进程生命周期竞态一致，是基于 raw 与代码路径的最可能诊断；raw 没有直接测得具体的 clone/exec/exit 系统事件。raw 能支持的结论是：

1. 这是监控生命周期诊断，发生在 form 编译阶段；
2. 它不是 P0 数值 residual、factor condition、row mapping 或 source rho 失败；
3. 它也不能证明完整 P0 build 会通过或超出 1.5 GB，因为 online 根本没有启动。

formal attempt 后的 telemetry 窄修复提交 083fb7863375c197437975bb51847682d9240f9a 只允许一次固定 20ms 的 H2B 专用复采：恢复时保留正常 worker sample，持续不可读仍 fail-closed，terminal 尾帧不计正式 peak。修复后的 test295=32 passed、focused 294–297=89 passed；这些是 implementation/tested 结果，不是新的 P0 formal qualification。Review V9 的 P0 预算没有 execution-fix rerun。

## P0 尚未测量的合同字段

| 字段 | 状态 |
|---|---|
| selected class / central cell / touching cell count | not_measured |
| element block 与 row-complete patch factor | not_measured |
| factorization residual / solve residual | not_measured |
| pivot growth / reciprocal condition / solve gain | not_measured |
| 五类 element 与 patch rho_star | not_measured |
| exact-action patch closure / off-patch spill | not_measured |
| class/cell/factor SHA binding | not_measured |
| P0 online process-tree peak | not_measured |
| P1 eligibility | false；P0 未形成 qualification |

不能从 H2A-R2 的 factor store 或 S0 的 687476736 B 峰值推导这些 P0 数值。也不能把 stage 1,281,662,976 B 当作 full P0 build 或 PDE 内存。

## Evidence 索引

| evidence | 路径 | SHA / 状态 |
|---|---|---|
| formal raw | benchmarks/artifacts/task037_extra_development/h2b_p0_d6f7cc4_run1 | ignored raw |
| watchdog summary | raw/p0_watchdog_summary.json | 514ae1f01ab6f6dd1126f4b8790c0e47bf69acbae52ff2ebc1e38e2dbeaa60a2 |
| stage progress | raw/stage_progress.jsonl | ac2b6278b467d42c469e1c8df2a4daa38a841e60ede9e08202d4c13bc14170f3 |
| stage root PID | raw/stage_root_pid.json | 9ff92245b304f8b019a3e421c523f1c898bc805f9f7fb1b0efbf9d535d564140 |
| stage stdout | raw/stage_stdout.txt | 1d5791863505d38408c3bd843e0ad247b4d511892f69b9d007173926cebf3cb5 |
| stage timeline | raw/stage_timeline.jsonl | 09fe1b0bffd989cb77b5af26a24b63a2344ca5d9c671b79a97fa3c75fb583a4a |
| P0 compact | benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch.json | file d811b5d5fa834699088b255631a05621b61dbfdb6e150b36850c3eda8944ac3a |
| compact embedded evidence | 同一 compact | 52e9251d46b1c6b7353f7975fb0ffa8e15ee63f15ae0691cab216ba980d98f3e |

P0 compact 保持 checker 原字节，不手工改写；其 measurements=null 与 raw_unreadable 问题是本次执行边界的一部分。

## 后续停止项与长期目标

本轮不重跑 P0，不进入 P1、H2B-K、H2D、H4、PDE、DtN、field 或 RTA。长期目标 MPI1 full PDE RSS < 2000000000 B、swap=0 以及 direct authority physics comparison 都没有测量或达成；stage 的约 1.282 GB 不能冒充 PDE peak。
