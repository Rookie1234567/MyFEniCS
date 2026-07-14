# Task032 滚动结果总结

## 1. local migration and branch identity

```text
task = Task032
status = phase0_complete / phase1_full3d_reference_complete / task_in_progress
base and Task031 merge = dae03170b0cdd87f2d72769aea7ce04e32acce2b
branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
old directory = read-only historical baseline
new directory = C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
origin = Rookie1234567/MyFEniCS
ordinary default changed = false
```

详细证据见 `local_migration_record.md`。新库从 Task031 clean merge 后的远程 `master` 克隆，Task032 分支已推送；旧目录未修改。

## 2. frozen physical model

已按任务书冻结：13.5 nm、当前验证 Si、规则双周期结构、主点 10° 掠角/phi=0/S、局部 3D p2 Nédélec、MPI4、direct only。材料扰动、多波长、h/p、自适应迭代法、实验噪声与反演不在 Task032 范围。

## 3. theory-to-code mapping

前置理论和 Task031 交接链已全部读取。Phase 0 完成环境与旧能力迁移；Phase 1 已加入显式、默认关闭的 full-3D 参考面导出，并建立 Case080 配置、命令、records 和 checker。`eigenmodes -> coupling -> solvers -> runner` 尚未开始实现。

## 4. eigenproblem implementation and validation

```text
implementation = not_started
environment = SLEPc 3.24 PEP/TOAR available
planned first gate = homogeneous air analytic beta
```

## 5. mode classification/normalization

`not_started`。后续必须基于 Poynting flux、物理衰减分支、左右模/双正交残差和近简并子空间处理。

## 6. stable propagation

`not_started`。禁止形成含指数增长衰减模的普通 transfer matrix。

## 7. interface projection

`not_started`。第一版使用匹配网格，并要求 trace round trip、orientation 与 projection residual。

## 8. augmented direct result

`not_started`。

## 9. modal-Schur result

`not_started`；必须在 augmented direct 通过后开始。

## 10. truncation convergence

`not_started`。

## 11. full-3D comparison

Phase 1 已从 clean commit `c468c728...` 完成 h5/h3 MPI4 direct reference。两档均生成 z=`10/30/60/90/110 nm`、40x20 周期单元中心网格上的 complex128 E/H；主数组 shape 为 `(5,20,40,3)`，接口显式保存 x/y tangential traces。z=10 从 +z 单元、z=110 从 -z 单元取迹，二者均来自中间模态区域。

h5 为 44,698 DoF，残差 `9.7340e-12`，`R/T/A=0.0890216029/0.4425882787/0.4683901184`；h3 为 198,438 DoF，残差 `9.9234e-12`，`R/T/A=0.0046130314/0.5836533572/0.4117336114`。两者闭合均优于 `1.3e-13`，NPZ/JSON/run-summary 哈希一致。h3 与历史 direct h3 的 R/T/A 绝对差约 `2.3e-14` 或更小。h5/h3 差异大，因此不宣称网格收敛：h5 用作快速开发，h3 是 Task032 主 full-3D 场/RTA reference。Case080 自动 Gate 为 `271/271 passed`。

## 12. angle/polarization smoke

`not_started`。

## 13. memory and timing

Phase 0 h5 full-3D direct 的 simultaneous total peak RSS 为 `2367.133 MB`，elapsed `23.849 s`。该数值用于环境迁移 sanity，不替代后续外部同时 sampler 的正式 Hybrid 内存结论。

Phase 1 冻结参考采样的 E/H 未压缩复制载荷仅 `384000 bytes`，并有 `64 MiB` fail-closed 上限；没有聚集完整 FE vector、matrix 或 volume mesh。

正式 h5/h3 的内部 historical-peak 上界分别为 `2360.723 MB` 和 `8707.480 MB`，elapsed 分别为 `21.178 s` 和 `79.541 s`。这些 peak 不是外部同时采样值，不作为 Task032 最终内存权威。

## 14. negative results

首次最小 Stage4 preset 被继承的 `50 x 50 x 50 nm` 光栅块与 `10 x 10 nm` 平层周期冲突。通过显式零尺寸 A/B 定位后，在新库最小修复 preset 并新增合同测试；原始命令现已通过。失败过程和根因保存在 `old_vs_new_smoke.md`。

## 15. changed files

Phase 0 和 Phase 1 exporter 已提交；Phase 1 evidence 当前 tracked 变化：

```text
benchmarks/check_benchmarks.py
benchmarks/README.md
benchmarks/cases/README.md
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/*
benchmarks/records/benchmark_gate_report.json
notes/reference/code_walkthrough/50_tests_and_benchmark_contract.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/full3d_reference_contract.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md
docs/development_progress.md
```

## 16. merge recommendation

```text
current recommendation = do_not_merge_yet
reason = Phase 1 reference is complete, but the Hybrid eigenproblem/coupling/direct solvers are not implemented
```

## 17. next Task033 decision

`not_applicable_yet`。只有 Task032 证明 Hybrid 正确且内存结构性下降后才评估 Task033。当前下一步是 Phase 2 截面 QEP，先从 homogeneous air analytic beta 开始。
