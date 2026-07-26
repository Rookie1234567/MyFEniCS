# Task035c 文件级 selective merge manifest v1

## 1. 决策

```text
source_branch = codex/20260726-task35c-hybrid-channel-memory-closure
base = origin/master@1fb144d3ca50208c22b5f0733e140bfac8d9c47c
tracked_or_planned_files = 69
production_core = 16
research_opt_in = 0
reusable_benchmark = 19
compact_evidence = 8
project_docs = 26
do_not_merge = 0
whole_branch_blind_merge = forbidden
integration_method = file-level restore by manifest dependency order
ordinary_default_change = false
```

本 manifest 覆盖 `origin/master...Task035c` 的全部 67 个已有差异文件，以及本
manifest 自身的 Markdown/CSV 两个文件。没有 tracked `do_not_merge` 差异，
但仍采用文件级迁移，以便机器核对实际迁入集合并避免把 ignored 本机 artifact
带入 master。

逐文件权威表为
[`selective_merge_manifest_v1.csv`](selective_merge_manifest_v1.csv)。CSV 的
每行给出 `path`、变更状态、分类、依赖组、默认行为、测试、数值证据、迁移顺序
和理由。

## 2. 迁移依赖顺序

| 顺序 | 依赖组 | 文件数 | 处置 |
|---:|---|---:|---|
| 1 | G1–G3 production numerical core + core tests | 16 | 保留 explicit opt-in；先迁移以便后续 runner/tests import |
| 2 | G4–G6 reusable Case096、runner、watchdog、checker和测试 | 19 | 不成为 ordinary solver default |
| 3 | G7 compact evidence | 8 | 只迁移 tracked compact/hash；保留正负结果 |
| 4 | G8 project docs/registry/review/task handoff | 24 | 同步适用边界、PSS/USS口径和Task035d入口 |
| 5 | G9 manifest | 2 | 最后迁移并执行实际diff集合核对 |

## 3. 数值身份与 PDE 重跑

Task035c 六条正式 `p6/h10` PDE 绑定：

```text
244b62e1fb4f299a468363cf90a2dd548dc34ff6
```

integration 必须对 Review V2 列出的 numerical kernel 运行 blob checker，并
逐文件确认与该 authority source 一致。M0 新增内容仅为 compact PSS/USS
重建、用户可见 scope metadata/help、测试、文档和 manifest；没有修改数值
kernel。若 integration 冲突解决改变任何 numerical blob，则本 manifest 的
“不重跑”判定立即失效，必须按 checker 选择必要 anchor。

PSS/USS ledger 只从原始、SHA-bound MPI8 `smaps_rollup` timeline 重建；不是
RSS 推算，也不是 PDE 重跑。正式 relative-memory authority 仍为原 campaign
的 simultaneous process-tree/live-worker RSS。

## 4. 明确排除

以下内容不在 69 个迁移文件内：

- `benchmarks/artifacts/**` 下 raw timeline、stdout、field、matrix、factor、
  cache 和其他 ignored heavy artifact；
- MPI1 `1.7517 GiB` 或 MPI2 `3.1418 GiB` 作为正式内存下限的任何提升；
- nonuniform z、curved/distorted hexa、tetra/mixed static Hybrid；
- h13 adaptive Hybrid、production selective trace、condensed iterative、
  irregular geometry 和 0.7 nm 外推；
- ordinary default 修改。

失败与 controlled-negative 只以 compact evidence 和文档进入 master，不会
注册为成功 production profile。

## 5. Integration 验收

临时 integration branch 必须从上述 base 的最新可验证 `origin/master` 建立。
若远程 master 在迁移前前进，应先更新本文件中的 base 并重新核对差异集合。
文件级 restore 后必须证明：

1. 实际 changed-path 集合与 CSV 69 行完全相等；
2. `do_not_merge = 0`，ignored raw artifact 为 0；
3. numerical blob checker 没有要求重跑；
4. Review V2 M4 的 focused、MPI、Case095/096、Task032/033、full pytest、
   Ruff、compileall、JSON parse、documentation、ordinary-default 和
   `git diff --check` 全部通过；
5. integration commit 后工作树干净，才允许 fast-forward master。
