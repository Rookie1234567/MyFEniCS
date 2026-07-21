# Task034 Codex response v3

## 交付结论

Review V2 的三个 blocking findings 已关闭。Task034 总状态保持 PASS_WITH_QUALIFICATIONS：uniform benchmark 与代表性 MPI identity 通过；equal-accuracy graded compression 仍是受控负结果；field-driven adaptivity 仍未资格化；0.7 nm production target-accuracy feasibility 仍为 unknown。失败、超时、缺失 exact metric 和资源停止均原样保留，没有放宽阈值或改写为通过。

正式主线继续使用 S polarization。没有为表格完整性重跑整套 P incidence；既有 p2/h5 P sample 仅作为 capability sample。

## Git 与 Review 权威身份

| 字段 | full SHA / 状态 |
|---|---|
| branch | codex/20260717-task34-workstation-wsl-adaptive-scalability |
| Review V3 branch base | 1f7911b1932b1bd64160c95253cd410399b3d00b |
| Review V3 reviewed-content commit | 2ce6befca16441fe6b1f3f338c67b1a018559695 |
| sync policy | 只对当前 Task34 分支执行 fast-forward pull |
| forbidden history operations | 未 merge/rebase/cherry-pick origin/master；未 force push 或重写历史 |
| numerical core | Maxwell/Floquet/QEP/Hybrid 核心未修改 |

response_v3.md 的交付提交是 reviewed-content commit 的直接子提交。Git 提交对象不能在自身内容中预写自身 SHA；最终推送后的 branch HEAD 由交付回执中的本地与远端 git rev-parse 共同确认。

本轮 fast-forward 带入的 AGENTS.md 与 review_report_v2.md 是只读 Review 权威输入，未被 Task034 修改，也不列入 Task034 selective-merge manifest。

## Blocking Finding 1：统一事实表字段语义

已移除含义敏感字段的无边界递归搜索，改为 Full3D 与 Hybrid 显式 schema path：

- p3/h3 Hybrid M160 MPI8 total_seconds 为 661.4100284820015，不再误绑 Full3D 的 1726.3617402129894。
- Full3D factor_nnz 只接受 stage4_dtn_factor_inventory；p3/h3 为 1,307,605,045。
- Hybrid 没有 factor inventory 时 factor_nnz 保持 null，不再使用 matrix_nnz_used 冒充 factor inventory。
- Hybrid external_aux_dofs 从两端 global rows 与 local FE DoF 精确推导；p3/h3 为 80。
- p3/h3 Hybrid 行满足 223770 + 80 + 320 = 224170。
- 仓库内 evidence_path 全部正规化为相对路径；仓库外绝对路径必须带 external_absolute 前缀。
- p3/h3 M-funnel 改用 current-source MPI8 权威记录：M80/M120/M160 总耗时分别为 529.556179、567.573403、661.410028 s。
- Hybrid A_volume 使用 physical_field_reconstruction.volume_absorption.A_volume_total 显式路径。
- MPI 行的结构 rows 从同一 Case093 权威 descriptor 绑定；Hybrid p3/h5 为 44,014 rows。

all_model_results.json 与 all_model_results.csv 已确定性重建并交叉校验：40 行、36 列，临时重建结果与仓库文件逐字节一致。

## Blocking Finding 2：summary 直接可审查

summary.md 现在直接覆盖全部 40 行事实：

1. 表 1a/1b：26 个固定几何主线与补充模型，直接列出状态、R/T/A_balance/A_volume、R00、FE DoF、external auxiliary DoF、modal unknowns、total rows、peak memory 和 total time。
2. 表 2：6 个 M-funnel 记录，明确 p3/h3 为 current-source MPI8，p4/h5 为 MPI4 formal；列出 M、modal、rows、R/T/A/Avol、R00、residual、memory、time 与相邻 M 最大差。
3. 表 3：8 个 MPI identity 记录，列出 method、MPI、M、rows、R/T/A/Avol、residual、memory、total time、reported core time 与最大物理漂移；MPI32 保持 exploratory。
4. 表 4：保留三个 Full3D assembly-only resource stop、p2/h1 Hybrid timeout 和两个 Hybrid shard 结果。

Full3D MPI identity 权威记录没有端到端 total，因此 total 明确保留 null，另列 stage4_dtn_port_assembly_and_solve；没有把阶段耗时冒充总耗时。

## Blocking Finding 3：adaptive selective-merge 边界

src/geometry/task034_adaptive_mesh.py 在 selective_merge_manifest.csv 中已改为：

- merge_action = research_only_do_not_merge_yet；
- dependency_group = research_only_conforming_graded_mesh；
- 明确记录 mechanism structural pass、equal-accuracy controlled negative 与 field-driven adaptivity not qualified；
- 不作为 production selective merge candidate。

test86 新增回归断言锁定该边界。changed_files 与 selective manifest 在排除两份只读 Review 权威输入后严格 139 对 139，无缺项或多余项。

## 验证

| 验证 | 结果 |
|---|---:|
| Review V3 targeted test82–test86 | 20 passed，1.95 s |
| Task034 test73–test86 | 104 passed，2.98 s |
| documentation contract test26 | 13 passed，0.11 s |
| final test26 + test86 retest | 18 passed，0.37 s |
| scoped Ruff | clean |
| bytecode compile | exit 0 |
| PETSc ABI probe after activate-myfenics | numpy.complex128 |
| full repository pytest after activate-myfenics | 498 passed，18 skipped，247.58 s |
| deterministic JSON/CSV rebuild compare | identical |
| git diff --check | clean |

第一次全仓 pytest 未先 source .venv/bin/activate-myfenics，加载 real PETSc ABI，结果为 445 passed、18 skipped、36 failed、17 errors。该失败作为 invalid environment invocation 保留在 test_summary.md；随后激活环境、确认 numpy.complex128，并在同一工作树完整复跑通过。没有隐藏或改写首次负结果。

## 重型证据边界

本轮没有修改 Maxwell/Floquet/QEP/Hybrid 数值核心，因此按 Review V2 已接受边界没有重跑：

- p3/h3、p4/h5 Full3D/Hybrid 主矩阵；
- p3/h5 Full3D/Hybrid MPI1/8/16 与 MPI32 exploratory；
- 完整 P polarization 矩阵。

## 交付索引与停止点

- 总结：outcomes/summary.md
- 统一事实表：outcomes/all_model_results.json 与 outcomes/all_model_results.csv
- 测试：outcomes/test_summary.md
- changed files：outcomes/changed_files.md
- selective merge：outcomes/selective_merge_manifest.csv
- Review 权威：review_report_v2.md

请基于本 response 与 reviewed-content commit 2ce6befca16441fe6b1f3f338c67b1a018559695 执行 Review V3。Codex 在提交并推送本文件后停止，不自行合并 master。
