# Task037-extra Response V4：H1R2 单源全空间 action

本 response 更新原 archived stub，固化 Review V4.2 唯一一次正式 H1R2 action-only
evidence。H1R2_PASS 的含义是：frozen p6/h10、MPI1、单一 `seed_17037` 的完整
全空间 `A_h = curl-curl - k0^2 * epsilon * mass` action 通过了独立 reference、数值和资源 Gate；这是 curl 项与带负号的频率-介电质量项，不是 coercive `B_h`。它不是
PDE/KSP solve，不是 physical field/RTA，也不是 H2 smoother。

## 1. Consolidated status

| 阶段 | 当前状态 | 边界 |
|---|---|---|
| H0 | `H0_PASS` | capability-only |
| H1R.0 | `PASS` | progress markers 已实现并测试 |
| H1R.1 | `H1R.1_PASS` | p2/p3/p4/p6 单元 action 证据 |
| H1R.2 | `H1R2_PASS` | p6/h10、MPI1、single-source exact action |
| H1R.3 | `locked_pending_review` | 只具备下一轮 review 讨论资格 |
| H2/H3/H4 | `locked` | 未运行、未解锁 |
| H1.2 historical | `CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED` | 保留负证据，不改写 |
| G2 | `G2_FAIL` | LOR-HX 结论冻结 |
| G3 additive LOR-HX | `prohibited` | 不重开、不扫描 |
| old G4 sweep | `prohibited` | failed LOR-HX 后禁止 |
| ordinary default | unchanged | Candidate H 仍为显式研究路径 |

## 2. 身份与正式结果

| 项目 | 值 |
|---|---|
| branch | `codex/20260806-task37-iterative-extra-development` |
| measurement source SHA | `66ccb5891b7f6caac3ebfe08f72cf525c40f3fef` |
| implementation commit | `032fb7d812648d4c8b286babdf1cafe1ac70cd59` |
| runtime provenance commit | `66ccb5891b7f6caac3ebfe08f72cf525c40f3fef` |
| source start/end | 同一 SHA，均 clean |
| source/MPI/applies | `seed_17037` / MPI1 / reference=1、candidate=2 |
| rows/constraints | `173802 / 9210` |
| completion/wall | `14.121019201120362 s / 14.13039601710625 s` |
| live samples | `56` |

## 3. 数值、时间和内存 Gate

| 指标 | 值 | 结论 |
|---|---:|---|
| reference first apply | `1.1653526849113405 s` | 记录 |
| candidate first/second | `1.2354860971681774 / 1.195433100918308 s` | 记录 |
| candidate second/reference | `1.0258122853248122` | `<=2` PASS |
| relative error | `2.7326039504560278e-17` | `<=1e-11` PASS |
| finite/deterministic/repeat | `true / true / true` | PASS |
| process-tree peak | `332636160 B = 0.30979156494140625 GiB` | live worker tree |
| swap | `0` | PASS |
| Review V4 `<=1.25 GiB` | `PASS` | 资格 authority |
| 用户 decimal `<2,000,000,000 B` | `PASS` | 独立的、更宽用户目标 |

Review V4 的 `1.25 GiB` 与用户的 decimal `<2,000,000,000 B` 是两个不同门槛，
不能混写。本次实测同时低于二者，因此不需要继续为这个单源 MPI1 结果做 `<2GB`
优化；不能外推到更大网格、MPI 或 PDE。

## 4. Action 存储与 canonical evidence

| 审计项 | 值 |
|---|---|
| retained payload | `6151104 B = 5.86614990234375 MiB = 0.005728662014007568 GiB` |
| component/local/global-sum/global-max | 全部 `6151104 B`，闭合，`<=0.50 GiB` PASS |
| dense cell tensor | `0` retained，per-apply `false` |
| global A / constraint matrix / Schur | `false / false / false` |
| factor / KSP / DtN | `0 / false / false` |
| per-apply packed temporary | `3556224 B`，使用后释放，不计 retained |
| canonical export | `true`，仅在 numerical Gate 后执行，不计 action timing |
| packet count/duplicates | `164592 = 173802-9210 / 0` |
| manifest | `canonical/seed_17037/candidate_manifest.json` |
| manifest SHA256 | `1dfdcbfcd73010234dcdb7438eb3d869c9cbd07ed6981fc0ba5275c170faf139` |

runtime identity 为 marker=`1`、Python
`/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python`，
`OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS` 均为`1`；watchdog 与 worker 完全匹配。
当前仓库 `.venv` 与该 qualified shared target 是同一 symlink target，不是
Windows/ABI 混用。

## 5. Evidence 索引

Raw ignored directory：
`/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_h1r2_v4_66ccb589_mpi1_20260809_run1`

| raw file | SHA256 |
|---|---|
| `run_summary.json` | `bcf220a7b62ce803387a71c6dd3cefed0447f6ada17234328106aa23b785114c` |
| `watchdog_summary.json` | `f8228385afc128aa3d2fd8a49398957da4d68d9eb6a634692748fe3a10ceae6a` |
| `watchdog_timeline.jsonl` | `61ffb299b4fd9a22bd65468e81bec8f28759295d6d8fea281ccdba2f4962a2a0` |
| `worker_stdout.txt` | `b83ac543bc909515c05b9a4109831d9d6b69a641caaada4f96f69592981988b9` |
| `canonical/seed_17037/candidate_manifest.json` | `1dfdcbfcd73010234dcdb7438eb3d869c9cbd07ed6981fc0ba5275c170faf139` |

完整命令、raw 索引和 compact checker record 见 [H1R2 outcome](outcomes/h1r2_single_source_action.md)。

Compact checker record：[h1r2_single_source_action.json](../../benchmarks/cases/101_task37_extra_development/records/h1r2_single_source_action.json)

| compact evidence | 值 |
|---|---|
| record SHA256 | `3be688f6e0794b47fb7d77f3823cb2e69b78aefaec6ea31833d3a0421acab978` |
| record `evidence_sha256` | `eeb002ad7d4091aec4aaf34055379f2a8f3bc4c64a46b3dda11328f8b28d0513` |
| checker result | `pass=true`、`status=pass`、`problems=[]` |
| all check groups | `true` |

## 6. Verification and next boundary

最终 targeted suite 为 `36 passed`；compileall 与 `git diff --check` 通过；Ruff
unavailable，未安装，不能写成 CI pass。没有触发 hard stop。

本轮未运行 MPI2、H2、H3、H4、full PDE、KSP、DtN、official field 或 official
RTA。H1R2_PASS 只支持向主审提交下一轮 H1R3 review 讨论，不代表 H1R3 或 H2 已解锁。
G2_FAIL、G3 prohibited、old G4 prohibited、old H1.2 timeout/not qualified 均保持。
