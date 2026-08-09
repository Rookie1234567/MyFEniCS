# Task037-extra Review Report V4：H1R.2 single-source action-only 授权

## 0. 审阅身份与范围

| 项目 | 值 |
|---|---|
| working branch | `codex/20260806-task37-iterative-extra-development` |
| reviewed source | `e90b0ba77eb2f0a1f393aefdb1d5dd3fe464aa89` |
| upstream | 同一 SHA，ahead/behind `0/0` |
| ordinary default | unchanged |
| 本轮授权 | 仅 H1R.2 single-source p6/h10 MPI1 action-only |
| 禁止 | 新分支、PR、merge、rebase、cherry-pick、force push、master/default 修改 |

本报告以 Review V3、[`response_v3.md`](response_v3.md) 和已提交的 H1R evidence 为前置依据。当前只授权设计与后续一次窄正式 action-only run；不得自行扩大为 H1R.3、MPI2、H2、PDE/KSP、DtN、field/RTA 或 LOR/shift 扫描。

## Weekly quota hard rule

若界面或执行环境显示每周使用限制为 `0`，立即暂停全部工作；不得使用点数，不得切换模型。只有用户明确告知额度恢复后，才可继续。

## 1. 已接受的历史结论与冻结边界

| 范围 | 当前决定 | 说明 |
|---|---|---|
| H1R.0 | accepted | marker/立即 flush focused contract |
| H1R.1 | `H1R.1_PASS` | 仅 MPI.COMM_SELF 单 affine hexa 单元/类诊断 |
| H1R.1 raw | accepted with historical false negative | raw 保留旧嵌入 `gate_failed`，不静默改写 |
| H1R.2 | newly authorized | 只做一次 single-source p6/h10 MPI1 action-only |
| 旧 H1.2 | `CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED` | 不是 H1R.2 的数值证据 |
| G2 | `G2_FAIL` | 不重开 |
| G3 additive LOR-HX | `prohibited` | 不进入本轮 |
| 旧 G4 sweep | `prohibited` | 不因 H1R 改变 |
| H2/H3/H4 | `locked` | H1R.2 通过也不自动解锁 |

H1R.1 的单元 RSS 观察不是 MPI1 completed-run peak evidence。当前 `MPI1_memory_target_evaluated=false` 的语义仍为 `NOT_EVALUATED`；用户提出的 MPI1 `<2 GB` 目标不能被单元 RSS 或其他历史内存数字冒充通过。

### 1.1 H1R.1 evidence binding

| 项目 | 值 |
|---|---|
| measurement source | `04030436b16050016d4b8ec37f30bf6bac56a144` |
| raw evidence | [`h1r_cell_action_microbenchmark.json`](../../benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_microbenchmark.json) |
| raw evidence SHA256 | `0caf43c1b1f8b1fe6eb502b13ca0c22f59f76b81d09d11f33e4845f196c9bc6b` |
| raw historical status | `gate_failed`，四个 `c_packed_shapes` |
| final checker | `b5796726e388d6a0be168ed19f93d4f0e8199b45` |
| requalification | [`h1r_cell_action_qualification_recheck.json`](../../benchmarks/cases/101_task37_extra_development/records/h1r_cell_action_qualification_recheck.json) |
| requalification evidence SHA256 | `13417fc293a2ad3641b36e7e3bf05f4ae5e205d8a0947b8b42ed1f8b83b1d7ca` |
| requalification result | `pass`，`problems=[]` |
| measurement modification/rerun | `measurement_fields_modified=false`，checker 修复后未重跑 measurement |

## 2. 唯一授权：H1R.2 single-source action-only

H1R.2 的作用是验证 direct candidate 能否在真实 p6/h10 distributed full mesh 上完成一次窄 action；它不是正式 PDE 求解，也不是 H1R.3 或 H2 的预备性扫描。

| 固定项 | 合同 |
|---|---|
| degree / mesh | degree 6、h=10 nm |
| source | 固定 `seed_17037`，不得由 CLI 替换 |
| MPI | MPI1，仅一次 |
| reference apply | 1 次 |
| candidate apply | 2 次，第二次用于 repeat/determinism |
| timeout | 600 s |
| process-tree RSS Gate | `<=1.25 GiB` |
| swap | 严格 `0` |
| canonical export | distributed Vec 数值 Gate 通过后才做一次；不计入 action timing；失败不 export |
| CLI 扫描入口 | 不开放 degree/source/repeat/limit 参数 |

