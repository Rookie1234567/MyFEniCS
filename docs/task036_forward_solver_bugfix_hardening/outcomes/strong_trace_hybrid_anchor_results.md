# Task036 Review V3：strong trace-subspace Hybrid 锚点结果

## 1. 最终结论

```text
A004-S = HYBRID_STRONG_TRACE_IMPLEMENTATION_FAIL
A004-S resource advantage = pass
A049-P = not_run_due_to_A004_gate
A001-P = not_run_due_to_A004_gate
M160 = not_authorized
production_candidate = none
ordinary_default = unchanged
next_route = Full3D_static_condensed_iterative
```

strong-trace 方程本身工作正常：它把接口切向电场从旧 Hybrid 的约 `9.27e-5` 相对跳跃
压到约 `4.59e-15`，同时把正式系统降到 13,296 rows，并把峰值保持在 Full3D 的
74.82%。但是正式物理 Gate 仍未闭合：

- `abs(R+T+A_volume-1)=1.531666e-5 > 1e-5`；
- 固定衍射通道仅 `77/96` 通过。

Review V3 明确把 energy identity failure 分类为 implementation failure，并要求三个
anchor 按顺序推进。因此 A049-P、A001-P 和 M160 均不得运行。

## 2. 权威身份

### 2.1 source

| 角色 | 完整 SHA | 说明 |
|---|---|---|
| Review V3 base | `33d0180cd2ed70218f3199ec69372bbefa03bba5` | 含 Review V3 |
| A004-S numerical source | `5b04a4398fe752083024487ca95eb00a09e646cc` | 矩阵、解、场、R/T/A 和资源 authority |
| residual telemetry fix | `a5b86a319af3cfc88d5de5801f2e8131f89a9be4` | 只修复齐次分区归一化，不改变 numerical solution |
| reused Full3D source | `6d5e9781bcb1458ecac7a77af22fa2d420f0cd55` | same-input p5/h10/Ny4 MPI8 authority |

环境：

```text
WSL Ubuntu 24.04
MPI = 8
Python = /home/Projects/MyFEniCS/.venv/bin/python
PETSc.ScalarType = complex128
PETSc.IntType = int32
DOLFINx = 0.10.0.post2
backend = assembly_time_static_condensed
p = 5
h = 10 nm
Ny = 4
M = 120 per direction
```

### 2.2 raw artifact

```text
benchmarks/artifacts/task036/
  5b04a4398fe752083024487ca95eb00a09e646cc/
    review_v3_strong_trace/A004-S/hybrid_strong_m120/
```

| 文件 | SHA-256 |
|---|---|
| `solver_record.json` | `340185586d976fc34f1ab11ddaa12eab19072ff23e8f4be8ec8bf5e0089e1511` |
| `memory_sampler_summary.json` | `b70cd1965ac59fdd9cf668866269062c41951f2eed22395ee32cf68ddd1a3585` |
| `memory_timeline.csv` | `533c6397de7ec4da5f40d245dfc871e8244f6596b504efcd6a22b65231598573` |
| reused Full3D `watchdog_summary.json` | `f91d30d7237c1f39aae7633309dc076e5acf04532f92214024fb48e691a9cfb8` |
| old Hybrid `solver_record.json` | `b40d000e3fa906b0349cfbdffac44b5c9b62f4f0a1c7bc63232b45d6b60f5c36` |
| old Hybrid `memory_sampler_summary.json` | `73ff8f1c427d032cfe6e3407f348ad134dbbb225fdc2f8b76c090f1c2da8cd98` |

Full3D cross-SHA preflight 检查了输入、geometry、mesh、degree、polarization、backend、
MPI、raw artifact hash 和允许的 source diff，结果为 pass；没有重跑 Full3D。

## 3. 三个 anchor 的执行状态

