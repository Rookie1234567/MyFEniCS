# Task40extra 当前测试摘要：Review V10文档收口与版本分列测试（V9及更早记录保留）

## Review V10 证据、工程修复与文档收口

| 检查集合 / source | 命令或证据 | 结果与边界 |
|---|---|---|
| 原始 A 定向测试，Git source `45a388fa12afb69a29afaa0240a72018a0069967` | V10 原 A 测试记录 | 44 passed，按该次原A源回执；保留为旧源测试结果 |
| A checker相关测试，Git source `b2c5ae94ebec1394e4b659dd6b8aef26866b5b38` | Task40 qualified activation下既有记录 | 30 passed in 2.96 s；不与其他source的fixtures合并 |
| A V2输出目录守卫fixtures，冻结source `a4ac46a8d796f9c101a0b4b9364bf01e9101dd50` | V2 runner fixture既有记录 | 3 passed in 0.52 s；与前两组分开，不求和宣称统一覆盖 |
| V10 ABI preflight（最终文档收口） | V10 §4.2 qualified activation；解析`runtime_prefix`下解释器与petsc4py/slepc4py/dolfinx/mpi4py | PASS；Linux；PETSc complex128/int32；全部模块来自同一runtime_prefix。较早一次探针错误地要求root/.venv，断言失败只反映路径条件不适用于Task40，不是ABI环境失败；随后按真实runtime_prefix resolve重跑通过 |
| V10文档合同测试 | `python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py` | 24 passed，134 subtests passed in 0.17 s；文档/registry/retrospective contracts only，无PDE |
| V10数值 / 全仓范围 | 本次收口 | 本次未追加FE/PDE或数值测试；此前V10的A边界与B0运行及负结果按Response/records登记。全仓pytest、MPI4、Ruff、CI未运行 |

上述测试属于不同源与fixture集合，不能相加为一个“通过总数”。定向测试不证明official R/T/A或目标尺度能力。
| 检查 | 命令 / 记录 | 结果与边界 |
|---|---|---|
| W1解析矩helper定向测试（V9 source `50f29a285d25b20ba0c4d34e6d6b9e2d8ce46de8`） | Task40资格化本机activation后运行`python -m pytest -q src/test/test_task40_w1_moment_reference.py` | `6 passed in 4.29 s`；只测独立高精度矩helper；不含FE/PDE。此为已有回执，V9文档收尾未重跑 |
| 收尾文档/记录检查 | 最终修改后`git diff --check`、JSON解析、原样快照SHA核对 | PASS：git diff --check、JSON解析、hash-bound证据、原样快照cmp及旧run-index字段保持核对；不是pytest或科学Gate |
| V2 raw持久性/ZIP/NPY头部目录 | qualified ABI下只读fsync、重开SHA、10成员CRC和shape/dtype目录 | PASS；无数组值、积分、残差、FE或PDE读取/计算 |
| helper静态检查 | qualified ABI preflight；对已提交helper与test执行compileall；检测ruff可用性 | ABI preflight及compileall PASS；Ruff `NOT_AVAILABLE`，未安装；未重跑6项数值测试 |
| 全仓pytest / MPI4 / Ruff / CI / 新PDE | 本轮无此类执行 | `NOT_RUN`；不声称CI通过 |

V9所列负实轴球Bessel分支、分析脚本维度修正、依赖安装和命令修复不混称为测试通过；耗时不完整的阶段保留`UNKNOWN`。clock-only RSS/swap不能作为测试或归因阶段资源结果。

---

## Review V6 closeout（V9之前历史测试记录）

