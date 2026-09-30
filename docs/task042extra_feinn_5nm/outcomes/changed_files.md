# 改动范围与合并边界

当前实现改动从发布提交起核对；最后的response/outcomes和总账追加另在交付commit中。实现未修改旧Task042历史、任务书或review。正式source hashes见[run index](records/run_index_v1.json)。

| 依赖组 | 文件/用途 | 审阅边界 |
| --- | --- | --- |
| production dispatch | scripts/run_case.py；src/io/feinn_pilot.py | 明确opt-in，原默认solver数学与旧Task042函数含义不改 |
| 完整数值核 | src/solvers/feinn_native.py、feinn_interpolation.py、feinn_torch.py、feinn_fem.py | 完整边/面/内部矩、原A/Aᴴ及准确端口；不是trace恢复 |
| 辅助Riesz | src/solvers/feinn_riesz.py、feinn_cholmod.c | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR，非无全局因子/可扩展PC结论 |
| 研究优化/验收 | feinn_validation.py、feinn_optimization.py、feinn_reference.py | 统一三路线预算、事务checkpoint、盲准确reference及有条件p4 |
| 可复用task编排 | src/runners/feinn_resources.py、feinn_workflow.py；scripts/activate_task42extra.sh、supervise_task42extra.py | 自有lock/env/cache/CPU-only和whole-tree guard；不改邻任务 |
| 检查工具 | benchmarks/check_feinn_pilot.py及E5容量/render辅助 | 只读或task-local轻量证据工具，不包含新PDE数学 |
| 输入/targeted tests | input/task042extra_feinn_5nm；src/test/test_feinn_*.py | 固定M5/seed/loss/G/近零阈值；只测必要合同 |
| 文档与证据 | docs/task042extra_feinn_5nm/outcomes、response_v1；progress/registry新节 | 所有正/负/未运行保留；旧历史逐字保留 |
| do-not-merge | venvs、raw矩阵/场/history/checkpoints、cache、Firefox profile | ignored，大文件不进入Git，无production资格或master merge |

从发布提交到实现HEAD的文件名单（路径用于审查，不把后续文档HEAD当数值source）：

```text
benchmarks/check_feinn_pilot.py
benchmarks/derive_task42extra_capacity.py
benchmarks/render_task42extra.py
docs/task042extra_feinn_5nm/outcomes/environment_and_isolation.md
docs/task042extra_feinn_5nm/outcomes/method_and_paper_mapping.md
docs/task042extra_feinn_5nm/outcomes/records/design_v1.json
docs/task042extra_feinn_5nm/outcomes/summary.md
input/task042extra_feinn_5nm/design_v1.json
input/task042extra_feinn_5nm/e1_fe.dat
input/task042extra_feinn_5nm/e1_grad.dat
input/task042extra_feinn_5nm/e1_smoke.dat
input/task042extra_feinn_5nm/e3_reference.dat
input/task042extra_feinn_5nm/e4_p4.dat
input/task042extra_feinn_5nm/feinn_dual.dat
input/task042extra_feinn_5nm/feinn_euc.dat
input/task042extra_feinn_5nm/free_fe_dual.dat
scripts/activate_task42extra.sh
scripts/run_case.py
scripts/supervise_task42extra.py
src/io/feinn_pilot.py
src/runners/feinn_resources.py
src/runners/feinn_workflow.py
src/solvers/feinn_cholmod.c
src/solvers/feinn_fem.py
src/solvers/feinn_interpolation.py
src/solvers/feinn_native.py
src/solvers/feinn_optimization.py
src/solvers/feinn_reference.py
src/solvers/feinn_riesz.py
src/solvers/feinn_torch.py
src/solvers/feinn_validation.py
src/test/test_feinn_full_algebra.py
src/test/test_feinn_riesz_ml.py
src/test/test_feinn_transaction_ml.py
```

最终diff还包含本任务compact records和总结、总账追加；它们不改变三条候选数学。没有全仓清理、amend、reset、force push或跨支线merge。本轮只推执行分支等待review，合并任何组仍需review。

## Review V1 后续 V2 增量与选择性合并边界

| 依赖组 | V2增量 | 数值/审阅边界 |
| --- | --- | --- |
| research-only scaling core | `src/solvers/feinn_scaling.py`、`feinn_optimization.py` | 明确opt-in `c=Dy`、`g_y=D* g_c`；原A/f/G/d_G/loss及V1默认路不改，非production资格 |
| compare-only验证 | `src/solvers/feinn_reference.py` | 已冻结候选恢复实际c，复用V1同p3准确参考；无新MUMPS分解/求解 |
| 编排/输入 | `src/io/feinn_pilot.py`、`src/runners/feinn_workflow.py`、`input/task042extra_feinn_5nm/v2_*.dat` | D0/D1/唯一候选/D3各自one-run stage/index；task自有锁/资源监督，不改其他项目 |
| 定向测试/checker | `src/test/test_feinn_scaling_ml.py`、`benchmarks/check_task42extra_v2.py`、局部Markdown检查器、`benchmarks/finalize_task42extra_render_v2.py` | 不以status字符串替代复向量/功率/原残差重算；测试9项+正式D1；渲染复核精确blob/截图hash |
| compact证据/文档 | `response_v2.md`、`outcomes/scaling_diagnostic_v2.md`、V2 records、summary/progress/registry/test/本页；`benchmarks/render_task42extra.py`加载策略 | 旧V1全文和负结果保留；准确运行source绑定在run index；加载策略只影响辅助浏览器 |
| 明示授权排版修正 | `task.md` §5.4唯一 `\operatorname{Re}`→`\mathrm{Re}` | 只改宏、数学不变；旧/新blob及GitHub渲染见Response V2 |
| do-not-merge | ignored原数组/场/history/checkpoint、浏览器profile/cache | 研究数据本机保留；新FREE路线未获solver/production资格，不允许据此合并master |

V2实现提交 `19c725efd27ae5daedba8e77d2ad98375711bb71` 绑定D0/D1/D2正式阶段；局部FE导入修复提交 `bfff1458a389b2c4a4d57112cc771bb33847c20a` 绑定完成的D3。后续证据与文档HEAD不替代这两个实际source。新一行task公式修改已由review明确授权，不推广为一般修改任务书权限。
