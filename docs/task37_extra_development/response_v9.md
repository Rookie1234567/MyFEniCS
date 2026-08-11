# Task037-extra Review V9 consolidated response

本文件保留并引用 [response_v8.md](response_v8.md)，不改写 V8 已记录的 H2B fixed-unit numeric hard stop、H2A 证据和历史结论。本轮新增的是 H2B-S0 证据、P0 两次执行边界，以及针对已确认 execution defect 的 exact-class 窄修复测试结果。

## 用户授权与总状态

2026-08-11，用户明确允许：对执行性问题持续做针对性定位、修复和修复后的重跑；在后续数值/物理/资源 Gate 全部通过后继续完整 PDE 目标。这一明确授权覆盖 Review V9 原 P0=1 campaign 之外的 execution-fix rerun，但不放宽任何数值、物理、RSS、swap 或 provenance Gate，也不允许把数值失败包装成执行问题重复运行；不授权新分支、PR、merge/rebase/cherry-pick、force-push、master 或 ordinary default 修改。

## 保留的冻结结论

| 结论 | 状态 |
|---|---|
| G2 LOR-HX | `G2_FAIL` |
| G3 additive LOR-HX | prohibited |
| old G4 sweep with failed LOR-HX | prohibited |
| old H1.2 | `CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED` |
| H1R3.0R / H1R3.1 / H1R3.2 | PASS |
| H2A-R0 / H2A-R1 / H2A-R2 | PASS，但不等于 PDE qualification |
| V8 H2B fixed-unit primary | `FAIL_NUMERIC / NOT_QUALIFIED` |
| ordinary default | unchanged |
| research-only implementation | 不提升为 production numerical candidate |

上述结论继续以 [response_v8.md](response_v8.md) 为历史 authority；本 response 只补充 V9 的 S0/P0 执行边界，不覆盖其原始 evidence。

| 阶段 | 状态 | 结论边界 |
|---|---|---|
| H1R3.0R / H1R3.1 / H1R3.2 | PASS | 保留此前已审 action/identity/scaling evidence |
| H2A-R0 / R1 / R2 | PASS | discovery、JIT hit、constrained factor store；不等于 PDE qualification |
| H2B fixed-unit primary | FAIL_NUMERIC / NOT_QUALIFIED | 详见 `response_v8.md`，不因本轮执行修复改变 |
| H2B-S0 | evidence 可验；direction Gate FAIL | 三组合 valid，但无一组合通过，route=H2B-P |
| H2B-P0 原始 campaign | CONTROLLED_STOP / NOT_QUALIFIED | 旧 telemetry policy 在 stage 中止，online 未启动 |
| H2B-P0 execution-fix rerun | CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED | stage 完成，P0 assembly 超时，未形成数值 summary |
| P1 | not_run / `locked_by_P0` | P0 未 qualification |
| H2B-K normalized two-level coercive solve | not_run / `locked_by_P1` | S0 失败后的 P 路线须先完成 P1 才能返回 K |
| H2D / full-space matrix-free DtN | not_run / `locked_by_H2B-K` | H2B-K 未完成 |
| H4 time-harmonic PDE | not_run / `locked_by_H2D` | 还须通过 H4 Gate |
| official field / RTA | not_run / `locked_by_H4` | 须完成 H4 full solve，并通过 true residual/physics Gate |

## S0 结论保持不变

S0 compact 的 evidence `status=pass` 只表示 raw 记录可被 checker 验证；`s0_direction_gate_pass=false`，三种组合都没有取得方向资格，正式路线为 H2B-P。不能把 S0 写成算法 PASS。S0 的五类 source、687476736 B whole-campaign peak、swap=0、factor+metadata=201933812 B 和 raw/compact 证据继续以 [h2b_scale_invariant_direction.md](outcomes/h2b_scale_invariant_direction.md) 为准。

## P0 两次执行及最小诊断

P0 的 row-complete patch 只围绕 central cell 的 882 个 independent rows，目标是构造 `B_P = R_P B0 R_P^T`，不是全局矩阵或 PDE。P0 的永久边界保持：uncondensed full-space、condensation=false、global matrix/global constraint matrix/static Schur/trace slab/B2-B4 Krylov/KSP/matrix-free DtN/PDE 均未使用，ordinary default unchanged。

| attempt | source | raw | measured outcome |
|---|---|---|---|
| 原始 P0 | `d6f7cc4d1cb334a5666545783add7e171da00c52` | `h2b_p0_d6f7cc4_run1` | stage 在 `b0_compile_started` 附近被旧 monitor 的单帧 unreadable policy 终止；online 未启动 |
| execution-fix rerun | `90a9dbbf01ac06abf3417116831d3483b7f37ca8` | `h2b_p0_90a9dbb_run2` | stage RC0；P0 在 3600.090414687 s timeout，`p0_summary.json` 缺失 |

run2 的实测边界：stage `26.242200638 s`、RC0、peak `1,286,606,848 B`、swap0；P0 elapsed `3600.090414687 s`、RC `-15`、peak `709,206,016 B`、swap0；reason=`timeout`，SIGTERM 足够、无 SIGKILL，进程全部退出。最后 marker 为 `patch_assembly_started`。authority、mesh、space、Floquet、cache、R2 factor/class authority、central cell selection 已完成；central ordinal=3、class=3、touching cells=19。没有生成 P0 factor/rho/solve/patch completion measurement，因此结论是执行 timeout，不是数值算法 FAIL。

