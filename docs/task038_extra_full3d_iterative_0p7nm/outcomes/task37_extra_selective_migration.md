# Task37-extra 选择性迁移审计

审计日期：2026-08-20。本文只定义继承边界和后续审查条件；本轮没有迁移 Task37-extra 代码、输入、factor、raw 或 compact。

## 1. 可见性与证据身份

Task038-extra 当前树不包含下列 Task37 权威路径。它们可通过只读远端 ref
`origin/codex/20260806-task37-iterative-extra-development`、SHA
`b8785c53ce12986aa5a63300038c80c7d0ad1798` 审计，但不属于当前分支的生产输入，也没有被复制：

```text
docs/task37_extra_development/response_v1.md
docs/task37_extra_development/response_v15.md
docs/task37_extra_development/review_report_v11.md
docs/task37_extra_development/outcomes/h1r3_warm_repeat_v2.md
docs/task37_extra_development/outcomes/h1r3_mpi2_partition_identity.md
docs/task37_extra_development/outcomes/h1r3_h5_scaling.md
docs/task37_extra_development/outcomes/m6_time_harmonic_pde.md
benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat_v2.json
benchmarks/cases/101_task37_extra_development/records/h1r3_mpi2_partition_identity.json
benchmarks/cases/101_task37_extra_development/records/h1r3_h5_scaling.json
benchmarks/cases/101_task37_extra_development/records/m6a_fullspace_matrix_free_dtn.json
benchmarks/cases/101_task37_extra_development/records/m6b_w5_disk_fgmres_screen.json
benchmarks/cases/101_task37_extra_development/records/m6b_w7_s1_restart_disk_fgmres_screen.json
```

只读检查还确认，旧档案包含 action-only 的正/负记录：例如 m6a compact 为
`pass`，m6b W5/W7 compact 为 `gate_failed`。这些字段只说明旧研究证据的原始分类，不能
替代当前分支重新绑定的 source、ABI、输入和物理 Gate；旧 branch 的任何 PASS 都不能替代
当前分支的 fresh qualification。

## 2. 旧分支 evidence snapshot

下表只摘要旧分支的 `measured` 或 `derived` evidence；它们不是当前 Task038-extra 分支的
fresh pass，也不构成 PDE、official field 或 R/T/A 资格。

| 旧证据 | measured / derived snapshot | 历史分类与边界 |
|---|---|---|
| H1R3 p6/h10 MPI1 action | rows `173802`；relative error `2.7326e-17`；12-repeat deterministic；retained `6,151,104 B`；process-tree peak `340,541,440 B` | action PASS；不是 PDE/RTA |
| H1R3 MPI2 identity | canonical relative L2 `5.727e-15`；peak `636,989,440 B`；global payload `6,988,752 B` | identity PASS；不是当前分支 MPI qualification |
| H1R3 p6/h5 scaling | rows `1,127,502`；retained `38,290,752 B`；peak `638,500,864 B`；p6/h1 `36.692 GB` 为 derived action-only prediction | p6/h5 action-only PASS；p6/h1 不是 PDE |
| M6A full-space matrix-free DtN | 冻结旧案例 `80` modes；MPI1/MPI2 action/recovery error `0`；retained+work 约 `16.7 MB`；peaks `388,956,160 / 693,411,840 B` | architecture/action PASS；不是 PDE/RTA |
| M6B W5 | 200-step true residual `0.1275056 > 0.08`；peak `1,607,802,880 B`；swap `0` | `NUMERIC_FAIL`；低于 2 GB 不等于 PDE 通过 |
| M6B W7 | cumulative400 residual `0.1214175 > 0.08`；late improvement `2.389%`；peak `1,611,878,400 B`；swap `0` | `NUMERIC_FAIL`；低于 2 GB 不等于 PDE 通过 |
| G2/G3 与 W8–W18 | G2 `LOR-HX = G2_FAIL`；G3 `prohibited`；W8–W18 PC/range/nested lines 保持 negative/do-not-migrate | 不迁移、不重开，不提升为 production candidate |
| Task37 time-harmonic PDE | 完整收敛的 time-harmonic PDE、official field/RTA 和最终低于 2 GB 的 PDE authority 均未完成/`not_run` | 不得从 action-only evidence 推导 PDE 资格 |

