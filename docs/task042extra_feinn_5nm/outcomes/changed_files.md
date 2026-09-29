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