### 最可能的性能边界

旧 P0 producer 对 19 个 touching cells 逐 cell 重新 tabulate curl+mass dense tensor。冻结 R2 raw 的 class factor 步骤约 191.78–195.89 s，median 约 193.78 s；因此 `19×193.78≈3681.82 s`，超过 3600 s。run2 的 class 序列是：

```text
[6, 8, 14, 3, 5, 13, 3, 3, 3, 5, 2, 3, 2, 2, 7, 4, 1, 4, 0]
```

它包含 11 个 unique exact classes；按每 class 只 tabulate 一次，旧计时推导的 construction estimate 为约 `11×193.78≈2131.58 s`。这两个数值都是 derived prediction，不是优化后 formal 实测。raw 支持的根因边界是重复 exact-class tabulation 与 timeout 的时间关系；不能把预测写成修复后的 PASS，也不能把 stage/P0 peak写成 PDE 内存。

### 已实现但尚未 formal 的修复

当前代码按 first-seen class 分组、class 内 ordinal 升序；每个 class 只为代表 cell tabulate 一次，随后每个 cell 仍用自己的 `independent_global_rows` 与同 class expansion pattern 累积，组完成即释放 proxy，最多一个 dense proxy 存活。没有改变 patch、orientation、MPC、action、factor、rho 或物理定义，没有 per-cell tensor/cache。

这是 `implemented/tested_only`，不是 P0 PASS。最终测试为 test297 `15 passed`、focused 294–297 `91 passed`，compileall、AST duplicate-key、diff-check 均通过；没有因此重新运行 formal。

## P0 数值状态与长期 PDE 目标

由于 run2 没有 `p0_summary.json`，以下字段全部 `not_measured`：factorization/solve residual、condition/pivot、solve gain、element/patch 五类 `rho_star`、exact-action closure、off-patch spill、class/cell/touching completion audit、P0 online resource qualification。不能从 H2A-R2 factor store 或 S0 evidence 猜测这些字段。

用户要求的 MPI1 full PDE process-tree RSS `<2,000,000,000 B`、swap=0 和 direct authority physics comparison，本轮没有运行 PDE、没有 true PDE residual、没有 field/RTA，也没有 direct-method comparison；stage 的 1.286 GB 和未完成 P0 的 709 MB 都不能冒充 full PDE peak。因此 H3/PDE qualification 仍为 none。

## Evidence index

| evidence | 路径 / 身份 |
|---|---|
| S0 outcome/compact | [h2b_scale_invariant_direction.md](outcomes/h2b_scale_invariant_direction.md)；compact file `44283799e9712aa8e4355fa31e232ce8b3cbf679867c7fface599f3152054637` |
| 原始 P0 outcome | [h2b_row_complete_patch.md](outcomes/h2b_row_complete_patch.md) |
| run2 raw | `benchmarks/artifacts/task037_extra_development/h2b_p0_90a9dbb_run2` |
| run2 watchdog | `p0_watchdog_summary.json` SHA `100128aee4a4c013256a27313cd8f9b4565d75479182e969a24eda8300ec8430`；embedded `7fc7af8e391bd0b30f0663128376de0c5a35dc9291253baca98043053db2ade4` |
| run2 stage summary | `stage_summary.json` SHA `ee7278fd44288753664827677355500e8101d4090d0600677a292ac98d0e2c9f` |
| run2 progress | `p0_progress.jsonl` SHA `d3ac29e2b32755f47a915d874632cf96dcf066892f4fe2b782b7c4fa0893ed59` |
| run2 timeline | `p0_timeline.jsonl` SHA `a8e1b6dc11b78538edbda49745aac677004d359a9fbcd59e13f44c3b57d4a74f` |
| v2 compact | `benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch_v2.json`；SHA `d811b5d5fa834699088b255631a05621b61dbfdb6e150b36850c3eda8944ac3a`；byte-for-byte 保留 |
| old compact | `.../h2b_row_complete_patch.json`；同 SHA `d811b5d5fa834699088b255631a05621b61dbfdb6e150b36850c3eda8944ac3a` |
| V8 history | [response_v8.md](response_v8.md)，不覆盖 |

## 后续与 selective boundary

| 组别 | 当前判断 |
|---|---|
| H2B P0 code/test | research-only，已做 execution-fix implementation/test，不具备 formal qualification |
| S0/P0 compact/raw/docs | 保留 hash-bound 正/负证据，不覆盖旧证据 |
| P1 | `not_run / locked_by_P0` |
| H2B-K normalized two-level coercive solve | `not_run / locked_by_P1`；S0 失败后的 P 路线须先完成 P1 才能返回 K |
| H2D / full-space matrix-free DtN | `not_run / locked_by_H2B-K` |
| H4 time-harmonic PDE | `not_run / locked_by_H2D` |
| official field / RTA | `not_run / locked_by_H4`；H4 full solve + true residual/physics Gate |
| ordinary default | unchanged |

在用户 2026-08-11 的明确授权下，execution issue 可做窄修并重跑；P0 formal PASS 后按 Review V9 Gate 自动推进，无需为一般执行问题等待新的 review。若出现数值负结果，严格走 Review V9 规定分支（包括 §5.4），不能以 execution fix 名义重跑。本轮没有启动新的 formal/heavy，也没有创建 H2D/H4/PDE outcome 或 record。
