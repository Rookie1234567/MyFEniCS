# Task037-extra Response V9：S0 路由与 P0 lifecycle 收口

本文件是 Review V9 本轮新增的 consolidated handoff。它保留并引用 [response_v8.md](response_v8.md)，不改写 V8 已记录的 H2B fixed-unit numeric hard stop、H2A 证据和历史结论。本轮新增两项实际阶段：H2B-S0 完成了尺度不变方向诊断；随后 H2B-P0 只启动 stage，因 telemetry lifecycle race 未进入 online。

## 阶段总表

| 阶段 | 状态 | 实际边界 |
|---|---|---|
| H1R3.0R / H1R3.1 / H1R3.2 | PASS | 保留 V6 已审 action/identity/scaling evidence |
| H2A-R0 / R1 / R2 | PASS | discovery、JIT hit、constrained factor store；不等于 PDE |
| H2B fixed-unit primary | FAIL_NUMERIC / NOT_QUALIFIED | V8 五类 source 的 fixed-unit symmetric 结果失败；保留 response_v8 |
| H2B-S0 | evidence PASS；direction Gate FAIL | 三组合 valid，但无一组合通过 rho_star；route=H2B-P |
| H2B-P0 | NOT_QUALIFIED / controlled execution failure | 只完成 stage，online 未启动；不能判定 P0 数值算法 |
| H2B-K | not_run / locked_by_S0 route and P0 boundary | S0 未产生 K 资格，P0 也未完成 |
| H2B-P1 | not_run / locked_by_P0 | P0 没有资格化 |
| H2D / H4 / PDE / DtN / field / RTA | not_run / locked | 本轮没有物理求解或后处理 |

H3/PDE qualification = none。本轮没有形成任何 H3 或 PDE 资格证据。

S0 compact 的 status=pass 只说明 raw 记录经过 checker 验证且 evidence 可读；关键数值字段 s0_direction_gate_pass=false，三组合的正式方向 Gate 无一通过。因此不能把 S0 写成算法 PASS。

## H2B-S0：实际结论

S0 固定使用 p6/h10、MPI1、252 cells、173802 full-space rows、9210 Floquet identity rows、24 exact classes、16 unique factors 和 factor+metadata 201933812 B。全程保持 uncondensed full-space、无 condensation、无 global matrix、无 Schur/slab/KSP/DtN/PDE，ordinary default unchanged。

永久 identity 仍为 uncondensed full-space；condensation、static condensed operator、trace slab PC、
B2/B4 local Krylov、global matrix、global constraint matrix、KSP、DtN 和 PDE solve 均为 false，slab
matrix/factor 为 0。这些是冻结的 materialization 边界，不是未运行阶段的 PASS。

Additive 只有 checkerboard/high-frequency 未通过，rho_star=0.9594480817867957，高于 0.70；gradient/curl/mixed/physical 分别为 0.00027302412076899286、0.7220541849334704、0.7013670818808797、0.6642345659875032，均在对应上限内。Forward 的五个 rho_star 约为 0.9999929–0.9999989，symmetric 的五个约为 0.9999610–0.9999989，均不合格。于是 checker 从三组完整 valid measurements 重新得到 route=H2B-P，而不是依赖 worker 自报 route。

S0 process-tree peak=687476736 B、swap=0；这是 whole S0 online campaign 的 measured peak，不是 PDE peak。S0 compact 与 outcome 见 [h2b_scale_invariant_direction.md](outcomes/h2b_scale_invariant_direction.md)。

## H2B-P0：唯一 formal campaign 的实际边界

P0 formal source 是 d6f7cc4d1cb334a5666545783add7e171da00c52，Review V9 给 P0 恰好一次 campaign。它启动了 stage 的 jit-worker，在 b0_compile_started 后因一次 process-tree status unreadable 被 watchdog 终止：

| 项目 | measured 值 |
|---|---:|
| stage elapsed | 58.98348014599833 s |
| stage peak RSS | 1281662976 B |
| stage swap | 0 B |
| stage return code | -15 |
| termination | process_tree_unreadable |
| last marker | b0_compile_started |
| p0 command / payload | null / null |
| stage_summary | missing |
| P0 online | not_run |

峰值低于 1.5 GB 不能使 P0 通过，因为 stage 没有正常完成；更不能把它当作完整 P0 build 或 PDE 内存。P0 没有测量 factor residual、solve residual、condition/pivot、solve gain、五类 rho、class/cell/touching inventory、patch closure 或 off-patch spill。因此结论是执行生命周期未完成，而不是 P0 算法 FAIL。