候选 worker/watchdog 可以作为现有 `benchmarks/run_task037_extra_candidate_h.py` 的窄子命令扩展；禁止复制新重型 runner。首次实现不走 reference 超过 300 s 的离线例外；只有实际遇到该情况且 candidate 结构/数值已通过后，才可在后续审阅中讨论一次 offline reference。

## 3. 技术决策：reference 与 candidate 必须独立

### 3.1 reference authority

reference 保留现有 `MpcFormActionContext` / `dolfinx_mpc` rank-one assembly，用于一次独立 authority action。它的用途是给 candidate 提供 full-mesh distributed Vec 数值对照，不是把 reference 调用换个名字重新包装成 candidate。

### 3.2 candidate action

candidate 必须是独立的 full-mesh direct rank-one residual 路径：

1. 使用普通 DOLFINx rank-one form assemble 到 local residual；
2. 在同一 candidate 路径中执行向量化的 MPC `R^H` reduction；
3. 正确处理 slave identity rows，使输出语义与 assembled authority 一致；
4. 只在 distributed Vec 数值 Gate 通过后做一次 canonical export。

candidate 不得调用同一 `MpcFormActionContext` 作为伪装的 independent implementation。它可保留的数值对象限于：coefficient/output/constants，以及按 constraint nnz 计的扁平 MPC metadata/working arrays。禁止保留：

- per-cell dof、coordinate 或 Python cell object；
- dense cell tensor 或 dense scratch；
- global A、global constraint matrix 或 Schur；
- per-cell factor、slab factor 或其他随 cell 数增长的对象。

## 4. V4.0：小型 serial MPC fixture 与测试合同

V4.0 必须先在 p2/p3 serial MPC fixture 证明 candidate 结构，再扩展既有 runner。fixture 对同一输入同时比较：

| authority | 作用 |
|---|---|
| assembled tiny authority | 检查完整局部/小网格输出语义 |
| `MpcFormActionContext` | 检查 full-space rank-one reference 语义 |
| independent candidate | 检查 `R^H` reduction、slave identity 与 local residual |

至少使用两个不同 deterministic inputs，并对每个 input 做 repeat exact determinism。测试必须覆盖：

- assembled authority 与 reference/candidate 的数值误差 `<=1e-11`；
- finite、repeat bitwise/deterministic；
- packed shapes、packed bytes、constraint nnz 与 retained payload closure；
- candidate 没有 dense matrix、global matrix、per-cell Python object；
- slave identity rows 与 `R^H` reduction 的闭合。

禁止在 fixture 阶段加入参数扫描、B dense cache、per-cell Python 循环/对象或泛化防御框架。若 MPC reduction 在 p2/p3 fixture 不能独立于 reference 正确闭合，停止在 V4.0，不启动正式 worker。

## 5. V4.1：代码实现与提交

V4.1 只在 V4.0 通过后实施，仍沿用 `run_task037_extra_candidate_h.py` 的现有 worker/watchdog/check 入口。可以增加明确的 `h1r2-worker`、`h1r2-watchdog` 或等价窄子命令，但不得新增通用 campaign/registry/schema/fallback 层。

提交前最小验证：

| 层 | 要求 |
|---|---|
| pure/serial | p2/p3 MPC fixture、两个输入、repeat 与双 authority |
| focused | runner/checker 合同、固定 source/degree/repeat、payload closure |
| static | compileall、git diff-check、qualified ABI |
| Git | 仍为唯一 extra 分支，逐文件 stage；禁止改 ordinary default |

V4.1 通过后提交并 push，报告完整 SHA、parent、upstream、clean 状态和测试证据；不得自动进入 V4.2。

## 6. V4.2：一次正式 run 与 Gate

正式 worker/watchdog 必须固定为 seed_17037、p6/h10、MPI1、reference=1、candidate=2、600 s timeout、RSS `<=1.25 GiB`、swap `0`。worker 必须在 start/end 检查 source clean/stable，并生成可 hash-bind 的 summary；重型 raw 只进入 ignored artifact 目录。

### 6.1 Worker Gate

| Gate | 要求 |
|---|---|
| action | candidate finite、deterministic |
| numerical | relative error `<=1e-11` |
| repeat | candidate second/repeated apply `<=2 × reference apply` |
| payload | retained payload `<=0.50 GiB` |
| storage | no dense cell tensor per apply、no global A、no Schur、no factor |
| forbidden operations | KSP=0、DtN=0 |
| canonical | 只有 distributed Vec 数值 Gate 通过后才 export 一次 |