| 检查 | 命令 / 证据 | 结果与边界 |
|---|---|---|
| postprocess preflight regression | source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_v5_postprocess_preflight.py | 7 passed；检查授权后历史失败接续和 preflight 行为；无 PDE |
| fresh independent checker | python -m benchmarks.check_task40_review_v5_gx784 对已保存 comparison 输出 fresh JSON（qualified activation 下） | tested_x_agreement_pass、无 failure reasons；fresh JSON 与保存 checker 记录相同；仅读保存场 |
| qualification and compilation | Task40 qualified activation ABI preflight；targeted compileall | PASS；PETSc complex128/int32、Linux ABI、MPI1；没有运行 MPI4 |
| final documentation and Task40 contracts | source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py src/test/test_task40_v5_postprocess_preflight.py | 31 passed；含 response、summary、registry、run-index 文档合同及 preflight regression，无 PDE |
| whitespace / JSON identity | git diff --check；compact record、run index 和 artifact hashes | PASS; 14 raw artifact hashes and compact-record/run-index binding verified |
| broader checks | full repository pytest / MPI4 / Ruff / CI / new PDE / target-scale / dot | not_run；本 closeout 不涵盖 |

V6 PDE source=2374d0d556aed7a415202757daa2b94b76ad399b，postprocess source=fea2b6c01b34940a6393bd47a4f545d6d53d61b4。旧尝试的 positive/negative evidence 和历史测试范围仍保留在下文；本节不把旧测试改归到本轮 source。

---

# Task40extra 测试与文档检查摘要

## Review V5 Gx784 安全预检与定向回归

实现 source 969b4086320b844d44fb0b67092ffe5af2d760b1，qualified WSL activation：

| 检查 | 结果 |
|---|---|
| 后处理预检、V5/V4 review fixtures、worker time policy 与 clock | 35 passed in 0.33 s；命令：source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_v5_postprocess_preflight.py src/test/test_task40_review_v5_gx784.py src/test/test_task40_review_v4_volume_runner.py src/test/test_task40extra_v5_worker_time_policy.py src/test/test_physical_schur_v14_runtime_clock.py |
| 被本次改动触及的 V20 lifecycle | 12 passed in 13.71 s；source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task39extra_v20_y1_lifecycle.py |
| 环境 / 静态检查 | qualified ABI preflight：complex128、int32、MPI1；compileall 与 git diff --check 通过 |
| 文档合同 | source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_183_development_model_registry_markdown.py src/test/test_29_task_retrospective_contract.py：13 passed in 0.02 s |
| 未运行 | full repository pytest、MPI4、Ruff、CI；没有 formal service、worker 或 PDE 重跑 |

两个测试命令分别报告，不将不同 fixture 集合合并为一次完整测试。通过单元测试只验证代码路径，不证明 Gx784 数值通过。

---

## Review V4 交叉网格收口验证

| 检查 | 命令 / source | 结果 | 证据边界 |
|---|---|---|---|
| V4 定向测试 | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_review_v4_volume_runner.py src/test/test_task40_review_v4_directional_cross.py src/test/test_task40_p3_mode_staircase.py`；source `55feda2c6f5c0e0b9ec4b57a341d209ec8b566d2` | `8 passed in 0.68 s` | runner/watchdog 启动与隔离、父进程不导入 FE、方向/交互量和模式分母 helper；不运行 PDE |
| Python 编译、命令入口 | 三个新增/相关模块 `py_compile`；volume/modes runner `--help` | PASS | 静态语法和入口参数检查；不代表完整仓库编译 |
| whitespace | `git diff --check` | PASS | V4 文档及 metadata 最终版检查 |
| Ruff | qualified environment 中 `python -m ruff` | `not_run`：环境没有安装 ruff 模块 | 未安装或临时增加依赖 |
| 项目文档合同测试 | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_183_development_model_registry_markdown.py src/test/test_29_task_retrospective_contract.py`；source `55feda2c6f5c0e0b9ec4b57a341d209ec8b566d2` | `13 passed in 0.02 s` | registry 表格结构与 retrospective 文档约定；不涉及 PDE |
| full repository pytest / MPI4 / CI | 未运行 | `not_run` | 本轮只运行 V4 focused 与两个文档合同测试；不声称 CI 通过 |
| V4 保存场后处理 | 4-corner directional volume worker 和 all-340-mode/power pass | 已完成，非 pytest | volume 用一个受 subreaper 监督的离线 worker，退出码 0、后代清空；mode 分析读取保存记录。无新 PDE/网格/factorization |

