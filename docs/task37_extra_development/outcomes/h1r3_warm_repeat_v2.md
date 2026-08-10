# Task037-extra H1R3.0R：p6/h10 MPI1 warm-repeat 证据

本 outcome 固化 V6 R2 唯一一次 H1R3.0R 正式 action-only 运行及其一次 compact
checker 结果。这里的 action 是“给定向量后计算离散算子作用”的计算内核；它不是
KSP/PDE 求解，也不产生物理场或 R/T/A 结果。

## 1. 阶段结论

| 阶段 | 状态 | 准确含义 |
|---|---|---|
| H1R3.0R | `PASS` | 审计闭合后的 p6/h10、MPI1、单 source warm-repeat action Gate 全部通过 |
| H1R3.1 | eligible but not run | 已满足进入 MPI2 分区身份阶段的前置 Gate；不表示 H1R3.1 已通过 |
| H1R3.2 | locked pending H1R3.1 | 等待 H1R3.1 正式通过 |
| H2 | locked | 本轮未授权、未运行 |
| H3/H4/PDE/DtN/RTA | prohibited / not run | 不在本轮范围 |

冻结边界保持：G2=`G2_FAIL`，G3 additive LOR-HX 与旧 G4 sweep 禁止；历史 H1.2
仍为 controlled timeout/not qualified；ordinary default unchanged。H1R3.0R 通过只
说明 full-space volume action 的数值、重复调用和资源证据闭合，不是整体 Maxwell
算法或 PDE 收敛通过。

## 2. 固定范围与身份

