# Task032 滚动结果总结

## 1. local migration and branch identity

```text
task = Task032
status = phase0_complete / task_in_progress
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

前置理论和 Task031 交接链已全部读取。Phase 0 只完成环境与旧能力迁移；`eigenmodes -> coupling -> solvers -> runner -> Case080` 尚未开始实现。

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

Phase 0 已证明现有 full-3D h5 MPI4 direct 在新目录可运行：44,698 FE DoF、80 auxiliary modes、真相对残差 `1.3033e-11`，`R/T/A = 0.0890216029 / 0.4425882787 / 0.4683901184`，闭合误差 `1.2124e-13`。这只是迁移基线，不是 Hybrid 对比结果。

## 12. angle/polarization smoke

`not_started`。

## 13. memory and timing

Phase 0 h5 full-3D direct 的 simultaneous total peak RSS 为 `2367.133 MB`，elapsed `23.849 s`。该数值用于环境迁移 sanity，不替代后续外部同时 sampler 的正式 Hybrid 内存结论。

## 14. negative results

首次最小 Stage4 preset 被继承的 `50 x 50 x 50 nm` 光栅块与 `10 x 10 nm` 平层周期冲突。通过显式零尺寸 A/B 定位后，在新库最小修复 preset 并新增合同测试；原始命令现已通过。失败过程和根因保存在 `old_vs_new_smoke.md`。

## 15. changed files

Phase 0 当前 tracked 变化：

```text
src/main.py
src/test/test_27_main_preset_contract.py
docs/development_progress.md
docs/task032_hybrid_fem_modal_direct_baseline/README.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/local_migration_record.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/environment_capability.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/old_vs_new_smoke.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md
```

## 16. merge recommendation

```text
current recommendation = do_not_merge_yet
reason = Task032 implementation has not started; only Phase 0 migration Gate is complete
```

## 17. next Task033 decision

`not_applicable_yet`。只有 Task032 证明 Hybrid 正确且内存结构性下降后才评估 Task033。当前下一步是 Phase 1 full-3D reference contract 与 field/trace extraction 设计。
