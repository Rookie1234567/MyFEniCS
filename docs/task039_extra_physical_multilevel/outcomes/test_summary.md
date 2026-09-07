# Task39extra 局部测试摘要

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

180 秒仅为该组件测试预算，正式 workflow/solve 仍为 7200/3600 秒。完整命令、源码 hash 和 9 份 raw 测试文件 hash 见 [implementation_manifest](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_manifest.json) 与 [实现报告](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_report.md)。小型测试通过不代表原尺寸 A2R 已运行或主候选已资格化。