| 顺序 | anchor | 固定输入 | 状态 | 原因 |
|---:|---|---|---|---|
| 1 | A004-S | 0.5° / 45° / S | measured negative | energy 与 fixed-channel Gate failed |
| 2 | A049-P | 10° / 90° / P | `not_run_due_to_A004_gate` | 顺序 Gate 未解锁 |
| 3 | A001-P | 0.5° / 0° / P | `not_run_due_to_A004_gate` | 顺序 Gate 未解锁 |
| optional | A001-P M160 | 同上 | `not_authorized` | A004 与 A049 均通过这一前提不成立 |

未运行项没有被推断为 pass 或 fail。

## 4. A004-S 数值 Gate

### 4.1 代数与物理

| Gate | 实测 | 限值 | 判定 |
|---|---:|---:|---|
| reduced true residual | `2.2893e-11` | `1e-9` | pass |
| bottom/top `D R-I` | `2.7638e-12 / 2.4151e-12` | `1e-10` | pass |
| bottom/top strong trace identity | `0 / 0` | `1e-10` | pass |
| bottom/top Petrov traction | `2.9292e-11 / 6.8286e-11` | `1e-8` | pass |
| bottom/top noninterface FE | `1.2173e-11 / 2.2557e-11` | `1e-9` | pass, first value offline renormalized |
| bottom/top external DtN | `1.4079e-13 / 1.3713e-12` | `1e-9` | pass, second value offline renormalized |
| biorthogonality row norm | `3.201e-7` | `1e-6` | pass |
| direct tangential projection | `1.100e-12` | `1e-10` | pass |
| geometry projection support | bottom/top `true` | complete | pass |
| Full3D max `abs(Delta R/T/A_volume)` | `1.2110e-5` | `1e-4` | pass |
| energy closure | `1.531666e-5` | `1e-5` | **fail** |
| fixed channel contract | `77/96` | `96/96` | **fail** |
| swap | `0` | `0` | pass |

原始 artifact 把 bottom noninterface 和 top external DtN 各报告为 `formal_relative=1`；
这是齐次分区的分母错误，不是 PDE 残差。原始绝对残差、全局尺度和失败 artifact 均原样
保留。提交 `a5b86a3...` 修正了今后的 telemetry，但没有把当前 formal anchor 追认为
成功：energy 和 fixed channels 仍是真实失败。

### 4.2 R/T/A

| quantity | Full3D | old projection-only M120 | new strong-trace M120 | new - Full3D |
|---|---:|---:|---:|---:|
| `R_total` | `0.621460748388` | `0.621472860053` | `0.621472858503` | `+1.211012e-5` |
| `T_total` | `0.006248078496` | `0.006248145976` | `0.006248145689` | `+6.719246e-8` |
| `A_balance` | `0.372291173116` | `0.372278993972` | `0.372278995808` | `-1.217731e-5` |
| `A_volume` | `0.372291173114` | `0.372294323387` | `0.372294312469` | `+3.139355e-6` |
| `R+T+A_volume-1` | `-1.632e-12` | `+1.532942e-5` | `+1.531666e-5` | — |

strong trace 与 old Hybrid 的 R/T/A 几乎相同；它修正了接口空间，却没有修正这个
whole-domain energy 缺口。

## 5. 固定衍射通道

合同使用 Full3D 与 candidate 的 significance 并集：

```text
significant power floor = 1e-8
significant relative power/amplitude error <= 1e-3
weak absolute power/amplitude error <= 1e-8
```

共 96 个固定通道，其中 20 个 significant；77 个完整通过，以下 19 个至少一项失败。
表中 `P metric` 和 `amplitude metric` 已按 significant/weak 选择正式 relative/absolute
口径。

