# Task39 Review V1 E0：扩展继承审计

本页是 Review V1 扩展的启动审计。它只确认已提交的 Task39 证据、Review 范围和
后续解锁条件，不改写 T3–T10 的科学结论，也不把任何未运行阶段写成通过。

## 1. 启动身份

| 项目 | E0 实际值 |
| --- | --- |
| branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` |
| pull 前 HEAD | `758ce5e734f4404fac502117c695b7148ba8e4f0` |
| pull 后 HEAD / upstream | `2207a9c410631129fd61c8a272bcb4bd5c8c4b62` / 同值 |
| pull | `git fetch origin --prune` 后 `git pull --ff-only`；仅快进，新增 Review V1 |
| ahead / behind | `0 / 0` |
| worktree | clean |
| base master | `438caf150439343ee7c4c58ad7e02a3da812a23c`，未修改 |
| E0 允许的首个提交 | `docs(task039): audit approved post-closeout extension` |

SSH 使用已加载 agent 的 BatchMode 探针通过。本阶段没有启动 pytest、MPI 或 PDE。

## 2. 首轮证据继承

首轮结果和负结果保持原样；以下记录仍是各阶段的唯一 compact authority 入口。

| 阶段 | 继承事实 | authority / raw 入口 |
| --- | --- | --- |
| T3 | p6/h10 Full3D direct MPI8 fixed-grid authority；residual `3.512831334578471e-11`，604 keys，formal swap used=0 | [T3 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t3_full3d_direct_mpi8_v1.json)；raw `results/task039_5nm_full3d_direct/task039_5nm_full3d_direct_p6h10_mpi8__full3d_direct__mpi8__Mna/20260812T204543.545080Z`；run manifest SHA `3aa7e4c1061fbbe58dbbe71dee2fde06dabef3a8106dd1783e8a9742ec7fce26`；diffraction SHA `6d2ed0911a07b0fde09892e553fb7ed5c15aeec5d0b04653967e2f81ac7185a0`；selected NPZ SHA `1602c66efcb69c070dbc2d71ba6e0166d269a10068fe017139c597c1d5edf681`；worker stdout SHA `8ccdf1980ec60b3b8e8691e0d77a45aae0cfdfe547715ba7f9bd9f3feb70aec9` |
| T4 | Full3D iterative p6/h10 在 4000 步 `DIVERGED_MAX_IT(-3)`；reported residual `0.1552648200050503`，正式数值负结果 | [T4 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t4_full3d_iterative_mpi8_negative_v1.json)；raw `results/task039_5nm_full3d_iterative/task039_5nm_full3d_iterative_p6h10_mpi8__full3d_iterative__mpi8__Mna/20260812T221136.855751Z`；M3a audit 独立存在但未嵌入 numerical summary，保留为 evidence gap |
| T5 M480 | own residual/traction/projection/closure 通过；Full3D H diagnostic 在 z=10/60 失败；不等于 Full3D validation | [T5 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json)；raw `results/task039_5nm_hybrid_direct_m480/task039_5nm_hybrid_direct_p6h10_mpi8__hybrid_direct__mpi8__M480/20260813T033657.601004Z`；direct payload SHA `b771548f2491cddca15af568339ffef465a13d4423e0a799fc46af98c98b7f75`；checker SHA `4ac919e01c7e965719807d0a54e6e8a06117f2d0a2d8ca711944ae6f31b68fda` |
| T5 M960 | solution 前 canonical raw-trace Gate 失败：raw `1.678e-11`、representation `1.008e-14`、limit `1e-12`；无合法 R/T/A 或 field observable | 同一 [T5 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json)；raw `results/task039_5nm_hybrid_direct_m960/task039_5nm_hybrid_direct_p6h10_m960_mpi8__hybrid_direct__mpi8__M960/20260813T042015.744006Z`；worker stdout SHA `84884ee4b07421bf0abf06588b8918417cd7eecbca26529b7008425977b59aba` |

T3 的 p6/h10 是 algorithmic stress anchor，不是 5 nm 网格收敛结论。T4、T5 的
negative 与 diagnostic 边界不覆盖、不改写；T6–T8、h7.5/h6/h5 和完整 0.7 nm PDE
仍分别保持 `not_run`、`blocked` 或组件级审计边界。

## 3. 资源继承口径

任务物理预算为 256 GiB；已建立的机器容量证据为 selected WSL
`MemTotal=228.0657501220703 GiB`，即 `0.90 * selected=205.2591751098633 GiB`。
只读环境证据显示 `SwapTotal=32 GiB`、当前使用量为 0 GiB；这不是“没有 swap
容量”，而是当前未使用。任何正式 job 一旦使用 swap 都必须失败并停止。RSS/PSS/USS
是独立的同时进程树峰值，不能与 solver-rank 历史峰值相加。

首轮 T3–T5 record 的历史配置为 warning=180 GiB、configured hard=220 GiB，故其
effective hard 为 `min(220, 205.2591751098633)=205.2591751098633 GiB`。Review V1
对 E2–E4 规定了新的扩展预算：warning=170 GiB、configured hard=195 GiB，因此
extension effective hard 为
`min(195, 0.90 * selected)=min(195, 205.2591751098633)=195 GiB`；h5 另需满足
预测 process-tree peak `<=180 GiB`。这些只属于后续启动策略，不改变首轮记录，也
不是本阶段的重型运行授权。

## 4. Review V1 E0–E10 计划

| 阶段 | 目标与主要 Gate | 重型运行解锁 | 提交边界 |
| --- | --- | --- | --- |
| E0 | 继承审计、source/record/resource 身份和 exact plan；docs-only | 无 | 本页单一 docs-only commit |
| E1 | 非侵入式 telemetry/comparator、focused tests；不改方程和 ordinary defaults | 只有实现与测试 Gate 通过后才可进入后续阶段 | code/test 独立小提交 |
| E2 | Full3D direct p6/h7.5；mesh、NNZ、factor、内存、swap preflight 后 own Gate | h7.5 预测不超过 effective hard stop 且无 swap | 运行和证据分阶段提交 |
| E3 | Full3D direct p6/h6；继承 h7.5 的安全与资源证据 | E2 完成并通过资源预检 | 独立阶段提交 |
| E4 | 条件 Full3D direct p6/h5；需已有 h10/h7.5/h6、预测峰值不超过180 GiB并留15%余量 | 所有条件同时满足；否则 `not_run_by_resource_policy` | 独立阶段提交 |
| E5 | 用 h10/h7.5/h6/h5 实测比较选 reference；只按 Review Gate 分类 | E2–E4 结果齐全或明确停止 | grid decision docs/record |
| E6 | M480 H native/curlE/Full3D 三路诊断；优先离线 | 只有现有 artifact 不足才允许一次冻结 M480 diagnostic rerun | diagnostic 独立提交 |
| E7 | M960 backward-error、Gram condition、逐列和重复装配审计 | 只有全部稳定性 Gate 通过才允许一次冻结 M960 direct rerun；否则禁止 | audit 与条件性 rerun 分离 |
| E8 | M480 Hybrid iterative MPI8 solver-only；冻结 M480、604 keys、restart90、max_it6000、五项 residual=5e-9 | 先有合法 M480 direct reference、实现/资源 Gate 通过 | solver diagnostic 提交 |
| E9 | 仅在 E8 MPI8 numerical Gate 通过后运行同候选 MPI1 minimum-memory | E8 通过，且不改变 M、PC、Krylov、mode set | MPI1 证据独立提交 |
| E10 | M120/M240/M480/M960 可得阶段的生命周期对象/容量归因；不自动做架构重构 | 无自动 modal matrix-free、owner-only Schur 或 QEP 替换 | closeout 与 `response_v2` 后停审 |

所有阶段均继承 heavy job 串行、无新 branch/worktree、无 master 写入、无 force push。
任何共享 material/mode-key/field/ABI defect 都先停止重型运行、窄修并复审；失败证据
不能被改写成 pass。

## 5. E0 Gate 与未完成边界

- Review V1 已从远端快进拉取，当前 source、upstream、clean 和 ahead/behind 已核对。
- T3/T4/T5 compact records、raw repo-relative 路径和关键 SHA 已核对；ignored raw
  不会被提交。
- 本轮只新增本页；没有 Python、input、config、schema、test 或 solver 变化。
- repository full pytest 按首轮 T10 记录为用户取消的 `cancelled / not_run`，不是 pass。
- ordinary defaults、master 和其他分支未改变；neural/learned 路线、0.7 nm 完整 PDE
  和新的 preconditioner 均未启动。

E0 结论：`E0_INHERITED_AUDIT_COMPLETE`。该状态只解锁 Review V1 的 E1 审阅，不解锁
任何 E2–E10 重型运行。
