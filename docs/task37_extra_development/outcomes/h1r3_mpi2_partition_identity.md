# H1R3.1 MPI2 分区身份与资源资格化

## 结论

本次测量验证的是 full-space matrix-free action：把有限元向量输入直接作用到
`A_h = curl-curl - k0^2 * epsilon * mass`，不先保存全局矩阵，并检查 MPI2 分区结果
与冻结的 MPI1 canonical dual authority 是否一致。它不是 PDE/KSP 求解、不是直接法
PDE 结果，也没有生成 physical field 或 RTA。

| 范围 | 结论 |
|---|---|
| H1R3.1 MPI2 action / partition identity | **PASS** |
| H1R3.2 | `eligible_by_review_v6`，本轮未运行 |
| H2 | `locked` |
| watchdog / checker | 各运行一次，无重跑 |

这表示候选 action 在规定的小范围内完成了数值、分区身份和资源 Gate；不能外推为
PDE、KSP、直接法或物理场结果。

## 身份与复现入口

| 项目 | 值 |
|---|---|
| branch | `codex/20260806-task37-iterative-extra-development` |
| source SHA | `c133a803d6086f6df8bf2cf703a53b43a79419c1` |
| case | p6 / h10 / MPI2 / `seed_17037` |
| reference / candidate apply | `1 / 2` |
| raw 目录 | [`benchmarks/artifacts/task037_extra_h1r3_mpi2_v6_c133a803_20260810_run1`](../../../benchmarks/artifacts/task037_extra_h1r3_mpi2_v6_c133a803_20260810_run1) |
| compact record | [`h1r3_mpi2_partition_identity.json`](../../../benchmarks/cases/101_task37_extra_development/records/h1r3_mpi2_partition_identity.json) |
| 历史 MPI1 authority | `benchmarks/artifacts/task037_extra_h1r2_v4_66ccb589_mpi1_20260809_run1` |

正式 watchdog 命令如下；它内部固定使用 MPI2、600 秒和 0.75 GiB 进程树限制：

```text
python -m benchmarks.run_task037_extra_candidate_h h1r3-mpi2-watchdog --run-dir benchmarks/artifacts/task037_extra_h1r3_mpi2_v6_c133a803_20260810_run1
```

watchdog 结束后只运行一次 checker：

```text
python -m benchmarks.run_task037_extra_candidate_h h1r3-mpi2-check --run-dir benchmarks/artifacts/task037_extra_h1r3_mpi2_v6_c133a803_20260810_run1 --mpi1-run-dir benchmarks/artifacts/task037_extra_h1r2_v4_66ccb589_mpi1_20260809_run1 --output benchmarks/cases/101_task37_extra_development/records/h1r3_mpi2_partition_identity.json
```

## Gate 与实测值

“相对误差”是两个向量之差的范数除以参考向量范数；它越接近零，说明同一离散 action
在数值上越一致。“canonical dual packet”是按物理实体和对偶变换整理的逐行数据包，
用于排除 MPI DoF 编号差异造成的假一致。

| Gate | 实测 | 限值/要求 | 状态 |
|---|---:|---:|---|
| same-run relative error | `2.663167576790903e-17` | `<=1e-11` | PASS |
| finite / deterministic | `true / true` | 均为 true | PASS |
| MPI2 vs MPI1 canonical relative L2 | `5.727032975605686e-15` | `<=1e-12` | PASS |
| missing / extra / duplicate | `0 / 0 / 0` | 全部为 0 | PASS |
| canonical packet count | `164592` | `173802 - 9210` | PASS |
| reference apply | `0.5931584620848298 s` | 有限且为正 | PASS |
| candidate apply 1 | `0.6048498440068215 s` | 有限且为正 | PASS |
| candidate apply 2 | `0.6196997419465333 s` | 有限且为正 | PASS |
| candidate2 / reference | `1.0447456819016228` | `<=2` | PASS |
| candidate2 fixed limit | `0.6196997419465333 s` | `<=2.390866201836616 s` | PASS |
| global payload / global rows | `6,988,752 / 173,802 = 40.21099872268444 B/row` | `<=45 B/row` | PASS |
| rank0 local payload | `3,492,456 B` | components 精确闭合 | PASS |
| global max payload | `3,496,296 B` | `local <= max <= sum` | PASS |
| completed process-tree peak | `636,989,440 B = 0.5932426452636719 GiB` | `<=0.75 GiB` | PASS |
| swap | `0 B` | `0` | PASS |
| completion | `9.08211386599578 s` | `<=600 s` | PASS |

action timing 是 MPI `MAX` reduction 的测量，不包括 canonical export。阶段 marker 是
辅助诊断：从 worker 起点到 reference apply 开始约 `3.91 s`，canonical export 约
`2.92 s`；因此总 wall time 还包括高阶空间、Floquet MPC、form/reference setup 和
canonical I/O，不能用 action timing 代替总运行时间。