| side/order/pol. | 类别 | P metric | amplitude metric | 失败项 |
|---|---|---:|---:|---|
| bottom `(-6,-2,s)` | weak | `1.331e-13` | `8.518e-8` | amplitude |
| bottom `(-6,-1,s)` | weak | `7.251e-14` | `4.137e-8` | amplitude |
| bottom `(-5,0,s)` | significant | `9.030e-3` | `5.354e-3` | power, amplitude |
| bottom `(-4,0,s)` | significant | `4.554e-4` | `2.072e-3` | amplitude |
| bottom `(-3,0,s)` | significant | `5.758e-3` | `3.063e-3` | power, amplitude |
| bottom `(0,-2,p)` | weak | `1.307e-14` | `1.380e-8` | amplitude |
| bottom `(0,-2,s)` | weak | `1.305e-13` | `4.360e-8` | amplitude |
| bottom `(0,-1,s)` | weak | `8.122e-14` | `3.215e-8` | amplitude |
| bottom `(0,0,p)` | weak | `1.990e-13` | `1.607e-8` | amplitude |
| top `(-6,-2,s)` | weak | `2.177e-13` | `1.070e-7` | amplitude |
| top `(-6,-1,s)` | weak | `1.256e-13` | `5.426e-8` | amplitude |
| top `(-5,0,s)` | significant | `6.125e-3` | `8.338e-3` | power, amplitude |
| top `(-4,0,s)` | significant | `2.040e-3` | `1.961e-3` | power, amplitude |
| top `(-3,0,s)` | weak | `6.192e-11` | `6.614e-8` | amplitude |
| top `(-1,0,p)` | significant | `1.431e-3` | `7.196e-4` | power |
| top `(0,-2,p)` | weak | `1.854e-14` | `1.641e-8` | amplitude |
| top `(0,-2,s)` | weak | `1.844e-13` | `5.176e-8` | amplitude |
| top `(0,-1,s)` | weak | `1.344e-13` | `4.131e-8` | amplitude |
| top `(0,0,p)` | weak | `7.648e-12` | `2.137e-7` | amplitude |

这 19 个 identity 与 old projection-only M120 的失败集合完全相同；old/new 最大通道
power 差只有约 `1.47e-9`。因此“strong trace 没有改变失败通道”是实测机制信号，不是
把 77/96 改写成成功。

全部 96 个通道的逐项 old/new/Full3D 误差和判定保存在
[a004_strong_trace_fixed_channels_v1.csv](../../../benchmarks/cases/099_strong_trace_hybrid_fixture/records/a004_strong_trace_fixed_channels_v1.csv)。

## 6. 接口、场和传播诊断

| 指标 | old M120 | strong M120 | 解释 |
|---|---:|---:|---|
| sampled physical interface `E_t` max relative jump | `9.272e-5` | `4.588e-15` | strong restriction 达到机器精度连续 |
| bottom/top exact H(curl) Petrov traction | 历史 Gate pass | `2.929e-11 / 6.829e-11` | variational flux row pass |
| middle plane E max relative error vs Full3D | — | `2.647e-5` | sampled diagnostic |
| middle plane H max relative error vs Full3D | — | `2.915e-5` | sampled diagnostic |
| selected propagation forward coefficient mismatch | 共同模型 | `3.9956e-3` | 主要剩余机制信号 |
| selected propagation backward coefficient mismatch | 共同模型 | `8.3073e-5` | 较小 |

历史 A004-S M240 的 energy closure 为约 `1.532319e-5`，forward mismatch 仍约
`3.9961e-3`；M120 增到 M240 没有改善。A004-S 没有 M480/M492 artifact，本轮也没有
恢复这些禁止的高 M 漏斗。

同一套 beta、normal、port 和 volume ledger 在历史 A049-P M120–M492 上能达到约
`1e-6` energy closure。因此当前证据不支持一个通用的 top/bottom 法向、共轭、端口功率
或 Gauss 积分 bug。更可能的问题是 A004 低掠射 45° 下，逐模态对角 scalar-CG propagation
不能表示真实 cross-interface modal mixing。

## 7. rows、NNZ 与 factor

| 方法 | rows | matrix NNZ | factor NNZ | fill |
|---|---:|---:|---:|---:|
| Full3D static | `46,656` | `26,952,096` | `164,378,718` | `6.099` |
| old Hybrid M120 | `7,728 × 2 + 240` inventory | `8,011,296` local pair | `26,702,638` local pair | `3.333` inventory |
| strong Hybrid M120 | `13,296` monolithic | `8,901,696` | `29,290,898` | `3.291` |