| 项目 | 值 |
|---|---|
| source commit | `5529a0159ac5b1500b4ccbd17ad962e2a875f3f1` |
| source start/end | 同一完整 SHA，均 clean |
| degree / h / MPI | p6 / h10 / MPI1 |
| source | `seed_17037` |
| reference / candidate applies | 1 / 12 |
| timeout | 180 s |
| process-tree peak Gate | 483183820 B（0.45 GiB） |
| operator | `A_h=curl-curl-k0^2*epsilon*mass` |
| condensation / KSP / DtN | false / false / false |
| qualified marker | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Python | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` |
| PETSc | complex128 / int32 |
| threads | OMP、OPENBLAS、MKL、NUMEXPR 均为 1 |

正式 worker 与 reference 在同一 worker 内运行；reference 使用既有
`MpcFormActionContext`，candidate 使用独立的 rank-one MPC action。两者都只作为
action authority，不构成 PDE solver authority。

## 3. 数值与重复调用结果

| 指标 | 实测值 / Gate |
|---|---:|
| global rows / constraints | 173802 / 9210 |
| reference first apply | 1.163214989937842 s |
| first / last relative error | 2.7326039504560278e-17 / 2.7326039504560278e-17，PASS |
| finite / deterministic | true / true |
| output hash identity | 12 次完全一致，PASS |
| output SHA | `f768296b487cf219ec67768ea17f3a184b27db1f98b96a34853df026926938d5` |
| steady applies | 5--12 |
| steady median | 1.1820809360360727 s <= 1.494291376147885 s，PASS |

| apply | seconds |
|---:|---:|
| 1 | 1.1683549720328301 |
| 2 | 1.1550444040913135 |
| 3 | 1.1919087360147387 |
| 4 | 1.190561065915972 |
| 5 | 1.1751817010808736 |
| 6 | 1.165220373077318 |
| 7 | 1.1790020540356636 |
| 8 | 1.158993573859334 |
| 9 | 1.204139461973682 |
| 10 | 1.1851598180364817 |
| 11 | 1.1992779339198023 |
| 12 | 1.2208232989069074 |

## 4. Payload、资源与 canonical

| 项目 | 实测值 / Gate |
|---|---:|
| retained payload local / global sum / global max | 6151104 / 6151104 / 6151104 B，闭合且稳定 |
| payload components | coefficient 2780832、output 2780832、conjugated coefficients 147360、constraint work 147360、owned-slave work 147360；四类 index arrays 各 36840 B；packed constants 0 |
| packed temporary | 3556224 B，12 次稳定，apply 后释放 |
| 每次 process-tree RSS / PSS / USS | 340328448 / 320476160 / 306462720 B |
| steady RSS span | 0 B |
| completed process-tree peak | 340541440 B <= 483183820 B，PASS |
| swap | 0，PASS |
| completion / wall | 26.248778069857508 / 26.262791958870366 s |
| live samples | 104 |
| canonical export | 仅一次，且在 numerical Gate 后 |
| canonical packets / duplicates | 164592 / 0 |
| packet closure | 164592 = 173802 - 9210 |

用户更宽的 decimal 2 GB 目标也由该实测 peak 通过，但本结果的资格 authority 是更严格
的 0.45 GiB process-tree Gate；两者不混写。

## 5. Audit 闭合

本次 worker audit 明确写出 V6 R0 修复的四个字段：

| 字段 | 值 |
|---|---:|
| `cell_schur_matrix_nnz` | 0 |
| `slab_matrix_nnz` | 0 |
| `cell_schur_matrix_materialized` | false |
| `slab_matrix_materialized` | false |

同时保持：global matrix、global constraint matrix、global condensed Schur 均 false；
dense cell tensor per apply=false；retained dense cell tensor count=0；factor=0；
KSP=false；DtN=false；ordinary_default_changed=false。所有 compact checker check
groups 为 true，`pass=true`，`problems=[]`。

## 6. Evidence 索引

Raw ignored directory：

`benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v6_5529a01`

| raw file | SHA256 |
|---|---|
| `run_summary.json` | `f50063d6de5b2e98b159b639cf830b4000a299cd7c19fd67714ba373b4505c10` |
| `watchdog_summary.json` | `136602cd2c6fc4843eac7e82f6295ee3a1f6fb2e3287523bae37accf46ca9580` |
| `watchdog_timeline.jsonl` | `f774b32f8c2c19987a673fac9c9b450d21e87842f2a562ffc7828c518704a34a` |
| `apply_telemetry.jsonl` | `5564af2ecae680918671a92a24e64a59c70301d8e50b4c81eef89f41a8618f9f` |
| `worker_stdout.txt` | `eacc6435f7375c416ddda9d329a8e1c3aea167931d21dbf0407b456afbe4ca87` |
| `h1r3_root_pid.json` | `243cdd6e165fd089946ff891cc27bc55b61e2fa0a017875279be9cb4e507d123` |
| `canonical/seed_17037/candidate_manifest.json` | `279bf1c2a09608dbe4a0843bb8b745ee5053cd64fef11f32c31b3a3984a0e1bc` |
| `canonical/seed_17037/candidate_rank0.jsonl` | `5e49562a9501f6921b452db9c7afe297b644f7fdb8e400879abf426fbc9d526a` |

Compact record：[h1r3_warm_repeat_v2.json](../../../benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat_v2.json)

| compact item | 值 |
|---|---|
| record SHA256 | `b2e347c1663df932ace40efdee898ca1c6a62790ce30b748e64fcb721bcac658` |
| compact evidence SHA256 | `f86666a3a2c367ddd9b358a016b015e17ea8902ead912a1a451e12181dc80439` |
| embedded worker evidence SHA256 | `7d3069935aac8621512716587c2f0bf323a174f52d317b3f1c85cec73ff430bf` |
| embedded watchdog evidence SHA256 | `2acf3ac88b2c74e640248753b63b3081e854288854a3a09ce90772fee94ba385` |

旧 v1 evidence 保持不变：

| 文件 | SHA256 |
|---|---|
| [h1r3_warm_repeat.json](../../../benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat.json) | `88bcd9461f8bc8cc961b481c588d1c2c56f5b2d50b60ae097be27a24874d9745` |
| [h1r3_warm_repeat.md](h1r3_warm_repeat.md) | `f76c2d2191d8352388633f2130ceff007da755258300d681788f3f9dcf07fe9e` |

## 7. 范围边界

本次 PASS 只覆盖 p6/h10、MPI1、single-source 的 full-space volume action。未运行
MPI2 partition identity、h5 refinement、H2/H3/H4、KSP、PDE、DtN、official field
或 RTA；不得将本证据外推为 PDE 收敛或整体算法通过。

按 compact scope boundary：H1R3.1 为 `eligible_by_review_v5_if_H1R3.0_pass`，但仍
需单独正式运行与审阅；H1R3.2 为 `locked_pending_H1R3.1_pass`；H2 保持 locked。