因此，低内存 action/DtN 结果也不能写成 scalable PDE candidate；它们仍须经过当前分支的
物理、离散、ownership、资源和 fresh qualification Gate。

## 3. 初始分类与当前决定

| 组件 | `task.md` 初始分类 | 当前决定 | 进入迁移前必须证明 |
|---|---|---|---|
| `hcurl_rank_one_form_action.py` | reusable candidate | 暂不迁移 | 去 task-specific 命名；当前 master focused tests；action、ownership、complex128 |
| `hcurl_rank_one_mpc_action.py` | reusable candidate | 暂不迁移 | Floquet/MPC、MPI1/MPI2、ownership 和 source identity |
| `hcurl_fullspace_dtn.py` | reusable architecture candidate | 暂不迁移 | 去固定 80-mode/identity-H 假设；动态 mode inventory、streaming 和边界合同 |
| canonical-vector utilities | reusable candidate | 暂不迁移 | 对齐 Task038 canonical schema、hash 和 provenance |
| JIT/cache/process-tree watchdog | reusable pattern | 只保留模式判断，不复制 runner | 通用 API、source/cache identity、无 task-numbered orchestration |
| `disk_backed_flexible_gmres.py` | diagnostic-only candidate | 不作为生产 PC | 只能作为有界 oracle；不得成为 0.7 nm production 基础 |
| p4→p6 owner-local transfer | deferred candidate | deferred | 仅在 p/h multilevel lane 获准后重新设计并验证 |
| `fullspace_matrix_free_hcurl.py` 旧 dense-cell 路径 | do not migrate | 明确不迁移 | 每次 dense cell tensor 的成本不满足 h/p 可扩展边界 |
| `hcurl_h2b_*`、`hcurl_m6b_*`、W8–W18 | do not migrate as PC | 明确不迁移为 PC | 旧 PC 家族的负资格化不能被旧 action-only 结果推翻 |
| 84 个 882D patch factors | do not promote | 明确不提升 | p6/h1 的内存/可扩展性与 0.7 nm 方向不合格 |
| fixed 75/390/530D range | do not promote | 明确不提升 | 固定维数不能代表增长电尺寸 |
| LOR-HX slab hierarchy | do not migrate | 明确不迁移 | 已有内存和数值负证据；不得只摘取局部成功字段 |
| `benchmarks/run_task037_extra_*.py` | do not migrate | 明确不迁移 | 巨型 task runner 不进入通用 Task038 runner |
| 历史 compact/raw/docs | archive/reference only | 只作参考 | 只可提取最小 authority summary，不能复制整套历史证据 |

## 4. 选择性迁移的硬条件

任何未来候选都必须在当前 Task038-extra 分支逐文件重建或最小改造，并同时满足：

1. 明确依赖图，不带入旧 task runner、旧输入路径、旧 fixed case 参数或隐含环境变量。
2. 用当前 input-driven schema、source/input hash、MPI/线程和 complex128 ABI 重新绑定。
3. 添加当前 master 下的 focused tests；旧分支 PASS 不能替代 fresh evidence。
4. 对 full-space、Floquet、DtN、MPC、ownership、residual、资源和 artifact identity 分别给出 Gate。
5. 不改变 ordinary default，不用降阶、固定 range、全局矩阵、静态凝聚或 0.7 nm PDE 试错来获得通过。

当前 T0 没有满足上述条件的迁移项。特别是 Task37 的 W14A–W18A action-only 研究路线、负结果和离线 span 记录仍是 research/archive evidence；它们不构成 Task038-extra 的生产 PC、Full3D solver 或 0.7 nm 资格。

## 5. T0 结论

本阶段只提交这份清单，不提交任何 Task37 Python、raw、factor、compact 或 runner。下一阶段如获批准，应先选一个最小通用 `src/` 候选并完成当前输入/ABI/ownership 的 focused audit；不能从旧分支整段复制后再补测试。
