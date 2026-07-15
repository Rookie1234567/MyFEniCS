# RESPONSE V1 FOLLOW-UP：Task032 Review V1 + Addendum 回应

## 0. 回应身份

```text
branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
review = review_report_v1.md + review_report_v1_addendum.md
historical execution summary = response_v1.md (preserved, not overwritten)
this response = response_v1_review_followup.md
implementation classification = hybrid_direct_engineering_success at 13.5 nm
h2 = not_run_by_gate
current direct at 0.7 nm = not_resource_feasible
ordinary default = unchanged
formal h5/h3 rerun = not required / not run
h2 or 0.7 nm PDE run = not required / not run
```

## 1. 总体处理决定

| Review 项 | 处理 | 结论 | 证据 |
|---|---|---|---|
| 13.5 nm h5/h3 物理与数值实现 | accepted | 保持 `hybrid_direct_engineering_success` | `outcomes/summary.md` |
| current direct 0.7 nm claim | accepted correction | 明确为 not resource feasible | scalability assessment |
| Hybrid 长期架构 | accepted | complex 3D FEM ends + generic 2D modal middle retained | roadmap/capability |
| h2 not-run | accepted | 两种预测均失败，不冒险运行 | h2 table |
| parameter 30/30 | accepted qualification | interface/API smoke only | summary/capability |
| table-first long-term rule | accepted | protected files、standard、tests 同步 | principles/tests |
| selective merge only | accepted | 新增 manifest，不建议整体 merge branch | manifest |
| Review V1 sections 6/7 pure-modal/y-first | superseded by addendum | 不作为主线或 service Gate | assessment/roadmap |

## 2. P0-A：table-first summary

已重写 [`outcomes/summary.md`](outcomes/summary.md)，不是在旧长叙述末尾追加表。当前包含：

| 独立表组 | 内容 |
|---|---|
| 状态 / scope / notation | classification、h2、parameter scope、M 定义、ordinary default |
| Phase 0–10 | planned/run/pass/fail/not_run 和证据 |
| QEP/modes | beta error、residual、biorthogonality、tracking |
| algebra scale | full3D/Hybrid rows、NNZ、cells、DoF、projection/factor payload |
| numerics | R/T/A、field、absorption、residual |
| truncation | M20/40/80/120/160 |
| memory/time | augmented/fast/minimal、baseline、分母、单位 |
| h2 / smoke / negative | predicted/not_run、smoke boundary、根因/停止 |
| 0.7 / records / merge / next | analytical projection、size inventory、manifest、Task033–036 |

所有数值表区分 `measured` / `derived` / `predicted` / `not_run`，并给出单位、baseline/分母和证据。

### 阶段编号的一处合理保留

Review V1 第 2.1 节把 Phase 7 写为 field reconstruction、Phase 8 写为 Modal-Schur；但不可改写的
canonical `task.md` 明确定义：

```text
Phase 6 = Hybrid augmented direct
Phase 7 = Modal-Schur direct
Phase 8 = modal truncation funnel
Phase 9 = full3D vs Hybrid + parameter smoke
Phase 10 = memory/time
```

因此 summary 的 Phase 表使用任务书编号，同时把 field reconstruction 归入 Phase 6/9 交付。
这不是拒绝 Review 的技术结论，而是避免两个文档产生永久编号冲突。

## 3. P0-B：长期表格规则与测试

已同步：

| 文件 | 修改 |
|---|---|
| `docs/repository_work_principles.md` | 新增强制 table-first 条款，并顺延后续编号 |
| root `README.md` protected section | 同步完整条款 |
| `docs/README.md` protected section | 同步完整条款 |
| `docs/task_retrospective_standard.md` | 第4节从“推荐”升级为 Task032 起的强制模板 |
| `src/test/test_24_repository_work_principles.py` | 检查三个 protected files 同步 |
| `src/test/test_26_documentation_contract.py` | 检查 >=8 tables、必需章节/身份/关键值、JSON/CSV artifacts |

规则不追溯强制重写 Task000–Task031，符合 Review 给定边界。

## 4. P0-C / D：0.7 nm 报告与确定性投影

新增：

