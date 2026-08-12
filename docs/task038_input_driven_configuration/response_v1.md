# Task38 正式结项答复

## 结论

Task38 在 `codex/20260812-task38-input-driven-configuration` 上完成了从 Python preset/多参数 CLI 到单一 `.dat` 输入的迁移。当前用户主流程是：

```bash
python scripts/run_case.py input/path/to/case.dat
```

一个 dat 表示一次 run；method、solver、MPI、requested M、结果目录和输出能力均来自文件。`--validate-only` 与 `--dry-run` 只做解析/计划检查，不创建结果目录、不启动 solver。6 个 research/history preset 仍保留原 replay 入口，不被普通 dat mapping 覆盖。

## 实现范围

| 层 | 已完成内容 | 边界 |
|---|---|---|
| schema / resolution | 5 identity、9 section、100 public field、strict typed validation、immutable specification | 不从 dataclass/argparse 自动生成 schema |
| provenance | raw input、resolved config、input/physical/source hash、manifest、summary | authority path/hash 不公开为用户字段 |
| adapters | Full3D direct、Hybrid direct、Hybrid iterative、ordinary 2D 与 staged 3D | 复用既有 runner/solver，不复制数值核心 |
| reporting | diffraction reporting bound 与 outgoing DtN 解耦 | 仍保留 legacy order semantics；未审组合 fail closed |
| compatibility | 11 migrated `src.main --preset` alias、6 retained replay | 无参数和旧直接 `2d/3d` facade 不再静默运行 |
| cleanup | 删除 5 个不可达旧 3D 模块，当前教程改为 dat | run_cases/run_3d_cases、Task37 authority、历史 records 保留 |

## 数值证据

| 路径 | 结论 |
|---|---|
| Full3D direct MPI1 | T4 old/new formal task contract pass；true residual `5.520787756471226e-14`；R=`0.9997827084780738`、T=`0.00010870177442776488`、A_volume=`0.00010858974749584228`；canonical selected fields `not_run_by_capability` |
| Hybrid direct MPI4 | T5 formal task contract pass；residual legacy/new=`5.014855373361551e-12`/`3.891075584849558e-12`；new hash-pinned summary SHA `2dadaf0554cdaae64a88e90d7d7146b34897f1ec075c25dc2a5c5f1d4ed22505`，R=`0.08902106910587838`、T=`0.4425867427441033`、A_balance=`0.4683921881500183`、A_volume=`0.46839218817098305`、closure=`2.096478546320668e-11`；exact NNZ diagnostic non-invariant |
| Hybrid iterative MPI8 | T6 formal pass；1771 iterations；five residuals all under task limit，最大 traction `4.880059476090313e-09`；R=`0.3656257867289616`、T=`0.012990632358457535`、A=`0.6213835809125808`、A_volume=`0.6213835766254876`、closure=`-4.287093235966211e-09`；process-tree RSS `6585.01953125 MiB`、swap0、998.13832s |
| T7 2D/Stage1 | 4 serial light PDE runs old/new at same SHA；2D residual `4.595181492041868e-15`，Stage1 `1.0869658196017029e-16`；all required shared observables pass |

上述数值来自 [`summary.md`](outcomes/summary.md) 与对应 compact records。不同 RSS 口径（solver-reported per-rank historical peak、process-tree simultaneous peak）只作记录，不能计算节省比例。T6 第一次 attempt 的唯一失败是 adapter 错读 `source.after.commit_sha` 而真实字段为 `source.after.head`；数值/物理/lifecycle 已通过，该负证据保留在 compact record，第二次只做同一修复后的正式运行。

## 测试与 Gate

T1–T9 的阶段 Gate、source SHA 和记录索引见 [`outcomes/test_summary.md`](outcomes/test_summary.md)。T9 已有 295 passed/2 skipped、Ruff/format、compileall、JSON/98 links、302/302 benchmark check。T10 文档前 Gate 为 17 passed；首轮 full 因 worktree `.venv` identity diagnostic 返回 1118 passed、48 skipped、1 failed，随后 targeted node `1 passed in 0.98s`，最终环境纠正后的 full 为 1119 passed、48 skipped、0 failed in 1514.73s。首轮 ABI failure 原始 evidence 保留，final pass 未掩盖它。最终 docs-only static Gate 另有 47 focused passed、302/302 benchmark、JSON/link/diff checks 通过；3 个继承 formatter debt 按 accepted inherited formatting qualification 记录，未冒充 format pass。

## 删除、保留与限制

11 个 migrated 与 6 个 retained 的逐项处置见 [`outcomes/preset_migration.md`](outcomes/preset_migration.md)；五个旧模块删除的 call graph 证据见 [`outcomes/legacy_cleanup.md`](outcomes/legacy_cleanup.md)。ordinary defaults、solver 数学和 research replay 未改。T4/T5 canonical export/selected-field comparison 是 capability boundary；T6 preferred 6 GiB 是资源偏好而非硬性数值失败；历史 Task37 compact 只作不同 source 的上下文，不是假装同 SHA formal comparator。

## 当前状态

T10 已完成 environment-corrected final full Gate：1119 passed、48 skipped、0 failed。首轮 failure、targeted 1 pass 与 final pass 的三阶段身份见 `outcomes/test_summary.md`；第二次只纠正共享 qualified venv 的 worktree identity，没有修改代码、测试、阈值或 default。本 response 随 Task38 closeout 提交到执行分支供 review；未申请或合并 master。
