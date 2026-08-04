# Task037 测试与静态检查汇总

## 当前源码 canonical 收口

canonical fix `2631a4c47258c9def919530787e409774b8ce029` 后的最终 targeted evidence：serial test226 `3 passed / 2 skipped`；MPI2 test226 每 rank `4 passed / 1 skipped`；test227+228 `5 passed / 3 skipped`；Ruff、py_compile/compileall、git diff --check 通过。Direct v2、M3a MPI4 full、canonical comparator 和一次性 physical-norm reconstruction 均绑定各自 artifact/manifest SHA；offline norm 不是 PDE solve。Full repository pytest 未在最终 source 上重跑，记录为 `not_run_by_user_efficiency_policy / not_verified`，因此不写成 full-suite PASS。

## 历史 response_v0 测试快照（当前增量见上节）

所有项目测试均在 `scripts/activate_myfenics_wsl.sh` 资格化环境中执行：项目
`.venv`、PETSc `complex128/int32`，petsc4py、slepc4py、DOLFINx 和 mpi4py
来自同一 Linux ABI 栈。下表合并同一 Gate 的代表性结果；重复 rerun 不另列为新能力。

| 阶段 | 代表性命令/范围 | 结果 |
|---|---|---|
| F2a partition | `test_220_task037_trace_aware_physical_slabs.py` serial/MPI2/MPI4 | 通过；coverage、support multiset、hash identity |
| F3a basis | `test_221_task037_active_trace_basis.py` serial/MPI2/MPI4；test220 serial | 通过；真实 H(curl) interpolation 与 75D basis |
| F3b-1 core | `test_222_task037_assembled_fgmres_core.py` serial/MPI2 | 通过；assembled exact algebra 与 20-step core |
| F3b-2 watchdog | test217、test223、test68、test181 focused | 通过；26 passed |
| F5a action | test224 serial；MPI2/MPI4 owner/scatter；test115 相关节点 | 通过；assembled/local-Schur action `<=1e-11` |
| F5b lifecycle | p2/h50、p6/h50 serial smoke | controlled negative；75D basis 在 release/KSP 前 singular |

F5b formal p6/h10/MPI8 的数值结果见 [summary](summary.md)；本表不把 smoke
或组件测试提升为 formal full qualification。

### 唯一 full repository pytest

Task037 只运行过一次无筛选 full suite，source `237e9abd2043fd5ec424de4d9f224cfd771bf8d9`：

| passed | skipped | failed | errors | pytest / shell wall | exit |
|---:|---:|---:|---:|---:|---:|
| 828 | 42 | 2 | 0 | `1297.70 s / 1298.58 s` | 1 |

它未 timeout；完整日志在 ignored artifact
`benchmarks/artifacts/cases/100_static_condensed_full3d_iterative/final_tests_237e9abd/full_pytest.log`。
两个失败及后续收口如下：

1. `test_26_documentation_contract.py` 原先未登记 tracked Case100；同一观察集还
   看到了 checkout-local ignored Case098，其目录仅含两个 `__pycache__/*.pyc`
   （`72697` bytes）。提交 `3abe2786` 增加 Case100 的
   `PARTIAL_WITH_CONTROLLED_NEGATIVES` 合同；Case098 只在 targeted test 期间临时
   移出并原样恢复，未删除、未放宽任意目录合同。最终等价 targeted result 为
   `14 passed`。
2. `test_53_task033_high_order_hybrid_components.py` 的旧期待为 `2*degree+4=10`，
   但 V8 lifted target strategy 的真实 coefficient degree 为 `degree`，linear
   geometry 的 interface quadrature degree 为 `3*degree+4=13`。`3abe2786` 只同步
   测试合同，没有修改 production quadrature；targeted result 为 `3 passed`
   （`242.23 s`）。

因此准确表述是 `full suite completed_with_2_failures; known assertions closed by
targeted tests; no second full suite`，不能把原始 full-suite exit 1 改写成 PASS。

### 其他验证边界

- touched Python 的 Ruff lint 通过；Case100 strict JSON duplicate-key parse 和
  `git diff --check` 通过。
- 现有 Task37 执行材料中未找到可引用的 aggregate compileall pass 记录；文档收口未
  重跑，因此该项为 `unverified/not evidenced`，不是数值失败。
- 两个既有大型测试文件的全文件 Ruff format-check 保留 baseline format debt，未
  做整文件重排；Task §9.1 对本阶段只要求 lint touched Python，format-check 适用于
  new/small extracted modules。
- 文档结项提交后不再运行 pytest、Ruff、compileall、PDE 或 MPI。各数值证据仍绑定
  各自记录中的 source SHA、command、MPI 和 artifact hashes。
- 未运行项包括 MPI4 formal full、第二次 full suite、F4/F5c/F6、Task037b、Hybrid
  和 hp/0.7 nm 扩展；这些不是测试失败后的隐式授权。