基于 raw 与代码路径的最小诊断是：PID/编译后代集合在最后样本附近发生变化，并出现单帧 all_status_readable=false；旧 monitor 对单次不可读立即杀组。这与短暂子进程生命周期竞态一致，是基于 raw 与代码的最可能诊断；raw 没有直接测得具体的 clone/exec/exit 系统事件。这是 telemetry lifecycle diagnosis，不是数值、factor、action 或 PDE 失败。随后提交的 083fb7863375c197437975bb51847682d9240f9a 是 formal attempt 后的 prospective one-recheck fix，只做了一次固定 20ms H2B 专用复采；test295=32 passed，focused 294–297=89 passed，compileall/AST/diff-check 通过。但该提交没有重新运行 formal P0，也没有 execution-fix rerun；P0 预算保持已消耗状态。

P0 compact 的原始 checker 状态是 gate_failed、pass=false、measurements=null、problem=raw_unreadable:FileNotFoundError。它保持 byte-for-byte 不变，见 [h2b_row_complete_patch.md](outcomes/h2b_row_complete_patch.md)。

## 用户最终目标

用户要求的 MPI1 full PDE RSS < 2000000000 B、swap=0，以及与 direct authority 的物理一致性，本轮没有达成：

- 没有运行 PDE；
- 没有 true PDE residual；
- 没有 field、RTA 或 direct-method comparison；
- S0 的 687476736 B 是 S0 online campaign peak；
- P0 stage 的 1281662976 B 是未完成 JIT stage peak；
- 两者都不能冒充 full PDE process-tree memory。

## 保留的历史结论与停止项

以下结论保持不变：

- G2=G2_FAIL；
- G3 prohibited；
- old G4 prohibited；
- 旧 H1.2 为 controlled timeout / NOT_QUALIFIED；
- H1R3.0R、H1R3.1、H1R3.2 PASS；
- H2A-R0/R1/R2 PASS，但不自动等于 PDE qualification；
- V8 H2B fixed-unit primary 的 FAIL_NUMERIC 仍以 response_v8 为准；
- ordinary default unchanged；
- H2B core/runner 仍是 research-only，不提升为 production numerical candidate。

本轮停止后不进入 P1、H2B-K、H2D、H4、PDE、DtN、field 或 RTA。Review V9 的 P0 预算没有 execution-fix rerun；后续若要处理 telemetry 或重新进行 P0，必须由新 review 明确授权，不能自行重启同一 campaign。

## Evidence index

| evidence | 路径 / 身份 |
|---|---|
| S0 outcome | [h2b_scale_invariant_direction.md](outcomes/h2b_scale_invariant_direction.md) |
| S0 compact | benchmarks/cases/101_task37_extra_development/records/h2b_scale_invariant_direction.json；file SHA 44283799e9712aa8e4355fa31e232ce8b3cbf679867c7fface599f3152054637；embedded c773ba5f96419e9afb433936b348ed5b3f251003b02a7c2e3f3af0e5a675c98f |
| S0 raw | benchmarks/artifacts/task037_extra_development/h2b_s0_053f5cb_run1；source 053f5cbb577e6e81571748d1580aa3858b5eeece |
| P0 outcome | [h2b_row_complete_patch.md](outcomes/h2b_row_complete_patch.md) |
| P0 compact | benchmarks/cases/101_task37_extra_development/records/h2b_row_complete_patch.json；file SHA d811b5d5fa834699088b255631a05621b61dbfdb6e150b36850c3eda8944ac3a；embedded 52e9251d46b1c6b7353f7975fb0ffa8e15ee63f15ae0691cab216ba980d98f3e |
| P0 raw | benchmarks/artifacts/task037_extra_development/h2b_p0_d6f7cc4_run1；watchdog SHA 514ae1f01ab6f6dd1126f4b8790c0e47bf69acbae52ff2ebc1e38e2dbeaa60a2；stage progress SHA ac2b6278b467d42c469e1c8df2a4daa38a841e60ede9e08202d4c13bc14170f3；timeline SHA 09fe1b0bffd989cb77b5af26a24b63a2344ca5d9c671b79a97fa3c75fb583a4a |
| historical consolidated handoff | [response_v8.md](response_v8.md)；保持不改 |

## 文档与合并边界

| 组别 | 当前建议 |
|---|---|
| S0/P0 research implementation | 不视为 production numerical candidate；不改变 ordinary default |
| S0/P0 tests | 可保留作为生命周期和负结果回归 |
| compact evidence/raw | 保留 hash-bound 负证据，禁止覆盖旧 evidence |
| H2B-K/P1/H2D/H4/PDE | do-not-run，等待新 review |

本轮没有创建 h2b_normalized_global_solve.md、h2d_fullspace_dtn.md 或 h4_fullspace_pde.md；没有新增 H2D/H4/PDE record。
