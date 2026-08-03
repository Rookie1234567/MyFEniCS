# Task004 Response V3：M4A/M4B/M4C controlled stop

## 已完成

1. 保留并只引用批准的 forward identity：`fdf961545f217d620e22800f2704ae9913a6d270`、Full3D static uniform N1curl p5/h10/Ny4、ICNTL(14)=40；没有重跑 96 个 FEM。
2. 建立不可变 `task004_angle_nominal_p5_ny4_train96_v2` package；`forward_solver_sha` 与 `surrogate_dataset_builder_sha` 分离。独立 Case125 checker 通过。
3. 建立独立的 response-blind spatial windows 和 mask-topology coverage。24 个 blind 设计的 mask signature 在 train96 中均有覆盖；4096 candidate 中未见 signature 会由 API 明确标记 unsupported/unqualified。
4. 完成 baseline/production candidate 分离、selected aggregate end-to-end power OOF、overlapping region 报告、逐 target cross-fitted uncertainty calibration 和 fail-closed API guard。
5. 完成同一 96 点上的 training-only 5-fold CV；所有折的 fitted kernel/LML/boundary/warning provenance 被保存。

## Gate 结果与停止原因

没有 production GP 同时通过 aggregate、spatial、uncertainty 和 power Gate。最佳代表为 `gp:F3/jitter=1e-6`，但 aggregate 的 `A_balance` NRMSE/p95/max 为 `0.04139/0.02466/0.14322`，cutoff-near 与 high-azimuth spatial windows 也超过 p95≤0.02；power side ledger 虽为 `2.22e-16` 且 mask 100%，primary channel accuracy 未通过。它的综合 score 4.9507 也没有优于 local-RBF baseline 4.4861，因此不满足 Review V2 的主动学习资格。

按任务书本轮受控停止：不运行 16 个新 FEM，不运行 24 个 blind FEM，不创建模型锁，不访问 frozen validation。完整证据位于 `benchmarks/cases/125_task004_angle_training_qualification/outcomes/`；等待 Review V3。

当前执行分支仍为 `codex/only-one-13p5nm-surrogate-inversion`，forward evidence、Case124 和 Task003 数据均未改写。
