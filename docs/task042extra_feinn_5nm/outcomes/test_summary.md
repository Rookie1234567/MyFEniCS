# Targeted tests 与文档复核

本页保留首次失败与修复后结果。完整suite与CI没有运行；检查限定于新增full-FE数学/事务/Riesz及本任务文档，不重跑旧heavy。

| 检查/尝试 | 监督状态/exit | wall / s | 同时树RSS / MiB | own swap / B | 子树清场 |
| --- | --- | --- | --- | --- | --- |
| algebra_and_lint_20260929T104946920206Z | WORKER_FAILED/1 | 1.998625 | 59.152 | 0 | True |
| c3_reference_static_20260929T180338558573Z | COMPLETED/0 | 1.519846 | 38.395 | 0 | True |
| cholmod_dependency_20260929T102823494524Z | WORKER_FAILED/1 | 7.300278 | 146.961 | 0 | True |
| e5_analytic_target_capacity_20260929T182053680758Z | COMPLETED/0 | 1.515314 | 41.074 | 0 | True |
| e5_compact_evidence_20260929T182110831272Z | COMPLETED/0 | 1.519980 | 40.312 | 0 | True |
| e5_independent_raw_check_20260929T182126238712Z | COMPLETED/0 | 2.024982 | 60.969 | 0 | True |
| fe_abi_20260929T102600471321Z | COMPLETED/0 | 3.311251 | 175.434 | 0 | True |
| implementation_checks_20260929T105219053119Z | COMPLETED/0 | 1.974255 | 59.156 | 0 | True |
| ml_abi_20260929T102713264800Z | COMPLETED/0 | 6.851944 | 265.969 | 0 | True |
| optimizer_transaction_20260929T111245150321Z | COMPLETED/0 | 5.494056 | 269.293 | 0 | True |
| pure_algebra_20260929T104743142102Z | WORKER_FAILED/1 | 2.664926 | 83.258 | 0 | True |
| sparse_gram_binding_20260929T104918118890Z | COMPLETED/0 | 2.657193 | 93.379 | 0 | True |
| task_local_ruff_20260929T105023806802Z | COMPLETED/0 | 9.171619 | 114.961 | 0 | True |

相关测试文件为 `src/test/test_feinn_full_algebra.py`（4项）、`test_feinn_riesz_ml.py`（2项）、`test_feinn_transaction_ml.py`（2项）和 `test_optical_material_table.py`（7项）。分别覆盖完整保留内部量的A/Aᴴ/原增广关系、复SPD解及symbolic拒绝numeric、优化外层异常恢复与accepted状态、材料离线hash/插值/边界；不会把纯测试称为物理5nm通过。

首次纯代数检查的fixture键名 `dofs` 与实现 `cell_dofs` 不一致，在C1提交前最小修复，原失败日志保留。scikit-sparse打包缺少Cython，改用系统已有CHOLMOD薄C ABI；没有在旧环境安装。后续source、Ruff/compile、输入解析和相关pytest以实际light记录为准，费用全部计入[研究成本](records/resource_costs_v1.json)。

E1真实制造解/384cell完整矩/原action/Gram、3方向FD与batch1/8、q15/30属于正式one-run接口资格，另见[interface](records/interface_gates_v1.json)。它们不是本页纯测试的替代，也不是候选原方程/场/功率通过。

独立stdlib checker从compact原数值重算方程、字段/复杂幅值、功率、能量和资源；大artifact hashes可在本机加 `--verify-raw`：

```bash
python benchmarks/check_feinn_pilot.py --evidence docs/task042extra_feinn_5nm/outcomes/records --output /tmp/task42extra_gate_recheck.json --verify-raw
```

结果见[Gate](records/gate_decisions_v1.json)，而非仅复述status字符串。FE体积分差由原独立积分保留absolute/denominator；complex E/H与ordered通道从compact复值重新算范数；功率差与闭合由原R/T/A_volume重新计算。

本任务Markdown逐页检查closed fences、math fence、表格列数、UTF-8 replacement及本地相对链接；summary按回顾标准16节且至少8张表。总账只运行相关3项Markdown检查，不宣称历史模型/COMSOL数值重验。解析、实际GitHub rendered view、raw blob一致性、浏览器DOM/截图和明确blocked原因分别见[render记录](records/render_check_v1.json)，本地解析不替代浏览器视图。

实际 GitHub Firefox 首轮检查 11 页（任务书、8页本任务文档、两份总账新节），每张表的浏览器 DOM 列数一致。它发现发布任务书 §5.4 的 `\operatorname{Re}` 和本任务方法映射原式的 `\operatorname{solve}` 均被 GitHub 数学渲染器拒绝。任务书由发布方维护，记录为 `RENDERED_VIEW_FAIL_TASK_MATH`；方法映射已改成 `\mathrm{solve}`，其复核随最终 render 记录提交。截图和完整 DOM 留在本任务 ignored 目录，compact 文件保留 hash，不称该失败检查为通过。

实际数值source是E1 C1、E2 C2及E3/E4各run index；之后证据提交HEAD不会冒充运行源码。运行中的HEAD未移动，提交前与推送后clean核验。
