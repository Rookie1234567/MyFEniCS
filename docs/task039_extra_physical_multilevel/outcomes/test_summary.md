# Task39extra 局部测试摘要

最终交付的计数窄修提交为 `adc448814c3022fdf6d1a688da69a28238e7db9c`，正式 A2R 运行源码仍为 `54ab46cf4c8378a9b27650ca6963cadb34013a2f`。窄修只把 S6/S3 生命周期序号按实际调用计一次，并提供旧 raw 的独立只读重算；未修改方程、PC 作用或求解过程。

| 最终补充检查 | 结果 |
|---|---|
| public 登记遗漏修复 test359 | 3 passed / 0.07 s；真实两份 dat 的 plan/public dry-run/worker 路由可用，ordinary/未知 profile 仍不可用 |
| 计数独立重算及未来 ledger test360 | 3 passed / 0.07 s；跨两个周期、生命周期序号不中断、逐次计数字段保留、输入不改；缺失序号拒绝 |
| 最后相关轻量回归 test356 + test359 + test360 | 19 passed / 0.85 s；ABI preflight、compileall、diff-check 通过 |
| 正式 A2R 审计 | 5 周期 reported/explicit 对照通过；163 个原 A4 残差均 ≤1e-10；外层 160 步残差 0.18250767622880507 >1e-6，性能停止，不是 solver PASS |

最后回归使用同一 shell activation/ABI preflight 后执行 `python -m pytest -q src/test/test_356_physical_intermediate_wiring.py src/test/test_359_physical_reference_public_entry.py src/test/test_360_physical_cost_recount.py`。没有因计数或文档变更重跑已绑定 FE/正式 PDE，也未运行 full repository pytest；无 CI 通过声明。对应源码 hash、完整命令、28 份正式 raw hash 由 [运行索引](records/run_index.json) 绑定。

以下为此前实现阶段记录，保留原测试快照边界；原尺寸最终结果以上述正式性能停止记录为准。

| 验证对象 | 实际结果 | 证据与边界 |
|---|---|---|
| S6 精确对角 | 三个原 p6 单元与旧 dense oracle 相对误差约 2.2–2.6e-15；p3 serial/MPI2 约 2.3e-15；最终 callback 回归 17 passed | [既有组件记录](records/setup_diagonal_optimization.json)；曾发生的 MPI2 reference 布局测试错误及修复日志保留 |
| A2R focused_v1 | 15 passed；覆盖 tiny p4、旧 A2 FE、接线及 real p3 h50 oracle | 此前实现快照，不冒称最终源码重新运行 |
| A2R focused_v2 | 17 passed；reference/原 profile 接线、ledger、释放、负路径 | 此前实现快照 |
| 最终 focused_v3 | 38 passed：test358、test352、test355 | 同 RHS repeat 相对差 0.0 ≤1e-12；增广/native action 1.8225937969296386e-15；原 A4 残差每次 ≤1e-10；错误 action 拒绝 |
| 最终组件资源 | RSS peak 640000000 B，swap 0，清场通过 | watchdog 原始 elapsed 61.57664551300695 s；pytest 原始 67.21 s，分别保留 |
| 静态检查 | compileall、git diff --check 通过 | 未运行 full repository pytest；不声称 CI 通过 |

A2R 代码提交为 `920cf08eedf99610e5eee90ec1fe8ce317e14591`。测试运行时为基于 `2bed3d4248a465a9cf2224c575fc8b64357fd020` 的 development worktree；经逐文件核验，最终 14 文件内容集合 hash 为 `2f61cf5c65a18dfcb71e700ac3a21ca1280e76d2516687627ccd7f05a44b5177`，与代码提交内容一致。较早回归没有因无关文档变更重跑。

全部 Python 测试先在同一 WSL shell 中 `source scripts/activate_myfenics_wsl.sh`，ABI preflight 确认 marker=1、链接的仓库 venv、PETSc complex128/int32、Linux OpenMPI、同 Linux ABI 库、线程数 1。实际命令：

```bash
python -m benchmarks.subreaper_watchdog --directory benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/focused_v3 --wall-seconds 180 -- python -m pytest -q -s src/test/test_358_physical_p4_reference.py src/test/test_352_task039_extra_physical_multilevel.py src/test/test_355_bounded_p1_factor.py
```

180 秒仅为该组件测试预算，正式 workflow/solve 仍为 7200/3600 秒。完整命令、源码 hash 和 9 份 raw 测试文件 hash 见 [implementation_manifest](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_manifest.json) 与 [实现报告](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_report.md)。这些小型测试当时不构成原尺寸 A2R 或主候选资格；后续正式结果见本文件开头及总账。
