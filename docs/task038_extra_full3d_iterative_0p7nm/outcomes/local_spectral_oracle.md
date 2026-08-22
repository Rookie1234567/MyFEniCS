# N1 local-spectral oracle（p2/p3、h=50 nm）

本阶段验证的是一个很小的、可审查的局部辅助算子：每个真实 hexahedral
cell 上用 `B0` 和 local volumetric mass `M` 生成固定的三条梯度候选与五条
正谱候选，再按固定 cell/mode 顺序做 regional Rayleigh--Ritz。它的作用是
验证局部材料、方向、Floquet/MPC 约束、owner-local factor 和 canonical
source/action 在 MPI 分区变化后仍一致；它不是 T3 的完整物理 operator，也
没有进入 N2/PDE/contraction。

## 结论

四个冻结 case 的 individual checker、两个 MPI pair checker 和 aggregate
均通过。MPI Gate 是 canonical full-space local source/action 的数值比较，
不是 regional basis 的 bitwise hash；mode ordering/phase 由每个 case 的
independent repeat `<=1e-13` 裁决。

| 项目 | 结果 |
|---|---|
| implementation source | `5ab68c14a8b4922df14a6471977a35677f540504` |
| case 集合 | p2-mpi1、p2-mpi2、p3-mpi1、p3-mpi2，均 h=50 nm |
| local algebra | 四案均 PASS；Hermitian、projected eigen、fixed solve、PoU/RP 均按各自 Gate 通过 |
| canonical MPI identity | p2/p3 source relative `0.0`；action relative 分别 `1.8605718413098607e-16`、`2.0089698816204241e-16` |
| repeat | 四案 source/action exact repeat，relative `0.0`；mode repeat exact |
| regional projector/packet | 保留为 measured diagnostic debt：`1.59451e-11` / `1.66085e-10`；不是 N1 hard Gate，不写成 PASS |
| N2/PDE | `not_run`；本阶段没有 physical RHS、KSP/PDE 或 contraction |

## Individual gates

数值指标来自独立 checker 从 ignored raw facts/NPZ 重算，而不是读取 worker
的 status。`regional residual` 和 `regional mass` 仅列作诊断，不能替代
canonical full-space source/action Gate。

| case | keys | UFL oracle（MPI1） | max B/M/gradient/projected/fixed residual | PoU / R-P | regional residual | checker |
|---|---:|---:|---:|---:|---:|---|
| p2-mpi1 | 720 | `1.0014682260391434e-15` | `3.578494639933735e-15` | `0.0 / 7.693864544320264e-16` | `1.7592475072253174e-14` | PASS |
| p2-mpi2 | 720 | not run（MPI2 boundary） | `2.7148741560045843e-15` | `0.0 / 7.181335680989415e-16` | `2.324464943678758e-14` | PASS |
| p3-mpi1 | 2349 | `1.2971226992449333e-15` | `6.441478248586372e-15` | `0.0 / 8.450022252381304e-16` | `2.563543642076944e-15` | PASS |
| p3-mpi2 | 2349 | not run（MPI2 boundary） | `6.309896779017945e-15` | `0.0 / 1.3836360623955716e-15` | `4.647475301838004e-15` | PASS |

四案的 `B0` 与 `M` Hermitian defect 也由 checker 独立读取 raw facts：p2
最大约 `4.03e-17`，p3 最大约 `8.81e-17`；所有 local gradient rank 均为 3，
所有 exact class 共 27 个，owner factor count 为 27。local dense B0/M 在
建立 modes 和 fixed-RHS solve residual 后释放；长期 evidence 不保留 dense
cell matrix。

## MPI pair 与禁止项

| pair | source relative L2 | action relative L2 | limit | 结果 |
|---|---:|---:|---:|---|
| p2 MPI1↔MPI2 | `0.0` | `1.8605718413098607e-16` | `1e-12` | PASS |
| p3 MPI1↔MPI2 | `0.0` | `2.0089698816204241e-16` | `1e-12` | PASS |

