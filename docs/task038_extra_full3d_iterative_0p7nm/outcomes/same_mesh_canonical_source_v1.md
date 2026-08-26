# C0 同网格 H(curl) canonical source 资格证据

## 结论

V13 C0 在同一份新源码 `4dc9b55cd3519a03b23c9d27779c0379cef84f66` 下，以 p3/p1 同网格、h=50、MPI1 与 MPI2 各运行一次，独立 checker 均通过。因此本证据的分类是 **`C0_CANONICAL_SOURCE_PASS_MPI1_MPI2`**。它只证明物理 canonical source、owner packet 传递和约束闭合；没有运行 C1 solver、p6、PDE 或 official physics。

V12 的旧 C1 identity negative 仍原样保留：`same_mesh_hcurl_pmg_c1_mpi_identity_v1.json` 的 primal relative=`0.10049859821442367`、dual relative=`0.004662851981572301`，分类仍为 `CLOSED_BY_MPI_CANONICAL_IDENTITY_GATE`。C0 v4 是新 schema、新 artifact root 下的独立证据，不重分类这项历史结果。

## 固定身份与 Gate

| 项目 | 实测/固定事实 |
|---|---|
| 源码 / 分支 | `4dc9b55cd3519a03b23c9d27779c0379cef84f66` / `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| 网格与层 | p3/h50；fine/coarse=(3,1)；MPI1、MPI2 |
| Basix variant | fine/coarse 均 `legendre` |
| schema | record v3 / marker v3 / checker v4；canonical-source hash v1 |
| source Gate | key set exact；primal/dual source finite、nonzero；coefficient relative ≤`1e-13`、max abs ≤`1e-12` |
| transfer Gate | owner primal/adjoint、linearity、repeat、finite、input unchanged、phase-once、local/global adjoint 均通过 |
| architecture | no global high-order AIJ、no global transfer matrix、no numeric allgather、no p1 factor/KSP/smoother、no physical/recovery |

## 两次运行

| 指标 | MPI1 | MPI2 |
|---|---:|---:|
| watchdog peak process-tree RSS | 141,524,992 B | 262,807,552 B |
| swap / return / lifecycle | 0 B / 0 / natural, no orphan | 0 B / 0 / natural, no orphan |
| source primal packets | 162（102 independent + 60 dependent） | 162（102 + 60） |
| source dual packets | 2,538 independent | 2,538 independent |
| source primal relative | 0 | 0 |
| source dual relative / max abs | 1.3112141111956135e-17 / 2.2887833992611187e-16 | 2.012501428728352e-17 / 2.2887833992611187e-16 |
| global adjoint work relative | 1.6024250121032939e-15 | 5.8266238536862765e-16 |
| implemented vs explicit vector relative | 1.732205676136131e-17 | 1.2248543800056866e-17 |
| linearity / repeat | 1.377237509255599e-16 / 0 | 1.4396768382121543e-16 / 0 |

## Cross-MPI canonical identity

两个 rank-shard 合并后按 physical key 比较，未使用 PETSc global row、rank、local row、ownership 或 Python hash。两种 MPI 数的 source key set 均完整，missing/extra/duplicate 都是 `0`。

| 比较对象 | relative | max absolute |
|---|---:|---:|
| source primal | 0 | 0 |
| source dual | 1.950065385229289e-17 | 2.2887833992611187e-16 |
| projected primal | 7.098786108663455e-16 | 2.3738609781529628e-15 |
| adjoint dual | 4.1067748418222563e-16 | 9.103828801926284e-15 |

primal dependent values不是独立 hash source，而是由 master 与 Floquet/MPC 关系生成；实测 relation relative=`1.9801606126261387e-16`、max abs=`2.237726045655905e-16`。dual 使用 slave-zero storage，未重复施加 phase。

## 证据入口

完整紧凑记录见 [`same_mesh_hcurl_pmg_c0_v4.json`](records/same_mesh_hcurl_pmg_c0_v4.json)。原始 ignored artifact root 为：

`benchmarks/artifacts/task038_extra_full3d_c0_canonical_source_v4/4dc9b55cd3519a03b23c9d27779c0379cef84f66/`

| MPI | worker record SHA256 | checker SHA256 | watchdog compact SHA256 |
|---|---|---|---|
| 1 | `cb9f3550a78536a25542002edf242f1f57a338b308ae656e702801b7936d1ce6` | `fd045daba810c2aa4f0f6cab833aa6f319574ed2912e888933b79de9df389a89` | `943ee72c22719aadf6ddc040b734737f67bcb5391cc7fbe3fe571bd835f921ca` |
| 2 | `a68037b088f91a7546e824af981f0b2fb91a158036f9b8b5adb9e33aa4a138af` | `3d8d523f8ac7215ef93d25415469a0e5472f9fbb9e5c6c77c62ebb96419de5ef` | `ece8662f106790ad90e89e3a296ae161496e7a389e292f80d25cd02d024a6cd4` |

## 下一步边界

C1 的下一小块是 small p3/h50 same-mesh positive candidate，仍需独立 focused tests；本文件不把它写成已运行或已通过。ordinary default、V12 旧 negative、Route A/B 旧 evidence 均未修改。
