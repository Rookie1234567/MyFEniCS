# Response V9：V8 K4 recycled p4 收口

## 审阅范围与结论

本轮阶段已完成 K0 preparation、K1 RESET/CARRY controls 和唯一 K2 original outer；K2 未通过进展/residual Gate 后，K3 official/notch/recovery 路径保持锁定，最后的 K4 阶段只完成 compact evidence 与文档收口。K4 没有启动新的 PDE、MPI、rank expansion、candidate rerun 或 workstation heavy case。

V8 K2 是一个可复核但未通过完整外层 Gate 的受控负结果：同一物理模型、`complex128/MPI1/线程1` 下运行 `59` 个 PC 后按 screen 规则停止；worker 为 `NORMAL_SCREEN_STOP`，parent 包装分类为 `WORKER_FAILED`。独立 checker 的 full explicit true residual 为 `0.09114277170870674`，高于 `1e-6`；因此本候选登记为 `RECYCLE_BOUNDED_NEGATIVE`，不产生 official E/H、R/T/A、`A_volume`、near-field 或衍射级。

## 已补齐的数值证据

- K1 六个固定 RHS 的 RESET/CARRY 序列时间为 `103.68024972011335 s` / `84.27563998301048 s`，CARRY 减少 `18.7158207946894%`；六项均较快，但 native residual 和 `eps` 已逐项保留，未宣称数值等价。
- K1 两次完整 control 的 PC 秒数、g2 native residual、g2 recompute 和 `eps` closure 均已写入 compact record；两个 closure relative 分别为 `7.43849805248163e-12` 与 `7.94492074043166e-12`，低于 `1e-8`。
- K2 内层保留 `118` 个逐 I4 compact rows；`A4_matvec=1098`、`explicit_A4=260`、最大 I4 elapsed `16.918557867058553 s`、B4 累计 `980`，118 次返回全部 approximate、目标命中为 `0`。
- K2 native spot 审计最大绝对误差为 `3.048957055467129e-12`。逐 I4 compact 中的 pool closure/orthogonality 最大误差为 `1.3729122738464301e-12` / `8.420384855112346e-14`，对应 pool 限值均为 `1e-10`；它们不是终端 `eps` closure。真实 BAL_H 终端 `eps` audit 的 closure relative 为 `8.534472501127559e-13`，限值为 `1e-8`，共 3 次 audit。compact rows 只保留审阅所需标量，不包含向量或大型 raw。

V8 在前 59 个外层 PC 的 B4 累计为 `980`，V7 A 为 `1888`，少 `908`（`48.09322033898305%`）。这是内部工作量减少，不是完整 solver speedup；同第 56 个 PC 时 V8 residual `0.09320528571929491`，仍高于 V7 A 的 `0.075149822567280145` 和 V5 exact p4 的 `0.030977506489411246`。

## 资源与账本边界

K2 process-tree RSS 峰为 `1530359808 B`，swap/global swap delta 均为零，后代已清场。资源安全不等于数值成功。账本中的 `3600 s` 是 preparation 的保守 RESERVED 上界，不是实测 CPU/墙钟；K2 实际 outer charge 为 `2060.801451572 s`，`5660.801451572001 s` 是 reserve 加实际 charge 的记账结果。K1 parent 的 `512.710820815 s` 已在 reserve 内计入一次，nested stage/control 时间没有重复加入；旧 V7 费用没有并入。

## 文件、测试与后续边界

本轮新增/更新了 [K4 中心结果](outcomes/recycled_p4_outer_v8.md)、[K4 outer compact](outcomes/records/recycled_p4_outer_v8.json)、[逐 I4 compact](outcomes/records/recycled_p4_i4_rows_v8.json)、[summary](outcomes/summary.md)、[run index](outcomes/records/run_index.json)、[test summary](outcomes/test_summary.md)、[development progress](../development_progress.md)、[model registry](../development_model_registry.md) 和 [workstation handoff](outcomes/workstation_handoff.md)。V5 成功 baseline、V7 负结果、K1 `checker_pre_fix` 及 ignored raw 均保留。

收口只执行 qualified activation 下的 JSON/schema/hash/link 检查和 `git diff --check`；没有重跑 pytest、正式 checker、PDE、MPI、factor 或 full repository suite。没有 CI 通过声明。ordinary default 保持不变；本响应不构成 `master` merge approval。