生产路径的 audit 明确为 `global_numeric_allgather=false`、
`global_aij=false`、`global_schur=false`、`global_factor=false`；每个 exact
class 只在 deterministic owner 保留一份 packed factor。MPI2 的 canonical
source/action 是 owner-local NPZ shard，checker 离线按 key 求和/比较；它不
是 solver 运行期的 numeric allgather。

regional expanded projector 与 packet 的历史 p2 诊断分别为
`1.59451e-11` 和 `1.66085e-10`。这说明 regional mode 的跨分区数值仍有
诊断债务，不能把它改写成 MPI hard-pass；当前 Review V4 规定的 hard MPI
observable 是上表的 full-space source/action，且 mode 语义由 repeat 决定。
旧 regional hash 是 raw-coordinate comparator 的产物，不代表物理算子改变。

## 资源与证据

formal worker 使用 qualified activation、线程 1，并以 `/usr/bin/time -v`
保存每个命令的 wall、单一 timed process 的 max RSS 和 swap；没有把它冒充
process-tree watchdog Gate。四案日志均 `Exit status: 0`、`Swaps: 0`。

| case | wall | `/usr/bin/time` max RSS | swap | raw/check |
|---|---:|---:|---:|---|
| p2-mpi1 | 3.89 s | 260548 kB | 0 | `benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/p2_mpi1/raw` / `benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/p2_mpi1/check.json` |
| p2-mpi2 | 2.43 s | 206764 kB | 0 | `benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/p2_mpi2/raw` / `benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/p2_mpi2/check.json` |
| p3-mpi1 | 1:04.31 | 693096 kB | 0 | `benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/p3_mpi1/raw` / `benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/p3_mpi1/check.json` |
| p3-mpi2 | 8.63 s | 229924 kB | 0 | `benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/p3_mpi2/raw` / `benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/p3_mpi2/check.json` |

完整 ignored 根为
`benchmarks/artifacts/task038_extra_full3d_iterative_n1_formal_v1/5ab68c1/`。
其中保留 worker `record.json`、`facts.json`、per-rank canonical NPZ、manifest、
UFL oracle（MPI1）和 log；tracked compact records 为：

| tracked compact | SHA256 |
|---|---|
| `records/n1_local_spectral_p2_mpi1_v1.json` | `76eefcacad98aabb8ecc218a9ba6d47cfaed850b72ea5e9b245b893e106f281c` |
| `records/n1_local_spectral_p2_mpi2_v1.json` | `9ae784aadc40a736b06420ba12bf2a9eb0216956b3c3ea39476477eff938e8e5` |
| `records/n1_local_spectral_p3_mpi1_v1.json` | `5564e0737fc4bf0335e1620782cba0779e886924ab84ccbd33dbc93eb717241d` |
| `records/n1_local_spectral_p3_mpi2_v1.json` | `120e1e591cb1ab3d72667db367ba65c1d39a8a542ef3b9f20085d67b277df476` |
| `records/n1_local_spectral_aggregate_v1.json` | `c3add6b05f67ae96d30055fdad88f9ab9b6e1474bdcd0bd0d84edc195bd84880` |

第一次 aggregate 使用 case 内部的 `record.json` 路径，checker 按 Review 固定
文件名配对而报告缺 pair；该非数值路径缺陷保留在 ignored
`aggregate_check.json`（SHA256 `37d1930b57ab690a319762ba3f96ce05238e7670854df40c1f003f924416b02f`）。
将已通过 compact records 放到固定 records 名称后，未重跑 worker 的
`aggregate_check_v2.json` PASS（SHA256
`c3add6b05f67ae96d30055fdad88f9ab9b6e1474bdcd0bd0d84edc195bd84880`）。

本阶段只证明 p2/p3 的 local-spectral oracle 和 canonical source/action；不
授权 N2，不改变 Candidate C 的 close/do-not-merge 结论，也不把小 fixture
的内存/资源结果推广为 p6 或完整 PDE 结论。
