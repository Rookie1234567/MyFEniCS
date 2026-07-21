# Task034 Response V5

## 结论

Review V4 的全部 final pre-merge finding 已关闭。本轮未修改 Maxwell、Floquet、QEP、DtN 或 Hybrid 数值核心，未重跑已接受的 p3/h3、p4/h5、M funnel 或 MPI 重型矩阵。

review_v4_findings = closed
heavy_pde_rerun = not_required
production_mainline = S polarization
selective_merge_authority = Review V4 + user final instruction
whole_branch_merge = forbidden

## Hybrid elements 与 hermetic aggregation

- 对 18 条 fe_dofs > 0 的 Hybrid 行，逐条核验 accepted artifact 与 compact provenance 中的 SHA-256 完全一致；
- elements 采用权威口径 prod(bottom_local_mesh_cells) + prod(top_local_mesh_cells)；
- 结果覆盖 72、288、480、2592、7020 五档，全部大于零；
- fixture provenance 保存每行 bottom/top 三轴计数、reduction 和最终值；
- metadata 已区分 extraction_process、fixture_schema_version 与 output_aggregator；
- 普通聚合器和 clean-checkout 测试仍不打开 benchmarks/artifacts；
- all_model_results.json/csv 与 authority audit 已重建，test86 增加零值语义和18行精确值回归。

## 当前能力与路线

- docs/capability_matrix.md 将旧 p2/h5-h3-h2、MPI4 约束明确限定为 Task027–Task031 canonical iterative profile；
- 新增 Task034 Case093 fixed-geometry qualification，明确 p2/p3/p4 S 主线、代表性 MPI1/8/16、MPI32 exploratory、M funnels、受控 stop 和单点 P capability；
- 当前能力/路线文档不再冻结 Task036 编号；后续依次描述 scalable modal core、low-memory Hybrid iterative 与 wavelength continuation to 0.7 nm；
- Task035 仍是 planning package，本轮未执行 Task035 code/PDE。

## 精确 changed-files 与 selective manifest

changed_files.md 与 manifest 以执行时真实 origin/master 和当前 Task034 tree 机械生成，并由 benchmarks/task034_selective_merge_manifest.py 验证：

manifest_rows = 170
changed_paths = 170
include_paths = 159
exclude_paths = 11
already_on_master_paths = 0

每个真实 changed path 有且只有一行；额外行只允许是 master 已存在且与 source 内容相同的 authority dependency。src/geometry/task034_adaptive_mesh.py、adaptive runners/tests 继续为 research_only_do_not_merge_yet；未选 historical compatibility 和 review-only research helpers 明确排除。 合并后 collection Gate 进一步确认：显式选择 run_task033_memory_watchdog.py 与 run_task032_phase6_augmented.py 两个必要兼容依赖；test75/test85 与各自 review-only helper 成组排除，避免孤立测试进入 production。 master test73 又将11个 repository-wide clean-source/resource-authority hardening 文件确认为整体依赖并显式选择；全仓 collection Gate 进一步确认 run_task033_full3d_watchdog.py 是已选 test68 的直接依赖并显式选择；全仓 test57 和 test60 进一步确认 run_task033_case090_watchdog.py 与 task033_hybrid_funnel.py 是直接依赖并显式选择；其余 optional 继续排除。

## 最终门禁

- test86 / no-artifact aggregation：10 passed；
- governance + documentation + Task034 test24/test26/test73–86：129 passed；
- manifest exact coverage：170 rows / 170 changed / 159 include / 11 exclude / 0 already-on-master；
- qualified complex ABI full pytest：505 passed，18 skipped，244.80 s；
- post-selective master targeted tests：109 passed，2.09 s；
- post-selective master full pytest：485 passed，18 skipped，238.92 s；
- scoped Ruff：pass；
- compileall：pass；
- staged/working git diff --check：pass；
- full-repository Ruff 的15条既有、范围外 lint debt 已如实记录，未修改数值核心。

所有 Gate 以最终改动后实际结果为准；失败不会改写为通过。

## File-level selective merge 规则

通过全部 Gate 后，只按 manifest 的 include action 与 dependency order 把文件级内容应用到最新 clean master；不使用 whole-branch merge、rebase 或 cherry-pick。排除：

- research_only_do_not_merge_yet；
- review_only_do_not_merge_to_production；
- 未明确选择的 historical_compatibility_optional。

合并后在 master 重新运行 governance、documentation、Task034 accepted/production、hermetic aggregation 与 full pytest，再提交并推送。随后才从已推送的 clean origin/master 创建 Task035 分支。