### 6.2 Watchdog Gate

| Gate | 要求 |
|---|---|
| completion | completed `<=600 s` |
| process memory | completed process-tree peak `<=1.25 GiB` |
| swap | worker process-tree swap `0` |
| source | start/end clean，SHA 稳定 |
| evidence | worker summary 存在且 hash 完整；失败时不伪造 summary |

用户 MPI1 `<2 GB` 目标不得单独冒充通过；`<=1.25 GiB` completed process-tree peak 是本阶段更严格的资格 authority。H1R.1 单元 RSS 不可用于替代该 Gate。

## 7. 失败处理与 hard stops

若 V4.0、V4.1 或 V4.2 失败，先停止正式阶段并把 raw evidence 与根因交主审。若主审继续授权，每一轮只改一个由 raw evidence 支持的根因，例如 vectorization、buffer lifetime 或 MPC reduction；主审可以继续下发下一轮窄修复。修复后先重跑受影响的 targeted test，只有 targeted test 通过且主审再次授权，才可再次运行唯一 heavy。禁止原样重跑、并行多方案或无证据扩张；不得：

- 参数扫描、重复 source、延长 timeout；
- 退回 B dense cache；
- 引入 per-cell Python 循环/对象；
- 添加 fallback/retry 矩阵或宽泛异常框架；
- 预备多个后端或把 reference 包装成 candidate；
- 启动 H1R.3、MPI2、H2/PDE/KSP/DtN/field/RTA。

以下任一情况立即 hard stop，并保留真实 raw/根因：

1. p2/p3 candidate 不能独立复现 assembled 与 `MpcFormActionContext` authority；
2. candidate relative error `>1e-11` 或 repeat 不 deterministic；
3. candidate retained payload `>0.50 GiB`、出现 dense/global/Schur/factor；
4. candidate second apply 超过 `2 × reference`；
5. watchdog 超过 600 s、peak 超过 1.25 GiB、swap 非零、source 不稳定或 summary 不完整；
6. 需要修改 ordinary default、新依赖、新分支或历史重写。

资源停止应分类为 controlled stop/qualification unavailable，不得改写成算法 FAIL；数值/结构 Gate 失败则记录实际根因，不得凭空宣称通过。

## 8. Required output 与 evidence

| 阶段 | 必需输出 |
|---|---|
| V4.0 | p2/p3 fixture test、两个输入的 authority/candidate errors、repeat、shape/bytes/payload closure |
| V4.1 | implementation commit、测试命令、qualified ABI、完整 Git SHA/upstream/clean |
| V4.2 raw | ignored run directory、worker/watchdog summary、source start/end、command、MPI/线程、reference/candidate timing、error、determinism、payload、peak、swap、canonical export 状态、各 raw SHA |
| 通过后的 compact evidence | `benchmarks/cases/101_task37_extra_development/records/` 下 hash-bound record |
| 通过后的文档 | `docs/task37_extra_development/outcomes/h1r2_single_source_action.md` 与 `docs/task37_extra_development/response_v4.md` |
| 失败证据 | 保留 raw 与窄根因说明；不删除、不改写为 pass |
| response handoff | 仅在最终 PASS、受控停止或 weekly quota 暂停交接时准确更新 `response_v4.md`；中间每个小修不新增 response 版本 |

只有 V4.2 完整通过并经下一次 review 审阅后，才可讨论 H1R.3 或 H2；本报告本身不授予这些权限。

## 9. Test pyramid 与分支禁令

执行顺序固定为：

1. V4.0 pure/serial p2/p3 MPC fixture；
2. V4.1 focused runner/checker、compileall、diff-check 和 qualified ABI；
3. V4.2 唯一一次 p6/h10 MPI1 action-only run；
4. Gate 失败时停止该次 heavy 并保存 evidence，由主审分析；若有明确修复则回到对应 targeted test/V4.1，只有通过后才再次运行唯一 heavy。Gate 通过时先生成 compact evidence，再等待审阅；这不是无条件无限期等待。

不得跳过小 fixture直接运行重型 case，不得并行启动第二个 heavy worker，不得建立新分支或 PR，不得 merge/rebase/cherry-pick/force push，不得修改 master 或 ordinary default。
