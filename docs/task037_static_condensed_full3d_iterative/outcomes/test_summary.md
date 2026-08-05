# Task037 测试与静态检查汇总

## Review V3 p4-core部分凝聚当前测试章节

本阶段只验证 p4-core 部分凝聚组件与真实 public DtN 接线；“静态凝聚”在这里指单元内先消去内部行，“retained p4 core”指在完整 p6 代数中保留 108 个 exact-sequence p4 core 行。所有结果绑定 qualified activation、PETSc complex128/int32 和同一 Linux ABI。

| 范围 | source | 结果 |
|---|---|---|
| R7a local | `ed871cbae51396e30ad5a3fd6bf32dc7601a4020` | PASS；误差 `1e-14–1e-15` |
| R7b1 global | `b93b72bac9095273c838ff653ca3bbf93567123c` | PASS；最大约 `2.58e-15` |
| R7b2a compiled-form | `0c882e7a6da38b6a66625e002fe64fabe0a70674` | test244 serial/MPI2、test243 serial PASS |
| R7b2b1 public DtN | `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a` | test245 `1 failed, 1 passed`；controlled negative |

R7b2a：serial test244 `1 passed / 132.33 s / MaxRSS 548212 kB / action 3.913e-16`；MPI2 test244 `passed / 129.36 s / MaxRSS 536320 kB / action 4.371e-16`；serial test243 `1 passed / 34.50 s`。ledger 为 partial Schur `9331200`、eliminated factor `3745584`、basis `15070464`、maps `37304`、numbering `864` bytes。

R7b2b1：命令为（在已执行 `source scripts/activate_myfenics_wsl.sh` 的同一 qualified shell 中）`source scripts/activate_myfenics_wsl.sh && /usr/bin/time -v python -m pytest -q -s src/test/test_245_task037_retained_dtn_adapter.py`；exit `1`、wall `88.15 s`、MaxRSS `661088 kB`、swap `0`。visible rows=`760`、KSP reason=`2`、RHS=`11.707507837771832`、solution=`275.1048734370968`、full true residual=`4.271433780052363e-11`。hard complement Gate 的 independent norm=`2.169086505997297e-12`、complement norm=`5.000737489099658e-10`，限值 `1e-11`，在 [test245:435](../../../src/test/test_245_task037_retained_dtn_adapter.py:435) 失败，约超限 `50.00737489099658` 倍。

Candidate D 的 D0 负证据为：low `0.24599945418880295 / 0.2540230551088513 / 0.9684138870126958`，high `0.24651896436171644 / 0.26531876351572775 / 0.929142594723057`，mixed `0.24612971921817314 / 0.2715867504171219 / 0.9062655628087525`（`rho_B4 / rho_D / improvement`）；p2 factor count=`2`、factor NNZ=`4608`、p6 matrix/factor=`0/0`，rows/aggregate bytes=`not_recorded`。D 的 20/100/200、full、restart、MPI1 均 `not_run_by_D0_gate`。

R7b2b1 touched Python scope 的 compileall、Ruff check、`git diff --check` 通过；test245 hard failure 原样保留，未 xfail/skip/放宽阈值。没有运行 full repository pytest；R7b2b2、MPI2 test245、MPI8 screen、full、official R/T/A 均 `not_run_by_gate`。Candidate E 为 `not_run_by_latest_user_sequence`；Candidate F addendum 为 `not_read_pending_v3_closeout`。

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