strong 系统精确满足：

```text
g_b = 1200
g_t = 1200
retained_bottom = 6528
retained_top = 6528
modal = 240
N = 6528 + 6528 + 240 = 13296
```

old Hybrid 的两套 local factor 和 small modal Schur 不是一个同时存在的 monolithic
factor，所以该行明确标为 inventory；不能把两个 row count 冒充单一方阵。

## 8. 内存与时间

### 8.1 资源

| 方法 | formal RSS GiB | complete-rank PSS GiB | USS GiB | swap | peak stage |
|---|---:|---:|---:|---:|---|
| Full3D static | `10.5490` | `8.9508` | `8.5409` | `0` | direct projection audit |
| old Hybrid M120 | `7.4640` | `4.0353` | `3.6131` | `0` | direct projection audit |
| strong Hybrid M120 | `7.8930` | `4.5314` | `4.1049` | `0` | direct projection audit |

```text
strong / Full3D peak = 0.74822
memory reduction     = 25.178%
required ceiling     = 0.85
resource Gate        = pass
```

strong 比 old Hybrid 多约 `0.429 GiB` RSS，但仍低于 Full3D 的 85% 资格线。PSS/USS
只使用同时读到全部 8 个 MPI rank 的 `/proc/<pid>/smaps_rollup` 样本；正式 RSS 仍采用
simultaneous process-tree authority。

### 8.2 wall time

| 方法 | solver-record total s | whole-job wall s |
|---|---:|---:|
| Full3D static | `869.607` | `894.386` |
| old Hybrid M120 | `712.222` | `721.698` |
| strong Hybrid M120 | `484.913` | `488.577` |

strong 的主要 phase：

| phase | s |
|---|---:|
| cross-section/QEP assembly | `5.114` |
| positive/negative bases | `39.396` |
| two local FEM/DtN systems | `56.689` |
| internal modal coupling | `29.841` |
| strong monolithic build | `13.943` |
| MUMPS setup / backsolve | `8.880 / 0.028` |
| static field recovery | `38.991` |
| physical reconstruction | `31.089` |
| direct projection audit | `260.528` |

时间结果是 measured，但不能抵消物理精度失败。

## 9. 正式分类与机制判断

### 9.1 正式分类

按 Review V3 taxonomy：

```text
HYBRID_STRONG_TRACE_IMPLEMENTATION_FAIL
```

原因是 energy identity Gate failed。虽然 residual、trace、Petrov、channels totals 和资源中
的大部分指标通过，但不能选择性忽略 energy 或 19 个失败通道。

### 9.2 诊断判断

以下只是机制诊断，不是成功声明：

- strong trace 已完全消除自由接口 complement；
- old/new Hybrid 的 R/T/A、energy 和失败通道几乎不变；
- M240 没有改善 energy 或 forward propagation mismatch；
- scalar-CG endpoint derivative、traction beta、static recovery beta 和 p5 Gauss-6
  volume integration 均通过已有离线/单元合同；
- A049-P 对照表明通用 port/normal/ledger 可以闭合。

因此下一步若继续 Hybrid，需要 matrix-valued axial propagation 或 Full3D-derived modal
Schur，不能继续靠 M 阈值、penalty 或 trace 数量微调。这是新数值架构，超出本轮
BUGFIX_ONLY。

## 10. 停止判定

Review V3 的 M160 授权条件是：

```text
A004-S pass
and A049-P pass
and A001-P only modal truncation
and predicted M160 peak below Full3D
```

第一个条件已失败，所以：

- 不运行 A049-P；
- 不运行 A001-P；
- 不运行 M160；
- 不恢复 M240/M480/M492；
- 不恢复 226 点扫描；
- 不放宽 energy、channel 或 residual Gate；
- 不做人工能量校正。

本轮按审阅要求停止等待后续决策。建议的 production 主线是
`Full3D assembly-time static condensation + FGMRES + H(curl)/trace-aware preconditioner`；
Task036 Review V3 本轮没有开始该新架构。
