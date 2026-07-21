# Task034 Codex response v1

## 交付状态

Task034 已按任务书、固定结构补充任务书及用户批准的 reduced scope 完成，正式状态为：

```text
PASS_WITH_QUALIFICATIONS
```

资格条件不是阈值放宽：fixed-p graded-h 的三组实测均未通过 same-error physical Gate，0.7 nm 当前架构评估为不可行；这些结果均保留为正式 negative。所有规定阶段都获得可审计 decision，环境、hardening、Task033 WSL anchors、p3/h3、p4/h5、fixed geometry、MPI identity、Case093、adaptive decision、resource model v2 和 0.7 nm assessment 均已闭合。

## 身份

| 字段 | 值 |
|---|---|
| base SHA | `82a5107b5c2bfe4c466a0d00ead31d7b172e2af4` |
| branch | `codex/20260717-task34-workstation-wsl-adaptive-scalability` |
| branch HEAD | 以本 response 的最终提交/推送 SHA 为准 |
| environment | Ubuntu 24.04 WSL native；48 physical cores；228 GiB RAM；32 GiB swap |
| primary production | S polarization |
| MPI formal matrix | `[1, 8, 16]` on representative p3/h5 Full3D + Hybrid |
| MPI32 | exploratory only |
| master merge | 未执行 |

```text
task034_addendum_loaded = true
phase_order_uses_fixed_geometry_benchmark_before_adaptive = true
mpi_matrix = [1, 8, 16]
case093_planned = true
case093_completed = true
ordinary_default_changed = false
```

## 主要结论

1. WSL native ABI/MPI/MUMPS/PEP 资格化通过；正式 heavy jobs 全部要求 source clean/stable、process-tree swap=0、true residual 和 staged Gate。
2. post-merge cache、allgather、watchdog、source-clean 与 numerical-blob 风险均闭合；需要 PDE rerun 的 numerical paths 已由 WSL fresh anchors 覆盖。
3. Task033 p3/h7.5、p3/h5 的 Full3D/Hybrid 锚点复现并 same-degree closure pass。
4. p3/h3 Full3D staged reference 和 Hybrid M160 closure pass；p3/h7.5 在新 reference 下仍通过等精度判定。
5. p4/h5 Full3D staged reference 与 Hybrid M160 closure pass，并相对 p3/h5 显示明确工程精度收益。
6. p2/p3/p4 uniform 成功序列分别为 h `[5,3,2]`、`[7.5,5,3]`、`[10,7.5,5]` nm；只声明 measured sequence，不声明 continuum/grid-convergence proof。
7. p3/h5 Full3D 与 Hybrid 在 MPI1/8/16 数值一致；MPI32 exploratory 不替代 MPI16。
8. conservative/balanced/aggressive graded-h 虽分别有 raw DoF reduction 1.561x/3.172x/9.590x，但全部 physical same-error fail，因此不称 qualified compression，并按 stop condition 不扩展更重 adaptive。
9. resource model v2 的 0.7 nm peak 约 2,014,975 GiB；local direct factor 与 modal dense multi-RHS 都是独立瓶颈，256 GiB/1 TiB/2 TiB 均不可行。

## 测试与记录索引

- Task034 serial/native：99 passed。
- selected MPI2/MPI4：每 rank 16 passed。
- Task032/Task033 regression：217 passed，8 skipped。
- scoped Ruff、compileall、numerical blob checker：pass。
- full Ruff：15 个未修改历史文件中的既有问题，已在 `outcomes/test_summary.md` 明确列出。
- 总结与重型 evidence 索引：`outcomes/summary.md`。
- changed files：`outcomes/changed_files.md`。
- 逐文件合并建议：`outcomes/selective_merge_manifest.csv`。
- Case093 authority：`benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/`。
- Case092 compact research records：`benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/`。

## Review 请求

请 ChatGPT 按 `outcomes/selective_merge_manifest.csv` 做 file-level review，重点审查 numerical-blob rerun binding、Case093 canonical positives、adaptive fail-closed 分类和 resource model component scaling。Codex 到此停止，不自行合并 `master`；后续修正将在同一分支新增 `response_v2.md`，不覆盖任务书或 review 文件。
