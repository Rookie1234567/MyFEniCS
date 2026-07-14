# Task032 滚动结果总结

## 1. local migration and branch identity

```text
task = Task032
status = phase0_complete / phase1_full3d_reference_complete / phase2_implementation_passed_clean_record_pending / task_in_progress
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

前置理论和 Task031 交接链已全部读取。Phase 0 完成环境与旧能力迁移；Phase 1 已加入显式、默认关闭的 full-3D 参考面导出，并建立 Case080 配置、命令、records 和 checker。Phase 2 已实现 `matching cross-section -> mixed QEP -> distributed PEP`；`classification -> coupling -> Hybrid solvers` 尚未开始。

## 4. eigenproblem implementation and validation

```text
implementation = passed in MPI4 tests and dirty-research benchmark
space = transverse N1curl(p2) x longitudinal Lagrange(p2)
polynomial = K0 + beta*K1 + beta^2*K2
solver = SLEPc 3.24 PEP/TOAR + shift-invert MUMPS
ownership = distributed reduced/full vectors; no rank0 full gather
clean formal record = pending code commit
```

二维截面复用 Stage4 三维 hexa 网格的 x/y 轴，并支持 homogeneous air、homogeneous lossy Si 和当前 air/Si `epsilon(x,y)`。双 Floquet 约束只复制周期边界规模元数据，显式构造分布式 `u=Cq`，矩阵通过 `C^H K C` 稀疏约化。MPI4 测试覆盖 Bloch phase、Nedelec orientation、无 slave-chain、解析复 beta、正反向配对、残差、归一化和 ownership。

研究验证中，air 基模从 h5 到 h3/h2/h1.5 单调逼近解析 `0.0808195317 1/nm`；h2/h1.5 相对误差约为 1.13%/0.455%。h5 的大误差来自 10° 掠入射下 `beta^2=k^2-k_t^2` 对横向色散高度敏感，不能拿 h5 单点否定 QEP 符号。正式数值将在 Phase 2 code commit 后 clean 重跑并写入 Case080 record。

## 5. mode classification/normalization

Phase 2 已提供 electric-L2 场尺度归一化，验证后范数为 1；它不是最终功率归一化。Poynting flux、物理衰减分支、左右模/双正交残差和近简并子空间处理仍属于 Phase 3，当前不得提前宣称完成。

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

Phase 0/1 已提交；Phase 2 implementation 当前 tracked 变化包括：

```text
src/modes/cross_section_spaces.py
src/modes/quadratic_beta_eigenproblem.py
src/constraints/cross_section_floquet.py
src/geometry/mesh_builder_3d.py
src/test/test_32_task032_cross_section_qep.py
benchmarks/run_task032_phase2_qep.py
notes/reference/code_walkthrough/42_task032_cross_section_qep.md
notes/theory/hybrid_fem_modal_domain_decomposition.md
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