首个 volume launcher 曾在任何 run 包载入前失败：parent 用文件路径启动导致 repository root 未进入 `sys.path`，`benchmarks` 模块解析失败。该事件准确归类为**工程 launcher startup failure**，不是场恢复、积分、PDE、残差或物理失败；无 saved run 被读取，也没有恢复或积分发生。随后的 launcher 修复改为 `python -m benchmarks...`，focused runner test 覆盖这一模块启动路径。此失败保留，不由后续成功覆盖。

## 当前文档检查

| 检查 | 状态 |
|---|---|
| V4 compact JSON 与 artifact SHA | `PASS`；run index、接口包及两个原始分析 artifact 均可解析；接口 SHA、两项 artifact SHA 和 F3 source correction 均与索引一致 |
| 本轮 Markdown 合同 | `PASS`；response/summary/test-summary、Task40 README、development_progress、development_model_registry 六份文档新增区共 23 个表格列数一致，新增相对链接目标均存在，`git diff --check` 通过；无独立多行公式 |
| GitHub rendered view | `NOT_VERIFIED`；待推送后检查当前分支上的 summary/response 页面 | 缓存或页面不可读时如实保留未验证状态 |
| full repository pytest / MPI4 / Ruff / CI | `not_run`；不外推 |


## 测试结果

