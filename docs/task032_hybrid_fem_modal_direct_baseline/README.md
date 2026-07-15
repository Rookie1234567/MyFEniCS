# Task032 入口

## 执行顺序

```text
1. 先将 Task031 按 review_report_v2.md 合入 master
2. 在 master 上运行轻量 contracts/checker
3. 记录 Task031 merge SHA
4. 保留旧本地目录为只读历史基线
5. 在 C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal 建立新的 clean clone
6. 从最新 origin/master 创建 codex/20260714-task32-hybrid-fem-modal-direct-baseline
7. 读取 task.md 和 Hybrid 理论笔记
8. 先完成本地迁移 Gate，再开始写 Hybrid solver code
```

## 文件

- [Task032 任务书](task.md)
- [滚动结果总结](outcomes/summary.md)
- [本地迁移记录](outcomes/local_migration_record.md)
- [环境能力记录](outcomes/environment_capability.md)
- [新旧目录 smoke 记录](outcomes/old_vs_new_smoke.md)
- [Phase 1 full-3D reference contract](outcomes/full3d_reference_contract.md)
- [Phase 2 cross-section QEP walkthrough](../../notes/reference/code_walkthrough/42_task032_cross_section_qep.md)
- [Phase 2 clean MPI4 QEP record](../../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/qep_phase2.json)
- [Phase 3 mode classification walkthrough](../../notes/reference/code_walkthrough/43_task032_mode_classification.md)
- [Phase 3 clean MPI4 mode-basis record](../../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/modes_phase3.json)
- [Phase 4 stable propagation walkthrough](../../notes/reference/code_walkthrough/44_task032_stable_propagation.md)
- [Phase 4 clean MPI4 propagation record](../../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/propagation_phase4.json)
- [Phase 5 matched trace/projection walkthrough](../../notes/reference/code_walkthrough/45_task032_modal_trace_projection.md)
- [Phase 5 clean MPI4 trace record](../../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/trace_phase5.json)
- [Phase 6a local FEM mesh walkthrough](../../notes/reference/code_walkthrough/46_task032_hybrid_local_mesh.md)
- [Phase 6c internal modal blocks walkthrough](../../notes/reference/code_walkthrough/47_task032_hybrid_internal_modes.md)
- [Phase 6d augmented direct algebra walkthrough](../../notes/reference/code_walkthrough/48_task032_hybrid_augmented_direct.md)
- [Phase 6e real-QEP h5/M6 runner walkthrough](../../notes/reference/code_walkthrough/49_task032_hybrid_physical_runner.md)
- [Phase 6e clean-source MPI4 integration record](../../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/hybrid_phase6_m6.json)
- [Phase 6e research diagnostic](outcomes/phase6e_research_diagnostic.md)
- [Case080 benchmark contract](../../benchmarks/cases/080_hybrid_fem_modal_direct_baseline/README.md)
- [项目服务需求与技术路线](../project_service_requirements_and_forward_model_roadmap.md)
- [第一阶段冻结范围](../project_service_requirements_phase1_scope.md)
- [Hybrid FEM–Modal 理论笔记](../../notes/theory/hybrid_fem_modal_domain_decomposition.md)
- [Task031 最终审阅](../task031_compact_physical_slab_memory_optimization/review_report_v2.md)

## 核心边界

```text
wavelength = 13.5 nm
material = fixed validated Si
geometry = current regular periodic structure
angles = 1–10 deg grazing parameterization smoke
polarization = S/P
direct solver only
no h/p adaptivity
no new iterative solver
no 0.7 nm
```

Task032 的第一目标是证明中间 z 不变区可以由二维截面模式可靠替代；第二目标才是评估 h2 Hybrid direct 是否进入 2–5 GiB 范围。

Phase 2 的测试入口为：

```bash
mpiexec -n 4 python -m unittest -v src.test.test_32_task032_cross_section_qep
mpiexec -n 4 python -m benchmarks.run_task032_phase2_qep --verified-clean-sha <full-sha>
```

第二条命令要求 tracked source clean；研究工作树必须显式使用
`--allow-dirty-research`，其结果不能升级为正式 record。Windows 宿主先用
`git status` 确认 clean，再把完整 SHA 作为 host clean attestation；Linux
容器只复核挂载仓库 HEAD 与该 SHA 相等，因为 CRLF bind mount 会让容器内
`git status` 把全部文本文件误报为修改。

Phase 2 已在 clean source `33211a4ac6d4f6717351197a93c506e1adec609f` 后完成正式记录与自动 Gate。Phase 3/4 也已分别完成 Poynting 双正交基和稳定双向传播的 clean record；后续状态见下文。

Phase 3 的测试与研究入口为：

```bash
python -m unittest -v src.test.test_33_task032_mode_classification
mpiexec -n 4 python -m unittest -v src.test.test_33_task032_mode_classification
mpiexec -n 4 python -m benchmarks.run_task032_phase3_modes --allow-dirty-research
VERIFIED_CLEAN_SHA=<full-sha> sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase3.sh
```

Phase 3 已在 clean source `72dca66b70515bcf6ccef239005afa43028df72b`
完成正式 MPI4 record，Case080 checker 为 `282/282 passed`。h10 runner 是
分类、双正交和 tracking 合同，不替代 Phase 2 beta 精度或后续 h3 Hybrid
场/RTA 对比。

Phase 4 的测试与研究入口为：

```bash
python -m unittest -v src.test.test_34_task032_stable_propagation
mpiexec -n 4 python -m benchmarks.run_task032_phase4_propagation --allow-dirty-research
VERIFIED_CLEAN_SHA=<full-sha> sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase4.sh
```

Phase 4 已在 clean source `9206e9c964db387448551cdefdc88081ef705441`
完成正式 MPI4 record；100 nm two-port、无反射、被动衰减、composition、
reciprocity 和强衰减负对照均通过，Case080 checker 为 `286/286 passed`。

Phase 5 已在 clean source `b565ac4610dee08a2d313060b7cb26b48145370d`
完成正式 MPI4 record；匹配 3D/2D Nédélec trace、bottom/top 法向、Stage4
left/right round trip、近简并子空间和无 dense `N_Gamma^2` 存储均通过，
Case080 checker 为 `290/290 passed`。Phase 6a--6d 已完成局部 FEM、外端口
DtN、内部模态 blocks 和 rank-major 单体 AIJ。Phase 6e 的真实 QEP h5/M6
已在 clean source `5c1f12e610dd8c6040389c44c31584ab7fba66cd` 生成 MPI4
集成记录，10 个 runner Gate 与 Case080 `294/294` 均通过；研究漏斗的
M4->M6 R/T/A 变化约 `1e-12`。当前下一步是 pointwise H jump、体吸收和
中间选面重建，而不是 Phase 7；该 clean record 仍不是最终 physical official record。