| artifact | 身份 | 关键边界 |
|---|---|---|
| `outcomes/task032_0p7nm_scalability_assessment.md` | engineering assessment | measured/derived/predicted 分开；含 1/2 TiB budget 和 hard Gates |
| `benchmarks/run_task032_scalability_projection.py` | deterministic standard-library script | 输入 lambda/periods/local thickness/mesh/safety/MPI |
| `outcomes/task032_0p7nm_projection.json` | `analytical_resource_projection` | `is_pde_run=false`、`is_solver_pass=false`、无 status=pass |
| `src/test/test_41_task032_scalability_projection.py` | non-PDE contract | deterministic、formula scale、invalid input fail-closed |

默认 0.7 nm 情景给出 generic propagation lower bound 16,028.5 modes/direction；机械 3.7x 只作
risk illustration，M=59,306 不是截断预测。uniform h0.1/20 nm local FE estimate 为 923,346,000
rows，future external aux count 未投影；current explicit layout 的最大单对象 proxy 为 1,595.60 TiB，
多对象累计体积为 1,611.30 TiB（非同时峰值），且尚未计入 factors、mesh 和 Krylov。这只证明
current layout 不能机械放大，不是未来 scalable implementation 的 RSS 预测。

## 5. P0-E：selective merge manifest

新增 [`outcomes/selective_merge_manifest.csv`](outcomes/selective_merge_manifest.csv)。决定分为：

| 类型 | 决定 |
|---|---|
| QEP/Floquet/modes/propagation/trace/local mesh/reconstruction | validated or experimental infrastructure，选择性合并 |
| augmented / Modal-Schur direct | current-scale reference，带 scalability warning 合并 |
| last-rank modal owner / replicated dense arrays / all-mode RHS / local LU | 可复现 reference only，禁止提升 0.7 production |
| Case080/tests/docs/light records | 合并证据合同 |
| fields/meshes/eigenvectors/matrices/factors/timelines/caches/logs/dirty records | excluded / ignored |

ordinary default 全部保持不变。

## 6. P0-F：compact-record inventory

新增 [`outcomes/compact_record_size_inventory.csv`](outcomes/compact_record_size_inventory.csv)。当前 21 个
Case080 records 加 1 个 analytical projection 共 22 个 tracked Task032 JSON、1,406,455 bytes；最大
`hybrid_h5_m160.json` 为 284,619 bytes（约 0.27 MiB）。

本轮没有压缩 M120/M160 records，理由是：

1. 精确逐衍射级复振幅是 M120→M160 funnel 的必要 denominator；
2. 单文件和总量仍属于轻量证据；
3. Git 中没有 full field、full eigenvector、matrix、factor、raw timeline；
4. 删除数组会降低 checker 和独立复核能力，却没有实质仓库收益。

若未来加入完整数组或文件超过轻量阈值，再只保留摘要、Gate、hash 和 ignored artifact pointer。

## 7. P0-G：项目文档与 API 边界同步

| 文件 | 已同步内容 |
|---|---|
| `README.md` | Task032 status、h2、parameter smoke、0.7 boundary |
| `docs/README.md` | Task032 Phase 0–10、两份 response 身份、review/addendum/assessment links |
| Task032 `README.md` | 不覆盖旧 response；新增 review follow-up 和 artifacts 入口 |
| `docs/development_progress.md` | Review 结论、规模、1 TiB identity、Task033–036 |
| `docs/capability_matrix.md` | current-scale experimental API、not-scalable objects、smoke-only |
| `docs/project_service_requirements_and_forward_model_roadmap.md` | complex ends + generic modal + corrected Task033–036 |
| benchmark indexes / Case080 | 302/302、Phase 0–10、analytical projection identity |
| implementation docstrings | QEP/coupling/augmented/Schur current-scale warning |

## 8. P0-H / I：Addendum 优先级

明确接受 addendum 对 Review V1 第 6、7 节和第 12 节 pure-modal-first 的 supersede：

| 原 Review 建议 | Follow-up 决定 | 理由 |
|---|---|---|
| y-invariant sector 作为下一主线 | 不采用为 mandatory/service Gate | 未来中间区只保证 generic `epsilon(x,y)` |
| pure-modal 先行并替代 local 3D | 不采用为主线 | 未来 z=0/120 附近可能曲边、圆角、任意3D材料 |
| generic 2D QEP | 保留 | 是未来真实服务能力 |
| pure-modal/y-sector diagnostic | 允许但非 P0 | 可作当前规则 Case080 独立 reference |

这不是主观拒绝，而是后发布的 mandatory addendum 明确覆盖了原建议。

## 9. P0-J / K：M 与 full3D/Hybrid 规模

统一定义：`M = retained internal cross-section modes per propagation direction`；M160 = 160 forward
+ 160 backward = 320 internal amplitudes。外部 80 个 Fourier-DtN auxiliary 不属于 M。

