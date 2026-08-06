# G0.1 继承基线审计

本审计记录的是本轮 G0 开始前的身份与继承边界。审计时使用仓库权威
`.git-codex`；当前工作树中的 `.venv` 是本地排除的 symlink，不属于源码或
provenance。

## Git 身份

| 项目 | 审计值 |
|---|---|
| branch | `codex/20260806-task37-iterative-extra-development` |
| HEAD | `e207f93abd3d82cd698b1da38750d3dd1243c8a9` |
| upstream | `origin/codex/20260806-task37-iterative-extra-development` |
| HEAD 与 upstream | ahead/behind `0/0` |
| 相对 `origin/master` | ahead/behind `106/0`，即 `0 behind / 106 ahead` |
| 相对原 Task037 branch `codex/20260803-task37-matrix-free-iterative-development` | ahead/behind `2/0`，即 `0 behind / 2 ahead` |
| 审计时 tracked 工作树 | clean |
| 当前审计后状态 | 只包含本轮 G0 草稿变更；未加入任何旧 artifact 或 `.venv` |

`.venv` 的 realpath 是 `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv`，通过
仓库权威 activation 使用 complex PETSc/SLEPc 栈；`.git-codex/info/exclude`
中只有本地精确条目 `.venv`，tracked `.gitignore` 未修改。

## 继承的数值身份

固定问题仍是 Task037 Case100 的 p6 Nédélec、h10、252-cell structured hexa、
S 偏振、80 个 DtN auxiliary rows。M3a 是当前唯一已有完整数值和物理 Gate 通过
的迭代基线：16 个 overlap `0.125` physical trace slabs、owner-local ILU(0)、
固定两步 smoother、75 维 Floquet/wave coarse 和 right FGMRES。历史 MPI1 full
背景值为 352 iterations、process-tree peak `4.600486755371094 GiB`、stored
factor NNZ `91,415,952`。本轮只做 MPI1 screen20，不把历史 full 数字冒充同机
新测量。

Task035c p6/h10 preflight authority 为：

```text
benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json
SHA256 = 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8
```

已通过的直接相关基础设施包括 Task037 tests 217–250 中的 static-condensed
FGMRES、action-only condensation、owner-local slab plan/smoother、factor-free
PC、canonical artifact 和 watchdog contracts。它们是可复用接口，不是本轮新
科学结论。

## 已关闭或冻结的候选边界

| 路径 | 当前结论 | 本轮处置 |
|---|---|---|
| M2c never-materialized ordinary owner-local path | controlled negative / 后续由 M3a profile 取代 | 不重跑 |
| M3a overlap `0.125` partition | 唯一历史 full numerical/physics pass；MPI8 资源超限 | 只做本机 MPI1 screen20 |
| A：p2 auxiliary diagonal pre/post | screen100 淘汰 | 不扩展 |
| B2：factor-free local GMRES(2) | screen200 淘汰；历史 i2500 受控停止 | 不重跑 i2500；无 hash-bound raw vector 则 `not_available_without_prohibitive_rerun` |
| B4：factor-free local GMRES(4) | screen200 淘汰 | 不做 candidate full |
| C：B4 + optimized Schwarz/RAS | screen200 淘汰 | 不做 sweep/retry |
| D：local p2 patch | D0 controlled negative | 保留旧负结果，不改写 |
| p4 core partial condensation | R7b2b1 complement Gate controlled negative | 不进入 G0 之外实现 |
| Candidate F F0/F0b | implementation gate 未闭合；容量科学 Gate 未运行，已有 F0b evidence 为 negative boundary | 不重跑 |
| Candidate E / V6 E0 | `MatPython.getInfo()` telemetry implementation failure | 明确不是 Candidate E scientific failure；formal E1–E5 未运行 |
| F3/F5b released-matrix lanes | 历史 residual/physical partial or controlled negative | 不在本轮提升为 no-global-factor 新结论 |

上述旧记录、旧负结果和任务书均保持原样。没有用 scalar residual、R/T/A 或
历史过程内存伪造任何 raw vector authority。

## 默认路径与永久隔离

- ordinary solver profile、默认参数、物理方程、80 modes、fine precision 和
  residual Gate 未改变。
- 本分支是研究隔离分支；本任务及其后续未获批准的研究能力永久不得直接合并
  `master`，也不创建 PR、merge、rebase、cherry-pick 或 force push。
- G0 的 snapshot 只保存 condensed active-trace dual/load residual；values 使用
  active-row global numbering，不是 physical field coefficient，
  不冒充 physical field；只有显式 opt-in 才会复制 PETSc Vec 并写出 artifact。
- 原始 snapshots、factor、timeline、field 和其他重型输出只能留在 ignored
  `benchmarks/artifacts/`；Git 只提交小型 hash-bound records 和文档。

本文件不宣称 M3a 新 screen 已通过；该判定必须绑定后续 clean code SHA、实际
命令、watchdog return code、residual trajectory 和资源 evidence。