## 分区、payload 与禁止对象

| 项目 | 实测 |
|---|---:|
| MPI2 global rows | `173802` |
| MPI2 global constraints | `9210` |
| rank0 owned / ghost / local storage rows | `87018 / 12876 / 99894` |
| rank0 local constraint NNZ | `4632` |
| retained payload local / global sum / global max | `3,492,456 / 6,988,752 / 3,496,296 B` |

payload 由 coefficient/output local storage、MPC flat indices、conjugated coefficients、
constraint work、owned-slave work 等组件组成；组件之和等于 local payload，MPI sum/max
分别形成 global sum/max，没有把 ghost 存储错误地扣除。

| 禁止对象或变化 | 审计值 |
|---|---:|
| global matrix materialized | `false` |
| global constraint matrix materialized | `false` |
| global condensed Schur materialized | `false` |
| cell Schur matrix NNZ / materialized | `0 / false` |
| slab matrix NNZ / materialized | `0 / false` |
| retained dense cell tensor count | `0` |
| cell metadata retained | `false` |
| factor count | `0` |
| KSP created | `false` |
| DtN used | `false` |
| ordinary default changed | `false` |

## Canonical authority

MPI2 当前运行与历史 MPI1 authority 使用不同源码 SHA，这是预期的历史基线关系，
不是要求两次运行源码相同：

| authority | source SHA | manifest SHA |
|---|---|---|
| 当前 MPI2 | `c133a803d6086f6df8bf2cf703a53b43a79419c1` | `6b6374aae471c652a254616c154364831f8308dc3e94829755f15c76fd3b28f0` |
| 冻结历史 MPI1 | `66ccb5891b7f6caac3ebfe08f72cf525c40f3fef` | `1dfdcbfcd73010234dcdb7438eb3d869c9cbd07ed6981fc0ba5275c170faf139` |

checker 验证了当前与历史 manifest 的 role、dtype、packet key、缺失/额外/重复项及
数值 L2；历史 raw 的 run summary、watchdog summary、manifest bytes/SHA 和内嵌 evidence
hash 也均通过绑定检查。

## Evidence SHA256 索引

raw 目录：`benchmarks/artifacts/task037_extra_h1r3_mpi2_v6_c133a803_20260810_run1`

| raw 文件 | SHA256 |
|---|---|
| `run_summary.json` | `3f6dafe850a6ca67bc94c1ac1a8866e5266ee34a5ab6aec42abd4859fdb00cc6` |
| `watchdog_summary.json` | `f41e5e32b87dc8db7fb12b2e4c7bf94b596e7a0686c540c7f9206f6dea11aada` |
| `watchdog_timeline.jsonl` | `1531af7e29b716d2dd8f3615bcaa20a8035bce46aa84637a24d1bd901f564e17` |
| `worker_stdout.txt` | `ca879bb6c22a459116e0def1c9087a852bce6632dc1d5f892b8d16a0e2e41a53` |
| `canonical/seed_17037/candidate_manifest.json` | `6b6374aae471c652a254616c154364831f8308dc3e94829755f15c76fd3b28f0` |
| `canonical/seed_17037/candidate_rank0.jsonl` | `fb2dfc78dfbe7d59b347f47ec4a33ce78e8ae40b6e23a8926f2bb98b3e9a221f` |
| `canonical/seed_17037/candidate_rank1.jsonl` | `4de54f93b0d75bd70b13f4824e69c4dc2332b2cdaee88879ce96c62387e281db` |

compact record [`h1r3_mpi2_partition_identity.json`](../../../benchmarks/cases/101_task37_extra_development/records/h1r3_mpi2_partition_identity.json) 的文件 SHA256 为
`2e927f1734c676a9df48972e0d4e353cabee085b91772e78159d48628a33020c`；其中嵌入的
`evidence_sha256` 为 `2a5489e9e984f8805d435825079e4d65e8981067ac78a2f79651cc07f4305413`。
两者分别是 record 文件本身的 SHA 和 record 内容的 evidence hash，不应混淆。

worker/watchdog 内容内嵌 evidence hash 分别为：

- worker：`a48346c8861d54b33c1c5b6ea815df57668a672fb29001b4171a13dd863f787c`
- watchdog：`5d95f96d20a531362fd4662e2ced818a6692d741231e70089ab9e606adda0e0d`

## 边界

本阶段的 action-only 进程树峰值也低于用户提出的 `<2,000,000,000 B` action-only
目标，但这不能推断未来 MPI1 PDE 运行仍低于 2 GB，也不能与直接法 PDE 的物理内存
口径或物理结果比较。本次只测 MPI2 action；PDE/KSP、field/RTA、DtN、H1R3.2 和 H2
不在本次测量范围内。H1R3.2 只是按当前 compact 的 `eligible_by_review_v6` 记录，
仍需后续审查授权。