| mesh | full3D rows / NNZ | Hybrid M160 rows / NNZ | rows reduction | NNZ reduction |
|---|---:|---:|---:|---:|
| h5 | 44,778 / 4,896,156 | 14,052 / 2,000,624 | 68.62% | 59.14% |
| h3 | 198,518 / 21,317,860 | 68,796 / 8,594,673 | 65.35% | 59.68% |

summary 还列出 cells、QEP full/reduced DoF、trace DoF、projection NNZ、factor NNZ、Schur bytes、
321 RHS 和 right/left eigenvector bytes；非 record 直接字段标为 `derived`。

## 10. P0-L / M：1 TiB 与 complex ends

| Gate | 决定 |
|---|---|
| local FE rows `<=2e8` | preferred / relatively promising |
| `2e8–3.5e8` | candidate zone |
| `3.5e8–5e8` | high risk |
| `>5e8` | likely infeasible in 1 TiB |
| whole solver `<=2 kB/FE DoF` | preferred |
| `<=3 kB/FE DoF` | hard exploratory ceiling |

future bottom/top exact complex 3D Nédélec FEM 明确保留。最终 1 TiB 判断是
`credible conditional opportunity, not demonstrated`；2 TiB 也不能弥补错误算法复杂度。

## 11. P0-N：修正后 Task033–Task036

| Task | 主线 | 首要 Gate |
|---|---|---|
| 033 | local h/p + interface-budget optimization | 13.5 nm 同误差 local DoF >=3x，preferred 5x |
| 034 | scalable generic 2D modal core | distributed/streamed/adaptive；no replicated M²/all-mode RHS |
| 035 | final Hybrid iterative | matrix-free local FEM + low-memory H(curl) + true residual |
| 036 | wavelength continuation | 13.5→5→2→1→0.7，逐步材料/网格/M/资源 Gate |

Task033 不在本 response 分支内提前实现。

## 12. 明确暂不执行的工作及理由

| 工作 | 决定 | 可信理由 |
|---|---|---|
| 重跑 formal h5/h3 physics | not_run | Review 明确不要求；物理实现已接受，重跑不关闭任何 P0 |
| h2 direct | not_run | 两套中心/上界预测均失败；运行会违反 fail-closed Gate |
| 0.7 nm PDE | not_run | current layout analytical lower bound 已远超预算；无安全/科学意义 |
| same-sampler full3D RSS A/B | deferred P1 | addendum 明确不阻塞；当前 full3D historical 与 Hybrid simultaneous 不能混算 |
| pure-modal/y-sector solver | not implemented | addendum 撤回 mandatory 主线；属于可选 benchmark，不是本 review closeout |
| compact current JSON arrays | retained | 最大0.27 MiB、总1.34 MiB；是截断证据且没有 heavy payload |
| 改写 `task.md` 或 review | not modified | 仓库治理明确禁止；编号差异在 response 解释 |

## 13. 验证

| 类别 | 命令 / 范围 | 结果 |
|---|---|---|
| local governance/docs/projection | tests 24/26/41 | 22/22 passed |
| Ruff / compileall | 8 changed Python files | all checks passed / passed |
| Task032 focused serial | tests 31–41 / qualified Docker | 49/49 passed |
| selected MPI2 | tests 33/34/35/38/39/40 | each rank 28 passed, 2 skipped |
| selected MPI4 | same | each rank 28 passed, 2 skipped |
| final projection Docker recheck | test41 | 4/4 passed |
| Case080 | checker `--no-write` | 302/302 passed |
| JSON/CSV/Markdown | documentation contract + parsers | passed |
| repository | `git diff --check` | passed；only expected LF→CRLF warnings |

测试细节同步在 [`outcomes/test_summary.md`](outcomes/test_summary.md)。formal h5/h3 physics、h2 和
0.7 nm PDE 均按 Review 的“不要求工作”保持未运行。

## 14. 最终请求

本 follow-up 请求独立复审以下统一身份：

```text
Task032 at 13.5 nm = hybrid_direct_engineering_success
h2 = not_run_by_gate
current direct implementation at 0.7 nm = not resource feasible
Hybrid architecture = promising / retained
future complex 3D ends = required
generic epsilon(x,y) modal middle = required
parameter 1–10° S/P = interface/API smoke only
ordinary default = unchanged
selective merge = provisionally recommended after this response passes review
```