| 范围 | 命令/输入 | 结果 | 证据边界 |
|---|---|---|---|
| N2 tiny p2 diagnostic | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_n2_tiny_task40_stage4_static_condensed_diagnostic` | `1 passed`；solver `8.608 s` | source commit/base `036dec55beb0fdb1f3cae7693fddfc0225921eb9` 加未提交实现 diff `7cd587b76d90670bc396dc3e82f4641fbd1cce3b1f65d2f4c71058bb6dd977e1`；60-cell p2 diagnostic，不是 G0/G1 official |
| Task40 focused regression suite（历史阶段；并非 profile smoke） | 5 个目标文件，精确命令见下方 | `41 passed, 1 deselected in 9.20 s` | 含 Task40 几何/launcher 与 Task038 staging/watchdog 回归，也含 V19 真实 FFCx/MPC 小 FE action、V18 小 FE 的真实 LU factor/solve；`-k` 排除 N2 测试。额外执行的 V19/V18 真实 FE/factor 测试超出 N2 单一 tiny fixture 范围；总耗时为 9.20 s，各 fixture 次数与单独耗时均 `unknown`。这不是 G0/G1 正式 PDE。该运行早于 `1ee85bc`，精确 HEAD 与未提交 diff 身份未保留，记为 `unknown` |
| ledger identity 与 G0/G1 capacity fixtures | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger src/test/test_task40_nonseparable_geometry.py::test_task40_capacity_context_binds_frozen_axes_and_live_class_metadata` | `3 passed, 10 deselected in 0.76 s` | source `1ee85bc2133b783da419d31dbe429643eb2c1191`；一个 ledger fixture、G0/G1 两个 capacity fixture；不包含 PDE |
| final mesh metadata fixture | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_task40_same_mesh_levels_preserve_air_void_audit_metadata` | `1 passed in 3.89 s` | source `59bad0d977f0e23555098d923a95afbf2e9f5bf4`；真实 G0 mesh/FE/MPC fixture，不装全局矩阵或因子 |
| compileall / diff whitespace | compileall for modified solver modules；`git diff --check` | `PASS` | 在最终 source 修复后完成；不等于 full test suite |
| full repository pytest / MPI4 / Ruff / CI | 未运行 | `not_run` | 本行仅说明初始N0–N6阶段与R5收口；Review V2已有的targeted MPI2资格见下方，不得由此行误读为未做任何MPI2测试 |

历史 focused regression suite 的原始命令（该运行早于 `1ee85bc2133b783da419d31dbe429643eb2c1191`）：

```bash
source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py src/test/test_337_task038_full3d_jit_staging.py src/test/test_task39extra_v30_monitor_policy.py src/test/test_task39extra_v19_p6_cell_condensed_action.py src/test/test_task39extra_v18_cell_condensed_core.py -k 'not n2_tiny_task40_stage4_static_condensed_diagnostic'
```

该 41 项 suite 的精确 HEAD 与未提交实现 diff SHA 未保留，因此 source identity 为 `unknown`；不能把它归到 `1ee85bc`。N2 diagnostic 则有独立运行记录：`source_head=036dec55beb0fdb1f3cae7693fddfc0225921eb9`，另绑定未提交实现 diff SHA256 `7cd587b76d90670bc396dc3e82f4641fbd1cce3b1f65d2f4c71058bb6dd977e1`。

两个 systemd service-log SHA 保留在原始 Task40 run records；日志未作为独立文件出现在本工作树，因此本轮只校验可见 artifact，不声称重新计算了这两项。 Task39 V31 首个 instrumentation failure 的原始注释仍保存在父任务记录 [`projection_layout_v31_resource_reaudit.json`](../../task039_extra_physical_multilevel/outcomes/records/projection_layout_v31_resource_reaudit.json)；该事件属于父任务。Task40 仅记录自身两次 G0 worker implementation failures，不覆盖或重分类父任务记录。

## 当前文档检查

| 检查 | 结果 | 范围 |
|---|---|---|
| 证据 JSON parse 与 identity/hash 对照 | `PASS`；10 个 JSON 可解析，G1 hash 与 geometry plan 一致；input、ledger 及当前可见的 9 个 raw run files 逐项复核 | `outcomes/records/*.json` 与 ignored raw runs |
| whitespace/diff check | `PASS`；`git diff --check` 与新增文本行尾空白检查通过 | 本轮文档与 metadata |
| Markdown fenced math / 表格 / 相对链接 | `PASS`；8 个相关 Markdown 的表格列数、围栏、相对链接检查通过；修复一条原模型登记表中指向 ignored artifact 的旧链接 | 新建/修改 Task40 Markdown 与项目索引 |
| GitHub rendered view | `NOT_VERIFIED` | 推送后尝试打开 summary、response 与 material identity 页面；页面读取返回 `Cache miss`，因此未确认 GitHub 渲染结果 |

## 2026-09-30 主控续算入口验证

资格化 complex128 / PETSc 3.19.6 环境下，`python -m pytest -q src/test/test_task40_bug_continuation.py src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger`：**4 passed in 1.10 s**。仅 mock/账本测试，无 FE/FFCx/因子：验证第三次预约保留两次历史和累计成本、授权只能消费一次、G1不获额外额度，以及授权不匹配/数值失败保持拒绝。未重跑已合格的字段修复网格 fixture。

## G0 JIT 缓存路径修复

最终组合执行 `python -m pytest -q src/test/test_task40_qualified_jit_cache.py src/test/test_task40_bug_continuation.py src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger`：**5 passed in 1.15 s**；compileall、diff 检查通过。此前隔壁单独路径 fixture 为 **1 passed in 0.19 s**，成本保留。测试只核对显式父 artifact 绑定、旧 V31 配置与账本，不建立 FE 矩阵/因子。父缓存路径是本笔记本显式配置，不声称跨机器自动可用；新 FFCx 表单仍按签名编译。


## 2026-09-30 attempt4 N6 evidence closeout

本轮只整理已落盘 attempt4 数值 Gate 和主控离线数组复核；没有改数值源码、重跑 FE/KSP/PDE，也没有新增测试。raw KSP status/reason 未持久化，callback因果为source-derived。

Task40 仓库根执行以下轻量检查，输出为：PASS: 3 JSON parse; 9 raw SHA match; identity normalization consistent.

命令1：
python3 -c 'import json,hashlib; from pathlib import Path; d=Path("docs/task40extra_0p7nm_engineering/outcomes/records"); [json.loads((d/n).read_text()) for n in ("g0_attempt4_identity_gate_stop.json","run_index.json","phase_I_results.json")]; r=Path("results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_g0_iterative_v1__full3d_iterative__mpi1__Mna/20260929T230709.246850Z"); c=json.loads((d/"g0_attempt4_identity_gate_stop.json").read_text()); a={"worker_summary_sha256":"task40extra_nonseparable_0p7nm_p6q4_summary.json","run_manifest_sha256":"run_manifest.json","run_summary_sha256":"run_summary.json","watchdog_summary_sha256":"watchdog/summary.json","release_gate_packet_sha256":"release_gate_failure/v20_release_gate.json","monitor_residuals_sha256":"monitor_residuals.jsonl","iterations_sha256":"iterations.jsonl","x2_retained_final_npz_sha256":"x2_retained_final.npz","x2_terminal_residual_npz_sha256":"x2_residual_0008_0002.npz"}; assert all(hashlib.sha256((r/v).read_bytes()).hexdigest()==c["artifacts"][k] for k,v in a.items()); assert abs(c["gate_metrics"]["native_identity_difference_norm"]/c["gate_metrics"]["native_identity_operation_scale"]-c["gate_metrics"]["native_identity_relative_recomputed"])<1e-25; print("PASS: 3 JSON parse; 9 raw SHA match; identity normalization consistent.")'

命令2：
git diff --cached --check

结果：两条命令均通过。该检查不是pytest、MPI、Ruff或CI。此前targeted tests的source SHA和范围仍按历史记录保存，不归到attempt4。




分组来源补充（不混入上表43项合计）：

- exact-geometry / R3 修复 fixture：15 项通过，提交 source 33b773d161b5e5dc218a29b122cdb4044ca01800；见 identity-recovery root-cause record。
- 非零 RHS 实算 action fixture：3 项通过，命令与范围见 identity_policy_decision_v1.json 的 current_abi_fixtures[0]，源测试为 test_task39extra_v19_p6_cell_condensed_action.py::test_real_ffcx_mpc_action_only_matches_augmented_schur_and_nonzero_rhs。
- local recovery/native residual oracle 与 non-Hermitian port fixture：2 项通过、9 项 deselected，见同一 record 的 current_abi_fixtures[1]；它与上一组的3项分开记录。

## R4 review_v1 runs and R5 documentation closeout

- R4 official execution used source SHA 393e5c0dddb933848945ab2e18edb73cf69cc224 for the direct reference; the G0/G1 source SHA is b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672. Targeted code checks recorded before the runs passed 34 cases across test_372, test_373 and test_task40_direct_reference_identity, plus 9 cases in test_374_reference_incident_quadrature.py, total 43. The 15 exact-geometry/R3 repair tests and separate nonzero-RHS groups (3 and 2 cases) are distinct earlier evidence and are not counted in these 43. This is not full-repository pytest, MPI2/4, Ruff or CI.
- R5 changed compact records and documentation only; no PDE, factorization, solver or new test suite was run for closeout. Final JSON parse, source/artifact identity checks and git diff checks are recorded after the last doc edit.
- direct reference independent saved-array audit: reference_full_residual.npz SHA256 0e8c5b1fc8a8718d56e7b0ab0bc9b7407d941022addbb9b72ada5314c64da630; recomputed norm(b-Ax)/norm(b)=5.055376131651821e-11 and maxabs(r-(b-Ax))=0.
- direct execution route deviation: user-service wrapper was not used; the observed cgroup was /init.scope. The independent process-tree watchdog completed with exit 0 and cleared descendants. No rerun was made.


## Review V2累计测试与本轮文档检查

| 范围 | 已有命令/输入 | 结果 | 身份与边界 |
|---|---|---|---|
| P4 same-M mode helper | `src/test/test_task40_p3_mode_staircase.py`定向fixture | `4 passed` | P3/P4保存场比较helper；P4不启动PDE。测试源代码由`benchmarks/postprocess_task40_p3_mode_staircase.py`所绑定的V2 commit `3f36014253525f5fc7e0e2ee56348bc3628e9024`识别 |
| P6 bounded diagnostic fixtures | `src/test/test_task40_p6_local_growth_v2.py` | `2 passed` | P6 source `5f9efdbae1c668ffa4426731156ec4afe9325eb2`；serial targeted fixture，不创建完整高M全局factor |
| Review V2 earlier serial/MPI2 qualification | V2实现阶段已运行的serial与MPI2 targeted tests及相关qualification | 已运行；本compact test summary未保留逐条命令、完整case count、耗时和每次source SHA，均记`unknown` | 不把未知写成未运行；不将MPI2结果扩展为MPI4或完整solver qualification。既有结果按原测试回执边界使用 |
| source checks during V2 implementation | targeted `compileall`及和数值实现相关的focused regression，见各代码阶段记录 | 通过的范围见既有代码阶段回执 | 不把实现阶段测试回填成本文档收尾新测试；不等于全库pytest |
| 本轮P7/文档收尾 | 10个compact JSON parse及身份/hash断言；234个Markdown表格列数、347个本地链接、7个编辑Markdown的围栏/尾空白；`git diff --check` | `PASS` | 只核对compact evidence与文档合同；没有新PDE、operator、factor、KSP或full test suite |
| full repository pytest / MPI4 / Ruff / CI | 未运行 | `not_run` | 不声称full pytest、MPI4、Ruff或CI通过 |

Review V2的正式F1/F2/F3/F5/E1/E2计算发生在此前campaign阶段，见run_index与各自raw run summaries；“本轮文档收尾没有新PDE”不等于整个Review V2没有正式运行。P1和P4都是保存场offline后处理。

## Review V7 文档与索引定向检查（2026-10-04）

| 检查 | 命令/范围 | 结果 | 边界 |
|---|---|---|---|
| 资格化本地 WSL preflight | `source scripts/activate_myfenics_wsl.sh` 后核验 lexical `sys.executable` 位于仓库 `.venv`、`sys.prefix` 与 `.venv` 一致、PETSc complex128/int32、PETSc/SLEPc/DOLFINx complex Linux ABI、Basix/mpi4py Linux 路径、Open MPI 4.1.6、MPI1 | PASS | 仅本地文档测试环境，不是原生工作站 W0 收据 |
| 文档合同与历史/模型注册合同 | `python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py` | 24 passed；pytest 报告 0.06 s | 没有 FE、MPI 多进程、full-repository pytest 或 PDE |
| 两次 preflight 脚本误报 | attempt 1 把 venv 符号链接目标误要求在 venv 内；attempt 2 把 SLEPc 安装目录误要求与 PETSc 同根。两次均在 pytest 启动前停止 | 保留为 agent assertion errors | 都不是项目/ABI 失败；单次耗时无 monotonic 收据，记 unknown，不记零或收费 |
| compact JSON / index / diff | 新 V7 link 和增量账 JSON parse；run index stage/status pointers、原四角哈希和 Gx784/F5 输入身份断言；`git diff --check` | PASS | 只验证本地文档/evidence；没有触及 ignored raw、工作站 FE 或历史 V6 ledger |

这组结果对应本轮新增文档与索引，不替代原生机器 ABI/resource Gate，也不改变 W0/W1/W2 状态。

原生 W0 handoff packet 已从 `/tmp/task40_native_handoff_4c98a859.b64` 解码并在本地逐项复核：packet 为 113,898 B、SHA256 `4c98a859a265bb942cc2eb3e37cead21f0fafd2251574bbe742f1cef61cf4d3d`；19 个 UTF-8 成员的字节长度和 SHA256 在写入前及 ignored artifact 回读后均通过。整包及全部成员保存在 `benchmarks/artifacts/task40extra_0p7nm_engineering/native_w0_handoff_4c98a859/`；13 份轻量 raw ABI/audit/import/resource/host 身份收据按原字节复制进 tracked receipt 目录，另外记录持久副本 stdout（明确标注为控制端回读 stdout，不是 packet member）。路径、全部成员 SHA、tracked receipt SHA 与复核边界见[原生 W0 handoff index](records/native_w0_handoff_4c98a859/handoff_index.json)。长安装日志、包清单与辅助脚本仍只留在 ignored artifacts，由 artifact manifest hash-index。

收据中的状态和边界如下：三项浅导入预检通过；真实命令 `python -c 'import src.solvers.dtn_port_3d'` 在 source `5be1210aa79f25c13a7677cc291a4a766a548650` 上于 `2026-10-04T03:24:37Z–03:24:38Z` 因 `ModuleNotFoundError: No module named 'pyvista'` 以 exit 1 停止，调用链为 `dtn_port_3d → common_3d_utils → solve_vector_maxwell → postprocess → pyvista`。FE start event `NOT_REACHED`，W0 component、dry admission、worker、checker、official physics、raw archive 均 `NOT_RUN`；这属于 FE 前入口 blocker，不是数值测试或 PDE 失败。ABI receipt SHA256 `4ef26bf3d4ea0b3c16170b030694e7de7a303108e5fd78b3309835d0c4aa5102`、closure JSON SHA256 `64f65b92b8379c432cf87c6f6d97b62108236e67512eade1699b22cdde9c20b7`、stderr trace SHA256 `343939c7bec310f03c05134763e4aef504d9997abb40f06956bdb08dcf2af01a` 已在 tracked receipt 中原字节保存。

03:35:29Z 宿主快照 `MemAvailable=2,089,370,224 KiB`（约 `2.1395e12 B`）；Task42 进程组在 03:34:11Z 前后已不见，Metrology 仍活动。本轮资源/空闲窗口为 `HELD/NOT_ATTEMPTED`，不是容量失败：宿主 SwapUsed 基线及末次观测均 21,600 KiB，但基线时间缺失；相等读数只得到 derived 0 KiB 差值，不能归因给 Task40；pswpin/out 的初始计数未采集，增量为 `null`。整体准备起点、monotonic/boottime 与 W0 预算消耗都未知；packet 中的 34.489 s 和 771 s 是 UTC-derived 局部区间，不是安装耗时、FE 耗时或预算扣款。

保留的辅助诊断也按实际类型分类：两次 readback 误报分别是 lexical venv Python 与 resolved symlink 被错误要求相同路径，以及假设 `dolfinx_mpc.__version__` 存在但模块未提供该属性；分别改用 prefix 同源核对和 conda-meta/dist-info 版本证据后通过，均未重建环境。只读 `micromamba list` 与 `micromamba --version` 查询曾以 `tl::bad_expected_access` 失败；包事实由 conda-meta 读取，版本查询未生成 core dump（`ulimit -c=0`），canonical repo 状态复查未变。这些是读取/断言诊断，不等于 ABI 或 package 环境失败。

原生 packet 文档收尾后，资格化 activation 轻量 preflight 再次通过；相同的三文件文档/模型注册/回顾合同 suite **24 passed in 0.05 s**。最小交叉 hash/index 检查通过：run index 的 response、增量账、四角父接口、V4/V6 历史引用和 handoff index 指针一致；packet 为 113,898 B、SHA256 匹配，19 个 artifact 成员及 14 个 tracked receipts 的长度/哈希匹配；W0/W1/W2 与 V6 settled debit 状态一致；`git diff --check` 通过。首个检查脚本自身曾把仓库相对路径再交给 `Path.relative_to(root)`，在文件校验开始前因 `ValueError` 退出；没有改写文件或触及证据。修正为根目录路径拼接后，上述检查通过。该脚本处理错误不是项目、packet 或数值失败。

## Review V7 W0 实际运行与离线收口（2026-10-04）

| 检查 | 命令/来源 | 结果 | 范围与边界 |
|---|---|---|---|
| Native 16-module import closure | earlier native startup preflight at source `74bfcddf52cc97b518e71154dc47d59654fd4a8e`; formal W0 run source `4b89d7f922bda3859048d20714557ac0cf07ffc6` used its own fresh ABI receipt; metadata-only identity fix `5f74e15fae6e01e4361325db162806a7319ba3f4` did not rerun the 16-module closure | 16-module closure passed at the earlier preflight; the 4b89 W0 startup ABI receipt passed independently; 5f74 explicitly reran the saved-receipt public validator in list and tuple forms | Import closure is historical startup evidence, not a new 5f74 test or FE/solver pass |
| Runner scope / degree gate | Read-only inspection of `benchmarks/run_fresh_c1_p6_component.py` at SHA `7290d392a9ac4c00b1bc1a3f070da947b62414865b29faac8f07814315a3ef36` | degree tuple `(6,)`; asserts `spaces == {6}` and `floquets == {6}` | Confirms p6-only setup; filename/config `q4` label was not run as four q branches; no p4 or q factors |
| W0 frozen budget manifest | `benchmarks/fresh_c1_p6_w0_budget.json`, SHA256 `533930676db07f7a145e0e6b71eacd198288bea92717bf7a8ba91fe9d16a9b81` | raw-member disk cap `8,589,934,592 B`; derived worst-case `6,900,030,936 B`; margin `1,689,903,656 B`; separate process-tree cap `3,221,225,472 B` | Derived admission contract; not measured output/RSS/capacity; legacy checker assertion still expects 512 MiB and was not changed |
| Native focused component suite | `python -m pytest -q -p no:cacheprovider src/test/test_fresh_c1_p6_component_contract.py src/test/test_fresh_c1_p6_native_tensor_checker.py` | `40 passed, 10 skipped in 0.39 s` | 10 项因 archive fixtures unavailable 而 skip；未对原始 tensor/CSR 数据执行 checker，且该 raw 未生成 |
| Actual W0 worker | native run `w0_20261004T0638Z_4b89d7f` | `WORKER_FAILED`, exit 1，tuple/list mode identity guard；196.762108860 s，RSS peak 1,408,434,176 B，task swap 0 | fresh setup 与 same-live component receipt 已生成；full p6 worker/raw export 前退出，不是 time/resource stop |
| Saved-receipt public validator: list | 捕获 native stdout `/tmp/task40_w0_fix5f74_list_tuple_stdout.json` | PASS；1.411307457 s 内部 / 1.58 s outer，46,796 KiB max RSS | JSON list 身份；FE/JIT/mesh/form/matrix/factor/PDE 均 NOT_RUN |
| Saved-receipt public validator: tuple | 同一 stdout 与同一 receipt SHA | PASS；1.404511847 s 内部 / 1.58 s outer，47,108 KiB max RSS | Python tuple 身份；离线验证，不是 worker 重放或 scientific raw checker |
| Captured validator stdout identity | root readback of native public validator stdout `/tmp/task40_w0_fix5f74_list_tuple_stdout.json` | `1,951 B`; SHA256 `b563cbce296c0740b707aa48394bc3fd15cb8cdbc5a89dbb6f473db5e01a8c89` | validator SHA `aec3ae90634ce8ef0f18d3490097e331f863dc56cc4d978c0e2244a22af4673d`; qualification SHA `fb572d7f1ab6f0e5bc2b94cc14bbb3d9a3bd9d1c6b637aa59a7926121c5ddfdb` |
| 本地文档合同 suite | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py` | `24 passed in 0.05 s` | 使用本地旧 PETSc 3.19/Open MPI 4.1.6 activation，仅测文档合同；不代表 native W0 ABI 或 PDE |
| Snapshot, packet 与 compact hash | qualification activation 下的单次 Python hash/index 合同检查 | PASS | 5f74 ledger snapshot byte-equal 到 commit blob；small packet archive 与 3 JSON members 的长度/SHA 匹配；native 36-file copy/readback 由本地 manifest 逐项报告，但原 member bytes/tensor arrays 不在主线 |
| `git diff --check` | 仓库根目录 | PASS after final content edits | 纯文本空白检查；不提供 Markdown GitHub rendered-view 证明 |

Native component-only receipt 的重算 Gate 数值、worker 失败位置、4 小时 policy cutoff 与 10:07:14Z launch deadline 的区别、scientific raw 不存在的原因见 [Response V7](../response_v7.md) 与 [actual-run record](records/native_w0_actual_run_v1.json)。



早期 native worker attempts 的 measured elapsed 子计时和 6bbc shell blocker 的 unknown cost 见 [Response V7](../response_v7.md) 与 [incremental ledger](records/review_v7_incremental_workflow_ledger.json)。三次 worker 仅小计 worker elapsed，不折算完整 W0 准备或收费。

本轮离线证据身份进一步确认：原 35-member 包（47,078 B，SHA256 `d5f934e09e034b1349c2860948e1dc91ec24c9670ba6dd5939a01bc8e6379f62`）是运行日志/ABI/资源/测试收据，不是 tensor/场数据；native 侧 36 份支持文件共 5,757,491 B，逐文件 SHA 和 copy/fsync/readback 通过。worker 在 scientific raw export 前失败，原始 p6 tensor/field 数组根本不存在；另一次支持收据跨窗传输被 auto-review 拒绝后，没有尝试替代通道。JIT 64 files / 1,220,807,231 B 留在 native 原路径，未复制。
